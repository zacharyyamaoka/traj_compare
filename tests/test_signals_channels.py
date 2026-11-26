"""Signals beyond the joints: motor current and every other recorded channel, in both run viewers (written before the
code, 2026-11-20).

Contract: docs/NAVIGATION.md Part C1 (frozen 2026-11-20), on top of Part B's question tabs. Source: the arm_motion_bench
Trajectory Tracking Agent's gaps 1 and 2 — a series' ``JointTrajectory.channels`` (motor current, contact force, winding
temperature) never reached the run view. These tests are the implementing lane's ruler: it must not edit this file.

What is pinned:

- ``traj_compare.Signal(title, unit, columns, per_joint)``: a frozen dataclass in ``model.py``, exported from
  ``traj_compare``; ``Comparison.signals`` (default ``{}``) and ``write_dataset_report(signals=...)`` give them.
- ``Situation.channels[name]``: float, (N,) or (N, k) on the situation's own samples; ``__post_init__`` refuses any other
  dimensionality, a first dimension other than ``len(t)``, and the key ``"current"``, naming situation and channel.
- ``columns`` of another length than k, or ``per_joint=True`` on a channel that is not (N, J): ``ValueError``.
- The dataset: ``channels["current"]`` (N, J) becomes the drill-down's ``Situation.current``, reordered onto the
  reference's joints as ``effort`` is; it draws in the HTML ``signals`` tab's ``joint-current`` section (one row per
  joint) and as Rerun's "Motor current [A]" sub-tab. A ``"current"`` of any other shape: ``ValueError`` from
  ``write_dataset_report`` naming run, series and shape. Every other channel becomes ``Situation.channels``; only a
  ``per_joint`` one is reordered. ``signals`` are stored in every manifest under ``"signals"``, and a drill-down rebuilt
  in a fresh process draws them.
- The run view's ``channels`` tab, after ``signals``: title "What else was measured?", heading "How did every other
  recorded signal change over the run?", one ``[data-tc-section="channel-<slug>"]`` per channel, plot titles
  ``Contact force [N]`` / ``Contact force, x [N]``, no ``[]`` without a unit; shown when any situation (the target
  included) has a channel, dropped by ``traj_compare.tabs.tabs_for`` otherwise. Rerun: a tab of the same title, one
  TimeSeriesView per channel titled ``<title> [<unit>]``, entities ``/channels/<name>/<column>/<situation>``.

Readings this file takes where the contract is open (the implementer follows them):

- An undescribed channel's columns are labelled ``0``, ``1``, ... (robot_msgs' own ``channels/<name>/<index>``); the
  literal ``[0]`` the contract prints is accepted too, in plot titles and in entity paths.
- No unit: the Rerun view is titled by the title alone, as the HTML plot is.
- An undescribed (N, k) channel is never reordered, even when k equals the joint count (only ``per_joint`` is).
- Every channel section is visible when the ``channels`` tab opens (none starts toggled off); a plot is a visible
  ``<canvas>`` and its title the text of its ``.ptitle`` (the title element every run-view plot card has), equal to
  the expected title or that title followed by `` · <note>``.
- Rerun: each channel view's origin is ``/channels/<name>`` (it holds all its columns and situations); the "Motor
  current [A]" sub-tab is the last signals sub-tab and holds one TimeSeriesView per joint, like its siblings; entity
  path parts are escaped as robot_msgs' logger escapes them (``rerun_export._part``).
- ``manifest["signals"]`` maps each described channel to ``{"title", "unit", "columns", "per_joint"}``.

Pins today's behaviour (passes now, must keep passing): ``test_without_channels_the_tabs_are_todays`` and
``test_a_dataset_without_channels_drills_down_to_todays_tabs``.

Browser tests need Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``); Rerun tests need the ``rerun`` extra; each is
skipped otherwise. Run:

    env -u VIRTUAL_ENV /home/bam/traj_compare/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_signals_channels.py
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import traj_compare
from signals_fixture import (
    BAD_CURRENT,
    BAD_RUN,
    CARRIERS,
    CHANNEL_NAMES,
    CHANNEL_RUN,
    DESCRIBED,
    ENTITY_COLUMNS,
    EXPECTED_PLOT_TITLES,
    EXPECTED_VIEW_TITLES,
    JOINTS,
    SAMPLES,
    SERIES,
    SLUGS,
    SPINDLE,
    T,
    bad_current_run,
    channel_runs,
    channel_values,
    channels_comparison,
    current_values,
    dataset_channels,
    described_signals,
    reference_positions,
)
from traj_compare import Comparison, Situation, build_drill_down, write_comparison_report, write_dataset_report
from traj_compare.analysis import analyze_comparison
from traj_compare.report import _colorize
from traj_compare.rerun_export import _part
from traj_compare.tabs import tabs_for

REPO = Path(__file__).resolve().parents[1]
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
HAS_BROWSER = PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node") is not None
HAS_RERUN = importlib.util.find_spec("rerun") is not None
needs_browser = pytest.mark.skipif(not HAS_BROWSER, reason="needs Node Playwright and Chrome")
needs_rerun = pytest.mark.skipif(not HAS_RERUN, reason="needs the rerun extra")

CHANNELS_TITLE = "What else was measured?"
CHANNELS_HEADING = "How did every other recorded signal change over the run?"
# The fixtures have three joints, no tool frame and no torque breakdown: today's tabs (NAVIGATION.md Part B).
TODAY_IDS = ["track", "joints", "signals"]
TODAY_TITLES = ["Did it track the target?", "Which joint has the error?", "Raw signals per joint"]
SIGNALS_TITLE = "Raw signals per joint"
SIGNAL_SUB_TABS = ["Angle [°]", "Speed [°/s]", "Applied torque [N·m]"]
MOTOR_CURRENT = "Motor current [A]"
DRILL_CHANNELS = {"channel-winding-temp", "channel-grip-force", "channel-contact-force"}  # current is no channel
MIN_PIXELS = 10  # a drawn trace covers far more; antialiasing and dashes never get it this low


# ── names that do not exist yet: fetched inside each test, never at import ───


def signal_class() -> Any:
    Signal = getattr(traj_compare, "Signal", None)
    assert Signal is not None, "traj_compare.Signal does not exist (NAVIGATION.md C1: a frozen dataclass in model.py)"
    return Signal


def require_situation_channels() -> None:
    names = {field.name for field in dataclasses.fields(Situation)}
    assert "channels" in names, "Situation has no `channels` field (NAVIGATION.md C1)"


def require_comparison_signals() -> None:
    names = {field.name for field in dataclasses.fields(Comparison)}
    assert "signals" in names, "Comparison has no `signals` field (NAVIGATION.md C1)"


def ready() -> Any:
    """``Signal``, after asserting the model carries channels and signals."""
    Signal = signal_class()
    require_situation_channels()
    require_comparison_signals()
    return Signal


# ── one build per module ─────────────────────────────────────────────────────
# WHY a cache, not fixtures: a missing feature then fails each test with its own traceback, never as a setup ERROR.

_CACHE: dict[str, tuple[bool, Any]] = {}


def cached(key: str, build: Callable[[], Any]) -> Any:
    if key not in _CACHE:
        try:
            _CACHE[key] = (True, build())
        except Exception as error:  # noqa: BLE001 - re-raised in every test that needs it
            _CACHE[key] = (False, error)
    ok, value = _CACHE[key]
    if not ok:
        raise AssertionError(f"building {key!r} failed: {type(value).__name__}: {value}") from value
    return value


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("signals_channels")


def dataset(workspace: Path, which: str) -> Path:
    """``described``: channel_runs() + ``signals``; ``undescribed``: the same runs, no ``signals`` argument (today's
    API); ``plain``: no channels anywhere."""

    def build() -> Path:
        out = workspace / f"dataset-{which}"
        if which == "described":
            Signal = signal_class()
            write_dataset_report(channel_runs(), out, title="C1 described", signals=described_signals(Signal))
        elif which == "undescribed":
            write_dataset_report(channel_runs(), out, title="C1 undescribed")
        else:
            write_dataset_report(channel_runs(channels=False), out, title="C1 plain")
        return out

    return cached(f"dataset:{which}", build)


def _fresh_process_drill(out: Path, run_name: str) -> Path:
    """``build_drill_down`` in a new interpreter: only what the files hold (the manifest) can reach the report."""
    code = "import sys\nfrom traj_compare import build_drill_down\nprint(build_drill_down(sys.argv[1], sys.argv[2]))"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO / "src"), os.environ.get("PYTHONPATH")]))}
    result = subprocess.run([sys.executable, "-c", code, str(out), run_name], capture_output=True, text=True,
                            timeout=300, env=env)  # fmt: skip
    assert result.returncode == 0, f"build_drill_down in a fresh process failed:\n{result.stderr[-3000:]}"
    return Path(result.stdout.strip().splitlines()[-1])


def drilled(workspace: Path, which: str, run_name: str = CHANNEL_RUN) -> Path:
    """The run's drill-down report; the ``described`` one is rebuilt in a fresh process, from its manifest alone."""

    def build() -> Path:
        out = dataset(workspace, which)
        if which == "described":
            return _fresh_process_drill(out, run_name)
        return build_drill_down(out, run_name)

    return cached(f"drill:{which}:{run_name}", build)


