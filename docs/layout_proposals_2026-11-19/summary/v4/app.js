/* V4 · Torque budget board — torque first: per target, a beeswarm of FB share by config group and one stacked
   feedforward | feedback | drive-gap bar per run (or per group, aggregated); tracking error is the secondary column.
   Click a bar: the drawer below plays that run's five torques over time against its group's feedback band.
   SIMULATED fixture; prototype stats. */
(function () {
  'use strict';
  const { el, svg } = TC;
  const S = {
    joint: TC.store.get('v4:joint', 0),
    unit: TC.store.get('v4:unit', 'share'),
    sort: TC.store.get('v4:sort', 'fb'),
    rows: TC.store.get('v4:rows', 'runs'),
    dateOff: new Set(TC.store.get('v4:dateOff', [])),
    selected: TC.store.get('v4:selected', 'full-circle-slow/real-03'),
    threshold: 5,
  };
  const save = () => { for (const k of ['joint', 'unit', 'sort', 'rows', 'selected']) TC.store.set('v4:' + k, S[k]); TC.store.set('v4:dateOff', [...S.dateOff]); };
  const keep = (r) => !S.dateOff.has(r.date);
  const ORDER = ['v1', 'v2', 'sim'];

  const app = document.getElementById('app');
  app.appendChild(TC.header('V4 · Torque budget board'));
  const toolbar = el('div', { class: 'toolbar' });
  app.appendChild(toolbar);
  const body = el('div', { class: 'vsplit' });
  const board = el('main', { class: 'board' });
  const gutter = el('div', { class: 'gutter row' });
  const drawer = el('section', { class: 'side drawer' });
  const foldBtn = el('button', { class: 'iconbtn' });
  const dTitle = el('span', { class: 'side-title ell' });
  const dActions = el('span', { class: 'dactions' });
  drawer.append(el('div', { class: 'side-head' }, [foldBtn, dTitle, dActions, el('span', { class: 'vlabel', text: 'Run torque' })]));
  const dBody = el('div', { class: 'side-body dbody' });
  drawer.appendChild(dBody);
  body.append(board, gutter, drawer);
  app.appendChild(body);
  TC.splitter({ gutter, panel: drawer, key: 'v4:drawer', side: 'bottom', min: 150, max: 520, size: 258, foldBtn });

  function seg(options, value, onPick) {
    const s = el('div', { class: 'seg' });
    options.forEach(([v, label, tip]) => s.appendChild(el('button', { class: v === value ? 'on' : '', title: tip || '', text: label, 'data-v': String(v), onclick: () => onPick(v) })));
    return s;
  }
  function renderToolbar() {
    toolbar.innerHTML = '';
    toolbar.append(
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Joint' }), seg(TC.joints.map((j, i) => [i, j]).concat([[TC.joints.length, 'all']]), S.joint, (v) => { S.joint = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Bars' }), seg([['share', '% of command', 'Feedforward and feedback as shares of Σ|command|; the drive gap on top'], ['nm', 'mean |τ| N·m', 'Mean absolute torque per component']], S.unit, (v) => { S.unit = v; save(); renderBoard(); })]),
      el('span', { class: 'ctl', id: 'rows-ctl' }, [el('span', { class: 'lab', text: 'Rows' }), seg([['runs', 'Per run'], ['groups', 'Per group', 'One aggregate bar per config group with its p25–p75 spread: what 100+ runs collapse to']], S.rows, (v) => { S.rows = v; save(); renderBoard(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Sort' }), seg([['fb', 'FB share'], ['num', 'Run #']], S.sort, (v) => { S.sort = v; save(); renderBoard(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Date' }), ...TC.dates.map((d) => el('span', { class: 'chip ' + (S.dateOff.has(d) ? 'off' : 'on'), onclick: () => { S.dateOff.has(d) ? S.dateOff.delete(d) : S.dateOff.add(d); save(); renderAll(); } }, [TC.shortDate(d)]))]),
      el('span', { class: 'spacer' }),
      el('span', { class: 'legend' }, [el('span', { class: 'sw ff' }), 'feedforward', el('span', { class: 'sw fb' }), 'feedback', el('span', { class: 'sw gap' }), 'drive gap', el('span', { class: 'satmark' }), 'at drive limit']),
    );
  }

  // ---------- answer strip ----------
  function answerFor(t) {
    const v1 = TC.groupRuns(t, 'v1', keep), v2 = TC.groupRuns(t, 'v2', keep);
    const fb1 = v1.length ? TC.median(v1.map((r) => TC.stat(r, S.joint, 'fbShare'))) : null;
    const fb2 = v2.length ? TC.median(v2.map((r) => TC.stat(r, S.joint, 'fbShare'))) : null;
    const sat = t.runs.filter(keep).filter((r) => r.kind === 'real' && TC.stat(r, S.joint, 'satFrac') > 0.01);
    const v = TC.verdict(t, S.joint, keep);
    const cell = el('div', { class: 'acell' });
    cell.appendChild(el('div', { class: 'atitle ell', title: t.title, text: t.title }));
    if (fb1 != null && fb2 != null) {
      cell.appendChild(el('div', { class: 'aline num' }, [el('span', { text: 'feedback supplies ' }), el('b', { text: TC.pct(fb1) }), el('span', { class: 'muted', text: ' with ff v1 → ' }), el('b', { text: TC.pct(fb2) }), el('span', { class: 'muted', text: ' with ff v2' })]));
      cell.appendChild(el('div', { class: 'asub num' }, [el('span', { text: `${Math.round(100 * (fb1 - fb2))} points less correction · RMS error ${TC.signedPct(v.delta)}` })]));
    } else {
      cell.appendChild(el('div', { class: 'aline num' }, [el('span', { text: 'feedback supplies ' }), el('b', { text: TC.pct(fb1) }), el('span', { class: 'muted', text: ' with ff v1' })]));
      cell.appendChild(el('div', { class: 'asub' }, [el('span', { text: 'no ff v2 runs yet' })]));
    }
    if (sat.length) {
      const fr = sat.map((r) => TC.stat(r, S.joint, 'satFrac'));
      cell.appendChild(el('span', { class: 'flag-warn atag', title: 'Commanded torque at the drive limit (max_torque_nm) — the feedback cannot add more', text: `${sat.length} runs at the ${TC.maxTorque[Math.min(S.joint, TC.joints.length - 1)]} N·m limit ${TC.pct(Math.min(...fr))}–${TC.pct(Math.max(...fr))} of the time` }));
    }
    return cell;
  }

  // ---------- beeswarm ----------
  function swarm(t, W) {
    const H = 92, left = 50, right = 10;
    const s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'swarm' });
    const runs = t.runs.filter(keep);
    const hi = Math.max(0.3, Math.ceil((Math.max(...runs.map((r) => TC.stat(r, S.joint, 'fbShare'))) + 0.02) * 10) / 10);
    const x = (v) => left + (v / hi) * (W - left - right);
    for (let v = 0; v <= hi + 1e-9; v += 0.1) {
      s.appendChild(svg('line', { x1: x(v), x2: x(v), y1: 4, y2: H - 16, stroke: '#efeee9' }));
      const tx = svg('text', { x: x(v), y: H - 4, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#8a8983' }); tx.textContent = Math.round(v * 100) + '%'; s.appendChild(tx);
    }
    const rows = ORDER.filter((k) => runs.some((r) => r.group === k));
    const rowH = (H - 22) / 3;
    rows.forEach((k, i) => {
      const y = 6 + rowH * i + rowH / 2;
      const g = TC.group(k);
      const lab = svg('text', { x: 0, y: y + 3.5, 'font-size': 10.5, fill: '#52514e' }); lab.textContent = g.short; s.appendChild(lab);
      const rs = runs.filter((r) => r.group === k);
      const vals = rs.map((r) => TC.stat(r, S.joint, 'fbShare'));
      if (rs.length > S.threshold) {
        const sm = TC.summary(vals);
        s.appendChild(svg('line', { x1: x(sm.min), x2: x(sm.max), y1: y, y2: y, stroke: g.color, 'stroke-width': 1 }));
        s.appendChild(svg('rect', { x: x(sm.p25), y: y - 7, width: Math.max(2, x(sm.p75) - x(sm.p25)), height: 14, fill: TC.hexA(g.color, 0.16), stroke: TC.hexA(g.color, 0.6), rx: 2 }));
      }
      if (rs.length > 1) { const md = TC.median(vals); s.appendChild(svg('line', { x1: x(md), x2: x(md), y1: y - 9, y2: y + 9, stroke: '#22211f', 'stroke-width': 1.6 })); }
      // beeswarm: place dots left→right, nudging vertically on collision
      const placed = [];
      rs.slice().sort((a, b) => TC.stat(a, S.joint, 'fbShare') - TC.stat(b, S.joint, 'fbShare')).forEach((r) => {
        const cx = x(TC.stat(r, S.joint, 'fbShare'));
        let dy = 0;
        for (const off of [0, -5, 5, -10, 10]) { if (!placed.some((p) => Math.abs(p[0] - cx) < 8 && Math.abs(p[1] - off) < 8)) { dy = off; break; } }
        placed.push([cx, dy]);
        const dot = svg('circle', { cx, cy: y + dy, r: 4, fill: g.color, 'fill-opacity': 0.88, stroke: S.selected === r.id ? '#22211f' : '#fff', 'stroke-width': S.selected === r.id ? 2 : 1 });
        dot.classList.add('pick');
        dot.addEventListener('mousemove', (e) => TC.tip(e, tipHtml(r)));
        dot.addEventListener('mouseleave', () => TC.tip(null));
        dot.addEventListener('click', () => select(r));
        dot.addEventListener('dblclick', () => TC.drill(r.target, r.short));
        s.appendChild(dot);
      });
    });
    return s;
  }
  function tipHtml(r) {
    const st = (k) => TC.stat(r, S.joint, k);
    return `<b>${TC.esc(r.id)}</b> · ${TC.esc(r.title)} · ${r.date}<br><span class="k">FB share</span> ${TC.pct(st('fbShare'))} · <span class="k">mean |ff|</span> ${st('ffMav').toFixed(2)} · <span class="k">|fb|</span> ${st('fbMav').toFixed(2)} · <span class="k">drive gap</span> ${st('gapMav').toFixed(3)} N·m<br><span class="k">at limit</span> ${TC.pct(st('satFrac'))} · <span class="k">RMS error</span> ${TC.deg(st('rmsErr'))}<br><span class="k">click: torque over time below · double-click: run view</span>`;
  }

  // ---------- bars ----------
  function bar(ff, fb, gap, sat, scale) {
    const tot = ff + fb;
    let w;
    if (S.unit === 'share') w = { ff: (100 * ff) / tot, fb: (100 * fb) / tot, gap: (100 * gap) / tot };
    else w = { ff: (100 * ff) / scale, fb: (100 * fb) / scale, gap: (100 * gap) / scale };
    const b = el('div', { class: 'bar' }, [el('span', { class: 'seg-ff', style: { width: w.ff + '%' } }), el('span', { class: 'seg-fb', style: { width: w.fb + '%' } }), el('span', { class: 'seg-gap', style: { width: w.gap + '%' } })]);
    if (sat > 0.01) b.appendChild(el('span', { class: 'satmark on', title: `command at the drive limit ${TC.pct(sat)} of the time` }));
    return b;
  }
  function column(t) {
    const col = el('section', { class: 'col' });
    const runs = t.runs.filter(keep);
    const v = TC.verdict(t, S.joint, keep);
    col.appendChild(el('div', { class: 'chead' }, [el('span', { class: 'ctitle ell', title: `${t.title} — ${t.description}`, text: t.title }), el('a', { class: 'drill', href: TC.drillHref(t.name, 'all'), text: 'run view ↗' })]));
    col.appendChild(el('div', { class: 'csec' }, [el('span', { text: `FB share by config · ${TC.jointLabel(S.joint)}` }), el('span', { class: 'faint', text: 'dot = run · box once n > 5' })]));
    const sw = el('div', { class: 'swarmbox' });
    col.appendChild(sw);
    col.appendChild(el('div', { class: 'csec' }, [el('span', { text: S.rows === 'runs' ? 'Budget per run' : 'Budget per group' }),
      el('span', { class: 'faint', text: S.unit === 'share' ? '% of Σ|command| · gap on top' : 'mean |τ| (N·m)' }), el('span', { class: 'errhead', title: 'Secondary: RMS tracking error of the run (°)', text: 'error' })]));
    const scale = Math.max(...runs.map((r) => TC.stat(r, S.joint, 'ffMav') + TC.stat(r, S.joint, 'fbMav') + TC.stat(r, S.joint, 'gapMav')));
    const list = el('div', { class: 'bars' });
    for (const k of ORDER) {
      let rs = runs.filter((r) => r.group === k);
      if (!rs.length) continue;
      const g = TC.group(k);
      if (S.rows === 'groups') {
        const agg = (key) => rs.reduce((a, r) => a + TC.stat(r, S.joint, key), 0) / rs.length;
        const fbs = TC.summary(rs.map((r) => TC.stat(r, S.joint, 'fbShare')));
        const b = bar(agg('ffMav'), agg('fbMav'), agg('gapMav'), Math.max(...rs.map((r) => TC.stat(r, S.joint, 'satFrac'))), scale);
        if (S.unit === 'share' && fbs.n > 1) b.appendChild(el('span', { class: 'iqr', title: `per-run FB share p25–p75 ${TC.pct(fbs.p25)}–${TC.pct(fbs.p75)}`, style: { left: 100 * (1 - fbs.p75) + '%', width: 100 * (fbs.p75 - fbs.p25) + '%' } }));
        const row = el('div', { class: 'brow agg', onclick: () => TC.drill(t.name, 'group/' + k), title: 'Open this group in the run view' }, [
          el('span', { class: 'blab ell' }, [el('span', { class: 'sw', style: { background: g.color } }), ` ${g.short}`]), b,
          el('span', { class: 'bfb num', text: TC.pct(fbs.p50) }), el('span', { class: 'berr num', text: TC.deg(TC.median(rs.map((r) => TC.stat(r, S.joint, 'rmsErr')))) }),
          el('span', { class: 'bn faint num', text: `n=${rs.length}` })]);
        list.appendChild(row);
        continue;
      }
      list.appendChild(el('div', { class: 'bgroup' }, [el('span', { class: 'sw', style: { background: g.color } }), g.label, el('span', { class: 'faint', text: ` · ${rs.length}` })]));
      rs = S.sort === 'fb' ? rs.slice().sort((a, b) => TC.stat(b, S.joint, 'fbShare') - TC.stat(a, S.joint, 'fbShare')) : rs.slice().sort((a, b) => a.num - b.num);
      rs.forEach((r) => {
        const st = (k2) => TC.stat(r, S.joint, k2);
        const row = el('div', { class: 'brow' + (S.selected === r.id ? ' selected' : ''), 'data-run': r.id, onclick: () => select(r), ondblclick: () => TC.drill(r.target, r.short) }, [
          el('span', { class: 'blab ell', title: `${r.id} — ${r.title} · ${r.date}`, text: r.short }),
          bar(st('ffMav'), st('fbMav'), st('gapMav'), st('satFrac'), scale),
          el('span', { class: 'bfb num', text: TC.pct(st('fbShare')) }),
          el('span', { class: 'berr num', text: TC.deg(st('rmsErr')) }),
          el('a', { class: 'drill', href: TC.drillHref(r.target, r.short), title: 'Open the run view', text: '↗', onclick: (e) => e.stopPropagation() }),
        ]);
        row.addEventListener('mousemove', (e) => TC.tip(e, tipHtml(r)));
        row.addEventListener('mouseleave', () => TC.tip(null));
        list.appendChild(row);
      });
    }
    col.appendChild(list);
    requestAnimationFrame(() => sw.appendChild(swarm(t, Math.max(200, sw.clientWidth))));
    return col;
  }
  const answer = el('div', { class: 'answer' });
  const cols = el('div', { class: 'cols' });
  board.append(answer, cols);
  function renderBoard() {
    answer.innerHTML = ''; cols.innerHTML = '';
    TC.targets.forEach((t) => { answer.appendChild(answerFor(t)); cols.appendChild(column(t)); });
  }

  // ---------- drawer: one run's five torques over time ----------
  let chart = null;
  function select(r) { S.selected = r.id; save(); renderBoard(); renderDrawer(); }
  function renderDrawer() {
    TC.destroyChart(chart); chart = null;
    const r = TC.run(S.selected) || TC.runs[1];
    const t = TC.target(r.target), g = TC.group(r.group);
    const j = Math.min(S.joint, TC.joints.length - 1);
    dTitle.innerHTML = '';
    dTitle.append(el('span', { class: 'sw', style: { background: g.color } }), ` ${r.id} `, el('span', { class: 'faint', text: `· ${r.title} · ${TC.joints[j]}${S.joint >= TC.joints.length ? ' (drawer shows one joint)' : ''}` }));
    dTitle.title = `${r.id} — ${r.title}`;
    dActions.innerHTML = '';
    dActions.append(el('a', { class: 'btn primary', href: TC.drillHref(r.target, r.short), text: 'Open run view ↗' }));
    dBody.innerHTML = '';
    const st = (k) => r.stats[j][k];
    const facts = el('div', { class: 'facts' }, [
      fact('FB share', TC.pct(st('fbShare'))), fact('cmd RMS', TC.nm(st('cmdRms'))), fact('ff RMS', TC.nm(st('ffRms'))), fact('fb RMS', TC.nm(st('fbRms'))),
      fact('target − cmd RMS', TC.nm(st('tgtCmdRms'))), fact('drive gap RMS', TC.nm(st('gapRms'), 3)), fact('peak |cmd|', TC.nm(st('peakCmd')), st('satFrac') > 0.01 ? `at limit ${TC.pct(st('satFrac'))}` : null),
      fact('RMS error', TC.deg(st('rmsErr'))),
    ]);
    const legend = el('div', { class: 'tlegend' }, [
      li('#8a8983', 'target', true), li(g.color, 'commanded', false, 3), li(TC.C.ff, 'feedforward'), li(TC.C.fb, 'feedback'), li('#22211f', 'applied', false, 1),
      el('span', { class: 'lg' }, [el('span', { class: 'bandsw' }), `${g.short} feedback band (n=${TC.groupRuns(t, r.group, keep).length})`]),
    ]);
    const host = el('div', { class: 'tplot' });
    const readout = el('div', { class: 'plot-readout', html: '&nbsp;' });
    dBody.append(el('div', { class: 'dgrid' }, [facts, el('div', { class: 'dright' }, [legend, host, readout])]));
    requestAnimationFrame(() => {
      const x = t.t;
      const peers = TC.groupRuns(t, r.group, keep);
      const layers = [];
      if (peers.length >= 3) layers.push({ key: 'band', color: TC.C.fb, label: g.short + ' feedback', mode: 'bands', runs: peers.map((p) => ({ run: p, y: TC.series(p, 'fb', j) })) });
      const overlay = [
        // CONTRACT.md: target dashed, commanded (run colour) thickest, feedforward, feedback, applied thin
        { run: { short: 'target' }, y: TC.resample(t.t, t.tau[j], x), color: '#8a8983', dash: [5, 4], width: 1.4 },
        { run: { short: 'ff' }, y: TC.series(r, 'ff', j), color: TC.C.ff, width: 1.4 },
        { run: { short: 'fb' }, y: TC.series(r, 'fb', j), color: TC.C.fb, width: 1.4 },
        { run: { short: 'applied' }, y: TC.series(r, 'applied', j), color: '#22211f', width: 1 },
        { run: { short: 'commanded' }, y: TC.series(r, 'cmd', j), color: g.color, width: 2.6 },
      ];
      const h = Math.max(110, dBody.clientHeight - 54);
      chart = TC.fanChart(host, { x, layers, overlay, height: h, yFmt: (v) => v.toFixed(2) + ' N·m', yUnit: '', readout, zeroLine: true });
    });
  }
  function fact(label, value, flag) { return el('div', { class: 'fact' }, [el('span', { class: 'flab', text: label }), el('b', { class: 'num', text: value }), flag ? el('span', { class: 'flag-warn', text: flag }) : null]); }
  function li(color, label, dashed, w = 1.6) { return el('span', { class: 'lg' }, [el('span', { class: 'line' + (dashed ? ' dashed' : ''), style: { background: dashed ? 'none' : color, borderColor: color, height: w + 'px' } }), label]); }

  function renderAll() { renderToolbar(); renderBoard(); renderDrawer(); }
  window.addEventListener('tcs:layout', () => { if (chart) { clearTimeout(window._v4t); window._v4t = setTimeout(renderDrawer, 60); } });
  renderAll();
  window.TCS_V4 = { S, renderAll, select, chart: () => chart };
})();
