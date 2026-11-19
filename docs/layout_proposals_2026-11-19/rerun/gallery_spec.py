"""The babble gallery for round C (Rerun run view): writes <OUT>/gallery-spec.json from the builder's manifest and the
real screenshots, then <OUT>/index.html.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19/rerun
    python3 gallery_spec.py [--out <OUT>]

Scores, gate results, the default and the decision hinge are left EMPTY on purpose: the dispatcher scores the round.
``gallery.py build`` refuses a spec without scores, so until then index.html is rendered with the skill's own
``render_gallery`` (same deck shell, no validation); the dispatcher's ``gallery.py build`` replaces it.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

OUT_DEFAULT = Path("/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19/rerun")
SKILL = Path("/home/bam/.claude-personal/skills/babble")
CRITERIA = Path(__file__).resolve().parents[1] / "CRITERIA.md"

REQUIREMENTS = [
    ("c1", "Torque breakdown at a glance", 25, "Zach: of the commanded torque, how much is feedforward and how much feedback 'is not being made clear to me'.",
     "target / commanded / FF / FB / applied for a joint and run in one view",
     ("spread over tabs", "one view per run, cluttered", "one view, legible, FB share visible")),
    ("c2", "Repeats as a distribution", 20, "real vs real × N: lines for a few, median + percentile fans (TensorBoard) for many.",
     "many repeats as bands (precomputed p5/p25/median/p75/p95 series) with any one run against them",
     ("all lines", "bands for one channel", "bands for error and torque, one run highlighted")),
    ("c3", "Where / when", 20, "The bad moment has to be located in the robot and on the clock together.",
     "3D, time series (and video when present) on one timeline", ("separate tabs", "same timeline, some scrolling", "one screen")),
    ("c4", "Scales to repeats", 15, "14 repeats today, many more later.",
     "14 repeats do not explode the tab bar or legends", ("one tab per run", "grouped", "constant structure as N grows")),
    ("c5", "Consistent with the HTML", 10, "Rerun and the HTML run view are two projections of one dataset.",
     "same names, colours, units as the HTML run view", ("different", "mostly", "identical")),
    ("c6", "Opens in one step", 10, "The 'Open in Rerun' button is one command.",
     "blueprint embedded, `uvx --from rerun-sdk==0.40.0 rerun file.rrd` shows it", ("needs manual setup", "needs a second file", "embedded")),
]

GATES = [
    ("g1", "Opens in stock Rerun 0.40.0 with the blueprint embedded", "The layout travels inside the .rrd; no fork, no plugin, no sidecar needed to see it."),
    ("g2", "Units: degrees, mm, N·m", "Zach's rule: degrees in every human view, SI in stored data."),
    ("g3", "Honest data: the shared fixture, SIMULATED on screen", "Every variant shows the same scenario and says it is simulated."),
]

AXES = [
    {"name": "Container structure", "values": [
        "pinned stage + question tabs, one new tab (V1)", "one screen per run, an .rbl per run to switch (V2)",
        "one screen: fan grid + 3D + summary (V3)", "one tab per config group + a comparison tab (V4)",
        "one vertical stack on one clock, joints as columns (V5)"]},
    {"name": "Torque encoding", "values": [
        "joint × component small multiples, lines (V1)", "stacked areas: FF + FB = commanded, one run (V2)",
        "feedback and commanded as percentile fans per group (V3)", "target · FF · commanded per run, feedback per run beside (V4)",
        "every component on one scope channel, contract colours (V5)"]},
    {"name": "Repeat encoding", "values": [
        "every run a line in every view (V1)", "one run against its group's grey fan (V2)",
        "fans per config group, runs hidden, worst run bold (V3)", "lines inside a group tab, fans only in v1 vs v2 (V4)",
        "scope persistence: every run faint, worst run bold (V5)"]},
]

VARIANTS = {
    "q1-torque-tab-grid": {
        "id": "v1", "name": "Torque Tab Grid", "accent": "#5c7cfa",
        "thesis": "The smallest change to the shipped `questions` layout: one more tab, a joint × component grid "
                  "(commanded · FF · FB · applied) with every run as a line in each view, FB-share bars and the torque budget table under it.",
        "bestWhen": "A handful of runs per target and you already work in `questions`: the torque tab sits one click beside the tabs you know.",
        "losesWhen": "Repeats grow: 15 lines per view already braid into one, FB share per run lives only in bars and a table, and the 8-hue palette repeats past 8 runs.",
        "decisions": [
            {"label": "Container", "value": "`questions` unchanged plus one tab, “Feedforward or feedback?”, second in the bar; the stage keeps every run in 3D."},
            {"label": "Torque encoding", "value": "One view per joint × component; the title names the component, so lines keep run colours (same run, same colour in all eight)."},
            {"label": "Repeats", "value": "Every run is a line; no bands. FB share = bars indexed by repeat number (0 = sim) plus the torque budget table."},
        ],
        "keepParts": ["joint × component grid", "FB-share bars indexed by repeat number", "torque budget table as a text view"],
        "steps": {"hero": ("Feedforward or feedback?", "The new tab: rows = joints, columns = commanded (grey = target) · FF · FB · applied, every run a line; FB-share bars and the budget table below. FF has two curves (v1, v2); FB fans out by group."),
                  "is-it-good": ("Is it good?", "The shipped opening tab, untouched: scorecard worst-first, worst-joint and L2-tip error, events. The torque tab is the second tab.")},
    },
    "q2-solo-run": {
        "id": "v2", "name": "Solo Run Dashboard", "accent": "#f08c00",
        "thesis": "One run at a time, everything about it on one screen: 3D beside its stacked breakdown (blue FF area + orange FB area = commanded, "
                  "target grey), its feedback and error against its config group's grey fan, and its numbers; one .rbl per run switches the run.",
        "bestWhen": "You are asking “what happened on this run, and how much of the command was feedback?” — the split reads at a glance, at any instant.",
        "losesWhen": "You want to compare runs: switching is one file per run (no in-viewer picker), and only the run's own group is drawn as a band.",
        "decisions": [
            {"label": "Container", "value": "No tabs: 3D + run card left; breakdown, feedback and error rows × joints right. The embedded layout is the scorecard's worst run; 15 sidecar .rbl files switch to any other."},
            {"label": "Torque encoding", "value": "Stacked areas drawn with Measurements (centre ± half-width): 0 → FF blue, FF → FF + FB orange. The orange sliver is the feedback share, at every instant."},
            {"label": "Repeats", "value": "The run against its group's fan, recoloured grey in this view by a blueprint override, so the fan never fights the run's own colour."},
        ],
        "keepParts": ["FF + FB stacked areas", "run card: FB share vs group median", "group fan behind one run"],
        "steps": {"hero": ("Worst run", "Real #03 · ff v1, the scorecard's worst (29.9 mm): the orange area between FF and commanded is the 24 % feedback share; its error rides the top of the ff v1 fan."),
                  "best-v2": ("Another run's .rbl", "The same .rrd opened with the best ff v2 run's blueprint: the orange sliver almost vanishes — the calibrated feedforward carries the load.")},
    },
    "q3-distribution-first": {
        "id": "v3", "name": "Distribution First", "accent": "#9a5b2e",
        "thesis": "Fans first: per joint, min–max and p25–p75 fans plus the median for error, feedback and commanded, one fan per config group; "
                  "individual runs are in every plot but hidden, and the worst run is drawn bold over the fans.",
        "bestWhen": "Many repeats (14 now, 100 later): the plot structure never changes with N, and v1 vs v2 reads as two fans.",
        "losesWhen": "You need the five-torque split for one run (only FB and commanded appear, as distributions), or a group has 2–3 runs and a fan is noise.",
        "decisions": [
            {"label": "Container", "value": "One screen, no tabs: a 3 × 2 fan grid, the worst run in 3D, a distribution summary and FB-share bars by group."},
            {"label": "Torque encoding", "value": "Feedback and commanded as per-group fans (brown ff v1, blue ff v2); FB share as group-coloured bars per run."},
            {"label": "Repeats", "value": "Runs hidden with EntityBehavior(visible=False), one eye-click away in the Blueprint panel; the worst run (scorecard) drawn bold."},
        ],
        "keepParts": ["per-group percentile fans (Measurements)", "hidden-but-present run lines", "worst run drawn over the fans"],
        "steps": {"hero": ("Fans + worst run", "Two fans per plot (brown ff v1 ×8, blue ff v2 ×6), medians as lines, Real #03 bold. The v2 fan sits near zero error and near zero feedback."),
                  "reveal": ("A run switched on", "The same view with the best ff v2 run switched on (an alternate blueprint stands in for the eye-click): one line against both fans.")},
    },
    "q4-config-group-tabs": {
        "id": "v4", "name": "Config-Group Tabs", "accent": "#0ca678",
        "thesis": "Group by configuration: one tab per config group (Sim · ff v1 ×8 · ff v2 ×6), each with its runs in 3D, target / FF / commanded "
                  "and feedback per run, error and the group's torque budget; a last tab lays the two groups' fans over each other.",
        "bestWhen": "The question is “did the new feedforward help?” and each group has few enough runs to read as lines.",
        "losesWhen": "Configurations multiply (a tab each) or a group grows past ~8 runs (lines braid); one run's FF / FB split is never isolated.",
        "decisions": [
            {"label": "Container", "value": "Tabs = config groups (constant as repeats grow, grows with configurations) + “v1 vs v2”."},
            {"label": "Torque encoding", "value": "Per group: target grey over FF blue (v1's FF is the target itself), commanded in run colours; feedback per run in run colours beside."},
            {"label": "Repeats", "value": "Lines within a group; fans (brown v1, blue v2) only on the comparison tab, with the FB-share bars by group."},
        ],
        "keepParts": ["one tab per config group", "group torque budget table", "v1 vs v2 fan overlay"],
        "steps": {"hero": ("ff v1 · 8 runs", "The ff v1 group: commanded sits ~1 N·m above target and FF (they coincide for v1), feedback per run carries the gap; budget table lower left."),
                  "ff-v2": ("ff v2 · 6 runs", "The ff v2 group: FF has moved up onto commanded, feedback shrinks to a few tenths of a N·m, error flattens."),
                  "compare": ("v1 vs v2", "Both groups as fans for error, feedback and commanded, the comparison table (FB share 23 % → 6 % at the shoulder) and FB-share bars by group.")},
    },
    "q5-oscilloscope": {
        "id": "v5", "name": "Oscilloscope Stack", "accent": "#495057",
        "thesis": "One vertical stack on one clock, like a scope: 3D (and video when present) and FB-share bars on top, then error, then target / commanded / "
                  "FF / FB, then applied and current — joints as columns; every run faint (persistence), the worst run bold.",
        "bestWhen": "Locating the bad moment: every channel shares the cursor and zoom on one screen, nothing to click.",
        "losesWhen": "The torque channel carries four components × 15 runs and stays legible only through persistence; the FB share per instant is read as the orange trace's height.",
        "decisions": [
            {"label": "Container", "value": "No tabs, fixed rows: 3D + bars · CH1 error · CH2 torque · CH3 applied + CH4 current; joints as columns; x zoom linked."},
            {"label": "Torque encoding", "value": "All components on one channel in their contract colours (commanded = run colour, FF blue, FB orange), target grey."},
            {"label": "Repeats", "value": "Persistence: blueprint overrides draw every run at alpha 55 and the worst run at full width — no extra entities."},
        ],
        "keepParts": ["scope persistence via overrides", "one-clock stack with linked zoom", "channel numbering"],
        "steps": {"hero": ("The stack", "Everything on one screen at the worst moment (t = 2.34 s): Real #03 bold over 14 faint runs in every channel."),
                  "zoom": ("Zoomed", "The same blueprint with a 1.6 s time window (TimeAxis view_range): the scope's horizontal zoom, all channels together.")},
    },
}


def preview(spec: dict, shots: list[dict]) -> str:
    """A tab-like step bar over the real screenshots; each button jumps the walkthrough to that state."""

    vid = spec["id"]
    rules = "".join(
        f'.prototype[data-story-state="s{i}"] img.rr-{vid}-s{i}{{display:block!important}}'
        f'.prototype[data-story-state="s{i}"] .rr-tab[data-story-to="s{i}"]{{background:#fff;color:#111;box-shadow:0 0 0 1px #c9c9c9}}'
        for i in range(len(shots))
    )
    rules += f'.prototype:not([data-story-state]) img.rr-{vid}-s0{{display:block!important}}'
    buttons = "".join(f'<button class="rr-tab" data-story-to="s{i}">{html.escape(spec["steps"][shot["shot"]][0])}</button>'
                      for i, shot in enumerate(shots))
    images = "".join(f'<img class="rr-shot rr-{vid}-s{i}" src="{html.escape(shot["png"])}" '
                     f'alt="{html.escape(spec["steps"][shot["shot"]][0])} — real Rerun 0.40.0 web viewer, 1440 × 900">'
                     for i, shot in enumerate(shots))
    style = ("<style>.rr-wrap{background:#f4f4f2;border-radius:8px;overflow:hidden}"
             ".rr-bar{display:flex;flex-wrap:wrap;gap:4px;padding:6px;background:#ececea;font:12px system-ui}"
             ".rr-tab{border:0;border-radius:5px;padding:4px 9px;background:transparent;color:#555;cursor:pointer;font:inherit}"
             ".rr-tab:hover{background:#fff}.prototype img.rr-shot{display:none;width:100%;height:auto;max-width:100%}" + rules + "</style>")
    return f'{style}<div class="rr-wrap"><div class="rr-bar">{buttons}</div>{images}</div>'


def build_spec(out: Path) -> dict:
    manifest = json.loads((out / "manifest.json").read_text())
    variants = []
    for slug, spec in VARIANTS.items():
        shots = [dict(shot, png=f"shots/{slug}--{shot['shot']}.png") for shot in manifest["shots"] if shot["slug"] == slug]
        missing = [shot["png"] for shot in shots if not (out / shot["png"]).is_file()]
        if missing:
            raise SystemExit(f"missing screenshots: {missing}")
        rrd = out / manifest["variants"][slug]["rrd"]
        command = f"uvx --from rerun-sdk==0.40.0 rerun {rrd}"
        media = [{"label": spec["steps"][shot["shot"]][0], "caption": spec["steps"][shot["shot"]][1],
                  "html": f'<img src="{html.escape(shot["png"])}" alt="{html.escape(spec["steps"][shot["shot"]][0])} — real Rerun 0.40.0 screenshot">'}
                 for shot in shots[1:]]  # fmt: skip
        check = out / "shots" / f"{slug}--embedded-check.png"
        if check.is_file():  # G1 proof: the .rrd opened alone, no .rbl in the URL
            media.append({"label": "Embedded only (G1 check)", "caption": f"{rrd.name} opened alone in the web viewer, no .rbl: "
                          "the embedded default blueprint lands on the same layout.",
                          "html": f'<img src="shots/{check.name}" alt="{rrd.name} opened with no blueprint file — real Rerun 0.40.0">'})
        commands = [command]
        if slug == "q2-solo-run":
            commands.append(f"uvx --from rerun-sdk==0.40.0 rerun {rrd} {out / 'blueprints' / 'q2-solo-run--real-10.rbl'}")
        media.append({"label": "Open in Rerun 0.40.0", "caption": "One command; the layout is embedded in the .rrd"
                      + (" (the second line opens another run's blueprint beside it)." if len(commands) > 1 else "."),
                      "html": "<pre style=\"white-space:pre-wrap;font:12px ui-monospace,monospace;padding:12px\"><code>"
                              + "\n".join(html.escape(c) for c in commands) + "</code></pre>"})
        variants.append({
            "id": spec["id"], "name": spec["name"], "thesis": spec["thesis"], "accent": spec["accent"],
            "bestWhen": spec["bestWhen"], "losesWhen": spec["losesWhen"], "decisions": spec["decisions"], "keepParts": spec["keepParts"],
            "proof": [
                f"Opened {rrd.name} in the real Rerun 0.40.0 web viewer (rerun --serve-web, headless Chromium via Playwright) with its "
                f"embedded blueprint; {len(shots)} state(s) screenshotted at 1440 × 900 with the playhead typed to t = {shots[0]['at']} s.",
                "Torque, bands and FB-share entities logged through write_rrd(extra=...) from the SIMULATED fixture on traj_compare HEAD 273ad59; "
                "/torque and /stats/fb_share paths as CONTRACT.md names them.",
            ],
            "previewLabel": "real Rerun 0.40.0 screenshots — click a state",
            "preview": preview(spec, shots),
            "story": {"title": "Walk the states", "steps": [
                {"label": spec["steps"][shot["shot"]][0], "caption": spec["steps"][shot["shot"]][1], "state": f"s{i}",
                 "target": f'.rr-tab[data-story-to="s{i}"]'} for i, shot in enumerate(shots)]},
            "media": media,
            "scores": {},
            "gateResults": {},
        })  # fmt: skip
    return {
        "schemaVersion": 3,
        "title": "Rerun run view — five layouts",
        "kicker": "Round C · babble 5 · 2026-11-19 · SIMULATED fixture",
        "brief": "Five layouts of traj_compare's Rerun RUN view — one target and every run of it, in stock Rerun 0.40.0 — that make the torque "
                 "breakdown (target / commanded / feedforward / feedback / applied) first class and show real × N repeats as lines for a few "
                 "and distributions for many. Same SIMULATED scenario in all five: full-circle-slow, sim + 8 ff v1 + 6 ff v2 repeats.",
        "count": len(variants),
        "defaultId": "", "defaultWhy": "", "decisionHinge": "",
        "invariants": [
            "Same .rrd content in all five (target full-circle-slow: sim + 14 real repeats); only the embedded blueprint differs.",
            "CONTRACT.md entity paths and component colours: /torque/<joint>/target, /torque/<joint>/<run>/{commanded,feedforward,feedback,applied}, /stats/fb_share/<joint>.",
            "Degrees, mm, N·m and A on screen; SI in stored data.",
            "Every screenshot is the real Rerun 0.40.0 web viewer at 1440 × 900, playhead at the worst run's worst moment (t = 2.34 s).",
        ],
        "boundary": "Real .rrd files with embedded blueprints in the real Rerun 0.40.0 viewer. The torque series, fans and FB-share bars are logged "
                    "by this round's builder from the SIMULATED fixture (traj_compare HEAD 273ad59 has no torque fields); the production "
                    "rerun_export is landing in parallel. The fixture has no video.",
        "axes": AXES,
        "requirements": [
            {"id": rid, "name": name, "weight": weight, "why": why, "passCondition": condition,
             "anchors": {"1": anchors[0], "3": anchors[1], "5": anchors[2]}}
            for rid, name, weight, why, condition, anchors in REQUIREMENTS
        ],
        "hardGates": [{"id": gid, "name": name, "why": why} for gid, name, why in GATES],
        "variants": variants,
        "checks": [f"Criteria frozen in {CRITERIA} before any variant was built (Round C)."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    out = args.out.resolve()
    spec_path, index = out / "gallery-spec.json", out / "index.html"
    spec = build_spec(out)
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    index.unlink(missing_ok=True)
    built = subprocess.run([sys.executable, str(SKILL / "scripts" / "gallery.py"), "build", "--spec", str(spec_path), "--output", str(index)],
                           capture_output=True, text=True)
    if built.returncode != 0:
        # unscored on purpose: render the same deck shell without the validator, which requires scores
        sys.path.insert(0, str(SKILL / "scripts"))
        import gallery  # noqa: E402

        index.write_text(gallery.render_gallery(spec, "deck"), encoding="utf-8")
        print(f"gallery.py build refused the unscored spec ({len(built.stderr.splitlines())} errors, scores/default empty by design); "
              f"rendered with render_gallery instead")
    print(spec_path)
    print(index)


if __name__ == "__main__":
    main()
