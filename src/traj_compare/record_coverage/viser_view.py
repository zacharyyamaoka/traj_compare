"""Viser view of a record-coverage payload ("traj_compare.record_coverage/1"): the records' 3-D field triple as points
in their declared box, through the house viewer (viser_3d_viewer).

    from traj_compare.record_coverage.viser_view import serve_records
    viewer = serve_records(payload, port=0)     # non-blocking; prints READY http://127.0.0.1:<port>/
    ...
    viewer.stop()

    cd ~/traj_compare && .venv/bin/python -m traj_compare.record_coverage.viser_view <coverage.json> --port 0

Reads ONLY the payload's `points3d` block (docs/RECORD_COVERAGE.md "The other viewers"): one point per record (at most
20 000, evenly picked by the analysis), coloured by `color_by` (one colour per class, in GROUP_COLORS order; a record
missing the class is grey), inside the box of the three fields' declared ranges (the limit colour). Without
`points3d` it refuses: there is nothing 3-D to draw.

WHY metres or [0, 1]: when the three fields are lengths (m or mm) the box is drawn to scale in metres, so a 0.8 m x
0.6 m x 0.4 m workspace looks like one; three fields of different kinds (an angle, a width, a force) have no common
scale, so each axis's [low, high] becomes [0, 1] and the panel says so, rather than drawing one axis 1000x longer.
WHY points: viser draws point clouds in exact sRGB (meshes and lines go through tone mapping), so a point matches the
legend's swatch and the PNGs' group colour (coverage/viser_view.py measured it).
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..coverage.matplotlib_view import BARS, GROUP_COLORS, LIMIT_COLOR, MUTED
from ..coverage.viser_view import _bar, _box_segments, _swatch
from .analysis import SCHEMA

TO_METRES = {"m": 1.0, "mm": 0.001}
LIMIT_RGB = (180, 68, 47)  # LIMIT_COLOR #b4442f
HAIR_RGB = (200, 200, 206)
MISSING_RGB = (110, 110, 115)  # MUTED: a record without a class; darker than GROUP_COLORS' own grey #bbbbbb
POINT_SIZE_PCT = 1.0  # a point's size as a share of the box's longest side
HOME_DIRECTION = (1.0, -1.8, 0.85)  # front-right, a little above (Fusion's side), never the exact cube diagonal


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    value = hex_colour.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _css(rgb: Sequence[int]) -> str:
    return "rgb({},{},{})".format(*(int(c) for c in rgb))


def _value_text(value: float, unit: str | None) -> str:
    text = f"{value:.3g}".replace("-", "−")
    if not unit:
        return text
    return f"{text}{unit}" if unit == "°" else f"{text} {unit}"


def check_payload(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema != SCHEMA:
        raise ValueError(f"not a record_coverage payload ({SCHEMA}): schema {schema!r}")
    if payload.get("points3d") is None:
        raise ValueError("this payload has no 3-D fields (points3d is null): pass xyz= to analyze() with three number "
                         "fields, or give the records a 3-vector field")


class RecordsViewer:
    """The scene and panel of one payload's `points3d` on a viser_3d_viewer `Viewer` (kept as `viewer.records`).

    `points` (N x 3, as drawn: metres or [0, 1] per axis), `colors` (N x 3 uint8), `legend_html` (the panel's legend:
    every level drawn, with its swatch), `low` / `high` (the box as drawn), `metric` (True = metres)."""

    def __init__(self, viewer: Any, payload: Mapping[str, Any]) -> None:
        self.viewer = viewer
        self.server = viewer.server
        self.payload = payload
        block = payload["points3d"]
        self.fields = [str(name) for name in block["fields"]]
        rows = {row["name"]: row for row in payload.get("fields") or []}
        self.units = [(rows.get(name) or {}).get("unit") for name in self.fields]
        self.displays = [(rows.get(name) or {}).get("display") or {"scale": 1.0, "unit": unit}
                         for name, unit in zip(self.fields, self.units, strict=True)]
        self.sources = [str(source) for source in block.get("source") or ["declared"] * 3]
        raw = np.asarray(block["points"], float).reshape(-1, 3)
        low, high = np.asarray(block["low"], float), np.asarray(block["high"], float)
        self.raw_low, self.raw_high = low, high
        self.metric = all(unit in TO_METRES for unit in self.units)
        if self.metric:
            factor = np.asarray([TO_METRES[unit] for unit in self.units])
            self.points, self.low, self.high = raw * factor, low * factor, high * factor
        else:
            span = np.where(high > low, high - low, 1.0)
            self.points, self.low, self.high = (raw - low) / span, np.zeros(3), np.ones(3)
        self.beyond = int(np.count_nonzero(((self.points < self.low - 1e-12) | (self.points > self.high + 1e-12))
                                           .any(axis=1))) if len(self.points) else 0
        self.color_by = block.get("color_by")
        self.levels = [str(level) for level in block.get("levels") or []]
        codes = np.asarray(block.get("codes") or [], int)
        self.codes = codes if len(codes) == len(self.points) else np.full(len(self.points), -1, int)
        self.palette = self._palette()
        self.colors = np.asarray([self.palette[int(code)] for code in self.codes], np.uint8).reshape(-1, 3)
        self.extent = float(np.max(self.high - self.low)) or 1.0
        self.legend_html = self._legend_html()
        self._build_gui()
        self._build_scene()
        bounds = self.bounds()
        # WHY off the exact diagonal: from (1, -1, 1) a cube's far vertical edge hides behind its near corner
        self.viewer.camera.fit_home(*bounds, direction=HOME_DIRECTION, aspect=0.8)
        self.viewer.camera.fit(*bounds, direction=HOME_DIRECTION)

    # ── colours ──────────────────────────────────────────────────────────────────────────────────────────────────────
    def _palette(self) -> dict[int, tuple[int, int, int]]:
        """code -> RGB. WHY the PNGs' group order first: when the points are coloured by the group_by field, a level
        gets the colour its bars have in numbers.png / classes.png (GROUP_COLORS indexed by source.groups)."""
        if not self.color_by:
            return {-1: _rgb(BARS)}
        palette: dict[int, tuple[int, int, int]] = {-1: MISSING_RGB}
        source = self.payload.get("source") or {}
        groups = [str(g) for g in source.get("groups") or []] if self.color_by == source.get("group_by") else []
        used = 0
        for index, group in enumerate(groups):
            if group in self.levels:
                palette[self.levels.index(group)] = _rgb(GROUP_COLORS[index % len(GROUP_COLORS)])
                used = max(used, index + 1)
        for code in sorted(set(self.codes.tolist()) - {-1} - set(palette)):
            palette[code] = _rgb(GROUP_COLORS[used % len(GROUP_COLORS)])
            used += 1
        return palette

    # ── GUI ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _build_gui(self) -> None:
        gui = self.server.gui
        source = self.payload.get("source") or {}
        self.status = self.viewer.add_status("Records")
        self.status.set(**{"data": self.payload.get("title") or "records",
                           "drawn": f"{len(self.points)} of {int(source.get('records', len(self.points)))} records",
                           "beyond the box": self.beyond or None})
        self.legend = gui.add_html(self.legend_html)
        self.point_size = gui.add_slider("Point size (% of the box)", min=0.2, max=4.0, step=0.1,
                                         initial_value=POINT_SIZE_PCT)
        self.point_size.on_update(lambda _event: self._resize_points())
        self.viewer.camera.add_gui(bounds=self.bounds)

    def _legend_html(self) -> str:
        counts = {code: int(np.count_nonzero(self.codes == code)) for code in self.palette}
        rows = []
        if self.color_by:
            title = f"colour = {html.escape(self.color_by)}"
            for code, rgb in self.palette.items():
                if code < 0 or not counts.get(code):
                    continue
                rows.append(f"{_swatch(_css(rgb))}{html.escape(self.levels[code])} · {counts[code]}")
            if counts.get(-1):
                rows.append(f"{_swatch(_css(MISSING_RGB))}({html.escape(self.color_by)} missing) · {counts[-1]}")
            absent = [level for code, level in enumerate(self.levels) if not counts.get(code)]
            if absent:
                rows.append(f'<span style="color:{MUTED}">no point: {html.escape(", ".join(absent))}</span>')
        else:
            title = "one colour: no category field to colour by"
            rows.append(f"{_swatch(_css(self.palette[-1]))}a record · {len(self.points)}")
        stated = all(source != "data" for source in self.sources)
        names = " × ".join(html.escape(name) for name in self.fields)
        if stated:
            rows.append(f"{_bar(f'solid {LIMIT_COLOR}')}red box = the stated ranges of {names}")
        else:
            missing = ", ".join(html.escape(n) for n, s in zip(self.fields, self.sources, strict=True) if s == "data")
            rows.append(f"{_bar('solid rgb(200,200,206)')}grey box = the ranges ({missing}: no range stated, its "
                        "data span)")
        for axis, name in enumerate(self.fields):
            display = self.displays[axis]
            scale, unit = float(display.get("scale") or 1.0), display.get("unit")
            rows.append(f'<span style="color:{MUTED}">{"xyz"[axis]} = {html.escape(name)}: '
                        f"{_value_text(self.raw_low[axis] * scale, unit)} … "
                        f"{_value_text(self.raw_high[axis] * scale, unit)}</span>")
        if self.metric:
            note = "drawn to scale, in metres"
        else:
            units = ", ".join(unit or "no unit" for unit in self.units)
            note = (f"axes normalised: each field's [low, high] is drawn as [0, 1], because the three fields do not "
                    f"share a length unit ({html.escape(units)})")
        if self.beyond:
            note += f" · {self.beyond} point{'' if self.beyond == 1 else 's'} beyond the box"
        body = "".join(f'<div style="margin-top:3px">{row}</div>' for row in rows)
        return (f'<div style="font-size:12px;line-height:1.35;padding:2px 12px 8px;color:#3a3a3e">'
                f'<div style="font-weight:600">{title}</div>{body}'
                f'<div style="margin-top:5px;font-size:11px;color:{MUTED}">{note}</div></div>')

    # ── scene ────────────────────────────────────────────────────────────────────────────────────────────────────────
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        pad = 0.08 * self.extent
        low = np.minimum(self.low, self.points.min(axis=0)) if len(self.points) else self.low
        high = np.maximum(self.high, self.points.max(axis=0)) if len(self.points) else self.high
        return tuple(float(v) for v in low - pad), tuple(float(v) for v in high + pad)

    def _size(self) -> float:
        return float(self.point_size.value) / 100.0 * self.extent

    def _build_scene(self) -> None:
        scene = self.server.scene
        self.cloud = scene.add_point_cloud("/records/points", self.points.astype(np.float32), self.colors,
                                           point_size=self._size(), point_shape="circle", point_shading="flat",
                                           precision="float32")
        stated = all(source != "data" for source in self.sources)
        scene.add_line_segments("/records/box", _box_segments(self.low, self.high).astype(np.float32),
                                LIMIT_RGB if stated else HAIR_RGB, thickness=2.0, thickness_units="screen")
        # one label per axis, mid-edge (x front-bottom, y right-bottom, z front-left), carrying its range. WHY not a
        # value at each end: the three edges meet in pairs at the box's corners, so end labels collided there.
        offset = 0.07 * self.extent
        low, high = self.low, self.high
        anchors = {0: np.array([np.nan, low[1] - offset, low[2]]), 1: np.array([high[0] + offset, np.nan, low[2]]),
                   2: np.array([low[0] - offset, low[1] - offset, np.nan])}
        for axis, name in enumerate(self.fields):
            display = self.displays[axis]
            scale, unit = float(display.get("scale") or 1.0), display.get("unit")
            at = anchors[axis].copy()
            at[axis] = (low[axis] + high[axis]) / 2
            text = (f"{'xyz'[axis]}: {name}  {_value_text(self.raw_low[axis] * scale, unit)} → "
                    f"{_value_text(self.raw_high[axis] * scale, unit)}")
            scene.add_label(f"/records/labels/{'xyz'[axis]}", text, position=at, anchor="center-center",
                            font_screen_scale=0.8)

    def _resize_points(self) -> None:
        self.cloud.point_size = self._size()


def serve_records(payload: Mapping[str, Any], *, port: int = 0, title: str | None = None) -> Any:
    """Start the records viewer (non-blocking) and print `READY <url>`; returns the viser_3d_viewer `Viewer`.

    `viewer.records` is the `RecordsViewer`; stop with `viewer.stop()`."""
    check_payload(payload)
    from viser_3d_viewer import Viewer, ViewerConfig

    # WHY light, no grid: the PNGs and the page are light (white = empty), and the declared box is the frame here; a
    # floor grid at z = 0 would cut through a box that spans it.
    viewer = Viewer(ViewerConfig(title=title or payload.get("title") or "Record coverage", port=port, dark_mode=False,
                                 grid=False))
    try:
        viewer.records = RecordsViewer(viewer, payload)
    except BaseException:
        viewer.stop()
        raise
    viewer.print_ready()
    return viewer


def main(argv: Sequence[str] | None = None, serve: Callable[..., Any] = serve_records) -> None:
    parser = argparse.ArgumentParser(description="Serve a record coverage.json (traj_compare.record_coverage/1) in the "
                                                 "house 3-D viewer until Ctrl-C.")
    parser.add_argument("coverage_json", type=Path, help="the payload written by analyze() / python -m "
                                                         "traj_compare.record_coverage")
    parser.add_argument("--port", type=int, default=0, help="0 = the OS picks (printed on the READY line)")
    parser.add_argument("--title", default=None)
    args = parser.parse_args(argv)
    payload = json.loads(args.coverage_json.read_text("utf-8"))
    viewer = serve(payload, port=args.port, title=args.title)
    viewer.serve_forever()


if __name__ == "__main__":
    main()
