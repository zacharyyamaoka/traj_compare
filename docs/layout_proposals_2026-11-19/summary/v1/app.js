/* V1 · Scalars board — TensorBoard's Scalars page for repeats: runs on the left grouped by target (regex + tag filters,
   colour checkboxes, select-all per target); on the right one chart per metric × target over trajectory time, a percentile
   fan per config group once a group has more than N runs, a smoothing slider. SIMULATED fixture; prototype stats. */
(function () {
  'use strict';
  const { el } = TC;
  const S = {
    joint: TC.store.get('v1:joint', 0),
    enc: TC.store.get('v1:enc', 'auto'),
    threshold: TC.store.get('v1:threshold', 5),
    smooth: TC.store.get('v1:smooth', 0),
    regex: '',
    unchecked: new Set(TC.store.get('v1:unchecked', [])),
    tagOff: new Set(TC.store.get('v1:tagOff', [])),
    collapsedTargets: new Set(TC.store.get('v1:collapsedTargets', [])),
    collapsedSections: new Set(TC.store.get('v1:collapsedSections', ['gap'])),
    hover: null, pinned: null,
  };
  const save = () => {
    TC.store.set('v1:joint', S.joint); TC.store.set('v1:enc', S.enc); TC.store.set('v1:threshold', S.threshold); TC.store.set('v1:smooth', S.smooth);
    TC.store.set('v1:unchecked', [...S.unchecked]); TC.store.set('v1:tagOff', [...S.tagOff]);
    TC.store.set('v1:collapsedTargets', [...S.collapsedTargets]); TC.store.set('v1:collapsedSections', [...S.collapsedSections]);
  };
  const SECTIONS = [
    { key: 'err', title: 'Tracking error', sub: 'target − run (°)', fmt: (v) => v.toFixed(2) + '°', unit: '°', zero: true },
    { key: 'fbabs', title: 'Feedback torque', sub: '|τ_fb| (N·m)', fmt: (v) => v.toFixed(2) + ' N·m', unit: '' },
    { key: 'share', title: 'FB share of the command', sub: 'rolling 0.2 s (%)', fmt: (v) => v.toFixed(0) + '%', unit: '%', range: [0, 100] },
    { key: 'gap', title: 'Drive gap', sub: '|τ_cmd − τ_applied| (N·m)', fmt: (v) => v.toFixed(3) + ' N·m', unit: '' },
  ];
  const tagKeys = (r) => ['ff:' + r.group, 'date:' + r.date, 'kind:' + r.kind];
  function regexOk(r) {
    if (!S.regex) return true;
    let re; try { re = new RegExp(S.regex, 'i'); } catch (e) { return true; }
    return re.test(`${r.target}/${r.short} ${r.title} ${r.tags.ff_model} ${r.date}`);
  }
  const filtered = (r) => regexOk(r) && !tagKeys(r).some((k) => S.tagOff.has(k));
  const visible = (r) => filtered(r) && !S.unchecked.has(r.id);

  // ---------- frame ----------
  const app = document.getElementById('app');
  app.appendChild(TC.header('V1 · Scalars board'));
  const split = el('div', { class: 'split-h' });
  const side = el('aside', { class: 'side runs-side' });
  const foldBtn = el('button', { class: 'iconbtn', title: 'Fold panel' });
  const countEl = el('span', { class: 'count faint num' });
  side.appendChild(el('div', { class: 'side-head' }, [el('span', { class: 'side-title', text: 'Runs' }), countEl, foldBtn, el('span', { class: 'vlabel', text: 'Runs' })]));
  const sideBody = el('div', { class: 'side-body' });
  side.appendChild(sideBody);
  const gutter = el('div', { class: 'gutter' });
  const main = el('main', { class: 'main board' });
  split.append(side, gutter, main);
  app.appendChild(split);
  TC.splitter({ gutter, panel: side, key: 'v1:side', side: 'left', min: 200, max: 520, size: 288, foldBtn });

  // ---------- sidebar ----------
  const filterInput = el('input', { class: 'filter', type: 'search', placeholder: 'Filter runs (regex)', spellcheck: 'false' });
  filterInput.addEventListener('input', () => { S.regex = filterInput.value; renderSide(); renderBoard(); });
  const tagBox = el('div', { class: 'tags' });
  const groupsBox = el('div', { class: 'groups' });
  sideBody.append(el('div', { class: 'filterwrap' }, [filterInput]), tagBox, groupsBox,
    el('div', { class: 'side-foot' }, [
      el('div', { class: 'faint', text: 'Checkbox colour = config group. Hover a run to draw it over its fan; click to pin it.' }),
    ]));

  function renderTags() {
    tagBox.innerHTML = '';
    const rows = [
      ['ff model', TC.GROUPS.map((g) => ({ key: 'ff:' + g.key, label: g.key === 'sim' ? 'sim' : g.label.replace('ff ', ''), color: g.color, n: TC.runs.filter((r) => r.group === g.key).length }))],
      ['date', TC.dates.map((d) => ({ key: 'date:' + d, label: TC.shortDate(d), n: TC.runs.filter((r) => r.date === d).length }))],
      ['kind', ['real', 'sim'].map((k) => ({ key: 'kind:' + k, label: k, n: TC.runs.filter((r) => r.kind === k).length }))],
    ];
    for (const [name, chips] of rows) {
      const row = el('div', { class: 'tagrow' }, [el('span', { class: 'taglab', text: name })]);
      for (const c of chips) {
        const on = !S.tagOff.has(c.key);
        row.appendChild(el('span', { class: 'chip ' + (on ? 'on' : 'off'), title: (on ? 'Hide' : 'Show') + ` runs tagged ${name} = ${c.label}`,
          onclick: () => { on ? S.tagOff.add(c.key) : S.tagOff.delete(c.key); save(); renderSide(); renderBoard(); } },
          [c.color ? el('span', { class: 'sw', style: { background: c.color } }) : null, c.label, el('span', { class: 'n', text: String(c.n) })]));
      }
      tagBox.appendChild(row);
    }
  }

  function checkbox(color, state) {
    // state: 'on' | 'off' | 'mixed'
    return el('span', { class: 'cb ' + state, style: { '--c': color } });
  }
  function renderSide() {
    renderTags();
    groupsBox.innerHTML = '';
    let shown = 0;
    for (const t of TC.targets) {
      const runs = t.runs.filter(filtered);
      const vis = runs.filter((r) => !S.unchecked.has(r.id));
      shown += vis.length;
      const collapsed = S.collapsedTargets.has(t.name);
      const state = !vis.length ? 'off' : vis.length === runs.length ? 'on' : 'mixed';
      const head = el('div', { class: 'ghead' }, [
        el('button', { class: 'caret iconbtn', text: collapsed ? '▸' : '▾', title: collapsed ? 'Expand' : 'Collapse',
          onclick: () => { collapsed ? S.collapsedTargets.delete(t.name) : S.collapsedTargets.add(t.name); save(); renderSide(); } }),
        el('span', { class: 'cbwrap', title: state === 'on' ? 'Deselect every run of this target' : 'Select every run of this target',
          onclick: () => { runs.forEach((r) => (state === 'on' ? S.unchecked.add(r.id) : S.unchecked.delete(r.id))); save(); renderSide(); renderBoard(); } },
          [checkbox('#52514e', state)]),
        el('span', { class: 'gname ell', title: `${t.title} — ${t.description}`, text: t.title }),
        el('span', { class: 'gcount faint num', text: `${vis.length}/${t.runs.length}` }),
      ]);
      groupsBox.appendChild(head);
      if (collapsed) continue;
      const list = el('div', { class: 'glist' });
      for (const r of runs) {
        const g = TC.group(r.group);
        const on = !S.unchecked.has(r.id);
        const row = el('div', { class: 'runrow' + (S.pinned === r.id ? ' pinned' : '') + (on ? '' : ' unchecked') }, [
          el('span', { class: 'cbwrap', title: on ? 'Hide this run' : 'Show this run',
            onclick: (e) => { e.stopPropagation(); on ? S.unchecked.add(r.id) : S.unchecked.delete(r.id); save(); renderSide(); renderBoard(); } }, [checkbox(g.color, on ? 'on' : 'off')]),
          el('span', { class: 'rname ell', title: `${r.id} — ${r.title} · ${r.tags.ff_model} · ${r.date}`, text: r.short }),
          el('span', { class: 'rtags ell faint', title: `${r.tags.ff_model} · ${r.date} · ${r.kind}`, text: `${r.group === 'sim' ? 'sim' : r.group} · ${TC.shortDate(r.date)}` }),
          el('span', { class: 'rval num', title: `RMS error ${TC.jointLabel(S.joint)}`, text: TC.deg(TC.stat(r, S.joint, 'rmsErr')) }),
          el('a', { class: 'drill', href: TC.drillHref(r.target, r.short), title: 'Open this run in the run view', text: '↗', onclick: (e) => e.stopPropagation() }),
        ]);
        row.addEventListener('mouseenter', () => { S.hover = r.id; renderTarget(r.target); });
        row.addEventListener('mouseleave', () => { S.hover = null; renderTarget(r.target); });
        row.addEventListener('click', () => { S.pinned = S.pinned === r.id ? null : r.id; renderSide(); renderBoard(); });
        list.appendChild(row);
      }
      groupsBox.appendChild(list);
    }
    countEl.textContent = `${shown}/${TC.runs.length}`;
  }

  // ---------- toolbar + answer strip ----------
  const toolbar = el('div', { class: 'toolbar' });
  const answer = el('div', { class: 'answer' });
  const sectionsBox = el('div', { class: 'sections' });
  main.append(toolbar, answer, sectionsBox);

  function seg(options, value, onPick, title) {
    const s = el('div', { class: 'seg', title: title || '' });
    options.forEach(([v, label, tip]) => s.appendChild(el('button', { class: v === value ? 'on' : '', title: tip || '', text: label, 'data-v': String(v), onclick: () => onPick(v) })));
    return s;
  }
  function renderToolbar() {
    toolbar.innerHTML = '';
    toolbar.append(
      el('span', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Joint' }),
        seg(TC.joints.map((j, i) => [i, j]).concat([[TC.joints.length, 'all']]), S.joint, (v) => { S.joint = v; save(); renderSide(); renderAll(); })]),
      el('span', { class: 'ctl', id: 'enc-ctl' }, [el('span', { class: 'lab', text: 'Repeats' }),
        seg([['auto', 'Auto', 'Lines while a group has ≤ N runs, percentile fan above'], ['lines', 'Lines', 'One line per run'], ['bands', 'Bands', 'Median, IQR, p5–p95, min–max']], S.enc,
          (v) => { S.enc = v; save(); renderToolbar(); renderBoard(); })]),
    );
    const thr = el('input', { type: 'range', min: 1, max: 15, step: 1, value: S.threshold, disabled: S.enc !== 'auto' ? true : null });
    const thrOut = el('output', { text: String(S.threshold) });
    thr.addEventListener('input', () => { S.threshold = +thr.value; thrOut.textContent = thr.value; save(); renderBoard(); });
    toolbar.appendChild(el('span', { class: 'ctl' + (S.enc !== 'auto' ? ' dim' : ''), title: 'Auto draws lines while a group has at most N runs' }, [el('span', { class: 'lab', text: 'Lines up to N' }), thr, thrOut]));
    const sm = el('input', { type: 'range', min: 0, max: 0.95, step: 0.05, value: S.smooth });
    const smOut = el('output', { text: S.smooth.toFixed(2) });
    sm.addEventListener('input', () => { S.smooth = +sm.value; smOut.textContent = S.smooth.toFixed(2); save(); renderBoard(); });
    toolbar.appendChild(el('span', { class: 'ctl', title: "TensorBoard's debiased exponential moving average, applied per run before the fan is taken" }, [el('span', { class: 'lab', text: 'Smoothing' }), sm, smOut]));
    toolbar.appendChild(el('span', { class: 'spacer' }));
    toolbar.appendChild(el('span', { class: 'faint hint', text: 'drag a chart to zoom · double-click resets · click a line or band to open it' }));
  }

  function renderAnswer() {
    answer.innerHTML = '';
    for (const t of TC.targets) {
      const v = TC.verdict(t, S.joint, visible);
      const cell = el('div', { class: 'acell' });
      cell.appendChild(el('div', { class: 'atitle ell', title: t.title + ' — ' + t.description, text: t.title }));
      if (v.hasBoth) {
        const g = TC.group(v.winner);
        cell.appendChild(el('div', { class: 'aline' }, [
          el('span', { class: 'sw', style: { background: g.color } }), el('b', { text: g.label }),
          el('span', { class: 'num', html: ` <b>${TC.signedPct(v.winner === 'v2' ? v.delta : -v.delta / (1 + v.delta))}</b> RMS error` }),
          el('span', { class: 'faint num', text: ` ${TC.deg(v.medA)} → ${TC.deg(v.medB)}` }),
        ]));
        cell.appendChild(el('div', { class: 'asub num' }, [
          el('span', { html: `FB share <b>${TC.pct(v.fbA)} → ${TC.pct(v.fbB)}</b>` }),
          el('span', { class: 'conf ' + v.conf, title: `Confidence ${v.conf}: ${TC.confText(v)} — the share of (v1, v2) run pairs in which the winner had the lower RMS error (probability of superiority)`,
            text: `${v.conf} · ${Math.round(v.winner === 'v2' ? v.wins : v.pairs - v.wins)}/${v.pairs} pairs` }),
        ]));
        cell.addEventListener('click', () => TC.drill(t.name, 'group/' + v.winner));
        cell.title = 'Open the winning group in the run view';
      } else {
        const only = v.a.length ? 'v1' : 'v2';
        const runs = only === 'v1' ? v.a : v.b;
        cell.appendChild(el('div', { class: 'aline' }, [el('span', { class: 'sw', style: { background: TC.group(only).color } }), el('b', { text: TC.group(only).label + ' only' }),
          el('span', { class: 'faint num', text: ` · ${runs.length} runs · median ${TC.deg(only === 'v1' ? v.medA : v.medB)}` })]));
        cell.appendChild(el('div', { class: 'asub num' }, [el('span', { html: `FB share <b>${TC.pct(only === 'v1' ? v.fbA : v.fbB)}</b>` }), el('span', { class: 'conf none', text: 'no ff v2 runs — nothing to compare' })]));
      }
      const sat = t.runs.filter(visible).filter((r) => r.kind === 'real' && TC.stat(r, S.joint, 'satFrac') > 0.01);
      if (sat.length) cell.appendChild(el('span', { class: 'flag-warn sat', title: 'Runs whose commanded torque sits at the drive limit for more than 1 % of samples', text: `${sat.length} runs saturate` }));
      answer.appendChild(cell);
    }
  }

  // ---------- charts ----------
  const charts = {}; // key `${section}:${target}` → { u, host, readout }
  function layersFor(t, key) {
    const layers = [];
    for (const g of TC.GROUPS) {
      const runs = t.runs.filter((r) => r.group === g.key && visible(r));
      if (!runs.length) continue;
      const mode = g.key === 'sim' ? 'lines' : TC.encodingFor(runs.length, S.enc, S.threshold);
      layers.push({ key: g.key, color: g.color, label: g.short, mode, dash: g.key === 'sim',
                    runs: runs.map((r) => ({ run: r, y: TC.smooth(TC.series(r, key, S.joint), S.smooth) })) });
    }
    return layers;
  }
  function renderChart(sec, t) {
    const id = sec.key + ':' + t.name;
    const c = charts[id];
    if (!c) return;
    TC.destroyChart(c.u);
    const layers = layersFor(t, sec.key);
    c.legend.innerHTML = '';
    for (const L of layers) c.legend.appendChild(el('span', { class: 'lg', title: `${TC.group(L.key).label}: ${L.runs.length} run(s) drawn as ${L.mode === 'bands' ? 'median + IQR + p5–p95 + min–max' : 'one line per run'}` },
      [el('span', { class: 'sw', style: { background: L.color } }), `${L.label} `, el('span', { class: 'faint', text: `n=${L.runs.length} · ${L.mode === 'bands' ? 'fan' : 'lines'}` })]));
    const overlay = [];
    for (const id2 of [S.pinned, S.hover]) {
      const r = id2 && TC.run(id2);
      if (r && r.target === t.name && visible(r) && !overlay.some((o) => o.run === r)) overlay.push({ run: r, y: TC.smooth(TC.series(r, sec.key, S.joint), S.smooth), color: '#22211f' });
    }
    c.u = TC.fanChart(c.host, { x: t.t, layers, overlay, height: 158, yFmt: sec.fmt, yUnit: sec.unit, readout: c.readout, zeroLine: sec.zero, yRange: sec.range,
      onPick: (hit) => (hit.run ? TC.drill(t.name, hit.run.short) : TC.drill(t.name, 'group/' + hit.layer.key)) });
  }
  function renderTarget(name) { for (const sec of SECTIONS) if (!S.collapsedSections.has(sec.key)) renderChart(sec, TC.target(name)); }
  function renderBoard() {
    renderAnswer();
    sectionsBox.innerHTML = '';
    for (const k of Object.keys(charts)) { TC.destroyChart(charts[k].u); delete charts[k]; }
    for (const sec of SECTIONS) {
      const collapsed = S.collapsedSections.has(sec.key);
      const box = el('section', { class: 'tb-section' + (collapsed ? ' collapsed' : ''), 'data-section': sec.key });
      box.appendChild(el('div', { class: 'tb-shead', onclick: () => { collapsed ? S.collapsedSections.delete(sec.key) : S.collapsedSections.add(sec.key); save(); renderBoard(); } }, [
        el('span', { class: 'caret', text: collapsed ? '▸' : '▾' }), el('span', { class: 'tb-stitle', text: sec.title }), el('span', { class: 'faint', text: ' ' + sec.sub }),
        el('span', { class: 'faint tb-scount', text: `${TC.targets.length} charts · ${TC.jointLabel(S.joint)}` })]));
      if (!collapsed) {
        const grid = el('div', { class: 'tb-grid' });
        for (const t of TC.targets) {
          const host = el('div', { class: 'plot' });
          const readout = el('div', { class: 'plot-readout', html: '&nbsp;' });
          const legend = el('div', { class: 'card-legend' });
          const card = el('div', { class: 'tb-card' }, [
            el('div', { class: 'tb-ctitle' }, [el('span', { class: 'ell', title: `${sec.key}/${t.name}/${TC.jointLabel(S.joint)} — ${t.title}`, text: `${t.name} · ${TC.jointLabel(S.joint)}` }),
              el('a', { class: 'drill', href: TC.drillHref(t.name, 'all'), title: 'Open this target in the run view', text: 'run view ↗' })]),
            legend, host, readout]);
          grid.appendChild(card);
          charts[sec.key + ':' + t.name] = { host, readout, legend };
        }
        box.appendChild(grid);
      }
      sectionsBox.appendChild(box);
    }
    requestAnimationFrame(() => { for (const sec of SECTIONS) if (!S.collapsedSections.has(sec.key)) for (const t of TC.targets) renderChart(sec, t); });
  }
  function renderAll() { renderToolbar(); renderBoard(); }
  window.addEventListener('tcs:layout', () => { /* charts follow their containers via ResizeObserver */ });
  renderSide();
  renderAll();
  window.TCS_V1 = { S, renderSide, renderAll, renderBoard };
})();
