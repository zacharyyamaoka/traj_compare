"""The record-coverage workbench: data-ui's <data-workbench> over a list of records (acceptance, written before the code,
2026-11-24). Contract: docs/RECORD_COVERAGE.md "The workbench"; data-ui docs/CONTRACT.md §52 and §53.

The oracle is independent of the module: every figure's counts for the records the rail keeps are recounted here with
numpy (np.histogram / np.histogram2d on the payload's own edges) and collections.Counter, and compared with the sum of
the part rows of the cohorts the rail keeps. Then data-ui's own checker reads the .base, and headless Chrome drives it.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from traj_compare.record_coverage import analyze, workbench_rows, write_workbench

sys.path.insert(0, str(Path(__file__).parent))
from test_record_coverage import made_up  # noqa: E402

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_data_ui = pytest.mark.skipif(not ((DATA_UI / "bin" / "data-ui.mjs").is_file() and shutil.which("node")),
                                   reason="needs node and the data-ui repo")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")
                                        and (DATA_UI / "bin" / "data-ui.mjs").is_file()),
                                   reason="needs Node Playwright, Chrome and the data-ui repo")
RANGES = {"draws": (0, 9), "tcp[0]": (-0.4, 0.4), "tcp[1]": (0.0, 0.6), "tcp[2]": (-0.2, 0.2)}
PAIRS = [("angle_rad", "grip.width_mm"), ("tcp[0]", "tcp[1]")]
PAGES = ["Overview", "Numbers", "Classes", "Pairs", "Missing", "Growth", "Support", "Records"]


@pytest.fixture(scope="module")
def picks():
    return made_up()


@pytest.fixture(scope="module")
def coverage(picks):
    return analyze(picks, ranges=RANGES, pairs=PAIRS, group_by="item", split="split", title="Made-up picks")


@pytest.fixture(scope="module")
def rows(coverage, picks):
    return workbench_rows(coverage, picks)


@pytest.fixture(scope="module")
def site(coverage, picks, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("record-workbench")
    write_workbench(coverage, picks, out)
    return out


def value_of(pick, name):
    """The test's own reading of a flattened field, straight off the dataclass."""
    if name == "angle_rad":
        return pick.angle_rad
    if name.startswith("grip."):
        return getattr(pick.grip, name.split(".", 1)[1])
    if name.startswith("tcp["):
        return pick.tcp[int(name[4])]
    if name == "len(path)":
        return len(pick.path)
    if name == "n_path":
        return pick.n_path
    if name == "bin":
        return pick.bin.value
    if name == "ok":
        return str(pick.ok)
    return getattr(pick, name)


def present(values):
    return np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))], float)


def kept_by(records_rows, picks, picked: dict) -> list:
    """The picks whose rail values are all in `picked` ({property key: {levels}})."""
    keep = []
    for row, pick in zip(records_rows, picks, strict=True):
        if all(row.get(key) in levels for key, levels in picked.items()):
            keep.append(pick)
    return keep


def summed(parts, cohorts: set, kind: str, grid: str, key: str, size: int) -> np.ndarray:
    total = np.zeros(size, int)
    for part in parts:
        if part["kind"] == kind and part["grid"] == grid and part["cohort"] in cohorts:
            values = part[key]
            if "at" in part:
                for at, value in zip(part["at"], values, strict=True):
                    total[at] += value
            else:
                total += np.asarray(values, int)
    return total


def picks_to_check(rows) -> list[dict]:
    record_rows, _ = rows
    rail = {"item": ["vial", "pill", "cap", "lid"], "split": ["dev", "holdout"]}
    picked = [{"item": {level}} for level in rail["item"]] + [{"split": {"holdout"}}]
    picked += [{"item": {a}, "split": {b}} for a, b in itertools.product(["vial", "cap"], ["dev", "holdout"])]
    picked.append({"item": {"vial", "lid"}})
    return picked


# ── the rows ────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_one_record_row_each_with_its_fields_numbers_and_cohort(rows, picks, coverage):
    record_rows, _ = rows
    assert len(record_rows) == len(picks)
    first = record_rows[0]
    assert first["id"] == "pick-000" and first["item"] == picks[0].item and first["split"] == picks[0].split
    assert first["grip_width_mm"] == pytest.approx(picks[0].grip.width_mm)
    assert first["tcp_0"] == pytest.approx(picks[0].tcp[0])
    for row, source in zip(record_rows, coverage.payload["records"], strict=True):
        assert (row["missing"], row["new_cells"], row["unique_cells"]) == \
               (source["missing"], source["new_cells"], source["unique_cells"])


