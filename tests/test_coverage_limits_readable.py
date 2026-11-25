"""The joint-limits histogram reads at a glance: no redundant limit lines on the normalized axis, and every mark and key
swatch clearly visible, light and dark (acceptance for Vibe Tracks feedback fb-509a6fe5 and fb-7a2772f9, 2026-11-23,
track robot-viz-agent).

Zach, Daily Note 2026-11-23, on the coverage page's "How much of its limits does each joint use?" ridgeline:

- fb-509a6fe5: "When ornamlized seems redudant to put the join limit bars as its always plus minud 100?"
- fb-7a2772f9: "and then the legend and labeling I don't know if it could be made more clear. right now like the colors
  are hard for me to see..."

The graph is drawn three ways: data-ui's stock ``coverage-hist`` in the coverage workbench (its Overview ridgeline and
the multiples on Limits, One joint and Tool position, walked from the written .base, so a hist view added later is held
too), traj_compare's own coverage page (``write_coverage_page``: its Overview ridgeline and its Limits cards), and the
Matplotlib viewer's ridgeline.png and limit-bars.png (the last test). The first two are built here from the made-up arm
of test_coverage_workbench.py and measured in headless Chrome, light and dark, from screenshots of what a reader
actually sees (canvas and CSS composited), never from DOM presence or CSS rules.

fb-509a6fe5, on every normalized (±100 % of the limit) axis:
- no limit line: no vertical run of limit-coloured pixels anywhere in the figure;
- samples past a limit still read as past it: every bin wholly past a limit with a count draws in the limit colour, and
  nothing inside ±100 % does (the oracle is the rows' own counts and edges, read here);
- "±100 % = the limit" is said once, in the key, and the key has no limit-line swatch any more;
- the actual-units multiples keep their limit lines (there they are information), measured below.

fb-7a2772f9, the measurable rule (WCAG 2.1 SC 1.4.11 non-text contrast, the dataviz skill's "contrast vs surface"):
- every mark a reader must see (bars, the limit line, the planner's limit, caps, the beyond-the-limit band, the picked
  row, the percentile ticks and hairline) has contrast >= 3:1 against the surface it sits on (the page, the zebra
  band, the picked tint), read off the composited pixels;
- a line mark is >= 1.5 CSS px wide, measured as the ink integrated across it (a 1.4 px line measures 1.4);
- every key swatch is >= 3:1 against the key's background, >= 12 px along and >= 2 px across;
- a key names only what is drawn (the limit, the planner's limit, the band, the ticks, past-the-limit, the picked row).
The group colours of stacked bars are exempt from the 3:1 gate: they are the host's categorical palette, one colour per
dataset in every view (data-ui CONTRACT §52), and the dataviz relief rule applies (each is named in the group legend
and the hover reads every group's count); their contrast is the palette's to fix, across data-ui, not this figure's.

    TRAJ_COMPARE_REQUIRE_BROWSER=1 uv run --extra test --extra rerun --extra export python -m pytest -q tests/test_coverage_limits_readable.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from test_coverage_workbench import CHROME, PLANNER, PLAYWRIGHT, made_up, needs_browser

from traj_compare.coverage import analyze
from traj_compare.coverage import workbench as workbench_module
from traj_compare.coverage.page import write_coverage_page
from traj_compare.coverage.workbench import write_workbench

# WHY a switch: CI (no Chrome, no data-ui) skips the browser tests, but a skipped spec passes a check without proving
# anything, so whoever claims this spec runs it with TRAJ_COMPARE_REQUIRE_BROWSER=1 and a missing tool fails instead
pytestmark = [] if os.environ.get("TRAJ_COMPARE_REQUIRE_BROWSER") == "1" else [needs_browser]

CONTRAST = 3.0  # WCAG 2.1 SC 1.4.11: graphical objects >= 3:1 against adjacent colours
LINE = 1.5  # CSS px, the thinnest a line mark may be
SWATCH_LONG, SWATCH_SHORT = 12, 2  # CSS px, a key swatch's ink: along and across
BAND_INK = 0.15  # the beyond-the-limit band: at least this share of its pixels are ink
LIMIT_TOL = 40  # a pixel is "limit-coloured" when every channel is within this of the limit colour
LINE_RUN = 20  # px: a vertical run of limit colour this tall on a normalized axis is a limit line
SCHEMES = ("light", "dark")
SURFACES = ("workbench", "page")

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
// what the reader sees: an element's screenshot, decoded back to RGB in the page (no image library in this env)
async function pixels(page, handle, file) {
  const png = await handle.screenshot({ path: file, animations: 'disabled' });
  return page.evaluate(async (b64) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    const rgb = new Uint8Array(c.width * c.height * 3);
    for (let i = 0, j = 0; i < d.length; i += 4, j += 3) { rgb[j] = d[i]; rgb[j + 1] = d[i + 1]; rgb[j + 2] = d[i + 2]; }
    let s = ''; for (let i = 0; i < rgb.length; i += 0x8000) s += String.fromCharCode.apply(null, rgb.subarray(i, i + 0x8000));
    return { w: c.width, h: c.height, rgb: btoa(s) };
  }, png.toString('base64'));
}
// every key item: its mark, its words, its swatch's colour and box inside the item, the item as seen
async function keyItems(page, items, file) {
  const out = [];
  for (let k = 0; k < items.length; k++) {
    const info = await items[k].evaluate((li) => {
      const sw = li.querySelector('i'); const r = li.getBoundingClientRect(); const s = sw && sw.getBoundingClientRect();
      const cs = sw && getComputedStyle(sw);
      return { mark: li.dataset.mark || (sw ? (sw.className.match(/(?:sw-|cov-sw )([\w-]+)/) || [])[1] : 'text') || 'text',
        group: li.hasAttribute('data-group') || !!li.closest('.dv-coverage-groups'), label: li.textContent.trim(),
        colour: cs ? (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' ? cs.backgroundColor : cs.borderTopColor) : null,
        swatch: s ? { x: s.left - r.left, y: s.top - r.top, w: s.width, h: s.height } : null };
    });
    if (info.swatch && !info.group) info.image = await pixels(page, items[k], `${file}-${k}.png`);
    out.push(info);
  }
  return out;
}
const TOKEN = (name) => { const el = document.querySelector('data-workbench .dv-view') || document.body;
  const c = document.createElement('canvas'); c.width = c.height = 1; const g = c.getContext('2d');
  g.fillStyle = '#000'; g.fillStyle = getComputedStyle(el).getPropertyValue(name).trim() || '#000'; g.fillRect(0, 0, 1, 1);
  return [...g.getImageData(0, 0, 1, 1).data].slice(0, 3); };
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  const out = { errors: [], workbench: {}, page: {} };
  for (const scheme of spec.schemes) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(`${scheme}: ${e}`));
    // WHY favicon.ico aside: the coverage page has no icon, so Chrome asks for one and logs the server's 404
    page.on('console', (m) => { if (m.type() === 'error' && !String((m.location() || {}).url).endsWith('/favicon.ico')) out.errors.push(`${scheme}: ${m.text()} ${(m.location() || {}).url || ''}`); });
    // ── the workbench: every coverage-hist view on every tab ──
    await page.goto(spec.workbench);
    await page.waitForSelector('data-workbench[data-ready]', { timeout: 30000 });
    await page.waitForTimeout(800);
    const tokens = {};
    for (const name of ['--dv-limit', '--dv-fg', '--dv-bg', '--dv-series-1', '--dv-accent']) tokens[name] = await page.evaluate(TOKEN, name);
    const figures = [];
    const tabs = await page.evaluate(() => [...document.querySelectorAll('data-workbench data-tabs [role=tab]')].map((t) => t.dataset.tab));
    for (const tab of tabs) {
      await page.click(`data-workbench data-tabs [role=tab][data-tab="${tab}"]`);
      try {
        await page.waitForFunction((tab) => {
          const shown = [...document.querySelectorAll('data-workbench [tab]')].find((p) => p.getAttribute('tab') === tab);
          return shown && !shown.hidden && [...shown.querySelectorAll('data-views')].every((e) => !(e.view && e.view.type === 'coverage-hist')
            || (e.querySelector('.dv-view') && e.querySelector('.dv-view').coverage && e.querySelector('.dv-view').coverage.drawn > 0));
        }, tab, { timeout: 15000 });
      } catch (e) { out.errors.push(`${scheme} · ${tab}: a histogram never drew`); }
      await page.waitForTimeout(400);
      const views = await page.$$(`data-workbench [tab="${tab}"] data-views`);
      for (const view of views) {
        const meta = await view.evaluate((e) => ({ name: e.view && e.view.name, type: e.view && e.view.type,
          layout: (e.view && e.view.coverage && e.view.coverage.layout) || 'multiples' }));
        if (meta.type !== 'coverage-hist') continue;
        const hook = await view.evaluate((e) => { const h = e.querySelector('.dv-view').coverage;
          return h.panels.map((p) => ({ id: p.id, box: p.box, lines: p.lines || null, columns: p.columns || null, strips: p.strips || null })); });
        const canvases = await view.$$('.dv-view canvas.dv-coverage-heat');
        const panels = [];
        for (let k = 0; k < hook.length; k++) {
          const file = `${spec.out}/${scheme}-${tab}-${meta.name}-${k}`.replace(/[^\w/.-]+/g, '_');
          panels.push({ ...hook[k], image: await pixels(page, canvases[k], `${file}.png`) });
        }
        const file = `${spec.out}/${scheme}-${tab}-${meta.name}-key`.replace(/[^\w/.-]+/g, '_');
        const key = await keyItems(page, await view.$$('.dv-coverage-key .dv-coverage-li, .dv-coverage-groups .dv-coverage-key-btn'), file);
        const keyText = await view.evaluate((e) => [...e.querySelectorAll('.dv-coverage-key')].map((k) => k.textContent).join(' '));
        figures.push({ tab, ...meta, panels, key, keyText });
      }
    }
    out.workbench[scheme] = { tokens, figures };
    // ── the hand-rolled page: its Overview ridgeline and its Limits cards ──
    await page.goto(spec.page);
    await page.waitForSelector('[data-cov-figure="ridgeline"] canvas', { timeout: 30000 });
    await page.waitForTimeout(500);
    const colours = await page.evaluate(() => ({ limit: window.CoverageColor && window.CoverageColor.LIMIT }));
    const figure = async (id, tab) => {
      if (tab) { await page.click(`[data-cov-tab="${tab}"]`); await page.waitForSelector(`[data-cov-figure="${id}"] canvas`, { timeout: 15000 }); await page.waitForTimeout(400); }
      const node = await page.$(`[data-cov-figure="${id}"]`);
      const canvases = await node.$$('.cov-figbody canvas');
      const panels = [];
      for (let k = 0; k < canvases.length; k++) {
        const geometry = await canvases[k].evaluate((c) => ({
          ridge: c._ridge || null,
          strips: (c._rows || []).map((r) => ({ signal: r.signal, box: r.box, lo: r.e.lo, hi: r.e.hi, scale: r.scale })),
          joint: (c.closest('.cov-card') && c.closest('.cov-card').querySelector('.cov-cardhead b') || {}).textContent || null }));
        panels.push({ ...geometry, image: await pixels(page, canvases[k], `${spec.out}/${scheme}-page-${id}-${k}.png`) });
      }
      const key = await keyItems(page, await node.$$('.cov-legend .cov-li'), `${spec.out}/${scheme}-page-${id}-key`);
      const keyText = await node.evaluate((n) => n.querySelector('.cov-legend').textContent);
      return { panels, key, keyText };
    };
    out.page[scheme] = { colours, ridgeline: await figure('ridgeline', null), limits: await figure('limit-bars', 'limits') };
    await context.close();
  }
  await browser.close();
  fs.writeFileSync(spec.out + '/measured.json', JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


# ── the site and the measurement ────────────────────────────────────────────


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict:
    """The workbench (data-ui main, vendored by write_workbench) and the hand-rolled page, side by side in one folder."""
    joints, tools, tags = made_up()
    reachable = np.random.default_rng(7).uniform([0.1, -0.35, 0.1], [0.7, 0.35, 0.5], size=(400, 3))
    coverage = analyze(joints, tool=tools, tags=tags, group_by="dataset", planner_limits=PLANNER,
                       reachable=reachable, title="Made-up arm")
    out = tmp_path_factory.mktemp("limits-readable")
    write_workbench(coverage, joints, out, tool=tools, title="Made-up arm")
    write_coverage_page(coverage.payload, out / "coverage.html")
    return {"site": out, "payload": coverage.payload,
            "parts": json.loads((out / "parts.json").read_text("utf-8"))["rows"]}


@pytest.fixture(scope="module")
def measured(built) -> dict:
    """Serve the folder with traj_compare.serve on a free port (its pid recorded, that pid stopped) and measure."""
    site = built["site"]
    shots = site / "shots"
    shots.mkdir(exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(site), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        url = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/")
        url = url.rsplit("/", 1)[0] if url.endswith(".html") else url
        (site / "spec.json").write_text(json.dumps({"workbench": f"{url}/index.html", "page": f"{url}/coverage.html",
                                                    "schemes": SCHEMES, "out": str(shots)}))
        (site / "driver.js").write_text(DRIVER)
        result = subprocess.run(["node", str(site / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(site / "spec.json")],
                                capture_output=True, text=True, timeout=600)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode != 0 or not (shots / "measured.json").is_file():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    return json.loads((shots / "measured.json").read_text("utf-8"))


# ── colour and ink, measured ────────────────────────────────────────────────


def image(capture: dict) -> np.ndarray:
    return np.frombuffer(base64.b64decode(capture["rgb"]), dtype=np.uint8).reshape(capture["h"], capture["w"], 3).astype(int)


def luminance(rgb) -> float:
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def css_rgb(text: str | None) -> list[int] | None:
    if not text:
        return None
    if text.startswith("#"):
        return [int(text[i:i + 2], 16) for i in (1, 3, 5)]
    if text.startswith("color(srgb"):
        return [round(float(v) * 255) for v in text[len("color(srgb"):].strip(" )").split()[:3]]
    return [round(float(v)) for v in text[text.index("(") + 1:].replace(",", " ").replace(")", " ").replace("/", " ").split()[:3]]


def mode(pixels: np.ndarray) -> np.ndarray:
    flat = pixels.reshape(-1, 3)
    colours, counts = np.unique(flat, axis=0, return_counts=True)
    return colours[counts.argmax()]


def deviation(pixels: np.ndarray, surface) -> np.ndarray:
    return np.abs(pixels - np.asarray(surface)).max(axis=-1)


def near(pixels: np.ndarray, colour, tol: int = LIMIT_TOL) -> np.ndarray:
    return np.abs(pixels - np.asarray(colour)).max(axis=-1) <= tol


def across(profile: np.ndarray, surface, centre: int, reach: int = 2) -> tuple[float, float]:
    """(width in px, contrast of its strongest pixel) of a line crossing this 1-D profile near `centre`: the ink
    integrated across it, each pixel's coverage its deviation from the surface over the strongest pixel's."""
    dev = deviation(profile, surface).astype(float)
    lo, hi = max(0, centre - reach), min(len(dev), centre + reach + 1)
    if hi <= lo or dev[lo:hi].max() <= 0:
        return 0.0, 1.0
    peak = lo + int(dev[lo:hi].argmax())
    cover = dev / dev[peak]
    width, k = cover[peak], peak - 1
    while k >= 0 and k >= peak - 5 and cover[k] > 0.06:
        width, k = width + min(1.0, cover[k]), k - 1
    k = peak + 1
    while k < len(cover) and k <= peak + 5 and cover[k] > 0.06:
        width, k = width + min(1.0, cover[k]), k + 1
    return float(width), contrast(profile[peak], surface)


# ── the oracle: the rows' own counts, edges and limits ──────────────────────


def summed(parts: list[dict], grid: str) -> dict:
    """The workbench's figure for one grid: its parts' shared edges and limits, their counts added up."""
    rows = [p for p in parts if p.get("kind") in ("hist", "tool_speed") and p.get("grid") == grid]
    assert rows, f"no part rows for {grid}"
    first = dict(rows[0])
    first["counts"] = list(np.sum([r["counts"] for r in rows], axis=0))
    first["stated"] = (isinstance(first.get("low"), (int, float)) and isinstance(first.get("high"), (int, float))
                       and first.get("limit_source") in (None, "limit"))
    return first


def page_hist(payload: dict, joint: str, signal: str) -> dict:
    """The page's figure for one joint and signal, in the same shape."""
    h = payload["hist"][joint][signal]
    lo, hi, bins = h["edges"]
    limit = payload["limits"][joint][signal]
    planner = ((payload.get("planner_limits") or {}).get(joint) or {}).get(signal) or {}
    scale = next(j for j in payload["joints"] if j["name"] == joint)["display"]["scale"]
    return {"lo": lo, "hi": hi, "bins": bins, "counts": h["counts"], "low": limit["low"], "high": limit["high"],
            "stated": limit["source"] == "limit", "planner_low": planner.get("low") if planner.get("source") == "limit" else None,
            "planner_high": planner.get("high") if planner.get("source") == "limit" else None,
            "p001": h.get("p001"), "p999": h.get("p999"), "scale": scale}


