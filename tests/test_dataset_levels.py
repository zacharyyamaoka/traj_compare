"""Dataset → Target → Run: the three-level dataset view (acceptance, written before the UI, 2026-11-19).

The contract is docs/NAVIGATION.md Part A (frozen @ 3362cda26). Zach: "the Target trajectory is kinda the primary thing we
want to organize things around", targets "as table or cards", and on a target, runs sortable "by date, configuration type,
sim/real". The data is tests/dataset_levels_fixture.py (production ``Run``s: 3 targets, 2 configs, 2 dates, sim and real).

Everything on the page is measured in headless Chrome (getBoundingClientRect, counts, text, order), never asserted from
DOM presence alone. One driver run opens every page once (``levels`` fixture) and each test checks its part, so a missing
hook fails its own test with its own first assertion. Hooks NAVIGATION.md does not name, which this file also relies on:
``[data-tc-target-panel="repeat" | "history"]`` (a target tab's panel), ``[data-tc-run-list-resize]`` and
``[data-tc-run-list-fold]`` (the run list's edge and fold, as Part B's stage), the regex filter = the run list's first text
or search ``<input>``, and a run report's breadcrumb = an ``<a>`` whose href attribute is ``../../index.html#/target/<slug>``.
A target's slug is dataset.py's ``_slug`` of its key (``"full-circle-slow"`` stays as is); ``data-config`` and
``data-date`` carry the tag values as text.

Needs Chrome and Node Playwright (``TRAJ_COMPARE_PLAYWRIGHT``, default the aruco-studio checkout's) for the browser
tests; those are skipped otherwise. Run:

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV uv run --extra test pytest -q -p no:cacheprovider tests/test_dataset_levels.py
"""

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from dataset_levels_fixture import (
    BASELINE,
    CALIBRATED,
    CONFIG_TAG,
    FIRST_DAY,
    SECOND_DAY,
    TARGET_TAG,
    TARGETS,
    build_runs,
    kind_of,
    lines_of,
    retagged,
    untagged,
)

from traj_compare import build_drill_down, default_pairs, write_dataset_report

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

needs_browser = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)

RUNS = build_runs()
LINES = lines_of(RUNS)
OPENED = "full-circle-slow"  # the target opened from its card: 7 lines of v1 (a fan), 3 of v2 (lines)
DEEP_LINKED = "full-circle-fast"  # the target opened by its address: series "twin_it5" and "real_retake"
DRILLED_RUN = "slow v1 rep 1"  # the run whose report is built and whose breadcrumb is followed
FILTER = r"v1 rep [2-4]"  # a regex (a character class), so a substring filter finds nothing
DRAG_PX = 120


