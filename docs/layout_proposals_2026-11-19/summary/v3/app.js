/* V3 · Target cards — small multiples: one card per target with its verdict line, its error fan per config group, a
   torque-budget bar per group and a strip of its runs; the grid is the page. ⤢ focuses one card full width with its run
   list beside it (draggable split). SIMULATED fixture; prototype stats. */
(function () {
  'use strict';
  const { el, svg } = TC;
  const S = {
    joint: TC.store.get('v3:joint', 0),
    metric: TC.store.get('v3:metric', 'err'),
    enc: TC.store.get('v3:enc', 'auto'),
    threshold: 5,
    dateOff: new Set(TC.store.get('v3:dateOff', [])),
    groupOff: new Set(TC.store.get('v3:groupOff', [])), // `${target}|${group}`
    runOff: new Set(TC.store.get('v3:runOff', [])),
    focus: TC.store.get('v3:focus', null),
    hover: null,
  };
  const save = () => { for (const k of ['joint', 'metric', 'enc', 'focus']) TC.store.set('v3:' + k, S[k]); for (const k of ['dateOff', 'groupOff', 'runOff']) TC.store.set('v3:' + k, [...S[k]]); };
  const keep = (r) => !S.dateOff.has(r.date) && !S.runOff.has(r.id);
  const METRICS = {
    err: { label: 'Tracking error', sub: 'target − run (°)', fmt: (v) => v.toFixed(2) + '°', unit: '°', zero: true },
    fbabs: { label: 'Feedback torque', sub: '|τ_fb| (N·m)', fmt: (v) => v.toFixed(2) + ' N·m', unit: '' },
    share: { label: 'FB share', sub: 'rolling 0.2 s (%)', fmt: (v) => v.toFixed(0) + '%', unit: '%', range: [0, 100] },
  };

  const app = document.getElementById('app');
  app.appendChild(TC.header('V3 · Target cards'));
  const toolbar = el('div', { class: 'toolbar' });
  const page = el('div', { class: 'cardpage' });
  app.append(toolbar, page);

  function seg(options, value, onPick) {
    const s = el('div', { class: 'seg' });
    options.forEach(([v, label, tip]) => s.appendChild(el('button', { class: v === value ? 'on' : '', title: tip || '', text: label, 'data-v': String(v), onclick: () => onPick(v) })));
    return s;
  }
  function renderToolbar() {
    toolbar.innerHTML = '';
    toolbar.append(
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Joint' }), seg(TC.joints.map((j, i) => [i, j]).concat([[TC.joints.length, 'all']]), S.joint, (v) => { S.joint = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Fan of' }), seg(Object.entries(METRICS).map(([k, m]) => [k, m.label]), S.metric, (v) => { S.metric = v; save(); renderAll(); })]),
      el('span', { class: 'ctl', id: 'enc' }, [el('span', { class: 'lab', text: 'Repeats' }), seg([['auto', 'Auto', 'Lines while a group has ≤ 5 runs, fan above'], ['lines', 'Lines'], ['bands', 'Bands', 'Median, IQR, p5–p95, min–max']], S.enc, (v) => { S.enc = v; save(); renderAll(); })]),
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Date' }), ...TC.dates.map((d) => el('span', { class: 'chip ' + (S.dateOff.has(d) ? 'off' : 'on'), onclick: () => { S.dateOff.has(d) ? S.dateOff.delete(d) : S.dateOff.add(d); save(); renderAll(); } },
        [TC.shortDate(d), el('span', { class: 'n', text: String(TC.runs.filter((r) => r.date === d).length) })]))]),
      el('span', { class: 'spacer' }),
      el('span', { class: 'faint hint', text: S.focus ? 'Esc or ✕ returns to the grid' : '⤢ focuses a card · click a dot, line or band to open it' }),
    );
  }

  const charts = {};
  function layersFor(t) {
    const out = [];
    for (const g of TC.GROUPS) {
      if (S.groupOff.has(t.name + '|' + g.key)) continue;
      const runs = TC.groupRuns(t, g.key, keep);
      if (!runs.length) continue;
      const mode = g.key === 'sim' ? 'lines' : TC.encodingFor(runs.length, S.enc, S.threshold);
      out.push({ key: g.key, color: g.color, label: g.short, mode, dash: g.key === 'sim', runs: runs.map((r) => ({ run: r, y: TC.series(r, S.metric, S.joint) })) });
    }
    return out;
  }
  function drawChart(t, height) {
    const c = charts[t.name]; if (!c) return;
    TC.destroyChart(c.u);
    const m = METRICS[S.metric];
    const overlay = [];
    const hr = S.hover && TC.run(S.hover);
    if (hr && hr.target === t.name) overlay.push({ run: hr, y: TC.series(hr, S.metric, S.joint), color: '#22211f' });
    c.u = TC.fanChart(c.host, { x: t.t, layers: layersFor(t), overlay, height, yFmt: m.fmt, yUnit: m.unit, readout: c.readout, zeroLine: m.zero, yRange: m.range,
      onPick: (hit) => (hit.run ? TC.drill(t.name, hit.run.short) : TC.drill(t.name, 'group/' + hit.layer.key)) });
  }

  function verdictBox(t) {
    const v = TC.verdict(t, S.joint, keep);
    const box = el('div', { class: 'verdict' });
    if (v.hasBoth) {
      const g = TC.group(v.winner);
      box.append(
        el('div', { class: 'vwho' }, [el('span', { class: 'sw', style: { background: g.color } }), el('b', { text: g.label }), el('span', { class: 'muted', text: ' tracks better' })]),
        el('div', { class: 'vnums' }, [
          el('div', { class: 'big' }, [el('span', { class: 'num', text: TC.signedPct(v.delta) }), el('small', { text: 'RMS error' })]),
          el('div', { class: 'mid num' }, [el('span', { text: `${TC.deg(v.medA)} → ${TC.deg(v.medB)}` }), el('small', { text: 'median, v1 → v2' })]),
          el('div', { class: 'mid num' }, [el('span', { text: `${TC.pct(v.fbA)} → ${TC.pct(v.fbB)}` }), el('small', { text: 'FB share' })]),
        ]),
        el('div', { class: 'vconf conf ' + v.conf, title: `Probability of superiority over every v1 × v2 run pair: ${TC.confText(v)}`, text: `${v.conf} confidence · ${Math.round(v.winner === 'v2' ? v.wins : v.pairs - v.wins)} of ${v.pairs} run pairs · n ${v.b.length} vs ${v.a.length}` }),
      );
    } else {
      const runs = v.a.length ? v.a : v.b;
      box.classList.add('single');
      box.append(
        el('div', { class: 'vwho' }, [el('span', { class: 'sw', style: { background: TC.C.v1 } }), el('b', { text: 'ff v1 nominal only' }), el('span', { class: 'muted', text: ' · no comparison yet' })]),
        el('div', { class: 'vnums' }, [
          el('div', { class: 'big' }, [el('span', { class: 'num', text: TC.deg(v.medA) }), el('small', { text: 'median RMS error' })]),
          el('div', { class: 'mid num' }, [el('span', { text: TC.pct(v.fbA) }), el('small', { text: 'FB share' })]),
          el('div', { class: 'mid num' }, [el('span', { text: String(runs.length) }), el('small', { text: 'runs' })]),
        ]),
        el('div', { class: 'vconf faint', text: 'Run ff v2 calibrated on this target to get a verdict.' }),
      );
    }
    return box;
  }
  function groupChips(t) {
    const box = el('div', { class: 'gchips' });
    for (const g of TC.GROUPS) {
      const runs = TC.groupRuns(t, g.key, keep);
      if (!TC.groupRuns(t, g.key).length) continue;
      const off = S.groupOff.has(t.name + '|' + g.key);
      const mode = g.key === 'sim' ? 'line' : TC.encodingFor(runs.length, S.enc, S.threshold) === 'bands' ? 'fan' : 'lines';
      box.appendChild(el('span', { class: 'chip ' + (off ? 'off' : 'on'), title: `${off ? 'Show' : 'Hide'} ${g.label} on this card (${runs.length} runs, drawn as ${mode})`,
        onclick: () => { off ? S.groupOff.delete(t.name + '|' + g.key) : S.groupOff.add(t.name + '|' + g.key); save(); renderAll(); } },
        [el('span', { class: 'sw', style: { background: g.color } }), g.short, el('span', { class: 'n', text: `${runs.length} · ${mode}` })]));
    }
    return box;
  }
  function budget(t) {
    const box = el('div', { class: 'budget' });
    box.appendChild(el('div', { class: 'csec' }, [el('span', { text: 'Torque budget · share of |command|' }),
      el('span', { class: 'blegend' }, [el('span', { class: 'sw ff' }), 'ff', el('span', { class: 'sw fb' }), 'fb', el('span', { class: 'sw gap' }), 'drive gap'])]));
    for (const g of TC.GROUPS.slice().reverse()) {
      const runs = TC.groupRuns(t, g.key, keep);
      if (!runs.length) continue;
      const sff = runs.reduce((a, r) => a + TC.stat(r, S.joint, 'ffMav'), 0), sfb = runs.reduce((a, r) => a + TC.stat(r, S.joint, 'fbMav'), 0), sg = runs.reduce((a, r) => a + TC.stat(r, S.joint, 'gapMav'), 0);
      const tot = sff + sfb;
      const sat = runs.filter((r) => TC.stat(r, S.joint, 'satFrac') > 0.01).length;
      const fbs = TC.summary(runs.map((r) => TC.stat(r, S.joint, 'fbShare')));
      const bar = el('div', { class: 'bbar', title: `${g.label}: feedforward ${TC.pct(sff / tot)}, feedback ${TC.pct(sfb / tot)} of Σ|command|; drive gap ${TC.pct(sg / tot, 1)} on top. Per-run FB share ${TC.pct(fbs.min)}–${TC.pct(fbs.max)}.` }, [
        el('span', { class: 'seg-ff', style: { width: (100 * sff) / (tot + sg) + '%' } }),
        el('span', { class: 'seg-fb', style: { width: (100 * sfb) / (tot + sg) + '%' } }),
        el('span', { class: 'seg-gap', style: { width: (100 * sg) / (tot + sg) + '%' } }),
      ]);
      // per-run FB-share spread drawn as a whisker inside the bar
      if (fbs.n > 1) bar.appendChild(el('span', { class: 'whisk', style: { left: (100 * (1 - fbs.max)) * (tot / (tot + sg)) + '%', width: (100 * (fbs.max - fbs.min)) * (tot / (tot + sg)) + '%' } }));
      box.appendChild(el('div', { class: 'brow' }, [el('span', { class: 'blab ell', title: g.label, text: g.short }), bar,
        el('span', { class: 'bval num', html: `<b>${TC.pct(sfb / tot)}</b> fb` }),
        sat ? el('span', { class: 'flag-warn', title: `${sat} of ${runs.length} runs hold the command at the drive limit for > 1 % of samples`, text: `${sat}/${runs.length} sat.` }) : el('span', { class: 'bsat' })]));
    }
    return box;
  }
  function strip(t, W) {
    const runs = t.runs.filter(keep);
    const box = el('div', { class: 'strip' });
    box.appendChild(el('div', { class: 'csec' }, [el('span', { text: `Runs · RMS error ${TC.jointLabel(S.joint)}` }), el('span', { class: 'faint', text: 'hover draws it on the fan · click opens it' })]));
    if (!runs.length) return box;
    const H = 18 * 3 + 16;
    const hi = Math.max(...runs.map((r) => TC.stat(r, S.joint, 'rmsErr'))) * 1.08 || 1;
    const x = (v) => 44 + (v / hi) * (W - 54);
    const s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const rows = ['sim', 'v1', 'v2'].filter((k) => runs.some((r) => r.group === k));
    rows.forEach((k, i) => {
      const y = 9 + i * 18;
      const lab = svg('text', { x: 0, y: y + 4, 'font-size': 10.5, fill: '#8a8983' }); lab.textContent = TC.group(k).short; s.appendChild(lab);
      s.appendChild(svg('line', { x1: 44, x2: W - 6, y1: y, y2: y, stroke: '#efeee9' }));
      const rs = runs.filter((r) => r.group === k);
      if (rs.length > 1) { const md = TC.median(rs.map((r) => TC.stat(r, S.joint, 'rmsErr'))); s.appendChild(svg('line', { x1: x(md), x2: x(md), y1: y - 7, y2: y + 7, stroke: '#22211f', 'stroke-width': 1.5 })); }
      rs.forEach((r) => {
        const v = TC.stat(r, S.joint, 'rmsErr');
        const dot = k === 'sim' ? svg('rect', { x: x(v) - 4, y: y - 4, width: 8, height: 8, transform: `rotate(45 ${x(v)} ${y})`, fill: '#fff', stroke: TC.group(k).color, 'stroke-width': 1.5 })
          : svg('circle', { cx: x(v), cy: y, r: 4.2, fill: TC.group(k).color, 'fill-opacity': 0.85, stroke: '#fff', 'stroke-width': 1 });
        dot.classList.add('pick');
        if (S.hover === r.id) { dot.setAttribute('stroke', '#22211f'); dot.setAttribute('stroke-width', 2); }
        dot.addEventListener('mouseenter', (e) => { S.hover = r.id; drawChart(t, charts[t.name].height); });
        dot.addEventListener('mousemove', (e) => TC.tip(e, `<b>${TC.esc(r.id)}</b> · ${TC.esc(r.title)} · ${r.date}<br><span class="k">RMS error</span> ${TC.deg(v)} · <span class="k">FB share</span> ${TC.pct(TC.stat(r, S.joint, 'fbShare'))}<br><span class="k">click to open the run view</span>`));
        dot.addEventListener('mouseleave', () => { TC.tip(null); S.hover = null; drawChart(t, charts[t.name].height); });
        dot.addEventListener('click', () => TC.drill(t.name, r.short));
        s.appendChild(dot);
      });
    });
    const yAx = 9 + rows.length * 18 - 4;
    const step = hi > 3 ? 1 : hi > 1.2 ? 0.5 : 0.25;
    for (let v = 0; v <= hi; v += step) { const tx = svg('text', { x: x(v), y: yAx + 8, 'font-size': 9.5, fill: '#8a8983', 'text-anchor': 'middle' }); tx.textContent = v.toFixed(step < 1 ? 2 : 0) + '°'; s.appendChild(tx); }
    box.appendChild(s);
    return box;
  }

  function card(t, focused) {
    const nAll = t.runs.length, nShown = t.runs.filter(keep).length;
    const sat = t.runs.filter(keep).filter((r) => r.kind === 'real' && TC.stat(r, S.joint, 'satFrac') > 0.01).length;
    const c = el('article', { class: 'card' + (focused ? ' focused' : ''), 'data-target': t.name });
    c.appendChild(el('div', { class: 'chead' }, [
      el('div', { class: 'ctitle ell', title: t.title, text: t.title }),
      el('span', { class: 'faint num', text: `${nShown}/${nAll} runs` }),
      focused ? el('button', { class: 'iconbtn', title: 'Back to the grid (Esc)', text: '✕', onclick: () => { S.focus = null; save(); renderAll(); } })
        : el('button', { class: 'iconbtn focusbtn', title: 'Focus this card full width', text: '⤢', onclick: () => { S.focus = t.name; save(); renderAll(); } }),
    ]));
    c.appendChild(el('div', { class: 'cdesc ell', title: t.description, text: t.description }));
    c.appendChild(verdictBox(t));
    const m = METRICS[S.metric];
    c.appendChild(el('div', { class: 'csec' }, [el('span', { text: `${m.label} · ${TC.jointLabel(S.joint)}` }), el('span', { class: 'faint', text: m.sub })]));
    c.appendChild(groupChips(t));
    const host = el('div', { class: 'plot' });
    const readout = el('div', { class: 'plot-readout', html: '&nbsp;' });
    c.append(host, readout);
    charts[t.name] = { host, readout, height: focused ? 250 : 222 };
    c.appendChild(budget(t));
    c.appendChild(strip(t, focused ? 620 : 420));
    c.appendChild(el('div', { class: 'cfoot' }, [
      el('a', { class: 'btn', href: TC.drillHref(t.name, 'all'), text: 'Open run view ↗' }),
      sat ? el('span', { class: 'flag-warn', title: 'Runs whose command sits at the drive limit for > 1 % of samples', text: `${sat} runs saturate the drive` }) : el('span', { class: 'faint', text: 'no saturation' }),
    ]));
    return c;
  }

  function runList(t) {
    const box = el('div', { class: 'runlist' });
    for (const g of TC.GROUPS) {
      const rs = t.runs.filter((r) => r.group === g.key && !S.dateOff.has(r.date));
      if (!rs.length) continue;
      const allOn = rs.every((r) => !S.runOff.has(r.id));
      box.appendChild(el('div', { class: 'rlgroup' }, [
        el('input', { type: 'checkbox', checked: allOn ? true : null, title: 'Select / deselect the whole group', onchange: () => { rs.forEach((r) => (allOn ? S.runOff.add(r.id) : S.runOff.delete(r.id))); save(); renderAll(); } }),
        el('span', { class: 'sw', style: { background: g.color } }), el('b', { text: g.label }), el('span', { class: 'faint', text: ` ${rs.length}` })]));
      rs.forEach((r) => {
        const on = !S.runOff.has(r.id);
        const row = el('label', { class: 'rlrow' + (on ? '' : ' off') }, [
          el('input', { type: 'checkbox', checked: on ? true : null, onchange: () => { on ? S.runOff.add(r.id) : S.runOff.delete(r.id); save(); renderAll(); } }),
          el('span', { class: 'ell', title: `${r.id} — ${r.title} · ${r.date}`, text: r.short }),
          el('span', { class: 'faint', text: TC.shortDate(r.date) }),
          el('span', { class: 'num', text: TC.deg(TC.stat(r, S.joint, 'rmsErr')) }),
          el('span', { class: 'num faint', text: TC.pct(TC.stat(r, S.joint, 'fbShare')) }),
          el('a', { class: 'drill', href: TC.drillHref(t.name, r.short), text: '↗', title: 'Open the run view' }),
        ]);
        row.addEventListener('mouseenter', () => { S.hover = r.id; drawChart(t, charts[t.name].height); });
        row.addEventListener('mouseleave', () => { S.hover = null; drawChart(t, charts[t.name].height); });
        box.appendChild(row);
      });
    }
    return box;
  }

  function renderPage() {
    for (const k of Object.keys(charts)) { TC.destroyChart(charts[k].u); delete charts[k]; }
    page.innerHTML = '';
    if (!S.focus) {
      const grid = el('div', { class: 'grid' });
      TC.targets.forEach((t) => grid.appendChild(card(t, false)));
      page.appendChild(grid);
    } else {
      const t = TC.target(S.focus);
      const others = el('div', { class: 'others' }, [el('span', { class: 'faint', text: 'Other targets:' }), ...TC.targets.filter((o) => o !== t).map((o) => {
        const v = TC.verdict(o, S.joint, keep);
        return el('button', { class: 'chip on', onclick: () => { S.focus = o.name; save(); renderAll(); }, title: 'Focus ' + o.title },
          [o.title, el('span', { class: 'n', text: v.hasBoth ? `${TC.group(v.winner).short} ${TC.signedPct(v.delta)}` : 'v1 only' })]);
      }), el('button', { class: 'btn', text: '▦ Back to grid', onclick: () => { S.focus = null; save(); renderAll(); } })]);
      page.appendChild(others);
      const split = el('div', { class: 'split-h focus-split' });
      const left = el('div', { class: 'focus-main' }, [card(t, true)]);
      const gutter = el('div', { class: 'gutter' });
      const side = el('aside', { class: 'side' });
      const foldBtn = el('button', { class: 'iconbtn' });
      side.append(el('div', { class: 'side-head' }, [foldBtn, el('span', { class: 'side-title', text: 'Runs of this target' }), el('span', { class: 'vlabel', text: 'Runs' })]),
        el('div', { class: 'side-body' }, [runList(t)]));
      split.append(left, gutter, side);
      page.appendChild(split);
      TC.splitter({ gutter, panel: side, key: 'v3:runs', side: 'right', min: 240, max: 620, size: 340, foldBtn });
    }
    requestAnimationFrame(() => { for (const name of Object.keys(charts)) drawChart(TC.target(name), charts[name].height); });
  }
  function renderAll() { renderToolbar(); renderPage(); }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.focus) { S.focus = null; save(); renderAll(); } });
  renderAll();
  window.TCS_V3 = { S, renderAll };
})();
