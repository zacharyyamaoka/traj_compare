"""Build the 2026-11-24 V2 round hub report: V2 landed as traj_compare's dataset viewer + three pick rounds.

Writes /home/bam/traj_compare/reports/media/traj-compare-v2-round-2026-11-24.html, one self-contained page (stills
and two short clips inlined, downscaled with ffmpeg so the page stays under the desktop preview's ~1.9 MB). The
three galleries it links stay the pick surfaces; this page is the one place that says what is done and what is his.

    python3 /home/bam/traj_compare/docs/build_v2_round_report.py
"""
from __future__ import annotations

import base64
import html
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEDIA = REPO / "reports" / "media"
OUT = MEDIA / "traj-compare-v2-round-2026-11-24.html"

PROD = MEDIA / "v2-production-2026-11-24"
OVER = MEDIA / "v2-overview-proposals-2026-11-24"
TABS = MEDIA / "v2-tab-proposals-2026-11-24"
PLAY = MEDIA / "run-view-proposals-2026-11-24"
PICKS = MEDIA / "v2-production-picks-2026-11-25"  # the O3 + T1 defaults, checked on the real bench
R2LIVE = MEDIA / "playback-r2-2026-11-25"  # the time lane as the viewer's default, + the workbench playback on main


def _still(path: Path, tmp: Path, width: int = 960) -> str:
    out = tmp / (path.stem + ".jpg")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vf", f"scale={width}:-2", "-q:v", "9",
                    str(out)], check=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.read_bytes()).decode()


def _clip(path: Path, tmp: Path, width: int = 860, crf: int = 34) -> str:
    out = tmp / (path.stem + ".small.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-an", "-vf", f"scale={width}:-2",
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(out)], check=True)
    return "data:video/mp4;base64," + base64.b64encode(out.read_bytes()).decode()


def _gallery_link(path: Path, label: str) -> str:
    return f'<a class="go" href="{html.escape(path.name)}">{html.escape(label)} ↗</a>'


def build() -> Path:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        media = {
            "journey": _clip(PROD / "journey.mp4", tmp),
            "target": _still(PROD / "03-target.png", tmp),
            "playback": _still(PROD / "06-playback.png", tmp),
            "o3": _still(OVER / "o3-step-1.jpg", tmp),
            "o1": _still(OVER / "o1-step-2.jpg", tmp),
            "o2": _still(OVER / "o2-step-1.jpg", tmp),
            "t1": _still(TABS / "t1-step-2.jpg", tmp),
            "t3": _still(TABS / "t3-step-2.jpg", tmp),
            "t2": _still(TABS / "t2-step-2.jpg", tmp),
            "lane": _clip(R2LIVE / "tta-time-lane.mp4", tmp, crf=32),
            "live_playback": _still(R2LIVE / "workbench-playback-main.png", tmp),
            "live_overview": _still(PICKS / "01-overview-all.png", tmp),
            "live_t1": _still(PICKS / "05-sim-real-bam-fb.png", tmp),
            "r2": _still(PLAY / "r2-step-2.jpg", tmp),
            "r3": _still(PLAY / "r3-step-2.jpg", tmp),
        }
    page = TEMPLATE
    for key, uri in media.items():
        page = page.replace("{{" + key + "}}", uri)
    page = (page.replace("{{g_over}}", _gallery_link(OVER.with_suffix(".html"), "Overview gallery · pick one"))
                .replace("{{g_tabs}}", _gallery_link(TABS.with_suffix(".html"), "New tabs gallery · pick one"))
                .replace("{{g_play}}", _gallery_link(PLAY.with_suffix(".html"), "Playback gallery · pick one")))
    OUT.write_text(page, encoding="utf-8")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>traj_compare V2 round</title>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#1f1e1b;--mute:#6b6a64;--line:#e4e2dc;--accent:#2563eb;--good:#15803d;--chip:#eef2ff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17171a;--card:#202024;--ink:#ecebe6;--mute:#a3a29c;--line:#34343a;--accent:#7aa2ff;--good:#4ade80;--chip:#262a3a}}
