"""Trajectory coverage: of everything the robot CAN do (its limits), how much do these trajectories visit?

robot_msgs in (JointTrajectory, PoseTrajectory, JointLimits), one payload dict "traj_compare.coverage/1" out. Every
viewer (page, Matplotlib, Viser, W&B) reads only that payload, so they can never disagree. The contract, every field
and its meaning: docs/COVERAGE.md. numpy + robot_msgs only; SI inside, display scale/unit only as payload hints.

Zach, Daily Note 2026-11-23: "Robot_msgs in. Then do the analysis. and then like the viewers out".
Prior art (ideas, reimplemented): robot_metrics/docs/proposals/coverage-2026-11-19/coverage.py (Grid, limit_use,
sphere_cell, rarefaction) and arm_motion_bench/src/arm_motion_bench/coverage.py (path densification, Strava paths
per pixel, tasks per cell).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs.geometry.rotations import quat_to_matrix
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory

SCHEMA = "traj_compare.coverage/1"
SIGNALS = ("q", "qd", "qdd", "qddd")
MAGNITUDE_LIMITS = {"qd": "max_velocity", "qdd": "max_acceleration", "qddd": "max_jerk"}
UNITS = {
    "revolute": {"q": "rad", "qd": "rad/s", "qdd": "rad/s^2", "qddd": "rad/s^3"},
    "prismatic": {"q": "m", "qd": "m/s", "qdd": "m/s^2", "qddd": "m/s^3"},
}
DISPLAY = {"revolute": {"scale": 180.0 / math.pi, "unit": "deg"}, "prismatic": {"scale": 1000.0, "unit": "mm"}}

DATA_PERCENTILES = (0.1, 99.9)
DATA_WIDEN = 1.15  # a signal with no stated limit spans its data's p0.1..p99.9, widened this much
HIST_BINS = 120
HIST_MARGIN = 0.08  # histograms run this share of the limit span past each limit, so overshoot shows
PLANE_BINS = {"q": 36, "qd": 24, "qdd": 24}
PLANES = (("q_qd", "q", "qd"), ("qd_qdd", "qd", "qdd"), ("q_qdd", "q", "qdd"))
SLABS = 5
PATH_POINTS_MAX = 400  # per trajectory
PATH_POINTS_TOTAL = 20_000  # per joint (or for the tool) over the whole dataset: keeps a big dataset's payload small
PATH_POINTS_MIN = 32
PARALLEL_SIGNALS = ("q", "qd", "qdd")
PARALLEL_WIDTH, PARALLEL_HEIGHT = 48, 128
PARALLEL_SAMPLES_MAX = 50_000
SHUFFLES = 32
PIXEL_M, VOXEL_M = 0.02, 0.05
SPEED_BINS = 60
SPHERE_RINGS, SPHERE_SECTORS = 12, 24
TILT_GRID_BINS, AZIMUTH_BINS, TILT_BINS, YAW_BINS = 18, 36, 36, 72
PROJECTIONS = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}


# ── the result ──────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, eq=False)
class TrajectoryCoverage:
    """The payload every viewer reads, its headline numbers by key, and one call per viewer."""

    payload: dict
    numbers: dict[str, float]

    def write_page(self, path, back=(), siblings=()) -> Path:
        """The standalone HTML page (`write_coverage_page`), with breadcrumb `back` and `siblings` set on a copy."""
        from .page import write_coverage_page

        payload = dict(self.payload)
        payload["back"] = [[str(label), str(href)] for label, href in back]
        payload["siblings"] = [_sibling(item) for item in siblings]
        return write_coverage_page(payload, path, back=payload["back"], siblings=payload["siblings"])

    def plot(self, out_dir, **options) -> list[Path]:
        from .matplotlib_view import plot_coverage

        return plot_coverage(self.payload, out_dir, **options)

    def serve_viser(self, **options):
        from .viser_view import serve_coverage

        return serve_coverage(self.payload, **options)

    def log_wandb(self, run, **options) -> dict:
        from .wandb_log import log_coverage

        return log_coverage(run, self.payload, **options)


def _sibling(item) -> dict:
    if isinstance(item, Mapping):
        return {"label": str(item["label"]), "href": str(item["href"]), "group": str(item.get("group", "")),
                "current": bool(item.get("current", False))}
    label, href, *rest = item
    return {"label": str(label), "href": str(href), "group": str(rest[0]) if rest else "",
            "current": bool(rest[1]) if len(rest) > 1 else False}


@dataclass(frozen=True)
class _Bound:
    low: float
    high: float
    source: str  # "limit" | "data"
    kind: str | None = None  # position bounds only: "physical" | "software" | None

    @property
    def span(self) -> float:
        return self.high - self.low

    def as_dict(self) -> dict:
        return {"low": self.low, "high": self.high, "source": self.source, "kind": self.kind}


@dataclass(frozen=True, eq=False)
class _Dataset:
    """Every trajectory's samples stacked: `signals[s]` is (N, J); `owner[n]` is the trajectory sample n belongs to."""

    names: list[str]
    tags: list[dict]
    joint_names: tuple[str, ...]
    signals: dict[str, np.ndarray]
    owner: np.ndarray
    starts: np.ndarray  # (T + 1,) sample offsets: trajectory k is starts[k]:starts[k + 1]
    durations: list[float]
    rate_hz: float | None

    @property
    def count(self) -> int:
        return len(self.names)

    def rows(self, k: int) -> slice:
        return slice(int(self.starts[k]), int(self.starts[k + 1]))


