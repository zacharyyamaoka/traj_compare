"""The Rerun projection: one comparison -> one ``.rrd`` recording with its blueprint inside.

WHY (Tracking-Run Data — data-ui vs Rerun, 2026-10-26): the dataset is the contract; our HTML viewer
and Rerun are two projections of it, and every analysis view carries an "Open in Rerun" button. This
file is the Rerun projection. It reads the ``analyze_comparison`` payload (never scraped HTML), so the
numbers in the .rrd are the numbers in the report, which in turn are ``robot_msgs.compare``'s.

Entity layout (situations are the last path part so a plot view can overlay them by origin):

    /world/<situation>/robot/<link>     static Mesh3D + per-time Transform3D
    /world/<situation>/tcp              static LineStrips3D path + per-time Points3D marker
    /position|velocity/<joint>/<situation>  degrees, °/s (every joint shown as revolute, as in the HTML report)
    /torque/<joint>/<situation>         N·m
    /error/joint/<joint>/<situation>    target - run, in degrees; /error/joint/<joint>/tolerance the shaded band
    /error/tool/<channel>/<situation>   position_mm (+ tolerance band), rotation_deg, {x,y,z}_mm, lag_mm, cross_track_mm,
                                        contour_mm (exact), lag_time_ms (+ behind)
    /worst/joint_deg/<situation>        the largest |joint error| at each instant (+ tolerance band)
    /tcp/{x,y,z}_mm/<situation>         the tool position, for evo's "trajectories" tab
    /heat_worst, /trail_worst           the reference path coloured by the worst run's tool error (static / on the clock)
    /video/overlay/<name>               a CameraOverlay baked into one MP4 (real camera + sim renders)
    /scorecard, /events, /stats/...     the worst-first summary table, tolerance events, RMS bars
    /error/axes/<label>_mm/<situation>  the position error projected on each ``error_axes`` direction
    /vec/<label>/<situation>            signed speed along a ``vec_dirs`` direction (belt matching)
    /video/<situation>                  AssetVideo + VideoFrameReference (MP4 only)
    /notes                              the statistics table, verdicts, latency, goal and ISO 9283
                                        aggregates as markdown

The timeline ``t`` is a duration in seconds from the reference's (target's) first sample.

WHY degrees in the .rrd (Zach's rule: degrees in every human view, SI in stored data): the .rrd is a
viewer projection; the stored data stays SI in the report payload, Parquet and MCAP.

Layouts are named (``LAYOUTS``): "questions" (the default) and "evo". Each .rrd embeds one and has
every layout beside it as ``<stem>.<layout>.rbl``; ``default_layout()`` reads the user's preference.
"""

from __future__ import annotations

import math
import os
import shlex
import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Any, Callable

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
DEGREES = 180.0 / math.pi
VIEWER_ARGV_PREFIX = ["uvx", "--from", f"rerun-sdk=={RERUN_SDK_VERSION}", "rerun"]

# (payload key, entity channel, scale) for the tool-error channels, in plot order.
_TOOL_ERROR_CHANNELS = (
    ("xyz_mag", "position_mm", 1000.0),
    ("rot_mag", "rotation_deg", 180.0 / math.pi),
    ("err_x", "x_mm", 1000.0),
    ("err_y", "y_mm", 1000.0),
    ("err_z", "z_mm", 1000.0),
    ("lag", "lag_mm", 1000.0),
    ("cross_track", "cross_track_mm", 1000.0),
    ("contour", "contour_mm", 1000.0),
    ("lag_time", "lag_time_ms", 1000.0),
)


def viewer_argv(rrd_path: Path | str, layout: str | None = None) -> list[str]:
    """The command that opens ``rrd_path`` in the pinned viewer, as an argument vector.

    With ``layout``, the layout's ``.rbl`` beside the .rrd is opened after it and replaces the embedded one."""

    argv = [*VIEWER_ARGV_PREFIX, str(Path(rrd_path).resolve())]
    if layout is not None:
        argv.append(str(blueprint_path(rrd_path, layout).resolve()))
    return argv


def viewer_command(rrd_path: Path | str, layout: str | None = None) -> str:
    """The same command as one copy-able shell line (absolute paths, quoted only when they must be)."""

    return shlex.join(viewer_argv(rrd_path, layout))


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


