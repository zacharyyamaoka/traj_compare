"""The words of the 2026-11-19 report (build_report.py renders them). Verdict first, then the evidence, then the decisions."""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMIT = "0ca81c414"

TORQUES = [
    ("Target", "target.tau", "the torque the reference needs (inverse dynamics of the target, planning model)", "planner · tau_pred"),
    ("Commanded", "tau_cmd", "what the controller asks the FOC current loop for at that instant", "moteus reply control_torque"),
    ("Feedforward", "tau_ff", "the model-based part of the command, sent by the host", "cmd feedforward_torque"),
    ("Feedback", "tau_fb", "the correcting part: kp·e + kd·ė + ki∫e", "control_torque − feedforward_torque"),
    ("Applied", "tau", "the torque actually delivered", "moteus reply torque (q-axis current × kt)"),
]

ROUNDS = [
    ("summary", "Standalone summary view — every target, every run",
     "What one page says about 30 runs over 3 targets: which feedforward is better, how repeatable, where the torque goes."),
    ("run", "Standalone run view — one target and its 15 runs",
     "How one target's runs read: the five torques, repeats as bands, the bad moment."),
    ("rerun", "Rerun run view — the same target in stock Rerun 0.40.0",
     "Real Rerun web viewer screenshots; each .rrd opens with its layout embedded."),
]


def _spec(round_name: str, media: Path) -> dict:
    return json.loads((media / round_name / "gallery-spec.json").read_text())


def _hero(round_name: str, variant: dict, media: Path) -> Path:
    shots = media / round_name / "shots"
    for pattern in (f"{variant['id']}-hero.png", f"*{variant['id'][1:]}*--hero.png", f"q{variant['id'][1:]}-*--hero.png"):
        found = sorted(shots.glob(pattern))
        if found:
            return found[0]
    return shots / f"{variant['id']}-hero.png"


