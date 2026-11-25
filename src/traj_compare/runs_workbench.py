"""The runs workbench: every run of several dataset sites in ONE stock data-ui ``<data-workbench>``, then the target view,
then playback (docs/RUNS_WORKBENCH.md; the round docs/proposals/tensorboard-2026-11-24/, its V2).

    sites = {"Arm cell": "dashboard/arm", "Pendulum": "dashboard/pendulum"}  # sites write_dataset_report wrote
    write_runs_workbench(sites, "dashboard/all", model_type={"pd_gains_v2": "PD gains", "model_ff": "feed-forward"})
    python -m traj_compare.serve dashboard      # then /all/index.html (the server builds run reports and playback)

Three levels (Zach, Daily Note 2026-11-24 l.3227: "We have like the dataset view, then the target view (at this point
its still just summary data though), Then we can actually open up the playback viewer. either our custom one or the
rerun one."):

1. ``index.html``: the dataset workbench. data-ui's ``<data-workbench src="runs.base">`` over ``runs.json``, one row per
   measured line (a run, to Zach) of every site. The rail filters runs across every deployment (deployment is a facet,
   never a split); tabs Overview · Targets · Runs; a Targets or Runs row's "Open target view" opens level 2 in the same
   tab with the rail's runs of that target ticked (``keep=``) and this page's URL, filter and tab included (``back=``).
2. ``target.html?site=<key>&target=<slug>&keep=<lines>&back=<url>``: one target's runs as summary data (a run list with
   checkboxes, the verdict, repeats as lines or bands, joint error per joint), from ``sites/<key>.js`` and the site's own
   ``targets/<slug>.js``. Its two buttons play the ticked runs back:
3. "Open playback": traj_compare's comparison viewer (``write_comparison_report``, called as it is) over that target and
   exactly the ticked runs, built by ``traj_compare.serve`` (``POST __playback``, ``selection.build_playback``); or
   "Open in Rerun": one recording, one plot per joint, one line per ticked run (``POST __rerun/selection``,
   ``selection.build_selection_rrd``, stock robot_msgs.viz.rerun). Each level's ‹ link returns with its state.

Written into ``out_dir``:

    runs.json       one row per line: deployment, dataset, the rail's run tags, model type (with ``model_type=``), config,
                    sim / real, speed, target, the KPIs (run tags; worst-joint RMS °, tool RMS mm, feedback share), links
    targets.json    one row per target (the Targets tab), linked one-way from the runs, so it lists only targets with a run
    runs.base       the rail, the pages (Overview · Targets · Runs, plus ``pages=``), the views, the drill actions
    index.html      the workbench and its host glue (assets/runs_host.js)
    target.html     the target view (assets/runs_target.js, .css; uPlot), every file inlined
    sites/<key>.js  per site, what the target view reads: its lines' numbers and its targets' time axes
    vendor/data-ui/ data-ui ``main`` vendored by its own ``data-ui vendor`` (unless ``kit=`` names one to reuse)

WHY from the sites' payloads (``dataset.read_site_payload``), never from the runs: the bench already wrote them (18,507
lines on four robots), and every number here is then the dataset view's own; nothing is recomputed but medians the views
take in the page, each named on its figure.

WHY no bench names here: the model types (``model_type=``), the dataset names (``dataset_titles=``) and the rail's run
tags (``rail=``, ``labels=``) are the caller's; the package knows only what ``write_dataset_report`` writes.
"""

from __future__ import annotations

import colorsys
import html
import importlib.resources
import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from . import _files
from .dataset import Metric, read_site_payload
from .report import SITUATION_PALETTE
from .runs_overview import (FILL, OVERVIEWS, RULE, against_order, build_pairs, config_order, fill_accuracy,
                            overview_parts, pairs_parts, pairs_schema)

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
DEG = 180.0 / math.pi
# V2's rail, in its order. A name is a column below or a run tag; one no row has a value for is left out. WHY "date":
# NAVIGATION.md Part A's date tag; V2's gap 1 (no bench run carries one yet), so it appears the day the runs do.
RAIL = ("deployment", "dataset", "split", "model_type", "config", "sim_real", "speed", "kind", "date", "target")
OTHER = "other"
_FIXED = {
    "id", "site", "line", "run", "deployment", "dataset", "target", "target_slug", "target_key", "config", "series",
    "sim_real", "speed", "model_type", "worst", "worst_joint", "tool_rms", "fb", "run_report", "rerun_runs",
    "accuracy", "accuracy_from",
}  # fmt: skip
LABELS = {
    "deployment": "Deployment", "dataset": "Dataset", "split": "Split", "model_type": "Model type", "config": "Config",
    "sim_real": "Sim / real", "series": "Series", "speed": "Speed", "kind": "Kind", "date": "Date", "target": "Target",
    "repeat": "Repeat",
    "worst": "Worst-joint RMS", "worst_joint": "Worst joint", "tool_rms": "Tool RMS (traj_compare)",
    "fb": "Feedback share", "run_report": "Run report", "target_slug": "Target slug", "target_key": "Target key",
    "run": "Run folder", "rerun_runs": "Rerun runs", "site": "Site", "line": "Line", "runs_all": "Runs (all)",
    "configs_all": "Configs (all)", "accuracy_from": "Overview value from",
}  # fmt: skip
UNITS = {"worst": "°", "tool_rms": "mm"}


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "site"


def _sites(sites: Mapping[str, Path | str] | Sequence[Path | str]) -> list[dict[str, Any]]:
    """[{title, path, key, payload}] in the given order: a Mapping is {deployment title: site dir}; a Sequence of site
    dirs takes each title from its page."""
    items = list(sites.items()) if isinstance(sites, Mapping) else [(None, path) for path in sites]
    if not items:
        raise ValueError("no sites given")
    out, keys = [], set()
    for title, path in items:
        path = Path(path)
        payload = read_site_payload(path)
        key, n = _slug(path.name), 2
        while key in keys:  # two sites in folders of one name stay two
            key, n = f"{_slug(path.name)}-{n}", n + 1
        keys.add(key)
        out.append({"title": str(title) if title is not None else payload["title"], "path": path, "key": key,
                    "payload": payload})
    titles = [site["title"] for site in out]
    if len(set(titles)) != len(titles):
        raise ValueError(f"two sites share a deployment title: {titles}")
    return out


