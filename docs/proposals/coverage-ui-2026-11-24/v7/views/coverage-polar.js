/* type: coverage-polar — a direction grid on a disk (PROPOSED-CONTRACT.md §52.4).
 *
 * Reads one grid row of tool directions and draws it as a disk seen from above: the centre is "along the reference"
 * (for the tool, straight down), the distance from the centre is the tilt, the angle is which way it leans in the base
 * XY plane (+x right, +y up). Two grids:
 *   grid: sphere        (V7) the payload's own equal-area sphere: 12 rings by the tool z axis's z component × 24
 *                       azimuth sectors. Drawn as a Lambert azimuthal equal-area disk (radius = sin(tilt / 2)), so every
 *                       cell is the same share of the sphere and of the disk: a big wedge is a big piece of the world,
 *                       never a stretched pole. It is the grid membership.json indexes, so a click asks who points there.
 *   grid: tilt_azimuth  V3's 36 × 18 tilt × azimuth grid, radius = tilt (equidistant).
 * Each cell is its annular sector, coloured under the dashboard's settings; white = never pointed there; the 90° ring
 * (horizontal) is dashed. Hover reads the cell; under a cell query (query.js) the answer's cells keep their colour.
 *
 *   coverage:
 *     reach: 180            the outer ring in degrees (tilt_azimuth only; default the grid's own top, 180°)
 *     compact: true         the landing's size: a shorter lead
 *
 * Prior art: traj_compare's coverage page `tilt-map`; a stereonet / sky plot (azimuth × elevation); Lambert's
 * equal-area projection (the Schmidt net of structural geology); V5's and V6's direction discs. STOCK PARTS: none.
 */
import {
  Color, esc, settingsOf, scaleTitle, tok, rgbOf, fmt, count, clamp, canvas, font, colorbar, legend, readout, hover,
  rows as rowsOf, block, emptyHtml, room, Query, gridKey, hitLayer, wrapCanvas, askCell, askLine, queryLegend, fade,
  tiltOfRing, clean,
} from './kit.js';
import css from './coverage-css.js';

export { css };

export function options() {
  return [{ type: 'slider', key: 'coverage.reach', displayName: 'Outer ring (°)', min: 30, max: 180, step: 10 }];
}

function css3(rgb) { return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; }

