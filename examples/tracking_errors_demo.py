"""Standard tracking-error fields on a toy planar 2R arm (a five-bar's L1/L2 chain).

One target and two runs. "Sim (lagging)" follows the same joint path 40 ms
late. "Real (offset)" is on time, but J2 reads 1.5° high. Together they show
every standard field: joint q/qd/qdd and error, the L2-tip pose per axis,
|Δp| / rotation, cross-track vs lag, per-axis x/y/z/rx/ry/rz error,
and the RMS · max · final table. Tolerances give each run a verdict (the lagging sim breaks the
30 mrad path limit; the offset real stays on path but misses the 5 mrad goal), the latency estimate
reads the sim's 40 ms back, and the error is also read along named axes.

    uv run --directory ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare python examples/tracking_errors_demo.py --out /tmp/tracking_errors_demo
    uv run --extra rerun --directory ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare python examples/tracking_errors_demo.py --out /tmp/tracking_errors_demo --rerun
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from robot_msgs.compare import JointTolerance, PoseTolerance, Tolerances

from traj_compare import Comparison, Situation, write_comparison_report

L1_M = 0.30
L2_M = 0.25
LAG_S = 0.04
J2_BIAS_RAD = np.radians(1.5)


def l2_tip_fk(q: np.ndarray) -> np.ndarray:
    """(N, 2) joint angles -> (N, 4, 4) pose of the L2 tip, yaw = j1 + j2."""

    j1, j2 = q[:, 0], q[:, 1]
    yaw = j1 + j2
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, 0, 0] = np.cos(yaw)
    poses[:, 0, 1] = -np.sin(yaw)
    poses[:, 1, 0] = np.sin(yaw)
    poses[:, 1, 1] = np.cos(yaw)
    poses[:, 0, 3] = L1_M * np.cos(j1) + L2_M * np.cos(yaw)
    poses[:, 1, 3] = L1_M * np.sin(j1) + L2_M * np.sin(yaw)
    return poses


def joint_path(t: np.ndarray) -> np.ndarray:
    """Rest, a smooth swing out and back, rest."""

    phase = np.clip((t - 0.3) / 3.0, 0.0, 1.0)
    swing = 0.5 - 0.5 * np.cos(2.0 * np.pi * phase)  # 0 -> 1 -> 0, zero velocity at the ends
    return np.column_stack([0.2 + 0.9 * swing, 0.6 + 0.7 * swing])


def build(out_dir: Path, rerun: bool = False) -> Path:
    t = np.linspace(0.0, 3.6, 1801)
    target = Situation(name="target", title="Target", t=t, q=joint_path(t))
    sim = Situation(name="sim", title="Sim (lagging)", t=t, q=joint_path(t - LAG_S))
    real_q = joint_path(t)
    real_q[:, 1] += J2_BIAS_RAD
    real = Situation(name="real", title="Real (offset)", t=t, q=real_q)
    comparison = Comparison(
        title="Planar 2R swing",
        joint_names=["j1", "j2"],
        target=target,
        situations=[sim, real],
        fk=l2_tip_fk,
        tcp_frame="L2 tip",
        default_sections=["joint-q", "joint-err", "tcp-err"],
        tolerances=Tolerances(
            path=(JointTolerance(name="j1", position=0.030), JointTolerance(name="j2", position=0.030)),
            goal=(JointTolerance(name="j1", position=0.005), JointTolerance(name="j2", position=0.005)),
            stopped_velocity_tolerance=0.0,  # positions only: the runs record no velocities
        ),
        tcp_tolerances=Tolerances(
            path=PoseTolerance(position=0.015), goal=PoseTolerance(position=0.005),
            stopped_velocity_tolerance=0.0,
        ),
        goal_band=0.005,
        tcp_goal_band=0.002,
        estimate_latency=True,
        error_axes=[("world x", np.array([1.0, 0.0, 0.0])), ("world y", np.array([0.0, 1.0, 0.0]))],
    )
    return write_comparison_report(
        [comparison], out_dir, title="Standard tracking-error fields", rerun=rerun
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("/tmp/tracking_errors_demo"))
    parser.add_argument(
        "--rerun", action="store_true", help="also write rerun/<name>.rrd and the Open in Rerun button"
    )
    args = parser.parse_args()
    print(build(args.out, rerun=args.rerun))
