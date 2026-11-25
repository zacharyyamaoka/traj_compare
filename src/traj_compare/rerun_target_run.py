"""Open in Rerun on a run that HAS a target: robot_msgs' stock arm for the run, with the target and its error on top.

    write_target_vs_run_rrd("run.rrd", run, target=planned, robot="ur5e.urdf", tool=run_tcp, target_tool=planned_tcp)

WHY (Zach, 2026-11-25, on the Rerun pick round docs/proposals/rerun-pick-variants-2026-11-24/): "when we are look at
just a normal trajectory without comparison than I think it makes sense to just keep with V1. that should basically
just be the stock like robot msg viz viewer for a joint trajectory". So a lone trajectory stays robot_msgs' V1
(``robot_msgs.viz.rerun`` with ``robot=``), and a run with its target is the round's V2 "Target vs run", the AI's pick
(91/100), which he did not object to. This module is that V2, grown from the round's v2/make.py.

It is V1 plus what a target adds, never a copy of V1: the run is logged by robot_msgs' own V1 logger (``_log_robot``,
the steel arm, its series, limits, cards, TCP, playhead table and tool path) and laid out by its own dashboard
(``_robot_dashboard``) over V1's own strips (``_RobotPlan``); this module adds

- the target as a wide pale line under every plot (entity part ``reference``, which sorts before ``run``: Rerun 0.40
  draws a plot's series in entity-path order, so the pale target lies UNDER the bold run);
- the run's deviation from the target ×N as a thin magenta skeleton (FEA style: the joint origins of the arm at
  target + N × (run − target), elbow → wrists → flange → tool point), an arrow from the target's tool point to the ×N
  one labelled "run ×N · TCP off X mm" (the TRUE offset), and the target's tool path dashed blue;
- an Error tab, first and open: the tool error in mm (the run's own ruler when given, else the TCP offset), each
  joint's error in degrees, and target vs run at the playhead.

No target arm is drawn: a tracked run is within a degree of its target, the same pose at this scale, and a second arm
z-fought the steel one (the round's first check). No ghosts: the start and end are the target path's own.

The recording's clock is V1's for the run: t = 0 is the run's first sample. The target is drawn on the same clock
(absolute times, ``header.stamp + t``), so a run that starts late is drawn late against its target; between samples,
and outside its span, the target is interpolated and held at its end poses.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import _files

try:
    import rerun as rr
    import rerun.blueprint as rrb

    # WHY robot_msgs' private V1 pieces (2026-11-25): V2 is V1 plus a target, so it is built on V1's plan, logger and
    # dashboard rather than on a copy of them; traj_compare's CI pins robot_msgs to a commit, so a rename there fails a
    # test here before it reaches a user
    from robot_msgs.viz import rerun as viz
except ModuleNotFoundError as error:  # the core report works without the SDK; only this module needs it
    if error.name != "rerun":
        raise
    rr = rrb = viz = None

from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

RUN, REFERENCE = "run", "reference"  # the entity parts: "reference" < "run", so the target draws under the run

# WHY these colours (calm UI, one meaning each): the run keeps V1's ink and steel; the target is one blue, pale in the
# plots and dashed for its tool path; the error is ONE magenta everywhere (the Error tab's line and shading, the 3D
# magnifier) so the eye links the two halves; no red or amber, nothing here is an alarm by itself
RUN_WIDTH = 2.0  # px; V1's default line is thin, and every title keys the run as "bold"
TARGET_PALE, TARGET_WIDTH = (160, 196, 236), 6.0  # a wide pale line under the bold one: reads as "rides the target"
TARGET_PATH = (60, 120, 220)
ERROR = (196, 40, 130)
# WHY full alpha: Rerun draws a Measurements band at about a quarter of its colour, so 55 was a haze nobody could see
ERROR_SHADE = (196, 40, 130, 255)
ERROR_SOFT = (225, 150, 195)
# the ×N skeleton. WHY these sizes (the round's second check): ~0.5 px per mm at the opening camera, so a 3.5 mm radius
# is a ~3.5 px line on a ~38 px forearm and a 9 mm sphere ~9 px; thin enough never to hide the steel, thick enough to
# follow at full frame (the arrow, 7 mm, stays the boldest magenta mark)
SKELETON_RADIUS = 0.0035  # m
SKELETON_JOINT_RADIUS = 0.009  # m
ARROW_RADIUS = 0.007  # m
JOINT_COLOURS = [(78, 154, 214), (242, 142, 43), (60, 170, 160), (120, 190, 90), (176, 112, 210), (205, 170, 40),
                 (255, 140, 160), (150, 120, 90)]
JOINT_COLOUR_NAMES = ["blue", "orange", "teal", "green", "purple", "gold", "pink", "brown"]  # for title keys
# the target's cards and TCP lines: the run's hues washed out, so a pale line is "the same quantity, the target"
_CARD_PALE = {"q": (165, 195, 238), "qd": (160, 214, 208), "qdd": (205, 205, 212)}
_AXIS_PALE = ((240, 170, 170), (165, 215, 175), (165, 185, 240))
# the magnified deviation's peak, as a share of the tool path's bounding radius. WHY 0.35 (the round: 0.15 gave ×20
# and a ~10 px arrow): ×50 on the UR5e tour, 176 mm drawn for 3.6 mm, a deformation seen at a glance
MAGNIFY_SHARE = 0.35
# the cap on the magnified joints: N × max |run − target| over every revolute joint and instant stays within this, N the
# largest 1-2-5 step that does. WHY (2026-11-25, the UR workbench check): the share above sizes N from the tool point
# alone, and a well-tuned run's joint errors cancel there (the UR5e sim run ctc_tuned_v2 r0 on workspace-dev-029: joints
# ≤ 0.04°, the tool 0.10 mm off), so it asked ×2000 and swung the elbow 77°: another pose, no longer a deformation of the
# arm. WHY 35° and not the 10-15° first proposed: the pick round's tour reads as a deformation at ×50 with its worst joint
# (wrist 2, 0.62°) 31° off and keeps ×50, which 15° would have made ×20; that sim run gets ×500, its elbow 19° off. A
# prismatic joint is not capped here: its slide moves the tool point one for one, which the share above already bounds
MAX_MAGNIFIED_DEG = 35.0
# below this peak deviation the run IS its target: nothing to magnify, so ×1 (a 1e-12 m peak gave ×1e10 otherwise)
SAME_POSE_M = 1e-6
# the magnifier's label sits off the arrow on a leader, at the first of a few places whose label box clears the start /
# end labels and the arrow on screen at the opening camera (the round's decision 6); the step is a share of the path
LABEL_LIFT_SHARE = 0.22
# Rerun's 3D label geometry at 1600 x 1000 (the review size), measured on the round's frames: the 3D view's centre and
# pixels per unit tan (Rerun's default 55° vertical field of view), a label's height, its gap under its point, and its
# width per character incl. padding
_VIEW_PX = (400.0, 517.0, 871.0)
_VIEW_BOX = (0.0, 62.0, 800.0, 968.0)
_LABEL_PX = {"height": 20.0, "gap": 3.0, "char": 6.7, "pad": 6.0, "margin": 5.0}


def _require() -> None:
    if rr is None:
        from .rerun_export import _require_sdk

        _require_sdk()


def _nice_factor(value: float) -> int:
    """The 1-2-5 number nearest ``value`` in log space (×10, ×20, ×50 ...), so the label reads like a scale bar."""
    if not np.isfinite(value) or value <= 1.0:
        return 1
    exponent = 10.0 ** np.floor(np.log10(value))
    candidates = [m * exponent for m in (1.0, 2.0, 5.0, 10.0)]
    return int(round(min(candidates, key=lambda c: abs(np.log(c / value)))))


def _nice_floor(value: float) -> int:
    """The largest 1-2-5 number at most ``value`` (×10, ×20, ×50 ...), at least 1: a cap's factor never exceeds it."""
    if not np.isfinite(value) or value < 2.0:
        return 1
    exponent = 10.0 ** np.floor(np.log10(value))
    return int(round(max(m * exponent for m in (1.0, 2.0, 5.0) if m * exponent <= value * (1.0 + 1e-12))))


