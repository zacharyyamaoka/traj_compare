"""One timeline for the page: the time lane docked under the question tabs, and one playhead line through every chart.

Zach's pick of the run-view round (docs/proposals/run-view-2026-11-24/, 2026-11-24): the AI pick R2 "One timeline for
the page" (80, co-leader with R3 at 78), applied as the default look of ``write_comparison_report`` on 2026-11-25. Built
on drag-to-sync (tests/test_drag_sync_browser.py), whose readback helpers this file reuses: a chart's committed time is
its ``[data-tc-playhead]`` read through its own x scale, the page's slider is the lane's ruler ``[data-tc-ruler]``
(``aria-valuenow``), and the 3D pose is matched against the payload's ``robot_track``.

What the lane must do, measured on the 3-DOF fixture (target + sim + three real repeats, two groups) at 1440 x 900,
everything read back from what is DRAWN and every expected time computed here from the payload's own ``err_q``:

- it is docked under the tabs column, stays in view while the page scrolls, and holds one track per run (an eye each,
  grouped sim / real), with no second slider anywhere on the page;
- the ruler and every chart's plotting area share the same x pixels (track and joints tabs), and ONE line
  ``[data-tc-line]`` runs through every chart at the committed time;
- each run's worst-moment marker sits at that run's largest |reference - run| over every joint and sample, the answer
  box's "Its worst moment ... at t = ..." included; the "error rises" marker at the first sample above half its peak;
- pressing and dragging the ruler (or a run's track) moves every chart, the 3D and the lane's readouts, live;
- Worst moment, the ‹ › moment arrows and a click on a marker jump there;
- a run's eye (and its group's) hides it on every chart, the 3D, the answer and the count;
- the zoom bar zooms every chart alike without moving the time, Full range resets, and its window shows a chart zoom;
- the lane folds, its height drags; the names column drags and the charts' title column follows; all three survive a
  reload; at 390 px nothing scrolls sideways.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``); skipped otherwise. Run:

    /home/bam/traj_compare/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_time_lane_browser.py
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scaling_fixtures import scaling_comparison
from test_drag_sync_browser import (
    CHROME,
    DRIVER,
    PLAYWRIGHT,
    SCENE_HOOK,
    _assert_everything_at,
    _close,
    _pointer_tolerance,
    _shown,
    _step,
)
from test_drag_sync_browser import pytestmark  # noqa: F401  (the same Chrome + Playwright skip)
from traj_compare import write_comparison_report

RAD2DEG = 180.0 / np.pi

# the drag-sync driver's page helpers (readback, chartBox, at, open, settle, step, clickTab, away), reused verbatim
HELPERS = DRIVER.split("async function main(")[0]

LANE_DRIVER = HELPERS + r"""
// ---- in the page: the lane as drawn ----
function laneback() {
  const p = TrajCompare.state.pages[0];
  const box = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; };
  const drawn = (el) => { if (!el || !el.getClientRects().length) return false; const s = getComputedStyle(el), b = el.getBoundingClientRect();
                          return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
  const text = (el) => el ? el.textContent.trim() : null;
  const lanes = [...document.querySelectorAll('[data-tc-lane]')];
  const lane = lanes[0] || null;
  const panel = document.querySelector('[data-tc-panel="' + p.activeTab + '"]');
  const charts = p.charts.filter((c) => c.u && panel && panel.contains(c.card) && c.card.offsetParent !== null)
    .map((c) => ({ title: c.spec.title, over: box(c.u.over), min: c.u.scales.x.min, max: c.u.scales.x.max,
                   series: c.u.series.slice(1).map((s) => ({ label: s.label, show: s.show })) }));
  const q = (sel) => lane ? lane.querySelector(sel) : null;
  const ruler = q('[data-tc-ruler]');
  const tracks = lane ? [...lane.querySelectorAll('[data-tc-lane-track]')].map((row) => {
    const eye = row.querySelector('[data-tc-lane-eye]');
    const value = row.querySelector('[data-tc-lane-value]');
    return {
      name: row.getAttribute('data-tc-lane-track'), shown: row.getAttribute('data-shown'), box: box(row), drawn: drawn(row),
      eye: eye ? { box: box(eye), pressed: eye.getAttribute('aria-pressed') } : null,
      time: box(row.querySelector('[data-tc-lane-time]')), value: text(value),
      moments: [...row.querySelectorAll('[data-tc-moment]')].map((m) => ({ kind: m.getAttribute('data-tc-moment'), box: box(m), drawn: drawn(m) })),
    };
  }) : [];
  const groups = lane ? [...lane.querySelectorAll('[data-tc-lane-group]')].map((row) => {
    const eye = row.querySelector('[data-tc-lane-eye]');
    return { key: row.getAttribute('data-tc-lane-group'), eye: eye ? { box: box(eye), pressed: eye.getAttribute('aria-pressed') } : null };
  }) : [];
  return {
    t: p.transport.t, tMin: p.transport.tMin, tMax: p.transport.tMax, activeTab: p.activeTab,
    lanes: lanes.length, lane: box(lane), laneDrawn: drawn(lane), folded: !!lane && lane.classList.contains('folded'),
    ruler: box(ruler), rulerDrawn: drawn(ruler), rulerRole: ruler && ruler.getAttribute('role'),
    rulerNow: ruler ? parseFloat(ruler.getAttribute('aria-valuenow')) : null,
    resize: box(q('[data-tc-lane-resize]')), namesResize: box(q('[data-tc-lane-names-resize]')),
    fold: box(q('[data-tc-lane-fold]')), tracksBox: box(q('[data-tc-lane-tracks]')), tracksDrawn: drawn(q('[data-tc-lane-tracks]')),
    zoomBar: box(q('[data-tc-zoom-bar]')), zoomWindow: box(q('[data-tc-zoom-window]')), zoomWindowDrawn: drawn(q('[data-tc-zoom-window]')),
    count: text(q('[data-tc-lane-count]')), readout: text(q('[data-tc-lane-readout]')),
    tracks: tracks, groups: groups,
    lines: [...document.querySelectorAll('[data-tc-line]')].map((line) => ({ box: box(line), drawn: drawn(line) })),
    charts: charts, panel: box(panel),
    otherSliders: [...document.querySelectorAll('input.tc-scrub, input[type="range"].tc-scrub')].filter(drawn).length,
    answer: text(document.querySelector('.tc-answer-lead')), detail: text(document.querySelector('.tc-answer-detail')),
    visible: Object.assign({}, p.visible),
    page: { w: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, h: innerHeight, y: scrollY },
  };
}

