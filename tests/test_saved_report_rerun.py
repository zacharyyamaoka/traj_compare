"""Saved comparison recordings use the stock Rerun exporter and local launcher."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest

from test_rerun_export import three_way
from test_viewer3d_dropdown import CHROME, PLAYWRIGHT, pytestmark as browser_required
from traj_compare import write_comparison_report
from traj_compare.serve import make_handler


@contextmanager
def running(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=10)


def open_report(base, report, index=0, **kwargs):
    params = urlencode({"report": report, "comparison": index})
    request = urllib.request.Request(f"{base}/__rerun/open?{params}", method="POST", **kwargs)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def test_server_reuses_the_exact_binary_recording(tmp_path):
    case = three_way()
    case.name = "A & B's collision-free run β"
    nested = tmp_path / "scope space" / "another's folder"
    report = write_comparison_report(case, nested / "picked # timing.html", rerun=True)
    recording = nested / "rerun" / f"{case.name}.rrd"
    contents = recording.read_bytes()
    launches = []
    with running(make_handler(tmp_path, spawn=launches.append)) as base:
        answer = open_report(base, report.relative_to(tmp_path).as_posix())
        assert answer["ok"]
        assert shlex.split(answer["command"]) == launches[0]
        assert launches[0][-1] == str(recording.resolve())
    assert recording.read_bytes() == contents


def test_server_builds_selected_comparison_and_rejects_wrong_origin_or_path(tmp_path):
    first = three_way()
    second = three_way(reference_title="Filtered target")
    second.name = "filtered"
    report = write_comparison_report([first, second], tmp_path / "archive copy" / "snapshot.html")
    assert not list(tmp_path.rglob("*.rrd"))
    launches = []
    with running(make_handler(tmp_path, spawn=launches.append)) as base:
        report_name = report.relative_to(tmp_path).as_posix()
        for invalid in ("../snapshot.html", str(report)):
            with pytest.raises(urllib.error.HTTPError) as error:
                open_report(base, invalid)
            assert error.value.code in (400, 403)
        with pytest.raises(urllib.error.HTTPError) as error:
            open_report(base, report_name, headers={"Origin": "https://elsewhere.invalid"})
        assert error.value.code == 403
        assert not launches
        assert open_report(base, report_name, index=1)["ok"]
        assert open_report(base, report_name, index=1)["ok"]
    recording = Path(launches[0][-1])
    assert len(launches) == 2 and launches[1] == launches[0]
    assert recording.name.endswith("-2.rrd")
    assert list(tmp_path.rglob("*.rrd")) == [recording]
    completed = subprocess.run(
        [sys.executable, "-m", "rerun", "rrd", "verify", str(recording)],
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_html_at_recording_path_is_not_reused(tmp_path):
    comparison = three_way()
    report = write_comparison_report(comparison, tmp_path, rerun=True)
    false_recording = tmp_path / "rerun" / f"{comparison.name}.rrd"
    html = b"<!doctype html><title>404 from static hosting</title>"
    false_recording.write_bytes(html)
    launches = []
    with running(make_handler(tmp_path, spawn=launches.append)) as base:
        assert open_report(base, report.name)["ok"]
    recording = Path(launches[0][-1])
    assert recording != false_recording and recording.read_bytes().startswith(b"RRF2")
    assert false_recording.read_bytes() == html


def test_builds_publish_recording_and_blueprints_together(tmp_path, monkeypatch):
    from traj_compare import rerun_report

    report = write_comparison_report(three_way(), tmp_path)
    original_writer = rerun_report.write_rrd
    started = threading.Barrier(3)
    release = threading.Event()

    def staged_writer(comparison, file, **kwargs):
        file.write_bytes(b"RRF2" + bytes(8))
        started.wait(timeout=10)
        assert release.wait(timeout=10)
        return original_writer(comparison, file, **kwargs)

    monkeypatch.setattr(rerun_report, "write_rrd", staged_writer)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(rerun_report.report_recording, report) for _ in range(2)]
        try:
            started.wait(timeout=10)
            cache = tmp_path / "rerun"
            assert not [path for path in cache.iterdir() if not path.name.startswith(".")]
            assert not any(future.done() for future in pending)
        finally:
            release.set()
        first, second = [future.result(timeout=15) for future in pending]
    assert first == second
    assert all(rerun_report.blueprint_path(first, name).is_file() for name in rerun_report.LAYOUTS)
    assert sorted(cache.iterdir()) == [first.parent]


def test_directory_routes_to_its_report_when_it_has_no_index(tmp_path):
    folder = tmp_path / "report folder"
    write_comparison_report(three_way(), folder)
    launches = []
    with running(make_handler(tmp_path, spawn=launches.append)) as base:
        assert open_report(base, "report folder/")["ok"]
    assert Path(launches[0][-1]).read_bytes().startswith(b"RRF2")


def test_trusted_server_reports_absolute_command_when_generation_fails(tmp_path, monkeypatch):
    from traj_compare import rerun_report

    report = write_comparison_report(three_way(), tmp_path / "nested β's" / "saved # report.html")
    launches = []

    def unavailable(*args, **kwargs):
        raise ImportError("recording SDK unavailable")

    monkeypatch.setattr(rerun_report, "report_recording", unavailable)
    with running(make_handler(tmp_path, spawn=launches.append)) as base:
        with pytest.raises(urllib.error.HTTPError) as error:
            open_report(base, report.relative_to(tmp_path).as_posix())
        assert error.value.code == 500
        response = json.load(error.value)
    assert response["error"] == "recording SDK unavailable"
    assert shlex.split(response["command"]) == ["traj-compare-rerun", str(report), "--comparison", "0", "--open"]
    assert not launches


DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage();
  const commands = [];
  for (const location of process.argv.slice(4)) {
    await page.goto(location, {waitUntil: 'domcontentloaded'});
    await page.locator('[data-tc-rerun-pin-open]').click();
    const command = page.locator('[data-tc-rerun-pin-pop] code');
    await command.waitFor({ state: 'visible' });
    commands.push({
      command: await command.textContent(),
      message: await page.locator('[data-tc-rerun-pin-pop] p').textContent()
    });
  }
  console.log(JSON.stringify(commands));
  await browser.close();
})().catch(err => { console.error(err); process.exitCode = 1; });
"""


