#!/usr/bin/env python3
"""Shared inputs for the Rerun JointTrajectory round (babble, 2026-11-24): one real UR5e dataset trajectory and the UR5e URDF.

    env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/extract.py

Writes data/ (gitignored): trajectory.npz (t, joint names, q in rad, the UR5e JointLimits, the tool pose in the base
frame), trajectory.json (what it is), and data/robot/ (bam_collision's ur5e_collision.urdf + the official UR5e
collision STLs, LICENSE beside them; copied by the dispatcher: Rerun 0.40 cannot load ur_description's .dae visuals and
no xacro is installed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/bam/arm_motion_bench/docs")
import build_ur_coverage_1123 as ur  # noqa: E402
from arm_motion_bench.datasets import load_dataset  # noqa: E402

HERE = Path(__file__).resolve().parent
TASKS = ("workspace-dev-029", "workspace-dev-003")  # a multi-waypoint tour (adds the most cells) and a short A to B


def main() -> None:
    ds = load_dataset(ur.REPO / "datasets/ur5e_alone/workspace/v2")
    out = {}
    for task in TASKS:
        target = ds.target(task, 1.0)
        t, position, rotation = ds.target_tcp(task, 1.0)
        meta = next(x for x in ds.tasks if x.task_id == task)
        limits = target.limits
        np.savez(HERE / "data" / f"{task}.npz", t=np.asarray(target.t), names=np.array(target.joint_names),
                 q=np.asarray(target.positions), qd=np.asarray(target.velocities) if target.velocities is not None else np.zeros(0),
                 qdd=np.asarray(target.accelerations) if target.accelerations is not None else np.zeros(0),
                 tool_xyz=np.asarray(position), tool_rot=np.asarray(rotation),
                 lo=np.asarray(limits.min_position), hi=np.asarray(limits.max_position),
                 vmax=np.asarray(limits.max_velocity), amax=np.asarray(limits.max_acceleration))
        out[task] = {"kind": meta.kind, "split": meta.split, "tags": list(meta.tags or []), "duration_s": float(target.t[-1] - target.t[0]),
                     "samples": len(target.t), "joint_names": list(target.joint_names), "tool_frame": "base"}
    (HERE / "data" / "trajectory.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
