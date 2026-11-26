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
    commands.push(await command.textContent());
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
    for command in json.loads(completed.stdout):
        assert shlex.split(command) == ["traj-compare-rerun", str(report), "--comparison", "0", "--open"]
    assert not list(tmp_path.rglob("*.rrd"))
