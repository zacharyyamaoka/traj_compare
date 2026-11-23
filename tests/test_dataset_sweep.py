"""The speed-sweep overview on the Dataset level (acceptance, written before the code, 2026-11-23).

Zach, Daily Note 2026-11-23 "Focus back on UR": "I want to be able to see the pareto graph that shows the accuracy vs time
scaling ... and then be able to drill down into any of the actual trajectories", and "I don't want to keep on making a new
viewer rather having the one kinda viewing setup that we add more info to eventually". So this is a view inside
traj_compare's Dataset level, not a new page.

The contract (``write_dataset_report(..., sweep=Sweep(...))`` -> ``payload["sweep"]``):

- ``Sweep(x, y, facet_by=None, x_label=x, y_label=y, unit="", log_y=False)``: ``x`` and ``y`` name numeric run tags (the
  time scaling and the accuracy metric), ``facet_by`` an optional tag that splits the overview into chips.
- One value per (target, config, x): the median over that config's runs of the target at that x (its repeats). A point
  per (facet, config, x): the median over targets of those values, ``q1`` / ``q3`` their 25th / 75th percentiles (numpy
  linear), ``n`` the number of targets, ``worst`` the top 10 targets by value, highest first (ties: target order), each
  ``{"target": slug, "title", "value", "run": slug of the run whose y is closest to the value, first on ties}``.
- Facets: ``"all"`` first, then each ``facet_by`` value in first-seen order. Configs in ``levels.configs`` order.
- A run without a numeric x or y is left out and counted in ``payload["sweep"]["skipped"]``.

The page (measured in headless Chrome):
- the targets view switch gains ``data-view="sweep"``, first, and it is the view the page opens on when the payload has a
  sweep; panel ``[data-tc-sweep]`` holds facet chips ``[data-tc-sweep-facet="<value>"]``, a chart
  ``[data-tc-sweep-chart]`` and a table ``[data-tc-sweep-table]`` with one ``[data-tc-sweep-cell]`` per config x speed
  (``data-config``, ``data-x``, the median as text; the lowest median at each x carries ``data-best="1"``);
- clicking a cell lists that point's worst targets in ``[data-tc-sweep-worst]``: rows ``[data-tc-sweep-worst-row]``,
  each with an ``a[href="#/target/<slug>"]`` and a link to ``runs/<run slug>/report.html``;
- a target link opens the Target level (``#/target/<slug>``, its run list showing);
- a site written without ``sweep`` has no sweep view (today's default stays).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, Sweep, write_dataset_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                                   reason="needs Node Playwright and Chrome")

JOINTS = ("j1", "j2")
SPEEDS = (0.25, 0.5, 1.0)
DATASETS = ("cell", "alone")
TASKS = 3
CONFIGS = ("pd", "ctc")
REPEATS = (0, 1)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def error_mm(dataset: str, task: int, speed: float, config: str, repeat: int) -> float:
    """A made-up but structured error: grows with speed; ctc halves it below full speed and is worse at full speed."""
    base = (1.0 + task) * (2.0 if dataset == "alone" else 1.0)
    scale = 1.0 if config == "pd" else (0.5 if speed < 1.0 else 1.5)
    return base * (1.0 + 4.0 * speed) * scale + 0.1 * repeat


def target_key(dataset: str, task: int, speed: float) -> str:
    return f"{dataset}-{task:03d} speed {speed:g}"


def _trajectory(duration_s: float, offset: float = 0.0) -> JointTrajectory:
    t = np.arange(0.0, duration_s + 1e-9, 0.02)
    q = np.column_stack([np.sin(t) + offset, np.cos(t) + offset])
    return JointTrajectory(t=t, joint_names=JOINTS, positions=q)


def build_runs(*, broken: bool = False) -> list[Run]:
    runs = []
    for dataset in DATASETS:
        for task in range(TASKS):
            for speed in SPEEDS:
                reference = _trajectory(1.0 / speed, offset=0.1 * task + (0.5 if dataset == "alone" else 0.0))
                for config in CONFIGS:
                    for repeat in REPEATS:
                        value = error_mm(dataset, task, speed, config, repeat)
                        runs.append(Run(
                            name=f"{target_key(dataset, task, speed)} {config} r{repeat}", reference=reference,
                            measured={"sim": _trajectory(1.0 / speed, offset=0.1 * task + 1e-3 * value)},
                            tags={"target": target_key(dataset, task, speed), "controller": config, "dataset": dataset,
                                  "speed_fraction": speed, "repeat": repeat, "tcp_rms_mm": value}))
    if broken:  # one run with no metric: left out of the sweep, counted as skipped
        first = runs[0]
        runs.append(Run(name="no metric", reference=first.reference, measured=dict(first.measured),
                        tags={**first.tags, "tcp_rms_mm": "n/a", "repeat": 9}))
    return runs


SWEEP = Sweep(x="speed_fraction", y="tcp_rms_mm", facet_by="dataset", x_label="time scaling", y_label="tool tracking RMS",
              unit="mm", log_y=True)


def payload_of(site: Path) -> dict:
    text = (site / "index.html").read_text("utf-8")
    return json.loads(re.search(r'id="traj-compare-dataset">(.*?)</script>', text, re.S).group(1).replace("<\\/", "</"))


def expected_point(facet: str, config: str, speed: float) -> dict:
    datasets = DATASETS if facet == "all" else (facet,)
    values = {target_key(d, k, speed): float(np.median([error_mm(d, k, speed, config, r) for r in REPEATS]))
              for d in datasets for k in range(TASKS)}
    ordered = sorted(values.items(), key=lambda item: -item[1])  # stable: ties keep target order
    return {"median": float(np.median(list(values.values()))), "q1": float(np.percentile(list(values.values()), 25)),
            "q3": float(np.percentile(list(values.values()), 75)), "n": len(values),
            "worst": [slug(key) for key, _ in ordered[:10]]}


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("sweep")
    write_dataset_report(build_runs(broken=True), root / "sweep", title="Sweep", target_by="target", config_by="controller",
                         sweep=SWEEP)
    write_dataset_report(build_runs(), root / "plain", title="Plain", target_by="target", config_by="controller")
    return root


# ── the payload ──────────────────────────────────────────────────────────────


def test_the_payload_carries_the_sweep_settings_and_counts_the_skipped_run(site):
    sweep = payload_of(site / "sweep")["sweep"]
    assert {key: sweep[key] for key in ("x", "y", "facet_by", "x_label", "y_label", "unit", "log_y")} == {
        "x": "speed_fraction", "y": "tcp_rms_mm", "facet_by": "dataset", "x_label": "time scaling",
        "y_label": "tool tracking RMS", "unit": "mm", "log_y": True}
    assert sweep["skipped"] == 1
    assert [facet["value"] for facet in sweep["facets"]] == ["all", *DATASETS]


def test_every_point_is_the_median_over_targets_of_the_median_over_repeats(site):
    sweep = payload_of(site / "sweep")["sweep"]
    for facet in sweep["facets"]:
        assert [config["name"] for config in facet["configs"]] == list(CONFIGS)
        for config in facet["configs"]:
            assert [point["x"] for point in config["points"]] == list(SPEEDS)
            for point in config["points"]:
                want = expected_point(facet["value"], config["name"], point["x"])
                assert point["median"] == pytest.approx(want["median"])
                assert point["q1"] == pytest.approx(want["q1"]) and point["q3"] == pytest.approx(want["q3"])
                assert point["n"] == want["n"]
                assert [row["target"] for row in point["worst"]] == want["worst"]
                values = [row["value"] for row in point["worst"]]
                assert values == sorted(values, reverse=True)


def test_each_worst_row_names_a_real_run_of_that_target_and_config(site):
    sweep = payload_of(site / "sweep")["sweep"]
    names = {json.loads(path.read_text("utf-8"))["name"]: path.parent.name for path in (site / "sweep" / "runs").glob("*/manifest.json")}
    point = sweep["facets"][0]["configs"][1]["points"][2]  # all · ctc · 1.0
    for row in point["worst"]:
        assert row["run"] in names.values()
        run_name = next(name for name, run_slug in names.items() if run_slug == row["run"])
        assert run_name.startswith(next(key for key in [target_key(d, k, 1.0) for d in DATASETS for k in range(TASKS)]
                                        if slug(key) == row["target"]))
        assert " ctc " in run_name


def test_a_site_without_a_sweep_has_none(site):
    assert "sweep" not in payload_of(site / "plain") or payload_of(site / "plain")["sweep"] is None


# ── the page ─────────────────────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [] };
  const vis = (page, sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).filter((el) => {
    const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0; }).length, sel);
  async function open(url) {
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url); await page.waitForTimeout(1200);
    return page;
  }
  // a site with a sweep opens on it
  // NAVIGATION.md Part E (2026-11-23): the sweep is the Speed sweeps tab; the Dataset level opens on the league Overview
  let page = await open(spec.sweep + '#/sweeps');
  out.views = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-dataset-tab]')).map((b) => b.getAttribute('data-tc-dataset-tab')));
  out.panel = await vis(page, '[data-tc-sweep]');
  out.chart = await page.evaluate(() => { const el = document.querySelector('[data-tc-sweep-chart]');
    if (!el) return null; const b = el.getBoundingClientRect(); return { w: b.width, h: b.height,
    drawn: el.querySelectorAll('canvas, svg').length }; });
  out.facets = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-sweep-facet]')).map((b) => b.getAttribute('data-tc-sweep-facet')));
  const cells = () => page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-sweep-cell]')).filter((el) => el.getBoundingClientRect().width > 0)
    .map((el) => ({ config: el.getAttribute('data-config'), x: Number(el.getAttribute('data-x')), text: el.textContent.trim(), best: el.getAttribute('data-best') })));
  out.cells_all = await cells();
  await page.click('[data-tc-sweep-cell][data-config="ctc"][data-x="1"]'); await page.waitForTimeout(400);
  out.worst = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-sweep-worst-row]')).filter((el) => el.getBoundingClientRect().width > 0)
    .map((row) => Array.from(row.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'))));
  await page.click('[data-tc-sweep-facet="alone"]'); await page.waitForTimeout(400);
  out.cells_alone = await cells();
  await page.click('[data-tc-sweep-cell][data-config="pd"][data-x="0.5"]'); await page.waitForTimeout(400);
  const link = await page.$('[data-tc-sweep-worst-row] a[href^="#/target/"]');
  out.first_target = link ? await link.getAttribute('href') : null;
  if (link) { await link.click(); await page.waitForTimeout(800); }
  out.after_click = { hash: await page.evaluate(() => location.hash), run_list: await vis(page, '[data-tc-run-list]') };
  // a site without one keeps today's default
  page = await open(spec.plain + '#/targets');
  out.plain_views = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-dataset-tab]')).map((b) => b.getAttribute('data-tc-dataset-tab')));
  out.plain_cards = await vis(page, '[data-tc-target-card]');
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def page(site) -> dict:
    spec = {"sweep": (site / "sweep" / "index.html").as_uri(), "plain": (site / "plain" / "index.html").as_uri()}
    (site / "spec.json").write_text(json.dumps(spec))
    (site / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                            capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def _median_text(cells, config, x):
    cell = next(c for c in cells if c["config"] == config and c["x"] == x)
    return float(re.search(r"[0-9]+(?:\.[0-9]+)?", cell["text"]).group(0)), cell["best"]


@needs_browser
def test_the_page_opens_on_the_sweep_with_a_drawn_chart_and_no_errors(page):
    assert page["errors"] == []
    assert "sweeps" in page["views"]  # Part E: a tab, no longer the landing view
    assert page["panel"] == 1
    assert page["chart"] and page["chart"]["w"] > 300 and page["chart"]["h"] > 150 and page["chart"]["drawn"] >= 1
    assert page["facets"] == ["all", *DATASETS]


@needs_browser
def test_the_table_shows_every_config_and_speed_with_the_best_marked(page):
    assert len(page["cells_all"]) == len(CONFIGS) * len(SPEEDS)
    for speed in SPEEDS:
        values = {config: _median_text(page["cells_all"], config, speed) for config in CONFIGS}
        for config in CONFIGS:
            assert values[config][0] == pytest.approx(expected_point("all", config, speed)["median"], rel=0.02)
        best = min(CONFIGS, key=lambda config: expected_point("all", config, speed)["median"])
        assert values[best][1] == "1" and all(values[c][1] != "1" for c in CONFIGS if c != best)


@needs_browser
def test_a_cell_lists_its_worst_targets_with_target_and_run_links(page):
    want = expected_point("all", "ctc", 1.0)["worst"]
    assert [next(h for h in row if h.startswith("#/target/")) for row in page["worst"]] == [f"#/target/{s}" for s in want]
    assert all(any(re.match(r"runs/[^/]+/report\.html$", h) for h in row) for row in page["worst"])


@needs_browser
def test_a_facet_chip_switches_the_numbers_and_a_target_link_opens_the_target(page):
    for config in CONFIGS:
        for speed in SPEEDS:
            got, _ = _median_text(page["cells_alone"], config, speed)
            assert got == pytest.approx(expected_point("alone", config, speed)["median"], rel=0.02)
    first = expected_point("alone", "pd", 0.5)["worst"][0]
    assert page["first_target"] == f"#/target/{first}"
    assert page["after_click"]["hash"] == f"#/target/{first}" and page["after_click"]["run_list"] == 1


@needs_browser
def test_a_site_without_a_sweep_keeps_todays_default(page):
    assert "sweeps" not in page["plain_views"]
    assert page["plain_cards"] > 0
