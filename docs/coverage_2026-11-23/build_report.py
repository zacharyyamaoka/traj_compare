"""Build the 2026-11-23 review: the trajectory coverage viewer, from Zach's "Coverage Feedback" note to the UR5e pages.

    taskset -c 2-5,16,17 /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/coverage_2026-11-23/build_report.py

Reads the media that record_hero.py and shoot_stills.py wrote into reports/media/coverage-viewer-2026-11-23/ and the UR5e
payloads under /home/bam/arm_motion_bench/reports/media/coverage-viewer/, and writes ONE self-contained page (images as
WebP data URIs, the hero clip as an MP4 data URI) to reports/media/coverage-viewer-2026-11-23.html. A missing still is
drawn as a labelled gap, never silently dropped.
"""

from __future__ import annotations

import base64
import html
import io
import json
import subprocess
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
MEDIA = PACKAGE / "reports" / "media" / "coverage-viewer-2026-11-23"
OUT = PACKAGE / "reports" / "media" / "coverage-viewer-2026-11-23.html"
UR = Path("/home/bam/arm_motion_bench/reports/media/coverage-viewer")
MAX_PREVIEW_BYTES = 1_900_000  # the desktop preview's ceiling for a page with media (CLAUDE.md, feedback_show_dont_tell)
MISSING: list[str] = []

STYLE = """
:root{--ink:#22221f;--muted:#6f6e69;--line:#e3e2dc;--bg:#fafaf7;--card:#fff;--accent:#2f6fdf;--ok:#2f8f4e;--warn:#b7791f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}h1{font-size:27px;margin:0 0 8px;line-height:1.25}
h2{font-size:20px;margin:40px 0 10px;border-top:1px solid var(--line);padding-top:24px}h3{font-size:16px;margin:24px 0 6px}
p{margin:8px 0}.muted{color:var(--muted)}.verdict{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);
padding:14px 18px;border-radius:6px;font-size:16px}.lead{font-size:16px}code{background:#f0efe9;padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:#1f1f1c;color:#f4f3ee;padding:14px 16px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.45}
figure{margin:14px 0;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px}figure img,figure video{display:block;max-width:100%;height:auto;margin:0 auto}
figcaption{color:var(--muted);font-size:13px;margin-top:6px}.grid{display:grid;gap:12px}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media(max-width:900px){.g2,.g3,.g4{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px;margin:10px 0}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f3f2ec;font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;background:#eef3fa;color:#24507f}
.ok{color:var(--ok);font-weight:600}.gap{padding:30px;text-align:center;color:#a4372a;border:1px dashed #d9a79f}
ul{margin:6px 0 6px 22px;padding:0}li{margin:3px 0}.pick{border-left:4px solid var(--accent)}details{margin:6px 0}summary{cursor:pointer;color:var(--accent)}
"""


