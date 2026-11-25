#!/usr/bin/env python3
"""R4 "Robot first, numbers at the cursor": a robot_msgs JointTrajectory + a URDF -> one .rrd whose 3D view IS the viewer.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r4/make.py

Writes r4/workspace-dev-029.rrd and r4/workspace-dev-003.rrd (the round's two inputs; they play and loop on open) and the
same two under r4/paused/ (open paused at 0 s, for the round's stills). The entry point is `save()`:

    save(path, traj, robot=urdf_path, tool=pose_traj_or_None, name="target", ghosts=5, playing=True)

What the recording shows (round contract 2026-11-24, Zach: "100% there should be a urdf showing"):
- the URDF arm moving with the trajectory, framed by a camera computed from the arm's own forward kinematics;
- the tool's whole path faint and coloured by tool speed, plus a bright trail of only the last DECAY_S seconds
  (WHY: data-ui trajectory3d's "decay" trail, Zach's Oct 28 ask, Rerun-native via a per-entity VisibleTimeRanges);
- GHOSTS faint copies of the arm at evenly spaced instants, each tool tip labelled with its time, so one still
  reads the whole motion;
- at the cursor: a readout of every joint's angle in degrees, where it sits between its limits and its speed,
  plus a bar chart of the same "% of range"; below, a narrow strip of q / qd / tool speed over time.

Grown from robot_msgs.viz.rerun (the JointTrajectory series logger, the PoseTrajectory world/<name>/path + frame
pattern, the /<field>/<column>/<name> layout) and traj_compare's rerun_export (_stage_eye framing, evo's growing time
ranges, the joint short names); the URDF is Rerun 0.40's own `rerun.urdf.UrdfTree`.
"""
from __future__ import annotations

import warnings
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
import rerun.urdf as rru
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as viz

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
APPLICATION_ID = "rerun-joint-trajectory-r4"
TIMELINE = viz.TIMELINE
DECAY_S = 0.5  # seconds of bright trail behind the playhead (data-ui trajectory3d's default decay is 0.5-0.6 s)
GHOSTS = 5  # faint arm poses at evenly spaced instants, first and last included
NEAR_LIMIT = 0.05  # a joint within 5 % of its range from a limit is flagged in the readout

# WHY these colours: categorical joint colours legible on Rerun's dark theme, no red (Zach's calm-UI rule: red and
# amber only for problems); speed uses viridis from its mid-dark end up, so slow is still visible on dark grey.
JOINT_COLORS = [(78, 154, 214), (242, 142, 43), (118, 183, 178), (120, 190, 90), (176, 122, 200), (237, 201, 72),
                (255, 157, 167), (170, 130, 100)]
VIRIDIS = np.array([[59, 82, 139], [44, 114, 142], [33, 145, 140], [39, 173, 129], [94, 201, 98],
                    [170, 220, 50], [253, 231, 37]], dtype=float)
# WHY a mid steel arm and pale, very thin ghosts (stills 2026-11-24): with ghosts at alpha 56 the live wrist vanished in
# the ghost fog whenever it passed behind one; mid grey reads on both Rerun themes.
ROBOT_RGBA = (138, 146, 160, 255)
GHOST_RGBA = (175, 190, 215, 36)
RANGE_RGBA = (150, 150, 150, 45)  # the full-range bar behind each joint's bar: the gauge's empty part


# ── small numerics (numpy only: robot_msgs' viz extra is rerun + numpy) ──────────────────────────────────────


def _short(joint: str) -> str:
    """A joint's readable name: the URDF name without its trailing "_joint" (shoulder_pan_joint -> shoulder_pan)."""
    return joint[: -len("_joint")] if joint.endswith("_joint") else joint


def _speed_rgb(fraction: np.ndarray) -> np.ndarray:
    """0 (slow) -> blue, 1 (this trajectory's fastest) -> yellow, viridis-like."""
    scaled = np.clip(np.nan_to_num(fraction), 0.0, 1.0) * (len(VIRIDIS) - 1)
    low = np.minimum(np.floor(scaled).astype(int), len(VIRIDIS) - 2)
    mix = (scaled - low)[:, None]
    return (VIRIDIS[low] * (1 - mix) + VIRIDIS[low + 1] * mix).astype(np.uint8)


