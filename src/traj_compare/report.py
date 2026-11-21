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
from collections.abc import Mapping, Sequence
from typing import Any

from . import _files
from .analysis import analyze_comparison
from .model import Comparison, ReportPage

COLOR_TARGET = "#52514e"
# Family palette: blue/orange first (the CVD-validated pair the earlier
# reports established), then green/purple/magenta for wider A/B/C panels.
# WHY three more: a repeat group (5 real runs beside a sim) is 6+ situations, and a wrapped colour
# would give two runs one swatch. Appended, so a report of five or fewer is unchanged.
SITUATION_PALETTE = (
    "#2a78d6", "#eb6834", "#2f9e44", "#8e5bd1", "#c22f6e", "#17a2b8", "#a67c00", "#6b7a8f",
)  # fmt: skip


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


def _breadcrumb_html(breadcrumb: Sequence[tuple[str, str]]) -> str:
    """``[(label, href), ...]`` as the links at the top of the page (``[data-tc-breadcrumb]``); empty draws nothing.

    WHY (docs/NAVIGATION.md Part A): a run report links back up its levels, ``Dataset › <target title> › <run>``,
    e.g. ``[("Dataset", "../../index.html"), ("Reach A", "../../index.html#/target/reach-a")]``. An empty ``href``
    draws its label as plain text: the page you are on.
    """

    items = []
    for item in breadcrumb:
        if isinstance(item, (str, bytes)) or len(item) != 2:
            raise ValueError(f"a breadcrumb entry is a (label, href) pair, got {item!r}")
        label, href = (str(part) for part in item)
        if href:
            items.append(f"<a href='{html.escape(href, quote=True)}'>{html.escape(label)}</a>")
        else:
            items.append(f"<span aria-current='page'>{html.escape(label)}</span>")
    if not items:
        return ""
    separator = "<span class='sep' aria-hidden='true'>›</span>"
    return f"<nav class='tc-breadcrumb' data-tc-breadcrumb aria-label='Breadcrumb'>{separator.join(items)}</nav>\n  "


def write_comparison_report(
    comparisons: Comparison | list[Comparison],
    output: Path | str,
    *,
    title: str | None = None,
    subtitle: str = "",
    provenance: dict[str, Any] | None = None,
    summary: ReportPage | None = None,
    insights: ReportPage | None = None,
    rerun: bool = False,
    rerun_layout: str | None = None,
    rerun_checks: Mapping[str, str] | None = None,
    exports: bool = False,
    breadcrumb: Sequence[tuple[str, str]] = (),
) -> Path:
    """Analyze the comparison(s) and write one self-contained ``report.html``.

    ``output`` may be a directory (writes ``report.html`` inside it) or a
    path ending in ``.html``. ``rerun=True`` also writes ``rerun/<name>.rrd`` beside
    the report for every comparison and gives each page an "Open in Rerun" control;
    it needs the ``rerun`` extra and raises ImportError naming it when the SDK is absent.
    ``rerun_layout`` names the layout embedded in each .rrd ("questions" or "evo"; default: the user's
    preference, ``rerun_export.default_layout()``); the page offers every layout either way.
    ``rerun_checks`` (``{"camera": "Camera Check"}``) gives each named situation group its own Rerun tab,
    out of every other Rerun view and summary (``rerun_export.layout_blueprint``); the HTML page is unchanged.
    ``exports=True`` writes ``exports/<name>.parquet`` and ``.mcap`` the same way (the ``export`` extra)
    and links them next to the page's other downloads.
    ``breadcrumb`` (``[(label, href), ...]``, e.g. ``[("Dataset", "../../index.html"), (target title,
    "../../index.html#/target/<slug>")]``) draws those links at the top of the page (``[data-tc-breadcrumb]``);
    an empty href draws plain text; empty draws nothing.
    """

    if isinstance(comparisons, Comparison):
        comparisons = [comparisons]
    breadcrumb_html = _breadcrumb_html(breadcrumb)
    if not comparisons:
        raise ValueError("need at least one comparison")

    output = Path(output)
    if output.suffix.lower() == ".html":
        report_path = output
    else:
        report_path = output / "report.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if rerun:
        # Lazy, so the core report never imports the SDK; the module raises its own clear error.
        from .rerun_export import LAYOUTS, RERUN_SDK_VERSION, blueprint_path, default_layout, viewer_command, write_rrd

        chosen = rerun_layout or default_layout()
        layout_order = [chosen, *[name for name in LAYOUTS if name != chosen]]

    if exports:
        from .export import write_mcap, write_parquet

    pages = []
    for comparison in comparisons:
        payload = analyze_comparison(comparison)
        _colorize(payload)
        if rerun:
            relative = f"rerun/{comparison.name}.rrd"
            rrd_path = write_rrd(
                comparison,
                report_path.parent / relative,
                layout=chosen,
                payload=payload,
                video_root=report_path.parent,
                checks=rerun_checks,
            )
            layouts = [
                {
                    "name": name,
                    "title": LAYOUTS[name][0],
                    "rbl": blueprint_path(relative, name).as_posix(),
                    # the chosen layout is embedded, so its command is the bare .rrd; the others add their .rbl
                    "command": viewer_command(rrd_path, layout=None if name == chosen else name),
                }
                for name in layout_order
            ]
            payload["rerun"] = {
                "rrd": relative,
                "sdk": RERUN_SDK_VERSION,
                "layout": chosen,
                "layouts": layouts,
                "command": layouts[0]["command"],
            }
        if exports:
            files = {"parquet": f"exports/{comparison.name}.parquet", "mcap": f"exports/{comparison.name}.mcap"}
            write_parquet(comparison, report_path.parent / files["parquet"], payload=payload)
            write_mcap(comparison, report_path.parent / files["mcap"], payload=payload)
            payload["exports"] = files
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
  {breadcrumb_html}<h1>{html.escape(report_title)}</h1>
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
    _files.write_text(report_path, document)  # NAVIGATION.md D2: a hard-linked copy's report is its own
    return report_path
