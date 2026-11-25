"""Grasp coverage, our own page: data-ui's <data-workbench> over a set of grasps (acceptance, written before the code,
2026-11-24). Contract: docs/GRASP_COVERAGE.md "Our page"; data-ui docs/CONTRACT.md §52, §53, §32.

The atomic unit is a grasp: the rail filters grasps and every coverage figure re-sums the kept grasps' part rows. The
oracle is the payload itself: every grasp's parts, added up per figure, give back the payload's counts exactly. Then
data-ui's own checker reads the .base, and headless Chrome ticks "failed" and reads each figure's hook (data-ui §53:
`el.coverage.rows[].total`) to prove the figures recount.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from grasp_fixture import AREA, PLANNER_RANGE, WIDTH_RANGE, made_up

from traj_compare.grasp_coverage import analyze_grasps
from traj_compare.grasp_coverage.workbench import grasp_workbench_rows, write_grasp_workbench

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_data_ui = pytest.mark.skipif(not ((DATA_UI / "bin" / "data-ui.mjs").is_file() and shutil.which("node")),
                                   reason="needs node and the data-ui repo")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")
                                        and (DATA_UI / "bin" / "data-ui.mjs").is_file()),
                                   reason="needs Node Playwright, Chrome and the data-ui repo")
PAGES = ["Overview", "Grippers", "Position", "Gripper", "Orientation", "Objects", "Over time", "Grasps"]  # round 2 (2026-11-24) added Grippers and Over time


@pytest.fixture(scope="module")
def inputs():
    grasps, outcomes, tags, _ = made_up()
    coverage = analyze_grasps(grasps, outcomes=outcomes, width_range=WIDTH_RANGE, planner_width_range=PLANNER_RANGE,
                              tags=tags, area=AREA, title="Made-up picks")
    return coverage, grasps, outcomes, tags


@pytest.fixture(scope="module")
def rows(inputs):
    coverage, grasps, _, _ = inputs
    return grasp_workbench_rows(coverage, grasps)


def dense(part: dict) -> np.ndarray:
    n = part["nu"] * part["nv"] if "nu" in part else part["nx"] * part["ny"]
    out = np.zeros(n, int)
    out[np.asarray(part["at"], int)] += np.asarray(part["samples"], int)
    return out


def summed(parts: list[dict], kind: str, **match) -> np.ndarray:
    chosen = [p for p in parts if p["kind"] == kind and all(p.get(k) == v for k, v in match.items())]
    assert chosen, (kind, match)
    if "counts" in chosen[0]:
        return np.sum([p["counts"] for p in chosen], axis=0)
    return np.sum([dense(p) for p in chosen], axis=0)


# ── the rows add back to the payload ────────────────────────────────────────


def test_one_grasp_row_each_in_display_units(inputs, rows):
    coverage, grasps, outcomes, tags = inputs
    grasp_rows, _ = rows
    assert [row["name"] for row in grasp_rows] == list(grasps)
    assert len({row["id"] for row in grasp_rows}) == len(grasps)
    first = grasp_rows[0]
    name = first["name"]
    assert first["object"] == grasps[name].object_id and first["outcome"] == (outcomes[0] or "unknown")
    assert first["run"] == tags[name]["run"] and first["day"] == tags[name]["day"]
    assert first["width_mm"] == pytest.approx(grasps[name].width * 1000, abs=0.01)
    assert first["x_mm"] == pytest.approx(grasps[name].pose.position.x * 1000, abs=0.01)
    payload_row = coverage.payload["grasps"][0]
    assert first["tilt_deg"] == pytest.approx(np.degrees(payload_row["tilt"]), abs=0.01)
    assert first["roll_deg"] == pytest.approx(np.degrees(payload_row["roll"]), abs=0.01)
    # the arrow's tail: 50 mm back along the approach, so the arrow points the way the gripper moves
    approach = np.asarray(payload_row["approach"])
    assert [first["from_x_mm"], first["from_y_mm"], first["from_z_mm"]] == pytest.approx(
        list(np.asarray(payload_row["position"]) * 1000 - 50 * approach), abs=0.01)


def test_projections_add_back(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    for face in ("xy", "xz", "yz"):
        assert summed(parts, "projection", grid=face).tolist() == payload["position"]["projections"][face]["samples"]


def test_histograms_add_back_with_their_groups(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    shown = payload["orientation"]["roll_shown"]
    for kind, block in (("width", payload["width"]), ("pre_grasp_width", payload["pre_grasp_width"]),
                        ("tilt", payload["orientation"]["tilt"]), ("roll", payload["orientation"][shown]),
                        ("score", payload["score"])):
        assert summed(parts, kind).tolist() == block["counts"], kind
        for group, counts in block["groups"].items():
            mine = [p for p in parts if p["kind"] == kind and p["groups"] == [group]]
            total = np.sum([p["group_counts"][0] for p in mine], axis=0) if mine else np.zeros(len(counts), int)
            assert total.tolist() == counts, (kind, group)


def test_direction_grids_add_back(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    orientation = payload["orientation"]
    # the pointing disk is data-ui's coverage-polar: x = azimuth, y = tilt (the payload's grid is tilt-major)
    tilts, azimuths = orientation["tilt_azimuth"]["shape"]
    pointing = np.asarray(orientation["tilt_azimuth"]["counts"]).reshape(tilts, azimuths).T.ravel()
    assert summed(parts, "pointing").tolist() == pointing.tolist()
    sphere = np.asarray(orientation["sphere"]["counts"]).reshape(12, 24).T.ravel()  # x = sector, y = ring (the z band)
    assert summed(parts, "sphere").tolist() == sphere.tolist()
    t, r = orientation["tilt_roll"]["shape"]
    assert summed(parts, "tilt_roll").tolist() == np.asarray(orientation["tilt_roll"]["counts"]).reshape(t, r).T.ravel().tolist()
    assert summed(parts, "width_tilt").tolist() == payload["width_tilt"]["counts"]


def test_a_part_is_sparse_and_names_its_grasp(rows):
    grasp_rows, parts = rows
    ids = {row["id"] for row in grasp_rows}
    assert {part["grasp"] for part in parts} == ids
    grids = [p for p in parts if "at" in p]
    assert grids and all(len(p["at"]) == len(p["samples"]) == 1 for p in grids)  # one grasp = one cell


def test_the_grasps_must_be_the_payloads(inputs):
    coverage, grasps, _, _ = inputs
    with pytest.raises(ValueError, match="grasps"):
        grasp_workbench_rows(coverage, list(grasps.values())[:-1])


# ── the files ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def site(inputs, tmp_path_factory):
    if not (DATA_UI / "bin" / "data-ui.mjs").is_file():
        pytest.skip("needs the data-ui repo")
    coverage, grasps, _, _ = inputs
    out = tmp_path_factory.mktemp("grasp_workbench")
    write_grasp_workbench(coverage, grasps, out, dataset_label="Made-up picks")
    return out


@needs_data_ui
def test_the_written_base_passes_data_ui_check(site):
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(site / "grasp_coverage.base"),
                             "--json"], capture_output=True, text=True, timeout=120)
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["errors"] == 0 and report["warnings"] == 0, report["problems"]


@needs_data_ui
def test_the_base_has_the_rail_pages_gear_and_outcome_colours(site):
    yaml = pytest.importorskip("yaml")
    base = yaml.safe_load((site / "grasp_coverage.base").read_text("utf-8"))
    assert [f.get("property") for f in base["facets"][:4]] == ["object", "outcome", "run", "day"]
    assert base["facets"][1]["order"] == ["picked", "failed", "hovered", "refused", "unknown"]
    assert [page["name"] for page in base["pages"]] == PAGES
    assert base["noun"] == ["grasp", "grasps"]
    assert base["settings"] == ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"]
    colours = base["properties"]["outcome"]["colors"]
    assert set(colours) == {"picked", "failed", "hovered", "refused", "unknown"}
    assert len(set(map(str, colours.values()))) == 5
    assert base["style"]["families"]["property"] == "outcome"
    sums = {v["name"]: v.get("coverage", {}).get("sum") for v in base["views"] if v["type"].startswith("coverage-")}
    assert sums and set(sums.values()) == {"grid"}, sums
    assert any(v["type"] == "scene3d" for v in base["views"])


@needs_data_ui
def test_index_and_embed_are_one_workbench_tag(site):
    index = (site / "index.html").read_text("utf-8")
    embed = (site / "embed.html").read_text("utf-8")
    assert index.count("<data-workbench") == 1 and 'src="grasp_coverage.base"' in index
    assert embed.count("<data-workbench") == 1 and "no-url" in embed and "1000px" in embed
    assert (site / "vendor" / "data-ui" / "data-ui.js").is_file()
    assert json.loads((site / "grasps.json").read_text("utf-8"))["rows"]
    assert json.loads((site / "parts.json").read_text("utf-8"))["rows"]


# ── the page in a browser ───────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const out = { errors: [], panels: {} };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const WB = 'data-workbench';
  async function open(url) {
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url);
    await page.waitForSelector(WB + '[data-ready]', { timeout: 30000 });
    await page.waitForTimeout(800);
    return page;
  }
  const count = (page) => page.evaluate(() => document.querySelector('data-workbench data-count').textContent.trim());
  // every shown panel: its title and each coverage figure's total (data-ui §53's hook) or that it drew a canvas
  const panels = (page) => page.evaluate(() => {
    const shown = [...document.querySelectorAll('data-workbench [tab]')].find((p) => !p.hidden);
    return [...shown.querySelectorAll('.dd-panel')].map((sec) => {
      const hooks = [...sec.querySelectorAll('*')].filter((e) => e.coverage).map((e) => ({
        type: e.coverage.type, total: e.coverage.rows.reduce((a, r) => a + r.total, 0), problems: e.coverage.problems.length,
        rows: Object.fromEntries(e.coverage.rows.map((r) => [r.id, r.total])) }));
      const canvases = [...sec.querySelectorAll('canvas')].filter((c) => c.width > 0 && c.height > 0).length;
      const marks = sec.querySelectorAll('svg path, svg circle, svg rect, svg .mark-symbol path').length;
      const failed = /could not be drawn/i.test(sec.textContent);
      // a Vega chart's data marks (not its axes, legends or grid): found on the real repicks, round 2 — two charts drew
      // axes and no line, because data-ui renames an encoding's field and a transform's output kept its spaces
      // counted: items placed at a finite position (a line point with no y is an item too), never a rule or a label
      // (a limit line draws whatever the data do); a panel that is text alone (no outcomes in the set) counts its text
      let data = null;
      const host = [...sec.querySelectorAll('*')].find((e) => e.vegaView);
      if (host) {
        let placed = 0, texts = 0, other = 0;
        const fin = Number.isFinite;
        const walk = (item) => { if (!item) return;
          const t = item.marktype, name = item.name || '';
          if (t && t !== 'group' && /(^|_)marks$/.test(name) && !/legend|axis|ghost/.test(name)) {
            const items = item.items || [];
            if (t === 'text') texts += items.filter((i) => i.text).length;
            else if (t !== 'rule') {
              other += 1;
              placed += items.filter((i) => (t === 'arc' ? fin(i.outerRadius) && i.outerRadius > 0
                                                        : (fin(i.y) || fin(i.y2) || fin(i.height)) && (fin(i.x) || fin(i.x2) || fin(i.width)))).length;
            }
          }
          for (const i of item.items || []) walk(i); };
        walk(host.vegaView.scenegraph().root);
        data = other ? placed : texts;
      }
      return { label: sec.getAttribute('aria-label'), hooks, canvases, marks, failed, data };
    });
  });
  let page = await open(spec.index);
  out.first = await page.evaluate(() => { const g = document.querySelector('data-workbench data-facets section.df-group'); return g && g.dataset.p; });
  out.count0 = await count(page);
  out.tabs = await page.evaluate(() => [...document.querySelectorAll('data-workbench data-tabs [role=tab]')].map((t) => t.dataset.tab));
  for (const tab of out.tabs) {
    await page.click(`${WB} data-tabs [role=tab][data-tab="${tab}"]`); await page.waitForTimeout(900);
    out.panels['all:' + tab] = await panels(page);
  }
  await page.click(`${WB} data-tabs [role=tab][data-tab="Overview"]`); await page.waitForTimeout(400);
  await page.click(`${WB} data-facets section.df-group[data-p="outcome"] input[data-value="failed"]`);
  await page.waitForTimeout(700);
  out.count1 = await count(page);
  out.kept = {};
  for (const tab of out.tabs) {
    await page.click(`${WB} data-tabs [role=tab][data-tab="${tab}"]`); await page.waitForTimeout(900);
    out.kept[tab] = await count(page);
    out.panels['failed:' + tab] = await panels(page);
  }
  await page.close();
  page = await open(spec.embed);
  out.embed = await page.evaluate(() => {
    const slot = document.querySelector('#host-slot').getBoundingClientRect();
    const wb = document.querySelector('#host-slot > data-workbench').getBoundingClientRect();
    return { inSlot: wb.left >= slot.left - 1 && wb.top >= slot.top - 1 && wb.right <= slot.right + 1 && wb.bottom <= slot.bottom + 1,
             scrollX: document.documentElement.scrollWidth - window.innerWidth };
  });
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def browsed(site) -> dict:
    """Serve the site with traj_compare.serve on a free port (that pid stopped after), drive it."""
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(site), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        url = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/")
        (site / "spec.json").write_text(json.dumps({"index": f"{url}/index.html", "embed": f"{url}/embed.html"}))
        (site / "driver.js").write_text(DRIVER)
        result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                                capture_output=True, text=True, timeout=300)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def panel(browsed: dict, key: str, label: str) -> dict:
    found = [p for p in browsed["panels"][key] if p["label"] == label]
    assert found, (key, label, [p["label"] for p in browsed["panels"][key]])
    return found[0]


@needs_browser
def test_the_page_draws_with_no_errors_object_first(browsed, inputs):
    total = len(inputs[1])
    assert browsed["errors"] == []
    assert browsed["first"] == "object"
    assert browsed["count0"] == f"{total} of {total} grasps"
    assert browsed["tabs"] == PAGES


@needs_browser
def test_every_panel_draws_something(browsed):
    for tab in PAGES:
        for found in browsed["panels"][f"all:{tab}"]:
            assert found["canvases"] or found["marks"] or tab == "Grasps", (tab, found)
            # found on the real repicks (round 2): a chart that throws still leaves an svg, so say it out loud
            assert not found["failed"], (tab, found["label"], "data-ui says the chart could not be drawn")
            assert found["data"] is None or found["data"] > 0, (tab, found["label"], "a chart with axes and no data marks")
            assert all(hook["problems"] == 0 for hook in found["hooks"]), (tab, found)


@needs_browser
def test_ticking_failed_recounts_every_tab_and_every_figure(browsed, inputs):
    coverage, grasps, outcomes, _ = inputs
    payload = coverage.payload
    total, failed = len(grasps), outcomes.count("failed")
    assert browsed["count1"] == f"{failed} of {total} grasps"
    assert browsed["kept"] == {tab: f"{failed} of {total} grasps" for tab in PAGES}
    low, high, _ = payload["width"]["edges"]
    failed_widths = [g.width for g, o in zip(grasps.values(), outcomes, strict=True) if o == "failed"]
    in_edges = sum(low <= w <= high for w in failed_widths)
    # the stock strips panel: its width strip is the width parts of the kept grasps, summed (data-ui §53's sum:<grid>)
    width = panel(browsed, "failed:Gripper", "Every histogram against its range")
    assert [hook["rows"]["sum:width"] for hook in width["hooks"]] == [in_edges]
    every = panel(browsed, "all:Gripper", "Every histogram against its range")
    assert [hook["rows"]["sum:width"] for hook in every["hooks"]] == [sum(payload["width"]["counts"])]
    faces = panel(browsed, "failed:Position", "The grasps from three sides")
    assert sum(hook["total"] for hook in faces["hooks"]) == 3 * failed
    pointing = panel(browsed, "failed:Orientation", "Which way it approaches")
    assert [hook["total"] for hook in pointing["hooks"]] == [failed]


@needs_browser
def test_embedded_it_stays_in_the_hosts_slot(browsed):
    assert browsed["embed"]["inSlot"] and browsed["embed"]["scrollX"] <= 1


# ── added 2026-11-24 (round 2: thin grippers, heatmaps, more kinds of view), written before the code ─────────────────

ROUND_2_VIEWS = {"Thin grippers in 3-D", "Thin grippers from above", "Thin grippers from the side",
                 "Grasp density from above", "Picked share per spot", "Density per outcome", "Width per object",
                 "Width × tilt per object", "Where each object was grasped", "Roll rose", "Approach directions in 3-D",
                 "Grasps per day", "Picked share per day", "Coverage growth", "Grasps per day per object",
                 "Every grasp as a line"}
PAGES_2 = ["Overview", "Grippers", "Position", "Gripper", "Orientation", "Objects", "Over time", "Grasps"]


def test_glyph_rows_are_one_polyline_per_grasp_linked_to_it(inputs, tmp_path):
    from traj_compare.grasp_coverage.analysis import gripper_polylines

    coverage, grasps, _, _ = inputs
    write_grasp_workbench(coverage, grasps, tmp_path, kit="../kit")
    glyphs = json.loads((tmp_path / "glyphs.json").read_text("utf-8"))["rows"]
    rows = json.loads((tmp_path / "grasps.json").read_text("utf-8"))["rows"]
    assert len(glyphs) == 7 * len(rows)
    # the path starts at the wrist end (the workbench's GLYPH_PATH): scene3d's per-path "now" ball lands on the wrist
    lines = gripper_polylines(coverage.payload["grasps"])[:, [3, 2, 1, 0, 1, 5, 6]] * 1000.0
    first = [g for g in glyphs if g["grasp"] == rows[0]["id"]]
    assert [g["t"] for g in first] == list(range(7))  # the path's order
    assert np.allclose([[g["x_mm"], g["y_mm"], g["z_mm"]] for g in first], lines[0], atol=0.01)
    assert {g["outcome"] for g in first} == {rows[0]["outcome"]}


def test_round_two_views_and_tabs_are_in_the_base(site):
    yaml = pytest.importorskip("yaml")
    base = yaml.safe_load((site / "grasp_coverage.base").read_text("utf-8"))
    names = {view["name"] for view in base["views"]}
    assert ROUND_2_VIEWS <= names, ROUND_2_VIEWS - names
    assert [page["name"] for page in base["pages"]] == PAGES_2
    links = {(link["from"], link["to"]) for link in base["links"]}
    assert ("grasps.id", "glyphs.grasp") in links
    shown = {panel["view"] for page in base["pages"] for panel in page["layout"]["panels"]}
    assert ROUND_2_VIEWS <= shown, ROUND_2_VIEWS - shown
