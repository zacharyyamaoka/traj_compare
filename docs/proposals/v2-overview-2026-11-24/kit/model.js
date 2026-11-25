/* The Overview round's one aggregation (pure, no DOM, no imports): every number any of the five Overviews states comes
   from here, over the rows the stock workbench hands a view (the scope's kept runs). oracle.py recomputes the same numbers
   in Python from the JSON; check.cjs compares them in both states of the shared scenario.

   The rule (V2's and Nov 23's, named on every figure): a target's value for a group (a config, or a model type) = the median
   over its runs; the group's value = the median over its targets; n = targets. A target belongs to exactly one speed,
   dataset, split and deployment, so every column of every figure is a filter on targets.
   Default x: the fastest speed the filter leaves (Nov 23's `model.top`). */

export const PALETTE = ['#2a78d6', '#eb6834', '#2f9e44', '#8e5bd1', '#c22f6e', '#17a2b8', '#a67c00', '#6b7a8f',
  '#d17c7b', '#336a3a', '#7d4b8b', '#974811', '#f356b8', '#ac28ab', '#b81b36', '#9d86da'];  // traj_compare report.py SITUATION_PALETTE

export const FIELDS = {
  tcp: { label: 'tool tracking RMS', short: 'tool RMS', unit: 'mm', log: true },
  energy: { label: 'energy per task', short: 'energy', unit: 'J', log: false },
  jerk: { label: 'tool jerk RMS', short: 'jerk', unit: 'm/s³', log: true },
  stop: { label: 'stop error (max)', short: 'stop error', unit: 'mm', log: true },
};
export const RULE = 'median over targets of each target’s median over its runs';
export const MODEL_TYPE_NOTE = 'proposed — MODEL_TYPE in build_rows.py';
export const DEPLOYMENT_ORDER = ['UR5e + Conveyor PnP cell', 'UR5e', 'BAM FB', '1-DOF pendulum'];
export const MODEL_TYPE_ORDER = ['computed torque / model feed-forward', 'stock / PD gains', 'friction hold',
  'record (no controller)', 'other (one-off rig run)'];

const finite = (v) => typeof v === 'number' && Number.isFinite(v);
// WHY tool RMS must be > 0: V2's League filter (isValid && > 0), and a log axis has no zero
const VALID = { tcp: (v) => finite(v) && v > 0, energy: finite, jerk: finite, stop: finite };

