"""The Rerun projection: one comparison -> one ``.rrd`` recording with its blueprint inside.

WHY (Tracking-Run Data — data-ui vs Rerun, 2026-10-26): the dataset is the contract; our HTML viewer
and Rerun are two projections of it, and every analysis view carries an "Open in Rerun" button. This
file is the Rerun projection. It reads the ``analyze_comparison`` payload (never scraped HTML), so the
numbers in the .rrd are the numbers in the report, which in turn are ``robot_msgs.compare``'s.

Entity layout (situations are the last path part so a plot view can overlay them by origin):

    /world/<situation>/robot/<link>     static Mesh3D + per-time Transform3D
    /world/<situation>/tcp              static LineStrips3D path + per-time Points3D marker
    /positions|velocities/<joint>/<situation>  degrees, °/s (every joint shown as revolute, as in the HTML report)
    /effort/<joint>/<situation>         N·m         (these three, the errors, bands, links and video are
    /error/positions/<joint>/<situation>  target - run in degrees, + /tolerance   written by robot_msgs.viz.rerun)
    /current/<joint>/<situation>        motor current, A (``Situation.current``)
    /channels/<name>/<column>/<situation>  every other recorded signal (``Situation.channels``), as recorded; a 1-D
                                        channel's column is ``value``, an undescribed one's ``0``, ``1``, ...
    /error/tool/<channel>/<situation>   position_mm (+ tolerance band), rotation_deg, {x,y,z}_mm, lag_mm, cross_track_mm,
                                        contour_mm (exact), lag_time_ms (+ behind)
    /worst/joint_deg/<situation>        the largest |joint error| at each instant (+ tolerance band)
    /tcp/{x,y,z}_mm/<situation>         the tool position, for evo's "trajectories" tab
    /heat_worst, /trail_worst           the reference path coloured by the worst run's tool error (static / on the clock)
    /video/overlay-<name>               a CameraOverlay baked into one MP4 (real camera + sim renders)
    /scorecard, /events, /stats/...     the worst-first summary table, tolerance events, RMS bars
    /torque/<joint>/target              the target torque, N·m (only when a run has a torque breakdown)
    /torque/<joint>/<run>/{commanded,feedforward,feedback,applied}   the run's torque breakdown, N·m
    /stats/fb_share/<joint>             the feedback share of the command, one bar per run, %
    /stats/joint_rms/<part>             the joints tab's ranking: per part, each joint's worst-run RMS error, °
    /stats/joint_ranking                every joint of every part, worst first, as one markdown line (≥ 2 parts)
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
from collections.abc import Mapping
from typing import Any, Callable

import numpy as np

from . import _files
from .analysis import analyze_comparison
from .model import Comparison, RobotDisplay, Situation
# WHY here (2026-11-25): Open in Rerun on a run that HAS a target is the pick round's V2 (robot_msgs' URDF arm for the
# run, the target and its error on top); this module is where every Open in Rerun recording is made, so it is exported
# from here beside write_rrd
from .rerun_target_run import comparison_inputs, target_vs_run_blueprint, write_target_vs_run_rrd
from .tabs import normalize_parts, resolve_tab, tabs_for

try:
    import rerun as rr
    import rerun.blueprint as rrb

    # WHY robot_msgs' logger for the standard parts (joint series, joint errors, bands, robot links,
    # video): one entity layout for every package (/<field>/<column>/<name>), so a traj_compare
    # recording and a msg.show() recording overlay (agreed with the Robot Msg Agent, 2026-11-11).
    from robot_msgs.trajectory import JointTrajectory, PoseTrajectory
    from robot_msgs.shape import Mesh
    from robot_msgs.viz import rerun as viz
except ModuleNotFoundError as error:  # the core report works without the SDK; only this module needs it
    if error.name != "rerun":
        raise
    rr = rrb = viz = None

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

# The torque breakdown (CONTRACT.md, 2026-11-19): (payload plot key, entity leaf). WHY fixed component
# colours (Zach 2026-11-19, torque breakdown): feedforward and feedback read the same on every run and
# in the HTML page; commanded and applied wear the run's colour, applied thin.
_TORQUE_COMPONENTS = (
    ("tau_cmd", "commanded"),
    ("tau_ff", "feedforward"),
    ("tau_fb", "feedback"),
    ("tau", "applied"),
)
FEEDFORWARD_COLOR = "#3b82f6"
FEEDBACK_COLOR = "#f97316"
TARGET_TORQUE_COLOR = "#8a8983"
_TORQUE_WIDTHS = {"commanded": 2.5, "feedforward": 1.5, "feedback": 1.5, "applied": 0.75, "target": 1.5}


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
    """One entity-path part, spelled as robot_msgs' logger spells it, so both write the same paths."""

    return viz.path_part(name)


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
        + _torque_budget_lines(payload)
    )
    return "\n".join(lines).rstrip("\n") + "\n"


def _nm(value: float | None) -> str:
    return "—" if value is None else f"{value:.3g} N·m"


def _torque_budget_lines(payload: dict[str, Any]) -> list[str]:
    """The HTML page's Torque budget table: per run × joint, how much of the command the feedback supplied."""

    rows = []
    for entry in payload["situations"]:
        for joint, row in (entry.get("torque_budget") or {}).items():
            share = "—" if row["fb_share"] is None else f"{row['fb_share'] * 100.0:.1f} %"
            rows.append(
                f"| {_markdown_cell(entry['title'])} | {_markdown_cell(joint)} | {share} | {_nm(row['cmd_rms'])} | "
                f"{_nm(row['ff_rms'])} | {_nm(row['fb_rms'])} | {_nm(row['target_minus_cmd_rms'])} | "
                f"{_nm(row['cmd_minus_applied_rms'])} | {_nm(row['cmd_peak'])} |"
            )
    if not rows:
        return []
    return [
        "## Torque budget",
        "",
        "FB share = Σ|feedback| / (Σ|feedforward| + Σ|feedback|): how much of the command the feedback had to supply. "
        f"RMS over each run's own samples; {payload['reference_title']} − commanded is lined up as every other error.",
        "",
        f"| Run | Joint | FB share | Commanded RMS | FF RMS | FB RMS | {_markdown_cell(payload['reference_title'])} − commanded RMS "
        "| Commanded − applied RMS | Peak \\|commanded\\| |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
    ]


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


