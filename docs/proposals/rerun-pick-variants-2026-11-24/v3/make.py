#!/usr/bin/env python3
"""V3 · Limit-lit: every link of the arm is tinted, live, by how close its joint is to a limit at the playhead.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v3/make.py

Writes v3/plan-dev-029.rrd (fixture.plan()) and v3/run-dev-029.rrd (fixture.run("p6s"): the solution lit, the target a
faint line in every plot). The entry point is `save(path, traj, *, robot, tool=None, target=None, target_tool=None,
extras=None)`; it returns the moment closest to a limit, where the recording opens and which every view marks.

Zach's frame (Nov 24: "split the page in half ... we are always showing the 3d robot ... on the right side ... show
what ever particualy information we want there"): the URDF arm on the left half, tabs on the right half. Inside it:

- each link's mesh colour is its joint's WORST % of limit at the playhead, the largest of |q| (to its position limit),
  |qd| / vmax and |qdd| / amax: green below 80 %, amber 80-95 %, red from 95 % (the albedo of each link mesh, logged on
  the t timeline). No ghosts; a fixed legend in a corner the arm and the tool path never reach gives each joint's
  number and which of q / qd / qdd it is, in its link's colour; start / end sit beside the path, off the arm.
- the right half opens on "% of limit": a lane per joint (named by the joint) with the tint it had at every instant
  (Rerun's state timeline), a two-line key, then one strip per joint of q, qd, qdd as % of its limits over the shaded
  ±100 % band, the amber 80-95 % and red ≥ 95 % zones and their lines. Then q, qd, qdd, qddd (each joint in degrees,
  the same zones of its limit shaded), q / qd / qdd (the stock table + cards) and TCP. Where the target sits under the
  run (closer than ~2 px), the title says so and by how much instead of promising a line.
- the recording OPENS at the moment closest to a limit, which is also marked (◆) on its joint's strip, named over the
  lanes and stored in the recording (property `limit_lit`: closest_s). Rerun 0.40 has no blueprint field for the time
  cursor, so the file is written in the order that puts it there: a paused viewer starts at the first time it sees,
  so the rows from the moment on come first, the rows before it last (`_write_opening_at`; measured in the real web
  viewer with v3/opens_at.cjs). On a run whose qd / qdd are differences of its encoder q, the opening title says the
  number is that measured rate and what it stays once q is smoothed (`_opening`).

Reuses robot_msgs.viz.rerun's pieces by import (`_RobotPlan`, `_series`, `_percent`, `_forward_kinematics`, `_eye`,
`band` ...) and never edits robot_msgs.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
import rerun.urdf as rurdf

from robot_msgs.trajectory import JointTrajectory, PoseTrajectory
from robot_msgs.viz import rerun as viz

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
APPLICATION_ID = "rerun_pick_v3"
TIMELINE = viz.TIMELINE

# WHY these two thresholds (the round's V3 thesis): below 80 % of a limit is ordinary, 80-95 % is "near", from 95 % on
# the joint is AT its limit (a time-optimal plan rides its acceleration limit at ~99 %).
NEAR, AT = 80.0, 95.0
SHORTS = ("q", "qd", "qdd")
# WHY colour means limit and nothing else here: the stock's orange tool trail and blue/orange ghosts would read as
# amber / alarms next to lit links, so the tool path is neutral slate and there are no ghosts.
OK_RGB, NEAR_RGB, AT_RGB = (64, 168, 92), (238, 160, 24), (214, 48, 44)
CLASS_RGB = (OK_RGB, NEAR_RGB, AT_RGB)
NO_LIMIT_RGB = (175, 180, 190)  # the stock steel: a link whose joint has no limit at all, and the fixed base
TRAVELLED, TO_GO = (70, 80, 96), (205, 209, 216)
TARGET_RGB = (200, 204, 212)  # the agent's target: a faint line under the bold solution in every plot
# WHY "_target": Rerun 0.40 draws a plot's series in entity-path order, the last on top, whatever the blueprint lists or
# the log order (measured); "target" sorts after "solution" and hid the lit run under its faint line, "_" sorts first
TARGET_PART = "_target"
# WHY opaque colours, several layers: Rerun 0.40 fills a Measurements band at 0.2 × its colour's alpha (measured: alpha
# 190 drew 15 %), so one layer is a haze; LAYERS copies of the same band stack to 1 - 0.8^LAYERS (2 → 36 %; 3 → 49 %
# made the ≥ 95 % zone of a "% of limit" strip, a third of its height, the loudest thing on the page)
NEAR_BAND, AT_BAND = (238, 160, 24, 255), (214, 48, 44, 255)
ZONE_LAYERS = 2
PCT_BAND = (96, 112, 140, 255)  # ±100 % in the "% of limit" strips: one layer of slate, the zones carry the colour
LIMIT_LINE = (90, 96, 110)  # the ±100 % edge in the "% of limit" strips
# WHY 2 %: a ~1.6 px run line covers a 1 px pale target until the two part by ~2 px, 2 % of a ~110 px strip; under
# that the title says "target under the run (≤ …)" instead of promising a line nobody can see
UNDER_SHARE = 0.02
# the stock cards' q / qd / qdd styles (colour, width), so the "% of limit" strips read like the q / qd / qdd tab
CARD_STYLE = {"q": ((38, 110, 214), 2.4), "qd": ((20, 150, 140), 1.6), "qdd": ((120, 120, 132), 1.0)}

# the 3D view at its opening camera, as a pinhole: Rerun 0.40's default vertical field of view, the 3D view of a
# 1600 × 1000 page (the left half, under its title bar), and a 3D label's box under its point (measured on the frames:
# the old callout column landed within 2 px of where this puts it)
FOV_Y = np.radians(55.0)
VIEW_PX = (800.0, 908.0)
LABEL_DROP_PX, LABEL_H_PX, LABEL_CHAR_PX, LABEL_PAD_PX = 3.0, 21.0, 6.8, 10.0
CELL_PX = 2  # the footprint grid
SURFACE_SAMPLES = 900  # points per link mesh for its footprint (area-weighted; a long tube has vertices at its ends only)
FOOTPRINT_ROWS = 120  # instants of the run whose arm footprint the legend and the start / end labels avoid
LEGEND_CLEAR_PX = 14  # the legend's clearance from anything the arm or the path ever covers
LEGEND_TITLE = "worst % of limit"


def _short(joint: str) -> str:
    return viz._short_joint(joint)


# ── the numbers: % of limit per joint, per sample ─────────────────────────────────────────────────────────────


class Lit:
    """Each joint's signed q / qd / qdd as % of its limits (stock `_percent`: [low, high] → [-100, +100]), its worst
    |%| per sample, which quantity that is, and the tint class (0 ok, 1 near, 2 at; -1 = no limit at all)."""

    def __init__(self, plan: Any) -> None:
        count, samples = len(plan.joints), len(plan.seconds)
        self.pct = {}
        for short in SHORTS:
            values = plan.signals[short]
            table = np.full((samples, count), np.nan)
            if values is not None:
                for index in range(count):
                    low, high = (bound[index] for bound in plan.limits[short])
                    if np.isfinite(low) and np.isfinite(high) and high > low:
                        table[:, index] = viz._percent(values[:, index], low, high)
            self.pct[short] = table
        stack = np.abs(np.stack([self.pct[short] for short in SHORTS]))  # (3, N, J)
        filled = np.where(np.isfinite(stack), stack, -1.0)
        self.which = filled.argmax(axis=0)  # (N, J) index into SHORTS
        self.worst = filled.max(axis=0)  # (N, J); -1 where a joint has no limit at all
        self.level = np.where(self.worst < 0, -1, (self.worst >= NEAR).astype(int) + (self.worst >= AT))
        # the moment closest to a limit: the instant whose worst joint is worst (the first one, on a tie)
        per_sample = self.worst.max(axis=1)
        self.k = int(np.argmax(per_sample))
        self.j = int(np.argmax(self.worst[self.k]))
        self.t = float(plan.seconds[self.k])
        self.at_share = (self.level == 2).mean(axis=0)  # the share of the run each joint spends ≥ 95 %

    def label(self, plan: Any, k: int, j: int) -> str:
        if self.level[k, j] < 0:
            return f"{_short(plan.joints[j])} · no limit"
        return f"{_short(plan.joints[j])} {self.worst[k, j]:.0f} % {SHORTS[self.which[k, j]]}"

    def moment(self, plan: Any, short: bool = False) -> str:
        if self.worst[self.k, self.j] < 0:
            return "no limits given"
        past = " (past it)" if self.worst[self.k, self.j] > 100.0 and not short else ""
        return f"{self.label(plan, self.k, self.j)}{past} at {self.t:.2f} s"


# ── the arm: one URDF copy, each link's albedo on t ─────────────────────────────────────────────────────────────


def _lit_copy(plan: Any, recording: rr.RecordingStream) -> tuple[Any, dict[str, list[tuple[str, str]]], dict]:
    """The stock `_urdf_copy` for the live arm, WITHOUT its static tint: a static albedo would shadow the temporal one
    (Rerun: static data wins over temporal data of the same component). Returns the tree,
    {link: [(geometry entity, archetype)]} and {link: the middle of its drawn geometry, in the link's frame}."""
    prefix = f"{plan.part}/"
    tree = rurdf.UrdfTree.from_file_path(plan.urdf, frame_prefix=prefix)
    entity, old_root = f"/world/{plan.part}/robot", f"/{tree.name}"
    chunks = list(tree.stream(include_joint_transforms=False))
    kinds = viz._geometry_kinds(chunks)

    def drawable(path: str) -> bool:
        archetype, media = kinds.get(path, ("", None))
        return bool(archetype) and (archetype != "Asset3D" or media in viz._DRAWABLE_MEDIA)

    by_link: dict[str, list[tuple[str, str]]] = {}
    keep: set[str] = set()
    for link in [tree.root_link().name, *(joint.child_link for joint in tree.joints())]:
        visuals = [path for path in tree.get_visual_geometry_paths(link) if drawable(path)]
        chosen = visuals or [path for path in tree.get_collision_geometry_paths(link) if drawable(path)]
        keep.update(chosen)
        by_link[link] = [(entity + path[len(old_root):], kinds[path][0]) for path in chosen]
    dropped = set(kinds) - keep
    surfaces = _link_surfaces(tree, chunks, keep)
    recording.send_chunks([
        chunk.with_entity_path(entity + chunk.entity_path[len(old_root):])
        for chunk in chunks
        if not any(chunk.entity_path == path or chunk.entity_path.startswith(path + "/") for path in dropped)
    ])  # fmt: skip
    recording.log(f"{entity}/mount", rr.Transform3D(parent_frame=f"tf#/world/{plan.part}",
                                                    child_frame=prefix + tree.root_link().name), static=True)
    return tree, by_link, surfaces


def _link_surfaces(tree: Any, chunks: list[Any], keep: set[str]) -> dict[str, np.ndarray]:
    """{link: up to SURFACE_SAMPLES points on its drawn geometry, in the link frame}, for the links whose geometry is
    a binary STL or a Mesh3D (others fall back to their joint origins in the footprint). WHY surface samples, not
    vertices: a long link (the UR's upper arm, a tube) has vertices only at its two ends, so a vertex footprint missed
    its middle; area-weighted points cover it. The seed is fixed, so the layout is the same every build."""
    from robot_msgs.geometry.rotations import quat_to_matrix

    parts: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        if chunk.entity_path not in keep:
            continue
        batch = chunk.to_record_batch()
        row = parts.setdefault(chunk.entity_path, {})
        for column in batch.schema.names:
            values = batch.column(column).to_pylist()
            if values and values[0] is not None:
                row[column] = values[0]
    link_of = {path: link for link in [tree.root_link().name, *(j.child_link for j in tree.joints())]
               for path in [*tree.get_visual_geometry_paths(link), *tree.get_collision_geometry_paths(link)]}
    out: dict[str, list[np.ndarray]] = {}
    rng = np.random.default_rng(0)
    for path, row in sorted(parts.items()):
        triangles = None
        if "Asset3D:blob" in row and (row.get("Asset3D:media_type") or [""])[0] == "model/stl":
            blob = bytes(bytearray(row["Asset3D:blob"][0]))
            if not blob[:80].lstrip().lower().startswith(b"solid") and len(blob) > 84:
                count = int(np.frombuffer(blob, dtype="<u4", count=1, offset=80)[0])
                record = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
                if len(blob) >= 84 + count * record.itemsize:
                    triangles = np.frombuffer(blob, dtype=record, count=count, offset=84)["vertices"]
        elif "Mesh3D:vertex_positions" in row and "Mesh3D:triangle_indices" in row:
            vertices = np.asarray(row["Mesh3D:vertex_positions"], dtype=np.float64)
            triangles = vertices[np.asarray(row["Mesh3D:triangle_indices"], dtype=np.int64)]
        if triangles is None or not len(triangles) or path not in link_of:
            continue
        triangles = np.asarray(triangles, dtype=np.float64)
        a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
        area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        if not area.sum() > 0:
            continue
        pick = rng.choice(len(triangles), size=SURFACE_SAMPLES, p=area / area.sum())
        u, v = rng.random((2, SURFACE_SAMPLES))
        flip = u + v > 1.0
        u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
        points = a[pick] + u[:, None] * (b - a)[pick] + v[:, None] * (c - a)[pick]
        scale = np.asarray((row.get("InstancePoses3D:scales") or [[1.0, 1.0, 1.0]])[0], dtype=np.float64)
        xyzw = np.asarray((row.get("InstancePoses3D:quaternions") or [[0.0, 0.0, 0.0, 1.0]])[0], dtype=np.float64)
        shift = np.asarray((row.get("InstancePoses3D:translations") or [[0.0, 0.0, 0.0]])[0], dtype=np.float64)
        out.setdefault(link_of[path], []).append(shift + (scale * points) @ quat_to_matrix(xyzw).T)
    return {link: np.vstack(points) for link, points in out.items()}


def _tint(recording: rr.RecordingStream, path: str, archetype: str, seconds: np.ndarray, rgb: np.ndarray) -> None:
    """One geometry's colour on t, logged only where it changes (latest-at holds it in between)."""
    change = np.flatnonzero(np.r_[True, np.any(np.diff(rgb, axis=0) != 0, axis=1)])
    colours = [tuple(int(c) for c in rgb[k]) + (255,) for k in change]
    at = [rr.TimeColumn(TIMELINE, duration=seconds[change])]
    if archetype == "Asset3D":
        recording.send_columns(path, indexes=at, columns=rr.Asset3D.columns(albedo_factor=colours))
    elif archetype == "Mesh3D":
        recording.send_columns(path, indexes=at, columns=rr.Mesh3D.columns(albedo_factor=colours))
    else:  # Boxes3D, Cylinders3D, ... : one colour per instance
        recording.send_columns(path, indexes=at, columns=getattr(rr, archetype).columns(colors=colours))


def _log_arm(plan: Any, lit: Lit, recording: rr.RecordingStream) -> "_Layout":
    """The lit arm (each link's albedo on t, every joint's transform) and the legend; returns the layout (the camera
    as a pinhole, the arm's footprint, the legend's box) that the start / end labels then avoid."""
    part, seconds = plan.part, plan.seconds
    on_t = [rr.TimeColumn(TIMELINE, duration=seconds)]
    tree, by_link, surfaces = _lit_copy(plan, recording)
    child_of = {joint.child_link: joint.name for joint in tree.joints()}
    columns = {joint: index for index, joint in enumerate(plan.joints)}
    palette = np.array(CLASS_RGB + (NO_LIMIT_RGB,), dtype=np.uint8)  # index -1 → the steel
    for link, paths in by_link.items():
        joint = child_of.get(link)
        if joint in columns:
            rgb = palette[lit.level[:, columns[joint]]]
        else:
            rgb = np.broadcast_to(np.array(NO_LIMIT_RGB, dtype=np.uint8), (len(seconds), 3))
        for path, archetype in paths:
            if joint in columns:
                _tint(recording, path, archetype, seconds, rgb)
            else:
                tint = (rr.Asset3D.from_fields(albedo_factor=NO_LIMIT_RGB) if archetype == "Asset3D"
                        else rr.Mesh3D.from_fields(albedo_factor=NO_LIMIT_RGB) if archetype == "Mesh3D"
                        else getattr(rr, archetype).from_fields(colors=[NO_LIMIT_RGB]))
                recording.log(path, tint, static=True)
    # every joint one transform entity: moving ones on t, the rest static (the stock's step 6)
    for joint in tree.joints():
        path = f"/world/{part}/robot/joint_transforms/{viz._part(joint.name)}"
        values = plan.values.get(joint.name)
        if values is not None and joint.joint_type != "fixed":
            recording.send_columns(path, indexes=on_t,
                                   columns=joint.compute_transform_columns(values.tolist(), clamp=False))
        else:
            recording.log(path, joint.compute_transform(0.0, clamp=False), static=True)

    # the number behind each colour: a legend (joint, worst %, which quantity) in each link's tint, in a corner of the
    # opening camera that the arm and the tool path never reach. WHY not a callout column with leaders (the check of
    # 2026-11-24): fixed beside the motion, its leaders crossed the whole view and the tool path when the arm swung
    # to the far side (2.4 s, 3.2 s). WHY not labels on the links (the first cut): UR joint origins coincide or sit
    # centimetres apart, and Rerun 0.40 overprints or hides labels that overlap. Base at the bottom, as on the arm.
    links = viz._forward_kinematics(tree, plan.values, len(seconds))
    layout = _Layout(plan, links, surfaces)
    count = len(plan.joints)
    rows = np.unique(np.linspace(0, len(seconds) - 1, min(len(seconds), viz._ROWS)).round().astype(int))
    texts = [[lit.label(plan, k, j) for j in range(count)] for k in rows]
    widest = max([len(LEGEND_TITLE)] + [len(text) for row in texts for text in row])
    points = layout.legend(count + 1, widest)  # (count + 1, 3): the title, then the last joint … the first
    frame = rr.CoordinateFrame(f"{part}/{tree.root_link().name}")
    recording.log(f"/world/{part}/limits/legend_title",
                  rr.Points3D([points[0]], labels=[LEGEND_TITLE], colors=[TRAVELLED], radii=[0.0006],
                              show_labels=True), frame, static=True)  # fmt: skip
    order = list(reversed(range(count)))  # the last joint on top, under the title
    path = f"/world/{part}/limits/legend"
    recording.log(path, rr.Points3D.from_fields(radii=[0.0006], show_labels=True), frame, static=True)
    recording.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=seconds[rows])],
                           columns=rr.Points3D.columns(
                               positions=np.broadcast_to(points[1:], (len(rows), count, 3)).reshape(-1, 3),
                               colors=[tuple(int(c) for c in palette[lit.level[k, j]]) for k in rows for j in order],
                               labels=[texts[r][j] for r in range(len(rows)) for j in order],
                           ).partition([count] * len(rows)))  # fmt: skip
    return layout


