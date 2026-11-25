"""One filter, every view: the coverage workbench's rail narrows the trajectories once and every view on every tab
redraws from just those (acceptance for Vibe Tracks feedback fb-a5db22b5, 2026-11-24, track robot-viz-agent).

Zach, 2026-11-24, on the coverage round's V2 "rows first" (the form write_workbench landed): "this view is powerful
beacuse it lets use filter specifically and then see the anlaysis on all of the views. Its kinda like tensor flow ...
where you change what runs are showing."

So this holds the part he called powerful, not just the corner count: tick a filter in the rail, then on EVERY tab EVERY
panel draws from exactly the trajectories the rail keeps, and each coverage figure's drawn numbers equal an oracle summed
here, in Python, from the site's own parts.json over those trajectories. The panels come from the written .base's pages,
so a tab or view added later is held without editing this file, and a panel that cannot be measured fails (fail closed).
test_coverage_workbench.py already proves the part rows add back up to analyze()'s payload exactly, so a figure that
matches this oracle is analyze()'s count restricted to the kept trajectories.

Mutation-tested 2026-11-25, both red, the writer restored after each: with the .base's `links:` (trajectories.id ->
parts.trajectory) dropped, every parts view stops following the rail, so the two filtered states fail (and the walk
reports figures that never redrew) while the unfiltered state passes; with only "Tool speed" pointed at an unlinked copy
of parts.json, exactly "Tool position · Tool speed" is named (drew 3600 samples from 12 trajectories; oracle 900 from 3).

    TRAJ_COMPARE_REQUIRE_BROWSER=1 uv run --extra test --extra rerun --extra export python -m pytest -q tests/test_coverage_workbench_filter_every_view.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest
from test_coverage_workbench import CHROME, DATASETS, PLANNER, PLAYWRIGHT, made_up, needs_browser

from traj_compare.coverage import analyze
from traj_compare.coverage import workbench as workbench_module
from traj_compare.coverage.workbench import write_workbench

# WHY a switch: CI (no Chrome, no data-ui) skips the browser tests, but a skipped spec passes a check without proving
# anything, so whoever claims this spec runs it with TRAJ_COMPARE_REQUIRE_BROWSER=1 and a missing tool fails instead
pytestmark = [] if os.environ.get("TRAJ_COMPARE_REQUIRE_BROWSER") == "1" else [needs_browser]

# (state, the rail clicks that lead to it from the state before): none, Zach's own "tick holdout" (one trajectory from
# each dataset), then a dataset on top of it, so every figure narrows to that one trajectory ("filter specifically")
STATES = (("unfiltered", ()), ("holdout", (("split", "holdout"),)), ("holdout of one dataset", (("dataset", DATASETS[1][0]),)))

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const spec = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const out = { errors: [], states: {} };
  page.on('pageerror', (e) => out.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
  const WB = 'data-workbench';
  await page.goto(spec.index);
  await page.waitForSelector(WB + '[data-ready]', { timeout: 30000 });
  await page.waitForTimeout(800);
  // what the shown tab draws: every <data-views> panel, the trajectories its rows belong to, a coverage figure's hook
  // (data-ui CONTRACT §53: one row per figure it drew, its samples added up and how many part rows it summed), and the
  // record ids a table put on screen
  const measure = () => page.evaluate(() => {
    const wb = document.querySelector('data-workbench');
    const shown = [...wb.querySelectorAll('[tab]')].find((p) => !p.hidden);
    return { tab: shown && shown.getAttribute('tab'), count: wb.querySelector('data-count').textContent.trim(),
      views: [...shown.querySelectorAll('data-views')].map((e) => {
        const root = e.querySelector('.dv-view');
        const hook = root && root.coverage;
        const rows = (e.model && e.model.rows) || null;
        return { name: e.view && e.view.name, type: e.view && e.view.type, from: e.view && e.view.from,
          trajectories: rows && [...new Set(rows.map((r) => ('trajectory' in r ? r.trajectory : r.id)))].sort(),
          drawn: hook ? hook.drawn : null,
          figures: hook ? (hook.rows || []).map((r) => ({ id: r.id, total: r.total, summed: r.summed })) : null,
          problems: hook ? hook.problems || [] : null,
          onScreen: root ? [...new Set([...root.querySelectorAll('[data-id]')].map((x) => x.dataset.id))].sort() : [] };
      }) };
  });
  const tabs = await page.evaluate(() => [...document.querySelectorAll('data-workbench data-tabs [role=tab]')].map((t) => t.dataset.tab));
  const drawnBefore = {};
  for (const [state, clicks] of spec.states) {
    for (const [prop, value] of clicks) {
      await page.click(`${WB} data-facets section.df-group[data-p="${prop}"] input[data-value="${value}"]`);
      await page.waitForTimeout(400);
    }
    out.states[state] = {};
    for (const tab of tabs) {
      await page.click(`${WB} data-tabs [role=tab][data-tab="${tab}"]`);
      // a hidden page catches up with the filter when shown: wait until each of its figures has drawn again
      try {
        await page.waitForFunction((args) => {
          const [tab, before] = args;
          const shown = [...document.querySelector('data-workbench').querySelectorAll('[tab]')].find((p) => p.getAttribute('tab') === tab);
          if (!shown || shown.hidden) return false;
          return [...shown.querySelectorAll('data-views')].every((e) => {
            if (!(e.view && String(e.view.type).startsWith('coverage-'))) return true;
            const root = e.querySelector('.dv-view'); const hook = root && root.coverage;
            return hook && hook.drawn > (before[tab + '|' + e.view.name] || 0);
          });
        }, [tab, drawnBefore], { timeout: 15000 });
      } catch (e) { out.errors.push(`${state} · ${tab}: a figure never redrew (${String(e).slice(0, 120)})`); }
      await page.waitForTimeout(300);
      const m = await measure();
      for (const v of m.views) if (v.drawn !== null) drawnBefore[tab + '|' + v.name] = v.drawn;
      out.states[state][tab] = m;
    }
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def written(tmp_path_factory) -> tuple[Path, dict]:
    """(the site, the .base the writer serialised into its coverage.base). WHY the dict, not the file read back: the
    .base is YAML and this environment has no YAML library (test_coverage_workbench.py's two readers skip without
    one); a skipped spec proves nothing, so the dict is caught on its way to the file instead."""
    joints, tools, tags = made_up()
    reachable = np.random.default_rng(7).uniform([0.1, -0.35, 0.1], [0.7, 0.35, 0.5], size=(400, 3))
    coverage = analyze(joints, tool=tools, tags=tags, group_by="dataset", planner_limits=PLANNER,
                       reachable=reachable, title="Made-up arm")
    out = tmp_path_factory.mktemp("filter-every-view")
    built: list[dict] = []
    real = workbench_module._base
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(workbench_module, "_base", lambda *args, **kwargs: built.append(real(*args, **kwargs)) or built[-1])
        write_workbench(coverage, joints, out, tool=tools, title="Made-up arm")
    assert len(built) == 1
    text = (out / "coverage.base").read_text("utf-8")
    assert all(f"name: {page['name']}" in text for page in built[0]["pages"]), "the caught .base is not the file's"
    return out, built[0]


@pytest.fixture(scope="module")
def site(written) -> Path:
    return written[0]


@pytest.fixture(scope="module")
def base(written) -> dict:
    return written[1]


@pytest.fixture(scope="module")
def browsed(site) -> dict:
    """Serve the site with traj_compare.serve on a free port (its pid recorded, that pid stopped), walk every state."""
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(site), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        url = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/")
        (site / "spec.json").write_text(json.dumps({"index": f"{url}/index.html", "states": STATES}))
        (site / "driver.js").write_text(DRIVER)
        result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                                capture_output=True, text=True, timeout=600)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


# ── the oracle: the site's own files, read here ─────────────────────────────


def kept(site: Path, state: str) -> list[str]:
    """The trajectories the rail keeps after this state's clicks (a group's ticks OR, groups AND, as data-ui's rail)."""
    picked: dict[str, set[str]] = defaultdict(set)
    for _, clicks in STATES[: [s for s, _ in STATES].index(state) + 1]:
        for prop, value in clicks:
            picked[prop] ^= {value}
    rows = json.loads((site / "trajectories.json").read_text("utf-8"))["rows"]
    return sorted(r["id"] for r in rows if all(not values or r[prop] in values for prop, values in picked.items()))


