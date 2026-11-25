"""Derive every comparison channel from raw situation recordings.

Per situation, computed on that situation's own time grid:

- joint space: ``q``, ``qd``, ``qdd``, ``tau``, ``current`` (velocity/
  acceleration fall back to ``np.gradient`` when not recorded; ``tau`` and
  ``current`` stay absent if absent — a missing channel is never invented);
- every other recorded signal (``Situation.channels``) as ``entry["channels"][name]``, one display column per
  channel column, named by ``Comparison.signals`` (``payload["channels"]``: title, unit, column labels, section);
  an undescribed channel keeps its own name, no unit and columns ``0``, ``1``, ... (docs/NAVIGATION.md C1);
- the torque breakdown: ``tau_cmd`` (commanded, to the FOC current loop), ``tau_ff``
  (feedforward) and ``tau_fb`` (feedback). Two of the three derive the third (``tau_cmd =
  tau_ff + tau_fb``, listed in ``entry["derived"]``); all three given are kept as given (a drive
  clamp can break the sum); one alone derives nothing. A measured run with a breakdown gets
  ``entry["torque_budget"]`` per joint;
- TCP pose: ``x, y, z`` and unwrapped extrinsic-xyz ``rx, ry, rz``;
- path progress and its two derivatives for four channel families:
  ``pct`` (percent of the reference path length completed — the end-effector
  progress/speed view), ``xyz`` (cumulative translational arc length),
  ``rpy`` (cumulative rotation, accumulated axis-angle), and one signed
  ``vec`` channel per configured direction (displacement projected onto the
  direction — point it along the conveyor to read belt-matching speed);
- error channels against the target, all from ``robot_msgs.compare`` (one
  source of truth for every error signal and statistic): per-joint ``q``
  error, ``xyz_mag`` (translation error norm), ``rot_mag`` (geodesic rotation
  error), per-axis ``err_x .. err_rz``, ``cross_track``, ``lag``, the exact
  ``contour`` / ``lag_time`` split, and (``Comparison.error_axes``) the position
  error projected on named axes. Every error is **target - run** (the ROS 2 controller-state convention), taken on
  the run's own samples inside the target's span; the target is interpolated,
  never extrapolated.

Optional, off unless the ``Comparison`` asks (all from ``robot_msgs.compare``): a verdict per
run (``check``), a latency estimate (``estimate_time_offset``), goal / settling statistics
(``goal``) and ISO 9283 accuracy vs repeatability over repeated runs (``aggregate``).

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
import dataclasses
import math
from typing import Any

import numpy as np
from robot_msgs.compare import (
    aggregate,
    align,
    check,
    compare,
    error_stats,
    estimate_time_offset,
    goal,
)
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from .model import Comparison, ReportTable, RobotDisplay, Signal, Situation, TableRow
from .rotations import (
    align_unwrapped,
    mat_to_quat,
    mat_to_rpy,
    successive_rotation_angles,
    unwrap_rpy,
)
from .tabs import channel_slug, normalize_parts, tabs_for

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


def _inside_span(t_from: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """Which of ``t_to`` lie in ``[t_from[0], t_from[-1]]``, both ends included."""

    return (t_to >= t_from[0]) & (t_to <= t_from[-1])


# WHY these resamplers stay although analyze_comparison no longer calls them (2026-11-10): the error
# signals now come from robot_msgs.compare, whose own interpolation is the documented rule; these are
# the adapters tests/test_difference_fixture.py drives against data-ui's difference(a, b) oracle.
def _resample_columns(t_from: np.ndarray, values: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    # WHY NaN outside the span, not np.interp's held end values: difference(a, b) never extrapolates
    # (data-ui gallery/robotics CONTRACT section 5; tests/fixtures/data_ui_difference), so a row past
    # the target's end is a null (no row), not an error measured against a frozen last sample.
    resampled = np.stack(
        [np.interp(t_to, t_from, values[:, col]) for col in range(values.shape[1])], axis=1
    )
    resampled[~_inside_span(t_from, t_to)] = np.nan
    return resampled


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
    slerped = blended / np.linalg.norm(blended, axis=1, keepdims=True)
    slerped[~_inside_span(t_from, t_to)] = np.nan  # never extrapolates, as _resample_columns
    return slerped


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


def _joint_trajectory(
    situation: Situation, joint_names: list[str], effort: np.ndarray | None = None
) -> JointTrajectory:
    """The situation as a robot_msgs trajectory; only the channels it recorded are passed.

    ``effort`` replaces the applied ``tau``: the commanded torque, so ``compare`` scores
    target − commanded.
    """

    return JointTrajectory(
        t=situation.t,
        joint_names=joint_names,
        positions=situation.q,
        velocities=situation.qd,
        accelerations=situation.qdd,
        effort=situation.tau if effort is None else effort,
    )


_BREAKDOWN_KEYS = ("tau_cmd", "tau_ff", "tau_fb")


def _torque_breakdown(situation: Situation) -> tuple[dict[str, np.ndarray | None], list[str]]:
    """Commanded, feedforward and feedback torque, the missing third derived from the other two.

    WHY derive only from two (Zach 2026-11-19, torque breakdown; CONTRACT.md): ``tau_cmd =
    tau_ff + tau_fb`` is the controller's own identity, so two given pin the third. All three
    given are kept as given (a drive clamp makes the sum differ, and the page must not hide
    that); one alone derives nothing, so nothing is invented. Returns the three (None when
    absent) and the names of the derived ones.
    """

    command, feedforward, feedback = situation.tau_cmd, situation.tau_ff, situation.tau_fb
    derived: list[str] = []
    if command is None and feedforward is not None and feedback is not None:
        command = feedforward + feedback
        derived.append("tau_cmd")
    elif feedback is None and command is not None and feedforward is not None:
        feedback = command - feedforward
        derived.append("tau_fb")
    elif feedforward is None and command is not None and feedback is not None:
        feedforward = command - feedback
        derived.append("tau_ff")
    return {"tau_cmd": command, "tau_ff": feedforward, "tau_fb": feedback}, derived


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _torque_budget(
    situation: Situation,
    breakdown: dict[str, np.ndarray | None],
    joint_names: list[str],
    target_joints: JointTrajectory | None,
) -> dict[str, dict[str, float | None]]:
    """Per joint: each torque's size, the feedback's share of the command, and the two gaps.

    Every statistic is ``robot_msgs.compare``'s ``error_stats`` on the run's own samples;
    target − commanded is ``compare`` itself (effort = the commanded torque), so the target is
    lined up exactly as for every other error: ``time_offset_s`` honoured, never extrapolated.
    """

    t = situation.t
    command, feedforward, feedback = (breakdown[key] for key in _BREAKDOWN_KEYS)
    applied = situation.tau

    def stat(series: np.ndarray | None, column: int, field: str) -> float | None:
        if series is None:
            return None
        return _finite_or_none(getattr(error_stats(series[:, column], t), field))

    target_minus_command = None
    if command is not None and target_joints is not None and target_joints.effort is not None:
        command_joints = _joint_trajectory(situation, joint_names, effort=command)
        result = _compare_or_none(target_joints, command_joints, situation.time_offset_s)
        if result is not None:
            target_minus_command = result.metrics

    budget: dict[str, dict[str, float | None]] = {}
    for column, joint in enumerate(joint_names):
        fb_share = None
        if feedforward is not None and feedback is not None:
            ff_column, fb_column = feedforward[:, column], feedback[:, column]
            both = np.isfinite(ff_column) & np.isfinite(fb_column)
            # a plain sum, not an error statistic: the share of |command| the feedback had to supply
            fb_sum = float(np.sum(np.abs(fb_column[both])))
            total = float(np.sum(np.abs(ff_column[both]))) + fb_sum
            fb_share = fb_sum / total if total > 0.0 else None
        gap = None
        if target_minus_command is not None and f"effort/{joint}" in target_minus_command:
            gap = _finite_or_none(target_minus_command[f"effort/{joint}"].rms)
        drive_gap = None
        if command is not None and applied is not None:
            drive_gap = _finite_or_none(error_stats(command[:, column] - applied[:, column], t).rms)
        budget[joint] = {
            "cmd_rms": stat(command, column, "rms"),
            "ff_rms": stat(feedforward, column, "rms"),
            "fb_rms": stat(feedback, column, "rms"),
            "applied_rms": stat(applied, column, "rms"),
            "cmd_peak": stat(command, column, "max_abs"),
            "fb_share": fb_share,
            "target_minus_cmd_rms": gap,
            "cmd_minus_applied_rms": drive_gap,
        }
    return budget


def _pose_trajectory(situation: Situation, poses: np.ndarray, frame: str) -> PoseTrajectory:
    return PoseTrajectory.from_matrices(situation.t, poses, child_frame_id=frame)


def _mask_on(comparison: Comparison, t: np.ndarray) -> np.ndarray:
    """``comparison.stats_mask`` (one bool per reference sample) at each instant of an error series: its nearest
    reference sample's value."""

    reference_t = np.asarray(comparison.target.t, dtype=float)
    mask = np.asarray(comparison.stats_mask, dtype=bool)
    after = np.clip(np.searchsorted(reference_t, t), 1, len(reference_t) - 1)
    nearer_before = np.abs(t - reference_t[after - 1]) <= np.abs(reference_t[after] - t)
    return mask[np.where(nearer_before, after - 1, after)]


