"""Record coverage analysis: any list of records in, the payload "traj_compare.record_coverage/1" out (numpy only).

    from traj_compare.record_coverage import analyze
    coverage = analyze(records, group_by="item", split="split", pairs=[("x_m", "y_m")])
    coverage.payload, coverage.numbers

Contract: docs/RECORD_COVERAGE.md. A record is a dataclass instance (robot_msgs messages are frozen dataclasses), at any
depth, or a Mapping read from a JSON log. Each record is flattened into columns; a column is a number (a histogram
against its declared range), a category (class balance) or text (an identifier); None and NaN are missing, never values.

WHY the dataclass is the schema (TFDV's schema, without TFDV): Zach's `Value(1.2, "m", low=0.6, high=1.85)` already
says what range a field may take, so the class declares the space and its instances hold the measurements; a field
default's Value is read even when a record holds a plain float (dataclass_values: a Value outside its range is refused
at construction, so measured data is plain and the declaration lives on the class).
WHY np.histogram's bins (searchsorted on linspace edges, the last bin closed): the edges are written into the payload
and any reader re-bins with numpy and gets the same counts (tests/test_record_coverage.py is that oracle).
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from dataclass_values import meta

SCHEMA = "traj_compare.record_coverage/1"
MARGIN = 0.10  # each side of a declared range, as a share of it: overshoot shows, the limits fall on bin edges
MAX_COMPONENTS = 4  # a sequence of at most this many numbers is one column per component, else its length
MAX_DEPTH = 4
TEXT_DISTINCT = 24  # a str field with more distinct values than this, and more than half distinct, is an identifier
TEXT_ALWAYS = 64  # ... and with more than this, it is one even when ids repeat (task ids shared across robots)
MAX_INTEGER_BINS = 60
GROWTH_POINTS = 200
SHUFFLES = 32
POINTS_MAX = 20_000
RAIL_LEVELS = (2, 24)  # a category the workbench rail may filter by
MISSING_GROUP = "(missing)"
DEG = 180.0 / math.pi
# WHY suffixes: Zach's logs name their units (psi_rad, item_width_mm, belt_speed_m_s); longest suffix first
SUFFIX_UNITS = (("_m_s", "m/s"), ("_rad_s", "rad/s"), ("_rad", "rad"), ("_deg", "deg"), ("_mm", "mm"), ("_kg", "kg"),
                ("_pct", "%"), ("_m", "m"), ("_s", "s"), ("_n", "N"), ("_hz", "Hz"))
# WHY degrees only at the display edge (Zach 2026-11-11): the payload stays SI, a viewer multiplies by display.scale
DISPLAY = {"rad": (DEG, "°"), "rad/s": (DEG, "°/s"), "rad/s^2": (DEG, "°/s²")}


# ── columns: a record flattened ───────────────────────────────────────────────────────────────────────────────────────


@dataclass
class _Column:
    name: str
    origin: str  # field | property | component | length
    values: list = field(default_factory=list)  # one per record, None = missing
    metas: list = field(default_factory=list)  # Value metadata seen on records (dicts)
    default_meta: dict | None = None  # the dataclass field default's Value metadata
    enum_type: type | None = None
    space_bounds: tuple[float, float] | None = None


def _is_number(value) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, (float, np.floating)) and math.isnan(float(value)))


def _value_meta(value) -> dict | None:
    try:
        found = meta(value)
    except Exception:  # meta() of a type it does not know
        return None
    return found or None


def _properties(cls: type) -> list[str]:
    """Public properties in definition order, base classes first (cached_property too)."""
    names: list[str] = []
    for klass in reversed(cls.__mro__):
        for name, member in vars(klass).items():
            if not name.startswith("_") and isinstance(member, (property, functools.cached_property)) and name not in names:
                names.append(name)
    return names


class _Flattener:
    """Two passes: leaves into ordered paths (a sequence kept whole), then each sequence path becomes components or a
    length for EVERY record, so a column means the same thing in every row."""

    def __init__(self, space=None) -> None:
        self.paths: dict[str, dict] = {}  # path -> {"origin", "default_meta", "enum"}
        self.notes: list[str] = []
        self.bounds = dict(getattr(space, "array_bounds", None) or {})

    def leaves(self, record) -> dict[str, Any]:
        out: dict[str, Any] = {}
        self._walk(record, "", 0, out, None)
        if dataclasses.is_dataclass(record) and not isinstance(record, type):
            for name in _properties(type(record)):
                try:
                    value = getattr(record, name)
                except Exception:  # a property that raises is skipped, never fatal
                    continue
                if value is None or _is_number(value) or isinstance(value, (str, bool, enum.Enum, np.bool_)):
                    self._leaf(name, value, out, "property", None)
        return out

    def _leaf(self, path: str, value, out: dict, origin: str, default_meta) -> None:
        if path not in self.paths:
            self.paths[path] = {"origin": origin, "default_meta": default_meta}
        elif default_meta and not self.paths[path].get("default_meta"):
            self.paths[path]["default_meta"] = default_meta
        out[path] = value

    def _walk(self, value, path: str, depth: int, out: dict, default_meta) -> None:
        if depth > MAX_DEPTH:
            note = f"cut at depth {MAX_DEPTH}: {path}"
            if note not in self.notes:
                self.notes.append(note)
            return
        join = (lambda key: f"{path}.{key}") if path else (lambda key: str(key))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                default = f.default if f.default is not dataclasses.MISSING else None
                self._walk(getattr(value, f.name), join(f.name), depth + 1, out, _value_meta(default))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                self._walk(item, join(key), depth + 1, out, None)
            return
        if isinstance(value, np.ndarray) and value.ndim == 0:
            value = value.item()
        if isinstance(value, (list, tuple, np.ndarray)) and not isinstance(value, str):
            self._leaf(path, ("__seq__", tuple(np.asarray(value).ravel().tolist()) if isinstance(value, np.ndarray)
                              else tuple(value)), out, "sequence", default_meta)
            return
        self._leaf(path, value, out, "field", default_meta)


def _columns(records: Sequence, *, space=None) -> tuple[list[_Column], list[str]]:
    flat = _Flattener(space)
    rows = [flat.leaves(record) for record in records]
    columns: list[_Column] = []
    for path, info in flat.paths.items():
        if info["origin"] != "sequence":
            column = _Column(path, info["origin"], default_meta=info.get("default_meta"))
            for row in rows:
                value = row.get(path)
                if isinstance(value, tuple) and value and value[0] == "__seq__":
                    value = len(value[1])  # the same path a sequence elsewhere: count its length
                column.values.append(value)
            columns.append(column)
            continue
        sequences = [row.get(path) for row in rows]
        given = [s[1] for s in sequences if isinstance(s, tuple) and s and s[0] == "__seq__"]
        lengths = {len(s) for s in given}
        numeric = all(all(_is_number(v) or _is_missing(v) for v in s) for s in given)
        if given and numeric and len(lengths) == 1 and 0 < next(iter(lengths)) <= MAX_COMPONENTS:
            n = next(iter(lengths))
            bounds = flat.bounds.get(path)
            for i in range(n):
                column = _Column(f"{path}[{i}]", "component")
                if bounds is not None:
                    low, high = (np.ravel(np.asarray(b, float)) for b in bounds)
                    column.space_bounds = (float(low[i]), float(high[i]))
                for s in sequences:
                    column.values.append(s[1][i] if isinstance(s, tuple) and s and s[0] == "__seq__" else None)
                columns.append(column)
        else:
            column = _Column(f"len({path})", "length")
            column.values = [len(s[1]) if isinstance(s, tuple) and s and s[0] == "__seq__" else None for s in sequences]
            columns.append(column)
    for column in columns:
        cleaned, metas = [], []
        for value in column.values:
            if isinstance(value, np.generic):
                value = value.item()
            found = _value_meta(value) if value is not None else None
            if found:
                metas.append(found)
            if isinstance(value, enum.Enum) and column.enum_type is None:
                column.enum_type = type(value)
            cleaned.append(None if _is_missing(value) else value)
        column.values = cleaned
        column.metas = metas
    return columns, flat.notes


# ── kinds, ranges, levels ─────────────────────────────────────────────────────────────────────────────────────────────


def _unit_of(name: str, metas: list[dict], default_meta: dict | None) -> str | None:
    for found in [*metas[:1], default_meta]:
        if found and found.get("unit"):
            return str(found["unit"])
    stem = name
    if stem.startswith("len("):
        return None
    stem = stem.split("[", 1)[0].rsplit(".", 1)[-1].lower()
    for suffix, unit in SUFFIX_UNITS:
        if stem.endswith(suffix):
            return unit
    return None


def _display(unit: str | None) -> dict:
    scale, shown = DISPLAY.get(unit or "", (1.0, unit))
    return {"scale": scale, "unit": shown}


def _level(value) -> str:
    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, float) and value.is_integer():
        return str(int(value)) if abs(value) < 1e15 else str(value)
    return str(value)


def _declared_choices(column: _Column, choices: Mapping | None) -> tuple[list[str] | None, str | None]:
    if choices and column.name in choices:
        return [_level(c) for c in choices[column.name]], "given"
    for found in [*column.metas[:1], column.default_meta]:
        if found and found.get("choices"):
            return [_level(c) for c in found["choices"]], "declared"
    if column.enum_type is not None:
        return [_level(member) for member in column.enum_type], "enum"
    present = [v for v in column.values if v is not None]
    if present and all(isinstance(v, (bool, np.bool_)) for v in present):
        return ["False", "True"], "bool"
    return None, None


def _kind(column: _Column, choices: Mapping | None) -> str:
    present = [v for v in column.values if v is not None]
    declared, _ = _declared_choices(column, choices)
    if declared is not None:
        return "category"
    if not present:
        return "number"
    if all(_is_number(v) for v in present):
        return "number"
    if all(isinstance(v, str) for v in present):
        distinct = len(set(present))
        if distinct > TEXT_ALWAYS or (distinct > TEXT_DISTINCT and distinct > len(present) / 2):
            return "text"
        return "category"
    return "category"


def _declared_range(column: _Column, ranges: Mapping | None, notes: list[str]) -> tuple[float, float, str] | None:
    if ranges and column.name in ranges:
        low, high = ranges[column.name]
        return float(low), float(high), "given"
    stated = [(m["low"], m["high"]) for m in column.metas if m.get("low") is not None and m.get("high") is not None]
    if stated:
        lows, highs = {float(lo) for lo, _ in stated}, {float(hi) for _, hi in stated}
        if len(lows) > 1 or len(highs) > 1:
            notes.append(f"{column.name}: the records declare different ranges; their union is used")
        return min(lows), max(highs), "declared"
    found = column.default_meta
    if found and found.get("low") is not None and found.get("high") is not None:
        return float(found["low"]), float(found["high"]), "declared"
    if column.space_bounds is not None:
        return column.space_bounds[0], column.space_bounds[1], "declared"
    return None


def _is_integer(values: np.ndarray, raw: list) -> bool:
    return bool(raw) and all(isinstance(v, (int, np.integer)) and not isinstance(v, bool) for v in raw)


def _edges(low: float, high: float, integer: bool, bins: int) -> tuple[list, int, int]:
    """([lo, hi, n], the first inside bin, the inside bin count) for a range, margin included."""
    if integer and float(low).is_integer() and float(high).is_integer() and high - low + 1 <= MAX_INTEGER_BINS:
        inside = int(high - low) + 1
        margin = max(1, round(MARGIN * inside))
        return [float(low) - 0.5 - margin, float(high) + 0.5 + margin, inside + 2 * margin], margin, inside
    inside = int(bins)
    margin = round(MARGIN * inside)
    width = (high - low) / inside
    return [float(low) - margin * width, float(high) + margin * width, inside + 2 * margin], margin, inside


def _bin(values: np.ndarray, block: Sequence) -> np.ndarray:
    """np.histogram's bin of each value on the linear edges [lo, hi, n]: -1 outside the edges or missing."""
    lo, hi, n = block
    edges = np.linspace(float(lo), float(hi), int(n) + 1)
    values = np.asarray(values, float)
    index = np.searchsorted(edges, values, side="right") - 1
    index[values == edges[-1]] = int(n) - 1
    index[(values < edges[0]) | (values > edges[-1]) | ~np.isfinite(values)] = -1
    return index