def beyond_bins(row: dict) -> list[tuple[float, float]]:
    """(from, to) value edges of every bin wholly past the limit that holds a sample."""
    if not row["stated"]:
        return []
    step = (row["hi"] - row["lo"]) / row["bins"]
    out = []
    for i, n in enumerate(row["counts"]):
        a, b = row["lo"] + i * step, row["lo"] + (i + 1) * step
        if n > 0 and (b <= row["low"] or a >= row["high"]):
            out.append((a, b))
    return out


def clipped_bins(counts: list) -> list[int]:
    """The bins the linear scale clips (count above the p98 of the non-zero counts, never below the least): capped."""
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return []
    at = (len(nz) - 1) * 0.98
    lo = int(np.floor(at))
    top = max(nz[lo] + (nz[min(len(nz) - 1, lo + 1)] - nz[lo]) * (at - lo), nz[0])
    return [i for i, c in enumerate(counts) if c > top]


def pct(row: dict, v: float) -> float:
    return (2 * (v - row["low"]) / (row["high"] - row["low"]) - 1) * 100


# ── the figures, gathered per surface ───────────────────────────────────────


def ridgelines(measured: dict, built: dict, surface: str, scheme: str) -> list[dict]:
    """[{image, columns, lines, cells: {(line, signal): row}, key, keyText, limit}] for every normalized figure."""
    out = []
    if surface == "workbench":
        m = measured["workbench"][scheme]
        for f in m["figures"]:
            if f["layout"] != "ridgeline":
                continue
            p = f["panels"][0]
            cells = {(line["id"], s): summed(built["parts"], f"{line['id']}.{s}") for line in p["lines"] or [] for s in line["signals"]}
            out.append({"name": f"{f['tab']} · {f['name']}", "image": image(p["image"]), "columns": p["columns"],
                        "lines": p["lines"], "cells": cells, "key": f["key"], "keyText": f["keyText"],
                        "limit": m["tokens"]["--dv-limit"]})
    else:
        m = measured["page"][scheme]
        f = m["ridgeline"]
        p = f["panels"][0]
        ridge = p["ridge"] or {}
        # the page's ridgeline: every joint, position / speed / acceleration (its fixed three columns)
        cells = {(joint["name"], signal): page_hist(built["payload"], joint["name"], signal)
                 for joint in built["payload"]["joints"] for signal in ("q", "qd", "qdd")}
        out.append({"name": "coverage page · ridgeline", "image": image(p["image"]), "columns": ridge.get("columns"),
                    "lines": ridge.get("lines"), "cells": cells, "key": f["key"], "keyText": f["keyText"],
                    "limit": css_rgb(m["colours"]["limit"])})
    assert out, f"{surface}, {scheme}: no normalized figure was measured, so this would prove nothing"
    return out


