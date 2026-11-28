"""Panels at the playhead: what a run view shows besides curves.

A run that executes a **sequence** (a homing recipe, a pick, a recovery procedure) has more to say than q / qd / T: which
step it is on, what each joint is being told right now, and the log of what happened when. Three plain building blocks,
all driven by the page's one transport (the time lane), all optional (``Comparison.panels``; a comparison without them is
unchanged):

- ``StepTrack``: one row of the **step band** above the stage and the tabs. Each ``StepSpan`` is a block on the run's
  clock (a recipe line, a primitive, a phase). Tracks stack, so the top row can be the recipe as its author wrote it and
  the row below what it expands to. The block under the playhead is highlighted, its whole text is written out under the
  band (a block is rarely wide enough for it), and a click on a block goes to its start.
- ``PlayheadTable``: a tab holding one table read **at the playhead**: one row per joint (or per anything), each cell a
  constant, a sampled series (the value at the playhead) or ``Changes`` (a value that holds from each change to the
  next: a mode, a command, the condition being waited on).
- ``TimeTable``: a tab of **time-stamped rows** (a command log). The newest row at or before the playhead is marked,
  later rows are dim, a click goes to the row's time. With ``level`` it is an outline that folds (a step, the calls in
  it, the primitives of each call); with ``kind`` it gets filter chips.

WHY in traj_compare (Zach, 2026-11-27, on the JointCommandSequence viewer: "I agree we should grow it out of Trajectory
Comparison ... Ideally we reduce as much code duplication as possible"): the first sequence viewer re-drew the 3D, the
plots and the time control to add these three; here they are the only new part, and the next recorded procedure (a
recovery's controller steps were a numbered ``Signal`` until now) gets them for free.

Text is the caller's, shown as given (truthful rendering): a long cell wraps, it is never cut. Times are seconds on the
comparison's clock; numbers are shown in the unit the caller names, so convert angles to degrees before handing them over.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

TONES = ("", "positive", "warning", "danger", "muted", "accent")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "panel"


def _time(value: Any, what: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{what} must be a finite time in seconds, got {value!r}")
    return value


def _tone(value: str, what: str) -> str:
    if value not in TONES:
        raise ValueError(f"{what}: unknown tone {value!r}; tones: {TONES[1:]}")
    return value


def _number(value: Any) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


# ── the step band ──────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StepSpan:
    """One block of a ``StepTrack``: from ``start`` to ``end`` (s) the run was on ``label``.

    ``detail`` is the longer text written under the band while the playhead is on the block. ``kind`` names what sort
    of block it is (``"Command"``, ``"Condition"``); blocks of one kind share a colour and the band's legend lists the
    kinds. ``color`` (``#rrggbb``) overrides that colour. ``tone`` marks a block that went wrong (``TONES``)."""

    start: float
    end: float
    label: str
    detail: str = ""
    kind: str = ""
    color: str = ""
    tone: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _time(self.start, f"span {self.label!r} start"))
        object.__setattr__(self, "end", _time(self.end, f"span {self.label!r} end"))
        if self.end < self.start:
            raise ValueError(f"span {self.label!r} ends ({self.end}) before it starts ({self.start})")
        if self.color and not re.fullmatch(r"#[0-9a-fA-F]{6}", self.color):
            raise ValueError(f"span {self.label!r}: color is #rrggbb, got {self.color!r}")
        _tone(self.tone, f"span {self.label!r}")

    def to_payload(self) -> dict[str, Any]:
        return {"t0": self.start, "t1": self.end, "label": str(self.label), "detail": str(self.detail),
                "kind": str(self.kind), "color": self.color, "tone": self.tone}


@dataclass
class StepTrack:
    """One row of the step band: ``title`` names it (``"Recipe"``), ``words`` says what it is in a few plain words
    (``"as written"``), ``spans`` are its blocks in time order. ``mono`` draws the labels in a monospace face (code).

    A span of zero length (an instant: a command that never waits) is drawn as a tick at its time."""

    title: str
    spans: Sequence[StepSpan]
    words: str = ""
    mono: bool = False

    def __post_init__(self) -> None:
        self.spans = list(self.spans)
        for span in self.spans:
            if not isinstance(span, StepSpan):
                raise TypeError(f"step track {self.title!r}: {type(span).__name__} is not a StepSpan")
        starts = [span.start for span in self.spans]
        if starts != sorted(starts):
            raise ValueError(f"step track {self.title!r}: its spans are not in time order")

    def to_payload(self) -> dict[str, Any]:
        return {"title": str(self.title), "words": str(self.words), "mono": bool(self.mono),
                "spans": [span.to_payload() for span in self.spans]}


