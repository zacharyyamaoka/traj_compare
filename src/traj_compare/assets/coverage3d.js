/* coverage3d.js — the three.js views of the trajectory coverage page (docs/COVERAGE.md, "The custom page").
 *
 *   const handle = Coverage3D.mount(body, 'voxels-3d' | 'spaghetti-3d' | 'sphere-3d', payload, ctx);
 *   const space = Coverage3D.mountProposals(section, payload, ctx);     // the [data-cov-view="space3d"] tab
 *   handle.update(ctx); handle.highlight(trajectoryIndex | null); handle.dispose();
 *
 * ctx = {cmap, reverse, scale, enough, joint, ramp}; every colour comes from coverage_color.js (CoverageColor).
 * Reads ONLY the payload "traj_compare.coverage/1" (SI) and labels in degrees, mm, deg/s.
 *
 * WHY these views (Zach, Daily Note 2026-11-23 "Coverage Feedback"): "I like the spaghetti view in cartesian and then
 * also the voxel view (which shows like the histogram of coverage in 3D) the score of the voxel is set by like the
 * visited count"; orientation "like a sphere kinda as well.. so I see on what side of the sphere you are tilting".
 * WHY the proposals: "Can you please make a bunch of different proposals about how we could use 3D plots to make
 * things clearer? histograms are good because you don't have things hidden inside like with voxel things. I feel it
 * could be useful for showing like q, qd, qdd all at the same time of something... or showing something that depends
 * on 2 other things right".
 * Camera taste: z up; drag orbits, wheel zooms, right-drag pans, double-click fits; three.js' own ViewHelper gizmo (the
 * one viewer3d.js uses); every colour and mark named in a legend; plain words; degrees, never radians.
 */
