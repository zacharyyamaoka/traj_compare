"""traj_compare as a producer for data-ui's robotics dashboards (written with the code, 2026-11-11).

The interface is data-ui's trajectory contract, version 1 (/home/bam/data-ui/gallery/robotics/CONTRACT.md): the tables a
producer writes, and difference(a, b) (section 5), which must reproduce the contract's own fixture. data-ui's reference
implementation is an oracle here, never imported by the package. Every number must equal ``robot_msgs.compare``'s for the
same inputs, converted at the edge (mm, mrad, degrees); a human-facing view shows degrees, never rad or mrad.
"""

import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.compare import compare
from robot_msgs.trajectory import JointTrajectory

from traj_compare.data_ui import difference, stage_viewer, write_tables
from traj_compare.dataset import Run, write_dataset_report

DATA_UI = Path("/home/bam/data-ui")
ROBOTICS = DATA_UI / "gallery" / "robotics"
ASSETS = Path(__file__).resolve().parent.parent / "src" / "traj_compare" / "assets"
VENDORED = Path(__file__).resolve().parent / "fixtures" / "data_ui_difference"

NAMES = ("j1", "j2")
T = np.linspace(0.0, 2.0, 401)  # 200 Hz: written at 100 Hz (every second row)


def tape(t: np.ndarray, amplitude: float = 0.4) -> np.ndarray:
    phase = np.clip(t / 1.6, 0.0, 1.0)
    s = 0.5 - 0.5 * np.cos(np.pi * phase)
    return np.column_stack([amplitude * s, -0.5 * amplitude * s])


def traj(positions: np.ndarray, t: np.ndarray = T) -> JointTrajectory:
    return JointTrajectory(t=t, joint_names=NAMES, positions=positions)


def make_run(index: int = 0) -> Run:
    return Run(
        name=f"rep {index}",
        reference=traj(tape(T)),
        measured={
            "sim": traj(tape(T - 0.005)),
            "real": traj(tape(T - 0.02) + np.array([0.002 * (index + 1), -0.001])),
        },
        tags={"tape": "A", "speed": 0.5, "kind": "swing"},
    )