def test_records_that_share_every_rail_value_share_a_cohort(rows):
    record_rows, _ = rows
    rail_keys = ["item", "split", "bin", "ok"]
    by_tuple: dict = {}
    for row in record_rows:
        by_tuple.setdefault(tuple(row[k] for k in rail_keys), set()).add(row["cohort"])
    assert all(len(cohorts) == 1 for cohorts in by_tuple.values())
    assert len({row["cohort"] for row in record_rows}) == len(by_tuple)


def test_every_part_names_a_cohort_and_adds_back_to_the_payload(rows, coverage):
    record_rows, parts = rows
    cohorts = {row["cohort"] for row in record_rows}
    assert {part["cohort"] for part in parts} <= cohorts
    payload = coverage.payload
    for name, hist in payload["hist"].items():
        grid = [p for p in parts if p["kind"] == "hist" and p["field"] == name][0]["grid"]
        assert summed(parts, cohorts, "hist", grid, "counts", hist["edges"][2]).tolist() == hist["counts"], name
    for pair in payload["pairs"]:
        grid = [p for p in parts if p["kind"] == "pair" and p["title"] == f"{pair['x']} × {pair['y']}"][0]["grid"]
        size = pair["shape"][0] * pair["shape"][1]
        assert summed(parts, cohorts, "pair", grid, "samples", size).tolist() == pair["samples"]
    for field in payload["fields"]:
        missing = sum(p["missing"] for p in parts if p["kind"] == "missing" and p["field"] == field["name"])
        assert missing == field["missing"], field["name"]


def test_the_parts_of_the_cohorts_a_pick_keeps_recount_every_figure_exactly(rows, picks, coverage):
    record_rows, parts = rows
    payload = coverage.payload
    for picked in picks_to_check(rows):
        kept = kept_by(record_rows, picks, picked)
        cohorts = {row["cohort"] for row in record_rows if all(row.get(k) in v for k, v in picked.items())}
        assert kept, picked
        for name, hist in payload["hist"].items():
            grid = [p for p in parts if p["kind"] == "hist" and p["field"] == name][0]["grid"]
            low, high, n = hist["edges"]
            oracle, _ = np.histogram(present([value_of(p, name) for p in kept]), bins=np.linspace(low, high, n + 1))
            assert summed(parts, cohorts, "hist", grid, "counts", n).tolist() == oracle.tolist(), (picked, name)
        for pair in payload["pairs"]:
            grid = [p for p in parts if p["kind"] == "pair" and p["title"] == f"{pair['x']} × {pair['y']}"][0]["grid"]
            (xl, xh, nx), (yl, yh, ny) = pair["x_edges"], pair["y_edges"]
            xs = np.asarray([value_of(p, pair["x"]) for p in kept], float)
            ys = np.asarray([value_of(p, pair["y"]) for p in kept], float)
            oracle, _, _ = np.histogram2d(xs, ys, bins=[np.linspace(xl, xh, nx + 1), np.linspace(yl, yh, ny + 1)])
            got = summed(parts, cohorts, "pair", grid, "samples", nx * ny)
            assert got.tolist() == oracle.astype(int).ravel().tolist(), (picked, pair["x"], pair["y"])
        for name in ("speed",):
            missing = sum(p["missing"] for p in parts if p["kind"] == "missing" and p["field"] == name
                          and p["cohort"] in cohorts)
            assert missing == sum(1 for p in kept if p.speed is None or math.isnan(p.speed)), picked


def test_a_hist_part_stacks_by_the_group_and_a_big_grid_is_sparse(rows):
    _, parts = rows
    hist = next(p for p in parts if p["kind"] == "hist")
    assert hist["groups"] and len(hist["groups"]) == len(hist["group_counts"])
    assert np.sum(hist["group_counts"], axis=0).tolist() == hist["counts"]
    pair = next(p for p in parts if p["kind"] == "pair")
    assert "at" in pair and len(pair["at"]) == len(pair["samples"]) and all(s > 0 for s in pair["samples"])


def test_the_records_must_be_the_payloads(coverage, picks):
    with pytest.raises(ValueError, match="the records analyze"):
        workbench_rows(coverage, picks[:-1])


# ── the .base ───────────────────────────────────────────────────────────────────────────────────────────────────────


