/* The host views' stylesheet (data-ui adds a view module's `css` to the document once). Colours from data-ui's tokens;
   the one rule outside a view's own element: a panel holding a tc-* view grows with its content, as a stock kpi panel
   does (NOTES.md gap: "a host view cannot say it is content-sized"). */
export const CSS = `
.dd-panel:not([data-sized])[data-type^="tc-"] data-views { height: auto; }
.dd-panel[data-type^="tc-"] .dv-view { overflow: visible; }
.tc-host { min-width: 0; }
.tc { font: 13px/1.45 var(--data-font, system-ui, sans-serif); color: var(--data-fg, #1f2328); min-width: 0; }
.tc b { font-weight: 600; }
.tc-mut { color: var(--data-muted, #6e7781); }
.tc-warn-t { color: #7d4e00; background: #fff8c5; border-radius: 4px; padding: 0 4px; white-space: nowrap; }
.tc-answer { font-size: 15px; line-height: 1.5; margin: 2px 0 10px; padding: 10px 12px; border: 1px solid var(--data-border, #d0d7de); border-radius: 8px; background: var(--data-bg, #fff); }
.tc-answer .tc-mut { font-size: 12.5px; }
.tc-sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: var(--c); margin: 0 5px 0 1px; vertical-align: -1px; flex: none; }
.tc-name { white-space: nowrap; }
.tc-gname { font-weight: 600; }
.tc-dep { font-size: 11px; font-weight: 400; color: var(--data-muted, #6e7781); margin-left: 6px; white-space: nowrap; }
.tc-chips { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; margin: 0 0 8px; font-size: 12.5px; }
.tc-chips .tc-k { font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: var(--data-muted, #6e7781); margin-right: 4px; }
.tc-chips button { font: inherit; font-size: 12.5px; padding: 2px 9px; border: 1px solid var(--data-border, #d0d7de); border-radius: 6px; background: var(--data-bg, #fff); color: inherit; cursor: pointer; }
.tc-chips button[aria-pressed="true"] { background: var(--data-fg, #1f2328); color: var(--data-bg, #fff); border-color: var(--data-fg, #1f2328); }
.tc-chips select { font: inherit; font-size: 12.5px; padding: 2px 6px; max-width: 420px; }
.tc-sp { flex: 1; }
.tc-link { font: inherit; font-size: 12px; padding: 1px 8px; border: 1px solid var(--data-border, #d0d7de); border-radius: 6px; background: var(--data-bg, #fff); color: var(--data-accent, #0969da); cursor: pointer; white-space: nowrap; text-decoration: none; }
.tc-chips .tc-link { color: var(--data-accent, #0969da); }
.tc-scroll { overflow-x: auto; max-width: 100%; }
.tc-foot { font-size: 11.5px; color: var(--data-muted, #6e7781); margin: 6px 2px 12px; }
.tc-u { display: block; font-size: 10.5px; font-weight: 400; color: var(--data-muted, #6e7781); white-space: nowrap; }
.tc-h { font-size: 11.5px; font-weight: 400; color: var(--data-muted, #6e7781); }
/* the League table */
.tc-ltable, .tc-stable { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
.tc-ltable th, .tc-stable th { font-size: 12px; font-weight: 600; text-align: right; padding: 4px 6px; border-bottom: 1px solid var(--data-border, #d0d7de); vertical-align: bottom; white-space: nowrap; }
.tc-ltable td, .tc-stable td { text-align: right; padding: 4px 6px; border-bottom: 1px solid var(--data-rule, #eaeef2); vertical-align: middle; white-space: nowrap; }
.tc-ltable th.tc-l, .tc-ltable td.tc-l, .tc-stable th.tc-l, .tc-stable td.tc-l { text-align: left; }
.tc-ltable tbody tr { cursor: pointer; }
.tc-ltable tbody tr:hover { background: var(--data-hover, #f6f8fa); }
.tc-rank { color: var(--data-muted, #6e7781); width: 1.5em; }
.tc-cfg { font-weight: 600; }
.tc-big { font-size: 15px; font-weight: 600; }
.tc-x { font-size: 11.5px; color: var(--data-muted, #6e7781); margin: 0 6px 0 5px; }
.tc-x.tc-best { color: #1a7f37; font-weight: 600; }
.tc-bar { display: inline-block; width: 48px; height: 7px; border-radius: 4px; background: var(--data-rule, #eaeef2); vertical-align: middle; overflow: hidden; }
.tc-bar i { display: block; height: 100%; background: var(--c); border-radius: 4px; }
.tc-kcell { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.tc-spark { display: block; }
.tc-axis { stroke: var(--data-rule, #e6e5e0); }
.tc-bestchip { font-size: 10.5px; padding: 0 5px; border-radius: 8px; border: 1px solid #a7d7b4; color: #1a7f37; }
.tc-cellbtn { font: inherit; border: 0; background: none; padding: 0; color: inherit; cursor: pointer; text-decoration: underline dotted; text-underline-offset: 3px; }
.tc-onfront td { background: color-mix(in srgb, var(--data-accent, #0969da) 6%, transparent); }
/* the inline drill: a config's worst targets, each linking its target view */
.tc-drillrow > td { padding: 0 0 8px 24px !important; background: var(--data-bg, #fff); cursor: default; }
.tc-ltable tbody tr.tc-drillrow:hover { background: none; }
.tc-drill { border: 1px solid var(--data-border, #d0d7de); border-left: 3px solid var(--data-accent, #0969da); border-radius: 6px; padding: 6px 8px; margin: 6px 0 8px; text-align: left; white-space: normal; }
.tc-drill-h { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; font-size: 12.5px; margin-bottom: 4px; }
.tc-drill .tc-stable td, .tc-drill .tc-stable th { padding: 2px 6px; font-size: 12px; }
/* matrices */
.tc-card { margin: 4px 0 8px; }
.tc-card h3 { font-size: 13.5px; margin: 6px 0 6px; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }
.tc-mtable { border-collapse: separate; border-spacing: 2px; font-size: 11.5px; font-variant-numeric: tabular-nums; }
.tc-mtable th { font-weight: 600; font-size: 11.5px; padding: 2px 4px; white-space: nowrap; }
.tc-mtable th.tc-l { text-align: left; }
.tc-mtable .tc-stick { position: sticky; left: 0; z-index: 1; background: var(--data-bg, #fff); }
.tc-mtable th.tc-grp { font-size: 11px; color: var(--data-muted, #6e7781); border-bottom: 1px solid var(--data-border, #d0d7de); text-align: center; font-weight: 600; }
.tc-mtable th.tc-col { vertical-align: bottom; cursor: pointer; min-width: 46px; max-width: 58px; }
.tc-mtable th.tc-col .tc-vh { display: inline-block; writing-mode: vertical-rl; transform: rotate(180deg); max-height: 128px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.tc-mtable th.tc-on { color: var(--data-accent, #0969da); }
.tc-mtable td { width: 52px; min-width: 46px; height: 22px; text-align: center; border-radius: 3px; padding: 0 3px; white-space: nowrap; }
.tc-mtable td.tc-r1 { box-shadow: inset 0 0 0 2px #2da44e; font-weight: 700; }
.tc-mtable td.tc-on { outline: 1px solid var(--data-accent, #0969da); }
.tc-mtable td.tc-none { background: repeating-linear-gradient(45deg, transparent 0 4px, var(--data-rule, #e3e2dc) 4px 5px); }
.tc-nested td[data-tc-cfg] { cursor: pointer; }
.tc-nested tr.tc-grow th { font-weight: 600; }
.tc-nested td.tc-gcell { opacity: .92; font-weight: 600; }
.tc-nested td.tc-roll { box-shadow: inset 2px 0 0 var(--data-border, #d0d7de); }
.tc-nested tr.tc-rollrow th, .tc-nested tr.tc-rollrow td { font-weight: 500; color: var(--data-muted, #6e7781); background: var(--data-bg, #fff); border-bottom: 1px solid var(--data-border, #d0d7de); }
.tc-nested tr.tc-rollrow td .tc-sw { width: 8px; height: 8px; margin: 0 2px 0 0; }
.tc-nested .tc-dep { display: inline; margin-left: 6px; }
.tc-chev { font: inherit; border: 0; background: none; cursor: pointer; width: 16px; padding: 0; color: var(--data-muted, #6e7781); }
.tc-indent { display: inline-block; width: 18px; }
.tc-ramp { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 400; color: var(--data-muted, #6e7781); }
.tc-ramp i { display: inline-block; width: 90px; height: 9px; border-radius: 3px; }
/* small multiples */
.tc-multiples { display: grid; gap: 12px; margin: 4px 0 10px; }
.tc-fig { margin: 0; border: 1px solid var(--data-rule, #eaeef2); border-radius: 8px; padding: 6px 6px 2px; min-width: 0; }
.tc-fig figcaption { font-size: 12.5px; margin: 0 0 2px 4px; }
.tc-figans { font-size: 12px; color: var(--data-fg, #1f2328); margin-top: 1px; }
.tc-panel { display: block; }
.tc-grid { stroke: var(--data-rule, #eaeef2); }
.tc-tick { font-size: 10px; fill: var(--data-muted, #6e7781); }
.tc-dl { font-size: 10.5px; font-weight: 600; }
.tc-dl-on { fill: var(--data-fg, #1f2328); }
.tc-front { fill: none; stroke: var(--data-fg, #1f2328); stroke-width: 1.4; stroke-dasharray: 5 3; opacity: .7; }
.tc-onring { stroke: var(--data-fg, #1f2328); stroke-width: 1.6; }
/* tiles */
.tc-top5 { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 1px 8px; font-size: 12px; align-items: center; font-variant-numeric: tabular-nums; }
.tc-top5 .tc-r { color: var(--data-muted, #6e7781); }
.tc-top5 .tc-v { text-align: right; }
.tc-tile { display: flex; flex-direction: column; gap: 4px; padding: 2px 2px 0; }
.tc-tnum { font-size: 24px; font-weight: 650; line-height: 1.2; display: flex; align-items: baseline; flex-wrap: wrap; gap: 0 8px; }
.tc-tnum .tc-name { font-size: 22px; }
.tc-tval { font-size: 15px; font-weight: 500; color: var(--data-muted, #6e7781); }
.tc-tsub { font-size: 12.5px; line-height: 1.45; }
.tc-tsub a { color: var(--data-accent, #0969da); }
.tc-tfig { margin-top: 4px; }
.tc-mini { display: block; max-width: 100%; }
.tc-fill { fill: #5a8fca; }
.tc-empty { fill: var(--data-rule, #e3e2dc); }
.tc-dep0 { fill: #2a78d6; } .tc-dep1 { fill: #86afdb; } .tc-dep2 { fill: #eb6834; } .tc-dep3 { fill: #2f9e44; }
@media (prefers-color-scheme: dark) {
  .tc-warn-t { color: #e3b341; background: #272115; }
  .tc-x.tc-best, .tc-bestchip { color: #57ab5a; border-color: #2b6a30; }
}
`;
