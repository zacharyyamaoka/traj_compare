"""traj_compare's resampling against data-ui's difference(a, b) fixture (gallery/robotics CONTRACT section 5).

The fixture is a numpy/scipy oracle copied verbatim into tests/fixtures/data_ui_difference (PROVENANCE.md there): two
trajectories of one run, a = ``real`` and b = ``target``, and the rows ``difference(a, b)`` must return, judged by the
fixture's own checker (1e-9 in a column's unit, 1e-4 mrad for err_rot_mrad, null as null). traj_compare has no table-level
``difference``; the adapters below drive the interpolation the analysis really uses (``_resample_columns``,
``_slerp_resample``, ``rotation_angles_between``) and write the contract's rows. A resampled row is NaN where b has
no sample to stand on, and NaN is "no row".
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from traj_compare.analysis import _quat_to_mat, _resample_columns, _slerp_resample
from traj_compare.rotations import rotation_angles_between

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "data_ui_difference"))
import fixture  # noqa: E402  (data-ui's stdlib checker, in the fixture directory)

POSE_KEY = ("run", "body", "frame")
SAMPLE_KEY = ("run", "device")


def _groups(rows: list[dict], key: tuple[str, ...]) -> dict[tuple, list[int]]:
    groups: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(tuple(row[name] for name in key), []).append(index)
    return groups


def _column(rows: list[dict], indices: list[int], name: str) -> np.ndarray:
    return np.array([np.nan if rows[i].get(name) is None else rows[i][name] for i in indices], float)


def _number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _paired(a_rows: list[dict], b_rows: list[dict], key: tuple[str, ...]):
    """(a indices, b indices, a's t, b's t, inside) per key both have; inside = a's samples in b's span, from the resampler."""
    b_groups = _groups(b_rows, key)
    for group, a_indices in _groups(a_rows, key).items():
        if group not in b_groups:
            continue  # a body b writes in another frame, a device or a run only a has: no rows, frames never mixed
        b_indices = b_groups[group]
        t_a, t_b = _column(a_rows, a_indices, "t"), _column(b_rows, b_indices, "t")
        inside = np.isfinite(_resample_columns(t_b, t_b[:, None], t_a)[:, 0])
        yield a_indices, b_indices, t_a, t_b, inside


def difference_samples(a_rows: list[dict], b_rows: list[dict]) -> list[dict]:
    errors = {"e_q_mrad": ("q_deg", np.pi / 180 * 1000), "e_q_mm": ("q_mm", 1.0), "e_qd_deg_s": ("qd_deg_s", 1.0),
              "e_qd_mm_s": ("qd_mm_s", 1.0), "e_tau_nm": ("tau_nm", 1.0)}
    out: dict[int, dict] = {}
    for a_indices, b_indices, t_a, t_b, inside in _paired(a_rows, b_rows, SAMPLE_KEY):
        channels = {column: _column(b_rows, b_indices, name)[:, None] for column, (name, _) in errors.items()}
        for row, index in enumerate(a_indices):
            if not inside[row]:
                continue
            a = a_rows[index]
            out[index] = {"t": a["t"], "run": a["run"], "situation": a["situation"], "source": a["source"], "reference": b_rows[0]["situation"],
                          "device": a["device"]}
        resampled = {column: _resample_columns(t_b, values, t_a)[:, 0] for column, values in channels.items()}
        for row, index in enumerate(a_indices):
            if inside[row]:
                for column, (name, scale) in errors.items():
                    out[index][column] = _number((resampled[column][row] - _column(a_rows, [index], name)[0]) * scale)
    return [out[index] for index in sorted(out)]


def difference_poses(a_rows: list[dict], b_rows: list[dict]) -> list[dict]:
    axes = ("x_mm", "y_mm", "z_mm")
    quats = ("quat_w", "quat_x", "quat_y", "quat_z")
    out: dict[int, dict] = {}
    for a_indices, b_indices, t_a, t_b, inside in _paired(a_rows, b_rows, POSE_KEY):
        b_position = np.stack([_column(b_rows, b_indices, name) for name in axes], axis=1)
        b_quat = np.stack([_column(b_rows, b_indices, name) for name in quats], axis=1)
        b_quat /= np.linalg.norm(b_quat, axis=1, keepdims=True)
        position = _resample_columns(t_b, b_position, t_a)
        ref_quat = _slerp_resample(t_b, b_quat, t_a)
        ref_quat[ref_quat[:, 0] < 0.0] *= -1.0  # canonical sign: w >= 0
        a_position = np.stack([_column(a_rows, a_indices, name) for name in axes], axis=1)
        a_quat = np.stack([_column(a_rows, a_indices, name) for name in quats], axis=1)
        a_unit = a_quat / np.linalg.norm(a_quat, axis=1, keepdims=True)
        angle = rotation_angles_between(_quat_to_mat(a_unit), _quat_to_mat(np.nan_to_num(ref_quat)))
        for row, index in enumerate(a_indices):
            if not inside[row]:
                continue
            a = a_rows[index]
            out[index] = {
                "t": a["t"], "run": a["run"], "situation": a["situation"], "source": a["source"], "reference": b_rows[0]["situation"],
                "body": a["body"], "frame": a["frame"],
                **{name: a[name] for name in axes}, **{f"ref_{name}": _number(position[row, i]) for i, name in enumerate(axes)},
                "err_mm": _number(np.linalg.norm(position[row] - a_position[row])),
                **{name: a[name] for name in quats}, **{f"ref_{name}": _number(ref_quat[row, i]) for i, name in enumerate(quats)},
                "err_rot_mrad": _number(1000.0 * angle[row]),
            }
    return [out[index] for index in sorted(out)]


def test_resampling_matches_the_data_ui_difference_fixture():
    problems = fixture.check_difference(poses=difference_poses, samples=difference_samples)
    assert problems == [], "\n".join(problems)


def test_the_fixture_has_rows_outside_the_targets_span_that_must_not_appear():
    a_rows, b_rows = fixture.trajectories("poses")
    tool0_a = [row["t"] for row in a_rows if row["body"] == "tool0" and row["run"] == "fixture/r1"]
    tool0_b = [row["t"] for row in b_rows if row["body"] == "tool0"]
    outside = [t for t in tool0_a if not tool0_b[0] <= t <= tool0_b[-1]]
    assert outside and len(difference_poses(a_rows, b_rows)) == len(fixture.rows("diff_poses"))


def test_resamplers_never_extrapolate_past_the_target_span():
    t = np.array([0.0, 1.0, 2.0])
    values = np.array([[0.0], [10.0], [20.0]])
    quats = np.tile([1.0, 0.0, 0.0, 0.0], (3, 1))
    grid = np.array([-0.5, 0.0, 0.5, 2.0, 2.5])
    linear = _resample_columns(t, values, grid)[:, 0]
    rotated = _slerp_resample(t, quats, grid)
    np.testing.assert_array_equal(np.isnan(linear), [True, False, False, False, True])
    np.testing.assert_array_equal(np.isnan(rotated[:, 0]), [True, False, False, False, True])
    assert linear[1] == 0.0 and linear[3] == 20.0 and linear[2] == 5.0  # both ends included, exact at b's own samples


def test_a_run_longer_than_its_target_has_no_error_rows_past_the_targets_end():
    from traj_compare.analysis import analyze_comparison
    from traj_compare.model import Comparison, Situation

    def fk(q: np.ndarray) -> np.ndarray:
        poses = np.tile(np.eye(4), (len(q), 1, 1))
        poses[:, :2, 3] = q
        return poses

    t_target, t_long = np.linspace(0.0, 1.0, 101), np.linspace(0.0, 2.0, 201)
    target = Situation(name="target", t=t_target, q=np.column_stack([t_target, 0 * t_target]))
    longer = Situation(name="long", t=t_long, q=np.column_stack([t_long + 0.1, 0 * t_long]))
    payload = analyze_comparison(Comparison(title="span", joint_names=["jx", "jy"], target=target, situations=[longer], fk=fk))
    entry = payload["situations"][1]
    past = t_long > 1.0
    assert all(value is None for value in np.array(entry["three"]["tp"], dtype=object)[past][:, 0])
    assert all(value is None for value in np.array(entry["three"]["tquat"], dtype=object)[past][:, 0])
    assert entry["three"]["tp"][100][0] == 1.0  # the target's last sample is inside the span, both ends included
    assert payload["statistics"]["rows"][0]["cells"][1] == "2.865°"  # mean of jx 0.1 rad and jy 0 over the rows with a target
