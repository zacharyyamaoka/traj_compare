"""Grasp coverage: robot_msgs GraspPose in, one payload "traj_compare.grasp_coverage/1" out, four viewers read it
(docs/GRASP_COVERAGE.md).

    from traj_compare.grasp_coverage import analyze_grasps
    coverage = analyze_grasps(grasps, outcomes=outcomes, width_range=(0.0, 0.125), area=box, title="Repicks")
    coverage.payload, coverage.numbers
    coverage.write_workbench(out_dir)   coverage.plot(out_dir)   coverage.serve_viser()   coverage.log_wandb(run)
"""

from .analysis import SCHEMA, GraspCoverage, analyze_grasps

# WHY lazy (as traj_compare.coverage): each viewer imports its own tool (matplotlib, viser, wandb) in its own module, so
# the analysis never needs them, and a viewer that is not installed fails only when it is asked for.
_VIEWERS = {
    "write_grasp_workbench": "workbench",
    "plot_grasp_coverage": "matplotlib_view",
    "serve_grasp_coverage": "viser_view",
    "log_grasp_coverage": "wandb_log",
}


def __getattr__(name: str):
    if name in _VIEWERS:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.{_VIEWERS[name]}"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["SCHEMA", "GraspCoverage", "analyze_grasps", *_VIEWERS]
