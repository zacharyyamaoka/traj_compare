"""Matplotlib view of a trajectory-coverage payload ("traj_compare.coverage/1"): one PNG per 2-D figure.

    from traj_compare.coverage.matplotlib_view import plot_coverage
    paths = plot_coverage(payload, "out/png", cmap="viridis", reverse=False, scale="linear")

Reads ONLY the payload dict (docs/COVERAGE.md "The other viewers"), so its pictures can never disagree with the page,
Viser or W&B. Every figure's title is the question it answers, its legend names every mark it draws, and its colour
bar carries the scale's real numbers. Values are SI in the payload; angles are shown in degrees and lengths in mm
(the payload's `display.scale/unit`).

The colour + scale rule at the top of this file is a numpy mirror of `assets/coverage_color.js` (the page's), so a
Matplotlib heatmap and a page heatmap with the same settings paint the same cell the same colour; the Viser view
imports it from here. matplotlib itself is imported only inside the drawing functions, through its object API
(`matplotlib.figure.Figure`, Agg canvas): no pyplot, so no global backend switch and no figure registry to leak.
"""

from __future__ import annotations

import math
import re
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# ── the colour + scale rule (mirror of assets/coverage_color.js) ─────────────────────────────────────────────────────

# WHY BAM Reach's five maps and "Reverse (high = dark)": Zach, 2026-11-23, "lets just do what we did with like bam
# reach. we can use viridis. but lets make it easy for the user to change ... to other good cmap and switch from high
# to low". The 17 stops are coverage_color.js's (= robot_reach codes.py COLORMAPS); a test pins them equal.
COLORMAPS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "viridis": ((68, 1, 84), (72, 24, 106), (71, 45, 123), (66, 64, 134), (59, 82, 139), (51, 99, 141),
                (44, 114, 142), (38, 130, 142), (33, 145, 140), (31, 160, 136), (40, 174, 128), (63, 188, 115),
                (94, 201, 98), (132, 212, 75), (173, 220, 48), (216, 226, 25), (253, 231, 37)),
    "magma": ((0, 0, 4), (10, 8, 34), (29, 17, 71), (54, 16, 107), (81, 18, 124), (106, 28, 129), (131, 38, 129),
              (156, 46, 127), (183, 55, 121), (208, 65, 111), (231, 82, 99), (245, 107, 92), (252, 137, 97),
              (254, 167, 114), (254, 196, 136), (253, 226, 163), (252, 253, 191)),
    "plasma": ((13, 8, 135), (49, 5, 151), (76, 2, 161), (102, 0, 167), (126, 3, 168), (149, 17, 161),
               (170, 35, 149), (188, 53, 135), (204, 71, 120), (218, 90, 106), (230, 108, 92), (240, 128, 78),
               (248, 149, 64), (253, 172, 51), (253, 197, 39), (248, 223, 37), (240, 249, 33)),
    "inferno": ((0, 0, 4), (11, 7, 36), (33, 12, 74), (61, 9, 101), (87, 16, 110), (113, 25, 110), (138, 34, 106),
                (163, 44, 97), (188, 55, 84), (210, 70, 68), (228, 90, 49), (241, 115, 29), (249, 142, 9),
                (252, 172, 17), (249, 203, 53), (242, 234, 105), (252, 255, 164)),
    "cividis": ((0, 34, 78), (0, 46, 106), (26, 56, 111), (50, 67, 109), (67, 78, 108), (83, 90, 109),
                (97, 101, 111), (111, 112, 115), (125, 124, 120), (140, 136, 120), (155, 148, 118), (171, 160, 114),
                (188, 174, 108), (205, 187, 99), (222, 201, 88), (240, 216, 70), (254, 232, 56)),
}
COLORMAP_NAMES: tuple[str, ...] = tuple(COLORMAPS)
# WHY linear first: Zach 2026-11-23, "Linear to me is BY far the most informative here".
SCALES: tuple[str, ...] = ("linear", "log", "equalized", "visited", "enough")
SCALE_TITLES = {"linear": "linear (clipped at p98)", "log": "log", "equalized": "histogram-equalized",
                "visited": "visited / not", "enough": "≥ enough samples / not"}
# WHY empty is white, never a colormap colour: Zach 2026-11-19, "so its clear that white means empty".
EMPTY_RGB = (255, 255, 255)
OUTSIDE_RGB = (221, 220, 214)  # beyond the limit: the robot cannot go there
LIMIT_COLOR = "#b4442f"  # limit lines: solid = the limit, dashed = the planner's
INK = "#1d1d1f"
MUTED = "#6e6e73"
HAIR = "#d2d2d7"
BARS = "#3d5a80"  # 1-D histograms: one calm ink, so colour stays reserved for "how much" in the heatmaps
# Group colours (Paul Tol "bright", colour-blind safe), in the order of payload["source"]["groups"].
GROUP_COLORS = ("#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee", "#aa3377", "#bbbbbb")


def check_colour_choice(cmap: str, scale: str) -> None:
    if cmap not in COLORMAPS:
        raise ValueError(f"cmap={cmap!r}: expected one of {', '.join(COLORMAP_NAMES)}")
    if scale not in SCALES:
        raise ValueError(f"scale={scale!r}: expected one of {', '.join(SCALES)}")


def ramp_rgb(t: Any, cmap: str = "viridis", reverse: bool = False) -> np.ndarray:
    """t in [0, 1] (any shape) -> uint8 RGB (shape + (3,)), interpolating the 17 stops exactly as the page does."""
    stops = np.asarray(COLORMAPS.get(cmap, COLORMAPS["viridis"]), float)
    if reverse:
        stops = stops[::-1]
    last = len(stops) - 1
    x = np.clip(np.asarray(t, float), 0.0, 1.0) * last
    lower = np.minimum(last - 1, np.floor(x)).astype(int)
    fraction = (x - lower)[..., None]
    rgb = stops[lower] + (stops[lower + 1] - stops[lower]) * fraction
    return np.floor(rgb + 0.5).astype(np.uint8)  # Math.round


def tick_label(value: float) -> str:
    """coverage_color.js round(): 412 -> "412", 12.5 -> "12.5", 0.25 -> "0.25", 3 -> "3"."""
    if value >= 100:
        return str(int(math.floor(value + 0.5)))
    if value >= 10:
        text = f"{value:.1f}"
        return text[:-2] if text.endswith(".0") else text
    text = format(value, "#.2g")
    return re.sub(r"\.?0+$", "", text) if "." in text else text


@dataclass(frozen=True)
class Scaled:
    """What a scale did to a count array: `t` (-1 = empty, else 0..1), colour-bar `ticks` [(t, label)], a `note`."""

    t: np.ndarray
    ticks: tuple[tuple[float, str], ...]
    note: str
    top: float
    mode: str


