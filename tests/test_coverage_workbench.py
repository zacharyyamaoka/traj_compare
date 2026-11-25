"""The coverage workbench: one data-ui <data-workbench> page over a set of trajectories (acceptance, written before the
code, 2026-11-24). Contract: docs/COVERAGE.md, "The workbench"; data-ui docs/CONTRACT.md §52 and §53.

Zach, 2026-11-24: "concretely I want to be able to analyze the UR trajectories I am making right now in our own custom
viewer"; "the atomic unit here is trajectories"; a Dataset filter first, dev/holdout across every dataset ticked; tabs
that feel like switching dashboards; compact enough to drop into any app.

The oracle is analyze() itself: every trajectory's part rows, added up per grid, must give back the payload's own counts
exactly (planes, histograms, projections, the direction sphere and grids), because the page re-sums those parts over
whatever the rail keeps. Then data-ui's own checker reads the written .base, and headless Chrome drives the page.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory
from scipy.spatial.transform import Rotation

from traj_compare.coverage import analyze
from traj_compare.coverage.workbench import workbench_rows, write_trajectory_rrd, write_workbench

DATA_UI = Path(os.environ.get("TRAJ_COMPARE_DATA_UI", "/home/bam/data-ui"))
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
needs_data_ui = pytest.mark.skipif(not ((DATA_UI / "bin" / "data-ui.mjs").is_file() and shutil.which("node")),
                                   reason="needs node and the data-ui repo")
needs_browser = pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")
                                        and (DATA_UI / "bin" / "data-ui.mjs").is_file()),
                                   reason="needs Node Playwright, Chrome and the data-ui repo")

JOINTS = ("base", "shoulder", "elbow")
LIMITS = JointLimits(joint_names=JOINTS, min_position=np.array([-math.pi, -2.0, -math.pi]),
                     max_position=np.array([math.pi, 2.0, math.pi]), max_velocity=np.array([3.0, 3.0, 4.0]),
                     max_acceleration=np.array([15.0, 15.0, 20.0]))
PLANNER = JointLimits(joint_names=JOINTS, max_velocity=np.array([2.4, 2.4, 3.2]))
# (dataset, trajectories): made up; every third trajectory of a dataset is holdout
DATASETS = (("Bench reach", 4), ("Cell pick", 5), ("Cell sweep", 3))
PAGES = ["Overview", "One joint", "Limits", "Tool position", "Tool orientation", "Trajectories"]


def trajectory(seed: int, seconds: float = 3.0) -> tuple[JointTrajectory, PoseTrajectory]:
    """A made-up three-joint move and its tool pose; seeds past 1000 overshoot the speed limit (samples 'outside')."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, seconds, 0.01)
    w = rng.uniform(0.4, 1.6, 3) * (1.8 if seed > 1000 else 1.0)
    amp = rng.uniform(0.3, 1.0, 3) * np.array([math.pi, 2.0, math.pi]) * 0.8
    q = amp * np.sin(w * t[:, None] + rng.uniform(0, 6, 3))
    joint = JointTrajectory(t=t, joint_names=JOINTS, positions=q, limits=LIMITS)
    xyz = np.stack([0.4 + 0.2 * np.cos(q[:, 0]), 0.2 * np.sin(q[:, 0]), 0.3 + 0.1 * np.sin(q[:, 1])], axis=1)
    rot = Rotation.from_euler("zyx", np.stack([q[:, 2], 0.4 * np.sin(q[:, 1]), np.full(len(t), math.pi)], axis=1))
    return joint, PoseTrajectory(t=t, positions=xyz, orientations=rot.as_quat())


def made_up() -> tuple[dict, dict, dict]:
    joints, tools, tags = {}, {}, {}
    seed = 0
    for dataset, count in DATASETS:
        for k in range(count):
            seed += 1
            name = f"{dataset.lower().replace(' ', '-')}/move-{k + 1}"
            joints[name], tools[name] = trajectory(seed if k != 1 else 1000 + seed)
            tags[name] = {"dataset": dataset, "split": "holdout" if k % 3 == 2 else "dev",
                          "kind": "reach" if k % 2 else "sweep", "tags": "Multi waypoint" if k % 2 else "Two point"}
    return joints, tools, tags


