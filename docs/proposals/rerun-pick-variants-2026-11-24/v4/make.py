#!/usr/bin/env python3
"""V4 · By joint + events: the run indexed by its events, the right half organised by JOINT.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v4/make.py

Writes v4/plan-dev-029.rrd (fixture.plan()) and v4/run-dev-029.rrd (fixture.run("p6s"): the solution drawn, the target
overlaid). Open either with `/home/bam/traj_compare/.venv/bin/rerun <file>`.

Thesis (Zach's frame kept: the URDF arm on the left half, always; tabs on the right half):
- The run is indexed by its EVENTS: start, each via point (the target's tool slowest between two moves), peak tool
  speed, the moment closest to a limit (q / qd / qdd vs the message's JointLimits), the worst tracking error (the
  agent's run: its own tool ruler), end. Each event is a numbered dot on the tool path, tinted by kind; while the
  playhead passes an event the live arm itself takes that event's colour (a solid tint, no second arm drawn on it),
  and the lit event's label reads "n kind" (placed clear of the other labels, the dots, the path and the arm).
- An Events tab leads the right half: two lanes on Rerun's state timeline (each event a numbered pulse; the moves
  between via points), the event log (a TextLog: time, kind, what it is; a click on a row's time cell moves the playhead
  there), a table of the arm at every event, and the tool speed (+ the run's tool error) with every event drawn as a
  vertical line.
- The rest is by JOINT: one tab per joint stacking its q, qd, qdd, qddd (small multiples, one shared time axis, the
  limits drawn, the events as vertical lines under the numbered lane), plus All joints and TCP. On the agent's run each joint tab overlays the
  target (faint, under the run) and adds the joint's error strip (run − target).
- His per-derivative tabs stay one click away inside All joints: All joints is itself a tab container whose tabs are
  "q / qd / qdd" (robot_msgs' cards + the playhead table, open first), then q, qd, qdd, qddd (robot_msgs' strips, one
  per joint), i.e. All joints › q is the stock q tab.

Built on robot_msgs.viz.rerun (main): `_RobotPlan` (the signals, limits, strips, FK, camera), `_log_robot` (the stock
series, limits, cards, TCP, playhead table, the arm and the tool path; only the arm's static steel tint is filtered out,
so its colour can go on the timeline) and its `_geometry_kinds` / `_DRAWABLE_MEDIA` for the arm's meshes. robot_msgs
is not edited; everything V4 adds is in this file.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from robot_msgs.trajectory import JointTrajectory, PoseTrajectory  # noqa: E402
from robot_msgs.viz import rerun as viz  # noqa: E402

APPLICATION_ID = "rerun_pick_v4"
TIMELINE = viz.TIMELINE

# one colour per event KIND, the same on the lit arm, the 3D dots and labels, the event lines, the lane and the log
# WHY calm (Zach: amber/red only for problems): start / end keep robot_msgs' blue / orange ghosts; a via point is green;
# peak speed teal; the limit event is violet unless the message is PAST a limit (then red); the worst error magenta.
# WHY green, not the first build's slate: a lit slate ghost on robot_msgs' steel arm barely changed it (the check)
_KIND_COLOUR = {
    "start": (70, 120, 220),
    "via": (60, 150, 75),
    "peak speed": (20, 150, 140),
    "near limit": (140, 80, 200),
    "past limit": (210, 50, 50),
    "worst error": (200, 50, 150),
    "end": (230, 130, 30),
}
# while the playhead is within _LIT_S of an event (windows cut halfway to the neighbours), the LIVE arm takes that
# event's colour: every link mesh's albedo on the timeline, opaque, the kind's colour at _LIT_ALPHA over robot_msgs'
# steel (mixed in linear light, as the viewer blended the lit ghost on the arm), so an event lights up as it did.
# Between events the arm is steel and only the numbered dots are drawn.
# WHY the live arm and not a lit ghost (the check of the second build): near its event a ghost stands where the arm is
# (its base always does), and the two meshes z-fought: magenta patches on the lower arm and base at 1.4 s, orange
# speckles at 3.1 s, half blue / half grey at 0.1 s. WHY no always-on ghosts (the first check): seven at alpha 40 fogged
# the live arm. `_GHOST_ALPHA = 40` brings them back, each hidden in its own window (fog, and the base z-fights again).
_LIT_S = 0.12
_LIT_ALPHA = 150
_GHOST_ALPHA = 0  # 0: no ghost copies are written at all (they would never be drawn, and each costs ~0.3 MB of meshes)
# the 3D labels: an unlit event shows its number, the lit one "n kind"; each label is placed (in screen space, for the
# blueprint's camera in the 1600×1000 review layout: an 800×908 px view, Rerun's 55° vertical field of view, measured to
# 1 px on the first build's frames) where its widest form ("n kind") overlaps no other label and no event dot.
# WHY (the check): "2 past limit" / "4 worst error" / "1 start" overprinted in the run, "2 near limit" / "3 via" in the plan
_VIEW_PX, _FOV_Y_DEG = (800.0, 908.0), 55.0
_LABEL_CHAR_PX, _LABEL_PAD_PX, _LABEL_H_PX, _DOT_PX = 6.3, 12.0, 18.0, 7.0
_MERGE_S = 0.06  # events closer than this share one window (one label: "3 via · peak speed")
_TARGET = (150, 175, 205)  # the target under the run: a pale blue, wider than the run's ink line
_ERROR = (200, 50, 150)
# WHY "0_target": a plot draws its series in entity-path order, and "target" sorted after the run ("p6s_…"), so the wide
# pale target hid the run's line wherever the two agree; a leading digit sorts first and is drawn under
_TARGET_PART = "0_target"
_VIA_PROMINENCE = 0.15  # a via point: a dip of the tool speed at least 15 % of its peak deep on both sides
_PULSE_S = 0.1  # an event's width on the "moments" lane: just wide enough for its number
_MOVE_SHADES = ((205, 210, 222, 255), (182, 189, 204, 255))
_REST_SHADE = (232, 234, 238, 255)
# an event line spans ±(a power of ten ≥ 10× its strip's range); every strip it is drawn in has a fixed y range, so it
# is clipped to the strip's height. WHY a ladder, not one huge span: a ±1e6 line in a ±0.1° strip is ~1e9 px long, past
# f32 precision; the viewer drew it dashed (±4 mm strip) or not at all (±0.1° strip)


class _Event:
    def __init__(self, kind: str, index: int, t: float, what: str, detail: str, colour: tuple) -> None:
        self.kinds, self.index, self.t, self.whats, self.details, self.colour = [kind], index, t, [what], [detail], colour
        self.number = 0

    @property
    def kind(self) -> str:
        return " · ".join(self.kinds)

    @property
    def label(self) -> str:
        """The lit form of the 3D label (unlit, it is the number alone)."""
        return f"{self.number} {self.kind}"

    @property
    def line(self) -> str:
        """The event log's body: number, time, what, detail (one row of Rerun's text log is one line)."""
        parts = [f"{what} — {detail}" if detail else what for what, detail in zip(self.whats, self.details, strict=True)]
        return f"{self.number} · {self.t:.2f} s · " + " · ".join(parts)


# ── the events ──────────────────────────────────────────────────────────────────────────────────────────────────


def _vias(seconds: np.ndarray, speed: np.ndarray) -> list[int]:
    """Via points: where the tool is at rest or slowest between two moves = the dips of its speed that are at least
    `_VIA_PROMINENCE` of the peak speed deep (a flat stop counts once, at its middle; the rest at either end does not)."""
    from scipy.signal import find_peaks

    top = float(np.nanmax(speed)) if speed.size else 0.0
    if top <= 0.0:
        return []
    dips, _ = find_peaks(-speed, prominence=_VIA_PROMINENCE * top)
    return [int(k) for k in dips]


def _differenced(plan: Any, short: str) -> bool:
    """True when the message's ``short`` (qd or qdd) is exactly the numerical difference of its q (np.gradient once /
    twice): a measured run's rates, not a planner's. WHY checked, not assumed: the caveat is printed only when true."""
    q = plan.signals["q"]
    if short not in ("qd", "qdd") or q is None or plan.signals[short] is None or len(plan.seconds) < 3:
        return False
    qd = np.gradient(q, plan.seconds, axis=0)
    rate = qd if short == "qd" else np.gradient(qd, plan.seconds, axis=0)
    return bool(np.allclose(plan.signals[short], rate, rtol=1e-6, atol=1e-9))


def _smoothed_percent(plan: Any, short: str, joint: int, windows_s: tuple[float, ...] = (0.07, 0.09, 0.11)) -> tuple[float, float]:
    """The joint's peak |short| (qd or qdd) as % of its limit when q is Savitzky–Golay smoothed over each window
    (polyorder 2) before it is differentiated: (lowest, highest) over the windows. Only a check printed beside the
    event; the plotted data stays as given."""
    from scipy.signal import savgol_filter

    step = float(np.median(np.diff(plan.seconds)))
    low, high = (bound[joint] for bound in plan.limits[short])
    peaks = []
    for window_s in windows_s:
        width = max(int(round(window_s / step)) | 1, 5)  # odd, and wider than the polynomial
        rate = savgol_filter(plan.signals["q"][:, joint], width, 2, deriv=1 if short == "qd" else 2, delta=step)
        peaks.append(float(np.max(np.abs(viz._percent(rate, low, high)))))
    return min(peaks), max(peaks)


def _limit_event(plan: Any, measured: bool) -> tuple[int, int, str, float, str, str, str, str]:
    """The sample closest to (or furthest past) a limit over q, qd, qdd, with robot_msgs' % of limit (the cards'):
    (sample, joint, quantity, %, what, detail, kind, the per-quantity summary). ``measured``: the trajectory is a run's
    (its q from encoders), so a qd / qdd that is a difference of q is called MEASURED in the detail."""
    worst = None
    per_field = []
    for short in ("q", "qd", "qdd"):
        values = plan.signals[short]
        if values is None:
            continue
        low, high = plan.limits[short]
        if not np.any(np.isfinite(low) & np.isfinite(high)):
            continue
        with np.errstate(invalid="ignore"):
            percent = np.abs(viz._percent(values, low, high))
        percent = np.where(np.isfinite(percent), percent, -1.0)
        k, j = np.unravel_index(int(np.argmax(percent)), percent.shape)
        rate = {"q": "", "qd": "/s", "qdd": "/s²"}[short]
        unit = plan.unit(j, rate).strip()
        shown = float(values[k, j] * plan.scale[j])
        bound = float(high[j] * plan.scale[j])
        entry = (float(percent[k, j]), int(k), int(j), short, shown, bound, unit)
        per_field.append(entry)
        if worst is None or entry[0] > worst[0]:
            worst = entry
    if worst is None:
        return -1, -1, "", 0.0, "", "", "near limit", ""
    percent, k, j, short, shown, bound, unit = worst
    joint = viz._short_joint(plan.joints[j])
    kind = "past limit" if percent > 100.0 else "near limit"
    span = f"±{bound:.0f}{unit}" if short != "q" else f"{plan.limits['q'][0][j] * plan.scale[j]:.0f}…{bound:.0f}{unit}"
    what = f"{joint} {short} {percent:.1f} % of limit"
    detail = f"{shown:+.0f}{unit} of {span}"
    if measured and _differenced(plan, short):
        # WHY said in the row itself (the check): 145 % read as the plan's number; it is the run's encoder q, differenced
        detail += " · MEASURED: differences of encoder q"
    elif kind == "past limit":
        detail += " · PAST it"
    summary = "worst % of limit per quantity: " + " · ".join(
        f"{f} {viz._short_joint(plan.joints[jj])} {p:.0f} % at {plan.seconds[kk]:.2f} s" for p, kk, jj, f, *_ in per_field)
    return k, j, short, percent, what, detail, kind, summary


def _events(plan: Any, target_plan: Any | None, extras: dict | None) -> tuple[list[_Event], list[str], float]:
    """The run's events in time order, numbered 1..n (events closer than `_MERGE_S` merged), the notes for the table,
    and the time the arm comes to rest for good (= the end when it never does)."""
    seconds = plan.seconds
    last = len(seconds) - 1
    speed_run = np.interp(seconds, plan.tool_t, plan.tcp["speed_mm_s"])
    found: list[_Event] = []

    def add(kind: str, k: int, what: str, detail: str, colour_kind: str | None = None) -> None:
        found.append(_Event(kind, int(k), float(seconds[k]), what, detail, _KIND_COLOUR[colour_kind or kind]))

    xyz = plan.tool_xyz * 1000.0
    notes: list[str] = []
    add("start", 0, "start", f"tool at ({xyz[0, 0]:.0f}, {xyz[0, 1]:.0f}, {xyz[0, 2]:.0f}) mm")
    # via points from the INTENT: the target's tool when there is one (the run's own speed dips are noise + the same)
    intent = target_plan if target_plan is not None else plan
    intent_speed = np.interp(seconds, intent.tool_t, intent.tcp["speed_mm_s"])
    for n, k in enumerate(_vias(seconds, intent_speed), start=1):
        whose = "the target's tool" if target_plan is not None else "the tool"
        add("via", k, f"via {n}", f"{whose} slowest between moves, {intent_speed[k]:.0f} mm/s")
    peak = int(np.argmax(speed_run))
    add("peak speed", peak, f"peak tool speed {speed_run[peak]:.0f} mm/s",
        f"turning {np.interp(seconds, plan.tool_t, plan.tcp['angular_speed_deg_s'])[peak]:.0f}°/s")
    k, j, short, percent, what, detail, kind, summary = _limit_event(plan, measured=target_plan is not None)
    caveat = None
    if k >= 0:
        add(kind, k, what, detail)
        notes.append(f"*{summary}*")
        if target_plan is not None and _differenced(plan, short):
            low, high = _smoothed_percent(plan, short, j)
            label = str((extras or {}).get("label", ""))
            who = f" ({label.split(',')[0]})" if label else ""
            verdict = ("still {low:.0f}–{high:.0f} %: a real overshoot of the controller{who}, not only noise" if low > 100.0
                       else "{low:.0f}–{high:.0f} %, within the limit: the peak is the differences' noise" if high <= 100.0
                       else "{low:.0f}–{high:.0f} %: partly the differences' noise")  # fmt: skip
            caveat = (kind, f"the solution's MEASURED {short}: {'second ' if short == 'qdd' else ''}differences of its "
                      f"encoder q, drawn as given ({percent:.1f} %). Smoothed first (Savitzky–Golay, 70–110 ms) it is "
                      + verdict.format(low=low, high=high, who=who) + ".")
    if target_plan is not None:
        joint_error = (plan.signals["q"] - target_plan.signals["q"]) * plan.scale
        ruler = None if extras is None else extras.get("tool_error_mm")
        if ruler is not None:
            error, source = np.asarray(ruler, dtype=np.float64), "the agent's ruler"
        else:
            aimed = np.stack([np.interp(seconds, target_plan.tool_t, target_plan.tool_xyz[:, axis]) for axis in range(3)], 1)
            done = np.stack([np.interp(seconds, plan.tool_t, plan.tool_xyz[:, axis]) for axis in range(3)], 1)
            error, source = np.linalg.norm(done - aimed, axis=1) * 1000.0, "tool distance to the target"
        w = int(np.nanargmax(error))
        j = int(np.argmax(np.abs(joint_error[w])))
        rms = extras.get("rms_mm") if extras else None
        rms_text = f", RMS {float(rms):.2f} mm" if rms is not None else ""
        add("worst error", w, f"worst tracking error {error[w]:.2f} mm",
            f"{source}{rms_text} · joint then: {viz._short_joint(plan.joints[j])} {joint_error[w, j]:+.2f}°")
    moving = np.flatnonzero(speed_run > 0.01 * float(speed_run.max()))
    rest_k = int(moving[-1]) + 1 if moving.size and moving[-1] + 1 < last else last
    settled = f"at rest from {seconds[rest_k]:.2f} s · " if rest_k < last else ""
    add("end", last, "end", f"{settled}tool at ({xyz[last, 0]:.0f}, {xyz[last, 1]:.0f}, {xyz[last, 2]:.0f}) mm")

    # merge events closer than _MERGE_S (one window, one label), keep time order, number them 1..n
    found.sort(key=lambda e: (e.t, e.kind != "start"))
    merged: list[_Event] = []
    for event in found:
        if merged and event.t - merged[-1].t < _MERGE_S:
            head = merged[-1]
            head.kinds += event.kinds
            head.whats += event.whats
            head.details += event.details
            continue
        merged.append(event)
    for number, event in enumerate(merged, start=1):
        event.number = number
    if caveat is not None:
        head = next(e for e in merged if caveat[0] in e.kinds)
        notes.append(f"**{head.number} {caveat[0]}** is {caveat[1]}")
    return merged, notes, float(seconds[rest_k])


# ── logging ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _copy_geometry(plan: Any, copy: str) -> tuple[Any, str, str, list[Any], dict[str, str]]:
    """What robot_msgs' `_urdf_copy` draws for ``copy`` ("robot" = the live arm): (the tree with its frames prefixed,
    the copy's entity, the loader's root, the loader's chunks, {drawn geometry's entity in the copy: its archetype}).
    Visuals first, else collision, as `_urdf_copy` picks them, so the paths are exactly the ones it tints."""
    import rerun.urdf as rurdf

    prefix = f"{plan.part}/" if copy == "robot" else f"{plan.part}/{copy}/"
    tree = rurdf.UrdfTree.from_file_path(plan.urdf, frame_prefix=prefix)
    entity, old_root = f"/world/{plan.part}/{copy}", f"/{tree.name}"
    chunks = list(tree.stream(include_joint_transforms=False))
    kinds = viz._geometry_kinds(chunks)

    def drawable(path: str) -> bool:
        archetype, media = kinds.get(path, ("", None))
        return bool(archetype) and (archetype != "Asset3D" or media in viz._DRAWABLE_MEDIA)

    keep: set[str] = set()
    for link in [tree.root_link().name, *(joint.child_link for joint in tree.joints())]:
        visuals = [path for path in tree.get_visual_geometry_paths(link) if drawable(path)]
        keep.update(visuals or [path for path in tree.get_collision_geometry_paths(link) if drawable(path)])
    return tree, entity, old_root, chunks, {entity + path[len(old_root):]: kinds[path][0] for path in sorted(keep)}


def _send_tints(recording: Any, geometry: dict[str, str], times: list[float], tints: list[tuple[int, ...]]) -> None:
    """Every geometry's colour on the timeline: ``tints[i]`` from ``times[i]`` on (latest-at holds it in between)."""
    at = [rr.TimeColumn(TIMELINE, duration=times)]
    for target, archetype in geometry.items():
        if archetype == "Asset3D":
            recording.send_columns(target, indexes=at, columns=rr.Asset3D.columns(albedo_factor=tints))
        elif archetype == "Mesh3D":
            recording.send_columns(target, indexes=at, columns=rr.Mesh3D.columns(albedo_factor=tints))
        else:  # Boxes3D, Cylinders3D, ...: one colour per instance
            recording.send_columns(target, indexes=at, columns=getattr(rr, archetype).columns(colors=tints))


