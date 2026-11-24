"""Switching tabs keeps the tab bar where it was (2026-11-23).

Found recording the review clip: hiding the old tab before the new one was built shrank the page, the browser clamped the
scroll, and the FIRST visit to a tab jumped to the top, leaving its figures below a ~560 px header. The tab bar must stay
where it was on screen, or at the top of the window when it had scrolled past it, on first and later visits alike.
"""

from __future__ import annotations

import json
import math
import subprocess

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory

from test_coverage_page import CHROME, PLAYWRIGHT, needs_browser
from traj_compare.coverage import analyze

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 800 } })).newPage();
  await page.goto(process.argv[4]); await page.waitForTimeout(800);
  const navTop = () => page.evaluate(() => document.querySelector('[data-cov-nav]').getBoundingClientRect().top);
  const tabs = await page.evaluate(() => Array.from(document.querySelectorAll('[data-cov-tab]')).map((b) => b.getAttribute('data-cov-tab')));
  const out = [];
  // the tab bar scrolled to 40 px below the top of the window, then every tab opened twice
  for (const round of [1, 2]) {
    for (const tab of tabs) {
      await page.evaluate(() => { const nav = document.querySelector('[data-cov-nav]');
        window.scrollBy(0, nav.getBoundingClientRect().top - 40); });
      const before = await navTop();
      await page.click(`[data-cov-tab="${tab}"]`); await page.waitForTimeout(400);
      out.push({ round, tab, before, after: await navTop() });
    }
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@needs_browser
def test_every_tab_switch_keeps_the_tab_bar_in_place(tmp_path):
    t = np.arange(0.0, 6.0, 0.01)
    joints = ("a", "b", "c")
    limits = JointLimits(joint_names=joints, min_position=np.full(3, -math.pi), max_position=np.full(3, math.pi),
                         max_velocity=np.full(3, 3.0), max_acceleration=np.full(3, 20.0))
    trajectories = {f"t{k}": JointTrajectory(t=t, joint_names=joints, limits=limits,
                                             positions=np.sin(t[:, None] * (1 + k) + np.arange(3))) for k in range(4)}
    page = analyze(trajectories, title="Scroll").write_page(tmp_path / "index.html")
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(CHROME), page.as_uri()],
                            capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        pytest.fail(result.stderr[-2000:])
    moves = json.loads(result.stdout.strip().splitlines()[-1])
    jumped = [move for move in moves if abs(move["after"] - move["before"]) > 2]
    assert not jumped, jumped
