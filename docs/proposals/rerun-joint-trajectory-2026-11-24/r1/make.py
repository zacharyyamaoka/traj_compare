#!/usr/bin/env python3
"""R1 "Stage + questions": the stock Rerun view of a robot_msgs JointTrajectory, grown from traj_compare's "questions" layout.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r1/make.py

Writes r1/workspace-dev-029.rrd and r1/workspace-dev-003.rrd (the round's two UR5e trajectories, data/).

The layout (traj_compare.rerun_export._layout_questions: a pinned stage on the left, question tabs beside it), with the
stage widened into the hero because a lone JointTrajectory has no runs to rank:

    stage (3/5 of the width)          question tabs (2/5)
    ┌──────────────────────────────┐  ┌ Where are the joints? ┬ How fast? ┬ How hard? ┬ Where does the tool go? ┐
    │ the URDF arm at the playhead,│  │ one plot per joint, in degrees (°, °/s, °/s²), each joint's limits as │
    │ each link tinted by the joint│  │ dark lines with a red strip beyond; the title holds the one number    │
    │ that drives it; the tool's   │  │ (its limits, or its peak as % of the limit). The joint's colour = its │
    │ path, its trail and its point│  │ links' tint on the stage. Last tab: the tool's x/y/z and speed, mm.   │
    ├──────────────────────────────┤  │                                                                       │
    │ at a glance: range, peak use │  │                                                                       │
    └──────────────────────────────┘  └───────────────────────────────────────────────────────────────────────┘

Entity layout — robot_msgs.viz.rerun's (/<field>/<column>/<name>, spatial under /world/<name>/), so a robot_msgs
``show(target=traj)`` logged into the same recording lands in the same plots:

    /world/<name>/robot/<urdf name>/...        the URDF, by Rerun's own loader (rr.log_file_from_path), static
    /world/<name>/robot/joint_transforms/<j>   the joint's transform on the t timeline (rerun.urdf compute_transform_columns)
    /world/<name>/tcp/{path,trail,now,axes,mount}  the tool: whole path (faint), path so far, the point at the playhead,
                                               its axes, a stick from the URDF's last link to it (a tool the URDF lacks)
    /positions|velocities|accelerations/<j>/<name>     the trajectory, ° · °/s · °/s² (mm for a prismatic joint)
    /positions|velocities|accelerations/<j>/limits     the JointLimits beside it: [min, max] / ±max, same units
    /positions|velocities|accelerations/<j>/{above,below}_limit   the red strip past each limit (robot_msgs' band)
    /tcp/{x,y,z}_mm/<name>, /tcp/speed_mm_s/<name>      the tool's position and speed (traj_compare's /tcp layout)
    /notes/<name>                                       the at-a-glance table

WHY degrees at the display edge (Zach's rule): the JointTrajectory stays SI; only what is logged for a person to read is
converted. WHY the URDF through Rerun's own loader (Rerun 0.40 rerun.urdf): it reads meshes, primitives, materials and
origins for any arm, so this file never parses geometry; it only computes forward kinematics (numpy, from the URDF's
joint origins and axes) to frame the camera and draw the tool when no tool PoseTrajectory is given.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
from rerun.urdf import UrdfTree
from robot_msgs.geometry.rotations import quat_from_matrix, quat_to_matrix
from robot_msgs.std.header import Header
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as viz

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
URDF = DATA / "robot" / "ur5e_collision.urdf"
TASKS = ("workspace-dev-029", "workspace-dev-003")

APPLICATION_ID = "joint_trajectory_r1_stage_questions"
TIMELINE = viz.TIMELINE
DEGREES = 180.0 / math.pi
TRAIL_ROWS = 600  # WHY a cap: the trail is the path so far at every logged instant (rows x points); a long, fast-sampled
# trajectory would otherwise write samples² points. 600 rows keep scrubbing smooth and the file small.

# WHY Tableau 10: six-plus well-separated hues that survive both light and dark viewer themes; joint i keeps colour i on
# the stage, in every plot and in the table, so "which is which" never needs a legend.
JOINT_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
ROBOT_GREY = (205, 208, 214)
LIMIT_LINE = (90, 90, 90, 255)
BEYOND_LIMIT = (224, 49, 49, 45)  # the shaded strip past a limit: red at a glance, faint enough to read a line over
AXIS_PAD = 0.12  # each plot shows its limits with this share of the range beyond them, so the red strip is visible
TOOL_PATH = (120, 120, 120, 170)
TOOL_TRAIL = (230, 120, 20, 255)
TOOL_NOW = (230, 60, 20, 255)
TOOL_MOUNT = (110, 110, 118, 255)
AXIS_RGB = {"x": (220, 60, 60), "y": (70, 170, 70), "z": (60, 110, 230)}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _joint_color(index: int) -> tuple[int, int, int]:
    return _rgb(JOINT_COLORS[index % len(JOINT_COLORS)])


def _short(joint: str) -> str:
    """'shoulder_pan_joint' -> 'shoulder pan': the name a person reads (traj_compare's _short)."""
    return joint.replace("_joint", "").replace("_", " ")


# ── forward kinematics from the URDF alone (no Pinocchio: any arm, the traj_compare venv) ────────────


def _rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """URDF rpy: fixed-axis roll, pitch, yaw = Rz(yaw) Ry(pitch) Rx(roll)."""
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw))
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _axis_rotations(axis: Any, angles: np.ndarray) -> np.ndarray:
    """(N, 3, 3) rotations about one unit axis (Rodrigues)."""
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    k = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    theta = np.asarray(angles, dtype=float)[:, None, None]
    return np.eye(3) + np.sin(theta) * k + (1.0 - np.cos(theta)) * (k @ k)


