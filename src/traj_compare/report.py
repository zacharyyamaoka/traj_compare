"""Assemble the self-contained static HTML comparison report.

One output file, everything inlined: the JSON channel payload, the vendored
uPlot + three.js bundles, and the authored viewer code. Open it from disk in
any browser — no server, no network, no install.
"""

from __future__ import annotations

import html
import importlib.resources
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .analysis import analyze_comparison
from .model import Comparison, ReportPage

COLOR_TARGET = "#52514e"
# Family palette: blue/orange first (the CVD-validated pair the earlier
# reports established), then green/purple/magenta for wider A/B/C panels.
SITUATION_PALETTE = ("#2a78d6", "#eb6834", "#2f9e44", "#8e5bd1", "#c22f6e")


def _asset(name: str) -> str:
    return importlib.resources.files("traj_compare").joinpath("assets", name).read_text("utf-8")


def _colorize(payload: dict[str, Any]) -> None:
    index = 0
    for situation in payload["situations"]:
        if situation["role"] == "target":
            situation["color"] = COLOR_TARGET
        else:
            situation["color"] = SITUATION_PALETTE[index % len(SITUATION_PALETTE)]
            index += 1


def _share_robot_meshes(pages: list[dict[str, Any]]) -> list[str]:
    """Hoist every distinct link mesh into one report-level library.

    WHY: a factorial study poses the same rig on many comparison pages (one
    per joint x speed), and each page's payload carries its own encoded
    triangle soups. Identical soups are stored once and each link keeps an
    index into ``mesh_library``; colors, opacities and names stay per page.
    """

    library: list[str] = []
    index_of: dict[str, int] = {}
    for page in pages:
        for model in page.get("robots", []):
            for link in model["links"]:
                tris = link["tris"]
                if tris not in index_of:
                    index_of[tris] = len(library)
                    library.append(tris)
                link["tris"] = index_of[tris]
    return library


def write_comparison_report(
    comparisons: Comparison | list[Comparison],
    output: Path | str,
    *,
    title: str | None = None,
    subtitle: str = "",
    provenance: dict[str, Any] | None = None,
    summary: ReportPage | None = None,
    insights: ReportPage | None = None,
) -> Path:
    """Analyze the comparison(s) and write one self-contained ``report.html``.

    ``output`` may be a directory (writes ``report.html`` inside it) or a
    path ending in ``.html``.
    """

    if isinstance(comparisons, Comparison):
        comparisons = [comparisons]
    if not comparisons:
        raise ValueError("need at least one comparison")

    output = Path(output)
    if output.suffix.lower() == ".html":
        report_path = output
    else:
        report_path = output / "report.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    pages = []
    for comparison in comparisons:
        payload = analyze_comparison(comparison)
        _colorize(payload)
        pages.append(payload)

    report_pages = [page for page in (summary, insights) if page is not None]
    report_page_names = [page.name for page in report_pages]
    if len(report_page_names) != len(set(report_page_names)):
        raise ValueError(f"report-page names must be unique, got {report_page_names}")

    report_title = title or (pages[0]["title"] if len(pages) == 1 else "Trajectory comparison")
    provenance_entries = {
        "generated": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "viewer": "traj_compare 0.1.0 (uPlot 1.6.30, three.js r160)",
        **(provenance or {}),
    }
    provenance_text = " · ".join(f"{key}: {value}" for key, value in provenance_entries.items())

    mesh_library = _share_robot_meshes(pages)
    payload = {
        "title": report_title,
        "comparisons": pages,
        "mesh_library": mesh_library,
        "report_pages": [page.to_payload() for page in report_pages],
    }
    # </script> would end the data block early; escape the slash (legal JSON).
    data_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")

    document = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>{html.escape(report_title)}</title>
<style>{_asset("uplot.min.css")}</style>
<style>{_asset("style.css")}</style>
</head>
<body>
<header class='tc'>
  <h1>{html.escape(report_title)}</h1>
  <p>{html.escape(subtitle)}</p>
</header>
<nav class='tc-tabs' id='tc-tabs'></nav>
<nav class='tc-subtabs' id='tc-subtabs'></nav>
<main class='tc' id='tc-main'></main>
<footer class='tc'>{html.escape(provenance_text)}</footer>
<script type="application/json" id="traj-compare-data">{data_json}</script>
<script>{_asset("uplot.iife.min.js")}</script>
<script>{_asset("three.min.js")}</script>
<script>{_asset("viewhelper.js")}</script>
<script>{_asset("viewer3d.js")}</script>
<script>{_asset("plots.js")}</script>
<script>TrajCompare.boot();</script>
</body>
</html>
"""
    report_path.write_text(document, encoding="utf-8")
    return report_path
