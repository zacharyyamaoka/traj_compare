#!/usr/bin/env python3
"""The round's independent oracle: every number the five Overviews state, recomputed in Python from the same rows, for the
two states of the shared scenario (no filter; Deployment = "UR5e + Conveyor PnP cell") and the one switch each variant's
walkthrough makes (O2 columns = speed, O4 panels = deployment, O5 cost = jerk).

    python3 /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/oracle.py

Writes ``oracle.json`` beside this file. Written apart from ``kit/model.js`` (plain loops over the rows, statistics.median),
so a shared mistake would have to be made twice. The rule: a target's value for a group = the median over its runs; the
group's = the median over its targets; at the fastest speed the filter leaves.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = HERE.parent / "tensorboard-2026-11-24" / "data" / "rows-runs.json"
CELL = "UR5e + Conveyor PnP cell"
DEPLOYMENTS = ["UR5e + Conveyor PnP cell", "UR5e", "BAM FB", "1-DOF pendulum"]
MODEL_TYPES = ["computed torque / model feed-forward", "stock / PD gains", "friction hold", "record (no controller)",
               "other (one-off rig run)"]


def js_number(v):
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def ok(field, v):
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        return False
    return v > 0 if field == "tcp" else True


def target_values(rows, field, group_of, keep=lambda r: True):
    """{group: {target_key: median over its runs}} over the rows that pass keep and have a valid field."""
    runs = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if keep(r) and ok(field, r[field]):
            runs[group_of(r)][r["target_key"]].append(r[field])
    return {g: {t: statistics.median(vs) for t, vs in by.items()} for g, by in runs.items()}


def two_stage(rows, field, group_of, keep=lambda r: True):
    """{group: (median over targets, n targets)}."""
    return {g: (statistics.median(list(tv.values())), len(tv)) for g, tv in target_values(rows, field, group_of, keep).items()}


def config_order(rows_all):
    runs = defaultdict(int)
    first = {}
    for r in rows_all:
        runs[r["config"]] += 1
        d = DEPLOYMENTS.index(r["deployment"])
        first[r["config"]] = min(first.get(r["config"], 99), d)
    return sorted(runs, key=lambda c: (first[c], -runs[c], c))


def ranked(values, order):
    """[(config, v, n)] lowest first, ties by the stable order."""
    return sorted(((c, v, n) for c, (v, n) in values.items()), key=lambda x: (x[1], order.index(x[0])))


def pareto(points):
    return [p for p in points if not any(q is not p and q[1] <= p[1] and q[2] <= p[2] and (q[1] < p[1] or q[2] < p[2]) for q in points)]


def state(rows, order):
    tcp_speeds = {r["speed"] for r in rows if ok("tcp", r["tcp"])}
    top, slow = max(tcp_speeds), min(tcp_speeds)
    speeds = sorted({r["speed"] for r in rows})
    at_top = lambda r: r["speed"] == top  # noqa: E731
    by_cfg = lambda r: r["config"]  # noqa: E731
    league = ranked(two_stage(rows, "tcp", by_cfg, at_top), order)
    out = {"runs": len(rows), "top": top, "league": [[c, v, n] for c, v, n in league]}
    out["kpis"] = {k: {c: v for c, (v, _) in two_stage(rows, k, by_cfg, at_top).items()} for k in ("energy", "jerk", "stop")}
    # O1's League on one dataset · split (its chips and its matrix's column click)
    fac = lambda r: f"{r['dataset']} · {r['split']}"  # noqa: E731
    out["leagueByFacet"] = {}
    out["kpisByFacet"] = {}
    for f in sorted({fac(r) for r in rows}):
        keep = lambda r, f=f: r["speed"] == top and fac(r) == f  # noqa: E731
        out["leagueByFacet"][f] = [[c, v, n] for c, v, n in ranked(two_stage(rows, "tcp", by_cfg, keep), order)]
        out["kpisByFacet"][f] = {k: {c: v for c, (v, _) in two_stage(rows, k, by_cfg, keep).items()} for k in ("energy", "jerk", "stop")}
    # best in X of Y: every (dataset · split, speed) cell with two or more configs
    facet = lambda r: f"{r['dataset']} · {r['split']}"  # noqa: E731
    per_cell = two_stage(rows, "tcp", lambda r: (facet(r), r["speed"], r["config"]))
    cells = defaultdict(dict)
    for (f, s, c), (v, _) in per_cell.items():
        cells[(f, s)][c] = v
    wins = defaultdict(lambda: [0, 0])
    n_cells = 0
    for cell in cells.values():
        if len(cell) < 2:
            continue
        n_cells += 1
        for c in cell:
            wins[c][1] += 1
        best = min(cell.items(), key=lambda kv: (kv[1], order.index(kv[0])))
        wins[best[0]][0] += 1
    out["wins"] = {"cells": n_cells, "byConfig": {c: w for c, w in wins.items()}}
    # O1's heat: config × dataset · split at the top speed
    heat = two_stage(rows, "tcp", lambda r: (r["config"], facet(r)), at_top)
    out["heat"] = [[c, f, v, n] for (c, f), (v, n) in heat.items()]
    # O2's matrix, two axes
    def matrix(axis):
        if axis == "speed":
            # WHY js_number: the page keys a speed column by JavaScript's String(1.0) = "1", not Python's "1.0"
            col, keep, allk = (lambda r: js_number(r["speed"])), (lambda r: True), (lambda r: True)
        else:
            col, keep, allk = (lambda r: r[axis]), at_top, at_top
        leaf = two_stage(rows, "tcp", lambda r: (r["config"], col(r)), keep)
        grp = two_stage(rows, "tcp", lambda r: (r["model_type"], col(r)), keep)
        best = {}
        for (c, k), (v, _) in leaf.items():
            if k not in best or v < best[k][1]:
                best[k] = (c, v)
        return {"leaf": [[c, k, v, n] for (c, k), (v, n) in leaf.items()],
                "group": [[g, k, v, n] for (g, k), (v, n) in grp.items()],
                "rollLeaf": {c: v for c, (v, _) in two_stage(rows, "tcp", by_cfg, allk).items()},
                "rollGroup": {g: v for g, (v, _) in two_stage(rows, "tcp", lambda r: r["model_type"], allk).items()},
                "best": {k: [c, v] for k, (c, v) in best.items()}}
    out["matrix"] = {"dataset": matrix("dataset"), "speed": matrix("speed")}
    # O4's sweep: config × speed (panels by model type pool a config's deployments; by deployment split them)
    sweep = two_stage(rows, "tcp", lambda r: (r["config"], r["speed"]))
    out["sweep"] = [[c, s, v, n] for (c, s), (v, n) in sweep.items()]
    sweep_dep = two_stage(rows, "tcp", lambda r: (r["deployment"], r["config"], r["speed"]))
    out["sweepByDeployment"] = [[d, c, s, v, n] for (d, c, s), (v, n) in sweep_dep.items()]
    slow_best = ranked(two_stage(rows, "tcp", by_cfg, lambda r: r["speed"] == slow), order)[0]
    fast = league[0]
    fast_slow = two_stage(rows, "tcp", by_cfg, lambda r: r["speed"] == slow).get(fast[0])
    out["sweepAnswer"] = {"slow": [slow_best[0], slow_best[1]], "fast": [fast[0], fast[1]],
                          "growth": fast[1] / fast_slow[0] if fast_slow else None}
    # O5's trade-off: per deployment, (cost, tool RMS) at the top speed, the frontier
    def tradeoff(cost):
        y = two_stage(rows, "tcp", lambda r: (r["deployment"], r["config"]), at_top)
        x = two_stage(rows, cost, lambda r: (r["deployment"], r["config"]), at_top)
        points, front = [], []
        for d in DEPLOYMENTS:
            pts = [(c, x[(dd, c)][0], v, n) for (dd, c), (v, n) in y.items() if dd == d and (dd, c) in x
                   and (cost == "energy" or x[(dd, c)][0] > 0)]
            points += [[d, c, xv, yv, n] for c, xv, yv, n in pts]
            front += [[d, p[0]] for p in pareto(pts)]
        return {"points": points, "frontier": front}
    out["tradeoff"] = {"energy": tradeoff("energy"), "jerk": tradeoff("jerk")}
    # O3's tiles
    best = league[0]
    tv_best = target_values(rows, "tcp", by_cfg, at_top)[best[0]]
    worst_t = max(tv_best.items(), key=lambda kv: kv[1])
    by_speed = {s: two_stage(rows, "tcp", by_cfg, lambda r, s=s: r["speed"] == s).get(best[0]) for s in speeds}
    first_speed = next(s for s in speeds if by_speed[s])
    model_types = {r["model_type"] for r in rows}
    datasets = {r["dataset"] for r in rows}
    filled = {(r["model_type"], r["dataset"]) for r in rows if ok("tcp", r["tcp"])}
    dep = sorted({r["deployment"] for r in rows if r["config"] == best[0]}, key=DEPLOYMENTS.index)[0]
    e = out["tradeoff"]["energy"]
    pts = [p for p in e["points"] if p[0] == dep]
    front = [p for p in pts if [dep, p[1]] in e["frontier"]]
    acc = min(front, key=lambda p: p[3])
    cheap = min(front, key=lambda p: p[2])
    out["tiles"] = {
        "best": {"config": best[0], "v": best[1], "n": best[2], "next": [league[1][0], league[1][1] / best[1]] if len(league) > 1 else None},
        "speed": {"config": best[0], "from": first_speed, "v0": by_speed[first_speed][0], "v1": best[1], "ratio": best[1] / by_speed[first_speed][0]},
        "worstList": [[t, v] for t, v in sorted(tv_best.items(), key=lambda kv: -kv[1])[:25]],
        "worst": {"config": best[0], "target": worst_t[0], "v": worst_t[1], "ratio": worst_t[1] / best[1], "targets": len(tv_best)},
        "coverage": {"filled": len(filled), "cells": len(model_types) * len(datasets), "pct": 100 * len(filled) / (len(model_types) * len(datasets))},
        "left": {"runs": len(rows), "targets": len({r["target_key"] for r in rows}), "configs": len({r["config"] for r in rows}),
                 "deployments": len({r["deployment"] for r in rows}), "datasets": len(datasets)},
        "cost": {"deployment": dep, "frontier": sorted(p[1] for p in front), "accurate": [acc[1], acc[2], acc[3]], "cheapest": [cheap[1], cheap[2], cheap[3]]},
    }
    return out


def main() -> None:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))["rows"]
    order = config_order(rows)
    oracle = {"all": state(rows, order), "ur5e_cell": state([r for r in rows if r["deployment"] == CELL], order)}
    (HERE / "oracle.json").write_text(json.dumps(oracle, ensure_ascii=False), encoding="utf-8")
    for k, s in oracle.items():
        print(k, s["runs"], "runs; best", s["league"][0], "; wins cells", s["wins"]["cells"])


if __name__ == "__main__":
    main()
