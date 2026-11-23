"""Coverage CLI and the analysis edges the acceptance tests do not pin (docs/COVERAGE.md).

`python -m traj_compare.coverage <npz|dir ...> --out DIR [--tool ...] [--title T]` reads robot_msgs .npz messages and
writes DIR/coverage.json (and DIR/index.html once the page viewer exists). Plus: write_page sets back/siblings on a
copy, the viewers load lazily, and NaN or limit-free input still gives strict JSON.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from robot_msgs._core import save_npz
from robot_msgs.std import Header
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory

import traj_compare.coverage as coverage_package
from traj_compare.coverage import analyze
from traj_compare.coverage.__main__ import main

JOINTS = ("a", "b")
LIMITS = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -1.0]),
                     max_position=np.array([math.pi, 1.0]), max_velocity=np.array([2.0, 2.0]),
                     max_acceleration=np.array([10.0, 10.0]))


def wave(amplitude: float, name: str | None = None, limits=LIMITS) -> JointTrajectory:
    t = np.arange(0.0, 4.0, 0.01)
    positions = amplitude * np.sin(t)[:, None] * np.array([1.0, 0.5])
    header = Header(meta={"name": name}) if name else Header()
    return JointTrajectory(t=t, joint_names=JOINTS, positions=positions, limits=limits, header=header)


def straight_down_tool(length: int, x: float) -> PoseTrajectory:
    t = np.arange(length) * 0.01
    positions = np.column_stack([np.full(length, x), np.linspace(0.0, 0.1, length), np.full(length, 0.2)])
    down = np.tile([1.0, 0.0, 0.0, 0.0], (length, 1))  # xyzw: half a turn about x, tool z = base -z
    return PoseTrajectory(t=t, positions=positions, orientations=down)


def fake_page_module() -> types.ModuleType:
    """A stand-in page viewer, so these tests never depend on the page lane's own state."""
    module = types.ModuleType("traj_compare.coverage.page")

    def write_coverage_page(payload, path, *, back=(), siblings=()):
        Path(path).write_text(f"<html data-cov-page>{payload['title']}</html>", "utf-8")
        return Path(path)

    module.write_coverage_page = write_coverage_page
    return module


@pytest.fixture()
def npz_dataset(tmp_path) -> tuple[Path, Path]:
    joints, tools = tmp_path / "joints", tmp_path / "tools"
    joints.mkdir()
    tools.mkdir()
    save_npz(wave(0.5, name="small lap"), joints / "01_small.npz")
    save_npz(wave(0.9), joints / "02_big.npz")
    save_npz(straight_down_tool(400, 0.3), tools / "01_small.npz")
    save_npz(straight_down_tool(400, 0.4), tools / "02_big.npz")
    return joints, tools


def test_the_cli_reads_npz_files_and_writes_strict_json(npz_dataset, tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "traj_compare.coverage.page", None)  # the page viewer not installed
    monkeypatch.delattr(coverage_package, "page", raising=False)
    joints, tools = npz_dataset
    out = tmp_path / "out"
    assert main([str(joints), "--tool", str(tools), "--out", str(out), "--title", "Two laps"]) == 0
    text = (out / "coverage.json").read_text("utf-8")
    payload = json.loads(text, parse_constant=lambda token: pytest.fail(f"non-strict JSON token {token}"))
    assert payload["schema"] == "traj_compare.coverage/1"
    assert payload["title"] == "Two laps"
    assert [row["name"] for row in payload["trajectories"]] == ["small lap", "02_big"]  # header name, else file name
    assert payload["source"]["samples"] == 800
    assert payload["tool"] is not None and len(payload["tool"]["spaghetti"]) == 2
    assert not (out / "index.html").exists()
    printed = capsys.readouterr().out
    assert "coverage.json" in printed and "not installed yet" in printed