def _result_metrics(comparison: Comparison, result: Any) -> dict[str, Any]:
    """robot_msgs.compare's metrics of one comparison result, as dicts: over every sample, or with
    ``comparison.stats_mask`` over the masked samples only (the others NaN, which ``error_stats`` skips).

    WHY (TTA ask, 2026-11-24): its ruler takes the tool tracking RMS over the samples where the target moves; over every
    sample the report's RMS also averaged the rests, up to 0.067 mm off. The math stays robot_msgs.compare's own
    (``joint_metrics`` / ``pose_metrics`` on the same error, masked)."""

    if comparison.stats_mask is None:
        return {name: value.as_dict() for name, value in result.metrics.items()}
    from robot_msgs.compare.metrics import joint_metrics, pose_metrics
    from robot_msgs.trajectory.trajectory import sample_fields

    error = result.error
    keep = _mask_on(comparison, np.asarray(error.t, dtype=float))

    def blank(values: Any) -> Any:
        array = np.array(values, dtype=float, copy=True)
        array[~keep] = np.nan
        return array

    changes = {f.name: blank(getattr(error, f.name)) for f in sample_fields(type(error))
               if getattr(error, f.name) is not None and f.name != "orientations"}  # fmt: skip
    changes["channels"] = {name: blank(values) for name, values in error.channels.items()}
    masked = dataclasses.replace(error, **changes)
    metrics = joint_metrics(masked) if isinstance(masked, JointTrajectory) else pose_metrics(masked)
    return {name: value.as_dict() for name, value in metrics.items()}


