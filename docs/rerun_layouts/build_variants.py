"""Five Rerun layouts for one traj_compare comparison — a babble round (2026-11-11).

Prototype, not the shipped layout: every variant writes the SAME recording (the UR5e conveyor
target -> sim & 5 stand-in real runs) with a different embedded blueprint, under its own
application id so all five can be open in one viewer at once and compared side by side.

Shared extras every variant may use (logged once per file through ``write_rrd(extra=...)``):

    /deg/error/<joint>/<run>        joint error, target - run, in degrees (the display edge; SI stays in /error/joint)
    /deg/error/<joint>/tolerance_±  the path tolerance, then the goal tolerance once the target ends
    /deg/position|velocity/<joint>/<run>
    /error/tool/position_mm/tolerance   the TCP path / goal position tolerance
    /worst/joint_deg/<run>          the largest |joint error| of any joint at each instant
    /tcp/<axis>_mm/<run>            the TCP position along each error axis (belt frame), evo's "xyz"
    /heat/<run>                     the run's TCP path coloured by its position error (green -> red at the tolerance)
    /video/overlay                  our own composite: the real camera with the sim and target renders laid over
    /events                         first tolerance violation and settle per run, as a text log
    /scorecard, /notes/<run>        a verdict-first summary table, and one page per run

Run (with the integration venv, which has Pinocchio for the UR5e and the rerun extra):

    traj_integration_tests/.venv/bin/python traj_compare/docs/rerun_layouts/build_variants.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from traj_compare.analysis import analyze_comparison
from traj_compare.report import _colorize
from traj_compare.rerun_export import _resolvable_videos, _array, _hex_to_rgb, _notes_markdown, _part, _Writer, write_rrd

DEG = 180.0 / math.pi
FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"


# ── the fixture ─────────────────────────────────────────────────────────────


def build_fixture(work: Path):
    """The UR5e 'Target -> Sim & Real' comparison, exactly as the site example builds it."""

    from traj_integration_tests.ur_compare import sim_to_real

    captured: dict[str, Any] = {}

    def capture(comparisons, out, **_):
        captured["comparisons"] = comparisons
        return Path(out) / "report.html"

    sim_to_real.write_comparison_report = capture  # WHY: we want the Comparison objects, not the report
    sim_to_real.run_ur_sim_to_real(work, fast=False)
    return captured["comparisons"][0]


def composite_overlay(work: Path, out: Path) -> Path:
    """Our own overlay: real #1's camera with the sim and target renders darken-blended on top.

    WHY pre-composited: Rerun shows a video as-is, so the overlay the HTML viewer blends live is
    baked here into one MP4 the standard video view can play (Zach, 2026-11-11)."""

    # each render: title band blanked, cropped to the robot, scaled up; the sim and target layers keyed
    # (their near-white background made transparent) and laid over the real camera at partial opacity
    prep = "drawbox=x=0:y=0:w=iw:h=50:color=0xfbfbf8:t=fill,crop=320:270:170:50,scale=960:810"
    graph = (
        f"[0:v]{prep}[real];"
        f"[1:v]{prep},colorkey=0xfbfbf8:0.18:0.05,format=rgba,colorchannelmixer=aa=0.65[sim];"
        f"[2:v]{prep},colorkey=0xfbfbf8:0.18:0.05,format=rgba,colorchannelmixer=aa=0.55[target];"
        "[real][sim]overlay=format=auto[a];[a][target]overlay=format=auto,"
        "drawtext=text='Real #1 camera (orange)  +  Sim render (blue)  +  Target (grey)':x=(w-tw)/2:y=14:fontsize=26:fontcolor=0x333333,"
        "format=yuv420p[v]"
    )
    command = [
        FFMPEG, "-y", "-loglevel", "error",
        "-i", str(work / "ur5e_conveyor__real_1.mp4"),
        "-i", str(work / "ur5e_conveyor__sim.mp4"),
        "-i", str(work / "ur5e_conveyor__target.mp4"),
        "-filter_complex", graph, "-map", "[v]",
        "-c:v", "libx264", "-bf", "0", "-g", "30", "-crf", "20", str(out),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    return out


# ── the shared extras ───────────────────────────────────────────────────────


def _heat_rgb(fraction: np.ndarray) -> np.ndarray:
    """0 -> green, 0.5 -> amber, >= 1 (the tolerance) -> red."""

    stops = np.array([[47, 158, 68], [245, 159, 0], [224, 49, 49]], dtype=float)
    f = np.clip(fraction, 0.0, 1.0) * 2.0
    low = np.floor(np.minimum(f, 1.999)).astype(int)
    mix = (f - low)[:, None]
    return (stops[low] * (1 - mix) + stops[low + 1] * mix).astype(np.uint8)


def make_extras(comparison, overlay_mp4: Path | None) -> Callable[[Any, dict, float], None]:
    tol_path = {j.name: j.position for j in comparison.tolerances.path}
    tol_goal = {j.name: j.position for j in comparison.tolerances.goal}
    tcp_path_m = comparison.tcp_tolerances.path.position
    tcp_goal_m = comparison.tcp_tolerances.goal.position

    def extras(recording, payload: dict, t0: float) -> None:
        writer = _Writer(recording, t0)
        plot_t = _array(payload["plot_t"]) - t0
        target_end = float(comparison.target.t[-1]) - t0
        band_rgba = [120, 120, 120, 70]
        in_goal = plot_t >= target_end

        def band(entity: str, low: np.ndarray, high: np.ndarray) -> None:
            """A shaded tolerance band: Rerun's Measurements draws value ± one standard deviation."""
            recording.log(entity, rr.Measurements.from_fields(colors=[band_rgba], names=["tolerance"], widths=[0.5]), static=True)
            recording.send_columns(
                entity,
                indexes=[rr.TimeColumn("t", duration=plot_t)],
                columns=rr.Measurements.columns(values=0.5 * (low + high), variances=(0.5 * (high - low)) ** 2),
            )

        for joint in payload["joint_names"]:
            limit = np.where(in_goal, tol_goal[joint], tol_path[joint]) * DEG
            band(f"/deg/error/{_part(joint)}/tolerance", -limit, limit)
        band_mm = np.where(in_goal, tcp_goal_m, tcp_path_m) * 1000.0
        band("/error/tool/position_mm/tolerance", np.zeros_like(band_mm), band_mm)
        worst_limit = np.where(in_goal, max(tol_goal.values()), max(tol_path.values())) * DEG
        band("/worst/joint_deg/tolerance", np.zeros_like(worst_limit), worst_limit)
        reference = next(entry for entry in payload["situations"] if entry["three"] is not None and "err_q" not in entry["plot"])
        recording.log("/path/reference", rr.LineStrips3D([np.asarray(reference["three"]["p"], dtype=float)],
                                                         colors=[_hex_to_rgb(reference["color"])], radii=0.0015), static=True)
        bar_runs: list[str] = []
        tool_errors: list[np.ndarray] = []
        bar_rms: list[float] = []

        events: list[tuple[float, str, str]] = []
        score_rows = []
        for entry in payload["situations"]:
            if not entry["has_data"]:
                continue
            name, color, label, plot = _part(entry["name"]), _hex_to_rgb(entry["color"]), entry["title"], entry["plot"]
            for dof, joint in enumerate(payload["joint_names"]):
                part = _part(joint)
                writer.series(f"/deg/position/{part}/{name}", plot_t, _array(plot["q"][dof]) * DEG, color, label)
                writer.series(f"/deg/velocity/{part}/{name}", plot_t, _array(plot["qd"][dof]) * DEG, color, label)
                if "err_q" in plot:
                    writer.series(f"/deg/error/{part}/{name}", plot_t, _array(plot["err_q"][dof]) * DEG, color, label)
            for axis, key in (("x", "x"), ("y", "y"), ("z", "z")):
                if key in plot:
                    writer.series(f"/tcp/{axis}_mm/{name}", plot_t, _array(plot[key]) * 1000.0, color, label)
            if "err_q" not in plot:
                continue  # the reference itself has no error
            err = np.abs(np.array([_array(row) for row in plot["err_q"]]))
            worst = np.nanmax(err, axis=0) * DEG
            writer.series(f"/worst/joint_deg/{name}", plot_t, worst, color, label)

            # the TCP path coloured by its position error, sampled on the plot clock
            position_mm = _array(plot["xyz_mag"]) * 1000.0
            xyz = np.column_stack([_array(plot["x"]), _array(plot["y"]), _array(plot["z"])])
            ok = np.all(np.isfinite(xyz), axis=1) & np.isfinite(position_mm)
            xyz, heat = xyz[ok], position_mm[ok]
            segments = np.stack([xyz[:-1], xyz[1:]], axis=1)
            fraction = 0.5 * (heat[:-1] + heat[1:]) / (tcp_path_m * 1000.0)
            heat_colors = _heat_rgb(fraction)
            recording.log(f"/heat/{name}", rr.LineStrips3D(segments, colors=heat_colors, radii=0.003), static=True)
            # the same path as a trail on the clock: with a growing time range it draws itself as you play (evo)
            heat_t = plot_t[ok][1:]
            for when, segment, rgb in zip(heat_t, segments, heat_colors, strict=True):
                recording.set_time("t", duration=float(when))
                recording.log(f"/trail/{name}", rr.LineStrips3D([segment], colors=[rgb], radii=0.003))
            tool_errors.append(position_mm)
            bar_runs.append(label)
            bar_rms.append(float(np.sqrt(np.nanmean(position_mm ** 2))))

            verdict = (entry.get("verdict") or {}).get("joint") or {}
            tcp_verdict = (entry.get("verdict") or {}).get("tcp") or {}
            for outcome, frame in ((verdict, "joints"), (tcp_verdict, payload["tcp_frame"])):
                for violation in outcome.get("violations", [])[:1]:
                    events.append((violation["t"] - t0, "WARN",
                                   f"{label}: {frame} {violation['phase']} tolerance broken on {violation['metric']}"))
            for key in ("joint",):
                for metric, stats in ((entry.get("goal") or {}).get(key) or {}).items():
                    if stats.get("settling_time") is not None and metric.endswith("elbow_joint"):
                        events.append((target_end + stats["settling_time"], "INFO",
                                       f"{label}: elbow settled {stats['settling_time']:.2f} s after the target ended"))
            latency = (entry.get("latency") or {}).get("offset_s")
            score_rows.append({
                "run": label,
                "verdict": verdict.get("code_name", "—"),
                "tcp_verdict": tcp_verdict.get("code_name", "—"),
                "tool_rms": float(np.sqrt(np.nanmean(position_mm ** 2))),
                "tool_max": float(np.nanmax(position_mm)),
                "worst_joint": float(np.nanmax(worst)),
                "latency_ms": None if latency is None else latency * 1000.0,
            })
            recording.log(f"/notes/{name}", rr.TextDocument(_run_page(payload, entry, score_rows[-1]),
                                                             media_type=rr.MediaType.MARKDOWN), static=True)
        for when, level, text in sorted(events):
            recording.set_time("t", duration=when)
            recording.log("/events", rr.TextLog(text, level=level))
        # the reference path coloured by the WORST run's tool error at each instant: where on the path,
        # across every run, the error is highest (the dataset-level question, Nov 11)
        worst_mm = np.nanmax(np.vstack(tool_errors), axis=0)
        reference_t = _array(reference["three"]["t"]) - t0
        reference_p = np.asarray(reference["three"]["p"], dtype=float)
        finite = np.isfinite(worst_mm)
        worst_on_path = np.interp(reference_t, plot_t[finite], worst_mm[finite])
        segments = np.stack([reference_p[:-1], reference_p[1:]], axis=1)
        colors = _heat_rgb(0.5 * (worst_on_path[:-1] + worst_on_path[1:]) / (tcp_path_m * 1000.0))
        recording.log("/heat_worst", rr.LineStrips3D(segments, colors=colors, radii=0.004), static=True)
        for when, segment, rgb in zip(reference_t[1:], segments, colors, strict=True):
            recording.set_time("t", duration=float(when))
            recording.log("/trail_worst", rr.LineStrips3D([segment], colors=[rgb], radii=0.004))
        recording.log("/stats/tool_rms_mm", rr.BarChart(np.array(bar_rms), color=[90, 90, 90]), static=True)
        recording.log("/scorecard", rr.TextDocument(_scorecard(payload, score_rows), media_type=rr.MediaType.MARKDOWN),
                      static=True)
        if overlay_mp4 is not None:
            writer.video("/video/overlay", overlay_mp4, 0.0)

    return extras


