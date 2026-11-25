"""Coverage, inside the runs workbench (feedback fb-5defddb0, written before the code, 2026-11-25).

Zach, Daily Note 2026-11-23 "Coverage Feedback": *"Ok I like alot of these things BUT I need to basically like integrate
this into the viewer. So we have like this traj compare viewer. BUt now we should have like trajectory Coverage Viewer
Where you can put in like datasets or single trajectories. I guess It should be almost like a page you can see standalone
or just quickly get there from the traj compare stuff..."*

The standalone page exists (``traj_compare.coverage``, docs/COVERAGE.md) and every bench site writes one
(``write_dataset_report(coverage=True)``), but the runs workbench, the traj_compare viewer since 2026-11-24
(docs/RUNS_WORKBENCH.md), had no way to it. So:

- the workbench gets a **Coverage** tab after Runs when any site has a coverage page: one entry per such deployment with
  its page (a path that resolves from the workbench), the page's own headline numbers and, per target of that site, the
  name its trajectory has on the page; the deployments without one are named, so the tab never hides them;
- the **target view** of a target whose site has a coverage page links to that page with the target's trajectory named
  (a single trajectory, highlighted among its dataset);
- no site with a coverage page: no tab, no link.

This file holds what Python can judge; tests/test_runs_workbench_coverage_browser.py drives it in headless Chrome.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from runs_workbench_fixture import ARM, PENDULUM, write_sites
from traj_compare.runs_workbench import write_runs_workbench


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The arm site writes its coverage page, the pendulum site does not."""
    root = tmp_path_factory.mktemp("coverage-tab")
    sites = write_sites(root, coverage=(ARM,))
    write_runs_workbench(sites, root / "all", title="Every run", kit="vendor/none")
    return root


def read_base(out: Path) -> dict:
    text = (out / "runs.base").read_text("utf-8")
    return json.loads("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def script_json(page: Path, script_id: str) -> dict:
    match = re.search(rf'<script type="application/json" id="{script_id}">(.*?)</script>', page.read_text("utf-8"), re.S)
    assert match, f"{page.name} has no <script id={script_id}>"
    return json.loads(match.group(1).replace("<\\/", "</"))


def runs_of(out: Path) -> list[dict]:
    return json.loads((out / "runs.json").read_text("utf-8"))["rows"]


def coverage_payload(root: Path) -> dict:
    return json.loads((root / "arm" / "coverage" / "coverage.json").read_text("utf-8"))


def test_a_coverage_tab_follows_runs_when_a_site_has_a_coverage_page(built):
    base = read_base(built / "all")
    names = [page["name"] for page in base["pages"]]
    assert "Coverage" in names, names
    assert names.index("Coverage") > names.index("Runs")
    page = base["pages"][names.index("Coverage")]
    panel_views = [panel["view"] for panel in page["layout"]["panels"] if "view" in panel]
    views = {view["name"]: view for view in base["views"]}
    assert [views[name]["type"] for name in panel_views] == ["tc-coverage"]


def test_the_tab_names_each_deployments_page_its_own_numbers_and_its_targets_names(built):
    out = built / "all"
    coverage = script_json(out / "index.html", "tc-views")["coverage"]
    assert [entry["deployment"] for entry in coverage["deployments"]] == [ARM]
    assert coverage["missing"] == [PENDULUM]
    entry = coverage["deployments"][0]
    assert entry["site"] == "arm"
    assert entry["href"] == "../arm/coverage/index.html"
    assert (out / entry["href"]).resolve().is_file()
    payload = coverage_payload(built)
    assert entry["trajectories"] == payload["source"]["trajectories"] == 3
    assert entry["numbers"] == payload["numbers"]  # the page's own headline numbers, never recomputed
    # every arm target the runs name -> the name of its trajectory on the coverage page
    slugs = {row["target_slug"] for row in runs_of(out) if row["deployment"] == ARM}
    assert set(entry["names"]) == slugs
    assert set(entry["names"].values()) == {item["name"] for item in payload["trajectories"]}


def test_the_target_view_links_its_own_trajectory_on_the_coverage_page(built):
    out = built / "all"
    config = script_json(out / "target.html", "tc-config")
    assert set(config["coverage"]) == {"arm"}  # the pendulum site has no coverage page: its target view no link
    arm = config["coverage"]["arm"]
    assert arm["href"] == "../arm/coverage/index.html"
    payload = coverage_payload(built)
    names = {item["name"] for item in payload["trajectories"]}
    slugs = {row["target_slug"] for row in runs_of(out) if row["deployment"] == ARM}
    assert set(arm["names"]) == slugs and set(arm["names"].values()) == names


def test_no_coverage_page_means_no_tab_and_no_link(tmp_path):
    sites = write_sites(tmp_path)
    write_runs_workbench(sites, tmp_path / "all", title="Every run", kit="vendor/none")
    out = tmp_path / "all"
    assert "Coverage" not in [page["name"] for page in read_base(out)["pages"]]
    assert "tc-coverage" not in {view["type"] for view in read_base(out)["views"]}
    assert script_json(out / "index.html", "tc-views")["coverage"] is None
    assert script_json(out / "target.html", "tc-config")["coverage"] == {}
