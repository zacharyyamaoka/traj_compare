#!/usr/bin/env python3
"""ONE row set across every bench deployment, for the round's five stock <data-workbench> variants (CONTRACT, top part).

    python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/build_rows.py

Reads data/<site>.js (extract.py) for ur5e, ur5e_alone, bam_fb, pendulum; writes (data/ is gitignored):

    data/rows-runs.json      one row per measured line of every deployment (the rail filters these; "N of M runs")
    data/rows-targets.json   one row per target (Targets tab), linked one-way from the runs, so it lists only the
                             targets with a run left
    v1/views.base … v5/views.base   each variant's .base: the shared rail, League, Speed sweeps, Targets and Runs, plus
                             what its direction changes (see variant_base)

Stdlib only. Nothing invented: every number is the extract's per-line value; aggregation happens in the page (stock
Vega-Lite transforms), named on every figure. The model-type mapping below is a PROPOSAL, labelled so in the UI.
"""

from __future__ import annotations

import colorsys
import json
import re
import sys
from pathlib import Path

ROUND = Path(__file__).resolve().parent
DATA = ROUND / "data"
SITES = ("ur5e", "ur5e_alone", "bam_fb", "pendulum")

# Copied from arm_motion_bench src/arm_motion_bench/playback.py (DATASET_TITLES, DEPLOYMENT_TITLES, 2026-11-24): Zach's
# names. The same dataset key on two deployments is two datasets, so a dataset value here always carries its deployment.
DATASET_TITLES = {"workspace": "Entire Workspace", "conveyor": "Conveyor PnP", "impact": "Conveyor Collision"}
DEPLOYMENT_TITLES = {"ur5e": "UR5e + Conveyor PnP cell", "ur5e_alone": "UR5e", "bam_fb": "BAM FB",
                     "pendulum": "1-DOF pendulum"}

# PROPOSED — edit MODEL_TYPE. Config → model type, first matching rule wins (a regex on the config name). Nothing in the
# bench records a model type yet; this is the round's guess so the League can group across deployments.
MODEL_TYPE = [
    (r"^hold_friction", "friction hold"),
    (r"^record$", "record (no controller)"),
    (r"^(menagerie_stock|board_pd|jtc_baseline|fullarm_jtc baseline)$", "stock / PD gains"),
    (r"^(ctc_|id_pd$|fullarm_jtc model-FF|ff_model$|round9_ff$|twin_ff$|ff_board_i$|ff_hold$)",
     "computed torque / model feed-forward"),
]
MODEL_TYPE_OTHER = "other (one-off rig run)"
MODEL_TYPE_NOTE = "proposed — edit MODEL_TYPE in build_rows.py"


def model_type(config: str) -> str:
    for pattern, name in MODEL_TYPE:
        if re.search(pattern, config):
            return name
    return MODEL_TYPE_OTHER


def dataset_title(deployment: str, dataset: str) -> str:
    """('ur5e', 'conveyor-v1') -> 'Conveyor PnP v1 · UR5e + Conveyor PnP cell'; an unknown key passes through. WHY the
    dataset first: a narrow rail cuts the end of a label, and the deployment is its own facet just above."""
    key, _, version = dataset.partition("-")
    name = DATASET_TITLES.get(key)
    shown = f"{name} {version}".strip() if name else dataset
    return f"{shown} · {DEPLOYMENT_TITLES.get(deployment, deployment)}"


def load(site: str) -> dict:
    text = (DATA / f"{site}.js").read_text(encoding="utf-8")
    return json.loads(text[text.index(",") + 1:text.rindex(")")])