def _on(t_from: np.ndarray, values: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """``values`` sampled at ``t_from`` onto ``t_to``, column by column; held at the end values outside ``t_from``."""
    values = np.asarray(values, dtype=np.float64)
    if len(t_from) == len(t_to) and np.allclose(t_from, t_to, rtol=0.0, atol=1e-12):
        return values
    flat = values.reshape(len(t_from), -1)
    out = np.stack([np.interp(t_to, t_from, flat[:, k]) for k in range(flat.shape[1])], axis=1)
    return out.reshape((len(t_to),) + values.shape[1:])


def _start(trajectory: Any) -> float:
    """The first sample on the header's clock (``header.stamp + t[0]``)."""
    return float(trajectory.header.stamp) + float(np.asarray(trajectory.t, dtype=np.float64)[0])


def _scalars(rec: Any, entity: str, t: np.ndarray, values: np.ndarray, *, names: Any, colours: Any, widths: Any) -> None:
    """One series entity on t; a (N, k) ``values`` is k instances of it (the legend reads them in order)."""
    values = np.asarray(values, dtype=np.float64)
    rec.log(entity, rr.SeriesLines(names=names, colors=colours, widths=widths), static=True)
    columns = rr.Scalars.columns(scalars=values.reshape(-1))
    if values.ndim > 1:
        columns = columns.partition([values.shape[1]] * len(t))
    rec.send_columns(entity, indexes=[rr.TimeColumn(viz.TIMELINE, duration=t)], columns=columns)


def _dashes(xyz: np.ndarray, dash_m: float) -> list[np.ndarray]:
    """A 3D polyline cut into dashes ``dash_m`` long with gaps as long (Rerun 0.40 has no dashed line style)."""
    if len(xyz) < 2:
        return [xyz]
    fine = np.vstack([np.linspace(a, b, 4, endpoint=False) for a, b in zip(xyz[:-1], xyz[1:])] + [xyz[-1:]])
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(fine, axis=0), axis=1))])
    on = (np.floor(s / dash_m).astype(int) % 2) == 0
    strips, start = [], None
    for k, flag in enumerate(on):
        if flag and start is None:
            start = k
        if (not flag or k == len(on) - 1) and start is not None:
            end = k if not flag else k + 1
            if end - start >= 2:
                strips.append(fine[start:end])
            start = None
    return strips


def _picked(count: int) -> np.ndarray:
    """The instants the per-instant entities are written at (V1's: at most ``_ROWS``; the latest holds between)."""
    last = count - 1
    return np.unique(np.linspace(0, last, min(last + 1, viz._ROWS)).round().astype(int))


