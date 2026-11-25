#!/usr/bin/env python3
"""R5 — robot_msgs' show(), grown: the arm over joint cards.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r5/make.py

Starts from what `robot_msgs.viz.rerun` draws for a JointTrajectory today (`log` → `_series` → `_blueprint`: one tab per
field, one plot per joint, radians, a 3D view only when something spatial was logged) and grows it the least amount that
fixes Zach's Nov 24 complaint ("a grey tool-path arc in an empty 3D view + nine separate per-joint q/qd/qdd panels …
100% there should be a urdf showing"):

- the URDF arm moves in a framed 3D view across the top, with the tool's path, the path so far, where the tool is now
  and a stick from the flange to it (the tool offset the URDF lacks); beside it the raw values at the playhead, in degrees;
- below it one card per joint (2 × 3 for six joints, adapting to the joint count): q, qd and qdd as % of that joint's own
  limits on one shared ±100 % axis, so every card reads the same and the in-limit band ends at ±100 %;
- the stock's per-field tabs stay one click away, now in degrees (the URDF says which joints are revolute).

Entity layout is the stock's `/<field>/<column>/<name>`: `/positions/<joint>/<name>` etc. (degrees, the stock's own
logger), `/limit_pct/<joint>/<name>` (one series entity per card, q / qd / qdd as its three instances, beside the stock
the way a Comparison sits under `error/`) with `/limit_pct/<joint>/<name>/limit` (the band), `/world/<robot>/…` (the
URDF), `/world/<name>/…` (tool path), `/notes/<name>` (the readout).

The proposed robot_msgs API is `save(path, traj, robot=urdf, tool=pose_trajectory)` → `.rrd`; `log_robot_trajectory`
below is the body that would move into `robot_msgs.viz.rerun` (see NOTES.md for the diff).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
from rerun.urdf import UrdfJoint, UrdfTree

from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as stock

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
APPLICATION_ID = "robot_msgs_r5_arm_over_joint_cards"  # one per proposal; Rerun 0.40 migrates ids with spaces or dots
TIMELINE = stock.TIMELINE  # "t", seconds from the first sample, as every robot_msgs recording

# One colour per quantity, the same in every card, so a glance at any card reads the same as any other.
Q_COLOR = [38, 110, 214]  # position: the strong line
QD_COLOR = [236, 134, 26]  # velocity
QDD_COLOR = [140, 140, 150]  # acceleration: quietest, it is the noisiest
LIMIT_BAND = [70, 160, 90, 60]  # the in-limit zone, ±100 %: a light green band whose edges are the limits
PATH_COLOR = [150, 150, 150]
TRAIL_COLOR = [236, 134, 26]
TOOL_COLOR = [236, 134, 26]
OFFSET_COLOR = [90, 90, 100]  # the flange-to-tool stick

COLORS = {"q": Q_COLOR, "qd": QD_COLOR, "qdd": QDD_COLOR}
WIDTHS = {"q": 2.5, "qd": 1.6, "qdd": 1.0}


# ── the URDF: which joints are revolute, their limits, forward kinematics for the framing and the tool path ──


def _rotation_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw))
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _rotation_about(axis: Any, angle: np.ndarray) -> np.ndarray:
    """Rodrigues for every sample at once: (N, 3, 3)."""
    unit = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    cross = np.array([[0, -unit[2], unit[1]], [unit[2], 0, -unit[0]], [-unit[1], unit[0], 0]])
    angle = np.asarray(angle, dtype=float)[:, None, None]
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * (cross @ cross)


def _link_poses(tree: UrdfTree, traj: JointTrajectory) -> dict[str, np.ndarray]:
    """Every link's pose in the URDF root frame at every sample, (N, 4, 4). Joints the trajectory lacks stay at 0."""
    samples = len(traj.t)
    positions = np.asarray(traj.positions, dtype=float)
    column = {name: index for index, name in enumerate(traj.joint_names)}
    poses = {tree.root_link().name: np.broadcast_to(np.eye(4), (samples, 4, 4))}
    pending = list(tree.joints())
    while pending:  # parents first, whatever order the URDF lists its joints in
        progressed = False
        for joint in list(pending):
            if joint.parent_link not in poses:
                continue
            value = _joint_value(joint, positions, column, samples)
            origin = np.eye(4)
            origin[:3, :3] = _rotation_rpy(*joint.origin_rpy)
            origin[:3, 3] = joint.origin_xyz
            motion = np.broadcast_to(np.eye(4), (samples, 4, 4)).copy()
            if joint.joint_type in ("revolute", "continuous"):
                motion[:, :3, :3] = _rotation_about(joint.axis, value)
            elif joint.joint_type == "prismatic":
                motion[:, :3, 3] = np.outer(value, np.asarray(joint.axis, dtype=float))
            poses[joint.child_link] = poses[joint.parent_link] @ origin @ motion
            pending.remove(joint)
            progressed = True
        if not progressed:
            break
    return poses


