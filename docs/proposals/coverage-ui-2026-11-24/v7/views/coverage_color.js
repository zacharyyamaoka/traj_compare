/* coverage_color.js — the one colour + scale rule every coverage view uses (docs/COVERAGE.md).
 *
 * WHY BAM Reach's five maps, its 17 stops and its "Reverse (high = dark)" switch: Zach, 2026-11-23, "instead of like
 * 1 color lets just do what we did with like bam reach. we can you like vidiris. but lets make it easy for the user to
 * change if they want... to other good cmap and switch from high to low". Stops copied from
 * /home/bam/robot_reach/src/robot_reach/codes.py COLORMAPS (matplotlib's perceptually uniform maps).
 * WHY empty is white, never a colormap colour: Zach 2026-11-19, "so its clear that white means empty".
 * WHY linear first: Zach 2026-11-23, "Linear to me is BY far the most informative here".
 *
 *   const paint = CoverageColor.ramp('viridis', false);          // t in [0, 1] -> [r, g, b]
 *   const scaled = CoverageColor.scale(counts, 'linear', {enough: 10});
 *   scaled.t[i]   // -1 = empty (draw EMPTY), else 0..1 (paint it)
 *   scaled.ticks  // [{t, label}] for the colorbar; scaled.note says what the scale did ("clipped at p98: 412")
 */
