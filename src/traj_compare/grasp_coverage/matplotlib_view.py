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
from .analysis import SCHEMA, gripper_polylines, time_buckets
from .colours import OUTCOME_SLOTS, SLOT_HEX, group_hex, outcome_hex

# the outcome colours are colours.py's (data-ui's slots), so the workbench, these PNGs and Viser paint an outcome alike
OUTCOME_COLORS = {name: SLOT_HEX[slot] for name, slot in OUTCOME_SLOTS.items()}
OUTCOME_MARKERS = {"picked": "o", "failed": "o", "hovered": "x", "refused": "+", "unknown": "."}
BEYOND = "#efeee9"  # the histogram strip past the jaw range: the claw cannot open there
FIGURE_IDS = ("positions", "position-density", "width", "roll", "pointing", "sphere", "width-tilt", "objects",
              # round 2 (Zach 2026-11-24: "I don't see thin grippers I don't see any heat maps ... add more")
              "grippers", "success-map", "density-outcomes", "roll-rose", "width-tilt-objects", "over-time", "growth")
GLYPHS_MAX = 900  # thin grippers drawn per figure (evenly picked): past ~1000 the lines become one solid smear
FACES = (("xy", "top view", "x", "y"), ("xz", "front view", "x", "z"), ("yz", "side view", "y", "z"))


def figure_ids(payload: Mapping[str, Any]) -> list[str]:
    """The PNGs this payload gets: the success map only when some grasp was closed (it is picked / closed)."""
    closed = payload["position"]["projections"]["xy"].get("closed")
    return [name for name in FIGURE_IDS if name != "success-map" or (closed is not None and any(closed))]


def group_colours(payload: Mapping[str, Any]) -> dict[str, str]:
    """The colour of each of `source.groups`: outcome colours when the groups are outcomes, else the slots."""
    return group_hex(payload["source"]["groups"], payload["source"]["group_by"])


def outcome_colours(payload: Mapping[str, Any]) -> dict[str, str]:
    return outcome_hex(payload["outcomes"]["order"])


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
    # WHY fills without outlines: a campaign offers one look area per run (174 on the repicks), and their outlines
    # were a tangle; overlapping pale fills draw exactly their union
    for lo, hi in area:
        top.add_patch(_rectangle(lo[0], lo[1], hi[0], hi[1]))
        side.add_patch(_rectangle(lo[0], lo[2], hi[0], hi[2]))
    if len(area) > 1:
        low = np.min([lo for lo, _ in area], axis=0)
        high = np.max([hi for _, hi in area], axis=0)
        top.add_patch(_rectangle(low[0], low[1], high[0], high[1], fill=False))
        side.add_patch(_rectangle(low[0], low[2], high[0], high[2], fill=False))
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
        handles.append(_patch("#e6edf7", "the offered pick area" + (f": {len(area)} look areas, overlapped"
                                                                     if len(area) > 1 else "")))
        if len(area) > 1:
            handles.append(_line("their outer box", style=(0, (3, 2)), width=0.9))
    _header(fig, "Where did the gripper close, and did it work there?",
            _data_line(payload) + " · a dot per grasp at the jaws' centre"
            + (f" · pale = the {len(area)} offered area{'s' if len(area) != 1 else ''}" if area else ""),
            handles, columns=2)
    return fig


def _rectangle(x0, y0, x1, y1, fill: bool = True):
    """A pale area fill with no edge (fill), or the dashed red outline of the areas' outer box (not fill)."""
    from matplotlib.patches import Rectangle

    if fill:
        return Rectangle((x0 * 1000, y0 * 1000), (x1 - x0) * 1000, (y1 - y0) * 1000, facecolor="#e6edf7",
                         edgecolor="none", linewidth=0, zorder=1)
    return Rectangle((x0 * 1000, y0 * 1000), (x1 - x0) * 1000, (y1 - y0) * 1000, fill=False, edgecolor=LIMIT_COLOR,
                     linewidth=0.9, linestyle=(0, (3, 2)), zorder=2)


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
    tilt_max = _number(payload, "tilt_max_deg")
    if tilt_max < 15.0:  # the gallery's note: a set that only comes straight down is one sliver at the centre
        ax.annotate(f"all {payload['source']['grasps']} grasps within {tilt_max:.1f}° of straight down",
                    xy=(math.radians(45), tilt_max), xytext=(math.radians(40), 0.45 * reach), fontsize=9, color=INK,
                    ha="left", arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.8},
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5, "alpha": 0.9})
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


