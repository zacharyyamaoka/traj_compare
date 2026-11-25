/* T1 on V2 "Two viewers, the filter carried" (V2's host.js, ../../tensorboard-2026-11-24/v2/host.js, plus one rule):
   Open target view opens common/target.html as its own page in this tab, back= this workbench URL with its filter and
   tab. A Targets or Runs row keeps the runs the rail keeps for that target (V2); a row of the new tab's dataset
   (pairs) is a sim ↔ real pair: keep= its two lines (the prediction and the real run).
   WHY the host: data-ui's drill runs href / post / copy only (V2 NOTES gap 2), and its href cannot carry keep=. */
import { host } from './host-common.js';

const api = host({ variant: 't1' });
const DATASET = 'pairs';
let extra = new Map();
api.wb.addEventListener('data-scope-load', () => {
  const sets = api.wb.scope && api.wb.scope.datasets;
  const rows = sets && sets[DATASET] ? sets[DATASET].rows : [];
  extra = new Map(rows.map((r) => [String(r.id), r]));
});

api.onDrill('Open target view', (row, btn) => {
  const own = extra.get(String(btn.dataset.drillRow));
  if (own) {
    // WHY both lines whatever the rail's Sim / real says: a pair IS the prediction and the measurement of one run
    const keep = String(own.keep).split(',').map(Number);
    location.href = api.targetUrl(own, { keep: keep.join(','), back: location.href });
    return;
  }
  if (!row) return;
  const keep = api.keptLines(row.target_key);
  location.href = api.targetUrl(row, { keep: keep.join(','), back: location.href });
});
window.TC_HOST = api;