def _compare_or_none(reference: Any, measured: Any, time_offset_s: float = 0.0) -> Any:
    """``compare(reference, measured, time_offset_s)``, or None when the run never meets the target's span.

    WHY None, not a raise: a run entirely outside the target's span is a legitimate report
    page (its error is simply absent), not a failure of the whole report.
    """

    try:
        return compare(reference, measured, time_offset_s=time_offset_s)
    except ValueError as error:
        if "no overlap" not in str(error):
            raise
        return None


def _or_none(function: Any, *args: Any, **kwargs: Any) -> Any:
    """``function(...)``, or None when the run never meets the reference's span.

    WHY None, not a raise: same rule as ``_compare_or_none``; the page just lacks that number.
    """

    try:
        return function(*args, **kwargs)
    except ValueError as error:
        if "overlap" not in str(error):
            raise
        return None


def _message_dict(message: Any) -> dict[str, Any]:
    return {field.name: getattr(message, field.name) for field in dataclasses.fields(message)}


def _outcome_payload(outcome: Any) -> dict[str, Any]:
    return _json_clean(
        {
            "error_code": outcome.error_code,
            "code_name": outcome.code_name,
            "error_string": outcome.error_string,
            "violations": [
                {
                    "phase": violation.phase,
                    "metric": violation.metric,
                    "t": violation.t,
                    "error": violation.error,
                    "limit": violation.limit,
                }
                for violation in outcome.violations
            ],
            "margins": dict(outcome.margins),
            "goal_time": outcome.goal_time,
            "unchecked": list(outcome.unchecked),
        }
    )