def slug(text: str) -> str:
    """dataset.py's ``_slug``: the target's key in its address and its ``data-tc-target-*`` value."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def lines_up_to_n_above_every_group() -> int:
    """One more than the largest config group on the opened target (sims counted in), so every group draws lines."""
    return max(Counter(line.config for line in lines_of(RUNS, OPENED)).values()) + 1


# ── the browser driver ───────────────────────────────────────────────────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const WAIT = 4000;
const SETTLE = 400;
// WHY a pause before every reload: a localStorage write still in flight when the page reloads can be lost (seen once
// in 2 runs at 400 ms on the pinned, niced CPUs); a person never reloads that fast after a click.
const BEFORE_RELOAD = 1000;

// Measurements every page needs, defined before the page's own scripts run.
const HELPERS = String.raw`
window.__tc = {
  visible(el) {
    if (!el) return false;
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  },
  rect(el) {
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  },
  all(selector, root) { return Array.from((root || document).querySelectorAll(selector)); },
  shown(selector, root) { return __tc.all(selector, root).filter((el) => __tc.visible(el)); },
  text(el) { return el ? el.textContent.replace(/\s+/g, ' ').trim() : null; },
  level() {
    return {
      hash: location.hash,
      summary: __tc.visible(document.querySelector('[data-tc-dataset-summary]')),
      cards: __tc.shown('[data-tc-target-card]').map((card) => ({
        slug: card.getAttribute('data-tc-target-card'),
        text: __tc.text(card),
        open: __tc.shown('a, button', card).filter((control) => /open target/i.test(control.textContent)).length,
      })),
      target_rows: __tc.shown('[data-tc-target-row]').map((row) => row.getAttribute('data-tc-target-row')),
      runs_table_rows: __tc.shown('.ds-table tbody tr').length,
      open_run_links: __tc.shown('.ds-table a').filter((link) => /open run/i.test(link.textContent)).length,
      run_list: __tc.visible(document.querySelector('[data-tc-run-list]')),
    };
  },
  runRows() {
    const list = document.querySelector('[data-tc-run-list]');
    if (!list) return null;
    return __tc.shown('[data-tc-run]', list).map((row) => ({
      line: row.getAttribute('data-line'),
      config: row.getAttribute('data-config'),
      kind: row.getAttribute('data-kind'),
      date: row.getAttribute('data-date'),
      hrefs: __tc.all('a[href]', row).map((link) => link.getAttribute('href')),
    }));
  },
  listWidth() {
    const box = __tc.rect(document.querySelector('[data-tc-run-list]'));
    return box ? box.width : null;
  },
  draws() {
    return __tc.shown('[data-tc-draw]').filter((el) => !el.closest('[data-tc-target-card]')).map((el) => ({
      config: el.getAttribute('data-config'),
      draw: el.getAttribute('data-draw'),
    }));
  },
  linesInput() {
    const el = document.querySelector('[data-tc-lines-n]');
    return el && (el.matches('input') ? el : el.querySelector('input'));
  },
  tabs() {
    return __tc.all('[data-tc-target-tab]').map((tab) => ({
      tab: tab.getAttribute('data-tab'), text: __tc.text(tab), visible: __tc.visible(tab),
    }));
  },
  panels() {
    const out = {};
    __tc.all('[data-tc-target-panel]').forEach((panel) => {
      const areas = __tc.all('svg, canvas', panel).map((chart) => {
        const box = chart.getBoundingClientRect();
        return box.width * box.height;
      });
      out[panel.getAttribute('data-tc-target-panel')] = {
        visible: __tc.visible(panel), chart_area: areas.length ? Math.max.apply(null, areas) : 0,
      };
    });
    return out;
  },
};`;

(async () => {
  const browser = await chromium.launch({
    executablePath: process.argv[3], headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const out = { errors: [] };

  async function open(url) {
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    await context.addInitScript(HELPERS);
    const page = await context.newPage();
    page.on('console', (message) => { if (message.type() === 'error') out.errors.push(page.url() + ' :: ' + message.text()); });
    page.on('pageerror', (error) => out.errors.push(page.url() + ' :: ' + String(error)));
    await page.goto(url);
    await page.waitForTimeout(SETTLE);
    return { context, page };
  }
  // A step records its measurement, or {failed: <first line of the error>}; later steps still run.
  async function step(record, name, body) {
    try { record[name] = await body(); }
    catch (error) { record[name] = { failed: String((error && error.message) || error).split('\n')[0] }; }
  }
  async function scene(name, url, body) {
    const record = {};
    out[name] = record;
    let context = null;
    try {
      const opened = await open(url);
      context = opened.context;
      await body(opened.page, record);
    } catch (error) {
      record.failed = String((error && error.message) || error).split('\n')[0];
    } finally {
      if (context) await context.close();
    }
  }
  const settle = (page) => page.waitForTimeout(SETTLE);
  const level = (page) => page.evaluate(() => __tc.level());
  const runRows = (page) => page.evaluate(() => __tc.runRows());
  const either = (container, attribute, value) =>
    `${container} [${attribute}="${value}"], ${container}[${attribute}="${value}"]`;

  // ── Dataset level ──
  await scene('dataset', spec.index, async (page, record) => {
    await step(record, 'summary', async () => {
      await page.waitForSelector('[data-tc-dataset-summary]', { state: 'attached', timeout: WAIT });
      return page.evaluate(() => {
        const band = document.querySelector('[data-tc-dataset-summary]');
        return { rect: __tc.rect(band), text: __tc.text(band) };
      });
    });
    await step(record, 'views', async () => page.evaluate(() =>
      __tc.all('[data-tc-targets-view] [data-view], [data-tc-targets-view][data-view]').map((button) => button.getAttribute('data-view'))));
    await step(record, 'cards', async () => {
      // NAVIGATION.md Part E (2026-11-23): the Dataset level is tabs and opens on the Overview; cards live in Targets.
      await page.click('[data-tc-dataset-tab="targets"]', { timeout: WAIT });
      await page.waitForSelector('[data-tc-target-card]', { state: 'attached', timeout: WAIT });
      return level(page);
    });
    await step(record, 'table', async () => {
      await page.click(either('[data-tc-targets-view]', 'data-view', 'table'), { timeout: WAIT });
      await settle(page);
      return level(page);
    });
    await step(record, 'table_after_reload', async () => {
      await page.waitForTimeout(BEFORE_RELOAD);
      await page.reload();
      await settle(page);
      return level(page);
    });
    await step(record, 'runs', async () => {
      await page.click('[data-tc-dataset-tab="runs"]', { timeout: WAIT });  // Part E: the runs table is its own tab
      await settle(page);
      return level(page);
    });
  });

  // ── Target level, opened from its card ──
  await scene('target', spec.index + '#/targets', async (page, record) => {
    const address = '#/target/' + spec.opened;
    await step(record, 'open', async () => {
      const card = page.locator(`[data-tc-target-card="${spec.opened}"]`);
      await card.waitFor({ state: 'visible', timeout: WAIT });
      await card.getByText(/open target/i).first().click({ timeout: WAIT });
      await page.waitForFunction((wanted) => location.hash === wanted, address, { timeout: WAIT }).catch(() => null);
      await settle(page);
      return level(page);
    });
    // WHY: the target-level checks must not all fail because the card's button did; reach the route by its address.
    if (!(await page.evaluate((wanted) => location.hash === wanted, address))) {
      record.reached_by_address = true;
      await page.goto(spec.index + address);
      await settle(page);
    }
    await step(record, 'rows', async () => {
      await page.waitForSelector('[data-tc-run-list] [data-tc-run]', { timeout: WAIT });
      return { level: await level(page), rows: await runRows(page) };
    });
    await step(record, 'back_forward', async () => {
      await page.evaluate(() => history.back());
      await page.waitForTimeout(700);
      const back = await level(page);
      await page.evaluate(() => history.forward());
      await page.waitForTimeout(700);
      return { back, forward: await level(page) };
    });
    if (!(await page.evaluate((wanted) => location.hash === wanted, address).catch(() => false))) {
      await page.goto(spec.index + address);
      await settle(page);
    }
    await step(record, 'verdict', async () => {
      await page.waitForSelector('[data-tc-verdict]', { state: 'attached', timeout: WAIT });
      return page.evaluate(() => {
        const card = document.querySelector('[data-tc-verdict]');
        return { visible: __tc.visible(card), text: __tc.text(card) };
      });
    });
    await step(record, 'tabs', async () => {
      await page.waitForSelector('[data-tc-target-tab]', { state: 'attached', timeout: WAIT });
      return { tabs: await page.evaluate(() => __tc.tabs()), panels: await page.evaluate(() => __tc.panels()) };
    });
    const mode = async (name) => {
      await page.click(either('[data-tc-repeats]', 'data-mode', name), { timeout: WAIT });
      await settle(page);
      return { draws: await page.evaluate(() => __tc.draws()) };
    };
    await step(record, 'draws_auto', async () => {
      await page.waitForSelector('[data-tc-draw]', { state: 'attached', timeout: WAIT });
      return { draws: await page.evaluate(() => __tc.draws()) };
    });
    await step(record, 'draws_lines', () => mode('lines'));
    await step(record, 'draws_bands', () => mode('bands'));
    await step(record, 'draws_auto_again', () => mode('auto'));
    await step(record, 'lines_n', async () => {
      const before = await page.evaluate(() => { const input = __tc.linesInput(); return input ? input.value : null; });
      if (before === null) throw new Error('no [data-tc-lines-n] input');
      const after = await page.evaluate((value) => {
        const input = __tc.linesInput();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, String(value));
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return input.value;
      }, spec.lines_n);
      await settle(page);
      return { before, after, draws: await page.evaluate(() => __tc.draws()) };
    });
    await step(record, 'filter', async () => {
      const box = page.locator(
        '[data-tc-run-list] input[type="search"], [data-tc-run-list] input[type="text"], [data-tc-run-list] input:not([type])'
      ).first();
      await box.fill(spec.filter, { timeout: WAIT });
      await settle(page);
      const filtered = await runRows(page);
      await box.fill('');
      await settle(page);
      return { filtered, cleared: await runRows(page) };
    });
    // config first, then date, then kind: each order the previous sort leaves cannot already satisfy the next check.
    for (const key of ['config', 'date', 'kind']) {
      await step(record, 'sort_' + key, async () => {
        const how = await page.evaluate((wanted) => {
          const select = document.querySelector('select[data-tc-sort], [data-tc-sort] select');
          if (select) {
            if (!Array.from(select.options).some((option) => option.value === wanted)) return 'no <option value="' + wanted + '">';
            select.value = wanted;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            return 'select';
          }
          const button = document.querySelector(`[data-tc-sort][data-sort="${wanted}"], [data-tc-sort] [data-sort="${wanted}"]`);
          if (button) { button.click(); return 'button'; }
          return 'no [data-tc-sort] control';
        }, key);
        if (how !== 'select' && how !== 'button') throw new Error(how);
        await settle(page);
        return { how, rows: await runRows(page) };
      });
    }
    await step(record, 'history', async () => {
      await page.click('[data-tc-target-tab][data-tab="history"]', { timeout: WAIT });
      await settle(page);
      return { panels: await page.evaluate(() => __tc.panels()) };
    });
    await step(record, 'sidebar', async () => {
      const before = await page.evaluate(() => __tc.listWidth());
      const handle = await page.evaluate(() => __tc.rect(document.querySelector('[data-tc-run-list-resize]')));
      if (!handle || !handle.width || !handle.height) {
        throw new Error('no visible [data-tc-run-list-resize] (run list width ' + before + ' px)');
      }
      const x = handle.x + handle.width / 2;
      const y = handle.y + Math.min(handle.height / 2, 300);
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x + spec.drag_px, y, { steps: 8 });
      await page.mouse.up();
      await settle(page);
      const dragged = await page.evaluate(() => __tc.listWidth());
      await page.waitForTimeout(BEFORE_RELOAD);
      await page.reload();
      await page.waitForSelector('[data-tc-run-list]', { timeout: WAIT });
      await settle(page);
      return { before, dragged, reloaded: await page.evaluate(() => __tc.listWidth()) };
    });
    await step(record, 'fold', async () => {
      const before = await page.evaluate(() => __tc.listWidth());
      await page.click('[data-tc-run-list-fold]', { timeout: WAIT });
      await settle(page);
      return { before, folded: await page.evaluate(() => __tc.listWidth()), rows: ((await runRows(page)) || []).length };
    });
  });

  // ── Target level, opened by its address ──
  await scene('deep_link', spec.index + '#/target/' + spec.deep_linked, async (page, record) => {
    await step(record, 'rows', async () => {
      await page.waitForSelector('[data-tc-run-list] [data-tc-run]', { timeout: WAIT });
      return { level: await level(page), rows: await runRows(page) };
    });
  });

  // ── Run level: the drill-down's breadcrumb back to its target ──
  await scene('report', spec.report, async (page, record) => {
    await page.waitForTimeout(1500);
    await step(record, 'breadcrumb', async () => {
      const found = await page.evaluate((href) => {
        const links = __tc.all('a[href]');
        const link = links.find((candidate) => candidate.getAttribute('href') === href);
        return {
          link: link ? { rect: __tc.rect(link), text: __tc.text(link) } : null,
          index_links: links.map((candidate) => candidate.getAttribute('href')).filter((value) => value.indexOf('index.html') !== -1).slice(0, 10),
        };
      }, spec.breadcrumb);
      if (!found.link) return found;
      await page.click(`a[href="${spec.breadcrumb}"]`, { timeout: WAIT });
      await page.waitForSelector('[data-tc-run-list]', { timeout: WAIT }).catch(() => null);
      await settle(page);
      return { ...found, after: { url: page.url(), level: await level(page) } };
    });
  });

  // ── How runs become targets when nothing names the target ──
  for (const variant of spec.grouping) {
    await scene('grouping_' + variant.name, variant.index + '#/targets', async (page, record) => {
      await step(record, 'cards', async () => {
        await page.waitForSelector('[data-tc-target-card]', { state: 'attached', timeout: WAIT });
        return level(page);
      });
      if (variant.open_title) {
        await step(record, 'opened', async () => {
          const card = page.locator('[data-tc-target-card]', { hasText: variant.open_title }).first();
          await card.getByText(/open target/i).first().click({ timeout: WAIT });
          await page.waitForSelector('[data-tc-run-list] [data-tc-run]', { timeout: WAIT });
          await settle(page);
          return { hash: await page.evaluate(() => location.hash), rows: await runRows(page) };
        });
      }
    });
  }

  console.log(JSON.stringify(out));
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
"""


