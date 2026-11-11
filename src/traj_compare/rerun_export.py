"""The Rerun projection: one comparison -> one ``.rrd`` recording with its blueprint inside.

WHY (Tracking-Run Data — data-ui vs Rerun, 2026-10-26): the dataset is the contract; our HTML viewer
and Rerun are two projections of it, and every analysis view carries an "Open in Rerun" button. This
file is the Rerun projection. It reads the ``analyze_comparison`` payload (never scraped HTML), so the
numbers in the .rrd are the numbers in the report, which in turn are ``robot_msgs.compare``'s.

Entity layout (situations are the last path part so a plot view can overlay them by origin):

    /world/<situation>/robot/<link>     static Mesh3D + per-time Transform3D
    /world/<situation>/tcp              static LineStrips3D path + per-time Points3D marker
    /position|velocity|torque/<joint>/<situation>
    /error/joint/<joint>/<situation>    target - run, SI radians
    /error/tool/<channel>/<situation>   position_mm, rotation_mrad (and rotation_deg), {x,y,z}_mm, lag_mm, cross_track_mm,
                                        contour_mm (exact), lag_time_ms (+ behind)
    /error/axes/<label>_mm/<situation>  the position error projected on each ``error_axes`` direction
    /vec/<label>/<situation>            signed speed along a ``vec_dirs`` direction (belt matching)
    /video/<situation>                  AssetVideo + VideoFrameReference (MP4 only)
    /notes                              the statistics table, verdicts, latency, goal and ISO 9283
                                        aggregates as markdown

The timeline ``t`` is a duration in seconds from the reference's (target's) first sample.
"""

from __future__ import annotations

import math
import shlex
import warnings
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import analyze_comparison
from .model import Comparison, RobotDisplay, Situation

try:
    import rerun as rr
    import rerun.blueprint as rrb
except ModuleNotFoundError as error:  # the core report works without the SDK; only this module needs it
    if error.name != "rerun":
        raise
    rr = rrb = None

# WHY one pin: an .rrd must be opened by a viewer at least as new as the SDK that wrote it, so the
# SDK that writes the file and the viewer the button launches (uvx --from rerun-sdk==...) are the
# same version everywhere. Bump it here and nowhere else.
RERUN_SDK_VERSION = "0.40.0"
APPLICATION_ID = "traj_compare"
TIMELINE = "t"
DEFAULT_LINK_OPACITY = 0.55
VIEWER_ARGV_PREFIX = ["uvx", "--from", f"rerun-sdk=={RERUN_SDK_VERSION}", "rerun"]

# (payload key, entity channel, scale) for the tool-error channels, in plot order.
_TOOL_ERROR_CHANNELS = (
    ("xyz_mag", "position_mm", 1000.0),
    ("rot_mag", "rotation_mrad", 1000.0),
    ("rot_mag", "rotation_deg", 180.0 / math.pi),  # WHY beside the mrad one: the entity is data, the view shows degrees
    ("err_x", "x_mm", 1000.0),
    ("err_y", "y_mm", 1000.0),
    ("err_z", "z_mm", 1000.0),
    ("lag", "lag_mm", 1000.0),
    ("cross_track", "cross_track_mm", 1000.0),
    ("contour", "contour_mm", 1000.0),
    ("lag_time", "lag_time_ms", 1000.0),
)


def viewer_argv(rrd_path: Path | str) -> list[str]:
    """The command that opens ``rrd_path`` in the pinned viewer, as an argument vector."""

    return [*VIEWER_ARGV_PREFIX, str(Path(rrd_path).resolve())]


def viewer_command(rrd_path: Path | str) -> str:
    """The same command as one copy-able shell line (absolute path, quoted only when it must be)."""

    return shlex.join(viewer_argv(rrd_path))


def _require_sdk() -> None:
    if rr is None:
        raise ImportError(
            f"writing a .rrd needs the Rerun SDK; install the 'rerun' extra "
            f"(pip install 'traj-compare[rerun]', or uv run --extra rerun) which pins "
            f"rerun-sdk=={RERUN_SDK_VERSION}"
        )


def _part(name: str) -> str:
    """One entity-path part, escaped so a joint called ``a b`` or ``l/r`` stays one part."""

    return rr.escape_entity_path_part(str(name))


def _hex_to_rgb(color: str) -> list[int]:
    color = color.lstrip("#")
    return [int(color[index : index + 2], 16) for index in (0, 2, 4)]


def _array(values: list | None) -> np.ndarray:
    """Payload columns carry null outside a run's own span; Rerun wants NaN for the gap."""

    return np.array([np.nan if value is None else value for value in values], dtype=float)


