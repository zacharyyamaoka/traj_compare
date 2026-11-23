"""Viser view of a trajectory-coverage payload ("traj_compare.coverage/1"): the 3-D views, through viser_3d_viewer.

    from traj_compare.coverage.viser_view import serve_coverage
    viewer = serve_coverage(payload, port=0)     # non-blocking; prints READY http://127.0.0.1:<port>/
    ...
    viewer.stop()

    cd ~/traj_compare && .venv/bin/python -m traj_compare.coverage.viser_view <coverage.json> --port 0   # until Ctrl-C

Views ("View" dropdown): Voxels (tool positions in 5 cm cells, coloured by samples, a threshold slider, reachable but
unvisited cells as faint grey dots), Tool paths (every trajectory's TCP path), Tool directions sphere (the tool z axis
on an equal-area sphere) and the q-qd-qdd height map of one joint (floor = position x speed, height = the largest
|acceleration| reached in the cell, colour = samples). The first three need the payload's `tool` block.

Reads ONLY the payload (docs/COVERAGE.md "The other viewers"). Colours come from the same rule as the page and the
PNGs (`matplotlib_view.ramp_rgb` / `scale_counts`, the numpy mirror of assets/coverage_color.js). The house viewer
(viser_3d_viewer) gives loopback, an asserted port, no logo and the Fusion ViewCube.

WHY coloured cells are square POINTS, not boxes (measured on the Nov 19 coverage gallery, robot_metrics
docs/proposals/coverage-2026-11-19/tools_viser.py): viser draws meshes and lines through three.js tone mapping, which
washes a colormap out (#0d2f5c drew as #5e9bcb); point clouds draw the exact sRGB colour, so a cell matches its colour
bar. A point's on-screen width is twice `point_size` in world units, so a cell of width w gets `point_size = w / 2`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .matplotlib_view import (
    COLORMAP_NAMES,
    COLORMAPS,
    OUTSIDE_RGB,
    SCALE_TITLES,
    SCALES,
    Scaled,
    edges,
    joint_display,
    joint_names,
    ramp_rgb,
    scale_counts,
    signal_unit,
    tool_frame,
)

VOXELS, TOOL_PATHS, SPHERE, HEIGHT_MAP = "Voxels", "Tool paths", "Tool directions sphere", "q-qd-qdd height map"
TOOL_VIEWS = (VOXELS, TOOL_PATHS, SPHERE)
LIMIT_RGB = (180, 68, 47)  # #b4442f, coverage_color.js LIMIT
HAIR_RGB = (200, 200, 206)
INK_RGB = (29, 29, 31)
STEM_RGB = (214, 214, 220)
HEIGHT_MAP_WIDTH = 1.2  # scene units for the q axis; qd gets the same cell size, height 100 % = HEIGHT_MAP_TOP
HEIGHT_MAP_TOP = 0.5
SPHERE_SPACING = 0.015  # fill-point spacing on the unit sphere; a point draws 2 x 0.012 wide, so no gaps

ABOUT = {
    VOXELS: "Each dot is a 5 cm cube of the workspace the tool (TCP) passed through, coloured by how many samples "
            "fell in it. The slider hides cubes with fewer samples, so the busy core stands out. Faint grey dots "
            "are cubes the robot can reach but the data never visited (only when a reachable set was given). The "
            "axes at the origin are the tool frame's own (x red, y green, z blue): the robot base when the frame is "
            "'base', else the origin the frame names.",
    TOOL_PATHS: "Every trajectory's tool path in the tool frame (at most 400 points each, evenly picked), coloured by "
                "its place in the dataset: first dark, last bright. Bundles show the motions the data repeats; a "
                "region no line crosses is a region no trajectory teaches.",
    SPHERE: "The tool z axis drawn on a unit sphere, split into 12 x 24 cells of equal area (12 bands of equal height "
            "in z, 24 sectors of azimuth). White cells are directions the tool never pointed. The black spike marks "
            "the reference direction (tilt 0, by default straight down).",
    HEIGHT_MAP: "Floor: the joint's position (q) x speed (qd) plane, exactly its limits (red frame). Each visited "
                "cell is a tile lifted to the largest |acceleration| (qdd) reached in it, as a share of the qdd limit "
                "(red frame on top = 100 %), and coloured by samples. Tiles near the top frame are cells where the "
                "data already pushes acceleration; low tiles are cells only visited gently.",
}


def _numbers(payload: Mapping[str, Any]) -> dict[str, float]:
    return {entry["key"]: float(entry["value"]) for entry in payload.get("numbers", [])}


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    span = high - low
    if not span > 0:
        return [low]
    raw = span / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(factor for factor in (1, 2, 2.5, 5, 10) if factor * magnitude >= raw) * magnitude
    first = math.ceil(low / step - 1e-9) * step
    return [float(v) for v in np.arange(first, high + step * 1e-6, step)]


def _box_segments(low: np.ndarray, high: np.ndarray) -> np.ndarray:
    corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    pairs = [(a, b) for a in range(8) for b in range(a + 1, 8) if bin(a ^ b).count("1") == 1]
    return corners[np.array(pairs)]


def _rectangle(x0: float, x1: float, y0: float, y1: float, z: float, dashed: bool = False) -> np.ndarray:
    corners = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z], [x0, y0, z]])
    segments = np.stack([corners[:-1], corners[1:]], axis=1)
    if not dashed:
        return segments
    pieces = []
    for start, end in segments:
        steps = np.linspace(0.0, 1.0, 25)
        for a, b in zip(steps[0:-1:2], steps[1::2], strict=False):
            pieces.append([start + (end - start) * a, start + (end - start) * b])
    return np.asarray(pieces)


def _gradient_css(cmap: str, reverse: bool) -> str:
    stops = COLORMAPS[cmap][::-1] if reverse else COLORMAPS[cmap]
    return ", ".join(f"rgb({r},{g},{b})" for r, g, b in stops)


def _swatch(css: str, border: bool = False) -> str:
    edge = "border:1px solid #c8c8ce;" if border else ""
    return (f'<span style="display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;'
            f'background:{css};{edge}"></span>')


def _bar(css: str) -> str:
    return (f'<span style="display:inline-block;width:14px;height:0;border-top:2px {css};margin-right:6px;'
            f'vertical-align:3px"></span>')


class CoverageViewer:
    """The GUI and scene of one coverage payload on a viser_3d_viewer `Viewer` (kept as `viewer.coverage`)."""

    def __init__(self, viewer: Any, payload: Mapping[str, Any]) -> None:
        self.viewer = viewer
        self.server = viewer.server
        self.payload = payload
        self.tool = payload.get("tool") or None
        self.numbers = _numbers(payload)
        self.joints = joint_names(payload)
        self.views = (TOOL_VIEWS if self.tool else ()) + (HEIGHT_MAP,)
        self.stale: set[str] = set()
        self.bounds: tuple[tuple[float, float, float], tuple[float, float, float]] = ((-1, -1, -1), (1, 1, 1))
        self.frames: dict[str, Any] = {}
        self._build_gui()
        self._build_scene()
        self.show(self.view.value)

    # ── GUI ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _build_gui(self) -> None:
        gui = self.server.gui
        source = self.payload.get("source", {})
        self.status = self.viewer.add_status("Coverage")
        self.status.set(data=self.payload.get("title") or "coverage",
                        trajectories=int(source.get("trajectories", 0)),
                        samples=f"{int(source.get('samples', 0)):,}".replace(",", " "))
        self.view = gui.add_dropdown("View", self.views, initial_value=self.views[0],
                                     hint="Which 3-D view of the coverage to show")
        self.joint = gui.add_dropdown("Joint", tuple(self.joints), initial_value=self.joints[0],
                                      hint="The joint whose q-qd-qdd height map is shown")
        # WHY these two labels: BAM Reach's (robot_reach viewer.py), so the same switch reads the same everywhere.
        self.colours = gui.add_dropdown("Colours", COLORMAP_NAMES, initial_value="viridis",
                                        hint="Perceptually uniform maps (matplotlib's); empty is always white")
        self.reverse = gui.add_checkbox("Reverse (high = dark)", initial_value=False)
        # WHY linear first: Zach 2026-11-23, "Linear to me is BY far the most informative here".
        self.scale = gui.add_dropdown("Scale", SCALES, initial_value="linear",
                                      hint="linear clips at p98; equalized colours by rank (where, not how much)")
        top = 1
        if self.tool:
            cells = self.tool["voxels"]["cells"]
            top = max([int(cell[3]) for cell in cells] or [1])
        # WHY from 0: a voxel a path crossed between two samples holds 0 samples but was visited (the analysis
        # densifies paths so a fast move skips no voxel); 0 shows every voxel the tool passed through.
        self.threshold = gui.add_slider("Show voxels with ≥ N samples", min=0, max=max(top, 1), step=1,
                                        initial_value=0)
        self.legend = gui.add_html("")
        self.viewer.camera.add_gui(bounds=lambda: self.bounds)
        with gui.add_folder("How to read this", expand_by_default=False):
            self.about = gui.add_markdown("")

        self.view.on_update(lambda _event: self.show(self.view.value))
        self.joint.on_update(lambda _event: self._joint_changed())
        self.threshold.on_update(lambda _event: self._repaint(VOXELS))
        for control in (self.colours, self.reverse, self.scale):
            control.on_update(lambda _event: self._colours_changed())

    # ── scene ────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _frame(self, key: str) -> Any:
        frame = self.server.scene.add_frame(f"/coverage/{key}", show_axes=False, visible=False)
        self.frames[key] = frame
        return frame

    def _build_scene(self) -> None:
        if self.tool:
            self._frame("workspace")
            self._draw_workspace()
            for key in ("voxels", "tool_paths", "sphere"):
                self._frame(key)
            self._draw_sphere_grid()
        self._frame("height")
        for view in self.views:
            self._paint(view)

    def _cmap(self) -> tuple[str, bool]:
        return str(self.colours.value), bool(self.reverse.value)

    def _scaled(self, counts: Any) -> Scaled:
        return scale_counts(counts, str(self.scale.value), enough=int(self.payload.get("enough", 10)))

    def _colours(self, scaled: Scaled) -> np.ndarray:
        cmap, reverse = self._cmap()
        return ramp_rgb(np.clip(scaled.t, 0, 1), cmap, reverse)

    def _paint(self, view: str) -> None:
        {VOXELS: self._paint_voxels, TOOL_PATHS: self._paint_tool_paths, SPHERE: self._paint_sphere,
         HEIGHT_MAP: self._paint_height_map}[view]()
        self.stale.discard(view)

    def _repaint(self, view: str) -> None:
        if view == self.view.value:
            self._paint(view)
            self._refresh_panel()
        else:
            self.stale.add(view)

    # workspace context: the frame's axes at its origin and the bounds box with mm ticks
    def _draw_workspace(self) -> None:
        scene = self.server.scene
        low, high = (np.asarray(corner, float) for corner in self.tool["bounds"])
        size = float(np.max(high - low))
        scene.add_frame("/coverage/workspace/base", axes_length=0.08 * size, axes_radius=0.004 * size)
        scene.add_label("/coverage/workspace/base/label", tool_frame(self.payload)[1],
                        position=(0.0, 0.0, -0.03 * size),
                        anchor="top-center", font_screen_scale=0.8)
        scene.add_line_segments("/coverage/workspace/box", _box_segments(low, high), HAIR_RGB, thickness=1.0,
                                thickness_units="screen")
        offset = 0.05 * size
        for axis, name in enumerate("xyz"):
            # x ticks along the front-bottom edge, y along the right-bottom edge, z up the front-left edge
            anchor = {0: np.array([np.nan, low[1] - offset, low[2]]), 1: np.array([high[0] + offset, np.nan, low[2]]),
                      2: np.array([low[0] - offset, low[1] - offset, np.nan])}[axis]
            for tick in _nice_ticks(low[axis] * 1000.0, high[axis] * 1000.0, 4):
                at = anchor.copy()
                at[axis] = tick / 1000.0
                scene.add_label(f"/coverage/workspace/ticks/{name}{tick:+.0f}", f"{tick:.0f}", position=at,
                                anchor="center-center", font_screen_scale=0.7)
            at = anchor.copy() + np.where(np.arange(3) == axis, 0.0, np.sign(anchor - (low + high) / 2) * offset * 1.4)
            at[axis] = (low[axis] + high[axis]) / 2
            scene.add_label(f"/coverage/workspace/ticks/{name}_title", f"{name} (mm)", position=np.nan_to_num(at),
                            anchor="center-center", font_screen_scale=0.85)

    def _voxel_centres(self) -> tuple[np.ndarray, np.ndarray, float]:
        voxels = self.tool["voxels"]
        size = float(voxels["size"])
        cells = np.asarray(voxels["cells"], float).reshape(-1, 6)
        centres = np.asarray(voxels["origin"], float) + (cells[:, :3] + 0.5) * size
        return centres, cells, size

    def _paint_voxels(self) -> None:
        scene = self.server.scene
        centres, cells, size = self._voxel_centres()
        samples = cells[:, 3]
        scaled = self._scaled(samples)
        self.voxel_scale = scaled
        shown = samples >= int(self.threshold.value)
        self.voxels_shown = int(shown.sum())
        if shown.any():
            scene.add_point_cloud("/coverage/voxels/visited", centres[shown].astype(np.float32),
                                  self._colours(scaled)[shown], point_size=0.88 * size / 2, point_shape="square",
                                  point_shading="flat", precision="float32")
        elif "/coverage/voxels/visited" in self._nodes():
            self._nodes()["/coverage/voxels/visited"].remove()
        reachable = self.tool["voxels"].get("reachable")
        if reachable and "/coverage/voxels/reachable" not in self._nodes():
            visited = {tuple(int(v) for v in cell[:3]) for cell in cells}
            empty = np.asarray([ijk for ijk in reachable if tuple(int(v) for v in ijk) not in visited], float)
            if len(empty):
                points = np.asarray(self.tool["voxels"]["origin"], float) + (empty + 0.5) * size
                scene.add_point_cloud("/coverage/voxels/reachable", points.astype(np.float32), OUTSIDE_RGB,
                                      point_size=0.18 * size, point_shape="circle", point_shading="flat",
                                      precision="float32")

    def _paint_tool_paths(self) -> None:
        paths = [np.asarray(path, float).reshape(-1, 3) for path in self.tool.get("spaghetti", [])]
        paths = [path for path in paths if len(path) > 1]
        if not paths:
            return
        cmap, reverse = self._cmap()
        # WHY 0..0.85 of the ramp: the bright end of every map (viridis yellow) vanishes on the white background,
        # and a line is thin; the order still reads first (dark) -> last (light).
        order = np.linspace(0.0, 0.85, len(paths)) if len(paths) > 1 else np.zeros(1)
        segments = np.concatenate([np.stack([path[:-1], path[1:]], axis=1) for path in paths])
        colours = np.concatenate([np.repeat(ramp_rgb(order[i], cmap, reverse)[None], len(path) - 1, axis=0)
                                  for i, path in enumerate(paths)])
        self.server.scene.add_line_segments("/coverage/tool_paths/lines", segments.astype(np.float32),
                                            np.repeat(colours[:, None, :], 2, axis=1), thickness=2.0,
                                            thickness_units="screen")

    def _sphere_block(self) -> tuple[int, int, np.ndarray]:
        sphere = self.tool["orientation"]["sphere"]
        rings, sectors = int(sphere["rings"]), int(sphere["sectors"])
        return rings, sectors, np.asarray(sphere["counts"], float).reshape(rings, sectors)

    def _draw_sphere_grid(self) -> None:
        scene = self.server.scene
        rings, sectors, _ = self._sphere_block()
        circle = np.linspace(0.0, 2 * np.pi, 97)
        segments = []
        for z in -1 + 2 * np.arange(1, rings) / rings:  # the equal-area band edges
            r = math.sqrt(1 - z * z)
            loop = np.column_stack([r * np.cos(circle), r * np.sin(circle), np.full_like(circle, z)]) * 1.014
            segments.append(np.stack([loop[:-1], loop[1:]], axis=1))
        height = np.linspace(-1.0, 1.0, 49)
        for azimuth in -np.pi + 2 * np.pi * np.arange(sectors) / sectors:
            r = np.sqrt(1 - height**2)
            meridian = np.column_stack([r * np.cos(azimuth), r * np.sin(azimuth), height]) * 1.014
            segments.append(np.stack([meridian[:-1], meridian[1:]], axis=1))
        scene.add_line_segments("/coverage/sphere/grid", np.concatenate(segments).astype(np.float32), HAIR_RGB,
                                thickness=1.0, thickness_units="screen")
        reference = np.asarray(self.tool["orientation"].get("reference", (0.0, 0.0, -1.0)), float)
        reference = reference / (np.linalg.norm(reference) or 1.0)
        scene.add_line_segments("/coverage/sphere/reference", np.array([[reference * 1.0, reference * 1.35]]),
                                INK_RGB, thickness=3.0, thickness_units="screen")
        scene.add_label("/coverage/sphere/reference_label", "reference: tilt 0°", position=reference * 1.42,
                        anchor="center-center", font_screen_scale=0.85)
        for name, at in (("+x", (1.45, 0, 0)), ("+y", (0, 1.45, 0)), ("+z (up)", (0, 0, 1.3)),
                         ("−x", (-1.45, 0, 0)), ("−y", (0, -1.45, 0))):
            scene.add_label(f"/coverage/sphere/axis {name}", name, position=at, anchor="center-center",
                            font_screen_scale=0.85)

    def _paint_sphere(self) -> None:
        rings, sectors, counts = self._sphere_block()
        scaled = self._scaled(counts)
        self.sphere_scale = scaled
        # never-held cells are a near-white (246): white to the eye, but the sphere keeps its outline on the white page
        colours = np.where((scaled.t >= 0)[..., None], self._colours(scaled), np.uint8(246)).reshape(rings, sectors, 3)
        points, point_colours = [], []
        for ring in range(rings):
            # WHY rows per band: equal-z bands are equal in AREA, not in arc, so the polar caps are ~3.5x taller
            # (in polar angle) than the equator band; a fixed row count left white stripes in the caps.
            bottom = math.acos(-1 + 2 * ring / rings)
            top = math.acos(-1 + 2 * (ring + 1) / rings)
            rows = max(3, math.ceil(abs(top - bottom) / SPHERE_SPACING))
            widest = max(math.sin(bottom), math.sin(top), 1.0 if (bottom - math.pi / 2) * (top - math.pi / 2) < 0
                         else 0.0)
            around = max(3, math.ceil(2 * math.pi * widest / sectors / SPHERE_SPACING))
            rise, turn = np.meshgrid((np.arange(rows) + 0.5) / rows, (np.arange(around) + 0.5) / around,
                                     indexing="ij")
            polar = bottom + (top - bottom) * rise.ravel()
            for sector in range(sectors):
                azimuth = -np.pi + 2 * np.pi * (sector + turn.ravel()) / sectors
                points.append(np.stack([np.sin(polar) * np.cos(azimuth), np.sin(polar) * np.sin(azimuth),
                                        np.cos(polar)], axis=-1))
                point_colours.append(np.repeat(colours[ring, sector][None], len(polar), axis=0))
        self.server.scene.add_point_cloud("/coverage/sphere/cells", np.concatenate(points).astype(np.float32),
                                          np.concatenate(point_colours), point_size=0.012, point_shape="square",
                                          point_shading="flat", precision="float32")

    def _height_geometry(self, joint: str) -> dict[str, Any]:
        plane = self.payload["planes"][joint]["q_qd"]
        nx, ny = (int(v) for v in plane["shape"])
        cell = HEIGHT_MAP_WIDTH / nx
        depth = cell * ny
        return {"plane": plane, "nx": nx, "ny": ny, "cell": cell, "width": HEIGHT_MAP_WIDTH, "depth": depth,
                "x_edges": edges(plane["x_edges"]), "y_edges": edges(plane["y_edges"])}

    def _paint_height_map(self) -> None:
        scene = self.server.scene
        joint = str(self.joint.value)
        geometry = self._height_geometry(joint)
        plane, nx, ny, cell = geometry["plane"], geometry["nx"], geometry["ny"], geometry["cell"]
        width, depth = geometry["width"], geometry["depth"]
        samples = np.asarray(plane["samples"], float).reshape(nx, ny)
        peak = np.asarray([np.nan if v is None else v for v in plane["max_other"]], float).reshape(nx, ny)
        limit = self.payload["limits"][joint]["qdd"]
        reach = max(abs(float(limit["low"])), abs(float(limit["high"]))) or 1.0
        scaled = self._scaled(samples)
        self.height_scale = scaled
        visited = scaled.t >= 0
        i, j = np.nonzero(visited)
        x = -width / 2 + (i + 0.5) * cell
        y = -depth / 2 + (j + 0.5) * cell
        share = np.nan_to_num(peak[i, j]) / reach
        z = np.clip(share, 0.0, 1.5) * HEIGHT_MAP_TOP
        self.height_numbers = {"cells": int(visited.sum()), "highest": float(share.max()) if len(share) else 0.0}
        root = "/coverage/height"
        for name in [name for name in self._nodes() if name.rsplit("/", 1)[0] == root]:
            handle = self._nodes().get(name)  # removing a node removes its children too
            if handle is not None:
                handle.remove()
        if len(i):
            tiles = np.column_stack([x, y, z]).astype(np.float32)
            scene.add_point_cloud(f"{root}/tiles", tiles, self._colours(scaled)[i, j], point_size=0.9 * cell / 2,
                                  point_shape="square", point_shading="flat", precision="float32")
            stems = np.stack([np.column_stack([x, y, np.zeros_like(z)]), tiles], axis=1)
            scene.add_line_segments(f"{root}/stems", stems.astype(np.float32), STEM_RGB, thickness=1.0,
                                    thickness_units="screen")
        scene.add_line_segments(f"{root}/floor_limits", _rectangle(-width / 2, width / 2, -depth / 2, depth / 2, 0.0),
                                LIMIT_RGB, thickness=2.0, thickness_units="screen")
        stated = limit.get("source") == "limit"
        scene.add_line_segments(f"{root}/qdd_limit", _rectangle(-width / 2, width / 2, -depth / 2, depth / 2,
                                                                HEIGHT_MAP_TOP),
                                LIMIT_RGB if stated else HAIR_RGB, thickness=1.6, thickness_units="screen")
        planner = ((self.payload.get("planner_limits") or {}).get(joint) or {}).get("qdd")
        if planner:
            level = max(abs(float(planner["low"])), abs(float(planner["high"]))) / reach * HEIGHT_MAP_TOP
            scene.add_line_segments(f"{root}/qdd_planner", _rectangle(-width / 2, width / 2, -depth / 2, depth / 2,
                                                                      level, dashed=True),
                                    LIMIT_RGB, thickness=1.4, thickness_units="screen")
        scale_value, unit = joint_display(self.payload, joint)
        x_edges, y_edges = geometry["x_edges"], geometry["y_edges"]
        for tick in _nice_ticks(x_edges[0] * scale_value, x_edges[-1] * scale_value, 5):
            at = -width / 2 + (tick / scale_value - x_edges[0]) / (x_edges[-1] - x_edges[0]) * width
            scene.add_label(f"{root}/q_ticks/{tick:+.0f}", f"{tick:.0f}", position=(at, -depth / 2 - 0.05, 0.0),
                            anchor="center-center", font_screen_scale=0.7)
        for tick in _nice_ticks(y_edges[0] * scale_value, y_edges[-1] * scale_value, 4):
            at = -depth / 2 + (tick / scale_value - y_edges[0]) / (y_edges[-1] - y_edges[0]) * depth
            scene.add_label(f"{root}/qd_ticks/{tick:+.0f}", f"{tick:.0f}", position=(width / 2 + 0.06, at, 0.0),
                            anchor="center-center", font_screen_scale=0.7)
        for share_tick in (0.0, 0.5, 1.0):
            scene.add_label(f"{root}/qdd_ticks/{share_tick:.1f}", f"{share_tick * 100:.0f} %",
                            position=(-width / 2 - 0.05, -depth / 2 - 0.05, share_tick * HEIGHT_MAP_TOP),
                            anchor="center-center", font_screen_scale=0.7)
        scene.add_label(f"{root}/q_title", f"q, position ({unit})", position=(0.0, -depth / 2 - 0.13, 0.0),
                        anchor="center-center", font_screen_scale=0.85)
        scene.add_label(f"{root}/qd_title", f"qd, speed ({signal_unit(unit, 'qd')})",
                        position=(width / 2 + 0.2, 0.0, 0.0), anchor="center-center", font_screen_scale=0.85)
        scene.add_label(f"{root}/qdd_title", "max |qdd|, % of its limit" if stated else "max |qdd|, % of data span",
                        position=(-width / 2 - 0.1, -depth / 2 - 0.1, HEIGHT_MAP_TOP * 1.15),
                        anchor="center-center", font_screen_scale=0.85)

    def _nodes(self) -> dict[str, Any]:
        # viser 1.1.1 keeps every live scene node here (name -> handle); a node added under an existing name replaces it
        return self.server.scene._handle_from_node_name

    # ── switching ────────────────────────────────────────────────────────────────────────────────────────────────────
    def show(self, view: str) -> None:
        if view not in self.views:
            raise ValueError(f"view {view!r}: expected one of {', '.join(self.views)}")
        if self.view.value != view:
            self.view.value = view  # runs on_update -> show(view) again; the second call does the work
            return
        if view in self.stale:
            self._paint(view)
        with self.server.atomic():
            for key, frame in self.frames.items():
                frame.visible = key == {VOXELS: "voxels", TOOL_PATHS: "tool_paths", SPHERE: "sphere",
                                        HEIGHT_MAP: "height"}[view] or (key == "workspace" and view in (VOXELS,
                                                                                                         TOOL_PATHS))
            self.viewer.grid.visible = view in (VOXELS, TOOL_PATHS)
        self.joint.visible = view == HEIGHT_MAP
        self.threshold.visible = view == VOXELS
        self.scale.disabled = view == TOOL_PATHS
        self.bounds = self._view_bounds(view)
        # WHY the sphere is seen from a little below: a tool pointing down (the usual case) fills the lower half
        direction = {HEIGHT_MAP: (1.0, -1.4, 0.9), SPHERE: (1.0, -1.3, -0.55)}.get(view)
        self.viewer.camera.fit_home(*self.bounds, direction=direction, aspect=0.8)
        self.viewer.camera.fit(*self.bounds, direction=direction)
        self._refresh_panel()

    def _view_bounds(self, view: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        if view in (VOXELS, TOOL_PATHS):
            low, high = self.tool["bounds"]
            return tuple(float(v) for v in low), tuple(float(v) for v in high)
        if view == SPHERE:
            return (-1.1, -1.1, -1.1), (1.1, 1.1, 1.1)
        geometry = self._height_geometry(str(self.joint.value))
        return ((-geometry["width"] / 2 - 0.1, -geometry["depth"] / 2 - 0.15, 0.0),
                (geometry["width"] / 2 + 0.1, geometry["depth"] / 2, HEIGHT_MAP_TOP * 1.15))

    def _joint_changed(self) -> None:
        self._repaint(HEIGHT_MAP)
        if self.view.value == HEIGHT_MAP:
            self.bounds = self._view_bounds(HEIGHT_MAP)

    def _colours_changed(self) -> None:
        for view in self.views:
            self.stale.add(view)
        self._repaint(str(self.view.value))

    # ── status, legend, explanation ──────────────────────────────────────────────────────────────────────────────────
    def _refresh_panel(self) -> None:
        view = str(self.view.value)
        numbers = self.numbers
        rows: dict[str, Any] = {key: None for key in ("voxels visited", "shown", "reachable visited", "directions",
                                                       "largest tilt", "tool speed p99", "joint", "q × qd visited",
                                                       "peak qdd", "paths")}
        if view == VOXELS:
            rows["voxels visited"] = int(numbers.get("tool_voxels_visited", len(self.tool["voxels"]["cells"])))
            threshold = int(self.threshold.value)
            rows["shown"] = (f"{self.voxels_shown} with ≥ {threshold} sample{'' if threshold == 1 else 's'}"
                             if threshold else f"all {self.voxels_shown}")
            if "tool_voxels_reachable_pct" in numbers:
                rows["reachable visited"] = f"{numbers['tool_voxels_reachable_pct']:.0f} %"
        elif view == TOOL_PATHS:
            rows["paths"] = len(self.tool.get("spaghetti", []))
            if "tool_speed_p99_m_s" in numbers:
                rows["tool speed p99"] = f"{numbers['tool_speed_p99_m_s']:.2f} m/s"
        elif view == SPHERE:
            if "tool_directions_visited_pct" in numbers:
                rows["directions"] = f"{numbers['tool_directions_visited_pct']:.0f} % of cells"
            if "tool_tilt_max_deg" in numbers:
                rows["largest tilt"] = f"{numbers['tool_tilt_max_deg']:.0f}°"
        else:
            joint = str(self.joint.value)
            rows["joint"] = joint
            rows["q × qd visited"] = f"{self.payload['planes'][joint]['q_qd']['visited_pct']:.0f} % of cells"
            rows["peak qdd"] = f"{self.payload['hist'][joint]['qdd']['peak_pct']:.0f} % of limit"
        self.status.set(**rows)
        self.legend.content = self._legend_html(view)
        self.about.content = ABOUT[view]

    def _marks(self, view: str) -> list[tuple[str, str]]:
        """Every mark the view draws besides the colour, as (swatch html, meaning)."""
        never = _swatch("#fff", border=True)
        if view == VOXELS:
            marks = [(never, "white / nothing = never visited")]
            if self.tool["voxels"].get("reachable"):
                marks.append((_swatch("rgb(221,220,214)"), "faint grey dot = reachable, never visited"))
            frame = tool_frame(self.payload)[0]
            return marks + [(_swatch("linear-gradient(90deg,#d33,#3a3,#33d)"),
                             f'"{frame}" axes: x red, y green, z blue')]
        if view == SPHERE:
            return [(never, "white cell = direction never held"),
                    (_bar("solid #1d1d1f"), "black spike = reference (tilt 0°)"),
                    (_bar("solid #c8c8ce"), "grey lines = the equal-area cells")]
        marks = [(_bar("solid #b4442f"), "red frame, floor = q / qd limits"),
                 (_bar("solid #b4442f"), "red frame, top = qdd limit (100 %)"),
                 (never, "no tile = never visited"),
                 (_bar("solid #d6d6dc"), "grey stem: height = max |qdd| in the cell")]
        if ((self.payload.get("planner_limits") or {}).get(str(self.joint.value)) or {}).get("qdd"):
            marks.append((_bar("dashed #b4442f"), "dashed red = planner's qdd limit"))
        return marks

    def _legend_html(self, view: str) -> str:
        cmap, reverse = self._cmap()
        if view == TOOL_PATHS:
            count = len(self.tool.get("spaghetti", []))
            ticks: Sequence[tuple[float, str]] = ((0.0, "first"), (0.85, f"last ({count})"))
            title, note = "colour = order in the dataset", ""
            marks = [(_bar("solid #555"), "a line = one trajectory's tool path")]
        else:
            scaled = {VOXELS: getattr(self, "voxel_scale", None), SPHERE: getattr(self, "sphere_scale", None),
                      HEIGHT_MAP: getattr(self, "height_scale", None)}[view]
            ticks = scaled.ticks if scaled is not None else ()
            unit = {VOXELS: "samples per 5 cm voxel", SPHERE: "samples per direction cell",
                    HEIGHT_MAP: "samples per q × qd cell"}[view]
            title = f"colour = {unit}"
            mode = str(self.scale.value)
            note = ("" if scaled is None else scaled.note if mode == "linear"
                    else f"{SCALE_TITLES[mode]} · {scaled.note}")
            marks = self._marks(view)
        tick_html = "".join(
            f'<span style="position:absolute;left:{100 * t:.1f}%;transform:translateX(-{100 * t:.0f}%);'
            f'white-space:nowrap">{label}</span>' for t, label in ticks)
        rows = "".join(f'<div style="margin-top:3px">{mark}{text}</div>' for mark, text in marks)
        return (f'<div style="font-size:12px;line-height:1.35;padding:2px 12px 8px;color:#3a3a3e">'
                f'<div style="font-weight:600">{title}</div>'
                f'<div style="height:11px;margin:4px 0 2px;border-radius:2px;'
                f'background:linear-gradient(90deg,{_gradient_css(cmap, reverse)})"></div>'
                f'<div style="position:relative;height:15px;font-size:11px;color:#6e6e73">{tick_html}</div>'
                + (f'<div style="font-size:11px;color:#6e6e73">{note}</div>' if note else "")
                + f'<div style="margin-top:4px">{rows}</div></div>')


def serve_coverage(payload: Mapping[str, Any], *, port: int = 0, title: str | None = None) -> Any:
    """Start the coverage viewer (non-blocking) and print `READY <url>`; returns the viser_3d_viewer `Viewer`.

    `viewer.coverage` is the `CoverageViewer` (its `show(view)` switches views); stop with `viewer.stop()`."""
    from viser_3d_viewer import Viewer, ViewerConfig

    if payload.get("schema") != "traj_compare.coverage/1":
        raise ValueError(f"not a coverage payload: schema {payload.get('schema')!r}")
    # WHY light: empty is white on the page and in the PNGs (Zach 2026-11-19, "so its clear that white means empty");
    # on viser's dark background a never-visited cell would read as a black hole instead.
    viewer = Viewer(ViewerConfig(title=title or payload.get("title") or "Trajectory coverage", port=port,
                                 dark_mode=False, grid_size=2.0))
    try:
        viewer.coverage = CoverageViewer(viewer, payload)
    except BaseException:
        viewer.stop()
        raise
    viewer.print_ready()
    return viewer


def main(argv: Sequence[str] | None = None, serve: Callable[..., Any] = serve_coverage) -> None:
    parser = argparse.ArgumentParser(description="Serve a coverage.json (traj_compare.coverage/1) in the house "
                                                 "3-D viewer until Ctrl-C.")
    parser.add_argument("coverage_json", type=Path, help="the payload written by analyze() / python -m "
                                                         "traj_compare.coverage")
    parser.add_argument("--port", type=int, default=0, help="0 = the OS picks (printed on the READY line)")
    parser.add_argument("--title", default=None)
    args = parser.parse_args(argv)
    payload = json.loads(args.coverage_json.read_text("utf-8"))
    viewer = serve(payload, port=args.port, title=args.title)
    viewer.serve_forever()


if __name__ == "__main__":
    main()
