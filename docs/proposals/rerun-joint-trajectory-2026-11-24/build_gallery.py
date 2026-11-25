#!/usr/bin/env python3
"""The prune surface for the Rerun JointTrajectory round (babble, 2026-11-24): one deck-shell gallery of the five looks.

    python3 /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/build_gallery.py

Reads criteria.json (frozen before the lanes), gallery-content.json (names, theses, scores, gate evidence: written after
every proposal was built and re-opened by the dispatcher) and each lane's exact-time stills in shots/ (taken in the real
Rerun 0.40 web viewer by shoot.cjs). Writes JPEG stills beside the report in
/home/bam/traj_compare/reports/media/rerun-joint-trajectory-proposals-2026-11-24/ and the gallery next to that folder.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "rerun-joint-trajectory-proposals-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/.claude-dfuture/skills/babble/scripts/gallery.py")

# The walkthrough every variant shows, at the same moments of the same two trajectories (the lane's exact-time stills)
STEPS = [("Start of the tour (0.4 s)", "workspace-dev-029, a 3.2 s multi-waypoint tour, 0.4 s in."),
         ("Mid-motion (1.8 s)", "The same tour at 1.8 s: the arm, the tool's path so far and every plot's cursor at one instant."),
         ("End of the tour", "The tour's last pose."),
         ("A short A to B (0.9 s)", "workspace-dev-003, a 1.8 s joint move, halfway.")]
FILES = {
    "r1": ["at-time/dev-029-1-t0.4.png", "at-time/dev-029-2-t1.8.png", "at-time/dev-029-3-t3.2.png", "at-time/dev-003-1-t0.9.png"],
    "r2": ["dev-029-1-t0.4.png", "dev-029-2-t1.8.png", "dev-029-3-t3.2.png", "dev-003-1-t0.9.png"],
    "r3": ["dev-029-1-t0.4.png", "dev-029-2-t1.8.png", "dev-029-3-tend.png", "dev-003-1-t0.9.png"],
    "r4": ["dev-029-1-t0.4.png", "dev-029-2-t1.8.png", "dev-029-3-tend.png", "dev-003-1-t0.9.png"],
    "r5": ["dev-029-at-0.4.png", "dev-029-at-1.8.png", "dev-029-at-end.png", "dev-003-at-0.9.png"],
}
EXTRA = {  # supporting exhibits: (file, label, caption)
    "r1": [("tabs/dev-029-how-fast-1-t1.8.png", "How fast? tab", "Speed per joint against ±max velocity, the dark lines and red strips beyond."),
           ("tabs/dev-029-tool-1-t1.8.png", "Where does the tool go? tab", "The tool's x, y, z and speed.")],
    "r2": [("dev-029-joints-1-t1.8.png", "Joints tab", "All six q in degrees on one plot, each joint's limits in its colour."),
           ("dev-029-speed-1-t1.8.png", "Speed tab", "qd against ±max velocity."),
           ("dev-029-data-1-t1.8.png", "Data tab", "The samples as a table that follows the playhead.")],
    "r4": [("dev-029-tab-qd-1-t1.8.png", "qd tab of the bottom strip", "Speeds of every joint on one plot.")],
    "r5": [("dev-029-tab-positions-at-1.8.png", "Positions tab", "The existing per-field plots stay one click away, now in degrees."),
           ("fallback-3-joints-urdf-limits-at-1.8.png", "Another arm", "A made-up 3-joint arm with no limits and no tool: the cards adapt."),
           ("stock-today-dev-029.png", "Before: robot_msgs' show() today", "What robot_msgs draws for this trajectory now, without a robot.")],
}


def jpeg(src: Path, dst: Path, width: int = 1600) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)],
                   check=True)


def stepped_preview(vid: str, names: list[str]) -> str:
    css = ["<style>.wt{position:relative;line-height:0}.wt img.f{width:100%;max-width:100%;height:auto;display:none}",
           ".wt .chips{position:absolute;left:8px;bottom:8px;display:flex;gap:6px;line-height:1.2}",
           ".wt .chips button{font:12px system-ui;padding:3px 8px;border-radius:12px;border:1px solid #bbb;",
           "background:rgba(255,255,255,.92);cursor:pointer}"]
    body = []
    for k, (label, _) in enumerate(STEPS, start=1):
        state = f"s{k}"
        css.append(f'[data-story-state="{state}"] .wt img.f[data-s="{state}"]{{display:block}}')
        css.append(f'[data-story-state="{state}"] .wt .chips button[data-story-to="{state}"]{{background:#222;color:#fff;border-color:#222}}')
        body.append(f'<img class="f" data-s="{state}" src="{SLUG}/{vid}-step-{k}.jpg" alt="{html.escape(label)}">')
    chips = "".join(f'<button data-story-to="s{k}">{k} · {html.escape(label)}</button>' for k, (label, _) in enumerate(STEPS, start=1))
    css.append("</style>")
    return "".join(css) + '<div class="wt">' + "".join(body) + f'<div class="chips">{chips}</div></div>'


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        for k, name in enumerate(FILES[vid], start=1):
            jpeg(SHOTS / vid / name, MEDIA / f"{vid}-step-{k}.jpg")
        media = []
        for n, (name, label, caption) in enumerate(EXTRA.get(vid, []), start=1):
            jpeg(SHOTS / vid / name, MEDIA / f"{vid}-extra-{n}.jpg")
            media.append({"label": label, "caption": caption, "html": f'<img src="{SLUG}/{vid}-extra-{n}.jpg" alt="{html.escape(label)}">'})
        variants.append({**entry, "previewLabel": "real Rerun 0.40 web viewer · exact-time stills",
                         "preview": stepped_preview(vid, FILES[vid]),
                         "story": {"title": "Walk it", "steps": [
                             {"label": label, "caption": caption, "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                             for k, (label, caption) in enumerate(STEPS, start=1)]},
                         "media": media})
    spec = {"schemaVersion": 3, **{key: content[key] for key in ("title", "kicker", "brief", "defaultId", "defaultWhy",
                                                                  "decisionHinge", "invariants", "boundary", "axes")},
            "count": len(variants), "requirements": criteria["requirements"], "hardGates": criteria["hardGates"],
            "variants": variants}
    SPEC.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    fresh = GALLERY.with_suffix(".next.html")
    fresh.unlink(missing_ok=True)
    subprocess.run(["python3", str(BABBLE), "build", "--spec", str(SPEC), "--output", str(fresh)], check=True)
    fresh.replace(GALLERY)
    subprocess.run(["python3", str(BABBLE), "check", "--input", str(GALLERY), "--strict"], check=True)
    print(GALLERY, f"{GALLERY.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
