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


def rotation_vectors_between(rotations: np.ndarray, references: np.ndarray) -> np.ndarray:
    """World-frame rotation vector taking ``references_i`` to ``rotations_i``, ``(N, 3)`` rad.

    It is the log map of ``R_err = rotations_i @ references_i^T``, so its norm
    equals :func:`rotation_angles_between` and its components are the rx / ry /
    rz error about the fixed world axes. WHY not a difference of RPY angles:
    Euler differences couple through pitch and jump at gimbal lock, while this
    is the actual rotation you would have to apply. Tested against scipy's
    ``as_rotvec``.
    """

    a = np.asarray(rotations, dtype=float)
    b = np.asarray(references, dtype=float)
    err = a @ np.swapaxes(b, -1, -2)
    skew = np.stack(
        [err[:, 2, 1] - err[:, 1, 2], err[:, 0, 2] - err[:, 2, 0], err[:, 1, 0] - err[:, 0, 1]],
        axis=1,
    )
    sin_angle = np.linalg.norm(skew, axis=1) / 2.0
    cos_angle = (np.einsum("nii->n", err) - 1.0) / 2.0
    # atan2, not arccos of the trace: arccos loses half its digits near 0 and pi.
    angle = np.arctan2(sin_angle, cos_angle)
    out = np.full_like(skew, np.nan)  # a row with no reference pose has no error, not a fake one
    finite = np.isfinite(angle)
    small = finite & (angle < 1e-6)
    # Near zero, vee(R - R^T) / 2 is already the rotation vector to first order.
    out[small] = skew[small] / 2.0
    near_pi = finite & ~small & (cos_angle < 0.0) & (sin_angle < 1e-3)
    regular = finite & ~small & ~near_pi
    out[regular] = skew[regular] / (2.0 * sin_angle[regular, None]) * angle[regular, None]
    for index in np.flatnonzero(near_pi):
        # Near pi the skew part vanishes; recover the axis from the symmetric part,
        # sym(R) = cos(angle) I + (1 - cos(angle)) a a^T.
        outer = ((err[index] + err[index].T) / 2.0 - cos_angle[index] * np.eye(3)) / (
            1.0 - cos_angle[index]
        )
        pivot = int(np.argmax(np.diag(outer)))
        axis = outer[:, pivot] / np.sqrt(max(outer[pivot, pivot], 1e-300))
        if np.dot(axis, skew[index]) < 0.0:
            axis = -axis
        out[index] = axis / np.linalg.norm(axis) * angle[index]
    return out


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
