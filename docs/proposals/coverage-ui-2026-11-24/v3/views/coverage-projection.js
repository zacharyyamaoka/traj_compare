/* type: coverage-projection — a path's footprint seen from the faces, pixel per pixel (PROPOSED-CONTRACT.md §52.3).
 *
 * Reads projection rows (one row = one face: u / v axis names, origin, shape, pixel size and list cells of samples,
 * distinct paths (Strava's rule: a pixel's count is how many trajectories crossed it, not how long one sat there),
 * max speed and a reachable mask) and draws every row side by side at ONE metric scale (a metre is the same length in
 * every panel), under the dashboard's colour settings. Reachable but never visited is the surface colour (white); a
 * pixel the robot cannot reach is grey; the axes are in mm in the frame the rows name.
 *
 *   coverage:
 *     value: samples | paths | max_speed     what the colour counts (default samples); the figure's own switch writes it
 *     overlay: [[x, y, z], …]                (a host's, e.g. the drill's) one path drawn over the map in the accent colour;
 *                                            with `muted: true` the map itself draws in grey so the path reads first
 *
 * Prior art: Strava's global heatmap (distinct activities per pixel); traj_compare's coverage page `projections` /
 * `tool-speed`; Rerun's 2-D views. STOCK PARTS: none (canvas 2D, one ImageData per face).
 */
import {
  Color, esc, settingsOf, scaleTitle, tok, rgbOf, fmt, count, withUnit, clamp, canvas, axes, heatImage, drawImage,
  frame, colorbar, legend, readout, hover, rows as rowsOf, block, emptyHtml, room,
} from './kit.js';
import css from './coverage-css.js';

export { css };

export function options() {
  return [{ type: 'dropdown', key: 'coverage.value', displayName: 'Colour =', options: { samples: 'samples per pixel', paths: 'trajectories per pixel', max_speed: 'max tool speed' }, default: 'samples' }];
}

const WORD = { samples: 'samples in the pixel', paths: 'distinct trajectories through the pixel (Strava)', max_speed: 'max tool speed in the pixel' };
const BAR = { samples: 'samples per pixel', paths: 'trajectories per pixel', max_speed: 'max tool speed (m/s)' };
const AXIS = { x: 0, y: 1, z: 2 };

export default class CoverageProjectionView {
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
    const list = rowsOf(this.input);
    if (!list.length) { el.insertAdjacentHTML('afterbegin', emptyHtml('No projection matches this view.')); return; }
    const input = this.input;
    const b = block(input);
    const t = tok(input);
    const settings = settingsOf(input);
    const value = b.value || 'samples';
    const muted = !!b.muted;
    const overlay = Array.isArray(b.overlay) ? b.overlay : null;
    const enough = list[0].enough || 10;