# ── the review entities every layout reads ─────────────────────────────────


def _heat_rgb(fraction: np.ndarray) -> np.ndarray:
    """0 -> green, 0.5 -> amber, >= 1 (the tolerance, or the largest error) -> red."""

    stops = np.array([[47, 158, 68], [245, 159, 0], [224, 49, 49]], dtype=float)
    scaled = np.clip(np.nan_to_num(fraction), 0.0, 1.0) * 2.0
    low = np.floor(np.minimum(scaled, 1.999)).astype(int)
    mix = (scaled - low)[:, None]
    return (stops[low] * (1 - mix) + stops[low + 1] * mix).astype(np.uint8)


def _joint_limits(tolerances: Any, phase: str) -> dict[str, float]:
    """A joint's position limit in one phase; 0 (unchecked, as in ROS) means no band."""

    if tolerances is None:
        return {}
    return {joint.name: joint.position for joint in getattr(tolerances, phase) if joint.position > 0}


def _tcp_limit(tolerances: Any, phase: str) -> float:
    if tolerances is None:
        return 0.0
    return float(getattr(tolerances, phase).position or 0.0)


def _runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The measured situations: the ones with an error against the reference."""

    return [entry for entry in payload["situations"] if entry["has_data"] and "err_q" in entry["plot"]]


def _reference_entry(payload: dict[str, Any]) -> dict[str, Any] | None:
    return next((entry for entry in payload["situations"]
                 if entry["has_data"] and "err_q" not in entry["plot"] and entry["three"] is not None), None)


def _short_run(entry: dict[str, Any]) -> str:
    return entry["title"].replace(" (stand-in)", "")


def _scorecard(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for entry in _runs(payload):
        metrics = entry["error_metrics"]
        joint_max = [metrics[f"positions/{joint}"]["max_abs"] for joint in payload["joint_names"]
                     if f"positions/{joint}" in metrics]
        verdict = entry.get("verdict") or {}
        latency = (entry.get("latency") or {}).get("offset_s")
        rows.append({
            "run": entry["title"],
            "joints": (verdict.get("joint") or {}).get("code_name", "—"),
            "tcp": (verdict.get("tcp") or {}).get("code_name", "—"),
            "tool_rms": metrics["position"]["rms"] if "position" in metrics else None,
            "tool_max": metrics["position"]["max_abs"] if "position" in metrics else None,
            "worst_joint": max(joint_max) if joint_max else None,
            "latency": latency,
        })
    key = "tool_max" if any(row["tool_max"] is not None for row in rows) else "worst_joint"
    rows.sort(key=lambda row: -(row[key] or 0.0))
    lines = [f"# {payload['title']}", ""]
    if rows:
        worst = rows[0]
        peak = f"tool error peaks at {_mm(worst['tool_max'])}" if key == "tool_max" else f"joint error peaks at {_deg(worst['worst_joint'])}"
        lines += [f"**Worst run: {worst['run']}** — {peak} (vs {payload['reference_title']}).", ""]
    lines += ["| Run | Joints | TCP | Tool RMS | Tool max | Worst joint | Latency |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        latency = "—" if row["latency"] is None else f"{row['latency'] * 1000.0:.1f} ms"
        lines.append(
            f"| {_markdown_cell(row['run'])} | {row['joints']} | {row['tcp']} | {_mm(row['tool_rms'])} | "
            f"{_mm(row['tool_max'])} | {_deg(row['worst_joint'])} | {latency} |"
        )
    return "\n".join(lines) + "\n", rows


def _events(payload: dict[str, Any], t0: float, reference_end: float) -> list[tuple[float, str, str]]:
    events = []
    for entry in _runs(payload):
        verdict = entry.get("verdict") or {}
        for key, frame in (("joint", "joints"), ("tcp", payload["tcp_frame"])):
            outcome = verdict.get(key) or {}
            first = (outcome.get("violations") or [None])[0]
            if first:
                events.append((first["t"] - t0, "WARN",
                               f"{entry['title']}: {frame} {first['phase']} tolerance broken on {first['metric']} "
                               f"(|error| {_limit(first['metric'], first['error'])} > {_limit(first['metric'], first['limit'])})"))
        settling = [stats["settling_time"] for stats in ((entry.get("goal") or {}).get("joint") or {}).values()]
        if settling:
            if any(value is None for value in settling):
                events.append((reference_end, "WARN", f"{entry['title']}: a joint never settled in the goal band"))
            else:
                events.append((reference_end + max(settling), "INFO",
                               f"{entry['title']}: every joint settled, {max(settling):.2f} s after the reference ended"))
    return sorted(events)


def _log_review_entities(recording: Any, writer: "_Writer", comparison: Comparison, payload: dict[str, Any], t0: float) -> None:
    """The entities the layouts read beyond the raw signals: bands, worst-of, heat path, scorecard, events.

    WHY here and not in a layout: both layouts (and any later one) read the same entities; a layout
    only chooses views, so switching layout never changes a number."""

    if payload["plot_t"] is None:
        return
    plot_t = _array(payload["plot_t"]) - t0
    reference_end = float(comparison.target.t[-1]) - t0 if comparison.target is not None and comparison.target.has_data else float(plot_t[-1])
    in_goal = plot_t >= reference_end
    band_rgba = [120, 120, 120, 70]

    def band(entity: str, low: np.ndarray, high: np.ndarray) -> None:
        """A shaded tolerance band: Rerun's Measurements draws centre ± one standard deviation."""
        recording.log(entity, rr.Measurements.from_fields(colors=[band_rgba], names=["tolerance"], widths=[0.5]), static=True)
        recording.send_columns(
            entity,
            indexes=[rr.TimeColumn(TIMELINE, duration=plot_t)],
            columns=rr.Measurements.columns(values=0.5 * (low + high), variances=(0.5 * (high - low)) ** 2),
        )

    path_limits = _joint_limits(comparison.tolerances, "path")
    goal_limits = _joint_limits(comparison.tolerances, "goal")
    for joint in payload["joint_names"]:
        if joint in path_limits or joint in goal_limits:
            limit = np.degrees(np.where(in_goal, goal_limits.get(joint, np.nan), path_limits.get(joint, np.nan)))
            band(f"/error/joint/{_part(joint)}/tolerance", -limit, limit)
    if path_limits or goal_limits:
        worst_limit = np.degrees(np.where(in_goal, max(goal_limits.values(), default=np.nan),
                                          max(path_limits.values(), default=np.nan)))
        band("/worst/joint_deg/tolerance", np.zeros_like(worst_limit), worst_limit)
    tcp_path_m = _tcp_limit(comparison.tcp_tolerances, "path")
    tcp_goal_m = _tcp_limit(comparison.tcp_tolerances, "goal")
    if tcp_path_m or tcp_goal_m:
        limit_mm = np.where(in_goal, tcp_goal_m or np.nan, tcp_path_m or np.nan) * 1000.0
        band("/error/tool/position_mm/tolerance", np.zeros_like(limit_mm), limit_mm)

    tool_errors: list[np.ndarray] = []
    bar_values: list[float] = []
    for entry in _runs(payload):
        name, color, label, plot = _part(entry["name"]), _hex_to_rgb(entry["color"]), entry["title"], entry["plot"]
        worst = np.degrees(np.nanmax(np.abs(np.array([_array(row) for row in plot["err_q"]])), axis=0))
        writer.series(f"/worst/joint_deg/{name}", plot_t, worst, color, label)
        if "xyz_mag" in plot:
            tool_errors.append(_array(plot["xyz_mag"]) * 1000.0)
        metrics = entry["error_metrics"]
        bar_values.append(metrics["position"]["rms"] * 1000.0 if "position" in metrics else
                          max((metrics[f"positions/{j}"]["rms"] for j in payload["joint_names"] if f"positions/{j}" in metrics), default=0.0) * DEGREES)
    if bar_values:
        recording.log("/stats/tool_rms_mm" if tool_errors else "/stats/joint_rms_deg",
                      rr.BarChart(np.array(bar_values), color=[90, 90, 90]), static=True)

    # The reference path coloured by the WORST run's tool error at each instant: where on the path,
    # across every run, the error is highest (Nov 11: "across a bunch of runs where was the error highest").
    reference = _reference_entry(payload)
    if reference is not None and tool_errors:
        worst_mm = np.nanmax(np.vstack(tool_errors), axis=0)
        finite = np.isfinite(worst_mm)
        reference_t = _array(reference["three"]["t"]) - t0
        reference_p = np.asarray(reference["three"]["p"], dtype=float)
        on_path = np.interp(reference_t, plot_t[finite], worst_mm[finite]) if finite.any() else np.zeros_like(reference_t)
        scale_mm = tcp_path_m * 1000.0 if tcp_path_m else (float(np.nanmax(worst_mm[finite])) if finite.any() else 1.0)
        segments = np.stack([reference_p[:-1], reference_p[1:]], axis=1)
        colors = _heat_rgb(0.5 * (on_path[:-1] + on_path[1:]) / max(scale_mm, 1e-9))
        recording.log("/heat_worst", rr.LineStrips3D(segments, colors=colors, radii=0.004), static=True)
        # the same path on the clock: with a growing time range it draws itself as you play (evo)
        recording.send_columns(
            "/trail_worst",
            indexes=[rr.TimeColumn(TIMELINE, duration=reference_t[1:])],
            columns=rr.LineStrips3D.columns(strips=segments, colors=colors, radii=np.full(len(segments), 0.004)),
        )
        recording.log("/path/reference", rr.LineStrips3D([reference_p], colors=[_hex_to_rgb(reference["color"])], radii=0.0015), static=True)

    scorecard, _ = _scorecard(payload)
    recording.log("/scorecard", rr.TextDocument(scorecard, media_type=rr.MediaType.MARKDOWN), static=True)
    for when, level, text in _events(payload, t0, reference_end):
        recording.set_time(TIMELINE, duration=when)
        recording.log("/events", rr.TextLog(text, level=level))
    recording.reset_time()


