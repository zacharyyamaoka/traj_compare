"""The coverage workbench: data-ui's stock ``<data-workbench>`` over a set of trajectories (docs/COVERAGE.md, "The
workbench"; data-ui docs/CONTRACT.md §52 coverage views and §53 scope + workbench).

    coverage = analyze(trajectories, tool=poses, tags=tags, group_by="dataset", title="UR5e")
    write_workbench(coverage, trajectories, "out/", tool=poses, rrd_for=lambda name: f"rrd/{name}.rrd")
    python -m traj_compare.serve out/          # then /index.html (its Open in Rerun is that server's endpoint)

Writes into ``out_dir``:

    trajectories.json   one row per trajectory: its name, every tag (dataset, split, kind, ...), its .rrd, the payload's
                        per-trajectory numbers: what the rail filters and the corner counts
    parts.json          one row per trajectory and figure, that trajectory's share of the figure (§52 grid / hist /
                        projection rows, sparse `at` where a grid is big): the views add up the parts of the
                        trajectories the rail keeps (`coverage.sum: grid`), so a tick recounts every figure on every tab
    coverage.base       the rail (Dataset first, then split, kind, tags, ranges), the tabs (`pages:`), the gear
                        (`settings:`), the record's Open in Rerun (`drill:`), the views
    index.html          one ``<data-workbench src="coverage.base">``
    embed.html          the same tag in a host app's 1000 x 680 slot (the round's host template)
    vendor/data-ui/     data-ui ``main`` vendored by its own ``data-ui vendor`` (unless ``kit=`` names one to reuse)

WHY parts re-summed in the page, not the payload's whole-set grids: Zach, 2026-11-24, "the atomic unit here is
trajectories" and "the dev/holdout will apply then to all of the datasets you include"; a figure must show what the rail
keeps. Every part is counted with analyze()'s own bin functions on the payload's own grids, so the parts of every
trajectory add back up to the payload exactly (tests/test_coverage_workbench.py is that oracle).

WHY beside the hand-rolled page (page.py), not instead of it: this is the stock data-ui form of the same figures
("the nice thing with data-ui is it's the common visual language"); the hand-rolled page keeps its 3-D views, growth
curve and parallel coordinates, which have no stock view yet.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs.trajectory import JointTrajectory

from .. import _files
from . import analysis as cov

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
DEG = 180.0 / math.pi
WORDS = {"q": "position", "qd": "speed", "qdd": "acceleration", "qddd": "jerk"}
DISPLAY_UNITS = {
    "revolute": {"q": "°", "qd": "°/s", "qdd": "°/s²", "qddd": "°/s³"},
    "prismatic": {"q": "mm", "qd": "mm/s", "qdd": "mm/s²", "qddd": "mm/s³"},
}
# WHY these slots: data-ui's series 4 is amber, 6 green and 8 red, which read as a status (CONTRACT §32); a dataset is
# a family, never a verdict (the round's P1/P5 measured 1, 2, 3, 7 on the four UR5e datasets)
SLOTS = (1, 2, 3, 7, 5)
FACES = {"xy": "from above", "xz": "from the front", "yz": "from the side"}
LABELS = {"dataset": "Dataset", "split": "Split", "kind": "Kind", "tags": "Tags", "rung": "Speed rung"}
SPLIT_ORDER = ("dev", "holdout")


# ── the rows ────────────────────────────────────────────────────────────────────────────────────────────────────────


def workbench_rows(coverage, trajectories, *, tool=None,
                   rrd_for: Callable[[str], str | None] | Mapping[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """(trajectory rows, part rows) for one ``analyze()`` result and the SAME inputs it was given, in the same order.

    ``coverage`` is a ``TrajectoryCoverage`` or its payload dict; ``trajectories`` and ``tool`` are what analyze() got
    (a Mapping or a Sequence; ``tool`` is required when the payload has a tool block). ``rrd_for(name)`` (or a Mapping)
    gives a trajectory's .rrd path relative to the page, the record's Open in Rerun target. Every count is binned on the
    payload's own grids with analysis.py's own functions, so the parts add back up to the payload exactly.
    """
    payload = _payload(coverage)
    named = cov._named(trajectories, JointTrajectory, "trajectories")
    names = [row["name"] for row in payload["trajectories"]]
    given = [name for name, _ in named]
    if given != names:
        missing = [name for name in names if name not in given][:3]
        extra = [name for name in given if name not in names][:3]
        raise ValueError(f"the trajectories must be the ones analyze() was given, in its order ({len(given)} given, the "
                         f"payload has {len(names)}; missing {missing}, extra {extra})")
    if payload["tool"] is not None and tool is None:
        raise ValueError("this payload has a tool block: pass the same tool= that analyze() was given")
    if payload["tool"] is None and tool is not None:
        raise ValueError("tool= was given, but the payload has no tool block (analyze() was given no tool)")
    rrd = _rrd_lookup(rrd_for)
    groups = _group_names(payload)
    joints = payload["joints"]

    trajectory_rows, parts = [], []
    for k, (name, trajectory) in enumerate(named):
        signals = dict(zip(cov.SIGNALS, cov._signals(trajectory), strict=True))
        source = payload["trajectories"][k]
        row = {"id": name, "name": name, **source["tags"]}
        if rrd is not None:
            row["rrd"] = rrd(name)
        row.update(duration_s=source["duration_s"], samples=source["samples"], new_cells=source["new_cells"])
        for joint in joints:
            row[f"q_range_{joint['name']}_pct"] = source["span_pct"][joint["name"]]["q"]
        trajectory_rows.append(row)
        parts += _joint_parts(payload, name, signals, groups[k])

    if tool is not None:
        tool_samples = cov._tool_samples(cov._matched_tools(tool, named))
        for k, name in enumerate(names):
            numbers, tool_parts = _tool_parts(payload, tool_samples, k, name, groups[k])
            trajectory_rows[k].update(numbers)
            parts += tool_parts
    return trajectory_rows, parts


def _payload(coverage) -> dict:
    payload = coverage.payload if hasattr(coverage, "payload") else coverage
    if not isinstance(payload, Mapping) or payload.get("schema") != cov.SCHEMA:
        raise ValueError(f"expected a {cov.SCHEMA!r} payload (analyze()'s result), got {type(coverage).__name__}")
    return payload  # type: ignore[return-value]


def _rrd_lookup(rrd_for) -> Callable[[str], str | None] | None:
    if rrd_for is None:
        return None
    if isinstance(rrd_for, Mapping):
        return lambda name: rrd_for.get(name)
    return rrd_for


def _group_names(payload: Mapping) -> list[str | None]:
    """Each trajectory's group_by value as analysis._groups names it (its histogram bars stack by it), or None."""
    group_by = payload["source"]["group_by"]
    if not group_by:
        return [None] * len(payload["trajectories"])
    return [str(row["tags"][group_by]) if group_by in row["tags"] else f"(no {group_by})" for row in payload["trajectories"]]


