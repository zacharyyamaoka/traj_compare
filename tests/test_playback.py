"""Playback in a real browser: the picture of a camera overlay never freezes or drifts off the plot cursor.

The rack sensors report (2026-10-21) froze: a play started mid-GOP (keyframes every 8.3 s) re-seeked
every tick and showed its last frame for ~3 s while the cursor ran on. This drives a toy report with
long-GOP overlay videos in headless Chrome, presses play on a freshly opened page, and logs every frame
the compositor presents (requestVideoFrameCallback) against the cursor.

Needs Chrome, ffmpeg and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT`` = its package directory, default
the aruco-studio checkout's); skipped otherwise. Run (from a fresh terminal):

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_playback.py
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from traj_compare import CameraOverlay, Comparison, Situation, write_comparison_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
FPS = 30
T0_S = -5.0  # the recording starts 5 s before the trajectory
VIDEO_S = 20.0

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node") and shutil.which("ffmpeg")),
    reason="needs Node Playwright, Chrome and ffmpeg",
)

DRIVER = r"""
const { chromium } = require(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 1600 } })).newPage();
  await page.goto('file://' + process.argv[3]);
  await page.waitForFunction(() => {
    const p = window.TrajCompare && TrajCompare.state.pages[0];
    return p && p.videos.filter((e) => e.el.duration > 0).length === 2;
  }, null, { timeout: 30000 });
  await page.waitForTimeout(1000);
  const log = await page.evaluate(async () => {
    const p = TrajCompare.state.pages[0];
    const out = [];
    p.videos.forEach((entry) => {
      const onFrame = (now, meta) => {
        if (p.transport.playing) out.push({ name: entry.sit.name, t0: entry.t0, media: meta.mediaTime, cursor: p.transport.t, now: now });
        entry.el.requestVideoFrameCallback(onFrame);
      };
      entry.el.requestVideoFrameCallback(onFrame);
    });
    // a freshly opened page: cursor at the end, the videos parked there; then play
    // The cursor each animation frame paints, logged AFTER the transport's own tick in the same frame: an
    // rVFC callback runs before the frame's rAF callbacks with the same timestamp, so the pairing is by
    // that timestamp, not by the cursor value the rVFC callback happens to read.
    const cursors = {};
    const started = performance.now();
    p.transport.play();
    const onAnimationFrame = (now) => {
      cursors[now] = p.transport.t;
      if (p.transport.playing) requestAnimationFrame(onAnimationFrame);
    };
    requestAnimationFrame(onAnimationFrame);
    await new Promise((resolve) => setTimeout(resolve, 4000));
    p.transport.pause();
    out.forEach((frame) => { frame.cursor = frame.now in cursors ? cursors[frame.now] : null; });
    return { frames: out, started: started };
  });
  console.log(JSON.stringify(log));
  await browser.close();
})();
"""


def long_gop_video(path: Path, hue: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            f"testsrc2=size=1280x720:rate={FPS}:duration={VIDEO_S}", "-vf", f"hue=h={hue}",
            "-c:v", "libx264", "-g", "250", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ],
        check=True,
    )  # fmt: skip


def test_play_from_a_fresh_page_never_freezes_and_stays_on_the_cursor(tmp_path):
    long_gop_video(tmp_path / "real.mp4", 0)
    long_gop_video(tmp_path / "sim.mp4", 90)
    t = np.linspace(0.0, 10.0, 501)
    q = np.column_stack([0.5 * np.sin(t)])
    comparison = Comparison(
        title="playback", joint_names=["j"], target=Situation(name="target", t=t, q=q),
        situations=[Situation(name="real", t=t, q=q)],
        overlays=[CameraOverlay(name="cam", real_video="real.mp4", sims=[("sim", "sim.mp4")], t0_s=T0_S)],
    )  # fmt: skip
    report = write_comparison_report(comparison, tmp_path)
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(
        ["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(report), str(CHROME)],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    log = json.loads(result.stdout.strip().splitlines()[-1])
    for name in ("overlay:cam:real", "overlay:cam:sim"):
        frames = [frame for frame in log["frames"] if frame["name"] == name]
        presented = np.array([frame["now"] for frame in frames])
        paired = [frame for frame in frames if frame["cursor"] is not None]
        offsets = np.array([round(frame["media"] * FPS) - np.floor((frame["cursor"] - frame["t0"]) * FPS + 1e-6) for frame in paired])
        gaps = np.diff(np.concatenate([[log["started"]], presented])) / 1e3
        print(f"\n{name}: {len(frames)} frames in 4 s ({len(paired)} paired with their frame's cursor), longest gap {gaps.max() * 1e3:.0f} ms, index offsets {dict(zip(*np.unique(offsets, return_counts=True)))}")
        # the old loop presented nothing for the ~3 s to the next keyframe; the fix holds the cursor <= ~0.5 s for a seek
        assert gaps.max() < 0.6, name
        # WHY 60 %: headless Chrome decodes two 720p streams in software and drops frames; a freeze is the gap above
        assert len(frames) > 0.6 * 4 * FPS, name
        # every presented frame is the grid frame the cursor painted with it points at, or its neighbour
        assert len(paired) > 0.5 * len(frames), name
        # WHY 90 %: headless software decode drops and bunches frames; the old loop sat at +2 for a whole camera
        assert np.mean(np.abs(offsets) <= 1) > 0.9, name
        assert np.max(np.abs(offsets)) <= 2, name
