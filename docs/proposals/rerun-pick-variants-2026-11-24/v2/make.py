#!/usr/bin/env python3
"""V2 · Target vs run: the agent's run solid steel, its deviation from the target drawn ×N as a magenta skeleton (FEA
style: the joint origins of target + N × (run − target), elbow → wrists → flange → TCP, labelled with N and the true
TCP offset), both tool paths (the target's dashed blue). The right half opens on an Error tab (the agent's own ruler in
mm with its RMS, the TCP offset the 3D label reads, and each joint's error in degrees), then V1's six tabs, every plot
overlaying the target (a wide pale line) under the solution (a bold ink line).

WHY no target arm (after the check, 2026-11-24): the target is within 0.62° of the run, so a second arm sat on the steel
one and z-fought (mottled stripes that read as a rendering bug); at this scale it is the same pose, and the title says
so. The ×N skeleton is what shows the difference.

WHY a skeleton and not a ×N arm of meshes (after the second check, 2026-11-24): even faded, the translucent pink ×50
links lay over the steel run arm from the opening camera for 16 of the 33 hero frames, tinting up to 34 % of its pixels
mauve at 1.3-1.6 s. A ~3 px line with small joint spheres covers a sliver of the arm, and where the deviation is small
it sits inside the steel casting and the depth test hides it, so steel reads as steel.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v2/make.py

Writes v2/plan-dev-029.rrd (fixture.plan(): no target, so one arm and the six tabs) and v2/run-dev-029.rrd
(fixture.run("p6s"): traj = the solution, target = the target). Entry point:

    save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None)

Grows from robot_msgs.viz.rerun (main): `_RobotPlan` works out each trajectory's signals, strips, cards, TCP and camera,
`_urdf_copy` loads each arm, `band` shades the error; nothing in robot_msgs is edited. WHY two plans and not one: each
trajectory keeps its own signals (the solution's qd/qdd are differences of encoder positions, the target's are the
planner's own), so the overlay shows the real difference, noise included.
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
from fixture import URDF, plan, run  # noqa: E402

from robot_msgs.trajectory import JointTrajectory, PoseTrajectory  # noqa: E402
from robot_msgs.viz import rerun as viz  # noqa: E402

APPLICATION_ID = "rerun_pick_v2"
T = viz.TIMELINE
_part = viz.path_part

# WHY these colours (calm UI, one meaning each): the solution keeps V1's ink and steel; the target is one blue, pale in
# the plots and dashed for its tool path; the error is ONE magenta everywhere (the Error tab's line and shading, the 3D
# magnifier) so the eye links the two halves; no red/amber, nothing here is an alarm by itself.
SOLUTION_INK, SOLUTION_WIDTH = viz._INK, 2.0
TARGET_PALE, TARGET_WIDTH = (160, 196, 236), 6.0  # a wide pale line under the bold one: reads as "rides the target"
TARGET_PATH = (60, 120, 220)
ERROR = (196, 40, 130)
# WHY full alpha (was 55): Rerun draws a Measurements band at about a quarter of its colour, so 55 was a pink haze the
# checker could barely see at full frame and 120 still only (249, 235, 243) on white; 255 gives (243, 212, 230)
ERROR_SHADE = (196, 40, 130, 255)
ERROR_SOFT = (225, 150, 195)
# the ×N skeleton: one magenta line through the magnified arm's joint origins and small spheres at the joints, in the
# error's one magenta. WHY these sizes (after the second check): ~0.5 px per mm at the opening camera, so a 3.5 mm
# radius is a ~3.5 px line on a ~38 px forearm and a 9 mm sphere is ~9 px; thin enough never to hide the steel, thick
# enough to follow at full frame (the arrow, 7 mm, stays the boldest magenta mark)
SKELETON_RADIUS = 0.0035  # m
SKELETON_JOINT_RADIUS = 0.009  # m
ARROW_RADIUS = 0.007  # m; 0.0035 drew a ~10 px hairline at full frame
JOINT_COLOURS = [(78, 154, 214), (242, 142, 43), (60, 170, 160), (120, 190, 90), (176, 112, 210), (205, 170, 40),
                 (255, 140, 160), (150, 120, 90)]
JOINT_COLOUR_NAMES = ["blue", "orange", "teal", "green", "purple", "gold", "pink", "brown"]  # for title keys
# the target's cards and TCP lines: the solution's hues washed out, so a pale line is "the same quantity, the target"
_CARD_PALE = {"q": (165, 195, 238), "qd": (160, 214, 208), "qdd": (205, 205, 212)}
_AXIS_PALE = ((240, 170, 170), (165, 215, 175), (165, 185, 240))
_ROWS = viz._ROWS
# the magnified deviation's peak, as a share of the tool path's bounding radius. WHY 0.35 (was 0.15, ×20 here): the
# ×20 arrow was ~10 px at full frame; 0.35 gives ×50 (peak 181 mm drawn for 3.6 mm), a deformation you see at a glance
MAGNIFY_SHARE = 0.35
# the magnifier's label sits off the arrow on a leader, at the first of a few places (above the arrow, higher, beside,
# below) whose label box clears the start / end labels and the arrow on screen at the view's opening camera. WHY: on
# the tool point it covered start / end at 0 s and 3.2 s (the deviation is ~0 there) and start at 1.4 s; a fixed lift
# off the arrow's top still landed on start at 1.2 s. LABEL_LIFT_SHARE is the step, a share of the path radius
LABEL_LIFT_SHARE = 0.22
# Rerun's 3D label geometry at 1600 x 1000 (the review size), measured on the first build's frames: the 3D view's
# centre and pixels per unit tan (Rerun's default 55° vertical field of view: 453 px / tan 27.5° = 871, fitted to 1 px
# on four known points), a label's height, its gap under its point, and its width per character incl. padding
_VIEW_PX = (400.0, 517.0, 871.0)
_VIEW_BOX = (0.0, 62.0, 800.0, 968.0)
_LABEL_PX = {"height": 20.0, "gap": 3.0, "char": 6.7, "pad": 6.0, "margin": 5.0}


def _nice_factor(value: float) -> int:
    """The 1-2-5 number nearest `value` in log space (×10, ×20, ×50 ...), so the label reads like a scale bar."""
    if not np.isfinite(value) or value <= 1.0:
        return 1
    exponent = 10.0 ** np.floor(np.log10(value))
    candidates = [m * exponent for m in (1.0, 2.0, 5.0, 10.0)]
    return int(min(candidates, key=lambda c: abs(np.log(c / value))))


def _on(t_from: np.ndarray, values: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """`values` sampled at `t_from` onto `t_to`, column by column (identity when the clocks already agree)."""
    values = np.asarray(values, dtype=np.float64)
    if len(t_from) == len(t_to) and np.allclose(t_from, t_to):
        return values
    flat = values.reshape(len(t_from), -1)
    out = np.stack([np.interp(t_to, t_from, flat[:, k]) for k in range(flat.shape[1])], axis=1)
    return out.reshape((len(t_to),) + values.shape[1:])


def _scalars(rec: rr.RecordingStream, entity: str, t: np.ndarray, values: np.ndarray, *, names: Any, colours: Any,
             widths: Any) -> None:
    """One series entity on t; a (N, k) `values` is k instances of it (the legend reads them in order)."""
    values = np.asarray(values, dtype=np.float64)
    rec.log(entity, rr.SeriesLines(names=names, colors=colours, widths=widths), static=True)
    columns = rr.Scalars.columns(scalars=values.reshape(-1))
    if values.ndim > 1:
        columns = columns.partition([values.shape[1]] * len(t))
    rec.send_columns(entity, indexes=[rr.TimeColumn(T, duration=t)], columns=columns)


def _dashes(xyz: np.ndarray, dash_m: float) -> list[np.ndarray]:
    """A 3D polyline cut into dashes `dash_m` long with gaps as long (Rerun 0.40 has no dashed line style)."""
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


class _Run:
    """The solution (traj) and, optionally, its target: the two `_RobotPlan`s and everything V2 adds between them."""

    def __init__(self, traj: JointTrajectory, robot: str | Path, tool: PoseTrajectory | None,
                 target: JointTrajectory | None, target_tool: PoseTrajectory | None, extras: dict | None) -> None:
        self.extras = dict(extras or {})
        self.label = str(self.extras.get("label") or ("solution" if target is not None else "plan"))
        self.s = viz._RobotPlan(traj, "solution" if target is not None else "plan", robot, tool)
        self.t: viz._RobotPlan | None = None
        if target is not None:
            if [str(j) for j in target.joint_names] != self.s.joints:
                raise ValueError(f"target joints {target.joint_names} differ from the solution's {self.s.joints}")
            # WHY the entity name "reference" (the legend still reads "target"): Rerun 0.40 draws a plot's series in
            # entity-path order, and "reference" < "solution", so the pale target lies UNDER the bold run (named
            # "target", it was drawn on top and hid the run in every strip; log order and contents order do not count)
            self.t = viz._RobotPlan(target, "reference", robot, target_tool)
            if (tool is None) != (target_tool is None):
                raise ValueError("pass tool= and target_tool= together (or neither): the magnifier compares the two")
        s = self.s
        self.seconds = s.seconds
        if self.t is None:
            return
        tt = self.t
        # 1. the joint error on the solution's clock, SI and shown (degrees for revolute joints)
        q_target = _on(tt.seconds, tt.signals["q"], s.seconds)
        self.dq = s.signals["q"] - q_target
        self.dq_shown = self.dq * s.scale
        self.target_on = {short: (None if tt.signals[short] is None else _on(tt.seconds, tt.signals[short], s.seconds))
                          for short in ("q", "qd", "qdd", "qddd")}  # fmt: skip
        # 2. the tool deviation at the tool point both plans carry (FK of the dataset's tool point here), and N
        if s.tool_frame != tt.tool_frame:
            raise ValueError(f"tool frames differ: solution {s.tool_frame!r}, target {tt.tool_frame!r}")
        self.p_target = _on(tt.tool_t, tt.tool_xyz, s.tool_t)
        self.dev = s.tool_xyz - self.p_target
        self.dev_mm = np.linalg.norm(self.dev, axis=1) * 1000.0
        radius = 0.5 * float(np.linalg.norm(np.ptp(s.tool_xyz, axis=0)))
        self.path_radius = radius
        peak = max(float(self.dev_mm.max()) / 1000.0, 1e-9)
        self.magnify = _nice_factor(MAGNIFY_SHARE * radius / peak)
        # the tool point's distance from the flange (the dataset's 145 mm point here), named wherever "TCP off" is read
        self.tool_offset_mm = (None if s.flange is None or len(s.flange) != len(s.tool_xyz) else
                               float(np.median(np.linalg.norm(s.tool_xyz - s.flange, axis=1))) * 1000.0)  # fmt: skip
        self._magnifier(robot, traj)
        # 3. the agent's own ruler, when the run carries it (per solution sample), else the FK deviation stands in
        ruler = self.extras.get("tool_error_mm")
        self.ruler = None if ruler is None or len(ruler) != len(s.seconds) else np.asarray(ruler, dtype=np.float64)
        self.ruler_rms = self.extras.get("rms_mm")

    def _magnifier(self, robot: str | Path, traj: JointTrajectory) -> None:
        """The run magnified about the target, FEA's deformation scale: every joint at target + N × (run − target), drawn
        as a skeleton through its joint origins (see `_skeleton`), and its tool point (the solution's tool offset carried
        by the magnified flange).

        WHY joint space and not target tool + N × the tool's deviation: the magnified arm's own tool point then sits
        exactly at the arrow's tip (the Cartesian ×20 point drifted up to 7 mm off it on this run); the label carries
        the true TCP offset."""
        from rerun.urdf import UrdfTree

        s, tt, n = self.s, self.t, self.magnify
        target_values = {k: _on(tt.seconds, v, s.seconds) for k, v in tt.values.items()}
        self.target_values = target_values
        self.magnified_values = {k: target_values[k] + n * (v - target_values[k]) for k, v in s.values.items()
                                 if k in target_values}  # fmt: skip
        self.skeleton = self.skeleton_joints = None
        if s.tool_frame != s.root:  # a tool in a moving link's frame: the Cartesian scale is the honest fallback
            self.p_magnified = self.p_target + n * self.dev
            return
        tree = UrdfTree.from_file_path(str(s.urdf))
        tip = viz._tip_link(tree, traj)
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
        self.magnified_moved = moved
        flange_s = viz._forward_kinematics(tree, s.values, len(s.seconds))[tip]
        flange_m = links_m[tip]
        tool_xyz = _on(s.tool_t, s.tool_xyz, s.seconds)
        offset = np.einsum("nji,nj->ni", flange_s[:, :3, :3], tool_xyz - flange_s[:, :3, 3])
        self.p_magnified = _on(s.seconds, flange_m[:, :3, 3] + np.einsum("nij,nj->ni", flange_m[:, :3, :3], offset),
                               s.tool_t)
        self._skeleton(tree, tip, links_m, moved)

    def _skeleton(self, tree: Any, tip: str, links_m: dict[str, np.ndarray], moved: dict[str, float]) -> None:
        """The ×N arm as a line through its joint origins, from the first link that really moves (the elbow on a UR5e
        at ×50) down to the flange, then out to the magnified tool point: `self.skeleton` (samples on tool_t, points,
        3) and `self.skeleton_joints` (the joint origins only, for the spheres).

        WHY from the first moving link: at ×50 the base and shoulder move 0 mm and the upper arm 32 mm, so their part of
        a skeleton would run inside the steel and say nothing; the forearm moves 70 mm and the wrists 99 mm.
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
        self.skeleton_links = chain

    # ── the plots: the solution's strips, the target added under each ──────────────────────────────────────────────

    def tabs(self) -> dict[str, list[viz._Strip]]:
        s, tt = self.s, self.t
        if tt is None:
            return s.tabs
        tabs: dict[str, list[viz._Strip]] = {}
        for short, tab, field_name, rate in viz._FIELDS:
            if s.signals[short] is None:
                continue
            strips = []
            for index, joint in enumerate(s.joints):
                strip = s._strip(short, field_name, rate, index)
                target = self.target_on[short]
                if target is None:
                    strips.append(strip)
                    continue
                scale = s.scale[index]
                shown_s, shown_t = s.signals[short][:, index] * scale, target[:, index] * scale
                low, high = (bound[index] * scale for bound in s.limits[short])
                digits = 2 if short == "q" else 1 if short == "qd" else 0
                unit = s.unit(index, rate)
                gap = float(np.nanmax(np.abs(shown_s - shown_t)))
                strip.title += f" · run − target ≤ {gap:.{digits}f}{unit}"
                strip.contents.insert(0, f"/{field_name}/{_part(joint)}/{tt.part}")
                strip.y_range = viz._strip_range(np.concatenate([shown_s, shown_t]), low, high)
                strip.legend = False
                strips.append(strip)
            # WHY the key in the first title, no legend (after the check): a ~130 px strip's legend (limit, target,
            # solution) covered the first joint's last half second; the title has room and covers nothing. WHY "grey =
            # limit" (after the second check): the legend named the grey limit lines and the title key had dropped
            # them; said only where a strip of the tab draws one (qddd has no jerk limit, so no grey line)
            limits = any(entity.endswith(("/lower_limit", "/upper_limit")) for strip in strips
                         for entity in strip.contents)  # fmt: skip
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
            # WHY the key in the title and no legend (after the check): position and orientation listed six entries
            # (x, y, z and their targets) and covered the last ~0.4 s; the key goes before the (long) source, which
            # the half-width title cuts first
            source = strip.title.find(" · tool PoseTrajectory") if " · tool PoseTrajectory" in strip.title \
                else strip.title.find(" · FK of ")
            head = strip.title[:source] if source >= 0 else strip.title
            tail = strip.title[source:] if source >= 0 else ""
            for listed, keyed in ((" · x / y / z", " · x red, y green, z blue"),
                                  (" · roll / pitch / yaw", " · roll red, pitch green, yaw blue")):
                head = head.replace(listed, keyed)
            if "orientation" in head:
                # WHY no source here (after the second check): at 148 characters the title was cut at 1600 px; the
                # position title above names the same tool PoseTrajectory, and its key (bold / pale) covers this one
                tail = ""
            else:
                # WHY the key on position, speed and angular speed (after the second check): the speeds are a bold
                # line over a pale one with nothing to say which is which; orientation has no room left for it
                head += " · bold = run, pale = target"
            tcp.append(viz._Strip(head + tail, contents, y_range, False))
        tabs["TCP"] = tcp
        return tabs

    def error_strips(self) -> list[viz._Strip]:
        s = self.s
        off_at = float(self.seconds[int(np.argmax(self.dev_mm))])
        # WHY "TCP off" everywhere (after the check): the 3D label said "true 3.3 mm" while this tab's ruler read
        # 2.05 mm at the same instant: two "true" errors. They measure different things (the ruler is the agent's
        # own, at its tool point; TCP off is FK at the dataset's tool point), so each keeps ONE name in the 3D label,
        # this title, the legend and the table
        off = f"TCP off (pale) max {self.dev_mm.max():.2f} at {off_at:.2f} s"
        if self.ruler is not None:
            at = float(self.seconds[int(np.argmax(self.ruler))])
            rms = self.ruler_rms if self.ruler_rms is not None else float(np.sqrt(np.mean(self.ruler ** 2)))
            # WHY "its score": rms_mm is the agent's own number for the task; the RMS of these samples can differ
            # (1.01 mm here), and the title shows the number the agent is judged by
            title = (f"Tool error [mm] · ruler (bold) RMS {rms:.2f} (the agent's score), max {self.ruler.max():.2f} at "
                     f"{at:.2f} s · {off}")
            top = max(float(self.ruler.max()), float(self.dev_mm.max()))
        else:
            title = f"Tool error [mm] · {off.replace(' (pale)', '')} (the 3D label, drawn ×{self.magnify})"
            top = float(self.dev_mm.max())
        # the joints: no legend (six entries covered wrist_1 / wrist_2 after ~2.95 s, after the check); the title names
        # the two worst by their line colour and bounds the rest, the playhead table names every joint by value
        worst = np.abs(self.dq_shown).max(axis=0)
        order = [int(k) for k in np.argsort(-worst)]
        unit = s.unit(order[0], "").strip()
        named = []
        for k in order[:2]:
            row = int(np.argmax(np.abs(self.dq_shown[:, k])))
            named.append(f"{JOINT_COLOUR_NAMES[k % len(JOINT_COLOUR_NAMES)]} {viz._short_joint(s.joints[k])} "
                         f"{self.dq_shown[row, k]:+.2f}{unit} at {self.seconds[row]:.2f} s")
        rest = f" · the rest within ±{worst[order[2]]:.2f}{unit}" if len(order) > 2 else ""
        span = float(worst.max())
        joints = viz._Strip(f"Joint error, run − target [{unit}] · " + " · ".join(named) + rest,
                            ["/error/joint/**"], viz._snap(-span, span), legend=False)
        tool = viz._Strip(title, ["/error/tool/**"], viz._snap(0.0, max(top, 1e-3)), legend=True)
        tool.corner = "RightTop"  # WHY: after ~2.4 s both lines stay under 1.6 mm, so the top right is empty
        return [tool, joints]

    def error_tables(self) -> tuple[np.ndarray, list[str]]:
        """At the playhead: the tool error now, and each joint's target, solution and difference."""
        s = self.s
        last = len(self.seconds) - 1
        picked = np.unique(np.linspace(0, last, min(last + 1, _ROWS)).round().astype(int))
        qd_s, qd_t = s.signals["qd"], self.target_on["qd"]
        tables = []
        run_id = self.label.split(":", 1)[0]
        for k in picked:
            ruler = f"ruler **{self.ruler[k]:.2f} mm** · " if self.ruler is not None else ""
            lines = [f"**t = {self.seconds[k]:.2f} s** · {ruler}TCP off **{self.dev_mm[k]:.2f} mm** (the 3D label; "
                     f"arrow ×{self.magnify}) · {run_id}", "",
                     "| joint | target | solution | run − target | qd run − target |", "|---|---:|---:|---:|---:|"]
            for index, joint in enumerate(s.joints):
                unit = s.unit(index, "").strip()
                scale = s.scale[index]
                dqd = "–" if qd_s is None or qd_t is None else f"{(qd_s[k, index] - qd_t[k, index]) * scale:+.2f}{unit}/s"
                lines.append(f"| {viz._short_joint(joint)} | {self.target_on['q'][k, index] * scale:+.2f}{unit} | "
                             f"{s.signals['q'][k, index] * scale:+.2f}{unit} | **{self.dq_shown[k, index]:+.3f}{unit}** | "
                             f"{dqd} |")
            tables.append("\n".join(lines))
        return self.seconds[picked], tables