def _sparse(counts: np.ndarray) -> np.ndarray:
    return np.flatnonzero(counts)


def _ints(values) -> list[int]:
    return np.asarray(values).astype(np.int64).tolist()


# ── joint figures: phase planes and histograms ──────────────────────────────────────────────────────────────────────


def _joint_parts(payload: Mapping, name: str, signals: dict[str, np.ndarray], group: str | None) -> list[dict]:
    parts = []
    enough = payload["enough"]
    planner = payload.get("planner_limits") or {}
    for j, joint_info in enumerate(payload["joints"]):
        joint = joint_info["name"]
        scale = joint_info["display"]["scale"]
        units = DISPLAY_UNITS[joint_info["kind"]]
        limits = payload["limits"][joint]
        for plane_name, plane in payload["planes"][joint].items():
            x, y = plane["x"], plane["y"]
            (x_lo, x_hi, nx), (y_lo, y_hi, ny) = plane["x_edges"], plane["y_edges"]
            x_values, y_values = signals[x][:, j], signals[y][:, j]
            x_index = cov._bin_index(x_values, x_lo, x_hi, nx)
            y_index = cov._bin_index(y_values, y_lo, y_hi, ny)
            inside = (x_index >= 0) & (y_index >= 0)
            cell = x_index[inside] * ny + y_index[inside]
            counts = np.bincount(cell, minlength=nx * ny)
            at = _sparse(counts)
            # WHY no paths list: one part row is one trajectory, so data-ui's sum counts the rows that visit a cell,
            # which IS the payload's paths (distinct trajectories per cell); writing 1s would only add bytes
            row = {
                "id": f"{name}|{joint}.{plane_name}", "kind": plane_name, "grid": f"{joint}.{plane_name}",
                "trajectory": name, "joint": joint, "joint_order": j,
                "x": x, "y": y, "x_label": f"{x} · {WORDS[x]}", "y_label": f"{y} · {WORDS[y]}",
                "x_lo": x_lo, "x_hi": x_hi, "nx": nx, "y_lo": y_lo, "y_hi": y_hi, "ny": ny,
                "x_scale": scale, "y_scale": scale, "x_unit": units[x], "y_unit": units[y],
                "box": "limit" if limits[x]["source"] == "limit" and limits[y]["source"] == "limit" else "none",
                "zero": "y" if x == "q" else "xy", "enough": enough,
                "at": _ints(at), "samples": _ints(counts[at]),
                "outside": int((np.isfinite(x_values) & np.isfinite(y_values) & ~inside).sum()),
            }
            if plane["max_other"] is not None:
                span = limits["qdd"]["high"] - limits["qdd"]["low"]
                largest = cov._max_per_cell(cell, np.abs(signals["qdd"][inside, j]), nx * ny)
                row.update(max_other=cov._floats(largest[at], cov._decimals(span)), other_label="max |qdd|",
                           other_scale=scale, other_unit=units["qdd"])
            parts.append(row)
        for s, signal in enumerate(payload["signals"]):
            hist = payload["hist"][joint][signal]
            low, high, bins = hist["edges"]
            values = signals[signal][:, j]
            index = cov._bin_index(values, low, high, bins)
            counts = _ints(np.bincount(index[index >= 0], minlength=bins))
            limit = limits[signal]
            stated = (planner.get(joint) or {}).get(signal) or {}
            row = {
                "id": f"{name}|{joint}.{signal}", "kind": "hist", "grid": f"{joint}.{signal}", "trajectory": name,
                "joint": joint, "joint_order": j, "signal": signal, "signal_order": s, "signal_word": WORDS[signal],
                "label": f"{joint} {signal}", "lo": low, "hi": high, "bins": bins, "counts": counts,
                "low": limit["low"], "high": limit["high"], "limit_source": limit["source"],
                "planner_low": stated.get("low"), "planner_high": stated.get("high"),
                "outside": cov._beyond(values, cov._Bound(limit["low"], limit["high"], limit["source"])),
                "scale": scale, "unit": units[signal],
            }
            if group is not None:
                row.update(groups=[group], group_counts=[counts])
            parts.append(row)
    return parts


