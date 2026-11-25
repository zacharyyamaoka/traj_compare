"""Build the 2026-11-25 report: four pieces of coverage feedback, each held by a spec.

Reads the real captures in ``reports/media/feedback-specs-2026-11-25/`` (``docs/feedback_specs_2026-11-25/film.cjs``
wrote the video and the filter stills; the lanes' checks wrote the rest) and its ``notes.json`` (the run results and the
decision surface, kept out of git), and writes one self-contained page, ``reports/media/feedback-specs-2026-11-25.html``.

    python3 /home/bam/traj_compare/docs/build_feedback_specs_report.py
"""
from __future__ import annotations

import base64
import html
import json
import subprocess
import tempfile
from pathlib import Path

MEDIA = Path("/home/bam/traj_compare/reports/media")
CAPTURES = MEDIA / "feedback-specs-2026-11-25"
OUT = MEDIA / "feedback-specs-2026-11-25.html"


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def data_uri(path: Path, kind: str) -> str:
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def still(name: str, tmp: Path, width: int = 900) -> str:
    out = tmp / f"{name}.jpg"
    ffmpeg("-i", str(CAPTURES / f"{name}.png"), "-vf", f"scale='min({width},iw)':-2", "-q:v", "6", str(out))
    return data_uri(out, "image/jpeg")


def figure(name: str, caption: str, tmp: Path, width: int = 900) -> str:
    return (f'<figure><img alt="{html.escape(caption)}" src="{still(name, tmp, width)}">'
            f"<figcaption>{html.escape(caption)}</figcaption></figure>")


def pair(stem: str, what: str, tmp: Path) -> str:
    return ('<div class="pair">' + figure(f"before-{stem}", f"Before · {what}", tmp, 760)
            + figure(f"after-{stem}", f"After · {what}", tmp, 760) + "</div>")


def items(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>"


def build() -> Path:
    notes = json.loads((CAPTURES / "notes.json").read_text("utf-8"))
    film = json.loads((CAPTURES / "film.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        mp4, gif = tmp / "hero.mp4", tmp / "hero.gif"
        start = ["-ss", f"{film['ready']}", "-i", str(CAPTURES / "hero.webm")]
        ffmpeg(*start, "-an", "-vf", "scale=960:-2", "-c:v", "libx264", "-preset", "slow", "-crf", "33", "-pix_fmt",
               "yuv420p", "-movflags", "+faststart", str(mp4))
        ffmpeg(*start, "-vf", "fps=4,scale=640:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse",
               str(gif))
        sections = [
            f"<p class=verdict>{notes['verdict']}</p>",
            f'<video controls muted loop autoplay playsinline src="{data_uri(mp4, "video/mp4")}"></video>'
            "<p class=cap>The real workbench on a made-up arm: tick holdout, then one dataset, then walk the tabs. "
            f'<details><summary>GIF</summary><img alt="the same clip as a GIF" src="{data_uri(gif, "image/gif")}"></details></p>',
            "<h2>1 · Filter once, every view follows</h2>", notes["filter"],
            '<div class="trio">' + figure("overview-all", "No filter: 12 trajectories", tmp, 620)
            + figure("overview-holdout", "holdout ticked: 3", tmp, 620)
            + figure("overview-one", "holdout + Cell pick: 1", tmp, 620) + "</div>",
            "<h2>2 · No limit bars on a normalized axis</h2>", notes["bars"],
            pair("workbench-ridgeline-light", "workbench ridgeline", tmp), pair("page-ridgeline-light", "hand-rolled page", tmp),
            "<h2>3 · Marks and key you can see</h2>", notes["colours"],
            pair("workbench-limits-light", "workbench, light", tmp), pair("workbench-limits-dark", "workbench, dark", tmp),
            "<h2>4 · Tabs that look like V3 / V5</h2>", notes["tabs"],
            figure("tabs-light-full", "data-ui main, light", tmp) + figure("tabs-dark-slot", "in a 1000 × 680 host slot, dark", tmp),
            "<h2>Proof</h2>", notes["proof"],
            *(f"<h2>{html.escape(title)}</h2>{items(lines)}" for title, lines in notes["surface"].items()),
        ]
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coverage feedback, held by specs · 2026-11-25</title><style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1120px;margin:24px auto;padding:0 20px;color:#1f2328;background:#fff}}
h1{{font-size:22px}}h2{{font-size:17px;margin:32px 0 8px}}.verdict{{font-size:17px}}video,img{{max-width:100%;border:1px solid #d0d7de;border-radius:6px}}
figure{{margin:8px 0}}figcaption,.cap{{color:#57606a;font-size:13px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.trio{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}table{{border-collapse:collapse;font-size:13.5px}}td,th{{border-bottom:1px solid #d0d7de;padding:5px 10px;text-align:left;vertical-align:top}}
code{{background:#f3f4f6;padding:1px 4px;border-radius:3px;overflow-wrap:anywhere}}blockquote{{margin:6px 0;padding-left:12px;border-left:3px solid #d0d7de;color:#57606a}}
@media(max-width:760px){{.pair,.trio{{grid-template-columns:1fr}}}}
</style></head><body><h1>Coverage feedback, held by specs</h1>{''.join(sections)}</body></html>"""
        OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build())
