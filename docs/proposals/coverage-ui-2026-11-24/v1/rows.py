#!/usr/bin/env python3
"""V1 "Stock dashboard": the coverage payload as ROW tables for data-ui (data-ui reads rows, never a payload).

    python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v1/rows.py

Reads ../data/coverage.json, ../data/trajectories.json and ../data/samples.json; writes v1/rows/*.json.

A RE-SHAPE ONLY. Nothing here is computed from the trajectories: every count, percentage and limit is the payload's
(traj_compare.coverage.analyze wrote it). The only arithmetic is
  - expanding the payload's own grid specs ([low, high, n] edges, origin + i * pixel) into each cell's lo / hi, and
  - the payload's own display scale (joints[].display.scale: rad -> deg) and m -> mm / rad -> deg for the tool,
so a row says in display units what the payload says in SI. Empty cells are not rows (white = never visited); the
tool's reachable mask is written as run-length rows (one row per run of reachable pixels in a pixel row), which is
the same mask, shorter. Two files hold lists (paths: each trajectory's q and qd points; parallel: each joint pair's
non-empty [gx, gy, lines] cells) that the chart's stock Vega-Lite `flatten` transform expands.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = HERE / "rows"

SIGNAL_WORD = {"q": "position", "qd": "speed", "qdd": "acceleration", "qddd": "jerk"}
UNIT = {"revolute": {"q": "°", "qd": "°/s", "qdd": "°/s²", "qddd": "°/s³"},
        "prismatic": {"q": "mm", "qd": "mm/s", "qdd": "mm/s²", "qddd": "mm/s³"}}
DEG = 180.0 / math.pi


def edges(spec):
    lo, hi, n = spec
    step = (hi - lo) / n
    return [(lo + i * step, lo + (i + 1) * step) for i in range(n)]


def r(v, d=4):
    return None if v is None else round(v, d)


def short(joint: str) -> str:
    return joint.removesuffix("_joint")


def write(name, rows):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    print(f"{name}.json: {len(rows)} rows, {(OUT / f'{name}.json').stat().st_size / 1024:.0f} KB")


def main():
    cov = json.loads((DATA / "coverage.json").read_text())
    trajs = json.loads((DATA / "trajectories.json").read_text())
    joints = [j["name"] for j in cov["joints"]]
    kind = {j["name"]: j["kind"] for j in cov["joints"]}
    scale = {j["name"]: j["display"]["scale"] for j in cov["joints"]}

    def sig_label(j, s):
        return f"{s} · {SIGNAL_WORD[s]} ({UNIT[kind[j]][s]})"

    # ── the page header: the payload's own title, subtitle and `enough` threshold (the gear's "enough" scale)
    write("meta", [{"id": "meta", "title": cov["title"], "subtitle": cov["subtitle"], "enough": cov["enough"],
                    "group_by": cov["source"]["group_by"], "groups": cov["source"]["groups"], "frame": cov["tool"]["frame"]}])

    # ── Overview: the headline numbers, one KPI card each (the producer's, never recomputed)
    write("numbers", [{"id": n["key"], "key": n["key"], "label": n["label"], "order": i,
                       "value": {"value": n["value"], "unit": n["unit"] or None}}
                      for i, n in enumerate(cov["numbers"])])

    # ── Overview: each joint in numbers (hist span / peak, plane visited %): the payload's per-joint figures
    jrows = []
    for i, j in enumerate(joints):
        h, pl = cov["hist"][j], cov["planes"][j]
        jrows.append({"id": j, "joint": j, "order": i,
                      "q_span_pct": r(h["q"]["span_pct"], 2), "qd_peak_pct": r(h["qd"]["peak_pct"], 2),
                      "qdd_peak_pct": r(h["qdd"]["peak_pct"], 2), "qddd_peak_pct": r(h["qddd"]["peak_pct"], 2),
                      "q_qd_visited_pct": r(pl["q_qd"]["visited_pct"], 2), "q_qd_sufficient_pct": r(pl["q_qd"]["sufficient_pct"], 2),
                      "q_qd_evenness_pct": r(pl["q_qd"]["evenness_pct"], 2), "qd_qdd_visited_pct": r(pl["qd_qdd"]["visited_pct"], 2),
                      "outside_q": h["q"]["outside"], "outside_qd": h["qd"]["outside"], "outside_qdd": h["qdd"]["outside"]})
    write("joints", jrows)

    # ── Limits: every histogram bin of every joint and signal, split by group (split = dev / holdout)
    hrows = []
    for j in joints:
        for s in cov["signals"]:
            h, lim = cov["hist"][j][s], cov["limits"][j][s]
            k = scale[j]
            groups = h["groups"] or {"all": h["counts"]}
            common = {"joint": j, "signal": sig_label(j, s), "sig": s,
                      "edge_low": r(h["edges"][0] * k, 3), "edge_high": r(h["edges"][1] * k, 3),
                      "limit_low": r(lim["low"] * k, 3), "limit_high": r(lim["high"] * k, 3),
                      "limit_source": lim["source"], "p001": r(h["p001"] * k, 3), "p999": r(h["p999"] * k, 3)}
            for g, counts in groups.items():
                for (lo, hi), c in zip(edges(h["edges"]), counts):
                    if c:
                        hrows.append({**common, "group": g, "lo": r(lo * k, 3), "hi": r(hi * k, 3), "count": c})
    write("hist", hrows)

    # ── One joint: the q x qd, qd x qdd, q x qdd planes, one row per VISITED cell; the limit box on every row
    crows = []
    for j in joints:
        for plane, p in cov["planes"][j].items():
            k = scale[j]
            xs, ys = edges(p["x_edges"]), edges(p["y_edges"])
            nx, ny = p["shape"]
            box = {"x_min": r(p["x_edges"][0] * k, 3), "x_max": r(p["x_edges"][1] * k, 3),
                   "y_min": r(p["y_edges"][0] * k, 3), "y_max": r(p["y_edges"][1] * k, 3)}
            for i in range(nx):
                for jj in range(ny):
                    n = p["samples"][i * ny + jj]
                    if not n:
                        continue
                    row = {"joint": j, "plane": plane, "x_lo": r(xs[i][0] * k, 3), "x_hi": r(xs[i][1] * k, 3),
                           "y_lo": r(ys[jj][0] * k, 3), "y_hi": r(ys[jj][1] * k, 3),
                           "samples": n, "paths": p["paths"][i * ny + jj], **box}
                    if p["max_other"] is not None and p["max_other"][i * ny + jj] is not None:
                        row["max_qdd"] = r(p["max_other"][i * ny + jj] * k, 2)
                    crows.append(row)
    write("cells", crows)

    # ── One joint: the q x qd plane per qdd slab (5 bands)
    srows = []
    for j in joints:
        sl = cov["slabs"][j]
        k = scale[j]
        nb, nx, ny = sl["shape"]
        p = cov["planes"][j]["q_qd"]
        xs, ys = edges(p["x_edges"]), edges(p["y_edges"])
        for b, (blo, bhi) in enumerate(edges(sl["by_edges"])):
            band = f"{b + 1} · qdd {blo * k:.0f} … {bhi * k:.0f} °/s² · {sl['visited_pct'][b]:.0f} % visited"
            for i in range(nx):
                for jj in range(ny):
                    n = sl["samples"][(b * nx + i) * ny + jj]
                    if n:
                        srows.append({"joint": j, "band": band, "band_i": b, "x_lo": r(xs[i][0] * k, 3), "x_hi": r(xs[i][1] * k, 3),
                                      "y_lo": r(ys[jj][0] * k, 3), "y_hi": r(ys[jj][1] * k, 3), "samples": n})
    write("slabs", srows)

    # ── One joint: every trajectory's (q, qd) path, the payload's evenly picked points as two lists per row (Vega-Lite's
    #    stock `flatten` transform turns them into points in the chart, so no point is dropped and the file stays small)
    names = [t["name"] for t in cov["trajectories"]]
    split = {t["name"]: t["tags"].get("split") for t in cov["trajectories"]}
    prows = []
    for j in joints:
        k = scale[j]
        for name, (qs, qds, _qdds) in zip(names, cov["paths"][j]):
            prows.append({"joint": j, "trajectory": name, "split": split[name],
                          "q": [r(v * k, 2) for v in qs], "qd": [r(v * k, 2) for v in qds]})
    write("paths", prows)

    # ── All joints: the parallel-coordinates line density between adjacent joints (limit-normalised 0..1): one row per
    #    signal and joint pair, its non-empty cells as [gx, gy, lines] triples (flattened by Vega-Lite in the chart)
    arows = []
    for s, par in cov["parallel"].items():
        w, hgt = par["width"], par["height"]
        for pi, gaps in enumerate(par["gaps"]):
            pair = f"{pi + 1} · {short(par['axes'][pi])} → {short(par['axes'][pi + 1])}"
            cells = [[gx, gy, gaps[gx * hgt + gy]] for gx in range(w) for gy in range(hgt) if gaps[gx * hgt + gy]]
            arows.append({"signal": s, "pair": pair, "pair_i": pi, "width": w, "height": hgt, "cells": cells})
    write("parallel", arows)

    # ── All joints: visited % as trajectories are added, and the shuffled band
    g = cov["growth"]
    write("growth", [{"added": i + 1, "visited_pct": r(v, 3), "shuffled_mean": r(g["shuffled"]["mean"][i], 3),
                      "shuffled_p10": r(g["shuffled"]["p10"][i], 3), "shuffled_p90": r(g["shuffled"]["p90"][i], 3)}
                     for i, v in enumerate(g["visited_pct"])])

    tool = cov["tool"]
    # ── Tool position: the three projections, visited pixels + the reachable mask as runs, in mm
    VIEW = {"xy": "from above (x, y)", "xz": "from the front (x, z)", "yz": "from the side (y, z)"}
    xrows = []
    for v, p in tool["projections"].items():
        px = tool["pixel_m"] * 1000
        (u0, v0), (nu, nv) = p["origin"], p["shape"]
        u0, v0 = u0 * 1000, v0 * 1000
        lim = {"u_min": r(u0, 1), "u_max": r(u0 + nu * px, 1), "v_min": r(v0, 1), "v_max": r(v0 + nv * px, 1)}
        for i in range(nu):
            for j in range(nv):
                n = p["samples"][i * nv + j]
                if n:
                    xrows.append({"view": VIEW[v], "kind": "pixel", "u_lo": r(u0 + i * px, 1), "u_hi": r(u0 + (i + 1) * px, 1),
                                  "v_lo": r(v0 + j * px, 1), "v_hi": r(v0 + (j + 1) * px, 1), "samples": n, "paths": p["paths"][i * nv + j],
                                  "max_speed": r(p["max_speed"][i * nv + j], 3), **lim})
        if p["reachable"] is not None:
            for j in range(nv):  # one row per run of reachable pixels along u, in pixel row j
                i = 0
                while i < nu:
                    if p["reachable"][i * nv + j]:
                        start = i
                        while i < nu and p["reachable"][i * nv + j]:
                            i += 1
                        xrows.append({"view": VIEW[v], "kind": "reachable", "u_lo": r(u0 + start * px, 1), "u_hi": r(u0 + i * px, 1),
                                      "v_lo": r(v0 + j * px, 1), "v_hi": r(v0 + (j + 1) * px, 1), **lim})
                    else:
                        i += 1
    write("pixels", xrows)

    # ── Tool position: the voxels (cell centres in mm), and the tool speed histogram
    vx = tool["voxels"]
    size = vx["size"] * 1000
    ox, oy, oz = (c * 1000 for c in vx["origin"])
    write("voxels", [{"x_mm": r(ox + (ix + 0.5) * size, 1), "y_mm": r(oy + (iy + 0.5) * size, 1), "z_mm": r(oz + (iz + 0.5) * size, 1),
                      "samples": n, "paths": paths, "max_speed": r(ms, 3)} for ix, iy, iz, n, paths, ms in vx["cells"]])
    p99 = next(n["value"] for n in cov["numbers"] if n["key"] == "tool_speed_p99_m_s")
    write("speed", [{"lo": r(lo, 4), "hi": r(hi, 4), "samples": c, "p99": r(p99, 3)}
                    for (lo, hi), c in zip(edges(tool["speed"]["edges"]), tool["speed"]["counts"])])

    # ── Tool position: every sample's tool point (samples.json's own columns: trajectory, split, t, x/y/z mm)
    samples = json.loads((DATA / "samples.json").read_text())
    write("toolpath", [{"trajectory": s["trajectory"], "split": s["split"], "t": s["t_s"], "frame": tool["frame"], "body": "tool",
                        "x_mm": s["x_mm"], "y_mm": s["y_mm"], "z_mm": s["z_mm"]} for s in samples])
    # the drill: one trajectory's joint angles over time (samples.json's columns, unchanged)
    qcols = [f"{short(j)}_q_deg" for j in joints]
    write("samples", [{"trajectory": s["trajectory"], "t": s["t_s"], **{c: s[c] for c in qcols},
                       "tool_speed_m_s": s["tool_speed_m_s"], "tilt_deg": s["tilt_deg"]} for s in samples])

    # ── Tool orientation: tilt x azimuth, tilt x yaw (cells in degrees), tilt and yaw histograms
    o = tool["orientation"]

    def grid(spec, a_key, b_key, name):
        out = []
        ra, rb = edges(spec[a_key]), edges(spec[b_key])
        na, nb = spec["shape"]
        for i in range(na):
            for j in range(nb):
                n = spec["counts"][i * nb + j]
                if n:
                    out.append({"tilt_lo": r(ra[i][0] * DEG, 2), "tilt_hi": r(ra[i][1] * DEG, 2),
                                f"{name}_lo": r(rb[j][0] * DEG, 2), f"{name}_hi": r(rb[j][1] * DEG, 2), "samples": n})
        return out

    write("tilt_azimuth", grid(o["tilt_azimuth"], "tilt_edges", "azimuth_edges", "azimuth"))
    write("tilt_yaw", grid(o["tilt_yaw"], "tilt_edges", "yaw_edges", "yaw"))
    write("angles", [{"angle": "tilt from the reference", "lo": r(lo * DEG, 2), "hi": r(hi * DEG, 2), "samples": c}
                     for (lo, hi), c in zip(edges(o["tilt"]["edges"]), o["tilt"]["counts"])]
          + [{"angle": "yaw · jaw heading in base x-y", "lo": r(lo * DEG, 2), "hi": r(hi * DEG, 2), "samples": c}
             for (lo, hi), c in zip(edges(o["yaw"]["edges"]), o["yaw"]["counts"])])

    # ── Trajectories: one row per trajectory (data/trajectories.json flattened; the .rrd as a link the page opens)
    trows = []
    for i, t in enumerate(trajs):
        row = {"id": t["name"], "name": t["name"], "order": i + 1, "split": t["tags"].get("split"), "kind": t["tags"].get("kind"),
               "rung": t["tags"].get("rung"), "tags": t["tags"].get("tags"), "duration_s": t["duration_s"], "samples": t["samples"]}
        for s in ("q", "qd", "qdd"):
            for j in joints:
                row[f"{short(j)}_{s}_span"] = t["span_pct"][j][s]
        row.update({"new_cells": t["new_cells"], "only_it_q_qd_cells": t["only_it_q_qd_cells"],
                    "tool_path_m": t["tool_path_m"], "tool_speed_max_m_s": t["tool_speed_max_m_s"],
                    "tool_z_min_mm": r(t["tool_z_min_m"] * 1000, 1), "tool_z_max_mm": r(t["tool_z_max_m"] * 1000, 1),
                    "tool_tilt_max_deg": t["tool_tilt_max_deg"],
                    # relative to THIS file (v1/rows/): the round's data/rrd/<name>.rrd
                    "rerun": "../../" + t["rrd"]})
        trows.append(row)
    write("trajectories", trows)


if __name__ == "__main__":
    main()
