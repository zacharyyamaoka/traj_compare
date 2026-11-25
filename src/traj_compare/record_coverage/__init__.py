"""Record coverage: any list of dataclass records in, one payload "traj_compare.record_coverage/1" out, four viewers read
it (docs/RECORD_COVERAGE.md). The generic family beside trajectories (traj_compare.coverage) and grasps.

    from traj_compare.record_coverage import analyze
    coverage = analyze(records, group_by="item", split="split")
    coverage.payload, coverage.numbers
    coverage.write_page(out_dir)   coverage.plot(out_dir)   coverage.serve_viser()   coverage.log_wandb(run)
"""

from .analysis import SCHEMA, RecordCoverage, analyze

# WHY lazy: each viewer imports its own tool (matplotlib, viser, wandb) in its own module, so the analysis never needs
# them and a viewer that is not installed fails only when it is asked for (the trajectory family's rule).
_VIEWERS = {
    "write_workbench": "workbench",
    "workbench_rows": "workbench",
    "plot_records": "matplotlib_view",
    "serve_records": "viser_view",
    "log_records": "wandb_log",
}


def __getattr__(name: str):
    if name in _VIEWERS:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.{_VIEWERS[name]}"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["SCHEMA", "RecordCoverage", "analyze", *_VIEWERS]
