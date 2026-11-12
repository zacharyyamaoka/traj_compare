"""The Rerun projection and the report's "Open in Rerun" backdoor (written before the code, 2026-11-10).

Decision being implemented: Tracking-Run Data — data-ui vs Rerun (2026-10-26): the dataset is
the contract, our viewer and Rerun are projections, and every analysis view carries an
"Open in Rerun" button. One recording per comparison, situations as entity prefixes, the
blueprint embedded in the .rrd, one SDK pin (0.40.0) written beside the file.

The read-back goes through Rerun's own CLI (`rerun rrd verify` / `rrd print`), not through
our writer, so the test can fail when the file is wrong.
"""

import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from traj_compare import Comparison, Situation, write_comparison_report
from traj_compare.analysis import analyze_comparison

rr = pytest.importorskip("rerun")

from traj_compare.rerun_export import RERUN_SDK_VERSION, write_rrd  # noqa: E402

from test_report import extract_payload  # noqa: E402


def translation_fk(q: np.ndarray) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, :2, 3] = q
    return poses


def three_way(reference_title: str = "Target") -> Comparison:
    t = np.linspace(0.0, 2.0, 201)
    q = np.column_stack([0.3 * t, 0.1 * np.sin(np.pi * t)])
    return Comparison(
        title="Belt pick",
        joint_names=["j1", "j2"],
        target=Situation(name="target", title=reference_title, t=t, q=q),
        situations=[
            Situation(name="sim", title="Sim", t=t, q=q + [0.002, 0.0], tau=np.ones_like(q)),
            Situation(name="real", title="Real", t=t, q=q + [0.0, -0.003]),
        ],
        fk=translation_fk,
        vec_dirs=[("Conveyor", np.array([0.0, 1.0, 0.0]))],
        tcp_frame="TCP",
    )