def _stats_payload(stats: dict[str, Any]) -> dict[str, Any]:
    return _json_clean({name: _message_dict(value) for name, value in stats.items()})


def _aggregate_payload(result: Any) -> dict[str, Any]:
    return _json_clean(
        {
            "accuracy": {name: value.as_dict() for name, value in result.accuracy.metrics.items()},
            "repeatability": {name: value.as_dict() for name, value in result.metrics.items()},
            "coverage": result.coverage,
        }
    )


def _decimals(value: float, digits: int = 3) -> int:
    """``digits``, or as many more decimals as keep two significant figures. WHY (TTA ask, 2026-11-24): fixed decimals
    printed a 0.0004° error as "0.000°"; every value of 0.01 and up prints exactly as before."""
    magnitude = abs(float(value))
    if magnitude == 0.0 or not math.isfinite(magnitude):
        return digits
    return min(12, max(digits, 1 - math.floor(math.log10(magnitude))))


def _format_degrees(value_rad: float) -> str:
    if not np.isfinite(value_rad):
        return "—"
    degrees = float(np.degrees(value_rad))
    return f"{degrees:,.{_decimals(degrees)}f}°"


def _format_millimetres(value_m: float) -> str:
    if not np.isfinite(value_m):
        return "—"
    millimetres = value_m * 1000.0
    return f"{millimetres:,.{_decimals(millimetres)}f} mm"


def reference_title(comparison: Comparison) -> str:
    """What the viewer calls the minuend of every error.

    WHY the target's own title: sim vs real has no target; whichever run sits in ``target`` is the
    reference, and the report names it instead of saying "target".
    """

    return comparison.target.title if comparison.target is not None else "Target"


def _verdict_cells(comparison: Comparison, metric: dict[str, Any]) -> list[str]:
    codes = metric.get("verdict", {})
    return [codes.get(key, "—") for key in ("joint", "tcp") if _has_verdict(comparison, key)]


def _has_verdict(comparison: Comparison, key: str) -> bool:
    return (comparison.tolerances if key == "joint" else comparison.tcp_tolerances) is not None


def _latency_cell(metric: dict[str, Any]) -> str:
    latency = metric.get("latency")
    if not latency or latency.get("offset_s") is None:
        return "—"
    after = latency["rms_after"] if latency["rms_after"] is not None else float("nan")
    before = latency["rms_before"] if latency["rms_before"] is not None else float("nan")
    return (
        f"{latency['offset_s'] * 1000.0:,.1f} ms · RMS {_format_degrees(after)} "
        f"(was {_format_degrees(before)})"
    )


def _settling_cell(metric: dict[str, Any]) -> str:
    """TCP settling · overshoot when the TCP has a band, else the slowest-settling joint's."""

    stats = metric.get("goal") or {}

    def settle(entry: dict[str, Any]) -> str:
        seconds = entry.get("settling_time")
        return "not settled" if seconds is None else f"{seconds * 1000.0:,.0f} ms"

    tcp = (stats.get("tcp") or {}).get("position")
    if tcp:
        over = tcp.get("overshoot")
        return f"{settle(tcp)} · over {_format_millimetres(over if over is not None else float('nan'))}"
    joints = stats.get("joint") or {}
    if not joints:
        return "—"
    # a joint that never settled is the worst; otherwise the slowest
    name, worst = max(
        joints.items(),
        key=lambda item: float("inf") if item[1].get("settling_time") is None else item[1]["settling_time"],
    )
    over = worst.get("overshoot")
    return (
        f"{name.split('/', 1)[-1]}: {settle(worst)} · over "
        f"{_format_degrees(over if over is not None else float('nan'))}"
    )