def report_pages(report: Path) -> list[dict]:
    html = report.read_text("utf-8")
    match = re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S)
    assert match, f"{report}: no run payload"
    return json.loads(match.group(1).replace("<\\/", "</"))["comparisons"]


def drill_page(report: Path) -> dict:
    pages = report_pages(report)
    found = [page for page in pages if page["name"] == f"reference--{SERIES}"]
    assert len(found) == 1, [page["name"] for page in pages]
    return found[0]


def entry_of(page: dict, name: str) -> dict:
    return next(entry for entry in page["situations"] if entry["name"] == name)


def tab_ids(payload: dict) -> list[str]:
    return [tab["id"] for tab in payload["tabs"]]


def as_array(values: list) -> np.ndarray:
    return np.array([np.nan if value is None else value for value in values], dtype=float)


def captured_situations(monkeypatch, out: Path, workspace: Path, label: str) -> list:
    """Every ``Situation`` the drill-down constructs for "channels run", built in-process from a copy of ``out``."""
    copy = workspace / f"capture-{label}"
    if not copy.exists():
        shutil.copytree(out, copy)
    captured: list = []
    original = Situation.__post_init__

    def recording(self) -> None:
        original(self)
        captured.append(self)

    monkeypatch.setattr(Situation, "__post_init__", recording)
    build_drill_down(copy, CHANNEL_RUN)
    monkeypatch.undo()
    return captured


# ── Signal and the model ─────────────────────────────────────────────────────


def test_signal_is_a_frozen_dataclass_in_model_exported_from_traj_compare():
    Signal = signal_class()
    from traj_compare import model

    assert getattr(model, "Signal", None) is Signal, "Signal lives in traj_compare/model.py"
    assert "Signal" in traj_compare.__all__
    assert dataclasses.is_dataclass(Signal)
    assert [field.name for field in dataclasses.fields(Signal)] == ["title", "unit", "columns", "per_joint"]
    default = Signal()
    assert (default.title, default.unit, list(default.columns), default.per_joint) == ("", "", [], False)
    described = Signal("Contact force", "N", ("x", "y", "z"), True)  # the contract's positional order
    assert (described.title, described.unit, list(described.columns), described.per_joint) == (
        "Contact force", "N", ["x", "y", "z"], True,
    )  # fmt: skip
    with pytest.raises(dataclasses.FrozenInstanceError):
        described.title = "Force"


def test_comparison_signals_default_to_empty_and_keep_the_descriptions_given():
    require_comparison_signals()
    assert dict(channels_comparison(None, channels=False).signals) == {}
    Signal = ready()
    signals = channels_comparison(Signal).signals
    assert set(signals) == set(DESCRIBED)
    for name, signal in described_signals(Signal).items():
        assert (signals[name].title, signals[name].unit, list(signals[name].columns), signals[name].per_joint) == (
            signal.title, signal.unit, list(signal.columns), signal.per_joint,
        ), name  # fmt: skip


