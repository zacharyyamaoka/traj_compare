"""Rotation helpers on stacked homogeneous transforms — numpy only.

Everything here is vectorized over a leading batch axis: matrices are
``(N, 3, 3)`` (or ``(N, 4, 4)`` homogeneous, from which ``[:3, :3]`` is
taken by the callers), quaternions are ``(N, 4)`` in ``[w, x, y, z]`` order.

RPY convention: extrinsic x-y-z (fixed world axes), i.e.
``R = Rz(yaw) @ Ry(pitch) @ Rx(roll)`` — the classic roll/pitch/yaw used by
the archived BAM matrix tooling. Tested against scipy's ``as_euler("xyz")``.
"""

from __future__ import annotations

import numpy as np


def mat_to_quat(rotations: np.ndarray) -> np.ndarray:
    """Stacked ``(N, 3, 3)`` rotation matrices → ``(N, 4)`` unit quaternions [w,x,y,z].

    Uses the largest-diagonal (Shepperd) branch per row so it is stable for
    all orientations, including angles near pi.
    """

    rot = np.asarray(rotations, dtype=float)
    single = rot.ndim == 2
    if single:
        rot = rot[None]

    m00, m01, m02 = rot[:, 0, 0], rot[:, 0, 1], rot[:, 0, 2]
    m10, m11, m12 = rot[:, 1, 0], rot[:, 1, 1], rot[:, 1, 2]
    m20, m21, m22 = rot[:, 2, 0], rot[:, 2, 1], rot[:, 2, 2]

    # Four candidate formulations, each numerically good in its own region.
    quats = np.empty((rot.shape[0], 4, 4))
    trace = m00 + m11 + m22
    quats[:, 0] = np.stack([1.0 + trace, m21 - m12, m02 - m20, m10 - m01], axis=1)
    quats[:, 1] = np.stack([m21 - m12, 1.0 + m00 - m11 - m22, m01 + m10, m02 + m20], axis=1)
    quats[:, 2] = np.stack([m02 - m20, m01 + m10, 1.0 - m00 + m11 - m22, m12 + m21], axis=1)
    quats[:, 3] = np.stack([m10 - m01, m02 + m20, m12 + m21, 1.0 - m00 - m11 + m22], axis=1)

    diagonals = np.stack([trace, m00, m11, m22], axis=1)
    choice = np.argmax(diagonals, axis=1)
    picked = quats[np.arange(rot.shape[0]), choice]
    picked /= np.linalg.norm(picked, axis=1, keepdims=True)
    # Canonical sign: w >= 0 keeps traces continuous enough for plotting.
    picked[picked[:, 0] < 0.0] *= -1.0
    return picked[0] if single else picked


def mat_to_rpy(rotations: np.ndarray) -> np.ndarray:
    """Stacked rotations → ``(N, 3)`` [roll, pitch, yaw], extrinsic x-y-z."""

    rot = np.asarray(rotations, dtype=float)
    single = rot.ndim == 2
    if single:
        rot = rot[None]

    pitch = np.arcsin(np.clip(-rot[:, 2, 0], -1.0, 1.0))
    roll = np.arctan2(rot[:, 2, 1], rot[:, 2, 2])
    yaw = np.arctan2(rot[:, 1, 0], rot[:, 0, 0])

    # Gimbal lock (|pitch| = pi/2): roll/yaw are degenerate; put it all in yaw.
    locked = np.abs(np.abs(rot[:, 2, 0]) - 1.0) < 1e-9
    if np.any(locked):
        sign = -np.sign(rot[locked, 2, 0])
        roll[locked] = 0.0
        yaw[locked] = np.arctan2(sign * rot[locked, 0, 1], rot[locked, 1, 1]) * sign

    rpy = np.stack([roll, pitch, yaw], axis=1)
    return rpy[0] if single else rpy


def rotation_angles_between(rotations_a: np.ndarray, rotations_b: np.ndarray) -> np.ndarray:
    """Geodesic angle of ``a_i^T b_i`` per row, in radians (always >= 0)."""

    a = np.asarray(rotations_a, dtype=float)
    b = np.asarray(rotations_b, dtype=float)
    relative_trace = np.einsum("nij,nij->n", a, b)
    return np.arccos(np.clip((relative_trace - 1.0) / 2.0, -1.0, 1.0))


def successive_rotation_angles(rotations: np.ndarray) -> np.ndarray:
    """Angles between consecutive rotations of a pose sequence, ``(N-1,)``."""

    rot = np.asarray(rotations, dtype=float)
    return rotation_angles_between(rot[:-1], rot[1:])


def unwrap_rpy(rpy: np.ndarray) -> np.ndarray:
    """Unwrap each RPY column along time so plotted angles stay continuous."""

    return np.unwrap(np.asarray(rpy, dtype=float), axis=0)


def align_unwrapped(angles: np.ndarray, reference_start: np.ndarray) -> np.ndarray:
    """Shift unwrapped angle columns by 2*pi*k toward a reference's first sample.

    After independent unwrapping, two situations describing the same motion can
    sit on branches 2*pi apart; this puts them on the reference's branch so the
    comparison plots overlay.
    """

    shifted = np.array(angles, dtype=float)
    turns = np.round((np.asarray(reference_start, dtype=float) - shifted[0]) / (2.0 * np.pi))
    return shifted + 2.0 * np.pi * turns
