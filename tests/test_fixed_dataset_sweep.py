"""The canonical Sweep tab can compare independent, path-matched speed measurements."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, Sweep, SweepObservation, write_dataset_report

from test_dataset_sweep import CHROME, PLAYWRIGHT, needs_browser, payload_of

PATHS = ("straight", "arc", "zigzag")
ITERATIONS = ("it0", "it1", "it2", "it3", "it4")
SPEEDS = tuple(index / 10 for index in range(1, 11))


def recorded_runs():
    for index, path in enumerate(PATHS):
        target = JointTrajectory(t=[0.0, 0.05, 0.1], joint_names=("joint",), positions=[[0], [index + 1], [0]])
        yield Run(name=path, reference=target, measured={"old-pd": target, "old-ctc": target},
                  tags={"path": path, "speed": 1.0, "shape": "line" if index == 0 else "corner",
                        "old-pd_error": 5.0, "old-ctc_error": 4.0})


def measurements():
    for iteration_number, iteration in enumerate(ITERATIONS):
        for speed in SPEEDS:
            for path_number, path in enumerate(PATHS):
                if (iteration, speed) == ("it4", 0.7):
                    continue
                value = speed * 10 + iteration_number + path_number
                if (iteration, speed, path) == ("it2", 0.4, "straight"):
                    value = None
                yield SweepObservation(iteration, path, speed, value)
    # The reporting data has two readings for one target in the first bin.
    yield SweepObservation("it0", "straight", 0.08, 3.0)
    yield SweepObservation("it0", "straight", 0.0, 500.0)
    yield SweepObservation("it0", "straight", 1.1, 600.0)


def site_at(root: Path, observations) -> Path:
    sweep = Sweep("speed", "{series}_error", facet_by="shape", unit="mm",
                  x_label="Speed fraction", y_label="Tool tracking RMS",
                  x_domain=(0.0, 1.0), x_step=0.1, observations=observations)
    write_dataset_report(list(recorded_runs()), root, title="Path-matched sweep", target_by="path", sweep=sweep,
                         rows=(), rerun=False)
    return root


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    path = tmp_path_factory.mktemp("fixed-speed-sweep")
    return site_at(path / "measured", list(measurements())), site_at(path / "empty", [])


def test_fixed_sweep_uses_only_supplied_iteration_measurements_and_all_paths(sites):
    payload = payload_of(sites[0])
    assert payload["series"] == ["old-pd", "old-ctc"]
    sweep = payload["sweep"]
    assert sweep["x_domain"] == [0.0, 1.0]
    assert sweep["x_buckets"] == list(SPEEDS)
    assert sweep["skipped"] == 2
    all_paths, straight, corners = sweep["facets"]
    assert [facet["expected"] for facet in (all_paths, straight, corners)] == [3, 1, 2]
    assert [series["name"] for series in all_paths["configs"]] == list(ITERATIONS)
    assert len({series["color"] for series in all_paths["configs"]}) == len(ITERATIONS)
    assert corners["configs"][0]["color"] == all_paths["configs"][0]["color"]
    points = {series["name"]: {point["x"]: point for point in series["points"]}
              for series in all_paths["configs"]}
    first = points["it0"][0.1]
    # 2.0 is the median of the straight path's two repeats. The three path medians are 2, 2, 3.
    assert (first["median"], first["q1"], first["q3"], first["n"]) == (2.0, 2.0, 2.5, 3)
    assert all(row["run"] is None for row in first["worst"])
    assert 0.0 not in points["it0"] and 1.1 not in points["it0"]
    incomplete = points["it2"][0.4]
    assert incomplete["n"] == 2 and incomplete["median"] is incomplete["q1"] is incomplete["q3"] is None
    assert corners["configs"][2]["points"][3]["median"] == 7.5
    assert 0.7 not in points["it4"]


def test_an_explicit_empty_sweep_keeps_the_domain_without_falling_back_to_runs(sites):
    sweep = payload_of(sites[1])["sweep"]
    assert sweep["observations"] and sweep["x_buckets"] == list(SPEEDS)
    assert sweep["facets"][0] == {"value": "all", "expected": 3, "configs": []}


@pytest.mark.parametrize("domain, step", [((1, 0), None), ((0, 1), 0.3), (None, 0.1), ((0, 1), 0)])
def test_refuses_an_invalid_sweep_grid(domain, step):
    with pytest.raises(ValueError):
        Sweep("speed", "error", x_domain=domain, x_step=step)


DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [measured, empty] = JSON.parse(process.argv[4]);
const shots = process.argv[5];
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const state = { errors: [] };
  for (const width of [1360, 375]) {
    const context = await browser.newContext({ viewport: { width, height: 850 }, colorScheme: 'dark' });
    await context.addInitScript(() => {
      let constructor;
      Object.defineProperty(window, 'uPlot', {
        configurable: true,
        get: () => constructor,
        set: (uPlot) => {
          constructor = function (opts, data, host) {
            const plot = new uPlot(opts, data, host);
            if (host?.matches('[data-tc-sweep-chart]')) {
              window.sweepPlot = plot;
              window.sweepChart = {
                x: data[0],
                lines: opts.series.map((series, i) => series.label ?
                  { name: series.label, values: data[i], spanGaps: series.spanGaps } : null).filter(Boolean),
              };
            }
            return plot;
          };
          Object.assign(constructor, uPlot);
        },
      });
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => state.errors.push(String(error)));
    await page.goto(measured + '#/sweeps');
    await page.waitForSelector('[data-tc-sweep-chart] canvas');
    state[width] = await page.evaluate(() => ({
      chart: { ...window.sweepChart, min: window.sweepPlot.scales.x.min, max: window.sweepPlot.scales.x.max },
      missing: [...document.querySelectorAll('[data-tc-sweep-missing]')].map((cell) => cell.textContent.trim()),
      hasCompleteCounts: [...document.querySelectorAll('[data-tc-sweep-cell]')].every((cell) => cell.textContent.includes('3/3 paths')),
      docWidth: document.documentElement.scrollWidth,
      tableScrolls: document.querySelector('.ds-sweep-scroll').scrollWidth > document.querySelector('.ds-sweep-scroll').clientWidth,
    }));
    await page.screenshot({ path: shots + '/sweep-' + width + '.png', fullPage: true });
    if (width === 1360) {
      await page.click('[data-tc-sweep-cell][data-config=it3][data-x="0.5"]');
      const detail = page.locator('[data-tc-sweep-worst-row]');
      state.openCount = await detail.count();
      state.fakeRunLink = await detail.locator('a[href^="runs/"]').count();
      state.detailText = await page.locator('[data-tc-sweep-worst] h3').textContent();
      await detail.first().locator('a').click();
      await page.locator('[data-tc-run-list]').waitFor({ state: 'visible' });
      state.target = new URL(page.url()).hash;
      await page.goto(measured + '#/targets');
      await page.click('[data-tc-targets-view] [data-view=table]');
      state.targetsTableVisible = await page.locator('#ds-view-table').isVisible();
      await page.click('[data-tc-targets-view] [data-view=cards]');
      state.targetCards = await page.locator('[data-tc-target-card]').count();
      await page.goto(measured + '#/');
      state.leagueNames = await page.locator('[data-tc-league-row]').evaluateAll(
        (rows) => rows.map((row) => row.getAttribute('data-key')));
      await page.goto(empty + '#/sweeps');
      state.emptyText = await page.locator('[data-tc-sweep-empty]').textContent();
    }
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(state));
})().catch((err) => { console.error(err); process.exit(1); });
"""


