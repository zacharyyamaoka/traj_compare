"""Grasp coverage: of everything the gripper CAN do (jaw range, approach directions, rolls, the offered area), how much do
these grasps use, and where did the failures sit?

robot_msgs GraspPose in (+ an outcome per grasp + the jaw range), one payload dict "traj_compare.grasp_coverage/1" out.
Every viewer (the data-ui workbench, Matplotlib, Viser, W&B) reads only that payload. The contract, every field and
its meaning: docs/GRASP_COVERAGE.md. numpy + robot_msgs only; SI inside, degrees and mm only in viewers.

WHY it bins with coverage/bins.py: a grasp set is the trajectory viewer's tool section without time (Zach's grasp ask,
Daily Note 2026-11-23), so the position grids, the equal-area sphere and the tilt disk are the trajectory payload's own.
Prior art (ideas, reimplemented): robot_metrics/docs/proposals/coverage-2026-11-19/figures_grasp.py (repick_positions,
width_limits, roll_rose, sphere_comparison, object_imbalance).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs.geometry.rotations import quat_to_matrix
from robot_msgs.manipulation import GraspPose

from ..coverage import bins

SCHEMA = "traj_compare.grasp_coverage/1"
KNOWN_OUTCOMES = ("picked", "failed", "hovered", "refused")
UNKNOWN = "unknown"
CLOSED = ("picked", "failed")
WORDS = {
    "picked": "closed on it and it came away (a success)",
    "failed": "closed on it, then missed or lost it",
    "hovered": "went to the grasp but never closed (hover only)",
    "refused": "planned, but the arm never went (a gate refused)",
    UNKNOWN: "no outcome given (a dataset label or a detector's proposal)",
}
NO_OBJECT = "(no object)"
DATA_PERCENTILES = (0.1, 99.9)
DATA_WIDEN = 1.15  # with no stated jaw range the box is the data's p0.1..p99.9, widened this much
HIST_MARGIN = 0.08  # the width histogram runs this share of the range past each end, so a grasp past the stop shows
WIDTH_BINS = 72
WIDTH_TILT_BINS = (36, 18)
TILT_GRID_BINS, AZIMUTH_BINS, TILT_BINS = 18, 36, 36
ROLL_BINS, ROLL_FOLDED_BINS = 72, 36
SCORE_BINS = 40
GRASPS_MAX = 20_000  # per-grasp rows kept in the payload (evenly picked past it); every count still uses all
PROJECTIONS = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}
ARROW_M = 0.05  # the workbench / Viser arrow: this far back along the approach
GLYPH_DEPTH_M, GLYPH_STEM_M = 0.04, 0.05  # robot_msgs viz/viser.py _gripper: finger length, the stem behind the palm
GROWTH_POINTS = 400  # coverage growth keeps at most this many points (evenly picked, both ends kept)


# ── the result ──────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, eq=False)
class GraspCoverage:
    """The payload every viewer reads, its headline numbers by key, and one call per viewer."""

    payload: dict
    numbers: dict[str, float]

    def write_workbench(self, out_dir, **options) -> Path:
        """Our page: data-ui's <data-workbench> over these grasps (`write_grasp_workbench`)."""
        from .workbench import write_grasp_workbench

        return write_grasp_workbench(self, None, out_dir, **options)

    def plot(self, out_dir, **options) -> list[Path]:
        from .matplotlib_view import plot_grasp_coverage

        return plot_grasp_coverage(self.payload, out_dir, **options)

    def serve_viser(self, **options):
        from .viser_view import serve_grasp_coverage

        return serve_grasp_coverage(self.payload, **options)

    def log_wandb(self, run, **options) -> dict:
        from .wandb_log import log_grasp_coverage

        return log_grasp_coverage(run, self.payload, **options)


