"""Runs and poses functions for the incremental-write acceptance tests (tests/test_incremental_writes.py, 2026-11-20).

docs/NAVIGATION.md Part D (frozen @ bfbcba2). Synthesized and seeded, so the ruler never moves; small, so a write takes
well under a second. What the tests count on:

- **Three targets** by the ``target`` tag (``reach``, ``wave``, ``swing``) at 100 Hz, each with its own sample count
  (101, 131, 161), so a trajectory a counted function is handed tells its target by its length alone. A fourth,
  ``solo`` (71 samples), is the only target of ``SOLO``, a run some tests add and later drop.
- **Two configs** by the ``controller`` tag (``pd``, ``mpc``; ``config_by="controller"``).
- **Every run** measures ``"sim"`` and ``"real"`` (default pairs: target to each, then sim to real). Every ``real`` has
  an ``effort``, ``channels["current"]`` ((N, 2), A) and ``channels["grip_force"]`` ((N,), described by ``SIGNALS``).
- **PROBE** (``"wave mpc 1"``, the middle of the list) carries every per-run ingredient a digest covers: a torque
  breakdown on ``real`` (``tau_ff`` + ``tau_fb``), a media file on ``real`` with ``media_start_s``, its own title and
  tags. ``"swing pd 2"`` carries a breakdown on ``sim`` (``tau_cmd`` + ``tau_fb``).
- **LATE** (``"swing late"``): its ``real`` runs 50 s after the reference, so (reference, real) and (sim, real) never
  overlap: today the write warns and records an ``error`` entry for each.
- **EXTRA** (``"reach mpc 2"``): a run the base set does not have (a run added by a later write).
- ``tool_xy`` / ``tool_xy_long``: planar 2-link TCPs (``poses="incremental_fixture:tool_xy"``). Each call appends the
  sample count of the trajectory it was handed to ``POSES_CALLS``: the counter the reuse tests read.
- ``make_clip``: the probe's media file, fixed bytes and a fixed ``mtime_ns`` (a digest covers (key, size,
  ``mtime_ns``), so two clips made by ``make_clip`` in different folders digest alike).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from robot_msgs.compare import JointTolerance, Tolerances
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from traj_compare import Run, Signal

JOINTS = ("shoulder", "elbow")
RATE_HZ = 100.0
SEED = 20261120
TITLE = "Incremental writes"
POSES = "incremental_fixture:tool_xy"
POSES_LONG = "incremental_fixture:tool_xy_long"
CONFIG_TAG = "controller"

# target -> (duration s, phase): 1.0 s = 101 samples, 1.3 s = 131, 1.6 s = 161, 0.7 s = 71
TARGETS = {"reach": (1.0, 0.0), "wave": (1.3, 0.6), "swing": (1.6, 1.2), "solo": (0.7, 1.8)}
LATE_S = 50.0


def samples_of(target: str) -> int:
    return round(TARGETS[target][0] * RATE_HZ) + 1


# ── the poses functions (counted) ────────────────────────────────────────────

POSES_CALLS: list[int] = []  # the sample count of every trajectory tool_xy / tool_xy_long was handed, in call order


def _planar_tool(trajectory: JointTrajectory, upper_m: float, lower_m: float) -> PoseTrajectory:
    POSES_CALLS.append(len(trajectory.t))
    q = trajectory.positions
    yaw = q[:, 0] + q[:, 1]
    positions = np.column_stack(
        [upper_m * np.cos(q[:, 0]) + lower_m * np.cos(yaw), upper_m * np.sin(q[:, 0]) + lower_m * np.sin(yaw), 0 * yaw]
    )
    quats = np.column_stack([0 * yaw, 0 * yaw, np.sin(yaw / 2), np.cos(yaw / 2)])
    return PoseTrajectory(
        t=trajectory.t, positions=positions, orientations=quats, child_frame_id="tool", header=trajectory.header
    )


def tool_xy(trajectory: JointTrajectory) -> PoseTrajectory:
    return _planar_tool(trajectory, 0.30, 0.25)


def tool_xy_long(trajectory: JointTrajectory) -> PoseTrajectory:
    return _planar_tool(trajectory, 0.40, 0.35)


# ── the write's options ──────────────────────────────────────────────────────


def tolerances(position: float = 0.05) -> Tolerances:
    return Tolerances(path=tuple(JointTolerance(name=name, position=position) for name in JOINTS))


def signals(grip_title: str = "Grip force") -> dict[str, Signal]:
    return {"grip_force": Signal(title=grip_title, unit="N")}


def write_options(**overrides) -> dict:
    """Every option the base writes pass; ``overrides`` replace or add keyword arguments."""
    options = {
        "title": TITLE,
        "config_by": CONFIG_TAG,
        "tolerances": tolerances(),
        "poses": POSES,
        "signals": signals(),
        "primary": {"twin": "sim"},
        "drill_down": "lazy",
    }
    options.update(overrides)
    return options


# ── the media file ───────────────────────────────────────────────────────────

CLIP_BYTES = b"\x00\x00\x00\x18ftypmp42" + bytes(range(64))
CLIP_MTIME_NS = 1_763_600_000_123_456_789


def make_clip(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "probe-real.mp4"
    path.write_bytes(CLIP_BYTES)
    os.utime(path, ns=(CLIP_MTIME_NS, CLIP_MTIME_NS))
    return path


# ── the runs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunPlan:
    name: str
    target: str
    controller: str
    seed: int
    torques: str | None = None  # the series carrying a torque breakdown, if any
    media: bool = False
    late: bool = False


PROBE = "wave mpc 1"
LATE = "swing late"
EXTRA = "reach mpc 2"
SOLO = "solo 1"

PLANS = (
    RunPlan("reach pd 1", "reach", "pd", 1),
    RunPlan("reach pd 2", "reach", "pd", 2),
    RunPlan("reach mpc 1", "reach", "mpc", 3),
    RunPlan("wave pd 1", "wave", "pd", 4),
    RunPlan(PROBE, "wave", "mpc", 5, torques="real", media=True),
    RunPlan("wave mpc 2", "wave", "mpc", 6),
    RunPlan("swing pd 1", "swing", "pd", 7),
    RunPlan("swing pd 2", "swing", "pd", 8, torques="sim"),
    RunPlan("swing mpc 1", "swing", "mpc", 9),
    RunPlan(LATE, "swing", "mpc", 10, late=True),
)
EXTRA_PLAN = RunPlan(EXTRA, "reach", "mpc", 11)
SOLO_PLAN = RunPlan(SOLO, "solo", "pd", 12)
ALL_PLANS = {plan.name: plan for plan in (*PLANS, EXTRA_PLAN, SOLO_PLAN)}
BASE = tuple(plan.name for plan in PLANS)


def target_of(name: str) -> str:
    return ALL_PLANS[name].target


def _motion(t: np.ndarray, phase: float) -> np.ndarray:
    duration = float(t[-1]) or 1.0
    return np.column_stack(
        [(0.4 + 0.15 * k) * np.sin(2.0 * np.pi * (1.0 + 0.5 * k) * t / duration + phase + 0.7 * k) for k in range(len(JOINTS))]
    )


def reference_of(target: str) -> JointTrajectory:
    duration, phase = TARGETS[target]
    t = np.round(np.arange(round(duration * RATE_HZ) + 1) / RATE_HZ, 6)
    return JointTrajectory(t=t, joint_names=JOINTS, positions=_motion(t, phase))


def _run(plan: RunPlan, reference: JointTrajectory, clip: Path | None) -> Run:
    rng = np.random.default_rng(SEED + plan.seed)
    t = np.array(reference.t)
    phase = TARGETS[plan.target][1]
    samples = len(t)
    sim_q = _motion(t - 0.004 * rng.uniform(0.8, 1.2), phase) + 0.0005 * rng.uniform(-1.0, 1.0, len(JOINTS))
    real_q = (
        _motion(t - 0.015 * rng.uniform(0.8, 1.2), phase)
        + 0.002 * np.sin(2.0 * np.pi * rng.uniform(0.8, 1.6) * t[:, None] + rng.uniform(0.0, 6.28, len(JOINTS)))
        + 0.001 * rng.uniform(-1.0, 1.0, len(JOINTS))
    )
    effort = 0.8 * real_q + np.array([1.2, 0.6]) + rng.normal(0.0, 0.01, size=real_q.shape)
    channels = {
        "current": np.column_stack([3.0 + 0.4 * np.sin(2.0 * np.pi * t), 2.0 + 0.3 * np.cos(2.0 * np.pi * t)])
        + rng.normal(0.0, 0.02, size=(samples, len(JOINTS))),
        "grip_force": 2.0 + np.sin(2.0 * np.pi * t / (float(t[-1]) or 1.0)) + rng.normal(0.0, 0.01, size=samples),
    }
    sim = JointTrajectory(t=t, joint_names=JOINTS, positions=sim_q)
    real_t = t + LATE_S if plan.late else t
    real = JointTrajectory(t=real_t, joint_names=JOINTS, positions=real_q, effort=effort, channels=channels)
    torques: dict = {}
    if plan.torques == "real":
        torques = {"real": {"tau_ff": 1.0 + 0.3 * real_q, "tau_fb": rng.normal(0.0, 0.1, size=real_q.shape)}}
    elif plan.torques == "sim":
        torques = {"sim": {"tau_cmd": 1.1 + 0.3 * sim_q, "tau_fb": rng.normal(0.0, 0.1, size=sim_q.shape)}}
    media: dict = {}
    media_start_s: dict = {}
    if plan.media:
        if clip is None:
            raise ValueError(f"run {plan.name!r} carries a media file: pass clip=make_clip(directory)")
        media, media_start_s = {"real": clip}, {"real": 0.1}
    return Run(
        name=plan.name,
        reference=reference,
        measured={"sim": sim, "real": real},
        tags={"target": plan.target, CONFIG_TAG: plan.controller, "speed": 0.5},
        title=f"{plan.name} take",  # WHY one title per run: a target's title is then its key, whichever title changes
        media=media,
        media_start_s=media_start_s,
        torques=torques,
    )


def build_runs(clip: Path | None, names: Sequence[str] = BASE) -> list[Run]:
    """New ``Run`` objects (new arrays, new messages) for ``names``, in that order; equal names give equal content.

    Every run of a target shares one reference object, as a recorder's runs do."""
    references: dict[str, JointTrajectory] = {}
    runs = []
    for name in names:
        plan = ALL_PLANS[name]
        reference = references.setdefault(plan.target, reference_of(plan.target))
        runs.append(_run(plan, reference, clip))
    return runs
