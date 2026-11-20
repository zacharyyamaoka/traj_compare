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

    out/index.html                  the at-a-glance page (self-contained, hash routes, works from file://)
    out/rows.json, rows.parquet     one row per run x pair x metric x stat, SI, every tag its own column
    out/runs/<slug>/manifest.json   what the drill-down needs to rebuild itself
    out/runs/<slug>/<series>.npz    robot_msgs's npz layout per series (``load_npz`` reads them back)
    out/runs/<slug>/<series>.torques.npz   the torque breakdown a series was given (tau_cmd / tau_ff / tau_fb), if any
    out/runs/<slug>/media/<key>.<ext>
    out/runs/<slug>/report.html     the run view, built lazily (or eagerly) from the files above
    out/references/<digest>.npz     each distinct reference once, named by a SHA-1 of its saved content; a manifest's
                                    ``files.reference`` is ``../../references/<digest>.npz`` (no per-run reference.npz),
                                    and a reference no ``runs/*/manifest.json`` names is deleted after the write

Every ``.npz`` is deflated (``np.savez_compressed``, values bit-identical), so ``load_npz`` and ``np.load`` read it
unchanged. A manifest written before 2026-11-20 names ``"reference.npz"`` beside its series and still builds.

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
import re
import shlex
import shutil
import sys
import warnings
from collections.abc import Callable, Mapping, Sequence
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

from . import rerun_export
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
# Config colours, fixed across every level (NAVIGATION.md): sim-only configs grey, the rest violet, green, ... WHY never
# blue or orange: those are the feedforward / feedback torque colours of the run view (CONTRACT.md, the five torques).
_SIM_COLOURS = ("#5f5e5a", "#8a8983", "#3f3e3b", "#a3a29c")
_CONFIG_COLOURS = ("#7c5cc4", "#0f9d8a", "#c22f6e", "#a67c00", "#17a2b8", "#5c8a2e", "#b8457a", "#6b7a8f", "#8c6d46", "#2e7d6b")


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


def _degrees_on(grid: np.ndarray, times: np.ndarray, values: np.ndarray) -> list[float | None]:
    """``values`` (rad) at the grid's instants in degrees, 4 decimals; None outside the line's own samples.

    WHY interpolate: every line of a target is drawn on that target's display grid (the reference's samples, picked at
    ``display_hz``) so a percentile fan can be taken per instant; when a line was sampled on the reference's instants
    (the usual case) this is exact picking, never averaging. Outside the line's span it is missing, never extrapolated.
    """
    return _picked_on(grid, times, values, scale=180.0 / math.pi)


def _picked_on(grid: np.ndarray, times: np.ndarray, values: np.ndarray, scale: float = 1.0) -> list[float | None]:
    """``values`` at the grid's instants times ``scale``, 4 decimals; None outside the line's own samples (see above)."""
    if len(times) == 0:
        return [None] * len(grid)
    inside = (grid >= times[0] - 1e-9) & (grid <= times[-1] + 1e-9)
    picked = np.interp(grid, times, values) * scale
    return [round(float(value), 4) if ok and math.isfinite(value) else None for value, ok in zip(picked, inside, strict=True)]


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
    series: str, measured: JointTrajectory, given: Mapping[str, np.ndarray], joints: Sequence[str], grid: np.ndarray,
    times: np.ndarray,
) -> dict[str, Any]:
    """One line's torque breakdown for the Dataset and Target levels (``line["torque"]``).

    The missing third comes from the run view's two-of-three rule (``analysis._torque_breakdown``); the drive gap is
    ``robot_msgs.compare.error_stats``' RMS of commanded − applied (applied = the series' ``effort``); the shares are
    plain sums. ``tau_fb`` and ``fb_share_over_time`` are display series, per joint in ``joints`` order on the target's
    grid (``times`` = the line's samples on the target clock), None outside the line's span.
    """
    situation = Situation(name=series, t=measured.t, q=measured.positions, tau=measured.effort, **given)
    breakdown, _ = _torque_breakdown(situation)
    command, feedforward, feedback = (breakdown[key] for key in _BREAKDOWN_KEYS)
    applied = situation.tau
    column_of = {name: index for index, name in enumerate(measured.joint_names)}
    t = np.asarray(measured.t, dtype=float)
    per_joint: dict[str, dict[str, float | None]] = {}
    tau_fb: list[list[float | None]] = []
    over_time: list[list[float | None]] = []
    for name in joints:
        column = column_of.get(name)
        share = gap = None
        if column is not None and feedforward is not None and feedback is not None:
            share = _fb_share(feedforward[:, column], feedback[:, column])
        if column is not None and command is not None and applied is not None:
            gap = _finite(error_stats(command[:, column] - applied[:, column], t).rms)
        per_joint[name] = {"fb_share": share, "drive_gap_rms": gap}
        if feedback is not None:
            tau_fb.append(_picked_on(grid, times, feedback[:, column]) if column is not None else [None] * len(grid))
        if feedforward is not None and feedback is not None:
            shares = _share_over_time(t, feedforward[:, column], feedback[:, column]) if column is not None else None
            over_time.append(_picked_on(grid, times, shares) if shares is not None else [None] * len(grid))
    both = feedforward is not None and feedback is not None
    return {
        "fb_share": _fb_share(feedforward, feedback) if both else None,
        "joints": per_joint,
        "tau_fb": tau_fb if feedback is not None else None,
        "fb_share_over_time": over_time if both else None,
    }


def _levels_payload(
    runs: Sequence[Run], targets: Sequence[_Target], slugs: Mapping[str, str], config_tag: str | None,
    joint_errors: Mapping[tuple[str, str], Any], entries: Sequence[Mapping[str, Any]], options: _Analysis,
    poses: Mapping[str, Mapping[str, PoseTrajectory]], display_hz: float, labels: Mapping[str, str],
) -> dict[str, Any]:
    """What the Dataset and Target levels draw: targets, configs and one line per measured series of every run.

    Scalars stay SI (rad, like ``rows``); the drawn series ``e_deg`` is the joint error target − line in degrees on the
    target's display grid (the display edge, like data_ui's tables). Every number is robot_msgs.compare's.
    """
    from .data_ui import _stride  # lazy: data_ui imports this module

    analysed = {(entry["run"], entry["pair"][1]): entry for entry in entries if entry["pair"][0] == REFERENCE}
    order = {run.name: index for index, run in enumerate(runs)}
    configs: dict[str, dict[str, int]] = {}
    lines: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    for target in targets:
        reference = target.reference
        stride, _ = _stride(reference, display_hz)
        grid = np.asarray(reference.t, dtype=float)[::stride]
        joints = list(reference.joint_names)
        members: dict[str, dict[str, list[tuple[Run, str]]]] = {}
        for run in target.runs:
            for series, measured in run.measured.items():
                kind = _kind(series)
                if config_tag is None:
                    config = series
                else:
                    config = str(_tag_value(run.tags[config_tag])) if config_tag in run.tags else f"no {config_tag}"
                configs.setdefault(config, {"sim": 0, "real": 0})[kind] += 1
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
                    lines.append({**line, "error": str(error)})
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
                    e_deg=[_degrees_on(grid, times, joint.error.positions[:, columns[name]]) for name in joints],
                )
                # WHY only when given (Zach 2026-11-19, torque breakdown in the dataset view; CONTRACT.md addendum): a
                # line without a breakdown carries no torque key at all, so a dataset without one is today's payload.
                if run.torques.get(series):
                    on_target_clock = np.asarray(measured.absolute_times, dtype=float) - offset - float(reference.header.stamp)
                    line["torque"] = _line_torque(series, measured, run.torques[series], joints, grid, on_target_clock)
                lines.append(line)
        target_row: dict[str, Any] = {
            "key": target.key,
            "slug": target.slug,
            "title": target.title,
            "named_by": target.named_by,
            "joints": joints,
            "t": [round(float(value), 4) for value in grid],
            "runs": len(target.runs),
            "repeatability": {
                config: _repeatability(reference, kinds["real"] or kinds["sim"], poses, options)
                for config, kinds in members.items()
            },
        }
        target_row["has_torque_breakdown"] = any(line.get("torque") for line in lines if line["target"] == target.slug)
        target_rows.append(target_row)
    any_breakdown = any(row["has_torque_breakdown"] for row in target_rows)
    if not any_breakdown:
        for row in target_rows:
            del row["has_torque_breakdown"]
    config_rows = []
    sim_colours, colours = iter(_SIM_COLOURS), iter(_CONFIG_COLOURS)
    for name, kinds in configs.items():
        palette = sim_colours if kinds["real"] == 0 else colours
        row = {"name": name, "color": next(palette, "#52514e"), **kinds}
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
    np.savez_compressed(path, __msg__=np.array(tree), **arrays)


def _content_digest(content: _NpzContent) -> str:
    """A SHA-1 over a message's saved content: its JSON tree, then every array's key, dtype, shape and bytes."""
    tree, arrays = content
    digest = hashlib.sha1(tree.encode("utf-8"))
    for key, array in arrays.items():
        # WHY dtype and shape too: equal bytes as float32 vs float64, or (N, 2) vs (2, N), are different references.
        digest.update(f"\0{key}\0{array.dtype.str}\0{array.shape}\0".encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


# A run folder is output/runs/<slug>, so this is output/references as its manifest names it.
_REFERENCES_FROM_RUN = "../../references"


class _References:
    """``references/<digest>.npz``: each distinct reference written once per write (NAVIGATION.md C6).

    WHY shared: the UR5e site copied ``reference.npz`` into all 4932 run folders (0.81 GB) for only 974 distinct
    references. Named by content, so equal references in new objects, another run order or another site share a name.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        # id(reference) -> (the reference, its manifest path); holding the object keeps its id from being reused.
        self._by_object: dict[int, tuple[JointTrajectory, str]] = {}
        self._written: set[str] = set()

    def save(self, reference: JointTrajectory) -> str:
        """The manifest's ``files.reference`` for ``reference``, writing its file the first time this write sees it."""
        known = self._by_object.get(id(reference))
        if known is not None and known[0] is reference:
            return known[1]
        content = _npz_content(reference)
        name = f"{_content_digest(content)}.npz"
        if name not in self._written:
            self.directory.mkdir(parents=True, exist_ok=True)
            # WHY rewritten once per write rather than skipped when present: a file a killed write truncated would
            # otherwise be trusted for as long as its name stays the same.
            _save_npz(reference, self.directory / name, content)
            self._written.add(name)
        relative = f"{_REFERENCES_FROM_RUN}/{name}"
        self._by_object[id(reference)] = (reference, relative)
        return relative

    def prune(self, runs_dir: Path) -> None:
        """Delete every ``references/*.npz`` that no ``runs/*/manifest.json`` on disk names, an earlier write's too.

        WHY every manifest on disk, not only this write's: a run folder an earlier write left still builds, so the
        reference it names must outlive this write.
        """
        if not self.directory.is_dir():
            return
        named: set[Path] = set()
        for manifest_path in runs_dir.glob("*/manifest.json"):
            try:
                files = json.loads(manifest_path.read_text("utf-8"))["files"]
                named.update((manifest_path.parent / relative).resolve() for relative in files.values())
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue  # a manifest that does not parse names nothing a drill-down could build from
        for path in self.directory.glob("*.npz"):
            if path.resolve() not in named:
                path.unlink()


def _write_run_files(
    run: Run, folder: Path, slug: str, options: _Analysis, specs: Mapping[str, str | None], import_roots: list[str],
    primary: Mapping[str, str], visible_pairs: Sequence[tuple[str, str]], target: _Target | None = None,
    *, references: _References,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    # WHY: a drill-down cached by an earlier write describes the old data; lazy mode would serve it.
    (folder / "report.html").unlink(missing_ok=True)
    shutil.rmtree(folder / "rerun", ignore_errors=True)
    # WHY: a write before 2026-11-20 copied the reference into every run folder; this manifest names references/.
    (folder / "reference.npz").unlink(missing_ok=True)
    files = {REFERENCE: references.save(run.reference)}
    for name, trajectory in run.measured.items():
        files[name] = f"{_safe_name(name)}.npz"
        _save_npz(trajectory, folder / files[name])
    # The torque breakdown beside its series (CONTRACT.md addendum): <series>.torques.npz holds only the keys given, so
    # the drill-down derives the third exactly as the run view does. WHY unlink first: a breakdown an earlier write
    # left behind would otherwise outlive the run that no longer carries it.
    for stale in folder.glob("*.torques.npz"):
        stale.unlink()
    for name, parts in run.torques.items():
        np.savez_compressed(
            folder / _torque_file(name), **{key: np.asarray(values, dtype=float) for key, values in parts.items()}
        )
    media: dict[str, str] = {}
    for key, source in run.media.items():
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"run {run.name!r}: media {key!r} is not a file: {source}")
        relative = f"media/{_safe_name(key)}{source.suffix.lower()}"
        (folder / "media").mkdir(exist_ok=True)
        shutil.copy2(source, folder / relative)
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
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


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


def _write_rows(output_dir: Path, rows: list[dict[str, Any]], files: frozenset[str]) -> None:
    """Write the row files ``files`` names (from ``_row_files``) and delete the other one, so no stale rows outlive
    their data."""
    if "json" in files:
        (output_dir / "rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    else:
        (output_dir / "rows.json").unlink(missing_ok=True)
    if "parquet" not in files:
        (output_dir / "rows.parquet").unlink(missing_ok=True)
        return
    import pyarrow as pa
    import pyarrow.parquet as pq

    columns = list(dict.fromkeys(key for row in rows for key in row))
    arrays = {}
    for column in columns:
        values = [row.get(column) for row in rows]
        try:
            arrays[column] = pa.array(values)
        except (pa.ArrowInvalid, pa.ArrowTypeError):  # a tag whose type differs between runs: keep it as text
            arrays[column] = pa.array([None if value is None else str(value) for value in values])
    pq.write_table(pa.table(arrays), output_dir / "rows.parquet")


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
) -> Path:
    """Write ``output_dir/index.html`` (many runs at a glance), ``rows.json``/``rows.parquet`` and ``runs/<slug>/``.

    - ``target_by``: the tag naming a run's target trajectory (the Dataset level's cards, ``#/target/<slug>``). Default:
      ``"target"`` when any run has it, else the first ``group_by`` tag, else a content hash of the reference, titled by
      its first run. An explicit ``target_by`` value holding two different references raises ``ValueError``.
    - ``config_by``: the tag naming a line's robot config (its colour on every level). Default: the first ``group_by``
      tag that does not name the target, else the series name. A line is one measured series of one run, its kind
      ``real`` when the series name starts with "real", else ``sim``; a run's ``"date"`` tag orders the control chart.
    - ``display_hz``: the rate of the error series the index embeds for its charts (reference samples picked, never
      averaged); rows.json and the drill-down keep every sample.
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
    """

    runs = list(runs)
    primary = dict(primary or {})
    group_by = tuple(group_by)
    row_files = _row_files(rows)  # NAVIGATION.md C2: refused before anything is written, the output directory included
    if drill_down not in _DRILL_DOWNS:
        raise ValueError(f"drill_down is one of {_DRILL_DOWNS}, got {drill_down!r}")
    if display_hz <= 0:
        raise ValueError(f"display_hz must be positive, got {display_hz}")
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
    if robot:
        _import_spec(robot, import_roots)  # fail now, not on the first drill-down

    series_order = list(dict.fromkeys(name for run in runs for name in run.measured))
    pair_order = list(dict.fromkeys(pair for run in runs for pair in run.resolved_pairs()))
    default_view = [pair for pair in pair_order if all(_visible(name, primary) for name in pair)]

    tidy_rows: list[dict[str, Any]] = []  # WHY not `rows`: that name is the row-file choice (C2)
    entries: list[dict[str, Any]] = []
    pose_cache: dict[str, dict[str, PoseTrajectory]] = {}
    joint_errors: dict[tuple[str, str], Any] = {}
    references = _References(output_dir / "references")
    for run in runs:
        slug = slugs[run.name]
        _write_run_files(
            run, output_dir / "runs" / slug, slug, options, specs, import_roots, primary, default_view, target_of[run.name],
            references=references,
        )
        tags = {key: _tag_value(value) for key, value in run.tags.items()}
        pose_cache[run.name] = options.pose_trajectories(run)
        for first, second in run.resolved_pairs():
            pair_name = _pair_name(first, second)
            rrd = f"runs/{slug}/rerun/{pair_name}.rrd"
            entry: dict[str, Any] = {
                "run": run.name,
                "slug": slug,
                "pair": [first, second],
                "tags": tags,
                "report": f"runs/{slug}/report.html",
                "rrd": rrd,
                "rerun_command": (
                    f"python -m traj_compare.dataset drill {shlex.quote(str(output_dir.resolve()))} "
                    f"{shlex.quote(run.name)} && "
                    + rerun_export.viewer_command(output_dir.resolve() / rrd)
                ),
            }
            try:
                analysis, metrics = _analyze_pair(run, first, second, options, pose_cache[run.name], joint_errors)
            except ValueError as error:  # e.g. the two series never overlap in time
                # WHY recorded, not raised: one broken run must not hide the other 386; the row says why.
                warnings.warn(f"{run.name}: {first} -> {second}: {error}", stacklevel=2)
                entries.append({**entry, "error": str(error)})
                continue
            entries.append({**entry, **analysis})
            base = {"run": run.name, "pair": [first, second]}
            for metric, stats in metrics:
                unit = _metric_unit(metric)
                for stat, value in stats.as_dict().items():
                    tidy_rows.append(
                        {**base, "metric": metric, "stat": stat, "value": _finite(value), "unit": _stat_unit(unit, stat), **tags}
                    )  # fmt: skip
            for metric, stat, value, unit in (
                ("coverage", "value", analysis["coverage"], ""),
                ("latency", "value", analysis["latency_s"], "s"),
            ):
                tidy_rows.append({**base, "metric": metric, "stat": stat, "value": value, "unit": unit, **tags})
    _write_rows(output_dir, tidy_rows, row_files)
    references.prune(output_dir / "runs")

    aggregates = _group_aggregates(runs, group_by, options, pose_cache)
    joint_names = list(dict.fromkeys(name for entry in entries for name in entry.get("joints", {})))
    labels = {series: alias for alias, series in primary.items()}
    levels = _levels_payload(
        runs, targets, slugs, config_tag, joint_errors, entries, options, pose_cache, display_hz, labels
    )
    payload = {
        "title": title,
        "generated": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "angle_unit": "deg",
        "group_by": list(group_by),
        "drill_down": drill_down,
        "serve_command": f"python -m traj_compare.serve {shlex.quote(str(output_dir.resolve()))}",
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
        "rows": _clean(entries),
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
    index.write_text(document, encoding="utf-8")

    if data_ui:
        from .data_ui import links_from_robot, stage_viewer, write_tables  # lazy: data_ui imports this module

        write_tables(
            runs,
            output_dir / "data-ui",
            poses=options.poses,
            links=links_from_robot(_import_spec(robot, import_roots)) if robot else None,
        )
        stage_viewer(output_dir, title=title)  # data-ui.html + kit link when a built data-ui is on this machine
    if drill_down == "eager":
        for run in runs:
            build_drill_down(output_dir, run.name)
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