def multiples(measured: dict, built: dict, surface: str, scheme: str) -> list[dict]:
    """[{name, image, strips: [{id, box, row}], key, keyText}] for every actual-units figure (a card is one image)."""
    out = []
    if surface == "workbench":
        for f in measured["workbench"][scheme]["figures"]:
            if f["layout"] == "ridgeline":
                continue
            for p in f["panels"]:
                strips = [{"id": s["id"], "box": s["box"], "row": summed(built["parts"], s["id"].removeprefix("sum:"))}
                          for s in p["strips"] or []]
                out.append({"name": f"{f['tab']} · {f['name']} · {p['id']}", "image": image(p["image"]), "strips": strips,
                            "key": f["key"], "keyText": f["keyText"]})
    else:
        f = measured["page"][scheme]["limits"]
        for p in f["panels"]:
            strips = [{"id": f"{p['joint']}.{s['signal']}", "box": s["box"], "row": page_hist(built["payload"], p["joint"], s["signal"])}
                      for s in p["strips"]]
            out.append({"name": f"coverage page · limits · {p['joint']}", "image": image(p["image"]), "strips": strips,
                        "key": f["key"], "keyText": f["keyText"]})
    assert out and all(fig["strips"] for fig in out), f"{surface}, {scheme}: an actual-units figure has no strips to measure"
    return out


