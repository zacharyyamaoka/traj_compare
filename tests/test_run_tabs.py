"""The run view's question tabs and the arm / hand parts, in Python (written before the viewers, 2026-11-19).

Contract: docs/NAVIGATION.md Part B (frozen 2026-11-19). Zach, daily note 2026-11-19 (traj compare view feedback):
the standalone and Rerun run viewers "should be the exact same thing"; "100% we need to do the tabbed model";
tab titles "super descriptive"; "split the arm and the hand into separate concerns, and each arm separately".

``traj_compare.tabs`` holds the one rule both viewers drop tabs by; ``payload["tabs"]`` and ``payload["parts"]``
carry it to them. The expected tab ids here come from the contract's "Shown when" column, written out by hand
(``expected_tab_ids``), never from ``tabs_for`` itself.

These tests are the acceptance ruler for the HTML and Rerun lanes: they must not edit this file.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from scaling_fixtures import (
    BIMANUAL_PARTS,
    DOF,
    FINGERS,
    JOINT_NAMES,
    SHAPES,
    arm_joints,
    hand_joints,
    scaling_comparison,
)
from traj_compare import Comparison, Situation
from traj_compare.analysis import analyze_comparison
from traj_compare.tabs import TABS, Tab, normalize_parts, resolve_tab, tabs_for

IDS = ["track", "where", "joints", "timing", "torque", "signals"]
TITLES = [
    "Did it track the target?",
    "Where is the error?",
    "Which joint has the error?",
    "Is it late or off the path?",
    "Feedforward or feedback?",
    "Raw signals per joint",
]
HEADINGS = [
    "How well did each run follow the target, and when was it worst?",
    "Where along the path is the tool off the target, and in which direction?",
    "Which joint contributes the most tracking error?",
    "Is the tool behind schedule (timing) or off the path (shape)?",
    "How much of the commanded torque comes from the feedforward model, and how much from feedback?",
    "Every measured joint signal: angle, speed, acceleration, torque, current",
]
SECTIONS = {
    "track": (),
    "where": ("tcp-err", "tcp-pose"),
    "joints": ("joint-err",),
    "timing": ("path",),
    "torque": ("joint-torque",),
    "signals": ("joint-q", "joint-qd", "joint-qdd", "joint-tau", "joint-current"),
}
LEGACY = {
    "Is it good?": "track",
    "Where?": "where",
    "Which joint?": "joints",
    "Timing or shape?": "timing",
    "Feedforward or feedback?": "torque",
    "Signals": "signals",
}


def expected_tab_ids(shape: str, tool: bool, torque: bool) -> list[str]:
    """NAVIGATION.md's "Shown when" column for a fixture that has a target."""

    shown = {
        "track": True,
        "where": tool,  # a tool frame exists
        "joints": DOF[shape] >= 2,
        "timing": tool,
        "torque": torque,  # a torque breakdown exists
        "signals": True,
    }
    return [tab_id for tab_id in IDS if shown[tab_id]]


COMBOS = [
    pytest.param(shape, tool, torque, id=f"{shape}-{'tool' if tool else 'notool'}-{'torque' if torque else 'notorque'}")
    for shape in SHAPES
    for tool in (True, False)
    for torque in (True, False)
]


@pytest.fixture(scope="module")
def payloads() -> dict[tuple[str, bool, bool], dict]:
    return {
        (shape, tool, torque): analyze_comparison(scaling_comparison(shape, tool=tool, torque=torque))
        for shape in SHAPES
        for tool in (True, False)
        for torque in (True, False)
    }


# ── the tab list ─────────────────────────────────────────────────────────────


def test_tabs_are_the_contract_ids_titles_and_headings_in_order():
    assert [tab.id for tab in TABS] == IDS
    assert [tab.title for tab in TABS] == TITLES
    assert [tab.heading for tab in TABS] == HEADINGS
    assert {tab.id: tuple(tab.html_sections) for tab in TABS} == SECTIONS
    assert all(isinstance(tab, Tab) for tab in TABS)


def test_a_tab_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        TABS[0].title = "Is it good?"