def _robot_links(robot: RobotDisplay, track: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """The robot as robot_msgs' (link name, Mesh, PoseTrajectory) triples, from the payload's link track."""

    track_t = _array(track["t"])
    positions = np.asarray(track["p"], dtype=float)  # (samples, links, 3)
    quats_wxyz = np.asarray(track["quat"], dtype=float)  # (samples, links, 4)
    parts = []
    for index, (link, soup) in enumerate(zip(robot.link_names, robot.link_meshes, strict=True)):
        soup = np.asarray(soup, dtype=float)  # a triangle soup (M, 3, 3)
        mesh = Mesh(vertices=soup.reshape(-1, 3), triangles=np.arange(3 * len(soup), dtype=np.int32).reshape(-1, 3))
        poses = PoseTrajectory(t=track_t, positions=positions[:, index],
                               orientations=quats_wxyz[:, index][:, [1, 2, 3, 0]])  # xyzw, as robot_msgs keeps it
        parts.append((link, mesh, poses))
    return parts


def _link_colors(robot: RobotDisplay, run_rgb: list[int]) -> list[list[int]]:
    colors = robot.link_colors or [None] * len(robot.link_names)
    opacities = robot.link_opacities or [DEFAULT_LINK_OPACITY] * len(robot.link_names)
    return [[*(_hex_to_rgb(color) if color else run_rgb), int(round(255 * opacity))]
            for color, opacity in zip(colors, opacities, strict=True)]


def _overlay_entity(name: str) -> str:
    """The video name a CameraOverlay is logged under: ``/video/overlay-<name>``."""

    return f"overlay-{name}"


class _Writer:
    def __init__(self, recording: Any, t0: float) -> None:
        self.recording = recording
        self.t0 = t0

    def series(self, entity: str, time_s: np.ndarray, values: np.ndarray, color, label: str,
               width: float | None = None) -> None:
        self.recording.log(entity, rr.SeriesLines(colors=color, names=label, widths=width), static=True)
        self.recording.send_columns(
            entity,
            indexes=[rr.TimeColumn(TIMELINE, duration=time_s)],
            columns=rr.Scalars.columns(scalars=values),
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


def _has_breakdown(entry: dict[str, Any]) -> bool:
    return entry["has_data"] and entry["plot"] is not None and any(entry["plot"].get(key) is not None
                                                                   for key in ("tau_cmd", "tau_ff", "tau_fb"))


def _torque_runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The measured situations with a torque breakdown, in payload order."""

    return [entry for entry in payload["situations"] if entry["role"] != "target" and _has_breakdown(entry)]


def _worst_torque_run(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The run whose full breakdown the torque tab shows: the worst on the scorecard that has one (else the first)."""

    runs = _torque_runs(payload)
    names = {entry["name"]: entry for entry in runs}
    _, rows = _scorecard(payload)
    ranked = [names[row["name"]] for row in rows if row["name"] in names]
    return ranked[0] if ranked else (runs[0] if runs else None)


def _fb_share_runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The runs with a feedback share: one bar each in ``/stats/fb_share/<joint>``, in this order."""

    return [entry for entry in _torque_runs(payload)
            if any(row["fb_share"] is not None for row in (entry["torque_budget"] or {}).values())]


def _scorecard(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for entry in _runs(payload):
        metrics = entry["error_metrics"]
        joint_max = [metrics[f"positions/{joint}"]["max_abs"] for joint in payload["joint_names"]
                     if f"positions/{joint}" in metrics]
        verdict = entry.get("verdict") or {}
        latency = (entry.get("latency") or {}).get("offset_s")
        rows.append({
            "name": entry["name"],
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
    return "\n".join(lines + _score_table(rows)) + "\n", rows


def _score_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| Run | Joints | TCP | Tool RMS | Tool max | Worst joint | Latency |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        latency = "—" if row["latency"] is None else f"{row['latency'] * 1000.0:.1f} ms"
        lines.append(
            f"| {_markdown_cell(row['run'])} | {row['joints']} | {row['tcp']} | {_mm(row['tool_rms'])} | "
            f"{_mm(row['tool_max'])} | {_deg(row['worst_joint'])} | {latency} |"
        )
    return lines


# ── check groups ────────────────────────────────────────────────────────────
# WHY (Zach, 2026-11-19, on the CAN 11 envelope report): "make a separate page tab for "Camera Check", here
# you show the camera information (on the other tabs it can just be the joint information)". A check group
# is a measurement that checks the others (the camera's ArUco angle checks the encoder), not a run to grade:
# its 15 fps noise made it the "worst run" and its spikes buried every error plot. So its runs leave every
# other view and the main summaries, and get one tab where they sit beside every run they check.

Checks = list[tuple[str, str, list[dict[str, Any]]]]


def _check_groups(payload: dict[str, Any], checks: Mapping[str, str] | None) -> Checks:
    """(group, tab title, its situations) for each ``checks`` group this comparison has, in ``checks`` order."""

    found: Checks = []
    for group, title in (checks or {}).items():
        members = [entry for entry in payload["situations"] if entry.get("group") == group]
        if members:
            found.append((group, title, members))
    return found


def _without_checks(payload: dict[str, Any], checks: Checks) -> dict[str, Any]:
    """``payload`` minus the check groups' situations: what the main views and summaries read."""

    names = {entry["name"] for _, _, members in checks for entry in members}
    return {**payload, "situations": [entry for entry in payload["situations"] if entry["name"] not in names]} if names else payload


def _check_document(payload: dict[str, Any], title: str, members: list[dict[str, Any]]) -> str:
    """The check tab's text: each check run's note (how it was measured, or why there is no line), then every run's scores."""

    lines = [f"# {title}", ""]
    for entry in members:
        lines += [f"**{_markdown_cell(entry['title'])}**" + (f" — {entry['note']}" if entry.get("note") else ""), ""]
    _, rows = _scorecard(payload)
    if rows:
        lines += [f"Every run against {payload['reference_title']}, the check beside the runs it checks:", "", *_score_table(rows)]
    return "\n".join(lines) + "\n"


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


def _log_review_entities(recording: Any, writer: "_Writer", comparison: Comparison, payload: dict[str, Any], t0: float,
                         checks: Mapping[str, str] | None = None) -> None:
    """The entities the layouts read beyond the raw signals: bands, worst-of, heat path, scorecard, events.

    WHY here and not in a layout: both layouts (and any later one) read the same entities; a layout
    only chooses views, so switching layout never changes a number. ``checks`` groups stay out of the
    scorecard, events, RMS bars and heat path, and get ``/checks/<group>/scorecard`` instead."""

    if payload["plot_t"] is None:
        return
    groups = _check_groups(payload, checks)
    for group, title, members in groups:
        recording.log(f"/checks/{_part(group)}/scorecard",
                      rr.TextDocument(_check_document(payload, title, members), media_type=rr.MediaType.MARKDOWN), static=True)
    graded = {entry["name"] for entry in _runs(_without_checks(payload, groups))}
    plot_t = _array(payload["plot_t"]) - t0
    reference_end = float(comparison.target.t[-1]) - t0 if comparison.target is not None and comparison.target.has_data else float(plot_t[-1])
    in_goal = plot_t >= reference_end

    def band(entity: str, low: np.ndarray, high: np.ndarray) -> None:
        viz.band(entity.lstrip("/"), plot_t, low, high, recording=recording)  # a shaded tolerance band

    path_limits = _joint_limits(comparison.tolerances, "path")
    goal_limits = _joint_limits(comparison.tolerances, "goal")
    for joint in payload["joint_names"]:
        if joint in path_limits or joint in goal_limits:
            limit = np.degrees(np.where(in_goal, goal_limits.get(joint, np.nan), path_limits.get(joint, np.nan)))
            band(f"/error/positions/{_part(joint)}/tolerance", -limit, limit)
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
        if entry["name"] not in graded:
            continue  # a check run: plotted in its own tab, never in the bars or the heat path
        if "xyz_mag" in plot:
            tool_errors.append(_array(plot["xyz_mag"]) * 1000.0)
        metrics = entry["error_metrics"]
        bar_values.append(metrics["position"]["rms"] * 1000.0 if "position" in metrics else
                          max((metrics[f"positions/{j}"]["rms"] for j in payload["joint_names"] if f"positions/{j}" in metrics), default=0.0) * DEGREES)
    if bar_values:
        recording.log("/stats/tool_rms_mm" if tool_errors else "/stats/joint_rms_deg",
                      rr.BarChart(np.array(bar_values), color=[90, 90, 90]), static=True)
    # The joints tab's ranking (NAVIGATION.md Part B): per part, one bar per joint in the part's own order, the RMS
    # error of that joint's worst run (°); check runs stay out, as above. One joint has nothing to rank.
    ranked = _without_checks(payload, groups)
    if _has_ranking(ranked):
        rms = _joint_rms_deg(ranked)
        for part in _parts(ranked):
            recording.log(f"/stats/joint_rms/{_part(part['name'])}",
                          rr.BarChart(np.array([rms[joint] for joint in _part_joints(part)]), color=[90, 90, 90]), static=True)
        if len(_parts(ranked)) >= 2:
            recording.log(_JOINT_RANKING, rr.TextDocument(_ranking_markdown(ranked, rms), media_type=rr.MediaType.MARKDOWN),
                          static=True)
    # How much of the command the feedback supplied, per joint, one bar per run (check runs stay out, as above).
    share_runs = _fb_share_runs(_without_checks(payload, groups))
    if share_runs:
        for joint in payload["joint_names"]:
            shares = [(entry["torque_budget"].get(joint) or {}).get("fb_share") for entry in share_runs]
            percent = np.array([np.nan if share is None else share * 100.0 for share in shares])
            recording.log(f"/stats/fb_share/{_part(joint)}",
                          rr.BarChart(percent, color=_hex_to_rgb(FEEDBACK_COLOR)), static=True)

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

    scorecard, _ = _scorecard(_without_checks(payload, groups))
    recording.log("/scorecard", rr.TextDocument(scorecard, media_type=rr.MediaType.MARKDOWN), static=True)
    for when, level, text in _events(_without_checks(payload, groups), t0, reference_end):
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
    # -f mp4: the temporary name it is written under (NAVIGATION.md D2) has no extension to infer it from
    command += ["-filter_complex", ";".join(graph), "-map", "[v]", "-c:v", "libx264", "-bf", "0", "-crf", "20", "-f", "mp4"]
    try:
        with _files.replacing(out) as temporary:
            subprocess.run([*command, str(temporary)], check=True, capture_output=True, timeout=600)
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


def _world(payload: dict[str, Any], name: str, contents: list[str], robot: bool = True, eye_controls: Any = None,
           **kwargs: Any) -> Any:
    return rrb.Spatial3DView(origin="/", contents=contents, name=name, line_grid=rrb.LineGrid3D(visible=False),
                             eye_controls=eye_controls if eye_controls is not None else _eye(payload, robot), **kwargs)


def _stage_eye(payload: dict[str, Any]) -> Any:
    """The stage's camera: every link of the robot in frame (both arms of a bimanual), not just the tool path.

    WHY (the 46-motor fixture in the real viewer, 2026-11-19): framing the tool path alone put a bimanual's torso in
    front of its far arm, half out of frame. The middle 90 % of the link origins (a static base link may sit at the
    world origin) and the tool path set the box; a robot wider across y than deep along x is seen from the front."""

    points = [np.asarray(entry["robot_track"]["p"], dtype=float).reshape(-1, 3)
              for entry in payload["situations"] if entry.get("robot_track")]
    if not points:
        return _eye(payload, True)
    points += [np.asarray(entry["three"]["p"], dtype=float) for entry in payload["situations"] if entry.get("three")]
    cloud = np.vstack(points)
    cloud = cloud[np.all(np.isfinite(cloud), axis=1)]
    low, high = np.percentile(cloud, 5, axis=0), np.percentile(cloud, 95, axis=0)
    look = 0.5 * (low + high)
    spread = high - low
    reach = max(float(spread.max()), 0.6)
    direction = np.array([1.9, -1.0, 0.9]) if spread[1] > 1.2 * spread[0] else np.array([1.5, -1.9, 1.1])
    return rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1], position=look + reach * direction)