# ── analyze ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def analyze(
    trajectories,
    *,
    tool=None,
    limits: JointLimits | None = None,
    planner_limits: JointLimits | None = None,
    tags: Mapping[str, Mapping[str, Any]] | None = None,
    group_by: str | None = None,
    title: str = "",
    subtitle: str = "",
    prismatic: Sequence[str] = (),
    reachable=None,
    tool_reference=(0.0, 0.0, -1.0),
    enough: int = 10,
) -> TrajectoryCoverage:
    """One trajectory or a dataset in, the coverage payload out (docs/COVERAGE.md)."""
    named = _named(trajectories, JointTrajectory, "trajectories")
    dataset = _stack(named, tags or {})
    joint_kinds = _joint_kinds(dataset.joint_names, prismatic)
    stated = limits if limits is not None else named[0][1].limits
    bounds = _bounds(stated, dataset)
    group_names, group_of_trajectory = _groups(dataset, group_by)
    group_of_sample = group_of_trajectory[dataset.owner] if group_by else None

    hist = _histograms(dataset, bounds, group_names, group_of_sample)
    planes, cell_keys = _planes(dataset, bounds, enough)
    growth, new_cells = _growth(cell_keys, dataset.count, len(dataset.joint_names) * _cells("q_qd"))
    tool_block, tool_extremes = None, {}
    if tool is not None:
        tool_block, tool_extremes = _tool(_matched_tools(tool, named), reachable, tool_reference)

    payload = {
        "schema": SCHEMA,
        "title": str(title),
        "subtitle": str(subtitle),
        "back": [],
        "siblings": [],
        "enough": int(enough),
        "source": _source(dataset, group_by, group_names),
        "joints": [{"name": name, "kind": joint_kinds[name], "display": dict(DISPLAY[joint_kinds[name]])}
                   for name in dataset.joint_names],
        "signals": list(SIGNALS),
        "units": {kind: dict(units) for kind, units in UNITS.items()},
        "limits": {joint: {signal: bound.as_dict() for signal, bound in by_signal.items()}
                   for joint, by_signal in bounds.items()},
        "planner_limits": _planner_limits(planner_limits, dataset.joint_names),
        "hist": hist,
        "planes": planes,
        "slabs": _slabs(dataset, bounds),
        "paths": _joint_paths(dataset, bounds),
        "parallel": _parallel(dataset, bounds),
        "trajectories": _trajectory_rows(dataset, bounds, new_cells),
        "growth": growth,
        "tool": tool_block,
    }
    payload["numbers"] = _headline_numbers(payload, tool_extremes)
    return TrajectoryCoverage(payload, {row["key"]: row["value"] for row in payload["numbers"]})


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def _named(items, message_type: type, what: str) -> list[tuple[str, Any]]:
    """(name, message) pairs, order kept. Names: the Mapping's keys, else header.meta["name"], else traj_<i>."""
    if isinstance(items, message_type):
        items = [items]
    if isinstance(items, Mapping):
        pairs = [(str(name), message) for name, message in items.items()]
    else:
        pairs = [(message.header.meta.get("name") or f"traj_{i}", message) for i, message in enumerate(items)]
    if not pairs:
        raise ValueError(f"analyze needs at least one entry in {what}")
    for name, message in pairs:
        if not isinstance(message, message_type):
            raise TypeError(f"{what}[{name!r}] is a {type(message).__name__}, not a {message_type.__name__}")
    return pairs


def _stack(named: list[tuple[str, JointTrajectory]], tags: Mapping[str, Mapping[str, Any]]) -> _Dataset:
    joint_names = named[0][1].joint_names
    parts: dict[str, list[np.ndarray]] = {signal: [] for signal in SIGNALS}
    lengths, durations, rates = [], [], []
    for name, trajectory in named:
        if trajectory.joint_names != joint_names:
            raise ValueError(f"trajectory {name!r} has joints {trajectory.joint_names}, the first has {joint_names}: "
                             "every trajectory must share joint names")
        for signal, values in zip(SIGNALS, _signals(trajectory), strict=True):
            parts[signal].append(values)
        t = np.asarray(trajectory.t, float)
        lengths.append(len(t))
        durations.append(float(t[-1] - t[0]) if len(t) else 0.0)
        steps = np.diff(t)
        steps = steps[steps > 0]
        if steps.size:
            rates.append(1.0 / float(np.median(steps)))
    starts = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)
    return _Dataset(
        names=[name for name, _ in named],
        tags=[_plain_tags(tags.get(name, {})) for name, _ in named],
        joint_names=joint_names,
        signals={signal: np.concatenate(values) if values else np.zeros((0, len(joint_names)))
                 for signal, values in parts.items()},
        owner=np.repeat(np.arange(len(named)), lengths),
        starts=starts,
        durations=durations,
        rate_hz=float(np.median(rates)) if rates else None,
    )


