#!/usr/bin/env python3
"""The pick page for the Rerun pick-variants round (babble, 2026-11-24): five variants of Zach's pick (R3 + his tabs).

    python3 /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/build_gallery.py

Reads criteria.json (frozen before V2-V5 were built), gallery-content.json (names, theses, exhibits, scores, gate
evidence: written after every variant was built, re-filmed by an independent checker and looked at by the dispatcher)
and the frames each variant filmed in the real Rerun 0.40 web viewer (film.cjs, shots/v<N>/). Writes the hero clips
(mp4 + GIF) and JPEG stills to /home/bam/traj_compare/reports/media/rerun-pick-variants-2026-11-24/ and the gallery
beside that folder, then runs the babble skill's strict check.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "rerun-pick-variants-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/zach_brain/Settings/Skills/babble/scripts/gallery.py")

# The walkthrough every variant shows: the same moments of the agent's run, from its own hero frames (one page load,
# the playhead set through the viewer's handle). WHY these: the start, the run's worst tracking error (ruler peak 2.1 mm
# at 1.42 s), mid-tour, the end.
STEPS = [("Start (0 s)", "f-0-t0.png", "The agent's run (p6s on workspace-dev-029) at its first sample."),
         ("Worst tracking error (1.4 s)", "f-14-t1.4.png", "Where the solution is furthest off its target: the agent's ruler peaks at 2.1 mm at 1.42 s."),
         ("Mid-tour (1.8 s)", "f-18-t1.8.png", "1.8 s in: the arm, the path so far and every plot's cursor at one instant."),
         ("End (3.2 s)", "f-32-t3.2.png", "The last sample.")]


def jpeg(src: Path, dst: Path, width: int = 1600) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)], check=True)


def hero_clip(vid: str) -> tuple[str, str]:
    """The 33 hero frames as a muted looping clip (6 frames/s: 5.5 s) and a GIF fallback."""
    frames = sorted((SHOTS / vid / "hero").glob("f-*-t*.png"), key=lambda p: int(p.name.split("-")[1]))
    assert len(frames) >= 30, (vid, len(frames))
    with tempfile.TemporaryDirectory() as tmp:
        for k, frame in enumerate(frames):
            shutil.copy(frame, Path(tmp) / f"{k:03d}.png")
        mp4, gif = MEDIA / f"{vid}-hero.mp4", MEDIA / f"{vid}-hero.gif"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6", "-i", f"{tmp}/%03d.png", "-vf", "scale=1600:-2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", str(mp4)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6", "-i", f"{tmp}/%03d.png",
                        "-vf", "scale=800:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse", str(gif)], check=True)
    return f"{SLUG}/{mp4.name}", f"{SLUG}/{gif.name}"


def stepped_preview(vid: str) -> str:
    css = ["<style>.wt{position:relative;line-height:0}.wt img.f{width:100%;max-width:100%;height:auto;display:none}",
           ".wt .chips{position:absolute;left:8px;bottom:8px;display:flex;gap:6px;line-height:1.2;flex-wrap:wrap}",
           ".wt .chips button{font:12px system-ui;padding:3px 8px;border-radius:12px;border:1px solid #bbb;",
           "background:rgba(255,255,255,.92);color:#222;cursor:pointer}"]
    body = []
    for k, (label, _, _) in enumerate(STEPS, start=1):
        css.append(f'[data-story-state="s{k}"] .wt img.f[data-s="s{k}"]{{display:block}}')
        css.append(f'[data-story-state="s{k}"] .wt .chips button[data-story-to="s{k}"]{{background:#222;color:#fff;border-color:#222}}')
        body.append(f'<img class="f" data-s="s{k}" src="{SLUG}/{vid}-step-{k}.jpg" alt="{html.escape(label)}">')
    chips = "".join(f'<button data-story-to="s{k}">{k} · {html.escape(label)}</button>' for k, (label, _, _) in enumerate(STEPS, start=1))
    css.append("</style>")
    return "".join(css) + '<div class="wt">' + "".join(body) + f'<div class="chips">{chips}</div></div>'


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        for k, (_, name, _) in enumerate(STEPS, start=1):
            jpeg(SHOTS / vid / "hero" / name, MEDIA / f"{vid}-step-{k}.jpg")
        mp4, gif = hero_clip(vid)
        media = [{"label": "Hero clip: the agent's run, 0 → 3.2 s", "caption":
                  f"Filmed in the real Rerun 0.40 web viewer, 33 frames 0.1 s apart (the playhead set through the viewer's own handle), "
                  f"played at 6 frames/s. <a href=\"{gif}\">GIF</a>.",
                  "html": f'<video src="{mp4}" poster="{SLUG}/{vid}-step-1.jpg" autoplay muted loop playsinline controls></video>'}]
        for n, (name, label, caption) in enumerate(entry.pop("exhibits"), start=1):
            jpeg(SHOTS / vid / name, MEDIA / f"{vid}-extra-{n}.jpg")
            media.append({"label": label, "caption": caption, "html": f'<img src="{SLUG}/{vid}-extra-{n}.jpg" alt="{html.escape(label)}">'})
        variants.append({**entry, "previewLabel": "real Rerun 0.40 web viewer · the agent's run",
                         "preview": stepped_preview(vid),
                         "story": {"title": "Walk it", "steps": [
                             {"label": label, "caption": caption, "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                             for k, (label, _, caption) in enumerate(STEPS, start=1)]},
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
    size = sum(p.stat().st_size for p in MEDIA.iterdir())
    print(GALLERY, f"{GALLERY.stat().st_size / 1e6:.2f} MB page + {size / 1e6:.1f} MB media")


if __name__ == "__main__":
    main()