def _has_world(payload: dict[str, Any]) -> bool:
    return any(entry["three"] or entry["robot_track"] for entry in payload["situations"])


def _has_tool(payload: dict[str, Any]) -> bool:
    return any("xyz_mag" in entry["plot"] for entry in _runs(payload))


def _camera_origin(videos: dict[str, Path], overlays: list[str]) -> str | None:
    if overlays:
        return f"/video/{_part(_overlay_entity(overlays[0]))}"
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


_PLOTS = ("TimeSeriesView", "BarChartView", "Spatial3DView")


def _exclude(container: Any, parts: list[str]) -> None:
    """Take the runs named ``parts`` out of every plot and 3D view under ``container`` (a contents rule per run).

    WHY a contents rule and not a hidden override: the run is not in the view at all, so it is in no legend,
    no auto-scaled axis and no Blueprint tree row there. Runs are the last path part (``/<field>/<column>/<run>``,
    ``/world/<run>/...``), so one rule per run covers every layout's views."""

    if not parts:
        return
    if hasattr(container, "origin"):
        kind = type(container).__name__
        if kind in _PLOTS:
            rules = [container.contents] if isinstance(container.contents, str) else list(container.contents or ["$origin/**"])
            # WHY no $origin rule in 3D: its origin is "/", so "$origin/<run>" would name a root entity, not the world's run
            rules += [f"- /world/{part}/**" if kind == "Spatial3DView" else f"- $origin/{part}/**" for part in parts]
            container.contents = rules
        return
    for child in getattr(container, "contents", None) or []:
        _exclude(child, parts)


def _check_parts(checks: Checks) -> list[str]:
    return [_part(entry["name"]) for _, _, members in checks for entry in members]


def _one_or_grid(views: list[Any], name: str) -> Any:
    return views[0] if len(views) == 1 else rrb.Grid(*views, grid_columns=min(2, len(views)), name=name)