def base_of(path: Path) -> dict:
    """The written .base read back with data-ui's own Python reader (dist/python/data_ui_base.py)."""
    sys.path.insert(0, str(DATA_UI / "dist" / "python"))
    try:
        from data_ui_base import loads
    except ImportError:
        pytest.skip("data-ui's python reader is not built")
    return loads((path / "coverage.base").read_text("utf-8"))


@needs_data_ui
def test_the_written_base_passes_data_ui_check(site):
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(site / "coverage.base"), "--json"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


def test_the_rail_is_the_group_then_the_split_then_small_categories_and_nothing_else(site):
    text = (site / "coverage.base").read_text("utf-8")
    base = base_of(site)
    facets = base["facets"]
    assert [f["property"] for f in facets] == ["item", "split", "bin", "ok"]
    assert all("as" not in f for f in facets), "a slider or a search keeps part of a cohort: never in the rail"
    assert facets[0]["order"] == ["vial", "pill", "cap", "box", "lid"]
    assert [p["name"] for p in base["pages"]] == PAGES
    assert base["settings"] == ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"]
    assert base["links"] == [{"from": "records.cohort", "to": "parts.cohort", "direction": "one-way"}]
    assert base["noun"] == ["record", "records"]
    assert "GENERATED" in text


def test_index_and_embed_are_one_workbench_tag_over_the_vendored_kit(site):
    index = (site / "index.html").read_text("utf-8")
    assert index.count("<data-workbench") == 1 and 'src="coverage.base"' in index
    assert (site / "vendor" / "data-ui" / "data-ui.js").is_file()
    embed = (site / "embed.html").read_text("utf-8")
    assert 'id="host-slot"' in embed and "no-url" in embed


def test_without_a_split_the_support_tab_is_left_out(picks, tmp_path):
    coverage = analyze(picks, ranges=RANGES, pairs=PAIRS, group_by="item")
    (tmp_path / "kit").mkdir()
    write_workbench(coverage, picks, tmp_path / "site", kit="../kit")
    base = base_of(tmp_path / "site")
    assert "Support" not in [p["name"] for p in base["pages"]]


# ── the page in a browser ───────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const out = { errors: [] };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const WB = 'data-workbench';
  async function open(url) {
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url);
    await page.waitForSelector(WB + '[data-ready]', { timeout: 30000 });
    await page.waitForTimeout(1200);
    return page;
  }
  const count = (page) => page.evaluate(() => document.querySelector('data-workbench data-count').textContent.trim());
  // every coverage figure on the shown page: its summed rows' totals (data-ui's hook, CONTRACT §52/§53)
  const figures = (page) => page.evaluate(() => [...document.querySelectorAll('data-workbench [tab]:not([hidden]) *')]
    .filter((el) => el.coverage && Array.isArray(el.coverage.rows))
    .map((el) => ({ type: el.coverage.type, problems: el.coverage.problems || [],
                    rows: el.coverage.rows.map((r) => ({ id: r.id, total: r.total, summed: r.summed })) })));
  let page = await open(spec.index);
  out.first = await page.evaluate(() => { const g = document.querySelector('data-workbench data-facets section.df-group'); return g && g.dataset.p; });
  out.count0 = await count(page);
  out.tabs = await page.evaluate(() => [...document.querySelectorAll('data-workbench data-tabs [role=tab]')].map((t) => t.dataset.tab));
  const tabNamed = (word) => out.tabs.find((t) => t.toLowerCase() === word);
  await page.click(`${WB} data-tabs [role=tab][data-tab="${tabNamed('numbers')}"]`); await page.waitForTimeout(800);
  out.numbers0 = await figures(page);
  await page.click(`${WB} data-facets section.df-group[data-p="item"] input[data-value="${spec.level}"]`);
  await page.waitForTimeout(800);
  out.count1 = await count(page);
  out.numbers1 = await figures(page);
  await page.click(`${WB} data-tabs [role=tab][data-tab="${tabNamed('pairs')}"]`); await page.waitForTimeout(800);
  out.pairs1 = await figures(page);
  out.kept = {};
  out.drawn = {};
  for (const tab of out.tabs) {
    await page.click(`${WB} data-tabs [role=tab][data-tab="${tab}"]`); await page.waitForTimeout(700);
    out.kept[tab] = await count(page);
    out.drawn[tab] = await page.evaluate(() => {
      const shown = document.querySelector('data-workbench [tab]:not([hidden])');
      if (!shown) return null;
      const canvases = [...shown.querySelectorAll('canvas')].filter((c) => c.width > 0 && c.height > 0).length;
      const empty = [...shown.querySelectorAll('.dv-empty, [data-empty]')].length;
      return { canvases, empty, text: shown.textContent.length };
    });
  }
  await page.close();
  page = await open(spec.embed);
  out.embed = await page.evaluate(() => {
    const slot = document.querySelector('#host-slot').getBoundingClientRect();
    const wb = document.querySelector('#host-slot > data-workbench').getBoundingClientRect();
    const box = document.querySelector('#host-slot');
    const inSlot = wb.left >= slot.left - 1 && wb.top >= slot.top - 1 && wb.right <= slot.right + 1 && wb.bottom <= slot.bottom + 1;
    return { slot: [box.clientWidth, box.clientHeight], inSlot, scrollX: document.documentElement.scrollWidth - window.innerWidth };
  });
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def browsed(site) -> dict:
    """Serve the site with traj_compare.serve on a free port (that pid stopped after), drive it with headless Chrome."""
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(site), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    try:
        line = server.stdout.readline()
        url = line.split(" on ", 1)[1].split()[0].rstrip("/")
        spec = {"index": f"{url}/index.html", "embed": f"{url}/embed.html", "level": "cap"}
        (site / "spec.json").write_text(json.dumps(spec))
        (site / "driver.js").write_text(DRIVER)
        result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                                capture_output=True, text=True, timeout=300)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


