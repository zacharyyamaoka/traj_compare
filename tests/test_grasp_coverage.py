"""Grasp coverage, the analysis (acceptance, written before the code, 2026-11-24). Contract: docs/GRASP_COVERAGE.md.

robot_msgs GraspPose in (+ an outcome per grasp + the jaw range), one payload "traj_compare.grasp_coverage/1" out. The
oracle is the made-up set in grasp_fixture.py: every grasp is built from known angles (tilt, azimuth, roll), width and
position, so the payload must give them back, and every count is re-derived here by hand.

Zach, Daily Note 2026-11-23: "showing where the failures where and not thats super helpful", "I really like this how it
shows the size of the grasps", roll as "just like a straight line actually works as well".
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from grasp_fixture import AREA, PLANNER_RANGE, WIDTH_RANGE, grasp, made_up
from robot_msgs.manipulation import GraspPose

from traj_compare.grasp_coverage import SCHEMA, analyze_grasps

DEG = 180.0 / math.pi


@pytest.fixture(scope="module")
def inputs():
    return made_up()


@pytest.fixture(scope="module")
def payload(inputs) -> dict:
    grasps, outcomes, tags, _ = inputs
    return analyze_grasps(grasps, outcomes=outcomes, width_range=WIDTH_RANGE, planner_width_range=PLANNER_RANGE,
                          tags=tags, area=AREA, title="Made-up picks").payload


def rows_by_name(payload: dict) -> dict:
    return {row["name"]: row for row in payload["grasps"]}


def hist_counts(values, block) -> np.ndarray:
    low, high, bins = block["edges"]
    index = np.floor((np.asarray(values, float) - low) / (high - low) * bins).astype(int)
    index = index[(index >= 0) & (index < bins)]
    return np.bincount(index, minlength=bins)


# ── the payload ─────────────────────────────────────────────────────────────


def test_schema_source_and_json_safety(payload, inputs):
    grasps = inputs[0]
    assert payload["schema"] == SCHEMA == "traj_compare.grasp_coverage/1"
    json.dumps(payload, allow_nan=False)  # JSON-safe by contract
    source = payload["source"]
    assert source["grasps"] == len(grasps) and source["frame"] == "base"
    assert source["objects"] == ["vial", "cap", "box"]  # most grasps first
    assert source["group_by"] == "outcome"
    assert source["with_pre_grasp"] == sum(g.pre_grasp_width is not None for g in grasps.values())
    assert source["with_score"] == sum(g.score is not None for g in grasps.values())
    assert source["jaws"] == "symmetric"
    assert payload["title"] == "Made-up picks"


def test_grasp_rows_keep_order_names_tags_and_si_values(payload, inputs):
    grasps, outcomes, tags, truth = inputs
    rows = payload["grasps"]
    assert [row["name"] for row in rows] == list(grasps)
    for row, outcome in zip(rows, outcomes, strict=True):
        assert row["outcome"] == (outcome or "unknown")
        assert row["tags"] == tags[row["name"]]
        assert row["object_id"] == grasps[row["name"]].object_id
        assert row["width"] == pytest.approx(truth[row["name"]]["width"])
        assert row["position"] == pytest.approx(list(truth[row["name"]]["position"]))
    assert payload["grasps_subsampled"] is None


def test_the_angles_come_back(payload, inputs):
    truth = inputs[3]
    for name, row in rows_by_name(payload).items():
        expected = truth[name]
        assert row["tilt"] == pytest.approx(expected["tilt"], abs=1e-9), name
        wrapped = math.remainder(row["roll"] - expected["roll"], 2 * math.pi)
        assert wrapped == pytest.approx(0.0, abs=1e-9), (name, row["roll"] * DEG, expected["roll"] * DEG)
        assert -math.pi < row["roll"] <= math.pi
        if expected["tilt"] > 1e-6:  # a straight-down approach has no lean
            assert math.remainder(row["azimuth"] - expected["azimuth"], 2 * math.pi) == pytest.approx(0.0, abs=1e-9)
        # robot_msgs' gripper: +z is the approach, x the jaw axis
        approach, jaw = np.asarray(row["approach"]), np.asarray(row["jaw"])
        assert abs(np.linalg.norm(approach) - 1) < 1e-9 and abs(approach @ jaw) < 1e-9


def test_a_straight_down_grasps_roll_is_its_jaw_heading():
    """The trajectory viewer's yaw, atan2(x.y, x.x), for a top-down grasp: one meaning across the two viewers."""
    for heading in (-170.0, -90.0, 0.0, 35.0, 90.0, 179.0):
        rad = math.radians(heading)
        rows = analyze_grasps([grasp((0.0, 0.0, 0.0), 0.0, 0.0, rad, 0.02)]).payload["grasps"]
        jaw = rows[0]["jaw"]
        assert math.degrees(math.atan2(jaw[1], jaw[0])) == pytest.approx(heading, abs=1e-6)
        assert math.degrees(rows[0]["roll"]) == pytest.approx(heading, abs=1e-6)