def scale_counts(counts: Any, mode: str = "linear", *, enough: int = 10, clip: float = 0.98,
                 top: float | None = None) -> Scaled:
    """coverage_color.js scale(): counts (None / NaN = no value) -> colour positions, ticks and a note.

    `top` forces the top of the linear / log scale (a shared max across small multiples)."""
    values = np.asarray([np.nan if value is None else value for value in np.ravel(counts)], float).reshape(
        np.shape(counts))
    t = np.full(values.shape, -1.0)
    visited = np.isfinite(values) & (values > 0)
    nonzero = np.sort(values[visited])
    if not len(nonzero):
        return Scaled(t, (), "nothing visited", 0.0, mode)
    highest = float(nonzero[-1])
    if mode == "visited":
        t[visited] = 1.0
        return Scaled(t, ((1.0, "visited"),), f"{len(nonzero)} cells visited", highest, mode)
    if mode == "enough":
        full = visited & (values >= enough)
        t[visited] = 0.25
        t[full] = 1.0
        return Scaled(t, ((0.25, f"< {enough}"), (1.0, f"≥ {enough}")),
                      f"{int(full.sum())} of {len(nonzero)} visited cells have ≥ {enough}", highest, mode)
    if mode == "equalized":
        # WHY it lifts thin cells: each cell's colour is its RANK among visited cells (the empirical CDF), so a cell
        # walked once spreads over the same colour range as one walked 1000 times. It shows WHERE, not HOW MUCH.
        below = np.searchsorted(nonzero, values[visited], side="left")
        upto = np.searchsorted(nonzero, values[visited], side="right")
        t[visited] = ((below + upto - 1) / 2) / (len(nonzero) - 1) if len(nonzero) > 1 else 1.0
        ticks = tuple((q, tick_label(float(np.quantile(nonzero, q)))) for q in (0.0, 0.25, 0.5, 0.75, 1.0))
        return Scaled(t, ticks, "colour = rank among visited cells", highest, mode)
    if mode == "log":
        scale_top = top or highest
        denominator = math.log1p(scale_top)
        t[visited] = np.minimum(1.0, np.log1p(values[visited]) / denominator)
        ticks = [(math.log1p(v) / denominator, tick_label(v)) for v in (1, 10, 100, 1000, 10000, 100000)
                 if v <= scale_top]
        ticks.append((1.0, tick_label(scale_top)))
        return Scaled(t, tuple(ticks), f"log, top {tick_label(scale_top)}", scale_top, mode)
    if mode != "linear":
        raise ValueError(f"scale={mode!r}: expected one of {', '.join(SCALES)}")
    scale_top = top or max(float(np.quantile(nonzero, clip)), float(nonzero[0]))
    t[visited] = np.minimum(1.0, values[visited] / scale_top)
    ticks = tuple((q, tick_label(q * scale_top)) for q in (0.0, 0.25, 0.5, 0.75, 1.0))
    note = (f"clipped at p{round(clip * 100)}: {tick_label(scale_top)} (top cell {tick_label(highest)})"
            if highest > scale_top else f"top {tick_label(scale_top)}")
    return Scaled(t, ticks, note, scale_top, mode)


# ── payload helpers ──────────────────────────────────────────────────────────────────────────────────────────────────

SIGNAL_WORDS = {"q": "position", "qd": "speed", "qdd": "acceleration", "qddd": "jerk"}
SIGNAL_POWERS = {"q": "", "qd": "/s", "qdd": "/s²", "qddd": "/s³"}


def edges(block: Sequence[float]) -> np.ndarray:
    """A payload edge triple [low, high, bins] -> the bins + 1 linear edges."""
    low, high, bins = block
    return np.linspace(float(low), float(high), int(bins) + 1)


def joint_display(payload: Mapping[str, Any], joint: str) -> tuple[float, str]:
    for entry in payload["joints"]:
        if entry["name"] == joint:
            return float(entry["display"]["scale"]), str(entry["display"]["unit"])
    raise KeyError(joint)


def signal_unit(unit: str, signal: str) -> str:
    return unit + SIGNAL_POWERS[signal]


def joint_names(payload: Mapping[str, Any]) -> list[str]:
    return [entry["name"] for entry in payload["joints"]]


def slug(name: str) -> str:
    """A joint name as a file-name part: anything but letters, digits, '_', '.' and '-' becomes '-'."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "joint"


def figure_ids(payload: Mapping[str, Any]) -> list[str]:
    """Every figure this view draws for `payload`, in reading order; each is also its PNG's stem."""
    names = joint_names(payload)
    ids = ["ridgeline", "limit-bars"]
    ids += [f"heat-q-qd-{slug(name)}" for name in names]
    ids += [f"slabs-{slug(name)}" for name in names]
    ids += ["parallel-q", "growth"]
    if payload.get("tool"):
        ids += ["projections", "tool-speed", "tilt-map", "tilt-yaw"]
    return ids


def tool_frame(payload: Mapping[str, Any]) -> tuple[str, str]:
    """(frame name, what its origin is called) of the payload's tool poses.

    WHY from the payload, never "robot base": the UR5e cell pages give the tool in the CELL frame (the arm hangs upside
    down there), so the origin is only the robot base when the frame says so."""
    frame = str((payload.get("tool") or {}).get("frame") or "base")
    return frame, ("robot base" if frame in ("base", "base_link") else f'origin of "{frame}"')


def _reference_words(reference: Sequence[float]) -> str:
    x, y, z = (float(v) for v in reference)
    if abs(x) < 1e-9 and abs(y) < 1e-9 and z < 0:
        return "straight down"
    if abs(x) < 1e-9 and abs(y) < 1e-9 and z > 0:
        return "straight up"
    return f"along ({x:.2g}, {y:.2g}, {z:.2g})"


def _value_text(value: float, unit: str) -> str:
    """+360° / −120 mm: a true minus, and the degree sign for angles."""
    text = f"{value:+.0f}".replace("-", "−")
    return f"{text}°" if unit == "deg" else f"{text} {unit}"


def _percent_tick(value: float, signed: bool) -> str:
    if not signed:
        return f"{value:.0f} %"
    return f"{value:+.0f} %".replace("-", "−") if value else "0 %"


