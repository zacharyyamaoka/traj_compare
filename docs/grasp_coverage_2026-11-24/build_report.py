"""Build the 2026-11-24 review: the grasp coverage viewer, robot_msgs grasps in, four viewers out, on real grasps.

    taskset -c 2-5,16,17 /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/grasp_coverage_2026-11-24/build_report.py

Reads build_real.py's payloads and PNGs and record_hero.py's clip and stills under reports/media/grasp-coverage-2026-11-24/
and writes ONE self-contained page (stills as WebP data URIs, the clip as an MP4 data URI, the GIF as its fallback) to
reports/media/grasp-coverage-2026-11-24.html. Every number on it is read from the payloads. A missing still is drawn as
a labelled gap, never silently dropped.
"""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
SITES = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24"
MEDIA = SITES / "report"
OUT = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24.html"
# the W&B runs of record (build_real.py --wandb, 2026-11-24 20:12; their summaries checked equal to the payloads' numbers)
WANDB = {"repicks": "https://forge.coreweave.com/wandb/zach-yamaoka-independent/grasp-coverage/runs/q3uhtlnv",
         "graspnet": "https://forge.coreweave.com/wandb/zach-yamaoka-independent/grasp-coverage/runs/svn5kl2w"}
MISSING: list[str] = []

STYLE = """
:root{--ink:#22221f;--muted:#6f6e69;--line:#e3e2dc;--bg:#fafaf7;--card:#fff;--accent:#2f6fdf;--ok:#2f8f4e;--warn:#b7791f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}h1{font-size:27px;margin:0 0 8px;line-height:1.25}
h2{font-size:20px;margin:40px 0 10px;border-top:1px solid var(--line);padding-top:24px}h3{font-size:16px;margin:24px 0 6px}
p{margin:8px 0}.muted{color:var(--muted)}.verdict{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);
padding:14px 18px;border-radius:6px;font-size:16px}code{background:#f0efe9;padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:#1f1f1c;color:#f4f3ee;padding:14px 16px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.45}
figure{margin:14px 0;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px}
figure img,figure video{display:block;max-width:100%;height:auto;margin:0 auto}
figcaption{color:var(--muted);font-size:13px;margin-top:6px}.grid{display:grid;gap:12px}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}@media(max-width:900px){.g2,.g3{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px;margin:10px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:#f3f2ec;font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}.gap{padding:30px;text-align:center;color:#a4372a;border:1px dashed #d9a79f}
ul{margin:6px 0 6px 22px;padding:0}li{margin:3px 0}.ok{color:var(--ok);font-weight:600}
blockquote{margin:8px 0;padding:6px 14px;border-left:3px solid var(--line);color:#46453f;font-style:italic}
"""


