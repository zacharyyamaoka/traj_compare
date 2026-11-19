"""A check group gets its own Rerun tab and stays out of every other view (written before the code, 2026-11-19).

Zach, on the CAN 11 envelope report in Rerun: "make a separate page tab for "Camera Check", here you show
the camera information (on the other tabs it can just be the joint information)". The camera's ArUco
line is a check on the encoder, not a run to grade: its 15 fps noise named it the worst run and its
green spikes dominated every error plot. ``checks={"camera": "Camera Check"}`` names the situation
group; its runs leave every other view, the main scorecard, the RMS bars and the worst-run heat path,
and get one tab of their own beside every other run.

Recording values are read back with Rerun's own RrdReader / `rerun rrd print`, never our writer.
"""

from __future__ import annotations

import numpy as np
import pytest

rr = pytest.importorskip("rerun")
from rerun.chunk import RrdReader  # noqa: E402

from traj_compare import Situation, write_comparison_report  # noqa: E402
from traj_compare.analysis import analyze_comparison  # noqa: E402
from traj_compare.report import _colorize  # noqa: E402
from traj_compare.rerun_export import blueprint_path, layout_blueprint, write_rrd  # noqa: E402

from test_rerun_export import rrd_print, three_way  # noqa: E402
from test_rerun_layouts import QUESTIONS_TABS, _find_tabs, _names  # noqa: E402

CHECKS = {"camera": "Camera Check"}
CAMERA_TITLE = "Camera · ArUco tag 8"
CAMERA_NOTE = "D405 at 15 fps, latency 60 ms; camera - encoder 1.70° RMS"


def camera_checked(with_data: bool = True):
    comparison = three_way()
    real = comparison.situations[-1]
    if with_data:
        noise = 0.02 * np.sin(40.0 * real.t)[:, None]  # far worse than sim or real: it would be the "worst run"
        camera = Situation(name="camera", title=CAMERA_TITLE, t=real.t, q=real.q + noise, group="camera",
                           group_title="Camera", note=CAMERA_NOTE)
    else:
        camera = Situation(name="camera", title="Camera · ArUco", note="tag tracking lost on this step", group="camera",
                           group_title="Camera")
    comparison.situations = [*comparison.situations, camera]
    return comparison


def _payload(comparison):
    payload = analyze_comparison(comparison)
    _colorize(payload)
    return payload


def _views(container) -> list:
    """Every view in a blueprint subtree (containers have ``contents`` lists of children; views have ``origin``)."""

    if hasattr(container, "origin"):
        return [container]
    found = []
    for child in getattr(container, "contents", None) or []:
        found += _views(child)
    return found


def _shows(view, run: str) -> bool:
    """Whether ``view``'s contents query lets ``run``'s subtree in: no ``- .../<run>/**`` rule excludes it."""

    rules = view.contents if isinstance(view.contents, list) else []
    return not any(rule.startswith("- ") and rule.rstrip("/*").endswith(f"/{run}") for rule in rules)


def _text(path, entity: str) -> str:
    for chunk in RrdReader(path).stream():
        if chunk.entity_path == entity:
            batch = chunk.to_record_batch()
            names = batch.schema.names
            column = next(name for name in names if name.endswith(":text"))
            return "".join(str(value[0] if isinstance(value, list) else value) for value in batch.column(names.index(column)).to_pylist())
    raise AssertionError(f"{entity} not in {path}")


def _container_names(rbl) -> set[str]:
    """The container (tab) names in a saved .rbl's blueprint store, read with Rerun's RrdReader."""

    reader = RrdReader(rbl)
    names: set[str] = set()
    for chunk in reader.stream(store=reader.blueprints()[0]):
        batch = chunk.to_record_batch()
        for index, column in enumerate(batch.schema.names):
            if column == "ContainerBlueprint:display_name":
                names |= {str(value[0] if isinstance(value, list) else value) for value in batch.column(index).to_pylist() if value}
    return names


