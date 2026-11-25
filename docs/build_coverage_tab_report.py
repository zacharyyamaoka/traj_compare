"""Build the 2026-11-25 report: coverage inside the runs workbench (feedback fb-5defddb0).

Reads the real-bench capture ``docs/coverage_tab_2026-11-25/film.cjs`` wrote into
``reports/media/coverage-tab-2026-11-25/`` (stills, the session video, film.json) and writes one self-contained page,
``reports/media/coverage-tab-2026-11-25.html`` (media inlined, downscaled with ffmpeg so the page stays under the desktop
preview's ~1.9 MB).

    python3 /home/bam/traj_compare/docs/build_coverage_tab_report.py [--cut START END] [--speed X]
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEDIA = REPO / "reports" / "media"
FILM = MEDIA / "coverage-tab-2026-11-25"
OUT = MEDIA / "coverage-tab-2026-11-25.html"


def _still(path: Path, tmp: Path, width: int = 960) -> str:
    out = tmp / (path.stem + ".jpg")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vf", f"scale={width}:-2", "-q:v", "12",
                    str(out)], check=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.read_bytes()).decode()


def _clip(path: Path, tmp: Path, *, start: float, end: float, speed: float, width: int = 900, crf: int = 36) -> tuple[str, str]:
    """(mp4 data URI, gif data URI): the session video cut to [start, end] s, sped up ``speed`` x."""
    mp4 = tmp / "hero.mp4"
    gif = tmp / "hero.gif"
    vf = f"setpts=PTS/{speed},scale={width}:-2"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start}", "-to", f"{end}", "-i", str(path), "-an",
                    "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-vf",
                    "fps=3,scale=420:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=32[p];[b][p]paletteuse=dither=none",
                    str(gif)], check=True)
    return ("data:video/mp4;base64," + base64.b64encode(mp4.read_bytes()).decode(),
            "data:image/gif;base64," + base64.b64encode(gif.read_bytes()).decode())


def build(cut: tuple[float, float] | None = None, speed: float = 1.0) -> Path:
    film = json.loads((FILM / "film.json").read_text("utf-8"))
    t = film["timings"]
    start, end = cut if cut else (max(0.0, t["outer ready"] - 0.3), t["end"] + 0.5)
    steps = film["steps"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        video, gif = _clip(Path(film["video"]), tmp, start=start, end=end, speed=speed)
        stills = {name: _still(FILM / f"{name}.png", tmp) for name in
                  ("01-coverage-tab", "02-embedded-page", "03-other-card", "04-rail-ticked", "05-target-view",
                   "06-highlighted", "07-one-joint-path") if (FILM / f"{name}.png").is_file()}
    cards = steps["tab"]["view"]["cards"]
    ticked = steps["ticked"]["view"]
    card_rows = "".join(f"<tr><td>{html.escape(c['deployment'])}</td><td>{c['of']}</td><td>{c['kept']}</td>"
                        f"<td>{next((x['kept'] for x in ticked['cards'] if x['deployment'] == c['deployment']), '—')}</td></tr>"
                        for c in cards)
    page = TEMPLATE
    values = {
        "video": video, "gif": gif, "card_rows": card_rows,
        "deployment": html.escape(film["deployment"]),
        "shown0": html.escape(steps["tab"]["view"]["shown"] or ""),
        "shown_ticked": html.escape(ticked["shown"] or ""),
        "picked": html.escape((steps.get("picked") or {}).get("view", {}).get("shown") or "—"),
        "target": html.escape(steps["target"]["title"]),
        "chip": html.escape(steps["page"].get("chip") or ""),
        "selected": html.escape("; ".join(steps["page"]["selected"])),
        "errors": str(len(film["errors"])),
        "n_deployments": str(len(cards)),
    }
    for key, uri in {**stills, **values}.items():
        page = page.replace("{{" + key + "}}", uri)
    OUT.write_text(page, encoding="utf-8")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coverage inside the runs workbench</title>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#1f1e1b;--mute:#6b6a64;--line:#e4e2dc;--accent:#2563eb;--good:#15803d;--chip:#eef2ff}
@media (prefers-color-scheme: dark){:root{--bg:#17171a;--card:#202024;--ink:#ecebe6;--mute:#a3a29c;--line:#34343a;--accent:#7aa2ff;--good:#4ade80;--chip:#262a3a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:19px;margin:34px 0 8px}
p{margin:6px 0}.mute{color:var(--mute)}.verdict{font-size:17px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
figure{margin:12px 0}figure img,figure video{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;display:block;background:#fff}
figcaption{color:var(--mute);font-size:13px;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
a{color:var(--accent)}ul{margin:6px 0 6px 20px;padding:0}li{margin:3px 0}
code{background:var(--chip);padding:0 4px;border-radius:4px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
</style></head><body><main>
<h1>Coverage is a tab of the traj_compare viewer now</h1>
<p class="mute">2026-11-25 · feedback fb-5defddb0, your Daily Note Nov 23 "Coverage Feedback": <i>"I need to basically like integrate this into the viewer ... a page you can see standalone or just quickly get there from the traj compare stuff"</i> · Claude Code (Opus 5.5)</p>

<div class="verdict"><b>The runs workbench (the traj_compare viewer since Nov 24) has a Coverage tab, and every target view has a "Coverage ↗" that opens that one trajectory, highlighted.</b> The tab embeds each deployment's own coverage page, unchanged, so the tab and the standalone page can't disagree. The rail picks which deployment the tab shows and recounts its cards. It doesn't refilter the page, and the tab says so.</div>

<h2>The flow, on the real bench</h2>
<figure><video src="{{video}}" autoplay muted loop playsinline controls></video>
<figcaption>Headless Chrome at 1440×900 on <code>arm_motion_bench/reports/media/dashboard/all</code>, rebuilt from <code>main</code>: open Coverage → the embedded page → pick another deployment's card → tick <b>{{deployment}}</b> in the rail (the cards recount, the tab follows) → Targets → open a target view → <b>Coverage ↗</b> → that target highlighted on its deployment's coverage page, then its path drawn in black on One joint. Console and network errors during the run: {{errors}}.</figcaption></figure>
<details><summary>GIF fallback</summary><img src="{{gif}}" alt="the same flow as a GIF" style="max-width:100%"></details>

<h2>What each step shows</h2>
<div class="grid">
<figure><img src="{{01-coverage-tab}}" alt="Coverage tab"><figcaption><b>The Coverage tab.</b> One card per deployment with a coverage page ({{n_deployments}} on the bench), each with its page's own headline numbers. It opens on <b>{{shown0}}</b>, with that deployment's page embedded below and "Open on its own ↗" beside it.</figcaption></figure>
<figure><img src="{{02-embedded-page}}" alt="embedded page"><figcaption><b>The page inside the tab</b> is the coverage viewer you reviewed on Nov 23 (its tabs, colour map, Reverse, Linear by default), unchanged. Its breadcrumb opens in the whole window, not inside the tab.</figcaption></figure>
<figure><img src="{{03-other-card}}" alt="another card"><figcaption><b>Pick another card</b> ({{picked}}): the frame switches to that deployment's page. The pick is remembered.</figcaption></figure>
<figure><img src="{{04-rail-ticked}}" alt="rail ticked"><figcaption><b>Tick {{deployment}} in the rail:</b> every card recounts how many of its targets the rail keeps runs of. The tab moves to <b>{{shown_ticked}}</b> because the rail keeps none of the picked deployment.</figcaption></figure>
<figure><img src="{{05-target-view}}" alt="target view"><figcaption><b>A target view ({{target}})</b> gets <b>Coverage ↗</b> beside Open playback and Open in Rerun when its site has a coverage page.</figcaption></figure>
<figure><img src="{{06-highlighted}}" alt="highlighted"><figcaption><b>One trajectory in its dataset:</b> the page opens on Trajectories with the row selected (<code>{{selected}}</code>) and the chip "{{chip}}".</figcaption></figure>
</div>
<figure><img src="{{07-one-joint-path}}" alt="one joint"><figcaption>The same highlight carries to <b>One joint</b>: its position × speed path in black over the dataset's faint ones (and the 3-D views).</figcaption></figure>

<h2>The cards, read from the page</h2>
<table><tr><th>Deployment</th><th>Target trajectories on its page</th><th>Targets the rail keeps runs of (no filter)</th><th>… after ticking {{deployment}}</th></tr>{{card_rows}}</table>

<h2>Decision surface</h2>
<table>
<tr><th>Done and proved</th><td>Spec first, red on <code>eca941c</code> (Python 4 failed, browser 2 failed), then green: <code>tests/test_runs_workbench_coverage.py</code> (the tab, its numbers equal to <code>coverage.json</code>'s, each target's trajectory name, no tab when no site has a page) and <code>tests/test_runs_workbench_coverage_browser.py</code> (the tab embeds a page that draws, the counts recount on a tick, Open on its own is the standalone URL, a target view's Coverage ↗ highlights exactly its row, no link on a site without a page). The coverage, runs workbench and dataset suites pass (143). The bench was filmed above on the fix's code. <b>My own edit to the spec after its red commit:</b> "the embedded page drew" first looked only for heatmap canvases, which the Overview tab doesn't have, so it now checks the shown tab's figures for SVG marks or inked canvases. Failed loads are now named by URL (favicon excluded), and I added a check that framed links leave the frame.</td></tr>
<tr><th>Decided for you</th><td>A <b>tab that embeds the page</b> (an iframe of the site's own file), not a redraw in data-ui, so there's one coverage viewer. The tab sits <b>after Runs and "Does sim match real?"</b>. Target view → <b>Trajectories tab with the row highlighted</b>, added to the page as <code>#trajectory=&lt;name&gt;</code>. The tab <b>does not refilter</b> the page: it counts every target of a deployment once, so the rail picks the deployment and the answer line says so. Undo: <code>git revert</code> the fix commit; the tab disappears and nothing else moves.</td></tr>
<tr><th>Left / next</th><td><b>A rail-filtered coverage tab</b> (coverage of exactly the targets the rail keeps) needs each site to write the coverage workbench (<code>traj_compare.coverage.workbench</code>, per-trajectory parts that re-sum) and the rail carried into it. That's the natural next leg if you want ticks to recount the heatmaps too. Coverage of the <i>measured</i> runs (what the robot actually did, not the targets) isn't built. <b>Pre-existing, not from this change:</b> arm_motion_bench's dashboard parity test (<code>tests/test_dashboard.py -k same_files_as_before</code>) already fails on traj_compare <code>main</code> before this change, on <code>index.html</code> and <code>coverage/index.html</code> (traj_compare commits since the fixture's 38b5967). This change moves only the second of those. I didn't regenerate it, so I'm not ratifying an <code>index.html</code> diff I haven't reviewed.</td></tr>
<tr><th>Needs you</th><td>Nothing.</td></tr>
<tr><th>Deliberately not done</th><td><code>write_dataset_report(coverage=)</code> still defaults to <code>False</code>, so a site that doesn't ask writes no page and its tab card doesn't appear (the bench asks for every site). No data-ui changes.</td></tr>
</table>
</main></body></html>
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cut", nargs=2, type=float, default=None, metavar=("START", "END"))
    parser.add_argument("--speed", type=float, default=1.0)
    options = parser.parse_args()
    path = build(tuple(options.cut) if options.cut else None, options.speed)
    print(path, f"{path.stat().st_size / 1e6:.2f} MB")
