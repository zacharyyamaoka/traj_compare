"""The HTML run view's question tabs, stage and parts, measured in headless Chrome (written before the UI, 2026-11-19).

Contract: docs/NAVIGATION.md Part B (frozen 2026-11-19). Zach, daily note 2026-11-19 (traj compare view feedback):
"100% we need to do the tabbed model"; keep the 3D always showing; tab titles "super descriptive"; "split the arm
and the hand into separate concerns, and each arm separately ... Hand can have 1 - N motors (perhaps you group by
finger)".

One browser opens four fixture reports (tests/scaling_fixtures.py; tool frame + torque breakdown on):

- 3-DOF: the tab strip's titles in order; a click shows only that tab's panel under its exact heading; the stage
  and its 3D canvas stay on every tab; the stage edge drags and the width survives a reload; the stage folds;
  the active tab survives a reload; ``report.html#tab=torque`` opens the torque tab; no console errors.
- 1-DOF: no joints tab, no ranking, no part selector.
- 6-DOF: six ranking bars, worst first, no part selector.
- Bimanual, 46 motors: a part selector of four labelled ``<part> · <n> joints``; 46 ranking bars, worst first,
  labelled ``<part> · <joint>``; clicking a hand bar selects the hand part; a hand part draws five finger rows.

Hooks the contract names: ``[data-tc-tabs]``, ``[data-tc-tab="<id>"]`` (``aria-selected``), ``[data-tc-panel="<id>"]``,
``[data-tc-tab-heading]``, ``[data-tc-stage]``, ``[data-tc-stage-resize]``, ``[data-tc-stage-fold]``,
``[data-tc-rank]``, ``[data-tc-rank-bar]`` (``data-joint``), ``[data-tc-part="<index>"]``. Two this file adds, the
smallest the contract implies: a part button's selected state is ``aria-selected="true"`` (as the tab buttons), and a
hand's finger row is ``[data-tc-finger="<finger>"]`` inside the joints panel. Spatial claims are measured with
getBoundingClientRect, never DOM presence.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``, default the aruco-studio checkout's); skipped
otherwise. These tests are the acceptance ruler for the HTML lane: it must not edit this file. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_run_tabs_html.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scaling_fixtures import BIMANUAL_PART_LABELS, BIMANUAL_PARTS, FINGERS, scaling_comparison
from traj_compare import write_comparison_report
from traj_compare.analysis import analyze_comparison
from traj_compare.tabs import tabs_for

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

HAND_JOINT = "l_index_pip"  # a Left hand joint: clicking its bar selects part 2
DRAG_PX = 160

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const CLICK = { timeout: 3000 };

function snapshot() {
  const rect = (el) => {
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return { x: box.x, y: box.y, w: box.width, h: box.height };
  };
  const strip = document.querySelector('[data-tc-tabs]');
  const buttons = strip ? [...strip.querySelectorAll('[data-tc-tab]')].map((button) => ({
    id: button.getAttribute('data-tc-tab'), text: button.textContent.trim(), selected: button.getAttribute('aria-selected'),
  })) : null;
  const panels = [...document.querySelectorAll('[data-tc-panel]')].map((panel) => {
    const heading = panel.querySelector('[data-tc-tab-heading]');
    return { id: panel.getAttribute('data-tc-panel'), rect: rect(panel), heading: heading ? heading.textContent.trim() : null,
             headingRect: rect(heading) };
  });
  const stage = document.querySelector('[data-tc-stage]');
  const canvases = stage ? [...stage.querySelectorAll('canvas')].map(rect).sort((a, b) => b.w * b.h - a.w * a.h) : [];
  const joints = document.querySelector('[data-tc-panel="joints"]');
  const visible = (el) => { const box = el.getBoundingClientRect(); return box.width > 0 && box.height > 0; };
  const label = (el) => [el.textContent, el.getAttribute('aria-label') || '', el.getAttribute('title') || ''].join(' ');
  return {
    buttons, panels, stage: rect(stage), canvas: canvases[0] || null,
    counts: {
      jointsTab: document.querySelectorAll('[data-tc-tab="joints"]').length,
      rank: document.querySelectorAll('[data-tc-rank]').length,
      rankBars: document.querySelectorAll('[data-tc-rank-bar]').length,
      parts: document.querySelectorAll('[data-tc-part]').length,
    },
    joints: joints ? {
      rankBars: [...joints.querySelectorAll('[data-tc-rank-bar]')].map((bar) => ({ joint: bar.getAttribute('data-joint'), label: label(bar) })),
      parts: [...joints.querySelectorAll('[data-tc-part]')].map((part) => ({
        index: part.getAttribute('data-tc-part'), text: part.textContent.trim(), selected: part.getAttribute('aria-selected'),
      })),
      fingers: [...joints.querySelectorAll('[data-tc-finger]')].filter(visible).map((row) => row.getAttribute('data-tc-finger')),
    } : null,
  };
}

async function open(browser, url, errors) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(url);
  await settle(page);
  return { context, page };
}

async function settle(page) {
  try {
    await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages.length && TrajCompare.state.pages[0].builtPage,
                               null, { timeout: 20000 });
  } catch (error) { /* a renamed internal: fall back on time */ }
  await page.waitForTimeout(700);
}

async function attempt(record, key, step) {
  try { record[key] = await step(); } catch (error) { record[key] = { error: String(error).split('\n')[0] }; }
}

async function clickTab(page, id) {
  await page.click(`[data-tc-tabs] [data-tc-tab="${id}"]`, CLICK);
  await page.waitForTimeout(400);
  return await page.evaluate(snapshot);
}

async function full(browser, job, errors) {
  const url = 'file://' + job.report;
  const out = {};
  let { context, page } = await open(browser, url, errors);
  out.initial = await page.evaluate(snapshot);
  out.perTab = {};
  for (const id of job.tabIds) await attempt(out.perTab, id, () => clickTab(page, id));
  await attempt(out, 'resize', async () => {
    const handle = await page.$('[data-tc-stage-resize]');
    if (!handle) throw new Error('no [data-tc-stage-resize]');
    const box = await handle.boundingBox();
    if (!box) throw new Error('[data-tc-stage-resize] has no box');
    const before = (await page.evaluate(snapshot)).stage;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + job.dragPx, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(400);
    const after = (await page.evaluate(snapshot)).stage;
    await page.reload();
    await settle(page);
    const reloaded = (await page.evaluate(snapshot)).stage;
    return { before, after, reloaded };
  });
  await attempt(out, 'remember', async () => {
    await clickTab(page, 'torque');
    await page.reload();
    await settle(page);
    return await page.evaluate(snapshot);
  });
  await attempt(out, 'fold', async () => {
    const before = await page.evaluate(snapshot);
    await page.click('[data-tc-stage-fold]', CLICK);
    await page.waitForTimeout(500);
    return { before, after: await page.evaluate(snapshot) };
  });
  await context.close();
  ({ context, page } = await open(browser, url + '#tab=torque', errors));
  out.hash = await page.evaluate(snapshot);
  await context.close();
  return out;
}

async function scan(browser, job, errors) {
  const out = {};
  const { context, page } = await open(browser, 'file://' + job.report, errors);
  out.initial = await page.evaluate(snapshot);
  out.perTab = {};
  for (const button of out.initial.buttons || []) await attempt(out.perTab, button.id, () => clickTab(page, button.id));
  out.afterAll = await page.evaluate(snapshot);
  if (job.handJoint) {
    await attempt(out, 'handClick', async () => {
      await clickTab(page, 'joints');
      await page.click(`[data-tc-panel="joints"] [data-tc-rank-bar][data-joint="${job.handJoint}"]`, CLICK);
      await page.waitForTimeout(600);
      return await page.evaluate(snapshot);
    });
  }
  await context.close();
  return out;
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const results = {};
  try {
    for (const job of jobs) {
      const errors = [];
      try {
        results[job.name] = job.kind === 'full' ? await full(browser, job, errors) : await scan(browser, job, errors);
      } catch (error) {
        results[job.name] = { crashed: String(error) };
      }
      results[job.name].errors = errors;
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(results));
})();
"""


