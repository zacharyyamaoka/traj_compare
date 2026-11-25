#!/usr/bin/env python3
"""Make o1 … o5 from V2 (``../tensorboard-2026-11-24/v2/``, read-only): its ``views.base`` with ONLY the Overview page and
its views replaced, its ``index.html`` and ``host-common.js`` as they are, a ``host.js`` that is V2's plus the round's
host views (``kit/views.js``, registered through data-ui's ``registerView``), and each variant's ``gates.json`` (the
check's story).

    python3 /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/build_bases.py

Reads ``../tensorboard-2026-11-24/data/rows-runs.json`` only for the configs' stable colour order (deployment, then runs).
Stdlib only.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "tensorboard-2026-11-24" / "v2"
ROWS = HERE.parent / "tensorboard-2026-11-24" / "data" / "rows-runs.json"
DEPLOYMENTS = ["UR5e + Conveyor PnP cell", "UR5e", "BAM FB", "1-DOF pendulum"]
RULE = "median over targets of median over its runs"
UR5E_CELL = 'input[data-k="v:deployment:UR5e + Conveyor PnP cell"]'

NAMES = {
    "o1": "The League, back, over the rail",
    "o2": "Model × dataset matrix first",
    "o3": "Headline tiles → drill",
    "o4": "Speed is the x axis",
    "o5": "Trade-off map",
}


def config_order() -> list[str]:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))["rows"]
    runs = collections.Counter(r["config"] for r in rows)
    first = {}
    for r in rows:
        d = DEPLOYMENTS.index(r["deployment"]) if r["deployment"] in DEPLOYMENTS else 99
        first[r["config"]] = min(first.get(r["config"], 99), d)
    return sorted(runs, key=lambda c: (first[c], -runs[c], c))


def v2_base() -> dict:
    text = (V2 / "views.base").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):])


def host_view(kind: str, name: str, order: list[str], **tc) -> dict:
    return {"type": kind, "name": name, "tc": {"configOrder": order, **tc}}


def overview(v: str, order: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """(Overview panels, extra pages after the Overview, views) for one variant."""
    if v == "o1":
        return ([{"view": "League", "w": 12,
                  "title": f"League · every config the filter leaves, at the fastest speed left · {RULE}"}], [],
                [host_view("tc-league", "League", order)])
    if v == "o2":
        return ([{"view": "Model × dataset", "w": 12,
                  "title": "Model type (proposed) › config × deployment › dataset · tool tracking RMS"}], [],
                [host_view("tc-matrix", "Model × dataset", order, axis="dataset")])
    if v == "o4":
        return ([{"view": "Speed sweep", "w": 12,
                  "title": f"Speed sweeps · tool tracking RMS vs speed, one line per config · {RULE}"}], [],
                [host_view("tc-sweep", "Speed sweep", order, by="model_type")])
    if v == "o5":
        return ([{"view": "Trade-off map", "w": 12,
                  "title": f"Trade-off · accuracy against cost, one point per config, per deployment · {RULE}"}], [],
                [host_view("tc-tradeoff", "Trade-off map", order, cost="energy")])
    # o3: §55's Overview grid, each tile a small view whose title row (and Open chip) opens its full view's page
    tiles = [
        ("Best config", "best", "League", 6), ("Speed growth", "speed", "Speed", 3), ("Energy frontier", "cost", "Trade-off", 3),
        ("Model × dataset coverage", "coverage", "Model × dataset", 6), ("Worst target", "worst", "Worst targets", 3),
        ("Runs left", "left", "Targets", 3),
    ]
    panels = [{"view": name, "w": w, "h": 3, "open": page} for name, _, page, w in tiles]
    views = [host_view("tc-tile", name, order, tile=kind) for name, kind, _, _ in tiles]
    pages = [
        ("League", host_view("tc-league", "League", order, matrix=False), f"League · {RULE}"),
        ("Model × dataset", host_view("tc-matrix", "Model × dataset", order, axis="dataset"),
         "Model type (proposed) › config × deployment › dataset · tool tracking RMS"),
        ("Speed", host_view("tc-sweep", "Speed sweep", order, by="model_type"), f"Speed sweeps · one line per config · {RULE}"),
        ("Trade-off", host_view("tc-tradeoff", "Trade-off map", order, cost="energy"), f"Trade-off · per deployment · {RULE}"),
        ("Worst targets", host_view("tc-worst", "Worst targets", order), "Worst targets · each opens its target view"),
    ]
    extra = [{"name": p, "layout": {"columns": 12, "rowHeight": 88, "panels": [{"view": view["name"], "w": 12, "title": title}]}}
             for p, view, title in pages]
    return panels, extra, views + [view for _, view, _ in pages]


def base_for(v: str, order: list[str]) -> dict:
    b = v2_base()
    panels, extra, views = overview(v, order)
    keep = {"Targets", "Runs"}  # V2's views off the Overview (League, its model-type twin, Speed sweeps, the pivot go)
    b["views"] = views + [x for x in b["views"] if x["name"] in keep]
    pages = [p for p in b["pages"] if p["name"] != "Overview"]
    b["pages"] = [{"name": "Overview", "layout": {"columns": 12, "rowHeight": 88, "panels": panels}}] + extra + pages
    return b


def story(v: str) -> list[dict]:
    landing = {"label": "Landing", "actions": []}
    tick = {"label": "One deployment", "actions": [{"click": f"#tc data-facets {UR5E_CELL}"}, {"wait": 2500}]}
    own = {
        "o1": [{"label": "A column ranks the League", "actions": [
            {"click": "#tc .tc-heat th.tc-col:nth-of-type(3)"}, {"wait": 900}]},
               {"label": "A row's worst targets", "actions": [
                   {"click": "#tc .tc-ltable tbody tr:nth-child(1) [data-tc-worst]"}, {"wait": 1200}]}],
        "o2": [{"label": "Columns: speed", "actions": [{"click": "#tc [data-tc-axis=speed]"}, {"wait": 900}]},
               {"label": "A cell's worst targets", "actions": [{"click": "#tc .tc-nested tr.tc-leaf td[data-tc-cfg]"}, {"wait": 1200}]},
               {"label": "Fold a model type", "actions": [{"click": "#tc .tc-nested [data-tc-fold]"}, {"wait": 900}]}],
        "o3": [{"label": "Best config opens the League", "actions": [
            {"click": "#tc data-dashboard[tab='Overview'] .dd-panel:nth-of-type(1) button.dd-open"}, {"wait": 2000}]},
               {"label": "Worst target opens its page", "actions": [
                   {"click": "#tc data-tabs [role=tab]:nth-of-type(1)"}, {"wait": 1500},
                   {"click": "#tc data-dashboard[tab='Overview'] .dd-panel:nth-of-type(5) button.dd-open"}, {"wait": 2000}]}],
        "o4": [{"label": "One panel per deployment", "actions": [{"click": "#tc [data-tc-by=deployment]"}, {"wait": 900}]},
               {"label": "A value's worst targets", "actions": [{"click": "#tc .tc-stable tbody tr:nth-child(1) .tc-cellbtn"}, {"wait": 1200}]}],
        "o5": [{"label": "Cost: jerk", "actions": [{"click": "#tc [data-tc-cost=jerk]"}, {"wait": 900}]},
               {"label": "A config's worst targets", "actions": [{"click": "#tc .tc-stable tbody tr:nth-child(1) [data-tc-worst]"}, {"wait": 1200}]}],
    }[v]
    return [landing, tick, *own]


def gates(v: str) -> dict:
    g = json.loads((V2 / "gates.json").read_text(encoding="utf-8"))
    g["story"] = story(v)
    g["figure"] = "#tc data-dashboard[tab='Overview'] [data-tc-view]"
    g["filter"] = [{"click": f"#tc data-facets {UR5E_CELL}"}, {"wait": 2500}]
    tabs = ["Overview", "Targets", "Runs"] if v != "o3" else [
        "Overview", "League", "Model × dataset", "Speed", "Trade-off", "Worst targets", "Targets", "Runs"]
    g["tabs"] = [{"id": t.lower().replace(" × ", "-x-").replace(" ", "-"), "label": t,
                  "sel": f"#tc data-tabs [role=tab]:nth-of-type({i + 1})"} for i, t in enumerate(tabs)]
    g["target_link"][0]["click"] = f"#tc data-tabs [role=tab]:nth-of-type({tabs.index('Targets') + 1})"
    return g


HOST = """/* {v} "{name}" (V2's Overview round, 2026-11-24): V2's host.js (the target view as its own page, the filter carried)
   plus the round's host views, registered through data-ui's own registerView (CONTRACT §1) before the workbench reads
   views.base. GENERATED by ../build_bases.py. */
