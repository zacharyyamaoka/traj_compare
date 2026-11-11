"""The site's inline SVG diagrams, computed from real geometry so they are to scale.

Each function returns one ``<svg>`` string that themes itself through the ``dg-*`` classes in
style.css (light and dark). WHY computed, not hand-drawn: the lag / cross-track / contour and ISO
9283 figures are claims about geometry; drawing them from the same maths the library uses means the
picture cannot quietly disagree with the definition (cross-track really is longer than contour on
the curve below, because the tangent split leaks lag on curves).
"""

from __future__ import annotations

import math
import random

ARROW_DEFS = """<defs>
  <marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" class="{cls}"/>
  </marker>
</defs>"""


def _defs(prefix: str) -> str:
    return "".join(
        ARROW_DEFS.format(id=f"{prefix}-{name}", cls=cls)
        for name, cls in (("a", "dg-arrowhead"), ("acc", "dg-fill-accent"), ("real", "dg-real"), ("target", "dg-target"))
    )


def _text(x: float, y: float, text: str, cls: str = "dg-muted", anchor: str = "start", extra: str = "") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{text}</text>'


def _line(x1, y1, x2, y2, cls="dg-line", marker="", extra="") -> str:
    end = f' marker-end="url(#{marker})"' if marker else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"{end} {extra}/>'


def _box(x, y, w, h, cls="dg-box", r=8) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" class="{cls}"/>'


# ── 1. data flow: runs → compare → Comparison → viewers ─────────────────────


