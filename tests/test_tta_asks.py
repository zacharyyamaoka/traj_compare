"""Eight additive asks from the Trajectory Tracking Agent site (written before the code, 2026-11-24).

TTA ships traj_compare's comparison report and dataset page on a public static host
(https://zacharyyamaoka.github.io/trajectory_tracking_agent/comparison/), and patched their text to do it. Each ask is a
new keyword whose default keeps today's output; these tests hold both halves: the new option does its job, and leaving
it out changes nothing. The browser halves (dark mode, ``#run=``, the fold button at 390 px, the dataset page's Rerun
links and footer) are in ``test_tta_asks_browser.py``.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Comparison, Situation, write_comparison_report
from traj_compare.dataset import Run, write_dataset_report

ASSETS = Path(__file__).resolve().parents[1] / "src" / "traj_compare" / "assets"
SHARED = ("uplot.min.css", "style.css", "uplot.iife.min.js", "three.min.js", "viewhelper.js", "viewer3d.js", "plots.js")
OLD_PALETTE = ("#2a78d6", "#eb6834", "#2f9e44", "#8e5bd1", "#c22f6e", "#17a2b8", "#a67c00", "#6b7a8f")


def comparison(runs: int = 2, **extra) -> Comparison:
    t = np.linspace(0.0, 2.0, 201)
    q = np.column_stack([0.6 * np.sin(t), 0.3 * np.cos(t)])

    def fk(joints: np.ndarray) -> np.ndarray:
        poses = np.tile(np.eye(4), (len(joints), 1, 1))
        poses[:, 0, 3] = 0.3 + 0.2 * np.cos(joints[:, 0])
        poses[:, 1, 3] = 0.3 * np.sin(joints[:, 0])
        poses[:, 2, 3] = 0.2 + 0.1 * joints[:, 1]
        return poses

    return Comparison(
        title="asks", name="asks", joint_names=["j1", "j2"], fk=fk,
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[Situation(name=f"run{i}", title=f"Run {i}", t=t, q=q + 0.01 * (i + 1)) for i in range(runs)],
        **extra,
    )  # fmt: skip


def report_payload(path: Path) -> dict:
    text = path.read_text("utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-data">(.*?)</script>', text, re.S)
    assert match
    return json.loads(match.group(1).replace("<\\/", "</"))


def dataset_payload(index: Path) -> dict:
    text = index.read_text("utf-8")
    match = re.search(r'id="traj-compare-dataset">(.*?)</script>', text, re.S)
    assert match
    return json.loads(match.group(1).replace("<\\/", "</"))


def _unstamped(text: str) -> str:
    return re.sub(r"generated: [^·<]*", "", text)


# ── 1. assets= : the shared viewer files once, not inlined in every report ──────────────────────────────────────────


def test_default_report_still_inlines_every_viewer_file(tmp_path):
    page = write_comparison_report(comparison(), tmp_path / "r.html").read_text("utf-8")
    for name in SHARED:
        tag = "style" if name.endswith(".css") else "script"
        assert f"<{tag}>{(ASSETS / name).read_text('utf-8')}</{tag}>" in page, name
    assert "<link rel=\"stylesheet\"" not in page


def test_assets_directory_is_written_once_and_referenced_relatively(tmp_path):
    shared = tmp_path / "site" / "assets"
    first = write_comparison_report(comparison(), tmp_path / "site" / "runs" / "a" / "report.html", assets=shared)
    second = write_comparison_report(comparison(), tmp_path / "site" / "runs" / "b" / "report.html", assets=shared)
    inline = write_comparison_report(comparison(), tmp_path / "inline.html")
    for name in SHARED:
        assert (shared / name).read_bytes() == (ASSETS / name).read_bytes(), name
    for page_path in (first, second):
        page = page_path.read_text("utf-8")
        assert (ASSETS / "three.min.js").read_text("utf-8")[:2000] not in page
        for name in SHARED:
            if name.endswith(".css"):
                assert f'<link rel="stylesheet" href="../../assets/{name}">' in page, name
            else:
                assert f'<script src="../../assets/{name}"></script>' in page, name
        # same order as the inline page: styles in <head>, then uPlot, three.js, the view helper, the viewer, plots.js
        order = [page.index(f"assets/{name}") for name in SHARED]
        assert order == sorted(order)
        assert page.index("traj-compare-data") < page.index("assets/uplot.iife.min.js")
    shared_bytes = sum((ASSETS / name).stat().st_size for name in SHARED)
    assert first.stat().st_size < inline.stat().st_size - shared_bytes + 2_000  # the viewer's bytes left the page


def test_assets_url_is_referenced_and_nothing_is_written(tmp_path):
    page = write_comparison_report(comparison(), tmp_path / "r.html", assets="https://example.org/tc/assets").read_text("utf-8")
    assert '<script src="https://example.org/tc/assets/three.min.js"></script>' in page
    assert '<link rel="stylesheet" href="https://example.org/tc/assets/style.css">' in page
    assert sorted(p.name for p in tmp_path.iterdir()) == ["r.html"]


# ── 2. the dataset page on a public static host ─────────────────────────────────────────────────────────────────────

NAMES = ("j1", "j2")
T = np.linspace(0.0, 2.0, 201)


def _tape(t, amplitude=0.4):
    s = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / 1.6, 0.0, 1.0))
    return np.column_stack([amplitude * s, -0.5 * amplitude * s])


def _runs(scale: float = 1.0) -> list[Run]:
    runs = []
    for index in range(3):
        reference = JointTrajectory(t=T, joint_names=NAMES, positions=_tape(T))
        sim = JointTrajectory(t=T, joint_names=NAMES, positions=_tape(T) + scale * 1e-5 * (index + 1))
        runs.append(Run(name=f"run {index}", reference=reference, measured={"sim": sim},
                        tags={"target": "A", "rep": index}))
    return runs


def test_command_root_replaces_the_absolute_build_folder(tmp_path):
    out = tmp_path / "build"
    write_dataset_report(_runs(), out, title="ds", rows=(), command_root="site/comparison")
    page = (out / "index.html").read_text("utf-8")
    assert str(out.resolve()) not in page
    payload = dataset_payload(out / "index.html")
    assert payload["serve_command"] == "python -m traj_compare.serve site/comparison"
    assert payload["command_template"]["drill"] == "python -m traj_compare.dataset drill site/comparison "
    viewer = "".join(payload["command_template"]["viewer"])
    assert payload["command_template"]["viewer"][0].endswith(" site/comparison/") and "/home/" not in viewer


def test_dataset_defaults_keep_todays_commands_and_payload_keys(tmp_path):
    out = tmp_path / "build"
    write_dataset_report(_runs(), out, title="ds", rows=())
    payload = dataset_payload(out / "index.html")
    assert payload["serve_command"].endswith(str(out.resolve()))
    for key in ("rerun_server", "public_url"):
        assert key not in payload, key


def test_rerun_server_false_and_public_url_reach_the_page(tmp_path):
    out = tmp_path / "build"
    write_dataset_report(_runs(), out, title="ds", rows=(), rerun_server=False,
                         public_url="https://example.org/tta/comparison/")
    payload = dataset_payload(out / "index.html")
    assert payload["rerun_server"] is False
    assert payload["public_url"] == "https://example.org/tta/comparison/"
    assert payload["rerun_sdk"] == "0.40.0"


def test_rows_choice_reaches_the_page_for_its_footer(tmp_path):
    out = tmp_path / "build"
    write_dataset_report(_runs(), out, title="ds", rows=())
    assert dataset_payload(out / "index.html")["row_files"] == []
    write_dataset_report(_runs(), out, title="ds", rows=("json",))
    assert dataset_payload(out / "index.html")["row_files"] == ["rows.json"]


# ── 3. dark mode: generated from the light rules, so the light page is today's ─────────────────────────────────────


@pytest.mark.parametrize("name", ["style.css", "dataset.css"])
def test_dark_block_is_the_generated_one_and_follows_the_system_theme(name):
    from traj_compare import _theme

    text = (ASSETS / name).read_text("utf-8")
    light, marker, block = text.partition(_theme.MARKER)
    assert marker, f"{name} has no generated dark block"
    assert text == _theme.generated(name), f"{name}: run python -m traj_compare._theme"
    assert "@media (prefers-color-scheme: dark)" in block
    assert ':root:not([data-theme="light"])' in block and ':root[data-theme="dark"]' in block


def test_dark_mapping_keeps_data_colours_and_inverts_neutrals():
    from traj_compare import _theme

    for colour in OLD_PALETTE[:7]:
        assert _theme.dark_colour(colour) == colour  # data colours mean the same thing in both themes
    page, panel, ink = (_theme.lightness(_theme.dark_colour(c)) for c in ("#f4f4f2", "#fcfcfb", "#0b0b0b"))
    assert page < 20 and panel < 25 and ink > 85
    assert panel > page  # a panel still sits above the page, as in the light theme


# ── 4. significant figures, not fixed decimals ──────────────────────────────────────────────────────────────────────


def test_report_degrees_and_millimetres_keep_two_significant_figures():
    from traj_compare.analysis import _format_degrees, _format_millimetres

    assert _format_degrees(math.radians(0.0012)) == "0.0012°"
    assert _format_degrees(math.radians(1.23456)) == "1.235°"  # today's three decimals where they carry the value
    assert _format_millimetres(0.0000031) == "0.0031 mm"
    assert _format_millimetres(0.0123) == "12.300 mm"


# ── 5. a sample mask on the error statistics ────────────────────────────────────────────────────────────────────────


def _masked_comparison(mask=None, label=""):
    t = np.linspace(0.0, 2.0, 201)
    q = np.column_stack([np.where(t < 1.0, 0.0, t - 1.0), np.zeros_like(t)])
    error = np.where(t < 1.0, 0.001, 0.003)  # 1 mrad at rest, 3 mrad while it moves
    extra = {} if mask is None else {"stats_mask": mask, "stats_mask_label": label}
    return Comparison(
        title="mask", name="mask", joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[Situation(name="run", title="Run", t=t, q=q - np.column_stack([error, error]))],
        **extra,
    )  # fmt: skip


def test_stats_mask_restricts_every_error_statistic_but_not_the_curves(tmp_path):
    t = np.linspace(0.0, 2.0, 201)
    moving = t >= 1.0
    full = report_payload(write_comparison_report(_masked_comparison(), tmp_path / "a.html"))["comparisons"][0]
    masked = report_payload(write_comparison_report(_masked_comparison(moving, "moving samples"), tmp_path / "b.html"))["comparisons"][0]
    run_full = next(s for s in full["situations"] if s["name"] == "run")
    run_masked = next(s for s in masked["situations"] if s["name"] == "run")
    assert run_masked["error_metrics"]["positions/j1"]["rms"] == pytest.approx(0.003, rel=1e-9)
    assert run_masked["error_metrics"]["positions/j1"]["n"] == int(moving.sum())
    assert run_full["error_metrics"]["positions/j1"]["rms"] == pytest.approx(math.sqrt((100 * 1e-6 + 101 * 9e-6) / 201), rel=1e-9)
    assert run_masked["plot"]["err_q"] == run_full["plot"]["err_q"]  # the plots still draw every sample
    assert masked["stats_mask"] == {"label": "moving samples", "n": int(moving.sum()), "of": len(t)}
    assert "stats_mask" not in full


def test_stats_mask_must_match_the_reference_samples():
    with pytest.raises(ValueError, match="stats_mask"):
        _masked_comparison(np.ones(10, dtype=bool))


def test_no_mask_is_todays_report(tmp_path):
    a = write_comparison_report(_masked_comparison(), tmp_path / "a.html").read_text("utf-8")
    b = write_comparison_report(_masked_comparison(), tmp_path / "b.html").read_text("utf-8")
    assert _unstamped(a) == _unstamped(b)


# ── 6. a palette past 8 colours, distinct and colour-blind aware ────────────────────────────────────────────────────

# Machado, Oliveira & Fernandes 2009, severity 1.0, on linear sRGB
_CVD = {
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]),
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]),
}


def _linear(colour):
    channels = np.array([int(colour[i : i + 2], 16) / 255.0 for i in (1, 3, 5)])
    return np.where(channels <= 0.04045, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)


def _lab(linear):
    x, y, z = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ np.clip(linear, 0, 1)
    f = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116  # noqa: E731
    fx, fy, fz = f(x / 0.95047), f(y), f(z / 1.08883)
    return np.array([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)])


def _distance(a, b, vision=None):
    la, lb = _linear(a), _linear(b)
    if vision:
        la, lb = _CVD[vision] @ la, _CVD[vision] @ lb
    return float(np.linalg.norm(_lab(la) - _lab(lb)))


def test_report_palette_keeps_the_first_eight_and_adds_distinct_colour_blind_aware_ones():
    from traj_compare.report import SITUATION_PALETTE

    assert tuple(SITUATION_PALETTE[:8]) == OLD_PALETTE
    assert len(SITUATION_PALETTE) >= 16 and len(set(SITUATION_PALETTE)) == len(SITUATION_PALETTE)
    for index, colour in enumerate(SITUATION_PALETTE[8:], start=8):
        assert 35 <= _lab(_linear(colour))[0] <= 70, colour  # a line on the light page and on the dark one
        for other in SITUATION_PALETTE[:index]:
            assert _distance(colour, other) >= 20, (colour, other)
            for vision in _CVD:
                assert _distance(colour, other, vision) >= 10, (colour, other, vision)


def test_twelve_runs_get_twelve_colours(tmp_path):
    payload = report_payload(write_comparison_report(comparison(runs=12), tmp_path / "r.html"))
    colours = [s["color"] for s in payload["comparisons"][0]["situations"] if s["role"] != "target"]
    assert len(set(colours)) == 12
    assert colours[:8] == list(OLD_PALETTE)


@pytest.mark.parametrize("name, pattern", [("dataset.js", r"var PALETTE = \[([^\]]*)\]"),
                                           ("plots.js", r"var colors = \[('#2a78d6'[^\]]*)\]")])
def test_the_pages_share_the_report_palette(name, pattern):
    from traj_compare.report import SITUATION_PALETTE

    match = re.search(pattern, (ASSETS / name).read_text("utf-8"))
    assert match, name
    colours = re.findall(r"'(#[0-9a-f]{6})'", match.group(1))
    assert colours == list(SITUATION_PALETTE)


def test_palette_pairs_are_checked_both_ways():  # the ruler itself: an identical pair must fail it
    assert _distance("#2a78d6", "#2a78d6") == 0.0
    assert min(_distance(a, b, "deuteranopia") for a, b in itertools.combinations(OLD_PALETTE, 2)) < 10


# ── 3b. the canvases' ink is the stylesheets' mapping (a JS port of _theme.dark_colour) ────────────────────────────


def test_js_ink_is_the_python_mapping_and_one_block_in_both_pages(tmp_path):
    import shutil
    import subprocess

    from traj_compare import _theme

    if not shutil.which("node"):
        pytest.skip("needs node")
    blocks = []
    for name in ("plots.js", "dataset.js"):
        text = (ASSETS / name).read_text("utf-8")
        start = text.index("  // ── ink: the dark theme's colour")
        blocks.append(text[start : text.index("  // ── ink end", start)])
    assert blocks[0] == blocks[1], "plots.js and dataset.js carry one ink block"
    css = "".join((ASSETS / name).read_text("utf-8").partition(_theme.MARKER)[0] for name in ("style.css", "dataset.css"))
    colours = sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b", css)) | set(OLD_PALETTE) | {"#fcfcfb", "#d0cfc9", "#52514e", "#fff"})
    script = tmp_path / "ink.js"
    script.write_text("var document = { documentElement: { getAttribute: function () { return 'dark'; } } };\n" + blocks[0] +
                      f"\nconsole.log(JSON.stringify({json.dumps(colours)}.map(darkInk)));\n")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True, timeout=60)
    assert json.loads(result.stdout) == [_theme.dark_colour(colour) for colour in colours]