def test_straight_up_is_tilt_180_and_still_has_a_roll():
    rows = analyze_grasps([grasp((0, 0, 0), math.pi, 0.0, 0.3, 0.02)]).payload["grasps"]
    assert math.degrees(rows[0]["tilt"]) == pytest.approx(180.0)
    assert math.isfinite(rows[0]["roll"])


def test_outcomes_order_counts_words_and_closed(payload, inputs):
    outcomes = inputs[1]
    block = payload["outcomes"]
    assert block["order"] == ["picked", "failed", "hovered", "refused", "unknown"]
    assert block["counts"] == {name: sum((o or "unknown") == name for o in outcomes) for name in block["order"]}
    assert block["closed"] == ["picked", "failed"]
    assert set(block["words"]) == set(block["order"]) and all(block["words"].values())
    assert payload["source"]["groups"] == block["order"]


def test_an_unknown_word_is_kept_after_the_known_ones():
    grasps = [grasp((0, 0, 0), 0.0, 0.0, 0.0, 0.02) for _ in range(3)]
    block = analyze_grasps(grasps, outcomes=["slipped", "picked", None]).payload["outcomes"]
    assert block["order"] == ["picked", "slipped", "unknown"]


def test_the_gripper_range_and_planner(payload):
    gripper = payload["gripper"]
    assert (gripper["low"], gripper["high"], gripper["source"]) == (0.0, 0.12, "limit")
    assert (gripper["planner_low"], gripper["planner_high"]) == (0.0, 0.07)


def test_width_histogram_against_the_range(payload, inputs):
    grasps = inputs[0]
    widths = np.array([g.width for g in grasps.values()])
    block = payload["width"]
    low, high, bins = block["edges"]
    assert bins == 72
    assert low == pytest.approx(0.0 - 0.08 * 0.12) and high == pytest.approx(0.12 + 0.08 * 0.12)
    assert block["counts"] == hist_counts(widths, block).tolist()
    order = payload["source"]["groups"]
    assert list(block["groups"]) == order
    assert np.sum([block["groups"][g] for g in order], axis=0).tolist() == block["counts"]
    failed = [g.width for g, o in zip(grasps.values(), inputs[1], strict=True) if o == "failed"]
    assert block["groups"]["failed"] == hist_counts(failed, block).tolist()
    assert block["outside"] == 1  # the 135 mm grasp, past the 120 mm open stop
    assert block["beyond_edges"] == int(np.sum((widths < low) | (widths > high)))
    p001, p999 = np.percentile(widths, [0.1, 99.9])
    assert block["p001"] == pytest.approx(p001) and block["p999"] == pytest.approx(p999)
    assert block["span_pct"] == pytest.approx((p999 - p001) / 0.12 * 100)
    assert block["peak_pct"] == pytest.approx(p999 / 0.12 * 100)


def test_pre_grasp_widths_over_the_grasps_that_have_one(payload, inputs):
    pre = [g.pre_grasp_width for g in inputs[0].values() if g.pre_grasp_width is not None]
    block = payload["pre_grasp_width"]
    assert block["edges"] == payload["width"]["edges"]
    assert sum(block["counts"]) == len(pre)
    assert block["counts"] == hist_counts(pre, block).tolist()


