"""The dataset view: many runs at a glance, then drill down (written before the code, 2026-11-11).

Zach: "across a bunch of runs, where was the error the highest… then drill down into particular
runs and view that recording in Rerun or our own viewer", and "by stock standard traj compare
should also do aggregate statistics across a bunch of runs". Seams agreed with the Sim to Real
agent: robot_msgs.compare = math, traj_compare = the run view + this dataset view, sim2real =
domain (runs, tags, tolerances). Sim-to-real is three-way per run (target, sim, real).

Every number must equal robot_msgs.compare's for the same inputs. Angles are SI in rows/npz and
degrees in every human-facing view.
"""

import json
import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from robot_msgs._core import load_npz
from robot_msgs.compare import JointTolerance, Tolerances, aggregate, check, compare
from robot_msgs.trajectory import JointTrajectory

from traj_compare.dataset import Run, build_drill_down, default_pairs, write_dataset_report

NAMES = ("j1", "j2")
T = np.linspace(0.0, 2.0, 401)


def tape(t: np.ndarray, amplitude: float = 0.4) -> np.ndarray:
    phase = np.clip(t / 1.6, 0.0, 1.0)
    s = 0.5 - 0.5 * np.cos(np.pi * phase)
    return np.column_stack([amplitude * s, -0.5 * amplitude * s])


def traj(positions: np.ndarray, t: np.ndarray = T) -> JointTrajectory:
    return JointTrajectory(t=t, joint_names=NAMES, positions=positions)


def make_run(index: int, tape_name: str = "A", amplitude: float = 0.4) -> Run:
    reference = traj(tape(T, amplitude))
    sim = traj(tape(T - 0.005, amplitude))
    bias = np.array([0.002 * (index + 1), -0.001])  # each real run sits a little further off
    real = traj(tape(T - 0.02, amplitude) + bias)
    return Run(
        name=f"can13 rep {index}",
        reference=reference,
        measured={"sim": sim, "real": real},
        tags={"rig": "ur_wrist", "can": 13, "tape": tape_name, "speed": 0.5, "held_out": index == 2},
    )


def rows_of(output) -> list[dict]:
    return json.loads((output / "rows.json").read_text("utf-8"))


def pick(rows, *, run, pair, metric, stat):
    matches = [
        row for row in rows
        if row["run"] == run and tuple(row["pair"]) == pair and row["metric"] == metric and row["stat"] == stat
    ]  # fmt: skip
    assert len(matches) == 1, (run, pair, metric, stat, len(matches))
    return matches[0]


def dataset_payload(output) -> dict:
    html = (output / "index.html").read_text("utf-8")
    match = re.search(
        r'<script type="application/json" id="traj-compare-dataset">(.*?)</script>', html, re.S
    )
    assert match, "index.html has no dataset payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_default_pairs_are_target_to_each_then_each_to_each():
    assert default_pairs(["sim", "real"]) == [
        ("reference", "sim"),
        ("reference", "real"),
        ("sim", "real"),
    ]
    assert default_pairs(["real"]) == [("reference", "real")]


def test_rows_equal_robot_msgs_for_every_pair_with_tags_as_columns(tmp_path):
    runs = [make_run(i) for i in range(3)]
    write_dataset_report(runs, tmp_path, title="Wrist coverage")
    rows = rows_of(tmp_path)
    run = runs[1]

    expected = compare(run.reference, run.measured["real"]).metrics["positions/j1"]
    row = pick(rows, run=run.name, pair=("reference", "real"), metric="positions/j1", stat="rms")
    assert row["value"] == pytest.approx(expected.rms)
    assert row["unit"] == "rad"  # SI in the data
    assert (row["rig"], row["can"], row["tape"], row["held_out"]) == ("ur_wrist", 13, "A", False)

    sim_real = compare(run.measured["sim"], run.measured["real"]).metrics["positions/j2"]
    row = pick(rows, run=run.name, pair=("sim", "real"), metric="positions/j2", stat="max_abs")
    assert row["value"] == pytest.approx(sim_real.max_abs)


def test_verdict_rows_equal_robot_msgs_check(tmp_path):
    tolerances = Tolerances(
        path=(JointTolerance(name="j1", position=0.01), JointTolerance(name="j2", position=0.01))
    )
    runs = [make_run(i) for i in range(3)]
    write_dataset_report(runs, tmp_path, title="Wrist", tolerances=tolerances)
    payload = dataset_payload(tmp_path)
    for run in runs:
        expected = check(run.reference, run.measured["real"], tolerances)
        entry = next(
            item for item in payload["rows"]
            if item["run"] == run.name and tuple(item["pair"]) == ("reference", "real")
        )  # fmt: skip
        assert entry["verdict"]["code_name"] == expected.code_name