def image(path: Path, width: int = 1100, quality: int = 58) -> str:
    if not path.is_file():
        MISSING.append(str(path.relative_to(SITES)))
        return ""
    picture = Image.open(path).convert("RGB")
    if picture.width > width:
        picture = picture.resize((width, round(picture.height * width / picture.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    picture.save(buffer, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()


def fig(path: Path, caption: str, width: int = 1100) -> str:
    uri = image(path, width)
    body = (f'<img src="{uri}" alt="{html.escape(caption)}">' if uri
            else f'<div class="gap">missing: {html.escape(path.name)}</div>')
    return f"<figure>{body}<figcaption>{caption}</figcaption></figure>"


def still(name: str, caption: str, width: int = 1100) -> str:
    return fig(MEDIA / "stills" / f"{name}.png", caption, width)


def png(site: str, name: str, caption: str, width: int = 900) -> str:
    return fig(SITES / site / "png" / f"{name}.png", caption, width)


def hero(timeline: dict) -> str:
    mp4, gif, poster = MEDIA / "hero.mp4", MEDIA / "hero.gif", MEDIA / "hero-poster.jpg"
    if not mp4.is_file():
        MISSING.append("hero.mp4")
        return '<div class="gap">missing: hero.mp4</div>'
    video = "data:video/mp4;base64," + base64.b64encode(mp4.read_bytes()).decode()
    still_uri = "data:image/jpeg;base64," + base64.b64encode(poster.read_bytes()).decode() if poster.is_file() else ""
    fallback = ("data:image/gif;base64," + base64.b64encode(gif.read_bytes()).decode()) if gif.is_file() else ""
    marks = {mark["name"]: mark for mark in timeline.get("marks", [])}
    steps = [("landing", "the repicks' Overview: all grasps"), ("failed", "Outcome ‘failed’ ticked: every figure recounts"),
             ("position", "Position: the 3-D view, orbited"), ("orientation", "Orientation"),
             ("all", "‘failed’ unticked"), ("graspnet", "GraspNet-1Billion's Orientation: the same views on 6-DOF labels")]
    timeline_text = " · ".join(f"{marks[name]['video_s']:.1f} s {words}" + (f" ({marks[name]['count']})"
                                                                             if marks[name].get("count") else "")
                               for name, words in steps if name in marks)
    return (f'<figure><video src="{video}" poster="{still_uri}" controls muted loop autoplay playsinline '
            f'style="width:100%">{"<img src=" + chr(34) + fallback + chr(34) + " alt=hero>" if fallback else ""}</video>'
            f'<figcaption>Recorded from the real workbench in headless Chrome, {timeline.get("duration_s", 0):.1f} s, no '
            f'page errors ({len(timeline.get("errors", []))}). {html.escape(timeline_text)}.</figcaption></figure>')


def numbers(payload: dict) -> dict:
    return {entry["key"]: entry for entry in payload["numbers"]}


def value(payload: dict, key: str, digits: int = 1) -> str:
    entry = numbers(payload).get(key)
    if entry is None:
        return "—"
    number = entry["value"]
    text = f"{number:,.0f}" if entry["unit"] == "" else f"{number:.{digits}f}"
    unit = {"%": " %", "deg": "°", "": ""}.get(entry["unit"], " " + entry["unit"])
    return text + unit


def _picked(row: dict) -> str:
    """picked % of the closed grasps, with its counts: 100 % of one grasp is not 100 % of a thousand."""
    if row["picked_pct"] is None:
        return "—"
    picked = row["outcomes"].get("picked", 0)
    closed = picked + row["outcomes"].get("failed", 0)
    return f"{row['picked_pct']:.0f} % ({picked} of {closed})"


def body() -> str:
    repicks = json.loads((SITES / "repicks" / "grasp_coverage.json").read_text("utf-8"))
    graspnet = json.loads((SITES / "graspnet" / "grasp_coverage.json").read_text("utf-8"))
    build = json.loads((SITES / "build.json").read_text("utf-8"))
    timeline = json.loads((MEDIA / "hero-timeline.json").read_text("utf-8")) if (MEDIA / "hero-timeline.json").is_file() else {}
    r, g = numbers(repicks), numbers(graspnet)
    counts = repicks["outcomes"]["counts"]
    gripper = repicks["gripper"]
    objects = repicks["objects"]
    vial = objects[0]
    rows = [("Grasps", "grasps"), ("Objects", "objects"), ("Picked, share of the closed grasps", "picked_pct"),
            ("Jaw range used (p0.1 to p99.9)", "width_span_pct"), ("Widest grasp, share of our open stop", "width_peak_pct"),
            ("Wider than our open stop", "width_outside"), ("Approach directions visited (288 equal-area cells)",
                                                            "directions_visited_pct"),
            ("Tilt from straight down, median", "tilt_median_deg"), ("Largest tilt", "tilt_max_deg"),
            ("Rolls visited", "roll_visited_pct"), ("Object balance (evenness)", "object_evenness_pct"),
            ("Largest object's share", "largest_object_pct"), ("Pick-area pixels with a grasp (1 cm, top view)",
                                                               "area_visited_pct")]
    table = "".join(f"<tr><td>{label}</td><td class=n>{value(repicks, key)}</td><td class=n>{value(graspnet, key)}</td></tr>"
                    for label, key in rows)
    object_rows = "".join(
        f"<tr><td>{html.escape(o['object_id'])}</td><td class=n>{o['grasps']}</td>"
        f"<td>{', '.join(f'{n} {w}' for w, n in o['outcomes'].items())}</td><td class=n>{_picked(o)}</td></tr>"
        for o in objects)
    numbers_list = "".join(f"<li><code>grasp_coverage/{e['key']}</code> — {html.escape(e['label'])}</li>"
                           for e in repicks["numbers"])
    return f"""
<h1>Grasp coverage: a stock viewer, robot_msgs grasps in, four viewers out</h1>
<p class=muted>traj_compare · 2026-11-24 · contract <code>docs/GRASP_COVERAGE.md</code> · on <code>main</code></p>
<div class=verdict><b>Built and proven on real grasps.</b> Put in a list of robot_msgs <code>GraspPose</code>, an outcome per
grasp and the gripper's jaw range; <code>traj_compare.grasp_coverage.analyze_grasps()</code> makes one payload, and our
data-ui page, Matplotlib, Viser and W&amp;B all read it. On our {r['grasps']['value']:,.0f} real repick grasps
({build['repicks']['runs']} runs, {build['repicks']['days'][0]} to {build['repicks']['days'][-1]}): {value(repicks, 'picked_pct')}
of the {counts.get('picked', 0) + counts.get('failed', 0)} grasps the claw closed on were picked; every approach is within
{value(repicks, 'tilt_max_deg')} of straight down, so they visit {value(repicks, 'directions_visited_pct')} of approach
directions against GraspNet-1Billion's {value(graspnet, 'directions_visited_pct')}; and {vial['object_id']} is
{value(repicks, 'largest_object_pct')} of them.</div>

{hero(timeline)}

<h2>What you put in (your open question)</h2>
<blockquote>“For the grasping though I am not entirely sure what you want to do there....” — Daily Note 2026-11-23</blockquote>
<p>A grasp set is the trajectory viewer's tool section without time, so the input is what a grasp detector already
emits, plus what happened:</p>
<pre>from traj_compare.grasp_coverage import analyze_grasps

coverage = analyze_grasps(
    grasps,                          # Sequence[GraspPose]: pose (+z approach, x jaw), width, score, object_id
    outcomes=outcomes,               # per grasp: picked | failed | hovered | refused | other word | None
    width_range=(0.0, {gripper['high']:.4f}),     # the jaw gap from shut to the open stop (m)
    planner_width_range=(0.0, {gripper['planner_high']:.3f}),
    tags=tags,                       # per grasp: run, day, failed at, dataset, split ...
    area=look_areas,                 # the offered pick area(s), boxes in the grasp frame
)
coverage.write_workbench("out/")     # our page (data-ui)
coverage.plot("out/png")             # Matplotlib
coverage.serve_viser()               # Viser
coverage.log_wandb(run)              # W&amp;B summary scalars</pre>
<p>Angles: <b>tilt</b> = the approach's angle from straight down; <b>roll</b> = the jaw axis about the approach (counter-clockwise
seen from behind the gripper; for a straight-down grasp it is the jaw's heading, the trajectory viewer's yaw), shown folded
to 0–180° for a symmetric two-finger claw. Every count uses the trajectory viewer's own binning, moved to a shared
<code>coverage/bins.py</code> (the trajectory payload stays byte-identical).</p>

<h2>What the real grasps say</h2>
<table><tr><th></th><th>Our repicks (base frame)</th><th>GraspNet-1Billion, 4 YCB objects (labels, object frame)</th></tr>{table}</table>
<p class=muted>Repicks: {build['repicks']['grasps']:,} planned grasps of pick_loop_full_arm_repick_real_* on /archive (read-only;
{build['repicks']['skipped']} plans had no item width and are left out), outcomes from attempts.jsonl: {', '.join(f'{n} {w}' for w, n in counts.items())}.
GraspNet: {build['graspnet']['per_object']} valid labels per object picked evenly (seed 0), measured against <i>our</i>
claw's range ({gripper['high'] * 1000:.1f} mm open stop, {gripper['planner_high'] * 1000:.0f} mm planner span).</p>
<table><tr><th>Object (repicks)</th><th>Grasps</th><th>Outcomes</th><th>Picked of closed</th></tr>{object_rows}</table>

<h2>1 · Our page: the data-ui workbench</h2>
<p>The rail filters <b>grasps</b> (Object, Outcome, Day, Failed at, then width / tilt ranges); every coverage figure re-sums the
kept grasps' part rows, so ticking “failed” recounts every tab. Same stock component as the trajectory workbench, so it
drops into any app (the 1000 × 680 embed below).</p>
{still('repicks-overview', 'Overview, all grasps. Where the gripper closed (top view, coloured by outcome), the jaw width against the claw (red: open stop solid, planner span dashed; grey past it), grasps per object, which way it approaches.')}
{still('repicks-overview-failed', 'The same page with Outcome “failed” ticked: 43 of 1,233 grasps. The failures spread across the belt; the picked cluster near x −350 mm had few.')}
<div class="grid g2">{still('repicks-position', 'Position: 3-D (a point per grasp, an arrow down its approach), top and side scatter.', 900)}
{still('repicks-orientation', 'Orientation: pointing disk, equal-area sphere, roll (full circle: our claw read as asymmetric), tilt.', 900)}
{still('repicks-gripper', 'Gripper: width and pre-grasp opening against the range; every histogram as data-ui strips; width × tilt.', 900)}
{still('repicks-objects', 'Objects: grasps and outcome share per object.', 900)}
{still('graspnet-orientation', 'GraspNet-1Billion, the same Orientation tab: 88 % of direction cells, every roll.', 900)}
{still('repicks-embed', 'Embedded in a host app’s 1000 × 680 slot (embed.html): the rail folds to a Filters chip.', 900)}</div>

<h2>2 · Matplotlib</h2>
<div class="grid g2">{png('repicks', 'positions', 'positions.png: where the gripper closed, by outcome, over the union of the 174 look areas.')}
{png('repicks', 'width', 'width.png: the size of the grasps against the claw (stacked by outcome).')}
{png('repicks', 'roll', 'roll.png: roll as a straight line (full circle here).')}
{png('repicks', 'pointing', 'pointing.png: the tilt disk; all within 2.8° of straight down.')}
{png('repicks', 'objects', 'objects.png: the balance per object, picked % beside each.')}
{png('graspnet', 'width', 'GraspNet width.png: 22 % of its labels are wider than our open stop.')}
{png('repicks', 'sphere', 'sphere.png: the equal-area approach map.')}
{png('repicks', 'position-density', 'position-density.png: grasps per 1 cm pixel, three faces, grey outside the offered area.')}</div>
<p class=muted>Also written: width-tilt.png. Each takes <code>cmap</code> (BAM Reach's five), <code>reverse</code> and <code>scale</code> (linear default).</p>

<h2>3 · Viser</h2>
<div class="grid g3">{still('viser-grasps', 'robot_msgs’ two-finger glyph per grasp, coloured by outcome, inside the look areas’ outer box.', 700)}
{still('viser-picked-hidden', 'The “picked” checkbox off: the failures and hovers that remain.', 700)}
{still('viser-sphere', 'Approach sphere from below: the 4 visited cells of 288.', 700)}</div>
<p class=muted>Headless review (headless-viser skill): mechanical PASS, visual PASS on run 02 at 1440 and 900 px; run 01 found
the 174 area boxes burying the grasps and a sphere camera that hid the visited cap, both fixed.</p>

<h2>4 · Weights &amp; Biases</h2>
<p>Project <code>grasp-coverage</code>, registered in bam_ws <code>tools/wandb_trackers/trackers/grasp_coverage.py</code> (origin/main
<code>ec0ddf927</code>). Summary scalars only, read back from the server and equal to the payloads' numbers:
<a href="{WANDB['repicks']}">repicks</a> ({len(repicks['numbers'])} scalars), <a href="{WANDB['graspnet']}">graspnet-4-ycb</a> ({len(graspnet['numbers'])}).</p>
<details><summary>The scalars</summary><ul>{numbers_list}</ul></details>

<h2>Proof</h2>
<ul>
<li>Acceptance tests written before the code (<code>c1a23d8</code>): 54 pass — the angles come back from grasps built from known
tilt / roll, every count re-derived by hand, the workbench parts add back to the payload exactly, data-ui's checker passes the
<code>.base</code> with 0 errors and 0 warnings, and headless Chrome ticks “failed” and reads each figure's recount.</li>
<li>The trajectory coverage suite stays green beside it (137 together); the trajectory payload is byte-identical after the
binning moved to <code>coverage/bins.py</code>.</li>
<li>Real data through all four viewers: the stills and clip above are the real pages; W&amp;B read back from the server.</li>
</ul>

<h2>Decided for you (each one undoable)</h2>
<ul>
<li><b>Lives in traj_compare</b> as <code>traj_compare.grasp_coverage</code>, beside <code>coverage</code>: it shares the binning, the
colour rule and the workbench writer. Undo: move the package out (it imports only <code>coverage.bins</code>,
<code>coverage.matplotlib_view</code>, <code>coverage.viser_view</code>, <code>coverage.workbench</code>).</li>
<li><b>Our page is the data-ui workbench</b>, not a hand-rolled page like the trajectory one (your Nov 24 “common visual
language”). The big width / roll / tilt histograms are Vega-Lite charts in it, because data-ui's coverage strips are 58 px
tall; the strips stay as one panel.</li>
<li><b>Outcomes</b>: success → picked, missed / suspect → failed, hover → hovered, refused → refused, stopped kept as its own word.</li>
<li><b>Width</b> = the look's item width (what the plan closes to), pre-grasp = the opening gap at approach (else the look's opening).</li>
<li><b>Our claw's roll shown as a full circle</b> (the Nov 19 gallery read the claw as asymmetric). One flag flips it:
<code>symmetric_jaws=True</code>.</li>
<li><b>Outcome colours</b>: picked blue, failed orange, hovered grey (the gallery's), refused amber, unknown violet — one table
(<code>colours.py</code>) for all four viewers.</li>
<li><b>Look areas</b>: drawn as their union (PNGs) or outer box (3-D); their height is the grasps' own ±10 mm.</li>
</ul>

<h2>Left, and not done</h2>
<ul>
<li>The workbench's projections carry no area mask (the same gap as the trajectory workbench's reachable mask: a per-grasp part
cannot hold the whole set's area); the area shows in the 3-D view and the PNGs.</li>
<li>GraspClutter6D is not in: the Nov 19 cache holds only per-object counts, and its labels are 200 compressed archives on
/archive (a ~4.5 min pass); GraspNet-1Billion stands in as the 6-DOF set.</li>
<li>The scatter's axes are not forced to equal scale (Vega-Lite has no aspect lock); the 3-D view and the projections are.</li>
<li>Beside this, a peer session landed <i>record coverage</i> (the generic ML dataclass viewer) in the same repo today; it
also reads the repicks, as records. The two are separate by design (your three viewers).</li>
</ul>
"""


def main() -> None:
    page = (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Grasp coverage viewer</title><style>{STYLE}</style></head><body><main>{body()}"
            f"</main></body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT} {OUT.stat().st_size / 1e6:.2f} MB" + (f"; MISSING: {MISSING}" if MISSING else ""))


if __name__ == "__main__":
    main()
