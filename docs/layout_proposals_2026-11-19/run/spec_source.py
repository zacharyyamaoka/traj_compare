"""Writes run/gallery-spec.json (the babble gallery spec for Round B). Kept as Python so the long preview/media HTML
is generated from one table of shots instead of hand-escaped JSON.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    python3 run/spec_source.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

REQUIREMENTS = [
    ("b1", "Torque breakdown readable", 25,
     "Zach does not see the FF/FB split as first class today; it is the headline of this round (CONTRACT.md).",
     "For a joint and run: target, commanded, feedforward, feedback, applied; how much is feedback is evident.",
     ("five lines in a tangle", "readable with effort", "the split reads at a glance and at any instant")),
    ("b2", "Repeat distribution", 20,
     "real vs real × N: a few repeats as lines, many as median + percentile fans (TensorBoard histogram style).",
     "N repeats of the target as lines or percentile bands, automatic or switchable.",
     ("overplotted lines only", "bands for one channel", "bands everywhere, lines on demand, one run highlightable against the band")),
    ("b3", "Where / when", 20,
     "The bad moment has to be located in time and in the robot's pose, not just reported as an RMS.",
     "Error, torque and 3D share the time cursor and zoom, so the bad moment is located.",
     ("separate, unsynced", "synced cursor", "cursor + zoom + an explicit \"worst moment\" jump")),
    ("b4", "Runs on the left", 15,
     "\"Take a bit of the TensorBoard layout, with the runs on the left\"; runs grouped by target.",
     "TensorBoard-like run list: toggle, solo, group by tag.",
     ("chips only", "list with toggles", "list with groups, solo, colour key, tag filter")),
    ("b5", "Calm density", 10,
     "One calm answer first, detail on demand (Zach's UI rule); today's view opens on a wall of tables.",
     "Progressive disclosure, not a wall of 40 plots.",
     ("wall", "sections", "one calm answer, detail on demand")),
    ("b6", "Fits traj_compare", 10,
     "The winner has to land in the existing stack, not as a rewrite.",
     "Buildable in the existing stack (vanilla JS, uPlot, three.js, sections, transport).",
     ("rewrite", "partial reuse", "reuses sections + transport as-is")),
]
GATES = [
    ("g1", "Self-contained", "Standalone pages open from file:// with no server and no CDN (traj_compare's contract)."),
    ("g2", "Units", "Angles in degrees, tool in mm, torque in N·m; SI stays in the stored data."),
    ("g3", "Honest data", "Everything shown comes from the shared fixture; every page says SIMULATED."),
    ("g4", "Robot model", "A run view with 3D keeps the robot model available (skill contract)."),
]

AXES = [
    ("Organising principle", ["signal sections, today's order (V1)", "torque per joint (V2)", "four question tabs (V3)",
                              "joint × signal spreadsheet (V4)", "the instant at the cursor (V5)"]),
    ("Torque encoding", ["contract's five lines, feedback filled to zero (V1)", "feedforward area + feedback wedge up to commanded (V2)",
                         "feedback share over time + 100% budget bars (V3)", "one column per component, one y scale per row (V4)",
                         "waterfall target → FF → +FB → commanded → applied (V5)"]),
    ("Repeat encoding", ["lines ≤ 5 per group, bands past that (V1)", "one run against its group's band (V2)",
                         "dot strips + run × time heat strip (V3)", "bands in every cell (V4)",
                         "spread at the instant: whiskers + stick ghosts (V5)"]),
    ("Locating the bad moment", ["Worst-moment button + 3D section below the fold (V1)", "Worst-moment button + 3D thumbnail (V2)",
                                 "heat strip + worst-moment list + 3D (V3)", "Worst-moment button + corner 3D (V4)",
                                 "opens on the worst moment; three one-click chips (V5)"]),
]

INVARIANTS = [
    "Same SIMULATED fixture (fixture.py) and hero target: full-circle-slow, sim + 14 real repeats (8 × ff v1, 6 × ff v2).",
    "1440 × 900 hero; traj_compare's own style.css, uPlot and three.js, loaded by <script src> from file://.",
    "Fixed component colours: feedforward #3b82f6, feedback #f97316, target grey dashed, commanded = run colour, applied thin.",
    "Degrees for angles, N·m for torque; FB share = Σ|fb| / (Σ|ff| + Σ|fb|); error = target − run.",
    "Run colours keyed by config (sim grey, ff v1 violet, ff v2 green), never blue/orange; amber only for problems.",
    "Every side panel drags (width remembered) and folds; time cursor and x zoom shared by every plot on the page.",
]

VARIANTS = [
    {
        "id": "v1", "name": "Sidebar + sections", "accent": "#2a78d6",
        "thesis": "Today's run view, TensorBoard-ified: a run tree on the left and traj_compare's own section stack on the right, with a new Torque breakdown section; repeats collapse into percentile bands past five per group.",
        "bestWhen": "You want the smallest step from today's viewer: same sections, same chips, same transport, now with runs on the left and the torque split as a section.",
        "losesWhen": "You need error, torque and 3D on one screen — the 3D and error sections sit below the fold, so locating a moment means scrolling.",
        "decisions": [
            ["Organisation", "Sections as today (Answer · Torque breakdown · Joint error · Joint q · 3D paths), toggled by chips in the sticky control bar."],
            ["Torque encoding", "The contract's five traces for the highlighted run, beside every visible run's feedback as bands."],
            ["Repeats", "Auto: ≤ 5 runs in a config → lines, more → median + IQR + p5–p95 + min–max; Lines/Bands force it."],
            ["Answer first", "An Answer section on top: which feedforward model tracks better and by how much, error and FB share."],
        ],
        "keepParts": ["run tree with group-by + solo", "Answer section facts", "torque budget table in a disclosure", "auto lines → bands threshold"],
        "states": [("hero", "Answer + torque breakdown", "Opens on one sentence (ff v2 −43 % shoulder error, FB share 23 % → 6 %) and the five-trace breakdown of the worst run next to every run's feedback band.", "v1-hero.png"),
                   ("worst", "Worst moment, zoomed", "⚠ Worst moment zooms every plot to ±0.6 s around Real #03's worst instant and pins the time.", "v1-worst.png"),
                   ("lines", "Lines on demand, another run", "Repeats switched to Lines; Real #12 · ff v2 highlighted — the breakdown cards follow it.", "v1-lines.png"),
                   ("3d", "3D at the pinned time", "Below the fold: the arm at the pinned time, target ghost grey, other runs as sticks, and the five torques at the cursor.", "v1-3d.png")],
    },
    {
        "id": "v2", "name": "Torque cockpit", "accent": "#f97316",
        "thesis": "The torque is the page: per joint the command is drawn as what it is made of — feedforward as a blue area, feedback as the orange wedge between feedforward and commanded — one run at a time against its group's band, with the budget beside it.",
        "bestWhen": "The question is \"how much of the command is feedback, when, and is this run typical?\" — the wedge thickness is the feedback at every instant.",
        "losesWhen": "You want to see many runs' breakdowns at once, or signals other than torque and error; it is deliberately one run at a time.",
        "decisions": [
            ["Torque encoding", "Stacked: feedforward area from zero, feedback wedge from feedforward to commanded (correct through sign changes), target dashed, applied thin."],
            ["Repeats", "The highlighted run against the p5–p95 / IQR band of its own config (or of all real runs) for commanded torque and error."],
            ["Budget column", "FB share as a big number + FF|FB bar, where this run sits among every run (dot strip), drive gap, peak vs limit."],
            ["Run stepping", "◀ ▶ (or [ ]) walks the visible runs; the run list shows each run's FB share as a bar."],
        ],
        "keepParts": ["feedforward area + feedback wedge plot", "instant readout target · FF + FB = commanded → applied", "FB-share dot strip per config", "run stepper ◀ ▶"],
        "states": [("hero", "Worst run's cockpit", "Real #03 · ff v1: the orange wedge is the feedback — 24 % of the command — riding on a blue feedforward that under-models gravity.", "v2-hero.png"),
                   ("v2run", "A ff v2 run", "Click Real #12 · ff v2: the wedge nearly vanishes (FB 5 %) and the budget dot moves to the v2 lane.", "v2-v2run.png"),
                   ("worst", "Worst moment, zoomed", "⚠ Worst moment zooms both cockpits to Real #12's worst instant; the readout gives the split at that sample.", "v2-worst.png")],
    },
    {
        "id": "v3", "name": "Question tabs", "accent": "#8e5bd1",
        "thesis": "The run view as the four questions you bring to it — Is it good? · Where does the torque come from? · When did it go wrong? · Which joint? — each one composed screen, each tab label carrying its own short answer.",
        "bestWhen": "Someone new to the data, or a review: the tab strip alone answers the four questions before a tab is opened.",
        "losesWhen": "You want to cross-read two answers at once (torque split at the worst moment) — that means switching tabs.",
        "decisions": [
            ["Organisation", "Four tabs mirroring Rerun's questions layout; the run list, cursor and zoom persist across tabs."],
            ["Torque encoding", "Feedback share of the command over time (0–100 %) as config bands, the highlighted run's five traces beside, and a 100 % FF|FB bar per run."],
            ["Repeats", "Dot strips (one dot per run per joint) on 'Is it good?', a run × time |error| heat strip on 'When did it go wrong?'."],
            ["Answers in the tabs", "Each tab button shows its answer: v2 −43 % error · FB 23 % → 6 % · 2.33 s Real #03 · shoulder."],
        ],
        "keepParts": ["tab labels that carry the answer", "run × time |error| heat strip", "FB share over time bands", "per-run 100 % FF|FB bars"],
        "states": [("hero", "Is it good?", "Verdict sentence, three answer tiles that link to the other tabs, one dot per run, error bands over time.", "v3-hero.png"),
                   ("torque", "Where does the torque come from?", "Feedback share over time per config (it peaks where gravity load is highest) beside the worst run's five traces; budget bars per run below.", "v3-torque.png"),
                   ("when", "When did it go wrong?", "Run × time heat strip of |error|, worst moments outlined amber; ⚠ jumps to the worst and poses the 3D arm there.", "v3-when.png")],
    },
    {
        "id": "v4", "name": "Joint × signal grid", "accent": "#2f9e44",
        "thesis": "A spreadsheet of small multiples: rows are joints, columns are signals (error, commanded, feedforward, feedback, FB share, …), every cell carries each config's repeat band with the highlighted run on top; torque columns share one y scale per row so feedforward and feedback compare by size.",
        "bestWhen": "Scanning for which joint × signal is off, across many repeats — every cell has the same encoding, so the eye compares cells, not legends.",
        "losesWhen": "You need the composition at one instant (FF + FB = commanded) — the components live in separate cells.",
        "decisions": [
            ["Organisation", "Fixed grid: joints × signal columns, columns added or removed with chips (drive gap, applied, q on demand)."],
            ["Torque encoding", "One column per component, one shared torque scale per row, so the feedback cell is visibly smaller than the feedforward cell."],
            ["Repeats", "Bands in every cell (per config), lines on demand; each cell header gives the per-config median."],
            ["Drill-down", "⤢ or double-click expands a cell over the grid, with tabs to the neighbouring signals and the other joint; Esc returns."],
        ],
        "keepParts": ["one torque scale per row", "cell header with per-config medians", "expand-a-cell overlay with signal tabs", "column chips"],
        "states": [("hero", "The grid", "Two joints × five signals; ff v1 violet and ff v2 green bands in every cell, Real #03 on top; the corner holds the arm at the cursor.", "v4-hero.png"),
                   ("expanded", "Feedback cell expanded", "⤢ on shoulder × Feedback: the cell fills the grid; chips switch to the other signals or joint.", "v4-expanded.png"),
                   ("lines", "Lines on demand", "Repeats → Lines: every run as its own line in every cell.", "v4-lines.png")],
    },
    {
        "id": "v5", "name": "The moment", "accent": "#d79818",
        "thesis": "One scrubbable stage: a big 3D arm and, at the cursor, a torque waterfall per joint (target → Δ model → feedforward → + feedback → commanded → Δ drive → applied) with every run's spread at that instant; time plots sit small underneath.",
        "bestWhen": "Diagnosing why a particular instant went wrong — pose, gravity load and the torque chain are read together at one time.",
        "losesWhen": "You want the whole-run picture or run-to-run statistics first; the overview is the thin strip of time plots.",
        "decisions": [
            ["Organisation", "Stage-first: 3D on the left, the torque at the cursor on the right, three small time strips + transport underneath."],
            ["Torque encoding", "A waterfall per joint at the cursor, a clamp bar when the drive clipped (never hidden), limit lines when near saturation."],
            ["Repeats", "Whiskers (min–max, p5–p95, IQR) of every visible real run on each total at the same instant; other runs as stick ghosts in 3D."],
            ["Entry point", "Opens on the highlighted run's worst moment; three worst-moment chips jump between the top three."],
        ],
        "keepParts": ["torque waterfall at the cursor", "worst-moment chips on the stage", "stick ghosts of other runs in 3D", "clamp bar when the drive clips"],
        "states": [("hero", "Opens on the worst moment", "Real #03 at its worst instant: arm pose, gravity load, and the waterfall showing feedback supplying a large part of the command.", "v5-hero.png"),
                   ("worst", "Worst-moment chip", "Click the second chip (Real #01 at 3.56 s): focus, cursor, 3D pose, waterfalls and strips jump there, zoomed ±0.8 s.", "v5-worst.png"),
                   ("fast", "Fast target: saturation", "Full-circle fast: the commanded torque hits the 7 N·m limit — a clamp bar and amber limit line appear.", "v5-fast.png")],
    },
]


def preview(variant: dict) -> str:
    """The hero exhibit: the hero screenshot, plus each story state's screenshot shown when the walkthrough is on it."""

    # WHY !important: the deck's adopted preview sheet (.prototype img {display:block}) wins ties over an inline <style>
    style = ["<style>.rvp{width:1440px}.rvp img{display:none!important;width:1440px!important;height:900px!important}"
             ".rvp img.st-hero{display:block!important}"]
    for key, *_ in variant["states"][1:]:
        style.append(f'[data-story-state="{key}"] .rvp img.st-hero{{display:none!important}}'
                     f'[data-story-state="{key}"] .rvp img.st-{key}{{display:block!important}}')
    style.append("</style>")
    imgs = [f'<img class="st-{key}" src="shots/{shot}" width="1440" height="900" alt="{variant["name"]}: {label}">'
            for key, label, _caption, shot in variant["states"]]
    return "".join(style) + '<div class="rvp">' + "".join(imgs) + "</div>"


