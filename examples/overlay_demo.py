"""Camera-overlay + motor-current demo: a toy 1-DOF rack with synthetic video.

Builds two short synthetic mp4s with ffmpeg (a stand-in "real" camera stream and
two stand-in sim renders), a target / real / twin triple that carries motor
current, and one report whose Camera section stacks the real stream under the
selected sim render.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    uv run python examples/overlay_demo.py --out /tmp/overlay_demo

then open ``/tmp/overlay_demo/report.html``. The videos sit beside it, so the
report must be opened from that directory (paths are relative, like
``Situation.video``).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import numpy as np

from traj_compare import CameraOverlay, Comparison, Situation, write_comparison_report

DURATION_S = 6.0
VIDEO_T0_S = 0.5  # the camera started rolling half a second into the trajectory


def make_video(path: Path, source: str, filters: str = "") -> None:
    """One 640x360, 30 fps, 6 s H.264 clip from an ffmpeg lavfi test source."""

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required to synthesize the demo videos")
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"{source}=size=640x360:rate=30",
        "-t", str(DURATION_S),
    ]  # fmt: skip
    if filters:
        command += ["-vf", filters]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True)


def toy_rack() -> Comparison:
    """1-DOF sweep: target, a laggy noisy "real" run, a closer "twin" run, all with current."""

    t = np.linspace(0.0, DURATION_S, 601)
    q_target = 0.6 * np.sin(2.0 * np.pi * t / DURATION_S)

    def run(lag_s: float, gain: float, friction_a: float, seed: int) -> Situation:
        rng = np.random.default_rng(seed)
        omega = 2.0 * np.pi / DURATION_S
        phase = omega * (t - lag_s)
        q = gain * 0.6 * np.sin(phase) + 0.002 * rng.standard_normal(t.size)
        qd = gain * 0.6 * omega * np.cos(phase)
        qdd = -gain * 0.6 * omega**2 * np.sin(phase)
        # inertial + viscous + Coulomb friction, in amperes, plus sensor noise
        current = 0.35 * qdd + 0.6 * qd + friction_a * np.tanh(qd / 0.05)
        current = current + 0.03 * rng.standard_normal(t.size)
        return Situation(
            name="real" if seed == 1 else "twin",
            title="Real rack" if seed == 1 else "Digital twin",
            t=t,
            q=q,
            qd=qd,
            qdd=qdd,
            current=current[:, None],
        )

    return Comparison(
        title="One-DOF rack — twin vs real",
        joint_names=["CAN 1"],
        target=Situation(name="target", title="Target", t=t, q=q_target),
        situations=[run(0.05, 0.97, 0.20, 1), run(0.01, 0.995, 0.15, 2)],
        default_sections=["joint-q", "joint-current", "camera"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    make_video(out / "real.mp4", "testsrc2")
    make_video(out / "sim_a.mp4", "testsrc2", "hue=h=70,eq=saturation=1.4")
    make_video(out / "sim_b.mp4", "testsrc")

    comparison = toy_rack()
    comparison.overlays = [
        CameraOverlay(
            name="Overhead D405",
            real_video="real.mp4",
            sims=[("MuJoCo render", "sim_a.mp4"), ("Kinematic render", "sim_b.mp4")],
            t0_s=VIDEO_T0_S,
            note="synthetic test patterns standing in for the camera and the sim render",
        )
    ]
    report = write_comparison_report(comparison, out, subtitle="overlay demo")
    print(report)


if __name__ == "__main__":
    main()