def _automatic_statistics(
    comparison: Comparison,
    metrics: dict[str, dict[str, Any]],
) -> ReportTable:
    rows: list[TableRow] = []
    has_goal = comparison.goal_band is not None or comparison.tcp_goal_band is not None
    verdict_columns = {
        (True, False): ["Verdict"],
        (False, True): ["Verdict (TCP)"],
        (True, True): ["Verdict (joints)", "Verdict (TCP)"],
    }.get((_has_verdict(comparison, "joint"), _has_verdict(comparison, "tcp")), [])
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

        stats = metric.get("stats", {})

        def pair(kind: str, formatter: Any, stats: dict = stats) -> str:
            summary = stats.get(kind)
            if not summary:
                return "—"
            return f"{formatter(summary['max_abs'])} · {formatter(summary['final'])}"

        track = "—"
        if stats.get("cross_track") and stats.get("lag"):
            track = (
                f"{_format_millimetres(stats['cross_track']['rms'])} · "
                f"{_format_millimetres(stats['lag']['rms'])}"
            )

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
                    pair("position", _format_millimetres),
                    pair("rotation", _format_degrees),
                    track,
                    *_verdict_cells(comparison, metric),
                    *([_latency_cell(metric)] if comparison.estimate_latency else []),
                    *([_settling_cell(metric)] if has_goal else []),
                    status,
                ],
                tone=tone,
            )
        )
    notes = ""
    if verdict_columns:
        notes += (
            " Verdict is robot_msgs.compare.check against the declared tolerances (ROS 2 "
            "joint_trajectory_controller: path while the reference runs, goal after it ends)."
        )
    if comparison.estimate_latency:
        notes += (
            " Est. latency is how late the run's clock runs (estimate_time_offset), with the joint "
            "RMS error once shifted by it."
        )
    if has_goal:
        notes += (
            " Settling is the time after the reference ends to stay inside the goal band, "
            "with the overshoot past the final value."
        )
    return ReportTable(
        title="Error statistics vs target",
        description=(
            f"Cartesian errors are of the {comparison.tcp_frame} frame. "
            "RMS values use each run's native samples. Final is the error at the "
            f"run's last sample inside the target's span. Errors are {reference_title(comparison)} − run. "
            "Cross-track is distance off the target's direction of travel; lag is "
            "signed along it, + when the run is behind the target. Angles are shown "
            "in degrees and positions in millimetres; raw report data remains SI."
            + notes
        ),
        columns=[
            "Situation",
            "Mean joint RMS",
            "Worst joint",
            "TCP pos RMS",
            "TCP rot RMS",
            "TCP pos max · final",
            "TCP rot max · final",
            "Cross-track · lag RMS",
            *verdict_columns,
            *(["Est. latency"] if comparison.estimate_latency else []),
            *(["Settling · overshoot"] if has_goal else []),
            "Samples / status",
        ],
        rows=rows,
    )


def _second_wave(
    comparison: Comparison,
    entry: dict[str, Any],
    metric: dict[str, Any],
    target_joints: JointTrajectory,
    run_joints: JointTrajectory,
    target_pose_track: PoseTrajectory | None,
    run_pose_track: PoseTrajectory | None,
    time_offset_s: float = 0.0,
) -> None:
    """The optional verdict / latency / goal blocks of one run, each from one robot_msgs.compare call."""

    has_pose = target_pose_track is not None and run_pose_track is not None
    if comparison.tolerances is not None or (comparison.tcp_tolerances is not None and has_pose):
        verdict: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        for key, tolerances, reference, run in (
            ("joint", comparison.tolerances, target_joints, run_joints),
            ("tcp", comparison.tcp_tolerances, target_pose_track, run_pose_track),
        ):
            if tolerances is None or reference is None or run is None:
                continue
            outcome = _or_none(check, reference, run, tolerances, time_offset_s=time_offset_s)
            if outcome is not None:
                raw[key] = outcome
                verdict[key] = _outcome_payload(outcome)
        if verdict:
            entry["verdict"] = verdict
            metric["verdict"] = {key: outcome.code_name for key, outcome in raw.items()}

    if comparison.estimate_latency:
        estimate = _or_none(estimate_time_offset, target_joints, run_joints)
        if estimate is not None:
            entry["latency"] = _json_clean(_message_dict(estimate))
            metric["latency"] = entry["latency"]

    if comparison.goal_band is not None or comparison.tcp_goal_band is not None:
        stats: dict[str, Any] = {}
        if comparison.goal_band is not None:
            joint_goal = _or_none(
                goal, target_joints, run_joints, band=comparison.goal_band, time_offset_s=time_offset_s
            )
            if joint_goal is not None:
                stats["joint"] = _stats_payload(joint_goal)
        if comparison.tcp_goal_band is not None and has_pose:
            tcp_goal = _or_none(
                goal, target_pose_track, run_pose_track,
                band=comparison.tcp_goal_band, time_offset_s=time_offset_s,
            )
            if tcp_goal is not None:
                stats["tcp"] = _stats_payload(tcp_goal)
        if stats:
            entry["goal"] = stats
            metric["goal"] = stats


