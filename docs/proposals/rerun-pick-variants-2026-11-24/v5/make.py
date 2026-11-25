#!/usr/bin/env python3
"""V5 · Tool first: the left half follows the tool, the right half opens on it.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v5/make.py

Writes v5/plan-dev-029.rrd (the dataset tour alone) and v5/run-dev-029.rrd (the Trajectory Tracking Agent's p6s run:
the solution drawn, the target beside it). Zach's frame is kept (CONTRACT.md): the URDF arm in 3D on the left half,
tabs on the right half. Inside it, everything is about the tool point:

- 3D: a TCP triad (x red, y green, z blue) and a point at the playhead, labelled (dark text, right beside the TCP on
  the side away from the arm, never on it) with its speed, the whole tool path coloured by tool speed (purple slow →
  lime fast, the scale in the view's title and in the TCP tab's speed strip, which is drawn on the same colours), a
  bold trail of only the last TRAIL_S seconds, a camera framed on the tool's workspace (the arm still whole in view).
  On the agent's run: the error vectors (target → solution) in magenta, drawn ×N from the target's tool point, N in
  the title; bold at the playhead, faint every 0.1 s away from it; the target's path itself only where it parts from
  the solution's by more than a line's width (never, on a mm run).
- Tabs: TCP (a readout at the playhead, x/y/z mm, roll/pitch °, yaw ° on its own strip, speed mm/s, angular speed
  °/s), Tool error (the agent's own ruler mm, the tool point's error vector mm, the orientation error °; run only),
  then V1's q · qd · qdd · qddd · q/qd/qdd.
- Every plot shows a following window, ±WINDOW_S around the playhead, so the cursor sits mid-plot while it plays.

Built from robot_msgs.viz.rerun's own pieces by import (`_RobotPlan` for the series, limits, cards, table and TCP
numbers; `_log_robot` for the arm and the stock series; `_Strip` for V1's strip titles and ranges); robot_msgs is not
edited. Only the tool layer, the TCP / Tool error tabs, the camera and the following-window axes are this file's own.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb
import rerun.urdf as rurdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fixture import URDF, plan as plan_scenario, run as run_scenario  # noqa: E402

from robot_msgs.geometry.rotations import quat_angle  # noqa: E402
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory  # noqa: E402
from robot_msgs.viz import rerun as viz  # noqa: E402

APPLICATION_ID = "rerun_pick_v5"
TIMELINE = viz.TIMELINE
WINDOW_S = 1.0  # the plots' following window: this many seconds either side of the playhead
TRAIL_S = 0.5  # the bold trail: the tool path of the last TRAIL_S seconds (data-ui trajectory3d's decay, Zach Oct 28)
TRIAD_M = 0.08  # the TCP triad's arm length
# WHY viridis cut at 0.875: its last stop (yellow) vanishes on the light theme the viewer opens in; purple → lime reads
# on both themes, and no step of it is amber or red (Zach's calm-UI rule: those mean a problem, speed is not one)
_SPEED_STOPS = np.array([[68, 1, 84], [71, 44, 122], [59, 82, 139], [44, 114, 142], [33, 145, 140], [39, 173, 129],
                         [92, 200, 99], [170, 220, 50]], dtype=float)
_TARGET = (168, 172, 182)  # the target's tool path and target lines: pale and opaque (a line alpha draws darker in 0.40)
_TARGET_AXES = ((236, 160, 160), (150, 205, 160), (150, 175, 236))  # x / y / z (roll / pitch / yaw), pale, for target
# WHY magenta (the check, 2026-11-24): the first build's rose sat beside the triad's red x arrow and read as it; magenta
# is ~60° of hue from red and ~80° from the triad's blue, and far lighter and more saturated than the slow end of the
# speed scale (a dark purple)
_ERROR = (200, 30, 200)
_ERROR_FAINT = (230, 160, 230)
_LABEL = (46, 48, 58)  # the playhead label's text: neutral and dark (Rerun draws a label in its point's colour)
_STICK = (90, 90, 100)
_ENDS = (120, 124, 136)
PATH_R, TRAIL_R, TARGET_R = 0.0028, 0.0085, 0.0016  # line radii [m]: the whole path, the bold trail, the target path
_AXIS_COLORS = viz._AXIS_COLORS
_ROWS = 400  # at most this many playhead readouts (between two, the latest holds)


def _speed_rgb(speed: np.ndarray, top: float) -> np.ndarray:
    """mm/s → RGB on the cut viridis: 0 → purple, `top` → lime."""
    scaled = np.clip(np.nan_to_num(speed / max(top, 1e-9)), 0.0, 1.0) * (len(_SPEED_STOPS) - 1)
    low = np.minimum(np.floor(scaled).astype(int), len(_SPEED_STOPS) - 2)
    mix = (scaled - low)[:, None]
    return (_SPEED_STOPS[low] * (1.0 - mix) + _SPEED_STOPS[low + 1] * mix).round().astype(np.uint8)


def _nice_gain(wanted: float) -> int:
    """The magnification for the error vectors: a round 1 / 2 / 5 × 10^k at or below `wanted`, at least 1."""
    if not np.isfinite(wanted) or wanted <= 1.0:
        return 1
    exponent = 10.0 ** np.floor(np.log10(wanted))
    return int(max(m * exponent for m in (1.0, 2.0, 5.0) if m * exponent <= wanted))


class _Without:
    """The recording, minus the entities V5 draws its own way: V1's tool path (`/world/<name>/tool/...`) and its
    one-colour speed series (`/tcp/speed_mm_s/<name>`, here drawn on the path's speed colours instead).

    WHY a filter and not a copy of `_log_robot`: everything else it logs (the stock series in degrees, the jerk, the
    limit lines, the cards and their band, the playhead table, the URDF arm) is exactly V1's, and stays robot_msgs'."""

    def __init__(self, stream: rr.RecordingStream, *prefixes: str) -> None:
        self._stream, self._prefixes = stream, tuple(prefix.strip("/") for prefix in prefixes)

    def _kept(self, path: Any) -> bool:
        return not str(path).strip("/").startswith(self._prefixes)

    def log(self, path: Any, *args: Any, **kwargs: Any) -> None:
        if self._kept(path):
            self._stream.log(path, *args, **kwargs)

    def send_columns(self, path: Any, *args: Any, **kwargs: Any) -> None:
        if self._kept(path):
            self._stream.send_columns(path, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class _Tool:
    """The tool point worked out once (pure, so the blueprint can be written before the data): the solution's path,
    speed and colours from `plan`, the target's beside it when given, their error, and the camera on the tool."""

    def __init__(self, plan: Any, target_plan: Any | None, extras: dict | None) -> None:
        self.t = plan.tool_t
        self.xyz = plan.tool_xyz
        self.speed = plan.tcp["speed_mm_s"]
        self.top = max(float(self.speed.max()), 1.0)
        self.rgb = _speed_rgb(self.speed, self.top)
        self.peak = int(np.argmax(self.speed))
        self.angular = plan.tcp["angular_speed_deg_s"]
        n = len(self.t)
        self.target_xyz = self.target_rpy = self.target_speed = self.target_angular = None
        self.error_mm = self.angle_deg = None
        self.ruler = self.ruler_rms = None
        self.gain = 1
        self.target_strips: list[np.ndarray] = []  # the target path, only where it parts from the solution's
        if target_plan is not None:
            def on_t(values: np.ndarray) -> np.ndarray:
                values = np.asarray(values, dtype=np.float64).reshape(len(target_plan.tool_t), -1)
                return np.stack([np.interp(self.t, target_plan.tool_t, values[:, k]) for k in range(values.shape[1])],
                                axis=1)
            self.target_xyz = on_t(target_plan.tool_xyz)
            self.target_rpy = on_t(target_plan.tcp["orientation_deg"])
            self.target_speed = on_t(target_plan.tcp["speed_mm_s"])[:, 0]
            self.target_angular = on_t(target_plan.tcp["angular_speed_deg_s"])[:, 0]
            self.error_mm = (self.xyz - self.target_xyz) * 1000.0
            if len(target_plan.tool_t) == n:
                self.angle_deg = np.degrees(quat_angle(np.asarray(target_plan.tool_quat), np.asarray(plan.tool_quat)))
            norm = np.linalg.norm(self.error_mm, axis=1)
            extent = float(np.ptp(np.vstack([self.xyz, self.target_xyz]), axis=0).max())
            # WHY ×N to about a seventh of the workspace: mm errors on a 0.6 m path are invisible at true scale
            self.gain = _nice_gain(0.15 * extent * 1000.0 / max(float(norm.max()), 1e-6))
            # WHY only where it parts (the check, 2026-11-24): Rerun 0.40 draws a line as a camera-facing ribbon, so a
            # target line running inside the solution's drew ON TOP of it and turned the fastest stretch's speed colour
            # grey. A target segment is drawn only where the two lines cannot overlap (farther apart than the bold
            # trail's half-width + its own); everywhere else the ×N arrows show the deviation. No offset is invented.
            apart = norm / 1000.0 > TRAIL_R + TARGET_R
            segments = np.flatnonzero(apart[:-1] & apart[1:])
            for run in np.split(segments, np.flatnonzero(np.diff(segments) > 1) + 1) if segments.size else []:
                self.target_strips.append(self.target_xyz[run[0]:run[-1] + 2])
        if extras and extras.get("tool_error_mm") is not None and len(extras["tool_error_mm"]) == len(plan.seconds):
            self.ruler = np.asarray(extras["tool_error_mm"], dtype=np.float64)
            self.ruler_rms = extras.get("rms_mm")

    @property
    def norm_mm(self) -> np.ndarray | None:
        return None if self.error_mm is None else np.linalg.norm(self.error_mm, axis=1)


def _quaternions(tool: PoseTrajectory | None, plan: Any) -> np.ndarray:
    """The tool's orientations as xyzw quaternions on plan.tool_t (the PoseTrajectory's own, else FK's)."""
    from robot_msgs.geometry.rotations import quat_from_matrix

    if tool is not None:
        return np.asarray(tool.orientations, dtype=np.float64)
    tree = rurdf.UrdfTree.from_file_path(plan.urdf)
    links = viz._forward_kinematics(tree, plan.values, len(plan.seconds))
    return quat_from_matrix(links[plan.tool_label][:, :3, :3])


def _tool_eye(plan: Any, tool: _Tool) -> tuple[Any, "_Screen"]:
    """A camera on the tool's workspace, the whole arm still in view at every sample; and the same camera as a
    `_Screen`, which places the labels.

    Look along the normal of the plane the tool path lies closest to, so its shape reads instead of being seen edge-on
    (turned 35° off it, from the side away from the base, 25–50° above the horizon); then move in as close as the arm
    allows: every link origin at every sample (padded by a link's thickness) and the path inside the view, the content
    centred. WHY not V1's `_eye` (a sphere about the swept arm, 2.35 radii, profile): it frames the arm, and the path is
    a small loop inside it; here the direction is the path's and the distance is the tightest the arm allows."""
    tree = rurdf.UrdfTree.from_file_path(plan.urdf)
    links = viz._forward_kinematics(tree, plan.values, len(plan.seconds))
    paths = tool.xyz if tool.target_xyz is None else np.vstack([tool.xyz, tool.target_xyz])
    middle = 0.5 * (paths.min(axis=0) + paths.max(axis=0))
    _, _, vt = np.linalg.svd(paths - paths.mean(axis=0), full_matrices=False)
    normal = vt[-1]
    outward = middle[:2] / max(float(np.linalg.norm(middle[:2])), 1e-9)
    horizontal = normal[:2] if np.linalg.norm(normal[:2]) > 0.2 else outward
    horizontal = horizontal / np.linalg.norm(horizontal)
    if horizontal @ outward < 0:
        horizontal = -horizontal
    # WHY turned 35° off the plane normal: square-on, the arm stands straight behind the path and hides its far side
    turn = np.radians(35.0)
    horizontal = np.array([horizontal[0] * np.cos(turn) - horizontal[1] * np.sin(turn),
                           horizontal[0] * np.sin(turn) + horizontal[1] * np.cos(turn)])
    elevation = float(np.clip(np.arcsin(abs(normal[2])), np.radians(25.0), np.radians(50.0)))
    direction = np.array([*(np.cos(elevation) * horizontal), np.sin(elevation)])

    origins = np.vstack([pose[:, :3, 3] for pose in links.values()])
    pads = np.vstack([np.zeros(3), *(sign * LINK_PAD_M * axis for axis in np.eye(3) for sign in (1.0, -1.0))])
    cloud = np.vstack([(origins[:, None, :] + pads[None, :, :]).reshape(-1, 3), paths])
    forward = -direction
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    tan_y = np.tan(0.5 * FOV_Y) * FILL
    tan_x = tan_y * VIEW_ASPECT

    def spread(look: np.ndarray, distance: float) -> tuple[np.ndarray, np.ndarray]:
        v = cloud - (look + distance * direction)
        depth = np.maximum(v @ forward, 1e-6)
        return (v @ right) / depth, (v @ up) / depth

    def fits(look: np.ndarray, distance: float) -> bool:
        x, y = spread(look, distance)
        return bool(np.all(np.abs(x) <= tan_x) and np.all(np.abs(y) <= tan_y))

    def closest(look: np.ndarray) -> float:
        near, far = 0.05, 50.0
        for _ in range(50):
            mid = 0.5 * (near + far)
            near, far = (near, mid) if fits(look, mid) else (mid, far)
        return far

    look = middle.copy()
    for _ in range(4):  # centre the content on screen, then move in again
        distance = closest(look)
        x, y = spread(look, distance)
        look = look + distance * (0.5 * (x.min() + x.max()) * right + 0.5 * (y.min() + y.max()) * up)
    distance = closest(look)
    position = look + distance * direction
    eye = rrb.EyeControls3D(kind="Orbital", look_target=look.tolist(), eye_up=[0.0, 0.0, 1.0],
                            position=position.tolist())
    return eye, _Screen(position, look)


class _Screen:
    """The fitted camera as a pinhole, in the 3D view's pixels (x right, y down, 0 at the view's top-left, under its
    title bar). Checked against the real viewer at 1600 × 1000: the TCP lands within 3 px of where it is drawn at t = 0,
    1.8 and 3.2 s."""

    def __init__(self, position: np.ndarray, look: np.ndarray) -> None:
        self.position = np.asarray(position, dtype=np.float64)
        self.forward = (look - self.position) / np.linalg.norm(look - self.position)
        self.right = np.cross(self.forward, [0.0, 0.0, 1.0])
        self.right /= np.linalg.norm(self.right)
        self.up = np.cross(self.right, self.forward)
        self.scale = 0.5 * VIEW_PX[1] / np.tan(0.5 * FOV_Y)  # px per unit of (sideways / depth)

    def pixels(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        v = np.asarray(points, dtype=np.float64) - self.position
        depth = v @ self.forward
        return np.stack([0.5 * VIEW_PX[0] + self.scale * (v @ self.right) / depth,
                         0.5 * VIEW_PX[1] - self.scale * (v @ self.up) / depth], axis=-1), depth

    def world(self, pixels: np.ndarray, depth: np.ndarray) -> np.ndarray:
        """The point at `depth` that lands on `pixels` (the inverse of `pixels`)."""
        x = (pixels[..., 0] - 0.5 * VIEW_PX[0]) / self.scale * depth
        y = (0.5 * VIEW_PX[1] - pixels[..., 1]) / self.scale * depth
        return (self.position + depth[..., None] * self.forward + x[..., None] * self.right
                + y[..., None] * self.up)


FOV_Y = np.radians(55.0)  # Rerun's default vertical field of view for a 3D view
VIEW_PX = (800.0, 908.0)  # the 3D view of a 1600 × 1000 page: the left half, under its title bar (measured)
VIEW_ASPECT = 0.87  # about VIEW_PX's: the camera fit's
FILL = 0.92  # leave 8 % of the half-height free around the content
LINK_PAD_M = 0.07  # a UR-size link's half thickness: link ORIGINS fit, so pad them


# ── logging ───────────────────────────────────────────────────────────────────────────────────────────────────────


def _readouts(plan: Any, tool: _Tool) -> tuple[np.ndarray, list[str]]:
    """The TCP tab's playhead readout, one markdown document per instant (at most _ROWS)."""
    last = len(tool.t) - 1
    picked = np.unique(np.linspace(0, last, min(last + 1, _ROWS)).round().astype(int))
    rpy = plan.tcp["orientation_deg"]
    xyz = tool.xyz * 1000.0
    docs = []
    for k in picked:
        # WHY t in the table's corner and one line under it (the check, 2026-11-24): with yaw on its own strip and
        # the angular speed back, the TCP tab holds six panes; a head line above the table pushed the error line out
        lines = [f"| **t = {tool.t[k]:.2f} s** | x mm | y mm | z mm | roll ° | pitch ° | yaw ° | mm/s |",
                 "|---|---:|---:|---:|---:|---:|---:|---:|"]
        lines.append("| " + ("solution" if tool.target_xyz is not None else "plan") + " | "
                     + " | ".join(f"{v:+.1f}" for v in (*xyz[k], *rpy[k])) + f" | **{tool.speed[k]:.0f}** |")
        tail = f"plots: ±{WINDOW_S:g} s around the playhead · peak {tool.top:.0f} mm/s at {tool.t[tool.peak]:.2f} s"
        if tool.target_xyz is not None:
            txyz = tool.target_xyz[k] * 1000.0
            lines.append("| target | " + " | ".join(f"{v:+.1f}" for v in (*txyz, *tool.target_rpy[k]))
                         + f" | {tool.target_speed[k]:.0f} |")
            drpy = rpy[k] - tool.target_rpy[k]
            lines.append("| error | " + " | ".join(f"{v:+.2f}" for v in (*tool.error_mm[k], *drpy))
                         + f" | {tool.speed[k] - tool.target_speed[k]:+.0f} |")
            tail = f"error **{tool.norm_mm[k]:.2f} mm** at the tool point (×{tool.gain} in 3D)"
            if tool.ruler is not None:
                tail += f" · the agent's ruler **{tool.ruler[k]:.2f} mm** (RMS {tool.ruler_rms:.2f})"
            tail += f" · plots ±{WINDOW_S:g} s"
        lines += ["", tail]
        docs.append("\n".join(lines))
    return tool.t[picked], docs


def _now_labels(tool: _Tool) -> list[str]:
    """The TCP's label at each sample: its speed, and on a run its error (the bold arrow at it is that error ×N).

    WHY no "(×N)" (the second check, 2026-11-24): the 3D title carries the gain; a shorter box finds a clear spot
    right beside the TCP more often."""
    if tool.norm_mm is None:
        return [f"{v:.0f} mm/s" for v in tool.speed]
    return [f"{v:.0f} mm/s · error {e:.2f} mm" for v, e in zip(tool.speed, tool.norm_mm)]


def _at_ends(xyz: np.ndarray) -> np.ndarray:
    """(n, 2): the TCP sits on the start / on the end: within AT_END_M of it, in the run of samples that begins (ends)
    the motion. WHY only that run: a tool merely passing near an end mid-motion is not "at the start"."""
    n = len(xyz)
    out = np.zeros((n, 2), dtype=bool)
    for e, order in enumerate((np.arange(n), np.arange(n)[::-1])):
        near = np.linalg.norm(xyz - xyz[order[0]], axis=1) < AT_END_M
        for k in order:
            if not near[k]:
                break
            out[k, e] = True
    return out


# ── the arm on screen (so a label never lands on it) ──────────────────────────────────────────────────────────────


def _stl_vertices(path: Path) -> np.ndarray | None:
    """An STL's vertices (binary or ASCII), (m, 3) in its own units."""
    raw = path.read_bytes()
    if len(raw) >= 84:
        count = int(np.frombuffer(raw[80:84], dtype="<u4")[0])
        if len(raw) == 84 + 50 * count:
            facets = np.frombuffer(raw[84:], dtype=np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)),
                                                             ("attribute", "<u2")]))
            return facets["corners"].reshape(-1, 3).astype(np.float64)
    rows = [line.split()[1:4] for line in raw.decode("ascii", "ignore").splitlines()
            if line.strip().startswith("vertex")]
    return np.asarray(rows, dtype=np.float64) if rows else None


