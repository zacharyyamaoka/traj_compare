"""Summary / Insights pages at phone width: an insight carrying a long unbreakable line (a path, a command) wraps inside its card and
never widens the page (measured in headless Chrome, documentElement.scrollWidth <= the viewport).

WHY (2026-11-13, the five-bar pick-tracking report): its insights carry absolute paths and launcher commands as evidence; a grid item's
min-content width is its longest unbreakable word, so one path made the 390 px page 500-732 px wide and the 1200 px Insights page 1274.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``, default the aruco-studio checkout's); skipped otherwise. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_insight_wrap.py
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from traj_compare import Comparison, Insight, ReportPage, Situation, write_comparison_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true });
  const out = {};
  for (const width of [390, 1200]) {
    const page = await (await browser.newContext({ viewport: { width: width, height: 900 } })).newPage();
    await page.goto('file://' + process.argv[3]);
    await page.waitForTimeout(800);
    for (const label of ['Summary', 'Insights']) {
      await page.locator('#tc-tabs').getByText(label, { exact: true }).first().click();
      await page.waitForTimeout(400);
      out[`${label} ${width}`] = await page.evaluate(() => document.documentElement.scrollWidth);
    }
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""

LONG = "/archive/datasets/bam_rig/rack_2026-11-10/fivebar/pick_tracking/2026-11-13/coverage_real_000000/ladder/very_long_unbreakable_name.json"


def test_a_long_unbreakable_evidence_line_wraps_inside_its_card(tmp_path):
    t = np.linspace(0.0, 2.0, 101)
    q = np.column_stack([np.sin(t), np.cos(t)])
    comparison = Comparison(title="wrap", joint_names=["j1", "j2"], target=Situation(name="target", title="Target", t=t, q=q),
                            situations=[Situation(name="run", title="Run", t=t, q=q + 0.01)])
    insight = Insight("A card with a path", f"finding {LONG}", f"recommendation {LONG}", evidence=[LONG, "systemd-run " + "x" * 160],
                      tone="action")
    report = write_comparison_report(comparison, tmp_path, summary=ReportPage(title="Summary", name="summary", insights=[insight]),
                                     insights=ReportPage(title="Insights", name="insights", insights=[insight, insight]))
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(report), str(CHROME)],
                            capture_output=True, text=True, check=True, timeout=120)
    widths = json.loads(result.stdout.strip().splitlines()[-1])
    for key, width in widths.items():
        assert width <= int(key.split()[-1]), f"{key}: the page is {width} px wide"
