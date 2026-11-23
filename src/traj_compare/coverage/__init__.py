"""Trajectory coverage: robot_msgs in, one payload "traj_compare.coverage/1" out, four viewers read it (docs/COVERAGE.md).

    from traj_compare.coverage import analyze
    coverage = analyze(trajectories, tool=poses, tags=tags, group_by="split", title="UR5e")
    coverage.payload, coverage.numbers
    coverage.write_page(path)   coverage.plot(out_dir)   coverage.serve_viser()   coverage.log_wandb(run)
"""

from .analysis import SCHEMA, TrajectoryCoverage, analyze

# WHY lazy: each viewer imports its own tool (matplotlib, viser, wandb) and lives in its own module, so importing the
# analysis never needs them, and a viewer that is not installed fails only when it is asked for.
_VIEWERS = {
    "write_coverage_page": "page",
    "plot_coverage": "matplotlib_view",
    "serve_coverage": "viser_view",
    "log_coverage": "wandb_log",
}


def __getattr__(name: str):
    if name in _VIEWERS:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.{_VIEWERS[name]}"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["SCHEMA", "TrajectoryCoverage", "analyze", *_VIEWERS]
