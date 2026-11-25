"""The runs workbench: V2 "Two viewers, the filter carried" made traj_compare's dataset viewer (written before the code,
2026-11-24; docs/proposals/tensorboard-2026-11-24/v2).

Zach, Daily Note 2026-11-24: "yes v2 is really great please do that one ... I really like kinda the layout structure
now"; runs are atomic, the rail filters runs across ALL deployments, deployment is a filter not a split, tabs Overview ·
Targets · Runs. Then (l.3227): "there are almost like 3 actually. We have like the dataset view, then the target view (at
this point its still just summary data though), Then we can actually open up the playback viewer. either our custom one
or the rerun one." So three levels:

1. the dataset workbench (``index.html``: stock data-ui ``<data-workbench>`` over every run of every site);
2. the target view (``target.html``: one target's runs as summary data, the rail's runs ticked through ``keep=``);
3. playback of the ticked runs: traj_compare's comparison viewer (``write_comparison_report``, called as it is) through
   ``traj_compare.serve``'s ``__playback``, or Rerun through its ``__rerun/selection`` (stock robot_msgs.viz.rerun).

This file holds what Python can judge; tests/test_runs_workbench_browser.py drives the journey in headless Chrome.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from runs_workbench_fixture import ARM, ARM_JOINTS, PENDULUM, energy_j, tcp_rms_mm, write_sites
from traj_compare.dataset import read_site_payload
from traj_compare.runs_workbench import write_runs_workbench
from traj_compare.serve import make_handler

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
needs_data_ui = pytest.mark.skipif(not ((DATA_UI / "bin" / "data-ui.mjs").is_file() and shutil.which("node")),
                                   reason="needs the data-ui checkout and node (vendoring, data-ui check)")
DEG = 180.0 / math.pi
PACKAGE = Path(__file__).resolve().parents[1] / "src" / "traj_compare"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("bench")
    sites = write_sites(root)
    index = write_runs_workbench(sites, root / "all", title="Every run")
    return root, sites, index


def read_json(path: Path):
    return json.loads(path.read_text("utf-8"))


def read_base(out: Path) -> dict:
    text = (out / "runs.base").read_text("utf-8")
    return json.loads("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def lines_of(site: Path) -> list[dict]:
    """The oracle: every line of a site, straight from its own payload, with its run's tags."""
    payload = read_site_payload(site)
    runs = {run["name"]: run for run in payload["runs"]}
    return [{**line, "tags": runs[line["run"]]["tags"]} for line in payload["levels"]["lines"]]


# ── 1. the outer view: one row per run (measured line) across every deployment ─────────────────────────────────────


@needs_data_ui
def test_one_row_per_measured_line_of_every_site(built):
    root, sites, index = built
    out = index.parent
    rows = read_json(out / "runs.json")["rows"]
    expected = sum(len(lines_of(site)) for site in sites.values())
    assert expected == 20 and len(rows) == 20
    assert len({row["id"] for row in rows}) == 20
    assert {row["deployment"] for row in rows} == {ARM, PENDULUM}
    assert sum(row["deployment"] == ARM for row in rows) == 12


