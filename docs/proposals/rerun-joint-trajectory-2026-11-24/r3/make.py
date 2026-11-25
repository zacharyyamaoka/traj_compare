#!/usr/bin/env python3
"""R3 · Solo Run Dashboard, one screen — how a robot_msgs JointTrajectory looks in Rerun 0.40 (babble, 2026-11-24).

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r3/make.py

One function, `save(path, traj, robot=urdf, tool=tcp)`: a JointTrajectory + its robot's URDF (+ an optional tool
PoseTrajectory) → one .rrd whose embedded blueprint answers "what does this whole motion look like, at a glance".
Everything on one screen, no tabs (grown from the Nov 19 Rerun run-view pick "Q2 Solo run dashboard", builder
/home/bam/traj_compare/docs/layout_proposals_2026-11-19/rerun/build_rerun_variants.py `q2`):

    ┌──────────────────────────────────┬────────────────────┐
    │ 3D, ~60 %: the URDF arm moving,   │ joint 1 q [°] strip │
    │ framed on its whole motion;       │ joint 2 …           │
    │ faint ghosts at the start and end │ …                   │
    │ poses; the tool path: travelled   │ joint N             │
    │ part solid, the rest faint        │ tool speed [mm/s]   │
    └──────────────────────────────────┴────────────────────┘
    time bar (paused at the start; play loops)

Entity layout = robot_msgs.viz.rerun's (`/<field>/<column>/<name>` series, `/world/<name>/...` spatial), so this grows
into that module as `log(traj, name, recording=, robot=…, tool=…)` plus a dashboard blueprint:

    /positions|velocities|accelerations/<joint>/<name>   the stock logger's series (degrees for revolute joints)
    /positions/<joint>/lower_limit, upper_limit          the joint's position limits, same units
    /tool/speed_mm_s/<name>                              |d tool / dt|
    /world/<name>/robot/...                              the URDF (Rerun's own loader), its joints on the t timeline
    /world/<name>/ghost_start/..., ghost_end/...         the same URDF again, posed statically, faint
    /world/<name>/tool/trail | path | ends               the travelled tool path, the rest of it, start/end labels
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
import rerun.urdf as rurdf
from robot_msgs.geometry.rotations import euler_to_matrix, quat_from_axis_angle, quat_from_matrix, quat_to_matrix
from robot_msgs.std.header import Header
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as stock

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
APPLICATION_ID = "robot_msgs-joint-trajectory-r3-solo-run"
TIMELINE = stock.TIMELINE  # "t", seconds from the first sample
DEG = 180.0 / np.pi

# Colours. WHY calm: one ink colour for every joint line (the strip's title names the joint), grey limits, and the
# one accent (Solo Run's orange, #f08c00) for the tool, so nothing reads as an alarm (Zach: amber/red only for problems).
INK = (37, 99, 160)
LIMIT = (150, 150, 150)
ACCENT = (240, 140, 0)
PATH_FAINT = (250, 208, 160)  # WHY opaque: a line with alpha drew darker (brown), not fainter, in the 0.40 viewer
ARM = (175, 180, 190, 255)  # a neutral steel, so the faint ghosts read against it on a white background
GHOST_START = (90, 140, 230, 60)
GHOST_END = (240, 150, 60, 60)
LABEL_START = (90, 140, 230)
LABEL_END = (220, 120, 20)

DISTANCE_RADII = 2.35  # camera distance in radii of the motion's bounding box: fits Rerun's default field of view
# The tool path is two polylines per instant (travelled, still to go): at most this many instants × vertices each,
# so a 10 000-sample trajectory stays a few MB; between instants the latest one holds
TRAIL_ROWS, TRAIL_VERTICES = 400, 256


# ── the robot: Rerun's URDF loader, re-rooted under /world/<name>/ ─────────────────────────────────────────────────


@dataclass
class Robot:
    """One URDF, loaded once per copy (the moving arm and each ghost): Rerun's own loader does the meshes."""

    path: Path
    tree: Any  # rerun.urdf.UrdfTree, for the joint list and transforms

    @property
    def name(self) -> str:
        return self.tree.name

    @property
    def root(self) -> str:
        return self.tree.root_link().name

    def links(self) -> list[str]:
        return [self.root, *[joint.child_link for joint in self.tree.joints()]]


