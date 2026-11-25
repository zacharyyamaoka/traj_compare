"""The record-coverage workbench: data-ui's stock ``<data-workbench>`` over a list of records (docs/RECORD_COVERAGE.md,
"The workbench"; data-ui docs/CONTRACT.md §52 coverage views and §53 scope + workbench).

    coverage = analyze(records, group_by="item", split="split")
    write_workbench(coverage, records, "out/")      # python -m traj_compare.serve out/  -> /index.html

Writes into ``out_dir``: ``records.json`` (one row per record: its id, every category, text and number field in display
units, its missing count, new and unique cells, its cohort), ``parts.json`` (one row per cohort × figure), ``growth.json``
(the whole set's growth curve), ``support.json`` (with a split), ``coverage.base``, ``index.html``, ``embed.html`` and
``vendor/data-ui/`` (data-ui vendored by its own ``vendor`` command, unless ``kit=`` names one already there).

WHY cohorts, not one part row per record: a part row carries its figure's whole geometry (data-ui sums rows whose grids
agree), so 1,131 records × 30 figures was ~12 MB of JSON. The rail filters records by category fields only, so the
records that share every rail value (a cohort) are always kept or dropped together: summing the parts of the kept
cohorts is EXACT (tests/test_record_coverage_workbench.py recounts it with numpy for every pick). A slider or a search in
the rail would keep part of a cohort, so the rail never has one; the Records table has its own search.
WHY the same base shape as the trajectory workbench (coverage/workbench.py): one visual language for all three families
(Zach 2026-11-23, "the nice thing with data-ui is its the common visual languague").
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .. import _files
from ..coverage.workbench import DATA_UI, SLOTS, SPLIT_SLOTS, _vendor, _write_json, _yaml
from . import analysis as rc

RESERVED = {"id", "index", "missing", "new_cells", "unique_cells", "cohort"}


def _payload(coverage) -> dict:
    payload = coverage.payload if hasattr(coverage, "payload") else coverage
    if not isinstance(payload, Mapping) or payload.get("schema") != rc.SCHEMA:
        raise ValueError(f"expected a {rc.SCHEMA!r} payload (analyze()'s result), got {type(coverage).__name__}")
    return payload  # type: ignore[return-value]


def _keys(names: Sequence[str]) -> dict[str, str]:
    """Each field name as a data-ui property key: runs of anything but letters, digits and _ become _ (tcp[0] -> tcp_0,
    grip.width_mm -> grip_width_mm, len(path) -> len_path); a clash with another key or a reserved column gets _2."""
    keys: dict[str, str] = {}
    taken = set(RESERVED)
    for name in names:
        key = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "field"
        if key[0].isdigit():
            key = "f_" + key
        base, k = key, 2
        while key in taken:
            key, k = f"{base}_{k}", k + 1
        taken.add(key)
        keys[name] = key
    return keys


def _rail(payload: Mapping) -> list[str]:
    """The category fields the rail filters by: group_by, then the split, then each category of 2 to 24 levels."""
    low, high = rc.RAIL_LEVELS
    small = [name for name, block in payload["classes"].items() if low <= len(block["levels"]) <= high]
    first = [name for name in (payload["source"]["group_by"], payload["source"]["split"]) if name in small]
    return list(dict.fromkeys(first + small))[:5]


def _round(value: float) -> float:
    return float(f"{value:.6g}")


def workbench_rows(coverage, records: Sequence) -> tuple[list[dict], list[dict]]:
    """(record rows, part rows) for one ``analyze()`` result and the SAME records it was given, in the same order."""
    payload = _payload(coverage)
    records = list(records)
    if len(records) != payload["source"]["records"]:
        raise ValueError(f"the records must be the records analyze() was given ({len(records)} given, the payload has "
                         f"{payload['source']['records']})")
    space = getattr(coverage, "options", {}).get("space") if hasattr(coverage, "options") else None
    columns, _ = rc._columns(records, space=space)
    by_name = {column.name: column for column in columns}
    fields = payload["fields"]
    missing = [f["name"] for f in fields if f["name"] not in by_name]
    if missing:
        raise ValueError(f"the records analyze() was given have the field {missing[0]!r}; these do not")
    ids = [row["id"] for row in payload["records"]]
    if payload["source"]["id_field"]:
        given = [str(v) if v is not None else f"#{i}" for i, v in enumerate(by_name[payload["source"]["id_field"]].values)]
        if given != ids:
            raise ValueError("the records must be the records analyze() was given, in its order (their ids differ)")
    keys = _keys([f["name"] for f in fields])
    kinds = {f["name"]: f for f in fields}
    rail = _rail(payload)

    def level(name: str, value) -> str | None:
        return None if value is None else rc._level(value)

    # each record's rail tuple names its cohort, in first-seen order
    cohort_of: dict[tuple, str] = {}
    cohorts = []
    for i in range(len(records)):
        values = tuple(level(name, by_name[name].values[i]) for name in rail)
        cohorts.append(cohort_of.setdefault(values, f"c{len(cohort_of)}"))

    record_rows = []
    for i, source in enumerate(payload["records"]):
        row: dict[str, Any] = {"id": source["id"], "index": i}
        for field in fields:
            value = by_name[field["name"]].values[i]
            key = keys[field["name"]]
            if field["kind"] == "number":
                # WHY full precision: the table rounds for display (decimals), the file keeps the measurement
                row[key] = None if value is None else float(value) * field["display"]["scale"]
            else:
                row[key] = level(field["name"], value) if field["kind"] == "category" else (None if value is None else str(value))
        row.update(missing=source["missing"], new_cells=source["new_cells"], unique_cells=source["unique_cells"],
                   cohort=cohorts[i])
        record_rows.append(row)

    group_by = payload["source"]["group_by"]
    group_of = [r["group"] for r in payload["records"]]
    cohort_members: dict[str, np.ndarray] = {}
    for name in dict.fromkeys(cohorts):
        cohort_members[name] = np.flatnonzero(np.asarray(cohorts, object) == name)

    parts: list[dict] = []
    for order, (name, hist) in enumerate(payload["hist"].items()):
        field = kinds[name]
        values = np.asarray([np.nan if v is None else float(v) for v in by_name[name].values], float)
        index = rc._bin(values, hist["edges"])
        n = hist["edges"][2]
        limit = hist["source"] != "data"
        for cohort, members in cohort_members.items():
            inside = members[index[members] >= 0]
            counts = np.bincount(index[inside], minlength=n)
            present = values[members][np.isfinite(values[members])]
            row = {"id": f"{cohort}|{keys[name]}", "kind": "hist", "grid": keys[name], "cohort": cohort, "field": name,
                   "field_order": order, "label": name, "signal": "records", "lo": hist["edges"][0], "hi": hist["edges"][1],
                   "bins": n, "counts": counts.tolist(), "low": hist["low"], "high": hist["high"],
                   "limit_source": "limit" if limit else "data",
                   "outside": int(((present < hist["low"]) | (present > hist["high"])).sum()) if limit else 0,
                   "scale": field["display"]["scale"], "unit": field["display"]["unit"]}
            if group_by is not None:
                names = list(dict.fromkeys(group_of[i] for i in inside)) or [group_of[members[0]]]
                row["groups"] = names
                row["group_counts"] = [np.bincount(index[[i for i in inside if group_of[i] == g]], minlength=n).tolist()
                                       for g in names]
            parts.append(row)

    for pair in payload["pairs"]:
        x, y = pair["x"], pair["y"]
        (xl, xh, nx), (yl, yh, ny) = pair["x_edges"], pair["y_edges"]
        xv = np.asarray([np.nan if v is None else float(v) for v in by_name[x].values], float)
        yv = np.asarray([np.nan if v is None else float(v) for v in by_name[y].values], float)
        both = np.isfinite(xv) & np.isfinite(yv)
        xi, yi = rc._bin(xv, pair["x_edges"]), rc._bin(yv, pair["y_edges"])
        cell = np.where(both & (xi >= 0) & (yi >= 0), xi * ny + yi, -1)
        grid = f"pair:{keys[x]}|{keys[y]}"
        boxed = payload["hist"][x]["source"] != "data" and payload["hist"][y]["source"] != "data"
        for cohort, members in cohort_members.items():
            counts = np.bincount(cell[members][cell[members] >= 0], minlength=nx * ny)
            at = np.flatnonzero(counts)
            parts.append({
                "id": f"{cohort}|{grid}", "kind": "pair", "grid": grid, "cohort": cohort, "title": f"{x} × {y}",
                "x": x, "y": y, "x_label": x, "y_label": y,
                "x_lo": xl, "x_hi": xh, "nx": nx, "y_lo": yl, "y_hi": yh, "ny": ny,
                "x_scale": kinds[x]["display"]["scale"], "y_scale": kinds[y]["display"]["scale"],
                "x_unit": kinds[x]["display"]["unit"] or "", "y_unit": kinds[y]["display"]["unit"] or "",
                "box": "limit" if boxed else "none", "enough": payload["enough"],
                "at": at.tolist(), "samples": counts[at].tolist(),
                "outside": int((both[members] & (cell[members] < 0)).sum()),
            })

    for order, field in enumerate(fields):
        values = by_name[field["name"]].values
        for cohort, members in cohort_members.items():
            gone = sum(1 for i in members if values[i] is None)
            parts.append({"id": f"{cohort}|missing|{keys[field['name']]}", "kind": "missing", "cohort": cohort,
                          "field": field["name"], "field_order": order, "missing": gone, "present": len(members) - gone})
    return record_rows, parts


# ── the files ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _record_properties(payload: Mapping, keys: Mapping[str, str]) -> dict:
    properties = {"id": {"type": "text", "label": "Record"}, "index": {"type": "number", "label": "Order",
                                                                        "description": "its place in the list analyze() was given"}}
    for field in payload["fields"]:
        key = keys[field["name"]]
        if field["kind"] == "number":
            entry = {"type": "number", "label": field["name"], "decimals": 3}
            if field["display"]["unit"]:
                entry["unitText"] = field["display"]["unit"]
            properties[key] = entry
        else:
            properties[key] = {"type": "text", "label": field["name"]}
    properties.update({
        "missing": {"type": "number", "label": "Missing", "decimals": 2,
                    "description": "fields with no value in this record"},
        "new_cells": {"type": "number", "label": "New cells",
                      "description": "cells of the space it was the first to visit, in the order analyze() was given"},
        "unique_cells": {"type": "number", "label": "Cells only it visits",
                         "description": "0 = every cell it visits, another record visits too (droppable)"},
        "cohort": {"type": "text", "label": "Cohort", "hidden": True,
                   "description": "the records that share every rail value"},
    })
    return properties


def _part_properties() -> dict:
    hidden_list = {"type": "list", "hidden": True}
    properties: dict[str, Any] = {
        "id": {"type": "text", "label": "Part"}, "kind": {"type": "text", "label": "Figure"},
        "grid": {"type": "text", "label": "Grid"}, "cohort": {"type": "text", "label": "Cohort"},
        "field": {"type": "text", "label": "Field"}, "field_order": {"type": "number", "hidden": True},
        "label": {"type": "text", "label": "Histogram"}, "title": {"type": "text", "label": "Plane"},
        "signal": {"type": "text", "hidden": True},
        "missing": {"type": "number", "label": "Records with no value"},
        "present": {"type": "number", "label": "Records with a value"},
        "at": {**hidden_list, "label": "cells visited"}, "samples": {**hidden_list, "label": "records per cell"},
        "counts": hidden_list, "groups": hidden_list, "group_counts": hidden_list,
    }
    for key in ("x", "y", "x_label", "y_label", "x_unit", "y_unit", "box", "limit_source", "unit"):
        properties[key] = {"type": "text", "hidden": True}
    for key in ("x_lo", "x_hi", "nx", "y_lo", "y_hi", "ny", "x_scale", "y_scale", "enough", "outside", "lo", "hi",
                "bins", "low", "high", "scale"):
        properties[key] = {"type": "number", "hidden": True}
    return properties


GROWTH_SERIES = ("in the order given", "random order: median", "random order: p10", "random order: p90")


def _growth_rows(payload: Mapping) -> list[dict]:
    """Long form, one row per (series, records): one line mark with a legend entry per series."""
    growth = payload["coverage"]["growth"]
    shuffled = growth["shuffled"]
    series = dict(zip(GROWTH_SERIES, (growth["visited_pct"], shuffled["median"], shuffled["p10"], shuffled["p90"]),
                      strict=True))
    return [{"id": f"{name}|{k}", "series": name, "records": k, "visited_pct": _round(value)}
            for name, values in series.items() for k, value in zip(growth["records"], values, strict=True)]


def _support_rows(payload: Mapping) -> list[dict]:
    support = payload["support"]
    rows = []
    for level, block in support["levels"].items():
        for name, pct in block["fields"].items():
            rows.append({"id": f"{level}|{name}", "level": level, "field": name, "unsupported_pct": _round(pct)})
    return rows


_HEADER = """# The record-coverage workbench: data-ui's <data-workbench> over these records (data-ui docs/CONTRACT.md §52, §53).
# GENERATED by traj_compare.record_coverage.workbench.write_workbench (docs/RECORD_COVERAGE.md "The workbench"): change
# the writer, never this file. The rail filters records by their category fields; every tab is a dashboard over what it
# keeps, and each coverage figure adds up the kept cohorts' part rows (coverage.sum), so a tick recounts every tab
# exactly. The growth and support panels are the whole set's (the rail does not narrow them); they say so.
"""


def _colours(levels: Sequence[str], slots: Sequence[int]) -> dict:
    return {level: slots[i] for i, level in enumerate(levels[:len(slots)])}


def _base(payload: Mapping, keys: Mapping[str, str], rail: Sequence[str], *, title: str) -> dict:
    classes = payload["classes"]
    group_by, split = payload["source"]["group_by"], payload["source"]["split"]
    facets = [{"property": keys[name], "label": name, "order": classes[name]["levels"]} for name in rail]
    properties: dict[str, Any] = {"id": {"displayName": "Record"}}
    group_colours = _colours(payload["source"]["groups"], SLOTS) if group_by else {}
    if group_by:
        properties[keys[group_by]] = {"displayName": group_by, "colors": group_colours}
    if split and split != group_by:
        free = [slot for slot in SPLIT_SLOTS if slot not in group_colours.values()]
        properties[keys[split]] = {"displayName": split, "colors": _colours(classes[split]["levels"], free)}
    style: dict[str, Any] = {"numbers": {"digits": 3}}
    if group_by:
        style["families"] = {"property": keys[group_by], "colors": group_colours}
    style["heatmap"] = {"colormap": "viridis", "reverse": False, "scale": "linear"}
    datasets = {"parts": {"data": "parts.json", "label": "Coverage parts"},
                "growth": {"data": "growth.json", "label": "Growth (whole set)"}}
    if payload["support"]:
        datasets["support"] = {"data": "support.json", "label": "Held-out support (whole set)"}
    return {
        "data": "records.json",
        "noun": ["record", "records"],
        "facets": facets,
        "properties": properties,
        "style": style,
        "settings": ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"],
        "drill": {"actions": [{"label": "Copy its id", "copy": "{id}", "title": "Copies {id}"}]},
        "datasets": datasets,
        "links": [{"from": "records.cohort", "to": "parts.cohort", "direction": "one-way"}],
        "pages": _pages(payload),
        "views": _views(payload, keys, rail),
    }


def _page(name: str, panels: list[dict]) -> dict:
    # WHY 48 px rows: the summary strip needs ~140 px; on 96 px rows it was clipped (1 row) or half empty (2 rows)
    return {"name": name, "layout": {"columns": 12, "rowHeight": 48,
                                     "panels": [{**p, "h": 2 * p["h"]} for p in panels if p]}}


def _pair_name(pair: Mapping) -> str:
    return f"{pair['x']} × {pair['y']}"


def _class_names(payload: Mapping) -> list[str]:
    return list(payload["classes"])


def _pages(payload: Mapping) -> list[dict]:
    classes = _class_names(payload)
    numbers = len(payload["hist"])
    hist_h = max(3, min(9, 1 + 2 * ((numbers + 2) // 3)))
    overview = [
        {"view": "At a glance", "w": 12, "h": 1.5, "style": {"title": "none"}},
        {"view": "Every number against its range", "w": 8, "h": 5} if numbers else None,
        {"view": "Is more data still adding coverage?", "w": 4, "h": 3},
        {"view": "Missing values", "w": 4, "h": 2},
    ]
    if payload["pairs"]:
        overview.append({"view": _pair_name(payload["pairs"][0]), "w": 6, "h": 4})
    for name in classes[:2]:
        overview.append({"view": f"{name} · class balance", "w": 3, "h": 4})
    pages = [
        _page("Overview", overview),
        _page("Numbers", [{"view": "Every number against its range", "w": 12, "h": hist_h,
                           "style": {"title": "none"}} if numbers else {"view": "Missing values", "w": 12, "h": 3}]),
        _page("Classes", [{"view": f"{name} · class balance", "w": 4, "h": 4} for name in classes]
              or [{"view": "Missing values", "w": 12, "h": 3}]),
        _page("Pairs", [{"view": _pair_name(pair), "w": 6, "h": 5} for pair in payload["pairs"]]
              or [{"view": "Missing values", "w": 12, "h": 3}]),
        _page("Missing", [{"view": "Missing values", "w": 12, "h": max(3, min(8, 1 + len(payload["fields"]) // 4))}]),
        _page("Growth", [{"view": "Is more data still adding coverage?", "w": 8, "h": 4},
                         {"view": "What each record added", "w": 12, "h": 3}]),
    ]
    if payload["support"]:
        pages.append(_page("Support", [{"view": "Held out, outside the reference", "w": 12, "h": 5}]))
    pages.append(_page("Records", [{"view": "Records", "w": 12, "h": 7, "style": {"title": "none"}}]))
    return pages


def _views(payload: Mapping, keys: Mapping[str, str], rail: Sequence[str]) -> list[dict]:
    n = payload["source"]["records"]
    group_by, split = payload["source"]["group_by"], payload["source"]["split"]
    views: list[dict] = [{
        "type": "summary", "name": "At a glance",
        "summary": {"cells": [
            {"label": "Records", "note": "what the rail keeps"},
            {"label": "Nothing missing", "note": "records with a value in every field", "filters": "missing == 0"},
            {"label": "Add a cell of their own", "note": "records that visit a cell no other record visits",
             "filters": "unique_cells > 0"},
            {"label": "Something missing", "note": "records with no value in at least one field",
             "filters": "missing > 0"},
        ]},
    }]
    if payload["hist"]:
        views.append({"type": "coverage-hist", "name": "Every number against its range", "from": "parts",
                      "filters": 'kind == "hist"', "sort": [{"property": "field_order", "direction": "ASC"}],
                      "coverage": {"sum": "grid", "card": "field", "title": "label"}})
    # WHY one view per pair, never small multiples: multiples share one y axis, and two pairs have different ranges
    for pair in payload["pairs"]:
        grid = f"pair:{keys[pair['x']]}|{keys[pair['y']]}"
        views.append({"type": "coverage-plane", "name": _pair_name(pair), "from": "parts",
                      "filters": f'kind == "pair" && grid == "{grid}"', "coverage": {"sum": "grid", "title": "title"}})
    for name, block in payload["classes"].items():
        colour = group_by if group_by and group_by != name else (split if split and split != name else None)
        encoding: dict[str, Any] = {
            "y": {"field": keys[name], "title": None, "sort": block["levels"], "scale": {"domain": block["levels"]}},
            "x": {"aggregate": "count", "title": "records"},
        }
        if colour:
            encoding["color"] = {"field": keys[colour], "title": colour}
        views.append({"type": "chart", "name": f"{name} · class balance", "chart": {"mark": "bar", "encoding": encoding}})
    views.append({"type": "chart", "name": "Missing values", "from": "parts", "filters": 'kind == "missing"',
                  "chart": {"mark": "bar", "encoding": {
                      "y": {"field": "field", "title": None, "sort": "-x"},
                      "x": {"aggregate": "sum", "field": "missing", "title": "records with no value"}}}})
    ceiling = payload["coverage"]["ceiling_pct"]
    views.append({"type": "chart", "name": "Is more data still adding coverage?", "from": "growth",
                  "chart": {"mark": "line", "encoding": {
                      "x": {"field": "records", "type": "quantitative",
                            "title": f"records added (all {n}; the rail does not narrow this one)"},
                      "y": {"field": "visited_pct", "type": "quantitative", "title": "cells of the space visited (%)"},
                      "color": {"field": "series", "title": None, "sort": list(GROWTH_SERIES)},
                      "strokeDash": {"field": "series", "title": None, "sort": list(GROWTH_SERIES)}}},
                  "guides": [{"rule": {"y": ceiling}, "label": f"Chao1: more of the same reaches {ceiling:.1f} %"}]})
    views.append({"type": "chart", "name": "What each record added",
                  "chart": {"mark": "bar", "encoding": {
                      "x": {"field": "index", "type": "quantitative", "title": "record (in the order given)"},
                      "y": {"field": "new_cells", "type": "quantitative", "title": "new cells"},
                      **({"color": {"field": keys[group_by], "title": group_by}} if group_by else {})}}})
    if payload["support"]:
        reference = payload["support"]["reference"]
        views.append({"type": "chart", "name": "Held out, outside the reference", "from": "support",
                      "chart": {"mark": "bar", "encoding": {
                          "y": {"field": "field", "title": None, "sort": "-x"},
                          "x": {"field": "unsupported_pct", "type": "quantitative",
                                "title": f"% of its records in cells {reference} never visits (whole set)"},
                          "color": {"field": "level", "title": "held out"}, "yOffset": {"field": "level"}}}})
    order = ["id", *(keys[name] for name in rail),
             *(keys[f["name"]] for f in payload["fields"] if f["kind"] == "number"),
             "missing", "new_cells", "unique_cells",
             *(keys[f["name"]] for f in payload["fields"] if f["kind"] != "number" and f["name"] not in rail
               and keys[f["name"]] != "id")]
    display = {keys[name]: "badge" for name in (group_by, split) if name}
    display["new_cells"] = "bar"
    views.append({"type": "table", "name": "Records", "order": list(dict.fromkeys(order)), "display": display})
    return views


_INDEX = """<!doctype html>
<!-- The record-coverage workbench, written by traj_compare.record_coverage.workbench (docs/RECORD_COVERAGE.md): one
     data-ui workbench element over coverage.base. Serve this folder (fetch and module scripts need http):
     python -m traj_compare.serve <this folder>  -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" href="data:,">  <!-- WHY: no /favicon.ico request, so the console stays clean -->