def _check_tab(full: dict[str, Any], group: str, title: str, members: list[dict[str, Any]]) -> Any:
    """One check group's tab: its note and scores, then its runs beside every other run (angle, joint error, tool error, 3D)."""

    document = rrb.TextDocumentView(origin=f"/checks/{_part(group)}/scorecard", name=title)
    measured = [entry for entry in members if entry["has_data"] and "err_q" in entry["plot"]]
    if not measured:  # only a note: why this comparison has no line for the check
        return rrb.Vertical(document, name=title)
    reference = _minuend(full)
    top = rrb.Horizontal(document, _world(full, f"{title}: every run in 3D", ["/world/**"]), column_shares=[2, 3]) if _has_world(full) else document
    rows = [top,
            _one_or_grid([_ts(f"/positions/{_part(j)}", f"{title}: {_short(j)} joint angle, every run [°]", legend=True)
                          for j in full["joint_names"]], "Angle"),
            _one_or_grid([_ts(f"/error/positions/{_part(j)}", f"{title}: {_short(j)} joint error, {reference} − run [°]")
                          for j in full["joint_names"]], "Joint error")]
    if any("xyz_mag" in entry["plot"] for entry in measured):
        rows.append(_ts("/error/tool/position_mm", f"{title}: {full['tcp_frame']} position error, |{reference} − run| [mm]"))
    return rrb.Vertical(*rows, row_shares=[3] + [2] * (len(rows) - 1), name=title)


# (worst breakdown run, every breakdown run's path part, the FB-share runs, their bar order, how the reference is named)
TorqueContext = tuple[dict[str, Any], list[str], list[dict[str, Any]], str, str]


def _torque_reference(payload: dict[str, Any]) -> str:
    """How a torque view names its dashed line: "target", or "<run> (applied)" when a run is the reference (sim → real)."""

    return f"{payload['reference_title']} (applied)" if payload.get("reference_kind") == "run" else "target"


def _torque_context(payload: dict[str, Any]) -> TorqueContext | None:
    """(the run whose full breakdown is drawn, every breakdown run's path part, the FB-share runs, their bar order)."""

    worst = _worst_torque_run(payload)
    if worst is None:
        return None
    share_runs = _fb_share_runs(payload)
    order = " · ".join(f"{index} {_short_run(entry)}" for index, entry in enumerate(share_runs))
    return worst, [_part(entry["name"]) for entry in _torque_runs(payload)], share_runs, order, _torque_reference(payload)


def _torque_views(joint: str, context: TorqueContext, legend: bool = True) -> list[Any]:
    """One joint's torque views: the worst run's breakdown, every run's feedback, the FB-share bars (with a share)."""

    worst, runs, share_runs, order, reference = context
    j = _part(joint)
    views = [
        _ts(f"/torque/{j}", f"{_short(joint)}: {_short_run(worst)} — {reference}, commanded, feedforward, feedback, applied [N·m]",
            legend=legend, contents=["+ $origin/target", f"+ $origin/{_part(worst['name'])}/**"]),
        _ts(f"/torque/{j}", f"{_short(joint)}: feedback, every run [N·m]", legend=legend,
            contents=[f"+ $origin/{run}/feedback" for run in runs]),
    ]
    if share_runs:
        views.append(rrb.BarChartView(origin=f"/stats/fb_share/{j}", name=f"{_short(joint)}: feedback share of the command [%] — {order}",
                                      plot_legend=_legend(False)))
    return views


def _torque_row(joint: str, context: TorqueContext, legend: bool = True) -> Any:
    views = _torque_views(joint, context, legend)
    return rrb.Horizontal(*views, column_shares=[3, 3, 2][: len(views)])


def _torque_tab(payload: dict[str, Any], name: str) -> Any:
    """Per joint: the worst run's full breakdown, every run's feedback, and the FB-share bars; None without a breakdown.

    WHY these three (Zach 2026-11-19, torque breakdown: "of the command torque some portion of that is coming from
    Feedforward, and some portion of that is coming from feedback"): one run shows how the command splits and how
    much of it arrived; the feedback of every run and its share say whether the feedforward model is doing the work."""

    context = _torque_context(payload)
    if context is None:
        return None
    return rrb.Vertical(*[_torque_row(joint, context) for joint in payload["joint_names"]], name=name)


# ── the questions layout: the shared question tabs (docs/NAVIGATION.md Part B) ──


def _parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """``payload["parts"]``: the arms and hands, in the caller's order (one implicit part when none were named)."""

    return payload.get("parts") or normalize_parts(payload["joint_names"], None)


def _part_joints(part: dict[str, Any]) -> list[str]:
    return [joint for group in part["groups"] for joint in group["joints"]]


def _part_label(part: dict[str, Any]) -> str:
    """The part's nested tab: ``<part> · <n> joints``, the HTML part selector's label (NAVIGATION.md Part B)."""

    count = len(_part_joints(part))
    return f"{part['name']} · {count} joint{'' if count == 1 else 's'}"


def _is_hand(part: dict[str, Any]) -> bool:
    """A hand groups its joints by finger (named groups); an arm is one unnamed group."""

    return any(group["name"] for group in part["groups"])


def _part_grid(part: dict[str, Any], cell: Callable[[str], Any], name: str) -> Any:
    """One part's per-joint cells: an arm as a two-column grid, a hand as one row per finger, its joints side by side.

    WHY rows per finger (Zach 2026-11-19, traj compare view feedback: "Hand can have 1 - N motors (perhaps you group
    by finger)"): a finger's joints move together, so they read side by side; an arm's 1-7 joints keep today's grid."""

    if _is_hand(part):
        return rrb.Vertical(*[rrb.Horizontal(*[cell(joint) for joint in group["joints"]], name=group["name"])
                              for group in part["groups"]], name=name)
    views = [cell(joint) for joint in _part_joints(part)]
    return rrb.Grid(*views, grid_columns=min(2, len(views)), name=name)


def _per_part(payload: dict[str, Any], title: str, build: Callable[[dict[str, Any], str], Any]) -> Any:
    """``build(part, name)`` for the one part (named ``title``), or nested tabs ``<part> · <n> joints`` for several.

    WHY nested tabs (Zach 2026-11-19, traj compare view feedback: "split the arm and the hand into separate concerns,
    and each arm separately"): 46 motors on one screen is unreadable; one part per tab keeps each plot legible."""

    parts = _parts(payload)
    if len(parts) == 1:
        return build(parts[0], title)
    return rrb.Tabs(*[build(part, _part_label(part)) for part in parts], name=title)


def _minuend(payload: dict[str, Any]) -> str:
    """The reference as every error's sign convention names it: ``target`` (− run), or the reference run's title."""

    title = payload["reference_title"]
    return "target" if title == "Target" else title


def _with_reference(payload: dict[str, Any], key: str) -> str:
    """Who a signal view draws: "target and every run" when the reference has ``key``, else "every run"."""

    reference = next((entry for entry in payload["situations"] if entry["role"] == "target"), None)
    has = reference is not None and reference["has_data"] and (reference["plot"] or {}).get(key) is not None
    return f"{_minuend(payload)} and every run" if has else "every run"


