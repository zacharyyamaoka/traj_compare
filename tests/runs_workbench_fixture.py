"""Two small dataset sites for the runs workbench's acceptance tests (tests/test_runs_workbench*.py, 2026-11-24).

The shape of the bench's four sites in miniature, so every rule V2 ("Two viewers, the filter carried",
docs/proposals/tensorboard-2026-11-24/v2) depends on has a case:

- **Arm cell** (2 joints, a tool from ``dataset_fixture_fk:tool_xy``, a ``Sweep`` over ``speed_fraction``): three targets
  (reach-01 at 0.5 x and 1 x, dataset reach-v1, split dev; swing-02 at 1 x, dataset swing-v1, split holdout), two
  configs (``pd``, ``ff``), two repeats each, one ``sim`` series: 12 lines, each with a torque breakdown.
- **Pendulum** (1 joint, no tool, NO sweep): two targets (swing-01 at 1 x in swing-v1, hold-01 at 0.5 x in hold-v1), one
  config (``pd``), two repeats, ``sim`` and ``real`` series: 8 lines. Its runs carry the same KPI tags as the arm's, so a
  site without a sweep of its own still gets its KPIs and its speed from the run tags.

Both sites have a dataset called ``swing-v1``: on two deployments that is two datasets, never one.
KPI tags are a formula of (config, speed, repeat, series), so a test can say what each row must hold.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Metric, Run, Sweep, write_dataset_report

ARM = "Arm cell"
PENDULUM = "Pendulum"
ARM_JOINTS = ("shoulder", "elbow")
PENDULUM_JOINTS = ("pivot",)
SWEEP = Sweep(x="speed_fraction", y="{series}_tcp_rms_mm", facet_by=("dataset", "split"), x_label="speed",
              y_label="tool RMS", unit="mm", metrics=(Metric("{series}_energy_j", "energy per task", "J"),))

# (target, dataset, split, speed_fraction, kind)
ARM_TARGETS = (
    ("reach-01 · 0.5x", "reach-v1", "dev", 0.5, "line"),
    ("reach-01 · 1x", "reach-v1", "dev", 1.0, "line"),
    ("swing-02 · 1x", "swing-v1", "holdout", 1.0, "arc"),
)
PENDULUM_TARGETS = (
    ("swing-01 · 1x", "swing-v1", "dev", 1.0, "arc"),
    ("hold-01 · 0.5x", "hold-v1", "dev", 0.5, "hold"),
)
ARM_CONFIGS = ("pd", "ff")
REPEATS = (0, 1)


def tcp_rms_mm(config: str, speed: float, repeat: int, series: str) -> float:
    """The KPI tag each run carries: ff tracks 4x better than pd, faster is worse, real 3x worse than sim."""
    base = {"pd": 2.0, "ff": 0.5}[config] * (0.5 + speed) * (1.0 + 0.1 * repeat)
    return round(base * (3.0 if series == "real" else 1.0), 4)


def energy_j(config: str, speed: float, repeat: int, series: str) -> float:
    return round({"pd": 10.0, "ff": 8.0}[config] * speed + repeat + (1.0 if series == "real" else 0.0), 4)


def _shape(t: np.ndarray, joints: int, amplitude: float) -> np.ndarray:
    phase = np.clip(t / t[-1], 0.0, 1.0)
    s = 0.5 - 0.5 * np.cos(np.pi * phase)
    return np.column_stack([amplitude * s * (1.0 - 0.3 * j) for j in range(joints)])


def _trajectory(t: np.ndarray, joints: tuple[str, ...], positions: np.ndarray) -> JointTrajectory:
    return JointTrajectory(t=t, joint_names=joints, positions=positions)


def _runs(targets, configs, joints, series_names, *, torques: bool) -> list[Run]:
    rng = np.random.default_rng(20261124)
    runs = []
    for target, dataset, split, speed, kind in targets:
        duration = 1.0 / speed
        t = np.round(np.linspace(0.0, duration, int(round(duration * 100)) + 1), 6)
        reference = _trajectory(t, joints, _shape(t, len(joints), 0.8))
        for config in configs:
            for repeat in REPEATS:
                scale = {"pd": 1.0, "ff": 0.25}[config] * (1.0 + 0.1 * repeat)
                measured = {}
                for series in series_names:
                    lag = 0.01 * scale * (3.0 if series == "real" else 1.0)
                    noise = 0.0005 * rng.standard_normal((len(t), len(joints)))
                    measured[series] = _trajectory(t, joints, _shape(np.clip(t - lag, 0.0, None), len(joints), 0.8) + noise)
                tags = {"target": target, "controller": config, "dataset": dataset, "split": split,
                        "speed_fraction": speed, "repeat": repeat, "kind": kind}
                for series in series_names:
                    tags[f"{series}_tcp_rms_mm"] = tcp_rms_mm(config, speed, repeat, series)
                    tags[f"{series}_energy_j"] = energy_j(config, speed, repeat, series)
                breakdown = {}
                if torques:
                    n = len(t)
                    breakdown = {series: {"tau_cmd": np.ones((n, len(joints))), "tau_ff": 0.8 * np.ones((n, len(joints)))}
                                 for series in series_names}
                runs.append(Run(name=f"{target} · {config} · r{repeat}", reference=reference, measured=measured, tags=tags,
                                torques=breakdown))
    return runs


def arm_runs() -> list[Run]:
    return _runs(ARM_TARGETS, ARM_CONFIGS, ARM_JOINTS, ("sim",), torques=True)


def pendulum_runs() -> list[Run]:
    return _runs(PENDULUM_TARGETS, ("pd",), PENDULUM_JOINTS, ("sim", "real"), torques=False)


def write_sites(root: Path) -> dict[str, Path]:
    """Both sites under ``root`` (``root/arm``, ``root/pendulum``); {deployment title: site dir}."""
    arm = root / "arm"
    pendulum = root / "pendulum"
    write_dataset_report(arm_runs(), arm, title="Arm cell (sim)", target_by="target", config_by="controller",
                         poses="dataset_fixture_fk:tool_xy", sweep=SWEEP, rows=())
    write_dataset_report(pendulum_runs(), pendulum, title="Pendulum (sim + real)", target_by="target",
                         config_by="controller", rows=())
    return {ARM: arm, PENDULUM: pendulum}
