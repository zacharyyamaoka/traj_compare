/* R4 "Rerun parity" (run-view round 2026-11-24): the playback viewer's frame, laid out AS the Rerun blueprint
 * traj_compare writes for the same runs (rerun_export._layout_questions, the `questions` layout), so switching between
 * the HTML and Rerun needs no re-orientation, and "Open the same in Rerun" is the page's primary action.
 *
 * WHY (Zach 2026-11-19: "designing a different run viewer for standalone and rerun is a bit silly ... they should be
 * the exact same thing"; 2026-11-24: the playback viewer is "either our custom one or the rerun one").
 *
 * What it mirrors, read from the real Rerun 0.40 viewer showing the recording serve.py writes (r4/rerun-real.cjs,
 * shots/r4/rerun-real-*.png):
 *   - the blueprint panel on the left (SOURCES, then the tree), each run under its entity path /world/<run> with an eye.
 *     Here the eye IS the run selection: shown in every view (Rerun: a `- /**\/<run>` line in each view's filter);
 *   - the stage (the 3D view, its own title bar) beside the question tabs at column shares 2 : 5;
 *   - the question tabs, exact titles (traj_compare.tabs.TABS), as Rerun's tab bar; every chart a Rerun view with its
 *     title bar (? help, eye = fold, maximize), one per row (Zach 2026-11-24 on the Rerun view: "Please show the joints
 *     one per row here not with 2 columns");
 *   - the time panel docked at the bottom: play, step, loop (off / selection / all), timeline "t", playback speed, the
 *     current time field, the streams rows and the time ruler with Rerun's time cursor (a line with a triangle) that
 *     drags; a drag on the ruler selects a time segment; collapsed, it is Rerun's one-row scrubber.
 * Colours: Rerun's light theme shape in traj_compare's palette and type (style.css), the runs keep their colours.
 */