async function lane(page) { return await page.evaluate(laneback); }
async function boxOf(page, selector) {
  return await page.evaluate((s) => { const el = document.querySelector(s); if (!el) return null; const b = el.getBoundingClientRect();
                                      return { x: b.x, y: b.y, w: b.width, h: b.height }; }, selector);
}
async function dragBy(page, b, dx, dy) {
  const x = b.x + b.w / 2, y = b.y + b.h / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(250);
}
// the time under a fraction of the ruler, through the first chart's own x scale (the ruler is on its x pixels)
function rulerAt(l, frac) {
  const c = l.charts[0];
  return { x: l.ruler.x + frac * l.ruler.w, y: l.ruler.y + l.ruler.h / 2, t: c.min + frac * (c.max - c.min), tol: (c.max - c.min) / l.ruler.w };
}

async function main(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  await step(out, 'initial', async () => ({ lane: await lane(page), rb: await settle(page, 50) }));
  await step(out, 'scrolled', async () => {
    await page.evaluate(() => window.scrollTo(0, 420));
    await page.waitForTimeout(300);
    const scrolled = await lane(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);
    return scrolled;
  });

  // press and drag on the ruler: live, released
  await step(out, 'rulerDrag', async () => {
    const l = await lane(page);
    const p0 = rulerAt(l, 0.25), p1 = rulerAt(l, 0.5), p2 = rulerAt(l, 0.75);
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    const pressed = await settle(page, 150);
    await page.mouse.move(p1.x, p1.y, { steps: 6 });
    const mid = await settle(page, 150);
    const midLane = await lane(page);
    await page.mouse.move(p2.x, p2.y, { steps: 6 });
    await page.mouse.up();
    await away(page);
    const released = await settle(page);
    return { expect: { pressed: p0, mid: p1, released: p2 }, pressed, mid, midLane, released, releasedLane: await lane(page) };
  });

  // press and drag on a run's track
  await step(out, 'trackDrag', async () => {
    const l = await lane(page);
    const track = l.tracks.find((tr) => tr.name === 'sim');
    const c = l.charts[0];
    const y = track.time.y + track.time.h / 2;
    const at = (f) => ({ x: track.time.x + f * track.time.w, y: y, t: c.min + f * (c.max - c.min), tol: (c.max - c.min) / track.time.w });
    // a press on a marker jumps to its moment instead: start and end clear of this track's markers
    const clear = (f) => track.moments.every((m) => Math.abs(m.box.x + m.box.w / 2 - at(f).x) > 12);
    const p0 = at([0.6, 0.66, 0.54, 0.72].find(clear)), p1 = at([0.4, 0.34, 0.46, 0.28].find(clear));
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    await page.mouse.move(p1.x, p1.y, { steps: 5 });
    const mid = await settle(page, 150);
    await page.mouse.up();
    await away(page);
    return { expect: { mid: p1, released: p1 }, mid, released: await settle(page) };
  });

  // moments: Worst moment, then › and ‹, then a click on the sim run's worst-moment marker
  await step(out, 'jumpWorst', async () => { await page.click('[data-tc-jump="worst"]'); await away(page); return await lane(page); });
  await step(out, 'jumpNext', async () => { await page.click('[data-tc-jump="next"]'); await away(page); return await lane(page); });
  await step(out, 'jumpPrev', async () => { await page.click('[data-tc-jump="prev"]'); await away(page); return await lane(page); });
  await step(out, 'markerClick', async () => {
    await page.click('[data-tc-lane-track="sim"] [data-tc-moment="worst"]');
    await away(page);
    return { lane: await lane(page), rb: await settle(page) };
  });

  // the joints tab: the same x pixels and the line through its charts
  await step(out, 'joints', async () => { await clickTab(page, 'joints'); await page.waitForTimeout(400); return await lane(page); });
  await step(out, 'jointsRuler', async () => {
    const l = await lane(page);
    const p = rulerAt(l, 0.33);
    await page.mouse.click(p.x, p.y);
    await away(page);
    return { expect: p, rb: await settle(page), lane: await lane(page) };
  });
  await clickTab(page, 'track');
  await context.close();
}

