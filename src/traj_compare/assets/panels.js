/* Panels at the playhead (traj_compare.panels, 2026-11-27): what a run view shows besides curves.
 *
 *   - the step band `[data-tc-step-band]` above the stage and the tabs: one row per StepTrack, one block per StepSpan on
 *     the run's clock, a line at the playhead, and under it each track's current block written out whole (a block is
 *     rarely wide enough for its text). Click a block: go to its start. Press and drag on the rows: scrub.
 *   - a PlayheadTable tab `[data-tc-playhead-table]`: one table read at the playhead (a constant, the newest sample at
 *     or before it, or the value in force since its last change).
 *   - a TimeTable tab `[data-tc-time-table]`: time-stamped rows; the newest at or before the playhead is marked (per
 *     level), later rows are dim, a click goes to the row's time; deeper levels fold; kinds have filter chips.
 *
 * WHY here and not in a page of its own (Zach, 2026-11-27, the JointCommandSequence viewer: "grow it out of Trajectory
 * Comparison ... reduce as much code duplication as possible"): the 3D, the plots, the tabs and the time lane are
 * plots.js's; this file adds only what a recorded procedure has on top, and everything it draws follows the page's one
 * transport (page.transport: eff() is the hovered time, else the committed one, else the end of the run).
 *
 * plots.js calls TrajComparePanels.band(page, root) from buildPage and TrajComparePanels.tab(page, record, host, panel)
 * the first time a panel tab opens. Text is the caller's, shown as given: a long cell wraps, it is never cut.
 */
