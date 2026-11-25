#!/usr/bin/env python3
"""Review report: robot_msgs' stock JointTrajectory viewer in Rerun, with the URDF (2026-11-24).

    python3 /home/bam/traj_compare/docs/rerun_stock_viewer_2026-11-24/build_report.py

Reads the stills and the hero frames shot in the real Rerun 0.40 web viewer (headless, the playhead set through the
viewer's own handle, docs/proposals/rerun-joint-trajectory-2026-11-24/shoot.cjs) from /tmp/claude-1000/rerun-stock-viewer-2026-11-24/
and writes /home/bam/traj_compare/reports/media/rerun-stock-viewer-2026-11-24.html with its media beside it.
"""

from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path

SRC = Path("/tmp/claude-1000/rerun-stock-viewer-2026-11-24")
OUT = Path("/home/bam/traj_compare/reports/media/rerun-stock-viewer-2026-11-24.html")
MEDIA = OUT.with_suffix("")
REL = MEDIA.name

TABS = [
    ("shots/dev-029-2-t1.8.png", "q (opens here)", "A strip per joint in degrees, the grey limit lines, \"travel 130° · 38° to limit\" in each title."),
    ("shots/dev-029-tab-qd-1-t1.8.png", "qd", "Joint speed in °/s against ±max velocity; titles carry the peak and % of the limit."),
    ("shots/dev-029-tab-qdd-1-t1.8.png", "qdd", "Joint acceleration in °/s² against ±max acceleration."),
    ("shots/dev-029-tab-qddd-1-t1.8.png", "qddd", "Jerk in °/s³: the slope of qdd on the trajectory's own clock (first-order at the ends, as coverage's _slope)."),
    ("shots/dev-029-tab-cards-1-t1.8.png", "q / qd / qdd", "Every joint at the playhead in degrees with its worst % of limit, over one card per joint (all three as % of that joint's limits)."),
    ("shots/dev-029-tab-tcp-1-t1.8.png", "TCP", "The tool: x / y / z in mm, roll / pitch / yaw in degrees (the near-gimbal-lock span named), speed in mm/s, angular speed in °/s."),
]
OTHERS = [
    ("amb-shots/conveyor-dev-000-1-t1.0.png", "The cell deployment", "Rebuilt from arm_motion_bench: the cell's UR5e hangs from its portal (mounted per deployment), the tool stick reaching the conveyor path."),
    ("shots/dev-003-1-t0.9.png", "A short A to B", "workspace-dev-003 halfway: the arm, its start/end ghosts and the q tab."),
]


