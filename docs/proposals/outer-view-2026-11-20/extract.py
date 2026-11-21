#!/usr/bin/env python3
"""Compact data for the outer-view proposals (babble round 2026-11-20), read from a traj_compare site's index.html.

    python3 extract.py                       # the bench's three sites: ur5e, pendulum, bam_fb
    python3 extract.py /path/to/site [...]   # any traj_compare dataset site (a folder holding index.html)

Writes data/<site>.js as `window.OUTER_DATA = {...}`: a <script src> loads from file://, a fetch does not.
Stdlib only. Nothing here is invented: every number is either a bench scorecard value (summary.charts, copied)
or a per-run value from the payload, reduced by a named rule (median over repeats, then over targets).

What it keeps, and why each variant needs it:
- configs (levels.configs: name, colour, sim/real line counts) - the primary object of every variant.
- score: summary.charts parsed into kpi -> "dataset split" -> series -> value per speed (energy and jerk live only
  here), plus scoreN: how many targets of the payload sit under each scorecard cell (the n the bench's median is over).
- targets + rms + run: one tool-RMS value per (target, config, domain) - the median over that config's repeats of
  the bench's own per-run tag `<domain>_tcp_rms_mm` when the site has it (the scorecard's input), else
  traj_compare's rows[].tcp.rms for the pair (reference, domain). `run` keeps the slug suffix of the repeat
  closest to that median, so a drill lands on a real run report.
- oracle: the per-target values re-aggregated the scorecard's way (median over the split's tasks) and compared with
  every scorecard RMS cell, so the Overview can say how exactly it reproduces the bench.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DASHBOARD = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
DEFAULT_SITES = [DASHBOARD / name for name in ("ur5e", "pendulum", "bam_fb")]
# WHY a fixed server URL: Zach serves the bench's sites at this address (2026-11-20); the drill links must land on the
# real Target level and run reports there, not on a copy.
SERVER = "http://127.0.0.1:8779/"
PAYLOAD = re.compile(r'id="traj-compare-dataset">(.*?)</script>', re.S)
SPEED_KEYS = ("speed", "speed_fraction")
KPI_IDS = (("tracking rms", "rms"), ("gate", "gates"), ("energy", "energy"), ("jerk", "jerk"))


def sig(value: float | None, digits: int = 4) -> float | None:
    """Round to significant digits so the data file stays small; None stays None."""
    if value is None:
        return None
    if value == 0:
        return 0.0
    return float(f"{value:.{digits}g}")


def load_payload(site: Path) -> dict:
    text = (site / "index.html").read_text(encoding="utf-8")
    match = PAYLOAD.search(text)
    if not match:
        raise SystemExit(f"{site}/index.html has no traj-compare-dataset payload")
    return json.loads(match.group(1).replace("<\\/", "</"))


def kpi_id(name: str) -> str:
    low = name.lower()
    for needle, identifier in KPI_IDS:
        if needle in low:
            return identifier
    return re.sub(r"[^a-z0-9]+", "_", low).strip("_")


def first_number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def extract(site: Path) -> dict:
    payload = load_payload(site)
    levels = payload["levels"]
    tag_keys = payload.get("tag_keys", [])
    speed_key = next((key for key in SPEED_KEYS if key in tag_keys), None)
    domains = list(payload.get("series") or ["sim"])
    default_domain = domains[0]
    config_by = levels.get("config_by") or "controller"
    target_by = levels.get("target_by") or "target"

    runs = payload["runs"]
    run_by_name = {run["name"]: run for run in runs}
    tcp_by_pair = {}
    for row in payload["rows"]:
        if row.get("tcp") and row["pair"][0] == "reference":
            tcp_by_pair[(row["run"], row["pair"][1])] = row["tcp"]["rms"] * 1000.0

    # Targets, in the payload's order; each knows its dataset/split group and speed from its runs' tags.
    targets = levels["targets"]
    index_of = {target["slug"]: position for position, target in enumerate(targets)}
    meta: dict[int, dict] = {}
    for line in levels["lines"]:
        position = index_of[line["target"]]
        if position not in meta:
            tags = run_by_name[line["run"]]["tags"]
            meta[position] = {
                "dataset": str(tags.get("dataset", "all")),
                "split": str(tags.get("split", "")),
                "speed": tags.get(speed_key) if speed_key else None,
                "kind": tags.get("kind") or "",
            }

    # Series = (config, domain) pairs that carry lines.
    configs = levels["configs"]
    config_names = [config["name"] for config in configs]
    present = {(line["config"], line["series"]) for line in levels["lines"]}
    series = [
        {"key": f"{name}|{domain}", "config": name, "domain": domain}
        for name in config_names
        for domain in domains
        if (name, domain) in present
    ]

    # One value per (target, series): median over repeats; keep the run closest to it.
    per: dict[str, dict[int, list[tuple[float, str, int]]]] = defaultdict(lambda: defaultdict(list))
    source_used = defaultdict(int)
    source_by_series: dict[str, set] = defaultdict(set)
    for line in levels["lines"]:
        run = run_by_name[line["run"]]
        tag = f"{line['series']}_tcp_rms_mm"
        value = run["tags"].get(tag)
        key = f"{line['config']}|{line['series']}"
        if isinstance(value, (int, float)):
            source_used["tag"] += 1
            source_by_series[key].add("tag")
        else:
            value = tcp_by_pair.get((line["run"], line["series"]))
            if value is not None:
                source_used["rows"] += 1
                source_by_series[key].add("rows")
        if value is None:
            source_used["none"] += 1
            continue
        position = index_of[line["target"]]
        suffix = run["slug"][len(targets[position]["slug"]) :]
        per[key][position].append((float(value), suffix, run["tags"].get("repeat", 0)))

    n_targets = len(targets)
    rms_out: dict[str, list] = {}
    run_out: dict[str, list] = {}
    reps_out: dict[str, list] = {}
    for item in series:
        values, suffixes, reps = [None] * n_targets, [None] * n_targets, [0] * n_targets
        for position, entries in per[item["key"]].items():
            median = statistics.median(value for value, _, _ in entries)
            closest = min(entries, key=lambda entry: (abs(entry[0] - median), entry[2]))
            values[position], suffixes[position], reps[position] = sig(median), closest[1], len(entries)
        rms_out[item["key"]] = values
        run_out[item["key"]] = suffixes
        if any(count > 1 for count in reps):
            reps_out[item["key"]] = reps

    # Groups: dataset x split. Scorecard groups first, in the scorecard's own order.
    summary = payload.get("summary") or {}
    charts = summary.get("charts") or []
    chart_groups: list[str] = []
    for chart in charts:
        group = chart["title"].split(" · ", 1)[1] if " · " in chart["title"] else "all"
        if group not in chart_groups:
            chart_groups.append(group)
    payload_groups = []
    for position in range(n_targets):
        info = meta.get(position)
        if info:
            key = f"{info['dataset']} {info['split']}".strip()
            if key not in payload_groups:
                payload_groups.append(key)
    group_keys = chart_groups + sorted(key for key in payload_groups if key not in chart_groups)
    groups = []
    for key in group_keys:
        dataset, _, split = key.rpartition(" ")
        groups.append({"key": key, "dataset": dataset or key, "split": split if dataset else "", "scorecard": key in chart_groups})
    group_index = {group["key"]: position for position, group in enumerate(groups)}

    speeds = sorted({info["speed"] for info in meta.values() if info["speed"] is not None})
    speed_index = {speed: position for position, speed in enumerate(speeds)}

    columns = {"slug": [], "task": [], "g": [], "v": [], "kind": []}
    kinds: list[str] = []
    for position, target in enumerate(targets):
        info = meta.get(position, {"dataset": "all", "split": "", "speed": None, "kind": ""})
        columns["slug"].append(target["slug"])
        columns["task"].append(target["title"].split(" · ")[0])
        columns["g"].append(group_index[f"{info['dataset']} {info['split']}".strip()])
        columns["v"].append(speed_index.get(info["speed"], -1))
        if info["kind"] not in kinds:
            kinds.append(info["kind"])
        columns["kind"].append(kinds.index(info["kind"]))

    # Scorecard: kpi -> group -> series key -> values by speed index.
    kpis: list[dict] = []
    score: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: defaultdict(dict))
    speed_labels = {}
    for chart in charts:
        name, _, rest = chart["title"].partition(" vs ")
        group = chart["title"].split(" · ", 1)[1] if " · " in chart["title"] else "all"
        identifier = kpi_id(name)
        if identifier not in {kpi["id"] for kpi in kpis}:
            kpis.append({
                "id": identifier,
                "name": name.strip(),
                "unit": chart.get("unit") or "",
                "better": "higher" if identifier == "gates" else "lower",
                "description": chart.get("description") or "",
            })
        positions = []
        for category in chart["categories"]:
            value = first_number(category)
            match = min(speeds, key=lambda speed: abs(speed - value)) if speeds and value is not None else None
            positions.append(speed_index.get(match, -1))
            if match is not None:
                speed_labels[speed_index[match]] = category
        for entry in chart["series"]:
            config, _, domain = entry["name"].partition(" · ")
            key = f"{config}|{domain or default_domain}"
            values = [None] * len(speeds)
            for at, value in zip(positions, entry["values"]):
                if at >= 0:
                    values[at] = sig(value)
            score[identifier][group][key] = values

    # n behind each scorecard cell: targets of that group and speed with a value for the series.
    score_n: dict[str, dict[str, list]] = defaultdict(dict)
    for item in series:
        counts = defaultdict(lambda: [0] * len(speeds))
        for position, value in enumerate(rms_out[item["key"]]):
            if value is not None and columns["v"][position] >= 0:
                counts[groups[columns["g"][position]]["key"]][columns["v"][position]] += 1
        for group, values in counts.items():
            score_n[group][item["key"]] = values

    # Oracle: re-aggregate per-target values the scorecard's way and compare with every scorecard RMS cell.
    errors = []
    unbacked = []
    for group, by_series in score.get("rms", {}).items():
        for key, values in by_series.items():
            for at, published in enumerate(values):
                if published is None:
                    continue
                if key not in rms_out:
                    unbacked.append(f"{key.replace('|', ' · ')} · {group}")
                    continue
                mine = [
                    rms_out[key][position]
                    for position in range(n_targets)
                    if rms_out[key][position] is not None
                    and groups[columns["g"][position]]["key"] == group
                    and columns["v"][position] == at
                ]
                if not mine:
                    unbacked.append(f"{key.replace('|', ' · ')} · {group}")
                else:
                    recomputed = statistics.median(mine)
                    errors.append((abs(recomputed - published) / max(abs(published), 1e-12), group, key, at, published, recomputed))
    errors.sort(reverse=True)
    unbacked_groups = sorted(set(unbacked))
    oracle = {
        "cells": len(errors),
        "unbacked": len(unbacked),
        "unbackedSeries": unbacked_groups,
        "within1pct": sum(1 for error in errors if error[0] <= 0.01),
        "maxRelErr": sig(errors[0][0], 3) if errors else None,
        "medianRelErr": sig(statistics.median(error[0] for error in errors), 3) if errors else None,
        "worst": (
            f"{errors[0][2].replace('|', ' · ')} · {errors[0][1]} · {speeds[errors[0][3]]}: scorecard {errors[0][4]:.4g} mm, "
            f"per-target median {errors[0][5]:.4g} mm"
        ) if errors else "",
    }

    source = "bench tag <domain>_tcp_rms_mm" if source_used["tag"] and not source_used["rows"] else (
        "traj_compare rows[].tcp.rms" if source_used["rows"] and not source_used["tag"] else
        "bench tag <domain>_tcp_rms_mm where the run has it, else traj_compare rows[].tcp.rms"
    )
    n_lines = len(levels["lines"])
    real_lines = sum(1 for line in levels["lines"] if line.get("kind") == "real")
    name = site.name
    return {
        "site": name,
        "title": payload.get("title", name),
        "generated": payload.get("generated", ""),
        "siteUrl": f"{SERVER}{name}/",
        "counts": {"targets": n_targets, "runs": len(runs), "lines": n_lines, "real": real_lines, "sim": n_lines - real_lines},
        "configBy": config_by,
        "targetBy": target_by,
        "speedKey": speed_key,
        "speeds": speeds,
        "speedLabels": [speed_labels.get(at, f"{speed:g}") for at, speed in enumerate(speeds)],
        "domains": domains,
        "configs": [{"name": c["name"], "color": c["color"], "sim": c.get("sim", 0), "real": c.get("real", 0)} for c in configs],
        "series": series,
        "groups": groups,
        "kinds": kinds,
        "kpis": kpis,
        "score": score,
        "scoreN": score_n,
        "scoreSource": "results summary, the bench's scorecard (summary.charts)",
        "targets": columns,
        "rms": rms_out,
        "run": run_out,
        "reps": reps_out,
        "rmsSource": source,
        "rmsSourceCounts": dict(source_used),
        "rmsSourceBySeries": {key: "+".join(sorted(value)) for key, value in source_by_series.items()},
        "oracle": oracle,
    }


def main(argv: list[str]) -> int:
    sites = [Path(arg).resolve() for arg in argv] or DEFAULT_SITES
    out_dir = HERE / "data"
    out_dir.mkdir(exist_ok=True)
    for site in sites:
        data = extract(site)
        text = "window.OUTER_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
        out = out_dir / f"{site.name}.js"
        out.write_text(text, encoding="utf-8")
        oracle = data["oracle"]
        print(
            f"{out}: {len(text) / 1024:.0f} KiB · {data['counts']['targets']} targets · {len(data['configs'])} configs · "
            f"{len(data['series'])} series · {len(data['kpis'])} KPIs · speeds {data['speeds']} · rms from {data['rmsSourceCounts']} · "
            f"oracle {oracle['within1pct']}/{oracle['cells']} cells within 1 %, max rel err {oracle['maxRelErr']} "
            f"(median {oracle['medianRelErr']}), {oracle['unbacked']} scorecard cells with no payload runs behind them"
            + (f" worst: {oracle['worst']}" if oracle["worst"] else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