def _finite(value: float) -> float:
    return float(value) if math.isfinite(float(value)) else 0.0


def _pct(part: float, whole: float) -> float:
    return 100.0 * part / whole if whole else 0.0


def _evenness(counts: np.ndarray, cells: int) -> float:
    counts = np.asarray(counts, float)
    counts = counts[counts > 0]
    if not len(counts) or not cells:
        return 0.0
    shares = counts / counts.sum()
    return 100.0 * math.exp(-float(np.sum(shares * np.log(shares)))) / cells


# ── the analysis ──────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class _Number:
    column: _Column
    values: np.ndarray  # NaN = missing
    low: float
    high: float
    source: str
    integer: bool
    edges: list
    first: int  # first inside bin
    inside: int  # inside bin count


@dataclass
class _Category:
    column: _Column
    levels: list[str]
    declared: list[bool]
    source: str
    codes: np.ndarray  # level index per record, -1 = missing


class RecordCoverage:
    """`analyze()`'s result: the JSON payload, its headline numbers, and the viewers over it."""

    def __init__(self, payload: dict, records: Sequence, options: dict) -> None:
        self.payload = payload
        self.records = records
        self.options = options

    @property
    def numbers(self) -> dict[str, float]:
        return {entry["key"]: entry["value"] for entry in self.payload["numbers"]}

    def write_page(self, out_dir: Path | str, **kwargs) -> Path:
        from .workbench import write_workbench

        return write_workbench(self, self.records, out_dir, **kwargs)

    def plot(self, out_dir: Path | str, **kwargs) -> list[Path]:
        from .matplotlib_view import plot_records

        return plot_records(self.payload, out_dir, **kwargs)

    def serve_viser(self, **kwargs):
        from .viser_view import serve_records

        return serve_records(self.payload, **kwargs)

    def log_wandb(self, run, **kwargs) -> dict:
        from .wandb_log import log_records

        return log_records(run, self.payload, **kwargs)