<link rel="stylesheet" href="{kit}/data-ui.css">
<style>
  html, body {{ margin: 0; }}
  body {{ font: 14px/1.4 system-ui, sans-serif; background: #fff; color: #1f2328; }}
  header {{ display: flex; align-items: baseline; gap: 12px; padding: 10px 16px 6px; min-width: 0; }}
  header h1 {{ font-size: 16px; margin: 0; white-space: nowrap; }}
  header p {{ margin: 0; color: #57606a; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  data-workbench {{ display: block; --data-height: calc(100vh - 44px); }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #111113; color: #e6edf3; }}
    header p {{ color: #9198a1; }}
  }}
</style>
</head>
<body>
<header><h1>{title}</h1><p title="{subtitle}">{subtitle}</p></header>
<data-workbench id="coverage" src="coverage.base" aria-label="{title}"></data-workbench>
<script type="module" src="{kit}/data-ui.js"></script>
</body>
</html>
"""

_EMBED = """<!doctype html>
<!-- The record-coverage workbench in a host app's 1000 x 680 slot (data-ui gallery/examples/coverage-workbench's host
     template): it draws nothing outside #host-slot; no-url leaves the host's URL alone. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Host app · {title}, embedded</title>
<link rel="icon" href="data:,">  <!-- WHY: no /favicon.ico request, so the console stays clean -->
<link rel="stylesheet" href="{kit}/data-ui.css">
<style>
  body {{ margin: 0; font: 14px system-ui, sans-serif; background: #eef0f3; color: #1f2328; }}
  #host-header {{ height: 48px; display: flex; align-items: center; gap: 16px; padding: 0 16px; background: #1f2937; color: #fff; }}
  #host-main {{ display: flex; }}
  #host-sidebar {{ width: 200px; min-height: calc(100vh - 48px); background: #fff; border-right: 1px solid #d0d7de; padding: 12px; box-sizing: border-box; }}
  #host-sidebar div {{ padding: 6px 8px; border-radius: 6px; color: #57606a; }}
  #host-sidebar div.on {{ background: #eef2ff; color: #1f2328; }}
  #host-content {{ padding: 20px; }}
  #host-content h2 {{ margin: 0 0 12px; font-size: 16px; }}
  #host-slot {{ width: 1000px; height: 680px; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; position: relative; }}
  #host-slot > data-workbench {{ height: 100%; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0d1117; color: #e6edf3; }}
    #host-sidebar, #host-slot {{ background: #111113; border-color: #30363d; }}
    #host-sidebar div {{ color: #9198a1; }}
    #host-sidebar div.on {{ background: #1f2a44; color: #e6edf3; }}
  }}
</style>
</head>
<body>
<div id="host-header"><b>Host app</b><span>Robots</span><span>Datasets</span><span>Reports</span></div>
<div id="host-main">
  <nav id="host-sidebar"><div>Robot</div><div class="on">Dataset coverage</div><div>Pick loop</div><div>Notes</div></nav>
  <main id="host-content">
    <h2>{title} (embedded)</h2>
    <div id="host-slot"><data-workbench id="embed" src="coverage.base" no-url aria-label="Record coverage workbench"></data-workbench></div>
  </main>
</div>
<script type="module" src="{kit}/data-ui.js"></script>
</body>
</html>
"""


def write_workbench(coverage, records: Sequence, out_dir: Path | str, *, title: str | None = None,
                    subtitle: str | None = None, kit: str | None = None, vendor: str = "main",
                    data_ui: Path | str = DATA_UI) -> Path:
    """Write the workbench into ``out_dir`` (the module docstring lists the files) and return its ``index.html``.

    ``kit`` is the href (relative to ``out_dir``) of a data-ui kit already vendored there; else ``vendor`` (a data-ui
    ref) is vendored into ``out_dir/vendor/data-ui`` from the ``data_ui`` checkout with data-ui's own command."""
    payload = _payload(coverage)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    record_rows, parts = workbench_rows(coverage, records)
    title = title or payload.get("title") or "Record coverage"
    subtitle = payload.get("subtitle", "") if subtitle is None else subtitle
    keys = _keys([f["name"] for f in payload["fields"]])
    rail = _rail(payload)
    _write_json(out / "records.json", {"id": "records", "title": f"{title}: records", "titleProperty": "id",
                                       "properties": _record_properties(payload, keys), "rows": record_rows})
    _write_json(out / "parts.json", {"id": "record-coverage-parts", "title": f"{title}: each cohort's share of every figure",
                                     "titleProperty": "id", "properties": _part_properties(), "rows": parts})
    _write_json(out / "growth.json", {"id": "record-coverage-growth", "title": f"{title}: growth (whole set)",
                                      "properties": {"series": {"type": "text", "label": "Series"},
                                                     "records": {"type": "number", "label": "Records added"},
                                                     "visited_pct": {"type": "number", "label": "Cells visited",
                                                                     "unitText": "%"}},
                                      "rows": _growth_rows(payload)})
    if payload["support"]:
        _write_json(out / "support.json", {"id": "record-coverage-support", "title": f"{title}: held-out support",
                                           "properties": {"level": {"type": "text", "label": "Held out"},
                                                          "field": {"type": "text", "label": "Field"},
                                                          "unsupported_pct": {"type": "number", "label": "Outside the reference",
                                                                              "unitText": "%"}},
                                           "rows": _support_rows(payload)})
    base = _base(payload, keys, rail, title=title)
    _files.write_text(out / "coverage.base", _HEADER + _yaml(base) + "\n")
    _files.write_text(out / "coverage.json", json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n")
    if kit is None:
        kit = _vendor(out, vendor, Path(data_ui))
    _files.write_text(out / "index.html", _INDEX.format(title=html.escape(title), subtitle=html.escape(subtitle),
                                                       kit=html.escape(kit.rstrip("/"))))
    _files.write_text(out / "embed.html", _EMBED.format(title=html.escape(title), kit=html.escape(kit.rstrip("/"))))
    return out / "index.html"