def _joint_rms_deg(payload: dict[str, Any]) -> dict[str, float]:
    """Each joint's RMS error in its worst run, in degrees: the ``joints`` tab's ranking (NAVIGATION.md Part B)."""

    runs = _runs(payload)
    worst: dict[str, float] = {}
    for joint in payload["joint_names"]:
        values = [entry["error_metrics"][f"positions/{joint}"]["rms"] for entry in runs
                  if f"positions/{joint}" in entry["error_metrics"]]
        finite = [value for value in values if value is not None and math.isfinite(value)]
        worst[joint] = max(finite) * DEGREES if finite else math.nan
    return worst


def _has_ranking(payload: dict[str, Any]) -> bool:
    """One joint has nothing to rank; without a graded run there is no error to rank."""

    return len(payload["joint_names"]) >= 2 and bool(_runs(payload))


# Every joint of every part, worst first, as one markdown line: the joints tab's cross-part ranking (≥ 2 parts).
_JOINT_RANKING = "/stats/joint_ranking"


def _ranking_markdown(payload: dict[str, Any], rms: dict[str, float]) -> str:
    """``1. Right hand · r index pip 2.25°; 2. …``: every joint, worst first, labelled ``<part> · <joint>`` as in the HTML.

    WHY "; " between entries (seen in the real viewer, 2026-11-19): " · " already joins a part and its joint."""

    owner = {joint: part["name"] for part in _parts(payload) for joint in _part_joints(part)}
    ranked = sorted((joint for joint in payload["joint_names"] if math.isfinite(rms[joint])), key=lambda joint: -rms[joint])
    return "; ".join(f"**{index}.** {owner[joint]} · {_short(joint)} {rms[joint]:.2f}°"
                     for index, joint in enumerate(ranked, start=1)) + "\n"


def _ranking_view(part: dict[str, Any], rms: dict[str, float]) -> Any:
    """The part's ranking bars (``/stats/joint_rms/<part>``), the worst joint first in the title, then the bar order.

    WHY the answer first (Zach 2026-11-19, traj compare view feedback: titles "super descriptive"): Rerun's bars carry
    no labels and a narrow view truncates its title, so the visible start names the worst joint; the order follows
    the way ``_torque_tab`` names its FB-share bars."""

    joints = _part_joints(part)
    finite = [joint for joint in joints if math.isfinite(rms[joint])]
    worst = max(finite, key=lambda joint: rms[joint]) if finite else None
    answer = f"worst {_short(worst)} {rms[worst]:.2f}°" if worst else "no joint error"
    order = " · ".join(f"{index} {_short(joint)}" for index, joint in enumerate(joints))
    return rrb.BarChartView(origin=f"/stats/joint_rms/{_part(part['name'])}",
                            name=f"{part['name']}: {answer} — RMS joint error of each joint's worst run [°] — bars {order}",
                            plot_legend=_legend(False))


def _track_tab(payload: dict[str, Any], title: str) -> Any:
    reference, tcp = _minuend(payload), payload["tcp_frame"]
    joint_band = " — grey band = tolerance" if _has_verdict(payload, "joint") else ""
    tool_band = " — grey band = tolerance" if _has_verdict(payload, "tcp") else ""
    views = [rrb.TextDocumentView(origin="/scorecard", name=f"Scorecard: every run against the {reference}, worst run first"),
             _ts("/worst/joint_deg", f"Largest joint error at each instant, any joint, |{reference} − run| [°]{joint_band}", legend=True)]
    if _has_tool(payload):
        views.append(_ts("/error/tool/position_mm", f"{tcp} position error, distance |{reference} − run| [mm]{tool_band}"))
    views.append(rrb.TextLogView(origin="/events", name="Events: tolerance breaks and settling, on the clock"))
    return rrb.Vertical(*views, row_shares=[3, 2, 2, 1][: len(views) - 1] + [1], name=title)


def _tool_position_views(payload: dict[str, Any]) -> list[Any]:
    """The tool position per axis: what the ``where`` / ``timing`` tabs show when there is a tool but no tool error."""

    who = _with_reference(payload, "x")
    return [_ts(f"/tcp/{axis}_mm", f"{payload['tcp_frame']} position {axis}, {who} [mm]", legend=True) for axis in "xyz"]


def _where_tab(payload: dict[str, Any], title: str) -> Any:
    if not _has_tool(payload):
        return rrb.Vertical(*_tool_position_views(payload), name=title)
    reference, tcp = _minuend(payload), payload["tcp_frame"]
    axes = ([(f"/error/axes/{_part(f'{label}_mm')}", label) for label in payload["error_axes"]] if payload["error_axes"]
            else [(f"/error/tool/{axis}_mm", axis) for axis in "xyz"])
    return rrb.Vertical(*[_ts(origin, f"{tcp} position error along {label}, {reference} − run [mm]", legend=index == 0)
                          for index, (origin, label) in enumerate(axes)], name=title)


def _joints_tab(payload: dict[str, Any], title: str) -> Any:
    """Ranking bars first, then every joint's error: one part as one grid, several as nested part tabs."""

    reference = _minuend(payload)

    def cell(joint: str) -> Any:
        return _ts(f"/error/positions/{_part(joint)}", f"{_short(joint)}: joint error, {reference} − run [°]")

    parts = _parts(payload)
    ranked = _has_ranking(payload)
    rms = _joint_rms_deg(payload)

    def part_body(part: dict[str, Any], name: str) -> Any:
        if not ranked:
            return _part_grid(part, cell, name)
        return rrb.Vertical(_ranking_view(part, rms), _part_grid(part, cell, "Joint error per joint"),
                            row_shares=[1, 4 if _is_hand(part) else 3], name=name)

    if len(parts) == 1:
        return part_body(parts[0], title)
    body = rrb.Tabs(*[part_body(part, _part_label(part)) for part in parts])
    if not ranked:
        return rrb.Vertical(body, name=title)
    # WHY one ranking line above the part tabs, each part's bars inside its tab (NAVIGATION.md Part B: ranking first,
    # then the part selector; seen in the real viewer, 2026-11-19): four bar charts side by side truncated every title
    # to its part's name, so which of 46 joints is worst never read. The line names it; a part's bars get full width.
    ranking = rrb.TextDocumentView(origin=_JOINT_RANKING,
                                   name=f"Which joint, of all {len(payload['joint_names'])}: worst first, RMS joint error of each "
                                        f"joint's worst run, {reference} − run [°]")
    return rrb.Vertical(ranking, body, row_shares=[1, 6], name=title)