def test_the_cli_writes_the_page_when_the_page_viewer_is_there(npz_dataset, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "traj_compare.coverage.page", fake_page_module())
    monkeypatch.delattr(coverage_package, "page", raising=False)
    joints, _ = npz_dataset
    out = tmp_path / "with_page"
    assert main([str(joints), "--out", str(out), "--title", "Two laps"]) == 0
    assert (out / "index.html").read_text("utf-8") == "<html data-cov-page>Two laps</html>"
    assert (out / "coverage.json").is_file()


def test_the_cli_runs_as_a_module(npz_dataset, tmp_path):
    joints, _ = npz_dataset
    out = tmp_path / "module"
    # runpy.run_module is what `python -m` runs; the page viewer is masked so only this lane's code is measured
    script = ("import runpy, sys; sys.modules['traj_compare.coverage.page'] = None; sys.argv[0] = 'coverage'; "
              "runpy.run_module('traj_compare.coverage', run_name='__main__', alter_sys=True)")
    done = subprocess.run([sys.executable, "-c", script, str(joints / "02_big.npz"), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "not installed yet" in done.stdout
    assert json.loads((out / "coverage.json").read_text("utf-8"))["source"]["trajectories"] == 1


def test_the_cli_refuses_a_pose_trajectory_as_a_joint_trajectory(npz_dataset, tmp_path):
    _, tools = npz_dataset
    with pytest.raises(SystemExit, match="PoseTrajectory.*--tool"):
        main([str(tools), "--out", str(tmp_path / "wrong")])


def test_the_cli_refuses_a_tool_count_that_does_not_match(npz_dataset, tmp_path):
    joints, tools = npz_dataset
    with pytest.raises(SystemExit, match="1 pose trajectories for 2"):
        main([str(joints), "--tool", str(tools / "01_small.npz"), "--out", str(tmp_path / "wrong")])


def test_write_page_sets_back_and_siblings_on_a_copy(monkeypatch, tmp_path):
    seen = {}
    page = types.ModuleType("traj_compare.coverage.page")

    def write_coverage_page(payload, path, *, back=(), siblings=()):
        seen.update(payload=payload, back=back, siblings=siblings)
        return Path(path)

    page.write_coverage_page = write_coverage_page
    monkeypatch.setitem(sys.modules, "traj_compare.coverage.page", page)
    coverage = analyze(wave(0.5))
    coverage.write_page(tmp_path / "index.html", back=[("Dataset", "../index.html")],
                        siblings=[{"label": "rung 0.5", "href": "../r05/index.html", "group": "rung"}])
    assert seen["payload"]["back"] == [["Dataset", "../index.html"]]
    assert seen["payload"]["siblings"] == [{"label": "rung 0.5", "href": "../r05/index.html", "group": "rung",
                                            "current": False}]
    assert coverage.payload["back"] == [] and coverage.payload["siblings"] == []  # the analysis is untouched


def test_the_viewers_load_lazily_and_unknown_names_still_fail():
    assert callable(coverage_package.analyze)
    with pytest.raises(AttributeError):
        coverage_package.no_such_viewer  # noqa: B018


def test_nan_samples_and_no_limits_still_give_strict_json():
    trajectory = wave(0.5, limits=None)
    positions = np.array(trajectory.positions)
    positions[5:9, 0] = np.nan
    payload = analyze(trajectory.replace(positions=positions)).payload
    json.dumps(payload, allow_nan=False)
    assert {bound["source"] for by_signal in payload["limits"].values() for bound in by_signal.values()} == {"data"}
    assert all(math.isfinite(row["value"]) for row in payload["numbers"])


def test_samples_past_the_histogram_edges_are_counted_not_hidden():
    trajectory = wave(0.5)
    positions = np.array(trajectory.positions)
    positions[:3, 1] = 5.0  # joint b's range is +-1, the histogram runs to +-1.16
    hist = analyze(trajectory.replace(positions=positions)).payload["hist"]["b"]["q"]
    assert hist["beyond_edges"] == 3 and hist["outside"] == 3
    assert sum(hist["counts"]) == len(positions) - 3
    assert hist["max"] == pytest.approx(5.0)