var TrajComparePanels = (function () {
  'use strict';

  var KIND_COLOURS = 8;  // .tc-pn-k0 ... k7 (style.css), assigned to kinds in the order they first appear

  function el(tag, className, parent, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  function store(key, value) { try { localStorage.setItem('traj-compare:panel:' + key, JSON.stringify(value)); } catch (e) {} }
  function recall(key, fallback) {
    try {
      var raw = localStorage.getItem('traj-compare:panel:' + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) { return fallback; }
  }
  function now(page) { return page.transport ? page.transport.eff() : 0; }
  function goTo(page, time) {
    if (!page.transport) return;
    page.transport.pause();
    page.transport.setScrub(time);
  }
  // the index of the last entry of a sorted list whose time (read by ``at``) is <= ``time``; -1 before the first
  function lastAtOrBefore(list, time, at) {
    var lo = 0, hi = list.length - 1, hit = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (at(list[mid]) <= time + 1e-9) { hit = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    return hit;
  }
  function niceStep(span, px) {
    var raw = span / Math.max(1, px / 70);
    var power = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var mantissa = raw / power;
    return (mantissa <= 1 ? 1 : mantissa <= 2 ? 2 : mantissa <= 5 ? 5 : 10) * power;
  }
  function seconds(value) { return (Math.round(value * 1000) / 1000).toFixed(value % 1 === 0 ? 1 : value < 10 ? 2 : 1); }

  /* ---------------- the step band ---------------- */

  // ``given`` (a PanelTab's tracks) draws the band inside a tab; without it, the comparison's own tracks above the stage
  function band(page, root, given) {
    var tracks = given || (page.data.panels && page.data.panels.tracks) || [];
    if (!tracks.length || !page.transport) return null;
    var transport = page.transport;
    var t0 = transport.tMin, t1 = transport.tMax, length = Math.max(t1 - t0, 1e-9);
    var host = el('section', 'tc-pn-band' + (given ? ' in-tab' : ''), root);
    host.setAttribute('data-tc-step-band', '');
    host.setAttribute('aria-label', 'Steps over time');

    var kinds = [];
    tracks.forEach(function (track) {
      track.spans.forEach(function (span) { if (span.kind && kinds.indexOf(span.kind) === -1) kinds.push(span.kind); });
    });
    function kindClass(span) {
      return span.kind ? ' tc-pn-k' + (kinds.indexOf(span.kind) % KIND_COLOURS) : ' tc-pn-k0';
    }

    var rowsEl = el('div', 'tc-pn-rows', host);
    var records = tracks.map(function (track, index) {
      var row = el('div', 'tc-pn-row', rowsEl);
      row.setAttribute('data-tc-step-track', track.title);
      var name = el('div', 'tc-pn-name', row);
      el('span', 'tc-pn-name-title', name, track.title);
      if (track.words) el('span', 'tc-pn-name-words', name, track.words);
      var lane = el('div', 'tc-pn-lane' + (track.mono ? ' mono' : ''), row);
      var blocks = track.spans.map(function (span) {
        var instant = span.t1 - span.t0 <= 1e-9;
        var block = el('button', 'tc-pn-span' + kindClass(span) + (instant ? ' instant' : '') +
          (span.tone ? ' tone-' + span.tone : ''), lane, instant ? '' : span.label);
        block.type = 'button';
        block.setAttribute('data-tc-step', span.label);
        block.style.left = ((span.t0 - t0) / length * 100) + '%';
        if (!instant) block.style.width = ((span.t1 - span.t0) / length * 100) + '%';
        block.title = span.label + (span.detail ? '\n' + span.detail : '') + '\n' + seconds(span.t0) +
          (instant ? ' s' : ' – ' + seconds(span.t1) + ' s') + (span.kind ? ' · ' + span.kind : '');
        if (span.color) { block.style.background = span.color; block.style.borderColor = span.color; }
        block.addEventListener('click', function (event) { event.stopPropagation(); goTo(page, span.t0); });
        return block;
      });
      return { track: track, index: index, lane: lane, blocks: blocks, current: -2 };
    });

    // the ruler under the rows, on the rows' own x pixels
    var rulerRow = el('div', 'tc-pn-row tc-pn-ruler-row', rowsEl);
    el('div', 'tc-pn-name', rulerRow, 't [s]');
    var ruler = el('div', 'tc-pn-lane tc-pn-ruler', rulerRow);
    function paintRuler() {
      ruler.textContent = '';
      var width = ruler.clientWidth || 600;
      var step = niceStep(length, width);
      for (var tick = Math.ceil(t0 / step) * step; tick <= t1 + 1e-9; tick += step) {
        var mark = el('span', 'tc-pn-tick', ruler, (Math.round(tick * 1000) / 1000).toString());
        mark.style.left = ((tick - t0) / length * 100) + '%';
      }
    }
    var line = el('div', 'tc-pn-line', rowsEl);
    line.setAttribute('data-tc-step-line', '');
    var ghost = el('div', 'tc-pn-line ghost', rowsEl);

    // press and drag on the rows: scrub (a click on a block goes to its start instead)
    function timeAt(clientX) {
      var box = records[0].lane.getBoundingClientRect();
      return t0 + Math.min(1, Math.max(0, (clientX - box.left) / Math.max(box.width, 1))) * length;
    }
    rowsEl.addEventListener('pointerdown', function (event) {
      if (event.button !== 0 || (event.target.closest && event.target.closest('.tc-pn-span, .tc-pn-name'))) return;
      event.preventDefault();
      goTo(page, timeAt(event.clientX));
      function move(moveEvent) { transport.setScrub(timeAt(moveEvent.clientX)); }
      function up() {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        window.removeEventListener('pointercancel', up);
      }
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
      window.addEventListener('pointercancel', up);
    });

    // under the band: each track's current block, written out whole
    var readout = el('div', 'tc-pn-readout', host);
    readout.setAttribute('data-tc-step-readout', '');
    var lines = records.map(function (record) {
      var row = el('div', 'tc-pn-read-row', readout);
      row.setAttribute('data-tc-step-now', record.track.title);
      el('span', 'tc-pn-read-name', row, record.track.title);
      var body = el('span', 'tc-pn-read-body', row);
      return {
        row: row,
        count: el('span', 'tc-pn-read-count', body),
        label: el(record.track.mono ? 'code' : 'strong', 'tc-pn-read-label', body),
        detail: el('span', 'tc-pn-read-detail', body),
      };
    });
    // one line when no track has a block at the playhead (between steps, after the last one), instead of a "nothing"
    // line per track: six tracks of two goals said it six times
    var idle = el('div', 'tc-pn-read-row tc-pn-idle', readout);
    idle.setAttribute('data-tc-step-idle', '');
    el('span', 'tc-pn-read-name', idle, '');
    el('span', 'tc-pn-read-body tc-pn-read-detail', idle, 'nothing running at this time');
    if (kinds.length > 1) {
      var legend = el('div', 'tc-pn-legend', host);
      kinds.forEach(function (kind, index) {
        var item = el('span', 'tc-pn-legend-item', legend);
        el('span', 'tc-pn-swatch tc-pn-k' + (index % KIND_COLOURS), item);
        item.appendChild(document.createTextNode(kind));
      });
    }

    // the block the playhead is on: the last one, in the track's order, that holds ``time``
    function currentOf(spans, time) {
      var hit = -1;
      for (var i = 0; i < spans.length; i++) {
        if (spans[i].t0 > time + 1e-9) break;
        if (time <= spans[i].t1 + 1e-9) hit = i;
      }
      return hit;
    }
    function place(element, time) {
      var lane = records[0].lane;
      var x = lane.offsetLeft + (time - t0) / length * lane.clientWidth;
      element.style.left = x + 'px';
    }
    function paint() {
      var time = now(page);
      place(line, time);
      var hover = transport.hoverT;
      ghost.style.display = hover === null || hover === undefined ? 'none' : '';
      if (hover !== null && hover !== undefined) { place(ghost, hover); place(line, transport.t === null ? t1 : transport.t); }
      records.forEach(function (record, index) {
        var spans = record.track.spans;
        var current = currentOf(spans, time);
        if (current === record.current) return;
        if (record.current >= 0) record.blocks[record.current].classList.remove('now');
        if (current >= 0) record.blocks[current].classList.add('now');
        record.current = current;
        var span = current >= 0 ? spans[current] : null;
        lines[index].row.hidden = !span;
        lines[index].count.textContent = span ? (current + 1) + ' of ' + spans.length : '';
        lines[index].label.textContent = span ? span.label : '';
        lines[index].detail.textContent = span ? span.detail : '';
      });
      idle.hidden = records.some(function (record) { return record.current >= 0; });
    }
    transport.onChange(paint);
    window.addEventListener('resize', function () { paintRuler(); paint(); });
    paintRuler();
    paint();
    // the rows have no width until the page is laid out
    if (window.requestAnimationFrame) requestAnimationFrame(function () { paintRuler(); paint(); });
    // in a tab the rows get their width only when the tab is shown: lay the ruler and the line out again then
    return { paint: function () { paintRuler(); paint(); } };
  }

  /* ---------------- a table read at the playhead ---------------- */

  function numberText(value, column) {
    if (value === null || value === undefined) return '—';
    if (typeof value !== 'number') return String(value);
    var text = value.toFixed(column.decimals);
    if (parseFloat(text) === 0) text = (0).toFixed(column.decimals);  // never "-0.00"
    return (column.signed && parseFloat(text) > 0 ? '+' : '') + text;
  }

  function playheadTable(page, record, host, panel) {
    var block = el('div', 'tc-pn-table-wrap', host);
    block.setAttribute('data-tc-playhead-table', panel.id);
    var clock = el('p', 'tc-pn-clock', block);
    var table = el('table', 'tc-pn-table tc-pn-playhead', block);
    var head = el('thead', '', table);
    var groups = el('tr', 'tc-pn-groups', head);
    el('th', '', groups);
    var anyGroup = panel.columns.some(function (column) { return column.group; });
    var last = null;
    panel.columns.forEach(function (column) {
      if (last && last.group === column.group) { last.cell.colSpan += 1; return; }
      last = { group: column.group, cell: el('th', column.group ? 'group' : '', groups, column.group) };
    });
    if (!anyGroup) groups.hidden = true;
    var titles = el('tr', '', head);
    el('th', 'row-title', titles, panel.row_title);
    panel.columns.forEach(function (column, index) {
      var th = el('th', (index && panel.columns[index - 1].group !== column.group) ? 'group-start' : '', titles, column.title);
      if (column.unit) el('span', 'unit', th, ' [' + column.unit + ']');
      if (column.words) th.title = column.words;
    });
    var body = el('tbody', '', table);
    var cells = panel.rows.map(function (rowTitle, rowIndex) {
      var tr = el('tr', '', body);
      tr.setAttribute('data-tc-row', rowTitle);
      el('th', 'row-title', tr, rowTitle);
      return panel.columns.map(function (column, index) {
        var td = el('td', (column.mono ? 'mono ' : '') + ((index && panel.columns[index - 1].group !== column.group) ? 'group-start' : ''), tr);
        td.setAttribute('data-tc-cell', column.title);
        var cell = column.cells[rowIndex];
        if ('c' in cell) {
          td.textContent = numberText(cell.c === '' ? null : cell.c, column);
          td.classList.add(typeof cell.c === 'number' ? 'num' : 'text');
          td.classList.add('const');
        } else {
          // a value in force since its last change is a number when every change is one (a cap, a gain)
          var numeric = 's' in cell || (cell.k.length > 0 && cell.k.every(function (change) {
            return change[1] === null || typeof change[1] === 'number';
          })) || (cell.k.length === 0 && column.cells.some(function (other) { return 's' in other; }));
          td.classList.add(numeric ? 'num' : 'text');
        }
        return { td: td, cell: cell, column: column, shown: undefined };
      });
    });
    if (panel.description) el('p', 'tc-pn-note', block, panel.description);

    function paint() {
      if (record.panel.hidden) return;
      var time = now(page);
      clock.textContent = 'at t = ' + time.toFixed(2) + ' s' +
        (page.transport && page.transport.hoverT !== null && page.transport.hoverT !== undefined ? ' (hovered)' : '');
      var sample = panel.t ? lastAtOrBefore(panel.t, time, function (value) { return value; }) : -1;
      cells.forEach(function (row) {
        row.forEach(function (entry) {
          var cell = entry.cell, value, tone = '';
          if ('c' in cell) return;
          if ('s' in cell) {
            value = sample < 0 ? null : cell.s[sample];
          } else {
            var index = lastAtOrBefore(cell.k, time, function (change) { return change[0]; });
            value = index < 0 ? null : cell.k[index][1];
            tone = index < 0 ? '' : cell.k[index][2];
          }
          var key = value + '|' + tone;
          if (key === entry.shown) return;
          entry.shown = key;
          entry.td.textContent = numberText(value, entry.column);
          entry.td.setAttribute('data-tone', tone || '');
        });
      });
    }
    if (page.transport) page.transport.onChange(paint);
    record.paints.push(paint);
    paint();
  }

  /* ---------------- a table of time-stamped rows ---------------- */

  function timeTable(page, record, host, panel) {
    var block = el('div', 'tc-pn-table-wrap', host);
    block.setAttribute('data-tc-time-table', panel.id);
    var hidden = {};
    var folded = {};
    if (panel.kinds.length) {
      var chips = el('div', 'tc-pn-chips', block);
      el('span', 'tc-pn-chips-label', chips, 'show');
      panel.kinds.forEach(function (kind) {
        hidden[kind[0]] = recall(panel.id + ':hide:' + kind[0], false);
        var chip = el('button', 'tc-pn-chip', chips, kind[1]);
        chip.type = 'button';
        chip.setAttribute('data-tc-kind', kind[0]);
        chip.setAttribute('aria-pressed', hidden[kind[0]] ? 'false' : 'true');
        chip.onclick = function () {
          hidden[kind[0]] = !hidden[kind[0]];
          chip.setAttribute('aria-pressed', hidden[kind[0]] ? 'false' : 'true');
          store(panel.id + ':hide:' + kind[0], hidden[kind[0]]);
          show();
          paint(true);
        };
      });
    }
    var scroll = el('div', 'tc-pn-scroll', block);
    var table = el('table', 'tc-pn-table tc-pn-times', scroll);
    var titles = el('tr', '', el('thead', '', table));
    el('th', 'time', titles, 't [s]');
    panel.columns.forEach(function (column) { el('th', '', titles, column); });
    var body = el('tbody', '', table);
    var deepest = panel.rows.reduce(function (most, row) { return Math.max(most, row.level); }, 0);
    if (deepest > 0) table.classList.add('outline');  // rows fold: the top level reads as headings
    var rows = panel.rows.map(function (row, index) {
      var next = panel.rows[index + 1];
      var parent = !!next && next.level > row.level;
      var tr = el('tr', 'level-' + row.level + (row.tone ? ' tone-' + row.tone : ''), body);
      tr.setAttribute('data-tc-time-row', index);
      if (row.kind) tr.setAttribute('data-kind', row.kind);
      el('td', 'time', tr, row.t === null ? '—' : row.t.toFixed(row.t < 100 ? 3 : 2));  // null: it never happened
      row.cells.forEach(function (text, column) {
        var td = el('td', panel.mono.indexOf(column) !== -1 ? 'mono' : '', tr);
        if (column === 0 && deepest > 0) {
          td.style.paddingLeft = (8 + row.level * 18) + 'px';
          var twist = el('button', 'tc-pn-twist' + (parent ? '' : ' leaf'), td, parent ? '▾' : '');
          twist.type = 'button';
          if (parent) {
            twist.setAttribute('aria-label', 'fold or unfold the rows under this one');
            twist.onclick = function (event) {
              event.stopPropagation();
              folded[index] = !folded[index];
              twist.textContent = folded[index] ? '▸' : '▾';
              show();
            };
            if (row.level >= panel.open_level) { folded[index] = true; twist.textContent = '▸'; }
          }
        }
        // in the tree column the text is a block beside its twist, so a wrapped line stays under its own first line
        if (column === 0 && deepest > 0) el('span', 'tc-pn-treetext', td, text);
        else td.appendChild(document.createTextNode(text));
      });
      tr.addEventListener('click', function () { if (row.t !== null) goTo(page, row.t); });
      return { row: row, tr: tr, state: '' };
    });
    if (panel.description) el('p', 'tc-pn-note', block, panel.description);

    // a row is drawn when its kind is not filtered out and no row above it, of a lower level, is folded
    function show() {
      var closedBelow = null;  // the level of the nearest folded ancestor
      rows.forEach(function (entry, index) {
        var level = entry.row.level;
        if (closedBelow !== null && level <= closedBelow) closedBelow = null;
        entry.tr.hidden = closedBelow !== null || !!hidden[entry.row.kind];
        if (closedBelow === null && folded[index]) closedBelow = level;
      });
    }

    // per level, the newest row at or before the playhead that has not ended is "now"; a row after it is "later"
    function paint() {
      if (record.panel.hidden) return;
      var time = now(page);
      var current = {};
      rows.forEach(function (entry, index) {
        var row = entry.row;
        if (row.t === null || row.t > time + 1e-9) return;
        if (row.end !== null && row.end !== undefined && time > row.end + 1e-9) return;
        current[row.level] = index;
      });
      // a deeper "now" only counts under the current row above it
      rows.forEach(function (entry, index) {
        var state = (entry.row.t === null || entry.row.t > time + 1e-9) ? 'later' : (current[entry.row.level] === index ? 'now' : '');
        if (state === entry.state) return;
        entry.state = state;
        entry.tr.classList.toggle('now', state === 'now');
        entry.tr.classList.toggle('later', state === 'later');
      });
    }
    if (page.transport) page.transport.onChange(paint);
    record.paints.push(paint);
    show();
    paint();
  }

  /* ---------------- a playhead table whose columns pair up as sent / measured ----------------
   *
   * PlayheadColumn(quantity=, role=): the table knows which column is the sent and which the measured value of one
   * quantity, so it can put them beside each other and take their difference. Three switches (Zach, 2026-11-28:
   * "Columns split or side by side / Show measured / Show Error. Those toggles should be enough") and five ways to draw
   * it, picked from the bottom-right drop-down `[data-tc-variant-pick]` (remembered; his standard for variants he has
   * not picked between yet). Variant 1 with the switches as they start is the recommendation. */

  var VARIANTS = [
    { id: 'table', name: 'Numbers side by side' },
    { id: 'stacked', name: 'Stacked cells' },
    { id: 'bars', name: 'Bars' },
    { id: 'cards', name: 'A card per row' },
    { id: 'across', name: 'Rows across' },
  ];
  var pairedTables = [];
  var variant = recall('variant', 'table');
  if (!VARIANTS.some(function (entry) { return entry.id === variant; })) variant = 'table';

  function ensureVariantPicker() {
    if (document.querySelector('[data-tc-variant-pick]')) return;
    var box = el('label', 'tc-variant-pick', document.body);
    box.setAttribute('data-tc-variant-pick', '');
    box.title = 'The sent / measured table: five proposals to compare (temporary)';
    box.appendChild(document.createTextNode('Sent table'));
    var select = el('select', '', box);
    VARIANTS.forEach(function (entry, index) {
      var option = el('option', '', select, (index + 1) + ' · ' + entry.name);
      option.value = entry.id;
    });
    select.value = variant;
    select.addEventListener('change', function () {
      variant = select.value;
      store('variant', variant);
      pairedTables.forEach(function (table) { table.render(); });
    });
  }

  function cellReader(cell, panel) {
    if ('c' in cell) {
      var constant = cell.c === '' ? null : cell.c;
      return function () { return { value: constant, tone: '' }; };
    }
    if ('s' in cell) {
      return function (time) {
        var index = panel.t ? lastAtOrBefore(panel.t, time, function (value) { return value; }) : -1;
        return { value: index < 0 ? null : cell.s[index], tone: '' };
      };
    }
    return function (time) {
      var index = lastAtOrBefore(cell.k, time, function (change) { return change[0]; });
      return index < 0 ? { value: null, tone: '' } : { value: cell.k[index][1], tone: cell.k[index][2] };
    };
  }
  // the smallest and largest number a cell ever holds (the bars' scale)
  function cellRange(cell, range) {
    var values = 'c' in cell ? [cell.c] : 's' in cell ? cell.s : cell.k.map(function (change) { return change[1]; });
    values.forEach(function (value) {
      if (typeof value !== 'number') return;
      if (value < range[0]) range[0] = value;
      if (value > range[1]) range[1] = value;
    });
    return range;
  }

  function pairedTable(page, record, host, panel) {
    ensureVariantPicker();
    var block = el('div', 'tc-pn-table-wrap tc-pn-paired', host);
    block.setAttribute('data-tc-playhead-table', panel.id);
    var state = {
      layout: recall('paired:layout', 'quantity'),   // 'quantity' = side by side, 'source' = all sent, then all measured
      measured: recall('paired:measured', true),
      error: recall('paired:error', true),
    };
    var quantities = {};
    panel.columns.forEach(function (column) {
      if (!column.role) return;
      if (!quantities[column.quantity]) quantities[column.quantity] = { name: column.quantity };
      quantities[column.quantity][column.role] = column;
    });

    var bar = el('div', 'tc-pn-chips', block);
    var clock = el('span', 'tc-pn-clock', bar);
    function toggle(key, label, title, flip) {
      var chip = el('button', 'tc-pn-chip', bar, label);
      chip.type = 'button';
      chip.title = title;
      chip.setAttribute('data-tc-toggle', key);
      chip.onclick = function () { flip(); store('paired:' + key, state[key]); render(); };
      return chip;
    }
    var layoutChip = toggle('layout', '', 'columns: each quantity\'s sent, measured and error side by side, or every sent ' +
      'column together and then every measured one', function () { state.layout = state.layout === 'quantity' ? 'source' : 'quantity'; });
    var measuredChip = toggle('measured', 'Show measured', 'the measured value beside the sent one',
      function () { state.measured = !state.measured; });
    var errorChip = toggle('error', 'Show error', 'error = sent − measured, where both are numbers',
      function () { state.error = !state.error; });
    var body = el('div', 'tc-pn-paired-body', block);
    if (panel.description) el('p', 'tc-pn-note', block, panel.description);
    var live = [];

    function valueNode(node, read, column) {
      live.push(function (time) {
        var got = read(time);
        var text = numberText(got.value, column);
        if (node.textContent !== text) node.textContent = text;
        if ((node.getAttribute('data-tone') || '') !== (got.tone || '')) node.setAttribute('data-tone', got.tone || '');
      });
    }
    function errorOf(quantity, row) {
      var sent = cellReader(quantity.sent.cells[row], panel), measured = cellReader(quantity.measured.cells[row], panel);
      return function (time) {
        var a = sent(time).value, b = measured(time).value;
        return { value: typeof a === 'number' && typeof b === 'number' ? a - b : null, tone: '' };
      };
    }
    function errorFormat(quantity) { return { decimals: quantity.sent.decimals, signed: true }; }
    function unitText(column) { return column.unit ? ' [' + column.unit + ']' : ''; }

    // One spec per value the table can show, in reading order: the columns of variant 1, the rows of variant 5.
    function specs() {
      var list = [];
      function plain(column) {
        list.push({ key: column.title, group: column.group, title: column.title, unit: column.unit, column: column, kind: 'plain',
          read: function (row) { return cellReader(column.cells[row], panel); } });
      }
      function value(quantity, role, bySource) {
        var column = quantity[role];
        list.push({ key: quantity.name + ':' + role, group: bySource ? column.group : quantity.name + unitText(column),
          title: bySource ? column.title : role, unit: bySource ? column.unit : '', column: column, kind: role,
          words: column.title + (column.words ? ': ' + column.words : ''), start: !bySource && role === 'sent',
          read: function (row) { return cellReader(column.cells[row], panel); } });
      }
      function error(quantity, bySource) {
        list.push({ key: quantity.name + ':error', group: bySource ? 'Error (sent − measured)' : quantity.name + unitText(quantity.sent),
          title: bySource ? quantity.name : 'Δ', unit: bySource ? quantity.sent.unit : '', column: errorFormat(quantity), kind: 'error',
          words: quantity.name + ': sent − measured',
          read: function (row) { return errorOf(quantity, row); } });
      }
      var bySource = state.layout === 'source';
      panel.columns.forEach(function (column) {
        var quantity = quantities[column.quantity];
        if (!column.role) plain(column);
        else if (column.role === 'sent') {
          value(quantity, 'sent', bySource);
          if (!bySource && state.measured && quantity.measured) value(quantity, 'measured', false);
          if (!bySource && state.error && quantity.measured) error(quantity, false);
        } else if (bySource && state.measured) value(quantity, 'measured', true);
      });
      if (bySource && state.error) {
        panel.columns.forEach(function (column) {
          if (column.role === 'sent' && quantities[column.quantity].measured) error(quantities[column.quantity], true);
        });
      }
      return list;
    }

    function headerRows(table, first, list) {
      var head = el('thead', '', table);
      var groups = el('tr', 'tc-pn-groups', head);
      el('th', '', groups);
      var last = null;
      list.forEach(function (spec) {
        if (last && last.group === spec.group) { last.cell.colSpan += 1; return; }
        last = { group: spec.group, cell: el('th', spec.group ? 'group' : '', groups, spec.group) };
      });
      var titles = el('tr', '', head);
      el('th', 'row-title', titles, first);
      list.forEach(function (spec, index) {
        var th = el('th', (index && list[index - 1].group !== spec.group) ? 'group-start' : '', titles, spec.title);
        if (spec.unit) el('span', 'unit', th, ' [' + spec.unit + ']');
        if (spec.words || (spec.column && spec.column.words)) th.title = spec.words || spec.column.words;
      });
    }
    function valueCell(tr, spec, row, start) {
      var numeric = spec.kind !== 'plain' || !spec.column.cells || spec.column.cells.some(function (cell) {
        return 's' in cell || typeof cell.c === 'number' ||
          ('k' in cell && cell.k.some(function (change) { return typeof change[1] === 'number'; }));
      });
      var td = el('td', (numeric ? 'num' : 'text') + ' kind-' + spec.kind + (spec.column.mono ? ' mono' : '') + (start ? ' group-start' : ''), tr);
      td.setAttribute('data-tc-cell', spec.key);
      valueNode(td, spec.read(row), spec.column);
      return td;
    }

    // 1 · the table: one row per joint, the specs as columns
    function drawTable() {
      var list = specs();
      var scroll = el('div', 'tc-pn-scroll', body);
      var table = el('table', 'tc-pn-table tc-pn-playhead', scroll);
      headerRows(table, panel.row_title, list);
      var tbody = el('tbody', '', table);
      panel.rows.forEach(function (title, row) {
        var tr = el('tr', '', tbody);
        tr.setAttribute('data-tc-row', title);
        el('th', 'row-title', tr, title);
        list.forEach(function (spec, index) { valueCell(tr, spec, row, index && list[index - 1].group !== spec.group); });
      });
    }

    // 5 · rows across: one column per joint, the specs as rows
    function drawAcross() {
      var list = specs();
      var scroll = el('div', 'tc-pn-scroll', body);
      var table = el('table', 'tc-pn-table tc-pn-playhead tc-pn-across', scroll);
      var titles = el('tr', '', el('thead', '', table));
      el('th', 'row-title', titles, '');
      panel.rows.forEach(function (title) { el('th', 'num', titles, title); });
      var tbody = el('tbody', '', table);
      list.forEach(function (spec, index) {
        var tr = el('tr', (index && list[index - 1].group !== spec.group) ? 'block-start' : '', tbody);
        var th = el('th', 'row-title', tr, (spec.group && spec.group !== spec.title ? spec.group + ' · ' : '') + spec.title);
        if (spec.unit) el('span', 'unit', th, ' [' + spec.unit + ']');
        panel.rows.forEach(function (title, row) { valueCell(tr, spec, row, false).setAttribute('data-tc-row', title); });
      });
    }

    // 2 / 3 · one column per quantity; the cell holds sent over measured (stacked) or both on one scale (bars)
    function drawQuantityCells(bars) {
      var scroll = el('div', 'tc-pn-scroll', body);
      var table = el('table', 'tc-pn-table tc-pn-playhead tc-pn-' + (bars ? 'bars' : 'stacked'), scroll);
      var titles = el('tr', '', el('thead', '', table));
      el('th', 'row-title', titles, panel.row_title);
      var shown = panel.columns.filter(function (column) { return column.role !== 'measured'; });
      shown.forEach(function (column) {
        var th = el('th', '', titles, column.role ? column.quantity : column.title);
        if (column.unit) el('span', 'unit', th, ' [' + column.unit + ']');
        if (column.role) el('span', 'unit', th, state.measured && quantities[column.quantity].measured ? ' · sent over measured' : ' · sent');
      });
      var tbody = el('tbody', '', table);
      panel.rows.forEach(function (title, row) {
        var tr = el('tr', '', tbody);
        tr.setAttribute('data-tc-row', title);
        el('th', 'row-title', tr, title);
        shown.forEach(function (column) {
          if (!column.role) {
            valueCell(tr, { key: column.title, kind: 'plain', column: column, read: function (r) { return cellReader(column.cells[r], panel); } }, row, false);
            return;
          }
          var quantity = quantities[column.quantity];
          var td = el('td', 'pair', tr);
          td.setAttribute('data-tc-cell', quantity.name);
          var sentRead = cellReader(quantity.sent.cells[row], panel);
          var measuredRead = quantity.measured ? cellReader(quantity.measured.cells[row], panel) : null;
          var showMeasured = state.measured && measuredRead, showError = state.error && measuredRead;
          if (bars) {
            var range = cellRange(quantity.sent.cells[row], [Infinity, -Infinity]);
            if (measuredRead) cellRange(quantity.measured.cells[row], range);
            if (!isFinite(range[0])) range = [0, 1];
            if (range[1] - range[0] < 1e-9) range = [range[0] - 1, range[1] + 1];
            var track = el('div', 'tc-pn-bar', td);
            track.title = 'scale: ' + numberText(range[0], quantity.sent) + ' … ' + numberText(range[1], quantity.sent) +
              (quantity.sent.unit ? ' ' + quantity.sent.unit : '') + ' (this row\'s range over the run)';
            var sentMark = el('span', 'tc-pn-mark sent', track);
            var measuredMark = showMeasured ? el('span', 'tc-pn-mark measured', track) : null;
            live.push(function (time) {
              var a = sentRead(time).value, b = measuredRead ? measuredRead(time).value : null;
              sentMark.hidden = typeof a !== 'number';
              if (typeof a === 'number') sentMark.style.left = ((a - range[0]) / (range[1] - range[0]) * 100) + '%';
              if (measuredMark) {
                measuredMark.hidden = typeof b !== 'number';
                if (typeof b === 'number') measuredMark.style.left = ((b - range[0]) / (range[1] - range[0]) * 100) + '%';
              }
            });
          }
          var numbers = el('div', 'tc-pn-pair' + (bars ? ' inline' : ''), td);
          var sentNode = el('span', 'sent', numbers);
          sentNode.setAttribute('data-tc-part', 'sent');
          valueNode(sentNode, sentRead, quantity.sent);
          if (showMeasured) {
            var measuredNode = el('span', 'measured', numbers);
            measuredNode.setAttribute('data-tc-part', 'measured');
            valueNode(measuredNode, measuredRead, quantity.measured);
          }
          if (showError) {
            var errorNode = el('span', 'error', numbers);
            errorNode.setAttribute('data-tc-part', 'error');
            el('span', 'delta', errorNode, 'Δ ');
            valueNode(el('span', '', errorNode), errorOf(quantity, row), errorFormat(quantity));
          }
        });
      });
    }

    // 4 · a card per joint: its quantities down, sent / measured / error across
    function drawCards() {
      var grid = el('div', 'tc-pn-cards', body);
      var paired = panel.columns.filter(function (column) { return column.role === 'sent'; });
      var others = panel.columns.filter(function (column) { return !column.role; });
      panel.rows.forEach(function (title, row) {
        var card = el('section', 'tc-pn-card', grid);
        card.setAttribute('data-tc-row', title);
        var head = el('header', '', card);
        el('strong', '', head, title);
        others.forEach(function (column) {
          var chip = el('span', 'tc-pn-fact', head);
          el('span', 'label', chip, column.title + ' ');
          var node = el('span', column.mono ? 'mono' : '', chip);
          node.setAttribute('data-tc-cell', column.title);
          valueNode(node, cellReader(column.cells[row], panel), column);
        });
        var table = el('table', 'tc-pn-table tc-pn-playhead', card);
        var titles = el('tr', '', el('thead', '', table));
        el('th', 'row-title', titles, '');
        el('th', 'num', titles, 'sent');
        if (state.measured) el('th', 'num', titles, 'measured');
        if (state.error) el('th', 'num', titles, 'Δ');
        var tbody = el('tbody', '', table);
        paired.forEach(function (column) {
          var quantity = quantities[column.quantity];
          var tr = el('tr', '', tbody);
          var th = el('th', 'row-title', tr, quantity.name);
          if (column.unit) el('span', 'unit', th, ' [' + column.unit + ']');
          function cell(kind, read, format) {
            var td = el('td', 'num kind-' + kind, tr);
            td.setAttribute('data-tc-cell', quantity.name + ':' + kind);
            if (read) valueNode(td, read, format); else td.textContent = '';
          }
          cell('sent', cellReader(quantity.sent.cells[row], panel), quantity.sent);
          if (state.measured) cell('measured', quantity.measured ? cellReader(quantity.measured.cells[row], panel) : null, quantity.measured);
          if (state.error) cell('error', quantity.measured ? errorOf(quantity, row) : null, errorFormat(quantity));
        });
      });
    }

    function paint() {
      if (record.panel.hidden) return;
      var time = now(page);
      clock.textContent = 'at t = ' + time.toFixed(2) + ' s' +
        (page.transport && page.transport.hoverT !== null && page.transport.hoverT !== undefined ? ' (hovered)' : '');
      live.forEach(function (update) { update(time); });
    }
    function render() {
      body.textContent = '';
      live = [];
      block.setAttribute('data-tc-variant', variant);
      var free = variant === 'table' || variant === 'across';   // the other three are side by side by nature
      layoutChip.textContent = 'Columns: ' + (state.layout === 'quantity' || !free ? 'side by side' : 'split by source');
      layoutChip.setAttribute('aria-pressed', state.layout === 'quantity' || !free ? 'true' : 'false');
      layoutChip.disabled = !free;
      measuredChip.setAttribute('aria-pressed', state.measured ? 'true' : 'false');
      errorChip.setAttribute('aria-pressed', state.error ? 'true' : 'false');
      if (variant === 'stacked') drawQuantityCells(false);
      else if (variant === 'bars') drawQuantityCells(true);
      else if (variant === 'cards') drawCards();
      else if (variant === 'across') drawAcross();
      else drawTable();
      paint();
    }
    if (page.transport) page.transport.onChange(paint);
    record.paints.push(paint);
    pairedTables.push({ render: render });
    render();
  }

  function part(page, record, host, panel, grouped) {
    if (grouped && panel.heading) el('h4', 'tc-pn-subheading', host, panel.heading);
    if (panel.kind === 'band') {
      var drawn = band(page, host, panel.tracks);
      if (drawn) record.paints.push(drawn.paint);
    } else if (panel.kind === 'playhead') {
      if (panel.columns.some(function (column) { return column.role; })) pairedTable(page, record, host, panel);
      else playheadTable(page, record, host, panel);
    } else if (panel.kind === 'times') timeTable(page, record, host, panel);
    else el('p', 'tc-empty', host, 'This report was written by a newer traj_compare: no view for a "' + panel.kind + '" panel.');
  }

  function tab(page, record, host, panel) {
    record.paints = [];
    record.paintPanel = function () { record.paints.forEach(function (paint) { paint(); }); };
    if (panel.kind === 'group') panel.parts.forEach(function (inner) { part(page, record, host, inner, true); });
    else part(page, record, host, panel, false);
  }

  return { band: band, tab: tab, variants: VARIANTS };
})();
