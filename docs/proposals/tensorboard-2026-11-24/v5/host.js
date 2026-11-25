/* V5 "A selection basket across targets": a Runs row's ＋ Add to selection puts that run in a basket kept in this
   browser (localStorage, try/catch) and shown on every tab ("Selection · N runs"); Open target view opens
   common/target.html?basket=site:line,… (the basket grouped by target), Open in Rerun posts the basket to the round's
   endpoint. The basket ignores the rail on purpose: it is for comparisons across targets and deployments. */
import { host, store } from './host-common.js';

const api = host({ variant: 'v5' });
const KEY = 'tc-round/v5/basket';
let basket = store.get(KEY, []);
const $ = (id) => document.getElementById(id);

function draw() {
  $('basket-n').textContent = String(basket.length);
  $('basket').classList.toggle('empty', !basket.length);
  $('basket-rerun').textContent = `Open in Rerun (${basket.length})`;
  $('basket-open').disabled = $('basket-rerun').disabled = !basket.length;
  $('basket').title = basket.length ? basket.join('\n') : 'Empty: open a run on the Runs tab, then ＋ Add to selection';
}
function save() { store.set(KEY, basket); draw(); }

api.onDrill('＋ Add to selection', (row, btn) => {
  if (!row || row.isTarget) {
    // a Targets row: add every run of that target the rail keeps
    const ids = api.kept().filter((r) => row && r.target_key === row.target_key).map((r) => String(r.id));
    for (const id of ids) if (!basket.includes(id)) basket.push(id);
    save();
    $('basket-status').textContent = `+${ids.length} runs`;
    return;
  }
  const id = String(row.id);
  if (!basket.includes(id)) basket.push(id);
  save();
  const status = btn.parentElement && btn.parentElement.querySelector('.ds-act-status');
  if (status) status.textContent = `In the selection (${basket.length})`;
});
$('basket-clear').addEventListener('click', () => { basket = []; save(); $('basket-status').textContent = ''; });
$('basket-open').addEventListener('click', () => {
  if (!basket.length) return;
  const dry = new URLSearchParams(location.search).get('dry') === '1' ? '&dry=1' : '';
  window.open(`/common/target.html?basket=${basket.join(',')}${dry}&back=${encodeURIComponent(location.href)}`, '_blank', 'noopener');
});
$('basket-rerun').addEventListener('click', async () => {
  if (!basket.length) return;
  $('basket-status').textContent = 'Sending…';
  try {
    const runs = basket.map((id) => { const [site, line] = id.split(':'); return { site, line: Number(line) }; });
    // dry=1 when the page was opened with ?dry=1 (the round's checks: build the .rrd, open no viewer)
    const dry = new URLSearchParams(location.search).get('dry') === '1' ? '?dry=1' : '';
    const res = await fetch(`/__rerun/selection${dry}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ runs }) });
    const answer = await res.json().catch(() => ({}));
    window.TC_LAST_RERUN = answer; // read by the round's check.cjs
    if (!res.ok || answer.ok === false) throw new Error(answer.error || `HTTP ${res.status}`);
    $('basket-status').textContent = dry ? `Built (not launched): ${answer.n ?? runs.length} runs` : `Sent ${answer.n ?? runs.length} runs to Rerun ✓`;
  } catch (err) { $('basket-status').textContent = `Could not: ${err.message}`; }
});
draw();
