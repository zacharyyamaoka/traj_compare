#!/usr/bin/env python3
"""Rows and .base files for the V2-tabs round (babble, 2026-11-24): three proposals for a fourth tab on V2's workbench.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/build_tabs.py [--cells]

Reads V2's rows and site extracts (../tensorboard-2026-11-24/data/, built there by extract.py + build_rows.py; READ-ONLY)
and, with --cells, the bench's own per-target drawn series (targets/<slug>.js: each line's joint error at 50 Hz) and
reference trajectories (references/<sha>.npz). Writes, into data/ (gitignored):

    pairs.json      T1: one row per run folder that holds a REAL line and its prediction (the sim twin, or the pendulum's
                    rehearsal of the real plan): the same commanded motion, predicted and measured
    h2h.json        T3: one row per (target, sim/real, config A, config B) where both configs ran that target: the median
                    tool RMS over each config's runs of it
    t2-cells.json   T2 (--cells): each target's cells on the bench's own q x qd coverage grid per joint (coverage.json,
                    the same 36 x 24 cells as the Coverage page), and each line's RMS joint error within each cell
    oracle.json     what each tab must show, unfiltered and after its scenario's one rail pick, computed here from the
                    same rows (check.cjs compares the page with it)

and t1/views.base, t2/views.base, t3/views.base: V2's .base unchanged plus the one new page (and its dataset + links).

Nothing invented: every number is a bench value or an aggregate of bench values named on its figure.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROUND = Path(__file__).resolve().parent
V2_ROUND = ROUND.parent / "tensorboard-2026-11-24"
SRC = V2_ROUND / "data"
DATA = ROUND / "data"
BENCH = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
SITES = ("ur5e", "ur5e_alone", "bam_fb", "pendulum")

T1 = "Does sim match real?"
T2 = "Where in the workspace is it worst?"
T3 = "Which config wins head to head?"
AGAINST = {"sim": "sim twin", "rehearsal": "rehearsal"}  # the prediction a real line is paired with
TIE = 0.05  # T3: B within ±5 % of A is a tie (stated on the page)
DEFAULT_A, DEFAULT_B = "ctc_tuned", "ctc_tuned_v2"  # T3's default match-up: the incumbent UR5e tune and its successor
# each tab's scenario: unfiltered, then ONE rail pick (check.cjs ticks it, the oracle recounts it)
SCENARIO = {
    "t1": {"facet": "deployment", "value": "BAM FB"},
    "t2": {"facet": "config", "value": "ctc_tuned"},
    "t3": {"facet": "speed", "value": 1.0},
}
MIN_TARGETS = 3  # T2: a cell is a candidate for "worst" only with this many targets through it (one target is noise)


def load_site(site: str) -> dict:
    text = (SRC / f"{site}.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def runs_rows() -> list[dict]:
    return json.loads((SRC / "rows-runs.json").read_text(encoding="utf-8"))["rows"]


def write(name: str, payload) -> None:
    path = DATA / name
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{path}: {path.stat().st_size / 1e6:.2f} MB")


def median(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.median(values) if values else None


def ok(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v) and v > 0


def target_link(site: str, slug: str, keep) -> str:
    return f"/common/target.html?site={site}&target={slug}&keep={','.join(str(k) for k in keep)}"


# ── T1: sim (or rehearsal) against real, per run folder ─────────────────────────────────────────────────────────────

PASS = ("deployment", "dataset", "split", "speed", "kind", "model_type", "config", "target", "target_slug", "target_key",
        "task", "repeat", "site", "report")


def build_pairs(rows: list[dict]) -> list[dict]:
    by: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        if r["report"]:
            by[(r["site"], r["report"])][r["series"]] = r
    out, skipped = [], 0
    for (site, report), series in sorted(by.items()):
        real = series.get("real")
        if not real:
            continue
        for key, word in AGAINST.items():
            pred = series.get(key)
            if not pred:
                continue
            if not (ok(pred["tcp"]) and ok(real["tcp"])):
                skipped += 1
                continue
            ratio = real["tcp"] / pred["tcp"]
            keep = [pred["line"], real["line"]]
            out.append({
                "id": f"{site}|{report}|{key}", **{k: real[k] for k in PASS}, "against": word,
                "pred_tcp": pred["tcp"], "real_tcp": real["tcp"], "ratio": round(ratio, 4),
                "apart": round(max(ratio, 1 / ratio), 4), "real_worse": 1 if ratio > 1 else 0,
                "pred_worst": pred["worst"], "real_worst": real["worst"], "worst_joint": real["worst_joint"],
                "keep": ",".join(map(str, keep)), "rerun_runs": f"{site}:{keep[0]},{site}:{keep[1]}",
                "target_view": target_link(site, real["target_slug"], keep),
            })
    print(f"T1 pairs: {len(out)} ({skipped} skipped: no tool RMS on one side)")
    return out


PAIR_PROPS = {
    "against": ("text", "Real against"), "pred_tcp": ("number", "Predicted tool RMS", "mm"),
    "real_tcp": ("number", "Real tool RMS", "mm"), "ratio": ("number", "Real ÷ predicted", "×"),
    "apart": ("number", "Apart (×)", "×"), "real_worse": ("number", "Real worse (1 = yes)"),
    "pred_worst": ("number", "Predicted worst-joint RMS", "°"), "real_worst": ("number", "Real worst-joint RMS", "°"),
    "worst_joint": ("text", "Worst joint (real)"), "keep": ("text", "Lines"), "rerun_runs": ("text", "Rerun runs"),
    "target_view": ("text", "Target view"),
}


# ── T3: config A against config B, per target ───────────────────────────────────────────────────────────────────────

def build_h2h(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    meta = {}
    for r in rows:
        if not ok(r["tcp"]):
            continue
        groups[(r["target_key"], r["series"])][r["config"]].append(r)
        meta[r["target_key"]] = r
    out = []
    for (tk, series), configs in sorted(groups.items()):
        names = sorted(configs)
        if len(names) < 2:
            continue
        m = meta[tk]
        med = {c: median([r["tcp"] for r in configs[c]]) for c in names}
        for a in names:
            for b in names:
                if a == b:
                    continue
                ratio = med[b] / med[a]
                verdict = "B better" if ratio < 1 - TIE else "A better" if ratio > 1 + TIE else "tie (within 5 %)"
                keep = [r["line"] for r in configs[a]] + [r["line"] for r in configs[b]]
                out.append({
                    # WHY so few columns: 26k match-ups; the rail's facets reach them through the links, not columns
                    "id": f"h{len(out)}", "site": m["site"], "target_slug": m["target_slug"], "deployment": m["deployment"], "dataset": m["dataset"], "speed": m["speed"],
                    "target": m["target"], "target_key": tk, "series": series, "config_a": a, "config_b": b,
                    "a": round(med[a], 4), "b": round(med[b], 4), "ratio": round(ratio, 4),
                    "change": round((ratio - 1) * 100, 2), "verdict": verdict,
                    "b_better": int(verdict == "B better"), "a_better": int(verdict == "A better"),
                    "tie": int(verdict.startswith("tie")), "n_a": len(configs[a]), "n_b": len(configs[b]),
                    "keep": ",".join(map(str, keep)),
                })
    print(f"T3 match-ups: {len(out)} rows")
    return out


H2H_PROPS = {
    "series": ("text", "Sim / real"), "config_a": ("text", "Config A"), "config_b": ("text", "Config B"),
"a": ("number", "A tool RMS", "mm"), "b": ("number", "B tool RMS", "mm"),
    "ratio": ("number", "B ÷ A", "×"), "change": ("number", "B against A", "%"), "verdict": ("text", "Verdict"),
    "b_better": ("number", "B better (1 = yes)"), "a_better": ("number", "A better (1 = yes)"),
    "tie": ("number", "Tie (1 = yes)"), "n_a": ("number", "A runs"), "n_b": ("number", "B runs"),
    "keep": ("text", "Lines"),
}


def dataset_file(rows: list[dict], props: dict, title: str, rid: str) -> dict:
    base = json.loads((SRC / "rows-runs.json").read_text(encoding="utf-8"))["properties"]
    properties = {}
    for column in rows[0]:
        if column in props:
            spec = props[column]
            properties[column] = {"type": spec[0], "label": spec[1], **({"unitText": spec[2]} if len(spec) > 2 else {}),
                                  **({"digits": 3} if spec[0] == "number" else {})}
        elif column in base:
            properties[column] = base[column]
        else:
            properties[column] = {"type": "text", "label": column}
    return {"id": rid, "title": title, "titleProperty": "target", "properties": properties, "rows": rows}


# ── T2: the error over each joint's position × speed cells ──────────────────────────────────────────────────────────

def time_axis(spec, points: int):
    """data/<site>.js's targets.t: [t0, t_end, n] (s) when evenly spaced, else every drawn time in ms (extract.py);
    the target view's timeAxis() reads it the same way."""
    if len(spec) == points and points != 3:
        return [ms / 1000.0 for ms in spec]
    step = (spec[1] - spec[0]) / (points - 1) if points > 1 else 0.0
    return [spec[0] + i * step for i in range(points)]