def column_x(column: dict, p: float) -> float:
    return column["x"] + (p - column["lo"]) / (column["hi"] - column["lo"]) * column["w"]


def strip_x(strip: dict, v: float) -> float:
    row, box = strip["row"], strip["box"]
    return box["x"] + (v - row["lo"]) / (row["hi"] - row["lo"]) * box["w"]


def row_surface(img: np.ndarray, line: dict) -> np.ndarray:
    return mode(img[int(line["y"]) + 1:int(line["y"] + line["h"]) - 1, :, :])


def strip_surface(img: np.ndarray, strip: dict) -> np.ndarray:
    box = strip["box"]
    return mode(img[int(box["y"]) - 1, int(box["x"]):int(box["x"] + box["w"]), :][None])


def line_width(img: np.ndarray, y: int, x: float, surface) -> tuple[float, float]:
    xi = int(np.floor(x))
    lo = max(0, xi - 6)
    return across(img[y, lo:xi + 7, :], surface, xi - lo)


CASES = [(surface, scheme) for surface in SURFACES for scheme in SCHEMES]


# ── the spec ────────────────────────────────────────────────────────────────


def test_the_driver_measured_both_surfaces_in_both_schemes_with_no_errors(measured):
    assert measured["errors"] == []
    for scheme in SCHEMES:
        layouts = sorted({f["layout"] for f in measured["workbench"][scheme]["figures"]})
        assert layouts == ["multiples", "ridgeline"], (scheme, layouts)
        assert measured["page"][scheme]["ridgeline"]["panels"] and measured["page"][scheme]["limits"]["panels"], scheme


