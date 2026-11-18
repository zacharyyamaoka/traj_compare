"""ScatterChart: a clickable x/y scatter (optionally with its Pareto front) on any ReportPage.

WHY (Zach, Daily Note 2026-11-18): "the pareto curve showing the speed vs trajectory error. Each of those points should
basically go to a run of the pendulum that I can view in rerun". A point with an href is a real
<a target="_blank" rel="noopener">: the local Rerun launcher only launches on a top-level, user-activated navigation.

The browser half needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``, else the first checkout below that has
it) and is skipped otherwise. Run (the rig host may be live, so pinned and niced):

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV uv run --frozen --extra test python -m pytest tests/test_scatter.py -q -p no:cacheprovider
"""

import dataclasses
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointTrajectory

from traj_compare import (
    BarChart,
    BarSeries,
    Comparison,
    MetricCard,
    ReportPage,
    ScatterChart,
    ScatterPoint,
    ScatterSeries,
    Situation,
    pareto_front,
    write_comparison_report,
)
from traj_compare.dataset import Run, write_dataset_report
from traj_compare.model import safe_href

# ── the dataclasses ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("x, y", [(float("nan"), 1.0), (1.0, float("inf")), (float("-inf"), 0.0)])
def test_a_point_refuses_a_non_finite_coordinate(x, y):
    with pytest.raises(ValueError, match="finite"):
        ScatterPoint(x, y)


@pytest.mark.parametrize("size", [0.0, -2.0, float("nan")])
def test_a_point_refuses_a_non_positive_or_non_finite_size(size):
    with pytest.raises(ValueError):
        ScatterPoint(1.0, 2.0, size=size)


def test_a_chart_refuses_an_unknown_pareto_mode():
    series = [ScatterSeries("A", [ScatterPoint(1.0, 2.0)])]
    with pytest.raises(ValueError, match="pareto"):
        ScatterChart("Speed vs error", "speed", "error", series, pareto="min_x_max_y")
    assert ScatterChart("ok", "speed", "error", series, pareto="max_x_min_y").pareto == "max_x_min_y"


def test_a_chart_needs_a_series_and_typed_parts():
    with pytest.raises(ValueError, match="at least one series"):
        ScatterChart("empty", "x", "y", [])
    with pytest.raises(TypeError):
        ScatterSeries("A", [(1.0, 2.0)])  # a bare tuple is not a ScatterPoint
    with pytest.raises(TypeError):
        ScatterChart("t", "x", "y", [{"name": "A"}])


def test_a_series_validates_its_line_and_band():
    with pytest.raises(ValueError, match="finite"):
        ScatterSeries("A", [], line=[(0.0, float("nan"))])
    with pytest.raises(ValueError, match="low"):
        ScatterSeries("A", [], band=[(0.0, 2.0, 1.0)])
    series = ScatterSeries("A", [], line=[(0, 1), (1, 2)], band=[(0, 0.5, 1.5)])
    assert series.line == ((0.0, 1.0), (1.0, 2.0)) and series.band == ((0.0, 0.5, 1.5),)


def test_log_y_refuses_a_y_that_is_not_positive():
    with pytest.raises(ValueError, match="log_y"):
        ScatterChart("t", "x", "y", [ScatterSeries("A", [ScatterPoint(1.0, 0.0)])], log_y=True)
    with pytest.raises(ValueError, match="log_y"):
        ScatterChart("t", "x", "y", [ScatterSeries("A", [ScatterPoint(1.0, 1.0)], band=[(1.0, -1.0, 2.0)])], log_y=True)
    ScatterChart("t", "x", "y", [ScatterSeries("A", [ScatterPoint(1.0, 0.0)])])  # linear y takes a zero


def test_the_dataclasses_are_frozen():
    point = ScatterPoint(1, 2, label="a")
    assert (point.x, point.y) == (1.0, 2.0) and isinstance(point.x, float)
    with pytest.raises(dataclasses.FrozenInstanceError):
        point.x = 3.0  # type: ignore[misc]
    chart = ScatterChart("t", "x", "y", [ScatterSeries("A", [point])])
    with pytest.raises(dataclasses.FrozenInstanceError):
        chart.pareto = "max_x_min_y"  # type: ignore[misc]