def test_a_situation_keeps_1d_and_2d_channels_as_float_on_its_own_samples():
    require_situation_channels()
    q = reference_positions()
    assert dict(Situation(name="bare", t=T, q=q).channels) == {}
    grip, contact = channel_values("real", "grip_force"), channel_values("real", "contact_force")
    mode = np.arange(SAMPLES) % 3  # integers: stored as float
    situation = Situation(name="real", t=T, q=q, channels={"grip_force": grip, "contact_force": contact, "mode": mode})
    assert set(situation.channels) == {"grip_force", "contact_force", "mode"}
    for name, given in (("grip_force", grip), ("contact_force", contact), ("mode", mode)):
        stored = np.asarray(situation.channels[name])
        assert stored.dtype.kind == "f", f"{name}: dtype {stored.dtype}, expected float"
        assert stored.shape == np.shape(given), f"{name}: shape {stored.shape}, given {np.shape(given)}"
        np.testing.assert_array_equal(stored, np.asarray(given, dtype=float))


@pytest.mark.parametrize(
    "key, values",
    [
        pytest.param("probe_signal", np.float64(1.0), id="0-D"),
        pytest.param("probe_signal", np.zeros((SAMPLES, 2, 2)), id="3-D"),
        pytest.param("probe_signal", np.zeros(SAMPLES - 1), id="1-D, one sample short"),
        pytest.param("probe_signal", np.zeros((SAMPLES + 1, 2)), id="2-D, one sample long"),
        pytest.param("current", np.zeros((SAMPLES, 3)), id="the key current"),
    ],
)  # fmt: skip
def test_a_situation_refuses_a_channel_it_cannot_hold_naming_situation_and_channel(key, values):
    require_situation_channels()
    with pytest.raises(ValueError) as info:
        Situation(name="probe_run", t=T, q=reference_positions(), channels={key: values})
    message = str(info.value)
    assert "probe_run" in message and key in message, f"the error names neither situation nor channel: {message!r}"


def test_signal_columns_must_have_one_name_per_column():
    Signal = ready()
    analyze_comparison(channels_comparison(Signal))  # the fixture's own descriptions are valid
    wrong = {**described_signals(Signal), "contact_force": Signal(title="Contact force", unit="N", columns=("x", "y"))}
    with pytest.raises(ValueError):  # at construction or at analysis; contact_force has 3 columns
        analyze_comparison(channels_comparison(Signal, signals=wrong))


def test_a_per_joint_signal_needs_one_column_per_joint():
    Signal = ready()
    wrong = {**described_signals(Signal), "contact_force_n": Signal(title="Contact force", unit="N", per_joint=True)}
    with pytest.raises(ValueError):  # contact_force_n is (N, 2) on three joints
        analyze_comparison(channels_comparison(Signal, signals=wrong))


# ── the tab rule (traj_compare.tabs.tabs_for) ────────────────────────────────


def test_tabs_for_puts_the_channels_tab_right_after_signals_with_one_section_per_channel():
    Signal = ready()
    payload = analyze_comparison(channels_comparison(Signal))
    tabs = tabs_for(payload)
    assert [tab["id"] for tab in tabs] == TODAY_IDS + ["channels"]
    channels = tabs[-1]
    assert set(channels) == {"id", "title", "heading", "sections", "subtabs"}
    assert channels["title"] == CHANNELS_TITLE
    assert channels["heading"] == CHANNELS_HEADING
    # <slug>: lowercase, runs outside [a-z0-9] -> "-", stripped ("__Spindle.Load__ (left)" -> "spindle-load-left")
    assert sorted(channels["sections"]) == sorted(f"channel-{SLUGS[name]}" for name in CHANNEL_NAMES)
    assert payload["tabs"] == tabs
    json.dumps(payload["tabs"])


def test_a_channel_on_the_target_alone_shows_the_channels_tab():
    Signal = ready()
    payload = analyze_comparison(channels_comparison(Signal, target_only=True))
    assert tab_ids(payload) == TODAY_IDS + ["channels"]
    assert payload["tabs"][-1]["sections"] == ["channel-grip-force"]


def test_without_channels_the_tabs_are_todays():
    """Pins today's behaviour: no channel anywhere, no channels tab (passes before and after C1)."""
    for current in (True, False):
        payload = analyze_comparison(channels_comparison(None, channels=False, current=current))
        assert [tab["id"] for tab in tabs_for(payload)] == TODAY_IDS
        assert tab_ids(payload) == TODAY_IDS


# ── the HTML run view, measured in headless Chrome ───────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const CLICK = { timeout: 3000 };

function snapshot(colours) {
  const rect = (el) => {
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return { x: box.x, y: box.y, w: box.width, h: box.height };
  };
  const visible = (el) => { const box = el.getBoundingClientRect(); return box.width > 0 && box.height > 0; };
  const text = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();
  function colourCounts(canvas) {
    const counts = {};
    Object.keys(colours).forEach((name) => { counts[name] = 0; });
    let data;
    try { data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data; }
    catch (error) { return { error: String(error) }; }
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 120) continue;
      for (const name of Object.keys(colours)) {
        const c = colours[name];
        if (Math.abs(data[i] - c[0]) <= 40 && Math.abs(data[i + 1] - c[1]) <= 40 && Math.abs(data[i + 2] - c[2]) <= 40) counts[name] += 1;
      }
    }
    return counts;
  }
  const strip = document.querySelector('[data-tc-tabs]');
  const buttons = strip ? [...strip.querySelectorAll('[data-tc-tab]')].map((button) => ({
    id: button.getAttribute('data-tc-tab'), text: text(button), selected: button.getAttribute('aria-selected'),
  })) : null;
  const panels = [...document.querySelectorAll('[data-tc-panel]')].map((panel) => {
    const heading = panel.querySelector('[data-tc-tab-heading]');
    return { id: panel.getAttribute('data-tc-panel'), rect: rect(panel), heading: heading ? text(heading) : null,
             headingRect: rect(heading) };
  });
  const channelsPanel = document.querySelector('[data-tc-panel="channels"]');
  const sections = [...document.querySelectorAll('[data-tc-section]')]
    .filter((section) => (section.getAttribute('data-tc-section') || '').indexOf('channel-') === 0)
    .map((section) => {
      const canvases = [...section.querySelectorAll('canvas')].filter(visible);
      return {
        id: section.getAttribute('data-tc-section'),
        inPanel: !!channelsPanel && channelsPanel.contains(section),
        rect: rect(section),
        titles: [...section.querySelectorAll('.ptitle')].filter(visible).map(text),
        plots: canvases.length,
        text: section.textContent || '',
        colours: canvases.map(colourCounts),
      };
    });
  const signalsPanel = document.querySelector('[data-tc-panel="signals"]');
  const current = document.querySelector('[data-tc-section="joint-current"]');
  return {
    buttons, panels, sections,
    current: current ? {
      rect: rect(current),
      inSignals: !!signalsPanel && signalsPanel.contains(current),
      rows: [...current.querySelectorAll('[data-tc-joint]')].filter(visible).map((row) => ({
        joint: row.getAttribute('data-tc-joint'), rect: rect(row),
        plots: [...row.querySelectorAll('canvas')].filter(visible).length,
        titles: [...row.querySelectorAll('.ptitle')].filter(visible).map(text),
      })),
    } : null,
  };
}