def rows_for(site: str):
    model = load(site)
    dims, T, L = model["dims"], model["targets"], model["lines"]
    joints, series_names, configs = model["joints"], model["series"], model["configs"]
    deployment = DEPLOYMENT_TITLES.get(site, site)

    def dim(key, i):
        v = T[key][i]
        return dims[key][v] if v is not None and v >= 0 else None

    runs, targets = [], {}
    for n, _ in enumerate(L["id"]):
        t = L["target"][n]
        config = configs[L["config"][n]]["name"]
        slug = T["slug"][t]
        target_key = f"{site}|{slug}"
        row = {
            "id": f"{site}:{n}", "site": site, "line": n, "deployment": deployment,
            "dataset": dataset_title(site, dim("dataset", t) or "all"), "split": dim("split", t),
            "speed": dim("speed", t), "kind": dim("kind", t),
            "model_type": model_type(config), "config": config, "series": series_names[L["series"][n]],
            "target": T["title"][t], "target_slug": slug, "target_key": target_key, "task": T["task"][t],
            "repeat": L["repeat"][n],
            "tcp": L["tcp"][n], "energy": L["energy"][n], "jerk": L["jerk"][n], "stop": L["stop"][n],
            "worst": L["worst"][n],
            "worst_joint": joints[L["worstJoint"][n]] if L["worstJoint"][n] >= 0 else None,
            "fb": L["fb"][n], "report": L["report"][n] or None,
            "run_report": f"/bench/{site}/runs/{L['report'][n]}/report.html" if L["report"][n] else None,
            "target_view": f"/common/target.html?site={site}&target={slug}",
            "rerun_runs": f"{site}:{n}",
        }
        runs.append(row)
        tr = targets.setdefault(target_key, {
            "id": target_key, "site": site, "target_slug": slug, "target_key": target_key, "deployment": deployment,
            "dataset": row["dataset"], "split": row["split"], "speed": row["speed"], "kind": row["kind"],
            "target": row["target"], "task": row["task"], "target_view": row["target_view"],
            "_lines": [], "_configs": set()})
        tr["_lines"].append(f"{site}:{n}")
        tr["_configs"].add(config)
    out_targets = []
    for tr in targets.values():
        lines = tr.pop("_lines")
        tr["runs_all"] = len(lines)
        tr["configs_all"] = len(tr.pop("_configs"))
        tr["rerun_runs"] = ",".join(lines)
        out_targets.append(tr)
    return runs, out_targets


NUM = {"tcp": ("Tool RMS", "mm"), "energy": ("Energy", "J"), "jerk": ("Tool jerk RMS", "m/s³"),
       "stop": ("Stop error (max)", "mm"), "worst": ("Worst-joint RMS", "°")}
TEXT = {"id": "Run", "site": "Site", "deployment": "Deployment", "dataset": "Dataset", "split": "Split",
        "kind": "Motion kind", "model_type": "Model type (proposed)", "config": "Config", "series": "Sim / real",
        "target": "Target", "target_slug": "Target slug", "target_key": "Target key", "task": "Task",
        "worst_joint": "Worst joint", "report": "Run folder", "run_report": "Run report", "target_view": "Target view",
        "rerun_runs": "Rerun runs"}


def schema(cols):
    props = {}
    for c in cols:
        if c in NUM:
            props[c] = {"type": "number", "label": NUM[c][0], "unitText": NUM[c][1], "digits": 3}
        elif c in ("line", "repeat", "runs_all", "configs_all"):
            props[c] = {"type": "number", "label": {"line": "Line", "repeat": "Repeat", "runs_all": "Runs (all)",
                                                    "configs_all": "Configs (all)"}[c]}
        elif c == "speed":
            props[c] = {"type": "number", "label": "Speed", "unitText": "×"}
        elif c == "fb":
            props[c] = {"type": "number", "label": "Feedback share", "digits": 3}
        else:
            props[c] = {"type": "text", "label": TEXT.get(c, c)}
    return props


def dataset_colors(values):
    """One distinct colour per dataset (golden-angle hues), so a dataset is one colour on every chart and badge."""
    out = {}
    for i, v in enumerate(sorted(values)):
        h = (i * 0.618033988749895) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, 0.45, 0.62)
        out[v] = "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    return out


