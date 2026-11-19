"""Build the five summary-view layout proposals (babble round A, 2026-11-19) from the shared SIMULATED fixture.

    .venv/bin/python summary/build.py            # pages: OUT/v1..v5/index.html, OUT/fixture.js, OUT/vendor, OUT/shared
    .venv/bin/python summary/build.py --gallery  # also OUT/gallery-spec.json + OUT/index.html (needs OUT/shots/)

Sources live here (small, committed); OUT is gitignored (reports/media). Pages load plain <script src> files, so every
page opens from file:// with no server and no CDN (gate G1). Stats are computed in the browser by shared/common.js.
The gallery is rendered with the babble skill's gallery.py; scores and the AI default are left for the dispatcher.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TCD = HERE.parent
ASSETS = TCD.parent.parent / "src" / "traj_compare" / "assets"
FIXTURE = TCD / "fixture" / "fixture.json"
GALLERY_PY = Path.home() / ".claude-personal" / "skills" / "babble" / "scripts" / "gallery.py"


def _bam_ws() -> Path:
    for parent in HERE.parents:
        if (parent / "reports").is_dir() and (parent / "src").is_dir():
            return parent
    raise SystemExit("could not find the bam_ws root above " + str(HERE))


OUT = _bam_ws() / "reports" / "media" / "traj-compare-layouts-2026-11-19" / "summary"
VARIANTS = ("v1", "v2", "v3", "v4", "v5")


def build_pages(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    vendor = out / "vendor"
    vendor.mkdir(exist_ok=True)
    for name in ("uplot.iife.min.js", "uplot.min.css"):  # vendored verbatim (copy, never edit)
        shutil.copy2(ASSETS / name, vendor / name)
    # the fixture verbatim behind one global, so pages need no fetch (file:// safe)
    (out / "fixture.js").write_text("window.FIXTURE = " + FIXTURE.read_text() + ";\n")
    shutil.copytree(HERE / "shared", out / "shared", dirs_exist_ok=True)
    for variant in VARIANTS:
        src = HERE / variant
        if not src.is_dir():
            continue
        shutil.copytree(src, out / variant, dirs_exist_ok=True)
        print(f"  {out / variant / 'index.html'}")
    print(f"pages → {out}  (fixture.js {(out / 'fixture.js').stat().st_size / 1e6:.2f} MB)")


def build_gallery(out: Path) -> None:
    sys.path.insert(0, str(HERE))
    from gallery_spec import spec  # noqa: E402

    project = spec(out)
    spec_path = out / "gallery-spec.json"
    spec_path.write_text(json.dumps(project, indent=2, ensure_ascii=False))
    print(f"spec → {spec_path}")
    # WHY render_gallery and not `gallery.py build`: build refuses a spec without scores / defaultId, and this lane must
    # leave the AI prune (scores, gates, default, hinge) empty for the dispatcher to fill after seeing all five rounds.
    loader = importlib.util.spec_from_file_location("babble_gallery", GALLERY_PY)
    gallery = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(gallery)
    html = gallery.render_gallery(project, "deck")
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"gallery → {out / 'index.html'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--gallery", action="store_true", help="also write gallery-spec.json and the gallery index.html")
    args = parser.parse_args()
    build_pages(args.out)
    if args.gallery:
        build_gallery(args.out)


if __name__ == "__main__":
    main()