# ── round 2: thin grippers, more heatmaps, other kinds of figure ───────────────────────────────────────────────────


def _evenly(rows: Sequence, most: int) -> list:
    if len(rows) <= most:
        return list(rows)
    return [rows[k] for k in np.unique(np.linspace(0, len(rows) - 1, most).round().astype(int))]


def _glyph_segments(lines: np.ndarray) -> np.ndarray:
    """The 7-point polylines as their 6 segments each (N * 6, 2, 3)."""
    return np.stack([lines[:, :-1], lines[:, 1:]], axis=2).reshape(-1, 2, 3)


def _grippers(payload, cmap, reverse, scale):
    from matplotlib.collections import LineCollection
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    colours = outcome_colours(payload)
    objects = [row["object_id"] for row in payload["objects"]][:4]
    fig = _new_figure(14.0, 9.2)
    grid = fig.add_gridspec(2, max(len(objects), 2), height_ratios=[1.05, 1.0])
    drawn = 0
    for column, name in enumerate(objects):
        rows = _evenly([row for row in payload["grasps"] if row["object_id"] == name], GLYPHS_MAX // max(len(objects), 1))
        ax = fig.add_subplot(grid[0, column], projection="3d")
        lines = gripper_polylines(rows) * 1000.0
        segments = _glyph_segments(lines)
        seg_colours = np.repeat([colours[row["outcome"]] for row in rows], 6)
        ax.add_collection3d(Line3DCollection(segments, colors=seg_colours, linewidths=0.55, alpha=0.38))
        points = lines.reshape(-1, 3)
        low, high = points.min(axis=0), points.max(axis=0)
        middle, half = (low + high) / 2, max(float((high - low).max()) / 2, 10.0)
        for setter, centre in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), middle, strict=True):
            setter(centre - half, centre + half)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=22, azim=-58)
        ax.tick_params(labelsize=6.5, colors=MUTED, pad=0)
        ax.set_xlabel("x (mm)", fontsize=7, labelpad=-2)
        ax.set_ylabel("y (mm)", fontsize=7, labelpad=-2)
        ax.set_zlabel("z (mm)", fontsize=7, labelpad=-2)
        total = sum(1 for row in payload["grasps"] if row["object_id"] == name)
        ax.set_title(f"{name}: {len(rows)} of {total} grasps", fontsize=9)
        drawn += len(rows)
    rows = _evenly(payload["grasps"], GLYPHS_MAX)
    lines = gripper_polylines(rows) * 1000.0
    seg_colours = np.repeat([colours[row["outcome"]] for row in rows], 6)
    half_columns = max(len(objects), 2) // 2
    for k, (title, (u, v), names) in enumerate((("from above", (0, 1), ("x", "y")), ("from the side", (0, 2), ("x", "z")))):
        ax = fig.add_subplot(grid[1, k * half_columns:(k + 1) * half_columns] if half_columns else grid[1, k])
        flat = _glyph_segments(lines)[:, :, [u, v]]
        ax.add_collection(LineCollection(flat, colors=seg_colours, linewidths=0.5, alpha=0.32))
        ax.autoscale()
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel(f"{names[0]} (mm)")
        ax.set_ylabel(f"{names[1]} (mm)")
        ax.set_title(f"every grasp {title} ({len(rows)} of {len(payload['grasps'])} drawn)", fontsize=9)
        ax.grid(color="#efeee9", linewidth=0.6)
    handles = [_line(f"{name} ({payload['outcomes']['counts'][name]})", color=colours[name], width=2.0)
               for name in payload["outcomes"]["order"]]
    _header(fig, "Where do the grippers go? Every grasp as a thin gripper",
            _data_line(payload) + " · robot_msgs' two-finger glyph per grasp (jaws at the closing width, 40 mm fingers, "
            "a stem back up the approach), thin and see-through so dense places read darker · top: one 3-D panel per "
            "object (the most grasped first); bottom: all of them from above and from the side",
            handles, columns=min(len(handles), 5))
    return fig


