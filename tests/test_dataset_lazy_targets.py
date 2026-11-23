"""Config colours and per-target lazy series (acceptance, written before the code, 2026-11-20).

The contract is docs/NAVIGATION.md Part C, **C4. Config colours** and **C5. Per-level detail and the index's size**
(frozen @ 040f536). Source: the arm_motion_bench agent's UR5e site, whose index was 38 MB (line torque series 13.4 MB,
line ``e_deg`` 6.7 MB, the runs table's rows 10.9 MB), and whose four sim-only configs all came out grey. The data is
tests/lazy_targets_fixture.py. These tests are the implementing lane's ruler: it must not edit this file.

What the contract leaves open, fixed here (the implementer builds to this):

- **A target file** ``targets/<slug>.js`` is ``window.trajCompareTarget("<slug>", <JSON object>);`` (leading ``//`` or
  ``/* */`` comments allowed). The object's ``"lines"`` is a list of ``{"id": <line id>, ...}`` or a dict keyed by line
  id, holding exactly that target's lines. A line entry has ``"e_deg"`` (one list per joint, in the target's ``joints``
  order, degrees, ``null`` outside the line's samples) and, for a line with a torque breakdown, ``"torque"`` with
  ``"tau_fb"`` and ``"fb_share_over_time"`` laid out the same way (the names the index used until now). The drawn grid
  is the object's ``"t"`` when present, else the index's ``levels.targets[*].t``.
- **Picking at display_hz** is data_ui's ``_stride`` rule: the reference's samples, every ``ceil(rate / display_hz)``-th
  one, where ``rate`` is 1 / the median sample step. ``target_budget`` counts every value of every drawn series of
  every line in the file (``t`` not counted). "The stride grows until the file fits" is read as: the **smallest** stride
  at or above display_hz's at which the file fits, so a file draws as many samples as its budget allows.
- **A drawn value** may be rounded, to no coarser than 0.001 deg (tolerance below).
- **[data-tc-drawn-rate]** of a Target-level chart is the nearest one up that chart's ancestors, and that ancestor holds
  only that one chart; a card's is any inside ``[data-tc-target-card]``. Its text holds the drawn rate as ``<n> Hz``.
  Only charts over trajectory time state a rate (the history tab's control chart draws one point per line).
- **"Loads it"** = a ``<script>`` whose ``src`` ends in ``targets/<slug>.js`` is added to the page (seen by a
  MutationObserver, so a script removed after it ran still counts). "Far below the fold" = top more than ``FAR_PX``
  below the first viewport's bottom, beyond any reasonable preload margin.
- **Distinct colours**: CIE76 ΔE >= ``MIN_DELTA_E`` between any two config colours and from the torque blue and orange
  (ΔE 2.3 is a just-noticeable difference; an evenly spaced 24-hue wheel at one lightness still clears 6). **A hue, not a
  grey**: CIELAB chroma >= ``MIN_CHROMA`` (today's greys are 1.9-3.4, the slate ``#6b7a8f`` 13). "Takes the next named
  hue in config order" is read as: the configs that take a hue take the same sequence an all-real dataset's configs do,
  in config order, the twin grey taking none of it.

Tests that pass on 040f536 pin behaviour C4 / C5 keep, and say so: colours ``[1-real]``, ``[4-real]``,
``[twin-1-sim-3-real]`` (real configs take violet, green, ...; the twin's sim config is grey), a non-positive
``display_hz`` raising ``ValueError``, Open in Rerun offering the row's full command, and no console errors.

Charts are measured on the page through every ``uPlot`` the page creates (the constructor is wrapped before the page's
scripts run): canvas size, number of data series with any finite value, number of x points. A spatial or drawn claim is
measured, never inferred from DOM presence. One headless Chrome run (``pages`` fixture) opens every page over file://
and over http (``traj_compare.serve``'s handler, on a free port, started and stopped here); each test checks its part.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``) for the browser tests; those are skipped otherwise. Run:

    cd /home/bam/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dataset_lazy_targets.py
"""

from __future__ import annotations

import contextlib
import inspect
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
from lazy_targets_fixture import (
    BIG,
    BIG_LINES,
    BIG_TORQUE_LINES,
    BROWSER_JOINTS,
    BUDGET,
    BUDGET_FITS,
    BUDGET_STRIDED,
    CONFIG_TAG,
    SIZE_JOINTS,
    TARGET_TAG,
    browser_plans,
    budget_plans,
    build_runs,
    colour_configs,
    colour_plans,
    files_plans,
    line_id,
    size_plans,
)
from robot_msgs.compare import compare

from traj_compare import Run, write_dataset_report
from traj_compare.rerun_export import viewer_command
from traj_compare.serve import make_handler

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

DEFAULT_DISPLAY_HZ = 50.0
DRAWN_TOLERANCE_DEG = 1e-3
TWIN_GREY = "#5f5e5a"
TORQUE_BLUE = "#2a78d6"
TORQUE_ORANGE = "#eb6834"
MIN_DELTA_E = 5.0
MIN_CHROMA = 10.0
FAR_PX = 1500
# WHY 4 KB per line (6 joints): a scalars-only line is O(joints) numbers. Measured on 040f536 for the size dataset: today's
# payload rewritten with every line series and rerun_command dropped and everything else kept (the runs-table rows, the
# runs, the target rows and their display grid) is 3.06 KB per line; without the target's display grid, ~2.0 KB. One
# joint's error alone at 50 Hz over 20 s is 1001 values, ~7 KB, and a line has 6: a budget of 4 KB admits every scalar
# and no line series. Context only, never the ruler: today's index of this dataset is ~25 MB, ~82 KB per line.
PER_LINE_BUDGET = 4096
# serve_command names the folder once; the runs table's command template (drill <folder> ... && rerun <folder>/...) at
# most twice more. Today each row repeats it twice (rerun_command): 29 for the files dataset's 14 rows.
FOLDER_MENTIONS = 4


# ── writing each dataset once per module ─────────────────────────────────────
# WHY a cache, not a fixture: a missing feature then fails each test with its own traceback, not as a setup error.

_WRITTEN: dict[str, tuple[Path, list[Run]]] = {}


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("lazy_targets")