@needs_browser
def test_page_draws_five_curves_with_fixed_domain_and_real_target_links(sites, tmp_path):
    driver = tmp_path / "browser.js"
    driver.write_text(DRIVER)
    urls = [(site / "index.html").as_uri() for site in sites]
    result = subprocess.run(["node", str(driver), str(PLAYWRIGHT), str(CHROME), json.dumps(urls), str(tmp_path)],
                            text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout.strip().splitlines()[-1])
    assert status["errors"] == []
    for width in (1360, 375):
        page = status[str(width)]
        assert page["docWidth"] == width
        chart = page["chart"]
        assert (chart["min"], chart["max"], chart["x"]) == (0, 1, list(SPEEDS))
        assert [series["name"] for series in chart["lines"]] == list(ITERATIONS)
        assert all(not series["spanGaps"] for series in chart["lines"])
        assert chart["lines"][2]["values"][3] is None and chart["lines"][4]["values"][6] is None
        assert "– 2/3 paths" in page["missing"] and "– 0/3 paths" in page["missing"]
        assert page["hasCompleteCounts"]
    assert status["375"]["tableScrolls"]
    assert status["openCount"] == 3 and status["fakeRunLink"] == 0
    assert "target links open available recordings" in status["detailText"]
    assert status["target"].startswith("#/target/")
    assert status["targetsTableVisible"] and status["targetCards"] == 3
    assert status["leagueNames"] == ["old-ctc", "old-pd"]
    assert "complete target path set" in status["emptyText"]