@pytest.mark.parametrize(
    "href, kept",
    [
        ("http://127.0.0.1:8771/open?rrd=a.rrd", "http://127.0.0.1:8771/open?rrd=a.rrd"),
        ("HTTPS://example.org/x", "HTTPS://example.org/x"),
        ("runs/a/report.html", "runs/a/report.html"),
        ("../up.html#t=1", "../up.html#t=1"),
        ("  runs/a.html ", "runs/a.html"),
        ("javascript:alert(1)", ""),
        ("JavaScript:alert(1)", ""),
        (" \x01javascript:alert(1)", ""),
        ("java\tscript:alert(1)", ""),
        ("data:text/html,<script>alert(1)</script>", ""),
        ("file:///etc/passwd", ""),
        ("", ""),
    ],
)
def test_safe_href_keeps_only_http_and_relative_links(href, kept):
    assert safe_href(href) == kept


# ── the Pareto front ─────────────────────────────────────────────────────────


def test_pareto_front_keeps_the_non_dominated_points_in_ascending_x():
    points = [(1.0, 1.0), (2.0, 3.0), (2.0, 2.0), (3.0, 2.5), (3.0, 4.0), (0.5, 0.5), (1.5, 1.0)]
    assert pareto_front(points) == [(0.5, 0.5), (1.5, 1.0), (2.0, 2.0), (3.0, 2.5)]
    assert pareto_front([(1.0, 1.0), (1.0, 1.0)]) == [(1.0, 1.0)]  # a duplicate counts once
    assert pareto_front([]) == []
    with pytest.raises(ValueError):
        pareto_front(points, mode="min_x_min_y")


def test_pareto_front_matches_brute_force_dominance():
    rng = np.random.default_rng(7)
    points = [(float(x), float(y)) for x, y in np.round(rng.uniform(0, 10, size=(200, 2)), 1)]

    def dominated(point):  # someone at least as fast and strictly better, or faster and as good
        return any((ox >= point[0] and oy < point[1]) or (ox > point[0] and oy <= point[1]) for ox, oy in points)

    expected = sorted({point for point in points if not dominated(point)})
    assert pareto_front(points) == expected


# ── the report pages ─────────────────────────────────────────────────────────

SAFE = "http://127.0.0.1:8771/open?rrd=runs%2Fkp8%2Fspeed_1.rrd"
RELATIVE = "runs/kp8_speed_2.html"
EVIL = "javascript:alert(1)"


def speed_vs_error() -> ScatterChart:
    return ScatterChart(
        title="Speed vs tracking error",
        x_label="peak speed",
        y_label="RMS error",
        x_unit="deg/s",
        y_unit="deg",
        pareto="max_x_min_y",
        series=[
            ScatterSeries(
                "Kp 8",
                [
                    ScatterPoint(90.0, 0.8, label="Kp 8 · 90 deg/s\nrun 1", href=SAFE),
                    ScatterPoint(180.0, 1.9, label="Kp 8 · 180 deg/s", href=RELATIVE),
                    ScatterPoint(270.0, 4.2, label="Kp 8 · 270 deg/s <b>bold?</b>", href=EVIL),
                ],
                line=[(90.0, 0.8), (180.0, 1.9), (270.0, 4.2)],
                band=[(90.0, 0.6, 1.0), (180.0, 1.5, 2.3), (270.0, 3.6, 5.0)],
            ),
            ScatterSeries("Kp 16", [ScatterPoint(90.0, 0.5), ScatterPoint(180.0, 2.4), ScatterPoint(300.0, 3.9)]),
        ],
    )