def _numbers_and_categories(columns, *, ranges, choices, bins, notes):
    numbers: dict[str, _Number] = {}
    categories: dict[str, _Category] = {}
    texts: dict[str, _Column] = {}
    kinds: dict[str, str] = {}
    for column in columns:
        kind = _kind(column, choices)
        kinds[column.name] = kind
        if kind == "text":
            texts[column.name] = column
        elif kind == "category":
            declared, source = _declared_choices(column, choices)
            seen = Counter(_level(v) for v in column.values if v is not None)
            if declared is None:
                first = {level: i for i, level in enumerate(dict.fromkeys(_level(v) for v in column.values if v is not None))}
                levels = sorted(seen, key=lambda level: (-seen[level], first[level]))
                flags, source = [False] * len(levels), "data"
            else:
                levels = list(dict.fromkeys(declared))
                extra = [level for level in dict.fromkeys(_level(v) for v in column.values if v is not None)
                         if level not in levels]
                flags = [True] * len(levels) + [False] * len(extra)
                levels += extra
            where = {level: i for i, level in enumerate(levels)}
            codes = np.asarray([-1 if v is None else where[_level(v)] for v in column.values], int)
            categories[column.name] = _Category(column, levels, flags, source, codes)
        else:
            values = np.asarray([np.nan if v is None else float(v) for v in column.values], float)
            present = values[np.isfinite(values)]
            if not len(present):
                notes.append(f"{column.name}: no values")
                continue
            integer = _is_integer(present, [v for v in column.values if v is not None])
            declared = _declared_range(column, ranges, notes)
            if declared is not None:
                low, high, source = declared
            elif integer:
                low, high, source = float(present.min()), float(present.max()), "data"
            else:
                p001, p999 = np.percentile(present, [0.1, 99.9])
                middle, half = (p001 + p999) / 2.0, (p999 - p001) / 2.0 * 1.15
                if half <= 0:
                    half = max(abs(float(middle)) * 0.05, 0.5)
                low, high, source = float(middle - half), float(middle + half), "data"
            if high < low or (high == low and not integer):
                notes.append(f"{column.name}: its range [{low}, {high}] is empty; widened by 0.5 each side")
                low, high = low - 0.5, high + 0.5
            edges, first, inside = _edges(low, high, integer, bins)
            numbers[column.name] = _Number(column, values, low, high, source, integer, edges, first, inside)
    return numbers, categories, texts, kinds


