"""Channel identities the analysis must reproduce exactly."""

import json

import numpy as np
import pytest
from robot_msgs.compare import compare
from robot_msgs.trajectory import JointTrajectory

from traj_compare.analysis import analyze_comparison
from traj_compare.model import Comparison, Situation


def yaw_only_fk(q: np.ndarray) -> np.ndarray:
    """Toy fk that only rotates: yaw = q0, TCP position fixed at the origin."""

    poses = np.tile(np.eye(4), (len(q), 1, 1))
    yaw = q[:, 0]
    poses[:, 0, 0] = np.cos(yaw)
    poses[:, 0, 1] = -np.sin(yaw)
    poses[:, 1, 0] = np.sin(yaw)
    poses[:, 1, 1] = np.cos(yaw)
    return poses


def translation_fk(q: np.ndarray) -> np.ndarray:
    """Pure translation fk (identity rotation) for path-channel identities."""

    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, :2, 3] = q
    return poses


def line_situation(name: str, speed: float, duration: float = 2.0, n: int = 201) -> Situation:
    t = np.linspace(0.0, duration, n)
    q = np.column_stack([speed * t, np.zeros_like(t)])
    return Situation(name=name, t=t, q=q)


def test_straight_line_constant_speed_identities():
    speed = 0.25
    comparison = Comparison(
        title="line",
        joint_names=["jx", "jy"],
        target=line_situation("target", speed),
        situations=[line_situation("sim", speed)],
        fk=translation_fk,
        vec_dirs=[("Along", np.array([1.0, 0.0, 0.0])), ("Ortho", np.array([0.0, 1.0, 0.0]))],
    )
    payload = analyze_comparison(comparison)
    target = payload["situations"][0]
    assert target["role"] == "target"
    plot = target["plot"]

    xyz = np.array(plot["xyz"], dtype=float)
    assert xyz[-1] == pytest.approx(speed * 2.0, abs=1e-9)
    np.testing.assert_allclose(np.array(plot["xyz_d"], dtype=float)[2:-2], speed, atol=1e-9)

    pct = np.array(plot["pct"], dtype=float)
    assert pct[0] == 0.0
    assert pct[-1] == pytest.approx(100.0, abs=1e-9)
    np.testing.assert_allclose(np.array(plot["pct_d"], dtype=float)[2:-2], 50.0, atol=1e-6)

    np.testing.assert_allclose(np.array(plot["vec0"], dtype=float), xyz, atol=1e-9)
    np.testing.assert_allclose(np.array(plot["vec1"], dtype=float), 0.0, atol=1e-12)
    assert np.all(np.array(plot["rpy"], dtype=float) == 0.0)

    sim = payload["situations"][1]
    np.testing.assert_allclose(np.array(sim["plot"]["xyz_mag"], dtype=float), 0.0, atol=1e-9)
    np.testing.assert_allclose(np.array(sim["plot"]["rot_mag"], dtype=float), 0.0, atol=1e-7)
    np.testing.assert_allclose(np.array(sim["plot"]["err_q"], dtype=float), 0.0, atol=1e-9)


def test_pure_rotation_accumulates_rpy_path():
    t = np.linspace(0.0, 2.0, 301)
    total_angle = 3.5
    q = np.column_stack([total_angle * t / 2.0, np.zeros_like(t)])
    target = Situation(name="target", t=t, q=q)
    comparison = Comparison(
        title="spin", joint_names=["yaw", "unused"], target=target, situations=[], fk=yaw_only_fk
    )
    plot = analyze_comparison(comparison)["situations"][0]["plot"]
    assert np.array(plot["rpy"], dtype=float)[-1] == pytest.approx(total_angle, abs=1e-6)
    # Unwrapped yaw crosses pi without jumping.
    rz = np.array(plot["rz"], dtype=float)
    assert rz[-1] == pytest.approx(total_angle, abs=1e-9)
    assert np.max(np.abs(np.diff(rz))) < 0.1
    assert np.all(np.array(plot["xyz"], dtype=float) < 1e-12)


def test_pct_uses_target_total_for_candidates():
    target = line_situation("target", speed=0.5)  # length 1.0
    half = line_situation("half", speed=0.25)  # length 0.5
    comparison = Comparison(
        title="pct", joint_names=["jx", "jy"], target=target, situations=[half], fk=translation_fk
    )
    payload = analyze_comparison(comparison)
    assert payload["pct_reference"] == "target"
    pct_half = np.array(payload["situations"][1]["plot"]["pct"], dtype=float)
    assert pct_half[-1] == pytest.approx(50.0, abs=1e-9)