def _ghost(plan: Any, recording: rr.RecordingStream, copy: str, event: _Event, times: list[float], alphas: list[int]) -> None:
    """A keyframe ghost of the arm at the event's sample (only when `_GHOST_ALPHA` > 0): robot_msgs' `_urdf_copy`, but
    the tint on the timeline (``alphas[i]`` from ``times[i]`` on) instead of static.

    WHY not `viz._urdf_copy`: it logs the tint static, and a static component always wins over a temporal one."""
    tree, entity, old_root, chunks, geometry = _copy_geometry(plan, copy)
    drawn = {old_root + path[len(entity):] for path in geometry}
    every = set(viz._geometry_kinds(chunks))
    recording.send_chunks([
        chunk.with_entity_path(entity + chunk.entity_path[len(old_root):])
        for chunk in chunks
        if not any(chunk.entity_path == path or chunk.entity_path.startswith(path + "/") for path in every - drawn)
    ])  # fmt: skip
    _send_tints(recording, geometry, times, [(*event.colour, alpha) for alpha in alphas])
    prefix = f"{plan.part}/{copy}/"
    recording.log(f"{entity}/mount", rr.Transform3D(parent_frame=f"tf#/world/{plan.part}",
                                                    child_frame=prefix + tree.root_link().name), static=True)
    for joint in tree.joints():
        values = plan.values.get(joint.name)
        value = 0.0 if values is None or joint.joint_type == "fixed" else float(values[event.index])
        recording.log(f"{entity}/joint_transforms/{viz._part(joint.name)}", joint.compute_transform(value, clamp=False),
                      static=True)  # fmt: skip