:root[data-theme="dark"]{--bg:#17171a;--card:#202024;--ink:#ecebe6;--mute:#a3a29c;--line:#34343a;--accent:#7aa2ff;--good:#4ade80;--chip:#262a3a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:19px;margin:36px 0 8px}h3{font-size:15px;margin:18px 0 6px}
p{margin:6px 0}.mute{color:var(--mute)}.verdict{font-size:17px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
figure{margin:12px 0}figure img,figure video{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;display:block;background:#fff}
figcaption{color:var(--mute);font-size:13px;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.score{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 9px;font-size:13px;margin-left:6px}
.pick{color:var(--good);font-weight:600}
a{color:var(--accent)}a.go{display:inline-block;margin:6px 0;font-weight:600}
ul{margin:6px 0 6px 20px;padding:0}li{margin:3px 0}
code{background:var(--chip);padding:0 4px;border-radius:4px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
</style></head><body><main>
<h1>traj_compare: V2 is the dataset viewer, with the picks applied</h1>
<p class="mute">2026-11-24 night → 11-25 · your feedback in Daily Note Nov 24 "# Traj compare feedback" and the three-levels clarification · built by four Claude Code lanes (Opus 5.5)</p>

<div class="verdict"><b>V2 is traj_compare's dataset viewer with your three levels, and the AI picks are live as its defaults:</b> Overview O3 tiles, the "Does sim match real?" tab, and a playback viewer where dragging the time on any figure moves everything, in R2's one-timeline look. All on <code>main</code> @ <code>f412bc7</code> (pushed). Each pick can be undone with git, and every gallery stays open for a swap.</div>

<h2>0 · Live now: the picks applied</h2>
<figure><video src="{{lane}}" autoplay muted loop playsinline controls></video>
<figcaption>The production viewer now (your workspace-dev-000): press and drag the time lane's ruler, a run's track or any chart, and every chart's one playhead, the 3D arm and each run's error-at-t follow; ◆ Worst moment jumps; the zoom bar drags a range. Measured: every playhead within 0.009 of a sample of the committed time; every chart's plot area on the ruler's exact x pixels (0 px).</figcaption></figure>
<div class="grid">
<figure><img src="{{live_overview}}" alt="O3 live"><figcaption><b>Overview = O3's tiles</b> on all 18,507 runs; each tile opens its page (League, Model × dataset, Speed, Trade-off, Worst targets). Every number equals the round's oracle, unfiltered and with the UR5e cell ticked.</figcaption></figure>
<figure><img src="{{live_t1}}" alt="T1 live"><figcaption><b>"Does sim match real?"</b> with BAM FB ticked: 26 pairs, real ×2.00 the sim, worse in 24. A row opens the target view with that pair ticked; back keeps the filter.</figcaption></figure>
</div>
<figure><img src="{{live_playback}}" alt="workbench playback"><figcaption>Level 3 from the runs workbench, rebuilt from <code>main</code>: the same 3 ticked runs as section 1, now in the time-lane look. Building this exposed a cache bug, fixed in <code>f412bc7</code>: a playback was cached by its runs alone, so one opened last night kept yesterday's viewer. It now carries the viewer version in its cache key and its assets folder.</figcaption></figure>
<div class="card"><ul>
<li><b>Drag-to-sync + two viewer bugs</b> (the 3D parked at the end on a tab's first open; the answer box naming a hidden run): <code>e7e6c57</code>. Undo: <code>git revert e7e6c57 31500e4</code>.</li>
<li><b>Overview O3 + "Does sim match real?"</b> as <code>write_runs_workbench</code>'s defaults: <code>4484abf</code>. Swap without git: <code>overview="league" | "matrix" | "speed" | "tradeoff" | "v2"</code>, <code>sim_vs_real=False</code>. Undo: <code>git revert --no-edit a77ffac^..c0081aa</code>.</li>
<li><b>R2 one timeline</b> as the comparison viewer's default look: <code>d1a2e45</code> (it changes NAVIGATION.md Part B: the stage's slider moved into the lane). Undo: <code>git revert a878cf8 d1a2e45 415f4af</code>.</li>
<li><b>Playback cache keyed by viewer:</b> <code>f412bc7</code>. Undo: <code>git revert f412bc7 c4f841f</code>.</li>
</ul></div>

<h2>1 · V2, landed: dataset → target → playback</h2>
<figure><video src="{{journey}}" autoplay muted loop playsinline controls></video>
<figcaption>The real journey over all 18,507 runs of the four deployments (headless Chrome, 1440×900). Tick UR5e cell (5,750) → ctc_tuned (1,642) → open a target (only ctc_tuned ticked; the other 3 runs listed, unticked, as "outside the rail filter") → back keeps the filter → tick 3 → Open playback → Open in Rerun (dry run: 3 lines per joint, read back from the .rrd).</figcaption></figure>
<div class="grid">
<figure><img src="{{target}}" alt="target view"><figcaption>Level 2, the target view: summary data, a run list ticked from your filter, verdict, joint error per joint. Open playback / Open in Rerun send the ticked runs.</figcaption></figure>
<figure><img src="{{playback}}" alt="playback viewer"><figcaption>Level 3, playback: today's comparison viewer, called as is (3D + question tabs) over the target and exactly the 3 ticked runs. Its breadcrumb goes back to the same ticks.</figcaption></figure>
</div>
<div class="card">
<ul>
<li><b>API:</b> <code>write_runs_workbench(sites, out_dir, *, model_type=None, overview=None, pages=(), views=(), …)</code>. It reads the sites <code>write_dataset_report</code> already writes, one row per measured run. Model type appears only when the caller passes a mapping (the bench passes V2's proposed regex, labelled "proposed").</li>
<li><b>Where your picks plug in:</b> <code>overview=</code> (the Overview round), <code>pages=</code> / <code>views=</code> (the new-tabs round). The playback level calls <code>write_comparison_report</code> unchanged, so the playback round's pick replaces its look in one place.</li>
<li><b>Proof:</b> 16 new tests (14 Python, 2 browser), red first. I re-ran them: 16 pass. Full suite on the lane: 769 pass. 1 timing test failed under load average 80, and main fails it the same way under that load.</li>
<li><b>Fixed from V2's gaps:</b> date tag read; Rerun from a table row; run reports built on demand by <code>traj_compare.serve</code>; the "Name search" pill that cloned a config pick.</li>
<li><b>Still open:</b> playback uses the viewer's own colours, not the config colours. A playback covers one target. The target view's joint charts are two per row, not one. Six data-ui gaps stay worked around in the page; the exact asks are in <code>docs/RUNS_WORKBENCH.md</code>.</li>
</ul></div>

<h2>2 · Overview: 5 proposals</h2>
<p><b>What V2 lost:</b> Nov 23's League led with one answer sentence, then a table per config with sparklines, then a config × dataset heatmap. V2's Overview is a dot plot of 23 configs with cut-off names, plus a speed chart with a 36-entry dataset legend. It has no sentence, no table and no matrix.</p>
<div class="grid">
<figure><img src="{{o3}}" alt="O3"><figcaption><b>O3 Headline tiles → drill</b><span class="score">AI 91</span> six calm answers on the first screen (best config, speed growth, energy frontier, model × dataset coverage, worst target, runs left), each opening its full page.</figcaption></figure>
<figure><img src="{{o1}}" alt="O1"><figcaption><b>O1 The League, back</b><span class="score">AI 86</span> Nov 23's sentence, League table and dataset × split matrix, recomputed over the filter. Ticking the UR5e cell gives exactly Nov 23's numbers.</figcaption></figure>
</div>
<figure><img src="{{o2}}" alt="O2"><figcaption><b>O2 Model × dataset matrix first</b><span class="score">AI 76</span> (your example): model type › config down, deployment › dataset across, best per column ringed; the columns switch to split, speed or deployment.</figcaption></figure>
<p><span class="pick">AI pick: O3 (91).</span> Runner-up O1 (86). If you want the detail on the Overview itself rather than one click away, O1 leads. Natural splice: O3's tiles on top, O1's League under, with O2's matrix as the League's matrix. Also: O4 speed on x (60), O5 trade-off map (63). Every number in all five matched a separate Python check, unfiltered and after the tick.</p>
{{g_over}}

<h2>3 · New tabs: 3 proposals (each a question)</h2>
<div class="grid">
<figure><img src="{{t1}}" alt="T1"><figcaption><b>T1 Does sim match real?</b><span class="score">AI 95</span> real paired with its sim twin (1,752) or rehearsal (1,204). On the pendulum, real is 1.24× the rehearsal and worse in 83%. A row opens the target view with exactly that pair ticked.</figcaption></figure>
<figure><img src="{{t3}}" alt="T3"><figcaption><b>T3 Which config wins head to head?</b><span class="score">AI 87</span> pick A and B. Overall ctc_tuned_v2 beats ctc_tuned on 376 of 502 targets. At 1×, only 35 of 158 (median 0.98), so most of the gain disappears at full speed.</figcaption></figure>
</div>
<figure><img src="{{t2}}" alt="T2"><figcaption><b>T2 Where in the workspace is it worst?</b><span class="score">AI 85</span> each joint's position × speed plane coloured by tracking error. With ctc_tuned the worst cell is wrist_3 on the collision targets (49.5°). Click a cell to list its targets.</figcaption></figure>
<p><span class="pick">AI pick: T1 (95).</span> What would flip it: the UR5e cell has no real runs, so if the work stays on the simulated cell, T3 leads. Note O3 also grows the Overview into eight tabs. If you pick O3, some of these may live there instead.</p>
{{g_tabs}}

<h2>4 · Playback viewer: 5 proposals, every one drags time across every figure</h2>
<p class="mute">In every one of the five, dragging the time on any chart moves every chart's playhead, the 3D pose and the slider (measured within 0.2 ms of the committed time, one sample = 10 ms, on other tabs too); x-zoom keeps its own gesture. Section 0's clip shows the applied pick.</p>
<div class="grid">
<figure><img src="{{r2}}" alt="R2"><figcaption><b>R2 One timeline for the page</b><span class="score">AI 80</span> one playhead line through every chart, plus a time lane with one track per run (its worst moment, where its error rises). It moves the stage's slider into the lane, which changes NAVIGATION.md Part B.</figcaption></figure>
<figure><img src="{{r3}}" alt="R3"><figcaption><b>R3 Summary and playback, one page</b><span class="score">AI 78</span> the target view's run list folded in with live values at the playhead, repeats as lines or bands. If it wins, level 2 merges into level 3.</figcaption></figure>
</div>
<p><span class="pick">AI pick: R2 and R3 are co-leaders (80 vs 78); R2 is applied (section 0).</span> Moving 10 weight points from "drag syncs" to "scales to many runs" puts R3 ahead. Others: R5 moments first (75: opens at the worst moment, ghost arms, value tables), R4 Rerun parity (74), R1 today's page where a drag on any chart scrubs (69, the minimal change). Fixtures: your workspace-dev-000 and BAM FB with 9 of 17 lines.</p>
<p><b>Two bugs in the production viewer</b>, found on the way (the 3D parked at the end on a tab's first open; with a subset of runs, the answer box named a run that isn't shown): both fixed in <code>src/</code> with drag-to-sync (<code>e7e6c57</code>).</p>
{{g_play}}

<h2>Decision surface</h2>
<table>
<tr><th>Done and proved</th><td>V2 landed (<code>8b97871</code>..<code>8399d09</code>) with the browser journey and the .rrd read back. The three rounds (<code>49ef321</code>, <code>b78e632</code>, <code>7284113</code> + <code>5ce1dc3</code>) each passed their headless checks and <code>gallery.py check --strict</code>. The four picks above landed with their tests, red first; I re-ran each lane's tests and the server suites one file per process (all green) and re-drove the three-level journey on <code>main</code>. All pushed; <code>main</code> @ <code>f412bc7</code>.</td></tr>
<tr><th>Decided for you</th><td>Your three levels are the spec: level 2 stays V2's summary target view; level 3 is our comparison viewer or Rerun. The AI pick of each round is applied (section 0, each with its undo). Run KPIs are the bench's own run tags; where a run has none, the Overview and T1 use traj_compare's own tool RMS, counted under each figure (<code>accuracy_fallback=False</code> turns it off). Undo for V2 itself: <code>git revert 8399d09 13e21ea 8b97871</code>.</td></tr>
<tr><th>Needs you</th><td>Nothing blocks. To swap a pick, say which: the galleries below each variant stay live.</td></tr>
<tr><th>Left / next</th><td>The time lane at phone width (~330 px tall) works but isn't polished. Playback in config colours. One target per playback. Old cached playbacks stay on disk until the next sweep. Data-ui asks (drill events, POST body, conditional notes, fold at any width, filtered legends, a stock two-stage median). TTA picks up drag-to-sync and the time lane at its next build.</td></tr>
<tr><th>Deliberately not done</th><td>No data-ui edits (gaps named with exact asks). TTA's uncommitted <code>tools/build_dropins.py</code> edit: not from this session; left for TTA's dispatcher.</td></tr>
</table>
</main></body></html>
"""

if __name__ == "__main__":
    path = build()
    print(path, f"{path.stat().st_size / 1e6:.2f} MB")