@pytest.mark.parametrize("shape, tool, torque", COMBOS)
def test_tabs_for_drops_a_tab_with_nothing_to_show(payloads, shape, tool, torque):
    payload = payloads[(shape, tool, torque)]
    tabs = tabs_for(payload)
    assert [tab["id"] for tab in tabs] == expected_tab_ids(shape, tool, torque)
    by_id = {tab.id: tab for tab in TABS}
    for tab in tabs:
        assert set(tab) == {"id", "title", "heading", "sections", "subtabs"}
        assert tab["title"] == by_id[tab["id"]].title
        assert tab["heading"] == by_id[tab["id"]].heading
    assert payload["tabs"] == tabs  # the payload carries the already-dropped list
    json.dumps(payload["tabs"])  # embeds in the report as JSON


@pytest.mark.parametrize("shape, tool, torque", COMBOS)
def test_a_tab_lists_only_the_sections_this_payload_draws(payloads, shape, tool, torque):
    sections = {tab["id"]: tab["sections"] for tab in payloads[(shape, tool, torque)]["tabs"]}
    assert sections["track"] == []
    # joint-tau / joint-current only with an applied torque / a current (the torque fixtures log both)
    assert sections["signals"] == (
        ["joint-q", "joint-qd", "joint-qdd", "joint-tau", "joint-current"] if torque else ["joint-q", "joint-qd", "joint-qdd"]
    )
    if tool:
        assert sections["where"] == ["tcp-err", "tcp-pose"]
        assert sections["timing"] == ["path"]
    if torque:
        assert sections["torque"] == ["joint-torque"]
    if DOF[shape] >= 2:
        assert sections["joints"] == ["joint-err"]


def test_without_a_target_there_is_no_joint_error_to_rank_so_no_joints_tab():
    comparison = dataclasses.replace(scaling_comparison("3dof", torque=False), target=None)
    ids = [tab["id"] for tab in analyze_comparison(comparison)["tabs"]]
    assert ids == ["track", "where", "timing", "signals"]  # the tool frame still shows its pose and path


def test_tool_poses_without_fk_count_as_a_tool_frame():
    t = np.linspace(0.0, 1.0, 51)
    q = np.column_stack([np.sin(t), np.cos(t)])

    def poses(offset: float) -> np.ndarray:
        frames = np.tile(np.eye(4), (t.size, 1, 1))
        frames[:, 0, 3] = q[:, 0] + offset
        return frames

    comparison = Comparison(title="poses", joint_names=["a", "b"],
                            target=Situation(name="target", t=t, q=q, poses=poses(0.0)),
                            situations=[Situation(name="run", t=t, q=q + 0.01, poses=poses(0.002))])  # fmt: skip
    assert [tab["id"] for tab in analyze_comparison(comparison)["tabs"]] == ["track", "where", "joints", "timing", "signals"]


# ── parts ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("shape", ["1dof", "3dof", "6dof"])
def test_no_parts_is_one_implicit_part_holding_every_joint(payloads, shape):
    parts = payloads[(shape, True, True)]["parts"]
    assert parts == [{"name": "All joints", "groups": [{"name": "", "joints": JOINT_NAMES[shape]}]}]


def test_bimanual_parts_are_two_arms_and_two_hands_grouped_by_finger(payloads):
    parts = payloads[("bimanual", True, True)]["parts"]
    assert [part["name"] for part in parts] == ["Left arm", "Right arm", "Left hand", "Right hand"]
    for part, side in zip(parts[:2], "lr", strict=True):
        assert part["groups"] == [{"name": "", "joints": arm_joints(side)}]  # an arm: one group named ""
    for part, side in zip(parts[2:], "lr", strict=True):
        assert [group["name"] for group in part["groups"]] == list(FINGERS)
        assert [len(group["joints"]) for group in part["groups"]] == [4, 3, 3, 3, 3]
        assert {group["name"]: group["joints"] for group in part["groups"]} == hand_joints(side)
    every = [joint for part in parts for group in part["groups"] for joint in group["joints"]]
    assert len(every) == 46 and sorted(every) == sorted(JOINT_NAMES["bimanual"])
    json.dumps(parts)


def test_parts_keep_the_callers_order_and_unnamed_joints_trail_as_other_joints():
    joints = ["j1", "j2", "j3", "j4", "j5"]
    parts = normalize_parts(joints, {"Wrist": ["j5", "j4"], "Base": ["j2"]})
    assert parts == [
        {"name": "Wrist", "groups": [{"name": "", "joints": ["j5", "j4"]}]},
        {"name": "Base", "groups": [{"name": "", "joints": ["j2"]}]},
        {"name": "Other joints", "groups": [{"name": "", "joints": ["j1", "j3"]}]},  # joint_names order
    ]
    assert normalize_parts(joints, {"All": joints}) == [{"name": "All", "groups": [{"name": "", "joints": joints}]}]