# ── the table at the playhead ──────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Changes:
    """A cell whose value holds from each change to the next: ``rows`` are ``(t, value)`` or ``(t, value, tone)``,
    in time order. Before the first change the cell is empty. ``value`` is text or a number."""

    rows: Sequence[Sequence[Any]]

    def __post_init__(self) -> None:
        rows = []
        for row in self.rows:
            if isinstance(row, (str, bytes)) or len(row) not in (2, 3):
                raise ValueError(f"a change is (t, value) or (t, value, tone), got {row!r}")
            value = row[1]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = _number(value)
            elif value is not None:
                value = str(value)
            rows.append([_time(row[0], "a change's time"), value, _tone(row[2] if len(row) == 3 else "", "a change")])
        if [row[0] for row in rows] != sorted(row[0] for row in rows):
            raise ValueError("changes are not in time order")
        object.__setattr__(self, "rows", rows)


@dataclass
class PlayheadColumn:
    """One column of a ``PlayheadTable``: ``cells`` holds one entry per table row, each a constant (text or a number),
    a sampled series (one value per ``PlayheadTable.t``; the cell shows the newest sample at or before the playhead) or
    ``Changes``.

    ``group`` puts neighbouring columns under one heading (``"Command being sent"``). ``unit`` is shown in the column
    heading; numbers are written with ``decimals`` places and a sign when ``signed``. ``mono`` is for code."""

    title: str
    cells: Sequence[Any]
    group: str = ""
    unit: str = ""
    decimals: int = 2
    signed: bool = False
    mono: bool = False
    words: str = ""

    def to_payload(self, samples: int | None, rows: int, table: str) -> dict[str, Any]:
        cells = list(self.cells)
        if len(cells) != rows:
            raise ValueError(f"{table}: column {self.title!r} has {len(cells)} cells for {rows} rows")
        out = []
        for index, cell in enumerate(cells):
            if isinstance(cell, Changes):
                out.append({"k": cell.rows})
            elif isinstance(cell, (str, bytes)) or cell is None:
                out.append({"c": "" if cell is None else str(cell)})
            elif np.ndim(cell) == 0:
                out.append({"c": _number(cell)})
            else:
                values = np.asarray(cell, dtype=float).reshape(-1)
                if samples is None or len(values) != samples:
                    raise ValueError(f"{table}: column {self.title!r} row {index} has {len(values)} samples; a sampled "
                                     f"cell needs one per PlayheadTable.t ({samples})")
                digits = max(int(self.decimals), 0) + 2
                out.append({"s": [None if not math.isfinite(v) else round(float(v), digits) for v in values]})
        return {"title": str(self.title), "group": str(self.group), "unit": str(self.unit), "decimals": int(self.decimals),
                "signed": bool(self.signed), "mono": bool(self.mono), "words": str(self.words), "cells": out}


@dataclass
class PlayheadTable:
    """A tab holding one table read at the playhead: ``rows`` are the row headings (joint names), ``columns`` its
    ``PlayheadColumn``s, ``t`` the clock (s) of every sampled cell. ``title`` is the tab's title, ``heading`` the line
    inside it, ``row_title`` the heading of the first column, ``description`` a note under the table."""

    title: str
    rows: Sequence[str]
    columns: Sequence[PlayheadColumn]
    t: Any = None
    heading: str = ""
    description: str = ""
    row_title: str = "Joint"
    id: str = ""

    def __post_init__(self) -> None:
        self.rows = [str(row) for row in self.rows]
        self.columns = list(self.columns)
        if not self.rows or not self.columns:
            raise ValueError(f"playhead table {self.title!r} needs at least one row and one column")
        self.id = self.id or _slug(self.title)

    def to_payload(self) -> dict[str, Any]:
        t = None if self.t is None else np.asarray(self.t, dtype=float).reshape(-1)
        if t is not None and (not np.all(np.isfinite(t)) or np.any(np.diff(t) < 0)):
            raise ValueError(f"playhead table {self.title!r}: t must be finite and not go backwards")
        samples = None if t is None else len(t)
        what = f"playhead table {self.title!r}"
        return {"kind": "playhead", "id": self.id, "title": str(self.title), "heading": str(self.heading or self.title),
                "description": str(self.description), "row_title": str(self.row_title), "rows": list(self.rows),
                "t": None if t is None else [float(v) for v in t],
                "columns": [column.to_payload(samples, len(self.rows), what) for column in self.columns]}