def _copy(urdf: Path, recording: rr.RecordingStream, entity: str, frame_prefix: str, *, joint_transforms: bool) -> Any:
    """Log one copy of the URDF at ``entity`` (meshes + static transforms), its frames prefixed with ``frame_prefix``.

    WHY re-path the loader's chunks: `UrdfTree.from_file_path(entity_path_prefix=…)` takes ONE path segment (slashes are
    escaped), so it cannot put the robot at robot_msgs' `/world/<name>/...`; the loader's own chunks are moved there
    instead (`stream().map(Chunk.with_entity_path)`), meshes and all, untouched otherwise.
    WHY a mount transform: the loader's frames hang off the URDF's root link, which nothing connects to the view; one
    identity edge from `tf#/world/<name>` (the entity's implicit frame) to the root link puts the robot in the scene."""

    tree = rurdf.UrdfTree.from_file_path(urdf, frame_prefix=frame_prefix or None)
    old_root = f"/{tree.name}"

    def move(chunk: Any) -> Any:
        path = chunk.entity_path
        if path == "/tf_static":
            return chunk.with_entity_path(f"{entity}/tf_static")
        return chunk.with_entity_path(entity + path[len(old_root):])

    recording.send_chunks(tree.stream(include_joint_transforms=joint_transforms).map(move))
    parent = "tf#" + entity.rsplit("/", 1)[0]
    recording.log(f"{entity}/mount", rr.Transform3D(parent_frame=parent, child_frame=frame_prefix + tree.root_link().name),
                  static=True)
    return tree


def _geometry_paths(tree: Any, entity: str) -> list[str]:
    old_root = f"/{tree.name}"
    out = []
    for link in [tree.root_link().name, *[joint.child_link for joint in tree.joints()]]:
        for path in [*tree.get_visual_geometry_paths(link), *tree.get_collision_geometry_paths(link)]:
            out.append(entity + path[len(old_root):])
    return list(dict.fromkeys(out))


def _joint_values(tree: Any, traj: JointTrajectory) -> dict[str, np.ndarray]:
    """Every URDF joint the trajectory moves (directly, or as a mimic of one), its value at each sample (rad or m)."""

    q = np.asarray(traj.positions, dtype=np.float64)
    names = [str(name) for name in traj.joint_names]
    values = {name: q[:, index] for index, name in enumerate(names)}
    for joint in tree.joints():
        mimic = joint.mimic
        if mimic is not None and mimic.joint in values and joint.name not in values:
            values[joint.name] = mimic.multiplier * values[mimic.joint] + mimic.offset
    return values


def _forward_kinematics(tree: Any, values: dict[str, np.ndarray], samples: int) -> dict[str, np.ndarray]:
    """Every link's pose in the root link's frame, ``(samples, 4, 4)``: for framing the camera and the flange path.

    WHY our own and not Rerun's: Rerun computes link poses inside the viewer only; the camera and the default tool path
    are set before anything is drawn. Built from the URDF's own joint origins/axes via robot_msgs' rotations."""

    poses = {tree.root_link().name: np.broadcast_to(np.eye(4), (samples, 4, 4))}
    pending = list(tree.joints())
    while pending:
        progressed = False
        for joint in list(pending):
            if joint.parent_link not in poses:
                continue
            origin = np.eye(4)
            origin[:3, :3] = euler_to_matrix(*joint.origin_rpy)
            origin[:3, 3] = joint.origin_xyz
            motion = np.broadcast_to(np.eye(4), (samples, 4, 4)).copy()
            value = values.get(joint.name)
            if value is not None and joint.joint_type in ("revolute", "continuous"):
                motion[:, :3, :3] = quat_to_matrix(quat_from_axis_angle(np.asarray(joint.axis), value))
            elif value is not None and joint.joint_type == "prismatic":
                motion[:, :3, 3] = np.asarray(joint.axis)[None, :] * value[:, None]
            poses[joint.child_link] = poses[joint.parent_link] @ origin @ motion
            pending.remove(joint)
            progressed = True
        if not progressed:
            raise ValueError(f"URDF joints not connected to the root link: {[joint.name for joint in pending]}")
    return poses


