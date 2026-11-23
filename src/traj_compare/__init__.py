"""traj_compare — turn-key A/B trajectory comparison viewer.

Feed it a target and any number of situations (sim A, sim B, real, ...);
get back one self-contained static ``report.html`` with joint / TCP /
path-progress plot grids and an interactive 3D path viewer.
"""

from .analysis import analyze_comparison
from .model import (
    BarChart,
    BarSeries,
    CameraOverlay,
    Comparison,
    Insight,
    MetricCard,
    ReportImage,
    ReportPage,
    ReportTable,
    RobotDisplay,
    Signal,
    Situation,
    TableRow,
)
from .report import write_comparison_report

# WHY lazy: ``python -m traj_compare.dataset`` runs dataset.py as __main__; importing it here eagerly
# would load it twice and print runpy's "found in sys.modules" warning on every CLI call.
_DATASET_EXPORTS = ("Run", "Sweep", "build_drill_down", "build_run_folder", "default_pairs", "write_dataset_report")


def __getattr__(name: str):
    if name in _DATASET_EXPORTS:
        from . import dataset

        return getattr(dataset, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BarChart",
    "BarSeries",
    "CameraOverlay",
    "Comparison",
    "Insight",
    "MetricCard",
    "Run",
    "ReportImage",
    "ReportPage",
    "ReportTable",
    "RobotDisplay",
    "Signal",
    "Situation",
    "Sweep",
    "TableRow",
    "analyze_comparison",
    "build_drill_down",
    "build_run_folder",
    "default_pairs",
    "write_comparison_report",
    "write_dataset_report",
]

__version__ = "0.1.0"