def test_iso_aggregate_per_group_and_series_equals_robot_msgs(tmp_path):
    group_a = [make_run(i, "A") for i in range(3)]
    group_b = [make_run(i, "B", amplitude=0.6) for i in range(3, 5)]
    for run in group_b:
        run.name = run.name + " B"
    write_dataset_report(group_a + group_b, tmp_path, title="Wrist", group_by=("tape",))
    payload = dataset_payload(tmp_path)
    expected = aggregate(group_a[0].reference, [run.measured["real"] for run in group_a])
    card = payload["aggregates"]["tape=A"]["real"]
    assert card["runs"] == [run.name for run in group_a]
    assert card["accuracy"]["positions/j1"]["max_abs"] == pytest.approx(
        expected.accuracy.metrics["positions/j1"].max_abs
    )
    assert card["repeatability"]["positions/j1"]["max"] == pytest.approx(
        expected.metrics["positions/j1"].max
    )
    assert "tape=B" in payload["aggregates"]


def test_group_with_different_references_is_named_not_aggregated(tmp_path):
    runs = [make_run(0, "A"), make_run(1, "A", amplitude=0.5)]
    write_dataset_report(runs, tmp_path, title="Mixed", group_by=("tape",))
    payload = dataset_payload(tmp_path)
    assert payload["aggregates"]["tape=A"]["status"] == "references differ"


def test_peak_time_is_where_the_error_is_largest(tmp_path):
    run = make_run(0)
    write_dataset_report([run], tmp_path, title="Peak")
    payload = dataset_payload(tmp_path)
    entry = next(
        item for item in payload["rows"]
        if item["run"] == run.name and tuple(item["pair"]) == ("reference", "real")
    )  # fmt: skip
    error = compare(run.reference, run.measured["real"]).error
    expected = float(error.t[np.nanargmax(np.abs(error.positions[:, 0]))])
    assert entry["peak_t"]["j1"] == pytest.approx(expected)


def test_human_view_is_in_degrees(tmp_path):
    write_dataset_report([make_run(0)], tmp_path, title="Units")
    payload = dataset_payload(tmp_path)
    assert payload["angle_unit"] == "deg"
    html = (tmp_path / "index.html").read_text("utf-8")
    assert "°" in html
    assert "mrad" not in html


def test_runs_are_stored_file_first_and_round_trip(tmp_path):
    run = make_run(0)
    write_dataset_report([run], tmp_path, title="Files")
    folders = [path for path in (tmp_path / "runs").iterdir() if path.is_dir()]
    assert len(folders) == 1
    manifest = json.loads((folders[0] / "manifest.json").read_text("utf-8"))
    assert manifest["name"] == run.name
    assert manifest["tags"]["can"] == 13
    assert [tuple(pair) for pair in manifest["pairs"]] == default_pairs(["sim", "real"])
    # one robot_msgs npz per series, loadable with robot_msgs alone
    reference = load_npz(folders[0] / "reference.npz")
    real = load_npz(folders[0] / "real.npz")
    np.testing.assert_allclose(reference.positions, run.reference.positions)
    np.testing.assert_allclose(real.positions, run.measured["real"].positions)
    assert (folders[0] / "sim.npz").is_file()


def test_lazy_drill_down_builds_one_run_report_with_a_tab_per_pair(tmp_path):
    run = make_run(0)
    write_dataset_report([run], tmp_path, title="Lazy", drill_down="lazy")
    folder = next(path for path in (tmp_path / "runs").iterdir() if path.is_dir())
    assert not (folder / "report.html").exists()  # nothing heavy written up front

    report = build_drill_down(tmp_path, run.name)
    assert report == folder / "report.html" and report.is_file()
    html = report.read_text("utf-8")
    payload = json.loads(
        re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</")
    )
    titles = [page["reference_title"] for page in payload["comparisons"]]
    assert len(payload["comparisons"]) == 3  # reference→sim, reference→real, sim→real
    assert any("sim" in title.lower() for title in titles)


