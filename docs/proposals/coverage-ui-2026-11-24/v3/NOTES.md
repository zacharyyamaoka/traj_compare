# V3 · Coverage views in data-ui

**Thesis.** Move the coverage figures into data-ui as four stock view types, and draw the whole page as one data-ui
`.base`: dashboard pages as the tabs, a gear for the dashboard-wide colours, and the stock table for trajectories. Every
dataset page in every app then gets these figures in data-ui's common visual language.

**Checks.** `node check.cjs v3 --port 8813 --shots …/shots`: 8 of 8 gates pass, exit 0.

| Gate | What the check measured |
|---|---|
| G1 | The KPIs show on Overview only. |
| G4a | The joint rail shows on One joint only. |
| G4b | The gear is hidden at first, and picking magma repaints the figure. |
| G2 | Filtering cuts 32 drawn rows to 12; a header click reorders; 5 saved views. |
| G3 | The split colour legend is visible. |
| G2b | The drill opens workspace-dev-014 and posts `rrd=data/rrd/workspace-dev-014.rrd`. |
| G6 | 0 px sideways overflow. |
| G5 | No console or page errors. |

The stills are `shots/v3/step-1..5.png` and the walk is `shots/v3/session.webm`.

**Run it.**

```bash
/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8813
```

Then open `http://127.0.0.1:8813/v3/index.html`.

## What it is

| File | Role |
|---|---|
| `coverage.base` | The page, as data. It holds 7 `pages:` (Overview, Limits, One joint, All joints, Tool position, Tool orientation, Trajectories), a `settings:` block, `style:` (defaults + family colours), 10 datasets and 21 views. |
| `rows.py` → `rows/*.json` | The `traj_compare.coverage/1` payload reshaped into data-ui row tables with nothing recomputed. The only arithmetic is rad→deg for display columns and a voxel's centre from the payload's own lattice. `samples.json` is not read. |
| `views/` | The four new view types as data-ui plugins (§1 shape, classes `dv-coverage-*`, colours from tokens). `kit.js` holds their shared helpers. `coverage_color.js` is copied unchanged from traj_compare. |
| `app.js`, `settings.js`, `index.html`, `app.css` | The host. It registers the views, draws `pages:` as tabs (one `<data-dashboard>` per page, or a `<data-views>` for the table page), runs `<data-settings>` (the gear), and fills the drill. |
| `PROPOSED-CONTRACT.md` | The data-ui amendment a lane could land: §52, because §51 is already taken by `lane/trail-rest`. |

## Consequential decisions

1. **Rows: one row per grid, not one per cell.**
   - What a reader filters (joint, plane, signal, face) is a row with ordinary scalar columns: visited %, the limit
     box, and so on. The counts ride along as list cells, which data-ui's row model allows.
   - The alternative, cells as rows, would push 13,824 plane cells through `rowModel` on every pick and gain nothing,
     since nobody filters a bin.
   - Reading the whole payload as one row breaks the row model. A nested dict is not a cell, so the stock rail, peek,
     table and checker could not touch it.
   - Exception: the tool's voxels are one row per cell, because data-ui's stock `voxels` view (§32) reads exactly that.
2. **Colours set once, delivered through `update(input)` today.**
   - The gear's picks go into the dashboard's `style:`, and data-ui already resolves style into every panel's
     `input.view.style`; `resolveStyle` keeps unknown keys.
   - So the new views read `colormap`, `reverse` and `scale` from their input, with no global or event bus.
   - The amendment names the clean field `input.settings`, and the views already read it first (`settingsOf` in
     kit.js).
   - The picks are kept in localStorage. "Reset to the file's" appears only once you have picks.
3. **The joint picker is the page's rail, not a view option.** This departs from the brief, which said "a VIEW option".
   - One joint's three figures must show the same joint. A per-view option would allow three different joints.
   - data-ui already has the part: a `select` facet on the page's own dataset rail.
   - So `pages[].datasets.planes.facets` puts the stock rail on One joint and nowhere else, which satisfies G4a.
   - Clicking a row in the Overview ridgeline opens One joint with the rail moved to that joint.
   - Undo: give coverage-plane a `coverage.joint` option and drop the page rail.
4. **Trajectories is data-ui's stock table, and its stock side peek is the drill.**
   - The saved views are tabs: By split, What each one adds, Speed span, Acceleration span, Holdout only, plus `+` for
     your own, persisted in localStorage. Search sits behind the icon, as in Zach's robotparts reference (§47). Groups
     fold.
   - Two host-side departures:
     - A plain header click sorts, overriding data-ui's Notion default where a click opens the column menu; the header's
       ⋯ still opens that menu. The amendment proposes this as `columnClick: sort`. Undo: delete the click listener in
       `buildViewsPage`.
     - The search box opens on arrival at the page.
   - Open in Rerun sits in the peek's actions row (§46 `openElsewhere`), turned into the POST.
   - The peek's foot (§37 `peekExtra`) shows "what it adds" and the trajectory's tool path and joint paths over the
     whole set, drawn by the same coverage views in a muted mode with an overlay.

