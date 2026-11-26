"""Signed limits and optional physical channels reach the native plot payload."""

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory

from traj_compare import Comparison, Situation, analyze_comparison
from traj_compare.dataset import Run, _RunFolder, write_dataset_report
from traj_compare.export import _channels


def test_signed_effort_limits_follow_each_signal_and_joint_order():
    shared = JointLimits(joint_names=("slide", "hinge"), min_position=[0, -2], max_position=[np.inf, 3],
                         max_velocity=[0.5, 1.2], max_acceleration=[1, 4], max_jerk=[3, 30], max_effort=[50, 12])
    data = [[0, 0], [0.2, 0.1], [0.4, 0.2]]
    run = Situation(name="run", t=[0, 1, 2], q=data, tau=data, tau_cmd=np.array(data) * 5,
                    tau_gearbox=np.array(data) * -3, signal_limits={"tau_cmd": ([-18, None], [13, None])})
    payload = analyze_comparison(Comparison(
        title="limits", joint_names=["hinge", "slide"], situations=[run], joint_limits=shared,
        signal_limits={"tau_gearbox": ([-7, None], [11, None])}, joint_units={"slide": "m"},
    ))
    assert payload["joint_units"] == ["rad", "m"]
    assert payload["plot_limits"] == {
        "q": {"lower": [-2, 0], "upper": [3, None]},
        "qd": {"lower": [-1.2, -0.5], "upper": [1.2, 0.5]},
        "qdd": {"lower": [-4, -1], "upper": [4, 1]},
        "qddd": {"lower": [-30, -3], "upper": [30, 3]},
        "tau": {"lower": [-12, -50], "upper": [12, 50]},
        "tau_gearbox": {"lower": [-7, None], "upper": [11, None]},
    }
    entry = payload["situations"][0]
    assert entry["plot_limits"] == {"tau_cmd": {"lower": [-18, None], "upper": [13, None]}}
    assert entry["plot"]["tau"][0] == [0, 0.2, 0.4]
    assert entry["plot"]["tau_cmd"][0] == [0, 1, 2]
    assert entry["plot"]["tau_gearbox"][0] == [0, -0.6, -1.2]
    exported = dict(_channels(payload, entry))
    assert [joint for joint, _ in exported["tau_gearbox"]] == ["hinge", "slide"]


def test_missing_physical_torque_and_jerk_stay_missing():
    run = Situation(name="controller", t=[0, 1], q=[0, 1], qdd=[1, 2], tau_ff=[1, 2], tau_fb=[0.5, 0.1])
    payload = analyze_comparison(Comparison(title="breakdown", joint_names=["hinge"], situations=[run]))
    entry = payload["situations"][0]
    assert entry["plot"]["tau_cmd"] == [[1.5, 2.1]]  # the breakdown keeps its existing identity
    assert "tau_cmd" in entry["derived"]
    assert entry["plot"]["tau"] is None
    assert entry["plot"].get("tau_gearbox") is None
    assert entry["plot"].get("qddd") is None
    assert not payload["has_tau"] and not payload["has_qddd"]


def test_reported_jerk_keeps_discontinuity_gap_after_plot_thinning(monkeypatch):
    monkeypatch.setattr("traj_compare.analysis.MAX_PLOT_POINTS", 4)
    run = Situation(name="run", t=np.arange(6), q=np.arange(6), qddd=[1, np.nan, 1, 1, 2, 2])
    payload = analyze_comparison(Comparison(title="jump", joint_names=["hinge"], situations=[run]))
    assert payload["plot_t"] == [0, 2, 4, 5]
    entry = payload["situations"][0]
    assert entry["plot"]["qddd"] == [[1, None, 2, 2]]
    assert "qddd" not in entry["derived"]
    signals = next(tab for tab in payload["tabs"] if tab["id"] == "signals")
    assert "joint-qddd" in signals["sections"]
    assert next(tab for tab in signals["subtabs"] if tab["id"] == "q-qd-qdd-qddd")["sections"] == [
        "joint-q", "joint-qd", "joint-qdd", "joint-qddd",
    ]