# ── logging ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _log_series(rec: rr.RecordingStream, plan: viz._RobotPlan, *, target: bool) -> None:
    """q / qd / qdd / qddd per joint, the cards and the TCP of one plan: bold ink for the solution, pale for a target."""
    t = plan.seconds
    colour, width = (TARGET_PALE, TARGET_WIDTH) if target else (SOLUTION_INK, SOLUTION_WIDTH)
    name = "target" if target else plan.name
    for short, _, field_name, _ in viz._FIELDS:
        values = plan.signals[short]
        if values is None:
            continue
        for index, joint in enumerate(plan.joints):
            _scalars(rec, f"/{field_name}/{_part(joint)}/{plan.part}", t, values[:, index] * plan.scale[index],
                     names=name, colours=colour, widths=width)
    for entity, names, colours, widths, percent in plan.card_data:
        if target:
            shorts = [n.split(" ", 1)[0] for n in names]
            colours = [_CARD_PALE[short] for short in shorts]
            widths = [w + 3.5 for w in widths]
            names = [f"target {n}" for n in names]
        _scalars(rec, entity, t, percent, names=names, colours=colours, widths=widths)
        if not target:
            viz.band(f"{entity}/limit", [0.0, float(t[-1])], -100.0, 100.0, recording=rec, color=viz._CARD_BAND,
                     name="limit ±100 %")
    for group, axes in (("position_mm", ["x", "y", "z"]), ("orientation_deg", ["roll", "pitch", "yaw"])):
        colours = list(_AXIS_PALE if target else viz._AXIS_COLORS)
        names = [f"target {a}" for a in axes] if target else axes
        _scalars(rec, f"/tcp/{group}/{plan.part}", plan.tool_t, plan.tcp[group], names=names, colours=colours,
                 widths=TARGET_WIDTH if target else 1.6)
    for group, colour in (("speed_mm_s", viz._ACCENT), ("angular_speed_deg_s", viz._INK)):
        _scalars(rec, f"/tcp/{group}/{plan.part}", plan.tool_t, plan.tcp[group],
                 names=("target " if target else "") + group.split("_")[0],
                 colours=TARGET_PALE if target else colour, widths=TARGET_WIDTH if target else 1.6)