def test_without_a_range_the_width_box_is_the_data_and_nothing_is_outside(inputs):
    grasps, outcomes, _, _ = inputs
    payload = analyze_grasps(grasps, outcomes=outcomes).payload
    assert payload["gripper"]["source"] == "data"
    assert payload["gripper"]["planner_low"] is None
    assert payload["width"]["outside"] == 0
    assert "width_outside" not in {entry["key"] for entry in payload["numbers"]}


def test_position_projections_count_every_grasp_on_origin_anchored_pixels(payload, inputs):
    truth = inputs[3]
    position = payload["position"]
    assert position["pixel_m"] == 0.01
    faces = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}
    for face, (u, v) in faces.items():
        block = position["projections"][face]
        nu, nv = block["shape"]
        u0, v0 = block["origin"]
        assert u0 / 0.01 == pytest.approx(round(u0 / 0.01)) and v0 / 0.01 == pytest.approx(round(v0 / 0.01))
        expected = np.zeros(nu * nv, int)
        for row in truth.values():
            i = math.floor(row["position"][u] / 0.01) - round(u0 / 0.01)
            j = math.floor(row["position"][v] / 0.01) - round(v0 / 0.01)
            expected[i * nv + j] += 1
        assert block["samples"] == expected.tolist(), face
        order = payload["source"]["groups"]
        assert np.sum([block["groups"][g] for g in order], axis=0).tolist() == block["samples"]


def test_the_area_mask_and_its_visited_share(payload, inputs):
    block = payload["position"]["projections"]["xy"]
    nu, nv = block["shape"]
    u0, v0 = block["origin"]
    (x0, y0, _), (x1, y1, _) = AREA
    centres_u = u0 + (np.arange(nu) + 0.5) * 0.01
    centres_v = v0 + (np.arange(nv) + 0.5) * 0.01
    inside = ((centres_u[:, None] >= x0) & (centres_u[:, None] <= x1) & (centres_v[None, :] >= y0)
              & (centres_v[None, :] <= y1)).astype(int)
    assert block["area"] == inside.ravel().tolist()
    assert payload["position"]["area"] == [[list(AREA[0]), list(AREA[1])]]
    samples = np.asarray(block["samples"]).reshape(nu, nv)
    numbers = {entry["key"]: entry["value"] for entry in payload["numbers"]}
    assert numbers["area_visited_pct"] == pytest.approx(100 * ((samples > 0) & (inside == 1)).sum() / inside.sum())
    closed = sum(np.asarray(block["groups"][g]).reshape(nu, nv) for g in ("picked", "failed"))
    assert numbers["area_closed_pct"] == pytest.approx(100 * ((closed > 0) & (inside == 1)).sum() / inside.sum())


def test_the_approach_sphere_tilt_and_rolls(payload, inputs):
    truth = inputs[3]
    orientation = payload["orientation"]
    assert orientation["reference"] == [0.0, 0.0, -1.0]
    sphere = orientation["sphere"]
    assert (sphere["rings"], sphere["sectors"]) == (12, 24) and sum(sphere["counts"]) == len(truth)
    straight_down = sum(1 for row in truth.values() if row["tilt"] == 0.0)
    ring0 = sum(sphere["counts"][:24])  # z = -1 is ring 0
    assert ring0 >= straight_down
    tilts = [row["tilt"] for row in truth.values()]
    assert orientation["tilt"]["counts"] == hist_counts(tilts, orientation["tilt"]).tolist()
    rolls = [math.remainder(row["roll"], 2 * math.pi) for row in truth.values()]
    assert orientation["roll"]["edges"] == [-math.pi, math.pi, 72]
    assert orientation["roll"]["counts"] == hist_counts(rolls, orientation["roll"]).tolist()
    folded = [roll % math.pi for roll in rolls]
    assert orientation["roll_folded"]["edges"] == [0.0, math.pi, 36]
    assert orientation["roll_folded"]["counts"] == hist_counts(folded, orientation["roll_folded"]).tolist()
    assert orientation["roll_shown"] == "roll_folded"
    assert orientation["tilt_roll"]["roll_edges"] == orientation["roll_folded"]["edges"]
    assert sum(orientation["tilt_roll"]["counts"]) == len(truth)
    assert sum(orientation["tilt_azimuth"]["counts"]) == len(truth)
    for key in ("sphere", "tilt", "roll", "roll_folded"):
        order = payload["source"]["groups"]
        assert np.sum([orientation[key]["groups"][g] for g in order], axis=0).tolist() == orientation[key]["counts"]


