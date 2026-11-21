"""Build the 2026-11-20 scale-and-signals review: the seven gaps arm_motion_bench reported, fixed (NAVIGATION.md Part C).

One self-contained HTML page (media inlined as data URIs, so it opens on any device), written to the main checkout's
``reports/media/``. WHY every still is re-encoded as WebP and the clip as H.264 at 1200 px: the desktop preview dies
above ~1.9 MB on disk; ``build()`` refuses a bigger page. The hero's GIF fallback (480 px, 3 fps) is inlined too and
swapped in only where the browser cannot play the H.264 clip; the caption also links the GIF file beside the page.

Media: ``record_hero.py`` (hero clip + timeline), ``shoot_stills.py`` (the "after" stills, shot with the bench's own
steps), the bench's "before" shots (``/home/bam/arm_motion_bench/reports/media/dashboard/shots/``, read only) and the
C1 proof shots from the channels lane (fixture data). Sources outside ``reports/media`` are copied in once, so the page
still builds after the bench reshoots or the lane's worktree is swept.

    env -u VIRTUAL_ENV /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/scale_signals_2026-11-20/build_report.py
"""

from __future__ import annotations

import base64
import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
REPORTS = PACKAGE / "reports" / "media"
MEDIA = REPORTS / "traj-compare-scale-signals-2026-11-20"
OUT = REPORTS / "traj-compare-scale-signals-2026-11-20.html"
FFMPEG = "/usr/bin/ffmpeg"
PIN = ["taskset", "-c", "2-5,16,17", "nice", "-n", "19"]
MAX_BYTES = 1_900_000  # the desktop preview's ceiling for a page with media

HEAD = "a70ac47"  # main after the seven gaps (243f892), the sim → real follow-up (c869be7) and incremental writes
REPO = "zacharyyamaoka/traj_compare"
INCREMENTAL = PACKAGE / "docs" / "incremental_2026-11-20"  # Part D's measurements, versioned beside their scripts
BENCH_SHOTS = Path("/home/bam/arm_motion_bench/reports/media/dashboard/shots")
C1_SHOTS = PACKAGE / ".claude" / "worktrees" / "channels" / "docs" / "proof_c1"
COPIES = {  # name inside MEDIA → where it came from (copied once; the page builds from the copy)
    "before/ur5e-2-target.png": BENCH_SHOTS / "ur5e-2-target.png",
    "before/ur5e-1b-dataset-table.png": BENCH_SHOTS / "ur5e-1b-dataset-table.png",
    "c1/c1-channels-tab.png": C1_SHOTS / "c1-channels-tab.png",
    "c1/c1-signals-motor-current.png": C1_SHOTS / "c1-signals-motor-current.png",
    # the follow-up the bench reported after switching (2026-11-20): a sim → real torque legend said "Target"
    "followup/pendulum-7-sim-real-torque.png": BENCH_SHOTS / "pendulum-7-sim-real-torque.png",
    "followup/pendulum-sim-real-torque-after.png": Path(
        "/tmp/claude-1000/-home-bam--claude-jidoka-spares-spare-rrpsDw/b331c896-01c1-4684-837b-e19d9e0e6e2f/scratchpad/"
        "pendulum-sim-real-torque-after.png"),
}
SERVE = ("env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python -m traj_compare.serve "
         "/home/bam/arm_motion_bench/reports/media/dashboard --port 8779")  # fmt: skip
# WHY the bench's own folder: it rebuilt all three sites with this code at 14:42-14:49 (index 19.2 / 10.3 / 13.4 MB),
# so the live dashboards are the after state; the scratch rebuild was only the measurement.

