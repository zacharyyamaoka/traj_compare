"""Trajectory coverage analysis (acceptance, written before the code, 2026-11-23).

The contract is docs/COVERAGE.md: robot_msgs in (JointTrajectory, PoseTrajectory, JointLimits), one payload dict
"traj_compare.coverage/1" out, which every viewer reads. Every case here has an answer known by construction
(a sine's span and peak, a robot standing still, a tool pointing straight down), so the numbers are checked
against the geometry, never against the code's own output.

Zach, Daily Note 2026-11-23 (Coverage Feedback): "Robot_msgs in. Then do the analysis. and then like the viewers out",
"So for Trajectory I think its clear its like Trajectory or Trajectory Dataset in".
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from robot_msgs.std import Header
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from scipy.spatial.transform import Rotation

from traj_compare.coverage import analyze

JOINTS = ("a", "b")
LIMITS = JointLimits(
    joint_names=JOINTS,
    min_position=np.array([-math.pi, -1.0]),
    max_position=np.array([math.pi, 1.0]),
    max_velocity=np.array([2.0, 2.0]),
    max_acceleration=np.array([10.0, 10.0]),
)
HZ = 100.0


def sine(amp: float = 1.0, w: float = 1.0, seconds: float = 20.0, derivatives: bool = True, limits=LIMITS,
         name: str | None = None) -> JointTrajectory:
    """Joint a: amp*sin(w t); joint b: half of it. Analytic derivatives (or none)."""
    t = np.arange(0.0, seconds, 1.0 / HZ)
    scale = np.array([1.0, 0.5])
    q = amp * np.sin(w * t)[:, None] * scale
    qd = amp * w * np.cos(w * t)[:, None] * scale
    qdd = -amp * w * w * np.sin(w * t)[:, None] * scale
    header = Header(meta={"name": name}) if name else Header()
    if not derivatives:
        return JointTrajectory(t=t, joint_names=JOINTS, positions=q, limits=limits, header=header)
    return JointTrajectory(t=t, joint_names=JOINTS, positions=q, velocities=qd, accelerations=qdd, limits=limits,
                           header=header)


def still(seconds: float = 5.0, at=(0.0, 0.0)) -> JointTrajectory:
    t = np.arange(0.0, seconds, 1.0 / HZ)
    q = np.tile(np.asarray(at, float), (len(t), 1))
    zero = np.zeros_like(q)
    return JointTrajectory(t=t, joint_names=JOINTS, positions=q, velocities=zero, accelerations=zero, limits=LIMITS)


def tool(positions: np.ndarray, rotation: np.ndarray, t: np.ndarray) -> PoseTrajectory:
    quat = Rotation.from_matrix(np.broadcast_to(rotation, (len(t), 3, 3))).as_quat()  # xyzw
    return PoseTrajectory(t=t, positions=positions, orientations=quat)


DOWN = np.diag([1.0, -1.0, -1.0])  # tool x = base x, tool z = base -z (straight down)


def counts(block) -> np.ndarray:
    return np.asarray(block, float)


# ── shape of the payload ─────────────────────────────────────────────────────


def test_one_trajectory_is_a_dataset_of_one_and_the_payload_is_strict_json():
    cov = analyze(sine())
    payload = cov.payload
    assert payload["schema"] == "traj_compare.coverage/1"
    json.dumps(payload, allow_nan=False)  # NaN / inf would break every viewer's JSON.parse
    assert payload["source"]["trajectories"] == 1
    assert payload["source"]["samples"] == 2000
    assert [joint["name"] for joint in payload["joints"]] == list(JOINTS)
    assert payload["joints"][0]["kind"] == "revolute" and payload["joints"][0]["display"]["unit"] == "deg"
    assert payload["signals"] == ["q", "qd", "qdd", "qddd"]
    assert payload["tool"] is None


def test_names_come_from_the_mapping_then_the_header_then_the_index():
    named = analyze({"first": sine(), "second": still()}).payload
    assert [row["name"] for row in named["trajectories"]] == ["first", "second"]
    from_header = analyze([sine(name="lap"), still()]).payload
    assert [row["name"] for row in from_header["trajectories"]] == ["lap", "traj_1"]


def test_joint_names_must_match():
    other = JointTrajectory(t=np.arange(0, 1, 0.01), joint_names=("a", "c"), positions=np.zeros((100, 2)))
    with pytest.raises(ValueError, match="joint"):
        analyze([sine(), other])


def test_headline_numbers_are_finite_and_complete():
    numbers = analyze(sine()).numbers
    for key in ("trajectories", "samples", "duration_s", "q_span_median_pct", "q_span_min_pct", "qd_peak_max_pct",
                "qdd_peak_max_pct", "q_qd_visited_mean_pct", "qd_qdd_visited_mean_pct"):
        assert key in numbers and math.isfinite(numbers[key]), key
    rows = analyze(sine()).payload["numbers"]
    assert {row["key"] for row in rows} == set(numbers)
    assert all({"key", "label", "value", "unit"} <= set(row) for row in rows)


# ── limits and 1-D histograms ───────────────────────────────────────────────


def test_a_sine_uses_the_share_of_each_limit_its_geometry_says():
    hist = analyze(sine(amp=1.0, w=1.0)).payload["hist"]
    # joint a: q in [-1, 1] of [-pi, pi]; qd peak 1 of 2; qdd peak 1 of 10
    assert hist["a"]["q"]["span_pct"] == pytest.approx(100 * 2.0 / (2 * math.pi), rel=0.01)
    assert hist["a"]["qd"]["peak_pct"] == pytest.approx(50.0, rel=0.01)
    assert hist["a"]["qdd"]["peak_pct"] == pytest.approx(10.0, rel=0.01)
    # joint b: half the amplitude on a +-1 range: q in [-0.5, 0.5] of [-1, 1]
    assert hist["b"]["q"]["span_pct"] == pytest.approx(50.0, rel=0.01)
    assert hist["b"]["qd"]["peak_pct"] == pytest.approx(25.0, rel=0.01)


def test_histogram_edges_span_the_limit_with_a_margin_and_count_every_sample():
    payload = analyze(sine()).payload
    q = payload["hist"]["a"]["q"]
    low, high, bins = q["edges"]
    assert bins == 120
    span = 2 * math.pi
    assert low == pytest.approx(-math.pi - 0.08 * span) and high == pytest.approx(math.pi + 0.08 * span)
    assert sum(q["counts"]) == 2000
    assert payload["limits"]["a"]["q"] == {"low": pytest.approx(-math.pi), "high": pytest.approx(math.pi),
                                           "source": "limit", "kind": None}


def test_a_signal_with_no_limit_falls_back_to_the_data_and_says_so():
    limits = analyze(sine()).payload["limits"]
    assert limits["a"]["qddd"]["source"] == "data"
    assert limits["a"]["qd"]["source"] == "limit"


def test_samples_beyond_a_limit_are_counted_outside():
    base = sine(amp=1.0)
    q = np.array(base.positions)
    q[:10, 1] = 1.05  # joint b's high limit is 1.0
    over = base.replace(positions=q)
    payload = analyze(over).payload
    assert payload["hist"]["b"]["q"]["outside"] == 10
    assert payload["planes"]["b"]["q_qd"]["outside"] == 10


def test_missing_derivatives_are_derived_from_positions():
    hist = analyze(sine(derivatives=False)).payload["hist"]
    assert hist["a"]["qd"]["peak_pct"] == pytest.approx(50.0, rel=0.02)
    assert hist["a"]["qdd"]["peak_pct"] == pytest.approx(10.0, rel=0.05)


def test_group_by_splits_each_histogram_and_the_parts_add_up():
    payload = analyze({"x": sine(), "y": sine(amp=0.5), "z": still()},
                      tags={"x": {"split": "dev"}, "y": {"split": "holdout"}, "z": {"split": "dev"}},
                      group_by="split").payload
    assert payload["source"]["group_by"] == "split"
    assert payload["source"]["groups"] == ["dev", "holdout"]
    block = payload["hist"]["a"]["qd"]
    total = counts(block["groups"]["dev"]) + counts(block["groups"]["holdout"])
    assert np.array_equal(total, counts(block["counts"]))
    assert payload["trajectories"][1]["tags"] == {"split": "holdout"}


def test_planner_limits_are_carried_for_the_dashed_lines():
    planner = JointLimits(joint_names=JOINTS, max_acceleration=np.array([5.0, 5.0]))
    payload = analyze(sine(), planner_limits=planner).payload
    assert payload["planner_limits"]["a"]["qdd"]["high"] == pytest.approx(5.0)
    assert payload["planner_limits"]["a"]["qdd"]["low"] == pytest.approx(-5.0)


# ── phase planes, slabs, paths ───────────────────────────────────────────────


def test_a_robot_standing_still_visits_exactly_one_cell():
    plane = analyze(still()).payload["planes"]["a"]["q_qd"]
    assert plane["shape"] == [36, 24]
    samples = counts(plane["samples"])
    assert (samples > 0).sum() == 1 and samples.sum() == 500
    assert plane["visited_pct"] == pytest.approx(100.0 / (36 * 24), rel=1e-6)
    assert plane["x_edges"] == [pytest.approx(-math.pi), pytest.approx(math.pi), 36]
    assert plane["y_edges"] == [pytest.approx(-2.0), pytest.approx(2.0), 24]


def test_paths_count_trajectories_not_samples():
    plane = analyze([sine(), sine()]).payload["planes"]["a"]["q_qd"]
    assert max(plane["paths"]) == 2
    assert sum(plane["samples"]) == 4000


def test_the_qdd_slabs_add_back_up_to_the_q_qd_plane():
    payload = analyze(sine()).payload
    slabs = payload["slabs"]["a"]
    assert slabs["by"] == "qdd" and slabs["shape"][0] == 5
    stacked = counts(slabs["samples"]).reshape(slabs["shape"]).sum(axis=0)
    plane = counts(payload["planes"]["a"]["q_qd"]["samples"]).reshape(payload["planes"]["a"]["q_qd"]["shape"])
    assert np.array_equal(stacked, plane)


def test_max_qdd_per_cell_is_recorded_and_null_where_unvisited():
    plane = analyze(sine()).payload["planes"]["a"]["q_qd"]
    values = plane["max_other"]
    visited = counts(plane["samples"]) > 0
    assert all((value is None) == (not seen) for value, seen in zip(values, visited, strict=True))
    assert max(value for value in values if value is not None) == pytest.approx(1.0, rel=0.02)


def test_paths_are_downsampled_per_trajectory():
    payload = analyze([sine(seconds=60.0), still()]).payload
    paths = payload["paths"]["a"]
    assert len(paths) == 2
    q, qd, qdd = paths[0]
    assert 50 <= len(q) <= 400 and len(q) == len(qd) == len(qdd)


def test_parallel_coordinates_have_one_gap_per_adjacent_joint_pair():
    parallel = analyze(sine()).payload["parallel"]["q"]
    assert parallel["axes"] == list(JOINTS)
    assert len(parallel["gaps"]) == len(JOINTS) - 1
    assert len(parallel["gaps"][0]) == parallel["width"] * parallel["height"]
    assert sum(parallel["gaps"][0]) > 0


# ── trajectories, growth ─────────────────────────────────────────────────────


def test_a_repeated_trajectory_adds_no_new_cells_and_growth_ends_at_the_pooled_value():
    payload = analyze({"one": sine(), "again": sine(), "rest": still(at=(2.0, 0.5))}).payload
    rows = payload["trajectories"]
    assert rows[0]["new_cells"] > 0 and rows[1]["new_cells"] == 0 and rows[2]["new_cells"] > 0
    growth = payload["growth"]["visited_pct"]
    assert len(growth) == 3
    assert all(later >= earlier for earlier, later in zip(growth, growth[1:]))
    assert growth[-1] == pytest.approx(analyze({"one": sine(), "again": sine(), "rest": still(at=(2.0, 0.5))})
                                       .numbers["q_qd_visited_mean_pct"])
    assert len(payload["growth"]["shuffled"]["mean"]) == 3


# ── the tool: Cartesian and orientation ─────────────────────────────────────


def test_a_tool_held_still_fills_one_voxel_and_one_pixel_per_projection():
    joint = still(seconds=2.0)
    t = np.asarray(joint.t)
    pose = tool(np.tile([0.3, 0.1, 0.2], (len(t), 1)), DOWN, t)
    payload = analyze(joint, tool=pose).payload
    assert payload["tool"] is not None
    assert len(payload["tool"]["voxels"]["cells"]) == 1
    for view in ("xy", "xz", "yz"):
        projection = payload["tool"]["projections"][view]
        samples = counts(projection["samples"])
        assert (samples > 0).sum() == 1 and samples.sum() == len(t)
        assert max(projection["paths"]) == 1


def test_a_downward_tool_has_zero_tilt_and_its_x_axis_sets_the_yaw():
    joint = still(seconds=2.0)
    t = np.asarray(joint.t)
    heading_y = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])  # tool x = base +y, tool z down
    orientation = analyze(joint, tool=tool(np.zeros((len(t), 3)), heading_y, t)).payload["tool"]["orientation"]
    tilt = counts(orientation["tilt"]["counts"])
    assert tilt[0] == tilt.sum() == len(t)
    low, high, bins = orientation["yaw"]["edges"]
    centres = low + (np.arange(bins) + 0.5) * (high - low) / bins
    assert math.degrees(centres[int(np.argmax(orientation["yaw"]["counts"]))]) == pytest.approx(90.0, abs=5.1)
    sphere = counts(orientation["sphere"]["counts"]).reshape(orientation["sphere"]["rings"], orientation["sphere"]["sectors"])
    assert sphere[0].sum() == len(t)  # base z = -1 is the first equal-area band


def test_a_tool_leaning_toward_x_by_45_degrees_lands_in_that_tilt_azimuth_cell():
    joint = still(seconds=2.0)
    t = np.asarray(joint.t)
    lean = Rotation.from_euler("y", -45, degrees=True).as_matrix() @ DOWN  # tool z tips from -z toward +x
    z_tool = lean[:, 2]
    assert z_tool[0] > 0 and z_tool[2] < 0
    grid = analyze(joint, tool=tool(np.zeros((len(t), 3)), lean, t)).payload["tool"]["orientation"]["tilt_azimuth"]
    cells = counts(grid["counts"]).reshape(grid["shape"])
    i, j = np.unravel_index(int(np.argmax(cells)), cells.shape)
    t_low, t_high, t_bins = grid["tilt_edges"]
    a_low, a_high, a_bins = grid["azimuth_edges"]
    tilt_centre = math.degrees(t_low + (i + 0.5) * (t_high - t_low) / t_bins)
    azimuth_centre = math.degrees(a_low + (j + 0.5) * (a_high - a_low) / a_bins)
    assert tilt_centre == pytest.approx(45.0, abs=10.1)
    assert azimuth_centre == pytest.approx(0.0, abs=10.1)


def test_tool_speed_and_paths_per_pixel_follow_the_motion():
    def sweep(seconds: float) -> tuple[JointTrajectory, PoseTrajectory]:
        t = np.arange(0.0, seconds, 1.0 / HZ)
        x = np.linspace(0.0, 0.2, len(t))
        joint = JointTrajectory(t=t, joint_names=JOINTS, positions=np.zeros((len(t), 2)), limits=LIMITS)
        return joint, tool(np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1), DOWN, t)

    slow_joint, slow_tool = sweep(2.0)  # 0.1 m/s
    fast_joint, fast_tool = sweep(1.0)  # 0.2 m/s
    payload = analyze([slow_joint, fast_joint], tool=[slow_tool, fast_tool]).payload
    xy = payload["tool"]["projections"]["xy"]
    visited = counts(xy["samples"]) > 0
    assert 10 <= visited.sum() <= 12  # 0.2 m of 2 cm pixels
    assert max(xy["paths"]) == 2
    speeds = [value for value in xy["max_speed"] if value is not None]
    assert max(speeds) == pytest.approx(0.2, rel=0.05)
    assert payload["tool"]["projections"]["xy"]["reachable"] is None


def test_reachable_points_give_the_cartesian_denominator():
    joint = still(seconds=1.0)
    t = np.asarray(joint.t)
    axis = np.linspace(0, 0.5, 51)  # 1 cm apart, so every 5 cm voxel of the box holds reachable points
    grid = np.stack(np.meshgrid(axis, axis, axis), -1).reshape(-1, 3)
    cov = analyze(joint, tool=tool(np.tile([0.12, 0.12, 0.12], (len(t), 1)), DOWN, t), reachable=grid)
    assert 0.0 < cov.numbers["tool_voxels_reachable_pct"] < 10.0
    assert cov.payload["tool"]["voxels"]["reachable"]
    for key in ("tool_pixels_xy", "tool_voxels_visited", "tool_speed_p99_m_s", "tool_directions_visited_pct",
                "tool_tilt_max_deg"):
        assert key in cov.numbers and math.isfinite(cov.numbers[key])
