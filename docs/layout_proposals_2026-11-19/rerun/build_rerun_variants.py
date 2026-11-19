"""Five Rerun RUN-view layouts for one target and its repeats — babble round C, 2026-11-19. SIMULATED fixture.

Every variant writes the SAME recording (target ``full-circle-slow``: sim + 14 real repeats, 8 × ff v1 nominal and
6 × ff v2 calibrated) with a different embedded blueprint, under its own application id so all five can be open in
one stock Rerun 0.40.0 viewer side by side. Allocated directions (CRITERIA.md, Round C):

    q1-torque-tab-grid     Q1  `questions` + one tab: a joint × component grid, every run in each view
    q2-solo-run            Q2  one screen per run: 3D, the run's stacked FF + FB breakdown over its group's band
    q3-distribution-first  Q3  percentile fans for error / feedback / commanded; runs hidden, the worst run drawn over
    q4-config-group-tabs   Q4  one tab per config group (sim · ff v1 · ff v2) + a "v1 vs v2" tab of the two bands
    q5-oscilloscope        Q5  one vertical stack on one clock: 3D, error, commanded / FF / FB, applied + current

Entities beyond what traj_compare HEAD (273ad59) writes — logged here through ``write_rrd(extra=...)`` because that
snapshot has no torque fields. The /torque and /stats/fb_share paths are CONTRACT.md's, so the production export
landing in parallel and these layouts line up:

    /torque/<joint>/target                                   target τ (inverse dynamics, planning model), grey
    /torque/<joint>/<run>/{commanded,feedforward,feedback,applied}   N·m; commanded = run colour, FF #3b82f6,
                                                             FB #f97316, applied = run colour thin
    /stats/fb_share/<joint>                                  bar per run, % (bar n = Real #n, bar 0 = sim)
    /stats/fb_share_by_group/<joint>/<group>                 the same bars split by config group, group colour
    /band/<signal>/<joint>/<group>/range                     min–max fan (Measurements: centre ± half-width)
    /band/<signal>/<joint>/<group>/iqr                       p25–p75 fan
    /band/<signal>/<joint>/<group>/median                    median line
                                                             signal ∈ error [°], commanded, feedback, applied [N·m];
                                                             group ∈ ff-v1, ff-v2
    /stack/<joint>/<run>/{ff_area,fb_area}                   stacked areas: 0 → FF (blue), FF → FF + FB (orange)
    /current/<joint>/<run>                                   motor current [A]
    /budget/{all,sim,ff-v1,ff-v2}, /runcard/<run>, /summary/{distribution,v1_vs_v2}   markdown

WHY Measurements for every band: Rerun 0.40 has no fill-between; Measurements shades value ± one standard deviation,
so centre = (lo + hi) / 2 and variance = ((hi − lo) / 2)² draw exactly [lo, hi] (robot_msgs.viz.rerun.band does the
same for tolerance bands). Width 0 hides its centre line, which is not a statistic.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19/rerun
    PYTHONPATH=<traj_compare HEAD src> traj_compare/.venv/bin/python build_rerun_variants.py [--out DIR]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import warnings
from pathlib import Path
from typing import Any, Callable

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # fixture.py, one level up

import fixture  # noqa: E402
from traj_compare.analysis import analyze_comparison  # noqa: E402
from traj_compare.report import _colorize  # noqa: E402
from traj_compare.rerun_export import TIMELINE, _array, _hex_to_rgb, _layout_questions, _part, write_rrd  # noqa: E402

DEG = 180.0 / math.pi
OUT_DEFAULT = Path("/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19/rerun")
TARGET = "full-circle-slow"
COMPONENTS = ("commanded", "feedforward", "feedback", "applied")
FIXTURE_KEY = {"commanded": "tau_cmd", "feedforward": "tau_ff", "feedback": "tau_fb", "applied": "tau"}
FF_RGB, FB_RGB, TARGET_RGB = [59, 130, 246], [249, 115, 22], [138, 137, 131]  # CONTRACT.md component colours
# Config-group colours (not in the contract; picked here). WHY brown / blue: the 8-hue run palette already holds
# violet, teal, orange, green, magenta, mustard, slate and blue, and no ff v1 run is brown, no ff v2 run is blue, so a
# run never sits on a fan of its own colour (the first pass used violet for v1 and drew Real #03, violet, on it).
GROUPS = {
    "sim": {"title": "Sim · ideal plant", "short": "sim", "rgb": [73, 80, 87]},
    "ff-v1": {"title": "ff v1 nominal", "short": "ff v1", "rgb": [154, 91, 46]},
    "ff-v2": {"title": "ff v2 calibrated", "short": "ff v2", "rgb": [25, 113, 194]},
}
GREY_FAN = [[120, 120, 120, 50], [120, 120, 120, 105], [110, 110, 110, 255]]  # Q2: the run's own group, neutral
BAND_GROUPS = ("ff-v1", "ff-v2")
BAND_SIGNALS = {"error": "°", "commanded": "N·m", "feedback": "N·m", "applied": "N·m"}
FB_BARS = "bar n = Real #n · bar 0 = sim"


# ── the derived data (computed once, logged into every variant) ─────────────────────────────────────────────────


@dataclasses.dataclass
class Run:
    name: str  # payload name: sim, real-01, ...
    part: str  # entity-path part
    title: str
    rgb: list[int]
    group: str  # sim | ff-v1 | ff-v2
    number: int  # 0 = sim, n = Real #n
    torque: dict[str, np.ndarray]  # component -> (joints, samples) on the plot clock
    error_deg: np.ndarray  # (joints, samples)
    current: np.ndarray
    budget: dict[str, dict[str, float]]
    tool_max_mm: float = 0.0
    tool_rms_mm: float = 0.0


@dataclasses.dataclass
class Derived:
    payload: dict
    joints: list[str]  # entity parts
    joint_names: list[str]
    plot_t: np.ndarray
    target_tau: np.ndarray  # (joints, samples)
    runs: list[Run]
    bands: dict[tuple[str, str, str], dict[str, np.ndarray]]
    worst: Run
    t_worst: float

    def group(self, group: str) -> list[Run]:
        return [run for run in self.runs if run.group == group]

    def by_part(self, part: str) -> Run:
        return next(run for run in self.runs if run.part == part)


def _on_clock(plot_t: np.ndarray, t: np.ndarray, columns: list[list[float]]) -> np.ndarray:
    """A run's own samples onto the shared plot clock, NaN outside its span (never extrapolated)."""

    return np.array([np.interp(plot_t, t, np.asarray(col, dtype=float), left=np.nan, right=np.nan) for col in columns])


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.nanmean(np.asarray(values, dtype=float) ** 2)))


