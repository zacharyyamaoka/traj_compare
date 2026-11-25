"""The runs workbench's Overview and its "Does sim match real?" tab (docs/RUNS_WORKBENCH.md), the two AI picks made its
defaults on 2026-11-25:

- **The Overview: "Headline tiles → drill"** (O3 of docs/proposals/v2-overview-2026-11-24/, o3/NOTES.md). Six calm
  tiles, each a small host view whose Open chip (data-ui §55's ``open:``) goes to its own full page: the best config
  and the top five (→ League), how the best config's error grows with speed (→ Speed), the trade-off frontier against
  the first cost KPI (→ Trade-off), model × dataset coverage (→ Model × dataset), the best config's worst target
  (→ Worst targets) and the runs left (→ Targets). A tile whose data is absent is absent, with its page: one speed →
  no Speed; no cost KPI → no Trade-off. The round's other four Overviews are one word away (``overview="league"``,
  ``"matrix"``, ``"speed"``, ``"tradeoff"``: that view alone, full width), and V2's own (the Vega League, League by model
  type, Speed sweeps) is ``overview="v2"``.
- **"Does sim match real?"** (T1 of docs/proposals/v2-tabs-2026-11-24/, t1/NOTES.md). A page over ``pairs.json``: one
  row per real line and a prediction of it from the same run folder (every other line of the folder: a simulation, a
  rehearsal), built here from the runs, never by scraping. Linked one-way from the runs by the folder (``run_report``),
  so a pair stays while any run of its folder passes the rail. With no pair in the data there is no tab; a filter that
  leaves none gets one calm sentence (``tc-pairs``).

Both read one value per run, ``accuracy``: the League KPI where the run carries it, else traj_compare's own tool RMS
(the V2 rounds' rule, their ``extract.py``: "tcp falls back to rows[].tcp"), flagged ``accuracy_from`` on the row and
counted under every figure that reads it. WHY: some real runs carry no tool RMS tag (on the bench, every real run of one
arm), and without the stand-in they had no pair and no place in the League.

The page side is ``assets/runs_views.js`` (the host views, registered through data-ui's own ``registerView``) and
``assets/runs_views.css``. No bench names here: the KPIs, deployments, model types and configs are the caller's.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

OVERVIEWS = ("tiles", "league", "matrix", "speed", "tradeoff", "v2")
T1 = "Does sim match real?"
RULE = "median over targets of each target’s median over its runs"
FILL = "traj_compare's own tool RMS (robot_msgs.compare)"
_SINGLE = {"league": ("tc-league", "League"), "matrix": ("tc-matrix", None), "speed": ("tc-sweep", "Speed sweep"),
           "tradeoff": ("tc-tradeoff", "Trade-off map")}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


# ── the one value both read ─────────────────────────────────────────────────────────────────────────────────────────


def fill_accuracy(rows: list[dict], league: str, *, fallback: str | None) -> int:
    """Write each row's ``accuracy``: its ``league`` column, else (``fallback`` given) that column's value, flagged
    ``accuracy_from: "traj_compare"``. Returns how many rows were filled. The League's own column is never touched."""
    filled = 0
    for row in rows:
        value = _number(row.get(league))
        if value is None and fallback and _number(row.get(fallback)) is not None:
            value = _number(row[fallback])
            row["accuracy_from"] = "traj_compare"
            filled += 1
        row["accuracy"] = value
    return filled


# ── the Overview ────────────────────────────────────────────────────────────────────────────────────────────────────


def _view(kind: str, name: str, **tc: Any) -> dict:
    return {"type": kind, "name": name, **({"tc": tc} if tc else {})}


def _page(name: str, panels: list[dict]) -> dict:
    return {"name": name, "layout": {"columns": 12, "rowHeight": 88, "panels": panels}}


