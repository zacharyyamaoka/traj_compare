"""The torque breakdown in the dataset view (acceptance, written before the code, 2026-11-19).

Zach, daily note 2026-11-19: "of the command torque some portion of that is coming from Feedforward, and some portion
of that is coming from feedback. That right now is not being made clear to me." The run view shows it; the dataset view
could not, because the dataset ``Run`` carried no breakdown.

Contract: the addendum of docs/layout_proposals_2026-11-19/CONTRACT.md ("the torque breakdown in the dataset view") and
docs/NAVIGATION.md Part A (where it shows: the Dataset summary band's median feedback share, the League table's FB share
and drive gap, the Target "How repeatable is each config on this target?" tab's feedback torque and FB share charts).
These tests are the implementing lane's ruler: it must not edit this file.

Key names the addendum leaves open, fixed here (the contract for the implementer):

- ``payload["levels"]["has_torque_breakdown"]``: true when any line has a breakdown. With none anywhere it is false or
  absent, and no other torque key (``TORQUE_KEYS``) appears anywhere in the dataset payload: the no-torque payload is
  today's.
- ``line["torque"]``: ``None`` (or absent) for a line without a breakdown, else a dict:
  - ``fb_share``: Σ|fb| / (Σ|ff| + Σ|fb|) over every joint and sample of the line, a fraction 0..1;
  - ``joints``: ``{joint: {"fb_share": ..., "drive_gap_rms": ...}}``, the same share per joint, and the RMS of
    commanded − applied (applied = the series' ``effort``; commanded given, or derived by the two-of-three rule);
  - ``tau_fb``: the feedback torque, one list per joint in ``target["joints"]`` order on ``target["t"]`` (the target's
    display grid), N·m, null outside the line's samples;
  - ``fb_share_over_time``: the FB share over time, the same layout, fractions 0..1 (±150 ms window, denominator
    floored so a parked joint does not read 100 %).
- ``target["has_torque_breakdown"]``: true when any of the target's lines has one; the repeat tab draws its feedback
  torque and FB share charts only then.
- ``config["fb_share_median"]``: the summary band's median feedback share, the median of the config's lines' overall
  ``fb_share`` across every target, over the lines that have one (its real lines when it has any, as the band's RMS
  median); ``None`` (or absent) for a config without a breakdown; absent from every config when no line has one.
- ``runs/<slug>/<series>.torques.npz`` names its series as ``<series>.npz`` does (``real`` -> ``real.torques.npz``).

The League table's FB share and drive gap per target x config are drawn from those lines' ``torque``; a row whose lines
have none says "—". The dispatcher checks the pixels in a browser; these tests pin the data the page draws from.

The data: a 2-joint arm (shoulder, elbow), two targets. On "probe", "v1 nominal" has 3 real lines without a breakdown and
"v2 calibrated" 3 real lines with one (two given as ff + fb, one as commanded + ff, so the feedback is derived). On
"swing", one line of each config, neither with a breakdown. The shoulder's feedback flips sign and steps at 1.5 s; the
elbow is parked from 1 s to 2 s (no feedforward, a hair of feedback), the case the floored denominator is for.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dataset_torques.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, build_drill_down, write_dataset_report

JOINTS = ("shoulder", "elbow")
SAMPLE_S = 0.01
T = np.round(np.arange(301) * SAMPLE_S, 6)  # 3 s at 100 Hz; the default display_hz (50) picks every other sample

TARGET_TAG = "target"
CONFIG_TAG = "ff_model"
BASELINE = "v1 nominal"  # first config: no breakdown
CALIBRATED = "v2 calibrated"  # has a breakdown on "probe"
SERIES = "real"

SWITCH_S = 1.5  # the shoulder's feedback steps (and flips sign) here
PARKED = (1.0, 2.0)  # the elbow is parked: no feedforward, a hair of feedback
CLEAR_S = 0.2  # > the ±150 ms window: grid instants this far from a step see one regime only

TORQUE_KEYS = frozenset(
    {"torque", "torques", "fb_share", "fb_share_median", "fb_share_over_time", "tau_fb", "tau_ff", "tau_cmd",
     "drive_gap_rms", "torque_budget"}
)  # fmt: skip


@dataclass(frozen=True)
class Plan:
    name: str
    target: str
    config: str
    given: tuple[str, ...] = ()  # which of tau_cmd / tau_ff / tau_fb the run carries
    feedback_scale: float = 1.0


# Interleaved targets and configs, so neither run order nor position decides a group.
PLAN = (
    Plan("probe v1 rep 1", "probe", BASELINE),
    Plan("probe v2 rep 1", "probe", CALIBRATED, ("tau_ff", "tau_fb"), 1.0),
    Plan("swing v1 rep 1", "swing", BASELINE),
    Plan("probe v1 rep 2", "probe", BASELINE),
    Plan("probe v2 rep 2", "probe", CALIBRATED, ("tau_ff", "tau_fb"), 0.6),
    Plan("swing v2 rep 1", "swing", CALIBRATED),
    Plan("probe v1 rep 3", "probe", BASELINE),
    Plan("probe v2 rep 3", "probe", CALIBRATED, ("tau_cmd", "tau_ff"), 1.4),  # feedback derived: cmd − ff
)
WITH_BREAKDOWN = [plan for plan in PLAN if plan.given]


def _reference_positions(target: str, t: np.ndarray) -> np.ndarray:
    phase = 2.0 * np.pi * t / 3.0
    if target == "probe":
        return np.column_stack([0.6 * (1.0 - np.cos(phase)), 0.4 + 0.3 * np.sin(phase)])
    return np.column_stack([0.7 * np.sin(phase / 2.0) ** 2, -0.2 + 0.5 * np.sin(phase / 2.0)])


def _parked() -> np.ndarray:
    return (T >= PARKED[0]) & (T < PARKED[1])


def feedforward() -> np.ndarray:
    shoulder = 1.5 + 0.5 * np.sin(2.0 * np.pi * T / 3.0)  # 1..2 N·m, never near zero
    elbow = np.where(_parked(), 0.0, 0.8)
    return np.column_stack([shoulder, elbow])


def feedback(scale: float) -> np.ndarray:
    ff = feedforward()
    # WHY a sign flip: Σ|fb| is the share, so a signed sum (fb / (ff + fb)) fails here.
    shoulder_gain = np.where(T < SWITCH_S, 0.25, -0.6) * scale
    elbow = np.where(_parked(), 1e-4 * np.sin(2.0 * np.pi * 3.0 * T), 0.2 * scale * ff[:, 1])
    return np.column_stack([shoulder_gain * ff[:, 0], elbow])


@dataclass(frozen=True)
class Truth:
    """What a line's breakdown is, computed here from the arrays (the oracle the payload is held to)."""

    ff: np.ndarray
    fb: np.ndarray
    cmd: np.ndarray
    applied: np.ndarray
    given: dict[str, np.ndarray]