async function eyes(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  await step(out, 'eye', async () => {
    const before = await lane(page);
    const match = /Worst run: (.+?), mean joint RMS error/.exec(before.answer || '');
    if (!match) throw new Error('no "Worst run: ..." in the answer: ' + before.answer);
    const title = match[1];
    const name = TrajCompare_nameOf(await page.evaluate(() => TrajCompare.state.pages[0].data.situations.map((s) => [s.name, s.title])), title);
    await page.click('[data-tc-lane-track="' + name + '"] [data-tc-lane-eye]');
    await away(page);
    const hidden = await lane(page);
    const hiddenRb = await settle(page, 100);
    await page.click('[data-tc-lane-track="' + name + '"] [data-tc-lane-eye]');
    await away(page);
    const restored = await lane(page);
    await page.click('[data-tc-lane-group="real"] [data-tc-lane-eye]');
    await away(page);
    const groupHidden = await lane(page);
    await page.click('[data-tc-lane-group="real"] [data-tc-lane-eye]');
    await away(page);
    return { title, name, before, hidden, hiddenRb, restored, groupHidden, groupRestored: await lane(page) };
  });
  await context.close();
}
function TrajCompare_nameOf(pairs, title) { const hit = pairs.find((pair) => pair[1] === title); return hit ? hit[0] : null; }

async function zoom(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  await step(out, 'zoomBar', async () => {
    const before = await lane(page);
    const bar = before.zoomBar;
    const y = bar.y + bar.h / 2;
    await page.mouse.move(bar.x + 0.3 * bar.w, y);
    await page.mouse.down();
    await page.mouse.move(bar.x + 0.6 * bar.w, y, { steps: 8 });
    await page.mouse.up();
    await away(page);
    await page.waitForTimeout(300);
    const zoomed = await lane(page);
    await page.click('[data-tc-zoom-reset]');
    await away(page);
    await page.waitForTimeout(300);
    return { before, zoomed, reset: await lane(page) };
  });
  await step(out, 'shiftZoomWindow', async () => {
    const a = await page.evaluate(chartBox, 0);
    const p0 = at(a, 0.2), p1 = at(a, 0.5);
    await page.keyboard.down('Shift');
    await page.mouse.move(p0.x, p0.y);
    await page.mouse.down();
    await page.mouse.move(p1.x, p1.y, { steps: 8 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await away(page);
    await page.waitForTimeout(400);
    return await lane(page);
  });
  await context.close();
}

async function sizes(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors);
  const reload = async () => {
    await page.reload();
    await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].builtPage, null, { timeout: WAIT });
    await page.waitForTimeout(600);
    return await lane(page);
  };
  await step(out, 'size', async () => {
    const initial = await lane(page);
    await dragBy(page, initial.resize, 0, 50);           // the lane's top edge down: 50 px shorter
    const shorter = await lane(page);
    const reloaded = await reload();
    await page.click('[data-tc-lane-fold]');
    await page.waitForTimeout(300);
    const folded = await lane(page);
    const foldedReloaded = await reload();
    await page.click('[data-tc-lane-fold]');
    await page.waitForTimeout(300);
    const unfolded = await lane(page);
    await page.dblclick('[data-tc-lane-resize]');
    await page.waitForTimeout(300);
    const reset = await lane(page);
    await dragBy(page, reset.namesResize, 60, 0);       // the names column 60 px wider
    const wider = await lane(page);
    const widerReloaded = await reload();
    return { initial, shorter, reloaded, folded, foldedReloaded, unfolded, reset, wider, widerReloaded };
  });
  await context.close();
}

