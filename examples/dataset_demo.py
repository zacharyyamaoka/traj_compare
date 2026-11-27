"""The dataset view on a planar 2R arm: twelve runs, three series, drill down into any one.

Each run is one pass over a "tape" (a reference swing): the recorded sim (`sim_record`), the sim after
five twin iterations (`sim_it5`) and the real arm, with different lags, biases and noise per series.
Tags (tape, conveyor speed, gain set, held out) make the table filterable; the tape is the group of
the ISO 9283 cards; tolerances give each run a verdict; `primary` says `sim` means `sim_it5`, so the
default view shows three pairs instead of six. Run 0 also carries a video (synced to the real series)
and an extra clip, so its drill-down shows both.

    uv run --extra rerun --directory ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare python examples/dataset_demo.py --out /tmp/dataset_demo
    python -m traj_compare.serve /tmp/dataset_demo

Without ``--eager`` the per-run reports are built the first time you open one (through ``traj_compare.serve``);
with it, all twelve are built now.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from robot_msgs.compare import JointTolerance, Tolerances, compare
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from traj_compare import (
    BarChart,
    BarSeries,
    MetricCard,
    ReportPage,
    RobotDisplay,
    Run,
    write_dataset_report,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the poses / robot specs below import this module
from tracking_errors_demo import L1_M, L2_M, joint_path, l2_tip_fk  # noqa: E402

JOINTS = ("j1", "j2")
RATE_HZ = 200.0
DURATION_S = 3.6
TIME = np.linspace(0.0, DURATION_S, int(DURATION_S * RATE_HZ) + 1)
RUNS = 12


def tape_path(tape: str, t: np.ndarray) -> np.ndarray:
    """Tape A is the swing of tracking_errors_demo; tape B swings further and then ends a little short."""
    q = joint_path(t)
    if tape == "B":
        q = q * np.array([1.15, 0.8]) + np.array([0.0, 0.1])
    return q


def l2_tip_poses(trajectory: JointTrajectory) -> PoseTrajectory:
    """The `poses` spec: the L2 tip of the planar arm."""
    return PoseTrajectory.from_matrices(
        trajectory.t, l2_tip_fk(trajectory.positions), child_frame_id="L2 tip", header=trajectory.header
    )


def _box(length: float, width: float) -> np.ndarray:
    """A box from x = 0 to `length`, `width` square, as 12 triangles."""
    x0, x1, h = 0.0, length, width / 2
    corners = np.array([[x, y, z] for x in (x0, x1) for y in (-h, h) for z in (-h, h)], dtype=np.float32)
    faces = [
        (0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
        (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3),
    ]  # fmt: skip
    return corners[np.array(faces)]


def planar_robot() -> RobotDisplay:
    """The `robot` spec: two thin links, posed by the joint angles."""

    def link_fk(q: np.ndarray) -> np.ndarray:
        poses = np.tile(np.eye(4), (len(q), 2, 1, 1))
        for link, angle in enumerate((q[:, 0], q[:, 0] + q[:, 1])):
            poses[:, link, 0, 0], poses[:, link, 0, 1] = np.cos(angle), -np.sin(angle)
            poses[:, link, 1, 0], poses[:, link, 1, 1] = np.sin(angle), np.cos(angle)
        poses[:, 1, 0, 3] = L1_M * np.cos(q[:, 0])
        poses[:, 1, 1, 3] = L1_M * np.sin(q[:, 0])
        return poses

    return RobotDisplay(
        link_names=["upper arm", "forearm"],
        link_meshes=[_box(L1_M, 0.03), _box(L2_M, 0.024)],
        link_fk=link_fk,
        link_colors=["#888888", None],
    )


def _trajectory(q: np.ndarray) -> JointTrajectory:
    return JointTrajectory(t=TIME, joint_names=JOINTS, positions=q)


def make_run(index: int, rng: np.random.Generator, media_dir: Path | None) -> Run:
    tape = "AB"[index % 2]
    speed = (0.5, 1.0)[(index // 2) % 2]
    gainset = ("stock", "ram")[(index // 4) % 2]
    reference = _trajectory(tape_path(tape, TIME))

    def series(lag_s: float, bias: tuple[float, float], noise_rad: float) -> JointTrajectory:
        q = tape_path(tape, TIME - lag_s) + np.array(bias)
        return _trajectory(q + noise_rad * rng.standard_normal(q.shape))

    # The faster the belt, the later the real arm; "ram" gains shave a little lag off.
    real_lag = 0.008 + 0.022 * speed - (0.004 if gainset == "ram" else 0.0) + 0.0015 * rng.standard_normal()
    run = Run(
        name=f"rep {index:02d}",
        reference=reference,
        measured={
            "sim_record": series(0.008, (0.004, 0.0), 0.0004),
            "sim_it5": series(0.022 + 0.001 * rng.standard_normal(), (0.0015, -0.001), 0.0004),
            "real": series(real_lag, (0.0025 * (1 + index % 4), 0.0012 * (index % 3 - 1)), 0.0012),
        },
        tags={"tape": tape, "speed": speed, "gainset": gainset, "held_out": index % 5 == 4},
        title=f"Rep {index:02d} · tape {tape} · speed {speed}",
    )
    if index == 0 and media_dir is not None:
        run.media = {"real": media_dir / "real.mp4", "side_by_side": media_dir / "side_by_side.mp4"}
        run.media_start_s = {"real": 0.25, "side_by_side": 0.0}
    return run


def make_clips(media_dir: Path) -> Path | None:
    """Two stand-in clips (a camera stream, a side-by-side) with ffmpeg; None when it is absent."""
    if shutil.which("ffmpeg") is None:
        return None
    media_dir.mkdir(parents=True, exist_ok=True)
    for name, source in (("real", "testsrc2"), ("side_by_side", "testsrc")):
        subprocess.run(  # noqa: S603 - fixed argv
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"{source}=size=480x270:rate=30",
                "-t", f"{DURATION_S + 0.5}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(media_dir / f"{name}.mp4"),
            ],
            check=True,
        )  # fmt: skip
    return media_dir


def summary_page(runs: list[Run]) -> ReportPage:
    """What the twin iterations bought, per tape: RMS of each sim against the real run, in degrees."""
    tapes = sorted({str(run.tags["tape"]) for run in runs})

    def gap(series: str, tape: str) -> float:
        values = [
            np.degrees(
                np.mean([compare(run.measured[series], run.measured["real"]).metrics[f"positions/{j}"].rms for j in JOINTS])
            )
            for run in runs
            if run.tags["tape"] == tape
        ]
        return float(np.mean(values))

    before = np.mean([gap("sim_record", tape) for tape in tapes])
    after = np.mean([gap("sim_it5", tape) for tape in tapes])
    return ReportPage(
        title="Sim to real",
        name="summary",
        metrics=[
            MetricCard("Sim vs real, recorded", f"{before:.2f}°", "mean joint RMS, all runs", "neutral"),
            MetricCard("Sim vs real, after 5 iterations", f"{after:.2f}°", f"{100 * (1 - after / before):.0f}% closer", "positive"),
        ],
        charts=[
            BarChart(
                title="Sim error against the real arm",
                categories=[f"tape {tape}" for tape in tapes],
                series=[
                    BarSeries("sim_record", [gap("sim_record", tape) for tape in tapes]),
                    BarSeries("sim_it5", [gap("sim_it5", tape) for tape in tapes]),
                ],
                unit="°",
                decimals=2,
            )
        ],
    )


def build(out: Path, eager: bool = False, runs_count: int = RUNS, static: bool = False) -> Path:
    """``static``: for a host with no server (the landing page on GitHub Pages): every drill-down built now, no
    .rrd and no Rerun actions, commands name the folder relatively, no data-ui tables.

    WHY (2026-11-27, the public landing page): a static host cannot build a drill-down on first open, and twelve eager
    runs with their .rrd files and data-ui tables weigh ~200 MB; four static runs are ~20 MB."""
    rng = np.random.default_rng(2026)
    media_dir = make_clips(out / "_clips")
    runs = [make_run(index, rng, media_dir) for index in range(runs_count)]
    tolerances = Tolerances(
        path=tuple(JointTolerance(name=joint, position=0.034) for joint in JOINTS),
        goal=tuple(JointTolerance(name=joint, position=0.012) for joint in JOINTS),
        stopped_velocity_tolerance=0.0,  # positions only: the runs record no velocities
    )
    index = write_dataset_report(
        runs,
        out,
        title="Planar 2R · twin iterations on two tapes",
        group_by=("tape",),
        tolerances=tolerances,
        poses="dataset_demo:l2_tip_poses",
        robot="dataset_demo:planar_robot",
        summary=summary_page(runs),
        primary={"sim": "sim_it5"},
        drill_down="eager" if eager or static else "lazy",
        data_ui=not static,
        **({"rerun_server": False, "rerun": False, "command_root": "dataset"} if static else {}),
    )
    if media_dir is not None:
        shutil.rmtree(media_dir)  # write_dataset_report copied the clips into runs/<slug>/media/
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("/tmp/dataset_demo"))
    parser.add_argument("--eager", action="store_true", help="build every run's drill-down now (default: on first open)")
    parser.add_argument("--runs", type=int, default=RUNS, help=f"how many runs (default {RUNS})")
    parser.add_argument("--static", action="store_true",
                        help="for a static host: eager drill-downs, no .rrd, no data-ui tables, relative commands")
    args = parser.parse_args()
    print(build(args.out, eager=args.eager, runs_count=args.runs, static=args.static))