def test_known_offset_error_magnitudes():
    t = np.linspace(0.0, 1.0, 101)
    q_target = np.column_stack([t, np.zeros_like(t)])
    offset = np.array([0.0, 0.03])
    target = Situation(name="target", t=t, q=q_target)
    shifted = Situation(name="shifted", t=t, q=q_target + offset)
    comparison = Comparison(
        title="offset",
        joint_names=["jx", "jy"],
        target=target,
        situations=[shifted],
        fk=translation_fk,
    )
    plot = analyze_comparison(comparison)["situations"][1]["plot"]
    np.testing.assert_allclose(np.array(plot["xyz_mag"], dtype=float), 0.03, atol=1e-9)
    # error = target - run, so a run 0.03 to the +y side reads -0.03
    np.testing.assert_allclose(np.array(plot["err_q"], dtype=float)[1], -0.03, atol=1e-9)
    # Difference arrows: same-time target pose recorded next to the situation.
    three = analyze_comparison(comparison)["situations"][1]["three"]
    assert np.allclose(np.array(three["tp"], dtype=float)[:, 1], 0.0, atol=1e-9)
    assert np.allclose(np.array(three["p"], dtype=float)[:, 1], 0.03, atol=1e-9)


def test_shorter_run_gets_null_padding_not_a_plateau():
    target = line_situation("target", speed=0.5, duration=2.0, n=201)
    short = line_situation("short", speed=0.5, duration=1.0, n=101)
    comparison = Comparison(
        title="short",
        joint_names=["jx", "jy"],
        target=target,
        situations=[short],
        fk=translation_fk,
    )
    payload = analyze_comparison(comparison)
    plot_t = np.array(payload["plot_t"], dtype=float)
    assert plot_t[-1] == pytest.approx(2.0)
    q0 = payload["situations"][1]["plot"]["q"][0]
    assert q0[-1] is None  # beyond the short run's span
    assert q0[10] is not None


def test_derivative_fallbacks_are_flagged_not_overwritten():
    t = np.linspace(0.0, 1.0, 51)
    q = np.column_stack([np.sin(t), np.cos(t)])
    qd = np.column_stack([np.cos(t), -np.sin(t)])
    with_qd = Situation(name="a", t=t, q=q, qd=qd)
    without = Situation(name="b", t=t, q=q)
    comparison = Comparison(
        title="derived", joint_names=["j1", "j2"], target=None, situations=[with_qd, without]
    )
    payload = analyze_comparison(comparison)
    entry_a, entry_b = payload["situations"]
    assert entry_a["derived"] == ["qdd"]
    assert entry_b["derived"] == ["qd", "qdd"]
    np.testing.assert_allclose(np.array(entry_a["plot"]["qd"], dtype=float), qd.T, atol=1e-6)


def test_empty_situation_and_json_round_trip():
    target = line_situation("target", speed=0.5)
    empty = Situation(name="real", note="hardware run skipped")
    comparison = Comparison(
        title="with empty",
        joint_names=["jx", "jy"],
        target=target,
        situations=[line_situation("sim", 0.5), empty],
        fk=translation_fk,
    )
    payload = analyze_comparison(comparison)
    entry = payload["situations"][2]
    assert entry["has_data"] is False
    assert entry["note"] == "hardware run skipped"
    assert entry["plot"] is None and entry["three"] is None

    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["situations"][2]["name"] == "real"


def test_joint_only_comparison_has_no_cartesian():
    t = np.linspace(0.0, 1.0, 41)
    q = np.column_stack([t, t])
    comparison = Comparison(
        title="joint only",
        joint_names=["j1", "j2"],
        target=Situation(name="target", t=t, q=q),
        situations=[Situation(name="sim", t=t, q=q * 0.9)],
    )
    payload = analyze_comparison(comparison)
    assert payload["has_cartesian"] is False
    sim_plot = payload["situations"][1]["plot"]
    assert "x" not in sim_plot
    # Joint error still computed without any fk.
    assert sim_plot["err_q"] is not None


def test_non_finite_values_become_null():
    t = np.linspace(0.0, 1.0, 11)
    q = np.column_stack([t, t])
    q[5, 0] = np.nan
    payload = analyze_comparison(
        Comparison(
            title="nan",
            joint_names=["j1", "j2"],
            target=None,
            situations=[Situation(name="sim", t=t, q=q)],
        )
    )
    dumped = json.dumps(payload)
    assert "NaN" not in dumped
    assert payload["situations"][0]["plot"]["q"][0][5] is None