# ── the .base ──────────────────────────────────────────────────────────────────────────────────────────────────────

AGG = "median over targets of median over its runs"


def league_chart(group: str, title_field: str):
    """Two-stage median from the RUNS (stock Vega-Lite): a target's value per group = median over its runs, the group's =
    median over targets; ranked at the fastest speed. WHY each median is written back as `tcp`: a log axis over a field
    the rows do not have drew nothing in data-ui's chart; WHY dots: a log axis has no zero for a bar."""
    return {
        "transform": [
            {"filter": "isValid(datum.tcp) && datum.tcp > 0"},
            {"aggregate": [{"op": "median", "field": "tcp", "as": "tcp"}], "groupby": [group, "target_key"]},
            {"aggregate": [{"op": "median", "field": "tcp", "as": "tcp"}, {"op": "count", "as": "n"}],
             "groupby": [group]},
            {"joinaggregate": [{"op": "min", "field": "tcp", "as": "best"}]},
            {"calculate": "datum.tcp / datum.best", "as": "ratio"},
            {"window": [{"op": "rank", "as": "rank"}], "sort": [{"field": "tcp", "order": "ascending"}]},
            {"calculate": "'#' + (datum.rank < 10 ? '0' : '') + datum.rank + '  ' + datum." + group
                          + " + '   ' + format(datum.tcp, '.3~g') + ' mm   ×' + (datum.ratio < 100 ? format(datum.ratio, '.3~g')"
                          " : format(datum.ratio, ',.0f')) + '   n=' + datum.n", "as": "label"},
        ],
        "mark": {"type": "point", "filled": True, "size": 120, "opacity": 1, "color": "#57606a"},
        "encoding": {"y": {"field": "label", "type": "nominal", "sort": {"field": "tcp"}, "title": None,
                           "axis": {"labelLimit": 460, "labelFontSize": 11, "labelOverlap": False}},
                     "x": {"field": "tcp", "type": "quantitative", "scale": {"type": "log"},
                           "title": f"tool tracking RMS at 1.0 ×, mm ({AGG}); n = targets"}},
    }