class _Screen:
    """The opening camera (`plan.eye`) as a pinhole in the 3D view's pixels: x right, y down, 0 at the view's top-left
    under its title bar."""

    def __init__(self, eye: Any) -> None:
        self.position = np.asarray(eye.position.as_arrow_array().to_pylist()[0], dtype=np.float64)
        self.look = np.asarray(eye.look_target.as_arrow_array().to_pylist()[0], dtype=np.float64)
        self.forward = (self.look - self.position) / np.linalg.norm(self.look - self.position)
        self.right = np.cross(self.forward, [0.0, 0.0, 1.0])
        self.right /= max(float(np.linalg.norm(self.right)), 1e-12)
        self.up = np.cross(self.right, self.forward)
        self.scale = 0.5 * VIEW_PX[1] / np.tan(0.5 * FOV_Y)  # px per unit of (sideways / depth)

    def pixels(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        v = np.asarray(points, dtype=np.float64) - self.position
        depth = np.maximum(v @ self.forward, 1e-6)
        return np.stack([0.5 * VIEW_PX[0] + self.scale * (v @ self.right) / depth,
                         0.5 * VIEW_PX[1] - self.scale * (v @ self.up) / depth], axis=-1), depth  # fmt: skip

    def world(self, pixels: np.ndarray, depth: np.ndarray | float) -> np.ndarray:
        """The point at ``depth`` that lands on ``pixels`` (the inverse of `pixels`)."""
        pixels = np.asarray(pixels, dtype=np.float64)
        depth = np.broadcast_to(np.asarray(depth, dtype=np.float64), pixels.shape[:-1])
        x = (pixels[..., 0] - 0.5 * VIEW_PX[0]) / self.scale * depth
        y = (0.5 * VIEW_PX[1] - pixels[..., 1]) / self.scale * depth
        return (self.position + depth[..., None] * self.forward + x[..., None] * self.right
                + y[..., None] * self.up)  # fmt: skip


def _label_box(point_px: np.ndarray, text: str) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of a 3D label's box in pixels: Rerun 0.40 centres it under its point."""
    width = len(text) * LABEL_CHAR_PX + LABEL_PAD_PX
    x, y = float(point_px[0]), float(point_px[1])
    return x - width / 2, y + LABEL_DROP_PX, x + width / 2, y + LABEL_DROP_PX + LABEL_H_PX


class _Layout:
    """Where things go in the 3D view at its opening camera: the arm's footprint over the run (its link meshes'
    surfaces + link origins, every FOOTPRINT_ROWS-th instant), the tool path's, and the boxes placed so far."""

    def __init__(self, plan: Any, links: dict[str, np.ndarray], surfaces: dict[str, np.ndarray]) -> None:
        from scipy.ndimage import binary_dilation

        self.screen = _Screen(plan.eye)
        self.shape = (int(VIEW_PX[1]) // CELL_PX, int(VIEW_PX[0]) // CELL_PX)
        count = len(plan.seconds)
        picked = np.unique(np.linspace(0, count - 1, min(count, FOOTPRINT_ROWS)).round().astype(int))

        def arm_at(rows: np.ndarray) -> np.ndarray:
            clouds = []
            for link, pose in links.items():
                local = surfaces.get(link)
                if local is not None:
                    clouds.append(np.einsum("nij,mj->nmi", pose[rows, :3, :3], local).reshape(len(rows), -1, 3)
                                  + pose[rows, None, :3, 3])  # fmt: skip
                clouds.append(pose[rows, None, :3, 3])
            if plan.flange is not None and plan.tool_frame == plan.root:  # the flange → TCP stick
                share = np.linspace(0.0, 1.0, 12)[None, :, None]
                clouds.append(plan.flange[rows, None, :] + share * (plan.tool_xyz[rows] - plan.flange[rows])[:, None, :])
            return np.concatenate(clouds, axis=1).reshape(-1, 3)

        self.arm = binary_dilation(self._grid(arm_at(picked)), iterations=3)  # the whole run
        self.arm_first = binary_dilation(self._grid(arm_at(np.array([0]))), iterations=3)
        self.arm_last = binary_dilation(self._grid(arm_at(np.array([count - 1]))), iterations=3)
        self.tool_ok = plan.tool_frame == plan.root
        path = plan.tool_xyz if self.tool_ok else np.zeros((0, 3))
        if len(path) > 1:  # 8 points per segment, so the drawn polyline is covered, not just its samples
            share = np.linspace(0.0, 1.0, 8, endpoint=False)[None, :, None]
            path = np.vstack([(path[:-1, None, :] + share * np.diff(path, axis=0)[:, None, :]).reshape(-1, 3), path[-1:]])
        self.path = binary_dilation(self._grid(path), iterations=2) if len(path) else np.zeros(self.shape, bool)
        self.taken: list[tuple[float, float, float, float]] = []

    def _grid(self, points: np.ndarray) -> np.ndarray:
        grid = np.zeros(self.shape, dtype=bool)
        if not len(points):
            return grid
        xy, _ = self.screen.pixels(points)
        cells = np.floor(xy / CELL_PX).astype(int)
        inside = (cells[:, 0] >= 0) & (cells[:, 0] < self.shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < self.shape[0])
        grid[cells[inside, 1], cells[inside, 0]] = True
        return grid

    def _cells(self, grid: np.ndarray, box: tuple[float, float, float, float], pad: float = 0.0) -> int:
        """How many footprint cells fall in ``box`` (grown by ``pad`` px); a box off the view counts its outside."""
        left, top, right, bottom = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        outside = max(0.0, -left) + max(0.0, -top) + max(0.0, right - VIEW_PX[0]) + max(0.0, bottom - VIEW_PX[1])
        c0, r0 = max(int(left // CELL_PX), 0), max(int(top // CELL_PX), 0)
        c1, r1 = min(int(np.ceil(right / CELL_PX)), self.shape[1]), min(int(np.ceil(bottom / CELL_PX)), self.shape[0])
        inside = int(grid[r0:r1, c0:c1].sum()) if r1 > r0 and c1 > c0 else 0
        return inside + int(1000 * outside)

    def _overlap(self, box: tuple[float, float, float, float]) -> float:
        return sum(max(0.0, min(box[2], o[2]) - max(box[0], o[0])) * max(0.0, min(box[3], o[3]) - max(box[1], o[1]))
                   for o in self.taken)  # fmt: skip

    def legend(self, rows: int, widest: int) -> np.ndarray:
        """The legend's label points, (rows, 3) top to bottom, at the depth of the camera's look target, in the free
        box nearest the bottom of the view (then nearest its middle, so a narrower window keeps it), clear of
        everything the arm and the tool path cover in the run by LEGEND_CLEAR_PX. If no box is clear, the least
        covered one (NOTES says so)."""
        width = widest * LABEL_CHAR_PX + LABEL_PAD_PX
        pitch = LABEL_H_PX + 2.0
        height = rows * pitch
        busy = self.arm | self.path
        best = None
        for top in np.arange(8.0, VIEW_PX[1] - height - 8.0, 6.0):
            for left in np.arange(8.0, VIEW_PX[0] - width - 8.0, 6.0):
                box = (left, top, left + width, top + height)
                hits = self._cells(busy, box, LEGEND_CLEAR_PX)
                score = (hits, -(top + height), abs(left + width / 2 - VIEW_PX[0] / 2))
                if best is None or score < best[0]:
                    best = (score, box)
        box = best[1]
        self.legend_hits = best[0][0]
        self.taken.append(box)
        centre = 0.5 * (box[0] + box[2])
        pixels = np.array([[centre, box[1] + r * pitch - LABEL_DROP_PX] for r in range(rows)])
        depth = float((self.screen.look - self.screen.position) @ self.screen.forward)
        return self.screen.world(pixels, depth)

    def end_label(self, xyz: np.ndarray, text: str, first: bool) -> tuple[np.ndarray, np.ndarray | None]:
        """A start / end label's point beside the path's end ``xyz``, off the arm where it stands at that end (and as
        far as it can be off the arm over the run, the path and the legend), and the leader's far end (None when the
        label sits on its end). WHY (the check of 2026-11-24): on its end, 'end' sat on the wrist once the arm got
        there (2.4 s, 3.2 s)."""
        (end_px,), (depth,) = self.screen.pixels(xyz[None])
        here = self.arm_first if first else self.arm_last
        best = None
        for distance in (0.0, 14.0, 22.0, 32.0, 44.0, 58.0, 74.0):
            for angle in np.radians(np.arange(0.0, 360.0, 22.5)) if distance else [0.0]:
                centre = end_px + distance * np.array([np.cos(angle), -np.sin(angle)])
                point = centre - [0.0, LABEL_DROP_PX + LABEL_H_PX / 2]
                box = _label_box(point, text)
                cost = (60.0 * self._cells(here, box) + 3.0 * self._cells(self.arm, box)
                        + 30.0 * self._cells(self.path, box, -2.0) + 5.0 * self._overlap(box) + distance)
                if best is None or cost < best[0]:
                    best = (cost, point, box)
        _, point, box = best
        self.taken.append(box)
        leader = None
        nearest = np.clip(end_px, [box[0], box[1]], [box[2], box[3]])
        if float(np.linalg.norm(nearest - end_px)) > 6.0:
            leader = self.screen.world(nearest[None], depth)[0]
        return self.screen.world(point[None], depth)[0], leader


def _log_tool(plan: Any, recording: rr.RecordingStream, layout: "_Layout") -> None:
    """The stock tool path (travelled solid, still to go faint, flange → TCP stick) in neutral slate: colour = limits.
    start / end: a dot on each end, its label beside it off the arm (`_Layout.end_label`), a thin leader between."""
    part = plan.part
    frame = rr.CoordinateFrame(f"{part}/{plan.tool_frame}")
    xyz = plan.tool_xyz
    last = len(xyz) - 1
    picked = np.unique(np.linspace(0, last, min(last + 1, viz._ROWS)).round().astype(int))

    def thin(first: int, end: int) -> np.ndarray:
        return xyz[np.unique(np.linspace(first, end, min(end - first + 1, viz._VERTICES)).round().astype(int))]

    at = [rr.TimeColumn(TIMELINE, duration=plan.tool_t[picked])]
    for entity, colour, radius, strips in (
        ("path", TO_GO, 0.003, [thin(row, last) for row in picked]),
        ("trail", TRAVELLED, 0.0045, [thin(0, row) for row in picked]),
    ):
        path = f"/world/{part}/tool/{entity}"
        recording.log(path, rr.LineStrips3D.from_fields(colors=[colour], radii=[radius]), frame, static=True)
        recording.send_columns(path, indexes=at, columns=rr.LineStrips3D.columns(strips=strips))
    if plan.flange is not None:
        stick = f"/world/{part}/tool/stick"
        recording.log(stick, rr.LineStrips3D.from_fields(colors=[viz._STICK], radii=[0.004]), frame, static=True)
        recording.send_columns(stick, indexes=at, columns=rr.LineStrips3D.columns(
            strips=[np.stack([plan.flange[row], xyz[row]]) for row in picked]))
    if not layout.tool_ok:  # a tool in a moving frame: the labels on their ends, as the stock does
        recording.log(f"/world/{part}/tool/ends", rr.Points3D([xyz[0], xyz[-1]], labels=["start", "end"],
                                                              colors=[TRAVELLED, TRAVELLED], radii=[0.007]),
                      frame, static=True)  # fmt: skip
        return
    recording.log(f"/world/{part}/tool/ends", rr.Points3D([xyz[0], xyz[-1]], colors=[TRAVELLED, TRAVELLED],
                                                          radii=[0.007]), frame, static=True)  # fmt: skip
    labels, leaders = [], []
    for index, text in ((0, "start"), (last, "end")):
        point, leader = layout.end_label(xyz[index], text, first=index == 0)
        labels.append(point)
        if leader is not None:
            leaders.append(np.stack([xyz[index], leader]))
    recording.log(f"/world/{part}/tool/end_labels", rr.Points3D(labels, labels=["start", "end"],
                                                                colors=[TRAVELLED, TRAVELLED], radii=[0.0006],
                                                                show_labels=True), frame, static=True)  # fmt: skip
    if leaders:
        recording.log(f"/world/{part}/tool/end_leaders", rr.LineStrips3D(leaders, colors=[TRAVELLED], radii=[0.0012]),
                      frame, static=True)  # fmt: skip


# ── the plots ───────────────────────────────────────────────────────────────────────────────────────────────


def _constant(recording: rr.RecordingStream, path: str, seconds: np.ndarray, values: list[float], names: list[str],
              colours: Any, width: float = 1.0) -> None:
    """Horizontal lines across the run, all instances of one entity (a colour each, or one for all): limits, the 80 %
    and 95 % lines. WHY one entity: every entity is ~3 chunks once `_write_opening_at` splits it, and at ~770 chunks
    the headless 0.40 viewer had not ingested the file 14 s after opening it (the zones of an unopened tab missing)."""
    colours = list(colours) if isinstance(colours, list) else [colours] * len(values)
    recording.log(path, rr.SeriesLines(names=names, colors=colours, widths=[width] * len(values)), static=True)
    recording.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=[seconds[0], seconds[-1]])],
                           columns=rr.Scalars.columns(scalars=np.array([values, values]).reshape(-1)).partition(
                               [len(values)] * 2))


def _bands(recording: rr.RecordingStream, path: str, seconds: np.ndarray,
           bands: list[tuple[float, float, Any, str, int]]) -> None:
    """Shaded bands across the run, as instances of one entity: each (low, high, colour, name, layers) is the stock
    `band` (a Measurements mean ± std, its centre line hidden), drawn ``layers`` times over itself so it reads at full
    frame (see NEAR_BAND); later bands are drawn over earlier ones."""
    flat = [(low, high, colour, name) for low, high, colour, name, layers in bands for _ in range(layers)]
    count = len(flat)
    recording.log(path, rr.Measurements.from_fields(colors=[b[2] for b in flat], names=[b[3] for b in flat],
                                                    widths=[0.0] * count), static=True)  # fmt: skip
    values = [0.5 * (low + high) for low, high, _, _ in flat]
    variances = [(0.5 * (high - low)) ** 2 for low, high, _, _ in flat]
    recording.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=[seconds[0], seconds[-1]])],
                           columns=rr.Measurements.columns(values=values * 2, variances=variances * 2)
                           .partition([count, count]))  # fmt: skip