def _rpy(r: float, p: float, y: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _about(axis: Sequence[float], angle: np.ndarray) -> np.ndarray:
    """(N,) angles about one axis -> (N, 3, 3) rotations (Rodrigues)."""
    a = np.asarray(axis, dtype=float)
    a = a / max(np.linalg.norm(a), 1e-12)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    s, c = np.sin(angle)[:, None, None], np.cos(angle)[:, None, None]
    return np.eye(3) + s * k + (1 - c) * (k @ k)


def _quat_xyzw(rot: np.ndarray) -> np.ndarray:
    """(N, 3, 3) rotation matrices -> (N, 4) unit quaternions, xyzw as robot_msgs and Rerun keep them."""
    m = np.asarray(rot, dtype=float).reshape(-1, 3, 3)
    w = np.sqrt(np.maximum(0.0, 1 + m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2])) / 2
    x = np.sqrt(np.maximum(0.0, 1 + m[:, 0, 0] - m[:, 1, 1] - m[:, 2, 2])) / 2
    y = np.sqrt(np.maximum(0.0, 1 - m[:, 0, 0] + m[:, 1, 1] - m[:, 2, 2])) / 2
    z = np.sqrt(np.maximum(0.0, 1 - m[:, 0, 0] - m[:, 1, 1] + m[:, 2, 2])) / 2
    x = np.copysign(x, m[:, 2, 1] - m[:, 1, 2])
    y = np.copysign(y, m[:, 0, 2] - m[:, 2, 0])
    z = np.copysign(z, m[:, 1, 0] - m[:, 0, 1])
    q = np.stack([x, y, z, w], axis=1)
    return q / np.linalg.norm(q, axis=1, keepdims=True)


# ── the robot: the URDF's own joints drive both the Rerun transforms and our forward kinematics ─────────────


def _joint_values(tree: rru.UrdfTree, traj: JointTrajectory) -> dict[str, np.ndarray]:
    """Every movable URDF joint's value per sample: from the trajectory, a mimic of one of its joints, or 0.

    WHY every joint, not only the trajectory's: a movable joint with no transform logged breaks the frame chain and
    everything below it vanishes (a gripper's fingers when only the arm is planned)."""
    q = np.asarray(traj.positions, dtype=float)
    index = {name: i for i, name in enumerate(traj.joint_names)}
    values: dict[str, np.ndarray] = {}
    for joint in tree.joints():
        if joint.joint_type == "fixed":
            continue
        if joint.name in index:
            values[joint.name] = q[:, index[joint.name]]
        elif joint.mimic is not None and joint.mimic.joint in index:
            values[joint.name] = joint.mimic.multiplier * q[:, index[joint.mimic.joint]] + joint.mimic.offset
        else:
            values[joint.name] = np.zeros(len(q))
    return values


