"""The viewer shows robot_msgs.compare's second wave (written before the code, 2026-11-10).

Verdicts (ROS 2 tolerances), latency estimate, goal / settling, exact contour + lag time,
ISO 9283 accuracy vs repeatability across repeated runs, and errors along named axes (the
conveyor frame). Every number in the payload must equal what robot_msgs.compare returns for the
same inputs, so the report and the library can never disagree.
"""

import numpy as np
import pytest
from robot_msgs.compare import (
    JointTolerance,
    PoseTolerance,
    Tolerances,
    aggregate,
    check,
    estimate_time_offset,
    goal,
)
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from traj_compare import Comparison, Situation, write_comparison_report
from traj_compare.analysis import analyze_comparison

from test_report import extract_payload

BELT = np.array([0.0, 1.0, 0.0])  # the conveyor runs along world +Y


def translation_fk(q: np.ndarray) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, :2, 3] = q
    return poses


def path(t: np.ndarray) -> np.ndarray:
    """j1 = x, j2 = y: rest, a smooth swing out along +Y (the belt), rest."""
    phase = np.clip((t - 0.2) / 1.6, 0.0, 1.0)
    s = 0.5 - 0.5 * np.cos(np.pi * phase)
    return np.column_stack([0.05 * np.sin(np.pi * phase), 0.3 * s])


T = np.linspace(0.0, 2.4, 1201)


def run(name: str, delay: float, bias=(0.0, 0.0), title=None) -> Situation:
    q = path(T - delay) + np.asarray(bias)
    return Situation(name=name, title=title or name, t=T, q=q)


def tolerances() -> Tolerances:
    return Tolerances(
        path=(JointTolerance(name="j1", position=0.004), JointTolerance(name="j2", position=0.004)),
        goal=(JointTolerance(name="j1", position=0.002), JointTolerance(name="j2", position=0.002)),
    )


def tcp_tolerances() -> Tolerances:
    return Tolerances(path=PoseTolerance(position=0.006), goal=PoseTolerance(position=0.002))


def comparison(**kwargs) -> Comparison:
    target = Situation(name="target", title="Target", t=T, q=path(T))
    situations = [
        run("sim", 0.010, title="Sim"),
        run("real_1", 0.030, (0.0005, 0.0)),
        run("real_2", 0.030, (-0.0005, 0.001)),
        run("real_3", 0.030, (0.0, -0.0010)),
    ]
    return Comparison(
        title="Belt pick",
        joint_names=["j1", "j2"],
        target=target,
        situations=situations,
        fk=translation_fk,
        vec_dirs=[("Conveyor", BELT)],
        **kwargs,
    )


def joint_traj(situation: Situation) -> JointTrajectory:
    return JointTrajectory(t=situation.t, joint_names=("j1", "j2"), positions=situation.q)


def pose_traj(situation: Situation) -> PoseTrajectory:
    return PoseTrajectory.from_matrices(situation.t, translation_fk(situation.q), child_frame_id="TCP")


def entry(payload, name):
    return next(item for item in payload["situations"] if item["name"] == name)


def test_off_by_default_old_reports_unchanged():
    payload = analyze_comparison(comparison())
    sim = entry(payload, "sim")
    for key in ("verdict", "latency", "goal"):
        assert sim.get(key) is None
    assert not payload.get("aggregates")


def test_verdict_per_situation_equals_robot_msgs_check():
    payload = analyze_comparison(comparison(tolerances=tolerances(), tcp_tolerances=tcp_tolerances()))
    reference = comparison().target
    for name in ("sim", "real_1"):
        situation = next(s for s in comparison().situations if s.name == name)
        expected = check(joint_traj(reference), joint_traj(situation), tolerances())
        verdict = entry(payload, name)["verdict"]["joint"]
        assert verdict["error_code"] == expected.error_code
        assert verdict["code_name"] == expected.code_name
        assert verdict["margins"] == pytest.approx(dict(expected.margins))
        if expected.violations:
            assert verdict["violations"][0]["metric"] == expected.violations[0].metric
            assert verdict["violations"][0]["t"] == pytest.approx(expected.violations[0].t)
        tcp_expected = check(pose_traj(reference), pose_traj(situation), tcp_tolerances())
        assert entry(payload, name)["verdict"]["tcp"]["code_name"] == tcp_expected.code_name
    # 30 ms behind on a 0.3 m swing breaks a 4 mm path tolerance; 10 ms does not
    assert entry(payload, "real_1")["verdict"]["joint"]["code_name"] == "PATH_TOLERANCE_VIOLATED"
    assert entry(payload, "sim")["verdict"]["joint"]["code_name"] == "SUCCESSFUL"
    assert "target" not in [item["name"] for item in payload["situations"] if item.get("verdict")]