@pytest.mark.parametrize("surface,scheme", CASES)
def test_no_limit_line_on_the_normalized_axis(measured, built, surface, scheme):
    """fb-509a6fe5: on a ±100 %-of-the-limit axis the limit is always at ±100 %, so no line marks it, and the key says
    "±100 % = the limit" once instead of naming a limit line."""
    wrong = {}
    for fig in ridgelines(measured, built, surface, scheme):
        red = near(fig["image"], fig["limit"])
        runs, best = red[0].astype(int), red[0].astype(int)
        for y in range(1, red.shape[0]):
            runs = np.where(red[y], runs + 1, 0)
            best = np.maximum(best, runs)
        lines = [int(x) for x in np.flatnonzero(best >= LINE_RUN)]
        line_items = [k["label"] for k in fig["key"] if k["mark"] in ("line", "dash", "thin") and "limit" in k["label"]]
        said = fig["keyText"].replace(" ", " ").count("±100 % = the limit")
        if lines or line_items or said != 1:
            wrong[fig["name"]] = {"limit-line columns (x)": lines[:12], "limit-line key items": line_items,
                                  '"±100 % = the limit" in the key': said}
    assert not wrong, wrong


@pytest.mark.parametrize("surface,scheme", CASES)
def test_samples_past_a_limit_still_read_as_past_it(measured, built, surface, scheme):
    """fb-509a6fe5, the meaning the line carried: every bin wholly past a limit with a sample draws in the limit
    colour (a lone sample included), and nothing inside ±100 % does. The oracle is the rows' own counts and edges."""
    wrong, expected = {}, 0
    for fig in ridgelines(measured, built, surface, scheme):
        past = sum(len(beyond_bins(row)) for row in fig["cells"].values())
        expected += past
        if not fig["columns"] or not fig["lines"] or any("base" not in line for line in fig["lines"]):
            wrong[fig["name"]] = "the figure does not say where its ±100 % and its baselines are (no column geometry)"
            continue
        img, red = fig["image"], near(fig["image"], fig["limit"])
        columns = {c["signal"]: c for c in fig["columns"]}
        for line in fig["lines"]:
            base = int(line["base"])
            for signal, column in columns.items():
                row = fig["cells"].get((line["id"], signal))
                if row is None or not row["stated"]:
                    continue
                for a, b in beyond_bins(row):
                    x0, x1 = sorted((column_x(column, pct(row, a)), column_x(column, pct(row, b))))
                    span = red[base - 1, max(0, int(np.floor(x0)) - 1):int(np.ceil(x1)) + 2]
                    if not span.any():
                        wrong.setdefault(fig["name"], []).append(f"{line['id']} {signal}: the bin {a:.3g} … {b:.3g} past the limit is not in the limit colour")
                inner = (int(np.ceil(column_x(column, -100))) + 2, int(np.floor(column_x(column, 100))) - 2)
                inside = red[int(line["y"]):base + 1, inner[0]:inner[1]]
                if inside.any():
                    wrong.setdefault(fig["name"], []).append(f"{line['id']} {signal}: {int(inside.sum())} limit-coloured pixels inside ±100 %")
        hit = [k for k in fig["key"] if k["mark"] == "fill" and k["colour"] and np.abs(np.array(css_rgb(k["colour"])) - fig["limit"]).max() <= 2]
        if past and not hit:
            wrong.setdefault(fig["name"], []).append("the key does not name the limit-coloured bars (samples past the limit)")
    assert expected, f"{surface}: the made-up arm has no sample past a limit, so this would prove nothing"
    assert not wrong, wrong