def rrd_print(path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "rerun", "rrd", "print", "-v", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    return result.stdout + result.stderr


def test_sdk_pin_is_the_one_version():
    assert RERUN_SDK_VERSION == "0.40.0" == rr.__version__


def test_write_rrd_logs_the_standard_entity_layout(tmp_path):
    path = write_rrd(three_way(), tmp_path / "belt_pick.rrd")
    verify = subprocess.run(
        [sys.executable, "-m", "rerun", "rrd", "verify", str(path)],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert verify.returncode == 0, verify.stdout + verify.stderr

    printed = rrd_print(path)
    for entity in (
        "/error/joint/j1/sim",  # signed joint error, target - run, SI
        "/error/joint/j2/real",
        "/error/tool/position_mm/sim",
        "/error/tool/rotation_deg/real",  # degrees only (Zach: never milliradians)
        "/error/tool/rotation_deg/real",  # the same error in degrees: the entity is data, the view shows degrees
        "/position/j1/target",
        "/position/j1/sim",
        "/vec/Conveyor/sim",  # signed speed along the named direction
        "/world/target",
        "/world/sim",
        "/notes",  # the metric table as markdown
    ):
        assert entity in printed, f"{entity} missing from the .rrd"
    assert "Blueprint" in printed  # the layout travels inside the file


def test_rrd_error_values_match_the_html_payload(tmp_path):
    comparison = three_way()
    path = write_rrd(comparison, tmp_path / "belt_pick.rrd")
    printed = rrd_print(path)
    assert "/error/joint/j2/real" in printed
    payload = analyze_comparison(comparison)
    real = next(entry for entry in payload["situations"] if entry["name"] == "real")
    # target - real on j2 is +0.003 rad everywhere; the .rrd logs SI radians
    values = [v for v in real["plot"]["err_q"][1] if v is not None]
    np.testing.assert_allclose(values, 0.003, atol=1e-12)


def test_report_writes_one_rrd_per_comparison_and_the_open_in_rerun_controls(tmp_path):
    first = three_way()
    second = three_way()
    second.title, second.name = "Sim as reference", "sim_as_reference"
    report = write_comparison_report([first, second], tmp_path, rerun=True)

    payload = extract_payload(report.read_text("utf-8"))
    for page in payload["comparisons"]:
        entry = page["rerun"]
        rrd = tmp_path / entry["rrd"]
        assert rrd.is_file() and rrd.suffix == ".rrd"
        assert entry["sdk"] == RERUN_SDK_VERSION
        # the copy-able command: one line, absolute path, the pinned viewer
        assert entry["command"] == f"uvx --from rerun-sdk=={RERUN_SDK_VERSION} rerun {rrd.resolve()}"
    html = report.read_text("utf-8")
    assert "Open in Rerun" in html


def test_report_without_rerun_has_no_button_and_no_files(tmp_path):
    report = write_comparison_report([three_way()], tmp_path, rerun=False)
    payload = extract_payload(report.read_text("utf-8"))
    assert payload["comparisons"][0].get("rerun") is None
    assert not list(tmp_path.rglob("*.rrd"))


def test_reference_title_names_the_minuend():
    """Sim vs real has no target: the reference is just whichever run sits in `target`."""
    payload = analyze_comparison(three_way(reference_title="Sim (reference)"))
    assert payload["reference_title"] == "Sim (reference)"


def test_serve_sends_cors_and_private_network_headers(tmp_path):
    from traj_compare.serve import make_handler

    (tmp_path / "a.rrd").write_bytes(b"rrd")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, spawn=lambda argv: None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base}/a.rrd", timeout=10) as response:
            assert response.read() == b"rrd"
            assert response.headers["Access-Control-Allow-Origin"] in ("*", "https://app.rerun.io")
        preflight = urllib.request.Request(
            f"{base}/a.rrd",
            method="OPTIONS",
            headers={
                "Origin": "https://app.rerun.io",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        with urllib.request.urlopen(preflight, timeout=10) as response:
            assert response.headers["Access-Control-Allow-Private-Network"] == "true"
    finally:
        server.shutdown()


def test_serve_open_endpoint_launches_the_pinned_viewer_on_a_file_inside_the_root(tmp_path):
    from traj_compare.serve import make_handler

    (tmp_path / "rerun").mkdir()
    (tmp_path / "rerun" / "a.rrd").write_bytes(b"rrd")
    launched: list[list[str]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, spawn=launched.append))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(f"{base}/__rerun/open?rrd=rerun/a.rrd", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read())
        assert body["ok"] is True
        assert launched and launched[0][-1] == str((tmp_path / "rerun" / "a.rrd").resolve())
        assert any(re.fullmatch(rf"rerun-sdk=={re.escape(RERUN_SDK_VERSION)}", arg) for arg in launched[0])
        # nothing outside the served root can be opened
        escape = urllib.request.Request(f"{base}/__rerun/open?rrd=../../etc/passwd", method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(escape, timeout=10)
        assert error.value.code in (400, 403, 404)
        assert len(launched) == 1
    finally:
        server.shutdown()


def test_notes_markdown_shows_degrees_and_mm_never_milliradians():
    """The /notes page is human-facing: verdict limits, latency RMS and goal errors read in degrees (the tool in mm)."""
    from robot_msgs.compare import JointTolerance, Tolerances

    from traj_compare.rerun_export import _notes_markdown

    comparison = three_way()
    comparison.tolerances = Tolerances(
        path=tuple(JointTolerance(name=joint, position=0.001) for joint in ("j1", "j2")),
        goal=tuple(JointTolerance(name=joint, position=0.001) for joint in ("j1", "j2")),
    )
    comparison.estimate_latency = True
    comparison.goal_band = 0.001
    markdown = _notes_markdown(analyze_comparison(comparison))
    for heading in ("## Verdicts", "## Estimated latency", "## Goal"):
        assert heading in markdown
    assert "> 0.0573°" in markdown  # the verdict's limit (0.001 rad), in degrees
    assert "mrad" not in markdown and "(SI)" not in markdown


def test_write_rrd_layout_hooks_swap_the_blueprint_and_add_entities(tmp_path):
    """blueprint= replaces the default layout, application_id= keeps layouts apart, extra= logs more entities."""
    import rerun.blueprint as rrb

    calls = []

    def layout(payload, videos):
        calls.append(payload["title"])
        return rrb.Blueprint(rrb.TextDocumentView(origin="/notes", name="Only the notes"))

    def extra(recording, payload, t0):
        recording.log("/extra/scorecard", rr.TextDocument("# hello"), static=True)

    path = write_rrd(three_way(), tmp_path / "alt.rrd", blueprint=layout, application_id="traj_compare-alt", extra=extra)
    printed = rrd_print(path)
    assert calls == ["Belt pick"]
    assert "/extra/scorecard" in printed
    assert "traj_compare-alt" in printed
    # the one-view layout replaced the default (which has a view per joint, error channel and video)
    assert printed.count("@ViewBlueprint:class_identifier") == 1
