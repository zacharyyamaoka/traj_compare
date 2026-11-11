"""The dataset as data-ui's trajectory tables (gallery/robotics/CONTRACT.md, version 1), so data-ui's robotics dashboards read it.

Seams (agreed 2026-11-11 with the Sim to Real agent): ``robot_msgs.compare`` is the math, traj_compare is the classic run view
(``runs/<slug>/report.html``, the drill-down) + the dataset view + this producer, data-ui only draws, sim2real is the domain.

    write_tables(runs, "out/data-ui", poses="my_arm:tcp_poses")      # runs.json, samples.json, diff_*.json, views.base, ...
    # node /home/bam/data-ui/bin/data-ui.mjs check out/data-ui/views.base

Files (CONTRACT section 2; display units declared per column, because data-ui converts nothing)::

    runs.json          one row per run; ``url`` is the classic drill-down, ``../runs/<slug>/report.html``
    samples.json       t x run x situation x device: q_deg, qd_deg_s, qdd_deg_s2, tau_nm (one device per joint)
    devices.json       one servo per joint (limits from the reference's JointLimits when it has them)
    poses.json         the TCP per situation, mm + wxyz quaternion (only with ``poses``)
    links.json         every link's world pose per situation (only with ``links``)
    diff_samples.json  difference(a, b) of samples.json: each situation against ``target``, each sim against ``real``
    diff_poses.json    difference(a, b) of poses.json, the same pairs (only with ``poses``)
    media.json         the runs' clips (only when some run has media)
    views.base         the dashboard over them, joint errors in degrees

SI stays in the dataset's own files (npz, rows.json); these tables are a display projection. Angles are written in degrees and
every human-facing view of them draws degrees (Zach's rule), a TCP error in mm.
"""

from __future__ import annotations

import importlib.resources
import json
import math
import shutil
import subprocess
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs.compare import align, compare
from robot_msgs.geometry.rotations import (
    matrix_to_pose,
    quat_conjugate,
    quat_multiply,
    quat_to_rotvec,
)
from robot_msgs.std import Header
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from .dataset import Run, _import_spec, _safe_name, _slug, _spec_import_root, _unique_slugs

CONTRACT_VERSION = 1
TARGET = "target"  # the situation name of the reference (CONTRACT section 4: the target is a situation)
FAMILIES = ("real", "sim", "target")

_DEGREES = 180.0 / math.pi
POS = ("x_mm", "y_mm", "z_mm")
QUAT = ("quat_w", "quat_x", "quat_y", "quat_z")
# difference(a, b) of samples: (column of a table, error column, scale from the library's SI error to the column's unit).
# WHY the pairs: CONTRACT section 5 names e_q_mrad (from q_deg, in mrad), e_q_mm, e_qd_*, e_tau_nm.
_ANGULAR = {"q": "q_deg", "qd": "qd_deg_s", "tau": "tau_nm"}
_LINEAR = {"q": "q_mm", "qd": "qd_mm_s", "tau": "tau_nm"}
_RUN_COLUMNS = (
    "run", "deployment", "started", "duration_s", "kind", "devices", "situations", "rate_hz", "display_hz",
    "label", "basis", "url", "note",
)  # fmt: skip

# ── rounding: the display projection ─────────────────────────────────────────
# WHY 9 decimals for what a difference reads (q, quaternions: 1e-9 deg is 2e-8 mrad) and 6 for what it writes (data-ui's own
# builders round to 6): a table is read, never recomputed from rounded numbers by this package.
_VALUE_DIGITS = 9
_OUT_DIGITS = 6


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _round(value: Any, digits: int) -> float | None:
    number = _number(value)
    return None if number is None else round(number, digits)


# ── difference(a, b): CONTRACT section 5, through robot_msgs.compare ─────────


def _column(rows: Sequence[Mapping[str, Any]], name: str) -> np.ndarray:
    return np.array([np.nan if (v := _number(row.get(name))) is None else v for row in rows], dtype=float)


def _present(rows: Sequence[Mapping[str, Any]], *names: str) -> bool:
    return any(_number(row.get(name)) is not None for row in rows for name in names)


def _groups(rows: Sequence[Mapping[str, Any]], key: tuple[str, ...]) -> dict[tuple, list[int]]:
    groups: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(tuple(row.get(name) for name in key), []).append(index)
    return groups


def _sorted_by_time(rows: Sequence[Mapping[str, Any]], indices: list[int]) -> list[int]:
    """The indices whose ``t`` is a number, in time order (a trajectory's clock rises strictly)."""
    return sorted((i for i in indices if _number(rows[i].get("t")) is not None), key=lambda i: float(rows[i]["t"]))


def _inside(t_a: np.ndarray, error_t: np.ndarray) -> np.ndarray:
    """Indices into a's samples of the rows ``compare`` kept: its error is on a's own samples inside b's span."""
    return np.searchsorted(t_a, error_t)


