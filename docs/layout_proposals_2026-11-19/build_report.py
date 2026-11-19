"""Build the 2026-11-19 review report: the torque breakdown (shipped) + the three layout rounds (proposals).

One self-contained HTML page (media inlined, so it opens on any device), written to the main checkout's reports/media.
Content lives in report_content.py beside this file; the prune numbers are read from each round's gallery-spec.json.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19
    ../../.venv/bin/python build_report.py
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEDIA = Path("/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19")
OUT = Path("/home/bam/bam_ws/reports/media/traj-compare-torque-2026-11-19.html")
FFMPEG = "/usr/bin/ffmpeg"


def _jpeg(path: Path, width: int = 1440, quality: int = 4) -> bytes:
    """A PNG still as a compact JPEG (the page must stay small enough for the desktop preview)."""

    if path.suffix.lower() in (".jpg", ".jpeg", ".webp", ".gif", ".mp4"):
        return path.read_bytes()
    result = subprocess.run(
        ["taskset", "-c", "2-5,16,17", "nice", "-n", "19", FFMPEG, "-v", "error", "-i", str(path),
         "-vf", f"scale='min({width},iw)':-2", "-q:v", str(quality), "-f", "image2", "-c:v", "mjpeg", "-"],
        capture_output=True, check=True,
    )  # fmt: skip
    return result.stdout


def data_uri(path: Path, width: int = 1440) -> str:
    path = Path(path)
    if path.suffix.lower() == ".png":
        return "data:image/jpeg;base64," + base64.b64encode(_jpeg(path, width)).decode()
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def figure(path: Path, caption: str, width: int = 1280, kind: str = "img") -> str:
    if not Path(path).is_file():
        return f'<figure class="missing"><div>missing: {html.escape(str(path))}</div><figcaption>{caption}</figcaption></figure>'
    if kind == "video" or str(path).endswith(".mp4"):
        body = f'<video src="{data_uri(path)}" autoplay muted loop playsinline controls></video>'
    else:
        body = f'<img src="{data_uri(path, width)}" alt="">'
    return f"<figure>{body}<figcaption>{caption}</figcaption></figure>"


def prune_table(spec_path: Path) -> str:
    """The AI prune of one round: ranking, weighted totals, per-FR scores with evidence (collapsed)."""

    if not spec_path.is_file():
        return f"<p class='missing'>no gallery spec at {html.escape(str(spec_path))}</p>"
    spec = json.loads(spec_path.read_text())
    requirements = spec.get("requirements") or []
    rows = []
    for variant in spec.get("variants", []):
        scores = variant.get("scores") or {}
        total = sum(float(req.get("weight", 0)) * float(scores.get(req["id"], {}).get("score", 0)) / 5.0 for req in requirements)
        rows.append((total, variant, scores))
    rows.sort(key=lambda row: -row[0])
    head = "".join(f"<th title='{html.escape(req.get('name', ''))}'>{html.escape(req['id'].upper())}<br><small>{req.get('weight')}%</small></th>"
                   for req in requirements)  # fmt: skip
    body = []
    for rank, (total, variant, scores) in enumerate(rows, start=1):
        cells = "".join(
            f"<td title='{html.escape(scores.get(req['id'], {}).get('evidence', ''))}'>{scores.get(req['id'], {}).get('score', '–')}</td>"
            for req in requirements
        )
        mark = " class='pick'" if variant.get("id") == spec.get("defaultId") else ""
        body.append(f"<tr{mark}><td>{rank}</td><td><b>{html.escape(variant['id'].upper())}</b> {html.escape(variant['name'])}</td>{cells}<td><b>{total:.0f}</b></td></tr>")
    hinge = html.escape(spec.get("decisionHinge", ""))
    why = html.escape(spec.get("defaultWhy", ""))
    return (f"<table class='prune'><tr><th>#</th><th>Variant</th>{head}<th>Total</th></tr>{''.join(body)}</table>"
            f"<p class='why'><b>AI pick:</b> {why}</p><p class='hinge'><b>Decision hinge:</b> {hinge}</p>")  # fmt: skip


STYLE = """
:root{--ink:#22221f;--muted:#6f6e69;--line:#e3e2dc;--bg:#fafaf7;--card:#fff;--accent:#2f6fdf;--ok:#2f8f4e;--warn:#b7791f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}h1{font-size:26px;margin:0 0 6px}h2{font-size:20px;margin:38px 0 10px;border-top:1px solid var(--line);padding-top:24px}
h3{font-size:16px;margin:22px 0 8px}.verdict{font-size:17px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);padding:12px 16px;border-radius:8px}
.kicker{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}figure{margin:14px 0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
figure img,figure video{width:100%;display:block;border-radius:4px}figcaption{color:var(--muted);font-size:13px;padding:6px 4px 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid5{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.grid5 figure{margin:0;padding:4px}.grid5 figcaption{font-size:12px}
@media (max-width:800px){.grid2,.grid5{grid-template-columns:1fr}}table{border-collapse:collapse;width:100%;background:var(--card);font-size:13px;margin:8px 0}
th,td{border:1px solid var(--line);padding:5px 7px;text-align:left;vertical-align:top}th{background:#f2f1ec}tr.pick td{background:#eef6ee}
code{background:#f0efe9;padding:1px 4px;border-radius:3px;font-size:13px}pre{background:#f0efe9;padding:10px;border-radius:6px;overflow:auto;font-size:13px}
.missing{color:#b42318}.why,.hinge{font-size:14px}ul{padding-left:20px}li{margin:3px 0}.tag{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 8px;color:var(--muted)}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}summary{cursor:pointer;font-weight:600}
"""


def build() -> Path:
    sys.path.insert(0, str(HERE))
    import report_content  # noqa: E402

    body = report_content.body(figure=figure, prune_table=prune_table, media=MEDIA)
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Torque breakdown + layouts</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>")  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    print(f"{OUT}  {OUT.stat().st_size / 1e6:.2f} MB")
    return OUT


if __name__ == "__main__":
    build()