def written(workspace: Path, name: str) -> tuple[Path, list[Run]]:
    """The dataset ``name`` written once into ``workspace``, and its runs."""
    if name not in _WRITTEN:
        builders = {
            "files": lambda: (build_runs(files_plans()), {}),
            "files_40": lambda: (build_runs(files_plans()), {"display_hz": 40.0}),
            "budget": lambda: (build_runs(budget_plans()), {"target_budget": BUDGET}),
            # WHY no group_by here: the ISO 9283 cards' aggregates are per group and C5 leaves them as they are (1.8 KB
            # per line of this dataset grouped by target x config); the size bound measures what C5 governs.
            "size": lambda: (build_runs(size_plans()), {"group_by": (), "config_by": CONFIG_TAG}),
            "tiny": lambda: (build_runs(size_plans(1, 1)), {"group_by": (), "config_by": CONFIG_TAG}),
        }
        runs, options = builders[name]()
        options = {"group_by": (TARGET_TAG, CONFIG_TAG), **options}
        out = workspace / name
        write_dataset_report(runs, out, title=f"Lazy targets ({name})", **options)
        _WRITTEN[name] = (out, runs)
    return _WRITTEN[name]


def dataset_payload(out: Path) -> dict:
    html = (out / "index.html").read_text("utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-dataset">(.*?)</script>', html, re.S)
    assert match, "index.html has no dataset payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


_WRAPPER = re.compile(r'window\.trajCompareTarget\(\s*("(?:[^"\\]|\\.)*")\s*,\s*(.*)\)\s*;?\s*', re.S)
_LEADING_COMMENT = re.compile(r"\s*(?:/\*.*?\*/|//[^\n]*(?:\n|$))", re.S)


def read_target_file(path: Path) -> tuple[str, dict]:
    """(slug, object) of ``window.trajCompareTarget("<slug>", {...});``."""
    text = path.read_text("utf-8")
    while (comment := _LEADING_COMMENT.match(text)) and comment.end() > 0:
        text = text[comment.end() :]
    match = _WRAPPER.fullmatch(text.strip())
    assert match, f"{path.name} is not one window.trajCompareTarget(\"<slug>\", {{...}}) call: {text[:160]!r}"
    return json.loads(match.group(1)), json.loads(match.group(2))


def target_file(out: Path, slug: str) -> dict:
    path = out / "targets" / f"{slug}.js"
    assert (out / "targets").is_dir(), f"no targets/ folder beside index.html (wanted targets/{slug}.js)"
    assert path.is_file(), f"no targets/{slug}.js; targets/ holds {sorted(p.name for p in (out / 'targets').glob('*'))}"
    named, data = read_target_file(path)
    assert named == slug, f"{path.name} calls window.trajCompareTarget({named!r}, ...), not {slug!r}"
    return data


def file_lines(data: dict) -> dict[str, dict]:
    lines = data.get("lines")
    if isinstance(lines, dict):
        return lines
    assert isinstance(lines, list), f"a target file's 'lines' is a list or a dict by line id, got {type(lines).__name__}"
    return {line["id"]: line for line in lines}


def payload_target(payload: dict, key: str) -> dict:
    return next(target for target in payload["levels"]["targets"] if target["key"] == key)


def drawn_grid(data: dict, target: dict) -> np.ndarray:
    grid = data["t"] if "t" in data else target.get("t")
    assert grid is not None, f"{target['key']}: no drawn grid, neither the file's 't' nor the index's target 't'"
    return np.asarray(grid, dtype=float)


def stride_of(reference_t: np.ndarray, display_hz: float) -> tuple[int, float]:
    """data_ui's ``_stride``: (rows to step by, native rate)."""
    rate = 1.0 / float(np.median(np.diff(reference_t)))
    return max(1, math.ceil(rate / display_hz - 1e-9)), rate


def as_array(values: list) -> np.ndarray:
    return np.array([np.nan if value is None else value for value in values], dtype=float)


def runs_of(runs: list[Run], key: str) -> list[Run]:
    return [run for run in runs if run.tags[TARGET_TAG] == key]


def joint_error_deg(run: Run) -> tuple[list[str], np.ndarray]:
    """robot_msgs.compare's error target − line per joint (the oracle), degrees, on the line's own samples."""
    (measured,) = run.measured.values()
    error = compare(run.reference, measured).error
    assert np.allclose(error.t, run.reference.t), "the fixture's lines are sampled on their reference's instants"
    return list(error.joint_names), np.degrees(error.positions)


def drawn_values(entry: dict) -> int:
    """Every value of every drawn series of one line entry (numbers and nulls in its lists of lists)."""
    total = 0

    def walk(value) -> None:
        nonlocal total
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            if value and all(isinstance(item, (int, float)) or item is None for item in value):
                total += len(value)
            else:
                for item in value:
                    walk(item)

    for key, value in entry.items():
        if key != "id":
            walk(value)
    return total


def long_numeric_lists(value, path: str = "") -> list[str]:
    """Paths of every list of >= 32 numbers (a time series) under ``value``, a target's own ``t`` grid excepted."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found += long_numeric_lists(item, f"{path}/{key}")
    elif isinstance(value, list):
        numeric = all(isinstance(item, (int, float)) and not isinstance(item, bool) or item is None for item in value)
        if numeric and len(value) >= 32 and not re.fullmatch(r"/levels/targets\[\d+\]/t", path):
            found.append(f"{path} ({len(value)} values)")
        elif not numeric:
            for index, item in enumerate(value):
                found += long_numeric_lists(item, f"{path}[{index}]")
    return found


# ── colours ──────────────────────────────────────────────────────────────────


def hex_of(colour: str) -> str:
    """``#rrggbb`` (lower case) of ``#rgb`` / ``#rrggbb`` / ``rgb(r, g, b)`` / ``rgba(r, g, b, a)``."""
    colour = colour.strip().lower()
    rgb = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)", colour)
    if rgb:
        return "#" + "".join(f"{int(part):02x}" for part in rgb.groups())
    if re.fullmatch(r"#[0-9a-f]{3}", colour):
        return "#" + "".join(2 * part for part in colour[1:])
    assert re.fullmatch(r"#[0-9a-f]{6}", colour), f"not a colour: {colour!r}"
    return colour


def lab(colour: str) -> tuple[float, float, float]:
    """CIELAB (D65) of an sRGB colour."""
    value = hex_of(colour)
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    return 116.0 * f(y) - 16.0, 500.0 * (f(x) - f(y)), 200.0 * (f(y) - f(z))


def delta_e(first: str, second: str) -> float:
    return math.dist(lab(first), lab(second))


def chroma(colour: str) -> float:
    _, a, b = lab(colour)
    return math.hypot(a, b)


