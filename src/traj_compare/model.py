"""Data model for a trajectory comparison — the turn-key A/B contract.

A ``Comparison`` is one page of the report: a shared joint layout, an optional
``target`` (the reference every error channel measures against), and any
number of ``Situation`` records to overlay — sim vs real, setup A vs setup B,
today vs yesterday. A declared-but-empty situation (``t=None``) is legal and
deliberate: it keeps its legend slot and renders as "no data", so a report
configured for sim-vs-real still builds when the real run was skipped.

Every array is SI: seconds, radians, meters, Nm, amperes. Unit conversion (the
degrees-by-default toggle) is a viewer concern, never a storage concern.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from robot_msgs.compare import Tolerances

from .tabs import normalize_parts

# (N, DOF) joint configurations in → (N, 4, 4) TCP poses out.
FkFunction = Callable[[np.ndarray], np.ndarray]

_TIME_SERIES_FIELDS = ("q", "qd", "qdd", "tau", "current", "tau_cmd", "tau_ff", "tau_fb")
_SECTION_IDS = {
    "joint-q",
    "joint-qd",
    "joint-qdd",
    "joint-tau",
    "joint-current",
    "joint-torque",
    "joint-err",
    "tcp-pose",
    "tcp-err",
    "path",
    "videos",
    "camera",
    "viewer3d",
}
_ROW_TONES = {"", "highlight", "positive", "warning", "danger", "muted"}
_CARD_TONES = {"", "neutral", "positive", "warning", "danger", "action"}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "comparison"


@dataclass
class TableRow:
    """One display-ready row in a report table.

    Cells are deliberately strings: study adapters own domain-specific unit
    conversion and comparison language, while the shared viewer owns layout.
    """

    cells: Sequence[str]
    tone: str = ""

    def __post_init__(self) -> None:
        self.cells = [str(cell) for cell in self.cells]
        if self.tone not in _ROW_TONES:
            raise ValueError(f"unknown table-row tone {self.tone!r}")

    def to_payload(self) -> dict[str, Any]:
        return {"cells": list(self.cells), "tone": self.tone}


@dataclass
class ReportTable:
    """A compact table that can appear on a comparison or report-level page."""

    title: str
    columns: Sequence[str]
    rows: Sequence[TableRow]
    description: str = ""

    def __post_init__(self) -> None:
        self.columns = [str(column) for column in self.columns]
        self.rows = list(self.rows)
        if not self.columns:
            raise ValueError("report table needs at least one column")
        for row in self.rows:
            if len(row.cells) != len(self.columns):
                raise ValueError(
                    f"table row has {len(row.cells)} cells; expected {len(self.columns)}"
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "columns": list(self.columns),
            "rows": [row.to_payload() for row in self.rows],
        }


@dataclass
class MetricCard:
    """One headline value on a Summary or Insights page."""

    label: str
    value: str
    detail: str = ""
    tone: str = ""

    def __post_init__(self) -> None:
        if self.tone not in _CARD_TONES:
            raise ValueError(f"unknown metric-card tone {self.tone!r}")

    def to_payload(self) -> dict[str, str]:
        return {
            "label": self.label,
            "value": self.value,
            "detail": self.detail,
            "tone": self.tone,
        }


@dataclass
class BarSeries:
    """One series in a compact grouped horizontal bar chart."""

    name: str
    values: Sequence[float | None]
    color: str = ""

    def __post_init__(self) -> None:
        self.values = [
            None if value is None or not np.isfinite(float(value)) else float(value)
            for value in self.values
        ]

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "values": list(self.values), "color": self.color}


@dataclass
class BarChart:
    """Grouped values rendered without an external chart dependency."""

    title: str
    categories: Sequence[str]
    series: Sequence[BarSeries]
    unit: str = ""
    description: str = ""
    decimals: int = 3

    def __post_init__(self) -> None:
        self.categories = [str(category) for category in self.categories]
        self.series = list(self.series)
        if not self.categories:
            raise ValueError("bar chart needs at least one category")
        if not self.series:
            raise ValueError("bar chart needs at least one series")
        for series in self.series:
            if len(series.values) != len(self.categories):
                raise ValueError(
                    f"bar series {series.name!r} has {len(series.values)} values; "
                    f"expected {len(self.categories)}"
                )
        if self.decimals < 0:
            raise ValueError("bar-chart decimals must be non-negative")

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "categories": list(self.categories),
            "series": [series.to_payload() for series in self.series],
            "unit": self.unit,
            "decimals": self.decimals,
        }


@dataclass
class Insight:
    """A conclusion with its evidence and a concrete next action."""

    title: str
    finding: str
    recommendation: str = ""
    evidence: Sequence[str] = field(default_factory=list)
    tone: str = ""

    def __post_init__(self) -> None:
        self.evidence = [str(item) for item in self.evidence]
        if self.tone not in _CARD_TONES:
            raise ValueError(f"unknown insight tone {self.tone!r}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "finding": self.finding,
            "recommendation": self.recommendation,
            "evidence": list(self.evidence),
            "tone": self.tone,
        }


@dataclass
class ReportImage:
    """A still figure on a report page, embedded as a data URI so the report stays one file."""

    title: str
    src: str  # "data:image/png;base64,..." or "data:image/jpeg;base64,..."
    caption: str = ""
    width_px: int | None = None  # display width; None = the image's own, capped to the page

    def __post_init__(self) -> None:
        if not self.src.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
            raise ValueError("report images must be embedded base64 data URIs (the report is self-contained)")
        if self.width_px is not None and self.width_px <= 0:
            raise ValueError("image width must be positive")

    def to_payload(self) -> dict[str, Any]:
        return {"title": self.title, "src": self.src, "caption": self.caption, "width_px": self.width_px}


@dataclass
class ReportPage:
    """A non-trajectory page such as Summary or Insights."""

    title: str
    name: str = ""
    description: str = ""
    metrics: Sequence[MetricCard] = field(default_factory=list)
    charts: Sequence[BarChart] = field(default_factory=list)
    tables: Sequence[ReportTable] = field(default_factory=list)
    insights: Sequence[Insight] = field(default_factory=list)
    images: Sequence[ReportImage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = _slug(self.title)
        self.metrics = list(self.metrics)
        self.charts = list(self.charts)
        self.tables = list(self.tables)
        self.insights = list(self.insights)
        self.images = list(self.images)

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "metrics": [metric.to_payload() for metric in self.metrics],
            "charts": [chart.to_payload() for chart in self.charts],
            "tables": [table.to_payload() for table in self.tables],
            "insights": [insight.to_payload() for insight in self.insights],
            "images": [image.to_payload() for image in self.images],
        }


@dataclass
class RobotDisplay:
    """Meshes + link fk so the 3D viewer can pose a robot at the scrub time.

    ``link_meshes`` are triangle soups (``(M, 3, 3)`` float32, meters) in each
    link's display frame; ``link_fk`` maps ``(N, DOF)`` joint tracks to
    ``(N, L, 4, 4)`` world poses of those display frames (any mesh-origin
    offset from the URDF is the caller's to fold in).
    """

    link_names: list[str]
    link_meshes: list[np.ndarray]
    link_fk: Callable[[np.ndarray], np.ndarray]
    name: str = "robot"
    # Optional per-link style.  A missing color means "use the situation
    # color", which lets target/sim/real robot overlays match their paths.
    # Fixed housings can pin neutral colors while moving links remain matched.
    link_colors: list[str | None] | None = None
    link_opacities: list[float] | None = None

    def __post_init__(self) -> None:
        if len(self.link_names) != len(self.link_meshes):
            raise ValueError("link_names and link_meshes must align")
        if not self.link_names:
            raise ValueError("RobotDisplay needs at least one link")
        if self.link_colors is not None and len(self.link_colors) != len(self.link_names):
            raise ValueError("link_colors and link_names must align")
        if self.link_opacities is not None and len(self.link_opacities) != len(
            self.link_names
        ):
            raise ValueError("link_opacities and link_names must align")
        if self.link_opacities is not None:
            for opacity in self.link_opacities:
                if not 0.0 <= opacity <= 1.0:
                    raise ValueError("link opacities must be in [0, 1]")
        self.link_meshes = [
            np.ascontiguousarray(np.asarray(mesh, dtype=np.float32).reshape(-1, 3, 3))
            for mesh in self.link_meshes
        ]


@dataclass
class CameraOverlay:
    """A real camera stream with simulated renders laid over it.

    ``real_video`` and every sim path are relative to the report's directory,
    as for ``Situation.video``. ``t0_s`` is the trajectory time shown at video
    time 0, so a video plays at ``currentTime = t - t0_s`` — recordings rarely
    start exactly when the trajectory does. A missing file is not an error
    here: the viewer greys that layer out and prints its path.
    """

    name: str
    real_video: str
    sims: Sequence[tuple[str, str]]  # (label, video path) per selectable sim render
    t0_s: float = 0.0
    note: str = ""
    # A render's flat background colour (e.g. "#fbfbf8"): keyed out when the overlay is baked into
    # one video for Rerun, so only the rendered robot lies over the camera. Empty: a plain 50 % mix.
    key_color: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("camera overlay needs a name")
        self.sims = [(str(label), str(path)) for label, path in self.sims]
        if not self.sims:
            raise ValueError(f"camera overlay '{self.name}' needs at least one sim video")
        labels = [label for label, _ in self.sims]
        if len(set(labels)) != len(labels):
            raise ValueError(
                f"camera overlay '{self.name}': sim labels must be unique, got {labels}"
            )
        self.t0_s = float(self.t0_s)
        if not np.isfinite(self.t0_s):
            raise ValueError(f"camera overlay '{self.name}': t0_s must be finite")

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "real_video": self.real_video,
            "sims": [{"label": label, "video": path} for label, path in self.sims],
            "t0_s": self.t0_s,
            "note": self.note,
        }


@dataclass(frozen=True)
class Signal:
    """How the run view names one recorded channel (``Situation.channels[name]``): title, unit and column labels.

    Given through ``Comparison.signals`` or ``write_dataset_report(signals=...)`` (docs/NAVIGATION.md C1):

    - ``title``: what the plots call it (``"Contact force"``); empty = the channel's own name.
    - ``unit``: shown in brackets (``"N"`` -> ``Contact force [N]``); empty draws no brackets.
    - ``columns``: one label per column of an (N, k) channel (``("x", "y", "z")``); empty = ``0``, ``1``, ...
    - ``per_joint``: the channel is (N, J), its columns the comparison's joints (and, in a dataset, reordered with the
      series as ``effort`` is). Its plots are labelled by the joints; ``columns``, if given, must still number J.

    WHY optional (truthful rendering): a channel nobody described is still drawn, under its own name with no unit;
    a recorded signal is never dropped or renamed.
    """

    title: str = ""
    unit: str = ""
    columns: Sequence[str] = ()
    per_joint: bool = False

    def __post_init__(self) -> None:
        # WHY a bare string is refused: "xyz" is a Sequence of letters, never one column label
        if isinstance(self.columns, (str, bytes)) or not isinstance(self.columns, Sequence):
            raise ValueError(f"Signal {self.title!r}: columns must be a list of labels, got {self.columns!r}")
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "unit", str(self.unit))
        object.__setattr__(self, "columns", tuple(str(column) for column in self.columns))
        object.__setattr__(self, "per_joint", bool(self.per_joint))

    def to_payload(self) -> dict[str, Any]:
        return {"title": self.title, "unit": self.unit, "columns": list(self.columns), "per_joint": self.per_joint}


@dataclass
class Situation:
    """One recorded (or declared) execution of the trajectory."""

    name: str
    title: str = ""
    t: np.ndarray | None = None
    q: np.ndarray | None = None
    qd: np.ndarray | None = None
    qdd: np.ndarray | None = None
    # (N, DOF) N·m. ``tau`` is the torque actually applied on a run (moteus reply ``torque``)
    # and the torque the reference needs on the target. The command breakdown sits beside it
    # (Zach 2026-11-19, torque breakdown: how much of the command came from feedforward, how
    # much from feedback). Two of tau_cmd / tau_ff / tau_fb derive the third.
    tau: np.ndarray | None = None
    current: np.ndarray | None = None  # (N, DOF) motor current, amperes
    tau_cmd: np.ndarray | None = None  # commanded, to the FOC current loop (moteus control_torque)
    tau_ff: np.ndarray | None = None  # feedforward: the model-based part of the command
    tau_fb: np.ndarray | None = None  # feedback: the error-correcting part (kp·e + kd·ė + ki∫e)
    poses: np.ndarray | None = None  # optional precomputed (N, 4, 4) TCP poses
    video: str = ""  # video file path relative to the report's directory
    note: str = ""  # shown in the legend when there is no data
    # Model posed at the scrub time for *this* run. Defaults to the
    # comparison's robot, so target/sim/real normally overlay the same rig in
    # their own colors; set it to compare two different models side by side.
    robot: RobotDisplay | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    # Semantic grouping for crowded comparison pages. The viewer may arrange
    # these groups responsively, but it never changes their meaning.
    group: str = ""
    group_title: str = ""
    # How late this run's clock runs against the reference (robot_msgs.compare's ``time_offset_s``):
    # every error, verdict, goal and aggregate for it is taken with the run shifted back by this
    # much. 0 = the clocks agree. Set it to a latency estimate to see the error that is left.
    time_offset_s: float = 0.0
    # Trajectory time shown at video time 0 (CameraOverlay.t0_s for a plain situation video): a
    # recording rarely starts exactly when the trajectory does, so the video plays at t - video_start_s.
    video_start_s: float = 0.0
    # Every other signal the run recorded (contact force, winding temperature, a collision residual), by name: float,
    # (N,) or (N, k) on this situation's own samples. ``Comparison.signals`` names them; motor current is ``current``.
    # WHY here (docs/NAVIGATION.md C1, the arm_motion_bench agent's gaps 1 and 2): they had nowhere to go in the run
    # view, so a peak force became a run tag and the curve was lost.
    channels: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.time_offset_s = float(self.time_offset_s)
        if not np.isfinite(self.time_offset_s):
            raise ValueError(f"situation '{self.name}': time_offset_s must be finite")
        self.video_start_s = float(self.video_start_s)
        if not np.isfinite(self.video_start_s):
            raise ValueError(f"situation '{self.name}': video_start_s must be finite")
        if not self.title:
            self.title = self.name
        if not self.group:
            self.group = "situations"
        if not self.group_title:
            self.group_title = "Situations"
        if self.t is None:
            if any(getattr(self, name) is not None for name in _TIME_SERIES_FIELDS) or self.channels:
                raise ValueError(f"situation '{self.name}': arrays given without a time base")
            self.channels = {}
            return
        self.t = np.asarray(self.t, dtype=float)
        if self.t.ndim != 1 or self.t.size < 2:
            raise ValueError(f"situation '{self.name}': t must be 1-D with >= 2 samples")
        if np.any(np.diff(self.t) <= 0.0):
            raise ValueError(f"situation '{self.name}': t must be strictly increasing")
        if self.q is None:
            raise ValueError(f"situation '{self.name}': a time base requires q")
        self.q = np.asarray(self.q, dtype=float)
        if self.q.ndim == 1:
            self.q = self.q[:, None]
        for name in _TIME_SERIES_FIELDS[1:]:
            value = getattr(self, name)
            if value is None:
                continue
            value = np.asarray(value, dtype=float)
            if value.ndim == 1:
                value = value[:, None]
            setattr(self, name, value)
        for name in _TIME_SERIES_FIELDS:
            value = getattr(self, name)
            if value is not None and value.shape != self.q.shape:
                raise ValueError(
                    f"situation '{self.name}': {name} shape {value.shape} != q shape {self.q.shape}"
                )
        if self.q.shape[0] != self.t.size:
            raise ValueError(f"situation '{self.name}': q rows must match t")
        if self.poses is not None:
            self.poses = np.asarray(self.poses, dtype=float)
            if self.poses.shape != (self.t.size, 4, 4):
                raise ValueError(
                    f"situation '{self.name}': poses must be (N, 4, 4) on the same grid"
                )
        self.channels = self._checked_channels()

    def _checked_channels(self) -> dict[str, np.ndarray]:
        """``channels`` as an owned dict of float (N,) / (N, k) arrays, or ``ValueError`` naming situation and channel."""

        if not isinstance(self.channels, Mapping):
            raise ValueError(f"situation '{self.name}': channels must map a name to its values")
        checked: dict[str, np.ndarray] = {}
        for key, values in self.channels.items():
            name = str(key)
            where = f"situation '{self.name}', channel {name!r}"
            if name == "current":
                raise ValueError(f"{where}: motor current is Situation.current, never a channel")
            try:
                array = np.array(values, dtype=float)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{where}: values must be numbers ({error})") from None
            if array.ndim not in (1, 2):
                raise ValueError(f"{where}: shape {array.shape}; a channel is (N,) or (N, k)")
            if array.shape[0] != self.t.size:
                raise ValueError(f"{where}: {array.shape[0]} samples, but t has {self.t.size}")
            checked[name] = array
        return checked

    @property
    def has_data(self) -> bool:
        return self.t is not None

    @property
    def dof(self) -> int | None:
        return None if self.q is None else self.q.shape[1]


def _default_vec_dirs() -> list[tuple[str, np.ndarray]]:
    return [
        ("X", np.array([1.0, 0.0, 0.0])),
        ("Y", np.array([0.0, 1.0, 0.0])),
        ("Z", np.array([0.0, 0.0, 1.0])),
    ]


@dataclass
class Comparison:
    """Everything needed to build one comparison page."""

    title: str
    joint_names: Sequence[str]
    situations: list[Situation]
    target: Situation | None = None
    fk: FkFunction | None = None
    # Default model for every situation; a Situation may override its own.
    robot: RobotDisplay | None = None
    # Labeled unit directions for the signed Vec progress channels. Default is
    # the world axes; pass your conveyor direction here to read belt-matching
    # speed straight off the Vec plots.
    vec_dirs: list[tuple[str, np.ndarray]] = field(default_factory=_default_vec_dirs)
    description: str = ""
    name: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    # Exact initial section set for this comparison. ``None`` keeps the
    # viewer defaults; callers can surface task-critical channels (for
    # example motor torque) without changing every other report.
    default_sections: Sequence[str] | None = None
    # Comparisons with the same group become one primary tab and a compact
    # secondary selector. This keeps factorial studies navigable.
    group: str = ""
    group_title: str = ""
    tab_title: str = ""
    # Domain-specific statistics replace the automatic error table.
    statistics: ReportTable | None = None
    # Real camera streams with sim renders laid over them; shown in the
    # "Camera" section beside the Videos, driven by the same transport.
    overlays: Sequence[CameraOverlay] = ()
    # Name of the frame ``fk`` / ``poses`` describe ("TCP", "L2 tip",
    # "coupler point"). WHY: the right frame differs per robot (6-DOF TCP vs a
    # five-bar's L2 tip or coupler), so the report has to say which one every
    # cartesian number is about. Shown in the TCP section hints and the table.
    tcp_frame: str = "TCP"
    # robot_msgs.compare's second wave, all off by default so an existing report is unchanged.
    # Verdicts (ROS 2 joint_trajectory_controller tolerances): ``tolerances`` judges the joints,
    # ``tcp_tolerances`` (PoseTolerance groups) the ``fk`` / ``poses`` frame; each run against the
    # reference gets a code name and the first violation.
    tolerances: Tolerances | None = None
    tcp_tolerances: Tolerances | None = None
    # Latency: estimate_time_offset on the joint trajectories, shown beside the verdict.
    estimate_latency: bool = False
    # Settling bands for ``goal``: rad (joints) / m (TCP position). None = no goal statistics.
    goal_band: float | None = None
    tcp_goal_band: float | None = None
    # Labeled unit vectors the TCP position error (reference - run) is projected onto.
    # WHY: errors along the conveyor (along / across / up) are what belt picking cares about; the
    # world x / y / z only coincide with them when the belt happens to be axis-aligned.
    error_axes: Sequence[tuple[str, Any]] | None = None
    # group name -> situation names that are repeats of one run: ISO 9283 accuracy vs
    # repeatability (robot_msgs.compare.aggregate) against the reference.
    repeat_groups: Mapping[str, Sequence[str]] = field(default_factory=dict)
    # Ordered part name -> its joints: a list (an arm, 1-7 motors) or {finger: [joints]} (a hand). Joints not
    # named fall into a trailing "Other joints"; None is one implicit part (no part selector). WHY explicit
    # (Zach 2026-11-19, traj compare view feedback: "split the arm and the hand into separate concerns, and
    # each arm separately"): the viewers never guess arm / hand membership from joint names (tabs.py).
    parts: Mapping[str, Sequence[str] | Mapping[str, Sequence[str]]] | None = None
    # Channel name -> its ``Signal`` (title, unit, column labels): how the "What else was measured?" tab names
    # ``Situation.channels``. A described channel no situation has is fine (a dataset describes every run's at once).
    signals: Mapping[str, Signal] = field(default_factory=dict)
    # What sits in ``target``: "target", a trajectory to follow (its τ is the torque it needs), or "run", a recorded run
    # another run is measured against (sim → real; its τ is that run's applied torque). WHY (arm_motion_bench, 2026-11-20):
    # a sim → real torque card called the sim run's applied torque "Target", a different signal; the viewers name a run
    # reference by its own title instead of "target".
    reference_kind: str = "target"
    # One bool per ``target`` sample: every error statistic (RMS, max, p95, ... in the tables, the answer and the hovers)
    # is taken over the True samples only; the plots still draw every sample. ``stats_mask_label`` names them in the
    # report ("moving samples"). WHY (TTA ask, 2026-11-24): its ruler's tool tracking RMS is over the samples where the
    # target moves; over every sample the report's RMS also averaged the rests. None (the default): every sample.
    stats_mask: Any = None
    stats_mask_label: str = ""

    def __post_init__(self) -> None:
        if self.stats_mask is not None:
            if self.target is None:
                raise ValueError(f"comparison {self.title!r}: stats_mask needs a target (it is one bool per target sample)")
            mask = np.asarray(self.stats_mask)
            if mask.ndim != 1 or mask.shape[0] != len(self.target.t):
                raise ValueError(f"comparison {self.title!r}: stats_mask has shape {mask.shape}, the target "
                                 f"{len(self.target.t)} samples; it is one bool per target sample")
            self.stats_mask = mask.astype(bool)
        if self.reference_kind not in ("target", "run"):
            raise ValueError(f"comparison {self.title!r}: reference_kind is 'target' or 'run', got {self.reference_kind!r}")
        if not self.name:
            self.name = _slug(self.title)
        if not self.group:
            self.group = self.name
        if not self.group_title:
            self.group_title = self.title
        if not self.tab_title:
            self.tab_title = self.title
        self.overlays = list(self.overlays)
        overlay_names = [overlay.name for overlay in self.overlays]
        if len(set(overlay_names)) != len(overlay_names):
            raise ValueError(f"camera overlay names must be unique, got {overlay_names}")
        self.joint_names = list(self.joint_names)
        if not self.joint_names:
            raise ValueError("joint_names must not be empty")
        names = [situation.name for situation in self.situations]
        if self.target is not None:
            names.append(self.target.name)
        if len(set(names)) != len(names):
            raise ValueError(f"situation names must be unique, got {names}")
        dof = len(self.joint_names)
        everyone = list(self.situations) + ([self.target] if self.target else [])
        for situation in everyone:
            if situation.has_data and situation.dof != dof:
                raise ValueError(
                    f"situation '{situation.name}' has {situation.dof} DOF, "
                    f"comparison declares {dof}"
                )
        normalized: list[tuple[str, np.ndarray]] = []
        for label, direction in self.vec_dirs:
            vector = np.asarray(direction, dtype=float).reshape(3)
            norm = float(np.linalg.norm(vector))
            if norm < 1e-12:
                raise ValueError(f"vec direction '{label}' must be non-zero")
            normalized.append((str(label), vector / norm))
        self.vec_dirs = normalized
        if self.default_sections is not None:
            self.default_sections = list(dict.fromkeys(self.default_sections))
            unknown_sections = set(self.default_sections) - _SECTION_IDS
            if unknown_sections:
                raise ValueError(
                    "unknown default sections "
                    f"{sorted(unknown_sections)}; known: {sorted(_SECTION_IDS)}"
                )
        if self.error_axes is not None:
            axes: list[tuple[str, np.ndarray]] = []
            for label, direction in self.error_axes:
                vector = np.asarray(direction, dtype=float).reshape(3)
                norm = float(np.linalg.norm(vector))
                if norm < 1e-12:
                    raise ValueError(f"error axis '{label}' must be non-zero")
                axes.append((str(label), vector / norm))
            labels = [label for label, _ in axes]
            if len(set(labels)) != len(labels):
                raise ValueError(f"error-axis labels must be unique, got {labels}")
            self.error_axes = axes
        known = {situation.name for situation in self.situations}
        groups: dict[str, list[str]] = {}
        for group, run_names in dict(self.repeat_groups).items():
            run_names = [str(run_name) for run_name in run_names]
            missing = [run_name for run_name in run_names if run_name not in known]
            if missing:
                raise ValueError(f"repeat group '{group}' names unknown situations {missing}")
            if len(run_names) < 2:
                raise ValueError(f"repeat group '{group}' needs at least 2 runs")
            groups[str(group)] = run_names
        self.repeat_groups = groups
        if self.parts is not None:
            normalize_parts(self.joint_names, self.parts)  # raises on an unknown or a repeated joint
            # an owned, ordered copy, so a caller mutating its dict later cannot desync the validated parts
            self.parts = {
                str(name): (
                    {str(finger): [str(joint) for joint in joints] for finger, joints in value.items()}
                    if isinstance(value, Mapping)
                    else [str(joint) for joint in value]
                )
                for name, value in self.parts.items()
            }
        self.signals = self._checked_signals(everyone)

    def _checked_signals(self, everyone: list[Situation]) -> dict[str, Signal]:
        """``signals`` as an owned dict, after checking every situation's channels against it and against each other.

        A channel keeps one shape across situations ((N,) everywhere, or (N, k) with one k), so each of its columns is
        one plot; a described channel's ``columns`` number k; a ``per_joint`` one is (N, J). Else ``ValueError``.
        """

        if not isinstance(self.signals, Mapping):
            raise ValueError(f"signals must map a channel name to its Signal, got {type(self.signals).__name__}")
        signals: dict[str, Signal] = {}
        for name, signal in self.signals.items():
            if not isinstance(signal, Signal):
                raise ValueError(f"signals[{name!r}] must be a traj_compare.Signal, got {type(signal).__name__}")
            signals[str(name)] = signal
        width: dict[str, tuple[int | None, str]] = {}  # channel -> (k, or None for 1-D; the first situation with it)
        for situation in everyone:
            for name, values in situation.channels.items():
                k = None if values.ndim == 1 else values.shape[1]
                if name in width and width[name][0] != k:
                    first_k, first = width[name]
                    raise ValueError(
                        f"channel {name!r} is {'(N,)' if first_k is None else f'(N, {first_k})'} on situation '{first}' "
                        f"but {values.shape} on '{situation.name}'; one channel keeps one shape"
                    )
                width.setdefault(name, (k, situation.name))
                signal = signals.get(name)
                if signal is None:
                    continue
                where = f"situation '{situation.name}', channel {name!r}"
                if signal.per_joint and (values.ndim != 2 or values.shape[1] != len(self.joint_names)):
                    raise ValueError(
                        f"{where}: per_joint needs (N, {len(self.joint_names)}), one column per joint "
                        f"{list(self.joint_names)}; got {values.shape}"
                    )
                count = 1 if k is None else k
                if signal.columns and len(signal.columns) != count:
                    raise ValueError(f"{where}: {count} column(s), but its Signal names {list(signal.columns)}")
        return signals
