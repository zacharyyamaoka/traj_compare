"""Synthetic runs the doc snippets are executed against (build_site.py --check runs every snippet).

Not shown on the site. A 6-joint arm (UR5e joint names) with a toy forward kinematics: the TCP moves
along the belt (+Y) with joint 2, so the conveyor examples read naturally. Three runs of one plan:

- target: the plan, 100 Hz;
- sim: 12 ms late, 100 Hz;
- real: 35 ms late, a 0.6 mrad shoulder bias, recorded at 125 Hz and starting 0.2 s after the plan
  starts (so `coverage` < 1), ending 0.3 s after it ends (so some samples are `dropped`).
"""

from __future__ import annotations

import numpy as np

JOINTS = (
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
)
BELT = np.array([0.0, 1.0, 0.0])  # the conveyor runs along world +Y
BELT_SPEED = 0.35  # m/s


def plan(t: np.ndarray) -> np.ndarray:
    """Rest, a smooth sweep, rest; joint 2 (elbow) carries the TCP along the belt."""
    phase = np.clip((np.asarray(t) - 0.3) / 2.4, 0.0, 1.0)
    s = 0.5 - 0.5 * np.cos(np.pi * phase)
    return np.column_stack(
        [0.20 * s, -0.10 * s, 1.20 * s, 0.15 * np.sin(np.pi * s), 0.05 * s, 0.30 * s]
    )


def fk(q: np.ndarray) -> np.ndarray:
    """(N, 6) -> (N, 4, 4) toy TCP poses: position from joints 0-2, yaw / pitch from 3-4."""
    q = np.atleast_2d(q)
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, 0, 3] = 0.45 + 0.10 * q[:, 0]
    poses[:, 1, 3] = -0.20 + 0.35 * q[:, 2]
    poses[:, 2, 3] = 0.25 + 0.08 * q[:, 1]
    yaw, pitch = q[:, 3], q[:, 4]
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    poses[:, 0, 0], poses[:, 0, 1], poses[:, 0, 2] = cy * cp, -sy, cy * sp
    poses[:, 1, 0], poses[:, 1, 1], poses[:, 1, 2] = sy * cp, cy, sy * sp
    poses[:, 2, 0], poses[:, 2, 1], poses[:, 2, 2] = -sp, 0.0, cp
    return poses


t = np.linspace(0.0, 3.0, 301)
q_target = plan(t)
t_sim = t.copy()
q_sim = plan(t_sim - 0.012)
t_real = np.arange(0.2, 3.3, 1.0 / 125.0)
q_real = plan(t_real - 0.035) + np.array([0.0, 0.0006, 0.0, 0.0, 0.0, 0.0])
# three repeats of the real run for the ISO 9283 example: same lag, small run-to-run noise
rng = np.random.default_rng(9283)
real_repeats = [
    plan(t - 0.035) + rng.normal(0.0, 0.0003, size=(len(t), 6)) + np.array([0.0, 0.0006, 0, 0, 0, 0])
    for _ in range(3)
]