@pytest.fixture(scope="module")
def inputs():
    joints, tools, tags = made_up()
    reachable = np.random.default_rng(7).uniform([0.1, -0.35, 0.1], [0.7, 0.35, 0.5], size=(400, 3))
    coverage = analyze(joints, tool=tools, tags=tags, group_by="dataset", planner_limits=PLANNER,
                       reachable=reachable, title="Made-up arm")
    return coverage, joints, tools, tags


@pytest.fixture(scope="module")
def rows(inputs):
    coverage, joints, tools, _ = inputs
    return workbench_rows(coverage, joints, tool=tools, rrd_for=lambda name: f"rrd/{name}.rrd")


@pytest.fixture(scope="module")
def site(inputs, tmp_path_factory) -> Path:
    coverage, joints, tools, _ = inputs
    out = tmp_path_factory.mktemp("workbench")
    for name in joints:
        write_trajectory_rrd(out / "rrd" / f"{name}.rrd", name, joints[name], tool=tools[name])
    write_workbench(coverage, joints, out, tool=tools, title="Made-up arm", rrd_for=lambda name: f"rrd/{name}.rrd")
    return out


# ── the parts add back up to the payload ────────────────────────────────────


def dense(part: dict, key: str, cells: int, fill=0) -> list:
    """A sparse part's list spread over the grid (data-ui's densify, CONTRACT §53)."""
    values = [fill] * cells
    for index, value in zip(part["at"], part[key], strict=True):
        values[index] = value
    return values


def added(parts: list[dict], kind: str, grid: str, key: str, cells: int) -> list:
    total = [0] * cells
    for part in parts:
        if part["kind"] == kind and part["grid"] == grid:
            for index, value in enumerate(dense(part, key, cells) if "at" in part else part[key]):
                total[index] += value
    return total


def visits(parts: list[dict], kind: str, grid: str, cells: int) -> list[int]:
    """Trajectories through each cell: the parts with samples there (what data-ui's sum counts as paths)."""
    total = [0] * cells
    for part in parts:
        if part["kind"] == kind and part["grid"] == grid:
            for index, value in zip(part["at"], part["samples"], strict=True):
                total[index] += value > 0
    return total


def most(parts: list[dict], kind: str, grid: str, key: str, cells: int) -> list:
    out: list = [None] * cells
    for part in parts:
        if part["kind"] == kind and part["grid"] == grid:
            for index, value in zip(part["at"], part[key], strict=True):
                if value is not None:
                    out[index] = value if out[index] is None else max(out[index], value)
    return out


def test_one_trajectory_row_each_with_its_tags_rrd_and_the_payloads_numbers(inputs, rows):
    coverage, joints, _, tags = inputs
    trajectory_rows, _ = rows
    assert [row["name"] for row in trajectory_rows] == list(joints)
    by_name = {row["name"]: row for row in coverage.payload["trajectories"]}
    for row in trajectory_rows:
        assert row["id"] == row["name"]
        for key, value in tags[row["name"]].items():
            assert row[key] == value
        assert row["rrd"] == f"rrd/{row['name']}.rrd"
        source = by_name[row["name"]]
        assert row["duration_s"] == source["duration_s"] and row["samples"] == source["samples"]
        assert row["new_cells"] == source["new_cells"]
        assert row["tool_path_m"] > 0