@needs_data_ui
def test_each_row_holds_v2s_columns_from_the_sites_own_numbers(built):
    root, sites, index = built
    rows = read_json(index.parent / "runs.json")["rows"]
    by_site = {}
    for row in rows:
        by_site.setdefault(row["deployment"], []).append(row)
    for deployment, site in sites.items():
        oracle = lines_of(site)
        mine = sorted(by_site[deployment], key=lambda row: row["line"])
        assert [row["line"] for row in mine] == list(range(len(oracle)))
        for row, line in zip(mine, oracle, strict=True):
            tags, series = line["tags"], line["series"]
            assert row["config"] == line["config"] == tags["controller"]
            assert row["series"] == series and row["sim_real"] == line["kind"]
            assert row["split"] == tags["split"] and row["kind"] == tags["kind"] and row["repeat"] == tags["repeat"]
            assert row["speed"] == tags["speed_fraction"]
            # WHY a dataset value carries its deployment: the same dataset key on two robots is two datasets
            assert row["dataset"] == f"{tags['dataset']} · {deployment}"
            assert row["target_slug"] == line["target"]
            # the KPIs: the run tags of THIS series (a site without a sweep of its own included), and traj_compare's own
            assert row["tcp_rms_mm"] == tcp_rms_mm(tags["controller"], tags["speed_fraction"], tags["repeat"], series)
            assert row["energy_j"] == energy_j(tags["controller"], tags["speed_fraction"], tags["repeat"], series)
            assert row["worst"] == pytest.approx(line["worst_rms"] * DEG, rel=1e-3)
    arm = by_site[ARM]
    assert all(row["tool_rms"] > 0 for row in arm)  # the arm has a tool (poses), the pendulum none
    assert all(row.get("tool_rms") is None for row in by_site[PENDULUM])
    assert all(row["fb"] == pytest.approx(0.2, abs=1e-6) for row in arm)  # tau_ff 0.8 of tau_cmd 1.0


@needs_data_ui
def test_the_rail_is_v2s_order_and_has_no_model_type_without_a_mapping(built):
    root, sites, index = built
    base = read_base(index.parent)
    rail = [facet["property"] for facet in base["facets"]]
    assert rail[:-1] == ["deployment", "dataset", "split", "config", "sim_real", "speed", "kind", "target"]
    assert base["facets"][-1]["as"] == "search"
    rows = read_json(index.parent / "runs.json")
    assert "model_type" not in rows["properties"] and all("model_type" not in row for row in rows["rows"])
    assert "model_type" not in json.dumps(base)
    # the defaults since 2026-11-25 (tests/test_runs_workbench_picks.py): O3's tiles and their pages, then T1
    assert [page["name"] for page in base["pages"]] == ["Overview", "League", "Config × dataset", "Speed", "Trade-off",
                                                        "Worst targets", "Targets", "Runs", "Does sim match real?"]
    assert base["noun"] == ["run", "runs"]


@needs_data_ui
def test_a_model_type_mapping_adds_the_facet_and_unmapped_configs_say_other(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench(sites, tmp_path / "typed", title="Typed", model_type={"ff": "feed-forward"},
                                 kit="../all/vendor/data-ui")
    rows = read_json(index.parent / "runs.json")["rows"]
    assert {row["model_type"] for row in rows if row["config"] == "ff"} == {"feed-forward"}
    assert {row["model_type"] for row in rows if row["config"] == "pd"} == {"other"}
    rail = [facet["property"] for facet in read_base(index.parent)["facets"]]
    assert rail.index("model_type") == rail.index("split") + 1  # V2: Split, then Model type, then Config


def test_the_package_names_no_bench_config():
    # WHY: the model types and the config names are the caller's (Zach's bench), never hard-coded in traj_compare
    words = ("ctc_tuned", "menagerie_stock", "hold_friction", "jtc_baseline", "ff_board_i", "board_pd", "MODEL_TYPE")
    files = [PACKAGE / "runs_workbench.py", PACKAGE / "selection.py", *sorted((PACKAGE / "assets").glob("runs_*"))]
    assert files and all(path.is_file() for path in files)
    for path in files:
        text = path.read_text("utf-8")
        assert not [word for word in words if word in text], path


@needs_data_ui
def test_the_targets_tab_lists_one_row_per_target_linked_from_the_runs(built):
    root, sites, index = built
    out = index.parent
    targets = read_json(out / "targets.json")["rows"]
    assert len(targets) == 3 + 2
    base = read_base(out)
    assert base["links"][0] == {"from": "runs.target_key", "to": "targets.target_key", "direction": "one-way"}
    assert base["links"][1:] == [{"from": "runs.run_report", "to": "pairs.run_report", "direction": "one-way"}]  # T1
    runs = read_json(out / "runs.json")["rows"]
    for target in targets:
        mine = [row for row in runs if row["target_key"] == target["target_key"]]
        assert target["runs_all"] == len(mine) and target["configs_all"] == len({row["config"] for row in mine})


@needs_data_ui
def test_the_drill_opens_the_target_view_the_run_report_and_rerun(built):
    root, sites, index = built
    out = index.parent
    actions = {action["label"]: action for action in read_base(out)["drill"]["actions"]}
    assert set(actions) == {"Open target view", "Open run report ↗", "Open in Rerun"}
    assert actions["Open target view"]["href"].startswith("target.html?site={site}&target={target_slug}")
    row = read_json(out / "runs.json")["rows"][0]
    report = (out / row["run_report"]).resolve()
    assert report.parent.parent.parent.resolve() in {site.resolve() for site in sites.values()}
    assert (report.parent / "manifest.json").is_file()  # built lazily by traj_compare.serve, from this folder
    assert actions["Open in Rerun"]["post"].startswith("__rerun/selection?runs=")


@needs_data_ui
def test_the_overview_and_more_tabs_splice_in_as_base_blocks(built, tmp_path):
    root, sites, _ = built
    overview = {"name": "Overview", "layout": {"columns": 12, "panels": [{"view": "Picked", "w": 12, "h": 4}]}}
    picked = {"type": "table", "name": "Picked", "order": ["config", "tcp_rms_mm"]}
    sweeps = {"name": "Sweeps", "layout": {"columns": 12, "panels": [{"view": "Picked", "w": 12, "h": 4}]}}
    index = write_runs_workbench(sites, tmp_path / "spliced", overview=overview, pages=[sweeps], views=[picked],
                                 kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert [page["name"] for page in base["pages"]] == ["Overview", "Targets", "Runs", "Does sim match real?", "Sweeps"]
    assert base["pages"][0] == overview
    assert "Picked" in {view["name"] for view in base["views"]}


@needs_data_ui
def test_the_base_passes_data_uis_own_checker(built):
    root, sites, index = built
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(index.parent / "runs.base"),
                             "--json"], capture_output=True, text=True, timeout=120)
    report = json.loads(result.stdout)
    assert result.returncode == 0, report
    assert not [problem for problem in report.get("problems", []) if problem.get("level", "error") == "error"], report