@pytest.mark.parametrize("surface,scheme", CASES)
def test_the_actual_units_layout_keeps_its_limit_lines_and_every_line_mark_is_readable(measured, built, surface, scheme):
    """fb-509a6fe5 keeps them where they carry information; fb-7a2772f9: the limit, the planner's limit and the
    percentile ticks are each >= 1.5 px wide and >= 3:1 against the surface they cross."""
    wrong, seen = {}, {"limit": 0, "planner": 0}
    for fig in multiples(measured, built, surface, scheme):
        img = fig["image"]
        for strip in fig["strips"]:
            row, box = strip["row"], strip["box"]
            sc = row.get("scale") or 1
            surface_colour = strip_surface(img, strip)
            marks = []
            if row["stated"]:
                marks += [("limit", row["low"]), ("limit", row["high"])]
            if isinstance(row.get("planner_low"), (int, float)) and isinstance(row.get("planner_high"), (int, float)):
                marks += [("planner", row["planner_low"]), ("planner", row["planner_high"])]
            for kind, value in marks:
                seen[kind] += 1
                width, ratio = line_width(img, int(box["y"]) - 1, strip_x(strip, value), surface_colour)
                if width < LINE or ratio < CONTRAST:
                    wrong.setdefault(fig["name"], []).append(f"{strip['id']} {kind} at {value * sc:.4g}: {width:.2f} px, {ratio:.2f}:1")
            base = int(box["y"] + box["h"])
            for value in (row.get("p001"), row.get("p999")):
                if isinstance(value, (int, float)) and np.isfinite(value):
                    tick_surface = mode(img[base + 2, int(box["x"]):int(box["x"] + box["w"]), :][None])
                    width, ratio = line_width(img, base + 2, strip_x(strip, value), tick_surface)
                    if width < LINE or ratio < CONTRAST:
                        wrong.setdefault(fig["name"], []).append(f"{strip['id']} percentile tick at {value * sc:.4g}: {width:.2f} px, {ratio:.2f}:1")
    assert seen["limit"] and seen["planner"], f"{surface}: no limit or planner line to measure ({seen}), so this proves nothing"
    assert not wrong, wrong


@pytest.mark.parametrize("surface,scheme", CASES)
def test_the_band_beyond_the_limit_and_the_caps_are_clearly_visible(measured, built, surface, scheme):
    """fb-7a2772f9: the beyond-the-limit band's ink is >= 3:1 against the surface and covers a visible share of it
    (where no bar stands on it); a clipped bar's cap is >= 1.5 px of a colour >= 3:1 against the surface."""
    wrong, bands, caps = {}, 0, 0
    for fig in multiples(measured, built, surface, scheme):
        img = fig["image"]
        for strip in fig["strips"]:
            row, box = strip["row"], strip["box"]
            surface_colour = strip_surface(img, strip)
            base = int(box["y"] + box["h"])
            step = (row["hi"] - row["lo"]) / row["bins"]
            if row["stated"]:
                busy = np.zeros(img.shape[1], dtype=bool)
                for i, n in enumerate(row["counts"]):
                    if n > 0:
                        a, b = strip_x(strip, row["lo"] + i * step), strip_x(strip, row["lo"] + (i + 1) * step)
                        busy[max(0, int(a) - 2):int(b) + 3] = True
                sides = ((box["x"] + 1, strip_x(strip, row["low"]) - 3), (strip_x(strip, row["high"]) + 3, box["x"] + box["w"] - 2))
                for x0, x1 in sides:
                    free = [x for x in range(int(np.ceil(x0)), int(np.floor(x1))) if not busy[x]]
                    if len(free) < 8:
                        continue
                    bands += 1
                    region = img[int(box["y"]) + 2:base - 2, free, :]
                    dev = deviation(region, surface_colour)
                    peak = np.unravel_index(dev.argmax(), dev.shape)
                    ratio = contrast(region[peak], surface_colour)
                    share = float((dev >= max(1, 0.5 * dev.max())).mean())
                    if ratio < CONTRAST or share < BAND_INK:
                        wrong.setdefault(fig["name"], []).append(f"{strip['id']} band x {int(x0)}…{int(x1)}: ink {ratio:.2f}:1, {share:.0%} of it inked")
            for i in clipped_bins(row["counts"]):
                caps += 1
                x = int(strip_x(strip, row["lo"] + (i + 0.5) * step))
                profile = img[int(box["y"]) - 3:int(box["y"]) + 6, x, :]
                darkest = profile[deviation(profile, surface_colour).argmax()]
                rows = int(near(profile, darkest, 30).sum())
                ratio = contrast(darkest, surface_colour)
                if rows < 2 or ratio < CONTRAST:
                    wrong.setdefault(fig["name"], []).append(f"{strip['id']} cap on bin {i}: {rows} px, {ratio:.2f}:1")
    assert bands and caps, f"{surface}: no band ({bands}) or cap ({caps}) to measure, so this proves nothing"
    assert not wrong, wrong