def build_cells() -> dict:
    import numpy as np

    out = {"planes": {}, "targets": {}, "lines": {}, "joints": {}}
    for site in SITES:
        model = load_site(site)
        cov = json.loads((BENCH / site / "coverage" / "coverage.json").read_text(encoding="utf-8"))
        joints = model["joints"]
        planes = []
        for joint in joints:
            p = cov["planes"][joint]["q_qd"]
            (xl, xh, nx), (yl, yh, ny) = p["x_edges"], p["y_edges"]
            planes.append({"joint": joint, "x_lo": xl, "x_hi": xh, "nx": nx, "y_lo": yl, "y_hi": yh, "ny": ny})
        out["planes"][site] = planes
        out["joints"][site] = joints
        L, T = model["lines"], model["targets"]
        line_of = {line_id: n for n, line_id in enumerate(L["id"])}
        first = {}
        for n, t in enumerate(L["target"]):
            first.setdefault(t, n)
        lines: list = [None] * len(L["id"])
        for t, n0 in sorted(first.items()):
            slug = T["slug"][t]
            folder = BENCH / site / "runs" / L["report"][n0]
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            npz = np.load(folder / manifest["files"]["reference"])
            msg = json.loads(str(npz["__msg__"]))
            rt = npz[msg["t"]["npz"]]
            rq, rqd = npz[msg["positions"]["npz"]], npz[msg["velocities"]["npz"]]
            text = (BENCH / site / "targets" / f"{slug}.js").read_text(encoding="utf-8")
            drawn = json.loads(text[text.index("{"): text.rindex("}") + 1])
            points = drawn["points"]
            times = np.asarray(time_axis(T["t"][t], points))
            cells_per_joint, geometry = [], []
            for j, plane in enumerate(planes):
                q = np.interp(times, rt, rq[:, j])
                qd = np.interp(times, rt, rqd[:, j])
                ix = np.floor((q - plane["x_lo"]) / (plane["x_hi"] - plane["x_lo"]) * plane["nx"])
                iy = np.floor((qd - plane["y_lo"]) / (plane["y_hi"] - plane["y_lo"]) * plane["ny"])
                inside = (ix >= 0) & (ix < plane["nx"]) & (iy >= 0) & (iy < plane["ny"])
                cell = np.where(inside, ix * plane["ny"] + iy, -1).astype(np.int64)
                cells_per_joint.append(cell)
                at, n = np.unique(cell[cell >= 0], return_counts=True)
                geometry.append([int(v) for pair in zip(at, n) for v in pair])
            out["targets"][f"{site}|{slug}"] = geometry
            for line in drawn["lines"]:
                n = line_of.get(line["id"])
                if n is None or not line.get("e_deg"):
                    continue
                per_joint = []
                for j, cell in enumerate(cells_per_joint):
                    e = line["e_deg"][j] if j < len(line["e_deg"]) else None
                    if e is None:
                        per_joint.append([])
                        continue
                    e = np.asarray([np.nan if v is None else v for v in e], float)[: len(cell)]
                    c = cell[: len(e)]
                    good = (c >= 0) & np.isfinite(e)
                    if not good.any():
                        per_joint.append([])
                        continue
                    at, inverse = np.unique(c[good], return_inverse=True)
                    sq = np.bincount(inverse, weights=e[good] ** 2)
                    cnt = np.bincount(inverse)
                    rms = np.sqrt(sq / cnt)
                    # WHY ints of 1e-4 °: one compact list per line and joint, [cell, rms, cell, rms, ...]
                    per_joint.append([int(v) for pair in zip(at, np.rint(rms * 1e4).astype(np.int64)) for v in pair])
                lines[n] = per_joint
        out["lines"][site] = lines
        print(f"T2 {site}: {len(first)} targets, {sum(1 for x in lines if x is not None)} of {len(lines)} lines with cells")
    return out