def _timing_tab(payload: dict[str, Any], title: str) -> Any:
    tcp, reference = payload["tcp_frame"], _minuend(payload)
    views = []
    if _has_tool(payload):
        views += [_ts("/error/tool/lag_time_ms", f"Lag time: how far behind schedule the {tcp} is along the path, + = behind [ms]",
                      legend=True),
                  _ts("/error/tool/contour_mm", f"Contour error: {tcp} distance off the {reference} path, timing ignored [mm]")]
    views += [_ts(f"/vec/{_part(label)}", f"{tcp} speed along {label}, signed, {_with_reference(payload, f'vec{index}_d')} [m/s]")
              for index, label in enumerate(payload["vec_labels"])]
    return rrb.Vertical(*(views or _tool_position_views(payload)), name=title)


def _hand_torque_cell(joint: str, context: TorqueContext) -> Any:
    """One finger joint's torque: the worst run's breakdown, its FB share in the title (no legend, no bars)."""

    worst, reference = context[0], context[4]
    share = ((worst.get("torque_budget") or {}).get(joint) or {}).get("fb_share")
    lead = f"FB share {share * 100.0:.0f} % · " if share is not None else ""
    return _ts(f"/torque/{_part(joint)}",
               f"{_short(joint)}: {lead}{_short_run(worst)} — {reference}, commanded, feedforward, feedback, applied [N·m]",
               contents=["+ $origin/target", f"+ $origin/{_part(worst['name'])}/**"])


def _torque_part(part: dict[str, Any], context: TorqueContext, name: str) -> Any:
    """One part's torque: an arm one row per joint (as ``_torque_tab``), a hand one row per finger.

    WHY a hand cell is one plot, the worst run's breakdown with its FB share leading the title (seen in the real viewer
    at 1440 × 900, 2026-11-19): a finger row holds 3-4 joints, so the legend covered the plot, stacked views left it no
    height, and beside the share bars both titles shrank to "l thum". The components keep their fixed colours
    (feedforward blue, feedback orange), as in every arm row, where the legend names them."""

    if not _is_hand(part):
        # WHY a legend on the first row only (seen in the real viewer at 1440 × 900, 2026-11-19): every row's legend
        # names the same run and components, and on a 6-joint arm it covered half of each plot.
        return rrb.Vertical(*[_torque_row(joint, context, legend=index == 0) for index, joint in enumerate(_part_joints(part))],
                            name=name)
    return rrb.Vertical(*[rrb.Horizontal(*[_hand_torque_cell(joint, context) for joint in group["joints"]], name=group["name"])
                          for group in part["groups"]], name=name)


def _torque_question_tab(payload: dict[str, Any], title: str) -> Any:
    context = _torque_context(payload)
    if context is None:
        return None
    return _per_part(payload, title, lambda part, name: _torque_part(part, context, name))


# The signals sub-tabs: (entity field, sub-tab title, what the view draws, unit, payload plot key). Motor current comes
# last, only when a situation has it (docs/NAVIGATION.md C1).
_SIGNALS = (
    ("positions", "Angle [°]", "joint angle", "°", "q"),
    ("velocities", "Speed [°/s]", "joint speed", "°/s", "qd"),
    ("effort", "Applied torque [N·m]", "applied torque", "N·m", "tau"),
    ("current", "Motor current [A]", "motor current", "A", "current"),
)
_OPTIONAL_SIGNALS = {"effort": "has_tau", "current": "has_current"}


def _signals_tab(payload: dict[str, Any], title: str) -> Any:
    signals = [signal for signal in _SIGNALS if signal[0] not in _OPTIONAL_SIGNALS or payload.get(_OPTIONAL_SIGNALS[signal[0]])]

    def part_signals(part: dict[str, Any], name: str) -> Any:
        tabs = []
        for field, tab_title, what, unit, key in signals:
            who = _with_reference(payload, key)
            if field == "effort" and who != "every run":  # the reference's torque is planned, never applied
                what, who = "torque", f"{_minuend(payload)} (planned) and every run (applied)"

            def cell(joint: str, field: str = field, what: str = what, unit: str = unit, who: str = who) -> Any:
                return _ts(f"/{field}/{_part(joint)}", f"{_short(joint)}: {what}, {who} [{unit}]")

            tabs.append(_part_grid(part, cell, tab_title))
        return rrb.Tabs(*tabs, name=name)

    return _per_part(payload, title, part_signals)


def _channel_view_title(channel: dict[str, Any]) -> str:
    """``<title> [<unit>]``, or the title alone without a unit (never ``[]``): NAVIGATION.md C1."""

    return f"{channel['title']} [{channel['unit']}]" if channel["unit"] else channel["title"]


def _channel_column(channel: dict[str, Any], index: int) -> str:
    """A channel column's entity part before escaping: ``value`` for a 1-D channel, else its label."""

    return "value" if channel["ndim"] == 1 else channel["columns"][index]


def _channels_tab(payload: dict[str, Any], title: str) -> Any:
    """One view per recorded channel, titled ``<title> [<unit>]``, holding all its columns and situations.

    WHY one view per channel, not per column as in the HTML (NAVIGATION.md C1): a Rerun view overlays every entity
    under its origin, and the legend names each line ``<run> · <column>``."""

    channels = payload.get("channels") or []
    if not channels:
        return None
    views = [_ts(f"/channels/{_part(channel['name'])}", _channel_view_title(channel), legend=True) for channel in channels]
    return rrb.Vertical(*views, name=title) if len(views) < 3 else rrb.Grid(*views, grid_columns=2, name=title)


_QUESTION_TABS: dict[str, Callable[[dict[str, Any], str], Any]] = {
    "track": _track_tab,
    "where": _where_tab,
    "joints": _joints_tab,
    "timing": _timing_tab,
    "torque": _torque_question_tab,
    "signals": _signals_tab,
    "channels": _channels_tab,
}


def _question_index(shown: list[str], titles: list[str], check_titles: list[str], tab: str | None) -> int | None:
    """The index of ``tab`` (an id, a title, a pre-2026-11-19 title or a check tab's name) among this layout's tabs."""

    if tab is None:
        return None
    if tab in check_titles:  # a check tab is named by its caller, never in traj_compare.tabs
        return len(shown) + check_titles.index(tab)
    try:
        wanted = resolve_tab(tab).id
    except ValueError:
        raise ValueError(f"no tab {tab!r} in this layout; tabs: {', '.join(titles + check_titles)}") from None
    if wanted not in shown:
        raise ValueError(f"tab {tab!r} has nothing to show in this comparison; tabs: {', '.join(titles + check_titles)}")
    return shown.index(wanted)