@pytest.mark.parametrize("surface,scheme", CASES)
def test_the_normalized_figure_marks_are_clearly_visible(measured, built, surface, scheme):
    """fb-7a2772f9 on the ridgeline: the bars and the past-the-limit bars are >= 3:1 against their row's surface (the
    page, the zebra band, the picked tint); the percentile hairline is >= 1.5 px and >= 3:1; a picked row carries a
    mark >= 3:1 against its own surface, >= 2 px wide, the height of the row (a tint alone is ~1.1:1)."""
    wrong = {}
    for fig in ridgelines(measured, built, surface, scheme):
        img = fig["image"]
        samples = [k for k in fig["key"] if k["mark"] == "fill" and k["colour"]
                   and np.abs(np.array(css_rgb(k["colour"])) - fig["limit"]).max() > 2]
        if not samples:
            wrong[fig["name"]] = "the key names no bar colour (samples)"
            continue
        bar = css_rgb(samples[0]["colour"])
        if not fig["lines"]:
            wrong[fig["name"]] = "the figure does not say where its rows are (no row geometry), so nothing here is measured"
            continue
        if surface == "page" and not any(line.get("marked") for line in fig["lines"]):
            # the page always picks a joint (its Joint control, the first joint on a fresh visit), so its row is marked
            wrong[fig["name"]] = "no row is marked as the joint picked in the Joint control"
        for line in fig["lines"]:
            band = img[int(line["y"]) + 1:int(line["y"] + line["h"]) - 1]
            surface_colour = row_surface(img, line)
            for name, colour in (("bars", bar), ("past-the-limit bars", fig["limit"])):
                hits = band[near(band, colour, 24)]
                if len(hits):
                    ratio = min(contrast(c, surface_colour) for c in np.unique(hits, axis=0))
                    if ratio < CONTRAST:
                        wrong.setdefault(fig["name"], []).append(f"{line['id']} {name}: {ratio:.2f}:1 on {surface_colour.tolist()}")
                elif name == "bars":
                    wrong.setdefault(fig["name"], []).append(f"{line['id']}: no bar in the key's colour {bar}")
            if fig["columns"] and "base" in line:
                for column in fig["columns"]:
                    row = fig["cells"].get((line["id"], column["signal"]))
                    if row and isinstance(row.get("p001"), (int, float)) and isinstance(row.get("p999"), (int, float)) and row["stated"]:
                        mid = (column_x(column, pct(row, row["p001"])) + column_x(column, pct(row, row["p999"]))) / 2
                        y = int(line["base"])
                        profile = img[y:y + 8, int(mid), :]
                        widths = [across(profile, surface_colour, k, 0) for k in range(len(profile))]
                        width, ratio = max(widths)
                        if width < LINE or ratio < CONTRAST:
                            wrong.setdefault(fig["name"], []).append(f"{line['id']} {column['signal']} percentile hairline: {width:.2f} px, {ratio:.2f}:1")
            if line.get("marked"):
                if not fig["columns"]:
                    wrong.setdefault(fig["name"], []).append("a picked row, but no column geometry to find its mark")
                    continue
                left = img[int(line["y"]):int(line["y"] + line["h"]), :max(1, int(fig["columns"][0]["x"]) - 2)]
                others = [row_surface(img, o) for o in fig["lines"] if not o.get("marked")] or [surface_colour]
                strong = np.array([[min([contrast(px, surface_colour)] + [contrast(px, o) for o in others]) >= CONTRAST for px in col] for col in left.transpose(1, 0, 2)])
                tall = strong.mean(axis=1) >= 0.8
                if int(tall.sum()) < 2:
                    wrong.setdefault(fig["name"], []).append(f"{line['id']} is picked but carries no row-tall mark >= 3:1 (best {strong.mean(axis=1).max():.0%} of the row)")
    assert not wrong, wrong


