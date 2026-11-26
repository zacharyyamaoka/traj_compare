"""The 2026-11-25 run-view rework, in headless Chrome: line styles, sub-tabs, legend, pinned Open in Rerun.

Zach 2026-11-25, traj compare 3D viewer feedback: "it's not completely clear to me, like the errors and the
differences. It's about the line stylings used." Pinned here:

- the 3D view draws no dashed material in any of the three styles (A / B / C), switched by the bottom-right
  ``[data-tc-style-pick]`` and remembered; its elements carry plain words;
- the Trail decay / Look-ahead sliders exist and change what is drawn;
- the "Raw signals per joint" tab has exactly the sub-tabs q, qd, qdd, T, q / qd / qdd, q / qd / T, one shows at a time,
  and a stack draws each joint's q, qd, qdd one under the other; the legend hides a joint's graphs;
- ``[data-tc-rerun-pin]`` stays in the viewport's top-right corner after scrolling and, from a file, shows the command.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``); skipped otherwise.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from test_viewer3d_dropdown import CHROME, PLAYWRIGHT, pytestmark  # noqa: F401  (the same skip)
from traj_compare import Comparison, Situation, write_comparison_report

VIEWER = Path(__file__).resolve().parents[1] / "src" / "traj_compare" / "assets" / "viewer3d.js"

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  const out = { errors: [] };
  page.on('pageerror', (error) => out.errors.push(String(error)));
  await page.goto('file://' + process.argv[3] + '#tab=signals');
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].viewer3d,
                             null, { timeout: 30000 });
  await page.evaluate(() => { const tc = TrajCompare.state.pages[0]; tc.transport.setScrub((tc.transport.tMin + tc.transport.tMax) / 2); });
  const drawn = () => page.evaluate(() => {
    let dashed = 0, meshes = 0, vertices = 0;
    window.__scenes.forEach((scene) => scene.traverse((object) => {
      const materials = object.material ? [].concat(object.material) : [];
      materials.forEach((material) => { if (material.isLineDashedMaterial) dashed++; });
      if (object.isMesh) { meshes++; vertices += object.geometry.attributes.position.count; }
    }));
    return { dashed, meshes, vertices };
  });
  out.styles = {};
  for (const style of ['A', 'B', 'C']) {
    await page.selectOption('[data-tc-style-pick] select', style);
    await page.waitForTimeout(150);
    out.styles[style] = await drawn();
  }
  out.remembered = await page.evaluate(() => localStorage.getItem('traj-compare:3d-style'));
  out.labels = await page.evaluate(() => [...[...document.querySelectorAll('.tc-ddmenu')].pop().querySelectorAll('.tc-dditem')].map((item) => item.textContent.trim()));
  const slide = (key, index) => page.evaluate(([key, index]) => {
    const slider = document.querySelector('[data-tc-3d-slider="' + key + '"]');
    slider.value = index; slider.dispatchEvent(new Event('input', { bubbles: true }));
  }, [key, index]);
  await slide('3d:decay', 0); await page.waitForTimeout(150);
  out.shortTrail = await drawn();
  await slide('3d:decay', 9); await page.waitForTimeout(150);
  out.fullTrail = await drawn();
  out.subtabs = await page.evaluate(() => [...document.querySelectorAll('[data-tc-panel="signals"] [data-tc-subtab-title]')].map((node) => node.textContent));
  const titles = () => page.evaluate(() => [...document.querySelectorAll('[data-tc-panel="signals"] .tc-plotcard')]
    .filter((card) => card.offsetParent).map((card) => card.querySelector('.ptitle').textContent));
  await page.click('[data-tc-panel="signals"] [data-tc-subtab="qd"]'); await page.waitForTimeout(200);
  out.qd = await titles();
  await page.click('[data-tc-panel="signals"] [data-tc-subtab="q-qd-qdd"]'); await page.waitForTimeout(200);
  out.stack = await titles();
  await page.click('[data-tc-panel="signals"] [data-tc-legend-item="joint:j1"]'); await page.waitForTimeout(200);
  out.withoutJ1 = await titles();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(200);
  out.scrolled = await page.evaluate(() => window.scrollY);
  out.pin = await page.evaluate(() => { const r = document.querySelector('[data-tc-rerun-pin-open]').getBoundingClientRect();
    return { top: r.top, right: r.right, width: innerWidth }; });
  await page.click('[data-tc-rerun-pin-open]');
  out.pinText = await page.locator('[data-tc-rerun-pin-pop]').innerText();
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""


def comparison() -> Comparison:
    t = np.linspace(0.0, 30.0, 1201)
    q = np.column_stack([0.8 * np.sin(0.5 * t), 0.3 * np.cos(0.7 * t)])

    def fk(joints: np.ndarray) -> np.ndarray:
        poses = np.tile(np.eye(4), (len(joints), 1, 1))
        poses[:, 0, 3] = 0.3 + 0.2 * np.cos(joints[:, 0])
        poses[:, 1, 3] = 0.3 * np.sin(joints[:, 0])
        poses[:, 2, 3] = 0.2 + 0.1 * joints[:, 1]
        return poses

    return Comparison(
        title="rework", joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[Situation(name="run", title="Run", t=t, q=q + 0.002 * np.sin(3 * t)[:, None], tau=0.1 * q)],
        fk=fk,
    )  # fmt: skip


def test_the_viewer_source_creates_no_dashed_material():
    assert "LineDashedMaterial" not in VIEWER.read_text()


def test_line_styles_sub_tabs_legend_and_pinned_rerun(tmp_path):
    report = write_comparison_report(comparison(), tmp_path)
    document = report.read_text()
    assert document.count("scene.add(grid);") == 1
    hooked = report.with_name("hooked.html")
    hooked.write_text(document.replace("scene.add(grid);", "scene.add(grid); (window.__scenes = window.__scenes || []).push(scene);"))
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(hooked), str(CHROME)],
                            capture_output=True, text=True, check=True, timeout=180)
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert all(drawn["dashed"] == 0 and drawn["meshes"] > 0 for drawn in out["styles"].values()), out["styles"]
    assert out["remembered"] == "C"
    assert out["labels"] == ["Path", "Points", "Pose frames", "Tool Z axis", "Position error arrow", "Orientation error arc"], out["labels"]
    assert out["fullTrail"]["vertices"] > out["shortTrail"]["vertices"], (out["shortTrail"], out["fullTrail"])
    assert out["subtabs"] == ["q", "qd", "qdd", "T", "q / qd / qdd", "q / qd / T"]
    assert out["qd"] and all("joint speed" in title for title in out["qd"]), out["qd"]
    assert [title.split(":")[0] for title in out["stack"]] == ["j1", "j1", "j1", "j2", "j2", "j2"], out["stack"]
    assert [title.split(":")[0] for title in out["withoutJ1"]] == ["j2", "j2", "j2"], out["withoutJ1"]
    assert out["scrolled"] > 0
    pin = out["pin"]
    assert 0 <= pin["top"] <= 20 and out["pin"]["width"] - 20 <= pin["right"] <= out["pin"]["width"], pin
    assert "traj-compare-rerun " in out["pinText"], out["pinText"]
    assert "--comparison 0 --open" in out["pinText"], out["pinText"]