async function settle(page) {
  try {
    await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages.length && TrajCompare.state.pages[0].builtPage,
                               null, { timeout: 20000 });
  } catch (error) { /* a renamed internal: fall back on time */ }
  await page.waitForTimeout(700);
}

async function open(browser, url, errors) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(url);
  await settle(page);
  return { context, page };
}

async function attempt(record, key, step) {
  try { record[key] = await step(); } catch (error) { record[key] = { error: String(error).split('\n')[0] }; }
}

// WHY scroll each section into view: a plot built lazily on scroll is measured once it would be seen
async function scrollChannelSections(page) {
  const ids = await page.evaluate(() => [...document.querySelectorAll('[data-tc-section]')]
    .map((section) => section.getAttribute('data-tc-section') || '').filter((id) => id.indexOf('channel-') === 0));
  for (const id of ids) {
    await page.evaluate((id) => {
      const section = document.querySelector('[data-tc-section="' + id + '"]');
      if (section) section.scrollIntoView({ block: 'center' });
    }, id);
    await page.waitForTimeout(150);
  }
}

// WHY one sub-tab at a time (2026-11-25): a tab of several sections shows one fixed graph per sub-tab (tabs.SubTab), so
// each channel section is measured with its own sub-tab open and the snapshots are merged
async function openTab(page, id, colours) {
  await page.click('[data-tc-tabs] [data-tc-tab="' + id + '"]', CLICK);
  await page.waitForTimeout(500);
  if (id !== 'channels') return await page.evaluate(snapshot, colours);
  const subs = await page.evaluate(() => [...document.querySelectorAll('[data-tc-panel="channels"] [data-tc-subtab]')]
    .map((button) => button.getAttribute('data-tc-subtab')));
  if (!subs.length) {
    await scrollChannelSections(page);
    return await page.evaluate(snapshot, colours);
  }
  let merged = null;
  for (const sub of subs) {
    await page.click('[data-tc-panel="channels"] [data-tc-subtab="' + sub + '"]', CLICK);
    await page.waitForTimeout(300);
    await scrollChannelSections(page);
    const snap = await page.evaluate(snapshot, colours);
    if (!merged) { merged = snap; continue; }
    merged.sections = merged.sections.map((section) => section.id === sub
      ? (snap.sections.filter((other) => other.id === sub)[0] || section) : section);
  }
  return merged;
}

async function comparisonJob(browser, job, errors) {
  const out = {};
  let { context, page } = await open(browser, 'file://' + job.report, errors);
  out.initial = await page.evaluate(snapshot, job.colours);
  await attempt(out, 'channels', () => openTab(page, 'channels', job.colours));
  await context.close();
  ({ context, page } = await open(browser, 'file://' + job.report + '#tab=channels', errors));
  out.hash = await page.evaluate(snapshot, job.colours);
  await context.close();
  return out;
}