def _recording_name(comparison: Comparison) -> str:
    # WHY the distinguishing part first: the Sources panel truncates long names, and a group title
    # is the same for every tab of a factorial study.
    if comparison.tab_title != comparison.group_title:
        return f"{comparison.tab_title} · {comparison.group_title}"
    return comparison.title


def _markdown_cell(cell: str) -> str:
    return str(cell).replace("|", "\\|").replace("\n", " ")


def _notes_markdown(payload: dict[str, Any]) -> str:
    statistics = payload["statistics"]
    lines = [f"# {payload['title']}", ""]
    if payload["description"]:
        lines += [payload["description"], ""]
    lines += [f"## {statistics['title']}", ""]
    if statistics["description"]:
        lines += [statistics["description"], ""]
    columns = statistics["columns"]
    lines.append("| " + " | ".join(_markdown_cell(column) for column in columns) + " |")
    lines.append("|" + "---|" * len(columns))
    for row in statistics["rows"]:
        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row["cells"]) + " |")
    lines.append("")
    lines += (
        _verdict_lines(payload)
        + _latency_lines(payload)
        + _goal_lines(payload)
        + _aggregate_lines(payload)
    )
    return "\n".join(lines).rstrip("\n") + "\n"


def _deg(value: float | None) -> str:
    """An angle given in radians, shown in degrees (the display edge of the SI payload)."""
    return "—" if value is None else f"{math.degrees(value):.3g}°"


def _limit(metric: str, value: float) -> str:
    """A verdict's SI error or limit, shown in the units a person reads: ° (°/s, °/s²) for joints and rotations, mm for the tool."""
    magnitude = abs(value)
    head = metric.split("/")[0]
    if head == "velocities" or metric == "angular_velocity":
        return f"{math.degrees(magnitude):.3g}°/s"
    if head == "accelerations":
        return f"{math.degrees(magnitude):.3g}°/s²"
    if head == "positions" or metric in ("rotation", "rx", "ry", "rz"):
        return f"{math.degrees(magnitude):.3g}°"
    if metric == "linear_velocity":
        return f"{magnitude * 1000.0:.3g} mm/s"
    if metric in ("position", "x", "y", "z", "lag", "cross_track", "contour"):
        return f"{magnitude * 1000.0:.3g} mm"
    if metric == "lag_time":
        return f"{magnitude * 1000.0:.3g} ms"
    if head == "effort":
        return f"{magnitude:.3g} N·m"
    return f"{magnitude:.3g}"


def _mm(value: float | None) -> str:
    return "—" if value is None else f"{value * 1000.0:.3g} mm"


def _verdict_lines(payload: dict[str, Any]) -> list[str]:
    rows = []
    for entry in payload["situations"]:
        for key, frame in (("joint", "joints"), ("tcp", payload["tcp_frame"])):
            outcome = (entry.get("verdict") or {}).get(key)
            if outcome is None:
                continue
            first = outcome["violations"][0] if outcome["violations"] else None
            detail = (
                f"{first['phase']} · {first['metric']}: |error| {_limit(first['metric'], first['error'])} > "
                f"{_limit(first['metric'], first['limit'])} at t = {first['t']:.2f} s"
                if first
                else outcome["error_string"] or "every tolerance met"
            )
            rows.append(
                f"| {_markdown_cell(entry['title'])} | {frame} | {outcome['code_name']} | "
                f"{_markdown_cell(detail)} |"
            )
    if not rows:
        return []
    return ["## Verdicts", "", "| Run | Frame | Verdict | First violation |", "|---|---|---|---|", *rows, ""]


def _latency_lines(payload: dict[str, Any]) -> list[str]:
    rows = [
        f"| {_markdown_cell(entry['title'])} | {entry['latency']['offset_s'] * 1000.0:.2f} ms | "
        f"{_deg(entry['latency']['rms_before'])} | {_deg(entry['latency']['rms_after'])} |"
        for entry in payload["situations"]
        if entry.get("latency") and entry["latency"].get("offset_s") is not None
    ]
    if not rows:
        return []
    return [
        "## Estimated latency",
        "",
        "| Run | Offset | RMS before | RMS after shift |",
        "|---|---|---|---|",
        *rows,
        "",
    ]