class Kinematics:
    """Every link's pose (base frame = the URDF root link) at every sample of a JointTrajectory."""

    def __init__(self, tree: UrdfTree, traj: JointTrajectory) -> None:
        self.tree = tree
        self.root = tree.root_link().name
        self.joints = {joint.name: joint for joint in tree.joints()}
        self.parent_joint = {joint.child_link: joint for joint in tree.joints()}
        names = list(traj.joint_names)
        q = np.asarray(traj.positions, dtype=float)
        n = len(q)
        children: dict[str, list[Any]] = {}
        for joint in tree.joints():
            children.setdefault(joint.parent_link, []).append(joint)
        self.poses: dict[str, tuple[np.ndarray, np.ndarray]] = {self.root: (np.repeat(np.eye(3)[None], n, 0), np.zeros((n, 3)))}
        stack = [self.root]
        while stack:
            link = stack.pop()
            rotation, position = self.poses[link]
            for joint in children.get(link, []):
                child_rotation = rotation @ _rpy_matrix(*joint.origin_rpy)
                child_position = position + rotation @ np.asarray(joint.origin_xyz, dtype=float)
                value = q[:, names.index(joint.name)] if joint.name in names else np.zeros(n)
                if joint.joint_type in ("revolute", "continuous"):
                    child_rotation = child_rotation @ _axis_rotations(joint.axis, value)
                elif joint.joint_type == "prismatic":
                    child_position = child_position + (child_rotation @ np.asarray(joint.axis, dtype=float)) * value[:, None]
                self.poses[joint.child_link] = (child_rotation, child_position)
                stack.append(joint.child_link)
        self.moving = [name for name in names if name in self.joints and self.joints[name].joint_type != "fixed"]

    def chain(self, link: str) -> list[Any]:
        """The joints from the root down to ``link``."""
        joints = []
        while link in self.parent_joint:
            joints.append(self.parent_joint[link])
            link = joints[-1].parent_link
        return joints[::-1]

    def tip(self) -> str:
        """The tool flange: the link below the most trajectory joints, the deepest one on a tie (tool0 below wrist_3)."""
        moving = set(self.moving)
        return max(self.poses, key=lambda link: (sum(j.name in moving for j in self.chain(link)), len(self.chain(link))))

    def driver(self, link: str) -> str | None:
        """The trajectory joint nearest above ``link`` (what moves it), or None for the base."""
        for joint in reversed(self.chain(link)):
            if joint.name in self.moving:
                return joint.name
        return None


def _unit(tree_joint: Any | None) -> tuple[float, str]:
    """(scale from SI, unit) for a joint's position: degrees for revolute/continuous (or unknown), mm for prismatic."""
    if tree_joint is not None and tree_joint.joint_type == "prismatic":
        return 1000.0, "mm"
    return DEGREES, "°"


# ── logging ─────────────────────────────────────────────────────────────────


