"""Matplotlib view of a record-coverage payload ("traj_compare.record_coverage/1"): one PNG per figure.

    from traj_compare.record_coverage.matplotlib_view import plot_records
    paths = plot_records(payload, "out/png", cmap="viridis", reverse=False, scale="linear")

Figures: numbers.png (every number field against its range), classes.png (each category's balance), missing.png,
pair-<x>-<y>.png (one heat image per pair plane), growth.png (is more data still adding coverage?) and support.png
(only with a split: how much of each held-out level the reference level covers).

Reads ONLY the payload (docs/RECORD_COVERAGE.md "The other viewers"), so its pictures can never disagree with the
workbench, Viser or W&B. Every figure's title is the question it answers, its legend names every mark it draws, a heat
image's colour bar carries the scale's real numbers and its note, empty is white, beyond a stated range is grey and a
stated range is a solid red line; a field whose range came from the data says "no range stated" and draws no limit.
Values are shown as `value × display.scale` in `display.unit` (radians become degrees).

WHY the trajectory family's colour rule and drawing helpers are imported, not copied (coverage/matplotlib_view.py):
the three coverage families share one colour rule (a numpy mirror of assets/coverage_color.js) and one figure
grammar (the question as the legend's title, the data line at the foot), so a records heatmap and a trajectory
heatmap with the same settings paint the same count the same colour. matplotlib itself is imported only inside the
drawing functions, through its object API (`matplotlib.figure.Figure`, Agg canvas): no pyplot, no global backend.
"""

from __future__ import annotations

import math
import re
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..coverage.matplotlib_view import (
    BARS,
    GROUP_COLORS,
    INK,
    LIMIT_COLOR,
    MUTED,
    OUTSIDE_RGB,
    SCALE_TITLES,
    STYLE,
    _colorbar,
    _colormap,
    _header,
    _heat,
    _line,
    _locator,
    _new_figure,
    _patch,
    _ramp_patch,
    _rgb_hex,
    check_colour_choice,
    edges,
    ramp_rgb,
    scale_counts,
)
from .analysis import SCHEMA

OUTSIDE = _rgb_hex(OUTSIDE_RGB)
MISSING_ROWS_MAX = 60  # missing.png lists at most this many fields (worst first); the rest are counted in its foot
SOURCE_WORDS = {"given": "levels given", "declared": "levels declared", "enum": "levels = the enum's members",
                "bool": "False / True", "data": "levels as seen (none declared)"}


# ── payload helpers ──────────────────────────────────────────────────────────────────────────────────────────────────


