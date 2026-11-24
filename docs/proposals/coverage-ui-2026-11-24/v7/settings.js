/* <data-settings> — the prototype of PROPOSED-CONTRACT.md §52.6: a dashboard's reader settings behind one gear.
 *
 * WHY an element of its own (like <data-facets for>): Zach, Nov 24: "the colors … perhaps those are in a settings gear
 * in the top right corner, things that apply to the entire thing that you set once". The settings are the style keys
 * the .base lists under `settings:` (their option types are Obsidian's, the ones a view's options() already uses, plus
 * `colormap`), the file's `style:` holds their defaults, the reader's picks are kept in this browser and win.
 *
 *   <data-settings key="coverage-ur5e"></data-settings>
 *   el.spec = base.settings; el.defaults = base.style;            // then el.value → {colormap, reverse, scale}
 *   el.addEventListener('data-settings-change', (e) => e.detail.settings)
 *
 * In data-ui it would be drawn by <data-dashboard> in its bar (right-most, as Display is in a view's bar) and each
 * view would get the resolved values as `input.settings`; here the host hands them on through the dashboard's style
 * (resolveStyle keeps unknown keys, so every panel already sees `input.view.style.colormap`).
 */
import './views/coverage_color.js';

const Color = globalThis.CoverageColor;
const NOTES = {
  linear: 'Colour grows in proportion to the count; the top 2 % of cells are clipped so one hot cell does not wash out the rest.',
  log: 'Colour follows log(count), so thin cells show too; equal colour steps are ×10, not +10.',
  equalized: 'Colour = rank among the visited cells: shows WHERE the data is, not HOW MUCH.',
  visited: 'One colour for every cell with any sample: is it covered at all?',
  enough: 'Full colour = at least the "enough" count of samples; pale = visited, but fewer.',
};
const GEAR = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