def _count(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def _data_line(payload: Mapping[str, Any]) -> str:
    source = payload.get("source", {})
    title = payload.get("title") or "coverage"
    trajectories = int(source.get("trajectories", 0))
    parts = [title, f"{trajectories} trajector{'y' if trajectories == 1 else 'ies'}",
             f"{_count(source.get('samples', 0))} samples"]
    if source.get("duration_s"):
        parts.append(f"{float(source['duration_s']):.0f} s")
    return " · ".join(parts)


def _enough(payload: Mapping[str, Any]) -> int:
    return int(payload.get("enough", 10))


# ── drawing helpers (matplotlib imported here, lazily) ───────────────────────────────────────────────────────────────

STYLE = {
    "font.family": "DejaVu Sans", "font.size": 9.0, "axes.titlesize": 9.5, "axes.titlelocation": "left",
    "axes.edgecolor": HAIR, "axes.labelcolor": INK, "axes.titlecolor": INK, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelsize": 8.0, "ytick.labelsize": 8.0, "legend.frameon": False, "legend.fontsize": 8.5,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "figure.constrained_layout.h_pad": 0.06, "figure.constrained_layout.w_pad": 0.06,
}


def _colormap(cmap: str, reverse: bool):
    from matplotlib.colors import LinearSegmentedColormap

    stops = np.asarray(COLORMAPS[cmap], float) / 255.0
    if reverse:
        stops = stops[::-1]
    colormap = LinearSegmentedColormap.from_list(f"{cmap}{'_r' if reverse else ''}", stops, N=256)
    return colormap.with_extremes(bad="white")  # masked = empty = the page


def _new_figure(width: float, height: float):
    from matplotlib.figure import Figure

    return Figure(figsize=(width, height), layout="constrained", dpi=130)


def _header(fig, question: str, footnote: str, handles: list, columns: int | None = None) -> None:
    """The question as the title, the legend (every mark the figure draws) right under it, the data line at the foot.

    WHY the question is the legend's title, not a suptitle: constrained layout stacks an "outside" legend under the
    axes area but not under a suptitle, so the two overlapped; as one block they can't."""
    legend = fig.legend(handles=handles, loc="outside upper left", ncols=columns or min(len(handles), 4),
                        handlelength=1.6, columnspacing=1.6, borderaxespad=0.3, title=question, alignment="left",
                        title_fontproperties={"weight": "bold", "size": 12.5})
    legend.get_title().set_color(INK)
    # ~16 characters an inch at 8 pt: wrapped so a long data line never runs off the PNG's right edge
    fig.supxlabel(textwrap.fill(footnote, width=int(fig.get_figwidth() * 16)), x=0.01, ha="left", fontsize=8,
                  color=MUTED, linespacing=1.3)


def _patch(color, label: str, edge: str | None = None):
    from matplotlib.patches import Patch

    return Patch(facecolor=color, edgecolor=edge or (HAIR if color in ("white", "#ffffff") else color), label=label)


def _line(label: str, color: str = LIMIT_COLOR, style: str = "-", width: float = 1.4):
    from matplotlib.lines import Line2D

    return Line2D([], [], color=color, linestyle=style, linewidth=width, label=label)


def _rgb_hex(rgb: Sequence[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(int(c) for c in rgb))


def _ramp_patch(cmap: str, reverse: bool, label: str):
    """A legend swatch that shows the ramp (three stops) so 'colour = how much' reads in the legend too."""
    return _patch(_rgb_hex(ramp_rgb(0.6, cmap, reverse)), label)


def _heat(ax, x_edges: np.ndarray, y_edges: np.ndarray, t: np.ndarray, colormap, outside: np.ndarray | None = None):
    """t[i, j] over x bin i, y bin j (-1 = empty -> white); `outside` cells painted the beyond-the-limit grey."""
    from matplotlib.colors import ListedColormap

    shown = np.ma.masked_where(t < 0, t)
    mesh = ax.pcolormesh(x_edges, y_edges, shown.T, cmap=colormap, vmin=0.0, vmax=1.0, shading="flat",
                         rasterized=True)
    if outside is not None and np.any(outside):
        grey = np.ma.masked_where(~outside.T, np.ones(outside.T.shape))
        ax.pcolormesh(x_edges, y_edges, grey, cmap=ListedColormap([_rgb_hex(OUTSIDE_RGB)]), vmin=0, vmax=1,
                      shading="flat", rasterized=True)
    return mesh


def _colorbar(fig, mesh, axes, scaled: Scaled, label: str, **options):
    bar = fig.colorbar(mesh, ax=axes, fraction=0.05, pad=0.02, aspect=28, **options)
    bar.outline.set_visible(False)
    if scaled.ticks:
        bar.set_ticks([t for t, _ in scaled.ticks], labels=[text for _, text in scaled.ticks])
    bar.ax.tick_params(labelsize=8, colors=MUTED, length=2)
    bar.set_label(f"{label}\n{SCALE_TITLES[scaled.mode]}", fontsize=8.5, color=INK)
    return bar


def _limit_box(ax, x_limit: Mapping[str, Any] | None, y_limit: Mapping[str, Any] | None, scale_x: float,
               scale_y: float, planner_x=None, planner_y=None) -> None:
    """Red frame where a limit is stated (solid), dashed red for the planner's own bound."""
    for limit, vertical, scale in ((x_limit, True, scale_x), (y_limit, False, scale_y)):
        if not limit or limit.get("source") != "limit":
            continue
        for value in (limit["low"], limit["high"]):
            (ax.axvline if vertical else ax.axhline)(value * scale, color=LIMIT_COLOR, linewidth=1.6, zorder=5)
    for limit, vertical, scale in ((planner_x, True, scale_x), (planner_y, False, scale_y)):
        if not limit:
            continue
        for value in (limit["low"], limit["high"]):
            (ax.axvline if vertical else ax.axhline)(value * scale, color=LIMIT_COLOR, linewidth=1.2,
                                                     linestyle=(0, (4, 3)), zorder=5)


def _limit_frame(ax, stated: bool) -> None:
    """A q x qd plane spans exactly the limits, so its frame IS the limit: drawn as red spines when one is stated."""
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(LIMIT_COLOR if stated else HAIR)
        spine.set_linewidth(1.6 if stated else 0.8)
        spine.set_zorder(6)


def _planner(payload: Mapping[str, Any], joint: str, signal: str) -> Mapping[str, Any] | None:
    planner = payload.get("planner_limits") or {}
    return (planner.get(joint) or {}).get(signal)


def _has_planner(payload: Mapping[str, Any], signals: Sequence[str], joints: Sequence[str] | None = None) -> bool:
    return any(_planner(payload, joint, signal) for joint in (joints or joint_names(payload)) for signal in signals)


def _limit_words(limit: Mapping[str, Any] | None) -> str:
    kind = (limit or {}).get("kind")
    return f"limit ({kind})" if kind else "limit"


# ── the figures ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _ridgeline(payload, cmap, reverse, scale):
    names = joint_names(payload)
    signals = ("q", "qd", "qdd")
    fig = _new_figure(12.5, 1.15 + 0.62 * len(names) + 0.9)
    axes = fig.subplots(1, 3, sharey=True)
    words = {"q": "q · position", "qd": "qd · speed", "qdd": "qdd · acceleration"}
    x_words = {"q": "% of the range (0 = low limit, 100 = high limit)", "qd": "% of the ± speed limit",
               "qdd": "% of the ± acceleration limit"}
    no_limit_rows = False
    for ax, signal in zip(axes, signals, strict=False):
        for row, joint in enumerate(names):
            block = payload["hist"][joint][signal]
            limit = payload["limits"][joint][signal]
            low, high = float(limit["low"]), float(limit["high"])
            x = edges(block["edges"])
            if signal == "q":
                to_pct = lambda v, low=low, high=high: (np.asarray(v, float) - low) / (high - low) * 100.0  # noqa: E731
            else:
                reach = max(abs(low), abs(high)) or 1.0
                to_pct = lambda v, reach=reach: np.asarray(v, float) / reach * 100.0  # noqa: E731
            counts = np.asarray(block["counts"], float)
            base = -row
            stated = limit.get("source") == "limit"
            no_limit_rows |= not stated
            if counts.max() > 0:
                height = 0.82 * counts / counts.max()
                ax.fill_between(to_pct(x[:-1]), base, base + height, step="post", linewidth=0,
                                color=BARS if stated else MUTED, alpha=0.95 if stated else 0.55, zorder=3)
                ax.stairs(base + height, to_pct(x), baseline=base, color="white", linewidth=0.4, zorder=3.5)
                lo, hi = to_pct([block["p001"], block["p999"]])
                ax.plot([lo, hi], [base - 0.08] * 2, color=INK, linewidth=0.9, solid_capstyle="butt", zorder=4)
                ax.plot([lo, lo, np.nan, hi, hi], [base - 0.14, base - 0.02, np.nan, base - 0.14, base - 0.02],
                        color=INK, linewidth=0.9, zorder=4)
            figure_text = (f"{block['span_pct']:.0f} %" if signal == "q" else f"peak {block['peak_pct']:.0f} %")
            if not stated:
                figure_text = "no limit stated"
            ax.text(1.005, base + 0.3, figure_text, transform=ax.get_yaxis_transform(), fontsize=7.5,
                    color=MUTED if stated else LIMIT_COLOR, va="center", ha="left", clip_on=False)
        lows, highs = ((0.0, 100.0) if signal == "q" else (-100.0, 100.0))
        span = highs - lows
        ax.set_xlim(lows - 0.1 * span, highs + 0.1 * span)
        ax.axvspan(lows - 0.2 * span, lows, color=_rgb_hex(OUTSIDE_RGB), zorder=0, linewidth=0)
        ax.axvspan(highs, highs + 0.2 * span, color=_rgb_hex(OUTSIDE_RGB), zorder=0, linewidth=0)
        for value in (lows, highs):
            ax.axvline(value, color=LIMIT_COLOR, linewidth=1.3, zorder=5)
        ax.set_title(words[signal], fontsize=10)
        ax.set_xlabel(x_words[signal], fontsize=8.5, color=MUTED)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_xticks([lows, lows + span / 2, highs] if signal == "q" else [-100, -50, 0, 50, 100])
        ax.xaxis.set_major_formatter(lambda value, _pos, signal=signal: _percent_tick(value, signed=signal != "q"))
    axes[0].set_yticks([-row + 0.3 for row in range(len(names))], names, fontsize=8.5)
    axes[0].set_ylim(-(len(names) - 1) - 0.3, 1.0)
    handles = [_patch(BARS, "samples (height: linear count, each row scaled to its own peak)"),
               _line("the limit"), _patch(_rgb_hex(OUTSIDE_RGB), "beyond the limit"),
               _line("p0.1 – p99.9 of the data (bar under each ridge)", color=INK, width=1.0)]
    if no_limit_rows:
        handles.append(_patch(MUTED, "grey ridge = no limit stated: % of the data's own span × 1.15"))
    _header(fig, "Which joints use their whole range, and which stay in the middle?",
            _data_line(payload) + " · right of each row: q = share of the range used (p0.1–p99.9); "
            "qd / qdd = peak as a share of the limit", handles, columns=4)
    return fig


def _limit_bars(payload, cmap, reverse, scale):
    names = joint_names(payload)
    signals = [s for s in ("q", "qd", "qdd", "qddd") if s in payload.get("signals", ("q", "qd", "qdd", "qddd"))]
    groups = list((payload.get("source") or {}).get("groups") or [])
    group_by = (payload.get("source") or {}).get("group_by")
    fig = _new_figure(13.0, 1.3 + 0.95 * len(names) + 0.9)
    grid = fig.subplots(len(names), len(signals), squeeze=False)
    outside_total = 0
    for row, joint in enumerate(names):
        scale_value, unit = joint_display(payload, joint)
        for column, signal in enumerate(signals):
            ax = grid[row][column]
            block = payload["hist"][joint][signal]
            limit = payload["limits"][joint][signal]
            x = edges(block["edges"]) * scale_value
            stated = limit.get("source") == "limit"
            total = np.asarray(block["counts"], float)
            peak = max(total.max(), 1.0)
            if block.get("groups") and groups:
                bottom = np.zeros_like(total)
                for index, group in enumerate(groups):
                    part = np.asarray(block["groups"].get(group, np.zeros_like(total)), float)
                    color = GROUP_COLORS[index % len(GROUP_COLORS)]
                    ax.stairs((bottom + part) / peak, x, baseline=bottom / peak, fill=True, color=color,
                              linewidth=0, zorder=3)
                    bottom = bottom + part
            else:
                ax.stairs(total / peak, x, fill=True, color=BARS, linewidth=0, zorder=3)
            low, high = float(limit["low"]) * scale_value, float(limit["high"]) * scale_value
            if stated:
                ax.axvspan(x[0], low, color=_rgb_hex(OUTSIDE_RGB), zorder=0, linewidth=0)
                ax.axvspan(high, x[-1], color=_rgb_hex(OUTSIDE_RGB), zorder=0, linewidth=0)
                for value in (low, high):
                    ax.axvline(value, color=LIMIT_COLOR, linewidth=1.4, zorder=5)
            planner = _planner(payload, joint, signal)
            if planner:
                for value in (planner["low"], planner["high"]):
                    ax.axvline(float(value) * scale_value, color=LIMIT_COLOR, linewidth=1.1,
                               linestyle=(0, (4, 3)), zorder=5)
            for extreme in (block["p001"], block["p999"]):
                ax.axvline(float(extreme) * scale_value, ymin=0.0, ymax=0.3, color=INK, linewidth=1.3, zorder=6)
            ax.set_xlim(x[0], x[-1])
            ax.set_ylim(0, 1.18)
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
            ax.xaxis.set_major_locator(_locator(5))
            if not stated:
                note, color = "no limit stated (axis = data span × 1.15)", LIMIT_COLOR
            elif signal == "q":
                note, color = f"{block['span_pct']:.0f} % of range used", MUTED
            else:
                note, color = f"peak {block['peak_pct']:.0f} % of limit", MUTED
            outside = int(block.get("outside", 0))
            outside_total += outside
            if outside:
                note += f" · {_count(outside)} beyond ▸"
                color = LIMIT_COLOR
            ax.text(0.015, 0.99, note, transform=ax.transAxes, fontsize=7.3, color=color, va="top", ha="left",
                    zorder=8, bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2, "alpha": 0.9})
            if row == 0:
                ax.set_title(f"{signal}: {SIGNAL_WORDS[signal]} ({signal_unit(unit, signal)})", fontsize=9.5)
            if column == 0:
                ax.set_ylabel(joint, rotation=0, ha="right", va="center", fontsize=9, color=INK, labelpad=6)
    handles = []
    if block.get("groups") and groups:
        handles += [_patch(GROUP_COLORS[i % len(GROUP_COLORS)], f"{group_by}: {group}") for i, group in
                    enumerate(groups)]
    else:
        handles.append(_patch(BARS, "samples (linear, each panel scaled to its peak)"))
    handles += [_line("the limit"), _patch(_rgb_hex(OUTSIDE_RGB), "beyond the limit")]
    if _has_planner(payload, signals):
        handles.append(_line("planner limit", style="--", width=1.1))
    handles.append(_line("p0.1 / p99.9 of the data (short black ticks)", color=INK, width=1.3))
    _header(fig, "How much of each joint's limits does the data use, and where does it pile up?",
            _data_line(payload) + (" · stacked by " + group_by if groups and group_by else "")
            + (f" · {_count(outside_total)} samples beyond a limit" if outside_total else ""),
            handles, columns=min(len(handles), 4))
    return fig


def _locator(count: int):
    from matplotlib.ticker import MaxNLocator

    return MaxNLocator(count)


def _heat_q_qd(payload, joint, cmap, reverse, scale):
    plane = payload["planes"][joint]["q_qd"]
    scale_value, unit = joint_display(payload, joint)
    x_edges, y_edges = edges(plane["x_edges"]) * scale_value, edges(plane["y_edges"]) * scale_value
    nx, ny = plane["shape"]
    samples = np.asarray(plane["samples"], float).reshape(nx, ny)
    scaled = scale_counts(samples, scale, enough=_enough(payload))
    fig = _new_figure(8.0, 5.6)
    ax = fig.subplots()
    mesh = _heat(ax, x_edges, y_edges, scaled.t, _colormap(cmap, reverse))
    limits = payload["limits"][joint]
    stated = limits["q"].get("source") == "limit" and limits["qd"].get("source") == "limit"
    _limit_box(ax, None, None, scale_value, scale_value, _planner(payload, joint, "q"), _planner(payload, joint, "qd"))
    _limit_frame(ax, stated)
    ax.set_xlim(x_edges[0], x_edges[-1])
    ax.set_ylim(y_edges[0], y_edges[-1])
    ax.set_xlabel(f"q, position ({unit})")
    ax.set_ylabel(f"qd, speed ({signal_unit(unit, 'qd')})")
    ax.set_title(f"{plane['visited_pct']:.0f} % of the {nx} × {ny} cells visited · {plane['sufficient_pct']:.0f} % "
                 f"have ≥ {_enough(payload)} samples · evenness {plane['evenness_pct']:.0f} %", fontsize=9,
                 color=MUTED)
    _colorbar(fig, mesh, ax, scaled, "samples per cell")
    handles = [_patch("white", "never visited"), _ramp_patch(cmap, reverse, "visited: colour = samples (bar)"),
               _line("the q and qd limits: the red frame") if stated else _line("no limit stated: the data span",
                                                                               color=MUTED)]
    if _planner(payload, joint, "q") or _planner(payload, joint, "qd"):
        handles.append(_line("planner limit", style="--", width=1.2))
    _header(fig, f"Where in position × speed has {joint} been?",
            _data_line(payload) + f" · colour: {scaled.note}", handles)
    return fig


def _slabs(payload, joint, cmap, reverse, scale):
    slabs = payload["slabs"][joint]
    scale_value, unit = joint_display(payload, joint)
    bands, nx, ny = slabs["shape"]
    plane = payload["planes"][joint]["q_qd"]
    x_edges, y_edges = edges(plane["x_edges"]) * scale_value, edges(plane["y_edges"]) * scale_value
    by_edges = edges(slabs["by_edges"]) * scale_value
    samples = np.asarray(slabs["samples"], float).reshape(bands, nx, ny)
    # WHY one scale over every slab: a colour must mean the same count in each panel, or the bands can't be compared.
    scaled = scale_counts(samples, scale, enough=_enough(payload))
    colormap = _colormap(cmap, reverse)
    fig = _new_figure(3.0 * bands + 1.2, 4.3)
    axes = fig.subplots(1, bands, sharey=True, squeeze=False)[0]
    limits = payload["limits"][joint]
    mesh = None
    for band, ax in enumerate(axes):
        mesh = _heat(ax, x_edges, y_edges, scaled.t[band], colormap)
        _limit_frame(ax, limits["q"].get("source") == "limit" and limits["qd"].get("source") == "limit")
        ax.set_xlim(x_edges[0], x_edges[-1])
        ax.set_ylim(y_edges[0], y_edges[-1])
        ax.xaxis.set_major_locator(_locator(4))
        visited = slabs["visited_pct"][band]
        band_text = (f"{by_edges[band]:+.0f} … {by_edges[band + 1]:+.0f} {signal_unit(unit, 'qdd')}"
                     .replace("-", "−"))
        ax.set_title(f"qdd {band_text}\n{visited:.0f} % of cells visited", fontsize=8.5)
        ax.set_xlabel(f"q ({unit})")
    axes[0].set_ylabel(f"qd ({signal_unit(unit, 'qd')})")
    _colorbar(fig, mesh, list(axes), scaled, "samples per cell")
    handles = [_patch("white", "never visited"), _ramp_patch(cmap, reverse, "visited: colour = samples (bar)"),
               _line("the q / qd limit (the frame)")]
    _header(fig, f"At each acceleration band, where in position × speed has {joint} been?",
            _data_line(payload) + f" · qdd bands in {signal_unit(unit, 'qdd')}, the limit cut in 5 equal slabs · "
            f"one colour scale for every panel: {scaled.note}", handles)
    return fig


def _parallel(payload, cmap, reverse, scale, signal="q"):
    block = payload["parallel"][signal]
    axes_names = list(block["axes"])
    width, height = int(block["width"]), int(block["height"])
    gaps = [np.asarray(gap, float).reshape(width, height) for gap in block["gaps"]]
    scaled = scale_counts(np.stack(gaps) if gaps else np.zeros((0, width, height)), scale, enough=_enough(payload))
    colormap = _colormap(cmap, reverse)
    fig = _new_figure(max(8.5, 1.55 * len(axes_names) + 1.6), 5.2)
    ax = fig.subplots()
    mesh = None
    for index in range(len(gaps)):
        mesh = _heat(ax, np.linspace(index, index + 1, width + 1), np.linspace(0.0, 1.0, height + 1),
                     scaled.t[index], colormap)
    for index, joint in enumerate(axes_names):
        scale_value, unit = joint_display(payload, joint)
        limit = payload["limits"][joint][signal]
        stated = limit.get("source") == "limit"
        ax.plot([index, index], [0, 1], color=INK, linewidth=0.8, zorder=4)
        for end, value in ((0.0, limit["low"]), (1.0, limit["high"])):
            ax.plot([index - 0.06, index + 0.06], [end, end], color=LIMIT_COLOR if stated else MUTED, linewidth=1.8,
                    zorder=5, solid_capstyle="butt")
            ax.text(index + 0.08, end, _value_text(float(value) * scale_value, signal_unit(unit, signal))
                    + ("" if stated else " (data)"), ha="left", va="center", fontsize=7.5,
                    color=LIMIT_COLOR if stated else MUTED, zorder=6,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.8})
    ax.set_xlim(-0.12, len(axes_names) - 1 + 0.6)
    ax.set_ylim(-0.03, 1.03)
    ax.set_yticks([0, 0.5, 1], ["low limit", "middle", "high limit"])
    ax.set_xticks(range(len(axes_names)), axes_names, fontsize=8.5)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(length=0)
    if mesh is not None:
        _colorbar(fig, mesh, ax, scaled, "lines through the pixel")
    subsampled = block.get("subsampled")
    handles = [_patch("white", "no sample passed"), _ramp_patch(cmap, reverse, "line density (bar)"),
               _line("each joint's limit (red ticks, value beside)", width=1.8),
               _line("joint axis: low limit at the bottom, high at the top", color=INK, width=0.8)]
    _header(fig, "Which joint combinations does the data hold, and which joints stay in a narrow band?",
            _data_line(payload) + f" · every sample is one polyline through all {len(axes_names)} {signal} axes"
            + (f" (drawn from {_count(subsampled)} samples)" if subsampled else "") + f" · colour: {scaled.note}",
            handles, columns=2)
    return fig