def image(name: str, width: int = 1100, quality: int = 56) -> str:
    """A still as a WebP data URI, scaled to at most `width` px."""
    path = MEDIA / name
    if not path.is_file():
        MISSING.append(name)
        return ""
    picture = Image.open(path).convert("RGB")
    if picture.width > width:
        picture = picture.resize((width, round(picture.height * width / picture.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    picture.save(buffer, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()


def fig(name: str, caption: str, width: int = 1100, quality: int = 56) -> str:
    uri = image(name, width, quality)
    body = f'<img src="{uri}" alt="{html.escape(caption)}">' if uri else f'<div class="gap">missing: {name}</div>'
    return f"<figure>{body}<figcaption>{caption}</figcaption></figure>"


def hero() -> str:
    """The hero clip, re-encoded small enough to inline (muted, looping, controls; the GIF is the fallback)."""
    source = MEDIA / "hero.mp4"
    if not source.is_file():
        MISSING.append("hero.mp4")
        return '<div class="gap">missing: hero.mp4</div>'
    small = MEDIA / "hero-inline.mp4"
    if not small.is_file() or small.stat().st_mtime < source.stat().st_mtime:
        subprocess.run(["taskset", "-c", "2-5,16,17", "/usr/bin/ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                        "-vf", "scale=960:-2", "-c:v", "libx264", "-crf", "35", "-preset", "slow", "-pix_fmt", "yuv420p",
                        "-an", "-movflags", "+faststart", str(small)], check=True)
    uri = "data:video/mp4;base64," + base64.b64encode(small.read_bytes()).decode()
    poster = image("hero-poster.jpg", 960, 55)
    return (f'<figure><video src="{uri}" poster="{poster}" autoplay muted loop playsinline controls></video>'
            "<figcaption>The real page on the real UR5e set (54 trajectories, full speed): landing page → overview → "
            "limits → one joint, switching colours, Reverse and the scale → all joints → tool position (voxels) → "
            "tool orientation (sphere) → three of the 3-D proposals → a trajectory picked in the table and highlighted. "
            "The full-size clip and a GIF are in reports/media/coverage-viewer-2026-11-23/.</figcaption></figure>")


def ur_rows() -> str:
    """The four UR5e datasets at full speed, from the pages' own payloads."""
    names = [("ur5e_alone-workspace", "UR5e · Entire Workspace"), ("ur5e-workspace", "Cell · Entire Workspace"),
             ("ur5e-conveyor", "Cell · Conveyor PnP"), ("ur5e-impact", "Cell · Conveyor Collision")]
    rows = []
    for folder, title in names:
        path = UR / folder / "full-speed" / "coverage.json"
        if not path.is_file():
            rows.append(f"<tr><td>{title}</td><td colspan=7 class='gap'>missing {path}</td></tr>")
            continue
        numbers = {row["key"]: row["value"] for row in json.loads(path.read_text("utf-8"))["numbers"]}
        cells = [f"{numbers['trajectories']:.0f}", f"{numbers['q_span_median_pct']:.0f} %",
                 f"{numbers['q_span_min_pct']:.0f} %", f"{numbers['q_qd_visited_mean_pct']:.0f} %",
                 f"{numbers.get('tool_voxels_reachable_pct', float('nan')):.1f} %",
                 f"{numbers.get('tool_directions_visited_pct', float('nan')):.0f} %",
                 f"{numbers.get('tool_speed_p99_m_s', float('nan')):.2f} m/s"]
        rows.append(f"<tr><td>{title}</td>" + "".join(f"<td class='n'>{cell}</td>" for cell in cells) + "</tr>")
    head = ("<tr><th>Dataset (full speed, dev + holdout)</th><th>Trajectories</th><th>Joint range used, median joint</th>"
            "<th>… least-used joint</th><th>Angle × speed cells visited</th><th>Reachable 5 cm voxels the tool passed</th>"
            "<th>Tool directions</th><th>Tool speed p99</th></tr>")
    return f"<table>{head}{''.join(rows)}</table>"


ASKS = [  # (what Zach asked, his words, what exists now, where)
    ("Integrate it into the traj compare viewer, standalone or one click away",
     "“a page you can see standalone or just quickly get there from the traj compare stuff”",
     "One coverage page per payload, opened from disk; <code>write_dataset_report(..., coverage=True)</code> writes it beside "
     "a dataset site and ends the Dataset level's tab bar with <b>Coverage ↗</b>", "traj_compare a5de694"),
    ("Datasets or single trajectories in", "“Trajectory or Trajectory Dataset in”",
     "<code>analyze()</code> takes one <code>JointTrajectory</code>, a list, or a name → trajectory dict (+ optional "
     "<code>PoseTrajectory</code> tool, <code>JointLimits</code>); CLI: <code>python -m traj_compare.coverage *.npz --out DIR</code>",
     "traj_compare 7ab37f1"),
    ("Show the legend of the meaning of the lines", "“This is good as long as you show the legend”",
     "Every figure on every tab has a visible legend; the acceptance test fails if one does not", "test_coverage_page.py"),
    ("Linear, viridis like BAM Reach, easy to change, high ↔ low", "“Linear to me is BY far the most informative”",
     "Sticky bar: Colours (viridis, magma, plasma, inferno, cividis — BAM Reach's set and stops), Reverse (high = dark), "
     "Scale (linear default, log, equalized, visited, enough); every heatmap and 3-D view repaints", "coverage_color.js"),
    ("Cartesian spaghetti + voxels scored by visit count", "“the score of the voxel is set by like the visited count”",
     "Tool position tab: x-y, x-z, y-z projections (samples or Strava paths), max tool speed per pixel, 3-D voxels with a "
     "≥ N slider and reachable-never-visited grey, 3-D tool paths", "coverage3d.js"),
    ("Many slices at once", "“cool idea to show many slices at a single time”",
     "One joint tab: q × qd for each of 5 acceleration bands, one shared scale", "slabs"),
    ("Compact overview, tidier", "“I like this as a compact overview … could be made a bit tidier”",
     "Overview tab: every joint's q, qd, qdd as % of its limit, one row each, one axis −100…+100 %", "ridgeline"),
    ("Parallel coordinates", "“it almost looks like the arm”", "All joints tab, with a q / qd / qdd switch", "parallel"),
    ("Tool orientation as 2 angles and on a sphere", "“a single angle away from z and then the yaw angle … see it like a sphere”",
     "Tool orientation tab: tilt disk (where it leans), tilt × yaw grid, a 3-D direction sphere, yaw as a straight line", "orientation"),
    ("Proposals for 3-D plots", "“make a bunch of different proposals about how we could use 3D plots”",
     "3-D proposals tab: 8 proposals behind a bottom-right drop-down that remembers your pick", "space3d"),
    ("Robot_msgs in → analysis → Matplotlib, Viser, W&B, our viewer", "“Robot_msgs in. Then do the analysis. and then like the viewers out”",
     "One payload, four viewers: the page, <code>plot_coverage</code> (PNGs), <code>serve_coverage</code> (Viser via viser_3d_viewer), "
     "<code>log_coverage</code> (W&B summary scalars)", "traj_compare f711537"),
    ("Analyze the UR trajectories in our own viewer", "“concretely I want to be able to analyze the UR trajectorys”",
     "16 pages: 4 UR5e datasets × 4 subsets, the reachable workspace as the Cartesian denominator, plus a landing page; "
     "numbers also in W&B project <i>trajectory-coverage</i>", "arm_motion_bench 21162fc"),
    ("Earlier Rerun 3-D coverage viewers", "“can you find those?”", "Found; listed below with commands", "§ Rerun"),
    ("Grasp viewers (failures, widths, roll)", "“For the grasping though I am not entirely sure”",
     "Not built: a proposed input contract and view list below", "§ Three families"),
]

PROPOSALS = [  # (still, title, what it shows / when it wins, keep?)
    ("p-height-q-qd.jpg", "1 · q × qd height map", "The q × qd heatmap lifted into bars. Wins when you want hot spots and empty corners at once; nothing hides behind anything.", True),
    ("p-slab-stack.jpg", "2 · qdd slab stack", "The five acceleration bands stacked as translucent planes: q, qd and qdd in one picture, which you asked for.", True),
    ("p-joint-skyline.jpg", "3 · joint skyline", "Every joint's range histogram side by side: the ridgeline in 3-D. Reads fast; adds little over the 2-D ridgeline.", False),
    ("p-workspace-terrain.jpg", "4 · workspace terrain", "x-y floor, height = trajectories through the pixel, colour = max tool speed: “something that depends on 2 other things”.", True),
    ("p-hist-over-trajectories.jpg", "5 · histogram over trajectories", "One qd histogram per trajectory along depth (the TensorBoard surface you liked). Wins for drift across a run order.", True),
    ("p-phase-space-3d.jpg", "6 · (q, qd, qdd) lines", "Each trajectory as a line inside the red limit box. An extra one, beyond the seven asked for.", False),
    ("p-terrain-qdd.jpg", "7 · max |qdd| terrain", "Height = hardest acceleration reached per (q, qd). On this UR data almost every cell hits the limit: a flat plateau.", False),
    ("p-direction-hedgehog.jpg", "8 · direction hedgehog", "Sphere with spikes = samples per direction. Busy at 95 % of directions; the flat tilt disk reads better.", False),
]


def body() -> str:
    asks = "".join(f"<tr><td><b>{a}</b><br><span class='muted'>{w}</span></td><td>{n}</td><td><code>{where}</code></td></tr>"
                   for a, w, n, where in ASKS)
    proposals = "".join(
        f"<div class='{'pick' if keep else ''}'>{fig(still, f'<b>{title}</b> — {blurb}' + (' <span class=ok>keep</span>' if keep else ''), 700, 58)}</div>"
        for still, title, blurb, keep in PROPOSALS)
    return f"""
<h1>Trajectory coverage is a stock viewer now</h1>
<p class="verdict"><b>One trajectory or a whole dataset in, one analysis, four viewers out:</b> our own page, Matplotlib,
Viser and W&amp;B all read the same payload, and every UR5e dataset has its page (4 datasets × 4 subsets).
Landed on <code>traj_compare</code> main (pushed), <code>arm_motion_bench</code> main and bam_ws <code>origin/main</code> (the W&amp;B tracker).
Grasp and generic-dataset viewers are proposed below, not built.</p>
{hero()}
<ul class="lead">
<li><b>UR5e · Entire Workspace, full speed:</b> 54 trajectories use a median <b>88 %</b> of each joint's range (least:
shoulder_lift, 28 %), reach <b>100 %</b> of the speed and acceleration limits, visit <b>50 %</b> of angle × speed cells and
point the tool in <b>95 %</b> of directions, yet pass through only <b>4.5 %</b> of the reachable 5 cm voxels.</li>
<li><b>Conveyor PnP is narrow by design:</b> median joint 18 % of its range; wrist_2 sits at 0 % (held at 90° so the tool
points down).</li>
<li><b>One false alarm fixed on the way:</b> every page said “past the jerk limit”; it was numpy's edge stencil at sample 0,
not the data (failing test first, then the fix).</li>
</ul>

<h2>What you asked → where it is now</h2>
<table><tr><th style="width:34%">Your ask</th><th>What exists now</th><th style="width:15%">Where</th></tr>{asks}</table>

<h2>Your three questions</h2>
<h3>“Why is there light blue and dark blue?”</h3>
<p>In the Nov 19 limit bars, <b>dark = every recording, light = rounds 0-9 only</b>, drawn on top. That was said only in the
caption. Now each group gets a named colour with a legend on the chart (here dev vs holdout), grey = beyond the limit,
solid red = physical limit, dashed red = the planner's, black ticks = p0.1 / p99.9 of the data.</p>
{fig("s02-limit-bars.jpg", "Limits tab on the UR5e set: every mark is named in the legend under the chart.")}
<h3>“What is going on with the wave?”</h3>
<p>On the pendulum, the motor's torque budget is shared with gravity: allowed qdd = (±τ<sub>max</sub> − m g l sin q) / J. With the
arm horizontal, gravity eats most of the budget for lifting and helps for lowering, so the band bulges up at one angle and
down at the opposite one: the wave. The UR5e states a flat acceleration limit (6 rad/s², the same at every angle), so its
envelope is a box and the figure's legend says so. A torque-limited envelope needs the robot's dynamics passed in; it is
not wired yet.</p>
{fig("s09-envelope.jpg", "One joint tab, the envelope: reached qdd per position band (blue) against the box limit (red); the legend names the flat band and why it would wave.")}
<h3>“How does histogram-equalized look vs linear? Why are more areas stronger?”</h3>
<p>Linear colours a pixel by <i>how much</i>: count ÷ top. Equalized colours it by <i>rank</i> among visited pixels, so every
colour step holds the same number of pixels. With a skewed distribution (Nov 19's busiest pixel had 2 382 paths while most had
1-5), linear leaves nearly everything at the bottom of the ramp and only the corridor shows; equalized spreads the 1-5-path
pixels over the whole ramp, so “more areas look stronger”. Use equalized to see <b>where</b> anything went, linear to see
<b>how much</b>. On the UR5e set the gap is small for paths (72 % of pixels have exactly one trajectory, the busiest 6) and big
for samples (median 3, busiest 362).</p>
<div class="grid g2">{fig("s05-projections-linear.jpg", "Linear (default): colour = trajectories through the pixel.", 560)}{fig("s05-projections-equalized.jpg", "Equalized: colour = rank among visited pixels.", 560)}</div>

<h2>The pipeline</h2>
<p>Robot messages in, one analysis, one payload (<code>traj_compare.coverage/1</code>, contract in <code>docs/COVERAGE.md</code>),
four viewers that read only the payload, so they cannot disagree.</p>
<figure><svg viewBox="0 0 1100 230" width="100%" role="img" aria-label="pipeline" style="font:14px system-ui">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#6f6e69"/></marker></defs>
<g stroke="#cfcec8" fill="#fff"><rect x="10" y="60" width="230" height="110" rx="8"/><rect x="330" y="60" width="250" height="110" rx="8"/>
<rect x="670" y="10" width="420" height="44" rx="6"/><rect x="670" y="64" width="420" height="44" rx="6"/><rect x="670" y="118" width="420" height="44" rx="6"/><rect x="670" y="172" width="420" height="44" rx="6"/></g>
<text x="24" y="88" font-weight="600">robot_msgs in</text><text x="24" y="112">JointTrajectory (one or many)</text><text x="24" y="134">PoseTrajectory (the tool)</text><text x="24" y="156">JointLimits</text>
<text x="344" y="88" font-weight="600">analyze()  → payload</text><text x="344" y="112">numpy only, SI inside</text><text x="344" y="134">limits = the denominator</text><text x="344" y="156">traj_compare.coverage/1</text>
<text x="684" y="37"><tspan font-weight="600">Our page</tspan>  write_coverage_page · HTML, no server</text>
<text x="684" y="91"><tspan font-weight="600">Matplotlib</tspan>  plot_coverage · PNGs</text>
<text x="684" y="145"><tspan font-weight="600">Viser</tspan>  serve_coverage · 3-D, via viser_3d_viewer</text>
<text x="684" y="199"><tspan font-weight="600">W&amp;B</tspan>  log_coverage · summary scalars only</text>
<g stroke="#6f6e69" stroke-width="1.6" fill="none" marker-end="url(#a)"><path d="M240,115H325"/><path d="M580,115C620,115 630,32 666,32"/><path d="M580,115C625,115 630,86 666,86"/><path d="M580,115C625,115 630,140 666,140"/><path d="M580,115C620,115 630,194 666,194"/></g>
</svg><figcaption>Where each piece lives: traj_compare/src/traj_compare/coverage/ (analysis, page, matplotlib_view, viser_view, wandb_log) and assets/coverage*.js.</figcaption></figure>
<pre>import numpy as np
from robot_msgs.trajectory import JointLimits, JointTrajectory
from traj_compare.coverage import analyze

t = np.arange(0.0, 10.0, 0.01)
limits = JointLimits(joint_names=("shoulder", "elbow"), min_position=np.array([-3.14, -2.0]),
                     max_position=np.array([3.14, 2.0]), max_velocity=np.array([2.0, 2.0]),
                     max_acceleration=np.array([10.0, 10.0]))
swing = JointTrajectory(t=t, joint_names=("shoulder", "elbow"), limits=limits,
                        positions=np.stack([np.sin(t), 0.5 * np.cos(t)], axis=1))

coverage = analyze({{"swing": swing}}, title="One swing")
print(f"{{coverage.numbers['q_span_median_pct']:.0f}} % of the range, median joint")
coverage.write_page("/tmp/claude-1000/one-swing/index.html")</pre>
<p class="muted">Output, run as shown: <code>28 % of the range, median joint</code>. The same object has <code>.plot(dir)</code>,
<code>.serve_viser()</code> and <code>.log_wandb(run)</code>.</p>

<h2>The page, tab by tab (UR5e · Entire Workspace, full speed)</h2>
{fig("s01-overview.jpg", "Overview: one sentence, the headline numbers, then every joint against its limits (the tidied ridgeline).")}
<div class="grid g2">{fig("s08-ridgeline.jpg", "Ridgeline: q, qd, qdd as % of each limit, one row per joint.", 560)}{fig("s07-parallel.jpg", "All joints: parallel coordinates as line density, each axis from its low to its high limit.", 560)}</div>
<h3>One joint: the four scales and the colour maps</h3>
<div class="grid g4">{fig("s03-heat-linear.jpg", "linear (default)", 300, 60)}{fig("s03-heat-log.jpg", "log", 300, 60)}{fig("s03-heat-equalized.jpg", "equalized", 300, 60)}{fig("s03-heat-visited.jpg", "visited / not", 300, 60)}</div>
<div class="grid g3">{fig("s04-cmap-magma.jpg", "magma", 380, 60)}{fig("s04-cmap-cividis.jpg", "cividis", 380, 60)}{fig("s04-viridis-reversed.jpg", "viridis, Reverse (high = dark)", 380, 60)}</div>
<div class="grid g2">{fig("s06-slabs.jpg", "Slabs: q × qd for each acceleration band, one scale.", 560)}{fig("s10-growth.jpg", "Growth: does each new trajectory still add ground? Blue = dataset order, band = 32 random orders.", 560)}</div>
<h3>Tool position and orientation</h3>
<div class="grid g2">{fig("s11-voxels-3d.jpg", "Voxels: samples per 5 cm voxel, ≥ N slider.", 560)}{fig("s12-spaghetti-3d.jpg", "Every tool path at low opacity.", 560)}</div>
<div class="grid g2">{fig("s14-tilt-map.jpg", "Tilt disk: centre = straight down, radius = tilt, angle = which way it leans.", 560)}{fig("s13-sphere-3d.jpg", "Direction sphere: which side of the sphere the tool points to.", 560)}</div>
<div class="grid g2">{fig("s15-tilt-yaw.jpg", "Tilt × jaw yaw: the two angles you named.", 560)}{fig("s16-yaw-line.jpg", "Yaw and tilt as straight lines (no rose).", 560)}</div>
{fig("s18-conveyor-projections.jpg", "A second dataset (Cell · Conveyor PnP): the same views, one click away through the Dataset chips.")}

<h2>The same payload in the other three tools</h2>
<div class="grid g2">{fig("mpl-heat-q-qd.jpg", "Matplotlib: plot_coverage → heat-q-qd-&lt;joint&gt;.png (same maps, same legend rules).", 560)}{fig("mpl-projections.jpg", "Matplotlib: projections.png.", 560)}</div>
<div class="grid g2">{fig("viser-voxels.jpg", "Viser (viser_3d_viewer: no logo, ViewCube): voxels with the Colours / Reverse / Scale controls.", 560)}{fig("viser-sphere.jpg", "Viser: the direction sphere.", 560)}</div>
<p><b>W&amp;B:</b> project <i>trajectory-coverage</i>, one run per UR5e page (16), the 15 headline numbers as summary scalars and a
small config naming the page. No tables or media (your Nov 21 rule).
<a href="https://forge.coreweave.com/wandb/zach-yamaoka-independent/trajectory-coverage">Open the W&amp;B project</a>. Tracker: bam_ws <code>tools/wandb_trackers/trackers/trajectory_coverage.py</code>.</p>

<h2>The 3-D proposals</h2>
<p>Your point that histograms hide nothing while voxels do drove the set: most are <b>height maps</b> (a quantity over two
others), not filled volumes. They sit behind the drop-down at the bottom right of the 3-D proposals tab. <b>My pick (outlined):</b>
keep 1, 2, 4 and 5; drop the rest unless you like them.</p>
<div class="grid g2">{proposals}</div>

<h2>The UR5e numbers</h2>
{ur_rows()}
{fig("s17-landing.jpg", "The landing page: every dataset × subset with its headline numbers.", 900)}
{fig("s19-dataset-link.jpg", "A traj_compare dataset site written with coverage=True: the tab bar ends with Coverage ↗.", 900)}

<h2>Three viewer families</h2>
<table><tr><th>Family</th><th>Input (robot_msgs)</th><th>Status</th></tr>
<tr><td><b>Trajectory coverage</b></td><td><code>JointTrajectory</code> (one or a dataset) + <code>PoseTrajectory</code> tool + <code>JointLimits</code></td><td class="ok">built (this report)</td></tr>
<tr><td><b>Grasp coverage</b></td><td><code>Sequence[GraspPose]</code> (pose, width, pre_grasp_width, score, object_id — already in robot_msgs) + an
outcome per grasp (picked / failed / hovered) + the gripper's width range. A set of grasp poses is the trajectory viewer's tool
section without time, so it reuses position voxels, the tilt disk and sphere, and adds: where closes happened coloured by outcome
(your “where the failures were”), jaw width against the claw's range (your “size of the grasps”), roll as a straight line folded
for a symmetric two-finger claw, and per-object balance.</td><td>proposed — a follow-up session</td></tr>
<tr><td><b>Generic dataset (the “ML dataclass” one)</b></td><td>any <code>Sequence</code> of frozen dataclasses: per-field histograms
against a declared range (robot_msgs <code>Space</code>), class balance for categorical fields, missing values, rarefaction.
Prior art: TFDV / Facets Overview. Likely home: data-ui (the shared data-view library).</td><td>proposed — a follow-up session</td></tr></table>

<h2>The earlier Rerun 3-D coverage viewers you remembered</h2>
<p>They are the Rerun column of the Nov 19 coverage gallery (<code>robot_metrics/docs/proposals/coverage-2026-11-19/tools_rerun.py</code>):</p>
<ul><li><b>tool-paths.rrd</b> — 1 131 planned tool paths coloured by voxel traffic plus the 1 441 occupied 2 cm voxels (true 3-D coverage).</li>
<li><b>phase-space-3d.rrd</b> — CAN 11's (angle, speed, acceleration) cells coloured by count, reachable-unvisited translucent.</li>
<li><b>direction-sphere.rrd</b> — equal-area sphere of grasp approach directions.</li>
<li><b>grasp-poses.rrd</b> — 1 131 real repick grasps as two-finger wireframes coloured by opening.</li></ul>
<pre>/home/bam/robot_metrics/.venv/bin/rerun /home/bam/robot_metrics/reports/media/coverage-gallery-2026-11-19/tools/rerun/tool-paths.rrd</pre>
<p class="muted">Swap the file name for the others. The UR5e playback .rrd files (arm_motion_bench reports/media/playback/) are trajectory playback, not coverage.</p>

<h2>Decision surface</h2>
<h3>Done and proved</h3>
<ul><li>Analysis: 23 frozen acceptance tests written before the code (sine spans, a robot standing still, a tool pointing down…) + 9 CLI tests + 2 edge tests, all green; the UR numbers were hand-checked against raw <code>np.percentile</code> / <code>histogram2d</code>, exact.</li>
<li>Page: the frozen browser test (tabs, BAM Reach colour maps, linear default, a legend on every figure, repaint on every control, 3-D views draw, proposals bottom-right and remembered, dataset link) — 10 passed.</li>
<li>Bench dashboards (ur5e / pendulum / bam_fb) now write their own coverage page and show <b>Coverage ↗</b> (the
league-table session added <code>coverage=True</code>, arm_motion_bench a1b0fd5); I served the dashboard, clicked the link on
ur5e and it opened the page over its 1 006 targets with no errors.</li>
<li>A scroll regression test (tab switches kept the tab bar in place), red on the old code, green now; 64 coverage tests in all.</li>
<li>Matplotlib / Viser / W&amp;B: 19 tests (one real offline W&amp;B run, Viser servers started and stopped); every PNG and Viser view looked at.</li>
<li>Whole traj_compare suite: 634 passed; 1 failure is <code>test_playback</code>, a video-timing test that flips red/green on the same commit (also red before today) and touches nothing changed here.</li></ul>
<h3>Decided for you (each one undoable)</h3>
<ul><li><b>The analysis lives in traj_compare</b> (<code>traj_compare.coverage</code>), not robot_metrics: it is the trajectory viewer's package and the four viewers sit beside it. Undo: move the module; the payload contract does not change. When the grasp viewer lands, the shared grid / sphere math can move to robot_metrics.</li>
<li><b>Cell frame for the UR5e tool numbers</b> (the cell arm hangs upside down, so base-frame z-up views were upside down). Undo: <code>--frame base</code>.</li>
<li><b>Linear clips at p98</b> so one rest-pose cell does not wash the rest out; the legend says where it clipped. Undo: one constant in coverage_color.js.</li>
<li><b>Derivatives take a first-order slope at each end</b> (the false jerk alarm). Undo: <code>git revert d39bd17</code>.</li>
<li><b>Every tab is at least a window tall</b> so switching tabs never jumps the page (found while recording). Undo: one CSS rule.</li>
<li><b>Coverage is a link at the end of the dataset tab bar</b>, not a tab: it is its own page. Undo: revert a5de694's dataset.js hunk.</li>
<li><b>Pushed traj_compare main</b> (private remote), which also carried the league-table session's landed commits.</li></ul>
<h3>Left</h3>
<ul><li>The bench dashboards' coverage pages were built just before the tab-scroll fix; their next rebuild picks it up.</li>
<li>Grasp and generic-dataset viewers (proposed above).</li>
<li>arm_motion_bench's own <code>coverage.py</code> (the Nov 19 PNGs) could now call traj_compare.coverage instead of keeping its own math.</li>
<li>A torque-limited acceleration envelope (the wave) needs the robot's dynamics passed in.</li></ul>
<h3>Needs you</h3>
<ul><li>Nothing blocks. The one taste call: which 3-D proposals stay (my pick: 1, 2, 4, 5).</li></ul>
<h3>Deliberately not done</h3>
<ul><li>No Rerun backend for coverage: you listed four viewers and Rerun was not one; the Nov 19 .rrd files still open.</li>
<li>No audit: none asked.</li></ul>
"""


def build() -> Path:
    document = (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>Trajectory coverage viewer</title><style>{STYLE}</style></head><body><main>{body()}</main></body></html>")
    OUT.write_text(document, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"{OUT}  {size / 1e6:.2f} MB" + ("" if size <= MAX_PREVIEW_BYTES else "  (over the desktop preview's ~1.9 MB: browser only)"))
    if MISSING:
        print("missing media:", ", ".join(MISSING))
    return OUT


if __name__ == "__main__":
    build()
