/* type: coverage-polar — a direction grid on a disk (PROPOSED-CONTRACT.md §52.4).
 *
 * Reads one grid row whose x is an angle around (azimuth, −180° … 180°) and whose y is the angle away from a reference
 * (tilt, 0° … 180°), and draws it as a polar disk seen from above: the centre is "along the reference" (for the tool,
 * straight down), the radius is the tilt, the angle is which way it leans in the base XY plane (+x right, +y up). Each
 * cell is its annular sector, coloured under the dashboard's settings; white = never pointed there. The 90° ring
 * (horizontal) is dashed. Hover reads the cell.
 *
 *   coverage:
 *     reach: 180            the outer ring in degrees (default: the grid's own top, 180°)
 *
 * Prior art: traj_compare's coverage page `tilt-map`; a stereonet / sky plot (azimuth × elevation); the polar
 * orientation plots of BAM Reach. STOCK PARTS: none (canvas 2D).
 */
import {
  Color, esc, settingsOf, scaleTitle, tok, rgbOf, fmt, count, clamp, canvas, font, colorbar, legend, readout, hover,
  rows as rowsOf, block, emptyHtml, room,
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
    const reach = clamp((b.reach || r.y_hi * deg) / deg, 0.1, r.y_hi);
    const scaled = Color.scale(r.samples, settings.scale, { enough });
    const availH = room(el, 450) - 76;
    const size = clamp(Math.min(width - 110, availH), 180, 520);
    const { canvas: c, g } = canvas(size, size, 'dv-coverage-heat');
    c.setAttribute('data-cov-heat', '');
    const cx = size / 2; const cy = size / 2; const R = size / 2 - 22;
    const rad = (tilt) => (tilt / reach) * R;
    const empty = css3(rgbOf(t.bg));
    const dx = (r.x_hi - r.x_lo) / r.nx; const dy = (r.y_hi - r.y_lo) / r.ny;
    // WHY the disk is filled first: an unvisited cell must read as the surface, not as a gap in a grey wheel
    g.fillStyle = empty; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
    for (let i = 0; i < r.nx; i++) {
      const a0 = r.x_lo + i * dx; const a1 = a0 + dx;
      for (let j = 0; j < r.ny; j++) {
        const t0 = r.y_lo + j * dy; const t1 = t0 + dy;
        if (t0 >= reach) continue;
        const v = scaled.t[i * r.ny + j];
        if (!(v >= 0)) continue;
        g.fillStyle = css3(settings.ramp(v));
        g.beginPath();
        // canvas y grows down; base +y is up, so the angle is negated
        g.arc(cx, cy, rad(Math.min(t1, reach)), -a0, -a1, true);
        g.arc(cx, cy, rad(t0), -a1, -a0, false);
        g.closePath();
        g.fill();
      }
    }
    g.strokeStyle = t.border; g.lineWidth = 1;
    g.font = font(t, 10); g.fillStyle = t.muted; g.textAlign = 'left'; g.textBaseline = 'middle';
    for (let ring = 30; ring <= reach * deg + 0.1; ring += 30) {
      g.save();
      g.setLineDash(ring === 90 ? [4, 3] : []);
      g.strokeStyle = ring === 90 ? t.fg : t.border;
      g.globalAlpha = ring === 90 ? 0.55 : 1;
      g.beginPath(); g.arc(cx, cy, rad(ring / deg), 0, Math.PI * 2); g.stroke();
      g.restore();
      const lx = cx + rad(ring / deg) * Math.cos(-Math.PI / 4) + 3; const ly = cy + rad(ring / deg) * Math.sin(-Math.PI / 4) - 5;
      // WHY a halo: the ring labels sit on coloured cells; the surface colour around each glyph keeps them legible
      g.save(); g.strokeStyle = t.bg; g.lineWidth = 3; g.lineJoin = 'round'; g.strokeText(`${ring}°`, lx, ly); g.restore();
      g.fillText(`${ring}°`, lx, ly);
    }
    g.strokeStyle = t.muted; g.globalAlpha = 0.4;
    g.beginPath(); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
    g.globalAlpha = 1;
    g.font = font(t, 11, 600); g.fillStyle = t.fg; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('+x', cx + R + 12, cy); g.fillText('−x', cx - R - 12, cy); g.fillText('+y', cx, cy - R - 11); g.fillText('−y', cx, cy + R + 11);
    hover(c, this.tip, (px, py) => {
      const ux = px - cx; const uy = cy - py;
      const dist = Math.hypot(ux, uy);
      if (dist > R) return null;
      const tilt = (dist / R) * reach;
      const az = Math.atan2(uy, ux);
      const i = clamp(Math.floor((az - r.x_lo) / dx), 0, r.nx - 1);
      const j = clamp(Math.floor((tilt - r.y_lo) / dy), 0, r.ny - 1);
      const idx = i * r.ny + j;
      return `tilt ${fmt((r.y_lo + j * dy) * deg)}° … ${fmt((r.y_lo + (j + 1) * dy) * deg)}°<br>leaning toward azimuth ${fmt((r.x_lo + i * dx) * deg)}° … ${fmt((r.x_lo + (i + 1) * dx) * deg)}°<br><b>${count(r.samples[idx])}</b> samples`;
    });
    const head = document.createElement('div');
    head.className = 'dv-coverage-head';
    const ref = Array.isArray(r.reference) ? r.reference : [0, 0, -1];
    head.innerHTML = `<p class="dv-coverage-lead">Centre = the tool along the reference (${ref.join(', ') === '0, 0, -1' ? 'straight down, −z' : esc(ref.join(', '))}); ring = how far it tilts; angle = which way it leans in base XY</p>`;
    const row = document.createElement('div');
    row.className = 'dv-coverage-heatrow';
    row.append(c, colorbar(scaled, 'samples per cell', size - 60, settings.ramp));
    el.prepend(head, row);
    el.append(legend([
      { kind: 'ramp', label: `colour = samples pointing that way (${scaleTitle(settings.scale, enough)})` },
      { kind: 'empty', label: 'white = never pointed there' },
      { kind: 'dash', colour: t.fg, label: '90° = tool horizontal' },
    ], settings.ramp));
  }

  selected() {}

  destroy() { this.ro.disconnect(); }
}
