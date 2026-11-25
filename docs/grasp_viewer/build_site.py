"""Build the Grasp dataset viewer: one static site over every grasp set traj_compare.grasp_coverage has analysed.

    python3 /home/bam/traj_compare/docs/grasp_viewer/build_site.py              # copy the existing outputs, scan, done
    python3 /home/bam/traj_compare/docs/grasp_viewer/build_site.py --rebuild    # re-run build_real.py first (reads /archive)

Source: build_real.py's output, ``reports/media/grasp-coverage-2026-11-24/`` (one folder per dataset: ``grasp_coverage.json``,
``png/``, ``site/``, and one data-ui kit in ``vendor/data-ui``). Every dataset folder found there is published, so a set
added to build_real.py appears here on the next build. Output (gitignored): ``reports/media/grasp-viewer-site/``:

    index.html                  the landing page: one card per dataset, its headline numbers read from its payload
    <slug>/site/                the data-ui workbench (its pages load ../../vendor/data-ui, kept as written)
    <slug>/png/                 the Matplotlib figures
    <slug>/grasp_coverage.json  the payload, downloadable
    vendor/data-ui/             ONE data-ui kit for every dataset
    404.html

Then a privacy scan over every text file that would be uploaded. It FAILS (exit 1, every hit printed) on a home or
archive path, an email address, the word "zach", or a token-looking string; nothing is rewritten to make it pass. Two
deliberate, printed exceptions: the kit's VENDOR.json files are left out (build provenance naming the build machine's
repo path; no page reads them), and the vendored data-ui kit may say "Zach" (its WHY comments): data-ui.dev serves the same
kit publicly (checked 2026-11-24: kit/views/table.js carries the same 3 mentions). The workbench's .base header is the
generator's notes (it quotes Zach); its comment lines are dropped on copy and the count printed (a .base comment is read
by nothing).

WHY a site of its own (Zach, 2026-11-24): "please deploy this as its own grasp dataset viewer". Deployed by
deploy/grasp-viewer (npm run deploy): a static-assets Cloudflare Worker on workers.dev.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
SOURCE = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24"
OUT = PACKAGE / "reports" / "media" / "grasp-viewer-site"
BUILD_REAL = PACKAGE / "docs" / "grasp_coverage_2026-11-24" / "build_real.py"
VENV_PYTHON = PACKAGE / ".venv" / "bin" / "python"
ORDER = ("repicks", "graspnet")  # first on the landing page; any other dataset folder follows, by name

TEXT = {".html", ".js", ".mjs", ".cjs", ".css", ".json", ".base", ".md", ".txt", ".py", ".svg", ".map", ".yaml", ".yml"}
SKIP_NAMES = {"VENDOR.json"}  # build provenance (the build machine's repo path); no page reads it
RULES = [
    ("home path", re.compile(r"/home/|/Users/|C:\\\\Users\\\\", re.I)),
    ("archive path", re.compile(r"/archive/")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]{2,}(?:\.[A-Za-z0-9-]{2,})*\."
                         r"(?:com|org|net|io|dev|ai|edu|gov|co|ca|uk|de|app)\b", re.I)),
    ("name", re.compile(r"zach", re.I)),
    ("token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b"
                         r"|\bxox[abposr]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{35}\b|\beyJ[A-Za-z0-9_-]{10,}\.eyJ"
                         r"|(?:api[_-]?key|secret|password|access[_-]?token)[\"'\s:=]+[A-Za-z0-9_\-]{20,}", re.I)),
]
# WHY: data-ui.dev publishes this same kit (its WHY comments name Zach); nothing else may
ALLOWED = {("vendor/data-ui/", "name")}

STYLE = """
:root{--ink:#22221f;--muted:#6f6e69;--line:#e3e2dc;--bg:#fafaf7;--card:#fff;--accent:#2f6fdf;--chip:#f0efe9}
@media (prefers-color-scheme: dark){:root{--ink:#e8e7e2;--muted:#a3a29b;--line:#34342f;--bg:#141413;--card:#1c1c1a;
--accent:#7aa7ff;--chip:#2a2a27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 20px 64px}h1{font-size:28px;margin:0 0 6px;line-height:1.2}
.lead{color:var(--muted);margin:0 0 24px;max-width:780px}code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 18px 14px;display:flex;flex-direction:column;gap:10px}
.card h2{font-size:19px;margin:0}.card p{margin:0;color:var(--muted);font-size:13.5px}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:4px 0}
.num{border:1px solid var(--line);border-radius:6px;padding:8px 10px}.num b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.num span{color:var(--muted);font-size:12px;line-height:1.3;display:block}
.thumbs{display:grid;grid-template-columns:1fr 1fr;gap:8px}.thumbs img{width:100%;height:auto;border:1px solid var(--line);border-radius:4px;background:#fff}
.links{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:14px}.open{background:var(--accent);color:#fff;padding:7px 14px;border-radius:6px;text-decoration:none;font-weight:600}
a{color:var(--accent)}footer{margin-top:32px;color:var(--muted);font-size:12.5px}
"""

NUMBERS = [("grasps", "grasps"), ("objects", "objects"), ("picked_pct", "picked, of the closed grasps"),
           ("directions_visited_pct", "approach directions visited"), ("tilt_max_deg", "largest tilt from straight down")]


def datasets(source: Path) -> list[str]:
    found = [p.name for p in sorted(source.iterdir()) if (p / "grasp_coverage.json").is_file() and (p / "site" / "index.html").is_file()]
    return [name for name in ORDER if name in found] + [name for name in found if name not in ORDER]


def number_text(entry: dict) -> str:
    value, unit = float(entry["value"]), entry.get("unit", "")
    if unit == "%":
        return f"{value:.1f} %"
    if unit == "deg":
        return f"{value:.1f}°"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:.2f}"


def card(slug: str, payload: dict) -> str:
    numbers = {entry["key"]: entry for entry in payload.get("numbers", [])}
    tiles = "".join(f'<div class=num><b>{number_text(numbers[key])}</b><span>{html.escape(words)}</span></div>'
                    for key, words in NUMBERS if key in numbers)
    thumbs = "".join(f'<a href="{slug}/png/{name}.png"><img loading=lazy src="{slug}/png/{name}.png" alt="{name}"></a>'
                     for name in ("positions", "width") if (OUT / slug / "png" / f"{name}.png").is_file())
    pngs = sorted(p.name for p in (OUT / slug / "png").glob("*.png")) if (OUT / slug / "png").is_dir() else []
    png_links = " · ".join(f'<a href="{slug}/png/{name}">{html.escape(name[:-4])}</a>' for name in pngs)
    return (f'<section class=card><h2>{html.escape(payload.get("title") or slug)}</h2>'
            f'<p>{html.escape(payload.get("subtitle") or "")}</p><div class=nums>{tiles}</div>'
            + (f"<div class=thumbs>{thumbs}</div>" if thumbs else "")
            + f'<div class=links><a class=open href="{slug}/site/index.html">Open the viewer</a>'
              f'<a href="{slug}/grasp_coverage.json" download>Download the payload (JSON)</a></div>'
            + (f'<p>Figures: {png_links}</p>' if png_links else "") + "</section>")


def landing(slugs: list[str]) -> str:
    cards = "".join(card(slug, json.loads((OUT / slug / "grasp_coverage.json").read_text("utf-8"))) for slug in slugs)
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=icon href="data:,"><title>Grasp dataset viewer</title><style>{STYLE}</style></head>
<body><main>
<h1>Grasp dataset viewer</h1>
<p class=lead>Robot grasps in, coverage figures out: a list of robot_msgs <code>GraspPose</code> (where the gripper closes, which
way it approaches, how wide the jaws are), an outcome per grasp and the gripper's jaw range go in; where the grasps sit,
how wide they are against the claw, which ways they come from and which objects they favour come out. Tick an outcome or
an object in a viewer's left rail and every figure recounts.</p>
<div class=cards>{cards}</div>
<footer>Made with traj_compare.grasp_coverage (one payload, read by this data-ui page, Matplotlib, Viser and W&amp;B summary
scalars) · {len(slugs)} dataset{'s' if len(slugs) != 1 else ''}</footer>
</main></body></html>
"""


NOT_FOUND = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=icon href="data:,"><title>Not found · Grasp dataset viewer</title>
<style>body{font:15px/1.5 system-ui,sans-serif;margin:48px auto;max-width:640px;padding:0 20px;color:#22221f}
@media (prefers-color-scheme: dark){body{background:#141413;color:#e8e7e2}a{color:#7aa7ff}}</style></head>
<body><h1>Not found</h1><p><a href="/">Back to the grasp dataset viewer</a></p></body></html>
"""


def copy_tree(source: Path, target: Path, notes: list[str]) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        if path.name in SKIP_NAMES:
            notes.append(f"left out {target.relative_to(OUT) / relative}: build provenance (the build machine's path)")
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".base":
            lines = path.read_text("utf-8").splitlines(keepends=True)
            kept = [line for line in lines if not line.lstrip().startswith("#")]
            destination.write_text("".join(kept), "utf-8")
            notes.append(f"{destination.relative_to(OUT)}: dropped {len(lines) - len(kept)} comment lines "
                         "(the generator's notes; the page reads no comment)")
        else:
            shutil.copy2(path, destination)


def scan(root: Path) -> list[str]:
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT:
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text("utf-8", errors="replace")
        for rule, pattern in RULES:
            if any(relative.startswith(prefix) and rule == allowed for prefix, allowed in ALLOWED):
                continue
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                start = max(0, match.start() - 40)
                hits.append(f"{relative}:{line}: {rule}: …{text[start:match.end() + 40]!r}…")
                if sum(1 for hit in hits if hit.startswith(relative)) >= 5:
                    break
    return hits


def build(rebuild: bool) -> list[str]:
    if rebuild:
        subprocess.run(["taskset", "-c", "2-5,16,17", "nice", "-n", "10", str(VENV_PYTHON), str(BUILD_REAL)], check=True)
    slugs = datasets(SOURCE)
    if not slugs:
        raise SystemExit(f"no grasp datasets under {SOURCE}; run with --rebuild (or build_real.py) first")
    if not (SOURCE / "vendor" / "data-ui" / "data-ui.js").is_file():
        raise SystemExit(f"no data-ui kit at {SOURCE / 'vendor' / 'data-ui'}; run build_real.py")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    notes: list[str] = []
    copy_tree(SOURCE / "vendor" / "data-ui", OUT / "vendor" / "data-ui", notes)
    for slug in slugs:
        copy_tree(SOURCE / slug / "site", OUT / slug / "site", notes)
        copy_tree(SOURCE / slug / "png", OUT / slug / "png", notes)
        shutil.copy2(SOURCE / slug / "grasp_coverage.json", OUT / slug / "grasp_coverage.json")
    (OUT / "index.html").write_text(landing(slugs), "utf-8")
    (OUT / "404.html").write_text(NOT_FOUND, "utf-8")
    for note in notes:
        print("note:", note)
    return slugs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="re-run build_real.py first (reads /archive, read-only)")
    args = parser.parse_args()
    slugs = build(args.rebuild)
    hits = scan(OUT)
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"built {OUT} : {', '.join(slugs)} · {files} files · {size / 1e6:.1f} MB")
    print("allowed: the word 'zach' inside vendor/data-ui/ (data-ui's WHY comments; data-ui.dev serves the same kit)")
    if hits:
        print(f"PRIVACY SCAN FAILED: {len(hits)} hit(s); nothing was rewritten, fix the source:", file=sys.stderr)
        for hit in hits:
            print("  " + hit, file=sys.stderr)
        raise SystemExit(1)
    print("privacy scan clean")


if __name__ == "__main__":
    main()