class _WithoutArmTint:
    """The recording, minus robot_msgs' STATIC tint on the live arm's meshes (`_urdf_copy` logs `_ARM` static, and a
    static component always wins over a temporal one, so the arm could never be lit). Everything else `_log_robot`
    logs (the series, limits, cards, TCP, table, the arm's meshes, mount and joint transforms, the tool path) passes.
    WHY a filter and not a copy of `_log_robot` (V5 does the same for its own entities): the arm stays robot_msgs'.
    ``dropped`` is checked after the call, so a robot_msgs change that moved the tint fails the build, not the look."""

    def __init__(self, stream: rr.RecordingStream, geometry: dict[str, str]) -> None:
        self._stream, self._geometry, self.dropped = stream, geometry, set()

    def log(self, path: Any, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("static") and str(path) in self._geometry:
            self.dropped.add(str(path))
            return
        self._stream.log(path, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def _linear(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(linear: np.ndarray) -> np.ndarray:
    return 255.0 * np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(linear, 1.0 / 2.4) - 0.055)


def _lit_colour(colour: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """The live arm's colour while an event is lit: the kind's colour at `_LIT_ALPHA` over robot_msgs' steel, opaque.
    WHY mixed in linear light: that is how the viewer blended the lit ghost over the arm, so the tint reads as before."""
    mix = _LIT_ALPHA / 255.0
    rgb = _srgb(mix * _linear(colour) + (1.0 - mix) * _linear(viz._ARM[:3]))
    return (*(int(round(float(v))) for v in np.clip(rgb, 0, 255)), 255)


def _windows(events: list[_Event], end: float) -> list[tuple[float, float]]:
    """Each event's lit window [from, to): ±_LIT_S, cut halfway to its neighbours so two never overlap, and inside the
    recording (a window that reaches the last sample stays lit through it)."""
    out = []
    for n, event in enumerate(events):
        low = event.t - _LIT_S if n == 0 else max(event.t - _LIT_S, 0.5 * (events[n - 1].t + event.t))
        high = event.t + _LIT_S if n == len(events) - 1 else min(event.t + _LIT_S, 0.5 * (event.t + events[n + 1].t))
        out.append((max(low, 0.0), min(high, end)))
    return out


def _lit_steps(windows: list[tuple[float, float]], end: float) -> tuple[list[float], list[int | None]]:
    """The lit event (its index, or None) as a step function on the timeline: from ``times[i]`` on, ``lit[i]``.

    WHY no step at or past ``end`` (the check): the first build closed the last window at end + 1 ms, which stretched
    the timeline to 3.201 s and left the end ghost unlit at the recording's end; a window that reaches the last sample
    now never closes. WHY starts written after ends: a window cut halfway starts where its neighbour's ends."""
    state: dict[float, int | None] = {0.0: None}
    for start, stop in windows:
        if stop < end - 1e-9:
            state[round(stop, 9)] = None
    for index, (start, _) in enumerate(windows):
        state[round(start, 9)] = index
    times = sorted(state)
    return times, [state[t] for t in times]


def _camera(plan: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float] | None:
    """The blueprint's camera (robot_msgs' `plan.eye`) as (position, forward, right, up, focal px) in the review
    layout's 3D view, or None when it cannot be read back (the labels then sit on their dots)."""
    try:
        position, look, up = (np.asarray(getattr(plan.eye, name).pa_array.to_pylist()[0], dtype=np.float64)
                              for name in ("position", "look_target", "eye_up"))  # fmt: skip
    except (AttributeError, IndexError, TypeError):
        return None
    forward = look - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    focal = 0.5 * _VIEW_PX[1] / np.tan(np.radians(0.5 * _FOV_Y_DEG))
    return position, forward, right, np.cross(right, forward), focal


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _project(camera: tuple, world: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Points in the URDF's root frame → (pixels in the review layout's 3D view, depth along the view)."""
    position, forward, right, up, focal = camera
    relative = world - position
    depth = relative @ forward
    centre = 0.5 * np.asarray(_VIEW_PX)
    return np.stack([centre[0] + focal * (relative @ right) / depth, centre[1] - focal * (relative @ up) / depth], 1), depth


def _stl(path: Path) -> np.ndarray:
    """An STL's triangle vertices, ``(n, 3, 3)`` (binary or ASCII)."""
    raw = path.read_bytes()
    count = int.from_bytes(raw[80:84], "little") if len(raw) >= 84 else -1
    if count >= 0 and len(raw) == 84 + 50 * count:
        records = np.frombuffer(raw, dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]),
                                count=count, offset=84)  # fmt: skip
        return records["v"].astype(np.float64)
    numbers = [line.split()[1:4] for line in raw.decode(errors="ignore").splitlines() if line.strip().startswith("vertex")]
    return np.asarray(numbers, dtype=np.float64).reshape(-1, 3, 3)


def _arm_cells(plan: Any, traj: JointTrajectory, samples: list[int], camera: tuple, cell: float = 6.0) -> list[set]:
    """The arm's silhouette at each of ``samples`` in the review layout's 3D view, as occupied ``cell`` px squares
    (each link's STL meshes, collision first as robot_msgs draws this URDF, through robot_msgs' own forward
    kinematics). A link without an STL mesh is left out (no silhouette is better than a wrong one)."""
    import xml.etree.ElementTree as ElementTree

    import rerun.urdf as rurdf
    from robot_msgs.geometry.rotations import euler_to_matrix

    urdf = Path(plan.urdf)
    tree = rurdf.UrdfTree.from_file_path(str(urdf))
    links = viz._forward_kinematics(tree, viz._joint_values(tree, traj), len(plan.seconds))
    meshes: list[tuple[str, np.ndarray]] = []  # (link, triangles (n, 3, 3) in the link's frame)
    for link in ElementTree.parse(urdf).getroot().iter("link"):
        for kind in ("collision", "visual"):
            found = []
            for element in link.iter(kind):
                mesh = element.find("geometry/mesh")
                if mesh is None or not mesh.get("filename", "").lower().endswith(".stl"):
                    continue
                file = (urdf.parent / mesh.get("filename").replace("package://", "")).resolve()
                if not file.exists():
                    continue
                triangles = _stl(file) * np.asarray([float(v) for v in (mesh.get("scale") or "1 1 1").split()])
                origin = element.find("origin")
                xyz = [float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()]
                rpy = [float(v) for v in (origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split()]
                found.append(triangles @ np.asarray(euler_to_matrix(*rpy)).T + np.asarray(xyz))
            if found:
                meshes += [(link.get("name"), points) for points in found]
                break
    out = []
    for sample in samples:
        occupied: set = set()
        for link, triangles in meshes:
            pose = links[link][sample]
            pixels, depth = _project(camera, triangles.reshape(-1, 3) @ pose[:3, :3].T + pose[:3, 3])
            corners = (pixels / cell).reshape(-1, 3, 2)[(depth.reshape(-1, 3) > 0).all(axis=1)]
            cells = _raster(corners)
            for dx in (-1, 0, 1):  # dilated one cell, so a label clears the mesh's edge
                for dy in (-1, 0, 1):
                    occupied.update(map(tuple, np.unique(cells + (dx, dy), axis=0)))
        out.append(occupied)
    return out


def _raster(corners: np.ndarray) -> np.ndarray:
    """The cells a set of triangles (corners in cell units, ``(n, 3, 2)``) cover: each sampled on a barycentric lattice
    finer than a cell (WHY not the vertices alone: a UR5e tube is a few long triangles, and its middle came out empty)."""
    edges = np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2).max(axis=1)
    steps = np.clip(np.ceil(edges * 1.5), 1, 80).astype(int)
    found = [np.floor(corners.reshape(-1, 2)).astype(int)]
    for step in np.unique(steps):
        chosen = corners[steps == step]
        a, b = (grid.ravel() / step for grid in np.meshgrid(np.arange(step + 1), np.arange(step + 1)))
        keep = a + b <= 1.0 + 1e-9
        weights = np.stack([a[keep], b[keep], 1.0 - a[keep] - b[keep]], axis=1)  # (m, 3)
        found.append(np.floor(np.einsum("mk,nkd->nmd", weights, chosen).reshape(-1, 2)).astype(int))
    return np.unique(np.vstack(found), axis=0)


def _label_layout(plan: Any, events: list[_Event], points: np.ndarray, mount: np.ndarray,
                  arms: list[set] | None, cell: float = 6.0) -> tuple[np.ndarray, np.ndarray, list[np.ndarray | None]]:
    """Where each event's 3D label goes, lit ("n kind") and unlit ("n"), in the tool frame, and a leader line's far end
    when the label had to move away from its dot (else None).

    Greedy cartographic placement in the review layout's screen space: each label, in event order, takes the nearest of
    the candidate spots (below its dot, above, right, left, then further out, up to ~110 px) where its lit form covers
    no placed label, no event dot, and as little as it can of the tool path and of the arm as it stands at that event
    (``arms``: `_arm_cells`; WHY: at the end the lit "7 end" sat on the orange-lit arm and lost its contrast), each
    14 px further out weighed against ~1 cell of cover. The number alone sits at the lit label's end
    nearest the dot. A pixel offset goes back to 3D at the dot's depth, so it holds when the view is resized (the
    labels' own pixel size does not scale). A Rerun label hangs centred below its point."""
    camera = _camera(plan)
    if camera is None:
        return points.copy(), points.copy(), [None] * len(events)
    position, forward, right, up, focal = camera
    rotation, offset = mount[:3, :3], mount[:3, 3]
    world = points @ rotation.T + offset
    dot_px, depth = _project(camera, world)
    dots = [(x - _DOT_PX, y - _DOT_PX, x + _DOT_PX, y + _DOT_PX) for x, y in dot_px]
    view = (0.0, 30.0, _VIEW_PX[0], _VIEW_PX[1])  # below the view's title bar
    path_px, _ = _project(camera, plan.tool_xyz @ rotation.T + offset)
    along = [np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b - a) / 2.0)) + 1)) for a, b in zip(path_px[:-1], path_px[1:])]
    path = set(map(tuple, np.unique(np.floor(np.vstack(along) / cell).astype(int), axis=0)))
    placed: list[tuple[float, ...]] = []
    lit_anchors, unlit_anchors, leaders = [], [], []
    for i, event in enumerate(events):
        width, height = _LABEL_CHAR_PX * len(event.label) + _LABEL_PAD_PX, _LABEL_H_PX
        number = _LABEL_CHAR_PX * len(str(event.number)) + _LABEL_PAD_PX
        # candidates, nearest first: (side: -1 left / 0 centred / +1 right of the dot, box top below the dot, side gap)
        candidates = []
        for extra in (0.0, 14.0, 28.0, 44.0, 62.0, 84.0, 110.0):
            beside = _DOT_PX + 2.0 + extra
            candidates += [(extra, 0, _DOT_PX - 2.0 + extra, 0.0), (extra, 0, -height - _DOT_PX + 1.0 - extra, 0.0),
                           (extra, 1, -0.5 * height, beside), (extra, -1, -0.5 * height, beside),
                           (extra, 1, 4.0 + extra, beside), (extra, -1, 4.0 + extra, beside),
                           (extra, 1, -height - 4.0 - extra, beside), (extra, -1, -height - 4.0 - extra, beside)]
        best = None
        for rank, (extra, side, top, beside) in enumerate(candidates):
            dot_x = dot_px[i, 0]
            left = dot_x - 0.5 * width if side == 0 else dot_x + beside if side > 0 else dot_x - beside - width
            box = (left, dot_px[i, 1] + top, left + width, dot_px[i, 1] + top + height)
            outside = width * height - _overlap(box, view)
            xs = range(int(np.floor(box[0] / cell)), int(np.floor(box[2] / cell)) + 1)
            ys = range(int(np.floor(box[1] / cell)), int(np.floor(box[3] / cell)) + 1)
            covered = sum((x, y) in path or (arms is not None and (x, y) in arms[i]) for x in xs for y in ys)
            cost = (10.0 * sum(_overlap(box, other) for other in placed) + 10.0 * outside
                    + 10.0 * sum(_overlap(box, dot) for k, dot in enumerate(dots) if k != i) + covered * cell * cell)  # fmt: skip
            score = cost + 2.5 * extra + 0.01 * rank
            if best is None or score < best[0]:
                best = (score, rank, box, side)
            if cost == 0.0:  # every later candidate is at least this far out
                break
        _, _, box, side = best
        placed.append(box)
        # the number alone: at the lit label's end nearest the dot (centred when the label is above or below it)
        small_left = box[0] if side > 0 else box[2] - number if side < 0 else 0.5 * (box[0] + box[2]) - 0.5 * number
        small = (small_left, box[1], small_left + number, box[3])

        def lift(pixel: np.ndarray, k: int = i) -> np.ndarray:
            """A pixel of the view, as a point in the tool frame at dot k's depth."""
            gap = pixel - dot_px[k]
            moved = world[k] + (gap[0] * right - gap[1] * up) * depth[k] / focal
            return (moved - offset) @ rotation

        lit_anchors.append(lift(np.asarray([0.5 * (box[0] + box[2]), box[1]])))
        unlit_anchors.append(lift(np.asarray([0.5 * (small[0] + small[2]), small[1]])))
        near = np.clip(dot_px[i], small[:2], small[2:])  # the label's nearest point to its dot
        leaders.append(lift(near) if np.hypot(*(near - dot_px[i])) > _DOT_PX + 4.0 else None)
    return np.asarray(lit_anchors), np.asarray(unlit_anchors), leaders


