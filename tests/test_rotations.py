"""rotations.py against scipy's Rotation as the oracle."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from traj_compare.rotations import (
    align_unwrapped,
    mat_to_quat,
    mat_to_rpy,
    rotation_angles_between,
    successive_rotation_angles,
    unwrap_rpy,
)

RNG = np.random.default_rng(7)


def random_rotations(count: int) -> np.ndarray:
    return Rotation.random(count, random_state=42).as_matrix()


def test_mat_to_quat_matches_scipy_up_to_sign():
    matrices = random_rotations(500)
    ours = mat_to_quat(matrices)
    theirs = Rotation.from_matrix(matrices).as_quat()  # [x, y, z, w]
    theirs = np.column_stack([theirs[:, 3], theirs[:, 0], theirs[:, 1], theirs[:, 2]])
    theirs[theirs[:, 0] < 0] *= -1.0
    np.testing.assert_allclose(ours, theirs, atol=1e-12)


def test_mat_to_quat_near_pi_rotations():
    axes = RNG.normal(size=(200, 3))
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    angles = np.pi - 10.0 ** RNG.uniform(-9, -3, size=200)
    matrices = Rotation.from_rotvec(axes * angles[:, None]).as_matrix()
    quats = mat_to_quat(matrices)
    rebuilt = Rotation.from_quat(
        np.column_stack([quats[:, 1], quats[:, 2], quats[:, 3], quats[:, 0]])
    ).as_matrix()
    np.testing.assert_allclose(rebuilt, matrices, atol=1e-9)


def test_mat_to_rpy_matches_scipy_extrinsic_xyz():
    matrices = random_rotations(500)
    ours = mat_to_rpy(matrices)
    theirs = Rotation.from_matrix(matrices).as_euler("xyz")
    np.testing.assert_allclose(ours, theirs, atol=1e-10)


def test_mat_to_rpy_single_matrix_shape():
    matrix = random_rotations(1)[0]
    assert mat_to_rpy(matrix).shape == (3,)
    assert mat_to_quat(matrix).shape == (4,)


def test_rotation_angles_between_matches_scipy_magnitude():
    a = random_rotations(300)
    b = random_rotations(300)
    ours = rotation_angles_between(a, b)
    relative = Rotation.from_matrix(a).inv() * Rotation.from_matrix(b)
    theirs = np.linalg.norm(relative.as_rotvec(), axis=1)
    np.testing.assert_allclose(ours, theirs, atol=1e-7)


def test_successive_angles_accumulate_a_constant_rate_spin():
    total_angle = 4.5  # more than pi: accumulation must not alias
    steps = 200
    angles = np.linspace(0.0, total_angle, steps)
    matrices = Rotation.from_euler("z", angles[:, None]).as_matrix()
    accumulated = float(np.sum(successive_rotation_angles(matrices)))
    assert accumulated == pytest.approx(total_angle, abs=1e-9)


def test_unwrap_and_align():
    yaw = np.linspace(0.0, 3.0 * np.pi, 400)
    wrapped = np.arctan2(np.sin(yaw), np.cos(yaw))
    rpy = np.column_stack([np.zeros_like(yaw), np.zeros_like(yaw), wrapped])
    unwrapped = unwrap_rpy(rpy)
    np.testing.assert_allclose(unwrapped[:, 2], yaw, atol=1e-9)

    shifted = unwrapped + np.array([0.0, 0.0, 2.0 * np.pi])
    aligned = align_unwrapped(shifted, unwrapped[0])
    np.testing.assert_allclose(aligned, unwrapped, atol=1e-9)
