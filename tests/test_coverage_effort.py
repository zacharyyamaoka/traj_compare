"""Recorded torque and computed jerk in trajectory coverage (acceptance, written before the viewers, 2026-11-26).

Zach, 2026-11-26: "it may be useful to see like the torque information of the trajecotries in the past I left that out as
planend trajectories don't have. ... if it has the information than you can display it", and on jerk: "if it doesn't
then there should be an option to like claculate and display the information".

The contract (docs/COVERAGE.md "Effort and provenance"): ``tau`` is in ``payload["signals"]`` only when some trajectory
recorded ``effort``; a trajectory without effort adds no torque samples; its bound is ``max_effort`` (±) else the data;
``payload["signal_source"]`` says per signal whether it was recorded, computed or mixed. A dataset with no effort gets
exactly today's payload plus ``signal_source``. Every number is known by construction.
"""

from __future__ import annotations

import math

import numpy as np
from robot_msgs.trajectory import JointLimits, JointTrajectory

from traj_compare.coverage import analyze
from traj_compare.coverage import workbench as wb

JOINTS = ("a", "b")
HZ = 100.0
LIMITS = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -1.0]), max_position=np.array([math.pi, 1.0]),
                     max_velocity=np.array([2.0, 2.0]), max_acceleration=np.array([10.0, 10.0]),
                     max_effort=np.array([10.0, 4.0]))
NO_EFFORT_LIMIT = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -1.0]),
                              max_position=np.array([math.pi, 1.0]), max_velocity=np.array([2.0, 2.0]),
                              max_acceleration=np.array([10.0, 10.0]))


def sine(seconds=10.0, effort=None, velocities=True, limits=LIMITS) -> JointTrajectory:
    t = np.arange(0.0, seconds, 1.0 / HZ)
    q = np.sin(t)[:, None] * np.array([1.0, 0.5])
    qd = np.cos(t)[:, None] * np.array([1.0, 0.5])
    tau = None if effort is None else np.sin(t)[:, None] * np.asarray(effort, float)
    return JointTrajectory(t=t, joint_names=JOINTS, positions=q, velocities=qd if velocities else None, effort=tau,
                           limits=limits)


def test_effort_on_some_trajectories_adds_tau_from_only_those_samples():
    trajectories = {"recorded": sine(effort=(5.0, 2.0)), "planned": sine()}
    payload = analyze(trajectories).payload
    assert payload["signals"] == ["q", "qd", "qdd", "qddd", "tau"]
    n = len(sine().t)
    # only the recorded trajectory's samples are binned: the planned one is NaN, never zero
    assert sum(payload["hist"]["a"]["tau"]["counts"]) == n
    assert sum(payload["hist"]["a"]["q"]["counts"]) == 2 * n
    # the bound is max_effort, symmetric
    assert payload["limits"]["a"]["tau"] == {"low": -10.0, "high": 10.0, "source": "limit", "kind": None}
    assert payload["limits"]["b"]["tau"]["high"] == 4.0
    # peak 5 of 10 N·m -> 50 %, 2 of 4 -> 50 % (p99.9 of a sine sits just under its amplitude)
    assert 49.0 < payload["hist"]["a"]["tau"]["peak_pct"] <= 50.0
    assert payload["signal_source"] == {"q": "recorded", "qd": "recorded", "qdd": "computed", "qddd": "computed",
                                        "tau": "mixed"}
    assert payload["units"]["revolute"]["tau"] == "N·m" and payload["units"]["prismatic"]["tau"] == "N"
    assert payload["signal_display"]["tau"]["revolute"] == {"scale": 1.0, "unit": "N·m"}
    rows = {row["name"]: row for row in payload["trajectories"]}
    assert rows["planned"]["tau_peak_pct"] is None and rows["planned"]["span_pct"]["a"]["tau"] is None
    assert math.isclose(rows["recorded"]["tau_peak"]["a"], 5.0, rel_tol=1e-3)
    assert math.isclose(rows["recorded"]["tau_peak_pct"], 50.0, rel_tol=1e-3)
    keys = {row["key"]: row["value"] for row in payload["numbers"]}
    assert 49.0 < keys["tau_peak_max_pct"] <= 50.0