def _tip_link(tree: Any, traj: JointTrajectory) -> str:
    """The link the last trajectory joint carries, followed down fixed joints to a leaf (the flange, tool0, ...)."""

    last = tree.get_joint_by_name(str(traj.joint_names[-1]))
    link = last.child_link
    while True:
        children = [joint for joint in tree.joints() if joint.parent_link == link and joint.joint_type == "fixed"]
        if len(children) != 1:
            return link
        link = children[0].child_link


# ── the plan: everything the logger and the blueprint need, computed once ─────────────────────────────────────


@dataclass
class Strip:
    """One small plot of the right-hand column."""

    title: str
    contents: list[str]
    y_range: tuple[float, float]


@dataclass
class Plan:
    """A JointTrajectory + its robot, worked out: what to log where, and how the dashboard frames it."""

    name: str  # the legend text
    part: str  # its entity-path segment
    urdf: Path
    seconds: np.ndarray  # t from the first sample
    revolute: list[str]  # the joints shown in degrees
    values: dict[str, np.ndarray]  # every URDF joint the trajectory moves (rad / m)
    limits: dict[str, tuple[float, float]]  # display units, NaN = none
    strips: list[Strip]
    tool_t: np.ndarray
    tool_xyz: np.ndarray  # in tool_frame
    tool_frame: str  # a URDF link
    tool_label: str
    speed_mm_s: np.ndarray
    eye: Any
    title: str


def _limits(tree: Any, traj: JointTrajectory) -> tuple[np.ndarray, np.ndarray]:
    """Position limits per trajectory joint: the message's own JointLimits first, else the URDF's (NaN = none)."""

    names = [str(name) for name in traj.joint_names]
    low = np.full(len(names), np.nan)
    high = np.full(len(names), np.nan)
    limits: JointLimits | None = traj.limits
    if limits is not None:
        by_name = {str(name): index for index, name in enumerate(limits.joint_names)}
        for index, name in enumerate(names):
            if name in by_name:
                if limits.min_position is not None:
                    low[index] = np.asarray(limits.min_position, dtype=float)[by_name[name]]
                if limits.max_position is not None:
                    high[index] = np.asarray(limits.max_position, dtype=float)[by_name[name]]
    for index, name in enumerate(names):
        joint = tree.get_joint_by_name(name)
        if joint.joint_type in ("revolute", "prismatic") and joint.limit_lower < joint.limit_upper:
            low[index] = joint.limit_lower if np.isnan(low[index]) else low[index]
            high[index] = joint.limit_upper if np.isnan(high[index]) else high[index]
    return low, high


def _nice(step: float) -> float:
    exponent = 10.0 ** np.floor(np.log10(step))
    return next(m * exponent for m in (1.0, 2.0, 5.0, 10.0) if m * exponent >= step)


def _strip_range(values: np.ndarray, low: float, high: float) -> tuple[float, float]:
    """The y range of a joint's strip: its motion padded, stretched to a limit only when that limit is close, snapped
    outward to round numbers.

    WHY not always to the limits: the UR5e's are ±360°, so a 60° move would be a flat line in a strip this small; the
    title carries the distance to the nearest limit instead, and a limit within one motion span is pulled into view as
    its grey line. WHY snapped: a ~90 px plot gets ticks 50 or 100 apart, and a range like 14…96 holds none, so the
    strip showed no numbers at all (first shots, elbow)."""

    vmin, vmax = float(values.min()), float(values.max())
    span = max(vmax - vmin, 1e-9)
    lo, hi = vmin - 0.08 * span, vmax + 0.08 * span
    if np.isfinite(low) and vmin - low <= span:
        lo = min(lo, low)
    if np.isfinite(high) and high - vmax <= span:
        hi = max(hi, high)
    return _snap(lo, hi)


