#!/usr/bin/env python3
"""R2 "evo: one full-screen tab per analysis" — a robot_msgs JointTrajectory + its URDF as one Rerun 0.40 recording.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r2/make.py

Grows traj_compare's "evo" layout (``rerun_export._layout_evo``, Zach's Nov 11 pick, copied from ``evo_ape --rerun``)
into the stock JointTrajectory view: Rerun Tabs, each full screen —

    Robot          the URDF arm moving, framed; the tool's whole path, the trail it has drawn so far, the tool now
    Joints         every joint's q on one plot, each named, in degrees, with its position limits
    Speed          qd, °/s, against ±max_velocity
    Acceleration   qdd, °/s², against ±max_acceleration
    Data           a DataframeView of the samples (t, q per joint in degrees) that scrolls with the playhead

Entity layout (robot_msgs.viz.rerun's, so a recording of this and a ``traj.show()`` / traj_compare recording overlay):

    /positions|velocities|accelerations/<joint>/<name>   robot_msgs.viz.rerun.log(traj, name, degrees=<revolute joints>)
    /positions|velocities|accelerations/<joint>/limits   the JointLimits bound(s), two lines per joint (min, max)
    /world/<robot>/...                                   Rerun's own URDF loader (rerun.urdf.UrdfTree), prefix "world"
    /world/<robot>/joint_transforms/<joint>              each joint's transform on the t timeline (compute_transform_columns)
    /world/<name>/tool/{trail,ahead,point,axes,ends,stick}  the tool: given PoseTrajectory, else the URDF's end link by FK

Writes r2/<task>.rrd (the Robot tab active) for both inputs, and r2/blueprints/<task>.<tab>.rbl, one per tab, so the
shooter can open the same recording on any tab (``shoot.cjs ... --blueprint r2/blueprints/<task>.joints.rbl``).
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
import rerun.urdf as rurdf

from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as viz

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
APPLICATION_ID = "robot_msgs_joint_trajectory_r2_evo"  # one per proposal (CONTRACT.md)
TIMELINE = viz.TIMELINE
DEGREES = 180.0 / math.pi
TABS = ("Robot", "Joints", "Speed", "Acceleration", "Data")
TASKS = ("workspace-dev-029", "workspace-dev-003")

# WHY Tableau 10 (cycled past ten joints): six joints on one plot need six colours that stay apart on Rerun's dark
# background; the same joint wears the same colour on Joints, Speed and Acceleration, so a colour is a joint everywhere.
PALETTE = ((78, 121, 167), (242, 142, 43), (225, 87, 89), (118, 183, 178), (89, 161, 79),
           (237, 201, 72), (176, 122, 161), (255, 157, 167), (156, 117, 95), (186, 176, 172))
ROBOT_RGBA = (196, 202, 210, 255)  # a neutral light grey: the arm reads as the object, the coloured tool path on it
PATH_RGBA = (150, 150, 150, 170)   # the path still ahead, faint: where the tool will go (reads on light and dark)
TRAIL_RGBA = (255, 166, 0, 255)    # the path drawn so far, evo's "drawn up to the playhead"
POINT_RGBA = (255, 214, 10, 255)
STICK_RGBA = (110, 110, 110, 230)  # the end link → tool offset (a TCP the URDF has no geometry for); reads light and dark
TRAIL_VERTICES = 400               # rows of the trail/ahead strips; WHY a cap: each row holds the whole path once
AXIS_LENGTH = 0.06                 # m, the tool triad
FOV_Y_DEG = 55.0                   # Rerun's default 3D eye field of view (vertical)
LINK_MARGIN = 0.08                 # m: link meshes stand this far around their origins (a UR5e link is ~0.1 m across)


def _short(joint: str) -> str:
    """traj_compare's joint label: ``shoulder_pan_joint`` → ``shoulder pan``."""

    return joint.replace("_joint", "").replace("_", " ")


def _rgb(index: int) -> tuple[int, int, int]:
    return PALETTE[index % len(PALETTE)]


# ── the URDF: Rerun's loader for the meshes, our own FK only for framing and a tool fallback ──────────────────────