def truth(plan: Plan) -> Truth:
    ff, fb = feedforward(), feedback(plan.feedback_scale)
    cmd = ff + fb
    applied = 0.92 * cmd - 0.01  # the drive delivers a little less than asked
    every = {"tau_cmd": cmd, "tau_ff": ff, "tau_fb": fb}
    return Truth(ff=ff, fb=fb, cmd=cmd, applied=applied, given={key: every[key] for key in plan.given})


def build_runs(*, torques: bool = True, empty_torques: bool = False) -> list[Run]:
    """PLAN's Runs. ``torques=False`` drops every breakdown; ``empty_torques`` then passes ``torques={}`` explicitly."""
    rng = np.random.default_rng(20261119)
    references = {
        key: JointTrajectory(t=T, joint_names=JOINTS, positions=_reference_positions(key, T)) for key in ("probe", "swing")
    }
    runs = []
    for plan in PLAN:
        lag_s = rng.uniform(0.008, 0.016)
        bias = rng.uniform(-0.002, 0.002, size=len(JOINTS))
        parts = truth(plan)
        measured = JointTrajectory(
            t=T, joint_names=JOINTS, positions=_reference_positions(plan.target, T - lag_s) + bias, effort=parts.applied
        )
        extra = {}
        if torques and plan.given:
            extra["torques"] = {SERIES: dict(parts.given)}
        elif empty_torques:
            extra["torques"] = {}
        runs.append(
            Run(
                name=plan.name,
                reference=references[plan.target],
                measured={SERIES: measured},
                tags={TARGET_TAG: plan.target, CONFIG_TAG: plan.config},
                title=plan.target,
                **extra,
            )
        )
    return runs