def _joint_value(joint: UrdfJoint, positions: np.ndarray, column: dict[str, int], samples: int) -> np.ndarray:
    if joint.name in column:
        return positions[:, column[joint.name]]
    if joint.mimic is not None and joint.mimic.joint in column:
        return joint.mimic.multiplier * positions[:, column[joint.mimic.joint]] + joint.mimic.offset
    return np.zeros(samples)


def _tool_link(tree: UrdfTree, traj: JointTrajectory) -> str:
    """The link at the end of the chain the trajectory moves: the deepest child below its last moving joint."""
    children: dict[str, list[str]] = {}
    for joint in tree.joints():
        children.setdefault(joint.parent_link, []).append(joint.child_link)
    moving = [joint for joint in tree.joints() if joint.name in set(traj.joint_names)]
    link = moving[-1].child_link if moving else tree.root_link().name
    while len(children.get(link, [])) == 1:  # follow fixed flanges / tool0 down a single branch
        link = children[link][0]
    return link


def _limits(traj: JointTrajectory, tree: UrdfTree) -> dict[str, dict[str, tuple[float, float] | None]]:
    """Per joint, per short field: (low, high) in the message's units, from `traj.limits`, else the URDF, else None."""
    joints = {joint.name: joint for joint in tree.joints()}
    limits: JointLimits | None = traj.limits
    out: dict[str, dict[str, tuple[float, float] | None]] = {}
    for index, name in enumerate(traj.joint_names):
        urdf = joints.get(name)
        row: dict[str, tuple[float, float] | None] = {}
        low = _bound(limits, "min_position", index)
        high = _bound(limits, "max_position", index)
        if (low is None or high is None) and urdf is not None and urdf.joint_type in ("revolute", "prismatic") \
                and urdf.limit_upper > urdf.limit_lower:
            low, high = urdf.limit_lower, urdf.limit_upper
        row["q"] = (low, high) if low is not None and high is not None and high > low else None
        velocity = _bound(limits, "max_velocity", index)
        if velocity is None and urdf is not None and urdf.limit_velocity > 0:
            velocity = urdf.limit_velocity
        row["qd"] = (-velocity, velocity) if velocity else None
        acceleration = _bound(limits, "max_acceleration", index)
        row["qdd"] = (-acceleration, acceleration) if acceleration else None
        out[name] = row
    return out


def _bound(limits: JointLimits | None, field_name: str, index: int) -> float | None:
    values = None if limits is None else getattr(limits, field_name)
    if values is None:
        return None
    value = float(np.asarray(values)[index])
    return value if math.isfinite(value) else None


# ── what each card's legend says: the 100 % scale in degrees (or mm), so the % reads back to the raw value ─────


def _unit(revolute: bool, short: str) -> tuple[float, str]:
    """(scale from SI, unit) for the legend: degrees for revolute joints (Zach's rule), mm for prismatic."""
    base = (180.0 / math.pi, "°") if revolute else (1000.0, " mm")
    suffix = {"q": "", "qd": "/s", "qdd": "/s²"}[short]
    return base[0], base[1] + suffix


def _legend(short: str, bound: tuple[float, float], revolute: bool) -> str:
    scale, unit = _unit(revolute, short)
    low, high = bound[0] * scale, bound[1] * scale
    if short == "q" and not math.isclose(low, -high):
        return f"{short} · {low:.0f}…{high:.0f}{unit}"
    return f"{short} · ±{high:.0f}{unit}"


def _percent(values: np.ndarray, bound: tuple[float, float]) -> np.ndarray:
    """Map [low, high] onto [-100, +100] %: the limit lines are ±100 % for every joint, symmetric range or not."""
    low, high = bound
    return (values - 0.5 * (low + high)) / (0.5 * (high - low)) * 100.0


# ── the recording ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Card:
    """One joint's card: its title, the % series (q / qd / qdd as instances of one entity) and their legend names."""

    joint: str
    title: str
    entity: str  # limit_pct/<joint>/<name>: one Scalars entity, one instance per quantity
    names: list[str]
    colors: list[list[int]]
    widths: list[float]
    percent: np.ndarray  # (N, quantities)