def _quat_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _matrix(transform: Any) -> np.ndarray:
    out = np.eye(4)
    out[:3, :3] = _quat_matrix(*transform.quaternion.as_arrow_array().to_pylist()[0])
    out[:3, 3] = transform.translation.as_arrow_array().to_pylist()[0]
    return out


def _link_poses(tree: Any, traj: JointTrajectory, samples: np.ndarray) -> dict[str, np.ndarray]:
    """Every link's (len(samples), 4, 4) pose in the root link's frame, by Rerun's own joint transforms.

    WHY Rerun's ``compute_transform`` and not a kinematics library: the arm drawn and the frame/tool derived from it
    come from one model, and robot_msgs + Rerun are the only dependencies the stock viewer may have."""

    index = {name: k for k, name in enumerate(traj.joint_names)}
    positions = np.asarray(traj.positions, dtype=np.float64)
    children: dict[str, list[Any]] = {}
    for joint in tree.joints():
        children.setdefault(joint.parent_link, []).append(joint)
    root = tree.root_link().name
    poses = {root: np.repeat(np.eye(4)[None], len(samples), axis=0)}
    stack = [root]
    while stack:
        parent = stack.pop()
        for joint in children.get(parent, []):
            column = index.get(joint.name)
            local = np.stack([_matrix(joint.compute_transform(float(positions[s, column]) if column is not None else 0.0,
                                                              clamp=False)) for s in samples])
            poses[joint.child_link] = poses[parent] @ local
            stack.append(joint.child_link)
    return poses


def _end_link(tree: Any, traj: JointTrajectory) -> str:
    """The link the tool rides on when no tool trajectory is given: the deepest child of a trajectory joint."""

    depth = {tree.root_link().name: 0}
    joints = list(tree.joints())
    for _ in joints:  # relax: a URDF is a tree, so len(joints) passes settle every depth
        for joint in joints:
            if joint.parent_link in depth:
                depth[joint.child_link] = depth[joint.parent_link] + 1
    moved = {joint.child_link for joint in joints if joint.name in traj.joint_names}
    below = {joint.child_link: joint.parent_link for joint in joints}

    def driven(link: str) -> bool:
        while link in below:
            if link in moved:
                return True
            link = below[link]
        return False

    return max((link for link in depth if driven(link)), key=lambda link: depth[link])


def _tool_from_fk(tree: Any, traj: JointTrajectory) -> tuple[str, np.ndarray, np.ndarray]:
    link = _end_link(tree, traj)
    pose = _link_poses(tree, traj, np.arange(len(traj.t)))[link]
    return link, pose[:, :3, 3], pose[:, :3, :3]


def _eye(tree: Any, traj: JointTrajectory, path: np.ndarray) -> Any:
    """Frame every link over the whole motion plus the tool path, from the front-right, z up.

    WHY a bounding sphere fitted to the field of view, not traj_compare's ``_stage_eye`` (seen in the real viewer,
    2026-11-24): _stage_eye scales the eye distance with the middle 90 % of link origins, which framed the 3.2 s tour
    small and cut the top off the arm on the 1.8 s A-to-B (its tool path is short, so the box was the arm's lower half).
    Every link origin over the motion and every tool sample go in; the sphere around them is fitted to Rerun's 3D
    field of view. The side it is seen from is _stage_eye's: a motion wider across y than deep along x, from the front."""

    samples = np.unique(np.linspace(0, len(traj.t) - 1, min(len(traj.t), 60)).astype(int))
    cloud = np.vstack([pose[:, :3, 3] for pose in _link_poses(tree, traj, samples).values()] + [path])
    cloud = cloud[np.all(np.isfinite(cloud), axis=1)]
    low, high = cloud.min(axis=0), cloud.max(axis=0)
    look = 0.5 * (low + high)
    spread = high - low
    radius = float(np.linalg.norm(cloud - look, axis=1).max()) + LINK_MARGIN
    direction = np.array([1.9, -1.0, 0.9]) if spread[1] > 1.2 * spread[0] else np.array([1.5, -1.9, 1.1])
    distance = radius / math.sin(math.radians(FOV_Y_DEG / 2))
    return rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1],
                             position=look + distance * direction / np.linalg.norm(direction))