def _arm_table(plan: Any, events: list[_Event], speed: np.ndarray, notes: list[str]) -> tuple[np.ndarray, list[str]]:
    """The Events tab's table, one markdown document per instant (robot_msgs' `_ROWS` cap): every event's time, kind and
    the arm there (each joint's q in degrees, the tool speed), the latest event at or before the playhead marked ▶."""
    seconds = plan.seconds
    last = len(seconds) - 1
    picked = np.unique(np.linspace(0, last, min(last + 1, viz._ROWS)).round().astype(int))
    shorts = [viz._short_joint(joint).replace("shoulder_", "").replace("wrist_", "w") for joint in plan.joints]
    header = "| | # | t s | event | " + " | ".join(shorts) + " | tool mm/s |"
    rule = "|---|---:|---:|---|" + "---:|" * len(shorts) + "---:|"
    docs = []
    for k in picked:
        now = seconds[k]
        passed = [e for e in events if e.t <= now + 1e-9]
        ahead = [e for e in events if e.t > now + 1e-9]
        current = passed[-1] if passed else None
        line = f"**t = {now:.2f} s**"
        if current is not None:
            line += f" · last event **{current.number} {current.kind}** at {current.t:.2f} s"
        if ahead:
            line += f" · next **{ahead[0].number} {ahead[0].kind}** in {ahead[0].t - now:.2f} s"
        rows = [line, "", header, rule]
        for event in events:
            mark = "▶" if event is current else ""
            q = plan.signals["q"][event.index] * plan.scale
            cells = " | ".join(f"{value:+.0f}" for value in q)
            text = f"| {mark} | {event.number} | {event.t:.2f} | {event.kind} | {cells} | {speed[event.index]:.0f} |"
            rows.append(text.replace(f"| {event.kind} |", f"| **{event.kind}** |") if event is current else text)
        # WHY a blank line between notes (the check): markdown joins adjacent lines into one paragraph, so the
        # measured-qdd caveat ran on straight after "… qdd wrist_2 145 % at 0.40 s"
        docs.append("\n".join(rows) + "\n\n" + "\n\n".join(notes))
    return seconds[picked], docs