def shared_base(colors, deployments, model_types) -> dict:
    facets = [
        {"property": "deployment", "label": "Deployment", "order": deployments},
        {"property": "dataset", "label": "Dataset"},
        {"property": "split", "label": "Split"},
        {"property": "model_type", "label": "Model type (proposed)", "order": model_types},
        {"property": "config", "label": "Config"},
        {"property": "series", "label": "Sim / real"},
        {"property": "speed", "as": "values", "label": "Speed (× fastest)", "order": [0.1, 0.25, 0.5, 0.75, 1.0]},
        {"property": "kind", "label": "Motion kind"},
        {"property": "target", "label": "Target"},
        # WHY on `task` (searching target, config and task): two facets on one property share their typed text in
        # data-ui (the Target list's find box leaked into a Name search pill)
        {"property": "task", "as": "search", "properties": ["task", "target", "config"], "label": "Name search",
         "placeholder": "e.g. conveyor-dev-00 or ctc_tuned"},
    ]
    props = {
        "deployment": {"displayName": "Deployment"},
        "dataset": {"displayName": "Dataset", "colors": colors},
        "model_type": {"displayName": "Model type (proposed)"},
        "config": {"displayName": "Config"},
        "series": {"displayName": "Sim / real"},
        "target": {"displayName": "Target"},
        "tcp": {"displayName": "Tool RMS"},
        "run_report": {"displayName": "Run report"},
        "target_view": {"displayName": "Target view"},
    }
    views = [
        {"type": "chart", "name": "League", "filters": "speed == 1", "chart": league_chart("config", "config"),
         # WHY target_key in hover: data-ui hands Vega only the columns a channel or the hover names
         "hover": {"title": "config", "fields": ["tcp", "target_key"]}},
        {"type": "chart", "name": "League by model type", "filters": "speed == 1",
         "chart": league_chart("model_type", "model_type"),
         "hover": {"title": "model_type", "fields": ["tcp", "target_key"]}},
        {"type": "chart", "name": "Speed sweeps",
         "chart": {"transform": [
             {"filter": "isValid(datum.tcp) && datum.tcp > 0"},
             {"aggregate": [{"op": "median", "field": "tcp", "as": "tcp"}],
              "groupby": ["model_type", "dataset", "speed", "target_key"]},
             {"aggregate": [{"op": "median", "field": "tcp", "as": "tcp"}], "groupby": ["model_type", "dataset", "speed"]}],
             "mark": {"type": "line", "point": True},
             "encoding": {"x": {"field": "speed", "type": "quantitative", "title": "speed (× fastest)",
                                "scale": {"domain": [0, 1]}},
                          "y": {"field": "tcp", "type": "quantitative", "scale": {"type": "log"},
                                "title": "tool RMS, mm", "axis": {"grid": False, "tickCount": 4}},
                          "color": {"field": "dataset", "type": "nominal", "title": "Dataset"},
                          "facet": {"field": "model_type", "type": "nominal", "columns": 3, "title": None}}},
         "hover": {"title": "dataset", "fields": ["tcp", "target_key", "model_type"]}},
        {"type": "pivot", "name": "Model type × deployment", "order": ["model_type"], "splitBy": ["deployment"],
         "value": {"property": "tcp", "summary": "Median", "display": "dist"}},
        {"type": "table", "name": "Targets", "from": "targets",
         "order": ["target", "deployment", "dataset", "split", "speed", "kind", "runs_all", "configs_all", "target_view"],
         "sort": [{"property": "deployment", "direction": "ASC"}, {"property": "target", "direction": "ASC"}],
         "display": {"dataset": "badge", "target_view": "link"}},
        {"type": "table", "name": "Runs",
         "order": ["target", "config", "series", "repeat", "deployment", "dataset", "split", "speed", "model_type", "tcp",
                   "worst", "worst_joint", "fb", "energy", "target_view", "run_report"],
         "sort": [{"property": "tcp", "direction": "DESC"}],
         "display": {"dataset": "badge", "tcp": "bar", "target_view": "link", "run_report": "link"}},
    ]
    note = (f"**Read it.** The rail filters **runs** (one measured line each); every tab shows what is left. League: "
            f"each config's tool RMS at 1.0 ×, {AGG}, × best and n targets. Model type is **{MODEL_TYPE_NOTE}**. "
            "Colour = dataset (legend on the chart). No run carries a date yet, so there is no date range.")
    return {
        "data": "../data/rows-runs.json",
        "noun": ["run", "runs"],
        "facets": facets,
        "properties": props,
        "style": {"numbers": {"digits": 3}},
        "drill": {"actions": [
            {"label": "Open target view ↗", "href": "/common/target.html?site={site}&target={target_slug}",
             "title": "The target view of {target}"},
            {"label": "Open run report ↗", "href": "/bench/{site}/runs/{report}/report.html", "title": "The run report"},
            {"label": "Open in Rerun", "post": "/__rerun/selection?runs={rerun_runs}",
             "title": "Sends {rerun_runs} to Rerun"},
        ]},
        "datasets": {"runs": {"data": "../data/rows-runs.json", "label": "Runs"},
                     "targets": {"data": "../data/rows-targets.json", "label": "Targets"}},
        "links": [{"from": "runs.target_key", "to": "targets.target_key", "direction": "one-way"}],
        "pages": [
            {"name": "Overview", "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "League", "w": 7, "h": 5, "title": f"League · configs · tool RMS at 1.0 × · {AGG}"},
                {"view": "League by model type", "w": 5, "h": 3,
                 "title": f"League by model type ({MODEL_TYPE_NOTE})"},
                {"text": note, "w": 5, "h": 2, "title": "About"},
                {"view": "Speed sweeps", "w": 12, "h": 6,
                 "title": f"Speed sweeps · tool RMS vs speed per model type, one line per dataset · {AGG}"},
            ]}},
            {"name": "Targets", "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "Targets", "w": 12, "h": 7,
                 "title": "Targets with at least one run left · click one for its target view"},
            ]}},
            {"name": "Runs", "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "Runs", "w": 12, "h": 7,
                 "title": "Every run the rail keeps · click one: target view, run report, Rerun"},
            ]}},
        ],
        "views": views,
    }


