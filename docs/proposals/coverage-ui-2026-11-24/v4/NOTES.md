# V4 · Tidy (hand-rolled)

**Thesis:** keep today's page, its at-a-glance views and its tabs, which Zach likes. Fix exactly what he flagged on
Nov 23 and change nothing structural.

Open: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8814`,
then `http://127.0.0.1:8814/v4/index.html`. Proof: `node check.cjs v4 --port 8814 --shots shots` passes 8 of 8 gates.

## What changed against today's page (each point is one of Zach's Nov 23 items)

1. **Headline numbers (1).** The one-sentence answer and the 15 numbers now sit in one card, on Overview only. They
   are grouped as Dataset · Joints · Tool, with the code id beside each label. The card is about 245 px tall; the old
   tiles were about 375 px.
2. **Drill in + Rerun (2).** Clicking a row opens a drawer on the right, in two columns. On the left: the
   trajectory's numbers, what only it adds (with its rank), and its per-joint span next to the whole dataset's span. On
   the right: its tool path drawn over the other 53 (from above and from the front), and q / qd per joint over time.
   The drawer has **Open in Rerun**. If that fails, it shows the command and a Copy button. ↑ / ↓ step through the
   rows; Esc closes it.
3. **The coloured squares (3).** Each blue square is now a labelled `dev` / `holdout` chip. The table's status line
   has a legend saying the same colours draw the split lines in One joint and the Limits bars.
4. **Table (4).** Built by hand in data-ui's table style (robotparts Datasheet):
   - View tabs across the top: All · by split / Holdout only / By kind / Adds the most / **+ Save view**. Saved views
     can be renamed (double-click) and deleted (×). A dot marks a view you have changed but not saved.
   - Search and a columns (settings) icon at the right.
   - Group by split / kind / none.
   - Split and kind chips with live counts.
   - Number ranges under each column (`2..4`, `>30`).
   - Sort by clicking a header. Span of position / speed / acceleration.
   - A status line like "54 of 54 rows · 2 groups · Unfold all Fold all".
   - New columns: "Only it" and tool path. Tool speed, z and tilt are in the column picker.
5. **Controls on every tab (5).** The control strip is gone. A gear at the top right opens one popover with: colour
   map (each with its ramp), Reverse, scale (with its one-line meaning), the "enough" count, the tool-frame note and
   Reset. The settings apply to every tab and are remembered in localStorage (try/catch). The gear button shows the
   current ramp and the map · scale name, so you can read it without opening.
   - Each tab now has its own header line. The joint picker shows only on One joint and on 3-D proposals (its
     per-joint shapes use the joint).
   - Tool position and Tool orientation show their frame as a chip.

## Consequential decisions

- **The joint picker is a row of buttons, not a drop-down.** All six joints are visible at once, so you switch with
  one click. It also shows on 3-D proposals, because the per-joint shapes there would otherwise have no way to change
  the joint.
- **The tab lives only in the URL (`#tab=`).** It is no longer stored in localStorage. A fresh open lands on Overview,
  where the headline is; a link or a reload keeps the tab.
- **The drawer floats over the table instead of pushing it.** The rows' names stay clickable under it, so clicking
  another row just switches the drawer. It is 900 px wide so the whole trajectory fits on one screen at 1440 × 900.
- **The "enough" count only changes the "Enough / not" colouring.** The "% with ≥ 10 samples" leads were counted by
  analyze at 10, so they keep saying "≥ 10" and do not move. The popover says this. Group rows show a count only, no
  sums: no new numbers are computed in the page.

## Best when / loses when

- **Best when** Zach wants today's page back with its paper cuts gone. Nothing to relearn: same tabs, figures,
  colours and words.
- **Loses when** he wants the page to *be* data-ui ("one of our like generic tables from data-ui", "the common visual
  language"). This table only looks like data-ui; it is not data-ui's code. Its filters and saved views would need
  porting, and the figures still don't cross-filter with the table.

## Parts worth keeping in a splice

1. `drawer.js`: the two-column drill drawer (numbers, "only it" rank strips, span against the dataset, tool path over
   the other 53, joints over time, Open in Rerun with a command fallback). It works over any table.
2. The gear popover in `coverage.js`: `buildSettings`, colour maps drawn as ramp buttons, the gear showing the current
   ramp.
3. The Overview's single headline card (`buildStats`), and the per-tab headers (`buildTabHead`) carrying only the
   controls that act on that tab.

## What is simulated or missing

- In `check.cjs`, Open in Rerun is intercepted (the story still shows "intercepted by check.cjs" as the command).
  Against the round's real server it starts the viewer.
- The table is data-ui's *look*, built by hand. It does not import data-ui (V4's thesis keeps the page hand-rolled).
  Saved views live in this browser's localStorage, not in a `.base` file.
- `samples.json` (9.3 MB) is fetched once, on the first drill. It is not subsampled. From file:// the drawer says it
  can't be loaded, and Open in Rerun shows the `uvx … rerun <abs path>` command instead.
- The data payload has no back links and no sibling pages, so today's breadcrumb and DATASET / SUBSET chips are
  missing here. The live page would still draw them from its payload.
- The story runs after the gates, so the landing still shows magma, the colour map the G4b gate picked. That colour
  choice was remembered, which is the behaviour being shown.