def _layout_questions(payload: dict[str, Any], videos: dict[str, Path], overlays: list[str], tab: str | None = None,
                      checks: Checks = ()) -> Any:
    """'questions': a pinned stage (3D over the camera) on the left; the shared question tabs beside it.

    WHY (Zach's pick, 2026-11-11, babble V2 at 88/100): the opening tab alone answers pass/fail, which
    run is worst and when, and the robot and camera never leave the screen while you work through
    where, which joint, and timing-or-shape. WHY the shared tabs (Zach 2026-11-19, traj compare view feedback:
    "designing a different run viewer for standalone and rerun is a bit silly ... they should be the exact same
    thing"): the titles and the drop rule are ``traj_compare.tabs``', the HTML run view's own. ``checks`` groups
    each get a last tab and leave the rest."""

    full, payload = payload, _without_checks(payload, checks)
    tabs, shown, titles = [], [], []
    for entry in full.get("tabs") or tabs_for(full):
        container = _QUESTION_TABS[entry["id"]](payload, entry["title"])
        if container is not None:
            tabs.append(container)
            shown.append(entry["id"])
            titles.append(entry["title"])

    stage = []
    if _has_world(payload):
        stage.append(_world(payload, f"3D: every run's robot and {payload['tcp_frame']} path", ["/world/**"],
                            eye_controls=_stage_eye(payload)))
    camera = _camera_origin(videos, overlays)
    if camera:
        stage.append(rrb.Spatial2DView(origin=camera, name="Camera overlay: the real camera with the sim renders over it"
                                       if overlays else "Camera: the run's video, at the playhead"))
    for container in tabs + stage:
        _exclude(container, _check_parts(checks))
    tabs += [_check_tab(full, *check) for check in checks]
    questions = rrb.Tabs(*tabs, active_tab=_question_index(shown, titles, [title for _, title, _ in checks], tab))
    if not stage:
        return rrb.Blueprint(questions, *_panels())
    # WHY 2 : 5 (was 2 : 3; seen in the real viewer, 2026-11-19): at 1440 px the six descriptive tab titles need
    # about 1000 px, and at 2 : 3 the last two hid behind the tab strip's scroll arrow. The stage still shows the robot.
    return rrb.Blueprint(rrb.Horizontal(rrb.Vertical(*stage, row_shares=[3, 2][: len(stage)]), questions, column_shares=[2, 5]),
                         *_panels())


def _layout_evo(payload: dict[str, Any], videos: dict[str, Path], overlays: list[str], tab: str | None = None,
                checks: Checks = ()) -> Any:
    """'evo': evo's own Rerun layout (evo_ape --rerun: Visualization + Raw data) with a full-screen tab per analysis.

    WHY (Zach's pick, 2026-11-11): evo is the reference he named; its blueprint is copied, not
    reinvented — the error-coloured path and the error curve draw themselves up to the playhead.
    ``checks`` groups each get a last tab and leave the rest."""

    full, payload = payload, _without_checks(payload, checks)
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
        tabs.append(rrb.Grid(*[_ts(f"/positions/{j}", f"{_short(j)} [°]") for j in joints], grid_columns=min(3, len(joints)),
                             name="Trajectories"))
    tabs.append(rrb.Grid(*[_ts(f"/error/positions/{j}", f"{_short(j)} error [°]") for j in joints],
                         grid_columns=min(3, len(joints)), name="Joint error"))
    if tool:
        along = _where_views(payload) + [_ts("/error/tool/contour_mm", "contour error [mm]"),
                                         _ts("/error/tool/lag_time_ms", "lag time [ms]")]
        along += [_ts(f"/vec/{_part(label)}", f"speed along {label} [m/s]") for label in payload["vec_labels"]]
        tabs.append(rrb.Grid(*along, grid_columns=3, name="Along / across"))
    torque = _torque_tab(payload, "Torque")
    if torque is not None:
        tabs.append(torque)
    if videos or overlays:
        big = _camera_origin(videos, overlays)
        small = [rrb.Spatial2DView(origin=f"/video/{_part(name)}", name=name) for name in videos]
        tabs.append(rrb.Horizontal(rrb.Spatial2DView(origin=big, name="Camera overlay" if overlays else "Camera"),
                                   *([rrb.Vertical(*small)] if small and overlays else []),
                                   column_shares=[3, 1][: 1 + bool(small and overlays)], name="Video"))
    tabs.append(rrb.Horizontal(rrb.TextDocumentView(origin="/scorecard", name="Scorecard"),
                               rrb.TextDocumentView(origin="/notes", name="Full statistics"), name="Stats"))
    tabs.append(rrb.DataframeView(origin="/error", name="Raw data"))
    for container in tabs:
        _exclude(container, _check_parts(checks))
    tabs += [_check_tab(full, *check) for check in checks]
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
                     tab: str | None = None, checks: Mapping[str, str] | None = None) -> Any:
    """The named layout's blueprint for one comparison payload, opening on ``tab`` (by name) if given.

    ``checks`` maps a situation ``group`` to a tab title (``{"camera": "Camera Check"}``): that group's runs
    leave every other view and get that tab, beside every run they check. A comparison without the group
    gets no tab."""

    _require_sdk()
    return LAYOUTS[_check_layout(name)][1](payload, videos, list(overlays), tab, _check_groups(payload, checks))


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


VIEWS = ("auto", "layouts", "target_vs_run")


