"""The Rerun ``questions`` layout carries the shared question tabs (written before the layout, 2026-11-19).

Contract: docs/NAVIGATION.md Part B (frozen 2026-11-19). Zach, daily note 2026-11-19 (traj compare view feedback):
"designing a different run viewer for standalone and rerun is a bit silly ... they should be the exact same
thing"; tab titles "super descriptive"; "split the arm and the hand into separate concerns, and each arm
separately".

- the ``questions`` tabs are ``traj_compare.tabs`` titles, dropped by ``tabs_for`` (the HTML's own rule);
- ``layout_blueprint(..., tab=)`` takes an id, the new title or a pre-2026-11-19 title;
- with parts, each per-joint tab (joints, torque, signals) nests one tab per part, ``<part> · <n> joints``;
- ``/stats/joint_rms/<part>`` holds the ranking bars of each part, the joint order in the view title;
- every view title in the joints tab names its unit and says "error";
- ``evo`` is unchanged.

Values are read back with Rerun's own RrdReader, never through our writer. These tests are the acceptance
ruler for the Rerun lane: it must not edit this file.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

rr = pytest.importorskip("rerun")
from rerun.chunk import RrdReader  # noqa: E402

from scaling_fixtures import BIMANUAL_PART_LABELS, BIMANUAL_PARTS, DOF, SHAPES, scaling_comparison  # noqa: E402
from test_rerun_layouts import _find_tabs, _names  # noqa: E402
from traj_compare.analysis import analyze_comparison  # noqa: E402
from traj_compare.report import _colorize  # noqa: E402
from traj_compare.rerun_export import _part, _short, layout_blueprint, write_rrd  # noqa: E402
from traj_compare.tabs import TABS, tabs_for  # noqa: E402

PART_TAB = re.compile(r" · \d+ joints?$")
SIGNAL_TABS = ["Angle [°]", "Speed [°/s]", "Applied torque [N·m]"]


def _payload(shape: str, tool: bool = True, torque: bool = True) -> dict:
    payload = analyze_comparison(scaling_comparison(shape, tool=tool, torque=torque))
    _colorize(payload)
    return payload


def _questions(payload: dict, **kwargs):
    """The outermost Tabs of the questions layout (beside the stage when there is one)."""
    return _find_tabs(layout_blueprint("questions", payload, {}, **kwargs).root_container)[0]


def _tab(questions, tab_id: str):
    title = next(tab.title for tab in TABS if tab.id == tab_id)
    matches = [child for child in questions.contents if getattr(child, "name", None) == title]
    assert matches, f"no {title!r} tab; tabs: {_names(questions)}"
    return matches[0]


def _views(container, kind: str) -> list:
    """Every view of type ``kind`` under ``container``, depth first."""
    found = [container] if type(container).__name__ == kind else []
    for child in getattr(container, "contents", None) or []:
        if hasattr(child, "contents") or hasattr(child, "origin"):
            found += _views(child, kind)
    return found


def _signature(container, depth: int = 0) -> list[tuple]:
    origin = getattr(container, "origin", None)
    rows = [(depth, type(container).__name__, getattr(container, "name", None), None if origin is None else str(origin))]
    for child in getattr(container, "contents", None) or []:
        if hasattr(child, "contents") or hasattr(child, "origin"):
            rows += _signature(child, depth + 1)
    return rows


def _entities(path) -> dict[str, list]:
    """Entity path -> its BarChart values (one list per logged row), read with Rerun's own reader."""
    found: dict[str, list] = {}
    for chunk in RrdReader(path).stream():
        entity = str(chunk.entity_path)
        values = found.setdefault(entity, [])
        batch = chunk.to_record_batch()
        if "BarChart:values" in batch.schema.names:
            for row in batch.column(batch.schema.names.index("BarChart:values")).to_pylist():
                if row:
                    values.append(row[0]["buffer"])
    return found


def _mentions_in_order(title: str, joints: list[str]) -> bool:
    """Each joint (as named, or as the views shorten it) appears in ``title``, in order."""
    position = 0
    for joint in joints:
        hits = [title.find(spelling, position) for spelling in (joint, _short(joint))]
        hits = [hit for hit in hits if hit >= 0]
        if not hits:
            return False
        position = min(hits) + 1
    return True