class _TargetRun:
    """The run and its target: V1's two plans and everything V2 adds between them. Pure until ``log``."""

    def __init__(self, run: JointTrajectory, target: JointTrajectory, robot: str | Path, tool: PoseTrajectory | None,
                 target_tool: PoseTrajectory | None, *, label: str, tool_error_mm: Any, tool_error_rms_mm: float | None,
                 tool_error_name: str) -> None:  # fmt: skip
        if (tool is None) != (target_tool is None):
            raise ValueError("pass tool= and target_tool= together (or neither): the magnifier compares the two")
        joints = [str(joint) for joint in run.joint_names]
        if [str(joint) for joint in target.joint_names] != joints:
            if sorted(str(joint) for joint in target.joint_names) != sorted(joints):
                raise ValueError(f"the target's joints {list(target.joint_names)} are not the run's {joints}")
            target = target.select(joints)
        self.run, self.label = run, label
        self.s = viz._RobotPlan(run, RUN, robot, tool)
        self.t = viz._RobotPlan(target, REFERENCE, robot, target_tool)
        s, tt = self.s, self.t
        if s.tool_frame != tt.tool_frame:
            raise ValueError(f"tool frames differ: run {s.tool_frame!r}, target {tt.tool_frame!r}")
        # the target on the run's clock (V1's: t = 0 at the run's first sample), by absolute time
        self.shift = _start(target) - _start(run)
        self.seconds = s.seconds
        self.target_seconds = tt.seconds + self.shift
        self.target_tool_t = tt.tool_t + self.shift
        # 1. the joint error on the run's samples, SI and shown (degrees for revolute joints)
        self.target_on = {short: None if tt.signals[short] is None else _on(self.target_seconds, tt.signals[short],
                                                                             s.seconds)
                          for short in ("q", "qd", "qdd", "qddd")}  # fmt: skip
        self.dq = s.signals["q"] - self.target_on["q"]
        self.dq_shown = self.dq * s.scale
        # 2. the tool deviation at the tool point both plans carry, and N
        self.p_target = _on(self.target_tool_t, tt.tool_xyz, s.tool_t)
        self.dev = s.tool_xyz - self.p_target
        self.dev_mm = np.linalg.norm(self.dev, axis=1) * 1000.0
        self.path_radius = 0.5 * float(np.linalg.norm(np.ptp(s.tool_xyz, axis=0))) if len(s.tool_xyz) else 0.0
        peak = float(self.dev_mm.max()) / 1000.0 if len(self.dev_mm) else 0.0
        self.magnify = 1 if peak < SAME_POSE_M else _nice_factor(MAGNIFY_SHARE * self.path_radius / peak)
        # ... and no revolute joint magnified past MAX_MAGNIFIED_DEG (the labels name this N, the one drawn)
        revolute = [k for k, joint in enumerate(s.joints) if joint in s.revolute]
        joint_peak = float(np.abs(self.dq_shown[:, revolute]).max()) if revolute and len(self.dq_shown) else 0.0
        if np.isfinite(joint_peak) and joint_peak > 1e-9:  # below a nano-degree the joints ARE the target's
            self.magnify = min(self.magnify, _nice_floor(MAX_MAGNIFIED_DEG / joint_peak))
        # the tool point's distance from the flange, named wherever "TCP off" is read
        self.tool_offset_mm = (None if s.flange is None or len(s.flange) != len(s.tool_xyz) else
                               float(np.median(np.linalg.norm(s.tool_xyz - s.flange, axis=1))) * 1000.0)  # fmt: skip
        self._magnifier(run)
        # 3. the run's own ruler, when it carries one (a value per run sample), else the TCP offset stands in
        self.ruler = None
        if tool_error_mm is not None:
            ruler = np.asarray(tool_error_mm, dtype=np.float64).reshape(-1)
            if len(ruler) != len(s.seconds):
                raise ValueError(f"tool_error_mm needs one value per run sample ({len(s.seconds)}), got {len(ruler)}")
            self.ruler = ruler
        self.ruler_rms = None if tool_error_rms_mm is None else float(tool_error_rms_mm)
        self.ruler_name = tool_error_name
        self.v2_tabs = self._tabs()

    # ── the magnifier ──────────────────────────────────────────────────────────────────────────────────────────────

    def _magnifier(self, run: JointTrajectory) -> None:
        """The run magnified about the target, FEA's deformation scale: every joint at target + N × (run − target), drawn
        as a skeleton through its joint origins (see ``_skeleton``), and its tool point (the run's tool offset carried
        by the magnified flange).

        WHY joint space and not target tool + N × the tool's deviation: the magnified arm's own tool point then sits
        exactly at the arrow's tip (the Cartesian ×20 point drifted up to 7 mm off it on the round's run); the label
        carries the true TCP offset."""
        from rerun.urdf import UrdfTree

        s, n = self.s, self.magnify
        target_values = {k: _on(self.target_seconds, v, s.seconds) for k, v in self.t.values.items()}
        self.magnified_values = {k: target_values[k] + n * (v - target_values[k]) for k, v in s.values.items()
                                 if k in target_values}  # fmt: skip
        self.skeleton = self.skeleton_joints = None
        if s.tool_frame != s.root:  # a tool in a moving link's frame: the Cartesian scale is the honest fallback
            self.p_magnified = self.p_target + n * self.dev
            return
        tree = UrdfTree.from_file_path(str(s.urdf))
        tip = viz._tip_link(tree, run)
        links_m = viz._forward_kinematics(tree, self.magnified_values, len(s.seconds))
        links_t = viz._forward_kinematics(tree, target_values, len(s.seconds))
        # how far each magnified link gets from the target's (its frame or a child joint's origin, worst instant): the
        # skeleton starts at the first link that moves at least half as far as the farthest one (see `_skeleton`)
        moved = {}
        for link, pose_m in links_m.items():
            points = [np.zeros(3)] + [np.asarray(j.origin_xyz, dtype=np.float64) for j in tree.joints()
                                      if j.parent_link == link]  # fmt: skip
            pose_t = links_t[link]
            moved[link] = max(float(np.linalg.norm((pose_m[:, :3, :3] - pose_t[:, :3, :3]) @ point
                                                   + pose_m[:, :3, 3] - pose_t[:, :3, 3], axis=1).max())
                              for point in points)  # fmt: skip
        flange_s = viz._forward_kinematics(tree, s.values, len(s.seconds))[tip]
        flange_m = links_m[tip]
        tool_xyz = _on(s.tool_t, s.tool_xyz, s.seconds)
        offset = np.einsum("nji,nj->ni", flange_s[:, :3, :3], tool_xyz - flange_s[:, :3, 3])
        self.p_magnified = _on(s.seconds, flange_m[:, :3, 3] + np.einsum("nij,nj->ni", flange_m[:, :3, :3], offset),
                               s.tool_t)
        self._skeleton(tree, tip, links_m, moved)

    def _skeleton(self, tree: Any, tip: str, links_m: dict[str, np.ndarray], moved: dict[str, float]) -> None:
        """The ×N arm as a line through its joint origins, from the first link that really moves (the elbow on a UR5e
        at ×50) down to the flange, then out to the magnified tool point: ``self.skeleton`` (samples on tool_t, points,
        3) and ``self.skeleton_joints`` (the joint origins only, for the spheres).

        WHY from the first moving link: at ×50 the UR5e's base and shoulder move 0 mm and the upper arm 32 mm, so their
        part of a skeleton would run inside the steel and say nothing; the forearm moves 70 mm and the wrists 99 mm.
        WHY a joint's offset is routed along the link first, then along the child joint's axis: a URDF's joint origins
        sit on the joint axes, offset along them from the casting's centre line (the UR5e's wrist_1 is 133 mm along its
        axis from the forearm's line). A straight segment between two origins cut diagonally out of the forearm even at
        zero error; routed, the zero-error skeleton stays inside the steel, and only the deformation brings it out."""
        from robot_msgs.geometry.rotations import euler_to_matrix

        s = self.s
        parent_joint = {joint.child_link: joint for joint in tree.joints()}
        chain = [tip]
        while chain[-1] in parent_joint:
            chain.append(parent_joint[chain[-1]].parent_link)
        chain.reverse()  # root → tip
        far = max(moved.values()) if moved else 0.0
        first = next((link for link in chain if moved.get(link, 0.0) >= 0.5 * far > 0.0), chain[-1])
        chain = chain[chain.index(first):]
        points, joints = [links_m[first][:, :3, 3]], [0]
        for child in chain[1:]:
            joint = parent_joint[child]
            pose = links_m[joint.parent_link]
            offset = np.asarray(joint.origin_xyz, dtype=np.float64)
            if joint.joint_type != "fixed":
                axis = euler_to_matrix(*joint.origin_rpy) @ np.asarray(joint.axis, dtype=np.float64)
                along = float(offset @ axis) * axis
                across = offset - along
                if np.linalg.norm(along) > 1e-3 and np.linalg.norm(across) > 1e-3:  # the casting's corner
                    points.append(pose[:, :3, 3] + np.einsum("nij,j->ni", pose[:, :3, :3], across))
            if np.linalg.norm(offset) > 1e-3:
                points.append(links_m[child][:, :3, 3])
            if joint.joint_type != "fixed" and np.linalg.norm(offset) > 1e-3:
                joints.append(len(points) - 1)
        on_tool = _on(self.seconds, np.stack(points, axis=1), s.tool_t)
        self.skeleton = np.concatenate([on_tool, self.p_magnified[:, None, :]], axis=1)
        self.skeleton_joints = on_tool[:, joints]

    # ── the plots: V1's strips of the run, the target added under each ─────────────────────────────────────────────

    def _tabs(self) -> dict[str, list[Any]]:
        s, tt = self.s, self.t
        tabs: dict[str, list[Any]] = {}
        for short, tab, field_name, rate in viz._FIELDS:
            if s.signals[short] is None:
                continue
            strips = []
            for index, joint in enumerate(s.joints):
                strip = s._strip(short, field_name, rate, index)  # V1's strip, a fresh one
                target = self.target_on[short]
                if target is None:
                    strips.append(strip)
                    continue
                scale = s.scale[index]
                shown_s, shown_t = s.signals[short][:, index] * scale, target[:, index] * scale
                low, high = (bound[index] * scale for bound in s.limits[short])
                digits = 2 if short == "q" else 1 if short == "qd" else 0
                gap = float(np.nanmax(np.abs(shown_s - shown_t)))
                strip.title += f" · run − target ≤ {gap:.{digits}f}{s.unit(index, rate)}"
                strip.contents.insert(0, f"/{field_name}/{viz.path_part(joint)}/{tt.part}")
                strip.y_range = viz._strip_range(np.concatenate([shown_s, shown_t]), low, high)
                strip.legend = False
                strips.append(strip)
            # WHY the key in the first title, no legend (the round's check): a ~130 px strip's legend covered the first
            # joint's last half second. WHY "grey = limit" only where a strip of the tab draws one (qddd has no jerk
            # limit, so no grey line, and saying so there would be false)
            limits = any(entity.endswith(("/lower_limit", "/upper_limit")) for strip in strips
                         for entity in strip.contents)  # fmt: skip
            if self.target_on[short] is not None:
                strips[0].title += " · bold = run, pale = target" + (", grey = limit" if limits else "")
            tabs[tab] = strips
        if s.cards:
            cards = []
            for card in s.cards:
                entity = card.contents[0][: -len("/**")]
                joint_part = entity.split("/")[2]
                cards.append(viz._Strip(card.title, [f"/limit_pct/{joint_part}/{tt.part}/**", *card.contents],
                                        card.y_range))
            tabs["q / qd / qdd"] = cards
        tcp = []
        for strip in s.tabs["TCP"]:
            group = strip.contents[0].split("/")[2]
            contents = [f"/tcp/{group}/{tt.part}", *strip.contents]
            y_range = strip.y_range
            if y_range is not None:  # the speeds: one 0-based range over both
                top = max(float(s.tcp[group].max()), float(tt.tcp[group].max()), 1.0)
                y_range = viz._snap(0.0, top)
            # WHY the key in the title and no legend (the round's check): position and orientation listed six entries
            # and covered the last ~0.4 s; the key goes before the (long) source, which a half-width title cuts first
            marker = " · tool PoseTrajectory" if " · tool PoseTrajectory" in strip.title else " · FK of "
            source = strip.title.find(marker)
            head = strip.title[:source] if source >= 0 else strip.title
            tail = strip.title[source:] if source >= 0 else ""
            for listed, keyed in ((" · x / y / z", " · x red, y green, z blue"),
                                  (" · roll / pitch / yaw", " · roll red, pitch green, yaw blue")):
                head = head.replace(listed, keyed)
            if "orientation" in head:
                tail = ""  # WHY: at 148 characters it was cut at 1600 px; the position title above names the source
            else:
                head += " · bold = run, pale = target"
            tcp.append(viz._Strip(head + tail, contents, y_range, False))
        tabs["TCP"] = tcp
        return tabs

    def _error_strips(self) -> tuple[Any, Any, str]:
        """The Error tab's two plots (tool, joints) as V1 strips, and the tool plot's legend corner."""
        s = self.s
        off_at = float(self.seconds[int(np.argmax(self.dev_mm))])
        # WHY "TCP off" everywhere (the round's check): the 3D label said "true 3.3 mm" while the ruler read 2.05 mm at
        # the same instant: two "true" errors. They measure different things (a ruler is the run's own, at its tool
        # point; TCP off is the tool points' distance), so each keeps ONE name in the 3D label, this title and the table
        off = f"TCP off (pale) max {self.dev_mm.max():.2f} at {off_at:.2f} s"
        if self.ruler is not None:
            at = float(self.seconds[int(np.argmax(self.ruler))])
            rms = self.ruler_rms if self.ruler_rms is not None else float(np.sqrt(np.mean(self.ruler ** 2)))
            # WHY "the run's score" for a given RMS: it is the number the run is judged by, and the RMS of these samples
            # can differ from it (1.01 vs 1.09 mm on the round's run)
            score = " (the run's score)" if self.ruler_rms is not None else ""
            title = (f"Tool error [mm] · {self.ruler_name} (bold) RMS {rms:.2f}{score}, max {self.ruler.max():.2f} at "
                     f"{at:.2f} s · {off}")
            top = max(float(self.ruler.max()), float(self.dev_mm.max()))
        else:
            title = f"Tool error [mm] · {off.replace(' (pale)', '')} (the 3D label, drawn ×{self.magnify})"
            top = float(self.dev_mm.max())
        # the joints: no legend (it covered the last second); the title names the two worst by their line colour and
        # bounds the rest, and the playhead table names every joint by value
        worst = np.abs(self.dq_shown).max(axis=0)
        order = [int(k) for k in np.argsort(-worst)]
        units = {s.unit(k, "").strip() for k in range(len(s.joints))}
        unit = units.pop() if len(units) == 1 else ""
        named = []
        for k in order[:2]:
            row = int(np.argmax(np.abs(self.dq_shown[:, k])))
            named.append(f"{JOINT_COLOUR_NAMES[k % len(JOINT_COLOUR_NAMES)]} {viz._short_joint(s.joints[k])} "
                         f"{self.dq_shown[row, k]:+.2f}{s.unit(k, '').strip()} at {self.seconds[row]:.2f} s")
        rest = f" · the rest within ±{worst[order[2]]:.2f}{unit}" if len(order) > 2 else ""
        span = float(worst.max())
        bracket = f" [{unit}]" if unit else " [° or m]"
        joints = viz._Strip(f"Joint error, run − target{bracket} · " + " · ".join(named) + rest,
                            ["/error/joint/**"], viz._snap(-span, span), legend=False)
        tool = viz._Strip(title, ["/error/tool/**"], viz._snap(0.0, max(top, 1e-3)), legend=True)
        return tool, joints, "RightTop"  # WHY top right: a rest-to-rest run ends with both lines low

    def _error_tables(self) -> tuple[np.ndarray, list[str]]:
        """At the playhead: the tool error now, and each joint's target, run and difference."""
        s = self.s
        picked = _picked(len(self.seconds))
        qd_s, qd_t = s.signals["qd"], self.target_on["qd"]
        run_id = self.label.split(":", 1)[0]
        clock = ("" if abs(self.shift) < 1e-9 else
                 f" · t = 0 is the run's first sample, the target starts at {self.shift:+.3f} s")  # fmt: skip
        tables = []
        for k in picked:
            ruler = f"{self.ruler_name} **{self.ruler[k]:.2f} mm** · " if self.ruler is not None else ""
            lines = [f"**t = {self.seconds[k]:.2f} s** · {ruler}TCP off **{self.dev_mm[k]:.2f} mm** (the 3D label; "
                     f"arrow ×{self.magnify}) · {run_id}{clock}", "",
                     "| joint | target | run | run − target | qd run − target |", "|---|---:|---:|---:|---:|"]
            for index, joint in enumerate(s.joints):
                unit = s.unit(index, "").strip()
                scale = s.scale[index]
                dqd = "–" if qd_s is None or qd_t is None else f"{(qd_s[k, index] - qd_t[k, index]) * scale:+.2f}{unit}/s"
                lines.append(f"| {viz._short_joint(joint)} | {self.target_on['q'][k, index] * scale:+.2f}{unit} | "
                             f"{s.signals['q'][k, index] * scale:+.2f}{unit} | **{self.dq_shown[k, index]:+.3f}{unit}** | "
                             f"{dqd} |")
            tables.append("\n".join(lines))
        return self.seconds[picked], tables

    # ── the dashboard: V1's, over the strips above, with the Error tab first ──────────────────────────────────────

    def blueprint(self) -> Any:
        s = self.s
        revolute = [k for k, joint in enumerate(s.joints) if joint in s.revolute]
        # WHY this short (the round's check): the key was cut at "dashed ▸" in the half-width view at 1600 px. WHY "not
        # drawn": the target arm is within this many degrees of the run, the same pose at this scale
        off = (f" (arm ≤ {float(np.abs(self.dq_shown[:, revolute]).max()):.2f}° off, not drawn)" if revolute else "")
        shown = copy.copy(s)  # V1's dashboard reads the plan's title and tabs: give it V2's, leave the plan as it is
        shown.title = (f"steel = run · magenta skeleton = run ×{self.magnify} about the target · dashed blue = target "
                       f"path{off}")
        shown.tabs = self.v2_tabs
        stock = viz._robot_dashboard(shown, ghosts=False)
        world, tabs = stock.root_container.contents
        tool, joints, corner = self._error_strips()
        error = rrb.Vertical(_plot(tool, corner), _plot(joints),
                             rrb.TextDocumentView(origin="/notes/error", name="at the playhead: target vs run"),
                             row_shares=[4, 4, 3], name="Error")
        stock.root_container = rrb.Horizontal(world, rrb.Tabs(error, *tabs.contents, active_tab=0), column_shares=[1, 1])
        return stock

    # ── logging ────────────────────────────────────────────────────────────────────────────────────────────────────

    def log(self, rec: Any) -> None:
        s = self.s
        self._log_target(rec)
        # the run: V1's own logger (no ghosts), its playhead table's key naming the pale lines too
        table_t, tables = s.tables
        s.tables = (table_t, [table.replace("(the green band is ±100 %)", "(the green band is ±100 %); the same three, "
                                            "pale and wide, underneath = the target", 1) for table in tables])
        viz._log_robot(self.run, s, rec, ghosts=False)
        for short, _, field_name, _ in viz._FIELDS:  # "bold = run": V1's lines, widened in place
            if s.signals[short] is None:
                continue
            for joint in s.joints:
                rec.log(f"/{field_name}/{viz.path_part(joint)}/{s.part}", rr.SeriesLines.from_fields(widths=[RUN_WIDTH]),
                        static=True)
        self._log_error(rec)
        self._log_tool(rec)
        viz._PATHS.pop(id(rec), None)  # V1's registry is for its automatic dashboard; this one is embedded

    def _log_target(self, rec: Any) -> None:
        """The target's q / qd / qdd / qddd per joint, its cards and its TCP: pale and wide, on the run's clock."""
        tt = self.t
        for short, _, field_name, _ in viz._FIELDS:
            values = tt.signals[short]
            if values is None:
                continue
            for index, joint in enumerate(tt.joints):
                _scalars(rec, f"/{field_name}/{viz.path_part(joint)}/{tt.part}", self.target_seconds,
                         values[:, index] * tt.scale[index], names="target", colours=TARGET_PALE, widths=TARGET_WIDTH)
        for entity, names, _, widths, percent in tt.card_data:
            shorts = [name.split(" ", 1)[0] for name in names]
            _scalars(rec, entity, self.target_seconds, percent, names=[f"target {name}" for name in names],
                     colours=[_CARD_PALE[short] for short in shorts], widths=[width + 3.5 for width in widths])
        for group, axes in (("position_mm", ["x", "y", "z"]), ("orientation_deg", ["roll", "pitch", "yaw"])):
            _scalars(rec, f"/tcp/{group}/{tt.part}", self.target_tool_t, tt.tcp[group],
                     names=[f"target {axis}" for axis in axes], colours=list(_AXIS_PALE), widths=TARGET_WIDTH)
        for group in ("speed_mm_s", "angular_speed_deg_s"):
            _scalars(rec, f"/tcp/{group}/{tt.part}", self.target_tool_t, tt.tcp[group],
                     names="target " + group.split("_")[0], colours=TARGET_PALE, widths=TARGET_WIDTH)

    def _log_error(self, rec: Any) -> None:
        t = self.seconds
        primary = self.ruler if self.ruler is not None else self.dev_mm
        # WHY shaded: the area under the error is what the eye compares across the run (Measurements = the stock band;
        # its centre line at width 0: at err / 2 it read as a second, false error curve)
        rec.log("/error/tool/shade", rr.Measurements.from_fields(colors=[ERROR_SHADE], names=["area under the error"],
                                                                 widths=[0.0]), static=True)
        rec.send_columns("/error/tool/shade", indexes=[rr.TimeColumn(viz.TIMELINE, duration=t)],
                         columns=rr.Measurements.columns(values=0.5 * primary, variances=(0.5 * primary) ** 2))
        if self.ruler is not None:
            # WHY "fk_tcp_off": entity-path order is draw order, and f < r keeps this pale line under the bold ruler
            point = "" if self.tool_offset_mm is None else f", {self.tool_offset_mm:.0f} mm point"
            _scalars(rec, "/error/tool/fk_tcp_off", t, self.dev_mm, names=f"TCP off{point} = 3D label",
                     colours=ERROR_SOFT, widths=1.6)
        _scalars(rec, "/error/tool/ruler", t, primary,
                 names=self.ruler_name if self.ruler is not None else "TCP off = 3D label", colours=ERROR, widths=2.2)
        joints = self.s.joints
        _scalars(rec, f"/error/joint/{self.s.part}", t, self.dq_shown, names=[viz._short_joint(j) for j in joints],
                 colours=[JOINT_COLOURS[k % len(JOINT_COLOURS)] for k in range(len(joints))], widths=1.8)
        table_t, tables = self._error_tables()
        rec.send_columns("/notes/error", indexes=[rr.TimeColumn(viz.TIMELINE, duration=table_t)],
                         columns=rr.TextDocument.columns(text=tables, media_type=["text/markdown"] * len(tables)))

    def _log_tool(self, rec: Any) -> None:
        """The target's tool path (dashed) and, at the playhead, the ×N skeleton, the arrow from the target's tool point
        to the ×N one, its label on a leader, and the target's tool point. The run's own tool path is V1's."""
        s = self.s
        part = s.part
        frame = rr.CoordinateFrame(f"{part}/{s.tool_frame}")
        xyz = s.tool_xyz
        last = len(xyz) - 1
        picked = _picked(len(xyz))

        def thin(points: np.ndarray, first: int, end: int) -> np.ndarray:
            return points[np.unique(np.linspace(first, end, min(end - first + 1, viz._VERTICES)).round().astype(int))]

        at = [rr.TimeColumn(viz.TIMELINE, duration=s.tool_t[picked])]
        target_path = self.t.tool_xyz  # the target's whole path, every sample (it may outlast the run)
        rec.log(f"/world/{part}/target_tool/path", rr.LineStrips3D(_dashes(target_path, 0.012), colors=[TARGET_PATH],
                                                                   radii=[0.0032]), frame, static=True)  # fmt: skip
        n, magnified = self.magnify, self.p_magnified
        rec.log(f"/world/{part}/magnifier/path", rr.LineStrips3D([thin(magnified, 0, last)], colors=[ERROR_SOFT],
                                                                 radii=[0.0022]), frame, static=True)  # fmt: skip
        arrow = f"/world/{part}/magnifier/now"
        rec.log(arrow, rr.Arrows3D.from_fields(colors=[ERROR], radii=[ARROW_RADIUS]), frame, static=True)
        rec.send_columns(arrow, indexes=at, columns=rr.Arrows3D.columns(origins=self.p_target[picked],
                                                                        vectors=(magnified - self.p_target)[picked]))
        if self.skeleton is not None:
            bones = f"/world/{part}/magnifier/skeleton"
            rec.log(bones, rr.LineStrips3D.from_fields(colors=[ERROR], radii=[SKELETON_RADIUS]), frame, static=True)
            rec.send_columns(bones, indexes=at, columns=rr.LineStrips3D.columns(
                strips=[self.skeleton[row] for row in picked]))
            joints = f"/world/{part}/magnifier/joints"
            count = self.skeleton_joints.shape[1]
            rec.log(joints, rr.Points3D.from_fields(colors=[ERROR], radii=[SKELETON_JOINT_RADIUS]), frame, static=True)
            rec.send_columns(joints, indexes=at, columns=rr.Points3D.columns(
                positions=self.skeleton_joints[picked].reshape(-1, 3)).partition([count] * len(picked)))
        tip = f"/world/{part}/magnifier/tip"
        rec.log(tip, rr.Points3D.from_fields(colors=[ERROR], radii=[0.009]), frame, static=True)
        rec.send_columns(tip, indexes=at, columns=rr.Points3D.columns(positions=magnified[picked]))
        texts = [f"run ×{n} · TCP off {self.dev_mm[row]:.1f} mm" for row in picked]
        foot, anchor = _label_places(self, picked, texts, xyz[0], xyz[-1])
        leader = f"/world/{part}/magnifier/leader"
        rec.log(leader, rr.LineStrips3D.from_fields(colors=[ERROR_SOFT], radii=[0.0015]), frame, static=True)
        rec.send_columns(leader, indexes=at, columns=rr.LineStrips3D.columns(
            strips=[np.stack([foot[i], anchor[i]]) for i in range(len(picked))]))
        label = f"/world/{part}/magnifier/label"
        rec.log(label, rr.Points3D.from_fields(colors=[ERROR], radii=[0.004], show_labels=True), frame, static=True)
        rec.send_columns(label, indexes=at, columns=rr.Points3D.columns(positions=anchor, labels=texts))
        point = f"/world/{part}/target_tool/now"
        rec.log(point, rr.Points3D.from_fields(colors=[TARGET_PATH], radii=[0.007]), frame, static=True)
        rec.send_columns(point, indexes=at, columns=rr.Points3D.columns(positions=self.p_target[picked]))