def test_the_joint_planes_add_back_to_the_payload(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    for joint, planes in payload["planes"].items():
        for name, plane in planes.items():
            cells = plane["shape"][0] * plane["shape"][1]
            grid = f"{joint}.{name}"
            assert added(parts, name, grid, "samples", cells) == plane["samples"], grid
            assert visits(parts, name, grid, cells) == plane["paths"], grid
            if plane["max_other"] is not None:
                assert most(parts, name, grid, "max_other", cells) == plane["max_other"], grid
            assert sum(p["outside"] for p in parts if p["grid"] == grid) == plane["outside"], grid
    assert sum(plane["outside"] for planes in payload["planes"].values() for plane in planes.values()) > 0, \
        "the fixture must put samples outside a box, or 'outside' is not tested"


def test_the_histograms_add_back_to_the_payload_by_group(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    for joint, by_signal in payload["hist"].items():
        for signal, hist in by_signal.items():
            grid = f"{joint}.{signal}"
            mine = [p for p in parts if p["kind"] == "hist" and p["grid"] == grid]
            assert len(mine) == len(payload["trajectories"])
            assert [sum(c) for c in zip(*(p["counts"] for p in mine), strict=True)] == hist["counts"], grid
            assert sum(p["outside"] for p in mine) == hist["outside"], grid
            for group, counts in hist["groups"].items():
                summed = [0] * len(counts)
                for p in mine:
                    for name, group_counts in zip(p["groups"], p["group_counts"], strict=True):
                        if name == group:
                            summed = [a + b for a, b in zip(summed, group_counts, strict=True)]
                assert summed == counts, (grid, group)
            first = mine[0]
            assert [first["lo"], first["hi"], first["bins"]] == hist["edges"]
            limit = payload["limits"][joint][signal]
            assert (first["low"], first["high"], first["limit_source"]) == (limit["low"], limit["high"], limit["source"])
    qd = next(p for p in parts if p["grid"] == f"{JOINTS[0]}.qd")
    assert qd["planner_low"] == -2.4 and qd["planner_high"] == 2.4


def test_the_tool_projections_add_back_to_the_payload(inputs, rows):
    payload = inputs[0].payload
    _, parts = rows
    tool = payload["tool"]
    for face, projection in tool["projections"].items():
        cells = projection["shape"][0] * projection["shape"][1]
        assert added(parts, "tool", face, "samples", cells) == projection["samples"], face
        assert added(parts, "tool", face, "paths", cells) == projection["paths"], face
        assert most(parts, "tool", face, "max_speed", cells) == projection["max_speed"], face
        first = next(p for p in parts if p["kind"] == "tool" and p["grid"] == face)
        assert [first["origin_u"], first["origin_v"]] == projection["origin"]
        assert [first["nu"], first["nv"]] == projection["shape"] and first["pixel_m"] == tool["pixel_m"]


def test_the_tool_directions_add_back_to_the_payload(inputs, rows):
    """The equal-area sphere, the pointing disk (azimuth x tilt) and tilt x yaw, each laid out as a §52 grid row."""
    orientation = inputs[0].payload["tool"]["orientation"]
    _, parts = rows
    rings, sectors = orientation["sphere"]["rings"], orientation["sphere"]["sectors"]
    sphere = added(parts, "sphere", "sphere", "samples", rings * sectors)  # x = sector, y = ring
    assert [sphere[s * rings + r] for r in range(rings) for s in range(sectors)] == orientation["sphere"]["counts"]
    tilts, azimuths = orientation["tilt_azimuth"]["shape"]
    pointing = added(parts, "pointing", "tilt_azimuth", "samples", tilts * azimuths)  # x = azimuth, y = tilt
    assert [pointing[a * tilts + t] for t in range(tilts) for a in range(azimuths)] == orientation["tilt_azimuth"]["counts"]
    tilts, yaws = orientation["tilt_yaw"]["shape"]
    tilt_yaw = added(parts, "tilt_yaw", "tilt_yaw", "samples", tilts * yaws)  # x = yaw, y = tilt
    assert [tilt_yaw[y * tilts + t] for t in range(tilts) for y in range(yaws)] == orientation["tilt_yaw"]["counts"]
    polar = next(p for p in parts if p["kind"] == "pointing")
    assert (polar["x"], polar["y"], polar["nx"], polar["ny"]) == ("azimuth", "tilt", azimuths, tilts)
    assert polar["reference"] == orientation["reference"]


def test_the_tool_speed_histogram_adds_back_to_the_payload(inputs, rows):
    speed = inputs[0].payload["tool"]["speed"]
    _, parts = rows
    mine = [p for p in parts if p["kind"] == "tool_speed"]
    assert [sum(c) for c in zip(*(p["counts"] for p in mine), strict=True)] == speed["counts"]
    assert [mine[0]["lo"], mine[0]["hi"], mine[0]["bins"]] == speed["edges"]


def test_a_part_is_sparse_and_names_its_trajectory(inputs, rows):
    trajectory_rows, parts = rows
    names = {row["id"] for row in trajectory_rows}
    assert {p["trajectory"] for p in parts} == names
    assert len({p["id"] for p in parts}) == len(parts)
    for p in parts:
        if "at" in p:
            assert p["at"] == sorted(set(p["at"]))
            assert all(len(p[k]) == len(p["at"]) for k in ("samples", "paths", "max_other", "max_speed") if k in p)


def test_the_inputs_must_be_the_payloads_trajectories(inputs):
    coverage, joints, tools, _ = inputs
    fewer = dict(list(joints.items())[:-1])
    with pytest.raises(ValueError, match="trajectories"):
        workbench_rows(coverage, fewer, tool=tools)
    with pytest.raises(ValueError, match="tool"):
        workbench_rows(coverage, joints)


# ── the files ───────────────────────────────────────────────────────────────


@needs_data_ui
def test_the_written_base_passes_data_ui_check(site):
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(site / "coverage.base"), "--json"],
                            capture_output=True, text=True, timeout=120)
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["errors"] == 0 and report["warnings"] == 0, report["problems"]


