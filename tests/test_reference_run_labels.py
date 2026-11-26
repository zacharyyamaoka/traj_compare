"""A run-to-run pair names its reference as the run it is, never "Target" (2026-11-20, from the arm_motion_bench walk).

The bench's pendulum report has a "sim → real" tab: the reference there is the sim run, and the torque card's dashed line is
that run's APPLIED torque. The components legend called it "Target" (the torque the target needs), which is a different
signal. ``Comparison.reference_kind`` ("target" | "run") says which one the reference is; the dataset drill-down sets "run"
for every pair whose first element is a measured series. Then:

- HTML: the torque components chip reads ``<reference title> τ (applied)``, the torque section's title names the reference
  instead of "target", and the toolbar's error group reads ``Error vs <reference title>``;
- the 3D view's error arrows read ``Position error arrow (vs <reference title>)`` (plain words since 2026-11-25);
- Rerun: each torque view's title names ``<reference title> (applied)`` instead of "target";
- a target reference (the default) keeps today's words.

Written by the dispatcher before its fix (red first), beside the bench's evidence
/home/bam/arm_motion_bench/reports/media/dashboard/shots/pendulum-7-sim-real-torque.png.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory
from scaling_fixtures import scaling_comparison

from traj_compare import Run, build_drill_down, write_comparison_report, write_dataset_report
from traj_compare.analysis import analyze_comparison

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")), reason="needs Node Playwright and Chrome"
)


def run_to_run(kind: str = "run"):
    """The 3-joint torque fixture with its reference retitled "sim": a run sitting in ``target`` (kind "run")."""
    comparison = scaling_comparison("3dof", tool=True, torque=True)
    reference = dataclasses.replace(comparison.target, title="sim")
    return dataclasses.replace(comparison, target=reference, **({"reference_kind": kind} if kind else {}))


# ── the model and the payload ────────────────────────────────────────────────


def test_comparison_says_what_its_reference_is_target_by_default():
    fields = {field.name: field for field in dataclasses.fields(scaling_comparison("1dof", tool=False, torque=True))}
    assert "reference_kind" in fields, "Comparison has no reference_kind"
    assert scaling_comparison("1dof", tool=False, torque=True).reference_kind == "target"


def test_an_unknown_reference_kind_is_refused():
    with pytest.raises(ValueError, match="reference_kind"):
        run_to_run("tape")


def test_the_payload_carries_the_reference_kind():
    assert analyze_comparison(run_to_run("run")).get("reference_kind") == "run"
    assert analyze_comparison(scaling_comparison("3dof", tool=False, torque=True)).get("reference_kind") == "target"


def test_the_dataset_drill_down_marks_run_to_run_pairs(tmp_path):
    t = np.linspace(0.0, 1.0, 101)
    joints = ("pivot",)

    def series(scale: float) -> JointTrajectory:
        return JointTrajectory(t=t, joint_names=joints, positions=scale * np.sin(t)[:, None],
                               effort=scale * np.cos(t)[:, None])

    run = Run(name="pendulum r0", reference=series(1.0), measured={"sim": series(1.01), "real": series(0.98)},
              torques={"real": {"tau_ff": np.cos(t)[:, None], "tau_fb": 0.1 * np.sin(t)[:, None]}})
    write_dataset_report([run], tmp_path, title="Pendulum", rows=())
    html = build_drill_down(tmp_path, run.name).read_text("utf-8")
    payload = json.loads(re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
    kinds = {page["title"]: page.get("reference_kind") for page in payload["comparisons"]}
    assert kinds.get("sim → real") == "run", kinds
    assert kinds.get("Reference → real") == "target", kinds
    assert kinds.get("Reference → sim") == "target", kinds


# ── Rerun ────────────────────────────────────────────────────────────────────


def _torque_view_names(payload: dict) -> list[str]:
    pytest.importorskip("rerun")
    from test_rerun_layouts import _find_tabs
    from test_rerun_tabs import _tab, _views

    from traj_compare.report import _colorize
    from traj_compare.rerun_export import layout_blueprint

    _colorize(payload)
    questions = _find_tabs(layout_blueprint("questions", payload, {}).root_container)[0]
    # the per-run breakdown views ("<joint>: <run> — <reference>, commanded, feedforward, feedback, applied [N·m]")
    return [view.name for view in _views(_tab(questions, "torque"), "TimeSeriesView") if "commanded, feedforward" in view.name]


def test_rerun_torque_views_name_the_reference_run_and_say_applied():
    names = _torque_view_names(analyze_comparison(run_to_run("run")))
    assert names, "no torque views"
    assert all("sim (applied)" in name for name in names), names
    assert not any("— target," in name for name in names), names


def test_rerun_torque_views_keep_target_for_a_target_reference():
    names = _torque_view_names(analyze_comparison(scaling_comparison("3dof", tool=False, torque=True)))
    assert names and all("— target," in name for name in names), names


# ── HTML, in headless Chrome ─────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const out = {};
  for (const [key, url] of JSON.parse(process.argv[4])) {
    const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto(url);
    try { await page.waitForSelector('.tc-torque-legend .chip', { timeout: 15000 }); } catch (error) { /* reported below */ }
    await page.waitForTimeout(300);
    out[key] = await page.evaluate(() => ({
      chips: [...document.querySelectorAll('.tc-torque-legend .chip')].map((chip) => chip.textContent.trim()),
      sections: [...document.querySelectorAll('[data-tc-section="joint-torque"]')].map((section) => section.textContent),
      errorGroup: [...document.querySelectorAll('.grouplabel')].map((label) => label.textContent.trim())
        .filter((text) => /^Error vs/.test(text)),
      arrows: [...document.querySelectorAll('.tc-dditem')].map((item) => item.textContent.trim())
        .filter((text) => /^Position error/.test(text)),
    }));
    out[key].errors = errors;
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("reference-labels")
    urls = []
    for key, comparison in (("run", run_to_run("run")), ("target", scaling_comparison("3dof", tool=True, torque=True))):
        report = write_comparison_report([comparison], root / key / "report.html", title=key, rerun=False)
        urls.append([key, report.resolve().as_uri() + "#tab=torque"])
    driver = root / "driver.cjs"
    driver.write_text(DRIVER, encoding="utf-8")
    done = subprocess.run(["node", str(driver), str(PLAYWRIGHT), str(CHROME), json.dumps(urls)],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@needs_browser
def test_html_torque_legend_names_the_reference_run_and_says_applied(pages):
    run = pages["run"]
    assert not run["errors"], run["errors"]
    assert run["chips"], "no torque components legend"
    assert run["chips"][0] == "sim τ (applied)", run["chips"]
    assert "Target" not in run["chips"], run["chips"]


@needs_browser
def test_html_torque_section_and_error_group_name_the_reference_run(pages):
    run = pages["run"]
    assert run["sections"] and all("Torque breakdown: sim (applied)," in text for text in run["sections"]), run["sections"]
    assert run["errorGroup"] == ["Error vs sim"], run["errorGroup"]


@needs_browser
def test_html_a_target_reference_keeps_todays_words(pages):
    target = pages["target"]
    assert not target["errors"], target["errors"]
    assert target["chips"] and target["chips"][0] == "Target", target["chips"]
    assert target["sections"] and all("Torque breakdown: target," in text for text in target["sections"]), target["sections"]
    assert target["errorGroup"] == ["Error vs target"], target["errorGroup"]


@needs_browser
def test_html_3d_arrows_point_at_the_reference_run_by_name(pages):
    assert pages["run"]["arrows"] and set(pages["run"]["arrows"]) == {"Position error arrow (vs sim)"}, pages["run"]["arrows"]
    assert pages["target"]["arrows"] and set(pages["target"]["arrows"]) == {"Position error arrow"}, pages["target"]["arrows"]
