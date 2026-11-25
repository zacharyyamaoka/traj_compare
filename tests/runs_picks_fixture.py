"""A third, small site for the runs workbench's two picks (tests/test_runs_workbench_picks*.py, 2026-11-25): the Overview
"Headline tiles → drill" (O3 of docs/proposals/v2-overview-2026-11-24/) and the tab "Does sim match real?" (T1 of
docs/proposals/v2-tabs-2026-11-24/), on top of runs_workbench_fixture's Arm cell (sim only) and Pendulum (sim + real).

**Rig** (2 joints, a tool from ``dataset_fixture_fk:tool_xy``, so traj_compare computes a tool RMS for every line): two
targets (lift-01 at 0.5 x, dataset lift-v1 · dev; lift-02 at 1 x, lift-v1 · holdout), two configs, two repeats. Every
rule T1 depends on has a case:

- ``pd`` runs hold three series: ``sim``, ``real`` and ``rehearsal`` (a second prediction of the same motion), so each
  ``pd`` folder is two pairs, one per prediction;
- ``mpc`` runs hold ``sim`` and ``real``; on ``lift-01 · mpc · r0`` real beats its prediction (ratio < 1);
- ``lift-02 · mpc · r1``'s real line carries NO tool RMS tag: the Overview and T1 read traj_compare's own tool RMS for it
  (the V2 rounds' rule: the run's tag, else traj_compare's), and say so;
- ``lift-01 · mpc · r1`` was run on the real robot only: a real line with no prediction is no pair.

KPI tags are a formula of (config, speed, repeat, series), so a test can say what each pair must hold.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from runs_workbench_fixture import ARM_JOINTS, SWEEP, _shape, _trajectory, write_sites
from traj_compare import Run, write_dataset_report

RIG = "Rig"
RIG_TARGETS = (
    ("lift-01 · 0.5x", "lift-v1", "dev", 0.5, "line"),
    ("lift-02 · 1x", "lift-v1", "holdout", 1.0, "line"),
)
RIG_CONFIGS = ("pd", "mpc")
REPEATS = (0, 1)
UNTAGGED = ("lift-02 · 1x", "mpc", 1, "real")  # (target, config, repeat, series) whose tool RMS tag is missing
REAL_ONLY = ("lift-01 · 0.5x", "mpc", 1)  # (target, config, repeat) run on the real robot only


def series_of(target: str, config: str, repeat: int) -> tuple[str, ...]:
    if (target, config, repeat) == REAL_ONLY:
        return ("real",)
    return ("sim", "real", "rehearsal") if config == "pd" else ("sim", "real")


def rig_tcp_rms_mm(target: str, config: str, speed: float, repeat: int, series: str) -> float | None:
    """The tool RMS tag of one line, or None where the run carries none (UNTAGGED)."""
    if (target, config, repeat, series) == UNTAGGED:
        return None
    base = {"pd": 1.5, "mpc": 0.6}[config] * (0.5 + speed) * (1.0 + 0.2 * repeat)
    gain = {"sim": 1.0, "rehearsal": 1.25, "real": 2.0 + 0.5 * repeat}[series]
    if (target, config, repeat) == ("lift-01 · 0.5x", "mpc", 0) and series == "real":
        gain = 0.8  # real beat its prediction here
    return round(base * gain, 4)


def rig_energy_j(config: str, speed: float, repeat: int, series: str) -> float:
    return round({"pd": 12.0, "mpc": 9.0}[config] * speed + 0.5 * repeat + (2.0 if series == "real" else 0.0), 4)


def rig_runs() -> list[Run]:
    rng = np.random.default_rng(20261125)
    runs = []
    for target, dataset, split, speed, kind in RIG_TARGETS:
        duration = 1.0 / speed
        t = np.round(np.linspace(0.0, duration, int(round(duration * 100)) + 1), 6)
        reference = _trajectory(t, ARM_JOINTS, _shape(t, len(ARM_JOINTS), 0.7))
        for config in RIG_CONFIGS:
            for repeat in REPEATS:
                names = series_of(target, config, repeat)
                measured, tags = {}, {"target": target, "controller": config, "dataset": dataset, "split": split,
                                      "speed_fraction": speed, "repeat": repeat, "kind": kind}
                for series in names:
                    lag = 0.008 * (1.0 if config == "pd" else 0.4) * (2.5 if series == "real" else 1.0) * (1 + repeat)
                    noise = 0.0004 * rng.standard_normal((len(t), len(ARM_JOINTS)))
                    shape = _shape(np.clip(t - lag, 0.0, None), len(ARM_JOINTS), 0.7) + noise
                    measured[series] = _trajectory(t, ARM_JOINTS, shape)
                    tcp = rig_tcp_rms_mm(target, config, speed, repeat, series)
                    if tcp is not None:
                        tags[f"{series}_tcp_rms_mm"] = tcp
                    tags[f"{series}_energy_j"] = rig_energy_j(config, speed, repeat, series)
                runs.append(Run(name=f"{target} · {config} · r{repeat}", reference=reference, measured=measured,
                                tags=tags))
    return runs


def write_three_sites(root: Path) -> dict[str, Path]:
    """Arm cell, Pendulum (runs_workbench_fixture) and Rig under ``root``; {deployment title: site dir}."""
    sites = write_sites(root)
    rig = root / "rig"
    write_dataset_report(rig_runs(), rig, title="Rig (sim + real + rehearsal)", target_by="target",
                         config_by="controller", poses="dataset_fixture_fk:tool_xy", sweep=SWEEP, rows=())
    return {**sites, RIG: rig}