def flow(sdk: str) -> str:
    p = "flow"
    parts = ['<svg viewBox="0 0 960 492" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Data flow: target, sim and real runs go pairwise through robot_msgs.compare into a '
             'Comparison, which traj_compare draws as an offline HTML report and a Rerun recording">', _defs(p)]
    # regions
    parts.append('<rect x="204" y="22" width="436" height="452" rx="12" class="dg-region"/>')
    parts.append(_text(220, 44, "robot_msgs.compare · pure numpy", "dg-label"))
    parts.append('<rect x="662" y="22" width="284" height="452" rx="12" class="dg-region"/>')
    parts.append(_text(678, 44, "traj_compare · viewers", "dg-label"))
    parts.append(_text(20, 44, "runs", "dg-label"))
    # sources, merged by a bracket into one input
    roles = (("target", "Target", "what was planned"), ("sim", "Sim", "a simulated run"), ("real", "Real", "a recorded run"))
    for index, (role, title, sub) in enumerate(roles):
        y = 72 + index * 92
        parts.append(_box(20, y, 154, 60))
        parts.append(f'<rect x="20" y="{y}" width="5" height="60" rx="2" class="dg-{role}"/>')
        parts.append(_text(36, y + 25, title, "dg-text"))
        parts.append(_text(36, y + 44, sub, "dg-faint"))
        parts.append(_line(174, y + 30, 190, y + 30, "dg-line"))
    parts.append(_line(190, 102, 190, 286, "dg-line"))
    parts.append(_line(190, 178, 222, 178, "dg-line", f"{p}-a"))
    parts.append(_text(97, 372, "each a JointTrajectory, or a", "dg-faint", "middle"))
    parts.append(_text(97, 388, "PoseTrajectory per point", "dg-faint", "middle"))
    # compare
    parts.append(_box(224, 136, 170, 84, "dg-box", 10))
    parts.append(_text(309, 165, "compare(", "dg-mono", "middle"))
    parts.append(_text(309, 183, "reference, measured)", "dg-mono", "middle"))
    parts.append(_text(309, 205, "one pair at a time", "dg-faint", "middle"))
    parts.append(_line(394, 178, 428, 178, "dg-line", f"{p}-a"))
    # Comparison
    parts.append(_box(430, 62, 192, 196, "dg-box", 10))
    parts.append(_text(446, 88, "Comparison", "dg-text"))
    rows = (
        ("error", "same type · ref − meas"),
        ("metrics", "ErrorStats by name"),
        ("time_offset_s", "how the clocks met"),
        ("dropped", "samples outside ref"),
        ("coverage", "share of ref measured"),
    )
    for index, (name, note) in enumerate(rows):
        y = 112 + index * 30
        parts.append(_text(446, y, name, "dg-mono"))
        parts.append(_text(446, y + 14, note, "dg-faint", extra='style="font-size:10.5px"'))
    # the same pair feeds the other functions
    parts.append(_line(309, 220, 309, 300, "dg-line"))
    parts.append(_line(282, 300, 566, 300, "dg-line"))
    parts.append(_text(318, 292, "same (reference, measured) pair", "dg-faint"))
    helpers = (
        (214, ("estimate_time_offset",), "→ time_offset_s"),
        (356, ("check", "ToleranceMonitor"), "→ Outcome 0 / −4 / −5"),
        (498, ("aggregate", "(N runs)"), "→ accuracy · repeatability"),
    )
    for x, titles, sub in helpers:
        parts.append(_line(x + 68, 300, x + 68, 328, "dg-line", f"{p}-a"))
        parts.append(_box(x, 330, 136, 76, "dg-soft", 8))
        for line, title in enumerate(titles):
            parts.append(_text(x + 68, 352 + 16 * line, title, "dg-mono", "middle", 'style="font-size:11px"'))
        parts.append(_text(x + 68, 394, sub, "dg-faint", "middle", 'style="font-size:10.5px"'))
    # latency goes back in, but only when you pass it
    parts.append(_line(236, 330, 236, 224, "dg-line dash", f"{p}-acc", 'style="stroke:var(--accent)"'))
    parts.append(_text(242, 262, "you pass it", "dg-faint", extra='style="fill:var(--accent)"'))
    parts.append(_text(422, 436, "also over the same pair: goal · relative_error · frechet", "dg-faint", "middle"))
    parts.append(_text(422, 456, "every ErrorStats: n rms mean median std min max max_abs p95_abs final iae ise itae",
                       "dg-faint", "middle", 'style="font-size:10.5px"'))
    # viewers
    parts.append(_line(622, 109, 680, 109, "dg-line", f"{p}-a"))
    parts.append(_line(622, 227, 680, 227, "dg-line", f"{p}-a"))
    viewers = (
        (72, "write_comparison_report", "report.html · offline, one file", "plots · 3D · synced video · verdicts"),
        (190, "rerun=True · write_rrd", "rerun/&lt;name&gt;.rrd", "one recording, blueprint inside"),
        (308, "python -m traj_compare.serve", "Open in Rerun button", f"→ pinned viewer {sdk}"),
    )
    for y, mono, title, sub in viewers:
        parts.append(_box(682, y, 246, 74, "dg-box", 10))
        parts.append(_text(698, y + 24, mono, "dg-mono", extra='style="font-size:11.5px"'))
        parts.append(_text(698, y + 44, title, "dg-text", extra='style="font-size:12.5px"'))
        parts.append(_text(698, y + 61, sub, "dg-faint"))
    parts.append(_line(805, 264, 805, 306, "dg-line", f"{p}-a"))
    parts.append(_text(805, 420, "the viewers only read results:", "dg-faint", "middle"))
    parts.append(_text(805, 436, "same numbers in both", "dg-faint", "middle"))
    parts.append("</svg>")
    return "".join(parts)


# ── 2. the three pairings ────────────────────────────────────────────────────


