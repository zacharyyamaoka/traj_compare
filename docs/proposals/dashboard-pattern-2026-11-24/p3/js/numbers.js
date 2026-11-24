/* numbers.js — two small views P3 registers for its dashboards' panels (CONTRACT §1, registerView).
 *
 *   numbers        headline numbers over the rows it is handed: stock <data-kpi> cards on a wide panel, a compact list
 *                  of label · value on a narrow one (`columns: 1`). Summaries: count, sum, min, max, median, distinct
 *                  (the size of a union of list cells, or its share of `total`), distinct-mean. With every row the
 *                  numbers that name a `payload` key equal analyze's (the oracle checks at load); on a subset each
 *                  carries data-ui's "~ derived" basis. Round 2's V2 had these as its `coverage-overview`. WHY not the
 *                  stock kpi view: data-ui has no "distinct items of a list column" summary yet (V2 gap 2).
 *   coverage-key   the one colour key a dashboard shares (the ramp from the gear's settings, white, grey, red frame),
 *                  so the small maps above it need none of their own.
 */

import { summarize } from './aggregate.js';
import { settingsOf, SCALE_NOTES } from './settings.js';
import { el, fmt, pct, legendItem, rampCss } from './occupancy.js';

const Color = globalThis.CoverageColor;

function payloadNumber(key) {
  const coverage = globalThis.COVERAGE_UI && globalThis.COVERAGE_UI.coverage;
  return coverage && key ? coverage.numbers.find((row) => row.key === key) : null;
}

function wholeText(row) {
  if (!row) return '';
  if (row.unit === '%') return pct(row.value);
  if (row.unit === 'm/s') return `${row.value.toFixed(2)} m/s`;
  return fmt(row.value) + (row.unit ? ` ${row.unit}` : '');
}

function valueText(value, spec) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const decimals = spec.decimals ?? (spec.unit === '%' ? 1 : 0);
  const text = value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).replace(/,/g, ' ');
  return text;
}

export class NumbersView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('p3-view', 'p3-numbers');
  }

  update(input) {
    const view = input.view || {};
    const rows = input.rows;
    const all = rows.length === input.total;
    const specs = view.numbers || [];
    const list = view.columns === 1 || view.compact;
    let body;
    if (list) {
      // a narrow panel: label · value rows (the producer's number beside it when nothing is filtered)
      body = el('dl', { class: 'p3-numlist' + (view.compact ? ' p3-numlist-compact' : ''), 'data-p3-stats': '' });
      for (const spec of specs) {
        const value = rows.length ? summarize(spec, rows) : null;
        const unit = spec.unit ? (spec.unit === '%' || spec.unit === '°' ? spec.unit : ` ${spec.unit}`) : '';
        body.append(el('div', { class: 'p3-numrow', title: [spec.note, all ? 'all 212 trajectories' : `re-aggregated over ${rows.length} trajectories`].filter(Boolean).join(' · ') }, [
          el('dt', { text: spec.label }),
          el('dd', {}, [el('b', { text: valueText(value, spec) }), unit ? el('span', { class: 'p3-unit', text: unit }) : null,
            !all && spec.summary !== 'count' ? el('span', { class: 'p3-derived', title: 'derived: re-aggregated over the rows the filters leave', text: '~' }) : null]),
        ]));
      }
    } else {
      // the headline numbers: stock <data-kpi> cards over THIS subset; equal to analyze's when nothing is filtered
      // WHY even rows: ten numbers read as two rows of five, not seven and three
      const cols = view.columns || (specs.length > 6 ? Math.ceil(specs.length / 2) : specs.length);
      body = el('div', { class: 'p3-kpis', 'data-p3-stats': '', style: `--cols:${cols}` });
      for (const spec of specs) {
        const value = rows.length ? summarize(spec, rows) : null;
        const payload = payloadNumber(spec.payload);
        const card = document.createElement('data-kpi');
        const decimals = spec.decimals ?? (spec.unit === '%' ? 1 : 0);
        card.card = {
          label: spec.label,
          value: { value, unit: spec.unit, basis: all ? undefined : 'derived', note: all ? `analyze: ${payload ? payload.value : '—'}` : 're-aggregated over the rows the filters leave' },
          column: { decimals },
          format: { compact: false },
          from: [spec.note, all ? (payload ? 'analyze' : null) : `subset of ${rows.length}`].filter(Boolean).join(' · '),
        };
        body.append(card);
      }
    }
    const whole = (view.whole || []).map(payloadNumber).filter(Boolean);
    const wholeLine = whole.length ? el('p', { class: 'p3-whole' }, [
      el('span', { class: 'p3-whole-label', text: all ? 'Also from analyze:' : 'Whole set only (needs every sample, does not re-aggregate):' }),
      ...whole.map((row) => el('span', { class: 'p3-whole-item', title: row.key }, [row.label.replace(/ \(.*\)$/, ''), ' ', el('b', { text: wholeText(row) })])),
    ]) : null;
    const caveat = view.caveat ? el('p', { class: 'p3-caveat', text: view.caveat }) : null;
    this.el.replaceChildren(el('div', { class: 'p3-viewbody' }, [body, wholeLine, caveat]));
  }

  destroy() {}
}

export class KeyView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('p3-view', 'p3-keyview');
  }

  update(input) {
    const view = input.view || {};
    const settings = settingsOf(input, this.host && this.host.element);
    const ramp = Color.ramp(settings.cmap, settings.reverse);
    const items = view.items || ['ramp', 'empty', 'outside', 'frame'];
    const labels = {
      ramp: [`colour = trajectories per cell, one scale per figure (${Color.SCALE_TITLES[settings.scale]})`, rampCss(ramp)],
      empty: ['white = no trajectory of this subset'],
      outside: ['grey = the robot cannot reach it'],
      frame: ['red frame = the joint\'s limit box'],
    };
    const key = el('div', { class: 'p3-legend', 'data-p3-key': '' }, items.map((item) => legendItem(item, ...(labels[item] || [item]))));
    this.el.replaceChildren(el('div', { class: 'p3-viewbody p3-keybody' }, [key,
      el('p', { class: 'p3-scale-note', text: view.note || SCALE_NOTES[settings.scale] })]));
  }

  destroy() {}
}