def _composite_overlay(overlay: Any, video_root: Path, out: Path) -> Path | None:
    """A ``CameraOverlay`` baked into one MP4: the real camera with every sim render laid over it.

    WHY baked (Zach, 2026-11-11: "overlay it ourselves and then put it in the standard rerun video
    viewer"): Rerun plays a video as-is, so the blend the HTML viewer does live is done here once.
    Each render is mixed at half opacity; with ``key_color`` its background is keyed out first,
    which suits a render on a flat background."""

    ffmpeg = shutil.which("ffmpeg")
    real = video_root / overlay.real_video
    sims = [video_root / path for _, path in overlay.sims if (video_root / path).is_file()]
    if ffmpeg is None or not real.is_file() or not sims:
        warnings.warn(f"camera overlay '{overlay.name}': needs ffmpeg, {real} and a sim render; skipped", stacklevel=3)
        return None
    key = getattr(overlay, "key_color", "")
    graph, current = [], "[0:v]"
    for index in range(len(sims)):
        layer = f"[{index + 1}:v]"
        keyed = f"colorkey=0x{key.lstrip('#')}:0.18:0.05," if key else ""
        graph.append(f"{layer}{current}scale2ref[s{index}][b{index}]")
        graph.append(f"[s{index}]{keyed}format=rgba,colorchannelmixer=aa=0.5[a{index}]")
        graph.append(f"[b{index}][a{index}]overlay=format=auto[o{index}]")
        current = f"[o{index}]"
    graph.append(f"{current}format=yuv420p[v]")
    command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(real)]
    for sim in sims:
        command += ["-i", str(sim)]
    command += ["-filter_complex", ";".join(graph), "-map", "[v]", "-c:v", "libx264", "-bf", "0", "-crf", "20", str(out)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        warnings.warn(f"camera overlay '{overlay.name}': ffmpeg failed ({error}); skipped", stacklevel=3)
        return None
    return out


# ── the named layouts ───────────────────────────────────────────────────────

def _legend(show: bool) -> Any:
    return None if show else rrb.PlotLegend(visible=False)


def _ts(origin: str, name: str, legend: bool = False, **kwargs: Any) -> Any:
    """A time-series view whose x zoom is linked to every other plot: zoom one, they all follow."""

    return rrb.TimeSeriesView(origin=origin, name=name, plot_legend=_legend(legend),
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"), **kwargs)


def _eye(payload: dict[str, Any], robot: bool) -> Any:
    """A default camera that frames the robot (or just the path) from the front-right, z up."""

    reference = _reference_entry(payload) or next((e for e in payload["situations"] if e["three"] is not None), None)
    if reference is None:
        return None
    path = np.asarray(reference["three"]["p"], dtype=float)
    if robot:
        look = 0.5 * (path.mean(axis=0) + np.array([0.0, 0.0, 0.35]))
        reach = max(float(np.ptp(path, axis=0).max()), 0.6)
        return rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1],
                                 position=look + reach * np.array([1.5, -1.9, 1.1]))
    centre = path.mean(axis=0)
    span = max(float(np.ptp(path, axis=0).max()), 0.05)
    return rrb.EyeControls3D(kind="Orbital", look_target=centre, eye_up=[0, 0, 1],
                             position=centre + span * np.array([0.6, -0.85, 0.75]))


