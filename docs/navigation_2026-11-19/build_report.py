"""Build the 2026-11-19 navigation review report: Dataset → Target → Run, and one tabbed run view for HTML and Rerun.

One self-contained HTML page (media inlined, so it opens on any device), written to the main checkout's
reports/media. Same look as the previous round (``../layout_proposals_2026-11-19/build_report.py``, whose STYLE it
imports). WHY every still is cropped and re-encoded as WebP and the clip as H.264 at 900 px: the desktop preview
dies above ~1.9 MB on disk, and this page carries a hero clip and ~20 screenshots; ``build()`` refuses a bigger page.

Media come from ``record_hero.py`` (the hero clip), ``shoot_html.py`` + ``shoot_3dof.py`` (HTML run view),
``rerun/build_rerun_tabs.py`` + ``rerun/build_rerun_3dof.py`` with ``../layout_proposals_2026-11-19/rerun/shoot_rerun.py``
(Rerun) and ``dataset_from_fixture.py --shots`` (dataset levels). The tab titles and headings are read from
``docs/NAVIGATION.md`` Part B; the full-suite line from the suite's output file when it is there.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/navigation_2026-11-19
    env -u VIRTUAL_ENV ../../.venv/bin/python build_report.py
"""

from __future__ import annotations

import base64
import html
import importlib.util
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
NAVIGATION = PACKAGE / "docs" / "NAVIGATION.md"
REPORTS = Path("/home/bam/bam_ws/reports/media")
MEDIA = REPORTS / "traj-compare-tabs-2026-11-19"
OUT = REPORTS / "traj-compare-navigation-2026-11-19.html"
PREVIOUS = REPORTS / "traj-compare-torque-2026-11-19.html"
FFMPEG = "/usr/bin/ffmpeg"
MAX_BYTES = 1_900_000  # the desktop preview's ceiling for a page with media

HEAD = "7a60b4ae6"
COMMITS = [
    ("3362cda26", "contract"),
    ("d4463c6ac", "tab model + tests"),
    ("b47a022a1", "dataset tests"),
    ("49ec654e0", "HTML tabs"),
    ("02531019a", "dataset levels"),
    ("6b29be64c", "Rerun tabs"),
    ("7a60b4ae6", "README"),
]
SUITE_OUTPUT = Path("/tmp/claude-1000/-home-bam-zach-brain/b331c896-01c1-4684-837b-e19d9e0e6e2f/tasks/byx5mgrsb.output")
# What that file said when it finished (2026-11-19 11:57); used only once /tmp has been cleared.
SUITE_RECORDED = "1 failed, 314 passed, 1 warning in 79.82s (0:01:19)"
OLD_TITLES = {
    "track": "Is it good?",
    "where": "Where?",
    "joints": "Which joint?",
    "timing": "Timing or shape?",
    "torque": "Feedforward or feedback?",
    "signals": "Signals",
}