@needs_browser
def test_the_page_draws_with_no_errors_group_first(browsed):
    assert browsed["errors"] == []
    assert browsed["first"] == "item"
    assert browsed["count0"] == "240 of 240 records"
    assert [tab.lower() for tab in PAGES] == [t.lower() for t in browsed["tabs"]]


@needs_browser
def test_a_tick_recounts_the_histograms_to_the_oracle(browsed, picks, coverage):
    kept = [p for p in picks if p.item == "cap"]
    assert browsed["count1"] == f"{len(kept)} of 240 records"
    figures = [f for f in browsed["numbers1"] if f["type"] == "coverage-hist"]
    assert figures and all(not f["problems"] for f in figures)
    totals = {row["id"]: row["total"] for f in figures for row in f["rows"]}
    for name, hist in coverage.payload["hist"].items():
        low, high, n = hist["edges"]
        values = present([value_of(p, name) for p in kept])
        oracle = int(((values >= low) & (values <= high)).sum())
        matching = [total for rid, total in totals.items() if rid.endswith(name.replace(".", "_").replace("[", "_")
                                                                           .replace("]", "").replace("(", "_").replace(")", ""))]
        assert oracle in matching, (name, oracle, totals)
    before = {row["id"]: row["total"] for f in browsed["numbers0"] if f["type"] == "coverage-hist" for row in f["rows"]}
    assert sum(before.values()) > sum(totals.values())


@needs_browser
def test_a_tick_recounts_the_pair_planes_to_the_oracle(browsed, picks, coverage):
    kept = [p for p in picks if p.item == "cap"]
    figures = [f for f in browsed["pairs1"] if f["type"] == "coverage-plane"]
    totals = sorted(row["total"] for f in figures for row in f["rows"])
    expected = []
    for pair in coverage.payload["pairs"]:
        (xl, xh, nx), (yl, yh, ny) = pair["x_edges"], pair["y_edges"]
        xs = np.asarray([value_of(p, pair["x"]) for p in kept], float)
        ys = np.asarray([value_of(p, pair["y"]) for p in kept], float)
        expected.append(int(((xs >= xl) & (xs <= xh) & (ys >= yl) & (ys <= yh)).sum()))
    assert totals == sorted(expected)


@needs_browser
def test_every_tab_keeps_the_tick_and_draws_something(browsed, picks):
    kept = sum(1 for p in picks if p.item == "cap")
    assert set(browsed["kept"].values()) == {f"{kept} of 240 records"}
    for tab, drawn in browsed["drawn"].items():
        assert drawn and (drawn["canvases"] > 0 or tab.lower() == "records") and drawn["text"] > 0, (tab, drawn)


@needs_browser
def test_embedded_it_stays_in_the_hosts_slot(browsed):
    assert browsed["embed"]["slot"] == [1000, 680]
    assert browsed["embed"]["inSlot"] and browsed["embed"]["scrollX"] <= 1