def _growth(payload, cmap, reverse, scale):
    growth = payload["growth"]
    recorded = np.asarray(growth["visited_pct"], float)
    count = np.arange(1, len(recorded) + 1)
    shuffled = growth.get("shuffled") or {}
    fig = _new_figure(8.5, 4.6)
    ax = fig.subplots()
    accent = _rgb_hex(ramp_rgb(0.25, "viridis"))
    handles = []
    if shuffled.get("mean"):
        ax.fill_between(count, shuffled["p10"], shuffled["p90"], color=MUTED, alpha=0.18, linewidth=0, step=None)
        ax.plot(count, shuffled["mean"], color=MUTED, linewidth=1.4, linestyle=(0, (5, 3)))
        handles += [_patch(MUTED + "40", "random orders: 10–90 % band (32 shuffles)"),
                    _line("random orders: mean", color=MUTED, style="--")]
    ax.plot(count, recorded, color=accent, linewidth=2.2, marker="o" if len(count) <= 30 else None, markersize=3)
    handles.insert(0, _line("in the dataset's order", color=accent, width=2.2))
    if len(recorded):
        ax.annotate(f"{recorded[-1]:.1f} %", (count[-1], recorded[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=accent, fontweight="bold")
    ax.set_xlim(0.5, max(len(recorded), 1) + 0.5 + 0.08 * max(len(recorded), 1))
    ax.set_ylim(0, max(float(recorded.max()) if len(recorded) else 1.0, 1.0) * 1.15)
    ax.set_xlabel("trajectories added")
    ax.set_ylabel("q × qd cells visited (%), mean over joints")
    ax.xaxis.set_major_locator(_locator(8))
    ax.grid(axis="y", color=HAIR, linewidth=0.5)
    new_cells = [int(entry.get("new_cells", 0)) for entry in payload.get("trajectories", [])]
    tail = sum(1 for value in new_cells[len(new_cells) // 2:] if value > 0) if new_cells else 0
    ax.set_title(f"{tail} of the last {len(new_cells) - len(new_cells) // 2} trajectories still opened a new cell"
                 if new_cells else "", fontsize=9, color=MUTED)
    _header(fig, "Is each new trajectory still adding coverage, or has it flattened out?",
            _data_line(payload) + " · a curve still climbing at the right means more data would still help",
            handles, columns=3)
    return fig


def _tool_grid(projection: Mapping[str, Any], pixel_m: float) -> tuple[np.ndarray, np.ndarray, int, int]:
    nu, nv = projection["shape"]
    u0, v0 = projection["origin"]
    u_edges_mm = (u0 + np.arange(nu + 1) * pixel_m) * 1000.0
    v_edges_mm = (v0 + np.arange(nv + 1) * pixel_m) * 1000.0
    return np.asarray(u_edges_mm), np.asarray(v_edges_mm), int(nu), int(nv)


def _projections(payload, cmap, reverse, scale):
    tool = payload["tool"]
    frame, origin = tool_frame(payload)
    pixel_m = float(tool["pixel_m"])
    trajectories = int(payload["source"]["trajectories"])
    # WHY trajectories per pixel for a dataset (Strava's heatmap): a pixel one slow path sat in for a minute must not
    # out-shout a pixel forty paths crossed; with one trajectory the samples (dwell) are the only signal left.
    value_key = "paths" if trajectories > 1 else "samples"
    words = "trajectories through the pixel" if value_key == "paths" else "samples in the pixel"
    views = [("xy", "top view", "x", "y"), ("xz", "front view", "x", "z"), ("yz", "side view", "y", "z")]
    grids = {key: np.asarray(tool["projections"][key][value_key], float).reshape(tool["projections"][key]["shape"])
             for key, *_ in views}
    pooled = scale_counts(np.concatenate([grid.ravel() for grid in grids.values()]), scale, enough=_enough(payload))
    colormap = _colormap(cmap, reverse)
    fig = _new_figure(15.0, 5.6)
    axes = fig.subplots(1, 3)
    offset = 0
    any_reachable = False
    mesh = None
    for ax, (key, title, x_name, y_name) in zip(axes, views, strict=False):
        projection = tool["projections"][key]
        u_edges, v_edges, nu, nv = _tool_grid(projection, pixel_m)
        t = pooled.t[offset:offset + nu * nv].reshape(nu, nv)
        offset += nu * nv
        reachable = projection.get("reachable")
        outside = None
        if reachable is not None:
            any_reachable = True
            outside = (np.asarray(reachable).reshape(nu, nv) == 0) & (t < 0)
        mesh = _heat(ax, u_edges, v_edges, t, colormap, outside)
        ax.set_aspect("equal")
        ax.set_xlim(u_edges[0], u_edges[-1])
        ax.set_ylim(v_edges[0], v_edges[-1])
        ax.xaxis.set_major_locator(_locator(5))
        ax.set_xlabel(f"{x_name} (mm)")
        ax.set_ylabel(f"{y_name} (mm)")
        ax.spines[["top", "right"]].set_visible(True)
        visited = int((t >= 0).sum())
        ax.set_title(f"{title} ({x_name}, {y_name}): {visited} pixels", fontsize=9)
        if u_edges[0] <= 0 <= u_edges[-1] and v_edges[0] <= 0 <= v_edges[-1]:
            ax.plot([0], [0], marker="+", color=INK, markersize=9, markeredgewidth=1.4, zorder=6)
            ax.annotate(origin, (0, 0), xytext=(4, 4), textcoords="offset points", fontsize=7.5, color=INK,
                        bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8, "alpha": 0.85})
    _colorbar(fig, mesh, list(axes), pooled, words)
    handles = [_patch("white", "tool never there" + (" (but reachable)" if any_reachable else "")),
               _ramp_patch(cmap, reverse, f"colour = {words} (bar)")]
    if any_reachable:
        handles.append(_patch(_rgb_hex(OUTSIDE_RGB), "out of reach"))
    handles.append(_line(f"+ {origin} (0, 0)", color=INK, width=0.0))
    _header(fig, "Where in the workspace does the tool go?",
            _data_line(payload) + f" · {pixel_m * 1000:.0f} mm pixels in the \"{frame}\" frame · "
            f"one colour scale over all three views: {pooled.note}", handles)
    return fig


def _tool_speed(payload, cmap, reverse, scale):
    tool = payload["tool"]
    _frame, origin = tool_frame(payload)
    projection = tool["projections"]["xy"]
    u_edges, v_edges, nu, nv = _tool_grid(projection, float(tool["pixel_m"]))
    speed = np.asarray([np.nan if value is None else value for value in projection["max_speed"]], float).reshape(nu, nv)
    visited = np.isfinite(speed)
    # WHY its own linear 0..p98 rule (not scale_counts): a speed of 0 is a visit, not an empty pixel.
    top = float(np.quantile(speed[visited], 0.98)) if visited.any() else 0.0
    top = top if top > 0 else (float(speed[visited].max()) if visited.any() else 1.0) or 1.0
    t = np.where(visited, np.clip(np.nan_to_num(speed) / top, 0.0, 1.0), -1.0)
    highest = float(speed[visited].max()) if visited.any() else 0.0
    note = (f"clipped at p98: {top:.2f} m/s (fastest pixel {highest:.2f} m/s)" if highest > top
            else f"top {top:.2f} m/s")
    scaled = Scaled(t, tuple((q, f"{q * top:.2f}") for q in (0.0, 0.25, 0.5, 0.75, 1.0)), note, top, "linear")
    fig = _new_figure(8.0, 6.4)
    ax = fig.subplots()
    reachable = projection.get("reachable")
    outside = (np.asarray(reachable).reshape(nu, nv) == 0) & ~visited if reachable is not None else None
    mesh = _heat(ax, u_edges, v_edges, t, _colormap(cmap, reverse), outside)
    ax.set_aspect("equal")
    ax.set_xlim(u_edges[0], u_edges[-1])
    ax.set_ylim(v_edges[0], v_edges[-1])
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.spines[["top", "right"]].set_visible(True)
    if u_edges[0] <= 0 <= u_edges[-1] and v_edges[0] <= 0 <= v_edges[-1]:
        ax.plot([0], [0], marker="+", color=INK, markersize=9, markeredgewidth=1.4, zorder=6)
        ax.annotate(origin, (0, 0), xytext=(4, 4), textcoords="offset points", fontsize=7.5, color=INK,
                        bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8, "alpha": 0.85})
    speed_numbers = {entry["key"]: entry for entry in payload.get("numbers", [])}
    p99 = speed_numbers.get("tool_speed_p99_m_s")
    ax.set_title(f"{int(visited.sum())} pixels visited" + (f" · tool speed p99 {p99['value']:.2f} m/s" if p99 else ""),
                 fontsize=9, color=MUTED)
    bar = fig.colorbar(mesh, ax=ax, fraction=0.05, pad=0.02, aspect=28)
    bar.outline.set_visible(False)
    bar.set_ticks([q for q, _ in scaled.ticks], labels=[text for _, text in scaled.ticks])
    bar.ax.tick_params(labelsize=8, colors=MUTED, length=2)
    bar.set_label("fastest tool speed seen in the pixel (m/s)\nlinear (clipped at p98)", fontsize=8.5)
    handles = [_patch("white", "tool never there"), _ramp_patch(cmap, reverse, "colour = fastest speed (bar)"),
               _line(f"+ {origin} (0, 0)", color=INK, width=0.0)]
    if outside is not None:
        handles.insert(2, _patch(_rgb_hex(OUTSIDE_RGB), "out of reach"))
    _header(fig, "How fast does the tool move over each spot? (top view)",
            _data_line(payload) + f" · {float(tool['pixel_m']) * 1000:.0f} mm pixels · colour: {note}", handles)
    return fig


def _tilt_map(payload, cmap, reverse, scale):
    orientation = payload["tool"]["orientation"]
    block = orientation["tilt_azimuth"]
    tilt_edges = np.degrees(edges(block["tilt_edges"]))
    azimuth_edges = edges(block["azimuth_edges"])
    tilts, azimuths = block["shape"]
    counts = np.asarray(block["counts"], float).reshape(tilts, azimuths)
    scaled = scale_counts(counts, scale, enough=_enough(payload))
    fig = _new_figure(7.6, 7.0)
    ax = fig.add_subplot(projection="polar")
    shown = np.ma.masked_where(scaled.t < 0, scaled.t)
    mesh = ax.pcolormesh(azimuth_edges, tilt_edges, shown, cmap=_colormap(cmap, reverse), vmin=0, vmax=1,
                         shading="flat", rasterized=True)
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_ylim(0, tilt_edges[-1])
    ax.set_axisbelow(False)  # the tilt rings and azimuth spokes stay readable on top of the cells
    ax.grid(color="white", linewidth=0.9, alpha=0.9)
    ax.set_yticks([30, 60, 90, 120, 150])
    ax.set_yticklabels(["30°", "60°", "90°", "120°", "150°"], fontsize=7.5, color=INK,
                       bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8, "alpha": 0.85})
    ax.set_rlabel_position(100)
    ax.set_xticks(np.radians([0, 90, 180, 270]), ["+x", "+y", "−x", "−y"], fontsize=9, color=INK)
    tilt_max = {entry["key"]: entry for entry in payload.get("numbers", [])}.get("tool_tilt_max_deg")
    if tilt_max:
        ring = np.linspace(-np.pi, np.pi, 181)
        at = np.full_like(ring, float(tilt_max["value"]))
        ax.plot(ring, at, color="white", linewidth=2.6, zorder=4)  # a white casing: it reads on dark cells too
        ax.plot(ring, at, color=INK, linewidth=1.1, linestyle=(0, (2, 2)), zorder=4.5)
    _colorbar(fig, mesh, ax, scaled, "samples per cell", shrink=0.8)
    reference = _reference_words(orientation.get("reference", (0, 0, -1)))
    handles = [_patch("white", "direction never held"), _ramp_patch(cmap, reverse, "colour = samples (bar)")]
    if tilt_max:
        handles.append(_line(f"largest tilt reached ({float(tilt_max['value']):.0f}°)", color=INK, style=":",
                             width=0.9))
    _header(fig, "Which way does the tool point?",
            _data_line(payload) + f" · centre = tool {reference} (tilt 0°); distance from centre = tilt; "
            f"angle = the way it leans in the \"{tool_frame(payload)[0]}\" XY plane", handles, columns=3)
    return fig


def _tilt_yaw(payload, cmap, reverse, scale):
    block = payload["tool"]["orientation"]["tilt_yaw"]
    tilt_edges = np.degrees(edges(block["tilt_edges"]))
    yaw_edges = np.degrees(edges(block["yaw_edges"]))
    tilts, yaws = block["shape"]
    counts = np.asarray(block["counts"], float).reshape(tilts, yaws)
    scaled = scale_counts(counts.T, scale, enough=_enough(payload))  # (yaw, tilt) = (x, y)
    fig = _new_figure(9.0, 5.4)
    ax = fig.subplots()
    mesh = _heat(ax, yaw_edges, tilt_edges, scaled.t, _colormap(cmap, reverse))
    ax.set_xlim(yaw_edges[0], yaw_edges[-1])
    ax.set_ylim(tilt_edges[-1], tilt_edges[0])  # tilt 0 (along the reference) at the top
    ax.set_xticks(np.arange(-180, 181, 45))
    ax.set_yticks(np.arange(0, 181, 30))
    ax.xaxis.set_major_formatter(lambda value, _pos: f"{value:+.0f}°")
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}°")
    ax.set_xlabel(f"yaw: heading of the tool x axis (the jaw) in \"{tool_frame(payload)[0]}\" XY, 0° = +x")
    reference = _reference_words(payload["tool"]["orientation"].get("reference", (0, 0, -1)))
    ax.set_ylabel(f"tilt from {reference}")
    ax.spines[["top", "right"]].set_visible(True)
    visited = int((scaled.t >= 0).sum())
    ax.set_title(f"{visited} of {tilts * yaws} cells visited ({100 * visited / max(tilts * yaws, 1):.0f} %)",
                 fontsize=9, color=MUTED)
    _colorbar(fig, mesh, ax, scaled, "samples per cell")
    _header(fig, "Which tilts and jaw headings does the tool hold?",
            _data_line(payload) + f" · {tilt_edges[1] - tilt_edges[0]:.0f}° tilt × {yaw_edges[1] - yaw_edges[0]:.0f}° "
            f"yaw cells · colour: {scaled.note}",
            [_patch("white", "never held"), _ramp_patch(cmap, reverse, "colour = samples (bar)")])
    return fig


