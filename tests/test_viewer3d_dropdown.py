"""The 3D viewer's layer dropdown stays open while you toggle layers (real headless Chrome, real mouse clicks).

WHY (Zach): he flips several layers (path line, points, robot, frames, arrows ...) on and off in a row to compare
them, so a click on a checkbox inside the open menu must not close it; a click elsewhere or Escape still does.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT`` = its package directory); skipped otherwise. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_viewer3d_dropdown.py
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from traj_compare import Comparison, Situation, write_comparison_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 1700 } })).newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto('file://' + process.argv[3]);
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].viewer3d, null, { timeout: 30000 });
  const isOpen = () => page.evaluate(() => !!document.querySelector('.tc-ddmenu.open'));
  const checked = () => page.evaluate(() => [...document.querySelectorAll('.tc-ddmenu.open input')].map((box) => box.checked));
  const out = { errors };
  await page.locator('.tc-ddbtn').first().click();
  out.openAfterButton = await isOpen();
  out.before = await checked();
  const boxes = page.locator('.tc-ddmenu.open .tc-dditem');
  await boxes.nth(0).click();   // click the label text, like Zach does
  out.openAfterFirstToggle = await isOpen();
  await boxes.nth(1).locator('input').click();  // and the bare checkbox
  out.openAfterSecondToggle = await isOpen();
  await boxes.nth(0).click();
  out.openAfterThirdToggle = await isOpen();
  out.after = await checked();
  await page.keyboard.press('Escape');
  out.openAfterEscape = await isOpen();
  await page.locator('.tc-ddbtn').first().click();
  out.reopened = await isOpen();
  await page.mouse.click(5, 5);  // somewhere that is not the menu
  out.openAfterOutsideClick = await isOpen();
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""


def comparison() -> Comparison:
    t = np.linspace(0.0, 5.0, 201)
    q = np.column_stack([0.8 * np.sin(0.5 * t), 0.3 * np.cos(0.7 * t)])

    def fk(joints: np.ndarray) -> np.ndarray:
        poses = np.tile(np.eye(4), (len(joints), 1, 1))
        poses[:, 0, 3] = 0.3 + 0.2 * np.cos(joints[:, 0])
        poses[:, 1, 3] = 0.3 * np.sin(joints[:, 0])
        poses[:, 2, 3] = 0.2 + 0.1 * joints[:, 1]
        return poses

    return Comparison(
        title="dropdown", joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[Situation(name="run", title="Run", t=t, q=q + 0.03)],
        fk=fk,
    )  # fmt: skip


def test_layer_menu_stays_open_while_toggling_and_closes_on_outside_click_or_escape(tmp_path):
    report = write_comparison_report(comparison(), tmp_path)
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(
        ["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(report), str(CHROME)],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["openAfterButton"]
    assert out["openAfterFirstToggle"], "clicking a layer's label closed the menu"
    assert out["openAfterSecondToggle"], "clicking a layer's checkbox closed the menu"
    assert out["openAfterThirdToggle"]
    # first layer toggled twice (back to start), second layer toggled once: the clicks really changed state
    assert out["after"][0] == out["before"][0]
    assert out["after"][1] != out["before"][1]
    assert not out["openAfterEscape"]
    assert out["reopened"]
    assert not out["openAfterOutsideClick"]