def test_latency_estimate_equals_robot_msgs_and_recovers_the_hidden_delay():
    payload = analyze_comparison(comparison(estimate_latency=True))
    reference = comparison().target
    sim = comparison().situations[0]
    expected = estimate_time_offset(joint_traj(reference), joint_traj(sim))
    latency = entry(payload, "sim")["latency"]
    assert latency["offset_s"] == pytest.approx(expected.offset_s)
    assert latency["offset_s"] == pytest.approx(0.010, abs=5e-4)
    assert latency["rms_after"] < latency["rms_before"]


def test_goal_stats_equal_robot_msgs_goal():
    payload = analyze_comparison(comparison(goal_band=0.002, tcp_goal_band=0.002))
    reference = comparison().target
    real = comparison().situations[1]
    expected = goal(joint_traj(reference), joint_traj(real), band=0.002)
    stats = entry(payload, "real_1")["goal"]["joint"]["positions/j2"]
    assert stats["final_error"] == pytest.approx(expected["positions/j2"].final_error)
    assert stats["settling_time"] == pytest.approx(expected["positions/j2"].settling_time, nan_ok=True)
    assert "position" in entry(payload, "real_1")["goal"]["tcp"]


def test_contour_and_lag_time_ride_in_the_tcp_plots():
    payload = analyze_comparison(comparison())
    plot = entry(payload, "real_1")["plot"]
    lag_time = np.array([v for v in plot["lag_time"] if v is not None], dtype=float)
    contour = np.array([v for v in plot["contour"] if v is not None], dtype=float)
    assert lag_time.size and contour.size
    assert np.nanmedian(lag_time) == pytest.approx(0.030, abs=2e-3)  # 30 ms behind, + = behind
    assert np.nanmax(contour) < 0.002  # a straight-ish path: the late run stays near it


def test_errors_along_named_axes_read_the_belt_frame():
    axes = [("along belt", BELT), ("across belt", np.array([1.0, 0.0, 0.0])), ("up", np.array([0.0, 0.0, 1.0]))]
    payload = analyze_comparison(comparison(error_axes=axes))
    assert payload["error_axes"] == ["along belt", "across belt", "up"]
    plot = entry(payload, "real_2")["plot"]
    along = np.array([v for v in plot["err_axes"][0] if v is not None], dtype=float)
    across = np.array([v for v in plot["err_axes"][1] if v is not None], dtype=float)
    err_y = np.array([v for v in plot["err_y"] if v is not None], dtype=float)
    err_x = np.array([v for v in plot["err_x"] if v is not None], dtype=float)
    np.testing.assert_allclose(along, err_y, atol=1e-12)  # belt is +Y: along = world y error
    np.testing.assert_allclose(across, err_x, atol=1e-12)


def test_iso_9283_aggregate_over_a_repeat_group_equals_robot_msgs():
    payload = analyze_comparison(comparison(repeat_groups={"Real ×3": ["real_1", "real_2", "real_3"]}))
    group = payload["aggregates"]["Real ×3"]
    assert group["runs"] == ["real_1", "real_2", "real_3"]
    base = comparison()
    runs = [joint_traj(s) for s in base.situations[1:]]
    expected = aggregate(joint_traj(base.target), runs)
    assert group["joint"]["repeatability"]["positions/j2"]["max"] == pytest.approx(
        expected.metrics["positions/j2"].max
    )
    assert group["joint"]["accuracy"]["positions/j2"]["max_abs"] == pytest.approx(
        expected.accuracy.metrics["positions/j2"].max_abs
    )
    tcp = aggregate(pose_traj(base.target), [pose_traj(s) for s in base.situations[1:]])
    assert group["tcp"]["repeatability"]["position"]["max"] == pytest.approx(tcp.metrics["position"].max)


def test_report_html_shows_the_new_sections(tmp_path):
    report = write_comparison_report(
        [
            comparison(
                tolerances=tolerances(),
                estimate_latency=True,
                goal_band=0.002,
                repeat_groups={"Real ×3": ["real_1", "real_2", "real_3"]},
            )
        ],
        tmp_path,
    )
    html = report.read_text("utf-8")
    page = extract_payload(html)["comparisons"][0]
    columns = page["statistics"]["columns"]
    for column in ("Verdict", "Est. latency", "Settling"):
        assert any(column in name for name in columns), f"{column} missing from {columns}"
    assert "ISO 9283" in html
    assert "PATH_TOLERANCE_VIOLATED" in html