def overview_parts(kind: str, *, speeds: bool, costs: bool, typed: bool, acc_label: str,
                   type_label: str) -> tuple[dict, list[dict], list[dict]]:
    """(the Overview page, the pages after it, their views) for ``kind`` in OVERVIEWS minus "v2"."""
    matrix = "Model × dataset" if typed else "Config × dataset"
    matrix_title = (f"{type_label} › config × deployment › dataset · {acc_label}" if typed
                    else f"Config × deployment › dataset · {acc_label}")
    sweep_by = "model_type" if typed else "deployment"
    if kind in _SINGLE:
        view_type, name = _SINGLE[kind]
        name = name or matrix
        tc = {"axis": "dataset"} if kind == "matrix" else {"by": sweep_by} if kind == "speed" else {}
        titles = {"league": f"League · every config the filter leaves, at the fastest speed left · {RULE}",
                  "matrix": matrix_title, "speed": f"Speed sweeps · {acc_label} vs speed, one line per config · {RULE}",
                  "tradeoff": f"Trade-off · accuracy against cost, one point per config, per deployment · {RULE}"}
        return (_page("Overview", [{"view": name, "w": 12, "title": titles[kind]}]), [], [_view(view_type, name, **tc)])
    if kind != "tiles":
        raise ValueError(f"overview={kind!r}: one of {', '.join(map(repr, OVERVIEWS))}, a .base page, or None")
    # O3: §55's Overview grid, each tile a small view whose Open chip goes to its full view's page. WHY a missing
    # tile's width goes to the best config's: the first row stays one row (best, speed, cost)
    first = [("Best config", "best", "League", 6)]
    if speeds:
        first.append(("Speed growth", "speed", "Speed", 3))
    if costs:
        first.append(("Trade-off frontier", "cost", "Trade-off", 3))
    first[0] = (*first[0][:3], 12 - 3 * (len(first) - 1))
    tiles = [*first, (f"{matrix} coverage", "coverage", matrix, 6), ("Worst target", "worst", "Worst targets", 3),
             ("Runs left", "left", "Targets", 3)]
    panels = [{"view": name, "w": w, "h": 3, "open": page} for name, _, page, w in tiles]
    views = [_view("tc-tile", name, tile=tile) for name, tile, _, _ in tiles]
    pages = [("League", _view("tc-league", "League", matrix=False), f"League · {RULE}"),
             (matrix, _view("tc-matrix", matrix, axis="dataset"), matrix_title)]
    if speeds:
        pages.append(("Speed", _view("tc-sweep", "Speed sweep", by=sweep_by), f"Speed sweeps · one line per config · {RULE}"))
    if costs:
        pages.append(("Trade-off", _view("tc-tradeoff", "Trade-off map"), f"Trade-off · per deployment · {RULE}"))
    pages.append(("Worst targets", _view("tc-worst", "Worst targets"), "Worst targets · each opens its target view"))
    extra = [_page(name, [{"view": view["name"], "w": 12, "title": title}]) for name, view, title in pages]
    return _page("Overview", panels), extra, views + [view for _, view, _ in pages]


def config_order(rows: Sequence[dict], deployments: Sequence[str]) -> list[str]:
    """The configs' stable colour order (the round's build_bases.py): first deployment, then most runs, then name."""
    runs: dict[str, int] = defaultdict(int)
    first: dict[str, int] = {}
    for row in rows:
        runs[row["config"]] += 1
        at = deployments.index(row["deployment"]) if row["deployment"] in deployments else len(deployments)
        first[row["config"]] = min(first.get(row["config"], at), at)
    return sorted(runs, key=lambda c: (first[c], -runs[c], c))


# ── "Does sim match real?" ──────────────────────────────────────────────────────────────────────────────────────────


def build_pairs(rows: Sequence[dict], *, carry: Sequence[str]) -> list[dict]:
    """One row per real line and each prediction of it in the same run folder (every other line of the folder), both
    with an ``accuracy`` > 0. ``carry``: the real line's columns a pair keeps (the rail's tags)."""
    folders: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("run_report"):
            folders[row["run_report"]].append(row)
    out = []
    for folder, lines in folders.items():
        predictions = [row for row in lines if row["sim_real"] != "real"]
        for real in (row for row in lines if row["sim_real"] == "real"):
            for pred in predictions:
                a, b = _number(pred.get("accuracy")), _number(real.get("accuracy"))
                if a is None or b is None or a <= 0 or b <= 0:
                    continue
                exact = b / a
                # WHY 4 decimals: the round's pairs.json rounds so, and its oracle's median is over the rounded ratios
                ratio = round(exact, 4) or float(f"{exact:.4g}")
                pair = {"id": f"pair:{real['site']}:{pred['line']}~{real['line']}", "site": real["site"],
                        "target_slug": real["target_slug"], "target_key": real["target_key"], "target": real["target"],
                        "deployment": real["deployment"], "dataset": real["dataset"]}
                pair.update({column: real[column] for column in carry if column in real and column not in pair})
                pair.update(against=pred["series"], pred=a, real=b, ratio=ratio, apart=round(max(exact, 1 / exact), 4),
                            real_worse=int(exact > 1), pred_worst=pred.get("worst"), real_worst=real.get("worst"),
                            worst_joint=real.get("worst_joint"), keep=f"{pred['line']},{real['line']}",
                            run_report=folder, rerun_runs=f"{pred['rerun_runs']},{real['rerun_runs']}")
                for side, row in (("pred", pred), ("real", real)):
                    if row.get("accuracy_from"):
                        pair[f"{side}_from"] = row["accuracy_from"]
                out.append(pair)
    return out


