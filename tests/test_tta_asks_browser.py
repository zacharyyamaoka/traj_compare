"""The TTA asks a browser has to judge (written before the code, 2026-11-24): dark mode, ``#run=``, the stage's fold
button at 390 px, and the dataset page's Rerun links, footer and number formatting. Real headless Chrome.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT`` = its package directory); skipped otherwise. Set
``TRAJ_COMPARE_SHOTS=<dir>`` to keep the screenshots (the 2026-11-24 report uses them).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import write_comparison_report
from traj_compare.dataset import Run, write_dataset_report

from test_tta_asks import comparison

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
SHOTS = os.environ.get("TRAJ_COMPARE_SHOTS", "")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

HEAD = r"""
const { chromium } = require(process.argv[2]);
const args = JSON.parse(process.argv[3]);
const shot = async (page, name) => { if (args.shots) await page.screenshot({ path: args.shots + '/' + name + '.png', fullPage: false }); };
(async () => {
  const browser = await chromium.launch({ executablePath: args.chrome, headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [] };
  const open = async (url, options) => {
    const context = await browser.newContext(Object.assign({ viewport: { width: 1280, height: 900 } }, options || {}));
    const page = await context.newPage();
    page.on('pageerror', (error) => out.errors.push(String(error)));
    await page.goto(url);
    return page;
  };
  const bg = (page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
"""
TAIL = r"""
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((error) => { console.log(JSON.stringify({ fatal: String(error) })); process.exit(1); });
"""


def drive(tmp_path: Path, body: str, **args) -> dict:
    script = tmp_path / "driver.js"
    script.write_text(HEAD + body + TAIL)
    args = {"chrome": str(CHROME), "shots": SHOTS, **args}
    result = subprocess.run(["node", str(script), str(PLAYWRIGHT), json.dumps(args)],
                            capture_output=True, text=True, timeout=240)
    assert result.stdout.strip(), result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out
    assert out["errors"] == [], out["errors"]
    return out


def luminance(css: str) -> float:
    r, g, b = (int(v) for v in css[css.index("(") + 1 : css.index(")")].split(",")[:3])
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


READY = "() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].builtPage"


# ── 3. dark mode ────────────────────────────────────────────────────────────────────────────────────────────────────


def _dataset(tmp_path: Path, scale: float = 1.0, **options) -> Path:
    names = ("j1", "j2")
    t = np.linspace(0.0, 2.0, 201)
    s = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / 1.6, 0.0, 1.0))
    tape = np.column_stack([0.4 * s, -0.2 * s])
    runs = [Run(name=f"run {i}", reference=JointTrajectory(t=t, joint_names=names, positions=tape),
                measured={"sim": JointTrajectory(t=t, joint_names=names, positions=tape + scale * 1e-5 * (i + 1))},
                tags={"target": "A", "rep": i}) for i in range(3)]
    return write_dataset_report(runs, tmp_path / "ds", title="TTA asks", **options)


def test_report_and_dataset_follow_the_system_theme(tmp_path):
    report = write_comparison_report(comparison(), tmp_path / "r" / "report.html")
    index = _dataset(tmp_path, rows=())
    pinned = {}
    for name, page in (("report", report), ("index", index)):  # the host pins the light theme: <html data-theme="light">
        copy = page.with_name("pinned-" + page.name)
        copy.write_text(page.read_text("utf-8").replace("<html lang='en'>", "<html lang='en' data-theme='light'>", 1), "utf-8")
        pinned[name + "_pinned"] = str(copy)
    out = drive(tmp_path, r"""
  for (const [name, url, pinnedUrl, ready] of [['report', args.report, args.report_pinned, args.ready], ['dataset', args.index, args.index_pinned, '() => document.querySelector("[data-tc-dataset-summary] table")']]) {
    for (const scheme of ['light', 'dark']) {
      const page = await open('file://' + url, { colorScheme: scheme });
      await page.waitForFunction(ready, null, { timeout: 30000 });
      await page.waitForTimeout(400);
      out[name + '_' + scheme] = await bg(page);
      out[name + '_' + scheme + '_ink'] = await page.evaluate(() => getComputedStyle(document.querySelector('h1') || document.body).color);
      await shot(page, 'dark-mode-' + name + '-' + scheme);
    }
    const pinned = await open('file://' + pinnedUrl, { colorScheme: 'dark' });
    await pinned.waitForFunction(ready, null, { timeout: 30000 });
    out[name + '_pinned_light'] = await bg(pinned);
  }
""", report=str(report), index=str(index), ready=READY, **pinned)
    for name in ("report", "dataset"):
        assert out[f"{name}_light"] == "rgb(244, 244, 242)", out  # today's light page
        assert luminance(out[f"{name}_dark"]) < 0.15, out
        assert luminance(out[f"{name}_dark_ink"]) > 0.7, out
        assert out[f"{name}_pinned_light"] == "rgb(244, 244, 242)", out  # <html data-theme="light"> keeps it light


# ── 7. #run=<label> opens one run ───────────────────────────────────────────────────────────────────────────────────


def test_run_deep_link_opens_one_run_by_title_or_name_and_is_not_remembered(tmp_path):
    report = write_comparison_report(comparison(runs=3), tmp_path / "report.html")
    out = drive(tmp_path, r"""
  const chips = (page) => page.evaluate(() => [...document.querySelectorAll('.situation-group .chip')].map((chip) => [chip.textContent.trim(), chip.classList.contains('on')]));
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const visit = async (hash) => {
    const page = await context.newPage();
    page.on('pageerror', (error) => out.errors.push(String(error)));
    await page.goto('file://' + args.report + hash);
    await page.waitForFunction(args.ready, null, { timeout: 30000 });
    await page.waitForTimeout(300);
    return page;
  };
  let page = await visit('#run=Run%201');
  out.byTitle = await chips(page);
  await shot(page, 'run-deep-link');
  page = await visit('#run=run2');
  out.byName = await chips(page);
  page = await visit('#tab=joints&run=run0');
  out.withTab = await chips(page);
  out.tab = await page.evaluate(() => (document.querySelector('[data-tc-tab][aria-selected="true"]') || {}).getAttribute ? document.querySelector('[data-tc-tab][aria-selected="true"]').getAttribute('data-tc-tab') : null);
  out.hashAfterTab = await page.evaluate(() => location.hash);
  page = await visit('');
  out.plain = await chips(page);
  page = await visit('#run=nobody');
  out.unknown = await chips(page);
""", report=str(report), ready=READY)
    on = lambda chips: sorted(name for name, state in chips if state)  # noqa: E731
    assert on(out["byTitle"]) == ["Run 1", "Target"], out["byTitle"]
    assert on(out["byName"]) == ["Run 2", "Target"], out["byName"]
    assert on(out["withTab"]) == ["Run 0", "Target"] and out["tab"] == "joints", out
    assert "run=run0" in out["hashAfterTab"], out["hashAfterTab"]
    assert on(out["plain"]) == ["Run 0", "Run 1", "Run 2", "Target"], "a deep link must not be remembered"
    assert on(out["unknown"]) == ["Run 0", "Run 1", "Run 2", "Target"]


# ── 8. the stage's fold button at 390 px ────────────────────────────────────────────────────────────────────────────


def test_fold_button_sits_inside_the_stage_clear_of_its_content_at_390_px(tmp_path):
    report = write_comparison_report(comparison(), tmp_path / "report.html")
    out = drive(tmp_path, r"""
  for (const width of [390, 1280]) {
    const page = await open('file://' + args.report, { viewport: { width: width, height: 844 } });
    await page.waitForFunction(args.ready, null, { timeout: 30000 });
    await page.waitForTimeout(500);
    out['w' + width] = await page.evaluate(() => {
      const box = (node) => { const r = node.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; };
      const stage = document.querySelector('[data-tc-stage]');
      const fold = document.querySelector('[data-tc-stage-fold]');
      const heading = stage.querySelector('.tc-section h3');
      const range = document.createRange();
      range.selectNodeContents(heading);
      const canvas = stage.querySelector('canvas');
      return { stage: box(stage), fold: box(fold), text: box(range), canvas: canvas ? box(canvas) : null,
               page: { width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth } };
    });
    await shot(page, 'fold-button-' + width);
  }
""", report=str(report), ready=READY)

    def overlaps(a, b):
        return a["left"] < b["right"] and b["left"] < a["right"] and a["top"] < b["bottom"] and b["top"] < a["bottom"]

    for width in ("w390", "w1280"):
        m = out[width]
        stage, fold = m["stage"], m["fold"]
        assert stage["left"] <= fold["left"] and fold["right"] <= stage["right"], (width, m)
        assert stage["top"] <= fold["top"] and fold["bottom"] <= stage["bottom"], (width, m)
        assert not overlaps(fold, m["text"]), (width, m)
        assert m["canvas"] is None or not overlaps(fold, m["canvas"]), (width, m)
    assert out["w390"]["page"]["scroll"] <= out["w390"]["page"]["width"], "no sideways scroll at 390 px"


# ── 2 + 4. the dataset page on a static host: Rerun links, footer, significant figures ─────────────────────────────


DATASET_DOM = r"""
  const page = await open('file://' + args.index);
  await page.waitForFunction(() => document.querySelector('[data-tc-dataset-summary] table'), null, { timeout: 30000 });
  out.band = await page.evaluate(() => document.querySelector('[data-tc-dataset-summary]').textContent);
  out.footer = await page.evaluate(() => document.getElementById('ds-foot').textContent);
  const runsView = await page.$('[data-tc-targets-view] [data-view="runs"]');
  if (runsView) await runsView.click();
  await page.waitForTimeout(300);
  out.post = await page.$$eval('button[data-rerun]', (nodes) => nodes.length);
  out.web = await page.$$eval('a[data-tc-rerun-web]', (nodes) => nodes.map((a) => [a.textContent, a.getAttribute('href'), a.target]));
  out.rrd = await page.$$eval('a[data-tc-rrd]', (nodes) => nodes.map((a) => [a.getAttribute('href'), a.hasAttribute('download')]));
  out.text = await page.evaluate(() => document.body.innerText);
  await shot(page, args.name);
"""


def test_static_host_dataset_page_links_the_web_viewer_and_names_no_row_files(tmp_path):
    index = _dataset(tmp_path, rows=(), rerun_server=False, public_url="https://example.org/tta/comparison/",
                     command_root="site/comparison")
    out = drive(tmp_path, DATASET_DOM, index=str(index), name="dataset-static-host")
    assert out["post"] == 0
    assert out["web"] and all(text == "Open in the Rerun web viewer" for text, _, _ in out["web"])
    for _, href, _ in out["web"]:
        assert href.startswith("https://app.rerun.io/version/0.40.0/index.html?url=https%3A%2F%2Fexample.org%2Ftta%2Fcomparison%2Fruns%2F")
        assert href.endswith(".rrd")
    assert out["rrd"] and all(href.startswith("runs/") and href.endswith(".rrd") and download for href, download in out["rrd"])
    assert "rows.json" not in out["footer"] and "rows.parquet" not in out["footer"]
    assert str(tmp_path) not in out["text"]


def test_default_dataset_page_keeps_the_rerun_button_and_the_footer(tmp_path):
    index = _dataset(tmp_path)
    out = drive(tmp_path, DATASET_DOM, index=str(index), name="dataset-default")
    assert out["post"] > 0 and out["web"] == []
    assert "rows.json / rows.parquet" in out["footer"]


def test_dataset_summary_shows_significant_figures_not_zero(tmp_path):
    index = _dataset(tmp_path, scale=1.0, rows=())  # joint errors of 1e-5 rad: about 0.0006°
    out = drive(tmp_path, DATASET_DOM, index=str(index), name="dataset-sig-figs")
    assert "0.00°" not in out["band"], out["band"]
    assert "0.0011°" in out["band"] or "0.0012°" in out["band"], out["band"]
