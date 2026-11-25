/* V3 "The target is a workbench page": Open target view adds a page to the SAME component, a tab "Target · <task>"
   (a host element with `tab`, which data-ui's scope treats as a page) holding common/target.html?embed=1; its checkboxes
   start as the runs the rail keeps and follow the rail while it is open. One target page at a time. */
import { host } from './host-common.js';

const api = host({ variant: 'v3' });
const style = document.createElement('style');
style.textContent = `#tc .v3-target { display: block; height: 100%; }
  #tc .v3-target[hidden] { display: none; }
  #tc .v3-target iframe { display: block; width: 100%; height: 100%; border: 0; background: var(--dv-bg, #fff); }`;
document.head.appendChild(style);
let page = null, current = null, shown = '';

function src(row) { return api.targetUrl(row, { keep: api.keptLines(row.target_key).join(','), embed: '1' }); }

api.onDrill('Open target view', (row) => {
  if (!row) return;
  const task = (api.rows().find((r) => r.target_key === row.target_key) || {}).task || row.target_slug;
  const name = `Target · ${task}`;
  if (!page) {
    page = document.createElement('section');
    page.className = 'v3-target';
    page.innerHTML = '<iframe title="Target view"></iframe>';
    api.wb.querySelector('.dw-pages').appendChild(page);
  }
  page.setAttribute('tab', name);
  current = row;
  shown = src(row);
  page.querySelector('iframe').src = shown;
  api.wb.scope.show(name);
});
// the rail still narrows the open target's checkboxes (a new keep= when it changes)
api.onChange.push(() => {
  if (!page || !current) return;
  const next = src(current);
  if (next !== shown) { shown = next; page.querySelector('iframe').src = next; }
});