# ── the tool: footprint, speed, directions ──────────────────────────────────────────────────────────────────────────


def _grid_on(points: np.ndarray, origin: Sequence[float], shape: Sequence[int], size: float, axes) -> np.ndarray:
    """analysis._grid_cells on the payload's own grid (origin, shape): low and high are set half a cell inside its first
    and last cells, so _grid_cells lands on exactly the payload's first cell and shape."""
    low, high = np.zeros(3), np.zeros(3)
    for axis, start, cells in zip(axes, origin, shape, strict=True):
        first = round(start / size)
        low[axis], high[axis] = (first + 0.5) * size, (first + cells - 0.5) * size
    index, got = cov._grid_cells(points, size, low, high, axes)
    if got != list(shape):  # pragma: no cover - a guard on the half-cell rule above
        raise AssertionError(f"the payload's grid {list(shape)} rebuilt as {got}")
    return index


def _tool_parts(payload: Mapping, samples, k: int, name: str, group: str | None) -> tuple[dict, list[dict]]:
    tool = payload["tool"]
    enough = payload["enough"]
    raw = slice(int(samples.starts[k]), int(samples.starts[k + 1]))
    dense = samples.path_owner == k
    positions, points, point_speeds = samples.positions[raw], samples.path_points[dense], samples.path_speeds[dense]
    parts = []
    for face, axes in cov.PROJECTIONS.items():
        projection = tool["projections"][face]
        nu, nv = projection["shape"]
        raw_cells = _grid_on(positions, projection["origin"], projection["shape"], tool["pixel_m"], axes)
        path_cells = _grid_on(points, projection["origin"], projection["shape"], tool["pixel_m"], axes)
        counts = np.bincount(raw_cells[raw_cells >= 0], minlength=nu * nv)
        on_path = path_cells >= 0
        crossed = np.unique(path_cells[on_path])
        fastest = cov._max_per_cell(path_cells[on_path], point_speeds[on_path], nu * nv)
        at = np.union1d(_sparse(counts), crossed)
        parts.append({
            "id": f"{name}|tool.{face}", "kind": "tool", "grid": face, "trajectory": name, "title": FACES[face],
            "u": face[0], "v": face[1], "frame": tool["frame"], "pixel_m": tool["pixel_m"],
            "origin_u": projection["origin"][0], "origin_v": projection["origin"][1], "nu": nu, "nv": nv,
            "enough": enough, "at": _ints(at), "samples": _ints(counts[at]),
            # WHY paths here (not in the planes): the payload's paths run along the densified path, which crosses
            # pixels no raw sample landed in; a row with samples only would undercount them
            "paths": _ints(np.isin(at, crossed)), "max_speed": cov._floats(fastest[at], 4),
        })

    speed = tool["speed"]
    low, high, bins = speed["edges"]
    finite = samples.speeds[raw][np.isfinite(samples.speeds[raw])]
    index = cov._bin_index(finite, low, high, bins)
    counts = _ints(np.bincount(index[index >= 0], minlength=bins))
    row = {"id": f"{name}|tool.speed", "kind": "tool_speed", "grid": "tool.speed", "trajectory": name,
           "signal": "speed", "signal_word": "tool speed", "label": "tool speed", "lo": low, "hi": high, "bins": bins,
           "counts": counts, "low": None, "high": None, "limit_source": "none", "outside": 0, "scale": 1, "unit": "m/s"}
    if group is not None:
        row.update(groups=[group], group_counts=[counts])
    parts.append(row)

    orientation = tool["orientation"]
    rotations = samples.rotations[raw]
    z_axis, x_axis = rotations[:, :, 2], rotations[:, :, 0]
    reference = np.asarray(orientation["reference"], float)
    tilt = np.arccos(np.clip(z_axis @ reference, -1.0, 1.0))
    azimuth = np.arctan2(z_axis[:, 1], z_axis[:, 0])
    yaw = np.arctan2(x_axis[:, 1], x_axis[:, 0])
    tilt_lo, tilt_hi, tilts = orientation["tilt_azimuth"]["tilt_edges"]
    az_lo, az_hi, azimuths = orientation["tilt_azimuth"]["azimuth_edges"]
    yaw_lo, yaw_hi, yaws = orientation["tilt_yaw"]["yaw_edges"]
    tilt_index = cov._bin_index(tilt, tilt_lo, tilt_hi, tilts)
    direction = {"x_scale": DEG, "y_scale": DEG, "x_unit": "°", "y_unit": "°", "box": "none", "enough": enough,
                 "trajectory": name}
    for kind, grid, x, x_label, x_values, (x_lo, x_hi, nx) in (
        ("pointing", "tilt_azimuth", "azimuth", "azimuth · which way the tool axis leans", azimuth, (az_lo, az_hi, azimuths)),
        ("tilt_yaw", "tilt_yaw", "yaw", "yaw · which way the tool's x axis heads", yaw, (yaw_lo, yaw_hi, yaws)),
    ):
        x_index = cov._bin_index(x_values, x_lo, x_hi, nx)
        inside = (x_index >= 0) & (tilt_index >= 0)
        counts = np.bincount(x_index[inside] * tilts + tilt_index[inside], minlength=nx * tilts)
        at = _sparse(counts)
        part = {"id": f"{name}|{grid}", "kind": kind, "grid": grid, **direction, "x": x, "y": "tilt",
                "x_label": x_label, "y_label": "tilt · away from the reference", "x_lo": x_lo, "x_hi": x_hi, "nx": nx,
                "y_lo": tilt_lo, "y_hi": tilt_hi, "ny": tilts, "zero": "none", "at": _ints(at), "samples": _ints(counts[at])}
        if kind == "pointing":
            part["reference"] = list(orientation["reference"])
        parts.append(part)
    sphere = orientation["sphere"]
    rings, sectors = sphere["rings"], sphere["sectors"]
    # WHY azimuth x height: the sphere's cells (rings equal in z, sectors equal in azimuth) are exactly a linear grid in
    # (azimuth, z), Lambert's cylindrical equal-area map, so the §52 plane draws them with every cell the same area
    counts = cov._sphere_counts(z_axis).reshape(rings, sectors).T.reshape(-1)
    at = _sparse(counts)
    parts.append({"id": f"{name}|sphere", "kind": "sphere", "grid": "sphere", **direction, "x": "azimuth", "y": "height",
                  "x_label": "azimuth · which way the tool axis points", "y_label": "height · the tool axis's z",
                  "x_lo": -math.pi, "x_hi": math.pi, "nx": sectors, "y_lo": -1.0, "y_hi": 1.0, "ny": rings,
                  "y_scale": 1, "y_unit": "", "zero": "y", "at": _ints(at), "samples": _ints(counts[at])})

    finite_positions = positions[np.isfinite(positions).all(axis=1)]
    speeds = samples.speeds[raw]
    numbers = {
        "tool_path_m": round(float(np.linalg.norm(np.diff(finite_positions, axis=0), axis=1).sum()), 4),
        "tool_speed_max_m_s": round(float(np.nanmax(speeds)), 4) if np.isfinite(speeds).any() else None,
        "tool_tilt_max_deg": round(float(np.degrees(tilt.max())), 2) if tilt.size else None,
    }
    return numbers, parts


