"""A planar 2-link tool for test_dataset.py's `poses="dataset_fixture_fk:tool_xy"` import spec."""

import numpy as np
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory


def tool_xy(trajectory: JointTrajectory) -> PoseTrajectory:
    q = trajectory.positions
    yaw = q[:, 0] + q[:, 1]
    positions = np.column_stack(
        [0.3 * np.cos(q[:, 0]) + 0.25 * np.cos(yaw), 0.3 * np.sin(q[:, 0]) + 0.25 * np.sin(yaw), 0 * yaw]
    )
    quats = np.column_stack([0 * yaw, 0 * yaw, np.sin(yaw / 2), np.cos(yaw / 2)])
    return PoseTrajectory(
        t=trajectory.t, positions=positions, orientations=quats, child_frame_id="tool", header=trajectory.header
    )
