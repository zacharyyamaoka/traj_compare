"""Derive every comparison channel from raw situation recordings.

Per situation, computed on that situation's own time grid:

- joint space: ``q``, ``qd``, ``qdd``, ``tau``, ``current`` (velocity/
  acceleration fall back to ``np.gradient`` when not recorded; ``tau`` and
  ``current`` stay absent if absent — a missing channel is never invented);
- TCP pose: ``x, y, z`` and unwrapped extrinsic-xyz ``rx, ry, rz``;
- path progress and its two derivatives for four channel families:
  ``pct`` (percent of the reference path length completed — the end-effector
  progress/speed view), ``xyz`` (cumulative translational arc length),
  ``rpy`` (cumulative rotation, accumulated axis-angle), and one signed
  ``vec`` channel per configured direction (displacement projected onto the
  direction — point it along the conveyor to read belt-matching speed);
- error channels against the target resampled onto this grid: per-joint
  ``q`` error, ``xyz_mag`` (translation error norm) and ``rot_mag``
  (geodesic rotation error).

Because the plot library draws all overlaid series against one shared x
array, every display channel is then resampled onto a common ``plot_t``
(the target's grid when there is one), padded with nulls outside a
situation's own recorded span so shorter runs end in a visible gap instead
of a fabricated plateau. The 3D viewer block (``three``) keeps each
situation's native grid: positions, quaternions, and the same-time target
pose for difference arrows.

Everything stays SI (s, rad, m, Nm, A); unit conversion happens in the viewer.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np

from .model import Comparison, ReportTable, RobotDisplay, Situation, TableRow
from .rotations import (
    align_unwrapped,
    mat_to_quat,
    mat_to_rpy,
    rotation_angles_between,
    successive_rotation_angles,
    unwrap_rpy,
)

MAX_PLOT_POINTS = 5000
MAX_ROBOT_TRACK_POINTS = 2000


def _json_clean(value: Any) -> Any:
    """Recursively convert metadata into JSON-safe built-in values."""

    if isinstance(value, np.ndarray):
        return _json_clean(value.tolist())
    if isinstance(value, np.generic):
        return _json_clean(value.item())
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _clean(values: np.ndarray | None, decimals: int = 6) -> list | None:
    """Rounded nested lists with JSON-legal ``None`` for non-finite entries."""

    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    rounded = np.round(array, decimals)
    flat = rounded.reshape(-1)
    cleaned = flat.astype(object)
    bad = ~np.isfinite(flat)
    if np.any(bad):
        cleaned[bad] = None
    return cleaned.reshape(rounded.shape).tolist()


def _gradient(values: np.ndarray, t: np.ndarray) -> np.ndarray:
    if values.ndim == 1:
        return np.gradient(values, t)
    return np.stack([np.gradient(values[:, col], t) for col in range(values.shape[1])], axis=1)


def _situation_poses(situation: Situation, comparison: Comparison) -> np.ndarray | None:
    if situation.poses is not None:
        return situation.poses
    if comparison.fk is not None and situation.q is not None:
        poses = np.asarray(comparison.fk(situation.q), dtype=float)
        if poses.shape != (situation.q.shape[0], 4, 4):
            raise ValueError(
                f"fk for '{situation.name}' returned {poses.shape}, expected (N, 4, 4)"
            )
        return poses
    return None


def _resample_columns(t_from: np.ndarray, values: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    return np.stack(
        [np.interp(t_to, t_from, values[:, col]) for col in range(values.shape[1])], axis=1
    )


def _slerp_resample(t_from: np.ndarray, quats: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """Slerp a quaternion track onto a new grid (used when there is no fk)."""

    upper = np.searchsorted(t_from, t_to, side="right")
    upper = np.clip(upper, 1, len(t_from) - 1)
    lower = upper - 1
    span = t_from[upper] - t_from[lower]
    fraction = np.where(span > 0.0, (t_to - t_from[lower]) / np.where(span > 0, span, 1.0), 0.0)
    fraction = np.clip(fraction, 0.0, 1.0)

    q0 = quats[lower]
    q1 = quats[upper]
    dot = np.sum(q0 * q1, axis=1, keepdims=True)
    q1 = np.where(dot < 0.0, -q1, q1)
    dot = np.abs(np.clip(dot, -1.0, 1.0))
    theta = np.arccos(dot)
    sin_theta = np.sin(theta)
    near = sin_theta[:, 0] < 1e-8
    w0 = np.where(near[:, None], 1.0 - fraction[:, None], np.sin((1 - fraction[:, None]) * theta))
    w1 = np.where(near[:, None], fraction[:, None], np.sin(fraction[:, None] * theta))
    scale = np.where(near[:, None], 1.0, sin_theta)
    blended = (w0 * q0 + w1 * q1) / scale
    return blended / np.linalg.norm(blended, axis=1, keepdims=True)


def _quat_to_mat(quats: np.ndarray) -> np.ndarray:
    w, x, y, z = quats[:, 0], quats[:, 1], quats[:, 2], quats[:, 3]
    matrices = np.empty((len(quats), 3, 3))
    matrices[:, 0, 0] = 1 - 2 * (y * y + z * z)
    matrices[:, 0, 1] = 2 * (x * y - w * z)
    matrices[:, 0, 2] = 2 * (x * z + w * y)
    matrices[:, 1, 0] = 2 * (x * y + w * z)
    matrices[:, 1, 1] = 1 - 2 * (x * x + z * z)
    matrices[:, 1, 2] = 2 * (y * z - w * x)
    matrices[:, 2, 0] = 2 * (x * z - w * y)
    matrices[:, 2, 1] = 2 * (y * z + w * x)
    matrices[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return matrices


def _target_on_grid(
    comparison: Comparison,
    target: Situation,
    target_poses: np.ndarray | None,
    t_to: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Target joint track and poses resampled onto another situation's grid."""

    q_resampled = _resample_columns(target.t, target.q, t_to)
    if comparison.fk is not None:
        return q_resampled, np.asarray(comparison.fk(q_resampled), dtype=float)
    if target_poses is not None:
        positions = _resample_columns(target.t, target_poses[:, :3, 3], t_to)
        quats = _slerp_resample(target.t, mat_to_quat(target_poses[:, :3, :3]), t_to)
        poses = np.tile(np.eye(4), (len(t_to), 1, 1))
        poses[:, :3, :3] = _quat_to_mat(quats)
        poses[:, :3, 3] = positions
        return q_resampled, poses
    return q_resampled, None