def against_order(pairs: Sequence[dict]) -> list[str]:
    """The predictions, most pairs first (the default of the page's "Real against" control)."""
    counts: dict[str, int] = defaultdict(int)
    for pair in pairs:
        counts[pair["against"]] += 1
    return sorted(counts, key=lambda a: (-counts[a], a))


def pairs_schema(columns: Sequence[str], *, acc_label: str, unit: str, labels: Mapping[str, str]) -> dict:
    own = {
        "against": ("text", "Real against"), "pred": ("number", f"Predicted {acc_label}", unit),
        "real": ("number", f"Real {acc_label}", unit), "ratio": ("number", "Real ÷ predicted", "×"),
        "apart": ("number", "Apart (×, either way)", "×"), "real_worse": ("number", "Real worse (1 = yes)"),
        "pred_worst": ("number", "Predicted worst-joint RMS", "°"), "real_worst": ("number", "Real worst-joint RMS", "°"),
        "worst_joint": ("text", "Worst joint (real)"), "keep": ("text", "Lines"), "run_report": ("text", "Run report"),
        "rerun_runs": ("text", "Rerun runs"), "pred_from": ("text", f"Predicted {acc_label} from"),
        "real_from": ("text", f"Real {acc_label} from"),
    }
    props = {}
    for column in columns:
        if column in own:
            spec = own[column]
            props[column] = {"type": spec[0], "label": spec[1], **({"unitText": spec[2]} if len(spec) > 2 else {}),
                             **({"digits": 3} if spec[0] == "number" else {})}
        elif column in ("speed", "repeat", "line"):
            props[column] = {"type": "number", "label": labels.get(column, column)}
        else:
            props[column] = {"type": "text", "label": labels.get(column, column)}
    return props


def _line_with_points(transform: list[dict], encoding: dict) -> dict:
    """A line through aggregated points, as layers that each carry the aggregate, the line's name at its last point.
    WHY not ``mark.point: true``: data-ui drew that overlay from every row, not the aggregate (the round's gap 3)."""
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