@dataclass(frozen=True, eq=False)
class GraspValues:
    """Every grasp's numbers, (N,) or (N, 3): what the payload bins. `roll` in (-pi, pi]."""

    names: list[str]
    objects: list[str]
    positions: np.ndarray
    approach: np.ndarray
    jaw: np.ndarray
    width: np.ndarray
    pre_grasp_width: np.ndarray  # NaN = none
    score: np.ndarray  # NaN = none
    tilt: np.ndarray
    azimuth: np.ndarray
    roll: np.ndarray
    frame: str

    def __len__(self) -> int:
        return len(self.names)


# ── analyze ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def analyze_grasps(
    grasps,
    *,
    outcomes=None,
    width_range: Sequence[float] | None = None,
    planner_width_range: Sequence[float] | None = None,
    symmetric_jaws: bool = True,
    tags: Mapping[str, Mapping[str, Any]] | None = None,
    group_by: str = "outcome",
    area=None,
    reference: Sequence[float] = (0.0, 0.0, -1.0),
    pixel_m: float = 0.01,
    enough: int = 10,
    title: str = "",
    subtitle: str = "",
) -> GraspCoverage:
    """One payload "traj_compare.grasp_coverage/1" for `grasps` (docs/GRASP_COVERAGE.md has every argument)."""
    named = _named(grasps)
    values = grasp_values(named, reference)
    names = values.names
    outcome_of = _outcomes(outcomes, names)
    has_outcomes = outcomes is not None
    tags_of = [_plain_tags((tags or {}).get(name, {})) for name in names]
    order = _outcome_order(outcome_of)
    objects = _object_order(values.objects)
    group_of, groups = _groups(group_by, outcome_of, order, values.objects, objects, tags_of)
    gripper = _gripper(width_range, planner_width_range, values.width)
    boxes = _boxes(area)
    reference = np.asarray(reference, float) / np.linalg.norm(np.asarray(reference, float))

    position = _position(values, boxes, pixel_m, group_of, groups, outcome_of if has_outcomes else None)
    width, width_edges = _width(values.width, gripper, group_of, groups)
    pre = values.pre_grasp_width
    pre_grasp = (None if not np.isfinite(pre).any() else
                 _hist_block(pre[np.isfinite(pre)], width_edges, group_of[np.isfinite(pre)], groups))
    roll_folded = np.mod(values.roll, math.pi)
    shown_key = "roll_folded" if symmetric_jaws else "roll"
    shown_edges = (0.0, math.pi, ROLL_FOLDED_BINS) if symmetric_jaws else (-math.pi, math.pi, ROLL_BINS)
    shown_roll = roll_folded if symmetric_jaws else values.roll
    orientation = {
        "reference": [float(v) for v in reference],
        "sphere": {"rings": bins.SPHERE_RINGS, "sectors": bins.SPHERE_SECTORS,
                   **_grouped_cells(bins.sphere_cell(values.approach), bins.SPHERE_RINGS * bins.SPHERE_SECTORS,
                                    group_of, groups)},
        "tilt_azimuth": bins.grid_2d(values.tilt, (0.0, math.pi, TILT_GRID_BINS), values.azimuth,
                                     (-math.pi, math.pi, AZIMUTH_BINS), "tilt_edges", "azimuth_edges"),
        "tilt": _hist_block(values.tilt, (0.0, math.pi, TILT_BINS), group_of, groups, stats=False),
        "roll": _hist_block(values.roll, (-math.pi, math.pi, ROLL_BINS), group_of, groups, stats=False),
        "roll_folded": _hist_block(roll_folded, (0.0, math.pi, ROLL_FOLDED_BINS), group_of, groups, stats=False),
        "roll_shown": shown_key,
        "tilt_roll": bins.grid_2d(values.tilt, (0.0, math.pi, TILT_GRID_BINS), shown_roll, shown_edges,
                                  "tilt_edges", "roll_edges"),
    }
    width_tilt = bins.grid_2d(values.width, (width_edges[0], width_edges[1], WIDTH_TILT_BINS[0]), values.tilt,
                              (0.0, math.pi, WIDTH_TILT_BINS[1]), "x_edges", "y_edges")
    score = _score(values.score, group_of, groups)
    rows, subsampled = _grasp_rows(values, outcome_of, group_of, groups, tags_of)

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "title": str(title),
        "subtitle": str(subtitle),
        "back": [],
        "siblings": [],
        "enough": int(enough),
        "source": {"grasps": len(values), "frame": values.frame, "objects": objects, "group_by": group_by,
                   "groups": groups, "with_pre_grasp": int(np.isfinite(pre).sum()),
                   "with_score": int(np.isfinite(values.score).sum()),
                   "jaws": "symmetric" if symmetric_jaws else "asymmetric"},
        "outcomes": {"order": order, "counts": {name: outcome_of.count(name) for name in order},
                     "closed": list(CLOSED), "words": {name: WORDS.get(name, f"outcome '{name}'") for name in order}},
        "gripper": gripper,
        "grasps": rows,
        "grasps_subsampled": subsampled,
        "position": position,
        "width": width,
        "pre_grasp_width": pre_grasp,
        "width_tilt": width_tilt,
        "orientation": orientation,
        "score": score,
        "objects": _object_rows(values, objects, outcome_of, order, gripper, shown_roll, shown_edges, position),
        "growth": _growth(values, position, width_edges, shown_roll, shown_edges),
    }
    payload["numbers"] = _headline_numbers(payload, values, outcome_of, has_outcomes, gripper, boxes)
    return GraspCoverage(payload=payload, numbers={row["key"]: row["value"] for row in payload["numbers"]})