def _per_joint(figure_id: str, payload: Mapping[str, Any]) -> tuple[str, str] | None:
    for prefix in ("heat-q-qd-", "slabs-"):
        if figure_id.startswith(prefix):
            wanted = figure_id[len(prefix):]
            for name in joint_names(payload):
                if slug(name) == wanted or name == wanted:
                    return prefix, name
            raise KeyError(f"{figure_id!r}: no joint {wanted!r} (joints: {', '.join(joint_names(payload))})")
    return None


FIGURES = {"ridgeline": _ridgeline, "limit-bars": _limit_bars, "parallel-q": _parallel, "growth": _growth,
           "projections": _projections, "tool-speed": _tool_speed, "tilt-map": _tilt_map, "tilt-yaw": _tilt_yaw}


def figure(payload: Mapping[str, Any], figure_id: str, *, cmap: str = "viridis", reverse: bool = False,
           scale: str = "linear"):
    """One figure as a matplotlib `Figure` (not registered with pyplot). `figure_id` is a PNG stem from
    `figure_ids(payload)`: "limit-bars", "heat-q-qd-<joint>", "slabs-<joint>", "tilt-map", ..."""
    import matplotlib

    check_colour_choice(cmap, scale)
    if payload.get("schema") != "traj_compare.coverage/1":
        raise ValueError(f"not a coverage payload: schema {payload.get('schema')!r}")
    with matplotlib.rc_context(STYLE):
        joint = _per_joint(figure_id, payload)
        if joint is not None:
            prefix, name = joint
            draw = _heat_q_qd if prefix == "heat-q-qd-" else _slabs
            return draw(payload, name, cmap, reverse, scale)
        if figure_id not in FIGURES:
            raise KeyError(f"unknown figure {figure_id!r}; this payload has {', '.join(figure_ids(payload))}")
        if figure_id in ("projections", "tool-speed", "tilt-map", "tilt-yaw") and not payload.get("tool"):
            raise KeyError(f"{figure_id!r} needs the tool (TCP) poses; this payload has none")
        return FIGURES[figure_id](payload, cmap, reverse, scale)


def plot_coverage(payload: Mapping[str, Any], out_dir: str | Path, *, cmap: str = "viridis", reverse: bool = False,
                  scale: str = "linear") -> list[Path]:
    """Write one PNG per 2-D figure into `out_dir` (created) and return their paths, in `figure_ids` order."""
    import matplotlib

    check_colour_choice(cmap, scale)
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