def _difference_samples(a_rows: Sequence[Mapping[str, Any]], b_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    b_groups = _groups(b_rows, ("run", "device"))
    out: dict[int, dict] = {}
    for key, a_all in _groups(a_rows, ("run", "device")).items():
        b_all = b_groups.get(key)
        if not b_all:
            continue  # a device or run only a has: no rows
        a_idx, b_idx = _sorted_by_time(a_rows, a_all), _sorted_by_time(b_rows, b_all)
        if not a_idx or not b_idx:
            continue
        a_part, b_part = [a_rows[i] for i in a_idx], [b_rows[i] for i in b_idx]
        families = []
        if _present((*a_part, *b_part), "q_deg", "qd_deg_s") or not _present((*a_part, *b_part), "q_mm", "qd_mm_s"):
            families.append(("angular", _ANGULAR))
        if _present((*a_part, *b_part), "q_mm", "qd_mm_s"):
            families.append(("linear", _LINEAR))
        t_a, t_b = _column(a_part, "t"), _column(b_part, "t")
        for index, (family, names) in enumerate(families):
            # SI inside the library: rad, rad/s, N·m (revolute); m, m/s (prismatic). Units convert back at the edge.
            angular = family == "angular"
            to_si = math.pi / 180.0 if angular else 1e-3
            effort = names["tau"] if index == 0 else None  # a torque belongs to the device's first family
            columns = {"q": names["q"], "qd": names["qd"]}
            trajectories = []
            for part, t in ((b_part, t_b), (a_part, t_a)):
                velocities = _column(part, columns["qd"]) * to_si
                trajectories.append(
                    JointTrajectory(
                        t=t,
                        joint_names=(str(key[1]),),
                        positions=(_column(part, columns["q"]) * to_si)[:, None],
                        velocities=velocities[:, None],
                        effort=_column(part, effort)[:, None] if effort else None,
                    )
                )
            reference, measured = trajectories  # b is the reference: compare's error is reference - measured = b - a
            try:
                with np.errstate(all="ignore"), warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    error = compare(reference, measured).error
            except ValueError:  # no overlap: no rows (never extrapolated)
                continue
            kept = _inside(t_a, error.t)
            scale_q, scale_qd = (1000.0, _DEGREES) if angular else (1000.0, 1000.0)
            e_q = ("e_q_mrad" if angular else "e_q_mm", error.positions[:, 0] * scale_q)
            e_qd = ("e_qd_deg_s" if angular else "e_qd_mm_s", error.velocities[:, 0] * scale_qd)
            channels = []
            if _present((*a_part, *b_part), columns["q"]):
                channels.append(e_q)
            if _present((*a_part, *b_part), columns["qd"]):
                channels.append(e_qd)
            if effort and _present((*a_part, *b_part), effort):
                channels.append(("e_tau_nm", error.effort[:, 0]))
            for row, local in enumerate(kept):
                original = a_idx[int(local)]
                source = a_rows[original]
                entry = out.setdefault(
                    original,
                    {
                        "t": source["t"], "run": source.get("run"), "situation": source.get("situation"),
                        "source": source.get("source"), "reference": b_rows[0].get("situation"), "device": source.get("device"),
                    },
                )  # fmt: skip
                for name, values in channels:
                    entry[name] = _number(values[row])
    return [out[index] for index in sorted(out)]


def _difference_poses(a_rows: Sequence[Mapping[str, Any]], b_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    has_quat = any(name in row for row in (*a_rows, *b_rows) for name in QUAT)
    b_groups = _groups(b_rows, ("run", "body", "frame"))
    out: dict[int, dict] = {}
    for key, a_all in _groups(a_rows, ("run", "body", "frame")).items():
        b_all = b_groups.get(key)
        if not b_all:
            continue  # a body b writes in another frame, or only a has: no rows, frames are never mixed
        a_idx, b_idx = _sorted_by_time(a_rows, a_all), _sorted_by_time(b_rows, b_all)
        if not a_idx or not b_idx:
            continue
        a_part, b_part = [a_rows[i] for i in a_idx], [b_rows[i] for i in b_idx]
        trajectories, missing = [], []
        for part in (b_part, a_part):
            positions = np.stack([_column(part, name) for name in POS], axis=1) * 1e-3
            quats = np.stack([_column(part, name) for name in QUAT], axis=1)  # wxyz as written
            gone = ~np.isfinite(quats).all(axis=1) | (np.linalg.norm(np.nan_to_num(quats), axis=1) < 1e-9)
            # robot_msgs is xyzw; a null orientation is a placeholder here and a null in the row (the channel interpolates to
            # > 0 wherever either neighbour was null)
            xyzw = np.where(gone[:, None], [0.0, 0.0, 0.0, 1.0], np.roll(np.nan_to_num(quats), -1, axis=1))
            missing.append(gone)
            trajectories.append(
                PoseTrajectory(
                    t=_column(part, "t"), positions=positions, orientations=xyzw, child_frame_id=str(key[1]),
                    header=Header(frame_id=str(key[2])), channels={"orientation_missing": gone.astype(float)},
                )
            )  # fmt: skip
        reference, measured = trajectories
        try:
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                error = compare(reference, measured).error
                reference_at, _, _, _ = align(reference, measured)
        except ValueError:
            continue
        t_a = _column(a_part, "t")
        kept = _inside(t_a, error.t)
        distance = np.linalg.norm(error.positions, axis=1) * 1000.0
        ref_mm = reference_at.positions * 1000.0
        # WHY the orientation of b at t by an exact slerp here, not robot_msgs' resample: its quat_slerp falls back to a normalised
        # lerp under about 1.8 degrees (dot > 0.9995), which is 8e-4 mrad off CONTRACT section 5's slerp in the fixture. The rotation
        # from a to b is robot_msgs' own pose_error formula (q_b * conj(q_a), as a rotation vector's length).
        ref_xyzw = _slerp_exact(reference.t, reference.orientations, t_a[kept])
        rotation = quat_multiply(ref_xyzw, quat_conjugate(measured.orientations[kept]))
        angle = np.linalg.norm(quat_to_rotvec(rotation), axis=1) * 1000.0
        ref_quat = np.roll(ref_xyzw, 1, axis=1)  # back to wxyz
        # CONTRACT section 5: written with w >= 0 (at w = 0 the first non-zero of x, y, z positive)
        flip = (ref_quat[:, 0] < 0) | ((ref_quat[:, 0] == 0) & (np.sign(_first_nonzero(ref_quat[:, 1:])) < 0))
        ref_quat = np.where(flip[:, None], -ref_quat, ref_quat)
        ref_gone = reference_at.channels["orientation_missing"] > 0
        for row, local in enumerate(kept):
            original = a_idx[int(local)]
            source = a_rows[original]
            entry = {
                "t": source["t"], "run": source.get("run"), "situation": source.get("situation"), "source": source.get("source"),
                "reference": b_rows[0].get("situation"), "body": source.get("body"), "frame": source.get("frame"),
                **{name: source.get(name) for name in POS},
                **{f"ref_{name}": _number(ref_mm[row, i]) for i, name in enumerate(POS)},
                "err_mm": _number(distance[row]),
            }  # fmt: skip
            if has_quat:
                no_rotation = bool(missing[1][int(local)] or ref_gone[row])
                entry.update({name: source.get(name) for name in QUAT})
                entry.update({f"ref_{name}": None if no_rotation else _number(ref_quat[row, i]) for i, name in enumerate(QUAT)})
                entry["err_rot_mrad"] = None if no_rotation else _number(angle[row])
            out[original] = entry
    return [out[index] for index in sorted(out)]


def _slerp_exact(t_from: np.ndarray, quats: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """Slerp of unit quaternions (xyzw) at ``t_to``, the short way; a sample of ``t_from`` comes back as itself."""
    if len(t_from) == 1:
        return np.repeat(quats[:1], len(t_to), axis=0)
    upper = np.clip(np.searchsorted(t_from, t_to, side="right"), 1, len(t_from) - 1)
    lower = upper - 1
    alpha = np.clip((t_to - t_from[lower]) / (t_from[upper] - t_from[lower]), 0.0, 1.0)[:, None]
    q0, q1 = quats[lower], quats[upper]
    q1 = np.where(np.sum(q0 * q1, axis=1, keepdims=True) < 0.0, -q1, q1)
    theta = 2.0 * np.arctan2(np.linalg.norm(q1 - q0, axis=1), np.linalg.norm(q1 + q0, axis=1))[:, None]  # well conditioned near 0
    near = np.sin(theta) < 1e-12
    scale = np.where(near, 1.0, np.sin(theta))
    w0 = np.where(near, 1.0 - alpha, np.sin((1.0 - alpha) * theta) / scale)
    w1 = np.where(near, alpha, np.sin(alpha * theta) / scale)
    blended = w0 * q0 + w1 * q1
    return blended / np.linalg.norm(blended, axis=1, keepdims=True)


def _first_nonzero(values: np.ndarray) -> np.ndarray:
    """The first non-zero of each row (0 where there is none): the sign that canonicalises a quaternion with w = 0."""
    first = np.argmax(values != 0, axis=1)
    return values[np.arange(len(values)), first]


def difference(a_rows: Sequence[Mapping[str, Any]], b_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """CONTRACT section 5's difference(a, b), b - a, over the rows of one table (poses or samples) of two situations.

    One row per sample of a inside b's span (never extrapolated), on a's own times, in a's order. b at t is
    ``robot_msgs.compare``'s alignment (linear; slerp the short way); the numbers are its ``reference - measured`` error with
    reference = b, converted at the edge (mm, mrad, deg/s). A null on either side is a null in the row.
    WHY through robot_msgs: one source of truth, so the dashboards, the report and the gates cannot drift apart. a's and b's
    ``t`` must rise strictly within a key (robot_msgs' own rule).
    """
    a_rows, b_rows = list(a_rows), list(b_rows)
    if not a_rows or not b_rows:
        return []
    if all(name in a_rows[0] for name in ("body", "frame", *POS)):
        return _difference_poses(a_rows, b_rows)
    return _difference_samples(a_rows, b_rows)


# ── the schemas, copied from data-ui (assets/data_ui/schemas, README there) ──


def _contract_fields(table: str) -> dict[str, dict]:
    text = importlib.resources.files("traj_compare").joinpath("assets", "data_ui", "schemas", f"{table}.schema.json")
    return {field["name"]: field for field in json.loads(text.read_text("utf-8"))["schema"]["fields"]}


def _write_table(
    path: Path, table: str, title: str, source: str, rows: list[dict], extra: Iterable[dict] = (), *, fields: Sequence[dict] | None = None
) -> None:
    """``{"title", "source", "schema": {"fields"}, "rows"}``: the contract's fields that some row has, then the extras."""
    have = {key for row in rows for key in row}
    contract = _contract_fields(table)
    declared = list(fields) if fields is not None else [field for name, field in contract.items() if name in have]
    declared += [field for field in extra if field["name"] in have and field["name"] not in {f["name"] for f in declared}]
    body = {"title": title, "source": source, "schema": {"fields": declared}}
    one = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one(body)
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(row) for row in rows) + "\n]}\n", encoding="utf-8")


# ── rows from the runs ───────────────────────────────────────────────────────


def _family(situation: str) -> str:
    """The situation's family (CONTRACT section 1): the reference is ``target``, a name starting ``real`` is ``real``, the rest ``sim``."""
    if situation == TARGET:
        return "target"
    return "real" if situation.startswith("real") else "sim"


def _stride(trajectory: JointTrajectory, display_hz: float) -> tuple[int, float | None]:
    """Rows to step by so the written rate is at most ``display_hz`` (picking rows, never averaging), and the native rate."""
    if len(trajectory) < 2:
        return 1, None
    rate = 1.0 / float(np.median(np.diff(trajectory.t)))
    return max(1, math.ceil(rate / display_hz - 1e-9)), rate


def _pick(trajectory: JointTrajectory, stride: int) -> JointTrajectory:
    return trajectory if stride == 1 else trajectory[np.arange(0, len(trajectory), stride)]


def _resolve(spec: str | Callable[..., Any] | None, roots: list[str]) -> Callable[..., Any] | None:
    if spec is None or callable(spec):
        return spec
    root = _spec_import_root(spec)
    if root is not None and root not in roots:
        roots.append(root)
    return _import_spec(spec, roots)


def links_from_robot(robot: Callable[[], Any]) -> Callable[[JointTrajectory], dict[str, PoseTrajectory]]:
    """``links`` for a ``robot() -> RobotDisplay`` spec: each link's ``link_fk`` pose as a PoseTrajectory, in metres."""

    display = robot()

    def links(trajectory: JointTrajectory) -> dict[str, PoseTrajectory]:
        poses = np.asarray(display.link_fk(trajectory.positions))
        result = {}
        for index, name in enumerate(display.link_names):
            positions, orientations = matrix_to_pose(poses[:, index])
            result[name] = PoseTrajectory(t=trajectory.t, positions=positions, orientations=orientations, header=trajectory.header)
        return result

    return links


def _started(started: Any, run: Run, written: str) -> tuple[str, bool]:
    """(ISO start with offset, whether it is the write time because nothing says when the run started)."""
    value = started.get(run.name) if isinstance(started, Mapping) else started
    if value is None:
        value = run.tags.get("started")
    if value is None:
        return written, True
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.astimezone()
        return value.isoformat(timespec="seconds"), False
    parsed = datetime.fromisoformat(str(value))
    return (parsed if parsed.tzinfo else parsed.astimezone()).isoformat(timespec="seconds"), False


def _when(started: str) -> str:
    """``Nov 11 10:49``: the table's reading of ``started`` (data-ui draws a datetime as its ISO text; the sort stays on ``started``)."""
    moment = datetime.fromisoformat(started)
    return f"{moment:%b} {moment.day} {moment:%H:%M}"


def _probe(path: Path) -> tuple[float | None, float | None]:
    """(fps, duration_s) of a clip through ffprobe; (None, None) when it is absent or cannot read it: missing is null."""
    if shutil.which("ffprobe") is None:
        return None, None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )  # fmt: skip
        info = json.loads(out.stdout)
        numerator, _, denominator = info["streams"][0]["avg_frame_rate"].partition("/")
        fps = float(numerator) / float(denominator or 1)
        return (round(fps, 3) if fps > 0 else None), _round(info["format"].get("duration"), 3)
    except (subprocess.SubprocessError, KeyError, IndexError, ValueError, ZeroDivisionError, OSError):
        return None, None


def _poster(video: Path, target: Path) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        subprocess.run(  # noqa: S603 - fixed argv
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1", "-q:v", "4", str(target)],
            check=True, timeout=60,
        )  # fmt: skip
    except (subprocess.SubprocessError, OSError):
        return False
    return target.is_file()


def _tag_columns(runs: Sequence[Run]) -> dict[str, str]:
    """Each tag as a column of runs.json: its own name, unless that is one of the contract's (then ``tag_<name>``; ``kind`` is the kind)."""
    columns: dict[str, str] = {}
    for run in runs:
        for tag in run.tags:
            if tag == "kind":
                continue
            columns[tag] = f"tag_{tag}" if tag in _RUN_COLUMNS else tag
    return columns


def _extra_field(name: str, values: Sequence[Any], description: str = "") -> dict:
    kinds = {type(value) for value in values if value is not None}
    kind = "boolean" if kinds <= {bool} and kinds else "number" if kinds and kinds <= {int, float} else "string"
    field = {"name": name, "type": kind}
    if description:
        field["description"] = description
    return field


# ── write ────────────────────────────────────────────────────────────────────


def write_tables(
    runs: Sequence[Run],
    out_dir: Path | str,
    *,
    poses: str | Callable[[JointTrajectory], PoseTrajectory] | None = None,
    links: str | Callable[[JointTrajectory], Mapping[str, PoseTrajectory]] | None = None,
    frame: str = "base",
    display_hz: float = 100.0,
    deployment: str = "",
    started: Any = None,
) -> Path:
    """Write the contract's tables and ``views.base`` into ``out_dir`` (``<dataset>/data-ui``) and return it.

    - ``poses``: ``"module:function"`` (or a callable), ``JointTrajectory -> PoseTrajectory`` in metres: the TCP, written to
      poses.json in ``frame`` (mm) with diff_poses.json beside it. The body is the PoseTrajectory's ``child_frame_id``.
    - ``links``: ``"module:function"`` (or a callable), ``JointTrajectory -> {link: PoseTrajectory}`` of each link's world pose in
      metres: links.json (mm).
    - ``display_hz``: at most this many rows per second per series, picked (every k-th row), never averaged. The differences are
      computed on the rows written, so anyone can recompute them from poses.json and samples.json.
    - ``deployment``: the machine's name, runs.json's ``deployment`` and the joints' parent.
    - ``started``: a datetime or ISO text for every run, or ``{run name: ...}``; else a run's ``started`` tag; else the time of
      this write (the runs record no start; the row's ``note`` says so).

    A series' clock is shifted by its ``time_offset_s`` onto the target's, so ``t`` is seconds of the target's clock and a
    difference agrees with ``compare(..., time_offset_s=...)``. The ``runs/<slug>/report.html`` of each run is the drill-down
    that ``runs.json``'s ``url`` points at (``write_dataset_report`` writes both).
    """
    runs = list(runs)
    if not runs:
        raise ValueError("need at least one run")
    if display_hz <= 0:
        raise ValueError(f"display_hz must be positive, got {display_hz}")
    for run in runs:
        if TARGET in run.measured:
            raise ValueError(f"run {run.name!r}: {TARGET!r} is the reference's situation name, not a series name")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slugs = _unique_slugs(runs)
    roots: list[str] = []
    pose_of = _resolve(poses, roots)
    links_of = _resolve(links, roots)
    written = datetime.now().astimezone().isoformat(timespec="seconds")
    tag_columns = _tag_columns(runs)

    samples: list[dict] = []
    pose_rows: list[dict] = []
    link_rows: list[dict] = []
    run_rows: list[dict] = []
    media_rows: list[dict] = []
    devices: dict[str, dict] = {}
    for run in runs:
        series = {TARGET: run.reference, **run.measured}
        stamp = float(run.reference.header.stamp)
        picked: dict[str, JointTrajectory] = {}
        native, written_rates = [], []
        for name, trajectory in series.items():
            stride, rate = _stride(trajectory, display_hz)
            picked[name] = _pick(trajectory, stride)
            if rate is not None:
                native.append(rate)
                written_rates.append(rate / stride)
        for name, trajectory in picked.items():
            offset = float(run.time_offset_s.get(name, 0.0))
            t = np.round(trajectory.absolute_times - stamp - offset, 6)
            source = _family(name)
            for column, joint in enumerate(trajectory.joint_names):
                for row, time in enumerate(t):
                    entry = {"t": float(time), "run": run.name, "situation": name, "source": source, "device": joint}
                    entry["q_deg"] = _round(trajectory.positions[row, column] * _DEGREES, _VALUE_DIGITS)
                    if trajectory.velocities is not None:
                        entry["qd_deg_s"] = _round(trajectory.velocities[row, column] * _DEGREES, _VALUE_DIGITS)
                    if trajectory.accelerations is not None:
                        entry["qdd_deg_s2"] = _round(trajectory.accelerations[row, column] * _DEGREES, _VALUE_DIGITS)
                    if trajectory.effort is not None:
                        entry["tau_nm"] = _round(trajectory.effort[row, column], _VALUE_DIGITS)
                    samples.append(entry)
            if pose_of is not None:
                pose = pose_of(trajectory)
                body = pose.child_frame_id or "tcp"
                for row, time in enumerate(t):
                    x, y, z = (pose.positions[row] * 1000.0).tolist()
                    qx, qy, qz, qw = pose.orientations[row].tolist()
                    pose_rows.append(
                        {
                            "t": float(time), "run": run.name, "situation": name, "source": source, "body": body, "frame": frame,
                            "x_mm": _round(x, _OUT_DIGITS), "y_mm": _round(y, _OUT_DIGITS), "z_mm": _round(z, _OUT_DIGITS),
                            "quat_w": _round(qw, _VALUE_DIGITS), "quat_x": _round(qx, _VALUE_DIGITS),
                            "quat_y": _round(qy, _VALUE_DIGITS), "quat_z": _round(qz, _VALUE_DIGITS),
                        }
                    )  # fmt: skip
            if links_of is not None:
                per_link = links_of(trajectory)
                for row, time in enumerate(t):
                    entry = {"t": float(time), "run": run.name, "situation": name, "source": source}
                    for link, pose in per_link.items():
                        x, y, z = (pose.positions[row] * 1000.0).tolist()
                        qx, qy, qz, qw = pose.orientations[row].tolist()
                        entry.update({f"{link}_x": _round(x, _OUT_DIGITS), f"{link}_y": _round(y, _OUT_DIGITS), f"{link}_z": _round(z, _OUT_DIGITS)})
                        entry.update({f"{link}_qw": _round(qw, _VALUE_DIGITS), f"{link}_qx": _round(qx, _VALUE_DIGITS)})
                        entry.update({f"{link}_qy": _round(qy, _VALUE_DIGITS), f"{link}_qz": _round(qz, _VALUE_DIGITS)})
                    link_rows.append(entry)
        reference = run.reference
        for joint in reference.joint_names:
            device = devices.setdefault(
                joint, {"device": joint, "type": "servo", "label": joint, "parent": deployment or "robot", "order": len(devices) + 1}
            )
            limits = reference.limits
            if limits is not None and joint in limits.joint_names:
                at = limits.joint_names.index(joint)
                for column_name, array, scale in (
                    ("q_min_deg", limits.min_position, _DEGREES), ("q_max_deg", limits.max_position, _DEGREES),
                    ("qd_max_deg_s", limits.max_velocity, _DEGREES), ("tau_max_nm", limits.max_effort, 1.0),
                ):  # fmt: skip
                    value = None if array is None else _round(array[at] * scale, _OUT_DIGITS)
                    if value is not None:
                        device.setdefault(column_name, value)
        start, defaulted = _started(started, run, written)
        extras = {tag_columns[tag]: value for tag, value in run.tags.items() if tag in tag_columns}
        run_rows.append(
            {
                "run": run.name, "deployment": deployment, "started": start, "when": _when(start),
                "duration_s": _round(reference.t[-1] - reference.t[0], 6), "kind": str(run.tags.get("kind", "trajectory")),
                "devices": list(reference.joint_names), "situations": list(series),
                "rate_hz": _round(max(native), 3) if native else None, "display_hz": _round(max(written_rates), 3) if written_rates else None,
                "label": run.title or run.name, "url": f"../runs/{slugs[run.name]}/report.html",
                **({"note": "started: the time this dataset was written (the runs record no start)"} if defaulted else {}),
                **extras,
            }
        )  # fmt: skip
        for key, clip in run.media.items():
            clip = Path(clip)
            fps, duration = _probe(clip)
            (out / "media").mkdir(exist_ok=True)
            poster = f"media/{slugs[run.name]}-{_slug(key)}.jpg"
            media_rows.append(
                {
                    "src": f"../runs/{slugs[run.name]}/media/{_safe_name(key)}{clip.suffix.lower()}",
                    "poster": poster if _poster(clip, out / poster) else None,
                    "t0": _round(run.media_start_s.get(key, 0.0), 3), "fps": fps, "duration": duration,
                    "basis": None, "run": run.name, "camera": key, "kind": "rgb",
                }
            )  # fmt: skip

    source = "traj_compare.data_ui (CONTRACT v1, gallery/robotics/CONTRACT.md)"
    tag_fields = [{"name": "when", "type": "string", "title": "Started", "description": "started, as a short text for a table (display only)"}]
    tag_fields += [_extra_field(column, [row.get(column) for row in run_rows]) for column in dict.fromkeys(tag_columns.values())]
    _write_table(out / "runs.json", "runs", "Runs", source, run_rows, tag_fields)
    _write_table(out / "samples.json", "samples", "Joints: angle, velocity, acceleration and torque per joint", source, samples)
    _write_table(out / "devices.json", "devices", "Devices: one servo per joint", source, list(devices.values()))
    if pose_of is not None:
        _write_table(out / "poses.json", "poses", "TCP poses (mm, wxyz)", source, pose_rows)
    if links_of is not None:
        names = list(dict.fromkeys(key[:-2] for row in link_rows for key in row if key.endswith("_x")))
        fields = list(_contract_fields("links").values())
        for link in names:
            fields += [{"name": f"{link}_{axis}", "type": "number", "unit": "mm"} for axis in ("x", "y", "z")]
            fields += [{"name": f"{link}_{part}", "type": "number"} for part in ("qw", "qx", "qy", "qz")]
        _write_table(out / "links.json", "links", "Link poses (mm, wxyz)", source, link_rows, fields=fields)
    if media_rows:
        _write_table(out / "media.json", "media", "Clips", source, media_rows)

    # difference(a, b): each situation against the target, each sim situation against each real one (CONTRACT section 5)
    def pairs(rows: list[dict]) -> list[tuple[str, str]]:
        situations = list(dict.fromkeys(row["situation"] for row in rows))
        families = {name: _family(name) for name in situations}
        return [(a, TARGET) for a in situations if a != TARGET] + [
            (a, b) for a in situations if families[a] == "sim" for b in situations if families[b] == "real"
        ]

    def diff_table(rows: list[dict], label: str) -> list[dict]:
        result: list[dict] = []
        by_run: dict[str, dict[str, list[dict]]] = {}
        for row in rows:
            by_run.setdefault(row["run"], {}).setdefault(row["situation"], []).append(row)
        for run, by_situation in by_run.items():
            for a, b in pairs([row for part in by_situation.values() for row in part[:1]]):
                rows_ab = difference(by_situation[a], by_situation[b])
                if not rows_ab:
                    warnings.warn(f"{run}: {label} {a} against {b}: no sample of {a} lies in {b}'s span", stacklevel=3)
                result += rows_ab
        return result

    # WHY a degrees column beside the contract's e_q_mrad (and err_rot_deg beside err_rot_mrad): data-ui draws the stored number
    # (it converts nothing, and a .base formula is a coalesce, never arithmetic), and every human-facing view here shows degrees.
    # CONTRACT section 5 lets a library add e_<channel> "in its unit": this is q_deg's, the same difference as e_q_mrad.
    joint_diff = diff_table(samples, "joints")
    for row in joint_diff:
        if row.get("e_q_mrad") is not None:
            row["e_q_deg"] = row["e_q_mrad"] / 1000.0 * _DEGREES
    joint_diff = _rounded(joint_diff, {"e_q_deg": _VALUE_DIGITS})
    _write_table(
        out / "diff_samples.json", "diff_samples", "Difference of the joints: each situation against the target, each sim against the real (b − a)",
        source, joint_diff,
        [{"name": "e_q_deg", "type": "number", "unit": "deg", "description": "b − a of q_deg: e_q_mrad's difference in degrees (this producer's own column, the display unit)"}],
    )  # fmt: skip
    if pose_of is not None:
        tcp_diff = diff_table(pose_rows, "tool")
        for row in tcp_diff:
            if row.get("err_rot_mrad") is not None:
                row["err_rot_deg"] = row["err_rot_mrad"] / 1000.0 * _DEGREES
        tcp_diff = _rounded(tcp_diff, {"err_rot_deg": _VALUE_DIGITS, **{name: _VALUE_DIGITS for name in (*QUAT, *(f"ref_{q}" for q in QUAT))}})
        _write_table(
            out / "diff_poses.json", "diff_poses", "Difference of the tool: each situation against the target, each sim against the real (b − a)",
            source, tcp_diff,
            [{"name": "err_rot_deg", "type": "number", "unit": "deg", "description": "the rotation from a to b in degrees: err_rot_mrad's display unit (this producer's own column)"}],
        )  # fmt: skip

    (out / "views.base").write_text(
        _views_base(
            joints=list(devices),
            has_poses=pose_of is not None,
            has_media=bool(media_rows),
            tag_columns=list(dict.fromkeys(tag_columns.values())),
            has_labels=any(row["label"] != row["run"] for row in run_rows),
        ),
        encoding="utf-8",
    )
    return out


DATA_UI_KIT = Path("/home/bam/data-ui/dist/site/kit")  # a built data-ui (npm --prefix /home/bam/data-ui run build)

_VIEWER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="kit/data-ui.css"><style>body{{margin:0;padding:16px}}</style></head>
<body><data-dashboard id="traj-compare" src="data-ui/views.base"></data-dashboard>
<script type="module">import './kit/data-ui.js'; import('./kit/dashboard.js');</script></body></html>
"""


def stage_viewer(dataset_dir: Path | str, kit: Path | str = DATA_UI_KIT, title: str = "traj_compare dataset") -> Path | None:
    """``<dataset_dir>/data-ui.html`` and a ``kit`` link to a built data-ui, so ``python -m traj_compare.serve <dataset_dir>`` shows
    the dashboard at ``/data-ui.html`` (and builds a run's drill-down when its link is followed). None when there is no kit.

    WHY a page here and no data-ui change: data-ui is not a standalone app; its dashboards are embedded by the host. This is the
    smallest host: one custom element over the files above.
    """
    kit = Path(kit)
    if not (kit / "data-ui.js").is_file():
        return None
    folder = Path(dataset_dir)
    link = folder / "kit"
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(kit.resolve())
    page = folder / "data-ui.html"
    page.write_text(_VIEWER.format(title=title.replace("<", "&lt;")), encoding="utf-8")
    return page


def _rounded(rows: list[dict], digits: Mapping[str, int]) -> list[dict]:
    """Every float of every row to the display projection's digits (6 unless the column says more): t, mm, mrad, deg/s, N·m."""
    return [{k: (round(v, digits.get(k, _OUT_DIGITS)) if isinstance(v, float) else v) for k, v in row.items()} for row in rows]


# ── views.base ───────────────────────────────────────────────────────────────


def _quote(text: str) -> str:
    """A YAML single-quoted scalar."""
    return "'" + text.replace("'", "''") + "'"


def _views_base(*, joints: Sequence[str], has_poses: bool, has_media: bool, tag_columns: Sequence[str], has_labels: bool) -> str:
    """data-ui's robotics playback dashboard over the tables (gallery/examples/robotics-arm/views.base, without its stand-in data).

    WHY every joint error reads ``e_q_deg`` and the tool's ``err_mm``: angles are degrees at the display edge (Zach's rule) and a
    .base cannot compute a unit conversion; the stored column is the display unit. Colour by family, the target muted.
    """
    first_joint = _quote(f'device == "{joints[0]}"')
    show = "poses" if has_poses else "samples"
    sort = json.dumps(list(joints), ensure_ascii=False)
    columns = ["run", *(["label"] if has_labels else []), "when", "kind", "duration_s", *tag_columns, "situations"]
    lines = [
        "# traj_compare's dataset as data-ui's robotics playback dashboard, over the trajectory contract's tables",
        "# (gallery/robotics/CONTRACT.md, version 1), written by traj_compare.data_ui. The rail picks a run (the first row of the",
        "# runs table when the page opens) and a joint; Show hides a situation in every panel. Colour by family (style.families:",
        "# real slot 1, sim slot 2, target muted). Angles are degrees, the tool's error is mm: the stored columns are the display",
        "# units (e_q_deg is e_q_mrad's degrees, this producer's own column beside the contract's). A run's `url` is its classic",
        "# drill-down (../runs/<slug>/report.html).",
        "data: runs.json",
        "style:",
        "  chrome: minimal",
        "  numbers: { digits: 4, compact: true }",
        "  families: { property: source, colors: { real: 1, sim: 2, target: muted } }",
        f"clock: {{ data: {show}, time: t }}",
        "datasets:",
        "  runs:",
        "    data: runs.json",
        "    label: Runs",
        "    facets:",
        "      - { property: run, as: select, label: Run }",
    ]
    if has_poses:
        lines += ["  poses:", "    data: poses.json", "    label: Tool poses", "    facets:", "      - { property: situation, label: Show }"]
    lines += ["  samples:", "    data: samples.json", "    label: Joints", "    facets:", "      - { property: device, as: select, label: Joint }"]
    if not has_poses:
        lines += ["      - { property: situation, label: Show }"]
    lines += [f"    filters: {first_joint}"]
    if has_poses:
        lines += ["  diff:", "    data: diff_poses.json", "    label: Tool difference"]
    lines += ["  joint_diff:", "    data: diff_samples.json", "    label: Joint difference"]
    if has_media:
        lines += ["  media: media.json"]
    lines += [
        "  # COVERAGE: unlinked copies, so a run pick never empties them",
        "  all_samples:",
        "    data: samples.json",
        "    label: Joints, every run",
    ]
    if has_poses:
        lines += ["  all_poses:", "    data: poses.json", "    label: Tool, every run"]
    lines += [
        "links:",
        "  # WHY one-way: the run pick narrows the joints (and the poses); Show and Joint never narrow the runs",
        "  - { from: runs.run, to: samples.run, direction: one-way }",
    ]
    if has_poses:
        lines += [
            "  - { from: runs.run, to: poses.run, direction: one-way }",
            "  - { from: samples.run, to: poses.run }",
            "  - { from: samples.situation, to: poses.situation }",
            "  # WHY a link per key column: a hidden situation loses its arrows and its error lines in every panel",
            "  - { from: diff.run, to: poses.run }",
            "  - { from: diff.situation, to: poses.situation }",
            "  - { from: diff.body, to: poses.body }",
            "  - { from: joint_diff.run, to: poses.run }",
            "  - { from: joint_diff.situation, to: poses.situation }",
        ]
    lines += [
        "  - { from: joint_diff.run, to: samples.run }",
        "  - { from: joint_diff.device, to: samples.device }",
        "  - { from: joint_diff.situation, to: samples.situation }",
    ]
    if has_media:
        lines += ["  - { from: media.run, to: samples.run }"]
    panels = ["    - { view: Runs, w: 12, h: 4 }", "    - { view: Playback, w: 12 }"]
    note = '    - text: "**Coverage** · every run, unlinked: a run pick never empties these. Each run\'s tool path at 1/n opacity per family, and each joint\'s range."\n      w: 12'
    if has_poses:
        panels += ["    - { view: Path 3D, w: 6, h: 6 }", "    - { view: Path top, w: 6, h: 6 }", "    - { view: Tool error, w: 4, h: 3 }"]
        panels += ["    - { view: Joint error, w: 4, h: 3 }", "    - { view: Joint angle, w: 4, h: 3 }"]
        if has_media:
            panels += ["    - { view: Camera, w: 6, h: 5 }", "    - { view: Coverage, w: 6, h: 5 }", note, "    - { view: Joint range, w: 12, h: 3 }"]
        else:
            panels += [note, "    - { view: Coverage, w: 6, h: 5 }", "    - { view: Joint range, w: 6, h: 5 }"]
    else:
        panels += ["    - { view: Joint error, w: 6, h: 3 }", "    - { view: Joint angle, w: 6, h: 3 }"]
        panels += (["    - { view: Camera, w: 6, h: 4 }", "    - { view: Joint range, w: 6, h: 4 }"] if has_media else ["    - { view: Joint range, w: 12, h: 4 }"])
    lines += ["layout:", "  panels:", *panels]
    lines += ["properties:", "  when: { displayName: Started }", "  duration_s: { displayName: Duration }", "  kind: { displayName: Kind }", "  situations: { displayName: Situations }", "views:"]
    lines += [
        "  # the runs table picks a run on the rail (a picker, CONTRACT section 33); its first row when the page opens",
        "  - type: table",
        "    name: Runs",
        "    from: runs",
        "    select: run",
        "    selected: first",
        f"    order: [{', '.join(columns)}]",
        "    sort:",
        "      - { property: started, direction: DESC }",
        "  - type: playback",
        "    name: Playback",
        "    playback: { readout: true }",
    ]
    if has_poses:
        lines += [
            "  - type: trajectory3d",
            "    name: Path 3D",
            "    from: poses",
            "    # arrows a(t) to b(t): each situation against the target, and each sim against the real",
            "    trajectory3d: { compare: { data: diff }, show: trail, decay: 0.6 }",
            "  - type: trajectory3d",
            "    name: Path top",
            "    from: poses",
            "    trajectory3d: { projection: top, compare: { data: diff } }",
            "  # |b - a| of the tool against the target (the arrows' lengths), in mm",
            "  - type: timeseries",
            "    name: Tool error",
            "    from: diff",
            "    filters: 'reference == \"target\"'",
            "    timeseries: { x: t, 'y': err_mm, series: situation, legend: top, unit: mm }",
        ]
    lines += [
        "  # e_q = target - q of the rail's joint, in degrees",
        "  - type: timeseries",
        "    name: Joint error",
        "    from: joint_diff",
        "    filters: 'reference == \"target\"'",
        "    timeseries: { x: t, 'y': e_q_deg, series: situation, legend: top, unit: '°', rules: [{ 'y': 0 }] }",
        "  - type: timeseries",
        "    name: Joint angle",
        "    from: samples",
        "    timeseries: { x: t, 'y': q_deg, series: situation, dash: [target], legend: top, unit: '°' }",
    ]
    if has_media:
        lines += ["  - type: video", "    name: Camera", "    from: media", "    video: { src: src, label: camera }"]
    if has_poses:
        lines += [
            "  # every run of every situation at opacity auto (1/n over each family's paths), from the top",
            "  - type: trajectory3d",
            "    name: Coverage",
            "    from: all_poses",
            "    trajectory3d: { projection: top, opacity: auto }",
        ]
    lines += [
        "  # each joint's range over every run and situation: the whiskers are the min and max",
        "  - type: chart",
        "    name: Joint range",
        "    from: all_samples",
        "    chart:",
        "      mark: { type: boxplot, extent: min-max }",
        "      encoding:",
        f"        x: {{ field: device, type: nominal, title: joint, sort: {sort} }}",
        "        'y': { field: q_deg, type: quantitative, title: 'q (°)' }",
    ]
    return "\n".join(lines) + "\n"
