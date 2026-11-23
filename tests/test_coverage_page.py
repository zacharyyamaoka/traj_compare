"""The coverage page and its place in traj_compare (acceptance, written before the code, 2026-11-23).

Contract: docs/COVERAGE.md, "The custom page" and "traj_compare integration". Measured in headless Chrome:
tabs, the colormap / reverse / scale controls (they must repaint the heatmap's pixels), a legend on every figure
(Zach 2026-11-23: "This is good as long as you show the legend of the meaning of the lines"), the 3D views drawing
something, the 3D proposals switch remembering its pick, and the Dataset level's link to the page.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from scipy.spatial.transform import Rotation

from traj_compare import Run, write_dataset_report
from traj_compare.coverage import analyze, write_coverage_page

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                                   reason="needs Node Playwright and Chrome")

JOINTS = ("shoulder", "elbow", "wrist")
LIMITS = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -2.0, -math.pi]),
                     max_position=np.array([math.pi, 2.0, math.pi]), max_velocity=np.array([3.0, 3.0, 4.0]),
                     max_acceleration=np.array([15.0, 15.0, 20.0]))
CMAPS = ["viridis", "magma", "plasma", "inferno", "cividis"]
SCALES = ["linear", "log", "equalized", "visited", "enough"]
TABS = ["overview", "limits", "joint", "joints", "cartesian", "orientation", "space3d", "trajectories"]
PROPOSALS = ["height-q-qd", "terrain-qdd", "hist-over-trajectories", "slab-stack", "joint-skyline",
             "workspace-terrain", "direction-hedgehog"]


def trajectory(seed: int, seconds: float = 8.0) -> tuple[JointTrajectory, PoseTrajectory]:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, seconds, 0.01)
    w = rng.uniform(0.4, 1.6, 3)
    amp = rng.uniform(0.3, 1.0, 3) * np.array([math.pi, 2.0, math.pi]) * 0.8
    q = amp * np.sin(w * t[:, None] + rng.uniform(0, 6, 3))
    joint = JointTrajectory(t=t, joint_names=JOINTS, positions=q, limits=LIMITS)
    xyz = np.stack([0.4 + 0.2 * np.cos(q[:, 0]), 0.2 * np.sin(q[:, 0]), 0.3 + 0.1 * np.sin(q[:, 1])], axis=1)
    rot = Rotation.from_euler("zyx", np.stack([q[:, 2], 0.4 * np.sin(q[:, 1]), np.full(len(t), math.pi)], axis=1))
    return joint, PoseTrajectory(t=t, positions=xyz, orientations=rot.as_quat())


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("coverage")
    pairs = {f"traj {k}": trajectory(k) for k in range(6)}
    tags = {name: {"split": "dev" if k < 4 else "holdout"} for k, name in enumerate(pairs)}
    cov = analyze({n: j for n, (j, _) in pairs.items()}, tool={n: p for n, (_, p) in pairs.items()}, tags=tags,
                  group_by="split", title="Synthetic arm")
    cov.write_page(root / "tool" / "index.html", back=[("Dataset", "../index.html")])
    no_tool = analyze({n: j for n, (j, _) in pairs.items()}, title="Joints only")
    write_coverage_page(no_tool.payload, root / "joints" / "index.html")
    runs = [Run(name=f"run {k}", reference=pairs[f"traj {k % 3}"][0], measured={"sim": pairs[f"traj {k % 3}"][0]},
                tags={"target": f"traj {k % 3}"}) for k in range(6)]
    write_dataset_report(runs, root / "dataset_with", title="With coverage", coverage=True)
    write_dataset_report(runs, root / "dataset_without", title="Without coverage")
    return root


# ── files ────────────────────────────────────────────────────────────────────


def test_the_page_is_one_self_contained_file(site):
    html = (site / "tool" / "index.html").read_text("utf-8")
    assert not re.search(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", html), "no CDN: it opens from disk"
    assert "data-cov-page" in html


def test_the_dataset_report_writes_its_coverage_page_only_when_asked(site):
    page = site / "dataset_with" / "coverage" / "index.html"
    assert page.is_file()
    payload = json.loads((site / "dataset_with" / "coverage" / "coverage.json").read_text("utf-8"))
    assert payload["schema"] == "traj_compare.coverage/1"
    assert payload["source"]["trajectories"] == 3  # the site's distinct targets, each once
    assert not (site / "dataset_without" / "coverage").exists()


# ── the page in a browser ───────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [] };
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  async function open(url) {
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url); await page.waitForTimeout(1500);
    return page;
  }
  // a digest of a canvas's pixels (2-D or WebGL: drawn into a 2-D canvas first)
  const pixels = (page, sel) => page.evaluate((s) => {
    const el = document.querySelector(s); if (!el) return null;
    const c = document.createElement('canvas'); c.width = el.width; c.height = el.height;
    const g = c.getContext('2d'); g.drawImage(el, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data; let h = 0; const colours = new Set();
    for (let i = 0; i < d.length; i += 4) { h = (h * 31 + d[i] + 7 * d[i + 1] + 13 * d[i + 2]) | 0;
      if (i % 64 === 0) colours.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]); }
    return { w: c.width, h: c.height, hash: h, colours: colours.size };
  }, sel);
  const legends = (page) => page.evaluate(() => Array.from(document.querySelectorAll('[data-cov-figure]'))
    .filter((f) => f.getBoundingClientRect().width > 0)
    .map((f) => ({ id: f.getAttribute('data-cov-figure'),
                   legend: ((f.querySelector('[data-cov-legend]') || {}).textContent || '').trim().length })));

  let page = await open(spec.tool);
  out.tabs = await page.evaluate(() => Array.from(document.querySelectorAll('[data-cov-nav] [data-cov-tab]')).map((b) => b.getAttribute('data-cov-tab')));
  out.cmaps = await page.evaluate(() => Array.from(document.querySelectorAll('select[data-cov-cmap] option')).map((o) => o.value));
  out.cmap = await page.evaluate(() => document.querySelector('select[data-cov-cmap]').value);
  out.scales = await page.evaluate(() => Array.from(document.querySelectorAll('select[data-cov-scale] option')).map((o) => o.value));
  out.scale = await page.evaluate(() => document.querySelector('select[data-cov-scale]').value);
  out.numbers = await page.evaluate(() => (document.querySelector('[data-cov-numbers]') || {}).textContent || '');
  out.figures = {};
  for (const tab of out.tabs) {
    await page.click(`[data-cov-tab="${tab}"]`); await page.waitForTimeout(700);
    out.figures[tab] = await legends(page);
  }
  // the colour controls repaint the q x qd heatmap
  await page.click('[data-cov-tab="joint"]'); await page.waitForTimeout(500);
  const heat = '[data-cov-figure="heat-q-qd"] canvas[data-cov-heat]';
  out.heat = [await pixels(page, heat)];
  await page.selectOption('select[data-cov-cmap]', 'magma'); await page.waitForTimeout(300);
  out.heat.push(await pixels(page, heat));
  await page.check('[data-cov-reverse]'); await page.waitForTimeout(300);
  out.heat.push(await pixels(page, heat));
  await page.selectOption('select[data-cov-scale]', 'equalized'); await page.waitForTimeout(300);
  out.heat.push(await pixels(page, heat));
  // 3-D: voxels draw, the proposals switch repaints and is remembered
  await page.click('[data-cov-tab="cartesian"]'); await page.waitForTimeout(1500);
  out.voxels = await pixels(page, '[data-cov-figure="voxels-3d"] canvas');
  await page.click('[data-cov-tab="orientation"]'); await page.waitForTimeout(1500);
  out.sphere = await pixels(page, '[data-cov-figure="sphere-3d"] canvas');
  await page.click('[data-cov-tab="space3d"]'); await page.waitForTimeout(1500);
  out.proposals = await page.evaluate(() => Array.from(document.querySelectorAll('select[data-cov-proposal] option')).map((o) => o.value));
  out.proposal_box = await page.evaluate(() => { const b = document.querySelector('select[data-cov-proposal]').getBoundingClientRect();
    return { right: innerWidth - b.right, bottom: innerHeight - b.bottom }; });
  const space = '[data-cov-view="space3d"] canvas';
  out.space = [await pixels(page, space)];
  await page.selectOption('select[data-cov-proposal]', 'joint-skyline'); await page.waitForTimeout(1200);
  out.space.push(await pixels(page, space));
  out.trajectory_rows = 0;
  await page.close();
  page = await open(spec.tool);
  out.remembered = await page.evaluate(() => document.querySelector('select[data-cov-proposal]').value);
  out.remembered_cmap = await page.evaluate(() => document.querySelector('select[data-cov-cmap]').value);
  await page.click('[data-cov-tab="trajectories"]'); await page.waitForTimeout(500);
  out.trajectory_rows = await page.evaluate(() => document.querySelectorAll('[data-cov-figure="table"] tbody tr').length);
  await page.close();
  page = await open(spec.tool + '#tab=cartesian');
  out.hash_tab = await page.evaluate(() => Array.from(document.querySelectorAll('[data-cov-view]'))
    .filter((v) => v.getBoundingClientRect().width > 0).map((v) => v.getAttribute('data-cov-view')));
  await page.close();
  page = await open(spec.joints);
  out.joints_tabs = await page.evaluate(() => Array.from(document.querySelectorAll('[data-cov-nav] [data-cov-tab]')).map((b) => b.getAttribute('data-cov-tab')));
  await page.close();
  page = await open(spec.dataset_with);
  out.link = await page.evaluate(() => { const a = document.querySelector('a[data-tc-coverage-link]');
    return a ? { href: a.getAttribute('href'), visible: a.getBoundingClientRect().width > 0 } : null; });
  await page.close();
  page = await open(spec.dataset_without);
  out.no_link = await page.evaluate(() => document.querySelectorAll('a[data-tc-coverage-link]').length);
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def page(site) -> dict:
    spec = {"tool": (site / "tool" / "index.html").as_uri(), "joints": (site / "joints" / "index.html").as_uri(),
            "dataset_with": (site / "dataset_with" / "index.html").as_uri(),
            "dataset_without": (site / "dataset_without" / "index.html").as_uri()}
    (site / "spec.json").write_text(json.dumps(spec))
    (site / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


@needs_browser
def test_no_errors_and_every_tab(page):
    assert page["errors"] == []
    assert page["tabs"] == TABS
    assert page["joints_tabs"] == [tab for tab in TABS if tab not in ("cartesian", "orientation")]


@needs_browser
def test_the_controls_are_bam_reachs_colormaps_and_linear_first(page):
    assert page["cmaps"] == CMAPS and page["cmap"] == "viridis"
    assert page["scales"] == SCALES and page["scale"] == "linear"
    assert page["numbers"].strip()


@needs_browser
def test_every_visible_figure_has_a_legend(page):
    for tab in TABS:
        figures = page["figures"][tab]
        assert figures, f"tab {tab} shows no figure"
        missing = [f["id"] for f in figures if f["legend"] == 0]
        assert not missing, f"tab {tab}: figures without a legend {missing}"


@needs_browser
def test_colormap_reverse_and_scale_repaint_the_heatmap(page):
    first, magma, reversed_, equalized = page["heat"]
    assert first and first["w"] >= 200 and first["colours"] > 5
    assert len({first["hash"], magma["hash"], reversed_["hash"], equalized["hash"]}) == 4


@needs_browser
def test_the_3d_views_draw(page):
    for key in ("voxels", "sphere"):
        assert page[key] and page[key]["w"] >= 300 and page[key]["colours"] > 10, key
    assert page["space"][0]["colours"] > 10 and page["space"][0]["hash"] != page["space"][1]["hash"]


@needs_browser
def test_the_3d_proposals_sit_bottom_right_and_remember_the_pick(page):
    assert set(PROPOSALS) <= set(page["proposals"])
    assert page["proposal_box"]["right"] < 120 and page["proposal_box"]["bottom"] < 120
    assert page["remembered"] == "joint-skyline"
    assert page["remembered_cmap"] == "magma"


@needs_browser
def test_tab_from_hash_and_one_table_row_per_trajectory(page):
    assert page["hash_tab"] == ["cartesian"]
    assert page["trajectory_rows"] == 6


@needs_browser
def test_the_dataset_level_links_to_its_coverage_page(page):
    assert page["link"] and page["link"]["visible"] and page["link"]["href"].endswith("coverage/index.html")
    assert page["no_link"] == 0
