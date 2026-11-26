"""Assemble the self-contained static HTML comparison report.

One output file, everything inlined: the JSON channel payload, the vendored
uPlot + three.js bundles, and the authored viewer code. Open it from disk in
any browser — no server, no network, no install.
"""

from __future__ import annotations

import hashlib
import html
import importlib.resources
import json
import os
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
# WHY eight more (TTA ask, 2026-11-24): a task with 12 solutions wrapped to colour 1 again. Picked greedily from mid-lightness
# CIELAB (L 40-62, so a line reads on the light page and the dark one) for the largest smallest distance to every colour
# before it, in normal vision and under deuteranopia / protanopia / tritanopia (Machado 2009): each new one is >= 22 ΔE76
# from all the others, >= 11 under each simulation (the first eight are 6 apart for a deutan). The first eight are
# unchanged, so an existing report keeps its colours; past 16 it wraps. dataset.js and plots.js carry the same list.
SITUATION_PALETTE = (
    "#2a78d6", "#eb6834", "#2f9e44", "#8e5bd1", "#c22f6e", "#17a2b8", "#a67c00", "#6b7a8f",
    "#d17c7b", "#336a3a", "#7d4b8b", "#974811", "#f356b8", "#ac28ab", "#b81b36", "#9d86da",
)  # fmt: skip
# The viewer files every report needs, in the order the page loads them: (tag, file under assets/)
VIEWER_ASSETS = (
    ("style", "uplot.min.css"),
    ("style", "style.css"),
    ("script", "uplot.iife.min.js"),
    ("script", "three.min.js"),
    ("script", "viewhelper.js"),
    ("script", "viewer3d.js"),
    ("script", "timeline.js"),  # the time lane under the question tabs (docs/NAVIGATION.md Part B, 2026-11-25)
    ("script", "plots.js"),
)


def _asset(name: str) -> str:
    return importlib.resources.files("traj_compare").joinpath("assets", name).read_text("utf-8")


def viewer_digest() -> str:
    """12 hex characters naming this version of the viewer: its files (``VIEWER_ASSETS``) and this module, which writes
    the page they read. WHY (2026-11-25): a cache keyed by what was compared alone (``traj_compare.serve``'s playbacks)
    kept serving yesterday's viewer after an upgrade; a cache or a shared assets folder carries this digest instead."""

    digest = hashlib.sha1()
    for _, name in VIEWER_ASSETS:
        digest.update(name.encode("utf-8") + b"\0" + _asset(name).encode("utf-8") + b"\0")
    digest.update(Path(__file__).read_bytes())
    return digest.hexdigest()[:12]


def _is_url(location: str) -> bool:
    return "://" in location or location.startswith("//")


