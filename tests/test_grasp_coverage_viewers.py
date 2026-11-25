"""Grasp coverage: the Matplotlib, Viser and W&B viewers (acceptance, written before the code, 2026-11-24).
Contract: docs/GRASP_COVERAGE.md "The other viewers".

Each reads only the payload. The PNGs: exactly the contract's names, none blank, the colour controls repaint the
heatmaps. W&B: exactly the headline numbers, nothing else. Viser: a gripper glyph set per outcome that its checkbox
hides, the area boxes, the approach sphere recoloured by the colormap dropdown.
"""

from __future__ import annotations

import io
import subprocess
import sys

import numpy as np
import pytest
from grasp_fixture import AREA, PLANNER_RANGE, WIDTH_RANGE, made_up

from traj_compare.grasp_coverage import analyze_grasps, log_grasp_coverage, plot_grasp_coverage
from traj_compare.grasp_coverage import matplotlib_view as mpl_view

PNGS = {"positions.png", "position-density.png", "width.png", "roll.png", "pointing.png", "sphere.png",
        "width-tilt.png", "objects.png"}


@pytest.fixture(scope="module")
def payload() -> dict:
    grasps, outcomes, tags, _ = made_up()
    return analyze_grasps(grasps, outcomes=outcomes, width_range=WIDTH_RANGE, planner_width_range=PLANNER_RANGE,
                          tags=tags, area=AREA, title="Made-up picks").payload


def figure_pixels(payload: dict, figure_id: str, **colour) -> np.ndarray:
    from matplotlib.image import imread

    buffer = io.BytesIO()
    mpl_view.figure(payload, figure_id, **colour).savefig(buffer, format="png", dpi=60)
    buffer.seek(0)
    return imread(buffer)[..., :3]


# ── Matplotlib ──────────────────────────────────────────────────────────────


def test_plot_writes_exactly_the_contract_pngs(payload, tmp_path):
    written = plot_grasp_coverage(payload, tmp_path / "png")
    assert {path.name for path in written} == PNGS
    assert all(path.parent == tmp_path / "png" and path.stat().st_size > 5000 for path in written)


def test_no_png_is_blank(payload, tmp_path):
    from matplotlib.image import imread

    for path in plot_grasp_coverage(payload, tmp_path):
        image = imread(str(path))[..., :3]
        assert image.shape[0] > 200 and image.shape[1] > 300, path.name
        assert image.std() > 0.05, f"{path.name} is (nearly) one flat colour"


@pytest.mark.parametrize("figure_id", ["position-density", "pointing", "sphere", "width-tilt"])
def test_colormap_reverse_and_scale_repaint_the_heatmaps(payload, figure_id):
    viridis = figure_pixels(payload, figure_id)
    for colour in ({"cmap": "magma"}, {"reverse": True}, {"scale": "visited"}):
        other = figure_pixels(payload, figure_id, **colour)
        assert other.shape == viridis.shape
        assert np.mean(np.any(np.abs(other - viridis) > 0.02, axis=-1)) > 0.002, (figure_id, colour)