def _forward(tree: rru.UrdfTree, values: dict[str, np.ndarray], samples: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Every link's pose in the root link's frame per sample: link -> (R (N, 3, 3), p (N, 3)), from the URDF alone."""
    eye = np.tile(np.eye(3), (samples, 1, 1))
    poses = {tree.root_link().name: (eye, np.zeros((samples, 3)))}
    pending = list(tree.joints())
    while pending:
        progressed = False
        for joint in list(pending):
            if joint.parent_link not in poses:
                continue
            parent_r, parent_p = poses[joint.parent_link]
            origin_r = parent_r @ _rpy(*joint.origin_rpy)
            origin_p = parent_p + parent_r @ np.asarray(joint.origin_xyz, dtype=float)
            value = values.get(joint.name, np.zeros(samples))
            if joint.joint_type in ("revolute", "continuous"):
                poses[joint.child_link] = (origin_r @ _about(joint.axis, value), origin_p)
            elif joint.joint_type == "prismatic":
                shift = value[:, None] * np.asarray(joint.axis, dtype=float)[None]
                poses[joint.child_link] = (origin_r, origin_p + np.einsum("nij,nj->ni", origin_r, shift))
            else:
                poses[joint.child_link] = (origin_r, origin_p)
            pending.remove(joint)
            progressed = True
        if not progressed:  # a joint whose parent is not reachable from the root: leave it out
            break
    return poses


def _flange(tree: rru.UrdfTree, traj: JointTrajectory) -> str:
    """The link the tool hangs from: the child of the trajectory's last joint, then down any chain of fixed joints."""
    joint = tree.get_joint_by_name(traj.joint_names[-1])
    link = joint.child_link if joint is not None else tree.root_link().name
    while True:
        fixed = [j for j in tree.joints() if j.parent_link == link and j.joint_type == "fixed"]
        if len(fixed) != 1:
            return link
        link = fixed[0].child_link


def _robot_root(tree: rru.UrdfTree) -> str:
    return f"/world/{viz.path_part(tree.name)}"


def _recolor(recording: rr.RecordingStream, chunks: list, rgba: Sequence[int], move=lambda path: path) -> None:
    """Send the URDF geometry chunks (paths moved by `move`) and give every geometry one colour.

    WHY by archetype: a URDF mesh arrives as Asset3D (albedo_factor), a primitive as Boxes3D / Cylinders3D /
    Ellipsoids3D / Mesh3D (colors or albedo_factor); one colour per robot keeps the arm and its ghosts apart."""
    colored: set[str] = set()
    for chunk in chunks:
        path = move(str(chunk.entity_path))
        recording.send_chunks(chunk.with_entity_path(path) if path != str(chunk.entity_path) else chunk)
        if path in colored:
            continue
        names = " ".join(chunk.to_record_batch().schema.names)
        if "Asset3D:" in names:
            recording.log(path, rr.Asset3D.from_fields(albedo_factor=rgba), static=True)
        elif "Mesh3D:" in names:
            recording.log(path, rr.Mesh3D.from_fields(albedo_factor=rgba), static=True)
        else:
            for archetype in (rr.Boxes3D, rr.Cylinders3D, rr.Ellipsoids3D, rr.Capsules3D):
                if f"{archetype.__name__}:" in names:
                    recording.log(path, archetype.from_fields(colors=[rgba]), static=True)
                    break
            else:
                continue
        colored.add(path)


def _log_robot(recording: rr.RecordingStream, urdf: Path, values: dict[str, np.ndarray], seconds: np.ndarray) -> rru.UrdfTree:
    """The URDF arm at /world/<robot>/..., its joints driven on the t timeline (Rerun's own URDF loader)."""
    probe = rru.UrdfTree.from_file_path(urdf)
    root = _robot_root(probe)
    tree = rru.UrdfTree.from_file_path(urdf, entity_path_prefix="world", static_transform_entity_path=f"{root}/tf_static")
    _recolor(recording, list(tree.stream(include_joint_transforms=True)), ROBOT_RGBA)
    for name, value in values.items():
        joint = tree.get_joint_by_name(name)
        recording.send_columns(f"{root}/joint_transforms/{viz.path_part(name)}",
                               indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                               columns=joint.compute_transform_columns(value.tolist(), clamp=False))
    return tree


def _log_ghosts(recording: rr.RecordingStream, urdf: Path, tree: rru.UrdfTree, values: dict[str, np.ndarray],
                keys: np.ndarray) -> None:
    """GHOSTS faint copies of the arm, frozen at the sample indices `keys`, at /world/<robot>/ghosts/<k>/...

    WHY a second UrdfTree per ghost: `frame_prefix` gives each copy its own frames, so one static set of joint
    transforms poses it; an identity transform hangs its root frame on the live arm's root."""
    root = _robot_root(tree)
    for k, sample in enumerate(keys):
        prefix = f"ghost{k}/"
        base = f"{root}/ghosts/{k}"
        ghost = rru.UrdfTree.from_file_path(urdf, entity_path_prefix="world", frame_prefix=prefix)

        def move(path: str, base: str = base) -> str:
            if path.startswith(base):
                return path
            return base + path[len(root):] if path == root or path.startswith(root + "/") else path

        # WHY include_joint_transforms=False: the URDF's own static set already poses every joint at 0, and a second
        # static transform for the same child frame is an ERROR in the viewer (seen 2026-11-24); we log them all here
        _recolor(recording, list(ghost.stream(include_joint_transforms=False)), GHOST_RGBA, move)
        for joint in ghost.joints():
            value = float(values[joint.name][sample]) if joint.name in values else 0.0
            recording.log(f"{base}/joint_transforms/{viz.path_part(joint.name)}",
                          joint.compute_transform(value, clamp=False), static=True)
        recording.log(f"{base}/anchor", rr.Transform3D(parent_frame=tree.root_link().name,
                                                         child_frame=prefix + tree.root_link().name), static=True)


# ── the tool: whole path faint, a decaying bright trail, a frame + label at the cursor ──────────────────────


def _segments(points: np.ndarray) -> np.ndarray:
    return np.stack([points[:-1], points[1:]], axis=1)  # (N-1, 2, 3)


def _matrices(quaternions: np.ndarray) -> np.ndarray:
    """(N, 4) xyzw -> (N, 3, 3)."""
    x, y, z, w = np.asarray(quaternions, dtype=float).T
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], axis=1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], axis=1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], axis=1)], axis=1)