async function narrow(browser, out, errors) {
  const { context, page } = await open(browser, 'file://' + REPORT, errors, { viewport: { width: 390, height: 844 } });
  await step(out, 'narrow', async () => await lane(page));
  await context.close();
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = {};
  const errors = [];
  try {
    for (const job of [main, eyes, zoom, sizes, narrow]) {
      try { await job(browser, out, errors); } catch (error) { out['crashed:' + job.name] = String(error); }
    }
  } finally {
    await browser.close();
  }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
"""


def _payload(report: Path) -> dict:
    text = report.read_text("utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-data">(.*?)</script>', text, re.S)
    assert match, "no payload in the report"
    return json.loads(match.group(1).replace("<\\/", "</"))["comparisons"][0]


def _moments(page: dict) -> dict[str, dict]:
    """Each run's moments, computed here from the payload: its envelope (largest |reference - run| over every joint per
    plot sample, radians), worst moment (time and size) and "error rises" (the first sample above half its peak)."""

    grid = np.asarray(page["plot_t"], dtype=float)
    out = {}
    for sit in page["situations"]:
        if sit["role"] == "target" or not sit.get("has_data") or not (sit.get("plot") or {}).get("err_q"):
            continue
        columns = np.array([[np.nan if value is None else abs(value) for value in column] for column in sit["plot"]["err_q"]])
        envelope = np.nanmax(columns, axis=0)
        worst = int(np.nanargmax(envelope))
        rise = int(np.argmax(envelope > envelope[worst] / 2))
        out[sit["name"]] = {
            "title": sit["title"], "group": sit.get("group"), "envelope": envelope, "worst_t": float(grid[worst]),
            "worst_size": float(envelope[worst]), "rise_t": float(grid[rise]),
        }
    return out


@pytest.fixture(scope="module")
def lane_run(tmp_path_factory) -> dict:
    """The 3-DOF fixture report driven once: every step's readback, plus the payload and its own moments."""

    root = tmp_path_factory.mktemp("time_lane")
    report = write_comparison_report(scaling_comparison("3dof"), root / "report")
    document = report.read_text()
    assert document.count(SCENE_HOOK) == 1, "viewer3d.js no longer adds its grid once: update the scene hook"
    hooked = report.with_name("report_hooked.html")
    hooked.write_text(document.replace(SCENE_HOOK, SCENE_HOOK + " window.__scenes.push(scene);"))
    (root / "driver.js").write_text(LANE_DRIVER)
    result = subprocess.run(
        ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(hooked), str(CHROME)],
        capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr[-3000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    crashed = {key: value for key, value in out.items() if key.startswith("crashed:")}
    assert not crashed, crashed
    page = _payload(report)
    out["payload"] = page
    out["moments"] = _moments(page)
    out["dt"] = page["plot_t"][1] - page["plot_t"][0]
    return out


def _t_at(lane: dict, x: float) -> float:
    """The time at viewport x, through the first shown chart's own x scale (its plotting area's box)."""

    chart = lane["charts"][0]
    return chart["min"] + (x - chart["over"]["x"]) / chart["over"]["w"] * (chart["max"] - chart["min"])


def _px(lane: dict) -> float:
    chart = lane["charts"][0]
    return (chart["max"] - chart["min"]) / chart["over"]["w"]


def _centre(box: dict) -> float:
    return box["x"] + box["w"] / 2


def _track(lane: dict, name: str) -> dict:
    hits = [track for track in lane["tracks"] if track["name"] == name]
    assert len(hits) == 1, f"{len(hits)} lane tracks for {name!r}"
    return hits[0]


def _marker_t(lane: dict, name: str, kind: str) -> float | None:
    marks = [mark for mark in _track(lane, name)["moments"] if mark["kind"] == kind and mark["drawn"]]
    assert len(marks) <= 1, f"{name}: {len(marks)} drawn {kind} markers"
    return _t_at(lane, _centre(marks[0]["box"])) if marks else None


def _assert_line_at(lane: dict, time: float, where: str) -> None:
    """Exactly one line ``[data-tc-line]`` is drawn, through every shown chart's plotting area at ``time``."""

    drawn = [line for line in lane["lines"] if line["drawn"]]
    assert len(drawn) == 1, f"{where}: {len(drawn)} [data-tc-line] drawn, wants one line for the page"
    line = drawn[0]["box"]
    charts = lane["charts"]
    assert charts, f"{where}: no chart shown"
    first = min(charts, key=lambda chart: chart["over"]["y"])
    last = max(charts, key=lambda chart: chart["over"]["y"])
    assert line["y"] <= first["over"]["y"] + 1 and line["y"] >= first["over"]["y"] - 14, (
        f"{where}: the line starts at y {line['y']}, the first chart's plot at {first['over']['y']}"
    )
    assert line["y"] + line["h"] >= last["over"]["y"] + last["over"]["h"] - 1, f"{where}: the line stops above the last chart"
    for chart in charts:
        x = chart["over"]["x"] + (time - chart["min"]) / (chart["max"] - chart["min"]) * chart["over"]["w"]
        assert abs(_centre(line) - x) <= 1.5, f"{where}: the line is at x {_centre(line):.1f}, {chart['title']!r} draws t at {x:.1f}"


def _angle(text: str | None) -> float:
    match = re.match(r"\s*(-?[0-9.]+(?:e-?\d+)?)\s*°", text or "")
    assert match, f"not an angle in degrees: {text!r}"
    return float(match.group(1))


# ── the lane: docked, one track per run, the only time control ──────────────────────────────────────────────────────


def test_the_lane_is_docked_under_the_tabs_with_one_track_per_run(lane_run):
    lane = _step(lane_run, "initial")["lane"]
    page = lane_run["payload"]
    assert lane["lanes"] == 1 and lane["laneDrawn"], "no time lane [data-tc-lane] drawn"
    assert lane["lane"]["y"] + lane["lane"]["h"] <= lane["page"]["h"] + 1, f"the lane is below the screen: {lane['lane']}"
    panel = lane["panel"]
    assert abs(lane["lane"]["x"] - panel["x"]) <= 2 and abs(lane["lane"]["w"] - panel["w"]) <= 2, (
        f"the lane {lane['lane']} is not under the tabs column {panel}"
    )
    wanted = [sit["name"] for sit in page["situations"] if sit.get("has_data")]
    assert [track["name"] for track in lane["tracks"]] == wanted, "one lane track per situation, in the payload's order"
    for track in lane["tracks"]:
        if track["name"] == "target":
            continue
        assert track["eye"] and track["eye"]["pressed"] == "true" and track["shown"] == "true", track
    assert sorted(group["key"] for group in lane["groups"]) == ["real", "sim"], lane["groups"]
    assert lane["count"] == "4 of 4 shown", lane["count"]
    scrolled = _step(lane_run, "scrolled")
    assert scrolled["page"]["y"] > 100, "the page did not scroll: the fixture is too short to test docking"
    assert scrolled["laneDrawn"] and scrolled["lane"]["y"] >= 0 and scrolled["lane"]["y"] + scrolled["lane"]["h"] <= scrolled["page"]["h"] + 1, (
        f"scrolled {scrolled['page']['y']} px, the lane left the screen: {scrolled['lane']}"
    )


def test_the_lane_ruler_is_the_pages_only_slider(lane_run):
    lane = _step(lane_run, "initial")["lane"]
    assert lane["rulerDrawn"] and lane["rulerRole"] == "slider", "the ruler [data-tc-ruler] is not a drawn slider"
    assert lane["otherSliders"] == 0, f"{lane['otherSliders']} other time sliders drawn: the lane is the one time control"
    assert _close(lane["rulerNow"], lane["tMax"], 1e-9), "a fresh page's ruler sits at the end, as the playheads do"


def test_the_ruler_and_every_chart_share_the_same_x_pixels(lane_run):
    for key, lane in (("track", _step(lane_run, "initial")["lane"]), ("joints", _step(lane_run, "joints"))):
        assert len(lane["charts"]) >= 2, f"{key}: wants at least two charts"
        for chart in lane["charts"]:
            assert abs(chart["over"]["x"] - lane["ruler"]["x"]) <= 1 and abs(chart["over"]["w"] - lane["ruler"]["w"]) <= 1, (
                f"{key}: {chart['title']!r} plots on x {chart['over']['x']:.1f} + {chart['over']['w']:.1f}, the ruler on "
                f"{lane['ruler']['x']:.1f} + {lane['ruler']['w']:.1f}"
            )
        for track in lane["tracks"]:
            assert abs(track["time"]["x"] - lane["ruler"]["x"]) <= 1 and abs(track["time"]["w"] - lane["ruler"]["w"]) <= 1, track


def test_one_line_runs_through_every_chart_at_the_committed_time(lane_run):
    drag = _step(lane_run, "rulerDrag")
    _assert_line_at(drag["releasedLane"], drag["released"]["t"], "track tab, after a ruler drag")
    _assert_line_at(drag["midLane"], drag["mid"]["t"], "track tab, mid-drag")
    joints = _step(lane_run, "jointsRuler")
    _assert_line_at(joints["lane"], joints["rb"]["t"], "joints tab")


# ── moments: worst, error rises; the answer box agrees ──────────────────────────────────────────────────────────────


def test_each_runs_worst_moment_marker_sits_at_its_worst_moment(lane_run):
    lane = _step(lane_run, "initial")["lane"]
    dt, px = lane_run["dt"], _px(lane)
    for name, moment in lane_run["moments"].items():
        drawn = _marker_t(lane, name, "worst")
        assert _close(drawn, moment["worst_t"], 1.5 * px), (
            f"{name}: the worst-moment marker is drawn at {drawn} s, its largest joint error is at {moment['worst_t']} s"
        )
        rise = _marker_t(lane, name, "rise")
        if abs(moment["rise_t"] - moment["worst_t"]) > 1.5 * dt:
            assert _close(rise, moment["rise_t"], 1.5 * px), f"{name}: error-rises marker at {rise} s, wants {moment['rise_t']} s"


def test_the_worst_runs_marker_is_the_answer_boxs_worst_moment(lane_run):
    lane = _step(lane_run, "initial")["lane"]
    worst_title = re.search(r"Worst run: (.+?), mean joint RMS error", lane["answer"] or "").group(1)
    said = float(re.search(r"Its worst moment: .* at t = ([0-9.]+) s", lane["detail"] or "").group(1))
    (name,) = [name for name, moment in lane_run["moments"].items() if moment["title"] == worst_title]
    drawn = _marker_t(lane, name, "worst")
    assert _close(drawn, said, 0.005 + 1.5 * _px(lane)), f"the answer says t = {said} s, {name}'s marker is at {drawn} s"


# ── the ruler and the tracks scrub: every chart, the 3D and the lane's readouts follow ──────────────────────────────


def _assert_readouts(lane: dict, moments: dict, payload: dict, time: float, where: str) -> None:
    grid = np.asarray(payload["plot_t"])
    index = int(np.argmin(np.abs(grid - time)))
    for name, moment in moments.items():
        shown = _angle(_track(lane, name)["value"])
        wanted = moment["envelope"][index] * RAD2DEG
        assert abs(shown - wanted) <= 0.006 * abs(wanted) + 1e-9, f"{where}: {name} reads {shown}° at t, its error is {wanted:.4g}°"
    assert lane["readout"] and lane["readout"].startswith(f"{time:.2f} / "), f"{where}: the readout says {lane['readout']!r}"


def test_dragging_the_ruler_moves_every_chart_the_3d_and_the_readouts_live(lane_run):
    drag = _step(lane_run, "rulerDrag")
    dt = lane_run["dt"]
    for phase in ("pressed", "mid", "released"):
        expect = drag["expect"][phase]
        assert _close(drag[phase]["t"], expect["t"], _pointer_tolerance(expect, dt)), (
            f"ruler {phase}: committed {drag[phase]['t']} s, the pointer was at {expect['t']:.4f} s"
        )
        _assert_everything_at(drag[phase], drag[phase]["t"], f"ruler drag {phase}")
    _assert_readouts(drag["midLane"], lane_run["moments"], lane_run["payload"], drag["mid"]["t"], "mid-drag")
    _assert_readouts(drag["releasedLane"], lane_run["moments"], lane_run["payload"], drag["released"]["t"], "released")


def test_dragging_a_runs_track_moves_the_time_too(lane_run):
    drag = _step(lane_run, "trackDrag")
    dt = lane_run["dt"]
    for phase in ("mid", "released"):
        expect = drag["expect"][phase]
        assert _close(drag[phase]["t"], expect["t"], _pointer_tolerance(expect, dt)), (
            f"track {phase}: committed {drag[phase]['t']} s, the pointer was at {expect['t']:.4f} s"
        )
        _assert_everything_at(drag[phase], drag[phase]["t"], f"track drag {phase}")


def test_the_ruler_moves_the_charts_of_a_tab_opened_later(lane_run):
    step = _step(lane_run, "jointsRuler")
    assert step["rb"]["activeTab"] == "joints"
    assert _close(step["rb"]["t"], step["expect"]["t"], _pointer_tolerance(step["expect"], lane_run["dt"]))
    _assert_everything_at(step["rb"], step["rb"]["t"], "joints tab, a click on the ruler", dots=True)


def test_worst_moment_and_the_moment_arrows_jump_there(lane_run):
    moments = lane_run["moments"]
    dt = lane_run["dt"]
    worst = max(moments.values(), key=lambda moment: moment["worst_size"])
    jumped = _step(lane_run, "jumpWorst")
    assert _close(jumped["t"], worst["worst_t"], dt / 2), f"Worst moment went to {jumped['t']} s, wants {worst['worst_t']} s"
    marked = sorted({round(moment["worst_t"], 9) for moment in moments.values()} | {
        round(moment["rise_t"], 9) for moment in moments.values() if abs(moment["rise_t"] - moment["worst_t"]) > 1.5 * dt
    })
    later = [time for time in marked if time > worst["worst_t"] + dt / 2]
    after = _step(lane_run, "jumpNext")
    if later:
        assert _close(after["t"], later[0], dt / 2), f"› went to {after['t']} s, the next marked moment is {later[0]} s"
    else:
        assert _close(after["t"], worst["worst_t"], dt / 2), "› past the last moment must stay put"
    before = [time for time in marked if time < after["t"] - dt / 2]
    back = _step(lane_run, "jumpPrev")
    assert before and _close(back["t"], before[-1], dt / 2), f"‹ went to {back['t']} s, the moment before is {before[-1:]}"
    click = _step(lane_run, "markerClick")
    assert _close(click["lane"]["t"], moments["sim"]["worst_t"], dt / 2), "a click on sim's worst-moment marker goes there"
    _assert_everything_at(click["rb"], moments["sim"]["worst_t"], "after a marker click", dots=True)


# ── a run's eye hides it everywhere ──────────────────────────────────────────────────────────────────────────────────


def _series_shown(lane: dict, title: str) -> list[bool]:
    return [series["show"] for chart in lane["charts"] for series in chart["series"] if series["label"] == title]


def test_a_runs_eye_hides_it_on_every_chart_the_3d_the_answer_and_the_count(lane_run):
    step = _step(lane_run, "eye")
    name, title = step["name"], step["title"]
    assert name, f"no situation titled {title!r}"
    hidden = step["hidden"]
    assert hidden["visible"].get(name) is False, f"the eye did not hide {name}"
    track = _track(hidden, name)
    assert track["shown"] == "false" and track["eye"]["pressed"] == "false", track
    assert _series_shown(hidden, title) and not any(_series_shown(hidden, title)), f"{title} still drawn on a chart"
    assert title not in (hidden["answer"] or ""), f"the answer names the hidden run: {hidden['answer']!r}"
    assert hidden["count"] == "3 of 4 shown", hidden["count"]
    arms = {robot["name"]: robot["visible"] for robot in step["hiddenRb"]["robots"]}
    assert arms.get(name) is False, f"the {name} arm is still shown in the 3D: {arms}"
    restored = step["restored"]
    assert restored["visible"].get(name) is not False and all(_series_shown(restored, title)), "the eye did not bring it back"
    assert restored["count"] == "4 of 4 shown"
    group = step["groupHidden"]
    real = [run for run, moment in lane_run["moments"].items() if moment["group"] == "real"]
    assert real and all(group["visible"].get(run) is False for run in real), f"the real group's eye left some on: {group['visible']}"
    assert group["count"] == f"{4 - len(real)} of 4 shown", group["count"]
    assert all(step["groupRestored"]["visible"].get(run) is not False for run in real)


# ── zoom: the zoom bar, Full range, and the window follows a chart zoom ─────────────────────────────────────────────


def test_the_zoom_bar_zooms_every_chart_alike_without_moving_the_time(lane_run):
    step = _step(lane_run, "zoomBar")
    before, zoomed = step["before"], step["zoomed"]
    span = before["tMax"] - before["tMin"]
    lo, hi = before["tMin"] + 0.3 * span, before["tMin"] + 0.6 * span
    tolerance = 2 * span / before["zoomBar"]["w"] + lane_run["dt"]
    for chart in zoomed["charts"]:
        assert _close(chart["min"], lo, tolerance) and _close(chart["max"], hi, tolerance), (
            f"{chart['title']!r} shows {chart['min']:.3f}..{chart['max']:.3f} s after the zoom bar's {lo:.3f}..{hi:.3f} s"
        )
    assert zoomed["t"] == before["t"], "zooming moved the time"
    for chart in step["reset"]["charts"]:
        assert _close(chart["min"], before["tMin"], 1e-6) and _close(chart["max"], before["tMax"], 1e-6), "Full range"


def test_the_zoom_window_shows_a_shift_drag_zoom(lane_run):
    lane = _step(lane_run, "shiftZoomWindow")
    chart = lane["charts"][0]
    assert chart["max"] - chart["min"] < 0.9 * (lane["tMax"] - lane["tMin"]), "Shift-drag did not zoom"
    bar, window = lane["zoomBar"], lane["zoomWindow"]
    assert lane["zoomWindowDrawn"], "no zoom window drawn while zoomed"
    span = lane["tMax"] - lane["tMin"]
    left = bar["x"] + (chart["min"] - lane["tMin"]) / span * bar["w"]
    right = bar["x"] + (chart["max"] - lane["tMin"]) / span * bar["w"]
    assert abs(window["x"] - left) <= 2 and abs(window["x"] + window["w"] - right) <= 2, (
        f"the zoom window spans {window['x']:.1f}..{window['x'] + window['w']:.1f}, the charts {left:.1f}..{right:.1f}"
    )
    assert abs(lane["ruler"]["x"] - chart["over"]["x"]) <= 1, "zoomed, the ruler still sits on the charts' x pixels"


# ── fold, height, names column: draggable and remembered ────────────────────────────────────────────────────────────


def test_the_lane_height_drags_and_is_remembered(lane_run):
    step = _step(lane_run, "size")
    initial, shorter, reloaded = step["initial"], step["shorter"], step["reloaded"]
    assert abs(shorter["lane"]["h"] - (initial["lane"]["h"] - 50)) <= 3, (
        f"dragging the lane's edge 50 px down: {initial['lane']['h']:.0f} -> {shorter['lane']['h']:.0f} px"
    )
    assert abs(reloaded["lane"]["h"] - shorter["lane"]["h"]) <= 1, "a reload forgot the lane's height"
    assert abs(step["reset"]["lane"]["h"] - initial["lane"]["h"]) <= 1, "a double-click on the edge restores the default"


def test_the_lane_folds_to_its_ruler_and_the_fold_is_remembered(lane_run):
    step = _step(lane_run, "size")
    folded, again, unfolded = step["folded"], step["foldedReloaded"], step["unfolded"]
    for where, lane in (("folded", folded), ("folded, reloaded", again)):
        assert lane["folded"], f"{where}: the lane is not folded"
        assert not lane["tracksDrawn"], f"{where}: the tracks still show"
        assert lane["rulerDrawn"], f"{where}: the ruler must stay (it is the page's slider)"
        assert lane["lane"]["h"] < step["reloaded"]["lane"]["h"] - 60, f"{where}: folding gave back no height"
    assert not unfolded["folded"] and unfolded["tracksDrawn"]
    assert abs(unfolded["lane"]["h"] - step["reloaded"]["lane"]["h"]) <= 1, "unfolding restores the remembered height"


def test_the_names_column_drags_the_charts_title_column_follows_and_is_remembered(lane_run):
    step = _step(lane_run, "size")
    reset, wider, again = step["reset"], step["wider"], step["widerReloaded"]
    assert abs(wider["ruler"]["x"] - (reset["ruler"]["x"] + 60)) <= 3, f"ruler {reset['ruler']['x']} -> {wider['ruler']['x']}"
    for lane in (wider, again):
        for chart in lane["charts"]:
            assert abs(chart["over"]["x"] - lane["ruler"]["x"]) <= 1, f"{chart['title']!r} left the ruler's x pixels"
    assert abs(again["ruler"]["x"] - wider["ruler"]["x"]) <= 1, "a reload forgot the names column's width"


def test_no_sideways_scroll_at_390_px_and_the_lane_still_shows(lane_run):
    narrow = _step(lane_run, "narrow")
    assert narrow["page"]["scroll"] <= narrow["page"]["w"], f"sideways scroll at 390 px: {narrow['page']}"
    assert narrow["laneDrawn"] and narrow["rulerDrawn"]
    assert narrow["lane"]["x"] >= 0 and narrow["lane"]["x"] + narrow["lane"]["w"] <= narrow["page"]["w"] + 1


def test_no_console_errors(lane_run):
    assert lane_run["errors"] == []