(function (global) {
  'use strict';

  const THREE = global.THREE;
  const CC = global.CoverageColor;

  const STORAGE_KEY = 'traj_compare.coverage.proposal';
  const GIZMO_SIZE = 128; // ViewHelper's fixed `dim`
  const INK = '#2b2a2f';
  const GRID = '#e9e8e3';
  const FRAME = '#b9b8b1';
  const HIGHLIGHT = '#e8590c';
  const REACHABLE_GREY = '#c9c8c1';
  const AXIS_COLOURS = ['#d23b3b', '#2f9e44', '#2a66d6']; // viewer3d.js' x / y / z
  const FONT = "-apple-system, 'Segoe UI', Roboto, sans-serif";

  /* ── small helpers ─────────────────────────────────────────────────────── */

  function el(tag, className, parent, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function clamp(value, lo, hi) { return Math.min(hi, Math.max(lo, value)); }

  /* A number as a label: few digits, a real minus sign. */
  function fmt(value) {
    if (value === null || value === undefined || !isFinite(value)) return '–';
    const size = Math.abs(value);
    let text;
    if (size === 0) text = '0';
    else if (size >= 100) text = String(Math.round(value));
    else if (size >= 10) text = String(Math.round(value * 10) / 10);
    else text = String(Number(value.toPrecision(2)));
    return text.replace('-', '−');
  }

  function niceStep(span, count) {
    const raw = span / Math.max(1, count);
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / magnitude;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * magnitude;
  }

  function niceTicks(lo, hi, count) {
    if (!(hi > lo)) return [lo];
    const step = niceStep(hi - lo, count || 4);
    const ticks = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) {
      ticks.push(Math.abs(v) < step * 1e-6 ? 0 : v);
    }
    return ticks;
  }

  /* The two ends (a limit's values) plus round values clear of them. */
  function endTicks(lo, hi, count) {
    if (!(hi > lo)) return [lo];
    const step = niceStep(hi - lo, count || 4);
    const inner = niceTicks(lo, hi, count || 4).filter((v) => v - lo > step * 0.45 && hi - v > step * 0.45);
    return [lo].concat(inner, [hi]);
  }

  /* data values -> [{f, label}] along an axis running lo..hi */
  function ticksOn(values, lo, hi, scale) {
    const k = scale || 1;
    return values.map((v) => ({ f: (v - lo) / (hi - lo), label: fmt(v * k) }));
  }

  // WHY exact colours: CoverageColor's bytes must reach the screen unchanged (white = empty, the colorbar = the cells).
  // three r160 renders in linear light and encodes sRGB on output, so every colour going into a buffer is decoded first.
  const SRGB_TO_LINEAR = new Float32Array(256);
  for (let i = 0; i < 256; i++) {
    const c = i / 255;
    SRGB_TO_LINEAR[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  function putRGB(array, offset, rgb) {
    array[offset] = SRGB_TO_LINEAR[rgb[0]];
    array[offset + 1] = SRGB_TO_LINEAR[rgb[1]];
    array[offset + 2] = SRGB_TO_LINEAR[rgb[2]];
  }

  function hexRGB(hex) {
    const n = parseInt(hex.replace('#', ''), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function colour(rgbOrHex) {
    const rgb = typeof rgbOrHex === 'string' ? hexRGB(rgbOrHex) : rgbOrHex;
    return new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace);
  }

  function luminance(rgb) { return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]; }

  /* The colormap's dark end: line ink that still follows the palette (and its Reverse switch). */
  function darkEnd(ramp) {
    const a = ramp(0.0);
    const b = ramp(1.0);
    return luminance(a) <= luminance(b) ? a : b;
  }

  function normalise(ctx, payload) {
    const out = Object.assign({ cmap: 'viridis', reverse: false, scale: 'linear' }, ctx || {});
    if (!out.enough) out.enough = (payload && payload.enough) || 10;
    if (typeof out.ramp !== 'function') out.ramp = CC.ramp(out.cmap, out.reverse);
    out.jointName = jointName(payload, out.joint);
    return out;
  }

  function jointName(payload, joint) {
    const joints = (payload && payload.joints) || [];
    if (typeof joint === 'number' && joints[joint]) return joints[joint].name;
    if (joints.some((j) => j.name === joint)) return joint;
    return joints.length ? joints[0].name : null;
  }

  /* Display units of a joint: q in deg (or mm), qd in deg/s, qdd in deg/s². */
  function units(payload, name) {
    const joint = (payload.joints || []).find((j) => j.name === name) || {};
    const display = joint.display || { scale: 180 / Math.PI, unit: 'deg' };
    return { scale: display.scale, q: display.unit, qd: display.unit + '/s', qdd: display.unit + '/s²' };
  }

  function disposeObject(object) {
    object.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      const materials = Array.isArray(child.material) ? child.material : child.material ? [child.material] : [];
      materials.forEach((material) => { if (material.map) material.map.dispose(); material.dispose(); });
    });
  }

  function storageGet(key) { try { return global.localStorage.getItem(key); } catch (e) { return null; } }
  function storageSet(key, value) { try { global.localStorage.setItem(key, value); } catch (e) { /* private mode */ } }

  /* ── style (own sheet: the page's coverage.css belongs to the page) ────── */

  function injectStyle() {
    if (document.getElementById('cov3d-style')) return;
    const style = el('style', null, document.head);
    style.id = 'cov3d-style';
    style.textContent = `
.cov3d-stage { position: relative; width: 100%; overflow: hidden; background: #fff;
  border: 1px solid #e6e5e0; border-radius: 6px; }
.cov3d-stage canvas { display: block; width: 100%; touch-action: none; }
.cov3d-labels { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.cov3d-label { position: absolute; left: 0; top: 0; font: 11px/1.15 ${FONT}; color: #45443f; white-space: nowrap;
  font-variant-numeric: tabular-nums; text-shadow: 0 0 2px #fff, 0 0 2px #fff, 0 0 3px #fff; }
.cov3d-label.axis { font-size: 11.5px; font-weight: 600; color: #22211f; }
.cov3d-label.name { font-size: 11.5px; color: #22211f; }
.cov3d-label.name.current { font-weight: 700; }
.cov3d-label.limit { color: #a4372a; font-weight: 600; }
.cov3d-label.dir { font-size: 12px; font-weight: 600; color: #22211f; background: rgba(255,255,255,.85); border-radius: 3px; padding: 0 3px; }
.cov3d-label.dir.faint { font-weight: 400; color: #8a8983; }
.cov3d-label.hi { color: ${HIGHLIGHT}; font-weight: 700; }
.cov3d-label.chip { background: rgba(255,255,255,.88); border-radius: 3px; padding: 0 3px; text-shadow: none; color: #22211f; }
.cov3d-tip { position: absolute; left: 0; top: 0; pointer-events: none; display: none; z-index: 2;
  background: rgba(252,252,251,.97); border: 1px solid #cfcec8; border-radius: 4px; padding: 3px 7px;
  font: 11.5px/1.35 ${FONT}; color: #22211f; white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,.10); }
.cov3d-hint { position: absolute; left: 8px; bottom: 6px; font: 10.5px ${FONT}; color: #9a9993; pointer-events: none; }
.cov3d-controls { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; margin: 6px 0 0;
  font: 12px ${FONT}; color: #52514e; }
.cov3d-controls:empty { display: none; }
.cov3d-controls label { display: inline-flex; align-items: center; gap: 6px; }
.cov3d-controls input[type=range] { width: 170px; accent-color: #2a78d6; }
.cov3d-controls input[type=checkbox] { accent-color: #2a78d6; margin: 0; }
.cov3d-controls output { color: #0b0b0b; font-variant-numeric: tabular-nums; }
.cov3d-legend { display: flex; flex-wrap: wrap; gap: 6px 26px; align-items: flex-start; margin-top: 8px;
  font: 12px/1.4 ${FONT}; color: #52514e; }
.cov3d-cbar { min-width: 250px; }
.cov3d-cbar .t { color: #22211f; font-weight: 600; margin-bottom: 3px; }
.cov3d-cbar .row { display: flex; align-items: flex-start; gap: 10px; }
.cov3d-cbar .scalebox { width: 230px; }
.cov3d-cbar .bar { height: 11px; border: 1px solid #cfcec8; border-radius: 2px; }
.cov3d-cbar .ticks { position: relative; height: 15px; font-size: 10.5px; color: #52514e;
  font-variant-numeric: tabular-nums; }
.cov3d-cbar .ticks span { position: absolute; top: 1px; transform: translateX(-50%); white-space: nowrap; }
.cov3d-cbar .ticks span:first-child { transform: none; }
.cov3d-cbar .ticks span:last-child { transform: translateX(-100%); }
.cov3d-cbar .empty { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; white-space: nowrap; }
.cov3d-cbar .empty i { width: 14px; height: 11px; border: 1px solid #cfcec8; background: #fff; border-radius: 2px; }
.cov3d-cbar .note { font-size: 10.5px; color: #8a8983; }
.cov3d-cbar .chips { display: flex; gap: 10px; flex-wrap: wrap; font-size: 11px; }
.cov3d-cbar .chips span { display: inline-flex; align-items: center; gap: 5px; }
.cov3d-cbar .chips i { width: 14px; height: 11px; border-radius: 2px; border: 1px solid rgba(0,0,0,.12); }
.cov3d-marks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-width: 640px; }
.cov3d-marks li { display: flex; align-items: baseline; gap: 7px; }
.cov3d-marks .sw { flex: 0 0 18px; height: 10px; border-radius: 2px; align-self: center; }
.cov3d-marks .sw.line { height: 0; border-top: 2.5px solid; border-radius: 0; }
.cov3d-marks .sw.dash { height: 0; border-top: 2px dashed; border-radius: 0; }
.cov3d-marks .sw.thin { height: 0; border-top: 1px solid; opacity: .75; border-radius: 0; }
.cov3d-marks .sw.dot { flex: 0 0 9px; height: 9px; border-radius: 50%; margin: 0 4.5px; }
.cov3d-proposal { margin: 0 0 70px; }
.cov3d-proposal h3 { margin: 0 0 2px; font: 600 15px ${FONT}; color: #22211f; }
.cov3d-proposal .what { margin: 0 0 8px; font: 13px/1.45 ${FONT}; color: #52514e; max-width: 980px; }
.cov3d-proposal details { margin-top: 8px; font: 12.5px/1.5 ${FONT}; color: #52514e; max-width: 980px; }
.cov3d-proposal summary { cursor: pointer; color: #22211f; }
.cov3d-switch { position: fixed; right: 16px; bottom: 16px; z-index: 40; display: flex; align-items: center; gap: 8px;
  background: #fcfcfb; border: 1px solid #cfcec8; border-radius: 8px; padding: 6px 8px 6px 11px;
  box-shadow: 0 2px 12px rgba(0,0,0,.14); font: 12px ${FONT}; color: #52514e; }
.cov3d-switch select { font: 12.5px ${FONT}; padding: 4px 6px; border: 1px solid #cfcec8; border-radius: 6px;
  background: #fff; color: #0b0b0b; max-width: 330px; }
.cov3d-empty { padding: 30px; color: #8a8983; font: 13px ${FONT}; }
`;
  }

  /* ── legend pieces ─────────────────────────────────────────────────────── */

  /* A colorbar with the scale's real numbers. scaled = CoverageColor.scale(...) or {ticks, note, mode}. */
  function colorbar(parent, title) {
    const box = el('div', 'cov3d-cbar', parent);
    const head = el('div', 't', box, title);
    const row = el('div', 'row', box);
    const scaleBox = el('div', 'scalebox', row);
    const bar = el('div', 'bar', scaleBox);
    const ticks = el('div', 'ticks', scaleBox);
    const chips = el('div', 'chips', scaleBox);
    const empty = el('span', 'empty', row);
    el('i', null, empty);
    const emptyText = el('span', null, empty, 'white = none');
    const note = el('div', 'note', box);
    return {
      setTitle(text) { head.textContent = text; },
      setEmpty(text) { empty.style.display = text ? '' : 'none'; emptyText.textContent = text || ''; },
      paint(scaled, ramp, opts) {
        opts = opts || {};
        ticks.textContent = '';
        chips.textContent = '';
        const discrete = scaled.mode === 'visited' || scaled.mode === 'enough';
        bar.style.display = discrete ? 'none' : '';
        ticks.style.display = discrete ? 'none' : '';
        chips.style.display = discrete ? '' : 'none';
        if (discrete) {
          (scaled.ticks || []).forEach((tick) => {
            const chip = el('span', null, chips);
            el('i', null, chip).style.background = CC.css(ramp(tick.t));
            chip.appendChild(document.createTextNode(tick.label));
          });
        } else {
          const stops = [];
          for (let i = 0; i <= 16; i++) stops.push(`${CC.css(ramp(i / 16))} ${(i / 16 * 100).toFixed(1)}%`);
          bar.style.background = `linear-gradient(to right, ${stops.join(', ')})`;
          const list = (scaled.ticks || []).slice().sort((a, b) => a.t - b.t);
          list.forEach((tick) => { el('span', null, ticks, tick.label).style.left = (tick.t * 100) + '%'; });
        }
        note.textContent = opts.note !== undefined ? opts.note : (scaled.note || '');
      },
    };
  }

  /* marks: [{kind: 'box'|'line'|'dash'|'thin'|'dot', colour, text}] */
  function markList(parent, marks) {
    const list = el('ul', 'cov3d-marks', parent);
    marks.forEach((mark) => {
      const item = el('li', null, list);
      const swatch = el('span', 'sw ' + (mark.kind || 'box'), item);
      if (mark.kind === 'line' || mark.kind === 'dash' || mark.kind === 'thin') swatch.style.borderColor = mark.colour;
      else {
        swatch.style.background = mark.colour;
        if (mark.colour === '#fff' || mark.colour === '#ffffff') swatch.style.border = '1px solid #cfcec8';
      }
      el('span', null, item, mark.text);
    });
    return list;
  }

  /* ── the stage: renderer, z-up orbit camera, labels, gizmo, hover ─────── */

  const ANCHORS = {
    center: 'translate(-50%, -50%)', left: 'translate(0, -50%)', right: 'translate(-100%, -50%)',
    above: 'translate(-50%, -100%)', below: 'translate(-50%, 0)',
  };

  function createStage(parent, options) {
    options = options || {};
    const heightFor = options.heightFor || ((width) => clamp(Math.round(width * 0.62), 320, 560));
    const wrap = el('div', 'cov3d-stage', parent);
    const canvas = el('canvas', null, wrap); // the figure's FIRST canvas: the acceptance test reads its pixels
    const labelLayer = el('div', 'cov3d-labels', wrap);
    const tip = el('div', 'cov3d-tip', wrap);
    el('div', 'cov3d-hint', wrap, 'drag: orbit · wheel: zoom · right-drag: pan · double-click: fit');

    const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
    renderer.setClearColor(0xffffff, 1);
    renderer.autoClear = false;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    const content = new THREE.Group();
    scene.add(content);
    const camera = new THREE.PerspectiveCamera(30, 1.6, 0.001, 1000);
    camera.up.set(0, 0, 1);

    const view = { theta: -Math.PI / 4, phi: Math.PI / 3, radius: 3, target: new THREE.Vector3() };
    const home = { theta: -Math.PI / 4, phi: Math.PI / 3, center: new THREE.Vector3(), radius: 1, margin: 1.08, points: null };
    let width = 0;
    let height = 0;
    let scheduled = false;
    let disposed = false;
    let touched = false; // the reader moved the camera: a resize keeps their view
    let fitted = false;
    let labels = [];
    let pick = null;
    let lastFrame = 0;

    function applyCamera() {
      const sinPhi = Math.sin(view.phi);
      camera.position.set(
        view.target.x + view.radius * sinPhi * Math.cos(view.theta),
        view.target.y + view.radius * sinPhi * Math.sin(view.theta),
        view.target.z + view.radius * Math.cos(view.phi));
      camera.lookAt(view.target);
      camera.near = view.radius / 200;
      camera.far = view.radius * 20;
      camera.updateProjectionMatrix();
      requestRender();
    }

    /* The tightest camera distance that shows every home point from the home direction, the points centred on
     * screen (a bounding sphere would leave a box drawn at a third of the canvas). */
    function fit() {
      view.theta = home.theta;
      view.phi = home.phi;
      const tanV = Math.tan(camera.fov * Math.PI / 360);
      const tanH = tanV * (camera.aspect || 1.6);
      if (!home.points) {
        view.target.copy(home.center);
        view.radius = home.radius * home.margin / Math.sin(Math.atan(Math.min(tanV, tanH)));
      } else {
        const sinPhi = Math.sin(home.phi);
        const forward = new THREE.Vector3(-sinPhi * Math.cos(home.theta), -sinPhi * Math.sin(home.theta), -Math.cos(home.phi));
        const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
        const up = new THREE.Vector3().crossVectors(right, forward);
        const target = home.center.clone();
        const rel = new THREE.Vector3();
        const distanceFor = () => {
          let distance = 0;
          home.points.forEach((p) => {
            rel.subVectors(p, target);
            const z = rel.dot(forward);
            distance = Math.max(distance, home.margin * Math.abs(rel.dot(right)) / tanH - z,
              home.margin * Math.abs(rel.dot(up)) / tanV - z);
          });
          return distance;
        };
        for (let pass = 0; pass < 4; pass++) {
          const distance = distanceFor();
          let x0 = Infinity; let x1 = -Infinity; let y0 = Infinity; let y1 = -Infinity;
          home.points.forEach((p) => {
            rel.subVectors(p, target);
            const depth = rel.dot(forward) + distance;
            const sx = rel.dot(right) / depth;
            const sy = rel.dot(up) / depth;
            x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
          });
          target.addScaledVector(right, (x0 + x1) / 2 * distance).addScaledVector(up, (y0 + y1) / 2 * distance);
        }
        view.target.copy(target);
        view.radius = Math.max(distanceFor(), home.radius * 0.2);
      }
      touched = false;
      fitted = width > 0;
      applyCamera();
    }

    /* Where double-click returns to: a viewing direction (theta from +x, phi from +z) and what must fit, either
     * {box: [min, max], extra: [points]} or a sphere {center, radius}. */
    function setHome(spec) {
      home.theta = spec.theta === undefined ? -Math.PI / 4 : spec.theta;
      home.phi = spec.phi === undefined ? Math.PI / 3 : spec.phi;
      home.margin = spec.margin || 1.06;
      if (spec.box) {
        const [lo, hi] = spec.box;
        const points = [];
        for (let i = 0; i < 8; i++) points.push([i & 1 ? hi[0] : lo[0], i & 2 ? hi[1] : lo[1], i & 4 ? hi[2] : lo[2]]);
        (spec.extra || []).forEach((p) => points.push(p));
        home.points = points.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
        home.center.set((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
        home.radius = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
      } else {
        home.points = null;
        home.center.set(spec.center[0], spec.center[1], spec.center[2]);
        home.radius = spec.radius;
      }
      fit();
    }

    // three.js' own orientation gizmo, as in viewer3d.js; a plain axes triad if the page did not inline it.
    const viewHelper = THREE.ViewHelper ? new THREE.ViewHelper(camera, canvas) : null;
    const fallbackGizmo = viewHelper ? null : makeFallbackGizmo();

    function syncViewFromCamera() {
      const offset = camera.position.clone().sub(view.target);
      view.radius = Math.max(offset.length(), 1e-6);
      view.theta = Math.atan2(offset.y, offset.x);
      view.phi = clamp(Math.acos(offset.z / view.radius), 0.03, Math.PI - 0.03);
    }

    function inGizmo(px, py) {
      return viewHelper && px >= width - GIZMO_SIZE && px <= width && py >= height - GIZMO_SIZE && py <= height;
    }

    let dragging = null;
    let hoverEvent = null;
    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('pointerdown', (event) => {
      const box = canvas.getBoundingClientRect();
      if (inGizmo(event.clientX - box.left, event.clientY - box.top)) {
        dragging = { mode: 'gizmo', x: event.clientX, y: event.clientY };
        return;
      }
      canvas.setPointerCapture(event.pointerId);
      dragging = { mode: (event.button === 2 || event.shiftKey || event.ctrlKey) ? 'pan' : 'orbit',
        x: event.clientX, y: event.clientY };
      tip.style.display = 'none';
    });
    canvas.addEventListener('pointermove', (event) => {
      const box = canvas.getBoundingClientRect();
      canvas.style.cursor = inGizmo(event.clientX - box.left, event.clientY - box.top) ? 'pointer' : '';
      if (!dragging) { hoverEvent = event; requestRender(); return; }
      if (dragging.mode === 'gizmo') return;
      const dx = event.clientX - dragging.x;
      const dy = event.clientY - dragging.y;
      dragging.x = event.clientX;
      dragging.y = event.clientY;
      touched = true;
      if (dragging.mode === 'orbit') {
        view.theta -= dx * 0.006;
        view.phi = clamp(view.phi - dy * 0.006, 0.03, Math.PI - 0.03);
      } else {
        const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
        const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        const step = view.radius * 0.0016;
        view.target.addScaledVector(right, -dx * step).addScaledVector(up, dy * step);
      }
      applyCamera();
    });
    canvas.addEventListener('pointerup', (event) => {
      if (dragging && dragging.mode === 'gizmo') {
        const moved = Math.abs(event.clientX - dragging.x) + Math.abs(event.clientY - dragging.y);
        if (moved < 5) {
          viewHelper.center.copy(view.target);
          if (viewHelper.handleClick(event)) { touched = true; requestRender(); }
        }
      }
      dragging = null;
    });
    canvas.addEventListener('pointerleave', () => { hoverEvent = null; tip.style.display = 'none'; });
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      touched = true;
      view.radius = clamp(view.radius * Math.exp(event.deltaY * 0.0012), home.radius * 0.05, home.radius * 40);
      applyCamera();
    }, { passive: false });
    canvas.addEventListener('dblclick', (event) => {
      const box = canvas.getBoundingClientRect();
      if (!inGizmo(event.clientX - box.left, event.clientY - box.top)) fit();
    });

    const raycaster = new THREE.Raycaster();
    function runPick() {
      const event = hoverEvent;
      hoverEvent = null;
      if (!pick || !event || !width) return;
      const box = canvas.getBoundingClientRect();
      const px = event.clientX - box.left;
      const py = event.clientY - box.top;
      if (inGizmo(px, py)) { tip.style.display = 'none'; return; }
      raycaster.setFromCamera(new THREE.Vector2(px / width * 2 - 1, -(py / height) * 2 + 1), camera);
      raycaster.params.Line.threshold = home.radius * 0.012;
      const text = pick(raycaster);
      if (!text) { tip.style.display = 'none'; return; }
      tip.textContent = text;
      tip.style.display = 'block';
      const left = px + 14 + tip.offsetWidth > width ? px - 14 - tip.offsetWidth : px + 14;
      tip.style.transform = `translate(${Math.max(0, left)}px, ${Math.max(0, py - 28)}px)`;
    }

    const projected = new THREE.Vector3();
    const ray = new THREE.Vector3();
    function behindSphere(position, radius) {
      ray.subVectors(position, camera.position);
      const length = ray.length();
      ray.divideScalar(length);
      const b = camera.position.dot(ray);
      const disc = b * b - (camera.position.lengthSq() - radius * radius);
      if (disc < 0) return false;
      const t = -b - Math.sqrt(disc);
      return t > 0 && t < length - 1e-4;
    }
    function projectLabels() {
      for (const label of labels) {
        projected.copy(label.position).project(camera);
        if (label.hidden || projected.z > 1 || projected.z < -1 || (label.occluder && behindSphere(label.position, label.occluder))) {
          label.node.style.display = 'none';
          continue;
        }
        label.node.style.display = '';
        const x = (projected.x + 1) / 2 * width;
        const y = (1 - projected.y) / 2 * height;
        label.node.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) ${ANCHORS[label.anchor] || ANCHORS.center}`;
      }
    }

    function render() {
      if (disposed || !width) return;
      renderer.setViewport(0, 0, width, height);
      renderer.clear();
      renderer.render(scene, camera);
      if (viewHelper) viewHelper.render(renderer);
      else fallbackGizmo.render(renderer, camera, width);
      projectLabels();
    }

    function frame(now) {
      scheduled = false;
      if (disposed) return;
      const delta = Math.min(0.1, (now - lastFrame) / 1000) || 0;
      lastFrame = now;
      if (viewHelper && viewHelper.animating) {
        viewHelper.update(delta);
        syncViewFromCamera();
        applyCamera(); // re-impose z up: ViewHelper animates in its own frame
      }
      render();
      runPick();
    }

    function requestRender() {
      if (scheduled || disposed) return;
      scheduled = true;
      lastFrame = lastFrame || performance.now();
      requestAnimationFrame(frame);
    }

    function resize() {
      const w = wrap.clientWidth;
      if (!w) { width = 0; return; }
      const h = Math.round(heightFor(w));
      if (w === width && h === height) return;
      width = w;
      height = h;
      renderer.setSize(w, h, false);
      canvas.style.height = h + 'px';
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (!fitted || !touched) fit();
      requestRender();
    }
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    if (observer) observer.observe(wrap);
    else global.addEventListener('resize', resize);

    function label(text, position, className, anchor, opts) {
      const node = el('div', 'cov3d-label' + (className ? ' ' + className : ''), labelLayer, text);
      const item = { node: node, position: new THREE.Vector3(position[0], position[1], position[2]),
        anchor: anchor || 'center', hidden: false, occluder: opts && opts.occluder };
      labels.push(item);
      requestRender();
      return item;
    }

    function removeLabels(items) {
      const drop = new Set(items);
      labels = labels.filter((item) => { if (drop.has(item)) { item.node.remove(); return false; } return true; });
    }

    function clear() {
      content.children.slice().forEach((child) => { content.remove(child); disposeObject(child); });
      labels.forEach((item) => item.node.remove());
      labels = [];
      pick = null;
      tip.style.display = 'none';
      requestRender();
    }

    function dispose() {
      disposed = true;
      if (observer) observer.disconnect(); else global.removeEventListener('resize', resize);
      clear();
      disposeObject(scene);
      if (viewHelper) disposeObject(viewHelper);
      if (fallbackGizmo) fallbackGizmo.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      wrap.remove();
    }

    resize();
    return {
      wrap, canvas, scene, content, camera, renderer,
      add(object) { content.add(object); requestRender(); return object; },
      remove(object) { content.remove(object); disposeObject(object); requestRender(); },
      label, removeLabels, clear, setHome, fit, requestRender, dispose,
      setPick(fn) { pick = fn; },
    };
  }

  /* A non-interactive x / y / z triad for pages that did not inline three.js' ViewHelper. */
  function makeFallbackGizmo() {
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1.5, 1.5, 1.5, -1.5, 0.1, 10);
    const forward = new THREE.Vector3();
    const textures = [];
    ['X', 'Y', 'Z'].forEach((name, axis) => {
      const direction = new THREE.Vector3(axis === 0 ? 1 : 0, axis === 1 ? 1 : 0, axis === 2 ? 1 : 0);
      scene.add(new THREE.ArrowHelper(direction, new THREE.Vector3(), 1, colour(AXIS_COLOURS[axis]), 0.25, 0.14));
      const paper = document.createElement('canvas');
      paper.width = 64; paper.height = 64;
      const g = paper.getContext('2d');
      g.fillStyle = AXIS_COLOURS[axis];
      g.font = 'bold 40px sans-serif';
      g.textAlign = 'center';
      g.fillText(name, 32, 46);
      const texture = new THREE.CanvasTexture(paper);
      texture.colorSpace = THREE.SRGBColorSpace;
      textures.push(texture);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture }));
      sprite.position.copy(direction).multiplyScalar(1.3);
      sprite.scale.setScalar(0.45);
      scene.add(sprite);
    });
    return {
      render(renderer, mainCamera, width) {
        mainCamera.getWorldDirection(forward);
        camera.position.copy(forward).multiplyScalar(-4);
        camera.quaternion.copy(mainCamera.quaternion);
        renderer.clearDepth();
        renderer.setViewport(width - 100, 4, 96, 96);
        renderer.render(scene, camera);
      },
      dispose() { disposeObject(scene); textures.forEach((t) => t.dispose()); },
    };
  }

  /* ── geometry helpers ──────────────────────────────────────────────────── */

  function segments(points, hex, opts) {
    opts = opts || {};
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(points), 3));
    const settings = { color: colour(hex) };
    if (opts.opacity !== undefined && opts.opacity < 1) {
      settings.transparent = true; settings.opacity = opts.opacity; settings.depthWrite = false;
    }
    let material;
    if (opts.dash) {
      material = new THREE.LineDashedMaterial(Object.assign(settings, { dashSize: opts.dash, gapSize: opts.dash * 0.7 }));
    } else {
      material = new THREE.LineBasicMaterial(settings);
    }
    const lines = new THREE.LineSegments(geometry, material);
    if (opts.dash) lines.computeLineDistances();
    if (opts.order !== undefined) lines.renderOrder = opts.order;
    return lines;
  }

  function polylineToSegments(points, out) {
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1];
      const b = points[i];
      out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
    return out;
  }

  /* A bold path for the highlighted trajectory: a tube, because WebGL lines are always 1 px. */
  function tube(points, radius, hex) {
    const group = new THREE.Group();
    const vectors = [];
    points.forEach((p) => {
      const v = new THREE.Vector3(p[0], p[1], p[2]);
      if (!vectors.length || v.distanceTo(vectors[vectors.length - 1]) > radius * 0.25) vectors.push(v);
    });
    if (vectors.length < 2) return group;
    const curve = new THREE.CatmullRomCurve3(vectors, false, 'catmullrom', 0.2);
    const material = new THREE.MeshBasicMaterial({ color: colour(hex) });
    group.add(new THREE.Mesh(new THREE.TubeGeometry(curve, Math.min(1600, vectors.length * 3), radius, 6, false), material));
    const start = new THREE.Mesh(new THREE.SphereGeometry(radius * 2.6, 14, 10), material);
    start.position.copy(vectors[0]);
    const end = new THREE.Mesh(new THREE.BoxGeometry(radius * 4.2, radius * 4.2, radius * 4.2), material);
    end.position.copy(vectors[vectors.length - 1]);
    group.add(start, end);
    return group;
  }

  /* A unit box whose faces carry a fixed shade (vertex colour x instance colour): top true colour, sides darker,
   * so stacked cells read as solids without lights changing the colormap's colours. base: z from 0 to 1. */
  function shadedBox(base) {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    if (base) geometry.translate(0, 0, 0.5);
    // BoxGeometry face order: +x, -x, +y, -y, +z, -z (4 vertices each); shades in sRGB terms
    const shades = [0.80, 0.76, 0.86, 0.90, 1.0, 0.70];
    const values = new Float32Array(24 * 3);
    shades.forEach((shade, face) => {
      const linear = Math.pow(shade, 2.2);
      for (let v = 0; v < 4; v++) values.set([linear, linear, linear], (face * 4 + v) * 3);
    });
    geometry.setAttribute('color', new THREE.BufferAttribute(values, 3));
    return geometry;
  }

  function instanced(geometry, count, opts) {
    opts = opts || {};
    const material = new THREE.MeshBasicMaterial({ vertexColors: !!opts.vertexColors, color: 0xffffff });
    if (opts.opacity !== undefined && opts.opacity < 1) {
      material.transparent = true; material.opacity = opts.opacity; material.depthWrite = false;
    }
    const mesh = new THREE.InstancedMesh(geometry, material, Math.max(1, count));
    mesh.count = count;
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, count) * 3), 3);
    return mesh;
  }

  function paintInstances(mesh, count, rgbOf) {
    const array = mesh.instanceColor.array;
    for (let k = 0; k < count; k++) putRGB(array, k * 3, rgbOf(k));
    mesh.instanceColor.needsUpdate = true;
  }

  /* A labelled box frame: the floor outline, a light floor grid at the x / y ticks, a vertical z ruler at the
   * (min x, min y) corner, tick values at each axis and the axis names. Edges are placed for the default view from
   * +x / -y (front: y = min, right: x = max). frame = {min, max, x: {title, ticks: [{f, label}]}, y, z, grid}. */
  function addFrame(stage, frame) {
    const min = frame.min;
    const max = frame.max;
    const size = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
    const s = Math.max(size[0], size[1], size[2]);
    const tick = s * 0.016;
    const gap = s * 0.045;
    const group = new THREE.Group();
    const framePts = [];
    const gridPts = [];
    const z0 = min[2];
    framePts.push(min[0], min[1], z0, max[0], min[1], z0, max[0], min[1], z0, max[0], max[1], z0,
      max[0], max[1], z0, min[0], max[1], z0, min[0], max[1], z0, min[0], min[1], z0);
    const own = [];
    const anchors = [];
    const mark = (text, position, cls, anchor) => { anchors.push(position); own.push(stage.label(text, position, cls, anchor)); };
    (frame.x.ticks || []).forEach((t) => {
      const x = min[0] + t.f * size[0];
      if (frame.grid !== false) gridPts.push(x, min[1], z0, x, max[1], z0);
      framePts.push(x, min[1], z0, x, min[1] - tick, z0);
      mark(t.label, [x, min[1] - gap, z0], 'tick', 'center');
    });
    if (frame.x.title) mark(frame.x.title, [min[0] + size[0] / 2, min[1] - gap * 2.6, z0], 'axis', 'center');
    (frame.y.ticks || []).forEach((t) => {
      const y = min[1] + t.f * size[1];
      if (frame.grid !== false) gridPts.push(min[0], y, z0, max[0], y, z0);
      framePts.push(max[0], y, z0, max[0] + tick, y, z0);
      mark(t.label, [max[0] + gap * 0.8, y, z0], 'tick', 'left');
    });
    if (frame.y.title) mark(frame.y.title, [max[0] + gap * 0.8, max[1] + gap * 1.6, z0], 'axis', 'left');
    if (gridPts.length) group.add(segments(gridPts, GRID));
    group.add(segments(framePts, FRAME));
    stage.add(group);

    let zGroup = null;
    let zLabels = [];
    // the z ruler stands at the corner that is leftmost in the home view: the back-left one when the camera looks
    // along +y (ridges), else the front-left one; its words go to -x, away from the x ticks (which go to -y)
    const theta = frame.theta === undefined ? -Math.PI / 4 : frame.theta;
    const zy = Math.abs(theta + Math.PI / 2) < 0.45 ? max[1] : min[1];
    function setZ(zAxis) {
      if (zGroup) stage.remove(zGroup);
      stage.removeLabels(zLabels);
      zLabels = [];
      zGroup = null;
      if (!zAxis || !(size[2] > 0)) return;
      const pts = [min[0], zy, min[2], min[0], zy, max[2]];
      (zAxis.ticks || []).forEach((t) => {
        const z = min[2] + t.f * size[2];
        pts.push(min[0], zy, z, min[0] - tick, zy, z);
        zLabels.push(stage.label(t.label, [min[0] - gap * 0.8, zy, z], 'tick', 'right'));
      });
      if (zAxis.title) zLabels.push(stage.label(zAxis.title, [min[0], zy, max[2] + gap * 0.9], 'axis', 'above'));
      zGroup = stage.add(segments(pts, FRAME));
    }
    setZ(frame.z);
    anchors.push([min[0] - gap * 1.8, zy, max[2] + gap * 1.4], [min[0] - gap * 1.8, zy, min[2]]);
    return { setZ, group, gap, size: s, anchors, box: [min, max] };
  }

  /* WHY from payload.tool.frame, never a hard-coded "robot base" / "base frame": the UR5e cell pages give the tool in
   * the CELL frame (the arm hangs upside down there), so the origin is the robot base only when the frame says so. */
  function frameName(tool) {
    return String((tool && tool.frame) || 'base');
  }

  function originLabel(tool) {
    const frame = frameName(tool);
    return frame === 'base' || frame === 'base_link' ? 'robot base' : `origin of "${frame}"`;
  }

  function frameAxesText(tool) {
    const frame = frameName(tool);
    return frame === 'base' || frame === 'base_link' ? 'robot base' : `"${frame}" axes`;
  }

  function addBaseMarker(stage, length, tool) {
    const pts = [];
    const group = new THREE.Group();
    [[1, 0, 0], [0, 1, 0], [0, 0, 1]].forEach((d, axis) => {
      group.add(segments([0, 0, 0, d[0] * length, d[1] * length, d[2] * length], AXIS_COLOURS[axis]));
    });
    pts.length = 0;
    stage.add(group);
    stage.label(originLabel(tool), [0, 0, -length * 0.35], 'chip', 'below');
    return group;
  }

  /* ── colour through the page's scale ───────────────────────────────────── */

  function scaled(counts, ctx) {
    return CC.scale(counts, ctx.scale, { enough: ctx.enough });
  }

  function scaleTitle(ctx) {
    return (CC.SCALE_TITLES && CC.SCALE_TITLES[ctx.scale]) || ctx.scale;
  }

  /* ── sphere pieces (orientation view, hedgehog proposal) ───────────────── */

  /* The 288 equal-area cells as flat-coloured patches: ring k covers base-z in [-1 + 2k/rings, ...), sector s covers
   * azimuth [-pi + s 2pi/sectors, ...); each cell is sub x sub quads so the patch follows the sphere. */
  function sphereCells(rings, sectors, radius, sub) {
    const trisPerCell = 2 * sub * sub;
    const cells = rings * sectors;
    const positions = new Float32Array(cells * trisPerCell * 9);
    const colours = new Float32Array(cells * trisPerCell * 9);
    let at = 0;
    const point = (z, azimuth) => {
      const r = Math.sqrt(Math.max(0, 1 - z * z)) * radius;
      return [r * Math.cos(azimuth), r * Math.sin(azimuth), z * radius];
    };
    for (let k = 0; k < rings; k++) {
      const z0 = -1 + 2 * k / rings;
      const z1 = -1 + 2 * (k + 1) / rings;
      for (let s = 0; s < sectors; s++) {
        const a0 = -Math.PI + s * 2 * Math.PI / sectors;
        const a1 = a0 + 2 * Math.PI / sectors;
        for (let i = 0; i < sub; i++) {
          const za = z0 + (z1 - z0) * i / sub;
          const zb = z0 + (z1 - z0) * (i + 1) / sub;
          for (let j = 0; j < sub; j++) {
            const aa = a0 + (a1 - a0) * j / sub;
            const ab = a0 + (a1 - a0) * (j + 1) / sub;
            const p00 = point(za, aa); const p01 = point(za, ab); const p11 = point(zb, ab); const p10 = point(zb, aa);
            [p00, p01, p11, p00, p11, p10].forEach((p) => { positions.set(p, at); at += 3; });
          }
        }
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colours, 3));
    return {
      geometry,
      verticesPerCell: trisPerCell * 3,
      paint(rgbOf) {
        const per = trisPerCell * 3;
        const rgb = [];
        for (let c = 0; c < cells; c++) {
          const value = rgbOf(c);
          for (let v = 0; v < per; v++) putRGB(colours, (c * per + v) * 3, value);
          rgb.push(value);
        }
        geometry.attributes.color.needsUpdate = true;
      },
      cellOfFace(faceIndex) { return Math.floor(faceIndex / trisPerCell); },
    };
  }

  function sphereGridLines(rings, sectors, radius) {
    const pts = [];
    const steps = 96;
    for (let k = 1; k < rings; k++) {
      const z = -1 + 2 * k / rings;
      const r = Math.sqrt(1 - z * z) * radius;
      for (let i = 0; i < steps; i++) {
        const a = i / steps * 2 * Math.PI;
        const b = (i + 1) / steps * 2 * Math.PI;
        pts.push(r * Math.cos(a), r * Math.sin(a), z * radius, r * Math.cos(b), r * Math.sin(b), z * radius);
      }
    }
    for (let s = 0; s < sectors; s++) {
      const a = -Math.PI + s * 2 * Math.PI / sectors;
      for (let i = 0; i < 48; i++) {
        const z0 = -1 + 2 * i / 48;
        const z1 = -1 + 2 * (i + 1) / 48;
        const r0 = Math.sqrt(Math.max(0, 1 - z0 * z0)) * radius;
        const r1 = Math.sqrt(Math.max(0, 1 - z1 * z1)) * radius;
        pts.push(r0 * Math.cos(a), r0 * Math.sin(a), z0 * radius, r1 * Math.cos(a), r1 * Math.sin(a), z1 * radius);
      }
    }
    return segments(pts, '#cfcec7', { opacity: 0.9 });
  }

  function cellCentre(rings, sectors, cell) {
    const k = Math.floor(cell / sectors);
    const s = cell % sectors;
    const z = -1 + (2 * k + 1) / rings;
    const a = -Math.PI + (s + 0.5) * 2 * Math.PI / sectors;
    const r = Math.sqrt(Math.max(0, 1 - z * z));
    return [r * Math.cos(a), r * Math.sin(a), z];
  }

  function unit(v) {
    const n = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / n, v[1] / n, v[2] / n];
  }

  function perpendiculars(direction) {
    const d = new THREE.Vector3(direction[0], direction[1], direction[2]).normalize();
    const helper = Math.abs(d.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
    const u = new THREE.Vector3().crossVectors(d, helper).normalize();
    const v = new THREE.Vector3().crossVectors(d, u).normalize();
    return { d, u, v };
  }

  /* Base axes as stubs poking out of the sphere, with the words Zach asked for: up / down / +x / +y. */
  function sphereAxes(stage, inner, outer, reference) {
    const ref = unit(reference || [0, 0, -1]);
    const refIsDown = ref[2] < -0.98;
    const refIsUp = ref[2] > 0.98;
    const specs = [
      { d: [1, 0, 0], c: AXIS_COLOURS[0], text: '+x', cls: 'dir' },
      { d: [-1, 0, 0], c: AXIS_COLOURS[0], text: '−x', cls: 'dir faint' },
      { d: [0, 1, 0], c: AXIS_COLOURS[1], text: '+y', cls: 'dir' },
      { d: [0, -1, 0], c: AXIS_COLOURS[1], text: '−y', cls: 'dir faint' },
      { d: [0, 0, 1], c: AXIS_COLOURS[2], text: refIsUp ? 'up (+z) · tilt 0°' : 'up (+z)', cls: 'dir' },
      { d: [0, 0, -1], c: AXIS_COLOURS[2], text: refIsDown ? 'down (−z) · tilt 0°' : 'down (−z)', cls: 'dir' },
    ];
    specs.forEach((spec) => {
      const p0 = spec.d.map((x) => x * inner);
      const p1 = spec.d.map((x) => x * outer);
      stage.add(segments(p0.concat(p1), spec.c));
      const cone = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.11, 12), new THREE.MeshBasicMaterial({ color: colour(spec.c) }));
      cone.position.set(p1[0], p1[1], p1[2]);
      cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(spec.d[0], spec.d[1], spec.d[2]));
      stage.add(cone);
      stage.label(spec.text, spec.d.map((x) => x * (outer + 0.12)), spec.cls, 'center', { occluder: 0.999 });
    });
    if (!refIsDown && !refIsUp) {
      const p1 = ref.map((x) => x * outer);
      stage.add(segments(ref.map((x) => x * inner).concat(p1), INK));
      stage.label('reference · tilt 0°', ref.map((x) => x * (outer + 0.16)), 'dir', 'center', { occluder: 0.999 });
    }
  }

  /* Dashed circles at fixed tilts from the reference, so "how far it leans" reads off the sphere. */
  function tiltCircles(stage, reference, radius, tilts) {
    const { d, u, v } = perpendiculars(reference);
    tilts.forEach((tilt) => {
      const a = tilt * Math.PI / 180;
      const pts = [];
      const steps = 120;
      let previous = null;
      for (let i = 0; i <= steps; i++) {
        const phi = i / steps * 2 * Math.PI;
        const p = d.clone().multiplyScalar(Math.cos(a))
          .addScaledVector(u, Math.sin(a) * Math.cos(phi)).addScaledVector(v, Math.sin(a) * Math.sin(phi))
          .multiplyScalar(radius);
        if (previous) pts.push(previous.x, previous.y, previous.z, p.x, p.y, p.z);
        previous = p;
      }
      stage.add(segments(pts, INK, { order: 3 }));
      stage.add(segments(pts, '#ffffff', { dash: 0.05, order: 4 }));
      // the label sits on the circle's side facing +x / -y (the default camera's side)
      const side = new THREE.Vector3(1, -1, 0).normalize();
      const along = side.clone().sub(d.clone().multiplyScalar(side.dot(d)));
      if (along.length() < 1e-3) along.copy(u);
      along.normalize();
      const at = d.clone().multiplyScalar(Math.cos(a)).addScaledVector(along, Math.sin(a)).multiplyScalar(radius * 1.03);
      stage.label(`tilt ${tilt}°`, [at.x, at.y, at.z], 'chip', 'left', { occluder: 0.999 });
    });
  }

  function degrees(radians) { return radians * 180 / Math.PI; }

  function plural(count, word) { return `${count} ${word}${count === 1 ? '' : 's'}`; }

  /* ── view: voxels ──────────────────────────────────────────────────────── */

  function boundsFrame(stage, tool, zTitle) {
    const [lo, hi] = tool.bounds;
    const axis = (i, name) => {
      const ticks = niceTicks(lo[i] * 1000, hi[i] * 1000, 4).map((v) => ({ f: (v / 1000 - lo[i]) / (hi[i] - lo[i]), label: fmt(v) }));
      return { title: name, ticks };
    };
    return addFrame(stage, { min: lo, max: hi, x: axis(0, 'x (mm)'), y: axis(1, 'y (mm)'),
      z: zTitle === null ? null : axis(2, zTitle || 'z (mm)') });
  }

  function homeOnBounds(stage, frame) {
    stage.setHome({ box: frame.box, extra: frame.anchors, theta: -Math.PI / 4, phi: 1.08 });
  }

  function mountVoxels(body, payload, ctx) {
    const tool = payload.tool;
    const voxels = tool.voxels;
    const size = voxels.size;
    const origin = voxels.origin;
    const cells = voxels.cells.slice().sort((a, b) => b[3] - a[3]); // most samples first: a threshold is a count
    const stage = createStage(body);
    const controls = el('div', 'cov3d-controls', body);
    const legend = el('div', 'cov3d-legend', body);
    legend.setAttribute('data-cov-legend', '');

    const centre = (c) => [origin[0] + (c[0] + 0.5) * size, origin[1] + (c[1] + 0.5) * size, origin[2] + (c[2] + 0.5) * size];
    const mesh = instanced(shadedBox(false), cells.length, { vertexColors: true });
    const matrix = new THREE.Matrix4();
    cells.forEach((cell, k) => {
      const p = centre(cell);
      matrix.makeScale(size * 0.9, size * 0.9, size * 0.9).setPosition(p[0], p[1], p[2]);
      mesh.setMatrixAt(k, matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
    stage.add(mesh);

    // reachable but never visited: faint grey specks, so the empty part of the workspace is visible, not blank
    let reachableMesh = null;
    if (voxels.reachable && voxels.reachable.length) {
      const visited = new Set(voxels.cells.map((c) => c[0] + ',' + c[1] + ',' + c[2]));
      const empty = voxels.reachable.filter((c) => !visited.has(c[0] + ',' + c[1] + ',' + c[2]));
      reachableMesh = instanced(new THREE.BoxGeometry(1, 1, 1), empty.length, { opacity: 0.35 });
      empty.forEach((cell, k) => {
        const p = centre(cell);
        matrix.makeScale(size * 0.32, size * 0.32, size * 0.32).setPosition(p[0], p[1], p[2]);
        reachableMesh.setMatrixAt(k, matrix);
      });
      paintInstances(reachableMesh, empty.length, () => hexRGB(REACHABLE_GREY));
      reachableMesh.instanceMatrix.needsUpdate = true;
      reachableMesh.userData.count = empty.length;
      stage.add(reachableMesh);
    }

    const frame = boundsFrame(stage, tool);
    addBaseMarker(stage, Math.max(0.06, size * 1.6), tool);
    homeOnBounds(stage, frame);

    // threshold: "show voxels with >= N samples" (log slider: counts span decades)
    const top = cells.length ? cells[0][3] : 1;
    const sliderLabel = el('label', null, controls);
    sliderLabel.appendChild(document.createTextNode('show voxels with ≥'));
    const slider = el('input', null, sliderLabel);
    slider.type = 'range'; slider.min = 0; slider.max = 100; slider.step = 1; slider.value = 0;
    const output = el('output', null, sliderLabel);
    function applyThreshold() {
      const threshold = Math.max(1, Math.round(Math.exp(Math.log(Math.max(1, top)) * slider.value / 100)));
      let shown = 0;
      while (shown < cells.length && cells[shown][3] >= threshold) shown++;
      mesh.count = shown;
      output.textContent = `${threshold} samples · ${shown} of ${cells.length} voxels`;
      stage.requestRender();
    }
    slider.addEventListener('input', applyThreshold);
    applyThreshold();
    if (reachableMesh) {
      const toggle = el('label', null, controls);
      const box = el('input', null, toggle);
      box.type = 'checkbox'; box.checked = true;
      toggle.appendChild(document.createTextNode(`reachable, never visited (${reachableMesh.userData.count} grey specks)`));
      box.addEventListener('change', () => { reachableMesh.visible = box.checked; stage.requestRender(); });
    }

    const bar = colorbar(legend, `samples per ${Math.round(size * 1000)} mm voxel`);
    const crossedOnly = cells.filter((c) => !(c[3] > 0)).length;
    const marks = [
      { kind: 'box', colour: '#ffffff', text: 'no cube = the tool never entered that voxel' +
        (crossedOnly ? ` (${crossedOnly} more voxels were crossed between two samples, with none inside: not drawn)` : '') },
    ];
    if (reachableMesh) marks.push({ kind: 'dot', colour: REACHABLE_GREY, text: 'grey speck = reachable by the robot, never visited' });
    marks.push({ kind: 'thin', colour: FRAME, text: `box + floor grid = the data bounds, ticks in mm (${frameName(tool)} frame)` });
    marks.push({ kind: 'line', colour: AXIS_COLOURS[0], text: `${frameAxesText(tool)}: red x, green y, blue z` });
    marks.push({ kind: 'line', colour: HIGHLIGHT, text: 'orange tube = the trajectory picked in the table' });
    markList(legend, marks);

    let highlightObject = null;
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(mesh, false)[0];
      if (!hit || hit.instanceId === undefined) return null;
      const cell = cells[hit.instanceId];
      const p = centre(cell).map((v) => Math.round(v * 1000));
      return `x ${fmt(p[0])}, y ${fmt(p[1])}, z ${fmt(p[2])} mm · ${plural(cell[3], 'sample')} · ${cell[4] === 1 ? '1 trajectory' : cell[4] + ' trajectories'} · max speed ${fmt(cell[5] * 1000)} mm/s`;
    });

    function recolour(next) {
      ctx = normalise(next, payload);
      const scale = scaled(cells.map((c) => c[3]), ctx);
      paintInstances(mesh, cells.length, (k) => ctx.ramp(Math.max(0, scale.t[k])));
      bar.paint(scale, ctx.ramp, { note: `${scaleTitle(ctx)} · ${scale.note}` });
      bar.setEmpty('no cube = none');
      stage.requestRender();
    }
    recolour(ctx);

    return {
      update: recolour,
      highlight(index) {
        if (highlightObject) { stage.remove(highlightObject); highlightObject = null; }
        const path = index === null || index === undefined ? null : (tool.spaghetti || [])[index];
        if (path) highlightObject = stage.add(tube(path, size * 0.09, HIGHLIGHT));
        stage.requestRender();
      },
      dispose() { stage.dispose(); controls.remove(); legend.remove(); },
    };
  }

  /* ── view: spaghetti ───────────────────────────────────────────────────── */

  function mountSpaghetti(body, payload, ctx) {
    const tool = payload.tool;
    const paths = tool.spaghetti || [];
    const names = (payload.trajectories || []).map((t) => t.name);
    const stage = createStage(body);
    const legend = el('div', 'cov3d-legend', body);
    legend.setAttribute('data-cov-legend', '');

    const pts = [];
    const starts = []; // first segment index of each trajectory
    paths.forEach((path) => { starts.push(pts.length / 6); polylineToSegments(path, pts); });
    // WHY low opacity, one ink (Strava's heatmap): overlap darkens, so the well-trodden routes read without a colour key
    const opacity = clamp(6 / Math.sqrt(Math.max(1, paths.length)), 0.12, 0.9);
    const lines = segments(pts, '#000000', { opacity: opacity });
    stage.add(lines);
    const frame = boundsFrame(stage, tool);
    addBaseMarker(stage, Math.max(0.06, frame.size * 0.06), tool);
    homeOnBounds(stage, frame);

    const ink = el('div', null, legend);
    const marks = markList(ink, []);
    function writeMarks() {
      marks.textContent = '';
      const inkHex = CC.css(darkEnd(ctx.ramp));
      [{ kind: 'line', colour: inkHex, text: `one line = one trajectory's tool path (TCP, ${frameName(tool)} frame): ${paths.length} trajectories, ≤ ${Math.max(0, ...paths.map((p) => p.length))} points each` },
        { kind: 'thin', colour: inkHex, text: `drawn at ${Math.round(opacity * 100)} % opacity: darker = more trajectories pass there` },
        { kind: 'line', colour: HIGHLIGHT, text: 'orange tube = the trajectory picked in the table (ball = start, cube = end)' },
        { kind: 'thin', colour: FRAME, text: 'box + floor grid = the data bounds, ticks in mm' },
        { kind: 'line', colour: AXIS_COLOURS[0], text: `${frameAxesText(tool)}: red x, green y, blue z · hover a line for its name` },
      ].forEach((m) => {
        const item = el('li', null, marks);
        const sw = el('span', 'sw ' + m.kind, item);
        sw.style.borderColor = m.colour;
        el('span', null, item, m.text);
      });
    }

    let highlightObject = null;
    let highlightLabel = null;
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(lines, false)[0];
      if (!hit) return null;
      const segment = Math.floor(hit.index / 2);
      let lo = 0; let hi = starts.length - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (starts[mid] <= segment) lo = mid; else hi = mid - 1; }
      return `${names[lo] || 'trajectory ' + (lo + 1)} (#${lo + 1})`;
    });

    function recolour(next) {
      ctx = normalise(next, payload);
      lines.material.color.copy(colour(darkEnd(ctx.ramp)));
      writeMarks();
      stage.requestRender();
    }
    recolour(ctx);

    return {
      update: recolour,
      highlight(index) {
        if (highlightObject) { stage.remove(highlightObject); highlightObject = null; }
        if (highlightLabel) { stage.removeLabels([highlightLabel]); highlightLabel = null; }
        const path = index === null || index === undefined ? null : paths[index];
        lines.material.opacity = path ? opacity * 0.55 : opacity;
        if (path) {
          highlightObject = stage.add(tube(path, frame.size * 0.0035, HIGHLIGHT));
          highlightLabel = stage.label(names[index] || `trajectory ${index + 1}`, path[0], 'hi', 'above');
        }
        stage.requestRender();
      },
      dispose() { stage.dispose(); legend.remove(); },
    };
  }

  /* ── view: orientation sphere ──────────────────────────────────────────── */

  function sphereHome(stage, sphere, reference) {
    // look at where the counts are (their mean direction), lifted toward the horizon so "up" stays up
    let m = [0, 0, 0];
    sphere.counts.forEach((count, cell) => {
      if (!count) return;
      const c = cellCentre(sphere.rings, sphere.sectors, cell);
      m = [m[0] + c[0] * count, m[1] + c[1] * count, m[2] + c[2] * count];
    });
    if (Math.hypot(m[0], m[1], m[2]) < 1e-9) m = reference.slice();
    m = unit(m);
    const phiData = Math.acos(clamp(m[2], -1, 1));
    const phi = Math.PI / 2 + (phiData - Math.PI / 2) * 0.45;
    const horizontal = Math.hypot(m[0], m[1]);
    const theta = horizontal > 0.2 ? Math.atan2(m[1], m[0]) + 0.45 : -Math.PI / 4;
    stage.setHome({ center: [0, 0, 0], radius: 1.5, theta: theta, phi: phi, margin: 1.0 });
  }

  function mountSphere(body, payload, ctx) {
    const orientation = payload.tool.orientation;
    const sphere = orientation.sphere;
    const reference = unit(orientation.reference || [0, 0, -1]);
    const stage = createStage(body);
    const legend = el('div', 'cov3d-legend', body);
    legend.setAttribute('data-cov-legend', '');

    const patches = sphereCells(sphere.rings, sphere.sectors, 1, 4);
    const mesh = new THREE.Mesh(patches.geometry, new THREE.MeshBasicMaterial({ vertexColors: true }));
    stage.add(mesh);
    stage.add(sphereGridLines(sphere.rings, sphere.sectors, 1.002));
    tiltCircles(stage, reference, 1.008, [30, 60, 90]);
    sphereAxes(stage, 1.0, 1.3, reference);
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 12), new THREE.MeshBasicMaterial({ color: colour(INK) }));
    dot.position.set(reference[0] * 1.01, reference[1] * 1.01, reference[2] * 1.01);
    stage.add(dot);
    sphereHome(stage, sphere, reference);

    const total = sphere.counts.reduce((a, b) => a + b, 0);
    const visitedCells = sphere.counts.filter((c) => c > 0).length;
    const bar = colorbar(legend, `samples per direction cell (${sphere.rings} rings × ${sphere.sectors} sectors, equal area)`);
    markList(legend, [
      { kind: 'box', colour: '#ffffff', text: 'white cell = the tool z axis never pointed that way' },
      { kind: 'dot', colour: INK, text: 'black dot = the reference direction (tilt 0°)' },
      { kind: 'dash', colour: INK, text: 'black-and-white circles = tilt 30° / 60° / 90° from the reference' },
      { kind: 'line', colour: AXIS_COLOURS[2], text: `stubs = "${frameName(payload.tool)}" axes: red ±x, green ±y, blue up / down` },
      { kind: 'thin', colour: '#cfcec7', text: `grey lines = cell borders · ${visitedCells} of ${sphere.counts.length} cells visited, ${total} samples` },
    ]);

    const { d, u, v } = perpendiculars(reference);
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(mesh, false)[0];
      if (!hit) return null;
      const cell = patches.cellOfFace(hit.faceIndex);
      const k = Math.floor(cell / sphere.sectors);
      const s = cell % sphere.sectors;
      const c = cellCentre(sphere.rings, sphere.sectors, cell);
      const tilt = degrees(Math.acos(clamp(c[0] * d.x + c[1] * d.y + c[2] * d.z, -1, 1)));
      const a0 = -180 + s * 360 / sphere.sectors;
      const e0 = degrees(Math.asin(-1 + 2 * k / sphere.rings));
      const e1 = degrees(Math.asin(-1 + 2 * (k + 1) / sphere.rings));
      void u; void v;
      return `tool z leans toward azimuth ${fmt(a0)}…${fmt(a0 + 360 / sphere.sectors)}°, elevation ${fmt(e0)}…${fmt(e1)}° · ≈ ${fmt(tilt)}° from the reference · ${sphere.counts[cell]} samples`;
    });

    function recolour(next) {
      ctx = normalise(next, payload);
      const scale = scaled(sphere.counts, ctx);
      patches.paint((cell) => (scale.t[cell] < 0 ? CC.EMPTY : ctx.ramp(scale.t[cell])));
      bar.paint(scale, ctx.ramp, { note: `${scaleTitle(ctx)} · ${scale.note}` });
      stage.requestRender();
    }
    recolour(ctx);

    return { update: recolour, highlight() {}, dispose() { stage.dispose(); legend.remove(); } };
  }

  /* ── proposals: shared builders ────────────────────────────────────────── */

  /* Columns on a grid: one box per visited cell, base on the floor. */
  function columns(stage, spec) {
    const { nx, ny, x0, y0, dx, dy } = spec;
    const cells = [];
    for (let i = 0; i < nx * ny; i++) if (spec.keep(i)) cells.push(i);
    const mesh = instanced(shadedBox(true), cells.length, { vertexColors: true });
    stage.add(mesh);
    const matrix = new THREE.Matrix4();
    const fill = spec.fill === undefined ? 0.92 : spec.fill;
    return {
      mesh, cells,
      setHeights(heightOf) {
        cells.forEach((i, k) => {
          const ix = Math.floor(i / ny);
          const iy = i % ny;
          matrix.makeScale(dx * fill, dy * fill, Math.max(1e-5, heightOf(i)))
            .setPosition(x0 + (ix + 0.5) * dx, y0 + (iy + 0.5) * dy, 0);
          mesh.setMatrixAt(k, matrix);
        });
        mesh.instanceMatrix.needsUpdate = true;
        mesh.computeBoundingSphere();
      },
      setColours(rgbOf) { paintInstances(mesh, cells.length, (k) => rgbOf(cells[k])); },
      cellOf(hit) { return hit && hit.instanceId !== undefined ? cells[hit.instanceId] : null; },
    };
  }

  /* Ridges (TensorBoard / W&B histograms, a joyplot in 3-D): one filled curtain per row, its top outlined, a faint
   * baseline so empty rows still show where they are. rows: [{y, xs: [world x]}]; setHeights(fn(row, j)) and
   * paint(fn(row, j) -> rgb) per column j. */
  function ridges(stage, rows) {
    let vertexCount = 0;
    rows.forEach((row) => { vertexCount += row.xs.length * 2; });
    const positions = new Float32Array(vertexCount * 3);
    const colours = new Float32Array(vertexCount * 3);
    const index = [];
    const faceRow = [];
    const baselines = [];
    let base = 0;
    let segmentCount = 0;
    rows.forEach((row, r) => {
      row.base = base;
      row.heights = row.xs.map(() => 0);
      row.xs.forEach((x, j) => {
        positions.set([x, row.y, 0], (base + j * 2) * 3);
        positions.set([x, row.y, 0], (base + j * 2 + 1) * 3);
        if (j > 0) {
          const a = base + (j - 1) * 2;
          const b = base + j * 2;
          index.push(a, b, b + 1, a, b + 1, a + 1);
          faceRow.push(r, r);
          segmentCount++;
        }
      });
      baselines.push(row.xs[0], row.y, 0, row.xs[row.xs.length - 1], row.y, 0);
      base += row.xs.length * 2;
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colours, 3));
    geometry.setIndex(index);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
    stage.add(mesh);
    stage.add(segments(baselines, '#dcdbd5'));
    const lines = stage.add(segments(new Array(segmentCount * 6).fill(0), '#2b2a2f', { opacity: 0.7 }));
    return {
      mesh, lines,
      setHeights(heightOf) {
        const outline = lines.geometry.attributes.position.array;
        let at = 0;
        rows.forEach((row, r) => {
          row.xs.forEach((x, j) => {
            row.heights[j] = Math.max(0, heightOf(r, j));
            positions[(row.base + j * 2 + 1) * 3 + 2] = row.heights[j];
            if (j === 0) return;
            const h0 = row.heights[j - 1];
            const h1 = row.heights[j];
            // a run of zeros draws nothing (both ends at one point): the baseline already says "empty"
            const x0 = h0 > 1e-6 || h1 > 1e-6 ? row.xs[j - 1] : x;
            outline.set([x0, row.y, h0, x, row.y, h1], at);
            at += 6;
          });
        });
        geometry.attributes.position.needsUpdate = true;
        geometry.computeBoundingSphere();
        lines.geometry.attributes.position.needsUpdate = true;
        lines.geometry.computeBoundingSphere();
      },
      paint(rgbOf) {
        rows.forEach((row, r) => {
          row.xs.forEach((x, j) => {
            const rgb = rgbOf(r, j);
            putRGB(colours, (row.base + j * 2) * 3, rgb);
            putRGB(colours, (row.base + j * 2 + 1) * 3, rgb);
          });
        });
        geometry.attributes.color.needsUpdate = true;
      },
      rowOfFace(faceIndex) { return faceRow[faceIndex]; },
    };
  }

  /* Histogram of values over [lo, hi] in `bins` bins, as % of the values. */
  function percentHistogram(values, lo, hi, bins) {
    const counts = new Array(bins).fill(0);
    let n = 0;
    values.forEach((v) => {
      if (v === null || !isFinite(v)) return;
      n++;
      const b = Math.floor((v - lo) / (hi - lo) * bins);
      if (b >= 0 && b < bins) counts[b]++;
    });
    return counts.map((c) => (n ? c / n * 100 : 0));
  }

  function limitOf(payload, joint, signal) {
    const limit = ((payload.limits || {})[joint] || {})[signal];
    return limit || { low: -1, high: 1, source: 'data' };
  }

  function limitWords(limit) {
    return limit.source === 'data' ? 'no limit stated: the span is the data’s p0.1…p99.9 widened ×1.15' : 'the joint’s limit';
  }

  /* ── the proposals ─────────────────────────────────────────────────────── */

  const PROPOSALS = [
    {
      id: 'height-q-qd', short: 'q × qd height map', title: 'Where does the joint spend its time, in position × speed?',
      what: 'The q × qd heatmap lifted into bars: height and colour = samples in the cell. Wins when you want the hot spots and the empty corners at once — nothing hides behind anything.',
      read: 'One bar per q × qd cell of the selected joint (36 × 24 cells spanning exactly its position and speed limits). Bar height and colour both follow the page’s scale, so equalized lifts thin cells and visited / enough flatten to a yes / no map. A missing bar is a cell never visited. Prior art: the q × qd heatmap of the Nov 19 coverage gallery, BAM Reach’s 3-D reach histograms.',
      joint: true, build: buildHeightQQd,
    },
    {
      id: 'terrain-qdd', short: 'max |qdd| terrain over q × qd', title: 'How hard does it accelerate at each position and speed?',
      what: 'Height and colour = the largest |qdd| reached in each q × qd cell; the red sheet is the acceleration limit. Wins for “something that depends on two other things”.',
      read: 'For every q × qd cell of the selected joint the payload keeps the largest |qdd| any sample in that cell reached (planes.q_qd.max_other). Bars show it as a share of the qdd limit: a bar touching the red sheet hit the limit there; a red-topped bar went past it. Unvisited cells have no bar. Prior art: a robot’s torque-speed envelope plotted as a terrain.',
      joint: true, build: buildTerrainQdd,
    },
    {
      id: 'slab-stack', short: 'q × qd slabs, stacked by qdd', title: 'Position × speed, sliced by acceleration',
      what: 'The five qdd slabs of q × qd stacked from hardest braking (bottom) to hardest accelerating (top). Wins for seeing q, qd and qdd at the same time without a voxel cloud.',
      read: 'payload.slabs splits the selected joint’s samples into five equal qdd bands and bins each band over q × qd. Each sheet is one band; empty cells are see-through, so lower sheets show through. One colour scale spans all five sheets. The end sheets also hold the samples past the qdd limit.',
      joint: true, build: buildSlabStack,
    },
    {
      id: 'phase-space-3d', short: 'q, qd, qdd lines (phase space)', title: 'Every trajectory in (position, speed, acceleration)',
      what: 'Each line is one trajectory’s path through q, qd and qdd of the selected joint, inside the red limit box. Wins for spotting the run that leaves the box, and the corners nobody visits.',
      read: 'The payload’s evenly picked path samples (≤ 400 per trajectory) drawn as 3-D lines in the joint’s q × qd × qdd limit box. Lines are faint, so overlap darkens. Pick a row in the Trajectories table to draw that trajectory bold. Prior art: the Nov 19 phase-space-3d (Rerun) proposal.',
      joint: true, build: buildPhaseSpace,
    },
    {
      id: 'hist-over-trajectories', short: 'qd histogram per trajectory', title: 'How does the speed spread change from one trajectory to the next?',
      what: 'One qd histogram per trajectory, stacked along depth in the order they were added (TensorBoard / W&B histograms). Wins for spotting the odd run out and drift over a dataset.',
      read: 'Each ridge is one trajectory’s histogram of the selected joint’s speed (qd), height = % of that trajectory’s samples in the bin. The payload has no per-trajectory histograms, so they are counted here from the evenly picked path samples (≤ 400 per trajectory, fewer for a big dataset). Red lines are the ± speed limit. Prior art: TensorBoard’s histogram dashboard (offset mode), the Nov 19 histogram-over-runs.',
      joint: true, build: buildHistOverTrajectories,
    },
    {
      id: 'joint-skyline', short: 'every joint’s range, side by side', title: 'Which joints use their whole range?',
      what: 'Every joint’s position histogram as % of its own limit range, one ridge per joint side by side: the fleet ridgeline in 3-D. Wins for comparing joints at a glance.',
      read: 'x runs from each joint’s low limit (0 %) to its high limit (100 %), with an 8 % margin either side so overshoot shows; height = % of that joint’s samples in the bin. Black ticks mark each joint’s p0.1 / p99.9. The selected joint’s name is bold. Prior art: the overview’s ridgeline, joyplots.',
      joint: false, build: buildJointSkyline,
    },
    {
      id: 'workspace-terrain', short: 'workspace floor: busy and fast', title: 'Where does the tool travel most, and how fast?',
      what: 'The xy floor of the workspace: height = how many trajectories pass through the 2 cm pixel, colour = the fastest the tool moved there. Wins for finding busy, fast lanes.',
      read: 'From tool.projections.xy (the top-down projection): one column per pixel the tool crossed. Height counts distinct trajectories (a Strava-style heatmap), colour is the maximum tool speed in the pixel. Grey floor squares are reachable but never visited (when the payload carries a reachable set).',
      tool: true, build: buildWorkspaceTerrain,
    },
    {
      id: 'direction-hedgehog', short: 'tool directions as spikes', title: 'Which ways does the tool point, and how often?',
      what: 'The orientation sphere as a hedgehog: one spike per direction cell, length and colour = samples. Wins when a few directions dominate and the flat sphere hides how much.',
      read: (payload) => `The 288 equal-area direction cells of the tool z axis (${frameName(payload.tool)} frame); each visited cell grows a spike outward from the sphere, its length and colour following the page’s scale. Dashed circles mark tilt 30° / 60° / 90° from the reference. Prior art: the Nov 19 direction sphere, hedgehog plots of vector fields.`,
      tool: true, build: buildHedgehog,
    },
  ];

  function buildHeightQQd(stage, payload, ctx, parts) {
    const extraHome = [];
    const joint = ctx.jointName;
    const plane = payload.planes[joint].q_qd;
    const u = units(payload, joint);
    const [nx, ny] = plane.shape;
    const [qlo, qhi] = plane.x_edges;
    const [vlo, vhi] = plane.y_edges;
    const X = 1.6; const Y = 1.1; const Z = 0.62;
    const field = columns(stage, { nx, ny, x0: 0, y0: 0, dx: X / nx, dy: Y / ny, keep: (i) => plane.samples[i] > 0 });
    const frame = addFrame(stage, {
      theta: -Math.PI / 2 + 0.62,
      min: [0, 0, 0], max: [X, Y, Z],
      x: { title: `q — position (${u.q})`, ticks: ticksOn(endTicks(qlo * u.scale, qhi * u.scale), qlo * u.scale, qhi * u.scale) },
      y: { title: `qd — speed (${u.qd})`, ticks: ticksOn(endTicks(vlo * u.scale, vhi * u.scale), vlo * u.scale, vhi * u.scale) },
      z: null,
    });
    stage.add(segments([0, 0, 0, X, 0, 0, X, 0, 0, X, Y, 0, X, Y, 0, 0, Y, 0, 0, Y, 0, 0, 0, 0], CC.LIMIT, { order: 2 }));
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 2 + 0.62, phi: 0.98 });

    const bar = colorbar(parts.legend, `samples per q × qd cell (${nx} × ${ny})`);
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.8)), text: 'bar height and colour = samples in the cell (same scale)' },
      { kind: 'box', colour: '#ffffff', text: `no bar = never visited · ${fmt(plane.visited_pct)} % of cells visited, ${fmt(plane.sufficient_pct)} % with ≥ ${ctx.enough}` },
      { kind: 'line', colour: CC.LIMIT, text: `red outline = ${limitWords(limitOf(payload, joint, 'q'))}s on q and qd (the floor is exactly the limit box)` },
    ]);
    const cellWidth = (qhi - qlo) / nx;
    const cellHeight = (vhi - vlo) / ny;
    stage.setPick((raycaster) => {
      const i = field.cellOf(raycaster.intersectObject(field.mesh, false)[0]);
      if (i === null) return null;
      const ix = Math.floor(i / ny); const iy = i % ny;
      const q0 = (qlo + ix * cellWidth) * u.scale; const v0 = (vlo + iy * cellHeight) * u.scale;
      return `q ${fmt(q0)}…${fmt(q0 + cellWidth * u.scale)} ${u.q}, qd ${fmt(v0)}…${fmt(v0 + cellHeight * u.scale)} ${u.qd} · ${plural(plane.samples[i], 'sample')} · ${plane.paths[i] === 1 ? '1 trajectory' : plane.paths[i] + ' trajectories'}`;
    });
    return {
      recolour(next) {
        const scale = scaled(plane.samples, next);
        field.setHeights((i) => Math.max(0, scale.t[i]) * Z);
        field.setColours((i) => next.ramp(Math.max(0, scale.t[i])));
        frame.setZ({ title: 'samples', ticks: scale.ticks.map((t) => ({ f: t.t, label: t.label })) });
        bar.paint(scale, next.ramp, { note: `${scaleTitle(next)} · ${scale.note}` });
      },
    };
  }

  function buildTerrainQdd(stage, payload, ctx, parts) {
    const extraHome = [];
    const joint = ctx.jointName;
    const plane = payload.planes[joint].q_qd;
    const u = units(payload, joint);
    const limit = limitOf(payload, joint, 'qdd');
    const top = Math.max(Math.abs(limit.low), Math.abs(limit.high)) || 1;
    const [nx, ny] = plane.shape;
    const [qlo, qhi] = plane.x_edges;
    const [vlo, vhi] = plane.y_edges;
    const X = 1.6; const Y = 1.1; const Z = 0.5;
    const values = plane.max_other || [];
    const ratio = (i) => Math.abs(values[i]) / top;
    const field = columns(stage, { nx, ny, x0: 0, y0: 0, dx: X / nx, dy: Y / ny, keep: (i) => values[i] !== null && values[i] !== undefined && plane.samples[i] > 0 });
    field.setHeights((i) => Math.min(ratio(i), 1.3) * Z);
    const frame = addFrame(stage, {
      theta: -Math.PI / 2 + 0.62,
      min: [0, 0, 0], max: [X, Y, Z],
      x: { title: `q — position (${u.q})`, ticks: ticksOn(endTicks(qlo * u.scale, qhi * u.scale), qlo * u.scale, qhi * u.scale) },
      y: { title: `qd — speed (${u.qd})`, ticks: ticksOn(endTicks(vlo * u.scale, vhi * u.scale), vlo * u.scale, vhi * u.scale) },
      z: { title: `max |qdd| (${u.qdd})`, ticks: [0, 0.5, 1].map((f) => ({ f, label: fmt(f * top * u.scale) + (f === 1 ? ' limit' : '') })) },
    });
    const sheet = new THREE.Mesh(new THREE.PlaneGeometry(X, Y),
      new THREE.MeshBasicMaterial({ color: colour(CC.LIMIT), transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide }));
    sheet.position.set(X / 2, Y / 2, Z);
    stage.add(sheet);
    stage.add(segments([0, 0, Z, X, 0, Z, X, 0, Z, X, Y, Z, X, Y, Z, 0, Y, Z, 0, Y, Z, 0, 0, Z], CC.LIMIT, { opacity: 0.7 }));
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 2 + 0.62, phi: 1.02 });

    const over = field.cells.filter((i) => ratio(i) > 1).length;
    const bar = colorbar(parts.legend, `max |qdd| reached in the cell, % of the limit (${fmt(top * u.scale)} ${u.qdd})`);
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.6)), text: 'bar height and colour = the largest |qdd| any sample in that q × qd cell reached' },
      { kind: 'box', colour: CC.LIMIT, text: `red bar = past the limit (${over} cells)` },
      { kind: 'box', colour: '#f6dcd6', text: `red sheet = the qdd limit (${limitWords(limit)})` },
      { kind: 'box', colour: '#ffffff', text: 'no bar = cell never visited · colour is linear in % of the limit (the scale menu does not apply)' },
    ]);
    const cellWidth = (qhi - qlo) / nx;
    const cellHeight = (vhi - vlo) / ny;
    stage.setPick((raycaster) => {
      const i = field.cellOf(raycaster.intersectObject(field.mesh, false)[0]);
      if (i === null) return null;
      const ix = Math.floor(i / ny); const iy = i % ny;
      const q0 = (qlo + ix * cellWidth) * u.scale; const v0 = (vlo + iy * cellHeight) * u.scale;
      return `q ${fmt(q0)}…${fmt(q0 + cellWidth * u.scale)} ${u.q}, qd ${fmt(v0)}…${fmt(v0 + cellHeight * u.scale)} ${u.qd} · max |qdd| ${fmt(Math.abs(values[i]) * u.scale)} ${u.qdd} (${fmt(ratio(i) * 100)} % of the limit)`;
    });
    return {
      recolour(next) {
        field.setColours((i) => (ratio(i) > 1 ? hexRGB(CC.LIMIT) : next.ramp(ratio(i))));
        bar.paint({ mode: 'linear', ticks: [0, 0.25, 0.5, 0.75, 1].map((t) => ({ t, label: fmt(t * 100) + ' %' })) }, next.ramp,
          { note: 'linear: 100 % = the limit' });
        bar.setEmpty('white = not visited');
      },
    };
  }

  function buildSlabStack(stage, payload, ctx, parts) {
    const extraHome = [];
    const joint = ctx.jointName;
    const slab = payload.slabs[joint];
    const u = units(payload, joint);
    const [K, nx, ny] = slab.shape;
    const plane = payload.planes[joint].q_qd;
    const [qlo, qhi] = plane.x_edges;
    const [vlo, vhi] = plane.y_edges;
    const [blo, bhi] = slab.by_edges;
    const X = 1.6; const Y = 1.1; const gap = 0.26;
    const Z = gap * (K - 1);
    const textures = [];
    const sheets = [];
    for (let k = 0; k < K; k++) {
      const data = new Uint8Array(nx * ny * 4);
      const texture = new THREE.DataTexture(data, nx, ny, THREE.RGBAFormat);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.magFilter = THREE.NearestFilter;
      texture.minFilter = THREE.NearestFilter;
      texture.generateMipmaps = false;
      textures.push(texture);
      const sheet = new THREE.Mesh(new THREE.PlaneGeometry(X, Y), new THREE.MeshBasicMaterial({
        map: texture, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
      sheet.position.set(X / 2, Y / 2, k * gap);
      sheet.renderOrder = k;
      stage.add(sheet);
      sheets.push(sheet);
      stage.add(segments([0, 0, k * gap, X, 0, k * gap, X, 0, k * gap, X, Y, k * gap, X, Y, k * gap, 0, Y, k * gap, 0, Y, k * gap, 0, 0, k * gap], FRAME));
      const b0 = blo + (bhi - blo) * k / K;
      const b1 = blo + (bhi - blo) * (k + 1) / K;
      const end = k === 0 ? ' (braking hardest)' : k === K - 1 ? ' (accelerating hardest)' : '';
      stage.label(`qdd ${fmt(b0 * u.scale)} … ${fmt(b1 * u.scale)} ${u.qdd}${end} · ${fmt(slab.visited_pct[k])} % visited`,
        [-0.05, Y * 0.22, k * gap], 'tick', 'right');
      extraHome.push([-0.9, Y * 0.22, k * gap]);
    }
    // the stack's corner posts, so five sheets read as one box
    const posts = [];
    [[0, 0], [X, 0], [X, Y], [0, Y]].forEach(([x, y]) => posts.push(x, y, 0, x, y, Z));
    stage.add(segments(posts, GRID));
    const frame = addFrame(stage, {
      theta: -Math.PI / 2 + 0.55,
      min: [0, 0, 0], max: [X, Y, Z], grid: false,
      x: { title: `q — position (${u.q})`, ticks: ticksOn(endTicks(qlo * u.scale, qhi * u.scale), qlo * u.scale, qhi * u.scale) },
      y: { title: `qd — speed (${u.qd})`, ticks: ticksOn(endTicks(vlo * u.scale, vhi * u.scale), vlo * u.scale, vhi * u.scale) },
      z: null, // each slab's own label is the z axis
    });
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 2 + 0.55, phi: 1.08 });

    const bar = colorbar(parts.legend, `samples per q × qd cell, within each qdd slab (${K} slabs, one shared scale)`);
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.7)), text: 'coloured cell = samples in that q × qd cell with qdd inside the slab’s band' },
      { kind: 'box', colour: '#ffffff', text: 'see-through = no sample in that cell and band' },
      { kind: 'thin', colour: FRAME, text: 'grey frame = one slab; its qdd band and visited % are written at its left edge' },
      { kind: 'box', colour: '#f2f1ec', text: 'bottom = hardest braking (most negative qdd), top = hardest accelerating' },
    ]);
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObjects(sheets, false).find((h) => {
        const k = sheets.indexOf(h.object);
        const i = Math.min(nx - 1, Math.floor(h.uv.x * nx));
        const j = Math.min(ny - 1, Math.floor(h.uv.y * ny));
        return slab.samples[k * nx * ny + i * ny + j] > 0;
      });
      if (!hit) return null;
      const k = sheets.indexOf(hit.object);
      const i = Math.min(nx - 1, Math.floor(hit.uv.x * nx));
      const j = Math.min(ny - 1, Math.floor(hit.uv.y * ny));
      const q0 = (qlo + (qhi - qlo) * i / nx) * u.scale;
      const v0 = (vlo + (vhi - vlo) * j / ny) * u.scale;
      return `slab ${k + 1} · q ${fmt(q0)} ${u.q}, qd ${fmt(v0)} ${u.qd} · ${slab.samples[k * nx * ny + i * ny + j]} samples`;
    });
    return {
      recolour(next) {
        const scale = scaled(slab.samples, next);
        textures.forEach((texture, k) => {
          const data = texture.image.data;
          for (let i = 0; i < nx; i++) {
            for (let j = 0; j < ny; j++) {
              const t = scale.t[k * nx * ny + i * ny + j];
              const at = (j * nx + i) * 4;
              if (t < 0) { data[at] = 255; data[at + 1] = 255; data[at + 2] = 255; data[at + 3] = 18; continue; }
              const rgb = next.ramp(t);
              data[at] = rgb[0]; data[at + 1] = rgb[1]; data[at + 2] = rgb[2]; data[at + 3] = 238;
            }
          }
          texture.needsUpdate = true;
        });
        bar.paint(scale, next.ramp, { note: `${scaleTitle(next)} · ${scale.note}` });
        bar.setEmpty('see-through = none');
      },
    };
  }

  function buildPhaseSpace(stage, payload, ctx, parts) {
    const extraHome = [];
    const joint = ctx.jointName;
    const u = units(payload, joint);
    const paths = (payload.paths || {})[joint] || [];
    const names = (payload.trajectories || []).map((t) => t.name);
    const L = { q: limitOf(payload, joint, 'q'), qd: limitOf(payload, joint, 'qd'), qdd: limitOf(payload, joint, 'qdd') };
    const X = 1.4; const Y = 1.0; const Z = 0.8;
    const map = (v, limit, size) => (v - limit.low) / (limit.high - limit.low) * size;
    const toWorld = (path) => path[0].map((q, i) => [map(q, L.q, X), map(path[1][i], L.qd, Y), map(path[2][i], L.qdd, Z)]);
    const worldPaths = paths.map(toWorld);
    const pts = [];
    const starts = [];
    let outside = 0;
    worldPaths.forEach((path) => {
      starts.push(pts.length / 6);
      polylineToSegments(path, pts);
      if (path.some((p) => p[0] < -1e-6 || p[0] > X + 1e-6 || p[1] < -1e-6 || p[1] > Y + 1e-6 || p[2] < -1e-6 || p[2] > Z + 1e-6)) outside++;
    });
    const opacity = clamp(6 / Math.sqrt(Math.max(1, paths.length)), 0.12, 0.9);
    const lines = stage.add(segments(pts, '#000000', { opacity }));
    const box = [];
    const corners = [[0, 0, 0], [X, 0, 0], [X, Y, 0], [0, Y, 0], [0, 0, Z], [X, 0, Z], [X, Y, Z], [0, Y, Z]];
    [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]].forEach(([a, b]) => box.push(...corners[a], ...corners[b]));
    stage.add(segments(box, CC.LIMIT, { opacity: 0.8 }));
    const frame = addFrame(stage, {
      theta: -Math.PI / 4 - 0.15,
      min: [0, 0, 0], max: [X, Y, Z],
      x: { title: `q — position (${u.q})`, ticks: ticksOn(endTicks(L.q.low * u.scale, L.q.high * u.scale), L.q.low * u.scale, L.q.high * u.scale) },
      y: { title: `qd — speed (${u.qd})`, ticks: ticksOn(endTicks(L.qd.low * u.scale, L.qd.high * u.scale), L.qd.low * u.scale, L.qd.high * u.scale) },
      z: { title: `qdd — acceleration (${u.qdd})`, ticks: ticksOn(endTicks(L.qdd.low * u.scale, L.qdd.high * u.scale), L.qdd.low * u.scale, L.qdd.high * u.scale) },
    });
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 4 - 0.15, phi: 1.12 });

    const marks = markList(parts.legend, []);
    function writeMarks(next) {
      marks.textContent = '';
      const inkHex = CC.css(darkEnd(next.ramp));
      [{ kind: 'line', colour: inkHex, text: `one line = one trajectory (${paths.length}), ≤ ${Math.max(0, ...paths.map((p) => p[0].length))} evenly picked samples each; darker = more overlap` },
        { kind: 'line', colour: CC.LIMIT, text: `red box = the joint’s q, qd and qdd limits · ${outside} trajectories leave it` },
        { kind: 'line', colour: HIGHLIGHT, text: 'orange tube = the trajectory picked in the table (ball = start, cube = end) · hover a line for its name' },
      ].forEach((m) => {
        const item = el('li', null, marks);
        el('span', 'sw ' + m.kind, item).style.borderColor = m.colour;
        el('span', null, item, m.text);
      });
    }
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(lines, false)[0];
      if (!hit) return null;
      const segment = Math.floor(hit.index / 2);
      let lo = 0; let hi = starts.length - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (starts[mid] <= segment) lo = mid; else hi = mid - 1; }
      return `${names[lo] || 'trajectory ' + (lo + 1)} (#${lo + 1})`;
    });
    let highlightObject = null;
    let highlightLabel = null;
    return {
      recolour(next) { lines.material.color.copy(colour(darkEnd(next.ramp))); writeMarks(next); },
      highlight(index) {
        if (highlightObject) { stage.remove(highlightObject); highlightObject = null; }
        if (highlightLabel) { stage.removeLabels([highlightLabel]); highlightLabel = null; }
        const path = index === null || index === undefined ? null : worldPaths[index];
        lines.material.opacity = path ? opacity * 0.55 : opacity;
        if (path) {
          highlightObject = stage.add(tube(path, 0.006, HIGHLIGHT));
          highlightLabel = stage.label(names[index] || `trajectory ${index + 1}`, path[0], 'hi', 'above');
        }
      },
    };
  }

  function buildHistOverTrajectories(stage, payload, ctx, parts) {
    const extraHome = [];
    const joint = ctx.jointName;
    const u = units(payload, joint);
    const paths = (payload.paths || {})[joint] || [];
    const names = (payload.trajectories || []).map((t) => t.name);
    const limit = limitOf(payload, joint, 'qd');
    const hist = ((payload.hist || {})[joint] || {}).qd;
    const lo = hist ? hist.edges[0] : limit.low - 0.08 * (limit.high - limit.low);
    const hi = hist ? hist.edges[1] : limit.high + 0.08 * (limit.high - limit.low);
    const bins = 60;
    const MAX_ROWS = 150;
    // WHY a cap: a 1 500-trajectory dataset would be a solid wall; evenly picked rows keep the order readable
    const picked = [];
    const step = Math.max(1, paths.length / MAX_ROWS);
    for (let r = 0; r < paths.length && picked.length < MAX_ROWS; r = Math.round((picked.length) * step)) picked.push(r);
    const histograms = picked.map((r) => percentHistogram(paths[r][1], lo, hi, bins));
    const X = 1.6; const Y = picked.length > 1 ? clamp(picked.length * 0.035, 0.6, 1.5) : 0.1; const Z = 0.5;
    const xs = [];
    for (let b = 0; b < bins; b++) xs.push((b + 0.5) / bins * X);
    // the first trajectory at the back, the last in front: the newest is closest, as in TensorBoard's offset view
    const rows = picked.map((r, k) => ({ y: picked.length > 1 ? (picked.length - 1 - k) / (picked.length - 1) * Y : 0,
      xs: [0].concat(xs, [X]) }));
    const ridge = ridges(stage, rows);
    const limitX = (v) => (v - lo) / (hi - lo) * X;
    stage.add(segments([limitX(limit.low), 0, 0, limitX(limit.low), Y, 0, limitX(limit.high), 0, 0, limitX(limit.high), Y, 0], CC.LIMIT));
    const tickValues = endTicks(limit.low * u.scale, limit.high * u.scale).filter((v) => true);
    const frame = addFrame(stage, {
      theta: -Math.PI / 2 + 0.2,
      min: [0, 0, 0], max: [X, Y, Z], grid: false,
      x: { title: `qd — speed (${u.qd})`, ticks: tickValues.map((v) => ({ f: (v / u.scale - lo) / (hi - lo), label: fmt(v) })) },
      y: { title: 'trajectory (order added) →', ticks: picked.length > 1 ? [{ f: 1, label: `#1` }, { f: 0, label: `#${picked[picked.length - 1] + 1}` }] : [] },
      z: null,
    });
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 2 + 0.2, phi: 0.98 });

    const bar = colorbar(parts.legend, '% of the trajectory’s samples in the speed bin');
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.7)), text: `one ridge = one trajectory’s qd histogram (${bins} bins), height and colour = % of its samples (same scale); back = first added, front = last${picked.length < paths.length ? ` · ${picked.length} of ${paths.length} trajectories, evenly picked` : ''}` },
      { kind: 'thin', colour: '#b5b4ad', text: 'grey baseline = one trajectory’s row (flat where it never reached that speed)' },
      { kind: 'line', colour: CC.LIMIT, text: `red lines = the ± speed limit (${limitWords(limit)})` },
      { kind: 'line', colour: HIGHLIGHT, text: 'orange outline = the trajectory picked in the table' },
      { kind: 'thin', colour: '#888', text: `counted here from the evenly picked path samples (≤ ${Math.max(0, ...picked.map((r) => paths[r][1].length))} per trajectory, payload.paths): the payload carries no per-trajectory histograms` },
    ]);
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(ridge.mesh, false)[0];
      if (!hit) return null;
      const row = ridge.rowOfFace(hit.faceIndex);
      const r = picked[row];
      const b = clamp(Math.floor(hit.point.x / X * bins), 0, bins - 1);
      const v0 = (lo + (hi - lo) * b / bins) * u.scale;
      return `${names[r] || 'trajectory ' + (r + 1)} (#${r + 1}) · qd ${fmt(v0)}…${fmt(v0 + (hi - lo) / bins * u.scale)} ${u.qd} · ${fmt(histograms[row][b])} % of its samples`;
    });
    let highlightObject = null;
    let highlightLabel = null;
    return {
      recolour(next) {
        const all = [];
        histograms.forEach((h) => h.forEach((v) => all.push(v)));
        const scale = scaled(all, next);
        const tOf = (r, j) => (j === 0 || j === bins + 1 ? -1 : scale.t[r * bins + j - 1]);
        ridge.setHeights((r, j) => Math.max(0, tOf(r, j)) * Z);
        ridge.paint((r, j) => next.ramp(Math.max(0, tOf(r, j))));
        frame.setZ({ title: '% of its samples', ticks: scale.ticks.map((t) => ({ f: t.t, label: t.label })) });
        bar.paint(scale, next.ramp, { note: `${scaleTitle(next)} · ${scale.note}` });
        bar.setEmpty('');
      },
      highlight(index) {
        if (highlightObject) { stage.remove(highlightObject); highlightObject = null; }
        if (highlightLabel) { stage.removeLabels([highlightLabel]); highlightLabel = null; }
        const row = index === null || index === undefined ? -1 : picked.indexOf(index);
        if (row < 0) return;
        const r = rows[row];
        const path = r.xs.map((x, j) => [x, r.y, r.heights[j] + 0.002]);
        highlightObject = stage.add(tube(path, 0.0045, HIGHLIGHT));
        highlightLabel = stage.label(names[index] || `trajectory ${index + 1}`, [X + 0.04, r.y, 0], 'hi', 'left');
      },
    };
  }

  function buildJointSkyline(stage, payload, ctx, parts) {
    const extraHome = [];
    const joints = payload.joints || [];
    const rowsData = joints.map((joint) => {
      const hist = payload.hist[joint.name].q;
      const limit = limitOf(payload, joint.name, 'q');
      const [lo, hi, bins] = hist.edges;
      const total = hist.counts.reduce((a, b) => a + b, 0) || 1;
      const span = (limit.high - limit.low) || 1;
      const pct = (v) => (v - limit.low) / span * 100;
      const centres = hist.counts.map((_, b) => pct(lo + (b + 0.5) * (hi - lo) / bins));
      return { joint, hist, limit, share: hist.counts.map((c) => c / total * 100), centres, pct, lo, hi, bins };
    });
    const X = 1.6; const gap = 0.24; const Z = 0.42;
    const Y = gap * Math.max(1, joints.length - 1);
    const xOf = (pct) => (pct + 10) / 120 * X;
    const rows = rowsData.map((r, k) => {
      const y = (joints.length - 1 - k) * gap; // first joint at the back = top of the list on screen
      return { y, xs: [xOf(r.centres[0])].concat(r.centres.map(xOf), [xOf(r.centres[r.centres.length - 1])]) };
    });
    const ridge = ridges(stage, rows);
    const limitLines = [xOf(0), -0.04, 0, xOf(0), Y + 0.04, 0, xOf(100), -0.04, 0, xOf(100), Y + 0.04, 0];
    stage.add(segments(limitLines, CC.LIMIT));
    const ticks = [];
    rowsData.forEach((r, k) => {
      const y = rows[k].y;
      [r.hist.p001, r.hist.p999].forEach((v) => {
        if (v === null || v === undefined) return;
        const x = xOf(r.pct(v));
        ticks.push(x, y - 0.05, 0, x, y + 0.05, 0);
      });
      stage.label(r.joint.name, [-0.05, y, 0], 'name' + (r.joint.name === ctx.jointName ? ' current' : ''), 'right');
      extraHome.push([-0.42, y, 0]);
    });
    stage.add(segments(ticks, '#111111'));
    const frame = addFrame(stage, {
      theta: -Math.PI / 2 + 0.16,
      min: [0, -0.1, 0], max: [X, Y + 0.1, Z], grid: false,
      x: { title: 'position as % of each joint’s range (0 % = low limit, 100 % = high limit)', ticks: [0, 25, 50, 75, 100].map((p) => ({ f: xOf(p) / X, label: p + ' %' })) },
      y: { title: '', ticks: [] },
      z: null,
    });
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 2 + 0.16, phi: 0.98 });

    const bar = colorbar(parts.legend, '% of the joint’s samples in the bin');
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.7)), text: `one ridge per joint (${joints.length}), height and colour = % of its samples at that position (same scale)` },
      { kind: 'line', colour: CC.LIMIT, text: 'red lines = each joint’s position limits (0 % and 100 % of its range)' },
      { kind: 'line', colour: '#111111', text: 'black ticks = each joint’s p0.1 and p99.9: the span it really uses' },
      { kind: 'thin', colour: FRAME, text: 'bold name = the joint selected in the page’s joint menu' },
    ]);
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(ridge.mesh, false)[0];
      if (!hit) return null;
      const r = rowsData[ridge.rowOfFace(hit.faceIndex)];
      const pct = hit.point.x / X * 120 - 10;
      const b = clamp(Math.floor((r.limit.low + pct / 100 * (r.limit.high - r.limit.low) - r.lo) / (r.hi - r.lo) * r.bins), 0, r.bins - 1);
      const u = units(payload, r.joint.name);
      return `${r.joint.name} · ${fmt(pct)} % of its range (q ${fmt((r.lo + (b + 0.5) * (r.hi - r.lo) / r.bins) * u.scale)} ${u.q}) · ${fmt(r.share[b])} % of its samples · span used ${fmt(r.hist.span_pct)} %`;
    });
    return {
      recolour(next) {
        const all = [];
        rowsData.forEach((r) => r.share.forEach((v) => all.push(v)));
        const scale = scaled(all, next);
        const offsets = [];
        let at = 0;
        rowsData.forEach((r) => { offsets.push(at); at += r.share.length; });
        const tOf = (row, j) => (j === 0 || j > rowsData[row].share.length ? -1 : scale.t[offsets[row] + j - 1]);
        ridge.setHeights((row, j) => Math.max(0, tOf(row, j)) * Z);
        ridge.paint((row, j) => next.ramp(Math.max(0, tOf(row, j))));
        frame.setZ({ title: '% of its samples', ticks: scale.ticks.map((t) => ({ f: t.t, label: t.label })) });
        bar.paint(scale, next.ramp, { note: `${scaleTitle(next)} · ${scale.note}` });
        bar.setEmpty('');
      },
    };
  }

  function buildWorkspaceTerrain(stage, payload, ctx, parts) {
    const extraHome = [];
    const tool = payload.tool;
    const projection = tool.projections.xy;
    const [nu, nv] = projection.shape;
    const [u0, v0] = projection.origin;
    const pixel = tool.pixel_m;
    const paths = projection.paths;
    const speeds = projection.max_speed;
    const maxPaths = Math.max(1, ...paths);
    const X = nu * pixel; const Y = nv * pixel;
    const Z = 0.32 * Math.max(X, Y);
    const field = columns(stage, { nx: nu, ny: nv, x0: u0, y0: v0, dx: pixel, dy: pixel, fill: 0.96, keep: (i) => paths[i] > 0 });
    field.setHeights((i) => paths[i] / maxPaths * Z);
    if (projection.reachable) {
      const floor = [];
      for (let i = 0; i < nu * nv; i++) if (projection.reachable[i] && !(paths[i] > 0)) floor.push(i);
      const mesh = instanced(new THREE.PlaneGeometry(1, 1), floor.length, {});
      const matrix = new THREE.Matrix4();
      floor.forEach((i, k) => {
        matrix.makeScale(pixel * 0.96, pixel * 0.96, 1).setPosition(u0 + (Math.floor(i / nv) + 0.5) * pixel, v0 + (i % nv + 0.5) * pixel, 0.0005);
        mesh.setMatrixAt(k, matrix);
      });
      paintInstances(mesh, floor.length, () => hexRGB('#e4e3dd'));
      mesh.instanceMatrix.needsUpdate = true;
      stage.add(mesh);
    }
    const lo = [u0, v0, 0]; const hi = [u0 + X, v0 + Y, Z];
    const axis = (i) => niceTicks(lo[i] * 1000, hi[i] * 1000, 4).map((v) => ({ f: (v / 1000 - lo[i]) / (hi[i] - lo[i]), label: fmt(v) }));
    const frame = addFrame(stage, {
      theta: -Math.PI / 4,
      min: lo, max: hi,
      x: { title: 'x (mm)', ticks: axis(0) }, y: { title: 'y (mm)', ticks: axis(1) },
      z: { title: 'trajectories through the pixel', ticks: niceTicks(0, maxPaths, 3).filter((v) => Number.isInteger(v)).map((v) => ({ f: v / maxPaths, label: fmt(v) })) },
    });
    if (u0 <= 0 && u0 + X >= 0 && v0 <= 0 && v0 + Y >= 0) addBaseMarker(stage, Math.max(X, Y) * 0.06, tool);
    stage.setHome({ box: frame.box, extra: frame.anchors.concat(extraHome), theta: -Math.PI / 4, phi: 0.95 });

    const bar = colorbar(parts.legend, 'fastest tool speed in the pixel (mm/s)');
    const marks = [
      { kind: 'box', colour: CC.css(ctx.ramp(0.7)), text: `column height = distinct trajectories through the ${Math.round(pixel * 1000)} mm pixel (top-down, xy); colour = max tool speed there` },
      { kind: 'box', colour: '#ffffff', text: 'no column = the tool never passed over that pixel' },
    ];
    if (projection.reachable) marks.push({ kind: 'box', colour: '#e4e3dd', text: 'grey floor square = reachable, never visited' });
    marks.push({ kind: 'line', colour: AXIS_COLOURS[0], text: `${frameAxesText(tool)}: red x, green y, blue z` });
    markList(parts.legend, marks);
    stage.setPick((raycaster) => {
      const i = field.cellOf(raycaster.intersectObject(field.mesh, false)[0]);
      if (i === null) return null;
      const x = (u0 + Math.floor(i / nv) * pixel) * 1000;
      const y = (v0 + (i % nv) * pixel) * 1000;
      return `x ${fmt(x)}…${fmt(x + pixel * 1000)} mm, y ${fmt(y)}…${fmt(y + pixel * 1000)} mm · ${paths[i] === 1 ? '1 trajectory' : paths[i] + ' trajectories'} · ${plural(projection.samples[i], 'sample')} · max ${fmt(speeds[i] * 1000)} mm/s`;
    });
    return {
      recolour(next) {
        // speed is not a count: visited / enough make no sense for it, so they fall back to linear
        const mode = ['linear', 'log', 'equalized'].indexOf(next.scale) >= 0 ? next.scale : 'linear';
        const scale = CC.scale(speeds.map((s, i) => (paths[i] > 0 && s !== null ? s * 1000 : null)), mode);
        field.setColours((i) => next.ramp(Math.max(0, scale.t[i])));
        bar.paint(scale, next.ramp, { note: `${CC.SCALE_TITLES[mode]} · ${scale.note}${mode !== next.scale ? ' (speed is not a count: shown linear)' : ''}` });
        bar.setEmpty('');
      },
    };
  }

  function buildHedgehog(stage, payload, ctx, parts) {
    const orientation = payload.tool.orientation;
    const sphere = orientation.sphere;
    const reference = unit(orientation.reference || [0, 0, -1]);
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.995, 48, 32), new THREE.MeshBasicMaterial({ color: colour('#f7f7f5') }));
    stage.add(ball);
    stage.add(sphereGridLines(sphere.rings, sphere.sectors, 1.0));
    tiltCircles(stage, reference, 1.004, [30, 60, 90]);
    sphereAxes(stage, 1.0, 2.05, reference);
    const visited = [];
    sphere.counts.forEach((c, cell) => { if (c > 0) visited.push(cell); });
    const geometry = new THREE.CylinderGeometry(1, 1, 1, 8).translate(0, 0.5, 0);
    const spikes = instanced(geometry, visited.length, {});
    stage.add(spikes);
    const matrix = new THREE.Matrix4();
    const quaternion = new THREE.Quaternion();
    const yAxis = new THREE.Vector3(0, 1, 0);
    const LENGTH = 0.95;
    sphereHome(stage, sphere, reference);
    // the spikes reach out to 2: widen the home so they fit
    stage.setHome({ center: [0, 0, 0], radius: 2.0, theta: stageHomeTheta(sphere, reference), phi: stageHomePhi(sphere, reference), margin: 1.02 });

    const bar = colorbar(parts.legend, `samples per direction cell (${sphere.rings * sphere.sectors} equal-area cells)`);
    markList(parts.legend, [
      { kind: 'box', colour: CC.css(ctx.ramp(0.7)), text: 'spike = a direction the tool z axis pointed; length and colour = samples in that cell (same scale)' },
      { kind: 'box', colour: '#f7f7f5', text: 'bare sphere = directions never used' },
      { kind: 'dash', colour: INK, text: 'black-and-white circles = tilt 30° / 60° / 90° from the reference' },
      { kind: 'line', colour: AXIS_COLOURS[2], text: `stubs = "${frameName(payload.tool)}" axes: red ±x, green ±y, blue up / down` },
    ]);
    stage.setPick((raycaster) => {
      const hit = raycaster.intersectObject(spikes, false)[0];
      if (!hit || hit.instanceId === undefined) return null;
      const cell = visited[hit.instanceId];
      const c = cellCentre(sphere.rings, sphere.sectors, cell);
      const tilt = degrees(Math.acos(clamp(c[0] * reference[0] + c[1] * reference[1] + c[2] * reference[2], -1, 1)));
      const azimuth = degrees(Math.atan2(c[1], c[0]));
      return `azimuth ${fmt(azimuth)}°, elevation ${fmt(degrees(Math.asin(c[2])))}° · ≈ ${fmt(tilt)}° from the reference · ${sphere.counts[cell]} samples`;
    });
    return {
      recolour(next) {
        const scale = scaled(sphere.counts, next);
        visited.forEach((cell, k) => {
          const c = cellCentre(sphere.rings, sphere.sectors, cell);
          const t = Math.max(0, scale.t[cell]);
          const radius = 0.017;
          quaternion.setFromUnitVectors(yAxis, new THREE.Vector3(c[0], c[1], c[2]));
          matrix.compose(new THREE.Vector3(c[0], c[1], c[2]), quaternion, new THREE.Vector3(radius, 0.04 + LENGTH * t, radius));
          spikes.setMatrixAt(k, matrix);
        });
        spikes.instanceMatrix.needsUpdate = true;
        spikes.computeBoundingSphere();
        paintInstances(spikes, visited.length, (k) => next.ramp(Math.max(0, scale.t[visited[k]])));
        bar.paint(scale, next.ramp, { note: `${scaleTitle(next)} · ${scale.note}` });
        bar.setEmpty('no spike = none');
      },
    };
  }

  function meanDirection(sphere, reference) {
    let m = [0, 0, 0];
    sphere.counts.forEach((count, cell) => {
      if (!count) return;
      const c = cellCentre(sphere.rings, sphere.sectors, cell);
      m = [m[0] + c[0] * count, m[1] + c[1] * count, m[2] + c[2] * count];
    });
    if (Math.hypot(m[0], m[1], m[2]) < 1e-9) m = reference.slice();
    return unit(m);
  }
  function stageHomePhi(sphere, reference) {
    const m = meanDirection(sphere, reference);
    return Math.PI / 2 + (Math.acos(clamp(m[2], -1, 1)) - Math.PI / 2) * 0.45;
  }
  function stageHomeTheta(sphere, reference) {
    const m = meanDirection(sphere, reference);
    return Math.hypot(m[0], m[1]) > 0.2 ? Math.atan2(m[1], m[0]) + 0.45 : -Math.PI / 4;
  }

  /* ── public: the three views ───────────────────────────────────────────── */

  const VIEWS = { 'voxels-3d': mountVoxels, 'spaghetti-3d': mountSpaghetti, 'sphere-3d': mountSphere };

  function mount(body, viewId, payload, ctx) {
    injectStyle();
    const build = VIEWS[viewId];
    const needsTool = !payload.tool || (viewId === 'sphere-3d' && !payload.tool.orientation);
    if (!build || needsTool) {
      const note = el('div', 'cov3d-empty', body, build ? 'No tool (TCP) poses in this payload: nothing to draw in 3-D.' : `Unknown 3-D view “${viewId}”.`);
      const legend = el('div', 'cov3d-legend', body, 'no data');
      legend.setAttribute('data-cov-legend', '');
      return { update() {}, highlight() {}, dispose() { note.remove(); legend.remove(); } };
    }
    return build(body, payload, normalise(ctx, payload));
  }

  /* ── public: the proposals switcher (space3d tab) ──────────────────────── */

  function mountProposals(section, payload, ctx) {
    injectStyle();
    ctx = normalise(ctx, payload);
    const available = PROPOSALS.filter((p) => !p.tool || (payload.tool && (p.id !== 'direction-hedgehog' || payload.tool.orientation)));
    const figure = el('figure', 'cov3d-proposal', section);
    figure.style.margin = '0 0 70px';
    const title = el('h3', null, figure);
    const what = el('p', 'what', figure);
    const stage = createStage(figure, { heightFor: (w) => clamp(Math.round(w * 0.5), 380, 640) });
    const legend = el('div', 'cov3d-legend', figure);
    legend.setAttribute('data-cov-legend', '');
    const details = el('details', null, figure);
    el('summary', null, details, 'How to read this');
    const readText = el('p', null, details);

    // WHY bottom-right and remembered (Zach's prototype-switch rule): variants behind one fixed drop-down that keeps
    // the pick across reloads, never a URL flag. Inside the section, so it only shows while the tab does.
    const switcher = el('div', 'cov3d-switch', section);
    el('span', null, switcher, '3-D proposal');
    const select = el('select', null, switcher);
    select.setAttribute('data-cov-proposal', '');
    available.forEach((p, k) => {
      const option = el('option', null, select, `${k + 1}. ${p.short}`);
      option.title = p.title;
      option.value = p.id;
    });
    const stored = storageGet(STORAGE_KEY);
    select.value = available.some((p) => p.id === stored) ? stored : available[0].id;

    let current = null;
    let currentJoint = null;
    let highlighted = null;
    function show(id) {
      const proposal = available.find((p) => p.id === id) || available[0];
      stage.clear();
      legend.textContent = '';
      figure.setAttribute('data-cov-figure', 'proposal-' + proposal.id);
      title.textContent = proposal.title;
      what.textContent = proposal.what;
      readText.textContent = typeof proposal.read === 'function' ? proposal.read(payload) : proposal.read;
      currentJoint = ctx.jointName;
      try {
        current = Object.assign({ proposal }, proposal.build(stage, payload, ctx, { legend }));
        current.recolour(ctx);
        if (current.highlight && highlighted !== null) current.highlight(highlighted);
      } catch (error) {
        // a payload without this view's field: say so instead of a blank canvas
        stage.clear();
        legend.textContent = `This proposal cannot draw from this payload (${error.message}).`;
        current = null;
        if (global.console) console.warn('coverage3d', proposal.id, error);
      }
      stage.requestRender();
    }
    select.addEventListener('change', () => { storageSet(STORAGE_KEY, select.value); show(select.value); });
    show(select.value);

    return {
      update(next) {
        ctx = normalise(next, payload);
        if (current && current.proposal.joint && ctx.jointName !== currentJoint) { show(select.value); return; }
        if (current && current.proposal.id === 'joint-skyline' && ctx.jointName !== currentJoint) { show(select.value); return; }
        if (current) { current.recolour(ctx); stage.requestRender(); }
      },
      highlight(index) {
        highlighted = index === undefined ? null : index;
        if (current && current.highlight) { current.highlight(highlighted); stage.requestRender(); }
      },
      dispose() { stage.dispose(); figure.remove(); switcher.remove(); },
      proposals: available.map((p) => p.id),
    };
  }

  global.Coverage3D = { mount, mountProposals, PROPOSALS: PROPOSALS.map((p) => p.id) };
})(typeof window !== 'undefined' ? window : globalThis);