def tool_speed(seconds: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """|d position / dt| in m/s per sample (central differences)."""
    return np.linalg.norm(np.gradient(positions, seconds, axis=0), axis=1) if len(seconds) > 1 else np.zeros(len(seconds))


def _log_tool(recording: rr.RecordingStream, root_frame: str, seconds: np.ndarray, positions: np.ndarray,
              quaternions: np.ndarray, keys: np.ndarray, reach: float, flange: np.ndarray | None = None) -> np.ndarray:
    """/world/tool/{path,trail,now,axes,keyframes}, all in the URDF root link's frame; returns the tool speed (m/s).

    WHY every entity declares `root_frame`: Rerun 0.40 places the URDF in named frames (base_link_ur, ...); an entity
    left in its implicit tf#/world/tool frame was not drawn beside it at all (seen 2026-11-24). WHY the cursor point
    and triad are data, not a moving Transform3D: latest-at data needs no extra frame and follows the playhead."""
    speed = tool_speed(seconds, positions)
    top = max(float(speed.max()), 1e-9)
    rgb = _speed_rgb(speed / top)
    segments = _segments(positions)
    seg_rgb = rgb[1:]
    thin, thick = 0.003 * reach, 0.008 * reach
    where = rr.CoordinateFrame(root_frame)
    time = [rr.TimeColumn(TIMELINE, duration=seconds)]
    faint = np.c_[seg_rgb, np.full(len(seg_rgb), 110)].astype(np.uint8)
    recording.log("world/tool/path", where, rr.LineStrips3D(segments, colors=faint, radii=thin), static=True)
    recording.log("world/tool/trail", where, rr.LineStrips3D.from_fields(radii=thick), static=True)
    recording.send_columns("world/tool/trail", indexes=[rr.TimeColumn(TIMELINE, duration=seconds[1:])],
                           columns=rr.LineStrips3D.columns(strips=segments, colors=seg_rgb).partition([1] * len(segments)))
    labels = [f"{v * 1000:.0f} mm/s" for v in speed]  # the time is in the readout and the time panel
    recording.log("world/tool/now", where, rr.Points3D.from_fields(radii=0.014 * reach, show_labels=True), static=True)
    recording.send_columns("world/tool/now", indexes=time,
                           columns=rr.Points3D.columns(positions=positions, labels=labels, colors=rgb))
    axes = _matrices(quaternions).transpose(0, 2, 1) * (0.1 * reach)  # rows = the tool's x, y, z axes
    recording.log("world/tool/axes", where, rr.Arrows3D.from_fields(radii=0.0035 * reach), static=True)
    recording.send_columns("world/tool/axes", indexes=time,
                           columns=rr.Arrows3D.columns(origins=np.repeat(positions, 3, axis=0),
                                                       vectors=axes.reshape(-1, 3),
                                                       colors=np.tile([[230, 80, 70], [90, 190, 90], [80, 130, 230]],
                                                                      (len(seconds), 1))).partition([3] * len(seconds)))
    if flange is not None and np.nanmax(np.linalg.norm(flange - positions, axis=1)) > 0.01:
        # WHY a stick from the flange to the tool point: a URDF without its gripper leaves the tool point floating
        # 10-20 cm off the arm; the stick says which arm point it belongs to
        recording.log("world/tool/stick", where, rr.LineStrips3D.from_fields(radii=0.003 * reach, colors=[(110, 118, 132)]),
                      static=True)
        recording.send_columns("world/tool/stick", indexes=time,
                               columns=rr.LineStrips3D.columns(strips=np.stack([flange, positions], axis=1))
                               .partition([1] * len(seconds)))
    # WHY drop a keyframe's label within 4 % of the reach of one already labelled: on a short move the ghosts' tool
    # points bunch up and their labels overprinted each other (dev-003 still, 2026-11-24)
    labels, kept = [], []
    for k in keys:
        close = any(np.linalg.norm(positions[k] - positions[j]) < 0.04 * reach for j in kept)
        labels.append("" if close else f"{seconds[k]:.2f} s")
        if not close:
            kept.append(k)
    recording.log("world/tool/keyframes", where,
                  rr.Points3D(positions[keys], radii=0.007 * reach, colors=[(120, 130, 150)], labels=labels,
                              show_labels=True), static=True)
    return speed


# ── numbers at the cursor ─────────────────────────────────────────────────────────────────────────────────


def _limits(traj: JointTrajectory, tree: rru.UrdfTree) -> tuple[np.ndarray, np.ndarray]:
    """Each joint's [lo, hi] in rad: the trajectory's own JointLimits first, else the URDF's (NaN when unbounded)."""
    lo = np.full(len(traj.joint_names), np.nan)
    hi = np.full(len(traj.joint_names), np.nan)
    limits = traj.limits
    for i, name in enumerate(traj.joint_names):
        joint = tree.get_joint_by_name(name)
        if joint is not None and joint.joint_type in ("revolute", "prismatic") and joint.limit_upper > joint.limit_lower:
            lo[i], hi[i] = joint.limit_lower, joint.limit_upper
    if limits is not None and limits.min_position is not None and limits.max_position is not None:
        order = [list(limits.joint_names).index(n) for n in traj.joint_names]
        lo = np.where(np.isfinite(np.asarray(limits.min_position, dtype=float)[order]),
                      np.asarray(limits.min_position, dtype=float)[order], lo)
        hi = np.where(np.isfinite(np.asarray(limits.max_position, dtype=float)[order]),
                      np.asarray(limits.max_position, dtype=float)[order], hi)
    return lo, hi


def _bar(fraction: float, width: int = 12) -> str:
    if not np.isfinite(fraction):
        return "·" * width
    filled = int(round(np.clip(fraction, 0, 1) * width))
    return "█" * filled + "░" * (width - filled)


def _readouts(traj: JointTrajectory, seconds: np.ndarray, fraction: np.ndarray, speed_mps: np.ndarray,
              top_speed: float) -> list[str]:
    q = np.degrees(np.asarray(traj.positions, dtype=float))
    qd = None if traj.velocities is None else np.degrees(np.asarray(traj.velocities, dtype=float))
    names = [_short(n) for n in traj.joint_names]
    docs = []
    for i, s in enumerate(seconds):
        rows = [f"**t = {s:.2f} s** of {seconds[-1]:.2f} s · tool **{speed_mps[i] * 1000:.0f} mm/s** "
                f"(top {top_speed * 1000:.0f})",
                "",
                "| joint | angle | between its limits | speed |",
                "|:--|--:|:--|--:|"]
        for j, name in enumerate(names):
            f = fraction[i, j]
            flag = " ⚠" if np.isfinite(f) and (f < NEAR_LIMIT or f > 1 - NEAR_LIMIT) else ""
            used = f"`{_bar(f)}` {f * 100:3.0f} %{flag}" if np.isfinite(f) else "no limits"
            speed = "" if qd is None else f"{qd[i, j]:+.0f} °/s"
            rows.append(f"| {j + 1} {name} | {q[i, j]:+.1f}° | {used} | {speed} |")
        docs.append("\n".join(rows))
    return docs


def _log_numbers(recording: rr.RecordingStream, traj: JointTrajectory, name: str, seconds: np.ndarray,
                 lo: np.ndarray, hi: np.ndarray, speed_mps: np.ndarray) -> None:
    q = np.asarray(traj.positions, dtype=float)
    fraction = (q - lo) / np.where(hi > lo, hi - lo, np.nan)
    docs = _readouts(traj, seconds, fraction, speed_mps, float(speed_mps.max()))
    recording.send_columns(f"readout/{name}", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                           columns=rr.TextDocument.columns(text=docs, media_type=["text/markdown"] * len(docs)))
    abscissa = np.arange(1, len(traj.joint_names) + 1, dtype=float)
    # WHY a static 100 % bar behind every joint: it pins the axis at 0-100 (an autoscaled axis jumped while scrubbing)
    # and turns each bar into a gauge between the joint's two limits
    recording.log("range/limits", rr.BarChart(np.where(np.isfinite(fraction[0]), 100.0, 0.0), abscissa=abscissa,
                                              color=RANGE_RGBA), static=True)
    for i, s in enumerate(seconds):
        recording.set_time(TIMELINE, duration=float(s))
        recording.log(f"range/{name}", rr.BarChart(np.nan_to_num(fraction[i] * 100.0), abscissa=abscissa,
                                                   color=(120, 170, 220)))
    recording.reset_time()


def _log_series(recording: rr.RecordingStream, traj: JointTrajectory, name: str, seconds: np.ndarray,
                speed_mps: np.ndarray) -> None:
    """q / qd / qdd via robot_msgs' own logger (degrees), then one colour + readable name per joint."""
    viz.log(traj, name, recording=recording, degrees=True)
    viz._PATHS.pop(id(recording), None)  # WHY: we send our own blueprint, not robot_msgs' default one
    for j, joint in enumerate(traj.joint_names):
        color = JOINT_COLORS[j % len(JOINT_COLORS)]
        for field in ("positions", "velocities", "accelerations"):
            if getattr(traj, field) is not None:
                recording.log(f"{field}/{viz.path_part(joint)}/{viz.path_part(name)}",
                              rr.SeriesLines(names=_short(joint), colors=color, widths=1.5), static=True)
    recording.log(f"speed/tool/{name}", rr.SeriesLines(names="tool speed", colors=(200, 210, 225), widths=1.5),
                  static=True)
    recording.send_columns(f"speed/tool/{name}", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                           columns=rr.Scalars.columns(scalars=speed_mps * 1000.0))


# ── the camera and the layout ────────────────────────────────────────────────────────────────────────────


def _eye(links: dict[str, tuple[np.ndarray, np.ndarray]], tool: np.ndarray) -> tuple[rrb.EyeControls3D, float]:
    """A camera on the whole swept arm (every link origin over the motion + the tool path), from the tool's side.

    WHY (grown from traj_compare's _stage_eye): the arm, not the path, is the subject; looking from ~55° beside the
    tool's mean bearing shows the arm in profile with the tool in front of the base rather than hidden behind it."""
    cloud = np.vstack([p for _, p in links.values()] + [tool])
    cloud = cloud[np.all(np.isfinite(cloud), axis=1)]
    low, high = cloud.min(axis=0), cloud.max(axis=0)
    look = 0.5 * (low + high)
    radius = float(np.linalg.norm(cloud - look, axis=1).max()) + 0.15  # link origins + ~the links' own thickness
    bearing = np.arctan2(tool[:, 1].mean(), tool[:, 0].mean()) - np.radians(55)
    elevation = np.radians(24)
    direction = np.array([np.cos(bearing) * np.cos(elevation), np.sin(bearing) * np.cos(elevation), np.sin(elevation)])
    eye = rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1], position=look + 2.05 * radius * direction)
    return eye, radius