def _goal_lines(payload: dict[str, Any]) -> list[str]:
    rows = []
    for entry in payload["situations"]:
        for key, frame in (("joint", "joints"), ("tcp", payload["tcp_frame"])):
            for metric, stats in ((entry.get("goal") or {}).get(key) or {}).items():
                unit = _mm if key == "tcp" else _deg
                settling = "not settled" if stats["settling_time"] is None else f"{stats['settling_time']:.3f} s"
                rows.append(
                    f"| {_markdown_cell(entry['title'])} | {frame} {metric.split('/')[-1]} | "
                    f"{unit(stats['final_error'])} | {settling} | {unit(stats['overshoot'])} | "
                    f"{unit(stats['band'])} |"
                )
    if not rows:
        return []
    return [
        "## Goal",
        "",
        "| Run | Signal | Final error | Settling | Overshoot | Band |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
    ]


def _aggregate_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for group, info in payload.get("aggregates", {}).items():
        lines += [
            f"## Accuracy vs repeatability (ISO 9283) — {group}",
            "",
            f"{len(info['runs'])} runs: {', '.join(info['titles'])}. AT = max |reference − barycentre|; "
            "RT = max of mean + 3σ of the runs' distance to the barycentre.",
            "",
            "| Signal | AT | RT |",
            "|---|---|---|",
        ]
        for joint in payload["joint_names"]:
            key = f"positions/{joint}"
            if "joint" in info and key in info["joint"]["accuracy"]:
                lines.append(
                    f"| {_markdown_cell(joint)} | {_deg(info['joint']['accuracy'][key]['max_abs'])} | "
                    f"{_deg(info['joint']['repeatability'][key]['max'])} |"
                )
        if "tcp" in info:
            lines.append(
                f"| {payload['tcp_frame']} position | {_mm(info['tcp']['accuracy']['position']['max_abs'])} | "
                f"{_mm(info['tcp']['repeatability']['position']['max'])} |"
            )
        lines.append("")
    return lines