def _path_channels(
    poses: np.ndarray,
    t: np.ndarray,
    vec_dirs: list[tuple[str, np.ndarray]],
    pct_total: float | None,
) -> dict[str, np.ndarray]:
    positions = poses[:, :3, 3]
    steps = np.diff(positions, axis=0)

    xyz = np.concatenate([[0.0], np.cumsum(np.linalg.norm(steps, axis=1))])
    rpy = np.concatenate([[0.0], np.cumsum(successive_rotation_angles(poses[:, :3, :3]))])

    total = pct_total if pct_total and pct_total > 1e-9 else (xyz[-1] if xyz[-1] > 1e-9 else 1.0)
    pct = xyz / total * 100.0

    channels: dict[str, np.ndarray] = {}
    for key, series in (("pct", pct), ("xyz", xyz), ("rpy", rpy)):
        channels[key] = series
        channels[f"{key}_d"] = _gradient(series, t)
        channels[f"{key}_dd"] = _gradient(channels[f"{key}_d"], t)
    for index, (label, direction) in enumerate(vec_dirs):
        del label
        vec = np.concatenate([[0.0], np.cumsum(steps @ direction)])
        channels[f"vec{index}"] = vec
        channels[f"vec{index}_d"] = _gradient(vec, t)
        channels[f"vec{index}_dd"] = _gradient(channels[f"vec{index}_d"], t)
    return channels