## Best when / loses when

- **Best when** Zach wants these figures in other apps too: sim2real, robot_metrics, a dataset page in traj_compare
  itself. When the "common visual language" matters more than bespoke polish. When an agent should be able to rearrange
  the page by editing one `.base`, since layout, pages, defaults and saved views are all data.
- **Loses when** the goal is the richest coverage page soonest:
  - Every figure is bound by data-ui's panel grid and chrome. The Arrange bar takes a row on each page, and each KPI
    card carries a "the producer's number" footer.
  - Figures a second app will not want were dropped (see below).
  - Several parts are host prototypes that only become stock once a data-ui lane lands §52, which is a barrier change to
    data-ui's contract.

## Parts worth keeping in a splice

1. **`views/coverage-plane.js` + `coverage-hist.js` with `kit.js`.** Plugin-shaped canvas views. Any variant can
   register them or copy their drawing: a shared scale across small multiples, colorbar ticks with the clip note,
   a legend item per mark, an interactive group legend, the ridgeline in % of limit.
2. **`<data-settings>` (`settings.js`).** The gear as a small element driven by a `settings:` spec. It drops into any
   page.
3. **The drill pattern.** The stock side peek, Open in Rerun in the actions row, and the trajectory's own tool path and
   joint paths overlaid on the dataset's figures (muted). It answers "what does this one add" visually.

## What is simulated or missing

- **Host prototypes** of what §52 would make stock: the page tabs (`pages:`), the gear, header-click sort, Open in Rerun
  (an `openElsewhere` link whose click is taken over), and the drill's figures (mounted by the host, not by
  `record.sections`).
- **A settings change remounts the open page's dashboard.** It calls `load(…, {keepState: true})`, so rails and
  selections stay, but every panel redraws. Hidden pages refresh when shown. §52 asks for an in-place `update(input)`.
- **Dropped figures:**
  - the 3-D direction sphere;
  - the parallel-coordinates density;
  - the dataset spaghetti and envelope figures (the drill shows one trajectory's paths instead);
  - the 3-D proposals tab;
  - the growth chart's shuffled p10–p90 band. A layered Vega spec with `y`/`y2` scrambled data-ui's axis title, so the
    stock chart draws only the two lines.
- **Stock `voxels`** keep their own grey ramp and do not follow the gear. Reachable-but-unvisited voxels (28,289 cells)
  are not drawn in 3-D; the projections show reachability instead.
- **The joint rail's "Any"** cannot be hidden: `any: false` is not a stock option. Picking it draws all six joints as
  small multiples. That works, but the slab view gets crowded.
- **Small layout blemishes** at 1440:
  - Overview's joint table clips its last column ("q×qd visite…", the % sign cut).
  - KPI labels truncate with an ellipsis; the full label is in the stock card's hover.
- **Payload size.** `rows/motion.json` (1.5 MB, the payload's per-trajectory paths) loads on the first drill.

## data-ui: stock vs new vs what it would need

| | Parts |
|---|---|
| **Stock, used as-is** | `<data-dashboard>` (layout, panels, Arrange, the dataset rail with a `select` facet); `<data-views>` with the bar in tabs form, query, view counts, Save view and `+`, groups with fold and summaries, `display: bar \| badge`, `units: inline`, `columnSize`; open `side` with `record.sections`, §46 `openElsewhere`, §37 `peekExtra`; `kpi` (15 cards, Overview only); `chart` (Vega-Lite growth lines and grouped bars, with its interactive legend); `voxels` (3-D tool cells); `registerView` / `loadView`; `parseBase` / `loadDataset`; tokens; `style.families`. |
| **New, registered from `v3/views/`** | `coverage-plane` (binned 2-D grids: joint planes, slabs, tilt × yaw; drill overlay), `coverage-hist` (limits small multiples, Overview ridgeline, tool speed / tilt / yaw), `coverage-projection` (xy/xz/yz footprints, samples / trajectories / max speed; drill overlay), `coverage-polar` (the tilt map). |
| **What data-ui would need** (`PROPOSED-CONTRACT.md`, §52) | the coverage bundle and its `coverage:` block; the grid / hist / projection row shapes checked by both checkers; the five colormaps and scales in core; the `--data-outside` and `--data-limit` tokens; `settings:` with `<data-settings>` and `input.settings`; `pages:` with per-page rails and `openPage`; `columnClick: sort`; per-row `rerun:` in the peek; record-section views binding `this.<column>` into any key and reading a layer dataset; the table badge reading `style.families`; a gallery case `trajectory-coverage` (needs Zach's OK that the UR5e sim rows are public-safe) with the checks listed there. |
