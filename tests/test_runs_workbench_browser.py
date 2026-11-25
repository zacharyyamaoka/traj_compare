"""The runs workbench's three levels in real headless Chrome (written before the code, 2026-11-24): filter the runs,
open a target (summary data, the rail's runs ticked), back keeps the filter and the tab, tick 3 runs, Open playback
(traj_compare's comparison viewer over exactly those 3 and the target), then Open in Rerun builds 3 lines.

Zach, Daily Note 2026-11-24 l.3227: "We have like the dataset view, then the target view (at this point its still just
summary data though), Then we can actually open up the playback viewer. either our custom one or the rerun one."

Needs Chrome, Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``) and the data-ui checkout (vendored by the writer).
Set ``TRAJ_COMPARE_SHOTS=<dir>`` to keep the screenshots.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from runs_workbench_fixture import write_sites
from traj_compare.runs_workbench import write_runs_workbench
from traj_compare.serve import make_handler

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
SHOTS = os.environ.get("TRAJ_COMPARE_SHOTS", "")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node") and (DATA_UI / "bin" / "data-ui.mjs").is_file()),
    reason="needs Node Playwright, Chrome and the data-ui checkout",
)

HEAD = r"""
const { chromium } = require(process.argv[2]);
const args = JSON.parse(process.argv[3]);
const out = { errors: [], steps: {} };
const shot = async (page, name) => { if (args.shots) await page.screenshot({ path: args.shots + '/' + name + '.png' }); };
(async () => {
  const browser = await chromium.launch({ executablePath: args.chrome, headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  // the check never launches a viewer: every selection post is rewritten to ?dry=1 (build the .rrd, answer, no spawn)
  await context.route('**/__rerun/**', (route) => { const u = route.request().url(); route.continue({ url: u + (u.includes('?') ? '&' : '?') + 'dry=1' }); });
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));
  // a static host answers the POSTs 501: that refusal is what the page must explain, not an error of the page
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text()) && !(args.static && /Failed to load resource/.test(m.text()))) out.errors.push(m.text()); });
  const ready = async () => { await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }); await page.waitForTimeout(400); };
  const count = () => page.evaluate(() => { const e = document.querySelector('#tc data-count'); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; });
  const tick = async (prop, value) => { await page.click(`#tc data-facets input[type=checkbox][data-p="${prop}"][data-value="${value}"]`); await page.waitForTimeout(700); };
  const targetView = () => page.evaluate(() => ({ url: location.href, lines: document.querySelectorAll('[data-tc-run]').length,
    ticked: [...document.querySelectorAll('[data-tc-run] input[type=checkbox]')].filter((c) => c.checked).map((c) => c.closest('[data-tc-run]').dataset.line),
    state: window.TV_STATE || null }));
  const openFirstTarget = async () => {
    await page.click('#tc data-tabs [role=tab]:nth-of-type(2)'); await page.waitForTimeout(1200);
    await page.click("#tc data-dashboard[tab='Targets'] tbody tr"); await page.waitForTimeout(800);
    await Promise.all([page.waitForNavigation(), page.click("#tc button[data-drill-action]:has-text('Open target view')")]);
    await ready();
  };