def _plot(strip: Any, corner: str = "RightBottom") -> Any:
    """An Error-tab strip as a plot, as V1 draws its own (the global time axis, its y range, its legend)."""
    axis_y = rrb.ScalarAxis(range=strip.y_range, zoom_lock=False) if strip.y_range else None
    return rrb.TimeSeriesView(origin="/", contents=strip.contents, name=strip.title,
                              plot_legend=rrb.PlotLegend(visible=strip.legend, corner=corner),
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"), axis_y=axis_y)


# ── the magnifier's label: placed at the opening camera, off start / end and the arrow ─────────────────────────────


def _screen(eye: Any, points: np.ndarray) -> np.ndarray:
    """World points → pixels in the 3D view at the opening camera (pinhole, _VIEW_PX), (N, 2) x right, y down."""
    position = np.asarray(eye.position.as_arrow_array().to_pylist()[0], dtype=np.float64)
    look = np.asarray(eye.look_target.as_arrow_array().to_pylist()[0], dtype=np.float64)
    forward = (look - position) / np.linalg.norm(look - position)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    v = np.atleast_2d(points) - position
    depth = v @ forward
    cx, cy, k = _VIEW_PX
    return np.column_stack([cx + k * (v @ right) / depth, cy - k * (v @ up) / depth])


def _label_box(xy: np.ndarray, text: str) -> np.ndarray:
    """The screen box [x0, y0, x1, y1] Rerun draws a point's label in: centred under the point."""
    width = _LABEL_PX["char"] * len(text) + 2 * _LABEL_PX["pad"]
    top = xy[1] + _LABEL_PX["gap"]
    return np.array([xy[0] - width / 2, top, xy[0] + width / 2, top + _LABEL_PX["height"]])


def _overlap(a: np.ndarray, b: np.ndarray, margin: float) -> float:
    """Overlap area of two boxes, each grown by ``margin`` px (0 = clear by at least 2 × margin)."""
    w = min(a[2], b[2]) - max(a[0], b[0]) + 2 * margin
    h = min(a[3], b[3]) - max(a[1], b[1]) + 2 * margin
    return max(w, 0.0) * max(h, 0.0)


def _label_places(view: _TargetRun, picked: np.ndarray, texts: list[str], start: np.ndarray,
                  end: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per row, where the magnifier's label goes: (the leader's foot on the arrow, the label's point).

    Candidates, in order: above the arrow's upper end (one, then two steps up), beside it (left, right), below its lower
    end. The first whose label box clears the start / end labels and points, the arrow and the view's edge wins; the row
    before's pick is kept while it still clears (no flicker). WHY placed here: Rerun draws a point's label just under
    the point, with no placement control or collision avoidance. Measured at the opening camera at 1600 x 1000: an orbit
    moves the labels."""
    eye = view.s.eye
    step = LABEL_LIFT_SHARE * max(view.path_radius, 1e-3)
    margin = _LABEL_PX["margin"]
    fixed = []
    for point, text in ((start, "start"), (end, "end")):
        xy = _screen(eye, point)[0]
        fixed += [_label_box(xy, text), np.array([xy[0] - 7, xy[1] - 7, xy[0] + 7, xy[1] + 7])]
    position = np.asarray(eye.position.as_arrow_array().to_pylist()[0], dtype=np.float64)
    look = np.asarray(eye.look_target.as_arrow_array().to_pylist()[0], dtype=np.float64)
    side = np.cross(look - position, [0.0, 0.0, 1.0])
    side = side / np.linalg.norm(side) * 1.4 * step
    lift = np.array([0.0, 0.0, step])
    x0, y0, x1, y1 = _VIEW_BOX
    feet, anchors, last = [], [], None
    for i, row in enumerate(picked):
        ends = np.stack([view.p_target[row], view.p_magnified[row]])
        ends_xy = _screen(eye, ends)
        upper, lower = ends[int(np.argmin(ends_xy[:, 1]))], ends[int(np.argmax(ends_xy[:, 1]))]
        shaft = _screen(eye, np.linspace(ends[0], ends[1], 12))
        shaft_box = np.array([*shaft.min(axis=0) - 4, *shaft.max(axis=0) + 4])
        options = [(upper, upper + lift), (upper, upper + 2 * lift), (upper, upper + lift - side),
                   (upper, upper + lift + side), (lower, lower - 0.25 * lift), (lower, lower - lift)]

        def cost(option: tuple[np.ndarray, np.ndarray], text: str = texts[i], shaft_box: np.ndarray = shaft_box) -> float:
            box = _label_box(_screen(eye, option[1])[0], text)
            out = max(x0 - box[0], 0) + max(box[2] - x1, 0) + max(y0 - box[1], 0) + max(box[3] - y1, 0)
            return sum(_overlap(box, other, margin) for other in fixed) + _overlap(box, shaft_box, 0.0) + 100 * out

        costs = [cost(option) for option in options]
        pick = last if last is not None and costs[last] == 0.0 else \
            next((k for k, c in enumerate(costs) if c == 0.0), int(np.argmin(costs)))
        last = pick
        feet.append(options[pick][0])
        anchors.append(options[pick][1])
    return np.asarray(feet), np.asarray(anchors)


# ── the public entry points ─────────────────────────────────────────────────────────────────────────────────────────


def _view(run: JointTrajectory, target: JointTrajectory, robot: str | Path, tool: PoseTrajectory | None,
          target_tool: PoseTrajectory | None, label: str | None, tool_error_mm: Any, tool_error_rms_mm: float | None,
          tool_error_name: str) -> _TargetRun:  # fmt: skip
    _require()
    if not isinstance(run, JointTrajectory) or not isinstance(target, JointTrajectory):
        raise TypeError("run and target are JointTrajectory messages")
    run, target = _with_rates(run), _with_rates(target)
    return _TargetRun(run, target, robot, tool, target_tool, label=label or RUN, tool_error_mm=tool_error_mm,
                      tool_error_rms_mm=tool_error_rms_mm, tool_error_name=tool_error_name)


def target_vs_run_blueprint(run: JointTrajectory, *, target: JointTrajectory, robot: str | Path,
                            tool: PoseTrajectory | None = None, target_tool: PoseTrajectory | None = None,
                            label: str | None = None, tool_error_mm: Any = None, tool_error_rms_mm: float | None = None,
                            tool_error_name: str = "ruler") -> Any:  # fmt: skip
    """The dashboard ``write_target_vs_run_rrd`` embeds (same arguments), for a recording you make yourself."""
    return _view(run, target, robot, tool, target_tool, label, tool_error_mm, tool_error_rms_mm,
                 tool_error_name).blueprint()


def write_target_vs_run_rrd(
    path: Path | str,
    run: JointTrajectory,
    *,
    target: JointTrajectory,
    robot: str | Path,
    tool: PoseTrajectory | None = None,
    target_tool: PoseTrajectory | None = None,
    label: str | None = None,
    tool_error_mm: Sequence[float] | np.ndarray | None = None,
    tool_error_rms_mm: float | None = None,
    tool_error_name: str = "ruler",
    application_id: str | None = None,
    recording_id: str | None = None,
    recording_name: str | None = None,
) -> Path:
    """Write ``run`` against its ``target`` on the URDF ``robot`` as one .rrd with its dashboard inside (the module's
    docstring) and return its path. Opens paused at t = 0 on the Error tab. Velocities and accelerations either one does
    not carry are filled by np.gradient (``_with_rates``), so every one shows V1's q, qd, qdd and qddd tabs.

    - ``tool`` / ``target_tool``: each one's tool PoseTrajectory, in a URDF link's frame (``header.frame_id``; empty = the
      root link), on its trajectory's clock; both or neither (neither: the URDF's last link, by forward kinematics).
    - ``label``: the run's name in the titles and the playhead table (default ``"run"``).
    - ``tool_error_mm``: the run's own tool error, one value per run sample (a ruler that judges it); the Error tab's
      bold line, named ``tool_error_name``, with ``tool_error_rms_mm`` (its score) in the title. Without it the TCP
      offset (the tool points' distance) is the bold line.
    - ``application_id`` (default traj_compare's), ``recording_id``, ``recording_name``: the recording's identity in the
      viewer (one id per run, so re-opening it replaces it).
    """
    view = _view(run, target, robot, tool, target_tool, label, tool_error_mm, tool_error_rms_mm, tool_error_name)
    blueprint = view.blueprint()
    if application_id is None:
        from .rerun_export import APPLICATION_ID as application_id
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    recording = rr.RecordingStream(application_id, recording_id=recording_id)
    # WHY under a temporary name, renamed into place once whole (NAVIGATION.md D2), as every traj_compare .rrd
    with _files.replacing(path) as temporary:
        # WHY default_blueprint at save (robot_msgs' R4 finding): written first, the file opens paused at t = 0
        recording.save(str(temporary), default_blueprint=blueprint)
        recording.send_recording_name(recording_name or view.label)
        view.log(recording)
        recording.flush()
        recording.disconnect()
    return path


def _gradient(values: np.ndarray, t: np.ndarray) -> np.ndarray:
    from .analysis import _gradient as gradient

    return gradient(values, t)


def _with_rates(trajectory: JointTrajectory) -> JointTrajectory:
    """``trajectory`` with velocities and accelerations: each one it does not carry by np.gradient (``analysis._gradient``,
    as the report differentiates), the accelerations from the velocities it then has.

    WHY in ``_view``, so on every V2 path (2026-11-25, the UR workbench check): V1 draws a tab per signal the run carries
    (its qddd is the slope of qdd), and a sim run stored without accelerations showed 5 tabs from the runs workbench
    (``selection``, the run's npz as stored) and 7 from the dataset drill-down (``_joint`` differentiated it); one
    differentiator here, so a run shows the same tabs whichever writer opens it."""
    if len(trajectory.t) < 2 or (trajectory.velocities is not None and trajectory.accelerations is not None):
        return trajectory
    t = np.asarray(trajectory.t, dtype=np.float64)
    qd = (_gradient(np.asarray(trajectory.positions, dtype=np.float64), t) if trajectory.velocities is None
          else np.asarray(trajectory.velocities, dtype=np.float64))  # fmt: skip
    qdd = _gradient(qd, t) if trajectory.accelerations is None else np.asarray(trajectory.accelerations, dtype=np.float64)
    return trajectory.replace(velocities=qd, accelerations=qdd)


def _joint(situation: Any, joints: list[str], shift_s: float = 0.0) -> JointTrajectory:
    """A situation's samples as a JointTrajectory; qd and qdd by np.gradient when not recorded (``_with_rates``)."""
    t = np.asarray(situation.t, dtype=np.float64) - shift_s
    q = np.asarray(situation.q, dtype=np.float64)
    qd = None if situation.qd is None else np.asarray(situation.qd, dtype=np.float64)
    qdd = None if situation.qdd is None else np.asarray(situation.qdd, dtype=np.float64)
    return _with_rates(JointTrajectory(t=t, joint_names=tuple(joints), positions=q, velocities=qd, accelerations=qdd))


def _pose(situation: Any, shift_s: float, child: str) -> PoseTrajectory:
    from robot_msgs.geometry.rotations import quat_from_matrix

    matrices = np.asarray(situation.poses, dtype=np.float64)
    return PoseTrajectory(t=np.asarray(situation.t, dtype=np.float64) - shift_s, positions=matrices[:, :3, 3],
                          orientations=quat_from_matrix(matrices[:, :3, :3]), child_frame_id=child)


def comparison_inputs(comparison: Any) -> dict[str, Any] | None:
    """``write_target_vs_run_rrd``'s arguments for a comparison it can draw, else None.

    It can when the comparison is one target and ONE run with data (``reference_kind == "target"``), drawn on a URDF
    (``RobotDisplay.urdf`` of the run's robot, else the comparison's), with no video (this recording has no video
    panel, and a run's video is never dropped silently). The tool is each one's ``Situation.poses`` (in the URDF's
    root frame, ``RobotDisplay.urdf``'s contract) when both have them, else the URDF's last link. The run is taken
    shifted back by its ``time_offset_s``, as every error of the report is."""
    target = comparison.target
    runs = [situation for situation in comparison.situations if situation.t is not None and situation.q is not None]
    if target is None or target.t is None or target.q is None or len(runs) != 1:
        return None
    if getattr(comparison, "reference_kind", "target") != "target":
        return None
    if comparison.overlays or any(situation.video for situation in [target, *comparison.situations]):
        return None
    run = runs[0]
    display = run.robot or comparison.robot
    urdf = getattr(display, "urdf", None)
    if not urdf:
        return None
    joints = [str(joint) for joint in comparison.joint_names]
    shift = float(run.time_offset_s)
    inputs: dict[str, Any] = {
        "run": _joint(run, joints, shift), "target": _joint(target, joints), "robot": urdf, "label": run.title,
        "recording_id": comparison.name,
    }
    if target.poses is not None and run.poses is not None:
        child = comparison.tcp_frame or "tool"
        inputs["tool"], inputs["target_tool"] = _pose(run, shift, child), _pose(target, 0.0, child)
    return inputs