def t2_aggregate(cells: dict, kept: list[dict]) -> dict:
    """The page's rule, independently: per joint plane, per cell, the median over the targets through it of (the median
    over its kept runs of their RMS joint error within that cell). The worst cell = the highest such value among cells
    with >= MIN_TARGETS targets."""
    by_target: dict[str, list[dict]] = defaultdict(list)
    for r in kept:
        by_target[r["target_key"]].append(r)
    values: dict[tuple, list] = defaultdict(list)
    for tk, runs in by_target.items():
        site = runs[0]["site"]
        for j in range(len(cells["planes"][site])):
            per_cell: dict[int, list] = defaultdict(list)
            for r in runs:
                entry = cells["lines"][site][r["line"]]
                if not entry:
                    continue
                flat = entry[j]
                for k in range(0, len(flat), 2):
                    per_cell[flat[k]].append(flat[k + 1] / 1e4)
            for cell, errs in per_cell.items():
                values[(site, j, cell)].append(statistics.median(errs))
    best = None
    planes = set()
    for (site, j, cell), vs in values.items():
        planes.add((site, j))
        if len(vs) >= MIN_TARGETS:
            m = statistics.median(vs)
            if best is None or m > best[0]:
                best = (m, site, j, cell, len(vs))
    every = [statistics.median(vs) for vs in values.values()]
    worst = None
    if best:
        m, site, j, cell, n = best
        worst = {"site": site, "joint": cells["planes"][site][j]["joint"], "cell": cell, "median": round(m, 4),
                 "targets": n}
    return {"planes": len(planes), "cells": len(values), "median_cell": round(statistics.median(every), 4) if every else None,
            "worst": worst}


