"""Drag the time on any figure and every other figure, the 3D pose and the stage slider follow (headless Chrome).

Zach, Daily Note 2026-11-24: "we should make sure our built in viewer here is also good. For example a important thing
is that as you drag the time on any of the figures it syncs across all of the other ones". The run-view round's five
proposals (docs/proposals/run-view-2026-11-24/) all agreed on this one mechanism (R1, "every figure is a scrubber");
this file is its acceptance ruler in the production viewer, written before the implementation (2026-11-25).

One fixture report (tests/scaling_fixtures.py, 3 DOF: target + sim + three real repeats, a robot model, tool frame,
torque breakdown) at 1440 x 900. Everything is read back from what is DRAWN, never from the gesture code:

- a chart's committed time is its ``[data-tc-playhead]`` mark (exactly one per chart card): the mark's centre x on
  the chart's plotting area (uPlot's ``.u-over``), mapped through that chart's own x scale;
- the page's slider is the time lane's ruler ``[data-tc-ruler]`` (its ``aria-valuenow``): the stage's own slider moved
  into the lane with the one-timeline look (Zach's pick round, 2026-11-24; tests/test_time_lane_browser.py);
- the 3D pose is the sample each robot model is standing at: its link meshes' positions matched against the payload's
  ``robot_track`` (a test-only copy of the report hands the viewer's private three.js scene to the page, as
  tests/test_viewer3d_span.py does).

Gestures checked: a plain press-and-drag on a chart commits the time live (mid-drag) and after release, on every chart
of the tab and of another tab once it is shown; a first open of a tab keeps the 3D at the committed time (bug (a) of
the round: the new charts' cursor sync parked the 3D at the end); hovering still previews in the 3D only, and leaving
puts it back; Shift-drag and Ctrl+wheel zoom x on every chart without moving the time; a plain wheel leaves the zoom
alone (it scrolls the page); the lane's Full range (Reset zoom before the lane) and a double-click restore the full
range; a press on the lane's ruler moves every playhead; a touch drag scrubs. And bug (b): the "Did it track the target?" answer and the joint ranking never name a run that is
not shown (a situation chip off, or ``#run=`` focusing one run).

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``, default the aruco-studio checkout's); skipped
otherwise. Run:

    /home/bam/traj_compare/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_drag_sync_browser.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scaling_fixtures import scaling_comparison
from traj_compare import write_comparison_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

SCENE_HOOK = "scene.add(grid);"

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const REPORT = process.argv[3];
const VIEWPORT = { width: 1440, height: 900 };
const WAIT = 20000;

// ---- in the page: what is drawn ----
function readback() {
  const p = TrajCompare.state.pages[0];
  const grid = p.data.plot_t;
  const shown = (el) => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
  const charts = p.charts.filter((c) => c.u).map((c) => {
    const over = c.u.over, box = over.getBoundingClientRect();
    const scale = c.u.scales.x;
    const marks = [...c.card.querySelectorAll('[data-tc-playhead]')];
    let markT = null, markShown = false;
    if (marks.length === 1) {
      const mark = marks[0], style = getComputedStyle(mark), mb = mark.getBoundingClientRect();
      markShown = style.display !== 'none' && style.visibility !== 'hidden' && mb.height > 0;
      if (markShown && box.width > 0) markT = scale.min + (mb.x + mb.width / 2 - box.x) / box.width * (scale.max - scale.min);
    }
    return { title: c.spec.title, shown: shown(over) && c.card.offsetParent !== null, w: box.width, min: scale.min, max: scale.max,
             marks: marks.length, markShown: markShown, markT: markT,
             // uPlot's cursor: its dots read the values at this sample (null while hidden)
             cursorT: c.u.cursor.idx == null || c.u.cursor.left < 0 ? null : grid[c.u.cursor.idx] };
  });
  const sliders = [...document.querySelectorAll('[data-tc-ruler]')].filter(shown).map((s) => parseFloat(s.getAttribute('aria-valuenow')));
  // each robot model: the payload sample its link meshes stand at
  const robots = [];
  const scene = window.__scenes && window.__scenes[0];
  const tracks = p.data.situations.filter((s) => s.robot_track);
  if (scene) {
    const groups = scene.children.filter((o) => o.isGroup && o.children.length && o.children.every((m) => m.isMesh));
    const taken = new Set();
    groups.forEach((group) => {
      const meshes = group.children;
      for (const sit of tracks) {
        if (taken.has(sit.name)) continue;
        const track = sit.robot_track;
        if (!track.p.length || track.p[0].length !== meshes.length) continue;
        // a still arm matches every sample of its dwell: of the matching samples, the one nearest the page's time
        const near = p.transport.eff();
        let hit = -1;
        for (let i = 0; i < track.p.length; i++) {
          let ok = true;
          for (let k = 0; k < meshes.length && ok; k++) {
            const q = track.p[i][k], m = meshes[k].position;
            ok = Math.abs(m.x - q[0]) < 1e-6 && Math.abs(m.y - q[1]) < 1e-6 && Math.abs(m.z - q[2]) < 1e-6;
          }
          if (ok && (hit < 0 || Math.abs(track.t[i] - near) < Math.abs(track.t[hit] - near))) hit = i;
        }
        if (hit >= 0) {
          taken.add(sit.name);
          const spacing = track.t.length > 1 ? (track.t[track.t.length - 1] - track.t[0]) / (track.t.length - 1) : 0;
          robots.push({ name: sit.name, index: hit, t: track.t[hit], spacing: spacing, visible: group.visible });
          break;
        }
      }
    });
  }
  const answer = document.querySelector('.tc-answer-lead');
  const label = (el) => [el.textContent, el.getAttribute('aria-label') || '', el.getAttribute('title') || ''].join(' ');
  return {
    t: p.transport.t, hover: p.transport.hoverT, tMin: p.transport.tMin, tMax: p.transport.tMax, dt: grid[1] - grid[0],
    activeTab: p.activeTab, charts: charts, sliders: sliders, robots: robots, robotTracks: tracks.length,
    answer: answer ? answer.textContent : null,
    rankLabels: [...document.querySelectorAll('[data-tc-rank-bar]')].map(label),
    visible: p.data.situations.filter((s) => s.role !== 'target' && s.has_data).map((s) => ({ name: s.name, title: s.title, on: p.visible[s.name] !== false })),
    stageHint: (document.querySelector('[data-tc-section="viewer3d"] .hint') || {}).textContent || null,
    scrollY: window.scrollY,
  };
}

// the n-th chart drawn in the active tab's panel, scrolled into view; its plotting area's box and x scale
function chartBox(n) {
  const p = TrajCompare.state.pages[0];
  const panel = document.querySelector('[data-tc-panel="' + p.activeTab + '"]');
  const charts = p.charts.filter((c) => c.u && panel.contains(c.card) && c.card.offsetParent !== null);
  const chart = charts[n];
  if (!chart) return null;
  chart.card.scrollIntoView({ block: 'center' });
  const box = chart.u.over.getBoundingClientRect();
  return { x: box.x, y: box.y, w: box.width, h: box.height, min: chart.u.scales.x.min, max: chart.u.scales.x.max,
           title: chart.spec.title, count: charts.length };
}

const at = (box, frac) => ({ x: box.x + frac * box.w, y: box.y + box.h / 2, t: box.min + frac * (box.max - box.min),
                             tol: (box.max - box.min) / box.w });

async function open(browser, url, errors, options) {
  const context = await browser.newContext({ viewport: VIEWPORT, ...(options || {}) });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.addInitScript(() => { window.__scenes = []; });
  await page.goto(url);
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].builtPage &&
                             TrajCompare.state.pages[0].viewer3d, null, { timeout: WAIT });
  await page.waitForTimeout(500);
  return { context, page };
}

async function settle(page, ms) { await page.waitForTimeout(ms || 250); return await page.evaluate(readback); }

async function step(out, key, body) {
  try { out[key] = await body(); } catch (error) { out[key] = { error: String(error).split('\n')[0] }; }
}

async function clickTab(page, id) {
  await page.click('[data-tc-tabs] [data-tc-tab="' + id + '"]', { timeout: 3000 });
}

async function away(page) { await page.mouse.move(3, 3); }

async function main(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  out.initial = await settle(page);

  // 1. a plain drag on the track tab's first chart: live, then released, then with the pointer gone
  await step(out, 'drag', async () => {
    const a = await page.evaluate(chartBox, 0);
    if (!a || a.count < 2) throw new Error('the track tab needs two charts, has ' + (a ? a.count : 0));
    const p0 = at(a, 0.2), p1 = at(a, 0.45), p2 = at(a, 0.7);
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    const pressed = await settle(page, 120);
    await page.mouse.move(p1.x, p1.y, { steps: 6 });
    const mid = await settle(page, 120);
    await page.mouse.move(p2.x, p2.y, { steps: 6 });
    await page.mouse.up();
    const released = await settle(page);
    await away(page);
    const gone = await settle(page);
    return { chart: a, expect: { pressed: p0, mid: p1, released: p2 }, pressed, mid, released, gone };
  });

  // 2. the joints tab, opened for the first time, shows that time; then a drag there, and back on the track tab
  await step(out, 'openJoints', async () => { await clickTab(page, 'joints'); return await settle(page, 500); });
  await step(out, 'dragJoints', async () => {
    const a = await page.evaluate(chartBox, 0);
    if (!a) throw new Error('no chart in the joints tab');
    const p0 = at(a, 0.65), p1 = at(a, 0.5), p2 = at(a, 0.35);
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    await page.mouse.move(p1.x, p1.y, { steps: 5 });
    const mid = await settle(page, 120);
    await page.mouse.move(p2.x, p2.y, { steps: 5 });
    await page.mouse.up();
    await away(page);
    const released = await settle(page);
    return { chart: a, expect: { mid: p1, released: p2 }, mid, released };
  });
  await step(out, 'backToTrack', async () => { await clickTab(page, 'track'); return await settle(page, 400); });

  // 3. hover previews in the 3D only; leaving puts the 3D back on the committed time
  await step(out, 'hover', async () => {
    const a = await page.evaluate(chartBox, 1);
    const p = at(a, 0.9);
    await page.mouse.move(p.x - 20, p.y);
    await page.mouse.move(p.x, p.y, { steps: 3 });
    const over = await settle(page, 200);
    await away(page);
    const left = await settle(page, 200);
    return { expect: p, over, left };
  });

  // 4. zoom: Shift-drag, plain wheel (no zoom), Ctrl+wheel, Reset zoom, double-click
  await step(out, 'shiftZoom', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p0 = at(a, 0.3), p1 = at(a, 0.6);
    const before = await settle(page, 50);
    await page.keyboard.down('Shift');
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    await page.mouse.move(p1.x, p1.y, { steps: 8 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await away(page);
    const after = await settle(page, 400);
    return { expect: { from: p0, to: p1 }, before, after };
  });
  await step(out, 'resetChip', async () => {
    await page.click('[data-tc-zoom-reset]', { timeout: 3000 });  // the lane's Full range (the Reset zoom chip moved there)
    await away(page);
    return await settle(page, 400);
  });
  await step(out, 'plainWheel', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p = at(a, 0.5);
    const before = await settle(page, 50);
    await page.mouse.move(p.x, p.y);
    await page.mouse.wheel(0, 240);
    await away(page);
    const after = await settle(page, 400);
    return { before, after };
  });
  await step(out, 'ctrlWheel', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p = at(a, 0.5);
    const before = await settle(page, 50);
    await page.mouse.move(p.x, p.y);
    await page.keyboard.down('Control');
    await page.mouse.wheel(0, -240);
    await page.keyboard.up('Control');
    await away(page);
    const after = await settle(page, 400);
    return { at: p, before, after };
  });
  await step(out, 'dblclickReset', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p = at(a, 0.5);
    await page.mouse.dblclick(p.x, p.y);
    await away(page);
    return await settle(page, 400);
  });

  // 5. a press on the lane's ruler (the page's slider) moves every playhead
  await step(out, 'slider', async () => {
    const { time, pointer } = await pressRuler(page, 0.37);
    return { time, pointer, after: await settle(page, 300) };
  });
  await context.close();
}

// a press on the lane's ruler at ``frac`` of its width (full range): the time it then reads, and the pointer's time
async function pressRuler(page, frac) {
  const r = await page.evaluate(() => {
    const ruler = document.querySelector('[data-tc-ruler]'), b = ruler.getBoundingClientRect();
    return { x: b.x, y: b.y, w: b.width, h: b.height, min: parseFloat(ruler.getAttribute('aria-valuemin')),
             max: parseFloat(ruler.getAttribute('aria-valuemax')) };
  });
  await page.mouse.click(r.x + frac * r.w, r.y + r.h / 2);
  await away(page);
  const time = await page.evaluate(() => parseFloat(document.querySelector('[data-tc-ruler]').getAttribute('aria-valuenow')));
  return { time, pointer: { t: r.min + frac * (r.max - r.min), tol: (r.max - r.min) / r.w } };
}

// bug (a) on its own: a time committed with the lane's ruler, then a tab opened for the first time
async function firstOpen(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  await step(out, 'firstOpen', async () => {
    const { time } = await pressRuler(page, 0.41);
    const before = await settle(page, 200);
    await clickTab(page, 'timing');
    return { time, before, opened: await settle(page, 500) };
  });
  await context.close();
}

async function touch(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors, { hasTouch: true });
  await step(out, 'touch', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p0 = at(a, 0.25), p1 = at(a, 0.5), p2 = at(a, 0.75);
    const cdp = await context.newCDPSession(page);
    const touchAt = (type, p) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: p ? [{ x: p.x, y: p.y }] : [] });
    await touchAt('touchStart', p0);
    for (let i = 1; i <= 6; i++) await touchAt('touchMove', { x: p0.x + (p1.x - p0.x) * i / 6, y: p0.y });
    const mid = await settle(page, 150);
    for (let i = 1; i <= 6; i++) await touchAt('touchMove', { x: p1.x + (p2.x - p1.x) * i / 6, y: p0.y });
    await touchAt('touchEnd', null);
    const released = await settle(page, 300);
    return { expect: { mid: p1, released: p2 }, mid, released };
  });
  await context.close();
}

async function selection(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  await step(out, 'hideWorst', async () => {
    const before = await settle(page, 100);
    const match = /Worst run: (.+?), mean joint RMS error/.exec(before.answer || '');
    if (!match) throw new Error('no "Worst run: ..." in the answer: ' + before.answer);
    const worst = match[1];
    const clicked = await page.evaluate((title) => {
      const chip = [...document.querySelectorAll('.situation-group button.chip')].find((b) => b.textContent.trim().startsWith(title));
      if (!chip) return false;
      chip.click();
      return true;
    }, worst);
    if (!clicked) throw new Error('no situation chip for ' + worst);
    const hidden = await settle(page, 300);
    await clickTab(page, 'joints');
    const joints = await settle(page, 400);
    await clickTab(page, 'track');
    await page.evaluate((title) => {
      [...document.querySelectorAll('.situation-group button.chip')].find((b) => b.textContent.trim().startsWith(title)).click();
    }, worst);
    const restored = await settle(page, 300);
    return { worst, before, hidden, joints, restored };
  });
  await context.close();
  const focused = await open(browser, 'file://' + REPORT + '#run=sim', errors);
  await step(out, 'focusRun', async () => {
    const shown = await settle(focused.page, 200);
    await clickTab(focused.page, 'joints');
    return { shown, joints: await settle(focused.page, 400) };
  });
  await focused.context.close();
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = {};
  const errors = [];
  try {
    for (const job of [main, firstOpen, touch, selection]) {
      try { await job(browser, out, errors); } catch (error) { out['crashed:' + job.name] = String(error); }
    }
  } finally {
    await browser.close();
  }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def measured(tmp_path_factory) -> dict:
    """The fixture report driven once in headless Chrome: every step's readback, keyed by step."""

    root = tmp_path_factory.mktemp("drag_sync")
    report = write_comparison_report(scaling_comparison("3dof"), root / "report")
    document = report.read_text()
    assert document.count(SCENE_HOOK) == 1, "viewer3d.js no longer adds its grid once: update the scene hook"
    # a test-only copy that hands the viewer's private scene to the page
    hooked = report.with_name("report_hooked.html")
    hooked.write_text(document.replace(SCENE_HOOK, SCENE_HOOK + " window.__scenes.push(scene);"))
    (root / "driver.js").write_text(DRIVER)
    result = subprocess.run(
        ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(hooked), str(CHROME)],
        capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr[-3000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    crashed = {key: value for key, value in out.items() if key.startswith("crashed:")}
    assert not crashed, crashed
    return out


def _step(measured: dict, key: str) -> dict:
    assert key in measured, f"{key}: never measured"
    value = measured[key]
    assert not (isinstance(value, dict) and "error" in value), f"{key}: {value['error']}"
    return value


def _shown(readback: dict) -> list[dict]:
    charts = [chart for chart in readback["charts"] if chart["shown"]]
    assert charts, f"no chart shown on tab {readback['activeTab']}"
    return charts


def _close(value: float | None, expected: float, tolerance: float) -> bool:
    return value is not None and abs(value - expected) <= tolerance + 1e-9


def _assert_everything_at(readback: dict, time: float, where: str, *, pose: bool = True, dots: bool = False) -> None:
    """The committed time, every shown chart's playhead, the stage slider and (``pose``) every arm read back ``time``,
    within one display sample (plus the one pixel a mark can round to). ``dots``: no pointer is on a plot, so uPlot's
    cursor (its dots read the values) sits on ``time`` too, not on a stale pixel or the run's last sample."""

    dt = readback["dt"]
    assert time is not None, f"{where}: no time was committed"
    assert _close(readback["t"], time, dt), f"{where}: committed time {readback['t']} != {time:.4f}"
    for chart in _shown(readback):
        assert chart["marks"] == 1, f"{where}: {chart['title']!r} has {chart['marks']} [data-tc-playhead] marks, wants 1"
        assert chart["markShown"], f"{where}: {chart['title']!r} hides its playhead at {time:.3f} s"
        pixel = (chart["max"] - chart["min"]) / chart["w"]
        assert _close(chart["markT"], time, dt + 1.5 * pixel), (
            f"{where}: {chart['title']!r} playhead at {chart['markT']} s, the time is {time:.4f} s"
        )
        if dots:
            assert _close(chart["cursorT"], time, dt + 1.5 * pixel), (
                f"{where}: {chart['title']!r} has uPlot's cursor (its value dots) at {chart['cursorT']} s, the time is "
                f"{time:.4f} s"
            )
    assert readback["sliders"], f"{where}: no time ruler [data-tc-ruler] shown"
    for value in readback["sliders"]:
        assert _close(value, time, dt), f"{where}: the lane's ruler reads {value}, the time is {time:.4f} s"
    if pose:
        assert readback["robotTracks"] > 0, "the fixture draws no robot model"
        assert len(readback["robots"]) == readback["robotTracks"], (
            f"{where}: matched {len(readback['robots'])} of {readback['robotTracks']} robot models to a payload sample"
        )
        for robot in readback["robots"]:
            assert _close(robot["t"], time, max(dt, robot["spacing"])), (
                f"{where}: the {robot['name']} arm stands at sample t = {robot['t']} s, the time is {time:.4f} s"
            )


def _pointer_tolerance(expect: dict, dt: float) -> float:
    return dt / 2 + 1.5 * expect["tol"]


# ── the drag: live, released, on every chart, every tab, the 3D and the slider ─────────────────────────────────────


def test_a_plain_drag_on_a_chart_commits_the_time_live_on_every_chart_the_slider_and_the_arms(measured):
    drag = _step(measured, "drag")
    dt = drag["mid"]["dt"]
    for phase in ("pressed", "mid", "released"):
        expect = drag["expect"][phase]
        readback = drag[phase]
        assert _close(readback["t"], expect["t"], _pointer_tolerance(expect, dt)), (
            f"{phase}: the drag committed {readback['t']} s, the pointer was at {expect['t']:.4f} s"
        )
        _assert_everything_at(readback, readback["t"], f"drag {phase}")
    assert len(_shown(drag["mid"])) >= 2, "the drag must be read back on a second chart of the same tab"


def test_the_pointer_leaving_after_a_drag_keeps_the_committed_time(measured):
    drag = _step(measured, "drag")
    _assert_everything_at(drag["gone"], drag["released"]["t"], "after the drag, pointer gone", dots=True)
    assert drag["gone"]["hover"] is None, "the hover preview outlived the pointer"


def test_a_tab_opened_for_the_first_time_keeps_the_3d_at_the_slider_time(measured):
    """Bug (a): the charts built on a tab's first show joined uPlot's cursor sync at their last sample, and that "hover"
    parked the 3D at the end (measured 2026-11-25 on production: hoverT = tMax after clicking a new tab)."""

    step = _step(measured, "firstOpen")
    opened = step["opened"]
    assert opened["activeTab"] == "timing"
    assert opened["hover"] is None, f"opening a tab left a hover preview at {opened['hover']} s (the 3D parks there)"
    for robot in opened["robots"]:
        assert _close(robot["t"], step["time"], max(opened["dt"], robot["spacing"])), (
            f"after opening a tab the {robot['name']} arm stands at {robot['t']} s, the slider says {step['time']:.3f} s"
        )
    _assert_everything_at(opened, step["time"], "timing tab, first open", dots=True)


def test_a_tab_opened_for_the_first_time_after_a_drag_shows_the_dragged_time(measured):
    committed = _step(measured, "drag")["released"]["t"]
    opened = _step(measured, "openJoints")
    assert opened["activeTab"] == "joints"
    assert opened["hover"] is None, f"opening a tab left a hover preview at {opened['hover']} s (the 3D parks there)"
    _assert_everything_at(opened, committed, "joints tab, first open", dots=True)


def test_a_drag_on_another_tab_moves_the_first_tabs_charts_too(measured):
    drag = _step(measured, "dragJoints")
    dt = drag["mid"]["dt"]
    for phase in ("mid", "released"):
        expect = drag["expect"][phase]
        assert _close(drag[phase]["t"], expect["t"], _pointer_tolerance(expect, dt)), (
            f"joints {phase}: committed {drag[phase]['t']} s, the pointer was at {expect['t']:.4f} s"
        )
        _assert_everything_at(drag[phase], drag[phase]["t"], f"joints drag {phase}")
    back = _step(measured, "backToTrack")
    assert back["activeTab"] == "track"
    _assert_everything_at(back, drag["released"]["t"], "back on the track tab", dots=True)


def test_hover_previews_in_the_3d_only_and_leaving_restores_the_committed_time(measured):
    """Kept from today (hover any plot to preview that instant): the playheads and the slider stay on the committed
    time, only the 3D previews the hovered instant; leaving the chart puts the 3D back."""

    committed = _step(measured, "backToTrack")["t"]
    hover = _step(measured, "hover")
    over, dt = hover["over"], hover["over"]["dt"]
    assert _close(over["hover"], hover["expect"]["t"], _pointer_tolerance(hover["expect"], dt) + dt), (
        f"hovering at {hover['expect']['t']:.3f} s previews {over['hover']}"
    )
    _assert_everything_at(over, committed, "hovering", pose=False)
    for robot in over["robots"]:
        assert _close(robot["t"], over["hover"], max(dt, robot["spacing"])), f"hover: {robot['name']} arm at {robot['t']}"
    assert hover["left"]["hover"] is None
    _assert_everything_at(hover["left"], committed, "hover left", dots=True)


# ── zoom moves off the plain drag ────────────────────────────────────────────────────────────────────────────────────


def _ranges(readback: dict) -> list[tuple[float, float]]:
    return [(chart["min"], chart["max"]) for chart in readback["charts"]]


def test_shift_drag_zooms_x_on_every_chart_without_moving_the_time(measured):
    zoom = _step(measured, "shiftZoom")
    before, after = zoom["before"], zoom["after"]
    lo, hi = zoom["expect"]["from"]["t"], zoom["expect"]["to"]["t"]
    tolerance = 2 * zoom["expect"]["from"]["tol"] + after["dt"]
    for chart_min, chart_max in _ranges(after):
        assert _close(chart_min, lo, tolerance) and _close(chart_max, hi, tolerance), (
            f"a chart shows {chart_min}..{chart_max} s after Shift-dragging {lo:.3f}..{hi:.3f} s"
        )
    assert after["t"] == before["t"], f"Shift-drag moved the time {before['t']} -> {after['t']}"
    _assert_everything_at(after, before["t"], "after the Shift-drag zoom", dots=True)


def test_reset_zoom_restores_the_full_range_on_every_chart(measured):
    reset = _step(measured, "resetChip")
    for chart_min, chart_max in _ranges(reset):
        assert _close(chart_min, reset["tMin"], 1e-6) and _close(chart_max, reset["tMax"], 1e-6), (chart_min, chart_max)


def test_a_plain_wheel_over_a_chart_does_not_zoom(measured):
    """WHY (2026-11-25): a tab is a column of charts, so the pointer is nearly always over one; a plain wheel there
    must keep scrolling the page. Ctrl+wheel (and a trackpad pinch, which Chrome sends as Ctrl+wheel) zooms."""

    wheel = _step(measured, "plainWheel")
    assert _ranges(wheel["after"]) == _ranges(wheel["before"])


def test_ctrl_wheel_zooms_x_around_the_pointer_on_every_chart_without_moving_the_time(measured):
    wheel = _step(measured, "ctrlWheel")
    before, after = wheel["before"], wheel["after"]
    spans = {round(chart_max - chart_min, 9) for chart_min, chart_max in _ranges(after)}
    assert len(spans) == 1, f"the charts disagree on the zoom: {_ranges(after)}"
    (span,) = spans
    assert span < 0.95 * (before["tMax"] - before["tMin"]), f"Ctrl+wheel did not zoom in (span {span} s)"
    pointer = wheel["at"]["t"]
    for chart_min, chart_max in _ranges(after):
        assert chart_min - 1e-9 <= pointer <= chart_max + 1e-9, "the zoom lost the instant under the pointer"
    assert after["t"] == before["t"], f"Ctrl+wheel moved the time {before['t']} -> {after['t']}"


def test_a_double_click_restores_the_full_range(measured):
    reset = _step(measured, "dblclickReset")
    for chart_min, chart_max in _ranges(reset):
        assert _close(chart_min, reset["tMin"], 1e-6) and _close(chart_max, reset["tMax"], 1e-6), (chart_min, chart_max)


def test_a_press_on_the_lane_ruler_moves_every_playhead(measured):
    slider = _step(measured, "slider")
    assert _close(slider["time"], slider["pointer"]["t"], _pointer_tolerance(slider["pointer"], slider["after"]["dt"])), (
        f"a press on the ruler at {slider['pointer']['t']:.4f} s committed {slider['time']} s"
    )
    _assert_everything_at(slider["after"], slider["time"], "after the ruler", dots=True)


def test_a_touch_drag_on_a_chart_scrubs(measured):
    drag = _step(measured, "touch")
    dt = drag["mid"]["dt"]
    for phase in ("mid", "released"):
        expect = drag["expect"][phase]
        assert _close(drag[phase]["t"], expect["t"], _pointer_tolerance(expect, dt)), (
            f"touch {phase}: committed {drag[phase]['t']} s, the finger was at {expect['t']:.4f} s"
        )
        _assert_everything_at(drag[phase], drag[phase]["t"], f"touch {phase}")


def test_the_stage_hint_names_the_drag(measured):
    hint = _step(measured, "initial")["stageHint"] or ""
    assert "drag" in hint and "hover any plot to preview that instant; scrub below the canvas" not in hint, hint


# ── bug (b): nothing names a run that is not shown ──────────────────────────────────────────────────────────────────


def _named_runs(text: str, runs: list[dict]) -> set[str]:
    return {run["title"] for run in runs if re.search(r"(?<!\w)" + re.escape(run["title"]) + r"(?!\w)", text)}


def test_hiding_the_worst_run_takes_it_out_of_the_answer_and_the_ranking(measured):
    step = _step(measured, "hideWorst")
    worst = step["worst"]
    hidden = step["hidden"]
    assert {run["title"]: run["on"] for run in hidden["visible"]}[worst] is False, f"the chip did not hide {worst}"
    shown = [run for run in hidden["visible"] if run["on"]]
    assert worst not in hidden["answer"], f"the answer names the hidden run: {hidden['answer']!r}"
    assert _named_runs(hidden["answer"], shown), f"the answer names no shown run: {hidden['answer']!r}"
    for label in step["joints"]["rankLabels"]:
        assert f"({worst})" not in label, f"a ranking bar names the hidden run: {label!r}"
    assert f"Worst run: {worst}," in step["restored"]["answer"], step["restored"]["answer"]


def test_a_run_deep_link_answers_for_that_run_only(measured):
    step = _step(measured, "focusRun")
    shown = step["shown"]
    on = [run for run in shown["visible"] if run["on"]]
    assert [run["name"] for run in on] == ["sim"], on
    off = [run["title"] for run in shown["visible"] if not run["on"]]
    for title in off:
        assert title not in shown["answer"], f"#run=sim: the answer names {title}: {shown['answer']!r}"
        for label in step["joints"]["rankLabels"]:
            assert f"({title})" not in label, f"#run=sim: a ranking bar names {title}: {label!r}"


def test_no_console_errors(measured):
    assert measured["errors"] == []