def clauses(expression: str | None) -> dict[str, str]:
    """`kind == "tool" && grid == "xy"` as {kind: tool, grid: xy}; any other form fails loudly, never mis-sums."""
    out: dict[str, str] = {}
    for part in expression.split("&&") if expression else ():
        match = re.fullmatch(r'\s*(\w+)\s*==\s*"([^"]*)"\s*', part)
        assert match, f"this oracle reads only `key == \"value\"` clauses joined by &&, not {expression!r}"
        out[match[1]] = match[2]
    return out


def figures(site: Path, view: dict, page: dict, keep: list[str]) -> dict[str, dict]:
    """{`sum:<grid>`: {total, summed}}: what a `coverage.sum: grid` view must draw over the kept trajectories' parts,
    narrowed by the view's own filter and its page's own control (One joint's Joint picker at its default)."""
    want = {**clauses(view.get("filters")), **clauses(page.get("datasets", {}).get(view["from"], {}).get("filters"))}
    keep_set = set(keep)
    out: dict[str, dict] = {}
    for part in json.loads((site / "parts.json").read_text("utf-8"))["rows"]:
        if part["trajectory"] not in keep_set or any(str(part.get(k)) != v for k, v in want.items()):
            continue
        figure = out.setdefault(f"sum:{part[view['coverage']['sum']]}", {"total": 0, "summed": 0})
        figure["total"] += sum(part.get("samples") or part.get("counts") or [])
        figure["summed"] += 1
    return out