def _aggregates(
    comparison: Comparison,
    target_joints: JointTrajectory | None,
    target_pose_track: PoseTrajectory | None,
) -> dict[str, Any]:
    """ISO 9283 accuracy vs repeatability per repeat group, against the reference."""

    out: dict[str, Any] = {}
    if target_joints is None:
        return out
    by_name = {situation.name: situation for situation in comparison.situations}
    for group, names in comparison.repeat_groups.items():
        runs = [by_name[name] for name in names if by_name[name].has_data]
        if len(runs) < 2:
            continue
        block: dict[str, Any] = {
            "runs": [run.name for run in runs],
            "titles": [run.title for run in runs],
        }
        offsets = [run.time_offset_s for run in runs]
        joint = _or_none(
            aggregate,
            target_joints,
            [_joint_trajectory(run, comparison.joint_names) for run in runs],
            time_offset_s=offsets,
        )
        if joint is not None:
            block["joint"] = _aggregate_payload(joint)
        run_poses = [_situation_poses(run, comparison) for run in runs]
        if target_pose_track is not None and all(poses is not None for poses in run_poses):
            tcp = _or_none(
                aggregate,
                target_pose_track,
                [
                    _pose_trajectory(run, poses, comparison.tcp_frame)
                    for run, poses in zip(runs, run_poses, strict=True)
                ],
                time_offset_s=offsets,
            )
            if tcp is not None:
                block["tcp"] = _aggregate_payload(tcp)
        if "joint" in block or "tcp" in block:
            out[group] = block
    return out


def _channel_descriptors(comparison: Comparison, ordered: list[tuple[Situation, str]]) -> list[dict[str, Any]]:
    """One entry per channel any situation (the target included) recorded: how both viewers name and lay it out.

    ``{"name", "section", "title", "unit", "ndim", "columns", "per_joint", "described"}``, the described channels in
    ``Comparison.signals`` order, then the rest in the order they first appear. ``section`` is ``channel-<slug>``
    (``tabs.channel_slug``), suffixed ``-2``, ``-3`` when two names slug alike, so neither is lost.

    WHY an undescribed channel is drawn anyway (NAVIGATION.md C1, truthful rendering): a recorded signal is never
    dropped or renamed — title = its name, no unit, columns ``0``, ``1``, ... (robot_msgs' own column indices).
    """

    shapes: dict[str, np.ndarray] = {}
    for situation, _ in ordered:
        for name, values in situation.channels.items():
            shapes.setdefault(name, values)  # Comparison keeps one shape per channel
    names = [name for name in comparison.signals if name in shapes] + [
        name for name in shapes if name not in comparison.signals
    ]
    taken: set[str] = set()
    descriptors = []
    for name in names:
        values = shapes[name]
        signal = comparison.signals.get(name) or Signal()
        if values.ndim == 1:
            columns: list[str] = []
        elif signal.per_joint:
            columns = list(comparison.joint_names)
        elif signal.columns:
            columns = list(signal.columns)
        else:
            columns = [str(index) for index in range(values.shape[1])]
        section = base = f"channel-{channel_slug(name)}"
        count = 1
        while section in taken:
            count += 1
            section = f"{base}-{count}"
        taken.add(section)
        descriptors.append({
            "name": name,
            "section": section,
            "title": signal.title or name,
            "unit": signal.unit,
            "ndim": int(values.ndim),
            "columns": columns,
            "per_joint": signal.per_joint,
            "described": name in comparison.signals,
        })  # fmt: skip
    return descriptors