def _encode_robot(robot: RobotDisplay) -> dict[str, Any]:
    """Embedded link meshes: base64 little-endian float32 triangle soups."""

    links = []
    colors = robot.link_colors or [None] * len(robot.link_names)
    opacities = robot.link_opacities or [0.55] * len(robot.link_names)
    for name, mesh, color, opacity in zip(
        robot.link_names, robot.link_meshes, colors, opacities, strict=True
    ):
        buffer = np.ascontiguousarray(mesh.astype("<f4")).tobytes()
        links.append(
            {
                "name": name,
                "tris": base64.b64encode(buffer).decode("ascii"),
                "color": color,
                "opacity": opacity,
            }
        )
    return {"name": robot.name, "links": links}


class _RobotRegistry:
    """Encode each distinct model once; situations reference it by index.

    Sim and real normally share one model and differ only in color, so the
    meshes must not be embedded per situation — but a situation is free to
    carry its own model, which is how two different rigs get compared.
    """

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self._models: list[RobotDisplay] = []

    def index_of(self, robot: RobotDisplay) -> int:
        for index, known in enumerate(self._models):
            if known is robot:
                return index
        self._models.append(robot)
        self.payloads.append(_encode_robot(robot))
        return len(self._models) - 1


def _robot_track(robot: RobotDisplay, situation: Situation) -> dict[str, Any]:
    """World pose of every robot link at each of the situation's samples."""

    sample_count = situation.q.shape[0]
    if sample_count > MAX_ROBOT_TRACK_POINTS:
        indices = np.linspace(
            0,
            sample_count - 1,
            MAX_ROBOT_TRACK_POINTS,
            dtype=int,
        )
    else:
        indices = np.arange(sample_count)
    sampled_q = situation.q[indices]
    sampled_t = situation.t[indices]
    poses = np.asarray(robot.link_fk(sampled_q), dtype=float)
    expected = (len(indices), len(robot.link_names), 4, 4)
    if poses.shape != expected:
        raise ValueError(f"link_fk returned {poses.shape}, expected {expected}")
    flat = poses.reshape(-1, 4, 4)
    quats = mat_to_quat(flat[:, :3, :3]).reshape(poses.shape[0], poses.shape[1], 4)
    return {
        "t": _clean(sampled_t),
        "p": _clean(poses[:, :, :3, 3], decimals=5),
        "quat": _clean(quats, decimals=5),
    }


def _choose_plot_grid(ordered: list[tuple[Situation, str]]) -> np.ndarray | None:
    """Shared display grid: the target's grid when present, else the first run's."""

    for situation, role in ordered:
        if role == "target" and situation.has_data:
            base = situation.t
            break
    else:
        with_data = [situation.t for situation, _ in ordered if situation.has_data]
        if not with_data:
            return None
        base = with_data[0]
    stride = max(1, int(np.ceil(len(base) / MAX_PLOT_POINTS)))
    grid = base[::stride]
    if grid[-1] != base[-1]:
        grid = np.concatenate([grid, base[-1:]])
    return grid


def _onto_plot_grid(t_native: np.ndarray, series: np.ndarray, plot_t: np.ndarray) -> np.ndarray:
    """Resample one channel onto the display grid, NaN outside the native span."""

    return np.interp(plot_t, t_native, series, left=np.nan, right=np.nan)


