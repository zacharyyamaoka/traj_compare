"""Production ``Run``s for the three-level dataset view's acceptance tests (tests/test_dataset_levels.py, 2026-11-19).

Synthesized (seeded) in the shape of docs/layout_proposals_2026-11-19/fixture/fixture.json, the data Zach reviewed the
summary layouts on: a vertical planar 2R arm (shoulder, elbow), three targets (full-circle-slow 6 s, full-circle-fast 2 s,
pick-swing 3 s), the tags ``target``, ``ff_model`` ("v1 nominal" / "v2 calibrated") and ``date`` (2026-11-18 / 2026-11-19),
sim and real series. WHY synthesized, not read from that file: an acceptance ruler must not move when a dated prototype
folder is pruned, and that file has one series per run where the production ``Run`` holds several.

What the tests count on:

- full-circle-slow: "v1 nominal" has 6 real lines + 1 sim (7 > N = 5: a fan), "v2 calibrated" 3 lines (lines stay lines).
  Both configs and both kinds appear on both dates, and both kinds in both configs, so a row order grouped by one of
  date / config / kind is never grouped by another: a sort that does nothing fails one of the sort checks.
- full-circle-fast: one Run holds the series "twin_it5" (a sim: its name does not start with "real") and "real_retake"
  (a real), so a line's kind comes from its series name, not from the words "sim" / "real".
- "v2 calibrated" tracks better than "v1 nominal" on full-circle-slow and full-circle-fast (0.4x the error) and worse on
  pick-swing (2.5x): "better on 2 of 3 targets". The first Run is "v1 nominal", so v1 is the baseline (first config).
- Runs of different targets are interleaved, so "only this target's lines" is a real filter, not the run order.
- Every Run of a target shares one reference object (the same trajectory) and is titled by its target.

No torques: ``Run`` carries no torque breakdown, and NAVIGATION.md makes the feedback / FB-share charts optional.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run

JOINTS = ("shoulder", "elbow")
SAMPLE_S = 0.01
SEED = 20261119

TARGET_TAG = "target"
CONFIG_TAG = "ff_model"
DATE_TAG = "date"
BASELINE = "v1 nominal"
CALIBRATED = "v2 calibrated"
FIRST_DAY = "2026-11-18"
SECOND_DAY = "2026-11-19"

ELBOW_HELD_RAD = np.deg2rad(23.0)
SIM_ERROR_SCALE = 0.15  # an ideal-plant sim tracks far better than any real run, whatever its config


def _minimum_jerk(phase: np.ndarray) -> np.ndarray:
    phase = np.clip(phase, 0.0, 1.0)
    return phase**3 * (10.0 - 15.0 * phase + 6.0 * phase**2)


def _full_circle(t: np.ndarray, duration_s: float) -> np.ndarray:
    """Shoulder one full turn, elbow held at 23 degrees."""
    shoulder = 2.0 * np.pi * _minimum_jerk(t / duration_s)
    return np.column_stack([shoulder, np.full_like(shoulder, ELBOW_HELD_RAD)])


def _pick_swing(t: np.ndarray, duration_s: float) -> np.ndarray:
    """Out to a pick pose and back, both joints moving."""
    out_and_back = np.sin(np.pi * np.clip(t / duration_s, 0.0, 1.0)) ** 2
    return np.column_stack([1.1 * out_and_back, ELBOW_HELD_RAD + 0.9 * out_and_back])


@dataclass(frozen=True)
class Target:
    key: str
    title: str
    duration_s: float
    calibrated_error_scale: float  # the "v2 calibrated" real error relative to "v1 nominal" on this target
    shape: Callable[[np.ndarray, float], np.ndarray]

    def times(self) -> np.ndarray:
        return np.round(np.arange(round(self.duration_s / SAMPLE_S) + 1) * SAMPLE_S, 6)

    def positions(self, t: np.ndarray) -> np.ndarray:
        return self.shape(t, self.duration_s)


TARGETS = {
    target.key: target
    for target in (
        Target("full-circle-slow", "Full-circle probe · slow (6 s)", 6.0, 0.4, _full_circle),
        Target("full-circle-fast", "Full-circle probe · fast (2 s)", 2.0, 0.4, _full_circle),
        Target("pick-swing", "Pick swing (3 s)", 3.0, 2.5, _pick_swing),
    )
}

# (run name, target, ff_model, date, series) in run order.
PLAN: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("slow v1 rep 1", "full-circle-slow", BASELINE, FIRST_DAY, ("real",)),
    ("fast v1 rep 1", "full-circle-fast", BASELINE, FIRST_DAY, ("twin_it5", "real_retake")),
    ("slow v2 rep 1", "full-circle-slow", CALIBRATED, FIRST_DAY, ("sim", "real")),
    ("pick v1 rep 1", "pick-swing", BASELINE, FIRST_DAY, ("sim", "real")),
    ("slow v1 rep 2", "full-circle-slow", BASELINE, FIRST_DAY, ("real",)),
    ("slow v1 rep 3", "full-circle-slow", BASELINE, SECOND_DAY, ("sim", "real")),
    ("fast v1 rep 2", "full-circle-fast", BASELINE, SECOND_DAY, ("real",)),
    ("slow v1 rep 4", "full-circle-slow", BASELINE, SECOND_DAY, ("real",)),
    ("fast v2 rep 1", "full-circle-fast", CALIBRATED, SECOND_DAY, ("real",)),
    ("slow v2 rep 2", "full-circle-slow", CALIBRATED, SECOND_DAY, ("real",)),
    ("pick v1 rep 2", "pick-swing", BASELINE, SECOND_DAY, ("real",)),
    ("slow v1 rep 5", "full-circle-slow", BASELINE, SECOND_DAY, ("real",)),
    ("fast v2 rep 2", "full-circle-fast", CALIBRATED, SECOND_DAY, ("real",)),
    ("pick v2 rep 1", "pick-swing", CALIBRATED, SECOND_DAY, ("real",)),
    ("slow v1 rep 6", "full-circle-slow", BASELINE, SECOND_DAY, ("real",)),
)


def kind_of(series: str) -> str:
    """NAVIGATION.md's rule (data_ui.py's family rule): ``real`` when the series name starts with "real", else ``sim``."""
    return "real" if series.startswith("real") else "sim"


def line_id(run_name: str, series: str) -> str:
    return f"{run_name} · {series}"


@dataclass(frozen=True)
class Line:
    """One measured series of one Run: what the target page lists as a row."""

    id: str
    run: str
    series: str
    target: str
    config: str
    date: str
    kind: str


def reference(target: Target) -> JointTrajectory:
    t = target.times()
    return JointTrajectory(t=t, joint_names=JOINTS, positions=target.positions(t))


def _measured(target: Target, error_scale: float, rng: np.random.Generator) -> JointTrajectory:
    """The target run late by a lag, plus a slow ripple and a bias, all growing with ``error_scale``."""
    t = target.times()
    lag_s = 0.012 * error_scale * rng.uniform(0.8, 1.2)
    ripple_hz = rng.uniform(0.8, 1.6)
    phases = rng.uniform(0.0, 2.0 * np.pi, size=len(JOINTS))
    ripple = 0.003 * error_scale * rng.uniform(0.7, 1.3) * np.sin(2.0 * np.pi * ripple_hz * t[:, None] + phases)
    bias = 0.001 * error_scale * rng.uniform(-1.0, 1.0, size=len(JOINTS))
    return JointTrajectory(t=t, joint_names=JOINTS, positions=target.positions(t - lag_s) + ripple + bias)


def _error_scale(target: Target, config: str, series: str) -> float:
    if kind_of(series) == "sim":
        return SIM_ERROR_SCALE
    return target.calibrated_error_scale if config == CALIBRATED else 1.0


def build_runs() -> list[Run]:
    """The 15 Runs (19 lines: 4 sim, 15 real) of PLAN, tagged target / ff_model / date, seeded."""
    rng = np.random.default_rng(SEED)
    references = {key: reference(target) for key, target in TARGETS.items()}
    runs = []
    for name, key, config, date, series_names in PLAN:
        target = TARGETS[key]
        runs.append(
            Run(
                name=name,
                reference=references[key],
                measured={series: _measured(target, _error_scale(target, config, series), rng) for series in series_names},
                tags={TARGET_TAG: key, CONFIG_TAG: config, DATE_TAG: date},
                title=target.title,
            )
        )
    return runs


def lines_of(runs: Sequence[Run], target: str | None = None, target_tag: str = TARGET_TAG) -> list[Line]:
    """Every line of ``runs`` in run order (of one target when given)."""
    return [
        Line(
            id=line_id(run.name, series),
            run=run.name,
            series=series,
            target=str(run.tags.get(target_tag, "")),
            config=str(run.tags.get(CONFIG_TAG, "")),
            date=str(run.tags.get(DATE_TAG, "")),
            kind=kind_of(series),
        )
        for run in runs
        for series in run.measured
        if target is None or run.tags.get(target_tag) == target
    ]


def retagged(runs: Sequence[Run], old: str, new: str) -> list[Run]:
    """The same Runs with the tag ``old`` renamed ``new`` (no "target" tag left when ``old`` is it)."""
    return [
        dataclasses.replace(run, tags={(new if key == old else key): value for key, value in run.tags.items()})
        for run in runs
    ]


def untagged(runs: Sequence[Run]) -> list[Run]:
    """The same Runs with no tags at all: only their references say which target they follow."""
    return [dataclasses.replace(run, tags={}) for run in runs]