@browser_required
def test_file_and_static_host_show_a_copyable_cli_for_the_saved_report(tmp_path):
    report = write_comparison_report(three_way(), tmp_path / "nested β's" / "saved # report.html")
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER)
    from functools import partial
    from urllib.parse import quote

    with running(partial(SimpleHTTPRequestHandler, directory=tmp_path)) as base:
        completed = subprocess.run(
            ["node", str(driver), str(PLAYWRIGHT), str(CHROME), report.as_uri(),
             f"{base}/{quote(report.relative_to(tmp_path).as_posix())}"],
            capture_output=True, text=True, timeout=60, check=True,
        )
    local, static = json.loads(completed.stdout)
    for result, expected in ((local, str(report)), (static, report.name)):
        assert shlex.split(result["command"]) == ["traj-compare-rerun", expected, "--comparison", "0", "--open"]
    assert "Download this report" in static["message"]
    assert not list(tmp_path.rglob("*.rrd"))


def _close_time_comparison():
    import numpy as np

    from traj_compare import Comparison, RobotDisplay, Situation

    t = [0.0, 0.25000004, 0.25000037, 0.75]
    q = [[0.0], [0.1], [0.3], [0.75]]

    def poses(joints):
        out = np.tile(np.eye(4), (len(joints), 1, 1))
        out[:, 0, 3] = joints[:, 0]
        return out

    robot = RobotDisplay(
        ["link"], [np.array([[[0, 0, 0], [.1, 0, 0], [0, .1, 0]]])],
        link_fk=lambda joints: poses(joints)[:, None],
    )
    reference = Situation("target", t=t, q=q, qddd=[[5.0], [None], [3.0], [7.0]],
                          channels={"load": [1.0, 2.0, 3.0, 4.0]})
    run = Situation("run", t=t, q=q)
    return Comparison("Close timestamp test", ["j1"], [run], target=reference, robot=robot, fk=poses)


def test_report_time_axes_keep_distinct_submicrosecond_samples(tmp_path):
    from test_report import extract_payload

    case = _close_time_comparison()
    page = write_comparison_report(case, tmp_path)
    payload = extract_payload(page.read_text())["comparisons"][0]
    assert payload["plot_t"] == case.target.t.tolist()
    for key in ("three", "robot_track"):
        assert payload["situations"][0][key]["t"] == case.target.t.tolist()


def test_saved_recording_coalesces_legacy_times_with_aligned_signals(tmp_path, monkeypatch):
    from traj_compare import rerun_report

    report = write_comparison_report(_close_time_comparison(), tmp_path)
    html = report.read_text()
    match = rerun_report._DATA.search(html)
    document = json.loads(match[1])
    payload = document["comparisons"][0]
    payload["plot_t"] = [round(t, 6) for t in payload["plot_t"]]
    for entry in payload["situations"]:
        for key in ("three", "robot_track"):
            entry[key]["t"] = [round(t, 6) for t in entry[key]["t"]]
    report.write_text(html[:match.start(1)] + json.dumps(document) + html[match.end(1):])
    saved_payload = {}
    original_writer = rerun_report.write_rrd

    def read_aligned(comparison, path, *, payload, **options):
        saved_payload.update(payload)
        return original_writer(comparison, path, payload=payload, **options)

    monkeypatch.setattr(rerun_report, "write_rrd", read_aligned)
    recording = rerun_report.report_recording(report)
    assert recording.is_file()
    assert saved_payload["plot_t"] == [0.0, 0.25, 0.75]
    target = saved_payload["situations"][0]
    assert target["plot"]["q"] == [[0.0, 0.3, 0.75]]
    assert target["plot"]["qddd"] == [[5.0, None, 7.0]]
    assert target["channels"]["load"] == [[1.0, 3.0, 4.0]]
    for key in ("three", "robot_track"):
        assert target[key]["t"] == saved_payload["plot_t"]
        assert len(target[key]["p"]) == len(target[key]["quat"]) == 3
