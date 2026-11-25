/* T3 on V2 "Two viewers, the filter carried" (V2's host.js, ../../tensorboard-2026-11-24/v2/host.js, plus one rule):
   Open target view opens common/target.html as its own page in this tab, back= this workbench URL with its filter and
   tab. A Targets or Runs row keeps the runs the rail keeps for that target (V2); a row of the new tab's dataset
   (h2h) is a match-up: keep= A's and B's runs of that target (those the rail keeps).
   WHY the host: data-ui's drill runs href / post / copy only (V2 NOTES gap 2), and its href cannot carry keep=. */
import { host } from './host-common.js';

const api = host({ variant: 't3' });
const DATASET = 'h2h';
let extra = new Map();
api.wb.addEventListener('data-scope-load', () => {
  const sets = api.wb.scope && api.wb.scope.datasets;
  const rows = sets && sets[DATASET] ? sets[DATASET].rows : [];
  extra = new Map(rows.map((r) => [String(r.id), r]));
});

api.onDrill('Open target view', (row, btn) => {
  const own = extra.get(String(btn.dataset.drillRow));
  if (own) {
    const kept = new Set(api.keptLines(own.target_key));
    const lines = String(own.keep).split(',').map(Number);
    // WHY the rail's runs only when it keeps some of them: a row of this tab is about exactly these runs
    const keep = lines.some((l) => kept.has(l)) ? lines.filter((l) => kept.has(l)) : lines;
    location.href = api.targetUrl(own, { keep: keep.join(','), back: location.href });
    return;
  }
  if (!row) return;
  const keep = api.keptLines(row.target_key);
  location.href = api.targetUrl(row, { keep: keep.join(','), back: location.href });
});
// data-ui gap (NOTES.md gap 1): the dashboard's drill hands its sheet the 26,442-row h2h dataset and calls openPeek
// before that sheet has a model, so the first click on a match-up row throws "reading 'pivot'" (a second click works).
// Until data-ui waits for it, the drill is retried once the sheet has drawn. drill() is one of the dashboard's public
// methods (CONTRACT §17); nothing else of it is touched.
function guardDrill() {
  const dash = api.wb.querySelector(`data-dashboard[tab="${'Which config wins head to head?'}"]`);
  if (!dash || dash._t3Guard || typeof dash.drill !== 'function') return;
  dash._t3Guard = true;
  const stock = dash.drill.bind(dash);
  dash.drill = (p, el, rowId, opts = {}) => {
    try {
      return stock(p, el, rowId, opts);
    } catch (err) {
      const sheet = dash.querySelector(':scope > data-views.dd-drill');
      if (!sheet) throw err;
      sheet.addEventListener('data-views-render', () => sheet.openPeek(rowId, opts), { once: true });
      return undefined;
    }
  };
}
api.wb.addEventListener('data-scope-load', () => setTimeout(guardDrill, 0));
api.wb.addEventListener('data-scope-tab', guardDrill);
window.TC_HOST = api;