def test_questions_layout_gets_a_camera_check_tab_and_the_other_tabs_show_joints_only():
    blueprint = layout_blueprint("questions", _payload(camera_checked()), {}, checks=CHECKS)
    stage, questions = blueprint.root_container.contents
    assert _names(questions) == [*QUESTIONS_TABS, "Camera Check"]
    plotted = [view for view in _views(stage) + _views(questions)
               if type(view).__name__ in ("TimeSeriesView", "Spatial3DView", "BarChartView")]
    check_tab = questions.contents[-1]
    in_check = {id(view) for view in _views(check_tab)}
    outside = [view for view in plotted if id(view) not in in_check]
    assert outside, "the main tabs and the stage have plots"
    for view in outside:
        assert not _shows(view, "camera"), f"{view.name!r} still shows the camera run"
        assert _shows(view, "real") and _shows(view, "sim"), f"{view.name!r} hides a joint run"
    check_views = [view for view in _views(check_tab) if type(view).__name__ in ("TimeSeriesView", "Spatial3DView")]
    assert any(type(view).__name__ == "TimeSeriesView" and str(view.origin).startswith("/positions/") for view in check_views)
    assert any(type(view).__name__ == "TimeSeriesView" and str(view.origin).startswith("/error/") for view in check_views)
    for view in check_views:
        assert _shows(view, "camera") and _shows(view, "real"), f"{view.name!r}: the check compares the camera with the encoder"
    assert any(type(view).__name__ == "TextDocumentView" and str(view.origin) == "/checks/camera/scorecard" for view in _views(check_tab))


def test_evo_layout_gets_the_same_check_tab():
    tabs = layout_blueprint("evo", _payload(camera_checked()), {}, checks=CHECKS).root_container
    assert _names(tabs)[-1] == "Camera Check"
    for container in tabs.contents[:-1]:
        for view in _views(container):
            if type(view).__name__ in ("TimeSeriesView", "Spatial3DView", "BarChartView"):
                assert not _shows(view, "camera"), f"{view.name!r} still shows the camera run"


def test_the_check_tab_opens_by_name_and_no_checks_changes_nothing():
    payload = _payload(camera_checked())
    questions = layout_blueprint("questions", payload, {}, tab="Camera Check", checks=CHECKS).root_container.contents[1]
    assert questions.active_tab == len(QUESTIONS_TABS)
    plain = layout_blueprint("questions", payload, {}).root_container.contents[1]
    assert _names(plain) == QUESTIONS_TABS  # without checks the camera is one more run, as before
    assert all(_shows(view, "camera") for view in _views(plain))
    assert len(_find_tabs(plain)) == 2


def test_main_scorecard_bars_and_heat_path_leave_the_check_out(tmp_path):
    rrd = write_rrd(camera_checked(), tmp_path / "s01.rrd", checks=CHECKS)
    scorecard = _text(rrd, "/scorecard")
    assert CAMERA_TITLE not in scorecard  # the camera can no longer be the "worst run"
    assert "Worst run: Real" in scorecard or "Worst run: Sim" in scorecard
    check = _text(rrd, "/checks/camera/scorecard")
    assert "Camera Check" in check and CAMERA_TITLE in check and CAMERA_NOTE in check
    assert "Real" in check  # beside the runs it checks
    printed = rrd_print(rrd)
    assert "/worst/joint_deg/camera" in printed  # the check tab still plots it
    bars = next(chunk for chunk in RrdReader(rrd).stream() if chunk.entity_path == "/stats/tool_rms_mm")
    batch = bars.to_record_batch()
    values = batch.column(next(i for i, name in enumerate(batch.schema.names) if name.endswith(":values"))).to_pylist()
    tensor = values[0][0] if isinstance(values[0], list) else values[0]  # Rerun stores the bars as a tensor {shape, buffer}
    assert tensor["shape"] == [2] and len(tensor["buffer"]) == 2  # sim and real, not the camera


def test_a_check_with_only_a_note_still_gets_its_tab_saying_why(tmp_path):
    comparison = camera_checked(with_data=False)
    questions = layout_blueprint("questions", _payload(comparison), {}, checks=CHECKS).root_container.contents[1]
    assert _names(questions)[-1] == "Camera Check"
    rrd = write_rrd(comparison, tmp_path / "s03.rrd", checks=CHECKS)
    assert "tag tracking lost on this step" in _text(rrd, "/checks/camera/scorecard")


def test_a_comparison_without_the_group_gets_no_check_tab():
    questions = layout_blueprint("questions", _payload(three_way()), {}, checks=CHECKS).root_container.contents[1]
    assert _names(questions) == QUESTIONS_TABS


def test_report_passes_the_checks_to_every_recording_and_layout_file(tmp_path):
    report = write_comparison_report([camera_checked()], tmp_path, rerun=True, rerun_checks=CHECKS)
    rrd = report.parent / "rerun" / f"{camera_checked().name}.rrd"
    assert CAMERA_TITLE not in _text(rrd, "/scorecard")
    for layout in ("questions", "evo"):
        assert "Camera Check" in _container_names(blueprint_path(rrd, layout)), f"{layout}.rbl has no Camera Check tab"