def _log_events(plan: Any, events: list[_Event], rest: float, marks: "_Marks", recording: rr.RecordingStream,
                mount: np.ndarray, traj: JointTrajectory, arm: dict[str, str]) -> None:
    part = plan.part
    end = float(plan.seconds[-1])
    times, lit = _lit_steps(_windows(events, end), end)
    # 1. the live arm (``arm``: its meshes, their static tint filtered out of `_log_robot`) lit in an event's colour while
    #    the playhead passes it, steel in between. No ghost is drawn lit: it would sit on the live arm and z-fight
    _send_tints(recording, arm, times, [viz._ARM if state is None else _lit_colour(events[state].colour) for state in lit])
    if _GHOST_ALPHA > 0:  # the first build's always-on faint ghosts, each hidden in its own window (the arm is lit)
        for index, event in enumerate(events):
            _ghost(plan, recording, f"event_{event.number}", event, times,
                   [0 if state == index else _GHOST_ALPHA for state in lit])
    # 2. at each event's tool point a small dot (static), a bigger one on the lit event (temporal), and a label placed
    #    clear of the others (`_label_layout`): the number, "n kind" while lit (temporal), with a leader line when it
    #    had to move away from its dot
    frame = rr.CoordinateFrame(f"{part}/{plan.tool_frame}")
    xyz = plan.tool_xyz
    tool_index = [int(np.argmin(np.abs(plan.tool_t - event.t))) for event in events]
    dots = np.asarray([xyz[k] for k in tool_index])
    camera = _camera(plan)
    arms = None if camera is None else _arm_cells(plan, traj, [event.index for event in events], camera)
    lit_at, unlit_at, leaders = _label_layout(plan, events, dots, mount, arms)
    recording.log(f"/world/{part}/events/dots", rr.Points3D(dots, colors=[e.colour for e in events], radii=[0.008]),
                  frame, static=True)  # fmt: skip
    strips = [(np.stack([dots[i], end_point]), events[i].colour) for i, end_point in enumerate(leaders)
              if end_point is not None]
    if strips:
        recording.log(f"/world/{part}/events/leaders", rr.LineStrips3D([s for s, _ in strips], colors=[c for _, c in strips],
                                                                       radii=[0.0012]), frame, static=True)  # fmt: skip
    label_path, lit_path = f"/world/{part}/events/labels", f"/world/{part}/events/lit"
    recording.log(label_path, rr.Points3D.from_fields(colors=[e.colour for e in events], radii=[0.0005], show_labels=True),
                  frame, static=True)  # fmt: skip
    recording.log(lit_path, rr.Points3D.from_fields(radii=[0.016]), frame, static=True)
    # WHY one log per step: the lit dot is ragged (one or none), and there are about two steps per event
    for at, state in zip(times, lit, strict=True):
        recording.set_time(TIMELINE, duration=at)
        recording.log(label_path, rr.Points3D.from_fields(
            positions=[lit_at[n] if n == state else unlit_at[n] for n in range(len(events))],
            labels=[e.label if n == state else str(e.number) for n, e in enumerate(events)]))
        recording.log(lit_path, rr.Points3D(np.zeros((0, 3))) if state is None
                      else rr.Points3D([dots[state]], colors=[(*events[state].colour, 255)]))
    recording.reset_time()
    # 3. the event log: one TextLog per event at its time (the level column = its kind)
    recording.send_columns("/events/log", indexes=[rr.TimeColumn(TIMELINE, duration=[e.t for e in events])],
                           columns=rr.TextLog.columns(
                               text=[e.line for e in events],
                               level=[e.kind.upper() for e in events],
                               color=[e.colour for e in events]))  # fmt: skip
    # 4. two lanes on Rerun's state timeline. "moments": each event a short numbered pulse at its time (WHY a pulse, not
    #    a state lasting until the next event: a long red "past limit" bar read as a limit held for 0.75 s). "moves": the
    #    motion cut at its via points (move 1, move 2, …, at rest), the one place a duration is what is meant
    end = float(plan.seconds[-1])
    rows: list[tuple[float, str]] = []
    for event in events:
        low = min(max(event.t - 0.5 * _PULSE_S, 0.0), end - _PULSE_S)
        rows += [(low, f"e{event.number}"), (low + _PULSE_S, "")]
    rows.sort(key=lambda row: row[0])
    recording.log("/events/moments", rr.StateConfiguration(
        values=[f"e{e.number}" for e in events], labels=[str(e.number) for e in events],
        colors=[(*e.colour, 255) for e in events]), static=True)  # fmt: skip
    recording.send_columns("/events/moments", indexes=[rr.TimeColumn(TIMELINE, duration=[row[0] for row in rows])],
                           columns=rr.StateChange.columns(state=[row[1] for row in rows]))
    cuts = [0.0] + [e.t for e in events if "via" in e.kinds] + ([rest] if rest < end - 1e-9 else [])
    names = [f"move {n}" for n in range(1, len(cuts) - (rest < end - 1e-9) + 1)] + (["at rest"] if rest < end - 1e-9 else [])
    labels = [f"{name} · {a:.2f}–{b:.2f} s" for name, a, b in zip(names, cuts, [*cuts[1:], end], strict=True)]
    recording.log("/events/moves", rr.StateConfiguration(
        values=names, labels=labels,
        colors=[_MOVE_SHADES[n % 2] if name != "at rest" else _REST_SHADE for n, name in enumerate(names)]),
        static=True)  # fmt: skip
    recording.send_columns("/events/moves", indexes=[rr.TimeColumn(TIMELINE, duration=[*cuts, end])],
                           columns=rr.StateChange.columns(state=[*names, ""]))
    # 5. one vertical line per event and span class used by the blueprint (`_Marks`): ±span at the event's time
    for span in sorted(marks.used):
        for event in events:
            path = marks.path(span, event)
            recording.log(path, rr.SeriesLines(colors=[event.colour], widths=[1.2], names=[f"{event.number} {event.kind}"],
                                               aggregation_policy="Off"), static=True)  # fmt: skip
            # WHY aggregation off: zoomed out, averaging the two ends of the line gives one point at 0
            # WHY never past `end`: the end event's t + 1 ns would stretch the timeline past the last sample
            at = [event.t, event.t + 1e-9] if event.t + 1e-9 <= end else [event.t - 1e-9, event.t]
            recording.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=at)],
                                   columns=rr.Scalars.columns(scalars=[-span, span]))