def _pair_edges(number: _Number, grid: int) -> list:
    if number.integer and number.low.is_integer() and number.high.is_integer() \
            and number.high - number.low + 1 <= MAX_INTEGER_BINS:
        return [number.low - 0.5, number.high + 0.5, int(number.high - number.low) + 1]
    return [number.low, number.high, int(grid)]


def _shuffled_growth(cells: np.ndarray, owners: np.ndarray, n_records: int, total: int, at: np.ndarray) -> dict:
    rng = np.random.default_rng(0)
    curves = []
    for _ in range(SHUFFLES):
        rank = rng.permutation(n_records)
        first = np.full(total, n_records, int)
        np.minimum.at(first, cells, rank[owners])
        ordered = np.sort(first[first < n_records])
        curves.append(np.searchsorted(ordered, at, side="left"))  # cells first visited by ranks < k
    # WHY counts first, scaled after: identical curves (every shuffle at k = n) then give identical percentiles
    curves = np.asarray(curves, float)
    scale = 100.0 / total if total else 0.0
    return {"median": (np.median(curves, axis=0) * scale).tolist(),
            "p10": (np.percentile(curves, 10, axis=0) * scale).tolist(),
            "p90": (np.percentile(curves, 90, axis=0) * scale).tolist()}


def analyze(records: Sequence, *, ranges: Mapping[str, tuple[float, float]] | None = None,
            choices: Mapping[str, Sequence] | None = None, space=None, fields: Sequence[str] | None = None,
            pairs: Sequence[tuple[str, str]] | None = None, group_by: str | None = None, split: str | None = None,
            reference: str | None = None, xyz: Sequence[str] | None = None, id_field: str | None = None,
            title: str = "", subtitle: str = "", enough: int = 10, bins: int = 40, grid: int = 24) -> RecordCoverage:
    """See docs/RECORD_COVERAGE.md. Records keep their order: it is the growth curve's order."""
    records = list(records)
    if not records:
        raise ValueError("no records: analyze() needs at least one")
    columns, notes = _columns(records, space=space)
    if fields is not None:
        by_name = {column.name: column for column in columns}
        unknown = [name for name in fields if name not in by_name]
        if unknown:
            raise ValueError(f"fields: no field {unknown[0]!r} (the records have {', '.join(list(by_name)[:12])} ...)")
        columns = [by_name[name] for name in fields]
    notes = list(notes)
    numbers, categories, texts, kinds = _numbers_and_categories(columns, ranges=ranges, choices=choices, bins=bins,
                                                                notes=notes)
    n = len(records)

    def need(name: str | None, kind: str, what: str) -> None:
        if name is None:
            return
        if name not in kinds:
            raise ValueError(f"{what}: no field {name!r}")
        if kinds[name] != kind:
            raise ValueError(f"{what}: {name!r} is a {kinds[name]} field; it needs a {kind} field")

    need(group_by, "category", "group_by")
    need(split, "category", "split")
    if split is not None:
        levels = categories[split].levels
        if reference is not None and str(reference) not in levels:
            raise ValueError(f"reference: {reference!r} is not a level of {split!r} ({', '.join(levels)})")

    # the id
    if id_field is None:
        id_field = next((name for name, column in texts.items()
                         if None not in column.values and len(set(column.values)) == n), None)
    elif id_field not in kinds:
        raise ValueError(f"id_field: no field {id_field!r}")
    by_name = {column.name: column for column in columns}
    ids = ([str(v) if v is not None else f"#{i}" for i, v in enumerate(by_name[id_field].values)] if id_field
           else [f"#{i}" for i in range(n)])

    # groups
    if group_by is not None:
        group = categories[group_by]
        group_names = [group.levels[c] if c >= 0 else MISSING_GROUP for c in group.codes]
        groups = [g for g in dict.fromkeys(group_names)]
        groups = [g for g in group.levels if g in groups] + ([MISSING_GROUP] if MISSING_GROUP in groups else [])
    else:
        group_names, groups = [None] * n, []

    # the fields block
    field_rows = []
    for column in columns:
        unit = _unit_of(column.name, column.metas, column.default_meta) if kinds[column.name] == "number" else None
        missing = sum(1 for v in column.values if v is None)
        field_rows.append({"name": column.name, "label": column.name, "kind": kinds[column.name], "unit": unit,
                           "display": _display(unit), "origin": column.origin, "present": n - missing,
                           "missing": missing, "missing_pct": _pct(missing, n)})

    # number fields
    hist_block: dict[str, dict] = {}
    for name, number in numbers.items():
        index = _bin(number.values, number.edges)
        counts = np.bincount(index[index >= 0], minlength=number.edges[2])
        present = number.values[np.isfinite(number.values)]
        p001, p999 = np.percentile(present, [0.1, 99.9])
        inside = counts[number.first:number.first + number.inside]
        outside = 0 if number.source == "data" else int(((present < number.low) | (present > number.high)).sum())
        block = {"edges": number.edges, "low": number.low, "high": number.high, "source": number.source,
                 "integer": number.integer, "counts": counts.tolist(), "groups": None,
                 "p001": float(p001), "p999": float(p999), "min": float(present.min()), "max": float(present.max()),
                 "mean": float(present.mean()), "std": float(present.std()),
                 "span_pct": _pct(float(p999 - p001), number.high - number.low),
                 "visited_pct": _pct(int(np.count_nonzero(inside)), number.inside), "outside": outside,
                 "distinct": int(len(np.unique(present)))}
        if groups:
            block["groups"] = {g: np.bincount(index[(index >= 0) & (np.asarray(group_names, object) == g)],
                                              minlength=number.edges[2]).tolist() for g in groups}
        hist_block[name] = block

    # category fields
    class_block: dict[str, dict] = {}
    for name, category in categories.items():
        k = len(category.levels)
        counts = np.bincount(category.codes[category.codes >= 0], minlength=k)
        seen = counts[counts > 0]
        total = int(seen.sum())
        shares = seen / total if total else seen
        effective = math.exp(-float(np.sum(shares * np.log(shares)))) if total else 0.0
        block = {"levels": category.levels, "declared": category.declared, "source": category.source,
                 "counts": counts.tolist(), "groups": None,
                 "unseen": [lvl for lvl, c, d in zip(category.levels, counts, category.declared) if d and not c],
                 "undeclared": [lvl for lvl, d in zip(category.levels, category.declared)
                                if not d and category.source != "data"],
                 "majority_pct": _pct(int(seen.max()), total) if total else 0.0,
                 "minority_pct": _pct(int(seen.min()), total) if total else 0.0,
                 "imbalance_ratio": float(seen.max() / seen.min()) if total else 1.0,
                 "effective_classes": effective, "evenness_pct": _pct(effective, k)}
        if groups:
            names = np.asarray(group_names, object)
            block["groups"] = {g: np.bincount(category.codes[(category.codes >= 0) & (names == g)], minlength=k).tolist()
                               for g in groups}
        class_block[name] = block

    text_block = {name: {"distinct": len(set(v for v in column.values if v is not None)),
                         "duplicates": sum(1 for v in column.values if v is not None)
                         - len(set(v for v in column.values if v is not None)),
                         "examples": [str(v) for v in list(dict.fromkeys(v for v in column.values if v is not None))[:3]]}
                  for name, column in texts.items()}

    # pairs
    if pairs is None:
        ranged = [name for name, number in numbers.items() if number.source != "data"][:4]
        pairs = [(a, b) for i, a in enumerate(ranged) for b in ranged[i + 1:]]
    pair_block = []
    pair_cells: list[np.ndarray] = []  # per pair: the flat cell per record, -1 none
    for x, y in pairs:
        for name in (x, y):
            if name not in kinds:
                raise ValueError(f"pairs: no field {name!r}")
            if kinds[name] != "number":
                raise ValueError(f"pairs: {name!r} is a {kinds[name]} field; a pair plane needs two number fields")
            if name not in numbers:
                raise ValueError(f"pairs: {name!r} has no values")
        xe, ye = _pair_edges(numbers[x], grid), _pair_edges(numbers[y], grid)
        xv, yv = numbers[x].values, numbers[y].values
        both = np.isfinite(xv) & np.isfinite(yv)
        xi, yi = _bin(xv, xe), _bin(yv, ye)
        cell = np.where(both & (xi >= 0) & (yi >= 0), xi * ye[2] + yi, -1)
        size = xe[2] * ye[2]
        samples = np.bincount(cell[cell >= 0], minlength=size)
        pair_cells.append(cell)
        pair_block.append({"x": x, "y": y, "x_edges": xe, "y_edges": ye, "shape": [xe[2], ye[2]],
                           "samples": samples.tolist(), "visited_pct": _pct(int(np.count_nonzero(samples)), size),
                           "sufficient_pct": _pct(int(np.count_nonzero(samples >= enough)), size),
                           "evenness_pct": _evenness(samples, size), "outside": int((both & (cell < 0)).sum()),
                           "missing": int((~both).sum())})

    # the space's cells, and which each record visits
    families: list[tuple[str, np.ndarray, int]] = []  # (field or pair, cell per record (-1 none), cells)
    for name, number in numbers.items():
        index = _bin(number.values, number.edges) - number.first
        families.append((name, np.where((index >= 0) & (index < number.inside), index, -1), number.inside))
    for name, category in categories.items():
        families.append((name, category.codes.copy(), len(category.levels)))
    for (x, y), cell, block in zip(pairs, pair_cells, pair_block):
        families.append((f"{x} × {y}", cell, block["shape"][0] * block["shape"][1]))
    offsets = np.cumsum([0] + [size for _, _, size in families])
    total = int(offsets[-1])
    owners_list, cells_list, family_of = [], [], []
    for f, (_, cell, _) in enumerate(families):
        has = cell >= 0
        owners_list.append(np.flatnonzero(has))
        cells_list.append(cell[has] + offsets[f])
        family_of.append(np.full(int(has.sum()), f))
    owners = np.concatenate(owners_list) if owners_list else np.zeros(0, int)
    cells = np.concatenate(cells_list).astype(int) if cells_list else np.zeros(0, int)
    family_index = np.concatenate(family_of) if family_of else np.zeros(0, int)
    first = np.full(total, n, int)
    np.minimum.at(first, cells, owners)
    visit_count = np.bincount(cells, minlength=total)
    visited = int(np.count_nonzero(visit_count))
    at = np.unique(np.linspace(1, n, min(GROWTH_POINTS, n)).round().astype(int))
    ordered = np.sort(first[first < n])
    growth_visited = np.searchsorted(ordered, at, side="left")
    new_cells = np.bincount(first[first < n], minlength=n)
    unique_owner = owners[visit_count[cells] == 1]
    unique_cells = np.bincount(unique_owner, minlength=n)
    tenth = int(math.ceil(0.9 * n))
    last_tenth = int(np.count_nonzero((first >= tenth) & (first < n)))
    f1, f2 = int(np.count_nonzero(visit_count == 1)), int(np.count_nonzero(visit_count == 2))
    chao1 = visited + (f1 * f1 / (2.0 * f2) if f2 else f1 * (f1 - 1) / 2.0)
    chao1 = min(float(chao1), float(total))
    coverage_block = {"cells": total, "visited": visited, "visited_pct": _pct(visited, total),
                      "growth": {"records": at.tolist(), "visited_pct": (growth_visited * (100.0 / total if total else 0.0)).tolist(),
                                 "shuffled": _shuffled_growth(cells, owners, n, total, at)},
                      "last_tenth_new_pct": _pct(last_tenth, visited), "chao1_cells": chao1,
                      "ceiling_pct": _pct(chao1, total)}

    # each record
    missing_per_record = [sum(1 for column in columns if column.values[i] is None) for i in range(n)]
    split_codes = categories[split].codes if split is not None else None
    record_rows = [{"id": ids[i], "index": i, "group": group_names[i],
                    "split": (categories[split].levels[split_codes[i]] if split_codes[i] >= 0 else None)
                    if split is not None else None,
                    "missing": missing_per_record[i], "new_cells": int(new_cells[i]), "unique_cells": int(unique_cells[i])}
                   for i in range(n)]

    # held-out support
    support = None
    if split is not None:
        category = categories[split]
        reference = str(reference) if reference is not None else category.levels[0]
        ref = category.levels.index(reference)
        split_family = [f for f, (name, _, _) in enumerate(families) if name == split]
        keep = ~np.isin(family_index, split_family)
        ref_cells = set(cells[keep & (category.codes[owners] == ref)].tolist())
        outside_ref = keep & ~np.isin(cells, list(ref_cells))
        levels_block = {}
        for code, level in enumerate(category.levels):
            if code == ref:
                continue
            members = np.flatnonzero(category.codes == code)
            if not len(members):
                continue
            bad = set(owners[outside_ref & (category.codes[owners] == code)].tolist())
            per_field = {}
            for f, (name, cell, _) in enumerate(families):
                if f in split_family or name not in numbers and name not in categories:
                    continue
                with_cell = members[cell[members] >= 0]
                if not len(with_cell):
                    continue
                off = set(owners[outside_ref & (family_index == f) & (category.codes[owners] == code)].tolist())
                per_field[name] = _pct(len(off), len(with_cell))
            levels_block[level] = {"records": int(len(members)), "unsupported": len(bad),
                                   "unsupported_pct": _pct(len(bad), len(members)), "fields": per_field}
        support = {"split": split, "reference": reference, "levels": levels_block}

    # 3-D points
    points3d = _points3d(xyz, numbers, columns, kinds, categories, group_by, split, field_rows)

    payload = {
        "schema": SCHEMA, "title": title, "subtitle": subtitle, "enough": int(enough),
        "source": {"records": n, "fields": len(columns), "group_by": group_by, "groups": groups, "split": split,
                   "reference": support["reference"] if support else None, "id_field": id_field, "notes": notes},
        "fields": field_rows, "hist": hist_block, "classes": class_block, "texts": text_block, "pairs": pair_block,
        "coverage": coverage_block, "records": record_rows, "support": support, "points3d": points3d,
    }
    payload["numbers"] = _headline(payload, n)
    return RecordCoverage(payload, records, {"ranges": ranges, "choices": choices, "space": space, "fields": fields})