def panels(base: dict) -> dict[str, list[str]]:
    return {page["name"]: [panel["view"] for panel in page["layout"]["panels"]] for page in base["pages"]}


# ── the spec ────────────────────────────────────────────────────────────────


def test_every_tab_was_walked_in_every_state_with_no_errors(browsed, base):
    assert browsed["errors"] == []
    for state, _ in STATES:
        assert list(browsed["states"][state]) == list(panels(base)), state


@pytest.mark.parametrize("state", [s for s, _ in STATES])
def test_the_corner_counts_what_the_rail_keeps_on_every_tab(browsed, site, base, state):
    total = len(json.loads((site / "trajectories.json").read_text("utf-8"))["rows"])
    expected = f"{len(kept(site, state))} of {total} trajectories"
    assert {tab: m["count"] for tab, m in browsed["states"][state].items()} == {tab: expected for tab in panels(base)}


@pytest.mark.parametrize("state", [s for s, _ in STATES])
def test_every_view_on_every_tab_draws_only_the_trajectories_the_rail_keeps(browsed, site, base, state):
    """The panels are the .base's, so none is skipped; each draws from exactly the kept trajectories, and a table puts
    exactly those records on screen."""
    keep = kept(site, state)
    views = {v["name"]: v for v in base["views"]}
    wrong = {}
    for tab, names in panels(base).items():
        measured = {v["name"]: v for v in browsed["states"][state][tab]["views"]}
        assert sorted(measured) == sorted(names), f"{state} · {tab}: measured {sorted(measured)}, the .base has {names}"
        for name in names:
            got = measured[name]
            if got["trajectories"] != keep:
                wrong[f"{tab} · {name}"] = got["trajectories"]
            if views[name]["type"] == "table" and got["onScreen"] != keep:
                wrong[f"{tab} · {name} (on screen)"] = got["onScreen"]
    assert not wrong, {"state": state, "kept": keep, "wrong": wrong}


@pytest.mark.parametrize("state", [s for s, _ in STATES])
def test_every_coverage_figure_on_every_tab_is_the_kept_trajectories_summed(browsed, site, base, state):
    """Each coverage figure's drawn numbers (its samples added up, how many part rows it summed) equal the oracle
    summed from parts.json over the kept trajectories: the analysis itself redraws, not just a label."""
    keep = kept(site, state)
    pages = {page["name"]: page for page in base["pages"]}
    views = {v["name"]: v for v in base["views"]}
    coverage = [(tab, name) for tab, names in panels(base).items() for name in names
                if views[name]["type"].startswith("coverage-")]
    assert coverage, "the .base has no coverage figure, so this would prove nothing"
    wrong = {}
    for tab, name in coverage:
        got = next(v for v in browsed["states"][state][tab]["views"] if v["name"] == name)
        drawn = {f["id"]: {"total": f["total"], "summed": f["summed"]} for f in got["figures"] or []}
        expected = figures(site, views[name], pages[tab], keep)
        assert expected, f"{tab} · {name}: the oracle found no parts, so it would prove nothing"
        if drawn != expected or got["problems"]:
            wrong[f"{tab} · {name}"] = {"drawn": drawn, "oracle": expected, "problems": got["problems"]}
    assert not wrong, {"state": state, "kept": keep, "wrong": wrong}