def _series(rec: rr.RecordingStream, path: str, seconds: np.ndarray, values: np.ndarray, *, names: Any, colors: Any,
            widths: Any) -> None:
    """One (or several, for a (n, k) array) line series on the t timeline."""
    rec.log(path, rr.SeriesLines(names=names, colors=colors, widths=widths), static=True)
    rec.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=seconds)], columns=rr.Scalars.columns(scalars=values))


def _log_limits(rec: rr.RecordingStream, column_path: str, span: np.ndarray, bounds: tuple[float, float, float, float],
                names: list[str]) -> None:
    """A limit pair as two dark lines plus a red strip beyond each (robot_msgs.viz.rerun.band) up to the plot's edge.

    WHY lines AND strips: a line alone is lost against a ±360° axis; the strip says "past here is out" without reading
    a number. Two samples (the start and the end) draw each flat over the whole trajectory."""
    low, high, axis_low, axis_high = bounds
    _series(rec, f"{column_path}/limits", span, np.array([[low, high], [low, high]], dtype=float), names=names,
            colors=[LIMIT_LINE, LIMIT_LINE], widths=[1.5, 1.5])
    viz.band(f"{column_path}/above_limit", span, high, axis_high, recording=rec, color=BEYOND_LIMIT, name="beyond the limit")
    viz.band(f"{column_path}/below_limit", span, axis_low, low, recording=rec, color=BEYOND_LIMIT, name="beyond the limit")


_FIELDS = (("positions", "min_position", "max_position"), ("velocities", "max_velocity", None),
           ("accelerations", "max_acceleration", None))


def _bounds(traj: JointTrajectory, kin: Kinematics, rates: dict[str, np.ndarray]) -> dict[tuple[str, str], tuple[float, float, float, float] | None]:
    """(field, joint) -> (low, high, axis low, axis high) in display units, or None when the limit is not stated.

    The axis holds both the limits and the values (a value past a limit stays on screen) plus AXIS_PAD beyond."""
    out = {}
    for index, joint in enumerate(traj.joint_names):
        scale, _ = _unit(kin.joints.get(joint))
        for field, first, second in _FIELDS:
            a = _limits_of(traj.limits, first, joint)
            b = _limits_of(traj.limits, second, joint) if second else a
            if a is None or b is None:
                out[field, joint] = None
                continue
            low, high = (a * scale, b * scale) if second else (-a * scale, a * scale)
            values = rates[field][:, index] * scale
            lo, hi = min(low, float(values.min())), max(high, float(values.max()))
            pad = AXIS_PAD * (hi - lo) if hi > lo else 1.0
            out[field, joint] = (low, high, lo - pad, hi + pad)
    return out


def _rates(traj: JointTrajectory) -> tuple[np.ndarray, np.ndarray, bool]:
    """qd and qdd, differentiated from q when the message leaves them out (the bool says so)."""
    t = np.asarray(traj.t, dtype=float)
    q = np.asarray(traj.positions, dtype=float)
    derived = traj.velocities is None or traj.accelerations is None
    qd = np.asarray(traj.velocities, dtype=float) if traj.velocities is not None else np.gradient(q, t, axis=0)
    qdd = np.asarray(traj.accelerations, dtype=float) if traj.accelerations is not None else np.gradient(qd, t, axis=0)
    return qd, qdd, derived


def _limits_of(limits: JointLimits | None, field: str, joint: str) -> float | None:
    if limits is None or getattr(limits, field) is None or joint not in limits.joint_names:
        return None
    value = float(np.asarray(getattr(limits, field))[list(limits.joint_names).index(joint)])
    return value if math.isfinite(value) else None


def _tool_poses(traj: JointTrajectory, kin: Kinematics, tool: PoseTrajectory | None
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, str]:
    """(t, positions (n, 3), rotations (n, 3, 3), label, where it came from) of the tool in the URDF root frame.

    A given tool PoseTrajectory wins (it knows the TCP offset); its header.frame_id may name a URDF link, whose pose
    (from the trajectory's own forward kinematics, same clock) carries it into the root frame. Without one: the flange."""
    if tool is None:
        tip = kin.tip()
        rotation, position = kin.poses[tip]
        return np.asarray(traj.t, dtype=float), position, rotation, tip, "no tool PoseTrajectory: the URDF's last link"
    t = np.asarray(tool.t, dtype=float)
    position = np.asarray(tool.positions, dtype=float)
    rotation = quat_to_matrix(np.asarray(tool.orientations, dtype=float))
    frame = tool.header.frame_id
    if frame and frame != kin.root and frame in kin.poses:
        link_rotation, link_position = kin.poses[frame]
        link_t = np.asarray(traj.t, dtype=float)
        pick = np.clip(np.searchsorted(link_t, t), 0, len(link_t) - 1)
        position = link_position[pick] + np.einsum("nij,nj->ni", link_rotation[pick], position)
        rotation = link_rotation[pick] @ rotation
    return t, position, rotation, tool.child_frame_id or "tool", "the given tool PoseTrajectory"


