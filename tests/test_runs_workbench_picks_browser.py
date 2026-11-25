"""The runs workbench's two picks in real headless Chrome (written before the code, 2026-11-25): the Overview's tiles
draw the oracle's numbers (tests/runs_picks_oracle.py, the rounds' rule) before and after a rail tick, each tile's Open
goes to its page, "Does sim match real?" answers and recounts on the rail, says so calmly when the filter leaves no pair,
and a pair's row opens the target view with exactly that pair ticked, whose ‹ link returns to the tab and the filter.

Needs Chrome, Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``) and the data-ui checkout. ``TRAJ_COMPARE_SHOTS=<dir>``
keeps the screenshots.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from runs_picks_fixture import RIG, write_three_sites
from runs_picks_oracle import config_order, overview_tiles, pairs, pairs_answer
from runs_workbench_fixture import ARM, PENDULUM
from traj_compare.runs_workbench import write_runs_workbench
from traj_compare.serve import make_handler

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
SHOTS = os.environ.get("TRAJ_COMPARE_SHOTS", "")
T1 = "Does sim match real?"

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node") and (DATA_UI / "bin" / "data-ui.mjs").is_file()),
    reason="needs Node Playwright, Chrome and the data-ui checkout",
)

HEAD = r"""
const { chromium } = require(process.argv[2]);
const args = JSON.parse(process.argv[3]);
const out = { errors: [], steps: {} };
const shot = async (page, name) => { if (args.shots) await page.screenshot({ path: args.shots + '/picks-' + name + '.png' }); };
(async () => {
  const browser = await chromium.launch({ executablePath: args.chrome, headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.route('**/__rerun/**', (route) => { const u = route.request().url(); route.continue({ url: u + (u.includes('?') ? '&' : '?') + 'dry=1' }); });
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) out.errors.push(m.text()); });
  const ready = async () => { await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }); await page.waitForTimeout(500); };
  const tick = async (prop, value) => { await page.click(`#tc data-facets input[type=checkbox][data-p="${prop}"][data-value="${value}"]`); await page.waitForTimeout(900); };
  const tab = async (name) => { await page.click(`#tc data-tabs [role=tab]:text-is(${JSON.stringify(name)})`); await page.waitForTimeout(1200); };
  const activeTab = () => page.evaluate(() => { const t = document.querySelector('#tc data-tabs [role=tab][aria-selected=true]'); return t ? t.textContent.trim() : null; });
  const tiles = () => page.evaluate(() => Object.fromEntries([...document.querySelectorAll("#tc data-dashboard[tab='Overview'] [data-tc-view='tc-tile']")]
    .map((el) => [el.tcOverview.tile, el.tcOverview.numbers])));
  const answer = () => page.evaluate(() => { const el = document.querySelector("#tc [data-tc-view='tc-pairs']"); return el ? { ...el.tcOverview, text: el.textContent.trim() } : null; });
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
    root = tmp_path_factory.mktemp("picks-browser")
    sites = write_three_sites(root)
    write_runs_workbench(sites, root / "all", title="Every run")
    return root


@pytest.fixture
def served(bench):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bench, spawn=lambda *a: None))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def rows_of(bench: Path) -> list[dict]:
    return json.loads((bench / "all" / "runs.json").read_text("utf-8"))["rows"]


def same(page: dict, oracle: dict) -> None:
    """Every number the oracle states equals the page's (lists element by element; names exactly)."""
    for tile, want in oracle.items():
        got = page[tile]
        for key, value in want.items():
            mine = got[key]
            if key == "frontier":
                assert sorted(mine) == value, (tile, key, mine, value)
            elif isinstance(value, list):
                assert [m if isinstance(m, str) else pytest.approx(m, rel=1e-9) for m in mine] == \
                    [v if isinstance(v, str) else pytest.approx(v, rel=1e-9) for v in value], (tile, key)
            elif isinstance(value, float):
                assert mine == pytest.approx(value, rel=1e-9), (tile, key, mine, value)
            else:
                assert mine == value, (tile, key, mine, value)


TILES = r"""
  await page.goto(args.base + '/all/index.html'); await ready();
  out.steps.tiles0 = await tiles();
  await shot(page, '1-overview');
  await tick('deployment', args.arm);
  out.steps.tiles1 = await tiles();
  await shot(page, '2-overview-arm');
  // each tile's Open goes to its page (the stock §55 chip), then the Overview again
  out.steps.opened = [];
  const n = await page.$$eval("#tc data-dashboard[tab='Overview'] .dd-panel", (els) => els.length);
  for (let i = 1; i <= n; i += 1) {
    await page.click(`#tc data-dashboard[tab='Overview'] .dd-panel:nth-of-type(${i}) button.dd-open`); await page.waitForTimeout(1200);
    out.steps.opened.push(await activeTab());
    await tab('Overview');
  }
"""


