"""The outer dataset view: tabs and the config league table (acceptance, written before the code, 2026-11-23).

Zach, 2026-11-20 (outer-view babble, docs/proposals/outer-view-2026-11-20/CONTRACT.md): "the landing page is WAYYY to hard
to navigate ... At the highest level we want to be comparing different pipeline configurations vs how they do on all of
the targets ... you should probably add tabs so it's not all on the one page." 2026-11-23: "league table seems reasonable
please build that out" (V1 League table). The contract this pins is docs/NAVIGATION.md Part E.

Python (``write_dataset_report(..., sweep=Sweep(...))`` -> ``payload["sweep"]``):
- ``Metric(tag, label=tag, unit="", log=False, better="lower")``; ``Sweep(..., metrics=(Metric, ...))`` lists more KPI
  tags beside ``y``; ``payload["sweep"]["metrics"]`` = ``[{"tag", "label", "unit", "log", "better"}]``.
- ``facet_by`` may be a tuple of tags: a facet's value is their values joined by " · ".
- ``y`` / a metric tag may hold ``{series}``: each measured series of a run reads its own tag ("{series}_tcp_rms_mm" ->
  "sim_tcp_rms_mm", "real_tcp_rms_mm"). When more than one series has values, a sweep config is "<config> · <series>".

The page (headless Chrome, 1440 x 900, file://):
- The Dataset level is tabs ``[data-tc-dataset-tabs]``: ``[data-tc-dataset-tab]`` overview, sweeps (with a sweep),
  targets, runs, in that order; ``index.html`` (``#/``) opens on overview; ``#/sweeps``, ``#/targets``, ``#/runs`` open
  the others. Each tab's panel ``[data-tc-dataset-panel="<id>"]``.
- Overview: the league ``[data-tc-league]``: one ``[data-tc-league-row]`` per config (``data-key``) with a value at the
  fastest x, ranked best first (``data-rank`` 1..n); ``[data-tc-league-value]`` the median over the facet's targets (of
  each target's median over repeats) of y at the fastest x; ``[data-tc-league-ratio]`` that over the best's ("best" on
  rank 1); ``[data-tc-league-n]`` the targets; one ``[data-tc-league-spark][data-metric="<tag>"]`` per KPI (y and
  each metric). Facet chips ``[data-tc-league-facet="<value>"]`` switch the numbers. The whole table lies above the fold
  (its bottom <= 900 px) and the page is at most ~3 screens.
- A league row's click opens the Targets tab filtered to that config, facet and fastest x (``#/targets?...``):
  ``[data-tc-drill]`` lists its targets worst first, rows ``[data-tc-drill-row]`` (``data-target`` = slug), each with
  ``a[href="#/target/<slug>"]`` and a link to that config's ``runs/<run slug>/report.html``; a target link opens the
  Target level.
- Speed sweeps: today's sweep panel ``[data-tc-sweep]``, one ``[data-tc-sweep-metric="<tag>"]`` chart per metric, and the
  domain summary folded away in ``details[data-tc-domain-summary]`` (closed).
- Targets without a drill: cards / table (``[data-tc-targets-view]``), a page at a time; Runs: today's runs table.
- No tab is taller than ~3 screens (3.5 x 900 px) on a 60-target site; no page errors.
- Without a sweep the overview still ranks every config, by its median RMS joint error over targets (the levels'
  numbers), and the summary band stays.
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

from traj_compare import BarChart, BarSeries, ReportPage, Run, Sweep, write_dataset_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                                   reason="needs Node Playwright and Chrome")

VIEWPORT = (1440, 900)
SCREENS = 3.5  # "every tab <= ~3 screens"
JOINTS = ("j1", "j2")
SPEEDS = (0.25, 0.5, 1.0)
GROUPS = (("cell", "dev"), ("alone", "holdout"))
TASKS = 10  # 2 groups x 10 tasks x 3 speeds = 60 targets
CONFIGS = ("pd", "ctc", "mpc")
REPEATS = (0, 1)
SERIES = {"pd": ("sim",), "ctc": ("sim", "real"), "mpc": ("sim",)}
KEYS = ["pd · sim", "ctc · sim", "ctc · real", "mpc · sim"]  # levels.configs order, then the payload's series order
FASTEST = max(SPEEDS)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def facet_of(dataset: str, split: str) -> str:
    return f"{dataset} · {split}"


FACETS = ["all", *(facet_of(*group) for group in GROUPS)]


def error_mm(dataset: str, task: int, speed: float, config: str, series: str, repeat: int) -> float:
    """Made-up but structured: grows with speed; ctc best when slow, mpc best at full speed; real worse than sim."""
    base = (1.0 + 0.3 * task) * (2.0 if dataset == "alone" else 1.0) * (1.0 + 4.0 * speed)
    scale = {"pd": 1.0, "ctc": 0.4 if speed < 1.0 else 0.9, "mpc": 0.6 if speed < 1.0 else 0.3}[config]
    return base * scale * (1.7 if series == "real" else 1.0) + 0.05 * repeat + 0.01 * task * (config == "pd")


def energy_j(dataset: str, task: int, speed: float, config: str, series: str, repeat: int) -> float:
    return (10.0 + task) * (1.0 + speed) * {"pd": 1.0, "ctc": 1.3, "mpc": 1.6}[config] + (0.5 if series == "real" else 0.0) + 0.1 * repeat


def jerk(dataset: str, task: int, speed: float, config: str, series: str, repeat: int) -> float:
    return (100.0 + 7 * task) * speed ** 3 * {"pd": 1.0, "ctc": 2.0, "mpc": 4.0}[config] + 0.01 * repeat


def target_key(dataset: str, split: str, task: int, speed: float) -> str:
    return f"{dataset}-{split}-{task:03d} speed {speed:g}"


def _trajectory(duration_s: float, offset: float = 0.0) -> JointTrajectory:
    t = np.arange(0.0, duration_s + 1e-9, 0.05)
    q = np.column_stack([np.sin(t) + offset, np.cos(t) + offset])
    return JointTrajectory(t=t, joint_names=JOINTS, positions=q)


def build_runs(*, configs=CONFIGS, series_of=SERIES) -> list[Run]:
    runs = []
    for dataset, split in GROUPS:
        for task in range(TASKS):
            for speed in SPEEDS:
                reference = _trajectory(1.0 / speed, offset=0.1 * task + (0.5 if dataset == "alone" else 0.0))
                for config in configs:
                    for repeat in REPEATS:
                        tags = {"target": target_key(dataset, split, task, speed), "controller": config, "dataset": dataset,
                                "split": split, "speed_fraction": speed, "repeat": repeat}
                        measured = {}
                        for series in series_of[config]:
                            value = error_mm(dataset, task, speed, config, series, repeat)
                            measured[series] = _trajectory(1.0 / speed, offset=0.1 * task + 1e-3 * value
                                                           + (0.5 if dataset == "alone" else 0.0))
                            tags[f"{series}_tcp_rms_mm"] = value
                            tags[f"{series}_energy_j"] = energy_j(dataset, task, speed, config, series, repeat)
                            tags[f"{series}_jerk"] = jerk(dataset, task, speed, config, series, repeat)
                        runs.append(Run(name=f"{target_key(dataset, split, task, speed)} {config} r{repeat}",
                                        reference=reference, measured=measured, tags=tags))
    return runs


from traj_compare import Metric  # noqa: E402  (the new name this file pins; an ImportError is the red state)

METRICS = (Metric("{series}_energy_j", label="energy per task", unit="J"),
           Metric("{series}_jerk", label="tool jerk RMS", unit="m/s³", log=True))
SWEEP = Sweep(x="speed_fraction", y="{series}_tcp_rms_mm", facet_by=("dataset", "split"), x_label="time scaling",
              y_label="tool tracking RMS", unit="mm", log_y=True, metrics=METRICS)
SUMMARY = ReportPage(title="Bench scorecard", charts=[
    BarChart(f"Tool tracking RMS vs speed · {name}", [f"{s:g}" for s in SPEEDS],
             [BarSeries(config, [float(k + i) for i in range(len(SPEEDS))]) for k, config in enumerate(CONFIGS)], unit="mm")
    for name in ("a", "b", "c", "d", "e", "f")])


def value_of(fn, config: str, series: str, facet: str, speed: float) -> tuple[dict[str, float], float]:
    """Each target's median over repeats, and their median over the facet's targets."""
    values = {}
    for dataset, split in GROUPS:
        if facet != "all" and facet != facet_of(dataset, split):
            continue
        for task in range(TASKS):
            values[slug(target_key(dataset, split, task, speed))] = float(
                np.median([fn(dataset, task, speed, config, series, r) for r in REPEATS]))
    return values, float(np.median(list(values.values())))


def expected_league(facet: str) -> list[tuple[str, float, int]]:
    """(key, median at the fastest x, n), best first."""
    rows = []
    for key in KEYS:
        config, series = key.split(" · ")
        values, middle = value_of(error_mm, config, series, facet, FASTEST)
        rows.append((key, middle, len(values)))
    return sorted(rows, key=lambda row: row[1])


def payload_of(site: Path) -> dict:
    text = (site / "index.html").read_text("utf-8")
    return json.loads(re.search(r'id="traj-compare-dataset">(.*?)</script>', text, re.S).group(1).replace("<\\/", "</"))


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("league")
    runs = build_runs()
    write_dataset_report(runs, root / "league", title="League", target_by="target", config_by="controller", sweep=SWEEP,
                         summary=SUMMARY, drill_down="lazy")
    write_dataset_report(runs, root / "plain", title="Plain", target_by="target", config_by="controller", drill_down="lazy")
    simonly = build_runs(configs=("pd", "mpc"), series_of={"pd": ("sim",), "mpc": ("sim",)})
    write_dataset_report(simonly, root / "simonly", title="Sim only", target_by="target", config_by="controller",
                         sweep=SWEEP, drill_down="lazy")
    return root


# ── the payload ──────────────────────────────────────────────────────────────


def test_metric_defaults_and_validation():
    metric = Metric("energy")
    assert (metric.tag, metric.label, metric.unit, metric.log, metric.better) == ("energy", "energy", "", False, "lower")
    assert Metric("gates", better="higher").better == "higher"
    with pytest.raises(ValueError):
        Metric("x", better="sideways")


def test_the_sweep_payload_lists_its_metrics_and_joins_a_tuple_facet(site):
    sweep = payload_of(site / "league")["sweep"]
    assert sweep["metrics"] == [
        {"tag": "{series}_energy_j", "label": "energy per task", "unit": "J", "log": False, "better": "lower"},
        {"tag": "{series}_jerk", "label": "tool jerk RMS", "unit": "m/s³", "log": True, "better": "lower"},
    ]
    assert [facet["value"] for facet in sweep["facets"]] == FACETS
    assert sweep["skipped"] == 0


def test_a_series_template_splits_configs_by_series_when_more_than_one_has_values(site):
    sweep = payload_of(site / "league")["sweep"]
    for facet in sweep["facets"]:
        assert [config["name"] for config in facet["configs"]] == KEYS
        for config in facet["configs"]:
            name, series = config["name"].split(" · ")
            for point in config["points"]:
                _, middle = value_of(error_mm, name, series, facet["value"], point["x"])
                assert point["median"] == pytest.approx(middle)


def test_a_series_template_on_a_single_series_site_keeps_plain_config_names(site):
    sweep = payload_of(site / "simonly")["sweep"]
    assert [config["name"] for config in sweep["facets"][0]["configs"]] == ["pd", "mpc"]
    point = sweep["facets"][0]["configs"][1]["points"][-1]
    assert point["median"] == pytest.approx(value_of(error_mm, "mpc", "sim", "all", FASTEST)[1])


# ── the page ─────────────────────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [] };
  const vis = (el) => { if (!el) return false; const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
  async function open(url) {
    const context = await browser.newContext({ viewport: { width: spec.viewport[0], height: spec.viewport[1] } });
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url); await page.waitForTimeout(1200);
    return page;
  }
  const height = (page) => page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  const tabs = (page) => page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-dataset-tabs] [data-tc-dataset-tab]')).map((t) => ({
    id: t.getAttribute('data-tc-dataset-tab'), selected: t.getAttribute('aria-selected'), visible: t.getBoundingClientRect().width > 0 })));
  const panels = (page) => page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-dataset-panel]')).filter((p) => {
    const b = p.getBoundingClientRect(); return b.width > 0 && b.height > 0; }).map((p) => p.getAttribute('data-tc-dataset-panel')));
  const league = (page) => page.evaluate(() => {
    const table = document.querySelector('[data-tc-league]');
    const box = table ? table.getBoundingClientRect() : null;
    const rows = Array.from(document.querySelectorAll('[data-tc-league-row]')).filter((r) => r.getBoundingClientRect().width > 0).map((r) => ({
      key: r.getAttribute('data-key'), rank: r.getAttribute('data-rank'),
      value: (r.querySelector('[data-tc-league-value]') || {}).textContent || null,
      ratio: (r.querySelector('[data-tc-league-ratio]') || {}).textContent || null,
      n: (r.querySelector('[data-tc-league-n]') || {}).textContent || null,
      sparks: Array.from(r.querySelectorAll('[data-tc-league-spark]')).map((s) => s.getAttribute('data-metric')) }));
    const verdict = document.querySelector('[data-tc-league-verdict]');
    return { box: box && { top: box.top, bottom: box.bottom, width: box.width }, rows,
      facets: Array.from(document.querySelectorAll('[data-tc-league-facet]')).map((c) => c.getAttribute('data-tc-league-facet')),
      verdict: verdict ? verdict.textContent : null,
      band: (() => { const b = document.querySelector('[data-tc-dataset-summary]'); if (!b) return false; const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0; })() };
  });

  // ── the sweep site ──
  let page = await open(spec.league);
  out.open = { hash: await page.evaluate(() => location.hash), tabs: await tabs(page), panels: await panels(page),
    league: await league(page), height: await height(page) };
  await page.click('[data-tc-league-facet="' + spec.facet + '"]'); await page.waitForTimeout(400);
  out.facet = await league(page);
  await page.click('[data-tc-league-facet="all"]'); await page.waitForTimeout(400);
  await page.click('[data-tc-league-row][data-key="' + spec.drill_key + '"]'); await page.waitForTimeout(800);
  out.drill = await page.evaluate(() => ({
    hash: location.hash,
    selected: (document.querySelector('[data-tc-dataset-tab][aria-selected="true"]') || {}).getAttribute
      ? document.querySelector('[data-tc-dataset-tab][aria-selected="true"]').getAttribute('data-tc-dataset-tab') : null,
    visible: (() => { const d = document.querySelector('[data-tc-drill]'); return !!d && d.getBoundingClientRect().height > 0; })(),
    rows: Array.from(document.querySelectorAll('[data-tc-drill-row]')).filter((r) => r.getBoundingClientRect().width > 0).map((r) => ({
      target: r.getAttribute('data-target'), hrefs: Array.from(r.querySelectorAll('a[href]')).map((a) => a.getAttribute('href')) })),
  }));
  out.drill.height = await height(page);
  const link = await page.$('[data-tc-drill-row] a[href^="#/target/"]');
  out.first_target = link ? await link.getAttribute('href') : null;
  if (link) { await link.click(); await page.waitForTimeout(800); }
  out.target = await page.evaluate(() => ({ hash: location.hash,
    run_list: (() => { const l = document.querySelector('[data-tc-run-list]'); return !!l && l.getBoundingClientRect().width > 0; })() }));

  // every other tab, by its address
  for (const tab of ['sweeps', 'targets', 'runs']) {
    page = await open(spec.league + '#/' + tab);
    out[tab] = { tabs: await tabs(page), panels: await panels(page), height: await height(page) };
  }
  page = await open(spec.league + '#/sweeps');
  out.sweeps.detail = await page.evaluate(() => ({
    sweep: (() => { const s = document.querySelector('[data-tc-sweep]'); return !!s && s.getBoundingClientRect().height > 0; })(),
    metrics: Array.from(document.querySelectorAll('[data-tc-sweep-metric]')).filter((c) => c.getBoundingClientRect().height > 0)
      .map((c) => ({ tag: c.getAttribute('data-tc-sweep-metric'), drawn: c.querySelectorAll('canvas, svg').length })),
    summary: (() => { const d = document.querySelector('details[data-tc-domain-summary]'); return d ? { open: d.open, text: d.textContent.slice(0, 200) } : null; })(),
  }));
  page = await open(spec.league + '#/targets');
  out.targets.cards = await page.evaluate(() => document.querySelectorAll('[data-tc-target-card]').length);
  await page.click('[data-tc-targets-view] [data-view="table"]'); await page.waitForTimeout(800);
  out.targets.table_height = await height(page);
  out.targets.table_rows = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-target-row]')).filter((r) => r.getBoundingClientRect().width > 0).length);
  page = await open(spec.league + '#/runs');
  out.runs.table_rows = await page.evaluate(() => Array.from(document.querySelectorAll('#ds-table tbody tr')).filter((r) => r.getBoundingClientRect().width > 0).length);

  // ── without a sweep ──
  page = await open(spec.plain);
  out.plain = { tabs: await tabs(page), league: await league(page), height: await height(page) };
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

DRILL_KEY = "ctc · real"
FACET = facet_of("alone", "holdout")


@pytest.fixture(scope="module")
def page(site) -> dict:
    spec = {"league": (site / "league" / "index.html").as_uri(), "plain": (site / "plain" / "index.html").as_uri(),
            "viewport": VIEWPORT, "drill_key": DRILL_KEY, "facet": FACET}
    (site / "spec.json").write_text(json.dumps(spec))
    (site / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def number(text: str | None) -> float:
    match = re.search(r"[0-9]+(?:[.,][0-9]+)*(?:\.[0-9]+)?", (text or "").replace(",", ""))
    assert match, f"no number in {text!r}"
    return float(match.group(0))


@needs_browser
def test_no_page_errors(page):
    assert page["errors"] == []


@needs_browser
def test_the_dataset_level_is_four_tabs_and_opens_on_the_overview(page):
    opened = page["open"]
    assert [tab["id"] for tab in opened["tabs"]] == ["overview", "sweeps", "targets", "runs"]
    assert all(tab["visible"] for tab in opened["tabs"])
    assert [tab["id"] for tab in opened["tabs"] if tab["selected"] == "true"] == ["overview"]
    assert opened["panels"] == ["overview"]
    for tab in ("sweeps", "targets", "runs"):
        assert [t["id"] for t in page[tab]["tabs"] if t["selected"] == "true"] == [tab], tab
        assert page[tab]["panels"] == [tab], (tab, page[tab]["panels"])


@needs_browser
def test_the_league_ranks_every_config_by_its_median_at_the_fastest_x(page):
    rows = page["open"]["league"]["rows"]
    want = expected_league("all")
    assert [row["key"] for row in rows] == [key for key, _, _ in want]
    assert [row["rank"] for row in rows] == [str(k + 1) for k in range(len(want))]
    best = want[0][1]
    for row, (key, middle, n) in zip(rows, want):
        assert number(row["value"]) == pytest.approx(middle, rel=0.02), row
        assert number(row["n"]) == n, row
        if row["rank"] == "1":
            assert "best" in (row["ratio"] or "").lower(), row
        else:
            assert number(row["ratio"]) == pytest.approx(middle / best, rel=0.03), row


@needs_browser
def test_each_league_row_draws_a_sparkline_per_kpi(page):
    tags = [SWEEP.y] + [metric.tag for metric in METRICS]
    for row in page["open"]["league"]["rows"]:
        assert sorted(row["sparks"]) == sorted(tags), row


@needs_browser
def test_the_verdict_names_the_best_config(page):
    verdict = page["open"]["league"]["verdict"] or ""
    assert expected_league("all")[0][0].split(" · ")[0] in verdict, verdict


@needs_browser
def test_the_league_and_the_page_fit_the_screen(page):
    opened = page["open"]
    box = opened["league"]["box"]
    assert box and box["width"] > 600 and box["bottom"] <= VIEWPORT[1], box
    assert opened["height"] <= SCREENS * VIEWPORT[1], opened["height"]


@needs_browser
def test_a_facet_chip_switches_the_league_to_that_facet(page):
    assert page["open"]["league"]["facets"] == FACETS
    rows = page["facet"]["rows"]
    want = expected_league(FACET)
    assert [row["key"] for row in rows] == [key for key, _, _ in want]
    for row, (key, middle, n) in zip(rows, want):
        assert number(row["value"]) == pytest.approx(middle, rel=0.02), row
        assert number(row["n"]) == n


@needs_browser
def test_a_league_row_drills_to_its_worst_targets_then_a_target(page):
    drill = page["drill"]
    assert drill["hash"].startswith("#/targets"), drill["hash"]
    assert drill["selected"] == "targets" and drill["visible"]
    config, series = DRILL_KEY.split(" · ")
    values, _ = value_of(error_mm, config, series, "all", FASTEST)
    worst = [target for target, _ in sorted(values.items(), key=lambda item: -item[1])]
    shown = [row["target"] for row in drill["rows"]]
    assert len(shown) >= 10 and shown == worst[: len(shown)], shown
    for row in drill["rows"]:
        assert f"#/target/{row['target']}" in row["hrefs"], row
        assert any(re.match(rf"runs/{re.escape(row['target'])}-[^/]*ctc[^/]*/report\.html$", href) for href in row["hrefs"]), row
    assert drill["height"] <= SCREENS * VIEWPORT[1]
    assert page["first_target"] == f"#/target/{worst[0]}"
    assert page["target"]["hash"] == f"#/target/{worst[0]}" and page["target"]["run_list"]


@needs_browser
def test_speed_sweeps_holds_the_sweep_a_chart_per_metric_and_the_folded_summary(page):
    detail = page["sweeps"]["detail"]
    assert detail["sweep"]
    assert [chart["tag"] for chart in detail["metrics"]] == [metric.tag for metric in METRICS]
    assert all(chart["drawn"] >= 1 for chart in detail["metrics"])
    assert detail["summary"] is not None and detail["summary"]["open"] is False


@needs_browser
def test_no_tab_is_taller_than_about_three_screens(page):
    limit = SCREENS * VIEWPORT[1]
    for tab in ("sweeps", "targets", "runs"):
        assert page[tab]["height"] <= limit, (tab, page[tab]["height"])
    assert page["targets"]["table_height"] <= limit, page["targets"]["table_height"]


@needs_browser
def test_targets_and_runs_still_show_cards_the_target_table_and_the_runs_table(page):
    assert page["targets"]["cards"] > 0
    assert page["targets"]["table_rows"] > 0
    assert page["runs"]["table_rows"] > 0


@needs_browser
def test_without_a_sweep_the_overview_ranks_configs_by_joint_error_and_keeps_the_band(page):
    plain = page["plain"]
    assert [tab["id"] for tab in plain["tabs"]] == ["overview", "targets", "runs"]
    assert sorted(row["key"] for row in plain["league"]["rows"]) == sorted(CONFIGS)
    assert [row["rank"] for row in plain["league"]["rows"]] == ["1", "2", "3"]
    assert plain["league"]["band"]
    assert plain["height"] <= SCREENS * VIEWPORT[1]