def _stage_eye(kin: Kinematics, tool_xyz: np.ndarray) -> rrb.EyeControls3D:
    """traj_compare's _stage_eye: frame every link origin and the tool path from the front-right, z up.

    WHY the middle 90 % of the link origins: a static base link at the world origin should not set the box."""
    cloud = np.vstack([position for _, position in kin.poses.values()] + [tool_xyz])
    cloud = cloud[np.all(np.isfinite(cloud), axis=1)]
    low, high = np.percentile(cloud, 5, axis=0), np.percentile(cloud, 95, axis=0)
    low[2] = min(low[2], 0.0)  # WHY: keep the base on screen; an arm reaching up is framed from its foot
    look = 0.5 * (low + high)
    spread = high - low
    reach = max(float(spread.max()), 0.6)
    direction = np.array([1.9, -1.0, 0.9]) if spread[1] > 1.2 * spread[0] else np.array([1.5, -1.9, 1.1])
    return rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1], position=look + 0.52 * reach * direction)


def _log_robot(rec: rr.RecordingStream, urdf: Path, name: str, tree: UrdfTree, kin: Kinematics, traj: JointTrajectory,
               seconds: np.ndarray) -> None:
    """The URDF by Rerun's loader, each link tinted by the joint that drives it, and the joints' transforms over time."""
    base = f"world/{viz.path_part(name)}/robot"
    rr.log_file_from_path(urdf, entity_path_prefix=base, static=True, recording=rec)
    names = list(traj.joint_names)
    for link in kin.poses:
        visual = tree.get_visual_geometry_paths(link)
        collision = tree.get_collision_geometry_paths(link)
        driver = kin.driver(link)
        if driver is None:
            tint = ROBOT_GREY
        else:  # WHY a pale tint, not the joint colour: the arm stays an arm; the tint only keys it to the plots
            tint = tuple(int(0.62 * g + 0.38 * c) for g, c in zip(ROBOT_GREY, _joint_color(names.index(driver))))
        for path in (visual or collision):
            if "/mesh/" in path:  # Asset3D only: a primitive (box, cylinder) is logged as another archetype
                rec.log(f"{base}{path}", rr.Asset3D.from_fields(albedo_factor=[*tint, 255]), static=True)
    q = np.asarray(traj.positions, dtype=float)
    for index, joint in enumerate(names):
        urdf_joint = tree.get_joint_by_name(joint)
        if urdf_joint is None:
            continue  # a joint the URDF lacks (a gripper's command channel): plotted, not drawn
        rec.send_columns(f"{base}/joint_transforms/{viz.path_part(joint)}", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                         columns=urdf_joint.compute_transform_columns(q[:, index].tolist(), clamp=False))