def _budget(record: dict, target: dict, joint: int) -> dict[str, float]:
    """CONTRACT.md's torque budget for one run and joint, on the run's own samples."""

    t = np.asarray(record["t"])
    cmd, ff, fb, applied = (np.asarray(record[key][joint]) for key in ("tau_cmd", "tau_ff", "tau_fb", "tau"))
    target_tau = np.interp(t, np.asarray(target["t"]), np.asarray(target["tau"][joint]), left=np.nan, right=np.nan)
    return {
        "fb_share": float(np.sum(np.abs(fb)) / (np.sum(np.abs(ff)) + np.sum(np.abs(fb)))),
        "cmd_rms": _rms(cmd), "ff_rms": _rms(ff), "fb_rms": _rms(fb), "applied_rms": _rms(applied),
        "cmd_peak": float(np.max(np.abs(cmd))), "target_minus_cmd_rms": _rms(target_tau - cmd),
        "cmd_minus_applied_rms": _rms(cmd - applied),
    }  # fmt: skip


def derive(comparison, payload: dict, data: dict) -> Derived:
    t0 = float(comparison.target.t[0])
    plot_t = _array(payload["plot_t"]) - t0
    target = next(record for record in data["targets"] if record["name"] == comparison.name)
    records = {record["name"].split("/")[1]: record for record in data["runs"] if record["target"] == comparison.name}
    joint_names = list(payload["joint_names"])
    runs = []
    for entry in payload["situations"]:
        if not entry["has_data"] or "err_q" not in entry["plot"]:
            continue
        record = records[entry["name"]]
        group = "sim" if record["kind"] == "sim" else ("ff-v1" if record["tags"]["ff_model"].startswith("v1") else "ff-v2")
        metrics = entry["error_metrics"]
        runs.append(Run(
            name=entry["name"], part=_part(entry["name"]), title=entry["title"], rgb=_hex_to_rgb(entry["color"]),
            group=group, number=0 if group == "sim" else int(entry["name"].split("-")[1]),
            torque={component: _on_clock(plot_t, np.asarray(record["t"]), record[FIXTURE_KEY[component]]) for component in COMPONENTS},
            error_deg=np.array([_array(row) for row in entry["plot"]["err_q"]]) * DEG,
            current=_on_clock(plot_t, np.asarray(record["t"]), record["current"]),
            budget={joint: _budget(record, target, index) for index, joint in enumerate(joint_names)},
            tool_max_mm=metrics["position"]["max_abs"] * 1000.0, tool_rms_mm=metrics["position"]["rms"] * 1000.0,
        ))  # fmt: skip
    target_tau = _on_clock(plot_t, np.asarray(target["t"]), target["tau"])
    bands = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns at a run's clock edges
        for group in BAND_GROUPS:
            members = [run for run in runs if run.group == group]
            for signal in BAND_SIGNALS:
                stack = np.array([run.error_deg if signal == "error" else run.torque[signal] for run in members])
                quantiles = np.nanpercentile(stack, [0, 25, 50, 75, 100], axis=0)  # (5, joints, samples)
                for index, joint in enumerate(joint_names):
                    bands[(signal, _part(joint), group)] = dict(zip(("min", "p25", "median", "p75", "max"), quantiles[:, index]))
    # the worst run is the scorecard's: largest tool (L2 tip) error, as traj_compare's _scorecard sorts
    worst = max((run for run in runs if run.group != "sim"), key=lambda run: run.tool_max_mm)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        joint_peak = np.nanargmax(np.nanmax(np.abs(worst.error_deg), axis=0))
    return Derived(payload=payload, joints=[_part(j) for j in joint_names], joint_names=joint_names, plot_t=plot_t,
                   target_tau=target_tau, runs=runs, bands=bands, worst=worst, t_worst=float(plot_t[joint_peak]))  # fmt: skip


# ── markdown pages ──────────────────────────────────────────────────────────────────────────────────────────────


def _pct(value: float) -> str:
    return f"{100.0 * value:.0f} %"