def _snap(lo: float, hi: float) -> tuple[float, float]:
    """Outward to round numbers, then 6 % air, so no tick label sits on the edge (it overprinted the time axis's +0s)."""

    step = _nice(max(hi - lo, 1e-9) / 2.0)
    lo, hi = float(np.floor(lo / step) * step), float(np.ceil(hi / step) * step)
    air = 0.06 * (hi - lo)
    return lo - air, hi + air


def _eye(points: np.ndarray) -> Any:
    """A camera on the whole motion: the arm seen in profile, from above, z up.

    Profile = looking across the main horizontal direction of everything that moves (link origins + tool path), from
    the side nearer traj_compare's front-right default, nudged towards it. WHY not that fixed front-right: a UR5e
    pointing along it is seen end-on, foreshortened into a blob (the A-to-B's first framing); in profile the elbow and
    wrist read as angles. WHY not from the tool's side: the arm then reaches at the camera and fills the view.
    A fixed elevation, so every trajectory opens from a familiar height."""

    points = points[np.all(np.isfinite(points), axis=1)]
    low, high = points.min(axis=0), points.max(axis=0)
    look = 0.5 * (low + high)
    radius = 0.5 * float(np.linalg.norm(high - low))
    front = np.array([1.5, -1.9, 0.0]) / np.linalg.norm([1.5, -1.9])
    direction = front.copy()
    xy = points[:, :2] - points[:, :2].mean(axis=0)
    if len(xy) > 2 and np.ptp(xy, axis=0).max() > 1e-3:
        _, _, vt = np.linalg.svd(xy, full_matrices=False)
        across = np.array([-vt[0, 1], vt[0, 0], 0.0])
        across = across if across @ front >= 0 else -across
        direction = across + 0.4 * front
    direction = direction / np.linalg.norm(direction[:2])
    direction[2] = 0.55  # ~29° above the horizon
    direction = direction / np.linalg.norm(direction)
    distance = DISTANCE_RADII * max(radius, 0.1)  # a 1-DOF rig's link origins span centimetres
    return rrb.EyeControls3D(kind="Orbital", look_target=look.tolist(), eye_up=[0.0, 0.0, 1.0],
                             position=(look + distance * direction).tolist())