# ── the files ───────────────────────────────────────────────────────────────────────────────────────────────────────


def write_workbench(coverage, trajectories, out_dir: Path | str, *, tool=None, title: str | None = None,
                    subtitle: str | None = None,
                    rrd_for: Callable[[str], str | None] | Mapping[str, str] | None = None,
                    dataset: str = "dataset", facets: Sequence[str] = ("split", "kind", "tags"),
                    labels: Mapping[str, str] | None = None, kit: str | None = None, vendor: str = "main",
                    data_ui: Path | str = DATA_UI) -> Path:
    """Write the workbench page into ``out_dir`` (see the module docstring) and return its ``index.html``.

    ``dataset`` is the tag the rail lists first (its values get the series colours); ``facets`` the tags after it, in
    order (a tag no trajectory has is left out); ``labels`` renames a tag in the rail. ``kit`` is the href (relative to
    ``out_dir``) of a data-ui kit already vendored there, so nothing is vendored; else ``vendor`` (a data-ui ref) is
    vendored into ``out_dir/vendor/data-ui`` with data-ui's own ``vendor`` command from the ``data_ui`` checkout.
    """
    payload = _payload(coverage)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    trajectory_rows, parts = workbench_rows(payload, trajectories, tool=tool, rrd_for=rrd_for)
    title = title or payload.get("title") or "Trajectory coverage"
    subtitle = payload.get("subtitle", "") if subtitle is None else subtitle
    names = {**LABELS, **(labels or {})}

    _write_json(out / "trajectories.json", {"id": "coverage-trajectories", "title": f"{title}: trajectories",
                                            "titleProperty": "name", "properties": _trajectory_properties(payload, trajectory_rows, names),
                                            "rows": trajectory_rows})
    _write_json(out / "parts.json", {"id": "coverage-parts", "title": f"{title}: each trajectory's share of every figure",
                                     "titleProperty": "id", "properties": _part_properties(), "rows": parts})
    base = _base(payload, trajectory_rows, title=title, dataset=dataset, facets=facets, labels=names,
                 rrd=rrd_for is not None, tool=payload["tool"] is not None)
    _files.write_text(out / "coverage.base", _HEADER + _yaml(base) + "\n")
    if kit is None:
        kit = _vendor(out, vendor, Path(data_ui))
    _files.write_text(out / "index.html", _INDEX.format(title=html.escape(title), subtitle=html.escape(subtitle),
                                                       kit=html.escape(kit.rstrip("/"))))
    _files.write_text(out / "embed.html", _EMBED.format(title=html.escape(title), kit=html.escape(kit.rstrip("/"))))
    return out / "index.html"


