#!/usr/bin/env python3
"""V1 · As built: robot_msgs' stock viewer exactly as it is on main (248f9f1): `viz.rerun.save(path, traj, robot=urdf, tool=tcp)`.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v1/make.py

A recording holds one JointTrajectory, so the agent's run is drawn as the solution alone (the target is not on screen).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fixture import URDF, plan, run  # noqa: E402

from robot_msgs.viz import rerun as viz  # noqa: E402

traj, tool = plan()
print(viz.save(str(HERE / "plan-dev-029.rrd"), **{"workspace-dev-029": traj}, robot=URDF, tool=tool))
_, solution, _, solution_tool, extras = run("p6s")
print(viz.save(str(HERE / "run-dev-029.rrd"), **{"p6s on workspace-dev-029": solution}, robot=URDF, tool=solution_tool))