@dataclass(frozen=True)
class Scene:
    """Everything the blueprint needs, worked out before anything is logged (so the blueprint can go first)."""

    tree: UrdfTree
    robot_entity: str  # world/<robot>
    tool_entity: str  # world/<name>
    readout_entity: str  # notes/<name>: the raw values at the playhead
    revolute: list[str]
    seconds: np.ndarray
    tool_xyz: np.ndarray
    tool_t: np.ndarray
    flange_xyz: np.ndarray  # the URDF's last link along the moving chain, by forward kinematics
    links: dict[str, np.ndarray]
    cards: list[Card]
    span: float  # the shared y range of every card, ± this many %


def scene(traj: JointTrajectory, robot: str | Path, *, tool: PoseTrajectory | None = None,
          name: str = "JointTrajectory") -> Scene:
    robot_name = stock.path_part(UrdfTree.from_file_path(Path(robot)).name)
    robot_entity = f"world/{robot_name}"
    # WHY prefix "world" (one segment: Rerun 0.40 escapes a '/' inside the prefix) and tf_static under the robot: the
    # arm lands at /world/<robot>/…, the stock's place for anything spatial
    tree = UrdfTree.from_file_path(Path(robot), "world", static_transform_entity_path=f"/{robot_entity}/tf_static")
    joints = {joint.name: joint for joint in tree.joints()}
    missing = [joint for joint in traj.joint_names if joint not in joints]
    if missing:
        raise ValueError(f"{Path(robot).name} has no joint(s) {missing}; its joints: {sorted(joints)}")
    revolute = [joint for joint in traj.joint_names if joints[joint].joint_type in ("revolute", "continuous")]
    seconds = np.asarray(traj.t, dtype=float) - float(traj.t[0])
    links = _link_poses(tree, traj)
    flange_xyz = links[_tool_link(tree, traj)][:, :3, 3]
    if tool is not None:
        tool_xyz = np.asarray(tool.positions, dtype=float)
        tool_t = np.asarray(tool.t, dtype=float) - float(traj.t[0])
    else:
        tool_xyz, tool_t = flange_xyz, seconds

    limits = _limits(traj, tree)
    arrays = {"q": traj.positions, "qd": traj.velocities, "qdd": traj.accelerations}
    cards, peak = [], 100.0
    for index, joint in enumerate(traj.joint_names):
        shown, absent, names, columns = [], [], [], []
        for short in ("q", "qd", "qdd"):
            values, bound = arrays[short], limits[joint][short]
            if values is None:
                continue
            if bound is None:
                absent.append(short)
                continue
            columns.append(_percent(np.asarray(values, dtype=float)[:, index], bound))
            names.append(_legend(short, bound, joint in revolute))
            shown.append(short)
        percent = np.stack(columns, axis=1) if columns else np.zeros((len(seconds), 0))
        if percent.size:
            peak = max(peak, float(np.nanmax(np.abs(percent))))
        title = f"{joint} · {' / '.join(shown) or 'nothing'}, % of limit"
        if absent:
            title += f" ({' / '.join(absent)}: no limit)"
        cards.append(Card(joint=joint, title=title, entity=f"limit_pct/{stock.path_part(joint)}/{stock.path_part(name)}",
                          names=names, colors=[COLORS[s] for s in shown], widths=[WIDTHS[s] for s in shown],
                          percent=percent))
    # WHY a fixed axis a quarter past ±100 %: every card reads the same and the band's edges (the limits) sit well
    # inside the plot; a trajectory that breaks a limit widens every card the same amount instead of clipping it.
    span = max(125.0, math.ceil(peak / 10.0) * 10.0 + 15.0)
    return Scene(tree=tree, robot_entity=robot_entity, tool_entity=f"world/{stock.path_part(name)}",
                 readout_entity=f"notes/{stock.path_part(name)}", revolute=revolute,
                 seconds=seconds, tool_xyz=tool_xyz, tool_t=tool_t, flange_xyz=flange_xyz, links=links, cards=cards, span=span)