def _write_json(path: Path, document: dict) -> None:
    # WHY allow_nan=False: a NaN would make JSON.parse throw in the browser; every number here is finite or None
    _files.write_text(path, json.dumps(document, separators=(",", ":"), allow_nan=False, ensure_ascii=False) + "\n")


def _vendor(out: Path, ref: str, data_ui: Path) -> str:
    """data-ui ``ref`` into out/vendor/data-ui with data-ui's own vendor command (a clean archive, sha-checked)."""
    cli = data_ui / "bin" / "data-ui.mjs"
    if not cli.is_file():
        raise FileNotFoundError(f"no data-ui checkout at {data_ui} to vendor from; pass kit= (an href to a vendored kit) "
                                "or data_ui= (the checkout)")
    target = out / "vendor" / "data-ui"
    result = subprocess.run(["node", str(cli), "vendor", ref, "--into", str(target)], capture_output=True, text=True,
                            timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"data-ui vendor {ref} failed: {(result.stderr or result.stdout)[-2000:]}")
    return "vendor/data-ui"


def _first_seen(rows: list[dict], key: str) -> list:
    return list(dict.fromkeys(row[key] for row in rows if row.get(key) is not None))


def _label(key: str, labels: Mapping[str, str]) -> str:
    return labels.get(key) or key.replace("_", " ").capitalize()


def _trajectory_properties(payload: Mapping, rows: list[dict], labels: Mapping[str, str]) -> dict:
    tag_keys = list(dict.fromkeys(key for row in payload["trajectories"] for key in row["tags"]))
    properties = {"id": {"type": "text", "label": "Trajectory", "hidden": True},
                  "name": {"type": "text", "label": "Trajectory"}}
    for key in tag_keys:
        properties[key] = {"type": "text", "label": _label(key, labels)}
    properties.update({
        "rrd": {"type": "text", "label": "Rerun file"},
        "duration_s": {"type": "number", "label": "Duration", "unitText": "s", "decimals": 2},
        "samples": {"type": "number", "label": "Samples"},
        "new_cells": {"type": "number", "label": "New cells",
                      "description": "position × speed cells (every joint) it was the first to visit, in analyze()'s order"},
    })
    for joint in payload["joints"]:
        properties[f"q_range_{joint['name']}_pct"] = {
            "type": "number", "label": f"{joint['name']} range used", "unitText": "%", "decimals": 1,
            "description": "p0.1 to p99.9 of its position, as a share of the joint's limits"}
    if payload["tool"] is not None:
        properties.update({
            "tool_path_m": {"type": "number", "label": "Tool path", "unitText": "m", "decimals": 2},
            "tool_speed_max_m_s": {"type": "number", "label": "Tool speed max", "unitText": "m/s", "decimals": 2},
            "tool_tilt_max_deg": {"type": "number", "label": "Tilt max", "unitText": "°", "decimals": 1,
                                  "description": "the largest angle between the tool axis and the reference"},
        })
    if not any("rrd" in row for row in rows):
        del properties["rrd"]
    return properties


def _part_properties() -> dict:
    hidden_list = {"type": "list", "hidden": True}
    properties = {
        "id": {"type": "text", "label": "Part"}, "kind": {"type": "text", "label": "Figure"},
        "grid": {"type": "text", "label": "Grid"}, "trajectory": {"type": "text", "label": "Trajectory"},
        "joint": {"type": "text", "label": "Joint"}, "joint_order": {"type": "number", "hidden": True},
        "signal": {"type": "text", "label": "Signal"}, "signal_order": {"type": "number", "hidden": True},
        "signal_word": {"type": "text", "hidden": True}, "label": {"type": "text", "label": "Histogram"},
        "title": {"type": "text", "label": "Seen"},
        "at": {**hidden_list, "label": "cells visited"}, "samples": {**hidden_list, "label": "samples per cell"},
        "paths": {**hidden_list, "label": "trajectories per cell"},
        "max_other": {**hidden_list, "label": "max |qdd| per cell"},
        "max_speed": {**hidden_list, "label": "max tool speed per pixel (m/s)"},
        "counts": hidden_list, "groups": hidden_list, "group_counts": hidden_list, "reference": hidden_list,
    }
    for key in ("x", "y", "x_label", "y_label", "x_unit", "y_unit", "box", "zero", "u", "v", "frame", "limit_source",
                "unit", "other_label", "other_unit"):
        properties[key] = {"type": "text", "hidden": True}
    for key in ("x_lo", "x_hi", "nx", "y_lo", "y_hi", "ny", "x_scale", "y_scale", "other_scale", "enough", "outside",
                "lo", "hi", "bins", "low", "high", "planner_low", "planner_high", "scale", "pixel_m", "origin_u",
                "origin_v", "nu", "nv"):
        properties[key] = {"type": "number", "hidden": True}
    return properties


# ── coverage.base ───────────────────────────────────────────────────────────────────────────────────────────────────

_HEADER = """# The coverage workbench: data-ui's <data-workbench> over these trajectories (data-ui docs/CONTRACT.md §52, §53).
# GENERATED by traj_compare.coverage.workbench.write_workbench (docs/COVERAGE.md "The workbench"): change the writer,
# never this file. The rail filters trajectories, Dataset first; every tab is a dashboard over what the rail keeps, and
# each coverage figure adds up the kept trajectories' part rows (coverage.sum), so a tick recounts every tab. One joint
# has a Joint picker of its own; the gear sets the heatmap colours for every tab at once.
#
# WHY trajectories in the rail and parts in the figures (Zach, 2026-11-24): "the atomic unit here is trajectories", and
# "the dev/holdout will apply then to all of the datasets you include".
"""


