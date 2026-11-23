"""The Matplotlib, Viser and W&B coverage viewers (docs/COVERAGE.md "The other viewers").

Each viewer reads only the payload `analyze()` writes, so these tests build one synthetic dataset (three joints, six
trajectories, a tool, a "split" tag) and check what each viewer does with it: the PNG names the contract lists, that
they are not blank and that the colour controls change their pixels; that W&B gets exactly the headline numbers and
nothing else; that the Viser scene holds its named views and switches them. The colour rule is checked against
assets/coverage_color.js, the page's, so the PNGs, Viser and the page cannot drift apart.

Zach, Daily Note 2026-11-23: "Matplot lib, Viser, weights and biases, OUr own custom viewer".
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from scipy.spatial.transform import Rotation

from traj_compare.coverage import analyze, log_coverage, plot_coverage
from traj_compare.coverage import matplotlib_view as mpl_view

COLOR_JS = Path(__file__).resolve().parents[1] / "src" / "traj_compare" / "assets" / "coverage_color.js"
JOINTS = ("shoulder", "elbow", "wrist")
LIMITS = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -2.0, -math.pi]),
                     max_position=np.array([math.pi, 2.0, math.pi]), max_velocity=np.array([3.0, 3.0, 4.0]),
                     max_acceleration=np.array([15.0, 15.0, 20.0]))


def trajectory(seed: int, seconds: float = 8.0) -> tuple[JointTrajectory, PoseTrajectory]:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, seconds, 0.01)
    w = rng.uniform(0.4, 1.6, 3)
    amp = rng.uniform(0.3, 1.0, 3) * np.array([math.pi, 2.0, math.pi]) * 0.8
    q = amp * np.sin(w * t[:, None] + rng.uniform(0, 6, 3))
    joint = JointTrajectory(t=t, joint_names=JOINTS, positions=q, limits=LIMITS)
    xyz = np.stack([0.4 + 0.2 * np.cos(q[:, 0]), 0.2 * np.sin(q[:, 0]), 0.3 + 0.1 * np.sin(q[:, 1])], axis=1)
    rot = Rotation.from_euler("zyx", np.stack([q[:, 2], 0.4 * np.sin(q[:, 1]), np.full(len(t), math.pi)], axis=1))
    return joint, PoseTrajectory(t=t, positions=xyz, orientations=rot.as_quat())


@pytest.fixture(scope="module")
def payload() -> dict:
    pairs = {f"traj {k}": trajectory(k) for k in range(6)}
    tags = {name: {"split": "dev" if k < 4 else "holdout"} for k, name in enumerate(pairs)}
    return analyze({n: j for n, (j, _) in pairs.items()}, tool={n: p for n, (_, p) in pairs.items()}, tags=tags,
                   group_by="split", title="Synthetic arm").payload


@pytest.fixture(scope="module")
def joints_only() -> dict:
    return analyze({f"traj {k}": trajectory(k)[0] for k in range(3)}, title="Joints only").payload


def pixels(path: Path) -> np.ndarray:
    from matplotlib.image import imread

    return imread(str(path))[..., :3]


def figure_pixels(payload: dict, figure_id: str, **colour) -> np.ndarray:
    import io

    from matplotlib.image import imread

    fig = mpl_view.figure(payload, figure_id, **colour)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=60)
    buffer.seek(0)
    return imread(buffer)[..., :3]


# ── the colour rule is the page's ────────────────────────────────────────────


def test_the_colormap_stops_are_the_pages():
    source = COLOR_JS.read_text("utf-8")
    for name, stops in mpl_view.COLORMAPS.items():
        found = re.search(rf"{name}: (\[\[.*?\]\]),", source)
        assert found, f"{name} missing from coverage_color.js"
        assert [tuple(stop) for stop in json.loads(found.group(1))] == list(stops), name
    assert mpl_view.COLORMAP_NAMES == ("viridis", "magma", "plasma", "inferno", "cividis")
    assert mpl_view.SCALES == ("linear", "log", "equalized", "visited", "enough")
    assert "[221, 220, 214]" in source and tuple(mpl_view.OUTSIDE_RGB) == (221, 220, 214)
    assert "'#b4442f'" in source and mpl_view.LIMIT_COLOR == "#b4442f"


def test_the_ramp_ends_on_the_first_and_last_stop_and_reverse_swaps_them():
    viridis = mpl_view.COLORMAPS["viridis"]
    assert tuple(mpl_view.ramp_rgb(0.0)) == viridis[0]
    assert tuple(mpl_view.ramp_rgb(1.0)) == viridis[-1]
    assert tuple(mpl_view.ramp_rgb(0.0, "viridis", reverse=True)) == viridis[-1]
    halfway = tuple(int(round((a + b) / 2 + 1e-9)) for a, b in zip(viridis[0], viridis[1], strict=False))
    assert tuple(mpl_view.ramp_rgb(0.5 / 16)) == halfway  # between stops: linear, rounded like Math.round


def test_each_scale_maps_counts_as_the_page_does():
    counts = [0, 1, 2, 3, 100]
    # linear: clipped at p98 of the visited cells (numpy's / the page's linear quantile)
    top = 3 + (100 - 3) * 0.94
    linear = mpl_view.scale_counts(counts, "linear")
    assert linear.t[0] == -1 and linear.t[-1] == 1.0
    assert linear.t[1] == pytest.approx(1 / top)
    assert "clipped at p98" in linear.note
    assert mpl_view.scale_counts(counts, "equalized").t.tolist() == pytest.approx([-1, 0, 1 / 3, 2 / 3, 1])
    assert mpl_view.scale_counts(counts, "visited").t.tolist() == [-1, 1, 1, 1, 1]
    assert mpl_view.scale_counts(counts, "enough", enough=3).t.tolist() == [-1, 0.25, 0.25, 1, 1]
    log = mpl_view.scale_counts(counts, "log")
    assert log.t[2] == pytest.approx(math.log1p(2) / math.log1p(100))
    assert mpl_view.scale_counts([0, 0], "linear").note == "nothing visited"


# ── Matplotlib ───────────────────────────────────────────────────────────────


def test_plot_coverage_writes_the_contract_png_names(payload, tmp_path):
    written = plot_coverage(payload, tmp_path / "png")
    names = {path.name for path in written}
    expected = {"limit-bars.png", "ridgeline.png", "parallel-q.png", "growth.png", "projections.png",
                "tool-speed.png", "tilt-map.png", "tilt-yaw.png"}
    expected |= {f"heat-q-qd-{joint}.png" for joint in JOINTS} | {f"slabs-{joint}.png" for joint in JOINTS}
    assert names == expected
    assert all(path.is_file() and path.parent == tmp_path / "png" for path in written)


def test_without_a_tool_there_are_no_tool_figures(joints_only, tmp_path):
    names = {path.name for path in plot_coverage(joints_only, tmp_path)}
    assert not names & {"projections.png", "tool-speed.png", "tilt-map.png", "tilt-yaw.png"}
    assert {"limit-bars.png", "ridgeline.png", "growth.png"} <= names


def test_no_png_is_blank(payload, tmp_path):
    for path in plot_coverage(payload, tmp_path):
        image = pixels(path)
        assert image.shape[0] > 200 and image.shape[1] > 300, path.name
        assert image.std() > 0.05, f"{path.name} is (nearly) one flat colour"
        colours = len(np.unique((image.reshape(-1, 3) * 255).astype(np.uint8), axis=0))
        assert colours > 20, f"{path.name}: only {colours} colours"


def test_colormap_reverse_and_scale_repaint_the_heatmap(payload):
    figure_id = f"heat-q-qd-{JOINTS[0]}"
    viridis = figure_pixels(payload, figure_id)
    magma = figure_pixels(payload, figure_id, cmap="magma")
    reversed_viridis = figure_pixels(payload, figure_id, reverse=True)
    equalized = figure_pixels(payload, figure_id, scale="equalized")
    for other in (magma, reversed_viridis, equalized):
        assert other.shape == viridis.shape
        assert np.mean(np.any(np.abs(other - viridis) > 0.02, axis=-1)) > 0.01


def test_an_unknown_colormap_or_scale_is_refused(payload, tmp_path):
    with pytest.raises(ValueError, match="viridis"):
        plot_coverage(payload, tmp_path, cmap="jet")
    with pytest.raises(ValueError, match="linear"):
        plot_coverage(payload, tmp_path, scale="sqrt")


def test_matplotlib_is_not_imported_by_the_payload_side():
    import subprocess
    import sys

    code = ("import sys, traj_compare.coverage as c; c.analyze; import traj_compare.coverage.wandb_log; "
            "print('matplotlib' in sys.modules, 'wandb' in sys.modules, 'viser' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["False", "False", "False"]


# ── W&B ──────────────────────────────────────────────────────────────────────


class FakeRun:
    def __init__(self) -> None:
        self.summary: dict = {}
        self.config: dict = {}


def test_log_coverage_writes_exactly_the_headline_numbers(payload):
    run = FakeRun()
    logged = log_coverage(run, payload)
    numbers = {f"coverage/{entry['key']}": entry["value"] for entry in payload["numbers"]}
    assert run.summary == pytest.approx(numbers)
    assert run.config == {"coverage/title": "Synthetic arm"}
    assert logged == {**run.summary, **run.config}
    assert all(isinstance(value, float) for value in run.summary.values())  # scalars only, no tables or media


def test_log_coverage_takes_a_prefix(payload):
    run = FakeRun()
    log_coverage(run, payload, prefix="cov.")
    assert set(run.summary) == {f"cov.{entry['key']}" for entry in payload["numbers"]}
    assert set(run.config) == {"cov.title"}


def test_log_coverage_into_a_real_offline_wandb_run(payload, tmp_path, monkeypatch):
    wandb = pytest.importorskip("wandb")
    monkeypatch.setenv("WANDB_MODE", "offline")
    monkeypatch.setenv("WANDB_SILENT", "true")
    monkeypatch.setenv("WANDB_DIR", str(tmp_path))
    run = wandb.init(mode="offline", dir=str(tmp_path), project="traj-compare-coverage-test",
                     settings=wandb.Settings(console="off", save_code=False))
    try:
        logged = log_coverage(run, payload)
        for entry in payload["numbers"]:
            assert run.summary[f"coverage/{entry['key']}"] == pytest.approx(entry["value"])
        assert run.config["coverage/title"] == "Synthetic arm"
        assert len(logged) == len(payload["numbers"]) + 1
    finally:
        run.finish()
    assert list(tmp_path.glob("wandb/offline-run-*")), "the offline run was written to disk"


# ── Viser ────────────────────────────────────────────────────────────────────


@pytest.fixture()
def viewer(payload):
    pytest.importorskip("viser")
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.coverage import serve_coverage

    started = serve_coverage(payload, port=0)
    yield started
    started.stop()
    assert started.server_closed


def test_serve_coverage_prints_ready(payload, capsys):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.coverage import serve_coverage

    started = serve_coverage(payload, port=0)
    try:
        assert f"READY {started.url}" in capsys.readouterr().out.splitlines()
    finally:
        started.stop()


def test_serve_coverage_builds_every_view(viewer):
    assert viewer.port > 0 and viewer.config.host == "127.0.0.1" and viewer.config.show_logo is False
    nodes = set(viewer.server.scene._handle_from_node_name)
    for name in ("/coverage/voxels/visited", "/coverage/tool_paths/lines", "/coverage/sphere/cells",
                 "/coverage/sphere/grid", "/coverage/height/tiles", "/coverage/height/floor_limits",
                 "/coverage/height/qdd_limit", "/coverage/workspace/base"):
        assert name in nodes, name


def test_the_view_dropdown_switches_which_frame_is_shown(viewer):
    coverage = viewer.coverage
    assert coverage.view.options == ("Voxels", "Tool paths", "Tool directions sphere", "q-qd-qdd height map")
    shown_for = {"Voxels": {"voxels", "workspace"}, "Tool paths": {"tool_paths", "workspace"},
                 "Tool directions sphere": {"sphere"}, "q-qd-qdd height map": {"height"}}
    for view, expected in shown_for.items():
        coverage.view.value = view
        assert {key for key, frame in coverage.frames.items() if frame.visible} == expected, view
        assert coverage.joint.visible == (view == "q-qd-qdd height map")
        assert coverage.threshold.visible == (view == "Voxels")


def test_colours_reverse_and_threshold_change_the_voxels(viewer):
    coverage = viewer.coverage
    nodes = viewer.server.scene._handle_from_node_name
    coverage.view.value = "Voxels"
    assert coverage.colours.options == ("viridis", "magma", "plasma", "inferno", "cividis")
    first = np.array(nodes["/coverage/voxels/visited"].colors).copy()
    coverage.colours.value = "magma"
    assert np.any(np.array(nodes["/coverage/voxels/visited"].colors) != first)
    coverage.colours.value = "viridis"
    coverage.reverse.value = True
    assert np.any(np.array(nodes["/coverage/voxels/visited"].colors) != first)
    everything = len(nodes["/coverage/voxels/visited"].points)
    assert everything == len(viewer.coverage.payload["tool"]["voxels"]["cells"])  # threshold 0 shows them all
    samples = sorted(cell[3] for cell in coverage.payload["tool"]["voxels"]["cells"])
    coverage.threshold.value = int(samples[len(samples) // 2])
    assert 0 < len(nodes["/coverage/voxels/visited"].points) < everything
    assert "colour = samples per 5 cm voxel" in coverage.legend.content


def test_the_height_map_follows_the_joint(viewer):
    coverage = viewer.coverage
    nodes = viewer.server.scene._handle_from_node_name
    coverage.view.value = "q-qd-qdd height map"
    first = np.array(nodes["/coverage/height/tiles"].points).copy()
    coverage.joint.value = JOINTS[1]
    second = np.array(nodes["/coverage/height/tiles"].points)
    assert first.shape != second.shape or np.any(first != second)
    assert coverage.status.rows["joint"] == JOINTS[1]


def test_without_a_tool_only_the_height_map_is_offered(joints_only):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.coverage import serve_coverage

    started = serve_coverage(joints_only, port=0)
    try:
        assert started.coverage.view.options == ("q-qd-qdd height map",)
        assert "/coverage/voxels" not in started.server.scene._handle_from_node_name
    finally:
        started.stop()


def test_the_cli_serves_the_json_it_is_given(payload, tmp_path):
    from traj_compare.coverage.viser_view import main

    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), "utf-8")
    calls = []

    class Served:
        def serve_forever(self) -> None:
            calls.append("served")

    def fake_serve(given, *, port, title):
        calls.append((given["title"], port, title))
        return Served()

    main([str(path), "--port", "0"], serve=fake_serve)
    assert calls == [("Synthetic arm", 0, None), "served"]
