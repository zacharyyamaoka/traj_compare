/* traj_compare — 3D path viewer (three.js, z-up).
 *
 * Per situation, one row: a bulk visibility eye plus a full-word multi-select
 * of what to draw for that run — path, sampled points, pose frames, tool z
 * axis, its robot model, and (candidates only) the position error to the
 * target's same-time pose and the orientation error between them. The model is
 * one more item in that dropdown because it is one more view of the same
 * trajectory, drawn in the same color: target vs sim vs real rigs overlay.
 *
 * Time-aware: the page's time (the lane, a plot drag or hover) is the playhead.
 * The runs draw their recent history, fading over "Trail decay" seconds; the
 * target draws the same history plus "Look-ahead" seconds ahead of the
 * playhead; each visible model stands at that instant.
 *
 * Line styles: three proposals, switched by a small drop-down pinned bottom
 * right of the page (Zach's rule for gated variants), remembered:
 *   A "Ghost + comet"   — the target a thick translucent tube, each run a solid
 *                          comet in its colour, error arrows coloured by size;
 *   B "Error ribbon"    — a ribbon from the target to the run, coloured by the
 *                          position error, the orientation error at the instant;
 *   C "Focused instant" — the whole route faint, the window around the playhead
 *                          bright, one big labelled arrow (mm) and arc (°) now.
 * WHY (Zach 2026-11-25, traj compare 3D viewer feedback: "it's not completely
 * clear to me, like the errors and the differences. It's about the line
 * stylings used"): sub-millimetre errors on a metre-long route vanish at true
 * scale, so every style draws the run at the target plus ×N its error (FEA's
 * deformation scale, the same 1-2-5 factor rule as the Rerun magnifier,
 * rerun_target_run.MAGNIFY_SHARE), colours the error by size on a stated scale,
 * and limits the drawing to a window around the playhead instead of a hairball
 * of the whole route. No dashed lines: width, opacity and colour carry
 * target vs run.
 *
 * Orientation gizmo: three.js' own ViewHelper (examples/jsm/helpers), drawn
 * bottom-right; click an axis ball to fly to that view.
 */