# ── the .base files ─────────────────────────────────────────────────────────────────────────────────────────────────

def v2_base() -> dict:
    text = (V2_ROUND / "v2" / "views.base").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):])


def sentence(parts: list[str]) -> str:
    return " + ".join(parts)


def text_chart(headline: dict, detail: dict | None = None, pre: list[dict] | None = None) -> dict:
    """One calm answer: a sentence computed by Vega-Lite from the rows the page keeps (a text mark), and under it the
    lines that support it (one per group). Each is {"groupby", "aggregate", "text"} (text: a Vega expression).
    WHY pixel y ranges: the panel's plot is shorter than the chart's own canvas; fixed rows keep every line inside it."""
    def layer(spec, size, weight, rng):
        return {"transform": [*(pre or []), {"aggregate": spec["aggregate"], "groupby": spec["groupby"]},
                              *spec.get("then", []), {"calculate": spec["text"], "as": "answer"}],
                "mark": {"type": "text", "align": "left", "baseline": "middle", "fontSize": size, "fontWeight": weight,
                         "x": 4, "limit": 1300},
                "encoding": {"text": {"field": "answer", "type": "nominal"},
                             "y": {"field": spec["groupby"][0] if spec["groupby"] else "answer", "type": "nominal",
                                   "axis": None, "title": None,
                                   "scale": {"range": rng, "paddingInner": 0, "paddingOuter": 0.5}}}}
    layers = [layer(headline, 15, 600, [0, 22])]
    if detail:
        layers.append(layer(detail, 12.5, 400, [26, 74]))
    return {"layer": layers, "resolve": {"scale": {"y": "independent"}}}


def line_with_points(transform: list[dict], encoding: dict) -> dict:
    """A line through aggregated points, as layers that each carry the aggregate, the line's name at its last point.
    WHY not `mark.point: true`: data-ui drew that point overlay from every row, not the aggregate (each pair's ratio as
    a dot under the median line). WHY a name at the end, not a colour: both lines are grey (colour = dataset elsewhere)."""
    plain = {k: v for k, v in encoding.items() if k != "detail"}
    by = encoding["detail"]["field"]
    return {"layer": [
        {"transform": transform, "mark": {"type": "line", "color": "#57606a", "strokeWidth": 2}, "encoding": encoding},
        {"transform": transform, "mark": {"type": "point", "filled": True, "size": 60, "opacity": 1, "color": "#57606a"},
         "encoding": plain},
        {"transform": [*transform, {"joinaggregate": [{"op": "max", "field": "speed", "as": "last"}], "groupby": [by]},
                       {"filter": "datum.speed == datum.last"}],
         "mark": {"type": "text", "align": "right", "dx": -6, "dy": -9, "fontSize": 11, "color": "#57606a"},
         "encoding": {**plain, "text": {"field": by, "type": "nominal"}}},
    ]}