def _points3d(xyz, numbers, columns, kinds, categories, group_by, split, field_rows) -> dict | None:
    if xyz is None:
        names = [c.name for c in columns]
        for column in columns:
            if column.origin == "component" and column.name.endswith("[0]"):
                stem = column.name[:-3]
                triple = [f"{stem}[{i}]" for i in range(3)]
                if all(t in names for t in triple) and f"{stem}[3]" not in names and all(t in numbers for t in triple):
                    xyz = triple
                    break
    if xyz is None:
        return None
    xyz = list(xyz)
    if len(xyz) != 3:
        raise ValueError(f"xyz: three number fields, got {len(xyz)}")
    for name in xyz:
        if name not in kinds:
            raise ValueError(f"xyz: no field {name!r}")
        if name not in numbers:
            raise ValueError(f"xyz: {name!r} is not a number field with values")
    values = np.stack([numbers[name].values for name in xyz], axis=1)
    keep = np.flatnonzero(np.isfinite(values).all(axis=1))
    if len(keep) > POINTS_MAX:
        keep = keep[np.unique(np.linspace(0, len(keep) - 1, POINTS_MAX).round().astype(int))]
    color_by = group_by or split or next((name for name, c in categories.items() if 2 <= len(c.levels) <= 12), None)
    display = next(row["display"] for row in field_rows if row["name"] == xyz[0])
    return {"fields": xyz, "labels": xyz, "low": [numbers[n].low for n in xyz], "high": [numbers[n].high for n in xyz],
            "source": [numbers[n].source for n in xyz], "display": display,
            "points": values[keep].tolist(), "color_by": color_by,
            "levels": categories[color_by].levels if color_by else [],
            "codes": categories[color_by].codes[keep].tolist() if color_by else []}