# ── the tab list ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "shape, tool, torque",
    [pytest.param(shape, tool, torque, id=f"{shape}-{'tool' if tool else 'notool'}-{'torque' if torque else 'notorque'}")
     for shape in SHAPES for tool in (True, False) for torque in (True, False)],
)  # fmt: skip
def test_questions_tabs_are_the_shared_titles_dropped_by_the_shared_rule(shape, tool, torque):
    payload = _payload(shape, tool, torque)
    assert _names(_questions(payload)) == [tab["title"] for tab in tabs_for(payload)]


def test_a_tab_opens_by_its_id_its_title_or_its_pre_2026_11_19_title():
    payload = _payload("3dof")
    tabs = tabs_for(payload)
    assert [tab["id"] for tab in tabs] == ["track", "where", "joints", "timing", "torque", "signals"]
    for index, shown in enumerate(tabs):
        tab = next(tab for tab in TABS if tab.id == shown["id"])
        for name in (tab.id, tab.title, *tab.legacy_titles):
            assert _questions(payload, tab=name).active_tab == index, name
    with pytest.raises(ValueError):
        _questions(payload, tab="Which motor?")


def test_signals_sub_tabs_name_signal_and_unit():
    with_torque = _tab(_questions(_payload("3dof")), "signals")
    # the torque fixture also records motor current, which gets its own sub-tab (NAVIGATION.md C1, 2026-11-20)
    assert any(_names(tabs) == [*SIGNAL_TABS, "Motor current [A]"] for tabs in _find_tabs(with_torque))
    without = _tab(_questions(_payload("3dof", torque=False)), "signals")
    assert any(_names(tabs) == SIGNAL_TABS[:2] for tabs in _find_tabs(without))  # no applied torque logged


# ── parts ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tab_id", ["joints", "torque", "signals"])
def test_bimanual_per_joint_tabs_nest_one_tab_per_part(tab_id):
    container = _tab(_questions(_payload("bimanual")), tab_id)
    nested = [_names(tabs) for tabs in _find_tabs(container)]
    assert BIMANUAL_PART_LABELS in nested, f"no part tabs {BIMANUAL_PART_LABELS} under {tab_id!r}; nested tabs: {nested}"


@pytest.mark.parametrize("shape", ["3dof", "6dof"])
@pytest.mark.parametrize("tab_id", ["joints", "torque", "signals"])
def test_one_implicit_part_draws_no_part_tabs(shape, tab_id):
    container = _tab(_questions(_payload(shape)), tab_id)
    labels = [name for tabs in _find_tabs(container) for name in _names(tabs) if name and PART_TAB.search(name)]
    assert labels == []


@pytest.mark.parametrize("shape", ["3dof", "bimanual"])
def test_every_joint_error_view_names_its_unit_and_says_error(shape):
    joints = _tab(_questions(_payload(shape)), "joints")
    series = _views(joints, "TimeSeriesView")
    assert len(series) >= DOF[shape], f"{len(series)} time-series views for {DOF[shape]} joints"
    for view in series:
        assert "error" in view.name and "[°]" in view.name, f"view title {view.name!r} must name the signal and its unit"


@pytest.mark.parametrize("shape", ["6dof", "bimanual"])
def test_the_joints_tab_ranks_each_part_from_its_joint_rms_bars(shape):
    payload = _payload(shape)
    joints = _tab(_questions(payload), "joints")
    bars = {str(view.origin): view.name for view in _views(joints, "BarChartView")}
    for part in payload["parts"]:
        origin = f"/stats/joint_rms/{_part(part['name'])}"
        assert origin in bars, f"no ranking bars at {origin}; bar views: {sorted(bars)}"
        names = [joint for group in part["groups"] for joint in group["joints"]]
        assert _mentions_in_order(bars[origin], names), f"{origin}: the view title must give the joint order: {bars[origin]!r}"


@pytest.mark.parametrize("shape", ["1dof", "6dof", "bimanual"])
def test_joint_rms_per_part_is_logged_in_the_recording(tmp_path, shape):
    payload = _payload(shape)
    entities = _entities(write_rrd(scaling_comparison(shape), tmp_path / f"{shape}.rrd", layout="questions"))
    logged = {entity: values for entity, values in entities.items() if entity.startswith("/stats/joint_rms/")}
    if DOF[shape] < 2:
        assert logged == {}, "one joint has nothing to rank"
        return
    expected = {f"/stats/joint_rms/{_part(part['name'])}": part for part in payload["parts"]}
    assert set(logged) == set(expected)
    for entity, part in expected.items():
        count = sum(len(group["joints"]) for group in part["groups"])
        assert logged[entity], f"{entity} logs no bar chart"
        values = np.asarray(logged[entity][-1], dtype=float)
        assert values.shape == (count,), f"{entity}: {values.shape[0]} bars for {count} joints"
        assert np.all(np.isfinite(values)) and np.all(values >= 0.0)