# ── the table of time-stamped rows ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimeRow:
    """One row of a ``TimeTable``: at ``t`` (s), these ``cells`` (one per column). ``end`` is when it stops being the
    current row (None: when the next row of its level starts). ``level`` > 0 folds the row under the nearest row above
    it of a lower level. ``kind`` is its filter chip; ``tone`` marks it (``TONES``).

    ``t=math.inf`` is a row that never happened (a step the run did not reach): its time reads "—", it is always
    drawn as still to come, and a click on it goes nowhere."""

    t: float
    cells: Sequence[str]
    end: float | None = None
    level: int = 0
    kind: str = ""
    tone: str = ""

    def __post_init__(self) -> None:
        if not (isinstance(self.t, float) and self.t == math.inf):
            object.__setattr__(self, "t", _time(self.t, "a time row's t"))
        if self.end is not None:
            object.__setattr__(self, "end", _time(self.end, "a time row's end"))
        object.__setattr__(self, "cells", [str(cell) for cell in self.cells])
        if self.level < 0:
            raise ValueError(f"a time row's level is 0 or more, got {self.level}")
        _tone(self.tone, "a time row")


@dataclass
class TimeTable:
    """A tab of time-stamped rows (``columns`` are the headings after the leading time column).

    ``kinds`` maps a row's ``kind`` to its chip's label, in chip order (a kind left out gets no chip and is always
    shown). ``mono`` names the columns drawn in a monospace face. ``open_level``: rows deeper than this start folded
    (0 shows only the top rows; the default shows everything). ``title`` is the tab's title, ``heading`` the line
    inside it."""

    title: str
    columns: Sequence[str]
    rows: Sequence[TimeRow]
    heading: str = ""
    description: str = ""
    kinds: Mapping[str, str] = field(default_factory=dict)
    mono: Sequence[str] = ()
    open_level: int = 99
    id: str = ""

    def __post_init__(self) -> None:
        self.columns = [str(column) for column in self.columns]
        self.rows = list(self.rows)
        if not self.columns:
            raise ValueError(f"time table {self.title!r} needs at least one column")
        for row in self.rows:
            if not isinstance(row, TimeRow):
                raise TypeError(f"time table {self.title!r}: {type(row).__name__} is not a TimeRow")
            if len(row.cells) != len(self.columns):
                raise ValueError(f"time table {self.title!r}: a row has {len(row.cells)} cells; expected {len(self.columns)}")
        unknown = [name for name in self.mono if name not in self.columns]
        if unknown:
            raise ValueError(f"time table {self.title!r}: mono names unknown columns {unknown}")
        self.id = self.id or _slug(self.title)

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "times", "id": self.id, "title": str(self.title), "heading": str(self.heading or self.title),
                "description": str(self.description), "columns": list(self.columns),
                "kinds": [[str(key), str(label)] for key, label in self.kinds.items()],
                "mono": [self.columns.index(name) for name in self.mono], "open_level": int(self.open_level),
                "rows": [{"t": None if row.t == math.inf else row.t, "end": row.end, "cells": list(row.cells),
                          "level": int(row.level),
                          "kind": str(row.kind), "tone": row.tone} for row in self.rows]}


Panel = StepTrack | PlayheadTable | TimeTable


def panels_payload(panels: Sequence[Any]) -> dict[str, Any] | None:
    """``Comparison.panels`` as the payload's ``panels``: ``{"tracks": [...], "tabs": [...]}``, or None without any.

    The tabs keep the caller's order and lead the question tabs (``tabs.tabs_for``); two tabs may not share an id."""

    panels = list(panels or ())
    if not panels:
        return None
    tracks, tabs = [], []
    for panel in panels:
        if isinstance(panel, StepTrack):
            tracks.append(panel.to_payload())
        elif isinstance(panel, (PlayheadTable, TimeTable)):
            tabs.append(panel.to_payload())
        else:
            raise TypeError(f"a panel is a StepTrack, a PlayheadTable or a TimeTable, got {type(panel).__name__}")
    ids = [tab["id"] for tab in tabs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"panel tabs need distinct ids (or titles), got {ids}")
    return {"tracks": tracks, "tabs": tabs}