# ── the inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _named(grasps) -> list[tuple[str, GraspPose]]:
    if isinstance(grasps, GraspPose):
        grasps = [grasps]
    if isinstance(grasps, Mapping):
        items = [(str(name), grasp) for name, grasp in grasps.items()]
    else:
        items = []
        for i, grasp in enumerate(grasps):
            meta = getattr(getattr(grasp, "header", None), "meta", None) or {}
            items.append((str(meta.get("name") or f"grasp_{i}"), grasp))
    if not items:
        raise ValueError("no grasps: analyze_grasps needs at least one robot_msgs GraspPose")
    for name, grasp in items:
        if not isinstance(grasp, GraspPose):
            raise TypeError(f"grasp {name!r} is a {type(grasp).__name__}, not a robot_msgs GraspPose")
    first = items[0][1].header.frame_id
    for name, grasp in items:
        if grasp.header.frame_id != first:
            raise ValueError(f"grasp {name!r} is in frame {grasp.header.frame_id!r}, the first in {first!r}: all grasps "
                             "must share one frame (positions in two frames do not add up)")
    return items


def grasp_values(named: Sequence[tuple[str, GraspPose]], reference: Sequence[float] = (0.0, 0.0, -1.0)) -> GraspValues:
    """Every grasp's position, approach (tool +z), jaw axis (tool x), widths, score and angles (docs "The angles")."""
    positions = np.array([[g.pose.position.x, g.pose.position.y, g.pose.position.z] for _, g in named], float)
    quats = np.array([[g.pose.orientation.x, g.pose.orientation.y, g.pose.orientation.z, g.pose.orientation.w]
                      for _, g in named], float)
    rotations = quat_to_matrix(quats).reshape(-1, 3, 3)
    approach, jaw = rotations[:, :, 2], rotations[:, :, 0]
    tilt, azimuth, _ = bins.direction_angles(rotations, reference)
    return GraspValues(
        names=[name for name, _ in named],
        objects=[g.object_id or NO_OBJECT for _, g in named],
        positions=positions, approach=approach, jaw=jaw,
        width=np.array([g.width for _, g in named], float),
        pre_grasp_width=np.array([np.nan if g.pre_grasp_width is None else g.pre_grasp_width for _, g in named], float),
        score=np.array([np.nan if g.score is None else g.score for _, g in named], float),
        tilt=tilt, azimuth=azimuth, roll=roll_angles(approach, jaw, reference),
        frame=named[0][1].header.frame_id or "base",
    )