STYLE = """
:root{--ink:#22221f;--muted:#6f6e69;--line:#e3e2dc;--bg:#fafaf7;--card:#fff;--accent:#2f6fdf;--ok:#2f8f4e;--warn:#b7791f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}h1{font-size:26px;margin:0 0 10px;line-height:1.25}
h2{font-size:20px;margin:38px 0 10px;border-top:1px solid var(--line);padding-top:24px}h3{font-size:16px;margin:26px 0 6px}
.kicker{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.verdict{font-size:17px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);padding:12px 16px;border-radius:8px;margin:12px 0}
figure{margin:14px 0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
figure img,figure video{width:100%;display:block;border-radius:4px}figure img{cursor:zoom-in}
figcaption{color:var(--muted);font-size:13px;padding:6px 4px 0}figcaption b{color:var(--ink)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid2 figure{margin:0}
figure.big{grid-column:1/-1}figure.big img{cursor:zoom-out}
.tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;border-radius:10px;padding:1px 8px;margin-right:6px}
.before{background:#f3f2ee;color:#6f6e69;border:1px solid #dcdbd5}.after{background:#e8f4ec;color:#2f8f4e;border:1px solid #bfe0c9}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px;margin:8px 0}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:#f2f1ec}
td.num{white-space:nowrap}
code{background:#f0efe9;padding:1px 4px;border-radius:3px;font-size:13px;overflow-wrap:anywhere}
pre{background:#f0efe9;padding:10px;border-radius:6px;overflow:auto;font-size:13px;white-space:pre-wrap;word-break:break-all}
ul{padding-left:20px}li{margin:4px 0}.note{color:var(--muted);font-size:13px}
.gap{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:4px 16px 12px;margin:14px 0}
.gap h3{margin-top:14px}.gap p{margin:6px 0}.gap .api{margin:6px 0}.commit{color:var(--muted);font-size:13px}
.missing{color:#b42318;padding:20px}figure.narrow{max-width:780px}.grid2.narrowpair{max-width:860px}.scroll{overflow-x:auto}
@media (max-width:800px){.grid2{grid-template-columns:1fr}}
"""

SCRIPT = """
document.addEventListener('click', function (event) {
  var img = event.target.closest('figure img');
  if (img) img.closest('figure').classList.toggle('big');
});
// The inlined GIF stands in only where this browser cannot play the H.264 clip.
(function () {
  var video = document.getElementById('hero');
  if (!video) return;
  function fallback() {
    var img = document.createElement('img');
    img.src = video.getAttribute('data-gif');
    img.alt = 'hero clip (GIF fallback)';
    video.replaceWith(img);
  }
  if (!video.canPlayType('video/mp4')) fallback();
  else video.addEventListener('error', fallback);
})();
"""


def copy_sources() -> None:
    for name, source in COPIES.items():
        target = MEDIA / name
        if not target.is_file() and source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _ffmpeg(*args: str) -> None:
    subprocess.run([*PIN, FFMPEG, "-v", "error", "-y", *args], check=True, capture_output=True)