def _blueprint(traj: JointTrajectory, robot_name: str, name: str, eye: rrb.EyeControls3D, duration: float,
               top_speed: float, playing: bool = True) -> rrb.Blueprint:
    trail = rrb.VisibleTimeRanges(timeline=TIMELINE, start=rrb.TimeRangeBoundary.cursor_relative(seconds=-DECAY_S),
                                  end=rrb.TimeRangeBoundary.cursor_relative(seconds=0.0))
    stage = rrb.Spatial3DView(
        origin="/", contents=["/world/**"],
        name=f"{robot_name} · {name} · {duration:.2f} s — tool path coloured by speed (blue slow → yellow "
             f"{top_speed * 1000:.0f} mm/s), last {DECAY_S:g} s bright, faint arms at {GHOSTS} instants",
        eye_controls=eye, line_grid=rrb.LineGrid3D(visible=True, spacing=0.1, color=(90, 90, 90, 90)),
        overrides={"/world/tool/trail": trail})

    def plot(origin: str, title: str) -> rrb.TimeSeriesView:
        return rrb.TimeSeriesView(origin=origin, name=title, axis_x=rrb.TimeAxis(link="LinkToGlobal"),
                                  plot_legend=rrb.PlotLegend(corner="LeftTop", visible=True))

    strip = rrb.Tabs(plot("/positions", "q [°] — every joint"), plot("/velocities", "qd [°/s] — every joint"),
                     plot("/speed", "tool speed [mm/s]"), active_tab=0, name="over time")
    side = rrb.Vertical(rrb.TextDocumentView(origin="/readout", name="at the playhead"),
                        rrb.BarChartView(origin="/range", name=f"% of range · joints 1-{len(traj.joint_names)} as above",
                                         plot_legend=rrb.PlotLegend(visible=False)),
                        row_shares=[5, 4])
    return rrb.Blueprint(
        rrb.Vertical(rrb.Horizontal(stage, side, column_shares=[3, 1]), strip, row_shares=[3, 1]),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        # WHY playing + looping by default (robot first: on open the arm moves and its decaying trail follows it);
        # playing=False opens paused at 0 s, for stills (shoot.cjs --duration clicks the scrub bar, exact only when
        # paused; the 0.40 web viewer ignored #when=t@<s> either way, measured 2026-11-24)
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="playing", loop_mode="All") if playing
        else rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused"),
        collapse_panels=False,
    )