function esc(text) { return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
function gradient(name, reverse) {
  const ramp = Color.ramp(name, reverse);
  const stops = [];
  for (let i = 0; i <= 8; i++) { const c = ramp(i / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]}) ${(i / 8) * 100}%`); }
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}

class DataSettings extends HTMLElement {
  constructor() {
    super();
    this.spec = {};
    this.defaults = {};
    this._picks = {};
  }

  get storeKey() { return `data-ui/settings/${this.getAttribute('key') || 'page'}`; }

  /** The resolved settings: the reader's pick, else the file's style default, else the option's first value. */
  get value() {
    const out = {};
    for (const [key, opt] of Object.entries(this.spec || {})) {
      const first = opt.type === 'toggle' ? false : Array.isArray(opt.options) ? opt.options[0] : Object.keys(opt.options || {})[0];
      out[key] = this._picks[key] !== undefined ? this._picks[key] : this.defaults[key] !== undefined ? this.defaults[key] : first;
    }
    return out;
  }

  connectedCallback() {
    if (this._drawn) return;
    this._drawn = true;
    try { this._picks = JSON.parse(localStorage.getItem(this.storeKey) || '{}') || {}; } catch { this._picks = {}; }
    this.classList.add('ds');
    this.innerHTML = `<button type="button" class="ds-gear" data-settings-gear aria-haspopup="dialog" aria-expanded="false" aria-label="Settings: colours for every figure" title="Settings: colours for every figure">${GEAR}<span class="ds-gear-label">Settings</span></button>
      <div class="ds-panel" role="dialog" aria-label="Settings" data-settings-panel hidden></div>`;
    this.gear = this.querySelector('.ds-gear');
    this.panel = this.querySelector('.ds-panel');
    this.gear.addEventListener('click', () => (this.panel.hidden ? this.open() : this.close()));
    this._outside = (e) => { if (!this.panel.hidden && !this.contains(e.target)) this.close(); };
    this._key = (e) => { if (e.key === 'Escape' && !this.panel.hidden) { e.stopPropagation(); this.close(); this.gear.focus(); } };
    document.addEventListener('pointerdown', this._outside, true);
    document.addEventListener('keydown', this._key, true);
    this.render();
  }

  disconnectedCallback() {
    document.removeEventListener('pointerdown', this._outside, true);
    document.removeEventListener('keydown', this._key, true);
  }

  open() { this.render(); this.panel.hidden = false; this.gear.setAttribute('aria-expanded', 'true'); }
  close() { this.panel.hidden = true; this.gear.setAttribute('aria-expanded', 'false'); }

  set(key, value) {
    this._picks = { ...this._picks, [key]: value };
    try { localStorage.setItem(this.storeKey, JSON.stringify(this._picks)); } catch { /* private window: kept for this page only */ }
    this.render();
    this.dispatchEvent(new CustomEvent('data-settings-change', { bubbles: true, detail: { settings: this.value, key } }));
  }

  reset() {
    this._picks = {};
    try { localStorage.removeItem(this.storeKey); } catch { /* nothing kept */ }
    this.render();
    this.dispatchEvent(new CustomEvent('data-settings-change', { bubbles: true, detail: { settings: this.value, key: null } }));
  }

  render() {
    if (!this.panel) return;
    const v = this.value;
    const rows = [];
    for (const [key, opt] of Object.entries(this.spec || {})) {
      const label = esc(opt.displayName || key);
      if (opt.type === 'colormap') {
        const names = Array.isArray(opt.options) ? opt.options : Color.NAMES;
        rows.push(`<fieldset class="ds-row"><legend>${label}</legend><div class="ds-maps" role="radiogroup" aria-label="${label}" data-setting="${esc(key)}">${names.map((name) => `<button type="button" role="radio" class="ds-map" data-value="${esc(name)}" aria-checked="${v[key] === name}"><i style="background:${gradient(name, !!v.reverse)}"></i><span>${esc(name)}</span></button>`).join('')}</div></fieldset>`);
      } else if (opt.type === 'toggle') {
        rows.push(`<label class="ds-row ds-check"><input type="checkbox" data-setting="${esc(key)}"${v[key] ? ' checked' : ''}><span>${label}</span></label>`);
      } else {
        const options = Array.isArray(opt.options) ? Object.fromEntries(opt.options.map((o) => [o, o])) : opt.options || {};
        rows.push(`<label class="ds-row ds-select"><span>${label}</span><select data-setting="${esc(key)}">${Object.entries(options).map(([o, l]) => `<option value="${esc(o)}"${v[key] === o ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>${key === 'scale' ? `<p class="ds-note" data-scale-note>${esc(NOTES[v[key]] || '')}</p>` : ''}`);
      }
    }
    const changed = Object.keys(this._picks).length > 0;
    this.panel.innerHTML = `<header class="ds-head"><div><h2>Settings</h2><p>Set once: every figure on every tab follows.</p></div><button type="button" class="ds-close" data-settings-close aria-label="Close settings">✕</button></header>
      ${rows.join('')}
      <footer class="ds-foot"><span>${changed ? 'Your picks, kept in this browser.' : 'The file\'s defaults (its <code>style:</code>).'}</span>${changed ? '<button type="button" class="ds-reset" data-settings-reset>Reset to the file\'s</button>' : ''}</footer>`;
    this.panel.querySelector('[data-settings-close]').addEventListener('click', () => { this.close(); this.gear.focus(); });
    const reset = this.panel.querySelector('[data-settings-reset]');
    if (reset) reset.addEventListener('click', () => this.reset());
    for (const group of this.panel.querySelectorAll('.ds-maps')) {
      group.addEventListener('click', (e) => {
        const b = e.target.closest('[data-value]');
        if (b && b.getAttribute('aria-checked') !== 'true') this.set(group.dataset.setting, b.dataset.value);
      });
    }
    for (const input of this.panel.querySelectorAll('input[data-setting]')) input.addEventListener('change', () => this.set(input.dataset.setting, input.checked));
    for (const select of this.panel.querySelectorAll('select[data-setting]')) select.addEventListener('change', () => this.set(select.dataset.setting, select.value));
  }
}

if (!customElements.get('data-settings')) customElements.define('data-settings', DataSettings);
