"""The independent oracle for the runs workbench's two picks (tests/test_runs_workbench_picks*.py, 2026-11-25).

Plain loops and ``statistics.median`` over the rows the writer put in ``runs.json``, written apart from the page's
``assets/runs_views.js`` (so a shared mistake would have to be made twice), following the rounds' own oracles:

- the Overview "Headline tiles → drill": ``docs/proposals/v2-overview-2026-11-24/oracle.py`` (its ``state()["tiles"]``):
  a target's value for a config = the median over its runs; the config's = the median over its targets; at the fastest
  speed the filter leaves; n = targets;
- "Does sim match real?": ``docs/proposals/v2-tabs-2026-11-24/build_tabs.py`` (``build_pairs`` + its oracle): one pair
  per run folder holding a real line and a prediction of it; ratio = real ÷ predicted tool RMS; a pair stays while any
  run of its folder passes the rail.

The value both read is the V2 rounds' tool RMS: the run's own tag where it carries one, else traj_compare's tool RMS
(``extract.py``: "tcp falls back to rows[].tcp"). The oracle recomputes it from those two columns.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def accuracy(row: dict, league: str = "tcp_rms_mm") -> float | None:
    value = row.get(league)
    return value if number(value) else (row.get("tool_rms") if number(row.get("tool_rms")) else None)


def _valid(field: str, value, log: bool) -> bool:
    if not number(value):
        return False
    return value > 0 if (field == "accuracy" or log) else True


def target_values(rows, field: str, group_of: Callable, keep=lambda r: True, log=False) -> dict:
    """{group: {target_key: median over its runs}}."""
    runs: dict = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row["accuracy"] if field == "accuracy" else row.get(field)
        if keep(row) and _valid(field, value, log):
            runs[group_of(row)][row["target_key"]].append(value)
    return {g: {t: statistics.median(vs) for t, vs in by.items()} for g, by in runs.items()}


def two_stage(rows, field, group_of, keep=lambda r: True, log=False) -> dict:
    """{group: (median over targets, n targets)}."""
    return {g: (statistics.median(list(tv.values())), len(tv))
            for g, tv in target_values(rows, field, group_of, keep, log).items()}


def config_order(rows_all: Sequence[dict], deployments: Sequence[str]) -> list[str]:
    """oracle.py's stable order: first deployment, then most runs, then name (it decides ties and colours)."""
    runs: dict = defaultdict(int)
    first: dict = {}
    for row in rows_all:
        runs[row["config"]] += 1
        first[row["config"]] = min(first.get(row["config"], 99), deployments.index(row["deployment"]))
    return sorted(runs, key=lambda c: (first[c], -runs[c], c))


def pareto(points):
    return [p for p in points if not any(q is not p and q[1] <= p[1] and q[2] <= p[2] and (q[1] < p[1] or q[2] < p[2])
                                         for q in points)]