@needs_data_ui
def test_the_base_is_dataset_first_with_the_pages_the_drill_and_the_gear(site):
    yaml = pytest.importorskip("yaml")  # only this test reads the .base back (the writer needs no YAML library)
    base = yaml.safe_load((site / "coverage.base").read_text("utf-8"))
    assert [f.get("property") for f in base["facets"][:4]] == ["dataset", "split", "kind", "tags"]
    assert base["facets"][0]["order"] == [name for name, _ in DATASETS]
    assert [page["name"] for page in base["pages"]] == PAGES
    one_joint = next(page for page in base["pages"] if page["name"] == "One joint")
    assert one_joint["datasets"]["parts"]["facets"][0]["property"] == "joint"
    assert base["noun"] == ["trajectory", "trajectories"]
    assert base["settings"] == ["heatmap.colormap", "heatmap.reverse", "heatmap.scale"]
    action = next(a for a in base["drill"]["actions"] if a["label"] == "Open in Rerun")
    assert action["post"] == "/__rerun/open?rrd={rrd}"
    sums = {view["name"]: view.get("coverage", {}).get("sum") for view in base["views"] if view["type"].startswith("coverage-")}
    assert sums and set(sums.values()) == {"grid"}, sums


@needs_data_ui
def test_each_split_has_its_own_colour_never_red_and_never_a_datasets(site):
    """Found on the UR page (2026-11-24): both splits were muted, so the 'Trajectories per dataset' chart stacked dev and
    holdout in one grey under a two-entry legend. A split is keyed in that chart, so each needs its own slot; not red
    (slot 8 reads as a problem) and not a dataset's slot (the rail and badges colour datasets)."""
    yaml = pytest.importorskip("yaml")
    base = yaml.safe_load((site / "coverage.base").read_text("utf-8"))
    split = base["properties"]["split"]["colors"]
    dataset = set(base["properties"]["dataset"]["colors"].values())
    assert set(split) == {"dev", "holdout"}
    assert len(set(split.values())) == 2 and all(1 <= slot <= 7 for slot in split.values()), split
    assert not set(split.values()) & dataset, (split, dataset)


@needs_data_ui
def test_index_and_embed_are_one_workbench_tag_over_the_vendored_kit(site):
    index = (site / "index.html").read_text("utf-8")
    embed = (site / "embed.html").read_text("utf-8")
    assert index.count("<data-workbench") == 1 and 'src="coverage.base"' in index
    assert 'href="vendor/data-ui/data-ui.css"' in index and 'src="vendor/data-ui/data-ui.js"' in index
    assert embed.count("<data-workbench") == 1 and "no-url" in embed and "1000px" in embed and "680px" in embed
    assert (site / "vendor" / "data-ui" / "data-ui.js").is_file()
    assert (site / "vendor" / "data-ui" / "dashboard.js").is_file()
    vendored = json.loads((site / "vendor" / "data-ui" / "VENDOR.json").read_text("utf-8"))
    assert vendored["ref"] == "main"
    written = json.loads((site / "trajectories.json").read_text("utf-8"))["rows"]
    assert all((site / row["rrd"]).stat().st_size > 1000 for row in written)


