/* traj_compare's runs workbench, the host glue around the stock <data-workbench id="tc"> (traj_compare.runs_workbench).
   Everything inside the workbench is stock data-ui; this file only does what data-ui cannot yet (docs/RUNS_WORKBENCH.md
   names each gap and its data-ui ask):
   - "Open target view" opens the target view IN THIS TAB, the runs the rail keeps for that target ticked (keep=) and
     this page's URL (its rail and its tab) as back=, so the target view's ‹ link returns to exactly this filter
     (data-ui's drill runs href / post / copy, and an href opens a new tab: gap 2);
   - the cross-deployment warning when the kept runs span more than one deployment (no conditional note: gap 5);
   - the Fold button: the stock rail folds only under 1,100 px, so it sets the stock fold="always" (gap 6);
   - html[data-ready=1] once the open page's panels drew (data-ui marks the workbench, not its dashboards).
   The rows are the scope's own (wb.scope.data.rows, wb.model.rows): nothing is loaded twice. */
const wb = document.getElementById('tc');
const warn = document.getElementById('warn');
const foldButton = document.getElementById('fold');
const FOLD_KEY = `traj-compare/runs-workbench/${location.pathname}/rail-folded`;
const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* a private window */ } },
};
const allRows = () => (wb.scope && wb.scope.data ? wb.scope.data.rows : []);
const keptRows = () => (wb.model ? wb.model.rows : []);
let byId = new Map();

function applyFold(folded) {
  const fold = wb.querySelector('data-fold.dw-rail');
  if (!fold) return;
  if (folded) fold.setAttribute('fold', 'always');
  else { fold.removeAttribute('fold'); if (fold.hasAttribute('open') && fold.toggle) fold.toggle(false); }
  foldButton.setAttribute('aria-pressed', String(folded));
  foldButton.textContent = folded ? '⟩ Show filters' : '⟨ Fold filters';
}
foldButton.addEventListener('click', () => {
  const next = foldButton.getAttribute('aria-pressed') !== 'true';
  store.set(FOLD_KEY, next);
  applyFold(next);
});

function changed() {
  const deployments = [...new Set(keptRows().map((row) => row.deployment))];
  // WHY a warning and never a block (Zach, 2026-11-24): "If you use the same configuration across multiple deployments
  // then you can compare it"; the earlier same-deployment rule survives only as this line
  warn.hidden = deployments.length <= 1;
  warn.textContent = deployments.length > 1
    ? `⚠ ${deployments.length} deployments in the filter (${deployments.join(', ')}): a config compares across robots, but the robots differ — read the League with that in mind.`
    : '';
}
wb.addEventListener('data-scope-load', () => {
  byId = new Map(allRows().map((row) => [String(row.id), row]));
  applyFold(store.get(FOLD_KEY, false));
});
wb.addEventListener('data-scope-change', changed);
wb.addEventListener('data-scope-tab', changed);

/** The target view's URL for one target: the runs the rail keeps ticked, this page (filter and tab) to come back to. */
function targetUrl(site, slug) {
  const key = `${site}|${slug}`;
  const keep = keptRows().filter((row) => row.target_key === key).map((row) => row.line);
  // WHY the path, not location.href: back= travels on into playback's breadcrumb, which takes same-origin paths only
  const query = new URLSearchParams({ site, target: slug, keep: keep.join(','), back: location.pathname + location.search + location.hash });
  return `target.html?${query.toString().replace(/%2C/g, ',')}`;
}

// the stock "Open target view" button, run here instead of data-ui's new tab (capture phase, matched by its label)
document.addEventListener('click', (event) => {
  const button = event.target.closest && event.target.closest('#tc [data-drill-action]');
  if (!button || !button.textContent.trim().startsWith('Open target view')) return;
  const id = button.dataset.drillRow || '';
  const row = byId.get(id);
  // a Targets row's id is its target key (<site>|<slug>); a Runs row's is <site>:<line>
  const [site, slug] = row ? [row.site, row.target_slug] : id.split('|');
  if (!site || !slug) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  location.href = targetUrl(site, slug);
}, true);

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
