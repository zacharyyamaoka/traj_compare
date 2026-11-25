"""Our page for grasp coverage: data-ui's stock ``<data-workbench>`` over a set of grasps (docs/GRASP_COVERAGE.md "Our
page"; data-ui docs/CONTRACT.md §52 coverage views, §53 scope + workbench, §32 scene3d layers).

    coverage = analyze_grasps(grasps, outcomes=outcomes, width_range=(0.0, 0.125), area=box, title="Repicks")
    write_grasp_workbench(coverage, grasps, "out/")      # or coverage.write_workbench("out/") (re-bins the payload's rows)
    python -m traj_compare.serve out/                    # then /index.html

Writes into ``out_dir``: ``grasps.json`` (one row per grasp: what the rail filters, the table lists and the charts and
the 3-D view draw), ``parts.json`` (one row per grasp and coverage figure, that grasp's share of it: a one-hot histogram
or one sparse cell), ``areas.json`` (the offered area's boxes, when given), ``grasp_coverage.base``, ``index.html``,
``embed.html`` (a host app's 1000 x 680 slot) and ``vendor/data-ui/`` (unless ``kit=``).

WHY a workbench and not a hand-rolled page: Zach, 2026-11-24, "the nice thing with data-ui is it's the common visual
language", and the trajectory workbench (coverage/workbench.py) proved the pattern; the `.base` writer, the vendoring
and the two HTML shells are that module's. WHY grasps in the rail and parts in the figures: as "the atomic unit here
is trajectories" for paths, a grasp is the unit here, so ticking "failed" must recount every figure; each part is
binned on the payload's own grids with the payload's own functions, so the parts add back up to it exactly.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .. import _files
from ..coverage import bins
from ..coverage.workbench import _EMBED, _INDEX, DATA_UI, _page, _parts_view, _vendor, _write_json, _yaml
from .analysis import ARROW_M, PROJECTIONS, SCHEMA, GraspValues, _named, grasp_values
from .colours import GROUP_SLOTS, SLOT_HEX, outcome_slots

DEG = 180.0 / math.pi
FACES = {"xy": "from above", "xz": "from the front", "yz": "from the side"}
PAGES = ("Overview", "Position", "Gripper", "Orientation", "Objects", "Grasps")
HIST_KINDS = ("width", "pre_grasp_width", "tilt", "roll", "score")  # the stock strips panel, top to bottom
LIMIT_HEX = "#b4442f"  # data-ui's --data-limit (light): a limit is a boundary, never a status
BEYOND_HEX = "#dddcd6"  # data-ui's --data-outside: past the range


# ── the rows ────────────────────────────────────────────────────────────────────────────────────────────────────────


def grasp_workbench_rows(coverage, grasps=None) -> tuple[list[dict], list[dict]]:
    """(grasp rows, part rows) for one ``analyze_grasps()`` result.

    ``grasps`` is what analyze_grasps() got (same names, same order), or None to re-bin the payload's own grasp rows
    (refused when the payload kept only an even pick of a huge set: its counts could not be rebuilt)."""
    payload = _payload(coverage)
    values = _values(payload, grasps)
    outcome_of = {row["name"]: row for row in payload["grasps"]}
    ids = _ids(values.names)
    rows = [_grasp_row(payload, values, k, ids[k], outcome_of[values.names[k]]) for k in range(len(values))]
    parts: list[dict] = []
    for k in range(len(values)):
        parts += _parts(payload, values, k, ids[k], outcome_of[values.names[k]]["group"])
    return rows, parts


def _payload(coverage) -> dict:
    payload = coverage.payload if hasattr(coverage, "payload") else coverage
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a grasp_coverage payload ({SCHEMA}): schema {payload.get('schema')!r}")
    return payload


def _values(payload: Mapping, grasps) -> GraspValues:
    reference = payload["orientation"]["reference"]
    names = [row["name"] for row in payload["grasps"]]
    if grasps is not None:
        named = _named(grasps)
        given = [name for name, _ in named]
        if payload["grasps_subsampled"] is None and given != names:
            raise ValueError(f"the grasps are not the payload's: {len(given)} given for {len(names)}"
                             + (f", first differing {next(a for a, b in zip(given, names) if a != b)!r}"
                                if len(given) == len(names) else ""))
        if len(given) != payload["source"]["grasps"]:
            raise ValueError(f"the grasps are not the payload's: {len(given)} given, it counted "
                             f"{payload['source']['grasps']}")
        return grasp_values(named, reference)
    if payload["grasps_subsampled"] is not None:
        raise ValueError(f"the payload keeps {payload['grasps_subsampled']} of {payload['source']['grasps']} grasps; "
                         "pass the grasps themselves so every figure can be recounted")
    rows = payload["grasps"]
    column = lambda key: np.array([row[key] for row in rows], float)  # noqa: E731
    optional = lambda key: np.array([np.nan if row[key] is None else row[key] for row in rows], float)  # noqa: E731
    return GraspValues(names=names, objects=[row["object_id"] for row in rows],
                       positions=np.array([row["position"] for row in rows], float),
                       approach=np.array([row["approach"] for row in rows], float),
                       jaw=np.array([row["jaw"] for row in rows], float), width=column("width"),
                       pre_grasp_width=optional("pre_grasp_width"), score=optional("score"), tilt=column("tilt"),
                       azimuth=column("azimuth"), roll=column("roll"), frame=payload["source"]["frame"])


def _ids(names: list[str]) -> list[str]:
    if len(set(names)) == len(names):
        return list(names)
    return [f"{name} #{k}" for k, name in enumerate(names)]


def _grasp_row(payload: Mapping, values: GraspValues, k: int, grasp_id: str, payload_row: Mapping) -> dict:
    position = values.positions[k] * 1000.0
    tail = position - ARROW_M * 1000.0 * values.approach[k]
    row: dict[str, Any] = {"id": grasp_id, "name": values.names[k], "object": values.objects[k],
                           "outcome": payload_row["outcome"]}
    for key, value in payload_row["tags"].items():
        if key not in row:
            row[key] = value
    row.update({
        "width_mm": round(float(values.width[k]) * 1000.0, 2),
        "pre_grasp_mm": None if not np.isfinite(values.pre_grasp_width[k]) else round(float(values.pre_grasp_width[k])
                                                                                       * 1000.0, 2),
        "score": None if not np.isfinite(values.score[k]) else round(float(values.score[k]), 4),
        "tilt_deg": round(float(values.tilt[k]) * DEG, 2),
        "azimuth_deg": round(float(values.azimuth[k]) * DEG, 2),
        "roll_deg": round(float(values.roll[k]) * DEG, 2),
        "roll_folded_deg": round(float(np.mod(values.roll[k], math.pi)) * DEG, 2),
        "x_mm": round(float(position[0]), 2), "y_mm": round(float(position[1]), 2), "z_mm": round(float(position[2]), 2),
        "from_x_mm": round(float(tail[0]), 2), "from_y_mm": round(float(tail[1]), 2),
        "from_z_mm": round(float(tail[2]), 2),
        # WHY a t of 0: data-ui's scene3d windows every primitive by a numeric t and drops a row without one
        # (scene3d bind.js); a grasp set has no clock, so every grasp stands at the same instant
        "t": 0.0,
    })
    return row


def _one_hot(index: int, bins_: int) -> list[int]:
    counts = [0] * bins_
    if index >= 0:
        counts[index] = 1
    return counts


def _hist_part(grasp_id: str, kind: str, value: float, edges, group: str, **extra) -> dict:
    low, high, count = edges
    index = int(bins.bin_index(np.array([value]), low, high, count)[0])
    one = _one_hot(index, count)
    return {"id": f"{grasp_id}/{kind}", "kind": kind, "grid": kind, "grasp": grasp_id, "hist_order": HIST_KINDS.index(kind),
            "lo": low, "hi": high, "bins": count, "counts": one, "groups": [group], "group_counts": [one], **extra}


def _grid_part(grasp_id: str, kind: str, grid: str, cell: int, geometry: dict, **extra) -> dict | None:
    if cell < 0:
        return None
    return {"id": f"{grasp_id}/{kind}/{grid}", "kind": kind, "grid": grid, "grasp": grasp_id, **geometry,
            "at": [int(cell)], "samples": [1], **extra}


def _parts(payload: Mapping, values: GraspValues, k: int, grasp_id: str, group: str) -> list[dict]:
    parts: list[dict | None] = []
    position = payload["position"]
    pixel = float(position["pixel_m"])
    for face, axes in PROJECTIONS.items():
        block = position["projections"][face]
        cell = int(bins.grid_cells_on(values.positions[k:k + 1], block["origin"], block["shape"], pixel, axes)[0])
        names = "xyz"
        parts.append(_grid_part(grasp_id, "projection", face, cell, {
            "u": names[axes[0]], "v": names[axes[1]], "origin_u": block["origin"][0], "origin_v": block["origin"][1],
            "pixel_m": pixel, "nu": block["shape"][0], "nv": block["shape"][1]},
            title=f"{FACES[face]} ({names[axes[0]]}, {names[axes[1]]})", frame=payload["source"]["frame"]))

    gripper = payload["gripper"]
    limits: dict[str, Any] = {"scale": 1000.0, "unit": "mm"}
    if gripper["source"] == "limit":
        limits.update(low=gripper["low"], high=gripper["high"], limit_source="limit")
    else:
        limits.update(limit_source="data")
    if gripper["planner_high"] is not None:
        limits.update(planner_low=gripper["planner_low"], planner_high=gripper["planner_high"])
    width_edges = payload["width"]["edges"]
    width = float(values.width[k])
    outside = int(gripper["source"] == "limit" and (width < gripper["low"] - 1e-9 * (gripper["high"] - gripper["low"])
                                                   or width > gripper["high"] + 1e-9 * (gripper["high"] - gripper["low"])))
    parts.append(_hist_part(grasp_id, "width", width, width_edges, group, label="jaw width", outside=outside, **limits))
    if payload["pre_grasp_width"] is not None and np.isfinite(values.pre_grasp_width[k]):
        parts.append(_hist_part(grasp_id, "pre_grasp_width", float(values.pre_grasp_width[k]), width_edges, group,
                                label="pre-grasp opening", **limits))
    orientation = payload["orientation"]
    angle = {"scale": DEG, "unit": "°"}
    parts.append(_hist_part(grasp_id, "tilt", float(values.tilt[k]), orientation["tilt"]["edges"], group,
                            label="tilt from straight down", **angle))
    shown = orientation["roll_shown"]
    roll = float(values.roll[k]) if shown == "roll" else float(np.mod(values.roll[k], math.pi))
    parts.append(_hist_part(grasp_id, "roll", roll, orientation[shown]["edges"], group,
                            label="roll about the approach" + (" (folded)" if shown == "roll_folded" else ""), **angle))
    if payload["score"] is not None and np.isfinite(values.score[k]):
        parts.append(_hist_part(grasp_id, "score", float(values.score[k]), payload["score"]["edges"], group,
                                label="the detector's score"))

    def plane(kind: str, x_value, x_edges, y_value, y_edges, **labels) -> None:
        x_index = int(bins.bin_index(np.array([x_value]), *x_edges)[0])
        y_index = int(bins.bin_index(np.array([y_value]), *y_edges)[0])
        cell = x_index * y_edges[2] + y_index if x_index >= 0 and y_index >= 0 else -1
        parts.append(_grid_part(grasp_id, kind, kind, cell, {
            "x_lo": x_edges[0], "x_hi": x_edges[1], "nx": x_edges[2], "y_lo": y_edges[0], "y_hi": y_edges[1],
            "ny": y_edges[2]}, **labels))

    tilt_edges = orientation["tilt_azimuth"]["tilt_edges"]
    plane("pointing", float(values.azimuth[k]), orientation["tilt_azimuth"]["azimuth_edges"], float(values.tilt[k]),
          tilt_edges, x="azimuth", y="tilt", x_label="which way it leans", y_label="tilt from straight down",
          x_scale=DEG, y_scale=DEG, x_unit="°", y_unit="°", reference=list(orientation["reference"]), box="none",
          zero="none")
    sphere = orientation["sphere"]
    sphere_cell = int(bins.sphere_cell(values.approach[k:k + 1], sphere["rings"], sphere["sectors"])[0])
    ring, sector = divmod(sphere_cell, sphere["sectors"])
    parts.append(_grid_part(grasp_id, "sphere", "sphere", sector * sphere["rings"] + ring, {
        "x_lo": -math.pi, "x_hi": math.pi, "nx": sphere["sectors"], "y_lo": -1.0, "y_hi": 1.0, "ny": sphere["rings"]},
        x="azimuth", y="approach z", x_label="which way it leans", y_label="approach z (−1 = straight down; equal-area rows)",
        x_scale=DEG, x_unit="°", box="none", zero="none"))
    plane("tilt_roll", roll, orientation["tilt_roll"]["roll_edges"], float(values.tilt[k]), tilt_edges,
          x="roll", y="tilt", x_label="roll about the approach", y_label="tilt from straight down", x_scale=DEG,
          y_scale=DEG, x_unit="°", y_unit="°", box="none", zero="none")
    width_tilt = payload["width_tilt"]
    plane("width_tilt", width, width_tilt["x_edges"], float(values.tilt[k]), width_tilt["y_edges"], x="width",
          y="tilt", x_label="jaw width", y_label="tilt from straight down", x_scale=1000.0, y_scale=DEG, x_unit="mm",
          y_unit="°", box="none", zero="none")
    return [part for part in parts if part is not None]


# ── the files ───────────────────────────────────────────────────────────────────────────────────────────────────────


def write_grasp_workbench(coverage, grasps, out_dir: Path | str, *, title: str | None = None,
                          subtitle: str | None = None, dataset_label: str | None = None,
                          facets: Sequence[str] | None = None, kit: str | None = None, vendor: str = "main",
                          data_ui: Path | str = DATA_UI) -> Path:
    """Write the workbench into ``out_dir`` (see the module docstring) and return its ``index.html``.

    ``grasps``: what analyze_grasps() got, or None (re-bin the payload's rows). ``facets``: the tags the rail lists
    after Object and Outcome (default every tag, first seen first). ``dataset_label`` names the data in the header.
    ``kit`` reuses a data-ui kit already vendored (an href relative to ``out_dir``); else ``vendor`` (a data-ui ref)
    is vendored from the ``data_ui`` checkout with data-ui's own ``vendor`` command."""
    payload = _payload(coverage)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, parts = grasp_workbench_rows(payload, grasps)
    title = title or payload.get("title") or "Grasp coverage"
    subtitle = payload.get("subtitle", "") if subtitle is None else subtitle
    if dataset_label:
        subtitle = f"{dataset_label} · {subtitle}" if subtitle else dataset_label
    tag_keys = list(dict.fromkeys(key for row in payload["grasps"] for key in row["tags"]))
    facets = tag_keys if facets is None else [key for key in facets if key in tag_keys]

    _write_json(out / "grasps.json", {"id": "grasp-coverage-grasps", "title": f"{title}: grasps", "titleProperty": "name",
                                      "properties": _grasp_properties(payload, tag_keys), "rows": rows})
    _write_json(out / "parts.json", {"id": "grasp-coverage-parts", "title": f"{title}: each grasp's share of every figure",
                                     "titleProperty": "id", "properties": _part_properties(), "rows": parts})
    areas = payload["position"]["area"] or []
    base = _base(payload, rows, facets=facets, areas=bool(areas))
    _files.write_text(out / "grasp_coverage.base", _HEADER + _yaml(base) + "\n")
    if kit is None:
        kit = _vendor(out, vendor, Path(data_ui))
    index = _INDEX.replace("coverage.base", "grasp_coverage.base").replace(
        "traj_compare.coverage.workbench (docs/COVERAGE.md \"The workbench\")",
        "traj_compare.grasp_coverage.workbench (docs/GRASP_COVERAGE.md \"Our page\")")
    embed = _EMBED.replace("coverage.base", "grasp_coverage.base").replace("Trajectory coverage", "Grasp coverage")
    _files.write_text(out / "index.html", index.format(title=html.escape(title), subtitle=html.escape(subtitle),
                                                       kit=html.escape(kit.rstrip("/"))))
    _files.write_text(out / "embed.html", embed.format(title=html.escape(title), kit=html.escape(kit.rstrip("/"))))
    return out / "index.html"


def _grasp_properties(payload: Mapping, tag_keys: list[str]) -> dict:
    properties: dict[str, Any] = {
        "id": {"type": "text", "label": "Grasp", "hidden": True}, "name": {"type": "text", "label": "Grasp"},
        "object": {"type": "text", "label": "Object"}, "outcome": {"type": "text", "label": "Outcome"},
    }
    for key in tag_keys:
        properties.setdefault(key, {"type": "text", "label": key.replace("_", " ").capitalize()})
    properties.update({
        "width_mm": {"type": "number", "label": "Jaw width", "unitText": "mm", "decimals": 1},
        "pre_grasp_mm": {"type": "number", "label": "Pre-grasp opening", "unitText": "mm", "decimals": 1},
        "score": {"type": "number", "label": "Score", "decimals": 3},
        "tilt_deg": {"type": "number", "label": "Tilt", "unitText": "°", "decimals": 1,
                     "description": "angle between the approach and straight down"},
        "azimuth_deg": {"type": "number", "label": "Leans toward", "unitText": "°", "decimals": 0},
        "roll_deg": {"type": "number", "label": "Roll", "unitText": "°", "decimals": 1,
                     "description": "the jaw axis about the approach, counter-clockwise seen from behind the gripper"},
        "roll_folded_deg": {"type": "number", "label": "Roll, folded", "unitText": "°", "decimals": 1,
                            "description": "roll mod 180°: a two-finger grasp and its jaws-swapped twin", "hidden": True},
    })
    for axis in "xyz":
        properties[f"{axis}_mm"] = {"type": "number", "label": axis, "unitText": "mm", "decimals": 1}
        properties[f"from_{axis}_mm"] = {"type": "number", "label": f"approach from {axis}", "unitText": "mm",
                                         "decimals": 1, "hidden": True}
    properties["t"] = {"type": "number", "label": "t", "hidden": True}
    if payload["pre_grasp_width"] is None:
        del properties["pre_grasp_mm"]
    if payload["score"] is None:
        del properties["score"]
    return properties


def _part_properties() -> dict:
    hidden_list = {"type": "list", "hidden": True}
    properties: dict[str, Any] = {
        "id": {"type": "text", "label": "Part"}, "kind": {"type": "text", "label": "Figure"},
        "grid": {"type": "text", "label": "Grid"}, "grasp": {"type": "text", "label": "Grasp"},
        "label": {"type": "text", "label": "Histogram"}, "title": {"type": "text", "label": "Seen"},
        "at": {**hidden_list, "label": "cells visited"}, "samples": {**hidden_list, "label": "grasps per cell"},
        "counts": hidden_list, "groups": hidden_list, "group_counts": hidden_list, "reference": hidden_list,
    }
    for key in ("x", "y", "x_label", "y_label", "x_unit", "y_unit", "box", "zero", "u", "v", "frame", "limit_source",
                "unit"):
        properties[key] = {"type": "text", "hidden": True}
    for key in ("x_lo", "x_hi", "nx", "y_lo", "y_hi", "ny", "x_scale", "y_scale", "outside", "lo", "hi", "bins", "hist_order",
                "low", "high", "planner_low", "planner_high", "scale", "pixel_m", "origin_u", "origin_v", "nu", "nv"):
        properties[key] = {"type": "number", "hidden": True}
    return properties


# ── grasp_coverage.base ─────────────────────────────────────────────────────────────────────────────────────────────

_HEADER = """# The grasp coverage workbench: data-ui's <data-workbench> over these grasps (data-ui docs/CONTRACT.md §52, §53, §32).
# GENERATED by traj_compare.grasp_coverage.workbench.write_grasp_workbench (docs/GRASP_COVERAGE.md "Our page"): change
# the writer, never this file. The rail filters grasps, Object and Outcome first; every tab is a dashboard over what the
# rail keeps, and each coverage figure adds up the kept grasps' part rows (coverage.sum), so ticking "failed" recounts
# every tab. The gear sets the heatmap colours for every tab at once.
#
# WHY the outcome colours: the Nov 19 gallery's (blue picked, orange failed, grey never closed), which Zach called
# "super helpful" for "showing where the failures where and not".
"""


def _base(payload: Mapping, rows: list[dict], *, facets: Sequence[str], areas: bool) -> dict:
    order = payload["outcomes"]["order"]
    objects = payload["source"]["objects"]
    slots = outcome_slots(order)
    rail: list[dict[str, Any]] = [{"property": "object", "label": "Object", "order": objects},
                                  {"property": "outcome", "label": "Outcome", "order": order}]
    for key in facets:
        values = list(dict.fromkeys(row.get(key) for row in rows if row.get(key) is not None))
        if values:
            rail.append({"property": key, "label": key.replace("_", " ").capitalize()})
    rail.append({"property": "name", "as": "search", "label": "Find a grasp", "placeholder": f"e.g. {rows[0]['name']}"})
    rail.append({"property": "width_mm", "as": "slider-histogram", "label": "Jaw width", "unit": "mm", "collapsed": True})
    rail.append({"property": "tilt_deg", "as": "slider-histogram", "label": "Tilt", "unit": "°", "collapsed": True})
    if payload["score"] is not None:
        rail.append({"property": "score", "as": "slider-histogram", "label": "Score", "collapsed": True})

    group_by = payload["source"]["group_by"]
    if group_by == "outcome":
        family = slots
    else:
        family = {name: GROUP_SLOTS[i % len(GROUP_SLOTS)] for i, name in enumerate(payload["source"]["groups"])}
    datasets: dict[str, Any] = {"parts": {"data": "parts.json", "label": "Coverage parts"}}
    return {
        "data": "grasps.json",
        "noun": ["grasp", "grasps"],
        "facets": rail,
        "properties": {"name": {"displayName": "Grasp"}, "object": {"displayName": "Object"},
                       "outcome": {"displayName": "Outcome", "colors": slots}},
        "style": {"numbers": {"digits": 3},
                  # the histograms stack by the payload's group_by, in the rail's outcome colours
                  "families": {"property": group_by, "colors": family},
                  "heatmap": {"colormap": "viridis", "reverse": False, "scale": "linear"}},
        "settings": ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"],
        "drill": {"actions": [{"label": "Copy its name", "copy": "{name}", "title": "Copies {name}"}]},
        "datasets": datasets,
        "links": [{"from": "grasps.id", "to": "parts.grasp", "direction": "one-way"}],
        "pages": _pages(payload, areas),
        "views": _views(payload, rows, slots, areas),
    }


def _pages(payload: Mapping, areas: bool) -> list[dict]:
    pages = [
        # WHY this order: the grid fills row by row, so the right column (widths, then objects) runs as tall as the top
        # view beside it, and the second row pairs the approach disk with the roll line
        _page("Overview", [
            {"view": "Where the gripper closed", "w": 5, "h": 5},
            {"view": "Jaw width against the claw", "w": 7, "h": 3},
            {"view": "Grasps per object", "w": 7, "h": 2},
            {"view": "Which way it approaches", "w": 5, "h": 4},
            {"view": "Roll about the approach", "w": 7, "h": 4},
        ]),
        _page("Position", [
            {"view": "In 3-D", "w": 7, "h": 6},
            {"view": "Where the gripper closed", "w": 5, "h": 3},
            {"view": "Seen from the side", "w": 5, "h": 3},
            {"view": "The grasps from three sides", "w": 12, "h": 4, "style": {"title": "none"}},
        ]),
        _page("Gripper", [panel for panel in (
            {"view": "Jaw width against the claw", "w": 12, "h": 3},
            {"view": "Pre-grasp opening", "w": 12, "h": 3} if payload["pre_grasp_width"] is not None else None,
            {"view": "Every histogram against its range", "w": 7, "h": 4},
            {"view": "Width × tilt", "w": 5, "h": 4},
        ) if panel]),
        _page("Orientation", [
            {"view": "Which way it approaches", "w": 5, "h": 5},
            {"view": "Every approach, equal area", "w": 7, "h": 5},
            {"view": "Roll about the approach", "w": 7, "h": 3},
            {"view": "Tilt from straight down", "w": 5, "h": 3},
            {"view": "Tilt × roll", "w": 12, "h": 4},
        ]),
        _page("Objects", [
            {"view": "Grasps per object", "w": 7, "h": 5},
            {"view": "Outcome share per object", "w": 5, "h": 5},
        ]),
        _page("Grasps", [{"view": "Grasps", "w": 12, "h": 6, "style": {"title": "none"}}]),
    ]
    return pages


def _colour_scale(slots: Mapping[str, int]) -> dict:
    # WHY explicit hex (light theme tokens): a Vega-Lite chart picks its own category colours otherwise, and an outcome
    # must be one colour in the rail, the badges, the stacked bars and the dots
    return {"domain": list(slots), "range": [SLOT_HEX[slot] for slot in slots.values()]}


def _views(payload: Mapping, rows: list[dict], slots: Mapping[str, int], areas: bool) -> list[dict]:
    colour = {"field": "outcome", "title": "Outcome", "scale": _colour_scale(slots), "sort": list(slots)}
    # WHY a linear scale said out loud: left to itself the chart drew y on a log axis and dropped every negative y
    point = {"type": "quantitative", "scale": {"type": "linear", "zero": False}}
    views: list[dict] = [
        # WHY a chart first: a view drawn alone (a gallery picture, a link to one view) reads the file's own rows
        {"type": "chart", "name": "Where the gripper closed", "chart": {
            "mark": {"type": "point", "filled": True, "size": 26, "opacity": 0.85},
            "encoding": {"x": {"field": "x_mm", "title": "x (mm)", **point}, "y": {"field": "y_mm", "title": "y (mm)",
                                                                                   **point},
                         "color": colour, "tooltip": [{"field": "name"}, {"field": "object"}, {"field": "outcome"},
                                                      {"field": "width_mm", "title": "width (mm)"}]}}},
        {"type": "chart", "name": "Seen from the side", "chart": {
            "mark": {"type": "point", "filled": True, "size": 26, "opacity": 0.85},
            "encoding": {"x": {"field": "x_mm", "title": "x (mm)", **point}, "y": {"field": "z_mm", "title": "z (mm)",
                                                                                   **point},
                         "color": colour, "tooltip": [{"field": "name"}, {"field": "outcome"}]}}},
        {"type": "chart", "name": "Grasps per object", "chart": {
            "mark": "bar", "encoding": {"y": {"field": "object", "title": None, "sort": "-x"},
                                        "x": {"aggregate": "count", "title": "grasps"}, "color": colour}}},
        {"type": "chart", "name": "Outcome share per object", "chart": {
            "mark": "bar", "encoding": {"y": {"field": "object", "title": None},
                                        "x": {"aggregate": "count", "stack": "normalize", "title": "share of its grasps"},
                                        "color": colour}}},
    ]
    # WHY density this high: scene3d draws `density` markers per path (default 20) and one colour is one path here
    layers: list[dict[str, Any]] = [
        {"primitive": "points", "x": "x_mm", "y": "y_mm", "z": "z_mm", "color": "outcome", "density": 100000},
        {"primitive": "arrows", "from": ["from_x_mm", "from_y_mm", "from_z_mm"], "to": ["x_mm", "y_mm", "z_mm"],
         "color": "outcome", "density": 100000},
    ]
    # WHY perspective: data-ui's face and {dir} projections are orthographic, where a drag pans and nothing rotates;
    # a grasp set is read by orbiting it (DROID's scene views)
    stage: dict[str, Any] = {"unit": "mm", "projection": "perspective", "show": "all", "axes": "auto",
                             "layers": layers}
    area = payload["position"]["area"]
    if area:
        # WHY the outer box, not a box per area: a campaign offers one look area per run (174 on the repicks); their
        # boxes drawn one by one buried the grasps
        low = np.min([lo for lo, _ in area], axis=0) * 1000.0
        high = np.max([hi for _, hi in area], axis=0) * 1000.0
        stage["workspace"] = {"box": [[round(float(v), 1) for v in low], [round(float(v), 1) for v in high]],
                              "opacity": 0.06}
    views.append({"type": "scene3d", "name": "In 3-D", "scene3d": stage})
    reach = max(90, min(180, 30 * math.ceil(max(_number(payload, "tilt_max_deg"), 1.0) / 30.0 + 1e-6)))
    views += [
        _parts_view("coverage-projection", "The grasps from three sides", 'kind == "projection"'),
        _parts_view("coverage-hist", "Every histogram against its range", " || ".join(
            f'kind == "{kind}"' for kind in HIST_KINDS), {"columns": 1}, ["hist_order"]),
        _parts_view("coverage-plane", "Width × tilt", 'kind == "width_tilt"'),
        _parts_view("coverage-polar", "Which way it approaches", 'kind == "pointing"', {"reach": reach}),
        _parts_view("coverage-plane", "Every approach, equal area", 'kind == "sphere"'),
        _parts_view("coverage-plane", "Tilt × roll", 'kind == "tilt_roll"'),
    ]
    gripper = payload["gripper"]
    width_low, width_high, width_bins = payload["width"]["edges"]
    width_marks = []
    if gripper["source"] == "limit":
        width_marks += [("band", width_low * 1000, gripper["low"] * 1000, ""),
                        ("band", gripper["high"] * 1000, width_high * 1000, ""),
                        ("rule", gripper["high"] * 1000, None, f"open stop {gripper['high'] * 1000:.0f} mm")]
    if gripper["planner_high"] is not None:
        width_marks.append(("dashed", gripper["planner_high"] * 1000, None,
                            f"planner span {gripper['planner_high'] * 1000:.0f} mm"))
    width_edges_mm = (width_low * 1000, width_high * 1000, width_bins)
    views.append(_hist_chart("Jaw width against the claw", "width_mm", "jaw width the grasp closes to (mm)",
                             width_edges_mm, colour, width_marks))
    if payload["pre_grasp_width"] is not None:
        views.append(_hist_chart("Pre-grasp opening", "pre_grasp_mm", "jaw opening before the approach (mm)",
                                 width_edges_mm, colour, width_marks))
    orientation = payload["orientation"]
    shown = orientation["roll_shown"]
    low, high, count = orientation[shown]["edges"]
    roll_field = "roll_folded_deg" if shown == "roll_folded" else "roll_deg"
    views.append(_hist_chart("Roll about the approach", roll_field, "roll of the jaws about the approach (°)"
                             + (", folded: r and r + 180° are one grasp" if shown == "roll_folded" else ", full circle"),
                             (low * DEG, high * DEG, count), colour, []))
    low, high, count = orientation["tilt"]["edges"]
    views.append(_hist_chart("Tilt from straight down", "tilt_deg", "tilt of the approach from straight down (°)",
                             (low * DEG, high * DEG, count), colour, [("dashed", 90.0, None, "level")]))
    present = {key for row in rows for key in row}
    tag_keys = [key for row in payload["grasps"] for key in row["tags"]]
    order = [key for key in ("name", "object", "outcome", *tag_keys, "width_mm", "pre_grasp_mm", "tilt_deg",
                             "roll_deg", "azimuth_deg", "score", "x_mm", "y_mm", "z_mm") if key in present]
    views.append({"type": "table", "name": "Grasps", "order": list(dict.fromkeys(order)),
                  "display": {"outcome": "badge", "object": "badge"}})
    return views


def _hist_chart(name: str, field: str, title: str, edges, colour: Mapping, marks) -> dict:
    """A Vega-Lite histogram of a grasps.json column on the payload's own linear bins, stacked by outcome, with the
    range drawn as `marks`: ("band", lo, hi, "") grey beyond the range, ("rule" | "dashed", at, None, label) a red limit.

    WHY a chart and not data-ui's coverage-hist here: its strips are 58 px tall (built for a stack of limit bars), and
    this is the figure Zach singled out ("I really like this how it shows the size of the grasps"); the strips stay, as
    one panel, on the Gripper tab. WHY every fixed mark aggregates first: a mark per grasp row would draw the same line
    a thousand times."""
    low, high, count = edges
    one = [{"aggregate": [{"op": "count", "as": "n"}]}]
    # WHY round ticks: a binned axis ticks at the bin edges (-10, -2, 6, 14 ... on a 2 mm width bin)
    span = high - low
    step = next(step for step in (5, 10, 20, 30, 45, 60, 90, 100, 200) if span / step <= 10)
    ticks = [round(v, 6) for v in np.arange(math.ceil(low / step) * step, high + 1e-9, step)]
    x = {"title": title}
    # WHY the bars first: data-ui's chart treats the first layer with an x or y as the chart itself (its legend, its
    # hidden-series filter, its defaults); with the grey band first the bars were never drawn
    layers: list[dict[str, Any]] = []
    # WHY cornerRadiusEnd 0: Vega-Lite 6.5 drops x from a binned bar when a corner radius applies (data-ui's theme sets
    # one) and the bars vanish; data-ui's own histograms square their ends for the same reason (chart index.js zeroBins)
    layers.append({"mark": {"type": "bar", "binSpacing": 0, "clip": True, "cornerRadiusEnd": 0}, "encoding": {
        "x": {"field": field, "bin": {"extent": [round(low, 4), round(high, 4)], "step": round((high - low) / count, 6)},
              **x, "scale": {"domain": [round(low, 4), round(high, 4)]}, "axis": {"values": ticks}},
        "y": {"aggregate": "count", "title": "grasps"}, "color": colour,
        "tooltip": [{"field": field, "bin": True, "title": title}, {"aggregate": "count", "title": "grasps"},
                    {"field": "outcome"}]}})
    for kind, at, to, label in marks:
        if kind == "band":  # past the range, drawn over the bars but see-through: a grasp out there still shows
            layers.append({"mark": {"type": "rect", "color": BEYOND_HEX, "opacity": 0.55}, "transform": one,
                           "encoding": {"x": {"datum": round(at, 3), **x}, "x2": {"datum": round(to, 3)}}})
    for kind, at, to, label in marks:
        if kind == "band":
            continue
        style = {"strokeDash": [4, 3]} if kind == "dashed" else {}
        layers.append({"mark": {"type": "rule", "color": LIMIT_HEX, "strokeWidth": 1.5, **style}, "transform": one,
                       "encoding": {"x": {"datum": round(at, 3), **x}}})
        layers.append({"mark": {"type": "text", "color": LIMIT_HEX, "align": "left", "baseline": "top", "dx": 4, "y": 4,
                                "fontSize": 11}, "transform": one,
                       "encoding": {"x": {"datum": round(at, 3), **x}, "text": {"value": label}}})
    off = [{"filter": f"datum['{field}'] > {round(high, 4)} || datum['{field}'] < {round(low, 4)}"}, *one,
           {"filter": "datum.n > 0"}, {"calculate": "datum.n + ' off the chart'", "as": "label"}]
    layers.append({"mark": {"type": "text", "color": LIMIT_HEX, "align": "right", "baseline": "top", "dx": -4, "y": 4,
                            "fontSize": 11}, "transform": off,
                   "encoding": {"x": {"datum": round(high, 3), **x}, "text": {"field": "label"}}})
    return {"type": "chart", "name": name, "chart": {"layer": layers}}


def _number(payload: Mapping, key: str, default: float = 0.0) -> float:
    for entry in payload.get("numbers", []):
        if entry["key"] == key:
            return float(entry["value"])
    return default