def body(figure, prune_table, media: Path) -> str:
    esc = html.escape
    torque = media / "torque"
    parts = [
        "<div class='kicker'>traj_compare · 2026-11-19 · Claude Code (Opus 5.5)</div>",
        "<h1>The torque breakdown is first class, from the dataset down to one run</h1>",
        "<p class='verdict'><b>Both viewers now show target, commanded, feedforward, feedback and applied torque as first-class "
        f"data</b> — on bam_ws <code>main</code> @ <code>{COMMIT}</code> (local; this checkout's main is not pushed). "
        "<b>On the real rigs only target, feedforward and applied exist today:</b> the logger never queries moteus "
        "<code>control_torque</code>, so commanded and feedback show in sim only until that one register is logged.</p>",
        "<ul>"
        "<li><b>HTML run view:</b> a new <i>Torque breakdown</i> section (on by default): a Torque budget table — feedback share, "
        "RMS of each torque, target − commanded, the drive gap — then one card per joint × run with the five traces.</li>"
        "<li><b>Rerun:</b> <code>/torque/&lt;joint&gt;/…</code> entities, feedback-share bars, and a torque tab in both layouts "
        "(<i>Feedforward or feedback?</i> / <i>Torque</i>).</li>"
        "<li><b>Layouts:</b> five each for the summary view, the run view and the Rerun run view, on one shared simulated fixture, "
        "scored against criteria written before any was built. You picked from the galleries (daily note, "
        "<i>Traj compare view feedback</i>): target-first navigation and one set of question tabs for HTML and Rerun — "
        "built by the navigation round (section 3).</li>"
        "<li><b>Dataset view:</b> now carries the torque breakdown too — feedback share and drive gap per config on the "
        "dataset and league table, feedback-torque and FB-share fans on each target (bam_ws <code>main</code> @ <code>2ab8c8782</code>).</li>"
        "</ul>",
        "<h2>1 · The torque breakdown (shipped)</h2>",
        figure(torque / "hero-torque-breakdown.mp4",
               "The real report on the shared fixture (full-circle probe, slow, 15 runs). The component chips switch feedforward and "
               "applied off and back on every card at once; the cursor is shared by every plot. 12 s, recorded from the running page.",
               kind="video"),
        "<table><tr><th>Torque</th><th>Field</th><th>What it is</th><th>moteus source</th></tr>"
        + "".join(f"<tr><td><b>{esc(a)}</b></td><td><code>{esc(b)}</code></td><td>{esc(c)}</td><td>{esc(d)}</td></tr>" for a, b, c, d in TORQUES)
        + "</table>"
        "<p>Two of commanded / feedforward / feedback derive the third (<code>commanded = feedforward + feedback</code>), and the card "
        "says <i>derived</i>. All three given are kept as given, because a drive clamp breaks the sum and the page must not hide it. "
        "<b>Feedback share</b> = Σ|feedback| / (Σ|feedforward| + Σ|feedback|): the part of the command the feedback had to supply.</p>",
        figure(torque / "shots" / "fixture-torque.png",
               "The section on the fixture: the Torque budget table (FB share 22–25 % on every ff v1 run, 3–9 % on ff v2), then the cards — "
               "target dashed grey, commanded thick in the run colour, feedforward blue, feedback orange filled to zero, applied thin. "
               "Measured in the browser: 30 cards, none overlapping, 0 console errors."),
        "<div class='grid2'>",
        figure(torque / "shots" / "prod-questions--0.png",
               "Rerun, <i>questions</i> layout → <b>Feedforward or feedback?</b> tab: the worst run's breakdown per joint, every run's "
               "feedback, feedback-share bars. Stock 0.40.0 web viewer.", width=1000),
        figure(torque / "shots" / "prod-evo--0.png",
               "Rerun, <i>evo</i> layout → <b>Torque</b> tab, same views full width. Known Rerun limits: bar charts only take numeric "
               "x labels, and 'every run' feedback is one orange, so v1 and v2 read as two clusters.", width=1000),
        "</div>",
        "<h3>On real data: CAN 11 pendulum, round 9, five repeats at speed f0.6</h3>",
        figure(torque / "shots" / "real-torque.png",
               "REAL hardware (2026-11-17). Feedforward (blue) is the host model torque; applied is the moteus reply torque. The gap "
               "between them during each acceleration is what the feedback supplied — but without <code>control_torque</code> it can "
               "only be eyeballed, not split out. The budget table drops the empty columns and says commanded and feedback were not "
               "recorded."),
        "<p><b>The gap, and the fix:</b> <code>bam_rack_twin/hardware/board.py</code> saves <code>tau</code>, <code>ff_model_nm</code>, "
        "<code>q_control</code> and <code>qd_control</code> (the last two are 100 % NaN), but never queries moteus's <code>control_torque</code>. "
        "Querying that one register and saving it as <code>tau_cmd</code> makes feedback = commanded − feedforward fall out on every "
        "future run, and this page will draw it with no further change. Nothing on disk today has it (searched the 1-DOF, five-bar "
        "and bus-tap data).</p>",
        "<h2>2 · Layouts — fifteen proposals in three rounds</h2>",
        "<p>All fifteen use one shared fixture (<code>fixture.py</code>, SIMULATED: a vertical 2R arm, three targets, 27 real repeats "
        "and 3 sims, feedforward v1 that underestimates gravity by about 20 % against a calibrated v2), so no layout wins on easier data. "
        "The criteria, weights and five directions per round were written down before anything was built "
        "(<code>docs/layout_proposals_2026-11-19/CRITERIA.md</code>); the builders did not score their own work. Each gallery has "
        "the live pages, walkthroughs, a split/compare view and a box for your pick or splice.</p>",
    ]
    for round_name, title, blurb in ROUNDS:
        spec = _spec(round_name, media)
        pick = next(v for v in spec["variants"] if v["id"] == spec["defaultId"])
        parts.append(f"<h3>{esc(title)}</h3><p>{esc(blurb)}</p><div class='grid5'>")
        for variant in spec["variants"]:
            parts.append(figure(_hero(round_name, variant, media),
                                f"<b>{esc(variant['id'].upper())} {esc(variant['name'])}</b> — {esc(variant['thesis'])}", width=480))
        parts.append("</div>")
        parts.append(f"<p>Gallery: <code>/home/bam/.local/bin/open {media / round_name / 'index.html'}</code></p>")
        parts.append(f"<details><summary>AI prune — pick {esc(pick['id'].upper())} {esc(pick['name'])}; scores, evidence, hinge</summary>"
                     f"{prune_table(media / round_name / 'gallery-spec.json')}</details>")
    parts += [
        "<h2>3 · After your pick (afternoon)</h2>",
        "<p>Your feedback on the galleries: organise around the target (Dataset › Target › Run, targets as cards or a table), "
        "one tabbed run view shared by HTML and Rerun with descriptive tab titles, and the 3D always showing. The navigation "
        "round built that and landed it (<code>3362cda26..e6c9c8390</code>, its own report: "
        "<code>/home/bam/.local/bin/open /home/bam/bam_ws/reports/media/traj-compare-navigation-2026-11-19.html</code>). "
        "The torque view lives there as the <b>Feedforward or feedback?</b> tab. Its handoff left one gap that was this task's: "
        "the dataset view couldn't carry the breakdown. That landed afterwards as <code>2ab8c8782</code> "
        "(22 acceptance tests written first by a separate agent; 110 dataset/torque tests green; browser-checked).</p>",
        "<div class='grid2'>",
        figure(media / "applied" / "dataset-torque" / "2-league-table.png",
               "Dataset level, League table: FB share and drive gap per target × config — full-circle slow 22 % (ff v1) vs 5.7 % (ff v2); "
               "the band above gives each config's median, 23 % vs 7.8 %.", width=1000),
        figure(media / "applied" / "dataset-torque" / "4-target-repeat-torque.png",
               "Target level, <i>How repeatable…</i> tab: feedback torque and FB share over the trajectory per joint, 8 ff v1 and 6 ff v2 "
               "real lines as fans (median · IQR · p5–p95 · min–max). The v1 feedback slopes with gravity; v2's stays near zero.", width=1000),
        "</div>",
        "<h2>4 · Decisions</h2>",
        "<h3>Done and proved</h3><ul>"
        "<li>Torque breakdown in the data model, payload, HTML run view, Parquet/MCAP and Rerun — 15 acceptance tests written first and "
        "untouched by the implementer (sha256 checked), 166/166 traj_compare tests pass.</li>"
        "<li>Browser-driven on the fixture and on real CAN 11 data (cards measured, chips toggled, 0 console errors); both Rerun torque "
        "tabs rendered in the stock 0.40.0 web viewer.</li>"
        "<li>Fifteen layout prototypes, each opened and exercised headlessly; three galleries pass <code>gallery.py check --strict</code>.</li>"
        "<li>The dataset view's torque breakdown (<code>2ab8c8782</code>): Run.torques persisted and read back into the run report; band, league and target charts measured in a browser.</li></ul>",
        "<h3>Decided for you</h3><ul>"
        f"<li>Landed the torque breakdown on bam_ws <code>main</code> ({COMMIT}). Undo: <code>git revert {COMMIT}</code>.</li>"
        "<li>Kept <code>tau</code> meaning <i>applied</i> on a run and <i>target</i> on the target, so every existing report renders "
        "unchanged; the new fields are additive.</li>"
        "<li>Budget table drops columns no run recorded and names the missing torques once, instead of a grid of dashes.</li>"
        "<li>Did not push: this checkout's <code>main</code> is 1373 commits behind <code>origin/main</code>, and nothing here pushes it.</li></ul>",
        "<h3>Left</h3><ul>"
        "<li>Log <code>control_torque</code> on the rigs (one register in <code>board.py</code>) — the only thing between the real data "
        "and a real feedback trace. Owned by the Sim to Real agent's hardware layer; proposed as its own task.</li>"
        "<li>The target page's <i>History</i> tab has no FB-share strip yet (NAVIGATION.md lists it).</li>"
        "<li>The budget table is one row per run × joint (30 rows at 14 repeats); the run-view proposals each fold it differently.</li></ul>",
        "<h3>Needs you</h3><ul><li>Nothing: your pick is built.</li></ul>",
        "<h3>Deliberately not done</h3><ul>"
        "<li>No audit (you didn't ask for one).</li>"
        "<li>Didn't change the rig logger myself: it changes what the live rig queries over CAN, and it belongs to another agent's "
        "hardware layer.</li>"
        "<li>Didn't ship the AI picks (Torque cockpit, a separate Rerun <i>Solo</i> layout): your feedback chose one shared tabbed view instead, and the navigation round built it.</li></ul>",
    ]
    return "\n".join(parts)