def analyze_comparison(comparison: Comparison) -> dict[str, Any]:
    """Compute the full channel payload for one comparison page."""

    target = comparison.target
    target_poses = _situation_poses(target, comparison) if target and target.has_data else None
    target_rpy_start: np.ndarray | None = None
    pct_total: float | None = None
    if target_poses is not None:
        target_steps = np.diff(target_poses[:, :3, 3], axis=0)
        pct_total = float(np.sum(np.linalg.norm(target_steps, axis=1)))

    target_joints = (
        _joint_trajectory(target, comparison.joint_names) if target and target.has_data else None
    )
    target_pose_track = (
        _pose_trajectory(target, target_poses, comparison.tcp_frame)
        if target_poses is not None
        else None
    )

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
    any_breakdown = False

    for situation, role in ordered:
        entry: dict[str, Any] = {
            "name": situation.name,
            "title": situation.title,
            "role": role,
            "time_offset_s": situation.time_offset_s,
            "has_data": situation.has_data,
            "note": situation.note,
            "derived": [],
            "video": situation.video or None,
            "video_start_s": situation.video_start_s,
            "group": situation.group,
            "group_title": situation.group_title,
            "meta": _json_clean(situation.meta),
            "plot": None,
            "three": None,
            "robot_track": None,
            "error_metrics": None,
            "torque_budget": None,
            # name -> display columns on plot_t (beside ``plot``, whose keys are the fixed joint / tool series)
            "channels": None,
        }
        payload_situations.append(entry)
        if role != "target":
            automatic_metrics[situation.name] = {
                "status": (
                    f"{len(situation.t):,} samples"
                    + (
                        f" · shifted {situation.time_offset_s * 1000.0:,.1f} ms"
                        if situation.time_offset_s
                        else ""
                    )
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
            **{key: None for key in _BREAKDOWN_KEYS},
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

        if situation.channels:
            # one column per channel column (a 1-D channel is one), on the display grid like every other trace
            entry["channels"] = {
                name: [_clean(on_grid(column)) for column in values.reshape(len(t), -1).T]
                for name, values in situation.channels.items()
            }

        breakdown, derived_torques = _torque_breakdown(situation)
        entry["derived"].extend(derived_torques)
        for key, series in breakdown.items():
            if series is not None:
                any_breakdown = True
                plot[key] = [_clean(on_grid(series[:, col])) for col in range(series.shape[1])]
        if role != "target" and any(series is not None for series in breakdown.values()):
            entry["torque_budget"] = _json_clean(
                _torque_budget(situation, breakdown, comparison.joint_names, target_joints)
            )

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

        if role != "target" and target_joints is not None:
            run_joints = _joint_trajectory(situation, comparison.joint_names)
            joint_result = _compare_or_none(target_joints, run_joints, situation.time_offset_s)
            stats: dict[str, dict[str, Any]] = {}
            if joint_result is None:
                joint_error = np.full(situation.q.shape, np.nan)
                joint_error_t = t
                alignment = {"coverage": 0.0, "dropped": len(t), "time_offset_s": 0.0}
            else:
                joint_error = joint_result.error.positions  # target - run
                joint_error_t = joint_result.error.t
                alignment = {
                    "coverage": joint_result.coverage,
                    "dropped": joint_result.dropped,
                    "time_offset_s": joint_result.time_offset_s,
                }
                stats = _result_metrics(comparison, joint_result)
            joint_rms = np.asarray(
                [
                    stats.get(f"positions/{name}", {}).get("rms", float("nan"))
                    for name in comparison.joint_names
                ]
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
                _clean(on_grid(joint_error[:, col], joint_error_t))
                for col in range(joint_error.shape[1])
            ]
            if poses is not None and target_pose_track is not None:
                run_pose_track = _pose_trajectory(situation, poses, comparison.tcp_frame)
                pose_result = _compare_or_none(
                    target_pose_track, run_pose_track, situation.time_offset_s
                )
            else:
                run_pose_track = None
                pose_result = None
            _second_wave(
                comparison, entry, automatic_metrics[situation.name],
                target_joints, run_joints, target_pose_track, run_pose_track,
                situation.time_offset_s,
            )  # fmt: skip
            if pose_result is not None:
                pose_error = pose_result.error  # target - run, a PoseTrajectory
                pose_t = pose_error.t
                position_delta = pose_error.positions
                rotation_delta = pose_error.channels["rotation_vector"]  # world axes
                stats.update(_result_metrics(comparison, pose_result))
                automatic_metrics[situation.name].update(
                    {
                        "position_rms": stats["position"]["rms"],
                        "rotation_rms": stats["rotation"]["rms"],
                    }
                )
                plot["xyz_mag"] = _clean(on_grid(np.linalg.norm(position_delta, axis=1), pose_t))
                plot["rot_mag"] = _clean(on_grid(pose_error.channels["rotation_angle"], pose_t))
                for axis, col in (("x", 0), ("y", 1), ("z", 2)):
                    plot[f"err_{axis}"] = _clean(on_grid(position_delta[:, col], pose_t))
                    plot[f"err_r{axis}"] = _clean(on_grid(rotation_delta[:, col], pose_t))
                plot["cross_track"] = _clean(on_grid(pose_error.channels["cross_track"], pose_t))
                plot["lag"] = _clean(on_grid(pose_error.channels["lag"], pose_t))
                plot["contour"] = _clean(on_grid(pose_error.channels["contour"], pose_t))
                plot["lag_time"] = _clean(on_grid(pose_error.channels["lag_time"], pose_t))
                if comparison.error_axes:
                    # the same vector as err_x / err_y / err_z, read on the named axes
                    plot["err_axes"] = [
                        _clean(on_grid(position_delta @ axis, pose_t))
                        for _, axis in comparison.error_axes
                    ]
                # The target at the run's own instants, exactly as compare() lined it up, so the
                # 3D difference arrows point at the pose the plotted error was measured against.
                target_at, _, _, _ = align(
                    target_pose_track, run_pose_track, time_offset_s=situation.time_offset_s
                )
                inside = np.searchsorted(t, pose_t)
                target_p = np.full((len(t), 3), np.nan)
                target_quat = np.full((len(t), 4), np.nan)
                target_p[inside] = target_at.positions
                xyzw = target_at.orientations
                wxyz = xyzw[:, [3, 0, 1, 2]]
                target_quat[inside] = np.where(wxyz[:, :1] < 0.0, -wxyz, wxyz)  # w >= 0
                entry["three"]["tp"] = _clean(target_p, decimals=5)
                entry["three"]["tquat"] = _clean(target_quat, decimals=5)
            automatic_metrics[situation.name]["stats"] = stats
            entry["error_metrics"] = _json_clean({**stats, **alignment})

        entry["plot"] = plot
        if role != "target" and entry["error_metrics"] is None:
            entry["error_metrics"] = {}  # measured, but nothing to measure against
    statistics = comparison.statistics or _automatic_statistics(comparison, automatic_metrics)
    aggregates = _aggregates(comparison, target_joints, target_pose_track)
    payload = {
        "name": comparison.name,
        "title": comparison.title,
        "group": comparison.group,
        "group_title": comparison.group_title,
        "tab_title": comparison.tab_title,
        "description": comparison.description,
        "meta": _json_clean(comparison.meta),
        "joint_names": list(comparison.joint_names),
        "tcp_frame": comparison.tcp_frame,
        "reference_title": reference_title(comparison),
        "reference_kind": comparison.reference_kind,
        "vec_labels": [label for label, _ in comparison.vec_dirs],
        "error_axes": [label for label, _ in comparison.error_axes or ()],
        "aggregates": aggregates,
        "pct_reference": "target" if pct_total else "self",
        "has_cartesian": any_cartesian,
        "has_tau": any_tau,
        "has_current": any_current,
        "has_torque_breakdown": any_breakdown,
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
        # WHY here (Zach 2026-11-19, traj compare view feedback: the standalone and the Rerun run viewer "should be
        # the exact same thing"): both read the parts and the already-dropped question tabs from this one payload.
        "parts": normalize_parts(comparison.joint_names, comparison.parts),
        "channels": _channel_descriptors(comparison, ordered),
    }
    payload["tabs"] = tabs_for(payload)
    if comparison.stats_mask is not None:  # what every error statistic above is taken over (the curves keep every sample)
        mask = np.asarray(comparison.stats_mask, dtype=bool)
        payload["stats_mask"] = {"label": comparison.stats_mask_label, "n": int(mask.sum()), "of": int(mask.size)}
    return payload