def _world(payload: dict[str, Any], name: str, contents: list[str], robot: bool = True, **kwargs: Any) -> Any:
    return rrb.Spatial3DView(origin="/", contents=contents, name=name, line_grid=rrb.LineGrid3D(visible=False),
                             eye_controls=_eye(payload, robot), **kwargs)


def _has_world(payload: dict[str, Any]) -> bool:
    return any(entry["three"] or entry["robot_track"] for entry in payload["situations"])


def _has_tool(payload: dict[str, Any]) -> bool:
    return any("xyz_mag" in entry["plot"] for entry in _runs(payload))


def _camera_origin(videos: dict[str, Path], overlays: list[str]) -> str | None:
    if overlays:
        return f"/video/overlay/{_part(overlays[0])}"
    if videos:
        measured = [name for name in videos]
        return f"/video/{_part(measured[-1])}"
    return None


def _short(joint: str) -> str:
    return joint.replace("_joint", "").replace("_", " ")


def _has_verdict(payload: dict[str, Any], key: str) -> bool:
    """A verdict exists only where tolerances were declared, so it says whether a band was drawn."""
    return any((entry.get("verdict") or {}).get(key) for entry in _runs(payload))


def _band_note(payload: dict[str, Any]) -> str:
    return " — grey band = tolerance" if _has_verdict(payload, "joint") or _has_verdict(payload, "tcp") else ""


