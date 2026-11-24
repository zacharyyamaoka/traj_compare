#!/usr/bin/env python3
"""V7's rows (V3's rows.py plus the equal-area sphere row): the coverage payload reshaped into data-ui row tables,
nothing recomputed.

    python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v7/rows.py

Reads ../data/coverage.json (traj_compare.coverage/1, docs/COVERAGE.md) and ../data/trajectories.json; writes
rows/<table>.json in data-ui's runtime dataset shape ({id, title, titleProperty, properties, rows}; data-ui
docs/CONTRACT.md §3). Every number is the payload's own: values are copied, renamed and regrouped, and the only
arithmetic is (a) a unit change for display columns (rad -> deg, the payload's own `display.scale`) and (b) a cell's
centre from the payload's own lattice (origin + (i + 0.5) * size) for the stock voxels view, which reads centres.

WHY "one row per grid" and not "one row per cell" (the choice NOTES.md defends): data-ui's row model is for things a
reader filters, sorts, groups and opens. A reader picks a joint, a plane, a signal, a projection: those are rows. Nobody
filters one bin of a 36 x 24 grid, and 13 824 plane cells pushed through the row model on every pick buy nothing. So a
grid is one row whose scalars (joint, plane, visited %, the limit box) are ordinary columns a table, a facet or a KPI
can read, and whose counts ride along as list cells (the row model allows lists, CONTRACT §2). The exception is the
tool's voxels: data-ui's stock `voxels` view (§32) reads pre-gridded rows, one per cell, so there they are cells.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = HERE / "rows"

SIGNAL_WORD = {"q": "position", "qd": "speed", "qdd": "acceleration", "qddd": "jerk"}
POWER = {"q": "", "qd": "/s", "qdd": "/s²", "qddd": "/s³"}
GRID_ORDER = {"q_qd": 0, "qd_qdd": 1, "q_qdd": 2}


def short(joint: str) -> str:
    return joint[:-6] if joint.endswith("_joint") else joint


def unit_of(joint: dict, signal: str) -> str:
    base = "°" if joint["display"]["unit"] == "deg" else joint["display"]["unit"]
    return base + POWER[signal]


def edges(spec: list) -> dict:
    lo, hi, n = spec
    return {"lo": lo, "hi": hi, "n": int(n)}


def write(name: str, title: str, properties: dict, rows: list, title_property: str | None = None) -> None:
    OUT.mkdir(exist_ok=True)
    doc = {"id": f"coverage-{name}", "title": title, "titleProperty": title_property or next(iter(properties)),
           "properties": properties, "rows": rows}
    (OUT / f"{name}.json").write_text(json.dumps(doc, allow_nan=False, separators=(",", ":")) + "\n")
    print(f"rows/{name}.json  {len(rows):6d} rows")


def grid_props(extra: dict | None = None) -> dict:
    """The grid-row shape every coverage-plane row shares (PROPOSED-CONTRACT.md "the grid row")."""
    hidden = {"type": "list", "hidden": True}
    props = {
        "id": {"type": "text", "label": "Grid"},
        "x": {"type": "text", "label": "x"}, "y": {"type": "text", "label": "y"},
        "x_label": {"type": "text", "label": "x axis"}, "y_label": {"type": "text", "label": "y axis"},
        "x_lo": {"type": "number"}, "x_hi": {"type": "number"}, "nx": {"type": "number"},
        "y_lo": {"type": "number"}, "y_hi": {"type": "number"}, "ny": {"type": "number"},
        "x_scale": {"type": "number"}, "y_scale": {"type": "number"},
        "x_unit": {"type": "text"}, "y_unit": {"type": "text"},
        "samples": hidden, "paths": hidden, "max_other": hidden,
        "visited_pct": {"type": "number", "label": "Cells visited", "unitText": "%", "decimals": 0},
        "sufficient_pct": {"type": "number", "label": "Cells with enough", "unitText": "%", "decimals": 0},
        "evenness_pct": {"type": "number", "label": "Evenness", "unitText": "%", "decimals": 0},
        "outside": {"type": "number", "label": "Samples outside the box"},
        "cells": {"type": "number", "label": "Cells"},
        "enough": {"type": "number", "label": "Enough (samples)"},
    }
    props.update(extra or {})
    return props


def main() -> None:
    payload = json.loads((DATA / "coverage.json").read_text())
    trajectories = json.loads((DATA / "trajectories.json").read_text())
    joints = payload["joints"]
    enough = payload["enough"]
    groups = payload["source"]["groups"] or []
    group_by = payload["source"]["group_by"]

    # ── numbers: the headline scalars, one row each (the stock kpi view, Overview only) ────────────────────────────
    sections = {"trajectories": "Dataset", "samples": "Dataset", "duration_s": "Dataset"}
    for n in payload["numbers"]:
        key = n["key"]
        sections.setdefault(key, "Tool" if key.startswith("tool_") else "Joints")
    unit_text = {"%": "%", "s": "s", "m/s": "m/s", "deg": "°", "": ""}
    rows = []
    for order, n in enumerate(payload["numbers"]):
        rows.append({"id": n["key"], "key": n["key"], "label": n["label"], "section": sections[n["key"]], "order": order,
                     "value": {"value": n["value"], "unit": unit_text.get(n["unit"], n["unit"]),
                               "note": f"payload numbers.{n['key']} (traj_compare.coverage.analyze)"}})
    write("numbers", "Headline numbers", {
        "label": {"type": "text", "label": "Number"}, "key": {"type": "text", "label": "Key"},
        "section": {"type": "text", "label": "Section"}, "order": {"type": "number"},
        "value": {"type": "number", "label": "Value", "digits": 3}}, rows, "label")

    # ── joints: one row per joint, the overview table (every number is a payload field) ────────────────────────────
    rows = []
    for order, j in enumerate(joints):
        name = j["name"]
        h = payload["hist"][name]
        lim = payload["limits"][name]
        sc = j["display"]["scale"]
        rows.append({
            "id": name, "joint": name, "order": order, "kind": j["kind"],
            "q_low": lim["q"]["low"] * sc, "q_high": lim["q"]["high"] * sc, "q_limit": lim["q"]["kind"] or lim["q"]["source"],
            "range_used_pct": h["q"]["span_pct"], "speed_peak_pct": h["qd"]["peak_pct"],
            "accel_peak_pct": h["qdd"]["peak_pct"], "jerk_peak_pct": h["qddd"]["peak_pct"],
            "q_qd_visited_pct": payload["planes"][name]["q_qd"]["visited_pct"],
            "qd_qdd_visited_pct": payload["planes"][name]["qd_qdd"]["visited_pct"],
            "q_qdd_visited_pct": payload["planes"][name]["q_qdd"]["visited_pct"],
            "beyond_limit": sum(h[s]["outside"] for s in payload["signals"]),
        })
    pct = lambda label: {"type": "number", "label": label, "unitText": "%", "decimals": 0}
    write("joints", "Joints", {
        "joint": {"type": "text", "label": "Joint"}, "order": {"type": "number"}, "kind": {"type": "text", "label": "Kind"},
        "q_low": {"type": "number", "label": "Low limit", "unitText": "°", "decimals": 0},
        "q_high": {"type": "number", "label": "High limit", "unitText": "°", "decimals": 0},
        "q_limit": {"type": "text", "label": "Limit kind"},
        "range_used_pct": pct("Range used"), "speed_peak_pct": pct("Peak speed"),
        "accel_peak_pct": pct("Peak acceleration"), "jerk_peak_pct": pct("Peak jerk"),
        "q_qd_visited_pct": pct("Position × speed cells"), "qd_qdd_visited_pct": pct("Speed × acceleration cells"),
        "q_qdd_visited_pct": pct("Position × acceleration cells"),
        "beyond_limit": {"type": "number", "label": "Samples past a limit"}}, rows, "joint")

    # ── hists: one row per 1-D histogram (joint × signal, then the tool's speed, tilt and yaw) ─────────────────────
    rows = []
    for jo, j in enumerate(joints):
        name = j["name"]
        for so, s in enumerate(payload["signals"]):
            h = payload["hist"][name][s]
            lim = payload["limits"][name][s]
            plan = ((payload.get("planner_limits") or {}).get(name) or {}).get(s)
            e = edges(h["edges"])
            rows.append({
                "id": f"{name}.{s}", "family": "joint", "joint": name, "joint_short": short(name), "joint_order": jo,
                "signal": s, "signal_order": so, "signal_word": SIGNAL_WORD[s],
                "label": f"{short(name)} {s}", "lo": e["lo"], "hi": e["hi"], "bins": e["n"],
                "counts": h["counts"], "groups": list(groups) if h["groups"] else [],
                "group_counts": [h["groups"][g] for g in groups] if h["groups"] else [],
                "low": lim["low"], "high": lim["high"], "limit_source": lim["source"], "limit_kind": lim["kind"],
                "planner_low": plan["low"] if plan else None, "planner_high": plan["high"] if plan else None,
                "p001": h["p001"], "p999": h["p999"], "min": h["min"], "max": h["max"],
                "span_pct": h["span_pct"], "peak_pct": h["peak_pct"], "outside": h["outside"],
                "beyond_edges": h["beyond_edges"], "scale": j["display"]["scale"], "unit": unit_of(j, s),
            })
    tool = payload["tool"]
    if tool:
        o = tool["orientation"]
        deg = 180 / math.pi
        for idx, (key, label, spec, counts, scale, unit) in enumerate([
            ("speed", "tool speed", tool["speed"]["edges"], tool["speed"]["counts"], 1.0, "m/s"),
            ("tilt", "tool tilt", o["tilt"]["edges"], o["tilt"]["counts"], deg, "°"),
            ("yaw", "jaw yaw", o["yaw"]["edges"], o["yaw"]["counts"], deg, "°"),
        ]):
            e = edges(spec)
            rows.append({
                "id": f"tool.{key}", "family": "tool", "joint": None, "joint_short": None, "joint_order": 100 + idx,
                "signal": key, "signal_order": idx, "signal_word": label, "label": label,
                "lo": e["lo"], "hi": e["hi"], "bins": e["n"], "counts": counts, "groups": [], "group_counts": [],
                "low": None, "high": None, "limit_source": None, "limit_kind": None, "planner_low": None,
                "planner_high": None, "p001": None, "p999": None, "min": None, "max": None, "span_pct": None,
                "peak_pct": None, "outside": 0, "beyond_edges": 0, "scale": scale, "unit": unit,
            })
    hidden = {"type": "list", "hidden": True}
    write("hists", "Histograms", {
        "label": {"type": "text", "label": "Histogram"}, "family": {"type": "text", "label": "Family"},
        "joint": {"type": "text", "label": "Joint"}, "joint_short": {"type": "text"}, "joint_order": {"type": "number"},
        "signal": {"type": "text", "label": "Signal"}, "signal_order": {"type": "number"}, "signal_word": {"type": "text"},
        "lo": {"type": "number"}, "hi": {"type": "number"}, "bins": {"type": "number"},
        "counts": hidden, "groups": hidden, "group_counts": hidden,
        "low": {"type": "number"}, "high": {"type": "number"}, "limit_source": {"type": "text"}, "limit_kind": {"type": "text"},
        "planner_low": {"type": "number"}, "planner_high": {"type": "number"},
        "p001": {"type": "number"}, "p999": {"type": "number"}, "min": {"type": "number"}, "max": {"type": "number"},
        "span_pct": pct("Span"), "peak_pct": pct("Peak"), "outside": {"type": "number", "label": "Past the limit"},
        "beyond_edges": {"type": "number", "label": "Off the chart"}, "scale": {"type": "number"},
        "unit": {"type": "text"}}, rows, "label")

    # ── planes: one grid row per joint plane, then its five qdd slabs ───────────────────────────────────────────────
    rows = []
    for jo, j in enumerate(joints):
        name = j["name"]
        sc = j["display"]["scale"]
        for key, p in payload["planes"][name].items():
            xe, ye = edges(p["x_edges"]), edges(p["y_edges"])
            nx, ny = p["shape"]
            rows.append({
                "id": f"{name}.{key}", "joint": name, "joint_short": short(name), "joint_order": jo,
                "grid": key, "grid_order": GRID_ORDER.get(key, 9), "slab": None, "slab_lo": None, "slab_hi": None,
                "x": p["x"], "y": p["y"],
                "x_label": f"{p['x']} · {SIGNAL_WORD[p['x']]}", "y_label": f"{p['y']} · {SIGNAL_WORD[p['y']]}",
                "x_lo": xe["lo"], "x_hi": xe["hi"], "nx": nx, "y_lo": ye["lo"], "y_hi": ye["hi"], "ny": ny,
                "x_scale": sc, "y_scale": sc, "x_unit": unit_of(j, p["x"]), "y_unit": unit_of(j, p["y"]),
                "samples": p["samples"], "paths": p["paths"],
                "max_other": p["max_other"] if p.get("max_other") and any(v is not None for v in p["max_other"]) else None,
                "other_label": "max |qdd|", "other_scale": sc, "other_unit": unit_of(j, "qdd"),
                "visited_pct": p["visited_pct"], "sufficient_pct": p["sufficient_pct"], "evenness_pct": p["evenness_pct"],
                "outside": p["outside"], "cells": nx * ny, "enough": enough, "box": "limit",
            })
        s = payload["slabs"][name]
        n_slab, nx, ny = s["shape"]
        by = edges(s["by_edges"])
        p = payload["planes"][name]["q_qd"]
        xe, ye = edges(p["x_edges"]), edges(p["y_edges"])
        step = (by["hi"] - by["lo"]) / by["n"]
        for k in range(n_slab):
            lo, hi = by["lo"] + k * step, by["lo"] + (k + 1) * step
            rows.append({
                "id": f"{name}.slab{k}", "joint": name, "joint_short": short(name), "joint_order": jo,
                "grid": "slab", "grid_order": 10 + k, "slab": k, "slab_lo": lo, "slab_hi": hi,
                "x": s["x"], "y": s["y"],
                "x_label": f"{s['x']} · {SIGNAL_WORD[s['x']]}", "y_label": f"{s['y']} · {SIGNAL_WORD[s['y']]}",
                "x_lo": xe["lo"], "x_hi": xe["hi"], "nx": nx, "y_lo": ye["lo"], "y_hi": ye["hi"], "ny": ny,
                "x_scale": sc, "y_scale": sc, "x_unit": unit_of(j, s["x"]), "y_unit": unit_of(j, s["y"]),
                "samples": s["samples"][k * nx * ny:(k + 1) * nx * ny], "paths": None, "max_other": None,
                "other_label": None, "other_scale": None, "other_unit": None,
                "visited_pct": s["visited_pct"][k], "sufficient_pct": None, "evenness_pct": None,
                "outside": None, "cells": nx * ny, "enough": enough, "box": "limit",
                "by": s["by"], "by_scale": sc, "by_unit": unit_of(j, s["by"]),
            })
    write("planes", "Joint planes", grid_props({
        "joint": {"type": "text", "label": "Joint"}, "joint_short": {"type": "text"}, "joint_order": {"type": "number"},
        "grid": {"type": "text", "label": "Plane"}, "grid_order": {"type": "number"},
        "slab": {"type": "number", "label": "Slab"}, "slab_lo": {"type": "number"}, "slab_hi": {"type": "number"},
        "other_label": {"type": "text"}, "other_scale": {"type": "number"}, "other_unit": {"type": "text"},
        "box": {"type": "text"}, "by": {"type": "text"}, "by_scale": {"type": "number"}, "by_unit": {"type": "text"}}),
        rows, "id")

    if not tool:
        return
    deg = 180 / math.pi
    o = tool["orientation"]

    # ── directions: the tool-orientation grids, in the same grid-row shape ─────────────────────────────────────────
    rows = []
    ta = o["tilt_azimuth"]
    ty = o["tilt_yaw"]
    for key, g, xname, xspec in (("tilt_azimuth", ta, "azimuth", ta["azimuth_edges"]), ("tilt_yaw", ty, "yaw", ty["yaw_edges"])):
        te, xe = edges(g["tilt_edges"]), edges(xspec)
        nt, nxx = g["shape"]
        # WHY transposed here: the payload stores [tilt][x] (C order); the grid row is [x][y] like the planes (x across,
        # y up), so every grid draws by one rule. Pure index shuffling, no value changes.
        counts = [g["counts"][t * nxx + i] for i in range(nxx) for t in range(nt)]
        rows.append({
            "id": key, "grid": key, "x": xname, "y": "tilt",
            "x_label": "azimuth · which way the tool z leans (base XY)" if xname == "azimuth" else "yaw · heading of the jaw (tool x) in base XY",
            "y_label": "tilt · from straight down",
            "x_lo": xe["lo"], "x_hi": xe["hi"], "nx": nxx, "y_lo": te["lo"], "y_hi": te["hi"], "ny": nt,
            "x_scale": deg, "y_scale": deg, "x_unit": "°", "y_unit": "°",
            "samples": counts, "paths": None, "max_other": None,
            "visited_pct": None, "sufficient_pct": None, "evenness_pct": None, "outside": None,
            "cells": nxx * nt, "enough": enough, "box": "none",
            "reference": o["reference"],
        })
    sphere = o["sphere"]
    # V7: the payload's own equal-area sphere (rings by the tool z axis's z component, sectors by its azimuth) as one
    # more grid row. WHY: it is the grid membership.json indexes ("directions": ring * sectors + sector), so a click on
    # the pointing map asks exactly the payload's cell, and its visited share is the headline "directions visited".
    # Copied as stored: counts are samples per cell (the payload keeps no per-direction trajectory count).
    rings, sectors = int(sphere["rings"]), int(sphere["sectors"])
    rows.append({
        "id": "sphere", "grid": "sphere", "x": "azimuth", "y": "tilt",
        "x_label": "azimuth · which way the tool z leans (base XY)", "y_label": "tilt · from straight down (equal-area rings)",
        "x_lo": -math.pi, "x_hi": math.pi, "nx": sectors, "y_lo": 0.0, "y_hi": math.pi, "ny": rings,
        "x_scale": deg, "y_scale": deg, "x_unit": "°", "y_unit": "°",
        "samples": list(sphere["counts"]), "paths": None, "max_other": None,
        "visited_pct": next((n["value"] for n in payload["numbers"] if n["key"] == "tool_directions_visited_pct"), None),
        "sufficient_pct": None, "evenness_pct": None, "outside": None,
        "cells": rings * sectors, "enough": enough, "box": "none", "reference": o["reference"],
        "rings": rings, "sectors": sectors,
    })
    write("directions", "Tool directions", grid_props({
        "grid": {"type": "text", "label": "Grid"}, "box": {"type": "text"}, "reference": hidden,
        "rings": {"type": "number"}, "sectors": {"type": "number"}}), rows, "id")

    # ── projections: one row per view of the tool path (Strava: distinct trajectories per pixel) ──────────────────
    rows = []
    axes = {"xy": ("x", "y", "from above"), "xz": ("x", "z", "from the front"), "yz": ("y", "z", "from the side")}
    for key, p in tool["projections"].items():
        u, v, word = axes[key]
        rows.append({
            "id": key, "view": key, "title": word, "u": u, "v": v, "frame": tool["frame"], "pixel_m": tool["pixel_m"],
            "origin_u": p["origin"][0], "origin_v": p["origin"][1], "nu": p["shape"][0], "nv": p["shape"][1],
            "samples": p["samples"], "paths": p["paths"], "max_speed": p["max_speed"], "reachable": p["reachable"],
            "pixels": sum(1 for c in p["samples"] if c > 0), "enough": enough,
        })
    write("projections", "Tool path projections", {
        "view": {"type": "text", "label": "View"}, "title": {"type": "text", "label": "Seen"},
        "u": {"type": "text"}, "v": {"type": "text"}, "frame": {"type": "text", "label": "Frame"},
        "pixel_m": {"type": "number", "label": "Pixel", "unitText": "m"},
        "origin_u": {"type": "number"}, "origin_v": {"type": "number"}, "nu": {"type": "number"}, "nv": {"type": "number"},
        "samples": hidden, "paths": hidden, "max_speed": hidden, "reachable": hidden,
        "pixels": {"type": "number", "label": "Pixels visited"}, "enough": {"type": "number"}}, rows, "view")

    # ── voxels: one row per visited 5 cm cell (the stock voxels view reads pre-gridded rows, CONTRACT §32) ────────
    vx = tool["voxels"]
    x0, y0, z0 = vx["origin"]
    size = vx["size"]
    rows = []
    for ix, iy, iz, samples, paths, speed in vx["cells"]:
        rows.append({"id": f"{ix}.{iy}.{iz}", "x": round(x0 + (ix + 0.5) * size, 6), "y": round(y0 + (iy + 0.5) * size, 6),
                     "z": round(z0 + (iz + 0.5) * size, 6), "samples": samples, "paths": paths, "max_speed": speed})
    write("voxels", "Tool voxels", {
        "x": {"type": "number", "label": "x", "unitText": "m"}, "y": {"type": "number", "label": "y", "unitText": "m"},
        "z": {"type": "number", "label": "z", "unitText": "m"}, "samples": {"type": "number", "label": "Samples"},
        "paths": {"type": "number", "label": "Trajectories"},
        "max_speed": {"type": "number", "label": "Max tool speed", "unitText": "m/s"}}, rows, "id")

    # ── growth: visited % of the q×qd cells as trajectories are added (stock chart) ─────────────────────────────────
    # long form (one row per series and step) so the stock chart's colour is a real column with its own legend
    g = payload["growth"]
    rows = []
    file_order, shuffled = "in file order", "shuffled order (mean of 32 shuffles)"
    for i, value in enumerate(g["visited_pct"]):
        rows.append({"id": f"file.{i + 1}", "added": i + 1, "series": file_order, "trajectory": payload["trajectories"][i]["name"],
                     "pct": value, "lo": None, "hi": None})
        rows.append({"id": f"shuffled.{i + 1}", "added": i + 1, "series": shuffled, "trajectory": None,
                     "pct": g["shuffled"]["mean"][i], "lo": g["shuffled"]["p10"][i], "hi": g["shuffled"]["p90"][i]})
    write("growth", "Growth", {
        "added": {"type": "number", "label": "Trajectories added"},
        "series": {"type": "text", "label": "Order", "colors": {file_order: 1, shuffled: "muted"}},
        "trajectory": {"type": "text", "label": "Trajectory added"},
        "pct": pct("q×qd cells visited"), "lo": pct("p10 of 32 shuffles"), "hi": pct("p90 of 32 shuffles")}, rows, "series")

    # visited: one row per joint and plane (the stock bar chart's long form; the payload's visited_pct, nothing else)
    words = {"q_qd": "position × speed", "qd_qdd": "speed × acceleration", "q_qdd": "position × acceleration"}
    rows = []
    for jo, j in enumerate(joints):
        for key in ("q_qd", "qd_qdd", "q_qdd"):
            rows.append({"id": f"{j['name']}.{key}", "joint": short(j["name"]), "joint_order": jo, "plane": words[key],
                         "plane_order": GRID_ORDER[key], "pct": payload["planes"][j["name"]][key]["visited_pct"]})
    write("visited", "Cells visited per plane", {
        "joint": {"type": "text", "label": "Joint"}, "joint_order": {"type": "number"},
        "plane": {"type": "text", "label": "Plane", "colors": {words["q_qd"]: 1, words["qd_qdd"]: 7, words["q_qdd"]: 3}},
        "plane_order": {"type": "number"}, "pct": pct("Cells visited")}, rows, "joint")

    # ── trajectories: the stock table's rows (one per trajectory; the round's trajectories.json, flattened) ────────
    motion = {}
    for i, t in enumerate(payload["trajectories"]):
        motion[t["name"]] = {
            "tool_path": tool["spaghetti"][i] if tool else None,
            "joint_paths": {j["name"]: payload["paths"][j["name"]][i] for j in joints},
        }
    rows = []
    for t in trajectories:
        row = {
            "id": t["name"], "name": t["name"], "split": t["tags"]["split"], "kind": t["tags"]["kind"],
            "rung": t["tags"]["rung"], "task": t["tags"]["tags"], "duration_s": t["duration_s"], "samples": t["samples"],
            "new_cells": t["new_cells"], "only_it_q_qd_cells": t["only_it_q_qd_cells"],
            "tool_path_m": t["tool_path_m"], "tool_speed_max_m_s": t["tool_speed_max_m_s"],
            "tool_z_min_m": t["tool_z_min_m"], "tool_z_max_m": t["tool_z_max_m"],
            "tool_tilt_max_deg": t["tool_tilt_max_deg"], "rrd": t["rrd"],
        }
        for s in ("q", "qd", "qdd"):
            for j in joints:
                row[f"{short(j['name'])}_{s}_span_pct"] = t["span_pct"][j["name"]][s]
        rows.append(row)
    props = {
        "name": {"type": "text", "label": "Trajectory"},
        "split": {"type": "text", "label": "Split", "display": "badge", "colors": {"dev": 1, "holdout": 3}},
        "kind": {"type": "text", "label": "Kind"}, "rung": {"type": "text", "label": "Rung"},
        "task": {"type": "text", "label": "Task"},
        "duration_s": {"type": "number", "label": "Duration", "unitText": "s", "decimals": 2},
        "samples": {"type": "number", "label": "Samples"},
        "new_cells": {"type": "number", "label": "New cells", "description": "q×qd cells (all joints) this trajectory was first to visit, in file order"},
        "only_it_q_qd_cells": {"type": "number", "label": "Only it", "description": "q×qd cells no other trajectory visits"},
        "tool_path_m": {"type": "number", "label": "Tool path", "unitText": "m", "decimals": 2},
        "tool_speed_max_m_s": {"type": "number", "label": "Tool speed max", "unitText": "m/s", "decimals": 2},
        "tool_z_min_m": {"type": "number", "label": "Tool z min", "unitText": "m", "decimals": 3},
        "tool_z_max_m": {"type": "number", "label": "Tool z max", "unitText": "m", "decimals": 3},
        "tool_tilt_max_deg": {"type": "number", "label": "Tilt max", "unitText": "°", "decimals": 0},
        "rrd": {"type": "text", "label": "Rerun file"},
    }
    for s in ("q", "qd", "qdd"):
        for j in joints:
            props[f"{short(j['name'])}_{s}_span_pct"] = {"type": "number", "label": f"{short(j['name'])} {s}",
                                                          "unitText": "%", "decimals": 1}
    write("trajectories", "Trajectories", props, rows, "name")

    # the drill's motion (one record per trajectory, read by the drill's coverage views; the payload's own paths)
    (OUT / "motion.json").write_text(json.dumps(motion, allow_nan=False, separators=(",", ":")) + "\n")
    print(f"rows/motion.json  {len(motion):6d} trajectories")

    # the page's frame: title, subtitle, frame and group names (read by the host page's header, not a dataset)
    meta = {"title": payload["title"], "subtitle": payload["subtitle"], "enough": enough, "group_by": group_by,
            "groups": groups, "frame": tool["frame"] if tool else None, "reference": o["reference"],
            "sphere": [sphere["rings"], sphere["sectors"]], "joints": [j["name"] for j in joints]}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")


if __name__ == "__main__":
    main()