def _log_tool(rec: rr.RecordingStream, name: str, kin: Kinematics, traj_t: np.ndarray, tool_t: np.ndarray, xyz: np.ndarray,
              rotation: np.ndarray, label: str) -> None:
    """The tool in 3D (path, trail so far, point, axes, the stick from the flange) and as plots (x/y/z, speed in mm)."""
    base = f"world/{viz.path_part(name)}/tcp"
    seconds = tool_t - traj_t[0]
    for leaf in ("path", "trail", "now", "axes", "mount"):
        rec.log(f"{base}/{leaf}", rr.CoordinateFrame(kin.root), static=True)
    # WHY a stick from the flange (seen on dev-003, 2026-11-24): a URDF without its gripper left the TCP point floating
    # 145 mm off the wrist, which read as a wrong frame; the stick says "a tool the URDF does not draw ends here"
    flange = kin.poses[kin.tip()][1][np.clip(np.searchsorted(traj_t, tool_t), 0, len(traj_t) - 1)]
    if np.linalg.norm(flange - xyz, axis=1).max() > 1e-3:
        rec.send_columns(f"{base}/mount", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                         columns=rr.LineStrips3D.columns(strips=[np.stack([a, b]) for a, b in zip(flange, xyz, strict=True)],
                                                         colors=[TOOL_MOUNT] * len(xyz), radii=[0.006] * len(xyz)))
    rec.log(f"{base}/path", rr.LineStrips3D([xyz], colors=[TOOL_PATH], radii=0.0025), static=True)
    stride = max(1, math.ceil(len(xyz) / TRAIL_ROWS))
    rows = list(range(0, len(xyz), stride))
    if rows[-1] != len(xyz) - 1:
        rows.append(len(xyz) - 1)
    rec.send_columns(f"{base}/trail", indexes=[rr.TimeColumn(TIMELINE, duration=seconds[rows])],
                     columns=rr.LineStrips3D.columns(strips=[np.vstack([xyz[:k + 1:stride], xyz[k]]) for k in rows],
                                                     colors=[TOOL_TRAIL] * len(rows), radii=[0.004] * len(rows)))
    rec.send_columns(f"{base}/now", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                     columns=rr.Points3D.columns(positions=xyz, colors=[TOOL_NOW] * len(xyz), radii=[0.014] * len(xyz),
                                                 labels=[label] * len(xyz)))
    length = 0.08
    origins = np.repeat(xyz, 3, axis=0)
    vectors = np.concatenate([rotation[:, :, axis][:, None, :] for axis in range(3)], axis=1).reshape(-1, 3) * length
    colors = np.tile(np.array([AXIS_RGB["x"], AXIS_RGB["y"], AXIS_RGB["z"]], dtype=np.uint8), (len(xyz), 1))
    rec.send_columns(f"{base}/axes", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                     columns=rr.Arrows3D.columns(origins=origins, vectors=vectors, colors=colors,
                                                 radii=[0.003] * len(origins)).partition([3] * len(xyz)))
    part = viz.path_part(name)
    for axis, column in zip("xyz", xyz.T, strict=True):
        _series(rec, f"tcp/{axis}_mm/{part}", seconds, column * 1000.0, names=f"{axis}", colors=AXIS_RGB[axis], widths=2.0)
    speed = np.linalg.norm(np.gradient(xyz, tool_t, axis=0), axis=1) * 1000.0
    _series(rec, f"tcp/speed_mm_s/{part}", seconds, speed, names="speed", colors=TOOL_TRAIL[:3], widths=2.0)


def _percent(peak: float, limit: float | None) -> str:
    return "" if not limit else f" · {100.0 * peak / limit:.0f} %"


def _glance(traj: JointTrajectory, kin: Kinematics, robot: str, name: str, qd: np.ndarray, qdd: np.ndarray,
            derived: bool, tool_label: str) -> str:
    """The at-a-glance table under the stage: each joint's range against its limits, and its peak speed and effort."""
    names = list(traj.joint_names)
    q = np.asarray(traj.positions, dtype=float)
    t = np.asarray(traj.t, dtype=float)
    rows = [f"**{robot} · {name}** — {len(names)} joints, {t[-1] - t[0]:.2f} s, {len(t)} samples; tool path: {tool_label}"
            + (" · speed/acceleration differentiated from the angles" if derived else ""),
            "", "| joint | range | limits | peak speed | peak acceleration |", "|---|---|---|---|---|"]
    for index, joint in enumerate(names):
        scale, unit = _unit(kin.joints.get(joint))
        low, high = _limits_of(traj.limits, "min_position", joint), _limits_of(traj.limits, "max_position", joint)
        vmax, amax = _limits_of(traj.limits, "max_velocity", joint), _limits_of(traj.limits, "max_acceleration", joint)
        peak_v, peak_a = float(np.abs(qd[:, index]).max()), float(np.abs(qdd[:, index]).max())
        limits = f"{low * scale:.0f} … {high * scale:.0f}" if low is not None and high is not None else "—"
        rows.append(f"| {_short(joint)} "
                    f"| {q[:, index].min() * scale:.0f} … {q[:, index].max() * scale:.0f} {unit} | {limits} "
                    f"| {peak_v * scale:.0f} {unit}/s{_percent(peak_v, vmax)} | {peak_a * scale:.0f} {unit}/s²{_percent(peak_a, amax)} |")
    return "\n".join(rows)


# ── the blueprint: the stage + the question tabs ─────────────────────────────