# ── writing each dataset once per module ─────────────────────────────────────
# WHY a cache, not a fixture: a missing feature then fails each test with its own traceback, not as setup errors.

_WRITTEN: dict[str, Path] = {}


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("dataset_torques")


def written(workspace: Path, name: str) -> Path:
    if name not in _WRITTEN:
        runs = {
            "mixed": lambda: build_runs(),
            "bare": lambda: build_runs(torques=False),
            "empty": lambda: build_runs(torques=False, empty_torques=True),
        }[name]()
        out = workspace / name
        write_dataset_report(runs, out, title=f"Torques ({name})", group_by=(TARGET_TAG, CONFIG_TAG))
        _WRITTEN[name] = out
    return _WRITTEN[name]


def dataset_payload(out: Path) -> dict:
    html = (out / "index.html").read_text("utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-dataset">(.*?)</script>', html, re.S)
    assert match, "index.html has no dataset payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


def levels_of(out: Path) -> dict:
    return dataset_payload(out)["levels"]


def line_of(levels: dict, plan: Plan) -> dict:
    wanted = f"{plan.name} · {SERIES}"
    found = [line for line in levels["lines"] if line["id"] == wanted]
    assert len(found) == 1, f"{wanted}: {[line['id'] for line in levels['lines']]}"
    return found[0]


def target_of(levels: dict, key: str) -> dict:
    return next(target for target in levels["targets"] if target["key"] == key)


def config_of(levels: dict, name: str) -> dict:
    return next(config for config in levels["configs"] if config["name"] == name)


def run_folder(out: Path, run_name: str) -> Path:
    for manifest in (out / "runs").glob("*/manifest.json"):
        if json.loads(manifest.read_text("utf-8"))["name"] == run_name:
            return manifest.parent
    raise AssertionError(f"no run folder for {run_name!r}")


def as_array(values: list) -> np.ndarray:
    return np.array([np.nan if value is None else value for value in values], dtype=float)


def overall_share(parts: Truth) -> float:
    return float(np.sum(np.abs(parts.fb)) / (np.sum(np.abs(parts.ff)) + np.sum(np.abs(parts.fb))))


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(values**2)))


def torque_keys_in(value, path: str = "") -> list[str]:
    """Every key of ``TORQUE_KEYS`` anywhere under ``value``, and any truthy ``has_torque_breakdown``."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TORQUE_KEYS or (key == "has_torque_breakdown" and item):
                found.append(f"{path}/{key}")
            found += torque_keys_in(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += torque_keys_in(item, f"{path}[{index}]")
    return found


# ── the Run model ────────────────────────────────────────────────────────────


def test_run_torques_default_to_empty_and_a_1d_torque_promotes_to_one_column():
    reference = JointTrajectory(t=T, joint_names=JOINTS, positions=_reference_positions("probe", T))
    assert Run(name="bare", reference=reference, measured={SERIES: reference}).torques == {}
    pendulum = JointTrajectory(t=T, joint_names=("pendulum",), positions=np.sin(T)[:, None])
    run = Run(name="pendulum", reference=pendulum, measured={SERIES: pendulum}, torques={SERIES: {"tau_ff": np.cos(T)}})
    assert np.shape(run.torques[SERIES]["tau_ff"]) == (T.size, 1)
    np.testing.assert_allclose(np.asarray(run.torques[SERIES]["tau_ff"])[:, 0], np.cos(T))


@pytest.mark.parametrize("series", ["sim", "reference"])
def test_run_rejects_torques_of_a_series_it_does_not_measure(series):
    reference = JointTrajectory(t=T, joint_names=JOINTS, positions=_reference_positions("probe", T))
    with pytest.raises(ValueError):
        Run(name="r", reference=reference, measured={SERIES: reference}, torques={series: {"tau_ff": feedforward()}})


@pytest.mark.parametrize("key", ["tau", "tau_xx", "feedforward"])
def test_run_rejects_an_unknown_torque_key(key):
    """Only tau_cmd / tau_ff / tau_fb: applied stays the series' effort, so even "tau" is unknown here."""
    reference = JointTrajectory(t=T, joint_names=JOINTS, positions=_reference_positions("probe", T))
    with pytest.raises(ValueError):
        Run(name="r", reference=reference, measured={SERIES: reference}, torques={SERIES: {key: feedforward()}})


