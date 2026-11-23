"""Derived signals must not invent overshoot at a trajectory's ends (2026-11-23).

Found on the real UR5e pages (Lane E): every page said "joint signals go past a stated limit (... qddd ...)" in red, and
every jerk sample over bam_ruckig's 60 rad/s^3 was sample 0 of a trajectory. numpy.gradient(edge_order=2) uses the
one-sided stencil (-3 f0 + 4 f1 - f2) / 2h at an edge, which overshoots when the slope changes right after the first
sample (a jerk phase that ends between samples, a tool that moves one step and stops). A first-order edge,
(f1 - f0) / h, is the slope the samples actually show. The same stencil computed the tool speed, so both are pinned.
"""

from __future__ import annotations

import math

import numpy as np
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory

from traj_compare.coverage import analyze

H = 0.01  # 100 Hz
JERK = 60.0  # rad/s^3, bam_ruckig's UR5e jerk limit


def test_a_jerk_phase_that_ends_after_the_first_sample_stays_inside_the_jerk_limit():
    samples = 50
    t = np.arange(samples) * H
    # qdd ramps at the full jerk for one sample, then holds: the true jerk is JERK for one step and 0 after.
    accelerations = np.full((samples, 1), JERK * H)
    accelerations[0] = 0.0
    velocities = np.cumsum(accelerations, axis=0) * H
    positions = np.cumsum(velocities, axis=0) * H
    limits = JointLimits(joint_names=("j",), min_position=np.array([-math.pi]), max_position=np.array([math.pi]),
                         max_velocity=np.array([3.0]), max_acceleration=np.array([6.0]),
                         max_jerk=np.array([JERK * 1.05]))
    trajectory = JointTrajectory(t=t, joint_names=("j",), positions=positions, velocities=velocities,
                                 accelerations=accelerations, limits=limits)
    jerk = analyze(trajectory).payload["hist"]["j"]["qddd"]
    assert jerk["outside"] == 0
    assert jerk["max"] <= JERK * 1.0001


def test_a_tool_that_moves_one_step_and_stops_is_not_faster_than_that_step():
    samples = 30
    t = np.arange(samples) * H
    step = 0.01  # m in one sample: 1 m/s, then still
    x = np.full(samples, step)
    x[0] = 0.0
    tool = PoseTrajectory(t=t, positions=np.stack([x, np.zeros(samples), np.zeros(samples)], axis=1),
                          orientations=np.tile([1.0, 0.0, 0.0, 0.0], (samples, 1)))
    joint = JointTrajectory(t=t, joint_names=("j",), positions=np.zeros((samples, 1)))
    xy = analyze(joint, tool=tool).payload["tool"]["projections"]["xy"]
    fastest = max(value for value in xy["max_speed"] if value is not None)
    assert fastest <= 1.0 * 1.0001
