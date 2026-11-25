#!/usr/bin/env python3
"""Compact data for the TensorBoard-pattern round (babble 2026-11-24), read from the bench's traj_compare sites.

    python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/extract.py          # ur5e, bam_fb, pendulum
    python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/extract.py /path/to/site [...]

Writes data/<site>.js as `window.TC_SITE("<site>", {...})` (a <script src> loads from file://, a fetch does not).
Stdlib only. Nothing is invented: every number is a per-line value from the site's own payload (levels.lines,
runs[].tags, rows[].tcp), copied and rounded to 4 significant digits. Aggregation happens in the page, by named rules.

The drawn time series are NOT copied: a page loads `<bench>/<site>/targets/<slug>.js` (the site's own C5 file) on
demand, so every one of the site's targets can be drawn. Only each target's time axis (levels.targets[].t, kept in
index.html) is carried here: as [t0, t_end, n] when it is evenly spaced to 0.5 ms, else the full list in ms.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DASHBOARD = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
DEFAULT_SITES = [DASHBOARD / name for name in ("ur5e", "bam_fb", "pendulum")]
PAYLOAD = re.compile(r'id="traj-compare-dataset">(.*?)</script>', re.S)
DEG = 180.0 / 3.141592653589793
# the KPIs a line carries, by the bench's own run tags ({series} = the line's series); tcp falls back to rows[].tcp
KPIS = [
    {"id": "tcp", "tag": "{series}_tcp_rms_mm", "label": "tool tracking RMS", "unit": "mm", "log": True},
    {"id": "energy", "tag": "{series}_energy_j", "label": "energy per task", "unit": "J", "log": False},
    {"id": "jerk", "tag": "{series}_tcp_jerk_rms_m_s3", "label": "tool jerk RMS", "unit": "m/s³", "log": True},
    {"id": "stop", "tag": "{series}_stop_error_max_mm", "label": "stop error (max)", "unit": "mm", "log": True},
]


def sig(value, digits: int = 4):
    if value is None or not isinstance(value, (int, float)):
        return None
    if value == 0:
        return 0
    return float(f"{value:.{digits}g}")


def load_payload(site: Path) -> dict:
    match = PAYLOAD.search((site / "index.html").read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"{site}/index.html has no traj-compare-dataset payload")
    return json.loads(match.group(1).replace("<\\/", "</"))


def time_axis(t: list[float]):
    if len(t) < 2:
        return [t[0] if t else 0.0, t[0] if t else 0.0, len(t)]
    step = (t[-1] - t[0]) / (len(t) - 1)
    if all(abs(value - (t[0] + i * step)) < 5e-4 for i, value in enumerate(t)):
        return [round(t[0], 4), round(t[-1], 4), len(t)]
    return [round(value * 1000) for value in t]


def index_of(values: list, value) -> int:
    if value not in values:
        values.append(value)
    return values.index(value)


def extract(site: Path) -> dict:
    payload = load_payload(site)
    levels = payload["levels"]
    joints = payload["joint_names"]
    runs = {run["name"]: run for run in payload["runs"]}
    tcp_rows = {}
    for row in payload["rows"]:
        if row.get("tcp") and row["pair"][0] == "reference":
            tcp_rows[(row["run"], row["pair"][1])] = row["tcp"]["rms"] * 1000.0

    targets = levels["targets"]
    target_index = {target["slug"]: i for i, target in enumerate(targets)}
    dims = {"dataset": [], "split": [], "speed": [], "kind": []}
    tcol = {"slug": [], "title": [], "task": [], "dataset": [], "split": [], "speed": [], "kind": [], "t": [],
            "hz": []}
    meta_done = set()
    tcol_rows: dict[int, dict] = {}
    for line in levels["lines"]:
        position = target_index[line["target"]]
        if position in meta_done:
            continue
        meta_done.add(position)
        tags = runs[line["run"]]["tags"]
        tcol_rows[position] = {
            "dataset": str(tags.get("dataset", "all")),
            "split": str(tags.get("split", "")),
            "speed": tags.get("speed_fraction"),
            "kind": str(tags.get("kind") or "—"),
        }
    for position, target in enumerate(targets):
        info = tcol_rows.get(position, {"dataset": "all", "split": "", "speed": None, "kind": "—"})
        tcol["slug"].append(target["slug"])
        tcol["title"].append(target["title"])
        tcol["task"].append(target["title"].split(" · ")[0])
        for key in ("dataset", "split", "kind"):
            tcol[key].append(index_of(dims[key], info[key]))
        tcol["speed"].append(index_of(dims["speed"], info["speed"]) if info["speed"] is not None else -1)
        tcol["t"].append(time_axis(target.get("t") or []))
        tcol["hz"].append(sig(target.get("drawn_hz"), 3))

    # order the dimension values for display; remap the columns
    def reorder(key, sort_key=None):
        values = dims[key]
        order = sorted(range(len(values)), key=lambda i: sort_key(values[i]) if sort_key else str(values[i]))
        remap = {old: new for new, old in enumerate(order)}
        dims[key] = [values[i] for i in order]
        tcol[key] = [remap.get(v, -1) if v >= 0 else -1 for v in tcol[key]]

    reorder("dataset")
    reorder("split")
    reorder("kind")
    reorder("speed", lambda v: float(v))

    configs = levels["configs"]
    config_index = {config["name"]: i for i, config in enumerate(configs)}
    series_names: list[str] = list(payload.get("series") or ["sim"])
    lcol = {"id": [], "target": [], "config": [], "series": [], "kind": [], "repeat": [], "report": [],
            "worst": [], "worstJoint": [], "rms": [], "fb": []}
    for kpi in KPIS:
        lcol[kpi["id"]] = []
    for line in levels["lines"]:
        run = runs[line["run"]]
        tags = run["tags"]
        lcol["id"].append(line["id"])
        lcol["target"].append(target_index[line["target"]])
        lcol["config"].append(config_index[line["config"]])
        lcol["series"].append(index_of(series_names, line["series"]))
        lcol["kind"].append(1 if line["kind"] == "real" else 0)
        lcol["repeat"].append(tags.get("repeat", 0) if isinstance(tags.get("repeat"), int) else 0)
        report = line.get("report") or ""
        lcol["report"].append(report[len("runs/"):-len("/report.html")] if report.startswith("runs/") else report)
        lcol["worst"].append(sig((line.get("worst_rms") or 0) * DEG) if line.get("worst_rms") is not None else None)
        lcol["worstJoint"].append(joints.index(line["worst_joint"]) if line.get("worst_joint") in joints else -1)
        rms = line.get("rms") or {}
        lcol["rms"].append([sig(rms[j] * DEG) if rms.get(j) is not None else None for j in joints])
        torque = line.get("torque") or {}
        lcol["fb"].append(sig(torque.get("fb_share"), 3))
        for kpi in KPIS:
            value = tags.get(kpi["tag"].replace("{series}", line["series"]))
            if kpi["id"] == "tcp" and not isinstance(value, (int, float)):
                value = tcp_rows.get((line["run"], line["series"]))
            lcol[kpi["id"]].append(sig(value))

    coverage = payload.get("coverage") or {}
    return {
        "site": site.name,
        "title": payload["title"],
        "generated": payload.get("generated"),
        "bench": f"../../../../../arm_motion_bench/reports/media/dashboard/{site.name}/",
        "coverage": coverage.get("href"),
        "joints": joints,
        "series": series_names,
        "configBy": levels.get("config_by"),
        "configs": [{"name": c["name"], "color": c["color"], "sim": c.get("sim", 0), "real": c.get("real", 0),
                     "fb": sig(c.get("fb_share_median"), 3)} for c in configs],
        "dims": dims,
        "kpis": [{k: v for k, v in kpi.items() if k != "tag"} for kpi in KPIS],
        "sweep": {k: payload["sweep"].get(k) for k in ("x", "x_label", "y_label", "unit", "facet_by")}
        if payload.get("sweep") else None,
        "targets": tcol,
        "lines": lcol,
    }


def main(argv: list[str]) -> None:
    sites = [Path(arg) for arg in argv] or DEFAULT_SITES
    out = HERE / "data"
    out.mkdir(exist_ok=True)
    for site in sites:
        model = extract(site)
        text = json.dumps(model, separators=(",", ":"), ensure_ascii=False)
        path = out / f"{site.name}.js"
        path.write_text(f"window.TC_SITE({json.dumps(site.name)}, {text});\n", encoding="utf-8")
        print(f"{path}: {len(text) / 1e6:.2f} MB, {len(model['targets']['slug'])} targets, "
              f"{len(model['lines']['id'])} lines, {len(model['configs'])} configs")


if __name__ == "__main__":
    main(sys.argv[1:])