def roll_angles(approach: np.ndarray, jaw: np.ndarray, reference: Sequence[float] = (0.0, 0.0, -1.0)) -> np.ndarray:
    """The jaw axis's angle about the approach, counter-clockwise seen from behind the gripper, in (-pi, pi].

    Zero is the reference grasp's jaw axis (the frame's +x made perpendicular to `reference`; +y if `reference` lies
    along x) carried by the shortest swing from `reference` to the approach (Rodrigues). WHY the swing: a roll must
    not depend on how far the approach tilts; WHY seen from behind: for a straight-down grasp it is then the jaw's
    heading in the frame's XY, the trajectory viewer's yaw (docs/GRASP_COVERAGE.md "The angles")."""
    r = np.asarray(reference, float)
    r = r / np.linalg.norm(r)
    x0 = np.array([1.0, 0.0, 0.0]) - r[0] * r
    if np.linalg.norm(x0) < 1e-9:
        x0 = np.array([0.0, 1.0, 0.0]) - r[1] * r
    x0 = x0 / np.linalg.norm(x0)
    a = np.asarray(approach, float).reshape(-1, 3)
    axis = np.cross(r, a)
    s = np.linalg.norm(axis, axis=1)
    c = a @ r
    turning = s > 1e-12
    k = np.where(turning[:, None], axis / np.where(turning, s, 1.0)[:, None], 0.0)
    swung = x0 * c[:, None] + np.cross(k, x0) * s[:, None] + k * (k @ x0)[:, None] * (1.0 - c)[:, None]
    # WHY x0 when not turning: straight along the reference needs no swing; straight against it is a half turn about
    # x0 (any axis across the reference does it), which leaves x0 where it is
    zero = np.where(turning[:, None], swung, x0)
    behind = -a
    roll = np.arctan2(np.einsum("ij,ij->i", np.cross(zero, jaw), behind), np.einsum("ij,ij->i", zero, jaw))
    return np.where(roll <= -math.pi, math.pi, roll)


def _outcomes(outcomes, names: list[str]) -> list[str]:
    if outcomes is None:
        given = [None] * len(names)
    elif isinstance(outcomes, Mapping):
        missing = [name for name in names if name not in outcomes]
        if missing:
            raise ValueError(f"outcomes is missing {len(missing)} grasp(s), the first {missing[0]!r}")
        given = [outcomes[name] for name in names]
    else:
        given = list(outcomes)
        if len(given) != len(names):
            raise ValueError(f"outcomes: {len(given)} given for {len(names)} grasps (one per grasp, same order)")
    return [UNKNOWN if value is None or not str(value).strip() else str(value).strip() for value in given]


def _outcome_order(outcome_of: list[str]) -> list[str]:
    present = dict.fromkeys(outcome_of)
    other = [name for name in present if name not in KNOWN_OUTCOMES and name != UNKNOWN]
    return [name for name in KNOWN_OUTCOMES if name in present] + other + ([UNKNOWN] if UNKNOWN in present else [])


def _object_order(objects: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for name in objects:
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts, key=lambda name: -counts[name])  # stable: ties keep first-seen order


def _plain_tags(tags: Mapping[str, Any]) -> dict:
    plain = {}
    for key, value in tags.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            plain[str(key)] = str(value)
        else:
            plain[str(key)] = float(value) if math.isfinite(float(value)) else None
    return plain


def _groups(group_by: str, outcome_of, order, objects, object_order, tags_of) -> tuple[np.ndarray, list[str]]:
    if group_by == "outcome":
        labels, names = outcome_of, order
    elif group_by == "object":
        labels, names = objects, object_order
    elif any(group_by in tags for tags in tags_of):
        labels = [str(tags.get(group_by, "(none)")) for tags in tags_of]
        names = list(dict.fromkeys(labels))
    else:
        raise ValueError(f"group_by={group_by!r}: expected 'outcome', 'object' or a tag every grasp may carry")
    index = {name: i for i, name in enumerate(names)}
    return np.array([index[label] for label in labels], np.int64), list(names)


