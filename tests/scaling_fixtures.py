"""Synthetic run comparisons at 1, 3, 6 and 46 joints: the acceptance fixtures of docs/NAVIGATION.md Part B.

Four robot shapes, each with a target, one sim run and three real repeats on smooth, seeded signals:

- ``"1dof"``: a single pivot swinging a 0.45 m link;
- ``"3dof"``: a yaw-pitch-pitch arm reaching out and back;
- ``"6dof"``: a UR-style 6-joint arm;
- ``"bimanual"``: 46 motors in four ``parts`` — Left arm (7), Right arm (7), Left hand (16: thumb 4, index 3,
  middle 3, ring 3, little 3), Right hand (16). ``joint_names`` interleave arm and hand (left arm, left hand,
  right arm, right hand), as a robot's own joint list might, so the parts' order is the caller's, not the joints'.

``tool=True`` gives a tool frame (``fk``) and a box robot in the 3D view; ``torque=True`` gives the torque
breakdown (real runs log commanded + feedforward like moteus, the sim logs feedforward + feedback) with applied
torque and motor current. The numbers are meant to look like a real rig in Zach's report screenshots: joint
errors of a few degrees from a 20-30 ms lag plus a small gain error, a feedback share of the command of roughly
5-40 %. Every build is deterministic for a ``seed``.

Built with ``scaling_comparison(shape, tool=..., torque=...)``; ``write_scaling_report`` writes its HTML report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from traj_compare import Comparison, RobotDisplay, Situation, write_comparison_report

RATE_HZ = 100.0
DURATION_S = 3.0
SHAPES = ("1dof", "3dof", "6dof", "bimanual")
DOF = {"1dof": 1, "3dof": 3, "6dof": 6, "bimanual": 46}
FINGERS = ("thumb", "index", "middle", "ring", "little")
REAL_RUNS = ("real_1", "real_2", "real_3")

_ARM_JOINTS = ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_yaw", "wrist_pitch", "wrist_roll")
_FINGER_JOINTS = {
    "thumb": ("rot", "mcp", "pip", "dip"),
    "index": ("mcp", "pip", "dip"),
    "middle": ("mcp", "pip", "dip"),
    "ring": ("mcp", "pip", "dip"),
    "little": ("mcp", "pip", "dip"),
}


def arm_joints(side: str) -> list[str]:
    """``"l"`` / ``"r"``: that arm's 7 joint names, shoulder to wrist."""
    return [f"{side}_{joint}" for joint in _ARM_JOINTS]


def hand_joints(side: str) -> dict[str, list[str]]:
    """``"l"`` / ``"r"``: that hand's joints, grouped by finger (16 in all)."""
    return {finger: [f"{side}_{finger}_{joint}" for joint in joints] for finger, joints in _FINGER_JOINTS.items()}


def _is_finger(joint: str) -> bool:
    return any(f"_{finger}_" in joint for finger in FINGERS)


def _flat(hand: dict[str, list[str]]) -> list[str]:
    return [joint for joints in hand.values() for joint in joints]


BIMANUAL_PARTS: dict[str, list[str] | dict[str, list[str]]] = {
    "Left arm": arm_joints("l"),
    "Right arm": arm_joints("r"),
    "Left hand": hand_joints("l"),
    "Right hand": hand_joints("r"),
}
# What the part selector and the Rerun nested tabs are labelled (NAVIGATION.md: "<part> · <n> joints").
BIMANUAL_PART_LABELS = ["Left arm · 7 joints", "Right arm · 7 joints", "Left hand · 16 joints", "Right hand · 16 joints"]

JOINT_NAMES: dict[str, list[str]] = {
    "1dof": ["pivot"],
    "3dof": ["base_yaw", "shoulder", "elbow"],
    "6dof": ["base_yaw", "shoulder", "elbow", "wrist_1", "wrist_2", "wrist_3"],
    "bimanual": arm_joints("l") + _flat(hand_joints("l")) + arm_joints("r") + _flat(hand_joints("r")),
}
TITLES = {
    "1dof": "1-DOF pivot sweep",
    "3dof": "3-DOF arm reach",
    "6dof": "6-DOF arm pick",
    "bimanual": "Bimanual 46-motor grasp",
}


