# V7 · Splice (data-ui, AI-default splice of V3 + V5/V6)

**Thesis.** data-ui's common visual language and V3's coverage views, with V5/V6's landing that shows the whole dataset
on one screen, and V6's "click a cell → who made it".

**Checks.** `node check.cjs v7 --port 8817 --shots …/shots`: 8 of 8 gates pass, exit 0 (`shots/v7.check.json`).

| Gate | What the check measured |
|---|---|
| G1 | The headline sheet shows on Overview only. |
| G4a | The joint rail shows on One joint only. |
| G4b | The gear is hidden at first, and picking magma repaints the figure. |
| G2 | Filtering cuts 31 drawn rows to 12; a header click reorders; 5 saved views. |
| G3 | The split colour legend is visible (and the who dock keys its own badges and bars). |
| G2b | The drill opens workspace-dev-014 and posts `rrd=data/rrd/workspace-dev-014.rrd`. |
| G6 | 0 px sideways overflow (and 0 px of document scroll: the figures column scrolls inside itself). |
| G5 | No console or page errors. |

The stills are `shots/v7/step-1..5.png`; the walk is `shots/v7/session.webm`.

**Run it.**

```bash
/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8817
```

Then open `http://127.0.0.1:8817/v7/index.html`. `rows/` is gitignored; `python3 v7/rows.py` rebuilds it.

## What came from which parent, and what changed

| Part | From | What changed in V7 |
|---|---|---|
| One `.base` (`coverage.base`) drawn by `<data-dashboard>` pages as tabs; the gear (`settings.js`); the stock Trajectories table with 5 saved views, search, groups, header-click sort; the stock side peek as the drill with Open in Rerun | **V3** | Unchanged in kind. The Overview's ridgeline and joint table moved to All joints. |
| The four coverage view types (`views/`) | **V3** | Each now reads the cell query (fades, framed chips, a click layer, "N of 54 visit it" in the hover) and measures its own head and legend before sizing the figure, so a longer legend never pushes it past its panel. `coverage-polar` also draws the payload's **equal-area sphere** (Lambert disk), the grid membership indexes; it replaces the 36 × 18 tilt × azimuth disk on Overview and Tool orientation. |
| The landing: one calm 1440 × 900 screen — a key/value headline sheet, every joint's q × qd plane as small multiples, the tool from three sides at one metric scale, where it points | **V5** (sheet, layout) and **V6** (the one-screen hero) | Built from V3's views at landing size (`coverage.compact`), not hand-rolled canvases. The sheet is a new small view, `coverage-sheet`: one column per section (Dataset · Joints · Tool), label · value, the full label + code id (`key`) + source on hover. No Arrange bar on this page (stock `layout.arrange: false`); a 20 px row grid there. |
| Click a cell → a plain-words chip; chips AND; the answer fades every figure; "n of 54" | **V6** | Data-ui-shaped (`views/query.js`): a view emits `coverage-cell` from its own element, the host owns the chips; the answer reaches both stock tables as data-ui's all-views filter, so their status lines read "8 of 54 rows" and the peek's ‹ › steps through the answer. Chips ride in the URL (`#page=…&q=…`). |
| The who list beside the figures | **V6** (dock) | A second stock `<data-views>` table (name, split badge, new cells bar), not hand-drawn. |
| The drill's content: its numbers, what it alone adds (first-visit + only-it cells), its tool path over the set, its joints over time, its spans against the set, ‹ ›, Open in Rerun with command + Copy | **V3** (peek, tool/joint paths over the muted set) + **V4/V5/V6** (numbers tiles, only-it ink, q/qd over time, span bars, the command shown even on success) | The q/qd-over-time plots are two **stock data-ui `chart` views** (Vega-Lite) on that trajectory's samples, keyed by their own legend. |

## Consequential decisions

1. **The who list is a docked stock table, not `host.open({records})`.** A records peek (V2) opens a 540 px panel over
   the right third of the figures each time you click, so the next cell you want to click is under it, and it closes
   as soon as you look elsewhere. The dock is always there (all 54 until you ask), answers the moment you click, and
   leaves every figure uncovered. It is the same stock table as the Trajectories tab, so its rows open the same drill.
   Cost: 316 px of width on every figure tab (the landing still fits, measured: 0 px of scroll).
2. **The drill from the dock is a drawer: data-ui's own peek, overlay mode, in a dock that widens to 560 px over the
   figures' right edge** (V6's drawer). The dataset stays visible on the left, chips and fade included, and the peek
   is the identical stock one the Trajectories table opens in split mode. Undo: give the dock `splitAt` back and the
   peek covers only the dock.
3. **The answer is data-ui's all-views filter, never recounted cells.** The figures keep the payload's counts and fade
   (a stated 84 % wash toward the surface, keyed "faded" in every legend while a question is set) the cells no answer
   trajectory visits. The only derived numbers are the answer size (a subset count from `membership.json`, said in
   the count's hover) and the fade. The filter is an or-group of `name ==` (Bases' grammar); the host relabels its pill
   "Who made it: the 8 that visit every asked cell", and the pill's ✕ clears the question everywhere.
