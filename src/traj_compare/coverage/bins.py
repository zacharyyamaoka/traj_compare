"""The binning every coverage payload shares: linear bins, grids anchored at the origin, equal-area direction cells,
and the JSON-safe number rules. numpy only.

    from traj_compare.coverage import bins
    index = bins.bin_index(widths, 0.0, 0.125, 50)               # -1 outside, else 0..49
    cell, shape = bins.grid_cells(points, 0.01, low, high, (0, 1))  # flat pixel per point on a 1 cm grid, -1 outside
    tilt, azimuth, yaw = bins.direction_angles(rotations, (0, 0, -1))

WHY one module (2026-11-24, the grasp coverage viewer): a grasp set is the trajectory viewer's tool section without
time, so the trajectory payload (``coverage.analysis``) and the grasp payload (``grasp_coverage.analysis``) bin with the
SAME functions; two copies would drift and the two pages would disagree about the same cell. Moved out of
coverage/analysis.py unchanged (it keeps its old ``_`` names as aliases).
"""

from __future__ import annotations

import math

import numpy as np

SPHERE_RINGS, SPHERE_SECTORS = 12, 24


def bin_index(values, low: float, high: float, bins: int) -> np.ndarray:
    """Linear bin of each value, -1 outside [low, high] or not finite.

    WHY linear (Zach 2026-11-19: "I feel it would be better to just have a linear scale"): equal cells, so a visited
    % is a share of the space. WHY a tolerance: a sample timed AT its limit lands on the last edge to the last ulp.
    """
    values = np.asarray(values, float)
    tolerance = 1e-9 * (high - low)
    with np.errstate(invalid="ignore"):
        index = np.floor((values - low) / (high - low) * bins)
        index = np.where((values >= high) & (values <= high + tolerance), bins - 1, index)
        index = np.where((values < low) & (values >= low - tolerance), 0, index)
        inside = (index >= 0) & (index < bins)
    return np.where(inside, index, -1).astype(np.int64)


def edges(low: float, high: float, bins: int) -> list:
    """An edge triple as the payloads write it: ``[low, high, bins]`` (linear)."""
    return [float(low), float(high), int(bins)]


def paths_per_cell(cell: np.ndarray, owner: np.ndarray, cells: int) -> tuple[np.ndarray, np.ndarray]:
    """Distinct owners (trajectories) through each cell, and the unique (owner * cells + cell) keys behind it.

    WHY count trajectories, not samples (arm_motion_bench, Zach: "colour by runs, not samples"): a long dwell is one
    visit."""
    keys = np.unique(owner.astype(np.int64) * cells + cell)
    return np.bincount(keys % cells, minlength=cells), keys


def max_per_cell(cell: np.ndarray, values: np.ndarray, cells: int) -> np.ndarray:
    """The largest value in each cell; NaN where no finite value landed."""
    finite = np.isfinite(values)
    largest = np.full(cells, -np.inf)
    np.maximum.at(largest, cell[finite], values[finite])
    largest[np.isneginf(largest)] = np.nan
    return largest


def evenness_pct(counts: np.ndarray) -> float:
    """exp(Shannon entropy) as a share of all cells: 100 % only if every cell holds the same (Hill number of order 1)."""
    counts = np.asarray(counts)
    total = counts.sum()
    if total == 0:
        return 0.0
    share = counts[counts > 0] / total
    return 100.0 * math.exp(float(-(share * np.log(share)).sum())) / counts.size


def grid_cells(points: np.ndarray, size: float, low: np.ndarray, high: np.ndarray, axes) -> tuple[np.ndarray, list]:
    """Flat cell index (row-major over `axes`) of each point on a grid of `size` anchored at the base origin, -1
    outside; and the grid's shape. WHY anchored at the origin, not at the data: two datasets' cells line up."""
    first = np.floor(low[list(axes)] / size).astype(np.int64)
    shape = (np.floor(high[list(axes)] / size).astype(np.int64) - first + 1)
    with np.errstate(invalid="ignore"):
        index = np.floor(points[:, list(axes)] / size)
    inside = np.isfinite(index).all(axis=1)
    index = np.where(inside[:, None], index, 0).astype(np.int64) - first
    inside &= ((index >= 0) & (index < shape)).all(axis=1)
    flat = np.ravel_multi_index(tuple(np.where(inside[:, None], index, 0).T), tuple(shape))
    return np.where(inside, flat, -1), [int(n) for n in shape]


def grid_origin(low: np.ndarray, size: float, axes) -> np.ndarray:
    """The low corner of cell (0, ...) of `grid_cells`' grid: its first cell, in metres."""
    return np.floor(np.asarray(low)[list(axes)] / size) * size