# ── logging ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _revolute(tree: Any, traj: JointTrajectory) -> list[str]:
    """The joints shown in degrees: revolute/continuous in the URDF; a joint the URDF lacks is assumed revolute."""

    kinds = {joint.name: joint.joint_type for joint in tree.joints()}
    return [name for name in traj.joint_names if kinds.get(name, "revolute") in ("revolute", "continuous")]


def _style_series(rec: rr.RecordingStream, traj: JointTrajectory, name: str) -> None:
    """Name every series by its joint and give it the joint's colour.

    WHY on top of robot_msgs' series: its legend says ``name`` ("target") on every line, which is right for one plot
    per joint (target vs real) and unreadable on one plot of six joints. Static styles: the later write wins."""

    for field in ("positions", "velocities", "accelerations"):
        if getattr(traj, field) is None:
            continue
        for index, joint in enumerate(traj.joint_names):
            rec.log(f"/{field}/{viz.path_part(joint)}/{viz.path_part(name)}",
                    rr.SeriesLines(names=_short(joint), colors=[_rgb(index)], widths=2.0), static=True)


def _limit_bounds(traj: JointTrajectory) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """field → (low, high) per joint, SI, for each field the trajectory has and its JointLimits bound."""

    limits: JointLimits | None = traj.limits
    if limits is None:
        return {}
    bounds = {"positions": (limits.min_position, limits.max_position),
              "velocities": (None if limits.max_velocity is None else -limits.max_velocity, limits.max_velocity),
              "accelerations": (None if limits.max_acceleration is None else -limits.max_acceleration, limits.max_acceleration)}
    return {field: (low, high) for field, (low, high) in bounds.items()
            if low is not None and high is not None and getattr(traj, field) is not None}


def _log_limits(rec: rr.RecordingStream, traj: JointTrajectory, revolute: list[str], seconds: np.ndarray) -> None:
    """Each joint's bound as two thin lines in its colour at ``/<field>/<joint>/limits`` (an infinite bound: none)."""

    if not len(seconds):
        return
    span = np.array([seconds[0], seconds[-1]])
    for field, (low, high) in _limit_bounds(traj).items():
        for index, joint in enumerate(traj.joint_names):
            scale = DEGREES if joint in revolute else 1.0
            pair = np.array([low[index], high[index]], dtype=np.float64) * scale
            if not np.all(np.isfinite(pair)):
                continue
            r, g, b = _rgb(index)
            entity = f"/{field}/{viz.path_part(joint)}/limits"
            label = f"{_short(joint)} limit"
            rec.log(entity, rr.SeriesLines(names=[label, label], colors=[(r, g, b, 150)] * 2, widths=[1.0, 1.0]), static=True)
            rec.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=span)],
                             columns=rr.Scalars.columns(scalars=np.tile(pair, (2, 1))))


def _log_robot(rec: rr.RecordingStream, tree: Any, traj: JointTrajectory, seconds: np.ndarray) -> list[str]:
    tree.log_urdf_to_recording(recording=rec)
    links = [tree.root_link().name] + [joint.child_link for joint in tree.joints()]
    for link in links:
        for path in tree.get_visual_geometry_paths(link) or tree.get_collision_geometry_paths(link):
            rec.log(path, rr.Asset3D.from_fields(albedo_factor=ROBOT_RGBA), static=True)
    missing = [name for name in traj.joint_names if tree.get_joint_by_name(name) is None]
    if missing:
        warnings.warn(f"the URDF {tree.name!r} has no joint {missing}; the arm does not show them", stacklevel=3)
    positions = np.asarray(traj.positions, dtype=np.float64)
    for index, joint_name in enumerate(traj.joint_names):
        joint = tree.get_joint_by_name(joint_name)
        if joint is None:
            continue
        # WHY clamp=False: the stored trajectory is the truth; a value past the URDF's limit is drawn where it is
        rec.send_columns(f"/world/{viz.path_part(tree.name)}/joint_transforms/{viz.path_part(joint_name)}",
                         indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                         columns=joint.compute_transform_columns(positions[:, index].tolist(), clamp=False))
    return missing