def test_effort_without_max_effort_falls_back_to_the_data_and_beyond_counts_against_the_limit():
    data_bound = analyze({"r": sine(effort=(5.0, 2.0), limits=NO_EFFORT_LIMIT)}).payload
    assert data_bound["limits"]["a"]["tau"]["source"] == "data"
    assert data_bound["hist"]["a"]["tau"]["outside"] == 0
    over = analyze({"r": sine(effort=(20.0, 2.0))}).payload  # 20 N·m on a 10 N·m joint
    assert over["hist"]["a"]["tau"]["outside"] > 0
    assert over["signal_source"]["tau"] == "recorded"


def test_no_effort_anywhere_keeps_todays_payload():
    payload = analyze({"x": sine(velocities=False), "y": sine()}, planner_limits=LIMITS).payload
    assert payload["signals"] == ["q", "qd", "qdd", "qddd"]
    assert "signal_display" not in payload
    assert all("tau" not in by_signal for by_signal in payload["limits"].values())
    assert all("tau" not in by_signal for by_signal in payload["hist"].values())
    assert all("tau" not in by_signal for by_signal in payload["planner_limits"].values())  # max_effort given there
    assert all("tau" not in units for units in payload["units"].values())
    assert all("tau_peak_pct" not in row for row in payload["trajectories"])
    assert "tau_peak_max_pct" not in {row["key"] for row in payload["numbers"]}
    assert payload["signal_source"] == {"q": "recorded", "qd": "mixed", "qdd": "computed", "qddd": "computed"}


def test_the_workbench_draws_tau_and_jerk_and_labels_computed_signals():
    trajectories = {"recorded": sine(effort=(5.0, 2.0)), "planned": sine()}
    coverage = analyze(trajectories)
    rows, parts = wb.workbench_rows(coverage, trajectories)
    hist = {(part["trajectory"], part["joint"], part["signal"]): part for part in parts if part["kind"] == "hist"}
    tau = hist[("recorded", "a", "tau")]
    assert sum(tau["counts"]) == len(sine().t)
    assert tau["unit"] == "N·m" and tau["scale"] == 1.0 and tau["signal_word"] == "torque"
    assert sum(hist[("planned", "a", "tau")]["counts"]) == 0
    assert hist[("recorded", "a", "qddd")]["signal_word"] == "jerk (computed)"
    assert hist[("recorded", "a", "qd")]["signal_word"] == "speed"
    by_name = {row["name"]: row for row in rows}
    assert math.isclose(by_name["recorded"]["tau_peak_pct"], 50.0, rel_tol=1e-3)
    views = {view["name"]: view for view in wb._views(coverage.payload, rows, dataset="dataset", facets=(), tool=False)}
    ridge = [view for view in views.values() if view.get("coverage", {}).get("layout") == "ridgeline"]
    assert ridge[0]["coverage"]["signals"] == ["q", "qd", "qdd"]  # the default view stays calm
    extra = {tuple(view["coverage"]["signals"]) for view in ridge[1:]}
    assert ("qddd",) in extra or any("qddd" in signals for signals in extra)
    assert any("tau" in signals for signals in extra)
    assert "tau_peak_pct" in views["Trajectories"]["order"]


def test_the_workbench_without_effort_offers_jerk_but_no_torque():
    trajectories = {"planned": sine()}
    coverage = analyze(trajectories)
    rows, parts = wb.workbench_rows(coverage, trajectories)
    assert not any(part.get("signal") == "tau" for part in parts)
    views = wb._views(coverage.payload, rows, dataset="dataset", facets=(), tool=False)
    signals = [view["coverage"]["signals"] for view in views if view.get("coverage", {}).get("layout") == "ridgeline"]
    assert any("qddd" in s for s in signals) and not any("tau" in s for s in signals)