def _gripper(width_range, planner_range, widths: np.ndarray) -> dict:
    if width_range is not None:
        low, high = (float(v) for v in width_range)
        if not (math.isfinite(low) and math.isfinite(high) and high > low):
            raise ValueError(f"width_range={tuple(width_range)!r}: expected (low_m, high_m) with high > low")
        source = "limit"
    else:
        p_low, p_high = np.percentile(widths, DATA_PERCENTILES)
        centre, half = (p_low + p_high) / 2.0, max((p_high - p_low) / 2.0 * DATA_WIDEN, 0.005)
        low, high, source = max(0.0, float(centre - half)), float(centre + half), "data"
    planner = (None, None)
    if planner_range is not None:
        planner = tuple(float(v) for v in planner_range)
        if not planner[1] > planner[0]:
            raise ValueError(f"planner_width_range={tuple(planner_range)!r}: expected (low_m, high_m), high > low")
    return {"low": low, "high": high, "source": source, "planner_low": planner[0], "planner_high": planner[1]}


def _boxes(area) -> list[tuple[np.ndarray, np.ndarray]]:
    if area is None:
        return []
    array = np.asarray(area, float)
    if array.shape == (2, 3):
        array = array[None]
    if array.ndim != 3 or array.shape[1:] != (2, 3):
        raise ValueError("area: one box ((x0, y0, z0), (x1, y1, z1)) or a list of them")
    return [(np.minimum(lo, hi), np.maximum(lo, hi)) for lo, hi in array]


# ── binning ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _grouped_cells(cell: np.ndarray, cells: int, group_of: np.ndarray, groups: list[str]) -> dict:
    """{"counts": flat, "groups": {group: flat}} of flat cell indices (-1 = in none)."""
    inside = cell >= 0
    out = {"counts": bins.ints(np.bincount(cell[inside], minlength=cells)), "groups": {}}
    for g, name in enumerate(groups):
        mine = inside & (group_of == g)
        out["groups"][name] = bins.ints(np.bincount(cell[mine], minlength=cells))
    return out


def _hist_block(values: np.ndarray, edges, group_of: np.ndarray, groups: list[str], stats: bool = False) -> dict:
    low, high, count = edges
    index = bins.bin_index(values, low, high, count)
    block = {"edges": bins.edges(low, high, count), **_grouped_cells(index, count, group_of, groups)}
    if stats:
        block["beyond_edges"] = int((index < 0).sum())
    return block


def _width(widths: np.ndarray, gripper: dict, group_of: np.ndarray, groups: list[str]) -> tuple[dict, tuple]:
    low, high = gripper["low"], gripper["high"]
    span = high - low
    edges = (low - HIST_MARGIN * span, high + HIST_MARGIN * span, WIDTH_BINS)
    block = _hist_block(widths, edges, group_of, groups, stats=True)
    p001, p999 = (float(v) for v in np.percentile(widths, DATA_PERCENTILES))
    tolerance = 1e-9 * span
    block.update({
        "p001": p001, "p999": p999, "min": float(widths.min()), "max": float(widths.max()),
        "span_pct": 100.0 * (p999 - p001) / span,
        "peak_pct": 100.0 * p999 / high if high > 0 else 0.0,
        "outside": int(((widths < low - tolerance) | (widths > high + tolerance)).sum())
        if gripper["source"] == "limit" else 0,
    })
    return block, edges


def _score(scores: np.ndarray, group_of: np.ndarray, groups: list[str]) -> dict | None:
    has = np.isfinite(scores)
    if not has.any():
        return None
    low, high = float(scores[has].min()), float(scores[has].max())
    if not high > low:
        low, high = low - 0.5, high + 0.5
    return _hist_block(scores[has], (low, high, SCORE_BINS), group_of[has], groups)