@needs_data_ui
def test_without_a_tool_the_tool_tabs_are_left_out(inputs, tmp_path):
    yaml = pytest.importorskip("yaml")
    _, joints, _, tags = inputs
    coverage = analyze(joints, tags=tags, title="Joints only")
    write_workbench(coverage, joints, tmp_path, kit="../kit")  # kit=: nothing vendored
    assert not (tmp_path / "vendor").exists() and 'src="../kit/data-ui.js"' in (tmp_path / "index.html").read_text("utf-8")
    base = yaml.safe_load((tmp_path / "coverage.base").read_text("utf-8"))
    assert [page["name"] for page in base["pages"]] == ["Overview", "One joint", "Limits", "Trajectories"]
    assert "rrd" not in json.loads((tmp_path / "trajectories.json").read_text("utf-8"))["rows"][0]
    assert [a["label"] for a in base["drill"]["actions"]] == ["Copy its name"]
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(tmp_path / "coverage.base"), "--json"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and json.loads(result.stdout)["errors"] == 0, result.stdout[-2000:]


# ── the page in a browser ───────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const out = { errors: [], posts: [] };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  // WHY intercepted: a test never opens a real Rerun window; the POST is recorded and answered here
  await context.route('**/__rerun/open**', (route) => { out.posts.push(route.request().method() + ' ' + route.request().url());
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, command: 'rerun (intercepted)' }) }); });
  const WB = 'data-workbench';
  async function open(url) {
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url);
    await page.waitForSelector(WB + '[data-ready]', { timeout: 30000 });
    await page.waitForTimeout(800);
    return page;
  }
  const count = (page) => page.evaluate(() => document.querySelector('data-workbench data-count').textContent.trim());
  let page = await open(spec.index);
  out.first = await page.evaluate(() => { const g = document.querySelector('data-workbench data-facets section.df-group'); return g && g.dataset.p; });
  out.count0 = await count(page);
  await page.click(`${WB} data-facets section.df-group[data-p="dataset"] input[data-value="${spec.dataset}"]`);
  await page.waitForTimeout(500);
  out.count1 = await count(page);
  out.tabs = await page.evaluate(() => [...document.querySelectorAll('data-workbench data-tabs [role=tab]')].map((t) => t.dataset.tab));
  out.kept = {};
  for (const tab of out.tabs) {
    await page.click(`${WB} data-tabs [role=tab][data-tab="${tab}"]`); await page.waitForTimeout(500);
    out.kept[tab] = await count(page);
  }
  // a record's drill: Open in Rerun posts its rrd
  await page.click(`${WB} [tab="Trajectories"] data-views .dv-view [data-id]`); await page.waitForTimeout(600);
  out.row = await page.evaluate(() => { const r = document.querySelector('data-workbench [tab="Trajectories"] data-views .dv-view [data-id]'); return r && r.dataset.id; });
  const action = await page.$(`${WB} .dv-peek [data-drill-action]:has-text("Open in Rerun")`);
  if (action) { await action.click(); await page.waitForTimeout(500); }
  await page.close();
  // deep links (CONTRACT §53's URL: the rail as search params, the page in #tab=): a host links straight to a filter
  const selectedTab = (p) => p.evaluate(() => { const t = document.querySelector('data-workbench data-tabs [role=tab][aria-selected="true"]'); return t && t.dataset.tab; });
  page = await open(spec.index + spec.deep);
  out.deep = { count: await count(page), tab: await selectedTab(page),
               ticked: await page.evaluate(() => [...document.querySelectorAll('data-workbench data-facets input:checked')].map((i) => i.dataset.value)) };
  await page.close();
  page = await open(spec.index + spec.several);
  out.several = await count(page);
  await page.close();
  page = await open(spec.embed);
  out.embed = await page.evaluate(() => {
    const slot = document.querySelector('#host-slot').getBoundingClientRect();
    const inSlot = (r) => r.left >= slot.left - 1 && r.top >= slot.top - 1 && r.right <= slot.right + 1 && r.bottom <= slot.bottom + 1;
    const wb = document.querySelector('#host-slot > data-workbench').getBoundingClientRect();
    const box = document.querySelector('#host-slot');  // its inner box: the 1 px border is the host's
    return { slot: [box.clientWidth, box.clientHeight], inSlot: inSlot(wb),
             scrollX: document.documentElement.scrollWidth - window.innerWidth };
  });
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def browsed(site) -> dict:
    """Serve the site with traj_compare.serve on a free port (its pid recorded, that pid stopped), drive it."""
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(site), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        line = server.stdout.readline()
        url = line.split(" on ", 1)[1].split()[0].rstrip("/")
        spec = {"index": f"{url}/index.html", "embed": f"{url}/embed.html", "dataset": DATASETS[1][0],
                "deep": f"?dataset={quote(DATASETS[1][0])}&split=holdout#tab=trajectories",
                "several": f"?dataset={quote(DATASETS[0][0])},{quote(DATASETS[1][0])}"}
        (site / "spec.json").write_text(json.dumps(spec))
        (site / "driver.js").write_text(DRIVER)
        result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                                capture_output=True, text=True, timeout=300)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