def test_an_asymmetric_claw_shows_the_full_circle(inputs):
    grasps, outcomes, _, _ = inputs
    orientation = analyze_grasps(grasps, outcomes=outcomes, symmetric_jaws=False).payload["orientation"]
    assert orientation["roll_shown"] == "roll"
    assert orientation["tilt_roll"]["roll_edges"] == [-math.pi, math.pi, 72]


def test_width_tilt_and_score(payload, inputs):
    grasps = inputs[0]
    block = payload["width_tilt"]
    assert block["x_edges"][:2] == payload["width"]["edges"][:2] and block["x_edges"][2] == 36
    assert block["y_edges"] == [0.0, math.pi, 18] and block["shape"] == [36, 18]
    inside = sum(1 for g in grasps.values() if payload["width"]["edges"][0] <= g.width <= payload["width"]["edges"][1])
    assert sum(block["counts"]) == inside
    scores = [g.score for g in grasps.values() if g.score is not None]
    assert sum(payload["score"]["counts"]) == len(scores)
    assert payload["score"]["edges"][0] == pytest.approx(min(scores))


def test_objects_most_grasps_first_with_their_success(payload, inputs):
    grasps, outcomes, _, _ = inputs
    rows = payload["objects"]
    assert [row["object_id"] for row in rows] == ["vial", "cap", "box"]
    for row in rows:
        mine = [o or "unknown" for g, o in zip(grasps.values(), outcomes, strict=True) if g.object_id == row["object_id"]]
        assert row["grasps"] == len(mine)
        assert row["outcomes"] == {o: mine.count(o) for o in payload["outcomes"]["order"] if o in mine}
        closed = mine.count("picked") + mine.count("failed")
        assert row["picked_pct"] == (pytest.approx(100 * mine.count("picked") / closed) if closed else None)


def test_headline_numbers(payload, inputs):
    grasps, outcomes, _, _ = inputs
    numbers = {entry["key"]: entry for entry in payload["numbers"]}
    assert set(numbers) == {
        "grasps", "objects", "width_span_pct", "width_peak_pct", "directions_visited_pct", "tilt_median_deg",
        "tilt_max_deg", "roll_visited_pct", "position_pixels_xy", "object_evenness_pct", "largest_object_pct",
        "width_outside", "closed", "picked_pct", "pre_grasp_width_peak_pct", "area_visited_pct", "area_closed_pct"}
    assert all(math.isfinite(entry["value"]) and entry["label"] for entry in numbers.values())
    picked = outcomes.count("picked")
    closed = picked + outcomes.count("failed")
    assert numbers["closed"]["value"] == closed
    assert numbers["picked_pct"]["value"] == pytest.approx(100 * picked / closed)
    assert numbers["grasps"]["value"] == len(grasps) and numbers["objects"]["value"] == 3
    assert numbers["tilt_max_deg"]["value"] == pytest.approx(87.0) and numbers["tilt_max_deg"]["unit"] == "deg"
    counts = np.array([19, 9, 5])
    share = counts / counts.sum()
    assert numbers["object_evenness_pct"]["value"] == pytest.approx(100 * math.exp(-(share * np.log(share)).sum()) / 3)
    assert numbers["largest_object_pct"]["value"] == pytest.approx(100 * 19 / 33)
    shown = payload["orientation"]["roll_folded"]["counts"]
    assert numbers["roll_visited_pct"]["value"] == pytest.approx(100 * np.mean(np.asarray(shown) > 0))
    assert numbers["position_pixels_xy"]["value"] == sum(1 for n in payload["position"]["projections"]["xy"]["samples"]
                                                         if n > 0)