def _scorecard(payload: dict, rows: list[dict]) -> str:
    worst = max(rows, key=lambda row: row["tool_max"])
    lines = [
        f"# {payload['title']}",
        "",
        f"**Worst run: {worst['run']}** — tool error peaks at {worst['tool_max']:.1f} mm.",
        "",
        "| Run | Joints | TCP | Tool RMS | Tool max | Worst joint | Latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda row: -row["tool_max"]):
        latency = "—" if row["latency_ms"] is None else f"{row['latency_ms']:.1f} ms"
        lines.append(
            f"| {row['run']} | {row['verdict']} | {row['tcp_verdict']} | {row['tool_rms']:.2f} mm | "
            f"{row['tool_max']:.2f} mm | {row['worst_joint']:.3f}° | {latency} |"
        )
    return "\n".join(lines) + "\n"


def _run_page(payload: dict, entry: dict, row: dict) -> str:
    lines = [f"# {entry['title']}", "", f"vs **{payload['reference_title']}**", "",
             f"- Joints: **{row['verdict']}** · TCP: **{row['tcp_verdict']}**",
             f"- Tool error: RMS {row['tool_rms']:.2f} mm, max {row['tool_max']:.2f} mm",
             f"- Worst joint error: {row['worst_joint']:.3f}°"]
    if row["latency_ms"] is not None:
        lines.append(f"- Estimated latency: {row['latency_ms']:.1f} ms")
    lines += ["", "| Joint | RMS | Max |", "|---|---|---|"]
    for joint in payload["joint_names"]:
        stats = entry["error_metrics"].get(f"positions/{joint}")
        if stats:
            lines.append(f"| {joint} | {stats['rms'] * DEG:.3f}° | {stats['max_abs'] * DEG:.3f}° |")
    return "\n".join(lines) + "\n"


# ── the five layouts ────────────────────────────────────────────────────────

HIDE = rrb.PlotLegend(visible=False)
SHOT_MODE = {"paused": False}  # the screenshot blueprints open paused, so the harness can set the playhead
GROWING = [rrb.VisibleTimeRange("t", start=rrb.TimeRangeBoundary.infinite(), end=rrb.TimeRangeBoundary.cursor_relative(seconds=0.0))]
TRAILING = [rrb.VisibleTimeRange("t", start=rrb.TimeRangeBoundary.cursor_relative(seconds=-1.5),
                                 end=rrb.TimeRangeBoundary.cursor_relative(seconds=0.5))]


def _ts(origin: str, name: str, legend: bool = False, **kwargs: Any) -> Any:
    """A time-series view whose x zoom is linked to every other plot (zoom one, they all follow)."""

    return rrb.TimeSeriesView(origin=origin, name=name, plot_legend=None if legend else HIDE,
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"), **kwargs)


def _chrome(time_panel: str = "collapsed") -> list[Any]:
    extra = {"play_state": "paused"} if SHOT_MODE["paused"] else {}
    return [rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
            rrb.TimePanel(state=time_panel, **extra)]


EYE: dict[str, Any] = {}  # set once per payload by _frame(): every 3D view opens on the same framed camera


def _frame(payload: dict) -> None:
    """A default camera that frames the robot and its tool path from the front-right, z up."""

    reference = next(entry for entry in payload["situations"] if entry["three"] is not None)
    path = np.asarray(reference["three"]["p"], dtype=float)
    look = 0.5 * (path.mean(axis=0) + np.array([0.0, 0.0, 0.35]))
    reach = max(float(np.ptp(path, axis=0).max()), 0.6)
    EYE["robot"] = rrb.EyeControls3D(kind="Orbital", look_target=look, eye_up=[0, 0, 1],
                                     position=look + reach * np.array([1.5, -1.9, 1.1]))
    centre = path.mean(axis=0)
    span = max(float(np.ptp(path, axis=0).max()), 0.05)
    EYE["path"] = rrb.EyeControls3D(kind="Orbital", look_target=centre, eye_up=[0, 0, 1],
                                    position=centre + span * np.array([0.6, -0.85, 0.75]))


def _world(name: str = "3D", contents: list[str] | None = None, **kwargs: Any) -> Any:
    contents = contents or ["/world/**"]
    has_robot = any(item.startswith("/world/") and item.endswith("/**") for item in contents)
    return rrb.Spatial3DView(origin="/", contents=contents, name=name, line_grid=rrb.LineGrid3D(visible=False),
                             eye_controls=EYE.get("robot" if has_robot else "path"), **kwargs)


def _runs(payload: dict) -> list[dict]:
    return [entry for entry in payload["situations"] if entry["has_data"] and "err_q" in entry["plot"]]


def _joints(payload: dict) -> list[str]:
    return [_part(joint) for joint in payload["joint_names"]]


def _short(joint: str) -> str:
    return joint.replace("_joint", "").replace("_", " ")


def _run_label(entry: dict) -> str:
    return entry["title"].replace(" (stand-in)", "")


def _bar_name(payload: dict) -> str:
    order = " · ".join(f"{index} {_run_label(entry)}" for index, entry in enumerate(_runs(payload)))
    return f"Tool RMS error per run [mm] — {order}"


def _joint_error_grid(payload: dict, contents_for: Callable[[str], list[str]] | None = None, columns: int = 3) -> Any:
    views = []
    for joint in _joints(payload):
        origin = f"/deg/error/{joint}"
        kwargs = {"contents": contents_for(origin)} if contents_for else {}
        views.append(_ts(origin, f"{_short(joint)} error [°]", **kwargs))
    return rrb.Grid(*views, grid_columns=columns, name="Joint error")


def v1_evo(payload: dict, videos: dict, active: int | None = None) -> Any:
    """evo's own Rerun layout (evo_ape --rerun), extended: Visualization · Raw data, plus one tab per extra analysis."""

    axes = payload["error_axes"]
    visualization = rrb.Vertical(
        _world("Target path coloured by the worst run's tool error (green → red at the 5 mm tolerance), drawn up to the playhead",
               ["/trail_worst", "/world/target/robot/**"], time_ranges=GROWING),
        rrb.Horizontal(
            _ts("/error/tool/position_mm", "Tool position error [mm] — grey band = tolerance", legend=True),
            rrb.BarChartView(origin="/stats/tool_rms_mm", name=_bar_name(payload), plot_legend=HIDE),
            column_shares=[3, 2],
        ),
        row_shares=[3, 2], name="Visualization",
    )
    tabs = rrb.Tabs(
        visualization,
        rrb.Horizontal(
            _world("Robots + paths"),
            rrb.Vertical(*[_ts(f"/tcp/{a}_mm", f"TCP {a} [mm]") for a in "xyz"]),
            column_shares=[3, 2], name="Trajectories",
        ),
        _joint_error_grid(payload),
        rrb.Grid(
            *[_ts(f"/error/axes/{_part(f'{a}_mm')}", f"error {a} [mm]") for a in axes],
            _ts("/error/tool/contour_mm", "contour error [mm]"),
            _ts("/error/tool/lag_time_ms", "lag time [ms]"),
            _ts("/vec/Conveyor", "speed along belt [m/s]"),
            grid_columns=3, name="Along / across",
        ),
        rrb.Horizontal(
            rrb.Spatial2DView(origin="/video/overlay", name="Overlay: real + sim + target"),
            rrb.Vertical(*[rrb.Spatial2DView(origin=f"/video/{_part(n)}", name=n) for n in videos]),
            column_shares=[3, 1], name="Video",
        ),
        rrb.Horizontal(rrb.TextDocumentView(origin="/scorecard", name="Scorecard"),
                       rrb.TextDocumentView(origin="/notes", contents=["/notes"], name="Full statistics"), name="Stats"),
        rrb.DataframeView(origin="/error/tool", name="Raw data"),
        active_tab=active,
    )
    return rrb.Blueprint(tabs, *_chrome())


V1_TABS = ["Visualization", "Trajectories", "Joint error", "Along / across", "Video", "Stats", "Raw data"]


def v2_stage(payload: dict, videos: dict, active: int | None = None) -> Any:
    """A pinned stage (3D over the overlay video) that never leaves, and question tabs beside it."""

    joints = _joints(payload)
    signals = rrb.Tabs(
        rrb.Grid(*[_ts(f"/deg/position/{j}", f"{_short(j)} [°]") for j in joints], grid_columns=2, name="Position"),
        rrb.Grid(*[_ts(f"/deg/velocity/{j}", f"{_short(j)} [°/s]") for j in joints], grid_columns=2, name="Velocity"),
        rrb.Grid(*[_ts(f"/torque/{j}", f"{_short(j)} [N·m]") for j in joints], grid_columns=2, name="Torque"),
        name="Signals",
    )
    questions = rrb.Tabs(
        rrb.Vertical(
            rrb.TextDocumentView(origin="/scorecard", name="Scorecard"),
            _ts("/worst/joint_deg", "Worst joint error, any joint [°] — grey band = tolerance", legend=True),
            _ts("/error/tool/position_mm", "Tool position error [mm]"),
            rrb.TextLogView(origin="/events", name="Events"),
            row_shares=[3, 2, 2, 1], name="Is it good?",
        ),
        rrb.Vertical(*[_ts(f"/error/axes/{_part(f'{a}_mm')}", f"error {a} [mm]") for a in payload["error_axes"]],
                     name="Where?"),
        rrb.Grid(*[_ts(f"/deg/error/{j}", f"{_short(j)} [°]") for j in joints], grid_columns=2, name="Which joint?"),
        rrb.Vertical(
            _ts("/error/tool/lag_time_ms", "Lag time [ms] (how late along the path)", legend=True),
            _ts("/error/tool/contour_mm", "Contour error [mm] (off the path)"),
            _ts("/vec/Conveyor", "Speed along belt [m/s]"),
            name="Timing or shape?",
        ),
        signals,
        active_tab=active,
    )
    stage = rrb.Vertical(_world("Stage"), rrb.Spatial2DView(origin="/video/overlay", name="Camera overlay"), row_shares=[3, 2])
    return rrb.Blueprint(rrb.Horizontal(stage, questions, column_shares=[2, 3]), *_chrome())


V2_TABS = ["Is it good?", "Where?", "Which joint?", "Timing or shape?", "Signals"]


def v3_runs(payload: dict, videos: dict, active: int | None = None) -> Any:
    """One tab per run (drill-down), behind an 'All runs' tab (evo_res) that says which run to open."""

    runs = _runs(payload)
    overview = rrb.Horizontal(
        rrb.Vertical(
            rrb.TextDocumentView(origin="/scorecard", name="Scorecard — worst first"),
            rrb.BarChartView(origin="/stats/tool_rms_mm", name=_bar_name(payload), plot_legend=HIDE),
            row_shares=[3, 2],
        ),
        rrb.Vertical(
            _ts("/error/tool/position_mm", "Tool position error, every run [mm]", legend=True),
            _ts("/worst/joint_deg", "Worst joint error, every run [°]"),
            _world("Where on the path is it worst? (worst run at each point; red = at the 5 mm tolerance)", ["/heat_worst"]),
        ),
        column_shares=[2, 3], name="All runs",
    )
    tabs = [overview]
    for entry in runs:
        run = _part(entry["name"])
        mine = lambda origin, run=run: [f"{origin}/{run}", f"{origin}/tolerance"]
        video = f"/video/{run}" if entry["name"] in videos else "/video/overlay"
        tabs.append(rrb.Horizontal(
            rrb.Vertical(
                _world(f"{_run_label(entry)} vs target", ["/world/target/**", f"/world/{run}/**", f"/heat/{run}"]),
                rrb.Spatial2DView(origin=video, name="Camera"),
                row_shares=[3, 2],
            ),
            rrb.Vertical(
                rrb.Horizontal(
                    rrb.TextDocumentView(origin=f"/notes/{run}", name="This run"),
                    _ts("/error/tool/position_mm", "Tool position error [mm]", contents=mine("/error/tool/position_mm")),
                    column_shares=[2, 3],
                ),
                _joint_error_grid(payload, mine),
                row_shares=[2, 3],
            ),
            column_shares=[2, 3], name=_run_label(entry),
        ))
    return rrb.Blueprint(rrb.Tabs(*tabs, active_tab=active), *_chrome())


def v3_tab_names(payload: dict) -> list[str]:
    return ["All runs", *[_run_label(entry) for entry in _runs(payload)]]


def v4_inspector(payload: dict, videos: dict, active: int | None = None) -> Any:
    """A signal inspector (Simulink Data Inspector / PlotJuggler): one tab per joint, stacked on one clock."""

    tabs = []
    for joint in _joints(payload):
        tabs.append(rrb.Vertical(
            _ts(f"/deg/position/{joint}", "position [°]", legend=True),
            _ts(f"/deg/error/{joint}", "error, target − run [°] — grey band = tolerance"),
            _ts(f"/deg/velocity/{joint}", "velocity [°/s]"),
            _ts(f"/torque/{joint}", "torque [N·m]"),
            name=_short(joint),
        ))
    tabs.append(rrb.Vertical(
        _ts("/error/tool/position_mm", "position error [mm] — grey band = tolerance", legend=True),
        _ts("/error/tool/rotation_deg", "rotation error [°]"),
        _ts("/error/tool/contour_mm", "contour error [mm]"),
        _ts("/error/tool/lag_time_ms", "lag time [ms]"),
        name="Tool (TCP)",
    ))
    side = rrb.Vertical(
        _world("3D"),
        rrb.Spatial2DView(origin="/video/overlay", name="Camera overlay"),
        rrb.TextLogView(origin="/events", name="Events"),
        row_shares=[3, 2, 1],
    )
    return rrb.Blueprint(rrb.Horizontal(rrb.Tabs(*tabs, active_tab=active), side, column_shares=[3, 2]), *_chrome())


def v4_tab_names(payload: dict) -> list[str]:
    return [*[_short(j) for j in _joints(payload)], "Tool (TCP)"]


def v5_replay(payload: dict, videos: dict, active: int | None = None) -> Any:
    """Video first, no tabs: the overlay big, the error-coloured path beside it, two strips that scroll with the playhead."""

    top = rrb.Horizontal(
        rrb.Spatial2DView(origin="/video/overlay", name="Camera overlay: real + sim + target"),
        _world("Robots + path coloured by the worst run's error", ["/world/**", "/heat_worst"]),
        column_shares=[3, 2],
    )
    strips = rrb.Horizontal(
        _ts("/error/tool/position_mm", "Tool error [mm], last 1.5 s", legend=True, time_ranges=TRAILING),
        _ts("/worst/joint_deg", "Worst joint error [°], last 1.5 s", time_ranges=TRAILING),
        rrb.TextLogView(origin="/events", name="Events"),
        column_shares=[2, 2, 1],
    )
    return rrb.Blueprint(rrb.Vertical(top, strips, row_shares=[3, 1]), *_chrome())


VARIANTS: dict[str, dict[str, Any]] = {
    "v1-evo-tabs": {"fn": v1_evo, "tabs": lambda p: V1_TABS},
    "v2-stage-questions": {"fn": v2_stage, "tabs": lambda p: V2_TABS},
    "v3-run-tabs": {"fn": v3_runs, "tabs": v3_tab_names},
    "v4-signal-inspector": {"fn": v4_inspector, "tabs": v4_tab_names},
    "v5-replay": {"fn": v5_replay, "tabs": lambda p: ["(no tabs)"]},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--blueprints-only", action="store_true",
                        help="rewrite only the per-tab .rbl files from the cached payload (fast layout iteration)")
    args = parser.parse_args()
    out = args.out.resolve()
    work = out / "fixture"
    work.mkdir(parents=True, exist_ok=True)
    cache = work / "payload.pkl"
    if args.blueprints_only:
        payload, videos = pickle.loads(cache.read_bytes())
        comparison = extras = None
    else:
        comparison = build_fixture(work)
        overlay = composite_overlay(work, work / "overlay_real1_sim_target.mp4")
        payload = analyze_comparison(comparison)
        _colorize(payload)
        extras = make_extras(comparison, overlay)
        videos = _resolvable_videos(payload, work)
        cache.write_bytes(pickle.dumps((payload, videos)))
    manifest = {}
    _frame(payload)
    for slug, spec in VARIANTS.items():
        app = f"traj_compare-{slug}"
        rrd = out / f"{slug}.rrd"
        if comparison is not None:
            write_rrd(comparison, rrd, payload=payload, video_root=work,
                      blueprint=spec["fn"], application_id=app, extra=extras)
        tabs = spec["tabs"](payload)
        # one blueprint file per tab, so a screenshot can open the viewer on that tab
        shots = []
        for index, tab in enumerate(tabs):
            rbl = out / "blueprints" / f"{slug}--{index}.rbl"
            rbl.parent.mkdir(exist_ok=True)
            SHOT_MODE["paused"] = True
            spec["fn"](payload, videos, active=index if len(tabs) > 1 else None).save(app, rbl)
            SHOT_MODE["paused"] = False
            shots.append({"tab": tab, "rbl": str(rbl.relative_to(out))})
        manifest[slug] = {"rrd": rrd.name, "application_id": app, "tabs": shots, "bytes": rrd.stat().st_size}
        print(f"{slug}: {rrd} ({rrd.stat().st_size / 1e6:.1f} MB), {len(tabs)} tab(s)")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
