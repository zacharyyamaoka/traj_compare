"""Screenshot (and optionally record) the HTML run view's question tabs on the scaling fixtures (2026-11-19).

Builds ``tests/scaling_fixtures.py`` reports (1, 3, 6 and 46 joints; tool frame + torque breakdown on) and drives
them in one headless Chrome through Node Playwright, 1440×900 by default:

- every question tab of the 6-joint report;
- the 1- and 46-joint ``track`` and ``joints`` tabs (the 46-joint one with the Left hand part selected);
- the 6-joint ``joints`` tab with the stage folded;
- ``--video``: a ~10 s clip clicking through the six tabs of the 6-joint report (Playwright ``recordVideo``).

WHY one browser, one lock, pinned and niced (2026-11-19): the robot arm on this host may be powered and a browser
stalls its CAN bus; every traj_compare lane takes ``/tmp/claude-1000/traj-tc-heavy.lock``. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV \
        .venv/bin/python docs/navigation_2026-11-19/shoot_html.py <out dir> [--video] [--shapes 1dof,6dof,bimanual]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
sys.path.insert(0, str(PACKAGE / "tests"))

from scaling_fixtures import write_scaling_report  # noqa: E402

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const plan = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));

async function settle(page) {
  try {
    await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages.length && TrajCompare.state.pages[0].builtPage,
                               null, { timeout: 20000 });
  } catch (error) {}
  await page.waitForTimeout(900);
}

async function step(page, action) {
  if (action.tab) await page.click(`[data-tc-tabs] [data-tc-tab="${action.tab}"]`, { timeout: 3000 });
  if (action.part !== undefined) await page.click(`[data-tc-panel]:not([hidden]) [data-tc-part="${action.part}"]`, { timeout: 3000 });
  if (action.scrollTo) await page.evaluate((selector) => document.querySelector(selector).scrollIntoView({ block: 'start' }), action.scrollTo);
  if (action.fold) await page.click('[data-tc-stage-fold]', { timeout: 3000 });
  if (action.scrub !== undefined) await page.evaluate((time) => TrajCompare.state.pages[0].transport.setScrub(time), action.scrub);
  if (action.scrollTop) await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(action.wait || 600);
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const done = [];
  try {
    for (const job of plan.shots) {
      const context = await browser.newContext({ viewport: { width: plan.width, height: plan.height } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
      await page.goto('file://' + job.report + (job.hash || ''));
      await settle(page);
      for (const action of job.actions || []) {
        try { await step(page, action); } catch (error) { errors.push('action ' + JSON.stringify(action) + ': ' + String(error).split('\n')[0]); }
      }
      await page.screenshot({ path: job.out, fullPage: !!job.fullPage });
      done.push({ out: job.out, errors });
      await context.close();
    }
    if (plan.video) {
      const context = await browser.newContext({ viewport: { width: plan.width, height: plan.height },
                                                 recordVideo: { dir: plan.video.dir, size: { width: plan.width, height: plan.height } } });
      const page = await context.newPage();
      await page.goto('file://' + plan.video.report);
      await settle(page);
      await page.evaluate(() => TrajCompare.state.pages[0].transport.setScrub(1.4));
      await page.waitForTimeout(700);
      for (const tab of plan.video.tabs) {
        await page.click(`[data-tc-tabs] [data-tc-tab="${tab}"]`, { timeout: 3000 });
        await page.waitForTimeout(1500);
      }
      const video = page.video();
      await context.close();
      done.push({ video: await video.path() });
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(done));
})();
"""

SIX_TABS = ["track", "where", "joints", "timing", "torque", "signals"]


def plan_shots(reports: dict[str, Path], out: Path) -> list[dict]:
    shots = []
    if "6dof" in reports:
        for tab in SIX_TABS:
            shots.append({"report": str(reports["6dof"]), "out": str(out / f"6dof-{tab}.png"), "actions": [{"tab": tab}]})
        shots.append({"report": str(reports["6dof"]), "out": str(out / "6dof-joints-stage-folded.png"),
                      "actions": [{"tab": "joints"}, {"fold": True}]})  # fmt: skip
        shots.append({"report": str(reports["6dof"]), "out": str(out / "6dof-track-full.png"),
                      "actions": [{"tab": "track"}], "fullPage": True})  # fmt: skip
    if "1dof" in reports:
        for tab in ("track", "signals", "torque"):
            shots.append({"report": str(reports["1dof"]), "out": str(out / f"1dof-{tab}.png"), "actions": [{"tab": tab}]})
    if "bimanual" in reports:
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-track.png"), "actions": [{"tab": "track"}]})
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-joints-left-arm.png"), "actions": [{"tab": "joints"}]})
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-joints-left-hand.png"),
                      "actions": [{"tab": "joints"}, {"part": 2, "wait": 900}]})  # fmt: skip
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-joints-left-hand-full.png"),
                      "actions": [{"tab": "joints"}, {"part": 2, "wait": 900}], "fullPage": True})  # fmt: skip
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-torque-left-hand.png"),
                      "actions": [{"tab": "torque"}, {"part": 2, "wait": 900},
                                  {"scrollTo": '[data-tc-panel="torque"] [data-tc-finger="index"]'}]})  # fmt: skip
        shots.append({"report": str(reports["bimanual"]), "out": str(out / "46-signals.png"), "actions": [{"tab": "signals"}]})
    return shots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="where the PNGs (and the .webm) go")
    parser.add_argument("--shapes", default="1dof,6dof,bimanual")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build = out / "_reports"
    reports = {shape: write_scaling_report(shape, build / shape) for shape in args.shapes.split(",")}
    plan = {"width": args.width, "height": args.height, "shots": plan_shots(reports, out)}
    if args.video and "6dof" in reports:
        plan["video"] = {"report": str(reports["6dof"]), "dir": str(build / "video"), "tabs": SIX_TABS}
    (build / "plan.json").write_text(json.dumps(plan))
    (build / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(build / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(build / "plan.json")],
                            capture_output=True, text=True, timeout=900)  # fmt: skip
    if result.returncode:
        sys.exit(result.stderr[-3000:])
    for item in json.loads(result.stdout.strip().splitlines()[-1]):
        if "video" in item:
            clip = out / "6dof-tabs-tour.webm"
            Path(item["video"]).replace(clip)
            print(clip)
        else:
            print(item["out"], "errors:" if item["errors"] else "", *item["errors"])


if __name__ == "__main__":
    main()