def _shape_points(geometry: Any, folder: Path) -> np.ndarray | None:
    """A URDF collision shape's points in its own frame: an STL mesh's vertices, a primitive's corners. None when it
    can't be read here (a package:// mesh, a .dae): that shape is then left out of the silhouette."""
    mesh, box, cylinder, sphere = (geometry.find(tag) for tag in ("mesh", "box", "cylinder", "sphere"))
    if mesh is not None:
        filename = mesh.get("filename", "").removeprefix("file://")
        path = None if "://" in filename else folder / filename
        if path is None or path.suffix.lower() != ".stl" or not path.is_file():
            return None
        points = _stl_vertices(path)
        scale = np.array([float(v) for v in mesh.get("scale", "1 1 1").split()])
        return None if points is None else points * scale
    corners = np.array([[x, y, z] for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)])
    if box is not None:
        return corners * 0.5 * np.array([float(v) for v in box.get("size", "0 0 0").split()])
    if cylinder is not None:
        radius, length = float(cylinder.get("radius", 0)), float(cylinder.get("length", 0))
        angle = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
        ring = radius * np.stack([np.cos(angle), np.sin(angle)], axis=1)
        return np.vstack([np.column_stack([ring, np.full(16, z)]) for z in (-0.5 * length, 0.5 * length)])
    if sphere is not None:
        return float(sphere.get("radius", 0)) * np.vstack([np.eye(3), -np.eye(3), corners / np.sqrt(3.0)])
    return None