def _plot(origin: str, name: str, legend: bool = False, y_range: tuple[float, float] | None = None) -> rrb.TimeSeriesView:
    """traj_compare's _ts: x zoom linked across every plot, so zooming one zooms them all; ``y_range`` opens on the limits."""
    return rrb.TimeSeriesView(origin=origin, name=name, plot_legend=rrb.PlotLegend(visible=legend),
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"),
                              axis_y=rrb.ScalarAxis(range=y_range) if y_range else None)


def _joint_grid(field: str, titles: dict[str, str], bounds: dict, title: str) -> rrb.Grid:
    views = [_plot(f"/{field}/{viz.path_part(joint)}", text,
                   y_range=bounds[field, joint][2:] if bounds.get((field, joint)) else None) for joint, text in titles.items()]
    return rrb.Grid(*views, grid_columns=2 if len(views) > 3 else 1, name=title)


def _limit_text(low: float, high: float) -> str:
    return f"±{high:.0f}" if abs(low + high) < 0.5 else f"{low:.0f} … {high:.0f}"


def _blueprint(traj: JointTrajectory, kin: Kinematics, robot: str, name: str, rates: dict[str, np.ndarray], bounds: dict,
               eye: rrb.EyeControls3D, tool_label: str, hidden: list[str]) -> rrb.Blueprint:
    """The stage + the question tabs. WHY short titles (seen at 1600 px): a 2-column grid in 2/5 of the width cut
    "shoulder pan angle [°] · limits −360 … 360" after "limits"; the joint, the unit and the one number that matters fit."""
    titles: dict[str, dict[str, str]] = {"positions": {}, "velocities": {}, "accelerations": {}}
    for index, joint in enumerate(traj.joint_names):
        scale, unit = _unit(kin.joints.get(joint))
        units = {"positions": unit, "velocities": f"{unit}/s", "accelerations": f"{unit}/s²"}
        for field, _, _ in _FIELDS:
            head = f"{_short(joint)} [{units[field]}]"
            bound = bounds.get((field, joint))
            if field == "positions":
                titles[field][joint] = f"{head} · limits {_limit_text(*bound[:2])}" if bound else f"{head} · no limits stated"
            else:
                peak = float(np.abs(rates[field][:, index]).max()) * scale
                titles[field][joint] = (f"{head} · peak {100 * peak / bound[1]:.0f} % of {bound[1]:.0f}" if bound
                                        else f"{head} · peak {peak:.0f}, no limit stated")
    part = viz.path_part(name)
    tabs = [
        _joint_grid("positions", titles["positions"], bounds, "Where are the joints?"),
        _joint_grid("velocities", titles["velocities"], bounds, "How fast?"),
        _joint_grid("accelerations", titles["accelerations"], bounds, "How hard?"),
        rrb.Vertical(rrb.TimeSeriesView(origin="/tcp", contents=[f"/tcp/{axis}_mm/**" for axis in "xyz"],
                                        name=f"tool position [mm] · x red, y green, z blue · {tool_label}",
                                        plot_legend=rrb.PlotLegend(visible=False), axis_x=rrb.TimeAxis(link="LinkToGlobal")),
                     _plot("/tcp/speed_mm_s", "tool speed [mm/s]"), row_shares=[3, 2], name="Where does the tool go?"),
    ]
    contents = [f"/world/{part}/**"] + [f"- {path}" for path in hidden]
    stage = rrb.Vertical(
        rrb.Spatial3DView(origin="/", contents=contents, eye_controls=eye,
                          name=f"{robot} · {name} — the arm at the playhead; orange = the tool's path so far, grey = still to come",
                          line_grid=rrb.LineGrid3D(visible=True, spacing=0.1, color=[128, 128, 128, 60])),
        rrb.TextDocumentView(origin=f"/notes/{part}", name="At a glance"),
        row_shares=[5, 2],
    )
    return rrb.Blueprint(
        rrb.Horizontal(stage, rrb.Tabs(*tabs, active_tab=0), column_shares=[3, 2]),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        # WHY paused: it opens on the start pose with the whole path ahead (a poster frame); press play or scrub. Tested
        # 2026-11-24 in the 0.40 web viewer: a link's #when=t@<s> is ignored under every state (paused -> 0, playing ->
        # plays from 0, following or no blueprint -> the end), so this choice does not cost the share-link time
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused", loop_mode="all"),
    )


# ── the entry point ─────────────────────────────────────────────────────────


