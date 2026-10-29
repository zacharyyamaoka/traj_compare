"""The 3D viewer in a real browser: rows outside the target's span draw no target pose and nothing ahead of the cursor.

A run that starts before its target (or ends after it) has null ``tp``/``tquat`` rows (analysis.py never extrapolates
the target). This opens such a report in headless Chrome, scrubs mid-run, and reads what the viewer's scene actually
draws: no segment may touch the origin (an arrow to a null pose), and no per-sample element (frames, z-vectors, z-arcs,
arrows) may belong to a sample later than the cursor.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT`` = its package directory, default the aruco-studio
checkout's); skipped otherwise. Run (from a fresh terminal):

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_viewer3d_span.py
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
  await page.addInitScript(() => { window.__scenes = []; });
  await page.goto('file://' + process.argv[3]);
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].viewer3d, null, { timeout: 30000 });
  const out = await page.evaluate(async (time) => {
    const page = TrajCompare.state.pages[0];
    const sit = page.data.situations.find((s) => s.three && s.three.tp);
    page.transport.setScrub(time);
    await new Promise((resolve) => setTimeout(resolve, 600));
    const rows = sit.three.p, times = sit.three.t;
    const touchesOrigin = [];
    const latestSample = {};
    window.__scenes[0].traverse((object) => {
      if (!object.visible || !object.isLineSegments) return;
      for (let up = object; up; up = up.parent) if (up.type === 'AxesHelper' || up.type === 'GridHelper') return;
      const position = object.geometry.attributes.position;
      const end = Math.min(position.count, object.geometry.drawRange.start + object.geometry.drawRange.count);
      let latest = -Infinity;
      for (let i = 0; i < end; i++) {
        const x = position.getX(i), y = position.getY(i), z = position.getZ(i);
        if (Math.hypot(x, y, z) < 1e-4) touchesOrigin.push([object.id, i]);
        // a vertex that sits exactly on a logged TCP position belongs to that sample
        const row = rows.findIndex((p) => Math.abs(p[0] - x) < 1e-4 && Math.abs(p[1] - y) < 1e-4 && Math.abs(p[2] - z) < 1e-4);
        if (row >= 0) latest = Math.max(latest, times[row]);
      }
      latestSample[object.id] = latest === -Infinity ? null : latest;  // JSON has no -Infinity
    });
    return { touchesOrigin: touchesOrigin, latestSample: latestSample, nullRows: sit.three.tp.filter((r) => r[0] === null).length };
  }, parseFloat(process.argv[5]));
  console.log(JSON.stringify({ errors: errors, ...out }));
  await browser.close();
})();
"""


def drive(tmp_path: Path, comparison: Comparison, scrub_s: float) -> dict:
    report = write_comparison_report(comparison, tmp_path)
    document = report.read_text()
    hook = "scene.add(grid);"
    assert document.count(hook) == 1
    # a test-only copy that hands the viewer's private scene to the page
    hooked = tmp_path / "report_hooked.html"
    hooked.write_text(document.replace(hook, hook + " window.__scenes.push(scene);"))
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(
        ["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(hooked), str(CHROME), str(scrub_s)],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    return json.loads(result.stdout.strip().splitlines()[-1])


def fk(q: np.ndarray) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, 0, 3] = 0.3 + 0.2 * np.cos(q[:, 0])
    poses[:, 1, 3] = 0.3 * np.sin(q[:, 0])
    poses[:, 2, 3] = 0.2 + 0.1 * q[:, 1]
    return poses


def q_of(t: np.ndarray, offset: float) -> np.ndarray:
    return np.column_stack([0.8 * np.sin(0.5 * t) + offset, 0.3 * np.cos(0.7 * t)])


def comparison(target_span: tuple[float, float], run_span: tuple[float, float]) -> Comparison:
    t_target = np.linspace(*target_span, 201)
    t_run = np.linspace(*run_span, 251)
    return Comparison(
        title="span", joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t_target, q=q_of(t_target, 0.0)),
        situations=[Situation(name="run", title="Run", t=t_run, q=q_of(t_run, 0.03))],
        fk=fk,
    )  # fmt: skip


@pytest.mark.parametrize(
    "target_span, run_span, scrub_s",
    [
        pytest.param((1.0, 5.0), (0.0, 5.0), 3.0, id="run-starts-before-target"),
        pytest.param((0.0, 4.0), (0.0, 6.0), 2.0, id="run-outlasts-target"),
    ],
)
def test_samples_outside_the_target_span_draw_no_arrow_and_nothing_ahead_of_the_cursor(tmp_path, target_span, run_span, scrub_s):
    result = drive(tmp_path, comparison(target_span, run_span), scrub_s)
    assert result["errors"] == []
    assert result["nullRows"] > 0, "the case must contain rows without a target pose"
    assert result["touchesOrigin"] == [], "an arrow or arc runs to the origin: a null target pose was drawn"
    # every per-sample element stops at the cursor (the path line itself is not a segment object)
    for object_id, latest in result["latestSample"].items():
        assert latest is None or latest <= scrub_s + 1e-6, f"scene object {object_id} draws a sample at t={latest} past the cursor {scrub_s}"