def plan(traj: JointTrajectory, name: str, robot: str | Path, tool: PoseTrajectory | None = None) -> Plan:
    urdf = Path(robot).resolve()
    tree = rurdf.UrdfTree.from_file_path(urdf)
    names = [str(joint) for joint in traj.joint_names]
    missing = [joint for joint in names if tree.get_joint_by_name(joint) is None]
    if missing:
        raise ValueError(f"{urdf.name} has no joints named {missing}")
    revolute = [joint for joint in names if tree.get_joint_by_name(joint).joint_type in ("revolute", "continuous")]
    t = np.asarray(traj.t, dtype=np.float64)
    seconds = t - t[0]
    values = _joint_values(tree, traj)
    part = stock.path_part(name)

    # the strips: one per joint, in what robot_msgs' degrees= logged (degrees for revolute, SI otherwise)
    low, high = _limits(tree, traj)
    q = np.asarray(traj.positions, dtype=np.float64)
    strips, limits = [], {}
    for index, joint in enumerate(names):
        scale, unit = (DEG, "°") if joint in revolute else (1.0, " m")
        shown, lo, hi = q[:, index] * scale, low[index] * scale, high[index] * scale
        limits[joint] = (lo, hi)
        joint_part = stock.path_part(joint)
        contents = [f"/positions/{joint_part}/{part}",
                    *[f"/positions/{joint_part}/{side}" for side, bound in (("lower_limit", lo), ("upper_limit", hi))
                      if np.isfinite(bound)]]
        digits = 0 if joint in revolute else 3
        title = f"{joint} [{unit.strip()}] · travel {np.ptp(shown):.{digits}f}{unit}"
        gaps = [gap for gap in (shown.min() - lo, hi - shown.max()) if np.isfinite(gap)]
        if gaps:
            headroom = min(gaps)
            word = "to limit" if headroom >= 0 else "PAST limit"
            title += f" · {abs(headroom):.{digits}f}{unit} {word}"
        strips.append(Strip(title, contents, _strip_range(shown, lo, hi)))

    # the tool: the given TCP path, else the flange's from the URDF; its speed is the last strip
    links = _forward_kinematics(tree, values, len(t))
    root = tree.root_link().name
    if tool is not None:
        tool_t = np.asarray(tool.t, dtype=np.float64) - t[0]
        tool_xyz = np.asarray(tool.positions, dtype=np.float64)
        tool_frame = tool.header.frame_id if tool.header.frame_id in links else root
        tool_label = tool.child_frame_id or "tool"
    else:
        tool_label = _tip_link(tree, traj)
        tool_t, tool_xyz, tool_frame = seconds, links[tool_label][:, :3, 3], root
    speed = np.linalg.norm(np.gradient(tool_xyz, tool_t, axis=0), axis=1) * 1000.0
    peak = int(np.argmax(speed))
    strips.append(Strip(f"{tool_label} speed [mm/s] · peak {speed[peak]:.0f} at {tool_t[peak]:.2f} s",
                        [f"/tool/speed_mm_s/{part}"], _snap(0.0, max(float(speed.max()), 1.0))))

    # the camera: every link origin at every sample, and the tool path (in the root frame; framing only)
    mount = links[tool_frame][0] if tool_frame != root else np.eye(4)
    tool_root = tool_xyz @ mount[:3, :3].T + mount[:3, 3]
    cloud = np.vstack([*(pose[:, :3, 3] for pose in links.values()), tool_root])
    length = float(np.linalg.norm(np.diff(tool_xyz, axis=0), axis=1).sum())
    title = (f"{name} · {tree.name} · {seconds[-1]:.2f} s · {tool_label} path {length:.2f} m"
             " · ghosts: blue = start, orange = end")
    return Plan(name=name, part=part, urdf=urdf, seconds=seconds, revolute=revolute, values=values, limits=limits,
                strips=strips, tool_t=tool_t, tool_xyz=tool_xyz, tool_frame=tool_frame, tool_label=tool_label,
                speed_mm_s=speed, eye=_eye(cloud), title=title)


# ── the logger ──────────────────────────────────────────────────────────────────────────────────────────────────