def _viewer_tags(assets: Path | str | None, report_dir: Path) -> dict[str, str]:
    """``{file name: its <style>/<script> tag}``: inlined (``assets=None``, today's self-contained page), or a reference
    to the one shared copy at ``assets`` (a URL, or a directory the files are written into, referenced relatively).

    WHY (TTA ask, 2026-11-24): 42 reports each inlining the same 0.92 MB of viewer (three.js r160 is 0.67 MB of it) put
    38 MB of copies on a static host; TTA swapped each inline copy for a reference by exact text substitution."""

    if assets is None:
        return {name: f"<{tag}>{_asset(name)}</{tag}>" for tag, name in VIEWER_ASSETS}
    if isinstance(assets, str) and _is_url(assets):
        base = assets.rstrip("/") + "/"
    else:
        folder = Path(assets)
        folder.mkdir(parents=True, exist_ok=True)
        for _, name in VIEWER_ASSETS:
            content = _asset(name)
            target = folder / name
            # WHY compare first: many reports share one folder; an unchanged file keeps its mtime (and a host's cache)
            if not target.is_file() or target.read_text("utf-8") != content:
                _files.write_text(target, content)
        base = Path(os.path.relpath(folder.resolve(), report_dir.resolve())).as_posix().rstrip("/") + "/"
    href = {name: html.escape(base + name, quote=True) for _, name in VIEWER_ASSETS}
    return {
        name: f'<link rel="stylesheet" href="{href[name]}">' if tag == "style" else f'<script src="{href[name]}"></script>'
        for tag, name in VIEWER_ASSETS
    }


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
    rerun_view: str = "auto",
    exports: bool = False,
    breadcrumb: Sequence[tuple[str, str]] = (),
    assets: Path | str | None = None,
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
    ``rerun_view`` (``rerun_export.write_rrd``'s ``view``): ``"auto"`` makes a comparison of one target and one run on a
    URDF (``RobotDisplay.urdf``) the target-vs-run recording (the run as its URDF arm, the target and its error on top),
    opened bare (no layout picker: the named layouts lay out the other recording); every other comparison, and
    ``"layouts"``, keeps the layouts above.
    ``exports=True`` writes ``exports/<name>.parquet`` and ``.mcap`` the same way (the ``export`` extra)
    and links them next to the page's other downloads.
    ``breadcrumb`` (``[(label, href), ...]``, e.g. ``[("Dataset", "../../index.html"), (target title,
    "../../index.html#/target/<slug>")]``) draws those links at the top of the page (``[data-tc-breadcrumb]``);
    an empty href draws plain text; empty draws nothing.
    ``assets`` (default ``None``: every viewer file inlined, one self-contained page): a directory or a URL holding the
    shared viewer files (uPlot, three.js, the viewer's JS and CSS; ``VIEWER_ASSETS``), referenced from there instead of
    inlined. A directory (a ``Path``, or a ``str`` that is not a URL) gets the files written into it and is referenced
    relative to the report, so many reports (and their host) share one copy; a URL is referenced as given.
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
        from .rerun_export import (LAYOUTS, RERUN_SDK_VERSION, blueprint_path, default_layout, viewer_command, write_rrd)
        from .rerun_export import rerun_view as view_of

        chosen = rerun_layout or default_layout()
        layout_order = [chosen, *[name for name in LAYOUTS if name != chosen]]

    if exports:
        from .export import write_mcap, write_parquet

    pages = []
    for comparison in comparisons:
        payload = analyze_comparison(comparison)
        _colorize(payload)
        # A saved HTML can recreate its Rerun layout from the embedded signals.
        # Keep native run bounds and limits, which downsampled plots cannot recover.
        situations = [*comparison.situations, comparison.target]
        payload["rerun_source"] = {
            "time_ranges": {item.name: [float(item.t[0]), float(item.t[-1])]
                            for item in situations if item is not None and item.has_data},
            "checks": dict(rerun_checks or {}),
        }
        source = payload["rerun_source"]
        if comparison.tolerances is not None:
            source["position_bands"] = {
                phase: {joint.name: float(joint.position) for joint in getattr(comparison.tolerances, phase)
                        if joint.position > 0}
                for phase in ("path", "goal")
            }
        if comparison.tcp_tolerances is not None:
            source["tcp_position_bands"] = {
                phase: float(getattr(getattr(comparison.tcp_tolerances, phase), "position", 0) or 0)
                for phase in ("path", "goal")
            }
        if rerun:
            relative = f"rerun/{comparison.name}.rrd"
            view = view_of(comparison, checks=rerun_checks) if rerun_view == "auto" else rerun_view
            rrd_path = write_rrd(
                comparison,
                report_path.parent / relative,
                layout=chosen,
                payload=payload,
                video_root=report_path.parent,
                checks=rerun_checks,
                view=view,
            )
        if rerun and view == "target_vs_run":
            # one recording with its own dashboard: no layout picker, and the page's open sends no ?layout=
            payload["rerun"] = {"rrd": relative, "sdk": RERUN_SDK_VERSION, "layout": "target_vs_run", "layouts": [],
                                "command": viewer_command(rrd_path)}
        elif rerun:
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
    tags = _viewer_tags(assets, report_path.parent)

    document = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>{html.escape(report_title)}</title>
{tags["uplot.min.css"]}
{tags["style.css"]}
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
{tags["uplot.iife.min.js"]}
{tags["three.min.js"]}
{tags["viewhelper.js"]}
{tags["viewer3d.js"]}
{tags["timeline.js"]}
{tags["plots.js"]}
<script>TrajCompare.boot();</script>
</body>
</html>
"""
    _files.write_text(report_path, document)  # NAVIGATION.md D2: a hard-linked copy's report is its own
    return report_path