@needs_browser
def test_the_page_draws_with_no_errors_dataset_first(browsed):
    assert browsed["errors"] == []
    assert browsed["first"] == "dataset"
    total = sum(count for _, count in DATASETS)
    assert browsed["count0"] == f"{total} of {total} trajectories"


@needs_browser
def test_a_dataset_tick_counts_its_trajectories_and_every_tab_keeps_it(browsed):
    total = sum(count for _, count in DATASETS)
    expected = f"{DATASETS[1][1]} of {total} trajectories"
    assert browsed["count1"] == expected
    assert browsed["tabs"] == PAGES
    assert browsed["kept"] == {tab: expected for tab in PAGES}


@needs_browser
def test_open_in_rerun_posts_the_rows_rrd(browsed):
    assert browsed["row"], "no Trajectories row to open"
    rrd = f"rrd/{browsed['row']}.rrd".replace("/", "%2F")
    assert browsed["posts"] and browsed["posts"][0].startswith("POST ") and browsed["posts"][0].endswith(f"rrd={rrd}"), \
        browsed["posts"]


@needs_browser
def test_embedded_it_stays_in_the_hosts_slot(browsed):
    assert browsed["embed"]["slot"] == [1000, 680]
    assert browsed["embed"]["inSlot"] and browsed["embed"]["scrollX"] <= 1


@needs_browser
def test_a_deep_link_opens_with_its_filter_and_tab(browsed):
    """TTA's Deployments page links into a dataset (Zach 2026-11-24: "when you click that deployment type or a particular
    deployment then it takes you to the next page where now you see the dataset overview, with either all or the
    particular dataset you select"). data-ui keeps the rail in the URL (CONTRACT §53), so a link is the filter."""
    total = sum(count for _, count in DATASETS)
    holdout = sum(1 for k in range(DATASETS[1][1]) if k % 3 == 2)
    assert browsed["deep"]["count"] == f"{holdout} of {total} trajectories"
    assert browsed["deep"]["tab"] == "Trajectories"
    assert set(browsed["deep"]["ticked"]) == {DATASETS[1][0], "holdout"}
    assert browsed["several"] == f"{DATASETS[0][1] + DATASETS[1][1]} of {total} trajectories"


def with_deployments(inputs):
    _, joints, tools, tags = inputs
    deployed = {name: {**tag, "deployment": "bench" if tag["dataset"] == "Bench reach" else "cell"} for name, tag in tags.items()}
    return analyze(joints, tool=tools, tags=deployed, group_by="dataset", title="Made-up arm"), joints, tools