def _strips(rec: rr.RecordingStream, entity: str, seconds: np.ndarray, strips: list[np.ndarray], rgba: Any,
            points: float) -> None:
    """One line strip per time row (latest-at shows the strip of the playhead's row)."""

    rec.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                     columns=rr.LineStrips3D.columns(strips=strips, colors=[rgba] * len(strips),
                                                     radii=[-points] * len(strips)).partition([1] * len(strips)))


def _log_tool(rec: rr.RecordingStream, base: str, frame: str, seconds: np.ndarray, path: np.ndarray,
              rotation: np.ndarray | None, label: str, flange: np.ndarray | None = None) -> None:
    """The tool in the root link's frame: the path drawn so far (orange) and still ahead (faint), the tool now with its
    triad, start/end, and — when the tool is offset from the end link — the offset as a thin stick.

    WHY "ahead" per time instead of one static full path under the trail (seen in the real viewer, 2026-11-24): two
    strips through the same points z-fight, the faint one speckling the orange trail grey."""

    where = rr.CoordinateFrame(frame)
    for leaf in ("trail", "ahead", "point", "axes", "stick"):
        rec.log(f"{base}/{leaf}", where, static=True)
    rec.log(f"{base}/ends", rr.Points3D(path[[0, -1]], colors=[(80, 200, 100), (235, 80, 80)], radii=rr.Radius.ui_points(7.0),
                                        labels=["start", "end"], show_labels=True), where, static=True)
    rec.send_columns(f"{base}/point", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                     columns=rr.Points3D.columns(positions=path, colors=[POINT_RGBA] * len(path),
                                                 radii=[-9.0] * len(path)).partition([1] * len(path)))
    rec.log(f"{base}/point", rr.Points3D.from_fields(labels=[label], show_labels=False), static=True)
    # WHY a cap of TRAIL_VERTICES rows: each row holds the whole path once (trail + ahead), O(rows x samples)
    step = max(1, math.ceil(len(path) / TRAIL_VERTICES))
    rows = sorted(set(range(0, len(path), step)) | {len(path) - 1})
    keep = np.array(rows)
    trail = [np.vstack([path[keep[keep <= i]], path[i]]) for i in rows]
    ahead = [np.vstack([path[i], path[keep[keep > i]]]) for i in rows]
    _strips(rec, f"{base}/trail", seconds[rows], trail, TRAIL_RGBA, 3.0)
    _strips(rec, f"{base}/ahead", seconds[rows], ahead, PATH_RGBA, 1.5)
    if flange is not None and np.max(np.linalg.norm(path - flange, axis=1)) > 1e-3:
        _strips(rec, f"{base}/stick", seconds, list(np.stack([flange, path], axis=1)), STICK_RGBA, 1.5)
    if rotation is not None:
        vectors = np.concatenate([rotation[:, :, axis] * AXIS_LENGTH for axis in range(3)], axis=1).reshape(-1, 3)
        origins = np.repeat(path, 3, axis=0)
        rec.send_columns(f"{base}/axes", indexes=[rr.TimeColumn(TIMELINE, duration=seconds)],
                         columns=rr.Arrows3D.columns(vectors=vectors, origins=origins,
                                                     colors=np.tile([(230, 60, 60), (60, 200, 60), (70, 120, 255)], (len(path), 1)),
                                                     ).partition([3] * len(path)))


# ── the blueprint: evo's tabs, grown ──────────────────────────────────────────────────────────────────────────────