export function median(values) {
  const s = values.slice().sort((a, b) => a - b);
  const n = s.length;
  if (!n) return null;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

/** "Conveyor PnP v1 · UR5e + Conveyor PnP cell" → "Conveyor PnP v1" (the deployment is said by a header beside it) */
export function datasetShort(dataset) {
  const at = String(dataset).lastIndexOf(' · ');
  return at > 0 ? dataset.slice(0, at) : String(dataset);
}

/** The model of one set of kept runs. `order`: the configs in their stable order (build_bases.py: deployment, then runs). */
export function buildModel(rows, order = []) {
  const rank = new Map(order.map((c, i) => [c, i]));
  const targets = new Map();
  const configs = new Map();
  const deployments = new Set();
  const raw = {};
  for (const f of Object.keys(FIELDS)) raw[f] = { config: new Map(), mt: new Map() };
  const push = (map, group, tk, v) => {
    let g = map.get(group);
    if (!g) map.set(group, (g = new Map()));
    let list = g.get(tk);
    if (!list) g.set(tk, (list = []));
    list.push(v);
  };
  for (const r of rows) {
    let t = targets.get(r.target_key);
    if (!t) {
      t = { key: r.target_key, site: r.site, slug: r.target_slug, task: r.task, target: r.target, speed: r.speed,
        dataset: r.dataset, split: r.split, deployment: r.deployment, kind: r.kind, facet: `${r.dataset} · ${r.split}`,
        lines: [], runs: [] };
      targets.set(r.target_key, t);
    }
    t.lines.push(r.line);
    t.runs.push(r);
    deployments.add(r.deployment);
    let c = configs.get(r.config);
    if (!c) configs.set(r.config, (c = { name: r.config, modelType: r.model_type, deployments: new Set(), runs: 0 }));
    c.deployments.add(r.deployment);
    c.runs += 1;
    for (const f of Object.keys(FIELDS)) {
      const v = r[f];
      if (!VALID[f](v)) continue;
      push(raw[f].config, r.config, r.target_key, v);
      push(raw[f].mt, r.model_type, r.target_key, v);
    }
  }
  // per field and grouping: group -> [{t, v (the target's median over its runs), runs: [values]}]
  const tmed = {};
  for (const f of Object.keys(FIELDS)) {
    tmed[f] = {};
    for (const by of ['config', 'mt']) {
      const out = new Map();
      for (const [g, byT] of raw[f][by]) {
        out.set(g, [...byT].map(([tk, vs]) => ({ t: targets.get(tk), v: median(vs), runs: vs })));
      }
      tmed[f][by] = out;
    }
  }
  const speeds = [...new Set([...targets.values()].map((t) => t.speed))].filter(finite).sort((a, b) => a - b);
  const tcpSpeeds = new Set();
  for (const list of tmed.tcp.config.values()) for (const item of list) tcpSpeeds.add(item.t.speed);
  const top = tcpSpeeds.size ? Math.max(...tcpSpeeds) : null;
  const slowest = tcpSpeeds.size ? Math.min(...tcpSpeeds) : null;
  const depOrder = (d) => { const i = DEPLOYMENT_ORDER.indexOf(d); return i < 0 ? 99 : i; };
  const cfgList = [...configs.values()].sort((a, b) =>
    (rank.has(a.name) ? rank.get(a.name) : 1e6) - (rank.has(b.name) ? rank.get(b.name) : 1e6) || b.runs - a.runs || (a.name < b.name ? -1 : 1));
  // WHY colours handed out to the configs the filter leaves, in one stable order: 30 configs exceed the 16-colour palette,
  // and every figure on a page gets the same kept rows, so they agree; the UR5e cell's five always get the first five.
  cfgList.forEach((c, i) => { c.color = PALETTE[i % PALETTE.length]; c.index = i; });
  const cache = new Map();

  const matches = (t, where) => {
    for (const k in where) {
      if (where[k] === undefined || where[k] === null) continue;
      if (t[k] !== where[k]) return false;
    }
    return true;
  };
  /** The value of one group under `where` (keys of a target: speed, dataset, split, deployment, facet). */
  function value(field, by, group, where = {}) {
    const key = `${field}|${by}|${group}|${JSON.stringify(where)}`;
    if (cache.has(key)) return cache.get(key);
    const items = (tmed[field][by].get(group) || []).filter((item) => matches(item.t, where));
    const out = items.length ? { v: median(items.map((i) => i.v)), n: items.length, items } : null;
    cache.set(key, out);
    return out;
  }
  /** Every config with a value under `where`, best (lowest) first; ties by the stable order. */
  function league(field = 'tcp', where = {}) {
    return cfgList.map((c) => ({ c, cell: value(field, 'config', c.name, where) }))
      .filter((x) => x.cell)
      .sort((a, b) => a.cell.v - b.cell.v || a.c.index - b.c.index)
      .map((x) => ({ name: x.c.name, config: x.c, v: x.cell.v, n: x.cell.n, items: x.cell.items }));
  }
  /** The distinct values of a target key among targets with a tool RMS value (optionally at a speed). */
  function columns(key, where = {}) {
    const seen = new Set();
    for (const list of tmed.tcp.config.values()) for (const item of list) if (matches(item.t, where)) seen.add(item.t[key]);
    return [...seen];
  }
  /** Nov 23's "best in X of Y cells": every (dataset · split, speed) cell with two or more configs, at every speed. */
  function wins(field = 'tcp') {
    const out = new Map(cfgList.map((c) => [c.name, { wins: 0, of: 0 }]));
    let cells = 0;
    for (const facet of columns('facet').sort()) {
      for (const speed of speeds) {
        const present = cfgList.map((c) => ({ c, cell: value(field, 'config', c.name, { facet, speed }) })).filter((x) => x.cell);
        if (present.length < 2) continue;
        cells += 1;
        for (const x of present) out.get(x.c.name).of += 1;
        const winner = present.reduce((a, b) => (b.cell.v < a.cell.v ? b : a));
        out.get(winner.c.name).wins += 1;
      }
    }
    return { cells, byConfig: out };
  }
  /** Configs not dominated on (cost, tool RMS): no other is at most as costly and as inaccurate, and better in one. */
  function pareto(points) {
    return points.filter((p) => !points.some((q) => q !== p && q.x <= p.x && q.y <= p.y && (q.x < p.x || q.y < p.y)));
  }
  const modelTypes = [...new Set(cfgList.map((c) => c.modelType))]
    .sort((a, b) => (MODEL_TYPE_ORDER.indexOf(a) + 99) % 99 - (MODEL_TYPE_ORDER.indexOf(b) + 99) % 99);
  return {
    rows, targets, configs: cfgList, configOf: configs, deployments: [...deployments].sort((a, b) => depOrder(a) - depOrder(b)),
    modelTypes, speeds, top, slowest, value, league, columns, wins, pareto, depOrder,
  };
}

// ── formatting (Nov 23's dataset.js rules) ──
export function num3(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value === 0) return '0';
  const abs = Math.abs(value);
  if (abs >= 1000) return Math.round(value).toLocaleString('en-US');
  if (abs >= 100) return value.toFixed(0);
  let text = Number(value.toPrecision(3)).toString();
  if (/e/.test(text)) text = value.toFixed(Math.min(8, 2 - Math.floor(Math.log10(abs))));
  return text;
}
export function times(ratio) {
  if (ratio === null || !Number.isFinite(ratio)) return '—';
  if (ratio >= 100) return `${Math.round(ratio).toLocaleString('en-US')}×`;
  if (ratio >= 10) return `${ratio.toFixed(0)}×`;
  if (ratio > 0.9 && ratio < 1.1) return `${Number(ratio.toPrecision(3))}×`;
  return `${Number(ratio.toPrecision(2))}×`;
}
export function speedText(speed) {
  return speed === null || speed === undefined ? '—' : `${Number(speed)}×`;
}
