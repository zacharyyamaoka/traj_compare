"""``write_target_vs_run_rrd(..., wrenches=, events=, plots=)``: robot_msgs' opt-in extras on the run's arm.

WHY (Zach, 2026-11-27, the gravity compensation box): "you can show an external force being applied as like a vector
arrow?". V2 is V1 plus a target, so the extras are V1's own (robot_msgs.viz.rerun ``wrenches`` / ``events`` / ``plots``)
on the run's plan, and V2 keeps the tabs they add after its own. Read back from the .rrd; the tool point is the made-up
arm's closed form (target_run_fixture.py). Skipped where robot_msgs predates the extras (CI installs it from PyPI).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("rerun")

from robot_msgs.std import Header  # noqa: E402
from robot_msgs.trajectory import WrenchTrajectory  # noqa: E402
from robot_msgs.viz import rerun as viz  # noqa: E402
from target_run_fixture import URDF, target_and_run, tcp, tool_of  # noqa: E402

from traj_compare.rerun_export import target_vs_run_blueprint, write_target_vs_run_rrd  # noqa: E402

pytestmark = pytest.mark.skipif("wrenches" not in inspect.signature(viz._RobotPlan.__init__).parameters,
                                reason="robot_msgs predates viz.rerun's wrenches/events/plots (ff949f2)")


def rows(path: Path, entity: str, column: str) -> list[tuple[float | None, object]]:
    from rerun.chunk import RrdReader

    found = []
    for chunk in RrdReader(path).stream():
        if chunk.entity_path != entity:
            continue
        batch = chunk.to_record_batch()
        if column not in batch.schema.names:
            continue
        values = batch.column(column).to_pylist()
        times = batch.column("t").cast("int64").to_pylist() if "t" in batch.schema.names else [None] * len(values)
        found += [(None if ns is None else ns / 1e9, value) for ns, value in zip(times, values, strict=True)]
    return sorted(found, key=lambda row: -1.0 if row[0] is None else row[0])


def extras(run):
    t = np.asarray(run.t)
    force = np.zeros((len(t), 3))
    force[:, 2] = -15.0 * np.sin(np.pi * t / t[-1])
    wrench = WrenchTrajectory(t=t, forces=force, torques=np.zeros_like(force), header=Header(frame_id=""))
    plots = {"Model check": {"pan: residual [N·m]": {"true": np.linspace(0.0, 1.0, len(t))}}}
    return {"wrenches": {"hand": wrench}, "events": [(0.5, "grab"), (1.5, "release")], "plots": plots}


def test_the_extras_ride_on_the_runs_arm_and_their_tabs_follow_v2s(tmp_path):
    target, run = target_and_run()
    given = extras(run)
    path = write_target_vs_run_rrd(tmp_path / "x.rrd", run, target=target, robot=URDF, tool=tool_of(run),
                                   target_tool=tool_of(target), **given)
    origins = [v[0] for t, v in rows(path, "/world/run/wrenches/hand", "Arrows3D:origins") if t is not None]
    np.testing.assert_allclose(np.array(origins), tcp(run.positions), atol=1e-6)  # at the run's tool point
    assert [(t, v) for t, v in rows(path, "/events", "TextLog:text") if t is not None] == [(0.5, ["grab"]),
                                                                                          (1.5, ["release"])]
    blueprint = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run), target_tool=tool_of(target),
                                        **given)
    _, tabs = blueprint.root_container.contents
    names = [tab.name for tab in tabs.contents]
    assert names[0] == "Error" and names[-3:] == ["Wrench", "Model check", "Events"]


def test_without_extras_v2_is_unchanged():
    target, run = target_and_run()
    plain = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run), target_tool=tool_of(target))
    _, tabs = plain.root_container.contents
    assert "Wrench" not in [tab.name for tab in tabs.contents]
