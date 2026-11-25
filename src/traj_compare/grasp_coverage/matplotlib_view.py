"""Matplotlib view of a grasp-coverage payload ("traj_compare.grasp_coverage/1"): one PNG per figure.

    from traj_compare.grasp_coverage.matplotlib_view import plot_grasp_coverage
    paths = plot_grasp_coverage(payload, "out/png", cmap="viridis", reverse=False, scale="linear")

Reads ONLY the payload (docs/GRASP_COVERAGE.md "The other viewers"). Every figure's title is the question it answers,
its legend names every mark it draws, its colour bar carries the scale's real numbers. Angles in degrees, lengths in mm.
The colour + scale rule, the legend-as-title header and the heat painter are the trajectory viewer's
(`traj_compare.coverage.matplotlib_view`, the numpy mirror of assets/coverage_color.js), imported, never copied.

WHY these figures (Zach, Daily Note 2026-11-23, on the Nov 19 gallery): the outcome-coloured positions ("showing where
the failures where and not thats super helpful"), the widths against the claw ("I really like this how it shows the
size of the grasps"), and roll as a straight line ("just like a straight line actually works as well").
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..coverage.matplotlib_view import (
    GROUP_COLORS,
    INK,
    LIMIT_COLOR,
    MUTED,
    OUTSIDE_RGB,
    STYLE,
    _colorbar,
    _colormap,
    _header,
    _heat,
    _line,
    _new_figure,
    _patch,
    _ramp_patch,
    _rgb_hex,
    check_colour_choice,
    edges,
    scale_counts,
)
from .analysis import SCHEMA

# WHY these: the Nov 19 gallery's outcome colours (figures_grasp.py repick_positions: blue = succeeded, orange = closed
# then missed, grey = never closed), the ones Zach answered "super helpful" to (blue / orange is colour-blind safe), as
# data-ui's series slots 1, 2 and muted so the workbench, these PNGs and Viser paint an outcome alike
# (workbench.OUTCOME_SLOTS); refused = slot 4 amber (a gate said no), unknown = slot 7 violet (no status meaning)
OUTCOME_COLORS = {"picked": "#2a78d6", "failed": "#eb6834", "hovered": "#8a8983", "refused": "#eda100",
                  "unknown": "#6250d6"}
OUTCOME_MARKERS = {"picked": "o", "failed": "o", "hovered": "x", "refused": "+", "unknown": "."}
BEYOND = "#efeee9"  # the histogram strip past the jaw range: the claw cannot open there
FIGURE_IDS = ("positions", "position-density", "width", "roll", "pointing", "sphere", "width-tilt", "objects")
FACES = (("xy", "top view", "x", "y"), ("xz", "front view", "x", "z"), ("yz", "side view", "y", "z"))


def figure_ids(payload: Mapping[str, Any]) -> list[str]:
    return list(FIGURE_IDS)


def group_colours(payload: Mapping[str, Any]) -> dict[str, str]:
    """The colour of each of `source.groups`: outcome colours when the groups are outcomes, else the palette."""
    groups = payload["source"]["groups"]
    if payload["source"]["group_by"] == "outcome":
        spare = iter(GROUP_COLORS[2:])
        return {name: OUTCOME_COLORS.get(name) or next(spare, MUTED) for name in groups}
    return {name: GROUP_COLORS[i % len(GROUP_COLORS)] for i, name in enumerate(groups)}


def outcome_colours(payload: Mapping[str, Any]) -> dict[str, str]:
    spare = iter(GROUP_COLORS[2:])
    return {name: OUTCOME_COLORS.get(name) or next(spare, MUTED) for name in payload["outcomes"]["order"]}


def _data_line(payload: Mapping[str, Any]) -> str:
    source = payload["source"]
    counts = payload["outcomes"]["counts"]
    outcomes = ", ".join(f"{counts[name]} {name}" for name in payload["outcomes"]["order"])
    return (f"{source['grasps']} grasps of {len(source['objects'])} object{'s' if len(source['objects']) != 1 else ''} "
            f"({outcomes}) in the \"{source['frame']}\" frame")


def _gripper_words(payload: Mapping[str, Any]) -> str:
    gripper = payload["gripper"]
    if gripper["source"] != "limit":
        return "no jaw range stated (the box is the data's span)"
    words = f"jaw range {gripper['low'] * 1000:.0f}-{gripper['high'] * 1000:.0f} mm"
    if gripper["planner_high"] is not None:
        words += f", planner {gripper['planner_low'] * 1000:.0f}-{gripper['planner_high'] * 1000:.0f} mm"
    return words


def _mm(value: float) -> float:
    return float(value) * 1000.0


# ── figures ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _positions(payload, cmap, reverse, scale):
    rows = payload["grasps"]
    colours = outcome_colours(payload)
    fig = _new_figure(13.0, 5.8)
    top, side = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.0, 1.0]})
    area = payload["position"]["area"] or []
    for lo, hi in area:
        top.add_patch(_rectangle(lo[0], lo[1], hi[0], hi[1]))
        side.add_patch(_rectangle(lo[0], lo[2], hi[0], hi[2]))
    handles = {}
    # WHY failures drawn last: a failed grasp among 800 picked ones must stay on top, where the eye finds it
    draw_order = [name for name in payload["outcomes"]["order"] if name not in ("failed",)] + \
        [name for name in ("failed",) if name in payload["outcomes"]["order"]]
    for name in draw_order:
        mine = np.array([row["position"] for row in rows if row["outcome"] == name], float).reshape(-1, 3) * 1000.0
        marker = OUTCOME_MARKERS.get(name, "o")
        style = ({"s": 16, "linewidths": 0.35, "edgecolors": "white"} if marker == "o"
                 else {"s": 18, "linewidths": 0.8})
        for ax, (u, v) in ((top, (0, 1)), (side, (0, 2))):
            ax.scatter(mine[:, u], mine[:, v], color=colours[name], marker=marker, zorder=3 if name != "failed" else 4,
                       **style)
        handles[name] = _marker(colours[name], marker, f"{name} ({payload['outcomes']['counts'][name]}): "
                                                       f"{payload['outcomes']['words'][name]}")
    handles = [handles[name] for name in payload["outcomes"]["order"]]  # the legend reads in outcome order
    for ax, (x_name, y_name), title in ((top, ("x", "y"), "from above"), (side, ("x", "z"), "from the side")):
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel(f"{x_name} (mm)")
        ax.set_ylabel(f"{y_name} (mm)")
        ax.set_title(title, fontsize=9.5)
        ax.grid(color="#efeee9", linewidth=0.6)
        ax.set_axisbelow(True)
    if area:
        handles.append(_patch("#eef2f8", "the offered pick area", edge=LIMIT_COLOR))
    _header(fig, "Where did the gripper close, and did it work there?",
            _data_line(payload) + " · a dot per grasp at the jaws' centre"
            + (f" · pale box = the {len(area)} offered area{'s' if len(area) != 1 else ''}" if area else ""),
            handles, columns=2)
    return fig


def _rectangle(x0, y0, x1, y1):
    from matplotlib.patches import Rectangle

    return Rectangle((x0 * 1000, y0 * 1000), (x1 - x0) * 1000, (y1 - y0) * 1000, facecolor="#eef2f8",
                     edgecolor=LIMIT_COLOR, linewidth=0.8, linestyle=(0, (3, 2)), zorder=1)


def _marker(colour: str, marker: str, label: str):
    from matplotlib.lines import Line2D

    return Line2D([], [], color=colour, marker=marker, linestyle="none", markersize=6, label=label,
                  markeredgecolor="white" if marker == "o" else colour)


def _position_density(payload, cmap, reverse, scale):
    position = payload["position"]
    pixel = float(position["pixel_m"])
    grids = {}
    for face, *_ in FACES:
        block = position["projections"][face]
        grids[face] = np.asarray(block["samples"], float)
    pooled = scale_counts(np.concatenate(list(grids.values())), scale, enough=int(payload.get("enough", 10)))
    colormap = _colormap(cmap, reverse)
    fig = _new_figure(15.0, 5.4)
    axes = fig.subplots(1, 3)
    offset, mesh, any_area = 0, None, False
    for ax, (face, title, x_name, y_name) in zip(axes, FACES, strict=True):
        block = position["projections"][face]
        nu, nv = block["shape"]
        u0, v0 = block["origin"]
        u_edges = (u0 + np.arange(nu + 1) * pixel) * 1000.0
        v_edges = (v0 + np.arange(nv + 1) * pixel) * 1000.0
        t = pooled.t[offset:offset + nu * nv].reshape(nu, nv)
        offset += nu * nv
        outside = None
        if block["area"] is not None:
            any_area = True
            outside = (np.asarray(block["area"]).reshape(nu, nv) == 0) & (t < 0)
        mesh = _heat(ax, u_edges, v_edges, t, colormap, outside)
        ax.set_aspect("equal")
        ax.set_xlim(u_edges[0], u_edges[-1])
        ax.set_ylim(v_edges[0], v_edges[-1])
        ax.set_xlabel(f"{x_name} (mm)")
        ax.set_ylabel(f"{y_name} (mm)")
        ax.spines[["top", "right"]].set_visible(True)
        ax.set_title(f"{title} ({x_name}, {y_name}): {int((t >= 0).sum())} pixels", fontsize=9)
    _colorbar(fig, mesh, list(axes), pooled, "grasps in the pixel")
    handles = [_patch("white", "no grasp" + (" (inside the offered area)" if any_area else "")),
               _ramp_patch(cmap, reverse, "colour = grasps in the pixel (bar)")]
    if any_area:
        handles.append(_patch(_rgb_hex(OUTSIDE_RGB), "outside the offered area, no grasp"))
    _header(fig, "How densely do the grasps cover the pick area?",
            _data_line(payload) + f" · {pixel * 1000:.0f} mm pixels anchored at the frame's origin · one colour "
            f"scale over all three views: {pooled.note}", handles)
    return fig


def _stacked(ax, block, colours: dict[str, str], groups: Sequence[str], scale_x: float, shift: float = 0.0):
    low, high, count = block["edges"]
    step = (high - low) / count
    left = (low + np.arange(count) * step) * scale_x + shift
    bottom = np.zeros(count)
    for name in groups:
        counts = np.asarray(block["groups"].get(name, [0] * count), float)
        if counts.any():
            ax.bar(left, counts, width=step * scale_x, bottom=bottom, align="edge", color=colours[name], linewidth=0)
        bottom += counts
    return bottom


def _counts_locator():
    from matplotlib.ticker import MaxNLocator

    return MaxNLocator(nbins=5, integer=True)  # a count axis never reads 0.5 grasps


def _width(payload, cmap, reverse, scale):
    gripper = payload["gripper"]
    groups = payload["source"]["groups"]
    colours = group_colours(payload)
    panels = [("width", "jaw width the grasp closes to")]
    if payload["pre_grasp_width"] is not None:
        panels.append(("pre_grasp_width", "pre-grasp opening (before the approach)"))
    fig = _new_figure(11.0, 2.6 + 2.0 * len(panels))
    axes = np.atleast_1d(fig.subplots(len(panels), 1, sharex=True))
    stated = gripper["source"] == "limit"
    for ax, (key, title) in zip(axes, panels, strict=True):
        block = payload[key]
        low, high, _ = block["edges"]
        heights = _stacked(ax, block, colours, groups, 1000.0)
        if stated:
            ax.axvspan(low * 1000, gripper["low"] * 1000, color=BEYOND, zorder=-3)
            ax.axvspan(gripper["high"] * 1000, high * 1000, color=BEYOND, zorder=-3)
            for edge in (gripper["low"], gripper["high"]):
                ax.axvline(edge * 1000, color=LIMIT_COLOR, linewidth=1.4)
        if gripper["planner_high"] is not None:
            for edge in (gripper["planner_low"], gripper["planner_high"]):
                ax.axvline(edge * 1000, color=LIMIT_COLOR, linewidth=1.1, linestyle=(0, (4, 3)))
        total = int(sum(block["counts"]))
        total += int(block.get("beyond_edges") or 0)
        ax.set_title(f"{title}: {total} grasps" + (f", {block['outside']} past the range" if block.get("outside")
                                                   else ""), fontsize=9)
        ax.set_ylabel("grasps")
        ax.set_xlim(low * 1000, high * 1000)
        ax.set_ylim(0, max(float(heights.max()), 1.0) * 1.12)
        ax.yaxis.set_major_locator(_counts_locator())
        off = int(block.get("beyond_edges") or 0)
        if off:  # WHY said, not hidden: a grasp past the chart's edge is in no bar (the trajectory viewer's rule)
            ax.text(0.995, 0.95, f"{off} off the chart (widest {payload['width']['max'] * 1000:.0f} mm) →"
                    if key == "width" else f"{off} off the chart →", transform=ax.transAxes, ha="right", va="top",
                    fontsize=8, color=LIMIT_COLOR)
    axes[-1].set_xlabel("jaw gap (mm), linear")
    handles = [_patch(colours[name], f"{name}") for name in groups]
    if stated:
        handles += [_line(f"the jaw range {gripper['low'] * 1000:.0f}-{gripper['high'] * 1000:.0f} mm (shut, open stop)"),
                    _patch(BEYOND, "past the range: the claw cannot")]
    if gripper["planner_high"] is not None:
        handles.append(_line(f"the planner's span {gripper['planner_high'] * 1000:.0f} mm", style=(0, (4, 3)),
                             width=1.1))
    width = payload["width"]
    _header(fig, "How wide do the jaws open, against the claw's range?",
            _data_line(payload) + f" · {_gripper_words(payload)} · range used (p0.1 to p99.9): "
            f"{width['span_pct']:.0f} %, widest {width['peak_pct']:.0f} % of the open stop · bars stacked by "
            f"{payload['source']['group_by']}", handles, columns=3)
    return fig


def _roll(payload, cmap, reverse, scale):
    orientation = payload["orientation"]
    key = orientation["roll_shown"]
    block = orientation[key]
    groups = payload["source"]["groups"]
    colours = group_colours(payload)
    fig = _new_figure(11.0, 4.2)
    ax = fig.subplots()
    heights = _stacked(ax, block, colours, groups, 180.0 / math.pi)
    low, high, count = block["edges"]
    ax.set_xlim(math.degrees(low), math.degrees(high))
    ax.set_ylim(0, max(float(heights.max()), 1.0) * 1.12)
    ax.yaxis.set_major_locator(_counts_locator())
    ax.set_xticks(np.arange(math.degrees(low), math.degrees(high) + 1, 30 if key == "roll_folded" else 45))
    ax.xaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}°")
    folded = key == "roll_folded"
    ax.set_xlabel("roll of the jaws about the approach, " + ("folded: r and r + 180° are the same two-finger grasp"
                                                             if folded else "full circle (the jaws are not symmetric)"))
    ax.set_ylabel("grasps")
    visited = int(sum(1 for n in block["counts"] if n > 0))
    ax.set_title(f"{visited} of {count} {math.degrees(high - low) / count:.0f}° bins hold a grasp", fontsize=9,
                 color=MUTED)
    handles = [_patch(colours[name], name) for name in groups]
    _header(fig, "Is every roll of the hand represented?",
            _data_line(payload) + " · 0° = the jaws along the frame's +x for a straight-down grasp (seen from behind "
            "the gripper, counter-clockwise positive) · a straight line, not a rose: equal bins read as equal lengths",
            handles, columns=min(len(handles), 5))
    return fig


def _pointing(payload, cmap, reverse, scale):
    block = payload["orientation"]["tilt_azimuth"]
    tilt_edges = np.degrees(edges(block["tilt_edges"]))
    azimuth_edges = edges(block["azimuth_edges"])
    tilts, azimuths = block["shape"]
    counts = np.asarray(block["counts"], float).reshape(tilts, azimuths)
    scaled = scale_counts(counts, scale, enough=int(payload.get("enough", 10)))
    fig = _new_figure(7.6, 7.0)
    ax = fig.add_subplot(projection="polar")
    shown = np.ma.masked_where(scaled.t < 0, scaled.t)
    mesh = ax.pcolormesh(azimuth_edges, tilt_edges, shown, cmap=_colormap(cmap, reverse), vmin=0, vmax=1,
                         shading="flat", rasterized=True)
    reach = max(90.0, min(180.0, 30.0 * math.ceil(max(_number(payload, "tilt_max_deg"), 1.0) / 30.0 + 0.001)))
    ax.set_ylim(0, reach)
    ax.set_axisbelow(False)
    ax.grid(color="white", linewidth=0.9, alpha=0.9)
    ax.set_yticks([v for v in (30, 60, 90, 120, 150) if v < reach])
    ax.set_yticklabels([f"{v}°" for v in (30, 60, 90, 120, 150) if v < reach], fontsize=7.5, color=INK,
                       bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8, "alpha": 0.85})
    ax.set_rlabel_position(100)
    ax.set_xticks(np.radians([0, 90, 180, 270]), ["+x", "+y", "−x", "−y"], fontsize=9, color=INK)
    if reach > 90:
        ring = np.linspace(-np.pi, np.pi, 181)
        ax.plot(ring, np.full_like(ring, 90.0), color=INK, linewidth=0.9, linestyle=(0, (3, 3)))
    _colorbar(fig, mesh, ax, scaled, "grasps per cell", shrink=0.8)
    handles = [_patch("white", "no grasp from there"), _ramp_patch(cmap, reverse, "colour = grasps (bar)")]
    if reach > 90:
        handles.append(_line("90°: approaching level", color=INK, style=(0, (3, 3)), width=0.9))
    _header(fig, "Which way does the gripper approach?",
            _data_line(payload) + " · centre = straight down (tilt 0°); distance from the centre = tilt; angle = the way "
            f"the approach leans in the frame's XY · {tilt_edges[1] - tilt_edges[0]:.0f}° × "
            f"{math.degrees(azimuth_edges[1] - azimuth_edges[0]):.0f}° cells · {scaled.note}", handles, columns=3)
    return fig


def _number(payload, key: str, default: float = 0.0) -> float:
    for entry in payload.get("numbers", []):
        if entry["key"] == key:
            return float(entry["value"])
    return default


def _sphere(payload, cmap, reverse, scale):
    sphere = payload["orientation"]["sphere"]
    rings, sectors = sphere["rings"], sphere["sectors"]
    counts = np.asarray(sphere["counts"], float).reshape(rings, sectors)  # ring = equal z band, sector = azimuth
    scaled = scale_counts(counts.T, scale, enough=int(payload.get("enough", 10)))  # (azimuth, z) = (x, y)
    fig = _new_figure(10.0, 5.2)
    ax = fig.subplots()
    azimuth_edges = np.linspace(-180.0, 180.0, sectors + 1)
    z_edges = np.linspace(-1.0, 1.0, rings + 1)
    mesh = _heat(ax, azimuth_edges, z_edges, scaled.t, _colormap(cmap, reverse))
    ax.set_xlim(-180, 180)
    ax.set_ylim(-1, 1)
    ax.set_xticks(np.arange(-180, 181, 45))
    ax.xaxis.set_major_formatter(lambda value, _pos: f"{value:+.0f}°")
    tilt_ticks = (0, 30, 60, 90, 120, 150, 180)
    ax.set_yticks([-math.cos(math.radians(t)) for t in tilt_ticks], [f"{t}°" for t in tilt_ticks])
    ax.set_xlabel("which way the approach leans (azimuth in the frame's XY)")
    ax.set_ylabel("tilt from straight down\n(rows are equal-area bands)")
    ax.spines[["top", "right"]].set_visible(True)
    visited = int((scaled.t >= 0).sum())
    ax.set_title(f"{visited} of {rings * sectors} equal-area cells hold a grasp ({100 * visited / (rings * sectors):.0f} %)",
                 fontsize=9, color=MUTED)
    _colorbar(fig, mesh, ax, scaled, "grasps per cell")
    _header(fig, "Which approach directions does the set cover, cell for equal cell?",
            _data_line(payload) + " · Lambert's cylindrical equal-area map of the approach (tool +z): every cell is the "
            "same share of the sphere, so a visited % is a share of all directions · " + scaled.note,
            [_patch("white", "never approached from there"), _ramp_patch(cmap, reverse, "colour = grasps (bar)")])
    return fig


def _width_tilt(payload, cmap, reverse, scale):
    block = payload["width_tilt"]
    nx, ny = block["shape"]
    x_edges = edges(block["x_edges"]) * 1000.0
    y_edges = np.degrees(edges(block["y_edges"]))
    counts = np.asarray(block["counts"], float).reshape(nx, ny)
    scaled = scale_counts(counts, scale, enough=int(payload.get("enough", 10)))
    gripper = payload["gripper"]
    fig = _new_figure(10.0, 5.6)
    ax = fig.subplots()
    outside = None
    if gripper["source"] == "limit":
        centres = (x_edges[:-1] + x_edges[1:]) / 2.0
        beyond = (centres < gripper["low"] * 1000) | (centres > gripper["high"] * 1000)
        outside = np.repeat(beyond[:, None], ny, axis=1) & (scaled.t < 0)
    mesh = _heat(ax, x_edges, y_edges, scaled.t, _colormap(cmap, reverse), outside)
    reach = max(90.0, min(180.0, 30.0 * math.ceil(max(_number(payload, "tilt_max_deg"), 1.0) / 30.0 + 0.001)))
    ax.set_xlim(x_edges[0], x_edges[-1])
    ax.set_ylim(reach, 0)  # straight down at the top
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}°")
    handles = [_patch("white", "no grasp"), _ramp_patch(cmap, reverse, "colour = grasps (bar)")]
    if gripper["source"] == "limit":
        for edge in (gripper["low"], gripper["high"]):
            ax.axvline(edge * 1000, color=LIMIT_COLOR, linewidth=1.4)
        handles += [_line("the jaw range"), _patch(_rgb_hex(OUTSIDE_RGB), "past the range")]
    if gripper["planner_high"] is not None:
        ax.axvline(gripper["planner_high"] * 1000, color=LIMIT_COLOR, linewidth=1.1, linestyle=(0, (4, 3)))
        handles.append(_line("the planner's span", style=(0, (4, 3)), width=1.1))
    ax.set_xlabel("jaw width (mm)")
    ax.set_ylabel("tilt from straight down")
    ax.spines[["top", "right"]].set_visible(True)
    _colorbar(fig, mesh, ax, scaled, "grasps per cell")
    _header(fig, "Which approach tilts need a wider hand?",
            _data_line(payload) + f" · {x_edges[1] - x_edges[0]:.1f} mm × {y_edges[1] - y_edges[0]:.0f}° cells · "
            + scaled.note, handles, columns=3)
    return fig


def _objects(payload, cmap, reverse, scale):
    rows = payload["objects"][:30]
    order = payload["outcomes"]["order"]
    colours = outcome_colours(payload)
    fig = _new_figure(11.0, 1.6 + 0.32 * len(rows))
    ax = fig.subplots()
    names = [row["object_id"] for row in rows]
    left = np.zeros(len(rows))
    for name in order:
        counts = np.array([row["outcomes"].get(name, 0) for row in rows], float)
        ax.barh(names, counts, left=left, color=colours[name], linewidth=0, height=0.7)
        left += counts
    for i, row in enumerate(rows):
        text = f"{row['grasps']}"
        if row["picked_pct"] is not None:
            text += f" · {row['picked_pct']:.0f} % picked"
        ax.text(left[i] + max(left) * 0.01, i, text, va="center", fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(left.max(), 1.0) * 1.22)
    ax.set_xlabel("grasps")
    evenness = _number(payload, "object_evenness_pct")
    largest = _number(payload, "largest_object_pct")
    more = len(payload["objects"]) - len(rows)
    _header(fig, "Are the objects balanced, and which ones fail?",
            _data_line(payload) + f" · balance (evenness) {evenness:.0f} %, the largest object holds {largest:.0f} % of "
            "the grasps · picked % = picked / (picked + failed)" + (f" · {more} more objects not drawn" if more > 0
                                                                     else ""),
            [_patch(colours[name], name) for name in order], columns=min(len(order), 5))
    return fig


FIGURES = {"positions": _positions, "position-density": _position_density, "width": _width, "roll": _roll,
           "pointing": _pointing, "sphere": _sphere, "width-tilt": _width_tilt, "objects": _objects}


def figure(payload: Mapping[str, Any], figure_id: str, *, cmap: str = "viridis", reverse: bool = False,
           scale: str = "linear"):
    """One figure as a matplotlib `Figure` (no pyplot). `figure_id` is one of `FIGURE_IDS`."""
    import matplotlib

    check_colour_choice(cmap, scale)
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a grasp_coverage payload ({SCHEMA}): schema {payload.get('schema')!r}")
    if figure_id not in FIGURES:
        raise KeyError(f"unknown figure {figure_id!r}; expected one of {', '.join(FIGURE_IDS)}")
    with matplotlib.rc_context(STYLE):
        return FIGURES[figure_id](payload, cmap, reverse, scale)


def plot_grasp_coverage(payload: Mapping[str, Any], out_dir: str | Path, *, cmap: str = "viridis",
                        reverse: bool = False, scale: str = "linear") -> list[Path]:
    """Write one PNG per figure into `out_dir` (created) and return their paths, in `FIGURE_IDS` order."""
    import matplotlib

    check_colour_choice(cmap, scale)
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a grasp_coverage payload ({SCHEMA}): schema {payload.get('schema')!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for figure_id in figure_ids(payload):
        fig = figure(payload, figure_id, cmap=cmap, reverse=reverse, scale=scale)
        path = out / f"{figure_id}.png"
        with matplotlib.rc_context(STYLE):
            fig.savefig(path, dpi=130, facecolor="white")
        written.append(path)
    return written