def test_robot_payload_and_tracks():
    import base64

    from traj_compare.model import RobotDisplay

    t = np.linspace(0.0, 1.0, 21)
    q = np.column_stack([t, np.zeros_like(t)])
    tri = np.array([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], dtype=np.float32)

    def link_fk(q_matrix):
        poses = np.tile(np.eye(4), (len(q_matrix), 2, 1, 1))
        poses[:, 1, 0, 3] = q_matrix[:, 0]  # second link slides along x
        return poses

    robot = RobotDisplay(
        link_names=["base", "slider"],
        link_meshes=[tri, tri],
        link_fk=link_fk,
        link_colors=["#888888", None],
        link_opacities=[0.5, 0.9],
    )
    comparison = Comparison(
        title="robot",
        joint_names=["jx", "jy"],
        target=Situation(name="target", t=t, q=q),
        situations=[Situation(name="real", note="skipped")],
        fk=translation_fk,
        robot=robot,
    )
    payload = analyze_comparison(comparison)
    assert len(payload["robots"]) == 1
    model = payload["robots"][0]
    assert [link["name"] for link in model["links"]] == ["base", "slider"]
    assert model["links"][0]["color"] == "#888888"
    assert model["links"][1]["color"] is None
    assert model["links"][0]["opacity"] == pytest.approx(0.5)
    assert model["links"][1]["opacity"] == pytest.approx(0.9)
    decoded = np.frombuffer(
        base64.b64decode(model["links"][0]["tris"]), dtype="<f4"
    ).reshape(-1, 3, 3)
    np.testing.assert_allclose(decoded, tri)

    track = payload["situations"][0]["robot_track"]
    assert track["robot"] == 0
    assert np.array(track["p"], dtype=float).shape == (21, 2, 3)
    assert np.array(track["quat"], dtype=float).shape == (21, 2, 4)
    np.testing.assert_allclose(np.array(track["p"], dtype=float)[:, 1, 0], t, atol=1e-5)
    # declared-empty situation carries no track
    assert payload["situations"][1]["robot_track"] is None


def test_long_robot_tracks_are_display_downsampled_without_losing_endpoints():
    from traj_compare.model import RobotDisplay

    t = np.linspace(0.0, 10.0, 5001)
    q = np.column_stack([t, np.zeros_like(t)])
    tri = np.asarray([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], dtype=np.float32)

    def one_link_fk(q_matrix):
        poses = np.tile(np.eye(4), (len(q_matrix), 1, 1, 1))
        poses[:, 0, 0, 3] = q_matrix[:, 0]
        return poses

    payload = analyze_comparison(
        Comparison(
            title="long robot track",
            joint_names=["x", "unused"],
            situations=[Situation(name="sim", t=t, q=q)],
            robot=RobotDisplay(
                link_names=["link"],
                link_meshes=[tri],
                link_fk=one_link_fk,
            ),
        )
    )
    track = payload["situations"][0]["robot_track"]

    assert len(track["t"]) == 2000
    assert track["t"][0] == pytest.approx(0.0)
    assert track["t"][-1] == pytest.approx(10.0)
    assert track["p"][0][0][0] == pytest.approx(0.0)
    assert track["p"][-1][0][0] == pytest.approx(10.0)


def test_situation_model_overrides_the_comparison_model():
    """Runs sharing a model embed it once; a run with its own gets its own."""

    from traj_compare.model import RobotDisplay

    t = np.linspace(0.0, 1.0, 11)
    q = np.column_stack([t, np.zeros_like(t)])
    tri = np.array([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], dtype=np.float32)

    def one_link_fk(q_matrix):
        return np.tile(np.eye(4), (len(q_matrix), 1, 1, 1))

    shared = RobotDisplay(link_names=["rig"], link_meshes=[tri], link_fk=one_link_fk,
                          name="shared rig")
    other = RobotDisplay(link_names=["rig"], link_meshes=[tri], link_fk=one_link_fk,
                         name="the other rig")
    payload = analyze_comparison(
        Comparison(
            title="two models",
            joint_names=["jx", "jy"],
            target=Situation(name="target", t=t, q=q),
            situations=[
                Situation(name="sim", t=t, q=q),
                Situation(name="real", t=t, q=q, robot=other),
            ],
            fk=translation_fk,
            robot=shared,
        )
    )

    assert [model["name"] for model in payload["robots"]] == ["shared rig", "the other rig"]
    by_name = {sit["name"]: sit["robot_track"]["robot"] for sit in payload["situations"]}
    assert by_name == {"target": 0, "sim": 0, "real": 1}


