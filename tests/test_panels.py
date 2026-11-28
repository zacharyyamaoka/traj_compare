"""Comparison.panels (traj_compare.panels): the step band, the table at the playhead, the time table.

The Python tests pin the payload both viewers read; the browser test drives the real page: the band's readout, the
table's cells and the log's marked row must follow the page's one transport, and a click must move it.
Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``) for the browser test; skipped otherwise.
"""

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from traj_compare import (
    Changes,
    Comparison,
    PanelTab,
    PlayheadColumn,
    PlayheadTable,
    Situation,
    StepSpan,
    StepTrack,
    TimeRow,
    TimeTable,
    analyze_comparison,
    write_comparison_report,
)
from traj_compare.panels import panels_payload
from traj_compare.report import VIEWER_ASSETS

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
T = np.arange(0.0, 4.0001, 0.1)


def _panels():
    recipe = StepTrack("Recipe", [
        StepSpan(0.0, 0.0, 'hold("shoulder", 12.0)', "a helper call", kind="Recipe line"),
        StepSpan(0.0, 2.0, 'find_hardstop("elbow", -1, 0.3, 3.0, 1.2)', "expands to Command → Condition → Command",
                 kind="Recipe line"),
        StepSpan(2.0, 3.0, 'move_to("elbow", -1.0, 1.0, 8.0)', "expands to Command → Condition", kind="Recipe line"),
    ], words="as written", mono=True)  # fmt: skip
    primitives = StepTrack("Primitive", [
        StepSpan(0.0, 2.0, "#2 Condition", "until InCollision(elbow)", kind="Condition"),
        StepSpan(2.0, 2.0, "#3 Command", "elbow: hold here", kind="Command"),
        StepSpan(2.0, 3.0, "#5 Condition", "until Reached(elbow)", kind="Condition", tone="danger"),
    ])
    now = PlayheadTable("Now", ["shoulder", "elbow"], [
        PlayheadColumn("Servo", ["CAN 11", "CAN 12"]),
        PlayheadColumn("Mode", [Changes([(0.0, "holding")]), Changes([(0.0, "moving"), (2.0, "holding", "positive")])]),
        PlayheadColumn("position", [np.zeros(len(T)), np.where(T < 2.0, T * 10.0, np.nan)], group="Command being sent",
                       unit="°", signed=True),
        PlayheadColumn("effort cap", [12.0, Changes([(0.0, 3.0), (2.0, 8.0)])], group="Command being sent", unit="N·m",
                       decimals=1),
    ], t=T, heading="At the playhead")  # fmt: skip
    log = TimeTable("Command log", ["Step", "Values"], [
        TimeRow(0.0, ["home", "hold shoulder"], kind="command"),
        TimeRow(0.0, ["home", "seek elbow"], kind="command"),
        TimeRow(2.0, ["", "elbow touched its stop"], kind="truth", tone="muted"),
        TimeRow(2.0, ["park", "move elbow"], kind="command"),
        TimeRow(math.inf, ["park", "stop all"], kind="command", tone="muted"),
    ], kinds={"command": "commands", "truth": "truth"}, mono=("Values",))  # fmt: skip
    outline = TimeTable("Recipe", ["Line"], [
        TimeRow(0.0, ["Home the elbow"], end=2.0, level=0),
        TimeRow(0.0, ['find_hardstop("elbow", -1, 0.3, 3.0, 1.2)'], end=2.0, level=1),
        TimeRow(0.0, ["#1 Command"], end=0.0, level=2),
        TimeRow(0.0, ["#2 Condition"], end=2.0, level=2),
        TimeRow(2.0, ["Park"], end=3.0, level=0),
        TimeRow(2.0, ['move_to("elbow", -1.0, 1.0, 8.0)'], end=3.0, level=1),
        TimeRow(2.0, ["#5 Condition"], end=3.0, level=2),
    ], open_level=1)  # fmt: skip
    return [recipe, primitives, now, log, outline]


def _comparison(**options):
    q = np.stack([np.zeros(len(T)), np.minimum(T, 2.0)], axis=1)
    return Comparison("Home elbow", ("shoulder", "elbow"), [Situation("truth", "Truth", T, q)], **options)


def test_a_comparison_without_panels_is_unchanged():
    payload = analyze_comparison(_comparison())
    assert "panels" not in payload
    assert all("panel" not in tab for tab in payload["tabs"])
    assert panels_payload(()) is None