@needs_data_ui
def test_index_is_one_workbench_over_the_vendored_kit_and_the_target_view_ships_beside_it(built):
    root, sites, index = built
    out = index.parent
    page = index.read_text("utf-8")
    assert '<data-workbench' in page and 'src="runs.base"' in page and 'src="vendor/data-ui/data-ui.js"' in page
    assert (out / "vendor" / "data-ui" / "data-ui.js").is_file()
    assert (out / "target.html").is_file()
    for key in ("arm", "pendulum"):
        assert (out / "sites" / f"{key}.js").is_file()


# ── 2 + 3. the server: playback (traj_compare's comparison viewer) and Rerun for a selection ────────────────────────


@pytest.fixture
def server(built):
    root, sites, index = built
    spawned = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, spawn=spawned.append))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", spawned
    finally:
        httpd.shutdown()
        httpd.server_close()


def post(url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def three_arm_lines(index: Path) -> list[dict]:
    rows = read_json(index.parent / "runs.json")["rows"]
    target = next(row["target_key"] for row in rows if row["deployment"] == ARM)
    mine = [row for row in rows if row["target_key"] == target][:3]
    assert len(mine) == 3
    return [{"folder": row["rerun_runs"].rpartition(":")[0], "series": row["series"],
             "label": f"{row['config']} · r{row['repeat']} · {row['series']}", "color": "#7c5cc4"} for row in mine]


@needs_data_ui
def test_rerun_for_a_selection_holds_n_lines_per_joint_read_back(built, server):
    pytest.importorskip("rerun")
    root, sites, index = built
    base, spawned = server
    picked = three_arm_lines(index)
    status, answer = post(f"{base}/all/__rerun/selection?dry=1", {"runs": picked})
    assert status == 200 and answer["ok"], answer
    assert answer["n"] == 3 and not spawned  # dry: built, never launched
    rrd = Path(answer["rrd"])
    assert rrd.is_file() and rrd.resolve().is_relative_to(index.parent.resolve())
    from rerun.chunk import RrdReader  # read back with Rerun's own reader, never our writer

    entities = {str(chunk.entity_path) for chunk in RrdReader(rrd).stream()}
    for joint in ARM_JOINTS:
        # robot_msgs.viz.rerun's stock layout: /<field>/<joint>/<name>, one plot per joint, one line per name
        names = {path.split("/")[-1] for path in entities if re.match(rf"^/?positions/{joint}/[^/]+$", path)}
        assert len(names) == 3 + 1, (joint, sorted(names))  # the three selected runs + the target
    status, answer = post(f"{base}/all/__rerun/selection", {"runs": picked})
    assert status == 200 and answer["ok"] and len(spawned) == 1  # not dry: the pinned viewer is started once


@needs_data_ui
def test_rerun_selection_takes_the_bodyless_query_form_and_refuses_outside_the_root(built, server):
    pytest.importorskip("rerun")
    root, sites, index = built
    base, _ = server
    row = read_json(index.parent / "runs.json")["rows"][0]
    status, answer = post(f"{base}/all/__rerun/selection?dry=1&runs={urllib.request.quote(row['rerun_runs'])}")
    assert status == 200 and answer["ok"] and answer["n"] == 1, answer
    status, answer = post(f"{base}/all/__rerun/selection?dry=1", {"runs": [{"folder": "../../../etc", "series": "sim"}]})
    assert status in (400, 403) and not answer["ok"]
    status, answer = post(f"{base}/all/__rerun/selection?dry=1", {"runs": []})
    assert status == 400 and not answer["ok"]


@needs_data_ui
def test_playback_is_the_comparison_viewer_over_exactly_the_ticked_runs_and_the_target(built, server):
    root, sites, index = built
    base, _ = server
    picked = three_arm_lines(index)
    back = "/all/target.html?site=arm&target=x&keep=0,1,2&back=%2Fall%2Findex.html%3Fdeployment%3DArm%2Bcell%23tab%3Dtargets"
    crumbs = [["‹ All targets", "/all/index.html?deployment=Arm+cell#tab=targets"], ["reach-01 · 0.5x", back]]
    status, answer = post(f"{base}/all/__playback", {"runs": picked, "crumbs": crumbs, "title": "reach-01 · 0.5x"})
    assert status == 200 and answer["ok"], answer
    with urllib.request.urlopen(base + answer["href"], timeout=120) as response:
        page = response.read().decode("utf-8")
    payload = json.loads(re.search(r'id="traj-compare-data">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    situations = payload["comparisons"][0]["situations"]
    assert [s["role"] for s in situations].count("target") == 1
    measured = [s["title"] for s in situations if s["role"] != "target"]
    assert measured == [run["label"] for run in picked]
    assert payload["comparisons"][0]["joint_names"] == list(ARM_JOINTS)
    nav = re.search(r"<nav class='tc-breadcrumb'.*?</nav>", page, re.S).group(0)
    assert "href='/all/index.html?deployment=Arm+cell#tab=targets'" in nav.replace("&amp;", "&")
    assert f"href='{back}'" in nav.replace("&amp;", "&")
    # the same selection again is the same page (a cache, not a rebuild)
    status, again = post(f"{base}/all/__playback", {"runs": picked, "crumbs": crumbs, "title": "reach-01 · 0.5x"})
    assert again["href"] == answer["href"]
    # a crumb that is not a same-origin path is refused (no javascript: links into the page)
    status, refused = post(f"{base}/all/__playback", {"runs": picked, "crumbs": [["x", "javascript:alert(1)"]]})
    assert status == 400 and not refused["ok"]


@needs_data_ui
def test_without_a_server_the_page_says_what_it_needs(built, tmp_path):
    root, sites, _ = built
    index = write_runs_workbench(sites, tmp_path / "static", rerun_server=False, kit="../all/vendor/data-ui")
    base = read_base(index.parent)
    assert "Open in Rerun" not in {action["label"] for action in base["drill"]["actions"]}
    target = (index.parent / "target.html").read_text("utf-8")
    assert "python -m traj_compare.serve" in target