def _log_limits(rec: rr.RecordingStream, plan: viz._RobotPlan) -> None:
    """Two grey lines per joint and field, in the strip's units (V1's)."""
    ends = [rr.TimeColumn(T, duration=[plan.seconds[0], plan.seconds[-1]])]
    for short, _, field_name, _ in viz._FIELDS:
        if plan.signals[short] is None:
            continue
        for index, joint in enumerate(plan.joints):
            for side, bound in zip(("lower_limit", "upper_limit"), plan.limits[short], strict=True):
                value = float(bound[index] * plan.scale[index])
                if np.isfinite(value):
                    entity = f"/{field_name}/{_part(joint)}/{side}"
                    rec.log(entity, rr.SeriesLines(colors=[viz._LIMIT], widths=[1.0], names=[side.replace("_", " ")]),
                            static=True)
                    rec.send_columns(entity, indexes=ends, columns=rr.Scalars.columns(scalars=[value, value]))


def _log_arm(rec: rr.RecordingStream, plan: viz._RobotPlan, copy: str, colour: Any, values: dict[str, np.ndarray],
             seconds: np.ndarray) -> None:
    """One URDF copy at /world/<solution>/<copy>, every moving joint on t from `values` (V1's loader, re-used)."""
    tree = viz._urdf_copy(plan, rec, copy, colour)
    on_t = [rr.TimeColumn(T, duration=seconds)]
    for joint in tree.joints():
        entity = f"/world/{plan.part}/{copy}/joint_transforms/{_part(joint.name)}"
        joint_values = values.get(joint.name)
        if joint_values is not None and joint.joint_type != "fixed":
            rec.send_columns(entity, indexes=on_t, columns=joint.compute_transform_columns(joint_values.tolist(),
                                                                                           clamp=False))
        else:
            rec.log(entity, joint.compute_transform(0.0, clamp=False), static=True)


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
    """Overlap area of two boxes, each grown by `margin` px (0 = clear by at least 2 × margin)."""
    w = min(a[2], b[2]) - max(a[0], b[0]) + 2 * margin
    h = min(a[3], b[3]) - max(a[1], b[1]) + 2 * margin
    return max(w, 0.0) * max(h, 0.0)


