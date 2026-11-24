# V5 · Focus rail (hand-rolled)

**Thesis:** keep the whole dataset on screen, and let a trajectory list on the left light up what any trajectory (or a
few) contributes, everywhere at once.

Run: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8815`, then open `http://127.0.0.1:8815/v5/index.html`.
Files: `index.html`, `app.js` (all logic, ~2.3 k lines, no framework), `app.css`, `coverage_color.js` (a copy of the live
page's colour module). Data comes only from `../data/`.

## Consequential decisions

1. **Master–detail instead of a table tab.** The trajectory list stays on screen as a resizable left rail (drag the
   boundary, width remembered, double-click resets). Filter, sort, group-by (split / kind / shape / none) and saved-view
   chips (All · Holdout · Adds most · Only-it cells · + Save) live in the rail. The Trajectories tab is the same list
   full width with every column, and the rail folds away while it is open. Both share one state: a filter typed in one
   shows in the other.
2. **One colour rule under a selection, on every map.** The selection's cells keep the colour map (the dataset's count
   there). The rest of the dataset goes grey (or faded colour, a gear option). Cells **only** the selection reaches turn
   cyan, with a dark frame where the cells are big enough. This holds for all 18 joint planes, the three tool
   projections and the direction disk, and comes from `membership.json`. The focus bar reads "these k add N cells nobody
   else visits", and every such number is labelled "subset count from membership.json". For a single trajectory the
   page checks N against `trajectories.json`'s `only_it_q_qd_cells` and warns on any mismatch (none seen). 1-D
   histograms (Limits, tool speed, tilt, yaw) and the All-joints range strips overlay the selection binned from
   `samples.json`, labelled the same way.
3. **Selection works both ways.** Click a rail row (⇧ range, Ctrl toggle, ↑/↓ steps through the list). You can also
   click any heat-map cell or disk cell to select the trajectories that pass through it ("who goes here?"). The same
   works by clicking a path on One joint, or a point on the growth curve.
4. **The drill-in is a page inside the app, not a modal.** Double-click a row (or ▸ / Open ▸) to open it. The page has
   a breadcrumb back (Esc works too), Previous/Next through the current list order, eight numbers, joint q/qd over time
   (every sample), its spans against the dataset, its tool path over the dataset footprint, and its q×qd cells per
   joint. **Open in Rerun** POSTs `/__rerun/open?rrd=data/rrd/<name>.rrd` and shows the returned command with Copy. If
   the call fails, or the page was opened from file://, it shows the same one-line `uvx … rerun <abs path>` command.
   `#traj=<name>` and `#tab=<id>` deep-link to a page or tab.

Smaller calls: the headline numbers became a 3-column key/value sheet, so all 15 fit in about 100 px and the overview
still shows every joint's map, the tool projections and the direction disk above the fold. "How to read this" is a `?`
in each figure header. On One joint, the samples/trajectories switch sits in the tab bar next to the joint picker. Blue
always means "selected", so no group colour is blue.

## Best when / loses when

- **Best when** the question is about a trajectory or a set of them: what does dev-029 add, is the holdout set covering
  anything dev doesn't, which trajectory could I drop without losing coverage? It also works for scanning one by one,
  pressing ↓ in the rail and watching every map change. The cell-click lookup answers "who goes here?", which the live
  page cannot.
- **Loses when** you only want the dataset picture. The rail takes 300 px of width all the time (fold it by dragging
  it narrower to 220 px; it never fully collapses). With 54 trajectories the rail is fine, but at 5 000 it would need
  virtualisation and an aggregate view. Selecting many trajectories turns most cells "selected", so the grey/colour
  contrast and the cyan "only" set say less. All 54 selected falls back to the plain dataset colouring, and the page
  says so.

## Worth keeping in a splice

- The **selection overlay rule**: colour = the selection, grey = the rest, cyan = only it, plus the "adds N cells
  nobody else visits" readout. It is `painter()` + `drawHeat()` in `app.js` and works on any grid that `membership.json`
  indexes.
- **Click a cell to select who goes there.** It uses the `owners` map built once per grid from `membership.json`, and
  it is cheap.
- The **"What the selection adds" card** on Overview: cells reached and cells only the selection reaches, per grid
  kind, with the all-54 column matching the payload's own numbers (2 584 / 1 663 / 1 283 / 274).

## Simulated or missing

- **No 3-D.** Voxels show only as counts (in the Tool position lead and the adds card). The live page's three.js views
  (voxels, 3-D spaghetti, sphere, the 3-D proposals tab) are not carried over. The tool is shown as three projections
  plus an equal-area direction disk built from the payload's 288 sphere cells.
- **Not carried over from the live page:** slabs, the qdd envelope, parallel-coordinate density, and the tilt × azimuth
  and tilt × yaw heat maps.
- **Rerun was not run against the real endpoint here.** It would open a Rerun window on the desktop; check.cjs
  intercepts the POST, and the file:// fallback command was checked. The fallback's absolute path comes from a constant
  (`ROUND_DIR`) when served over http.
- `samples.json` is used whole (not subsampled). It is fetched after the first paint; figures that need it say
  "loading…" until then, or give the serve command when it cannot be fetched (file://). Jerk has no selection overlay
  because `samples.json` carries q, qd and qdd only.
- **Saved views and gear settings persist in localStorage** (per browser), not in a file or URL. Because the gear
  choice persists, the gallery's story lands in **magma**: check.cjs's G4b picks magma just before the story replays.
  The story's last step switches back to viridis.
- No hover preview: hovering a rail row does not light up the maps; it takes a click. There is no column chooser in the
  full table.
- Hand-rolled. No data-ui parts are used, so nothing here is stock data-ui.
