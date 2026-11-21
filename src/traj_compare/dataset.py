"""The dataset view: many runs at a glance, then drill down into one (2026-11-11).

Zach: "across a bunch of runs, where was the error the highest… then drill down into particular
runs and view that recording in Rerun or our own viewer". The seams: ``robot_msgs.compare`` is the
math, ``traj_compare`` is the run view (``write_comparison_report``) plus this dataset view, and the
domain package (sim2real) supplies the runs, their tags, tolerances and a ``summary`` page.

    runs = [Run(name="can13 rep 0", reference=target, measured={"sim": sim, "real": real},
                tags={"tape": "A", "speed": 0.5})]
    write_dataset_report(runs, "out/", title="Wrist coverage", group_by=("tape",))
    # python -m traj_compare.serve out/      -> http://127.0.0.1:8767/

Three levels, organised around the target trajectory (docs/NAVIGATION.md Part A; Zach 2026-11-19, traj compare view
feedback: "the Target trajectory is kinda the primary thing we want to organize things around"): ``index.html`` opens on
the Dataset (every target at once, as cards, a league table or today's runs table), ``index.html#/target/<slug>`` is one
Target (its lines, repeatability per config, the control chart over dates), and ``runs/<slug>/report.html`` is one Run.

Files (file-first, so a dataset can be re-read, re-sorted or opened in pandas without this package)::

    out/index.html                  the at-a-glance page (scalars only, hash routes, works from file://)
    out/targets/<slug>.js           one target's drawn series (joint error, torque display series), at most target_budget
                                    values: a classic script index.html loads when that target is shown
    out/targets/<slug>.cache.json   that target's index entry and lines, under the key a later write reuses them by
    out/rows.json, rows.parquet     one row per run x pair x metric x stat, SI, every tag its own column
    out/runs/<slug>/manifest.json   what the drill-down needs to rebuild itself, and the run's digest; written last
    out/runs/<slug>/analysis.json   the run's index entries and tidy rows, under its digest, for a later write to reuse
    out/runs/<slug>/<series>.npz    robot_msgs's npz layout per series (``load_npz`` reads them back)
    out/runs/<slug>/<series>.torques.npz   the torque breakdown a series was given (tau_cmd / tau_ff / tau_fb), if any
    out/runs/<slug>/media/<key>.<ext>
    out/runs/<slug>/report.html     the run view, built lazily (or eagerly) from the files above
    out/references/<digest>.npz     each distinct reference once, named by a SHA-1 of its saved content; a manifest's
                                    ``files.reference`` is ``../../references/<digest>.npz`` (no per-run reference.npz),
                                    and a reference no ``runs/*/manifest.json`` names is deleted after the write

Every ``.npz`` is deflated (``np.savez_compressed``, values bit-identical), so ``load_npz`` and ``np.load`` read it
unchanged. A manifest written before 2026-11-20 names ``"reference.npz"`` beside its series and still builds.

Writes are incremental (NAVIGATION.md Part D): a run whose digest matches its folder's is reused, files untouched, and a
target whose key matches its ``.cache.json`` likewise; the output equals a ``reuse=False`` write. Every file goes to a
temporary name and is renamed into place (``_files``), so a hard-linked copy of a site can be rewritten without touching
the original, and ``progress(phase, done, total)`` reports the runs, reused, targets, index and drill phases.

Every number is ``robot_msgs.compare``'s (compare, check, aggregate, estimate_time_offset); nothing
here re-implements a metric. Angles are SI in the data and degrees in the human view.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import importlib.resources
import importlib.util
import inspect
import json
import math
import operator
import re
import shlex
import shutil
import struct
import sys
import warnings
from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs._core import from_dict, load_npz, to_dict
from robot_msgs.compare import (
    PoseTolerance,
    Tolerances,
    aggregate,
    check,
    compare,
    error_stats,
    estimate_time_offset,
)
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from . import _files, rerun_export
from .analysis import _BREAKDOWN_KEYS, _torque_breakdown
from .model import Comparison, ReportPage, RobotDisplay, Signal, Situation
from .report import write_comparison_report

REFERENCE = "reference"
Tag = str | int | float | bool
# Columns every row has; a tag may not reuse one of these names.
_FIXED_COLUMNS = ("run", "pair", "metric", "stat", "value", "unit")
_DRILL_DOWNS = ("lazy", "eager")
_TORQUE_KEYS = _BREAKDOWN_KEYS  # tau_cmd / tau_ff / tau_fb: Run.torques' keys, the run view's breakdown

_JOINT_UNITS = {"positions": "rad", "velocities": "rad/s", "accelerations": "rad/s²", "effort": "Nm"}
_POSE_UNITS = {
    "position": "m", "x": "m", "y": "m", "z": "m", "lag": "m", "cross_track": "m", "contour": "m",
    "rotation": "rad", "rx": "rad", "ry": "rad", "rz": "rad",
    "lag_time": "s", "linear_velocity": "m/s", "angular_velocity": "rad/s",
}  # fmt: skip


@dataclass
class Run:
    """One recorded run: the reference it was meant to follow and the series measured against it.

    - ``measured`` holds every series of this run by name (``"sim"``, ``"real"``, ``"sim_it5"``).
      ``"reference"`` is reserved for the target itself.
    - ``pairs`` is which (a, b) comparisons to make, each element ``"reference"`` or a series name;
      ``None`` = ``default_pairs`` (the target to each series, then every series to every other).
    - ``time_offset_s`` is how late a series' clock runs (``robot_msgs.compare``'s ``time_offset_s``);
      a pair (a, b) is taken with ``offset[b] - offset[a]``.
    - ``media`` maps a key to a video file. A key that equals a series name is that series' synced
      video in the drill-down; any other key is an extra clip listed on the run page.
      ``media_start_s`` is the trajectory time at video time 0 for that key.
    - ``torques`` is the command's torque breakdown per series (a key of ``measured``): any of ``"tau_cmd"``
      (commanded), ``"tau_ff"`` (feedforward), ``"tau_fb"`` (feedback), each (N, DOF) N·m on that series' own samples;
      1-D promotes to one column. Two of the three derive the third (the run view's rule). Applied stays the series'
      ``effort``, target the reference's ``effort``.
    """

    name: str
    reference: JointTrajectory
    measured: Mapping[str, JointTrajectory]
    tags: Mapping[str, Tag] = field(default_factory=dict)
    pairs: Sequence[tuple[str, str]] | None = None
    time_offset_s: Mapping[str, float] = field(default_factory=dict)
    title: str = ""
    media: Mapping[str, Path] = field(default_factory=dict)
    media_start_s: Mapping[str, float] = field(default_factory=dict)
    # WHY on the Run (Zach 2026-11-19, torque breakdown in the dataset view: "of the command torque some portion of that
    # is coming from Feedforward, and some portion of that is coming from feedback"): without it the dataset view could
    # not show that split, nor hand it to the run report it builds.
    torques: Mapping[str, Mapping[str, np.ndarray]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.torques = _checked_torques(self.name, self.measured, self.torques)

    def resolved_pairs(self) -> list[tuple[str, str]]:
        if self.pairs is None:
            return default_pairs(list(self.measured))
        return [(str(a), str(b)) for a, b in self.pairs]

    def series(self) -> dict[str, JointTrajectory]:
        """Every trajectory of the run by name, the reference first."""
        return {REFERENCE: self.reference, **self.measured}

    def relative_offset_s(self, first: str, second: str) -> float:
        return float(self.time_offset_s.get(second, 0.0)) - float(self.time_offset_s.get(first, 0.0))


def _checked_torques(
    run_name: str, measured: Mapping[str, JointTrajectory], torques: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, np.ndarray]]:
    """``Run.torques`` as float (N, DOF) arrays, or ``ValueError`` for an unknown series or key or a mismatched shape.

    WHY only tau_cmd / tau_ff / tau_fb (CONTRACT.md addendum): applied is already the series' ``effort``; a second
    "tau" here would be two sources for one signal. A series with no torque given is dropped, so ``{}`` is no breakdown.
    """
    checked: dict[str, dict[str, np.ndarray]] = {}
    for series, given in dict(torques or {}).items():
        if series not in measured:
            raise ValueError(f"run {run_name!r}: torques for {series!r}, which is no measured series; series are {sorted(measured)}")
        trajectory = measured[series]
        shape = (len(trajectory.t), len(trajectory.joint_names))
        parts: dict[str, np.ndarray] = {}
        for key, values in dict(given).items():
            if key not in _TORQUE_KEYS:
                raise ValueError(f"run {run_name!r}: torque {key!r} of {series!r} is not one of {_TORQUE_KEYS}")
            array = np.array(values, dtype=float)
            if array.ndim == 1:
                array = array[:, None]
            if array.shape != shape:
                raise ValueError(
                    f"run {run_name!r}: {series}.{key} has shape {array.shape}, the series' positions {shape} "
                    f"({len(trajectory.t)} samples x joints {list(trajectory.joint_names)})"
                )
            parts[key] = array
        if parts:
            checked[str(series)] = parts
    return checked


def default_pairs(series_names: Sequence[str]) -> list[tuple[str, str]]:
    """The target against each series, then every series against each later one."""
    names = list(series_names)
    pairs = [(REFERENCE, name) for name in names]
    pairs += [(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))]
    return pairs


# ── small helpers ────────────────────────────────────────────────────────────


def _finite(value: Any) -> Any:
    """JSON-safe number: NaN / inf are missing data (null), never 0."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    number = float(value)
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (float, int, bool, np.generic)):
        return _finite(value)
    return value