def _kpi_id(tag: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", tag.replace("{series}_", "").replace("{series}", "").lower()).strip("_") or "kpi"


def _default_kpis(sites: list[dict[str, Any]]) -> list[Metric]:
    """Every site's sweep KPIs (its y, then its metrics), each tag once, in first-seen order."""
    seen: dict[str, Metric] = {}
    for site in sites:
        sweep = site["payload"].get("sweep")
        if not sweep:
            continue
        candidates = [Metric(sweep["y"], label=sweep.get("y_label") or sweep["y"], unit=sweep.get("unit") or "",
                             log=bool(sweep.get("log_y")))]
        candidates += [Metric(m["tag"], label=m.get("label"), unit=m.get("unit") or "", log=bool(m.get("log")),
                              better=m.get("better") or "lower") for m in sweep.get("metrics") or []]
        for metric in candidates:
            seen.setdefault(metric.tag, metric)
    return list(seen.values())


def _speed(sites: list[dict[str, Any]], speed: str | None) -> tuple[str | None, str]:
    if speed is not None:
        return speed, speed
    for site in sites:
        sweep = site["payload"].get("sweep")
        if sweep:
            return sweep["x"], sweep.get("x_label") or sweep["x"]
    return None, ""


def _lookup(mapping: Mapping[str, str] | Callable[[str], str | None] | None) -> Callable[[str], str | None] | None:
    if mapping is None:
        return None
    if isinstance(mapping, Mapping):
        return lambda value: mapping.get(value)
    return mapping


def _sig(value: Any, digits: int = 4) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    return 0.0 if value == 0 else float(f"{value:.{digits}g}")


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


# ── the rows ────────────────────────────────────────────────────────────────────────────────────────────────────────


def _target_name(target: Mapping[str, Any]) -> str:
    """A tagged target's own name (its tag value); a hashed one's title. WHY not always the title: a tagged target's
    title is its runs' shared title, which for a one-run target names that run's config too."""
    return str(target["key"]) if target.get("named_by") else str(target.get("title") or target["key"])


def _tool_rms_mm(payload: Mapping[str, Any]) -> dict[tuple[str, str], float]:
    out = {}
    for row in payload.get("rows") or []:
        pair = row.get("pair") or []
        if row.get("tcp") and len(pair) == 2 and pair[0] == "reference" and row["tcp"].get("rms") is not None:
            out[(row["run"], pair[1])] = row["tcp"]["rms"] * 1000.0
    return out


def _site_rows(site: dict[str, Any], out_dir: Path, *, dataset: str, dataset_title: Callable[[str], str | None] | None,
               model_type: Callable[[str], str | None] | None, tags: Sequence[str], target_tags: Sequence[str],
               kpis: Sequence[Metric], speed: str | None) -> tuple[list[dict], list[dict], dict]:
    """(run rows, target rows, the target view's site model) of one site."""
    payload, key, deployment = site["payload"], site["key"], site["title"]
    levels = payload["levels"]
    runs = {run["name"]: run for run in payload["runs"]}
    joints = list(payload.get("joint_names") or [])
    configs = [{"name": c["name"], "color": c["color"]} for c in levels.get("configs") or []]
    config_index = {c["name"]: i for i, c in enumerate(configs)}
    targets = list(levels.get("targets") or [])
    target_index = {target["slug"]: i for i, target in enumerate(targets)}
    tools = _tool_rms_mm(payload)
    href = Path(os.path.relpath(site["path"].resolve(), out_dir.resolve())).as_posix()
    series_names: list[str] = []
    lines = {k: [] for k in ("id", "target", "config", "series", "kind", "repeat", "run", "worst", "worstJoint", "tool",
                             "kpis", "fb")}
    rows, by_target = [], {}
    for n, line in enumerate(levels.get("lines") or []):
        run = runs[line["run"]]
        run_tags = run.get("tags") or {}
        series = line["series"]
        target = targets[target_index[line["target"]]]
        dataset_value = run_tags.get(dataset)
        shown = (dataset_title(str(dataset_value)) if dataset_title and dataset_value is not None else None) or dataset_value
        row: dict[str, Any] = {
            "id": f"{key}:{n}", "site": key, "line": n, "deployment": deployment,
            # WHY the deployment in every dataset value: the same dataset key on two robots is two datasets
            "dataset": f"{shown} · {deployment}" if shown is not None else deployment,
        }
        for tag in tags:
            if tag in run_tags and tag not in _FIXED:
                row[tag] = run_tags[tag]
        if model_type is not None:
            row["model_type"] = model_type(line["config"]) or OTHER
        row["config"] = line["config"]
        row["series"] = series
        row["sim_real"] = line["kind"]
        if speed is not None and _number(run_tags.get(speed)) is not None:
            row["speed"] = _number(run_tags[speed])
        row["target"] = _target_name(target)
        row["target_slug"] = target["slug"]
        row["target_key"] = f"{key}|{target['slug']}"
        values = []
        for metric in kpis:
            value = _number(run_tags.get(metric.tag.replace("{series}", series)))
            row[_kpi_id(metric.tag)] = value
            values.append(value)
        worst = _sig(line["worst_rms"] * DEG) if _number(line.get("worst_rms")) is not None else None
        row["worst"] = worst
        row["worst_joint"] = line.get("worst_joint")
        tool = _sig(tools.get((line["run"], series)))
        if tool is not None:
            row["tool_rms"] = tool
        fb = _sig(((line.get("torque") or {}).get("fb_share")), 3)
        if fb is not None:
            row["fb"] = fb
        report = line.get("report") or ""
        folder = report[: -len("/report.html")] if report.endswith("/report.html") else report
        row["run"] = folder.rpartition("/")[2]
        row["run_report"] = f"{href}/{report}" if report else None
        row["rerun_runs"] = f"{href}/{folder}:{series}" if folder else None
        rows.append(row)
        entry = by_target.setdefault(row["target_key"], {"row": row, "lines": 0, "configs": set()})
        entry["lines"] += 1
        entry["configs"].add(line["config"])
        if series not in series_names:
            series_names.append(series)
        lines["id"].append(line["id"])
        lines["target"].append(target_index[line["target"]])
        lines["config"].append(config_index.get(line["config"], -1))
        lines["series"].append(series_names.index(series))
        lines["kind"].append(1 if line["kind"] == "real" else 0)
        lines["repeat"].append(run_tags.get("repeat") if isinstance(run_tags.get("repeat"), int) else None)
        lines["run"].append(row["run"])
        lines["worst"].append(worst)
        lines["worstJoint"].append(joints.index(line["worst_joint"]) if line.get("worst_joint") in joints else -1)
        lines["tool"].append(tool)
        lines["kpis"].append(values)
        lines["fb"].append(fb)
    target_rows = []
    for target_key, entry in by_target.items():
        first = entry["row"]
        target_row = {"id": target_key, "site": key, "target_slug": first["target_slug"], "target_key": target_key,
                      "deployment": deployment, "dataset": first["dataset"]}
        # a target's rail tags and speed are its first run's (the bench tags them per target: dataset, split, kind)
        for column in (*target_tags, "speed"):
            if column in first:
                target_row[column] = first[column]
        target_row.update(target=first["target"], runs_all=entry["lines"], configs_all=len(entry["configs"]))
        target_rows.append(target_row)
    model = {
        "key": key, "title": payload.get("title") or deployment, "deployment": deployment, "href": href,
        "joints": joints, "series": series_names, "configs": configs,
        "kpis": [{"id": _kpi_id(m.tag), "label": m.label, "unit": m.unit} for m in kpis],
        "targets": {"slug": [t["slug"] for t in targets], "name": [_target_name(t) for t in targets],
                    "t": [_time_axis(t.get("t") or []) for t in targets]},
        "lines": lines,
    }
    return rows, target_rows, model


def _time_axis(t: Sequence[float]) -> list:
    """A target's drawn time axis for the target view: ``[t0, t_end, n]`` when evenly spaced to 0.5 ms, else
    ``["ms", ...every sample in ms]``. WHY compact: 2,000 targets at 50 Hz are about 3 MB as plain lists."""
    t = [float(v) for v in t]
    if len(t) < 2:
        return [t[0] if t else 0.0, t[0] if t else 0.0, len(t)]
    step = (t[-1] - t[0]) / (len(t) - 1)
    if all(abs(v - (t[0] + i * step)) < 5e-4 for i, v in enumerate(t)):
        return [round(t[0], 4), round(t[-1], 4), len(t)]
    return ["ms", *[round(v * 1000) for v in t]]


# ── the .base ───────────────────────────────────────────────────────────────────────────────────────────────────────

AGG = "median over targets of each target's median over its runs"


def _schema(columns: Sequence[str], labels: Mapping[str, str], kpis: Sequence[Metric], numeric: set[str]) -> dict:
    kpi = {_kpi_id(m.tag): m for m in kpis}
    props = {}
    for column in columns:
        if column in kpi:
            props[column] = {"type": "number", "label": kpi[column].label, "unitText": kpi[column].unit, "digits": 3}
        elif column in UNITS:
            props[column] = {"type": "number", "label": labels.get(column, column), "unitText": UNITS[column], "digits": 3}
        elif column == "fb":
            props[column] = {"type": "number", "label": labels["fb"], "digits": 3}
        elif column in numeric:
            props[column] = {"type": "number", "label": labels.get(column, column)}
        else:
            props[column] = {"type": "text", "label": labels.get(column, column)}
    return props


def dataset_colors(values: Sequence[str]) -> dict[str, str]:
    """One distinct colour per dataset (golden-angle hues), so a dataset is one colour on every chart and badge."""
    out = {}
    for i, value in enumerate(sorted(values)):
        r, g, b = colorsys.hls_to_rgb((i * 0.618033988749895) % 1.0, 0.45, 0.62)
        out[value] = "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    return out


def _league_chart(group: str, kpi: str, kpi_title: str) -> dict:
    """Two-stage median from the RUNS (stock Vega-Lite): a target's value per group = median over its runs, the group's =
    median over targets, ranked. WHY each median is written back as the KPI's name: a log axis over a field the rows do
    not have drew nothing in data-ui's chart; WHY dots: a log axis has no zero for a bar (v2/NOTES.md gap 8)."""
    return {
        "transform": [
            {"filter": f"isValid(datum.{kpi}) && datum.{kpi} > 0"},
            {"aggregate": [{"op": "median", "field": kpi, "as": kpi}], "groupby": [group, "target_key"]},
            {"aggregate": [{"op": "median", "field": kpi, "as": kpi}, {"op": "count", "as": "n"}], "groupby": [group]},
            {"joinaggregate": [{"op": "min", "field": kpi, "as": "best"}]},
            {"calculate": f"datum.{kpi} / datum.best", "as": "ratio"},
            {"window": [{"op": "rank", "as": "rank"}], "sort": [{"field": kpi, "order": "ascending"}]},
            # WHY a zero-padded rank in the label: a sort after transforms is ignored by data-ui's chart (gap 8)
            {"calculate": "'#' + (datum.rank < 10 ? '0' : '') + datum.rank + '  ' + datum." + group
                          + f" + '   ' + format(datum.{kpi}, '.3~g') + '   ×' + (datum.ratio < 100 ? format(datum.ratio, '.3~g')"
                          " : format(datum.ratio, ',.0f')) + '   n=' + datum.n", "as": "label"},
        ],
        "mark": {"type": "point", "filled": True, "size": 120, "opacity": 1, "color": "#57606a"},
        "encoding": {"y": {"field": "label", "type": "nominal", "sort": {"field": kpi}, "title": None,
                           "axis": {"labelLimit": 460, "labelFontSize": 11, "labelOverlap": False}},
                     "x": {"field": kpi, "type": "quantitative", "scale": {"type": "log"}, "title": kpi_title}},
    }


def _base(rows: list[dict], target_rows: list[dict], sites: list[dict], *, rail: Sequence[str], labels: Mapping[str, str],
          kpis: Sequence[Metric], league: str, model_types: list[str] | None, speed_label: str,
          overview: Mapping | str, pages: Sequence[Mapping], views: Sequence[Mapping], rerun_server: bool,
          colors: Mapping[str, str], costs: Sequence[Metric], pairs: tuple[dict, list[dict]] | None) -> dict:
    has = lambda column: any(row.get(column) is not None for row in rows)  # noqa: E731
    kpi_of = {_kpi_id(m.tag): m for m in kpis}
    league_label = kpi_of[league].label if league in kpi_of else labels.get(league, league)
    league_unit = kpi_of[league].unit if league in kpi_of else UNITS.get(league, "")
    speeds = sorted({row["speed"] for row in rows if row.get("speed") is not None})
    fastest = speeds[-1] if speeds else None

    facets = []
    for name in rail:
        if not has(name):
            continue
        facet: dict[str, Any] = {"property": name, "label": labels.get(name, name)}
        if name == "deployment":
            facet["order"] = [site["title"] for site in sites]
        elif name == "model_type" and model_types:
            facet["order"] = model_types
        elif name == "speed":
            facet.update(**{"as": "values", "order": speeds})
        facets.append(facet)
    # WHY only columns no other facet has (the target's slug, the run's folder, which holds its config): in data-ui a
    # search facet owns every property it searches, so a Config or Target tick also showed as a Name search pill, whose
    # ✕ dropped it (measured on the bench, 2026-11-24; v2/NOTES.md gap 8 had it as shared typed text)
    facets.append({"property": "target_slug", "as": "search", "properties": ["target_slug", "run"],
                   "label": "Name search", "placeholder": "part of a target's or a run folder's name"})

    properties: dict[str, Any] = {name: {"displayName": labels.get(name, name)} for name in
                                  ("deployment", "config", "sim_real", "target", "run_report")}
    properties["dataset"] = {"displayName": labels.get("dataset", "Dataset"), "colors": dict(colors)}
    if model_types:
        properties["model_type"] = {"displayName": labels.get("model_type", "Model type")}
    at = f" at {fastest:g} ×" if fastest is not None else ""
    title = f"{league_label}{at}, {league_unit} ({AGG}); n = targets" if league_unit else f"{league_label}{at} ({AGG})"
    base_views: list[dict[str, Any]] = [{
        "type": "chart", "name": "League", "chart": _league_chart("config", league, title),
        # WHY target_key in hover: data-ui hands Vega only the columns a channel or the hover names (gap 8)
        "hover": {"title": "config", "fields": [league, "target_key"]},
        **({"filters": f"speed == {fastest:g}"} if fastest is not None else {}),
    }]
    if model_types:
        base_views.append({"type": "chart", "name": "League by model type", "chart": _league_chart("model_type", league, title),
                           "hover": {"title": "model_type", "fields": [league, "target_key"]},
                           **({"filters": f"speed == {fastest:g}"} if fastest is not None else {})})
    split_by = "model_type" if model_types else "deployment"
    if speeds:
        base_views.append({"type": "chart", "name": "Speed sweeps", "chart": {"transform": [
            {"filter": f"isValid(datum.{league}) && datum.{league} > 0"},
            {"aggregate": [{"op": "median", "field": league, "as": league}],
             "groupby": [split_by, "dataset", "speed", "target_key"]},
            {"aggregate": [{"op": "median", "field": league, "as": league}], "groupby": [split_by, "dataset", "speed"]}],
            "mark": {"type": "line", "point": True},
            "encoding": {"x": {"field": "speed", "type": "quantitative", "title": speed_label},
                         "y": {"field": league, "type": "quantitative", "scale": {"type": "log"},
                               "title": f"{league_label}, {league_unit}" if league_unit else league_label,
                               "axis": {"grid": False, "tickCount": 4}},
                         "color": {"field": "dataset", "type": "nominal", "title": "Dataset"},
                         "facet": {"field": split_by, "type": "nominal", "columns": 3, "title": None}}},
            "hover": {"title": "dataset", "fields": [league, "target_key", split_by]}})
    target_columns = [c for c in ("target", "deployment", "dataset", *[n for n in rail if n not in _FIXED], "speed",
                                  "runs_all", "configs_all") if any(c in row for row in target_rows)]
    target_columns = list(dict.fromkeys(target_columns))
    kpi_columns = [_kpi_id(m.tag) for m in kpis if has(_kpi_id(m.tag))]
    run_columns = [c for c in ("target", "config", "series", "repeat", "deployment", "dataset",
                               *[n for n in rail if n not in _FIXED], "speed", "model_type", *kpi_columns, "worst",
                               "worst_joint", "tool_rms", "fb", "run_report") if has(c)]
    run_columns = list(dict.fromkeys(run_columns))
    table_views = [
        {"type": "table", "name": "Targets", "from": "targets", "order": target_columns,
         "sort": [{"property": "deployment", "direction": "ASC"}, {"property": "target", "direction": "ASC"}],
         "display": {"dataset": "badge"}},
        {"type": "table", "name": "Runs", "order": run_columns,
         "sort": [{"property": league if has(league) else "worst", "direction": "DESC"}],
         "display": {"dataset": "badge", **({league: "bar"} if has(league) else {}), "run_report": "link"}},
    ]
    note = (f"**Read it.** The rail filters **runs** (one measured line each) across every deployment; every tab shows "
            f"what is left. League: each config's {league_label.lower()}{at}, {AGG}, × the best and n targets. "
            "Colour = dataset. A Targets or Runs row opens its **target view** (summary data, the rail's runs ticked); "
            "from there the ticked runs play back in traj_compare's viewer or in Rerun.")
    if model_types:
        note += " Model type is the caller's mapping of configs (unmapped: \"other\")."
    if not any(row.get("date") is not None for row in rows):
        note += " No run carries a date yet, so there is no date range."
    extra_pages: list[dict] = []
    if isinstance(overview, str) and overview != "v2":
        # the default since 2026-11-25: O3's tiles and their pages (or one of the round's other Overviews), host views
        # in place of V2's Vega League, League by model type and Speed sweeps (runs_overview.py)
        overview, extra_pages, base_views = overview_parts(
            overview, speeds=len(speeds) > 1, costs=bool(costs), typed=bool(model_types), acc_label=league_label,
            type_label=labels.get("model_type", "Model type"))
    elif isinstance(overview, str):
        overview = None  # "v2": V2's own Overview, below
    if overview is None:
        panels = [{"view": "League", "w": 7, "h": 5, "title": f"League · configs · {title}"}]
        if model_types:
            panels += [{"view": "League by model type", "w": 5, "h": 3, "title": "League by model type"},
                       {"text": note, "w": 5, "h": 2, "title": "About"}]
        else:
            panels.append({"text": note, "w": 5, "h": 5, "title": "About"})
        if speeds:
            panels.append({"view": "Speed sweeps", "w": 12, "h": 6,
                           "title": f"Speed sweeps · {league_label} vs speed per {labels.get(split_by, split_by).lower()}, "
                                    f"one line per dataset · {AGG}"})
        overview = {"name": "Overview", "layout": {"columns": 12, "rowHeight": 88, "panels": panels}}
    actions = [
        # WHY a host action on this stock button (runs_host.js): data-ui's href opens a new tab and cannot carry the
        # rail; the host opens it in this tab with keep= and back= (gap 2). Without the host it still opens (new tab).
        {"label": "Open target view", "href": "target.html?site={site}&target={target_slug}",
         "title": "The target view of {target}: its runs, the ones the rail keeps ticked"},
        {"label": "Open run report ↗", "href": "{run_report|path}", "title": "This run's report (built on first open)"},
    ]
    if rerun_server:
        # WHY the query form: data-ui's stock post: sends no body (gap 3); traj_compare.serve takes both
        actions.append({"label": "Open in Rerun", "post": "__rerun/selection?runs={rerun_runs}",
                        "title": "This run and its target in Rerun (traj_compare.serve)"})
    datasets = {"runs": {"data": "runs.json", "label": "Runs"}, "targets": {"data": "targets.json", "label": "Targets"}}
    links = [{"from": "runs.target_key", "to": "targets.target_key", "direction": "one-way"}]
    pairs_page, pairs_views = pairs if pairs else (None, [])
    if pairs_page:
        # WHY linked by the run folder: a pair is two lines of one folder, so it stays while either passes the rail
        # (the Sim / real facet alone would otherwise empty the tab)
        datasets["pairs"] = {"data": "pairs.json", "label": "Sim ↔ real pairs"}
        links.append({"from": "runs.run_report", "to": "pairs.run_report", "direction": "one-way"})
        properties["against"] = {"displayName": "Real against"}
    return {
        "data": "runs.json",
        "noun": ["run", "runs"],
        "facets": facets,
        "properties": properties,
        "style": {"numbers": {"digits": 3}},
        "drill": {"actions": actions},
        "datasets": datasets,
        "links": links,
        "pages": [
            dict(overview),
            *extra_pages,
            {"name": "Targets", "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "Targets", "w": 12, "h": 7,
                 "title": "Targets with at least one run left · click one, then Open target view"}]}},
            {"name": "Runs", "layout": {"columns": 12, "rowHeight": 88, "panels": [
                {"view": "Runs", "w": 12, "h": 7,
                 "title": "Every run the rail keeps · click one: target view, run report, Rerun"}]}},
            *([pairs_page] if pairs_page else []),
            *[dict(page) for page in pages],
        ],
        "views": [*base_views, *table_views, *pairs_views, *[dict(view) for view in views]],
    }