def pairs_parts(pairs: Sequence[dict], *, acc_label: str, unit: str, speed_label: str) -> tuple[dict, list[dict]]:
    """(the "Does sim match real?" page, its views): the answer (``tc-pairs``), per config, each pair, the gap against
    speed (when the pairs have one), and the pairs that disagree most (a row drills to its target view)."""
    order = against_order(pairs)
    valid = {"filter": "isValid(datum.ratio) && datum.ratio > 0"}
    views: list[dict] = [
        {"type": "tc-pairs", "name": "Sim against real", "from": "pairs"},
        {"type": "chart", "name": "Sim against real per config", "from": "pairs", "chart": {
            "transform": [valid,
                          {"aggregate": [{"op": "median", "field": "ratio", "as": "ratio"}, {"op": "count", "as": "n"}],
                           "groupby": ["deployment", "config"]},
                          # WHY the deployment in the label: one config name on two robots is two points. WHY the
                          # number first: Vega cuts a long label at its end, and a cut name keeps its hover, a cut
                          # number is gone
                          # WHY a zero-padded rank: data-ui's chart ignores a sort after transforms (V2's gap 8)
                          {"window": [{"op": "rank", "as": "rank"}], "sort": [{"field": "ratio", "order": "descending"}]},
                          {"calculate": "'#' + (datum.rank < 10 ? '0' : '') + datum.rank + '  ×' + format(datum.ratio, '.3~g')"
                                        " + '  n=' + datum.n + '   ' + datum.config + ' · ' + datum.deployment",
                           "as": "label"}],
            "mark": {"type": "point", "filled": True, "size": 110, "opacity": 1, "color": "#57606a"},
            "encoding": {"y": {"field": "label", "type": "nominal", "sort": {"field": "ratio", "order": "descending"},
                               "title": None, "axis": {"labelLimit": 380, "labelFontSize": 11, "labelOverlap": False}},
                         "x": {"field": "ratio", "type": "quantitative", "scale": {"type": "log"},
                               "title": "real ÷ predicted, median over its pairs"}}},
         "guides": [{"rule": {"x": 1}, "label": "real = predicted"}],
         "hover": {"title": "config", "fields": ["ratio", "deployment", "config", "real_worse"]}},
        {"type": "chart", "name": "Sim against real each pair", "from": "pairs", "chart": {
            "transform": [valid],
            "mark": {"type": "point", "filled": True, "size": 26, "opacity": 0.55, "color": "#57606a"},
            "encoding": {"x": {"field": "pred", "type": "quantitative", "scale": {"type": "log"},
                               "title": f"predicted {acc_label}, {unit}"},
                         "y": {"field": "real", "type": "quantitative", "scale": {"type": "log"},
                               "title": f"real {acc_label}, {unit}"}}},
         "guides": [{"indexLine": {"slope": 1, "through": 1}, "label": "real = predicted"}],
         "hover": {"title": "target", "fields": ["config", "real", "pred", "ratio", "deployment"]}},
    ]
    has_speed = any(_number(pair.get("speed")) is not None for pair in pairs)
    if has_speed:
        views.append({"type": "chart", "name": "Sim against real by speed", "from": "pairs", "chart": _line_with_points(
            [valid, {"aggregate": [{"op": "median", "field": "ratio", "as": "ratio"}, {"op": "count", "as": "n"}],
                     "groupby": ["speed", "deployment"]}],
            {"x": {"field": "speed", "type": "quantitative", "title": speed_label},
             "y": {"field": "ratio", "type": "quantitative", "scale": {"type": "log"}, "title": "real ÷ predicted (median)"},
             "detail": {"field": "deployment", "type": "nominal"}}),
            "guides": [{"rule": {"y": 1}}], "hover": {"title": "deployment", "fields": ["ratio", "speed"]}})
    present = {column for pair in pairs for column in pair}
    table = [c for c in ("target", "config", "against", "deployment", "dataset", "speed", "repeat", "pred", "real", "ratio",
                         "apart", "pred_worst", "real_worst", "worst_joint", "real_from", "pred_from") if c in present]
    views.append({"type": "table", "name": "Sim against real, most apart", "from": "pairs", "order": table,
                  "sort": [{"property": "apart", "direction": "DESC"}], "display": {"dataset": "badge", "apart": "bar"}})
    panels = [{"view": "Sim against real", "w": 12, "title": f"The answer · median real ÷ predicted {acc_label} over the pairs"},
              {"view": "Sim against real per config", "w": 6 if has_speed else 7, "h": 5,
               "title": "Per config · real ÷ predicted, median over its pairs"},
              {"view": "Sim against real each pair", "w": 3 if has_speed else 5, "h": 5,
               "title": f"Each pair · predicted against real {acc_label}"}]
    if has_speed:
        panels.append({"view": "Sim against real by speed", "w": 3, "h": 5, "title": "Does the gap grow with speed? · median per speed"})
    panels.append({"view": "Sim against real, most apart", "w": 12, "h": 5,
                   "title": "Where they disagree most · click one, then Open target view: the pair ticked"})
    page: dict[str, Any] = {"name": T1, "layout": {"columns": 12, "rowHeight": 88, "panels": panels}}
    if len(order) > 1:
        # WHY one prediction at a time by default: a run folder can hold two (a simulation and a rehearsal), and pooling
        # them would count one real run twice; the stock page-level select (§53) switches it, "any" pools them
        page["datasets"] = {"pairs": {"facets": [{"property": "against", "as": "select", "label": "Real against",
                                                  "order": order}],
                                      "filters": f'against == "{order[0]}"'}}
    return page, views