async function drillJob(browser, job, errors) {
  const out = {};
  const { context, page } = await open(browser, 'file://' + job.report, errors);
  out.initial = await page.evaluate(snapshot, job.colours);
  await attempt(out, 'signals', async () => {
    let snap = await openTab(page, 'signals', job.colours);
    const shown = snap.current && snap.current.rect.w > 0 && snap.current.rect.h > 0;
    if (!shown) {  // a section on its own sub-tab (2026-11-25: "Current"): open it
      const chip = page.locator('[data-tc-panel="signals"] [data-tc-subtab="current"]').first();
      if (await chip.count()) {
        await chip.click(CLICK);
        await page.waitForTimeout(600);
        snap = await page.evaluate(snapshot, job.colours);
      }
    }
    return snap;
  });
  await attempt(out, 'channels', () => openTab(page, 'channels', job.colours));
  await context.close();
  return out;
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const results = {};
  try {
    for (const job of jobs) {
      const errors = [];
      try {
        results[job.name] = job.kind === 'comparison' ? await comparisonJob(browser, job, errors) : await drillJob(browser, job, errors);
      } catch (error) {
        results[job.name] = { crashed: String(error) };
      }
      results[job.name].errors = errors;
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(results));
})();
"""


def _rgb(color: str) -> list[int]:
    color = color.lstrip("#")
    return [int(color[index : index + 2], 16) for index in (0, 2, 4)]


def _drive(workspace: Path) -> dict[str, dict]:
    """Every report this file looks at, driven once in one headless Chrome: ``{job: measurements}``.

    A report that cannot be built today is recorded as ``{"failed": why}``, so its tests fail with that reason."""
    root = workspace / "browser"
    root.mkdir(exist_ok=True)
    jobs: list[dict] = []
    results: dict[str, dict] = {}

    def prepare(name: str, build: Callable[[], dict]) -> None:
        try:
            jobs.append({"name": name, **build()})
        except Exception as error:  # noqa: BLE001 - reported by every test of that job
            results[name] = {"failed": f"{type(error).__name__}: {error}"}

    def comparison_job() -> dict:
        comparison = channels_comparison(ready())
        payload = analyze_comparison(comparison)
        _colorize(payload)
        colours = {entry["name"]: _rgb(entry["color"]) for entry in payload["situations"]}
        return {"kind": "comparison", "report": str(write_comparison_report(comparison, root / "comparison")),
                "colours": colours}  # fmt: skip

    prepare("comparison", comparison_job)
    prepare("drill-current", lambda: {"kind": "drill", "report": str(drilled(workspace, "undescribed")), "colours": {}})
    prepare("drill-signals", lambda: {"kind": "drill", "report": str(drilled(workspace, "described")), "colours": {}})
    if jobs:
        (root / "jobs.json").write_text(json.dumps(jobs))
        (root / "driver.js").write_text(DRIVER)
        result = subprocess.run(
            ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(root / "jobs.json")],
            capture_output=True, text=True, timeout=600,
        )  # fmt: skip
        assert result.returncode == 0, result.stderr[-3000:]
        results.update(json.loads(result.stdout.strip().splitlines()[-1]))
    return results


def browser_record(workspace: Path, name: str) -> dict:
    record = cached("browser", lambda: _drive(workspace))[name]
    assert "failed" not in record, f"{name}: its report could not be built: {record['failed']}"
    assert "crashed" not in record, f"{name}: the driver crashed: {record['crashed']}"
    return record


def step(record: dict, key: str) -> dict:
    assert key in record, f"{key}: never measured"
    value = record[key]
    assert "error" not in value, f"{key}: {value['error']}"
    return value


def area(rect: dict | None) -> float:
    return 0.0 if not rect else rect["w"] * rect["h"]


def strip_of(snapshot: dict) -> list[dict]:
    assert snapshot["buttons"] is not None, "no tab strip [data-tc-tabs]"
    return snapshot["buttons"]


def selected(snapshot: dict) -> list[str]:
    return [button["id"] for button in strip_of(snapshot) if button["selected"] == "true"]


def sections_of(snapshot: dict) -> dict[str, dict]:
    return {section["id"]: section for section in snapshot["sections"]}


def title_ok(title: str, accepted: tuple[str, ...]) -> bool:
    return any(title == spelling or title.startswith(spelling + " · ") for spelling in accepted)


def check_titles(section: dict, expected: list[tuple[str, ...]], name: str) -> None:
    assert section["plots"] == len(expected), f"{name}: {section['plots']} plots drawn, expected {len(expected)} (one per column)"
    assert len(section["titles"]) == len(expected), f"{name}: plot titles {section['titles']}"
    for title, accepted in zip(section["titles"], expected, strict=True):
        assert title_ok(title, accepted), f"{name}: plot titled {title!r}, expected {' or '.join(map(repr, accepted))}"


@needs_browser
def test_html_the_channels_tab_is_titled_exactly_and_follows_signals(workspace):
    record = browser_record(workspace, "comparison")
    buttons = strip_of(record["initial"])
    assert [button["id"] for button in buttons] == TODAY_IDS + ["channels"]
    assert [button["text"] for button in buttons] == TODAY_TITLES + [CHANNELS_TITLE]


@needs_browser
def test_html_the_channels_tab_shows_only_its_panel_under_its_exact_heading(workspace):
    snapshot = step(browser_record(workspace, "comparison"), "channels")
    assert selected(snapshot) == ["channels"]
    panels = {panel["id"]: panel for panel in snapshot["panels"]}
    assert "channels" in panels, f'no [data-tc-panel="channels"]; panels: {sorted(panels)}'
    panel = panels["channels"]
    assert panel["heading"] == CHANNELS_HEADING, f"heading {panel['heading']!r}"
    assert area(panel["rect"]) > 0 and area(panel["headingRect"]) > 0
    assert panel["rect"]["h"] > panel["headingRect"]["h"] + 100, "the channels panel shows nothing under its heading"
    shown = [other["id"] for other in snapshot["panels"] if other["id"] != "channels" and area(other["rect"]) > 0]
    assert shown == [], f"other panels still visible: {shown}"


@needs_browser
def test_html_every_channel_has_a_visible_section_in_the_channels_tab(workspace):
    sections = sections_of(step(browser_record(workspace, "comparison"), "channels"))
    assert set(sections) == {f"channel-{SLUGS[name]}" for name in CHANNEL_NAMES}
    for section_id, section in sections.items():
        assert section["inPanel"], f'{section_id} is not inside [data-tc-panel="channels"]'
        assert area(section["rect"]) > 0, f"{section_id} is not visible when the tab opens"
        assert section["plots"] >= 1, f"{section_id} draws no plot"


@needs_browser
def test_html_described_channels_are_titled_by_signal_column_and_unit(workspace):
    sections = sections_of(step(browser_record(workspace, "comparison"), "channels"))
    for name in DESCRIBED:  # Grip force [N]; Contact force, x [N]; Winding temperature, shoulder [°C] (joint order)
        section_id = f"channel-{SLUGS[name]}"
        assert section_id in sections, f"no {section_id}; sections: {sorted(sections)}"
        check_titles(sections[section_id], EXPECTED_PLOT_TITLES[name], name)


@needs_browser
def test_html_an_undescribed_channel_is_drawn_under_its_own_name_without_brackets(workspace):
    sections = sections_of(step(browser_record(workspace, "comparison"), "channels"))
    for name in ("contact_force_n", SPINDLE):  # never renamed, never dropped, never "contact_force_n []"
        section_id = f"channel-{SLUGS[name]}"
        assert section_id in sections, f"no {section_id}; sections: {sorted(sections)}"
        check_titles(sections[section_id], EXPECTED_PLOT_TITLES[name], name)
        assert "[]" not in sections[section_id]["text"], f"{name}: a missing unit drew empty brackets"


@needs_browser
def test_html_each_situation_with_a_channel_is_drawn_in_its_colour(workspace):
    sections = sections_of(step(browser_record(workspace, "comparison"), "channels"))
    grip = sections.get(f"channel-{SLUGS['grip_force']}")
    assert grip and grip["colours"], "no grip_force plot"
    counts = grip["colours"][0]
    assert "error" not in counts, counts
    for situation in CARRIERS:  # the target (its own grey), sim and real all record grip_force
        assert counts[situation] >= MIN_PIXELS, f"grip_force: {situation} is not drawn in its colour: {counts}"
    only_real = sections.get(f"channel-{SLUGS['contact_force_n']}")
    assert only_real and only_real["colours"], "no contact_force_n plot"
    for counts in only_real["colours"]:  # recorded by real alone: sim has nothing to draw there
        assert counts["real"] >= MIN_PIXELS and counts["sim"] <= 3, f"contact_force_n: {counts}"


@needs_browser
def test_html_hash_tab_channels_opens_the_channels_tab(workspace):
    snapshot = browser_record(workspace, "comparison")["hash"]
    assert selected(snapshot) == ["channels"]


@needs_browser
@pytest.mark.parametrize("job", ["comparison", "drill-current", "drill-signals"])
def test_html_no_console_errors(workspace, job):
    record = browser_record(workspace, job)
    assert strip_of(record["initial"])  # a page that never built its tabs cannot count as error-free
    assert record["errors"] == []


# ── Rerun ────────────────────────────────────────────────────────────────────


def _names(container) -> list:
    return [getattr(child, "name", None) for child in container.contents]


def _find_tabs(container) -> list:
    found = [container] if type(container).__name__ == "Tabs" else []
    for child in getattr(container, "contents", None) or []:
        found += _find_tabs(child)
    return found


def _views(container, kind: str) -> list:
    found = [container] if type(container).__name__ == kind else []
    for child in getattr(container, "contents", None) or []:
        if hasattr(child, "contents") or hasattr(child, "origin"):
            found += _views(child, kind)
    return found


def rerun_payload(comparison: Comparison) -> dict:
    payload = analyze_comparison(comparison)
    _colorize(payload)
    return payload


def questions(payload: dict, **kwargs):
    """The outermost Tabs of the questions layout."""
    from traj_compare.rerun_export import layout_blueprint

    return _find_tabs(layout_blueprint("questions", payload, {}, **kwargs).root_container)[0]


def child_named(container, name: str):
    matches = [child for child in container.contents if getattr(child, "name", None) == name]
    assert matches, f"no {name!r} under {getattr(container, 'name', None)!r}; children: {_names(container)}"
    return matches[0]


def motor_current_views(payload: dict) -> list:
    signals = child_named(questions(payload), SIGNALS_TITLE)
    subs = [child for tabs in _find_tabs(signals) for child in tabs.contents if getattr(child, "name", None) == MOTOR_CURRENT]
    nested = [_names(tabs) for tabs in _find_tabs(signals)]
    assert subs, f"no {MOTOR_CURRENT!r} sub-tab in the signals tab; nested tabs: {nested}"
    return _views(subs[0], "TimeSeriesView")


def scalars_by_entity(path: Path, prefix: str = "/") -> dict[str, np.ndarray]:
    """Entity path -> its logged scalars in time order, read with Rerun's own RrdReader (never our writer)."""
    import pyarrow as pa
    from rerun.chunk import RrdReader

    rows: dict[str, list[tuple[int, float]]] = {}
    for chunk in RrdReader(path).stream():
        entity = str(chunk.entity_path)
        if not entity.startswith(prefix):
            continue
        batch = chunk.to_record_batch()
        names = batch.schema.names
        if "Scalars:scalars" not in names:
            continue
        values = batch.column(names.index("Scalars:scalars")).to_pylist()
        times = batch.column(names.index("t")).cast(pa.int64()).to_pylist() if "t" in names else list(range(len(values)))
        for time, value in zip(times, values, strict=True):
            if value:
                rows.setdefault(entity, []).append((time, float(value[0])))
    return {entity: np.array([value for _, value in sorted(pairs)]) for entity, pairs in rows.items()}