def _slope(values: np.ndarray, t: np.ndarray) -> np.ndarray:
    """d values / dt along axis 0: central differences inside, a plain one-sided difference at each end.

    WHY first order at the ends (2026-11-23, tests/test_coverage_edges.py): numpy's second-order edge stencil
    (-3 f0 + 4 f1 - f2) / 2h overshoots when the slope changes right after the first sample, so every UR5e page showed
    a false "past the jerk limit" at sample 0 of each trajectory. A coverage number must never claim a sample went
    somewhere the data does not show."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.gradient(values, t, axis=0, edge_order=1)


def _signals(trajectory: JointTrajectory) -> tuple[np.ndarray, ...]:
    """q, qd, qdd, qddd of one trajectory, (N, J) each. Missing qd/qdd and the jerk are `_slope`s on the trajectory's
    own clock (COVERAGE.md)."""
    positions = np.asarray(trajectory.positions, float)
    if len(trajectory) < 2:  # nothing to differentiate: a single pose stands still
        zero = np.zeros_like(positions)
        return positions, zero, zero, zero
    t = np.asarray(trajectory.t, float)
    velocities = _slope(positions, t) if trajectory.velocities is None else np.asarray(trajectory.velocities, float)
    accelerations = (_slope(velocities, t) if trajectory.accelerations is None
                     else np.asarray(trajectory.accelerations, float))
    return positions, velocities, accelerations, _slope(accelerations, t)


def _plain_tags(tags: Mapping[str, Any]) -> dict:
    """JSON-safe tag values: str stays str, numpy scalars become Python numbers."""
    plain = {}
    for key, value in tags.items():
        if isinstance(value, np.generic):
            value = value.item()
        plain[str(key)] = value if isinstance(value, str | int | float | bool) or value is None else str(value)
    return plain


def _joint_kinds(joint_names: tuple[str, ...], prismatic: Sequence[str]) -> dict[str, str]:
    unknown = sorted(set(prismatic) - set(joint_names))
    if unknown:
        raise ValueError(f"prismatic names {unknown} are not joints; the joints are {joint_names}")
    return {name: "prismatic" if name in prismatic else "revolute" for name in joint_names}


def _groups(dataset: _Dataset, group_by: str | None) -> tuple[list[str], np.ndarray]:
    """The group_by tag's values in order of first appearance, and each trajectory's group index."""
    if not group_by:
        return [], np.zeros(dataset.count, np.int64)
    labels = [str(tags[group_by]) if group_by in tags else f"(no {group_by})" for tags in dataset.tags]
    names = list(dict.fromkeys(labels))
    return names, np.array([names.index(label) for label in labels], np.int64)


def _matched_tools(tool, named: list[tuple[str, JointTrajectory]]) -> list[PoseTrajectory]:
    """One PoseTrajectory per trajectory: a Mapping by name, else in the same order."""
    if isinstance(tool, Mapping):
        missing = [name for name, _ in named if name not in tool]
        if missing:
            raise ValueError(f"tool has no pose trajectory for {missing}")
        poses = [tool[name] for name, _ in named]
    else:
        poses = [tool] if isinstance(tool, PoseTrajectory) else list(tool)
        if len(poses) != len(named):
            raise ValueError(f"tool has {len(poses)} pose trajectories for {len(named)} joint trajectories")
    for pose in poses:
        if not isinstance(pose, PoseTrajectory):
            raise TypeError(f"tool entries are PoseTrajectory, got {type(pose).__name__}")
    return poses


# ── limits ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def _bounds(limits: JointLimits | None, dataset: _Dataset) -> dict[str, dict[str, _Bound]]:
    """Per joint and signal, the denominator every % is taken of.

    WHY the limits are the denominator (Zach, Daily Note 2026-11-19: "When we talk about coverage yes it needs to be
    relative to kinda like the limits"): a share of what the robot can do, not of what the data happened to do. A
    signal with no stated limit falls back to its data and says so (source "data"), so a viewer can say "no limit
    stated".
    """
    bounds: dict[str, dict[str, _Bound]] = {}
    for j, joint in enumerate(dataset.joint_names):
        stated = _stated_bounds(limits, joint)
        bounds[joint] = {signal: stated.get(signal) or _data_bound(dataset.signals[signal][:, j])
                         for signal in SIGNALS}
    return bounds


def _stated_bounds(limits: JointLimits | None, joint: str) -> dict[str, _Bound]:
    """The finite, non-empty bounds `limits` states for one joint (q, qd, qdd, qddd)."""
    if limits is None or joint not in limits.joint_names:
        return {}
    i = limits.joint_names.index(joint)
    stated = {}
    if limits.min_position is not None and limits.max_position is not None:
        low, high = float(limits.min_position[i]), float(limits.max_position[i])
        kind = limits.position_kind[i] if limits.position_kind is not None else None
        if math.isfinite(low) and math.isfinite(high) and high > low:
            stated["q"] = _Bound(low, high, "limit", kind)
    for signal, field_name in MAGNITUDE_LIMITS.items():
        values = getattr(limits, field_name)
        if values is not None and math.isfinite(float(values[i])) and float(values[i]) > 0:
            stated[signal] = _Bound(-float(values[i]), float(values[i]), "limit")
    return stated


def _data_bound(values: np.ndarray) -> _Bound:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return _Bound(-1.0, 1.0, "data")
    p_low, p_high = np.percentile(finite, DATA_PERCENTILES)
    centre, half = 0.5 * (p_low + p_high), 0.5 * (p_high - p_low) * DATA_WIDEN
    if not half > 0:  # WHY: a signal that never changes still needs a box to bin into; one unit either side
        half = 1.0
    return _Bound(float(centre - half), float(centre + half), "data")


def _planner_limits(planner: JointLimits | None, joint_names: tuple[str, ...]) -> dict | None:
    if planner is None:
        return None
    return {joint: {signal: bound.as_dict() for signal, bound in _stated_bounds(planner, joint).items()}
            for joint in joint_names}


# ── binning ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _bin_index(values: np.ndarray, low: float, high: float, bins: int) -> np.ndarray:
    """Linear bin of each value, -1 outside [low, high] or not finite.

    WHY linear (Zach 2026-11-19: "I feel it would be better to just have a linear scale"): equal cells, so a visited
    % is a share of the space. WHY a tolerance: a sample timed AT its limit lands on the last edge to the last ulp.
    """
    values = np.asarray(values, float)
    tolerance = 1e-9 * (high - low)
    with np.errstate(invalid="ignore"):
        index = np.floor((values - low) / (high - low) * bins)
        index = np.where((values >= high) & (values <= high + tolerance), bins - 1, index)
        index = np.where((values < low) & (values >= low - tolerance), 0, index)
        inside = (index >= 0) & (index < bins)
    return np.where(inside, index, -1).astype(np.int64)


def _beyond(values: np.ndarray, bound: _Bound) -> int:
    """Samples past the stated limit (same tolerance as the bins); a data-derived box has no 'beyond'."""
    if bound.source != "limit":
        return 0
    tolerance = 1e-9 * bound.span
    finite = values[np.isfinite(values)]
    return int(((finite < bound.low - tolerance) | (finite > bound.high + tolerance)).sum())


def _edges(low: float, high: float, bins: int) -> list:
    return [float(low), float(high), int(bins)]


def _cells(plane: str) -> int:
    x, y = plane.split("_")
    return PLANE_BINS[x] * PLANE_BINS[y]


def _paths_per_cell(cell: np.ndarray, owner: np.ndarray, cells: int) -> tuple[np.ndarray, np.ndarray]:
    """Distinct trajectories through each cell, and the unique (trajectory * cells + cell) keys behind it.

    WHY count trajectories, not samples (arm_motion_bench, Zach: "colour by runs, not samples"): a long dwell is one
    visit."""
    keys = np.unique(owner.astype(np.int64) * cells + cell)
    return np.bincount(keys % cells, minlength=cells), keys


def _max_per_cell(cell: np.ndarray, values: np.ndarray, cells: int) -> np.ndarray:
    """The largest value in each cell; NaN where no finite value landed."""
    finite = np.isfinite(values)
    largest = np.full(cells, -np.inf)
    np.maximum.at(largest, cell[finite], values[finite])
    largest[np.isneginf(largest)] = np.nan
    return largest


def _evenness_pct(counts: np.ndarray) -> float:
    """exp(Shannon entropy) as a share of all cells: 100 % only if every cell holds the same (Hill number of order 1)."""
    total = counts.sum()
    if total == 0:
        return 0.0
    share = counts[counts > 0] / total
    return 100.0 * math.exp(float(-(share * np.log(share)).sum())) / counts.size


# ── 1-D histograms ──────────────────────────────────────────────────────────────────────────────────────────────────


def _histograms(dataset: _Dataset, bounds, group_names: list[str], group_of_sample: np.ndarray | None) -> dict:
    return {joint: {signal: _histogram(dataset.signals[signal][:, j], bounds[joint][signal], signal, group_names,
                                       group_of_sample)
                    for signal in SIGNALS}
            for j, joint in enumerate(dataset.joint_names)}


def _histogram(values: np.ndarray, bound: _Bound, signal: str, group_names: list[str],
               group_of_sample: np.ndarray | None) -> dict:
    margin = HIST_MARGIN * bound.span
    low, high = bound.low - margin, bound.high + margin
    index = _bin_index(values, low, high, HIST_BINS)
    drawn = index >= 0
    groups = None
    if group_of_sample is not None:
        groups = {name: _ints(np.bincount(index[drawn & (group_of_sample == g)], minlength=HIST_BINS))
                  for g, name in enumerate(group_names)}
    finite = values[np.isfinite(values)]
    p_low, p_high = np.percentile(finite, DATA_PERCENTILES) if finite.size else (math.nan, math.nan)
    return {
        "edges": _edges(low, high, HIST_BINS),
        "counts": _ints(np.bincount(index[drawn], minlength=HIST_BINS)),
        "groups": groups,
        "p001": _number(p_low),
        "p999": _number(p_high),
        "min": _number(finite.min()) if finite.size else None,
        "max": _number(finite.max()) if finite.size else None,
        "span_pct": _number(_span_pct(p_low, p_high, bound)),
        "peak_pct": _number(_peak_pct(p_low, p_high, bound, signal)),
        "outside": _beyond(values, bound),
        "beyond_edges": int((np.isfinite(values) & ~drawn).sum()),
    }


def _span_pct(p_low: float, p_high: float, bound: _Bound) -> float:
    return 100.0 * (p_high - p_low) / bound.span


def _peak_pct(p_low: float, p_high: float, bound: _Bound, signal: str) -> float:
    """qd/qdd/qddd: the largest magnitude reached as a share of the larger limit magnitude. q: the share of the half
    range reached from the range's centre (the same rule about the centre instead of zero)."""
    if signal == "q":
        centre, half = 0.5 * (bound.low + bound.high), 0.5 * bound.span
        return 100.0 * max(abs(p_low - centre), abs(p_high - centre)) / half
    return 100.0 * max(abs(p_low), abs(p_high)) / max(abs(bound.low), abs(bound.high))


# ── phase planes and slabs ──────────────────────────────────────────────────────────────────────────────────────────


def _planes(dataset: _Dataset, bounds, enough: int) -> tuple[dict, np.ndarray]:
    """Every joint's q x qd, qd x qdd and q x qdd planes, and the q_qd (trajectory, cell) keys of all joints (offset
    per joint) for the growth curve."""
    planes: dict[str, dict] = {}
    q_qd_keys = []
    for j, joint in enumerate(dataset.joint_names):
        planes[joint] = {}
        for name, x, y in PLANES:
            plane, keys = _plane(dataset, j, bounds[joint], name, x, y, enough)
            planes[joint][name] = plane
            if name == "q_qd":
                q_qd_keys.append(_rekey(keys, _cells(name), j, len(dataset.joint_names)))
    return planes, np.concatenate(q_qd_keys)


def _rekey(keys: np.ndarray, cells: int, joint: int, joints: int) -> np.ndarray:
    """(trajectory * cells + cell) of one joint -> (trajectory * joints * cells + joint * cells + cell)."""
    owner, cell = keys // cells, keys % cells
    return owner * joints * cells + joint * cells + cell


def _plane(dataset: _Dataset, j: int, bounds: dict[str, _Bound], name: str, x: str, y: str,
           enough: int) -> tuple[dict, np.ndarray]:
    x_values, y_values = dataset.signals[x][:, j], dataset.signals[y][:, j]
    nx, ny = PLANE_BINS[x], PLANE_BINS[y]
    x_index = _bin_index(x_values, bounds[x].low, bounds[x].high, nx)
    y_index = _bin_index(y_values, bounds[y].low, bounds[y].high, ny)
    inside = (x_index >= 0) & (y_index >= 0)
    cell = x_index[inside] * ny + y_index[inside]
    samples = np.bincount(cell, minlength=nx * ny)
    paths, keys = _paths_per_cell(cell, dataset.owner[inside], nx * ny)
    max_other = None
    if name == "q_qd":
        span = bounds["qdd"].span
        max_other = _floats(_max_per_cell(cell, np.abs(dataset.signals["qdd"][inside, j]), nx * ny),
                            _decimals(span))
    plane = {
        "x": x,
        "y": y,
        "x_edges": _edges(bounds[x].low, bounds[x].high, nx),
        "y_edges": _edges(bounds[y].low, bounds[y].high, ny),
        "shape": [nx, ny],
        "samples": _ints(samples),
        "paths": _ints(paths),
        "max_other": max_other,
        "visited_pct": 100.0 * float((samples > 0).sum()) / samples.size,
        "sufficient_pct": 100.0 * float((samples >= enough).sum()) / samples.size,
        "evenness_pct": _evenness_pct(samples),
        "outside": int((np.isfinite(x_values) & np.isfinite(y_values) & ~inside).sum()),
    }
    return plane, keys


def _slabs(dataset: _Dataset, bounds) -> dict:
    """q x qd counts split into SLABS bands of qdd. WHY the end slabs also hold samples past the qdd limit: so the slabs
    add back up to the q_qd plane exactly (a sample is never dropped for its acceleration)."""
    slabs = {}
    nx, ny = PLANE_BINS["q"], PLANE_BINS["qd"]
    for j, joint in enumerate(dataset.joint_names):
        joint_bounds = bounds[joint]
        q_index = _bin_index(dataset.signals["q"][:, j], joint_bounds["q"].low, joint_bounds["q"].high, nx)
        qd_index = _bin_index(dataset.signals["qd"][:, j], joint_bounds["qd"].low, joint_bounds["qd"].high, ny)
        qdd = dataset.signals["qdd"][:, j]
        keep = (q_index >= 0) & (qd_index >= 0) & np.isfinite(qdd)
        qdd_bound = joint_bounds["qdd"]
        slab = np.clip(np.floor((qdd[keep] - qdd_bound.low) / qdd_bound.span * SLABS), 0, SLABS - 1).astype(np.int64)
        counts = np.bincount((slab * nx + q_index[keep]) * ny + qd_index[keep], minlength=SLABS * nx * ny)
        visited = (counts.reshape(SLABS, nx * ny) > 0).sum(axis=1)
        slabs[joint] = {
            "x": "q", "y": "qd", "by": "qdd",
            "by_edges": _edges(qdd_bound.low, qdd_bound.high, SLABS),
            "shape": [SLABS, nx, ny],
            "samples": _ints(counts),
            "visited_pct": [100.0 * float(v) / (nx * ny) for v in visited],
        }
    return slabs


# ── per-trajectory paths, parallel coordinates ──────────────────────────────────────────────────────────────────────


def _points_per_trajectory(trajectories: int) -> int:
    """At most PATH_POINTS_MAX per trajectory, fewer for a big dataset so the payload stays small."""
    return int(np.clip(PATH_POINTS_TOTAL // max(trajectories, 1), PATH_POINTS_MIN, PATH_POINTS_MAX))


def _evenly_picked(length: int, points: int) -> np.ndarray:
    if length <= points:
        return np.arange(length)
    return np.unique(np.linspace(0, length - 1, points).round().astype(np.int64))


def _joint_paths(dataset: _Dataset, bounds) -> dict:
    """Per joint, per trajectory, its (q, qd, qdd) path, evenly picked."""
    points = _points_per_trajectory(dataset.count)
    paths: dict[str, list] = {joint: [] for joint in dataset.joint_names}
    for k in range(dataset.count):
        rows = dataset.rows(k)
        picked = _evenly_picked(rows.stop - rows.start, points) + rows.start
        for j, joint in enumerate(dataset.joint_names):
            # WHY 3 significant figures of the limit span: finer than a pixel on any figure, and the paths are the
            # payload's biggest block (UR5e rung 1.0: 1.4 MB at 4 figures)
            paths[joint].append([_floats(dataset.signals[signal][picked, j], _decimals(bounds[joint][signal].span, 3))
                                 for signal in ("q", "qd", "qdd")])
    return paths


def _parallel(dataset: _Dataset, bounds) -> dict:
    """Line density between adjacent joint axes, each axis running low limit (0) .. high limit (1). A line that goes
    past a limit leaves the frame (those pixels are not counted)."""
    total = len(dataset.owner)
    picked = None
    if total > PARALLEL_SAMPLES_MAX:
        picked = _evenly_picked(total, PARALLEL_SAMPLES_MAX)
    blocks = {}
    for signal in PARALLEL_SIGNALS:
        values = dataset.signals[signal] if picked is None else dataset.signals[signal][picked]
        normalized = np.column_stack([(values[:, j] - bounds[joint][signal].low) / bounds[joint][signal].span
                                      for j, joint in enumerate(dataset.joint_names)])
        gaps = [_ints(_line_density(normalized[:, j], normalized[:, j + 1]))
                for j in range(len(dataset.joint_names) - 1)]
        blocks[signal] = {"axes": list(dataset.joint_names), "height": PARALLEL_HEIGHT, "width": PARALLEL_WIDTH,
                          "range": "limit", "gaps": gaps, "subsampled": None if picked is None else int(len(picked))}
    return blocks


def _line_density(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Straight lines from `left` (x = 0) to `right` (x = width - 1), rasterized: lines per pixel, flat [x][y]."""
    finite = np.isfinite(left) & np.isfinite(right)
    left, right = left[finite], right[finite]
    along = np.arange(PARALLEL_WIDTH) / (PARALLEL_WIDTH - 1)
    heights = left[:, None] + (right - left)[:, None] * along[None, :]
    rows = np.floor(heights * PARALLEL_HEIGHT)
    rows = np.where(heights == 1.0, PARALLEL_HEIGHT - 1, rows)
    columns = np.broadcast_to(np.arange(PARALLEL_WIDTH), rows.shape)
    inside = (rows >= 0) & (rows < PARALLEL_HEIGHT)
    pixel = columns[inside] * PARALLEL_HEIGHT + rows[inside].astype(np.int64)
    return np.bincount(pixel, minlength=PARALLEL_WIDTH * PARALLEL_HEIGHT)


# ── trajectories and growth ─────────────────────────────────────────────────────────────────────────────────────────


def _trajectory_rows(dataset: _Dataset, bounds, new_cells: np.ndarray) -> list[dict]:
    rows = []
    for k, name in enumerate(dataset.names):
        part = dataset.rows(k)
        spans = {}
        for j, joint in enumerate(dataset.joint_names):
            spans[joint] = {}
            for signal in SIGNALS:
                values = dataset.signals[signal][part, j]
                finite = values[np.isfinite(values)]
                if finite.size:
                    p_low, p_high = np.percentile(finite, DATA_PERCENTILES)
                    spans[joint][signal] = round(_span_pct(p_low, p_high, bounds[joint][signal]), 3)
                else:
                    spans[joint][signal] = None
        rows.append({"name": name, "tags": dataset.tags[k], "duration_s": dataset.durations[k],
                     "samples": part.stop - part.start, "span_pct": spans, "new_cells": int(new_cells[k])})
    return rows


def _growth(keys: np.ndarray, trajectories: int, cells: int) -> tuple[dict, np.ndarray]:
    """Mean q_qd visited % (over joints) as trajectories are added in order, the same over 32 shuffled orders (seed 0),
    and how many cells each trajectory was first to visit.

    The ecology species-accumulation curve (prior art `rarefaction`): still climbing means more of the same data still
    buys coverage; flat below 100 % means the rest needs a different trajectory, not more repeats.
    """
    owner, cell = keys // cells, keys % cells
    in_order = _accumulation(owner, cell, np.arange(trajectories), trajectories, cells)
    first_rank = np.full(cells, trajectories)
    np.minimum.at(first_rank, cell, owner)
    new_cells = np.bincount(first_rank[first_rank < trajectories], minlength=trajectories)
    rng = np.random.default_rng(0)
    shuffled = np.array([_accumulation(owner, cell, rng.permutation(trajectories), trajectories, cells)
                         for _ in range(SHUFFLES)])
    growth = {
        "visited_pct": [float(v) for v in in_order],
        "shuffled": {"mean": _floats(shuffled.mean(axis=0), 4),
                     "p10": _floats(np.percentile(shuffled, 10, axis=0), 4),
                     "p90": _floats(np.percentile(shuffled, 90, axis=0), 4)},
    }
    return growth, new_cells


def _accumulation(owner: np.ndarray, cell: np.ndarray, order: np.ndarray, trajectories: int, cells: int) -> np.ndarray:
    """Visited % of all cells after the first k trajectories of `order`, k = 1..T."""
    rank = np.empty(trajectories, np.int64)
    rank[order] = np.arange(trajectories)
    first_rank = np.full(cells, trajectories)
    np.minimum.at(first_rank, cell, rank[owner])
    firsts = np.bincount(first_rank[first_rank < trajectories], minlength=trajectories)
    return 100.0 * np.cumsum(firsts) / cells


# ── the tool: Cartesian and orientation ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, eq=False)
class _ToolSamples:
    positions: np.ndarray  # (N, 3) raw samples
    speeds: np.ndarray  # (N,) m/s
    rotations: np.ndarray  # (N, 3, 3) base <- tool
    owner: np.ndarray  # (N,)
    path_points: np.ndarray  # (M, 3) the polylines densified so no pixel or voxel is skipped
    path_speeds: np.ndarray  # (M,)
    path_owner: np.ndarray  # (M,)
    starts: np.ndarray  # (T + 1,) raw sample offsets


def _tool(poses: list[PoseTrajectory], reachable, tool_reference) -> tuple[dict, dict[str, float]]:
    """The tool block, and the raw-sample extremes its headline numbers need (speed p99, largest tilt)."""
    samples = _tool_samples(poses)
    reach = None if reachable is None else np.asarray(reachable, float).reshape(-1, 3)
    reach = None if reach is None else reach[np.isfinite(reach).all(axis=1)]
    low, high = _tool_bounds(samples, reach)
    orientation, tilt = _orientation(samples.rotations, tool_reference)
    speeds = samples.speeds[np.isfinite(samples.speeds)]
    extremes = {"speed_p99": float(np.percentile(speeds, 99)) if speeds.size else 0.0,
                "tilt_max": float(tilt.max()) if tilt.size else 0.0}
    block = {
        "frame": poses[0].header.frame_id or "base",
        "pixel_m": PIXEL_M,
        "voxel_m": VOXEL_M,
        "bounds": [_floats(low, 6), _floats(high, 6)],
        "projections": {view: _projection(samples, reach, low, high, axes) for view, axes in PROJECTIONS.items()},
        "voxels": _voxels(samples, reach, low, high),
        "spaghetti": _spaghetti(samples),
        "speed": _speed_histogram(samples.speeds),
        "orientation": orientation,
    }
    return block, extremes


def _tool_samples(poses: list[PoseTrajectory]) -> _ToolSamples:
    positions, speeds, rotations, path_points, path_speeds, path_owner, lengths = [], [], [], [], [], [], []
    for k, pose in enumerate(poses):
        position = np.asarray(pose.positions, float)
        speed = _tool_speed(pose)
        points, point_speeds = _densify(position, speed, PIXEL_M / 4.0)
        positions.append(position)
        speeds.append(speed)
        rotations.append(quat_to_matrix(np.asarray(pose.orientations, float)) if len(pose) else np.zeros((0, 3, 3)))
        path_points.append(points)
        path_speeds.append(point_speeds)
        path_owner.append(np.full(len(points), k, np.int64))
        lengths.append(len(position))
    return _ToolSamples(
        positions=np.concatenate(positions), speeds=np.concatenate(speeds), rotations=np.concatenate(rotations),
        owner=np.repeat(np.arange(len(poses)), lengths), path_points=np.concatenate(path_points),
        path_speeds=np.concatenate(path_speeds), path_owner=np.concatenate(path_owner),
        starts=np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64),
    )


def _tool_speed(pose: PoseTrajectory) -> np.ndarray:
    """Linear speed of the tool origin, m/s: the pose's own linear_velocities, else finite differences on its clock."""
    if pose.linear_velocities is not None:
        return np.linalg.norm(np.asarray(pose.linear_velocities, float), axis=1)
    if len(pose) < 2:
        return np.zeros(len(pose))
    velocity = _slope(np.asarray(pose.positions, float), np.asarray(pose.t, float))
    return np.linalg.norm(velocity, axis=1)


def _densify(points: np.ndarray, speeds: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """The polyline with extra points so no two neighbours are more than `step` apart; every original point kept.

    WHY (arm_motion_bench resample_path, the Strava line-density view): a fast segment must not skip a pixel or a voxel
    it passes through. Keeping the originals means a pixel with samples is always on the path too."""
    finite = np.isfinite(points).all(axis=1)
    points, speeds = points[finite], speeds[finite]
    if len(points) < 2:
        return points, speeds
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    pieces = np.maximum(np.ceil(lengths / step), 1).astype(np.int64)
    segment = np.repeat(np.arange(len(lengths)), pieces)
    offsets = np.concatenate([[0], np.cumsum(pieces)[:-1]])
    fraction = (np.arange(len(segment)) - offsets[segment]) / pieces[segment]
    dense = points[segment] + fraction[:, None] * (points[segment + 1] - points[segment])
    dense_speeds = speeds[segment] + fraction * (speeds[segment + 1] - speeds[segment])
    return np.vstack([dense, points[-1:]]), np.concatenate([dense_speeds, speeds[-1:]])


def _tool_bounds(samples: _ToolSamples, reach: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """The data (and reachable) extent, padded by a voxel."""
    every = samples.positions[np.isfinite(samples.positions).all(axis=1)]
    if reach is not None and len(reach):
        every = np.vstack([every, reach])
    if not len(every):
        return np.full(3, -VOXEL_M), np.full(3, VOXEL_M)
    return every.min(axis=0) - VOXEL_M, every.max(axis=0) + VOXEL_M


def _grid_cells(points: np.ndarray, size: float, low: np.ndarray, high: np.ndarray, axes) -> tuple[np.ndarray, list]:
    """Flat cell index (row-major over `axes`) of each point on a grid of `size` anchored at the base origin, -1
    outside; and the grid's shape. WHY anchored at the origin, not at the data: two datasets' cells line up."""
    first = np.floor(low[list(axes)] / size).astype(np.int64)
    shape = (np.floor(high[list(axes)] / size).astype(np.int64) - first + 1)
    with np.errstate(invalid="ignore"):
        index = np.floor(points[:, list(axes)] / size)
    inside = np.isfinite(index).all(axis=1)
    index = np.where(inside[:, None], index, 0).astype(np.int64) - first
    inside &= ((index >= 0) & (index < shape)).all(axis=1)
    flat = np.ravel_multi_index(tuple(np.where(inside[:, None], index, 0).T), tuple(shape))
    return np.where(inside, flat, -1), [int(n) for n in shape]


def _projection(samples: _ToolSamples, reach, low, high, axes: tuple[int, int]) -> dict:
    raw, shape = _grid_cells(samples.positions, PIXEL_M, low, high, axes)
    dense, _ = _grid_cells(samples.path_points, PIXEL_M, low, high, axes)
    cells = shape[0] * shape[1]
    on_path = dense >= 0
    paths, _ = _paths_per_cell(dense[on_path], samples.path_owner[on_path], cells)
    reachable = None
    if reach is not None:
        reach_cells, _ = _grid_cells(reach, PIXEL_M, low, high, axes)
        reachable = _ints(np.bincount(reach_cells[reach_cells >= 0], minlength=cells) > 0)
    origin = np.floor(low[list(axes)] / PIXEL_M) * PIXEL_M
    return {
        "origin": _floats(origin, 6),
        "shape": shape,
        "samples": _ints(np.bincount(raw[raw >= 0], minlength=cells)),
        "paths": _ints(paths),
        "max_speed": _floats(_max_per_cell(dense[on_path], samples.path_speeds[on_path], cells), 4),
        "reachable": reachable,
    }


def _voxels(samples: _ToolSamples, reach, low, high) -> dict:
    axes = (0, 1, 2)
    raw, shape = _grid_cells(samples.positions, VOXEL_M, low, high, axes)
    dense, _ = _grid_cells(samples.path_points, VOXEL_M, low, high, axes)
    total = int(np.prod(shape))
    on_path = dense >= 0
    counts = np.bincount(raw[raw >= 0], minlength=total)
    paths, _ = _paths_per_cell(dense[on_path], samples.path_owner[on_path], total)
    fastest = _max_per_cell(dense[on_path], samples.path_speeds[on_path], total)
    visited = np.flatnonzero(paths > 0)
    ix, iy, iz = np.unravel_index(visited, shape)
    cells = [[int(a), int(b), int(c), int(n), int(p), _number(round(float(v), 4))]
             for a, b, c, n, p, v in zip(ix, iy, iz, counts[visited], paths[visited], fastest[visited], strict=True)]
    reachable = None
    if reach is not None:
        reach_cells, _ = _grid_cells(reach, VOXEL_M, low, high, axes)
        unique = np.unique(reach_cells[reach_cells >= 0])
        reachable = np.column_stack(np.unravel_index(unique, shape)).tolist()
    return {"origin": _floats(np.floor(low / VOXEL_M) * VOXEL_M, 6), "size": VOXEL_M, "cells": cells,
            "reachable": reachable}


def _spaghetti(samples: _ToolSamples) -> list:
    """Every trajectory's tool path, evenly picked, in metres to 0.1 mm."""
    trajectories = len(samples.starts) - 1
    points = _points_per_trajectory(trajectories)
    lines = []
    for k in range(trajectories):
        start, stop = int(samples.starts[k]), int(samples.starts[k + 1])
        picked = _evenly_picked(stop - start, points) + start
        lines.append(np.round(samples.positions[picked], 4).tolist())
    return lines


def _speed_histogram(speeds: np.ndarray) -> dict:
    finite = speeds[np.isfinite(speeds)]
    fastest = float(finite.max()) if finite.size else 0.0
    if not fastest > 0:  # WHY: a tool that never moves still needs a non-empty axis
        fastest = 0.01
    index = _bin_index(finite, 0.0, fastest, SPEED_BINS)
    return {"edges": _edges(0.0, fastest, SPEED_BINS),
            "counts": _ints(np.bincount(index[index >= 0], minlength=SPEED_BINS))}


def _orientation(rotations: np.ndarray, tool_reference) -> tuple[dict, np.ndarray]:
    """Where the tool z axis points (sphere, tilt from the reference, azimuth) and its x axis heading (yaw), base frame;
    and every sample's tilt (rad)."""
    reference = np.asarray(tool_reference, float)
    reference = reference / np.linalg.norm(reference)
    z_axis, x_axis = rotations[:, :, 2], rotations[:, :, 0]
    tilt = np.arccos(np.clip(z_axis @ reference, -1.0, 1.0))
    azimuth = np.arctan2(z_axis[:, 1], z_axis[:, 0])
    yaw = np.arctan2(x_axis[:, 1], x_axis[:, 0])
    block = {
        "reference": [float(v) for v in reference],
        "sphere": {"rings": SPHERE_RINGS, "sectors": SPHERE_SECTORS, "counts": _ints(_sphere_counts(z_axis))},
        "tilt_azimuth": _grid_2d(tilt, (0.0, math.pi, TILT_GRID_BINS), azimuth, (-math.pi, math.pi, AZIMUTH_BINS),
                                 "tilt_edges", "azimuth_edges"),
        "tilt_yaw": _grid_2d(tilt, (0.0, math.pi, TILT_GRID_BINS), yaw, (-math.pi, math.pi, AZIMUTH_BINS),
                             "tilt_edges", "yaw_edges"),
        "tilt": _histogram_1d(tilt, 0.0, math.pi, TILT_BINS),
        "yaw": _histogram_1d(yaw, -math.pi, math.pi, YAW_BINS),
    }
    return block, tilt


def _sphere_counts(directions: np.ndarray) -> np.ndarray:
    """Equal-area cells of unit vectors (prior art sphere_cell): rings uniform in z (Archimedes: equal z bands have equal
    area) x sectors uniform in azimuth from -pi. Flat index ring * sectors + sector."""
    ring = np.clip(np.floor((directions[:, 2] + 1.0) / 2.0 * SPHERE_RINGS), 0, SPHERE_RINGS - 1).astype(np.int64)
    azimuth = np.arctan2(directions[:, 1], directions[:, 0])
    sector = np.clip(np.floor((azimuth + math.pi) / (2 * math.pi) * SPHERE_SECTORS), 0,
                     SPHERE_SECTORS - 1).astype(np.int64)
    return np.bincount(ring * SPHERE_SECTORS + sector, minlength=SPHERE_RINGS * SPHERE_SECTORS)


def _grid_2d(x_values, x_edges, y_values, y_edges, x_key: str, y_key: str) -> dict:
    x_index = _bin_index(x_values, *x_edges)
    y_index = _bin_index(y_values, *y_edges)
    inside = (x_index >= 0) & (y_index >= 0)
    nx, ny = x_edges[2], y_edges[2]
    return {x_key: _edges(*x_edges), y_key: _edges(*y_edges), "shape": [nx, ny],
            "counts": _ints(np.bincount(x_index[inside] * ny + y_index[inside], minlength=nx * ny))}


def _histogram_1d(values, low: float, high: float, bins: int) -> dict:
    index = _bin_index(values, low, high, bins)
    return {"edges": _edges(low, high, bins), "counts": _ints(np.bincount(index[index >= 0], minlength=bins))}


# ── source and headline numbers ─────────────────────────────────────────────────────────────────────────────────────


def _source(dataset: _Dataset, group_by: str | None, group_names: list[str]) -> dict:
    return {"trajectories": dataset.count, "samples": int(len(dataset.owner)),
            "duration_s": float(sum(dataset.durations)),
            "rate_hz": None if dataset.rate_hz is None else round(dataset.rate_hz, 6),
            "group_by": group_by or None, "groups": group_names}


def _headline_numbers(payload: dict, tool_extremes: dict[str, float]) -> list[dict]:
    """The scalars W&B logs and every viewer's numbers row shows; always finite."""
    hist, planes, source = payload["hist"], payload["planes"], payload["source"]
    joints = [joint["name"] for joint in payload["joints"]]

    def over_joints(reduce, pick) -> float:
        values = [value for value in (pick(joint) for joint in joints) if value is not None]
        return float(reduce(values)) if values else 0.0

    rows = [
        ("trajectories", "Trajectories", source["trajectories"], ""),
        ("samples", "Samples", source["samples"], ""),
        ("duration_s", "Total duration", source["duration_s"], "s"),
        ("q_span_median_pct", "Joint range used (median joint)",
         over_joints(np.median, lambda joint: hist[joint]["q"]["span_pct"]), "%"),
        ("q_span_min_pct", "Joint range used (least-used joint)",
         over_joints(min, lambda joint: hist[joint]["q"]["span_pct"]), "%"),
        ("qd_peak_max_pct", "Peak speed, fastest joint (% of its limit)",
         over_joints(max, lambda joint: hist[joint]["qd"]["peak_pct"]), "%"),
        ("qdd_peak_max_pct", "Peak acceleration, hardest joint (% of its limit)",
         over_joints(max, lambda joint: hist[joint]["qdd"]["peak_pct"]), "%"),
        ("q_qd_visited_mean_pct", "Angle x speed cells visited (mean over joints)",
         over_joints(np.mean, lambda joint: planes[joint]["q_qd"]["visited_pct"]), "%"),
        ("qd_qdd_visited_mean_pct", "Speed x acceleration cells visited (mean over joints)",
         over_joints(np.mean, lambda joint: planes[joint]["qd_qdd"]["visited_pct"]), "%"),
    ]
    if payload["tool"] is not None:
        rows += _tool_numbers(payload["tool"], tool_extremes)
    return [{"key": key, "label": label, "value": _finite(value), "unit": unit} for key, label, value, unit in rows]


def _tool_numbers(tool: dict, extremes: dict[str, float]) -> list[tuple]:
    xy = tool["projections"]["xy"]
    voxels = tool["voxels"]
    sphere = tool["orientation"]["sphere"]["counts"]
    rows = [
        ("tool_pixels_xy", "Tool path pixels, top view (2 cm)", sum(1 for paths in xy["paths"] if paths > 0), ""),
        ("tool_voxels_visited", "Tool path voxels (5 cm)", len(voxels["cells"]), ""),
    ]
    if voxels["reachable"] is not None:
        reachable = {tuple(cell) for cell in voxels["reachable"]}
        visited = sum(1 for cell in voxels["cells"] if tuple(cell[:3]) in reachable)
        rows.append(("tool_voxels_reachable_pct", "Reachable voxels the tool passed through",
                     100.0 * visited / max(len(reachable), 1), "%"))
    rows += [
        ("tool_speed_p99_m_s", "Tool speed, 99th percentile", extremes["speed_p99"], "m/s"),
        ("tool_directions_visited_pct", "Tool directions visited (equal-area sphere cells)",
         100.0 * sum(1 for count in sphere if count > 0) / len(sphere), "%"),
        ("tool_tilt_max_deg", "Largest tool tilt from the reference", math.degrees(extremes["tilt_max"]), "deg"),
    ]
    return rows


# ── JSON-safe values ────────────────────────────────────────────────────────────────────────────────────────────────


def _ints(values) -> list[int]:
    return np.asarray(values).astype(np.int64).tolist()


def _floats(values, decimals: int | None = None) -> list:
    """Python floats, NaN/inf -> None (json.dumps(allow_nan=False) must work)."""
    values = np.asarray(values, float)
    if decimals is not None:
        values = np.round(values, decimals)
    return [value if math.isfinite(value) else None for value in values.tolist()]


def _number(value) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def _finite(value) -> float:
    value = float(value)
    return value if math.isfinite(value) else 0.0


def _decimals(span: float, digits: int = 4) -> int:
    """Decimals that keep `digits` significant figures of a limit span (a path drawn on a figure needs no more)."""
    if not span > 0 or not math.isfinite(span):
        return 6
    return max(0, int(math.ceil(digits - math.log10(span))))