(function (global) {
  'use strict';
  const MAPS = {
    viridis: [[68, 1, 84], [72, 24, 106], [71, 45, 123], [66, 64, 134], [59, 82, 139], [51, 99, 141], [44, 114, 142], [38, 130, 142], [33, 145, 140], [31, 160, 136], [40, 174, 128], [63, 188, 115], [94, 201, 98], [132, 212, 75], [173, 220, 48], [216, 226, 25], [253, 231, 37]],
    magma: [[0, 0, 4], [10, 8, 34], [29, 17, 71], [54, 16, 107], [81, 18, 124], [106, 28, 129], [131, 38, 129], [156, 46, 127], [183, 55, 121], [208, 65, 111], [231, 82, 99], [245, 107, 92], [252, 137, 97], [254, 167, 114], [254, 196, 136], [253, 226, 163], [252, 253, 191]],
    plasma: [[13, 8, 135], [49, 5, 151], [76, 2, 161], [102, 0, 167], [126, 3, 168], [149, 17, 161], [170, 35, 149], [188, 53, 135], [204, 71, 120], [218, 90, 106], [230, 108, 92], [240, 128, 78], [248, 149, 64], [253, 172, 51], [253, 197, 39], [248, 223, 37], [240, 249, 33]],
    inferno: [[0, 0, 4], [11, 7, 36], [33, 12, 74], [61, 9, 101], [87, 16, 110], [113, 25, 110], [138, 34, 106], [163, 44, 97], [188, 55, 84], [210, 70, 68], [228, 90, 49], [241, 115, 29], [249, 142, 9], [252, 172, 17], [249, 203, 53], [242, 234, 105], [252, 255, 164]],
    cividis: [[0, 34, 78], [0, 46, 106], [26, 56, 111], [50, 67, 109], [67, 78, 108], [83, 90, 109], [97, 101, 111], [111, 112, 115], [125, 124, 120], [140, 136, 120], [155, 148, 118], [171, 160, 114], [188, 174, 108], [205, 187, 99], [222, 201, 88], [240, 216, 70], [254, 232, 56]],
  };
  const NAMES = ['viridis', 'magma', 'plasma', 'inferno', 'cividis'];
  const SCALES = ['linear', 'log', 'equalized', 'visited', 'enough'];
  const SCALE_TITLES = {
    linear: 'linear (clipped at p98)', log: 'log', equalized: 'histogram-equalized',
    visited: 'visited / not', enough: '≥ enough samples / not',
  };
  const EMPTY = [255, 255, 255]; // never visited
  const OUTSIDE = [221, 220, 214]; // beyond the limit: the robot cannot go there
  const LIMIT = '#b4442f'; // the limit lines (solid = physical, dashed = planner)

  function ramp(name, reverse) {
    const stops = (MAPS[name] || MAPS.viridis).slice();
    if (reverse) stops.reverse();
    const last = stops.length - 1;
    return function (t) {
      const x = Math.min(1, Math.max(0, t)) * last;
      const i = Math.min(last - 1, Math.floor(x));
      const f = x - i;
      const a = stops[i];
      const b = stops[i + 1];
      return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f),
        Math.round(a[2] + (b[2] - a[2]) * f)];
    };
  }

  function css(rgb, alpha) {
    return alpha === undefined ? `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` : `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`;
  }

  function quantile(sorted, q) {
    if (!sorted.length) return 0;
    const at = (sorted.length - 1) * q;
    const lo = Math.floor(at);
    const hi = Math.min(sorted.length - 1, lo + 1);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo);
  }

  function round(value) {
    if (value >= 100) return String(Math.round(value));
    if (value >= 10) return value.toFixed(1).replace(/\.0$/, '');
    return value.toPrecision(2).replace(/\.?0+$/, '');
  }

  /* counts (array of numbers >= 0, or null for "no value") -> {t: Float32Array (-1 = empty), ticks, note, max}.
   * opts.enough: the "enough samples" threshold; opts.clip: linear's clip quantile (default 0.98 of the nonzero values);
   * opts.max: force the top of the scale (e.g. a shared max across small multiples). */
  function scale(counts, mode, opts) {
    opts = opts || {};
    const n = counts.length;
    const t = new Float32Array(n).fill(-1);
    const nonzero = [];
    for (let i = 0; i < n; i++) if (counts[i] !== null && counts[i] > 0) nonzero.push(counts[i]);
    nonzero.sort((a, b) => a - b);
    const top = nonzero.length ? nonzero[nonzero.length - 1] : 0;
    if (!nonzero.length) return { t, ticks: [], note: 'nothing visited', max: 0, mode };
    if (mode === 'visited') {
      for (let i = 0; i < n; i++) if (counts[i] > 0) t[i] = 1;
      return { t, ticks: [{ t: 1, label: 'visited' }], note: `${nonzero.length} cells visited`, max: top, mode };
    }
    if (mode === 'enough') {
      const enough = opts.enough || 10;
      let full = 0;
      for (let i = 0; i < n; i++) {
        if (counts[i] >= enough) { t[i] = 1; full++; } else if (counts[i] > 0) t[i] = 0.25;
      }
      return { t, ticks: [{ t: 0.25, label: `< ${enough}` }, { t: 1, label: `≥ ${enough}` }],
        note: `${full} of ${nonzero.length} visited cells have ≥ ${enough}`, max: top, mode };
    }
    if (mode === 'equalized') {
      // WHY it lifts thin cells: each cell's colour is its RANK among visited cells (the empirical CDF), so a cell
      // walked once is spread over the same colour range as a cell walked 1000 times. It shows WHERE, not HOW MUCH.
      for (let i = 0; i < n; i++) {
        if (!(counts[i] > 0)) continue;
        let lo = 0; let hi = nonzero.length;
        while (lo < hi) { const mid = (lo + hi) >> 1; if (nonzero[mid] < counts[i]) lo = mid + 1; else hi = mid; }
        let upper = lo;
        while (upper < nonzero.length && nonzero[upper] === counts[i]) upper++;
        t[i] = nonzero.length > 1 ? ((lo + upper - 1) / 2) / (nonzero.length - 1) : 1;
      }
      const ticks = [0, 0.25, 0.5, 0.75, 1].map((q) => ({ t: q, label: round(quantile(nonzero, q)) }));
      return { t, ticks, note: 'colour = rank among visited cells', max: top, mode };
    }
    if (mode === 'log') {
      const max = opts.max || top;
      const denominator = Math.log1p(max);
      for (let i = 0; i < n; i++) if (counts[i] > 0) t[i] = Math.min(1, Math.log1p(counts[i]) / denominator);
      const ticks = [1, 10, 100, 1000, 10000, 100000].filter((v) => v <= max)
        .map((v) => ({ t: Math.log1p(v) / denominator, label: round(v) }));
      ticks.push({ t: 1, label: round(max) });
      return { t, ticks, note: `log, top ${round(max)}`, max, mode };
    }
    // linear (default)
    const clip = opts.clip === undefined ? 0.98 : opts.clip;
    const max = opts.max || Math.max(quantile(nonzero, clip), nonzero[0]);
    for (let i = 0; i < n; i++) if (counts[i] > 0) t[i] = Math.min(1, counts[i] / max);
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((q) => ({ t: q, label: round(q * max) }));
    const clipped = top > max ? `clipped at p${Math.round(clip * 100)}: ${round(max)} (top cell ${round(top)})` : `top ${round(max)}`;
    return { t, ticks, note: clipped, max, mode };
  }

  global.CoverageColor = { MAPS, NAMES, SCALES, SCALE_TITLES, EMPTY, OUTSIDE, LIMIT, ramp, css, scale, quantile };
})(typeof window !== 'undefined' ? window : globalThis);