@pytest.fixture(scope="module")
def levels(tmp_path_factory) -> dict:
    """Write the datasets, build one run's drill-down, and measure every page in one headless Chrome."""
    root = tmp_path_factory.mktemp("dataset_levels")
    write_dataset_report(RUNS, root / "levels", title="Dataset levels", group_by=(TARGET_TAG, CONFIG_TAG))
    report = build_drill_down(root / "levels", DRILLED_RUN)
    # The "target" tag wins over the first group_by tag (here ff_model, whose groups mix references).
    write_dataset_report(RUNS, root / "precedence", title="Target tag first", group_by=(CONFIG_TAG,))
    # No "target" tag: the first group_by tag names the target.
    write_dataset_report(retagged(RUNS, TARGET_TAG, "move"), root / "by_group", title="By group", group_by=("move", CONFIG_TAG))
    # No tags at all: runs sharing a reference are one target, titled by their first run's title.
    write_dataset_report(untagged(RUNS), root / "by_hash", title="By reference", group_by=())
    spec = {
        "index": (root / "levels" / "index.html").as_uri(),
        "opened": slug(OPENED),
        "deep_linked": slug(DEEP_LINKED),
        "report": report.as_uri(),
        "breadcrumb": f"../../index.html#/target/{slug(OPENED)}",
        "filter": FILTER,
        "lines_n": lines_up_to_n_above_every_group(),
        "drag_px": DRAG_PX,
        "grouping": [
            {"name": "precedence", "index": (root / "precedence" / "index.html").as_uri()},
            {"name": "by_group", "index": (root / "by_group" / "index.html").as_uri()},
            {"name": "by_hash", "index": (root / "by_hash" / "index.html").as_uri(), "open_title": TARGETS[OPENED].title},
        ],
    }
    (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "driver.js").write_text(DRIVER, encoding="utf-8")
    result = subprocess.run(
        ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(root / "spec.json")],
        capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    measured = json.loads(result.stdout.strip().splitlines()[-1])
    measured["run_slugs"] = {
        json.loads(path.read_text("utf-8"))["name"]: path.parent.name
        for path in (root / "levels" / "runs").glob("*/manifest.json")
    }
    return measured