def rerun_view(comparison: Comparison, *, checks: Mapping[str, str] | None = None) -> str:
    """Which recording ``write_rrd(view="auto")`` writes for ``comparison``: ``"target_vs_run"`` for one target and one
    run with data on a URDF (``RobotDisplay.urdf``) and no video (``rerun_target_run.comparison_inputs``), else
    ``"layouts"`` (the named layouts' recording: the question tabs or evo's). ``checks`` asks for the layouts."""

    return "target_vs_run" if not checks and comparison_inputs(comparison) is not None else "layouts"


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
    checks: Mapping[str, str] | None = None,
    view: str = "auto",
) -> Path:
    """Write ``comparison`` as one .rrd and return its path.

    ``view``: ``"auto"`` (the default) writes the target-vs-run recording (``write_target_vs_run_rrd``: the run as its
    URDF arm, the target and its error on top, an Error tab first) when the comparison is one target and one run on a
    URDF (``rerun_view``), else the named layouts' recording below. ``"layouts"`` always writes the latter,
    ``"target_vs_run"`` the former or raises ``ValueError`` saying why it cannot. WHY auto (Zach, 2026-11-25: a lone
    trajectory keeps robot_msgs' viewer, a run with a target gets the pick round's V2): only a ``RobotDisplay`` with a
    ``urdf`` qualifies, a field older callers never set, so their recordings are unchanged. A target-vs-run .rrd has no
    ``.rbl`` files beside it (they lay out the other recording); the hooks below apply to the layouts' recording only.

    ``layout`` names the embedded layout (``LAYOUTS``; default: the user's ``default_layout()``).
    Every layout is also written beside the .rrd as ``<stem>.<layout>.rbl`` so any of them opens
    with ``viewer_argv(path, layout=...)``. ``payload`` is an already-computed ``analyze_comparison``
    result (colours included) so a report that also writes the HTML does not analyze twice; omitted,
    it is computed here. ``video_root`` is the directory ``Situation.video`` and ``CameraOverlay``
    paths are relative to (default: beside the .rrd). ``checks`` (``{"camera": "Camera Check"}``) gives
    each named situation group its own tab, out of every other view and summary (``layout_blueprint``).

    Hooks for trying another layout without forking the writer: ``blueprint(payload, videos)``
    replaces the named layout; ``application_id`` keeps several layouts of one comparison apart when
    they are open in one viewer; ``extra(recording, payload, t0)`` logs more entities.
    """

    _require_sdk()
    from .report import _colorize

    layout = _check_layout(layout) if layout is not None else default_layout()
    if view not in VIEWS:
        raise ValueError(f"view is one of {VIEWS}, got {view!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if view != "layouts":
        hooks = [name for name, given in (("blueprint", blueprint), ("extra", extra), ("checks", checks)) if given]
        inputs = None if hooks else comparison_inputs(comparison)
        if view == "target_vs_run" and inputs is None:
            raise ValueError(
                "view='target_vs_run' draws one target and one run with data on a URDF (RobotDisplay.urdf), with no "
                f"video{f' and no {hooks}' if hooks else ''}; this comparison is not that: use view='layouts'"
            )
        if inputs is not None:
            written = write_target_vs_run_rrd(path, **inputs, application_id=application_id,
                                              recording_name=_recording_name(comparison))
            for name in LAYOUTS:  # a stale layout file beside it would open the wrong recording's tabs
                blueprint_path(path, name).unlink(missing_ok=True)
            return written
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
    embedded = blueprint(payload, videos) if blueprint else layout_blueprint(layout, payload, videos, list(overlays), checks=checks)
    # WHY under a temporary name, renamed into place once whole (NAVIGATION.md D2): a drill-down rebuilt in a
    # hard-linked copy of a site must not write through to the original's .rrd, nor leave a torn one when stopped.
    with _files.replacing(path) as temporary:
        recording.save(temporary, default_blueprint=embedded)
        writer = _Writer(recording, t0)

        plot_t = _array(payload["plot_t"]) - t0 if payload["plot_t"] is not None else None
        for entry in payload["situations"]:
            if not entry["has_data"] or plot_t is None:
                continue
            name = _part(entry["name"])
            color = _hex_to_rgb(entry["color"])
            label = entry["title"]
            plot = entry["plot"]
            joints = list(payload["joint_names"])
            columns = lambda key: np.array([_array(row) for row in plot[key]]).T  # (samples, joints)
            signals = JointTrajectory(
                t=plot_t, joint_names=joints, positions=columns("q"), velocities=columns("qd"),
                effort=columns("tau") if plot["tau"] is not None else None,
            )  # fmt: skip
            # /positions, /velocities (degrees: every joint shown as revolute, as in the HTML report), /effort
            viz.log(signals, entry["name"], recording=recording, degrees=True, color=color, label=label, t0=0.0)
            if "err_q" in plot:
                # WHY from the payload: target - run, straight from robot_msgs.compare, so the HTML and the
                # .rrd can never disagree; at /error/positions/<joint>/<run>, in degrees (the display edge).
                error = JointTrajectory(t=plot_t, joint_names=joints, positions=columns("err_q"))
                viz.log(error, entry["name"], recording=recording, degrees=True, color=color, label=label,
                        prefix="error/", t0=0.0)  # fmt: skip
            if plot["current"] is not None:
                # /current/<joint>/<situation>, A: the signals tab's "Motor current [A]" sub-tab (NAVIGATION.md C1)
                for column, joint in enumerate(joints):
                    writer.series(f"/current/{_part(joint)}/{name}", plot_t, _array(plot["current"][column]), color, label)
            # /channels/<name>/<column>/<situation>: every other recorded signal, as recorded (no unit conversion).
            # WHY every one, described or not (NAVIGATION.md C1, truthful rendering): a recorded signal is never dropped.
            for channel in payload.get("channels") or []:
                recorded = (entry.get("channels") or {}).get(channel["name"])
                if recorded is None:
                    continue
                for index, values in enumerate(recorded):
                    column = _channel_column(channel, index)
                    series_label = label if channel["ndim"] == 1 else f"{label} · {column}"
                    writer.series(f"/channels/{_part(channel['name'])}/{_part(column)}/{name}", plot_t, _array(values),
                                  color, series_label)  # fmt: skip
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
            if payload.get("has_torque_breakdown"):
                # /torque/<joint>/target and /torque/<joint>/<run>/<component> (CONTRACT.md, 2026-11-19), N·m
                for column, joint in enumerate(joints):
                    torque = f"/torque/{_part(joint)}"
                    if entry["role"] == "target":
                        if plot["tau"] is not None:
                            writer.series(f"{torque}/target", plot_t, _array(plot["tau"][column]),
                                          _hex_to_rgb(TARGET_TORQUE_COLOR),
                                          f"{label} · applied" if payload.get("reference_kind") == "run" else f"{label} · target",
                                          _TORQUE_WIDTHS["target"])
                        continue
                    if not _has_breakdown(entry):
                        continue
                    for key, leaf in _TORQUE_COMPONENTS:
                        if plot[key] is None:
                            continue
                        tone = {"feedforward": _hex_to_rgb(FEEDFORWARD_COLOR), "feedback": _hex_to_rgb(FEEDBACK_COLOR)}.get(leaf, color)
                        derived = " (derived)" if key in entry["derived"] else ""  # the other two gave it
                        writer.series(f"{torque}/{name}/{leaf}", plot_t, _array(plot[key][column]), tone,
                                      f"{label} · {leaf}{derived}", _TORQUE_WIDTHS[leaf])

            if entry["three"] is not None:
                writer.tcp(f"/world/{name}/tcp", entry["three"], color)
            robot = by_name[entry["name"]].robot or comparison.robot
            if robot is not None and entry["robot_track"] is not None:
                viz.links(_robot_links(robot, entry["robot_track"]), entry["name"], recording=recording,
                          color=_link_colors(robot, color), t0=t0)  # fmt: skip
            if entry["name"] in videos:
                # a video plays at video time = trajectory time - video_start_s, as in the HTML viewer
                viz.video(videos[entry["name"]], entry["name"], recording=recording, start_s=entry.get("video_start_s", 0.0) - t0)
        for overlay_name, (baked, start_s) in overlays.items():
            viz.video(baked, _overlay_entity(overlay_name), recording=recording, start_s=start_s - t0)

        recording.log(
            "/notes",
            rr.TextDocument(_notes_markdown(payload), media_type=rr.MediaType.MARKDOWN),
            static=True,
        )
        _log_review_entities(recording, writer, comparison, payload, t0, checks=checks)
        if extra is not None:
            extra(recording, payload, t0)
        recording.flush()
        recording.disconnect()
    # every named layout beside the file, so the user's other preference is one argument away
    for name in LAYOUTS:
        with _files.replacing(blueprint_path(path, name)) as temporary:
            layout_blueprint(name, payload, videos, list(overlays), checks=checks).save(application_id, temporary)
    return path