def _zones(centre: float, half: float, edges: tuple[float, float]) -> list[tuple[float, float, Any, str, int]]:
    """The amber 80-95 % and red ≥ 95 % zones of one limit pair (centre ± half), both sides, as `_bands` takes them.
    WHY red out to the strip's edge (``edges``) and not to 100 %: red is "≥ 95 %" on the arm, past the limit too, and a
    95-100 % sliver was 1-2 px in a strip (the check of 2026-11-24); the limit itself stays a line."""
    out = []
    for sign, edge in ((1.0, edges[1]), (-1.0, edges[0])):
        near, at = centre + sign * half * NEAR / 100.0, centre + sign * half * AT / 100.0
        out.append((min(near, at), max(near, at), NEAR_BAND, "80-95 % of limit", ZONE_LAYERS))
        far = edge + 0.1 * sign * abs(edge - centre)
        if sign * (far - at) > 0:  # else the strip ends before 95 %: nothing to shade
            out.append((min(at, far), max(at, far), AT_BAND, "≥ 95 % of limit", ZONE_LAYERS))
    return out


def _log_zones(plan: Any, recording: rr.RecordingStream | None) -> dict[tuple[str, int], list[str]]:
    """In each q / qd / qdd strip, the 80-95 % (amber) and ≥ 95 % (red) zones of the joint's limits, both sides, in
    the strip's units, as one entity `_band` ("_band" sorts first, so it is drawn under the lines; see TARGET_PART).
    Returns {(short, joint index): entities} to add to the strips; ``recording=None`` only lists them (the blueprint
    is written before the data)."""
    out: dict[tuple[str, int], list[str]] = {}
    for short, tab, field_name, _ in viz._FIELDS:
        if short not in SHORTS or plan.signals[short] is None:
            continue
        for index, joint in enumerate(plan.joints):
            low, high = (bound[index] * plan.scale[index] for bound in plan.limits[short])
            if not (np.isfinite(low) and np.isfinite(high) and high > low):
                continue
            path = f"/{field_name}/{viz._part(joint)}/_band"
            if recording is not None:
                y_range = plan.tabs[tab][index].y_range or (low, high)
                _bands(recording, path, plan.seconds, _zones(0.5 * (low + high), 0.5 * (high - low), y_range))
            out[(short, index)] = [path]
    return out