def test_bimanual_parts_are_the_fixtures():
    assert [_part(name) for name in BIMANUAL_PARTS] == [_part(label.split(" · ")[0]) for label in BIMANUAL_PART_LABELS]


# ── evo is unchanged ─────────────────────────────────────────────────────────

# The evo blueprint of the 1-DOF fixture (tool + torque) as it was before this contract (2026-11-19 @ 3362cda26).
EVO_1DOF = [
    (0, "Tabs", None, None),
    (1, "Vertical", "Visualization", None),
    (2, "Spatial3DView", "Reference path coloured by the worst run's tool error (green → red at the largest error), drawn up to the playhead", "/"),
    (2, "Horizontal", None, None),
    (3, "TimeSeriesView", "TCP position error [mm]", "/error/tool/position_mm"),
    (3, "BarChartView", "Tool RMS error per run [mm] — 0 Sim · 1 Real 1 · 2 Real 2 · 3 Real 3", "/stats/tool_rms_mm"),
    (1, "Horizontal", "Trajectories", None),
    (2, "Spatial3DView", "Robots + paths", "/"),
    (2, "Vertical", None, None),
    (3, "TimeSeriesView", "TCP x [mm]", "/tcp/x_mm"),
    (3, "TimeSeriesView", "TCP y [mm]", "/tcp/y_mm"),
    (3, "TimeSeriesView", "TCP z [mm]", "/tcp/z_mm"),
    (1, "Grid", "Joint error", None),
    (2, "TimeSeriesView", "pivot error [°]", "/error/positions/pivot"),
    (1, "Grid", "Along / across", None),
    (2, "TimeSeriesView", "error x [mm]", "/error/tool/x_mm"),
    (2, "TimeSeriesView", "error y [mm]", "/error/tool/y_mm"),
    (2, "TimeSeriesView", "error z [mm]", "/error/tool/z_mm"),
    (2, "TimeSeriesView", "contour error [mm]", "/error/tool/contour_mm"),
    (2, "TimeSeriesView", "lag time [ms]", "/error/tool/lag_time_ms"),
    (2, "TimeSeriesView", "speed along Conveyor [m/s]", "/vec/Conveyor"),
    (1, "Vertical", "Torque", None),
    (2, "Horizontal", None, None),
    (3, "TimeSeriesView", "pivot: Real 2 — target, commanded, feedforward, feedback, applied [N·m]", "/torque/pivot"),
    (3, "TimeSeriesView", "pivot: feedback, every run [N·m]", "/torque/pivot"),
    (3, "BarChartView", "pivot: feedback share of the command [%] — 0 Sim · 1 Real 1 · 2 Real 2 · 3 Real 3", "/stats/fb_share/pivot"),
    (1, "Horizontal", "Stats", None),
    (2, "TextDocumentView", "Scorecard", "/scorecard"),
    (2, "TextDocumentView", "Full statistics", "/notes"),
    (1, "DataframeView", "Raw data", "/error"),
]  # fmt: skip


def test_evo_is_unchanged_for_one_joint():
    assert _signature(layout_blueprint("evo", _payload("1dof"), {}).root_container) == EVO_1DOF


def test_evo_is_unchanged_with_46_motors_no_part_tabs_one_row_per_joint():
    payload = _payload("bimanual")
    evo = layout_blueprint("evo", payload, {}).root_container
    assert _names(evo) == ["Visualization", "Trajectories", "Joint error", "Along / across", "Torque", "Stats", "Raw data"]
    assert len(_find_tabs(evo)) == 1  # evo nests no tabs, so no part tabs
    joint_error = next(child for child in evo.contents if child.name == "Joint error")
    assert [(view.name, str(view.origin)) for view in joint_error.contents] == [
        (f"{_short(joint)} error [°]", f"/error/positions/{_part(joint)}") for joint in payload["joint_names"]
    ]
    torque = next(child for child in evo.contents if child.name == "Torque")
    assert len(torque.contents) == 46 and all(len(row.contents) == 3 for row in torque.contents)
