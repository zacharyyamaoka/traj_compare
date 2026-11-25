"""The runs workbench's two AI picks as its defaults (written before the code, 2026-11-25):

- the Overview = O3 "Headline tiles → drill" of docs/proposals/v2-overview-2026-11-24/ (o3/NOTES.md): six calm tiles
  (best config + top 5, speed growth, the trade-off frontier, model × dataset coverage, worst target, runs left), each
  opening its own full page (League, Model × dataset, Speed, Trade-off, Worst targets; Runs left opens Targets);
- a fourth tab, T1 "Does sim match real?" of docs/proposals/v2-tabs-2026-11-24/ (t1/NOTES.md): each real run paired with
  the prediction from the same run folder, built in Python from the runs (never the round's scraping).

Every caller gets them; ``overview=`` and ``pages=`` still override. A tile whose data is absent is absent (no cost KPI
→ no trade-off tile or page; one speed → no speed tile or page); with no pair in the data there is no T1 tab.
tests/test_runs_workbench_picks_browser.py checks the drawn numbers against runs_picks_oracle in headless Chrome.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
from pathlib import Path

import pytest

from runs_picks_fixture import RIG, REAL_ONLY, UNTAGGED, write_three_sites
from runs_picks_oracle import accuracy, pairs, pairs_answer
from runs_workbench_fixture import ARM, PENDULUM
from traj_compare import Metric
from traj_compare.runs_workbench import write_runs_workbench

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
needs_data_ui = pytest.mark.skipif(not ((DATA_UI / "bin" / "data-ui.mjs").is_file() and shutil.which("node")),
                                   reason="needs the data-ui checkout and node (vendoring)")
T1 = "Does sim match real?"
O3_PAGES = ["Overview", "League", "Config × dataset", "Speed", "Trade-off", "Worst targets", "Targets", "Runs", T1]
PACKAGE = Path(__file__).resolve().parents[1] / "src" / "traj_compare"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("picks")
    sites = write_three_sites(root)
    index = write_runs_workbench(sites, root / "all", title="Every run")
    return root, sites, index


def read_json(path: Path):
    return json.loads(path.read_text("utf-8"))


def read_base(out: Path) -> dict:
    text = (out / "runs.base").read_text("utf-8")
    return json.loads("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def views_of(base: dict) -> dict:
    return {view["name"]: view for view in base["views"]}


def tiles_of(base: dict) -> list[str]:
    overview = base["pages"][0]
    views = views_of(base)
    return [views[panel["view"]]["tc"]["tile"] for panel in overview["layout"]["panels"]]


# ── the Overview: O3's tiles, each opening its page ─────────────────────────────────────────────────────────────────


@needs_data_ui
def test_the_default_overview_is_six_tiles_each_opening_its_own_page(built):
    root, sites, index = built
    base = read_base(index.parent)
    assert [page["name"] for page in base["pages"]] == O3_PAGES
    overview = base["pages"][0]
    assert overview["name"] == "Overview"
    assert tiles_of(base) == ["best", "speed", "cost", "coverage", "worst", "left"]
    opens = [panel["open"] for panel in overview["layout"]["panels"]]
    assert opens == ["League", "Speed", "Trade-off", "Config × dataset", "Worst targets", "Targets"]
    names = {page["name"] for page in base["pages"]}
    assert set(opens) <= names
    views = views_of(base)
    # each detail page is one full-width host view (the round's), every tile a tc-tile
    for page, kind in (("League", "tc-league"), ("Config × dataset", "tc-matrix"), ("Speed", "tc-sweep"),
                       ("Trade-off", "tc-tradeoff"), ("Worst targets", "tc-worst")):
        panels = next(p for p in base["pages"] if p["name"] == page)["layout"]["panels"]
        assert [views[p["view"]]["type"] for p in panels] == [kind], page
    assert {views[p["view"]]["type"] for p in overview["layout"]["panels"]} == {"tc-tile"}


@needs_data_ui
def test_the_page_carries_its_views_config_and_ships_the_promoted_kit(built):
    root, sites, index = built
    out = index.parent
    page = index.read_text("utf-8")
    assert 'id="tc-views"' in page and "runs_views.js" in page
    assert (out / "runs_views.js").is_file()
    config = json.loads(page.split('id="tc-views">', 1)[1].split("</script>", 1)[0])
    assert config["acc"]["id"] == "accuracy" and config["acc"]["unit"] == "mm"
    assert config["acc"]["kpi"] == "tcp_rms_mm" and config["acc"]["label"] == "tool RMS"
    assert [cost["id"] for cost in config["costs"]] == ["energy_j"]
    assert config["deployments"] == [ARM, PENDULUM, RIG]
    rows = read_json(out / "runs.json")["rows"]
    assert sorted(config["configOrder"]) == sorted({row["config"] for row in rows})
    assert config["modelTypes"] is None  # no mapping given: configs stand in for model types


@needs_data_ui
def test_the_overview_value_is_the_runs_tag_else_traj_compares_tool_rms_and_says_which(built):
    # WHY (the V2 rounds' extract.py: "tcp falls back to rows[].tcp"): BAM FB's real runs carry no tool RMS tag, so
    # without it the real arm had no pair and no place in the League; the substitution is flagged, never silent
    root, sites, index = built
    rows = read_json(index.parent / "runs.json")["rows"]
    filled = [row for row in rows if row.get("accuracy_from")]
    assert [(row["target"], row["config"], row["repeat"], row["series"]) for row in filled] == [UNTAGGED]
    for row in rows:
        assert row["accuracy"] == accuracy(row)
        if not row.get("accuracy_from"):
            assert row["accuracy"] == row["tcp_rms_mm"]
    assert filled[0]["accuracy"] == filled[0]["tool_rms"] and filled[0]["accuracy_from"] == "traj_compare"


@needs_data_ui
def test_no_cost_kpi_means_no_trade_off_tile_and_no_trade_off_page(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench(sites, tmp_path / "no-cost", kpis=[Metric("{series}_tcp_rms_mm", "tool RMS", "mm", log=True)],
                                 kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert "cost" not in tiles_of(base)
    assert "Trade-off" not in [page["name"] for page in base["pages"]]
    assert "tc-tradeoff" not in {view["type"] for view in base["views"]}
    assert tiles_of(base) == ["best", "speed", "coverage", "worst", "left"]


@needs_data_ui
def test_one_speed_means_no_speed_tile_and_no_speed_page(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench(sites, tmp_path / "no-speed", speed="no_such_tag", kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert "speed" not in tiles_of(base)
    assert "Speed" not in [page["name"] for page in base["pages"]]


@needs_data_ui
def test_a_model_type_mapping_names_the_matrix_page_model_by_dataset(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench(sites, tmp_path / "typed", model_type={"ff": "feed-forward", "mpc": "model predictive"},
                                 kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    names = [page["name"] for page in base["pages"]]
    assert "Model × dataset" in names and "Config × dataset" not in names
    page = index.read_text("utf-8")
    config = json.loads(page.split('id="tc-views">', 1)[1].split("</script>", 1)[0])
    assert config["modelTypes"] == ["feed-forward", "model predictive", "other"]


@needs_data_ui
def test_overview_still_overrides_and_v2s_old_overview_stays_an_option(built, tmp_path):
    root, sites, _ = built
    spliced = {"name": "Overview", "layout": {"columns": 12, "panels": [{"view": "Runs", "w": 12, "h": 4}]}}
    index = write_runs_workbench(sites, tmp_path / "spliced", overview=spliced, kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert base["pages"][0] == spliced
    assert [page["name"] for page in base["pages"]] == ["Overview", "Targets", "Runs", T1]
    index = write_runs_workbench(sites, tmp_path / "v2", overview="v2", kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert [page["name"] for page in base["pages"]] == ["Overview", "Targets", "Runs", T1]
    assert "League" in views_of(base) and views_of(base)["League"]["type"] == "chart"  # V2's Vega League
    # the round's other four Overviews are one word away (each its one host view, full width)
    for name, kind in (("league", "tc-league"), ("matrix", "tc-matrix"), ("speed", "tc-sweep"),
                       ("tradeoff", "tc-tradeoff")):
        index = write_runs_workbench(sites, tmp_path / name, overview=name, kit="../all/vendor/data-ui")
        base = read_base(index.parent)
        views = views_of(base)
        assert [views[p["view"]]["type"] for p in base["pages"][0]["layout"]["panels"]] == [kind], name
    with pytest.raises(ValueError, match="overview"):
        write_runs_workbench(sites, tmp_path / "bad", overview="nope", kit="../all/vendor/data-ui")


# ── "Does sim match real?": pairs built in Python from the runs ─────────────────────────────────────────────────────


@needs_data_ui
def test_pairs_are_one_per_real_line_and_prediction_of_one_run_folder(built):
    root, sites, index = built
    out = index.parent
    rows = read_json(out / "runs.json")["rows"]
    got = read_json(out / "pairs.json")["rows"]
    want = pairs(rows)
    assert len(got) == len(want) == 4 + 7 + 4  # pendulum 4 sim; rig 7 sim (one folder is real only) + 4 rehearsal
    by = {(p["site"], tuple(sorted(int(x) for x in p["keep"].split(","))), p["against"]): p for p in got}
    for p in want:
        mine = by[(p["site"], tuple(p["lines"]), p["against"])]
        assert mine["ratio"] == p["ratio"] and mine["real_worse"] == int(p["ratio"] > 1)
        assert mine["apart"] == pytest.approx(max(p["ratio"], 1 / p["ratio"]), rel=1e-3)
        assert mine["deployment"] == p["deployment"] and mine["run_report"] == p["folder"]
    # every pendulum pair: real 3x sim, by the fixture's formula
    assert sorted(p["ratio"] for p in got if p["deployment"] == PENDULUM) == [3.0] * 4
    # the real-only folder holds no pair; the untagged real line pairs on traj_compare's tool RMS, and says so
    real_only = [r for r in rows if (r["target"], r["config"], r.get("repeat")) == REAL_ONLY]
    assert real_only and not [p for p in got if p["run_report"] == real_only[0]["run_report"]]
    untagged = [p for p in got if p.get("real_from") == "traj_compare"]
    assert len(untagged) == 1 and untagged[0]["config"] == UNTAGGED[1]
    # the stock drill opens the target view with the pair (its two lines) and Rerun with both
    for p in got:
        a, b = (int(x) for x in p["keep"].split(","))
        assert {rows_by_line(rows, p["site"], a)["run_report"], rows_by_line(rows, p["site"], b)["run_report"]} == {p["run_report"]}
        assert p["rerun_runs"].count(",") == 1 and p["site"] and p["target_slug"]


def rows_by_line(rows, site, line):
    return next(r for r in rows if r["site"] == site and r["line"] == line)


@needs_data_ui
def test_the_sim_vs_real_tab_is_a_page_over_pairs_linked_one_way_from_the_runs(built):
    root, sites, index = built
    base = read_base(index.parent)
    assert base["datasets"]["pairs"]["data"] == "pairs.json"
    assert {"from": "runs.run_report", "to": "pairs.run_report", "direction": "one-way"} in base["links"]
    page = next(p for p in base["pages"] if p["name"] == T1)
    facet = page["datasets"]["pairs"]["facets"][0]
    assert facet["property"] == "against" and facet["as"] == "select"
    # the default prediction is the one with the most pairs (sim: 11, rehearsal: 4)
    assert facet["order"][0] == "sim" and page["datasets"]["pairs"]["filters"] == 'against == "sim"'
    views = views_of(base)
    kinds = [views[p["view"]]["type"] for p in page["layout"]["panels"]]
    assert kinds[0] == "tc-pairs" and kinds[-1] == "table"
    assert all(views[p["view"]].get("from") == "pairs" for p in page["layout"]["panels"])
    rows = read_json(index.parent / "runs.json")["rows"]
    all_pairs = pairs(rows)
    answer = pairs_answer(all_pairs, rows, "sim")
    assert answer["n"] == 11
    assert answer == pairs_answer(all_pairs, rows, "sim")  # the browser test reads the page against this
    assert pairs_answer(all_pairs, [r for r in rows if r["deployment"] == PENDULUM], "sim") == \
        {"n": 4, "median": 3.0, "worse": 4}
    assert pairs_answer(all_pairs, [r for r in rows if r["deployment"] == ARM], "sim")["n"] == 0


@needs_data_ui
def test_no_real_run_means_no_sim_vs_real_tab(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench({ARM: sites[ARM]}, tmp_path / "sim-only", kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert T1 not in [page["name"] for page in base["pages"]]
    assert "pairs" not in base["datasets"] and not (index.parent / "pairs.json").exists()
    assert not [link for link in base["links"] if "pairs" in link["to"]]


@needs_data_ui
def test_the_rig_pairs_median_matches_the_formula(built):
    # an oracle that is not the oracle: the fixture's formula, by hand, for the rig's rehearsal pairs (pd only)
    root, sites, index = built
    got = [p for p in read_json(index.parent / "pairs.json")["rows"] if p["deployment"] == RIG and p["against"] == "rehearsal"]
    # pd: real gain 2.0 (r0) / 2.5 (r1) over rehearsal's 1.25: 1.6 and 2.0 on each of two targets
    assert sorted(p["ratio"] for p in got) == [1.6, 1.6, 2.0, 2.0]
    assert statistics.median(p["ratio"] for p in got) == 1.8


def test_the_new_files_name_no_bench_config_or_deployment():
    words = ("ctc_tuned", "menagerie_stock", "hold_friction", "jtc_baseline", "ff_board_i", "board_pd", "MODEL_TYPE",
             "UR5e", "BAM FB", "pendulum", "Conveyor", "sim twin")
    files = [PACKAGE / "runs_overview.py", *sorted((PACKAGE / "assets").glob("runs_*"))]
    assert (PACKAGE / "runs_overview.py").is_file() and (PACKAGE / "assets" / "runs_views.js").is_file()
    for path in files:
        text = path.read_text("utf-8")
        assert not [word for word in words if word in text], path