def _where_views(payload: dict[str, Any]) -> list[Any]:
    if payload["error_axes"]:
        return [_ts(f"/error/axes/{_part(f'{label}_mm')}", f"error {label} [mm]") for label in payload["error_axes"]]
    return [_ts(f"/error/tool/{axis}_mm", f"error {axis} [mm]") for axis in "xyz"]


def _layout_questions(payload: dict[str, Any], videos: dict[str, Path], overlays: list[str], tab: str | None = None) -> Any:
    """'questions': a pinned stage (3D over the camera) on the left; tabs named by the question you are asking.

    WHY (Zach's pick, 2026-11-11, babble V2 at 88/100): the opening tab alone answers pass/fail, which
    run is worst and when, and the robot and camera never leave the screen while you work through
    where, which joint, and timing-or-shape."""

    joints = [_part(joint) for joint in payload["joint_names"]]
    tool = _has_tool(payload)
    good = [rrb.TextDocumentView(origin="/scorecard", name="Scorecard"),
            _ts("/worst/joint_deg", f"Worst joint error, any joint [°]{_band_note(payload)}", legend=True)]
    if tool:
        good.append(_ts("/error/tool/position_mm", f"{payload['tcp_frame']} position error [mm]"))
    good.append(rrb.TextLogView(origin="/events", name="Events"))
    tabs = [rrb.Vertical(*good, row_shares=[3, 2, 2, 1][: len(good) - 1] + [1], name="Is it good?")]
    if tool:
        tabs.append(rrb.Vertical(*_where_views(payload), name="Where?"))
    tabs.append(rrb.Grid(*[_ts(f"/error/joint/{j}", f"{_short(j)} [°]") for j in joints],
                         grid_columns=min(2, len(joints)), name="Which joint?"))
    if tool:
        timing = [_ts("/error/tool/lag_time_ms", "Lag time [ms] (how late along the path)", legend=True),
                  _ts("/error/tool/contour_mm", "Contour error [mm] (off the path)")]
        timing += [_ts(f"/vec/{_part(label)}", f"Speed along {label} [m/s]") for label in payload["vec_labels"]]
        tabs.append(rrb.Vertical(*timing, name="Timing or shape?"))
    signals = [rrb.Grid(*[_ts(f"/position/{j}", f"{_short(j)} [°]") for j in joints], grid_columns=min(2, len(joints)), name="Position"),
               rrb.Grid(*[_ts(f"/velocity/{j}", f"{_short(j)} [°/s]") for j in joints], grid_columns=min(2, len(joints)), name="Velocity")]
    if payload["has_tau"]:
        signals.append(rrb.Grid(*[_ts(f"/torque/{j}", f"{_short(j)} [N·m]") for j in joints], grid_columns=min(2, len(joints)), name="Torque"))
    tabs.append(rrb.Tabs(*signals, name="Signals"))
    questions = rrb.Tabs(*tabs, active_tab=_active(tabs, tab))

    stage = []
    if _has_world(payload):
        stage.append(_world(payload, "Stage", ["/world/**"]))
    camera = _camera_origin(videos, overlays)
    if camera:
        stage.append(rrb.Spatial2DView(origin=camera, name="Camera overlay" if overlays else "Camera"))
    if not stage:
        return rrb.Blueprint(questions, *_panels())
    return rrb.Blueprint(rrb.Horizontal(rrb.Vertical(*stage, row_shares=[3, 2][: len(stage)]), questions, column_shares=[2, 3]),
                         *_panels())


