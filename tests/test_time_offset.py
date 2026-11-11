"""Situation.time_offset_s reaches every robot_msgs.compare call for that run.

A run that is 20 ms late shows a lag error and breaks a tight path tolerance; told its clock runs
20 ms late (the latency estimate), what is left is the error that is not a delay.
"""

import numpy as np
import pytest
from robot_msgs.compare import JointTolerance, Tolerances, compare
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Comparison, Situation
from traj_compare.analysis import analyze_comparison

DELAY = 0.020
T = np.linspace(0.0, 2.4, 1201)
# WHY longer: shifted back by 20 ms the run's last sample must still reach the reference's end,
# or the goal phase is never observed (check says GOAL_TOLERANCE_VIOLATED, rightly)
T_RUN = np.linspace(0.0, 2.6, 1301)


def path(t):
    phase = np.clip((t - 0.2) / 1.6, 0.0, 1.0)
    return np.column_stack([0.3 * (0.5 - 0.5 * np.cos(np.pi * phase))])


def translation_fk(q):
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, 0, 3] = q[:, 0]
    return poses


def comparison(offset=0.0, **kwargs):
    late = Situation(
        name="late", title="Late", t=T_RUN, q=path(T_RUN - DELAY) + 0.0005, time_offset_s=offset
    )
    return Comparison(
        title="Offset", joint_names=["j"], target=Situation(name="target", t=T, q=path(T)),
        situations=[late], fk=translation_fk, **kwargs,
    )  # fmt: skip


def entry(payload):
    return next(item for item in payload["situations"] if item["name"] == "late")


def test_error_equals_robot_msgs_compare_at_that_offset():
    payload = analyze_comparison(comparison(DELAY))
    late = entry(payload)
    reference = JointTrajectory(t=T, joint_names=("j",), positions=path(T))
    run = JointTrajectory(t=T_RUN, joint_names=("j",), positions=path(T_RUN - DELAY) + 0.0005)
    expected = compare(reference, run, time_offset_s=DELAY)
    assert late["error_metrics"]["positions/j"]["rms"] == pytest.approx(
        expected.metrics["positions/j"].rms
    )
    assert late["error_metrics"]["time_offset_s"] == pytest.approx(DELAY)
    assert late["time_offset_s"] == pytest.approx(DELAY)
    unshifted = entry(analyze_comparison(comparison()))
    assert unshifted["error_metrics"]["positions/j"]["rms"] > 5 * late["error_metrics"]["positions/j"]["rms"]


def test_verdict_goal_and_tcp_follow_the_offset():
    tolerances = Tolerances(
        path=(JointTolerance(name="j", position=0.002),),
        goal=(JointTolerance(name="j", position=0.002),),
        stopped_velocity_tolerance=0.0,
    )
    options = dict(tolerances=tolerances, goal_band=0.002)
    assert entry(analyze_comparison(comparison(**options)))["verdict"]["joint"]["code_name"] == (
        "PATH_TOLERANCE_VIOLATED"
    )
    payload_shifted = analyze_comparison(comparison(DELAY, **options))
    shifted = entry(payload_shifted)
    assert shifted["verdict"]["joint"]["code_name"] == "SUCCESSFUL"
    plot_t = np.array(payload_shifted["plot_t"], dtype=float)
    swing = (plot_t > 0.5) & (plot_t < 1.8)  # at rest the nearest point on the path is ambiguous
    lag_time = np.array([np.nan if v is None else v for v in shifted["plot"]["lag_time"]])
    assert abs(np.nanmedian(lag_time[swing])) < 5e-3  # was 20 ms; the 0.5 mm bias alone reads as ~2 ms


def test_aggregate_uses_each_runs_offset():
    runs = [
        Situation(name=f"r{i}", t=T, q=path(T - DELAY) + 0.0002 * i, time_offset_s=DELAY)
        for i in range(3)
    ]
    comp = Comparison(
        title="Agg", joint_names=["j"], target=Situation(name="target", t=T, q=path(T)),
        situations=runs, fk=translation_fk, repeat_groups={"g": ["r0", "r1", "r2"]},
    )  # fmt: skip
    block = analyze_comparison(comp)["aggregates"]["g"]
    assert block["joint"]["accuracy"]["positions/j"]["max_abs"] < 1e-3  # the 20 ms bias is removed


def test_status_cell_and_validation():
    payload = analyze_comparison(comparison(DELAY))
    assert any("shifted 20.0 ms" in cell for row in payload["statistics"]["rows"] for cell in row["cells"])
    with pytest.raises(ValueError, match="finite"):
        Situation(name="x", t=T, q=path(T), time_offset_s=float("nan"))