def test_derived_jerk_uses_declared_continuous_acceleration_and_actual_time_intervals():
    target = Situation(name="target", t=[0, 0.25, 0.5, 0.75, 1.0, 1.25], q=[0, 1, 2, 3, 4, 5])
    run = Situation(name="run", t=[0.25, 0.5, 1.0], q=[0, 1, 2], qdd=[0, 0.5, 2.5], derive_jerk=True)
    payload = analyze_comparison(Comparison(title="slope", joint_names=["hinge"], target=target, situations=[run]))
    entry = payload["situations"][1]
    assert entry["plot"]["qddd"] == [[None, 2, 4, 4, 4, None]]
    assert "qddd" in entry["derived"]


def test_limits_and_jerk_validation_names_bad_input():
    with pytest.raises(ValueError, match="derive_jerk requires supplied qdd"):
        Situation(name="run", t=[0, 1], q=[0, 1], derive_jerk=True)
    with pytest.raises(ValueError, match="lower bound"):
        Comparison(title="bad", joint_names=["hinge"], situations=[], signal_limits={"tau_gearbox": (10, 4)})


def test_saved_trajectory_limits_and_typed_channels_follow_the_reference_joints(tmp_path):
    target = JointTrajectory(t=[0, 1, 2], joint_names=["first", "second"], positions=[[0, 0], [1, 2], [2, 4]])
    recorded = JointTrajectory(
        t=[0, 1, 2], joint_names=["second", "first"], positions=[[0, 0], [2, 1], [4, 2]],
        limits=JointLimits(joint_names=["second", "first"], max_jerk=[30, 40]),
        channels={"qddd": [[1, 2], [3, 4], [5, 6]], "tau_gearbox": [[1, 2], [3, 4], [5, 6]],
                  "tau_cmd": [[1, 2], [3, 4], [5, 6]]},
    )
    write_dataset_report([Run("check", target, {"sim": recorded})], tmp_path, title="Limits", rerun=False)
    run = _RunFolder(next((tmp_path / "runs").iterdir()))
    situation = run.situation("sim", target, 0.0, 0.0)
    payload = analyze_comparison(Comparison(title="Limits", joint_names=target.joint_names, situations=[situation]))
    entry = payload["situations"][0]
    assert entry["plot_limits"]["qddd"]["upper"] == [40, 30]
    for key in ("qddd", "tau_gearbox", "tau_cmd"):
        assert entry["plot"][key] == [[2, 4, 6], [1, 3, 5]]


def test_rerun_projects_only_supplied_raw_torque_channels_and_keeps_jerk_gaps(tmp_path):
    pytest.importorskip("rerun")
    from test_signals_channels import scalars_by_entity

    from traj_compare.rerun_export import write_rrd

    load = Situation(name="load", t=[0, 1, 2], q=[0, 1, 2], qddd=[1, np.nan, 3], tau_gearbox=[-2, 4, 1])
    command = Situation(name="command", t=[0, 1, 2], q=[0, 1, 2], tau_cmd=[1, 2, 3])
    legacy = Situation(name="derived-command", t=[0, 1, 2], q=[0, 1, 2], tau_ff=[1, 2, 3], tau_fb=[1, 1, 1])
    comparison = Comparison(title="Jerk and effort", joint_names=["hinge"], situations=[load, command, legacy])
    data = scalars_by_entity(write_rrd(comparison, tmp_path / "motion.rrd", view="layouts"))
    np.testing.assert_allclose(data["/jerks/hinge/load"], np.rad2deg([1, np.nan, 3]), atol=1e-5)
    np.testing.assert_allclose(data["/gearbox_load/hinge/load"], [-2, 4, 1])
    np.testing.assert_allclose(data["/commanded_torque/hinge/command"], [1, 2, 3])
    assert "/commanded_torque/hinge/derived-command" not in data
