/* traj_compare — dataset view: Dataset → Target → Run, organised around the target trajectory.
 *
 * Reads the payload dataset.py embeds (SI: rad, m, s) and draws one of two levels by the hash route
 * (docs/NAVIGATION.md Part A; Zach 2026-11-19, traj compare view feedback: "the Target trajectory is
 * kinda the primary thing we want to organize things around"):
 *   #/              the Dataset: the domain's Summary page, a summary band across every target, then the
 *                   targets as cards ⇄ a league table ⇄ today's runs view (answer line, runs x pairs table,
 *                   joint x run heatmap, peak-time strip, ISO 9283 cards).
 *   #/target/<slug> one Target: its lines in a run list on the left, a verdict, and two question tabs
 *                   (repeatability as lines-or-fans over trajectory time; a control chart across dates).
 * A line's ↗ opens runs/<slug>/report.html, the Run level. WHY degrees here and not in the data: angles
 * are SI in rows.json and the payload's scalars, and become degrees only at this display edge (Zach:
 * angles read in degrees); the drawn error series arrive in degrees, already a display projection.
 */
(function () {
  'use strict';

  var D = JSON.parse(document.getElementById('traj-compare-dataset').textContent);
  var DEG = 180 / Math.PI;
  var REFERENCE = 'reference';
  var TABLE_ROWS = 300;
  // Joint colours in the peak strip; the family palette of report.py's situations.
  var PALETTE = ['#2a78d6', '#eb6834', '#2f9e44', '#8e5bd1', '#c22f6e', '#17a2b8', '#a67c00', '#6b7a8f'];
  var METRICS = [['rms', 'RMS'], ['max_abs', 'Max'], ['p95_abs', 'P95'], ['final', 'Final']];

  var S = { pair: null, showAll: false, order: 'worst', metric: 'rms', sort: null, filters: {}, limit: TABLE_ROWS };

  // ── helpers ────────────────────────────────────────────────────────────────

  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function $(id) { return document.getElementById(id); }
  function make(tag, className, parent, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  function pk(pair) { return pair[0] + '\u0000' + pair[1]; }
  function label(name) { return name === REFERENCE ? 'reference' : (D.labels[name] || name); }
  function pairLabel(pair) { return label(pair[0]) + ' → ' + label(pair[1]); }
  function nice(value, digits) {
    return Math.abs(value) < 10 ? value.toFixed(digits === undefined ? 2 : digits) : value.toFixed(1);
  }
  function deg(rad) { return rad === null || rad === undefined ? null : rad * DEG; }
  function mm(metres) { return metres === null || metres === undefined ? null : metres * 1000; }
  function tint(value, maximum) {
    var share = maximum > 0 ? Math.min(1, Math.abs(value) / maximum) : 0;
    return 'rgba(42,120,214,' + (0.05 + 0.5 * share).toFixed(3) + ')';
  }
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return false; });
    }
    var area = make('textarea', '', document.body, text);
    area.style.cssText = 'position:fixed;left:-9999px;top:0';
    area.select();
    var done = false;
    try { done = document.execCommand('copy'); } catch (error) { done = false; }
    document.body.removeChild(area);
    return Promise.resolve(done);
  }

  // ── data ───────────────────────────────────────────────────────────────────

  var rowsAll = D.rows;
  var runIndex = {};
  D.runs.forEach(function (run, index) { runIndex[run.name] = index; });
  var spanOf = {};
  D.runs.forEach(function (run) { spanOf[run.name] = run.t_span; });

  rowsAll.forEach(function (row) {
    var worst = null, worstJoint = '', worstMax = null, worstMaxJoint = '';
    D.joint_names.forEach(function (joint) {
      var stats = row.joints && row.joints[joint];
      if (!stats) return;
      if (stats.rms !== null && (worst === null || stats.rms > worst)) { worst = stats.rms; worstJoint = joint; }
      if (stats.max_abs !== null && (worstMax === null || stats.max_abs > worstMax)) {
        worstMax = stats.max_abs; worstMaxJoint = joint;
      }
    });
    row._worst = { rms: worst, joint: worstJoint, max: worstMax, maxJoint: worstMaxJoint };
  });

  var allPairs = [];
  (function () {
    var seen = {};
    rowsAll.forEach(function (row) {
      if (!seen[pk(row.pair)]) { seen[pk(row.pair)] = true; allPairs.push(row.pair); }
    });
  })();

  function visiblePairs() {
    if (S.showAll) return allPairs;
    var wanted = {};
    D.default_pairs.forEach(function (pair) { wanted[pk(pair)] = true; });
    var shown = allPairs.filter(function (pair) { return wanted[pk(pair)]; });
    return shown.length ? shown : allPairs;
  }
  function hiddenPairCount() {
    var wanted = {};
    D.default_pairs.forEach(function (pair) { wanted[pk(pair)] = true; });
    return allPairs.filter(function (pair) { return !wanted[pk(pair)]; }).length;
  }
  function visibleSeries() {
    var names = {};
    visiblePairs().forEach(function (pair) { names[pair[0]] = true; names[pair[1]] = true; });
    return names;
  }
  // The pair the answer line, heatmap and strip describe: the last pair that starts at the
  // reference (with a sim and a real series, how well the real run tracks the target).
  function focusPair() {
    var pairs = visiblePairs();
    var fromReference = pairs.filter(function (pair) { return pair[0] === REFERENCE; });
    return (fromReference.length ? fromReference : pairs).slice(-1)[0];
  }
  function selectedPair() {
    var pairs = visiblePairs();
    var keys = pairs.map(pk);
    if (!S.pair || keys.indexOf(pk(S.pair)) === -1) S.pair = focusPair();
    return S.pair;
  }

  function passesFilters(row) {
    return D.tag_keys.every(function (key) {
      var wanted = S.filters[key];
      if (!wanted) return true;
      var have = row.tags[key] === undefined ? '' : String(row.tags[key]);
      return wanted.exact ? have === wanted.value : have.toLowerCase().indexOf(wanted.value.toLowerCase()) !== -1;
    });
  }
  function rowsOfPair(pair) {
    return rowsAll.filter(function (row) { return pk(row.pair) === pk(pair) && passesFilters(row); });
  }
  function orderedRows(rows) {
    var copy = rows.slice();
    if (S.order === 'worst') {
      copy.sort(function (a, b) { return (b._worst.rms === null ? -1 : b._worst.rms) - (a._worst.rms === null ? -1 : a._worst.rms); });
    } else {
      copy.sort(function (a, b) { return runIndex[a.run] - runIndex[b.run]; });
    }
    return copy;
  }

  // ── skeleton ───────────────────────────────────────────────────────────────

  var main = $('ds-main');
  main.innerHTML =
    '<nav class="ds-crumbs" id="ds-crumbs" aria-label="Breadcrumb"></nav>' +
    '<div id="ds-level-dataset">' +
    '<header class="ds-head"><h1></h1><p class="ds-sub"></p><div class="ds-banner" id="ds-banner" hidden></div></header>' +
    '<div class="ds-summary" id="ds-summary"></div>' +
    '<section class="ds-band" id="ds-band" data-tc-dataset-summary></section>' +
    '<section class="ds-targets"><div class="ds-targets-head"><h2>Which config tracks each target better?</h2>' +
    '<div class="ds-seg ds-viewswitch" data-tc-targets-view role="group" aria-label="Show the targets as">' +
    '<button type="button" data-view="cards">Cards</button><button type="button" data-view="table">Table</button>' +
    '<button type="button" data-view="runs">Runs</button></div><div class="ds-bar ds-levelbar" id="ds-dataset-controls"></div></div>' +
    '<div id="ds-view-cards"></div><div id="ds-view-table"></div><div id="ds-view-runs">' +
    '<p class="ds-answer" id="ds-answer"></p><div class="ds-bar" id="ds-global"></div>' +
    '<section class="ds-card"><h2>Runs <span class="ds-hint" id="ds-table-count"></span></h2>' +
    '<div class="ds-bar" id="ds-filters"></div><div class="ds-scroll" id="ds-table"></div>' +
    '<div class="ds-more" id="ds-more"></div><div class="ds-status" id="ds-status" role="status"></div></section>' +
    '<section class="ds-card"><h2>Where the error is <span class="ds-hint">joint × run · click a cell to open the run</span></h2>' +
    '<div class="ds-bar" id="ds-heat-controls"></div><div class="ds-heatwrap" id="ds-heat"></div>' +
    '<div class="ds-legend" id="ds-heat-legend"></div></section>' +
    '<section class="ds-card"><h2>When the error peaks <span class="ds-hint">one dot per joint, at the instant of its largest error</span></h2>' +
    '<div class="ds-keys" id="ds-peak-keys"></div><div class="ds-peaks" id="ds-peaks"></div><div id="ds-peak-axis"></div></section>' +
    '<section class="ds-card"><h2>Accuracy and repeatability <span class="ds-hint">ISO 9283, per group and series</span></h2>' +
    '<div class="ds-iso" id="ds-iso"></div><p class="ds-note" id="ds-iso-note"></p></section>' +
    '</div></section></div>' +
    '<div id="ds-level-target" hidden></div>' +
    '<footer class="ds-foot" id="ds-foot"></footer>';
  document.title = D.title;
  main.querySelector('#ds-level-dataset h1').textContent = D.title;
  main.querySelector('#ds-level-dataset .ds-sub').textContent =
    D.runs.length + ' runs · ' + D.series.length + ' series · ' + D.generated;

  // ── global controls: pair, order, show all pairs ───────────────────────────

  function buildGlobalControls() {
    var bar = $('ds-global');
    bar.innerHTML = '';
    var pairs = visiblePairs();
    var current = selectedPair();
    if (pairs.length > 1) {
      var pairLabelEl = make('label', 'ds-pairpick', null);
      make('span', 'ds-k', pairLabelEl, 'Pair');
      var pairSelect = make('select', '', pairLabelEl);
      pairs.forEach(function (pair) {
        var option = make('option', '', pairSelect, pairLabel(pair));
        option.value = pk(pair);
        option.selected = pk(pair) === pk(current);
      });
      pairSelect.onchange = function () {
        S.pair = pairs.filter(function (pair) { return pk(pair) === pairSelect.value; })[0];
        renderPairViews();
      };
      bar.appendChild(pairLabelEl);
      pairLabelEl.style.marginLeft = '0';
    }
    var orderLabel = make('label', '', bar);
    make('span', 'ds-k', orderLabel, 'Order runs');
    var orderSelect = make('select', '', orderLabel);
    [['worst', 'worst first'], ['recorded', 'as recorded']].forEach(function (item) {
      var option = make('option', '', orderSelect, item[1]);
      option.value = item[0];
      option.selected = S.order === item[0];
    });
    orderSelect.onchange = function () { S.order = orderSelect.value; renderPairViews(); };
    var hidden = hiddenPairCount();
    if (hidden > 0) {
      var allLabel = make('label', '', bar);
      var check = make('input', '', allLabel);
      check.type = 'checkbox';
      check.checked = S.showAll;
      make('span', '', allLabel, 'show all pairs (' + (S.showAll ? allPairs.length : allPairs.length - hidden) + ' of ' + allPairs.length + ')');
      check.onchange = function () {
        S.showAll = check.checked;
        buildGlobalControls();
        renderAll();
      };
    }
  }

  // ── answer line ────────────────────────────────────────────────────────────

  function renderAnswer() {
    var pair = selectedPair();
    var rows = rowsOfPair(pair);
    var analysed = rows.filter(function (row) { return !row.error; });
    var parts = [];
    parts.push('<b>' + rows.length + ' run' + (rows.length === 1 ? '' : 's') + '</b>');
    if (D.has_tolerances) {
      var failed = analysed.filter(function (row) { return row.verdict && !row.verdict.ok; }).length;
      var passed = analysed.filter(function (row) { return row.verdict && row.verdict.ok; }).length;
      parts.push(passed + ' pass' + (failed ? ', <span class="ds-fail">' + failed + ' fail</span>' : ''));
    }
    var broken = rows.length - analysed.length;
    if (broken) parts.push('<span class="ds-fail">' + broken + ' could not be analysed</span>');
    var text = parts.join(' · ') + ' <span class="ds-mut">on ' + esc(pairLabel(pair)) + '</span>';
    var worstRow = null;
    analysed.forEach(function (row) {
      if (row._worst.rms !== null && (!worstRow || row._worst.rms > worstRow._worst.rms)) worstRow = row;
    });
    if (worstRow && analysed.length > 1) {
      var peak = worstRow.peak_t && worstRow.peak_t[worstRow._worst.joint];
      text += ' · worst: <b>' + esc(worstRow.run) + '</b>, ' + nice(deg(worstRow._worst.rms)) + '° RMS on ' +
        esc(worstRow._worst.joint) + (peak === null || peak === undefined ? '' : ', peaking at ' + peak.toFixed(2) + ' s');
    }
    $('ds-answer').innerHTML = text;
  }

  // ── runs x pairs table ─────────────────────────────────────────────────────

  function numberColumn(key, title, unit, get, options) {
    options = options || {};
    return { key: key, label: title, unit: unit, get: get, shade: !!options.shade, digits: options.digits, joint: options.joint };
  }

  function buildColumns(pairs) {
    var cols = [{ key: 'run', label: 'Run', text: true, first: true, get: function (row) { return row.run; } }];
    if (pairs.length > 1) cols.push({ key: 'pair', label: 'Pair', text: true, get: function (row) { return pairLabel(row.pair); } });
    D.tag_keys.forEach(function (tag) {
      cols.push({ key: 'tag:' + tag, label: tag, text: true, tag: true, get: function (row) { return row.tags[tag] === undefined ? '' : String(row.tags[tag]); } });
    });
    cols.push({
      key: 'verdict', label: 'Verdict', text: true, verdict: true,
      get: function (row) { return row.error ? 'not analysed' : (row.verdict ? (row.verdict.ok ? 'pass' : 'fail') : ''); },
    });
    cols.push(numberColumn('worst_rms', 'Worst RMS', '°', function (row) { return deg(row._worst.rms); }, { shade: true, joint: function (row) { return row._worst.joint; } }));
    cols.push(numberColumn('worst_max', 'Worst max', '°', function (row) { return deg(row._worst.max); }, { shade: true, joint: function (row) { return row._worst.maxJoint; } }));
    D.joint_names.forEach(function (joint) {
      cols.push(numberColumn('rms:' + joint, joint + ' RMS', '°', function (row) {
        return row.joints && row.joints[joint] ? deg(row.joints[joint].rms) : null;
      }, { shade: true }));
    });
    if (D.has_tcp) {
      cols.push(numberColumn('tcp', 'TCP RMS', 'mm', function (row) { return row.tcp ? mm(row.tcp.rms) : null; }, { shade: true }));
    }
    cols.push(numberColumn('latency', 'Latency', 'ms', function (row) {
      return row.latency_s === null || row.latency_s === undefined ? null : row.latency_s * 1000;
    }, { digits: 1 }));
    cols.push(numberColumn('coverage', 'Coverage', '%', function (row) {
      return row.coverage === null || row.coverage === undefined ? null : row.coverage * 100;
    }, { digits: 0 }));
    cols.push({ key: 'actions', label: '', actions: true });
    return cols;
  }

  function renderTable() {
    var pairs = visiblePairs();
    var wanted = {};
    pairs.forEach(function (pair) { wanted[pk(pair)] = true; });
    var rows = rowsAll.filter(function (row) { return wanted[pk(row.pair)] && passesFilters(row); });
    var cols = buildColumns(pairs);
    if (!D.has_tolerances && !rows.some(function (row) { return row.error; })) {
      cols = cols.filter(function (col) { return !col.verdict; });
    }
    if (S.sort) {
      var sortCol = cols.filter(function (col) { return col.key === S.sort.key; })[0];
      if (sortCol) {
        rows = rows.slice().sort(function (a, b) {
          var left = sortCol.get(a), right = sortCol.get(b);
          var leftMissing = left === null || left === undefined || left === '';
          var rightMissing = right === null || right === undefined || right === '';
          if (leftMissing || rightMissing) return leftMissing === rightMissing ? 0 : (leftMissing ? 1 : -1);
          var order = sortCol.text ? String(left).localeCompare(String(right), undefined, { numeric: true }) : left - right;
          return order * S.sort.dir;
        });
      }
    }
    var shown = rows.slice(0, S.limit);
    var peaks = {};
    cols.forEach(function (col) {
      if (!col.shade) return;
      var maximum = 0;
      shown.forEach(function (row) {
        var value = col.get(row);
        if (value !== null && value !== undefined && value > maximum) maximum = value;
      });
      peaks[col.key] = maximum;
    });

    var html = '<table class="ds-table"><thead><tr>';
    cols.forEach(function (col) {
      var classes = [];
      if (col.first) classes.push('ds-first');
      if (col.text) classes.push('ds-text');
      if (col.tag) classes.push('ds-tag');
      if (S.sort && S.sort.key === col.key) classes.push('sorted', S.sort.dir === 1 ? 'asc' : 'desc');
      html += '<th data-key="' + esc(col.key) + '" class="' + classes.join(' ') + '">' + esc(col.label) +
        (col.unit ? '<span class="ds-unit">' + esc(col.unit) + '</span>' : '') + '</th>';
    });
    html += '</tr></thead><tbody>';
    shown.forEach(function (row) {
      html += '<tr>';
      cols.forEach(function (col) {
        if (col.actions) {
          html += '<td class="ds-actions"><a class="ds-link" href="' + esc(row.report) + '">Open run</a>' +
            '<button class="ds-btn" data-rerun="' + rowsAll.indexOf(row) + '">Open in Rerun</button></td>';
          return;
        }
        var value = col.get(row);
        if (col.first) {
          html += '<td class="ds-first" title="' + esc(row.run) + '">' + esc(value) + '</td>';
        } else if (col.verdict) {
          var cls = row.error || (row.verdict && !row.verdict.ok) ? 'ds-violated' : (value === 'pass' ? 'ds-pass' : 'ds-muted');
          var shortCode = '';
          if (row.verdict && !row.verdict.ok) {
            shortCode = ' · ' + ({ PATH_TOLERANCE_VIOLATED: 'path', GOAL_TOLERANCE_VIOLATED: 'goal' }[row.verdict.code_name] || row.verdict.code_name);
          }
          var title = row.error || (row.verdict ? row.verdict.error_string : '');
          html += '<td class="ds-text ' + cls + '" title="' + esc(title) + '">' + esc(value || '—') + esc(shortCode) + '</td>';
        } else if (col.text) {
          html += '<td class="ds-text' + (col.tag ? ' ds-tag' : '') + '">' + esc(value === '' ? '—' : value) + '</td>';
        } else if (value === null || value === undefined) {
          html += '<td class="ds-muted">—</td>';
        } else {
          var classes = [];
          var style = '';
          if (col.shade) {
            classes.push('ds-shade');
            style = ' style="--tint:' + tint(value, peaks[col.key]) + '"';
            if (shown.length > 1 && value === peaks[col.key]) classes.push('ds-worst');
          }
          var text = col.digits === undefined ? nice(value) : value.toFixed(col.digits);
          var where = col.joint ? '<span class="ds-joint">' + esc(col.joint(row)) + '</span>' : '';
          html += '<td class="' + classes.join(' ') + '"' + style + '>' + text + where + '</td>';
        }
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    $('ds-table').innerHTML = html;
    $('ds-table-count').textContent = rows.length + ' row' + (rows.length === 1 ? '' : 's') +
      ' · click a column to sort';
    var more = $('ds-more');
    more.innerHTML = '';
    if (rows.length > shown.length) {
      var button = make('button', 'ds-btn', more, 'Show all ' + rows.length + ' rows');
      button.onclick = function () { S.limit = Infinity; renderTable(); };
    }
  }

  $('ds-table').addEventListener('click', function (event) {
    var head = event.target.closest('th[data-key]');
    if (head) {
      var key = head.getAttribute('data-key');
      if (key === 'actions') return;
      S.sort = S.sort && S.sort.key === key ? { key: key, dir: -S.sort.dir } : { key: key, dir: head.classList.contains('ds-text') ? 1 : -1 };
      renderTable();
      return;
    }
    var button = event.target.closest('button[data-rerun]');
    if (button) openRerun(rowsAll[Number(button.getAttribute('data-rerun'))]);
  });

  function setStatus(text, bad) {
    var status = $('ds-status');
    status.textContent = text;
    status.className = 'ds-status' + (bad ? ' bad' : '');
  }

  // WHY POST to the serve endpoint and fall back to the command: a page cannot start a process;
  // `python -m traj_compare.serve` can (same as the run report's button), a file:// page cannot.
  function openRerun(row) {
    var name = row.run + ' · ' + pairLabel(row.pair);
    function fallback(reason) {
      copyText(row.rerun_command).then(function (copied) {
        setStatus((copied ? 'Copied the command for ' : 'Command for ') + name + ' (' + reason + '): ' + row.rerun_command, !copied);
      });
    }
    if (location.protocol !== 'http:' && location.protocol !== 'https:') {
      fallback('this page is not served; run ' + D.serve_command + ' to launch from here');
      return;
    }
    setStatus('Building ' + name + ' and opening it in Rerun…');
    // WHY resolved against the page URL: one server holds several sites (ur5e/, pendulum/, ...), and the
    // endpoint wants the path from the served root, not from this site.
    var relative = decodeURIComponent(new URL(row.rrd, location.href).pathname.replace(/^\//, ''));
    fetch(location.origin + '/__rerun/open?rrd=' + encodeURIComponent(relative), { method: 'POST' })
      .then(function (response) {
        return response.json().then(function (body) { return { ok: response.ok && body.ok, body: body, status: response.status }; },
          function () { return { ok: false, body: {}, status: response.status }; });
      })
      .then(function (result) {
        if (result.ok) setStatus('Opened ' + name + ' in Rerun.');
        else fallback(result.body.error || 'this server cannot launch Rerun (HTTP ' + result.status + ')');
      }, function (error) { fallback(String(error)); });
  }

  // ── tag filters ────────────────────────────────────────────────────────────

  function buildFilters() {
    var bar = $('ds-filters');
    bar.innerHTML = '';
    D.tag_keys.forEach(function (tag) {
      var values = [];
      D.runs.forEach(function (run) {
        if (run.tags[tag] !== undefined && values.indexOf(String(run.tags[tag])) === -1) values.push(String(run.tags[tag]));
      });
      if (values.length < 2 && D.tag_keys.length > 3) return;  // a tag every run shares filters nothing
      var field = make('label', '', bar);
      make('span', 'ds-k', field, tag);
      if (values.length > 40) {
        var input = make('input', '', field);
        input.type = 'text';
        input.placeholder = 'contains…';
        input.oninput = function () {
          if (input.value) S.filters[tag] = { exact: false, value: input.value }; else delete S.filters[tag];
          renderViews();
        };
        return;
      }
      var select = make('select', '', field);
      make('option', '', select, 'all').value = '';
      values.sort(function (a, b) { return a.localeCompare(b, undefined, { numeric: true }); });
      values.forEach(function (value) { make('option', '', select, value).value = value; });
      select.onchange = function () {
        if (select.value) S.filters[tag] = { exact: true, value: select.value }; else delete S.filters[tag];
        renderViews();
      };
    });
  }

  // ── heatmap ────────────────────────────────────────────────────────────────

  function buildHeatControls() {
    var bar = $('ds-heat-controls');
    bar.innerHTML = '';
    var field = make('label', '', bar);
    make('span', 'ds-k', field, 'Metric');
    var select = make('select', '', field);
    METRICS.forEach(function (item) {
      var option = make('option', '', select, item[1]);
      option.value = item[0];
      option.selected = S.metric === item[0];
    });
    select.onchange = function () { S.metric = select.value; renderHeat(); };
  }

  function renderHeat() {
    var pair = selectedPair();
    var rows = orderedRows(rowsOfPair(pair)).filter(function (row) { return !row.error; });
    var holder = $('ds-heat');
    var legend = $('ds-heat-legend');
    if (!rows.length) { holder.innerHTML = '<p class="ds-note">No analysed runs for this pair.</p>'; legend.innerHTML = ''; return; }
    var maximum = 0, worst = null;
    rows.forEach(function (row) {
      D.joint_names.forEach(function (joint) {
        var stats = row.joints && row.joints[joint];
        var value = stats ? stats[S.metric] : null;
        if (value !== null && value !== undefined && Math.abs(value) > maximum) { maximum = Math.abs(value); worst = row.run + '\u0000' + joint; }
      });
    });
    var heads = rows.length <= 40;
    var html = '<div class="ds-heat" style="grid-template-columns:70px repeat(' + rows.length + ',' + (rows.length > 120 ? 8 : rows.length > 60 ? 14 : rows.length > 24 ? 22 : 44) + 'px)">';
    if (heads) {
      html += '<div></div>';
      rows.forEach(function (row) { html += '<div class="ds-colhead" title="' + esc(row.run) + '">' + esc(row.run) + '</div>'; });
    }
    D.joint_names.forEach(function (joint) {
      html += '<div class="ds-rowlabel">' + esc(joint) + '</div>';
      rows.forEach(function (row) {
        var stats = row.joints && row.joints[joint];
        var value = stats ? stats[S.metric] : null;
        if (value === null || value === undefined) { html += '<a class="ds-cell ds-none" href="' + esc(row.report) + '"></a>'; return; }
        var tip = row.run + ' · ' + joint + ' · ' + METRICS.filter(function (item) { return item[0] === S.metric; })[0][1] + ' ' + nice(deg(value)) + '°';
        var isWorst = worst === row.run + '\u0000' + joint && rows.length > 1;
        html += '<a class="ds-cell' + (isWorst ? ' ds-worst' : '') + '" style="--tint:' + tint(value, maximum) + '" href="' +
          esc(row.report) + '" title="' + esc(tip) + '"></a>';
      });
    });
    holder.innerHTML = html + '</div>';
    legend.innerHTML = '<span>0°</span><span class="ds-ramp"></span><span>' + nice(deg(maximum)) + '° · ' +
      esc(pairLabel(pair)) + ' · ' + rows.length + ' runs, ' + (S.order === 'worst' ? 'worst first' : 'as recorded') + '</span>';
  }

  // ── peak-time strip ────────────────────────────────────────────────────────

  function renderPeaks() {
    var pair = selectedPair();
    var rows = orderedRows(rowsOfPair(pair)).filter(function (row) { return !row.error; });
    var holder = $('ds-peaks');
    var keys = $('ds-peak-keys');
    var axis = $('ds-peak-axis');
    keys.innerHTML = '';
    axis.innerHTML = '';
    if (!rows.length) { holder.innerHTML = '<p class="ds-note">No analysed runs for this pair.</p>'; return; }
    var start = Infinity, end = -Infinity;
    rows.forEach(function (row) {
      var span = spanOf[row.run];
      if (span[0] !== null && span[0] < start) start = span[0];
      if (span[1] !== null && span[1] > end) end = span[1];
    });
    var width = end - start > 0 ? end - start : 1;
    D.joint_names.forEach(function (joint, index) {
      keys.insertAdjacentHTML('beforeend', '<span><span class="ds-swatch" style="background:' + PALETTE[index % PALETTE.length] + '"></span>' + esc(joint) + '</span>');
    });
    if (D.has_tcp) keys.insertAdjacentHTML('beforeend', '<span><span class="ds-swatch" style="background:#22211f"></span>TCP</span>');
    var html = '';
    rows.forEach(function (row) {
      html += '<div class="ds-peakrow"><div class="ds-name" title="' + esc(row.run) + '">' + esc(row.run) + '</div><div class="ds-track">';
      function dot(name, time, color, value, unit) {
        if (time === null || time === undefined) return '';
        var left = ((time - start) / width * 100).toFixed(2);
        return '<a class="ds-dot" href="' + esc(row.report) + '" style="left:' + left + '%;background:' + color + '" title="' +
          esc(row.run + ' · ' + name + ' peaks at ' + time.toFixed(2) + ' s · ' + value + ' ' + unit) + '"></a>';
      }
      D.joint_names.forEach(function (joint, index) {
        var stats = row.joints && row.joints[joint];
        if (!stats) return;
        html += dot(joint, row.peak_t && row.peak_t[joint], PALETTE[index % PALETTE.length], nice(deg(stats.max_abs)), '°');
      });
      if (row.tcp) html += dot('TCP', row.tcp_peak_t, '#22211f', nice(mm(row.tcp.max_abs)), 'mm');
      html += '</div></div>';
    });
    holder.innerHTML = html;
    axis.innerHTML = '<div class="ds-peakaxis"><div></div><div><span>' + start.toFixed(1) + ' s</span><span>' +
      ((start + end) / 2).toFixed(1) + ' s</span><span>' + end.toFixed(1) + ' s</span></div></div>';
  }

  // ── ISO 9283 cards ─────────────────────────────────────────────────────────

  function statusText(status) {
    if (status === 'references differ') {
      return 'These runs do not share one reference, so they are not repeats: no accuracy or spread is computed for them.';
    }
    return status;
  }

  function renderIso() {
    var holder = $('ds-iso');
    var shownSeries = visibleSeries();
    var html = '';
    var any = false;
    Object.keys(D.aggregates).forEach(function (group) {
      var cards = D.aggregates[group];
      if (cards.status) {
        any = true;
        html += '<div class="ds-isocard ds-pending"><h3>' + esc(group) + '</h3>' + esc(statusText(cards.status)) + '</div>';
        return;
      }
      Object.keys(cards).forEach(function (series) {
        if (!shownSeries[series]) return;
        any = true;
        var card = cards[series];
        var title = '<h3>' + esc(group) + ' · ' + esc(label(series)) + (card.runs ? ' <span class="ds-mut">' + card.runs.length + ' runs</span>' : '') + '</h3>';
        if (card.status) { html += '<div class="ds-isocard ds-pending">' + title + esc(statusText(card.status)) + '</div>'; return; }
        var body = '<table><thead><tr><th></th><th>AT</th><th>RT</th></tr></thead><tbody>';
        D.joint_names.forEach(function (joint) {
          var accuracy = card.accuracy['positions/' + joint], spread = card.repeatability['positions/' + joint];
          if (!accuracy || !spread) return;
          body += '<tr><td>' + esc(joint) + '</td><td>' + nice(deg(accuracy.max_abs)) + '°</td><td>' + nice(deg(spread.max)) + '°</td></tr>';
        });
        if (card.accuracy.position && card.repeatability.position) {
          body += '<tr><td>TCP</td><td>' + nice(mm(card.accuracy.position.max_abs)) + ' mm</td><td>' + nice(mm(card.repeatability.position.max)) + ' mm</td></tr>';
        }
        html += '<div class="ds-isocard">' + title + body + '</tbody></table></div>';
      });
    });
    holder.innerHTML = html || '<p class="ds-note">Nothing to aggregate.</p>';
    $('ds-iso-note').textContent = any
      ? 'AT is the largest bias of the runs’ mean from the reference; RT the largest spread of the runs around their own mean (mean + 3σ, ISO 9283), both from robot_msgs.compare.aggregate.'
      : '';
  }


  // ── assembly: the runs view (today's index, unchanged) ─────────────────────

  function renderPairViews() { renderAnswer(); renderHeat(); renderPeaks(); }
  function renderViews() { renderAnswer(); renderTable(); renderHeat(); renderPeaks(); }
  function renderAll() { renderViews(); renderIso(); }

  if (D.summary && window.TrajCompare && TrajCompare.renderReportPage) {
    TrajCompare.renderReportPage($('ds-summary'), D.summary);
  }
  if (D.drill_down === 'lazy' && location.protocol === 'file:') {
    var banner = $('ds-banner');
    banner.hidden = false;
    banner.innerHTML = 'Run reports are built the first time you open them. Serve this folder to open them, and to launch Rerun from a row:<code>' +
      esc(D.serve_command) + '</code>';
  }
  buildGlobalControls();
  buildFilters();
  buildHeatControls();
  renderAll();
  $('ds-foot').textContent = 'traj_compare dataset view · rows.json holds every pair, run and statistic in SI units';

  // ══ Dataset → Target levels (docs/NAVIGATION.md Part A) ══════════════════════
  //
  // A line is one measured series of one run ("<run> · <series>"); its kind is real when the series name starts with
  // "real"; its config is the config_by tag (else the series name); configs keep one colour on every level. A line's
  // scalar is robot_msgs.compare's RMS joint error (the worst joint's unless a joint is picked); the drawn series is
  // compare's error target − line, per joint, on the target's display grid.

  var LV = D.levels || { targets: [], configs: [], lines: [] };
  var INK = '#22211f';
  var FAN_TEXT = 'median, IQR, p5–p95 and min–max across its lines at each instant';
  // The torque breakdown (Zach 2026-11-19, torque breakdown in the dataset view: "of the command torque some portion of
  // that is coming from Feedforward, and some portion of that is coming from feedback"). Only lines given one carry
  // line.torque; with none anywhere nothing below draws, and the page is today's. Feedback keeps the run view's fixed
  // orange wherever one colour stands for it; on the target's charts the config colours rule, as on every other chart.
  var HAS_TORQUE = LV.has_torque_breakdown === true;
  var FEEDBACK = '#f97316';
  var SHARE_TEXT = 'FB share = Σ|feedback| / (Σ|feedforward| + Σ|feedback|), the part of the commanded torque the feedback had to supply (0 % = the feedforward model did all of it)';

  // WHY try/catch around every storage access: file:// pages, private windows and blocked site data can throw; the
  // page must work without it (Zach 2026-11-19, traj compare view feedback: every choice remembered, never required).
  var store = {
    get: function (key, fallback) {
      try {
        var value = localStorage.getItem('tc-dataset:' + key);
        return value === null ? fallback : JSON.parse(value);
      } catch (error) { return fallback; }
    },
    set: function (key, value) {
      try { localStorage.setItem('tc-dataset:' + key, JSON.stringify(value)); } catch (error) { /* in-memory state still holds */ }
    },
  };
  function oneOf(value, allowed, fallback) { return allowed.indexOf(value) === -1 ? fallback : value; }
  function within(value, low, high, fallback) {
    return typeof value === 'number' && isFinite(value) ? Math.max(low, Math.min(high, value)) : fallback;
  }

  var V = {
    view: oneOf(store.get('view', 'cards'), ['cards', 'table', 'runs'], 'cards'),
    joint: store.get('joint', ''),  // '' = each line's worst joint
    mode: oneOf(store.get('repeats', 'auto'), ['auto', 'lines', 'bands'], 'auto'),
    n: Math.round(within(store.get('lines-n', 5), 1, 20, 5)),
    smooth: within(store.get('smoothing', 0), 0, 0.95, 0),
    tab: oneOf(store.get('target-tab', 'repeat'), ['repeat', 'history'], 'repeat'),
    groupBy: oneOf(store.get('group-by', 'config'), ['config', 'date', 'kind'], 'config'),
    listWidth: within(store.get('list-width', 300), 180, 640, 300),
    listFolded: store.get('list-folded', false) === true,
    league: null, expanded: {},
    target: null, filter: '', chipOff: {}, unchecked: {}, hover: null, pinned: null,
  };
  if (V.joint && D.joint_names.indexOf(V.joint) === -1) V.joint = '';

  var configOf = {};
  LV.configs.forEach(function (config, index) { config.index = index; configOf[config.name] = config; });
  var BASELINE = LV.configs.length ? LV.configs[0].name : null;
  var targetOf = {};
  LV.targets.forEach(function (target) { target.lines = []; targetOf[target.slug] = target; });
  LV.lines.forEach(function (line) { if (targetOf[line.target]) targetOf[line.target].lines.push(line); });
  var tagsOf = {};
  D.runs.forEach(function (run) { tagsOf[run.name] = run.tags; });
  var LEVEL_TAGS = [LV.target_by, LV.config_by, LV.date_tag];

  // ── statistics of compare's numbers (display summaries, never a new metric) ──

  function byNumber(a, b) { return a - b; }
  function present(values) { return values.filter(function (value) { return value !== null && value !== undefined && isFinite(value); }); }
  function quantile(sorted, p) {
    if (!sorted.length) return null;
    var position = (sorted.length - 1) * p, low = Math.floor(position), high = Math.ceil(position);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  }
  function median(values) { return quantile(present(values).sort(byNumber), 0.5); }
  function mean(values) {
    var kept = present(values);
    return kept.length ? kept.reduce(function (a, b) { return a + b; }, 0) / kept.length : null;
  }
  // Per-instant percentiles across lines on one grid (the fan).
  function bandOf(arrays) {
    var n = arrays.length ? arrays[0].length : 0;
    var keys = ['min', 'p5', 'p25', 'p50', 'p75', 'p95', 'max'];
    var out = {};
    keys.forEach(function (key) { out[key] = new Array(n); });
    var column = [];
    for (var i = 0; i < n; i++) {
      column.length = 0;
      for (var k = 0; k < arrays.length; k++) {
        var value = arrays[k][i];
        if (value !== null && value !== undefined) column.push(value);
      }
      if (!column.length) { keys.forEach(function (key) { out[key][i] = null; }); continue; }
      column.sort(byNumber);
      out.min[i] = column[0]; out.max[i] = column[column.length - 1];
      out.p5[i] = quantile(column, 0.05); out.p25[i] = quantile(column, 0.25); out.p50[i] = quantile(column, 0.5);
      out.p75[i] = quantile(column, 0.75); out.p95[i] = quantile(column, 0.95);
    }
    return out;
  }
  // TensorBoard's debiased exponential moving average, per line before the fan is taken.
  function smoothed(values, weight) {
    if (!weight || !values) return values;
    var last = 0, count = 0;
    return values.map(function (value) {
      if (value === null || value === undefined) return null;
      last = last * weight + (1 - weight) * value;
      count += 1;
      return last / (1 - Math.pow(weight, count));
    });
  }
  // SPC individuals chart (I-MR): centre = mean, limits = mean ± 2.66 · mean moving range.
  function controlLimits(values) {
    var kept = present(values);
    if (kept.length < 2) return null;
    var centre = mean(kept), range = 0;
    for (var i = 1; i < kept.length; i++) range += Math.abs(kept[i] - kept[i - 1]);
    range /= kept.length - 1;
    return { mean: centre, ucl: centre + 2.66 * range, lcl: Math.max(0, centre - 2.66 * range) };
  }
  function niceStep(x) {
    var power = Math.pow(10, Math.floor(Math.log10(x || 1))), m = x / power;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * power;
  }

  // ── formatting ──

  function fmtDeg(rad) { return rad === null || rad === undefined ? '—' : nice(rad * DEG) + '°'; }
  function fmtShare(x) {
    if (x === null || x === undefined) return '—';
    var pct = 100 * x;
    return (pct < 10 ? pct.toFixed(1) : pct.toFixed(0)) + '%';
  }
  function fmtNm(x) { return x === null || x === undefined ? '—' : nice(x) + ' N·m'; }
  function signedPct(x) { return (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(100 * x).toFixed(0) + '%'; }
  function shortDate(text) { return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(5, 10) : text; }
  function dateRange(dates) {
    if (!dates.length) return '';
    var first = dates[0], last = dates[dates.length - 1];
    if (first === last) return esc(first);
    var sameYear = /^\d{4}-/.test(first) && first.slice(0, 5) === last.slice(0, 5);
    return esc(first) + ' → ' + esc(sameYear ? shortDate(last) : last);
  }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  function hexA(hex, alpha) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }
  // One shade per line of a config, so a few lines stay individually distinguishable.
  function shade(hex, index, count) {
    var n = parseInt(hex.slice(1), 16), t = count <= 1 ? 0 : (index / (count - 1)) * 0.55 - 0.25;
    return '#' + [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (v) {
      var mixed = Math.round(t < 0 ? v * (1 + t) : v + (255 - v) * t);
      return (mixed < 16 ? '0' : '') + mixed.toString(16);
    }).join('');
  }
  function colorOf(config) { return configOf[config] ? configOf[config].color : '#52514e'; }
  function swatch(color, sim) {
    return '<span class="ds-sw' + (sim ? ' ds-sw-sim' : '') + '" style="--c:' + color + '"></span>';
  }
  function unique(values) {
    var seen = {}, out = [];
    values.forEach(function (value) { if (!seen[value]) { seen[value] = true; out.push(value); } });
    return out;
  }
  function kindCounts(lines) {
    var counts = { sim: 0, real: 0 };
    lines.forEach(function (line) { counts[line.kind] += 1; });
    return counts;
  }

  // ── lines, configs, verdicts ──

  function valueOf(line, joint) {
    if (line.error) return null;
    var value = joint ? (line.rms ? line.rms[joint] : null) : line.worst_rms;
    return value === undefined ? null : value;
  }
  function jointWords(joint) { return joint ? joint : 'worst joint'; }
  // WHY real lines only (dispatcher's rule, 2026-11-19): repeatability is "same everything, run again", so a config's fan
  // covers its real lines and its sim line(s) draw dashed over it, never pooled into it. A config with no real line on a
  // target is drawn from its sims.
  function membersOf(lines) {
    var real = lines.filter(function (line) { return line.kind === 'real'; });
    if (!real.length) return { members: lines, sims: [], kind: 'sim' };
    return { members: real, sims: lines.filter(function (line) { return line.kind !== 'real'; }), kind: 'real' };
  }
  function configGroups(lines) {
    var groups = [];
    LV.configs.forEach(function (config) {
      var own = lines.filter(function (line) { return line.config === config.name && !line.error; });
      if (!own.length) return;
      var split = membersOf(own);
      groups.push({ config: config, lines: own, members: split.members, sims: split.sims, kind: split.kind });
    });
    return groups;
  }
  // Auto: lines while a config has ≤ N lines, else a fan; Bands forces a fan from 2 lines; Lines forces lines.
  function drawMode(count) {
    if (V.mode === 'lines') return 'lines';
    if (V.mode === 'bands') return count >= 2 ? 'bands' : 'lines';
    return count <= V.n ? 'lines' : 'bands';
  }
  function worstJoint(target) {
    var members = membersOf(target.lines.filter(function (line) { return !line.error; })).members;
    var best = target.joints[0], bestValue = -1;
    target.joints.forEach(function (joint) {
      var value = median(members.map(function (line) { return line.rms ? line.rms[joint] : null; }));
      if (value !== null && value > bestValue) { bestValue = value; best = joint; }
    });
    return best;
  }
  // Which config tracks better: medians of the lines' RMS error (real lines when the target has any), the best config
  // against the baseline (the first config) or, when the baseline is best, against the runner-up; the confidence is the
  // share of (winner, other) line pairs in which the winner's line had the lower error (probability of superiority).
  function verdictOf(lines, joint) {
    var usable = lines.filter(function (line) { return valueOf(line, joint) !== null; });
    var kind = usable.some(function (line) { return line.kind === 'real'; }) ? 'real' : 'sim';
    var groups = [];
    LV.configs.forEach(function (config) {
      var own = usable.filter(function (line) { return line.config === config.name && line.kind === kind; });
      if (!own.length) return;
      var values = own.map(function (line) { return valueOf(line, joint); });
      groups.push({ config: config, lines: own, values: values, median: median(values) });
    });
    var result = { kind: kind, groups: groups, joint: joint };
    if (groups.length < 2) { result.single = groups[0] || null; return result; }
    var lowest = function (best, group) { return group.median < best.median ? group : best; };
    var winner = groups.reduce(lowest);
    var base = groups.filter(function (group) { return group.config.name === BASELINE; })[0];
    var other = base && base !== winner ? base : groups.filter(function (group) { return group !== winner; }).reduce(lowest);
    var wins = 0, pairs = 0;
    winner.values.forEach(function (a) {
      other.values.forEach(function (b) { pairs += 1; wins += a < b ? 1 : a === b ? 0.5 : 0; });
    });
    var share = pairs ? wins / pairs : 0.5;
    result.winner = winner; result.other = other; result.wins = wins; result.pairs = pairs; result.share = share;
    result.delta = other.median > 0 ? (winner.median - other.median) / other.median : 0;
    // WHY "low" under 4 pairs: one line against one or two is a coin toss however far apart they sit.
    result.conf = pairs < 4 ? 'low' : share >= 0.9 ? 'high' : share >= 0.75 ? 'moderate' : 'low';
    return result;
  }
  function verdictHtml(v, short) {
    var basis = '<span class="ds-mut">' + v.kind + ' lines · RMS error, ' + esc(jointWords(v.joint)) + '</span>';
    if (!v.groups.length) return '<span class="ds-mut">No analysed lines here.</span>';
    if (v.single) {
      var only = v.single;
      return swatch(only.config.color) + '<b>Nothing to compare</b>: only ' + esc(only.config.name) + ' has ' + v.kind +
        ' lines · median ' + fmtDeg(only.median) + ' over ' + plural(only.lines.length, 'line') + (short ? '' : ' · ' + basis);
    }
    if (v.winner.median === v.other.median) {
      return '<b>No difference</b>: ' + esc(v.winner.config.name) + ' and ' + esc(v.other.config.name) + ' share a median of ' +
        fmtDeg(v.winner.median) + (short ? '' : ' · ' + basis);
    }
    var conf = '<span class="ds-conf ds-conf-' + v.conf + '" title="Lower in ' + Math.round(v.wins) + ' of ' + v.pairs +
      ' line pairs (' + esc(v.winner.config.name) + ' × ' + esc(v.other.config.name) + '), n ' + v.winner.lines.length + ' vs ' +
      v.other.lines.length + '">' + v.conf + ' confidence · ' + Math.round(v.wins) + ' of ' + v.pairs + ' line pairs</span>';
    return swatch(v.winner.config.color) + '<b>' + esc(v.winner.config.name) + '</b> tracks better than ' + esc(v.other.config.name) +
      ': <b>' + signedPct(v.delta) + '</b> RMS error <span class="ds-num">(' + fmtDeg(v.other.median) + ' → ' + fmtDeg(v.winner.median) +
      ' median)</span> ' + conf + (short ? '' : ' · ' + basis);
  }

  // ── uPlot fan / lines chart (2026-11-19 summary prototypes' shared/common.js, ported) ──

  var charts = { cards: [], table: [], repeat: [] };
  function destroyCharts(scope) {
    charts[scope].forEach(function (chart) { if (chart._ro) chart._ro.disconnect(); chart.destroy(); });
    charts[scope] = [];
  }
  // layers: [{config, color, mode: 'lines' | 'bands', dash, lines: [{line, y}]}]; overlay: [{line, y}] drawn in ink.
  function fanChart(host, options) {
    host.innerHTML = '';
    if (!window.uPlot) return null;
    var x = options.x;
    var data = [x], series = [{}], bands = [], meta = [null];
    function add(values, style, info) {
      var item = { points: { show: false }, spanGaps: false };
      Object.keys(style).forEach(function (key) { if (style[key] !== undefined) item[key] = style[key]; });
      data.push(values); series.push(item); meta.push(info);
      return data.length - 1;
    }
    options.layers.forEach(function (layer) {
      if (!layer.lines.length) return;
      var dash = layer.dash ? [5, 4] : undefined;
      if (layer.mode === 'bands') {
        var fan = bandOf(layer.lines.map(function (item) { return item.y; }));
        var thin = { stroke: 'transparent', width: 0 };
        var top = add(fan.max, thin, null), bottom = add(fan.min, thin, null);
        var p95 = add(fan.p95, thin, null), p5 = add(fan.p5, thin, null);
        var p75 = add(fan.p75, thin, null), p25 = add(fan.p25, thin, null);
        add(fan.p50, { stroke: layer.color, width: 1.8, dash: dash }, { layer: layer, role: 'median' });
        bands.push({ series: [top, bottom], fill: hexA(layer.color, 0.09) }, { series: [p95, p5], fill: hexA(layer.color, 0.14) },
          { series: [p75, p25], fill: hexA(layer.color, 0.26) });
      } else {
        layer.lines.forEach(function (item, index) {
          add(item.y, { stroke: layer.dash ? layer.color : shade(layer.color, index, layer.lines.length), width: layer.dash ? 1.3 : 1.25, dash: dash },
            { layer: layer, role: 'line', line: item.line });
        });
      }
    });
    (options.overlay || []).forEach(function (item) { add(item.y, { stroke: INK, width: 2 }, { role: 'overlay', line: item.line }); });
    var font = '10.5px -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif';
    var axis = { stroke: '#8a8983', font: font, grid: { stroke: '#efeee9', width: 1 }, ticks: { stroke: '#e6e5e0', width: 1, size: 4 } };
    function decimals(step) {
      var digits = 0;
      while (digits < 4 && Math.abs(Math.round(step * Math.pow(10, digits)) - step * Math.pow(10, digits)) > 1e-6) digits++;
      return digits;
    }
    // Nearest drawn line at this instant, a fan's own lines included: clicking a line or a band opens that run.
    function nearest(u, index) {
      var top = u.cursor.top;
      if (top === null || top === undefined || top < 0) return null;
      var value = u.posToVal(top, 'y'), best = null;
      options.layers.forEach(function (layer) {
        layer.lines.forEach(function (item) {
          var y = item.y[index];
          if (y === null || y === undefined) return;
          var distance = Math.abs(y - value);
          if (!best || distance < best.distance) best = { distance: distance, line: item.line, y: y };
        });
      });
      return best;
    }
    // unit follows every readout value; tickUnit (default: unit) each y tick, so a long unit (N·m) can stay in the title.
    var unit = options.unit || '';
    var tickUnit = options.tickUnit === undefined ? unit : options.tickUnit;
    var digits = options.digits === undefined ? 3 : options.digits;
    var opts = {
      width: Math.max(160, host.clientWidth), height: options.height || 200, legend: { show: false },
      cursor: { drag: { x: true, y: false }, points: { show: false } },
      scales: { x: { time: false }, y: { auto: true } },
      axes: [
        Object.assign({}, axis, { size: 26, values: function (u, values) { return values.map(function (v) { return v + ' s'; }); } }),
        Object.assign({}, axis, { size: 50, values: function (u, values, i, space, step) {
          var places = decimals(step || 1);
          return values.map(function (v) { return v.toFixed(places) + tickUnit; });
        } }),
      ],
      series: series, bands: bands,
      hooks: {
        setCursor: [function (u) {
          if (!options.readout) return;
          var index = u.cursor.idx;
          if (index === null || index === undefined) { options.readout.innerHTML = '&nbsp;'; return; }
          var parts = ['t ' + x[index].toFixed(2) + ' s'];
          meta.forEach(function (info, k) {
            if (info && info.role === 'median' && data[k][index] !== null && data[k][index] !== undefined) {
              parts.push('<span style="color:' + info.layer.color + '">■</span> ' + esc(info.layer.config) + ' median <b>' + data[k][index].toFixed(digits) + unit + '</b>');
            }
          });
          var near = nearest(u, index);
          if (near) parts.push('nearest <b>' + esc(near.line.id) + '</b> ' + near.y.toFixed(digits) + unit);
          options.readout.innerHTML = parts.join(' · ');
        }],
        draw: [function (u) {
          var zero = u.valToPos(0, 'y', true);
          if (zero < u.bbox.top || zero > u.bbox.top + u.bbox.height) return;
          var ctx = u.ctx;
          ctx.save(); ctx.strokeStyle = '#cfcec8'; ctx.lineWidth = 1; ctx.beginPath();
          ctx.moveTo(u.bbox.left, zero); ctx.lineTo(u.bbox.left + u.bbox.width, zero); ctx.stroke(); ctx.restore();
        }],
      },
    };
    var chart = new uPlot(opts, data, host);
    chart.over.style.cursor = options.onPick ? 'pointer' : 'crosshair';
    if (options.onPick) {
      var down = null;
      chart.over.addEventListener('mousedown', function (event) { down = [event.clientX, event.clientY]; });
      chart.over.addEventListener('click', function (event) {
        if (down && Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 4) return;  // a drag-zoom, not a pick
        var index = chart.cursor.idx;
        if (index === null || index === undefined) return;
        var hit = nearest(chart, index);
        if (hit) options.onPick(hit.line);
      });
    }
    chart.over.addEventListener('dblclick', function () { chart.setScale('x', { min: x[0], max: x[x.length - 1] }); });
    var observer = new ResizeObserver(function () {
      var width = Math.max(160, host.clientWidth);
      if (host.clientWidth > 0 && Math.abs(width - chart.width) > 1) chart.setSize({ width: width, height: opts.height });
    });
    observer.observe(host);
    chart._ro = observer;
    return chart;
  }

  // A line's drawn series for one joint: its joint error (°, the default), its feedback torque (N·m) or its FB share (%).
  function errorSeries(line, jointIndex) { return line.e_deg[jointIndex]; }
  function feedbackSeries(line, jointIndex) {
    return line.torque && line.torque.tau_fb ? line.torque.tau_fb[jointIndex] : null;
  }
  function shareSeries(line, jointIndex) {
    var values = line.torque && line.torque.fb_share_over_time ? line.torque.fb_share_over_time[jointIndex] : null;
    return values ? values.map(function (value) { return value === null || value === undefined ? null : 100 * value; }) : null;
  }
  // The lines a torque number is taken over: those with a breakdown, the real ones when any has one (as the band's RMS).
  function torqueMembers(lines) {
    var having = lines.filter(function (line) { return line.torque && !line.error; });
    var real = having.filter(function (line) { return line.kind === 'real'; });
    return real.length ? real : having;
  }
  function shareOf(line, joint) {
    if (!line.torque) return null;
    var value = joint ? (line.torque.joints[joint] || {}).fb_share : line.torque.fb_share;
    return value === undefined ? null : value;
  }
  // The drive gap (RMS of commanded − applied) of the picked joint, else the line's largest over its joints.
  function gapOf(line, joint) {
    if (!line.torque) return null;
    var joints = line.torque.joints || {}, worst = null;
    if (joint) return joints[joint] && joints[joint].drive_gap_rms !== undefined ? joints[joint].drive_gap_rms : null;
    Object.keys(joints).forEach(function (key) {
      var value = joints[key].drive_gap_rms;
      if (value !== null && value !== undefined && (worst === null || value > worst)) worst = value;
    });
    return worst;
  }

  // The layers one joint's chart draws for these lines, and what each config draws (the [data-tc-draw] statements).
  function layersFor(lines, jointIndex, valuesOf) {
    var layers = [], draws = [];
    var pick = valuesOf || errorSeries;
    function series(line) { return { line: line, y: smoothed(pick(line, jointIndex), V.smooth) }; }
    configGroups(lines).forEach(function (group) {
      var mode = drawMode(group.members.length);
      layers.push({ config: group.config.name, color: group.config.color, mode: mode, dash: group.kind === 'sim', lines: group.members.map(series) });
      if (group.sims.length) {
        layers.push({ config: group.config.name, color: group.config.color, mode: 'lines', dash: true, lines: group.sims.map(series) });
      }
      draws.push({ group: group, mode: mode });
    });
    return { layers: layers, draws: draws };
  }
  function drawChips(draws) {
    return draws.map(function (item) {
      var group = item.group, fan = item.mode === 'bands';
      var what = plural(group.members.length, group.kind + ' line') + ' as ' + (fan ? 'a fan' : 'lines') +
        (group.sims.length ? ' + ' + group.sims.length + ' sim dashed' : '');
      var title = group.config.name + ': ' + what + (fan ? ' (' + FAN_TEXT + ')' : '') +
        (group.sims.length ? '; sim lines draw dashed over it, never pooled into it' : '');
      return '<span class="ds-chip" data-tc-draw data-config="' + esc(group.config.name) + '" data-draw="' + item.mode + '" title="' +
        esc(title) + '">' + swatch(group.config.color, group.kind === 'sim') + esc(group.config.name) + ' <span class="ds-mut">' + esc(what) + '</span></span>';
    }).join('');
  }
  function openLine(line) { if (line && line.report) location.href = line.report; }

  // ── Dataset level: the summary band ──

  function renderBand() {
    var lines = LV.lines;
    var counts = kindCounts(lines);
    var dates = unique(lines.map(function (line) { return line.date; }).filter(Boolean)).sort();
    var html = '<h2>How is tracking across every target, per config?</h2><p class="ds-band-answer"><b>' + plural(LV.targets.length, 'target') +
      '</b> · <b>' + plural(lines.length, 'line') + '</b> (' + counts.sim + ' sim · ' + counts.real + ' real) · <b>' +
      plural(LV.configs.length, 'config') + '</b>' + (dates.length ? ' · ' + dateRange(dates) : '') + '</p>';
    var tolerances = lines.some(function (line) { return line.ok === true || line.ok === false; });
    html += '<table class="ds-band-table"><thead><tr><th>Config</th><th>Lines</th><th>Median RMS error <span class="ds-unit">' +
      esc(jointWords(V.joint)) + '</span></th>' +
      (HAS_TORQUE ? '<th title="' + esc(SHARE_TEXT) + '"><span class="ds-fbmark"></span>Median FB share <span class="ds-unit">all joints</span></th>' : '') +
      (tolerances ? '<th>Pass</th>' : '') + '<th>Against the baseline</th></tr></thead><tbody>';
    var verdicts = LV.targets.map(function (target) { return verdictOf(target.lines, V.joint); });
    LV.configs.forEach(function (config) {
      var own = lines.filter(function (line) { return line.config === config.name; });
      var split = membersOf(own.filter(function (line) { return !line.error; }));
      var middle = median(split.members.map(function (line) { return valueOf(line, V.joint); }));
      var judged = own.filter(function (line) { return line.ok === true || line.ok === false; });
      var passed = judged.filter(function (line) { return line.ok; }).length;
      var against = '<span class="ds-mut">baseline</span>';
      if (config.name !== BASELINE) {
        var wins = 0, shared = 0;
        verdicts.forEach(function (v) {
          var mine = v.groups.filter(function (group) { return group.config.name === config.name; })[0];
          var base = v.groups.filter(function (group) { return group.config.name === BASELINE; })[0];
          if (!mine || !base) return;
          shared += 1;
          if (mine.median < base.median) wins += 1;
        });
        against = shared ? 'better than ' + esc(BASELINE) + ' on <b>' + wins + ' of ' + plural(shared, 'target') + '</b>'
          : '<span class="ds-mut">no target shared with ' + esc(BASELINE) + '</span>';
      }
      var share = '';
      if (HAS_TORQUE) {
        // WHY the payload's median, not one taken here: the band's FB share is dataset.py's (robot_msgs.compare's median).
        var withTorque = torqueMembers(own);
        share = config.fb_share_median === null || config.fb_share_median === undefined
          ? '<td data-tc-fb-share="' + esc(config.name) + '"><span class="ds-mut" title="no line of this config has a torque breakdown">—</span></td>'
          : '<td data-tc-fb-share="' + esc(config.name) + '"><b>' + fmtShare(config.fb_share_median) + '</b> <span class="ds-mut">' +
            plural(withTorque.length, withTorque.length && withTorque[0].kind === 'real' ? 'real line' : 'sim line') + '</span></td>';
      }
      html += '<tr><td class="ds-text">' + swatch(config.color, !config.real) + esc(config.name) + '</td><td>' + own.length +
        ' <span class="ds-mut">(' + config.sim + ' sim · ' + config.real + ' real)</span></td><td><b>' + fmtDeg(middle) +
        '</b> <span class="ds-mut">' + split.kind + ' lines</span></td>' + share +
        (tolerances ? '<td>' + (judged.length ? passed + '/' + judged.length : '—') + '</td>' : '') + '<td class="ds-text">' + against + '</td></tr>';
    });
    html += '</tbody></table><p class="ds-note">A line is one measured series of one run. Its RMS error is robot_msgs.compare’s, of the ' +
      esc(jointWords(V.joint)) + '; a config’s median is over its real lines (its sims when it has none), and “better” compares those medians on each target both configs ran.' +
      (HAS_TORQUE ? ' ' + esc(SHARE_TEXT) + ', over every joint and sample of a line; its median is over the config’s lines with a torque breakdown (real ones when it has any), “—” where none has one.' : '') + '</p>';
    $('ds-band').innerHTML = html;
  }

  // ── Dataset level: controls, cards, league table ──

  function jointSelect(id) {
    return '<label class="ds-ctl"><span class="ds-k">Joint</span><select id="' + id + '"><option value="">worst joint</option>' +
      D.joint_names.map(function (joint) {
        return '<option value="' + esc(joint) + '"' + (V.joint === joint ? ' selected' : '') + '>' + esc(joint) + '</option>';
      }).join('') + '</select></label>';
  }
  function setJoint(joint) {
    V.joint = joint;
    store.set('joint', joint);
  }
  function renderDatasetControls() {
    var bar = $('ds-dataset-controls');
    if (V.view === 'runs') { bar.innerHTML = ''; return; }
    bar.innerHTML = jointSelect('ds-joint-dataset') + '<span class="ds-hint">Charts draw lines while a config has ≤ ' + V.n +
      ' lines, a fan past that (set on a target’s page) · click a line or a dot to open its run</span>';
    $('ds-joint-dataset').onchange = function (event) { setJoint(event.target.value); renderBand(); showView(); };
  }

  function stripHtml(target, joint, groups) {
    var values = [];
    groups.forEach(function (group) { group.lines.forEach(function (line) { values.push(valueOf(line, joint)); }); });
    values = present(values);
    if (!values.length) return '';
    var high = Math.max.apply(null, values) * DEG * 1.08 || 1;
    var step = niceStep(high / 4);
    var left = function (rad) { return (rad * DEG / high * 100).toFixed(2); };
    var html = '<div class="ds-strip">';
    groups.forEach(function (group) {
      html += '<div class="ds-strip-row"><span class="ds-strip-label" title="' + esc(group.config.name) + '">' + esc(group.config.name) +
        '</span><div class="ds-strip-track">';
      var middle = group.members.length > 1 ? median(group.members.map(function (line) { return valueOf(line, joint); })) : null;
      if (middle !== null) html += '<span class="ds-strip-median" style="left:' + left(middle) + '%" title="median of the ' + group.kind + ' lines ' + fmtDeg(middle) + '"></span>';
      group.lines.forEach(function (line) {
        var value = valueOf(line, joint);
        if (value === null) return;
        html += '<a class="ds-sdot' + (line.kind === 'sim' ? ' ds-sdot-sim' : '') + '" href="' + esc(line.report) + '" style="left:' + left(value) +
          '%;--c:' + group.config.color + '" title="' + esc(line.id + ' · ' + line.kind + (line.date ? ' · ' + line.date : '') + ' · RMS ' + fmtDeg(value)) + '"></a>';
      });
      html += '</div></div>';
    });
    html += '<div class="ds-strip-axis"><span></span><div>';
    for (var v = 0; v <= high + 1e-9; v += step) html += '<span style="left:' + (v / high * 100).toFixed(2) + '%">' + +v.toFixed(3) + '°</span>';
    return html + '</div></div></div>';
  }

  function renderCards() {
    destroyCharts('cards');
    var holder = $('ds-view-cards');
    holder.innerHTML = '';
    var grid = make('div', 'ds-cards', holder);
    var todo = [];
    LV.targets.forEach(function (target) {
      var joint = V.joint || worstJoint(target);
      var jointIndex = target.joints.indexOf(joint);
      var counts = kindCounts(target.lines);
      var groups = configGroups(target.lines);
      var card = make('article', 'ds-tcard', grid);
      card.setAttribute('data-tc-target-card', target.slug);
      var drawn = jointIndex === -1 ? { layers: [], draws: [] } : layersFor(target.lines, jointIndex);
      card.innerHTML =
        '<div class="ds-tcard-head"><h3>' + esc(target.title) + '</h3>' +
        (target.key !== target.title ? '<span class="ds-key" title="target key">' + esc(target.key) + '</span>' : '') +
        '<span class="ds-count">' + plural(target.lines.length, 'line') + ' · ' + counts.sim + ' sim · ' + counts.real + ' real</span></div>' +
        '<div class="ds-tcard-verdict">' + verdictHtml(verdictOf(target.lines, V.joint), true) + '</div>' +
        '<div class="ds-csec">' + esc(joint) + ': joint error, target − line [°]</div>' +
        '<div class="ds-chips">' + drawChips(drawn.draws) + '</div><div class="ds-plot"></div><div class="ds-readout">&nbsp;</div>' +
        '<div class="ds-csec">RMS error per line, ' + esc(jointWords(V.joint)) + ' [°] <span class="ds-mut">◇ sim · ● real</span></div>' +
        stripHtml(target, V.joint, groups) +
        '<div class="ds-tcard-foot"><a class="ds-btn ds-primary" href="#/target/' + encodeURIComponent(target.slug) + '">Open target</a>' +
        '<span class="ds-mut">' + plural(target.runs, 'run') + '</span></div>';
      var host = card.querySelector('.ds-plot'), readout = card.querySelector('.ds-readout');
      todo.push(function () {
        var chart = fanChart(host, { x: target.t, layers: drawn.layers, height: 190, unit: '°', readout: readout, onPick: openLine });
        if (chart) charts.cards.push(chart);
      });
    });
    requestAnimationFrame(function () { todo.forEach(function (draw) { draw(); }); });
  }

  function repeatabilityOf(target, config, joint) {
    var spread = target.repeatability && target.repeatability[config];
    if (!spread || !spread.joints) return { value: null, title: spread ? spread.status : 'not computed' };
    var name = joint, value = joint ? spread.joints[joint] : null;
    if (!joint) {
      Object.keys(spread.joints).forEach(function (key) {
        if (spread.joints[key] !== null && (value === null || spread.joints[key] > value)) { value = spread.joints[key]; name = key; }
      });
    }
    return { value: value, joint: name, tcp: spread.tcp, n: spread.n,
      title: 'ISO 9283 path repeatability RT of ' + spread.n + ' lines (robot_msgs.compare.aggregate: mean + 3σ spread around their own mean, worst over the path), ' + name };
  }
  function sparkSvg(lines, jointIndex, color, range) {
    var width = 120, height = 24, low = range[0], high = range[1];
    var arrays = lines.map(function (line) { return line.e_deg[jointIndex]; });
    if (!arrays.length) return '';
    var fan = bandOf(arrays);
    function path(values) {
      var d = '', pen = false;
      values.forEach(function (value, i) {
        if (value === null || value === undefined) { pen = false; return; }
        d += (pen ? 'L' : 'M') + (i / Math.max(1, values.length - 1) * width).toFixed(1) + ' ' + (height - (value - low) / (high - low || 1) * height).toFixed(1);
        pen = true;
      });
      return d;
    }
    var svg = '<svg class="ds-spark" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">';
    if (low < 0 && high > 0) {
      var zero = (height - (0 - low) / (high - low) * height).toFixed(1);
      svg += '<line x1="0" x2="' + width + '" y1="' + zero + '" y2="' + zero + '" stroke="#e6e5e0"/>';
    }
    if (arrays.length >= 3) {
      var upper = path(fan.p75), lower = path(fan.p25.slice().reverse());
      if (upper && lower) svg += '<path d="' + upper + 'L' + lower.slice(1) + 'Z" fill="' + hexA(color, 0.25) + '" stroke="none"/>';
    }
    return svg + '<path d="' + path(fan.p50) + '" fill="none" stroke="' + color + '" stroke-width="1.3"/></svg>';
  }
  function leagueRows() {
    var rows = [];
    LV.targets.forEach(function (target) {
      var joint = V.joint || worstJoint(target);
      var jointIndex = target.joints.indexOf(joint);
      var groups = configGroups(target.lines);
      var base = groups.filter(function (group) { return group.config.name === BASELINE; })[0];
      var baseMedian = base ? median(base.members.map(function (line) { return valueOf(line, V.joint); })) : null;
      var low = 0, high = 0;
      groups.forEach(function (group) {
        group.members.forEach(function (line) {
          (line.e_deg[jointIndex] || []).forEach(function (value) {
            if (value !== null) { low = Math.min(low, value); high = Math.max(high, value); }
          });
        });
      });
      groups.forEach(function (group) {
        var values = present(group.members.map(function (line) { return valueOf(line, V.joint); }));
        var middle = median(values);
        var judged = group.lines.filter(function (line) { return line.ok === true || line.ok === false; });
        var torqued = torqueMembers(group.lines);
        rows.push({
          target: target, group: group, values: values, median: middle, joint: joint, jointIndex: jointIndex, range: [low, high],
          delta: group === base ? 'baseline' : base && base.kind === group.kind && baseMedian ? (middle - baseMedian) / baseMedian : null,
          spread: repeatabilityOf(target, group.config.name, V.joint),
          pass: judged.length ? judged.filter(function (line) { return line.ok; }).length / judged.length : null, judged: judged.length,
          // medians over the row's lines that have a breakdown; null (the cell says "—") when none has one
          torqued: torqued,
          fb: median(torqued.map(function (line) { return shareOf(line, V.joint); })),
          gap: median(torqued.map(function (line) { return gapOf(line, V.joint); })),
        });
      });
    });
    return rows;
  }
  var LEAGUE_SORTS = {
    config: function (row) { return row.group.config.index; },
    n: function (row) { return -row.group.lines.length; },
    median: function (row) { return row.median === null ? Infinity : row.median; },
    delta: function (row) { return typeof row.delta === 'number' ? row.delta : row.delta === 'baseline' ? 0 : Infinity; },
    rt: function (row) { return row.spread.value === null ? Infinity : row.spread.value; },
    pass: function (row) { return row.pass === null ? Infinity : -row.pass; },
    fb: function (row) { return row.fb === null ? Infinity : row.fb; },
    gap: function (row) { return row.gap === null ? Infinity : row.gap; },
  };
  function renderLeague() {
    var holder = $('ds-view-table');
    var rows = leagueRows();
    var tolerances = rows.some(function (row) { return row.judged > 0; });
    var sorted = V.league && LEAGUE_SORTS[V.league.key];
    // WHY a scale per target while grouped (2026-11-19 summary V2): targets differ by 10x in error, and one shared axis
    // squeezed the slow probe's dots into a corner; a sorted league compares across targets, so it shares one axis.
    function scaleOf(subset) {
      var top = 0;
      subset.forEach(function (row) { row.values.forEach(function (value) { top = Math.max(top, value * DEG); }); });
      top = top * 1.08 || 1;
      return { high: top, step: niceStep(top / 4) };
    }
    function axisHtml(scale) {
      var out = '<span class="ds-axis">';
      for (var v = 0; v <= scale.high + 1e-9; v += scale.step) out += '<span style="left:' + (v / scale.high * 100).toFixed(2) + '%">' + +v.toFixed(3) + '°</span>';
      return out + '</span>';
    }
    var shared = scaleOf(rows), scales = {};
    LV.targets.forEach(function (target) { scales[target.slug] = scaleOf(rows.filter(function (row) { return row.target === target; })); });
    if (sorted) {
      rows.sort(function (a, b) {
        return (LEAGUE_SORTS[V.league.key](a) - LEAGUE_SORTS[V.league.key](b)) * V.league.dir || a.target.index - b.target.index;
      });
    }
    var columns = [
      ['target', 'Target · config'], ['n', 'Lines'], ['dist', 'RMS error per line'], ['median', 'Median'], ['delta', 'Δ vs ' + (BASELINE || 'baseline')],
    ];
    if (HAS_TORQUE) columns.push(['fb', 'FB share'], ['gap', 'Drive gap']);  // NAVIGATION.md's order: after Δ, before RT
    if (tolerances) columns.push(['pass', 'Pass']);
    columns.push(['rt', 'ISO 9283 RT'], ['spark', 'Error over time'], ['open', '']);
    var html = '<div class="ds-scroll ds-league-wrap"><table class="ds-league"><thead><tr>';
    columns.forEach(function (column) {
      var key = column[0], sortable = key === 'target' || LEAGUE_SORTS[key] || key === 'dist';
      var sortKey = key === 'dist' ? 'median' : key;
      var active = key === 'target' ? !V.league : V.league && V.league.key === sortKey && key !== 'dist';
      var tip = key === 'fb' ? SHARE_TEXT + '; median over the row’s lines with a torque breakdown, ' + (V.joint || 'all joints')
        : key === 'gap' ? 'Drive gap = RMS of commanded − applied torque (robot_msgs.compare), what the drive fell short of the command by ' +
          '(saturation, current-loop lag, kt error); median over the row’s lines with a torque breakdown, ' + (V.joint || 'each line’s largest joint') : '';
      html += '<th data-sort-key="' + (sortable ? sortKey : '') + '" class="' + (sortable ? 'sortable' : '') + (active ? ' sorted' : '') + '"' +
        (tip ? ' title="' + esc(tip) + '"' : '') + '>' + (key === 'fb' ? '<span class="ds-fbmark"></span>' : '') + esc(column[1]);
      if (key === 'dist' && sorted) html += axisHtml(shared);
      if (active && key !== 'target') html += V.league.dir > 0 ? ' ↑' : ' ↓';
      html += '</th>';
    });
    html += '</tr></thead><tbody>';
    var lastTarget = null;
    rows.forEach(function (row) {
      var target = row.target, group = row.group;
      if (!sorted && target !== lastTarget) {
        lastTarget = target;
        html += '<tr class="ds-lg-head"><th colspan="2"><a class="ds-lg-title" href="#/target/' + encodeURIComponent(target.slug) + '">' + esc(target.title) +
          '</a></th><th class="ds-dist">' + axisHtml(scales[target.slug]) + '</th><th colspan="' + (columns.length - 3) + '" class="ds-lg-verdict">' +
          verdictHtml(verdictOf(target.lines, V.joint), true) + '</th></tr>';
      }
      var id = target.slug + ' | ' + group.config.name;  // WHY not NUL: the HTML parser rewrites it, so the key never matched
      var open = !!V.expanded[id];
      var name = (sorted ? '<a class="ds-lg-title" href="#/target/' + encodeURIComponent(target.slug) + '">' + esc(target.title) + '</a> · ' : '') +
        swatch(group.config.color, group.kind === 'sim') + esc(group.config.name);
      var delta = row.delta === 'baseline' ? '<span class="ds-mut">baseline</span>' : row.delta === null ? '<span class="ds-mut">—</span>' : signedPct(row.delta);
      html += '<tr class="ds-lg-row" data-tc-target-row="' + esc(target.slug) + '" data-config="' + esc(group.config.name) + '" data-row="' + esc(id) + '">' +
        '<td class="ds-text"><span class="ds-caret">' + (open ? '▾' : '▸') + '</span>' + name + '</td>' +
        '<td>' + group.lines.length + ' <span class="ds-mut">(' + (group.sims.length ? group.members.length + ' ' + group.kind + ' · ' + group.sims.length + ' sim' : 'all ' + group.kind) + ')</span></td>' +
        '<td class="ds-dist">' + distHtml(row, (sorted ? shared : scales[target.slug]).high) + '</td>' +
        '<td><b>' + fmtDeg(row.median) + '</b></td><td>' + delta + '</td>' +
        (HAS_TORQUE ? torqueCells(row.fb, row.gap, row.torqued.length) : '') +
        (tolerances ? '<td>' + (row.pass === null ? '—' : Math.round(row.pass * 100) + '%') + '</td>' : '') +
        '<td title="' + esc(row.spread.title || '') + '">' + (row.spread.value === null ? '<span class="ds-mut">—</span>' : fmtDeg(row.spread.value) +
          (row.spread.tcp !== null && row.spread.tcp !== undefined ? ' · ' + nice(mm(row.spread.tcp)) + ' mm' : '')) + '</td>' +
        '<td>' + (row.jointIndex === -1 ? '' : sparkSvg(group.members, row.jointIndex, group.config.color, row.range)) + '</td>' +
        '<td><a class="ds-link" href="#/target/' + encodeURIComponent(target.slug) + '" title="Open this target">↗</a></td></tr>';
      if (open) {
        group.lines.forEach(function (line) {
          html += '<tr class="ds-lg-line"><td class="ds-text" title="' + esc(line.id) + '">' + esc(line.id) + '</td><td class="ds-mut">' + line.kind +
            (line.date ? ' · ' + esc(shortDate(line.date)) : '') + '</td><td></td><td>' + fmtDeg(valueOf(line, V.joint)) + '</td><td></td>' +
            (HAS_TORQUE ? torqueCells(shareOf(line, V.joint), gapOf(line, V.joint), line.torque ? 1 : 0) : '') +
            (tolerances ? '<td>' + (line.ok === null || line.ok === undefined ? '—' : line.ok ? 'pass' : '<span class="ds-fail">fail</span>') + '</td>' : '') +
            '<td></td><td></td><td><a class="ds-link" href="' + esc(line.report) + '" title="Open this run’s report">↗</a></td></tr>';
        });
      }
    });
    html += '</tbody></table></div><p class="ds-note">One row per target × config: its real lines (its sims when it has none). ' +
      'Dots while a config has ≤ ' + V.n + ' lines, a box (IQR) with min–max whiskers past that; the bar is the median. ' +
      'RT is ISO 9283 path repeatability from robot_msgs.compare.aggregate. Click a row for its lines, a header to sort.' +
      (HAS_TORQUE ? ' FB share and drive gap (RMS of commanded − applied torque) are medians over the row’s lines with a torque breakdown, ' +
        (V.joint ? esc(V.joint) : 'the share over all joints and the gap of each line’s largest joint') + '; “—” where none has one.' : '') + '</p>';
    holder.innerHTML = html;
  }
  // The League table's FB share and drive gap cells; "—" where no line of the row has a breakdown (never 0 %).
  function torqueCells(share, gap, count) {
    if (!count) return '<td data-tc-fb-share><span class="ds-mut" title="no line here has a torque breakdown">—</span></td>' +
      '<td data-tc-drive-gap><span class="ds-mut">—</span></td>';
    return '<td data-tc-fb-share>' + fmtShare(share) + '</td><td data-tc-drive-gap>' + fmtNm(gap) + '</td>';
  }
  function distHtml(row, high) {
    var color = row.group.config.color, html = '<div class="ds-dtrack">';
    var left = function (rad) { return (rad * DEG / high * 100).toFixed(2); };
    if (drawMode(row.values.length) === 'bands' && row.values.length >= 2) {
      var sorted = row.values.slice().sort(byNumber);
      html += '<span class="ds-dwhisk" style="left:' + left(sorted[0]) + '%;width:' + (left(sorted[sorted.length - 1]) - left(sorted[0])).toFixed(2) + '%;--c:' + color + '"></span>' +
        '<span class="ds-dbox" style="left:' + left(quantile(sorted, 0.25)) + '%;width:' + Math.max(0.5, left(quantile(sorted, 0.75)) - left(quantile(sorted, 0.25))).toFixed(2) +
        '%;--c:' + color + '"></span>';
    } else {
      row.values.forEach(function (value) { html += '<span class="ds-ddot" style="left:' + left(value) + '%;--c:' + color + '"></span>'; });
    }
    if (row.values.length > 1 && row.median !== null) html += '<span class="ds-dmed" style="left:' + left(row.median) + '%"></span>';
    return html + '</div>';
  }
  $('ds-view-table').addEventListener('click', function (event) {
    var head = event.target.closest('th[data-sort-key]');
    if (head) {
      var key = head.getAttribute('data-sort-key');
      if (!key) return;
      if (key === 'target') V.league = null;
      else V.league = V.league && V.league.key === key ? { key: key, dir: -V.league.dir } : { key: key, dir: 1 };
      renderLeague();
      return;
    }
    if (event.target.closest('a')) return;
    var row = event.target.closest('tr[data-row]');
    if (!row) return;
    var id = row.getAttribute('data-row');
    V.expanded[id] = !V.expanded[id];
    renderLeague();
  });

  // ── Dataset level: the view switch ──

  function showView() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-tc-targets-view] [data-view]'), function (button) {
      var on = button.getAttribute('data-view') === V.view;
      button.classList.toggle('on', on);
      button.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    $('ds-view-cards').hidden = V.view !== 'cards';
    $('ds-view-table').hidden = V.view !== 'table';
    $('ds-view-runs').hidden = V.view !== 'runs';
    renderDatasetControls();
    destroyCharts('cards');
    if (V.view === 'cards') renderCards();
    if (V.view === 'table') renderLeague();
  }
  document.querySelector('[data-tc-targets-view]').addEventListener('click', function (event) {
    var button = event.target.closest('[data-view]');
    if (!button) return;
    V.view = button.getAttribute('data-view');
    store.set('view', V.view);
    showView();
  });

  // ── Target level ──

  var TABS = [
    ['repeat', 'How repeatable is each config on this target?'],
    ['history', 'Has tracking improved across configs over time?'],
  ];
  function chipKeys(line) {
    var keys = ['config=' + line.config, 'date=' + line.date, 'kind=' + line.kind];
    var tags = tagsOf[line.run] || {};
    Object.keys(tags).forEach(function (key) { if (LEVEL_TAGS.indexOf(key) === -1) keys.push('tag:' + key + '=' + tags[key]); });
    return keys;
  }
  function listedLines(target) {
    var pattern = null;
    if (V.filter) { try { pattern = new RegExp(V.filter, 'i'); } catch (error) { pattern = null; } }
    return target.lines.filter(function (line) {
      if (pattern && !pattern.test(line.id + ' ' + line.config + ' ' + line.kind + ' ' + line.date)) return false;
      return !chipKeys(line).some(function (key) { return V.chipOff[key]; });
    });
  }
  function drawnLines(target) {
    return listedLines(target).filter(function (line) { return !V.unchecked[line.id] && !line.error; });
  }

  function renderTargetLevel(target) {
    if (V.target !== target) { V.filter = ''; V.chipOff = {}; V.unchecked = {}; V.hover = null; V.pinned = null; }
    V.target = target;
    destroyCharts('repeat');
    var holder = $('ds-level-target');
    var tabs = TABS.map(function (tab) {
      return '<button type="button" class="ds-tab" role="tab" data-tc-target-tab data-tab="' + tab[0] + '">' + esc(tab[1]) + '</button>';
    }).join('');
    holder.innerHTML =
      '<div class="ds-tl">' +
      '<aside class="ds-rl" id="ds-rl" data-tc-run-list aria-label="Lines of this target">' +
      '<div class="ds-rl-head"><span class="ds-rl-title">Lines</span><span class="ds-rl-count" id="ds-rl-count"></span>' +
      '<button type="button" class="ds-iconbtn" id="ds-rl-fold" data-tc-run-list-fold></button></div>' +
      '<div class="ds-rl-body"><input type="search" id="ds-rl-filter" placeholder="Filter lines (regex)" spellcheck="false" aria-label="Filter lines (regular expression)">' +
      '<div class="ds-rl-chips" id="ds-rl-chips"></div>' +
      '<label class="ds-rl-sort"><span class="ds-k">Group by</span><select id="ds-rl-sort" data-tc-sort>' +
      '<option value="config">config</option><option value="date">date</option><option value="kind">sim / real</option></select></label>' +
      '<div class="ds-rl-groups" id="ds-rl-groups"></div>' +
      '<p class="ds-note">Checkbox colour = config. Hover a line to draw it over its fan; click it to keep it drawn; ↗ opens its run.' +
      (D.drill_down === 'lazy' && location.protocol === 'file:' ? ' Run reports open once this folder is served: <code>' + esc(D.serve_command) + '</code>' : '') + '</p></div>' +
      '</aside>' +
      '<div class="ds-rl-gutter" id="ds-rl-gutter" data-tc-run-list-resize title="Drag to resize · double-click to fold"></div>' +
      '<section class="ds-tl-main">' +
      '<header class="ds-head"><h1>' + esc(target.title) + '</h1><p class="ds-sub" id="ds-tl-sub"></p></header>' +
      '<section class="ds-verdict" data-tc-verdict><h2>Which config tracks this target better?</h2><p id="ds-tl-verdict"></p></section>' +
      '<div class="ds-bar ds-toolbar" id="ds-tl-tools"></div>' +
      '<div class="ds-tabs" role="tablist">' + tabs + '</div>' +
      '<section class="ds-panel" id="ds-panel-repeat" data-tc-target-panel="repeat" role="tabpanel"></section>' +
      '<section class="ds-panel" id="ds-panel-history" data-tc-target-panel="history" role="tabpanel"></section>' +
      '</section></div>';
    var counts = kindCounts(target.lines);
    var dates = unique(target.lines.map(function (line) { return line.date; }).filter(Boolean)).sort();
    $('ds-tl-sub').innerHTML = (target.key !== target.title ? esc(target.key) + ' · ' : '') + plural(target.lines.length, 'line') + ' (' + counts.sim +
      ' sim · ' + counts.real + ' real) from ' + plural(target.runs, 'run') + (dates.length ? ' · ' + dateRange(dates) : '') + ' · ' +
      target.joints.map(esc).join(', ');
    var filter = $('ds-rl-filter');
    filter.value = V.filter;
    filter.addEventListener('input', function () { V.filter = filter.value; refreshTarget(); });
    var sort = $('ds-rl-sort');
    sort.value = V.groupBy;
    sort.addEventListener('change', function () { V.groupBy = sort.value; store.set('group-by', V.groupBy); renderRunList(); });
    wireRunList();
    renderTools();
    holder.querySelector('.ds-tabs').addEventListener('click', function (event) {
      var button = event.target.closest('[data-tab]');
      if (!button) return;
      V.tab = button.getAttribute('data-tab');
      store.set('target-tab', V.tab);
      showTab();
    });
    refreshTarget();
  }
  // Everything that follows the drawn lines: the list, the verdict and the open tab.
  function refreshTarget() {
    renderRunList();
    var v = verdictOf(drawnLines(V.target), V.joint);
    $('ds-tl-verdict').innerHTML = verdictHtml(v, false);
    showTab();
  }
  function showTab() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-tc-target-tab]'), function (button) {
      var on = button.getAttribute('data-tab') === V.tab;
      button.classList.toggle('on', on);
      button.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    $('ds-panel-repeat').hidden = V.tab !== 'repeat';
    $('ds-panel-history').hidden = V.tab !== 'history';
    if (V.tab === 'repeat') renderRepeat(); else { destroyCharts('repeat'); renderHistory(); }
  }

  function renderTools() {
    var bar = $('ds-tl-tools');
    bar.innerHTML =
      '<span class="ds-ctl"><span class="ds-k">Repeats</span><span class="ds-seg" data-tc-repeats role="group">' +
      [['auto', 'Auto', 'Lines while a config has ≤ N lines, a fan past that'], ['lines', 'Lines', 'One line per line'], ['bands', 'Bands', 'A fan: ' + FAN_TEXT]]
        .map(function (item) {
          return '<button type="button" data-mode="' + item[0] + '" title="' + esc(item[2]) + '" class="' + (V.mode === item[0] ? 'on' : '') + '">' + item[1] + '</button>';
        }).join('') + '</span></span>' +
      '<label class="ds-ctl' + (V.mode === 'auto' ? '' : ' ds-dim') + '" data-tc-lines-n title="Auto draws lines while a config has at most N lines">' +
      '<span class="ds-k">Lines up to N</span><input type="range" min="1" max="20" step="1" value="' + V.n + '"><output>' + V.n + '</output></label>' +
      '<label class="ds-ctl" title="TensorBoard’s debiased exponential moving average, per line before the fan is taken">' +
      '<span class="ds-k">Smoothing</span><input type="range" id="ds-smooth" min="0" max="0.95" step="0.05" value="' + V.smooth + '"><output>' + V.smooth.toFixed(2) + '</output></label>' +
      jointSelect('ds-joint-target') +
      '<span class="ds-hint">drag a chart to zoom · double-click resets · click a line or a fan to open the nearest run</span>';
    bar.querySelector('[data-tc-repeats]').addEventListener('click', function (event) {
      var button = event.target.closest('[data-mode]');
      if (!button) return;
      V.mode = button.getAttribute('data-mode');
      store.set('repeats', V.mode);
      renderTools();
      if (V.tab === 'repeat') renderRepeat();
    });
    var lines = bar.querySelector('[data-tc-lines-n] input');
    lines.addEventListener('input', function () {
      V.n = Math.round(within(Number(lines.value), 1, 20, 5));
      lines.nextElementSibling.textContent = String(V.n);
      store.set('lines-n', V.n);
      if (V.tab === 'repeat') renderRepeat();
    });
    var smooth = $('ds-smooth');
    smooth.addEventListener('input', function () {
      V.smooth = within(Number(smooth.value), 0, 0.95, 0);
      smooth.nextElementSibling.textContent = V.smooth.toFixed(2);
      store.set('smoothing', V.smooth);
      if (V.tab === 'repeat') renderRepeat();
    });
    $('ds-joint-target').addEventListener('change', function (event) { setJoint(event.target.value); refreshTarget(); });
  }

  // ── Target level: the run list (2026-11-19 summary V1's sidebar) ──

  function groupOf(line) {
    if (V.groupBy === 'config') return line.config;
    if (V.groupBy === 'date') return line.date || '(no date)';
    return line.kind;
  }
  function groupOrder(a, b) {
    if (V.groupBy === 'config') return (configOf[a] ? configOf[a].index : 1e9) - (configOf[b] ? configOf[b].index : 1e9);
    if (V.groupBy === 'kind') return (a === 'real' ? 0 : 1) - (b === 'real' ? 0 : 1);
    return a === '(no date)' ? 1 : b === '(no date)' ? -1 : a < b ? -1 : a > b ? 1 : 0;
  }
  function lineOrder(a, b) {
    return (a.date < b.date ? -1 : a.date > b.date ? 1 : 0) || a.order - b.order;
  }
  function renderChips(target) {
    var rows = [['config', unique(target.lines.map(function (line) { return line.config; })), true]];
    var dates = unique(target.lines.map(function (line) { return line.date; }).filter(Boolean)).sort();
    if (dates.length) rows.push(['date', dates, false]);
    rows.push(['kind', unique(target.lines.map(function (line) { return line.kind; })), false]);
    var tags = {};
    target.lines.forEach(function (line) {
      var own = tagsOf[line.run] || {};
      Object.keys(own).forEach(function (key) {
        if (LEVEL_TAGS.indexOf(key) !== -1) return;
        tags[key] = tags[key] || [];
        if (tags[key].indexOf(String(own[key])) === -1) tags[key].push(String(own[key]));
      });
    });
    Object.keys(tags).forEach(function (key) {
      if (tags[key].length >= 2 && tags[key].length <= 12) rows.push(['tag:' + key, tags[key].sort(), false]);
    });
    $('ds-rl-chips').innerHTML = rows.map(function (row) {
      var key = row[0], label = key.indexOf('tag:') === 0 ? key.slice(4) : key;
      return '<div class="ds-rl-tagrow"><span class="ds-k">' + esc(label) + '</span>' + row[1].map(function (value) {
        var id = key + '=' + value;
        var count = target.lines.filter(function (line) { return chipKeys(line).indexOf(id) !== -1; }).length;
        return '<button type="button" class="ds-tchip' + (V.chipOff[id] ? ' off' : '') + '" data-chip="' + esc(id) + '" title="' +
          (V.chipOff[id] ? 'Show' : 'Hide') + ' lines with ' + esc(label) + ' = ' + esc(value) + '">' + (row[2] ? swatch(colorOf(value), configOf[value] && !configOf[value].real) : '') +
          esc(key === 'date' ? shortDate(value) : value) + '<span class="ds-n">' + count + '</span></button>';
      }).join('') + '</div>';
    }).join('');
  }
  function renderRunList() {
    var target = V.target;
    renderChips(target);
    var listed = listedLines(target);
    var groups = {};
    listed.forEach(function (line) { (groups[groupOf(line)] = groups[groupOf(line)] || []).push(line); });
    var html = '';
    Object.keys(groups).sort(groupOrder).forEach(function (key) {
      var lines = groups[key].sort(lineOrder);
      var on = lines.filter(function (line) { return !V.unchecked[line.id]; }).length;
      var color = V.groupBy === 'config' ? colorOf(key) : '#52514e';
      var label = V.groupBy === 'date' ? key : key;
      html += '<div class="ds-rl-group"><input type="checkbox" class="ds-cb" data-group="' + esc(key) + '" style="--c:' + color + '"' +
        (on === lines.length ? ' checked' : '') + (on > 0 && on < lines.length ? ' data-mixed="1"' : '') + ' title="Draw every line of this group">' +
        (V.groupBy === 'config' ? swatch(color, configOf[key] && !configOf[key].real) : '') + '<span class="ds-rl-gname">' + esc(label) +
        '</span><span class="ds-rl-gcount">' + on + '/' + lines.length + '</span></div>';
      lines.forEach(function (line) {
        var checked = !V.unchecked[line.id];
        var meta = [];
        if (V.groupBy !== 'config') meta.push(esc(line.config));
        if (V.groupBy !== 'kind') meta.push(line.kind);
        if (V.groupBy !== 'date' && line.date) meta.push(esc(shortDate(line.date)));
        html += '<div class="ds-rl-row' + (checked ? '' : ' off') + (V.pinned === line.id ? ' pinned' : '') + '" data-tc-run data-line="' + esc(line.id) +
          '" data-config="' + esc(line.config) + '" data-kind="' + line.kind + '" data-date="' + esc(line.date) + '">' +
          '<input type="checkbox" class="ds-cb" style="--c:' + colorOf(line.config) + '"' + (checked ? ' checked' : '') + ' aria-label="Draw ' + esc(line.id) + '">' +
          '<span class="ds-rl-name" title="' + esc(line.id) + '">' + esc(line.id) + '</span>' +
          '<span class="ds-rl-val" title="RMS joint error, ' + esc(jointWords(V.joint)) + '">' + (line.error ? '<span class="ds-fail" title="' + esc(line.error) + '">not analysed</span>' : fmtDeg(valueOf(line, V.joint))) + '</span>' +
          '<a class="ds-rl-open" href="' + esc(line.report) + '" title="Open the run report of ' + esc(line.run) + '">↗</a>' +
          '<span class="ds-rl-meta">' + meta.join(' · ') + '</span></div>';
      });
    });
    var box = $('ds-rl-groups');
    box.innerHTML = html || '<p class="ds-note">No line matches the filter.</p>';
    Array.prototype.forEach.call(box.querySelectorAll('input[data-mixed]'), function (input) { input.indeterminate = true; });
    $('ds-rl-count').textContent = listed.filter(function (line) { return !V.unchecked[line.id]; }).length + '/' + target.lines.length;
    var invalid = false;
    if (V.filter) { try { new RegExp(V.filter); } catch (error) { invalid = true; } }
    $('ds-rl-filter').classList.toggle('bad', invalid);
  }
  function wireRunList() {
    var aside = $('ds-rl'), gutter = $('ds-rl-gutter'), fold = $('ds-rl-fold'), groups = $('ds-rl-groups');
    function apply() {
      aside.classList.toggle('folded', V.listFolded);
      aside.style.width = V.listFolded ? '' : V.listWidth + 'px';
      fold.textContent = V.listFolded ? '»' : '«';
      fold.title = V.listFolded ? 'Unfold the line list' : 'Fold the line list';
    }
    function toggle() {
      V.listFolded = !V.listFolded;
      store.set('list-folded', V.listFolded);
      apply();
    }
    apply();
    // WHY window listeners, not pointer capture: the drag must survive the pointer leaving the 7 px gutter.
    gutter.addEventListener('pointerdown', function (event) {
      event.preventDefault();
      var startX = event.clientX, startWidth = V.listFolded ? 30 : V.listWidth, moved = false;
      document.body.classList.add('ds-resizing');
      function move(next) {
        var dx = next.clientX - startX;
        if (!moved && Math.abs(dx) < 3) return;
        moved = true;
        V.listFolded = false;
        V.listWidth = Math.max(180, Math.min(640, startWidth + dx));
        apply();
      }
      function up() {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        document.body.classList.remove('ds-resizing');
        if (moved) { store.set('list-width', V.listWidth); store.set('list-folded', V.listFolded); }
      }
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    gutter.addEventListener('dblclick', toggle);
    fold.addEventListener('click', toggle);
    $('ds-rl-chips').addEventListener('click', function (event) {
      var chip = event.target.closest('[data-chip]');
      if (!chip) return;
      var id = chip.getAttribute('data-chip');
      if (V.chipOff[id]) delete V.chipOff[id]; else V.chipOff[id] = true;
      refreshTarget();
    });
    groups.addEventListener('change', function (event) {
      var input = event.target;
      if (!input.matches('input[type="checkbox"]')) return;
      var group = input.getAttribute('data-group');
      if (group !== null) {
        listedLines(V.target).forEach(function (line) {
          if (groupOf(line) !== group) return;
          if (input.checked) delete V.unchecked[line.id]; else V.unchecked[line.id] = true;
        });
      } else {
        var id = input.closest('[data-tc-run]').getAttribute('data-line');
        if (input.checked) delete V.unchecked[id]; else V.unchecked[id] = true;
      }
      refreshTarget();
    });
    groups.addEventListener('click', function (event) {
      if (event.target.closest('input, a')) return;
      var row = event.target.closest('[data-tc-run]');
      if (!row) return;
      var id = row.getAttribute('data-line');
      V.pinned = V.pinned === id ? null : id;
      Array.prototype.forEach.call(groups.querySelectorAll('[data-tc-run]'), function (other) {
        other.classList.toggle('pinned', other.getAttribute('data-line') === V.pinned);
      });
      if (V.tab === 'repeat') renderRepeat();
    });
    var pending = null;
    function hover(id) {
      if (V.hover === id) return;
      V.hover = id;
      if (pending) cancelAnimationFrame(pending);
      pending = requestAnimationFrame(function () { pending = null; if (V.tab === 'repeat') renderRepeat(); });
    }
    groups.addEventListener('mouseover', function (event) {
      var row = event.target.closest('[data-tc-run]');
      hover(row ? row.getAttribute('data-line') : null);
    });
    groups.addEventListener('mouseleave', function () { hover(null); });
  }

  // ── Target level: the repeat tab ──

  function renderRepeat() {
    destroyCharts('repeat');
    var target = V.target, panel = $('ds-panel-repeat');
    var lines = drawnLines(target);
    var byId = {};
    target.lines.forEach(function (line) { byId[line.id] = line; });
    var highlighted = unique([V.pinned, V.hover].filter(Boolean)).map(function (id) { return byId[id]; }).filter(function (line) {
      return line && !line.error && lines.indexOf(line) !== -1;
    });
    var html = '<h2 class="ds-panel-h" data-tc-tab-heading>' + esc(TABS[0][1]) + '</h2><p class="ds-note">Each chart is one joint’s error, target − line, over the trajectory. ' +
      'A config draws lines while it has ≤ N lines and a fan past that (' + FAN_TEXT + '); its sim lines draw dashed over it, never pooled into the fan.</p>';
    if (!lines.length) html += '<p class="ds-note">Every line is filtered out or unchecked.</p>';
    var todo = [];
    // One chart card per joint x signal; every chart draws its config groups exactly as the joint error does.
    function card(title, joint, index, kind, valuesOf, options) {
      var own = lines.filter(function (line) { return valuesOf(line, index) !== null; });
      var drawn = layersFor(own, index, valuesOf);
      todo.push({ drawn: drawn, index: index, valuesOf: valuesOf, options: options, own: own });
      return '<div class="ds-chart-card" data-tc-chart="' + kind + '" data-joint-name="' + esc(joint) + '"><div class="ds-csec"><b>' + esc(title) +
        '</b></div><div class="ds-chips">' + drawChips(drawn.draws) + '</div><div class="ds-plot" data-joint="' + index + '"></div><div class="ds-readout">&nbsp;</div></div>';
    }
    html += '<div class="ds-charts">';
    target.joints.forEach(function (joint, index) {
      html += card(joint + ': joint error, target − line [°]', joint, index, 'joint-error', errorSeries, { unit: '°' });
    });
    html += '</div>';
    // WHY only on a target with a breakdown (Zach 2026-11-19, torque breakdown in the dataset view; NAVIGATION.md Part A:
    // "when present feedback torque and FB share"): a target whose lines carry none shows no empty torque chart.
    if (target.has_torque_breakdown) {
      var torqued = lines.filter(function (line) { return line.torque; });
      html += '<section class="ds-torque" data-tc-torque><h3 class="ds-panel-sub"><span class="ds-fbmark"></span>How much of the commanded torque did the feedback supply?</h3>' +
        '<p class="ds-note">Feedback torque is the error-correcting part of the command (commanded − feedforward), per joint over the trajectory. ' +
        esc(SHARE_TEXT) + ', here over a ±150 ms window around each instant; the window’s denominator is floored at 5 % of the joint’s typical command, ' +
        'so a parked joint (no feedforward, a hair of feedback) reads near 0 %, not 100 %. Only lines with a torque breakdown draw; their configs fan past N as above.</p>';
      if (!torqued.length) {
        html += '<p class="ds-note">No drawn line has a torque breakdown: check one in the list.</p>';
      } else {
        html += '<div class="ds-charts">';
        target.joints.forEach(function (joint, index) {
          html += card(joint + ': feedback torque, commanded − feedforward [N·m]', joint, index, 'feedback-torque', feedbackSeries, { unit: ' N·m', tickUnit: '' });
          html += card(joint + ': feedback share of the command, ±150 ms [%]', joint, index, 'fb-share', shareSeries, { unit: '%', digits: 1 });
        });
        html += '</div>';
      }
      html += '</section>';
    }
    panel.innerHTML = html;
    var hosts = panel.querySelectorAll('.ds-plot');
    requestAnimationFrame(function () {
      if (V.target !== target || V.tab !== 'repeat') return;
      todo.forEach(function (item, k) {
        var host = hosts[k];
        if (!host || !host.isConnected) return;
        var overlay = highlighted.filter(function (line) { return item.own.indexOf(line) !== -1; }).map(function (line) {
          return { line: line, y: smoothed(item.valuesOf(line, item.index), V.smooth) };
        });
        var chart = fanChart(host, Object.assign({ x: target.t, layers: item.drawn.layers, overlay: overlay, height: 220, readout: host.nextElementSibling, onPick: openLine }, item.options));
        if (chart) charts.repeat.push(chart);
      });
    });
  }

  // ── Target level: the history tab (2026-11-19 summary V5's control chart) ──

  function renderHistory() {
    var target = V.target, panel = $('ds-panel-history');
    var lines = drawnLines(target).filter(function (line) { return valueOf(line, V.joint) !== null; });
    var real = lines.filter(function (line) { return line.kind === 'real'; });
    var points = (real.length ? real : lines).slice().sort(lineOrder);
    var sims = real.length ? lines.filter(function (line) { return line.kind === 'sim'; }) : [];
    var html = '<h2 class="ds-panel-h" data-tc-tab-heading>' + esc(TABS[1][1]) + '</h2>';
    if (!points.length) { panel.innerHTML = html + '<p class="ds-note">Every line is filtered out or unchecked.</p>'; return; }
    var phases = [];
    points.forEach(function (line, index) {
      var last = phases[phases.length - 1];
      if (!last || last.config !== line.config) phases.push({ config: line.config, start: index, lines: [line] });
      else last.lines.push(line);
    });
    phases.forEach(function (phase) {
      phase.values = phase.lines.map(function (line) { return valueOf(line, V.joint); });
      phase.mean = mean(phase.values);
      phase.limits = controlLimits(phase.values);
    });
    var above = [];
    phases.forEach(function (phase) {
      phase.lines.forEach(function (line, k) { if (phase.limits && phase.values[k] > phase.limits.ucl) above.push(line); });
    });
    // The answer: the config of the latest phase against the earliest, by their mean over this target's lines.
    var order = unique(points.map(function (line) { return line.config; }));
    var meanOf = function (config) {
      return mean(points.filter(function (line) { return line.config === config; }).map(function (line) { return valueOf(line, V.joint); }));
    };
    var first = order[0], latest = phases[phases.length - 1].config;
    var answer;
    if (order.length < 2) {
      answer = 'One config so far: ' + swatch(colorOf(first)) + '<b>' + esc(first) + '</b>, mean ' + fmtDeg(meanOf(first)) + ' over ' + plural(points.length, (real.length ? 'real' : 'sim') + ' line') + '.';
    } else {
      var a = meanOf(first), b = meanOf(latest);
      if (latest === first) {
        answer = 'The latest lines are ' + swatch(colorOf(latest)) + '<b>' + esc(latest) + '</b> again: mean ' + fmtDeg(b) + '; ' + order.slice(1).map(esc).join(', ') + ' ran in between.';
      } else {
        var change = a > 0 ? (b - a) / a : 0;
        answer = swatch(colorOf(latest)) + '<b>' + esc(latest) + '</b> (latest) against ' + esc(first) + ' (first): mean RMS error ' + fmtDeg(a) + ' → ' + fmtDeg(b) +
          ', <b>' + signedPct(change) + '</b> — ' + (b < a ? 'tracking improved' : b > a ? '<span class="ds-warn">tracking got worse</span>' : 'no change') + '.';
      }
    }
    if (above.length) answer += ' <span class="ds-fail">' + plural(above.length, 'line') + ' above its phase’s upper control limit</span>.';
    html += '<p class="ds-answer">' + answer + '</p><div class="ds-spc" id="ds-spc"></div>' +
      '<p class="ds-note">' + phases.map(function (phase) {
        return esc(phase.config) + ' n=' + phase.lines.length + ': mean ' + fmtDeg(phase.mean) + (phase.limits ? ', UCL ' + fmtDeg(phase.limits.ucl) : '');
      }).join(' · ') + '. One point per ' + (real.length ? 'real ' : '') + 'line in date order (RMS error, ' + esc(jointWords(V.joint)) +
      '); a phase is a run of lines with one config, its centre line the mean and its dashed limits mean ± 2.66 × the mean moving range (I-MR).' +
      (sims.length ? ' Dotted: each config’s sim lines (median), for reference.' : '') + ' Click a point to open its run.</p>';
    panel.innerHTML = html;
    drawControlChart($('ds-spc'), points, phases, sims, above);
  }
  function drawControlChart(host, points, phases, sims, above) {
    var width = Math.max(420, host.clientWidth || 800), height = 230;
    var left = 54, right = 120, top = 26, bottom = 30;
    var n = points.length;
    var values = points.map(function (line) { return valueOf(line, V.joint) * DEG; });
    var simRefs = [];
    LV.configs.forEach(function (config) {
      var own = sims.filter(function (line) { return line.config === config.name; });
      if (own.length) simRefs.push({ config: config, value: median(own.map(function (line) { return valueOf(line, V.joint); })) * DEG });
    });
    var high = Math.max.apply(null, values.concat(phases.map(function (phase) { return phase.limits ? phase.limits.ucl * DEG : 0; }),
      simRefs.map(function (ref) { return ref.value; })));
    var step = niceStep((high || 1) / 4);
    high = Math.ceil((high * 1.05 || 1) / step) * step;
    var x = function (i) { return left + (n === 1 ? 0.5 : i / (n - 1)) * (width - left - right); };
    var y = function (v) { return top + (1 - v / high) * (height - top - bottom); };
    var half = (width - left - right) / Math.max(1, n - 1) / 2;
    var svg = '<svg class="ds-spc-svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Control chart of RMS error per line">';
    phases.forEach(function (phase) {
      var color = colorOf(phase.config);
      var x0 = Math.max(left - 8, x(phase.start) - half), x1 = Math.min(width - right + 8, x(phase.start + phase.lines.length - 1) + half);
      svg += '<rect x="' + x0.toFixed(1) + '" y="' + (top - 4) + '" width="' + Math.max(4, x1 - x0).toFixed(1) + '" height="' + (height - top - bottom + 8) +
        '" fill="' + hexA(color, 0.06) + '" rx="3"/>';
      svg += '<text x="' + (x1 - 4).toFixed(1) + '" y="' + (top - 8) + '" text-anchor="end" font-size="10.5" font-weight="600" fill="' + color + '">' +
        esc(phase.config) + ' · n=' + phase.lines.length + '</text>';
      if (phase.limits) {
        svg += '<line x1="' + (x0 + 2).toFixed(1) + '" x2="' + (x1 - 2).toFixed(1) + '" y1="' + y(phase.limits.mean * DEG).toFixed(1) + '" y2="' + y(phase.limits.mean * DEG).toFixed(1) +
          '" stroke="' + color + '" stroke-width="1.4"/>';
        [phase.limits.ucl, phase.limits.lcl].forEach(function (limit) {
          var v = limit * DEG;
          if (v > 0 && v <= high) {
            svg += '<line x1="' + (x0 + 2).toFixed(1) + '" x2="' + (x1 - 2).toFixed(1) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) +
              '" stroke="#8a8983" stroke-dasharray="4 3"/>';
          }
        });
      }
    });
    for (var v = 0; v <= high + 1e-9; v += step) {
      svg += '<text x="' + (left - 8) + '" y="' + (y(v) + 3).toFixed(1) + '" text-anchor="end" font-size="10" fill="#8a8983">' + +v.toFixed(3) + '°</text>' +
        '<line x1="' + (left - 4) + '" x2="' + left + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '" stroke="#cfcec8"/>';
    }
    simRefs.forEach(function (ref) {
      svg += '<line x1="' + left + '" x2="' + (width - right) + '" y1="' + y(ref.value).toFixed(1) + '" y2="' + y(ref.value).toFixed(1) + '" stroke="' + ref.config.color +
        '" stroke-dasharray="1 3" stroke-width="1.3"/><text x="' + (width - right + 6) + '" y="' + (y(ref.value) + 3).toFixed(1) + '" font-size="10" fill="' + ref.config.color + '">sim · ' +
        esc(ref.config.name) + '</text>';
    });
    var labelEvery = Math.max(1, Math.ceil(n / Math.max(1, (width - left - right) / 30)));
    points.forEach(function (line, i) {
      if (line.date && (i === 0 || points[i - 1].date !== line.date)) {
        if (i > 0) svg += '<line x1="' + (x(i) - half).toFixed(1) + '" x2="' + (x(i) - half).toFixed(1) + '" y1="' + top + '" y2="' + (height - bottom + 2) + '" stroke="#cfcec8" stroke-dasharray="2 2"/>';
        svg += '<text x="' + ((i > 0 ? x(i) - half : left - 6) + 4).toFixed(1) + '" y="' + (height - 4) + '" font-size="10" fill="#52514e">' + esc(line.date) + '</text>';
      }
      if (i % labelEvery === 0) svg += '<text x="' + x(i).toFixed(1) + '" y="' + (height - bottom + 12) + '" text-anchor="middle" font-size="9.5" fill="#8a8983">#' + (i + 1) + '</text>';
    });
    svg += '<path d="' + values.map(function (value, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(value).toFixed(1); }).join('') + '" fill="none" stroke="#b9b8b1"/>';
    points.forEach(function (line, i) {
      var out = above.indexOf(line) !== -1, color = colorOf(line.config);
      svg += '<a href="' + esc(line.report) + '"><title>' + esc(line.id + ' · ' + line.config + (line.date ? ' · ' + line.date : '') + ' · RMS ' + nice(values[i]) + '°' +
        (out ? ' · above its upper control limit' : '') + ' · click to open its run') + '</title>' +
        (out ? '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(values[i]).toFixed(1) + '" r="8" fill="none" stroke="#c74434" stroke-width="1.3"/>' : '') +
        '<circle class="ds-spc-dot" cx="' + x(i).toFixed(1) + '" cy="' + y(values[i]).toFixed(1) + '" r="4.5" fill="' + (out ? '#c74434' : color) + '" stroke="#fff"/></a>';
    });
    host.innerHTML = svg + '</svg>';
  }

  // ── routing: #/ (Dataset) and #/target/<slug> (Target) ──

  function route() {
    var match = /^#\/target\/(.+)$/.exec(location.hash || '');
    var slug = match ? decodeURIComponent(match[1]) : null;
    var target = slug ? targetOf[slug] : null;
    var crumbs = $('ds-crumbs');
    destroyCharts('cards');
    destroyCharts('repeat');
    if (target) {
      $('ds-level-dataset').hidden = true;
      $('ds-level-target').hidden = false;
      crumbs.innerHTML = '<a href="#/">Dataset</a><span class="ds-crumb-sep">›</span><span class="ds-crumb-here">' + esc(target.title) + '</span>';
      document.title = target.title + ' · ' + D.title;
      renderTargetLevel(target);
    } else {
      $('ds-level-target').hidden = true;
      $('ds-level-target').innerHTML = '';
      V.target = null;
      $('ds-level-dataset').hidden = false;
      crumbs.innerHTML = '<span class="ds-crumb-here">Dataset</span>' +
        (slug ? '<span class="ds-crumb-sep">·</span><span class="ds-fail">no target “' + esc(slug) + '” in this dataset</span>' : '');
      document.title = D.title;
      renderBand();
      showView();
    }
  }
  window.addEventListener('hashchange', function () { route(); window.scrollTo(0, 0); });
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (V.target && V.tab === 'history') renderHistory(); }, 150);
  });
  route();
})();