# ── kinematics: a serial chain of revolute joints, batched over samples ─────


@dataclass(frozen=True)
class Chain:
    """A serial chain: each joint translates by ``offset`` (from the previous frame) then rotates about ``axis``."""

    base: tuple[float, float, float]
    joints: tuple[tuple[str, str, tuple[float, float, float]], ...]  # (joint name, axis "x" | "y" | "z", offset)
    tool: tuple[float, float, float]


def _rotation(axis: str, angles: np.ndarray) -> np.ndarray:
    cos, sin = np.cos(angles), np.sin(angles)
    zeros, ones = np.zeros_like(angles), np.ones_like(angles)
    rows = {
        "x": [[ones, zeros, zeros], [zeros, cos, -sin], [zeros, sin, cos]],
        "y": [[cos, zeros, sin], [zeros, ones, zeros], [-sin, zeros, cos]],
        "z": [[cos, -sin, zeros], [sin, cos, zeros], [zeros, zeros, ones]],
    }[axis]
    return np.stack([np.stack(row, axis=-1) for row in rows], axis=-2)


def _chain_frames(chain: Chain, joint_index: dict[str, int], q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """World frame after each joint ``(N, J, 4, 4)`` and the tool frame ``(N, 4, 4)``."""

    sample_count = q.shape[0]
    frame = np.tile(np.eye(4), (sample_count, 1, 1))
    frame[:, :3, 3] = chain.base
    frames = []
    for joint, axis, offset in chain.joints:
        step = np.tile(np.eye(4), (sample_count, 1, 1))
        step[:, :3, :3] = _rotation(axis, q[:, joint_index[joint]])
        step[:, :3, 3] = offset
        frame = frame @ step
        frames.append(frame)
    tool = np.tile(np.eye(4), (sample_count, 1, 1))
    tool[:, :3, 3] = chain.tool
    return np.stack(frames, axis=1), frame @ tool


def _chains(shape: str) -> list[Chain]:
    if shape == "1dof":
        return [Chain(base=(0.0, 0.0, 0.0), joints=(("pivot", "z", (0.0, 0.0, 0.30)),), tool=(0.45, 0.0, 0.0))]
    if shape == "3dof":
        return [Chain(base=(0.0, 0.0, 0.0), joints=(
            ("base_yaw", "z", (0.0, 0.0, 0.15)),
            ("shoulder", "y", (0.0, 0.0, 0.20)),
            ("elbow", "y", (0.35, 0.0, 0.0)),
        ), tool=(0.30, 0.0, 0.0))]  # fmt: skip
    if shape == "6dof":
        return [Chain(base=(0.0, 0.0, 0.0), joints=(
            ("base_yaw", "z", (0.0, 0.0, 0.15)),
            ("shoulder", "y", (0.0, 0.0, 0.15)),
            ("elbow", "y", (0.40, 0.0, 0.0)),
            ("wrist_1", "y", (0.35, 0.0, 0.0)),
            ("wrist_2", "z", (0.0, 0.0, -0.09)),
            ("wrist_3", "x", (0.08, 0.0, 0.0)),
        ), tool=(0.10, 0.0, 0.0))]  # fmt: skip
    chains = []
    for side, y in (("l", 0.22), ("r", -0.22)):
        names = arm_joints(side)
        chains.append(Chain(base=(0.0, y, 1.25), joints=(
            (names[0], "y", (0.0, 0.0, 0.0)),
            (names[1], "x", (0.0, 0.0, 0.0)),
            (names[2], "z", (0.0, 0.0, -0.05)),
            (names[3], "y", (0.0, 0.0, -0.28)),
            (names[4], "z", (0.0, 0.0, -0.13)),
            (names[5], "y", (0.0, 0.0, -0.13)),
            (names[6], "x", (0.0, 0.0, 0.0)),
        ), tool=(0.0, 0.0, -0.10)))  # fmt: skip
    return chains


def _box(low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """An axis-aligned box as 12 triangles ``(12, 3, 3)``."""

    corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    triangles = []
    for a, b, c, d in faces:
        triangles += [corners[[a, b, c]], corners[[a, c, d]]]
    return np.asarray(triangles, dtype=np.float32)


def _link_box(offset: tuple[float, float, float], thickness: float) -> np.ndarray:
    """A box from a link's own origin to the next joint (``offset``), ``thickness`` thick."""

    end = np.asarray(offset, dtype=float)
    pad = thickness / 2.0
    return _box(np.minimum(0.0, end) - pad, np.maximum(0.0, end) + pad)


def _robot(shape: str, joint_names: list[str]) -> tuple:
    """``(fk, RobotDisplay, tcp frame name)`` for the shape: the first chain is the tool's."""

    chains = _chains(shape)
    joint_index = {joint: index for index, joint in enumerate(joint_names)}

    def fk(q: np.ndarray) -> np.ndarray:
        return _chain_frames(chains[0], joint_index, np.atleast_2d(q))[1]

    link_names, meshes, colors = [], [], []
    if shape == "bimanual":
        link_names.append("torso")
        meshes.append(_box(np.array([-0.10, -0.16, 0.70]), np.array([0.10, 0.16, 1.28])))
        colors.append("#9a9890")
    for chain in chains:
        offsets = [offset for _, _, offset in chain.joints[1:]] + [chain.tool]
        for (joint, _, _), offset in zip(chain.joints, offsets, strict=True):
            link_names.append(f"{joint}_link")
            meshes.append(_link_box(offset, 0.05 if shape != "bimanual" else 0.06))
            colors.append(None)

    def link_fk(q: np.ndarray) -> np.ndarray:
        q = np.atleast_2d(q)
        frames = [_chain_frames(chain, joint_index, q)[0] for chain in chains]
        if shape == "bimanual":
            frames.insert(0, np.tile(np.eye(4), (q.shape[0], 1, 1, 1)))
        return np.concatenate(frames, axis=1)

    robot = RobotDisplay(link_names=link_names, link_meshes=meshes, link_fk=link_fk, name=TITLES[shape],
                         link_colors=colors)  # fmt: skip
    return fk, robot, ("left palm" if shape == "bimanual" else "TCP")


# ── signals ────────────────────────────────────────────────────────────────


def _min_jerk(fraction: np.ndarray) -> np.ndarray:
    clipped = np.clip(fraction, 0.0, 1.0)
    return clipped**3 * (10.0 - 15.0 * clipped + 6.0 * clipped**2)


def _out_and_back(t: np.ndarray, start: float, rise: float, hold: float) -> np.ndarray:
    """0 → 1 (min-jerk over ``rise`` s from ``start``), held ``hold`` s, then back to 0: starts and ends at rest."""

    return _min_jerk((t - start) / rise) - _min_jerk((t - start - rise - hold) / rise)


def _target_angles(shape: str, joint_names: list[str], t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    columns = []
    for joint in joint_names:
        finger = next((name for name in FINGERS if f"_{name}_" in joint), None)
        if finger is not None:  # a grasp: each finger curls in turn, holds, opens
            stagger = FINGERS.index(finger) * 0.08 + (0.15 if joint.startswith("r_") else 0.0)
            curl = rng.uniform(0.7, 1.1) * (0.6 if joint.endswith(("_rot", "_dip")) else 1.0)
            columns.append(0.05 + curl * _out_and_back(t, 0.5 + stagger, 0.8, 0.5))
            continue
        nominal = rng.uniform(-0.4, 0.4)
        if joint.endswith("elbow"):
            nominal = -1.1 if shape == "bimanual" else 0.9
        reach = rng.uniform(0.35, 0.8) * rng.choice([-1.0, 1.0])
        sway = rng.uniform(0.04, 0.12)
        phase = rng.uniform(0.0, 2.0 * np.pi)
        motion = reach * _out_and_back(t, 0.3, 1.0, 0.5) + sway * np.sin(2.0 * np.pi * t / DURATION_S + phase) * _out_and_back(t, 0.2, 0.6, 1.6)
        columns.append(nominal + motion)
    return np.column_stack(columns)


def _smooth_noise(t: np.ndarray, columns: int, amplitude: float, rng: np.random.Generator) -> np.ndarray:
    """A few slow random sines per column: bounded, smooth drift (not white noise)."""

    noise = np.zeros((t.size, columns))
    for _ in range(3):
        frequency = rng.uniform(0.3, 2.0, columns)
        phase = rng.uniform(0.0, 2.0 * np.pi, columns)
        noise += np.sin(2.0 * np.pi * np.outer(t, frequency) + phase)
    return amplitude * noise / 3.0


def _delayed(t: np.ndarray, angles: np.ndarray, delay_s: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(t - delay_s[column], t, angles[:, column]) for column in range(angles.shape[1])])


def _measured_angles(target: np.ndarray, t: np.ndarray, rng: np.random.Generator, real: bool) -> np.ndarray:
    columns = target.shape[1]
    delay_s = rng.uniform(0.018, 0.032, columns) if real else rng.uniform(0.004, 0.010, columns)
    gain_error = rng.uniform(-0.035, 0.035, columns) if real else rng.uniform(-0.01, 0.01, columns)
    bias = np.radians(rng.uniform(-0.3, 0.3, columns)) if real else np.zeros(columns)
    drift = _smooth_noise(t, columns, np.radians(0.25 if real else 0.05), rng)
    lagged = _delayed(t, target, delay_s)
    return lagged + gain_error * (lagged - target[0]) + bias + drift


def _model_torque(joint_names: list[str], q: np.ndarray, qd: np.ndarray, qdd: np.ndarray) -> np.ndarray:
    """Inverse dynamics of a plausible rig: inertia, gravity, viscous friction per joint (N·m)."""

    columns = []
    for column, joint in enumerate(joint_names):
        if _is_finger(joint):
            inertia, gravity, viscous = 2e-4, 0.02, 0.004
        elif "wrist" in joint:
            inertia, gravity, viscous = 0.01, 0.8, 0.05
        elif joint.endswith(("yaw", "pivot")):
            inertia, gravity, viscous = 0.25, 0.0, 0.3
        else:
            inertia, gravity, viscous = 0.15, 6.0, 0.25
        coulomb = 0.15 * gravity + 0.05
        columns.append(inertia * qdd[:, column] + gravity * np.cos(q[:, column]) + viscous * qd[:, column]
                       + coulomb * np.tanh(qd[:, column] / 0.05))  # fmt: skip
    return np.column_stack(columns)


def _first_order(t: np.ndarray, values: np.ndarray, time_constant_s: float) -> np.ndarray:
    """The drive's current loop as a first-order lag: applied torque trails the command."""

    filtered = np.empty_like(values)
    filtered[0] = values[0]
    alpha = 1.0 - np.exp(-np.diff(t) / time_constant_s)
    for index in range(1, t.size):
        filtered[index] = filtered[index - 1] + alpha[index - 1] * (values[index] - filtered[index - 1])
    return filtered


def _feedback_gains(feedforward: np.ndarray, angle_error: np.ndarray, speed_error: np.ndarray,
                    rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """Per-joint kp, kd tuned so the first real run's feedback supplies 12-35 % of the command."""

    raw = angle_error + 0.08 * speed_error
    wanted = rng.uniform(0.12, 0.35, feedforward.shape[1])
    ff_sum = np.sum(np.abs(feedforward), axis=0)
    fb_sum = np.maximum(np.sum(np.abs(raw), axis=0), 1e-9)
    kp = wanted * ff_sum / ((1.0 - wanted) * fb_sum)
    return kp, 0.08 * kp


def scaling_comparison(shape: str, *, tool: bool = True, torque: bool = True, seed: int = 7) -> Comparison:
    """A target, a sim run and three real repeats of ``shape`` (``SHAPES``), with or without a tool frame / torque."""

    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; one of {SHAPES}")
    rng = np.random.default_rng(seed)
    joint_names = list(JOINT_NAMES[shape])
    t = np.round(np.arange(0.0, DURATION_S + 0.5 / RATE_HZ, 1.0 / RATE_HZ), 9)
    target_q = _target_angles(shape, joint_names, t, rng)
    target_qd = np.gradient(target_q, t, axis=0)
    target_qdd = np.gradient(target_qd, t, axis=0)
    target_tau = _model_torque(joint_names, target_q, target_qd, target_qdd)

    runs = {name: _measured_angles(target_q, t, rng, real=name != "sim") for name in ("sim", *REAL_RUNS)}
    kp = kd = None
    situations = []
    for name, q in runs.items():
        qd = np.gradient(q, t, axis=0)
        torques: dict[str, np.ndarray] = {}
        if torque:
            feedforward = target_tau  # the planner's inverse dynamics, sent as feedforward
            if kp is None:
                kp, kd = _feedback_gains(feedforward, target_q - runs["real_1"], target_qd - np.gradient(runs["real_1"], t, axis=0), rng)
            feedback = kp * (target_q - q) + kd * (target_qd - qd)
            commanded = feedforward + feedback
            applied = 0.97 * _first_order(t, commanded, 0.006)
            # N·m per A at the joint (geared arm motors; small direct finger drives)
            torque_constant = np.array([0.12 if _is_finger(joint) else 1.3 for joint in joint_names])
            if name == "sim":  # a sim controller exports its two terms; the command is their sum
                torques = {"tau_ff": feedforward, "tau_fb": feedback}
            else:  # moteus: control_torque and feedforward_torque; feedback = their difference
                torques = {"tau_cmd": commanded, "tau_ff": feedforward}
            torques.update(tau=applied, current=applied / torque_constant)
        real = name != "sim"
        situations.append(Situation(
            name=name, title=name.replace("_", " ").title(), t=t, q=q, qd=qd, **torques,
            group="real" if real else "sim", group_title=f"Real ({len(REAL_RUNS)} repeats)" if real else "Sim",
            meta={"rig": "bam-cell-2" if real else "mujoco", "controller": "pd+ff"},
        ))  # fmt: skip

    fk = robot = None
    tcp_frame = "TCP"
    if tool:
        fk, robot, tcp_frame = _robot(shape, joint_names)
    return Comparison(
        title=TITLES[shape],
        name=f"scaling-{shape}",
        joint_names=joint_names,
        target=Situation(name="target", title="Target", t=t, q=target_q, qd=target_qd,
                         tau=target_tau if torque else None),
        situations=situations,
        fk=fk,
        robot=robot,
        tcp_frame=tcp_frame,
        vec_dirs=[("Conveyor", np.array([0.0, 1.0, 0.0]))],
        description=f"Synthetic acceptance fixture: {DOF[shape]} joint(s), target + sim + {len(REAL_RUNS)} real repeats.",
        repeat_groups={"real": list(REAL_RUNS)},
        parts=BIMANUAL_PARTS if shape == "bimanual" else None,
    )  # fmt: skip


def write_scaling_report(shape: str, output: Path, *, tool: bool = True, torque: bool = True, **kwargs) -> Path:
    """``scaling_comparison(shape, ...)`` written as ``<output>/report.html``; returns its path."""

    return write_comparison_report(scaling_comparison(shape, tool=tool, torque=torque), output, **kwargs)