def _base(payload: Mapping, rows: list[dict], *, title: str, dataset: str, facets: Sequence[str],
          labels: Mapping[str, str], rrd: bool, tool: bool) -> dict:
    joints = [joint["name"] for joint in payload["joints"]]
    group_by = payload["source"]["group_by"]
    rail = []
    for key in (dataset, *facets):
        values = _first_seen(rows, key)
        if not values:
            continue
        facet: dict[str, Any] = {"property": key, "label": _label(key, labels)}
        if key == "split":
            values = [v for v in SPLIT_ORDER if v in values] + [v for v in values if v not in SPLIT_ORDER]
        if key in (dataset, "split"):
            facet["order"] = values
        rail.append(facet)
    rail.append({"property": "name", "as": "search", "label": "Find a trajectory", "placeholder": f"e.g. {rows[0]['name']}"})
    rail.append({"property": "duration_s", "as": "slider-histogram", "label": "Duration", "unit": "s", "collapsed": True})
    rail.append({"property": "new_cells", "as": "slider-histogram", "label": "New cells", "collapsed": True})
    if tool:
        rail.append({"property": "tool_path_m", "as": "slider-histogram", "label": "Tool path", "unit": "m", "collapsed": True})

    datasets_seen = _first_seen(rows, dataset)
    colours = {value: SLOTS[i] for i, value in enumerate(datasets_seen[:len(SLOTS)])}
    properties: dict[str, Any] = {"name": {"displayName": "Trajectory"}}
    if colours:
        properties[dataset] = {"displayName": _label(dataset, labels), "colors": colours}
    splits = _first_seen(rows, "split")
    if splits and dataset != "split":
        # WHY muted: an unlisted value gets a hashed slot, and "holdout" landed on red, which reads as a problem; a split
        # is a word, not a status (the round's P5: "Split has no colour")
        properties["split"] = {"displayName": _label("split", labels), "colors": {value: 0 for value in splits}}
    style: dict[str, Any] = {"numbers": {"digits": 3}}
    if group_by:
        group_colours = colours if group_by == dataset else {
            value: SLOTS[i] for i, value in enumerate(_first_seen(rows, group_by)[:len(SLOTS)])}
        # the histograms stack by the payload's group_by, in the rail's colours
        style["families"] = {"property": group_by, "colors": group_colours}
    style["heatmap"] = {"colormap": "viridis", "reverse": False, "scale": "linear"}

    actions = []
    if rrd:
        actions.append({"label": "Open in Rerun", "post": "/__rerun/open?rrd={rrd}",
                        "title": "Opens {rrd} in the native Rerun viewer (needs python -m traj_compare.serve)"})
    actions.append({"label": "Copy its name", "copy": "{name}", "title": "Copies {name}"})

    pages = _pages(joints, tool)
    views = _views(payload, rows, dataset=dataset, facets=facets, tool=tool)
    return {
        "data": "trajectories.json",
        "noun": ["trajectory", "trajectories"],
        "facets": rail,
        "properties": properties,
        "style": style,
        "settings": ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"],
        "drill": {"actions": actions},
        "datasets": {"parts": {"data": "parts.json", "label": "Coverage parts"}},
        "links": [{"from": "trajectories.id", "to": "parts.trajectory", "direction": "one-way"}],
        "pages": pages,
        "views": views,
    }


def _page(name: str, panels: list[dict], **extra) -> dict:
    return {"name": name, **extra, "layout": {"columns": 12, "rowHeight": 96, "panels": panels}}


def _pages(joints: list[str], tool: bool) -> list[dict]:
    # WHY this order: the grid fills row by row, so the right column (count chart, then the tool from above) runs as
    # tall as the joint grids beside it, and the second row pairs the limits with the pointing disk
    overview = [
        {"view": "Every joint", "w": 8, "h": 5, "title": "Every joint · position × speed"},
        {"view": "Trajectories per dataset", "w": 4, "h": 2 if tool else 5},
        {"view": "The tool from above", "w": 4, "h": 3} if tool else None,
        {"view": "Every joint against its limits", "w": 8 if tool else 12, "h": 4},
        {"view": "Which way the tool points", "w": 4, "h": 4} if tool else None,
    ]
    pages = [
        _page("Overview", [panel for panel in overview if panel]),
        # this page's own control: a joint, over the parts; it never touches the rail or another tab
        _page("One joint", [
            {"view": "Position × speed", "w": 6, "h": 4},
            {"view": "Speed × acceleration", "w": 6, "h": 4},
            {"view": "Position × acceleration", "w": 6, "h": 4},
            {"view": "Against the limits", "w": 6, "h": 4},
        ], datasets={"parts": {
            "facets": [{"property": "joint", "as": "select", "label": "Joint", "dropdown": True, "order": joints}],
            "filters": f'joint == "{joints[0]}"'}}),
        _page("Limits", [{"view": "Every joint, every signal", "w": 12, "h": 7, "style": {"title": "none"}}]),
    ]
    if tool:
        pages += [
            _page("Tool position", [
                {"view": "The tool from three sides", "w": 12, "h": 5, "style": {"title": "none"}},
                {"view": "Tool speed", "w": 12, "h": 3},
            ]),
            _page("Tool orientation", [
                {"view": "Which way the tool points", "w": 5, "h": 5},
                {"view": "Every direction, equal area", "w": 7, "h": 5},
                {"view": "Tilt × yaw", "w": 12, "h": 4},
            ]),
        ]
    pages.append(_page("Trajectories", [{"view": "Trajectories", "w": 12, "h": 6, "style": {"title": "none"}}]))
    return pages