def pairings() -> str:
    p = "pair"
    nodes = {"target": (270, 52, "Target"), "sim": (100, 236, "Sim"), "real": (440, 236, "Real")}
    parts = ['<svg viewBox="0 0 540 300" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Three pairings: target to sim, target to real, sim to real">', _defs(p)]

    def edge(a: str, b: str, label: str, side: float) -> None:
        (x1, y1, _), (x2, y2, _) = nodes[a][:3], nodes[b][:3]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        gap = 34 if abs(uy) < 0.2 else 30
        sx, sy = x1 + ux * (gap + 30 * abs(ux)), y1 + uy * gap
        ex, ey = x2 - ux * (gap + 30 * abs(ux)), y2 - uy * gap
        parts.append(_line(sx, sy, ex, ey, "dg-line", f"{p}-a", 'style="stroke-width:1.6"'))
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        nx, ny = -uy * side, ux * side
        parts.append(_text(mx + nx, my + ny + 4, label, "dg-mono", "middle"))

    edge("target", "sim", "target → sim", 50)
    edge("target", "real", "target → real", -50)
    edge("sim", "real", "sim → real", 16)
    for role, (x, y, title) in nodes.items():
        parts.append(f'<rect x="{x - 58}" y="{y - 22}" width="116" height="44" rx="9" class="dg-{role}"/>')
        parts.append(f'<text x="{x}" y="{y + 5}" text-anchor="middle" style="fill:#fff;font:600 15px var(--font)">{title}</text>')
    parts.append(_text(270, 292, "arrow = reference → measured · error = reference − measured", "dg-faint", "middle"))
    parts.append("</svg>")
    return "".join(parts)


# ── 3. lag / cross_track (tangent split) vs contour / lag_time (nearest point) ──


def tracking() -> str:
    """A curved reference, one measured sample behind and inside it, drawn to scale."""
    p = "trk"
    cx, cy, radius = 340.0, 820.0, 760.0  # a gentle arc across the top of the figure

    def on_arc(theta_deg: float, r: float = radius) -> tuple[float, float]:
        theta = math.radians(theta_deg)
        return cx + r * math.cos(theta), cy - r * math.sin(theta)

    theta_ref, theta_meas, inset = 84.0, 95.5, 70.0
    ref = on_arc(theta_ref)
    meas = on_arc(theta_meas, radius - inset)
    # direction of travel at the reference: the path runs left -> right (polar angle decreasing), so in
    # screen coordinates (y down) the unit tangent is (sin θ, cos θ)
    t_ref = math.radians(theta_ref)
    tangent = (math.sin(t_ref), math.cos(t_ref))
    error = (ref[0] - meas[0], ref[1] - meas[1])
    lag = error[0] * tangent[0] + error[1] * tangent[1]
    foot = (meas[0] + lag * tangent[0], meas[1] + lag * tangent[1])
    cross = math.hypot(ref[0] - foot[0], ref[1] - foot[1])
    radial = (meas[0] - cx, meas[1] - cy)
    norm = math.hypot(*radial)
    nearest = (cx + radial[0] / norm * radius, cy + radial[1] / norm * radius)
    contour = math.hypot(nearest[0] - meas[0], nearest[1] - meas[1])
    assert cross > contour, "on a curve the tangent split must leak lag into cross-track"

    parts = ['<svg viewBox="0 0 680 300" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Lag and cross-track split the error along the reference tangent; contour is the exact '
             'distance to the nearest point of the reference path">', _defs(p)]
    # reference path + its samples
    start, end = on_arc(116.0), on_arc(64.0)
    parts.append(f'<path d="M{start[0]:.1f},{start[1]:.1f} A{radius},{radius} 0 0 1 {end[0]:.1f},{end[1]:.1f}" '
                 f'class="dg-line" style="stroke:var(--target);stroke-width:2.2;stroke-dasharray:7 5"/>')
    for theta in range(114, 64, -4):
        x, y = on_arc(theta)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" class="dg-target"/>')
    parts.append(_text(start[0] - 4, start[1] + 26, "reference path (target)", "dg-faint"))
    # direction of travel
    tip = (ref[0] + 70 * tangent[0], ref[1] + 70 * tangent[1])
    parts.append(_line(ref[0], ref[1], *tip, "dg-line", f"{p}-target", 'style="stroke:var(--target);stroke-width:1.6"'))
    parts.append(_text(tip[0] + 4, tip[1] - 10, "direction of travel", "dg-faint"))
    # error vector, split
    parts.append(_line(meas[0], meas[1], foot[0], foot[1], "dg-line dash", "",
                       'style="stroke:var(--accent);stroke-width:1.8"'))
    parts.append(_line(foot[0], foot[1], ref[0], ref[1], "dg-line dash", "",
                       'style="stroke:var(--accent);stroke-width:1.8"'))
    parts.append(_line(meas[0], meas[1], ref[0], ref[1], "dg-line", f"{p}-acc",
                       'style="stroke:var(--accent);stroke-width:2.2"'))
    # contour to the nearest point
    parts.append(_line(meas[0], meas[1], nearest[0], nearest[1], "dg-line", "",
                       'style="stroke:var(--real);stroke-width:2"'))
    parts.append(f'<circle cx="{nearest[0]:.1f}" cy="{nearest[1]:.1f}" r="5" style="fill:var(--surface);stroke:var(--real);stroke-width:2"/>')
    # points
    parts.append(f'<circle cx="{ref[0]:.1f}" cy="{ref[1]:.1f}" r="6" class="dg-target"/>')
    parts.append(f'<circle cx="{meas[0]:.1f}" cy="{meas[1]:.1f}" r="6" class="dg-real"/>')
    # labels
    parts.append(_text(ref[0] + 10, ref[1] - 12, "reference at τ", "dg-text"))
    parts.append(_text(meas[0] - 10, meas[1] + 24, "measured at τ", "dg-text", "end"))
    mid_lag = ((meas[0] + foot[0]) / 2, (meas[1] + foot[1]) / 2)
    parts.append(_text(mid_lag[0] + 4, mid_lag[1] + 22, "lag (+ = behind)", "dg-muted", "middle",
                       'style="fill:var(--accent)"'))
    parts.append(_text(foot[0] + 10, (foot[1] + ref[1]) / 2 + 12, "cross_track", "dg-muted", "start",
                       'style="fill:var(--accent)"'))
    mid_err = ((meas[0] + ref[0]) / 2, (meas[1] + ref[1]) / 2)
    parts.append(_text(mid_err[0] - 8, mid_err[1] - 12, "error", "dg-muted", "middle", 'style="fill:var(--accent)"'))
    parts.append(_text(nearest[0] - 10, nearest[1] - 12, "nearest point, at t_nearest", "dg-muted", "end",
                       'style="fill:var(--real)"'))
    parts.append(_text(nearest[0] - 12, (nearest[1] + meas[1]) / 2 + 4, "contour", "dg-muted", "end",
                       'style="fill:var(--real)"'))
    # numbers (to scale, in figure units)
    parts.append(_text(24, 236, f"to scale: lag {lag:.0f} · cross_track {cross:.0f} · contour {contour:.0f} (figure units)",
                       "dg-faint"))
    parts.append(_text(24, 256, "tangent split: lag + cross_track, no search, leaks lag into cross_track on a curve",
                       "dg-faint"))
    parts.append(_text(24, 276, "nearest point: contour + lag_time = τ − t_nearest, searched within ±contour_window_s",
                       "dg-faint"))
    parts.append("</svg>")
    return "".join(parts)