def _finite_rms(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return float("nan")
    return float(np.sqrt(np.mean(finite**2)))


def _format_degrees(value_rad: float) -> str:
    if not np.isfinite(value_rad):
        return "—"
    return f"{np.degrees(value_rad):,.3f}°"


def _format_millimetres(value_m: float) -> str:
    if not np.isfinite(value_m):
        return "—"
    return f"{value_m * 1000.0:,.3f} mm"


def _automatic_statistics(
    comparison: Comparison,
    metrics: dict[str, dict[str, Any]],
) -> ReportTable:
    rows: list[TableRow] = []
    for situation in comparison.situations:
        metric = metrics[situation.name]
        status = metric["status"]
        tone = ""
        if not situation.has_data:
            tone = "muted"
        elif situation.meta.get("aborted"):
            tone = "danger"
            reason = situation.meta.get("abort_reason")
            status = "aborted" + (f" — {reason}" if reason else "")

        worst = "—"
        worst_index = metric.get("worst_joint")
        if worst_index is not None:
            worst = (
                f"{comparison.joint_names[worst_index]} "
                f"({_format_degrees(metric['joint_rms'][worst_index])})"
            )
        rows.append(
            TableRow(
                cells=[
                    situation.title,
                    _format_degrees(metric.get("mean_joint_rms", float("nan"))),
                    worst,
                    _format_millimetres(metric.get("position_rms", float("nan"))),
                    _format_degrees(metric.get("rotation_rms", float("nan"))),
                    status,
                ],
                tone=tone,
            )
        )
    return ReportTable(
        title="Error statistics vs target",
        description=(
            "RMS values use each run's native samples. Angles are shown in degrees "
            "and positions in millimetres; raw report data remains SI."
        ),
        columns=[
            "Situation",
            "Mean joint RMS",
            "Worst joint",
            "TCP pos RMS",
            "TCP rot RMS",
            "Samples / status",
        ],
        rows=rows,
    )


def analyze_comparison(comparison: Comparison) -> dict[str, Any]:
    """Compute the full channel payload for one comparison page."""

    target = comparison.target
    target_poses = _situation_poses(target, comparison) if target and target.has_data else None
    target_rpy_start: np.ndarray | None = None
    pct_total: float | None = None
    if target_poses is not None:
        target_steps = np.diff(target_poses[:, :3, 3], axis=0)
        pct_total = float(np.sum(np.linalg.norm(target_steps, axis=1)))

    ordered: list[tuple[Situation, str]] = []
    if target is not None:
        ordered.append((target, "target"))
    ordered.extend((situation, "situation") for situation in comparison.situations)

    plot_t = _choose_plot_grid(ordered)
    payload_situations: list[dict[str, Any]] = []
    registry = _RobotRegistry()
    automatic_metrics: dict[str, dict[str, Any]] = {}
    any_cartesian = False
    any_tau = False
    any_current = False

    for situation, role in ordered:
        entry: dict[str, Any] = {
            "name": situation.name,
            "title": situation.title,
            "role": role,
            "has_data": situation.has_data,
            "note": situation.note,
            "derived": [],
            "video": situation.video or None,
            "group": situation.group,
            "group_title": situation.group_title,
            "meta": _json_clean(situation.meta),
            "plot": None,
            "three": None,
            "robot_track": None,
        }
        payload_situations.append(entry)
        if role != "target":
            automatic_metrics[situation.name] = {
                "status": (
                    f"{len(situation.t):,} samples"
                    if situation.has_data
                    else situation.note or "no data"
                ),
                "joint_rms": None,
                "worst_joint": None,
                "mean_joint_rms": float("nan"),
                "position_rms": float("nan"),
                "rotation_rms": float("nan"),
            }
        if not situation.has_data or plot_t is None:
            continue
        robot = situation.robot or comparison.robot
        if robot is not None:
            entry["robot_track"] = dict(
                _robot_track(robot, situation), robot=registry.index_of(robot)
            )

        t = situation.t
        qd = situation.qd
        if qd is None:
            qd = _gradient(situation.q, t)
            entry["derived"].append("qd")
        qdd = situation.qdd
        if qdd is None:
            qdd = _gradient(qd, t)
            entry["derived"].append("qdd")

        def on_grid(series: np.ndarray, t_native: np.ndarray = t) -> np.ndarray:
            return _onto_plot_grid(t_native, series, plot_t)

        plot: dict[str, Any] = {
            "q": [_clean(on_grid(situation.q[:, col])) for col in range(situation.q.shape[1])],
            "qd": [_clean(on_grid(qd[:, col])) for col in range(qd.shape[1])],
            "qdd": [_clean(on_grid(qdd[:, col])) for col in range(qdd.shape[1])],
            "tau": None,
            "current": None,
        }
        if situation.tau is not None:
            any_tau = True
            plot["tau"] = [
                _clean(on_grid(situation.tau[:, col])) for col in range(situation.tau.shape[1])
            ]

        if situation.current is not None:
            any_current = True
            plot["current"] = [
                _clean(on_grid(situation.current[:, col]))
                for col in range(situation.current.shape[1])
            ]

        poses = target_poses if role == "target" else _situation_poses(situation, comparison)
        if poses is not None:
            any_cartesian = True
            rpy = unwrap_rpy(mat_to_rpy(poses[:, :3, :3]))
            if role == "target":
                target_rpy_start = rpy[0]
            elif target_rpy_start is not None:
                rpy = align_unwrapped(rpy, target_rpy_start)
            path = _path_channels(poses, t, comparison.vec_dirs, pct_total)
            plot.update(
                {
                    "x": _clean(on_grid(poses[:, 0, 3])),
                    "y": _clean(on_grid(poses[:, 1, 3])),
                    "z": _clean(on_grid(poses[:, 2, 3])),
                    "rx": _clean(on_grid(rpy[:, 0])),
                    "ry": _clean(on_grid(rpy[:, 1])),
                    "rz": _clean(on_grid(rpy[:, 2])),
                }
            )
            plot.update({key: _clean(on_grid(series)) for key, series in path.items()})
            entry["three"] = {
                "t": _clean(t),
                "p": _clean(poses[:, :3, 3], decimals=5),
                "quat": _clean(mat_to_quat(poses[:, :3, :3]), decimals=5),
                "tp": None,
                "tquat": None,
            }

        if role != "target" and target is not None and target.has_data:
            q_target, poses_target = _target_on_grid(comparison, target, target_poses, t)
            joint_error = situation.q - q_target
            joint_rms = np.asarray(
                [_finite_rms(joint_error[:, col]) for col in range(joint_error.shape[1])]
            )
            finite_joint_rms = np.isfinite(joint_rms)
            automatic_metrics[situation.name].update(
                {
                    "joint_rms": joint_rms,
                    "worst_joint": (
                        int(np.nanargmax(joint_rms)) if finite_joint_rms.any() else None
                    ),
                    "mean_joint_rms": (
                        float(np.mean(joint_rms[finite_joint_rms]))
                        if finite_joint_rms.any()
                        else float("nan")
                    ),
                }
            )
            plot["err_q"] = [
                _clean(on_grid(joint_error[:, col])) for col in range(joint_error.shape[1])
            ]
            if poses is not None and poses_target is not None:
                position_error = np.linalg.norm(
                    poses[:, :3, 3] - poses_target[:, :3, 3], axis=1
                )
                rotation_error = rotation_angles_between(
                    poses[:, :3, :3], poses_target[:, :3, :3]
                )
                automatic_metrics[situation.name].update(
                    {
                        "position_rms": _finite_rms(position_error),
                        "rotation_rms": _finite_rms(rotation_error),
                    }
                )
                plot["xyz_mag"] = _clean(on_grid(position_error))
                plot["rot_mag"] = _clean(on_grid(rotation_error))
                entry["three"]["tp"] = _clean(poses_target[:, :3, 3], decimals=5)
                entry["three"]["tquat"] = _clean(mat_to_quat(poses_target[:, :3, :3]), decimals=5)

        entry["plot"] = plot

    statistics = comparison.statistics or _automatic_statistics(comparison, automatic_metrics)
    return {
        "name": comparison.name,
        "title": comparison.title,
        "group": comparison.group,
        "group_title": comparison.group_title,
        "tab_title": comparison.tab_title,
        "description": comparison.description,
        "meta": _json_clean(comparison.meta),
        "joint_names": list(comparison.joint_names),
        "vec_labels": [label for label, _ in comparison.vec_dirs],
        "pct_reference": "target" if pct_total else "self",
        "has_cartesian": any_cartesian,
        "has_tau": any_tau,
        "has_current": any_current,
        "has_video": any(entry["video"] for entry in payload_situations),
        "overlays": [overlay.to_payload() for overlay in comparison.overlays],
        "has_overlay": bool(comparison.overlays),
        "default_sections": (
            list(comparison.default_sections)
            if comparison.default_sections is not None
            else None
        ),
        "plot_t": _clean(plot_t) if plot_t is not None else None,
        "robots": registry.payloads,
        "situations": payload_situations,
        "statistics": statistics.to_payload(),
    }