def _log_target(plan: Any, target_plan: Any, target: JointTrajectory, recording: rr.RecordingStream) -> None:
    """The target under the run: the stock series at /<field>/<joint>/target (faint, wide), its jerk, and the run's
    joint error at /joint_error/<joint>."""
    viz._series(target, _TARGET_PART, recording, degrees=plan.revolute, color=_TARGET, label="target")
    on_t = [rr.TimeColumn(TIMELINE, duration=target_plan.seconds)]
    for field_name in ("positions", "velocities", "accelerations"):
        for joint in plan.joints:
            recording.log(f"/{field_name}/{viz._part(joint)}/{_TARGET_PART}",
                          rr.SeriesLines(names="target", colors=_TARGET, widths=3.0), static=True)
    for index, joint in enumerate(plan.joints):
        entity = f"/jerks/{viz._part(joint)}/{_TARGET_PART}"
        recording.log(entity, rr.SeriesLines(names="target", colors=_TARGET, widths=3.0), static=True)
        recording.send_columns(entity, indexes=on_t, columns=rr.Scalars.columns(
            scalars=target_plan.signals["qddd"][:, index] * plan.scale[index]))
        error = (plan.signals["q"][:, index] - target_plan.signals["q"][:, index]) * plan.scale[index]
        entity = f"/joint_error/{viz._part(joint)}"
        recording.log(entity, rr.SeriesLines(names="run − target", colors=_ERROR, widths=1.4), static=True)
        recording.send_columns(entity, indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                               columns=rr.Scalars.columns(scalars=error))


# ── the blueprint ───────────────────────────────────────────────────────────────────────────────────────────────


def _plot(title: str, contents: list[str], y_range: tuple[float, float] | None, legend: bool = False) -> Any:
    return rrb.TimeSeriesView(
        origin="/", contents=contents, name=title,
        plot_legend=rrb.PlotLegend(visible=legend, corner="RightBottom"),
        axis_x=rrb.TimeAxis(link="LinkToGlobal"),
        axis_y=None if y_range is None else rrb.ScalarAxis(range=y_range, zoom_lock=False),
    )  # fmt: skip