# ── the pages ───────────────────────────────────────────────────────────────────────────────────────────────────────


def _asset(name: str) -> str:
    return importlib.resources.files("traj_compare").joinpath("assets", name).read_text("utf-8")


def _script_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def write_runs_workbench(
    sites: Mapping[str, Path | str] | Sequence[Path | str],
    out_dir: Path | str,
    *,
    title: str = "Every run",
    model_type: Mapping[str, str] | Callable[[str], str | None] | None = None,
    dataset: str = "dataset",
    dataset_titles: Mapping[str, str] | Callable[[str], str | None] | None = None,
    rail: Sequence[str] = RAIL,
    columns: Sequence[str] = ("repeat",),
    labels: Mapping[str, str] | None = None,
    kpis: Sequence[Metric] | None = None,
    league: str | None = None,
    speed: str | None = None,
    overview: Mapping[str, Any] | str | None = None,
    pages: Sequence[Mapping[str, Any]] = (),
    views: Sequence[Mapping[str, Any]] = (),
    sim_vs_real: bool = True,
    accuracy_fallback: bool = True,
    kit: str | None = None,
    vendor: str = "main",
    data_ui: Path | str = DATA_UI,
    rerun_server: bool = True,
    serve_root: Path | str | None = None,
) -> Path:
    """Write the runs workbench into ``out_dir`` (see the module docstring) and return its ``index.html``.

    - ``sites``: ``{deployment title: site dir}`` (sites ``write_dataset_report`` wrote), or a list of site dirs titled
      by their pages. Their order is the Deployment facet's.
    - ``model_type``: config -> model type (a Mapping or a function; an unmapped config is ``"other"``). ``None``: no
      model type column or facet. WHY the caller's: nothing traj_compare reads records one.
    - ``dataset``: the run tag naming a run's dataset; ``dataset_titles`` renames its values. A dataset value always
      carries its deployment (``"<dataset> · <deployment>"``).
    - ``rail``: the facets, in order: ``deployment``, ``dataset``, ``model_type``, ``config``, ``sim_real`` (the line's
      kind, real when its series name starts with "real"), ``series``, ``speed``, ``target``, or any run tag; one no row
      has is left out. A Name search over the target's slug and the run's folder always ends it. ``columns``: more run tags in the rows and
      the Runs table. ``labels``: a name's rail and column label.
    - ``kpis``: ``Metric``s read from run tags (``{series}`` = the line's series); default every site's ``Sweep`` y and
      metrics. Each is a column named by its tag without ``{series}_``. ``league``: the column the League ranks by
      (default the first KPI, else traj_compare's tool RMS, else the worst-joint RMS). ``speed``: the run tag of the
      speed (default the sites' sweep x); the League is taken at its fastest value.
    - ``overview``: the Overview. Default (``None`` or ``"tiles"``): O3 "Headline tiles → drill" (runs_overview.py), six
      tiles each opening its page (League, Model × dataset, Speed, Trade-off, Worst targets), the tiles and pages whose
      data is absent left out. ``"league"``, ``"matrix"``, ``"speed"``, ``"tradeoff"``: that round's other Overviews (one
      host view, full width, no extra pages); ``"v2"``: V2's own (Vega League, League by model type, Speed sweeps); a
      ``.base`` page (``{"name", "layout"}``) replaces it, V2's views beside it. ``pages`` are more tabs at the end;
      ``views`` the views they name.
    - ``sim_vs_real``: the "Does sim match real?" tab after Runs (``pairs.json``: each real line against each prediction
      in its run folder), when the runs hold any such pair. ``accuracy_fallback``: where a run carries no League KPI
      value, traj_compare's own tool RMS stands in for the Overview and the pairs (when the League KPI is in mm), flagged
      ``accuracy_from`` on the row; ``False``: the League KPI only.
    - ``kit``: the href (relative to ``out_dir``) of a data-ui kit already vendored, else ``vendor`` (a data-ui ref) is
      vendored into ``out_dir/vendor/data-ui`` from the ``data_ui`` checkout.
    - ``rerun_server``: ``False`` for a static host: no per-run Open in Rerun, and the target view's playback buttons say
      what they need instead of trying. ``serve_root``: the folder the server command names (default the deepest folder
      holding ``out_dir`` and every site).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolved = _sites(sites)
    names = {**LABELS, **(labels or {})}
    kpis = list(_default_kpis(resolved) if kpis is None else kpis)
    speed_tag, speed_label = _speed(resolved, speed)
    names.setdefault("speed", speed_label or "Speed")
    if speed_label and (labels or {}).get("speed") is None:
        names["speed"] = speed_label
    tags = [name for name in (*rail, *columns) if name not in _FIXED and name != dataset]
    lookup = _lookup(model_type)
    rows, target_rows, models = [], [], []
    for site in resolved:
        site_rows, site_targets, model = _site_rows(site, out, dataset=dataset, dataset_title=_lookup(dataset_titles),
                                                    model_type=lookup, tags=tags,
                                                    target_tags=[name for name in rail if name in tags], kpis=kpis,
                                                    speed=speed_tag)
        rows += site_rows
        target_rows += site_targets
        models.append(model)
    if not rows:
        raise ValueError("the sites hold no runs")
    kpi_ids = [_kpi_id(m.tag) for m in kpis]
    has = lambda column: any(row.get(column) is not None for row in rows)  # noqa: E731
    league = league or next((k for k in kpi_ids if has(k)), None) or ("tool_rms" if has("tool_rms") else "worst")
    if overview is None:
        overview = "tiles"
    if isinstance(overview, str) and overview not in OVERVIEWS:
        raise ValueError(f"overview={overview!r}: one of {', '.join(map(repr, OVERVIEWS))}, a .base page, or None")
    model_types = None
    if lookup is not None:
        values = list(model_type.values()) if isinstance(model_type, Mapping) else sorted({r["model_type"] for r in rows})
        model_types = [v for v in dict.fromkeys(values) if v != OTHER] + [OTHER]
    kpi_of = {_kpi_id(m.tag): m for m in kpis}
    league_label = kpi_of[league].label if league in kpi_of else names.get(league, league)
    league_unit = kpi_of[league].unit if league in kpi_of else UNITS.get(league, "")
    # WHY only into a League KPI in mm: traj_compare's tool RMS is in mm, and a stand-in must measure the same thing
    fallback = "tool_rms" if accuracy_fallback and league not in ("tool_rms", "worst") and league_unit == "mm" else None
    fill_accuracy(rows, league, fallback=fallback)
    costs = [m for m in kpis if _kpi_id(m.tag) != league and m.better == "lower" and has(_kpi_id(m.tag))]
    carry = [n for n in (*rail, *columns) if n not in ("deployment", "dataset", "target", "sim_real")]
    pairs = build_pairs(rows, carry=carry) if sim_vs_real else []
    pairs_page = pairs_parts(pairs, acc_label=league_label, unit=league_unit, speed_label=names["speed"]) if pairs else None
    colors = dataset_colors(sorted({row["dataset"] for row in rows}))
    run_columns = list(dict.fromkeys(k for row in rows for k in row))
    numeric = {column for column in run_columns if all(_number(row.get(column)) is not None or row.get(column) is None
                                                      for row in rows)}
    target_columns = list(dict.fromkeys(k for row in target_rows for k in row))
    base = _base(rows, target_rows, resolved, rail=rail, labels=names, kpis=kpis, league=league, model_types=model_types,
                 speed_label=names["speed"], overview=overview, pages=pages, views=views, rerun_server=rerun_server,
                 colors=colors, costs=costs, pairs=pairs_page)

    run_schema = _schema(run_columns, names, kpis, numeric)
    run_schema["accuracy"] = {"type": "number", "label": f"{league_label} (Overview: the tag, else traj_compare's)",
                              "unitText": league_unit, "digits": 3}
    _files.write_text(out / "runs.json", json.dumps(
        {"id": "tc-runs", "title": f"{title}: every run", "titleProperty": "target",
         "properties": run_schema, "rows": rows},
        ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    if pairs:
        pair_columns = list(dict.fromkeys(k for pair in pairs for k in pair))
        _files.write_text(out / "pairs.json", json.dumps(
            {"id": "tc-pairs", "title": f"{title}: real against its prediction, per run folder", "titleProperty": "target",
             "properties": pairs_schema(pair_columns, acc_label=league_label, unit=league_unit, labels=names),
             "rows": pairs}, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    elif (out / "pairs.json").exists():
        (out / "pairs.json").unlink()  # a rebuild without pairs: no stale tab data beside the .base
    _files.write_text(out / "targets.json", json.dumps(
        {"id": "tc-targets", "title": f"{title}: every target", "titleProperty": "target",
         "properties": _schema(target_columns, names, kpis, numeric | {"runs_all", "configs_all"}), "rows": target_rows},
        ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    _files.write_text(out / "runs.base", "# The runs workbench's .base, GENERATED by traj_compare.runs_workbench "
                                         "(write_runs_workbench). JSON is YAML.\n"
                      + json.dumps(base, indent=1, ensure_ascii=False) + "\n")
    (out / "sites").mkdir(exist_ok=True)
    for model in models:
        _files.write_text(out / "sites" / f"{model['key']}.js",
                          f"// traj_compare runs workbench: {model['deployment']}'s lines for the target view\n"
                          f"window.TC_SITE({json.dumps(model['key'])}, {_script_json(model)});\n")
    root = Path(serve_root) if serve_root is not None else Path(os.path.commonpath(
        [str(out.resolve()), *[str(site["path"].resolve()) for site in resolved]]))
    relative = Path(os.path.relpath(out.resolve(), root.resolve())).as_posix()
    page_path = "/" if relative == "." else f"/{relative}/"
    serve = f"python -m traj_compare.serve {root}"
    config = {"title": title, "rerunServer": bool(rerun_server), "serve": serve, "page": page_path,
              "deployments": {model["key"]: model["deployment"] for model in models},
              "league": {"id": league, "label": names.get(league) if league not in kpi_ids else
                         next(m.label for m in kpis if _kpi_id(m.tag) == league),
                         "unit": UNITS.get(league, "") if league not in kpi_ids else
                         next(m.unit for m in kpis if _kpi_id(m.tag) == league)}}
    _files.write_text(out / "target.html", _TARGET.format(
        title=html.escape(title), config=_script_json(config), serve=html.escape(serve),
        uplot_css=_asset("uplot.min.css"), css=_asset("runs_target.css"), uplot=_asset("uplot.iife.min.js"),
        js=_asset("runs_target.js")))
    if kit is None:
        from .coverage.workbench import _vendor

        kit = _vendor(out, vendor, Path(data_ui))
    subtitle = f"{len(rows):,} runs · {len(target_rows):,} targets · {len(resolved)} deployments"
    # the host views' config: every name they show is the caller's (assets/runs_views.js reads nothing else)
    deployments = [site["title"] for site in resolved]
    speed_text = names["speed"]
    views_config = {
        "acc": {"id": "accuracy", "kpi": league, "label": league_label, "short": league_label, "unit": league_unit,
                "log": True, "fill": FILL},
        "costs": [{"id": _kpi_id(m.tag), "label": m.label, "short": m.label, "unit": m.unit, "log": bool(m.log)}
                  for m in costs],
        "deployments": deployments, "modelTypes": model_types, "modelTypeLabel": names.get("model_type", "Model type"),
        "configOrder": config_order(rows, deployments), "palette": list(SITUATION_PALETTE),
        "speed": ({"label": speed_text, "times": "×" in speed_text, "word": "speed"}
                  if any(row.get("speed") is not None for row in rows) else None),
        "rule": RULE,
        "pairs": ({"label": league_label, "against": against_order(pairs),
                   "deployments": [d for d in deployments if any(p["deployment"] == d for p in pairs)]} if pairs else None),
    }
    _files.write_text(out / "runs_views.js", f"const CSS = {json.dumps(_asset('runs_views.css'))};\n"
                      + _asset("runs_views.js"))
    kit = kit.rstrip("/")
    # WHY "./" in front: an ES module import of "vendor/…" is a bare specifier, which the browser refuses
    kit_import = kit if kit.startswith(("/", "./", "../", "http:", "https:")) else f"./{kit}"
    _files.write_text(out / "index.html", _INDEX.format(
        title=html.escape(title), subtitle=html.escape(subtitle), kit=html.escape(kit), kit_import=html.escape(kit_import),
        host=_asset("runs_host.js"), serve=html.escape(serve), views=_script_json(views_config)))
    return out / "index.html"


# WHY every file inlined: the target view opens from file:// as well (its data are classic scripts, as the dataset view's
# targets/<slug>.js are); only the playback buttons need the server, and they say so.
_TARGET = """<!doctype html>
<!-- The target view of traj_compare's runs workbench (traj_compare.runs_workbench): one target's runs as summary data.
     ?site=<key>&target=<slug>[&keep=<line>,<line>][&back=<url>]. Its playback buttons need: {serve} -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Target view · {title}</title>
