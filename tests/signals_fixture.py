"""Small data for docs/NAVIGATION.md Part C1, "Signals beyond the joints" (frozen 2026-11-20).

A 3-joint arm (shoulder, elbow, wrist), 3 s at 100 Hz (301 samples), on smooth signals. Two builders:

- ``channels_comparison(Signal, ...)``: a run-view ``Comparison`` (target + "sim" + "real") whose situations carry
  ``Situation.channels`` and ``Situation.current``. Which situation carries which channel is ``CARRIERS``:
  - ``grip_force``, 1-D, described ``Signal("Grip force", "N")``: on the target and both runs;
  - ``contact_force``, (N, 3), described with columns x / y / z (3 columns on 3 joints, NOT per joint: never reordered);
  - ``winding_temp``, (N, 3), described ``per_joint=True``;
  - ``contact_force_n``, (N, 2), undescribed (the contract's own example name): on "real" only;
  - ``SPINDLE`` (``"__Spindle.Load__ (left)"``), 1-D, undescribed: on "real" only (the slug's strip rule, and a name
    that must be drawn exactly as recorded).
- ``channel_runs()``: dataset ``Run``s. "channels run"'s one series "real" records its joints in ANOTHER order
  (``SERIES_JOINTS``) than its reference (``JOINTS``), with ``channels["current"]`` (N, J) and three channels in that
  series order; "plain run" has no channels.

``Signal`` is passed in by the caller, so importing this module never needs a name the package does not have yet.
Every value is deterministic; the per-situation offsets keep traces apart, so a plot shows each one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Comparison, Run, Situation

JOINTS = ("shoulder", "elbow", "wrist")
SERIES_JOINTS = ("elbow", "wrist", "shoulder")  # the dataset series' own joint order
# series column c holds reference joint SERIES_JOINTS[c]: series_array = reference_order_array[:, TO_SERIES]
TO_SERIES = [JOINTS.index(joint) for joint in SERIES_JOINTS]
RATE_HZ = 100.0
T = np.round(np.arange(301) / RATE_HZ, 6)
SAMPLES = T.size

SPINDLE = "__Spindle.Load__ (left)"
DESCRIBED = ("grip_force", "contact_force", "winding_temp")
UNDESCRIBED = ("contact_force_n", SPINDLE)
CARRIERS: dict[str, tuple[str, ...]] = {
    "target": ("grip_force",),
    "sim": ("grip_force", "contact_force", "winding_temp"),
    "real": ("grip_force", "contact_force", "winding_temp", "contact_force_n", SPINDLE),
}
CHANNEL_NAMES = ("grip_force", "contact_force", "winding_temp", "contact_force_n", SPINDLE)

# <slug>: lowercased, every run outside [a-z0-9] -> "-", leading / trailing "-" stripped (NAVIGATION.md C1)
SLUGS = {
    "grip_force": "grip-force",
    "contact_force": "contact-force",
    "winding_temp": "winding-temp",
    "contact_force_n": "contact-force-n",
    SPINDLE: "spindle-load-left",
}


def undescribed_column(index: int) -> tuple[str, ...]:
    """The accepted spellings of an undescribed channel's column ``index``.

    The contract writes "columns `[0]`, `[1]`, ..." — read here as column labels ``0``, ``1`` (robot_msgs' own
    ``channels/<name>/<index>`` convention); the literal ``[0]`` is accepted too.
    """
    return (str(index), f"[{index}]")


# Each entry: one plot's accepted titles (a tuple of spellings), in column order (NAVIGATION.md C1 "Plot titles").
EXPECTED_PLOT_TITLES: dict[str, list[tuple[str, ...]]] = {
    "grip_force": [("Grip force [N]",)],
    "contact_force": [(f"Contact force, {axis} [N]",) for axis in "xyz"],
    "winding_temp": [(f"Winding temperature, {joint} [°C]",) for joint in JOINTS],  # the reference's joint order
    "contact_force_n": [tuple(f"contact_force_n, {label}" for label in undescribed_column(i)) for i in range(2)],
    SPINDLE: [(SPINDLE,)],  # no unit: no brackets; the name exactly as recorded
}
# One Rerun view per channel, titled "<title> [<unit>]" (no unit: the title alone).
EXPECTED_VIEW_TITLES = {
    "grip_force": "Grip force [N]",
    "contact_force": "Contact force [N]",
    "winding_temp": "Winding temperature [°C]",
    "contact_force_n": "contact_force_n",
    SPINDLE: SPINDLE,
}
# A Rerun entity's <column> part, before path escaping: a 1-D channel's column is "value".
ENTITY_COLUMNS: dict[str, list[tuple[str, ...]]] = {
    "grip_force": [("value",)],
    "contact_force": [("x",), ("y",), ("z",)],
    "winding_temp": [(joint,) for joint in JOINTS],
    "contact_force_n": [undescribed_column(i) for i in range(2)],
    SPINDLE: [("value",)],
}

_OFFSETS = {"target": 0.0, "sim": 1.5, "real": 3.0, "reference": 0.0}


def _phase(t: np.ndarray) -> np.ndarray:
    return 2.0 * np.pi * t / 3.0


def reference_positions(t: np.ndarray = T) -> np.ndarray:
    """(N, 3) rad, in ``JOINTS`` order."""
    phase = _phase(t)
    return np.column_stack([0.6 * (1.0 - np.cos(phase)), 0.4 + 0.3 * np.sin(phase), -0.2 + 0.25 * np.sin(2.0 * phase)])


def measured_positions(lag_s: float, bias: float) -> np.ndarray:
    return reference_positions(T - lag_s) + bias


def channel_values(situation: str, name: str) -> np.ndarray:
    """The channel ``name`` as ``situation`` records it, columns in ``JOINTS`` / ``x y z`` order."""
    offset = _OFFSETS[situation]
    phase = _phase(T)
    if name == "grip_force":
        return 2.0 + offset + np.sin(phase)
    if name == "contact_force":
        return np.column_stack([10.0 + 2.0 * np.sin(phase), -4.0 + np.cos(phase), 25.0 + 3.0 * np.sin(2.0 * phase)]) + offset
    if name == "winding_temp":  # very different per joint, so a column swap cannot hide
        return np.column_stack([40.0 + 2.0 * T, 33.0 + 1.0 * T, 26.0 + 0.5 * T]) + offset
    if name == "contact_force_n":
        return np.column_stack([1.0 + 0.5 * np.sin(phase), -1.0 + 0.5 * np.cos(phase)]) + offset
    if name == SPINDLE:
        return 0.3 + 0.1 * np.sin(3.0 * phase) + offset
    raise KeyError(name)


def current_values(situation: str) -> np.ndarray:
    """(N, 3) A in ``JOINTS`` order: shoulder ~3 A, elbow ~2 A, wrist ~1 A, so a column swap cannot hide."""
    phase = _phase(T)
    scale = 1.0 + 0.1 * _OFFSETS[situation]
    return np.column_stack([3.0 + 0.4 * np.sin(phase), 2.0 + 0.3 * np.cos(phase), 1.0 + 0.2 * np.sin(2.0 * phase)]) * scale


def described_signals(Signal: Callable[..., Any]) -> dict[str, Any]:
    return {
        "grip_force": Signal(title="Grip force", unit="N"),
        "contact_force": Signal(title="Contact force", unit="N", columns=("x", "y", "z")),
        "winding_temp": Signal(title="Winding temperature", unit="°C", per_joint=True),
    }


def channels_comparison(
    Signal: Callable[..., Any] | None,
    *,
    channels: bool = True,
    current: bool = True,
    target_only: bool = False,
    signals: Mapping[str, Any] | None = None,
) -> Comparison:
    """Target + "sim" + "real" on ``JOINTS``.

    ``channels=False`` passes no channel and no ``signals`` at all (today's API); ``target_only`` gives only the target
    a channel (``grip_force``); ``signals`` overrides ``described_signals(Signal)``.
    """
    rng = np.random.default_rng(20261120)
    situations = []
    for name, lag_s in (("sim", 0.006), ("real", 0.022)):
        extra: dict[str, Any] = {}
        if channels and not target_only:
            extra["channels"] = {channel: channel_values(name, channel) for channel in CARRIERS[name]}
        if current:
            extra["current"] = current_values(name)
        q = measured_positions(lag_s, rng.uniform(-0.002, 0.002))
        situations.append(Situation(name=name, title=name.title(), t=T, q=q, tau=0.5 * q + 1.0, **extra))
    target_extra: dict[str, Any] = {}
    if channels:
        target_extra["channels"] = {channel: channel_values("target", channel) for channel in CARRIERS["target"]}
    comparison_extra: dict[str, Any] = {}
    if channels:
        comparison_extra["signals"] = described_signals(Signal) if signals is None else dict(signals)
    return Comparison(
        title="C1 signals beyond the joints",
        name="c1-signals",
        joint_names=list(JOINTS),
        target=Situation(name="target", title="Target", t=T, q=reference_positions(), **target_extra),
        situations=situations,
        **comparison_extra,
    )


# ── the dataset ──────────────────────────────────────────────────────────────

CHANNEL_RUN = "channels run"
PLAIN_RUN = "plain run"
SERIES = "real"
DATASET_CHANNELS = ("current", "winding_temp", "grip_force", "contact_force")


def _reference() -> JointTrajectory:
    return JointTrajectory(t=T, joint_names=JOINTS, positions=reference_positions())


def dataset_channels() -> dict[str, np.ndarray]:
    """"channels run"'s series channels as it records them: per-joint ones in ``SERIES_JOINTS`` order."""
    return {
        "current": current_values(SERIES)[:, TO_SERIES],
        "winding_temp": channel_values(SERIES, "winding_temp")[:, TO_SERIES],
        "grip_force": channel_values(SERIES, "grip_force"),
        "contact_force": channel_values(SERIES, "contact_force"),  # x y z: not joints, so never reordered
    }


def _effort(q: np.ndarray) -> np.ndarray:
    return 0.8 * q + np.array([1.2, 0.6, 0.2])


def channel_runs(*, channels: bool = True) -> list[Run]:
    """"channels run" (series joints in ``SERIES_JOINTS`` order, with channels) and "plain run" (no channels).

    ``channels=False`` drops "channels run"'s channels too: a dataset today's code writes."""
    reference = _reference()
    q = measured_positions(0.012, 0.001)
    reordered = JointTrajectory(
        t=T, joint_names=SERIES_JOINTS, positions=q[:, TO_SERIES], effort=_effort(q)[:, TO_SERIES],
        channels=dataset_channels() if channels else {},
    )  # fmt: skip
    q_plain = measured_positions(0.016, -0.001)
    plain = JointTrajectory(t=T, joint_names=JOINTS, positions=q_plain, effort=_effort(q_plain))
    return [
        Run(name=CHANNEL_RUN, reference=reference, measured={SERIES: reordered}, tags={"target": "reach"}, title="reach"),
        Run(name=PLAIN_RUN, reference=reference, measured={SERIES: plain}, tags={"target": "reach"}, title="reach"),
    ]


BAD_CURRENT = {
    "1-D on three joints": (SAMPLES,),
    "one joint short": (SAMPLES, 2),
    "one joint extra": (SAMPLES, 4),
}
BAD_RUN = "bad current run"


def bad_current_run(shape: tuple[int, ...]) -> Run:
    """One run whose series carries a ``"current"`` channel of ``shape`` (not (N, 3))."""
    q = measured_positions(0.01, 0.0)
    series = JointTrajectory(
        t=T, joint_names=JOINTS, positions=q, channels={"current": np.ones(shape, dtype=float)},
    )  # fmt: skip
    return Run(name=BAD_RUN, reference=_reference(), measured={SERIES: series}, tags={"target": "reach"})