def _xy_grid(payload):
    block = payload["position"]["projections"]["xy"]
    nu, nv = block["shape"]
    pixel = float(payload["position"]["pixel_m"])
    u0, v0 = block["origin"]
    return block, nu, nv, (u0 + np.arange(nu + 1) * pixel) * 1000.0, (v0 + np.arange(nv + 1) * pixel) * 1000.0


def _crop(ax, counts: np.ndarray, u_edges, v_edges, pad: int = 2) -> None:
    """Zoom to the pixels that hold anything (a pick cluster in a big offered area is otherwise a few specks)."""
    used = np.argwhere(counts > 0)
    if not len(used):
        return
    (i0, j0), (i1, j1) = used.min(axis=0), used.max(axis=0)
    ax.set_xlim(u_edges[max(i0 - pad, 0)], u_edges[min(i1 + 1 + pad, len(u_edges) - 1)])
    ax.set_ylim(v_edges[max(j0 - pad, 0)], v_edges[min(j1 + 1 + pad, len(v_edges) - 1)])


def _success_map(payload, cmap, reverse, scale):
    block, nu, nv, u_edges, v_edges = _xy_grid(payload)
    picked = np.asarray(block["picked"], float).reshape(nu, nv)
    closed = np.asarray(block["closed"], float).reshape(nu, nv)
    share = np.where(closed > 0, picked / np.maximum(closed, 1), np.nan)
    t = np.where(closed > 0, np.nan_to_num(share), -1.0)
    fig = _new_figure(12.0, 6.4)
    left, right = fig.subplots(1, 2)
    outside = (np.asarray(block["area"]).reshape(nu, nv) == 0) & (closed == 0) if block["area"] is not None else None
    mesh = _heat(left, u_edges, v_edges, t, _colormap(cmap, reverse), outside)
    counts = scale_counts(closed, scale, enough=int(payload.get("enough", 10)))
    right_mesh = _heat(right, u_edges, v_edges, counts.t, _colormap(cmap, reverse), outside)
    for ax, title in ((left, "picked share of the closed grasps in each 1 cm pixel"),
                      (right, "how many grasps closed there (the share's sample size)")):
        _crop(ax, closed, u_edges, v_edges)
        ax.set_aspect("equal")
        ax.set_xlabel("x (mm)")
        ax.set_ylabel("y (mm)")
        ax.set_title(title, fontsize=9)
        ax.spines[["top", "right"]].set_visible(True)
    bar = fig.colorbar(mesh, ax=left, fraction=0.05, pad=0.02, aspect=28)
    bar.outline.set_visible(False)
    bar.set_ticks([0, 0.25, 0.5, 0.75, 1.0], labels=["0 %", "25 %", "50 %", "75 %", "100 %"])
    bar.set_label("picked / (picked + failed)\nlinear", fontsize=8.5)
    _colorbar(fig, right_mesh, right, counts, "closed grasps in the pixel")
    low = int(((closed > 0) & (share < 0.5)).sum())
    handles = [_patch("white", "no closed grasp there"), _ramp_patch(cmap, reverse, "colour = picked share (left) or "
                                                                                     "count (right)")]
    if outside is not None:
        handles.append(_patch(_rgb_hex(OUTSIDE_RGB), "outside the offered area"))
    _header(fig, "Where does picking work, and where does it fail?",
            _data_line(payload) + f" · {int((closed > 0).sum())} pixels hold a closed grasp, {low} of them pick under "
            "half the time; read the left map beside the right one: a pixel of 1 closed grasp is 0 % or 100 %",
            handles, columns=3)
    return fig


