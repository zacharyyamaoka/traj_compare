/* Summary-view layout proposals (2026-11-19) — shared PROTOTYPE computation over the SIMULATED fixture.
   Everything here is derived in the browser from window.FIXTURE (fixture.py → fixture.json); nothing is invented.
   - error = target − run in degrees, the target interpolated onto the run's own samples (never extrapolated)
   - FB share = Σ|τ_fb| / (Σ|τ_ff| + Σ|τ_fb|) over the run's samples (CONTRACT.md)
   - drive gap = τ_cmd − τ_applied; saturation = |τ_cmd| at the fixture's max_torque_nm
   - bands across repeats are taken on the target's time grid (each run's series resampled onto it)
   This is a prototype computation, not traj_compare's analysis.py. */
(function () {
  'use strict';
  const F = window.FIXTURE;
  const DEG = 180 / Math.PI;
  const TC = (window.TC = { F, DEG });
  TC.joints = F.joints.slice();
  TC.maxTorque = F.max_torque_nm.slice();
  TC.L1 = 0.30; TC.L2 = 0.25;
  TC.C = { sim: '#6f6e69', v1: '#7c5cc4', v2: '#0f9d8a', ff: '#3b82f6', fb: '#f97316', gap: '#b4b3ac', target: '#8a8983',
           warn: '#d79818', bad: '#c74434', ok: '#2f9e44', action: '#2a78d6', ink: '#22211f' };
  TC.GROUPS = [
    { key: 'sim', label: 'Sim (ideal plant)', short: 'sim', color: TC.C.sim },
    { key: 'v1', label: 'ff v1 nominal', short: 'ff v1', color: TC.C.v1 },
    { key: 'v2', label: 'ff v2 calibrated', short: 'ff v2', color: TC.C.v2 },
  ];
  TC.group = (key) => TC.GROUPS.find((g) => g.key === key);

  // ---------- math ----------
  function resample(xs, ys, xq) {
    // linear interpolation of (xs, ys) at xq; null outside [xs0, xsN] or where ys is null
    const out = new Array(xq.length);
    let k = 0;
    const n = xs.length;
    for (let i = 0; i < xq.length; i++) {
      const x = xq[i];
      if (x < xs[0] - 1e-9 || x > xs[n - 1] + 1e-9) { out[i] = null; continue; }
      while (k < n - 2 && xs[k + 1] < x) k++;
      const x0 = xs[k], x1 = xs[k + 1];
      const y0 = ys[k], y1 = ys[k + 1];
      if (y0 == null || y1 == null) { out[i] = null; continue; }
      const w = x1 === x0 ? 0 : Math.min(1, Math.max(0, (x - x0) / (x1 - x0)));
      out[i] = y0 + (y1 - y0) * w;
    }
    return out;
  }
  TC.resample = resample;
  function quantile(sorted, p) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * p, lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  TC.quantile = quantile;
  TC.median = (values) => quantile(values.filter((v) => v != null).slice().sort((a, b) => a - b), 0.5);
  TC.summary = function (values) {
    const s = values.filter((v) => v != null && isFinite(v)).slice().sort((a, b) => a - b);
    if (!s.length) return null;
    const mean = s.reduce((a, b) => a + b, 0) / s.length;
    const sd = s.length > 1 ? Math.sqrt(s.reduce((a, b) => a + (b - mean) ** 2, 0) / (s.length - 1)) : 0;
    return { n: s.length, min: s[0], p5: quantile(s, 0.05), p25: quantile(s, 0.25), p50: quantile(s, 0.5), p75: quantile(s, 0.75),
             p95: quantile(s, 0.95), max: s[s.length - 1], mean, sd, values: s };
  };
  // per-sample percentile bands across runs (arrays on one grid)
  TC.band = function (arrays) {
    const n = arrays.length ? arrays[0].length : 0;
    const keys = ['min', 'p5', 'p25', 'p50', 'p75', 'p95', 'max'];
    const out = {}; keys.forEach((k) => (out[k] = new Array(n)));
    const col = [];
    for (let i = 0; i < n; i++) {
      col.length = 0;
      for (const a of arrays) { const v = a[i]; if (v != null) col.push(v); }
      if (!col.length) { keys.forEach((k) => (out[k][i] = null)); continue; }
      col.sort((a, b) => a - b);
      out.min[i] = col[0]; out.max[i] = col[col.length - 1];
      out.p5[i] = quantile(col, 0.05); out.p25[i] = quantile(col, 0.25); out.p50[i] = quantile(col, 0.5);
      out.p75[i] = quantile(col, 0.75); out.p95[i] = quantile(col, 0.95);
    }
    return out;
  };
  // TensorBoard's debiased exponential moving average
  TC.smooth = function (ys, weight) {
    if (!weight) return ys;
    let last = 0, count = 0;
    return ys.map((y) => {
      if (y == null) return null;
      last = last * weight + (1 - weight) * y; count++;
      const debias = 1 - Math.pow(weight, count);
      return last / debias;
    });
  };
  function rolling(arr, half) {
    // centred moving average, window 2·half+1, shortened at the ends
    const n = arr.length, pre = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) pre[i + 1] = pre[i] + arr[i];
    const out = new Array(n);
    for (let i = 0; i < n; i++) { const a = Math.max(0, i - half), b = Math.min(n, i + half + 1); out[i] = (pre[b] - pre[a]) / (b - a); }
    return out;
  }

  // ---------- targets + runs ----------
  TC.targets = F.targets.map((t, index) => ({ name: t.name, title: t.title, description: t.description, t: t.t, q: t.q, tau: t.tau,
                                             duration: t.t[t.t.length - 1], index, runs: [] }));
  TC.target = (name) => TC.targets.find((t) => t.name === name);
  const J = TC.joints.length;

  function computeRun(run, target) {
    const r = run.raw, t = r.t, n = t.length;
    run.stats = [];
    run.err = [];
    let allE2 = 0, allN = 0, allMax = 0, allFF = 0, allFB = 0, allGap2 = 0, allSat = 0, allPeak = 0, allGapAbs = 0;
    for (let j = 0; j < J; j++) {
      const tq = resample(target.t, target.q[j], t);
      const ttau = resample(target.t, target.tau[j], t);
      const e = tq.map((v, k) => (v == null ? null : (v - r.q[j][k]) * DEG));
      run.err.push(e);
      let e2 = 0, ne = 0, emax = 0, sff = 0, sfb = 0, ff2 = 0, fb2 = 0, cmd2 = 0, app2 = 0, gap2 = 0, gapAbs = 0, tc2 = 0, ntc = 0, peak = 0, sat = 0;
      const lim = TC.maxTorque[j] - 1e-3;
      for (let k = 0; k < n; k++) {
        const ek = e[k];
        if (ek != null) { e2 += ek * ek; ne++; if (Math.abs(ek) > emax) emax = Math.abs(ek); }
        const ff = r.tau_ff[j][k], fb = r.tau_fb[j][k], cmd = r.tau_cmd[j][k], app = r.tau[j][k];
        sff += Math.abs(ff); sfb += Math.abs(fb);
        ff2 += ff * ff; fb2 += fb * fb; cmd2 += cmd * cmd; app2 += app * app;
        gap2 += (cmd - app) ** 2; gapAbs += Math.abs(cmd - app);
        if (ttau[k] != null) { tc2 += (ttau[k] - cmd) ** 2; ntc++; }
        if (Math.abs(cmd) > peak) peak = Math.abs(cmd);
        if (Math.abs(cmd) >= lim) sat++;
      }
      run.stats.push({
        rmsErr: Math.sqrt(e2 / Math.max(1, ne)), maxErr: emax, fbShare: sff + sfb > 0 ? sfb / (sff + sfb) : null,
        ffRms: Math.sqrt(ff2 / n), fbRms: Math.sqrt(fb2 / n), cmdRms: Math.sqrt(cmd2 / n), appliedRms: Math.sqrt(app2 / n),
        gapRms: Math.sqrt(gap2 / n), tgtCmdRms: ntc ? Math.sqrt(tc2 / ntc) : null, peakCmd: peak, satFrac: sat / n,
        ffMav: sff / n, fbMav: sfb / n, gapMav: gapAbs / n,
      });
      allE2 += e2; allN += ne; allMax = Math.max(allMax, emax); allFF += sff; allFB += sfb; allGap2 += gap2; allGapAbs += gapAbs;
      allSat += sat; allPeak = Math.max(allPeak, peak);
    }
    // index J = all joints pooled
    run.stats.push({
      rmsErr: Math.sqrt(allE2 / Math.max(1, allN)), maxErr: allMax, fbShare: allFF + allFB > 0 ? allFB / (allFF + allFB) : null,
      gapRms: Math.sqrt(allGap2 / (n * J)), satFrac: allSat / (n * J), peakCmd: allPeak,
      ffMav: allFF / (n * J), fbMav: allFB / (n * J), gapMav: allGapAbs / (n * J),
      ffRms: null, fbRms: null, cmdRms: null, appliedRms: null, tgtCmdRms: null,
    });
    run._grid = {};
  }

  TC.runs = F.runs.map((r, order) => {
    const target = TC.target(r.target);
    const group = r.kind === 'sim' ? 'sim' : r.tags.ff_model.startsWith('v2') ? 'v2' : 'v1';
    const short = r.name.split('/')[1];
    const num = short === 'sim' ? 0 : +short.split('-')[1];
    const run = { id: r.name, short, num, order, title: r.title, target: r.target, kind: r.kind, group, date: r.tags.date, tags: r.tags, raw: r };
    computeRun(run, target);
    target.runs.push(run);
    return run;
  });
  TC.run = (id) => TC.runs.find((r) => r.id === id);
  TC.dates = [...new Set(TC.runs.map((r) => r.date))].sort();

  // joint index: 0..J-1, or J = all joints pooled
  TC.jointLabel = (j) => (j >= J ? 'all joints' : TC.joints[j]);
  TC.stat = (run, j, key) => run.stats[Math.min(j, J)][key];

  // series on the target grid, memoised: err (°), fb, fbabs, ff, cmd, applied, gap (|cmd−applied|), share (rolling 0.2 s FB share)
  TC.series = function (run, kind, j) {
    const key = kind + ':' + j;
    if (run._grid[key]) return run._grid[key];
    const r = run.raw, target = TC.target(run.target);
    const js = j >= J ? [...Array(J).keys()] : [j];
    let src;
    const per = js.map((jj) => {
      if (kind === 'err') src = run.err[jj];
      else if (kind === 'fb') src = r.tau_fb[jj];
      else if (kind === 'fbabs') src = r.tau_fb[jj].map(Math.abs);
      else if (kind === 'ff') src = r.tau_ff[jj];
      else if (kind === 'cmd') src = r.tau_cmd[jj];
      else if (kind === 'applied') src = r.tau[jj];
      else if (kind === 'gap') src = r.tau_cmd[jj].map((c, k) => Math.abs(c - r.tau[jj][k]));
      else if (kind === 'share') {
        const fa = rolling(r.tau_ff[jj].map(Math.abs), 10), fbb = rolling(r.tau_fb[jj].map(Math.abs), 10);
        src = fa.map((a, k) => (a + fbb[k] > 1e-6 ? (100 * fbb[k]) / (a + fbb[k]) : null));
      }
      const xs = [], ys = [];
      src.forEach((v, k) => { if (v != null) { xs.push(r.t[k]); ys.push(v); } });
      return resample(xs, ys, target.t);
    });
    let out;
    if (per.length === 1) out = per[0];
    else if (kind === 'err') out = per[0].map((_, i) => { const v = per.map((p) => p[i]); return v.some((x) => x == null) ? null : Math.sqrt(v.reduce((a, b) => a + b * b, 0) / v.length); });
    else out = per[0].map((_, i) => { const v = per.map((p) => p[i]); return v.some((x) => x == null) ? null : v.reduce((a, b) => a + Math.abs(b), 0) / v.length; });
    run._grid[key] = out;
    return out;
  };
  TC.SERIES = {
    err: { label: 'Tracking error · target − run', unit: '°', fmt: (v) => v.toFixed(2) + '°' },
    fbabs: { label: 'Feedback torque |τ_fb|', unit: 'N·m', fmt: (v) => v.toFixed(2) + ' N·m' },
    share: { label: 'FB share, rolling 0.2 s', unit: '%', fmt: (v) => v.toFixed(0) + '%' },
    gap: { label: 'Drive gap |τ_cmd − τ_applied|', unit: 'N·m', fmt: (v) => v.toFixed(3) + ' N·m' },
    cmd: { label: 'Commanded τ_cmd', unit: 'N·m', fmt: (v) => v.toFixed(2) + ' N·m' },
  };

  // tool (L2 tip) position in mm on the grid, for ISO 9283 path repeatability
  TC.tipGrid = function (run) {
    if (run._grid.tip) return run._grid.tip;
    const target = TC.target(run.target), r = run.raw;
    const q1 = resample(r.t, r.q[0], target.t), q2 = resample(r.t, r.q[1], target.t);
    const x = q1.map((a, i) => (a == null || q2[i] == null ? null : 1000 * (TC.L1 * Math.cos(a) + TC.L2 * Math.cos(a + q2[i]))));
    const y = q1.map((a, i) => (a == null || q2[i] == null ? null : 1000 * (TC.L1 * Math.sin(a) + TC.L2 * Math.sin(a + q2[i]))));
    return (run._grid.tip = { x, y });
  };
  // ISO 9283 path repeatability RT = max over the path of (l̄ + 3·S_l), l = distance to the barycentre of the N repeats (mm)
  TC.pathRepeatability = function (runs) {
    if (runs.length < 3) return null;
    const tips = runs.map(TC.tipGrid);
    const n = tips[0].x.length;
    let worst = 0, worstI = 0;
    for (let i = 0; i < n; i++) {
      const pts = tips.map((tp) => [tp.x[i], tp.y[i]]).filter((p) => p[0] != null);
      if (pts.length < 3) continue;
      const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length, cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
      const l = pts.map((p) => Math.hypot(p[0] - cx, p[1] - cy));
      const lm = l.reduce((a, b) => a + b, 0) / l.length;
      const s = Math.sqrt(l.reduce((a, b) => a + (b - lm) ** 2, 0) / (l.length - 1));
      if (lm + 3 * s > worst) { worst = lm + 3 * s; worstI = i; }
    }
    return { rt: worst, at: TC.target(runs[0].target).t[worstI] };
  };

  // ---------- comparisons ----------
  TC.groupRuns = (target, key, keep) => target.runs.filter((r) => r.group === key && (!keep || keep(r)));
  // v1 vs v2 on one metric (lower is better): medians, relative change, probability of superiority over all run pairs
  TC.verdict = function (target, j, keep, key = 'rmsErr') {
    const a = TC.groupRuns(target, 'v1', keep), b = TC.groupRuns(target, 'v2', keep);
    const va = a.map((r) => TC.stat(r, j, key)), vb = b.map((r) => TC.stat(r, j, key));
    const res = { target, a, b, metric: key, hasBoth: a.length > 0 && b.length > 0 };
    res.medA = va.length ? TC.median(va) : null; res.medB = vb.length ? TC.median(vb) : null;
    const fa = a.map((r) => TC.stat(r, j, 'fbShare')), fbv = b.map((r) => TC.stat(r, j, 'fbShare'));
    res.fbA = fa.length ? TC.median(fa) : null; res.fbB = fbv.length ? TC.median(fbv) : null;
    if (!res.hasBoth) return res;
    let wins = 0;
    for (const x of vb) for (const y of va) wins += x < y ? 1 : x === y ? 0.5 : 0;
    res.pairs = va.length * vb.length; res.wins = wins; res.pSup = wins / res.pairs;
    res.delta = (res.medB - res.medA) / res.medA;
    res.winner = res.medB < res.medA ? 'v2' : 'v1';
    const p = Math.max(res.pSup, 1 - res.pSup);
    res.conf = p >= 0.9 ? 'high' : p >= 0.75 ? 'moderate' : 'low';
    res.overlap = !(Math.max(...vb) < Math.min(...va) || Math.max(...va) < Math.min(...vb));
    return res;
  };
  TC.confText = (v) => (v.hasBoth ? `${Math.round(v.winner === 'v2' ? v.wins : v.pairs - v.wins)} of ${v.pairs} run pairs · n ${v.b.length} vs ${v.a.length}` : '');
  // SPC individuals chart (I-MR): centre = mean, limits = mean ± 2.66·MR̄
  TC.imr = function (values) {
    const v = values.filter((x) => x != null);
    if (v.length < 2) return null;
    const mean = v.reduce((a, b) => a + b, 0) / v.length;
    let mr = 0; for (let i = 1; i < v.length; i++) mr += Math.abs(v[i] - v[i - 1]);
    mr /= v.length - 1;
    return { mean, mr, ucl: mean + 2.66 * mr, lcl: Math.max(0, mean - 2.66 * mr) };
  };
  TC.encodingFor = (n, mode, threshold) => (mode === 'lines' ? 'lines' : mode === 'bands' ? (n >= 3 ? 'bands' : 'lines') : n <= threshold ? 'lines' : 'bands');

  // ---------- formatting ----------
  TC.deg = (v, d) => (v == null ? '—' : v.toFixed(d != null ? d : v < 10 ? 2 : 1) + '°');
  TC.pct = (v, d = 0) => (v == null ? '—' : (100 * v).toFixed(d) + '%');
  TC.nm = (v, d = 2) => (v == null ? '—' : v.toFixed(d) + ' N·m');
  TC.mm = (v, d = 1) => (v == null ? '—' : v.toFixed(d) + ' mm');
  TC.signedPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '−') + Math.abs(100 * v).toFixed(0) + '%');
  TC.shortDate = (d) => d.slice(5);
  TC.esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ---------- DOM ----------
  TC.el = function (tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) e.style.setProperty(sk, sv); else e.style[sk] = sv; }
      else if (k === 'text') e.textContent = v;
      else if (k === 'html') e.innerHTML = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    (children || []).forEach((c) => c != null && e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
    return e;
  };
  TC.store = {
    get(key, fallback) { try { const v = localStorage.getItem('tcs:' + key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; } },
    set(key, value) { try { localStorage.setItem('tcs:' + key, JSON.stringify(value)); } catch (e) { /* storage blocked: keep the in-memory state */ } },
  };
  // Draggable boundary with a remembered size; the panel folds (double-click the gutter or the fold button).
  TC.splitter = function ({ gutter, panel, key, side = 'left', min = 160, max = 640, size = 280, foldBtn, onResize }) {
    const vertical = side === 'top' || side === 'bottom';
    const prop = vertical ? 'height' : 'width';
    let cur = TC.store.get(key + ':size', size);
    let folded = TC.store.get(key + ':folded', false);
    const apply = () => {
      panel.style[prop] = cur + 'px';
      panel.classList.toggle('folded', folded);
      if (foldBtn) { foldBtn.textContent = folded ? (side === 'left' ? '»' : side === 'right' ? '«' : '▴') : (side === 'left' ? '«' : side === 'right' ? '»' : '▾');
                     foldBtn.title = folded ? 'Unfold panel' : 'Fold panel'; }
      if (onResize) onResize();
      window.dispatchEvent(new Event('tcs:layout'));
    };
    gutter.addEventListener('pointerdown', (ev) => {
      ev.preventDefault();
      // WHY no unfold here: a double-click starts with two pointerdowns; unfolding on press made the dblclick re-fold
      const start = vertical ? ev.clientY : ev.clientX, startSize = cur;
      gutter.classList.add('dragging'); document.body.classList.add('resizing'); if (vertical) document.body.classList.add('rows');
      gutter.setPointerCapture(ev.pointerId);
      const move = (e) => {
        const d = (vertical ? e.clientY : e.clientX) - start;
        if (Math.abs(d) < 3) return;
        folded = false; // dragging a folded boundary unfolds it
        const sign = side === 'left' || side === 'top' ? 1 : -1;
        cur = Math.max(min, Math.min(max, startSize + sign * d));
        apply();
      };
      const up = () => {
        gutter.classList.remove('dragging'); document.body.classList.remove('resizing', 'rows');
        gutter.removeEventListener('pointermove', move); gutter.removeEventListener('pointerup', up);
        TC.store.set(key + ':size', cur); TC.store.set(key + ':folded', folded);
      };
      gutter.addEventListener('pointermove', move); gutter.addEventListener('pointerup', up);
    });
    const toggle = () => { folded = !folded; TC.store.set(key + ':folded', folded); apply(); };
    gutter.addEventListener('dblclick', toggle);
    if (foldBtn) foldBtn.addEventListener('click', toggle);
    gutter.title = 'Drag to resize · double-click to fold';
    apply();
    return { toggle, get size() { return cur; }, get folded() { return folded; } };
  };

  // drill-down placeholder: #run/<target>/<run> (or #run/<target>/group/<key>) — in production, traj_compare's run view
  TC.drillHref = (target, what) => `#run/${target}/${what}`;
  function showDrill() {
    const h = decodeURIComponent(location.hash || '');
    if (!h.startsWith('#run/')) return;
    let toast = document.querySelector('.drill-toast');
    if (!toast) {
      toast = TC.el('div', { class: 'drill-toast' });
      document.body.appendChild(toast);
    }
    const parts = h.slice(5).split('/');
    const target = TC.target(parts[0]);
    const what = parts[1] === 'group' ? `${TC.group(parts[2]) ? TC.group(parts[2]).label : parts[2]} group` : parts.slice(1).join('/');
    toast.innerHTML = `Drill-down placeholder → run view of <b>${TC.esc(target ? target.title : parts[0])}</b> · <b>${TC.esc(what)}</b> &nbsp;<code>${TC.esc(h)}</code><span class="x" title="Dismiss">✕</span>`;
    toast.classList.add('show');
    toast.querySelector('.x').onclick = () => { toast.classList.remove('show'); history.replaceState(null, '', location.pathname + location.search); };
  }
  window.addEventListener('hashchange', showDrill);
  window.addEventListener('DOMContentLoaded', showDrill);
  TC.drill = (target, what) => { location.hash = TC.drillHref(target, what); };

  // tooltip
  let tipEl = null;
  TC.tip = function (ev, html) {
    if (!tipEl) { tipEl = TC.el('div', { class: 'tip' }); document.body.appendChild(tipEl); }
    if (!html) { tipEl.classList.remove('show'); return; }
    tipEl.innerHTML = html; tipEl.classList.add('show');
    const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
    if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
    tipEl.style.left = x + 'px'; tipEl.style.top = y + 'px';
  };

  TC.hexA = function (hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  // shade a group colour per run so few-N lines stay individually distinguishable
  TC.shade = function (hex, i, n) {
    const c = parseInt(hex.slice(1), 16);
    let r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
    const t = n <= 1 ? 0 : (i / (n - 1)) * 0.55 - 0.25; // −25 % darker … +30 % lighter
    const mix = (v) => Math.round(t < 0 ? v * (1 + t) : v + (255 - v) * t);
    return '#' + [mix(r), mix(g), mix(b)].map((v) => v.toString(16).padStart(2, '0')).join('');
  };

  // ---------- uPlot fan / lines chart ----------
  // layers: [{ key, color, label, mode: 'lines'|'bands', runs: [{ run, y }], dash }], overlay: [{ run, y, color }]
  TC.fanChart = function (host, { x, layers, overlay = [], height = 180, yFmt = (v) => v.toFixed(2), yUnit = '', readout, onPick, yRange, zeroLine }) {
    host.innerHTML = '';
    const data = [x], series = [{}], bands = [], meta = [null];
    const add = (y, s, m) => { data.push(y); series.push(Object.assign({ points: { show: false }, spanGaps: false }, s)); meta.push(m); return data.length - 1; };
    for (const L of layers) {
      if (!L.runs.length) continue;
      if (L.mode === 'bands') {
        const b = TC.band(L.runs.map((r) => r.y));
        const thin = { stroke: 'transparent', width: 0 };
        const iMax = add(b.max, thin, { L, role: 'max' }), iMin = add(b.min, thin, { L, role: 'min' });
        const i95 = add(b.p95, thin, { L, role: 'p95' }), i5 = add(b.p5, thin, { L, role: 'p5' });
        const i75 = add(b.p75, thin, { L, role: 'p75' }), i25 = add(b.p25, thin, { L, role: 'p25' });
        add(b.p50, { stroke: L.color, width: 1.8 }, { L, role: 'median', band: b });
        bands.push({ series: [iMax, iMin], fill: TC.hexA(L.color, 0.09) }, { series: [i95, i5], fill: TC.hexA(L.color, 0.14) },
                   { series: [i75, i25], fill: TC.hexA(L.color, 0.26) });
      } else {
        L.runs.forEach((r, i) => add(r.y, { stroke: L.dash ? L.color : TC.shade(L.color, i, L.runs.length), width: L.dash ? 1.3 : 1.25, dash: L.dash ? [5, 4] : undefined },
                                     { L, role: 'run', run: r.run }));
      }
    }
    for (const o of overlay) add(o.y, { stroke: o.color || TC.C.ink, width: o.width || 1.9, dash: o.dash }, { role: 'overlay', run: o.run });
    const axisFont = '10.5px -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif';
    const ax = { stroke: '#8a8983', font: axisFont, grid: { stroke: '#efeee9', width: 1 }, ticks: { stroke: '#e6e5e0', width: 1, size: 4 } };
    const opts = {
      width: Math.max(120, host.clientWidth), height, legend: { show: false },
      cursor: { drag: { x: true, y: false }, points: { show: false } },
      scales: { x: { time: false }, y: yRange ? { range: yRange } : { auto: true } },
      axes: [Object.assign({}, ax, { size: 26, values: (u, v) => v.map((s) => s + ' s') }),
             // tick labels carry as many decimals as the tick step needs, plus the unit
             Object.assign({}, ax, { size: 46, values: (u, v, ai, sp, incr) => { let d = 0; while (d < 4 && Math.abs(Math.round((incr || 1) * 10 ** d) - (incr || 1) * 10 ** d) > 1e-6) d++; return v.map((s) => s.toFixed(d) + yUnit); } })],
      series, bands,
      hooks: {
        setCursor: [(u) => {
          if (!readout) return;
          const i = u.cursor.idx;
          if (i == null) { readout.innerHTML = '&nbsp;'; return; }
          const parts = [`t ${x[i].toFixed(2)} s`];
          meta.forEach((m, k) => {
            if (!m) return;
            if (m.role === 'median' && data[k][i] != null) parts.push(`<span style="color:${m.L.color}">■</span> ${TC.esc(m.L.label)} median <b>${yFmt(data[k][i])}</b>`);
            if (m.role === 'overlay' && data[k][i] != null) parts.push(`${TC.esc(m.run.short)} <b>${yFmt(data[k][i])}</b>`);
          });
          const near = nearest(u, i);
          if (near && near.run) parts.push(`nearest <b>${TC.esc(near.run.short)}</b> ${yFmt(near.v)}`);
          readout.innerHTML = parts.join(' · ');
        }],
        draw: [(u) => {
          if (!zeroLine) return;
          const y0 = u.valToPos(0, 'y', true);
          if (y0 < u.bbox.top || y0 > u.bbox.top + u.bbox.height) return;
          const c = u.ctx; c.save(); c.strokeStyle = '#cfcec8'; c.lineWidth = 1; c.beginPath(); c.moveTo(u.bbox.left, y0); c.lineTo(u.bbox.left + u.bbox.width, y0); c.stroke(); c.restore();
        }],
      },
    };
    function nearest(u, i) {
      const top = u.cursor.top;
      if (top == null || top < 0) return null;
      const yv = u.posToVal(top, 'y');
      let best = null;
      meta.forEach((m, k) => {
        if (!m || (m.role !== 'run' && m.role !== 'overlay')) return;
        const v = data[k][i];
        if (v == null) return;
        const d = Math.abs(v - yv);
        if (!best || d < best.d) best = { d, run: m.run, v };
      });
      // inside a band → the band's group
      if (!best || best.d > (u.scales.y.max - u.scales.y.min) * 0.08) {
        for (let k = 0; k < meta.length; k++) {
          const m = meta[k];
          if (m && m.role === 'median') {
            const b = m.band; if (b.min[i] != null && yv >= b.min[i] && yv <= b.max[i]) return { layer: m.L, v: data[k][i] };
          }
        }
      }
      return best;
    }
    const u = new uPlot(opts, data, host);
    u.over.style.cursor = onPick ? 'pointer' : 'crosshair';
    if (onPick) {
      let down = null;
      u.over.addEventListener('mousedown', (e) => (down = [e.clientX, e.clientY]));
      u.over.addEventListener('click', (e) => {
        if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return; // a drag-zoom, not a pick
        const i = u.cursor.idx; if (i == null) return;
        const hit = nearest(u, i); if (hit) onPick(hit);
      });
    }
    u.over.addEventListener('dblclick', () => u.setScale('x', { min: x[0], max: x[x.length - 1] }));
    const ro = new ResizeObserver(() => { const w = Math.max(120, host.clientWidth); if (Math.abs(w - u.width) > 1) u.setSize({ width: w, height }); });
    ro.observe(host);
    u._ro = ro;
    return u;
  };
  TC.destroyChart = (u) => { if (u) { if (u._ro) u._ro.disconnect(); u.destroy(); } };

  // small SVG helpers
  TC.svg = function (tag, attrs, children) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
    (children || []).forEach((c) => c && e.appendChild(c));
    return e;
  };
  TC.sparkPath = function (ys, w, h, lo, hi) {
    let d = '', pen = false;
    ys.forEach((y, i) => {
      if (y == null) { pen = false; return; }
      const px = (i / (ys.length - 1)) * w, py = h - ((y - lo) / (hi - lo || 1)) * h;
      d += (pen ? 'L' : 'M') + px.toFixed(1) + ' ' + py.toFixed(1); pen = true;
    });
    return d;
  };
  TC.areaPath = function (lo, hi, w, h, vlo, vhi) {
    const pts = [];
    const n = lo.length;
    for (let i = 0; i < n; i++) if (hi[i] != null) pts.push([(i / (n - 1)) * w, h - ((hi[i] - vlo) / (vhi - vlo || 1)) * h]);
    for (let i = n - 1; i >= 0; i--) if (lo[i] != null) pts.push([(i / (n - 1)) * w, h - ((lo[i] - vlo) / (vhi - vlo || 1)) * h]);
    return pts.length ? 'M' + pts.map((p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L') + 'Z' : '';
  };

  // header with the SIMULATED badge
  TC.header = function (variantName, extra) {
    const nReal = TC.runs.filter((r) => r.kind === 'real').length;
    return TC.el('header', { class: 'tcs' }, [
      TC.el('div', { class: 'brand', html: 'traj_compare<span class="sep">/</span><span class="page">Summary</span>' }),
      TC.el('div', { class: 'context ell', title: F.robot, text: `${F.robot.split('(')[0].trim()} · ${TC.targets.length} targets · ${nReal} real + ${TC.runs.length - nReal} sim runs · ${TC.joints.join(', ')}` }),
      TC.el('div', { class: 'spacer' }),
      extra || null,
      TC.el('span', { class: 'variant-tag', text: variantName }),
      TC.el('span', { class: 'sim-badge', title: 'Every number on this page is computed from the shared SIMULATED fixture (fixture.py): a vertical 2R arm with moteus-style control. Not rig data.', text: 'SIMULATED fixture' }),
    ]);
  };
})();
