/* The round's shared host glue (identical copy in v1..v5; v1/host-common.js is the source, the others are copies).
   Everything inside <data-workbench> is stock data-ui; this file only does what data-ui cannot (each named in NOTES.md):
   - html[data-ready=1] once the open page's panels drew (data-ui marks the workbench, not its dashboards);
   - the cross-deployment warning line when the kept runs span more than one deployment (no conditional note in data-ui);
   - the Fold button: §53 folds the rail only under 1,100 px, so it sets the stock fold="always" on the workbench's rail;
   - onDrill(label, fn): a host action on a stock drill button (data-ui's drill runs href / post / copy only).
   The rows are the scope's own (wb.scope.data.rows, wb.model.rows): nothing is loaded twice. */

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window */ } },
};
export { store };

export function host({ variant }) {
  const wb = document.getElementById('tc');
  const warn = document.getElementById('warn');
  const foldBtn = document.getElementById('fold');
  const FOLD = `tc-round/${variant}/rail-folded`;
  const api = { wb, rows: () => (wb.scope && wb.scope.data ? wb.scope.data.rows : []), kept: () => (wb.model ? wb.model.rows : []),
    byId: new Map(), drills: [], onChange: [] };

  function applyFold(folded) {
    const fold = wb.querySelector('data-fold.dw-rail');
    if (!fold) return;
    if (folded) fold.setAttribute('fold', 'always'); else { fold.removeAttribute('fold'); if (fold.hasAttribute('open')) fold.toggle(false); }
    foldBtn.setAttribute('aria-pressed', String(folded));
    foldBtn.textContent = folded ? '⟩ Show filters' : '⟨ Fold filters';
  }
  foldBtn.addEventListener('click', () => { const next = foldBtn.getAttribute('aria-pressed') !== 'true'; store.set(FOLD, next); applyFold(next); });

  function changed() {
    const kept = api.kept();
    const deps = new Set(kept.map((r) => r.deployment));
    // WHY a warning and never a block (Zach, Nov 24): "If you use the same configuration across multiple deployments then
    // you can compare it" — the earlier same-deployment rule survives only as this line
    warn.hidden = deps.size <= 1;
    warn.textContent = deps.size > 1
      ? `⚠ ${deps.size} deployments in the filter (${[...deps].join(', ')}): a config compares across robots, but the robots differ — read the League with that in mind.`
      : '';
    for (const fn of api.onChange) fn(kept);
  }

  wb.addEventListener('data-scope-load', () => {
    api.byId = new Map(api.rows().map((r) => [String(r.id), r]));
    applyFold(store.get(FOLD, false));
  });
  wb.addEventListener('data-scope-change', changed);
  wb.addEventListener('data-scope-tab', changed);

  // a host action on a stock drill button: matched by its label, run instead of data-ui's (capture phase, stopped)
  api.onDrill = (labelStart, fn) => api.drills.push([labelStart, fn]);
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('#tc [data-drill-action]');
    if (!btn) return;
    const hit = api.drills.find(([l]) => btn.textContent.trim().startsWith(l));
    if (!hit) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const row = api.byId.get(btn.dataset.drillRow) || targetRow(btn.dataset.drillRow);
    hit[1](row, btn);
  }, true);
  // a Targets row's id is its target key (site|slug): the drill gets a stand-in with the fields the links need
  function targetRow(id) {
    const [site, slug] = String(id || '').split('|');
    return site && slug ? { id, site, target_slug: slug, target_key: id, isTarget: true } : null;
  }

  // the runs of one target that pass the rail (what a target view starts with checked)
  api.keptLines = (targetKey) => api.kept().filter((r) => r.target_key === targetKey).map((r) => r.line);
  api.targetUrl = (row, extra = {}) => {
    const q = new URLSearchParams({ site: row.site, target: row.target_slug, ...extra });
    // the round's checks open the workbench with ?dry=1: the target view's Open in Rerun then builds without a viewer
    if (new URLSearchParams(location.search).get('dry') === '1') q.set('dry', '1');
    return `/common/target.html?${q.toString().replace(/%2C/g, ',')}`;
  };

  // ready: the workbench drew and every panel on the open page drew
  (function tick() {
    const page = [...wb.querySelectorAll('data-dashboard[tab]')].find((d) => !d.hidden);
    const views = page ? [...page.querySelectorAll('data-views')] : [];
    if (wb.hasAttribute('data-ready') && page && page.hasAttribute('data-view') && views.length && views.every((v) => v.hasAttribute('data-view'))) {
      document.documentElement.dataset.ready = '1';
      return;
    }
    setTimeout(tick, 100);
  }());
  return api;
}