def save_joint_trajectory(traj: JointTrajectory, urdf: str | Path, out: str | Path, *, tool: PoseTrajectory | None = None,
                          name: str | None = None, application_id: str = APPLICATION_ID) -> Path:
    """One JointTrajectory (+ its robot's URDF, + optionally the tool's PoseTrajectory) -> a self-contained ``.rrd``.

    ``name`` is robot_msgs' name (default: the type name, as ``traj.show()``); the tool's pose may be in the URDF's root
    frame or in any URDF link's frame (``tool.header.frame_id``)."""
    urdf, out = Path(urdf), Path(out)
    name = name or type(traj).__name__
    tree = UrdfTree.from_file_path(urdf)
    kin = Kinematics(tree, traj)
    t = np.asarray(traj.t, dtype=float)
    t0 = float(t[0])
    seconds = t - t0
    qd, qdd, derived = _rates(traj)
    rates = {"positions": np.asarray(traj.positions, dtype=float), "velocities": qd, "accelerations": qdd}
    bounds = _bounds(traj, kin, rates)
    tool_t, tool_xyz, tool_rotation, tool_label, tool_source = _tool_poses(traj, kin, tool)
    hidden = [f"/world/{viz.path_part(name)}/robot{path}" for link in kin.poses for path in
              (tree.get_collision_geometry_paths(link) if tree.get_visual_geometry_paths(link) else [])]
    blueprint = _blueprint(traj, kin, tree.name, name, rates, bounds, _stage_eye(kin, tool_xyz), tool_label, hidden)

    rec = rr.RecordingStream(application_id, recording_id=f"{application_id}-{out.stem}")
    rec.save(out, default_blueprint=blueprint)
    _log_robot(rec, urdf, name, tree, kin, traj, seconds)
    _log_tool(rec, name, kin, t, tool_t, tool_xyz, tool_rotation, tool_label)

    part = viz.path_part(name)
    span = np.array([seconds[0], seconds[-1]])
    for index, joint in enumerate(traj.joint_names):
        scale, _ = _unit(kin.joints.get(joint))
        column = viz.path_part(joint)
        for field, first, second in _FIELDS:
            _series(rec, f"{field}/{column}/{part}", seconds, rates[field][:, index] * scale, names=name,
                    colors=_joint_color(index), widths=2.0)
            if bounds.get((field, joint)):
                _log_limits(rec, f"{field}/{column}", span, bounds[field, joint],
                            [first, second] if second else [f"-{first}", first])
    rec.log(f"notes/{part}", rr.TextDocument(_glance(traj, kin, tree.name, name, qd, qdd, derived, f"{tool_label} ({tool_source})"),
                                             media_type="text/markdown"), static=True)
    viz._PATHS.pop(id(rec), None)  # WHY: viz.band registers paths for robot_msgs' own blueprint; this file sends its own
    rec.flush()
    rec.disconnect()
    return out


# ── the round's inputs ──────────────────────────────────────────────────────


def load_round_trajectory(task: str) -> tuple[JointTrajectory, PoseTrajectory]:
    """data/<task>.npz -> the robot_msgs JointTrajectory and the tool's PoseTrajectory.

    The tool is in the URDF root frame (base_link_ur): it equals wrist_3_link + 144.8 mm along its z to 0.7 mm (checked
    against this file's forward kinematics), so it says frame_id=base_link_ur."""
    data = np.load(DATA / f"{task}.npz")
    names = tuple(str(name) for name in data["names"])
    limits = JointLimits(joint_names=names, min_position=data["lo"], max_position=data["hi"], max_velocity=data["vmax"],
                         max_acceleration=data["amax"])
    traj = JointTrajectory(t=data["t"], joint_names=names, positions=data["q"],
                           velocities=data["qd"] if data["qd"].size else None,
                           accelerations=data["qdd"] if data["qdd"].size else None, limits=limits)
    tool = PoseTrajectory(t=data["t"], positions=data["tool_xyz"], orientations=quat_from_matrix(data["tool_rot"]),
                          child_frame_id="tcp", header=Header(frame_id="base_link_ur"))
    return traj, tool


def main() -> None:
    for task in TASKS:
        traj, tool = load_round_trajectory(task)
        out = save_joint_trajectory(traj, URDF, HERE / f"{task}.rrd", tool=tool, name="target")
        print(out, f"{out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
