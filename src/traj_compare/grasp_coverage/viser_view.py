"""Viser view of a grasp-coverage payload ("traj_compare.grasp_coverage/1"): the grasps in 3-D, through viser_3d_viewer.

    from traj_compare.grasp_coverage.viser_view import serve_grasp_coverage
    viewer = serve_grasp_coverage(payload, port=0)     # non-blocking; prints READY http://127.0.0.1:<port>/
    ...
    viewer.stop()

    /home/bam/traj_compare/.venv/bin/python -m traj_compare.grasp_coverage.viser_view <grasp_coverage.json> --port 0

Views ("View" dropdown): **Grasps in 3-D** (robot_msgs' two-finger glyph at every grasp — jaws along the tool x, the
approach along +z, the stem back where the wrist comes from — coloured by outcome, a checkbox per outcome, the offered
area as red boxes) and **Approach sphere** (the approach on the equal-area sphere, coloured by count, the trajectory
viewer's sphere drawing). Reads ONLY the payload. Colours: outcome colours from the Matplotlib view (the Nov 19
gallery's), the count ramp from `coverage.matplotlib_view` (= assets/coverage_color.js).

WHY a centre dot beside the glyph lines: viser draws lines through three.js tone mapping, which washes a colour out;
point clouds keep the exact sRGB (measured on the trajectory viewer, coverage/viser_view.py), so the dot carries the
outcome's true colour and the glyph its shape.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..coverage.matplotlib_view import COLORMAP_NAMES, SCALES, ramp_rgb, scale_counts
from ..coverage.viser_view import (
    HAIR_RGB,
    INK_RGB,
    LIMIT_RGB,
    _box_segments,
    _gradient_css,
    _swatch,
    sphere_cell_points,
    sphere_grid_segments,
)
from .analysis import SCHEMA, gripper_polylines
from .matplotlib_view import outcome_colours

GRASPS, SPHERE = "Grasps in 3-D", "Approach sphere"
VIEWS = (GRASPS, SPHERE)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def glyph_segments(rows: Sequence[Mapping[str, Any]], size: float = 1.0) -> np.ndarray:
    """robot_msgs' two-finger glyph per grasp row as four segments (4 * n, 2, 3) float32: the two jaws, the palm and the
    stem. The shape is analysis.gripper_polylines' (one definition for every viewer); a segment list drops the polyline's
    retraced stem."""
    lines = gripper_polylines(rows, size)
    if not len(lines):
        return np.zeros((0, 2, 3), np.float32)
    pairs = ((0, 1), (1, 5), (2, 3), (5, 6))  # jaw, palm, stem, jaw
    return np.stack([lines[:, [a, b]] for a, b in pairs], axis=1).reshape(-1, 2, 3).astype(np.float32)


class GraspCoverageViewer:
    """The GUI and scene of one grasp-coverage payload on a viser_3d_viewer `Viewer` (kept as `viewer.grasp_coverage`)."""

    def __init__(self, viewer: Any, payload: Mapping[str, Any]) -> None:
        self.viewer = viewer
        self.server = viewer.server
        self.payload = payload
        self.order = list(payload["outcomes"]["order"])
        self.colours_of = outcome_colours(payload)
        self.numbers = {entry["key"]: float(entry["value"]) for entry in payload.get("numbers", [])}
        self.frames: dict[str, Any] = {}
        self.bounds = ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
        self._build_gui()
        self._build_scene()
        self.show(GRASPS)

    # ── GUI ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _build_gui(self) -> None:
        gui = self.server.gui
        source = self.payload["source"]
        self.status = self.viewer.add_status("Grasp coverage")
        rows: dict[str, Any] = {"data": self.payload.get("title") or "grasps", "grasps": int(source["grasps"]),
                                "objects": len(source["objects"])}
        if "picked_pct" in self.numbers:
            rows["picked"] = f"{self.numbers['picked_pct']:.0f} % of {int(self.numbers.get('closed', 0))} closed"
        rows["directions"] = f"{self.numbers.get('directions_visited_pct', 0):.0f} % of sphere cells"
        self.status.set(**rows)
        self.view = gui.add_dropdown("View", VIEWS, initial_value=GRASPS, hint="The grasps where they are, or where "
                                                                               "they approach from on a sphere")
        self.shown = {}
        counts = self.payload["outcomes"]["counts"]
        with gui.add_folder("Outcomes"):
            for name in self.order:
                self.shown[name] = gui.add_checkbox(f"{name} ({counts[name]})", initial_value=True,
                                                    hint=self.payload["outcomes"]["words"][name])
        self.size = gui.add_slider("Gripper size", min=0.2, max=1.5, step=0.05, initial_value=1.0,
                                   hint="1 = the real size of robot_msgs' glyph (40 mm fingers)")
        # WHY these labels: BAM Reach's (robot_reach viewer.py) and the trajectory viewer's, one switch everywhere
        self.colours = gui.add_dropdown("Colours", COLORMAP_NAMES, initial_value="viridis",
                                        hint="The sphere's count colours; empty is always white")
        self.reverse = gui.add_checkbox("Reverse (high = dark)", initial_value=False)
        self.scale = gui.add_dropdown("Scale", SCALES, initial_value="linear",
                                      hint="linear clips at p98; equalized colours by rank (where, not how much)")
        self.legend = gui.add_html("")
        self.viewer.camera.add_gui(bounds=lambda: self.bounds)
        self.view.on_update(lambda _event: self.show(str(self.view.value)))
        for name, box in self.shown.items():
            box.on_update(lambda _event, name=name: self._toggle(name))
        self.size.on_update(lambda _event: self._paint_grasps())
        for control in (self.colours, self.reverse, self.scale):
            control.on_update(lambda _event: self._paint_sphere())

    # ── scene ────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _build_scene(self) -> None:
        scene = self.server.scene
        self.frames["grasps"] = scene.add_frame("/grasps", show_axes=False)
        self.frames["sphere"] = scene.add_frame("/sphere", show_axes=False, visible=False)
        position = self.payload["position"]
        low, high = (np.asarray(corner, float) for corner in position["bounds"])
        area = position["area"] or []
        # WHY the outer box, not a box per area: a campaign offers one look area per run (174 on the repicks), and their
        # boxes buried the grasps (headless review 2026-11-24); the PNGs draw their union. WHY always a node: the area is
        # a fixed part of the view (empty when no area was offered), so a toggle or a test finds it by name
        segments = (_box_segments(np.min([lo for lo, _ in area], axis=0), np.max([hi for _, hi in area], axis=0))
                    if area else np.zeros((0, 2, 3)))
        scene.add_line_segments("/grasps/area", np.asarray(segments, np.float32), LIMIT_RGB, thickness=1.6,
                                thickness_units="screen")
        scene.add_line_segments("/grasps/bounds", _box_segments(low, high), HAIR_RGB, thickness=1.0,
                                thickness_units="screen")
        self._paint_grasps()
        scene.add_line_segments("/sphere/grid", sphere_grid_segments(self.payload["orientation"]["sphere"]["rings"],
                                                                     self.payload["orientation"]["sphere"]["sectors"]),
                                HAIR_RGB, thickness=1.0, thickness_units="screen")
        reference = np.asarray(self.payload["orientation"]["reference"], float)
        scene.add_line_segments("/sphere/reference", np.array([[reference, reference * 1.35]], np.float32), INK_RGB,
                                thickness=3.0, thickness_units="screen")
        scene.add_label("/sphere/reference_label", "straight down: tilt 0°", position=reference * 1.42,
                        anchor="center-center", font_screen_scale=0.85)
        for name, at in (("+x", (1.45, 0, 0)), ("+y", (0, 1.45, 0)), ("+z (up)", (0, 0, 1.3)), ("−x", (-1.45, 0, 0)),
                         ("−y", (0, -1.45, 0))):
            scene.add_label(f"/sphere/axis {name}", name, position=at, anchor="center-center", font_screen_scale=0.85)
        self._paint_sphere()

    def _paint_grasps(self) -> None:
        scene = self.server.scene
        size = float(self.size.value)
        rows = self.payload["grasps"]
        for name in self.order:
            mine = [row for row in rows if row["outcome"] == name]
            colour = _rgb(self.colours_of[name])
            scene.add_line_segments(f"/grasps/{name}/jaws", glyph_segments(mine, size), colour, thickness=2.0,
                                    thickness_units="screen", visible=bool(self.shown[name].value))
            centres = np.asarray([row["position"] for row in mine], np.float32).reshape(-1, 3)
            scene.add_point_cloud(f"/grasps/{name}/centres", centres, np.tile(np.uint8(colour), (len(centres), 1)),
                                  point_size=0.0025, point_shape="circle", point_shading="flat",
                                  visible=bool(self.shown[name].value))

    def _sphere_scaled(self):
        sphere = self.payload["orientation"]["sphere"]
        counts = np.asarray(sphere["counts"], float).reshape(sphere["rings"], sphere["sectors"])
        return scale_counts(counts, str(self.scale.value), enough=int(self.payload.get("enough", 10)))

    def _paint_sphere(self) -> None:
        scaled = self._sphere_scaled()
        self.sphere_scale = scaled
        ramp = ramp_rgb(np.clip(scaled.t, 0, 1), str(self.colours.value), bool(self.reverse.value))
        colours = np.where((scaled.t >= 0)[..., None], ramp, np.uint8(246))
        points, point_colours = sphere_cell_points(colours)
        self.server.scene.add_point_cloud("/sphere/cells", points, point_colours, point_size=0.012,
                                          point_shape="square", point_shading="flat", precision="float32")
        self.legend.content = self._legend_html()

    def _toggle(self, name: str) -> None:
        nodes = self.server.scene._handle_from_node_name  # viser 1.1: every live node by name
        for part in ("jaws", "centres"):
            node = nodes.get(f"/grasps/{name}/{part}")
            if node is not None:
                node.visible = bool(self.shown[name].value)

    # ── switching ────────────────────────────────────────────────────────────────────────────────────────────────────
    def show(self, view: str) -> None:
        if view not in VIEWS:
            raise ValueError(f"view {view!r}: expected one of {', '.join(VIEWS)}")
        if self.view.value != view:
            self.view.value = view  # on_update runs show(view) again; the second call does the work
            return
        self.frames["grasps"].visible = view == GRASPS
        self.frames["sphere"].visible = view == SPHERE
        self.viewer.grid.visible = view == GRASPS
        if view == GRASPS:
            low, high = self.payload["position"]["bounds"]
            self.bounds = (tuple(float(v) for v in low), tuple(float(v) for v in high))
            direction = (1.0, -1.3, 0.9)
        else:
            self.bounds = ((-1.1, -1.1, -1.1), (1.1, 1.1, 1.1))
            # WHY from below: a grasp from above points its approach (+z) down, so a pick set fills the bottom cap; a
            # camera level with the equator showed a white sphere (headless review 2026-11-24)
            direction = (0.5, -0.7, -1.1)
        self.viewer.camera.fit_home(*self.bounds, direction=direction, aspect=0.8)
        self.viewer.camera.fit(*self.bounds, direction=direction)
        self.legend.content = self._legend_html()

    def _legend_html(self) -> str:
        if str(self.view.value) == GRASPS:
            rows = "".join(f'<div style="margin-top:3px">{_swatch(self.colours_of[name])}{name}: '
                           f'{self.payload["outcomes"]["words"][name]}</div>' for name in self.order)
            return ('<div style="font-size:12px;line-height:1.35;padding:2px 12px 8px;color:#3a3a3e">'
                    '<div style="font-weight:600">a glyph per grasp: two jaws, the palm, the stem back along the '
                    'approach</div>' + rows +
                    f'<div style="margin-top:3px">{_swatch("#b4442f")}red box = around the offered pick areas</div></div>')
        scaled = getattr(self, "sphere_scale", None)
        ticks = scaled.ticks if scaled is not None else ()
        tick_html = "".join(f'<span style="position:absolute;left:{100 * t:.1f}%;transform:translateX(-{100 * t:.0f}%);'
                            f'white-space:nowrap">{label}</span>' for t, label in ticks)
        return ('<div style="font-size:12px;line-height:1.35;padding:2px 12px 8px;color:#3a3a3e">'
                '<div style="font-weight:600">colour = grasps per equal-area direction cell</div>'
                f'<div style="height:11px;margin:4px 0 2px;border-radius:2px;background:linear-gradient(90deg,'
                f'{_gradient_css(str(self.colours.value), bool(self.reverse.value))})"></div>'
                f'<div style="position:relative;height:15px;font-size:11px;color:#6e6e73">{tick_html}</div>'
                + (f'<div style="font-size:11px;color:#6e6e73">{scaled.note}</div>' if scaled is not None else "")
                + f'<div style="margin-top:4px">{_swatch("#fff", border=True)}white = never approached from there</div>'
                '<div>black spike = straight down (tilt 0°)</div></div>')


def serve_grasp_coverage(payload: Mapping[str, Any], *, port: int = 0, title: str | None = None) -> Any:
    """Start the grasp viewer (non-blocking) and print `READY <url>`; returns the viser_3d_viewer `Viewer`.

    `viewer.grasp_coverage` is the `GraspCoverageViewer`; stop with `viewer.stop()`."""
    from viser_3d_viewer import Viewer, ViewerConfig

    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a grasp_coverage payload ({SCHEMA}): schema {payload.get('schema')!r}")
    low, high = (np.asarray(corner, float) for corner in payload["position"]["bounds"])
    grid = max(0.2, 2.0 * math.ceil(float(np.max(high - low)) * 5) / 5)
    # WHY light: empty is white everywhere else (Zach 2026-11-19, "so its clear that white means empty")
    viewer = Viewer(ViewerConfig(title=title or payload.get("title") or "Grasp coverage", port=port, dark_mode=False,
                                 grid_size=grid))
    try:
        viewer.grasp_coverage = GraspCoverageViewer(viewer, payload)
    except BaseException:
        viewer.stop()
        raise
    viewer.print_ready()
    return viewer


def main(argv: Sequence[str] | None = None, serve: Callable[..., Any] = serve_grasp_coverage) -> None:
    parser = argparse.ArgumentParser(description="Serve a grasp_coverage.json (traj_compare.grasp_coverage/1) in the "
                                                 "house 3-D viewer until Ctrl-C.")
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("--port", type=int, default=0, help="0 = the OS picks (printed on the READY line)")
    parser.add_argument("--title", default=None)
    args = parser.parse_args(argv)
    viewer = serve(json.loads(args.coverage_json.read_text("utf-8")), port=args.port, title=args.title)
    viewer.serve_forever()


if __name__ == "__main__":
    main()