def step(levels: dict, scene: str, name: str):
    """One step's measurement; a step that could not run fails here with what stopped it."""
    record = levels[scene]
    assert "failed" not in record, f"{scene}: the page did not open: {record['failed']}"
    value = record.get(name)
    assert value is not None, f"{scene}/{name}: not measured"
    assert not (isinstance(value, dict) and "failed" in value), f"{scene}/{name}: {value['failed']}"
    return value


def states(text: str, count: int, noun: str) -> bool:
    """``text`` states ``count`` of ``noun``: "3 targets", "targets: 3", "3 target"."""
    return bool(re.search(rf"(?<![\d.]){count}\s*{noun}|{noun}\w*\W{{0,3}}{count}(?![\d.])", text, re.I))


def contiguous(values: list) -> bool:
    """Every value appears in one unbroken run (rows grouped by it)."""
    seen: list = []
    for value in values:
        if seen and seen[-1] == value:
            continue
        if value in seen:
            return False
        seen.append(value)
    return True


def monotonic(values: list) -> bool:
    return values == sorted(values) or values == sorted(values, reverse=True)


def target_lines(target: str) -> list:
    return [line for line in LINES if line.target == target]


# ── Python: the model ────────────────────────────────────────────────────────


def test_target_by_and_config_by_are_keywords_of_write_dataset_report(tmp_path):
    index = write_dataset_report(
        RUNS, tmp_path, title="Explicit", group_by=(TARGET_TAG, CONFIG_TAG), target_by=TARGET_TAG, config_by=CONFIG_TAG
    )
    assert index == tmp_path / "index.html" and index.is_file()


