"""The round's two scenarios as robot_msgs messages (the dispatcher's; lanes import it, never edit it).

    import sys; sys.path.insert(0, "/home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24")
    from fixture import plan, run, URDF

- plan(): the dataset tour workspace-dev-029 alone (3.2 s, six UR5e joints): (JointTrajectory with q/qd/qdd + the
  UR5e JointLimits, tool PoseTrajectory). What "Open in Rerun" shows for a dataset row today.
- run(solution="p6s"): the Trajectory Tracking Agent's saved run of that task: (target JointTrajectory, solution
  JointTrajectory (the joint encoders; q only, qd/qdd by central differences), target tool PoseTrajectory, solution tool
  PoseTrajectory, extras). Both tools are the dataset's tool point (its fixed
  offset in the flange frame) on the URDF's forward kinematics of each joint path, so both share one FK (the
  agent's own tool point is in MuJoCo Menagerie's base frame, ~0.5 m from the URDF's). extras: tool_error_mm (the agent's own ruler, per sample), tau_pct, qd_pct (% of cap / limit), label, score.
  "p6s" = best of generation 0 (1.09 mm RMS on this task); "p5s-pass3" = best so far (0.039 mm).
- URDF: the UR5e collision URDF (official meshes; joint names match).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
URDF = DATA / "robot" / "ur5e_collision.urdf"


def _limits(d, names):
    from robot_msgs.trajectory import JointLimits
    return JointLimits(joint_names=names, min_position=d["lo"], max_position=d["hi"], max_velocity=d["vmax"], max_acceleration=d["amax"])


def _flange(t: np.ndarray, names: tuple, q: np.ndarray) -> np.ndarray:
    from rerun.urdf import UrdfTree
    from robot_msgs.viz import rerun as viz
    tree = UrdfTree.from_file_path(str(URDF))
    traj = JointTrajectory(t=t, joint_names=names, positions=q)
    return viz._forward_kinematics(tree, viz._joint_values(tree, traj), len(t))["wrist_3_link"]


def _pose(t, positions, rotations) -> PoseTrajectory:
    from robot_msgs.geometry.rotations import quat_from_matrix
    from robot_msgs.std import Header
    return PoseTrajectory(t=t, positions=positions, orientations=quat_from_matrix(rotations),
                          header=Header(frame_id="base_link_ur"), child_frame_id="tool")


def _tool(t: np.ndarray, names: tuple, q: np.ndarray, d) -> PoseTrajectory:
    """The dataset's tool point carried by q: its fixed offset in the flange frame (from the dataset's own FK), on
    the URDF's flange at q."""
    target_flange = _flange(d["t"], names, d["q"])
    offset = np.median(np.einsum("nji,nj->ni", target_flange[:, :3, :3], d["tool_xyz"] - target_flange[:, :3, 3]), axis=0)
    flange = _flange(t, names, q)
    positions = flange[:, :3, 3] + np.einsum("nij,j->ni", flange[:, :3, :3], offset)
    tool_in_flange = np.einsum("nji,njk->nik", target_flange[:, :3, :3], d["tool_rot"])[len(d["t"]) // 2]
    return _pose(t, positions, np.einsum("nij,jk->nik", flange[:, :3, :3], tool_in_flange))


def _rates(t: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    qd = np.gradient(q, t, axis=0)
    return qd, np.gradient(qd, t, axis=0)


def plan():
    d = np.load(DATA / "workspace-dev-029.npz")
    names = tuple(str(n) for n in d["names"])
    traj = JointTrajectory(t=d["t"], joint_names=names, positions=d["q"], velocities=d["qd"], accelerations=d["qdd"], limits=_limits(d, names))
    return traj, _pose(d["t"], d["tool_xyz"], d["tool_rot"])


def run(solution: str = "p6s"):
    d = np.load(DATA / "workspace-dev-029.npz")
    a = np.load(DATA / "tta-dev-029.npz")
    meta = json.loads((DATA / "tta.json").read_text())
    names = tuple(str(n) for n in d["names"])
    t = a["t"]
    target = JointTrajectory(t=t, joint_names=names, positions=d["q"], velocities=d["qd"], accelerations=d["qdd"], limits=_limits(d, names))
    q = a[f"q_{solution}"]
    qd, qdd = _rates(t, q)
    measured = JointTrajectory(t=t, joint_names=names, positions=q, velocities=qd, accelerations=qdd, limits=_limits(d, names))
    info = next(s for s in meta["solutions"] if s["id"] == solution)
    extras = {"tool_error_mm": a[f"tool_error_{solution}"], "tau_pct": a[f"tau_pct_{solution}"], "qd_pct": a[f"qd_pct_{solution}"],
              "label": f"{solution}: {info['label']}", "rms_mm": info["tool_track_rms_mm_on_this_task"], "commit": meta["commit"]}
    return target, measured, _tool(t, names, d["q"], d), _tool(t, names, q, d), extras