def test_without_outcomes_every_grasp_is_unknown_and_there_is_no_success_rate(inputs):
    payload = analyze_grasps(inputs[0]).payload
    assert payload["outcomes"]["order"] == ["unknown"]
    keys = {entry["key"] for entry in payload["numbers"]}
    assert not keys & {"closed", "picked_pct", "area_visited_pct", "area_closed_pct"}


def test_group_by_object_stacks_the_histograms_by_object(inputs):
    grasps, outcomes, _, _ = inputs
    payload = analyze_grasps(grasps, outcomes=outcomes, group_by="object").payload
    assert payload["source"]["groups"] == ["vial", "cap", "box"]
    assert list(payload["width"]["groups"]) == ["vial", "cap", "box"]


def test_a_mapping_of_outcomes_and_a_tag_group(inputs):
    grasps, outcomes, tags, _ = inputs
    by_name = dict(zip(grasps, outcomes, strict=True))
    payload = analyze_grasps(grasps, outcomes=by_name, tags=tags, group_by="day").payload
    assert payload["source"]["groups"] == ["2026-11-12", "2026-11-14"]
    assert [row["outcome"] for row in payload["grasps"]] == [o or "unknown" for o in outcomes]


def test_names_from_the_header_meta_then_numbered():
    grasps = [grasp((0, 0, 0), 0.0, 0.0, 0.0, 0.02, name="first"), grasp((0, 0, 0), 0.0, 0.0, 0.0, 0.02)]
    assert [row["name"] for row in analyze_grasps(grasps).payload["grasps"]] == ["first", "grasp_1"]


def test_the_inputs_are_checked(inputs):
    grasps, outcomes, _, _ = inputs
    with pytest.raises(ValueError, match="no grasps"):
        analyze_grasps([])
    with pytest.raises(ValueError, match="frame"):
        analyze_grasps([grasp((0, 0, 0), 0, 0, 0, 0.02), grasp((0, 0, 0), 0, 0, 0, 0.02, frame="camera")])
    with pytest.raises(ValueError, match="outcomes"):
        analyze_grasps(grasps, outcomes=outcomes[:-1])
    with pytest.raises(ValueError, match="missing"):
        analyze_grasps(grasps, outcomes={"vial-01": "picked"})
    with pytest.raises(TypeError, match="GraspPose"):
        analyze_grasps(["not a grasp"])
    with pytest.raises(ValueError, match="group_by"):
        analyze_grasps(grasps, group_by="nonsense")
    with pytest.raises(ValueError, match="width_range"):
        analyze_grasps(grasps, width_range=(0.1, 0.0))
    assert isinstance(next(iter(grasps.values())), GraspPose)


def test_a_huge_set_keeps_an_even_pick_of_rows_but_counts_every_grasp(monkeypatch):
    from traj_compare.grasp_coverage import analysis

    monkeypatch.setattr(analysis, "GRASPS_MAX", 10)
    grasps = [grasp((0.01 * k, 0, 0), 0.0, 0.0, 0.0, 0.02) for k in range(40)]
    payload = analyze_grasps(grasps).payload
    assert len(payload["grasps"]) == 10 and payload["grasps_subsampled"] == 10
    assert payload["source"]["grasps"] == 40 and sum(payload["width"]["counts"]) == 40


def test_the_shared_binning_is_the_trajectory_viewers():
    """The grasp payload bins with coverage/bins.py, the module the trajectory payload uses (one copy, no drift)."""
    from traj_compare.coverage import analysis as trajectory_analysis
    from traj_compare.coverage import bins
    from traj_compare.grasp_coverage import analysis

    assert trajectory_analysis._bin_index is bins.bin_index and trajectory_analysis._grid_cells is bins.grid_cells
    assert analysis.bins is bins
