#!/usr/bin/env python3
"""V2 as landed (2026-11-25): the round's two scenarios through traj_compare's stock Open in Rerun writers, not make.py.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v2/stock.py

Writes v2/stock-run-dev-029.rrd (fixture.run("p6s"): the Trajectory Tracking Agent's run against its target, the
agent's own ruler as the tool error) with ``traj_compare.rerun_export.write_target_vs_run_rrd`` (V2), and
v2/stock-plan-dev-029.rrd (fixture.plan(): the dataset tour alone) with
``traj_compare.coverage.workbench.write_trajectory_rrd``, the record's Open in Rerun, which stays robot_msgs' V1.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fixture import URDF, plan, run  # noqa: E402

from traj_compare.coverage.workbench import write_trajectory_rrd  # noqa: E402
from traj_compare.rerun_export import write_target_vs_run_rrd  # noqa: E402


def main() -> None:
    target, solution, target_tool, solution_tool, extras = run("p6s")
    print(write_target_vs_run_rrd(HERE / "stock-run-dev-029.rrd", solution, target=target, robot=URDF,
                                  tool=solution_tool, target_tool=target_tool, label=extras["label"],
                                  tool_error_mm=extras["tool_error_mm"], tool_error_rms_mm=extras["rms_mm"],
                                  recording_id="workspace-dev-029 · p6s"))
    traj, tool = plan()
    print(write_trajectory_rrd(HERE / "stock-plan-dev-029.rrd", "workspace-dev-029", traj, robot=URDF, tool=tool))


if __name__ == "__main__":
    main()
