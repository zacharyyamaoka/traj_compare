/* V2 · League table — answer first: one row per target × config group with the verdict on each target's header;
   the error distribution as a box (dots while n is small), FB share, drive gap, saturation, ISO 9283 path repeatability
   and an error sparkline; sort by any column, expand a row into its runs, select a row to see it over time on the right.
   SIMULATED fixture; prototype stats. */
(function () {
  'use strict';
  const { el, svg } = TC;
  const S = {
    joint: TC.store.get('v2:joint', 0),
    metric: TC.store.get('v2:metric', 'rmsErr'),
    layout: TC.store.get('v2:layout', 'grouped'),
    sort: TC.store.get('v2:sort', { key: 'median', dir: 1 }),
    dateOff: new Set(TC.store.get('v2:dateOff', [])),
    expanded: new Set(TC.store.get('v2:expanded', ['full-circle-slow|v2'])),
    selected: TC.store.get('v2:selected', 'full-circle-slow|v2'),
    threshold: 5,
  };
  const save = () => { for (const k of ['joint', 'metric', 'layout', 'sort', 'selected']) TC.store.set('v2:' + k, S[k]); TC.store.set('v2:dateOff', [...S.dateOff]); TC.store.set('v2:expanded', [...S.expanded]); };
  const keep = (r) => !S.dateOff.has(r.date);
  const METRICS = {
    rmsErr: { label: 'RMS error', unit: '°', fmt: (v) => TC.deg(v) },
    maxErr: { label: 'Max |error|', unit: '°', fmt: (v) => TC.deg(v) },
    fbShare: { label: 'FB share', unit: '%', fmt: (v) => TC.pct(v), scale: 100 },
  };

  // ---------- data rows ----------
  function rowsFor(t) {
    const rows = [];
    const v = TC.verdict(t, S.joint, keep, S.metric === 'fbShare' ? 'fbShare' : S.metric);
    for (const g of TC.GROUPS) {
      const runs = TC.groupRuns(t, g.key, keep);
      if (!runs.length) continue;
      const vals = runs.map((r) => TC.stat(r, S.joint, S.metric));
      const sm = TC.summary(vals);
      const fb = TC.summary(runs.map((r) => TC.stat(r, S.joint, 'fbShare')));
      const gap = TC.median(runs.map((r) => TC.stat(r, S.joint, 'gapRms')));
      const sat = TC.median(runs.map((r) => TC.stat(r, S.joint, 'satFrac')));
      const satRuns = runs.filter((r) => TC.stat(r, S.joint, 'satFrac') > 0.01).length;
      const rt = g.key === 'sim' ? null : TC.pathRepeatability(runs);
      const v1 = TC.groupRuns(t, 'v1', keep);
      const v1med = v1.length ? TC.median(v1.map((r) => TC.stat(r, S.joint, S.metric))) : null;
      const delta = g.key === 'v2' && v1med ? (sm.p50 - v1med) / v1med : null;
      rows.push({ id: t.name + '|' + g.key, t, g, runs, sm, fb, gap, sat, satRuns, rt, delta, verdict: v });
    }
    let lo = 0, hi = 0;
    rows.forEach((row) => row.runs.forEach((r) => TC.series(r, 'err', S.joint).forEach((y) => { if (y != null) { lo = Math.min(lo, y); hi = Math.max(hi, y); } })));
    rows.forEach((row) => (row.sparkRange = [lo, hi]));
    return rows;
  }
  const SORTS = {
    group: (r) => ['v2', 'v1', 'sim'].indexOf(r.g.key), n: (r) => -r.runs.length, median: (r) => r.sm.p50, delta: (r) => (r.delta == null ? 9 : r.delta),
    fb: (r) => r.fb.p50, gap: (r) => r.gap, sat: (r) => r.sat, rt: (r) => (r.rt ? r.rt.rt : 1e9),
  };
  // WHY sim stays last: it is the ideal-plant reference (error ≈ 0), not a contender; sorting it to the top hid the answer
  const sortRows = (rows) => rows.slice().sort((a, b) => ((a.g.key === 'sim') - (b.g.key === 'sim')) || S.sort.dir * (SORTS[S.sort.key](a) - SORTS[S.sort.key](b)));

  // ---------- frame ----------
  const app = document.getElementById('app');
  app.appendChild(TC.header('V2 · League table'));
  const toolbar = el('div', { class: 'toolbar' });
  app.appendChild(toolbar);
  const split = el('div', { class: 'split-h' });
  const main = el('main', { class: 'main league' });
  const gutter = el('div', { class: 'gutter' });
  const side = el('aside', { class: 'side detail' });
  const foldBtn = el('button', { class: 'iconbtn', title: 'Fold panel' });
  const sideTitle = el('span', { class: 'side-title ell' });
  side.appendChild(el('div', { class: 'side-head' }, [foldBtn, sideTitle, el('span', { class: 'vlabel', text: 'Detail' })]));
  const sideBody = el('div', { class: 'side-body' });
  side.appendChild(sideBody);
  split.append(main, gutter, side);
  app.appendChild(split);
  TC.splitter({ gutter, panel: side, key: 'v2:detail', side: 'right', min: 300, max: 720, size: 392, foldBtn });

  function seg(options, value, onPick) {
    const s = el('div', { class: 'seg' });
    options.forEach(([v, label, tip]) => s.appendChild(el('button', { class: v === value ? 'on' : '', title: tip || '', text: label, 'data-v': String(v), onclick: () => onPick(v) })));
    return s;
  }
  function renderToolbar() {
    toolbar.innerHTML = '';
    toolbar.append(
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Distribution of' }),
        seg(Object.entries(METRICS).map(([k, m]) => [k, m.label]), S.metric, (v) => { S.metric = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Joint' }),
        seg(TC.joints.map((j, i) => [i, j]).concat([[TC.joints.length, 'all']]), S.joint, (v) => { S.joint = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Rows' }),
        seg([['grouped', 'By target', 'One block per target, verdict on its header'], ['flat', 'League', 'Every target × group in one ranked list']], S.layout, (v) => { S.layout = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Date' }), ...TC.dates.map((d) => el('span', { class: 'chip ' + (S.dateOff.has(d) ? 'off' : 'on'), title: (S.dateOff.has(d) ? 'Include' : 'Exclude') + ' runs from ' + d,
        onclick: () => { S.dateOff.has(d) ? S.dateOff.delete(d) : S.dateOff.add(d); save(); renderAll(); } }, [TC.shortDate(d), el('span', { class: 'n', text: String(TC.runs.filter((r) => r.date === d).length) })]))]),
      el('span', { class: 'spacer' }),
      el('span', { class: 'faint hint', text: 'click a header to sort · click a row for detail · ▸ expands its runs' }),
    );
  }

  // ---------- table ----------
  const COLS = [
    ['group', 'Target · config', 'left'], ['n', 'n', 'right'], ['dist', null, 'center'], ['median', 'median', 'right'], ['delta', 'Δ vs ff v1', 'right'],
    ['fb', 'FB share', 'left'], ['gap', 'drive gap N·m', 'right'], ['sat', 'sat.', 'right'], ['rt', 'ISO 9283 RT', 'right'], ['spark', 'error over time', 'left'], ['go', '', 'center'],
  ];
  const WIDTHS = [180, 32, 196, 70, 70, 108, 64, 52, 74, 122, 26];
  function colgroup() { return el('colgroup', null, WIDTHS.map((w) => el('col', { style: { width: w + 'px' } }))); }
  function thead(scale) {
    const tr = el('tr');
    COLS.forEach(([k, label, align]) => {
      let content = label;
      if (k === 'dist') content = METRICS[S.metric].label + ' · ' + (S.metric === 'fbShare' ? 'per run' : TC.jointLabel(S.joint));
      const sortable = k in SORTS || k === 'dist';
      const key = k === 'dist' ? 'median' : k;
      const th = el('th', { class: 'al-' + align + (sortable ? ' sortable' : '') + (S.sort.key === key && sortable ? ' sorted' : ''), title: sortable ? 'Sort by ' + (content || k) : null,
        onclick: sortable ? () => { S.sort = { key, dir: S.sort.key === key ? -S.sort.dir : 1 }; save(); renderTable(); } : null });
      th.appendChild(document.createTextNode(content || ''));
      if (S.sort.key === key && sortable && k !== 'dist') th.appendChild(el('span', { class: 'arrow', text: S.sort.dir > 0 ? ' ↑' : ' ↓' }));
      if (k === 'dist') th.appendChild(axisSvg(scale));
      if (k === 'rt') th.title = 'ISO 9283 path repeatability of the L2 tip: max over the path of l̄ + 3·S_l (mm); needs ≥ 3 runs';
      if (k === 'sat') th.title = 'Median share of samples with the commanded torque at the drive limit';
      if (k === 'gap') th.title = 'Median RMS of τ_cmd − τ_applied (N·m): saturation, current-loop lag, kt error';
      tr.appendChild(th);
    });
    return el('thead', null, [tr]);
  }
  const DW = 180, DH = 22;
  function scaleFor(rows) {
    let hi = 0;
    rows.forEach((r) => r.runs.forEach((run) => (hi = Math.max(hi, TC.stat(run, S.joint, S.metric)))));
    const step = niceStep(hi / 4);
    return { lo: 0, hi: Math.max(step, Math.ceil(hi / step) * step), step };
  }
  function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x || 1))); const m = x / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p; }
  const sx = (scale, v) => 12 + ((v - scale.lo) / (scale.hi - scale.lo)) * (DW - 26);
  function axisSvg(scale) {
    const s = svg('svg', { class: 'axis', width: DW, height: 14, viewBox: `0 0 ${DW} 14` });
    for (let v = scale.lo; v <= scale.hi + 1e-9; v += scale.step) {
      const x = sx(scale, v);
      s.appendChild(svg('line', { x1: x, x2: x, y1: 10, y2: 14, stroke: '#cfcec8' }));
      const t = svg('text', { x, y: 8, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#8a8983' });
      t.textContent = S.metric === 'fbShare' ? Math.round(v * 100) + '%' : +v.toFixed(2) + '°';
      s.appendChild(t);
    }
    return s;
  }
  function distSvg(row, scale) {
    const s = svg('svg', { width: DW, height: DH, viewBox: `0 0 ${DW} ${DH}`, class: 'dist' });
    const vals = row.runs.map((r) => TC.stat(r, S.joint, S.metric));
    const c = row.g.color, mid = DH / 2;
    s.appendChild(svg('line', { x1: 6, x2: DW - 6, y1: mid, y2: mid, stroke: '#efeee9' }));
    const sm = row.sm;
    const mode = row.g.key === 'sim' ? 'single' : TC.encodingFor(vals.length, 'auto', S.threshold);
    if (mode === 'bands') {
      s.appendChild(svg('line', { x1: sx(scale, sm.min), x2: sx(scale, sm.max), y1: mid, y2: mid, stroke: c, 'stroke-width': 1.2 }));
      [sm.min, sm.max].forEach((v) => s.appendChild(svg('line', { x1: sx(scale, v), x2: sx(scale, v), y1: mid - 4, y2: mid + 4, stroke: c, 'stroke-width': 1.2 })));
      s.appendChild(svg('rect', { x: sx(scale, sm.p25), y: mid - 6, width: Math.max(1.5, sx(scale, sm.p75) - sx(scale, sm.p25)), height: 12, fill: TC.hexA(c, 0.22), stroke: c, 'stroke-width': 1, rx: 1.5 }));
    }
    row.runs.forEach((r, i) => {
      const v = TC.stat(r, S.joint, S.metric);
      const dot = svg(row.g.key === 'sim' ? 'rect' : 'circle', row.g.key === 'sim'
        ? { x: sx(scale, v) - 3.5, y: mid - 3.5, width: 7, height: 7, transform: `rotate(45 ${sx(scale, v)} ${mid})`, fill: '#fff', stroke: c, 'stroke-width': 1.5 }
        : { cx: sx(scale, v), cy: mid + (mode === 'bands' ? 0 : ((i % 3) - 1) * 3.2), r: mode === 'bands' ? 2 : 3, fill: mode === 'bands' ? '#fff' : c, stroke: c, 'stroke-width': 1, 'fill-opacity': mode === 'bands' ? 1 : 0.85 });
      dot.classList.add('pick');
      dot.addEventListener('mousemove', (e) => TC.tip(e, `<b>${TC.esc(r.id)}</b><br>${TC.esc(r.title)} · ${r.date}<br><span class="k">${METRICS[S.metric].label}</span> ${METRICS[S.metric].fmt(v)} · <span class="k">FB share</span> ${TC.pct(TC.stat(r, S.joint, 'fbShare'))}<br><span class="k">click to open the run view</span>`));
      dot.addEventListener('mouseleave', () => TC.tip(null));
      dot.addEventListener('click', (e) => { e.stopPropagation(); TC.drill(r.target, r.short); });
      s.appendChild(dot);
    });
    if (row.g.key !== 'sim' && row.runs.length > 1) s.appendChild(svg('line', { x1: sx(scale, sm.p50), x2: sx(scale, sm.p50), y1: mid - 8, y2: mid + 8, stroke: '#22211f', 'stroke-width': 1.6 }));
    return s;
  }
  function fbCell(fb) {
    const W = 64;
    const wrap = el('div', { class: 'fbcell' });
    const s = svg('svg', { width: W, height: 12, viewBox: `0 0 ${W} 12` });
    const x = (v) => (Math.min(v, 0.5) / 0.5) * W;
    s.appendChild(svg('rect', { x: 0, y: 3, width: W, height: 6, fill: '#ecebe6', rx: 2 }));
    s.appendChild(svg('rect', { x: 0, y: 3, width: x(fb.p50), height: 6, fill: TC.C.fb, rx: 2 }));
    if (fb.n > 1) s.appendChild(svg('line', { x1: x(fb.min), x2: x(fb.max), y1: 6, y2: 6, stroke: '#22211f', 'stroke-width': 1 }));
    wrap.title = `FB share median ${TC.pct(fb.p50)}${fb.n > 1 ? `, range ${TC.pct(fb.min)}–${TC.pct(fb.max)}` : ''} (axis 0–50 %)`;
    wrap.append(s, el('span', { class: 'num', text: TC.pct(fb.p50) }));
    return wrap;
  }
  // WHY a shared range per block: a per-row range blew the sim's ≈ 0 error up into a full-height wiggle
  function spark(ys, band, color, range) {
    const W = 110, H = 22;
    let [lo, hi] = range;
    const s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'spark' });
    if (lo < 0 && hi > 0) { const y0 = H - ((0 - lo) / (hi - lo)) * H; s.appendChild(svg('line', { x1: 0, x2: W, y1: y0, y2: y0, stroke: '#e6e5e0' })); }
    if (band) s.appendChild(svg('path', { d: TC.areaPath(band.p25, band.p75, W, H, lo, hi), fill: TC.hexA(color, 0.25) }));
    s.appendChild(svg('path', { d: TC.sparkPath(band ? band.p50 : ys, W, H, lo, hi), fill: 'none', stroke: color, 'stroke-width': 1.3 }));
    return s;
  }
  function groupRow(row, scale, showTarget) {
    const open = S.expanded.has(row.id);
    const sel = S.selected === row.id;
    const tr = el('tr', { class: 'grow' + (sel ? ' selected' : '') + ' g-' + row.g.key, 'data-row': row.id, onclick: () => { S.selected = row.id; save(); renderTable(); renderDetail(); } });
    const errs = row.runs.map((r) => TC.series(r, 'err', S.joint));
    const band = row.runs.length >= 3 ? TC.band(errs) : null;
    const name = el('div', { class: 'gname' }, [
      el('button', { class: 'iconbtn caret', text: open ? '▾' : '▸', title: open ? 'Collapse runs' : 'Expand into runs',
        onclick: (e) => { e.stopPropagation(); open ? S.expanded.delete(row.id) : S.expanded.add(row.id); save(); renderTable(); } }),
      el('span', { class: 'sw', style: { background: row.g.color } }),
      el('span', { class: 'ell', title: `${row.t.title} · ${row.g.label}`, text: showTarget ? `${row.t.name.replace('full-circle-', 'circle ')} · ${row.g.short}` : row.g.label }),
    ]);
    const deltaTxt = row.delta == null ? '' : TC.signedPct(row.delta);
    const cells = [
      name, el('span', { class: 'num', text: String(row.runs.length) }), distSvg(row, scale),
      el('span', { class: 'num strong', text: row.g.key === 'sim' ? METRICS[S.metric].fmt(row.sm.p50) : METRICS[S.metric].fmt(row.sm.p50) }),
      el('span', { class: 'num' + (row.delta != null && row.delta < 0 ? ' better' : ''), text: deltaTxt || (row.g.key === 'v1' ? 'baseline' : '') }),
      fbCell(row.fb), el('span', { class: 'num', text: row.gap.toFixed(3) }),
      row.satRuns ? el('span', { class: 'flag-warn', title: `${row.satRuns} of ${row.runs.length} runs hold the command at the drive limit for > 1 % of samples`, text: TC.pct(row.sat) }) : el('span', { class: 'num faint', text: TC.pct(row.sat) }),
      el('span', { class: 'num', title: row.rt ? `worst at t = ${row.rt.at.toFixed(2)} s` : 'needs ≥ 3 runs', text: row.rt ? TC.mm(row.rt.rt, 2) : '—' }),
      spark(band ? null : errs[0], band, row.g.color, row.sparkRange),
      el('a', { class: 'drill', href: TC.drillHref(row.t.name, 'group/' + row.g.key), title: 'Open this group in the run view', text: '↗', onclick: (e) => e.stopPropagation() }),
    ];
    cells.forEach((c, i) => tr.appendChild(el('td', { class: 'al-' + COLS[i][2] }, [c])));
    const out = [tr];
    if (open) {
      const med = row.sm.p50;
      row.runs.slice().sort((a, b) => TC.stat(a, S.joint, S.metric) - TC.stat(b, S.joint, S.metric)).forEach((r) => {
        const v = TC.stat(r, S.joint, S.metric);
        const sub = el('tr', { class: 'runrow', onclick: () => TC.drill(r.target, r.short), title: 'Open ' + r.id + ' in the run view' });
        const one = { ...row, runs: [r], sm: TC.summary([v]) };
        const subcells = [
          el('div', { class: 'rname' }, [el('span', { class: 'ell', title: `${r.id} — ${r.title}`, text: r.short }), el('span', { class: 'faint', text: ' ' + TC.shortDate(r.date) })]),
          el('span', { text: '' }), distSvg(one, scale), el('span', { class: 'num', text: METRICS[S.metric].fmt(v) }),
          el('span', { class: 'num faint', title: 'vs this group\'s median', text: row.runs.length > 1 ? TC.signedPct((v - med) / med) : '' }),
          fbCell(TC.summary([TC.stat(r, S.joint, 'fbShare')])), el('span', { class: 'num', text: TC.stat(r, S.joint, 'gapRms').toFixed(3) }),
          TC.stat(r, S.joint, 'satFrac') > 0.01 ? el('span', { class: 'flag-warn', text: TC.pct(TC.stat(r, S.joint, 'satFrac')) }) : el('span', { class: 'num faint', text: TC.pct(TC.stat(r, S.joint, 'satFrac')) }),
          el('span', { class: 'faint', text: '' }), spark(TC.series(r, 'err', S.joint), null, row.g.color, row.sparkRange),
          el('a', { class: 'drill', href: TC.drillHref(r.target, r.short), text: '↗', onclick: (e) => e.stopPropagation() }),
        ];
        subcells.forEach((c, i) => sub.appendChild(el('td', { class: 'al-' + COLS[i][2] }, [c])));
        out.push(sub);
      });
    }
    return out;
  }
  function verdictLine(v, t) {
    const box = el('div', { class: 'verdict' });
    const mlabel = METRICS[S.metric].label;
    if (v.hasBoth) {
      const g = TC.group(v.winner);
      box.append(el('span', { class: 'sw', style: { background: g.color } }), el('b', { text: g.label + ' better' }),
        el('span', { class: 'num', html: ` <b>${TC.signedPct(v.delta)}</b> ${mlabel}` }),
        el('span', { class: 'num muted', html: ` · FB share <b>${TC.pct(v.fbA)} → ${TC.pct(v.fbB)}</b>` }),
        el('span', { class: 'conf ' + v.conf, title: `Probability of superiority: ${TC.confText(v)}`, text: ` ${v.conf} confidence · ${Math.round(v.winner === 'v2' ? v.wins : v.pairs - v.wins)}/${v.pairs} run pairs` }));
    } else {
      box.append(el('span', { class: 'sw', style: { background: TC.C.v1 } }), el('b', { text: 'ff v1 nominal only' }), el('span', { class: 'muted', text: ` · ${v.a.length} runs · no ff v2 runs on this target yet — nothing to compare` }));
    }
    const sat = t.runs.filter(keep).filter((r) => r.kind === 'real' && TC.stat(r, S.joint, 'satFrac') > 0.01).length;
    if (sat) box.appendChild(el('span', { class: 'flag-warn', title: 'Runs whose command sits at the drive limit for > 1 % of samples', text: `${sat} runs saturate` }));
    return box;
  }
  function renderTable() {
    main.innerHTML = '';
    if (S.layout === 'grouped') {
      for (const t of TC.targets) {
        const rows = rowsFor(t);
        if (!rows.length) continue;
        const scale = scaleFor(rows);
        const block = el('section', { class: 'block' });
        block.appendChild(el('div', { class: 'bhead' }, [el('span', { class: 'btitle ell', title: `${t.title} — ${t.description}`, text: t.title }), verdictLine(rows[0].verdict, t)]));
        const table = el('table', { class: 'lt' }, [colgroup(), thead(scale)]);
        const tb = el('tbody');
        sortRows(rows).forEach((r) => groupRow(r, scale, false).forEach((tr) => tb.appendChild(tr)));
        table.appendChild(tb);
        block.appendChild(table);
        main.appendChild(block);
      }
    } else {
      const rows = TC.targets.flatMap(rowsFor);
      const scale = scaleFor(rows);
      const block = el('section', { class: 'block' });
      block.appendChild(el('div', { class: 'bhead' }, [el('span', { class: 'btitle', text: 'League · every target × config group' }),
        el('span', { class: 'muted', text: `ranked by ${S.sort.key}; one shared axis, so targets of different difficulty sit on one scale` })]));
      const table = el('table', { class: 'lt' }, [colgroup(), thead(scale)]);
      const tb = el('tbody');
      sortRows(rows).forEach((r) => groupRow(r, scale, true).forEach((tr) => tb.appendChild(tr)));
      table.appendChild(tb);
      block.appendChild(table);
      main.appendChild(block);
    }
    main.appendChild(el('div', { class: 'foot faint', text: 'Prototype computation over the SIMULATED fixture: error = target − run (°), target interpolated onto each run\'s samples; FB share = Σ|τ_fb| / (Σ|τ_ff| + Σ|τ_fb|); confidence = probability of superiority over all v1 × v2 run pairs. Dots while a group has ≤ 5 runs, box (IQR) + min–max whiskers above.' }));
  }

  // ---------- detail panel ----------
  let detailChart = null;
  function renderDetail() {
    TC.destroyChart(detailChart); detailChart = null;
    sideBody.innerHTML = '';
    const [tname, gkey] = S.selected.split('|');
    const t = TC.target(tname) || TC.targets[0];
    const g = TC.group(gkey) || TC.GROUPS[2];
    const runs = TC.groupRuns(t, g.key, keep);
    sideTitle.textContent = `${t.title} · ${g.label}`;
    sideTitle.title = sideTitle.textContent;
    const body = el('div', { class: 'dbody' });
    body.appendChild(el('div', { class: 'dhead' }, [el('span', { class: 'sw', style: { background: g.color } }), el('b', { class: 'ell', title: `${t.title} · ${g.label}`, text: `${g.label} · ${runs.length} run${runs.length === 1 ? '' : 's'}` }),
      el('a', { class: 'btn primary', href: TC.drillHref(t.name, 'group/' + g.key), text: 'Open run view ↗' })]));
    body.appendChild(el('div', { class: 'dsec', text: `Tracking error over the trajectory · ${TC.jointLabel(S.joint)}` }));
    const legend = el('div', { class: 'card-legend' });
    const host = el('div', { class: 'dplot' });
    const readout = el('div', { class: 'plot-readout', html: '&nbsp;' });
    body.append(legend, host, readout);
    body.appendChild(el('div', { class: 'dsec', text: 'Torque budget per run · mean |τ| (N·m)' }));
    body.appendChild(el('div', { class: 'blegend' }, [el('span', { class: 'sw ff' }), 'feedforward', el('span', { class: 'sw fb' }), 'feedback', el('span', { class: 'sw gap' }), 'drive gap |τ_cmd − τ_applied|']));
    const budget = el('div', { class: 'budget' });
    const groupsShown = [g.key].concat(['v2', 'v1', 'sim'].filter((k) => k !== g.key));
    let maxTot = 0;
    t.runs.filter(keep).forEach((r) => (maxTot = Math.max(maxTot, TC.stat(r, S.joint, 'ffMav') + TC.stat(r, S.joint, 'fbMav') + TC.stat(r, S.joint, 'gapMav'))));
    for (const k of groupsShown) {
      const rs = TC.groupRuns(t, k, keep);
      if (!rs.length) continue;
      budget.appendChild(el('div', { class: 'bgroup' + (k === g.key ? ' sel' : '') }, [el('span', { class: 'sw', style: { background: TC.group(k).color } }), TC.group(k).label]));
      rs.forEach((r) => {
        const ff = TC.stat(r, S.joint, 'ffMav'), fb = TC.stat(r, S.joint, 'fbMav'), gp = TC.stat(r, S.joint, 'gapMav');
        const W = (v) => (100 * v) / maxTot + '%';
        const bar = el('div', { class: 'bbar' }, [el('span', { class: 'seg-ff', style: { width: W(ff) } }), el('span', { class: 'seg-fb', style: { width: W(fb) } }), el('span', { class: 'seg-gap', style: { width: W(gp) } })]);
        const line = el('a', { class: 'brow' + (k === g.key ? '' : ' dim'), href: TC.drillHref(t.name, r.short) }, [el('span', { class: 'ell', title: r.id, text: r.short }), bar, el('span', { class: 'num', text: TC.pct(TC.stat(r, S.joint, 'fbShare')) })]);
        line.addEventListener('mousemove', (e) => TC.tip(e, `<b>${TC.esc(r.id)}</b><br><span class="k">ff</span> ${ff.toFixed(2)} · <span class="k">fb</span> ${fb.toFixed(2)} · <span class="k">gap</span> ${gp.toFixed(3)} N·m<br><span class="k">FB share</span> ${TC.pct(TC.stat(r, S.joint, 'fbShare'))} · <span class="k">RMS error</span> ${TC.deg(TC.stat(r, S.joint, 'rmsErr'))}`));
        line.addEventListener('mouseleave', () => TC.tip(null));
        budget.appendChild(line);
      });
    }
    body.appendChild(budget);
    sideBody.appendChild(body);
    requestAnimationFrame(() => {
      const layers = [];
      for (const gg of TC.GROUPS) {
        const rs = TC.groupRuns(t, gg.key, keep);
        if (!rs.length) continue;
        const mode = gg.key === 'sim' ? 'lines' : TC.encodingFor(rs.length, 'auto', S.threshold);
        layers.push({ key: gg.key, color: gg.key === g.key || gg.key === 'sim' ? gg.color : '#b9b8b1', label: gg.short, mode, dash: gg.key === 'sim', runs: rs.map((r) => ({ run: r, y: TC.series(r, 'err', S.joint) })) });
        legend.appendChild(el('span', { class: 'lg' }, [el('span', { class: 'sw', style: { background: layers[layers.length - 1].color } }), `${gg.short} `, el('span', { class: 'faint', text: `n=${rs.length} · ${mode === 'bands' ? 'fan' : 'lines'}` })]));
      }
      // selected group drawn last (on top)
      layers.sort((a, b) => (a.key === g.key) - (b.key === g.key));
      detailChart = TC.fanChart(host, { x: t.t, layers, height: 200, yFmt: (v) => v.toFixed(2) + '°', yUnit: '°', readout, zeroLine: true,
        onPick: (hit) => (hit.run ? TC.drill(t.name, hit.run.short) : TC.drill(t.name, 'group/' + hit.layer.key)) });
    });
  }
  function renderAll() { renderToolbar(); renderTable(); renderDetail(); }
  renderAll();
  window.TCS_V2 = { S, renderAll };
})();