def small_comparison() -> Comparison:
    t = np.linspace(0.0, 1.0, 40)
    q = np.column_stack([0.3 * t])
    return Comparison(
        title="pendulum",
        joint_names=["j1"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[Situation(name="real", title="Real", t=t, q=q + 0.002)],
    )


def summary_page() -> ReportPage:
    return ReportPage(
        name="summary",
        title="Summary",
        metrics=[MetricCard("Runs", "6")],
        scatters=[speed_vs_error()],
        charts=[BarChart("Errors", ["A"], [BarSeries("Kp 8", [1.0])])],
    )


def report_payload(document: str, script_id: str) -> dict:
    match = re.search(rf'<script type="application/json" id="{script_id}">(.*?)</script>', document, re.S)
    assert match, f"no {script_id} payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


def assert_scatter_payload(scatter: dict) -> None:
    assert scatter["title"] == "Speed vs tracking error"
    assert scatter["pareto"] == "max_x_min_y" and scatter["log_y"] is False
    assert (scatter["x_unit"], scatter["y_unit"]) == ("deg/s", "deg")
    assert [series["name"] for series in scatter["series"]] == ["Kp 8", "Kp 16"]
    hrefs = [point["href"] for point in scatter["series"][0]["points"]]
    assert hrefs == [SAFE, RELATIVE, ""], "the javascript: link must be dropped, the others kept"
    assert scatter["series"][0]["points"][0]["label"] == "Kp 8 · 90 deg/s\nrun 1"
    assert scatter["series"][0]["band"][1] == [180.0, 1.5, 2.3]
    assert scatter["series"][1]["line"] is None


def test_a_report_page_without_scatters_still_carries_an_empty_list():
    assert ReportPage(title="Summary").to_payload()["scatters"] == []


def test_the_comparison_reports_summary_page_carries_the_scatter(tmp_path):
    with pytest.warns(UserWarning, match="dropped the link"):
        path = write_comparison_report(small_comparison(), tmp_path, summary=summary_page(),
                                       insights=ReportPage(title="Insights", scatters=[speed_vs_error()]))
    document = path.read_text("utf-8")
    payload = report_payload(document, "traj-compare-data")
    summary, insights = payload["report_pages"]
    assert_scatter_payload(summary["scatters"][0])
    assert_scatter_payload(insights["scatters"][0])
    assert EVIL not in document
    assert "function buildScatterChart" in document
    # the renderer makes every linked point a new-tab anchor (checked live in the browser test below)
    assert "target: '_blank', rel: 'noopener'" in document


def dataset_runs() -> list[Run]:
    t = np.linspace(0.0, 2.0, 201)
    names = ("j1",)
    runs = []
    for index in range(2):
        reference = JointTrajectory(t=t, joint_names=names, positions=(0.4 * np.sin(t))[:, None])
        real = JointTrajectory(t=t, joint_names=names, positions=(0.4 * np.sin(t - 0.02) + 0.001 * (index + 1))[:, None])
        runs.append(Run(name=f"pendulum rep {index}", reference=reference, measured={"real": real}, tags={"rep": index}))
    return runs


def test_the_dataset_reports_summary_page_carries_the_scatter(tmp_path):
    with pytest.warns(UserWarning, match="dropped the link"):
        index = write_dataset_report(dataset_runs(), tmp_path, title="Pendulum sweep", summary=summary_page())
    document = index.read_text("utf-8")
    payload = report_payload(document, "traj-compare-dataset")
    assert_scatter_payload(payload["summary"]["scatters"][0])
    assert EVIL not in document
    assert "function buildScatterChart" in document  # plots.js rides along whenever a summary is given


# ── in a real browser ────────────────────────────────────────────────────────

PLAYWRIGHT_CANDIDATES = [
    os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", ""),
    "/home/bam/aruco-studio/web/node_modules/playwright",
    "/home/bam/clank-markdownify/node_modules/playwright",
]
PLAYWRIGHT = next((Path(path) for path in PLAYWRIGHT_CANDIDATES if path and Path(path).is_dir()), None)
CHROME = Path("/usr/bin/google-chrome")
needs_browser = pytest.mark.skipif(
    not (PLAYWRIGHT and CHROME.is_file() and shutil.which("node")), reason="needs Node Playwright and Chrome"
)

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const config = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const inspect = (points) => {
  const root = document.querySelector('.tc-scatter');
  const page = root.parentElement;
  const front = root.querySelector('path.tc-sc-front');
  return {
    anchors: [...root.querySelectorAll('svg a')].map(a => ({ href: a.getAttribute('href'), target: a.getAttribute('target'), rel: a.getAttribute('rel') })),
    dots: root.querySelectorAll('circle.tc-sc-dot').length,
    onFront: root.querySelectorAll('circle.tc-sc-dot.on-front').length,
    frontD: front ? front.getAttribute('d') : null,
    bands: root.querySelectorAll('polygon.tc-sc-band').length,
    lines: root.querySelectorAll('polyline.tc-sc-line').length,
    legend: [...root.querySelectorAll('.tc-scatter-legend .chip')].map(c => c.textContent),
    order: [...page.children].map(c => c.className).filter(c => c.indexOf('tc-') === 0),
    scrollWidth: document.documentElement.scrollWidth,
    svgWidth: root.querySelector('svg').getBoundingClientRect().width,
    sectionRight: root.getBoundingClientRect().right,
    jsFront: points ? TrajCompare.scatter.paretoFront(points.map(p => ({ x: p[0], y: p[1] }))).map(p => [p.x, p.y]) : null,
    jsSafe: TrajCompare.scatter.safeHref(' java\tscript:alert(1)'),
  };
};
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[4], headless: true, args: ['--disable-gpu', '--renderer-process-limit=2'] });
  const out = {};
  for (const [name, file] of Object.entries(config.reports)) {
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto('file://' + file);
    await page.waitForTimeout(500);
    if (name === 'comparison') {
      await page.locator('#tc-tabs').getByText('Summary', { exact: true }).first().click();
      await page.waitForTimeout(300);
    }
    const result = { before: await page.evaluate(inspect, config.points) };
    await page.hover('.tc-scatter svg a');
    result.tip = await page.evaluate(() => { const tip = document.querySelector('.tc-scatter-tip'); return tip.hidden ? null : tip.textContent; });
    await page.locator('.tc-scatter-legend .chip').first().click();  // hide series "Kp 8"
    await page.waitForTimeout(100);
    result.after = await page.evaluate(inspect, null);
    await page.locator('.tc-scatter-legend .chip').first().click();  // and back
    await page.waitForTimeout(100);
    if (name === 'comparison') {
      const [popup] = await Promise.all([context.waitForEvent('page'), page.click('.tc-scatter svg a[href="' + config.relative + '"]')]);
      result.popup = popup.url();
    }
    result.errors = errors;
    out[name] = result;
    await context.close();
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""


@needs_browser
def test_the_scatter_draws_new_tab_links_toggles_and_recomputes_its_front_in_a_browser(tmp_path):
    with pytest.warns(UserWarning):
        comparison = write_comparison_report(small_comparison(), tmp_path / "comparison", summary=summary_page())
        dataset = write_dataset_report(dataset_runs(), tmp_path / "dataset", title="Pendulum sweep", summary=summary_page())
    (comparison.parent / RELATIVE).parent.mkdir(parents=True, exist_ok=True)
    (comparison.parent / RELATIVE).write_text("<p>run</p>")
    rng = np.random.default_rng(3)
    points = [[float(x), float(y)] for x, y in np.round(rng.uniform(0, 10, size=(80, 2)), 1)]
    config = {"reports": {"comparison": str(comparison), "dataset": str(dataset)}, "points": points, "relative": RELATIVE}
    (tmp_path / "config.json").write_text(json.dumps(config))
    (tmp_path / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(tmp_path / "driver.js"), str(PLAYWRIGHT), str(tmp_path / "config.json"), str(CHROME)],
                            capture_output=True, text=True, check=True, timeout=180)
    out = json.loads(result.stdout.strip().splitlines()[-1])

    for name, view in out.items():
        before, after = view["before"], view["after"]
        assert view["errors"] == [], f"{name}: console errors {view['errors']}"
        assert before["anchors"] == [
            {"href": SAFE, "target": "_blank", "rel": "noopener"},
            {"href": RELATIVE, "target": "_blank", "rel": "noopener"},
        ], f"{name}: linked points must be new-tab anchors and the javascript: one a plain circle"
        assert before["dots"] == 6 and before["bands"] == 1 and before["lines"] == 1
        # front over all six points: (90, 0.5) (180, 1.9) (300, 3.9)
        assert before["onFront"] == 3 and before["frontD"] is not None
        assert before["legend"][0].startswith("Kp 8") and before["legend"][-1].startswith("Pareto front")
        assert "Kp 8 · 90 deg/s" in view["tip"] and "run 1" in view["tip"]
        assert before["jsFront"] == [list(point) for point in pareto_front([tuple(point) for point in points])]
        assert before["jsSafe"] == ""
        # metric cards, then the scatter, then the bar chart
        order = [entry.split()[0] for entry in before["order"]]
        assert order.index("tc-metriccards") < order.index("tc-summary-chart")
        assert before["order"].index("tc-summary-chart tc-scatter") < before["order"].index("tc-summary-chart")
        assert before["scrollWidth"] <= 1400 and before["sectionRight"] <= 1400 and before["svgWidth"] > 600
        # hiding "Kp 8" leaves Kp 16's three points; its front is (90, 0.5) (180, 2.4) (300, 3.9)
        assert after["dots"] == 3 and after["anchors"] == [] and after["bands"] == 0 and after["lines"] == 0
        assert after["onFront"] == 3 and after["frontD"] != before["frontD"]
    assert out["comparison"]["popup"].endswith(RELATIVE)