def _previous_round():
    """The previous round's builder, loaded under its own name (this file is also called build_report.py)."""

    path = HERE.parent / "layout_proposals_2026-11-19" / "build_report.py"
    spec = importlib.util.spec_from_file_location("previous_round_build_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STYLE = _previous_round().STYLE + """
.badge{display:inline-block;background:#fff4e0;color:#8a5a00;border:1px solid #f0d49a;border-radius:12px;padding:2px 10px;font-size:13px;font-weight:600;margin:10px 0 2px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.grid3 figure,.grid4 figure,.grid2 figure{margin:0}.grid4 figure{padding:4px}.grid4 figcaption{font-size:12px}
figure img{cursor:zoom-in}figure.big{grid-column:1/-1}figure.big img{cursor:zoom-out}
.ask{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:16px 0}
.ask blockquote{margin:0 0 8px;padding:2px 12px;border-left:3px solid var(--accent);color:var(--muted);font-style:italic}
.ask .built{margin:0 0 6px}.ask figure{margin:10px 0 0}.ask .grid2,.ask .grid3{margin-top:10px}
.lane{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin:16px 0 6px}
.cmd{margin:4px 0 2px;white-space:pre-wrap;word-break:break-all}p code,li code,td code{overflow-wrap:anywhere}.note{color:var(--muted);font-size:13px}
.narrow{max-width:780px}
@media (max-width:800px){.grid3,.grid4{grid-template-columns:1fr}}
"""

SCRIPT = """
document.addEventListener('click', function (event) {
  var img = event.target.closest('figure img');
  if (img) img.closest('figure').classList.toggle('big');
});
"""


def _ffmpeg(*args: str) -> bytes:
    command = ["taskset", "-c", "2-5,16,17", "nice", "-n", "19", FFMPEG, "-v", "error", *args]
    return subprocess.run(command, capture_output=True, check=True).stdout


def still(path: Path, width: int, crop: tuple[int, int, int, int] | None = None, quality: int = 75) -> str:
    """A PNG screenshot as a WebP data URI: ``crop`` = (x, y, w, h) in source pixels, then scaled to ``width``."""

    filters = ([f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}"] if crop else []) + [f"scale='min({width},iw)':-2:flags=lanczos"]
    # WHY a file, not stdout: on a pipe ffmpeg's webp muxer cannot seek back, and an image over ~32 kB keeps a RIFF
    # size of 0, which Chrome refuses to decode (measured 2026-11-19: 8 of 22 stills blank).
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "still.webp"
        _ffmpeg("-i", str(path), "-vf", ",".join(filters), "-c:v", "libwebp", "-quality", str(quality),
                "-compression_level", "6", "-y", str(target))  # fmt: skip
        data = target.read_bytes()
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise SystemExit(f"bad WebP header for {path}")
    return "data:image/webp;base64," + base64.b64encode(data).decode()


def clip(path: Path) -> str:
    return "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()


def fig(path: Path, caption: str, width: int = 1000, crop: tuple[int, int, int, int] | None = None) -> str:
    if not path.is_file():
        return f'<figure class="missing"><div>missing: {html.escape(str(path))}</div><figcaption>{caption}</figcaption></figure>'
    return f'<figure><img src="{still(path, width, crop)}" alt=""><figcaption>{caption}</figcaption></figure>'


def video(path: Path, caption: str) -> str:
    if not path.is_file():
        return f'<figure class="missing"><div>missing: {html.escape(str(path))}</div><figcaption>{caption}</figcaption></figure>'
    return (f'<figure><video id="hero" src="{clip(path)}" autoplay muted loop playsinline controls></video>'
            f"<figcaption>{caption}</figcaption></figure>")  # fmt: skip


def tab_rows() -> list[tuple[str, str, str]]:
    """(id, exact title, exact heading) per question tab, from NAVIGATION.md Part B's table."""

    rows = re.findall(r"^\| `(\w+)` \| \*\*(.+?)\*\* \| (.+?) \|", NAVIGATION.read_text("utf-8"), flags=re.MULTILINE)
    if [row[0] for row in rows] != list(OLD_TITLES):
        raise SystemExit(f"NAVIGATION.md Part B's tabs changed: {[row[0] for row in rows]}")
    return rows


def suite_line() -> tuple[str, bool]:
    """The full suite's pytest summary line, and whether the suite has finished."""

    if not SUITE_OUTPUT.is_file():
        return SUITE_RECORDED, True
    lines = [line.strip() for line in SUITE_OUTPUT.read_text("utf-8", errors="replace").splitlines()]
    summary = [line for line in lines if re.search(r"\d+ (passed|failed)", line) and " in " in line]
    return (summary[-1], True) if summary else ("running at build time", False)


def body() -> str:
    esc = html.escape
    html_dir, dataset, rerun = MEDIA / "html", MEDIA / "dataset", MEDIA / "rerun" / "shots"
    # Crops in source pixels (1440×900 screenshots): the run view's tab panel without the stage, and Rerun's
    # tab area without the 3D view; both read in a four-across strip and open full width on a click.
    html_panel, rerun_panel = (440, 120, 1000, 780), (410, 36, 1030, 834)
    suite, finished = suite_line()
    tabs = tab_rows()
    rel_previous = PREVIOUS.relative_to(OUT.parent).as_posix()
    rel_site = (MEDIA / "dataset" / "site" / "index.html").relative_to(OUT.parent).as_posix()
    serve = ("env -u VIRTUAL_ENV /home/bam/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/.venv/bin/python "
             "-m traj_compare.serve /home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/dataset/site --port 8768")  # fmt: skip
    rerun_cmd = "uvx --from rerun-sdk==0.40.0 rerun /home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/rerun/bimanual.rrd"

    parts = [
        "<div class='kicker'>traj_compare · 2026-11-19 · second round · Claude Code (Opus 5.5)</div>",
        "<h1>traj_compare, organised around the target: Dataset → Target → Run, and one tabbed run view for HTML and Rerun</h1>",
        "<p class='verdict'><b>Your feedback is built and landed on bam_ws <code>main</code> (local, @ "
        f"<code>{HEAD}</code>):</b> the dataset view is three levels around the target trajectory, and the HTML run view and "
        "Rerun share one set of six question tabs that scale from 1 to 46 joints. All data shown is simulated test fixtures.</p>",
        "<span class='badge'>SIMULATED DATA · test fixtures, not rig data</span>",
        video(MEDIA / "hero" / "hero-dataset-target-run.mp4",
              "The real dataset site, served by <code>traj_compare.serve</code>, 17 s: Dataset cards with the summary band on top → "
              "Table → Cards → <b>Open target</b> “Full-circle probe · slow” → <b>Lines up to N</b> 5 → 8 (both configs' fans "
              "turn into lines) → back to 5 → the history tab → a line's ↗, whose run report the server built on that click "
              "(it did not exist before) → its question tabs. The grey dot is the mouse. This fixture has no robot model, so "
              "its run report has no 3D stage; the scaling fixtures below do."),
        f"<p class='note'>Follows <a href='{rel_previous}'>the previous round</a> (torque breakdown + fifteen layout proposals); "
        "your feedback on those layouts is what this round builds.</p>",
        # ── 1 · asks ─────────────────────────────────────────────────────────────────────────────────────────────
        "<h2>1 · What you asked → what's built</h2>",
        "<div class='ask'><blockquote>“a super top level view which provides summary across the entire dataset”</blockquote>"
        "<p class='built'>→ The <b>summary band</b> at the top of <code>index.html</code>: targets, lines (sim / real), configs, "
        "dates; per config the median RMS error, and “better than v1 nominal on 2 of 2 targets”.</p>"
        + fig(dataset / "1-dataset-cards.png", "Dataset level, top: the band answers “How is tracking across every target, per config?”",
              1100, (0, 0, 1440, 395))
        + "</div>",
        "<div class='ask'><blockquote>“sort by target trajectories (can show as table or cards)”</blockquote>"
        "<p class='built'>→ A <b>Cards ⇄ Table ⇄ Runs</b> switch under the band, remembered per browser. Runs is today's table: "
        "nothing was removed.</p>"
        + fig(dataset / "1-dataset-cards.png", "<b>Cards</b> (default): per target the verdict, the error chart per config, a dot per line, Open target.", 1100, (0, 400, 1440, 500))
        + "<div class='grid2'>"
        + fig(dataset / "2-dataset-table.png", "<b>Table</b>: one row per target × config, median, Δ vs baseline, ISO 9283 RT, sparkline; a row expands to its lines.", 960, (0, 400, 1440, 500))
        + fig(dataset / "3-dataset-runs.png", "<b>Runs</b>: today's runs × pairs table, unchanged.", 960, (0, 400, 1440, 500))
        + "</div><p class='note'>Click any picture to open it full width.</p></div>",
        "<div class='ask'><blockquote>“drill into a particular target trajectory … all of the runs … sort by date, configuration "
        "type, sim/real”</blockquote>"
        "<p class='built'>→ <code>#/target/&lt;slug&gt;</code>: the Scalars-board <b>line list</b> on the left: regex filter, "
        "chips per config / date / kind, <b>Group by</b> config / date / sim-real with select-all per group, a ↗ per line to its "
        "run report; the edge drags and the list folds.</p><div class='grid3 narrow'>"
        + fig(dataset / "4-target-repeat.png", "Group by <b>config</b>", 330, (0, 40, 325, 860))
        + fig(dataset / "6-run-list-by-date.png", "Group by <b>date</b>", 330, (0, 40, 325, 860))
        + fig(dataset / "6-run-list-by-kind.png", "Group by <b>sim / real</b>", 330, (0, 40, 325, 860))
        + "</div></div>",
        "<div class='ask'><blockquote>“I like the control over how the lines are showing”</blockquote>"
        "<p class='built'>→ <b>Repeats</b> Auto / Lines / Bands, <b>lines up to N</b>, smoothing. In Auto a config draws its lines "
        "while it has ≤ N, then a percentile fan (median · IQR · p5–p95 · min–max) of its <b>real</b> lines; sim lines draw "
        "dashed over it and are never pooled into the fan. Each chart says what it draws per config.</p>"
        + fig(dataset / "4-target-repeat.png", "N = 6: v1 nominal's 8 real lines draw as a fan, v2 calibrated's 6 as lines; the sim is dashed. "
              "The black line is the hovered run (real-03).", 1000, (330, 180, 1110, 510))
        + "</div>",
        "<div class='ask'><blockquote>“the time view … is more helpful for comparing … different robot configurations … improved "
        "in tracking over time”</blockquote>"
        "<p class='built'>→ Its own tab on the target: <b>Has tracking improved across configs over time?</b> A control chart "
        "per config phase (mean and I-MR limits), one point per real line in date order; a point opens its run.</p>"
        + fig(dataset / "5-target-history.png", "v2 calibrated (latest) against v1 nominal (first): mean RMS error 0.88° → 0.44°, −51 %.",
              1000, (330, 240, 1110, 410))
        + "</div>",
        "<div class='ask'><blockquote>“designing a different run viewer for standalone and rerun is a bit silly … we need to do "
        "the tabbed model”</blockquote>"
        "<p class='built'>→ One tab model, <code>traj_compare.tabs</code>: the same titles, headings and drop rule (a tab with "
        "nothing to show is dropped) in both viewers.</p>"
        + fig(html_dir / "6dof-track.png", "<b>HTML</b> run view, 6-joint fixture, first tab: the stage on the left, the six question tabs on the right.", 1100, (0, 120, 1440, 500))
        + fig(rerun / "6dof--w1440-track.png", "<b>Rerun</b> 0.40.0, the same fixture in the <code>questions</code> layout: the same stage, the same six titles.", 1100, (0, 0, 1440, 640))
        + "</div>",
        "<div class='ask'><blockquote>“Do we always want the 3D thing showing … basically always”</blockquote>"
        "<p class='built'>→ The 3D is pinned in a <b>stage</b> beside the tabs in both viewers. HTML: drag its edge, or fold it "
        "with ‹ to get the full width back (above, open; here, folded). Rerun: as before.</p>"
        + fig(html_dir / "6dof-joints-stage-folded.png", "Stage folded to a “3D view” rail: the tab panel widens from 1083 to 1348 px.",
              1000, (0, 120, 1440, 370))
        + "</div>",
        "<div class='ask'><blockquote>“make sure these header titles are super descriptive … Where is the error? is better”</blockquote>"
        "<p class='built'>→ Every tab title is a full question and every tab opens with a full-sentence heading (from "
        "<code>docs/NAVIGATION.md</code> Part B, the same in both viewers):</p>"
        "<table><tr><th>Before</th><th>Tab title now</th><th>Heading inside the tab</th></tr>"
        + "".join(f"<tr><td>{esc(OLD_TITLES[tab_id])}</td><td><b>{esc(title)}</b>{' <span class=note>(kept)</span>' if OLD_TITLES[tab_id] == title else ''}</td>"
                  f"<td>{esc(heading)}</td></tr>" for tab_id, title, heading in tabs)
        + "</table><p>And every plot title names its signal, joint, sign and unit: <code>shoulder: joint error, target − run [°]</code>, "
        "never <code>shoulder [°]</code>.</p></div>",
        "<div class='ask'><blockquote>“how does it look like for a 1 dof robot 3 dof robot 6 dof robot n dof … split the arm and the "
        "hand … each arm separately … hand … group by finger”</blockquote>"
        "<p class='built'>→ The next section.</p></div>",
        # ── 2 · scaling ──────────────────────────────────────────────────────────────────────────────────────────
        "<h2>2 · How it scales: 1 → 3 → 6 → 46 joints</h2>",
        "<ul>"
        "<li><b>Ranking first</b> (≥ 2 joints): one bar per joint across every part, worst first, labelled "
        "<code>&lt;part&gt; · &lt;joint&gt;</code>: RMS joint error of the worst run (°) on <i>Which joint has the error?</i>, "
        "FB share (%) on <i>Feedforward or feedback?</i>. A click on a bar opens that joint's part and scrolls to its plot.</li>"
        "<li><b>Part selector</b> <code>Left hand · 16 joints</code> when there are ≥ 2 parts: buttons in HTML, nested tabs in "
        "Rerun, same labels.</li>"
        "<li><b>Inside a part</b>: an arm is one row per joint; a hand is one row per finger, that finger's joints as columns.</li>"
        "<li><b>One joint</b>: no <i>Which joint has the error?</i> tab (nothing to rank); its error lives in the first tab.</li>"
        "</ul>"
        "<p>Parts are <b>declared</b>, never inferred from joint names. No <code>parts</code> → one part, “All joints”, no selector; "
        "a joint the declaration doesn't name falls into “Other joints”; an unknown or repeated joint is a <code>ValueError</code>.</p>"
        "<pre>Comparison(..., parts={\"Left arm\": [\"l_shoulder_pitch\", ..., \"l_wrist_roll\"],          # 7 joints\n"
        "                       \"Right arm\": [\"r_shoulder_pitch\", ..., \"r_wrist_roll\"],\n"
        "                       \"Left hand\": {\"thumb\": [\"l_thumb_rot\", \"l_thumb_mcp\", ...], \"index\": [...], ...},  # by finger\n"
        "                       \"Right hand\": {...}})</pre>",
        "<div class='lane'>HTML run view · Which joint has the error?</div><div class='grid4'>",
        fig(html_dir / "1dof-track.png", "<b>1 joint</b>: no <i>Which joint</i> tab; the first tab holds its error.", 900, html_panel),
        fig(html_dir / "3dof-joints.png", "<b>3 joints</b>: 3 bars, 3 rows, no part selector.", 900, html_panel),
        fig(html_dir / "6dof-joints.png", "<b>6 joints</b>: 6 bars, 6 rows.", 900, html_panel),
        fig(html_dir / "46-joints-left-hand.png", "<b>46 joints</b>: 46 bars across 4 parts, then <i>Left hand · 16 joints</i>: one row per finger.", 900, html_panel),
        "</div><div class='lane'>Rerun · the same tabs</div><div class='grid4'>",
        fig(rerun / "1dof--w1440-track.png", "<b>1 joint</b>: five tabs, no <i>Which joint</i>.", 900, rerun_panel),
        fig(MEDIA / "rerun" / "3dof" / "shots" / "3dof--w1440-joints.png", "<b>3 joints</b>: ranking of 3, one view per joint.", 900, rerun_panel),
        fig(rerun / "6dof--w1440-joints.png", "<b>6 joints</b>: ranking of 6.", 900, rerun_panel),
        fig(rerun / "bimanual--w1440-joints-part2.png", "<b>46 joints</b>: ranking of all 46, nested part tabs, Left hand by finger.", 900, rerun_panel),
        "</div><div class='lane'>A hand's torque tab · Feedforward or feedback?</div><div class='grid2'>",
        fig(html_dir / "46-torque-left-hand.png", "HTML, Left hand, scrolled to the index finger: one card per joint × run, feedback orange.", 860),
        fig(rerun / "bimanual--w1440-torque-part2.png", "Rerun, Left hand: one row per finger, FB share and worst run in every view title.", 860, rerun_panel),
        "</div>",
        # ── 3 · proof ────────────────────────────────────────────────────────────────────────────────────────────
        "<h2>3 · Proof</h2>",
        "<p>The acceptance tests were written first by agents that did not build the UI, committed before any UI work, checksummed, "
        "and left untouched by the builders: <b>7 / 7 checksums match</b>.</p>"
        "<table><tr><th>Tests</th><th>Count</th></tr>"
        "<tr><td>new: <code>test_run_tabs.py</code> · <code>test_run_tabs_html.py</code> · <code>test_rerun_tabs.py</code> · "
        "<code>test_dataset_levels.py</code></td><td>69 · 17 · 37 · 26</td></tr>"
        "<tr><td>existing: HTML run view · Rerun · dataset / serve / data_ui</td><td>57 · 6 files green · 47</td></tr>"
        + (f"<tr><td>full suite</td><td><code>{esc(suite)}</code></td></tr></table>" if finished
           else "<tr><td>full suite</td><td>running at build time</td></tr></table>")
        + ("<p>The one failure is <code>tests/test_playback.py::test_play_from_a_fresh_page_never_freezes_and_stays_on_the_cursor</code>. "
           "On the pre-change commit <code>670366292</code> the same test failed 2 of 3 runs, so it's a pre-existing flake on this "
           "host, not this change.</p>" if finished and "failed" in suite else ""),
        "<p><b>Measured in the browser:</b></p><ul>"
        "<li>Stage 419 px by default; a −120 px drag → 299 px; folding widens the tab panel 1083 → 1348 px.</li>"
        "<li>Ranking bars: 6 (6 joints), 46 (46 joints), 0 (1 joint).</li>"
        "<li>Charts re-size on a tab switch: 0 stale after, against 6 / 6 before.</li>"
        "<li>No horizontal scroll at 1440, 860 or 390 px wide.</li>"
        "<li>Rerun's six tab titles read in full at 1440 px (stage narrowed 2:3 → 2:5) and at 1920 px.</li>"
        "<li>Hero clip: the ↗ click made the server build <code>runs/full-circle-slow-real-01/report.html</code> on that request.</li></ul>"
        "<p><b>Commits on bam_ws <code>main</code></b> (local): "
        + " · ".join(f"<code>{sha}</code> {esc(what)}" for sha, what in COMMITS) + "</p>",
        # ── 4 · decided ──────────────────────────────────────────────────────────────────────────────────────────
        "<h2>4 · Decided for you</h2><ul>"
        "<li>Dataset home = the summary band and the targets on one page, not two levels of pages: one less click, and the band is "
        "short. Undo: <code>git revert 02531019a</code>.</li>"
        "<li>A sim line takes its run's config but is never pooled into that config's fan: it draws dashed over it (repeatability "
        "means same everything, run again).</li>"
        "<li>HTML 3D pinned in a stage beside the tabs, as Rerun does; fold it with ‹ to get the old full width back.</li>"
        "<li>Rerun stage narrowed from 2:3 to 2:5 so all six tab titles read at 1440 px.</li>"
        "<li><i>Feedforward or feedback?</i> kept (you didn't flag it); every other title rewritten as a full question, each tab "
        "opening with a full-sentence heading.</li>"
        "<li>Arm / hand membership is declared (<code>Comparison.parts</code>), never guessed from joint names; with none it's one "
        "part, “All joints”.</li>"
        "<li>Old Rerun tab names still open tabs (<code>layout_blueprint(tab=\"Which joint?\")</code>), so existing callers keep working.</li>"
        "<li>In Rerun's torque tab an arm's legend sits on its first row only (it covered half of every plot).</li>"
        f"<li><b>Undo everything:</b> <code>git revert 3362cda26^..{HEAD}</code>.</li></ul>",
        # ── 5 · left ─────────────────────────────────────────────────────────────────────────────────────────────
        "<h2>5 · Left</h2><ul>"
        "<li>The target page has no feedback-torque / FB-share charts yet: the production <code>Run</code> has no torque fields "
        "(adding them touches the run files, the manifest and the drill-down). Same root as the rig gap from the previous round: "
        "<code>bam_rack_twin/hardware/board.py</code> doesn't log <code>control_torque</code>.</li>"
        "<li>data-ui: the targets table ⇄ cards in data-ui's own views (<code>targets.json</code> + <code>views.base</code>) is not "
        "done; it needs a schema in data-ui. The switch exists in the static page.</li>"
        "<li>One tool frame per arm: the model has one <code>tcp_frame</code>, so <i>Where is the error?</i> and <i>Is it late or "
        "off the path?</i> follow one tool on a bimanual robot.</li>"
        "<li>The HTML 46-joint ranking lists all 46 joints before the part selector; a “top 10 + show all” fold would be calmer.</li>"
        "<li>Rerun: a seventh tab (e.g. a check tab) scrolls the tab strip at 1440 px; finger-row titles get cut in narrow views "
        "(a Rerun view-title limit).</li>"
        "<li><code>test_playback</code> is flaky on this host before and after this change (one frame off the cursor, limit 2).</li>"
        "<li>Not pushed: bam_ws <code>main</code> is local, 24 commits ahead of <code>origin/main</code> and 1,373 behind (as in "
        "the previous round).</li></ul>",
        # ── 6 · open it ──────────────────────────────────────────────────────────────────────────────────────────
        "<h2>6 · Open it</h2>",
        "<p><b>The dataset site, served</b> (run reports are built the first time you open them):</p>",
        f"<pre class='cmd'>{esc(serve)}</pre>",
        "<p class='note'>It prints <code>serving /home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/dataset/site on "
        "http://127.0.0.1:8768/</code>; open <code>http://127.0.0.1:8768/</code>. Without <code>--port</code> it takes 8767, which "
        "another session's server holds on this host right now. Ctrl-C stops it.</p>",
        "<p><b>Rerun, the 46-joint recording</b> in the <code>questions</code> layout (1-, 6-joint recordings beside it, the "
        "3-joint one in <code>rerun/3dof/</code>):</p>",
        f"<pre class='cmd'>{esc(rerun_cmd)}</pre>",
        f"<p class='note'>Without a server: <a href='{rel_site}'>the dataset page</a> opens from file (run reports then need the "
        "server above).</p>",
    ]
    return "\n".join(parts)


def build() -> Path:
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>traj_compare navigation</title><style>{STYLE}</style></head><body><main>{body()}</main>"
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
