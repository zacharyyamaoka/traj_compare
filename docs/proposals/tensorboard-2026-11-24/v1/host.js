/* V1 "The rail is the selection": Target is a rail facet; when the kept runs belong to exactly ONE target, the Runs tab
   shows that target's view (common/target.html?embed=1) above the runs table, its checkboxes = the runs the rail keeps.
   "Selected" = passes the rail. Open target view (drill) stays stock: a new tab. */
import { host } from './host-common.js';

const api = host({ variant: 'v1' });
const box = document.createElement('section');
box.id = 'v1-target';
box.hidden = true;
box.innerHTML = '<div class="v1-head"><b></b><span>the rail leaves one target: these are its runs, checked = kept by the rail</span></div><iframe title="Target view"></iframe>';
const style = document.createElement('style');
style.textContent = `#v1-target { display: block; margin: 10px 12px 0; background: var(--dv-bg, #fff); border: 1px solid var(--dv-border, #d0d7de); border-radius: 10px; overflow: hidden; }
  #v1-target[hidden] { display: none; }
  #v1-target .v1-head { display: flex; gap: 10px; align-items: baseline; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--dv-rule, #eaeef2); }
  #v1-target .v1-head span { color: var(--dv-muted, #57606a); font-size: 12px; }
  #v1-target iframe { display: block; width: 100%; height: 520px; border: 0; }`;
document.head.appendChild(style);
let shown = '';

function place() {
  const pages = api.wb.querySelector('.dw-pages');
  const runs = api.wb.querySelector('data-dashboard[tab="Runs"]');
  if (pages && runs && box.nextElementSibling !== runs) pages.insertBefore(box, runs);
}

api.onChange.push((kept) => {
  place();
  const targets = new Set(kept.map((r) => r.target_key));
  const one = targets.size === 1 && kept.length ? kept[0] : null;
  const onRuns = api.wb.tab === 'Runs';
  box.hidden = !(one && onRuns);
  if (!one) { shown = ''; return; }
  const url = api.targetUrl(one, { keep: kept.map((r) => r.line).join(','), embed: '1' });
  box.querySelector('b').textContent = one.target;
  if (url !== shown) { shown = url; box.querySelector('iframe').src = url; }
});