def t1_page_and_views() -> tuple[dict, list[dict]]:
    agg = "median real ÷ predicted tool RMS over the pairs"
    views = [
        {"type": "chart", "name": "T1 answer", "from": "pairs", "chart": text_chart(
            {"groupby": ["against"],
             "aggregate": [{"op": "median", "field": "ratio", "as": "med"}, {"op": "count", "as": "n"},
                           {"op": "sum", "field": "real_worse", "as": "worse"}],
             "text": "'On the real robot the tool error is ' + format(datum.med, '.2f') + '× what the ' + datum.against"
                     " + ' predicted: median real ÷ predicted over ' + format(datum.n, ',') + ' paired runs; real was worse in '"
                     " + format(datum.worse, ',') + ' (' + format(datum.worse / datum.n, '.0%') + ').'"},
            {"groupby": ["deployment"],
             "aggregate": [{"op": "median", "field": "ratio", "as": "med"}, {"op": "count", "as": "n"},
                           {"op": "sum", "field": "real_worse", "as": "worse"}],
             "text": "datum.deployment + ':  ×' + format(datum.med, '.2f') + ' over ' + format(datum.n, ',')"
                     " + ' pairs, real worse in ' + format(datum.worse / datum.n, '.0%')"},
            [{"filter": "isValid(datum.ratio) && datum.ratio > 0"}]),
         "hover": {"title": "against", "fields": ["ratio", "real_worse", "against", "deployment"]}},
        {"type": "chart", "name": "T1 per config", "from": "pairs", "chart": {
            "transform": [
                {"filter": "isValid(datum.ratio) && datum.ratio > 0"},
                {"aggregate": [{"op": "median", "field": "ratio", "as": "ratio"}, {"op": "count", "as": "n"}],
                 "groupby": ["deployment", "config"]},
                {"calculate": "datum.config + '   ×' + format(datum.ratio, '.3~g') + '   n=' + datum.n", "as": "label"}],
            "mark": {"type": "point", "filled": True, "size": 110, "opacity": 1, "color": "#57606a"},
            "encoding": {"y": {"field": "label", "type": "nominal", "sort": {"field": "ratio", "order": "descending"},
                               "title": None, "axis": {"labelLimit": 300, "labelFontSize": 11, "labelOverlap": False}},
                         "x": {"field": "ratio", "type": "quantitative", "scale": {"type": "log"},
                               "title": "real ÷ predicted tool RMS (median over its pairs)"}}},
         "guides": [{"rule": {"x": 1}, "label": "real = predicted"}],
         "hover": {"title": "config", "fields": ["ratio", "deployment", "real_worse"]}},
        {"type": "chart", "name": "T1 each pair", "from": "pairs", "chart": {
            "transform": [{"filter": "isValid(datum.ratio) && datum.ratio > 0"}],
            "mark": {"type": "point", "filled": True, "size": 26, "opacity": 0.55, "color": "#57606a"},
            "encoding": {"x": {"field": "pred_tcp", "type": "quantitative", "scale": {"type": "log"},
                               "title": "predicted tool RMS, mm"},
                         "y": {"field": "real_tcp", "type": "quantitative", "scale": {"type": "log"},
                               "title": "real tool RMS, mm"}}},
         "guides": [{"indexLine": {"slope": 1, "through": 1}, "label": "real = predicted"}],
         "hover": {"title": "target", "fields": ["config", "real_tcp", "pred_tcp", "ratio", "deployment"]}},
        {"type": "chart", "name": "T1 by speed", "from": "pairs", "chart": line_with_points(
            [{"filter": "isValid(datum.ratio) && datum.ratio > 0"},
             {"aggregate": [{"op": "median", "field": "ratio", "as": "ratio"}, {"op": "count", "as": "n"}],
              "groupby": ["speed", "deployment"]}],
            {"x": {"field": "speed", "type": "quantitative", "title": "speed (× fastest)", "scale": {"domain": [0, 1]}},
             "y": {"field": "ratio", "type": "quantitative", "scale": {"type": "log"}, "title": "real ÷ predicted (median)"},
             "detail": {"field": "deployment", "type": "nominal"}}),
         "guides": [{"rule": {"y": 1}}],
         "hover": {"title": "deployment", "fields": ["ratio", "speed"]}},
        {"type": "table", "name": "T1 disagree", "from": "pairs",
         "order": ["target", "config", "deployment", "dataset", "speed", "repeat", "pred_tcp", "real_tcp", "ratio", "apart",
                   "pred_worst", "real_worst", "worst_joint"],
         "sort": [{"property": "apart", "direction": "DESC"}],
         "display": {"dataset": "badge", "apart": "bar"}},
    ]
    page = {"name": T1,
            "datasets": {"pairs": {"facets": [{"property": "against", "as": "select", "label": "Real against",
                                               "order": list(AGAINST.values())}],
                                   "filters": 'against == "sim twin"'}},
            "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "T1 answer", "w": 12, "h": 2, "title": "The answer · " + agg},
                {"view": "T1 per config", "w": 6, "h": 5, "title": "Per config · real ÷ predicted, median over its pairs"},
                {"view": "T1 each pair", "w": 3, "h": 5, "title": "Each pair · predicted against real tool RMS"},
                {"view": "T1 by speed", "w": 3, "h": 5, "title": "Does the gap grow with speed? · median per speed"},
                {"view": "T1 disagree", "w": 12, "h": 5,
                 "title": "Where they disagree most · click one: its target view with the two lines checked"},
            ]}}
    return page, views