def colour_rule_violations(colours: dict[str, str], kinds: dict[str, str], palette: list[str] | None) -> list[str]:
    """Everything C4 forbids in one dataset's config colours (``colours`` in config order; ``kinds``: config -> "sim" for
    a config with no real line, else "real"); ``palette`` = an all-real dataset's colours in config order."""
    problems: list[str] = []
    sim_only = [name for name in colours if kinds[name] == "sim"]
    twin = len(sim_only) == 1 and len(sim_only) < len(colours)
    hues = []
    for name, colour in colours.items():
        colour = hex_of(colour)
        if twin and name == sim_only[0]:
            if colour != TWIN_GREY:
                problems.append(f"{name}: the twin case's one sim-only config is grey {TWIN_GREY}, got {colour}")
            continue
        hues.append(colour)
        if colour == TWIN_GREY or chroma(colour) < MIN_CHROMA:
            problems.append(f"{name}: {colour} is a grey (chroma {chroma(colour):.1f} < {MIN_CHROMA}); only the twin case's sim config is grey")
        for torque, label in ((TORQUE_BLUE, "torque blue"), (TORQUE_ORANGE, "torque orange")):
            if delta_e(colour, torque) < MIN_DELTA_E:
                problems.append(f"{name}: {colour} is the {label} {torque} (ΔE {delta_e(colour, torque):.1f})")
    names = list(colours)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            distance = delta_e(colours[first], colours[second])
            if distance < MIN_DELTA_E:
                problems.append(f"{first} {hex_of(colours[first])} and {second} {hex_of(colours[second])} are not distinct (ΔE {distance:.1f})")
    if palette is not None and hues != [hex_of(colour) for colour in palette[: len(hues)]]:
        problems.append(f"the hue-taking configs' colours {hues} are not the next hues in config order {palette[: len(hues)]}")
    return problems


def write_colour_dataset(out: Path, kinds: list[str]) -> dict[str, str]:
    """Write the colour fixture for ``kinds`` and return the payload's config colours in config order."""
    runs = build_runs(colour_plans(kinds))
    write_dataset_report(runs, out, title="Colours", group_by=(TARGET_TAG, CONFIG_TAG))
    configs = dataset_payload(out)["levels"]["configs"]
    assert [config["name"] for config in configs] == colour_configs(kinds), "config order is the order of first appearance"
    return {config["name"]: config["color"] for config in configs}


_PALETTE: list[list[str]] = []


def all_real_palette(workspace: Path) -> list[str]:
    """The colours an all-real dataset of 24 configs takes, in config order: the "next hue" sequence."""
    if not _PALETTE:
        _PALETTE.append(list(write_colour_dataset(workspace / "palette-24-real", ["real"] * 24).values()))
    return _PALETTE[0]


# ── C4: config colours, in the payload ───────────────────────────────────────

COLOUR_CASES = {
    "1-sim-only": ["sim"],
    "1-real": ["real"],
    "4-sim-only": ["sim"] * 4,
    "4-real": ["real"] * 4,
    "2-sim-only-2-real": ["sim", "real", "sim", "real"],
    "12-real": ["real"] * 12,
    "12-sim-only": ["sim"] * 12,
    "24-real": ["real"] * 24,
    "24-alternating": ["sim", "real"] * 12,
    "twin-1-sim-3-real": ["real", "sim", "real", "real"],
    "twin-1-sim-23-real": ["sim"] + ["real"] * 23,
}


@pytest.mark.parametrize("case", list(COLOUR_CASES))
def test_config_colours_are_distinct_hues_and_grey_only_marks_the_twin_case(workspace, case):
    kinds = COLOUR_CASES[case]
    colours = write_colour_dataset(workspace / f"colours-{case}", kinds)
    by_name = dict(zip(colour_configs(kinds), kinds, strict=True))
    assert colour_rule_violations(colours, by_name, all_real_palette(workspace)) == []


# ── C5: the index embeds scalars only ────────────────────────────────────────


def test_index_lines_keep_only_their_scalars_and_those_are_compares(workspace):
    out, runs = written(workspace, "files")
    payload = dataset_payload(out)
    lines = {line["id"]: line for line in payload["levels"]["lines"]}
    with_series = sorted(line for line, entry in lines.items() if "e_deg" in entry)
    assert with_series == [], f"{len(with_series)} index lines still embed e_deg, e.g. {with_series[:3]}"
    assert long_numeric_lists(payload) == [], "the index embeds time series"
    assert sorted(lines) == sorted(line_id(run) for run in runs)
    for run in runs:
        line = lines[line_id(run)]
        (series,) = run.measured
        comparison = compare(run.reference, run.measured[series])
        rms = {name: comparison.metrics[f"positions/{name}"].rms for name in comparison.error.joint_names}
        assert set(line["rms"]) == set(rms), line["id"]
        for name, value in rms.items():
            assert line["rms"][name] == pytest.approx(value, rel=1e-9, abs=1e-12), (line["id"], name)
        worst = max(rms, key=rms.get)
        assert line["worst_joint"] == worst and line["worst_rms"] == pytest.approx(rms[worst], rel=1e-9), line["id"]
        assert line["coverage"] == pytest.approx(comparison.coverage), line["id"]
        assert "ok" in line, f"{line['id']}: no 'ok' (null without tolerances)"
        given = run.torques.get(series)
        if not given:
            assert not line.get("torque"), f"{line['id']} has no breakdown but carries {line.get('torque')}"
            continue
        torque = line.get("torque")
        assert torque, f"{line['id']}: the torque scalars are gone from the index"
        ff, fb = np.abs(given["tau_ff"]), np.abs(given["tau_fb"])
        assert torque["fb_share"] == pytest.approx(float(fb.sum() / (ff.sum() + fb.sum())), rel=1e-6), line["id"]
        effort = run.measured[series].effort
        for column, name in enumerate(run.reference.joint_names):
            share = float(fb[:, column].sum() / (ff[:, column].sum() + fb[:, column].sum()))
            gap = float(np.sqrt(np.mean((given["tau_ff"][:, column] + given["tau_fb"][:, column] - effort[:, column]) ** 2)))
            assert torque["joints"][name]["fb_share"] == pytest.approx(share, rel=1e-6), (line["id"], name)
            assert torque["joints"][name]["drive_gap_rms"] == pytest.approx(gap, rel=1e-3), (line["id"], name)


def test_the_runs_table_rows_never_repeat_the_folder_per_row(workspace):
    out, runs = written(workspace, "files")
    html = (out / "index.html").read_text("utf-8")
    folder = str(out.resolve())
    mentions = html.count(folder)
    assert mentions <= FOLDER_MENTIONS, (
        f"index.html names the folder {mentions} times for {len(runs)} rows; build each row's command from one template"
    )


def test_index_bytes_per_line_stay_within_a_scalars_only_budget(workspace):
    big, big_runs = written(workspace, "size")
    tiny, tiny_runs = written(workspace, "tiny")
    lines = len(big_runs) - len(tiny_runs)
    per_line = ((big / "index.html").stat().st_size - (tiny / "index.html").stat().st_size) / lines
    assert per_line <= PER_LINE_BUDGET, (
        f"each line adds {per_line / 1024:.1f} KB to index.html ({len(SIZE_JOINTS)} joints); scalars only fit in "
        f"{PER_LINE_BUDGET / 1024:.0f} KB"
    )