def log_robot_trajectory(traj: JointTrajectory, view: Scene, *, recording: rr.RecordingStream,
                         name: str = "JointTrajectory") -> None:
    """Log `traj`, its URDF arm, the tool path and the joint cards' series into `recording`."""
    time_column = [rr.TimeColumn(TIMELINE, duration=view.seconds)]

    # 1. the stock: one series per field and joint, now in degrees (`degrees=` the URDF's revolute joints)
    stock.log(traj, name, recording=recording, degrees=view.revolute)
    stock._PATHS.pop(id(recording), None)  # the stock's path register, read only by its own default blueprint

    # 2. the URDF arm, driven by the trajectory (Rerun 0.40's own loader; joint transforms are parent→child frames)
    view.tree.log_urdf_to_recording(recording=recording)
    joints = {joint.name: joint for joint in view.tree.joints()}
    positions = np.asarray(traj.positions, dtype=float)
    for index, joint in enumerate(traj.joint_names):
        recording.send_columns(f"{view.robot_entity}/joint_transforms/{stock.path_part(joint)}", indexes=time_column,
                               columns=joints[joint].compute_transform_columns(positions[:, index].tolist(),
                                                                                clamp=False))

    # 3. where the tool goes: the whole path (quiet), the path so far, the tool now — in the URDF root frame
    root_frame = rr.CoordinateFrame(view.tree.root_link().name)
    count = len(view.tool_xyz)
    tool_time = [rr.TimeColumn(TIMELINE, duration=view.tool_t)]
    recording.log(f"{view.tool_entity}/path", rr.LineStrips3D([view.tool_xyz], colors=[PATH_COLOR], radii=0.002),
                  root_frame, static=True)
    recording.log(f"{view.tool_entity}/trail", root_frame, static=True)
    recording.log(f"{view.tool_entity}/tool", root_frame, static=True)
    recording.send_columns(f"{view.tool_entity}/trail", indexes=tool_time,
                           columns=rr.LineStrips3D.columns(strips=[view.tool_xyz[: k + 1] for k in range(count)],
                                                           colors=[TRAIL_COLOR] * count, radii=[0.004] * count))
    recording.send_columns(f"{view.tool_entity}/tool", indexes=tool_time,
                           columns=rr.Points3D.columns(positions=view.tool_xyz, colors=[TOOL_COLOR] * count,
                                                       radii=[0.012] * count))
    # WHY a stick from the flange to the tool point: a tool PoseTrajectory usually carries a TCP offset the URDF lacks
    # (here a 145 mm tool); without the stick the tool point floats beside the arm and reads as a frame bug
    offset = np.linalg.norm(view.tool_xyz - view.flange_xyz, axis=1) if len(view.tool_xyz) == len(view.flange_xyz) else None
    if offset is not None and float(offset.max()) > 0.001:
        recording.log(f"{view.tool_entity}/tool_offset", root_frame, static=True)
        recording.send_columns(f"{view.tool_entity}/tool_offset", indexes=tool_time,
                               columns=rr.LineStrips3D.columns(
                                   strips=[np.stack([view.flange_xyz[k], view.tool_xyz[k]]) for k in range(count)],
                                   colors=[OFFSET_COLOR] * count, radii=[0.005] * count))

    # 4. the joint cards: q / qd / qdd as three instances of one series entity (legend order q, qd, qdd), and the
    #    in-limit band ±100 % under it (the stock's `band`, so its edges are the limit lines)
    for card in view.cards:
        if card.percent.shape[1] == 0:
            continue
        recording.log(card.entity, rr.SeriesLines(names=card.names, colors=card.colors, widths=card.widths),
                      static=True)
        recording.send_columns(card.entity, indexes=time_column,
                               columns=rr.Scalars.columns(scalars=card.percent.reshape(-1))
                               .partition([card.percent.shape[1]] * len(view.seconds)))
        stock.band(f"{card.entity}/limit", [0.0, float(view.seconds[-1])], -100.0, 100.0, recording=recording,
                   color=LIMIT_BAND, name="limit ±100 %")
    stock._PATHS.pop(id(recording), None)

    # 5. the raw values at the playhead, in degrees: what a card's hover cannot say (Rerun 0.40's plot hover shows the
    #    plotted number, here the %), in the dead space beside the arm
    recording.send_columns(view.readout_entity, indexes=time_column,
                           columns=rr.TextDocument.columns(text=_readouts(traj, view),
                                                           media_type=["text/markdown"] * len(view.seconds)))