def _pct_span(lit: Lit) -> float:
    """The "% of limit" strips' half range: a quarter past ±100 %, or past the worst peak (the stock cards' rule)."""
    return max(125.0, float(np.ceil(np.nanmax(lit.worst) / 10.0) * 10.0 + 15.0))


def _log_pct(plan: Any, lit: Lit, recording: rr.RecordingStream, target_lit: Lit | None, key: str) -> None:
    """The "% of limit" tab's data: per joint, q / qd / qdd % as three instances of one entity (the stock card
    pattern, so the legend reads q, qd, qdd), the target's the same, faint; the shaded ±100 % band, the amber / red
    zones, the 80 % / 95 % / 100 % lines; the lanes (one per joint, Rerun's state timeline); the key."""
    seconds = plan.seconds
    on_t = [rr.TimeColumn(TIMELINE, duration=seconds)]
    span = _pct_span(lit)
    for index, joint in enumerate(plan.joints):
        base = f"/pct/{viz._part(joint)}"
        for who, source, faint in ((TARGET_PART, target_lit, True), (plan.part, lit, False)):
            if source is None:
                continue
            shown = [short for short in SHORTS if np.isfinite(source.pct[short][:, index]).any()]
            if not shown:
                continue
            percent = np.stack([source.pct[short][:, index] for short in shown], axis=1)
            names = [f"{short} target" if faint else short for short in shown]
            colours = [TARGET_RGB if faint else CARD_STYLE[short][0] for short in shown]
            widths = [1.0 if faint else CARD_STYLE[short][1] for short in shown]
            # the target goes twice: here, and under the stock cards of the q / qd / qdd tab ("_target" sorts before
            # the cards' own entity, so it is drawn under them; see TARGET_PART)
            for entity in [f"{base}/{who}"] + ([f"/limit_pct/{viz._part(joint)}/{who}"] if faint else []):
                recording.log(entity, rr.SeriesLines(names=names, colors=colours, widths=widths), static=True)
                recording.send_columns(entity, indexes=on_t,
                                       columns=rr.Scalars.columns(scalars=percent.reshape(-1)).partition(
                                           [len(shown)] * len(seconds)))
        # WHY one layer of slate for ±100 %: the in-limit area reads as a band, and the q / qd / qdd lines stay crisp
        _bands(recording, f"{base}/_band", seconds,
               [(-100.0, 100.0, PCT_BAND, "within ±100 % of limit", 1)] + _zones(0.0, 100.0, (-span, span)))
        _constant(recording, f"{base}/lines", seconds, [NEAR, -NEAR, AT, -AT, 100.0, -100.0],
                  ["80 %", "-80 %", "95 %", "-95 %", "limit", "-limit"],
                  [NEAR_RGB, NEAR_RGB, AT_RGB, AT_RGB, LIMIT_LINE, LIMIT_LINE], 1.0)  # fmt: skip

    # the lanes: one entity, one string component per joint, each a lane of the state timeline by a visualizer
    # mapping (`_lanes_view`). WHY (the check of 2026-11-24): a lane is labelled with its entity path and lanes sort by
    # it, so one entity per joint read "/tint/1_shoulder_pan"; a mapped component reads "/joint (shoulder_pan)", in
    # the order the blueprint lists them
    for index, joint in enumerate(plan.joints):
        states = [_state(lit, k, index) for k in range(len(seconds))]
        change = [k for k in range(len(states)) if k == 0 or states[k] != states[k - 1]]
        recording.send_columns(LANES, indexes=[rr.TimeColumn(TIMELINE, duration=seconds[change])],
                               columns=rr.AnyValues.columns(**{_short(joint): [states[k] for k in change]}))
    recording.log(LANES, STATE_STYLE, static=True)
    recording.log(KEY, rr.TextDocument(key, media_type="text/markdown"), static=True)

    # the moment closest to a limit, on its joint's strip
    k, j = lit.k, lit.j
    if lit.level[k, j] < 0:
        return
    short = SHORTS[lit.which[k, j]]
    path = f"/pct/{viz._part(plan.joints[j])}/closest"
    recording.log(path, rr.SeriesPoints(names=f"closest to a limit: {lit.moment(plan)}", colors=[AT_RGB],
                                        markers=["diamond"], marker_sizes=[7.0]), static=True)
    recording.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=[seconds[k]])],
                           columns=rr.Scalars.columns(scalars=[float(lit.pct[short][k, j])]))