def _link_mesh(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A triangle soup (M, 3, 3) -> vertices (3M, 3) plus flat per-face normals."""

    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return triangles.reshape(-1, 3), np.repeat(normals, 3, axis=0)


class _Writer:
    def __init__(self, recording: Any, t0: float) -> None:
        self.recording = recording
        self.t0 = t0

    def series(self, entity: str, time_s: np.ndarray, values: np.ndarray, color, label: str) -> None:
        self.recording.log(entity, rr.SeriesLines(colors=color, names=label), static=True)
        self.recording.send_columns(
            entity,
            indexes=[rr.TimeColumn(TIMELINE, duration=time_s)],
            columns=rr.Scalars.columns(scalars=values),
        )

    def robot(self, prefix: str, robot: RobotDisplay, track: dict[str, Any], color) -> None:
        track_t = _array(track["t"]) - self.t0
        positions = np.asarray(track["p"], dtype=float)  # (samples, links, 3)
        quats_wxyz = np.asarray(track["quat"], dtype=float)  # (samples, links, 4)
        colors = robot.link_colors or [None] * len(robot.link_names)
        opacities = robot.link_opacities or [DEFAULT_LINK_OPACITY] * len(robot.link_names)
        for index, (link, mesh, link_color, opacity) in enumerate(
            zip(robot.link_names, robot.link_meshes, colors, opacities, strict=True)
        ):
            entity = f"{prefix}/robot/{_part(link)}"
            vertices, normals = _link_mesh(mesh)
            rgb = _hex_to_rgb(link_color) if link_color else color
            self.recording.log(
                entity,
                rr.Mesh3D(
                    vertex_positions=vertices,
                    vertex_normals=normals,
                    albedo_factor=[*rgb, int(round(255 * opacity))],
                ),
                static=True,
            )
            self.recording.send_columns(
                entity,
                indexes=[rr.TimeColumn(TIMELINE, duration=track_t)],
                columns=rr.Transform3D.columns(
                    translation=positions[:, index],
                    quaternion=quats_wxyz[:, index][:, [1, 2, 3, 0]],  # Rerun wants xyzw
                ),
            )

    def tcp(self, entity: str, three: dict[str, Any], color) -> None:
        tcp_t = _array(three["t"]) - self.t0
        positions = np.asarray(three["p"], dtype=float)
        self.recording.log(
            entity, rr.LineStrips3D([positions], colors=[color], radii=0.0012), static=True
        )
        self.recording.send_columns(
            entity,
            indexes=[rr.TimeColumn(TIMELINE, duration=tcp_t)],
            columns=rr.Points3D.columns(
                positions=positions,
                colors=[color] * len(positions),
                radii=[0.006] * len(positions),
            ),
        )

    def video(self, entity: str, path: Path, start_s: float = 0.0) -> None:
        asset = rr.AssetVideo(path=path)
        self.recording.log(entity, asset, static=True)
        frame_nanos = asset.read_frame_timestamps_nanos()
        # A video plays at video time = trajectory time - start_s (as in the HTML viewer), so frame k
        # sits at its own timestamp plus the trajectory time shown at video time 0, minus the reference's start.
        self.recording.send_columns(
            entity,
            indexes=[rr.TimeColumn(TIMELINE, duration=frame_nanos / 1e9 + start_s - self.t0)],
            columns=rr.VideoFrameReference.columns_nanos(frame_nanos),
        )


def _blueprint(payload: dict[str, Any], videos: dict[str, Path]) -> Any:
    measured = [entry["plot"] for entry in payload["situations"] if entry["has_data"]]
    has_world = any(entry["three"] or entry["robot_track"] for entry in payload["situations"])
    has_joint_error = any("err_q" in plot for plot in measured)
    has_tool_error = any("xyz_mag" in plot for plot in measured)
    joints = [_part(name) for name in payload["joint_names"]]
    hidden_legend = rrb.PlotLegend(visible=False)  # the colours are named in the error plots' legend

    def joint_grid(root: str, unit: str, name: str) -> Any:
        return rrb.Grid(
            *[
                rrb.TimeSeriesView(
                    origin=f"/{root}/{joint}", name=f"{joint} [{unit}]", plot_legend=hidden_legend
                )
                for joint in joints
            ],
            grid_columns=min(3, len(joints)),
            name=name,
        )

    error_views: list[Any] = [
        rrb.TimeSeriesView(origin=f"/error/joint/{joint}", name=f"{joint} error [rad]")
        for joint in joints
        if has_joint_error
    ]
    if has_tool_error:
        error_views.append(
            rrb.TimeSeriesView(
                origin="/error/tool/position_mm",
                name=f"{payload['tcp_frame']} position error [mm]",
            )
        )
        if any("rot_mag" in plot for plot in measured):
            error_views.append(
                rrb.TimeSeriesView(
                    origin="/error/tool/rotation_deg",
                    name=f"{payload['tcp_frame']} rotation error [°]",
                )
            )
    if any("contour" in plot for plot in measured):
        error_views.append(
            rrb.TimeSeriesView(
                origin="/error/tool/contour_mm", name=f"{payload['tcp_frame']} contour error [mm]"
            )
        )
        error_views.append(
            rrb.TimeSeriesView(
                origin="/error/tool/lag_time_ms", name=f"{payload['tcp_frame']} lag time [ms]"
            )
        )
    if any("err_axes" in plot for plot in measured):
        error_views += [
            rrb.TimeSeriesView(
                origin=f"/error/axes/{_part(f'{label}_mm')}", name=f"error {label} [mm]"
            )
            for label in payload["error_axes"]
        ]
    tabs = [
        joint_grid("position", "rad", "Position"),
        joint_grid("velocity", "rad/s", "Velocity"),
    ]
    if payload["has_tau"]:
        tabs.append(joint_grid("torque", "Nm", "Torque"))
    tabs += [
        rrb.TimeSeriesView(origin=f"/vec/{_part(label)}", name=f"{label} speed [m/s]")
        for label in payload["vec_labels"]
        if payload["has_cartesian"]
    ]

    right: list[Any] = []
    shares: list[float] = []
    if has_world:
        right.append(rrb.Spatial3DView(origin="/world", name="3D"))
        shares.append(4)
    if error_views:
        right.append(rrb.Grid(*error_views, grid_columns=min(3, len(error_views)), name="Error"))
        shares.append(3)
    right.append(rrb.Tabs(*tabs))
    shares.append(3)
    if videos:
        right.append(
            rrb.Horizontal(
                *[
                    rrb.Spatial2DView(origin=f"/video/{_part(name)}", name=f"video · {name}")
                    for name in videos
                ]
            )
        )
        shares.append(3)
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.TextDocumentView(origin="/notes", name="Statistics"),
            rrb.Vertical(*right, row_shares=shares),
            column_shares=[1, 4],
        ),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        rrb.TimePanel(state="expanded"),
    )


def _resolvable_videos(payload: dict[str, Any], video_root: Path) -> dict[str, Path]:
    """The situations whose video can go into the recording: an MP4 that exists and Rerun can read.

    WHY the read here: a dataset run's media comes from outside (a recorder, a stand-in), and one
    unreadable clip must cost its video view, not the whole run's recording.
    """

    found: dict[str, Path] = {}
    for entry in payload["situations"]:
        if not entry["video"] or not entry["has_data"]:
            continue
        video_path = video_root / entry["video"]
        if video_path.suffix.lower() != ".mp4":
            warnings.warn(f"{video_path}: Rerun video here is MP4 only; skipped", stacklevel=3)
        elif not video_path.is_file():
            warnings.warn(f"{video_path}: video file not found; skipped", stacklevel=3)
        else:
            try:
                rr.AssetVideo(path=video_path).read_frame_timestamps_nanos()
            except RuntimeError as error:
                warnings.warn(f"{video_path}: Rerun cannot read the video ({error}); skipped", stacklevel=3)
                continue
            found[entry["name"]] = video_path
    return found


def _reference_start(comparison: Comparison) -> float:
    """Time zero: the reference's first sample, else the earliest run's."""

    if comparison.target is not None and comparison.target.has_data:
        return float(comparison.target.t[0])
    starts = [s.t[0] for s in comparison.situations if s.has_data]
    return float(min(starts)) if starts else 0.0


def write_rrd(
    comparison: Comparison,
    path: Path | str,
    *,
    payload: dict[str, Any] | None = None,
    video_root: Path | str | None = None,
) -> Path:
    """Write ``comparison`` as one .rrd (blueprint embedded) and return its path.

    ``payload`` is an already-computed ``analyze_comparison`` result (colours included) so a report
    that also writes the HTML does not analyze twice; omitted, it is computed here. ``video_root``
    is the directory ``Situation.video`` paths are relative to (default: beside the .rrd).
    """

    _require_sdk()
    from .report import _colorize

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    video_root = Path(video_root) if video_root is not None else path.parent
    if payload is None:
        payload = analyze_comparison(comparison)
        _colorize(payload)
    by_name: dict[str, Situation] = {s.name: s for s in comparison.situations}
    if comparison.target is not None:
        by_name[comparison.target.name] = comparison.target

    videos = _resolvable_videos(payload, video_root)
    t0 = _reference_start(comparison)
    recording = rr.RecordingStream(APPLICATION_ID, recording_id=comparison.name)
    recording.send_recording_name(_recording_name(comparison))
    # WHY embedded: the blueprint travels inside the .rrd (default_blueprint), so the layout opens
    # the same in any viewer of the pinned version, with no sidecar file.
    recording.save(path, default_blueprint=_blueprint(payload, videos))
    writer = _Writer(recording, t0)

    plot_t = _array(payload["plot_t"]) - t0 if payload["plot_t"] is not None else None
    for entry in payload["situations"]:
        if not entry["has_data"] or plot_t is None:
            continue
        name = _part(entry["name"])
        color = _hex_to_rgb(entry["color"])
        label = entry["title"]
        plot = entry["plot"]
        for dof, joint in enumerate(payload["joint_names"]):
            joint_part = _part(joint)
            writer.series(f"/position/{joint_part}/{name}", plot_t, _array(plot["q"][dof]), color, label)
            writer.series(f"/velocity/{joint_part}/{name}", plot_t, _array(plot["qd"][dof]), color, label)
            if plot["tau"] is not None:
                writer.series(f"/torque/{joint_part}/{name}", plot_t, _array(plot["tau"][dof]), color, label)
            if "err_q" in plot:
                # WHY from the payload: target - run, SI, straight from robot_msgs.compare, so the
                # HTML and the .rrd can never disagree.
                writer.series(f"/error/joint/{joint_part}/{name}", plot_t, _array(plot["err_q"][dof]), color, label)
        for key, channel, scale in _TOOL_ERROR_CHANNELS:
            if key in plot:
                writer.series(f"/error/tool/{channel}/{name}", plot_t, _array(plot[key]) * scale, color, label)
        for index, axis_label in enumerate(payload["error_axes"]):
            if "err_axes" in plot:
                writer.series(
                    f"/error/axes/{_part(f'{axis_label}_mm')}/{name}",
                    plot_t, _array(plot["err_axes"][index]) * 1000.0, color, label,
                )  # fmt: skip
        for index, vec_label in enumerate(payload["vec_labels"]):
            if f"vec{index}_d" in plot:
                writer.series(f"/vec/{_part(vec_label)}/{name}", plot_t, _array(plot[f"vec{index}_d"]), color, label)

        if entry["three"] is not None:
            writer.tcp(f"/world/{name}/tcp", entry["three"], color)
        robot = by_name[entry["name"]].robot or comparison.robot
        if robot is not None and entry["robot_track"] is not None:
            writer.robot(f"/world/{name}", robot, entry["robot_track"], color)
        if entry["name"] in videos:
            writer.video(f"/video/{name}", videos[entry["name"]], entry.get("video_start_s", 0.0))

    recording.log(
        "/notes",
        rr.TextDocument(_notes_markdown(payload), media_type=rr.MediaType.MARKDOWN),
        static=True,
    )
    recording.flush()
    recording.disconnect()
    return path
