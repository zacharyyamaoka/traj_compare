"""The babble gallery spec for Round A (standalone summary view): criteria from CRITERIA.md, five variants, their media.

Scores, gate results, the AI default and the decision hinge are deliberately EMPTY: the dispatcher prunes after seeing
all three rounds (the builder never grades its own variants). Proof lines come from OUT/shots/states.json, which
shots.py writes from what it actually exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIREMENTS = [
    ("a1", "Answer first", 25, "Zach's attention is the bottleneck; the page must say which feedforward configuration wins on each target before he reads anything else.",
     "Opening the page says which configuration is better on each target, and by how much (error and FB share), without scrolling",
     "numbers exist but must be hunted", "per-target winner visible, magnitude needs reading", "one glance: winner, margin, and confidence per target"),
    ("a2", "Runs grouped by target", 20, "\"The target is the thing that is constant and identical in everything\": runs only compare within their target.",
     "Runs sit under their target; select / hide / filter by tag (ff model, date, kind)",
     "flat run list", "grouped, but filtering is clumsy", "TensorBoard-grade: grouped, colour-keyed, filterable, select-all per group"),
    ("a3", "Repeat distribution", 20, "Real vs real × N: lines for a couple of repeats, distribution lines (median, IQR, percentiles) once N grows, like TensorBoard's histogram fans.",
     "real vs real × N spread is readable: lines for a few, bands (median, IQR, p5–p95, min–max) for many",
     "only means", "spread shown for one metric", "spread over time and per metric, encoding adapts to N"),
    ("a4", "Torque budget at summary level", 15, "\"Of the command torque some portion is coming from feedforward and some from feedback. That right now is not being made clear to me.\"",
     "FF vs FB share, drive gap and saturation per run / group",
     "absent", "one number per run", "compared across groups and targets at a glance"),
    ("a5", "Drill-down", 10, "The summary is the index; the run view is where a bad moment gets diagnosed.",
     "one click from a run or group to its run view", "none", "link per run", "from any mark (row, band, dot)"),
    ("a6", "Scales", 10, "Today 30 runs on 3 targets; a sweep or a week of repeats is 100+ runs and up to 6 joints.",
     "3 → 100+ runs, 1 → 6 joints without breaking", "breaks past ~10 runs", "degrades but usable", "designed for it (aggregation, virtual lists)"),
]
GATES = [
    ("g1", "Self-contained", "Standalone pages open from file:// with no server and no CDN (traj_compare's contract)."),
    ("g2", "Units", "Angles in degrees, tool in mm, torque in N·m; SI stays in the stored data."),
    ("g3", "Honest data", "Everything shown comes from the shared fixture; every page says SIMULATED."),
]

VARIANTS = [
    {
        "id": "v1", "name": "Scalars board", "accent": "#2a78d6",
        "thesis": "TensorBoard's Scalars page for repeats: runs on the left grouped by target, one chart per metric × target over trajectory time, a percentile fan per config group once it has more than N runs.",
        "bestWhen": "You already know the question is 'where in the motion does it diverge' and want every metric over time, TensorBoard-style, with run toggling as the main verb.",
        "losesWhen": "You want a ranked answer or a single number per configuration: the verdict is a thin strip and everything else is curves to read.",
        "decisions": [
            {"label": "Primary object", "value": "A chart per metric × target (error, |τ_fb|, FB share, drive gap), sections like TensorBoard tag groups."},
            {"label": "Navigation", "value": "Left run tree: regex filter, tag chips (ff model, date, kind), colour checkbox per run, select-all per target; hover draws a run over its fan, click pins it."},
            {"label": "Repeats", "value": "Auto: lines while a group has ≤ N runs (slider), median + IQR + p5–p95 + min–max fan above; Lines / Bands override; TensorBoard smoothing."},
            {"label": "Answer", "value": "One verdict cell per target above the charts: winner, Δ RMS error, FB share v1 → v2, pair-wise confidence."},
        ],
        "keepParts": ["left run tree with tag chips + select-all per target", "auto lines→fan threshold slider", "hover a run to draw it over its group's fan"],
        "previewLabel": "Scalars board · 1440 × 900",
        "steps": [
            ("base", "Verdict strip + fans", "Each target's winner, margin and confidence sit above the charts; slow's ff v1 (8 runs) and ff v2 (6) are already fans, fast and pick are lines (≤ 5 runs)."),
            ("bands", "Bands for every group", "Repeats → Bands: every group with ≥ 3 runs becomes median + IQR + p5–p95 + min–max, so fast's 4 + 4 compare as distributions too."),
            ("pinned", "Filter + pin one run", "Regex 'v1|sim' hides the v2 runs; clicking real-03 pins it as a dark line over the ff v1 fan on every chart of its target."),
        ],
    },
    {
        "id": "v2", "name": "League table", "accent": "#5b6b7a",
        "thesis": "Answer first as a table: one row per target × config group with the verdict on each target's header, the error distribution as a box (dots while n is small), FB share, drive gap, saturation, ISO 9283 path repeatability and an error sparkline.",
        "bestWhen": "You want the decision ('is v2 better, by how much, how sure') and the numbers behind it in one dense, sortable view, then a detail panel for the one row you care about.",
        "losesWhen": "The question is about when in the trajectory things diverge: time only appears as sparklines and in the detail panel.",
        "decisions": [
            {"label": "Primary object", "value": "The target × config-group row; runs are its expansion (▸), sorted by the chosen metric."},
            {"label": "Navigation", "value": "Sort by any column; By target blocks or one ranked League; date filter; a draggable, foldable detail panel for the selected row."},
            {"label": "Repeats", "value": "Dots while a group has ≤ 5 runs, box (IQR) + min–max whiskers above; the detail panel shows the group's error fan over time."},
            {"label": "Torque budget", "value": "FB-share bar with the run range, drive-gap RMS and saturation per row; per-run stacked ff | fb | gap bars in the panel."},
        ],
        "keepParts": ["verdict line on each target header", "box-or-dots distribution cell on a per-target axis", "ISO 9283 path repeatability column (mm)"],
        "previewLabel": "League table · 1440 × 900",
        "steps": [
            ("base", "Verdict per target header", "Each block opens with the winner, Δ RMS error, FB share v1 → v2 and confidence; ff v2 slow is selected (detail right) and expanded into its 6 runs."),
            ("league", "One ranked league", "Rows → League: every target × group on one shared axis, ranked by median; the sim reference rows stay last."),
            ("fbshare", "Distribution of FB share", "Distribution of → FB share, then the fast ff v1 row: the detail panel swaps to its error fan and per-run torque budget."),
        ],
    },
    {
        "id": "v3", "name": "Target cards", "accent": "#0f9d8a",
        "thesis": "Small multiples: one card per target with a big verdict, its error fan per config group, a torque-budget bar per group and a strip of its runs — the grid is the page; ⤢ focuses one card with its run list.",
        "bestWhen": "A handful of targets you scan side by side, each needing its own answer, curve and torque split in one place.",
        "losesWhen": "Many targets (cards scroll) or cross-target ranking: each card has its own scale and nothing compares targets directly.",
        "decisions": [
            {"label": "Primary object", "value": "The target card: verdict → fan → torque budget → run strip, top to bottom."},
            {"label": "Navigation", "value": "Grid of cards; per-card group chips; ⤢ focus expands one card with a draggable, foldable run list (checkboxes per run and per group)."},
            {"label": "Repeats", "value": "Auto lines ≤ 5 runs, fan above, per card; fan of error, |τ_fb| or rolling FB share; hover a run dot to draw it over the fan."},
            {"label": "Torque budget", "value": "One stacked bar per config group (ff | fb | drive gap as shares of Σ|command|) with the per-run FB-share whisker."},
        ],
        "keepParts": ["big verdict box per target (Δ, v1 → v2, FB share, confidence)", "per-group torque budget bar with run whisker", "run dot strip that draws the hovered run on the fan"],
        "previewLabel": "Target cards · 1440 × 900",
        "steps": [
            ("base", "Three verdicts at a glance", "Each card leads with its verdict (−43 % / −52 % / v1 only), then the fan, the torque budget per group and the run strip."),
            ("focus", "Focus one target", "⤢ on the slow card: it spans the page with a bigger fan and its run list on the right (draggable, foldable, checkboxes)."),
            ("fbtorque", "Fan of feedback torque", "Fan of → Feedback torque: the same cards now show |τ_fb| over time, so the ff v1 gravity slope is visible per target."),
        ],
    },
    {
        "id": "v4", "name": "Torque budget board", "accent": "#e07b39",
        "thesis": "Torque first: per target a beeswarm of FB share by config group and one stacked feedforward | feedback | drive-gap bar per run; tracking error is the secondary column; a drawer plays one run's five torques over time.",
        "bestWhen": "The question of the day is Zach's: how much of the command is feedback, did the calibrated feedforward take it over, and where does the drive saturate.",
        "losesWhen": "You need tracking error over time or a ranked accuracy verdict: error is one grey number per run here.",
        "decisions": [
            {"label": "Primary object", "value": "The torque budget: FF / FB / drive-gap per run, as % of Σ|command| or mean |τ| in N·m."},
            {"label": "Navigation", "value": "Three target columns side by side; click any bar or dot → the bottom drawer (draggable, foldable) shows that run's target / commanded / ff / fb / applied over time."},
            {"label": "Repeats", "value": "Beeswarm dot per run, IQR box once n > 5; Per group collapses runs into one aggregate bar with its p25–p75 spread (the 100+ runs view)."},
            {"label": "Problems", "value": "Amber limit marks where the command sits at max_torque_nm; nothing else is coloured as a warning."},
        ],
        "keepParts": ["FB-share beeswarm by config", "stacked ff | fb | drive-gap bar per run with limit mark", "five-torque drawer with the group's feedback band"],
        "previewLabel": "Torque budget board · 1440 × 900",
        "steps": [
            ("base", "Where the command comes from", "The strip answers per target (feedback 23 % → 6 % on slow); below, the FB-share beeswarm and one budget bar per run, sorted by FB share."),
            ("fastrun", "One run's torques over time", "Click fast real-04: the drawer plots target (dashed), commanded, ff, fb and applied with the ff v1 feedback band behind, and flags the drive limit."),
            ("groups", "Collapse to groups", "Rows → Per group: each config group becomes one aggregate bar with its FB-share p25–p75 spread — the view that survives 100+ runs."),
        ],
    },
    {
        "id": "v5", "name": "Run ledger", "accent": "#7c5cc4",
        "thesis": "History first: every run in order along date / run number, one SPC control-chart lane per target with I-MR limits per ff-model phase, a run ledger on the left, and a drawer with the selected phase's repeats over the trajectory.",
        "bestWhen": "You are tracking a rig over days: what changed when (ff v1 → v2), whether a new run is inside the usual spread, and spotting drift.",
        "losesWhen": "The fixture has no time of day and few dates, so the history axis is thin; within-trajectory shape lives only in the drawer.",
        "decisions": [
            {"label": "Primary object", "value": "The run in time: an individuals control chart per target, centre line and ±2.66·MR̄ limits per phase, out-of-limit runs red."},
            {"label": "Navigation", "value": "Left ledger (date-grouped, draggable, foldable) and the lanes select the same run; the bottom drawer (draggable, foldable) shows that phase as lines or a fan."},
            {"label": "Repeats", "value": "Spread as control limits across runs; over the trajectory, the drawer draws lines for ≤ 5 repeats and a fan above, against the other phase in grey."},
            {"label": "Answer", "value": "A 'what changed' banner: Δ mean per target at the phase break, FB share before → after, and whether any run left its limits."},
        ],
        "keepParts": ["what-changed banner at the ff-model phase break", "control-chart lane with per-phase limits + shift rule", "date-grouped run ledger"],
        "previewLabel": "Run ledger · 1440 × 900",
        "steps": [
            ("base", "What changed, and is it real", "The banner states the phase break (ff v2 from 11-19) per target; each lane shows the per-phase centre and limits, with no run above its upper limit."),
            ("lane", "Whole-lane limits find the shift", "Limits → Whole lane: one set of limits over the full history; the 6-in-a-row rule brackets ff v1's 8 runs above centre, real-03 turns red above the upper limit, real-14 is ringed grey (unusually good)."),
            ("fbshare", "FB share history + one run", "Metric → FB share, then fast real-01 in the ledger: its point is ringed and the drawer shows its phase's repeats with real-01 in black."),
        ],
    },
]

SHOT_NAMES = {
    "v1": {"bands": "v1-bands", "pinned": "v1-pinned"},
    "v2": {"league": "v2-league", "fbshare": "v2-fbshare"},
    "v3": {"focus": "v3-focus", "fbtorque": "v3-fbtorque"},
    "v4": {"fastrun": "v4-fastrun", "groups": "v4-groups"},
    "v5": {"lane": "v5-lane", "fbshare": "v5-fbshare"},
}


def _preview(variant: dict, states: dict) -> str:
    vid = variant["id"]
    css = [".tcs-shot{position:relative;width:1440px;height:900px;background:#f4f4f2}",
           ".tcs-shot>img.shot{display:none!important;width:1440px!important;height:900px!important;max-width:none!important}",
           ".tcs-shot>img.shot.s-base{display:block!important}",
           ".tcs-shot>span.hl{display:none;border-radius:6px;pointer-events:none}"]
    parts = []
    for state, label, _caption in variant["steps"]:
        src = f"shots/{vid}-hero.png" if state == "base" else f"shots/{SHOT_NAMES[vid][state]}.png"
        if state != "base":
            css.append(f'[data-story-state="{state}"] .tcs-shot>img.shot.s-{state}{{display:block!important}}')
            css.append(f'[data-story-state="{state}"] .tcs-shot>img.shot.s-base{{display:none!important}}')
        css.append(f'[data-story-state="{state}"] .tcs-shot>span.hl-{state}{{display:block}}')
        parts.append(f'<img class="shot s-{state}" src="{src}" width="1440" height="900" alt="{variant["name"]} — {label}">')
        r = (states.get(vid, {}).get("steps", {}).get(state) or {}).get("hl")
        if r:
            parts.append(f'<span class="hl hl-{state}" style="position:absolute;left:{r["x"] - 3}px;top:{r["y"] - 3}px;width:{r["w"] + 6}px;height:{r["h"] + 6}px"></span>')
    return f'<div class="tcs-shot"><style>{"".join(css)}</style>{"".join(parts)}</div>'


def _proof(vid: str, states: dict) -> list[str]:
    tests = states.get(vid, {}).get("tests", {})
    lines = [f"Drove {len(states.get(vid, {}).get('steps', {}))} states in headless Chrome at 1440 × 900 from file:// (shots.py); every state shot is that run."]
    for key, res in tests.items():
        if key.endswith("drag_fold_persist"):
            lines.append(f"{'Drawer' if key.startswith('drawer') else 'Panel'} boundary drag-tested: {res['before']} → {res['after_drag']} px, same after reload ({res['after_reload']} px), double-click folds to {res['folded']} px and restores — {'PASS' if res['ok'] else 'FAIL'}.")
        elif key == "drill":
            lines.append(f"Drill-down click sets {res['hash']} and shows the labelled run-view placeholder — {'PASS' if res['ok'] else 'FAIL'}.")
        elif key == "regex_filter_rows":
            lines.append(f"Regex filter 'v1|sim' left {res} run rows in the tree.")
        elif key == "sort_click":
            lines.append(f"Clicking the FB share header re-sorted the first block (top row {res}).")
        elif key == "detail_title":
            lines.append(f"Selecting a row retitled the detail panel: '{res}'.")
    errs = [e for e in states.get("console_errors", []) if e.startswith(vid + ":")]
    lines.append("0 console errors." if not errs else f"{len(errs)} console errors: {errs[0][:120]}")
    lines.append("Stats are a prototype computation in shared/common.js over the SIMULATED fixture, not traj_compare's analysis.py.")
    return lines


def spec(out: Path) -> dict:
    states_path = out / "shots" / "states.json"
    states = json.loads(states_path.read_text()) if states_path.exists() else {}
    variants = []
    for v in VARIANTS:
        vid = v["id"]
        media = []
        for state, label, caption in v["steps"][1:]:
            media.append({"label": label, "caption": caption, "html": f'<img src="shots/{SHOT_NAMES[vid][state]}.png" width="1440" height="900" alt="{v["name"]} — {label}">'})
        media.append({"label": "Live", "caption": "The running page from file:// — every control works; drag the panel boundary, fold it, click any mark to drill.",
                      "html": f'<iframe src="{vid}/index.html" title="{v["name"]} live" style="width:1440px;height:900px;border:0"></iframe>'})
        variants.append({
            "id": vid, "name": v["name"], "thesis": v["thesis"], "accent": v["accent"], "bestWhen": v["bestWhen"], "losesWhen": v["losesWhen"],
            "decisions": v["decisions"], "keepParts": v["keepParts"], "proof": _proof(vid, states), "previewLabel": v["previewLabel"],
            "preview": _preview(v, states), "media": media,
            "story": {"title": f"{v['name']} · walkthrough", "steps": [{"label": label, "caption": caption, "state": state, "target": f".hl-{state}"} for state, label, caption in v["steps"]]},
            "scores": {}, "gateResults": {},
        })
    axes = [
        {"name": "Primary object", "values": ["metric chart over time (V1)", "target × config row (V2)", "target card (V3)", "torque budget per run (V4)", "run in history (V5)"]},
        {"name": "Navigation", "values": ["run tree + chart sections (V1)", "sortable table + detail panel (V2)", "card grid + focus (V3)", "target columns + run drawer (V4)", "ledger + control-chart lanes (V5)"]},
        {"name": "Distribution encoding", "values": ["time fan per group, lines ≤ N (V1)", "box or dots per group (V2)", "fan per card + run dot strip (V3)", "beeswarm + stacked bars (V4)", "control limits per phase (V5)"]},
        {"name": "Answer device", "values": ["verdict strip over the charts (V1)", "verdict on each target header (V2)", "big verdict per card (V3)", "FB-share answer strip (V4)", "what-changed banner (V5)"]},
    ]
    return {
        "schemaVersion": 3,
        "title": "Summary view — five layouts",
        "kicker": "Round A · traj_compare standalone summary · /babble 5",
        "brief": "Five layouts for traj_compare's standalone summary view: many runs across every target, runs grouped by target (the target is the one thing identical across its runs), real-vs-real × N as lines for a few and percentile fans for many, and the feedforward / feedback torque budget first class.",
        "count": len(variants),
        "defaultId": "", "defaultWhy": "", "decisionHinge": "",
        "invariants": [
            "Same SIMULATED fixture (fixture.py): vertical 2R arm, 3 targets, 27 real repeats + 3 sims, ff v1 nominal vs v2 calibrated.",
            "Same viewport (1440 × 900), traj_compare's calm palette and uPlot; amber/red only for problems.",
            "Same prototype stats (shared/common.js): error = target − run in degrees, FB share = Σ|τ_fb| / (Σ|τ_ff| + Σ|τ_fb|), drive gap = τ_cmd − τ_applied.",
            "Every page opens from file://, says SIMULATED, drills to a labelled #run/<target>/<run> placeholder.",
        ],
        "boundary": "Standalone HTML prototypes over the shared SIMULATED fixture; interactions, filters and panel resizing are real; the run view behind every drill link is a placeholder hash, and the stats are a browser-side prototype computation, not traj_compare's analysis.py.",
        "axes": axes,
        "requirements": [{"id": i, "name": n, "weight": w, "why": why, "passCondition": pc, "anchors": {"1": a1, "3": a3, "5": a5}} for i, n, w, why, pc, a1, a3, a5 in REQUIREMENTS],
        "hardGates": [{"id": i, "name": n, "why": why} for i, n, why in GATES],
        "variants": variants,
        "checks": ["Exactly five structural directions (S1–S5 as allocated in CRITERIA.md)", "Same fixture, viewport and fidelity class", "Scores, gates and the AI default left for the dispatcher"],
    }