def _headroom(y_range: tuple[float, float], share: float = 0.1) -> tuple[float, float]:
    """A strip's range with ``share`` more room above its top tick, for the short strips of the Events tab."""
    return y_range[0], y_range[1] + share * (y_range[1] - y_range[0])


def _decade_range(low: float, high: float) -> tuple[float, float]:
    """A fixed y range for a strip robot_msgs lets Rerun scale (TCP position / orientation): the values, stretched on
    each side to the next round number (a multiple of the span's decade, then of the decade above) when it is within
    20 % of the span, plus 6 % air.

    WHY: the viewer labels only ticks a power of ten apart that are far enough apart on screen, so on a ~130 px strip
    the orientation (-828…+89°) read a single "0"; stretched to -1000 it reads 0 and -1000."""
    span = max(high - low, 1e-9)
    for decade in (10.0 ** np.floor(np.log10(span)), 10.0 ** np.ceil(np.log10(span))):
        below, above = np.floor(low / decade) * decade, np.ceil(high / decade) * decade
        low = below if low - below <= 0.2 * span else low
        high = above if above - high <= 0.2 * span else high
    air = 0.06 * (high - low) + 1e-3
    return float(low - air), float(high + air)


class _Marks:
    """The event lines a strip shows, by its y range: one entity per event per span class (a power of ten)."""

    def __init__(self, events: list[_Event]) -> None:
        self.events, self.used = events, set()

    @staticmethod
    def path(span: float, event: _Event) -> str:
        return f"/events/marks/{span:.0e}/{event.number}".replace("+", "")

    def at(self, y_range: tuple[float, float] | None) -> list[str]:
        if y_range is None:  # an autoscaled strip would scale to the line: none
            return []
        reach = max(abs(y_range[0]), abs(y_range[1]), 1e-9)
        span = float(10.0 ** (np.ceil(np.log10(reach)) + 1))
        self.used.add(span)
        return [self.path(span, event) for event in self.events]


def _lane(moves: bool) -> Any:
    """Rerun's state timeline on the plots' time axis: the numbered events (+ the moves between via points). No title
    bar: its rows name themselves (/events/moments, /events/moves), and in the Events tab the 28 px went to the table
    (WHY, the check: the run's 7th table row was cut off); in a joint tab the lane alone is ~45 px."""
    contents = ["/events/moments"] + (["/events/moves"] if moves else [])
    return rrb.StateTimelineView(origin="/events", contents=contents, name="events" + (" · moves" if moves else ""),
                                 titlebar=False, time_view=rrb.TimeAxis(link="LinkToGlobal"))