def _label_places(run_: _Run, picked: np.ndarray, texts: list[str], start: np.ndarray,
                  end: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per row, where the magnifier's label goes: (the leader's foot on the arrow, the label's point).

    Candidates, in order: above the arrow's upper end (one, then two steps up), beside it (left, right), below its lower
    end. The first whose label box clears the start / end labels and points, the arrow, and the view's edge wins; the
    row before's pick is kept while it still clears (no flicker). Measured at the opening camera at 1600 x 1000: an
    orbit moves the labels, and the frames are the check."""
    eye = run_.s.eye
    step = LABEL_LIFT_SHARE * run_.path_radius
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
        ends = np.stack([run_.p_target[row], run_.p_magnified[row]])
        ends_xy = _screen(eye, ends)
        upper, lower = ends[int(np.argmin(ends_xy[:, 1]))], ends[int(np.argmax(ends_xy[:, 1]))]
        shaft = _screen(eye, np.linspace(ends[0], ends[1], 12))
        shaft_box = np.array([*shaft.min(axis=0) - 4, *shaft.max(axis=0) + 4])
        options = [(upper, upper + lift), (upper, upper + 2 * lift), (upper, upper + lift - side),
                   (upper, upper + lift + side), (lower, lower - 0.25 * lift), (lower, lower - lift)]

        def cost(option: tuple[np.ndarray, np.ndarray]) -> float:
            box = _label_box(_screen(eye, option[1])[0], texts[i])
            out = max(x0 - box[0], 0) + max(box[2] - x1, 0) + max(y0 - box[1], 0) + max(box[3] - y1, 0)
            return sum(_overlap(box, other, margin) for other in fixed) + _overlap(box, shaft_box, 0.0) + 100 * out

        costs = [cost(option) for option in options]
        pick = last if last is not None and costs[last] == 0.0 else \
            next((k for k, c in enumerate(costs) if c == 0.0), int(np.argmin(costs)))
        last = pick
        feet.append(options[pick][0])
        anchors.append(options[pick][1])
    return np.asarray(feet), np.asarray(anchors)


def _log_tool(rec: rr.RecordingStream, run_: _Run) -> None:
    """The solution's tool path (V1's: travelled solid, ahead faint, the stick, start/end), the target's dashed, and
    the magnifier: the ×N tool point's path (static), and at the playhead the ×N skeleton and an arrow from the
    target's tool point to the ×N one."""
    s = run_.s
    part = s.part
    frame = rr.CoordinateFrame(f"{part}/{s.tool_frame}")
    xyz = s.tool_xyz
    last = len(xyz) - 1
    picked = np.unique(np.linspace(0, last, min(last + 1, _ROWS)).round().astype(int))
    vertices = viz._VERTICES

    def thin(points: np.ndarray, first: int, end: int) -> np.ndarray:
        return points[np.unique(np.linspace(first, end, min(end - first + 1, vertices)).round().astype(int))]

    at = [rr.TimeColumn(T, duration=s.tool_t[picked])]
    for entity, colour, radius, strips in (
        ("path", viz._PATH_FAINT, 0.003, [thin(xyz, row, last) for row in picked]),
        ("trail", viz._ACCENT, 0.0045, [thin(xyz, 0, row) for row in picked]),
    ):
        path = f"/world/{part}/tool/{entity}"
        rec.log(path, rr.LineStrips3D.from_fields(colors=[colour], radii=[radius]), frame, static=True)
        rec.send_columns(path, indexes=at, columns=rr.LineStrips3D.columns(strips=strips))
    if s.flange is not None:
        stick = f"/world/{part}/tool/stick"
        rec.log(stick, rr.LineStrips3D.from_fields(colors=[viz._STICK], radii=[0.004]), frame, static=True)
        rec.send_columns(stick, indexes=at, columns=rr.LineStrips3D.columns(
            strips=[np.stack([s.flange[row], xyz[row]]) for row in picked]))
    rec.log(f"/world/{part}/tool/ends", rr.Points3D([xyz[0], xyz[-1]], labels=["start", "end"],
                                                    colors=[viz._LABEL_START, viz._LABEL_END], radii=[0.009]),
            frame, static=True)
    if run_.t is None:
        return
    # the target's path: dashed (Rerun has no dash style: alternate 12 mm pieces), static, under the solution's
    rec.log(f"/world/{part}/target_tool/path", rr.LineStrips3D(_dashes(run_.p_target, 0.012), colors=[TARGET_PATH],
                                                               radii=[0.0032]), frame, static=True)  # fmt: skip
    # the magnifier: the target path + N × the solution's deviation, the whole run static and thin, and at the playhead
    # an arrow from the target's tool point to the magnified solution point, labelled with N and the true TCP offset
    n = run_.magnify
    magnified = run_.p_magnified
    rec.log(f"/world/{part}/magnifier/path", rr.LineStrips3D([thin(magnified, 0, last)], colors=[ERROR_SOFT],
                                                             radii=[0.0022]), frame, static=True)  # fmt: skip
    arrow = f"/world/{part}/magnifier/now"
    rec.log(arrow, rr.Arrows3D.from_fields(colors=[ERROR], radii=[ARROW_RADIUS]), frame, static=True)
    rec.send_columns(arrow, indexes=at, columns=rr.Arrows3D.columns(origins=run_.p_target[picked],
                                                                    vectors=(magnified - run_.p_target)[picked]))
    if run_.skeleton is not None:
        # the ×N arm as a skeleton at the playhead (see the module's WHY): one magenta line, elbow → wrists → flange →
        # the ×N tool point (the arrow's tip), and a small sphere at each joint
        bones = f"/world/{part}/magnifier/skeleton"
        rec.log(bones, rr.LineStrips3D.from_fields(colors=[ERROR], radii=[SKELETON_RADIUS]), frame, static=True)
        rec.send_columns(bones, indexes=at, columns=rr.LineStrips3D.columns(
            strips=[run_.skeleton[row] for row in picked]))
        joints = f"/world/{part}/magnifier/joints"
        count = run_.skeleton_joints.shape[1]
        rec.log(joints, rr.Points3D.from_fields(colors=[ERROR], radii=[SKELETON_JOINT_RADIUS]), frame, static=True)
        rec.send_columns(joints, indexes=at, columns=rr.Points3D.columns(
            positions=run_.skeleton_joints[picked].reshape(-1, 3)).partition([count] * len(picked)))
    tip = f"/world/{part}/magnifier/tip"
    rec.log(tip, rr.Points3D.from_fields(colors=[ERROR], radii=[0.009]), frame, static=True)
    rec.send_columns(tip, indexes=at, columns=rr.Points3D.columns(positions=magnified[picked]))
    # the label, off the arrow on a thin leader, placed where it clears start / end (see LABEL_LIFT_SHARE)
    texts = [f"run ×{n} · TCP off {run_.dev_mm[row]:.1f} mm" for row in picked]
    foot, anchor = _label_places(run_, picked, texts, xyz[0], xyz[-1])
    leader = f"/world/{part}/magnifier/leader"
    rec.log(leader, rr.LineStrips3D.from_fields(colors=[ERROR_SOFT], radii=[0.0015]), frame, static=True)
    rec.send_columns(leader, indexes=at, columns=rr.LineStrips3D.columns(
        strips=[np.stack([foot[i], anchor[i]]) for i in range(len(picked))]))
    label = f"/world/{part}/magnifier/label"
    rec.log(label, rr.Points3D.from_fields(colors=[ERROR], radii=[0.004], show_labels=True), frame, static=True)
    rec.send_columns(label, indexes=at, columns=rr.Points3D.columns(positions=anchor, labels=texts))
    point = f"/world/{part}/target_tool/now"
    rec.log(point, rr.Points3D.from_fields(colors=[TARGET_PATH], radii=[0.007]), frame, static=True)
    rec.send_columns(point, indexes=at, columns=rr.Points3D.columns(positions=run_.p_target[picked]))