def test_the_tiles_draw_the_oracles_numbers_before_and_after_a_tick_and_each_opens_its_page(bench, served, tmp_path):
    steps = drive(tmp_path, TILES, base=served, arm=ARM)["steps"]
    rows = rows_of(bench)
    deployments = [ARM, PENDULUM, RIG]
    order = config_order(rows, deployments)
    unfiltered = overview_tiles(rows, order=order, deployments=deployments)
    assert set(steps["tiles0"]) == set(unfiltered) == {"best", "speed", "cost", "coverage", "worst", "left"}
    same(steps["tiles0"], unfiltered)
    arm = overview_tiles([r for r in rows if r["deployment"] == ARM], order=order, deployments=deployments)
    same(steps["tiles1"], arm)
    assert steps["tiles1"]["left"]["runs"] == 12 and steps["tiles0"]["left"]["runs"] == len(rows)
    assert steps["opened"] == ["League", "Speed", "Trade-off", "Config × dataset", "Worst targets", "Targets"]


PAIRS = r"""
  await page.goto(args.base + '/all/index.html'); await ready();
  await tab(args.t1); await page.waitForTimeout(800);
  out.steps.all = await answer();
  await shot(page, '3-sim-real');
  await tick('deployment', args.pendulum);
  out.steps.pendulum = await answer();
  await tick('deployment', args.pendulum); await tick('deployment', args.arm);
  out.steps.arm = await answer();
  await shot(page, '4-sim-real-empty');
  await tick('deployment', args.arm); await tick('deployment', args.rig);
  out.steps.rig = await answer();
  // the pair that disagrees most: its row, then the stock drill's Open target view
  await page.click(`#tc data-dashboard[tab=${JSON.stringify(args.t1)}] tbody tr`); await page.waitForTimeout(800);
  await Promise.all([page.waitForNavigation(), page.click("#tc button[data-drill-action]:has-text('Open target view')")]);
  await ready();
  out.steps.target = await page.evaluate(() => ({ url: location.href,
    ticked: [...document.querySelectorAll('[data-tc-run] input[type=checkbox]')].filter((c) => c.checked).map((c) => Number(c.closest('[data-tc-run]').dataset.line)) }));
  await shot(page, '5-target');
  await Promise.all([page.waitForNavigation(), page.click('#back')]); await ready(); await page.waitForTimeout(800);
  out.steps.back = { url: page.url(), tab: await activeTab(), answer: await answer() };
"""


def test_sim_vs_real_answers_recounts_says_when_empty_and_a_pair_opens_its_target_view(bench, served, tmp_path):
    steps = drive(tmp_path, PAIRS, base=served, t1=T1, arm=ARM, pendulum=PENDULUM, rig=RIG)["steps"]
    rows = rows_of(bench)
    every = pairs(rows)

    def check(got, kept):
        want = pairs_answer(every, kept, "sim")
        assert got["n"] == want["n"] and got["worse"] == want["worse"], (got, want)
        assert got["median"] == pytest.approx(want["median"], rel=1e-9)

    check(steps["all"], rows)
    assert steps["all"]["n"] == 11 and steps["all"]["against"] == "sim"
    check(steps["pendulum"], [r for r in rows if r["deployment"] == PENDULUM])
    assert steps["pendulum"]["median"] == 3.0
    # the filter leaves no pair: one calm sentence, no number to misread
    assert steps["arm"]["n"] == 0 and "no real run" in steps["arm"]["text"].lower()
    rig = [r for r in rows if r["deployment"] == RIG]
    check(steps["rig"], rig)
    # the row on top disagrees most (apart = max(ratio, 1/ratio)); the target view opens with exactly its two lines
    rig_pairs = [p for p in every if p["deployment"] == RIG and p["against"] == "sim"]
    top = max(rig_pairs, key=lambda p: max(p["ratio"], 1 / p["ratio"]))
    assert "target.html?" in steps["target"]["url"] and "back=" in steps["target"]["url"]
    assert sorted(steps["target"]["ticked"]) == top["lines"]
    back = steps["back"]
    assert "deployment=Rig" in back["url"] and "#tab=" in back["url"] and back["tab"] == T1
    check(back["answer"], rig)
