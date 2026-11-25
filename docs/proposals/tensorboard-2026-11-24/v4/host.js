/* V4 "Model × deployment first, target in a side pane": the Overview leads with the model type × deployment matrix
   (views.base); Open target view opens common/target.html?embed=1 in a pane on the right of the workbench, its edge
   data-ui's own makeResizable (drag, ←/→, double-click resets, width remembered), ✕ closes it. */
import { host } from './host-common.js';
import { makeResizable } from '../vendor/data-ui/resize.js';

const api = host({ variant: 'v4' });
const pane = document.getElementById('pane');
const frame = document.getElementById('pane-frame');
let resize = null;
let current = null;

function src(row) { return api.targetUrl(row, { keep: api.keptLines(row.target_key).join(','), embed: '1' }); }

api.onDrill('Open target view', (row) => {
  if (!row) return;
  current = row;
  pane.hidden = false;
  if (!resize) resize = makeResizable(pane, { edge: 'left', min: 360, max: 1000, keep: 520, key: 'tc-round/v4/target-pane', label: 'the target view' });
  const title = (api.rows().find((r) => r.target_key === row.target_key) || {}).target || row.target_slug;
  document.getElementById('pane-title').textContent = title;
  document.getElementById('pane-open').href = api.targetUrl(row, { keep: api.keptLines(row.target_key).join(','), back: location.href });
  frame.src = src(row);
  // the stock drill sheet stays open over the tabs; close it (its own Escape) so the pane and the tabs both show
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
});
document.getElementById('pane-x').addEventListener('click', () => { pane.hidden = true; current = null; frame.removeAttribute('src'); });
api.onChange.push(() => { if (current && !pane.hidden) { const next = src(current); if (frame.getAttribute('src') !== next) frame.src = next; } });