<style>{uplot_css}</style>
<style>{css}</style>
</head>
<body>
<div class="tv" id="tv">
  <nav class="tv-crumb" id="crumb"><a id="back" href="index.html">‹ All targets</a> <span aria-hidden="true">›</span> <b id="crumb-title"></b></nav>
  <div class="tv-body">
    <aside class="tv-panel" id="panel" data-tc-run-list>
      <div class="tv-panel-head"><b>Runs</b><span class="tv-mut" id="lcount"></span>
        <button class="tv-fold" id="fold" type="button" title="Fold the run list">«</button></div>
      <input type="text" id="regex" placeholder="Filter runs (regex)" aria-label="Filter runs (regex)">
      <div class="tv-chips" id="chips"></div>
      <label class="tv-group">Group by <select id="groupby" data-tc-sort><option value="config">config</option><option value="kind">sim / real</option></select></label>
      <div class="tv-lines" id="lines"></div>
      <p class="tv-note">Ticked = what every chart draws and what the playback buttons send. Runs the rail kept start
        ticked; the others are listed unticked. Colour = config. ↗ opens one run's report.</p>
      <div class="tv-resize" id="resize" title="Drag to resize"></div>
    </aside>
    <main class="tv-main">
      <div class="tv-head">
        <div><h1 id="title"></h1><p class="tv-sub" id="sub"></p></div>
        <div class="tv-play">
          <div class="tv-play-buttons">
            <button id="playback" class="tv-primary" type="button" title="traj_compare's comparison viewer: the target and every ticked run, 3D stage and question tabs">Open playback</button>
            <button id="rerun" class="tv-second" type="button" title="One Rerun recording: the target and every ticked run, one plot per joint, one line per run">Open in Rerun</button>
          </div>
          <div class="tv-status" id="status" role="status"></div>
        </div>
      </div>
      <div class="tv-card" id="verdict" data-tc-verdict></div>
      <div class="tv-bar">
        <span class="tv-k">Repeats</span>
        <span class="tv-seg" id="mode" data-tc-repeats><button type="button" data-mode="auto" class="on">Auto</button><button type="button" data-mode="lines">Lines</button><button type="button" data-mode="bands">Bands</button></span>
        <label><span class="tv-k">Lines up to N</span> <input type="range" id="linesn" min="1" max="20" value="5" data-tc-lines-n> <span id="linesnv">5</span></label>
        <label><span class="tv-k">Joint</span> <select id="joint"></select></label>
      </div>
      <div id="sections"></div>
    </main>
  </div>