# ── 4. the conveyor frame ───────────────────────────────────────────────────


def conveyor() -> str:
    """Top view: a belt at 20° to world x; the TCP error read along / across it (error exaggerated)."""
    p = "cv"
    angle = math.radians(20.0)  # belt direction, measured from world +x towards world +y
    belt = (math.cos(angle), -math.sin(angle))  # screen coords: world +y is up the page
    # "across belt" = belt × up (np.cross(BELT, UP), as the UR5e example): right of the direction of travel
    across = (math.sin(angle), math.cos(angle))
    centre = (350.0, 150.0)
    half_length, half_width = 330.0, 56.0

    def at(a: float, b: float) -> tuple[float, float]:
        return centre[0] + a * belt[0] + b * across[0], centre[1] + a * belt[1] + b * across[1]

    corners = [at(-half_length, -half_width), at(half_length, -half_width), at(half_length, half_width),
               at(-half_length, half_width)]
    parts = ['<svg viewBox="0 0 700 300" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Top view of a conveyor at an angle to the world axes; the TCP error is read along and '
             'across the belt">', _defs(p)]
    parts.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in corners) + '" class="dg-soft"/>')
    for a in range(-300, 320, 50):  # chevrons: the belt moves along +belt
        if -70 < a < 90 or -270 < a < -140:
            continue  # keep the error drawing and the belt axes clear
        tip = at(a + 10, 0)
        left, right = at(a - 6, -16), at(a - 6, 16)
        parts.append(f'<polyline points="{left[0]:.1f},{left[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} {right[0]:.1f},{right[1]:.1f}" '
                     f'class="dg-line" style="stroke:var(--border-strong);stroke-width:2"/>')
    label = at(-150, -half_width + 14)
    rotation = math.degrees(math.atan2(belt[1], belt[0]))
    parts.append(_text(*label, "conveyor · moves at belt speed (0.35 m/s in the UR5e example)", "dg-faint",
                       extra=f'transform="rotate({rotation:.1f} {label[0]:.1f} {label[1]:.1f})"'))
    # target vs measured TCP on the belt: the run is behind (along) and off to the side (across)
    ref = at(50, -8)
    meas = at(50 - 46, -8 + 28)
    corner = at(50, -8 + 28)
    dashed = 'style="stroke:var(--accent);stroke-width:1.8"'
    parts.append(_line(meas[0], meas[1], corner[0], corner[1], "dg-line dash", "", dashed))
    parts.append(_line(corner[0], corner[1], ref[0], ref[1], "dg-line dash", "", dashed))
    parts.append(_line(meas[0], meas[1], ref[0], ref[1], "dg-line", f"{p}-acc", 'style="stroke:var(--accent);stroke-width:2.2"'))
    parts.append(f'<circle cx="{ref[0]:.1f}" cy="{ref[1]:.1f}" r="6" class="dg-target"/>')
    parts.append(f'<circle cx="{meas[0]:.1f}" cy="{meas[1]:.1f}" r="6" class="dg-real"/>')
    parts.append(_text(ref[0] + 10, ref[1] - 10, "target TCP", "dg-text"))
    parts.append(_text(meas[0] - 12, meas[1] + 5, "real TCP", "dg-text", "end"))
    mid = ((meas[0] + corner[0]) / 2, (meas[1] + corner[1]) / 2)
    parts.append(_text(mid[0] + 6, mid[1] + 26, "along belt", "dg-muted", "middle", 'style="fill:var(--accent)"'))
    mid2 = ((corner[0] + ref[0]) / 2, (corner[1] + ref[1]) / 2)
    parts.append(_text(mid2[0] + 10, mid2[1] + 6, "across belt", "dg-muted", extra='style="fill:var(--accent)"'))
    # belt-frame axes, drawn near the start of the belt
    origin = at(-215, 0)
    b_tip = at(-215 + 72, 0)
    a_tip = at(-215, 46)
    arrow = 'style="stroke:var(--accent);stroke-width:2"'
    parts.append(_line(*origin, *b_tip, "dg-line", f"{p}-acc", arrow))
    parts.append(_line(*origin, *a_tip, "dg-line", f"{p}-acc", arrow))
    parts.append(_text(b_tip[0] + 6, b_tip[1] - 6, "b (along)", "dg-muted", extra='style="fill:var(--accent)"'))
    parts.append(_text(a_tip[0] + 8, a_tip[1] + 10, "b × up (across)", "dg-muted", extra='style="fill:var(--accent)"'))
    parts.append(f'<circle cx="{origin[0]:.1f}" cy="{origin[1]:.1f}" r="6" style="fill:var(--surface);stroke:var(--accent);stroke-width:1.6"/>')
    parts.append(f'<circle cx="{origin[0]:.1f}" cy="{origin[1]:.1f}" r="1.8" class="dg-fill-accent"/>')
    parts.append(_text(origin[0] - 10, origin[1] - 10, "up ⊙", "dg-muted", "end", 'style="fill:var(--accent)"'))
    # world axes, top-left
    wx, wy = 34.0, 74.0
    parts.append(_line(wx, wy, wx + 50, wy, "dg-line", f"{p}-a"))
    parts.append(_line(wx, wy, wx, wy - 50, "dg-line", f"{p}-a"))
    parts.append(_text(wx + 56, wy + 4, "world x", "dg-faint"))
    parts.append(_text(wx + 6, wy - 46, "world y", "dg-faint"))
    parts.append(_text(686, 262, "vec_dirs: Vec[Conveyor]_d = TCP velocity · b, flat at belt speed on the track",
                       "dg-faint", "end"))
    parts.append(_text(686, 280, "error_axes: the same error vector, read on (b, b × up, up) instead of world x / y / z",
                       "dg-faint", "end"))
    parts.append(_text(686, 298, "error exaggerated for legibility", "dg-faint", "end", 'style="font-size:10.5px"'))
    parts.append("</svg>")
    return "".join(parts)


