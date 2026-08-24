"""traj_compare — turn-key A/B trajectory comparison viewer.

Feed it a target and any number of situations (sim A, sim B, real, ...);
get back one self-contained static ``report.html`` with joint / TCP /
path-progress plot grids and an interactive 3D path viewer.
"""

from .analysis import analyze_comparison
from .model import (
    BarChart,
    BarSeries,
    Comparison,
    Insight,
    MetricCard,
    ReportPage,
    ReportTable,
    RobotDisplay,
    Situation,
    TableRow,
)
from .report import write_comparison_report

__all__ = [
    "BarChart",
    "BarSeries",
    "Comparison",
    "Insight",
    "MetricCard",
    "ReportPage",
    "ReportTable",
    "RobotDisplay",
    "Situation",
    "TableRow",
    "analyze_comparison",
    "write_comparison_report",
]

__version__ = "0.1.0"