def variant_base(v: int, base: dict) -> dict:
    b = json.loads(json.dumps(base))
    pages = {p["name"]: p for p in b["pages"]}
    if v == 1:
        pages["Runs"]["layout"]["panels"][0]["title"] = (
            "Every run the rail keeps · pick ONE target in the rail and its target view opens above this table")
    if v == 3:
        pages["Targets"]["layout"]["panels"][0]["title"] = (
            "Targets with at least one run left · Open target view adds a “Target · <task>” tab here")
    if v == 4:
        panels = pages["Overview"]["layout"]["panels"]
        pages["Overview"]["layout"]["panels"] = [
            {"view": "Model type × deployment", "w": 12, "h": 4,
             "title": f"Model type × deployment · tool RMS, median over runs, all speeds · n = runs ({MODEL_TYPE_NOTE})"},
            {"view": "League by model type", "w": 5, "h": 5, "title": f"League by model type · at 1.0 × · {AGG}"},
            {"view": "League", "w": 7, "h": 5, "title": f"League · configs · at 1.0 × · {AGG}"},
            panels[3],
        ]
        pages["Targets"]["layout"]["panels"][0]["title"] = (
            "Targets with at least one run left · Open target view opens it in the pane on the right")
    if v == 5:
        b["drill"]["actions"].insert(0, {"label": "＋ Add to selection", "copy": "{id}",
                                         "title": "Adds {id} to the selection basket (host)"})
        pages["Runs"]["layout"]["panels"][0]["title"] = (
            "Every run the rail keeps · click one, then ＋ Add to selection: the basket spans targets and deployments")
    return b


def main(argv):
    runs, targets = [], []
    for site in SITES:
        r, t = rows_for(site)
        runs += r
        targets += t
        print(f"{site}: {len(r)} runs, {len(t)} targets")
    colors = dataset_colors({r["dataset"] for r in runs})
    deployments = [DEPLOYMENT_TITLES[s] for s in SITES]
    model_types = [name for _, name in MODEL_TYPE] + [MODEL_TYPE_OTHER]
    run_cols = list(runs[0].keys())
    target_cols = list(targets[0].keys())
    (DATA / "rows-runs.json").write_text(json.dumps(
        {"id": "tc-runs", "title": "Every run of every bench deployment", "titleProperty": "target",
         "properties": schema(run_cols), "rows": runs}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "rows-targets.json").write_text(json.dumps(
        {"id": "tc-targets", "title": "Every target of every bench deployment", "titleProperty": "target",
         "properties": schema(target_cols), "rows": targets}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    base = shared_base(colors, deployments, model_types)
    for v in range(1, 6):
        path = ROUND / f"v{v}" / "views.base"
        path.parent.mkdir(exist_ok=True)
        header = (f"# V{v} .base, GENERATED by ../build_rows.py (edit that, then re-run it). JSON is YAML.\n")
        path.write_text(header + json.dumps(variant_base(v, base), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(runs)} runs, {len(targets)} targets, {len(colors)} datasets -> data/rows-*.json, v1..v5/views.base")
    unmapped = sorted({r["config"] for r in runs if r["model_type"] == MODEL_TYPE_OTHER})
    print("model type 'other':", unmapped)


if __name__ == "__main__":
    main(sys.argv[1:])