def _position(values: GraspValues, boxes, pixel_m: float, group_of: np.ndarray, groups: list[str],
              outcome_of: list[str] | None = None) -> dict:
    points = values.positions
    every = np.vstack([points] + [np.vstack(box) for box in boxes]) if boxes else points
    every = every[np.isfinite(every).all(axis=1)]
    low, high = every.min(axis=0) - pixel_m, every.max(axis=0) + pixel_m
    projections = {}
    for face, axes in PROJECTIONS.items():
        cell, shape = bins.grid_cells(points, pixel_m, low, high, axes)
        origin = bins.grid_origin(low, pixel_m, axes)
        cells = shape[0] * shape[1]
        block = {"origin": bins.floats(origin, 6), "shape": shape,
                 **{("samples" if key == "counts" else key): value
                    for key, value in _grouped_cells(cell, cells, group_of, groups).items()},
                 "picked": None, "closed": None, "area": None}
        if outcome_of is not None:
            # WHY its own two grids, not the groups: the success map (picked / closed) must not depend on group_by
            picked = np.array([word == "picked" for word in outcome_of]) & (cell >= 0)
            closed = np.array([word in CLOSED for word in outcome_of]) & (cell >= 0)
            block["picked"] = bins.ints(np.bincount(cell[picked], minlength=cells))
            block["closed"] = bins.ints(np.bincount(cell[closed], minlength=cells))
        if boxes:
            centres_u = origin[0] + (np.arange(shape[0]) + 0.5) * pixel_m
            centres_v = origin[1] + (np.arange(shape[1]) + 0.5) * pixel_m
            mask = np.zeros(shape, bool)
            u, v = axes
            for lo, hi in boxes:
                mask |= ((centres_u[:, None] >= lo[u]) & (centres_u[:, None] <= hi[u])
                         & (centres_v[None, :] >= lo[v]) & (centres_v[None, :] <= hi[v]))
            block["area"] = bins.ints(mask.ravel())
        projections[face] = block
    return {"pixel_m": float(pixel_m), "bounds": [bins.floats(low, 6), bins.floats(high, 6)],
            "area": [[bins.floats(lo), bins.floats(hi)] for lo, hi in boxes] or None, "projections": projections}


def _grasp_rows(values: GraspValues, outcome_of, group_of, groups, tags_of) -> tuple[list[dict], int | None]:
    count = len(values)
    picked = np.arange(count) if count <= GRASPS_MAX else np.unique(np.linspace(0, count - 1, GRASPS_MAX).round()
                                                                      .astype(np.int64))
    rows = []
    for k in picked:
        rows.append({
            "name": values.names[k], "object_id": values.objects[k], "outcome": outcome_of[k],
            "group": groups[group_of[k]], "tags": tags_of[k],
            "position": bins.floats(values.positions[k]), "approach": bins.floats(values.approach[k]),
            "jaw": bins.floats(values.jaw[k]), "width": float(values.width[k]),
            "pre_grasp_width": bins.number(values.pre_grasp_width[k]), "score": bins.number(values.score[k]),
            "tilt": float(values.tilt[k]), "azimuth": float(values.azimuth[k]), "roll": float(values.roll[k]),
        })
    return rows, (None if count <= GRASPS_MAX else len(rows))


def _object_rows(values: GraspValues, objects, outcome_of, order, gripper, shown_roll, shown_edges, position) -> list:
    rows = []
    objects_of = np.array(values.objects, dtype=object)
    span = gripper["high"] - gripper["low"]
    xy = position["projections"]["xy"]
    for name in objects:
        mine = objects_of == name
        outcomes = [outcome_of[k] for k in np.flatnonzero(mine)]
        closed = sum(outcomes.count(word) for word in CLOSED)
        widths = values.width[mine]
        p001, p999 = np.percentile(widths, DATA_PERCENTILES)
        directions = np.unique(bins.sphere_cell(values.approach[mine]))
        roll_index = bins.bin_index(shown_roll[mine], *shown_edges)
        pixels = bins.grid_cells_on(values.positions[mine], xy["origin"], xy["shape"], position["pixel_m"],
                                    PROJECTIONS["xy"])
        rows.append({
            "object_id": name, "grasps": int(mine.sum()),
            "outcomes": {word: outcomes.count(word) for word in order if word in outcomes},
            "picked_pct": (100.0 * outcomes.count("picked") / closed) if closed else None,
            "width_span_pct": 100.0 * float(p999 - p001) / span,
            "directions_visited_pct": 100.0 * len(directions) / (bins.SPHERE_RINGS * bins.SPHERE_SECTORS),
            "roll_visited_pct": 100.0 * len(np.unique(roll_index[roll_index >= 0])) / shown_edges[2],
            "pixels_xy": int(len(np.unique(pixels[pixels >= 0]))),
        })
    return rows