"""
TAIL = r"""
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((error) => { console.log(JSON.stringify({ fatal: String(error && error.stack || error), out })); process.exit(1); });
"""


def drive(tmp_path: Path, body: str, **args) -> dict:
    script = tmp_path / "driver.js"
    script.write_text(HEAD + body + TAIL)
    args = {"chrome": str(CHROME), "shots": SHOTS, **args}
    result = subprocess.run(["node", str(script), str(PLAYWRIGHT), json.dumps(args)], capture_output=True, text=True,
                            timeout=600)
    assert result.stdout.strip(), result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out
    assert out["errors"] == [], out["errors"]
    return out


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    root = tmp_path_factory.mktemp("bench")
    sites = write_sites(root)
    write_runs_workbench(sites, root / "all", title="Every run")
    return root


def serving(root: Path, handler) -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


JOURNEY = r"""
  await page.goto(args.base + '/all/index.html'); await ready();
  out.steps.count0 = await count();
  await shot(page, '1-outer');
  await tick('deployment', 'Arm cell'); out.steps.count1 = await count();
  await tick('config', 'pd'); out.steps.count2 = await count();
  await openFirstTarget();
  out.steps.target = await targetView();
  await shot(page, '2-target');
  await Promise.all([page.waitForNavigation(), page.click('#back')]); await ready();
  out.steps.back = { url: page.url(), count: await count() };
  await openFirstTarget();
  const unticked = await page.$('[data-tc-run] input[type=checkbox]:not(:checked)');
  await unticked.click(); await page.waitForTimeout(300);
  out.steps.three = await targetView();
  out.steps.playbackLabel = (await page.textContent('#playback')).trim();
  await Promise.all([page.waitForNavigation({ timeout: 120000 }), page.click('#playback')]);
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].builtPage, null, { timeout: 120000 });
  await page.waitForTimeout(800);
  await shot(page, '3-playback');
  out.steps.playback = await page.evaluate(() => {
    const data = JSON.parse(document.getElementById('traj-compare-data').textContent);
    const s = data.comparisons[0].situations;
    return { url: location.href, targets: s.filter((x) => x.role === 'target').length, measured: s.filter((x) => x.role !== 'target').map((x) => x.title),
             crumbs: [...document.querySelectorAll('[data-tc-breadcrumb] a')].map((a) => a.getAttribute('href')) };
  });
  const crumbs = await page.$$('[data-tc-breadcrumb] a');
  await Promise.all([page.waitForNavigation(), crumbs[crumbs.length - 1].click()]); await ready();
  out.steps.returned = await targetView();
  out.steps.rerunLabel = (await page.textContent('#rerun')).trim();
  await page.click('#rerun');
  await page.waitForFunction(() => window.TV_LAST_RERUN, null, { timeout: 120000 });
  out.steps.rerun = await page.evaluate(() => ({ answer: window.TV_LAST_RERUN, status: document.getElementById('status').textContent }));
  await shot(page, '4-rerun');
"""


def test_filter_target_back_playback_rerun(bench, tmp_path):
    pytest.importorskip("rerun")
    spawned = []
    httpd, base = serving(bench, make_handler(bench, spawn=spawned.append))
    try:
        steps = drive(tmp_path, JOURNEY, base=base)["steps"]
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert steps["count0"] == "20 of 20 runs"
    assert steps["count1"] == "12 of 20 runs"  # the arm's 12 lines
    assert steps["count2"] == "6 of 20 runs"  # its pd lines: 3 targets x 2 repeats
    target = steps["target"]
    assert "target.html?" in target["url"] and "keep=" in target["url"] and "back=" in target["url"]
    assert target["lines"] == 4  # every run of the target listed (2 configs x 2 repeats) ...
    assert len(target["ticked"]) == 2  # ... the rail's (pd) ticked
    back = steps["back"]
    assert "deployment=" in back["url"] and "config=pd" in back["url"] and back["url"].endswith("#tab=targets")
    assert back["count"] == "6 of 20 runs"
    assert len(steps["three"]["ticked"]) == 3 and steps["playbackLabel"].endswith("3 runs")
    playback = steps["playback"]
    assert "/playback/" in playback["url"] and playback["targets"] == 1 and len(playback["measured"]) == 3
    assert any("target.html?" in href for href in playback["crumbs"])
    assert sorted(steps["returned"]["ticked"]) == sorted(steps["three"]["ticked"])  # the crumb carries the 3 back
    assert steps["rerunLabel"].endswith("3 runs")
    answer = steps["rerun"]["answer"]
    assert answer["ok"] and answer["n"] == 3, answer
    assert len(answer["entities"]) == 3 + 1 and not spawned
    assert "Built" in steps["rerun"]["status"]


STATIC = r"""
  await page.goto(args.url); await ready();
  await page.click('#rerun'); await page.waitForTimeout(1500);
  out.steps.rerun = await page.textContent('#status');
  await page.click('#playback'); await page.waitForTimeout(1500);
  out.steps.playback = await page.textContent('#status');
  out.steps.url = page.url();
"""


def test_on_a_static_host_both_playback_buttons_say_what_they_need(bench, tmp_path):
    rows = json.loads((bench / "all" / "runs.json").read_text("utf-8"))["rows"]
    row = rows[0]

    class Static(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(bench), **k)

        def log_message(self, *a):
            pass

    httpd, base = serving(bench, Static)
    try:
        steps = drive(tmp_path, STATIC, url=f"{base}/all/target.html?site={row['site']}&target={row['target_slug']}",
                      static=True)["steps"]
    finally:
        httpd.shutdown()
        httpd.server_close()
    for said in (steps["rerun"], steps["playback"]):
        assert "python -m traj_compare.serve" in said, said
    assert "target.html" in steps["url"]  # it stayed on the page and said why