def _readouts(traj: JointTrajectory, view: Scene) -> list[str]:
    """One markdown table per sample: each joint's q, qd, qdd in degrees (mm for a prismatic joint) and its worst %."""
    arrays = [traj.positions, traj.velocities, traj.accelerations]
    shorts = [short for short, values in zip(("q", "qd", "qdd"), arrays) if values is not None]
    units = {"q": "", "qd": "/s", "qdd": "/s²"}
    # every joint revolute (the usual arm): the unit sits once in the header; a prismatic joint in the mix puts it in
    # each cell instead (mm), so no row reads millimetres as degrees
    mixed = len(view.revolute) != len(traj.joint_names)
    header = "| joint | " + " | ".join(short if mixed else f"{short} °{units[short]}" for short in shorts) \
        + " | worst, % of limit |"
    rule = "|---|" + "---:|" * (len(shorts) + 1)
    tables = []
    for k in range(len(view.seconds)):
        rows = [f"**t = {view.seconds[k]:.2f} s**", "", header, rule]
        for index, (joint, card) in enumerate(zip(traj.joint_names, view.cards)):
            scale = 180.0 / math.pi if joint in view.revolute else 1000.0
            cells = [f"{float(np.asarray(values)[k, index]) * scale:+.1f}" for values in arrays if values is not None]
            if mixed:
                unit = "°" if joint in view.revolute else " mm"
                cells = [f"{cell}{unit}{units[short]}" for cell, short in zip(cells, shorts)]
            if card.percent.shape[1]:
                which = int(np.nanargmax(np.abs(card.percent[k])))
                worst = f"{abs(float(card.percent[k, which])):.0f} {card.names[which].split(' ')[0]}"
            else:
                worst = "–"
            rows.append(f"| {_short_joint(joint)} | " + " | ".join(cells) + f" | {worst} |")
        tables.append("\n".join(rows))
    return tables


def _short_joint(joint: str) -> str:
    """`shoulder_pan_joint` → `shoulder_pan`: the table is narrow, and every row is a joint."""
    return joint[: -len("_joint")] if joint.endswith("_joint") and len(joint) > len("_joint") else joint


def _eye(view: Scene, vertical_fov_deg: float = 55.0, aspect: float = 2.6) -> Any:
    """Frame every link origin over the whole motion plus the tool path, from the front-right, z up.

    WHY every link (traj_compare's `_stage_eye`, 2026-11-19): framing the tool path alone cut a bimanual's far arm.
    The distance is the closest at which every point fits a 55° vertical field of view in a view `aspect` wide
    (the arm's view is a wide strip over the cards), with a 5 % margin; the eye sits low (≈ 18° up) so the arm
    stands tall in the strip rather than foreshortened from above."""
    cloud = np.vstack([pose[:, :3, 3] for pose in view.links.values()] + [view.tool_xyz])
    cloud = cloud[np.all(np.isfinite(cloud), axis=1)]
    # WHY a radius per point: link origins sit inside the meshes (dev-003's wrist housing poked out of the top of the
    # view); 7 % of the motion's largest extent stands in for the links' thickness (a URDF's meshes are not read here)
    radius = 0.07 * float((cloud.max(axis=0) - cloud.min(axis=0)).max())
    look = 0.5 * (cloud.min(axis=0) + cloud.max(axis=0))
    back = np.array([1.0, -1.3, 0.55])
    back = back / np.linalg.norm(back)  # from the target toward the eye
    right = np.cross([0.0, 0.0, 1.0], -back)
    right = right / np.linalg.norm(right)
    up = np.cross(right, -back)
    tan_v = math.tan(math.radians(vertical_fov_deg) / 2) / 1.05
    tan_h = tan_v * aspect
    offsets = cloud - look
    # a point at offset o sits (distance - o·back) in front of the eye; it fits when its up/right offsets over that
    # depth stay under the half-angles' tangents
    need = np.maximum((np.abs(offsets @ up) + radius) / tan_v, (np.abs(offsets @ right) + radius) / tan_h) + offsets @ back
    distance = max(float(need.max()), 0.3)
    return rrb.EyeControls3D(kind="Orbital", look_target=look.tolist(), eye_up=[0, 0, 1],
                             position=(look + distance * back).tolist())


def _grid_columns(count: int) -> int:
    """Two rows up to eight joints (6 → 3 × 2, 7 → 4 + 3), then roughly 4:3: wide cards, because time runs across."""
    if count <= 3:
        return max(count, 1)
    rows = math.ceil(count / math.ceil(math.sqrt(count * 1.5)))
    return math.ceil(count / rows)


