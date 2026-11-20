"""A one-joint series may log its motor current flat, (N,), as Run.torques accepts 1-D (NAVIGATION.md C1, amended 2026-11-20).

The arm_motion_bench pendulum is 1-DOF and records current as one column; on two or more joints a flat current names no joint
and stays refused (tests/test_signals_channels.py). Written by the dispatcher beside its two-line change.
"""

import json
import re

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, build_drill_down, write_dataset_report


def _pendulum(current: np.ndarray | None = None) -> JointTrajectory:
    t = np.linspace(0.0, 2.0, 201)
    channels = {} if current is None else {"current": current}
    return JointTrajectory(t=t, joint_names=("pivot",), positions=np.sin(t)[:, None], channels=channels)


def test_a_one_joint_current_logged_flat_is_drawn_as_that_joints_motor_current(tmp_path):
    amps = np.linspace(0.1, 0.9, 201)
    run = Run(name="pendulum rep 0", reference=_pendulum(), measured={"real": _pendulum(amps)})
    write_dataset_report([run], tmp_path, title="Pendulum", rows=())
    html = build_drill_down(tmp_path, run.name).read_text("utf-8")
    payload = json.loads(re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    drawn = [entry for comparison in payload["comparisons"] for entry in comparison.get("runs", comparison.get("situations", []))
             if isinstance(entry, dict) and entry.get("plot", {}).get("current") is not None]
    assert drawn, "the flat one-joint current reached no situation's plot"
    values = np.asarray(drawn[0]["plot"]["current"], dtype=float).reshape(-1)
    assert values.min() >= 0.1 - 1e-3 and values.max() <= 0.9 + 1e-3


def test_a_flat_current_on_two_joints_is_still_refused(tmp_path):
    t = np.linspace(0.0, 2.0, 201)
    two = JointTrajectory(t=t, joint_names=("a", "b"), positions=np.zeros((201, 2)), channels={"current": np.ones(201)})
    reference = JointTrajectory(t=t, joint_names=("a", "b"), positions=np.zeros((201, 2)))
    with pytest.raises(ValueError, match="current"):
        write_dataset_report([Run(name="two", reference=reference, measured={"real": two})], tmp_path, title="Two", rows=())