# ── 5. ISO 9283: accuracy (bias of the barycentre) vs repeatability (spread) ──


def iso9283() -> str:
    p = "iso"
    rng = random.Random(9283)
    reference = (64.0, 120.0)
    bias = (226.0, -32.0)
    runs = [(reference[0] + bias[0] + rng.gauss(0, 15), reference[1] + bias[1] + rng.gauss(0, 15)) for _ in range(10)]
    bx = sum(x for x, _ in runs) / len(runs)
    by = sum(y for _, y in runs) / len(runs)
    distances = [math.hypot(x - bx, y - by) for x, y in runs]
    mean = sum(distances) / len(distances)
    spread = math.sqrt(sum((d - mean) ** 2 for d in distances) / (len(distances) - 1))
    rp = mean + 3.0 * spread  # ISO 9283 RP = l̄ + 3·S_l, S_l with ddof = 1, from the drawn points
    accuracy = math.hypot(bx - reference[0], by - reference[1])
    parts = ['<svg viewBox="0 0 620 226" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="ISO 9283: accuracy is the distance from the reference to the barycentre of the runs; '
             'repeatability is a circle of radius mean plus three standard deviations around the barycentre">',
             _defs(p)]
    parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{rp:.1f}" class="dg-region" style="stroke:var(--real)"/>')
    for x, y in runs:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" class="dg-real" style="opacity:0.85"/>')
    parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="5.5" style="fill:var(--surface);stroke:var(--accent);stroke-width:2.2"/>')
    rx, ry = reference
    parts.append(f'<path d="M{rx - 8},{ry} h16 M{rx},{ry - 8} v16" style="stroke:var(--target);stroke-width:2.6"/>')
    length = math.hypot(bx - rx, by - ry)
    ux, uy = (bx - rx) / length, (by - ry) / length
    parts.append(_line(rx + 10 * ux, ry + 10 * uy, bx - 8 * ux, by - 8 * uy, "dg-line", f"{p}-acc",
                       'style="stroke:var(--accent);stroke-width:2"'))
    parts.append(_text(rx, ry - 16, "reference", "dg-text", "middle"))
    parts.append(_text(rx - 6, ry + 34, "accuracy = |reference − barycentre|", "dg-muted", "start", 'style="fill:var(--accent)"'))
    parts.append(_text(rx - 6, ry + 51, "the bias: feed-forward or calibration removes it", "dg-faint"))
    edge = (bx + rp * 0.80, by - rp * 0.60)
    parts.append(_line(bx, by, *edge, "dg-line dash", "", 'style="stroke:var(--real)"'))
    tx = bx + rp + 16
    parts.append(_text(tx, by - 30, "repeatability RP = l̄ + 3·S_l", "dg-muted", "start", 'style="fill:var(--real)"'))
    parts.append(_text(tx, by - 12, "l = each run's distance to the", "dg-faint"))
    parts.append(_text(tx, by + 3, "barycentre (ring); S_l with ddof = 1", "dg-faint"))
    parts.append(_text(tx, by + 21, "the spread: only a better", "dg-faint"))
    parts.append(_text(tx, by + 36, "controller or plant shrinks it", "dg-faint"))
    parts.append(_text(310, 214, f"10 runs drawn to scale: accuracy {accuracy:.0f}, RP {rp:.0f} (figure units)",
                       "dg-faint", "middle"))
    parts.append("</svg>")
    return "".join(parts)


ALL = {"flow": flow, "pairings": pairings, "tracking": tracking, "conveyor": conveyor, "iso9283": iso9283}
