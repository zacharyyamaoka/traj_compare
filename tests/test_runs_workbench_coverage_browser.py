"""Coverage inside the runs workbench, in real headless Chrome (feedback fb-5defddb0, written before the code, 2026-11-25).

Zach, Daily Note 2026-11-23: *"I need to basically like integrate this into the viewer ... trajectory Coverage Viewer
Where you can put in like datasets or single trajectories ... a page you can see standalone or just quickly get there
from the traj compare stuff"*. The journey (tests/test_runs_workbench_coverage.py holds the Python side):

1. The workbench's **Coverage** tab shows the arm's coverage page inside the viewer (an iframe of the site's own page, which
   draws), says how many of the deployment's targets the rail keeps runs of (and recounts on a tick), names the
   deployment without a page, and its "Open on its own" link is the standalone page.
2. An arm target's **target view** links to that page with its trajectory highlighted (one trajectory in its dataset:
   the Trajectories tab, its row selected); the pendulum's target view, whose site has no coverage page, has no link.

Needs Chrome, Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``) and the data-ui checkout. ``TRAJ_COMPARE_SHOTS=<dir>`` keeps
the screenshots.
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

from runs_workbench_fixture import ARM, PENDULUM, write_sites
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
const shot = async (page, name) => { if (args.shots) await page.screenshot({ path: args.shots + '/coverage-tab-' + name + '.png' }); };
(async () => {
  const browser = await chromium.launch({ executablePath: args.chrome, headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) out.errors.push(m.text()); });
  // a failed load is named by its URL (the console line above does not say which)
  page.on('response', (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) out.errors.push(r.status() + ' ' + r.url()); });
  const ready = async () => { await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }); await page.waitForTimeout(500); };
  const tick = async (prop, value) => { await page.click(`#tc data-facets input[type=checkbox][data-p="${prop}"][data-value="${value}"]`); await page.waitForTimeout(900); };
  const tab = async (name) => { await page.click(`#tc data-tabs [role=tab]:text-is(${JSON.stringify(name)})`); await page.waitForTimeout(1200); };
  const view = () => page.evaluate(() => { const el = document.querySelector("#tc [data-tc-view='tc-coverage']"); return el ? { ...el.tcOverview, text: el.textContent.replace(/\s+/g, ' ').trim() } : null; });
  // the coverage page inside the tab: its own root, title and a heatmap that drew (non-white pixels)
  const framed = async () => {
    const handle = await page.$("#tc [data-tc-view='tc-coverage'] iframe[data-tc-coverage-frame]");
    if (!handle) return null;
    const box = await handle.boundingBox();
    const frame = await handle.contentFrame();
    await frame.waitForSelector('[data-cov-page]', { timeout: 30000 });
    await frame.waitForTimeout(800);
    return { box, url: frame.url(), ...(await frame.evaluate(() => ({
      title: (document.querySelector('[data-cov-title]') || {}).textContent || '',
      leaves: !!document.querySelector('base[target="_top"]'),  // its breadcrumb opens in the window, not in the tab
      tabs: [...document.querySelectorAll('[data-cov-tab]')].map((b) => b.dataset.covTab),
      // the shown tab's figures drew: marks in an SVG, or a canvas with non-white pixels
      shown: [...document.querySelectorAll('[data-cov-view]')].filter((s) => !s.hidden).map((s) => s.dataset.covView),
      inked: [...document.querySelectorAll('[data-cov-view]:not([hidden]) [data-cov-figure]')].some((fig) =>
        fig.querySelector('svg path, svg rect, svg polyline, svg line') || [...fig.querySelectorAll('canvas')].some((c) => {
          if (!c.width || !c.height) return false;
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 0 && (d[i] < 240 || d[i + 1] < 240 || d[i + 2] < 240)) return true;
          return false;
        })),
    }))) };
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
    root = tmp_path_factory.mktemp("coverage-tab-browser")
    sites = write_sites(root, coverage=(ARM,))
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


TAB = r"""
  await page.goto(args.base + '/all/index.html'); await ready();
  await tab('Coverage');
  out.steps.view0 = await view();
  out.steps.frame0 = await framed();
  await shot(page, '1-tab');
  const open = await page.$("#tc [data-tc-view='tc-coverage'] a[data-tc-coverage-open]");
  out.steps.open = open ? await open.evaluate((a) => a.href) : null;
  await tick('split', 'holdout');
  out.steps.view1 = await view();
  await shot(page, '2-holdout');