# ── the entry point ──────────────────────────────────────────────────────────────────────────────────────


def save(path: str | Path, traj: JointTrajectory, robot: str | Path, tool: PoseTrajectory | None = None, *,
         name: str = "target", ghosts: int = GHOSTS, playing: bool = True) -> Path:
    """Write `traj` with its robot to an .rrd: the R4 proposal for robot_msgs' stock JointTrajectory viewer.

    ``robot`` is the URDF path (its joint names match ``traj.joint_names``); ``tool`` is the tool's poses in the URDF
    root frame (default: the flange's, from the URDF's own forward kinematics); ``name`` is robot_msgs' series name;
    ``ghosts`` how many faint frozen arms (0: none); ``playing`` False opens paused at 0 s instead of looping."""
    urdf = Path(robot)
    seconds = np.asarray(traj.t, dtype=float) - float(traj.t[0])
    samples = len(seconds)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # WHY: limits are shown, not enforced; clamp=False must not spam
        tree = rru.UrdfTree.from_file_path(urdf)
        values = _joint_values(tree, traj)
        links = _forward(tree, values, samples)
        if tool is None:
            r, p = links[_flange(tree, traj)]
            tool_t, tool_p, tool_q = seconds, p, _quat_xyzw(r)
        else:
            tool_t = np.asarray(tool.t, dtype=float) - float(traj.t[0])
            tool_p = np.asarray(tool.positions, dtype=float)
            tool_q = np.asarray(tool.orientations, dtype=float)
        keys = np.unique(np.round(np.linspace(0, samples - 1, max(ghosts, 2))).astype(int))
        tool_keys = np.searchsorted(tool_t, seconds[keys]).clip(0, len(tool_t) - 1)
        eye, radius = _eye(links, tool_p)
        reach = max(radius, 0.3)
        top = float(tool_speed(tool_t, tool_p).max())
        recording = rr.RecordingStream(APPLICATION_ID)
        # WHY the blueprint first (default_blueprint=): sent after the data, a paused TimePanel pinned the playhead at
        # the first chunk's time (+0.1 s) and ignored the link's #when=t@<s> (seen in the real viewer 2026-11-24)
        recording.save(str(path), default_blueprint=_blueprint(traj, tree.name, name, eye, float(seconds[-1]), top,
                                                               playing))
        speed_on_traj = np.interp(seconds, tool_t, tool_speed(tool_t, tool_p))
        _log_series(recording, traj, name, seconds, speed_on_traj)
        _log_numbers(recording, traj, viz.path_part(name), seconds, *_limits(traj, tree), speed_on_traj)
        flange = None if tool is None else np.array([np.interp(tool_t, seconds, links[_flange(tree, traj)][1][:, axis])
                                                      for axis in range(3)]).T
        _log_tool(recording, tree.root_link().name, tool_t, tool_p, tool_q, tool_keys, reach, flange)
        _log_robot(recording, urdf, values, seconds)
        if ghosts:
            _log_ghosts(recording, urdf, tree, values, keys)
    recording.flush()
    recording.disconnect()
    return Path(path)


