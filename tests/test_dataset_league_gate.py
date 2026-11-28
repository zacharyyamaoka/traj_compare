"""The league with a gate (acceptance, written before the code, 2026-11-27).

WHY: on the Gravity Compensation Controller box the league ranked S001 "best" by its median hand effort although it
fails the ruler's drift gate on half the cases (its median drift hid 74° falls). A ruler ranks only admissible
solutions; the league must be able to as well, without a box rolling its own page.

Contract (docs/NAVIGATION.md Part E, E2 "gate"): ``Sweep(gate=<tag>)`` names a numeric run tag (may hold ``{series}``)
that is >= 1 when the run passes every gate and < 1 when it fails one. Each league row gets ``data-gate`` = ``pass``
(every target in the facet at that x passes) or ``fail``, and ``[data-tc-league-gate]`` saying on how many targets it
fails. Rows that pass rank first (by the primary KPI), failing rows after them; rank 1 and the ratios' "best" and the
verdict are the best PASSING key. Without ``gate`` nothing changes (tests/test_dataset_league.py).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, Sweep, write_dataset_report
from tests.test_dataset_league import CHROME, PLAYWRIGHT, needs_browser

CONFIGS = {"light": 1.0, "ok": 2.0, "heavy": 3.0}  # effort per config; "light" fails the gate on 2 of 6 targets
TARGETS = 6
FAILS = {("light", 1), ("light", 4)}


def _trajectory(offset: float) -> JointTrajectory:
    t = np.arange(0.0, 1.0 + 1e-9, 0.05)
    return JointTrajectory(t=t, joint_names=("j1",), positions=np.column_stack([np.sin(t) + offset]))


def _runs() -> list[Run]:
    runs = []
    for task in range(TARGETS):
        for config, effort in CONFIGS.items():
            passes = 0.0 if (config, task) in FAILS else 1.0
            runs.append(Run(name=f"t{task} {config}", reference=_trajectory(0.1 * task), measured={"sim": _trajectory(0.1 * task + 0.01)},
                            tags={"target": f"t{task}", "controller": config, "all": 1, "sim_effort": effort + 0.01 * task,
                                  "sim_passes": passes}))
    return runs


SWEEP = Sweep(x="all", y="{series}_effort", gate="{series}_passes", y_label="hand effort", unit="N·m")


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("gate")
    write_dataset_report(_runs(), root / "site", title="Gate", target_by="target", config_by="controller", sweep=SWEEP,
                         drill_down="lazy")
    return root / "site"


def test_the_sweep_payload_carries_its_gate(site):
    text = (site / "index.html").read_text("utf-8")
    payload = json.loads(re.search(r'id="traj-compare-dataset">(.*?)</script>', text, re.S).group(1).replace("<\\/", "</"))
    assert payload["sweep"]["gate"] == "{series}_passes"


def test_a_sweep_without_a_gate_has_none():
    assert Sweep(x="a", y="b").gate is None


DRIVER = r"""
const [pw, chrome, url] = process.argv.slice(2);
const { chromium } = require(pw);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(url);
  await page.waitForSelector('[data-tc-league-row]');
  const rows = await page.$$eval('[data-tc-league-row]', (els) => els.map((el) => ({
    key: el.dataset.key, rank: el.dataset.rank, gate: el.dataset.gate || null,
    ratio: (el.querySelector('[data-tc-league-ratio]') || {}).textContent || null,
    note: (el.querySelector('[data-tc-league-gate]') || {}).textContent || null })));
  const verdict = await page.$eval('[data-tc-league-verdict]', (el) => el.textContent);
  console.log(JSON.stringify({ rows, verdict, errors }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def league(site) -> dict:
    (site / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), (site / "index.html").as_uri()],
                            capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


@needs_browser
def test_no_page_errors(league):
    assert league["errors"] == []


@needs_browser
def test_passing_configs_rank_before_a_lighter_one_that_fails_a_gate(league):
    rows = league["rows"]
    assert [row["key"] for row in rows] == ["ok", "heavy", "light"]
    assert [row["rank"] for row in rows] == ["1", "2", "3"]
    assert [row["gate"] for row in rows] == ["pass", "pass", "fail"]
    assert "best" in rows[0]["ratio"].lower()
    assert "2 of 6" in (rows[2]["note"] or ""), rows[2]


@needs_browser
def test_the_verdict_names_the_best_passing_config(league):
    verdict = league["verdict"]
    assert "ok" in verdict and "every gate" in verdict, verdict