@pytest.mark.parametrize("parts", [None, {}])
def test_none_or_empty_parts_is_the_implicit_part(parts):
    assert normalize_parts(["a", "b"], parts) == [{"name": "All joints", "groups": [{"name": "", "joints": ["a", "b"]}]}]


@pytest.mark.parametrize(
    "parts, match",
    [
        pytest.param({"Arm": ["j1", "nope"]}, "nope", id="unknown-joint"),
        pytest.param({"Hand": {"thumb": ["j1", "ghost"]}}, "ghost", id="unknown-joint-in-a-finger"),
        pytest.param({"Arm": ["j1", "j1"]}, "j1", id="duplicate-in-one-part"),
        pytest.param({"Arm": ["j1", "j2"], "Wrist": ["j2"]}, "j2", id="duplicate-across-parts"),
        pytest.param({"Arm": ["j1"], "Hand": {"index": ["j1"]}}, "j1", id="duplicate-arm-and-hand"),
        pytest.param({"Arm": "j1"}, "Arm", id="a-bare-string-is-not-a-joint-list"),
        pytest.param({"Arm": []}, "Arm", id="empty-part"),
        pytest.param({"Hand": {}}, "Hand", id="hand-without-fingers"),
        pytest.param({"Hand": {"thumb": []}}, "thumb", id="empty-finger"),
        pytest.param({"Other joints": ["j1"]}, "Other joints", id="other-joints-name-taken-while-joints-are-left"),
    ],
)
def test_normalize_parts_refuses_what_it_cannot_place(parts, match):
    with pytest.raises(ValueError, match=match):
        normalize_parts(["j1", "j2", "j3"], parts)


def test_a_comparison_validates_its_parts_when_built():
    comparison = scaling_comparison("6dof", tool=False, torque=False)
    fields = {field.name: getattr(comparison, field.name) for field in dataclasses.fields(comparison)}
    with pytest.raises(ValueError, match="gripper"):
        Comparison(**{**fields, "parts": {"Arm": ["base_yaw", "gripper"]}})
    with pytest.raises(ValueError, match="elbow"):
        Comparison(**{**fields, "parts": {"Arm": ["base_yaw", "elbow"], "Wrist": ["elbow"]}})


def test_a_comparison_keeps_its_own_copy_of_the_parts():
    caller = {"Arm": ["base_yaw", "shoulder", "elbow"], "Wrist": ["wrist_1", "wrist_2", "wrist_3"]}
    comparison = dataclasses.replace(scaling_comparison("6dof", tool=False, torque=False), parts=caller)
    caller["Arm"].append("wrist_1")  # would be a duplicate; the comparison must not see it
    assert comparison.parts == {"Arm": ["base_yaw", "shoulder", "elbow"], "Wrist": ["wrist_1", "wrist_2", "wrist_3"]}
    assert [part["name"] for part in analyze_comparison(comparison)["parts"]] == ["Arm", "Wrist"]


def test_bimanual_fixture_parts_are_the_contracts():
    assert list(BIMANUAL_PARTS) == ["Left arm", "Right arm", "Left hand", "Right hand"]
    assert [len(BIMANUAL_PARTS[name]) for name in ("Left arm", "Right arm")] == [7, 7]
    for name in ("Left hand", "Right hand"):
        assert {finger: len(joints) for finger, joints in BIMANUAL_PARTS[name].items()} == {
            "thumb": 4, "index": 3, "middle": 3, "ring": 3, "little": 3,
        }  # fmt: skip


# ── resolving a tab by name ──────────────────────────────────────────────────


@pytest.mark.parametrize("tab_id, title", list(zip(IDS, TITLES, strict=True)))
def test_resolve_tab_by_id_or_title(tab_id, title):
    assert resolve_tab(tab_id).id == tab_id
    assert resolve_tab(title).id == tab_id


@pytest.mark.parametrize("legacy, tab_id", list(LEGACY.items()))
def test_resolve_tab_by_a_pre_2026_11_19_title(legacy, tab_id):
    assert resolve_tab(legacy).id == tab_id
    assert legacy in resolve_tab(tab_id).legacy_titles


def test_an_unknown_tab_says_which_exist():
    with pytest.raises(ValueError, match="joints"):
        resolve_tab("Which motor?")