def comparison_rrd(workspace: Path) -> Path:
    def build() -> Path:
        from traj_compare.rerun_export import write_rrd

        return write_rrd(channels_comparison(ready()), workspace / "rerun" / "c1-signals.rrd", layout="questions")

    return cached("rrd:comparison", build)


def drill_rrd(report: Path) -> Path:
    found = sorted((report.parent / "rerun").glob("*.rrd"))
    assert len(found) == 1, f"expected one .rrd beside {report}: {found}"
    return found[0]


def assert_logged_under(logged: dict[str, np.ndarray], origin: str, want: np.ndarray, what: str) -> None:
    under = {entity: values for entity, values in logged.items() if entity == origin or entity.startswith(origin + "/")}
    assert under, f"{what}: nothing is logged under the view's origin {origin!r}"
    matches = [entity for entity, values in under.items()
               if values.shape == want.shape and np.allclose(values, want, rtol=1e-5, atol=1e-5)]  # fmt: skip
    assert matches, f"{what}: none of {sorted(under)} holds the expected values"


@needs_rerun
def test_rerun_questions_layout_has_the_channels_tab_after_signals_and_opens_it_by_id_or_title():
    Signal = ready()
    payload = rerun_payload(channels_comparison(Signal))
    assert _names(questions(payload)) == TODAY_TITLES + [CHANNELS_TITLE]
    for name in ("channels", CHANNELS_TITLE):
        assert questions(payload, tab=name).active_tab == len(TODAY_TITLES), name
    checked = channels_comparison(Signal)
    checked.situations[0].group = "camera"  # sim becomes a check run: the check tab comes after the channels tab
    names = _names(questions(rerun_payload(checked), checks={"camera": "Camera Check"}))
    assert names == TODAY_TITLES + [CHANNELS_TITLE, "Camera Check"]
    # no channel anywhere: no channels tab (the shared tabs_for rule)
    assert _names(questions(rerun_payload(channels_comparison(None, channels=False)))) == TODAY_TITLES