# ── C5: one file per target ──────────────────────────────────────────────────


def test_one_target_file_per_target_calls_traj_compare_target_with_its_slug(workspace):
    out, _ = written(workspace, "files")
    assert (out / "targets").is_dir(), "no targets/ folder beside index.html"
    slugs = sorted(target["slug"] for target in dataset_payload(out)["levels"]["targets"])
    assert slugs == sorted(re.sub(r"[^a-z0-9]+", "-", plan.key).strip("-") for plan in files_plans())
    assert sorted(path.name for path in (out / "targets").glob("*.js")) == [f"{slug}.js" for slug in slugs]
    for slug in slugs:
        named, data = read_target_file(out / "targets" / f"{slug}.js")
        assert named == slug and isinstance(data, dict), slug


@pytest.mark.parametrize("dataset, display_hz", [("files", DEFAULT_DISPLAY_HZ), ("files_40", 40.0)], ids=["default-50Hz", "40Hz"])
def test_a_target_file_holds_each_lines_joint_error_picked_at_display_hz(workspace, dataset, display_hz):
    out, runs = written(workspace, dataset)
    payload = dataset_payload(out)
    for plan in files_plans():
        target = payload_target(payload, plan.key)
        data = target_file(out, target["slug"])
        members = runs_of(runs, plan.key)
        lines = file_lines(data)
        assert sorted(lines) == sorted(line_id(run) for run in members), f"{plan.key}: the file holds exactly its lines"
        reference_t = members[0].reference.t
        stride, _ = stride_of(reference_t, display_hz)
        grid = drawn_grid(data, target)
        np.testing.assert_allclose(grid, reference_t[::stride], atol=5e-5, err_msg=f"{plan.key}: picked every {stride}th sample")
        for run in members:
            joints, error = joint_error_deg(run)
            entry = lines[line_id(run)]
            assert len(entry["e_deg"]) == len(target["joints"]), line_id(run)
            for column, joint in enumerate(target["joints"]):
                drawn = as_array(entry["e_deg"][column])
                expected = error[::stride, joints.index(joint)]
                assert drawn.shape == expected.shape, (line_id(run), joint, drawn.shape, expected.shape)
                np.testing.assert_allclose(drawn, expected, atol=DRAWN_TOLERANCE_DEG, err_msg=f"{line_id(run)} {joint}")


def test_a_target_file_holds_the_torque_display_series_of_each_line_with_a_breakdown(workspace):
    out, runs = written(workspace, "files")
    payload = dataset_payload(out)
    breakdowns = 0
    for plan in files_plans():
        target = payload_target(payload, plan.key)
        data = target_file(out, target["slug"])
        lines = file_lines(data)
        grid = drawn_grid(data, target)
        for run in runs_of(runs, plan.key):
            (series,) = run.measured
            entry = lines[line_id(run)]
            given = run.torques.get(series)
            if not given:
                assert not entry.get("torque"), f"{line_id(run)} has no breakdown, so no torque series"
                continue
            breakdowns += 1
            stride, _ = stride_of(run.reference.t, DEFAULT_DISPLAY_HZ)
            torque = entry.get("torque") or {}
            assert len(torque.get("tau_fb") or []) == len(target["joints"]), f"{line_id(run)}: tau_fb per joint"
            assert len(torque.get("fb_share_over_time") or []) == len(target["joints"]), f"{line_id(run)}: FB share per joint"
            for column, joint in enumerate(target["joints"]):
                np.testing.assert_allclose(
                    as_array(torque["tau_fb"][column]), given["tau_fb"][::stride, column], atol=1e-3, err_msg=f"{line_id(run)} {joint}"
                )  # fmt: skip
                share = as_array(torque["fb_share_over_time"][column])
                assert share.shape == grid.shape, (line_id(run), joint, share.shape, grid.shape)
                finite = share[np.isfinite(share)]
                assert finite.size and finite.min() >= -1e-9 and finite.max() <= 1 + 1e-9, f"{line_id(run)} {joint}: a fraction"
    assert breakdowns == 4, "the fixture's premise: 4 lines with a torque breakdown"


def test_rewriting_with_fewer_targets_deletes_every_target_file_it_did_not_write(tmp_path):
    out = tmp_path / "stale"
    write_dataset_report(build_runs(files_plans()), out, title="Three targets", group_by=(TARGET_TAG, CONFIG_TAG))
    first = sorted(path.name for path in (out / "targets").glob("*.js"))
    assert first == ["reach.js", "swing-back.js", "wave.js"], f"the first write's target files: {first}"
    (out / "targets" / "renamed-long-ago.js").write_text('window.trajCompareTarget("renamed-long-ago", {"lines": []});\n', "utf-8")
    write_dataset_report(build_runs(files_plans(slim=True)), out, title="Two targets", group_by=(TARGET_TAG, CONFIG_TAG))
    assert sorted(path.name for path in (out / "targets").glob("*.js")) == ["reach.js", "wave.js"]


# ── C5: the rate and the budget ──────────────────────────────────────────────


def test_target_budget_is_a_keyword_defaulting_to_two_million_values():
    parameters = inspect.signature(write_dataset_report).parameters
    assert "target_budget" in parameters, f"write_dataset_report has no target_budget; it takes {list(parameters)}"
    assert parameters["target_budget"].default == 2_000_000
    assert parameters["display_hz"].default == DEFAULT_DISPLAY_HZ


def test_over_budget_a_targets_stride_grows_to_the_first_that_fits_and_another_target_keeps_display_hz(workspace):
    assert "target_budget" in inspect.signature(write_dataset_report).parameters, "write_dataset_report has no target_budget"
    out, runs = written(workspace, "budget")
    payload = dataset_payload(out)
    for key, stride in ((BUDGET_STRIDED, 10), (BUDGET_FITS, 4)):
        target = payload_target(payload, key)
        data = target_file(out, target["slug"])
        lines = file_lines(data)
        values = sum(drawn_values(entry) for entry in lines.values())
        assert values <= BUDGET, f"{key}: {values} drawn values > target_budget {BUDGET}"
        members = runs_of(runs, key)
        reference_t = members[0].reference.t
        grid = drawn_grid(data, target)
        np.testing.assert_allclose(
            grid, reference_t[::stride], atol=5e-5, err_msg=f"{key}: every {stride}th sample ({200 / stride:g} Hz)"
        )  # fmt: skip
        if key == BUDGET_STRIDED:
            one_finer = len(lines) * len(target["joints"]) * len(reference_t[:: stride - 1])
            assert one_finer > BUDGET, "the fixture's premise: stride 9 does not fit, so 10 is the first that does"
        for run in members:
            joints, error = joint_error_deg(run)
            for column, joint in enumerate(target["joints"]):
                np.testing.assert_allclose(
                    as_array(lines[line_id(run)]["e_deg"][column]), error[::stride, joints.index(joint)],
                    atol=DRAWN_TOLERANCE_DEG, err_msg=f"{line_id(run)} {joint}: picked, never averaged",
                )  # fmt: skip


