"""Production ``Run``s for the lazy-target and config-colour acceptance tests (tests/test_dataset_lazy_targets.py, 2026-11-20).

docs/NAVIGATION.md Part C, C4 (config colours) and C5 (per-level detail and the index's size). Synthesized and seeded, so
the ruler never moves: every reference is a smooth multi-joint motion, every line the reference run late by a small lag
plus a ripple and a bias. Each ``Run`` holds ONE measured series, so one run is one line and one runs-table row.

What the tests count on:

- **browser**: the page the lazy-loading tests drive. ``BIG`` comes first and is recorded at 120 Hz (the default
  ``display_hz`` 50 picks every 3rd sample: 40 Hz drawn); every other target at 200 Hz (every 4th: 50 Hz drawn), so a
  card or chart that states ``display_hz`` instead of the rate it draws is caught. ``BIG`` has 12 lines over two configs
  (10 real, 2 sim; v2's 4 real lines with a torque breakdown, so its repeat tab also draws feedback torque and FB share
  per joint), the 36 small targets 3 lines each and no breakdown: 37 cards, enough that the last rows sit far below a
  900 px fold.
- **files**: three targets at 200 Hz, three joints, some lines with a torque breakdown (``tau_ff`` + ``tau_fb`` and an
  ``effort``), 14 lines; a ``slim`` variant drops the last target (the stale-file rewrite).
- **budget**: one target whose file must be strided past ``display_hz`` by ``target_budget`` and one that fits.
- **size**: 60 targets x 5 lines x 6 joints x 20 s at 200 Hz, a torque breakdown on 2 of every 5 lines (arm_motion_bench's
  shape at a size a test can write); ``tiny`` is its first target with one line, the fixed overhead of an index.
- **colours**: ``n_sim_only`` configs with only sim lines and ``n_real`` configs with only real lines, one target.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run

TARGET_TAG = "target"
CONFIG_TAG = "cfg"
SEED = 20261120


def times(duration_s: float, rate_hz: float) -> np.ndarray:
    """``duration_s`` of samples at ``rate_hz``, both ends included, rounded as recorders write them."""
    return np.round(np.arange(round(duration_s * rate_hz) + 1) / rate_hz, 6)


def _motion(t: np.ndarray, joints: Sequence[str], phase: float) -> np.ndarray:
    """A smooth out-and-back per joint: each joint its own amplitude and frequency, ``phase`` per target."""
    duration = float(t[-1]) or 1.0
    columns = []
    for index, _ in enumerate(joints):
        amplitude = 0.4 + 0.15 * index
        cycles = 1.0 + 0.5 * (index % 3)
        columns.append(amplitude * np.sin(2.0 * np.pi * cycles * t / duration + phase + 0.7 * index))
    return np.column_stack(columns)


@dataclass(frozen=True)
class LinePlan:
    """One run = one line: its config, its series name (kind from the name: ``real*`` is real), a torque breakdown or not."""

    config: str
    series: str = "real"
    torque: bool = False
    error_scale: float = 1.0


@dataclass(frozen=True)
class TargetPlan:
    key: str
    duration_s: float
    rate_hz: float
    joints: tuple[str, ...]
    lines: tuple[LinePlan, ...]
    title: str = ""


def reference_of(plan: TargetPlan, phase: float) -> JointTrajectory:
    t = times(plan.duration_s, plan.rate_hz)
    return JointTrajectory(t=t, joint_names=plan.joints, positions=_motion(t, plan.joints, phase))


def feedforward(t: np.ndarray, joints: Sequence[str]) -> np.ndarray:
    return np.column_stack([1.2 + 0.4 * np.sin(2.0 * np.pi * t / (float(t[-1]) or 1.0) + k) for k, _ in enumerate(joints)])


def feedback(t: np.ndarray, joints: Sequence[str], scale: float) -> np.ndarray:
    return np.column_stack([scale * (0.2 + 0.1 * k) * np.cos(2.0 * np.pi * 1.3 * t + k) for k, _ in enumerate(joints)])


def build_runs(plans: Sequence[TargetPlan], *, seed: int = SEED, prefix: str = "") -> list[Run]:
    """One Run per line of every target, tagged ``target`` / ``cfg``, in plan order; every run of a target shares its
    reference object. A torque line carries ``tau_ff`` + ``tau_fb`` and an ``effort`` a little short of their sum."""
    rng = np.random.default_rng(seed)
    runs: list[Run] = []
    for number, plan in enumerate(plans):
        phase = 0.37 * number
        reference = reference_of(plan, phase)
        t = reference.t
        for index, line in enumerate(plan.lines):
            scale = line.error_scale * (0.15 if not line.series.startswith("real") else 1.0)
            lag_s = 0.010 * scale * rng.uniform(0.8, 1.2)
            ripple = 0.002 * scale * np.sin(2.0 * np.pi * rng.uniform(0.8, 1.6) * t[:, None] + rng.uniform(0, 6.28, len(plan.joints)))
            bias = 0.001 * scale * rng.uniform(-1.0, 1.0, size=len(plan.joints))
            positions = _motion(t - lag_s, plan.joints, phase) + ripple + bias
            extra: dict = {}
            effort = None
            if line.torque:
                ff = feedforward(t, plan.joints)
                fb = feedback(t, plan.joints, 0.5 + 0.25 * (index % 3))
                effort = 0.93 * (ff + fb) - 0.01
                extra["torques"] = {line.series: {"tau_ff": ff, "tau_fb": fb}}
            measured = JointTrajectory(t=t, joint_names=plan.joints, positions=positions, effort=effort)
            runs.append(
                Run(
                    name=f"{prefix}{plan.key} {line.config} rep {index + 1}",
                    reference=reference,
                    measured={line.series: measured},
                    tags={TARGET_TAG: plan.key, CONFIG_TAG: line.config},
                    title=plan.title or plan.key,
                    **extra,
                )
            )
    return runs


def line_id(run: Run) -> str:
    (series,) = run.measured
    return f"{run.name} · {series}"


# ── browser ──────────────────────────────────────────────────────────────────

BIG = "big-probe"
BIG_RATE_HZ = 120.0  # display_hz 50 -> stride ceil(120 / 50) = 3 -> 40 Hz drawn
SMALL_RATE_HZ = 200.0  # display_hz 50 -> stride 4 -> 50 Hz drawn
BROWSER_JOINTS = ("shoulder", "elbow")
SMALL_TARGETS = 36
BIG_LINES = 12
BIG_TORQUE_LINES = 4  # v2's real lines carry a torque breakdown: BIG's repeat tab draws joint error, feedback torque, FB share


def browser_plans() -> list[TargetPlan]:
    big_lines = tuple(
        [LinePlan("v1", "real", error_scale=1.0 + 0.05 * k) for k in range(6)]
        + [LinePlan("v1", "sim")]
        + [LinePlan("v2", "real", torque=True, error_scale=0.5 + 0.05 * k) for k in range(BIG_TORQUE_LINES)]
        + [LinePlan("v2", "sim")]
    )
    plans = [TargetPlan(BIG, 4.0, BIG_RATE_HZ, BROWSER_JOINTS, big_lines, title="Big probe (12 lines)")]
    for number in range(SMALL_TARGETS):
        plans.append(
            TargetPlan(
                f"small-{number + 1:02d}", 4.0, SMALL_RATE_HZ, BROWSER_JOINTS,
                (LinePlan("v1", "real"), LinePlan("v2", "real", error_scale=0.6), LinePlan("v2", "sim")),
                title=f"Small target {number + 1:02d}",
            )
        )  # fmt: skip
    return plans


# ── files ────────────────────────────────────────────────────────────────────

FILES_JOINTS = ("base", "shoulder", "elbow")
FILES_RATE_HZ = 200.0


def files_plans(slim: bool = False) -> list[TargetPlan]:
    plans = [
        TargetPlan(
            "reach", 3.0, FILES_RATE_HZ, FILES_JOINTS,
            (LinePlan("v1"), LinePlan("v1"), LinePlan("v2", torque=True), LinePlan("v2", torque=True), LinePlan("v2", "sim", torque=True)),
        ),
        TargetPlan("wave", 2.5, FILES_RATE_HZ, FILES_JOINTS, (LinePlan("v1"), LinePlan("v1", "sim"), LinePlan("v2"), LinePlan("v2"))),
        TargetPlan("swing-back", 2.0, FILES_RATE_HZ, FILES_JOINTS, (LinePlan("v1", torque=True), LinePlan("v1"), LinePlan("v2"), LinePlan("v2", "sim_it5"), LinePlan("v2"))),
    ]  # fmt: skip
    return plans[:2] if slim else plans


# ── budget ───────────────────────────────────────────────────────────────────

BUDGET_JOINTS = ("shoulder", "elbow")
BUDGET_RATE_HZ = 200.0
BUDGET = 1700
# "strided": 4 lines x 2 joints x 2001 samples (10 s). At display_hz 50 (stride 4) the file would hold 4 x 2 x 501 = 4008
# values > 1700. Stride 9 gives 223 samples (1784 > 1700); stride 10 gives 201 (1608 <= 1700): the first that fits, 20 Hz.
# "fits": 1 line x 2 joints x 501 = 1002 <= 1700, so it keeps display_hz's stride 4 (50 Hz): the cap is per target.
BUDGET_STRIDED = "strided"
BUDGET_FITS = "fits"


def budget_plans() -> list[TargetPlan]:
    return [
        TargetPlan(BUDGET_STRIDED, 10.0, BUDGET_RATE_HZ, BUDGET_JOINTS, tuple(LinePlan("v1" if k < 2 else "v2") for k in range(4))),
        TargetPlan(BUDGET_FITS, 10.0, BUDGET_RATE_HZ, BUDGET_JOINTS, (LinePlan("v1"),)),
    ]


# ── size ─────────────────────────────────────────────────────────────────────

SIZE_TARGETS = 60
SIZE_LINES = 5
SIZE_JOINTS = ("j1", "j2", "j3", "j4", "j5", "j6")
SIZE_DURATION_S = 20.0
SIZE_RATE_HZ = 200.0


def size_plans(targets: int = SIZE_TARGETS, lines: int = SIZE_LINES) -> list[TargetPlan]:
    shape = (
        LinePlan("v1"), LinePlan("v1", torque=True), LinePlan("v2"), LinePlan("v2", torque=True), LinePlan("v2", "sim"),
    )[:lines]  # fmt: skip
    return [TargetPlan(f"t{number:02d}", SIZE_DURATION_S, SIZE_RATE_HZ, SIZE_JOINTS, shape) for number in range(targets)]


# ── colours ──────────────────────────────────────────────────────────────────

COLOUR_JOINTS = ("shoulder", "elbow")


def colour_configs(kinds: Sequence[str]) -> list[str]:
    """One config per entry of ``kinds`` ("sim" = a config with only sim lines, "real" = only real lines), in config
    order: ``c01 sim``, ``c02 real``, ..."""
    return [f"c{index + 1:02d} {kind}" for index, kind in enumerate(kinds)]


def colour_plans(kinds: Sequence[str], key: str = "probe") -> list[TargetPlan]:
    """One target, one line per config, in ``kinds`` order (so config order is ``kinds`` order)."""
    names = colour_configs(kinds)
    lines = tuple(LinePlan(name, "sim" if kind == "sim" else "real") for name, kind in zip(names, kinds, strict=True))
    return [TargetPlan(key, 1.0, 100.0, COLOUR_JOINTS, lines)]