def jpeg(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=1600:-2", "-q:v", "4", str(dst)], check=True)


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    frames = sorted((SRC / "hero").glob("f-*.png"), key=lambda p: int(p.name.split("-")[1]))
    for k, frame in enumerate(frames):
        shutil.copy(frame, MEDIA / f"frame-{k:03d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10", "-i", str(MEDIA / "frame-%03d.png"),
                    "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-movflags", "+faststart",
                    str(MEDIA / "hero.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10", "-i", str(MEDIA / "frame-%03d.png"),
                    "-vf", "scale=720:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse",
                    str(MEDIA / "hero.gif")], check=True)
    for frame in MEDIA.glob("frame-*.png"):
        frame.unlink()
    figures = []
    for k, (name, title, caption) in enumerate(TABS + OTHERS):
        jpeg(SRC / name, MEDIA / f"still-{k}.jpg")
        figures.append(f'<figure><img src="{REL}/still-{k}.jpg" alt="{html.escape(title)}"><figcaption><b>{html.escape(title)}.</b> '
                       f'{html.escape(caption)}</figcaption></figure>')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Rerun trajectory viewer</title><style>
:root{{--bg:#fbfaf7;--fg:#1f2328;--muted:#57606a;--rule:#d8dee4}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e6e6e6;--muted:#9aa4ae;--rule:#30363d}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 64px}} h1{{font-size:24px;margin:0 0 6px}}
h2{{font-size:18px;margin:32px 0 10px;border-top:1px solid var(--rule);padding-top:20px}} .muted{{color:var(--muted)}}
video,img{{width:100%;height:auto;border:1px solid var(--rule);border-radius:8px;background:#fff}} figure{{margin:0 0 22px}}
figcaption{{color:var(--muted);font-size:14px;margin-top:6px}} code,pre{{font-size:13px}} pre{{background:rgba(127,127,127,.1);padding:10px;border-radius:6px;overflow-x:auto}}
ul{{padding-left:20px}}</style></head><body><main>
<h1>robot_msgs' stock JointTrajectory viewer in Rerun, with the URDF</h1>
<p><b>Any robot_msgs JointTrajectory plus its robot's URDF opens in Rerun as the moving arm on the left half and your tabs on the right
(q · qd · qdd · qddd · q / qd / qdd · TCP), in degrees.</b> It is the five-way round's pick (R3, Solo run dashboard) with your Nov 24 change.</p>
<p class="muted">robot_msgs main 248f9f1 (b806be5 freezes the output without a robot) · traj_compare 023b876 (Open in Rerun) · arm_motion_bench 66fb115
(the 212 UR recordings rebuilt) · all pushed except arm_motion_bench (no remote) · not released to PyPI.</p>
<video src="{REL}/hero.mp4" poster="{REL}/still-0.jpg" autoplay muted loop playsinline controls></video>
<p class="muted">The real Rerun 0.40 viewer playing workspace-dev-029 (3.2 s, a stop-motion of 33 frames, the playhead set 0.1 s apart through the
viewer's own handle): the arm leaves the blue start ghost, the tool path fills in, every strip's cursor follows. <a href="{REL}/hero.gif">GIF</a>.</p>
<h2>The six tabs (workspace-dev-029 at 1.8 s)</h2>{''.join(figures[:len(TABS)])}
<h2>On other trajectories</h2>{''.join(figures[len(TABS):])}
<h2>Use it</h2>
<pre>from robot_msgs.viz import rerun as viz
viz.save("move.rrd", traj, robot="ur5e.urdf", tool=tcp)        # or traj.show(robot="ur5e.urdf")
# traj_compare's Open in Rerun:
write_trajectory_rrd(path, name, traj, tool=tcp, robot=urdf, ghosts=False)   # ghosts=False for web bundles</pre>
<h2>Decided for you</h2><ul>
<li>R3 + your tabs as the stock, without waiting: undo with <code>git -C /home/bam/robot_msgs revert 248f9f1</code>, <code>git -C /home/bam/traj_compare revert 023b876</code>, <code>git -C /home/bam/arm_motion_bench revert 66fb115</code>.</li>
<li>A thin stick from the flange to the tool point: without it the tool floated 145 mm off the wrist and read as a frame bug.</li>
<li>TCP orientation as ROS roll / pitch / yaw, unwrapped, with the near-gimbal-lock span named in the title (tilt + yaw has its own singularity on this tour).</li>
<li>Opens paused at t = 0 on the q tab; play loops. A tab whose data the message lacks is left out.</li>
<li>arm_motion_bench had no URDF (its station is MuJoCo Menagerie's MJCF): the UR5e URDF, meshes and BSD licence are committed there, mounted per deployment.</li></ul>
<h2>Left</h2><ul>
<li>Files are ~10× larger: 2.18 MB per 3.2 s trajectory (1.56 MB with ghosts=False); all 212 UR files 518 MB (383 MB without ghosts), up from 48 MB.</li>
<li>One trajectory per recording: target vs real on one arm isn't designed yet. Only collision meshes (Rerun 0.40 can't load the .dae visuals).</li>
<li>Dense strips show few tick labels at ~100 px (Rerun's plot library); the titles carry the peak and % of limit.</li>
<li>robot_msgs isn't released: a PyPI install of 0.3.1 lacks <code>robot=</code>.</li></ul>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, f"{sum(p.stat().st_size for p in MEDIA.iterdir()) / 1e6:.1f} MB media")


if __name__ == "__main__":
    main()