LANES, KEY = "/joint", "/key/limits"
OPENS_ON_SCREEN = ("/world", "/pct", LANES, KEY)  # the 3D view and the "% of limit" tab: `_write_opening_at`


def _state(lit: Lit, k: int, j: int) -> str:
    level = lit.level[k, j]
    if level < 0:
        return "no limit"
    if level == 0:
        return "ok"
    return f"{'near' if level == 1 else 'at'} {SHORTS[lit.which[k, j]]}"


_STATE_VALUES = ["ok"] + [f"near {s}" for s in SHORTS] + [f"at {s}" for s in SHORTS] + ["no limit"]
STATE_STYLE = rr.StateConfiguration(
    values=_STATE_VALUES,
    # WHY short: a lane segment is often a few pixels wide; the colour is the level, the text only says which quantity
    labels=["ok"] + list(SHORTS) + list(SHORTS) + ["no limit"],
    colors=[OK_RGB] + [NEAR_RGB] * 3 + [AT_RGB] * 3 + [NO_LIMIT_RGB],
)


def _lanes_view(plan: Any, name: str) -> Any:
    from rerun.blueprint.encodings import VisualizerComponentMapping

    lanes = [rr.StateChange.from_fields().visualizer(mappings=[VisualizerComponentMapping(
        target="StateChange:state", source_kind="SourceComponent", source_component=_short(joint))])
        for joint in plan.joints]  # fmt: skip
    return rrb.StateTimelineView(origin="/", contents=[LANES], name=name, overrides={LANES: lanes})


def _log_target_series(plan: Any, target: JointTrajectory, recording: rr.RecordingStream) -> None:
    """The target as faint lines in the q / qd / qdd / qddd strips: the stock series under the name `target`."""
    viz._series(target, TARGET_PART, recording, degrees=plan.revolute, color=TARGET_RGB, label="target")
    if target.accelerations is not None:
        jerk = viz._slope(np.asarray(target.accelerations, dtype=np.float64), plan.seconds)
        for index, joint in enumerate(plan.joints):
            entity = f"/jerks/{viz._part(joint)}/{TARGET_PART}"
            recording.log(entity, rr.SeriesLines(names="target", colors=TARGET_RGB), static=True)
            recording.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                                   columns=rr.Scalars.columns(scalars=jerk[:, index] * plan.scale[index]))


