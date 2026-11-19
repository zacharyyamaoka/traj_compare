"""REAL data through the torque breakdown: the CAN 11 pendulum, round 9 (2026-11-17), five repeats of one speed.

What the 1-DOF logger records per run (bam_rack_twin/hardware/board.py): q_target, qd_target, q, qd, the reply
torque `tau` (applied), and the host's model feedforward `ff_model_nm`. It does NOT query moteus's `control_torque`,
so the commanded torque — and with it the feedback part (commanded − feedforward) — is not on disk. This adapter
passes exactly what exists: target τ (the model torque for the target), feedforward, applied. The breakdown section
then shows the gap between applied and feedforward, and honestly no commanded/feedback trace.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19
    ../../.venv/bin/python real_can11.py --speed f0.6 --out /tmp/real-can11
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from traj_compare import Comparison, Situation, write_comparison_report

ROUND9 = Path("/archive/datasets/bam_rig/onedof_2026-11-15/round9/real/can11")


def _runs(speed: str) -> list[tuple[str, dict]]:
    session = json.loads((ROUND9 / "session.json").read_text())
    found = []
    for step in session["steps"]:
        label = step.get("label", "")
        # WHY repeats only: the held-out runs at a speed follow other targets; only repeats share this one
        if step["kind"] != "waypoints" or f" {speed} repeat " not in f"{label} ":
            continue
        npz = next(path for path in step["files"] if path.endswith(".npz"))
        found.append((label, dict(np.load(ROUND9 / npz))))
    return found


def comparison(speed: str) -> Comparison:
    runs = _runs(speed)
    if not runs:
        raise SystemExit(f"no round 9 runs at {speed}")
    first = runs[0][1]
    # WHY the first repeat's ff_model_nm as the target torque: it is the model's torque along the target, which is
    # what "target torque" means; every repeat follows the same target, so any repeat's copy is the same curve.
    target = Situation(name="target", title="Target", t=first["t"], q=first["q_target"], qd=first["qd_target"],
                       tau=first["ff_model_nm"])  # fmt: skip
    situations = []
    for label, record in runs:
        tail = label.split(f"{speed} ")[1]
        name = tail.split(" ")[0] + "-" + tail.split(" ")[1].replace("/", "of")
        situations.append(Situation(
            name=name, title=tail.split(" r8")[0], t=record["t"], q=record["q"], qd=record["qd"], tau=record["tau"],
            tau_ff=record["ff_model_nm"], group="real", group_title="Real repeats",
            note="commanded torque not logged (control_torque is not queried)",
        ))  # fmt: skip
    repeats = [situation.name for situation in situations if situation.group == "real"]
    return Comparison(
        title=f"CAN 11 pendulum · round 9 · {speed}", name=f"can11-r9-{speed}", joint_names=["can11"],
        target=target, situations=situations, repeat_groups={f"Real ×{len(repeats)}": repeats},
        description="REAL hardware, 2026-11-17. Feedforward = host model torque (ff_model_nm); applied = moteus reply "
        "torque. Commanded torque (control_torque) is not logged, so feedback cannot be shown.",
        default_sections=["joint-q", "joint-err", "joint-torque"],
    )  # fmt: skip


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", default="f0.6")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rerun", action="store_true")
    args = parser.parse_args()
    print(write_comparison_report([comparison(args.speed)], args.out, rerun=args.rerun))
