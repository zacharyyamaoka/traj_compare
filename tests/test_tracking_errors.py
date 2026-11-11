"""Standard tracking-error fields: per-axis TCP error, lag/cross-track, max/final stats, frame name.

Every error is target - run (robot_msgs.compare's convention); lag is + when the run is behind.

Expected values are built by hand from the geometry of each fixture, and the
rotation-vector math is checked against scipy, so neither comes from the
implementation under test.
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from traj_compare import write_comparison_report
from traj_compare.analysis import analyze_comparison
from traj_compare.model import Comparison, Situation
from traj_compare.rotations import rotation_angles_between, rotation_vectors_between

from test_report import extract_payload

SPEED = 0.2  # m/s along world x
LAG_S = 0.05  # the run follows the same route this late
OFFSET_Y = 0.004  # and this far to the side
YAW_ERROR = 0.1  # rad, constant tool yaw error


def poses_from(positions: np.ndarray, yaw: float = 0.0) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(positions), 1, 1))
    poses[:, :3, :3] = Rotation.from_euler("z", yaw).as_matrix()
    poses[:, :3, 3] = positions
    return poses


def x_route(t: np.ndarray) -> np.ndarray:
    """Rest for 0.5 s, cruise along +x, rest again from 2.5 s."""

    x = SPEED * np.clip(t - 0.5, 0.0, 2.0)
    return np.column_stack([x, np.zeros_like(t), np.zeros_like(t)])


def lagging_comparison(**kwargs) -> Comparison:
    t = np.linspace(0.0, 3.0, 3001)
    target = Situation(name="target", t=t, q=np.zeros((len(t), 1)), poses=poses_from(x_route(t)))
    run_positions = x_route(t - LAG_S) + np.array([0.0, OFFSET_Y, 0.0])
    run = Situation(
        name="run",
        title="Run",
        t=t,
        q=np.zeros((len(t), 1)),
        poses=poses_from(run_positions, yaw=YAW_ERROR),
    )
    return Comparison(
        title="lag", joint_names=["j"], target=target, situations=[run], **kwargs
    )


def run_entry(payload: dict) -> dict:
    return next(entry for entry in payload["situations"] if entry["name"] == "run")


def column(plot: dict, key: str) -> np.ndarray:
    return np.array(plot[key], dtype=float)


def test_rotation_vectors_match_scipy_including_near_zero_and_near_pi():
    rng = np.random.default_rng(3)
    references = Rotation.random(300, random_state=1).as_matrix()
    axes = rng.normal(size=(300, 3))
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    angles = np.concatenate(
        [
            rng.uniform(0.0, np.pi, 100),
            10.0 ** rng.uniform(-10, -5, 100),  # near zero
            np.pi - 10.0 ** rng.uniform(-9, -4, 100),  # near pi
        ]
    )
    expected = axes * angles[:, None]
    rotations = Rotation.from_rotvec(expected).as_matrix() @ references

    ours = rotation_vectors_between(rotations, references)

    regular = angles < np.pi - 1e-3
    np.testing.assert_allclose(ours[regular], expected[regular], atol=1e-7)
    # At pi the axis sign is ambiguous; the rotation itself must still match.
    rebuilt = Rotation.from_rotvec(ours).as_matrix() @ references
    np.testing.assert_allclose(rebuilt, rotations, atol=1e-6)
    np.testing.assert_allclose(
        np.linalg.norm(ours, axis=1), rotation_angles_between(rotations, references), atol=1e-7
    )


def test_rotation_vectors_keep_missing_rows_missing():
    references = np.tile(np.eye(3), (3, 1, 1))
    rotations = references.copy()
    rotations[1] = np.nan
    out = rotation_vectors_between(rotations, references)
    assert np.isnan(out[1]).all()
    np.testing.assert_allclose(out[[0, 2]], 0.0, atol=1e-12)


def test_per_axis_tcp_error_channels():
    plot = run_entry(analyze_comparison(lagging_comparison()))["plot"]

    # Cruise is 0.55 s .. 2.5 s for both; in it x lags by SPEED * LAG_S exactly.
    t = np.linspace(0.0, 3.0, 3001)
    cruise = (t > 0.6) & (t < 2.45)
    plot_t = np.array(analyze_comparison(lagging_comparison())["plot_t"], dtype=float)
    cruise_plot = (plot_t > 0.6) & (plot_t < 2.45)
    # target - run: the run is behind in x, +y of it, +yaw: so x is +, y and yaw are -.
    np.testing.assert_allclose(column(plot, "err_x")[cruise_plot], SPEED * LAG_S, atol=1e-6)
    np.testing.assert_allclose(column(plot, "err_y"), -OFFSET_Y, atol=1e-9)
    np.testing.assert_allclose(column(plot, "err_z"), 0.0, atol=1e-9)
    np.testing.assert_allclose(column(plot, "err_rz"), -YAW_ERROR, atol=1e-9)
    np.testing.assert_allclose(column(plot, "err_rx"), 0.0, atol=1e-9)
    np.testing.assert_allclose(column(plot, "err_ry"), 0.0, atol=1e-9)
    assert cruise.any()


def test_lag_and_cross_track_split_lag_from_offset():
    payload = analyze_comparison(lagging_comparison())
    plot = run_entry(payload)["plot"]
    plot_t = np.array(payload["plot_t"], dtype=float)
    cruise = (plot_t > 0.6) & (plot_t < 2.45)

    lag = column(plot, "lag")
    cross = column(plot, "cross_track")
    assert "along_track" not in plot
    # Behind the target by SPEED * LAG_S along +x -> positive lag.
    np.testing.assert_allclose(lag[cruise], SPEED * LAG_S, atol=1e-6)
    np.testing.assert_allclose(cross[cruise], OFFSET_Y, atol=1e-6)
    # While the target rests there is no direction of travel: no lag/cross value.
    resting = (plot_t < 0.45) | (plot_t > 2.55)
    assert np.isnan(lag[resting]).all()
    assert np.isnan(cross[resting]).all()


def test_error_metrics_carry_every_error_stat_per_metric():
    metrics = run_entry(analyze_comparison(lagging_comparison()))["error_metrics"]

    assert set(metrics) >= {
        "positions/j", "position", "rotation", "cross_track", "lag",
        "x", "y", "z", "rx", "ry", "rz",
        "coverage", "dropped", "time_offset_s",
    }  # fmt: skip
    stat_fields = {
        "n", "rms", "mean", "median", "std", "min", "max", "max_abs", "p95_abs", "final",
        "iae", "ise", "itae",
    }  # fmt: skip
    for summary in (metrics["position"], metrics["rotation"], metrics["x"], metrics["positions/j"]):
        assert set(summary) == stat_fields
    assert (metrics["coverage"], metrics["dropped"], metrics["time_offset_s"]) == (1.0, 0, 0.0)

    rotation = metrics["rotation"]
    assert rotation["rms"] == pytest.approx(YAW_ERROR, abs=1e-9)
    assert rotation["max_abs"] == pytest.approx(YAW_ERROR, abs=1e-9)
    assert rotation["final"] == pytest.approx(YAW_ERROR, abs=1e-9)
    assert rotation["std"] == pytest.approx(0.0, abs=1e-9)

    # Both end at rest, the run reaches the end of the route: only the side offset is left.
    assert metrics["position"]["final"] == pytest.approx(OFFSET_Y, abs=1e-9)
    worst = float(np.hypot(SPEED * LAG_S, OFFSET_Y))
    assert metrics["position"]["max_abs"] == pytest.approx(worst, abs=1e-6)
    assert OFFSET_Y <= metrics["position"]["p95_abs"] <= worst + 1e-9
    assert metrics["lag"]["max_abs"] == pytest.approx(SPEED * LAG_S, abs=1e-6)
    assert metrics["lag"]["final"] > 0.0  # signed: still behind at the last moving sample
    assert metrics["rz"]["final"] == pytest.approx(-YAW_ERROR, abs=1e-9)  # target - run
    assert metrics["positions/j"]["rms"] == pytest.approx(0.0, abs=1e-12)


def test_tcp_frame_is_named_in_payload_and_table(tmp_path):
    path = write_comparison_report([lagging_comparison(tcp_frame="L2 tip")], tmp_path)
    page = extract_payload(path.read_text("utf-8"))["comparisons"][0]

    assert page["tcp_frame"] == "L2 tip"
    table = page["statistics"]
    assert "L2 tip frame" in table["description"]
    assert table["columns"] == [
        "Situation",
        "Mean joint RMS",
        "Worst joint",
        "TCP pos RMS",
        "TCP rot RMS",
        "TCP pos max · final",
        "TCP rot max · final",
        "Cross-track · lag RMS",
        "Samples / status",
    ]
    cells = table["rows"][0]["cells"]
    assert cells[6] == "5.730° · 5.730°"  # 0.1 rad
    assert cells[5].endswith("· 4.000 mm")


def test_default_frame_is_tcp():
    assert analyze_comparison(lagging_comparison())["tcp_frame"] == "TCP"
