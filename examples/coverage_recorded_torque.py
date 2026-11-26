"""Trajectory coverage of RECORDED runs, with their torque, beside the planned tapes they followed.

    uv --directory /home/bam/traj_compare run --all-extras python examples/coverage_recorded_torque.py \
        --out /home/bam/traj_compare/reports/media/coverage-recorded-torque

Zach, 2026-11-26: "it may be useful to see like the torque information of the trajecotries ... planend trajectories
don't have. but mabye you want to use this actually to look a bunch of recorded trajectories that do have that
information!" Reads the Trajectory Tracking Agent's recorded traces (`*.trace.npz`: t, q, qd, tau, target_q/qd/qdd) of
the BAM FB arm on the workspace v2 dataset, and arm_motion_bench's station.json for the joint limits (torque limit =
the drive's peak torque, the controller's torque cap as the dashed planner limit). Each trace gives two trajectories:
the recorded one (q, qd, tau: jerk and acceleration computed) and the planned target it followed (no torque), so the
page shows torque only where it was measured. The traces are MuJoCo runs (meta domain "sim"), not hardware.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from robot_msgs.trajectory import JointLimits, JointTrajectory

from traj_compare.coverage import analyze
from traj_compare.coverage.workbench import write_workbench

TRACES = Path("/home/bam/trajectory_tracking_agent/outputs/bam-fb-workspace")
STATION = Path("/home/bam/arm_motion_bench/datasets/bam_fb/workspace/v2/station.json")
RUNS = {  # controller folder -> its label; the reference JTC and the calibrated controller Zach's agent landed on
    "reference-fresh/bam_fb/jtc_baseline/workspace-v2": "jtc_baseline",
    "public-calibrated-x8hold8-traces/bam_fb/public-calibrated-x8hold8/workspace-v2": "public-calibrated-x8hold8",
}


def limits(station: dict, effort_key: str) -> JointLimits:
    joints = station["joints"]
    return JointLimits(
        joint_names=tuple(joint["name"] for joint in joints),
        min_position=np.array([joint["position_min_rad"] for joint in joints]),
        max_position=np.array([joint["position_max_rad"] for joint in joints]),
        max_velocity=np.array([joint["velocity_max_rad_s"] for joint in joints]),
        max_acceleration=np.array([joint["acceleration_max_rad_s2"] for joint in joints]),
        max_effort=np.array([joint[effort_key] for joint in joints]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kit", default=None, help="a vendored data-ui kit's href (default: vendor data-ui main)")
    args = parser.parse_args()
    station = json.loads(STATION.read_text())
    joint_limits, cap = limits(station, "torque_peak_nm"), limits(station, "torque_cap_nm")
    names = joint_limits.joint_names
    trajectories, tags = {}, {}
    planned_done = set()
    for folder, controller in RUNS.items():
        for trace in sorted((TRACES / folder).glob("*/*.trace.npz")):
            with np.load(trace) as arrays:
                meta = json.loads(str(arrays["meta"]))
                t = np.asarray(arrays["t"], float)
                recorded = JointTrajectory(t=t, joint_names=names, positions=arrays["q"], velocities=arrays["qd"],
                                           effort=arrays["tau"], limits=joint_limits)
                planned = JointTrajectory(t=t, joint_names=names, positions=arrays["target_q"],
                                          velocities=arrays["target_qd"], accelerations=arrays["target_qdd"],
                                          limits=joint_limits)
            task = meta["task_id"]
            name = f"recorded/{controller}/{task}"
            trajectories[name] = recorded
            tags[name] = {"source": f"recorded · {controller}", "split": meta["split"], "domain": meta["domain"],
                          "task": task}
            if task not in planned_done:  # every controller followed the same tape: one planned copy per task
                planned_done.add(task)
                trajectories[f"planned/{task}"] = planned
                tags[f"planned/{task}"] = {"source": "planned tape", "split": meta["split"], "domain": "plan",
                                           "task": task}
    title = "BAM FB · workspace v2 · recorded vs planned"
    subtitle = (f"{len(trajectories)} trajectories: the Trajectory Tracking Agent's recorded MuJoCo runs (with torque) "
                "and the planned tapes they followed (no torque). Torque limit = drive peak; dashed = controller cap.")
    coverage = analyze(trajectories, tags=tags, group_by="source", planner_limits=cap, title=title, subtitle=subtitle)
    out = write_workbench(coverage, trajectories, args.out, title=title, subtitle=subtitle, dataset="source",
                          facets=("split", "domain"), kit=args.kit)
    print(json.dumps({"page": str(out), "signals": coverage.payload["signals"],
                      "signal_source": coverage.payload["signal_source"],
                      "tau_peak_max_pct": coverage.numbers.get("tau_peak_max_pct")}))


if __name__ == "__main__":
    main()