def _parts_view(kind: str, name: str, filters: str, coverage: dict | None = None, sort: Sequence[str] = ()) -> dict:
    view: dict[str, Any] = {"type": kind, "name": name, "from": "parts", "filters": filters}
    if sort:
        view["sort"] = [{"property": key, "direction": "ASC"} for key in sort]
    view["coverage"] = {"sum": "grid", **(coverage or {})}
    return view


def _views(payload: Mapping, rows: list[dict], *, dataset: str, facets: Sequence[str], tool: bool) -> list[dict]:
    # WHY the chart first: a view drawn alone (a gallery picture, a link to one view) reads the file's own rows
    views: list[dict] = [{
        "type": "chart", "name": "Trajectories per dataset",
        "chart": {"mark": "bar", "encoding": {"y": {"field": dataset, "title": None},
                                              "x": {"aggregate": "count", "title": "trajectories"},
                                              "color": {"field": "split", "title": "Split"}}},
    }]
    three = [signal for signal in ("q", "qd", "qdd") if signal in payload["signals"]]
    views += [
        _parts_view("coverage-plane", "Every joint", 'kind == "q_qd"', {"title": "joint", "columns": 3}, ["joint_order"]),
        _parts_view("coverage-hist", "Every joint against its limits", 'kind == "hist"',
                    {"layout": "ridgeline", "card": "joint", "signals": three}, ["joint_order", "signal_order"]),
        _parts_view("coverage-plane", "Position × speed", 'kind == "q_qd"'),
        _parts_view("coverage-plane", "Speed × acceleration", 'kind == "qd_qdd"'),
        _parts_view("coverage-plane", "Position × acceleration", 'kind == "q_qdd"'),
        _parts_view("coverage-hist", "Against the limits", 'kind == "hist"', {"card": "joint", "columns": 1},
                    ["signal_order"]),
        _parts_view("coverage-hist", "Every joint, every signal", 'kind == "hist"', {"card": "joint"},
                    ["joint_order", "signal_order"]),
    ]
    if tool:
        views += [
            _parts_view("coverage-projection", "The tool from above", 'kind == "tool" && grid == "xy"'),
            _parts_view("coverage-projection", "The tool from three sides", 'kind == "tool"'),
            _parts_view("coverage-hist", "Tool speed", 'kind == "tool_speed"'),
            _parts_view("coverage-polar", "Which way the tool points", 'kind == "pointing"'),
            _parts_view("coverage-plane", "Every direction, equal area", 'kind == "sphere"'),
            _parts_view("coverage-plane", "Tilt × yaw", 'kind == "tilt_yaw"'),
        ]
    present = {key for row in rows for key in row}
    # the table: the name, the rail's tags, the numbers, then every other tag (a speed rung, a belt speed): one row
    # per trajectory as the hand-rolled page's trajectory table, the columns the rail filters on first
    tag_keys = [key for row in payload["trajectories"] for key in row["tags"]]
    order = [key for key in ("name", dataset, *facets, "duration_s", "samples", "new_cells", "tool_path_m",
                             "tool_speed_max_m_s", "tool_tilt_max_deg", *tag_keys) if key in present]
    display = {key: "badge" for key in (dataset, "split") if key in present}
    display["new_cells"] = "bar"
    views.append({"type": "table", "name": "Trajectories", "order": list(dict.fromkeys(order)), "display": display})
    return views


# ── a small YAML writer (the .base is YAML; flow mappings keep a facet or a panel on one line, as the gallery's) ─────

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .·×/-]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _scalar(value) -> str:
    if value is None:
        return "null"
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    text = str(value)
    if _PLAIN.match(text) and text.lower() not in _RESERVED and not text.endswith(" ") and ": " not in text:
        return text
    return "'" + text.replace("'", "''") + "'"


def _flow(value) -> str:
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{_scalar(k)}: {_flow(v)}" for k, v in value.items()) + " }" if value else "{}"
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    return _scalar(value)


def _simple(value) -> bool:
    """Short enough and flat enough for one flow line."""
    return len(_flow(value)) <= 110 and not any(isinstance(v, Mapping) and any(isinstance(w, Mapping | list) for w in v.values())
                                                 for v in (value.values() if isinstance(value, Mapping) else value))