</div>
<script type="application/json" id="tc-config">{config}</script>
<script>{uplot}</script>
<script>{js}</script>
</body>
</html>
"""

_INDEX = """<!doctype html>
<!-- The runs workbench of traj_compare (traj_compare.runs_workbench): one stock data-ui <data-workbench> over every run of
     every deployment (runs.base); the host script adds only what data-ui cannot (named in docs/RUNS_WORKBENCH.md).
     Serve it (module scripts and the playback buttons need http):  {serve}  -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>{title}</title>
<link rel="stylesheet" href="{kit}/data-ui.css">
<style>
  html, body {{ margin: 0; }}
  body {{ font: 14px/1.4 system-ui, sans-serif; background: #fff; color: #1f2328; overflow-x: hidden; }}
  #host {{ display: flex; align-items: center; gap: 12px; height: 40px; padding: 0 14px; box-sizing: border-box; min-width: 0; }}
  #host h1 {{ font-size: 14.5px; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; flex: 0 1 auto; }}
  #host .sub {{ color: #57606a; font-size: 12.5px; white-space: nowrap; }}
  #host button {{ font: inherit; font-size: 12.5px; padding: 3px 8px; border: 1px solid #d0d7de; border-radius: 6px; background: #fff; color: inherit; cursor: pointer; white-space: nowrap; }}
  #warn {{ font-size: 12.5px; color: #7d4e00; background: #fff8c5; border: 1px solid #eac54f; border-radius: 6px; padding: 2px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; flex: 1 1 auto; }}
  #host .sp {{ flex: 1; }}
  #tc .dw-frame > data-fold[fold="always"] {{ width: auto; padding: 8px 6px 0 8px; border-right: 0; }}
  #tc .dw-frame > data-fold[fold="always"] + .dw-rail-handle {{ display: none !important; }}
  data-workbench {{ display: block; --data-height: calc(100vh - 40px); }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #111113; color: #e6edf3; }}
    #host .sub {{ color: #9198a1; }}
    #host button {{ background: #161b22; border-color: #30363d; }}
    #warn {{ color: #e3b341; background: #272115; border-color: #6c5418; }}
  }}
</style>
</head>
<body>
<header id="host">
  <button type="button" id="fold" aria-pressed="false" title="Fold the filter rail to a chip">⟨ Fold filters</button>
  <h1>{title}</h1><span class="sub">{subtitle}</span>
  <span id="warn" role="status" hidden></span>
  <span class="sp"></span>
</header>
<data-workbench id="tc" src="runs.base" aria-label="{title}"></data-workbench>
<script type="application/json" id="tc-views">{views}</script>
<script type="module" src="{kit}/data-ui.js"></script>
<script type="module">
// the host views (the Overview's tiles and pages, the sim-vs-real answer), registered through data-ui's own
// registerView before the workbench draws a panel of runs.base (traj_compare.runs_overview, assets/runs_views.js)
import {{ registerView }} from '{kit_import}/data-ui.js';
import {{ registerRunsViews }} from './runs_views.js';
registerRunsViews(registerView, JSON.parse(document.getElementById('tc-views').textContent));
{host}
</script>
</body>
</html>
"""