def _log_target_tcp(target_plan: Any, recording: rr.RecordingStream, notes: "_Notes") -> None:
    on_t = [rr.TimeColumn(TIMELINE, duration=target_plan.tool_t)]
    for group, axes in (("position_mm", ["x", "y", "z"]), ("orientation_deg", ["roll", "pitch", "yaw"])):
        entity = f"/tcp/{group}/{TARGET_PART}"
        # WHY "(under)": the legend lists the target, which is drawn but hidden under the run (the title says by how
        # much); a bare "x target" promised a line nobody could find (the check of 2026-11-24)
        under = " (under)" if notes.tcp_under.get(group) else ""
        recording.log(entity, rr.SeriesLines(names=[f"{a} target{under}" for a in axes], colors=[TARGET_RGB] * 3,
                                             widths=[1.0] * 3), static=True)  # fmt: skip
        recording.send_columns(entity, indexes=on_t, columns=rr.Scalars.columns(
            scalars=target_plan.tcp[group].reshape(-1)).partition([3] * len(target_plan.tool_t)))
    for group in ("speed_mm_s", "angular_speed_deg_s"):
        entity = f"/tcp/{group}/{TARGET_PART}"
        recording.log(entity, rr.SeriesLines(names="target", colors=TARGET_RGB, widths=1.0), static=True)
        recording.send_columns(entity, indexes=on_t, columns=rr.Scalars.columns(scalars=target_plan.tcp[group]))


# ── what the titles say: the target, the moment ───────────────────────────────────────────────────────────────


def _sig(value: float) -> str:
    return f"{value:.0f}" if value >= 10 else f"{value:.1f}" if value >= 1 else f"{value:.2f}"