def overview_tiles(rows: Sequence[dict], *, order: Sequence[str], deployments: Sequence[str], league: str = "tcp_rms_mm",
                   cost: str | None = "energy_j", cost_log: bool = False) -> dict:
    """The six tiles' numbers (oracle.py's ``tiles``) over ``rows`` (the runs the rail keeps)."""
    rows = [{**row, "accuracy": accuracy(row, league)} for row in rows]
    speeds_valid = {row["speed"] for row in rows if _valid("accuracy", row["accuracy"], True) and "speed" in row}
    top = max(speeds_valid) if speeds_valid else None
    speeds = sorted({row["speed"] for row in rows if "speed" in row})
    at_top = (lambda r: r.get("speed") == top) if top is not None else (lambda r: True)  # noqa: E731
    by_config = lambda r: r["config"]  # noqa: E731
    league_rows = sorted(((c, v, n) for c, (v, n) in two_stage(rows, "accuracy", by_config, at_top).items()),
                         key=lambda x: (x[1], order.index(x[0])))
    best = league_rows[0]
    tiles: dict = {"best": {"config": best[0], "v": best[1], "n": best[2], "configs": len(league_rows),
                            "next": [league_rows[1][0], league_rows[1][1] / best[1]] if len(league_rows) > 1 else None}}
    if len(speeds) > 1:
        by_speed = {s: two_stage(rows, "accuracy", by_config, lambda r, s=s: r.get("speed") == s).get(best[0])
                    for s in speeds}
        first = next(s for s in speeds if by_speed[s])
        tiles["speed"] = {"config": best[0], "from": first, "v0": by_speed[first][0], "v1": best[1],
                          "ratio": best[1] / by_speed[first][0]}
    per_target = target_values(rows, "accuracy", by_config, at_top)[best[0]]
    worst = max(per_target.items(), key=lambda kv: kv[1])
    tiles["worst"] = {"config": best[0], "target": worst[0], "v": worst[1], "ratio": worst[1] / best[1],
                      "targets": len(per_target)}
    group = (lambda r: r["model_type"]) if any("model_type" in r for r in rows) else by_config  # noqa: E731
    groups = {group(r) for r in rows}
    datasets = {r["dataset"] for r in rows}
    filled = {(group(r), r["dataset"]) for r in rows if _valid("accuracy", r["accuracy"], True)}
    tiles["coverage"] = {"filled": len(filled), "cells": len(groups) * len(datasets),
                         "pct": 100 * len(filled) / (len(groups) * len(datasets))}
    tiles["left"] = {"runs": len(rows), "targets": len({r["target_key"] for r in rows}),
                     "configs": len({r["config"] for r in rows}), "deployments": len({r["deployment"] for r in rows}),
                     "datasets": len(datasets)}
    if cost is not None:
        dep = sorted({r["deployment"] for r in rows if r["config"] == best[0]}, key=deployments.index)[0]
        y = two_stage(rows, "accuracy", lambda r: (r["deployment"], r["config"]), at_top)
        x = two_stage(rows, cost, lambda r: (r["deployment"], r["config"]), at_top, log=cost_log)
        points = [(c, x[(d, c)][0], v) for (d, c), (v, _) in y.items() if d == dep and (d, c) in x]
        front = pareto(points)
        accurate = min(front, key=lambda p: p[2])
        cheapest = min(front, key=lambda p: p[1])
        tiles["cost"] = {"deployment": dep, "frontier": sorted(p[0] for p in front),
                         "accurate": list(accurate), "cheapest": list(cheapest)}
    return tiles


def pairs(rows: Sequence[dict], league: str = "tcp_rms_mm") -> list[dict]:
    """build_tabs.py's rule: per run folder, each real line against each prediction (every other line of the folder),
    both with a tool RMS > 0; ratio = real ÷ predicted, rounded to 4 decimals as the round's."""
    folders: dict = defaultdict(list)
    for row in rows:
        if row.get("run_report"):
            folders[row["run_report"]].append(row)
    out = []
    for folder, lines in folders.items():
        for real in (r for r in lines if r["sim_real"] == "real"):
            for pred in (r for r in lines if r["sim_real"] != "real"):
                a, b = accuracy(pred, league), accuracy(real, league)
                if not (number(a) and a > 0 and number(b) and b > 0):
                    continue
                out.append({"folder": folder, "against": pred["series"], "deployment": real["deployment"],
                            "lines": sorted([pred["line"], real["line"]]), "site": real["site"],
                            "ratio": round(b / a, 4)})
    return out


def pairs_answer(all_pairs: Sequence[dict], kept_rows: Sequence[dict], against: str) -> dict:
    """{n, median, worse} of the pairs the rail keeps (a pair stays while any run of its folder passes)."""
    folders = {row["run_report"] for row in kept_rows if row.get("run_report")}
    kept = [p for p in all_pairs if p["folder"] in folders and p["against"] == against]
    return {"n": len(kept), "median": statistics.median([p["ratio"] for p in kept]) if kept else None,
            "worse": sum(p["ratio"] > 1 for p in kept)}