def load_fixture():
    """data-ui's checker (stdlib): the live checkout when there is one, else the copy under tests/fixtures."""
    folder = ROBOTICS if (ROBOTICS / "fixture.py").is_file() else VENDORED
    spec = importlib.util.spec_from_file_location("data_ui_robotics_fixture", folder / "fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table(folder: Path, name: str) -> dict:
    return json.loads((folder / f"{name}.json").read_text("utf-8"))


def planar_tool(trajectory: JointTrajectory):
    from dataset_fixture_fk import tool_xy

    return tool_xy(trajectory)


# ── difference(a, b) is the contract's ───────────────────────────────────────


def test_difference_reproduces_the_contracts_fixture():
    fixture = load_fixture()
    problems = fixture.check_difference(poses=difference, samples=difference)
    assert problems == [], "\n".join(problems)


def test_difference_in_the_live_checkout_is_the_copy_we_test_against():
    if not (ROBOTICS / "fixture.py").is_file():
        pytest.skip("the data-ui checkout is absent")
    live = json.loads((ROBOTICS / "fixtures" / "difference" / "diff_poses.json").read_text("utf-8"))["rows"]
    copy = json.loads((VENDORED / "diff_poses.json").read_text("utf-8"))["rows"]
    assert live == copy, "data-ui's fixture moved: refresh tests/fixtures/data_ui_difference and the vendored schemas"


def test_vendored_schemas_are_data_uis():
    if not ROBOTICS.is_dir():
        pytest.skip("the data-ui checkout is absent")
    for path in (ASSETS / "data_ui" / "schemas").glob("*.json"):
        assert path.read_text("utf-8") == (ROBOTICS / "schemas" / path.name).read_text("utf-8"), path.name


# ── the tables ───────────────────────────────────────────────────────────────


def written(tmp_path, runs=None, **options) -> Path:
    return write_tables(runs or [make_run(0), make_run(1)], tmp_path / "data-ui", **options)


def contract(name: str) -> dict:
    return json.loads((ASSETS / "data_ui" / "schemas" / f"{name}.schema.json").read_text("utf-8"))


@pytest.mark.parametrize("name", ["runs", "samples", "devices", "diff_samples", "poses", "diff_poses"])
def test_tables_have_the_contracts_required_columns_and_units(tmp_path, name):
    folder = written(tmp_path, poses=planar_tool)
    doc = table(folder, name)
    spec = contract(name)
    units = {field["name"]: field.get("unit") for field in spec["schema"]["fields"]}
    for field in doc["schema"]["fields"]:
        if field["name"] in units:  # a contract column keeps the contract's unit
            assert field.get("unit") == units[field["name"]], (name, field["name"])
        else:  # a producer's own column is declared, and ends in the unit it declares
            assert field["name"] in {"when", "tape", "speed", "e_q_deg", "err_rot_deg"}, (name, field["name"])
    declared = {field["name"] for field in doc["schema"]["fields"]}
    assert doc["rows"], name
    for row in doc["rows"]:
        assert set(spec["required"]) <= row.keys(), (name, sorted(set(spec["required"]) - row.keys()))
        assert set(row) <= declared, (name, sorted(set(row) - declared))
        assert all(not (isinstance(value, float) and not math.isfinite(value)) for value in row.values())


def test_runs_one_row_per_run_with_the_drill_down_url_and_families(tmp_path):
    runs = [make_run(0), make_run(1)]
    folder = tmp_path / "out"
    write_dataset_report(runs, folder, title="runs", data_ui=True)
    rows = table(folder / "data-ui", "runs")["rows"]
    assert [row["run"] for row in rows] == ["rep 0", "rep 1"]
    first = rows[0]
    assert first["url"] == "../runs/rep-0/report.html"
    assert (folder / "data-ui" / first["url"]).parent.is_dir()  # the classic drill-down's folder (the page builds lazily)
    assert first["situations"] == ["target", "sim", "real"] and first["devices"] == list(NAMES)
    assert first["kind"] == "swing" and first["tape"] == "A" and first["speed"] == 0.5
    assert first["duration_s"] == pytest.approx(2.0) and first["rate_hz"] == pytest.approx(200.0)
    assert first["display_hz"] == pytest.approx(100.0)
    families = {(r["situation"], r["source"]) for r in table(folder / "data-ui", "samples")["rows"]}
    assert families == {("target", "target"), ("sim", "sim"), ("real", "real")}


def test_samples_are_picked_at_the_display_rate_in_degrees(tmp_path):
    run = make_run(0)
    rows = [r for r in table(written(tmp_path, [run]), "samples")["rows"] if r["situation"] == "real" and r["device"] == "j1"]
    assert len(rows) == 201  # 401 samples at 200 Hz, every second one (a pick, never an average)
    assert rows[1]["t"] == pytest.approx(0.01)
    np.testing.assert_allclose([r["q_deg"] for r in rows], np.degrees(run.measured["real"].positions[::2, 0]), atol=1e-8)


def test_a_series_clock_is_shifted_onto_the_targets_by_its_offset(tmp_path):
    run = make_run(0)
    run.time_offset_s = {"real": 0.02}
    rows = [r for r in table(written(tmp_path, [run]), "samples")["rows"] if r["situation"] == "real" and r["device"] == "j1"]
    assert rows[0]["t"] == pytest.approx(-0.02)
    diff = [r for r in table(written(tmp_path / "again", [run]), "diff_samples")["rows"] if r["situation"] == "real" and r["reference"] == "target"]
    assert diff[0]["t"] == pytest.approx(0.0)  # the first sample of real inside the target's span


def test_diff_samples_are_robot_msgs_compare_in_mrad_and_degrees(tmp_path):
    run = make_run(0)
    folder = written(tmp_path, [run])
    rows = [r for r in table(folder, "diff_samples")["rows"] if (r["situation"], r["reference"], r["device"]) == ("real", "target", "j1")]
    pick = np.arange(0, len(T), 2)
    error = compare(run.reference[pick], run.measured["real"][pick]).error  # target - real, on the rows written
    assert len(rows) == len(error.t)
    np.testing.assert_allclose([r["t"] for r in rows], error.t, atol=1e-9)
    np.testing.assert_allclose([r["e_q_mrad"] for r in rows], error.positions[:, 0] * 1000.0, atol=1e-4)
    np.testing.assert_allclose([r["e_q_deg"] for r in rows], np.degrees(error.positions[:, 0]), atol=1e-6)


def test_pairs_are_each_situation_against_the_target_and_each_sim_against_the_real(tmp_path):
    rows = table(written(tmp_path), "diff_samples")["rows"]
    assert {(r["situation"], r["reference"]) for r in rows} == {("sim", "target"), ("real", "target"), ("sim", "real")}
    assert {r["source"] for r in rows if r["situation"] == "sim"} == {"sim"}  # a's family, so a view needs no join


def test_poses_and_their_differences_when_a_poses_function_is_given(tmp_path):
    run = make_run(0)
    folder = written(tmp_path, [run], poses=planar_tool, frame="base")
    poses = table(folder, "poses")["rows"]
    assert {r["body"] for r in poses} == {"tool"} and {r["frame"] for r in poses} == {"base"}
    real = [r for r in poses if r["situation"] == "real"]
    expected = planar_tool(run.measured["real"][np.arange(0, len(T), 2)])
    np.testing.assert_allclose([[r["x_mm"], r["y_mm"], r["z_mm"]] for r in real], expected.positions * 1000.0, atol=1e-6)
    pick = np.arange(0, len(T), 2)
    error = compare(planar_tool(run.reference[pick]), planar_tool(run.measured["real"][pick])).error
    diff = [r for r in table(folder, "diff_poses")["rows"] if (r["situation"], r["reference"]) == ("real", "target")]
    np.testing.assert_allclose([r["err_mm"] for r in diff], np.linalg.norm(error.positions, axis=1) * 1000.0, atol=1e-5)
    np.testing.assert_allclose([r["err_rot_mrad"] for r in diff], error.channels["rotation_angle"] * 1000.0, atol=1e-4)
    np.testing.assert_allclose([r["err_rot_deg"] for r in diff], np.degrees(error.channels["rotation_angle"]), atol=1e-6)
    assert all(r["ref_quat_w"] >= 0 for r in diff)  # the contract's canonical sign


def test_without_poses_there_are_no_pose_tables(tmp_path):
    folder = written(tmp_path)
    assert not (folder / "poses.json").exists() and not (folder / "diff_poses.json").exists()
    assert not (folder / "links.json").exists()


def test_links_are_written_when_given(tmp_path):
    from robot_msgs.trajectory import PoseTrajectory

    def links(trajectory):
        pose = planar_tool(trajectory)
        return {"tool": PoseTrajectory(t=pose.t, positions=pose.positions, orientations=pose.orientations)}

    doc = table(written(tmp_path, [make_run(0)], links=links), "links")
    assert {"tool_x", "tool_qw"} <= {field["name"] for field in doc["schema"]["fields"]}
    assert {field["name"]: field.get("unit") for field in doc["schema"]["fields"]}["tool_x"] == "mm"
    assert {r["situation"] for r in doc["rows"]} == {"target", "sim", "real"}


def test_media_json_exists_only_when_a_run_has_media(tmp_path):
    assert not (written(tmp_path / "none") / "media.json").exists()
    clip = tmp_path / "real.mp4"
    clip.write_bytes(b"not a video")  # ffprobe cannot read it: fps and duration are null, never made up
    run = make_run(0)
    run.media = {"real": clip}
    run.media_start_s = {"real": 0.25}
    out = tmp_path / "with"
    write_dataset_report([run], out, title="media", data_ui=True)
    (row,) = table(out / "data-ui", "media")["rows"]
    assert row["src"] == "../runs/rep-0/media/real.mp4" and (out / "runs" / "rep-0" / "media" / "real.mp4").is_file()
    assert (row["run"], row["camera"], row["kind"], row["t0"]) == ("rep 0", "real", "rgb", 0.25)
    assert row["fps"] is None and row["duration"] is None and row["basis"] is None


def test_started_is_given_or_it_is_the_write_time_and_says_so(tmp_path):
    rows = table(written(tmp_path / "default"), "runs")["rows"]
    assert "was written" in rows[0]["note"] and re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$", rows[0]["started"])
    given = table(written(tmp_path / "given", started="2026-11-10T09:30:00-08:00"), "runs")["rows"]
    assert given[0]["started"] == "2026-11-10T09:30:00-08:00" and "note" not in given[0] and given[0]["when"] == "Nov 10 09:30"


def test_a_series_called_target_is_refused(tmp_path):
    run = make_run(0)
    run.measured = {"target": run.measured["real"]}
    with pytest.raises(ValueError, match="target"):
        written(tmp_path, [run])


# ── the dashboard ────────────────────────────────────────────────────────────


def test_views_base_shows_degrees_and_mm_never_mrad(tmp_path):
    for with_poses in (False, True):
        folder = written(tmp_path / str(with_poses), poses=planar_tool if with_poses else None)
        text = (folder / "views.base").read_text("utf-8")
        shown = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "mrad" not in shown and "rad" not in re.sub(r"\bgradient\b", "", shown)
        assert "e_q_deg" in shown and "unit: '°'" in shown
        assert ("err_mm" in shown) == with_poses
        assert ("trajectory3d" in shown) == with_poses
        assert "media.json" not in shown


def test_views_base_checks_clean_in_data_ui(tmp_path):
    node = shutil.which("node")
    if node is None or not (DATA_UI / "bin" / "data-ui.mjs").is_file():
        pytest.skip("node or the data-ui checkout is absent")
    clip = tmp_path / "real.mp4"
    clip.write_bytes(b"x")
    run = make_run(0)
    run.media = {"real": clip}
    out = tmp_path / "out"
    write_dataset_report([run, make_run(1)], out, title="check", poses="dataset_fixture_fk:tool_xy", data_ui=True)
    result = subprocess.run(
        [node, str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(out / "data-ui" / "views.base")],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert result.returncode == 0 and "0 errors, 0 warnings" in result.stdout, result.stdout + result.stderr


# ── the degrees rule in the run view and the dataset view ────────────────────


@pytest.mark.parametrize("asset", ["plots.js", "dataset.js", "style.css", "dataset.css"])
def test_no_mrad_in_the_human_facing_assets(asset):
    assert "mrad" not in (ASSETS / asset).read_text("utf-8")


def test_stage_viewer_links_a_built_kit_and_writes_the_host_page(tmp_path):
    kit = tmp_path / "somewhere" / "kit"
    kit.mkdir(parents=True)
    (kit / "data-ui.js").write_text("// stand-in", encoding="utf-8")
    (tmp_path / "out").mkdir()
    page = stage_viewer(tmp_path / "out", kit, title="A <b>")
    assert page.name == "data-ui.html" and (tmp_path / "out" / "kit" / "data-ui.js").is_file()
    assert 'src="data-ui/views.base"' in page.read_text("utf-8") and "A &lt;b>" in page.read_text("utf-8")
    assert stage_viewer(tmp_path / "out", tmp_path / "no-kit") is None