def _yaml(value, indent: int = 0) -> str:
    pad = " " * indent
    lines = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, Mapping | list | tuple) and item and not _simple(item):
                lines.append(f"{pad}{_scalar(key)}:")
                lines.append(_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{_scalar(key)}: {_flow(item)}")
    else:
        for item in value:
            if isinstance(item, Mapping) and item and not _simple(item):
                block = _yaml(item, indent + 2)
                lines.append(f"{pad}- {block.lstrip()}")
            else:
                lines.append(f"{pad}- {_flow(item)}")
    return "\n".join(lines)


# ── the pages ───────────────────────────────────────────────────────────────────────────────────────────────────────

_INDEX = """<!doctype html>
<!-- The coverage workbench, written by traj_compare.coverage.workbench (docs/COVERAGE.md "The workbench"): one data-ui
     workbench element over coverage.base. Serve this folder (fetch and module scripts need http, and Open in Rerun is the
     server's endpoint):  python -m traj_compare.serve <this folder>  -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{kit}/data-ui.css">
<style>
  html, body {{ margin: 0; }}
  body {{ font: 14px/1.4 system-ui, sans-serif; background: #fff; color: #1f2328; }}
  header {{ display: flex; align-items: baseline; gap: 12px; padding: 10px 16px 6px; min-width: 0; }}
  header h1 {{ font-size: 16px; margin: 0; white-space: nowrap; }}
  header p {{ margin: 0; color: #57606a; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  /* the element's own height: the window less the header */
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
<!-- The coverage workbench dropped into a fake host app (data-ui's gallery/examples/coverage-workbench/embed.html, the
     2026-11-24 round's host template): the component lives in #host-slot (1000 x 680) and draws nothing outside it. The
     element is narrower than 1,100 px, so its own container queries fold the rail to a Filters chip whose panel opens
     inside it; no-url leaves the host's URL alone. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Host app · {title}, embedded</title>
<link rel="stylesheet" href="{kit}/data-ui.css">
<style>
  body {{ margin: 0; font: 14px system-ui, sans-serif; background: #eef0f3; color: #1f2328; }}
  #host-header {{ height: 48px; display: flex; align-items: center; gap: 16px; padding: 0 16px; background: #1f2937; color: #fff; }}
  #host-header b {{ font-size: 15px; }}
  #host-main {{ display: flex; }}
  #host-sidebar {{ width: 200px; min-height: calc(100vh - 48px); background: #fff; border-right: 1px solid #d0d7de; padding: 12px; box-sizing: border-box; }}
  #host-sidebar div {{ padding: 6px 8px; border-radius: 6px; color: #57606a; }}
  #host-sidebar div.on {{ background: #eef2ff; color: #1f2328; }}
  #host-content {{ padding: 20px; }}
  #host-content h2 {{ margin: 0 0 12px; font-size: 16px; }}
  #host-slot {{ width: 1000px; height: 680px; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; position: relative; }}
  /* the host gives the component its slot; nothing else */
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
  <nav id="host-sidebar"><div>Robot</div><div class="on">Trajectory coverage</div><div>Pick loop</div><div>Notes</div></nav>
  <main id="host-content">
    <h2>{title} (embedded)</h2>
    <div id="host-slot"><data-workbench id="embed" src="coverage.base" no-url aria-label="Coverage workbench"></data-workbench></div>
  </main>
</div>
<script type="module" src="{kit}/data-ui.js"></script>
</body>
</html>
"""


# ── a Rerun recording per trajectory (the record's Open in Rerun) ───────────────────────────────────────────────────


def write_trajectory_rrd(path: Path | str, name: str, trajectory: JointTrajectory, *, tool=None,
                         prismatic: Sequence[str] = (), application_id: str = "traj_compare_coverage") -> Path:
    """One trajectory as an .rrd: q, qd, qdd per joint (degrees, or mm for a ``prismatic`` joint) on its own clock, the
    same signals analyze() bins, and the tool's path (a grey line, the current point on the clock) when ``tool`` is a
    PoseTrajectory. Needs the ``rerun`` extra (rerun-sdk, imported here only).

    WHY not robot_msgs.viz.rerun.save: it logs radians, and Zach reads angles in degrees (the display edge converts);
    this is the dashboard-pattern round's write_rrd (2026-11-24), which Open in Rerun was proven on.
    """
    import rerun as rr

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    recording = rr.RecordingStream(application_id, recording_id=name)
    recording.save(str(path))
    t = np.asarray(trajectory.t, float)
    times = [rr.TimeColumn("t", duration=t - (t[0] if t.size else 0.0))]
    signals = dict(zip(cov.SIGNALS, cov._signals(trajectory), strict=True))
    for signal in ("q", "qd", "qdd"):
        for j, joint in enumerate(trajectory.joint_names):
            scale, unit = (1000.0, DISPLAY_UNITS["prismatic"]) if joint in prismatic else (DEG, DISPLAY_UNITS["revolute"])
            recording.log(f"joints/{signal}/{joint}", rr.SeriesLines(names=f"{joint} {signal} ({unit[signal]})"), static=True)
            recording.send_columns(f"joints/{signal}/{joint}", indexes=times,
                                   columns=rr.Scalars.columns(scalars=signals[signal][:, j] * scale))
    if tool is not None:
        positions = np.asarray(tool.positions, float)
        recording.log("tool/path", rr.LineStrips3D([positions], colors=[[120, 120, 120]], radii=[0.002]), static=True)
        recording.send_columns("tool/now", indexes=[rr.TimeColumn("t", duration=np.asarray(tool.t, float) - float(tool.t[0]))],
                               columns=rr.Points3D.columns(positions=positions).partition([1] * len(positions)))
    recording.flush()
    recording.disconnect()
    return path