def t3_page_and_views() -> tuple[dict, list[dict]]:
    colors = {"B better": "#1f6feb", "tie (within 5 %)": "#8c959f", "A better": "#8250df"}
    views = [
        {"type": "chart", "name": "T3 answer", "from": "h2h", "chart": text_chart(
            {"groupby": ["config_a", "config_b"],
             "aggregate": [{"op": "count", "as": "n"}, {"op": "sum", "field": "b_better", "as": "bw"},
                           {"op": "sum", "field": "a_better", "as": "aw"}, {"op": "sum", "field": "tie", "as": "t"},
                           {"op": "median", "field": "ratio", "as": "med"}],
             "text": "'B ' + datum.config_b + ' beats A ' + datum.config_a + ' on ' + format(datum.bw, ',') + ' of '"
                     " + format(datum.n, ',') + ' targets they both ran, loses on ' + format(datum.aw, ',') + ', ties '"
                     " + format(datum.t, ',') + '; median B ÷ A = ' + format(datum.med, '.3~f') + ' ('"
                     " + (datum.med <= 1 ? 'B ' + format(1 - datum.med, '.0%') + ' better' : 'B ' + format(datum.med - 1, '.0%') + ' worse') + ').'"},
            {"groupby": ["config_a", "config_b"],
             # WHY argmax over `change`, not `ratio`: Vega-Lite merges both lines' aggregates (same groupby) into one,
             # and a median beside an argmax OF THE SAME FIELD reads a stale memo after a filter (vega TupleStore;
             # data-ui's chart notes it): the headline's median stayed at the unfiltered 0.570 once in three runs
             "aggregate": [{"op": "argmax", "field": "change", "as": "up"}, {"op": "argmin", "field": "change", "as": "down"}],
             "text": "'Biggest regression: ' + datum.up.tname + ' (B ' + format(datum.up.change / 100, '+.0%') + ')'"
                     " + '   ·   biggest gain: ' + datum.down.tname + ' (B ' + format(datum.down.change / 100, '+.0%') + ')'"},
            # WHY a calculate that reads datum.target: data-ui hands Vega only the columns a channel or a transform
            # names, and an argmax's row carries only those
            [{"calculate": "split(datum.target, ' · ')[0] + ' at ' + datum.speed + ' ×'", "as": "tname"}]),
         "hover": {"title": "target", "fields": ["ratio", "change", "verdict", "config_a", "config_b", "b_better", "a_better", "tie"]}},
        {"type": "chart", "name": "T3 by dataset", "from": "h2h", "chart": {
            "mark": {"type": "bar"},
            "encoding": {"y": {"field": "dataset", "type": "nominal", "title": None, "axis": {"labelLimit": 360}},
                         "x": {"aggregate": "count", "type": "quantitative", "title": "targets", "stack": "zero"},
                         "color": {"field": "verdict", "type": "nominal", "title": "Verdict",
                                   "scale": {"domain": list(colors), "range": list(colors.values())}},
                         "order": {"field": "verdict", "sort": "descending"}}},
         "hover": {"title": "dataset", "fields": ["verdict", "series"]}},
        {"type": "chart", "name": "T3 per target", "from": "h2h", "chart": {
            "mark": {"type": "point", "filled": True, "size": 30, "opacity": 0.6},
            "encoding": {"x": {"field": "a", "type": "quantitative", "scale": {"type": "log"}, "title": "A: tool RMS, mm (median over its runs)"},
                         "y": {"field": "b", "type": "quantitative", "scale": {"type": "log"}, "title": "B: tool RMS, mm (median over its runs)"},
                         "color": {"field": "verdict", "type": "nominal", "title": "Verdict",
                                   "scale": {"domain": list(colors), "range": list(colors.values())}}}},
         "guides": [{"indexLine": {"slope": 1, "through": 1}, "label": "B = A"}],
         "hover": {"title": "target", "fields": ["a", "b", "ratio", "series", "config_a", "config_b"]}},
        {"type": "chart", "name": "T3 by speed", "from": "h2h", "chart": line_with_points(
            [{"aggregate": [{"op": "median", "field": "ratio", "as": "ratio"}, {"op": "count", "as": "n"}],
              "groupby": ["speed", "series"]}],
            {"x": {"field": "speed", "type": "quantitative", "title": "speed (× fastest)", "scale": {"domain": [0, 1]}},
             "y": {"field": "ratio", "type": "quantitative", "title": "B ÷ A (median over targets)"},
             "detail": {"field": "series", "type": "nominal"}}),
         "guides": [{"rule": {"y": 1}}],
         "hover": {"title": "series", "fields": ["ratio", "speed"]}},
        {"type": "table", "name": "T3 regressed", "from": "h2h", "filters": 'verdict == "A better"',
         "order": ["target", "config_b", "config_a", "b", "a", "change", "dataset", "speed", "series", "n_a", "n_b"],
         "sort": [{"property": "ratio", "direction": "DESC"}],
         "display": {"dataset": "badge", "change": "bar"}},
    ]
    page = {"name": T3,
            "datasets": {"h2h": {"facets": [
                {"property": "config_a", "as": "select", "label": "A · current", "dropdown": True},
                {"property": "config_b", "as": "select", "label": "B · candidate", "dropdown": True}],
                "filters": {"and": [f'config_a == "{DEFAULT_A}"', f'config_b == "{DEFAULT_B}"']}}},
            "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "T3 answer", "w": 12, "h": 2,
                 "title": "The answer · per target: median tool RMS over each config's runs; a tie is within 5 %"},
                {"view": "T3 by dataset", "w": 5, "h": 4, "title": "Wins, ties and losses per dataset · targets"},
                {"view": "T3 per target", "w": 4, "h": 4, "title": "Each target · A against B"},
                {"view": "T3 by speed", "w": 3, "h": 4, "title": "Does it hold with speed? · median B ÷ A"},
                {"view": "T3 regressed", "w": 12, "h": 5,
                 "title": "Where B regressed most · click one: its target view with A's and B's runs checked"},
            ]}}
    return page, views


