/* The coverage views' stylesheet (one for the bundle: registered with folder "coverage", so data-ui adds it once).
 * Colours only from data-ui's private tokens (--dv-*, CONTRACT §4); classes dv-coverage-* (the bundle's prefix). */
export default `
.dv-coverage { position: relative; font: 12.5px/1.45 var(--dv-font); color: var(--dv-fg); min-width: 0; }
/* V7: a grid, not a wrapping flex row: after a redraw Chrome sized the wrapped row's head to its first line only, and
 * the "colour =" switch then sat over the figure (measured 2026-11-24 on One joint after a query change) */
.dv-coverage { container-type: inline-size; }
/* a dashboard panel lays its view out as a column of fixed height: the head, figure and legend keep their own height
 * (the figure is sized to what is left, see room() and each view's measured reserve) */
.dv-coverage > * { flex-shrink: 0; }
.dv-coverage-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 4px 8px; margin: 0 0 6px; min-height: 24px; }
@container (max-width: 620px) { .dv-coverage-head { grid-template-columns: minmax(0, 1fr); } .dv-coverage-head .dv-coverage-switch { justify-self: end; } }
.dv-coverage-lead { margin: 0; color: var(--dv-muted); min-width: 0; }
.dv-coverage-lead b { color: var(--dv-fg); font-weight: 600; }
.dv-coverage-switch { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; margin-left: auto; }
.dv-coverage-seg-label { color: var(--dv-muted); font-size: 11px; text-transform: lowercase; }
.dv-coverage-seg { display: inline-flex; border: 1px solid var(--dv-border); border-radius: calc(var(--dv-radius, 8px) - 2px); overflow: hidden; }
.dv-coverage-seg button { font: inherit; font-size: 11.5px; border: 0; background: var(--dv-bg); color: var(--dv-muted); padding: 2px 9px; cursor: pointer; }
.dv-coverage-seg button + button { border-left: 1px solid var(--dv-border); }
.dv-coverage-seg button[aria-pressed="true"] { background: var(--dv-subtle); color: var(--dv-fg); font-weight: 600; }
.dv-coverage-body { min-width: 0; }
.dv-coverage-heatrow { display: flex; gap: 8px; align-items: flex-start; min-width: 0; }
.dv-coverage-single, .dv-coverage-multiples { min-width: 0; }
.dv-coverage-multiples { display: grid; gap: 4px 6px; }
.dv-coverage-panel { min-width: 0; }
.dv-coverage-panel-title { font-size: 11px; color: var(--dv-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dv-coverage-panel-title b { color: var(--dv-fg); font-weight: 600; }
.dv-coverage-heat, .dv-coverage-canvas { display: block; }
.dv-coverage-colorbar { flex: 0 0 auto; width: 92px; font-size: 10.5px; color: var(--dv-muted); }
.dv-coverage-cb-title { color: var(--dv-fg); margin-bottom: 4px; line-height: 1.2; }
.dv-coverage-cb-body { position: relative; }
.dv-coverage-cb-canvas { display: block; border: 1px solid var(--dv-border); }
.dv-coverage-cb-tick { position: absolute; left: 18px; transform: translateY(50%); white-space: nowrap; font-variant-numeric: tabular-nums; }
.dv-coverage-cb-tick::before { content: ""; position: absolute; left: -6px; top: 50%; width: 4px; border-top: 1px solid var(--dv-muted); }
.dv-coverage-cb-note { margin-top: 6px; line-height: 1.25; }
.dv-coverage-legend { display: flex; flex-wrap: wrap; gap: 3px 14px; margin-top: 6px; font-size: 11.5px; color: var(--dv-muted); }
.dv-coverage-li { display: inline-flex; align-items: center; gap: 6px; font: inherit; color: inherit; background: none; border: 0; padding: 0; }
button.dv-coverage-li { cursor: pointer; border-radius: 4px; padding: 1px 4px; margin: -1px -4px; }
button.dv-coverage-li:hover { background: var(--dv-hover); }
button.dv-coverage-li[aria-pressed="false"] { opacity: .45; text-decoration: line-through; }
.dv-coverage-sw { display: inline-block; width: 14px; height: 10px; border-radius: 2px; flex: 0 0 auto; }
.dv-coverage-sw-empty { background: var(--dv-bg); border: 1px solid var(--dv-border); }
.dv-coverage-sw-outside { background: rgb(221, 220, 214); }
.dv-coverage-sw-frame { border: 1.5px solid currentColor; background: transparent; }
.dv-coverage-sw-line { height: 0; border-top: 2px solid currentColor; }
.dv-coverage-sw-dash { height: 0; border-top: 2px dashed currentColor; }
.dv-coverage-sw-tick { width: 2px; height: 12px; background: currentColor; }
.dv-coverage-sw-path { height: 0; border-top: 2.5px solid currentColor; }
.dv-coverage-problem { color: var(--dv-warn); }
.dv-coverage-tip { position: fixed; z-index: 60; pointer-events: none; max-width: 320px; padding: 6px 9px; border-radius: 6px;
  background: var(--dv-fg); color: var(--dv-bg); font-size: 11.5px; line-height: 1.4; box-shadow: 0 4px 14px rgb(0 0 0 / .18); }
.dv-coverage-tip b { font-weight: 600; }
.dv-coverage-empty { color: var(--dv-muted); margin: 12px 0; }
.dv-coverage-hist-grid { display: grid; gap: 10px 14px; }
.dv-coverage-card { border: 1px solid var(--dv-border); border-radius: calc(var(--dv-radius, 8px) - 2px); padding: 6px 8px 4px; min-width: 0; }
.dv-coverage-card-head { font-size: 12px; margin-bottom: 2px; }
.dv-coverage-card-head b { font-weight: 600; }
.dv-coverage-card-head span { color: var(--dv-muted); margin-left: 6px; font-size: 11px; }
.dv-coverage-proj { display: flex; gap: 10px; align-items: flex-start; min-width: 0; }
.dv-coverage-proj-title { font-size: 11.5px; color: var(--dv-muted); margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dv-coverage-proj-title b { color: var(--dv-fg); font-weight: 600; }
/* V7: the click layer over a plot (one cell wider and taller: see kit.js hitLayer), the faded swatch, the sheet */
.dv-coverage-wrap { position: relative; display: inline-block; vertical-align: top; }
.dv-coverage-hit { position: absolute; outline: none; }
.dv-coverage-hit:focus-visible { box-shadow: 0 0 0 2px var(--dv-accent); border-radius: 2px; }
.dv-coverage-tip-hint { opacity: .75; font-style: italic; }
.dv-coverage-sw-faded { border: 1px solid var(--dv-border); }
.dv-coverage-sheet { display: grid; gap: 0 28px; font-size: 12.5px; }
.dv-coverage-sheet-col { min-width: 0; }
.dv-coverage-sheet-h { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--dv-muted); margin: 0 0 2px; }
.dv-coverage-sheet-row { display: flex; align-items: baseline; gap: 10px; padding: 1.5px 0; border-bottom: 1px solid var(--dv-rule, var(--dv-border)); cursor: help; }
.dv-coverage-sheet-row:last-child { border-bottom: 0; }
.dv-coverage-sheet-l { flex: 1 1 auto; min-width: 0; color: var(--dv-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dv-coverage-sheet-v { flex: 0 0 auto; color: var(--dv-fg); font-weight: 600; font-variant-numeric: tabular-nums; }
`;