@pytest.mark.parametrize("surface,scheme", CASES)
def test_every_key_swatch_is_readable_and_the_key_names_only_what_is_drawn(measured, built, surface, scheme):
    """fb-7a2772f9: every mark swatch (not the group colours, see the module docstring) is >= 3:1 against the key's
    background, >= 12 px along and >= 2 px across; the key names a mark only when the figure draws it."""
    wrong = {}
    figures = ridgelines(measured, built, surface, scheme) + multiples(measured, built, surface, scheme)
    seen = set()
    for fig in figures:
        key_id = (fig["name"].rsplit(" · ", 1)[0] if " · " in fig["name"] else fig["name"], fig["keyText"])
        if key_id in seen:
            continue
        seen.add(key_id)
        for item in fig["key"]:
            if item["group"] or not item["swatch"] or "image" not in item:
                continue
            img, sw = image(item["image"]), item["swatch"]
            surface_colour = mode(img)
            region = img[max(0, int(sw["y"]) - 1):int(np.ceil(sw["y"] + sw["h"])) + 1, max(0, int(sw["x"]) - 1):int(np.ceil(sw["x"] + sw["w"])) + 1]
            dev = deviation(region, surface_colour)
            if dev.max() == 0:
                wrong.setdefault(fig["name"], []).append(f"{item['label']!r}: the swatch draws nothing")
                continue
            peak = np.unravel_index(dev.argmax(), dev.shape)
            ratio = contrast(region[peak], surface_colour)
            ys, xs = np.nonzero(dev >= 0.5 * dev.max())
            h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
            if ratio < CONTRAST or max(h, w) < SWATCH_LONG or min(h, w) < SWATCH_SHORT:
                wrong.setdefault(fig["name"], []).append(f"{item['label']!r} ({item['mark']}): {ratio:.2f}:1, ink {w}×{h} px")
        # names only what is drawn
        marks = {item["mark"] for item in fig["key"]}
        labels = " | ".join(item["label"] for item in fig["key"])
        if "strips" in fig:
            stated = any(s["row"]["stated"] for s in fig["strips"])
            planner = any(isinstance(s["row"].get("planner_low"), (int, float)) for s in fig["strips"])
            ticks = any(isinstance(s["row"].get("p001"), (int, float)) for s in fig["strips"])
            for name, drawn, named in (("the limit", stated, "line" in marks and "the limit" in labels),
                                       ("beyond the limit", stated, any(i["label"] == "beyond the limit" and i["mark"] != "text" for i in fig["key"])),
                                       ("the planner's limit", planner, "dash" in marks),
                                       ("p0.1 / p99.9 ticks", ticks, "tick" in marks)):
                if drawn != named:
                    wrong.setdefault(fig["name"], []).append(f"{name}: drawn {drawn}, named {named}")
        else:
            picked = any(line.get("marked") for line in fig["lines"] or [])
            named = any("picked" in item["label"] for item in fig["key"] if item["mark"] != "text")
            if picked != named:
                wrong.setdefault(fig["name"], []).append(f"the picked row: drawn {picked}, named {named}")
            past = any(beyond_bins(row) for row in fig["cells"].values())
            red = any(item["mark"] == "fill" and item["colour"] and np.abs(np.array(css_rgb(item["colour"])) - fig["limit"]).max() <= 2 for item in fig["key"])
            if past != red:
                wrong.setdefault(fig["name"], []).append(f"samples past the limit: drawn {past}, named {red}")
    assert not wrong, wrong


def test_the_matplotlib_sibling_keeps_the_same_two_rules(built):
    """The same figure's third drawing, traj_compare's Matplotlib viewer (ridgeline.png, limit-bars.png; light only, a
    white PNG): its normalized ridgeline draws no limit line and paints the samples past a limit in the limit colour;
    its limit bars hatch beyond the limit in an ink >= 3:1 instead of the 1.37:1 flat grey."""
    pytest.importorskip("matplotlib")
    import io

    import matplotlib
    from matplotlib.image import imread

    from traj_compare.coverage import matplotlib_view as mpl_view

    def png(figure_id: str) -> np.ndarray:
        buffer = io.BytesIO()
        with matplotlib.rc_context(mpl_view.STYLE):
            mpl_view.figure(built["payload"], figure_id).savefig(buffer, format="png", dpi=130, facecolor="white")
        buffer.seek(0)
        return (imread(buffer)[..., :3] * 255).round().astype(int)

    limit = css_rgb(mpl_view.LIMIT_COLOR)
    ridge = png("ridgeline")
    red = near(ridge, limit)
    runs, best = red[0].astype(int), red[0].astype(int)
    for y in range(1, red.shape[0]):
        runs = np.where(red[y], runs + 1, 0)
        best = np.maximum(best, runs)
    past = any(beyond_bins(page_hist(built["payload"], j["name"], s)) for j in built["payload"]["joints"] for s in ("q", "qd", "qdd"))
    assert past, "the made-up arm has no sample past a limit, so this would prove nothing"
    bars = png("limit-bars")
    flat = int(near(bars, mpl_view.OUTSIDE_RGB, 2).sum())
    # the hatch is drawn in MUTED (the PNG has no geometry to find the band by, so its colour is held as computed)
    assert {"limit-line columns (x)": [int(x) for x in np.flatnonzero(best >= LINE_RUN)][:12],
            "limit-coloured pixels (samples past the limit)": int(red.sum()) > 0,
            "flat beyond-the-limit pixels": flat,
            "hatch ink >= 3:1 on white": contrast(css_rgb(mpl_view.MUTED), [255, 255, 255]) >= CONTRAST,
            } == {"limit-line columns (x)": [], "limit-coloured pixels (samples past the limit)": True,
                  "flat beyond-the-limit pixels": 0, "hatch ink >= 3:1 on white": True}