4. **The pointing map is the payload's equal-area sphere.** It is the grid the headline "directions visited 95 %" counts
   and the grid membership indexes, so a click asks exactly the payload's cell; every wedge is the same share of the
   sphere. Colour is samples (the payload keeps no per-direction trajectory count).

## Best when / loses when

- **Best when** Zach wants V3's portability (every figure a registered data-ui view, the page one `.base`) *and* the
  one-glance landing *and* the "which trajectory made this, and what else does it do" loop: click a cell, read the
  list, drill, Open in Rerun, without leaving the screen.
- **Loses when** the screen is narrower than ~1300 px (the dock and the figures compete), or when the question is
  "what does this subset cover by itself": the page fades but never re-aggregates (V2's thesis). Membership's grids
  bound the clicks: q bins of 20° (10° for elbow), 2 cm pixels (a 3–4 px target on the landing), 12 × 24 directions;
  slabs, tilt × yaw, histograms and the 3-D voxels are not clickable and do not fade. Six figure tabs × the dock means
  the dock repeats on pages where nothing can be clicked (Limits).

## Parts worth keeping

1. **`views/query.js` + kit's `gridKey` / `cellWords` / `hitLayer` / `fade`.** A ~120-line cell query any coverage view
   joins in three lines (subscribe, fade, click layer); the click layer's one-cell overhang makes its centre one cell.
2. **The dock + drawer**: a stock table filtered by the answer beside the figures, whose peek widens over them.
3. **`coverage-sheet`**: 15 numbers in ~150 px with the code id on hover (as `kpi` `layout: sheet`, §52.9).

## What is simulated or missing

- **Host prototypes** of what data-ui would make stock: V3's (pages as tabs, the gear, header-click sort, Open in
  Rerun's POST, the drill's figures mounted by the host) plus V7's: the cell query and its chips (§52.8 in
  `PROPOSED-CONTRACT.md`), the pill relabel (a DOM rewrite after each render), the dock (host-placed), the drawer
  (the dock widens while a `.dv-peek` is shown).
- **Saved views do not keep the chips**: data-ui's Save view stores the view entry, not the all-views filter. The chips
  ride in the URL instead, so a link or bookmark reopens the question.
- **Rerun** was only called through check.cjs's intercept (it would open a window). The by-hand command is the server's
  own when it sends one; else the round's pinned `uvx --from rerun-sdk==0.40.0 rerun <abs path>` (the path from a
  constant, `ROUND_DIR`, when served; from the page's own path on file://).
- **`samples.json` is fetched whole** (9.3 MB) on the first drill, not subsampled; on file:// it cannot load and the
  drill says so. `rows/motion.json` (1.5 MB) also loads on the first drill.
- **The drill's oracle**: the only-it cells it inks (its membership cells where the payload's `paths` is 1) must sum to
  the table's "Only it"; a mismatch is a console error (none seen; G5 would fail).
- **Dropped from V3**: the 36 × 18 tilt × azimuth disk (the equal-area sphere replaces it); V3's other drops stand
  (3-D sphere, parallel coordinates, spaghetti/envelope, proposals tab, the growth band). From V6, not carried: holes,
  emptiest-spot pins, "closest 8" for an empty cell (an empty-cell click says "nobody visits that cell"), histogram-bar
  clicks. From V5: the selection-as-colour rule (cyan "only it") on the dataset figures; V7 shows only-it in the drill.
- **The walkthrough's stills show the hover readout** after each click (the mouse stays over the figure).

## data-ui: stock vs new vs what it would need

| | Parts |
|---|---|
| **Stock, used as-is** | `<data-dashboard>` (layout, panels, the dataset rail with a `select` facet, `layout.arrange: false`); two `<data-views>` tables on one dataset (the Trajectories page with tabs, query, view counts, Save view, `+`, groups, `display: bar \| badge`, the all-views filter and its pill; the dock with `toolbar: none`); the side peek in split (page) and overlay (dock) modes with `record.sections`, ‹ n of N ›, §46 `openElsewhere`, §37 `peekExtra`; `chart` (the growth lines and grouped bars, and the drill's q/qd over time, each in its own `<data-views>`); `voxels`; `registerView` / `loadView`; `parseBase` / `loadDataset`; tokens; `style.families`. |
| **New, registered from `v7/views/`** | V3's `coverage-plane`, `coverage-hist`, `coverage-projection`, `coverage-polar` (now with the equal-area sphere, the cell query and measured sizing) and V7's `coverage-sheet`. |
| **What data-ui would need** | V3's §52.1–52.7, plus §52.8 (a `membership:` dataset checked against the payload, `coverage-cell` → dashboard chips → `input.query`, the answer as an all-views clause with a host label `filtersLabel`, the overhanging click target) and §52.9 (`kpi` `layout: sheet`); a docked companion table (`dock:`) and a peek that can widen over its neighbours. |