def _worst_first(payload: dict) -> list[str]:
    """Joints by the RMS joint error of their worst run, worst first (NAVIGATION.md: the ``joints`` ranking)."""

    runs = [entry for entry in payload["situations"] if entry["role"] != "target" and entry["error_metrics"]]
    worst = {
        joint: max(entry["error_metrics"][f"positions/{joint}"]["rms"] for entry in runs) for joint in payload["joint_names"]
    }
    return sorted(payload["joint_names"], key=lambda joint: -worst[joint])


@pytest.fixture(scope="module")
def browser(tmp_path_factory) -> dict:
    """Every fixture report, driven once in one headless Chrome; ``{shape: (payload, measurements)}``."""

    root = tmp_path_factory.mktemp("run_tabs_html")
    jobs, payloads = [], {}
    for shape, kind in (("3dof", "full"), ("1dof", "scan"), ("6dof", "scan"), ("bimanual", "scan")):
        comparison = scaling_comparison(shape)
        payloads[shape] = analyze_comparison(comparison)
        report = write_comparison_report(comparison, root / shape)
        job = {"name": shape, "kind": kind, "report": str(report)}
        if kind == "full":
            job.update(tabIds=[tab["id"] for tab in tabs_for(payloads[shape])], dragPx=DRAG_PX)
        if shape == "bimanual":
            job["handJoint"] = HAND_JOINT
        jobs.append(job)
    (root / "jobs.json").write_text(json.dumps(jobs))
    (root / "driver.js").write_text(DRIVER)
    result = subprocess.run(
        ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(root / "jobs.json")],
        capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr[-3000:]
    measured = json.loads(result.stdout.strip().splitlines()[-1])
    for shape, record in measured.items():
        assert "crashed" not in record, f"{shape}: the driver crashed: {record['crashed']}"
    return {shape: (payloads[shape], measured[shape]) for shape in payloads}


