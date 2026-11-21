#!/usr/bin/env python3
"""Shoot the five outer-view prototypes and build the babble gallery (round 2026-11-20).

    python3 build_gallery.py            # shoot every state (headless Chrome, one page at a time), then build
    python3 build_gallery.py --no-shoot # rebuild the gallery from the stills already shot
    python3 build_gallery.py --shoot-only

Stills: /home/bam/traj_compare/reports/media/outer-view-proposals-2026-11-20/shots/*.png (gitignored, raw evidence).
Gallery: /home/bam/traj_compare/reports/media/outer-view-proposals-2026-11-20.html, built by the babble skill's
gallery.py (deck shell) from gallery-spec.json written here. Each hero is the variant's walkthrough as real stills,
with a click target over the control that leads to the next state; the live exhibit is an <iframe> of vN.html.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MEDIA = REPO / "reports" / "media"
SHOTS = MEDIA / "outer-view-proposals-2026-11-20" / "shots"
OUT = MEDIA / "outer-view-proposals-2026-11-20.html"
# The built spec embeds every still as a data URI (~1.8 MB), so it lives beside the stills, out of git, not in docs/.
SPEC = MEDIA / "outer-view-proposals-2026-11-20" / "gallery-spec.json"
SKILL = Path.home() / ".claude-jidoka" / "skills" / "babble" / "scripts" / "gallery.py"
REL = "../../docs/proposals/outer-view-2026-11-20/"   # the gallery's relative path to the prototypes
NICE = ["taskset", "-c", "2-5,16,17", "nice", "-n", "19"]
U = lambda name, frag: f"file://{HERE}/{name}{frag}"  # noqa: E731


def rect(css: str, nth: int = 0) -> dict:
    return {"eval": f"JSON.stringify((function(){{var el=document.querySelectorAll({json.dumps(css)})[{nth}];"
                    f"if(!el)return null;var r=el.getBoundingClientRect();return {{x:r.left,y:r.top,w:r.width,h:r.height}};}})())"}


# Every variant's walkthrough: (state, label, caption, url, actions, next-control css, nth). The next control's rect, measured
# in that state, becomes the still's click target to the following state; the last state marks the run link instead.
STATES = {
    "v1": [
        ("s1", "read the overview", "One row per config, ranked by tool RMS at full speed on the chosen split, ×best and a log bar for the distance; every KPI’s curve against speed beside it; the matrix below ranks every split at once.",
         U("v1.html", "#/overview"), [], 'button.chip[data-g="2"]', 0),
        ("s2", "switch dataset · split", "The chip filter swaps the table to workspace-v2 dev: two configs ran there, so the league is two rows and the verdict says so.",
         U("v1.html", "#/overview?g=2"), [], 'tr[data-key="ctc_model_err|sim"] .ov-drill', 0),
        ("s3", "worst targets, then a run", "One click on a row: that config’s worst targets on that split at full speed, worst first; Target ↗ and run ↗ open the real site.",
         U("v1.html", "#/targets?cfg=ctc_model_err%7Csim&g=2&v=4"), [], ".ov-runlink", 0),
    ],
    "v2": [
        ("s1", "read the overview", "Tool RMS (log) against energy per task; each config a path from speed 0.1 to 1.0; at speed 1.0 the frontier is ctc_tuned and id_pd, and the list says what dominates the rest.",
         U("v2.html", "#/overview"), [], '#v2-speed [data-v="1"]', 0),
        ("s2", "change the speed", "At speed 0.25 the frontier collapses to id_pd alone: it beats every config on both axes.",
         U("v2.html", "#/overview?v=1"), [], '#v2-y [data-y="jerk"]', 0),
        ("s3", "swap the cost axis", "Tool jerk RMS as the cost: still id_pd alone on the frontier at 0.25.",
         U("v2.html", "#/overview?v=1&y=jerk"), [], '.v2-list tr[data-key="ctc_model_err|sim"]', 0),
        ("s4", "worst targets, then a run", "Click a config (or a dot): its worst targets at that split and speed, then the run report.",
         U("v2.html", "#/targets?cfg=ctc_model_err%7Csim&g=0&v=1"), [], ".ov-runlink", 0),
    ],
    "v3": [
        ("s1", "read the overview", "Today’s 20 bar charts as 20 small line charts on one screen: rows = KPI × split, columns = dataset, one shared legend, one y scale per row (log for RMS and jerk).",
         U("v3.html", "#/overview"), [], '.v3-legend [data-key="id_pd|sim"]', 0),
        ("s2", "focus one config", "Clicking id_pd in the legend fades the others in all 20 charts; hovering one chart moves the cursor in all of them and reads out the values with n.",
         U("v3.html", "#/overview?focus=id_pd%7Csim"), [{"hover": ".v3-cell >> nth=2"}], ".v3-cell", 2),
        ("s3", "worst targets, then a run", "Clicking a chart drills to the focused config’s worst targets on that dataset · split at the speed under the cursor.",
         U("v3.html", "#/targets?cfg=id_pd%7Csim&g=4&v=2"), [], ".ov-runlink", 0),
    ],
    "v4": [
        ("s1", "read the overview", "All 1006 targets as columns, grouped by dataset and speed and sorted hardest first; one row per config, colour = log tool RMS; the bottom strip is the best config per target.",
         U("v4.html", "#/overview"), [], '[data-c="ratio"]', 0),
        ("s2", "colour by ratio to the best", "Colour = each config ÷ the best config on that target: white is best. Hovering a column names the target and every config’s value; a click opens its real Target level.",
         U("v4.html", "#/overview?c=ratio"), [{"hoverAt": [420, 330]}], ".v4-labels .v4-lab", 5),
        ("s3", "worst targets, then a run", "Clicking a config’s name: its worst targets relative to the best config on each, then the run report.",
         U("v4.html", "#/targets?cfg=menagerie_stock%7Csim&sort=best"), [], ".ov-runlink", 0),
    ],
    "v5": [
        ("s1", "read the overview", "Baseline id_pd (the default: lowest median tool RMS on the 504 targets all four ran). Each other config is a histogram of its per-target ratio to it, with “better on k of n” and the ratio against speed.",
         U("v5.html", "#/overview"), [], '[data-b="ctc_tuned|sim"]', 0),
        ("s2", "change the baseline", "Against ctc_tuned, id_pd is better on 377 of 504 shared targets (median 0.5×) — but its ratio climbs to 1.08× at full speed.",
         U("v5.html", "#/overview?b=ctc_tuned%7Csim"), [], ".v5-row:not(.head)", 0),
        ("s3", "worst targets, then a run", "Clicking a row: that config’s targets sorted by its ratio to the baseline, worst first, then the run report.",
         U("v5.html", "#/targets?cfg=id_pd%7Csim&sort=vs&vs=ctc_tuned%7Csim"), [], ".ov-runlink", 0),
    ],
}
TAG_BELOW = {"v4-s2", "v3-s2"}
GENERAL = {v: [(f"{v}-bam_fb", U(f"{v}.html", "?site=bam_fb#/overview")), (f"{v}-pendulum", U(f"{v}.html", "?site=pendulum#/overview"))] for v in STATES}


def shoot() -> dict:
    jobs = []
    for variant, states in STATES.items():
        for state, _, _, url, actions, css, nth in states:
            jobs.append({"name": f"{variant}-{state}", "url": url, "actions": actions + [rect(css, nth)]})
        for name, url in GENERAL[variant]:
            jobs.append({"name": name, "url": url})
    job_file = SHOTS.parent / "jobs.json"
    SHOTS.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps(jobs, indent=1))
    out = subprocess.run(NICE + ["node", str(HERE / "shoot.cjs"), str(job_file), str(SHOTS)], capture_output=True, text=True, check=True)
    results = {}
    for line in out.stdout.splitlines():
        row = json.loads(line)
        results[row["name"]] = row
        flag = " ERRORS " + str(row["errors"]) if row["errors"] else ""
        net = " NETWORK " + str(row["network"]) if row["network"] else ""
        print(f"  {row['name']}: page {row['height']['scroll']} px{flag}{net}")
    (SHOTS.parent / "shoot-results.json").write_text(json.dumps(results, indent=1))
    return results


def webp(name: str, quality: int = 38, width: int | None = None) -> str:
    image = Image.open(SHOTS / f"{name}.png").convert("RGB")
    if width and image.width != width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()


def hero(variant: str, results: dict, accent: str) -> str:
    """The walkthrough as stills: one 1440 x 900 still per state, a click target over the control that leads on."""
    states = STATES[variant]
    css = [
        ".oh{position:relative;width:1440px;height:900px;overflow:hidden;background:#f4f4f2}",
        ".oh .st{display:none;position:absolute;inset:0}",
        ".oh .st img{display:block;width:1440px;height:900px}",
        ".prototype:not([data-story-state]) .oh .st-s1{display:block}",
        f".oh .hot{{position:absolute;border:2px dashed {accent};border-radius:6px;background:rgba(255,255,255,0);cursor:pointer;padding:0;margin:0}}",
        f".oh .hot:hover{{background:rgba(118,103,198,.10)}}",
        f".oh .mark{{position:absolute;border:2px solid {accent};border-radius:6px;pointer-events:none}}",
        ".oh .tag{position:absolute;transform:translateY(-100%);margin-top:-4px;font:600 12px/1.3 -apple-system,Segoe UI,Roboto,sans-serif;"
        f"color:#fff;background:{accent};padding:2px 7px;border-radius:4px;white-space:nowrap;pointer-events:none}}",
    ]
    parts = []
    for k, (state, label, _, _, _, _, _) in enumerate(states):
        css.append(f'.prototype[data-story-state="{state}"] .oh .st-{state}{{display:block}}')
        r = json.loads(results[f"{variant}-{state}"]["results"][-1] or "null")
        pad = 4
        box = f"left:{r['x'] - pad:.0f}px;top:{r['y'] - pad:.0f}px;width:{r['w'] + 2 * pad:.0f}px;height:{r['h'] + 2 * pad:.0f}px" if r else ""
        def tag_at(text: str) -> str:
            # Anchor the label to the box's right edge when it would run off the 1440 px still; below the box where the
            # row above it carries content the label would hide (V4's config names).
            if not r:
                return ""
            wide = 7.2 * len(text) + 16
            side = f"right:{1440 - (r['x'] + r['w'] + pad):.0f}px" if r["x"] - pad + wide > 1436 else f"left:{r['x'] - pad:.0f}px"
            if f"{variant}-{state}" in TAG_BELOW:
                return f'<span class="tag" style="{side};top:{r["y"] + r["h"] + pad + 4:.0f}px;transform:none;margin-top:0">{text}</span>'
            return f'<span class="tag" style="{side};top:{r["y"] - pad:.0f}px">{text}</span>'

        if k + 1 < len(states):
            nxt = states[k + 1]
            control = f'<button class="hot" data-story-to="{nxt[0]}" style="{box}" title="click: {nxt[1]}" aria-label="{nxt[1]}"></button>'
            tag = tag_at(f"click → {nxt[1]}")
        else:
            control = f'<span class="mark" data-mark="{state}" style="{box}"></span>'
            tag = tag_at("run ↗ opens the real report (live exhibit)")
        parts.append(f'<div class="st st-{state}"><img alt="{variant.upper()} · {label}" width="1440" height="900" src="{webp(f"{variant}-{state}")}">{control}{tag}</div>')
    return f"<style>{''.join(css)}</style><div class=\"oh\">{''.join(parts)}</div>"


def live(variant: str, name: str) -> str:
    return (
        '<div style="width:1440px;font:12px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;color:#52514e">'
        f'<div style="padding:4px 2px 6px">Live prototype on the real UR5e data · reaches the walkthrough’s states through its own controls (not tied to the stepper) · '
        f'<a href="{REL}{variant}.html" target="_blank" rel="noopener">open {variant}.html in its own tab ↗</a></div>'
        f'<iframe src="{REL}{variant}.html" title="{name}, live" width="1440" height="900" '
        'style="display:block;width:1440px;height:900px;border:1px solid #dddcd6;border-radius:6px;background:#f4f4f2"></iframe></div>'
    )


def still(name: str, alt: str, width: int = 1000) -> str:
    # WHY 1000 px at q32: ten generality stills must fit the 1.9 MB desktop-preview budget beside sixteen full-size heroes.
    return f'<img alt="{alt}" width="{width}" src="{webp(name, 32, width)}">'


def main() -> int:
    results = shoot() if "--no-shoot" not in sys.argv else json.loads((SHOTS.parent / "shoot-results.json").read_text())
    if "--shoot-only" in sys.argv:
        return 0
    content = json.loads((HERE / "gallery-content.json").read_text(encoding="utf-8"))
    for variant in content["variants"]:
        vid = variant["id"]
        variant["preview"] = hero(vid, results, variant["accent"])
        variant["story"] = {
            "title": "Walk the overview to a run",
            "steps": [
                {"label": label, "caption": caption, "state": state,
                 "target": f'[data-story-to="{STATES[vid][k + 1][0]}"]' if k + 1 < len(STATES[vid]) else f'[data-mark="{state}"]'}
                for k, (state, label, caption, *_rest) in enumerate(STATES[vid])
            ],
        }
        variant["media"] = [
            {"label": "Live prototype", "caption": "The real page in an iframe from file:// — every control works; Target ↗ and run ↗ open the bench’s server on 127.0.0.1:8779.", "html": live(vid, variant["name"])},
            {"label": "Same page · BAM FB", "caption": variant["generality"]["bam_fb"], "html": still(f"{vid}-bam_fb", f"{variant['name']} on BAM FB")},
            {"label": "Same page · pendulum", "caption": variant["generality"]["pendulum"], "html": still(f"{vid}-pendulum", f"{variant['name']} on the pendulum")},
        ]
        del variant["generality"]
    SPEC.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    if OUT.exists():
        OUT.unlink()
    subprocess.run([sys.executable, str(SKILL), "build", "--spec", str(SPEC), "--output", str(OUT), "--strict"], check=True)
    subprocess.run([sys.executable, str(SKILL), "check", "--input", str(OUT), "--strict"], check=True)
    print(f"{OUT}: {OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