def _growth(values: GraspValues, position: dict, width_edges, shown_roll: np.ndarray, shown_edges) -> dict:
    """Distinct xy pixels, approach cells, width bins and roll bins after the first k grasps, in the given order.

    WHY (the trajectory viewer's growth curve, for grasps): a flat curve says the newest grasps add no coverage, so
    more of the same data will not help; a rising one says the set is still filling in."""
    xy = position["projections"]["xy"]
    keys = {
        "position_pixels_xy": bins.grid_cells_on(values.positions, xy["origin"], xy["shape"], position["pixel_m"],
                                                 PROJECTIONS["xy"]),
        "direction_cells": bins.sphere_cell(values.approach),
        "width_bins": bins.bin_index(values.width, *width_edges),
        "roll_bins": bins.bin_index(shown_roll, *shown_edges),
    }
    count = len(values)
    picked = np.unique(np.concatenate([np.linspace(0, count - 1, min(GROWTH_POINTS, count)).round(), [0, count - 1]])
                       .astype(np.int64))
    out: dict[str, Any] = {"order": "as given", "grasps": bins.ints(picked + 1)}
    for key, cell in keys.items():
        first = np.zeros(count, bool)
        inside = np.flatnonzero(cell >= 0)
        _, first_at = np.unique(cell[inside], return_index=True)
        first[inside[first_at]] = True
        out[key] = bins.ints(np.cumsum(first)[picked])
    return out


def time_buckets(rows: Sequence[Mapping[str, Any]], batches: int = 20) -> tuple[list[str], list[str], str]:
    """Each grasp row's bucket on a time axis, the buckets in order, and the axis's name: the `day` tag when every
    grasp has one, else `batches` equal batches in the given order ("1-62", "63-124", ...)."""
    if rows and all(row["tags"].get("day") for row in rows):
        labels = [str(row["tags"]["day"]) for row in rows]
        return labels, sorted(set(labels)), "day"
    batch = max(1, math.ceil(len(rows) / batches))
    labels = [f"{(k // batch) * batch + 1}-{min((k // batch + 1) * batch, len(rows))}" for k in range(len(rows))]
    return labels, list(dict.fromkeys(labels)), "grasps, in the given order"


def gripper_polylines(rows: Sequence[Mapping[str, Any]], size: float = 1.0) -> np.ndarray:
    """robot_msgs' two-finger glyph per grasp row as ONE polyline of 7 points, (N, 7, 3) metres, in the payload frame:
    jaw tip, palm, palm centre, the wrist end of the stem, palm centre, palm, the other jaw tip.

    The jaws sit at ±width/2 along the jaw axis (tool x), the fingers run GLYPH_DEPTH_M back along the approach (tool
    +z) to the palm, and the stem GLYPH_STEM_M further back (robot_msgs viz/viser.py `_gripper`). `size` scales the
    finger and stem lengths, never the jaw gap. WHY one polyline: every viewer draws a grasp as one path (data-ui
    scene3d `lines` by grasp, a Matplotlib LineCollection, Viser's segments), the Nov 19 gallery's "thin grippers"."""
    if not rows:
        return np.zeros((0, 7, 3))
    p = np.array([row["position"] for row in rows], float)
    a = np.array([row["approach"] for row in rows], float)
    j = np.array([row["jaw"] for row in rows], float)
    half = (np.maximum(np.array([row["width"] for row in rows], float), 0.004) / 2.0)[:, None]
    palm = p - GLYPH_DEPTH_M * size * a
    stem = palm - GLYPH_STEM_M * size * a
    return np.stack([p - half * j, palm - half * j, palm, stem, palm, palm + half * j, p + half * j], axis=1)