def test_outcomes_are_drawn_in_their_own_colours(payload):
    """'showing where the failures where and not': the positions figure paints each outcome's dots in its colour."""
    image = figure_pixels(payload, "positions")
    for hex_colour in (mpl_view.OUTCOME_COLORS["picked"], mpl_view.OUTCOME_COLORS["failed"]):
        rgb = np.array([int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
        near = np.all(np.abs(image - rgb) < 0.06, axis=-1)
        assert near.sum() > 10, hex_colour


def test_an_unknown_colour_choice_or_payload_is_refused(payload, tmp_path):
    with pytest.raises(ValueError, match="viridis"):
        plot_grasp_coverage(payload, tmp_path, cmap="jet")
    with pytest.raises(ValueError, match="linear"):
        plot_grasp_coverage(payload, tmp_path, scale="sqrt")
    with pytest.raises(ValueError, match="grasp_coverage"):
        plot_grasp_coverage({"schema": "traj_compare.coverage/1"}, tmp_path)


def test_the_analysis_imports_no_viewer_tool():
    code = ("import sys, traj_compare.grasp_coverage as g; g.analyze_grasps; import traj_compare.grasp_coverage.wandb_log; "
            "print('matplotlib' in sys.modules, 'wandb' in sys.modules, 'viser' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["False", "False", "False"]


# ── W&B ─────────────────────────────────────────────────────────────────────


class FakeRun:
    def __init__(self) -> None:
        self.summary: dict = {}
        self.config: dict = {}


def test_wandb_gets_exactly_the_headline_numbers(payload):
    run = FakeRun()
    logged = log_grasp_coverage(run, payload)
    assert run.summary == pytest.approx({f"grasp_coverage/{e['key']}": e["value"] for e in payload["numbers"]})
    assert run.config == {"grasp_coverage/title": "Made-up picks"}
    assert logged == {**run.summary, **run.config}
    assert all(isinstance(value, float) for value in run.summary.values())  # scalars only


def test_wandb_takes_a_prefix_and_refuses_another_payload(payload):
    run = FakeRun()
    log_grasp_coverage(run, payload, prefix="g.")
    assert set(run.summary) == {f"g.{e['key']}" for e in payload["numbers"]}
    with pytest.raises(ValueError, match="grasp_coverage"):
        log_grasp_coverage(FakeRun(), {"schema": "traj_compare.coverage/1", "numbers": []})


def test_wandb_into_a_real_offline_run(payload, tmp_path, monkeypatch):
    wandb = pytest.importorskip("wandb")
    monkeypatch.setenv("WANDB_MODE", "offline")
    monkeypatch.setenv("WANDB_SILENT", "true")
    monkeypatch.setenv("WANDB_DIR", str(tmp_path))
    run = wandb.init(mode="offline", dir=str(tmp_path), project="grasp-coverage-test",
                     settings=wandb.Settings(console="off", save_code=False))
    try:
        log_grasp_coverage(run, payload)
        for entry in payload["numbers"]:
            assert run.summary[f"grasp_coverage/{entry['key']}"] == pytest.approx(entry["value"])
    finally:
        run.finish()


# ── Viser ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def viewer(payload):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.grasp_coverage import serve_grasp_coverage

    started = serve_grasp_coverage(payload, port=0)
    yield started
    started.stop()


def test_viser_prints_ready_on_loopback_without_a_logo(payload, capsys):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.grasp_coverage import serve_grasp_coverage

    started = serve_grasp_coverage(payload, port=0)
    try:
        assert f"READY {started.url}" in capsys.readouterr().out.splitlines()
        assert started.port > 0 and started.config.host == "127.0.0.1" and started.config.show_logo is False
    finally:
        started.stop()


def test_viser_draws_a_glyph_set_per_outcome_the_area_and_the_sphere(viewer, payload):
    nodes = viewer.server.scene._handle_from_node_name
    for outcome in payload["outcomes"]["order"]:
        name = f"/grasps/{outcome}/jaws"
        assert name in nodes, name
        expected = payload["outcomes"]["counts"][outcome] * 4  # four segments per glyph
        assert len(np.asarray(nodes[name].points)) == expected, outcome
    assert "/grasps/area" in nodes
    assert "/sphere/cells" in nodes


def test_an_outcome_checkbox_hides_its_grasps(viewer):
    view = viewer.grasp_coverage
    nodes = viewer.server.scene._handle_from_node_name
    assert set(view.shown) == {"picked", "failed", "hovered", "refused", "unknown"}
    view.shown["picked"].value = False
    assert nodes["/grasps/picked/jaws"].visible is False and nodes["/grasps/failed/jaws"].visible is True
    view.shown["picked"].value = True
    assert nodes["/grasps/picked/jaws"].visible is True


def test_the_colormap_and_reverse_recolour_the_sphere(viewer):
    view = viewer.grasp_coverage
    nodes = viewer.server.scene._handle_from_node_name
    assert view.colours.options == ("viridis", "magma", "plasma", "inferno", "cividis")
    first = np.array(nodes["/sphere/cells"].colors).copy()
    view.colours.value = "magma"
    assert np.any(np.array(nodes["/sphere/cells"].colors) != first)
    view.colours.value = "viridis"
    view.reverse.value = True
    assert np.any(np.array(nodes["/sphere/cells"].colors) != first)