def test_eager_drill_down_writes_every_run(tmp_path):
    runs = [make_run(i) for i in range(2)]
    write_dataset_report(runs, tmp_path, title="Eager", drill_down="eager")
    reports = sorted((tmp_path / "runs").glob("*/report.html"))
    assert len(reports) == 2


def test_serve_builds_a_missing_drill_down_on_first_request(tmp_path):
    from traj_compare.serve import make_handler

    run = make_run(0)
    write_dataset_report([run], tmp_path, title="Serve", drill_down="lazy")
    folder = next(path for path in (tmp_path / "runs").iterdir() if path.is_dir())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, spawn=lambda argv: None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/runs/{folder.name}/report.html"
        with urllib.request.urlopen(url, timeout=120) as response:
            assert response.status == 200
            assert b"traj-compare-data" in response.read()
        assert (folder / "report.html").is_file()  # cached for the next click
    finally:
        server.shutdown()


def test_poses_import_spec_adds_tcp_rows(tmp_path):
    run = make_run(0)
    write_dataset_report([run], tmp_path, title="TCP", poses="dataset_fixture_fk:tool_xy")
    rows = rows_of(tmp_path)
    row = pick(rows, run=run.name, pair=("reference", "real"), metric="position", stat="rms")
    assert row["unit"] == "m"
    assert row["value"] > 0.0


# ── additions agreed with the Sim to Real agent (2026-11-11) ────────────────


def twin_iterations_run(index: int = 0) -> Run:
    reference = traj(tape(T))
    return Run(
        name=f"iters {index}",
        reference=reference,
        measured={
            "sim_record": traj(tape(T - 0.015)),
            "sim_it5": traj(tape(T - 0.006)),
            "real": traj(tape(T - 0.02) + [0.002, 0.0]),
        },
        tags={"tape": "A"},
    )


def test_three_or_more_series_get_every_pair_in_rows_and_iso_per_series(tmp_path):
    runs = [twin_iterations_run(i) for i in range(2)]
    assert len(default_pairs(["sim_record", "sim_it5", "real"])) == 6
    write_dataset_report(runs, tmp_path, title="Iterations", group_by=("tape",))
    rows = rows_of(tmp_path)
    pairs = {tuple(row["pair"]) for row in rows if row["run"] == runs[0].name}
    assert pairs == set(default_pairs(["sim_record", "sim_it5", "real"]))
    payload = dataset_payload(tmp_path)
    assert set(payload["aggregates"]["tape=A"]) >= {"sim_record", "sim_it5", "real"}


def test_primary_picks_the_twin_so_the_default_view_is_three_pairs_not_six(tmp_path):
    runs = [twin_iterations_run(0)]
    write_dataset_report(runs, tmp_path, title="Primary", primary={"sim": "sim_it5"})
    payload = dataset_payload(tmp_path)
    # alias "sim" stands for sim_it5; the other sim_* series stay in rows.json, hidden by default
    assert [tuple(pair) for pair in payload["default_pairs"]] == [
        ("reference", "sim_it5"),
        ("reference", "real"),
        ("sim_it5", "real"),
    ]
    assert payload["labels"]["sim_it5"] == "sim"
    assert {tuple(row["pair"]) for row in rows_of(tmp_path)} == set(
        default_pairs(["sim_record", "sim_it5", "real"])
    )


def test_media_is_copied_and_synced_into_the_drill_down(tmp_path):
    clip = tmp_path / "source_clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # stand-in bytes; only the plumbing is under test
    side = tmp_path / "side_by_side.mp4"
    side.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    run = make_run(0)
    run.media = {"real": clip, "side_by_side": side}
    run.media_start_s = {"real": 0.25}
    out = tmp_path / "out"
    write_dataset_report([run], out, title="Media", drill_down="eager")
    folder = next(path for path in (out / "runs").iterdir() if path.is_dir())
    copied = sorted(path.name for path in (folder / "media").iterdir())
    assert copied == ["real.mp4", "side_by_side.mp4"]
    html = (folder / "report.html").read_text("utf-8")
    payload = json.loads(
        re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</")
    )
    # a key equal to a measured series becomes that run's synced video, on its own time base
    situations = [s for page in payload["comparisons"] for s in page["situations"] if s["name"] == "real"]
    assert situations and all(s.get("video", "").endswith("real.mp4") for s in situations)
    assert all(s.get("video_start_s") == pytest.approx(0.25) for s in situations)
    # any other key is an extra clip on the run page
    assert "side_by_side.mp4" in html
