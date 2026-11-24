# V6 · Who goes there (hand-rolled)

**Thesis.** Every coloured cell answers "which trajectories made this?", and every empty one answers "who comes closest?".
You filter the dataset by clicking the figures.

Run it: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8816`,
then open `http://127.0.0.1:8816/v6/index.html`. It also opens from `file://`. Without a server, the drill's motion
charts and Open in Rerun fall back to a message, and the Rerun command comes with a Copy button.

Files: `index.html`, `v6.css`, `v6.js` (the whole page, no build step) and `coverage_color.js`, a copy of the live page's
colour module. The page reads `../data/coverage.js`, `membership.js` and `trajectories.js`. It fetches `samples.json` on
the first drill.

## Consequential decisions

1. **The query is a row of chips that the figures write.** A click on a q×qd or qd×qdd cell, a tool pixel (xy/xz/yz),
   a direction cell (on the disc or the unrolled map) or a histogram bar adds a chip, such as "visits shoulder_pan
   q 0–20°, qd 0–15°/s". Chips AND together. Clicking the same cell again removes its chip, and clicking a chip's
   text opens the tab and joint where that cell lives. Chips use membership's own grids, so a chip's cell is exactly
   the payload's cell.
   - A **bar** click maps to the matching column or row: q → a q×qd column, qd → a q×qd row, qdd → a qd×qdd row. The
     chip states that band ("q 0–20° (any speed)"), not the 120-bin bar, because membership has no finer grid. Jerk
     bars cannot be clicked.
   - An **empty cell** sets a "closest 8" chip (THEN). It ranks the current AND answer by distance and keeps the 8
     nearest. A thin line runs from the empty cell to each of those trajectories' nearest cell. The distance unit is
     stated in the chip and the dock: nearest-pixel search (cm), nearest-cell search (cells) or nearest-direction
     search (°).
2. **Colour is trajectories per cell by default**, which is the count that a click answers. The gear can switch it to
   samples per cell. Directions are always samples, because the payload keeps no per-direction trajectory count, and
   the legend says so. The figures never recount a subset.
   - Instead, they **fade** every cell that no trajectory in the answer visits. This cross-filters every tab while the
     counts stay the payload's.
   - The only numbers the page derives are the answer size ("n of 54", labelled a subset count from membership), the
     nearest-cell distances, and the distance on each hole pin.
3. **A "who" dock sits beside every figure tab** (340 px on the right, filling the window). It lists the trajectories
   in the answer. Hovering a row inks that trajectory's cells on every figure on screen, including the histograms
   (ticks under the axis) and the disc.
   - The **Trajectories** tab is the full table: text filter, column filters (split, kind, tags), header sort, group
     by split, kind or tags with fold, and "Unfold all · Fold all".
   - **Saved views:** four built in (All, Holdout, Adds most, By kind), plus "+ Save current". A saved view stores the
     filter, sort, grouping, span column and the figure query (marked "● query"), persists in localStorage, and can
     be deleted.
4. **The drill is a drawer over the right side, so the dataset stays visible behind it.** The open trajectory stays
   inked on the figures. The drawer shows:
   - its numbers;
   - "What it adds": its cells in ink over the faded dataset, on the tool view from above and on all six q×qd planes.
     Blue marks cells no other trajectory visits (payload `paths == 1`).
   - q and qd per joint over time: every sample from `samples.json`, not subsampled, one colour per joint, explained
     in a legend;
   - span bars and its directions;
   - ‹ › buttons to step through the answer;
   - **Open in Rerun**: it POSTs `/__rerun/open?rrd=data/rrd/<name>.rrd`, then shows the command with a Copy button,
     whether the call worked or failed.

**Holes** (Tool position tab) paints every reachable pixel with `paths = 0` amber. It also pins the 3 reachable pixels
farthest from any visited pixel, found by a nearest-pixel search on the payload's `paths` and `reachable`. Clicking a
pin, or any hole, asks who comes closest.

## Best when / loses when

- **Best when** the question is about *which trajectories*: who is behind a hot spot, who almost reaches a gap, and
  so which one to extend or which new task to add. It suits curating the dataset: click a region, read the list,
  drill in, open it in Rerun.
- **Loses when** you want coverage numbers recomputed for a subset (for example "what does holdout alone cover"):
  the page fades but never recounts, so that needs a sibling page.
  - Bars are only as fine as membership's grids (20° q columns).
  - A 2 cm pixel is a 2.6–4 px click target.
  - There is no 3-D voxel view, parallel coordinates or growth curve, because nothing in membership makes them
    clickable.
  - It is hand-rolled, so it shares nothing with data-ui (criterion fr5 scores low).
  - The canvas figures work with the mouse only.

## Parts worth keeping in a splice

1. **Figures that write the query, plus the docked who-list.** The protocol is small: a view emits
   `{grid, cells, label}`, and the list filters on membership. Any variant's heatmaps could adopt it, data-ui ones
   included.
2. **Holes, emptiest-spot pins and nearest lines.** "Who comes closest?" turns a coverage gap into a short list of
   trajectories to extend.
3. **The drill drawer.** It shows the trajectory's cells in ink over the faded dataset, marks the cells only it
   visits, plots its q and qd, and has Open in Rerun with a command, a Copy button and a file:// fallback. Saved views
   that keep the figure query are a small part worth taking along with it.

## Simulated, missing, caveats

- Under `check.cjs`, Open in Rerun is intercepted; served normally, it really POSTs to `traj_compare.serve`.
- The walkthrough's landing shows **magma**, not the default viridis. Gate G4b selects magma, and the gear's settings
  persist in localStorage (on purpose: set once). The joint and saved views persist the same way.
- Not drawn, because none can be clicked through membership: the tool speed histogram, tilt×yaw, the 3-D voxels and
  the three.js sphere. The direction disc is a Lambert equal-area drawing of the payload's own 12 × 24 sphere cells,
  which is that sphere seen from above.
- No dashed planner limits are drawn, because the payload's `planner_limits` is null.
- `samples.json` (9.3 MB) loads on the first drill. On file:// it cannot load, and the drill says so.
- The layout is computed for the window at load time; a resize rebuilds the tabs.
- Implementation detail: each heatmap's click target is one cell wider (right) and taller (top) than the plot. Its
  centre therefore lands in the middle of a cell rather than on a corner shared by four. The walkthrough clicks
  figure centres, and the extra strip outside the plot ignores clicks.
- **data-ui:** no part of data-ui is used (this is a hand-rolled variant). To make these parts stock, data-ui would
  need:
  - a selection protocol in which a view emits a cell selection and a table filters by a membership index;
  - a grid-heatmap view with cell-click selection, a selected-cell frame and fading of unselected cells;
  - a histogram view with band selection;
  - an equal-area direction disc view.