def _log_error(rec: rr.RecordingStream, run_: _Run) -> None:
    t = run_.seconds
    primary = run_.ruler if run_.ruler is not None else run_.dev_mm
    # WHY shaded: the area under the error is what the eye compares across the run (Measurements = the stock band)
    # (viz.band's own call, its centre line at width 0: at err / 2 it read as a second, false error curve)
    rec.log("/error/tool/shade", rr.Measurements.from_fields(colors=[ERROR_SHADE], names=["area under the ruler"],
                                                             widths=[0.0]), static=True)
    rec.send_columns("/error/tool/shade", indexes=[rr.TimeColumn(T, duration=t)],
                     columns=rr.Measurements.columns(values=0.5 * primary, variances=(0.5 * primary) ** 2))
    if run_.ruler is not None:
        # WHY "fk_tcp_off": entity-path order is draw order (see "reference"), and f < r keeps this pale line under
        # the bold ruler; its name is the 3D label's
        point = "" if run_.tool_offset_mm is None else f", {run_.tool_offset_mm:.0f} mm point"
        _scalars(rec, "/error/tool/fk_tcp_off", t, run_.dev_mm, names=f"TCP off (FK{point}) = 3D label",
                 colours=ERROR_SOFT, widths=1.6)
    _scalars(rec, "/error/tool/ruler", t, primary,
             names="the agent's ruler" if run_.ruler is not None else "TCP off = 3D label", colours=ERROR, widths=2.2)
    s = run_.s
    _scalars(rec, f"/error/joint/{s.part}", t, run_.dq_shown, names=[viz._short_joint(j) for j in s.joints],
             colours=JOINT_COLOURS[: len(s.joints)], widths=1.8)
    table_t, tables = run_.error_tables()
    rec.send_columns(f"/notes/error", indexes=[rr.TimeColumn(T, duration=table_t)],
                     columns=rr.TextDocument.columns(text=tables, media_type=["text/markdown"] * len(tables)))