def check_payload(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema != SCHEMA:
        raise ValueError(f"not a record_coverage payload ({SCHEMA}): schema {schema!r}")


def slug(name: str) -> str:
    """A field name as a file-name part: `tcp[0]` -> `tcp-0`; anything but letters, digits, '_', '.', '-' -> '-'."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", re.sub(r"\[(\d+)\]", r"-\1", name))


def pair_id(pair: Mapping[str, Any]) -> str:
    return f"pair-{slug(pair['x'])}-{slug(pair['y'])}"


def figure_ids(payload: Mapping[str, Any]) -> list[str]:
    """Every figure this view draws for `payload`, in reading order; each is also its PNG's stem."""
    ids = ["numbers", "classes", "missing"]
    ids += [pair_id(pair) for pair in payload.get("pairs") or []]
    ids.append("growth")
    if payload.get("support"):
        ids.append("support")
    return ids


def _field_rows(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {row["name"]: row for row in payload.get("fields") or []}


def _display(payload: Mapping[str, Any], name: str) -> tuple[float, str | None]:
    display = (_field_rows(payload).get(name) or {}).get("display") or {}
    return float(display.get("scale") or 1.0), display.get("unit")


def _axis_label(name: str, unit: str | None) -> str:
    return f"{name} ({unit})" if unit else name


def _value_text(value: float, unit: str | None) -> str:
    """−0.4 m / 74.5° / 9: a true minus, the degree sign hugging its number."""
    text = f"{value:.3g}".replace("-", "−")
    if not unit:
        return text
    return f"{text}{unit}" if unit == "°" else f"{text} {unit}"


def _count(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def _enough(payload: Mapping[str, Any]) -> int:
    return int(payload.get("enough", 10))


def _numbers(payload: Mapping[str, Any]) -> dict[str, float]:
    return {entry["key"]: float(entry["value"]) for entry in payload.get("numbers") or []}


def _groups(payload: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    source = payload.get("source") or {}
    return source.get("group_by"), list(source.get("groups") or [])


def _group_color(index: int) -> str:
    return GROUP_COLORS[index % len(GROUP_COLORS)]


def _group_handles(group_by: str | None, groups: Sequence[str]) -> list:
    return [_patch(_group_color(index), f"{group_by}: {group}") for index, group in enumerate(groups)]


def _data_line(payload: Mapping[str, Any]) -> str:
    source = payload.get("source") or {}
    records = int(source.get("records", 0))
    parts = [payload.get("title") or "record coverage", f"{_count(records)} record{'' if records == 1 else 's'}",
             f"{int(source.get('fields', 0))} fields"]
    if source.get("group_by"):
        parts.append(f"grouped by {source['group_by']}")
    if source.get("split"):
        parts.append(f"split by {source['split']} (reference {source.get('reference')})")
    return " · ".join(parts)


def _fit_columns(fig, handles: Sequence, most: int) -> int:
    """The most legend columns (<= `most`) whose widest labels still fit the figure's width (column-first filling,
    as matplotlib fills a legend); ~13 characters an inch at the legend's 8.5 pt, plus the swatch and the gap."""
    width = fig.get_figwidth() - 0.3
    for columns in range(min(most, len(handles)), 1, -1):
        rows = math.ceil(len(handles) / columns)
        widest = [max(len(handle.get_label()) for handle in handles[k * rows:(k + 1) * rows] or [handles[0]])
                  for k in range(columns)]
        if sum(chars / 13.0 + 0.55 for chars in widest) <= width:
            return columns
    return 1


def _title(fig, question: str, foot: str, handles: list, columns: int = 4) -> None:
    """coverage's `_header` (the question as the legend's title, the data line at the foot), with the question wrapped
    and the legend's columns fitted to the figure, so a long field name never runs off the PNG's edge."""
    # ~9 characters an inch at the question's 12.5 pt bold
    _header(fig, textwrap.fill(question, width=int(fig.get_figwidth() * 9)), foot, handles,
            columns=_fit_columns(fig, handles, columns))


def _message(payload: Mapping[str, Any], question: str, text: str):
    """A figure for an empty section (no number fields, no category fields ...): it says so instead of a blank."""
    fig = _new_figure(9.0, 3.0)
    ax = fig.subplots()
    ax.set_axis_off()
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=11, color=MUTED, transform=ax.transAxes)
    _title(fig, question, _data_line(payload), [_patch("white", "nothing to draw")])
    return fig


# ── the figures ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _numbers_figure(payload, cmap, reverse, scale):
    from matplotlib.ticker import MaxNLocator

    hist = payload.get("hist") or {}
    names = list(hist)
    question = "How much of each number field's range do the records cover, and where do they pile up?"
    if not names:
        return _message(payload, question, "These records have no number fields.")
    group_by, groups = _groups(payload)
    columns = 1 if len(names) == 1 else 2 if len(names) <= 4 else 3
    rows = math.ceil(len(names) / columns)
    fig = _new_figure(13.0 if columns > 1 else 10.5, 1.7 + 2.05 * rows + 0.6)
    grid = fig.subplots(rows, columns, squeeze=False)
    stacked_any = no_range_any = stated_any = False
    beyond_total = 0
    for index, ax in enumerate(grid.flat):
        if index >= len(names):
            ax.set_axis_off()
            continue
        name = names[index]
        block = hist[name]
        factor, unit = _display(payload, name)
        x = edges(block["edges"]) * factor
        total = np.asarray(block["counts"], float)
        stacked = bool(block.get("groups")) and bool(groups)
        if stacked:
            stacked_any = True
            bottom = np.zeros_like(total)
            for number, group in enumerate(groups):
                part = np.asarray(block["groups"].get(group) or np.zeros_like(total), float)
                if part.any():
                    ax.stairs(bottom + part, x, baseline=bottom, fill=True, color=_group_color(number), linewidth=0,
                              zorder=3)
                bottom = bottom + part
        else:
            ax.stairs(total, x, fill=True, color=BARS, linewidth=0, zorder=3)
        stated = block.get("source") != "data"
        low, high = float(block["low"]) * factor, float(block["high"]) * factor
        if stated:
            stated_any = True
            ax.axvspan(x[0], low, color=OUTSIDE, zorder=0, linewidth=0)
            ax.axvspan(high, x[-1], color=OUTSIDE, zorder=0, linewidth=0)
            for value in (low, high):
                ax.axvline(value, color=LIMIT_COLOR, linewidth=1.4, zorder=5)
        for extreme in (block["p001"], block["p999"]):
            ax.axvline(float(extreme) * factor, ymin=0.0, ymax=0.22, color=INK, linewidth=1.4, zorder=6)
        ax.set_xlim(x[0], x[-1])
        ax.set_ylim(0, max(float(total.max()), 1.0) * 1.4)
        ax.yaxis.set_major_locator(MaxNLocator(3, integer=True))
        ax.xaxis.set_major_locator(MaxNLocator(5, integer=bool(block.get("integer"))))
        ax.set_title(_axis_label(name, unit), fontsize=9.5)
        visited = float(block.get("visited_pct", 0.0))
        ax.set_title(f"visited {visited:.0f} % of its range" if stated else f"visited {visited:.0f} % of its data span",
                     loc="right", fontsize=8, color=MUTED)
        notes = []
        if not stated:
            no_range_any = True
            notes.append("no range stated")
        outside = int(block.get("outside", 0))
        if outside > 0:
            beyond_total += outside
            where = []
            if float(block["min"]) < float(block["low"]):
                where.append(f"min {_value_text(float(block['min']) * factor, unit)}")
            if float(block["max"]) > float(block["high"]):
                where.append(f"max {_value_text(float(block['max']) * factor, unit)}")
            notes.append(f"{_count(outside)} beyond the range" + (f" ({', '.join(where)})" if where else ""))
        if notes:
            ax.text(0.015, 0.97, " · ".join(notes), transform=ax.transAxes, fontsize=7.5, color=LIMIT_COLOR, va="top",
                    ha="left", zorder=8, bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2, "alpha": 0.9})
        if index % columns == 0:
            ax.set_ylabel("records", fontsize=8, color=MUTED)
    handles = _group_handles(group_by, groups) if stacked_any else [_patch(BARS, "records per bin")]
    if stated_any:
        handles += [_line("the stated range (given or declared)"), _patch(OUTSIDE, "beyond the stated range")]
    handles.append(_line("p0.1 / p99.9 of the data (short black ticks)", color=INK, width=1.4))
    foot = _data_line(payload) + " · bars: records per bin" + (f", stacked by {group_by}" if stacked_any else "")
    if no_range_any:
        foot += " · \"no range stated\": the axis is the data's own span × 1.15 and no limit is drawn"
    if beyond_total:
        foot += " · a value beyond the range by more than 10 % of it falls off the axis and is counted in red"
    _title(fig, question, foot, handles, columns=4)
    return fig


def _classes_figure(payload, cmap, reverse, scale):
    classes = payload.get("classes") or {}
    names = list(classes)
    question = "Is every class there, and how balanced are they?"
    if not names:
        return _message(payload, question, "These records have no category fields.")
    group_by, groups = _groups(payload)
    columns = 1 if len(names) == 1 else 2
    rows = math.ceil(len(names) / columns)
    ratios = [max(len(classes[name]["levels"]) for name in names[row * columns:(row + 1) * columns]) + 1.6
              for row in range(rows)]
    fig = _new_figure(13.0 if columns > 1 else 10.0, 1.7 + 0.3 * sum(ratios) + 0.6)
    grid = fig.subplots(rows, columns, squeeze=False, gridspec_kw={"height_ratios": ratios})
    stacked_any = unseen_any = undeclared_any = False
    for index, ax in enumerate(grid.flat):
        if index >= len(names):
            ax.set_axis_off()
            continue
        name = names[index]
        block = classes[name]
        levels = [str(level) for level in block["levels"]]
        counts = np.asarray(block["counts"], float)
        y = np.arange(len(levels))
        present = float(counts.sum())
        peak = max(float(counts.max()) if len(counts) else 0.0, 1.0)
        height = 0.68
        stacked = bool(block.get("groups")) and bool(groups)
        if stacked:
            stacked_any = True
            left = np.zeros_like(counts)
            for number, group in enumerate(groups):
                part = np.asarray(block["groups"].get(group) or np.zeros_like(counts), float)
                if part.any():
                    ax.barh(y, part, left=left, height=height, color=_group_color(number), linewidth=0, zorder=3)
                left = left + part
        else:
            ax.barh(y, counts, height=height, color=BARS, linewidth=0, zorder=3)
        unseen, undeclared = set(block.get("unseen") or []), set(block.get("undeclared") or [])
        stub = 0.08 * peak
        for row, level in enumerate(levels):
            if level in unseen:
                unseen_any = True
                ax.barh(row, stub, height=height, facecolor="white", edgecolor=LIMIT_COLOR, hatch="////",
                        linewidth=0.9, zorder=3)
                ax.text(stub + 0.02 * peak, row, "none — declared", va="center", ha="left", fontsize=7.5,
                        color=LIMIT_COLOR, zorder=6)
                continue
            ax.text(counts[row] + 0.02 * peak, row,
                    f"{_count(counts[row])} ({100 * counts[row] / present:.0f} %)" if present else "0",
                    va="center", ha="left", fontsize=7.5, color=MUTED, zorder=6)
            if level in undeclared:
                undeclared_any = True
                ax.barh(row, counts[row], height=height + 0.12, fill=False, edgecolor=INK, linestyle=(0, (3, 2)),
                        linewidth=1.0, zorder=4)
        ax.set_yticks(y, [f"{level} (not declared)" if level in undeclared else level for level in levels],
                      fontsize=8.5)
        for label, level in zip(ax.get_yticklabels(), levels, strict=False):
            if level in undeclared or level in unseen:
                label.set_color(LIMIT_COLOR)
        ax.set_ylim(ratios[index // columns] - 1.6 - 0.4, -0.6)  # first level on top; one bar height everywhere
        ax.set_xlim(0, peak * 1.32)
        ax.xaxis.set_major_locator(_locator(4))
        ax.tick_params(axis="y", length=0)
        ax.set_title(f"{name} · {SOURCE_WORDS.get(block.get('source'), block.get('source'))}", fontsize=9.5)
        ax.set_title(f"imbalance {float(block['imbalance_ratio']):.1f}× · evenness "
                     f"{float(block['evenness_pct']):.0f} %", loc="right", fontsize=8, color=MUTED)
        if index >= len(names) - columns:
            ax.set_xlabel("records", fontsize=8, color=MUTED)
    handles = _group_handles(group_by, groups) if stacked_any else [_patch(BARS, "records per level")]
    if unseen_any:
        handles.append(_hatch("declared level no record has (a missing class)"))
    if undeclared_any:
        handles.append(_dashed_box("level the declaration does not list (not declared)"))
    foot = (_data_line(payload) + " · beside each bar: its records (share of the field's present records) · "
            "imbalance = largest ÷ smallest seen class (1 = balanced) · evenness = effective classes "
            "(exp of the Shannon entropy) ÷ every level, declared or seen")
    _title(fig, question, foot, handles, columns=3)
    return fig


def _hatch(label: str):
    from matplotlib.patches import Patch

    return Patch(facecolor="white", edgecolor=LIMIT_COLOR, hatch="////", linewidth=0.9, label=label)


def _dashed_box(label: str):
    from matplotlib.patches import Patch

    return Patch(facecolor="none", edgecolor=INK, linestyle=(0, (3, 2)), linewidth=1.0, label=label)


def _missing_figure(payload, cmap, reverse, scale):
    rows = list(payload.get("fields") or [])
    numbers = _numbers(payload)
    question = "Which fields have missing values, and how many records are complete?"
    if not rows:
        return _message(payload, question, "These records have no fields.")
    order = sorted(range(len(rows)), key=lambda i: (-float(rows[i]["missing_pct"]), i))
    shown = order[:MISSING_ROWS_MAX]
    records = int((payload.get("source") or {}).get("records", 0))
    fig = _new_figure(9.5, 1.8 + 0.27 * len(shown) + 0.7)
    ax = fig.subplots()
    pct = np.asarray([float(rows[i]["missing_pct"]) for i in shown])
    y = np.arange(len(shown))
    ax.barh(y, pct, height=0.66, color=BARS, linewidth=0, zorder=3)
    top = max(float(pct.max()) if len(pct) else 0.0, 10.0) * 1.3
    for row, i in enumerate(shown):
        missing = int(rows[i]["missing"])
        text = f"{_count(missing)} of {_count(records)} ({pct[row]:.1f} %)" if missing else "none missing"
        ax.text(pct[row] + 0.01 * top, row, text, va="center", ha="left", fontsize=7.5,
                color=INK if missing else MUTED, zorder=6)
    ax.set_yticks(y, [f"{rows[i]['name']} · {rows[i]['kind']}" for i in shown], fontsize=8.5)
    ax.set_ylim(len(shown) - 0.4, -0.6)
    ax.set_xlim(0, top)
    ax.xaxis.set_major_locator(_locator(5))
    ax.xaxis.set_major_formatter(lambda value, _pos: f"{value:.0f} %")
    ax.set_xlabel("records missing a value in the field (None, NaN or absent)", fontsize=8.5, color=MUTED)
    ax.tick_params(axis="y", length=0)
    ax.set_title(f"{numbers.get('complete_records_pct', 0.0):.0f} % of records are complete (no field missing) · "
                 f"{numbers.get('missing_pct', 0.0):.1f} % of all values are missing", fontsize=9, color=MUTED)
    foot = _data_line(payload) + " · sorted worst first"
    if len(order) > len(shown):
        foot += f" · {len(order) - len(shown)} more fields with fewer missing values are not listed"
    _title(fig, question, foot, [_patch(BARS, "records missing the field (% of all records)")], columns=1)
    return fig


def _stated(payload: Mapping[str, Any], name: str) -> bool:
    return ((payload.get("hist") or {}).get(name) or {}).get("source", "data") != "data"


def _pair_figure(payload, pair, cmap, reverse, scale):
    x, y = pair["x"], pair["y"]
    x_scale, x_unit = _display(payload, x)
    y_scale, y_unit = _display(payload, y)
    x_edges, y_edges = edges(pair["x_edges"]) * x_scale, edges(pair["y_edges"]) * y_scale
    nx, ny = (int(v) for v in pair["shape"])
    samples = np.asarray(pair["samples"], float).reshape(nx, ny)  # counts[i * ny + j]: i along x, j up
    scaled = scale_counts(samples, scale, enough=_enough(payload))
    fig = _new_figure(8.0, 6.0)
    ax = fig.subplots()
    mesh = _heat(ax, x_edges, y_edges, scaled.t, _colormap(cmap, reverse))
    x_stated, y_stated = _stated(payload, x), _stated(payload, y)
    # WHY the frame is the limit: a pair plane spans EXACTLY the stated ranges, so its sides are the limits
    for side, stated in (("left", x_stated), ("right", x_stated), ("bottom", y_stated), ("top", y_stated)):
        spine = ax.spines[side]
        spine.set_visible(True)
        spine.set_color(LIMIT_COLOR if stated else MUTED)
        spine.set_linewidth(1.6 if stated else 0.8)
        spine.set_zorder(6)
    ax.set_xlim(x_edges[0], x_edges[-1])
    ax.set_ylim(y_edges[0], y_edges[-1])
    ax.xaxis.set_major_locator(_locator(6))
    ax.yaxis.set_major_locator(_locator(6))
    ax.set_xlabel(_axis_label(x, x_unit))
    ax.set_ylabel(_axis_label(y, y_unit))
    enough = _enough(payload)
    ax.set_title(f"{float(pair['visited_pct']):.0f} % of the {nx} × {ny} cells visited · "
                 f"{float(pair['sufficient_pct']):.0f} % have ≥ {enough} records · evenness "
                 f"{float(pair['evenness_pct']):.0f} %", fontsize=9, color=MUTED)
    bar = _colorbar(fig, mesh, ax, scaled, "records per cell")
    bar.set_label(f"records per cell\n{SCALE_TITLES[scaled.mode]}\n{scaled.note}", fontsize=8.5, color=INK)
    handles = [_patch("white", "no record in the cell"), _ramp_patch(cmap, reverse, "colour = records per cell (bar)")]
    if x_stated and y_stated:
        handles.append(_line("the stated ranges (the red frame)"))
    elif x_stated or y_stated:
        handles += [_line(f"the stated range of {x if x_stated else y} (red sides)"),
                    _line(f"no range stated for {y if x_stated else x}: its data span", color=MUTED, width=0.8)]
    else:
        handles.append(_line("no range stated: the frame is the data's span", color=MUTED, width=0.8))
    foot = _data_line(payload)
    outside, missing = int(pair.get("outside", 0)), int(pair.get("missing", 0))
    if outside or missing:
        foot += (f" · not drawn: {_count(outside)} record{'' if outside == 1 else 's'} beyond either range, "
                 f"{_count(missing)} missing a value")
    _title(fig, f"Which combinations of {x} and {y} do the records hold?", foot, handles)
    return fig


def _growth_figure(payload, cmap, reverse, scale):
    coverage = payload["coverage"]
    growth = coverage["growth"]
    records = np.asarray(growth["records"], float)
    given = np.asarray(growth["visited_pct"], float)
    shuffled = growth.get("shuffled") or {}
    ceiling = float(coverage.get("ceiling_pct", 0.0))
    fig = _new_figure(8.5, 4.9)
    ax = fig.subplots()
    accent = _rgb_hex(ramp_rgb(0.25, "viridis"))
    handles = [_line("in the records' own order", color=accent, width=2.2)]
    tops = [ceiling, float(given.max()) if len(given) else 0.0]
    if shuffled.get("median"):
        p10, p90 = np.asarray(shuffled["p10"], float), np.asarray(shuffled["p90"], float)
        ax.fill_between(records, p10, p90, color=MUTED, alpha=0.2, linewidth=0, zorder=2)
        ax.plot(records, shuffled["median"], color=MUTED, linewidth=1.3, zorder=3)
        handles += [_line("random orders: median (32 shuffles)", color=MUTED, width=1.3),
                    _patch(MUTED + "33", "random orders: p10 – p90 band", edge=MUTED + "33")]
        tops.append(float(p90.max()))
    ax.plot(records, given, color=accent, linewidth=2.2, zorder=4, marker="o" if len(records) <= 30 else None,
            markersize=3)
    ax.axhline(ceiling, color=INK, linewidth=1.1, linestyle=(0, (5, 3)), zorder=3)
    handles.append(_line(f"Chao1 ceiling: more of the same data reaches about {ceiling:.0f} %", color=INK,
                         style="--", width=1.1))
    last = max(float(records[-1]) if len(records) else 1.0, 1.0)
    if len(given):
        ax.annotate(f"{given[-1]:.1f} %", (records[-1], given[-1]), xytext=(6, -2), textcoords="offset points",
                    va="top", fontsize=9, color=accent, fontweight="bold")
    ax.set_xlim(0, last * 1.1)
    ax.set_ylim(0, min(max(max(tops), 1.0) * 1.15, 105.0))
    ax.xaxis.set_major_locator(_locator(8))
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f} %")
    ax.set_xlabel("records added")
    ax.set_ylabel("cells of the whole space visited")
    ax.grid(axis="y", color="#e6e6ea", linewidth=0.5)
    ax.set_title(f"the last 10 % of records first reached {float(coverage.get('last_tenth_new_pct', 0.0)):.1f} % of the "
                 f"visited cells", fontsize=9, color=MUTED)
    foot = (_data_line(payload) + f" · the space: {_count(coverage.get('cells', 0))} cells (each number field's bins "
            f"inside its range, each category's levels, each pair plane's cells), {_count(coverage.get('visited', 0))} "
            "visited · a curve still climbing at the right means more data would still help")
    _title(fig, "Is more data still adding coverage?", foot, handles, columns=2)
    return fig


def _support_figure(payload, cmap, reverse, scale):
    support = payload["support"]
    reference, split = support.get("reference"), support.get("split")
    levels = support.get("levels") or {}
    if not levels:
        return _message(payload, f"Does {reference} cover the other {split} levels?",
                        f"Only {split} = {reference} has records: nothing is held out.")
    names = list(levels)
    question = (f"Does {reference} cover the {names[0]} records?" if len(names) == 1
                else f"Does {reference} cover the other {split} levels?")
    columns = 1 if len(names) == 1 else 2
    rows = math.ceil(len(names) / columns)
    per_row = max(len(block.get("fields") or {}) for block in levels.values()) + 1
    fig = _new_figure(9.5 if columns == 1 else 14.0, 1.8 + rows * (0.27 * per_row + 0.8) + 0.6)
    grid = fig.subplots(rows, columns, squeeze=False)
    for index, ax in enumerate(grid.flat):
        if index >= len(names):
            ax.set_axis_off()
            continue
        level = names[index]
        block = levels[level]
        fields = block.get("fields") or {}
        order = sorted(fields, key=lambda name: (-float(fields[name]), list(fields).index(name)))
        labels = ["any field or pair plane", *order]
        values = np.asarray([float(block["unsupported_pct"]), *(float(fields[name]) for name in order)])
        colours = [INK] + [BARS] * len(order)
        y = np.arange(len(labels))
        ax.barh(y, values, height=0.66, color=colours, linewidth=0, zorder=3)
        for row, value in enumerate(values):
            ax.text(value + 1.0, row, f"{value:.0f} %" if value >= 1 or value == 0 else f"{value:.1f} %",
                    va="center", ha="left", fontsize=7.5, color=INK if row == 0 else MUTED, zorder=6)
        ax.set_yticks(y, labels, fontsize=8.5)
        ax.get_yticklabels()[0].set_fontweight("bold")
        ax.set_ylim(len(labels) - 0.4, -0.6)
        ax.set_xlim(0, 112)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.xaxis.set_major_formatter(lambda value, _pos: f"{value:.0f} %")
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel(f"share of the {level} records with a value no {reference} record has", fontsize=8.5, color=MUTED)
        ax.set_title(f"{level}: {float(block['unsupported_pct']):.0f} % of its {_count(block['records'])} records fall "
                     f"outside what {reference} covers", fontsize=9.5)
    handles = [_patch(INK, f"any field or pair plane: the record has ≥ 1 bin, level or cell no {reference} record has"),
               _patch(BARS, f"this field alone: its bin or level has no {reference} record")]
    foot = (_data_line(payload) + f" · {split} = {reference} is the reference · the top bar counts pair-plane cells "
            "too, so it can exceed every field's own bar")
    _title(fig, question, foot, handles, columns=1)
    return fig


FIGURES = {"numbers": _numbers_figure, "classes": _classes_figure, "missing": _missing_figure,
           "growth": _growth_figure, "support": _support_figure}


def figure(payload: Mapping[str, Any], figure_id: str, *, cmap: str = "viridis", reverse: bool = False,
           scale: str = "linear"):
    """One figure as a matplotlib `Figure` (not registered with pyplot). `figure_id` is a PNG stem from
    `figure_ids(payload)`: "numbers", "classes", "missing", "pair-<x>-<y>", "growth", "support"."""
    import matplotlib

    check_colour_choice(cmap, scale)
    check_payload(payload)
    with matplotlib.rc_context(STYLE):
        for pair in payload.get("pairs") or []:
            if pair_id(pair) == figure_id:
                return _pair_figure(payload, pair, cmap, reverse, scale)
        if figure_id not in figure_ids(payload) or figure_id not in FIGURES:
            raise KeyError(f"unknown figure {figure_id!r}; this payload has {', '.join(figure_ids(payload))}")
        return FIGURES[figure_id](payload, cmap, reverse, scale)


def plot_records(payload: Mapping[str, Any], out_dir: str | Path, *, cmap: str = "viridis", reverse: bool = False,
                 scale: str = "linear") -> list[Path]:
    """Write one PNG per figure into `out_dir` (created) and return their paths, in `figure_ids` order."""
    import matplotlib

    check_colour_choice(cmap, scale)
    check_payload(payload)
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