def grid_cells_on(points: np.ndarray, origin, shape, size: float, axes) -> np.ndarray:
    """`grid_cells` on a payload's own grid (its `origin` and `shape`), -1 outside: low and high are set half a cell
    inside its first and last cells, so `grid_cells` lands on exactly that first cell and shape. WHY: a payload writes
    its origin rounded; re-deriving the grid from rounded bounds could shift it by a cell (the workbenches re-bin)."""
    low, high = np.zeros(3), np.zeros(3)
    for axis, start, cells in zip(axes, origin, shape, strict=True):
        first = round(start / size)
        low[axis], high[axis] = (first + 0.5) * size, (first + cells - 0.5) * size
    index, got = grid_cells(np.asarray(points, float).reshape(-1, 3), size, low, high, axes)
    if got != list(shape):  # pragma: no cover - a guard on the half-cell rule above
        raise AssertionError(f"the payload's grid {list(shape)} rebuilt as {got}")
    return index


def sphere_counts(directions: np.ndarray, rings: int = SPHERE_RINGS, sectors: int = SPHERE_SECTORS) -> np.ndarray:
    """Equal-area cells of unit vectors (prior art sphere_cell): rings uniform in z (Archimedes: equal z bands have equal
    area) x sectors uniform in azimuth from -pi. Flat index ring * sectors + sector."""
    return np.bincount(sphere_cell(directions, rings, sectors), minlength=rings * sectors)


def sphere_cell(directions: np.ndarray, rings: int = SPHERE_RINGS, sectors: int = SPHERE_SECTORS) -> np.ndarray:
    """The flat equal-area cell (ring * sectors + sector) of each unit vector (see `sphere_counts`)."""
    directions = np.asarray(directions, float).reshape(-1, 3)
    ring = np.clip(np.floor((directions[:, 2] + 1.0) / 2.0 * rings), 0, rings - 1).astype(np.int64)
    azimuth = np.arctan2(directions[:, 1], directions[:, 0])
    sector = np.clip(np.floor((azimuth + math.pi) / (2 * math.pi) * sectors), 0, sectors - 1).astype(np.int64)
    return ring * sectors + sector


def grid_2d(x_values, x_edges, y_values, y_edges, x_key: str, y_key: str) -> dict:
    """A 2-D count grid ``{x_key: edges, y_key: edges, "shape": [nx, ny], "counts": flat}`` (C order)."""
    x_index = bin_index(x_values, *x_edges)
    y_index = bin_index(y_values, *y_edges)
    inside = (x_index >= 0) & (y_index >= 0)
    nx, ny = x_edges[2], y_edges[2]
    return {x_key: edges(*x_edges), y_key: edges(*y_edges), "shape": [nx, ny],
            "counts": ints(np.bincount(x_index[inside] * ny + y_index[inside], minlength=nx * ny))}


def histogram_1d(values, low: float, high: float, bins: int) -> dict:
    """``{"edges": [low, high, bins], "counts": [...]}``; values outside are in no bin."""
    index = bin_index(values, low, high, bins)
    return {"edges": edges(low, high, bins), "counts": ints(np.bincount(index[index >= 0], minlength=bins))}


def direction_angles(rotations: np.ndarray, reference) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(tilt, azimuth, yaw) in radians of every (3, 3) base <- tool rotation.

    tilt = angle between the tool z axis and `reference` (0 = along it); azimuth = atan2(z.y, z.x), which way in base
    XY the tool z leans; yaw = atan2(x.y, x.x), the heading of the tool x axis in base XY."""
    reference = np.asarray(reference, float)
    reference = reference / np.linalg.norm(reference)
    z_axis, x_axis = rotations[:, :, 2], rotations[:, :, 0]
    tilt = np.arccos(np.clip(z_axis @ reference, -1.0, 1.0))
    azimuth = np.arctan2(z_axis[:, 1], z_axis[:, 0])
    yaw = np.arctan2(x_axis[:, 1], x_axis[:, 0])
    return tilt, azimuth, yaw


# ── JSON-safe values ────────────────────────────────────────────────────────────────────────────────────────────────


def ints(values) -> list[int]:
    return np.asarray(values).astype(np.int64).tolist()


def floats(values, decimals: int | None = None) -> list:
    """Python floats, NaN/inf -> None (json.dumps(allow_nan=False) must work)."""
    values = np.asarray(values, float)
    if decimals is not None:
        values = np.round(values, decimals)
    return [value if math.isfinite(value) else None for value in values.tolist()]


def number(value) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def finite(value) -> float:
    value = float(value)
    return value if math.isfinite(value) else 0.0


def decimals(span: float, digits: int = 4) -> int:
    """Decimals that keep `digits` significant figures of a limit span (a path drawn on a figure needs no more)."""
    if not span > 0 or not math.isfinite(span):
        return 6
    return max(0, int(math.ceil(digits - math.log10(span))))