def write_bases() -> None:
    base = v2_base()
    header = "# {v} .base, GENERATED by ../build_tabs.py: V2's own .base (../../tensorboard-2026-11-24/v2/) plus ONE page. JSON is YAML.\n"
    # T1
    b = json.loads(json.dumps(base))
    page, views = t1_page_and_views()
    b["datasets"]["pairs"] = {"data": "../data/pairs.json", "label": "Sim ↔ real pairs"}
    b["links"].append({"from": "runs.report", "to": "pairs.report", "direction": "one-way"})
    b["properties"]["against"] = {"displayName": "Real against"}
    b["pages"].append(page)
    b["views"] += views
    (ROUND / "t1" / "views.base").write_text(header.format(v="T1") + json.dumps(b, indent=1, ensure_ascii=False) + "\n")
    # T2: the page is the host's (t2/host.js): the .base is V2's, unchanged
    (ROUND / "t2" / "views.base").write_text(header.format(v="T2").replace("plus ONE page", "unchanged; the T2 page is host.js's")
                                             + json.dumps(base, indent=1, ensure_ascii=False) + "\n")
    # T3
    b = json.loads(json.dumps(base))
    page, views = t3_page_and_views()
    b["datasets"]["h2h"] = {"data": "../data/h2h.json", "label": "Head to head"}
    # WHY four links, ANDed (data-ui §17 P1a): a match-up is kept only when its target, its sim/real and BOTH its configs
    # are among the runs the rail keeps ("runs are atomic: only runs passing every filter show")
    b["links"] += [{"from": "runs.target_key", "to": "h2h.target_key", "direction": "one-way"},
                   {"from": "runs.series", "to": "h2h.series", "direction": "one-way"},
                   {"from": "runs.config", "to": "h2h.config_a", "direction": "one-way"},
                   {"from": "runs.config", "to": "h2h.config_b", "direction": "one-way"}]
    b["properties"]["verdict"] = {"displayName": "Verdict"}
    b["pages"].append(page)
    b["views"] += views
    (ROUND / "t3" / "views.base").write_text(header.format(v="T3") + json.dumps(b, indent=1, ensure_ascii=False) + "\n")
    print("t1/t2/t3 views.base written")


