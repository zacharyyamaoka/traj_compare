"""Space toggles the active trajectory transport from the report panes."""

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from traj_compare import Comparison, Signal, Situation, write_comparison_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

DRIVER = """
const assert = require('node:assert/strict');
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('file://' + process.argv[3]);
    const playing = index => page.evaluate(i => TrajCompare.state.pages[i].transport.playing, index);
    await page.getByRole('tab', { name: 'Diagnostics' }).click();
    await page.keyboard.press('Space');
    assert.equal(await playing(0), true);
    await page.evaluate(() => document.activeElement.dispatchEvent(
      new KeyboardEvent('keydown', { key: ' ', repeat: true, bubbles: true, cancelable: true })));
    assert.equal(await playing(0), true);
    await page.keyboard.press('Space');
    assert.equal(await playing(0), false);

    await page.evaluate(() => {
      const input = document.createElement('input');
      document.body.prepend(input);
      input.focus();
    });
    await page.keyboard.press('Space');
    assert.equal(await page.locator('input').first().inputValue(), ' ');
    assert.equal(await playing(0), false);
    await page.locator('input').first().evaluate(input => { input.type = 'range'; });
    await page.keyboard.press('Space');
    assert.equal(await playing(0), true);
    await page.keyboard.press('Space');
    assert.equal(await playing(0), false);
    await page.getByRole('button', {name: 'Second'}).click();
    await page.keyboard.press('Space');
    assert.equal(await playing(0), false);
    assert.equal(await playing(1), true);
    await page.keyboard.press('Space');
    assert.equal(await playing(1), false);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
                    reason="needs Node Playwright and Chrome")
def test_space_plays_active_report_from_the_diagnostics_tab(tmp_path):
    t = np.arange(0.0, 10.0, 0.1)
    comparisons = [
        Comparison(title, ("joint",), [
            Situation("measured", t=t, q=t[:, None], channels={"contact": np.zeros(len(t))}),
        ], signals={"contact": Signal("Contact force", "N")}, channels_title="Diagnostics")
        for title in ("First", "Second")
    ]
    report = write_comparison_report(comparisons, tmp_path)
    driver = tmp_path / "driver.cjs"
    driver.write_text(DRIVER)
    result = subprocess.run(["node", driver, PLAYWRIGHT, report, CHROME], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