def _ts(origin: str, title: str, **kwargs: Any) -> Any:
    """traj_compare's ``_ts``: a plot whose x zoom is linked to every other plot, legend at the top right."""

    return rrb.TimeSeriesView(origin=origin, name=title, plot_legend=rrb.PlotLegend(corner="RightTop"),
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"), **kwargs)


def blueprint(traj: JointTrajectory, tree: Any, eye: Any, *, name: str = "target", tab: str | None = None,
              revolute: list[str] | None = None, limits: list[str] = (), has_visuals: bool = False) -> Any:
    """The five tabs, opening on ``tab`` (by name; default the Robot tab)."""

    if tab is not None and tab not in TABS:
        raise ValueError(f"no tab {tab!r}; tabs: {', '.join(TABS)}")
    revolute = list(traj.joint_names) if revolute is None else revolute
    mixed = len(revolute) != len(traj.joint_names)
    unit = {"positions": "° (m prismatic)" if mixed else "°", "velocities": "°/s (m/s prismatic)" if mixed else "°/s",
            "accelerations": "°/s² (m/s² prismatic)" if mixed else "°/s²"}
    robot = viz.path_part(tree.name)
    contents = ["/world/**"] + ([f"- /world/{robot}/collision_geometries/**"] if has_visuals else [])
    world = rrb.Spatial3DView(origin="/world", contents=contents, eye_controls=eye, line_grid=rrb.LineGrid3D(visible=True),
                              name=f"{tree.name} along the trajectory — the tool: path so far (orange), still ahead "
                                   f"(grey), now (yellow, with its axes)")
    duration = float(traj.t[-1] - traj.t[0]) if len(traj.t) else 0.0
    tabs = [rrb.Horizontal(world, name="Robot")]

    def plot(field: str, what: str, tab_name: str, bound: str) -> Any:
        against = f", against {bound}" if field in limits else ""
        # WHY wrapped: a tab's label is its container's name, so the tab reads "Joints" and the plot keeps its title
        return rrb.Horizontal(_ts(f"/{field}", f"{what} of all {traj.n_joints} joints [{unit[field]}]{against} — "
                                               f"{duration:.2f} s"), name=tab_name)

    tabs.append(plot("positions", "Joint angles q", "Joints", "each joint's position limits"))
    if traj.velocities is not None:
        tabs.append(plot("velocities", "Joint speeds qd", "Speed", "±max velocity"))
    if traj.accelerations is not None:
        tabs.append(plot("accelerations", "Joint accelerations qdd", "Acceleration", "±max acceleration"))
    # WHY select: robot_msgs' static SeriesLines (colour, name, width) would add three columns per joint; the table is t
    # and q. WHY the selector object: the "/path:Component" string form splits on one ':' and 0.40's component id is
    # "Scalars:scalars". auto_scroll: the row at the playhead stays in view, so the table scrubs with the arm.
    q_paths = [f"/positions/{viz.path_part(j)}/{viz.path_part(name)}" for j in traj.joint_names]
    columns = [rrb.components.ComponentColumnSelector(entity_path=p, component="Scalars:scalars") for p in q_paths]
    table = rrb.DataframeView(origin="/positions", contents=q_paths,
                              name=f"The samples: t and q of each joint [{unit['positions']}], scrolled to the playhead",
                              query=rrb.archetypes.DataframeQuery(timeline=TIMELINE, auto_scroll=True, entity_order=q_paths,
                                                                  select=[TIMELINE] + columns))
    tabs.append(rrb.Horizontal(table, name="Data"))
    names = [container.name for container in tabs]
    active = 0 if tab is None else names.index(tab) if tab in names else 0
    return rrb.Blueprint(
        rrb.Tabs(*tabs, active_tab=active),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        # WHY paused: it opens on the start pose with the whole path ahead, and the playhead stays where the reviewer
        # puts it (space plays). A playing blueprint's playhead lands anywhere headless (software rendering plays ~5x
        # slow). Measured 2026-11-24: shoot.cjs's #when=t@<s> does not move it either way; r2/shoot_at.cjs seeks.
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused"),
    )


def save(path: str | Path, traj: JointTrajectory, robot: str | Path, *, tool: PoseTrajectory | None = None,
         name: str = "target", tab: str | None = None, application_id: str = APPLICATION_ID,
         blueprints: str | Path | None = None) -> Path:
    """One JointTrajectory + its URDF → one ``.rrd`` with the evo-tabs blueprint embedded.

    ``tool`` is the tool's PoseTrajectory in the URDF root link's frame, on the trajectory's clock (default: the
    URDF's end link by FK — the flange, with no TCP offset). ``name`` is the robot_msgs series name (``target``, as
    traj_compare names a reference, so a ``real`` run overlays). ``blueprints``: a folder to also write one
    ``<stem>.<tab>.rbl`` per tab into, each opening the recording on that tab."""

    path = Path(path)
    tree = rurdf.UrdfTree.from_file_path(robot, "world")
    t = np.asarray(traj.t, dtype=np.float64)
    seconds = t - t[0]
    revolute = _revolute(tree, traj)
    end_link, end_xyz, end_rot = _tool_from_fk(tree, traj)
    if tool is not None:
        label = tool.child_frame_id or "tool"
        tool_t = np.asarray(tool.t, dtype=np.float64) - t[0]
        tool_xyz = np.asarray(tool.positions, dtype=np.float64)
        tool_rot = tool.matrices()[:, :3, :3]
        flange = np.stack([np.interp(tool_t, seconds, end_xyz[:, axis]) for axis in range(3)], axis=1)
    else:
        label, tool_xyz, tool_rot, tool_t, flange = end_link, end_xyz, end_rot, seconds, None
    has_visuals = any(tree.get_visual_geometry_paths(joint.child_link) for joint in tree.joints())
    eye = _eye(tree, traj, tool_xyz)
    options = dict(name=name, revolute=revolute, limits=list(_limit_bounds(traj)), has_visuals=has_visuals)
    rec = rr.RecordingStream(application_id)
    # WHY the blueprint first (default_blueprint=, seen in the real viewer 2026-11-24): sent after the data, playback
    # ran one frame before the paused TimePanel arrived and the recording opened at +0.1 s instead of the start
    rec.save(path, default_blueprint=blueprint(traj, tree, eye, tab=tab, **options))
    viz.log(traj, name, recording=rec, degrees=revolute)
    viz._PATHS.pop(id(rec), None)  # WHY: we send our own blueprint; robot_msgs' path registry would only leak
    _style_series(rec, traj, name)
    _log_limits(rec, traj, revolute, seconds)
    _log_robot(rec, tree, traj, seconds)
    _log_tool(rec, f"/world/{viz.path_part(name)}/tool", tree.root_link().name, tool_t, tool_xyz, tool_rot, label, flange)
    rec.flush()
    rec.disconnect()
    if blueprints is not None:
        folder = Path(blueprints)
        folder.mkdir(parents=True, exist_ok=True)
        for tab_name in TABS:
            blueprint(traj, tree, eye, tab=tab_name, **options).save(application_id, folder / f"{path.stem}.{tab_name.lower()}.rbl")
    return path


# ── the two inputs ────────────────────────────────────────────────────────────────────────────────────────────────


def load(task: str) -> tuple[JointTrajectory, PoseTrajectory]:
    data = np.load(ROUND / "data" / f"{task}.npz")
    names = tuple(str(n) for n in data["names"])
    limits = JointLimits(joint_names=names, min_position=data["lo"], max_position=data["hi"],
                         max_velocity=data["vmax"], max_acceleration=data["amax"])
    optional = {key: data[key] for key in ("qd", "qdd") if data[key].size}
    traj = JointTrajectory(t=data["t"], joint_names=names, positions=data["q"], velocities=optional.get("qd"),
                           accelerations=optional.get("qdd"), limits=limits)
    rot = data["tool_rot"]
    matrices = np.repeat(np.eye(4)[None], len(data["t"]), axis=0)
    matrices[:, :3, :3], matrices[:, :3, 3] = rot, data["tool_xyz"]
    tool = PoseTrajectory.from_matrices(data["t"], matrices, child_frame_id="tcp")
    return traj, tool


def main() -> None:
    urdf = ROUND / "data" / "robot" / "ur5e_collision.urdf"
    for task in TASKS:
        traj, tool = load(task)
        out = save(HERE / f"{task}.rrd", traj, urdf, tool=tool, blueprints=HERE / "blueprints")
        print(out, f"{out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