def still(path: Path, width: int, crop: tuple[int, int, int, int] | None = None, quality: int = 72) -> str:
    """A PNG screenshot as a WebP data URI: ``crop`` = (x, y, w, h) in source pixels, then scaled to ``width``."""

    filters = ([f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}"] if crop else []) + [f"scale='min({width},iw)':-2:flags=lanczos"]
    # WHY a file, not stdout: on a pipe ffmpeg's webp muxer cannot seek back, and an image over ~32 kB keeps a RIFF
    # size of 0, which Chrome refuses to decode (measured 2026-11-19).
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "still.webp"
        _ffmpeg("-i", str(path), "-vf", ",".join(filters), "-c:v", "libwebp", "-quality", str(quality),
                "-compression_level", "6", str(target))  # fmt: skip
        data = target.read_bytes()
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise SystemExit(f"bad WebP header for {path}")
    return "data:image/webp;base64," + base64.b64encode(data).decode()


def fig(path: Path, caption: str, width: int = 1000, crop: tuple[int, int, int, int] | None = None, quality: int = 72,
        css: str = "") -> str:
    klass = f' class="{css}"' if css else ""
    if not path.is_file():
        return f'<figure{klass}><div class="missing">missing: {html.escape(str(path))}</div><figcaption>{caption}</figcaption></figure>'
    return f'<figure{klass}><img src="{still(path, width, crop, quality)}" alt=""><figcaption>{caption}</figcaption></figure>'


def hero(timeline: dict) -> str:
    mp4, gif = MEDIA / "hero" / "hero.mp4", MEDIA / "hero" / "hero.gif"
    if not mp4.is_file():
        return f'<figure><div class="missing">missing: {html.escape(str(mp4))}</div></figure>'
    marks = {mark["name"]: mark for mark in timeline["marks"]}
    gif_rel = gif.relative_to(OUT.parent).as_posix()
    caption = (
        f"The real thing, recorded headless at 1440×900, {timeline['duration_s']:.0f} s, real time: "
        "<b>one server</b> for the folder holding the bench's three sites answers <code>/</code> with a landing page (C3) → "
        f"<b>UR5e</b>: 1006 target cards, the 19 MB index ready in {marks['site']['load_ms'] / 1000:.1f} s → a fast scroll past the "
        "bench's scorecard into the cards, whose charts are grey placeholders until each target's own file arrives (C5) → "
        f"a jump to card {marks['jump']['index'] + 1}, the target of the bench's “before” shot (placeholders drawn "
        f"{marks['jump-drawn']['after_ms'] / 1000:.2f} s later) → <b>Open target</b>: four controllers in four colours (C4), every chart "
        f"“{html.escape(marks['target']['rate'])}” (C5) → the ↗ of <i>{html.escape(timeline['line'].split(' · ', 3)[3])}</i>: "
        f"its run report did not exist; the server built it on that click ({marks['run']['build_and_load_ms'] / 1000:.1f} s, a site one "
        "level below the served root, C3). The grey dot is the mouse."
    )
    gif_uri = "data:image/gif;base64," + base64.b64encode(gif.read_bytes()).decode() if gif.is_file() else gif_rel
    return (f'<figure><video id="hero" src="data:video/mp4;base64,{base64.b64encode(mp4.read_bytes()).decode()}" '
            f'data-gif="{gif_uri}" autoplay muted loop playsinline controls></video>'
            f'<figcaption>{caption} <a href="{gif_rel}">GIF version</a>.</figcaption></figure>')  # fmt: skip


def pair(before: str, after: str, css: str = "") -> str:
    return f"<div class='grid2 {css}'>{before}{after}</div>"


def commit(*shas: str) -> str:
    return "<p class='commit'>" + " · ".join(f"<code>{sha}</code>" for sha in shas) + "</p>"


def body() -> str:
    timeline = json.loads((MEDIA / "hero" / "hero-timeline.json").read_text("utf-8"))
    stills_info = json.loads((MEDIA / "stills" / "stills.json").read_text("utf-8"))
    before, after, c1 = MEDIA / "before", MEDIA / "stills", MEDIA / "c1"
    bench_tag, main_tag = "<span class='tag before'>before</span>", "<span class='tag after'>after</span>"
    esc = html.escape
    held = len(stills_info.get("held", []))

    parts = [
        "<div class='kicker'>traj_compare · 2026-11-20 · scale and signals (NAVIGATION.md Part C) · Claude Code (Opus 5.5)</div>",
        "<h1>traj_compare at bench scale: the seven gaps arm_motion_bench worked around</h1>",
        f"<p class='verdict'><b>All seven gaps the bench reported are fixed — on traj_compare <code>main</code> @ <code>{HEAD}</code></b>, "
        f"pushed to the private <code>{REPO}</code>. The UR5e's index halves (38.1 → 19.2 MB) while drawing 16× finer (3.2 → 50 Hz); "
        "one server serves all three robots; four controllers get four colours. Later the same day the bench asked for incremental "
        "rebuilds: an unchanged run or target is now reused, so on 1,500 real UR5e runs adding 225 takes 22 s instead of 74 s and a "
        "rebuild with nothing changed 5 s. Qualification: the bench's data has no extra channels, so the signals work is shown on "
        "fixture data.</p>",
        hero(timeline),
        # ── numbers ──────────────────────────────────────────────────────────────────────────────────────────────
        "<h2>Before → after, on the bench's own data</h2>",
        "<p>Before is the bench's own build from 12:4x today. After is the same build script (<code>dashboard.py build --no-hero "
        "--display-hz 50</code>) run on the new code into a scratch folder.</p>",
        "<div class='scroll'><table><tr><th>Robot</th><th>What</th><th>Before</th><th>After</th></tr>"
        "<tr><td rowspan='6'><b>UR5e</b><br>1006 targets<br>4932 runs</td><td>index.html</td><td class='num'>38.1 MB, drawn at 3.2 Hz</td><td class='num'><b>19.2 MB, drawn at 50 Hz</b></td></tr>"
        "<tr><td>rows.json</td><td>671 MB (the bench deletes it by hand)</td><td>not written with <code>rows=(\"parquet\",)</code> (C2)</td></tr>"
        "<tr><td>runs/</td><td>2.3 GB, of which 0.81 GB per-run copies of the reference (974 distinct of 4932)</td>"
        "<td>1.4 GB + <code>references/</code> 121 MB, one file per distinct reference (974)</td></tr>"
        "<tr><td>targets/</td><td>(series were in the index)</td><td>274 MB in 1006 files, largest 1.9 MB, each loaded only when its target is seen</td></tr>"
        "<tr><td>build</td><td class='num'>296 s</td><td class='num'>287 s, peak memory 5.7 GB</td></tr>"
        f"<tr><td>open in a browser</td><td>—</td><td class='num'>{timeline['marks'][1]['load_ms'] / 1000:.1f} s to the 1006 cards (headless, this host)</td></tr>"
        "<tr><td><b>pendulum</b></td><td>index.html</td><td class='num'>12.6 MB at 50 Hz, 2301 runs</td><td class='num'><b>9.7 MB at 50 Hz, 3464 runs</b></td></tr>"
        "<tr><td><b>BAM FB</b></td><td>index.html</td><td class='num'>25.9 MB at 19.9 Hz, 1648 runs</td><td class='num'><b>13.0 MB at 50 Hz, 2914 runs</b></td></tr>"
        "</table></div>",
        "<p class='note'>The bench added runs between the two builds (pendulum +1163, BAM FB +1266), so those rows compare a bigger "
        "dataset after. What still fills the UR5e's 19 MB index: per-joint stats in the runs table 4.2 MB, target time grids 3.6 MB, "
        "the runs list 2.1 MB, per-line torque numbers 1.9 MB, per-line RMS 1.2 MB.</p>",
        "<h3>The same target, the same clicks</h3>",
        "<p>The after shot repeats the bench's own screenshot steps (dataset page → Table → Cards → Open target, 1.6 s, shoot), so "
        "viewport, scroll position and mouse position match.</p>",
        pair(fig(before / "ur5e-2-target.png", f"{bench_tag}<b>Bench build, old code.</b> The four controllers are four greys, and "
                 "every line is a polyline drawn at 3.2 Hz.", 1000),
             fig(after / "ur5e-2-target.png", f"{main_tag}<b>main @ {HEAD}.</b> Four hues (ctc_model_err violet, ctc_tuned teal, id_pd "
                 "crimson, menagerie_stock ochre); each chart says <i>drawn at 50 Hz</i>.", 1000)),
        pair(fig(before / "ur5e-2-target.png", f"{bench_tag}One chart, zoomed: 3.2 Hz corners.", 640, (337, 368, 535, 345), 80),
             fig(after / "ur5e-2-target.png", f"{main_tag}The same chart at 50 Hz, its rate in the title.", 640, (337, 385, 535, 345), 80)),
        # WHY stacked full width, cropped to the table: side by side at half width the dots and sparklines are too small to tell apart.
        fig(before / "ur5e-1b-dataset-table.png", f"{bench_tag}The targets table (Table view): grey swatches, grey dots, grey sparklines.",
            1140, (0, 430, 1440, 470)),
        fig(after / "ur5e-1b-dataset-table.png", f"{main_tag}The same table, same clicks: each config its own colour in the swatches, "
            "dots and sparklines.", 1140, (0, 430, 1440, 470)),
        # ── the seven gaps ───────────────────────────────────────────────────────────────────────────────────────
        "<h2>The seven gaps, one by one</h2>",
        "<div class='gap'><h3>1 + 2 · Signals beyond the joints: motor current, contact force, detector residual (C1)</h3>"
        "<p><b>Was:</b> the run view drew joints and torques only; the bench had motor current and other signals with nowhere to put them.</p>"
        "<p><b>Now:</b> a series' <code>channels[\"current\"]</code> is the run report's motor current (HTML signals tab; Rerun gets a "
        "<i>Motor current [A]</i> sub-tab). Every other channel gets the new tab <b>What else was measured?</b> in HTML and Rerun, one "
        "section per channel, titled with its unit; a channel nobody described is still drawn under its own name. Parquet and MCAP "
        "exports carry them too. A one-joint series may log current flat, shape (N,).</p>"
        "<p class='api'><code>write_dataset_report(..., signals={\"contact_force\": traj_compare.Signal(title=\"Contact force\", unit=\"N\", columns=(\"x\", \"y\", \"z\"))})</code></p>"
        + fig(c1 / "c1-channels-tab.png", "<b>What else was measured?</b> (fixture data): one section per channel, one plot per column, "
              "units in the titles (the page goes on with winding temperature and two channels nobody described, drawn under their "
              "recorded names).", 1140, (0, 60, 1440, 720))
        + fig(c1 / "c1-signals-motor-current.png", "The signals tab's <b>motor current</b> (fixture data), one plot per joint, "
              "in the run colours.", 1140)
        + "<p class='note'>Fixture data: the bench's runs carry no channels yet. Rerun's side (the tab and the Motor current sub-tab) is "
        "pinned by the acceptance tests, not pictured here.</p>"
        + commit("b4a0bdb (merge 34da438)", "dea63c1 one-joint flat current", "f417ec1 exports") + "</div>",
        "<div class='gap'><h3>3 · Row files (C2)</h3>"
        "<p><b>Was:</b> every write produced a 460–690 MB <code>rows.json</code>, which the bench deleted by hand.</p>"
        "<p><b>Now:</b> the caller picks the row files. Content and columns are unchanged; a file not chosen this time is deleted, so "
        "stale rows never outlive their data; a bad name fails before anything is written.</p>"
        "<p class='api'><code>write_dataset_report(..., rows=(\"parquet\",))</code> · <code>rows=()</code> writes none · default "
        "<code>None</code> as before</p>"
        "<p class='note'>In this rebuild the bench's script still wrote rows.json (688 MB) and deleted it afterwards: it does not pass "
        "<code>rows=</code> yet.</p>" + commit("4029ed1 (merge fc26e2e)") + "</div>",
        "<div class='gap'><h3>4 · One server, many sites (C3)</h3>"
        "<p><b>Was:</b> one server per site, and run reports were built lazily only for a site at the served root.</p>"
        "<p><b>Now:</b> one server serves every site at any depth below the folder it is given, and builds any site's run report on "
        "its first request, straight from that run's folder. When the folder has no index.html of its own, <code>/</code> is a landing "
        "page listing the sites up to 3 levels deep.</p>"
        "<p class='api'><code>python -m traj_compare.serve &lt;folder&gt;</code> · <code>traj_compare.dataset.build_run_folder(folder)</code></p>"
        + fig(after / "landing.png", "The landing page, as served: one link per site with its title and run count.", 760, None, 85, "narrow")
        + "<p class='note'>The hero shows the rest: the ↗ on a UR5e line, one level below the served root, built that run's report on the click.</p>"
        + commit("45c3432", "cc49a2b") + "</div>",
        "<div class='gap'><h3>5 · Config colours (C4)</h3>"
        "<p><b>Was:</b> any config without real lines was grey, so the UR5e's four sim-only controllers were four greys.</p>"
        "<p><b>Now:</b> grey marks a sim-only config only in the <i>twin case</i> (exactly one config has no real lines and some config "
        "has real lines). Every other config takes the next hue; all distinct for up to 24 configs, never the torque blue or the orange. "
        "Sim lines are still dashed, so kind is never shown by colour alone.</p>"
        "<p class='note'>Evidence: the before/after target and table pairs above.</p>" + commit("cf105f9 (merge 7c8db3d)") + "</div>",
        "<div class='gap'><h3>6 · Index size (C5)</h3>"
        "<p><b>Was:</b> every line's time series sat in index.html; the UR5e's 38 MB page only opened at 3.2 Hz.</p>"
        "<p><b>Now:</b> the index holds scalars only. Each target's drawn series live in <code>targets/&lt;slug&gt;.js</code>, loaded when "
        "the target opens or its card scrolls into view (a plain script tag, so it works from file:// too). Series are picked at "
        "<code>display_hz</code> (50 by default), never averaged; one target's file is capped at <code>target_budget</code> values; every "
        "chart and card says the rate it actually draws.</p>"
        "<p class='api'><code>write_dataset_report(..., display_hz=50, target_budget=2_000_000)</code></p>"
        # WHY the middle column only: at half width the whole 3-column grid is too small to read the placeholder text.
        + pair(fig(after / "lazy-held.png", f"UR5e cards (middle column), scrolled one row past what has loaded: the next card's chart "
                   f"is a placeholder until its file arrives (for this shot the {held} target files in flight were held; on localhost "
                   "they arrive in ~0.2 s).", 560, (490, 60, 460, 810), 75),
               fig(after / "lazy-drawn.png", f"The same view once the files arrived ({stills_info.get('drawn_after_release_ms', 0)} ms "
                   "after release): drawn, “drawn at 50 Hz”.", 560, (490, 60, 460, 810), 75), "narrowpair")
        + commit("cf105f9 (merge 7c8db3d)") + "</div>",
        "<div class='gap'><h3>7 · Disk (C6)</h3>"
        "<p><b>Was:</b> each of 4932 run folders held its own copy of the reference; only 974 were distinct (0.81 GB of copies).</p>"
        "<p><b>Now:</b> one <code>references/&lt;digest&gt;.npz</code> per distinct reference (SHA-1 of its content), named from each "
        "manifest; unreferenced ones are deleted; old manifests still build. Every .npz the dataset writes is compressed, values "
        "bit-identical.</p>"
        "<p class='note'>UR5e: runs/ 2.3 → 1.4 GB, plus references/ 121 MB in 974 files.</p>" + commit("4029ed1 (merge fc26e2e)") + "</div>",
        "<div class='gap'><h3>Follow-up · a sim → real pair names its reference (reported by the bench after it switched)</h3>"
        "<p><b>Was:</b> in a run-to-run pair the reference is a run, not a target. The pendulum's <i>sim → real</i> torque legend "
        "still called the sim run's <b>applied</b> torque “Target”, a different signal. The toolbar said “Error vs target”, the 3D "
        "dropdown “Arrows → target”, and Rerun's torque views “— target, …”.</p>"
        "<p><b>Now:</b> <code>Comparison.reference_kind</code> is <code>\"target\"</code> (default, wording unchanged) or "
        "<code>\"run\"</code>. The dataset drill-down sets it for every pair whose first element is a measured series. Every place "
        "that named the reference then says <i>sim τ (applied)</i>, <i>Error vs sim</i>, <i>Arrows → sim</i>, and in Rerun "
        "<i>sim (applied)</i>.</p>"
        + pair(fig(MEDIA / "followup" / "pendulum-7-sim-real-torque.png", "<span class='tag before'>before</span> The bench's own "
                   "shot: components “Target · Feedforward · Applied”, “Error vs target”.", 1000, (440, 280, 1000, 620), 75),
               fig(MEDIA / "followup" / "pendulum-sim-real-torque-after.png", "<span class='tag after'>after</span> The same run, "
                   "rebuilt from a copy of its folder: “sim τ (applied)”, “Torque breakdown: sim (applied), …”, “Error vs sim”.",
                   1000, (440, 280, 1000, 620), 75))
        + commit("c869be7") + "</div>",
        # ── follow-up 2: incremental writes (Part D) ─────────────────────────────────────────────────────────────
        incremental_section(),
        # ── decision surface ─────────────────────────────────────────────────────────────────────────────────────
        "<h2>Decided for you</h2><ul>"
        "<li><b>The channels tab is not one of the fixed tabs</b>: it is <code>tabs.CHANNELS_TAB</code>, shown only when some situation "
        "has a channel, as the check tabs are. Undo: move it into <code>traj_compare.tabs.TABS</code>.</li>"
        "<li><b>Target time grids stay in the index</b> (3.6 MB of the UR5e's 19 MB): tests pin <code>target[\"t\"]</code> there. "
        "Undo: move them into <code>targets/&lt;slug&gt;.js</code> and update those tests.</li>"
        "<li><b>Every .npz is compressed</b> (about +20 % on the run-file writes, lost in the noise of the UR5e build). Undo: "
        "<code>np.savez</code> in place of the two <code>np.savez_compressed</code> calls in <code>dataset.py</code>.</li>"
        "<li><b>A one-joint series may log current flat, (N,)</b>, as <code>Run.torques</code> already accepts 1-D (the pendulum). "
        "Undo: <code>git revert dea63c1</code>.</li>"
        "<li><b><code>rows=None</code> stays the default</b> (rows.json still written) because other bam_ws code reads rows.json. Undo: "
        "default <code>rows=(\"parquet\",)</code> once nothing reads it.</li>"
        "<li><b>Grey only for the twin case, and the slate hue (<code>#6b7a8f</code>, a blue-grey) dropped from the named hues</b>, so "
        "no config passes for the twin grey. Undo: <code>git revert -m 1 7c8db3d</code> (it also reverts C5).</li>"
        "<li><b>robot_msgs untouched</b>: compression and deduplication live in traj_compare's writer, not the message format.</li>"
        "<li><b>Undo everything:</b> revert the 14 first-parent commits from <code>e22e512</code> back to <code>040f536</code>, newest "
        "first, the three merges (<code>7c8db3d</code>, <code>34da438</code>, <code>fc26e2e</code>) with <code>-m 1</code>.</li>"
        "<li><b>Incremental writes are on by default</b> (<code>reuse=True</code>): a write into a folder an earlier write made reuses "
        "every run and target whose digest matches. Undo for one write: <code>reuse=False</code>; for good: "
        "<code>git revert a70ac47 0d59e28 14662f6 34411a4</code>.</li>"
        "<li><b>The digest covers code files, not <code>__version__</code></b>: traj_compare's files, robot_msgs's <code>.py</code> and "
        "the files defining the <code>poses</code> / <code>robot</code> functions. So the first build after a commit to either package "
        "is a full one; stale numbers after a code change were the alternative.</li>"
        "<li><b><code>display_hz</code>, <code>target_budget</code> and <code>config_by</code> are not in the run digest</b>: they do not "
        "change a run's files or analysis, so changing them recomputes only the targets.</li>"
        "<li><b>An old pin was rewritten</b>: <code>test_dataset_serve::test_rewriting_a_dataset_drops_the_stale_drill_down</code> "
        "(2026-11-11) assumed every rewrite rewrote every run. It now drops the drill-down when the run's data changes and keeps it "
        "when only <code>title</code> or <code>drill_down</code> change (<code>a70ac47</code>).</li></ul>",
        "<h2>Left</h2><ul>"
        "<li><b>The bench has to switch</b> (message sent to its agent): pass <code>rows=(\"parquet\",)</code>, put its signals in "
        "<code>channels</code> with <code>signals=</code>, serve its three sites with one server, and set <code>display_hz</code> back to 50.</li>"
        "<li>Channels on the Dataset and Target levels: out of scope (a per-run scalar such as peak force stays a run tag).</li>"
        "<li>The UR5e index's remaining 19 MB: the runs table's per-joint stats (4.2 MB) and the target time grids (3.6 MB) could move "
        "into the per-target files next.</li>"
        "<li>Two channel names that escape to the same Rerun entity path share one view.</li>"
        "<li><b>Incremental writes on the full UR5e site</b> (5,750 runs + 818) are extrapolated, not measured: the machine had 11 GB "
        "free, so the run was capped at 1,500 runs. The harness runs the full set: "
        "<code>docs/incremental_2026-11-20/bench_ur5e.py</code>.</li>"
        "<li><code>group_by</code> cards are not cached: a dataset with a <code>group_by</code> whose groups share a reference still "
        "computes every run's TCP poses for them (the bench passes none).</li>"
        "<li>Two browser tests are load-sensitive at this host's load of 30: <code>test_playback</code> (first video frame 0.78 s against "
        "a 0.6 s limit, also on the old code) and the run-list drag in <code>test_dataset_levels</code>.</li></ul>",
        "<h2>How it was built</h2><ul>"
        "<li>The contract first: <code>docs/NAVIGATION.md</code> Part C, frozen in <code>040f536</code>.</li>"
        "<li>Acceptance tests next, written by separate agents before each implementation (<code>c2397e3</code>, <code>dae8c29</code>, "
        "<code>be8ab1c</code>, <code>37c311d</code>) and never edited by the implementers; their checksums were verified at every merge.</li>"
        "<li>Implementers in their own worktrees (channels, files, lazy-targets, serve-sites); the dispatcher merged each lane.</li>"
        "<li>Full suite on <code>main</code> after the last merge: <b>481 passed, 0 failed</b>.</li></ul>",
        "<h2>Open it</h2>",
        "<p>The three rebuilt bench sites, one server (run reports are built the first time you open them; the bench's interpreter "
        "serves because the run manifests import its robot model, which needs mujoco):</p>",
        f"<pre>{esc(SERVE)}</pre>",
        "<p class='note'>Then open <code>http://127.0.0.1:8779/</code>. That folder is scratch: it lasts until /tmp is cleared, and the "
        "bench's own rebuild replaces it. Ctrl-C stops the server.</p>",
        "<p class='note'>Media scripts: <code>docs/scale_signals_2026-11-20/</code> (<code>record_hero.py</code>, <code>shoot_stills.py</code>, "
        "<code>build_report.py</code>).</p>",
    ]
    return "\n".join(parts)


def _timings_svg(rows: list[dict]) -> str:
    """Horizontal bars, one per scenario, labelled with its seconds (a plain SVG: no chart library for three numbers)."""
    names = {"fresh": "Fresh write (reuse=False)", "added": "+225 runs into the same folder", "unchanged": "Nothing changed"}
    shown = [row for row in rows if row.get("scenario") in names]
    shown.sort(key=lambda row: list(names).index(row["scenario"]))
    top = max(row["seconds"] for row in shown)
    width, left, bar = 720, 230, 26
    out = [f"<svg viewBox='0 0 {width} {len(shown) * 40 + 10}' width='100%' style='max-width:{width}px' role='img' "
           "aria-label='write_dataset_report seconds per scenario'>"]
    for index, row in enumerate(shown):
        y = 8 + index * 40
        length = (width - left - 70) * row["seconds"] / top
        colour = "#c9c7bf" if row["scenario"] == "fresh" else "#2f8f4e"
        out.append(f"<text x='{left - 10}' y='{y + 18}' text-anchor='end' font-size='13' fill='#22221f'>{names[row['scenario']]}</text>"
                   f"<rect x='{left}' y='{y}' width='{length:.1f}' height='{bar}' rx='3' fill='{colour}'/>"
                   f"<text x='{left + length + 8:.1f}' y='{y + 18}' font-size='13' font-weight='600' fill='#22221f'>"
                   f"{row['seconds']:.1f} s</text>")
    return "".join(out) + "</svg>"


def incremental_section() -> str:
    rows = [json.loads(line) for line in (INCREMENTAL / "ur5e-1500-timings.jsonl").read_text("utf-8").splitlines() if line.strip()]
    by = {row["scenario"]: row for row in rows if "scenario" in row}  # the first line names the traj_compare it timed
    demo = (INCREMENTAL / "demo-staging.txt").read_text("utf-8")

    def phases(name: str) -> str:
        return " · ".join(f"{phase} {seconds:.1f} s" for phase, seconds in by[name]["phases"].items())

    return (
        "<div class='gap'><h3>Follow-up 2 · Incremental rebuilds: an unchanged run is reused (NAVIGATION.md Part D)</h3>"
        "<p><b>Was:</b> every write re-analysed and rewrote every run. Adding 818 runs to the bench's 5,750-run UR5e site cost "
        "all 5,750; Zach waited about 6 min and hit Ctrl-C. In the bench's profile, about 35 ms per run was identical work "
        "(the time-offset estimate, the TCP compare, compressing the .npz files).</p>"
        "<p><b>Now:</b>"
        "<ul><li>Each run gets a digest of everything that decides its files and analysis: its data, its options, and the code "
        "that analyses it. A run whose digest matches is reused: its folder is not touched, so a drill-down built earlier stays, and "
        "its numbers come from <code>runs/&lt;slug&gt;/analysis.json</code>.</li>"
        "<li>A target whose runs all match is reused too (<code>targets/&lt;slug&gt;.cache.json</code>), so a rebuild where nothing "
        "changed runs no compare and no forward kinematics at all.</li>"
        "<li>Every file is written under a <code>.tmp</code> name and renamed into place. A hard-linked copy of a live site "
        "(<code>cp -al</code>) can therefore be rebuilt while live is served, and a stopped write never leaves a torn file.</li>"
        "<li><code>progress(phase, done, total)</code> reports runs, reused, targets and index.</li></ul></p>"
        "<p class='api'><code>write_dataset_report(..., reuse=True, progress=fn)</code> · <code>reuse=False</code> rewrites every run</p>"
        "<h3>Timed on the bench's real UR5e runs</h3>"
        f"<p>The first {by['fresh']['runs']:,} of its runs, its own options (50 Hz, parquet rows, its MuJoCo poses), CPUs 2-5, 16, 17 "
        "on a host at load 30, through the bench's own loader: <code>docs/incremental_2026-11-20/bench_ur5e.py</code>.</p>"
        + _timings_svg(rows)
        + "<div class='scroll'><table><tr><th>Write</th><th>Runs</th><th>Reused</th><th>Seconds</th><th>By phase</th></tr>"
        + "".join(
            f"<tr><td>{label}</td><td class='num'>{by[name]['runs']:,}</td><td class='num'>{by[name]['reused']:,}</td>"
            f"<td class='num'><b>{by[name]['seconds']:.1f}</b></td><td>{phases(name)}</td></tr>"
            for name, label in (("fresh", "Fresh, reuse=False"), ("added", "+225 runs (15 %)"), ("unchanged", "Nothing changed"))
        )
        + "</table></div>"
        + f"<p>The incremental site's index payload equals the fresh one's: <b>{str(by['compare']['index_payload_equal']).lower()}</b>. "
        "Scaled to the bench's 5,750 runs + 818, adding takes about 60 s instead of about 5 min (an extrapolation, not a measurement; "
        "see Left). A rebuild with nothing changed costs about 3.5 ms per run, all phases included; 1.8 ms of that is "
        "digesting the run's data and reading its cache.</p>"
        "<h3>The bench's staging rebuild, checked</h3>"
        "<p>On the Part D test fixture: build live, hard-link it to staging, rebuild staging with one run changed and one added, then "
        "compare every live file's inode, mtime and bytes with before.</p>"
        f"<pre>{html.escape(demo)}</pre>"
        "<p class='note'>Pinned by 36 acceptance tests written before the implementation (<code>tests/test_incremental_writes.py</code>, "
        "checksums verified at merge): a reused write equals a fresh one, each digest ingredient rewrites exactly its run, target "
        "reuse, reuse preconditions, the hard-linked copy (with a Rerun recording), stopped writes and the progress sequences. Full "
        "suite: 526 passed; the one failure is the load-sensitive playback test, which also fails on the old code.</p>"
        + commit("bfbcba2 contract", "5c03d28 tests", "34411a4 _files", "14662f6 dataset", "0d59e28 docs", "a70ac47 old pin")
        + "</div>"
    )


def build() -> Path:
    copy_sources()
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>traj_compare at bench scale</title><style>{STYLE}</style></head><body><main>{body()}</main>"
            f"<script>{SCRIPT}</script></body></html>")  # fmt: skip
    size = len(page.encode("utf-8"))
    if size > MAX_BYTES:
        raise SystemExit(f"{size / 1e6:.2f} MB is over the {MAX_BYTES / 1e6:.1f} MB the desktop preview opens; shrink the media")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT}  {OUT.stat().st_size / 1e6:.2f} MB")
    return OUT


if __name__ == "__main__":
    build()
