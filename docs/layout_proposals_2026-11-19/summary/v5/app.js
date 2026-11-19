/* V5 · Run ledger — history first: every run in order (date, then run number; the fixture has no time of day), one
   control-chart lane per target (SPC individuals chart, I-MR limits per phase), the phase break where the feedforward
   model changed, and a ledger of runs on the left. Pick a run or phase: the drawer shows that phase's repeats over the
   trajectory. SIMULATED fixture; prototype stats. */
(function () {
  'use strict';
  const { el, svg } = TC;
  const S = {
    metric: TC.store.get('v5:metric', 'rmsErr'),
    joint: TC.store.get('v5:joint', 0),
    limits: TC.store.get('v5:limits', 'phase'),
    selected: TC.store.get('v5:selected', 'full-circle-slow|v2'),
    selRun: TC.store.get('v5:selRun', null),
    hover: null,
    threshold: 5,
  };
  const save = () => { for (const k of ['metric', 'joint', 'limits', 'selected', 'selRun']) TC.store.set('v5:' + k, S[k]); };
  const METRICS = {
    rmsErr: { label: 'RMS error', fmt: (v) => TC.deg(v), axis: (v) => +v.toFixed(2) + '°' },
    maxErr: { label: 'Max |error|', fmt: (v) => TC.deg(v), axis: (v) => +v.toFixed(2) + '°' },
    fbShare: { label: 'FB share', fmt: (v) => TC.pct(v), axis: (v) => Math.round(v * 100) + '%' },
    gapRms: { label: 'Drive gap RMS', fmt: (v) => TC.nm(v, 3), axis: (v) => +v.toFixed(3) + '' },
  };
  const val = (r) => TC.stat(r, S.joint, S.metric);
  function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x || 1))); const m = x / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p; }
  const reals = (t) => t.runs.filter((r) => r.kind === 'real').sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.num - b.num));

  // phases = consecutive runs with one ff model; limits per phase (or one set for the whole lane)
  function lane(t) {
    const runs = reals(t);
    const phases = [];
    runs.forEach((r, i) => {
      const last = phases[phases.length - 1];
      if (!last || last.group !== r.group) phases.push({ group: r.group, start: i, runs: [r] });
      else last.runs.push(r);
    });
    const whole = TC.imr(runs.map(val));
    phases.forEach((p) => { p.lim = S.limits === 'phase' ? TC.imr(p.runs.map(val)) || whole : whole; p.mean = p.runs.reduce((a, r) => a + val(r), 0) / p.runs.length; });
    // WHY only above-UCL is red: every metric here is lower-is-better, so a run below the LCL is unusually good (ringed grey)
    const out = new Set(), low = new Set();
    runs.forEach((r, i) => { const p = phases.find((ph) => i >= ph.start && i < ph.start + ph.runs.length); if (p.lim && val(r) > p.lim.ucl) out.add(r.id); if (p.lim && p.lim.lcl > 0 && val(r) < p.lim.lcl) low.add(r.id); });
    // Western Electric rule 2 (whole-lane limits): 6+ consecutive points on one side of the centre line = the process shifted
    const streaks = [];
    if (S.limits === 'lane' && whole) {
      let side = 0, start = 0;
      runs.forEach((r, i) => {
        const s = Math.sign(val(r) - whole.mean);
        if (s !== side) { if (side && i - start >= 6) streaks.push({ start, end: i - 1, side }); side = s; start = i; }
      });
      if (side && runs.length - start >= 6) streaks.push({ start, end: runs.length - 1, side });
    }
    const sim = t.runs.find((r) => r.kind === 'sim');
    return { t, runs, phases, out, low, streaks, sim, whole };
  }

  const app = document.getElementById('app');
  app.appendChild(TC.header('V5 · Run ledger'));
  const toolbar = el('div', { class: 'toolbar' });
  app.appendChild(toolbar);
  const split = el('div', { class: 'split-h' });
  const side = el('aside', { class: 'side ledger' });
  const foldBtn = el('button', { class: 'iconbtn' });
  side.append(el('div', { class: 'side-head' }, [el('span', { class: 'side-title', text: 'Ledger · every run in order' }), foldBtn, el('span', { class: 'vlabel', text: 'Ledger' })]));
  const ledgerBody = el('div', { class: 'side-body' });
  side.appendChild(ledgerBody);
  const gutter = el('div', { class: 'gutter' });
  const right = el('div', { class: 'rightcol' });
  split.append(side, gutter, right);
  app.appendChild(split);
  TC.splitter({ gutter, panel: side, key: 'v5:ledger', side: 'left', min: 220, max: 560, size: 300, foldBtn });
  const lanesBox = el('main', { class: 'lanes' });
  const rgutter = el('div', { class: 'gutter row' });
  const drawer = el('section', { class: 'side drawer' });
  const dFold = el('button', { class: 'iconbtn' });
  const dTitle = el('span', { class: 'side-title ell' });
  const dAct = el('span', { class: 'dact' });
  drawer.append(el('div', { class: 'side-head' }, [dFold, dTitle, dAct, el('span', { class: 'vlabel', text: 'Phase detail' })]));
  const dBody = el('div', { class: 'side-body dbody' });
  drawer.appendChild(dBody);
  right.append(lanesBox, rgutter, drawer);
  TC.splitter({ gutter: rgutter, panel: drawer, key: 'v5:drawer', side: 'bottom', min: 150, max: 480, size: 226, foldBtn: dFold });

  function seg(options, value, onPick) {
    const s = el('div', { class: 'seg' });
    options.forEach(([v, label, tip]) => s.appendChild(el('button', { class: v === value ? 'on' : '', title: tip || '', text: label, 'data-v': String(v), onclick: () => onPick(v) })));
    return s;
  }
  function renderToolbar() {
    toolbar.innerHTML = '';
    toolbar.append(
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Metric' }), seg(Object.entries(METRICS).map(([k, m]) => [k, m.label]), S.metric, (v) => { S.metric = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Joint' }), seg(TC.joints.map((j, i) => [i, j]).concat([[TC.joints.length, 'all']]), S.joint, (v) => { S.joint = v; save(); renderAll(); })]),
      el('span', { class: 'ctl', id: 'limits-ctl' }, [el('span', { class: 'lab', text: 'Limits' }), seg([['phase', 'Per phase', 'Centre line and ±2.66·MR̄ limits recomputed after every ff-model change'], ['lane', 'Whole lane', 'One set of limits over all runs; a run of 6+ points on one side flags a shift']], S.limits, (v) => { S.limits = v; save(); renderAll(); })]),
      el('span', { class: 'spacer' }),
      el('span', { class: 'legend' }, [el('span', { class: 'sw v1' }), 'ff v1 nominal', el('span', { class: 'sw v2' }), 'ff v2 calibrated', el('span', { class: 'lline' }), 'centre', el('span', { class: 'lline dashed' }), 'limits (I-MR)', el('span', { class: 'ldot bad' }), 'above upper limit']),
    );
  }

  // ---------- banner: what changed ----------
  function banner(lanes) {
    const box = el('div', { class: 'banner' });
    const changes = lanes.filter((L) => L.phases.length > 1);
    const outN = lanes.reduce((a, L) => a + L.out.size, 0);
    const first = changes.length ? changes[0].phases[1].runs[0] : null;
    box.appendChild(el('div', { class: 'bwhat' }, [el('span', { class: 'blab', text: 'What changed' }),
      first ? el('span', {}, [el('b', { text: 'ff v2 calibrated' }), ` from ${first.date}`]) : el('span', { text: 'no ff-model change in this history' })]));
    const items = el('div', { class: 'bitems' });
    for (const L of lanes) {
      const it = el('div', { class: 'bitem', onclick: () => { const p = L.phases[L.phases.length - 1]; S.selected = `${L.t.name}|${p.group}`; S.selRun = null; save(); renderAll(); }, title: 'Show this lane\'s latest phase below' });
      it.appendChild(el('span', { class: 'bt ell', title: L.t.title, text: L.t.title.replace('Full-circle probe · ', 'Full circle ') }));
      if (L.phases.length > 1) {
        const a = L.phases[L.phases.length - 2], b = L.phases[L.phases.length - 1];
        const d = (b.mean - a.mean) / a.mean;
        it.appendChild(el('span', { class: 'num ell', html: `<b>${TC.signedPct(d)}</b> mean ${METRICS[S.metric].label}` }));
        const fa = TC.median(a.runs.map((r) => TC.stat(r, S.joint, 'fbShare'))), fbv = TC.median(b.runs.map((r) => TC.stat(r, S.joint, 'fbShare')));
        const detail = `${METRICS[S.metric].fmt(a.mean)} → ${METRICS[S.metric].fmt(b.mean)}` + (S.metric !== 'fbShare' ? ` · FB share ${TC.pct(fa)} → ${TC.pct(fbv)}` : '');
        it.appendChild(el('span', { class: 'num muted ell', title: detail, text: detail }));
      } else it.appendChild(el('span', { class: 'muted', text: `unchanged · ${L.runs.length} runs of ${TC.group(L.phases[0].group).short} only` }));
      if (L.out.size) it.appendChild(el('span', { class: 'flag-bad', text: `${L.out.size} above upper limit` }));
      items.appendChild(it);
    }
    box.appendChild(items);
    box.appendChild(el('div', { class: 'bstat ' + (outN ? 'bad' : 'ok'), text: outN ? `${outN} run(s) above their upper limit` : 'no run above its upper limit' }));
    return box;
  }

  // ---------- SPC lane ----------
  function laneSvg(L, W) {
    const H = 104, top = 16, bottom = 18, left = 50, right = 62;
    const n = L.runs.length;
    const vals = L.runs.map(val);
    let hi = Math.max(...vals, ...L.phases.map((p) => (p.lim ? p.lim.ucl : 0)));
    if (L.sim) hi = Math.max(hi, val(L.sim));
    const step = niceStep(hi / 3);
    hi = Math.ceil((hi * 1.04) / step) * step;
    const x = (i) => left + (n === 1 ? 0.5 : i / (n - 1)) * (W - left - right);
    const y = (v) => top + (1 - v / hi) * (H - top - bottom);
    const s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'spc' });
    const half = (W - left - right) / Math.max(1, n - 1) / 2;
    // phase backgrounds
    L.phases.forEach((p) => {
      const x0 = Math.max(left - 6, x(p.start) - half), x1 = Math.min(W - right + 6, x(p.start + p.runs.length - 1) + half);
      const sel = S.selected === `${L.t.name}|${p.group}`;
      const r = svg('rect', { x: x0, y: top - 4, width: x1 - x0, height: H - top - bottom + 8, fill: TC.hexA(TC.group(p.group).color, sel ? 0.1 : 0.045), stroke: sel ? TC.hexA(TC.group(p.group).color, 0.5) : 'none', rx: 3 });
      r.classList.add('pick');
      r.addEventListener('click', () => { S.selected = `${L.t.name}|${p.group}`; S.selRun = null; save(); renderAll(); });
      s.appendChild(r);
      const lab = svg('text', { x: x1 - 4, y: 10, 'text-anchor': 'end', 'font-size': 10, fill: TC.group(p.group).color, 'font-weight': 600 }); lab.textContent = `${TC.group(p.group).short} · n=${p.runs.length}`; s.appendChild(lab);
      if (p.lim) {
        const xa = x0 + 2, xb = x1 - 2;
        s.appendChild(svg('line', { x1: xa, x2: xb, y1: y(p.lim.mean), y2: y(p.lim.mean), stroke: S.limits === 'phase' ? TC.group(p.group).color : '#52514e', 'stroke-width': 1.3 }));
        [p.lim.ucl, p.lim.lcl].forEach((v) => { if (v > 0 && v < hi) s.appendChild(svg('line', { x1: xa, x2: xb, y1: y(v), y2: y(v), stroke: '#8a8983', 'stroke-width': 1, 'stroke-dasharray': '4 3' })); });
      }
    });
    // y axis
    for (let v = 0; v <= hi + 1e-9; v += step) {
      const tx = svg('text', { x: left - 8, y: y(v) + 3, 'text-anchor': 'end', 'font-size': 9.5, fill: '#8a8983' }); tx.textContent = METRICS[S.metric].axis(v); s.appendChild(tx);
      s.appendChild(svg('line', { x1: left - 4, x2: left, y1: y(v), y2: y(v), stroke: '#cfcec8' }));
    }
    // sim reference
    if (L.sim) {
      const sv = val(L.sim);
      s.appendChild(svg('line', { x1: left, x2: W - right, y1: y(sv), y2: y(sv), stroke: '#6f6e69', 'stroke-dasharray': '1 3', 'stroke-width': 1.2 }));
      const tx = svg('text', { x: W - 2, y: y(sv) + 3, 'text-anchor': 'end', 'font-size': 9.5, fill: '#6f6e69' }); tx.textContent = 'sim ' + METRICS[S.metric].fmt(sv); s.appendChild(tx);
    }
    // date boundaries + x labels
    L.runs.forEach((r, i) => {
      if (i === 0 || L.runs[i - 1].date !== r.date) {
        if (i > 0) s.appendChild(svg('line', { x1: x(i) - half, x2: x(i) - half, y1: 2, y2: H - bottom + 2, stroke: '#cfcec8', 'stroke-dasharray': '2 2' }));
        const tx = svg('text', { x: (i > 0 ? x(i) - half : left - 6) + 4, y: 10, 'font-size': 9.5, fill: '#8a8983' }); tx.textContent = r.date; s.appendChild(tx);
      }
      const lx = svg('text', { x: x(i), y: H - 5, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#8a8983' }); lx.textContent = '#' + r.num; s.appendChild(lx);
    });
    // connecting line + points
    let d = '';
    vals.forEach((v, i) => (d += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)));
    s.appendChild(svg('path', { d, fill: 'none', stroke: '#b9b8b1', 'stroke-width': 1 }));
    // Western Electric rule 2: 6+ consecutive runs on one side of the whole-lane centre = the process shifted
    L.streaks.forEach((st, k) => {
      const xa = x(st.start) - 7, xb = x(st.end) + 7, yb = H - bottom - 2;
      s.appendChild(svg('path', { d: `M${xa} ${yb - 4}V${yb}H${xb}V${yb - 4}`, fill: 'none', stroke: '#52514e', 'stroke-width': 1 }));
      const tx = svg('text', { x: (xa + xb) / 2, y: yb - 4, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#22211f', stroke: '#fcfcfb', 'stroke-width': 3, 'paint-order': 'stroke' });
      tx.textContent = `${st.end - st.start + 1} in a row ${st.side < 0 ? 'below' : 'above'} centre` + (k > 0 && L.streaks[k - 1].side !== st.side && L.streaks[k - 1].end === st.start - 1 ? ` → shift at #${L.runs[st.start].num}` : '');
      s.appendChild(tx);
    });
    L.runs.forEach((r, i) => {
      const v = vals[i], out = L.out.has(r.id), g = TC.group(r.group);
      const sel = S.selRun === r.id || S.hover === r.id;
      if (out) s.appendChild(svg('circle', { cx: x(i), cy: y(v), r: 8, fill: 'none', stroke: TC.C.bad, 'stroke-width': 1.2 }));
      if (L.low.has(r.id)) s.appendChild(svg('circle', { cx: x(i), cy: y(v), r: 8, fill: 'none', stroke: '#8a8983', 'stroke-width': 1.2, 'stroke-dasharray': '2 2' }));
      const c = svg('circle', { cx: x(i), cy: y(v), r: sel ? 5.5 : 4.3, fill: out ? TC.C.bad : g.color, stroke: sel ? '#22211f' : '#fff', 'stroke-width': sel ? 2 : 1 });
      c.classList.add('pick');
      c.addEventListener('mousemove', (e) => TC.tip(e, `<b>${TC.esc(r.id)}</b> · ${TC.esc(r.title)} · ${r.date}<br><span class="k">${METRICS[S.metric].label}</span> ${METRICS[S.metric].fmt(v)}${out ? ' · <b>above its upper limit</b>' : L.low.has(r.id) ? ' · below its lower limit (unusually good)' : ''}<br><span class="k">FB share</span> ${TC.pct(TC.stat(r, S.joint, 'fbShare'))} · <span class="k">at limit</span> ${TC.pct(TC.stat(r, S.joint, 'satFrac'))}<br><span class="k">click: phase detail · double-click: run view</span>`));
      c.addEventListener('mouseleave', () => TC.tip(null));
      c.addEventListener('click', () => selectRun(r));
      c.addEventListener('dblclick', () => TC.drill(r.target, r.short));
      s.appendChild(c);
    });
    return { s, x };
  }
  function fbStrip(L, W, x) {
    const H = 24, s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'fbstrip' });
    const lab = svg('text', { x: 0, y: 14, 'font-size': 9.5, fill: '#8a8983' }); lab.textContent = 'FB share'; s.appendChild(lab);
    s.appendChild(svg('line', { x1: 50, x2: W - 14, y1: H - 2, y2: H - 2, stroke: '#e6e5e0' }));
    L.runs.forEach((r, i) => {
      const v = TC.stat(r, S.joint, 'fbShare'), h = Math.min(1, v / 0.5) * (H - 4);
      const sat = TC.stat(r, S.joint, 'satFrac') > 0.01;
      const b = svg('rect', { x: x(i) - 5, y: H - 2 - h, width: 10, height: h, fill: TC.C.fb, 'fill-opacity': 0.75, rx: 1 });
      b.appendChild(svg('title', {}, [document.createTextNode(`${r.short}: FB share ${TC.pct(v)}${sat ? ' · command at the drive limit ' + TC.pct(TC.stat(r, S.joint, 'satFrac')) : ''}`)]));
      s.appendChild(b);
      if (sat) s.appendChild(svg('rect', { x: x(i) + 6, y: H - 14, width: 3, height: 12, fill: TC.C.warn, rx: 1 }));
    });
    return s;
  }
  function renderLanes() {
    lanesBox.innerHTML = '';
    const lanes = TC.targets.map(lane);
    lanesBox.appendChild(banner(lanes));
    const W = Math.max(500, lanesBox.clientWidth - 32 - 22);
    for (const L of lanes) {
      const box = el('section', { class: 'lane' });
      const ph = L.phases.map((p) => `${TC.group(p.group).short} n=${p.runs.length}: mean ${METRICS[S.metric].fmt(p.mean)}${p.lim ? `, UCL ${METRICS[S.metric].fmt(p.lim.ucl)}` : ''}`).join('  ·  ');
      box.appendChild(el('div', { class: 'lhead' }, [el('span', { class: 'ltitle ell', title: `${L.t.title} — ${L.t.description}`, text: L.t.title }), el('span', { class: 'lph faint ell num', title: ph, text: ph }),
        el('a', { class: 'drill', href: TC.drillHref(L.t.name, 'all'), text: 'run view ↗' })]));
      const { s, x } = laneSvg(L, W);
      box.append(s, fbStrip(L, W, x));
      lanesBox.appendChild(box);
    }
  }

  // ---------- ledger ----------
  function renderLedger() {
    ledgerBody.innerHTML = '';
    const lanes = Object.fromEntries(TC.targets.map((t) => [t.name, lane(t)]));
    const all = TC.runs.filter((r) => r.kind === 'real').sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.order - b.order));
    const table = el('div', { class: 'ltable' });
    table.appendChild(el('div', { class: 'lrow lh' }, [el('span', { text: '#' }), el('span', { text: 'target' }), el('span', { text: 'run' }), el('span', { text: 'ff' }), el('span', { class: 'r', text: METRICS[S.metric].label }), el('span', { text: '' })]));
    let date = null, seq = 0;
    for (const r of all) {
      if (r.date !== date) { date = r.date; table.appendChild(el('div', { class: 'ldate', text: date })); }
      seq++;
      const out = lanes[r.target].out.has(r.id);
      const sat = TC.stat(r, S.joint, 'satFrac') > 0.01;
      const row = el('div', { class: 'lrow' + (S.selRun === r.id ? ' selected' : ''), 'data-run': r.id, onclick: () => selectRun(r), ondblclick: () => TC.drill(r.target, r.short), title: `${r.id} — ${r.title} · ${r.date} (double-click: run view)` }, [
        el('span', { class: 'num faint', text: String(seq) }),
        el('span', { class: 'ell', text: r.target.replace('full-circle-', 'circle ') }),
        el('span', { class: 'ell', text: r.short }),
        el('span', {}, [el('span', { class: 'sw ' + r.group })]),
        el('span', { class: 'num r', text: METRICS[S.metric].fmt(val(r)) }),
        el('span', {}, [out ? el('span', { class: 'flag-bad', title: 'above its upper control limit', text: 'high' }) : sat ? el('span', { class: 'flag-warn', title: `command at the drive limit ${TC.pct(TC.stat(r, S.joint, 'satFrac'))} of the time`, text: 'sat' }) : null]),
      ]);
      row.addEventListener('mouseenter', () => { S.hover = r.id; renderLanes(); });
      row.addEventListener('mouseleave', () => { S.hover = null; renderLanes(); });
      table.appendChild(row);
    }
    table.appendChild(el('div', { class: 'ldate', text: 'references (not history)' }));
    TC.runs.filter((r) => r.kind === 'sim').forEach((r) => table.appendChild(el('div', { class: 'lrow ref', onclick: () => TC.drill(r.target, r.short), title: r.title }, [
      el('span', { class: 'faint', text: '—' }), el('span', { class: 'ell', text: r.target.replace('full-circle-', 'circle ') }), el('span', { text: 'sim' }), el('span', {}, [el('span', { class: 'sw sim' })]), el('span', { class: 'num r', text: METRICS[S.metric].fmt(val(r)) }), el('span', {})])));
    ledgerBody.appendChild(table);
    ledgerBody.appendChild(el('div', { class: 'lfoot faint', text: `Order = date, then run number (the fixture has no time of day). ${all.length} real runs; designed as a virtual list for hundreds.` }));
  }

  // ---------- drawer: the selected phase over the trajectory ----------
  let chart = null;
  function selectRun(r) { S.selRun = r.id; S.selected = `${r.target}|${r.group}`; save(); renderAll(); }
  function renderDrawer() {
    TC.destroyChart(chart); chart = null;
    const [tn, gk] = S.selected.split('|');
    const t = TC.target(tn) || TC.targets[0];
    const g = TC.group(gk) || TC.group('v2');
    const runs = TC.groupRuns(t, g.key);
    const other = TC.GROUPS.filter((gg) => gg.key !== g.key && gg.key !== 'sim').map((gg) => ({ gg, rs: TC.groupRuns(t, gg.key) })).filter((o) => o.rs.length);
    const mode = TC.encodingFor(runs.length, 'auto', S.threshold);
    dTitle.innerHTML = '';
    dTitle.append(el('span', { class: 'sw', style: { background: g.color } }), ` ${t.title} · ${g.label} phase `, el('span', { class: 'faint', text: `· ${runs.length} repeats as ${mode === 'bands' ? 'a percentile fan' : 'lines'} · error over the trajectory, ${TC.jointLabel(S.joint)}` }));
    dTitle.title = `${t.title} · ${g.label}`;
    dAct.innerHTML = '';
    dAct.append(el('a', { class: 'btn primary', href: TC.drillHref(t.name, S.selRun ? TC.run(S.selRun).short : 'group/' + g.key), text: S.selRun ? `Open ${TC.run(S.selRun).short} ↗` : 'Open run view ↗' }));
    dBody.innerHTML = '';
    const legend = el('div', { class: 'card-legend' });
    const host = el('div', { class: 'dplot' });
    const readout = el('div', { class: 'plot-readout', html: '&nbsp;' });
    dBody.append(legend, host, readout);
    requestAnimationFrame(() => {
      const layers = other.map((o) => ({ key: o.gg.key, color: '#b9b8b1', label: o.gg.short + ' (other phase)', mode: TC.encodingFor(o.rs.length, 'auto', S.threshold), runs: o.rs.map((r) => ({ run: r, y: TC.series(r, 'err', S.joint) })) }));
      layers.push({ key: g.key, color: g.color, label: g.short, mode, runs: runs.map((r) => ({ run: r, y: TC.series(r, 'err', S.joint) })) });
      const overlay = S.selRun && TC.run(S.selRun) && TC.run(S.selRun).target === t.name ? [{ run: TC.run(S.selRun), y: TC.series(TC.run(S.selRun), 'err', S.joint), color: '#22211f' }] : [];
      layers.forEach((L) => legend.appendChild(el('span', { class: 'lg' }, [el('span', { class: 'sw', style: { background: L.color } }), `${L.label} `, el('span', { class: 'faint', text: `n=${L.runs.length} · ${L.mode === 'bands' ? 'fan' : 'lines'}` })])));
      if (overlay.length) legend.appendChild(el('span', { class: 'lg' }, [el('span', { class: 'sw', style: { background: '#22211f' } }), ` ${overlay[0].run.short} (selected)`]));
      chart = TC.fanChart(host, { x: t.t, layers, overlay, height: Math.max(100, dBody.clientHeight - 44), yFmt: (v) => v.toFixed(2) + '°', yUnit: '°', readout, zeroLine: true,
        onPick: (hit) => (hit.run ? TC.drill(t.name, hit.run.short) : TC.drill(t.name, 'group/' + hit.layer.key)) });
    });
  }

  function renderAll() { renderToolbar(); renderLanes(); renderLedger(); renderDrawer(); }
  let rt = null;
  window.addEventListener('tcs:layout', () => { clearTimeout(rt); rt = setTimeout(() => { renderLanes(); renderDrawer(); }, 60); });
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { renderLanes(); renderDrawer(); }, 80); });
  renderAll();
  window.TCS_V5 = { S, renderAll, selectRun };
})();