def _stats(stats: Any) -> dict[str, Any]:
    return {key: _finite(value) for key, value in stats.as_dict().items()}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def _safe_name(text: str) -> str:
    """A filename part that keeps the author's spelling where it can (``sim_it5`` stays)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "series"


def _tag_value(value: Any) -> Tag:
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (str, int, float, bool)):
        raise TypeError(f"a tag is a str, int, float or bool, got {type(value).__name__}: {value!r}")
    return value


def _pair_name(first: str, second: str) -> str:
    """The comparison's name, hence its .rrd's: stable, so the dataset page can link it before it exists."""
    return f"{_slug(first)}--{_slug(second)}"


def _metric_unit(metric: str) -> str:
    head, _, rest = metric.partition("/")
    if rest and head in _JOINT_UNITS:
        return _JOINT_UNITS[head]
    return _POSE_UNITS.get(metric, "")


def _stat_unit(unit: str, stat: str) -> str:
    """ErrorStats' integral criteria carry the signal's unit times time (rad·s, rad²·s, rad·s²)."""
    if not unit:
        return ""
    return {"iae": f"{unit}·s", "ise": f"{unit}²·s", "itae": f"{unit}·s²", "n": ""}.get(stat, unit)


def _group_key(tags: Mapping[str, Tag], group_by: Sequence[str]) -> str:
    if not group_by:
        return "all runs"
    return ", ".join(f"{key}={tags[key]}" if key in tags else f"{key}=—" for key in group_by)


def _same_reference(first: JointTrajectory, second: JointTrajectory) -> bool:
    return bool(
        first.joint_names == second.joint_names
        and first.header.stamp == second.header.stamp
        and first.t.shape == second.t.shape
        and np.allclose(first.t, second.t, rtol=0.0, atol=1e-12)
        and np.allclose(first.positions, second.positions, rtol=0.0, atol=1e-12, equal_nan=True)
    )


# ── import specs ("module:function") ─────────────────────────────────────────


def _split_spec(spec: str) -> tuple[str, str]:
    module, separator, function = spec.partition(":")
    if not (module and separator and function):
        raise ValueError(f"import spec must be 'module:function', got {spec!r}")
    return module, function


def _spec_import_root(spec: str) -> str | None:
    """The directory that has to be on sys.path for ``spec``'s module (stored in the manifest).

    WHY: a lazy drill-down is built later, in another process (``traj_compare.serve``), which has not
    imported the author's module; without this hint the poses / robot functions of an example run
    from a plain directory could not be found there.
    """
    top = _split_spec(spec)[0].partition(".")[0]
    found = importlib.util.find_spec(top)
    if found is None or not found.origin:
        return None
    origin = Path(found.origin)
    return str(origin.parent.parent if found.submodule_search_locations else origin.parent)


def _import_spec(spec: str, import_roots: Sequence[str] = ()) -> Callable[..., Any]:
    module_name, function = _split_spec(spec)
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        for root in import_roots:
            if root not in sys.path and Path(root).is_dir():
                sys.path.insert(0, root)
        module = importlib.import_module(module_name)
    return getattr(module, function)


# ── analysis of one run ──────────────────────────────────────────────────────


class _Analysis:
    """Everything the dataset view knows about the options of one write (tolerances, poses)."""

    def __init__(self, tolerances: Tolerances | None, poses: Callable[..., Any] | None) -> None:
        self.tolerances = tolerances
        self.poses = poses
        self.pose_tolerances = tolerances is not None and (
            isinstance(tolerances.path, PoseTolerance) or isinstance(tolerances.goal, PoseTolerance)
        )
        if self.pose_tolerances and poses is None:
            raise ValueError("pose tolerances judge a TCP pose trajectory; pass poses='module:function'")

    def pose_trajectories(self, run: Run) -> dict[str, PoseTrajectory]:
        if self.poses is None:
            return {}
        return {name: self.poses(trajectory) for name, trajectory in run.series().items()}


class _Poses(dict):
    """Run name -> that run's pose trajectories (``_Analysis.pose_trajectories``), each taken when first asked for.

    WHY lazy (NAVIGATION.md D1): a reused run's TCP is needed only by what this write recomputes (a target that is not
    reused, a ``group_by`` card over one reference), and the poses function was 1.5 s of the bench's 600-run build.
    """

    def __init__(self, runs: Sequence[Run], options: _Analysis) -> None:
        super().__init__()
        self._runs = {run.name: run for run in runs}
        self._options = options

    def __missing__(self, name: str) -> dict[str, PoseTrajectory]:
        poses = self[name] = self._options.pose_trajectories(self._runs[name])
        return poses


def _violation(violation: Any) -> dict[str, Any]:
    return {
        "phase": violation.phase,
        "metric": violation.metric,
        "t": _finite(violation.t),
        "error": _finite(violation.error),
        "limit": _finite(violation.limit),
    }


def _verdict(outcome: Any) -> dict[str, Any]:
    return {
        "code": outcome.error_code,
        "code_name": outcome.code_name,
        "ok": outcome.ok,
        "error_string": outcome.error_string,
        "violations": [_violation(violation) for violation in outcome.violations],
        "goal_time": _finite(outcome.goal_time),
        "unchecked": list(outcome.unchecked),
    }


def _peak_times(error: Any) -> dict[str, float | None]:
    """Seconds (on the error's own clock) of the largest |error| of each joint."""
    peaks: dict[str, float | None] = {}
    for column, name in enumerate(error.joint_names):
        magnitude = np.abs(error.positions[:, column])
        peaks[name] = None if np.isnan(magnitude).all() else float(error.t[np.nanargmax(magnitude)])
    return peaks


_SUMMARY_STATS = ("rms", "max_abs", "p95_abs", "final")


def _analyze_pair(
    run: Run, first: str, second: str, options: _Analysis, poses: Mapping[str, PoseTrajectory],
    joint_errors: dict[tuple[str, str], Any] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    """The payload entry of one run x pair, and its (metric name, ErrorStats) list for rows.json.

    ``joint_errors``, when given, keeps the joint comparison of a (reference, series) pair under (run, series), so the
    target level draws compare's own error series instead of comparing the pair a second time."""
    series = run.series()
    offset = run.relative_offset_s(first, second)
    joint = compare(series[first], series[second], time_offset_s=offset)
    if joint_errors is not None and first == REFERENCE:
        joint_errors[(run.name, second)] = joint
    metrics: list[tuple[str, Any]] = list(joint.metrics.items())
    entry: dict[str, Any] = {
        "joints": {
            name: {stat: _finite(getattr(joint.metrics[f"positions/{name}"], stat)) for stat in _SUMMARY_STATS}
            for name in joint.error.joint_names
        },
        "peak_t": _peak_times(joint.error),
        "tcp": None,
        "tcp_peak_t": None,
        "coverage": _finite(joint.coverage),
        "dropped": joint.dropped,
        "time_offset_s": _finite(offset),
        "latency_s": None,
    }
    if poses:
        tcp = compare(poses[first], poses[second], time_offset_s=offset)
        metrics += list(tcp.metrics.items())
        position = tcp.metrics["position"]
        entry["tcp"] = {stat: _finite(getattr(position, stat)) for stat in _SUMMARY_STATS}
        distance = np.linalg.norm(tcp.error.positions, axis=1)
        entry["tcp_peak_t"] = None if np.isnan(distance).all() else float(tcp.error.t[np.nanargmax(distance)])
    try:
        entry["latency_s"] = _finite(estimate_time_offset(series[first], series[second]).offset_s)
    except ValueError:  # too short to correlate: no estimate, not zero
        pass
    if options.tolerances is not None:
        judged = (poses[first], poses[second]) if options.pose_tolerances else (series[first], series[second])
        entry["verdict"] = _verdict(check(*judged, options.tolerances, time_offset_s=offset))
    return entry, metrics


def _analyze_run(
    run: Run, slug: str, options: _Analysis, poses: Mapping[str, PoseTrajectory],
    joint_errors: dict[tuple[str, str], Any],
) -> dict[str, list[dict[str, Any]]]:
    """One run's ``entries`` (its rows of the index payload, one per pair, error entries included) and its tidy ``rows``
    for rows.json: what its ``analysis.json`` keeps (NAVIGATION.md D1). JSON-clean, so a reused run's equal a fresh
    one's."""
    tags = {key: _tag_value(value) for key, value in run.tags.items()}
    entries: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for first, second in run.resolved_pairs():
        entry: dict[str, Any] = {
            "run": run.name,
            "slug": slug,
            "pair": [first, second],
            "tags": tags,
            "report": f"runs/{slug}/report.html",
            "rrd": f"runs/{slug}/rerun/{_pair_name(first, second)}.rrd",
        }
        try:
            analysis, metrics = _analyze_pair(run, first, second, options, poses, joint_errors)
        except ValueError as error:  # e.g. the two series never overlap in time
            # WHY recorded, not raised: one broken run must not hide the other 386; the row says why.
            warnings.warn(_pair_warning(run.name, first, second, error), stacklevel=3)
            entries.append({**entry, "error": str(error)})
            continue
        entries.append({**entry, **analysis})
        base = {"run": run.name, "pair": [first, second]}
        for metric, stats in metrics:
            unit = _metric_unit(metric)
            for stat, value in stats.as_dict().items():
                rows.append(
                    {**base, "metric": metric, "stat": stat, "value": _finite(value), "unit": _stat_unit(unit, stat), **tags}
                )  # fmt: skip
        for metric, stat, value, unit in (
            ("coverage", "value", analysis["coverage"], ""),
            ("latency", "value", analysis["latency_s"], "s"),
        ):
            rows.append({**base, "metric": metric, "stat": stat, "value": value, "unit": unit, **tags})
    return {"entries": _clean(entries), "rows": rows}


def _pair_warning(run_name: str, first: str, second: str, error: Any) -> str:
    return f"{run_name}: {first} -> {second}: {error}"


# ── ISO 9283 per group and series ────────────────────────────────────────────


def _group_aggregates(
    runs: Sequence[Run], group_by: Sequence[str], options: _Analysis, poses: Mapping[str, Mapping[str, PoseTrajectory]]
) -> dict[str, Any]:
    groups: dict[str, list[Run]] = {}
    for run in runs:
        groups.setdefault(_group_key(run.tags, group_by), []).append(run)
    result: dict[str, Any] = {}
    for key, members in groups.items():
        if len(members) < 2:
            result[key] = {"status": "needs at least 2 runs"}
            continue
        if not all(_same_reference(members[0].reference, run.reference) for run in members[1:]):
            # WHY named, not aggregated: ISO 9283 spread is "N runs of one reference"; against
            # different references the barycentre means nothing, so say so instead of a number.
            result[key] = {"status": "references differ"}
            continue
        names = list(dict.fromkeys(name for run in members for name in run.measured))
        cards: dict[str, Any] = {}
        for name in names:
            having = [run for run in members if name in run.measured]
            if len(having) < 2:
                cards[name] = {"status": "needs at least 2 runs"}
                continue
            offsets = [float(run.time_offset_s.get(name, 0.0)) for run in having]
            try:
                joint = aggregate(having[0].reference, [run.measured[name] for run in having], time_offset_s=offsets)
                accuracy = {metric: _stats(stats) for metric, stats in joint.accuracy.metrics.items()}
                repeatability = {metric: _stats(stats) for metric, stats in joint.metrics.items()}
                coverage = joint.coverage
                if options.poses is not None:
                    tcp = aggregate(
                        poses[having[0].name][REFERENCE],
                        [poses[run.name][name] for run in having],
                        time_offset_s=offsets,
                    )
                    accuracy.update({metric: _stats(stats) for metric, stats in tcp.accuracy.metrics.items()})
                    repeatability.update({metric: _stats(stats) for metric, stats in tcp.metrics.items()})
            except ValueError as error:
                cards[name] = {"status": str(error)}
                continue
            cards[name] = {
                "runs": [run.name for run in having],
                "coverage": _finite(coverage),
                "accuracy": accuracy,
                "repeatability": repeatability,
            }
        result[key] = cards
    return result


# ── which series the default view shows ──────────────────────────────────────


def _visible(name: str, primary: Mapping[str, str]) -> bool:
    """WHY this rule (Sim to Real agent, 2026-11-11): a twin has many iterations (sim_record, sim_it5,
    ...) but one is *the* sim. ``primary={"sim": "sim_it5"}`` names it; the view then shows the
    reference, the primary series, and every series that is not an iteration of an alias
    (neither named like one nor starting ``<alias>_``). rows.json always holds every pair."""
    if name == REFERENCE or name in primary.values():
        return True
    return name not in primary and not any(name.startswith(f"{alias}_") for alias in primary)


# ── the three levels: targets, configs, lines (docs/NAVIGATION.md Part A) ────

TARGET_TAG = "target"
DATE_TAG = "date"
# Config colours, fixed across every level (NAVIGATION.md C4). WHY grey only in the twin case (exactly one config has no
# real line, and another has real lines): there grey reads "the twin", the one sim beside the real configs. Grey for every
# sim-only config painted arm_motion_bench's four sim-only controllers in four indistinguishable greys (2026-11-20), so
# every other config takes the next hue, sim-only or not, and kind is told by the dashed line and hollow swatch instead.
# WHY never blue or orange: those are the feedforward / feedback torque colours of the run view (CONTRACT.md).
_TWIN_GREY = "#5f5e5a"
_CONFIG_COLOURS = ("#7c5cc4", "#0f9d8a", "#c22f6e", "#a67c00", "#17a2b8", "#5c8a2e", "#b8457a", "#8c6d46", "#2e7d6b")
_TORQUE_COLOURS = ("#2a78d6", "#eb6834")
_HUES: list[str] = list(_CONFIG_COLOURS)  # the named hues, then generated ones appended as a dataset needs them


def _lab(colour: str) -> tuple[float, float, float]:
    """CIELAB (D65) of an sRGB ``#rrggbb``."""
    channels = [int(colour[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    return 116.0 * f(y) - 16.0, 500.0 * (f(x) - f(y)), 200.0 * (f(y) - f(z))


def _hex_of_lab(lightness: float, a: float, b: float) -> str | None:
    """The sRGB ``#rrggbb`` of a CIELAB colour, or None when it lies outside sRGB."""
    fy = (lightness + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def inverse(t: float) -> float:
        return t**3 if t**3 > 0.008856 else (t - 16.0 / 116.0) / 7.787

    x, y, z = 0.95047 * inverse(fx), inverse(fy), 1.08883 * inverse(fz)
    linear = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z, 0.0557 * x - 0.2040 * y + 1.0570 * z)
    if any(value < -1e-4 or value > 1.0 + 1e-4 for value in linear):
        return None
    encoded = [min(1.0, max(0.0, v)) for v in linear]
    encoded = [12.92 * v if v <= 0.0031308 else 1.055 * v ** (1.0 / 2.4) - 0.055 for v in encoded]
    return "#" + "".join(f"{round(v * 255):02x}" for v in encoded)


def _config_hues(count: int) -> list[str]:
    """The first ``count`` hues configs take: the named ones, then generated ones, each the in-gamut colour (mid lightness,
    clear chroma, far from the torque blue and orange) farthest in CIELAB from every hue before it, the torque colours
    and the twin grey. Deterministic, so a config keeps its colour from one write to the next."""
    if len(_HUES) < count:
        avoid = [_lab(colour) for colour in (*_TORQUE_COLOURS, _TWIN_GREY)]
        candidates = []
        for lightness in (40.0, 48.0, 56.0, 64.0):  # WHY not lighter: a line must read on the near-white page
            for chroma_value in (38.0, 52.0, 66.0):
                for hue in range(0, 360, 10):
                    angle = math.radians(hue)
                    colour = _hex_of_lab(lightness, chroma_value * math.cos(angle), chroma_value * math.sin(angle))
                    if colour and min(math.dist(_lab(colour), torque) for torque in avoid[:2]) >= 30.0:
                        candidates.append(colour)
        taken = [_lab(colour) for colour in _HUES] + avoid
        while len(_HUES) < count:
            free = [colour for colour in candidates if colour not in _HUES] or candidates
            best = max(free, key=lambda colour: min(math.dist(_lab(colour), other) for other in taken))
            _HUES.append(best)
            taken.append(_lab(best))
    return _HUES[:count]


def _kind(series: str) -> str:
    """``real`` when the series name starts with "real", else ``sim`` (data_ui's family rule, NAVIGATION.md)."""
    return "real" if series.startswith("real") else "sim"


def _reference_digest(reference: JointTrajectory) -> str:
    """The content hash that names a target nothing else names: the reference's ``t`` and ``q`` bytes."""
    digest = hashlib.sha1()
    digest.update(np.ascontiguousarray(reference.t, dtype=np.float64).tobytes())
    digest.update(np.ascontiguousarray(reference.positions, dtype=np.float64).tobytes())
    return digest.hexdigest()[:12]


@dataclass
class _Target:
    key: str
    runs: list[Run]
    named_by: str | None  # the tag whose value is the key, or None for a content hash
    slug: str = ""

    @property
    def reference(self) -> JointTrajectory:
        return self.runs[0].reference

    @property
    def title(self) -> str:
        """A hashed target is titled by its first run; a tagged one by the title every run shares, else its key."""
        if self.named_by is None:
            return self.runs[0].title or self.runs[0].name
        titles = {run.title for run in self.runs}
        return titles.pop() if len(titles) == 1 and self.runs[0].title else self.key


def _target_tag(runs: Sequence[Run], group_by: Sequence[str], target_by: str | None) -> str | None:
    """NAVIGATION.md's precedence: ``target_by``; else the "target" tag when any run has it; else the first ``group_by`` tag."""
    if target_by is not None:
        if not any(target_by in run.tags for run in runs):
            raise ValueError(f"target_by={target_by!r} is a tag no run has; tags are {sorted({k for r in runs for k in r.tags})}")
        return target_by
    if any(TARGET_TAG in run.tags for run in runs):
        return TARGET_TAG
    return group_by[0] if group_by else None


def _resolve_targets(runs: Sequence[Run], tag: str | None, explicit: bool) -> list[_Target]:
    """The runs grouped by the trajectory they follow, in order of first appearance.

    A run without the tag is keyed by its reference's content hash. Two different references under one explicit
    ``target_by`` value raise ``ValueError`` naming both runs. WHY only explicit: a defaulted tag (the first ``group_by``
    tag, e.g. a tape that ran at two amplitudes) is a grouping the author asked for elsewhere, not a claim that its runs
    follow one trajectory; such a value is split into one target per reference ("tape A", "tape A (2)") instead.
    """
    targets: dict[str, _Target] = {}
    splits: dict[str, list[str]] = {}
    for run in runs:
        if tag is not None and tag in run.tags:
            value = str(_tag_value(run.tags[tag]))
            keys = splits.setdefault(value, [])
            home = next((targets[key] for key in keys if _same_reference(targets[key].reference, run.reference)), None)
            if home is not None:
                home.runs.append(run)
                continue
            if keys and explicit:
                first = targets[keys[0]].runs[0]
                raise ValueError(
                    f"target_by={tag!r}: {value!r} holds two different references, run {first.name!r} and run {run.name!r}; "
                    "a target is one trajectory, so give them different values"
                )
            key = value if not keys else f"{value} ({len(keys) + 1})"
            keys.append(key)
            targets[key] = _Target(key, [run], tag)
        else:
            key = _reference_digest(run.reference)
            if key in targets:
                targets[key].runs.append(run)
            else:
                targets[key] = _Target(key, [run], None)
    taken: set[str] = set()
    for target in targets.values():
        slug, count = _slug(target.key), 1
        target.slug = slug
        while target.slug in taken:
            count += 1
            target.slug = f"{slug}-{count}"
        taken.add(target.slug)
    return list(targets.values())


def _config_tag(runs: Sequence[Run], group_by: Sequence[str], config_by: str | None, target_tag: str | None) -> str | None:
    """``config_by``; else the first ``group_by`` tag that does not name the target (the second when the first does);
    else None: a line's config is then its series name."""
    if config_by is not None:
        if not any(config_by in run.tags for run in runs):
            raise ValueError(f"config_by={config_by!r} is a tag no run has; tags are {sorted({k for r in runs for k in r.tags})}")
        return config_by
    others = [key for key in group_by if key != target_tag]
    return others[0] if others else None


def _picked_on(grid: np.ndarray, times: np.ndarray, values: np.ndarray | None, scale: float = 1.0) -> np.ndarray:
    """``values`` (on the line's own ``times``) at the grid's instants times ``scale``; NaN outside the line's samples,
    where a value is not finite, and everywhere when ``values`` is None (a joint the line does not have).

    WHY interpolate: every line of a target is drawn on that target's display grid (the reference's samples, picked at
    ``display_hz``) so a percentile fan can be taken per instant; when a line was sampled on the reference's instants
    (the usual case) this is exact picking, never averaging. Outside the line's span it is missing, never extrapolated.
    """
    if values is None or len(times) == 0:
        return np.full(len(grid), np.nan)
    inside = (grid >= times[0] - 1e-9) & (grid <= times[-1] + 1e-9)
    picked = np.interp(grid, times, np.asarray(values, dtype=float)) * scale
    return np.where(inside & np.isfinite(picked), picked, np.nan)


def _series_json(rows: Sequence[np.ndarray]) -> str:
    """One list per row, 4 decimals, ``null`` for NaN: the target file's layout of a per-joint series.

    WHY through numpy and one ``json.dumps``: a site's target files hold millions of values (UR5e: 4932 lines), and a
    Python ``round`` per value was the slow part of the old index; NaN is the only token ``json.dumps`` writes as ``NaN``.
    """
    return json.dumps(np.round(np.asarray(rows, dtype=float), 4).tolist(), separators=(",", ":")).replace("NaN", "null")


# The FB share over time (Zach 2026-11-19, torque breakdown in the dataset view; CONTRACT.md addendum): Σ|fb| / (Σ|ff| +
# Σ|fb|) over ±150 ms around each sample. WHY a floor under the denominator: where a joint is parked its command is
# ~0, so a hair of feedback alone would read 100 %; the window's denominator is held to at least 5 % of the joint's
# typical |ff| + |fb| (its mean over the line), so a parked joint reads near 0 % and a moving one is untouched.
_SHARE_WINDOW_S = 0.15
_SHARE_FLOOR = 0.05


def _share_over_time(t: np.ndarray, feedforward: np.ndarray, feedback: np.ndarray) -> np.ndarray:
    """The feedback share of one joint's command over a ±``_SHARE_WINDOW_S`` window, on its own samples (NaN where
    the window holds no finite sample). A plain ratio of sums, as the run view's ``fb_share``; no new statistic."""
    ff, fb = np.abs(feedforward), np.abs(feedback)
    finite = np.isfinite(ff) & np.isfinite(fb)
    ff, fb = np.where(finite, ff, 0.0), np.where(finite, fb, 0.0)

    def windowed(values: np.ndarray) -> np.ndarray:
        running = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
        return running[high] - running[low]

    low = np.searchsorted(t, t - _SHARE_WINDOW_S, side="left")
    high = np.searchsorted(t, t + _SHARE_WINDOW_S, side="right")
    count = windowed(finite.astype(float))
    typical = float(np.mean(ff[finite] + fb[finite])) if finite.any() else 0.0
    denominator = np.maximum(windowed(ff) + windowed(fb), _SHARE_FLOOR * typical * count)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = windowed(fb) / denominator
    return np.where((count > 0) & (denominator > 0.0), share, np.nan)


def _fb_share(feedforward: np.ndarray, feedback: np.ndarray) -> float | None:
    """Σ|fb| / (Σ|ff| + Σ|fb|) over the samples where both are finite (the run view's ``fb_share``, any shape)."""
    both = np.isfinite(feedforward) & np.isfinite(feedback)
    fb_sum = float(np.sum(np.abs(feedback[both])))
    total = float(np.sum(np.abs(feedforward[both]))) + fb_sum
    return fb_sum / total if total > 0.0 else None


def _line_torque(
    series: str, measured: JointTrajectory, given: Mapping[str, np.ndarray], joints: Sequence[str]
) -> tuple[dict[str, Any], dict[str, list[np.ndarray | None]]]:
    """One line's torque breakdown: its scalars for the index (``line["torque"]``) and its display series for its target
    file, before they are picked on the target's grid.

    The missing third comes from the run view's two-of-three rule (``analysis._torque_breakdown``); the drive gap is
    ``robot_msgs.compare.error_stats``' RMS of commanded − applied (applied = the series' ``effort``); the shares are
    plain sums. The display series ``tau_fb`` and ``fb_share_over_time`` are per joint in ``joints`` order on the line's
    own samples (None for a joint it does not have); a series the breakdown cannot give is absent.
    """
    situation = Situation(name=series, t=measured.t, q=measured.positions, tau=measured.effort, **given)
    breakdown, _ = _torque_breakdown(situation)
    command, feedforward, feedback = (breakdown[key] for key in _BREAKDOWN_KEYS)
    applied = situation.tau
    column_of = {name: index for index, name in enumerate(measured.joint_names)}
    t = np.asarray(measured.t, dtype=float)
    both = feedforward is not None and feedback is not None
    per_joint: dict[str, dict[str, float | None]] = {}
    drawn: dict[str, list[np.ndarray | None]] = {}
    if feedback is not None:
        drawn["tau_fb"] = []
    if both:
        drawn["fb_share_over_time"] = []
    for name in joints:
        column = column_of.get(name)
        share = gap = None
        if column is not None and both:
            share = _fb_share(feedforward[:, column], feedback[:, column])
        if column is not None and command is not None and applied is not None:
            gap = _finite(error_stats(command[:, column] - applied[:, column], t).rms)
        per_joint[name] = {"fb_share": share, "drive_gap_rms": gap}
        if feedback is not None:
            drawn["tau_fb"].append(None if column is None else feedback[:, column])
        if both:
            drawn["fb_share_over_time"].append(
                None if column is None else _share_over_time(t, feedforward[:, column], feedback[:, column])
            )
    scalars = {"fb_share": _fb_share(feedforward, feedback) if both else None, "joints": per_joint}
    return scalars, drawn


def _target_stride(
    reference: JointTrajectory, display_hz: float, per_sample: int, budget: int, key: str
) -> tuple[int, int, float | None]:
    """(rows of the reference to step by, the rows ``display_hz`` alone steps by, its native rate) for one target's file
    (NAVIGATION.md C5).

    data_ui's ``_stride`` at ``display_hz`` (picked, never averaged), grown to the smallest stride at which the file's
    ``per_sample`` drawn values per grid instant fit ``budget``, so a target draws as many samples as its budget allows.
    """
    from .data_ui import _stride  # lazy: data_ui imports this module

    stride, rate = _stride(reference, display_hz)
    display_stride, samples = stride, len(reference.t)
    if per_sample > 0:
        fits = budget // per_sample  # grid instants the budget holds
        if fits < 1:
            warnings.warn(
                f"target {key!r}: {per_sample} drawn values per instant exceed target_budget={budget}; its file draws "
                "one instant", stacklevel=3,
            )  # fmt: skip
            fits = 1
        stride = max(stride, -(-samples // fits))  # ceil: the first stride whose ceil(samples / stride) <= fits
    return stride, display_stride, rate


def _target_level(
    target: _Target, order: Mapping[str, int], slugs: Mapping[str, str], config_tag: str | None,
    joint_errors: Mapping[tuple[str, str], Any], analysed: Mapping[tuple[str, str], Mapping[str, Any]], options: _Analysis,
    poses: Mapping[str, Mapping[str, PoseTrajectory]], display_hz: float, labels: Mapping[str, str], target_budget: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """What the Dataset and Target levels draw of one target: its entry in ``levels.targets`` (with its own
    ``has_torque_breakdown``, before ``_site_levels``), its lines in ``levels.lines`` (one per measured series of each of
    its runs), and the data of its file ``targets/<slug>.js``.

    The index keeps each line's scalars only, SI (rad, like ``rows``). Every line's drawn series go to the target's file
    (NAVIGATION.md C5): ``e_deg``, the joint error target − line in degrees, and the torque display series, on the
    target's display grid (the display edge, like data_ui's tables), picked at ``display_hz`` and thinned further until the
    file holds at most ``target_budget`` values. Every number is robot_msgs.compare's. ``analysed`` holds the index
    entry of each (reference, series) pair by (run name, series); ``order`` each run's place in this write.
    """
    reference = target.reference
    reference_t = np.asarray(reference.t, dtype=float)
    joints = list(reference.joint_names)
    members: dict[str, dict[str, list[tuple[Run, str]]]] = {}
    own_lines: list[dict[str, Any]] = []
    # (line id, its samples on the target clock, error per joint (rad), its samples for torque, torque series)
    series_of: list[tuple[str, np.ndarray, list[np.ndarray | None], np.ndarray | None, dict[str, list]]] = []
    for run in target.runs:
        for series, measured in run.measured.items():
            kind = _kind(series)
            if config_tag is None:
                config = series
            else:
                config = str(_tag_value(run.tags[config_tag])) if config_tag in run.tags else f"no {config_tag}"
            members.setdefault(config, {"sim": [], "real": []})[kind].append((run, series))
            line: dict[str, Any] = {
                "id": f"{run.name} · {series}",
                "run": run.name,
                "series": series,
                "label": labels.get(series, series),
                "target": target.slug,
                "config": config,
                "kind": kind,
                "date": str(_tag_value(run.tags[DATE_TAG])) if DATE_TAG in run.tags else "",
                "order": order[run.name],
                "report": f"runs/{slugs[run.name]}/report.html",
            }
            offset = run.relative_offset_s(REFERENCE, series)
            try:
                joint = joint_errors.get((run.name, series)) or compare(reference, measured, time_offset_s=offset)
            except ValueError as error:  # e.g. no overlap: the line is listed and says why, it draws nothing
                own_lines.append({**line, "error": str(error)})
                continue
            entry = analysed.get((run.name, series))
            rms = {name: _finite(joint.metrics[f"positions/{name}"].rms) for name in joint.error.joint_names}
            worst = max((name for name in rms if rms[name] is not None), key=lambda name: rms[name], default=None)
            times = joint.error.absolute_times - offset - float(reference.header.stamp)
            columns = {name: index for index, name in enumerate(joint.error.joint_names)}
            line.update(
                rms=rms,
                worst_rms=None if worst is None else rms[worst],
                worst_joint=worst,
                coverage=_finite(joint.coverage),
                ok=(entry or {}).get("verdict", {}).get("ok") if options.tolerances is not None else None,
            )
            errors = [joint.error.positions[:, columns[name]] if name in columns else None for name in joints]
            torque_times, drawn = None, {}
            # WHY only when given (Zach 2026-11-19, torque breakdown in the dataset view; CONTRACT.md addendum): a
            # line without a breakdown carries no torque key at all, so a dataset without one is today's payload.
            if run.torques.get(series):
                torque_times = np.asarray(measured.absolute_times, dtype=float) - offset - float(reference.header.stamp)
                line["torque"], drawn = _line_torque(series, measured, run.torques[series], joints)
            series_of.append((line["id"], times, errors, torque_times, drawn))
            own_lines.append(line)
    # One drawn value per joint per series per grid instant: e_deg, then tau_fb and fb_share_over_time if given.
    per_sample = sum(len(joints) * (1 + len(drawn)) for _, _, _, _, drawn in series_of)
    stride, display_stride, rate = _target_stride(reference, display_hz, per_sample, target_budget, target.key)
    grid = reference_t[::stride]
    # The file's object, written as text one line at a time (see _series_json): {"slug", "points", "stride",
    # "drawn_hz", "lines": [{"id", "e_deg": [per joint], "torque": {"tau_fb", "fb_share_over_time"}}]}.
    drawn_lines = []
    for line_id, times, errors, torque_times, drawn in series_of:
        e_deg = _series_json([_picked_on(grid, times, values, 180.0 / math.pi) for values in errors])
        text = f'{{"id":{json.dumps(line_id)},"e_deg":{e_deg}'
        if drawn:
            parts = [
                f"{json.dumps(key)}:{_series_json([_picked_on(grid, torque_times, v) for v in values])}"
                for key, values in drawn.items()
            ]
            text += f',"torque":{{{",".join(parts)}}}'
        drawn_lines.append(text + "}")
    head = {"slug": target.slug, "points": len(grid), "stride": stride, "drawn_hz": None if rate is None else rate / stride}
    data = json.dumps(head, separators=(",", ":"))[:-1] + ',"lines":[' + ",".join(drawn_lines) + "]}"
    target_row: dict[str, Any] = {
        "key": target.key,
        "slug": target.slug,
        "title": target.title,
        "named_by": target.named_by,
        "joints": joints,
        "t": [round(float(value), 4) for value in grid],
        # the rate the target's file draws (NAVIGATION.md C5): its reference's, picked every ``stride``-th sample;
        # ``capped`` when target_budget thinned it below display_hz
        "rate_hz": rate,
        "stride": stride,
        "drawn_hz": None if rate is None else rate / stride,
        "capped": stride > display_stride,
        "runs": len(target.runs),
        "repeatability": {
            config: _repeatability(reference, kinds["real"] or kinds["sim"], poses, options)
            for config, kinds in members.items()
        },
    }
    target_row["has_torque_breakdown"] = any(line.get("torque") for line in own_lines)
    return target_row, own_lines, data


def _site_levels(target_rows: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, Any]:
    """``levels`` from every target's entry and lines, in target order: the site-wide pieces no one target decides,
    recomputed on every write (NAVIGATION.md D1b): each config's line counts and colour (C4), its ``fb_share_median``,
    and the ``has_torque_breakdown`` flags, which stay only when some target has a breakdown."""
    configs: dict[str, dict[str, int]] = {}
    for line in lines:  # error lines too; configs in order of first appearance, so a config keeps its colour
        configs.setdefault(line["config"], {"sim": 0, "real": 0})[line["kind"]] += 1
    any_breakdown = any(row["has_torque_breakdown"] for row in target_rows)
    if not any_breakdown:
        for row in target_rows:
            del row["has_torque_breakdown"]
    config_rows = []
    sim_only = [name for name, kinds in configs.items() if kinds["real"] == 0]
    twin = sim_only[0] if len(sim_only) == 1 and len(configs) > 1 else None  # see _TWIN_GREY
    hues = iter(_config_hues(len(configs) - (twin is not None)))
    for name, kinds in configs.items():
        row = {"name": name, "color": _TWIN_GREY if name == twin else next(hues), **kinds}
        if any_breakdown:
            row["fb_share_median"] = _fb_share_median([line for line in lines if line["config"] == name])
        config_rows.append(row)
    levels: dict[str, Any] = {"targets": target_rows, "configs": config_rows, "lines": lines}
    if any_breakdown:
        levels["has_torque_breakdown"] = True
    return levels


def _fb_share_median(lines: Sequence[Mapping[str, Any]]) -> float | None:
    """The summary band's median feedback share of one config: over its lines' overall ``fb_share``, its real lines when
    any of them has one (as the band's RMS median), else its sim lines; None when no line has a share.
    The median is ``robot_msgs.compare.error_stats``' (the package's one source of statistics)."""
    having = [line for line in lines if (line.get("torque") or {}).get("fb_share") is not None]
    real = [line for line in having if line["kind"] == "real"]
    shares = [line["torque"]["fb_share"] for line in (real or having)]
    return _finite(error_stats(np.asarray(shares, dtype=float)).median) if shares else None


def _repeatability(
    reference: JointTrajectory, members: Sequence[tuple[Run, str]], poses: Mapping[str, Mapping[str, PoseTrajectory]],
    options: _Analysis,
) -> dict[str, Any]:
    """ISO 9283 path repeatability (RT) of one config's repeats on one target: ``robot_msgs.compare.aggregate``'s spread
    (mean + 3σ around the repeats' own mean), worst over the path, per joint (rad) and of the TCP (m) with ``poses``.
    Taken over the config's real lines (repeatability = same everything, run again), its sim lines only when it has none."""
    if len(members) < 2:
        return {"status": "needs at least 2 repeats", "n": len(members)}
    offsets = [float(run.time_offset_s.get(series, 0.0)) for run, series in members]
    try:
        joint = aggregate(reference, [run.measured[series] for run, series in members], time_offset_s=offsets)
        tcp = None
        if options.poses is not None:
            first = members[0][0].name
            spread = aggregate(poses[first][REFERENCE], [poses[run.name][series] for run, series in members], time_offset_s=offsets)
            tcp = _finite(spread.metrics["position"].max)
    except ValueError as error:
        return {"status": str(error), "n": len(members)}
    return {
        "n": len(members),
        "joints": {
            metric.partition("/")[2]: _finite(stats.max) for metric, stats in joint.metrics.items() if metric.startswith("positions/")
        },
        "tcp": tcp,
    }


# ── writing ──────────────────────────────────────────────────────────────────


def _unique_slugs(runs: Sequence[Run]) -> dict[str, str]:
    names = [run.name for run in runs]
    if len(set(names)) != len(names):
        duplicated = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"run names identify rows and must be unique, got duplicates {duplicated}")
    slugs: dict[str, str] = {}
    taken: set[str] = set()
    for name in names:
        slug = _slug(name)
        candidate, count = slug, 1
        while candidate in taken:
            count += 1
            candidate = f"{slug}-{count}"
        taken.add(candidate)
        slugs[name] = candidate
    return slugs


def _validate(runs: Sequence[Run], group_by: Sequence[str], primary: Mapping[str, str]) -> None:
    if not runs:
        raise ValueError("need at least one run")
    series_seen: set[str] = set()
    for run in runs:
        for name in run.measured:
            if name == REFERENCE:
                raise ValueError(f"run {run.name!r}: {REFERENCE!r} is the target's name, not a series name")
        known = set(run.series())
        for first, second in run.resolved_pairs():
            if first not in known or second not in known or first == second:
                raise ValueError(f"run {run.name!r}: pair {(first, second)} needs two different names from {sorted(known)}")
        for tag in run.tags:
            if tag in _FIXED_COLUMNS:
                raise ValueError(f"run {run.name!r}: tag {tag!r} collides with a rows.json column {_FIXED_COLUMNS}")
        files = [_safe_name(name) for name in run.measured]
        if len(set(files)) != len(files):
            raise ValueError(f"run {run.name!r}: series names collide as filenames: {list(run.measured)}")
        media_files = [_safe_name(key) for key in run.media]
        if len(set(media_files)) != len(media_files):
            raise ValueError(f"run {run.name!r}: media keys collide as filenames: {list(run.media)}")
        series_seen.update(run.measured)
    for key in group_by:
        if key in _FIXED_COLUMNS:
            raise ValueError(f"group_by {key!r} collides with a rows.json column")
    missing = [series for series in primary.values() if series not in series_seen]
    if missing:
        raise ValueError(f"primary names series no run has: {missing}; series are {sorted(series_seen)}")
    if len(set(primary.values())) != len(primary):
        raise ValueError(f"primary maps two aliases to one series: {dict(primary)}")


def _drawable(values: Any) -> bool:
    """Whether the run view can draw a channel: numbers, (N,) or (N, k). Labels and (N, a, b) blocks it cannot."""
    array = np.asarray(values)
    return array.dtype.kind in "biuf" and array.ndim in (1, 2)


def _validate_channels(runs: Sequence[Run], signals: Mapping[str, Signal]) -> None:
    """Every series' ``channels``, checked when the dataset is written, so a drill-down never fails on them (NAVIGATION.md C1).

    ``channels["current"]`` is motor current, (N, J) in that series' ``joint_names`` order; any other shape raises
    ``ValueError`` naming run, series and shape. A described channel must fit its ``Signal`` (``per_joint``: (N, J);
    ``columns``: one per column), and one channel keeps one shape across a run's series (one plot per column).
    """
    for name, signal in signals.items():
        if not isinstance(signal, Signal):
            raise ValueError(f"signals[{name!r}] must be a traj_compare.Signal, got {type(signal).__name__}")
    for run in runs:
        shapes: dict[str, tuple[tuple[int, ...], str]] = {}  # channel -> (shape past N, the first series with it)
        for series, trajectory in run.series().items():
            joints = list(trajectory.joint_names)
            for key, values in trajectory.channels.items():
                shape = tuple(np.shape(values))
                if key == "current":
                    # WHY (N,) too on one joint: a 1-DOF rig (the bench's pendulum) logs current flat, and Run.torques
                    # already promotes 1-D to one column; on two or more joints a flat current names no joint.
                    if shape != (len(trajectory.t), len(joints)) and not (len(joints) == 1 and shape == (len(trajectory.t),)):
                        raise ValueError(
                            f"run {run.name!r}: series {series!r} has channels['current'] of shape {shape}; motor current "
                            f"is (N, J) = {(len(trajectory.t), len(joints))}, amperes, one column per joint of {joints}"
                        )
                    continue
                if not _drawable(values):
                    continue  # the drill-down says it is not drawn, and why
                where = f"run {run.name!r}: series {series!r}, channel {key!r}"
                first = shapes.setdefault(key, (shape[1:], series))
                if first[0] != shape[1:]:
                    recorded = "(N, " + ", ".join(map(str, first[0])) + ")" if first[0] else "(N,)"
                    raise ValueError(f"{where} has shape {shape}, but series {first[1]!r} records it {recorded}; one shape per channel")
                signal = signals.get(key)
                if signal is None:
                    continue
                if signal.per_joint and shape[1:] != (len(joints),):
                    raise ValueError(f"{where} has shape {shape}; per_joint needs (N, {len(joints)}), one column per joint of {joints}")
                count = shape[1] if len(shape) == 2 else 1
                if signal.columns and len(signal.columns) != count:
                    raise ValueError(f"{where} has {count} column(s), but its Signal names {list(signal.columns)}")


def _torque_file(series: str) -> str:
    """``<series>.torques.npz``, the series named as its ``<series>.npz`` is (``real`` -> ``real.torques.npz``)."""
    return f"{_safe_name(series)}.torques.npz"


# What robot_msgs' save_npz stores for a message: its ``__msg__`` JSON and the arrays that JSON names by key.
_NpzContent = tuple[str, dict[str, np.ndarray]]


def _npz_content(message: Any) -> _NpzContent:
    arrays: dict[str, np.ndarray] = {}
    return json.dumps(to_dict(message, arrays=arrays)), arrays


def _save_npz(message: Any, path: Path, content: _NpzContent | None = None) -> None:
    """robot_msgs' ``save_npz`` layout (``__msg__`` + its arrays), deflated (NAVIGATION.md C6).

    ``robot_msgs._core.load_npz`` and ``np.load`` read it unchanged, values bit-identical. WHY not robot_msgs' own
    ``save_npz``: it stores uncompressed, and the UR5e site's 0.81 GB of references were 886 KB each, 528 KB deflated.
    """
    tree, arrays = content if content is not None else _npz_content(message)
    _files.save_npz(path, {"__msg__": np.array(tree), **arrays})


def _content_digest(content: _NpzContent) -> str:
    """A SHA-1 over a message's saved content: its JSON tree, then every array's key, dtype, shape and bytes."""
    tree, arrays = content
    digest = hashlib.sha1(tree.encode("utf-8"))
    for key, array in arrays.items():
        # WHY dtype and shape too: equal bytes as float32 vs float64, or (N, 2) vs (2, N), are different references.
        digest.update(f"\0{key}\0{array.dtype.str}\0{array.shape}\0".encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


class _Contents:
    """Each message's saved content (``_npz_content``) and its C6 digest, taken once per write.

    WHY once (NAVIGATION.md D1): a run's digest, its reference's file name and its series' ``.npz`` all need the same
    content, and the reference every run of a target shares would otherwise be hashed once per run.
    """

    def __init__(self) -> None:
        # id(message) -> (the message, its content, its digest); holding the message keeps its id from being reused.
        self._by_object: dict[int, tuple[Any, _NpzContent, str]] = {}

    def of(self, message: Any) -> tuple[_NpzContent, str]:
        known = self._by_object.get(id(message))
        if known is None or known[0] is not message:
            content = _npz_content(message)
            known = self._by_object[id(message)] = (message, content, _content_digest(content))
        return known[1], known[2]


# A run folder is output/runs/<slug>, so this is output/references as its manifest names it.
_REFERENCES_FROM_RUN = "../../references"


def _reference_names(files: Mapping[str, str]) -> set[str]:
    """The ``references/*.npz`` a manifest's ``files`` names (a manifest from before 2026-11-20 names none)."""
    prefix = f"{_REFERENCES_FROM_RUN}/"
    return {relative[len(prefix) :] for relative in files.values() if relative.startswith(prefix)}


class _References:
    """``references/<digest>.npz``: each distinct reference written once (NAVIGATION.md C6).

    WHY shared: the UR5e site copied ``reference.npz`` into all 4932 run folders (0.81 GB) for only 974 distinct
    references. Named by content, so equal references in new objects, another run order or another site share a name.
    """

    def __init__(self, directory: Path, contents: _Contents, rewrite: bool) -> None:
        self.directory = directory
        self.contents = contents
        self.rewrite = rewrite
        self._written: set[str] = set()

    def save(self, reference: JointTrajectory) -> str:
        """The manifest's ``files.reference`` for ``reference``, writing its file unless it is already there.

        WHY an existing file is kept (``rewrite`` False, i.e. ``reuse=True``): its name is its content, and D2 writes it
        whole or not at all, so it already holds this reference; rewriting it would also give a hard-linked copy of the
        site a new inode for nothing. ``reuse=False`` rewrites it once per write, so a file a write from before D2
        truncated is never trusted past one.
        """
        content, digest = self.contents.of(reference)
        name = f"{digest}.npz"
        if name not in self._written:
            path = self.directory / name
            if self.rewrite or not path.is_file():
                self.directory.mkdir(parents=True, exist_ok=True)
                _save_npz(reference, path, content)
            self._written.add(name)
        return f"{_REFERENCES_FROM_RUN}/{name}"

    def prune(self, runs_dir: Path, known: Mapping[str, Mapping[str, str]]) -> None:
        """Delete every ``references/*.npz`` that no ``runs/*/manifest.json`` on disk names, an earlier write's too.

        ``known`` is the ``files`` of each manifest this write already holds, by run folder name; every other manifest is
        read once here. WHY every manifest on disk, not only this write's: a run folder an earlier write left still
        builds, so the reference it names must outlive this write.
        """
        if not self.directory.is_dir():
            return
        named: set[str] = set()
        for files in known.values():
            named |= _reference_names(files)
        for manifest_path in runs_dir.glob("*/manifest.json"):
            if manifest_path.parent.name in known:
                continue
            try:
                named |= _reference_names(json.loads(manifest_path.read_text("utf-8"))["files"])
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue  # a manifest that does not parse names nothing a drill-down could build from
        for path in self.directory.glob("*.npz"):
            if path.name not in named:
                path.unlink()


# ── incremental writes: digests and reuse (NAVIGATION.md Part D) ─────────────


def _code_digest(functions: Sequence[Callable[..., Any] | None]) -> str:
    """A SHA-1 over the code that decides a run's files and analysis: every file of this package (``.py`` and
    ``assets/``), every ``.py`` of robot_msgs, and the source file defining each of ``functions`` (poses, robot).

    WHY files, not ``__version__``: the version does not move on a commit, and a cache that outlives a code change serves
    stale numbers. Read on every write, since a module edited on disk is not re-imported. Data such a function loads (a
    URDF, a MuJoCo model) is not covered: pass ``reuse=False`` after changing it.
    """
    import robot_msgs

    package = Path(__file__).parent
    robot_package = Path(robot_msgs.__file__).parent
    sources = [
        (f"traj_compare/{path.relative_to(package).as_posix()}", path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
        and (path.suffix == ".py" or path.relative_to(package).parts[0] == "assets")
    ]  # fmt: skip
    sources += [
        (f"robot_msgs/{path.relative_to(robot_package).as_posix()}", path) for path in sorted(robot_package.rglob("*.py"))
    ]
    for function in functions:
        if function is None:
            continue
        try:
            source = inspect.getsourcefile(function)
        except TypeError:  # a builtin or a C extension: no source file to read
            source = None
        source = source or getattr(sys.modules.get(getattr(function, "__module__", "")), "__file__", None)
        if source:
            sources.append((f"function/{getattr(function, '__qualname__', function)}", Path(source)))
    digest = hashlib.sha1()
    for label, path in sources:
        data = path.read_bytes()
        digest.update(f"\0{label}\0{len(data)}\0".encode())
        digest.update(data)
    return digest.hexdigest()


def _run_digest(run: Run, slug: str, target: _Target, contents: _Contents, shared: str) -> str:
    """The SHA-1 hex string of everything that decides one run's files and analysis (NAVIGATION.md D1): ``shared`` (the
    write's code and per-run options), the run (name, title, tags, series, pairs, offsets, media, torques), the C6
    digest of its reference and of every measured series, and its place in this write (slug, its target's key, slug
    and title). Dict orders count: a tag's order is a column's order in rows.parquet."""
    media = []
    for key, source in run.media.items():
        source = Path(source)
        try:
            status = source.stat()
        except OSError as error:
            raise FileNotFoundError(f"run {run.name!r}: media {key!r} is not a file: {source}") from error
        # WHY its size and mtime, not its bytes: hashing every clip on every write costs about what copying it does. Its
        # suffix too, since it names the copy (media/<key><suffix>).
        media.append([str(key), source.suffix.lower(), status.st_size, status.st_mtime_ns])
    described = {
        "name": run.name,
        "title": run.title,
        "tags": [[str(key), _tag_value(value)] for key, value in run.tags.items()],
        "series": list(run.measured),
        "pairs": run.resolved_pairs(),
        "time_offset_s": [[str(key), float(value)] for key, value in run.time_offset_s.items()],
        "media_start_s": [[str(key), float(value)] for key, value in run.media_start_s.items()],
        "media": media,
        "slug": slug,
        "target": [target.key, target.slug, target.title],
    }
    digest = hashlib.sha1(shared.encode())
    digest.update(json.dumps(described).encode())
    for name, message in run.series().items():
        digest.update(f"\0{name}\0{contents.of(message)[1]}".encode())
    for series, parts in run.torques.items():
        for key, values in parts.items():
            digest.update(f"\0{series}\0{key}\0{values.dtype.str}\0{values.shape}\0".encode())
            digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def _reusable_run(folder: Path, digest: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(manifest, analysis) of a run folder D1 reuses: both parse and hold ``digest``, and every file the manifest names
    (series, reference, torques, media) exists. None when any of that fails: the folder is then rewritten."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        if manifest.get("digest") != digest:
            return None
        analysis = json.loads((folder / "analysis.json").read_text("utf-8"))
        if analysis.get("digest") != digest or not {"entries", "rows"} <= set(analysis):
            return None
        named = [*manifest["files"].values(), *manifest["media"].values()]
        named += [_torque_file(name) for name in manifest["torques"]]
        if not all((folder / relative).is_file() for relative in named):
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return manifest, analysis


def _target_key(
    target: _Target, digests: Mapping[str, str], config_tag: str | None, labels: Mapping[str, str], display_hz: float,
    target_budget: int,
) -> str:
    """The SHA-1 hex string D1b reuses a target by: its runs' digests in order, its key, slug and title, and the config
    tag, labels, ``display_hz`` and ``target_budget``. Also ``named_by``, which the target's entry carries."""
    described = {
        "runs": [digests[run.name] for run in target.runs],
        "target": [target.key, target.slug, target.title, target.named_by],
        "config_tag": config_tag,
        "labels": [[series, alias] for series, alias in labels.items()],
        "display_hz": float(display_hz),
        "target_budget": int(target_budget),
    }
    return hashlib.sha1(json.dumps(described).encode()).hexdigest()


def _reusable_target(targets_dir: Path, slug: str, key: str) -> dict[str, Any] | None:
    """A target's ``.cache.json`` when D1b reuses it: it parses, holds ``key``, and its ``<slug>.js`` exists."""
    try:
        cache = json.loads((targets_dir / f"{slug}.cache.json").read_text("utf-8"))
        if cache.get("key") != key or not isinstance(cache.get("target"), dict):
            return None
        if not isinstance(cache.get("lines"), list):
            return None
    except (OSError, ValueError, AttributeError):
        return None
    return cache if (targets_dir / f"{slug}.js").is_file() else None


def _write_run_files(
    run: Run, folder: Path, slug: str, options: _Analysis, specs: Mapping[str, str | None], import_roots: list[str],
    primary: Mapping[str, str], visible_pairs: Sequence[tuple[str, str]], target: _Target | None = None,
    *, references: _References, digest: str, analysis: Mapping[str, Any],
) -> dict[str, Any]:
    """Rewrite one run's folder (NAVIGATION.md D1) and return its manifest: the series and torque ``.npz``, the media
    copies, ``analysis.json`` (``analysis``'s entries and rows under ``digest``), then ``manifest.json``.

    WHY the manifest is deleted first and written last: a write stopped midway then leaves no manifest naming
    half-written data, so the next write rewrites this folder instead of reusing it.
    """
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").unlink(missing_ok=True)
    # WHY: a drill-down cached by an earlier write describes the old data; lazy mode would serve it.
    (folder / "report.html").unlink(missing_ok=True)
    shutil.rmtree(folder / "rerun", ignore_errors=True)
    # WHY: a write before 2026-11-20 copied the reference into every run folder; this manifest names references/.
    (folder / "reference.npz").unlink(missing_ok=True)
    files = {REFERENCE: references.save(run.reference)}
    for name, trajectory in run.measured.items():
        files[name] = f"{_safe_name(name)}.npz"
        _save_npz(trajectory, folder / files[name], references.contents.of(trajectory)[0])
    # The torque breakdown beside its series (CONTRACT.md addendum): <series>.torques.npz holds only the keys given, so
    # the drill-down derives the third exactly as the run view does. WHY unlink first: a breakdown an earlier write
    # left behind would otherwise outlive the run that no longer carries it.
    for stale in folder.glob("*.torques.npz"):
        stale.unlink()
    for name, parts in run.torques.items():
        arrays = {key: np.asarray(values, dtype=float) for key, values in parts.items()}
        _files.save_npz(folder / _torque_file(name), arrays)
    media: dict[str, str] = {}
    for key, source in run.media.items():
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"run {run.name!r}: media {key!r} is not a file: {source}")
        relative = f"media/{_safe_name(key)}{source.suffix.lower()}"
        (folder / "media").mkdir(exist_ok=True)
        _files.copy_file(source, folder / relative)
        media[key] = relative
    manifest = {
        "name": run.name,
        "title": run.title or run.name,
        "slug": slug,
        "tags": {key: _tag_value(value) for key, value in run.tags.items()},
        "series": list(run.measured),
        "files": files,
        "torques": {name: list(parts) for name, parts in run.torques.items()},
        "pairs": [list(pair) for pair in run.resolved_pairs()],
        "default_pairs": [list(pair) for pair in run.resolved_pairs() if pair in set(visible_pairs)],
        "time_offset_s": {key: float(value) for key, value in run.time_offset_s.items()},
        "labels": {series: alias for alias, series in primary.items()},
        "media": media,
        "media_start_s": {key: float(value) for key, value in run.media_start_s.items()},
        "poses": specs["poses"],
        "robot": specs["robot"],
        "import_roots": import_roots,
        "tolerances": None if options.tolerances is None else to_dict(options.tolerances),
        # the run report's breadcrumb back to index.html#/target/<slug> (NAVIGATION.md Part A)
        "target": None if target is None else {"key": target.key, "slug": target.slug, "title": target.title},
        # how the run view names each channel (traj_compare.Signal), so a drill-down rebuilt later still has them (C1)
        "signals": {name: signal.to_payload() for name, signal in getattr(options, "signals", {}).items()},
        # what decided this folder (NAVIGATION.md D1): a later write whose digest for the run is the same reuses it
        "digest": digest,
    }
    _files.write_text(folder / "analysis.json", json.dumps({"digest": digest, **analysis}, separators=(",", ":")))
    _files.write_text(folder / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


_ROW_FILES = ("json", "parquet")


def _row_files(rows: Sequence[str] | None) -> frozenset[str]:
    """Which row files this write produces (NAVIGATION.md C2); raises before any file is written.

    WHY a choice: the UR5e site's 460 MB ``rows.json`` was never read once ``rows.parquet`` existed.
    """
    if rows is None:  # rows.json always, rows.parquet when pyarrow (the optional `export` extra) imports
        try:
            import pyarrow.parquet  # noqa: F401
        except ModuleNotFoundError:
            return frozenset({"json"})
        return frozenset(_ROW_FILES)
    if isinstance(rows, str):  # "json" would otherwise read as the names "j", "s", "o", "n"
        raise ValueError(f"rows is a sequence of row file names from {_ROW_FILES}, e.g. ('json',), not {rows!r}")
    chosen = list(dict.fromkeys(rows))
    unknown = [name for name in chosen if name not in _ROW_FILES]
    if unknown:
        raise ValueError(f"rows names unknown row files {unknown}; choose from {_ROW_FILES}")
    if "parquet" in chosen:
        try:
            import pyarrow  # noqa: F401
            import pyarrow.parquet  # noqa: F401
        except ModuleNotFoundError as error:
            raise ModuleNotFoundError(
                "rows.parquet needs pyarrow (traj-compare's `export` extra); install it or leave 'parquet' out of rows",
                name=error.name,
            ) from error
    return frozenset(chosen)


# What varies from one tidy row of a run to the next (_analyze_run: {run, pair, metric, stat, value, unit, **tags}); every other
# column holds one value for all of a run's rows, so _RowSink keeps it once per run.
_PER_ROW = frozenset({"pair", "metric", "stat", "value", "unit"})
_INTERNED = ("pair", "metric", "stat", "unit")
# WHY 1 Mi rows: pyarrow's default max row group length, the split pq.write_table makes on its own, so writing one group at a
# time leaves rows.parquet's bytes as they were (tests/test_rows_stream.py pins two groups for 1.1 M rows).
_ROW_GROUP = 1024 * 1024
_EXACT_INT = 2**53  # an int a float64 holds exactly, so the sink can keep it in its float column and give it back
# a row's value, as _RowSink stores it: its kind codes
_NONE, _FLOAT, _INT, _BOOL, _OTHER, _ABSENT = range(6)


def _value_key(value: Any) -> Any:
    """A dict key for ``value`` that keeps apart what ``==`` merges (1, 1.0 and True; 0.0 and -0.0), so one code never
    stands for two values pyarrow or json writes differently."""
    kind = type(value)
    if kind is str:
        return value
    if kind is float:
        return (float, struct.pack("<d", value))
    if kind is list or kind is tuple:
        return (kind, tuple(_value_key(item) for item in value))
    if kind is dict:
        return (dict, tuple((key, _value_key(item)) for key, item in value.items()))
    try:
        hash(value)
    except TypeError:  # unknown and unhashable: a code of its own (the sink keeps it, so its id is not reused)
        return (kind, id(value))
    return (kind, value)


class _Interned:
    """One per-row column: its distinct values by first appearance and one int32 code per row (-1: the row has no such key)."""

    __slots__ = ("absent", "codes", "index", "values")

    def __init__(self) -> None:
        self.codes = array("i")
        self.index: dict[Any, int] = {}
        self.values: list[Any] = []
        self.absent = False

    def add(self, value: Any) -> None:
        key = _value_key(value)
        code = self.index.get(key)
        if code is None:
            code = self.index[key] = len(self.values)
            self.values.append(value)
        self.codes.append(code)

    def skip(self) -> None:
        self.codes.append(-1)
        self.absent = True


def _shared_getter(keys: Sequence[str]) -> Callable[[Mapping[str, Any]], tuple[Any, ...]]:
    if not keys:
        return lambda row: ()
    if len(keys) == 1:
        only = keys[0]
        return lambda row: (row[only],)
    return operator.itemgetter(*keys)


class _RowSink:
    """The tidy rows of a write (rows.json, rows.parquet), about 29 bytes a row instead of one dict each.

    WHY (arm_motion_bench, 2026-11-21): its pendulum site holds 7,782 traces in 4,804 runs; holding all 2.24 M rows as dicts
    (2.9 KB each once a reused run's analysis.json is parsed) until the files were written peaked its rebuild at 10.24 GiB
    under an 11 GiB cap. Here a run's rows are one *segment*: the values every row of it shares (run, tags), kept once,
    and per row int32 codes into the distinct values of ``pair``, ``metric``, ``stat`` and ``unit`` plus its ``value`` in a
    float64 column. A run's parsed dicts die with its loop iteration. Both files are written from here with the bytes the
    dict writer wrote: rows.json one run at a time, rows.parquet one 1 Mi-row group at a time.

    A segment is consecutive rows with the same keys in the same order and equal shared values (``==``): every row of a run
    spreads one tags dict, so a run is one segment, and a run whose rows differ (a column that varies inside it) is split,
    never merged. Each ``add_run`` starts a segment.
    """

    def __init__(self) -> None:
        self.count = 0
        self.columns: dict[str, None] = {}  # every key by first appearance: dict.fromkeys(key for row in rows for key in row)
        self.segments: list[tuple[tuple[str, ...], tuple[Any, ...]]] = []  # (its rows' keys in order, their shared values)
        self.segment_of = array("i")
        self.interned = {column: _Interned() for column in _INTERNED}
        self.value = array("d")  # float, int (|v| <= 2**53) and bool values; 0.0 where the kind says otherwise
        self.kind = array("b")
        self.other: dict[int, Any] = {}  # row -> a value of no kind above (an int beyond 2**53, a str, ...)
        self.first: list[int | None] = [None] * 6  # kind -> the first row holding it
        self.int_range: list[int] = []  # [smallest, largest] int value
        self._layouts: dict[tuple[str, ...], tuple[Callable[[Mapping[str, Any]], tuple[Any, ...]], dict[str, int]]] = {}

    def __len__(self) -> int:
        return self.count

    def _layout(self, keys: tuple[str, ...]):
        found = self._layouts.get(keys)
        if found is None:
            shared = [key for key in keys if key not in _PER_ROW]
            found = self._layouts[keys] = (_shared_getter(shared), {key: index for index, key in enumerate(shared)})
            for key in keys:
                self.columns.setdefault(key, None)
        return found

    def add_run(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Take one run's tidy rows, in order; the caller can drop them afterwards."""
        segment_keys: tuple[str, ...] | None = None
        segment_values: tuple[Any, ...] = ()
        getter = None
        interned = [(column, self.interned[column]) for column in _INTERNED]
        for row in rows:
            keys = tuple(row)
            if keys != segment_keys:
                getter = self._layout(keys)[0]
                shared = getter(row)
                self.segments.append((keys, shared))
                segment_keys, segment_values = keys, shared
            else:
                shared = getter(row)
                if shared != segment_values:
                    self.segments.append((keys, shared))
                    segment_values = shared
            self.segment_of.append(len(self.segments) - 1)
            for column, codes in interned:
                if column in row:
                    codes.add(row[column])
                else:
                    codes.skip()
            self._add_value(row)

    def _add_value(self, row: Mapping[str, Any]) -> None:
        number = 0.0
        if "value" not in row:
            kind = _ABSENT
        else:
            value = row["value"]
            kind_of = type(value)
            if kind_of is float:
                kind, number = _FLOAT, value
            elif value is None:
                kind = _NONE
            elif kind_of is bool:
                kind, number = _BOOL, float(value)
            elif kind_of is int and -_EXACT_INT <= value <= _EXACT_INT:
                kind, number = _INT, float(value)
                if not self.int_range:
                    self.int_range = [value, value]
                elif value < self.int_range[0]:
                    self.int_range[0] = value
                elif value > self.int_range[1]:
                    self.int_range[1] = value
            else:
                kind = _OTHER
                self.other[self.count] = value
        if self.first[kind] is None:
            self.first[kind] = self.count
        self.value.append(number)
        self.kind.append(kind)
        self.count += 1

    def _value_at(self, index: int) -> Any:
        kind = self.kind[index]
        if kind == _FLOAT:
            return self.value[index]
        if kind == _INT:
            return int(self.value[index])
        if kind == _BOOL:
            return bool(self.value[index])
        if kind == _OTHER:
            return self.other[index]
        return None

    def _segment_rows(self) -> Iterator[list[dict[str, Any]]]:
        """Each segment's rows rebuilt as the dicts that were added: same keys, same order, same values."""
        segment_of = np.frombuffer(self.segment_of, dtype=np.int32)
        codes = {column: self.interned[column].codes for column in _INTERNED}
        values = {column: self.interned[column].values for column in _INTERNED}
        bounds = np.flatnonzero(np.diff(segment_of)) + 1
        starts = [0, *bounds.tolist()]
        stops = [*bounds.tolist(), self.count]
        for start, stop in zip(starts, stops):
            if start == stop:
                continue
            keys, shared = self.segments[segment_of[start]]
            positions = self._layout(keys)[1]
            rows = []
            for index in range(start, stop):
                row = {}
                for key in keys:
                    if key == "value":
                        row[key] = self._value_at(index)
                    elif key in _PER_ROW:
                        row[key] = values[key][codes[key][index]]
                    else:
                        row[key] = shared[positions[key]]
                rows.append(row)
            yield rows

    def write_json(self, handle) -> None:
        """``json.dumps(rows, separators=(",", ":"))``, written one segment at a time."""
        handle.write("[")
        first = True
        for rows in self._segment_rows():
            text = json.dumps(rows, separators=(",", ":"))[1:-1]
            handle.write(text if first else "," + text)
            first = False
        handle.write("]")

    # -- rows.parquet: each column's type is the one pa.array gives the whole column ----------------------------------------
    #
    # WHY witnesses, not the column: pa.array infers a type from the values up to the first bool, float or str (ints and None
    # do not stop it), then converts every value to it, and a value it cannot convert sends the column to text. Distinct
    # values in first-appearance order go through both steps exactly as the whole column does.

    def _witnesses(self, column: str) -> list[Any]:
        if column in self.interned:
            interned = self.interned[column]
            return [*interned.values, *([None] if interned.absent else [])]
        if column == "value":
            firsts = sorted((row, kind) for kind, row in enumerate(self.first) if row is not None and kind != _OTHER)
            witnesses = sorted([*((row, self._value_at(row)) for row, _ in firsts), *self.other.items()], key=lambda item: item[0])
            return [value for _, value in witnesses] + list(self.int_range)
        return self._per_segment(column)

    def _per_segment(self, column: str) -> list[Any]:
        values = []
        for keys, shared in self.segments:
            position = self._layout(keys)[1].get(column)
            values.append(None if position is None else shared[position])
        return values

    def _plan(self, pa, column: str):
        """(arrow type, as_text): as_text where pa.array refuses the column and the dict writer kept it as text."""
        witnesses = self._witnesses(column)
        try:
            return pa.array(witnesses).type, False
        except (pa.ArrowInvalid, pa.ArrowTypeError):  # a tag whose type differs between runs: keep it as text
            return pa.array(_as_text(witnesses)).type, True

    def write_parquet(self, handle) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if not self.count:
            pq.write_table(pa.table({}), handle)
            return
        plans = {column: self._plan(pa, column) for column in self.columns}
        schema = pa.schema([(column, plans[column][0]) for column in self.columns])
        dictionaries = {}  # a per-row or per-segment column: its distinct values as an arrow array, taken from per group
        for column, (kind, as_text) in plans.items():
            if column == "value":
                continue
            values = self.interned[column].values if column in self.interned else self._per_segment(column)
            dictionaries[column] = pa.array(_as_text(values) if as_text else values, type=kind)
        segment_of = np.frombuffer(self.segment_of, dtype=np.int32)
        kinds = np.frombuffer(self.kind, dtype=np.int8)
        numbers = np.frombuffer(self.value, dtype=np.float64)
        with pq.ParquetWriter(handle, schema) as writer:
            for start in range(0, self.count, _ROW_GROUP):
                stop = min(start + _ROW_GROUP, self.count)
                arrays = []
                for column in self.columns:
                    kind, as_text = plans[column]
                    if column == "value":
                        arrays.append(self._value_array(pa, kind, as_text, kinds[start:stop], numbers[start:stop], start, stop))
                    elif column in self.interned:
                        codes = np.frombuffer(self.interned[column].codes, dtype=np.int32)[start:stop]
                        arrays.append(dictionaries[column].take(pa.array(codes, mask=codes < 0)))
                    else:
                        arrays.append(dictionaries[column].take(pa.array(segment_of[start:stop])))
                writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
                del arrays

    def _value_array(self, pa, kind, as_text: bool, kinds: np.ndarray, numbers: np.ndarray, start: int, stop: int):
        if not as_text and pa.types.is_float64(kind) and not (kinds == _OTHER).any():
            # WHY the float column as is: pa.array converts an int and a bool to the same double (True -> 1.0)
            return pa.array(numbers, type=kind, mask=(kinds == _NONE) | (kinds == _ABSENT))
        values = [self._value_at(index) for index in range(start, stop)]
        return pa.array(_as_text(values) if as_text else values, type=kind)


def _as_text(values: Sequence[Any]) -> list[str | None]:
    return [None if value is None else str(value) for value in values]


def _write_rows(output_dir: Path, rows: _RowSink, files: frozenset[str]) -> None:
    """Write the row files ``files`` names (from ``_row_files``) and delete the other one, so no stale rows outlive
    their data."""
    if "json" in files:
        with _files.replacing(output_dir / "rows.json") as temporary, open(temporary, "x", encoding="utf-8") as handle:
            rows.write_json(handle)
    else:
        (output_dir / "rows.json").unlink(missing_ok=True)
    if "parquet" not in files:
        (output_dir / "rows.parquet").unlink(missing_ok=True)
        return
    with _files.replacing(output_dir / "rows.parquet") as temporary, open(temporary, "xb") as handle:
        rows.write_parquet(handle)


_TARGETS_DIR = "targets"
# A row's fields the page derives from its run (D.runs) and pair (pair_files), never stored per row (NAVIGATION.md C5).
_ROW_REPEATS = frozenset({"slug", "tags", "report", "rrd"})
_RRD_STAND_IN = "traj-compare-rrd-stand-in"


def _asset(name: str) -> str:
    return importlib.resources.files("traj_compare").joinpath("assets", name).read_text("utf-8")


def write_dataset_report(
    runs: Sequence[Run],
    output_dir: Path | str,
    *,
    title: str,
    group_by: Sequence[str] = (),
    tolerances: Tolerances | None = None,
    poses: str | None = None,
    robot: str | None = None,
    summary: ReportPage | None = None,
    primary: Mapping[str, str] | None = None,
    drill_down: str = "lazy",
    data_ui: bool = False,
    rows: Sequence[str] | None = None,
    target_by: str | None = None,
    config_by: str | None = None,
    display_hz: float = 50.0,
    signals: Mapping[str, Signal] | None = None,
    target_budget: int = 2_000_000,
    reuse: bool = True,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    """Write ``output_dir/index.html`` (many runs at a glance), ``rows.json``/``rows.parquet`` and ``runs/<slug>/``.

    - ``target_by``: the tag naming a run's target trajectory (the Dataset level's cards, ``#/target/<slug>``). Default:
      ``"target"`` when any run has it, else the first ``group_by`` tag, else a content hash of the reference, titled by
      its first run. An explicit ``target_by`` value holding two different references raises ``ValueError``.
    - ``config_by``: the tag naming a line's robot config (its colour on every level). Default: the first ``group_by``
      tag that does not name the target, else the series name. A line is one measured series of one run, its kind
      ``real`` when the series name starts with "real", else ``sim``; a run's ``"date"`` tag orders the control chart.
    - ``display_hz``: the rate of the series the Dataset and Target levels draw (reference samples picked, never
      averaged); rows.json and the drill-down keep every sample.
    - ``target_budget``: the most drawn values (lines x joints x samples x drawn series) one ``targets/<slug>.js`` holds;
      over it, that target's samples are picked further apart until its file fits. Every chart states the rate it draws.
    - ``group_by``: tag names; runs sharing their values are one group for the ISO 9283 cards.
    - ``tolerances``: a ``robot_msgs.compare.Tolerances``; every run x pair gets ``check``'s verdict.
    - ``poses`` / ``robot``: ``"module:function"`` import specs, stored in each manifest so the drill-down
      can be rebuilt later in another process. ``poses(JointTrajectory) -> PoseTrajectory`` adds the TCP
      metrics and the run view's cartesian sections; ``robot() -> RobotDisplay`` gives its 3D view a robot.
    - ``summary``: a ``ReportPage`` drawn at the top (the domain's at-a-glance answer).
    - ``primary``: alias -> series (see ``_visible``): the default view shows 3 pairs, not 6.
    - ``drill_down``: ``"lazy"`` builds ``runs/<slug>/report.html`` on first request through
      ``traj_compare.serve`` (or ``python -m traj_compare.dataset drill``); ``"eager"`` builds them all now.
      WHY lazy is the default: a run's drill-down writes one .rrd per pair, so 387 runs x 3 pairs is
      about 2 GB up front for pages almost nobody opens.
    - ``data_ui``: also write ``output_dir/data-ui/`` (``traj_compare.data_ui.write_tables``): data-ui's trajectory-contract
      tables over the same runs (the TCP from ``poses``, the links from ``robot``) and a ``views.base`` dashboard whose run
      rows link back to the drill-down. Open it in data-ui; see the README's "data-ui" section.
    - ``rows``: which row files to write, a subset of ``("json", "parquet")``. ``None`` is ``rows.json`` plus
      ``rows.parquet`` when pyarrow imports, ``()`` neither; one not chosen is deleted. An unknown name (``ValueError``)
      or ``"parquet"`` without pyarrow (``ModuleNotFoundError``) raises before any file is written.
    - ``signals``: channel name -> ``traj_compare.Signal`` (title, unit, column labels, ``per_joint``) for the series'
      ``JointTrajectory.channels``, stored in every manifest; the drill-down draws ``channels["current"]`` ((N, J), A)
      as motor current and every other channel, described or not, in its "What else was measured?" tab.
    - ``reuse``: reuse what an earlier write left in ``output_dir`` where nothing that decides it changed (NAVIGATION.md
      Part D). A run whose folder holds its digest (its data, its place in the write, the per-run options and the code)
      keeps its folder untouched, its drill-down included; a target whose ``.cache.json`` holds its key keeps its files.
      The output equals a ``reuse=False`` write, which rewrites every run and target. Run folders not in this write stay.
    - ``progress``: ``progress(phase, done, total)`` for the phases ``"runs"``, ``"reused"`` (once: runs reused of all),
      ``"targets"``, ``"index"`` and, with ``drill_down="eager"``, ``"drill"``. An exception it raises stops the write;
      every file is written under a temporary name and renamed into place, so each is left whole, old or new.
    """

    runs = list(runs)
    primary = dict(primary or {})
    group_by = tuple(group_by)
    row_files = _row_files(rows)  # NAVIGATION.md C2: refused before anything is written, the output directory included
    if drill_down not in _DRILL_DOWNS:
        raise ValueError(f"drill_down is one of {_DRILL_DOWNS}, got {drill_down!r}")
    if display_hz <= 0:
        raise ValueError(f"display_hz must be positive, got {display_hz}")
    if isinstance(target_budget, bool) or not isinstance(target_budget, (int, np.integer)) or target_budget <= 0:
        raise ValueError(f"target_budget must be a positive whole number of drawn values, got {target_budget!r}")
    _validate(runs, group_by, primary)
    signals = {str(name): signal for name, signal in dict(signals or {}).items()}
    _validate_channels(runs, signals)
    target_tag = _target_tag(runs, group_by, target_by)
    targets = _resolve_targets(runs, target_tag, explicit=target_by is not None)
    target_of = {run.name: target for target in targets for run in target.runs}
    config_tag = _config_tag(runs, group_by, config_by, target_tag)
    slugs = _unique_slugs(runs)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = {"poses": poses, "robot": robot}
    import_roots: list[str] = []
    for spec in (poses, robot):
        if spec is None:
            continue
        _split_spec(spec)
        root = _spec_import_root(spec)
        if root is not None and root not in import_roots:
            import_roots.append(root)
    options = _Analysis(tolerances, _import_spec(poses, import_roots) if poses else None)
    options.signals = signals  # the channel descriptions travel with the write's other options into every manifest
    robot_function = _import_spec(robot, import_roots) if robot else None  # fail now, not on the first drill-down

    series_order = list(dict.fromkeys(name for run in runs for name in run.measured))
    pair_order = list(dict.fromkeys(pair for run in runs for pair in run.resolved_pairs()))
    default_view = [pair for pair in pair_order if all(_visible(name, primary) for name in pair)]

    def report(phase: str, done: int, total: int) -> None:
        if progress is not None:
            progress(phase, done, total)

    # NAVIGATION.md D1: what every run's digest shares, taken once per write
    per_run_options = {
        "poses": poses,
        "robot": robot,
        "import_roots": import_roots,
        "tolerances": None if tolerances is None else to_dict(tolerances),
        "signals": {name: signal.to_payload() for name, signal in signals.items()},
        "primary": primary,
    }
    shared = _code_digest([options.poses, robot_function]) + json.dumps(per_run_options)
    contents = _Contents()
    references = _References(output_dir / "references", contents, rewrite=not reuse)
    runs_dir = output_dir / "runs"
    # WHY a sink, not a list of the rows: see _RowSink (a reused run's rows, parsed back, held to the end: 10.24 GiB)
    tidy_rows = _RowSink()  # WHY not `rows`: that name is the row-file choice (C2)
    entries: list[dict[str, Any]] = []
    pose_cache = _Poses(runs, options)
    joint_errors: dict[tuple[str, str], Any] = {}
    digests: dict[str, str] = {}
    run_files: dict[str, Mapping[str, str]] = {}  # run folder name -> its manifest's files, for references.prune
    reused: set[str] = set()
    report("runs", 0, len(runs))
    for done, run in enumerate(runs, start=1):
        slug = slugs[run.name]
        folder = runs_dir / slug
        digest = digests[run.name] = _run_digest(run, slug, target_of[run.name], contents, shared)
        kept = _reusable_run(folder, digest) if reuse else None
        if kept is not None:
            manifest, analysis = kept
            reused.add(run.name)
            for entry in analysis["entries"]:
                if "error" in entry:  # as the write that made it warned
                    warnings.warn(_pair_warning(run.name, *entry["pair"], entry["error"]), stacklevel=2)
        else:
            analysis = _analyze_run(run, slug, options, pose_cache[run.name], joint_errors)
            manifest = _write_run_files(
                run, folder, slug, options, specs, import_roots, primary, default_view, target_of[run.name],
                references=references, digest=digest, analysis=analysis,
            )
        run_files[slug] = manifest["files"]
        entries.extend(analysis["entries"])
        tidy_rows.add_run(analysis["rows"])
        report("runs", done, len(runs))
    report("reused", len(reused), len(runs))
    _write_rows(output_dir, tidy_rows, row_files)
    references.prune(runs_dir, run_files)

    aggregates = _group_aggregates(runs, group_by, options, pose_cache)
    joint_names = list(dict.fromkeys(name for entry in entries for name in entry.get("joints", {})))
    labels = {series: alias for alias, series in primary.items()}
    targets_dir = output_dir / _TARGETS_DIR
    targets_dir.mkdir(exist_ok=True)
    analysed = {(entry["run"], entry["pair"][1]): entry for entry in entries if entry["pair"][0] == REFERENCE}
    order = {run.name: index for index, run in enumerate(runs)}
    target_rows: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    kept_files: set[str] = set()
    report("targets", 0, len(targets))
    for done, target in enumerate(targets, start=1):
        key = _target_key(target, digests, config_tag, labels, display_hz, target_budget)
        kept = _reusable_target(targets_dir, target.slug, key) if reuse else None
        if kept is not None:  # NAVIGATION.md D1b: neither file is written, nothing of it recomputed
            target_row, own_lines = kept["target"], kept["lines"]
            for line in own_lines:
                line["order"] = order[line["run"]]
        else:
            target_row, own_lines, data = _target_level(
                target, order, slugs, config_tag, joint_errors, analysed, options, pose_cache, display_hz, labels,
                target_budget,
            )  # fmt: skip
            # WHY clean before the cache and the site-wide pass alike: a reused target's lines are read back from JSON,
            # so a fresh one's must be the same values, or fb_share_median could differ between the two.
            target_row, own_lines = _clean(target_row), _clean(own_lines)
            # WHY the cache is deleted first and written last, on reuse=False too: it vouches for its .js, so a .js
            # this write replaces never sits beside the cache of an older one, even when the write stops in between.
            cache_path = targets_dir / f"{target.slug}.cache.json"
            cache_path.unlink(missing_ok=True)
            # WHY a classic script calling a global, not JSON for fetch(): fetch() of a file:// URL is refused, and
            # index.html must open from file:// (NAVIGATION.md Part A); a <script src> loads from file:// and http
            # alike (C5).
            _files.write_text(
                targets_dir / f"{target.slug}.js",
                f"// traj_compare: the drawn series of target {target.slug}, loaded by ../index.html when it is shown "
                f"(NAVIGATION.md C5)\nwindow.trajCompareTarget({json.dumps(target.slug)}, {data});\n",
            )
            cache = {"key": key, "target": target_row, "lines": own_lines}
            _files.write_text(cache_path, json.dumps(cache, separators=(",", ":")))
        kept_files |= {f"{target.slug}.js", f"{target.slug}.cache.json"}
        target_rows.append(target_row)
        lines.extend(own_lines)
        report("targets", done, len(targets))
    levels = _site_levels(target_rows, lines)
    for stale in [*targets_dir.glob("*.js"), *targets_dir.glob("*.cache.json")]:  # a target this write does not have
        if stale.name not in kept_files:
            stale.unlink()
    folder = output_dir.resolve()
    # The runs table's command, built in the page per row (NAVIGATION.md C5): rerun_command repeated the folder twice per
    # row, 10.9 MB of the UR5e index. The viewer half is rerun_export's own command around a stand-in for the row's .rrd,
    # which the page splices in; WHY that is the row's exact command: the stand-in and every .rrd path below the folder
    # (runs/<slug>/rerun/<pair>.rrd, all [a-z0-9./-]) need no shell quoting, so quoting the whole path quotes only the folder.
    viewer_before, _, viewer_after = rerun_export.viewer_command(folder / _RRD_STAND_IN).partition(_RRD_STAND_IN)
    # WHY a write id on each target file's URL: a page served over http may keep an earlier write's targets/<slug>.js
    # in its cache; a new id per write makes the browser fetch this write's files.
    write_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    payload = {
        "title": title,
        "generated": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "angle_unit": "deg",
        "group_by": list(group_by),
        "drill_down": drill_down,
        "write_id": write_id,
        "serve_command": f"python -m traj_compare.serve {shlex.quote(str(output_dir.resolve()))}",
        "command_template": {
            "drill": f"python -m traj_compare.dataset drill {shlex.quote(str(folder))} ",
            "viewer": [viewer_before, viewer_after],
        },
        "pair_files": [[first, second, _pair_name(first, second)] for first, second in pair_order],
        "labels": {series: alias for alias, series in primary.items()},
        "series": series_order,
        "default_pairs": [list(pair) for pair in default_view],
        "joint_names": joint_names,
        "tag_keys": list(dict.fromkeys(key for run in runs for key in run.tags)),
        "has_tcp": poses is not None,
        "has_tolerances": tolerances is not None,
        "runs": [
            {
                "name": run.name,
                "slug": slugs[run.name],
                "tags": {key: _tag_value(value) for key, value in run.tags.items()},
                "t_span": [_finite(run.reference.t[0]), _finite(run.reference.t[-1])],
            }
            for run in runs
        ],
        "rows": _clean([{key: value for key, value in entry.items() if key not in _ROW_REPEATS} for entry in entries]),
        "aggregates": _clean(aggregates),
        "summary": summary.to_payload() if summary is not None else None,
        "levels": {
            "target_by": target_tag,
            "config_by": config_tag,
            "date_tag": DATE_TAG if any(DATE_TAG in run.tags for run in runs) else None,
            "display_hz": display_hz,
            **_clean(levels),
        },
    }
    data_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    # The ReportPage renderer lives in plots.js; it is only worth its 75 KB when a summary is given.
    renderer = f"<script>{_asset('plots.js')}</script>" if summary is not None else ""
    document = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>{html.escape(title)}</title>
<style>{_asset("style.css")}</style>
<style>{_asset("uplot.min.css")}</style>
<style>{_asset("dataset.css")}</style>
</head>
<body>
<main class='ds' id='ds-main'></main>
<script type="application/json" id="traj-compare-dataset">{data_json}</script>
{renderer}
<script>{_asset("uplot.iife.min.js")}</script>
<script>{_asset("dataset.js")}</script>
</body>
</html>
"""
    index = output_dir / "index.html"
    report("index", 0, 1)
    _files.write_text(index, document)
    report("index", 1, 1)

    if data_ui:
        from .data_ui import links_from_robot, stage_viewer, write_tables  # lazy: data_ui imports this module

        write_tables(
            runs,
            output_dir / "data-ui",
            poses=options.poses,
            links=links_from_robot(robot_function) if robot_function is not None else None,
        )
        stage_viewer(output_dir, title=title)  # data-ui.html + kit link when a built data-ui is on this machine
    if drill_down == "eager":
        report("drill", 0, len(runs))
        for done, run in enumerate(runs, start=1):
            folder = runs_dir / slugs[run.name]
            # WHY by folder, not build_drill_down's name scan: that reads every manifest once per run
            if run.name not in reused or not (folder / "report.html").is_file():
                build_run_folder(folder)
            report("drill", done, len(runs))
    return index


# ── drill-down ───────────────────────────────────────────────────────────────


def _find_run_folder(output_dir: Path, run_name: str) -> Path:
    for manifest_path in sorted((output_dir / "runs").glob("*/manifest.json")):
        if json.loads(manifest_path.read_text("utf-8"))["name"] == run_name:
            return manifest_path.parent
    raise KeyError(f"no run named {run_name!r} under {output_dir / 'runs'}")


def _rerun_available() -> bool:
    if rerun_export.rr is None:
        warnings.warn(
            "the Rerun SDK is not installed, so the drill-down has no .rrd; install the 'rerun' extra",
            stacklevel=3,
        )
        return False
    return True


def _clip_situations(manifest: Mapping[str, Any], series_names: Sequence[str]) -> list[Situation]:
    """Extra clips (a media key that is no series) as data-less situations that carry only a video.

    WHY situations: the viewer's transport already seeks every situation video together, so a clip
    plays on the run's clock for free; its legend chip reads "extra clip" instead of a data swatch.
    """
    clips = []
    for key, relative in manifest["media"].items():
        if key in series_names or key == REFERENCE:
            continue
        clips.append(
            Situation(
                name=key,
                title=Path(relative).name,
                video=relative,
                video_start_s=manifest["media_start_s"].get(key, 0.0),
                note="extra clip",
            )
        )
    return clips


def _build_run_report(folder: Path) -> Path:
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    poses = _import_spec(manifest["poses"], manifest["import_roots"]) if manifest["poses"] else None
    robot: RobotDisplay | None = _import_spec(manifest["robot"], manifest["import_roots"])() if manifest["robot"] else None
    tolerances = from_dict(manifest["tolerances"], Tolerances) if manifest["tolerances"] else None
    pose_tolerances = tolerances is not None and (
        isinstance(tolerances.path, PoseTolerance) or isinstance(tolerances.goal, PoseTolerance)
    )
    labels: Mapping[str, str] = manifest["labels"]

    def label(name: str) -> str:
        return "Reference" if name == REFERENCE else labels.get(name, name)

    trajectories = {name: load_npz(folder / file) for name, file in manifest["files"].items()}
    torques: dict[str, dict[str, np.ndarray]] = {}
    for name, keys in manifest.get("torques", {}).items():  # .get: manifests written before 2026-11-19 have none
        with np.load(folder / _torque_file(name), allow_pickle=False) as stored:
            torques[name] = {key: stored[key] for key in keys}
    # .get: manifests written before 2026-11-20 describe no channel (they are drawn under their own names)
    signals = {
        str(name): Signal(title=entry.get("title", ""), unit=entry.get("unit", ""), columns=tuple(entry.get("columns", ())),
                          per_joint=bool(entry.get("per_joint", False)))
        for name, entry in (manifest.get("signals") or {}).items()
    }  # fmt: skip
    not_drawn: dict[str, str] = {}  # a channel the run view cannot hold -> why; the page says so (never silently)
    offsets: Mapping[str, float] = manifest["time_offset_s"]
    series_names = list(manifest["series"])
    shown = {tuple(pair) for pair in manifest["default_pairs"]}
    # Tabs open on the default pairs; the hidden ones (earlier twin iterations) follow, marked.
    pairs = sorted((tuple(pair) for pair in manifest["pairs"]), key=lambda pair: pair not in shown)

    def situation(name: str, reference: JointTrajectory, role_origin: float, offset_s: float) -> Situation:
        trajectory = trajectories[name]
        if set(trajectory.joint_names) != set(reference.joint_names):
            raise ValueError(f"{name!r} has joints {trajectory.joint_names}, the reference {reference.joint_names}")
        # The breakdown's columns follow the series' own joint order; reorder them with the series onto the reference's.
        columns = [list(trajectory.joint_names).index(joint) for joint in reference.joint_names]
        breakdown = {key: values[:, columns] for key, values in torques.get(name, {}).items()}
        # NAVIGATION.md C1: channels["current"] is Situation.current, every other channel Situation.channels.
        # WHY reordered like effort: current and a per_joint channel follow the series' own joint order, the view the
        # reference's (select() keeps channels whole); any other channel's columns (x, y, z) are no joints, never moved.
        recorded = {str(key): np.asarray(values) for key, values in trajectory.channels.items()}
        current = recorded.pop("current", None)
        if current is not None and current.ndim == 1 and len(columns) == 1:  # one joint's current, logged flat
            current = current[:, None]
        if current is not None and current.shape != (len(trajectory.t), len(columns)):  # a manifest from before C1
            not_drawn["current"] = f"shape {current.shape}, not (N, {len(columns)})"
            current = None
        channels: dict[str, np.ndarray] = {}
        for key, values in recorded.items():
            if not _drawable(values):
                not_drawn.setdefault(key, f"{values.dtype} of shape {values.shape}")
                continue
            signal = signals.get(key)
            channels[key] = values[:, columns] if signal is not None and signal.per_joint else values
        trajectory = trajectory.select(reference.joint_names)
        return Situation(
            name=name,
            title=label(name),
            t=trajectory.absolute_times - role_origin,
            q=trajectory.positions,
            qd=trajectory.velocities,
            qdd=trajectory.accelerations,
            tau=trajectory.effort,
            current=None if current is None else current[:, columns],
            **breakdown,  # tau_cmd / tau_ff / tau_fb as given; the run view derives the third (its "Feedforward or feedback?" tab)
            poses=None if poses is None else poses(trajectory).matrices(),
            video=manifest["media"].get(name, ""),
            video_start_s=manifest["media_start_s"].get(name, 0.0),
            time_offset_s=offset_s,
            robot=None,
            channels=channels,
        )

    comparisons = []
    for first, second in pairs:
        reference = trajectories[first]
        origin = float(reference.header.stamp)
        offset = float(offsets.get(second, 0.0)) - float(offsets.get(first, 0.0))
        tcp_frame = poses(reference).child_frame_id if poses is not None else ""
        hidden = "" if (first, second) in shown else " (earlier iteration)"
        target, measured = situation(first, reference, origin, 0.0), situation(second, reference, origin, offset)
        skipped = "".join(f" Not drawn: {key} ({why})." for key, why in not_drawn.items())
        comparisons.append(
            Comparison(
                title=f"{label(first)} → {label(second)}",
                name=_pair_name(first, second),
                tab_title=f"{label(first)} → {label(second)}{hidden}",
                joint_names=list(reference.joint_names),
                target=target,
                situations=[measured, *_clip_situations(manifest, series_names)],
                robot=robot,
                tcp_frame=tcp_frame or "TCP",
                tolerances=None if pose_tolerances else tolerances,
                tcp_tolerances=tolerances if pose_tolerances else None,
                estimate_latency=True,
                description=f"Errors are {label(first)} − {label(second)}, the ROS 2 convention.{skipped}",
                signals=signals,
                # a pair whose first element is a measured series (sim → real) is measured against a run, not a target
                reference_kind="target" if first == REFERENCE else "run",
            )
        )
    tags = " · ".join(f"{key}={value}" for key, value in manifest["tags"].items())
    extra: dict[str, Any] = {}
    # WHY guarded: the breadcrumb kwarg lands in report.py from a sibling lane (2026-11-19); until it does, the run report
    # is written exactly as before rather than failing.
    if "breadcrumb" in inspect.signature(write_comparison_report).parameters:
        crumbs = [("Dataset", "../../index.html#/")]
        target = manifest.get("target")
        if target:
            crumbs.append((target["title"], f"../../index.html#/target/{target['slug']}"))
        extra["breadcrumb"] = crumbs
    return write_comparison_report(
        comparisons,
        folder / "report.html",
        title=manifest["title"],
        subtitle=tags,
        provenance={"run": manifest["name"]},
        rerun=_rerun_available(),
        **extra,
    )


def build_drill_down(output_dir: Path | str, run_name: str) -> Path:
    """Build ``runs/<slug>/report.html`` (and its .rrd per pair) from the files alone and return its path.

    Reads the manifest and the npz files, so it needs no in-memory ``Run`` and can run long after
    ``write_dataset_report``, in another process.
    """

    return build_run_folder(_find_run_folder(Path(output_dir), run_name))


def build_run_folder(folder: Path | str) -> Path:
    """Build ``<folder>/report.html`` (and its .rrd per pair) from that run folder's manifest alone and return its path.

    WHY public and folder-only: ``python -m traj_compare.serve`` serves many sites at once and must build a run
    where the request names it, without scanning every manifest of a site to find it.
    """

    return _build_run_report(Path(folder))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m traj_compare.dataset", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    drill = commands.add_parser("drill", help="build one run's drill-down report")
    drill.add_argument("output_dir", type=Path, help="the dataset directory (holds index.html and runs/)")
    drill.add_argument("run_name", help="the run's name, as in rows.json")
    args = parser.parse_args(argv)
    if args.command == "drill":
        print(build_drill_down(args.output_dir, args.run_name))


if __name__ == "__main__":
    main()