def log(traj: JointTrajectory, name: str, *, recording: rr.RecordingStream, robot: str | Path,
        tool: PoseTrajectory | None = None) -> Plan:
    """Log one JointTrajectory with its robot: the stock series + limits, the URDF arm on the t timeline, two ghosts,
    the tool path and speed. ``tool`` is the TCP's PoseTrajectory (its ``header.frame_id`` a URDF link, default the
    root link); without it the path is the flange's, from the URDF."""

    p = plan(traj, name, robot, tool)
    part, seconds = p.part, p.seconds

    # 1. the stock series: robot_msgs' own logger, degrees for the revolute joints (Zach's rule; the message stays SI)
    stock.log(traj, part, recording=recording, degrees=p.revolute, color=INK, label=name)
    stock._PATHS.pop(id(recording), None)  # the dashboard below replaces the stock blueprint

    # 2. limits: two grey lines per joint, in the units the strip shows
    ends = rr.TimeColumn(TIMELINE, duration=[seconds[0], seconds[-1]])
    for joint, bounds in p.limits.items():
        for side, bound in zip(("lower_limit", "upper_limit"), bounds, strict=True):
            if np.isfinite(bound):
                entity = f"/positions/{stock.path_part(joint)}/{side}"
                recording.log(entity, rr.SeriesLines(colors=[LIMIT], widths=[1.0], names=[side.replace("_", " ")]),
                              static=True)
                recording.send_columns(entity, indexes=[ends], columns=rr.Scalars.columns(scalars=[bound, bound]))

    # 3. the arm: Rerun's URDF loader, every joint on the t timeline
    base = f"/world/{part}"
    arm = _copy(p.urdf, recording, f"{base}/robot", f"{part}/", joint_transforms=True)
    for joint in arm.joints():
        if joint.name in p.values and joint.joint_type != "fixed":
            recording.send_columns(f"{base}/robot/joint_transforms/{stock.path_part(joint.name)}",
                                   indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                                   columns=joint.compute_transform_columns(p.values[joint.name].tolist(), clamp=False))
    for path in _geometry_paths(arm, f"{base}/robot"):
        recording.log(path, rr.Asset3D.from_fields(albedo_factor=ARM), static=True)

    # 4. the ghosts: the same URDF twice more, every joint posed statically at the first / last sample, faint
    for ghost, sample, colour in (("ghost_start", 0, GHOST_START), ("ghost_end", -1, GHOST_END)):
        entity = f"{base}/{ghost}"
        tree = _copy(p.urdf, recording, entity, f"{part}/{ghost}/", joint_transforms=False)
        for joint in tree.joints():
            value = float(p.values[joint.name][sample]) if joint.name in p.values else 0.0
            recording.log(f"{entity}/joint_transforms/{stock.path_part(joint.name)}",
                          joint.compute_transform(value, clamp=False), static=True)
        for path in _geometry_paths(tree, entity):
            recording.log(path, rr.Asset3D.from_fields(albedo_factor=colour), static=True)

    # 5. the tool, in its own frame: at every instant the travelled part solid (start → now) and the rest faint
    #    (now → end), so the whole path is always there; start / end labelled.
    #    WHY two polylines per instant, latest-at: one static faint path under a solid trail z-fought into beads (lines
    #    are camera-facing quads at the same depth), and one segment per sample shown over a growing time range dropped
    #    the ghosts' colours (a view-wide range query). Latest-at needs nothing from the blueprint either.
    frame = rr.CoordinateFrame(f"{part}/{p.tool_frame}")
    xyz = p.tool_xyz
    last = len(xyz) - 1
    rows = np.unique(np.linspace(0, last, min(last + 1, TRAIL_ROWS)).round().astype(int))

    def thin(first: int, end: int) -> np.ndarray:
        return xyz[np.unique(np.linspace(first, end, min(end - first + 1, TRAIL_VERTICES)).round().astype(int))]

    at = [rr.TimeColumn(TIMELINE, duration=p.tool_t[rows])]
    for entity, colour, radius, strips in (
        ("path", PATH_FAINT, 0.003, [thin(row, last) for row in rows]),
        ("trail", ACCENT, 0.005, [thin(0, row) for row in rows]),
    ):
        recording.log(f"{base}/tool/{entity}", rr.LineStrips3D.from_fields(colors=[colour], radii=[radius]), frame,
                      static=True)
        recording.send_columns(f"{base}/tool/{entity}", indexes=at, columns=rr.LineStrips3D.columns(strips=strips))
    recording.log(f"{base}/tool/ends", rr.Points3D([xyz[0], xyz[-1]], labels=["start", "end"],
                                                    colors=[LABEL_START, LABEL_END], radii=[0.009]), frame, static=True)
    speed = f"/tool/speed_mm_s/{part}"
    recording.log(speed, rr.SeriesLines(colors=[ACCENT], widths=[1.6], names=[f"{p.tool_label} speed"]), static=True)
    recording.send_columns(speed, indexes=[rr.TimeColumn(TIMELINE, duration=p.tool_t)],
                           columns=rr.Scalars.columns(scalars=p.speed_mm_s))
    return p