@pytest.mark.parametrize("budget", [0, -1])
def test_a_non_positive_target_budget_raises_value_error(tmp_path, budget):
    with pytest.raises(ValueError, match="target_budget"):
        write_dataset_report(build_runs(budget_plans()[1:]), tmp_path, title="Budget", target_budget=budget)


@pytest.mark.parametrize("display_hz", [0.0, -5.0])
def test_a_non_positive_display_hz_raises_value_error(tmp_path, display_hz):
    """Pins today's behaviour (dataset.py already refuses it), which C5 keeps."""
    with pytest.raises(ValueError, match="display_hz"):
        write_dataset_report(build_runs(budget_plans()[1:]), tmp_path, title="Rate", display_hz=display_hz)


# ── the browser driver ───────────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const WAIT = 6000;
const SETTLE = 600;
const LAZY_SETTLE = 1500;

// Defined before the page's own scripts: every <script src> the page adds, every uPlot it creates, and measurements.
const HELPERS = String.raw`
(function () {
  var tc = window.__tc = { scripts: [], plots: [] };
  function note(node) { if (node && node.nodeName === 'SCRIPT' && node.src) tc.scripts.push(node.src); }
  new MutationObserver(function (records) {
    records.forEach(function (record) {
      if (record.type === 'attributes') note(record.target);
      Array.prototype.forEach.call(record.addedNodes || [], function (node) {
        note(node);
        if (node.querySelectorAll) Array.prototype.forEach.call(node.querySelectorAll('script[src]'), note);
      });
    });
  }).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
  var Real = null, Wrapped;
  Object.defineProperty(window, 'uPlot', {
    configurable: true, enumerable: true,
    get: function () { return Wrapped; },
    set: function (value) {
      Real = value;
      if (typeof value !== 'function') { Wrapped = value; return; }
      Wrapped = function (opts, data, target) { var plot = new Real(opts, data, target); tc.plots.push(plot); return plot; };
      Object.setPrototypeOf(Wrapped, Real);
      Wrapped.prototype = Real.prototype;
    },
  });
  tc.all = function (selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); };
  tc.visible = function (el) { if (!el) return false; var box = el.getBoundingClientRect(); return box.width > 0 && box.height > 0; };
  tc.text = function (el) { return el ? el.textContent.replace(/\s+/g, ' ').trim() : null; };
  tc.loaded = function (slug) {  // a slug is [a-z0-9-]: nothing in it to escape
    var wanted = new RegExp('(^|/)targets/' + slug + '\\.js([?#].*)?$');
    return tc.scripts.some(function (src) { return wanted.test(src); });
  };
  tc.live = function (root) {
    return tc.plots.filter(function (plot) { return plot.root && plot.root.isConnected && (!root || root.contains(plot.root)); });
  };
  tc.plotInfo = function (plot) {
    var canvas = plot.root.querySelector('canvas');
    var box = canvas ? canvas.getBoundingClientRect() : { width: 0, height: 0 };
    var withData = 0;
    for (var i = 1; i < plot.data.length; i++) {
      var column = plot.data[i] || [];
      if (Array.prototype.some.call(column, function (v) { return v !== null && v !== undefined && isFinite(v); })) withData++;
    }
    var owner = plot.root.parentElement, statement = null;
    while (owner && !owner.querySelector('[data-tc-drawn-rate]')) owner = owner.parentElement;
    if (owner) statement = tc.text(owner.querySelector('[data-tc-drawn-rate]'));
    return { width: box.width, height: box.height, series: plot.series.length - 1, with_data: withData,
      points: plot.data[0] ? plot.data[0].length : 0, rate: statement, rate_owner_charts: owner ? tc.live(owner).length : 0 };
  };
  tc.charts = function (selector) {
    var root = document.querySelector(selector);
    return root ? tc.live(root).filter(function (plot) { return tc.visible(plot.root); }).map(tc.plotInfo) : null;
  };
  tc.drawnSvg = function (root) {
    var paths = tc.all('svg path', root).filter(function (path) {
      return tc.visible(path.ownerSVGElement) && ((path.getAttribute('d') || '').match(/[ML]/g) || []).length >= 10;
    });
    var canvases = tc.all('canvas', root).filter(function (canvas) {
      if (!tc.visible(canvas) || !canvas.width || !canvas.height) return false;
      var context = canvas.getContext('2d');
      if (!context) return false;
      var pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      for (var i = 3; i < pixels.length; i += 4) if (pixels[i] > 0) return true;
      return false;
    });
    return paths.length + canvases.length;
  };
  tc.cards = function () {
    return tc.all('[data-tc-target-card]').map(function (card) {
      var box = card.getBoundingClientRect(), slug = card.getAttribute('data-tc-target-card');
      return { slug: slug, top: box.top + window.scrollY, height: box.height, text: (tc.text(card) || '').slice(0, 300),
        loaded: tc.loaded(slug), charts: tc.live(card).map(tc.plotInfo),
        rates: tc.all('[data-tc-drawn-rate]', card).filter(tc.visible).map(tc.text) };
    });
  };
  tc.rows = function () {
    return tc.all('[data-tc-target-row]').map(function (row) {
      var box = row.getBoundingClientRect(), slug = row.getAttribute('data-tc-target-row');
      return { slug: slug, config: row.getAttribute('data-config'), top: box.top + window.scrollY, loaded: tc.loaded(slug),
        drawn: tc.drawnSvg(row) + tc.live(row).length };
    });
  };
  tc.painted = function (el) {
    var style = getComputedStyle(el);
    function solid(colour) { return colour && colour !== 'transparent' && !/^rgba\(.*,\s*0\)$/.test(colour); }
    if (solid(style.backgroundColor) && style.backgroundColor !== 'rgb(255, 255, 255)') return style.backgroundColor;
    if (style.borderTopStyle !== 'none' && parseFloat(style.borderTopWidth) > 0 && solid(style.borderTopColor)) return style.borderTopColor;
    return null;
  };
  tc.chips = function () {
    return tc.all('[data-tc-draw]').filter(function (chip) { return tc.visible(chip) && !chip.closest('[data-tc-target-card]'); })
      .map(function (chip) {
        var swatches = tc.all('*', chip).filter(function (el) {
          var box = el.getBoundingClientRect();
          return box.width > 0 && box.height > 0 && box.width <= 16 && box.height <= 16;
        });
        return { config: chip.getAttribute('data-config'), colours: swatches.map(tc.painted).filter(Boolean) };
      });
  };
})();`;