def test_the_payload_carries_the_band_and_leads_the_tabs_with_the_panel_tabs():
    payload = analyze_comparison(_comparison(panels=_panels()))
    panels = payload["panels"]
    assert [track["title"] for track in panels["tracks"]] == ["Recipe", "Primitive"]
    assert panels["tracks"][0]["mono"] is True and panels["tracks"][0]["words"] == "as written"
    assert panels["tracks"][1]["spans"][2] == {"t0": 2.0, "t1": 3.0, "label": "#5 Condition", "detail": "until Reached(elbow)",
                                               "kind": "Condition", "color": "", "tone": "danger"}
    # the caller's tabs lead, in the caller's order, each pointing at its definition
    assert [(tab["id"], tab["title"], tab.get("panel")) for tab in payload["tabs"]][:3] == [
        ("panel-now", "Now", 0), ("panel-command-log", "Command log", 1), ("panel-recipe", "Recipe", 2)]
    assert [tab["id"] for tab in payload["tabs"]][3:] == [tab["id"] for tab in analyze_comparison(_comparison())["tabs"]]
    now = panels["tabs"][0]
    assert now["kind"] == "playhead" and now["rows"] == ["shoulder", "elbow"] and len(now["t"]) == len(T)
    servo, mode, position, cap = now["columns"]
    assert servo["cells"] == [{"c": "CAN 11"}, {"c": "CAN 12"}]
    assert mode["cells"][1] == {"k": [[0.0, "moving", ""], [2.0, "holding", "positive"]]}
    # a sample that is not a number is stored as null (the page writes "—"), never as 0
    assert position["cells"][1]["s"][5] == 5.0 and position["cells"][1]["s"][-1] is None
    assert cap["cells"] == [{"c": 12.0}, {"k": [[0.0, 3.0, ""], [2.0, 8.0, ""]]}]
    log = panels["tabs"][1]
    assert log["kinds"] == [["command", "commands"], ["truth", "truth"]] and log["mono"] == [1]
    assert log["rows"][-1]["t"] is None  # math.inf: the run never reached this row
    assert panels["tabs"][2]["open_level"] == 1
    json.dumps(payload["panels"], allow_nan=False)


def test_bad_panels_are_refused_with_the_reason():
    with pytest.raises(ValueError, match="ends .* before it starts"):
        StepSpan(1.0, 0.5, "x")
    with pytest.raises(ValueError, match="not in time order"):
        StepTrack("Recipe", [StepSpan(1.0, 2.0, "b"), StepSpan(0.0, 1.0, "a")])
    with pytest.raises(ValueError, match="unknown tone"):
        TimeRow(0.0, ["x"], tone="red")
    with pytest.raises(ValueError, match="has 1 cells; expected 2"):
        TimeTable("Log", ["a", "b"], [TimeRow(0.0, ["only one"])])
    with pytest.raises(ValueError, match="has 1 cells for 2 rows"):
        PlayheadTable("Now", ["a", "b"], [PlayheadColumn("Servo", ["x"])]).to_payload()
    with pytest.raises(ValueError, match="one per PlayheadTable.t"):
        PlayheadTable("Now", ["a"], [PlayheadColumn("q", [np.zeros(3)])], t=T).to_payload()
    with pytest.raises(ValueError, match="distinct ids"):
        panels_payload([TimeTable("Log", ["a"], []), TimeTable("Log", ["a"], [])])
    with pytest.raises(TypeError, match="a panel is"):
        panels_payload(["Recipe"])


def test_the_report_loads_panels_js_and_writes_the_host_header_first(tmp_path):
    assert ("script", "panels.js") in VIEWER_ASSETS
    names = [name for _, name in VIEWER_ASSETS]
    assert names.index("panels.js") < names.index("plots.js")
    bar = '<nav id="host-site-bar">the site that hosts this report</nav>'
    report = write_comparison_report(_comparison(panels=_panels()), tmp_path, assets=tmp_path / "assets", host_header=bar)
    text = report.read_text()
    assert re.search(r"<body>\s*" + re.escape(bar) + r"\s*<header class='tc'>", text)
    assert '<script src="assets/panels.js"></script>' in text and (tmp_path / "assets" / "panels.js").is_file()
    assert "host-site-bar" not in write_comparison_report(_comparison(), tmp_path / "plain").read_text()


def test_the_rerun_layouts_leave_panel_tabs_out_instead_of_failing():
    pytest.importorskip("rerun")
    from traj_compare.rerun_export import layout_blueprint

    payload = analyze_comparison(_comparison(panels=_panels()))
    assert layout_blueprint("questions", payload, {}) is not None