# ── the oracle ──────────────────────────────────────────────────────────────────────────────────────────────────────

def keep(rows: list[dict], scenario: dict | None) -> list[dict]:
    if not scenario:
        return rows
    return [r for r in rows if r[scenario["facet"]] == scenario["value"]]


def oracle(rows, pairs, h2h, cells) -> dict:
    out = {}
    # T1: pairs whose run folder has a kept run (the one-way link runs.report -> pairs.report), "sim twin"
    for state in ("unfiltered", "scenario"):
        kept = keep(rows, SCENARIO["t1"] if state == "scenario" else None)
        reports = {r["report"] for r in kept}
        p = [x for x in pairs if x["report"] in reports and x["against"] == "sim twin"]
        out.setdefault("t1", {})[state] = {"n": len(p), "median": round(statistics.median([x["ratio"] for x in p]), 4) if p else None,
                                           "worse": sum(x["real_worse"] for x in p)}
    # T3: match-ups whose target, series and both configs are among the kept runs, A/B the defaults
    for state in ("unfiltered", "scenario"):
        kept = keep(rows, SCENARIO["t3"] if state == "scenario" else None)
        tk, se, cf = {r["target_key"] for r in kept}, {r["series"] for r in kept}, {r["config"] for r in kept}
        m = [x for x in h2h if x["config_a"] == DEFAULT_A and x["config_b"] == DEFAULT_B and x["target_key"] in tk
             and x["series"] in se and x["config_a"] in cf and x["config_b"] in cf]
        out.setdefault("t3", {})[state] = {"n": len(m), "b_better": sum(x["b_better"] for x in m),
                                           "a_better": sum(x["a_better"] for x in m), "tie": sum(x["tie"] for x in m),
                                           "median": round(statistics.median([x["ratio"] for x in m]), 4) if m else None}
    if cells:
        for state in ("unfiltered", "scenario"):
            kept = keep(rows, SCENARIO["t2"] if state == "scenario" else None)
            out.setdefault("t2", {})[state] = t2_aggregate(cells, kept)
    out["scenario"] = SCENARIO
    out["defaults"] = {"t3": [DEFAULT_A, DEFAULT_B]}
    return out


def main(argv: list[str]) -> None:
    DATA.mkdir(exist_ok=True)
    rows = runs_rows()
    pairs = build_pairs(rows)
    write("pairs.json", dataset_file(pairs, PAIR_PROPS, "Sim (or rehearsal) against real, per run folder", "tc-pairs"))
    h2h = build_h2h(rows)
    write("h2h.json", dataset_file(h2h, H2H_PROPS, "Config A against config B, per target", "tc-h2h"))
    cells = None
    if "--cells" in argv:
        cells = build_cells()
        write("t2-cells.json", cells)
    elif (DATA / "t2-cells.json").exists():
        cells = json.loads((DATA / "t2-cells.json").read_text(encoding="utf-8"))
    write_bases()
    result = oracle(rows, pairs, h2h, cells)
    (DATA / "oracle.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
