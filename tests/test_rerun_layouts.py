"""Named Rerun layouts — "questions" (default) and "evo" — and the user's choice between them (written before the code, 2026-11-11).

Zach picked two of the five babble layouts (reports/media/traj-compare-rerun-layouts-2026-11-11):
"evo" (evo's own Rerun layout + one full-screen tab per analysis) and "questions" (a pinned 3D +
camera stage, question-named tabs). Both ship, named, and the user picks: an argument, an env var,
or a config file. Every .rrd carries one layout embedded and the other as a .rbl beside it.

Values are read back with Rerun's own RrdReader, never through our writer.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

rr = pytest.importorskip("rerun")
from rerun.chunk import RrdReader  # noqa: E402

from robot_msgs.compare import JointTolerance, PoseTolerance, Tolerances  # noqa: E402
from traj_compare import CameraOverlay, Comparison, Situation, write_comparison_report  # noqa: E402
from traj_compare.analysis import analyze_comparison  # noqa: E402
from traj_compare.report import _colorize  # noqa: E402
from traj_compare.rerun_export import (  # noqa: E402
    DEFAULT_LAYOUT,
    LAYOUTS,
    default_layout,
    layout_blueprint,
    viewer_argv,
    write_rrd,
)

from test_report import extract_payload  # noqa: E402
from test_rerun_export import rrd_print, three_way  # noqa: E402

# The shared question-tab titles (docs/NAVIGATION.md Part B, 2026-11-19: "super descriptive"); the old ones still
# open a tab by name (tab="Which joint?" below).
QUESTIONS_TABS = ["Did it track the target?", "Where is the error?", "Which joint has the error?",
                  "Is it late or off the path?", "Raw signals per joint"]


def _scalars(path: Path, entity: str) -> np.ndarray:
    values: list[float] = []
    for chunk in RrdReader(path).stream():
        if chunk.entity_path != entity:
            continue
        batch = chunk.to_record_batch()
        names = batch.schema.names
        if "Scalars:scalars" in names:
            values += [row[0] for row in batch.column(names.index("Scalars:scalars")).to_pylist() if row]
    return np.asarray(values, dtype=float)


def _names(container) -> list[str]:
    return [getattr(child, "name", None) for child in container.contents]


def _find_tabs(container):
    """Every Tabs container in a blueprint tree, outermost first."""
    found = []
    if type(container).__name__ == "Tabs":
        found.append(container)
    for child in getattr(container, "contents", None) or []:
        found += _find_tabs(child)
    return found


def toleranced() -> Comparison:
    comparison = three_way()
    comparison.tolerances = Tolerances(
        path=tuple(JointTolerance(name=joint, position=0.002) for joint in ("j1", "j2")),
        goal=tuple(JointTolerance(name=joint, position=0.001) for joint in ("j1", "j2")),
    )
    comparison.tcp_tolerances = Tolerances(path=PoseTolerance(position=0.0025), goal=PoseTolerance(position=0.001))
    return comparison


@pytest.fixture
def no_preference(monkeypatch, tmp_path):
    monkeypatch.delenv("TRAJ_COMPARE_RERUN_LAYOUT", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"


def test_two_named_layouts_and_questions_is_the_default(no_preference):
    assert set(LAYOUTS) == {"questions", "evo"}
    assert DEFAULT_LAYOUT == "questions"
    assert default_layout() == "questions"


def test_preference_from_config_file_then_env_var(no_preference, monkeypatch):
    config = no_preference / "traj_compare" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('rerun_layout = "evo"\n')
    assert default_layout() == "evo"
    monkeypatch.setenv("TRAJ_COMPARE_RERUN_LAYOUT", "questions")
    assert default_layout() == "questions"  # the env var beats the file
    monkeypatch.setenv("TRAJ_COMPARE_RERUN_LAYOUT", "nope")
    with pytest.raises(ValueError, match="questions"):
        default_layout()  # an unknown name says which names exist


def test_questions_layout_pins_the_stage_and_names_its_tabs_by_question():
    payload = analyze_comparison(three_way())
    _colorize(payload)
    blueprint = layout_blueprint("questions", payload, {})
    root = blueprint.root_container
    assert type(root).__name__ == "Horizontal"
    stage, questions = root.contents
    assert type(stage).__name__ == "Vertical"  # 3D (+ camera when there is one) on the left, never a tab
    assert any(type(view).__name__ == "Spatial3DView" for view in stage.contents)
    assert _names(questions) == QUESTIONS_TABS
    nested = _find_tabs(questions)[1]
    assert _names(nested) == ["Angle [°]", "Speed [°/s]", "Applied torque [N·m]"]  # the sim carries torque in three_way


def test_evo_layout_follows_evo_and_drops_tabs_with_nothing_to_show():
    payload = analyze_comparison(three_way())
    _colorize(payload)
    tabs = layout_blueprint("evo", payload, {}).root_container
    assert type(tabs).__name__ == "Tabs"
    names = _names(tabs)
    assert names[0] == "Visualization" and names[-1] == "Raw data"  # evo_ape --rerun's two tabs, first and last
    assert names == ["Visualization", "Trajectories", "Joint error", "Along / across", "Stats", "Raw data"]
    assert "Video" not in names  # no video in this comparison
    with_video = _names(layout_blueprint("evo", payload, {"real": Path("real.mp4")}).root_container)
    assert "Video" in with_video


def test_write_rrd_embeds_one_layout_and_writes_every_layout_beside_it(tmp_path, no_preference):
    rrd = write_rrd(three_way(), tmp_path / "belt_pick.rrd", layout="evo")
    for name in LAYOUTS:
        assert (tmp_path / f"belt_pick.{name}.rbl").is_file()
    assert viewer_argv(rrd)[-1] == str(rrd.resolve())  # the embedded layout needs no extra file
    argv = viewer_argv(rrd, layout="questions")
    assert argv[-2:] == [str(rrd.resolve()), str((tmp_path / "belt_pick.questions.rbl").resolve())]
    with pytest.raises(ValueError):
        viewer_argv(rrd, layout="nope")


def test_rrd_shows_joint_angles_in_degrees_and_keeps_the_tool_in_mm(tmp_path):
    rrd = write_rrd(three_way(), tmp_path / "belt_pick.rrd")
    # target - real on j2 is +0.003 rad everywhere (three_way); the view reads degrees
    np.testing.assert_allclose(_scalars(rrd, "/error/positions/j2/real"), math.degrees(0.003), atol=1e-9)
    np.testing.assert_allclose(_scalars(rrd, "/error/tool/position_mm/real"), 3.0, atol=1e-6)
    printed = rrd_print(rrd)
    assert "rotation_mrad" not in printed  # Zach's rule: degrees, never milliradians


def test_tolerance_bands_are_logged_as_shaded_measurements(tmp_path):
    rrd = write_rrd(toleranced(), tmp_path / "belt_pick.rrd")
    printed = rrd_print(rrd)
    for entity in ("/error/positions/j1/tolerance", "/error/tool/position_mm/tolerance", "/worst/joint_deg/tolerance"):
        assert entity in printed, f"{entity} missing"
    assert "Measurements:variances" in printed  # the band is a ±1σ shading around the centre


def test_scorecard_events_and_worst_run_heat_path_are_in_the_recording(tmp_path):
    printed = rrd_print(write_rrd(toleranced(), tmp_path / "belt_pick.rrd"))
    for entity in ("/scorecard", "/events", "/heat_worst", "/trail_worst", "/stats/tool_rms_mm", "/worst/joint_deg/real"):
        assert entity in printed, f"{entity} missing"


def test_report_offers_both_layouts_with_the_preferred_one_first(tmp_path, no_preference, monkeypatch):
    monkeypatch.setenv("TRAJ_COMPARE_RERUN_LAYOUT", "evo")
    report = write_comparison_report([three_way()], tmp_path, rerun=True)
    entry = extract_payload(report.read_text("utf-8"))["comparisons"][0]["rerun"]
    assert entry["layout"] == "evo"
    assert [layout["name"] for layout in entry["layouts"]] == ["evo", "questions"]
    for layout in entry["layouts"]:
        assert (tmp_path / layout["rbl"]).is_file()
    preferred, other = entry["layouts"]
    assert preferred["command"].endswith(".rrd")  # embedded: the bare file opens in it
    assert other["command"].endswith(str((tmp_path / other["rbl"]).resolve()))
    assert entry["command"] == preferred["command"]


def _serve(root, launched):
    from traj_compare.serve import make_handler

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, spawn=launched.append))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_serve_opens_the_chosen_layout(tmp_path):
    (tmp_path / "rerun").mkdir()
    (tmp_path / "rerun" / "a.rrd").write_bytes(b"rrd")
    (tmp_path / "rerun" / "a.evo.rbl").write_bytes(b"rbl")
    launched: list[list[str]] = []
    server, base = _serve(tmp_path, launched)
    try:
        request = urllib.request.Request(f"{base}/__rerun/open?rrd=rerun/a.rrd&layout=evo", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            assert json.loads(response.read())["ok"] is True
        assert launched[0][-2:] == [str((tmp_path / "rerun" / "a.rrd").resolve()),
                                    str((tmp_path / "rerun" / "a.evo.rbl").resolve())]
        for query, codes in (("layout=nope", (400,)), ("layout=questions", (404,))):  # unknown name; no .rbl on disk
            bad = urllib.request.Request(f"{base}/__rerun/open?rrd=rerun/a.rrd&{query}", method="POST")
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad, timeout=10)
            assert error.value.code in codes
        assert len(launched) == 1
    finally:
        server.shutdown()


def _clip(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:size=160x90:rate=10",
         "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0", str(path)],
        check=True,
    )  # fmt: skip


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_camera_overlay_is_composited_into_one_video_rerun_plays(tmp_path):
    _clip(tmp_path / "real.mp4", "red")
    _clip(tmp_path / "sim.mp4", "blue")
    comparison = three_way()
    comparison.overlays = [CameraOverlay(name="front", real_video="real.mp4", sims=[("Sim", "sim.mp4")], t0_s=0.2)]
    rrd = write_rrd(comparison, tmp_path / "rerun" / "belt_pick.rrd", video_root=tmp_path)
    composite = tmp_path / "rerun" / "belt_pick.overlay-front.mp4"
    assert composite.is_file()
    # the mix is neither input: red and blue at partial opacity
    frame = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(composite), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    r, g, b = frame[0], frame[1], frame[2]
    assert r > 60 and b > 60, (r, g, b)
    printed = rrd_print(rrd)
    assert "/video/overlay-front" in printed and "VideoFrameReference" in printed
    payload = analyze_comparison(comparison)
    _colorize(payload)
    stage = layout_blueprint("questions", payload, {}, overlays=["front"]).root_container.contents[0]
    assert any(type(view).__name__ == "Spatial2DView" and str(view.origin) == "/video/overlay-front" for view in stage.contents)


def test_a_layout_can_open_on_a_named_tab():
    payload = analyze_comparison(three_way())
    _colorize(payload)
    tabs = layout_blueprint("evo", payload, {}, tab="Joint error").root_container
    assert tabs.active_tab == 2
    questions = layout_blueprint("questions", payload, {}, tab="Which joint?").root_container.contents[1]
    assert questions.active_tab == 2
    with pytest.raises(ValueError, match="Raw data"):
        layout_blueprint("evo", payload, {}, tab="Nope")