def _layout_evo(payload: dict[str, Any], videos: dict[str, Path], overlays: list[str], tab: str | None = None) -> Any:
    """'evo': evo's own Rerun layout (evo_ape --rerun: Visualization + Raw data) with a full-screen tab per analysis.

    WHY (Zach's pick, 2026-11-11): evo is the reference he named; its blueprint is copied, not
    reinvented — the error-coloured path and the error curve draw themselves up to the playhead."""

    joints = [_part(joint) for joint in payload["joint_names"]]
    tool = _has_tool(payload)
    bars = "/stats/tool_rms_mm" if tool else "/stats/joint_rms_deg"
    order = " · ".join(f"{index} {_short_run(entry)}" for index, entry in enumerate(_runs(payload)))
    bar_view = rrb.BarChartView(origin=bars, name=f"{'Tool' if tool else 'Worst joint'} RMS error per run "
                                                  f"[{'mm' if tool else '°'}] — {order}", plot_legend=_legend(False))
    growing = [rrb.VisibleTimeRange(TIMELINE, start=rrb.TimeRangeBoundary.infinite(),
                                    end=rrb.TimeRangeBoundary.cursor_relative(seconds=0.0))]
    if tool and _reference_entry(payload) is not None:
        scale = "the tolerance" if _has_verdict(payload, "tcp") else "the largest error"
        reference = _part(_reference_entry(payload)["name"])
        visualization = rrb.Vertical(
            _world(payload, f"Reference path coloured by the worst run's tool error (green → red at {scale}), drawn up to the playhead",
                   ["/trail_worst", f"/world/{reference}/robot/**"], time_ranges=growing),
            rrb.Horizontal(_ts("/error/tool/position_mm", f"{payload['tcp_frame']} position error [mm]{_band_note(payload)}",
                               legend=True, time_ranges=growing), bar_view, column_shares=[3, 2]),
            row_shares=[3, 2], name="Visualization",
        )
    else:
        visualization = rrb.Vertical(_ts("/worst/joint_deg", f"Worst joint error [°]{_band_note(payload)}", legend=True,
                                         time_ranges=growing), bar_view, row_shares=[3, 2], name="Visualization")
    tabs = [visualization]
    if _has_world(payload):
        tcp = [_ts(f"/tcp/{axis}_mm", f"{payload['tcp_frame']} {axis} [mm]") for axis in "xyz"] if tool else []
        tabs.append(rrb.Horizontal(_world(payload, "Robots + paths", ["/world/**"]), *([rrb.Vertical(*tcp)] if tcp else []),
                                   column_shares=[3, 2][: 1 + bool(tcp)], name="Trajectories"))
    else:
        tabs.append(rrb.Grid(*[_ts(f"/position/{j}", f"{_short(j)} [°]") for j in joints], grid_columns=min(3, len(joints)),
                             name="Trajectories"))
    tabs.append(rrb.Grid(*[_ts(f"/error/joint/{j}", f"{_short(j)} error [°]") for j in joints],
                         grid_columns=min(3, len(joints)), name="Joint error"))
    if tool:
        along = _where_views(payload) + [_ts("/error/tool/contour_mm", "contour error [mm]"),
                                         _ts("/error/tool/lag_time_ms", "lag time [ms]")]
        along += [_ts(f"/vec/{_part(label)}", f"speed along {label} [m/s]") for label in payload["vec_labels"]]
        tabs.append(rrb.Grid(*along, grid_columns=3, name="Along / across"))
    if videos or overlays:
        big = _camera_origin(videos, overlays)
        small = [rrb.Spatial2DView(origin=f"/video/{_part(name)}", name=name) for name in videos]
        tabs.append(rrb.Horizontal(rrb.Spatial2DView(origin=big, name="Camera overlay" if overlays else "Camera"),
                                   *([rrb.Vertical(*small)] if small and overlays else []),
                                   column_shares=[3, 1][: 1 + bool(small and overlays)], name="Video"))
    tabs.append(rrb.Horizontal(rrb.TextDocumentView(origin="/scorecard", name="Scorecard"),
                               rrb.TextDocumentView(origin="/notes", name="Full statistics"), name="Stats"))
    tabs.append(rrb.DataframeView(origin="/error", name="Raw data"))
    return rrb.Blueprint(rrb.Tabs(*tabs, active_tab=_active(tabs, tab)), *_panels())