# ── headline numbers ────────────────────────────────────────────────────────────────────────────────────────────────


def _headline_numbers(payload: dict, values: GraspValues, outcome_of, has_outcomes: bool, gripper: dict,
                      boxes) -> list[dict]:
    """The scalars W&B logs and every viewer's numbers row shows; always finite."""
    width = payload["width"]
    orientation = payload["orientation"]
    object_counts = np.array([row["grasps"] for row in payload["objects"]], float)
    shown = orientation[orientation["roll_shown"]]["counts"]
    xy = payload["position"]["projections"]["xy"]
    rows = [
        ("grasps", "Grasps", len(values), ""),
        ("objects", "Objects", len(payload["objects"]), ""),
        ("width_span_pct", "Jaw range used (p0.1 to p99.9)", width["span_pct"], "%"),
        ("width_peak_pct", "Widest grasp (p99.9), share of the open stop", width["peak_pct"], "%"),
        ("directions_visited_pct", "Approach directions visited (equal-area sphere cells)",
         100.0 * sum(1 for n in orientation["sphere"]["counts"] if n > 0) / len(orientation["sphere"]["counts"]), "%"),
        ("tilt_median_deg", "Tilt from straight down, median", math.degrees(float(np.median(values.tilt))), "deg"),
        ("tilt_max_deg", "Largest tilt from straight down", math.degrees(float(values.tilt.max())), "deg"),
        ("roll_visited_pct", "Rolls about the approach visited (" + ("folded 0-180°" if orientation["roll_shown"]
                                                                     == "roll_folded" else "full circle") + ")",
         100.0 * float(np.mean(np.asarray(shown) > 0)), "%"),
        ("position_pixels_xy", f"Grasp position pixels, top view ({payload['position']['pixel_m'] * 1000:.0f} mm)",
         sum(1 for n in xy["samples"] if n > 0), ""),
        ("object_evenness_pct", "Object balance (evenness of grasps over objects)", bins.evenness_pct(object_counts),
         "%"),
        ("largest_object_pct", "Largest object's share of the grasps",
         100.0 * float(object_counts.max()) / float(object_counts.sum()), "%"),
    ]
    if gripper["source"] == "limit":
        rows.append(("width_outside", "Grasps wider than the open stop (or below shut)", width["outside"], ""))
    if has_outcomes:
        closed = sum(outcome_of.count(word) for word in CLOSED)
        rows.append(("closed", "Grasps the claw closed on (picked + failed)", closed, ""))
        if closed:
            rows.append(("picked_pct", "Picked, share of the closed grasps",
                         100.0 * outcome_of.count("picked") / closed, "%"))
    if payload["pre_grasp_width"] is not None:
        pre = values.pre_grasp_width[np.isfinite(values.pre_grasp_width)]
        rows.append(("pre_grasp_width_peak_pct", "Widest pre-grasp opening (p99.9), share of the open stop",
                     100.0 * float(np.percentile(pre, DATA_PERCENTILES[1])) / gripper["high"], "%"))
    if boxes and xy["area"] is not None:
        mask = np.asarray(xy["area"], bool)
        samples = np.asarray(xy["samples"])
        cells = max(int(mask.sum()), 1)
        rows.append(("area_visited_pct", "Pick-area pixels with a grasp (top view)",
                     100.0 * int(((samples > 0) & mask).sum()) / cells, "%"))
        closed_mask = np.isin(np.array(outcome_of, dtype=object), CLOSED)
        if has_outcomes and closed_mask.any():
            cell = bins.grid_cells_on(values.positions[closed_mask], xy["origin"], xy["shape"],
                                      payload["position"]["pixel_m"], PROJECTIONS["xy"])
            hit = np.zeros(mask.size, bool)
            hit[cell[cell >= 0]] = True
            rows.append(("area_closed_pct", "Pick-area pixels the claw closed in (top view)",
                         100.0 * int((hit & mask).sum()) / cells, "%"))
    return [{"key": key, "label": label, "value": bins.finite(value), "unit": unit} for key, label, value, unit in rows]
