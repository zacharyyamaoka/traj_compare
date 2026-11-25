"""A made-up arm, a target and a run of it that tracks it closely: the target-vs-run Rerun tests' inputs and oracle.

    from target_run_fixture import URDF, JOINTS, target_and_run, tcp, robot, poses

The arm is ``tests/fixtures/target_run_arm.urdf``: a pan about z (0.1 m up), a shoulder about y (0.3 m above it), an
elbow about y (0.25 m above that), a flange 0.2 m out and a tool point 0.05 m past the flange. Its kinematics here are
closed form, written from the URDF by hand, so the tests never check robot_msgs' forward kinematics against itself.

``robot()`` and ``poses()`` are import specs for ``write_dataset_report(robot="target_run_fixture:robot",
poses="target_run_fixture:poses")``: the RobotDisplay carries the same arm as its URDF.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from robot_msgs.geometry.rotations import quat_from_matrix
from robot_msgs.std import Header
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory

URDF = Path(__file__).resolve().parent / "fixtures" / "target_run_arm.urdf"
JOINTS = ("pan", "shoulder", "elbow")
TOOL_PAST_FLANGE = 0.05  # m along the flange's z


def _ry(angle: np.ndarray) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    out = np.zeros(angle.shape + (3, 3))
    out[..., 0, 0], out[..., 0, 2], out[..., 1, 1], out[..., 2, 0], out[..., 2, 2] = c, s, 1.0, -s, c
    return out


def _rz(angle: np.ndarray) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    out = np.zeros(angle.shape + (3, 3))
    out[..., 0, 0], out[..., 0, 1], out[..., 1, 0], out[..., 1, 1], out[..., 2, 2] = c, -s, s, c, 1.0
    return out


def link_poses(q: np.ndarray) -> np.ndarray:
    """(N, 4, 4, 4): the poses of l1, l2, l3 and the tool point, closed form."""
    q = np.atleast_2d(np.asarray(q, dtype=np.float64))
    pan, shoulder, elbow = q[:, 0], q[:, 1], q[:, 2]
    yaw = _rz(pan)
    r1, r2, r3 = yaw, yaw @ _ry(shoulder), yaw @ _ry(shoulder + elbow)
    p1 = np.tile([0.0, 0.0, 0.1], (len(q), 1))
    p2 = p1 + r1 @ np.array([0.0, 0.0, 0.3])
    p3 = p2 + r2 @ np.array([0.0, 0.0, 0.25])
    p4 = p3 + r3 @ np.array([0.0, 0.0, 0.2 + TOOL_PAST_FLANGE])
    out = np.tile(np.eye(4), (len(q), 4, 1, 1))
    for index, (rotation, position) in enumerate(((r1, p1), (r2, p2), (r3, p3), (r3, p4))):
        out[:, index, :3, :3], out[:, index, :3, 3] = rotation, position
    return out


def tcp(q: np.ndarray) -> np.ndarray:
    """(N, 3): the tool point, 0.05 m past the flange."""
    return link_poses(q)[:, 3, :3, 3]


def _limits() -> JointLimits:
    return JointLimits(joint_names=JOINTS, min_position=[-3.1, -2.0, -2.5], max_position=[3.1, 2.0, 2.5],
                       max_velocity=[3.0, 3.0, 4.0], max_acceleration=[20.0, 20.0, 30.0])


def target_and_run(start_late_s: float = 0.0, samples: int = 201) -> tuple[JointTrajectory, JointTrajectory]:
    """A rest-to-rest target over 2 s, and a run that follows it a fraction of a degree off (elbow worst, mid-move).
    ``start_late_s``: the run's clock starts that much after the target's (its header stamp), samples alike."""
    t = np.linspace(0.0, 2.0, samples)
    s = 0.5 - 0.5 * np.cos(np.pi * t / 2.0)
    target_q = np.stack([0.2 + 1.2 * s, -0.3 + 0.8 * s, 0.9 - 1.1 * s], 1)
    bump = np.sin(np.pi * t / 2.0) ** 2  # zero at both ends
    deviation = np.radians(np.stack([0.05 * bump, -0.15 * bump, 0.4 * bump * np.sin(2.0 * t)], 1))
    target = JointTrajectory(t=t, joint_names=JOINTS, positions=target_q, limits=_limits()).with_derivatives()
    # start_late_s: the same samples of the motion, stamped that much later (the run lags the target by it)
    run = JointTrajectory(t=t, joint_names=JOINTS, positions=target_q + deviation, limits=_limits(),
                          header=Header(stamp=start_late_s)).with_derivatives()
    return target, run


def well_tracked(peak_deg: float = 0.04, samples: int = 201) -> tuple[JointTrajectory, JointTrajectory]:
    """A long rest-to-rest target (the tool sweeps a path ~0.6 m across) and a run a few hundredths of a degree off it,
    its error along the joint direction that moves the tool point least (the closed form's smallest singular vector):
    joint errors that cancel at the tool, as a well-tuned controller leaves them (the UR5e sim run ctc_tuned_v2 r0 on
    workspace-dev-029, 2026-11-25: joints ≤ 0.04°, the tool 0.10 mm off). ``peak_deg`` bounds every joint's error."""
    t = np.linspace(0.0, 2.0, samples)
    s = 0.5 - 0.5 * np.cos(np.pi * t / 2.0)
    target_q = np.stack([-0.8 + 2.0 * s, 0.3 + 0.8 * s, 0.9 - 1.2 * s], 1)  # reaching out, pan sweeping
    step = 1e-6
    directions, previous = [], None
    for q in target_q:
        jacobian = np.stack([(tcp(q + step * e) - tcp(q - step * e))[0] / (2 * step) for e in np.eye(3)], 1)
        least = np.linalg.svd(jacobian)[2][-1]
        if previous is not None and least @ previous < 0:
            least = -least  # one continuous direction, not a sign that flips sample to sample
        directions.append(least)
        previous = least
    bump = np.sin(np.pi * t / 2.0) ** 2  # zero at both ends
    deviation = np.radians(peak_deg) * bump[:, None] * np.asarray(directions)  # a unit vector: no joint above peak_deg
    target = JointTrajectory(t=t, joint_names=JOINTS, positions=target_q, limits=_limits()).with_derivatives()
    run = JointTrajectory(t=t, joint_names=JOINTS, positions=target_q + deviation, limits=_limits()).with_derivatives()
    return target, run


def tool_of(trajectory: JointTrajectory) -> PoseTrajectory:
    """The tool point's PoseTrajectory in the URDF's root link frame (frame_id empty), on the trajectory's own clock."""
    poses = link_poses(trajectory.positions)
    return PoseTrajectory(t=trajectory.t, positions=poses[:, 3, :3, 3], orientations=quat_from_matrix(poses[:, 3, :3, :3]),
                          header=Header(stamp=trajectory.header.stamp), child_frame_id="tool")


def poses(trajectory: JointTrajectory) -> PoseTrajectory:
    """write_dataset_report's ``poses`` spec."""
    return tool_of(trajectory)


def robot():
    """write_dataset_report's ``robot`` spec: the arm's links as small boxes, posed in closed form, with its URDF."""
    from traj_compare import RobotDisplay

    def box(size: tuple[float, float, float]) -> np.ndarray:
        x, y, z = (0.5 * value for value in size)
        corners = np.array([[sx * x, sy * y, sz * z] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
        faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6),
                 (0, 6, 4), (1, 5, 7), (1, 7, 3)]
        return corners[np.array(faces)]

    def fk(q: np.ndarray) -> np.ndarray:
        return link_poses(q)

    meshes = [box((0.06, 0.06, 0.3)), box((0.05, 0.05, 0.25)), box((0.04, 0.04, 0.2)), box((0.02, 0.02, 0.02))]
    return RobotDisplay(link_names=["l1", "l2", "l3", "tool"], link_meshes=meshes, link_fk=fk, name="made-up arm",
                        urdf=str(URDF))


def nice(value: float) -> bool:
    """Is ``value`` a 1-2-5 number (1, 2, 5, 10, 20, 50, ...)?"""
    exponent = 10.0 ** math.floor(math.log10(value))
    return any(math.isclose(value, m * exponent) for m in (1.0, 2.0, 5.0))