def test_robot_display_validation():
    from traj_compare.model import RobotDisplay

    tri = np.zeros((1, 3, 3), dtype=np.float32)
    with pytest.raises(ValueError):
        RobotDisplay(link_names=["a", "b"], link_meshes=[tri], link_fk=lambda q: None)
    with pytest.raises(ValueError):
        RobotDisplay(
            link_names=["a"],
            link_meshes=[tri],
            link_fk=lambda q: None,
            link_opacities=[1.5],
        )


def test_video_passthrough():
    t = np.linspace(0.0, 1.0, 11)
    q = np.column_stack([t, t])
    comparison = Comparison(
        title="video",
        joint_names=["j1", "j2"],
        target=None,
        situations=[
            Situation(name="sim", t=t, q=q, video="sim.mp4"),
            Situation(name="quiet", t=t, q=q),
        ],
    )
    payload = analyze_comparison(comparison)
    assert payload["has_video"] is True
    assert payload["situations"][0]["video"] == "sim.mp4"
    assert payload["situations"][1]["video"] is None


def test_numpy_metadata_is_json_safe():
    t = np.array([0.0, 1.0])
    comparison = Comparison(
        title="metadata",
        joint_names=["j1"],
        situations=[
            Situation(
                name="sim",
                t=t,
                q=np.zeros((2, 1)),
                meta={
                    "series": np.array([1.0, np.nan]),
                    "count": np.int64(2),
                },
            )
        ],
        meta={"score": np.float64(0.5)},
    )

    payload = analyze_comparison(comparison)
    assert payload["meta"] == {"score": 0.5}
    assert payload["situations"][0]["meta"] == {
        "series": [1.0, None],
        "count": 2,
    }


def test_joint_error_is_target_minus_run_and_is_robot_msgs_compare_error():
    rng = np.random.default_rng(7)
    t = np.linspace(0.0, 1.0, 101)
    target = Situation(
        name="target", t=t, q=rng.normal(size=(101, 2)), qd=rng.normal(size=(101, 2))
    )
    run = Situation(name="run", t=t, q=rng.normal(size=(101, 2)), qd=rng.normal(size=(101, 2)))
    comparison = Comparison(
        title="one source", joint_names=["jx", "jy"], target=target, situations=[run]
    )

    entry = analyze_comparison(comparison)["situations"][1]
    payload_error = np.array(entry["plot"]["err_q"], dtype=float).T  # (N, J) on the target grid
    library = compare(
        JointTrajectory(t=t, joint_names=["jx", "jy"], positions=target.q, velocities=target.qd),
        JointTrajectory(t=t, joint_names=["jx", "jy"], positions=run.q, velocities=run.qd),
    )

    # the payload rounds to 6 decimals
    np.testing.assert_allclose(payload_error, -(run.q - target.q), atol=1e-6)
    np.testing.assert_allclose(payload_error, library.error.positions, atol=1e-6)
    # the table statistics are the library's numbers too, not a second computation
    metrics = entry["error_metrics"]
    for index, name in enumerate(["jx", "jy"]):
        assert metrics[f"positions/{name}"] == library.metrics[f"positions/{name}"].as_dict()
        assert metrics[f"positions/{name}"]["rms"] == pytest.approx(
            float(np.sqrt(np.mean((target.q[:, index] - run.q[:, index]) ** 2)))
        )
    assert "velocities/jx" in metrics


def test_run_on_its_own_grid_is_compared_on_its_own_samples_inside_the_target_span():
    t_target = np.linspace(0.0, 1.0, 11)
    t_run = np.linspace(-0.5, 1.5, 201)  # denser than the target and longer on both ends
    target = Situation(name="target", t=t_target, q=np.column_stack([2.0 * t_target]))
    run = Situation(name="run", t=t_run, q=np.column_stack([2.0 * t_run + 0.1]))
    comparison = Comparison(title="grids", joint_names=["j"], target=target, situations=[run])

    entry = analyze_comparison(comparison)["situations"][1]
    inside = (t_run >= 0.0) & (t_run <= 1.0)
    metrics = entry["error_metrics"]

    assert metrics["positions/j"]["n"] == int(inside.sum())  # 101 of 201, none extrapolated
    assert metrics["dropped"] == int((~inside).sum())
    assert metrics["coverage"] == pytest.approx(1.0)
    # target - run = -0.1 everywhere the target exists
    np.testing.assert_allclose(np.array(entry["plot"]["err_q"][0], dtype=float), -0.1, atol=1e-9)
