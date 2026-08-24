# Vendored browser libraries

These files are third-party, vendored verbatim so that generated reports are
fully self-contained (no CDN, no network at view time). Do not edit them.

| File | Project | Version | Source URL | License |
| --- | --- | --- | --- | --- |
| `uplot.iife.min.js` | [uPlot](https://github.com/leeoniya/uPlot) | 1.6.30 | https://cdn.jsdelivr.net/npm/uplot@1.6.30/dist/uPlot.iife.min.js | MIT |
| `uplot.min.css` | uPlot | 1.6.30 | https://cdn.jsdelivr.net/npm/uplot@1.6.30/dist/uPlot.min.css | MIT |
| `three.min.js` | [three.js](https://github.com/mrdoob/three.js) | r160 (0.160.0, last UMD build) | https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js | MIT |
| `viewhelper.js` | three.js `examples/jsm/helpers/ViewHelper.js` | r160 (0.160.0) | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/helpers/ViewHelper.js | MIT |

Downloaded 2026-07-28 (`viewhelper.js` 2026-07-29). three r160 is deliberately
pinned: it is the last release that ships the classic-script UMD build
(`window.THREE`), which is what a single-file `<script>`-inlined report needs.
Its startup `console.warn` about deprecation is expected and harmless.

`viewhelper.js` is the orientation gizmo the three.js editor itself uses — the
maintained off-the-shelf alternative to a hand-rolled view cube. Only its
ES-module header and footer are rewritten (`import … from 'three'` →
destructuring the `THREE` global; `export` → `THREE.ViewHelper = …`) because
the report loads classic scripts; the body is upstream and must stay that way
so it can be diffed against the release.

`plots.js`, `viewer3d.js`, and `style.css` in this directory are authored in
this package, not vendored.