def _budget_table(derived: Derived, runs: list[Run]) -> list[str]:
    lines = ["| Run | Joint | FB share | cmd RMS | FF RMS | FB RMS | target − cmd RMS | cmd − applied RMS | peak cmd |",
             "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for run in runs:
        for joint in derived.joint_names:
            b = run.budget[joint]
            lines.append(f"| {run.title} | {joint} | **{_pct(b['fb_share'])}** | {b['cmd_rms']:.2f} | {b['ff_rms']:.2f} | "
                         f"{b['fb_rms']:.2f} | {b['target_minus_cmd_rms']:.2f} | {b['cmd_minus_applied_rms']:.3f} | {b['cmd_peak']:.2f} |")  # fmt: skip
    return lines


def _share_summary(derived: Derived, group: str, joint: str) -> str:
    shares = np.array([run.budget[joint]["fb_share"] for run in derived.group(group)])
    return f"{_pct(np.median(shares))} ({_pct(shares.min())}–{_pct(shares.max())})"


def _err_rms(run: Run) -> float:
    return _rms(np.nanmax(np.abs(run.error_deg), axis=0))


def budget_page(derived: Derived, group: str | None) -> str:
    runs = derived.runs if group is None else derived.group(group)
    title = "every run" if group is None else f"{GROUPS[group]['title']} · {len(runs)} run{'s' * (len(runs) > 1)}"
    lines = [f"# Torque budget — {title}", "", "SIMULATED fixture · N·m · FB share = Σ|FB| / (Σ|FF| + Σ|FB|)", ""]
    if group is None:
        lines += ["Grid above: rows = joints; columns = commanded (grey = target) · feedforward · feedback · applied; "
                  "every run in its run colour in every view.", ""]
    if group in BAND_GROUPS:
        lines += ["- FB share median (range): " + " · ".join(f"{j} {_share_summary(derived, group, j)}" for j in derived.joint_names), ""]
    return "\n".join(lines + _budget_table(derived, runs)) + "\n"


def run_card(derived: Derived, run: Run) -> str:
    peers = derived.group(run.group)
    rank = sorted(peers, key=lambda r: -r.tool_max_mm).index(run) + 1
    lines = [f"# {run.title}", "", derived.payload["title"], "",
             f"**{GROUPS[run.group]['title']}** · tool error max **{run.tool_max_mm:.1f} mm**, RMS {run.tool_rms_mm:.1f} mm "
             f"· rank {rank} of {len(peers)} in its group (1 = worst)", "",
             "| Joint | FB share | group median | FB RMS | target − cmd RMS | cmd − applied RMS |", "|---|---|---|---|---|---|"]  # fmt: skip
    for joint in derived.joint_names:
        b = run.budget[joint]
        median = _share_summary(derived, run.group, joint) if run.group in BAND_GROUPS else "—"
        lines.append(f"| {joint} | **{_pct(b['fb_share'])}** | {median} | {b['fb_rms']:.2f} N·m | "
                     f"{b['target_minus_cmd_rms']:.2f} N·m | {b['cmd_minus_applied_rms']:.3f} N·m |")
    lines += ["", "**Key:** grey line = target · blue area = feedforward · orange area = feedback (together: commanded) · "
              "thick run colour = commanded · thin = applied · grey fans = this run's config group (min–max, p25–p75, median).",
              "", "Other runs: open `blueprints/q2-solo-run--<run>.rbl` with this .rrd."]
    return "\n".join(lines) + "\n"


def distribution_page(derived: Derived) -> str:
    worst = derived.worst
    lines = [f"# {derived.payload['title']}", "",
             f"**{len(derived.runs) - 1} real repeats** (8 ff v1 · 6 ff v2) + sim. Fans: light = min–max, dark = p25–p75, "
             "line = median, per config group. Individual runs are in every plot but hidden: switch one on in the "
             "Blueprint panel (eye icon).", "",
             f"**Worst run: {worst.title}** — tool error peaks at {worst.tool_max_mm:.1f} mm (drawn bold over the fans; "
             f"3D beside). Worst moment t = {derived.t_worst:.2f} s.", "",
             "| FB share | ff v1 median (range) | ff v2 median (range) |", "|---|---|---|"]  # fmt: skip
    for joint in derived.joint_names:
        lines.append(f"| {joint} | {_share_summary(derived, 'ff-v1', joint)} | {_share_summary(derived, 'ff-v2', joint)} |")
    return "\n".join(lines) + "\n"


def compare_page(derived: Derived) -> str:
    lines = ["# ff v1 nominal vs ff v2 calibrated", "", derived.payload["title"], "",
             "| | ff v1 · 8 runs | ff v2 · 6 runs |", "|---|---|---|"]  # fmt: skip
    for joint in derived.joint_names:
        lines.append(f"| FB share {joint} | {_share_summary(derived, 'ff-v1', joint)} | {_share_summary(derived, 'ff-v2', joint)} |")
    for group_label, key in (("tool error max (median)", "tool_max_mm"),):
        values = {g: np.median([getattr(run, key) for run in derived.group(g)]) for g in BAND_GROUPS}
        lines.append(f"| {group_label} | {values['ff-v1']:.1f} mm | {values['ff-v2']:.1f} mm |")
    for joint_index, joint in enumerate(derived.joint_names):
        values = {g: np.median([_rms(run.error_deg[joint_index]) for run in derived.group(g)]) for g in BAND_GROUPS}
        lines.append(f"| {joint} error RMS (median) | {values['ff-v1']:.2f}° | {values['ff-v2']:.2f}° |")
    lines += ["", "Brown = ff v1, blue = ff v2. Fans: light = min–max, dark = p25–p75, line = median."]
    return "\n".join(lines) + "\n"


# ── logging (write_rrd's extra hook) ────────────────────────────────────────────────────────────────────────────


def make_extras(derived: Derived) -> Callable[[Any, dict, float], None]:
    def extras(recording, payload: dict, t0: float) -> None:
        clock = [rr.TimeColumn(TIMELINE, duration=derived.plot_t)]

        def series(entity: str, values: np.ndarray, rgb, label: str, width: float) -> None:
            recording.log(entity, rr.SeriesLines(colors=[rgb], names=[label], widths=[width]), static=True)
            recording.send_columns(entity, indexes=clock, columns=rr.Scalars.columns(scalars=values))

        def fan(entity: str, low: np.ndarray, high: np.ndarray, rgba, label: str) -> None:
            recording.log(entity, rr.Measurements.from_fields(colors=[rgba], names=[label], widths=[0.0]), static=True)
            recording.send_columns(entity, indexes=clock,
                                   columns=rr.Measurements.columns(values=0.5 * (low + high), variances=(0.5 * (high - low)) ** 2))

        for index, joint in enumerate(derived.joints):
            series(f"/torque/{joint}/target", derived.target_tau[index], TARGET_RGB, "target", 2.0)
            for run in derived.runs:
                base = f"/torque/{joint}/{run.part}"
                series(f"{base}/commanded", run.torque["commanded"][index], run.rgb, f"{run.title} · commanded", 2.0)
                series(f"{base}/feedforward", run.torque["feedforward"][index], FF_RGB, f"{run.title} · feedforward", 1.4)
                series(f"{base}/feedback", run.torque["feedback"][index], FB_RGB, f"{run.title} · feedback", 1.4)
                series(f"{base}/applied", run.torque["applied"][index], run.rgb, f"{run.title} · applied", 0.8)
                series(f"/current/{joint}/{run.part}", run.current[index], run.rgb, run.title, 1.0)
                ff, fb = run.torque["feedforward"][index], run.torque["feedback"][index]
                fan(f"/stack/{joint}/{run.part}/ff_area", np.zeros_like(ff), ff, [*FF_RGB, 70], "feedforward part (area)")
                fan(f"/stack/{joint}/{run.part}/fb_area", ff, ff + fb, [*FB_RGB, 150], "feedback part (area)")
            name = derived.joint_names[index]
            numbers = np.array([run.number for run in derived.runs], dtype=float)
            shares = np.array([100.0 * run.budget[name]["fb_share"] for run in derived.runs])
            recording.log(f"/stats/fb_share/{joint}", rr.BarChart(shares, abscissa=numbers, color=FB_RGB), static=True)
            for group in GROUPS:
                pick = np.array([run.group == group for run in derived.runs])
                recording.log(f"/stats/fb_share_by_group/{joint}/{group}",
                              rr.BarChart(shares[pick], abscissa=numbers[pick], color=GROUPS[group]["rgb"]), static=True)
            for group in BAND_GROUPS:
                rgb, label = GROUPS[group]["rgb"], GROUPS[group]["short"]
                for signal in BAND_SIGNALS:
                    q = derived.bands[(signal, joint, group)]
                    base = f"/band/{signal}/{joint}/{group}"
                    fan(f"{base}/range", q["min"], q["max"], [*rgb, 55], f"{label} min–max")
                    fan(f"{base}/iqr", q["p25"], q["p75"], [*rgb, 120], f"{label} p25–p75")
                    series(f"{base}/median", q["median"], rgb, f"{label} median", 2.0)
        markdown = lambda entity, text: recording.log(entity, rr.TextDocument(text, media_type=rr.MediaType.MARKDOWN), static=True)  # noqa: E731
        markdown("/budget/all", budget_page(derived, None))
        for group in GROUPS:
            markdown(f"/budget/{group}", budget_page(derived, group))
        for run in derived.runs:
            markdown(f"/runcard/{run.part}", run_card(derived, run))
        markdown("/summary/distribution", distribution_page(derived))
        markdown("/summary/v1_vs_v2", compare_page(derived))

    return extras


# ── blueprint helpers ───────────────────────────────────────────────────────────────────────────────────────────

SHOT = {"paused": False, "zoom": None}  # screenshot blueprints open paused (the harness types the playhead)
EYE: dict[str, Any] = {}


def _frame(derived: Derived) -> None:
    """The planar arm moves in the x–y plane with gravity along −y: look down z, y up, so it reads like a drawing."""

    reference = next(entry for entry in derived.payload["situations"] if entry["three"] is not None)
    path = np.asarray(reference["three"]["p"], dtype=float)
    EYE["centre"] = 0.5 * (path.min(axis=0) + path.max(axis=0))


def panels(time_panel: str = "collapsed") -> list[Any]:
    extra = {"play_state": "paused"} if SHOT["paused"] else {}
    return [rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"), rrb.TimePanel(state=time_panel, **extra)]


def ts(name: str, contents: list[str], legend: Any = False, overrides: dict | None = None, **kwargs: Any) -> Any:
    """A time-series view over explicit entities; its x zoom is linked to every other plot."""

    axis = rrb.TimeAxis(link="LinkToGlobal")
    if SHOT["zoom"] is not None:
        # WHY Independent + a cursor window: with LinkToGlobal the viewer ignored view_range (first shot came out
        # unzoomed); a scope sweep is a window around the trigger, so the zoomed state draws only cursor ± half-width
        half = 0.5 * (SHOT["zoom"][1] - SHOT["zoom"][0])
        centre = 0.5 * (SHOT["zoom"][1] + SHOT["zoom"][0])
        axis = rrb.TimeAxis(link="Independent", view_range=rrb.TimeRange(start=rrb.TimeRangeBoundary.absolute(seconds=centre - half),
                                                                         end=rrb.TimeRangeBoundary.absolute(seconds=centre + half)))
        kwargs.setdefault("time_ranges", [rrb.VisibleTimeRange(TIMELINE, start=rrb.TimeRangeBoundary.cursor_relative(seconds=-half),
                                                               end=rrb.TimeRangeBoundary.cursor_relative(seconds=half))])
    return rrb.TimeSeriesView(origin="/", contents=contents, name=name, overrides=overrides or None,
                              plot_legend=rrb.PlotLegend(legend, visible=True) if legend else rrb.PlotLegend(visible=False),
                              axis_x=axis, **kwargs)  # fmt: skip


def world(name: str, runs: list[Run] | None, distance: float = 1.75) -> Any:
    """3D: the target robot and ``runs`` (None = every run); ``distance`` (m) fits the arm to the view's height."""

    contents = ["/world/**"] if runs is None else ["/world/target/**", *[f"/world/{run.part}/**" for run in runs]]
    centre = EYE["centre"]
    eye = rrb.EyeControls3D(kind="Orbital", look_target=centre, eye_up=[0, 1, 0], position=centre + np.array([0.0, -0.1 * distance, distance]))
    return rrb.Spatial3DView(origin="/", contents=contents, name=name, line_grid=rrb.LineGrid3D(visible=False), eye_controls=eye)


def bars(origin: str, name: str) -> Any:
    return rrb.BarChartView(origin=origin, name=name, plot_legend=rrb.PlotLegend(visible=False))


def short(joint: str) -> str:
    return joint.replace("_joint", "").replace("_", " ")


def band_paths(signal: str, joint: str, groups=BAND_GROUPS, median: bool = True) -> list[str]:
    parts = ("range", "iqr", "median") if median else ("range", "iqr")
    return [f"/band/{signal}/{joint}/{group}/{part}" for group in groups for part in parts]


def run_path(signal: str, joint: str, run: Run) -> str:
    return f"/error/positions/{joint}/{run.part}" if signal == "error" else f"/torque/{joint}/{run.part}/{signal}"


def look(rgb, alpha: int = 255, width: float = 1.4) -> Any:
    return rr.SeriesLines.from_fields(colors=[[*rgb[:3], alpha]], widths=[width])


# ── Q1 · torque tab grid ────────────────────────────────────────────────────────────────────────────────────────

Q1_TAB = "Feedforward or feedback?"


def q1_torque_tab(derived: Derived) -> Any:
    views = []
    for joint in derived.joints:
        for component in ("commanded", "feedforward", "feedback", "applied"):
            paths = [f"/torque/{joint}/{run.part}/{component}" for run in derived.runs]
            with_target = component in ("commanded", "applied")
            # WHY run colours in the FF / FB / applied columns: the view title names the component, so colour can keep
            # naming the run — the same run is the same colour in all eight views (TensorBoard's rule)
            overrides = {path: look(run.rgb, 255, 1.2) for path, run in zip(paths, derived.runs, strict=True)} if component != "commanded" else None
            label = f"{short(joint)} {dict(commanded='cmd', feedforward='FF', feedback='FB', applied='applied')[component]} [N·m]"
            views.append(ts(label, ([f"/torque/{joint}/target"] if with_target else []) + paths, overrides=overrides))
    grid = rrb.Grid(*views, grid_columns=4)
    bottom = rrb.Horizontal(
        *[bars(f"/stats/fb_share/{joint}", f"{short(joint)} FB share per run [%] — {FB_BARS}") for joint in derived.joints],
        rrb.TextDocumentView(origin="/budget/all", name="Torque budget (every run)"),
        column_shares=[1, 1, 2],
    )
    return rrb.Vertical(grid, bottom, row_shares=[3, 1.4], name=Q1_TAB)


def q1(derived: Derived, active: str | None = Q1_TAB) -> Callable:
    def build(payload: dict, videos: dict) -> Any:
        blueprint = _layout_questions(payload, videos, [], tab=None, checks=[])
        root = blueprint.root_container  # Horizontal(stage, question tabs) — the shipped `questions` layout
        tabs = list(root.contents[1].contents)
        tabs.insert(1, q1_torque_tab(derived))
        names = [tab.name for tab in tabs]
        questions = rrb.Tabs(*tabs, active_tab=names.index(active) if active else None)
        # the stage's 3D: same entities as `questions`, but this fixture's arm is planar in x–y, so look down z
        stage = rrb.Vertical(world("Stage — SIMULATED fixture, every run", None, distance=2.6))
        # WHY narrower than `questions`' 2:3 stage: the grid has four columns and needs the width for its titles
        return rrb.Blueprint(rrb.Horizontal(stage, questions, column_shares=[1, 3]), *panels())

    return build


Q1_SHOTS = [("hero", Q1_TAB), ("is-it-good", "Is it good?")]


# ── Q2 · solo run dashboard ─────────────────────────────────────────────────────────────────────────────────────


def q2(derived: Derived, run: Run | None = None) -> Callable:
    run = run or derived.worst
    group = GROUPS[run.group]
    has_band = run.group in BAND_GROUPS
    peers = [run.group] if has_band else []

    def grey_fans(signal: str, joint: str) -> dict:
        """The run's own group, recoloured neutral in this view only (a blueprint override, not a second entity)."""

        return {f"/band/{signal}/{joint}/{run.group}/{part}": (rr.Measurements.from_fields(colors=[rgba]) if part != "median" else look(rgba, 255, 1.6))
                for part, rgba in zip(("range", "iqr", "median"), GREY_FAN, strict=True)} if has_band else {}

    def build(payload: dict, videos: dict) -> Any:
        left = rrb.Vertical(
            world(f"SIMULATED · {run.title} (forearm in run colour) vs target (grey)", [run], distance=1.25),
            rrb.TextDocumentView(origin=f"/runcard/{run.part}", name=f"{run.title} — numbers"),
            row_shares=[3, 2],
        )
        torque, feedback, error = [], [], []
        for index, joint in enumerate(derived.joints):
            base = f"/torque/{joint}/{run.part}"
            torque.append(ts(
                f"{short(joint)} τ [N·m] · commanded = FF + FB",
                [*band_paths("commanded", joint, peers, median=False), f"/stack/{joint}/{run.part}/ff_area",
                 f"/stack/{joint}/{run.part}/fb_area", f"/torque/{joint}/target", f"{base}/feedforward", f"{base}/commanded",
                 f"{base}/applied"],
                legend=rrb.Corner2D.LeftBottom if index == 0 else False, overrides=grey_fans("commanded", joint),
            ))  # fmt: skip
            feedback.append(ts(f"{short(joint)} feedback [N·m] vs {group['short']} fan", [*band_paths("feedback", joint, peers), f"{base}/feedback"],
                               overrides=grey_fans("feedback", joint)))
            error.append(ts(f"{short(joint)} error, target − run [°] vs {group['short']} fan",
                            [*band_paths("error", joint, peers), f"/error/positions/{joint}/{run.part}"],
                            overrides={**grey_fans("error", joint), f"/error/positions/{joint}/{run.part}": look(run.rgb, 255, 2.2)}))
        right = rrb.Vertical(rrb.Horizontal(*torque), rrb.Horizontal(*feedback), rrb.Horizontal(*error), row_shares=[3, 1.5, 1.5])
        return rrb.Blueprint(rrb.Horizontal(left, right, column_shares=[2, 3]), *panels())

    return build


# ── Q3 · distribution first ─────────────────────────────────────────────────────────────────────────────────────

Q3_SIGNALS = (("error", "error, target − run [°]"), ("feedback", "feedback τ [N·m]"), ("commanded", "commanded τ [N·m] — grey = target"))


def q3(derived: Derived, reveal: Run | None = None) -> Callable:
    worst = derived.worst

    def build(payload: dict, videos: dict) -> Any:
        views = []
        for signal, label in Q3_SIGNALS:
            for joint in derived.joints:
                lines = {run.part: run_path(signal, joint, run) for run in derived.runs}
                # WHY hidden, not excluded: every run stays in the view (and the Blueprint panel's tree), one eye-click
                # away — lines on demand over a distribution by default
                overrides: dict[str, Any] = {path: rrb.EntityBehavior(visible=False) for part, path in lines.items()
                                             if part not in (worst.part, getattr(reveal, "part", None))}
                overrides[lines[worst.part]] = look(worst.rgb, 255, 2.4)
                if reveal is not None:
                    overrides[lines[reveal.part]] = look(reveal.rgb, 255, 2.0)
                target = [f"/torque/{joint}/target"] if signal == "commanded" else []
                views.append(ts(f"{short(joint)} · {label}", [*band_paths(signal, joint), *target, *lines.values()],
                                legend=rrb.Corner2D.RightTop if signal == "error" and joint == derived.joints[0] else False,
                                overrides=overrides))
        grid = rrb.Grid(*views, grid_columns=2)
        right = rrb.Vertical(
            world(f"SIMULATED · worst run {worst.title} vs target", [worst], distance=1.2),
            rrb.TextDocumentView(origin="/summary/distribution", name="Distribution — 14 repeats"),
            rrb.Horizontal(*[bars(f"/stats/fb_share_by_group/{joint}", f"{short(joint)} FB share [%] — brown v1 · blue v2")
                             for joint in derived.joints]),
            row_shares=[2.4, 2.6, 1.4],
        )
        return rrb.Blueprint(rrb.Horizontal(grid, right, column_shares=[3, 2]), *panels())

    return build


# ── Q4 · config-group tabs ──────────────────────────────────────────────────────────────────────────────────────


def _group_tab(derived: Derived, group: str) -> Any:
    runs = derived.group(group)
    meta = GROUPS[group]
    title = f"{meta['title']} · {len(runs)} run{'s' * (len(runs) > 1)}"
    left = rrb.Vertical(world(f"SIMULATED · {title} vs target", runs, distance=1.25),
                        rrb.TextDocumentView(origin=f"/budget/{group}", name=f"Torque budget — {meta['short']}"), row_shares=[3, 2])
    views = []
    for joint in derived.joints:
        commanded = [f"/torque/{joint}/{run.part}/commanded" for run in runs]
        feedforward = [f"/torque/{joint}/{run.part}/feedforward" for run in runs]
        views.append(ts(f"{short(joint)} · target (grey) · FF (blue) · commanded (run colours) [N·m]",
                        [f"/torque/{joint}/target", *feedforward, *commanded], legend=False))
    for joint in derived.joints:
        paths = [f"/torque/{joint}/{run.part}/feedback" for run in runs]
        views.append(ts(f"{short(joint)} · feedback per run [N·m]", paths, legend=rrb.Corner2D.RightTop if joint == derived.joints[0] else False,
                        overrides={path: look(run.rgb, 255, 1.4) for path, run in zip(paths, runs, strict=True)}))
    for joint in derived.joints:
        views.append(ts(f"{short(joint)} · error, target − run [°]", [f"/error/positions/{joint}/{run.part}" for run in runs]))
    return rrb.Horizontal(left, rrb.Grid(*views, grid_columns=2), column_shares=[2, 3], name=title)


def _compare_tab(derived: Derived) -> Any:
    views = []
    for signal, label in Q3_SIGNALS:
        for joint in derived.joints:
            target = [f"/torque/{joint}/target"] if signal == "commanded" else []
            views.append(ts(f"{short(joint)} · {label}", [*band_paths(signal, joint), *target],
                            legend=rrb.Corner2D.RightTop if signal == "error" and joint == derived.joints[0] else False))
    right = rrb.Vertical(rrb.TextDocumentView(origin="/summary/v1_vs_v2", name="v1 vs v2"),
                         *[bars(f"/stats/fb_share_by_group/{joint}", f"{short(joint)} FB share per run [%] — brown v1 · blue v2 · {FB_BARS}")
                           for joint in derived.joints], row_shares=[2, 1, 1])  # fmt: skip
    return rrb.Horizontal(rrb.Grid(*views, grid_columns=2), right, column_shares=[3, 2], name="v1 vs v2")


Q4_ORDER = ["sim", "ff-v1", "ff-v2", "compare"]


def q4(derived: Derived, active: str = "ff-v1") -> Callable:
    def build(payload: dict, videos: dict) -> Any:
        tabs = [_group_tab(derived, group) for group in GROUPS] + [_compare_tab(derived)]
        return rrb.Blueprint(rrb.Tabs(*tabs, active_tab=Q4_ORDER.index(active)), *panels())

    return build


# ── Q5 · oscilloscope stack ─────────────────────────────────────────────────────────────────────────────────────


def q5(derived: Derived) -> Callable:
    worst = derived.worst

    def persist(paths_runs: list[tuple[str, Run]], rgb_of: Callable[[Run], list[int]]) -> dict:
        """Scope persistence: every sweep faint, the worst run bold."""

        return {path: look(rgb_of(run), 255, 2.4) if run is worst else look(rgb_of(run), 55, 1.0) for path, run in paths_runs}

    def build(payload: dict, videos: dict) -> Any:
        top = rrb.Horizontal(
            world(f"SIMULATED · every run (worst: {worst.title}) — a video row goes here when the run has one", None, distance=1.1),
            *[bars(f"/stats/fb_share/{joint}", f"{short(joint)} FB share [%] — {FB_BARS}") for joint in derived.joints],
            column_shares=[2, 1, 1],
        )
        error, torque, applied = [], [], []
        for index, joint in enumerate(derived.joints):
            pairs = [(f"/error/positions/{joint}/{run.part}", run) for run in derived.runs]
            error.append(ts(f"CH1 {short(joint)} · error [°] — every run faint, {worst.title} bold", [p for p, _ in pairs],
                            overrides=persist(pairs, lambda run: run.rgb)))
            commanded = [(f"/torque/{joint}/{run.part}/commanded", run) for run in derived.runs]
            ff = [(f"/torque/{joint}/{run.part}/feedforward", run) for run in derived.runs]
            fb = [(f"/torque/{joint}/{run.part}/feedback", run) for run in derived.runs]
            overrides = {**persist(commanded, lambda run: run.rgb), **persist(ff, lambda run: FF_RGB), **persist(fb, lambda run: FB_RGB)}
            torque.append(ts(f"CH2 {short(joint)} · target (grey) · commanded (run colour) · FF (blue) · FB (orange) [N·m]",
                             [f"/torque/{joint}/target", *[p for p, _ in commanded + ff + fb]], overrides=overrides))
            ap = [(f"/torque/{joint}/{run.part}/applied", run) for run in derived.runs]
            cur = [(f"/current/{joint}/{run.part}", run) for run in derived.runs]
            applied.append(rrb.Horizontal(
                ts(f"CH3 {short(joint)} · applied [N·m]", [p for p, _ in ap], overrides=persist(ap, lambda run: run.rgb)),
                ts(f"CH4 {short(joint)} · current [A]", [p for p, _ in cur], overrides=persist(cur, lambda run: run.rgb)),
            ))
        stack = rrb.Vertical(top, rrb.Horizontal(*error), rrb.Horizontal(*torque), rrb.Horizontal(*applied), row_shares=[2.1, 1.6, 2.4, 1.6])
        return rrb.Blueprint(stack, *panels())

    return build


# ── build ───────────────────────────────────────────────────────────────────────────────────────────────────────

VARIANTS = {
    "q1-torque-tab-grid": "Q1 Torque tab grid",
    "q2-solo-run": "Q2 Solo run dashboard",
    "q3-distribution-first": "Q3 Distribution first",
    "q4-config-group-tabs": "Q4 Config-group tabs",
    "q5-oscilloscope": "Q5 Oscilloscope stack",
}


def blueprints(derived: Derived) -> dict[str, Callable]:
    return {"q1-torque-tab-grid": q1(derived), "q2-solo-run": q2(derived), "q3-distribution-first": q3(derived),
            "q4-config-group-tabs": q4(derived), "q5-oscilloscope": q5(derived)}  # fmt: skip


def shot_blueprints(derived: Derived) -> list[dict]:
    """(variant, shot name, blueprint builder, playhead) for the screenshot harness: the hero plus 1–2 more states."""

    best_v2 = min(derived.group("ff-v2"), key=lambda run: run.tool_max_mm)
    t = round(derived.t_worst, 2)
    zoom = (max(0.0, t - 0.8), t + 0.8)
    return [
        {"slug": "q1-torque-tab-grid", "shot": "hero", "fn": q1(derived, Q1_TAB), "at": t, "caption": "Feedforward or feedback? tab"},
        {"slug": "q1-torque-tab-grid", "shot": "is-it-good", "fn": q1(derived, "Is it good?"), "at": t, "caption": "Is it good? tab (shipped)"},
        {"slug": "q2-solo-run", "shot": "hero", "fn": q2(derived), "at": t, "caption": f"worst run {derived.worst.title}"},
        {"slug": "q2-solo-run", "shot": "best-v2", "fn": q2(derived, best_v2), "at": t, "caption": f"another run's .rbl: {best_v2.title}"},
        {"slug": "q3-distribution-first", "shot": "hero", "fn": q3(derived), "at": t, "caption": "fans + worst run"},
        {"slug": "q3-distribution-first", "shot": "reveal", "fn": q3(derived, best_v2), "at": t, "caption": f"{best_v2.title} switched on"},
        {"slug": "q4-config-group-tabs", "shot": "hero", "fn": q4(derived, "ff-v1"), "at": t, "caption": "ff v1 tab"},
        {"slug": "q4-config-group-tabs", "shot": "ff-v2", "fn": q4(derived, "ff-v2"), "at": t, "caption": "ff v2 tab"},
        {"slug": "q4-config-group-tabs", "shot": "compare", "fn": q4(derived, "compare"), "at": t, "caption": "v1 vs v2 tab"},
        {"slug": "q5-oscilloscope", "shot": "hero", "fn": q5(derived), "at": t, "caption": "the stack"},
        {"slug": "q5-oscilloscope", "shot": "zoom", "fn": q5(derived), "at": t, "zoom": zoom, "caption": f"zoomed to {zoom[0]:.1f}–{zoom[1]:.1f} s"},
    ]  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--blueprints-only", action="store_true", help="rewrite only the .rbl files (fast layout iteration)")
    args = parser.parse_args()
    out = args.out.resolve()
    (out / "blueprints").mkdir(parents=True, exist_ok=True)
    data = json.loads(fixture.OUT.read_text())
    comparison = next(c for c in fixture.comparisons(data) if c.name == args.target)
    label = f"SIMULATED · {comparison.title}"
    comparison = dataclasses.replace(comparison, title=label, tab_title=label, group_title=label)
    payload = analyze_comparison(comparison)
    _colorize(payload)
    derived = derive(comparison, payload, data)
    _frame(derived)
    extras = make_extras(derived)
    manifest: dict[str, Any] = {"target": args.target, "worst": derived.worst.title, "t_worst": derived.t_worst, "variants": {}, "shots": []}
    for slug, build in blueprints(derived).items():
        app = f"traj_compare-run-{slug}"
        rrd = out / f"{slug}.rrd"
        if not args.blueprints_only:
            write_rrd(comparison, rrd, payload=payload, blueprint=build, application_id=app, extra=extras)
            for stale in out.glob(f"{slug}.*.rbl"):  # write_rrd's named-layout sidecars: not these layouts
                stale.unlink()
        manifest["variants"][slug] = {"title": VARIANTS[slug], "rrd": rrd.name, "application_id": app,
                                      "bytes": rrd.stat().st_size if rrd.exists() else None}
        print(f"{slug}: {rrd}")
    # Q2's switcher: one blueprint per run, opened beside the .rrd
    app = "traj_compare-run-q2-solo-run"
    for run in derived.runs:
        q2(derived, run)(payload, {}).save(app, out / "blueprints" / f"q2-solo-run--{run.part}.rbl")
    # screenshot blueprints: paused, optionally zoomed
    for spec in shot_blueprints(derived):
        SHOT["paused"], SHOT["zoom"] = True, spec.get("zoom")
        rbl = out / "blueprints" / "shots" / f"{spec['slug']}--{spec['shot']}.rbl"
        rbl.parent.mkdir(exist_ok=True)
        spec["fn"](payload, {}).save(f"traj_compare-run-{spec['slug']}", rbl)
        SHOT["paused"], SHOT["zoom"] = False, None
        manifest["shots"].append({"slug": spec["slug"], "shot": spec["shot"], "rbl": str(rbl.relative_to(out)),
                                  "at": spec["at"], "caption": spec["caption"]})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"worst run {derived.worst.title} (tool max {derived.worst.tool_max_mm:.1f} mm), worst moment t = {derived.t_worst:.2f} s")


if __name__ == "__main__":
    main()