# ── the round's inputs ───────────────────────────────────────────────────────────────────────────────────


def load(task: str) -> tuple[JointTrajectory, PoseTrajectory]:
    """The round's npz -> a robot_msgs JointTrajectory (+ the dataset's tool poses as a PoseTrajectory)."""
    data = np.load(ROUND / "data" / f"{task}.npz")
    names = tuple(str(n) for n in data["names"])
    q = np.asarray(data["q"], dtype=float)
    traj = JointTrajectory(
        t=np.asarray(data["t"], dtype=float), joint_names=names, positions=q,
        velocities=np.asarray(data["qd"], dtype=float) if data["qd"].size else None,
        accelerations=np.asarray(data["qdd"], dtype=float) if data["qdd"].size else None,
        limits=JointLimits(joint_names=names, min_position=data["lo"], max_position=data["hi"],
                           max_velocity=data["vmax"], max_acceleration=data["amax"]))
    tool = PoseTrajectory(t=np.asarray(data["t"], dtype=float), positions=np.asarray(data["tool_xyz"], dtype=float),
                          orientations=_quat_xyzw(data["tool_rot"]))
    return traj, tool


def main() -> None:
    urdf = ROUND / "data" / "robot" / "ur5e_collision.urdf"
    for task in ("workspace-dev-029", "workspace-dev-003"):
        traj, tool = load(task)
        out = save(HERE / f"{task}.rrd", traj, urdf, tool, name="target")
        print(out, f"{out.stat().st_size / 1e6:.2f} MB")
        # the same recording opening paused, for the round's stills (shoot.cjs --duration lands exactly only when paused)
        (HERE / "paused").mkdir(exist_ok=True)
        print(save(HERE / "paused" / f"{task}.rrd", traj, urdf, tool, name="target", playing=False))


if __name__ == "__main__":
    main()