@needs_data_ui
def test_a_deployment_leads_the_rail_and_a_static_host_gets_rerun_links(inputs, tmp_path):
    """Datasets compare within one deployment (Zach 2026-11-24), so a deployment tag is the rail's first group; on a static
    host (GitHub Pages) there is no server to POST to, so the record offers the Rerun web viewer and the file instead."""
    yaml = pytest.importorskip("yaml")
    coverage, joints, tools = with_deployments(inputs)
    public = "https://example.github.io/app/datasets/"
    write_workbench(coverage, joints, tmp_path, tool=tools, kit="../kit", rrd_for=lambda name: f"rrd/{name}.rrd",
                    public_url=public, rerun_server=False)
    base = yaml.safe_load((tmp_path / "coverage.base").read_text("utf-8"))
    assert [f.get("property") for f in base["facets"][:3]] == ["deployment", "dataset", "split"]
    actions = base["drill"]["actions"]
    assert not any("post" in action for action in actions), actions
    web = [action for action in actions if str(action.get("href", "")).startswith("https://app.rerun.io/version/0.40.0/")]
    assert len(web) == 1 and "{rrd_url}" in web[0]["href"], actions
    assert any(action.get("href") == "{rrd}" for action in actions), actions
    rows = json.loads((tmp_path / "trajectories.json").read_text("utf-8"))["rows"]
    assert all(row["rrd_url"] == public + row["rrd"] for row in rows)
    assert {row["deployment"] for row in rows} == {"bench", "cell"}
    result = subprocess.run(["node", str(DATA_UI / "bin" / "data-ui.mjs"), "check", str(tmp_path / "coverage.base"), "--json"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and json.loads(result.stdout)["errors"] == 0, result.stdout[-2000:]


@needs_data_ui
def test_served_locally_the_record_posts_to_rerun_and_offers_the_file(site):
    yaml = pytest.importorskip("yaml")
    base = yaml.safe_load((site / "coverage.base").read_text("utf-8"))
    labels = [action["label"] for action in base["drill"]["actions"]]
    assert labels[0] == "Open in Rerun" and any(action.get("href") == "{rrd}" for action in base["drill"]["actions"])


@needs_data_ui
def test_below_the_server_root_the_rerun_post_names_the_file_from_the_root(inputs, tmp_path):
    """TTA (2026-11-24): its workbench sits at /datasets/ur5e/, but traj_compare.serve resolves ?rrd= from the server root,
    so the POST must carry the page's path; the download link stays relative to the page."""
    yaml = pytest.importorskip("yaml")
    _, joints, tools, tags = inputs
    coverage = analyze(joints, tool=tools, tags=tags, group_by="dataset")
    write_workbench(coverage, joints, tmp_path, tool=tools, kit="../kit", rrd_for=lambda name: f"rrd/{name}.rrd",
                    served_at="/datasets/ur5e/")
    actions = yaml.safe_load((tmp_path / "coverage.base").read_text("utf-8"))["drill"]["actions"]
    post = next(action["post"] for action in actions if "post" in action)
    assert post == "/__rerun/open?rrd=datasets/ur5e/{rrd}", post
    assert any(action.get("href") == "{rrd}" for action in actions)


def test_a_host_with_its_own_page_can_skip_index_and_embed(inputs, tmp_path):
    _, joints, tools, tags = inputs
    coverage = analyze(joints, tool=tools, tags=tags, group_by="dataset")
    write_workbench(coverage, joints, tmp_path, tool=tools, kit="../kit", pages=False)
    assert not (tmp_path / "index.html").exists() and not (tmp_path / "embed.html").exists()
    assert (tmp_path / "coverage.base").is_file() and (tmp_path / "trajectories.json").is_file()


def test_a_row_without_a_recording_carries_no_rrd(inputs):
    coverage, joints, tools, _ = inputs
    names = list(joints)
    rows, _ = workbench_rows(coverage, joints, tool=tools, rrd_for={names[0]: f"rrd/{names[0]}.rrd"})
    assert rows[0]["rrd"] == f"rrd/{names[0]}.rrd"
    assert all("rrd" not in row for row in rows[1:]), [row.get("rrd") for row in rows[1:3]]