@pytest.mark.parametrize("tag", [TARGET_TAG, "move"])
def test_a_target_by_value_holding_two_references_raises_naming_both_runs(tmp_path, tag):
    slow = next(run for run in RUNS if run.tags[TARGET_TAG] == "full-circle-slow")
    fast = next(run for run in RUNS if run.tags[TARGET_TAG] == "full-circle-fast")
    runs = retagged([slow, fast], TARGET_TAG, tag)
    runs[1].tags = {**runs[1].tags, tag: "full-circle-slow"}  # a different trajectory claiming the slow probe's key
    with pytest.raises(ValueError) as error:
        write_dataset_report(runs, tmp_path, title="Mixed", group_by=(tag, CONFIG_TAG), target_by=tag)
    assert slow.name in str(error.value) and fast.name in str(error.value), str(error.value)


# ── Dataset level ────────────────────────────────────────────────────────────


@needs_browser
def test_index_opens_on_the_dataset_level_with_a_summary_band_stating_targets_and_lines(levels):
    summary = step(levels, "dataset", "summary")
    assert summary["rect"]["width"] > 0 and summary["rect"]["height"] > 0, summary["rect"]
    assert states(summary["text"], len(TARGETS), "target"), summary["text"]
    assert states(summary["text"], len(LINES), "line"), summary["text"]