@pytest.mark.parametrize(
    "shape", ["one sample short", "one joint short", "one joint extra", "1-D on two joints"]
)  # fmt: skip
def test_run_rejects_a_torque_whose_shape_does_not_match_the_series(shape):
    ff = feedforward()
    wrong = {
        "one sample short": ff[:-1],
        "one joint short": ff[:, :1],
        "one joint extra": np.column_stack([ff, ff[:, 0]]),
        "1-D on two joints": ff[:, 0],
    }[shape]
    reference = JointTrajectory(t=T, joint_names=JOINTS, positions=_reference_positions("probe", T))
    with pytest.raises(ValueError):
        Run(name="r", reference=reference, measured={SERIES: reference}, torques={SERIES: {"tau_ff": wrong}})


# ── persisted per series ─────────────────────────────────────────────────────


def test_torques_are_persisted_per_series_with_only_the_given_keys_and_listed_in_the_manifest(workspace):
    out = written(workspace, "mixed")
    for plan in PLAN:
        folder = run_folder(out, plan.name)
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        path = folder / f"{SERIES}.torques.npz"
        if not plan.given:
            assert not path.exists() and not list(folder.glob("*.torques.npz")), f"{plan.name}: a torque file without torques"
            assert manifest.get("torques", {}) == {}, f"{plan.name}: {manifest.get('torques')}"
            continue
        assert path.is_file(), f"{plan.name}: no {path.name} in {sorted(p.name for p in folder.iterdir())}"
        with np.load(path, allow_pickle=False) as stored:
            assert sorted(stored.files) == sorted(plan.given), f"{plan.name}: stored {stored.files}, given {plan.given}"
            for key, array in truth(plan).given.items():
                np.testing.assert_allclose(stored[key], array, err_msg=f"{plan.name}: {key}")
        assert set(manifest["torques"]) == {SERIES}, manifest["torques"]
        assert sorted(manifest["torques"][SERIES]) == sorted(plan.given), manifest["torques"]


# ── the drill-down reads them back ───────────────────────────────────────────


def report_payload(report: Path) -> dict:
    html = report.read_text("utf-8")
    match = re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S)
    assert match, f"{report}: no run payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


def reference_to_series(report: Path) -> dict:
    pages = report_payload(report)["comparisons"]
    found = [page for page in pages if page["name"] == f"reference--{SERIES}"]
    assert len(found) == 1, [page["name"] for page in pages]
    return found[0]


@pytest.mark.parametrize(
    ("run_name", "derived", "check"),
    [("probe v2 rep 1", "tau_cmd", "cmd"), ("probe v2 rep 3", "tau_fb", "fb")],
)  # fmt: skip
def test_the_drill_down_reads_the_breakdown_back_and_derives_the_third(workspace, run_name, derived, check):
    out = written(workspace, "mixed")
    page = reference_to_series(build_drill_down(out, run_name))
    assert page["has_torque_breakdown"] is True
    assert "torque" in [tab["id"] for tab in page["tabs"]], "no 'Feedforward or feedback?' tab"
    entry = next(entry for entry in page["situations"] if entry["name"] == SERIES)
    assert derived in entry["derived"], entry["derived"]
    parts = truth(next(plan for plan in PLAN if plan.name == run_name))
    plot_t = as_array(page["plot_t"])
    for key, expected in (("tau_ff", parts.ff), (derived, getattr(parts, check))):
        assert entry["plot"][key] is not None, f"{key} not drawn"
        for joint in range(len(JOINTS)):
            drawn = as_array(entry["plot"][key][joint])
            inside = np.isfinite(drawn)
            assert inside.sum() > 0.9 * drawn.size, f"{key}[{joint}]: {inside.sum()} of {drawn.size} samples"
            want = np.interp(plot_t[inside], T, expected[:, joint])
            np.testing.assert_allclose(drawn[inside], want, atol=1e-3, err_msg=f"{run_name}: {key}[{joint}]")