(async () => {
  const browser = await chromium.launch({
    executablePath: process.argv[3], headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const out = { errors: [], viewport: spec.viewport };

  async function open(url) {
    const context = await browser.newContext({ viewport: { width: spec.viewport.width, height: spec.viewport.height } });
    await context.addInitScript(HELPERS);
    const page = await context.newPage();
    // WHY "Failed to load resource" comes from the request events instead: they name the URL, so the browser's own
    // /favicon.ico probe of an http page (no favicon here, nor in any traj_compare site) can be told apart.
    page.on('console', (message) => {
      if (message.type() === 'error' && !/^Failed to load resource/.test(message.text())) out.errors.push(page.url() + ' :: ' + message.text());
    });
    page.on('pageerror', (error) => out.errors.push(page.url() + ' :: ' + String(error)));
    page.on('requestfailed', (request) => out.errors.push(page.url() + ' :: failed ' + request.url() + ' ' + ((request.failure() || {}).errorText || '')));
    page.on('response', (response) => {
      if (response.status() >= 400 && !/\/favicon\.ico$/.test(response.url())) out.errors.push(page.url() + ' :: HTTP ' + response.status() + ' ' + response.url());
    });
    await page.goto(url);
    await page.waitForTimeout(SETTLE);
    return { context, page };
  }
  async function step(record, name, body) {
    try { record[name] = await body(); }
    catch (error) { record[name] = { failed: String((error && error.message) || error).split('\n')[0] }; }
  }
  async function scene(name, url, body) {
    const record = {};
    out[name] = record;
    let context = null;
    try {
      const opened = await open(url);
      context = opened.context;
      await body(opened.page, record);
    } catch (error) {
      record.failed = String((error && error.message) || error).split('\n')[0];
    } finally {
      if (context) await context.close();
    }
  }
  const until = (page, fn, arg) => page.waitForFunction(fn, arg, { timeout: WAIT }).catch(() => null);
  const REPEAT = '[data-tc-target-panel="repeat"]';

  for (const origin of spec.origins) {
    // ── Target level by its address ──
    await scene('target_' + origin.name, origin.index + '#/target/' + spec.big, async (page, record) => {
      const drawn = ({ selector, count }) => {
        const charts = __tc.charts(selector) || [];
        return charts.length >= count && charts.every((chart) => chart.with_data > 0);
      };
      await until(page, drawn, { selector: REPEAT, count: spec.big_charts });
      await page.waitForTimeout(SETTLE);
      await step(record, 'opened', () => page.evaluate(({ slug, selector }) => ({
        loaded: __tc.loaded(slug), scripts: __tc.scripts.slice(0, 20), charts: __tc.charts(selector),
      }), { slug: spec.big, selector: REPEAT }));
      await step(record, 'lines_mode', async () => {
        await page.click('[data-tc-repeats] [data-mode="lines"], [data-tc-repeats][data-mode="lines"]', { timeout: WAIT });
        await page.waitForTimeout(SETTLE);
        await until(page, drawn, { selector: REPEAT, count: spec.big_charts });
        return { charts: await page.evaluate((selector) => __tc.charts(selector), REPEAT) };
      });
    });

    // ── Dataset level: cards render lazily ──
    await scene('cards_' + origin.name, origin.index + '#/targets', async (page, record) => {
      await page.waitForSelector('[data-tc-target-card]', { state: 'attached', timeout: WAIT });
      // the cards in view draw first (their files load), then a pause in which an eager loader would reach the rest
      await until(page, () => __tc.cards().filter((card) => card.top < window.innerHeight - 100)
        .every((card) => card.charts.some((chart) => chart.with_data > 0)));
      await page.waitForTimeout(LAZY_SETTLE);
      await step(record, 'before', () => page.evaluate(() => ({ scroll_y: window.scrollY, cards: __tc.cards() })));
      await step(record, 'scrolled', async () => {
        const slug = await page.evaluate((far) => {
          const cards = __tc.cards().filter((card) => card.top > window.innerHeight + far);
          if (!cards.length) return null;
          const last = cards[cards.length - 1].slug;
          document.querySelector('[data-tc-target-card="' + last + '"]').scrollIntoView({ block: 'center' });
          return last;
        }, spec.far_px);
        if (!slug) throw new Error('no card lies ' + spec.far_px + ' px below the fold');
        await until(page, (wanted) => {
          const card = document.querySelector('[data-tc-target-card="' + wanted + '"]');
          return __tc.live(card).some((plot) => __tc.plotInfo(plot).with_data > 0);
        }, slug);
        await page.waitForTimeout(SETTLE);
        return page.evaluate((wanted) => ({ slug: wanted, card: __tc.cards().filter((card) => card.slug === wanted)[0] }), slug);
      });
    });
  }

  // ── Dataset level: league rows render lazily (file://) ──
  await scene('league', spec.origins[0].index + '#/targets', async (page, record) => {
    await page.waitForSelector('[data-tc-targets-view]', { state: 'attached', timeout: WAIT });
    await page.click('[data-tc-targets-view] [data-view="table"], [data-tc-targets-view][data-view="table"]', { timeout: WAIT });
    await until(page, () => __tc.rows().filter((row) => row.top < window.innerHeight - 50).every((row) => row.drawn > 0));
    await page.waitForTimeout(LAZY_SETTLE);
    await step(record, 'before', () => page.evaluate(() => ({ rows: __tc.rows() })));
    await step(record, 'scrolled', async () => {
      const slug = await page.evaluate((far) => {
        const rows = __tc.rows().filter((row) => row.top > window.innerHeight + far);
        if (!rows.length) return null;
        const last = rows[rows.length - 1].slug;
        const elements = document.querySelectorAll('[data-tc-target-row="' + last + '"]');
        elements[elements.length - 1].scrollIntoView({ block: 'center' });
        return last;
      }, spec.far_px);
      if (!slug) throw new Error('no league row lies ' + spec.far_px + ' px below the fold');
      await until(page, (wanted) => __tc.rows().filter((row) => row.slug === wanted).every((row) => row.drawn > 0), slug);
      await page.waitForTimeout(SETTLE);
      return page.evaluate((wanted) => ({ slug: wanted, rows: __tc.rows().filter((row) => row.slug === wanted) }), slug);
    });
  });

  // ── Dataset level: the runs table's Open in Rerun, served from file:// (the command fallback) ──
  await scene('rerun', spec.origins[0].index, async (page, record) => {
    await page.click('[data-tc-dataset-tab="runs"]', { timeout: WAIT });  // NAVIGATION.md Part E: runs is its own tab
    await page.waitForTimeout(SETTLE);
    await step(record, 'status', async () => {
      await page.getByRole('button', { name: /open in rerun/i }).first().click({ timeout: WAIT });
      await page.waitForTimeout(SETTLE);
      return page.evaluate(() => __tc.all('[role="status"]').map(__tc.text).filter(Boolean));
    });
  });

  // ── Config colours on the Target level ──
  for (const site of spec.colours) {
    await scene('colours_' + site.name, site.index + '#/target/' + site.slug, async (page, record) => {
      await page.waitForSelector('[data-tc-draw]', { state: 'attached', timeout: WAIT }).catch(() => null);
      await page.waitForTimeout(SETTLE);
      await step(record, 'chips', () => page.evaluate(() => __tc.chips()));
    });
  }

  console.log(JSON.stringify(out));
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
"""

VIEWPORT = {"width": 1400, "height": 900}
COLOUR_SITES = {"sim4": ["sim"] * 4, "real4": ["real"] * 4, "twin": ["real", "sim", "real"]}


@contextlib.contextmanager
def served(root: Path):
    """``traj_compare.serve``'s handler over ``root`` on a free port, stopped on exit."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, spawn=lambda argv: None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict:
    """Write the browser datasets and measure every page in one headless Chrome, over file:// and http."""
    root = tmp_path_factory.mktemp("lazy_pages")
    site = root / "browser"
    runs = build_runs(browser_plans())
    write_dataset_report(runs, site, title="Lazy targets", group_by=(TARGET_TAG, CONFIG_TAG))
    colours = {}
    for name, kinds in COLOUR_SITES.items():
        write_dataset_report(build_runs(colour_plans(kinds)), root / f"colours-{name}", title=f"Colours {name}", group_by=(TARGET_TAG, CONFIG_TAG))
        colours[name] = {"kinds": dict(zip(colour_configs(kinds), kinds, strict=True)), "payload": dataset_payload(root / f"colours-{name}")}
    (root / "driver.js").write_text(DRIVER, encoding="utf-8")
    with served(site) as origin:
        spec = {
            "viewport": VIEWPORT,
            "origins": [{"name": "file", "index": (site / "index.html").as_uri()}, {"name": "http", "index": f"{origin}/index.html"}],
            "big": BIG,
            "big_charts": 3 * len(BROWSER_JOINTS),
            "far_px": FAR_PX,
            "colours": [{"name": name, "index": (root / f"colours-{name}" / "index.html").as_uri(), "slug": "probe"} for name in COLOUR_SITES],
        }
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        result = subprocess.run(
            ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(root / "spec.json")],
            capture_output=True, text=True, timeout=600,
        )  # fmt: skip
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    measured = json.loads(result.stdout.strip().splitlines()[-1])
    measured["site"] = site
    measured["runs"] = runs
    measured["colours"] = colours
    measured["drawn"] = {}  # slug -> (points, rate Hz) each target's charts must draw
    for plan in browser_plans():
        reference_t = next(run.reference.t for run in runs if run.tags[TARGET_TAG] == plan.key)
        stride, rate = stride_of(reference_t, DEFAULT_DISPLAY_HZ)
        measured["drawn"][plan.key] = (len(reference_t[::stride]), rate / stride)
    return measured


def step(pages: dict, scene: str, name: str):
    """One step's measurement; a step that could not run fails here with what stopped it."""
    record = pages[scene]
    assert "failed" not in record, f"{scene}: the page did not open: {record['failed']}"
    value = record.get(name)
    assert value is not None, f"{scene}/{name}: not measured"
    assert not (isinstance(value, dict) and "failed" in value), f"{scene}/{name}: {value['failed']}"
    return value


def states_rate(text: str | None, rate_hz: float) -> bool:
    """``text`` holds ``<rate> Hz`` for the drawn rate (rounded as a person writes it)."""
    values = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*Hz", text or "")]
    return any(abs(value - rate_hz) <= max(0.05, 0.02 * rate_hz) for value in values)


def lines_on(pages: dict, key: str) -> int:
    return sum(len(run.measured) for run in pages["runs"] if run.tags[TARGET_TAG] == key)


ORIGINS = ["file", "http"]


# ── Target level ─────────────────────────────────────────────────────────────


@needs_browser
@pytest.mark.parametrize("origin", ORIGINS)
def test_opening_a_target_loads_its_target_file_and_draws_every_line(pages, origin):
    opened = step(pages, f"target_{origin}", "opened")
    assert opened["loaded"], f"opening #/target/{BIG} added no <script src=…targets/{BIG}.js>; scripts: {opened['scripts']}"
    charts = opened["charts"]
    assert charts is not None, "no [data-tc-target-panel='repeat']"
    # per joint: joint error, feedback torque, FB share (NAVIGATION.md Part A: "when present feedback torque and FB share")
    assert len(charts) == 3 * len(BROWSER_JOINTS), f"{len(charts)} charts drawn, want 3 per joint: {charts}"
    points, _ = pages["drawn"][BIG]
    for chart in charts:
        assert chart["width"] > 100 and chart["height"] > 50, chart
        assert chart["with_data"] >= 1 and chart["points"] == points, f"want the target grid's {points} points: {chart}"
    lines = step(pages, f"target_{origin}", "lines_mode")["charts"]
    assert lines_on(pages, BIG) == BIG_LINES
    # Lines mode: a joint-error chart draws every line, a torque chart every line with a breakdown, from the target file
    want = sorted([BIG_TORQUE_LINES] * (2 * len(BROWSER_JOINTS)) + [BIG_LINES] * len(BROWSER_JOINTS))
    assert sorted(chart["with_data"] for chart in lines) == want, f"series with data per chart in Lines mode: {lines}"


@needs_browser
@pytest.mark.parametrize("origin", ORIGINS)
def test_every_target_level_chart_states_the_rate_it_draws(pages, origin):
    charts = step(pages, f"target_{origin}", "opened")["charts"] or []
    assert charts, "no chart drawn on the target level"
    _, rate = pages["drawn"][BIG]
    for chart in charts:
        assert chart["rate"] is not None, f"a chart with no [data-tc-drawn-rate] up its ancestors: {chart}"
        assert chart["rate_owner_charts"] == 1, f"one [data-tc-drawn-rate] per chart, this one covers {chart['rate_owner_charts']}"
        assert states_rate(chart["rate"], rate), f"{BIG} draws {rate:g} Hz (120 Hz picked every 3rd), the chart says {chart['rate']!r}"


# ── Dataset level: lazy cards and league rows ────────────────────────────────


def far_below(items: list[dict], viewport_height: float) -> list[dict]:
    return [item for item in items if item["top"] > viewport_height + FAR_PX]


@needs_browser
@pytest.mark.parametrize("origin", ORIGINS)
def test_cards_far_below_the_fold_wait_as_placeholders_without_their_target_file(pages, origin):
    before = step(pages, f"cards_{origin}", "before")
    assert before["scroll_y"] == 0
    far = far_below(before["cards"], VIEWPORT["height"])
    drawn = [card["slug"] for card in far if any(chart["with_data"] for chart in card["charts"])]
    assert len(far) >= 3 and drawn == [], f"{len(drawn)} of {len(far)} cards far below the fold drew a chart before scrolling: {drawn[:5]}"
    assert [card["slug"] for card in far if card["loaded"]] == [], "a card far below the fold loaded its target file"
    titles = {plan.key: plan.title for plan in browser_plans()}
    for card in far:
        assert card["height"] > 0 and titles[card["slug"]] in card["text"], f"{card['slug']}: the placeholder card names its target"


@needs_browser
@pytest.mark.parametrize("origin", ORIGINS)
def test_a_card_scrolled_into_view_loads_its_target_file_and_draws_at_its_rate(pages, origin):
    scrolled = step(pages, f"cards_{origin}", "scrolled")
    card = scrolled["card"]
    assert card["loaded"], f"{card['slug']}: scrolled into view, but no <script src=…targets/{card['slug']}.js> was added"
    points, rate = pages["drawn"][card["slug"]]
    drawn = [chart for chart in card["charts"] if chart["with_data"] > 0]
    assert drawn and all(chart["width"] > 100 and chart["height"] > 50 for chart in drawn), card["charts"]
    assert all(chart["points"] == points for chart in drawn), f"want the target grid's {points} points: {drawn}"
    assert any(states_rate(text, rate) for text in card["rates"]), f"{card['slug']} draws {rate:g} Hz; its card says {card['rates']}"


@needs_browser
def test_cards_in_the_first_viewport_load_their_files_and_state_their_own_rate(pages):
    cards = step(pages, "cards_file", "before")["cards"]
    in_view = [card for card in cards if card["top"] < VIEWPORT["height"] - 100]
    assert [card["slug"] for card in in_view if not card["loaded"]] == [], "a card in view did not load its target file"
    assert BIG in [card["slug"] for card in in_view], f"the fixture's premise: {BIG} is the first card"
    for card in in_view:
        points, rate = pages["drawn"][card["slug"]]
        drawn = [chart for chart in card["charts"] if chart["with_data"] > 0]
        assert drawn and all(chart["points"] == points for chart in drawn), (card["slug"], card["charts"])
        # BIG is recorded at 120 Hz (40 Hz drawn), the rest at 200 Hz (50 Hz): a card stating display_hz fails one of them
        assert any(states_rate(text, rate) for text in card["rates"]), f"{card['slug']} draws {rate:g} Hz; its card says {card['rates']}"


@needs_browser
def test_league_rows_far_below_the_fold_draw_nothing_until_scrolled_into_view(pages):
    rows = step(pages, "league", "before")["rows"]
    far = far_below(rows, VIEWPORT["height"])
    drawn = [row["slug"] for row in far if row["drawn"]]
    assert len(far) >= 3 and drawn == [], f"{len(drawn)} of {len(far)} league rows far below the fold drew before scrolling: {drawn[:5]}"
    assert [row["slug"] for row in far if row["loaded"]] == [], "a league row far below the fold loaded its target file"


@needs_browser
def test_a_league_row_scrolled_into_view_loads_its_target_file_and_draws_its_error_over_time(pages):
    scrolled = step(pages, "league", "scrolled")
    assert scrolled["rows"] and all(row["loaded"] for row in scrolled["rows"]), (
        f"{scrolled['slug']}: scrolled into view, but its target file was never added: {scrolled['rows']}"
    )
    assert all(row["drawn"] > 0 for row in scrolled["rows"]), f"{scrolled['slug']}: no error-over-time drawing: {scrolled['rows']}"


# ── Dataset level: the runs table's command, from one template ───────────────


@needs_browser
def test_open_in_rerun_from_file_still_offers_the_rows_full_command(pages):
    """Pins today's behaviour (the command each row stored), which the one-template page must keep building."""
    status = " ".join(step(pages, "rerun", "status"))
    site = pages["site"].resolve()
    commands = {}
    for run in pages["runs"]:
        manifest = next(path for path in (site / "runs").glob("*/manifest.json") if json.loads(path.read_text("utf-8"))["name"] == run.name)
        (series,) = run.measured
        rrd = site / "runs" / manifest.parent.name / "rerun" / f"reference--{series}.rrd"
        commands[run.name] = f"python -m traj_compare.dataset drill {shlex.quote(str(site))} {shlex.quote(run.name)} && {viewer_command(rrd)}"
    offered = [name for name, command in commands.items() if command in status]
    assert len(offered) == 1, f"the status names no row's full command (or several): {status[:600]!r}"
    assert offered[0] in status


# ── C4 on the page ───────────────────────────────────────────────────────────


@needs_browser
def test_config_swatches_on_the_target_level_follow_the_colour_rule(pages):
    for name in ("sim4", "real4", "twin"):  # sim4 first: today's grey shades
        chips = step(pages, f"colours_{name}", "chips")
        site = pages["colours"][name]
        expected = {config["name"]: hex_of(config["color"]) for config in site["payload"]["levels"]["configs"]}
        drawn: dict[str, set[str]] = {}
        for chip in chips:
            drawn.setdefault(chip["config"], set()).update(hex_of(colour) for colour in chip["colours"])
        assert set(drawn) == set(expected), f"{name}: [data-tc-draw] chips for {sorted(drawn)}, configs {sorted(expected)}"
        assert all(len(colours) == 1 for colours in drawn.values()), f"{name}: a config drawn in two colours: {drawn}"
        on_page = {config: next(iter(drawn[config])) for config in expected}
        problems = colour_rule_violations(on_page, site["kinds"], None)
        assert problems == [], f"{name}: the swatches {on_page} break C4: {problems}"
        assert on_page == expected, f"{name}: the page's swatches {on_page} are not the payload's config colours {expected}"


@needs_browser
def test_no_console_errors_on_any_page(pages):
    assert pages["errors"] == []