    const head = document.createElement('div');
    head.className = 'dv-coverage-head';
    const lead = document.createElement('p');
    lead.className = 'dv-coverage-lead';
    lead.innerHTML = muted ? `Frame <b>${esc(list[0].frame)}</b>, ${Math.round(list[0].pixel_m * 1000)} mm pixels: every trajectory in grey, this one on top`
      : `Frame <b>${esc(list[0].frame)}</b>, ${Math.round(list[0].pixel_m * 1000)} mm pixels, every view at one scale`;
    head.append(lead);
    if (!muted && b.switch !== false) {
      const choices = [['samples', 'samples'], ['paths', 'trajectories'], ['max_speed', 'max speed']];
      head.insertAdjacentHTML('beforeend', `<span class="dv-coverage-switch"><span class="dv-coverage-seg-label">colour =</span><span class="dv-coverage-seg" role="group" aria-label="What the colour counts">${choices.map(([v, l]) => `<button type="button" data-value="${v}" aria-pressed="${v === value}">${esc(l)}</button>`).join('')}</span></span>`);
      head.querySelector('.dv-coverage-seg').addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-value]');
        if (btn && btn.dataset.value !== value) this.host.setView({ coverage: { ...b, value: btn.dataset.value } });
      });
    }
    el.prepend(head);

    // WHY one scale for all faces: the same metre is the same length everywhere, so the three read as one object
    const cbW = muted ? 0 : 100;
    const margin = { l: 50, r: 10, t: 4, b: 36 };
    const gaps = list.length * (margin.l + margin.r) + (list.length - 1) * 8;
    const sumU = list.reduce((n, r) => n + r.nu, 0);
    const maxV = Math.max(...list.map((r) => r.nv));
    const availH = room(el, 460) - 100;
    const s = Math.max(0.5, Math.min((width - cbW - gaps - 4) / sumU, (availH - margin.t - margin.b) / maxV));
    const values = list.map((r) => r[value] || r.samples);
    const all = values.flat().map((v) => (v === null ? 0 : v));
    const scaled = Color.scale(all, value === 'max_speed' ? (settings.scale === 'enough' ? 'linear' : settings.scale) : settings.scale, { enough });
    const grey = (tt) => { const v = Math.round(225 - 120 * tt); return [v, v, v]; };
    const ramp = muted ? grey : settings.ramp;
    const empty = rgbOf(t.bg);
    const strip = document.createElement('div');
    strip.className = 'dv-coverage-proj';
    let offset = 0;
    let plotH = 0;
    list.forEach((r, k) => {
      const tt = scaled.t.subarray(offset, offset + values[k].length);
      offset += values[k].length;
      const w = Math.round(r.nu * s); const h = Math.round(r.nv * s);
      plotH = Math.max(plotH, h);
      const { canvas: c, g } = canvas(w + margin.l + margin.r, h + margin.t + margin.b, 'dv-coverage-heat');
      c.setAttribute('data-cov-heat', '');
      const box = { x: margin.l, y: margin.t, w, h };
      const reach = Array.isArray(r.reachable) ? r.reachable : null;
      drawImage(g, heatImage(r.nu, r.nv, tt, ramp, empty, reach ? (idx) => !reach[idx] : null), box);
      frame(g, box, t.border, 1);
      const mm = 1000;
      const u = { lo: r.origin_u * mm, hi: (r.origin_u + r.nu * r.pixel_m) * mm, label: `${r.u} (mm)` };
      const v = { lo: r.origin_v * mm, hi: (r.origin_v + r.nv * r.pixel_m) * mm, label: `${r.v} (mm)`, offset: 40 };
      axes(g, t, box, u, v);
      if (overlay && overlay.length) {
        const iu = AXIS[r.u]; const iv = AXIS[r.v];
        g.save();
        g.strokeStyle = t.accent; g.lineWidth = 2; g.lineJoin = 'round';
        g.beginPath();
        overlay.forEach((p, n) => {
          const px = box.x + ((p[iu] * mm - u.lo) / (u.hi - u.lo)) * box.w;
          const py = box.y + box.h - ((p[iv] * mm - v.lo) / (v.hi - v.lo)) * box.h;
          if (n === 0) g.moveTo(px, py); else g.lineTo(px, py);
        });
        g.stroke();
        const p0 = overlay[0];
        g.fillStyle = t.accent;
        g.beginPath();
        g.arc(box.x + ((p0[iu] * mm - u.lo) / (u.hi - u.lo)) * box.w, box.y + box.h - ((p0[iv] * mm - v.lo) / (v.hi - v.lo)) * box.h, 3.5, 0, Math.PI * 2);
        g.fill();
        g.restore();
      }
      hover(c, this.tip, (px, py) => {
        if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
        const i = clamp(Math.floor(((px - box.x) / box.w) * r.nu), 0, r.nu - 1);
        const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * r.nv), 0, r.nv - 1);
        const idx = i * r.nv + j;
        const ua = (r.origin_u + i * r.pixel_m) * mm; const va = (r.origin_v + j * r.pixel_m) * mm;
        let html = `${esc(r.u)} ${fmt(ua)} … ${fmt(ua + r.pixel_m * mm)} mm<br>${esc(r.v)} ${fmt(va)} … ${fmt(va + r.pixel_m * mm)} mm<br>`;
        if (reach && !reach[idx]) return `${html}not reachable`;
        html += `<b>${count(r.samples[idx])}</b> samples · <b>${count(r.paths[idx])}</b> trajectories`;
        if (r.max_speed && r.max_speed[idx] !== null) html += `<br>max tool speed ${withUnit(r.max_speed[idx], 'm/s')}`;
        return html;
      });
      const panel = document.createElement('div');
      panel.innerHTML = `<div class="dv-coverage-proj-title" style="padding-left:${margin.l}px"><b>${esc(r.title)}</b> (${esc(r.u)}, ${esc(r.v)})${muted ? '' : ` · ${count(r.pixels)} pixels`}</div>`;
      panel.append(c);
      strip.append(panel);
    });
    if (!muted) strip.append(colorbar(scaled, BAR[value], Math.max(80, plotH), ramp));
    el.insertBefore(strip, head.nextSibling);
    const reachable = list.some((r) => Array.isArray(r.reachable));
    el.append(legend(muted ? [
      { kind: 'path', colour: t.accent, label: 'this trajectory (dot = its start)' },
      { kind: 'fill', colour: 'rgb(150,150,150)', label: 'every trajectory in the set (darker = more samples)' },
      reachable ? { kind: 'outside', label: 'grey = not reachable' } : null,
    ] : [
      { kind: 'ramp', label: `colour = ${WORD[value]} (${scaleTitle(settings.scale, enough)})` },
      { kind: 'empty', label: reachable ? 'white = reachable, never visited' : 'white = never visited' },
      reachable ? { kind: 'outside', label: 'grey = not reachable' } : null,
    ], ramp));
  }

  selected() {}

  destroy() { this.ro.disconnect(); }
}