def test_a_drill_down_without_a_breakdown_has_no_torque_tab(workspace):
    out = written(workspace, "mixed")
    page = reference_to_series(build_drill_down(out, "probe v1 rep 1"))
    assert page["has_torque_breakdown"] is False
    assert "torque" not in [tab["id"] for tab in page["tabs"]]
    entry = next(entry for entry in page["situations"] if entry["name"] == SERIES)
    assert all(entry["plot"].get(key) is None for key in ("tau_cmd", "tau_ff", "tau_fb")), entry["plot"].keys()


# ── per line, in the levels payload ──────────────────────────────────────────


def test_a_line_with_a_breakdown_carries_its_fb_share_overall_and_per_joint(workspace):
    levels = levels_of(written(workspace, "mixed"))
    assert levels.get("has_torque_breakdown") is True
    for plan in WITH_BREAKDOWN:
        parts, torque = truth(plan), line_of(levels, plan).get("torque")
        assert torque, f"{plan.name}: no line['torque']"
        assert torque["fb_share"] == pytest.approx(overall_share(parts), rel=1e-3, abs=1e-4), plan.name
        assert set(torque["joints"]) == set(JOINTS), torque["joints"]
        for column, joint in enumerate(JOINTS):
            fb, ff = np.abs(parts.fb[:, column]), np.abs(parts.ff[:, column])
            share = float(fb.sum() / (ff.sum() + fb.sum()))
            assert torque["joints"][joint]["fb_share"] == pytest.approx(share, rel=1e-3, abs=1e-4), (plan.name, joint)


def test_a_lines_drive_gap_is_the_rms_of_commanded_minus_applied_per_joint(workspace):
    levels = levels_of(written(workspace, "mixed"))
    for plan in WITH_BREAKDOWN:
        parts, torque = truth(plan), line_of(levels, plan).get("torque")
        assert torque, f"{plan.name}: no line['torque']"
        for column, joint in enumerate(JOINTS):
            gap = rms(parts.cmd[:, column] - parts.applied[:, column])
            assert torque["joints"][joint]["drive_gap_rms"] == pytest.approx(gap, rel=1e-3, abs=1e-4), (plan.name, joint)


def test_the_feedback_torque_display_series_is_on_the_target_grid(workspace):
    levels = levels_of(written(workspace, "mixed"))
    target = target_of(levels, "probe")
    grid = as_array(target["t"])
    assert grid.size < T.size, "the display grid is the reference picked at display_hz"
    assert target["joints"] == list(JOINTS)
    for plan in WITH_BREAKDOWN:
        parts, torque = truth(plan), line_of(levels, plan).get("torque")
        assert torque, f"{plan.name}: no line['torque']"
        assert len(torque["tau_fb"]) == len(JOINTS)
        for column in range(len(JOINTS)):
            drawn = as_array(torque["tau_fb"][column])
            assert drawn.size == grid.size, (plan.name, column, drawn.size, grid.size)
            np.testing.assert_allclose(drawn, np.interp(grid, T, parts.fb[:, column]), atol=1e-3, err_msg=plan.name)


def test_fb_share_over_time_follows_the_local_share_and_stays_low_where_a_joint_is_parked(workspace):
    """Away from a step, any ±150 ms window sees one regime, so the share there is |fb| / (|ff| + |fb|) at that instant.
    Where the elbow is parked (no feedforward, |fb| ~ 1e-4 N·m) an unfloored ratio reads 100 %; floored, it stays low."""
    levels = levels_of(written(workspace, "mixed"))
    grid = as_array(target_of(levels, "probe")["t"])
    shoulder_clear = np.abs(grid - SWITCH_S) > CLEAR_S
    elbow_clear = (grid < PARKED[0] - CLEAR_S) | (grid > PARKED[1] + CLEAR_S)
    elbow_parked = (grid > PARKED[0] + CLEAR_S) & (grid < PARKED[1] - CLEAR_S)
    for plan in WITH_BREAKDOWN:
        parts, torque = truth(plan), line_of(levels, plan).get("torque")
        assert torque, f"{plan.name}: no line['torque']"
        series = [as_array(values) for values in torque["fb_share_over_time"]]
        assert len(series) == len(JOINTS) and all(values.size == grid.size for values in series), plan.name
        for values in series:
            finite = values[np.isfinite(values)]
            assert finite.size and finite.min() >= -1e-9 and finite.max() <= 1.0 + 1e-9, f"{plan.name}: not a fraction"
        with np.errstate(invalid="ignore", divide="ignore"):  # 0/0 only inside the parked stretch, never compared
            local = [
                np.interp(grid, T, np.abs(parts.fb[:, column]) / (np.abs(parts.ff[:, column]) + np.abs(parts.fb[:, column])))
                for column in range(len(JOINTS))
            ]
        np.testing.assert_allclose(series[0][shoulder_clear], local[0][shoulder_clear], atol=0.01, err_msg=plan.name)
        np.testing.assert_allclose(series[1][elbow_clear], local[1][elbow_clear], atol=0.01, err_msg=plan.name)
        assert np.nanmax(series[1][elbow_parked]) < 0.5, f"{plan.name}: the parked elbow reads {np.nanmax(series[1][elbow_parked])}"


