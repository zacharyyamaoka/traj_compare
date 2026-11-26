"""Nominal speed scales are explicit trajectory metadata, with the workbench rail as their scope."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare.coverage import analyze
from traj_compare.coverage.workbench import workbench_rows, write_workbench

from test_coverage_workbench import CHROME, DATA_UI, PLAYWRIGHT, needs_browser


def _trajectory(positions):
    return JointTrajectory(t=np.array([0.0, 1.0, 3.0, 4.0]), joint_names=("base",),
                           positions=np.array(positions, dtype=float)[:, None])


@pytest.fixture
def tapes():
    return {
        "slow": _trajectory([0, 0, 1, 1]),
        "mid": _trajectory([0, 1, 2, 2]),
        "maximum": _trajectory([0, 1, 2, 3]),
        "unknown": _trajectory([0, 1, 2, 3]),
    }


def test_distribution_counts_tapes_and_sums_only_moving_intervals(tapes):
    coverage = analyze(tapes, speed_scales={"slow": 0.1, "mid": 0.31, "maximum": 1.0})
    speed = coverage.payload["speed_scale"]
    assert (speed["known"], speed["missing"]) == (3, 1)
    assert [(bucket["low"], bucket["high"]) for bucket in speed["bins"]] == [
        (index / 10, (index + 1) / 10) for index in range(10)
    ]
    assert [bucket["count"] for bucket in speed["bins"]] == [1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
    assert [bucket["motion_s"] for bucket in speed["bins"]] == [2, 0, 0, 3, 0, 0, 0, 0, 0, 4]
    rows, _ = workbench_rows(coverage, tapes)
    assert [row["speed_scale"] for row in rows] == [0.1, 0.31, 1.0, None]
    assert rows[-1]["speed_scale_motion_s"] is None


def test_every_tenth_belongs_to_the_bin_ending_at_that_tenth(tapes):
    trajectory = tapes["slow"]
    scales = {str(i): i / 10 for i in range(1, 11)}
    speed = analyze(dict.fromkeys(scales, trajectory), speed_scales=scales).payload["speed_scale"]
    assert [bucket["count"] for bucket in speed["bins"]] == [1] * 10


@pytest.mark.parametrize("bad", [0, -0.1, 1.01, float("nan"), float("inf"), True, "0.5"])
def test_rejects_invalid_calibration_metadata(tapes, bad):
    with pytest.raises(ValueError, match=r"fraction in \(0, 1\]"):
        analyze(tapes, speed_scales={"slow": bad})


def test_unknown_and_missing_scales_are_explicit(tapes):
    with pytest.raises(ValueError, match="unknown trajectories"):
        analyze(tapes, speed_scales={"typo": 0.5})
    assert analyze(tapes).payload["speed_scale"] is None
    speed = analyze(tapes, speed_scales={}).payload["speed_scale"]
    assert (speed["known"], speed["missing"]) == (0, 4)
    assert all(bucket["count"] == 0 for bucket in speed["bins"])


DRIVER = r"""
const { chromium } = require(process.argv[2]);
const assert = require('node:assert/strict');
(async () => {
  const [executablePath, url, directory] = process.argv.slice(3);
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox'] });
  try {
    const errors = [];
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
    const panelSelector = '[tab="Trajectory speed scale"] .dv-view-chart';
    const snapshot = () => {
      const charts = [...document.querySelectorAll('[tab="Trajectory speed scale"] .dv-view-chart')];
      return charts.filter((chart) => chart.vegaView).map(({vegaView: view}) => {
        const bars = [], labels = [];
        const visit = (node) => {
          if (node.mark?.marktype === 'rect' && Object.hasOwn(node.datum ?? {}, 'bin_total')) {
            const {speed_scale_high, bin_total} = node.datum;
            bars.push([speed_scale_high, bin_total]);
          }
          if (node.mark?.marktype === 'text') labels.push(node.text);
          for (const child of node.items ?? []) visit(child);
        };
        visit(view.scenegraph().root);
        return {domain: view.scale('x')?.domain(), bars, labels};
      });
    };
    await page.goto(url + '#tab=trajectory-speed-scale');
    await page.waitForSelector(panelSelector + ' canvas');
    assert.equal(await page.getByRole('tab', {name: 'Trajectory speed scale'}).getAttribute('aria-selected'), 'true');
    await page.waitForFunction(() => [...document.querySelectorAll('[tab="Trajectory speed scale"] .dv-view-chart')]
      .filter((chart) => chart.vegaView).length === 2);
    const full = await page.evaluate(snapshot);
    await page.screenshot({path: directory + '/speed-scale-desktop.png'});

    await page.locator('data-facets [data-p="dataset"] input[data-value="Mystery"]').click();
    await page.waitForFunction(() => [...document.querySelectorAll('[tab="Trajectory speed scale"] .dv-view-chart')]
      .filter((chart) => chart.vegaView?.data('rows').length === 1).length === 2);
    const missing = await page.evaluate(snapshot);
    await page.screenshot({path: directory + '/speed-scale-missing.png'});

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url + '#tab=trajectory-speed-scale');
    await page.waitForFunction(() => [...document.querySelectorAll('[tab="Trajectory speed scale"] .dv-view-chart')]
      .filter((chart) => chart.vegaView?.data('rows').length === 4).length === 2);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    await page.screenshot({path: directory + '/speed-scale-mobile.png'});
    console.log(JSON.stringify({full, missing, overflow, errors}));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


@needs_browser
def test_stock_workbench_draws_and_filters_speed_scale(tapes, tmp_path):
    tags = {name: {"dataset": "Mystery" if name == "unknown" else "Known", "split": "dev"} for name in tapes}
    coverage = analyze(tapes, tags=tags, speed_scales={"slow": 0.1, "mid": 0.31, "maximum": 1.0})
    write_workbench(coverage, tapes, tmp_path, title="Trajectory speed scale check")
    checked = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check",
                              str(tmp_path / "coverage.base"), "--json"], capture_output=True, text=True, timeout=60)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER)
    with subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(tmp_path), "--port", "0"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as server:
        try:
            assert server.stdout is not None
            url = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/") + "/index.html"
            result = subprocess.run(["node", str(driver), str(PLAYWRIGHT), str(CHROME), url, str(tmp_path)],
                                    capture_output=True, text=True, timeout=60)
        finally:
            server.terminate()
    assert result.returncode == 0, result.stdout + result.stderr
    drawn = json.loads(result.stdout.strip().splitlines()[-1])
    assert drawn["errors"] == []
    assert drawn["overflow"] <= 1
    full, missing = drawn["full"], drawn["missing"]
    assert [view["domain"] for view in full + missing] == [[0, 1]] * 4
    assert all("Fraction of maximum feasible speed" in view["labels"] for view in full + missing)
    assert [view["bars"] for view in full] == [[[0.1, 1], [0.4, 1], [1, 1]], [[0.1, 2], [0.4, 3], [1, 4]]]
    assert all("1 without a recorded speed scale" in view["labels"] for view in full)
    assert all(view["bars"] == [] and "No recorded speed scales in this selection" in view["labels"] for view in missing)
