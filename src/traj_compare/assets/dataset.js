/* traj_compare — dataset view: many runs at a glance, then drill down.
 *
 * Reads the payload dataset.py embeds (SI: rad, m, s) and draws, top to bottom: one calm answer
 * line, the domain's Summary page, the runs x pairs table, a joint x run heatmap, a peak-time
 * strip and the ISO 9283 cards. WHY degrees here and not in the data: angles are SI in rows.json
 * and the payload, and become degrees only at this display edge (Zach: angles read in degrees).
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
    '<header><h1></h1><p class="ds-sub"></p><p class="ds-answer" id="ds-answer"></p>' +
    '<div class="ds-bar" id="ds-global"></div><div class="ds-banner" id="ds-banner" hidden></div></header>' +
    '<div class="ds-summary" id="ds-summary"></div>' +
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
    '<footer class="ds-foot" id="ds-foot"></footer>';
  document.title = D.title;
  main.querySelector('h1').textContent = D.title;
  main.querySelector('.ds-sub').textContent =
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
    fetch(location.origin + '/__rerun/open?rrd=' + encodeURIComponent(row.rrd), { method: 'POST' })
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

  // ── assembly ───────────────────────────────────────────────────────────────

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
})();
