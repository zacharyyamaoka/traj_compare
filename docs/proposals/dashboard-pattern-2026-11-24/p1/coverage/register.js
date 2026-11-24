/* register.js — the coverage app's part of P1: the three views its .base names that stock data-ui does not have,
 * registered once (CONTRACT §1, registerView), and their stylesheet. Load it before the workbench draws a page. */

import { registerView } from '../../vendor/data-ui/data-ui.js';
import './coverage_color.js';
import { OccupancyView, NumbersView, DatasetMixView } from './views.js';

registerView('occupancy', { name: 'Occupancy', icon: 'chart', load: async () => ({ default: OccupancyView }) });
registerView('coverage-numbers', { name: 'Coverage numbers', icon: 'kpi', load: async () => ({ default: NumbersView }) });
registerView('dataset-mix', { name: 'Dataset mix', icon: 'chart', load: async () => ({ default: DatasetMixView }) });

if (!document.querySelector('link[data-coverage-css]')) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = new URL('./coverage.css', import.meta.url).href;
  link.dataset.coverageCss = '';
  document.head.append(link);
}