"""


def test_the_coverage_tab_shows_the_page_in_the_viewer_and_counts_the_rails_targets(bench, served, tmp_path):
    out = drive(tmp_path, TAB, base=served)["steps"]
    view0 = out["view0"]
    assert view0 is not None, "no tc-coverage view on the Coverage tab"
    assert view0["shown"] == ARM
    assert [(card["deployment"], card["kept"], card["of"]) for card in view0["cards"]] == [(ARM, 3, 3)]
    assert view0["missing"] == [PENDULUM]
    assert PENDULUM in view0["text"]  # the deployment without a page is named, never silently absent
    frame = out["frame0"]
    assert frame is not None, "the Coverage tab embeds no coverage page"
    assert frame["url"].startswith(served + "/arm/coverage/index.html")
    assert "Arm cell" in frame["title"]
    assert frame["leaves"]
    assert frame["shown"] and frame["inked"], ("the embedded coverage page drew nothing", frame)
    assert frame["box"]["height"] >= 400 and frame["box"]["width"] >= 800, frame["box"]  # room to read it, in the tab
    assert out["open"] == served + "/arm/coverage/index.html"
    holdout = {row["target_slug"] for row in rows_of(bench) if row["deployment"] == ARM and row.get("split") == "holdout"}
    assert [(card["deployment"], card["kept"], card["of"]) for card in out["view1"]["cards"]] == [(ARM, len(holdout), 3)]


TARGET = r"""
  await page.goto(args.base + '/all/target.html?site=arm&target=' + encodeURIComponent(args.arm));
  await page.waitForSelector('#title', { timeout: 30000 }); await page.waitForTimeout(800);
  const link = await page.$('a[data-tc-coverage-link]');
  out.steps.href = link ? await link.evaluate((a) => a.href) : null;
  await shot(page, '3-target-view');
  if (link) {
    await link.click();
    await page.waitForSelector('[data-cov-page]', { timeout: 30000 }); await page.waitForTimeout(1200);
    out.steps.page = await page.evaluate(() => ({
      url: location.pathname,
      tab: [...document.querySelectorAll('[data-cov-view]')].filter((s) => !s.hidden).map((s) => s.dataset.covView),
      selected: [...document.querySelectorAll('[data-cov-view="trajectories"] tr.selected')].map((tr) => tr.textContent),
    }));
    await shot(page, '4-coverage-highlighted');
  }
  await page.goto(args.base + '/all/target.html?site=pendulum&target=' + encodeURIComponent(args.pendulum));
  await page.waitForSelector('#title', { timeout: 30000 }); await page.waitForTimeout(800);
  out.steps.pendulumLink = await page.$$eval('a[data-tc-coverage-link]', (els) => els.filter((a) => !a.hidden).length);
"""


def test_a_target_view_opens_its_own_trajectory_on_the_coverage_page(bench, served, tmp_path):
    rows = rows_of(bench)
    arm = next(row for row in rows if row["deployment"] == ARM and row["target"] == "swing-02 · 1x")
    pendulum = next(row for row in rows if row["deployment"] == PENDULUM)
    out = drive(tmp_path, TARGET, base=served, arm=arm["target_slug"], pendulum=pendulum["target_slug"])["steps"]
    assert out["href"], "the arm target view has no coverage link"
    assert out["href"].startswith(served + "/arm/coverage/index.html#")
    page = out["page"]
    assert page["url"] == "/arm/coverage/index.html"
    assert page["tab"] == ["trajectories"]
    assert len(page["selected"]) == 1 and "swing-02 · 1x" in page["selected"][0], page["selected"]
    assert out["pendulumLink"] == 0
