"""The three-level dataset view (Dataset → Target → Run) on the 2026-11-19 layout fixture, plus its review screenshots.

Turns ``docs/layout_proposals_2026-11-19/fixture/fixture.json`` (SIMULATED: a vertical planar 2R arm, 3 targets, 30 runs
tagged ``ff_model`` / ``date``, one sim or real series each) into production ``Run``s and writes the dataset with
``write_dataset_report(..., group_by=("target", "ff_model"))``. Zach reviewed the summary layouts on this data, so the
production levels are judged on it too. Each run's torque breakdown (its ``tau_cmd`` / ``tau_ff`` / ``tau_fb``, all three
given) goes into ``Run.torques``, so the Dataset band and League table show the FB share and drive gap, the Target's repeat
tab its feedback torque and FB share charts, and each run report its "Feedforward or feedback?" tab.

``--shots DIR`` also drives the pages in one headless Chrome (Node Playwright, 1440×900) and writes, in order: the
Dataset level as cards, as the league table (one config row expanded) and as today's runs view; the Target level's
repeat tab (lines up to N = 6, so ff v1's 8 real lines draw as a fan and ff v2's 6 as lines) and its history tab; the
run list grouped by date and by kind. WHY one browser behind one lock, pinned and niced (2026-11-19): the robot arm on
this host may be powered and a browser stalls its CAN bus; every traj_compare lane takes the same lock. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV .venv/bin/python docs/navigation_2026-11-19/dataset_from_fixture.py --shots /home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/dataset
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, write_dataset_report

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "layout_proposals_2026-11-19" / "fixture" / "fixture.json"
OUT = Path("/home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/dataset/site")
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
TAGS = ("ff_model", "date")  # the fixture's tags that name a config and a day; the rest are its simulation knobs
BREAKDOWN = ("tau_cmd", "tau_ff", "tau_fb")  # the fixture's command breakdown, joint-major like its other series


def _trajectory(record: dict, joints: tuple[str, ...], effort: str) -> JointTrajectory:
    """A fixture series (joint-major lists) as a robot_msgs JointTrajectory (sample-major arrays, SI)."""

    def columns(key: str) -> np.ndarray | None:
        return np.asarray(record[key], dtype=float).T if key in record else None

    return JointTrajectory(
        t=np.asarray(record["t"], dtype=float),
        joint_names=joints,
        positions=columns("q"),
        velocities=columns("qd"),
        accelerations=columns("qdd"),
        effort=columns(effort),
    )


def runs_from_fixture(path: Path = FIXTURE) -> list[Run]:
    """One ``Run`` per fixture run: its target as the reference, its one series named ``sim`` or ``real``."""
    fixture = json.loads(path.read_text("utf-8"))
    joints = tuple(fixture["joints"])
    targets = {target["name"]: target for target in fixture["targets"]}
    references = {name: _trajectory(target, joints, "tau") for name, target in targets.items()}
    runs = []
    for record in fixture["runs"]:
        target = targets[record["target"]]
        runs.append(
            Run(
                name=record["name"],
                reference=references[record["target"]],
                measured={record["kind"]: _trajectory(record, joints, "tau")},
                tags={"target": record["target"], **{key: record["tags"][key] for key in TAGS}},
                title=target["title"],
                # WHY (Zach 2026-11-19, torque breakdown in the dataset view): the demo shows the split it was built for.
                torques={record["kind"]: {key: np.asarray(record[key], dtype=float).T for key in BREAKDOWN if key in record}},
            )
        )
    return runs


DRIVER = r"""
const { chromium } = require(process.argv[2]);
const index = process.argv[4], out = process.argv[5];
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [], shots = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  async function shoot(name) {
    await page.waitForTimeout(600);
    await page.screenshot({ path: out + '/' + name + '.png' });
    shots.push(name + '.png');
  }
  await page.goto(index);
  await page.waitForSelector('[data-tc-target-card]');
  await shoot('1-dataset-cards');
  await page.click('[data-tc-targets-view] [data-view="table"]');
  await page.click('[data-tc-target-row="full-circle-slow"][data-config="v2 calibrated"]');
  await shoot('2-dataset-table');
  await page.click('[data-tc-targets-view] [data-view="runs"]');
  await shoot('3-dataset-runs');
  await page.click('[data-tc-targets-view] [data-view="cards"]');
  await page.click('[data-tc-target-card="full-circle-slow"] >> text=Open target');
  await page.waitForSelector('[data-tc-run-list] [data-tc-run]');
  await page.evaluate(() => {
    const input = document.querySelector('[data-tc-lines-n] input');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '6');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.hover('[data-tc-run][data-line="full-circle-slow/real-03 · real"]');
  await shoot('4-target-repeat');
  await page.click('[data-tc-target-tab][data-tab="history"]');
  await shoot('5-target-history');
  for (const key of ['date', 'kind']) {
    await page.selectOption('select[data-tc-sort]', key);
    await shoot('6-run-list-by-' + key);
  }
  await page.selectOption('select[data-tc-sort]', 'config');
  await page.click('[data-tc-target-tab][data-tab="repeat"]');
  console.log(JSON.stringify({ shots, errors }));
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
"""


def shoot(index: Path, out: Path) -> dict:
    """Drive the written pages in headless Chrome and write the review screenshots into ``out``."""
    if not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")):
        raise SystemExit(f"--shots needs Node Playwright ({PLAYWRIGHT}) and Chrome ({CHROME})")
    out.mkdir(parents=True, exist_ok=True)
    driver = out / "driver.js"
    driver.write_text(DRIVER, encoding="utf-8")
    try:
        result = subprocess.run(
            ["node", str(driver), str(PLAYWRIGHT), str(CHROME), index.as_uri(), str(out)],
            capture_output=True, text=True, timeout=300, check=False,
        )  # fmt: skip
    finally:
        driver.unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit(f"the screenshot driver failed: {result.stderr[-2000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT, help=f"the dataset folder (default {OUT})")
    parser.add_argument("--shots", type=Path, help="also write the review screenshots into this folder")
    args = parser.parse_args()
    runs = runs_from_fixture()
    index = write_dataset_report(runs, args.out, title="Layout fixture · 3 targets (SIMULATED)", group_by=("target", "ff_model"))
    payload = (index.read_text("utf-8").split('id="traj-compare-dataset">', 1)[1]).split("</script>", 1)[0]
    print(f"{index}  ({len(runs)} runs, index {index.stat().st_size / 1e3:.0f} kB, payload {len(payload) / 1e3:.0f} kB)")
    if args.shots:
        print(json.dumps(shoot(index, args.shots), indent=1))


if __name__ == "__main__":
    sys.exit(main())