import {{ registerView }} from '../vendor/data-ui/data-ui.js';
import {{ registerOverviewViews }} from '../kit/views.js';
import {{ host }} from './host-common.js';

registerOverviewViews(registerView);
const api = host({{ variant: '{v}' }});
api.onDrill('Open target view', (row) => {{
  if (!row) return;
  const keep = api.keptLines(row.target_key);
  location.href = api.targetUrl(row, {{ keep: keep.join(','), back: location.href }});
}});
"""


def main() -> None:
    order = config_order()
    index = (V2 / "index.html").read_text(encoding="utf-8")
    common = (V2 / "host-common.js").read_text(encoding="utf-8")
    for v, name in NAMES.items():
        out = HERE / v
        out.mkdir(exist_ok=True)
        head = f"# {v.upper()} .base, GENERATED by ../build_bases.py from V2's (only the Overview changed). JSON is YAML.\n"
        (out / "views.base").write_text(head + json.dumps(base_for(v, order), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "index.html").write_text(
            index.replace('V2 "Two viewers, the filter carried"', f'{v.upper()} "{name}" (V2 with its Overview redone)')
            .replace("traj_compare · V2 Two viewers, the filter carried", f"traj_compare · {v.upper()} {name}")
            .replace("<h1>traj_compare · every deployment</h1>", f"<h1 title=\"traj_compare · every deployment · {v.upper()} {name}\">traj_compare · every deployment <span style=\"font-weight:400;color:#6e7781\">· {v.upper()} {name}</span></h1>"),
            encoding="utf-8")
        (out / "host-common.js").write_text(common.replace("identical copy in v1..v5; v1/host-common.js is the source",
                                                           "V2's, copied unchanged by ../build_bases.py"), encoding="utf-8")
        (out / "host.js").write_text(HOST.format(v=v, name=name), encoding="utf-8")
        (out / "gates.json").write_text(json.dumps(gates(v), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(order)} configs in colour order; wrote", ", ".join(NAMES))


if __name__ == "__main__":
    main()