def _collision_hulls(urdf: Path) -> list[tuple[str, np.ndarray]]:
    """(link, the corners of its collision shape's convex hull in the link's frame) for every shape it can read."""
    import xml.etree.ElementTree as ElementTree

    from scipy.spatial import ConvexHull

    from robot_msgs.geometry.rotations import euler_to_matrix

    shapes = []
    for link in ElementTree.parse(urdf).getroot().iter("link"):
        for collision in link.findall("collision"):
            geometry = collision.find("geometry")
            points = None if geometry is None else _shape_points(geometry, urdf.parent)
            if points is None or len(points) < 4:
                continue
            try:
                points = points[ConvexHull(points).vertices]
            except Exception:  # flat or degenerate: keep every point
                pass
            origin = collision.find("origin")
            xyz = np.array([float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()])
            rpy = [float(v) for v in (origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split()]
            shapes.append((link.get("name"), points @ np.asarray(euler_to_matrix(*rpy)).T + xyz))
    return shapes


CELL_PX = 4.0  # the arm's silhouette is kept on a grid of this many px


class _ArmOnScreen:
    """The arm's silhouette in the fitted camera's pixels: at a sample, each collision shape's projected convex hull,
    filled on a CELL_PX grid, and `covered` = how many of its cells lie under a box.

    WHY the collision meshes: they are what the viewer draws (the fixture's URDF is collision-only), so a box clear of
    them is clear of the drawn arm. `anchor` is where the arm meets the tool on each sample (the flange the stick runs
    from; else the deepest link origin off the TCP): the label prefers the side of the TCP away from it."""

    def __init__(self, plan: Any, screen: _Screen, xyz: np.ndarray) -> None:
        tree = rurdf.UrdfTree.from_file_path(plan.urdf)
        links = viz._forward_kinematics(tree, plan.values, len(plan.seconds))
        self.shapes = [(links[name], points) for name, points in _collision_hulls(plan.urdf) if name in links]
        self.screen = screen
        self.rows, self.columns = int(np.ceil(VIEW_PX[1] / CELL_PX)), int(np.ceil(VIEW_PX[0] / CELL_PX))
        self.sums = np.zeros((self.rows + 1, self.columns + 1), dtype=np.int64)
        if plan.flange is not None and len(plan.flange) == len(xyz):
            self.anchor = plan.flange
        else:
            off = [pose[:, :3, 3] for pose in links.values()
                   if len(pose) == len(xyz) and float(np.linalg.norm(pose[:, :3, 3] - xyz, axis=1).mean()) > 0.02]
            self.anchor = off[-1] if off else np.zeros_like(xyz)

    def at(self, k: int) -> "_ArmOnScreen":
        """Fill the silhouette of sample k."""
        from scipy.spatial import ConvexHull

        grid = np.zeros((self.rows, self.columns), dtype=np.int64)
        for pose, points in self.shapes:
            pixels, depth = self.screen.pixels(points @ pose[k, :3, :3].T + pose[k, :3, 3])
            if np.any(depth <= 0.0):
                continue
            try:
                corners = pixels[ConvexHull(pixels).vertices]
            except Exception:
                continue
            low = np.clip(np.floor(corners.min(axis=0) / CELL_PX).astype(int), 0, [self.columns, self.rows])
            high = np.clip(np.ceil(corners.max(axis=0) / CELL_PX).astype(int), 0, [self.columns, self.rows])
            if np.any(high <= low):
                continue
            x, y = np.meshgrid((np.arange(low[0], high[0]) + 0.5) * CELL_PX, (np.arange(low[1], high[1]) + 0.5) * CELL_PX)
            edge = np.roll(corners, -1, axis=0) - corners
            cross = (edge[:, 0, None, None] * (y[None] - corners[:, 1, None, None])
                     - edge[:, 1, None, None] * (x[None] - corners[:, 0, None, None]))
            grid[low[1]:high[1], low[0]:high[0]] += np.all(cross >= 0.0, axis=0) | np.all(cross <= 0.0, axis=0)
        self.sums[1:, 1:] = grid.cumsum(axis=0).cumsum(axis=1)
        return self

    def covered(self, x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray) -> np.ndarray:
        """The silhouette's cells under each box (px)."""
        c0, c1 = (np.clip(np.floor(v / CELL_PX).astype(int), 0, self.columns) for v in (x0, x1))
        r0, r1 = (np.clip(np.floor(v / CELL_PX).astype(int), 0, self.rows) for v in (y0, y1))
        c1, r1 = np.maximum(c1 + 1, c0).clip(0, self.columns), np.maximum(r1 + 1, r0).clip(0, self.rows)
        return self.sums[r1, c1] - self.sums[r0, c1] - self.sums[r1, c0] + self.sums[r0, c0]


def _segment_hits(a: np.ndarray, b: np.ndarray, x0: Any, y0: Any, x1: Any, y1: Any) -> np.ndarray:
    """Does the segment a → b (px) cross each box (x0, y0, x1, y1)? Liang–Barsky, over arrays of boxes."""
    d = b - a
    shape = np.shape(x0)
    low, high, hit = np.zeros(shape), np.ones(shape), np.ones(shape, dtype=bool)
    for p, q in ((-d[0], a[0] - x0), (d[0], x1 - a[0]), (-d[1], a[1] - y0), (d[1], y1 - a[1])):
        if abs(p) < 1e-12:
            hit &= np.asarray(q) >= 0.0
        elif p < 0.0:
            low = np.maximum(low, q / p)
        else:
            high = np.minimum(high, q / p)
    return hit & (low <= high)


def _to_segment(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Each point's distance to the segment a → b (px)."""
    d = b - a
    along = np.clip(((points - a) @ d) / max(float(d @ d), 1e-12), 0.0, 1.0)
    return np.linalg.norm(points - (a + along[..., None] * d), axis=-1)


# a label's box as Rerun 0.40 draws it (measured on the frames): hung from its point, ~5 px below it, ~19 px tall,
# ~6.2 px a character wide plus its padding
LABEL_DROP_PX, LABEL_H_PX, LABEL_CHAR_PX, LABEL_PAD_PX = 5.0, 19.0, 6.2, 8.0
LABEL_GAP_PX = 5.0  # between a label's box and a mark at the TCP (the triad, the stick, the bold arrow, the point)
ARM_GAP_PX = 10.0  # between a label's box and the arm's silhouette
LABEL_MARGIN_PX = 4.0  # from the view's edges
LABEL_REACH_PX = 120.0  # the farthest the playhead label's near edge sits from the TCP
LABEL_STEP_PX = 3.0
LABEL_DIRECTIONS = 24  # the directions around the TCP it may sit in (every 15°)
AWAY_PX = 70.0  # the cost, in px of extra offset, of sitting on the arm's side of the TCP instead of the far side
MOVE_COST = 0.5  # per px the label's offset from the TCP jumps between two samples: it glides, it doesn't flicker
ON_ARM_COST, END_COST = 2000.0, 300.0  # last resorts: over the arm; over a "start" / "end" label
AT_END_M = 0.02  # the TCP "sits on" the start / end while it is this close to it
FAINT_CLEAR_S = 0.15  # a faint 0.1 s arrow is hidden while the playhead is this close to its time
FAINT_GAP_PX = 6.0  # ... and while it passes this close to the bold arrow, the triad, the TCP point or the label


def _place_labels(xyz: np.ndarray, marks: list, arm: _ArmOnScreen, screen: _Screen, texts: list[str],
                  ends_at: np.ndarray, trail_samples: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where the playhead label hangs at each sample: its point (n, 3) and its box in px (n, 4: x0, y0, x1, y1); and
    (n, 2) whether the arm's silhouette or a mark at the TCP covers the "start" / "end" label on its point (then it is
    hidden: WHY, the second check, 2026-11-24: at 2.2–2.4 s the wrist passes over the end point and "end" floated over
    the wrist; at 2.5 s it sat inside the triad, before the playhead label takes it over at the end).

    The box sits right beside the TCP on screen, in one of LABEL_DIRECTIONS directions, at the shortest offset that
    clears the TCP's own marks (`marks`: (a, b, half-width) px segments per sample) and the arm's silhouette (`arm`),
    inside the view. Of those, it takes the one that is closest, on the side away from the arm (`arm.anchor`, the
    flange), off the bold trail and the path just ahead, and off the "start" / "end" labels; a Viterbi pass over the
    samples keeps it from jumping (MOVE_COST per px of change).

    WHY (the second check, 2026-11-24): the first placement went only straight above or below, just past the farthest
    mark; below meant past the flange end of the 145 mm stick, so at 1.8 s it hung ~160 px from the TCP over the wrist
    and read as the wrist's label. Now it is never on the arm (checked against its collision meshes on these pixels)
    and never farther than LABEL_REACH_PX. Still placed for the default camera: orbit it and the offsets keep their
    metres, not their pixels."""
    n = len(xyz)
    centre, depth = screen.pixels(xyz)
    width = np.array([LABEL_CHAR_PX * len(text) + LABEL_PAD_PX for text in texts])
    half_h = 0.5 * LABEL_H_PX
    angles = np.radians(np.arange(LABEL_DIRECTIONS) * 360.0 / LABEL_DIRECTIONS)
    unit = np.stack([np.cos(angles), np.sin(angles)], axis=1)  # px: x right, y down
    reach = np.arange(0.0, LABEL_REACH_PX + 1e-9, LABEL_STEP_PX)
    toward_arm = screen.pixels(arm.anchor)[0] - centre
    toward_arm /= np.maximum(np.linalg.norm(toward_arm, axis=1, keepdims=True), 1e-9)
    ends_px = screen.pixels(np.array([xyz[0], xyz[-1]]))[0]
    end_half = [0.5 * (LABEL_CHAR_PX * len(text) + LABEL_PAD_PX) for text in ("start", "end")]
    end_boxes = [(ends_px[e, 0] - end_half[e] - 3.0, ends_px[e, 1] + LABEL_DROP_PX - 3.0,
                  ends_px[e, 0] + end_half[e] + 3.0, ends_px[e, 1] + LABEL_DROP_PX + LABEL_H_PX + 3.0)
                 for e in range(2)]
    ahead = trail_samples  # the path just ahead weighs half the trail
    cost = np.full((n, LABEL_DIRECTIONS), 1e9)
    offset = np.zeros((n, LABEL_DIRECTIONS, 2))
    ends_covered = np.zeros((n, 2), dtype=bool)
    for k in range(n):
        arm.at(k)
        for e, (bx0, by0, bx1, by1) in enumerate(end_boxes):
            by0 = min(by0, ends_px[e, 1] - 4.0)  # the box and its point
            ends_covered[k, e] = int(arm.covered(np.array(bx0), np.array(by0), np.array(bx1), np.array(by1))) > 0 \
                or any(bool(_segment_hits(a[k], b[k], np.array(bx0 - w[k]), np.array(by0 - w[k]), np.array(bx1 + w[k]),
                                          np.array(by1 + w[k]))) for a, b, w in marks)
        half_w = 0.5 * width[k]
        support = np.abs(unit[:, 0]) * half_w + np.abs(unit[:, 1]) * half_h
        middle = centre[k] + unit[:, None, :] * (reach[None, :, None] + support[:, None, None])  # (J, M, 2)
        x0, x1 = middle[..., 0] - half_w, middle[..., 0] + half_w
        y0, y1 = middle[..., 1] - half_h, middle[..., 1] + half_h
        fits = ((x0 >= LABEL_MARGIN_PX) & (x1 <= VIEW_PX[0] - LABEL_MARGIN_PX)
                & (y0 >= LABEL_MARGIN_PX) & (y1 <= VIEW_PX[1] - LABEL_MARGIN_PX))
        hits = np.zeros_like(fits)
        for a, b, half_width in marks:
            gap = LABEL_GAP_PX + half_width[k]
            hits |= _segment_hits(a[k], b[k], x0 - gap, y0 - gap, x1 + gap, y1 + gap)
        on_arm = arm.covered(x0 - ARM_GAP_PX, y0 - ARM_GAP_PX, x1 + ARM_GAP_PX, y1 + ARM_GAP_PX)
        weight = np.full(n, 0.5)  # the rest of the path
        weight[max(0, k - trail_samples):k + 1] = 4.0  # the bold trail
        weight[k + 1:k + 1 + ahead] = 2.0
        for j in range(LABEL_DIRECTIONS):
            penalty = 0.0
            for level, allowed in enumerate((fits[j] & ~hits[j] & (on_arm[j] == 0), fits[j] & ~hits[j], fits[j])):
                options = np.flatnonzero(allowed)
                if options.size:
                    m = int(options[0])
                    penalty = (0.0, ON_ARM_COST + float(on_arm[j, m]), 1e6)[level]
                    break
            else:
                continue
            box = (x0[j, m], y0[j, m], x1[j, m], y1[j, m])
            inside = ((centre[:, 0] > box[0] - 2.0) & (centre[:, 0] < box[2] + 2.0)
                      & (centre[:, 1] > box[1] - 2.0) & (centre[:, 1] < box[3] + 2.0))
            on_end = sum(END_COST for e in range(2) if not (ends_at[k, e] or ends_covered[k, e])
                         and box[0] < end_boxes[e][2] and end_boxes[e][0] < box[2]
                         and box[1] < end_boxes[e][3] and end_boxes[e][1] < box[3])
            away = AWAY_PX * 0.5 * (1.0 + float(unit[j] @ toward_arm[k]))
            cost[k, j] = reach[m] + away + float(weight[inside].sum()) + on_end + penalty
            offset[k, j] = middle[j, m] - centre[k]
    # the cheapest sequence of directions, a jump in the box's offset costing MOVE_COST per px
    total, back = cost[0].copy(), np.zeros((n, LABEL_DIRECTIONS), dtype=int)
    for k in range(1, n):
        step = total[:, None] + MOVE_COST * np.linalg.norm(offset[k][None, :, :] - offset[k - 1][:, None, :], axis=2)
        back[k] = np.argmin(step, axis=0)
        total = step[back[k], np.arange(LABEL_DIRECTIONS)] + cost[k]
    chosen = np.empty(n, dtype=int)
    chosen[-1] = int(np.argmin(total))
    for k in range(n - 1, 0, -1):
        chosen[k - 1] = back[k, chosen[k]]
    middle = centre + offset[np.arange(n), chosen]
    middle[:, 0] = np.clip(middle[:, 0], 0.5 * width + LABEL_MARGIN_PX, VIEW_PX[0] - 0.5 * width - LABEL_MARGIN_PX)
    middle[:, 1] = np.clip(middle[:, 1], half_h + LABEL_MARGIN_PX, VIEW_PX[1] - half_h - LABEL_MARGIN_PX)
    boxes = np.column_stack([middle[:, 0] - 0.5 * width, middle[:, 1] - half_h,
                             middle[:, 0] + 0.5 * width, middle[:, 1] + half_h])
    point = screen.world(np.stack([middle[:, 0], boxes[:, 1] - LABEL_DROP_PX], axis=1), depth)
    return point, boxes, ends_covered


def _faint_shown(faint: tuple[np.ndarray, np.ndarray], faint_t: np.ndarray, t: np.ndarray, marks: list,
                 boxes: np.ndarray) -> np.ndarray:
    """(n, K): which faint 0.1 s arrows are drawn at each sample. Hidden while the playhead is within FAINT_CLEAR_S of
    one's time, and while it passes within FAINT_GAP_PX of the bold arrow, the triad, the TCP point or the label.

    WHY (the second check, 2026-11-24): drawn always, the arrow at the playhead's own 0.1 s sat on the bold one, and
    Rerun drew its light magenta over it and over the triad; the faint arrows are context, away from the playhead."""
    start, end = faint
    along = np.linspace(0.0, 1.0, 12)
    points = start[:, None, :] + along[None, :, None] * (end - start)[:, None, :]  # (K, 12, 2)
    shown = np.abs(t[:, None] - faint_t[None, :]) > FAINT_CLEAR_S
    for k in np.flatnonzero(shown.any(axis=1)):
        hidden = np.zeros(len(faint_t), dtype=bool)
        for a, b, half_width in marks:
            hidden |= (_to_segment(points, a[k], b[k]) < FAINT_GAP_PX + half_width[k]).any(axis=1)
        x0, y0, x1, y1 = boxes[k] + np.array([-FAINT_GAP_PX, -FAINT_GAP_PX, FAINT_GAP_PX, FAINT_GAP_PX])
        for i in range(len(faint_t)):
            hidden[i] |= bool(_segment_hits(start[i], end[i], np.array(x0), np.array(y0), np.array(x1), np.array(y1)))
        shown[k] &= ~hidden
    return shown


def _on_changes(t: np.ndarray, shown: np.ndarray) -> np.ndarray:
    """The samples where a per-sample visibility mask changes (the first included): log a batch only there."""
    return np.flatnonzero(np.r_[True, np.any(shown[1:] != shown[:-1], axis=1)])


def _log_tool(stream: rr.RecordingStream, plan: Any, tool: _Tool, quats: np.ndarray, screen: _Screen,
              arm: _ArmOnScreen) -> None:
    """/world/<name>/tcp/...: the speed-coloured path, the trail, the triad and point at the playhead, its label (beside
    the TCP, off the arm), the stick, the ends; on a run the error vectors (and the target path where it parts from the
    solution's). All in the tool's own frame (the URDF root, prefixed)."""
    from robot_msgs.geometry.rotations import quat_to_matrix

    base = f"/world/{plan.part}/tcp"
    frame = rr.CoordinateFrame(f"{plan.part}/{plan.tool_frame}")
    on_t = [rr.TimeColumn(TIMELINE, duration=tool.t)]
    xyz, n = tool.xyz, len(tool.t)
    segments = np.stack([xyz[:-1], xyz[1:]], axis=1)
    # the whole path, static, one segment per sample pair in the speed colour of its end sample
    stream.log(f"{base}/path", frame, rr.LineStrips3D(segments, colors=tool.rgb[1:], radii=PATH_R), static=True)
    # the trail: the same segments, each on t at its end sample; the view keeps only (cursor − TRAIL_S, cursor]
    stream.log(f"{base}/trail", frame, rr.LineStrips3D.from_fields(radii=TRAIL_R), static=True)
    stream.send_columns(f"{base}/trail", indexes=[rr.TimeColumn(TIMELINE, duration=tool.t[1:])],
                        columns=rr.LineStrips3D.columns(strips=segments, colors=tool.rgb[1:]).partition([1] * (n - 1)))
    # the TCP now: a point in its speed colour, and the triad of the tool's own axes
    stream.log(f"{base}/now", frame, rr.Points3D.from_fields(radii=0.011), static=True)
    stream.send_columns(f"{base}/now", indexes=on_t, columns=rr.Points3D.columns(positions=xyz, colors=tool.rgb))
    axes = quat_to_matrix(quats).transpose(0, 2, 1) * TRIAD_M  # rows = the tool's x, y, z axes in the root frame
    vectors = None if tool.error_mm is None else tool.error_mm / 1000.0 * tool.gain
    stick = plan.flange is not None and len(plan.flange) == n

    # what sits at the TCP on screen, as (a, b, half-width) px segments per sample: the label and the faint arrows
    # stay off them. WHY 2.5 × an arrow's radius: its head is wider than its shaft
    centre, depth = screen.pixels(xyz)
    per_m = screen.scale / depth

    def px(points: np.ndarray) -> np.ndarray:
        return screen.pixels(points)[0]

    marks = [(centre, px(xyz + axes[:, a, :]), 2.5 * 0.0042 * per_m) for a in range(3)]
    marks.append((centre, centre, 0.011 * per_m))
    if stick:
        marks.append((px(plan.flange), centre, 0.0035 * per_m))
    if vectors is not None:
        marks.append((px(tool.target_xyz), px(tool.target_xyz + vectors), 2.5 * 0.0034 * per_m))

    # its label on a point of its own, drawn at radius 0 in a dark neutral (the label's text takes its point's colour:
    # in the speed colour it was low-contrast at speed), beside the TCP and off the arm (`_place_labels`). At an end it
    # leads with "start" / "end", and that end's own label steps aside (WHY: the triad covers the end's point there)
    ends_at = _at_ends(xyz)
    texts = [("start · " if ends_at[k, 0] else "end · " if ends_at[k, 1] else "") + text
             for k, text in enumerate(_now_labels(tool))]
    trail_samples = int(round(TRAIL_S / max(float(np.median(np.diff(tool.t))), 1e-9)))
    label, boxes, ends_covered = _place_labels(xyz, marks, arm, screen, texts, ends_at, trail_samples)
    stream.log(f"{base}/now_label", frame, rr.Points3D.from_fields(radii=0.0, colors=[_LABEL], show_labels=True),
               static=True)
    stream.send_columns(f"{base}/now_label", indexes=on_t, columns=rr.Points3D.columns(positions=label, labels=texts))
    stream.log(f"{base}/triad", frame, rr.Arrows3D.from_fields(radii=0.0042), static=True)
    stream.send_columns(f"{base}/triad", indexes=on_t, columns=rr.Arrows3D.columns(
        origins=np.repeat(xyz, 3, axis=0), vectors=axes.reshape(-1, 3),
        colors=np.tile(np.asarray(_AXIS_COLORS, dtype=np.uint8), (n, 1))).partition([3] * n))
    if stick:
        stream.log(f"{base}/stick", frame, rr.LineStrips3D.from_fields(colors=[_STICK], radii=0.0035), static=True)
        stream.send_columns(f"{base}/stick", indexes=on_t, columns=rr.LineStrips3D.columns(
            strips=np.stack([plan.flange, xyz], axis=1)).partition([1] * n))
    ends = np.array([xyz[0], xyz[-1]])
    stream.log(f"{base}/ends", frame, rr.Points3D(ends, colors=[_ENDS], radii=0.007), static=True)
    shown, names = ~ends_at & ~ends_covered, np.array(["start", "end"])
    rows = _on_changes(tool.t, shown)
    stream.log(f"{base}/ends_label", frame, rr.Points3D.from_fields(radii=0.0, colors=[_ENDS], show_labels=True),
               static=True)
    stream.send_columns(f"{base}/ends_label", indexes=[rr.TimeColumn(TIMELINE, duration=tool.t[rows])],
                        columns=rr.Points3D.columns(positions=np.vstack([ends[shown[k]] for k in rows]),
                                                    labels=np.concatenate([names[shown[k]] for k in rows]).tolist())
                        .partition([int(shown[k].sum()) for k in rows]))
    if vectors is None:
        return
    # the target's path only where it parts from the solution's (`_Tool.target_strips`; none on a mm-level run)
    if tool.target_strips:
        stream.log(f"{base}/target_path", frame, rr.LineStrips3D(tool.target_strips, colors=[_TARGET],
                                                                 radii=TARGET_R), static=True)
    every = max(1, int(round(0.1 / max(float(np.median(np.diff(tool.t))), 1e-9))))  # one faint arrow per 0.1 s
    keys = np.arange(0, n, every)
    faint = (px(tool.target_xyz[keys]), px(tool.target_xyz[keys] + vectors[keys]))
    shown = _faint_shown(faint, tool.t[keys], tool.t, marks, boxes)
    rows = _on_changes(tool.t, shown)
    stream.log(f"{base}/error_every_0.1s", frame, rr.Arrows3D.from_fields(colors=[_ERROR_FAINT], radii=0.0014),
               static=True)
    stream.send_columns(f"{base}/error_every_0.1s", indexes=[rr.TimeColumn(TIMELINE, duration=tool.t[rows])],
                        columns=rr.Arrows3D.columns(origins=np.vstack([tool.target_xyz[keys][shown[k]] for k in rows]),
                                                    vectors=np.vstack([vectors[keys][shown[k]] for k in rows]))
                        .partition([int(shown[k].sum()) for k in rows]))
    # WHY no label of its own: the playhead label says both (two labels by one point overprinted)
    stream.log(f"{base}/error_now", frame, rr.Arrows3D.from_fields(radii=0.0034, colors=[_ERROR]), static=True)
    stream.send_columns(f"{base}/error_now", indexes=on_t, columns=rr.Arrows3D.columns(
        origins=tool.target_xyz, vectors=vectors))


def _log_series(stream: rr.RecordingStream, plan: Any, tool: _Tool) -> None:
    """The TCP tab's speed on the path's colours, its target overlays, the Tool error tab's series, the readout."""
    part = plan.part
    on_t = [rr.TimeColumn(TIMELINE, duration=tool.t)]
    # WHY per-sample colours: the strip doubles as the 3D path's colour key (the same mm/s, the same colour)
    stream.log(f"/tcp/speed_mm_s/{part}", rr.SeriesLines(names="speed", widths=3.0), static=True)
    stream.send_columns(f"/tcp/speed_mm_s/{part}", indexes=on_t,
                        columns=[*rr.Scalars.columns(scalars=tool.speed), *rr.SeriesLines.columns(colors=tool.rgb)])

    def lines(entity: str, values: np.ndarray, names: list[str], colors: list, width: float) -> None:
        values = np.asarray(values, dtype=np.float64).reshape(len(tool.t), -1)
        stream.log(entity, rr.SeriesLines(names=names, colors=colors, widths=width), static=True)
        stream.send_columns(entity, indexes=on_t, columns=rr.Scalars.columns(scalars=values.reshape(-1))
                            .partition([values.shape[1]] * len(tool.t)))

    # WHY roll / pitch apart from yaw (the check, 2026-11-24): the unwrapped yaw turns ~660° on this tour (it trades
    # off with roll near gimbal lock), so on one shared range roll and pitch were flat lines; each strip has its own
    rpy = plan.tcp["orientation_deg"]
    lines(f"/tcp/roll_pitch_deg/{part}", rpy[:, :2], ["roll", "pitch"], list(_AXIS_COLORS[:2]), 2.0)
    lines(f"/tcp/yaw_deg/{part}", rpy[:, 2], ["yaw"], [_AXIS_COLORS[2]], 2.0)
    if tool.target_xyz is not None:
        # WHY "_target": Rerun draws a plot's series in entity-path order, so the pale target goes under the solution
        lines("/tcp/position_mm/_target", tool.target_xyz * 1000.0, ["x target", "y target", "z target"],
              list(_TARGET_AXES), 4.0)
        lines("/tcp/roll_pitch_deg/_target", tool.target_rpy[:, :2], ["roll target", "pitch target"],
              list(_TARGET_AXES[:2]), 4.0)
        lines("/tcp/yaw_deg/_target", tool.target_rpy[:, 2], ["yaw target"], [_TARGET_AXES[2]], 4.0)
        lines("/tcp/speed_mm_s/_target", tool.target_speed, ["target"], [_TARGET], 4.0)
        lines("/tcp/angular_speed_deg_s/_target", tool.target_angular, ["target"], [_TARGET], 4.0)
        # the Tool error tab
        stream.log(f"/tool_error/vector_mm/{part}", rr.SeriesLines(
            names=["|error|", "x", "y", "z"], colors=[_ERROR, *_AXIS_COLORS], widths=[2.4, 1.0, 1.0, 1.0]), static=True)
        values = np.column_stack([tool.norm_mm, tool.error_mm])
        stream.send_columns(f"/tool_error/vector_mm/{part}", indexes=on_t,
                            columns=rr.Scalars.columns(scalars=values.reshape(-1)).partition([4] * len(tool.t)))
        if tool.angle_deg is not None:
            stream.log(f"/tool_error/angle_deg/{part}", rr.SeriesLines(names="angle", colors=_ERROR, widths=2.0),
                       static=True)
            stream.send_columns(f"/tool_error/angle_deg/{part}", indexes=on_t,
                                columns=rr.Scalars.columns(scalars=tool.angle_deg))
    if tool.ruler is not None:
        stream.log(f"/tool_error/ruler_mm/{part}", rr.SeriesLines(names="the agent's ruler", colors=_ERROR, widths=2.4),
                   static=True)
        stream.send_columns(f"/tool_error/ruler_mm/{part}", indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                            columns=rr.Scalars.columns(scalars=tool.ruler))
        if tool.ruler_rms is not None:
            stream.log("/tool_error/ruler_mm/rms", rr.SeriesLines(names=f"RMS {tool.ruler_rms:.2f} mm", colors=viz._LIMIT,
                                                                  widths=1.0), static=True)
            stream.send_columns("/tool_error/ruler_mm/rms", indexes=[rr.TimeColumn(
                TIMELINE, duration=[plan.seconds[0], plan.seconds[-1]])],
                columns=rr.Scalars.columns(scalars=[tool.ruler_rms, tool.ruler_rms]))
    readout_t, docs = _readouts(plan, tool)
    stream.send_columns(f"/notes/tcp_{part}", indexes=[rr.TimeColumn(TIMELINE, duration=readout_t)],
                        columns=rr.TextDocument.columns(text=docs, media_type=["text/markdown"] * len(docs)))


# ── the layout ────────────────────────────────────────────────────────────────────────────────────────────────────


def _following() -> Any:
    """The time axis every plot shares: ±WINDOW_S around the playhead, so the cursor sits mid-plot and the window
    moves with it. WHY Independent: LinkToGlobal makes a view use the shared global range instead of its own."""
    window = rrb.TimeRange(start=rrb.TimeRangeBoundary.cursor_relative(seconds=-WINDOW_S),
                           end=rrb.TimeRangeBoundary.cursor_relative(seconds=WINDOW_S))
    return rrb.TimeAxis(link="Independent", view_range=window, zoom_lock=False)


def _plot(strip: Any) -> Any:
    axis_y = rrb.ScalarAxis(range=strip.y_range, zoom_lock=False) if strip.y_range else None
    return rrb.TimeSeriesView(origin="/", contents=strip.contents, name=strip.title,
                              plot_legend=rrb.PlotLegend(visible=strip.legend, corner="RightBottom"),
                              axis_x=_following(), axis_y=axis_y)


def _span(*arrays: np.ndarray | None, floor: float | None = None, steps: float = 4.0, pad: float = 0.06,
          air: float = 0.04) -> tuple[float, float]:
    """A fixed y range over the WHOLE motion (snapped, as V1's strips): the window moves, the axis does not jump.
    `steps`: snap to a round step about span / steps (finer = the range hugs the data closer); `pad` / `air`: the
    margin added before / after the snap, as a fraction of the span."""
    values = np.concatenate([np.ravel(a) for a in arrays if a is not None])
    values = values[np.isfinite(values)]
    low, high = float(values.min()), float(values.max())
    if floor is not None:
        low = min(low, floor)
    margin = pad * max(high - low, 1e-6)
    low, high = (low - margin if floor is None else low), high + margin
    # WHY a quarter-span step (not V1's half-span `_snap`): these strips are taller, and -1000…2000 for a 1.5 m move
    # left half of the TCP strip empty
    step = viz._nice(max(high - low, 1e-9) / steps)
    low, high = float(np.floor(low / step) * step), float(np.ceil(high / step) * step)
    gap = air * (high - low)  # WHY: a tick label on the bottom edge overprinted the time axis's +0s
    return low - (gap if floor is None or low < 0 else 0.0), high + gap


def _tcp_tab(plan: Any, tool: _Tool) -> Any:
    """The readout, then position, roll / pitch, yaw, speed and angular speed (V1's TCP strips, orientation split)."""
    run = tool.target_xyz is not None
    under = " · target pale, under" if run else ""
    rpy = plan.tcp["orientation_deg"]
    target_rpy = tool.target_rpy if run else np.full_like(rpy, np.nan)
    turn = int(np.argmax(tool.angular))

    def series(group: str) -> list[str]:
        return [f"/tcp/{group}/{plan.part}"] + ([f"/tcp/{group}/_target"] if run else [])

    strips = [
        viz._Strip(f"TCP position [mm] · x red / y green / z blue{under}", series("position_mm"),
                   # WHY steps=8 (the second check, 2026-11-24): -464…1264, not -580…1580, so the strip that gave yaw
                   # its height still shows the curves' shape
                   _span(tool.xyz * 1000.0, None if not run else tool.target_xyz * 1000.0, steps=8.0)),
        viz._Strip(f"TCP roll / pitch [°] · roll red, pitch green · ROS rpy, unwrapped{plan.gimbal}{under}",
                   # WHY steps=16 (the second check, 2026-11-24): the ±216 of a quarter-span snap spent ~60 px on
                   # empty bands that yaw needs; ±130 still labels -100 / 0 / 100
                   series("roll_pitch_deg"), _span(rpy[:, :2], target_rpy[:, :2], steps=16.0)),
        viz._Strip(f"TCP yaw [°] · its own range: unwrapped, it turns {rpy[0, 2]:.0f} → {rpy[-1, 2]:.0f}°{under}",
                   # WHY snapped to 50 with thin margins on a tall strip (the second check, 2026-11-24): Rerun labels
                   # a y axis at powers of ten only, so -1040…40 carried just 0 and -1000; -857…-143 on ~177 px puts
                   # a label every 100° (-800 … -200), ~25 px apart, about the closest Rerun still draws them clearly
                   series("yaw_deg"), _span(rpy[:, 2], target_rpy[:, 2], steps=16.0, pad=0.0, air=0.01)),
        viz._Strip(f"TCP speed [mm/s] · on the 3D path's colours · peak {tool.top:.0f} at "
                   f"{tool.t[tool.peak]:.2f} s{under}", series("speed_mm_s"),
                   # WHY steps=8 (the second check, 2026-11-24): 0…2080 put its "2000" on the strip's top edge, cut
                   _span(tool.speed, tool.target_speed, floor=0.0, steps=8.0)),
        # WHY back (the check, 2026-11-24): V1's TCP tab "has all the cartesian info" (Zach); the first build dropped it
        viz._Strip(f"TCP angular speed [°/s] · peak {tool.angular[turn]:.0f} at {tool.t[turn]:.2f} s{under}",
                   # WHY steps=16: Rerun labels a y axis at powers of ten only and fades a label out under ~25 px
                   # apart; 0…600 for a 415 °/s peak left this strip with a lone "0"; 0…468 labels every 100 on less
                   series("angular_speed_deg_s"), _span(tool.angular, tool.target_angular, floor=0.0, steps=16.0)),
    ]
    readout = rrb.TextDocumentView(origin=f"/notes/tcp_{plan.part}", name="the tool at the playhead")
    # WHY these shares (pixels at 1000 px high; a strip's title and time labels take ~42 px of its share): the readout
    # just fits its table and the line under it; each strip gets the plot height that keeps its labels ≥ ~25 px apart
    # (yaw's 100° steps over 714° need the most, ~180 px), and what is left goes to position, the first strip
    shares = [197, 121, 115, 221, 92, 159] if run else [152, 140, 117, 221, 96, 179]
    return rrb.Vertical(readout, *(_plot(s) for s in strips), row_shares=shares, name="TCP")


def _error_tab(plan: Any, tool: _Tool) -> Any | None:
    if tool.error_mm is None and tool.ruler is None:
        return None
    strips = []
    if tool.ruler is not None:
        peak = int(np.argmax(tool.ruler))
        rms = f" · RMS {tool.ruler_rms:.2f} mm on this task" if tool.ruler_rms is not None else ""
        strips.append(viz._Strip(
            f"tool error [mm] · the agent's own ruler (magenta){rms} (grey) · peak {tool.ruler[peak]:.2f} at "
            f"{plan.seconds[peak]:.2f} s",
            [f"/tool_error/ruler_mm/{plan.part}"] + (["/tool_error/ruler_mm/rms"] if tool.ruler_rms else []),
            _span(tool.ruler, floor=0.0)))
    if tool.error_mm is not None:
        norm = tool.norm_mm
        peak = int(np.argmax(norm))
        strips.append(viz._Strip(
            # WHY this short: a strip title is one line, cut at ~115 characters in half the page
            f"tool point error [mm] · solution − target · peak {norm[peak]:.2f} at {tool.t[peak]:.2f} s · "
            f"×{tool.gain} in 3D · |error| magenta, x red / y green / z blue",
            [f"/tool_error/vector_mm/{plan.part}"], _span(norm, tool.error_mm)))
    if tool.angle_deg is not None:
        peak = int(np.argmax(tool.angle_deg))
        strips.append(viz._Strip(
            f"tool orientation error [°] · angle between the target and solution tool frames · peak "
            f"{tool.angle_deg[peak]:.2f} at {tool.t[peak]:.2f} s",
            [f"/tool_error/angle_deg/{plan.part}"], _span(tool.angle_deg, floor=0.0)))
    return rrb.Vertical(*(_plot(s) for s in strips), name="Tool error")


def _world_title(plan: Any, tool: _Tool) -> str:
    """The 3D view's title: what it is (name · robot · duration), then the key the view cannot draw.

    WHY this short (the check, 2026-11-24): a view title is one line, cut at the half-page width (~110 characters at
    1600 px); the first build led with the key and lost the run's name, robot and duration. The trail, triad and stick
    explain themselves while it plays; the speed scale and the ×N do not."""
    title = f"{plan.name} · {plan.robot_name} · {plan.seconds[-1]:.2f} s · purple→lime 0–{tool.top:.0f} mm/s"
    if tool.error_mm is None:
        return title + f" · bold = last {TRAIL_S:g} s · triad = TCP"
    title += f" · magenta error ×{tool.gain}"
    if tool.target_strips:
        return title + f" · grey = target >{(TRAIL_R + TARGET_R) * 1000:.0f} mm off"
    # WHY say it: the target path is not drawn at all, it never parts from the solution's by more than a line's width
    return title + " · target path not drawn"


def _dashboard(plan: Any, tool: _Tool, eye: Any) -> Any:
    """Zach's frame: the arm on the left half, tabs on the right half; TCP open, every plot a following window."""
    trail = rrb.VisibleTimeRanges(timeline=TIMELINE, start=rrb.TimeRangeBoundary.cursor_relative(seconds=-TRAIL_S),
                                  end=rrb.TimeRangeBoundary.cursor_relative(seconds=0.0))
    title = _world_title(plan, tool)
    world = rrb.Spatial3DView(origin="/", contents=[f"/world/{plan.part}/**"], name=title, eye_controls=eye,
                              overrides={f"/world/{plan.part}/tcp/trail": trail})
    tabs = [_tcp_tab(plan, tool)]
    error = _error_tab(plan, tool)
    if error is not None:
        tabs.append(error)
    for name, strips in plan.tabs.items():
        if name == "TCP":
            continue
        if name == "q / qd / qdd":
            table = rrb.TextDocumentView(origin=f"/notes/{plan.part}", name="at the playhead")
            columns = 1 if len(strips) <= 3 else 2
            card_rows = -(-len(strips) // columns)
            tabs.append(rrb.Vertical(table, rrb.Grid(*(_plot(s) for s in strips), grid_columns=columns),
                                     row_shares=[len(plan.joints) + 5, 8 * card_rows], name=name))
        else:
            tabs.append(rrb.Vertical(*(_plot(s) for s in strips), name=name))
    return rrb.Blueprint(
        rrb.Horizontal(world, rrb.Tabs(*tabs, active_tab=0), column_shares=[1, 1]),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused", loop_mode="all"),
        collapse_panels=False,
    )


# ── the entry point ───────────────────────────────────────────────────────────────────────────────────────────────


def save(path: str | Path, traj: JointTrajectory, *, robot: str | Path, tool: PoseTrajectory | None = None,
         target: JointTrajectory | None = None, target_tool: PoseTrajectory | None = None, extras: dict | None = None,
         name: str | None = None) -> str:
    """Write `traj` (a plan, or a run's solution) with its URDF arm to an .rrd, tool first.

    ``tool`` is its tool's PoseTrajectory (default: the URDF's last link by FK); ``target`` + ``target_tool`` the run's
    target (its tool path drawn pale, the error vectors ×N, the Tool error tab); ``extras`` the agent's own numbers
    (``tool_error_mm`` per sample, ``rms_mm``, ``label``); ``name`` the entity / title name (default: the label)."""
    name = name or (str(extras["label"]).split(":")[0] if extras and extras.get("label") else type(traj).__name__)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the limits are shown, not enforced: clamp=False must not spam
        plan = viz._RobotPlan(traj, name, robot, tool)
        plan.tool_quat = _quaternions(tool, plan)
        target_plan = None
        if target is not None:
            target_plan = viz._RobotPlan(target, "target", robot, target_tool)
            target_plan.tool_quat = _quaternions(target_tool, target_plan)
        info = _Tool(plan, target_plan, extras)
        stream = rr.RecordingStream(APPLICATION_ID)
        # WHY default_blueprint at save (robot_msgs' R4 finding): written first, the file opens paused at t = 0
        eye, screen = _tool_eye(plan, info)
        stream.save(str(path), default_blueprint=_dashboard(plan, info, eye))
        filtered = _Without(stream, f"world/{plan.part}/tool", f"tcp/speed_mm_s/{plan.part}",
                            f"tcp/orientation_deg/{plan.part}")
        viz._log_robot(traj, plan, filtered, ghosts=False)
        viz._PATHS.pop(id(filtered), None)
        _log_tool(stream, plan, info, plan.tool_quat, screen, _ArmOnScreen(plan, screen, info.xyz))
        _log_series(stream, plan, info)
    stream.flush()
    stream.disconnect()
    return str(path)


def main() -> None:
    traj, tool = plan_scenario()
    print(save(HERE / "plan-dev-029.rrd", traj, robot=URDF, tool=tool, name="workspace-dev-029"))
    target, solution, target_tool, solution_tool, extras = run_scenario("p6s")
    print(save(HERE / "run-dev-029.rrd", solution, robot=URDF, tool=solution_tool, target=target,
               target_tool=target_tool, extras=extras, name="p6s on workspace-dev-029"))


if __name__ == "__main__":
    main()