NUMBER_LABELS = {
    "records": ("Records", ""), "fields": ("Fields", ""), "number_fields": ("Number fields", ""),
    "category_fields": ("Category fields", ""), "missing_pct": ("Missing values", "%"),
    "complete_records_pct": ("Records with nothing missing", "%"),
    "range_visited_mean_pct": ("Range visited, mean over number fields", "%"),
    "fields_without_range": ("Number fields with no stated range", ""),
    "class_imbalance_max": ("Largest class imbalance (largest ÷ smallest class)", "×"),
    "missing_classes": ("Declared classes no record has", ""),
    "pair_visited_mean_pct": ("Pair planes visited, mean", "%"),
    "coverage_visited_pct": ("Cells of the whole space visited", "%"),
    "last_tenth_new_pct": ("Visited cells first reached by the last 10 % of records", "%"),
    "ceiling_pct": ("Expected with more of the same data (Chao1)", "%"),
    "droppable_records_pct": ("Records that add no cell of their own", "%"),
}


def _headline(payload: dict, n: int) -> list[dict]:
    fields = payload["fields"]
    hist, classes, pairs = payload["hist"], payload["classes"], payload["pairs"]
    missing = sum(f["missing"] for f in fields)
    complete = sum(1 for r in payload["records"] if r["missing"] == 0)
    values = {
        "records": n, "fields": len(fields),
        "number_fields": sum(1 for f in fields if f["kind"] == "number"),
        "category_fields": sum(1 for f in fields if f["kind"] == "category"),
        "missing_pct": _pct(missing, n * len(fields)),
        "complete_records_pct": _pct(complete, n),
        "range_visited_mean_pct": float(np.mean([h["visited_pct"] for h in hist.values()])) if hist else 0.0,
        "fields_without_range": sum(1 for f in fields if f["kind"] == "number"
                                    and (f["name"] not in hist or hist[f["name"]]["source"] == "data")),
        "class_imbalance_max": max((c["imbalance_ratio"] for c in classes.values()), default=1.0),
        "missing_classes": sum(len(c["unseen"]) for c in classes.values()),
        "pair_visited_mean_pct": float(np.mean([p["visited_pct"] for p in pairs])) if pairs else 0.0,
        "coverage_visited_pct": payload["coverage"]["visited_pct"],
        "last_tenth_new_pct": payload["coverage"]["last_tenth_new_pct"],
        "ceiling_pct": payload["coverage"]["ceiling_pct"],
        "droppable_records_pct": _pct(sum(1 for r in payload["records"] if r["unique_cells"] == 0), n),
    }
    out = [{"key": key, "label": NUMBER_LABELS[key][0], "value": _finite(value), "unit": NUMBER_LABELS[key][1]}
           for key, value in values.items()]
    if payload["support"]:
        for level, block in payload["support"]["levels"].items():
            out.append({"key": f"unsupported_pct.{level}",
                        "label": f"{level} records outside what {payload['support']['reference']} covers",
                        "value": _finite(block["unsupported_pct"]), "unit": "%"})
    return out