def _events_shares(events: list[_Event], notes: list[str], strips: int) -> list[float]:
    """The Events tab's row shares, in pixels of the 1600×1000 review layout (904 px of panels under the tab bar; the
    viewer splits them in proportion): the lanes, the log (a 20 px row per event), the table (a 23 px row per event,
    then its notes at ~128 characters and 15 px a line), and the strips share the rest. Measured on the frames (panel
    separators, both scenarios). WHY measured, not guessed (the check): with fixed shares the run's 7th row was cut."""
    lines = sum(-(-len(note.replace("*", "")) // 128) for note in notes)
    heights = [103.0, 84.0 + 20.0 * len(events),
               135.0 + 23.0 * len(events) + 15.0 * lines + 13.0 * max(len(notes) - 1, 0)]
    rest = max(904.0 - sum(heights), 100.0 * strips)
    return heights + [rest / strips] * strips


def _blueprint(plan: Any, events: list[_Event], marks: _Marks, target_plan: Any | None, extras: dict | None,
               speed: np.ndarray, notes: list[str]) -> Any:
    world_title = f"{plan.title} · {len(events)} events, the arm lit in each one's colour as it passes"
    world = rrb.Spatial3DView(origin="/", contents=[f"/world/{plan.part}/**"], name=world_title, eye_controls=plan.eye)

    # Events: the lane, the log (the index), the arm at each event, the tool speed (+ tool error) with event lines
    peak = float(speed.max())
    # WHY headroom: a ~100 px strip put its top tick label ("2000") half under the title bar
    speed_range = _headroom(viz._snap(0.0, max(peak, 1.0)))
    speed_strip = _plot(f"tool speed [mm/s] · peak {peak:.0f} · the {len(events)} events as lines",
                        [f"/tcp/speed_mm_s/{plan.part}", *marks.at(speed_range)], speed_range)
    log = rrb.TextLogView(origin="/events", contents=["/events/log"],
                          name="event log · the blue time cell is the playhead; click a time cell to jump there",
                          columns=rrb.TextLogColumns(timeline_columns=[TIMELINE], text_log_columns=["loglevel", "body"]),
                          format_options=rrb.TextLogFormat(monospace_body=False))  # fmt: skip
    table = rrb.TextDocumentView(origin="/events/table", name="the arm at each event · q [°] · ▶ = the latest event")
    events_parts = [_lane(True), log, table, speed_strip]
    tool_error = None  # a function, because one view object shown in two tabs is drawn in only one of them
    if target_plan is not None and extras is not None and extras.get("tool_error_mm") is not None:
        error = np.asarray(extras["tool_error_mm"], dtype=np.float64)
        rms = extras.get("rms_mm")
        title = f"tool error [mm] · the agent's ruler · worst {error.max():.2f}" + (f" · RMS {float(rms):.2f}" if rms else "")
        error_range = _headroom(viz._snap(0.0, float(error.max())))

        def tool_error(title: str = title, error_range: tuple[float, float] = error_range) -> Any:
            return _plot(title, ["/tool_error_mm", *marks.at(error_range)], error_range)

        events_parts.append(tool_error())
    shares = _events_shares(events, notes, strips=len(events_parts) - 3)
    tabs = [rrb.Vertical(*events_parts, row_shares=shares, name="Events")]

    # one tab per joint: q, qd, qdd, qddd stacked (+ the run's error), events as lines, the target under the run
    fields = [short for short in ("q", "qd", "qdd", "qddd") if short in plan.tabs]
    field_names = {short: field_name for short, _, field_name, _ in viz._FIELDS}
    for index, joint in enumerate(plan.joints):
        strips = []
        for short in fields:
            strip = plan.tabs[short][index]
            title = short + strip.title[len(joint):]  # "shoulder_pan_joint [°] · travel …" → "q [°] · travel …"
            contents = list(strip.contents)
            y_range = strip.y_range
            if target_plan is not None:
                contents.insert(0, f"/{field_names[short]}/{viz._part(joint)}/{_TARGET_PART}")
                title += " · target pale"
                # the target's own range too, so neither curve leaves the strip
                tvals = target_plan.signals[short][:, index] * plan.scale[index]
                low, high = (bound[index] * plan.scale[index] for bound in plan.limits[short])
                trange = viz._strip_range(tvals, low, high)
                y_range = (min(y_range[0], trange[0]), max(y_range[1], trange[1]))
            strips.append(_plot(title, contents + marks.at(y_range), y_range))
        if target_plan is not None:
            error = (plan.signals["q"][:, index] - target_plan.signals["q"][:, index]) * plan.scale[index]
            worst = int(np.argmax(np.abs(error)))
            span = max(float(np.abs(error).max()), 1e-3)
            error_range = viz._snap(-span, span)
            strips.append(_plot(f"q error, run − target [°] · worst {error[worst]:+.2f}° at {plan.seconds[worst]:.2f} s",
                                [f"/joint_error/{viz._part(joint)}", *marks.at(error_range)], error_range))
        tabs.append(rrb.Vertical(_lane(False), *strips, row_shares=[1.3] + [3.0] * len(strips),
                                 name=viz._short_joint(joint)))

    # All joints: his overview (robot_msgs' q / qd / qdd cards + the playhead table) first, then his per-derivative
    # tabs (robot_msgs' strips, events as lines), nested, so "All joints › q" is the stock q tab
    # (robot_msgs' layout of that tab, `_robot_dashboard`: the table over a grid of cards, rows shared joints + 5 : 8 per
    # card row; rebuilt here only to add the event lines to the cards)
    derivative_tabs = []
    for short in fields:
        derivative_tabs.append(rrb.Vertical(*(_plot(s.title, s.contents + marks.at(s.y_range), s.y_range)
                                              for s in plan.tabs[short]),
                                            name=short))
    all_joints = list(derivative_tabs)
    if plan.cards:
        columns = 1 if len(plan.cards) <= 3 else 2
        card_rows = -(-len(plan.cards) // columns)
        overview = rrb.Vertical(
            rrb.TextDocumentView(origin=f"/notes/{plan.part}", name="at the playhead"),
            rrb.Grid(*(_plot(c.title, c.contents + marks.at(c.y_range), c.y_range) for c in plan.cards), grid_columns=columns),
            row_shares=[len(plan.joints) + 5, 8 * card_rows], name="q / qd / qdd")  # fmt: skip
        all_joints.insert(0, overview)
    tabs.append(rrb.Tabs(*all_joints, active_tab=0, name="All joints"))

    # TCP: robot_msgs' four strips, + the run's tool error. WHY a fixed range on position / orientation too (robot_msgs
    # lets Rerun scale those two): an event line needs a fixed range to be clipped to
    tcp = []
    # WHY no legend there: it would list the event lines too; the title names the axis colours instead
    for strip, group in zip(plan.tabs["TCP"], ("position_mm", "orientation_deg", None, None), strict=True):
        y_range, title = strip.y_range, strip.title
        if y_range is None and group is not None:
            values = plan.tcp[group]
            low, high = float(values.min()), float(values.max())
            y_range = _decade_range(float(values.min()), float(values.max()))
            title = title.replace(" · x / y / z", " · x / y / z = red / green / blue")
            if group == "orientation_deg":
                # WHY rebuilt (the check): robot_msgs' title + the colour key ran past the strip's width and was cut
                # ("… near gimbal lock 1.05–1.12 s · t"); the frame is the position strip's, one row up
                title = f"TCP orientation [°] · roll / pitch / yaw = red / green / blue · ROS rpy, unwrapped{plan.gimbal}"
        tcp.append(_plot(title, strip.contents + marks.at(y_range), y_range))
    if tool_error is not None:
        tcp.append(tool_error())
    tabs.append(rrb.Vertical(*tcp, name="TCP"))

    return rrb.Blueprint(
        rrb.Horizontal(world, rrb.Tabs(*tabs, active_tab=0), column_shares=[1, 1]),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        rrb.TimePanel(state="collapsed", timeline=TIMELINE, play_state="paused", loop_mode="all"),
        collapse_panels=False,
    )


def _mount(traj: JointTrajectory, plan: Any) -> np.ndarray:
    """The tool's frame in the URDF's root frame (robot_msgs' own choice: its pose at the first sample), so the label
    layout projects the tool points through the blueprint's camera."""
    import rerun.urdf as rurdf

    tree = rurdf.UrdfTree.from_file_path(plan.urdf)
    if plan.tool_frame == tree.root_link().name:
        return np.eye(4)
    links = viz._forward_kinematics(tree, viz._joint_values(tree, traj), len(plan.seconds))
    return np.asarray(links[plan.tool_frame][0], dtype=np.float64)


# ── the one function ────────────────────────────────────────────────────────────────────────────────────────────


def save(path: str | Path, traj: JointTrajectory, *, robot: str | Path, tool: PoseTrajectory | None = None,
         target: JointTrajectory | None = None, target_tool: PoseTrajectory | None = None,
         extras: dict | None = None) -> str:
    """Write ``traj`` drawn on ``robot`` (a URDF) as V4's recording: events indexed, the right half by joint.

    ``target`` (+ ``target_tool``) is what ``traj`` tracked: its via points define the events, and every joint tab
    overlays it; ``extras`` may carry ``tool_error_mm`` (per sample: the worst-error event and the tool error strip),
    ``rms_mm``, and ``name`` / ``label`` (the run's name)."""
    extras = dict(extras or {})
    name = extras.get("name") or (str(extras["label"]).split(":")[0] if extras.get("label") else type(traj).__name__)
    plan = viz._RobotPlan(traj, name, robot, tool)
    target_plan = None if target is None else viz._RobotPlan(target, "target", robot, target_tool)
    events, notes, rest = _events(plan, target_plan, extras)
    speed = np.interp(plan.seconds, plan.tool_t, plan.tcp["speed_mm_s"])

    stream = rr.RecordingStream(APPLICATION_ID)
    # WHY default_blueprint at save (robot_msgs' save): written first, the file opens paused at t = 0
    marks = _Marks(events)
    stream.save(str(path), default_blueprint=_blueprint(plan, events, marks, target_plan, extras, speed, notes))
    # robot_msgs' own arm, series, limits, cards, TCP, playhead table and tool path; its start / end ghosts are off,
    # because start and end are two of the events here. The arm's static steel tint is filtered out (`_WithoutArmTint`)
    # and logged on the timeline instead (`_log_events`), so the arm itself lights up at each event
    arm = _copy_geometry(plan, "robot")[4]
    without_tint = _WithoutArmTint(stream, arm)
    viz._log_robot(traj, plan, without_tint, ghosts=False)
    viz._PATHS.pop(id(without_tint), None)
    if without_tint.dropped != set(arm):
        raise RuntimeError(f"robot_msgs' arm tint moved: filtered {sorted(without_tint.dropped)}, expected {sorted(arm)}")
    # the tool path's "start" / "end" dots would repeat the event labels: emptied
    stream.log(f"/world/{plan.part}/tool/ends", rr.Points3D(np.zeros((0, 3))), static=True)
    if target is not None:
        _log_target(plan, target_plan, target, stream)
    if extras.get("tool_error_mm") is not None:
        stream.log("/tool_error_mm", rr.SeriesLines(names="tool error", colors=_ERROR, widths=1.4), static=True)
        stream.send_columns("/tool_error_mm", indexes=[rr.TimeColumn(TIMELINE, duration=plan.seconds)],
                            columns=rr.Scalars.columns(scalars=np.asarray(extras["tool_error_mm"], dtype=np.float64)))
    _log_events(plan, events, rest, marks, stream, _mount(traj, plan), traj, arm)
    table_t, docs = _arm_table(plan, events, speed, notes)
    stream.send_columns("/events/table", indexes=[rr.TimeColumn(TIMELINE, duration=table_t)],
                        columns=rr.TextDocument.columns(text=docs, media_type=["text/markdown"] * len(docs)))
    viz._PATHS.pop(id(stream), None)
    stream.flush()
    stream.disconnect()
    for event in events:
        print(f"  [{event.kind}] {event.line}")
    return str(path)


def main() -> None:
    from fixture import URDF, plan, run

    traj, tool = plan()
    print(save(HERE / "plan-dev-029.rrd", traj, robot=URDF, tool=tool, extras={"name": "workspace-dev-029"}))
    target, solution, target_tool, solution_tool, extras = run("p6s")
    print(save(HERE / "run-dev-029.rrd", solution, robot=URDF, tool=solution_tool, target=target,
               target_tool=target_tool, extras={**extras, "name": "p6s on workspace-dev-029"}))


if __name__ == "__main__":
    main()