def media(variant: dict) -> list:
    items = [{"label": label, "caption": caption, "html": f'<img src="shots/{shot}" width="1440" height="900" alt="{label}">'}
             for key, label, caption, shot in variant["states"][1:3]]
    items.append({"label": "Live", "caption": "The running prototype on the shared fixture — drive it: click runs, Lines/Bands, ⚠ Worst moment, drag the panel edges.",
                  "html": f'<iframe src="{variant["id"]}/index.html" style="width:1440px;height:900px;border:0" title="{variant["name"]} live"></iframe>'})
    return items


def main() -> None:
    proofs = json.loads((HERE / "proof.json").read_text()) if (HERE / "proof.json").exists() else {}
    spec = {
        "schemaVersion": 3,
        "title": "Run view — five layouts",
        "kicker": "traj_compare · Round B · /babble 5 · SIMULATED fixture",
        "brief": "Five layouts for traj_compare's standalone RUN view — one target and all its runs (sim + 14 real repeats) — with a TensorBoard-style run list on the left, repeats as lines for a few and percentile bands for many, and the torque breakdown (target, commanded, feedforward, feedback, applied) first class.",
        "count": 5,
        "defaultId": "",
        "defaultWhy": "",
        "decisionHinge": "",
        "invariants": INVARIANTS,
        "boundary": "Standalone front-end prototypes over the SIMULATED shared fixture (fixture.py); run/build.py re-grids each run onto its target's time grid and computes the per-run torque budget, the page computes bands over the runs you select. Not wired into traj_compare's report.py / plots.js; no real rig data.",
        "axes": [{"name": name, "values": values} for name, values in AXES],
        "requirements": [
            {"id": rid, "name": name, "weight": weight, "why": why, "passCondition": cond, "anchors": {"1": a1, "3": a3, "5": a5}}
            for rid, name, weight, why, cond, (a1, a3, a5) in REQUIREMENTS
        ],
        "hardGates": [{"id": gid, "name": name, "why": why} for gid, name, why in GATES],
        "variants": [],
    }
    for v in VARIANTS:
        spec["variants"].append({
            "id": v["id"], "name": v["name"], "thesis": v["thesis"], "accent": v["accent"],
            "bestWhen": v["bestWhen"], "losesWhen": v["losesWhen"],
            "decisions": [{"label": label, "value": value} for label, value in v["decisions"]],
            "keepParts": v["keepParts"],
            "proof": proofs.get(v["id"], ["(proof not yet recorded — run build.py --shots)"]),
            "scores": {}, "gateResults": {},
            "previewLabel": "hero · 1440 × 900",
            "preview": preview(v),
            "story": {"title": v["name"] + " — walkthrough", "steps": [
                {"label": label, "caption": caption, "state": key} for key, label, caption, _shot in v["states"]]},
            "media": media(v),
        })  # fmt: skip
    (HERE / "gallery-spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
    print(HERE / "gallery-spec.json")


if __name__ == "__main__":
    main()