# ── the dashboard ───────────────────────────────────────────────────────────────────────────────────────────────


def _plot(strip: viz._Strip) -> Any:
    axis_y = rrb.ScalarAxis(range=strip.y_range, zoom_lock=False) if strip.y_range else None
    return rrb.TimeSeriesView(origin="/", contents=strip.contents, name=strip.title,
                              plot_legend=rrb.PlotLegend(visible=strip.legend,
                                                         corner=getattr(strip, "corner", "RightBottom")),
                              axis_x=rrb.TimeAxis(link="LinkToGlobal"), axis_y=axis_y)


def _dashboard(run_: _Run) -> Any:
    s = run_.s
    if run_.t is None:
        title = f"{run_.label} · {s.robot_name} · {s.seconds[-1]:.2f} s · {s.tool_label} path solid to the playhead"
    else:
        worst = float(np.abs(run_.dq_shown).max())
        # WHY this short (after the check): the key was cut at "dashed ▸" in the half-width view at 1600 px; the run's
        # label moved to the Error table. WHY "not drawn": the target arm is within this many degrees of the run, the
        # same pose at this scale, and drawn twice it z-fought the steel
        title = (f"steel = run · magenta skeleton = run ×{run_.magnify} about the target · dashed blue = target path "
                 f"(arm ≤ {worst:.2f}° off, not drawn)")
    world = rrb.Spatial3DView(origin="/", contents=[f"/world/{s.part}/**"], name=title, eye_controls=s.eye)
    tabs = []
    if run_.t is not None:
        tool, joints = run_.error_strips()
        tabs.append(rrb.Vertical(_plot(tool), _plot(joints),
                                 rrb.TextDocumentView(origin="/notes/error", name="at the playhead: target vs run"),
                                 row_shares=[4, 4, 3], name="Error"))
    for name, strips in run_.tabs().items():
        if name == "q / qd / qdd":
            table = rrb.TextDocumentView(origin=f"/notes/{s.part}", name="at the playhead (solution)")
            columns = 1 if len(strips) <= 3 else 2
            card_rows = -(-len(strips) // columns)
            tabs.append(rrb.Vertical(table, rrb.Grid(*(_plot(c) for c in strips), grid_columns=columns),
                                     row_shares=[len(s.joints) + 5, 8 * card_rows], name=name))
        else:
            tabs.append(rrb.Vertical(*(_plot(strip) for strip in strips), name=name))
    return rrb.Blueprint(
        rrb.Horizontal(world, rrb.Tabs(*tabs, active_tab=0), column_shares=[1, 1]),
        rrb.BlueprintPanel(state="collapsed"),
        rrb.SelectionPanel(state="collapsed"),
        rrb.TimePanel(state="collapsed", timeline=T, play_state="paused", loop_mode="all"),
        collapse_panels=False,
    )


def save(path, traj: JointTrajectory, *, robot, tool: PoseTrajectory | None = None, target: JointTrajectory | None = None,
         target_tool: PoseTrajectory | None = None, extras: dict | None = None) -> str:
    """Write `traj` (the solution, or a plan) with its URDF `robot` to an .rrd; `target` adds the ×N skeleton, the
    dashed target path, the magnifier arrow, the Error tab and a pale target line under every plot. `extras` (the
    agent's run): `label` (titles), `tool_error_mm` (the agent's ruler per sample, the Error tab's bold line) and
    `rms_mm` (its title)."""
    run_ = _Run(traj, robot, tool, target, target_tool, extras)
    rec = rr.RecordingStream(APPLICATION_ID)
    # WHY default_blueprint at save (robot_msgs' R4 finding): written first, the file opens paused at t = 0
    rec.save(str(path), default_blueprint=_dashboard(run_))
    s = run_.s
    if run_.t is not None:  # (draw order is entity-path order, not log order: see the "reference" WHY)
        _log_series(rec, run_.t, target=True)
    _log_series(rec, s, target=False)
    _log_limits(rec, s)
    table_t, tables = s.tables
    if run_.t is not None:  # V1's colour key, plus what the pale lines are
        tables = [table.replace("(the green band is ±100 %)", "(the green band is ±100 %); the same three, pale and "
                                "wide, underneath = the target", 1) for table in tables]
    rec.send_columns(f"/notes/{s.part}", indexes=[rr.TimeColumn(T, duration=table_t)],
                     columns=rr.TextDocument.columns(text=tables, media_type=["text/markdown"] * len(tables)))
    _log_arm(rec, s, "robot", viz._ARM, s.values, s.seconds)
    if run_.t is not None:  # no target arm (the run's pose within 0.62°) and no ×N arm of meshes: the module's WHYs
        _log_error(rec, run_)
    _log_tool(rec, run_)
    viz._PATHS.pop(id(rec), None)  # `band` registers paths for robot_msgs' own default dashboard; ours is sent above
    rec.flush()
    rec.disconnect()
    return str(path)


def main() -> None:
    traj, tool = plan()
    print(save(HERE / "plan-dev-029.rrd", traj, robot=URDF, tool=tool, extras={"label": "workspace-dev-029 (plan)"}))
    target, solution, target_tool, solution_tool, extras = run("p6s")
    print(save(HERE / "run-dev-029.rrd", solution, robot=URDF, tool=solution_tool, target=target,
               target_tool=target_tool, extras=extras))


if __name__ == "__main__":
    main()