def _active(tabs: list[Any], tab: str | None) -> int | None:
    """The index of the tab named ``tab`` (None: the first); an unknown name says which exist."""

    if tab is None:
        return None
    names = [container.name for container in tabs]
    if tab not in names:
        raise ValueError(f"no tab {tab!r} in this layout; tabs: {', '.join(names)}")
    return names.index(tab)


def _panels() -> list[Any]:
    return [rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"), rrb.TimePanel(state="collapsed")]


# Name -> (title, builder). WHY names, not one default: Zach asked for named layouts so a user can
# keep their preference (2026-11-11: 'call one "evo" the other "questions"').
LAYOUTS: dict[str, tuple[str, Callable[..., Any]]] = {
    "questions": ("Questions — stage + question tabs", _layout_questions),
    "evo": ("evo — one tab per analysis", _layout_evo),
}
DEFAULT_LAYOUT = "questions"
LAYOUT_ENV = "TRAJ_COMPARE_RERUN_LAYOUT"


def _check_layout(name: str) -> str:
    if name not in LAYOUTS:
        raise ValueError(f"unknown Rerun layout {name!r}; choose one of: {', '.join(LAYOUTS)}")
    return name


def config_path() -> Path:
    """Where the user's preference lives: ``$XDG_CONFIG_HOME/traj_compare/config.toml`` (``rerun_layout = "evo"``)."""

    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "traj_compare" / "config.toml"


def default_layout() -> str:
    """The user's preferred layout: ``$TRAJ_COMPARE_RERUN_LAYOUT``, else the config file, else ``"questions"``."""

    name = os.environ.get(LAYOUT_ENV)
    if not name and config_path().is_file():
        import tomllib

        name = tomllib.loads(config_path().read_text("utf-8")).get("rerun_layout")
    return _check_layout(name or DEFAULT_LAYOUT)


def layout_blueprint(name: str, payload: dict[str, Any], videos: dict[str, Path], overlays: list[str] | tuple = (),
                     tab: str | None = None) -> Any:
    """The named layout's blueprint for one comparison payload, opening on ``tab`` (by name) if given."""

    _require_sdk()
    return LAYOUTS[_check_layout(name)][1](payload, videos, list(overlays), tab)


def blueprint_path(rrd_path: Path | str, layout: str) -> Path:
    """The ``.rbl`` beside an ``.rrd`` that opens it in ``layout``: ``<stem>.<layout>.rbl``."""

    rrd_path = Path(rrd_path)
    return rrd_path.with_name(f"{rrd_path.stem}.{_check_layout(layout)}.rbl")


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
    layout: str | None = None,
    payload: dict[str, Any] | None = None,
    video_root: Path | str | None = None,
    blueprint: Callable[[dict[str, Any], dict[str, Path]], Any] | None = None,
    application_id: str = APPLICATION_ID,
    extra: Callable[[Any, dict[str, Any], float], None] | None = None,
) -> Path:
    """Write ``comparison`` as one .rrd and return its path.

    ``layout`` names the embedded layout (``LAYOUTS``; default: the user's ``default_layout()``).
    Every layout is also written beside the .rrd as ``<stem>.<layout>.rbl`` so any of them opens
    with ``viewer_argv(path, layout=...)``. ``payload`` is an already-computed ``analyze_comparison``
    result (colours included) so a report that also writes the HTML does not analyze twice; omitted,
    it is computed here. ``video_root`` is the directory ``Situation.video`` and ``CameraOverlay``
    paths are relative to (default: beside the .rrd).

    Hooks for trying another layout without forking the writer: ``blueprint(payload, videos)``
    replaces the named layout; ``application_id`` keeps several layouts of one comparison apart when
    they are open in one viewer; ``extra(recording, payload, t0)`` logs more entities.
    """

    _require_sdk()
    from .report import _colorize

    layout = _check_layout(layout) if layout is not None else default_layout()
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
    overlays: dict[str, tuple[Path, float]] = {}
    for overlay in comparison.overlays:
        baked = _composite_overlay(overlay, video_root, path.with_name(f"{path.stem}.overlay-{overlay.name}.mp4"))
        if baked is not None:
            overlays[overlay.name] = (baked, overlay.t0_s)
    t0 = _reference_start(comparison)
    recording = rr.RecordingStream(application_id, recording_id=comparison.name)
    recording.send_recording_name(_recording_name(comparison))
    # WHY embedded: the blueprint travels inside the .rrd (default_blueprint), so the layout opens
    # the same in any viewer of the pinned version, with no sidecar file.
    embedded = blueprint(payload, videos) if blueprint else layout_blueprint(layout, payload, videos, list(overlays))
    recording.save(path, default_blueprint=embedded)
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
            writer.series(f"/position/{joint_part}/{name}", plot_t, _array(plot["q"][dof]) * DEGREES, color, label)
            writer.series(f"/velocity/{joint_part}/{name}", plot_t, _array(plot["qd"][dof]) * DEGREES, color, label)
            if plot["tau"] is not None:
                writer.series(f"/torque/{joint_part}/{name}", plot_t, _array(plot["tau"][dof]), color, label)
            if "err_q" in plot:
                # WHY from the payload: target - run, straight from robot_msgs.compare, so the HTML and
                # the .rrd can never disagree; shown in degrees, the display edge.
                writer.series(f"/error/joint/{joint_part}/{name}", plot_t, _array(plot["err_q"][dof]) * DEGREES, color, label)
        for key, channel, scale in _TOOL_ERROR_CHANNELS:
            if key in plot:
                writer.series(f"/error/tool/{channel}/{name}", plot_t, _array(plot[key]) * scale, color, label)
        for axis in "xyz":
            if axis in plot:
                writer.series(f"/tcp/{axis}_mm/{name}", plot_t, _array(plot[axis]) * 1000.0, color, label)
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
    for overlay_name, (baked, start_s) in overlays.items():
        writer.video(f"/video/overlay/{_part(overlay_name)}", baked, start_s)

    recording.log(
        "/notes",
        rr.TextDocument(_notes_markdown(payload), media_type=rr.MediaType.MARKDOWN),
        static=True,
    )
    _log_review_entities(recording, writer, comparison, payload, t0)
    if extra is not None:
        extra(recording, payload, t0)
    recording.flush()
    recording.disconnect()
    # every named layout beside the file, so the user's other preference is one argument away
    for name in LAYOUTS:
        layout_blueprint(name, payload, videos, list(overlays)).save(application_id, blueprint_path(path, name))
    return path