var Viewer3D = (function () {
  'use strict';

  var CANVAS_HEIGHT = 540;
  // a neutral scene colour in the page's theme (TrajCompare.ink, plots.js: unchanged on the light page)
  function inkNumber(value) {
    var tc = window.TrajCompare;
    if (!tc || !tc.ink) return value;
    return parseInt(tc.ink('#' + ('00000' + value.toString(16)).slice(-6)).slice(1, 7), 16);
  }
  var GIZMO_SIZE = 128;   // ViewHelper's fixed `dim`
  var ARC_STEPS = 24;

  var EYE_OPEN =
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/></svg>';
  var EYE_CLOSED =
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><line x1="4" y1="20" x2="20" y2="4"/></svg>';

  // all:  offered for every situation (otherwise: candidates only, since it
  //       is measured against the target)
  // robot: offered only when this situation carries a model
  // WHY plain words (Zach 2026-11-25, traj compare 3D viewer feedback): "Arrows → target" and "Z rotation arcs" said
  // how they are drawn, not what they show
  var ELEMENTS = [
    { id: 'path', label: 'Path', all: true, on: true },
    { id: 'points', label: 'Points', all: true, on: false },
    { id: 'robot', label: 'Robot model', all: true, on: true, robot: true },
    { id: 'frames', label: 'Pose frames', all: true, on: false },
    { id: 'zvec', label: 'Tool Z axis', all: true, on: false },
    { id: 'diff', label: 'Position error arrow', all: false, on: true },
    { id: 'zarc', label: 'Orientation error arc', all: false, on: true },
  ];

  /* The three line-style proposals; A is the default. */
  var STYLES = [
    { id: 'A', name: 'Ghost + comet' },
    { id: 'B', name: 'Error ribbon' },
    { id: 'C', name: 'Focused instant' },
  ];
  var STYLE_KEY = 'traj-compare:3d-style';

  function recallStyle() {
    try {
      var value = localStorage.getItem(STYLE_KEY);
      return STYLES.some(function (style) { return style.id === value; }) ? value : 'A';
    } catch (error) { return 'A'; }
  }
  function storeStyle(value) {
    try { localStorage.setItem(STYLE_KEY, value); } catch (error) { /* a file:// page may refuse storage */ }
  }

  var viewers = [];
  var currentStyle = recallStyle();

  // One switch per document, whatever number of 3D views the report holds.
  function ensureStylePicker() {
    if (document.querySelector('[data-tc-style-pick]')) return;
    var box = document.createElement('label');
    box.className = 'tc-style-pick';
    box.setAttribute('data-tc-style-pick', '');
    box.title = '3D view line style: three proposals to compare (temporary)';
    box.appendChild(document.createTextNode('3D style'));
    var select = document.createElement('select');
    STYLES.forEach(function (style) {
      var option = document.createElement('option');
      option.value = style.id;
      option.textContent = style.id + ' · ' + style.name;
      select.appendChild(option);
    });
    select.value = currentStyle;
    select.addEventListener('change', function () { setStyleEverywhere(select.value); });
    box.appendChild(select);
    document.body.appendChild(box);
  }

  function setStyleEverywhere(value) {
    if (!STYLES.some(function (style) { return style.id === value; })) value = 'A';
    currentStyle = value;
    storeStyle(value);
    var select = document.querySelector('[data-tc-style-pick] select');
    if (select && select.value !== value) select.value = value;
    viewers.forEach(function (viewer) { viewer.setStyle(value); });
  }

  /* An element's words on this page and style. WHY (arm_motion_bench, 2026-11-20): in a sim → real pair the error is
     measured against the sim run (Comparison.reference_kind "run"), so it says so instead of the target. */
  function elementLabel(element, page, style) {
    var data = page && page.data;
    var label = element.label;
    if (element.id === 'diff' && style === 'B') label = 'Position error ribbon';
    if ((element.id === 'diff' || element.id === 'zarc') && data && data.reference_kind === 'run') {
      label += ' (vs ' + data.reference_title + ')';
    }
    return label;
  }

  // Colour ramp for an error's size, 0 → the largest error on the page: green, amber, red, plum (no blue: the runs are).
  var RAMP = [[0.0, [0.11, 0.62, 0.47]], [0.4, [0.90, 0.67, 0.01]], [0.75, [0.84, 0.19, 0.12]], [1.0, [0.48, 0.0, 0.47]]];
  function rampRgb(fraction) {
    var f = Math.max(0, Math.min(1, fraction || 0));
    for (var k = 1; k < RAMP.length; k++) {
      if (f <= RAMP[k][0]) {
        var a = RAMP[k - 1], b = RAMP[k];
        var w = (f - a[0]) / (b[0] - a[0]);
        return [a[1][0] + (b[1][0] - a[1][0]) * w, a[1][1] + (b[1][1] - a[1][1]) * w, a[1][2] + (b[1][2] - a[1][2]) * w];
      }
    }
    return RAMP[RAMP.length - 1][1];
  }
  function rampCss() {
    return 'linear-gradient(90deg,' + RAMP.map(function (stop) {
      return 'rgb(' + stop[1].map(function (c) { return Math.round(c * 255); }).join(',') + ') ' + stop[0] * 100 + '%';
    }).join(',') + ')';
  }

  // The 1-2-5 number nearest ``value`` in log space (rerun_target_run._nice_factor), at least 1.
  function niceFactor(value) {
    if (!isFinite(value) || value <= 1) return 1;
    var exponent = Math.pow(10, Math.floor(Math.log10(value)));
    var best = 1, bestGap = Infinity;
    [1, 2, 5, 10].forEach(function (m) {
      var gap = Math.abs(Math.log(m * exponent / value));
      if (gap < bestGap) { bestGap = gap; best = m * exponent; }
    });
    return Math.round(best);
  }
  var MAGNIFY_SHARE = 0.35;   // rerun_target_run.MAGNIFY_SHARE: the drawn peak error, as a share of the path's radius
  var ARC_TARGET_DEG = 60;    // the largest orientation error is drawn this wide
  var SAME_POSE_M = 1e-6;

  // the slider steps; Infinity draws everything
  var DECAY_STEPS = [0.5, 1, 2, 3, 5, 10, 20, 30, 60, Infinity];
  var LOOK_STEPS = [0, 0.5, 1, 2, 3, 5, 10, 20, Infinity];
  var MAGNIFY_STEPS = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];  // 0: auto
  var MAX_WINDOW_POINTS = 1600;   // a window's line is decimated to at most this many samples

  function secondsText(value, zeroWord) {
    if (value === Infinity) return 'full';
    if (value === 0) return zeroWord;
    return value + ' s';
  }

  function mmText(metres) {
    var mm = metres * 1000;
    if (mm >= 100) return mm.toFixed(0) + ' mm';
    if (mm >= 10) return mm.toFixed(1) + ' mm';
    if (mm >= 1) return mm.toFixed(2) + ' mm';
    return mm.toFixed(3) + ' mm';
  }
  function degText(radians) {
    var deg = radians * 180 / Math.PI;
    if (deg >= 10) return deg.toFixed(1) + '°';
    if (deg >= 1) return deg.toFixed(2) + '°';
    return deg.toFixed(3) + '°';
  }

  function availableElements(sit) {
    return ELEMENTS.filter(function (element) {
      if (element.robot) return !!sit.robot_track;
      return element.all || sit.three.tp;
    });
  }

  function el(tag, className, parent, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function countLeq(sorted, value) {
    var lo = 0, hi = sorted.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (sorted[mid] <= value) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  function zAxisOf(quat) { // [w,x,y,z] -> rotated +Z column
    var w = quat[0], x = quat[1], y = quat[2], z = quat[3];
    return [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)];
  }

  function columnsOf(quat) { // x,y,z axis columns of R
    var w = quat[0], x = quat[1], y = quat[2], z = quat[3];
    return [
      [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)],
      [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)],
      [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)],
    ];
  }

  function decodeTris(b64) {
    var raw = atob(b64);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return new Float32Array(bytes.buffer);
  }

  /* ``options.height(width)``: the canvas height for a canvas box ``width`` px wide (default CANVAS_HEIGHT).
     WHY (Zach 2026-11-19, traj compare view feedback: keep the 3D always visible): in the run view's stage the
     canvas sits in a pane a third of the page wide, where a fixed 540 px would push the scrubber off screen. */
  function create(page, container, options) {
    var prefs = TrajCompare.prefs();
    var heightFor = (options && options.height) || function () { return CANVAS_HEIGHT; };
    var canvasHeight = CANVAS_HEIGHT;
    var situations = page.data.situations.filter(function (sit) { return sit.three; });
    if (!situations.length) {
      el('div', 'tc-empty', container, 'no cartesian data to draw');
      return { setSituationVisible: function () {}, setActive: function () {} };
    }

    var wrap = el('div', 'tc-3dwrap', container);
    var canvasBox = el('div', 'tc-3dcanvasbox', wrap);
    var canvas = document.createElement('canvas');
    canvasBox.appendChild(canvas);
    var panel = el('div', 'tc-3dpanel', wrap);

    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.autoClear = false;
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(inkNumber(0xfcfcfb));
    var camera = new THREE.PerspectiveCamera(50, 1.6, 0.005, 200);
    camera.up.set(0, 0, 1);

    var grid = new THREE.GridHelper(2, 20, inkNumber(0xd0cfc9), inkNumber(0xe6e5e0));
    grid.rotation.x = Math.PI / 2; // robotics z-up: grid on the XY plane
    scene.add(grid);
    scene.add(new THREE.AxesHelper(0.15));

    var dirty = true;
    var active = false;

    /* ---------------- bounds + camera ---------------- */

    var bounds = new THREE.Box3();
    situations.forEach(function (sit) {
      sit.three.p.forEach(function (point) {
        bounds.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
      });
      // Robot links sweep well beyond the TCP paths; sample their track so
      // the default fit shows the whole arm, not a cropped torso.
      var track = sit.robot_track;
      if (track) {
        [0, track.p.length - 1, track.p.length >> 1].forEach(function (sample) {
          track.p[sample].forEach(function (link) {
            bounds.expandByPoint(new THREE.Vector3(link[0], link[1], link[2]));
          });
        });
      }
    });
    if ((page.data.robots || []).length) bounds.expandByPoint(new THREE.Vector3(0, 0, 0));
    var span = bounds.getSize(new THREE.Vector3()).length() || 1.0;
    var center = bounds.getCenter(new THREE.Vector3());

    var view = { theta: -Math.PI / 4, phi: Math.PI / 3.2, radius: span * 0.78, target: center.clone() };

    function applyCamera() {
      var sinPhi = Math.sin(view.phi);
      camera.position.set(
        view.target.x + view.radius * sinPhi * Math.cos(view.theta),
        view.target.y + view.radius * sinPhi * Math.sin(view.theta),
        view.target.z + view.radius * Math.cos(view.phi)
      );
      camera.lookAt(view.target);
      dirty = true;
    }

    function fitView() {
      view.target.copy(center);
      // WHY tighter than the bounds (2026-11-25): the bounds hold every link's reach sphere, so 1.05 × their diagonal
      // framed mostly floor grid and left the paths, where the error is, a few pixels tall
      view.radius = Math.max(span * 0.78, 0.2);
      view.theta = -Math.PI / 4;
      view.phi = Math.PI / 3.2;
      applyCamera();
    }

    /* ---------------- orientation gizmo (three.js ViewHelper) ---------------- */

    // Upstream owns the widget: drawing, hit testing, and the fly-to
    // animation. It drives the camera directly, so after every animation step
    // the spherical orbit state is read back off the camera — otherwise the
    // next drag would snap back to wherever the orbit thought it was.
    var viewHelper = new THREE.ViewHelper(camera, canvas);
    viewHelper.setLabels ? viewHelper.setLabels('X', 'Y', 'Z') : null;

    function syncViewFromCamera() {
      var offset = camera.position.clone().sub(view.target);
      view.radius = Math.max(offset.length(), 1e-6);
      view.theta = Math.atan2(offset.y, offset.x);
      view.phi = Math.min(Math.PI - 0.03,
        Math.max(0.03, Math.acos(offset.z / view.radius)));
    }

    function inGizmo(px, py) {
      var width = canvas.clientWidth || 800;
      return px >= width - GIZMO_SIZE && px <= width
        && py >= canvasHeight - GIZMO_SIZE && py <= canvasHeight;
    }

    /* ---------------- pointer: orbit / pan / gizmo ---------------- */

    var dragging = null;
    canvas.addEventListener('contextmenu', function (event) { event.preventDefault(); });
    canvas.addEventListener('pointerdown', function (event) {
      var box = canvas.getBoundingClientRect();
      var px = event.clientX - box.left, py = event.clientY - box.top;
      if (inGizmo(px, py)) {
        dragging = { mode: 'gizmo', x: event.clientX, y: event.clientY };
        return;
      }
      canvas.setPointerCapture(event.pointerId);
      dragging = {
        mode: (event.button === 2 || event.shiftKey || event.ctrlKey) ? 'pan' : 'orbit',
        x: event.clientX, y: event.clientY,
      };
    });
    canvas.addEventListener('pointermove', function (event) {
      var box = canvas.getBoundingClientRect();
      canvas.style.cursor = inGizmo(event.clientX - box.left, event.clientY - box.top)
        ? 'pointer' : '';
      if (!dragging || dragging.mode === 'gizmo') return;
      var dx = event.clientX - dragging.x;
      var dy = event.clientY - dragging.y;
      dragging.x = event.clientX;
      dragging.y = event.clientY;
      if (dragging.mode === 'orbit') {
        view.theta -= dx * 0.006;
        view.phi = Math.min(Math.PI - 0.03, Math.max(0.03, view.phi - dy * 0.006));
      } else {
        var right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
        var up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        var scale = view.radius * 0.0016;
        view.target.addScaledVector(right, -dx * scale).addScaledVector(up, dy * scale);
      }
      applyCamera();
    });
    canvas.addEventListener('pointerup', function (event) {
      if (dragging && dragging.mode === 'gizmo') {
        var moved = Math.abs(event.clientX - dragging.x) + Math.abs(event.clientY - dragging.y);
        if (moved < 5) {
          viewHelper.center.copy(view.target);
          if (viewHelper.handleClick(event)) dirty = true;
        }
      }
      dragging = null;
    });
    canvas.addEventListener('wheel', function (event) {
      event.preventDefault();
      view.radius = Math.min(span * 12, Math.max(span * 0.05, view.radius * Math.exp(event.deltaY * 0.0012)));
      applyCamera();
    }, { passive: false });
    canvas.addEventListener('dblclick', function (event) {
      var box = canvas.getBoundingClientRect();
      if (!inGizmo(event.clientX - box.left, event.clientY - box.top)) fitView();
    });

    /* ---------------- per-situation geometry ---------------- */

    // What is drawn for a situation is remembered under its *name*, so the
    // same choice comes back on every scenario tab (see plots.js prefs).
    // WHY "3dv2:" (2026-11-25): the elements' defaults changed with the line styles (points off, the orientation arc
    // on); a choice made under the old drawing would bring the old clutter back
    function elementKey(sit, id) { return '3dv2:' + sit.name + ':' + id; }
    function eyeKey(sit) { return '3deye:' + sit.name; }

    var sitStates = situations.map(function (sit) {
      var group = new THREE.Group();
      scene.add(group);
      var enabled = {};
      availableElements(sit).forEach(function (element) {
        enabled[element.id] = prefs.get(elementKey(sit, element.id), element.on);
      });
      return {
        sit: sit,
        group: group,
        eyeOn: prefs.get(eyeKey(sit), true),
        globalOn: page.visible[sit.name] !== false,
        enabled: enabled,
        dynamic: [],     // this frame's window geometry, disposed on the next rebuild
        labels: [],      // [{node, at}] screen labels pinned to a world point (style C)
        row: null,
        eyeBtn: null,
        boxes: {},       // element id -> its checkbox in the dropdown
        labelNodes: {},  // element id -> its label text in the dropdown
        paintButton: null,
      };
    });

    var style = currentStyle;
    var density = 20;
    var markerSize = Math.max(0.01, Math.min(0.25, span * 0.05));
    var decay = 5;
    var lookahead = 2;
    var magnifyChoice = 0;   // 0: auto

    /* ---- the error, per candidate sample: |target − run| (m), the rotation between them (rad, axis) ---- */

    var errorPeak = 0, anglePeak = 0;
    sitStates.forEach(function (state) {
      var three = state.sit.three;
      var n = three.p.length;
      state.err = new Float64Array(n).fill(NaN);
      state.ang = new Float64Array(n).fill(NaN);
      state.axis = new Float64Array(n * 3);
      if (!three.tp) return;
      for (var i = 0; i < n; i++) {
        var to = three.tp[i];
        if (!to || to[0] === null) continue;
        var dx = to[0] - three.p[i][0], dy = to[1] - three.p[i][1], dz = to[2] - three.p[i][2];
        state.err[i] = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (state.err[i] > errorPeak) errorPeak = state.err[i];
        var q = three.quat[i], tq = three.tquat[i];
        if (!tq || tq[0] === null) continue;
        // the rotation run -> target, in the world: tq * conj(q)
        var w = tq[0] * q[0] + tq[1] * q[1] + tq[2] * q[2] + tq[3] * q[3];
        var x = -tq[0] * q[1] + tq[1] * q[0] - tq[2] * q[3] + tq[3] * q[2];
        var y = -tq[0] * q[2] + tq[1] * q[3] + tq[2] * q[0] - tq[3] * q[1];
        var z = -tq[0] * q[3] - tq[1] * q[2] + tq[2] * q[1] + tq[3] * q[0];
        if (w < 0) { w = -w; x = -x; y = -y; z = -z; }
        var s = Math.sqrt(x * x + y * y + z * z);
        state.ang[i] = 2 * Math.atan2(s, w);
        if (s > 1e-12) { state.axis[i * 3] = x / s; state.axis[i * 3 + 1] = y / s; state.axis[i * 3 + 2] = z / s; }
        else state.axis[i * 3 + 2] = 1;
        if (state.ang[i] > anglePeak) anglePeak = state.ang[i];
      }
    });
    var targetState = sitStates.filter(function (state) { return state.sit.role === 'target'; })[0] || null;
    var pathRadius = (function () {
      var box = new THREE.Box3();
      (targetState || sitStates[0]).sit.three.p.forEach(function (point) {
        box.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
      });
      return 0.5 * box.getSize(new THREE.Vector3()).length();
    })();
    var autoMagnify = errorPeak < SAME_POSE_M ? 1 : niceFactor(MAGNIFY_SHARE * pathRadius / errorPeak);
    var arcMagnify = anglePeak <= 0 ? 1 : Math.max(1, niceFactor((ARC_TARGET_DEG * Math.PI / 180) / anglePeak));
    function magnify() { return magnifyChoice || autoMagnify; }

    // where a sample is drawn: the run at target + N × (run − target); the target, and a run with no target, as recorded
    function drawnAt(state, i, out) {
      var three = state.sit.three;
      var p = three.p[i];
      var to = three.tp ? three.tp[i] : null;
      if (!to || to[0] === null) { out[0] = p[0]; out[1] = p[1]; out[2] = p[2]; return out; }
      var n = magnify();
      out[0] = to[0] + n * (p[0] - to[0]); out[1] = to[1] + n * (p[1] - to[1]); out[2] = to[2] + n * (p[2] - to[2]);
      return out;
    }

    function disposeDynamic(state) {
      state.dynamic.forEach(function (object) {
        state.group.remove(object);
        object.traverse(function (child) {
          if (child.geometry) child.geometry.dispose();
          if (child.material) child.material.dispose();
        });
      });
      state.dynamic = [];
      state.labels.forEach(function (label) { label.node.remove(); });
      state.labels = [];
    }

    function keep(state, object) {
      state.group.add(object);
      state.dynamic.push(object);
      return object;
    }

    /* The samples drawn now, [first, last) on the situation's own clock, decimated to MAX_WINDOW_POINTS. The run's
       window is its trail (decay seconds up to the playhead); the target's adds the look-ahead. */
    function windowOf(state, time, ahead) {
      var t = state.sit.three.t;
      var first = decay === Infinity ? 0 : countLeq(t, time - decay);
      var last = ahead === Infinity ? t.length : countLeq(t, time + ahead);
      var indices = [];
      var stride = Math.max(1, Math.ceil((last - first) / MAX_WINDOW_POINTS));
      for (var i = first; i < last; i += stride) indices.push(i);
      if (last - 1 >= first && indices[indices.length - 1] !== last - 1) indices.push(last - 1);
      return indices;
    }

    // how bright a sample is: 1 at the playhead, fading to 0 over the trail; ahead, a gentle taper to 0.35
    function fadeAt(sampleTime, time) {
      if (sampleTime <= time) return decay === Infinity ? 1 : Math.max(0, 1 - (time - sampleTime) / decay);
      if (lookahead === Infinity || lookahead === 0) return 1;
      return 1 - 0.65 * Math.min(1, (sampleTime - time) / lookahead);
    }

    /* A tube along ``points`` (an array of [x,y,z]) of world ``radius``, one RGBA per point (vertex colours, so a
       window fades along its length). WHY tubes and not lines: WebGL draws every line 1 px wide, and width is what
       tells the target from the run once dashes are gone. */
    function tube(points, rgba, radius, radial) {
      radial = radial || 6;
      var n = points.length;
      if (n < 2) return null;
      var positions = new Float32Array(n * radial * 3);
      var colors = new Float32Array(n * radial * 4);
      var index = [];
      var normal = new THREE.Vector3(), binormal = new THREE.Vector3(), tangent = new THREE.Vector3();
      var previousNormal = null;
      for (var i = 0; i < n; i++) {
        var a = points[Math.max(0, i - 1)], b = points[Math.min(n - 1, i + 1)];
        tangent.set(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
        if (tangent.lengthSq() < 1e-20) tangent.set(0, 0, 1);
        tangent.normalize();
        // parallel transport: keep the previous normal, made perpendicular to this tangent, so the tube never twists
        if (previousNormal) normal.copy(previousNormal);
        else normal.set(Math.abs(tangent.z) < 0.9 ? 0 : 1, 0, Math.abs(tangent.z) < 0.9 ? 1 : 0);
        normal.addScaledVector(tangent, -normal.dot(tangent));
        if (normal.lengthSq() < 1e-12) normal.set(1, 0, 0).addScaledVector(tangent, -tangent.x);
        normal.normalize();
        previousNormal = normal.clone();
        binormal.crossVectors(tangent, normal);
        for (var k = 0; k < radial; k++) {
          var angle = (k / radial) * Math.PI * 2;
          var c = Math.cos(angle) * radius, s = Math.sin(angle) * radius;
          var o = (i * radial + k) * 3;
          positions[o] = points[i][0] + normal.x * c + binormal.x * s;
          positions[o + 1] = points[i][1] + normal.y * c + binormal.y * s;
          positions[o + 2] = points[i][2] + normal.z * c + binormal.z * s;
          var co = (i * radial + k) * 4;
          colors[co] = rgba[i][0]; colors[co + 1] = rgba[i][1]; colors[co + 2] = rgba[i][2]; colors[co + 3] = rgba[i][3];
        }
        if (i > 0) {
          for (var m = 0; m < radial; m++) {
            var a0 = (i - 1) * radial + m, a1 = (i - 1) * radial + (m + 1) % radial;
            var b0 = i * radial + m, b1 = i * radial + (m + 1) % radial;
            index.push(a0, b0, a1, a1, b0, b1);
          }
        }
      }
      var geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute('color', new THREE.BufferAttribute(colors, 4));
      geometry.setIndex(index);
      return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
        vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
    }

    // a plain 1 px polyline (the faint whole-route context of style C)
    function polyline(points, color, opacity) {
      var flat = new Float32Array(points.length * 3);
      points.forEach(function (point, i) { flat[i * 3] = point[0]; flat[i * 3 + 1] = point[1]; flat[i * 3 + 2] = point[2]; });
      var geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(flat, 3));
      return new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: color, transparent: true, opacity: opacity, depthWrite: false }));
    }

    function segments(positions, color, opacity) {
      var geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
      var options = { color: color };
      if (opacity < 1) { options.transparent = true; options.opacity = opacity; }
      return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial(options));
    }

    function sphere(at, radius, color, opacity) {
      var mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 14, 10), new THREE.MeshBasicMaterial({
        color: color, transparent: opacity < 1, opacity: opacity }));
      mesh.position.set(at[0], at[1], at[2]);
      return mesh;
    }

    // an arrow as a cylinder and a cone, from ``from`` to ``to`` (world), coloured ``rgb``
    function arrow(from, to, rgb, shaft) {
      var direction = new THREE.Vector3(to[0] - from[0], to[1] - from[1], to[2] - from[2]);
      var length = direction.length();
      if (length < 1e-9) return null;
      direction.divideScalar(length);
      var head = Math.min(length * 0.45, shaft * 4.2);
      var color = new THREE.Color(rgb[0], rgb[1], rgb[2]);
      var group = new THREE.Group();
      var material = new THREE.MeshBasicMaterial({ color: color });
      var body = new THREE.Mesh(new THREE.CylinderGeometry(shaft, shaft, Math.max(length - head, 1e-9), 8), material);
      var cone = new THREE.Mesh(new THREE.ConeGeometry(shaft * 2.6, head, 12), material.clone());
      var yUp = new THREE.Vector3(0, 1, 0);
      var turn = new THREE.Quaternion().setFromUnitVectors(yUp, direction);
      body.quaternion.copy(turn);
      cone.quaternion.copy(turn);
      body.position.set(from[0], from[1], from[2]).addScaledVector(direction, (length - head) / 2);
      cone.position.set(to[0], to[1], to[2]).addScaledVector(direction, -head / 2);
      group.add(body);
      group.add(cone);
      return group;
    }

    /* The orientation error at sample i as an arc about its rotation axis, centred on the drawn run point: it turns
       ×arcMagnify the true angle (capped below a full turn) from the run's tool z (or any direction across the axis)
       toward the target's. Returns {object, tip}. */
    function orientationArc(state, i, at, radius, rgb, width) {
      var angle = state.ang[i];
      if (!(angle > 0)) return null;
      var axis = new THREE.Vector3(state.axis[i * 3], state.axis[i * 3 + 1], state.axis[i * 3 + 2]);
      var z = zAxisOf(state.sit.three.quat[i]);
      var start = new THREE.Vector3(z[0], z[1], z[2]);
      start.addScaledVector(axis, -start.dot(axis));
      if (start.lengthSq() < 1e-6) {
        start.set(1, 0, 0).addScaledVector(axis, -axis.x);
        if (start.lengthSq() < 1e-6) start.set(0, 1, 0).addScaledVector(axis, -axis.y);
      }
      start.normalize();
      var sweep = Math.min(angle * arcMagnify, Math.PI * 1.6);
      var points = [], rgba = [];
      var turn = new THREE.Quaternion();
      for (var k = 0; k <= ARC_STEPS; k++) {
        turn.setFromAxisAngle(axis, sweep * k / ARC_STEPS);
        var v = start.clone().applyQuaternion(turn).multiplyScalar(radius);
        points.push([at[0] + v.x, at[1] + v.y, at[2] + v.z]);
        rgba.push([rgb[0], rgb[1], rgb[2], 1]);
      }
      var group = new THREE.Group();
      var line = tube(points, rgba, width, 6);
      if (line) group.add(line);
      // the two spokes make it read as an angle: from the run's direction to the target's
      var first = points[0], last = points[points.length - 1];
      group.add(segments([at[0], at[1], at[2], first[0], first[1], first[2], at[0], at[1], at[2], last[0], last[1], last[2]],
        new THREE.Color(rgb[0], rgb[1], rgb[2]), 0.8));
      var tipDir = new THREE.Vector3(last[0] - points[points.length - 2][0], last[1] - points[points.length - 2][1],
        last[2] - points[points.length - 2][2]).normalize();
      var cone = new THREE.Mesh(new THREE.ConeGeometry(width * 2.8, width * 7, 10),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(rgb[0], rgb[1], rgb[2]) }));
      cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tipDir);
      cone.position.set(last[0], last[1], last[2]);
      group.add(cone);
      return { object: group, tip: last };
    }

    // ``place`` "above" / "below" its point, so the two labels of one instant never sit on each other
    function label(state, text, at, color, place) {
      var node = el('div', 'tc-3dlabel ' + (place || 'above'), canvasBox, text);
      node.setAttribute('data-tc-3dlabel', '');
      if (color) node.style.borderColor = color;
      state.labels.push({ node: node, at: new THREE.Vector3(at[0], at[1], at[2]) });
    }

    function placeLabels() {
      var width = canvasBox.clientWidth || 800;
      var projected = new THREE.Vector3();
      sitStates.forEach(function (state) {
        state.labels.forEach(function (entry) {
          projected.copy(entry.at).project(camera);
          var visible = state.group.visible && projected.z < 1 && Math.abs(projected.x) <= 1 && Math.abs(projected.y) <= 1;
          entry.node.hidden = !visible;
          if (!visible) return;
          entry.node.style.left = ((projected.x + 1) / 2 * width) + 'px';
          entry.node.style.top = ((1 - projected.y) / 2 * canvasHeight) + 'px';
        });
      });
    }

    function rgbOf(color) { var c = new THREE.Color(color); return [c.r, c.g, c.b]; }

    /* Everything a situation draws at ``time`` in the active style. Rebuilt on every time change: a window is at most
       MAX_WINDOW_POINTS samples, so a rebuild is a few thousand vertices. */
    function rebuild(state, time) {
      disposeDynamic(state);
      var sit = state.sit;
      var three = sit.three;
      var isTarget = sit.role === 'target';
      var candidate = !!three.tp;
      var color = rgbOf(sit.color);
      var on = state.enabled;
      var ahead = isTarget ? lookahead : 0;
      var indices = windowOf(state, time, ahead);
      var head = Math.max(0, countLeq(three.t, time) - 1);
      var at = [0, 0, 0];
      var points = indices.map(function (i) { return drawnAt(state, i, [0, 0, 0]); });
      var fades = indices.map(function (i) { return fadeAt(three.t[i], time); });
      var headAt = drawnAt(state, head, [0, 0, 0]);
      var started = three.t.length && time >= three.t[0];

      if (on.path) {
        if (style === 'C' && isTarget) {
          // the whole route, faint, for context; the window bright on top. WHY the target's only: the magnified run's
          // whole history drawn faint was a haze of spikes, the clutter this style exists to remove
          var every = [];
          var stride = Math.max(1, Math.ceil(three.t.length / 4000));
          for (var g = 0; g < three.t.length; g += stride) every.push(drawnAt(state, g, [0, 0, 0]));
          keep(state, polyline(every, sit.color, 0.28));
        }
        var radius, alpha;
        if (isTarget) {
          radius = style === 'A' ? span * 0.0065 : style === 'B' ? span * 0.0016 : span * 0.0045;
          alpha = style === 'A' ? 0.32 : style === 'B' ? 0.95 : 0.45;
        } else {
          radius = style === 'A' ? span * 0.0024 : style === 'B' ? span * 0.0016 : span * 0.003;
          alpha = 1;
        }
        var rgba = fades.map(function (f) { return [color[0], color[1], color[2], alpha * f]; });
        var line = tube(points, rgba, radius, isTarget && style === 'A' ? 10 : 6);
        if (line) {
          line.renderOrder = isTarget ? 1 : 3;
          keep(state, line);
        }
        if (started) {
          var now = keep(state, sphere(headAt, (isTarget ? 1.25 : 1.6) * Math.max(radius, span * 0.0022), sit.color,
            isTarget ? 0.6 : 1));
          now.renderOrder = 4;
        }
      }

      // the samples of the window, every ``density``-th of the whole run: points, pose frames, tool z
      var markerStride = Math.max(1, Math.floor(three.t.length / density));
      var marks = indices.filter(function (i) { return i % markerStride === 0 && three.t[i] <= time + ahead; });
      if (on.points && marks.length) {
        var flat = [];
        marks.forEach(function (i) { drawnAt(state, i, at); flat.push(at[0], at[1], at[2]); });
        var geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(flat), 3));
        keep(state, new THREE.Points(geometry, new THREE.PointsMaterial({
          color: sit.color, size: Math.max(3, markerSize * 55), sizeAttenuation: false })));
      }
      if ((on.frames || on.zvec) && marks.length) {
        var framePositions = [], frameColors = [], zPositions = [];
        var axisColors = [[0.82, 0.23, 0.23], [0.18, 0.62, 0.27], [0.16, 0.4, 0.84]];
        marks.forEach(function (i) {
          drawnAt(state, i, at);
          var columns = columnsOf(three.quat[i]);
          for (var axis = 0; axis < 3; axis++) {
            framePositions.push(at[0], at[1], at[2], at[0] + columns[axis][0] * markerSize,
              at[1] + columns[axis][1] * markerSize, at[2] + columns[axis][2] * markerSize);
            frameColors.push.apply(frameColors, axisColors[axis].concat(axisColors[axis]));
          }
          zPositions.push(at[0], at[1], at[2], at[0] + columns[2][0] * markerSize,
            at[1] + columns[2][1] * markerSize, at[2] + columns[2][2] * markerSize);
        });
        if (on.frames) {
          var frameGeometry = new THREE.BufferGeometry();
          frameGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(framePositions), 3));
          frameGeometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(frameColors), 3));
          keep(state, new THREE.LineSegments(frameGeometry, new THREE.LineBasicMaterial({ vertexColors: true })));
        }
        if (on.zvec) keep(state, segments(zPositions, sit.color, 1));
      }

      if (!candidate || !started) return;
      var headErr = state.err[head];
      var headTarget = three.tp[head];
      var shaft = span * 0.0021;

      if (on.diff) {
        if (style === 'B') {
          // a ribbon from the target to the drawn run at every sample of the trail, coloured by the error's size
          var ribbon = [], ribbonColors = [], ribbonIndex = [];
          var vertex = 0;
          indices.forEach(function (i, k) {
            var to = three.tp[i];
            if (!to || to[0] === null || !(state.err[i] >= 0)) { vertex = -1; return; }
            var rgb = rampRgb(errorPeak > 0 ? state.err[i] / errorPeak : 0);
            var fade = fades[k] * 0.85;
            ribbon.push(to[0], to[1], to[2], points[k][0], points[k][1], points[k][2]);
            ribbonColors.push(rgb[0], rgb[1], rgb[2], fade, rgb[0], rgb[1], rgb[2], fade);
            var base = ribbon.length / 3 - 2;
            if (vertex >= 0 && k > 0) ribbonIndex.push(base - 2, base - 1, base, base, base - 1, base + 1);
            vertex = base;
          });
          if (ribbonIndex.length) {
            var ribbonGeometry = new THREE.BufferGeometry();
            ribbonGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(ribbon), 3));
            ribbonGeometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(ribbonColors), 4));
            ribbonGeometry.setIndex(ribbonIndex);
            var surface = keep(state, new THREE.Mesh(ribbonGeometry, new THREE.MeshBasicMaterial({
              vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide })));
            surface.renderOrder = 2;
          }
        } else if (style === 'A') {
          // arrows along the trail, evenly spaced in time, the newest at the playhead; brightness fades with the trail
          var count = Math.max(3, Math.min(60, Math.round(density / 2.5)));
          var picked = [];
          var tFirst = three.t[indices[0]], tLast = three.t[head];
          for (var a = 0; a < count; a++) {
            var when = tLast - (tLast - tFirst) * a / Math.max(1, count - 1);
            var idx = Math.max(0, countLeq(three.t, when) - 1);
            if (picked.indexOf(idx) === -1) picked.push(idx);
          }
          var background = scene.background;
          picked.forEach(function (i) {
            var to = three.tp[i];
            if (!to || to[0] === null || !(state.err[i] > 0)) return;
            var rgb = rampRgb(errorPeak > 0 ? state.err[i] / errorPeak : 0);
            var fade = 0.3 + 0.7 * fadeAt(three.t[i], time);
            var mixed = [0, 1, 2].map(function (c) {
              return rgb[c] * fade + [background.r, background.g, background.b][c] * (1 - fade);
            });
            var made = arrow(drawnAt(state, i, [0, 0, 0]), to, mixed, shaft);
            if (made) keep(state, made).renderOrder = 5;
          });
        } else if (headTarget && headTarget[0] !== null && headErr > 0) {
          // C: one big arrow at the playhead, labelled with the true error
          var big = arrow(headAt, headTarget, rampRgb(errorPeak > 0 ? headErr / errorPeak : 0), shaft * 2.2);
          if (big) keep(state, big).renderOrder = 5;
          label(state, mmText(headErr), [(headAt[0] + headTarget[0]) / 2, (headAt[1] + headTarget[1]) / 2,
            (headAt[2] + headTarget[2]) / 2], sit.color);
        }
      }

      if (on.zarc && state.ang[head] > 0) {
        // every style: the orientation error at the playhead only
        var ring = orientationArc(state, head, headAt, markerSize * (style === 'C' ? 1.4 : 0.9),
          style === 'C' ? [0.42, 0.24, 0.62] : color, span * (style === 'C' ? 0.0024 : 0.0016));
        if (ring) {
          keep(state, ring.object).renderOrder = 5;
          if (style === 'C') label(state, degText(state.ang[head]), ring.tip, '#6b3d9e', 'below');
        }
      }
    }

    /* ---------------- robot model ---------------- */

    var robotPayloads = page.data.robots || [];
    var geometryCache = {};

    // Situations usually share one model and differ only in color, so the
    // triangle soups are decoded once per distinct model, not per situation.
    function geometriesFor(index) {
      if (!geometryCache[index]) {
        geometryCache[index] = robotPayloads[index].links.map(function (link) {
          var geometry = new THREE.BufferGeometry();
          geometry.setAttribute('position', new THREE.BufferAttribute(decodeTris(link.tris), 3));
          geometry.computeVertexNormals();
          return geometry;
        });
      }
      return geometryCache[index];
    }

    var robots = [];
    page.data.situations.forEach(function (sit) {
      var track = sit.robot_track;
      var payload = track ? robotPayloads[track.robot || 0] : null;
      if (!payload) return;
      var geometries = geometriesFor(track.robot || 0);
      var robot = { group: new THREE.Group(), links: [], sit: sit, lastIndex: -1 };
      payload.links.forEach(function (link, linkIndex) {
        var baseOpacity = link.opacity === undefined ? 0.55 : link.opacity;
        var material = new THREE.MeshLambertMaterial({
          color: link.color || sit.color,
          transparent: baseOpacity < 1,
          opacity: baseOpacity,
        });
        material.userData.baseOpacity = baseOpacity;
        var mesh = new THREE.Mesh(geometries[linkIndex], material);
        robot.group.add(mesh);
        robot.links.push(mesh);
      });
      robot.group.visible = page.visible[sit.name] !== false;
      scene.add(robot.group);
      robots.push(robot);
    });
    if (robots.length) {
      scene.add(new THREE.HemisphereLight(0xffffff, 0x9a9994, 1.0));
      var sun = new THREE.DirectionalLight(0xffffff, 0.65);
      sun.position.set(1.2, -0.8, 1.6);
      scene.add(sun);

      // The bounds so far know link *origins* only. A 250 mm arm or a payload
      // disc reaches far past its origin, so fold in each link's own extent —
      // otherwise the default fit frames the skeleton and crops the model.
      robots.forEach(function (robot) {
        var track = robot.sit.robot_track;
        robot.links.forEach(function (mesh, linkIndex) {
          mesh.geometry.computeBoundingSphere();
          var reach = mesh.geometry.boundingSphere.radius;
          [0, track.p.length - 1, track.p.length >> 1].forEach(function (sample) {
            var p = track.p[sample][linkIndex];
            bounds.expandByPoint(new THREE.Vector3(p[0] + reach, p[1] + reach, p[2] + reach));
            bounds.expandByPoint(new THREE.Vector3(p[0] - reach, p[1] - reach, p[2] - reach));
          });
        });
      });
      span = bounds.getSize(new THREE.Vector3()).length() || 1.0;
      center = bounds.getCenter(new THREE.Vector3());
    }

    function robotForSituation(name) {
      for (var i = 0; i < robots.length; i++) {
        if (robots[i].sit.name === name) return robots[i];
      }
      return null;
    }

    // Posed whether or not it is currently shown: a hidden model that is
    // re-enabled mid-scrub must already be standing at the scrub time.
    function poseRobots(time) {
      robots.forEach(function (robot) {
        var track = robot.sit.robot_track;
        var index = Math.max(0, countLeq(track.t, time) - 1);
        if (index === robot.lastIndex) return;
        robot.lastIndex = index;
        robot.links.forEach(function (mesh, linkIndex) {
          var p = track.p[index][linkIndex];
          var q = track.quat[index][linkIndex];
          mesh.position.set(p[0], p[1], p[2]);
          mesh.quaternion.set(q[1], q[2], q[3], q[0]); // three wants [x,y,z,w]
        });
      });
      dirty = true;
    }

    /* ---------------- time-limited drawing ---------------- */

    function applyDisplayTime() {
      var time = page.transport ? page.transport.eff() : Infinity;
      if (time === Infinity || time === null || time === undefined) {
        time = Math.max.apply(null, sitStates.map(function (state) {
          var t = state.sit.three.t;
          return t.length ? t[t.length - 1] : 0;
        }));
      }
      sitStates.forEach(function (state) { rebuild(state, time); });
      poseRobots(time);
      dirty = true;
    }

    /* ---------------- control panel ---------------- */

    function setElement(state, id, on, remember) {
      state.enabled[id] = on;
      if (remember) prefs.set(elementKey(state.sit, id), on);
      if (state.boxes[id]) state.boxes[id].checked = on;
      paintVisibility(state);   // the model rides on the same eye
      queueTime();
      if (state.paintButton) state.paintButton();
    }

    function paintVisibility(state) {
      state.group.visible = state.globalOn && state.eyeOn;
      var associatedRobot = robotForSituation(state.sit.name);
      if (associatedRobot) {
        associatedRobot.group.visible =
          state.globalOn && state.eyeOn && !!state.enabled.robot;
      }
      if (state.row) state.row.style.display = state.globalOn ? '' : 'none';
      if (state.eyeBtn) {
        state.eyeBtn.innerHTML = state.eyeOn ? EYE_OPEN : EYE_CLOSED;
        state.eyeBtn.className = 'tc-eye' + (state.eyeOn ? '' : ' off');
      }
      dirty = true;
    }

    var rows = el('div', 'tc-3drows', panel);
    sitStates.forEach(function (state) {
      var row = el('div', 'tc-3drow', rows);
      state.row = row;

      var eye = el('button', 'tc-eye', row);
      eye.title = 'show/hide everything for this situation in the 3D scene';
      state.eyeBtn = eye;
      eye.onclick = function () {
        state.eyeOn = !state.eyeOn;
        prefs.set(eyeKey(state.sit), state.eyeOn);
        paintVisibility(state);
        paintLegend();
      };

      var name = el('span', 'tc-3dname', row);
      var swatch = el('span', 'swatch', name);
      swatch.style.background = state.sit.color;
      name.appendChild(document.createTextNode(state.sit.title));
      name.title = state.sit.title;

      // full-word multi-select dropdown instead of a cryptic checkbox matrix;
      // the situation's robot model is one of the items
      var dd = el('div', 'tc-dd', row);
      var button = el('button', 'tc-ddbtn', dd);
      var menu = el('div', 'tc-ddmenu', dd);
      var available = availableElements(state.sit);
      state.boxes = {};

      function paintButton() {
        var on = available.filter(function (element) { return state.enabled[element.id]; });
        button.textContent = on.length === 0 ? 'nothing shown'
          : on.length === available.length ? 'everything shown'
          : on.map(function (element) { return elementLabel(element, page, style); }).join(', ');
        available.forEach(function (element) {
          if (state.labelNodes[element.id]) state.labelNodes[element.id].textContent = elementLabel(element, page, style);
        });
      }
      state.paintButton = paintButton;

      available.forEach(function (element) {
        var label = el('label', 'tc-dditem', menu);
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = !!state.enabled[element.id];
        label.appendChild(checkbox);
        state.labelNodes[element.id] = label.appendChild(document.createTextNode(elementLabel(element, page, style)));
        if (element.robot) {
          var payload = robotPayloads[state.sit.robot_track.robot || 0];
          label.title = payload ? payload.name : 'robot model';
          el('span', 'tc-ddnote', label, label.title);
        }
        state.boxes[element.id] = checkbox;
        checkbox.onchange = function () {
          setElement(state, element.id, checkbox.checked, true);
        };
      });
      button.onclick = function (event) {
        event.stopPropagation();
        var open = menu.classList.contains('open');
        document.querySelectorAll('.tc-ddmenu.open').forEach(function (other) {
          other.classList.remove('open');
        });
        if (!open) menu.classList.add('open');
      };
      paintButton();
      paintVisibility(state);
    });
    // WHY: Zach flips several layers on/off in a row to compare them, so a click
    // inside an open menu (its checkboxes, labels, padding) must NOT close it;
    // only a click elsewhere on the page, or Escape, does.
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      document.querySelectorAll('.tc-ddmenu.open').forEach(function (menu) {
        menu.classList.remove('open');
      });
    });
    document.addEventListener('click', function (event) {
      if (event.target.closest && event.target.closest('.tc-ddmenu')) return;
      document.querySelectorAll('.tc-ddmenu.open').forEach(function (menu) {
        menu.classList.remove('open');
      });
    });

    if (robots.length) {
      sliderRow('Model opacity', 5, 100, prefs.get('3d:opacity', 100), 5, function (value) {
        return value + '%';
      }, function (value) {
        prefs.set('3d:opacity', value);
        applyModelOpacity(value);
      });
      applyModelOpacity(prefs.get('3d:opacity', 100));
    }

    function applyModelOpacity(percent) {
      var scale = percent / 100;
      robots.forEach(function (robot) {
        robot.links.forEach(function (mesh) {
          mesh.material.opacity = mesh.material.userData.baseOpacity * scale;
          mesh.material.transparent = mesh.material.opacity < 1;
        });
      });
      dirty = true;
    }

    function sliderRow(label, min, max, value, step, format, onInput) {
      var row = el('div', 'sliderrow', panel);
      var labelEl = el('label', '', row);
      labelEl.appendChild(document.createTextNode(label));
      var output = el('output', '', labelEl, format(value));
      var slider = document.createElement('input');
      slider.type = 'range';
      slider.min = min; slider.max = max; slider.step = step; slider.value = value;
      row.appendChild(slider);
      slider.addEventListener('input', function () {
        var parsed = parseFloat(slider.value);
        output.textContent = format(parsed);
        onInput(parsed);
      });
      return slider;
    }

    var timeQueued = false;
    function queueTime() {
      if (timeQueued) return;
      timeQueued = true;
      requestAnimationFrame(function () {
        timeQueued = false;
        applyDisplayTime();
      });
    }

    function stepSlider(label, steps, key, fallback, format, onValue) {
      var index = prefs.get(key, steps.indexOf(fallback));
      if (!(index >= 0 && index < steps.length)) index = steps.indexOf(fallback);
      onValue(steps[index]);
      var slider = sliderRow(label, 0, steps.length - 1, index, 1, function (value) {
        return format(steps[Math.round(value)]);
      }, function (value) {
        prefs.set(key, Math.round(value));
        onValue(steps[Math.round(value)]);
        paintLegend();
        queueTime();
      });
      slider.setAttribute('data-tc-3d-slider', key);
      return slider;
    }

    // WHY these two (Zach 2026-11-25, traj compare 3D viewer feedback): how much history a run trails behind the
    // playhead, and how far ahead the target shows where it is going; their ends draw everything
    stepSlider('Trail decay', DECAY_STEPS, '3d:decay', 5, function (value) {
      return value === Infinity ? 'full (no fade)' : 'fades over ' + value + ' s';
    }, function (value) { decay = value; });
    stepSlider('Look-ahead', LOOK_STEPS, '3d:lookahead', 2, function (value) {
      return value === Infinity ? 'full route' : value === 0 ? 'off' : value + ' s ahead';
    }, function (value) { lookahead = value; });
    stepSlider('Error magnification', MAGNIFY_STEPS, '3d:magnify', 0, function (value) {
      return value === 0 ? 'auto (×' + autoMagnify + ')' : value === 1 ? '×1 (true scale)' : '×' + value;
    }, function (value) { magnifyChoice = value; });

    var densityDial = prefs.get('3d:density', 35);
    sliderRow('Marker density', 0, 100, densityDial, 1, function (value) {
      return String(Math.round(4 * Math.pow(100, value / 100)));
    }, function (value) {
      density = Math.round(4 * Math.pow(100, value / 100)); // 4 .. 400, log
      prefs.set('3d:density', value);
      queueTime();
    });
    density = Math.round(4 * Math.pow(100, densityDial / 100));

    markerSize = prefs.get('3d:markersize', Math.round(markerSize * 1000)) / 1000;
    sliderRow('Marker size', 5, 250, Math.round(markerSize * 1000), 5, function (value) {
      return (value) + ' mm';
    }, function (value) {
      markerSize = value / 1000;
      prefs.set('3d:markersize', value);
      queueTime();
    });

    var fitRow = el('div', 'btnrow', panel);
    var fitButton = el('button', '', fitRow, 'Fit view');
    fitButton.onclick = fitView;

    /* ---------------- the compact legend under the canvas: the marks of the active style ---------------- */

    // WHY a legend of swatches, not a paragraph (Zach 2026-11-25, traj compare 3D viewer feedback): the old caption
    // explained arrows and arcs in two long sentences under the canvas
    var legend = el('div', 'tc-3dlegend', canvasBox);
    legend.setAttribute('data-tc-3dlegend', '');

    function paintLegend() {
      legend.innerHTML = '';
      legend.setAttribute('data-style', style);
      function entry(swatchClass, color, text, extra) {
        var item = el('span', 'tc-3dlegend-item', legend);
        var swatch = el('span', swatchClass, item);
        if (color) swatch.style.color = color;
        el('span', '', item, text);
        if (extra) extra(item);
        return item;
      }
      var candidates = sitStates.filter(function (state) { return state.sit.three.tp && state.globalOn && state.eyeOn; });
      sitStates.forEach(function (state) {
        if (!state.globalOn || !state.eyeOn) return;
        var isTarget = state.sit.role === 'target';
        var cls = 'tc-3dlegend-line' + (isTarget && style === 'A' ? ' thick' : '');
        var words = isTarget ? state.sit.title + (style === 'A' ? ' (target, wide and pale)' : ' (target)')
          : state.sit.title + (state.sit.three.tp ? ' (×' + magnify() + ' its error)' : '');
        entry(cls, state.sit.color, words);
      });
      if (candidates.length && errorPeak > 0) {
        var reference = page.data && page.data.reference_kind === 'run' ? page.data.reference_title : 'target';
        var errorWords = style === 'B' ? 'Position error ribbon' : style === 'C' ? 'Position error now' : 'Position error arrow';
        var ramp = el('span', 'tc-3dlegend-item', legend);
        el('span', '', ramp, errorWords + ' (to ' + reference + ')');
        el('span', 'tc-3dlegend-num', ramp, '0');
        el('span', 'tc-3dlegend-ramp', ramp).style.background = rampCss();
        el('span', 'tc-3dlegend-num', ramp, mmText(errorPeak));
        if (anglePeak > 0) {
          entry('tc-3dlegend-arc', style === 'C' ? '#6b3d9e' : candidates[0].sit.color,
            'Orientation error arc, now' + (arcMagnify > 1 ? ' (×' + arcMagnify + ' its angle)' : ''));
        }
      }
      var windowWords = (decay === Infinity ? 'whole history' : 'history fades over ' + decay + ' s') + ' · target ' +
        (lookahead === Infinity ? 'whole route' : lookahead === 0 ? 'up to now' : lookahead + ' s ahead') +
        (style === 'C' ? ' · the rest of the route faint' : '');
      el('span', 'tc-3dlegend-note', legend, windowWords + ' · drag: orbit · right-drag: pan · wheel: zoom · double-click: fit');
    }

    /* ---------------- scrubber (page transport) ---------------- */

    if (page.transport) {
      TrajCompare.buildTransportBar(page, canvasBox);
      page.transport.onChange(function () { applyDisplayTime(); });
    }

    /* ---------------- lifecycle ---------------- */

    function resize() {
      var width = canvasBox.clientWidth || 800;
      canvasHeight = Math.round(heightFor(width));
      renderer.setSize(width, canvasHeight, false);
      canvas.style.height = canvasHeight + 'px';
      camera.aspect = width / canvasHeight;
      camera.updateProjectionMatrix();
      dirty = true;
    }
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(function () { resize(); }).observe(canvasBox);
    }

    var lastFrame = 0;

    function frame(now) {
      var delta = Math.min(0.1, (now - lastFrame) / 1000) || 0;
      lastFrame = now;
      if (active && viewHelper.animating) {
        viewHelper.update(delta);
        syncViewFromCamera();
        applyCamera();   // re-impose z-up; ViewHelper animates in its own frame
      }
      if (active && dirty) {
        var width = canvasBox.clientWidth || 800;
        renderer.setViewport(0, 0, width, canvasHeight);
        renderer.clear();
        renderer.render(scene, camera);
        viewHelper.render(renderer);
        placeLabels();
        dirty = false;
      }
      requestAnimationFrame(frame);
    }

    sitStates.forEach(function (state) { paintVisibility(state); });
    paintLegend();
    applyDisplayTime();
    resize();
    fitView();
    requestAnimationFrame(frame);

    var api = {
      setStyle: function (value) {
        if (value === style) return;
        style = value;
        sitStates.forEach(function (state) { if (state.paintButton) state.paintButton(); });
        paintLegend();
        applyDisplayTime();
      },
      setSituationVisible: function (name, show) {
        sitStates.forEach(function (state) {
          if (state.sit.name === name) {
            state.globalOn = show;
            paintVisibility(state);
          }
        });
        paintLegend();
        dirty = true;
      },
      // Another scenario tab changed the 3D layout; adopt it.
      applyShared: function () {
        sitStates.forEach(function (state) {
          state.eyeOn = prefs.get(eyeKey(state.sit), true);
          availableElements(state.sit).forEach(function (element) {
            var want = prefs.get(elementKey(state.sit, element.id), element.on);
            if (want !== !!state.enabled[element.id]) setElement(state, element.id, want, false);
          });
          paintVisibility(state);
        });
      },
      setActive: function (value) {
        active = !!value;
        if (active) { resize(); dirty = true; }
      },
    };
    viewers.push(api);
    ensureStylePicker();
    return api;
  }

  return { create: create, styles: STYLES, setStyle: setStyleEverywhere };
})();