@needs_rerun
def test_rerun_channels_tab_has_one_view_per_channel_titled_by_signal_and_unit():
    payload = rerun_payload(channels_comparison(ready()))
    tab = child_named(questions(payload), CHANNELS_TITLE)
    views = _views(tab, "TimeSeriesView")
    assert sorted(view.name for view in views) == sorted(EXPECTED_VIEW_TITLES.values())
    by_title = {view.name: view for view in views}
    for name in CHANNEL_NAMES:
        view = by_title[EXPECTED_VIEW_TITLES[name]]
        assert str(view.origin) == f"/channels/{_part(name)}", f"{name}: the view's origin is {view.origin}"
        assert "[]" not in view.name


@needs_rerun
def test_rerun_logs_every_channel_column_of_every_situation_that_has_it(workspace):
    logged = scalars_by_entity(comparison_rrd(workspace), "/channels/")
    found: set[str] = set()
    for situation, names in CARRIERS.items():
        for name in names:
            columns = channel_values(situation, name).reshape(SAMPLES, -1)
            for column, spellings in enumerate(ENTITY_COLUMNS[name]):
                candidates = [f"/channels/{_part(name)}/{_part(spelling)}/{_part(situation)}" for spelling in spellings]
                hits = [entity for entity in candidates if entity in logged]
                assert len(hits) == 1, f"{name} column {column} of {situation}: none of {candidates} is logged"
                np.testing.assert_allclose(logged[hits[0]], columns[:, column], rtol=1e-5, atol=1e-5, err_msg=hits[0])
                found.add(hits[0])
    assert set(logged) == found, f"logged for no situation that has the channel: {sorted(set(logged) - found)}"


@needs_rerun
def test_rerun_signals_tab_gets_a_motor_current_sub_tab_only_when_a_run_has_current():
    with_current = child_named(questions(rerun_payload(channels_comparison(None, channels=False))), SIGNALS_TITLE)
    nested = [_names(tabs) for tabs in _find_tabs(with_current)]
    assert SIGNAL_SUB_TABS + [MOTOR_CURRENT] in nested, f"signals sub-tabs: {nested}"
    without = child_named(questions(rerun_payload(channels_comparison(None, channels=False, current=False))), SIGNALS_TITLE)
    assert not any(MOTOR_CURRENT in _names(tabs) for tabs in _find_tabs(without))


@needs_rerun
def test_rerun_motor_current_views_show_each_runs_current_per_joint(tmp_path):
    from traj_compare.rerun_export import write_rrd

    comparison = channels_comparison(None, channels=False)
    views = motor_current_views(rerun_payload(comparison))
    assert len(views) == len(JOINTS), f"{len(views)} motor current views for {len(JOINTS)} joints"
    logged = scalars_by_entity(write_rrd(comparison, tmp_path / "current.rrd", layout="questions"))
    for column, joint in enumerate(JOINTS):
        view = next((view for view in views if joint in view.name), None)
        assert view is not None, f"no motor current view names {joint!r}: {[view.name for view in views]}"
        assert "[A]" in view.name, view.name
        for run in ("sim", "real"):
            assert_logged_under(logged, str(view.origin), current_values(run)[:, column], f"{joint} current of {run}")


# ── the dataset path ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("label", list(BAD_CURRENT))
def test_write_dataset_report_refuses_a_current_channel_of_another_shape(tmp_path, label):
    shape = BAD_CURRENT[label]
    run = bad_current_run(shape)  # a Run takes it; the dataset write is where it is refused (never at drill-down)
    with pytest.raises(ValueError) as info:
        write_dataset_report([run], tmp_path / "bad", title="bad current")
    message = str(info.value)
    for part in (BAD_RUN, SERIES, str(shape)):
        assert part in message, f"the error must name run, series and shape; missing {part!r}: {message!r}"


def test_signals_are_stored_in_every_manifest(workspace):
    Signal = signal_class()
    out = dataset(workspace, "described")
    manifests = sorted((out / "runs").glob("*/manifest.json"))
    assert len(manifests) == 2
    for path in manifests:
        manifest = json.loads(path.read_text("utf-8"))
        assert "signals" in manifest, f"{path.parent.name}: no 'signals' in its manifest"
        stored = manifest["signals"]
        assert set(stored) == set(DESCRIBED), stored
        for name, signal in described_signals(Signal).items():
            entry = stored[name]
            assert (entry["title"], entry["unit"], list(entry["columns"]), bool(entry["per_joint"])) == (
                signal.title, signal.unit, list(signal.columns), signal.per_joint,
            ), (path.parent.name, name, entry)  # fmt: skip


def test_the_drill_down_draws_current_on_the_reference_joints(workspace):
    page = drill_page(drilled(workspace, "undescribed"))
    assert page["has_current"] is True, "the drill-down hands no current over"
    signals = next(tab for tab in page["tabs"] if tab["id"] == "signals")
    assert "joint-current" in signals["sections"], signals["sections"]
    assert page["joint_names"] == list(JOINTS)
    entry = entry_of(page, SERIES)
    plot_t = as_array(page["plot_t"])
    want = current_values(SERIES)  # the series recorded it in SERIES_JOINTS order; drawn in JOINTS order
    for column, joint in enumerate(JOINTS):
        drawn = as_array(entry["plot"]["current"][column])
        inside = np.isfinite(drawn)
        assert inside.sum() > 0.9 * drawn.size, f"{joint}: {inside.sum()} of {drawn.size} samples"
        expected = np.interp(plot_t[inside], T, want[:, column])
        np.testing.assert_allclose(drawn[inside], expected, atol=1e-4, err_msg=f"current of {joint}")


def test_the_drill_down_hands_current_over_as_situation_current(workspace, monkeypatch):
    out = dataset(workspace, "undescribed")
    runs = [s for s in captured_situations(monkeypatch, out, workspace, "undescribed") if s.name == SERIES and s.has_data]
    assert runs, "the drill-down built no situation for the series"
    for situation in runs:
        assert situation.current is not None, "Situation.current is None: channels['current'] was not handed over"
        np.testing.assert_allclose(situation.current, current_values(SERIES), atol=1e-9)  # on the reference's joints
        channels = dict(getattr(situation, "channels", None) or {})
        assert "current" not in channels, "current is Situation.current, never a channel"
        # undescribed (N, 3) winding_temp: not per joint, so its columns stay as recorded
        np.testing.assert_allclose(channels["winding_temp"], dataset_channels()["winding_temp"], atol=1e-9)