def test_a_line_target_or_config_without_a_breakdown_carries_nothing_for_it(workspace):
    levels = levels_of(written(workspace, "mixed"))
    for plan in PLAN:
        if not plan.given:
            assert line_of(levels, plan).get("torque") is None, plan.name
    assert target_of(levels, "probe").get("has_torque_breakdown") is True
    assert target_of(levels, "swing").get("has_torque_breakdown", False) is False, "swing has no breakdown: no torque charts"


# ── the page surfaces ────────────────────────────────────────────────────────


def test_the_summary_band_carries_a_median_feedback_share_per_config(workspace):
    levels = levels_of(written(workspace, "mixed"))
    expected = float(np.median([overall_share(truth(plan)) for plan in WITH_BREAKDOWN]))
    assert config_of(levels, CALIBRATED).get("fb_share_median") == pytest.approx(expected, rel=1e-3, abs=1e-4)
    assert config_of(levels, BASELINE).get("fb_share_median") is None, "a config without a breakdown has no median: '—'"


def test_the_league_table_and_the_repeat_tab_draw_the_breakdown_only_from_lines_that_have_one(workspace):
    """The League table's FB share / drive gap per target x config come from its lines: a row whose lines carry no
    ``torque`` says "—". The page's code names those columns and the repeat tab's charts (NAVIGATION.md's words)."""
    out = written(workspace, "mixed")
    levels = levels_of(out)
    rows: dict[tuple[str, str], list[dict]] = {}
    for plan in PLAN:
        rows.setdefault((plan.target, plan.config), []).append(line_of(levels, plan))
    for (target, config), lines in rows.items():
        with_one = [bool(line.get("torque")) for line in lines]
        if (target, config) == ("probe", CALIBRATED):
            assert all(with_one), f"{target} x {config}: {with_one}"
            for line in lines:
                assert all(line["torque"]["joints"][joint]["drive_gap_rms"] is not None for joint in JOINTS), line["id"]
        else:
            assert not any(with_one), f"{target} x {config} has no breakdown, so its FB share cell is '—': {with_one}"
    html = (out / "index.html").read_text("utf-8")
    for words in ("FB share", "drive gap", "feedback torque"):
        assert re.search(words, html, re.I), f"index.html never says {words!r}"
    window = r"150(?:\s|&nbsp;|&#8239;|\\u00a0|\\u202f)*ms|0\.15(?:\s|&nbsp;|\\u00a0)*s\b"
    assert re.search(window, html), "the FB share chart note states its ±150 ms window"


# ── no breakdown anywhere ────────────────────────────────────────────────────


def test_no_breakdown_anywhere_leaves_the_payload_as_the_no_torque_path(workspace):
    empty = written(workspace, "empty")  # every Run(torques={})
    bare = written(workspace, "bare")  # no torques argument at all
    payload = dataset_payload(empty)
    assert torque_keys_in(payload) == [], torque_keys_in(payload)
    assert levels_of(empty) == levels_of(bare), "torques={} changed the levels payload"
    assert not list((empty / "runs").glob("*/*.torques.npz"))
    for manifest in (empty / "runs").glob("*/manifest.json"):
        assert json.loads(manifest.read_text("utf-8")).get("torques", {}) == {}, manifest
