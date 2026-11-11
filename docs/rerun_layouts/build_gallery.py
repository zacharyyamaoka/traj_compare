"""The babble gallery for the five Rerun layouts: spec JSON -> the babble skill's gallery.py -> index.html.

    python3 build_gallery.py --dir <variants out> [--gallery-py <babble>/scripts/gallery.py]

Every image is a real screenshot of the pinned Rerun 0.40.0 web viewer (shoot.py) on the same
recording at the same playhead (t = 2 s), so the variants differ only by their blueprint.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

SCORES_FILE = Path(__file__).with_name("scores.json")
UVX = "uvx --from rerun-sdk==0.40.0 rerun"

REQUIREMENTS = [
    {
        "id": "fr1", "name": "At a glance: is it good, and where is it worst", "weight": 30,
        "why": "The sim2real ask (Nov 11): across a bunch of runs, where was the error highest — before any clicking.",
        "passCondition": "Opening the file answers pass/fail, which run is worst and where on the path/time it peaks, with no tab change.",
        "anchors": {"1": "Needs several tabs or reading raw plots to find the worst run and moment.",
                    "3": "Verdict or worst moment visible on open, but not both.",
                    "5": "Verdict, worst run and worst place on the path all visible on the opening screen."},
    },
    {
        "id": "fr2", "name": "Drill into one run without losing the rest", "weight": 20,
        "why": "The second level Zach named: drill down into a particular run and view that recording.",
        "passCondition": "One run can be isolated (its 3D, video, errors, numbers) in one step, and getting back to all runs is one step.",
        "anchors": {"1": "Isolating a run means hand-hiding series in the viewer.",
                    "3": "Possible through legend toggles or a filtered view, but no per-run page.",
                    "5": "A ready per-run page with its own numbers, 3D, camera and plots, one click from the overview."},
    },
    {
        "id": "fr3", "name": "Says why: joint vs timing vs shape", "weight": 20,
        "why": "A big error is only useful if the view separates a joint fault, a delay (lag) and a path-shape (contour) error.",
        "passCondition": "Per-joint error against tolerance, lag time and contour/cross-track are each reachable and comparable on one clock.",
        "anchors": {"1": "Only a magnitude; cause must be dug out elsewhere.",
                    "3": "The channels exist but are scattered or not on a shared clock.",
                    "5": "Joint, lag and contour channels grouped by the question they answer, zoom-linked, tolerance shown."},
    },
    {
        "id": "fr4", "name": "Video and 3D on the same clock as the error", "weight": 15,
        "why": "Zach wants the overlay video first-class in the stock Rerun video view.",
        "passCondition": "The camera overlay and the 3D robot are visible while reading an error plot, scrubbed by the same playhead.",
        "anchors": {"1": "Video only in a separate tab from every plot.",
                    "3": "Video and plots share a screen in some tabs only.",
                    "5": "Overlay video, 3D and the error stay together on screen throughout."},
    },
    {
        "id": "fr5", "name": "A stock default for any comparison", "weight": 15,
        "why": "This becomes traj_compare's standard dashboard (and the .show() Zach asked for): 2-DOF or 6-DOF, 1 run or 20, video or none.",
        "passCondition": "The layout is generated from the payload without hand-tuning and degrades sensibly with more joints/runs or no video.",
        "anchors": {"1": "Breaks or becomes unreadable outside this fixture.",
                    "3": "Works but one axis (runs or joints) grows the tab bar or crowds the screen.",
                    "5": "Fixed tab count; joints and runs grow inside grids and legends; missing video/3D just drops a view."},
    },
]
GATES = [
    {"id": "g1", "name": "Stock Rerun, one file", "why": "It must open in the pinned stock viewer from one .rrd with the layout embedded — no custom viewer."},
    {"id": "g2", "name": "Degrees and millimetres in every view", "why": "Zach's rule: angles in degrees, tool in mm, in every human-facing view."},
]

VARIANTS = [
    {
        "id": "v1", "slug": "v1-evo-tabs", "name": "evo Toolbox", "accent": "#2a78d6",
        "thesis": "Copy evo's own Rerun layout (Visualization + Raw data tabs) and add one full-screen tab per analysis.",
        "bestWhen": "You already know which analysis you want (APE, joints, video) and want each one big.",
        "losesWhen": "You want the video or 3D beside the plot you are reading; every analysis is a tab switch away from the others.",
        "decisions": [["Organising idea", "one tab per analysis, as evo_ape / evo_traj / evo_res"],
                      ["Opening screen", "target path coloured by the worst run's error, drawn up to the playhead, over the error plot and RMS bars"],
                      ["Raw data", "a DataframeView tab, as evo"]],
        "keepParts": ["growing error-coloured path", "Raw data tab", "RMS-per-run bars"],
        "steps": [(0, "Visualization", "evo's opening screen: the path draws itself as you play, coloured by the worst run's error."),
                  (1, "Trajectories", "Robots and paths with TCP x/y/z, as evo_traj."),
                  (2, "Joint error", "All six joints in degrees; the grey band is the tolerance."),
                  (4, "Video", "Our overlay composite big, the three raw renders beside it."),
                  (6, "Raw data", "Every tool-error channel as a table (evo's Raw Data tab).")],
    },
    {
        "id": "v2", "slug": "v2-stage-questions", "name": "Stage + Questions", "accent": "#eb6834",
        "thesis": "Pin the 3D robot over the camera overlay on the left; the right side is tabs named by the question you are asking.",
        "bestWhen": "Diagnosing a specific comparison: you keep seeing the robot and camera while you work through good? where? which joint? timing or shape?",
        "losesWhen": "Many runs: the stage shows them all at once and there is no per-run page.",
        "decisions": [["Organising idea", "tabs are questions, not data types"],
                      ["Always visible", "3D stage and camera overlay"],
                      ["Opening tab", "scorecard, worst-joint and tool error with tolerance bands, event log"]],
        "keepParts": ["pinned stage", "question-named tabs", "scorecard + events on the first tab"],
        "steps": [(0, "Is it good?", "Scorecard worst-first, worst-joint and tool error against the tolerance band, events."),
                  (1, "Where?", "Error along the belt, across it and up — in the conveyor's own frame."),
                  (2, "Which joint?", "Six joint errors in degrees with tolerance bands."),
                  (3, "Timing or shape?", "Lag time (late along the path) against contour error (off the path)."),
                  (4, "Signals", "Nested tabs: position, velocity, torque per joint.")],
    },
    {
        "id": "v3", "slug": "v3-run-tabs", "name": "Run Tabs", "accent": "#2f9e44",
        "thesis": "Overview first, then one tab per run: 'All runs' says which run to open, each run tab is that run's own cockpit.",
        "bestWhen": "Many repeats of one trajectory (sim vs N real runs): find the bad run, open it, see its camera, 3D and numbers alone.",
        "losesWhen": "Twenty runs: the tab bar overflows; and comparing two specific runs side by side needs the overview, not the tabs.",
        "decisions": [["Organising idea", "overview + detail (Shneiderman): All runs, then one tab per run"],
                      ["Per-run page", "this run vs target in 3D, its camera, its numbers, its errors with tolerance"],
                      ["Overview", "scorecard worst-first, RMS bars, every run's error, worst-run heat path"]],
        "keepParts": ["All runs overview", "per-run notes page", "worst-run heat path"],
        "steps": [(0, "All runs", "Scorecard sorted worst first, RMS bars, every run's error and where on the path it peaks."),
                  (5, "Real #4 (worst)", "The worst run alone: its 3D against the target, its errors against tolerance, its numbers."),
                  (4, "Real #3", "The best real run, same page, for contrast."),
                  (1, "Sim", "The sim's page: well inside every band."),
                  (2, "Real #1 (camera)", "The run with a camera: its own video beside its 3D.")],
    },
    {
        "id": "v4", "slug": "v4-signal-inspector", "name": "Signal Inspector", "accent": "#8e5bd1",
        "thesis": "Simulink Data Inspector / PlotJuggler: one tab per joint, each a stack of position, error, velocity and torque on one clock, with 3D and video at the side.",
        "bestWhen": "Tuning one joint's controller: the error lines up under the position, velocity and torque that caused it.",
        "losesWhen": "The first question is 'which run, where on the path' — the joint tabs answer 'how', not 'where'.",
        "decisions": [["Organising idea", "one tab per signal (joint), stacked plots sharing an x-axis"],
                      ["Always visible", "3D, camera overlay, event log"],
                      ["Tool tab", "position, rotation, contour and lag time stacked"]],
        "keepParts": ["per-joint stacked plots", "event log under the camera", "Tool (TCP) stack"],
        "steps": [(1, "shoulder lift", "Position, error with band, velocity and torque stacked on one clock."),
                  (2, "elbow", "Same stack for the elbow; the side panel never moves."),
                  (3, "wrist 1", "The joint with the deepest excursion past the band."),
                  (0, "shoulder pan", "A joint that stays inside its band."),
                  (6, "Tool (TCP)", "Position, rotation, contour and lag time stacked.")],
    },
    {
        "id": "v5", "slug": "v5-replay", "name": "Replay", "accent": "#c22f6e",
        "thesis": "No tabs, video first: the camera overlay big, the worst-error path beside it, and two strips that scroll with the playhead.",
        "bestWhen": "Watching a run back like a match replay, and showing it to someone who has not seen the plots.",
        "losesWhen": "Diagnosis: no per-joint view, no per-run page, and the strips only show 1.5 s around the playhead.",
        "decisions": [["Organising idea", "one screen, no tabs, the playhead is the navigation"],
                      ["Strips", "tool and worst-joint error in a 1.5 s window that follows the playhead"],
                      ["3D", "robots plus the target path coloured by the worst run's error"]],
        "keepParts": ["big overlay video", "scrolling error strips", "events beside the strips"],
        "steps": [(0, "t = 0.6 s", "The start: the peak at launch is in the strips' window.", "@0.6s"),
                  (0, "t = 2.0 s", "Mid-run: the strips have scrolled; the video and 3D follow.", ""),
                  (0, "t = 3.4 s", "The second peak, near the end of the belt segment.", "@3.4s")],
    },
]


def preview_html(variant: dict, shots: dict[int, str]) -> str:
    """A replica tab bar (each button jumps the story to that tab) over the real screenshots."""

    states = [f"s{index}" for index in range(len(variant["steps"]))]
    rules = "".join(
        f'.prototype[data-story-state="{state}"] img.rr-shot.rr-{variant["id"]}-{state}{{display:block!important}}'
        f'.prototype[data-story-state="{state}"] .rr-tab[data-story-to="{state}"]{{background:#fff;color:#111;box-shadow:0 0 0 1px #c9c9c9}}'
        for state in states
    )
    buttons = "".join(
        f'<button class="rr-tab" data-story-to="{state}">{html.escape(step[1])}</button>'
        for state, step in zip(states, variant["steps"])
    )
    images = "".join(
        f'<img class="rr-shot rr-{variant["id"]}-{state}" src="{html.escape(shots[i])}" alt="{html.escape(step[1])} — real Rerun 0.40 screenshot" loading="lazy">'
        for i, (state, step) in enumerate(zip(states, variant["steps"]))
    )
    style = (
        "<style>.rr-wrap{background:#f4f4f2;border-radius:8px;overflow:hidden}"
        ".rr-bar{display:flex;flex-wrap:wrap;gap:4px;padding:6px;background:#ececea;font:12px system-ui}"
        ".rr-tab{border:0;border-radius:5px;padding:4px 9px;background:transparent;color:#555;cursor:pointer;font:inherit}"
        ".rr-tab:hover{background:#fff}.prototype img.rr-shot{display:none!important;width:100%;height:auto;max-width:100%}" + rules + "</style>"
    )
    return f'{style}<div class="rr-wrap"><div class="rr-bar">{buttons}</div>{images}</div>'


def _media(root: Path, slug: str, rrd: Path) -> list[dict]:
    media = []
    clip = root / "media" / f"{slug}-hero.mp4"
    if clip.is_file():
        media.append({
            "label": "Playing in the real viewer",
            "caption": "Stop-motion of the pinned Rerun web viewer: the playhead stepped 0.1 → 4.5 s, one screenshot per step.",
            "html": (f'<video src="media/{clip.name}" poster="media/{slug}-hero-poster.png" autoplay muted loop playsinline controls '
                     f'style="width:100%;display:block"><img src="media/{slug}-hero.gif" alt="playback"></video>'),
        })
    media.append({"label": "Open in the real viewer", "caption": "One command opens this layout in the pinned native viewer.",
                  "html": f'<pre style="white-space:pre-wrap;font-size:12px;margin:0;padding:12px">{html.escape(UVX)} {html.escape(str(rrd))}</pre>'})
    return media


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--gallery-py", type=Path, default=Path.home() / ".claude-dfuture/skills/babble/scripts/gallery.py")
    args = parser.parse_args()
    root = args.dir.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    scores = json.loads(SCORES_FILE.read_text())
    variants = []
    for variant in VARIANTS:
        slug = variant["slug"]
        rrd = root / manifest[slug]["rrd"]
        shots = {}
        for index, step in enumerate(variant["steps"]):
            suffix = step[3] if len(step) > 3 else ""
            shots[index] = f"shots/{slug}--{step[0]}{suffix}.png"
            if not (root / shots[index]).is_file():
                raise SystemExit(f"missing screenshot {shots[index]}")
        score = scores[variant["id"]]
        variants.append({
            "id": variant["id"], "name": variant["name"], "thesis": variant["thesis"], "accent": variant["accent"],
            "bestWhen": variant["bestWhen"], "losesWhen": variant["losesWhen"],
            "decisions": [{"label": label, "value": value} for label, value in variant["decisions"]],
            "keepParts": variant["keepParts"],
            "proof": [f"Real Rerun 0.40.0 web viewer screenshots of {rrd.name} ({rrd.stat().st_size / 1e6:.1f} MB), playhead set to 2.0 s, layout embedded in the file.",
                      f"Open it yourself: {UVX} {rrd}"],
            "scores": score["scores"], "gateResults": score["gates"],
            "previewLabel": "real Rerun screenshots — click a tab",
            "story": {"title": "Walk the tabs", "steps": [
                {"label": step[1], "caption": step[2], "state": f"s{index}", "target": f'.rr-tab[data-story-to="s{index}"]'}
                for index, step in enumerate(variant["steps"])]},
            "media": _media(root, slug, rrd),
            "preview": preview_html(variant, shots),
        })
    spec = {
        "schemaVersion": 3,
        "title": "Five Rerun layouts for traj_compare",
        "kicker": "Babble · 5 blueprints · one recording",
        "brief": ("The stock Rerun viewer as traj_compare's first-class review surface: one comparison (UR5e conveyor — target, "
                  "sim and 5 stand-in real runs, with our own camera overlay video) under five different embedded blueprints, "
                  "making better use of tabs, with evo's own Rerun layout as the reference."),
        "count": len(variants),
        "defaultId": scores["default"]["id"], "defaultWhy": scores["default"]["why"],
        "decisionHinge": scores["default"]["hinge"],
        "invariants": ["Same .rrd data in every variant (only the blueprint differs)", "Pinned Rerun 0.40.0",
                       "Angles in degrees, tool in mm", "One colour per run in every view", "Playhead at 2.0 s in every screenshot"],
        "boundary": ("Prototype blueprints in a script (docs/rerun_layouts/), not the shipped default. 'Real' is the stand-in plant and "
                     "the camera is a synthetic render; the overlay is our own ffmpeg composite. Screenshots are the real web viewer."),
        "axes": [{"name": "Organising idea", "values": ["analysis type (evo)", "question", "run", "signal (joint)", "none — playhead"]},
                 {"name": "Always visible", "values": ["nothing (full-screen tabs)", "3D + camera", "nothing (per-run cockpit)", "3D + camera + events", "everything"]}],
        "requirements": REQUIREMENTS, "hardGates": GATES, "variants": variants,
    }
    spec_path = root / "gallery-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    # gallery.py refuses to overwrite; build beside it and swap in, so a rebuild is one command
    fresh = root / "index.new.html"
    fresh.unlink(missing_ok=True)
    subprocess.run(["python3", str(args.gallery_py), "build", "--spec", str(spec_path), "--output", str(fresh)], check=True)
    fresh.replace(root / "index.html")
    subprocess.run(["python3", str(args.gallery_py), "check", "--input", str(root / "index.html"), "--strict"], check=True)
    print(root / "index.html")


if __name__ == "__main__":
    main()