DRIVER = """
const assert = require('node:assert/strict');
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto('file://' + process.argv[3] + '#t=1.0');
    const time = () => page.evaluate(() => TrajCompare.state.pages[0].transport.eff());
    const go = t => page.evaluate(t => TrajCompare.state.pages[0].transport.setScrub(t), t);
    const text = selector => page.locator(selector).innerText();

    // the page opens on the first panel tab, at the linked time
    assert.equal(await page.getByRole('tab', { selected: true }).innerText(), 'Now');
    assert.ok(Math.abs(await time() - 1.0) < 1e-6);

    // the band: one row per track, the block at the playhead marked and written out whole under it
    assert.equal(await page.locator('[data-tc-step-band] [data-tc-step-track]').count(), 2);
    assert.match(await text('[data-tc-step-now="Recipe"]'), /2 of 3\\s*find_hardstop\\("elbow", -1, 0\\.3, 3\\.0, 1\\.2\\)\\s*expands to Command → Condition → Command/);
    assert.match(await text('[data-tc-step-now="Primitive"]'), /#2 Condition\\s*until InCollision\\(elbow\\)/);
    assert.equal(await page.locator('[data-tc-step-track="Recipe"] .tc-pn-span.now').count(), 1);
    // the playhead line sits a quarter of the way along the rows (t = 1 of 4 s)
    const lane = await page.locator('[data-tc-step-track="Recipe"] .tc-pn-lane').boundingBox();
    const line = await page.locator('[data-tc-step-line]').boundingBox();
    assert.ok(Math.abs((line.x + line.width / 2) - (lane.x + lane.width * 0.25)) < 2, 'the line is at t = 1 s');

    // the Now table reads its cells at the playhead: a constant, a sample, a change
    const cell = (row, column) => text(`[data-tc-playhead-table] [data-tc-row="${row}"] [data-tc-cell="${column}"]`);
    assert.equal(await cell('elbow', 'Servo'), 'CAN 12');
    assert.equal(await cell('elbow', 'Mode'), 'moving');
    assert.equal(await cell('elbow', 'position'), '+10.00');
    assert.equal(await cell('shoulder', 'position'), '0.00');
    assert.equal(await cell('elbow', 'effort cap'), '3.0');
    await go(2.5);
    assert.equal(await cell('elbow', 'Mode'), 'holding');
    assert.equal(await cell('elbow', 'position'), '—');   // nothing sent: never drawn as 0
    assert.equal(await cell('elbow', 'effort cap'), '8.0');
    assert.match(await text('[data-tc-step-now="Recipe"]'), /3 of 3\\s*move_to/);
    await go(3.5);
    // after the last block: one line says so, instead of one per track
    assert.equal(await page.locator('[data-tc-step-now="Recipe"]').isHidden(), true);
    assert.match(await text('[data-tc-step-idle]'), /nothing running at this time/);
    await go(2.5);
    assert.equal(await page.locator('[data-tc-step-idle]').isHidden(), true);

    // a click on a block goes to its start
    await page.locator('[data-tc-step-track="Recipe"] [data-tc-step^="move_to"]').click();
    assert.ok(Math.abs(await time() - 2.0) < 1e-6);

    // the log: the newest row at or before the playhead is marked, later rows are dim, a click goes to its time
    await page.getByRole('tab', { name: 'Command log' }).click();
    const rows = page.locator('[data-tc-time-table="command-log"] tbody tr');
    assert.equal(await rows.count(), 5);
    assert.deepEqual(await rows.evaluateAll(list => list.map(row => row.className.replace(/level-0|tone-muted/g, '').trim())),
                     ['', '', '', 'now', 'later']);
    assert.equal(await rows.nth(4).locator('td').first().innerText(), '—');
    await rows.nth(0).click();
    assert.ok(Math.abs(await time() - 0.0) < 1e-6);
    assert.deepEqual(await rows.evaluateAll(list => list.map(row => row.classList.contains('later'))),
                     [false, false, true, true, true]);
    await rows.nth(4).click();   // a row that never happened goes nowhere
    assert.ok(Math.abs(await time() - 0.0) < 1e-6);
    await page.locator('[data-tc-kind="truth"]').click();
    assert.equal(await rows.nth(2).isHidden(), true);
    await page.locator('[data-tc-kind="truth"]').click();
    assert.equal(await rows.nth(2).isHidden(), false);

    // the outline: primitives start folded under their call, and open with its twist
    await page.getByRole('tab', { name: 'Recipe' }).click();
    const lines = page.locator('[data-tc-time-table="recipe"] tbody tr');
    assert.deepEqual(await lines.evaluateAll(list => list.map(row => row.hidden)), [false, false, true, true, false, false, true]);
    await lines.nth(1).locator('.tc-pn-twist').click();
    assert.deepEqual(await lines.evaluateAll(list => list.map(row => row.hidden)), [false, false, false, false, false, false, true]);
    await go(1.0);
    assert.deepEqual(await lines.evaluateAll(list => list.map(row => row.classList.contains('now'))),
                     [true, true, false, true, false, false, false]);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                    reason="needs Node Playwright and Chrome")
def test_the_panels_follow_the_transport_in_the_real_page(tmp_path):
    report = write_comparison_report(_comparison(panels=_panels()), tmp_path)
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER)
    result = subprocess.run(["node", driver, PLAYWRIGHT, report, CHROME], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr


# ── round 3 (2026-11-28): a tab of several panels, and the paired sent / measured table with its variants ────────────


def _paired():
    sent = np.stack([np.zeros(len(T)), np.where(T < 2.0, T * 10.0, np.nan)], axis=1)
    measured = sent - np.array([0.0, 1.5])
    return PlayheadTable("Sent to servos", ["shoulder", "elbow"], [
        PlayheadColumn("Servo", ["CAN 11", "CAN 12"]),
        PlayheadColumn("position", [sent[:, 0], sent[:, 1]], group="Sent", unit="°", signed=True, quantity="position", role="sent"),
        PlayheadColumn("effort cap", [12.0, Changes([(0.0, 3.0), (2.0, 8.0)])], group="Sent", unit="N·m", decimals=1),
        PlayheadColumn("q", [measured[:, 0], measured[:, 1]], group="Measured", unit="°", signed=True, quantity="position",
                       role="measured"),
    ], t=T, id="sent")  # fmt: skip


def test_a_panel_tab_holds_a_band_and_tables_and_columns_carry_their_quantity():
    recipe, primitives, now, log, outline = _panels()
    tab = PanelTab("Recipe", [recipe, primitives, outline], heading="Across, then down")
    payload = analyze_comparison(_comparison(panels=[_paired(), tab, log]))
    assert "tracks" in payload["panels"] and payload["panels"]["tracks"] == []  # no band above the stage any more
    assert [(entry["id"], entry.get("panel")) for entry in payload["tabs"]][:3] == [
        ("panel-sent", 0), ("panel-recipe", 1), ("panel-command-log", 2)]
    group = payload["panels"]["tabs"][1]
    assert group["kind"] == "group" and group["heading"] == "Across, then down"
    assert [part["kind"] for part in group["parts"]] == ["band", "times"]
    assert [track["title"] for track in group["parts"][0]["tracks"]] == ["Recipe", "Primitive"]  # neighbours share a band
    columns = payload["panels"]["tabs"][0]["columns"]
    assert [(column["quantity"], column["role"]) for column in columns] == [
        ("", ""), ("position", "sent"), ("", ""), ("position", "measured")]
    with pytest.raises(ValueError, match="quantity and role go together"):
        PlayheadColumn("q", [1.0], role="measured")
    with pytest.raises(ValueError, match="measured without a sent"):
        PlayheadTable("x", ["a"], [PlayheadColumn("q", [1.0], quantity="position", role="measured")]).to_payload()
    with pytest.raises(ValueError, match="holds no panel"):
        PanelTab("Recipe", [])
    with pytest.raises(TypeError, match="holds StepTracks"):
        PanelTab("Recipe", [tab])


PAIRED_DRIVER = r"""
const assert = require('node:assert/strict');
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto('file://' + process.argv[3] + '#t=1.0');
    const go = t => page.evaluate(t => TrajCompare.state.pages[0].transport.setScrub(t), t);
    const table = page.locator('[data-tc-playhead-table="sent"]');
    const cell = (row, key) => table.locator(`[data-tc-row="${row}"] [data-tc-cell="${key}"]`).innerText();
    const heads = () => table.locator('thead tr').last().locator('th').allInnerTexts();
    const press = key => table.locator(`[data-tc-toggle="${key}"]`).click();

    // no band above the stage: it is inside the Recipe tab
    assert.equal(await page.locator('[data-tc-step-band]').count(), 0);

    // variant 1 as it starts: each quantity's sent, measured and error side by side
    assert.equal(await table.getAttribute('data-tc-variant'), 'table');
    assert.deepEqual(await heads(), ['Joint', 'Servo', 'sent', 'measured', 'Δ', 'effort cap [N·m]']);
    assert.equal(await cell('elbow', 'position:sent'), '+10.00');
    assert.equal(await cell('elbow', 'position:measured'), '+8.50');
    assert.equal(await cell('elbow', 'position:error'), '+1.50');
    await go(2.5);
    assert.equal(await cell('elbow', 'position:sent'), '—');
    assert.equal(await cell('elbow', 'position:error'), '—');     // nothing sent: no error, never 0
    assert.equal(await cell('elbow', 'effort cap'), '8.0');
    await go(1.0);

    // the three switches
    await press('error');
    assert.deepEqual(await heads(), ['Joint', 'Servo', 'sent', 'measured', 'effort cap [N·m]']);
    await press('measured');
    assert.deepEqual(await heads(), ['Joint', 'Servo', 'sent', 'effort cap [N·m]']);
    await press('measured'); await press('error');
    await press('layout');   // split by source: every sent column, then every measured one, then the errors
    assert.deepEqual(await heads(), ['Joint', 'Servo', 'position [°]', 'effort cap [N·m]', 'q [°]', 'position [°]']);
    assert.equal(await cell('elbow', 'position:error'), '+1.50');
    await press('layout');

    // the drop-down: five variants, each showing the same three numbers; the pick is remembered
    const pick = page.locator('[data-tc-variant-pick] select');
    assert.equal(await pick.locator('option').count(), 5);
    for (const id of ['stacked', 'bars']) {
      await pick.selectOption(id);
      assert.equal(await table.getAttribute('data-tc-variant'), id);
      const pair = table.locator('[data-tc-row="elbow"] [data-tc-cell="position"]');
      assert.equal(await pair.locator('[data-tc-part="sent"]').innerText(), '+10.00');
      assert.equal(await pair.locator('[data-tc-part="measured"]').innerText(), '+8.50');
      assert.match(await pair.locator('[data-tc-part="error"]').innerText(), /Δ\s*\+1\.50/);
      assert.equal(await table.locator('[data-tc-toggle="layout"]').isDisabled(), true);
    }
    // bars: the sent mark sits at 10 of this row's 0 … 19 range (measured reaches -1.5 … 17.5)
    const track = await table.locator('[data-tc-row="elbow"] .tc-pn-bar').boundingBox();
    const mark = await table.locator('[data-tc-row="elbow"] .tc-pn-mark.sent').boundingBox();
    assert.ok(Math.abs((mark.x + mark.width / 2 - track.x) / track.width - (10 + 1.5) / (19 + 1.5)) < 0.02);
    await pick.selectOption('cards');
    assert.equal(await table.locator('.tc-pn-card').count(), 2);
    assert.equal(await cell('elbow', 'position:error'), '+1.50');
    assert.equal(await cell('elbow', 'Servo'), 'CAN 12');
    await pick.selectOption('across');
    assert.deepEqual(await table.locator('thead th').allInnerTexts(), ['', 'shoulder', 'elbow']);
    assert.equal(await table.locator('tbody tr').count(), 5);
    assert.equal(await table.locator('tbody tr').nth(3).locator('[data-tc-row="elbow"]').innerText(), '+1.50');
    await page.reload();
    assert.equal(await page.locator('[data-tc-playhead-table="sent"]').getAttribute('data-tc-variant'), 'across');

    // the Recipe tab holds the band (laid out when the tab opens) over the outline
    await page.getByRole('tab', { name: 'Recipe' }).click();
    const band = page.locator('[data-tc-panel="panel-recipe"] [data-tc-step-band]');
    assert.equal(await band.locator('[data-tc-step-track]').count(), 2);
    const lane = await band.locator('[data-tc-step-track="Recipe"] .tc-pn-lane').boundingBox();
    const line = await band.locator('[data-tc-step-line]').boundingBox();
    assert.ok(lane.width > 300 && Math.abs((line.x + line.width / 2) - (lane.x + lane.width * 0.25)) < 2);
    assert.equal(await page.locator('[data-tc-panel="panel-recipe"] [data-tc-time-table="recipe"] tbody tr').count(), 7);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                    reason="needs Node Playwright and Chrome")
def test_the_paired_table_its_switches_and_variants_in_the_real_page(tmp_path):
    recipe, primitives, now, log, outline = _panels()
    report = write_comparison_report(
        _comparison(panels=[_paired(), PanelTab("Recipe", [recipe, primitives, outline]), log]), tmp_path)
    driver = tmp_path / "driver.cjs"
    driver.write_text(PAIRED_DRIVER)
    result = subprocess.run(["node", driver, PLAYWRIGHT, report, CHROME], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