(function () {
  'use strict';
  var KEY = 'tc-r4:';
  function store(key, value) {
    try { if (value === null) localStorage.removeItem(KEY + key); else localStorage.setItem(KEY + key, JSON.stringify(value)); } catch (error) {}
  }
  function recall(key, fallback) {
    try { var raw = localStorage.getItem(KEY + key); return raw === null ? fallback : JSON.parse(raw); } catch (error) { return fallback; }
  }
  function el(tag, cls, parent, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  function clamp(value, lo, hi) { return Math.max(lo, Math.min(hi, value)); }

  // 14 px line icons in the spirit of Rerun's (drawn here, not copied)
  var PATHS = {
    view3d: '<rect x="1.5" y="1.5" width="11" height="11" rx="2"/><path d="M4.5 4v5.5H10M4.5 9.5 8 6"/>',
    series: '<rect x="1.5" y="1.5" width="11" height="11" rx="2"/><path d="M3.8 9.2 5.8 6l2 2.2 2.6-3.8"/>',
    text: '<rect x="1.5" y="1.5" width="11" height="11" rx="2"/><path d="M4.2 4.8h5.6M4.2 7h5.6M4.2 9.2h3.6"/>',
    bars: '<rect x="1.5" y="1.5" width="11" height="11" rx="2"/><path d="M4.5 10V7M7 10V4.5M9.5 10V6"/>',
    vertical: '<rect x="1.5" y="2" width="11" height="4.4" rx="1"/><rect x="1.5" y="7.6" width="11" height="4.4" rx="1"/>',
    horizontal: '<rect x="1.5" y="2" width="4.6" height="10" rx="1"/><rect x="7.9" y="2" width="4.6" height="10" rx="1"/>',
    tabs: '<path d="M1.5 5h11v7h-11zM1.5 5V2.5h4.2V5"/>',
    grid: '<rect x="1.5" y="1.5" width="4.5" height="4.5" rx=".8"/><rect x="8" y="1.5" width="4.5" height="4.5" rx=".8"/><rect x="1.5" y="8" width="4.5" height="4.5" rx=".8"/><rect x="8" y="8" width="4.5" height="4.5" rx=".8"/>',
    eye: '<path d="M1.2 7S3.4 3.2 7 3.2 12.8 7 12.8 7 10.6 10.8 7 10.8 1.2 7 1.2 7z"/><circle cx="7" cy="7" r="1.7"/>',
    eyeOff: '<path d="M1.2 7S3.4 3.2 7 3.2 12.8 7 12.8 7 10.6 10.8 7 10.8 1.2 7 1.2 7z"/><path d="M2.5 11.5 11.5 2.5"/>',
    max: '<path d="M8.5 1.8h3.7v3.7M12.2 1.8 8.2 5.8M5.5 12.2H1.8V8.5M1.8 12.2l4-4"/>',
    entity: '<path d="M7 2.6 11.4 7 7 11.4 2.6 7z"/>',
    app: '<ellipse cx="7" cy="3.6" rx="4.6" ry="1.8"/><path d="M2.4 3.6v6.8c0 1 2 1.8 4.6 1.8s4.6-.8 4.6-1.8V3.6M2.4 7c0 1 2 1.8 4.6 1.8S11.6 8 11.6 7"/>',
    recording: '<circle cx="7" cy="7" r="5"/><circle cx="7" cy="7" r="1.6" fill="currentColor"/>',
    play: '<path d="M4.2 2.6v8.8L11 7z"/>',
    pause: '<path d="M4.8 3v8M9.2 3v8"/>',
    stepBack: '<path d="M3.4 3v8M10.8 3v8L5.4 7z"/>',
    stepFwd: '<path d="M10.6 3v8M3.2 3v8L8.6 7z"/>',
    loop: '<path d="M5 3.4 2.6 5.8 5 8.2M2.6 5.8h6.2a2.6 2.6 0 0 1 0 5.2H6.2"/>',
    down: '<path d="M4 5.5 7 8.5l3-3"/>',
    right: '<path d="M5.5 4 8.5 7l-3 3"/>',
    panelLeft: '<rect x="1.5" y="2" width="11" height="10" rx="1.5"/><path d="M5.6 2v10"/>',
    panelBottom: '<rect x="1.5" y="2" width="11" height="10" rx="1.5"/><path d="M1.5 8.6h11"/>',
    open: '<path d="M8.2 1.8h4v4M12.2 1.8 6.6 7.4M10.6 8.6v3.6H1.8V3.4h3.6"/>',
    search: '<circle cx="6" cy="6" r="3.8"/><path d="m9 9 3.2 3.2"/>',
  };
  function icon(name, cls) {
    var span = el('span', 'r4-ico' + (cls ? ' ' + cls : ''));
    span.setAttribute('aria-hidden', 'true');
    span.innerHTML = '<svg viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.15" ' +
      'stroke-linecap="round" stroke-linejoin="round">' + PATHS[name] + '</svg>';
    return span;
  }
  function iconButton(parent, name, title, cls) {
    var button = el('button', 'r4-ibtn' + (cls ? ' ' + cls : ''), parent);
    button.type = 'button';
    button.appendChild(icon(name));
    button.title = title;
    button.setAttribute('aria-label', title);
    return button;
  }

  /* ------------------------------------------------------------------ help: Rerun 0.40's own rows, and this page's */
  // Quoted from the "?" popups of the real Rerun 0.40 viewer (shots/r4/rerun-real-tta-help-*.png). `here` says what
  // this page does when it differs; null = the same as Rerun.
  var HELP = {
    series: {
      title: 'Time series view',
      rows: [
        ['Move time cursor', 'drag anywhere · right click', 'right click · drag the cursor itself'],
        ['Pan', 'middle drag · Shift + scroll', 'left drag'],
        ['Horizontal pan', null, 'Shift + scroll'],
        ['Zoom', null, 'Ctrl + scroll'],
        ['Zoom X-axis', null, 'Ctrl + Shift + scroll'],
        ['Zoom Y-axis', 'not built: y always fits the runs shown', 'Ctrl + Alt + scroll'],
        ['Zoom to selection', 'right drag · Ctrl + drag', 'right drag'],
        ['Reset view', null, 'double click'],
        ['Hide/show series', 'the eye in Runs: every view at once', 'click the legend'],
        ['Hide/show other series', 'Alt + click a run in Runs', 'Alt + click the legend'],
        ['Read the values', null, 'hover: the time and every run\'s value'],
      ],
      note: 'One difference on purpose: a plain drag moves the time on every chart, the 3D and the time panel ' +
        '(in Rerun it pans), because dragging the time on any figure is this viewer\'s core.',
    },
    view3d: {
      title: '3D view',
      rows: [
        ['Rotate', 'drag', 'left drag'],
        ['Pan', 'right drag', 'right drag'],
        ['Zoom', 'scroll', 'scroll'],
        ['Reset view', 'double click', 'double click the background'],
        ['Fly to an axis', 'click a ball on the corner gizmo', null],
        ['Roll · navigate · focus · track', 'not built', 'Alt + right drag · WASD/QE · double click · Alt + double click'],
      ],
      note: 'The arm of each run stands at the time cursor; a run hidden in Runs leaves the 3D too.',
    },
    text: {
      title: 'Text view',
      rows: [['Scroll', 'scroll the tab', 'scroll'], ['Go to the worst moment', 'the “Go to t = …” button', 'the scorecard names it']],
      note: 'In Rerun the scorecard is a text document; here it is the run report\'s answer and statistics table.',
    },
    time: {
      title: 'Timeline',
      rows: [
        ['Move time cursor', 'click or drag the streams, drag the cursor', 'click the streams, drag the cursor'],
        ['Select time segment', 'drag the time scale', 'drag the time scale'],
        ['Remove the selection', 'double click the time scale · Esc', 'context menu on the selection'],
        ['Snap to grid', 'always: every sample of the run', 'Shift'],
        ['Pan · zoom the time panel', 'not built: it always shows the whole run', 'middle drag · Ctrl + scroll · right drag'],
        ['Play/Pause', null, 'Space'],
        ['Step one sample', '← →', '← →'],
      ],
      note: 'Loop: off → the time selection → the whole run (as Rerun\'s loop button). Speed: 0.25x to 4x.',
    },
  };
  var helpEl = null, helpOwner = null, helpTimer = 0;
  function showHelp(button, kind) {
    var spec = HELP[kind];
    if (!helpEl) {
      helpEl = el('div', 'r4-help', document.body);
      helpEl.setAttribute('role', 'tooltip');
      helpEl.addEventListener('mouseenter', function () { clearTimeout(helpTimer); });
      helpEl.addEventListener('mouseleave', hideHelpSoon);
    }
    clearTimeout(helpTimer);
    helpOwner = button;
    helpEl.innerHTML = '';
    var head = el('div', 'r4-help-head', helpEl);
    el('span', 'r4-help-title', head, spec.title);
    el('span', 'r4-help-cols', head, 'this page · Rerun 0.40');
    var table = el('table', 'r4-help-table', helpEl);
    spec.rows.forEach(function (row) {
      var tr = el('tr', row[1] ? 'diff' : '', table);
      el('th', '', tr, row[0]);
      el('td', 'here', tr, row[1] || row[2] || '—');
      el('td', 'rerun', tr, row[1] ? (row[2] || '—') : 'same');
    });
    if (spec.note) el('p', 'r4-help-note', helpEl, spec.note);
    helpEl.style.display = 'block';
    var box = button.getBoundingClientRect();
    var width = helpEl.offsetWidth, height = helpEl.offsetHeight;
    var left = clamp(box.right - width, 8, window.innerWidth - width - 8);
    var top = box.bottom + 6;
    if (top + height > window.innerHeight - 8) top = Math.max(8, box.top - height - 6);
    helpEl.style.left = left + 'px';
    helpEl.style.top = top + 'px';
  }
  function hideHelpSoon() {
    clearTimeout(helpTimer);
    helpTimer = setTimeout(function () { if (helpEl) helpEl.style.display = 'none'; helpOwner = null; }, 180);
  }
  function helpButton(parent, kind) {
    var button = el('button', 'r4-ibtn r4-q', parent, '?');
    button.type = 'button';
    button.title = 'Help: ' + HELP[kind].title.toLowerCase() + ' — the gestures here, beside Rerun 0.40\'s';
    button.setAttribute('aria-label', button.title);
    button.addEventListener('mouseenter', function () { showHelp(button, kind); });
    button.addEventListener('mouseleave', hideHelpSoon);
    button.addEventListener('click', function () { if (helpOwner === button && helpEl.style.display === 'block') hideHelpSoon(); else showHelp(button, kind); });
    return button;
  }

  /* ------------------------------------------------------------------ a Rerun view: its title bar */
  // icon · title (ellipsized, whole in `title`) · ? · eye (fold the view, remembered) · maximize
  function viewBar(kind, titleNode, options) {
    var bar = el('div', 'r4-vbar');
    bar.appendChild(icon({ series: 'series', view3d: 'view3d', text: 'text', bars: 'bars' }[kind] || 'series', 'r4-vicon'));
    if (typeof titleNode === 'string') {
      var text = el('span', 'r4-vtitle', null, titleNode);
      text.title = titleNode;
      titleNode = text;
    }
    titleNode.classList.add('r4-vtitle');
    bar.appendChild(titleNode);
    var tools = el('span', 'r4-vtools', bar);
    helpButton(tools, options.help || kind);
    if (options.onEye) {
      var eye = iconButton(tools, 'eye', 'Fold this view away (its title bar stays): click again to show it');
      eye.onclick = function () { options.onEye(eye); };
      bar.eye = eye;
    }
    if (options.onMax) {
      var max = iconButton(tools, 'max', 'Maximize this view (Esc or click again to restore)');
      max.onclick = function () { options.onMax(max); };
    }
    return bar;
  }
  function paintEye(button, on) {
    if (!button) return;
    button.innerHTML = '';
    button.appendChild(icon(on ? 'eye' : 'eyeOff'));
    button.classList.toggle('off', !on);
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  /* ------------------------------------------------------------------ state */
  var page = null;
  var bp = {}, tp = {}, header = {};
  function runsOf() { return page.data.situations.filter(function (s) { return s.has_data; }); }
  function shownNames() { return runsOf().filter(function (s) { return s.role !== 'target' && page.visible[s.name] !== false; }).map(function (s) { return s.name; }); }
  function isOn(name) { return page.visible[name] !== false; }
  function nowT() { var tr = page.transport; return tr.t === null ? tr.tMax : tr.t; }
  function tabTitle() {
    var tab = (page.tabs || []).filter(function (t) { return t.id === page.activeTab; })[0];
    return tab ? tab.title : '';
  }
  function chipFor(name) {
    return Array.prototype.filter.call(document.querySelectorAll('[data-r4-chip]'), function (chip) {
      return chip.getAttribute('data-r4-chip') === name;
    })[0];
  }
  function setRun(name, show) {
    if (isOn(name) === show) return;
    var chip = chipFor(name);
    if (chip) chip.click();
  }
  // Rerun's Alt+click on a legend entry: this run alone; again: every run
  // (leaving it brings back the runs shown before, else every run)
  function solo(names) {
    var all = runsOf().filter(function (s) { return s.role !== 'target'; }).map(function (s) { return s.name; });
    var alone = all.every(function (name) { return (names.indexOf(name) !== -1) === isOn(name); });
    if (!alone) bp.beforeSolo = all.filter(isOn);
    var back = alone && bp.beforeSolo && bp.beforeSolo.length ? bp.beforeSolo : all;
    all.forEach(function (name) { setRun(name, alone ? back.indexOf(name) !== -1 : names.indexOf(name) !== -1); });
    if (alone) bp.beforeSolo = null;
  }

  /* ------------------------------------------------------------------ boundaries: drag, remember, double-click default */
  // axis 'x': drag right grows; 'y': drag up grows (a panel docked at the bottom); 'y-down': drag down grows
  function splitter(handle, key, read, write, fallback, axis) {
    var horizontal = axis === 'x', sign = axis === 'y' ? -1 : 1;
    var value = recall(key, null);
    write(value === null ? fallback() : value);
    handle.title = 'drag to resize · double-click for the default';
    handle.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      var start = horizontal ? event.clientX : event.clientY, from = read();
      handle.classList.add('dragging');
      document.body.classList.add(horizontal ? 'r4-resizing-x' : 'r4-resizing-y');
      try { handle.setPointerCapture(event.pointerId); } catch (error) {}
      function move(moveEvent) { write(from + ((horizontal ? moveEvent.clientX : moveEvent.clientY) - start) * sign); }
      function up() {
        handle.classList.remove('dragging');
        document.body.classList.remove('r4-resizing-x', 'r4-resizing-y');
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', up);
        handle.removeEventListener('pointercancel', up);
        store(key, read());
      }
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', up);
      handle.addEventListener('pointercancel', up);
    });
    handle.addEventListener('dblclick', function (event) { event.stopPropagation(); store(key, null); write(fallback()); });
  }

  /* ------------------------------------------------------------------ header: the primary action and the panel toggles */
  function decorateHeader() {
    var parts = RunView.headerParts();
    var host = parts.host;
    host.classList.add('r4-top');
    parts.rerun.classList.add('r4-primary');
    parts.rerun.innerHTML = '';
    parts.rerun.appendChild(icon('open'));
    el('span', '', parts.rerun, 'Open the same in Rerun');
    parts.rerun.title = 'Opens exactly this in the Rerun viewer: the runs shown here, the open question tab, and the time ' +
      '(a 0.2 s time selection around it: Rerun 0.40\'s blueprint has no cursor position), in the same questions layout';
    // left of the button, two lines: how many runs are shown, then what the button opens (or, once pressed, its answer)
    var open = el('div', 'r4-open', null);
    var info = el('div', 'r4-open-info', open);
    info.appendChild(parts.count);
    info.appendChild(parts.status);
    header.carries = el('div', 'r4-carries', info);
    open.appendChild(parts.rerun);
    host.appendChild(open);
    header.status = parts.status;
    parts.rerun.addEventListener('click', function () { header.sent = header.carries.textContent; });
    var toggles = el('div', 'r4-toggles', host);
    header.bpToggle = iconButton(toggles, 'panelLeft', 'Blueprint panel: show / hide (the runs and the views)');
    header.timeToggle = iconButton(toggles, 'panelBottom', 'Time panel: expand / collapse');
    header.bpToggle.onclick = function () { setBlueprintHidden(!bp.hidden, true); };
    header.timeToggle.onclick = function () { setTimeCollapsed(!tp.collapsed, true); };
  }
  function paintCarries() {
    if (!header.carries) return;
    var n = shownNames().length;
    header.carries.textContent = 'Rerun opens ' + (n === 1 ? 'it' : 'them') + ' on “' + tabTitle() + '” at t = ' + nowT().toFixed(2) + ' s';
    // the answer of the last press stays until what the button would send changes
    if (header.sent && header.sent !== header.carries.textContent && header.status && /ok|bad/.test(header.status.className)) {
      header.status.textContent = '';
      header.status.className = 'rv-status';
      header.sent = null;
    }
    header.carries.title = 'What Open the same in Rerun sends: the ' + n + ' run' + (n === 1 ? '' : 's') + ' shown (' +
      shownNames().join(', ') + '), the tab “' + tabTitle() + '”, and t = ' + nowT().toFixed(3) + ' s as a 0.2 s time selection ' +
      '(Rerun 0.40\'s blueprint has no cursor position). The recording opens paused, time panel expanded.';
  }

  /* ------------------------------------------------------------------ the blueprint panel (left) */
  function section(parent, name, hint) {
    var box = el('section', 'r4-bp-sec', parent);
    var head = el('div', 'r4-bp-h', box);
    el('span', 'r4-bp-hname', head, name);
    if (hint) el('span', 'r4-bp-hint', head, hint);
    return box;
  }
  function treeRow(parent, depth, iconName, label, sub, options) {
    options = options || {};
    var row = el('div', 'r4-row' + (options.cls ? ' ' + options.cls : ''), parent);
    row.style.paddingLeft = (6 + depth * 14) + 'px';
    var caret = el('span', 'r4-caret', row);
    if (options.caret) caret.appendChild(icon(options.open === false ? 'right' : 'down'));
    if (options.swatch) {
      var swatch = el('span', 'r4-swatch' + (options.dashed ? ' dashed' : ''), row);
      swatch.style.background = options.swatch;
      swatch.style.color = options.swatch;
    }
    if (iconName) row.appendChild(icon(iconName, 'r4-rico'));
    var text = el('span', 'r4-rlabel', row);
    el('span', 'r4-rname', text, label);
    if (sub) el('span', 'r4-rsub', text, sub);
    text.title = options.title || (label + (sub ? ' — ' + sub : ''));
    row.caret = caret;
    return row;
  }
  // a run's own words beside its entity name: its title without the name or the group it is listed under
  function runSub(sit) {
    var title = String(sit.title || '');
    if (sit.group && title.indexOf(sit.group + ' · ') === 0) return title.slice(sit.group.length + 3);
    if (title.indexOf(sit.name) === 0) return title.slice(sit.name.length).replace(/^\s*\(?/, '').replace(/\)\s*$/, '');
    return title === sit.name ? '' : title;
  }

  function buildBlueprint() {
    var host = document.getElementById('r4-bp');
    host.innerHTML = '';
    var data = page.data, meta = RunView.meta() || {};

    // SOURCES: the application id and the recording, as Rerun lists them
    var sources = section(host, 'Sources');
    treeRow(sources, 0, 'app', 'traj_compare', '', { caret: true, title: 'application id: every recording traj_compare writes' });
    var rec = treeRow(sources, 1, 'recording', data.name, '', { cls: 'r4-rec', title: data.title + (meta.deployment ? ' · ' + meta.deployment : '') });
    rec.setAttribute('aria-current', 'true');
    if (data.description) el('p', 'r4-bp-note', sources, data.description);

    // RUNS: /world/<run> with the eye that IS the selection
    var runs = section(host, 'Runs', 'eye = shown in every view');
    runs.classList.add('r4-runs');
    runs.querySelector('.r4-bp-h').title = 'Each run is the entity /world/<run> (and /positions/<joint>/<run>, /error/…/<run>, …) in ' +
      'the recording. Its eye shows or hides it in the 3D and every chart at once. Alt+click a run: show it alone (again: all).';
    var world = treeRow(runs, 0, 'entity', 'world/', 'the 3D and every chart', { caret: true, title: '/world: every run\'s robot and tool path; the same runs in every chart' });
    world.classList.add('r4-container');
    bp.rows = {};
    bp.groups = [];
    var sits = runsOf();
    var target = sits.filter(function (s) { return s.role === 'target'; });
    var others = sits.filter(function (s) { return s.role !== 'target'; });
    var names = [];
    others.forEach(function (s) { if (names.indexOf(s.group || '') === -1) names.push(s.group || ''); });
    var grouped = names.length > 1 && names.length < others.length;
    target.concat(grouped ? [] : others).forEach(function (sit) { runRow(runs, 1, sit); });
    if (grouped) {
      names.forEach(function (name) {
        var members = others.filter(function (s) { return (s.group || '') === name; });
        // a group is the bench's config (the recording's paths are flat /world/<run>): no entity icon; its name wraps
        var head = treeRow(runs, 1, null, name, '',
          { caret: true, swatch: members[0].color, cls: 'r4-group', title: name + ': ' + members.map(function (s) { return s.name; }).join(', ') });
        var count = el('span', 'r4-gcount', head);
        var eye = el('button', 'r4-eye', head);  // Rerun's place: the row's right end (always shown here: it is the selection)
        eye.type = 'button';
        var group = { name: name, head: head, eye: eye, count: count, members: members, rows: [], open: recall('group-open:' + name, true) };
        bp.groups.push(group);
        eye.title = 'Show or hide every run of ' + name;
        eye.onclick = function (event) {
          event.stopPropagation();
          var names = members.map(function (s) { return s.name; });
          if (event.altKey) { solo(names); return; }
          var any = members.some(function (s) { return isOn(s.name); });
          names.forEach(function (n) { setRun(n, !any); });
        };
        head.onclick = function (event) {
          if (event.altKey) { solo(members.map(function (s) { return s.name; })); return; }
          group.open = !group.open;
          store('group-open:' + name, group.open);
          paintGroups();
        };
        members.forEach(function (sit) { group.rows.push(runRow(runs, 2, sit)); });
      });
    }

    // BLUEPRINT: the questions layout's own tree (rerun_export._layout_questions)
    var blueprint = section(host, 'Blueprint', 'the questions layout');
    treeRow(blueprint, 0, 'horizontal', 'Viewport', '(Horizontal container, 2 : 5)', { caret: true });
    treeRow(blueprint, 1, 'vertical', 'Vertical container', '', { caret: true });
    var stageRow = treeRow(blueprint, 2, 'view3d', '3D: every run\'s robot and ' + data.tcp_frame + ' path', '', { cls: 'r4-click' });
    stageRow.onclick = function () { if (page.stageFolded) page.stage.fold.click(); };
    treeRow(blueprint, 1, 'tabs', 'Tab container', '', { caret: true });
    bp.tabRows = {};
    (page.tabs || []).forEach(function (tab) {
      var row = treeRow(blueprint, 2, 'vertical', tab.title, '', { cls: 'r4-click', title: tab.title + ' — ' + tab.heading });
      row.onclick = function () { TrajCompare.activateTab(page, tab.id, true); afterTabChange(); };
      bp.tabRows[tab.id] = row;
    });

    // what this viewer has beyond the blueprint: the Δ curves, the angle unit, reset zoom
    var options = el('details', 'r4-bp-sec r4-options', host);
    var summary = el('summary', 'r4-bp-h', options);
    el('span', 'r4-bp-hname', summary, 'View options');
    el('span', 'r4-bp-hint', summary, 'this viewer only');
    var controls = page.el.querySelector('.tc-controls');
    if (controls) {
      Array.prototype.slice.call(controls.children).forEach(function (group) {
        if (group.classList.contains('tc-situation-groups')) return;  // the runs' chips: the eyes above replace them
        options.appendChild(group);
      });
    }
    var foot = document.getElementById('rv-foot');
    if (foot) { host.appendChild(foot); foot.classList.add('r4-foot'); }
    paintRuns();
    paintGroups();
    paintTabRows();
  }
  function runRow(parent, depth, sit) {
    var row = treeRow(parent, depth, 'entity', sit.name + '/', runSub(sit),
      { swatch: sit.color, dashed: sit.role === 'target', cls: 'r4-run', title: '/world/' + sit.name + ' — ' + sit.title });
    var eye = el('button', 'r4-eye', row);
    eye.type = 'button';
    eye.setAttribute('data-rv-run', sit.name);  // the run toggle (check.cjs clicks it by the situation's name)
    eye.title = 'Show or hide ' + sit.title + ' in every view (Alt+click: show it alone)';
    eye.setAttribute('aria-label', eye.title);
    function toggle(event) {
      event.stopPropagation();
      if (event.altKey) solo([sit.name]); else setRun(sit.name, !isOn(sit.name));
    }
    eye.onclick = toggle;
    row.onclick = toggle;
    bp.rows[sit.name] = { row: row, eye: eye };
    return row;
  }
  function paintRuns() {
    Object.keys(bp.rows || {}).forEach(function (name) {
      var entry = bp.rows[name], on = isOn(name);
      paintEye(entry.eye, on);
      entry.row.classList.toggle('off', !on);
    });
    (bp.groups || []).forEach(function (group) {
      var on = group.members.filter(function (s) { return isOn(s.name); }).length;
      paintEye(group.eye, on > 0);
      group.eye.classList.toggle('some', on > 0 && on < group.members.length);
      group.head.classList.toggle('off', !on);
      group.count.textContent = on + '/' + group.members.length;
      group.count.title = on + ' of ' + group.members.length + ' run' + (group.members.length === 1 ? '' : 's') + ' of ' + group.name + ' shown';
    });
  }
  function paintGroups() {
    (bp.groups || []).forEach(function (group) {
      group.rows.forEach(function (row) { row.style.display = group.open ? '' : 'none'; });
      group.head.caret.innerHTML = '';
      group.head.caret.appendChild(icon(group.open ? 'down' : 'right'));
    });
  }
  function paintTabRows() {
    Object.keys(bp.tabRows || {}).forEach(function (id) { bp.tabRows[id].classList.toggle('active', id === page.activeTab); });
  }

  function setBlueprintWidth(width) {
    bp.width = clamp(Math.round(width), 170, Math.min(520, window.innerWidth * 0.4));
    document.getElementById('r4-bp').style.width = bp.width + 'px';
  }
  function setBlueprintHidden(hidden, remember) {
    bp.hidden = hidden;
    document.body.classList.toggle('r4-bp-hidden', hidden);
    if (header.bpToggle) header.bpToggle.classList.toggle('on', !hidden);
    if (header.bpToggle) header.bpToggle.setAttribute('aria-pressed', hidden ? 'false' : 'true');
    if (remember) store('bp-hidden', hidden);
    relayout();
  }

  /* ------------------------------------------------------------------ the stage: Rerun's spatial view */
  function decorateStage() {
    if (!page.stage) return;
    var stage = page.stage.el;
    var section = stage.querySelector('[data-tc-section="viewer3d"]');
    if (!section) return;
    var heading = section.querySelector('h3');
    var bar = viewBar('view3d', '3D: every run\'s robot and ' + page.data.tcp_frame + ' path', {
      onEye: function () { page.stage.fold.click(); relayout(); },
      onMax: function (button) { toggleStageMax(button); },
    });
    section.insertBefore(bar, section.firstChild);
    if (heading) heading.classList.add('r4-hidden-heading');
    var wrap = section.querySelector('.tc-3dwrap');
    var panel = section.querySelector('.tc-3dpanel');
    if (wrap && panel) {
      var props = el('details', 'r4-3dprops', wrap);
      var summary = el('summary', '', props);
      el('span', 'r4-props-name', summary, 'Visualizers and view options');
      el('span', 'r4-props-hint', summary, 'per run: path, points, robot, arrows · markers · Fit view');
      props.appendChild(panel);
      props.addEventListener('toggle', relayout);
      bp.props = props;
    }
    bp.stageBar = bar;
    page.canvasHeight = function () {
      var scroll = stage.querySelector('.tc-stage-scroll');
      var room = (scroll ? scroll.clientHeight : stage.clientHeight) - bar.offsetHeight - (bp.props ? bp.props.offsetHeight : 0) - 2;
      return Math.max(160, room);
    };
  }
  function toggleStageMax() {
    document.body.classList.toggle('r4-stage-max');
    relayout();
  }

  /* ------------------------------------------------------------------ the question tabs and their views */
  function decorateTabs() {
    var strip = page.el.querySelector('.tc-qtabs');
    if (!strip) return;
    Array.prototype.forEach.call(strip.querySelectorAll('.tc-qtab'), function (button) {
      button.insertBefore(icon('vertical', 'r4-tabico'), button.firstChild);
    });
    strip.addEventListener('click', function () { setTimeout(afterTabChange, 0); });
    strip.addEventListener('keydown', function () { setTimeout(afterTabChange, 0); });
    window.addEventListener('hashchange', function () { setTimeout(afterTabChange, 0); });
  }
  function afterTabChange() {
    paintTabRows();
    paintCarries();
  }

  function frameBlocks(panel, nodes, kind, title, cls) {
    nodes = nodes.filter(Boolean);
    if (!nodes.length) return null;
    var view = el('section', 'r4-view r4-view-' + kind + (cls ? ' ' + cls : ''));
    nodes[0].parentNode.insertBefore(view, nodes[0]);
    var body = el('div', 'r4-vbody');
    view.appendChild(viewBar(kind, title, { help: kind === 'bars' ? 'text' : kind, onEye: function (eye) { foldView(view, title, eye); } }));
    view.appendChild(body);
    nodes.forEach(function (node) { body.appendChild(node); });
    if (kind === 'text') {
      // the view's bottom edge drags (remembered): Rerun's row share between the scorecard and the charts below
      var edge = el('div', 'r4-split r4-split-view', view);
      edge.setAttribute('role', 'separator');
      edge.setAttribute('aria-orientation', 'horizontal');
      splitter(edge, 'view-height:' + title, function () { return body.offsetHeight; }, function (height) {
        body.style.maxHeight = clamp(Math.round(height), 90, Math.round(window.innerHeight * 0.8)) + 'px';
      }, function () { return Math.min(body.scrollHeight + 2, Math.round(window.innerHeight * 0.42)); }, 'y-down');
    }
    var eye = view.querySelector('.r4-vbar').eye;
    if (recall('fold:' + title, false)) foldView(view, title, eye, true);
    return view;
  }
  function foldView(view, title, eye, force) {
    var folded = force === true ? true : !view.classList.contains('r4-folded');
    view.classList.toggle('r4-folded', folded);
    paintEye(eye, !folded);
    store('fold:' + title, folded || null);
  }

  // the tab's own blocks as Rerun views (charts get theirs in onChart)
  function onPanel(pg, tab) {
    var panel = tab.panel;
    var minus = (page.data.reference_title || 'Target');
    if (tab.id === 'track') {
      frameBlocks(panel, [panel.querySelector('.tc-answer'), panel.querySelector('.tc-stats-mask'), panel.querySelector('.tc-tableblock')],
        'text', 'Scorecard: every run against the ' + minus + ', worst run first');
    }
    var rank = panel.querySelector('.tc-rank');
    if (rank) {
      frameBlocks(panel, [rank], 'bars', tab.id === 'torque'
        ? 'Feedback share of the command per joint, worst first [%]'
        : 'All joints: RMS joint error of each joint\'s worst run, ' + minus + ' − run, worst first [°]');
    }
    // several plot sections in one tab: Rerun's nested tabs (one at a time), as its signals tab
    var toggles = tab.sections.filter(function (section) { return section.toggle; });
    var chips = panel.querySelector('.tc-panel-chips');
    if (toggles.length && chips) {
      var nested = el('nav', 'r4-nested', null);
      chips.parentNode.insertBefore(nested, chips);
      chips.classList.add('r4-hidden-chips');
      // the pick is remembered in R4's own key: the report-wide section prefs are shared with every other page of it
      var picked = recall('nested:' + tab.id, null);
      var first = toggles.filter(function (section) { return section.def.id === picked; })[0] ||
        toggles.filter(function (section) { return section.on; })[0] || toggles[0];
      var buttons = toggles.map(function (section) {
        var button = el('button', 'r4-ntab', nested);
        button.type = 'button';
        button.appendChild(icon('vertical', 'r4-tabico'));
        var label = el('span', '', button, section.chip ? section.chip.textContent : section.def.id);
        button.title = label.textContent;
        button.onclick = function () { only(section); store('nested:' + tab.id, section.def.id); };
        return { section: section, button: button };
      });
      function only(chosen) {
        TrajCompare.setSection(page, chosen, true, false);
        toggles.forEach(function (section) { if (section !== chosen && section.on) TrajCompare.setSection(page, section, false, false); });
        buttons.forEach(function (entry) {
          entry.button.classList.toggle('active', entry.section === chosen);
          entry.button.setAttribute('aria-selected', entry.section === chosen ? 'true' : 'false');
        });
        relayout();
      }
      only(first);
    }
    Array.prototype.forEach.call(panel.querySelectorAll('.tc-section > h3'), function (heading) {
      heading.classList.add('r4-container-head');
      heading.insertBefore(icon('vertical', 'r4-rico'), heading.firstChild);
    });
  }

  // Rerun's hover tooltip on a time series: the time, then each shown series' colour, name and value (while dragging the
  // time, the pointer IS the time cursor, so it reads every run at the playhead)
  var tip = null;
  function hoverTip(chart) {
    var u = chart.u;
    if (!u || !u.hooks) return;
    (u.hooks.setCursor = u.hooks.setCursor || []).push(function () {
      if (!tip) { tip = el('div', 'r4-tip', document.body); tip.setAttribute('role', 'status'); }
      var index = u.cursor.idx;
      if (index == null || u.cursor.left == null || u.cursor.left < 0 || page.hoverChart !== chart) { tip.style.display = 'none'; return; }
      tip.innerHTML = '';
      el('div', 'r4-tip-t', tip, TrajCompare.relativeTime(Number(page.data.plot_t[index].toFixed(3))));
      var unit = chart.titleEl.querySelector('.unit');
      unit = unit ? unit.textContent.replace(/[\[\]]/g, '') : '';
      var rows = 0;
      u.series.forEach(function (series, i) {
        if (!i || !series.show) return;
        var value = u.data[i][index];
        if (value == null || !isFinite(value)) return;
        var row = el('div', 'r4-tip-row', tip);
        var dot = el('span', 'r4-tip-dot', row);
        dot.style.background = typeof series.stroke === 'function' ? series.stroke(u, i) : series.stroke;
        el('span', 'r4-tip-name', row, series.label);
        el('span', 'r4-tip-v', row, Number(value.toPrecision(3)) + (unit === '°' ? '°' : unit ? ' ' + unit : ''));
        rows++;
      });
      if (!rows) { tip.style.display = 'none'; return; }
      tip.style.display = 'block';
      var box = u.over.getBoundingClientRect();
      var x = box.left + u.cursor.left + 16, y = box.top + 8;
      if (x + tip.offsetWidth > window.innerWidth - 8) x = box.left + u.cursor.left - tip.offsetWidth - 16;
      tip.style.left = Math.max(8, x) + 'px';
      tip.style.top = Math.min(window.innerHeight - tip.offsetHeight - 8, y) + 'px';
    });
    u.over.addEventListener('mouseleave', function () { if (tip) tip.style.display = 'none'; });
  }

  // every chart: Rerun's view title bar, its fold and maximize
  function onChart(pg, chart) {
    var card = chart.card;
    if (card.querySelector('.r4-vbar')) return;
    var title = chart.spec.title;
    var bar = viewBar('series', chart.titleEl, {
      onEye: function (eye) {
        var folded = !card.classList.contains('r4-folded');
        card.classList.toggle('r4-folded', folded);
        paintEye(eye, !folded);
        store('fold:' + title, folded || null);
        if (!folded) chart.resize();
      },
      onMax: function () { maximize(chart); },
    });
    card.insertBefore(bar, card.firstChild);
    card.classList.add('r4-view');
    hoverTip(chart);
    if (recall('fold:' + title, false)) { card.classList.add('r4-folded'); paintEye(bar.eye, false); }
  }
  var maxed = null;
  function maximize(chart) {
    if (maxed) {
      var was = maxed;
      was.card.classList.remove('r4-max');
      was.card.style.cssText = was.card.style.display === 'none' ? 'display:none' : '';
      was.height = null;
      maxed = null;
      was.resize();
      if (was === chart) return;
    }
    var column = page.el.querySelector('.tc-qcol');
    var box = column.getBoundingClientRect();
    chart.card.classList.add('r4-max');
    chart.card.style.left = box.left + 'px';
    chart.card.style.top = box.top + 'px';
    chart.card.style.width = box.width + 'px';
    chart.card.style.height = box.height + 'px';
    chart.height = Math.max(160, box.height - 70);
    maxed = chart;
    chart.resize();
  }

  /* ------------------------------------------------------------------ the time panel (bottom) */
  function niceStep(span, px) {
    var raw = span / Math.max(1, px / 80);
    var steps = [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60];
    for (var i = 0; i < steps.length; i++) if (steps[i] >= raw) return steps[i];
    return steps[steps.length - 1];
  }
  function fmtField(t) { return (t < 0 ? '−' : '+') + Math.abs(t).toFixed(3) + 's'; }

  function buildTimePanel() {
    var host = document.getElementById('r4-time');
    host.innerHTML = '';
    var transport = page.transport;
    tp.host = host;
    tp.split = el('div', 'r4-split r4-split-time', host);
    tp.split.setAttribute('role', 'separator');
    tp.split.setAttribute('aria-orientation', 'horizontal');
    var bar = el('div', 'r4-time-bar', host);
    tp.play = iconButton(bar, 'play', 'Play / pause (Space)', 'r4-tbtn');
    tp.play.onclick = function () { transport.toggle(); };
    var back = iconButton(bar, 'stepBack', 'Step back one sample (←)', 'r4-tbtn');
    back.onclick = function () { transport.stepBy(-1); };
    var fwd = iconButton(bar, 'stepFwd', 'Step forward one sample (→)', 'r4-tbtn');
    fwd.onclick = function () { transport.stepBy(1); };
    tp.loop = iconButton(bar, 'loop', '', 'r4-tbtn');
    tp.loop.onclick = function () {
      var order = transport.selection ? ['off', 'selection', 'all'] : ['off', 'all'];
      transport.loop = order[(order.indexOf(transport.loop) + 1) % order.length];
      paintLoop();
    };
    var timeline = el('label', 'r4-tsel', bar);
    var tl = el('select', '', timeline);
    el('option', '', tl, 't');
    timeline.title = 'Timeline t: the run\'s clock, seconds from the target\'s start (the recording\'s one duration timeline)';
    var speedBox = el('label', 'r4-tsel r4-speed', bar);
    var speed = el('select', '', speedBox);
    [0.25, 0.5, 1, 2, 4].forEach(function (value) {
      var option = el('option', '', speed, value.toFixed(2) + 'x');
      option.value = String(value);
    });
    speed.value = String(recall('speed', 1));
    transport.speed = parseFloat(speed.value) || 1;
    speedBox.title = 'Playback speed';
    speed.onchange = function () { transport.speed = parseFloat(speed.value) || 1; store('speed', transport.speed); };
    tp.field = el('input', 'r4-tfield', bar);
    tp.field.type = 'text';
    tp.field.spellcheck = false;
    tp.field.title = 'The current time: type one (in seconds) and press Enter';
    tp.field.setAttribute('aria-label', 'Current time in seconds');
    tp.field.addEventListener('focus', function () { tp.field.select(); });
    tp.field.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        var value = parseFloat(String(tp.field.value).replace(/[+s\s]/g, '').replace('−', '-'));
        if (isFinite(value)) { transport.pause(); transport.setScrub(value); }
        tp.field.blur();
      } else if (event.key === 'Escape') { tp.field.blur(); }
      event.stopPropagation();
    });
    tp.field.addEventListener('blur', paintTime);
    // collapsed: Rerun's one-row scrubber
    tp.mini = el('div', 'r4-mini', bar);
    tp.mini.setAttribute('data-rv-slider', '');
    tp.mini.title = 'Drag to move the time';
    tp.miniTrack = el('div', 'r4-mini-track', tp.mini);
    tp.miniCursor = el('div', 'r4-mini-cursor', tp.mini);
    el('div', 'r4-mini-head', tp.miniCursor);
    scrubOn(tp.mini, tp.mini);
    tp.hint = el('span', 'r4-time-hint', bar, 'drag on any chart to move the time everywhere');
    el('span', 'r4-flex', bar);
    helpButton(bar, 'time');
    tp.fold = iconButton(bar, 'panelBottom', 'Expand / collapse the time panel', 'r4-tbtn');
    tp.fold.onclick = function () { setTimeCollapsed(!tp.collapsed, true); };

    var body = el('div', 'r4-time-body', host);
    tp.body = body;
    var streams = el('div', 'r4-streams', body);
    var sHead = el('div', 'r4-streams-h', streams);
    el('span', '', sHead, 'Streams');
    sHead.appendChild(icon('search', 'r4-dim'));
    tp.streamRows = el('div', 'r4-streams-rows', streams);
    tp.split2 = el('div', 'r4-split r4-split-streams', body);
    var area = el('div', 'r4-tl', body);
    area.setAttribute('data-rv-slider', '');
    tp.area = area;
    tp.ruler = el('div', 'r4-ruler', area);
    tp.ruler.title = 'Drag the time scale to select a time segment (loop it with the loop button) · click to move the time · double-click: remove the selection';
    tp.lanes = el('div', 'r4-lanes', area);
    tp.sel = el('div', 'r4-tsel-band', area);
    tp.selTip = el('div', 'r4-tsel-tip', area);
    tp.cursor = el('div', 'r4-cursor', area);
    el('div', 'r4-cursor-head', tp.cursor);
    tp.cursor.title = 'The time cursor: drag it';

    // streams: one row per run entity (/world/<run>), the other entity groups in one line
    tp.rows = {};
    var sits = runsOf();
    sits.forEach(function (sit) {
      var label = el('div', 'r4-srow', tp.streamRows);
      label.appendChild(icon('entity', 'r4-rico'));
      var name = el('span', 'r4-sname', label, 'world/' + sit.name + '/');
      label.title = '/world/' + sit.name + ' — ' + sit.title;
      name.style.color = '';
      var lane = el('div', 'r4-lane', tp.lanes);
      var fill = el('div', 'r4-lane-fill' + (sit.role === 'target' ? ' dashed' : ''), lane);
      fill.style.background = sit.color;
      fill.style.color = sit.color;
      tp.rows[sit.name] = { label: label, lane: lane, fill: fill, sit: sit };
    });
    var more = el('div', 'r4-srow r4-smore', tp.streamRows);
    more.appendChild(icon('entity', 'r4-rico'));
    el('span', 'r4-sname', more, 'positions/ velocities/ error/ effort/ tcp/ worst/ …');
    more.title = 'The recording\'s other entities (every joint signal and error, per run): in this page they are the charts';
    el('div', 'r4-lane', tp.lanes);
    tp.streamRows.addEventListener('scroll', function () { tp.lanes.scrollTop = tp.streamRows.scrollTop; });
    tp.lanes.addEventListener('scroll', function () { tp.streamRows.scrollTop = tp.lanes.scrollTop; });

    // gestures: drag the cursor or the streams = move the time; drag the time scale = select a segment
    scrubOn(tp.lanes, area);
    scrubOn(tp.cursor, area);
    selectOn(tp.ruler, area);
    tp.ruler.addEventListener('dblclick', function () { setSelection(null); });
    // as Rerun: hovering the selection shows its start, stop and length; its context menu removes it
    function inSelection(event) {
      var span = page.transport.selection;
      if (!span) return false;
      var t = timeAtX(area.getBoundingClientRect(), event.clientX);
      return t >= span.min && t <= span.max;
    }
    area.addEventListener('mousemove', function (event) {
      if (event.buttons) return;
      if (inSelection(event)) paintSelection(true); else tp.selTip.style.display = 'none';
    });
    area.addEventListener('mouseleave', function () { tp.selTip.style.display = 'none'; });
    area.addEventListener('contextmenu', function (event) { if (inSelection(event)) { event.preventDefault(); setSelection(null); } });

    splitter(tp.split, 'time-height', function () { return tp.height; }, setTimeHeight, function () { return 170; }, 'y');
    splitter(tp.split2, 'streams-width', function () { return tp.streamsWidth; }, setStreamsWidth, function () { return 220; }, 'x');
    setTimeCollapsed(!!recall('time-collapsed', false), false);
    transport.onChange(paintTime);
    paintLoop();
    paintStreams();
  }
  function setTimeHeight(height) {
    tp.height = clamp(Math.round(height), 96, Math.round(window.innerHeight * 0.6));
    if (!tp.collapsed) tp.host.style.height = tp.height + 'px';
    relayout();
  }
  function setStreamsWidth(width) {
    tp.streamsWidth = clamp(Math.round(width), 120, 420);
    tp.body.style.gridTemplateColumns = tp.streamsWidth + 'px 6px minmax(0, 1fr)';
    paintTime();
  }
  function setTimeCollapsed(collapsed, remember) {
    tp.collapsed = collapsed;
    tp.host.classList.toggle('collapsed', collapsed);
    tp.host.style.height = collapsed ? '' : tp.height + 'px';
    if (header.timeToggle) { header.timeToggle.classList.toggle('on', !collapsed); header.timeToggle.setAttribute('aria-pressed', collapsed ? 'false' : 'true'); }
    if (remember) store('time-collapsed', collapsed);
    relayout();
  }
  function timeAtX(box, clientX) {
    var tr = page.transport, grid = page.data.plot_t;
    var f = clamp((clientX - box.left) / Math.max(1, box.width), 0, 1);
    return grid[TrajCompare.nearestIndex(grid, tr.tMin + f * (tr.tMax - tr.tMin))];
  }
  function scrubOn(target, frameEl) {
    target.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      var box = (frameEl === tp.mini ? tp.miniTrack : frameEl).getBoundingClientRect();
      page.transport.pause();
      document.body.classList.add('rv-scrubbing');
      page.transport.setScrub(timeAtX(box, event.clientX));
      try { target.setPointerCapture(event.pointerId); } catch (error) {}
      function move(moveEvent) { page.transport.setScrub(timeAtX(box, moveEvent.clientX)); }
      function up() {
        document.body.classList.remove('rv-scrubbing');
        target.removeEventListener('pointermove', move);
        target.removeEventListener('pointerup', up);
        target.removeEventListener('pointercancel', up);
      }
      target.addEventListener('pointermove', move);
      target.addEventListener('pointerup', up);
      target.addEventListener('pointercancel', up);
    });
  }
  function selectOn(target, frameEl) {
    target.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      var box = frameEl.getBoundingClientRect();
      var start = event.clientX, a = timeAtX(box, start), moved = false;
      try { target.setPointerCapture(event.pointerId); } catch (error) {}
      function move(moveEvent) {
        if (!moved && Math.abs(moveEvent.clientX - start) < 4) return;
        moved = true;
        var b = timeAtX(box, moveEvent.clientX);
        setSelection({ min: Math.min(a, b), max: Math.max(a, b) }, true);
      }
      function up(upEvent) {
        target.removeEventListener('pointermove', move);
        target.removeEventListener('pointerup', up);
        target.removeEventListener('pointercancel', up);
        tp.selTip.style.display = 'none';
        if (!moved) { page.transport.pause(); page.transport.setScrub(timeAtX(box, upEvent.clientX)); }
        else if (page.transport.selection) { page.transport.loop = 'selection'; paintLoop(); }  // as Rerun: a selection turns its loop on
      }
      target.addEventListener('pointermove', move);
      target.addEventListener('pointerup', up);
      target.addEventListener('pointercancel', up);
    });
  }
  function setSelection(span, tip) {
    var tr = page.transport;
    tr.selection = span && span.max - span.min > 0 ? span : null;
    if (!tr.selection && tr.loop === 'selection') tr.loop = 'off';
    paintSelection(tip);
    paintLoop();
  }
  function paintSelection(tip) {
    var tr = page.transport, span = tr.selection;
    var width = tp.area.clientWidth || 1;
    function x(t) { return (t - tr.tMin) / (tr.tMax - tr.tMin) * width; }
    tp.sel.style.display = span ? 'block' : 'none';
    if (!span) { tp.selTip.style.display = 'none'; return; }
    tp.sel.style.left = x(span.min) + 'px';
    tp.sel.style.width = Math.max(1, x(span.max) - x(span.min)) + 'px';
    tp.sel.title = 'Time selection ' + fmtField(span.min) + ' to ' + fmtField(span.max) + ' (' + (span.max - span.min).toFixed(3) +
      ' s). Right-click or double-click the time scale to remove it.';
    if (tip) {
      tp.selTip.style.display = 'block';
      tp.selTip.innerHTML = '';
      [['Start', fmtField(span.min)], ['Stop', fmtField(span.max)], ['Length', (span.max - span.min).toFixed(3) + 's']].forEach(function (pair) {
        var row = el('div', '', tp.selTip);
        el('span', 'k', row, pair[0]);
        el('span', 'v', row, pair[1]);
      });
      tp.selTip.style.left = clamp(x(span.max) + 6, 0, width - 140) + 'px';
    }
  }
  function paintLoop() {
    var mode = page.transport.loop;
    tp.loop.classList.toggle('on', mode !== 'off');
    tp.loop.classList.toggle('all', mode === 'all');
    tp.loop.title = { off: 'Loop: off (click: loop ' + (page.transport.selection ? 'the time selection' : 'the whole run') + ')',
      selection: 'Loop: the time selection (click: the whole run)', all: 'Loop: the whole run (click: off)' }[mode];
    tp.loop.setAttribute('aria-label', tp.loop.title);
  }
  function paintTime() {
    var tr = page.transport;
    if (!tp.area) return;
    var t = nowT();
    var f = (t - tr.tMin) / Math.max(1e-9, tr.tMax - tr.tMin);
    tp.cursor.style.left = (f * 100) + '%';
    tp.miniCursor.style.left = (f * 100) + '%';
    tp.area.setAttribute('data-rv-time', String(t));
    tp.mini.setAttribute('data-rv-time', String(t));
    if (document.activeElement !== tp.field) tp.field.value = fmtField(t);
    tp.play.innerHTML = '';
    tp.play.appendChild(icon(tr.playing ? 'pause' : 'play'));
    tp.play.classList.toggle('on', tr.playing);
    paintCarries();
  }
  function paintRuler() {
    var tr = page.transport;
    var width = tp.area.clientWidth;
    if (!width) return;
    tp.ruler.innerHTML = '';
    var span = tr.tMax - tr.tMin;
    var step = niceStep(span, width);
    var minor = step / 5;
    var first = Math.ceil(tr.tMin / minor - 1e-9) * minor;
    for (var t = first; t <= tr.tMax + 1e-9; t += minor) {
      var major = Math.abs(t / step - Math.round(t / step)) < 1e-6;
      var tick = el('span', 'r4-tick' + (major ? ' major' : ''), tp.ruler);
      tick.style.left = ((t - tr.tMin) / span * 100) + '%';
      if (major) el('span', 'r4-tlabel', tick, TrajCompare.relativeTime(Number(t.toFixed(6))));
    }
    paintSelection(false);
  }
  function paintStreams() {
    Object.keys(tp.rows || {}).forEach(function (name) {
      var row = tp.rows[name], on = isOn(name);
      row.label.classList.toggle('off', !on);
      row.lane.classList.toggle('off', !on);
    });
  }

  /* ------------------------------------------------------------------ layout */
  var relayoutQueued = false;
  function relayout() {
    if (relayoutQueued) return;
    relayoutQueued = true;
    requestAnimationFrame(function () {
      relayoutQueued = false;
      if (!page) return;
      if (page.viewer3d && !page.stageFolded) page.viewer3d.setActive(true);
      var tab = (page.tabs || []).filter(function (t) { return t.id === page.activeTab; })[0];
      if (tab) page.charts.forEach(function (chart) { if (tab.panel.contains(chart.card) && chart.card.offsetParent) chart.resize(); });
      if (tp.area) { paintRuler(); paintTime(); }
    });
  }

  function onKey(event) {
    var tag = (event.target && event.target.tagName) || '';
    if (/INPUT|SELECT|TEXTAREA/.test(tag)) return;
    if (event.key === 'Escape') {
      if (maxed) maximize(maxed);
      else if (document.body.classList.contains('r4-stage-max')) toggleStageMax();
      else if (page.transport.selection) setSelection(null);
      return;
    }
    if (event.key === ' ' && tag !== 'BUTTON') { event.preventDefault(); page.transport.toggle(); }
    else if (event.key === 'ArrowLeft' && !/BUTTON/.test(tag)) { event.preventDefault(); page.transport.stepBy(-1); }
    else if (event.key === 'ArrowRight' && !/BUTTON/.test(tag)) { event.preventDefault(); page.transport.stepBy(1); }
  }

  window.RunViewVariant = {
    beforeBoot: function () {
      TrajCompare.onChart(function (pg, chart) { if (pg.index === 0) onChart(pg, chart); });
      TrajCompare.onPanel(function (pg, tab) { if (pg.index === 0) { page = pg; onPanel(pg, tab); } });
    },
    afterBoot: function () {
      page = TrajCompare.state.pages[0];
      if (!page || !page.transport) return;
      document.body.classList.add('r4-ready');
      decorateHeader();
      buildBlueprint();
      decorateStage();
      decorateTabs();
      buildTimePanel();
      splitter(document.getElementById('r4-split-bp'), 'bp-width', function () { return bp.width; }, setBlueprintWidth, function () { return 240; }, 'x');
      setBlueprintHidden(!!recall('bp-hidden', false), false);
      window.addEventListener('rv-selection', function () { paintRuns(); paintStreams(); paintCarries(); });
      window.addEventListener('resize', relayout);
      document.addEventListener('keydown', onKey);
      if (typeof ResizeObserver !== 'undefined') new ResizeObserver(relayout).observe(document.getElementById('r4-viewport'));
      paintCarries();
      relayout();
    },
  };
})();