export default class CoveragePolarView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.classList.add('dv-coverage');
    this.tip = readout(el);
    this.width = 0;
    this.ro = new ResizeObserver(() => {
      const w = Math.floor(el.clientWidth);
      if (this.input && w > 0 && Math.abs(w - this.width) > 2) this.draw();
    });
    this.ro.observe(el);
    this.onQuery = () => { if (this.input) this.draw(); };
    Query.addEventListener('change', this.onQuery);
  }

  update(input) { this.input = input; this.draw(); }

  draw() {
    const el = this.el;
    const width = Math.floor(el.clientWidth);
    this.width = width;
    if (!width || !this.input) return;
    for (const node of [...el.children]) if (!node.classList.contains('dv-coverage-tip')) node.remove();
    const r = rowsOf(this.input)[0];
    if (!r) { el.insertAdjacentHTML('afterbegin', emptyHtml('No direction grid matches this view.')); return; }
    const input = this.input;
    const b = block(input);
    const t = tok(input);
    const settings = settingsOf(input);
    const enough = r.enough || 10;
    const deg = r.y_scale;
    const sphere = r.grid === 'sphere';
    const compact = !!b.compact;
    const reach = sphere ? r.y_hi : clamp((b.reach || r.y_hi * deg) / deg, 0.1, r.y_hi);
    const scaled = Color.scale(r.samples, settings.scale, { enough });
    const emptyRgb = rgbOf(t.bg);
    const key = gridKey(r);
    const head = document.createElement('div');
    head.className = 'dv-coverage-head';
    const ref = Array.isArray(r.reference) ? r.reference : [0, 0, -1];
    const down = ref.join(', ') === '0, 0, -1' ? 'straight down, −z' : esc(ref.join(', '));
    head.innerHTML = compact
      ? `<p class="dv-coverage-lead">Centre = ${down}; ring = tilt; angle = which way it leans. ${r.visited_pct != null ? `<b>${Math.round(r.visited_pct)} %</b> of directions` : ''}</p>`
      : `<p class="dv-coverage-lead">Centre = the tool along the reference (${down}); ring = how far it tilts; angle = which way it leans in base XY${sphere ? '; equal-area: every cell is the same share of the sphere' : ''}${r.visited_pct != null ? ` · <b>${Math.round(r.visited_pct)} %</b> of directions visited` : ''}</p>`;
    el.prepend(head);
    const leg = legend([
      { kind: 'ramp', label: compact ? `colour = samples (${settings.scale})` : `colour = samples pointing that way (${scaleTitle(settings.scale, enough)})` },
      { kind: 'empty', label: compact ? 'white = never' : 'white = never pointed there' },
      { kind: 'dash', colour: t.fg, label: '90° = tool horizontal' },
      sphere && !compact ? { kind: 'text', label: 'equal-area cells (Lambert): radius = sin(tilt / 2)' } : null,
      ...(key && Query.indexed(key) ? queryLegend(t, compact).map((it) => ({ ...it, bg: emptyRgb })) : []),
      key && Query.indexed(key) && !Query.active ? { kind: 'text', label: 'click a cell: who points there' } : null,
    ], settings.ramp);
    el.append(leg);
    // the head and legend are measured first: the disk gets the panel's height that is left
    const availH = room(el, 450) - head.offsetHeight - leg.offsetHeight - 24;
    const size = clamp(Math.min(width - 110, availH), 170, 520);
    const { canvas: c, g } = canvas(size, size, 'dv-coverage-heat');
    c.setAttribute('data-cov-heat', '');
    const cx = size / 2; const cy = size / 2; const R = size / 2 - 22;
    // tilt (rad) → radius: equal-area for the sphere (Lambert: sin(tilt / 2)), equidistant for tilt × azimuth
    const rad = (tilt) => (sphere ? R * Math.sin(Math.min(tilt, Math.PI) / 2) : (tilt / reach) * R);
    const empty = css3(emptyRgb);
    const answer = key ? Query.visited(key) : null;
    // the lattice: sphere cells are ring k (tilt band by z) × sector s; tilt_azimuth cells are azimuth i × tilt j
    const nA = sphere ? r.sectors || r.nx : r.nx;
    const nT = sphere ? r.rings || r.ny : r.ny;
    const da = (r.x_hi - r.x_lo) / nA;
    const idxOf = (ia, it) => (sphere ? it * nA + ia : ia * nT + it);
    const tiltLo = (it) => (sphere ? (tiltOfRing(it, nT) * Math.PI) / 180 : r.y_lo + it * ((r.y_hi - r.y_lo) / nT));
    const ringR = (it) => (sphere ? R * Math.sqrt(Math.min(1, it / nT)) : rad(tiltLo(it)));
    // WHY the disk is filled first: an unvisited cell must read as the surface, not as a gap in a grey wheel
    g.fillStyle = empty; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
    const sector = (ia, it) => {
      const a0 = r.x_lo + ia * da; const a1 = a0 + da;
      g.beginPath();
      // canvas y grows down; base +y is up, so the angle is negated
      g.arc(cx, cy, Math.min(ringR(it + 1), R), -a0, -a1, true);
      g.arc(cx, cy, ringR(it), -a1, -a0, false);
      g.closePath();
    };
    for (let ia = 0; ia < nA; ia++) {
      for (let it = 0; it < nT; it++) {
        if (tiltLo(it) >= reach) continue;
        const k = idxOf(ia, it);
        const v = scaled.t[k];
        if (!(v >= 0)) continue;
        let rgb = settings.ramp(v);
        if (answer && !answer.has(k)) rgb = fade(rgb, emptyRgb);
        g.fillStyle = css3(rgb);
        sector(ia, it);
        g.fill();
      }
    }
    if (sphere) {
      // the equal-area lattice itself, faint: each wedge the same area
      g.save(); g.strokeStyle = t.bg; g.lineWidth = 0.6; g.globalAlpha = 0.55;
      for (let it = 1; it < nT; it++) { g.beginPath(); g.arc(cx, cy, ringR(it), 0, Math.PI * 2); g.stroke(); }
      g.restore();
    }
    g.strokeStyle = t.border; g.lineWidth = 1;
    g.font = font(t, 10); g.fillStyle = t.muted; g.textAlign = 'left'; g.textBaseline = 'middle';
    const rings = sphere ? [45, 90, 135] : [];
    if (!sphere) for (let ring = 30; ring <= reach * deg + 0.1; ring += 30) rings.push(ring);
    for (const ring of rings) {
      const rr = rad(ring / deg);
      g.save();
      g.setLineDash(ring === 90 ? [4, 3] : []);
      g.strokeStyle = ring === 90 ? t.fg : t.border;
      g.globalAlpha = ring === 90 ? 0.55 : 1;
      g.beginPath(); g.arc(cx, cy, rr, 0, Math.PI * 2); g.stroke();
      g.restore();
      const lx = cx + rr * Math.cos(-Math.PI / 4) + 3; const ly = cy + rr * Math.sin(-Math.PI / 4) - 5;
      // WHY a halo: the ring labels sit on coloured cells; the surface colour around each glyph keeps them legible
      g.save(); g.strokeStyle = t.bg; g.lineWidth = 3; g.lineJoin = 'round'; g.strokeText(`${ring}°`, lx, ly); g.restore();
      g.fillText(`${ring}°`, lx, ly);
    }
    g.strokeStyle = t.muted; g.globalAlpha = 0.4;
    g.beginPath(); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
    g.globalAlpha = 1;
    // the asked cells, framed
    for (const chip of key ? Query.on(key) : []) {
      const it = Math.floor(chip.cell / nA); const ia = chip.cell % nA;
      g.save(); sector(ia, it);
      g.lineWidth = 3; g.strokeStyle = t.bg; g.stroke();
      g.lineWidth = 1.6; g.strokeStyle = t.fg; g.stroke();
      g.restore();
    }
    g.font = font(t, 11, 600); g.fillStyle = t.fg; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('+x', cx + R + 12, cy); g.fillText('−x', cx - R - 12, cy); g.fillText('+y', cx, cy - R - 11); g.fillText('−y', cx, cy + R + 11);
    const cellAt = (px, py) => {
      const ux = px - cx; const uy = cy - py;
      const dist = Math.hypot(ux, uy);
      if (dist > R) return -1;
      const az = Math.atan2(uy, ux);
      const ia = clamp(Math.floor((az - r.x_lo) / da), 0, nA - 1);
      const it = sphere ? clamp(Math.floor((dist / R) ** 2 * nT), 0, nT - 1)
        : clamp(Math.floor((((dist / R) * reach) - r.y_lo) / ((r.y_hi - r.y_lo) / nT)), 0, nT - 1);
      return idxOf(ia, it);
    };
    const find = (px, py) => {
      const idx = cellAt(px, py);
      if (idx < 0) return null;
      const it = sphere ? Math.floor(idx / nA) : idx % nT;
      const ia = sphere ? idx % nA : Math.floor(idx / nT);
      const t0 = tiltLo(it) * deg; const t1 = (it + 1 >= nT ? r.y_hi : tiltLo(it + 1)) * deg;
      let html = `tilt ${fmt(clean(t0))}° … ${fmt(clean(t1))}° from straight down${sphere ? ' (an equal-area ring)' : ''}<br>leaning toward azimuth ${fmt(clean((r.x_lo + ia * da) * deg))}° … ${fmt(clean((r.x_lo + (ia + 1) * da) * deg))}°<br><b>${count(r.samples[idx])}</b> samples`;
      if (key && Query.indexed(key)) html += askLine(key, idx, r.samples[idx] > 0);
      return html;
    };
    const wrap = wrapCanvas(c);
    if (key && Query.indexed(key)) {
      hitLayer(wrap, { x: cx - R, y: cy - R, w: 2 * R, h: 2 * R }, 0, 0, {
        id: key, tip: this.tip, find, round: true, label: 'tool directions: click a cell to ask who points there',
        click: (px, py) => { const idx = cellAt(px, py); if (idx >= 0) askCell(this.el, r, idx, !(r.samples[idx] > 0)); },
      });
    } else {
      hover(c, this.tip, find);
    }
    const row = document.createElement('div');
    row.className = 'dv-coverage-heatrow';
    row.append(wrap, colorbar(scaled, 'samples per cell', size - 60, settings.ramp));
    head.after(row);
  }

  selected() {}

  destroy() { this.ro.disconnect(); Query.removeEventListener('change', this.onQuery); }
}
