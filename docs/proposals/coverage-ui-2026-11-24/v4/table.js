/* table.js — V4 "Tidy": the Trajectories table, hand-built in data-ui's table language.
 *
 * Zach, Nov 23: "I should also be able to like filter etc this table, and possibly like create saved views … it should
 * be one of our like generic tables from data-ui" — his reference is robotparts' Datasheet table: view tabs across the
 * top ("Datasheet · Datasheet only · Measured vs datasheet · Sources · +"), search + settings icons at the right, groups
 * that fold, "38 of 38 rows · 7 groups · Unfold all · Fold all". V4 keeps the coverage page hand-rolled, so this is that
 * look built here (no data-ui import), on the round's data/trajectories.js rows.
 *
 * A view = { q, facets: {key: [values]}, ranges: {column: text}, group, sort: {key, desc} | null, signal, hidden }.
 * Built-in views can't be deleted; "+ Save view" stores the current one (localStorage, behind the page's try/catch).
 * Every number is a field of data/trajectories.js (analyze's numbers + extract.py's tool numbers); the table only
 * filters, sorts, groups and sums a column (group rows), never recomputes coverage.
 */
(function (global) {
  'use strict';

  const SEARCH_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
  const SLIDERS_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>';

  function build(fig, api) {
    const { el, pct, count, duration, minibar, payload } = api;
    const rows = api.trajectories.map((row, index) => Object.assign({ _i: index }, row));
    const byName = new Map(payload.trajectories.map((row, index) => [row.name, index]));
    const groupKey = payload.source.group_by || null;
    const tagKeys = [];
    for (const row of rows) for (const key of Object.keys(row.tags || {})) if (!tagKeys.includes(key)) tagKeys.push(key);
    const facetKeys = [groupKey, 'kind'].filter((key, k, all) => key && tagKeys.includes(key) && all.indexOf(key) === k);
    const jointNames = api.joints().map((joint) => joint.name);
    const SIGNAL_WORD = { q: 'position', qd: 'speed', qdd: 'acceleration' };
    const maxNew = Math.max(1, ...rows.map((row) => row.new_cells || 0));
    const maxOnly = Math.max(1, ...rows.map((row) => row.only_it_q_qd_cells || 0));

    // ── columns ────────────────────────────────────────────────────────────────────────────────────────────────
    const tagValue = (row, key) => ((row.tags || {})[key] === undefined ? '' : String(row.tags[key]));
    const fixed2 = (v) => (Number.isFinite(v) ? v.toFixed(2) : '—');
    const columns = [
      { id: 'idx', label: '#', type: 'num', left: true, fixed: true, get: (row) => row._i + 1, cell: (row) => el('td', { class: 'left muted', text: String(row._i + 1) }) },
      { id: 'name', label: 'Trajectory', type: 'text', left: true, fixed: true, get: (row) => row.name,
        cell: (row) => el('td', { class: 'left v4-namecell' }, [row.name, groupKey ? splitChip(tagValue(row, groupKey)) : null]) },
      ...tagKeys.filter((key) => key !== groupKey).map((key) => ({
        id: 'tag:' + key, label: key, sub: 'tag', type: 'text', left: true, get: (row) => tagValue(row, key),
        hidden: key === 'rung' || key === 'tags', cell: (row) => el('td', { class: 'left', text: tagValue(row, key) }),
      })),
      { id: 'duration', label: 'Duration', sub: 's', type: 'num', get: (row) => row.duration_s, cell: (row) => el('td', { text: duration(row.duration_s) }) },
      { id: 'samples', label: 'Samples', type: 'num', get: (row) => row.samples, cell: (row) => el('td', { text: count(row.samples) }) },
      ...jointNames.map((name) => ({
        id: 'span:' + name, label: name, joint: true, type: 'num', unit: '%',
        get: (row, view) => { const v = ((row.span_pct || {})[name] || {})[view.signal]; return v === null || v === undefined ? null : v; },
        cell: (row, view) => {
          const v = ((row.span_pct || {})[name] || {})[view.signal];
          if (v === null || v === undefined) return el('td', { class: 'muted', text: '—' });
          return el('td', null, el('span', { class: 'cov-cell' }, [pct(v), minibar(v)]));
        },
      })),
      { id: 'new', label: 'New cells', sub: 'first to visit', type: 'num', get: (row) => row.new_cells,
        cell: (row) => el('td', null, el('span', { class: 'cov-cell' }, [count(row.new_cells), minibar((100 * (row.new_cells || 0)) / maxNew)])) },
      { id: 'only', label: 'Only it', sub: 'cells no other visits', type: 'num', get: (row) => row.only_it_q_qd_cells,
        cell: (row) => el('td', null, el('span', { class: 'cov-cell' }, [count(row.only_it_q_qd_cells), minibar((100 * (row.only_it_q_qd_cells || 0)) / maxOnly)])) },
      { id: 'path', label: 'Tool path', sub: 'm', type: 'num', get: (row) => row.tool_path_m, cell: (row) => el('td', { text: fixed2(row.tool_path_m) }) },
      { id: 'speed', label: 'Tool speed', sub: 'max, m/s', type: 'num', hidden: true, get: (row) => row.tool_speed_max_m_s, cell: (row) => el('td', { text: fixed2(row.tool_speed_max_m_s) }) },
      { id: 'zmin', label: 'Tool z', sub: 'lowest, mm', type: 'num', hidden: true, get: (row) => row.tool_z_min_m * 1000, cell: (row) => el('td', { text: api.minus(String(Math.round(row.tool_z_min_m * 1000))) }) },
      { id: 'tilt', label: 'Tool tilt', sub: 'max, °', type: 'num', hidden: true, get: (row) => row.tool_tilt_max_deg, cell: (row) => el('td', { text: Math.round(row.tool_tilt_max_deg) + '°' }) },
    ];
    const columnById = new Map(columns.map((column) => [column.id, column]));
    const defaultHidden = columns.filter((column) => column.hidden).map((column) => column.id);

    // ── views ──────────────────────────────────────────────────────────────────────────────────────────────────
    function blank(extra) {
      return Object.assign({ q: '', facets: {}, ranges: {}, group: groupKey || 'none', sort: null, signal: 'q', hidden: defaultHidden.slice() }, extra || {});
    }
    const PRESETS = [
      { id: 'all', name: groupKey ? `All · by ${groupKey}` : 'All trajectories', builtin: true, state: blank() },
      groupKey && facetValues(groupKey).includes('holdout')
        ? { id: 'holdout', name: 'Holdout only', builtin: true, state: blank({ facets: { [groupKey]: ['holdout'] }, group: 'kind' }) } : null,
      tagKeys.includes('kind') ? { id: 'kind', name: 'By kind', builtin: true, state: blank({ group: 'kind' }) } : null,
      { id: 'adds', name: 'Adds the most', builtin: true, state: blank({ group: 'none', sort: { key: 'only', desc: true } }) },
    ].filter(Boolean);
    let userViews = (api.load('v4.views', []) || []).filter((view) => view && view.id && view.state);
    const allViews = () => PRESETS.concat(userViews);
    let activeId = api.load('v4.view', 'all');
    if (!allViews().some((view) => view.id === activeId)) activeId = 'all';
    let view = clone(allViews().find((item) => item.id === activeId).state);
    const folded = new Set();
    let showRanges = Object.values(view.ranges || {}).some(Boolean);

    function clone(value) { return JSON.parse(JSON.stringify(value)); }
    function normal(state) { return JSON.stringify(Object.assign(blank(), state)); }
    function modified() { const saved = allViews().find((item) => item.id === activeId); return !saved || normal(saved.state) !== normal(view); }
    function persist() { api.save('v4.views', userViews); api.save('v4.view', activeId); }

    function facetValues(key) {
      const values = [];
      for (const row of api.trajectories) { const v = tagValue(row, key); if (v !== '' && !values.includes(v)) values.push(v); }
      if (key === groupKey) {
        const order = api.groupNames();
        values.sort((a, b) => (order.indexOf(a) - order.indexOf(b)) || a.localeCompare(b));
      } else values.sort((a, b) => a.localeCompare(b));
      return values;
    }

    // ── the split chip and its legend (G3: every colour beside a trajectory is named) ─────────────────────────
    function splitChip(value) {
      if (!value) return null;
      const colour = api.groupColour(value);
      return el('span', { class: 'v4-split', 'data-split': value, style: `--c:${colour}`, title: `${groupKey} = ${value}` }, [el('i'), value]);
    }

    // ── filtering, sorting, grouping ───────────────────────────────────────────────────────────────────────────
    function parseRange(text) {
      const t = String(text || '').trim().replace(/\s+/g, '').replace(/[−–—]/g, '-').replace(/(%|°|s|m|mm|m\/s)$/i, '');
      if (!t) return null;
      const n = '(-?\\d*\\.?\\d+)';
      let m = new RegExp(`^(>=|≥|>|<=|≤|<|=)${n}$`).exec(t);
      if (m) {
        const v = Number(m[2]);
        if (m[1] === '>') return (x) => x > v;
        if (m[1] === '>=' || m[1] === '≥') return (x) => x >= v;
        if (m[1] === '<') return (x) => x < v;
        if (m[1] === '<=' || m[1] === '≤') return (x) => x <= v;
        return (x) => x === v;
      }
      m = new RegExp(`^${n}(?:\\.\\.|-|to)${n}$`).exec(t);
      if (m) { const lo = Math.min(Number(m[1]), Number(m[2])); const hi = Math.max(Number(m[1]), Number(m[2])); return (x) => x >= lo && x <= hi; }
      m = new RegExp(`^${n}$`).exec(t);
      if (m) { const v = Number(m[1]); return (x) => x >= v; }
      return 'bad';
    }

    function passes(row, skipFacet) {
      const q = view.q.trim().toLowerCase();
      if (q) {
        const hay = [row.name, ...Object.values(row.tags || {}).map(String)].join(' ').toLowerCase();
        if (!q.split(/\s+/).every((token) => hay.includes(token))) return false;
      }
      for (const [key, values] of Object.entries(view.facets || {})) {
        if (key === skipFacet || !values || !values.length) continue;
        if (!values.includes(tagValue(row, key))) return false;
      }
      for (const [id, text] of Object.entries(view.ranges || {})) {
        const test = parseRange(text);
        const column = columnById.get(id);
        if (!test || test === 'bad' || !column) continue;
        const value = column.get(row, view);
        if (value === null || value === undefined || !test(value)) return false;
      }
      return true;
    }

    function ordered(list) {
      const out = list.slice();
      const sort = view.sort;
      if (!sort || !columnById.has(sort.key)) return out.sort((a, b) => a._i - b._i);
      const column = columnById.get(sort.key);
      out.sort((a, b) => {
        const va = column.get(a, view);
        const vb = column.get(b, view);
        let c;
        if (column.type === 'text') c = String(va).localeCompare(String(vb), undefined, { numeric: true });
        else c = (va === null ? -Infinity : va) - (vb === null ? -Infinity : vb);
        return (sort.desc ? -c : c) || a._i - b._i;
      });
      return out;
    }

    function grouped(list) {
      if (!view.group || view.group === 'none') return [{ key: null, rows: list }];
      const order = facetValues(view.group);
      const groups = new Map(order.map((value) => [value, []]));
      for (const row of list) { const v = tagValue(row, view.group); if (!groups.has(v)) groups.set(v, []); groups.get(v).push(row); }
      return [...groups].filter(([, items]) => items.length).map(([key, items]) => ({ key, rows: items }));
    }

    // ── DOM ────────────────────────────────────────────────────────────────────────────────────────────────────
    const root = el('div', { class: 'v4-table', 'data-v4-table': '' });
    const viewTabs = el('div', { class: 'v4-viewtabs', role: 'tablist', 'aria-label': 'Saved views' });
    const search = el('input', { type: 'search', placeholder: 'Search name, split, kind…', 'data-v4-filter': '', 'aria-label': 'Filter the trajectories' });
    const searchBox = el('label', { class: 'v4-search', title: 'Filter: every word must match the name or a tag' }, [search]);
    searchBox.insertAdjacentHTML('afterbegin', SEARCH_SVG);
    const columnsButton = el('button', { type: 'button', class: 'v4-icon', 'data-v4-columns': '', title: 'Columns: show or hide', 'aria-expanded': 'false' });
    columnsButton.insertAdjacentHTML('afterbegin', SLIDERS_SVG);
    const columnsPanel = el('div', { class: 'v4-columns-panel', hidden: true, 'data-v4-columns-panel': '' });
    const viewBar = el('div', { class: 'v4-viewbar' }, [viewTabs, el('div', { class: 'v4-viewbar-right' }, [searchBox, columnsButton, columnsPanel])]);
    const toolbar = el('div', { class: 'v4-toolbar' });
    const facetBar = el('div', { class: 'v4-facetbar' });
    const status = el('div', { class: 'v4-status' });
    const table = el('table', { class: 'cov-table v4-grid' });
    const wrap = el('div', { class: 'v4-tablewrap' }, table);
    root.append(viewBar, toolbar, facetBar, status, wrap);
    fig.body.append(root);
    let visibleNames = [];

    columnsButton.addEventListener('click', () => {
      columnsPanel.hidden = !columnsPanel.hidden;
      columnsButton.setAttribute('aria-expanded', String(!columnsPanel.hidden));
      paintColumnsPanel();
    });
    document.addEventListener('pointerdown', (event) => {
      if (columnsPanel.hidden || columnsPanel.contains(event.target) || columnsButton.contains(event.target)) return;
      columnsPanel.hidden = true;
      columnsButton.setAttribute('aria-expanded', 'false');
    });
    search.addEventListener('input', () => { view.q = search.value; render(); });

    function setView(id) {
      activeId = id;
      view = clone(allViews().find((item) => item.id === id).state);
      showRanges = Object.values(view.ranges || {}).some(Boolean);
      folded.clear();
      persist();
      render();
    }

    function autoName() {
      const parts = [];
      if (view.q.trim()) parts.push(`“${view.q.trim()}”`);
      for (const [, values] of Object.entries(view.facets || {})) if (values && values.length) parts.push(values.join(' + '));
      const ranges = Object.entries(view.ranges || {}).filter(([, text]) => text && parseRange(text) !== 'bad');
      for (const [id, text] of ranges) parts.push(`${columnById.get(id).label} ${text}`);
      if (view.group !== (groupKey || 'none')) parts.push(view.group === 'none' ? 'ungrouped' : `by ${view.group}`);
      if (view.sort) parts.push(`${columnById.get(view.sort.key).label} ${view.sort.desc ? '↓' : '↑'}`);
      if (view.signal !== 'q') parts.push(`${SIGNAL_WORD[view.signal]} span`);
      const name = parts.join(' · ') || 'My view';
      let unique = name;
      for (let k = 2; allViews().some((item) => item.name === unique); k++) unique = `${name} (${k})`;
      return unique;
    }

    function saveView() {
      const id = 'u' + Date.now().toString(36);
      userViews.push({ id, name: autoName(), state: clone(view) });
      activeId = id;
      persist();
      render();
    }

    function renameView(item, tab) {
      const input = el('input', { class: 'v4-rename', value: item.name, 'aria-label': 'View name' });
      tab.replaceWith(input);
      input.focus();
      input.select();
      const done = (keep) => {
        if (keep && input.value.trim()) { item.name = input.value.trim(); persist(); }
        render();
      };
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') done(true); if (event.key === 'Escape') { event.stopPropagation(); done(false); } });
      input.addEventListener('blur', () => done(true));
    }

    function paintViewTabs() {
      viewTabs.replaceChildren();
      const dirty = modified();
      for (const item of allViews()) {
        const on = item.id === activeId;
        const tab = el('button', {
          type: 'button', role: 'tab', class: 'v4-viewtab' + (on && dirty ? ' dirty' : ''), 'data-view': item.id, 'aria-selected': String(on),
          title: item.builtin ? 'a built-in view' : 'your saved view · double-click to rename',
          onclick: () => setView(item.id),
        }, [el('span', { class: 'v4-viewname', text: item.name })]);
        if (!item.builtin) tab.title = `${item.name} · your saved view · double-click to rename`;
        if (on && dirty) tab.append(el('i', { class: 'v4-dot', title: 'changed since this view was saved: "+ Save view" keeps it as a new view' }));
        if (!item.builtin) {
          tab.addEventListener('dblclick', () => renameView(item, tab));
          tab.append(el('span', { class: 'v4-viewx', title: 'Delete this view', text: '×', onclick: (event) => {
            event.stopPropagation();
            userViews = userViews.filter((other) => other.id !== item.id);
            if (activeId === item.id) { activeId = 'all'; view = clone(PRESETS[0].state); }
            persist();
            render();
          } }));
        }
        viewTabs.append(tab);
      }
      viewTabs.append(el('button', { type: 'button', class: 'v4-viewtab-add', 'data-v4-save-view': '', title: 'Save the current search, filters, grouping, sort and columns as a new view', text: '+ Save view', onclick: saveView }));
    }

    function seg(label, options, value, onChange, attrs) {
      const box = el('div', { class: 'cov-seg', role: 'group', 'aria-label': label });
      for (const [optionValue, optionLabel] of options) {
        box.append(el('button', { type: 'button', 'data-value': optionValue, 'aria-pressed': String(optionValue === value), text: optionLabel, onclick: () => onChange(optionValue) }));
      }
      return el('span', Object.assign({ class: 'v4-tool' }, attrs || {}), [el('span', { class: 'cov-seg-label', text: label }), box]);
    }

    function paintToolbar() {
      const groupOptions = [...(groupKey ? [[groupKey, groupKey]] : []), ...(tagKeys.includes('kind') && groupKey !== 'kind' ? [['kind', 'kind']] : []), ['none', 'none']];
      const sortLabel = view.sort ? `${columnById.get(view.sort.key).label} ${view.sort.desc ? '↓' : '↑'}` : 'dataset order';
      const activeRanges = Object.values(view.ranges || {}).filter((text) => text && String(text).trim()).length;
      toolbar.replaceChildren(
        seg('Group', groupOptions, view.group, (value) => { view.group = value; folded.clear(); render(); }, { 'data-v4-group': '' }),
        el('span', { class: 'v4-tool v4-sort' }, [el('span', { class: 'cov-seg-label', text: 'Sort' }), el('span', { class: 'v4-sortval', text: sortLabel }),
          view.sort ? el('button', { type: 'button', class: 'v4-x small', title: 'Back to the dataset order', text: '×', onclick: () => { view.sort = null; render(); } }) : null]),
        seg('Span of', [['q', 'position'], ['qd', 'speed'], ['qdd', 'acceleration']], view.signal, (value) => { view.signal = value; render(); }, { 'data-v4-signal': '' }),
        el('button', { type: 'button', class: 'v4-toggle', 'aria-pressed': String(showRanges), 'data-v4-ranges': '',
          title: 'A range box under each number column: 2..4, >30, <=1.5', onclick: () => { showRanges = !showRanges; render(); } },
        [`Ranges${activeRanges ? ' · ' + activeRanges : ''}`]),
      );
    }

    function paintFacets() {
      facetBar.replaceChildren();
      for (const key of facetKeys) {
        const chosen = (view.facets || {})[key] || [];
        const box = el('span', { class: 'v4-facet', 'data-v4-facet': key }, [el('span', { class: 'cov-seg-label', text: key })]);
        for (const value of facetValues(key)) {
          const n = api.trajectories.filter((row, index) => tagValue(row, key) === value && passes(rows[index], key)).length;
          const on = chosen.includes(value);
          const chip = el('button', { type: 'button', class: 'v4-fchip' + (on ? ' on' : '') + (n ? '' : ' none'), 'aria-pressed': String(on), 'data-value': value,
            title: on ? 'click to drop this filter' : `show only ${key} = ${value}`,
            onclick: () => {
              const next = on ? chosen.filter((item) => item !== value) : chosen.concat(value);
              view.facets = Object.assign({}, view.facets, { [key]: next });
              render();
            } }, [key === groupKey ? el('i', { class: 'v4-fdot', style: `background:${api.groupColour(value)}` }) : null, value, el('span', { class: 'n', text: String(n) })]);
          box.append(chip);
        }
        facetBar.append(box);
      }
      const anything = view.q.trim() || Object.values(view.facets || {}).some((values) => values && values.length) || Object.values(view.ranges || {}).some((text) => text && String(text).trim());
      if (anything) facetBar.append(el('button', { type: 'button', class: 'v4-link', text: 'Clear filters', onclick: () => { view.q = ''; view.facets = {}; view.ranges = {}; render(); } }));
    }

    function paintColumnsPanel() {
      columnsPanel.replaceChildren(el('div', { class: 'v4-panel-title', text: 'Columns' }));
      for (const column of columns) {
        if (column.fixed) continue;
        const box = el('input', { type: 'checkbox' });
        box.checked = !view.hidden.includes(column.id);
        box.addEventListener('change', () => {
          view.hidden = box.checked ? view.hidden.filter((id) => id !== column.id) : view.hidden.concat(column.id);
          render();
          paintColumnsPanel();
        });
        columnsPanel.append(el('label', { class: 'v4-check' }, [box, column.label + (column.sub ? ` (${column.sub})` : column.joint ? ` (${view.signal} span)` : '')]));
      }
    }

    function headerLabel(column) {
      if (column.joint) {
        // WHY <wbr> after each underscore: the joint names stay whole (truthful), but may break onto two lines
        const label = el('span', { class: 'v4-jointlabel' });
        column.label.split('_').forEach((part, k, parts) => { label.append(part + (k < parts.length - 1 ? '_' : '')); if (k < parts.length - 1) label.append(el('wbr')); });
        return [label, el('span', { class: 'sub', text: `${view.signal} span` })];
      }
      return [column.label, column.sub ? el('span', { class: 'sub', text: column.sub }) : null];
    }

    function paintTable(groups, shown) {
      const visible = columns.filter((column) => column.fixed || !view.hidden.includes(column.id));
      const headRow = el('tr', null, visible.map((column) => {
        const on = view.sort && view.sort.key === column.id;
        const th = el('th', { class: 'sortable' + (column.left ? ' left' : '') + (on ? ' sorted' : ''), 'data-col': column.id, title: 'sort by this column',
          'aria-sort': on ? (view.sort.desc ? 'descending' : 'ascending') : 'none',
          onclick: () => {
            if (on) view.sort = { key: column.id, desc: !view.sort.desc };
            else view.sort = { key: column.id, desc: column.type === 'num' && column.id !== 'idx' };
            render();
          } }, headerLabel(column));
        if (on) th.append(el('span', { class: 'v4-arrow', text: view.sort.desc ? ' ↓' : ' ↑' }));
        return th;
      }));
      const thead = el('thead', null, headRow);
      if (showRanges) {
        thead.append(el('tr', { class: 'v4-rangerow' }, visible.map((column) => {
          if (column.type !== 'num' || column.id === 'idx') return el('th', { class: column.left ? 'left' : '' });
          const text = (view.ranges || {})[column.id] || '';
          const input = el('input', { type: 'text', value: text, 'data-range': column.id, placeholder: column.unit === '%' ? 'e.g. >20' : 'e.g. 2..4',
            'aria-label': `Range for ${column.label}`, class: parseRange(text) === 'bad' ? 'bad' : '' });
          input.addEventListener('change', () => { view.ranges = Object.assign({}, view.ranges, { [column.id]: input.value }); render(); });
          input.addEventListener('keydown', (event) => { if (event.key === 'Enter') input.blur(); });
          return el('th', null, input);
        })));
      }
      const tbody = el('tbody');
      for (const group of groups) {
        if (group.key !== null) {
          const isFolded = folded.has(group.key);
          const chip = view.group === groupKey ? splitChip(group.key) : el('b', { text: group.key });
          tbody.append(el('tr', { class: 'v4-grouprow' + (isFolded ? ' folded' : ''), 'data-group': group.key,
            onclick: () => { if (folded.has(group.key)) folded.delete(group.key); else folded.add(group.key); render(); } },
          el('td', { class: 'left', colspan: String(visible.length) }, [
            el('span', { class: 'v4-caret', text: isFolded ? '▸' : '▾' }), chip, el('span', { class: 'v4-gcount', text: String(group.rows.length) }),
          ])));
          if (isFolded) continue;
        }
        for (const row of group.rows) {
          const index = byName.get(row.name);
          const tr = el('tr', { 'data-row': '', 'data-name': row.name, class: index === api.state.highlight ? 'selected' : null,
            title: 'open this trajectory' }, visible.map((column) => column.cell(row, view)));
          tr.addEventListener('click', () => openRow(row.name));
          tbody.append(tr);
        }
      }
      if (!shown) tbody.append(el('tr', null, el('td', { class: 'left muted v4-empty', colspan: String(visible.length), text: 'No trajectory matches. Clear filters to see them all.' })));
      table.replaceChildren(thead, tbody);
    }

    function openRow(name) {
      const index = byName.get(name);
      if (index !== undefined && api.state.highlight !== index) api.setHighlight(index);
      if (global.V4Drawer) global.V4Drawer.open(name, visibleNames.slice());
    }

    function paintStatus(groups, shown) {
      const n = groups.filter((group) => group.key !== null).length;
      const legend = groupKey ? el('span', { class: 'v4-legend', 'data-v4-split-legend': '' }, [
        el('span', { class: 'cov-seg-label', text: groupKey }),
        ...api.groupNames().map((name) => splitChip(name)),
        el('span', { class: 'v4-legend-note', text: `the chip beside a name is its ${groupKey}; the same colours draw the ${groupKey} lines in One joint's paths and the stacked Limits bars` }),
      ]) : null;
      status.replaceChildren(
        el('span', { class: 'v4-count' }, [`${count(shown)} of ${count(rows.length)} rows`, n ? ` · ${n} group${n === 1 ? '' : 's'} · ` : '',
          n ? el('button', { type: 'button', class: 'v4-link', text: 'Unfold all', onclick: () => { folded.clear(); render(); } }) : null,
          n ? el('button', { type: 'button', class: 'v4-link', text: 'Fold all', onclick: () => { for (const group of groups) if (group.key !== null) folded.add(group.key); render(); } }) : null]),
        legend,
      );
    }

    function render() {
      if (search.value !== view.q) search.value = view.q;
      const kept = rows.filter((row) => passes(row));
      const sorted = ordered(kept);
      const groups = grouped(sorted);
      visibleNames = groups.filter((group) => !folded.has(group.key)).flatMap((group) => group.rows.map((row) => row.name));
      paintViewTabs();
      paintToolbar();
      paintFacets();
      paintStatus(groups, kept.length);
      paintTable(groups, kept.length);
      api.setLegend(fig, [
        { kind: 'fill', colour: '#7f9cc0', label: `span bar = share of the joint's ${SIGNAL_WORD[view.signal]} range this trajectory alone covers (p0.1–p99.9), 0 – 100 %` },
        { kind: 'text', label: 'new cells = position × speed cells (all joints) it was first to visit, in the dataset\'s order; only it = cells no other trajectory visits; bars relative to the most' },
        { kind: 'text', label: 'outlined row = the open (highlighted) trajectory; it is drawn black in One joint\'s paths and the 3-D views' },
      ]);
      if (global.V4Drawer) global.V4Drawer.setOrder(visibleNames.slice());
    }

    api.onHighlight((index) => {
      for (const tr of table.querySelectorAll('tr[data-row]')) tr.classList.toggle('selected', byName.get(tr.dataset.name) === index);
    });
    render();
  }

  global.V4Table = { build };
})(typeof window !== 'undefined' ? window : globalThis);