@needs_browser
def test_the_summary_band_splits_lines_by_kind_and_names_configs_dates_and_wins(levels):
    text = step(levels, "dataset", "summary")["text"]
    kinds = Counter(line.kind for line in LINES)
    assert states(text, kinds["sim"], "sim") and states(text, kinds["real"], "real"), text
    assert states(text, 2, "config"), text
    assert BASELINE in text and CALIBRATED in text, text
    assert FIRST_DAY[5:] in text and SECOND_DAY[5:] in text, f"date range {FIRST_DAY} … {SECOND_DAY} not in: {text}"
    # v2 calibrated beats the baseline (v1, the first config) on the two full-circle probes, not on the pick swing
    assert re.search(r"\b2\s*(?:of|/)\s*3\b", text), text


@needs_browser
def test_targets_default_to_one_card_per_target_each_with_open_target(levels):
    assert set(step(levels, "dataset", "views")) == {"cards", "table"}  # Part E: runs is its own tab
    level = step(levels, "dataset", "cards")
    assert sorted(card["slug"] for card in level["cards"]) == sorted(slug(key) for key in TARGETS), level["cards"]
    for card in level["cards"]:
        target = next(target for target in TARGETS.values() if slug(target.key) == card["slug"])
        assert target.key in card["text"] or target.title in card["text"], card
        assert card["open"] == 1, f"{card['slug']}: {card['open']} visible Open target controls"
    assert level["target_rows"] == [] and level["runs_table_rows"] == 0, "the cards view shows only cards"
    assert level["summary"] and not level["run_list"], "index.html opens on the Dataset level"


@needs_browser
def test_the_table_view_has_one_row_per_target_and_config_and_survives_a_reload(levels):
    expected = Counter(slug(key) for key, config in {(line.target, line.config) for line in LINES})
    table = step(levels, "dataset", "table")
    assert Counter(table["target_rows"]) == expected, table["target_rows"]
    assert table["cards"] == [], "the table view hides the cards"
    reloaded = step(levels, "dataset", "table_after_reload")
    assert Counter(reloaded["target_rows"]) == expected and reloaded["cards"] == [], "the view choice did not survive a reload"


@needs_browser
def test_the_runs_view_is_todays_runs_by_pairs_table(levels):
    pairs = sum(len(default_pairs(list(run.measured))) for run in RUNS)
    runs = step(levels, "dataset", "runs")
    assert runs["runs_table_rows"] == pairs, f"{runs['runs_table_rows']} visible rows, want one per run x pair ({pairs})"
    assert runs["open_run_links"] == pairs
    assert runs["cards"] == [] and runs["target_rows"] == []


# ── Target level ─────────────────────────────────────────────────────────────


@needs_browser
def test_open_target_routes_to_the_target_and_lists_exactly_its_lines(levels):
    opened = step(levels, "target", "open")
    assert opened["hash"] == f"#/target/{slug(OPENED)}", opened["hash"]
    shown = step(levels, "target", "rows")
    assert shown["level"]["run_list"] and not shown["level"]["summary"] and shown["level"]["cards"] == []
    rows = {row["line"]: row for row in shown["rows"]}
    assert len(rows) == len(shown["rows"]), "a line is listed twice"
    assert sorted(rows) == sorted(line.id for line in target_lines(OPENED))
    for line in target_lines(OPENED):
        row = rows[line.id]
        assert (row["config"], row["kind"], row["date"]) == (line.config, line.kind, line.date), row