def _on(values: np.ndarray, t_from: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """``values`` (N, …) sampled at ``t_from``, on ``t_to`` (the target's samples on the run's)."""
    if len(t_from) == len(t_to) and np.allclose(t_from, t_to):
        return values
    flat = values.reshape(len(t_from), -1)
    out = np.stack([np.interp(t_to, t_from, flat[:, k]) for k in range(flat.shape[1])], axis=1)
    return out.reshape((len(t_to),) + values.shape[1:])


class _Notes:
    """Per strip, whether the target shows beside the run or sits under it (closer than UNDER_SHARE of the strip's
    height), and the title words for each. WHY (the check of 2026-11-24): "pale = target" in a strip whose target is
    0.6° off a 450° axis promised a line nobody could see; now such a title says "target under the run (≤ 0.62°)"."""

    def __init__(self, plan: Any, lit: Lit, target_plan: Any | None, target_lit: Lit | None) -> None:
        self.strip: dict[tuple[str, int], str] = {}
        self.card: dict[int, str] = {}
        self.pct_shown: list[str] = []  # the quantities whose target shows in the "% of limit" strips
        self.pct_under: list[str] = []
        self.tcp: dict[str, str] = {}
        self.tcp_under: dict[str, bool] = {}
        self.target = target_plan is not None
        if target_plan is None:
            return
        seconds = plan.seconds
        for short, tab, _, rate in viz._FIELDS:
            if plan.signals[short] is None or target_plan.signals[short] is None or tab not in plan.tabs:
                continue
            target = _on(target_plan.signals[short], target_plan.seconds, seconds)
            for index in range(len(plan.joints)):
                y_range = plan.tabs[tab][index].y_range
                scale = plan.scale[index]
                gap = float(np.nanmax(np.abs(plan.signals[short][:, index] - target[:, index]))) * scale
                span = (y_range[1] - y_range[0]) if y_range else float(np.ptp(plan.signals[short][:, index])) * scale
                unit = plan.unit(index, rate).strip()
                unit = unit if unit.startswith("°") else f" {unit}"
                self.strip[(short, index)] = (f" · target under the run (≤ {_sig(gap)}{unit})"
                                              if gap < UNDER_SHARE * span else " · pale = target")  # fmt: skip
        span = 2.0 * _pct_span(lit)
        card_span = 2.0 * getattr(plan, "card_span", 125.0)
        cards_shown: dict[int, list[str]] = {}
        for short in SHORTS:
            target = _on(target_lit.pct[short], target_plan.seconds, seconds)
            gaps = np.abs(lit.pct[short] - target)
            if not np.isfinite(gaps).any():
                continue
            gaps = np.where(np.isfinite(gaps), gaps, 0.0)
            (self.pct_shown if gaps.max() >= UNDER_SHARE * span else self.pct_under).append(short)
            for index in range(len(plan.joints)):
                if gaps[:, index].max() >= UNDER_SHARE * card_span:
                    cards_shown.setdefault(index, []).append(short)
        for index in range(len(plan.joints)):
            shown = cards_shown.get(index, [])
            self.card[index] = f" · pale = {' / '.join(shown)} target" if shown else " · target under the run"
        for group, unit in (("position_mm", " mm"), ("orientation_deg", "°"), ("speed_mm_s", " mm/s"),
                            ("angular_speed_deg_s", "°/s")):
            run = plan.tcp[group]
            target = _on(target_plan.tcp[group], target_plan.tool_t, plan.tool_t)
            gap = float(np.nanmax(np.abs(run - target)))
            span = float(np.ptp(np.concatenate([run.ravel(), target.ravel()]))) or 1.0
            self.tcp_under[group] = gap < UNDER_SHARE * span
            self.tcp[group] = (f" · target under the run (≤ {_sig(gap)}{unit})" if self.tcp_under[group]
                               else " · pale = target")  # fmt: skip

    def pct_key(self) -> str:
        """The "% of limit" key's two lines. WHY this short: a line holds ~130 characters at 1600 × 1000 and the next
        wraps out of the panel (filmed)."""
        lanes = "**Lanes:** each joint's link colour over the run, labelled by the quantity that set it"
        if self.target and self.pct_shown:
            lanes += f" · pale line = {' / '.join(self.pct_shown)} target"
            if self.pct_under:
                lanes += f" ({', '.join(self.pct_under)}: under the run)"
        elif self.target:
            lanes += " · target: under the run"
        strips = ("**Strips:** q blue, qd teal, qdd grey in % of the joint's limits · slate ±100 % · amber 80-95 % · "
                  "red ≥ 95 %, past the limit too")
        return f"{lanes}  \n{strips}"


def _differenced(traj: JointTrajectory) -> bool:
    """True when the message's qd (and qdd) are central differences of its q (np.gradient), i.e. not a plan's own."""
    t, q = np.asarray(traj.t, dtype=np.float64), np.asarray(traj.positions, dtype=np.float64)
    if traj.velocities is None or len(t) < 3:
        return False
    qd = np.gradient(q, t, axis=0)
    same = np.allclose(np.asarray(traj.velocities, dtype=np.float64), qd, rtol=1e-9, atol=1e-12)
    if traj.accelerations is not None:
        same = same and np.allclose(np.asarray(traj.accelerations, dtype=np.float64), np.gradient(qd, t, axis=0),
                                    rtol=1e-9, atol=1e-12)  # fmt: skip
    return bool(same)


def _smoothed(plan: Any, lit: Lit) -> tuple[float, float] | None:
    """The moment's % again with q smoothed before the difference (Savitzky-Golay, order 2, 70 / 90 / 110 ms
    windows), the peak within 50 ms of the moment: (lowest, highest). None for a q moment or uneven samples."""
    from scipy.signal import savgol_filter

    short = SHORTS[lit.which[lit.k, lit.j]]
    step = np.diff(plan.seconds)
    if short == "q" or len(step) < 4 or np.ptp(step) > 1e-6 * max(float(step.mean()), 1e-12):
        return None
    step = float(step.mean())
    low, high = (bound[lit.j] for bound in plan.limits[short])
    near = np.abs(plan.seconds - lit.t) <= 0.05
    peaks = []
    for window_s in (0.07, 0.09, 0.11):
        window = int(round(window_s / step)) | 1
        if window < 5 or window > len(plan.seconds):
            continue
        smooth = savgol_filter(plan.signals["q"][:, lit.j], window, 2, deriv=SHORTS.index(short), delta=step)
        peaks.append(float(np.abs(viz._percent(smooth[near], low, high)).max()))
    return (min(peaks), max(peaks)) if peaks else None


def _opening(plan: Any, traj: JointTrajectory, lit: Lit, measured: bool) -> str:
    """The opening tab's title: the moment the file opens at, and, on a run whose qd / qdd are differences of its
    encoder q, that the number is that measured rate and what it is once smoothed. WHY (the check of 2026-11-24):
    wrist_2's 145 % qdd at 0.40 s read like a plan's limit violation; it is the run's measured acceleration, and still
    132-141 % smoothed over 70-110 ms, so a real overshoot of the gen-0 controller, not only quantisation noise."""
    title = f"◆ closest to limit: {lit.moment(plan, short=True)}"
    short = SHORTS[lit.which[lit.k, lit.j]] if lit.level[lit.k, lit.j] >= 0 else "q"
    if measured and short != "q" and _differenced(traj):
        # WHY this short: the title is cut at ~108 characters; the windows (70-110 ms) are in NOTES and `_smoothed`
        smoothed = _smoothed(plan, lit)
        title += " · measured (encoder q differenced" + (
            f"; smoothed {smoothed[0]:.0f}-{smoothed[1]:.0f} %)" if smoothed else ")")
    return title


# ── the dashboard ───────────────────────────────────────────────────────────────────────────────────────────


def _plot(title: str, contents: list[str], y_range: tuple[float, float] | None, legend: bool = False) -> Any:
    return rrb.TimeSeriesView(
        origin="/", contents=contents, name=title,
        plot_legend=rrb.PlotLegend(visible=legend, corner="RightBottom"),
        axis_x=rrb.TimeAxis(link="LinkToGlobal"),
        axis_y=rrb.ScalarAxis(range=y_range, zoom_lock=False) if y_range else None,
    )  # fmt: skip


def _dashboard(plan: Any, lit: Lit, zones: dict, notes: _Notes, *, label: str, opening: str) -> Any:
    # WHY every title this short (the check of 2026-11-24 found the TCP orientation's cut): a view's title is one line,
    # Rerun cuts the rest, and at 1600 × 1000 that is ~118 characters across the half page, ~50 in a half-width strip
    target = notes.target
    world = rrb.Spatial3DView(
        origin="/", contents=[f"/world/{plan.part}/**"], eye_controls=plan.eye,
        name=f"{label} · link colour = joint's worst % of limit: green < 80 · amber 80-95 · red ≥ 95",
    )  # fmt: skip
    span = _pct_span(lit)
    strips = []
    for index, joint in enumerate(plan.joints):
        # the peak's time is the ◆ / the lanes, "red" is the tint's own word for ≥ 95 %
        title = f"{_short(joint)} · "
        if lit.level[:, index].max() < 0:
            title += "no limit"
        else:
            k = int(np.argmax(lit.worst[:, index]))
            title += (f"peak {lit.worst[k, index]:.0f} % {SHORTS[lit.which[k, index]]} · "
                      f"{lit.at_share[index] * 100:.0f} % red")
        strips.append(_plot(title, [f"/pct/{viz._part(joint)}/**"], (-span, span)))
    lanes = _lanes_view(plan, opening)
    # WHY a key between the lanes and the strips: the strips' legends are off (a legend hid a third of a half-width
    # strip, the stock's R5), and the moment took the lanes' title; two lines, no title bar
    key = rrb.TextDocumentView(origin=KEY, name="key", titlebar=False)
    # WHY a grid of strips under full-width lanes: a lane is ~40 px (its name over its bar), so six lanes take ~290 px
    # of the ~900 px tab; six strips stacked under them got ~95 px each and lost their y ticks, two columns get ~190
    columns = 1 if len(strips) <= 3 else 2
    rows = -(-len(strips) // columns)
    limit_tab = rrb.Vertical(lanes, key, rrb.Grid(*strips, grid_columns=columns),
                             row_shares=[0.45 * len(plan.joints) + 0.45, 0.55, 2.0 * rows], name="% of limit")

    tabs = [limit_tab]
    for short, tab, field_name, _ in viz._FIELDS:
        if tab not in plan.tabs:
            continue
        views = []
        for index, strip in enumerate(plan.tabs[tab]):
            limits = f"/{field_name}/{viz._part(plan.joints[index])}/limits"
            contents = list(zones.get((short, index), [])) + [strip.contents[0], limits]
            title = strip.title
            if target:
                contents.append(f"/{field_name}/{viz._part(plan.joints[index])}/{TARGET_PART}")
                title += notes.strip.get((short, index), "")
            views.append(_plot(title, contents, strip.y_range))
        tabs.append(rrb.Vertical(*views, name=tab))
    if "q / qd / qdd" in plan.tabs:  # the stock tab as built: the playhead table over the cards
        cards = plan.tabs["q / qd / qdd"]
        table = rrb.TextDocumentView(origin=f"/notes/{plan.part}", name="at the playhead")
        columns = 1 if len(cards) <= 3 else 2
        rows = -(-len(cards) // columns)
        card_joints = [joint for joint in plan.joints
                       if any(strip.contents[0].split("/")[2] == viz._part(joint) for strip in cards)]

        def card(strip: Any) -> Any:  # the stock card (`/limit_pct/<joint>/<part>/**`) + the target's, pale, under it
            joint_part = strip.contents[0].split("/")[2]
            joint = next(j for j in card_joints if viz._part(j) == joint_part)
            title = strip.title.replace(joint, _short(joint), 1)  # the half-width card: short names keep it whole
            if not target:
                return _plot(title, strip.contents, strip.y_range)
            title += notes.card.get(plan.joints.index(joint), "")
            return _plot(title, [f"/limit_pct/{joint_part}/{TARGET_PART}", *strip.contents], strip.y_range)

        tabs.append(rrb.Vertical(table, rrb.Grid(*(card(s) for s in cards), grid_columns=columns),
                                 row_shares=[len(plan.joints) + 5, 8 * rows], name="q / qd / qdd"))  # fmt: skip
    speed, angular = plan.tcp["speed_mm_s"], plan.tcp["angular_speed_deg_s"]
    peak, turn = int(np.argmax(speed)), int(np.argmax(angular))
    titles = {  # the stock's, without the tool's source (the 3D view shows it), so the target note fits
        "position_mm": f"TCP position [mm] · x / y / z in {plan.tool_frame}",
        "orientation_deg": f"TCP orientation [°] · roll / pitch / yaw{plan.gimbal}",  # unwrapped, as the stock's
        "speed_mm_s": f"TCP speed [mm/s] · peak {speed[peak]:.0f} at {plan.tool_t[peak]:.2f} s",
        "angular_speed_deg_s": f"TCP angular speed [°/s] · peak {angular[turn]:.0f} at {plan.tool_t[turn]:.2f} s",
    }
    tcp = []
    for strip in plan.tabs["TCP"]:
        group = strip.contents[0].split("/")[2]
        contents = list(strip.contents) + ([f"/tcp/{group}/{TARGET_PART}"] if target else [])
        title = titles.get(group, strip.title) + (notes.tcp.get(group, "") if target else "")
        tcp.append(_plot(title, contents, strip.y_range, strip.legend))
    tabs.append(rrb.Vertical(*tcp, name="TCP"))
    return rrb.Blueprint(
        rrb.Horizontal(world, rrb.Tabs(*tabs, active_tab=0), column_shares=[1, 1]),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused", loop_mode="all"),
        collapse_panels=False,
    )


# ── the entry point ─────────────────────────────────────────────────────────────────────────────────────────


def save(path: str | Path, traj: JointTrajectory, *, robot: str | Path, tool: PoseTrajectory | None = None,
         target: JointTrajectory | None = None, target_tool: PoseTrajectory | None = None,
         extras: dict | None = None) -> dict:
    """Write the limit-lit recording of ``traj`` (the one that is lit) to ``path``; ``target`` (and ``target_tool``)
    are drawn as faint lines in every plot. Returns {"path", "closest_s", "closest"} (the moment every view marks)."""
    name = "solution" if target is not None else "plan"
    label = f"{name} {str((extras or {}).get('label', '')).split(':', 1)[0]}".strip()
    plan = viz._RobotPlan(traj, name, robot, tool)
    lit = Lit(plan)
    target_plan = viz._RobotPlan(target, "target", robot, target_tool) if target is not None else None
    target_lit = Lit(target_plan) if target_plan is not None else None
    notes = _Notes(plan, lit, target_plan, target_lit)
    opening = _opening(plan, traj, lit, measured=target is not None)
    blueprint = _dashboard(plan, lit, _log_zones(plan, None), notes, label=label, opening=opening)
    # everything is logged to a scratch file first, then written out in the order that opens it at the moment
    with tempfile.TemporaryDirectory(prefix="limit_lit_") as scratch_dir:
        scratch = Path(scratch_dir) / "scratch.rrd"
        stream = rr.RecordingStream(APPLICATION_ID)
        stream.save(str(scratch))
        layout = _log_all(plan, lit, target_lit, stream, traj=traj, name=name, target=target,
                          target_plan=target_plan, notes=notes)
        _write_opening_at(scratch, Path(path), blueprint, lit.t, {
            # WHY also a property: a host that can move the cursor (a notebook, the web viewer's
            # set_time_for_timeline, rerun.experimental.ViewerClient.set_time) reads the moment from the file
            "limit_lit": rr.AnyValues(closest_s=lit.t, closest=lit.moment(plan), near_pct=NEAR, at_pct=AT),
        })
    return {"path": str(path), "closest_s": lit.t, "closest": lit.moment(plan), "opening": opening,
            "legend_hits": layout.legend_hits}


def _write_opening_at(scratch: Path, path: Path, blueprint: Any, at_s: float, properties: dict) -> None:
    """Write ``scratch``'s chunks to ``path`` (blueprint first) so the viewer's time cursor starts at ``at_s``.

    WHY (V3's thesis: open AT the moment closest to a limit): Rerun 0.40 has no blueprint field for the time cursor
    (`TimePanel` takes timeline, play state, loop mode, speed, fps and a selection), and a `#when=t@…` fragment on a
    plain .rrd URL is ignored (measured, five spellings). What it does (observed, not documented): a paused viewer
    puts the cursor at the start of the range its timeline has when that timeline first appears, and keeps it there
    as more data streams in; one row at the moment sent first, followed at once by rows from 0 s, still opened at 0 s
    (the viewer ingests many chunks per frame). So every temporal chunk is split at ``at_s`` and the file holds, in
    order: the on-screen rows at or after ``at_s`` (the 3D view and the "% of limit" tab, earliest first: the first
    temporal row the viewer sees is the moment itself), then the static data (the URDF meshes, a few hundred kB, so the
    viewer ingests them over several frames), then the on-screen rows before ``at_s`` (the arm's first), then the other
    tabs' rows, after the moment and before it. The data is the same, only its order changed; a viewer that ingests the
    whole file in one frame would open at 0 s as before (and the ◆ / titles still name the moment). Measured with
    v3/opens_at.cjs in the real 0.40 web viewer: opens at the moment on every load (9 of 9 on the first build, and on
    this order see NOTES)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    from rerun.chunk import Chunk, RrdReader

    threshold = int(round(at_s * 1e9)) - 1_000  # ns; 1 µs of slack for the float → ns rounding (samples are ms apart)
    after: list[tuple[int, Any]] = []
    static: list[Any] = []
    before: list[Any] = []
    for chunk in RrdReader(scratch).stream().to_chunks():
        if chunk.entity_path.startswith("/__properties"):
            continue  # re-sent below, once, from the final stream
        if chunk.is_static or TIMELINE not in chunk.timeline_names:
            static.append(chunk)
            continue
        batch = chunk.to_record_batch()
        ns = pc.cast(batch.column(TIMELINE), pa.int64()).to_numpy(zero_copy_only=False)
        late = ns >= threshold
        if late.all():
            after.append((int(ns.min()), chunk))
        elif not late.any():
            before.append(chunk)
        else:  # `entity_path=` makes fresh row and chunk ids, so the two halves don't collide in the store
            after += [(int(ns[late].min()), half) for half in
                      Chunk.from_record_batch(batch.filter(pa.array(late)), entity_path=chunk.entity_path)]
            before += Chunk.from_record_batch(batch.filter(pa.array(~late)), entity_path=chunk.entity_path)
    after.sort(key=lambda pair: pair[0])
    # WHY the rows on screen at the opening (the 3D view, the "% of limit" tab) go first on both sides of the static
    # data, and the other tabs' rows (after the moment, then before it) last: the headless 0.40 viewer ingests a few
    # chunks per frame, and under load (load average ~90) it was still on the rows before the moment 12 s after opening,
    # so film.cjs read the timeline as 0.4 → 3.2 s and the hero's first frame drew the base alone. The other tabs are
    # clicked later. Among the rows before the moment: the arm's joints first, then its tint, the legend, the tool.
    def shown(chunk: Any) -> bool:
        return chunk.entity_path.startswith(OPENS_ON_SCREEN)

    def arm_first(chunk: Any) -> int:
        return 0 if "/joint_transforms/" in chunk.entity_path else 1 if chunk.entity_path.startswith("/world") else 2

    stream = rr.RecordingStream(APPLICATION_ID)
    # WHY default_blueprint at save (the stock's R4 finding): written first, the file opens paused on the layout
    stream.save(str(path), default_blueprint=blueprint)
    stream.send_chunks([chunk for _, chunk in after if shown(chunk)])
    stream.send_chunks(static)
    for property_name, values in properties.items():
        stream.send_property(property_name, values)
    stream.send_chunks(sorted((chunk for chunk in before if shown(chunk)), key=arm_first))  # stable: rows keep order
    stream.send_chunks([chunk for _, chunk in after if not shown(chunk)])
    stream.send_chunks([chunk for chunk in before if not shown(chunk)])
    stream.flush()
    stream.disconnect()


def _log_all(plan: Any, lit: Lit, target_lit: Lit | None, stream: rr.RecordingStream, *, traj: JointTrajectory,
             name: str, target: JointTrajectory | None, target_plan: Any | None, notes: _Notes) -> "_Layout":
    """Every entity of the recording, in no particular order (`_write_opening_at` orders the file)."""
    # the stock series (degrees for revolute joints), the jerk, the limit lines, the cards, the TCP, the table
    viz._series(traj, name, stream, degrees=plan.revolute, color=viz._INK, label=name)
    for index, joint in enumerate(plan.joints):
        if plan.signals["qddd"] is not None:
            entity = f"/jerks/{viz._part(joint)}/{plan.part}"
            stream.log(entity, rr.SeriesLines(names=name, colors=viz._INK), static=True)
            stream.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                                columns=rr.Scalars.columns(scalars=plan.signals["qddd"][:, index] * plan.scale[index]))
    for short, _, field_name, _ in viz._FIELDS:
        if plan.signals[short] is None:
            continue
        for index, joint in enumerate(plan.joints):  # the stock's lower_limit / upper_limit, as one entity
            sides = [(side, float(bound[index] * plan.scale[index]))
                     for side, bound in zip(("lower limit", "upper limit"), plan.limits[short], strict=True)]
            sides = [(side, value) for side, value in sides if np.isfinite(value)]
            if sides:
                _constant(stream, f"/{field_name}/{viz._part(joint)}/limits", plan.seconds,
                          [value for _, value in sides], [side for side, _ in sides], viz._LIMIT)
    _log_zones(plan, stream)
    for entity, names, colours, widths, percent in plan.card_data:
        stream.log(entity, rr.SeriesLines(names=names, colors=colours, widths=widths), static=True)
        stream.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                            columns=rr.Scalars.columns(scalars=percent.reshape(-1)).partition(
                                [percent.shape[1]] * len(plan.seconds)))
        viz.band(f"{entity}/limit", [0.0, float(plan.seconds[-1])], -100.0, 100.0, recording=stream,
                 color=viz._CARD_BAND, name="limit ±100 %")
    tool_t = [rr.TimeColumn(TIMELINE, duration=plan.tool_t)]
    for group, axes in (("position_mm", ["x", "y", "z"]), ("orientation_deg", ["roll", "pitch", "yaw"])):
        entity = f"/tcp/{group}/{plan.part}"
        stream.log(entity, rr.SeriesLines(names=axes, colors=list(viz._AXIS_COLORS)), static=True)
        stream.send_columns(entity, indexes=tool_t, columns=rr.Scalars.columns(scalars=plan.tcp[group].reshape(-1))
                            .partition([3] * len(plan.tool_t)))  # fmt: skip
    for group, colour in (("speed_mm_s", viz._INK), ("angular_speed_deg_s", viz._INK)):
        entity = f"/tcp/{group}/{plan.part}"
        stream.log(entity, rr.SeriesLines(names=group.split("_")[0], colors=colour, widths=1.6), static=True)
        stream.send_columns(entity, indexes=tool_t, columns=rr.Scalars.columns(scalars=plan.tcp[group]))
    table_t, tables = plan.tables
    stream.send_columns(f"/notes/{plan.part}", indexes=[rr.TimeColumn(TIMELINE, duration=table_t)],
                        columns=rr.TextDocument.columns(text=tables, media_type=["text/markdown"] * len(tables)))
    if target is not None:
        _log_target_series(plan, target, stream)
        _log_target_tcp(target_plan, stream, notes)

    _log_pct(plan, lit, stream, target_lit, notes.pct_key())
    layout = _log_arm(plan, lit, stream)
    _log_tool(plan, stream, layout)
    viz._PATHS.pop(id(stream), None)
    stream.flush()
    stream.disconnect()
    return layout


def main() -> None:
    sys.path.insert(0, str(ROUND))
    from fixture import URDF, plan, run  # the round's two scenarios (the dispatcher's)

    traj, tool = plan()
    print(save(HERE / "plan-dev-029.rrd", traj, robot=URDF, tool=tool, extras={"label": "workspace-dev-029"}))
    target, solution, target_tool, solution_tool, extras = run("p6s")
    print(save(HERE / "run-dev-029.rrd", solution, robot=URDF, tool=solution_tool, target=target,
               target_tool=target_tool, extras=extras))


if __name__ == "__main__":
    main()
