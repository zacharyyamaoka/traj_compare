#!/usr/bin/env python3
"""The prune surface for the dashboard-pattern round (babble, 2026-11-24): one deck-shell gallery of the five
ways to do "filter rail + tabbed dashboards" in data-ui.

    python3 /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/build_gallery.py

Reads criteria.json (frozen before the lanes), gallery-content.json (names, theses, scores: written after every
variant was built and checked), each variant's story.json + shots/v<N>/step-*.png (check.cjs --shots) and
shots/v<N>/session.webm. Writes the media next to the report (JPEG stills, an MP4 per walkthrough) under
/home/bam/traj_compare/reports/media/dashboard-pattern-proposals-2026-11-24/ and the gallery beside it, so the page stays
small and opens from file://. Stdlib + ffmpeg + Pillow-free (ffmpeg does the JPEGs too).
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "dashboard-pattern-proposals-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/.claude-dfuture/skills/babble/scripts/gallery.py")
SHOTS = HERE / "shots"


def jpeg(src: Path, dst: Path, box: dict | None = None, colour: str = "#e05a3f", width: int = 1440,
         quality: int = 4) -> None:
    """The still as a JPEG, with the control its step demonstrates boxed in the variant's accent colour.

    WHY burned in: an overlay <div> inside the gallery's shadow-root preview collapsed to 0 px high under the shell's
    stylesheet; a box in the pixels can't drift from the picture."""
    chain = []
    if box:
        x, y = max(0, round(box["x"]) - 3), max(0, round(box["y"]) - 3)
        w, h = round(box["width"]) + 6, max(round(box["height"]) + 6, 12)
        chain.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={colour}@0.95:t=4")
    chain.append(f"scale={width}:-2")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", ",".join(chain), "-q:v", str(quality),
                    str(dst)], check=True)


def mp4(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=1280:-2,fps=20", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", "-crf", "32", "-movflags", "+faststart", "-an", str(dst)],
                   check=True)


def stepped_preview(variant: str, steps: list[dict]) -> str:
    """Every walkthrough still in one preview; the stepper's state (s1, s2, ...) shows one. The box of the control that
    step demonstrates (check.cjs measured it with getBoundingClientRect) is drawn into the still itself (jpeg)."""
    css = ["<style>.wt{position:relative;line-height:0}.wt img.f{width:100%;max-width:100%;height:auto;display:none}",
           ".wt .chips{position:absolute;left:8px;bottom:8px;display:flex;gap:6px;line-height:1.2}",
           ".wt .chips button{font:12px system-ui;padding:3px 8px;border-radius:12px;border:1px solid #bbb;",
           "background:rgba(255,255,255,.92);cursor:pointer}"]
    body = []
    for k, step in enumerate(steps, start=1):
        state = f"s{k}"
        css.append(f'[data-story-state="{state}"] .wt img.f[data-s="{state}"]{{display:block}}')
        css.append(f'[data-story-state="{state}"] .wt .chips button[data-story-to="{state}"]'
                   '{background:#222;color:#fff;border-color:#222}')
        body.append(f'<img class="f" data-s="{state}" src="{SLUG}/{variant}-step-{k}.jpg" '
                    f'alt="{html.escape(step["label"])}">')
    chips = "".join(f'<button data-story-to="s{k}">{k} · {html.escape(step["label"])}</button>'
                    for k, step in enumerate(steps, start=1))
    css.append("</style>")
    return "".join(css) + '<div class="wt">' + "".join(body) + f'<div class="chips">{chips}</div></div>'


GATES = {"g1": ("P1",), "g2": ("P2",), "g3": ("P3",), "g4": ("P4",), "g5": ("P5", "P6", "P7")}


def gate_results(variant: str) -> dict:
    """The hard gates straight from check.cjs's JSON (shots/<v>.check.json), never typed by hand."""
    check = json.loads((SHOTS / f"{variant}.check.json").read_text())
    by_id = {r["gate"].split(" ")[0]: r for r in check["results"]}
    out = {}
    for gate, ids in GATES.items():
        rows = [by_id[i] for i in ids]
        evidence = " · ".join(f'{r["gate"]}: {json.dumps(r["detail"], separators=(", ", ": "))[:160]}' for r in rows)
        out[gate] = {"pass": all(r["ok"] for r in rows), "evidence": f"check.cjs — {evidence}"}
    return out


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        steps = json.loads((SHOTS / vid / "story.shot.json").read_text())
        for k in range(1, len(steps) + 1):
            jpeg(SHOTS / vid / f"step-{k}.png", MEDIA / f"{vid}-step-{k}.jpg", steps[k - 1].get("box"), entry["accent"])
        media = list(entry.get("media", []))
        embed = SHOTS / vid / "embed.png"
        if embed.exists():
            jpeg(embed, MEDIA / f"{vid}-embed.jpg")
            media.insert(0, {"label": "Dropped into a host app",
                             "caption": "The same component in a fake host app's 1000 × 680 slot (host header and sidebar around it): check P4 measured that nothing draws outside the slot.",
                             "html": f'<img src="{SLUG}/{vid}-embed.jpg" alt="embedded in a host app">'})
        webm = SHOTS / vid / "session.webm"
        if webm.exists():
            mp4(webm, MEDIA / f"{vid}-session.mp4")
            media.append({"label": "The whole check, recorded",
                          "caption": "check.cjs driving the live prototype: every gate, then the walkthrough (headless, 1440 × 900).",
                          "html": f'<video src="{SLUG}/{vid}-session.mp4" muted loop playsinline controls></video>'})
        variants.append({
            **{key: value for key, value in entry.items() if key != "media"},
            "gateResults": gate_results(vid),
            "previewLabel": "walkthrough · real prototype captures",
            "preview": stepped_preview(vid, steps),
            "story": {"title": "Walk it", "steps": [
                {"label": step["label"], "caption": step["caption"], "state": f"s{k}",
                 "target": f'.chips button[data-story-to="s{k}"]'}
                for k, step in enumerate(steps, start=1)]},
            "media": media,
        })
    spec = {
        "schemaVersion": 3,
        "title": content["title"],
        "kicker": content["kicker"],
        "brief": content["brief"],
        "count": len(variants),
        "defaultId": content["defaultId"],
        "defaultWhy": content["defaultWhy"],
        "decisionHinge": content["decisionHinge"],
        "invariants": content["invariants"],
        "boundary": content["boundary"],
        "axes": content["axes"],
        "requirements": criteria["requirements"],
        "hardGates": criteria["hardGates"],
        "variants": variants,
    }
    SPEC.write_text(json.dumps(spec, indent=1))
    # WHY a temp file: gallery.py refuses to overwrite, and the previous build must stay until the new one exists
    fresh = GALLERY.with_suffix(".next.html")
    fresh.unlink(missing_ok=True)
    subprocess.run(["python3", str(BABBLE), "build", "--spec", str(SPEC), "--output", str(fresh)], check=True)
    fresh.replace(GALLERY)
    subprocess.run(["python3", str(BABBLE), "check", "--input", str(GALLERY), "--strict"], check=True)
    print(GALLERY, f"{GALLERY.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