@needs_browser
def test_a_line_id_is_run_name_dot_series_and_its_kind_follows_the_series_name(levels):
    shown = step(levels, "deep_link", "rows")
    assert shown["level"]["hash"] == f"#/target/{slug(DEEP_LINKED)}" and shown["level"]["run_list"]
    kinds = {row["line"]: row["kind"] for row in shown["rows"]}
    expected = {f"{run.name} · {series}": kind_of(series) for run in RUNS if run.tags[TARGET_TAG] == DEEP_LINKED for series in run.measured}
    assert kinds == expected
    assert kinds["fast v1 rep 1 · twin_it5"] == "sim" and kinds["fast v1 rep 1 · real_retake"] == "real"


@needs_browser
def test_each_lines_arrow_opens_its_run_report(levels):
    rows = step(levels, "target", "rows")["rows"]
    assert rows and all(isinstance(row["line"], str) for row in rows), rows
    for row in rows:
        run_slug = levels["run_slugs"][row["line"].rsplit(" · ", 1)[0]]
        wanted = re.compile(rf"(^|/)runs/{re.escape(run_slug)}/report\.html(#.*)?$")
        assert any(wanted.search(href) for href in row["hrefs"]), row


@needs_browser
def test_back_returns_to_the_dataset_level_and_forward_to_the_target(levels):
    moved = step(levels, "target", "back_forward")
    back, forward = moved["back"], moved["forward"]
    # Part E: the card was opened from the Targets tab, so back returns there (the band lives on the Overview tab)
    assert back["hash"] in ("", "#", "#/", "#/targets") and (back["summary"] or back["cards"]) and not back["run_list"], back
    assert forward["hash"] == f"#/target/{slug(OPENED)}" and forward["run_list"] and not forward["summary"], forward


@needs_browser
def test_the_verdict_names_the_config_that_tracks_this_target_better(levels):
    verdict = step(levels, "target", "verdict")
    assert verdict["visible"] and CALIBRATED in verdict["text"], verdict


@needs_browser
def test_two_question_tabs_with_repeat_open_by_default(levels):
    shown = step(levels, "target", "tabs")
    tabs = {tab["tab"]: tab for tab in shown["tabs"]}
    assert set(tabs) == {"repeat", "history"}
    assert "How repeatable is each config on this target?" in tabs["repeat"]["text"], tabs["repeat"]
    assert "Has tracking improved across configs over time?" in tabs["history"]["text"], tabs["history"]
    panels = shown["panels"]
    assert panels.get("repeat", {}).get("visible") and not panels.get("history", {}).get("visible"), panels


@needs_browser
def test_the_history_tab_shows_the_control_chart(levels):
    panels = step(levels, "target", "history")["panels"]
    history = panels.get("history", {})
    assert history.get("visible") and history.get("chart_area", 0) > 100 * 50, panels
    assert not panels.get("repeat", {}).get("visible"), panels


def draws_of(measured: dict) -> dict[str, set[str]]:
    by_config: dict[str, set[str]] = {}
    for draw in measured["draws"]:
        by_config.setdefault(draw["config"], set()).add(draw["draw"])
    return by_config


@needs_browser
def test_auto_repeats_draw_a_fan_past_n_lines_and_lines_up_to_n(levels):
    groups = Counter(line.config for line in target_lines(OPENED))
    assert groups[BASELINE] > 5 >= groups[CALIBRATED]  # the fixture's premise
    for name in ("draws_auto", "draws_auto_again"):
        draws = draws_of(step(levels, "target", name))
        assert draws.get(BASELINE) == {"bands"}, f"{name}: {draws}"
        assert draws.get(CALIBRATED) == {"lines"}, f"{name}: {draws}"


@needs_browser
def test_repeats_lines_and_bands_modes_force_their_drawing(levels):
    for mode, drawing in (("lines", "lines"), ("bands", "bands")):
        draws = draws_of(step(levels, "target", f"draws_{mode}"))
        assert draws.get(BASELINE) == {drawing} and draws.get(CALIBRATED) == {drawing}, f"mode {mode}: {draws}"