# ── the dashboard ───────────────────────────────────────────────────────────────────────────────────────────────


def blueprint(p: Plan) -> rrb.Blueprint:
    """One screen, no tabs: the arm ~60 % on the left, one small plot per joint (+ tool speed) stacked on the right.

    WHY no tabs (Solo Run's container decision, Nov 19): the question is "what does this whole motion look like" — every
    answer must be on screen at once; a tab hides half of it."""

    world = rrb.Spatial3DView(
        origin="/", contents=[f"/world/{p.part}/**"], name=p.title, eye_controls=p.eye,
    )
    strips = [
        rrb.TimeSeriesView(origin="/", contents=strip.contents, name=strip.title,
                           plot_legend=rrb.PlotLegend(visible=False),
                           axis_x=rrb.TimeAxis(link="LinkToGlobal"),  # zoom one strip, they all follow
                           axis_y=rrb.ScalarAxis(range=strip.y_range, zoom_lock=False))
        for strip in p.strips
    ]
    return rrb.Blueprint(
        rrb.Horizontal(world, rrb.Vertical(*strips), column_shares=[3, 2]),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        # WHY paused + written first: the viewer opens on the start pose, not wherever loading left the playhead (a
        # blueprint sent last let it play ~0.1 s first); play loops the whole motion
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused", loop_mode="all"),
        collapse_panels=False,
    )


def save(path: str | Path, traj: JointTrajectory, *, robot: str | Path, tool: PoseTrajectory | None = None,
         name: str = "JointTrajectory", application_id: str = APPLICATION_ID) -> Path:
    """The proposal's entry point: a JointTrajectory + its URDF (+ the TCP's PoseTrajectory) → one .rrd, dashboard
    embedded. Proposed robot_msgs form: ``robot_msgs.viz.rerun.save(path, traj, robot=urdf, tool=tcp)`` /
    ``traj.show(robot=urdf, tool=tcp)``."""

    path = Path(path)
    stream = rr.RecordingStream(application_id)
    stream.save(str(path), default_blueprint=blueprint(plan(traj, name, robot, tool)))
    log(traj, name, recording=stream, robot=robot, tool=tool)
    stream.flush()
    stream.disconnect()
    return path


# ── the round's two trajectories ────────────────────────────────────────────────────────────────────────────────


def load(task: str) -> tuple[JointTrajectory, PoseTrajectory]:
    """data/<task>.npz → the robot_msgs messages the entry point takes (the npz is just this round's carrier)."""

    data = np.load(ROUND / "data" / f"{task}.npz")
    names = tuple(str(name) for name in data["names"])
    limits = JointLimits(joint_names=names, min_position=data["lo"], max_position=data["hi"],
                         max_velocity=data["vmax"], max_acceleration=data["amax"])
    traj = JointTrajectory(t=data["t"], joint_names=names, positions=data["q"],
                           velocities=data["qd"] if data["qd"].size else None,
                           accelerations=data["qdd"] if data["qdd"].size else None, limits=limits)
    # the dataset's TCP is in the UR base frame, which is this URDF's root link (checked: flange orientation matches
    # to 1e-8; the TCP sits a constant ~145 mm out along the flange's z)
    tool = PoseTrajectory(t=data["t"], positions=data["tool_xyz"], orientations=quat_from_matrix(data["tool_rot"]),
                          header=Header(frame_id="base_link_ur"), child_frame_id="tool")
    return traj, tool


def main() -> None:
    urdf = ROUND / "data" / "robot" / "ur5e_collision.urdf"
    out = {}
    for task in json.loads((ROUND / "data" / "trajectory.json").read_text()):
        traj, tool = load(task)
        path = save(HERE / f"{task}.rrd", traj, robot=urdf, tool=tool, name=task)
        out[task] = {"rrd": str(path), "bytes": path.stat().st_size}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
