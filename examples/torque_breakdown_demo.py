"""The torque breakdown on a toy vertical 2R arm: target, commanded, feedforward, feedback, applied.

SIMULATED. Each joint runs moteus-style control at 1 kHz: commanded = clip(feedforward + kp·e +
kd·ė), a current loop that delivers it through a 1.5 ms lag with a 3 % torque-constant error,
recorded at 100 Hz. "ff v1" uses a feedforward model that underestimates gravity by 20 % and knows
no friction, so its feedback slopes with the arm's angle; "ff v2" uses the true model, so its
feedback stays small. The runs record different pairs (v1: feedforward + feedback, v2: commanded +
feedforward), so the report derives the third and says so. The arm is the L1/L2 chain of
tracking_errors_demo.py, each joint treated as its own pendulum.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    uv run python examples/torque_breakdown_demo.py --out /tmp/torque_breakdown_demo

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    uv run --extra rerun python examples/torque_breakdown_demo.py --out /tmp/torque_breakdown_demo --rerun
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from tracking_errors_demo import joint_path, l2_tip_fk

from traj_compare import Comparison, Situation, write_comparison_report

INERTIA = np.array([0.050, 0.012])  # kg·m² seen by each joint
GRAVITY_NM = np.array([1.60, 0.45])  # peak gravity torque of each joint
VISCOUS = np.array([0.08, 0.03])  # N·m·s/rad
KP, KD = np.array([40.0, 15.0]), np.array([1.2, 0.4])
MAX_TORQUE_NM = np.array([4.0, 1.5])
CONTROL_HZ, RECORD_HZ = 1000, 100


def torque_needed(q, qd, qdd, gravity_scale=1.0, viscous=VISCOUS):
    """Inverse dynamics of the toy arm: inertia + gravity (joint 2 hangs on q1 + q2) + viscous friction."""

    gravity = GRAVITY_NM * np.column_stack([np.cos(q[:, 0]), np.cos(q[:, 0] + q[:, 1])])
    return INERTIA * qdd + gravity_scale * gravity + viscous * qd


def simulate(t, gravity_scale, viscous):
    """The 1 kHz loop on the true arm with a feedforward from the given model; 100 Hz records (SI)."""

    q_target = joint_path(t)
    qd_target = np.gradient(q_target, t, axis=0)
    qdd_target = np.gradient(qd_target, t, axis=0)
    feedforward = torque_needed(q_target, qd_target, qdd_target, gravity_scale, viscous)
    q, qd, applied = q_target[0].copy(), np.zeros(2), feedforward[0].copy()
    rows = {key: np.zeros((t.size, 2)) for key in ("q", "tau_cmd", "tau_ff", "tau_fb", "tau")}
    for index in range(t.size):
        feedback = KP * (q_target[index] - q) + KD * (qd_target[index] - qd)
        command = np.clip(feedforward[index] + feedback, -MAX_TORQUE_NM, MAX_TORQUE_NM)
        applied += (1.0 / CONTROL_HZ / 0.0015) * (0.97 * command - applied)
        record = {"q": q, "tau_cmd": command, "tau_ff": feedforward[index], "tau_fb": feedback, "tau": applied}
        for key, value in record.items():
            rows[key][index] = value
        qdd = (applied - torque_needed(q[None], qd[None], np.zeros((1, 2)))[0]) / INERTIA
        qd = qd + qdd / CONTROL_HZ
        q = q + qd / CONTROL_HZ
    step = CONTROL_HZ // RECORD_HZ
    return {key: value[::step] for key, value in rows.items()}


def build(out_dir: Path, rerun: bool = False) -> Path:
    t = np.arange(0.0, 3.6, 1.0 / CONTROL_HZ)
    recorded_t = t[:: CONTROL_HZ // RECORD_HZ]
    q_target = joint_path(recorded_t)
    qd_target = np.gradient(q_target, recorded_t, axis=0)
    target = Situation(name="target", title="Target", t=recorded_t, q=q_target,
                       tau=torque_needed(q_target, qd_target, np.gradient(qd_target, recorded_t, axis=0)))  # fmt: skip
    v1 = simulate(t, gravity_scale=0.8, viscous=np.zeros(2))
    v2 = simulate(t, gravity_scale=1.0, viscous=VISCOUS)
    runs = [
        Situation(name="real_v1", title="Real · ff v1", t=recorded_t, q=v1["q"], tau=v1["tau"],
                  tau_ff=v1["tau_ff"], tau_fb=v1["tau_fb"]),  # commanded derived
        Situation(name="real_v2", title="Real · ff v2", t=recorded_t, q=v2["q"], tau=v2["tau"],
                  tau_cmd=v2["tau_cmd"], tau_ff=v2["tau_ff"]),  # feedback derived
    ]  # fmt: skip
    comparison = Comparison(
        title="Planar 2R swing · torque breakdown", joint_names=["j1", "j2"], target=target, situations=runs,
        fk=l2_tip_fk, tcp_frame="L2 tip", default_sections=["joint-q", "joint-torque"],
    )  # fmt: skip
    return write_comparison_report([comparison], out_dir, title="Torque breakdown", rerun=rerun)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("/tmp/torque_breakdown_demo"))
    parser.add_argument(
        "--rerun", action="store_true", help="also write rerun/<name>.rrd and the Open in Rerun button"
    )
    args = parser.parse_args()
    print(build(args.out, rerun=args.rerun))