def _area(rect: dict | None) -> float:
    return 0.0 if not rect else rect["w"] * rect["h"]


def _strip(snapshot: dict) -> list[dict]:
    assert snapshot["buttons"] is not None, "no tab strip [data-tc-tabs]"
    return snapshot["buttons"]


def _measured(record: dict, key: str) -> dict:
    assert key in record, f"{key}: never measured (its tab button was not in the [data-tc-tabs] strip)"
    value = record[key]
    assert "error" not in value, f"{key}: {value['error']}"
    return value


def _panel(snapshot: dict, tab_id: str) -> dict:
    panels = {panel["id"]: panel for panel in snapshot["panels"]}
    assert tab_id in panels, f'no [data-tc-panel="{tab_id}"]; panels: {sorted(panels)}'
    return panels[tab_id]


def _selected(snapshot: dict) -> list[str]:
    return [button["id"] for button in _strip(snapshot) if button["selected"] == "true"]


# ── 3 DOF: the tabs, the stage ───────────────────────────────────────────────


def test_tab_strip_shows_the_exact_titles_in_order(browser):
    payload, record = browser["3dof"]
    buttons = _strip(record["initial"])
    assert [button["text"] for button in buttons] == [tab["title"] for tab in tabs_for(payload)]
    assert [button["id"] for button in buttons] == ["track", "where", "joints", "timing", "torque", "signals"]
    assert _selected(record["initial"]) == ["track"]  # a fresh page opens on the first question


def test_clicking_a_tab_shows_only_its_panel_under_its_exact_heading(browser):
    payload, record = browser["3dof"]
    for tab in tabs_for(payload):
        snapshot = _measured(record["perTab"], tab["id"])
        assert _selected(snapshot) == [tab["id"]]
        panel = _panel(snapshot, tab["id"])
        assert _area(panel["rect"]) > 0, f"{tab['id']}: its panel is not visible"
        assert panel["heading"] == tab["heading"], f"{tab['id']}: heading {panel['heading']!r}"
        assert _area(panel["headingRect"]) > 0, f"{tab['id']}: its heading is not visible"
        assert panel["rect"]["h"] > panel["headingRect"]["h"] + 40, f"{tab['id']}: the panel shows nothing under its heading"
        hidden = [other["id"] for other in snapshot["panels"] if other["id"] != tab["id"] and _area(other["rect"]) > 0]
        assert hidden == [], f"{tab['id']}: other panels still visible: {hidden}"


def test_the_stage_and_its_3d_canvas_stay_visible_on_every_tab(browser):
    payload, record = browser["3dof"]
    for tab in tabs_for(payload):
        snapshot = _measured(record["perTab"], tab["id"])
        assert _area(snapshot["stage"]) > 0, f"{tab['id']}: no visible [data-tc-stage]"
        assert _area(snapshot["canvas"]) > 0, f"{tab['id']}: the stage's 3D canvas is not visible"
        panel = _panel(snapshot, tab["id"])["rect"]
        stage = snapshot["stage"]
        assert stage["x"] + stage["w"] <= panel["x"] + 2, f"{tab['id']}: the stage is not a pane left of the tabs (1400 px wide)"


def test_dragging_the_stage_edge_resizes_it_and_a_reload_keeps_the_width(browser):
    _, record = browser["3dof"]
    resize = _measured(record, "resize")
    before, after, reloaded = resize["before"]["w"], resize["after"]["w"], resize["reloaded"]["w"]
    assert abs(after - before) >= DRAG_PX / 2, f"dragging {DRAG_PX} px moved the stage edge {after - before:.0f} px"
    assert abs(reloaded - after) <= 3, f"after a reload the stage is {reloaded:.0f} px, was dragged to {after:.0f} px"


