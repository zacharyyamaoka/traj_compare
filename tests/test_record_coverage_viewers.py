"""Record coverage viewers: Matplotlib, Viser and W&B read ONLY the payload (acceptance, written before the code,
2026-11-24). Contract: docs/RECORD_COVERAGE.md, "The other viewers"."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from traj_compare.record_coverage import analyze

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from test_record_coverage import made_up  # noqa: E402  the same made-up picks as the analysis tests


@pytest.fixture(scope="module")
def payload() -> dict:
    coverage = analyze(made_up(), ranges={"draws": (0, 9), "tcp[0]": (-0.4, 0.4), "tcp[1]": (0.0, 0.6),
                                          "tcp[2]": (-0.2, 0.2)},
                       pairs=[("angle_rad", "grip.width_mm"), ("tcp[0]", "tcp[1]")], group_by="item", split="split",
                       title="Made-up picks")
    # WHY through JSON: a viewer is handed what a file on disk holds, never the live object
    return json.loads(json.dumps(coverage.payload))


@pytest.fixture(scope="module")
def plain_payload() -> dict:
    rows = [{"a": float(i % 7), "b": "x" if i % 3 else "y"} for i in range(30)]
    return json.loads(json.dumps(analyze(rows).payload))


def pixels(path) -> np.ndarray:
    from matplotlib import image

    return image.imread(str(path))


# ── Matplotlib ───────────────────────────────────────────────────────────────


def test_plot_records_writes_the_contract_png_names(payload, tmp_path):
    from traj_compare.record_coverage import plot_records

    paths = plot_records(payload, tmp_path)
    names = sorted(p.name for p in paths)
    assert names == sorted(["numbers.png", "classes.png", "missing.png", "pair-angle_rad-grip.width_mm.png",
                            "pair-tcp-0-tcp-1.png", "growth.png", "support.png"])
    assert all(p.parent == tmp_path and p.is_file() for p in paths)


def test_without_pairs_or_a_split_there_are_no_pair_or_support_pngs(plain_payload, tmp_path):
    from traj_compare.record_coverage import plot_records

    names = {p.name for p in plot_records(plain_payload, tmp_path)}
    assert names == {"numbers.png", "classes.png", "missing.png", "growth.png"}


def test_no_png_is_blank(payload, tmp_path):
    from traj_compare.record_coverage import plot_records

    for path in plot_records(payload, tmp_path):
        image = pixels(path)
        assert image.shape[0] > 200 and image.shape[1] > 300, path.name
        assert float(np.std(image[..., :3])) > 0.02, f"{path.name} is (nearly) one colour"


def test_colormap_reverse_and_scale_repaint_the_pair_heatmap(payload, tmp_path):
    from traj_compare.record_coverage import plot_records

    def pair_image(**kwargs):
        out = tmp_path / "-".join(f"{k}{v}" for k, v in kwargs.items())
        plot_records(payload, out, **kwargs)
        return pixels(out / "pair-angle_rad-grip.width_mm.png")

    base = pair_image(cmap="viridis")
    for other in (dict(cmap="magma"), dict(cmap="viridis", reverse=True), dict(cmap="viridis", scale="log")):
        changed = pair_image(**other)
        assert changed.shape == base.shape and not np.allclose(changed, base), other


def test_an_unknown_colormap_or_scale_is_refused(payload, tmp_path):
    from traj_compare.record_coverage import plot_records

    with pytest.raises(ValueError, match="cmap"):
        plot_records(payload, tmp_path, cmap="jet")
    with pytest.raises(ValueError, match="scale"):
        plot_records(payload, tmp_path, scale="sqrt")


def test_a_payload_of_another_schema_is_refused(tmp_path):
    from traj_compare.record_coverage import plot_records

    with pytest.raises(ValueError, match="record_coverage"):
        plot_records({"schema": "traj_compare.coverage/1"}, tmp_path)


def test_no_viewer_tool_is_imported_by_the_analysis_side():
    code = ("import sys, traj_compare.record_coverage as r; r.analyze; import traj_compare.record_coverage.wandb_log; "
            "print('matplotlib' in sys.modules, 'wandb' in sys.modules, 'viser' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["False", "False", "False"]


# ── W&B ──────────────────────────────────────────────────────────────────────


class FakeRun:
    def __init__(self) -> None:
        self.summary: dict = {}
        self.config: dict = {}


def test_log_records_writes_exactly_the_headline_numbers(payload):
    from traj_compare.record_coverage import log_records

    run = FakeRun()
    logged = log_records(run, payload)
    numbers = {f"records/{entry['key']}": entry["value"] for entry in payload["numbers"]}
    assert run.summary == pytest.approx(numbers)
    assert run.config == {"records/title": "Made-up picks"}
    assert logged == {**run.summary, **run.config}
    assert all(isinstance(value, float) for value in run.summary.values())  # scalars only, no tables or media


def test_log_records_refuses_another_schema():
    from traj_compare.record_coverage import log_records

    with pytest.raises(ValueError, match="record_coverage"):
        log_records(FakeRun(), {"schema": "traj_compare.coverage/1", "numbers": []})


def test_log_records_into_a_real_offline_wandb_run(payload, tmp_path, monkeypatch):
    wandb = pytest.importorskip("wandb")
    from traj_compare.record_coverage import log_records

    monkeypatch.setenv("WANDB_MODE", "offline")
    monkeypatch.setenv("WANDB_SILENT", "true")
    monkeypatch.setenv("WANDB_DIR", str(tmp_path))
    run = wandb.init(mode="offline", dir=str(tmp_path), project="record-coverage-test",
                     settings=wandb.Settings(console="off", save_code=False))
    try:
        logged = log_records(run, payload)
        for entry in payload["numbers"]:
            assert run.summary[f"records/{entry['key']}"] == pytest.approx(entry["value"])
        assert len(logged) == len(payload["numbers"]) + 1
    finally:
        run.finish()


# ── Viser ────────────────────────────────────────────────────────────────────


@pytest.fixture()
def viewer(payload):
    pytest.importorskip("viser")
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.record_coverage import serve_records

    started = serve_records(payload, port=0)
    yield started
    started.stop()


def test_serve_records_prints_ready_on_loopback_without_the_logo(payload, capsys):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.record_coverage import serve_records

    started = serve_records(payload, port=0)
    try:
        assert f"READY {started.url}" in capsys.readouterr().out.splitlines()
        assert started.port > 0 and started.config.host == "127.0.0.1" and started.config.show_logo is False
    finally:
        started.stop()


def test_serve_records_draws_the_points_in_their_declared_box(viewer, payload):
    nodes = set(viewer.server.scene._handle_from_node_name)
    assert "/records/points" in nodes and "/records/box" in nodes
    view = viewer.records
    assert view.points.shape == (len(payload["points3d"]["points"]), 3)
    assert view.colors.shape == view.points.shape and view.colors.dtype == np.uint8


def test_each_class_gets_its_own_colour_and_the_panel_names_them(viewer, payload):
    view = viewer.records
    codes = np.asarray(payload["points3d"]["codes"])
    seen = sorted(set(codes.tolist()))
    colours = {code: tuple(view.colors[np.flatnonzero(codes == code)[0]]) for code in seen}
    assert len(set(colours.values())) == len(seen)  # one colour per class
    for level in [payload["points3d"]["levels"][c] for c in seen]:
        assert level in view.legend_html  # the legend names every colour it draws


def test_without_3d_points_the_viser_view_is_refused(plain_payload):
    pytest.importorskip("viser_3d_viewer")
    from traj_compare.record_coverage import serve_records

    with pytest.raises(ValueError, match="3-D"):
        serve_records(plain_payload, port=0)


# ── the command line ─────────────────────────────────────────────────────────


def test_the_cli_reads_json_lines_and_a_json_list_and_writes_the_workbench(tmp_path):
    lines = tmp_path / "a.jsonl"
    lines.write_text("\n".join(json.dumps({"x_m": i / 10, "kind": "a" if i % 3 else "b", "split": "dev" if i % 4 else "holdout"})
                               for i in range(40)) + "\n")
    listed = tmp_path / "b.json"
    listed.write_text(json.dumps([{"x_m": 0.5, "kind": "c", "split": "dev"}]))
    (tmp_path / "kit").mkdir()
    out = tmp_path / "site"
    result = subprocess.run([sys.executable, "-m", "traj_compare.record_coverage", str(lines), str(listed), "--out", str(out),
                             "--group-by", "kind", "--split", "split", "--range", "x_m", "0", "5", "--kit", "../kit",
                             "--title", "CLI rows"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "coverage.json").read_text())
    assert payload["source"]["records"] == 41 and payload["title"] == "CLI rows"
    assert payload["source"]["group_by"] == "kind" and payload["support"]["reference"] == "dev"
    assert (payload["hist"]["x_m"]["low"], payload["hist"]["x_m"]["high"], payload["hist"]["x_m"]["source"]) == (0.0, 5.0, "given")
    assert (out / "index.html").is_file() and 'src="../kit/data-ui.js"' in (out / "index.html").read_text()
    assert str(out / "index.html") in result.stdout