def _density_outcomes(payload, cmap, reverse, scale):
    from ..coverage import bins

    block, nu, nv, u_edges, v_edges = _xy_grid(payload)
    order = payload["outcomes"]["order"]
    rows = payload["grasps"]
    pixel = float(payload["position"]["pixel_m"])
    grids = {}
    for name in order:
        mine = np.array([row["position"] for row in rows if row["outcome"] == name], float).reshape(-1, 3)
        cell = bins.grid_cells_on(mine, block["origin"], block["shape"], pixel, (0, 1))
        grids[name] = np.bincount(cell[cell >= 0], minlength=nu * nv).reshape(nu, nv).astype(float)
    pooled = scale_counts(np.concatenate([g.ravel() for g in grids.values()]), scale, enough=int(payload.get("enough", 10)))
    columns = min(len(order), 5)
    fig = _new_figure(3.3 * columns + 1.2, 4.6)
    axes = np.atleast_1d(fig.subplots(1, columns))
    every = sum(grids.values())
    mesh = None
    for k, (ax, name) in enumerate(zip(axes, order[:columns], strict=False)):
        t = pooled.t[k * nu * nv:(k + 1) * nu * nv].reshape(nu, nv)
        mesh = _heat(ax, u_edges, v_edges, t, _colormap(cmap, reverse))
        _crop(ax, every, u_edges, v_edges)
        ax.set_aspect("equal")
        ax.set_title(f"{name}: {int(grids[name].sum())}", fontsize=9, color=outcome_colours(payload)[name])
        ax.set_xlabel("x (mm)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.spines[["top", "right"]].set_visible(True)
    axes[0].set_ylabel("y (mm)")
    _colorbar(fig, mesh, list(axes), pooled, "grasps in the pixel")
    _header(fig, "Where does each outcome happen? One density map per outcome, one colour scale",
            _data_line(payload) + f" · 1 cm pixels from above, cropped to where any grasp sits · {pooled.note}",
            [_patch("white", "none there"), _ramp_patch(cmap, reverse, "colour = grasps of that outcome (bar)")])
    return fig


def _roll_rose(payload, cmap, reverse, scale):
    orientation = payload["orientation"]
    key = orientation["roll_shown"]
    block = orientation[key]
    low, high, count = block["edges"]
    width = (high - low) / count
    centres = low + (np.arange(count) + 0.5) * width
    groups = payload["source"]["groups"]
    colours = group_colours(payload)
    fig = _new_figure(7.4, 7.4)
    ax = fig.add_subplot(projection="polar")
    total = np.asarray(block["counts"], float)
    top = max(float(total.max()), 1.0)
    folded = key == "roll_folded"
    for offset, alpha in ((0.0, 1.0), (math.pi, 0.35)) if folded else ((0.0, 1.0),):
        bottom = np.zeros(count)
        for name in groups:
            counts = np.asarray(block["groups"].get(name, [0] * count), float) / top
            if counts.any():
                ax.bar(centres + offset, counts, width=width * 0.94, bottom=bottom, color=colours[name], alpha=alpha,
                       linewidth=0)
            bottom += counts
        ax.bar(centres[total > 0] + offset, 0.05, bottom=1.06, width=width * 0.94, color=INK, alpha=0.5 * alpha,
               linewidth=0)
    ax.set_ylim(0, 1.14)
    ax.set_yticks([])
    ax.set_xticks(np.radians([0, 45, 90, 135, 180, 225, 270, 315]),
                  ["0°", "45°", "90°", "135°", "±180°" if not folded else "180°", "−135°" if not folded else "225°",
                   "−90°" if not folded else "270°", "−45°" if not folded else "315°"], fontsize=8)
    ax.grid(color="#d2d2d7", linewidth=0.5)
    visited = int((total > 0).sum())
    ax.set_title(f"{visited} of {count} {math.degrees(width):.0f}° bins hold a grasp", fontsize=9, color=MUTED, pad=10)
    handles = [_patch(colours[name], name) for name in groups]
    handles.append(_patch(INK, "rim tick = a bin with any grasp"))
    _header(fig, "Which way do the jaws sit? A rose shows the symmetry",
            _data_line(payload) + " · bar length = grasps / the fullest bin, linear · "
            + ("folded two-finger roll: the faded half repeats it at +180°" if folded
               else "full circle: the jaws are not symmetric"), handles, columns=3)
    return fig


def _width_tilt_objects(payload, cmap, reverse, scale):
    from ..coverage import bins

    block = payload["width_tilt"]
    x_edges = edges(block["x_edges"])
    y_edges = edges(block["y_edges"])
    nx, ny = block["shape"]
    objects = [row["object_id"] for row in payload["objects"]][:8]
    grids = []
    for name in objects:
        rows = [row for row in payload["grasps"] if row["object_id"] == name]
        xi = bins.bin_index(np.array([row["width"] for row in rows]), *block["x_edges"])
        yi = bins.bin_index(np.array([row["tilt"] for row in rows]), *block["y_edges"])
        inside = (xi >= 0) & (yi >= 0)
        grid = np.bincount(xi[inside] * ny + yi[inside], minlength=nx * ny).reshape(nx, ny).astype(float)
        grids.append(100.0 * grid / max(grid.sum(), 1.0))  # share of the object's own grasps: one scale for all
    pooled = scale_counts(np.concatenate([g.ravel() for g in grids]), scale, enough=1)
    columns = min(len(objects), 4)
    rows_n = math.ceil(len(objects) / columns)
    fig = _new_figure(3.4 * columns + 1.2, 3.2 * rows_n + 1.4)
    axes = np.atleast_1d(fig.subplots(rows_n, columns, squeeze=False)).ravel()
    gripper = payload["gripper"]
    reach = max(90.0, min(180.0, 30.0 * math.ceil(max(_number(payload, "tilt_max_deg"), 1.0) / 30.0 + 0.001)))
    mesh = None
    for k, ax in enumerate(axes):
        if k >= len(objects):
            ax.set_visible(False)
            continue
        t = pooled.t[k * nx * ny:(k + 1) * nx * ny].reshape(nx, ny)
        mesh = _heat(ax, x_edges * 1000.0, np.degrees(y_edges), t, _colormap(cmap, reverse))
        if gripper["source"] == "limit":
            ax.axvline(gripper["high"] * 1000, color=LIMIT_COLOR, linewidth=1.2)
        if gripper["planner_high"] is not None:
            ax.axvline(gripper["planner_high"] * 1000, color=LIMIT_COLOR, linewidth=1.0, linestyle=(0, (4, 3)))
        ax.set_ylim(reach, 0)
        ax.set_title(objects[k], fontsize=9)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("width (mm)", fontsize=8)
        ax.spines[["top", "right"]].set_visible(True)
    axes[0].set_ylabel("tilt from straight down (°)")
    _colorbar(fig, mesh, [ax for ax in axes if ax.get_visible()], pooled, "% of the object's grasps")
    handles = [_patch("white", "no grasp"), _ramp_patch(cmap, reverse, "colour = share of that object's grasps"),
               _line("open stop"), _line("planner span", style=(0, (4, 3)), width=1.0)]
    _header(fig, "Per object: which widths from which tilts?",
            _data_line(payload) + " · each panel is its own object's share, so a 1 000-grasp object and a 30-grasp one "
            "share one colour scale · " + pooled.note, handles, columns=4)
    return fig


def _over_time(payload, cmap, reverse, scale):
    labels, buckets, axis_name = time_buckets(payload["grasps"])
    order = payload["outcomes"]["order"]
    colours = outcome_colours(payload)
    rows = payload["grasps"]
    counts = {name: np.array([sum(1 for lab, row in zip(labels, rows, strict=True) if lab == b and row["outcome"] == name)
                              for b in buckets], float) for name in order}
    fig = _new_figure(12.0, 5.6)
    ax = fig.subplots()
    x = np.arange(len(buckets))
    bottom = np.zeros(len(buckets))
    for name in order:
        ax.bar(x, counts[name], bottom=bottom, color=colours[name], width=0.8, linewidth=0)
        bottom += counts[name]
    ax.set_xticks(x, buckets, rotation=35 if len(buckets) > 8 else 0, ha="right" if len(buckets) > 8 else "center",
                  fontsize=8)
    ax.set_ylabel("grasps")
    ax.set_xlabel(axis_name)
    handles = [_patch(colours[name], name) for name in order]
    picked, failed = counts.get("picked"), counts.get("failed")
    if picked is not None and failed is not None:
        closed = picked + failed
        share = np.where(closed > 0, 100.0 * picked / np.maximum(closed, 1), np.nan)
        twin = ax.twinx()
        twin.plot(x, share, color=INK, marker="o", markersize=4, linewidth=1.4)
        for xi, (s, n) in enumerate(zip(share, closed, strict=True)):
            if np.isfinite(s):
                twin.annotate(f"{int(n)}", (xi, s), xytext=(0, 6), textcoords="offset points", ha="center",
                              fontsize=7, color=MUTED)
        twin.set_ylim(0, 105)
        twin.set_ylabel("picked share of the closed grasps (%)")
        twin.spines["right"].set_visible(True)
        handles.append(_line("picked share (right axis; the number = closed grasps)", color=INK, width=1.4))
    _header(fig, "How did the grasps and their outcomes change over time?",
            _data_line(payload) + f" · bars = grasps per {axis_name.split(',')[0]}, stacked by outcome", handles,
            columns=4)
    return fig


def _growth(payload, cmap, reverse, scale):
    growth = payload["growth"]
    x = np.asarray(growth["grasps"])
    series = (("position_pixels_xy", "xy pixels with a grasp (1 cm)"), ("direction_cells", "approach cells (of 288)"),
              ("width_bins", f"width bins (of {payload['width']['edges'][2]})"),
              ("roll_bins", f"roll bins (of {payload['orientation'][payload['orientation']['roll_shown']]['edges'][2]})"))
    fig = _new_figure(12.0, 6.2)
    axes = fig.subplots(2, 2).ravel()
    for ax, (key, words) in zip(axes, series, strict=True):
        y = np.asarray(growth[key])
        ax.plot(x, y, color=OUTCOME_COLORS["picked"], linewidth=1.6)
        ax.fill_between(x, 0, y, color=OUTCOME_COLORS["picked"], alpha=0.12, linewidth=0)
        half = int(np.searchsorted(y, 0.5 * y[-1]))
        ax.axvline(x[min(half, len(x) - 1)], color=MUTED, linewidth=0.8, linestyle=(0, (2, 2)))
        late = y[-1] - y[int(len(y) * 0.8)] if len(y) > 4 else 0
        ax.set_title(f"{words}: {y[-1]}; the last 20 % of grasps added {late}", fontsize=9)
        ax.set_xlabel("grasps so far (the given order)", fontsize=8)
        ax.set_ylim(0, max(y[-1], 1) * 1.1)
    _header(fig, "Are new grasps still adding coverage?",
            _data_line(payload) + " · a flat end means more of the same grasps will not fill anything new",
            [_line("distinct cells reached", color=OUTCOME_COLORS["picked"], width=1.6),
             _line("half of the final count reached", color=MUTED, style=(0, (2, 2)), width=0.8)])
    return fig


FIGURES = {"positions": _positions, "position-density": _position_density, "width": _width, "roll": _roll,
           "pointing": _pointing, "sphere": _sphere, "width-tilt": _width_tilt, "objects": _objects,
           "grippers": _grippers, "success-map": _success_map, "density-outcomes": _density_outcomes,
           "roll-rose": _roll_rose, "width-tilt-objects": _width_tilt_objects, "over-time": _over_time,
           "growth": _growth}


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