def test_the_stage_folds_and_gives_its_width_to_the_tabs(browser):
    _, record = browser["3dof"]
    fold = _measured(record, "fold")
    before, after = fold["before"], fold["after"]
    active = _selected(before)[0]
    assert _area(before["canvas"]) > 0
    assert _area(after["canvas"]) == 0, "folded, the 3D canvas still shows"
    assert _panel(after, active)["rect"]["w"] > _panel(before, active)["rect"]["w"] + 100, "folding gave the tabs no room"


def test_the_active_tab_survives_a_reload(browser):
    _, record = browser["3dof"]
    assert _selected(_measured(record, "remember")) == ["torque"]


def test_hash_tab_opens_that_tab(browser):
    payload, record = browser["3dof"]
    snapshot = record["hash"]
    assert _selected(snapshot) == ["torque"]
    torque = _panel(snapshot, "torque")
    assert _area(torque["rect"]) > 0
    assert torque["heading"] == next(tab["heading"] for tab in tabs_for(payload) if tab["id"] == "torque")


@pytest.mark.parametrize("shape", ["3dof", "1dof", "6dof", "bimanual"])
def test_no_console_errors(browser, shape):
    _, record = browser[shape]
    assert _strip(record["initial"])  # a page that never built its tabs cannot count as error-free
    assert record["errors"] == []


# ── scaling with joint count ─────────────────────────────────────────────────


def test_one_joint_has_no_joints_tab_no_ranking_and_no_part_selector(browser):
    payload, record = browser["1dof"]
    buttons = _strip(record["initial"])
    assert [button["text"] for button in buttons] == [tab["title"] for tab in tabs_for(payload)]
    assert [button["id"] for button in buttons] == ["track", "where", "timing", "torque", "signals"]
    assert len(record["perTab"]) == len(buttons) and not any("error" in value for value in record["perTab"].values())
    counts = record["afterAll"]["counts"]  # every tab has been opened, so every panel is built
    assert counts["jointsTab"] == 0 and counts["rank"] == 0 and counts["parts"] == 0, counts


def test_six_joints_rank_six_bars_worst_first_without_a_part_selector(browser):
    payload, record = browser["6dof"]
    assert "joints" in [button["id"] for button in _strip(record["initial"])]
    joints = _measured(record["perTab"], "joints")["joints"]
    assert joints is not None, 'no [data-tc-panel="joints"]'
    assert [bar["joint"] for bar in joints["rankBars"]] == _worst_first(payload)
    assert record["afterAll"]["counts"]["parts"] == 0, "one part draws no part selector"


def test_46_motors_get_a_part_selector_of_four(browser):
    _, record = browser["bimanual"]
    joints = _measured(record["perTab"], "joints")["joints"]
    assert joints is not None, 'no [data-tc-panel="joints"]'
    assert [part["index"] for part in joints["parts"]] == ["0", "1", "2", "3"]
    assert [part["text"] for part in joints["parts"]] == BIMANUAL_PART_LABELS


def test_46_motors_rank_46_bars_worst_first_labelled_by_part(browser):
    payload, record = browser["bimanual"]
    bars = _measured(record["perTab"], "joints")["joints"]["rankBars"]
    assert len(bars) == 46
    assert [bar["joint"] for bar in bars] == _worst_first(payload)
    part_of = {joint: part["name"] for part in payload["parts"] for group in part["groups"] for joint in group["joints"]}
    for bar in bars:
        assert f"{part_of[bar['joint']]} · {bar['joint']}" in bar["label"], f"bar {bar['joint']!r} is labelled {bar['label']!r}"


def test_clicking_a_hand_bar_selects_the_hand_and_it_draws_five_finger_rows(browser):
    _, record = browser["bimanual"]
    left_hand = list(BIMANUAL_PARTS).index("Left hand")
    joints = _measured(record, "handClick")["joints"]
    assert [part["index"] for part in joints["parts"] if part["selected"] == "true"] == [str(left_hand)]
    assert joints["fingers"] == list(FINGERS), f"visible finger rows: {joints['fingers']}"


def test_the_fixtures_worst_first_order_is_strict():
    """A tie would make 'worst first' untestable: the fixtures' worst-run RMS errors are all distinct."""

    for shape in ("6dof", "bimanual"):
        payload = analyze_comparison(scaling_comparison(shape))
        runs = [entry for entry in payload["situations"] if entry["role"] != "target"]
        worst = [max(entry["error_metrics"][f"positions/{joint}"]["rms"] for entry in runs) for joint in payload["joint_names"]]
        assert len(np.unique(np.round(worst, 9))) == len(worst)