@needs_browser
def test_raising_lines_up_to_n_above_the_group_size_draws_lines(levels):
    moved = step(levels, "target", "lines_n")
    assert moved["before"] == "5", "lines up to N starts at 5"
    assert moved["after"] == str(lines_up_to_n_above_every_group()), moved
    draws = draws_of(moved)
    assert draws.get(BASELINE) == {"lines"} and draws.get(CALIBRATED) == {"lines"}, draws


@needs_browser
def test_the_regex_filter_narrows_the_run_list(levels):
    filtered = step(levels, "target", "filter")
    wanted = sorted(line.id for line in target_lines(OPENED) if re.search(FILTER, line.id))
    assert 0 < len(wanted) < len(target_lines(OPENED))
    assert sorted(row["line"] for row in filtered["filtered"]) == wanted
    assert len(filtered["cleared"]) == len(target_lines(OPENED)), "clearing the filter lists every line again"


@needs_browser
def test_sorting_by_config_date_and_kind_reorders_the_run_list(levels):
    every = sorted(line.id for line in target_lines(OPENED))
    for key, holds in (("config", contiguous), ("date", monotonic), ("kind", contiguous)):
        rows = step(levels, "target", f"sort_{key}")["rows"]
        assert sorted(row["line"] for row in rows) == every, f"sort by {key} changed which lines are listed"
        order = [row[key] for row in rows]
        assert None not in order and holds(order), f"sort by {key}: {order}"


@needs_browser
def test_the_run_list_edge_drags_its_width_survives_a_reload_and_it_folds(levels):
    sidebar = step(levels, "target", "sidebar")
    assert sidebar["before"] and sidebar["before"] > 100, sidebar
    assert abs(sidebar["dragged"] - sidebar["before"] - DRAG_PX) <= 30, sidebar
    assert abs(sidebar["reloaded"] - sidebar["dragged"]) <= 4, sidebar
    fold = step(levels, "target", "fold")
    assert fold["folded"] is None or fold["folded"] < 60 or fold["rows"] == 0, fold


# ── Run level ────────────────────────────────────────────────────────────────


@needs_browser
def test_a_run_reports_breadcrumb_links_back_to_its_target(levels):
    crumb = step(levels, "report", "breadcrumb")
    assert crumb["link"], f"no <a href='../../index.html#/target/{slug(OPENED)}'>; links to index.html: {crumb['index_links']}"
    assert crumb["link"]["rect"]["width"] > 0 and crumb["link"]["rect"]["height"] > 0, crumb["link"]
    after = crumb["after"]
    assert after["url"].endswith(f"/levels/index.html#/target/{slug(OPENED)}"), after["url"]
    assert after["level"]["run_list"], "following the breadcrumb lands on the target level"


# ── How runs become targets ──────────────────────────────────────────────────


@needs_browser
def test_the_target_tag_names_the_target_before_the_first_group_by_tag(levels):
    cards = step(levels, "grouping_precedence", "cards")["cards"]
    assert sorted(card["slug"] for card in cards) == sorted(slug(key) for key in TARGETS), cards


@needs_browser
def test_without_a_target_tag_the_first_group_by_tag_names_the_target(levels):
    cards = step(levels, "grouping_by_group", "cards")["cards"]
    assert sorted(card["slug"] for card in cards) == sorted(slug(key) for key in TARGETS), cards


@needs_browser
def test_without_tags_runs_sharing_a_reference_are_one_target_titled_by_their_first_run(levels):
    cards = step(levels, "grouping_by_hash", "cards")["cards"]
    assert len(cards) == len(TARGETS), cards
    for target in TARGETS.values():
        assert sum(target.title in card["text"] for card in cards) == 1, f"{target.title}: {cards}"
    opened = step(levels, "grouping_by_hash", "opened")
    assert all(isinstance(row["line"], str) for row in opened["rows"]), opened["rows"]
    assert sorted(row["line"] for row in opened["rows"]) == sorted(line.id for line in target_lines(OPENED))
    # no second group_by tag: a line's config is its series name
    assert all(row["config"] == row["line"].rsplit(" · ", 1)[1] for row in opened["rows"]), opened["rows"]


@needs_browser
def test_no_console_errors_on_any_level(levels):
    assert levels["errors"] == []