def blueprint(traj: JointTrajectory, view: Scene, name: str = "JointTrajectory") -> Any:
    arm = rrb.Spatial3DView(origin="/world", contents=[f"/{view.robot_entity}/**", f"/{view.tool_entity}/**"],
                            name=f"{view.tree.name} · {name}", eye_controls=_eye(view))
    joint_cards = [
        rrb.TimeSeriesView(origin=f"/{card.entity}", name=card.title,
                           axis_y=rrb.ScalarAxis(range=(-view.span, view.span), zoom_lock=True),
                           axis_x=rrb.TimeAxis(link="LinkToGlobal"),  # zoom one card's time, every card follows
                           plot_legend=rrb.PlotLegend(corner="LeftTop"))
        for card in view.cards
    ]
    readout = rrb.TextDocumentView(origin=f"/{view.readout_entity}", name="at the playhead · degrees")
    top = rrb.Horizontal(arm, readout, column_shares=[3.2, 1.0])
    overview = rrb.Vertical(top, rrb.Grid(*joint_cards, grid_columns=_grid_columns(len(joint_cards))),
                            row_shares=[1.25, 1.0], name="arm + joints")
    # the stock's per-field tabs, kept one click away and now in degrees: one plot per joint, the raw value in the hover
    units = {"positions": "°", "velocities": "°/s", "accelerations": "°/s²"}
    stock_tabs = [
        rrb.Grid(*(rrb.TimeSeriesView(origin=f"/{field_name}/{stock.path_part(joint)}",
                                      name=f"{joint} {units[field_name]}" if joint in view.revolute else joint)
                   for joint in traj.joint_names),
                 name=f"{field_name} {units[field_name]}")
        for field_name in ("positions", "velocities", "accelerations")
        if getattr(traj, field_name) is not None
    ]
    return rrb.Blueprint(
        rrb.Tabs(overview, *stock_tabs, active_tab=0),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        # WHY playing and looping, not paused: on open the arm moves (Zach: the robot is the first thing you see).
        # A paused blueprint did not hold a link's #when= playhead either (it opened at +0.000 s), so pausing bought
        # the round's stills nothing; NOTES.md has the probe.
        rrb.TimePanel(state="collapsed", play_state="playing", loop_mode="all"),
    )


def save(path: str | Path, traj: JointTrajectory, robot: str | Path, *, tool: PoseTrajectory | None = None,
         name: str = "JointTrajectory", application_id: str = APPLICATION_ID) -> Path:
    """The proposal's one function: a JointTrajectory + its URDF (+ the tool's PoseTrajectory) → an `.rrd`.

    The blueprint goes first (`default_blueprint`, at the head of the file), so the layout is there before the data."""
    view = scene(traj, robot, tool=tool, name=name)
    recording = rr.RecordingStream(application_id)
    recording.save(str(path), default_blueprint=blueprint(traj, view, name))
    log_robot_trajectory(traj, view, recording=recording, name=name)
    recording.flush()
    recording.disconnect()
    return Path(path)


# ── the round's two inputs ───────────────────────────────────────────────────


def _quaternion_xyzw(rotation: np.ndarray) -> np.ndarray:
    """(N, 3, 3) rotation matrices → (N, 4) xyzw quaternions (Shepperd's method, numerically safe on every branch)."""
    out = np.empty((len(rotation), 4))
    for k, m in enumerate(rotation):
        trace = np.trace(m)
        if trace > 0:
            s = 2.0 * math.sqrt(trace + 1.0)
            out[k] = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
        elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = 2.0 * math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
            out[k] = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
        elif m[1, 1] > m[2, 2]:
            s = 2.0 * math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
            out[k] = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
        else:
            s = 2.0 * math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
            out[k] = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    return out


def load(task: str) -> tuple[JointTrajectory, PoseTrajectory]:
    data = np.load(ROUND / "data" / f"{task}.npz")
    names = tuple(str(name) for name in data["names"])
    limits = JointLimits(joint_names=names, min_position=data["lo"], max_position=data["hi"],
                         max_velocity=data["vmax"], max_acceleration=data["amax"])
    traj = JointTrajectory(t=data["t"], joint_names=names, positions=data["q"], velocities=data["qd"],
                           accelerations=data["qdd"], limits=limits)
    tool = PoseTrajectory(t=data["t"], positions=data["tool_xyz"], orientations=_quaternion_xyzw(data["tool_rot"]))
    return traj, tool


def main() -> None:
    urdf = ROUND / "data" / "robot" / "ur5e_collision.urdf"
    for task in ("workspace-dev-029", "workspace-dev-003"):
        traj, tool = load(task)
        out = save(HERE / f"{task}.rrd", traj, urdf, tool=tool, name=task)
        print(out, f"{out.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