def test_the_drill_down_draws_undescribed_channels_too(workspace):
    page = drill_page(drilled(workspace, "undescribed"))
    assert tab_ids(page) == TODAY_IDS + ["channels"]
    assert set(page["tabs"][-1]["sections"]) == DRILL_CHANNELS


def test_the_drill_down_reorders_only_per_joint_channels(workspace, monkeypatch):
    out = dataset(workspace, "described")
    captured = captured_situations(monkeypatch, out, workspace, "described")
    runs = [s for s in captured if s.name == SERIES and s.has_data]
    assert runs, "the drill-down built no situation for the series"
    for situation in runs:
        channels = dict(getattr(situation, "channels", None) or {})
        assert set(channels) == {"winding_temp", "grip_force", "contact_force"}, sorted(channels)
        # per_joint: back on the reference's joints, as effort is
        np.testing.assert_allclose(channels["winding_temp"], channel_values(SERIES, "winding_temp"), atol=1e-9)
        assert np.shape(channels["grip_force"]) == (SAMPLES,)
        np.testing.assert_allclose(channels["grip_force"], channel_values(SERIES, "grip_force"), atol=1e-9)
        # x / y / z are no joints: never reordered, though there are three of each
        np.testing.assert_allclose(channels["contact_force"], channel_values(SERIES, "contact_force"), atol=1e-9)
    for situation in (s for s in captured if s.name == "reference" and s.has_data):
        assert dict(getattr(situation, "channels", None) or {}) == {}, "the reference records no channel"


def test_a_drill_down_rebuilt_in_a_fresh_process_draws_the_manifest_signals(workspace):
    report = drilled(workspace, "described")  # build_drill_down in a new interpreter: the manifest is all it has
    page = drill_page(report)
    assert tab_ids(page) == TODAY_IDS + ["channels"]
    assert set(page["tabs"][-1]["sections"]) == DRILL_CHANNELS
    html = report.read_text("utf-8")
    for title in ("Winding temperature", "Grip force", "Contact force"):
        assert title in html, f"the rebuilt report never says {title!r}: the manifest's signals did not reach it"


def test_a_dataset_without_channels_drills_down_to_todays_tabs(workspace):
    """Pins today's behaviour: no channel, no current, no ``signals``: the drill-down's tabs are today's."""
    page = drill_page(drilled(workspace, "plain"))
    assert tab_ids(page) == TODAY_IDS
    signals = next(tab for tab in page["tabs"] if tab["id"] == "signals")
    assert signals["sections"] == ["joint-q", "joint-qd", "joint-qdd", "joint-tau"]
    assert page["has_current"] is False


@needs_browser
def test_html_drill_down_draws_motor_current_one_row_per_reference_joint(workspace):
    snapshot = step(browser_record(workspace, "drill-current"), "signals")
    current = snapshot["current"]
    assert current, 'no [data-tc-section="joint-current"] in the drill-down'
    assert current["inSignals"], 'joint-current is not in the "Raw signals per joint" tab'
    assert area(current["rect"]) > 0, "joint-current never shows (not even on its Current sub-tab)"
    rows = current["rows"]
    assert [row["joint"] for row in rows] == list(JOINTS), f"rows {[row['joint'] for row in rows]}"
    for row in rows:
        assert row["plots"] >= 1, f"{row['joint']}: no plot drawn"
        assert any(row["joint"] in title and "[A]" in title for title in row["titles"]), (row["joint"], row["titles"])


@needs_browser
def test_html_drill_down_channels_are_titled_from_the_manifest_signals(workspace):
    snapshot = step(browser_record(workspace, "drill-signals"), "channels")
    assert selected(snapshot) == ["channels"]
    panel = next((panel for panel in snapshot["panels"] if panel["id"] == "channels"), None)
    assert panel and panel["heading"] == CHANNELS_HEADING
    sections = sections_of(snapshot)
    assert set(sections) == DRILL_CHANNELS
    for name in DESCRIBED:  # winding_temp: per joint, titled in the reference's joint order
        check_titles(sections[f"channel-{SLUGS[name]}"], EXPECTED_PLOT_TITLES[name], name)


@needs_rerun
def test_rerun_drill_down_shows_motor_current_on_the_reference_joints(workspace):
    report = drilled(workspace, "undescribed")
    page = drill_page(report)
    views = motor_current_views(page)
    assert len(views) == len(JOINTS), f"{len(views)} motor current views for {len(JOINTS)} joints"
    logged = scalars_by_entity(drill_rrd(report))
    for column, joint in enumerate(JOINTS):
        view = next((view for view in views if joint in view.name), None)
        assert view is not None, f"no motor current view names {joint!r}: {[view.name for view in views]}"
        assert_logged_under(logged, str(view.origin), current_values(SERIES)[:, column], f"{joint} current")


@needs_rerun
def test_rerun_drill_down_logs_channels_per_column_with_per_joint_ones_on_the_reference_joints(workspace):
    report = drilled(workspace, "described")
    logged = scalars_by_entity(drill_rrd(report), "/channels/")
    run = _part(SERIES)
    expected = {f"/channels/grip_force/value/{run}": channel_values(SERIES, "grip_force")}
    for column, joint in enumerate(JOINTS):
        expected[f"/channels/winding_temp/{_part(joint)}/{run}"] = channel_values(SERIES, "winding_temp")[:, column]
    for column, axis in enumerate("xyz"):
        expected[f"/channels/contact_force/{axis}/{run}"] = channel_values(SERIES, "contact_force")[:, column]
    assert set(logged) == set(expected), f"logged {sorted(logged)}"
    for entity, want in expected.items():
        np.testing.assert_allclose(logged[entity], want, rtol=1e-5, atol=1e-5, err_msg=entity)
    page = drill_page(report)
    views = {view.name: str(view.origin) for view in _views(child_named(questions(page), CHANNELS_TITLE), "TimeSeriesView")}
    assert views == {EXPECTED_VIEW_TITLES[name]: f"/channels/{_part(name)}" for name in DESCRIBED}
