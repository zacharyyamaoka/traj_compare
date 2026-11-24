#!/usr/bin/env python3
"""Build the league-table review report (2026-11-23): one self-contained HTML page with every capture inlined.

    python3 docs/league_2026-11-23/build_report.py

Reads reports/media/league-2026-11-23/ (written by measure.cjs and record.cjs on the bench's rebuilt sites, plus the
before captures) and writes reports/media/league-2026-11-23.html. Stdlib only; screenshots are re-encoded as JPEG with
ffmpeg to keep the page small.
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEDIA = REPO / "reports" / "media" / "league-2026-11-23"
OUT = REPO / "reports" / "media" / "league-2026-11-23.html"
ROBOTS = (("ur5e", "UR5e (sim, 5 configs)"), ("bam_fb", "BAM five-bar (sim + real)"), ("pendulum", "Pendulum (sim + real + rehearsal)"))
# Measured before this change, 1440 px wide: the Nov 20 number Zach saw, and today's pages (the UR5e already opened on the
# speed sweep, the other two still on the target cards) as captured by measure_before in this folder's README of runs.
BEFORE_NOV20 = {"ur5e": 206_472}
SCREEN = 900


def jpeg(path: Path, width: int = 1100, quality: int = 7) -> str:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={width}:-2", "-q:v", str(quality), "-f", "image2pipe",
                          "-vcodec", "mjpeg", "-"], capture_output=True, check=True).stdout
    return "data:image/jpeg;base64," + base64.b64encode(out).decode()


def raw(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def screens(px: int) -> str:
    return f"{px / SCREEN:.1f}"


def main() -> None:
    measured = {name: json.loads((MEDIA / f"{name}.json").read_text()) for name, _ in ROBOTS if (MEDIA / f"{name}.json").is_file()}
    before = json.loads((MEDIA / "before.json").read_text())
    esc = html.escape

    rows = []
    for name, label in ROBOTS:
        m = measured.get(name)
        if not m:
            continue
        t = m["tabs"]
        cells = [t.get("overview"), t.get("sweeps"), t.get("targets_cards"), t.get("targets_table"), t.get("runs"), t.get("drill")]
        worst = max(v for v in cells if v)
        before_px = before.get(name)
        nov20 = BEFORE_NOV20.get(name)
        rows.append(
            f"<tr><th>{esc(label)}</th><td>{f'{nov20:,}' if nov20 else '—'}</td><td>{before_px:,} <span>({screens(before_px)} scr)</span></td>"
            + "".join(f"<td class='{'ok' if (v or 0) <= 3.5 * SCREEN else 'warn'}'>{f'{v:,}' if v else '—'}</td>" for v in cells)
            + f"<td>{m['league']['bottom']} px</td><td>{m['league']['rows']}</td><td>{worst / SCREEN:.1f}</td></tr>")
    table = ("<table class='h'><thead><tr><th>site</th><th>landing, Nov 20</th><th>landing today, before</th><th>Overview</th><th>Speed sweeps</th>"
             "<th>Targets · cards</th><th>Targets · table</th><th>Runs</th><th>Drill (config's worst)</th><th>league bottom</th><th>league rows</th>"
             "<th>tallest tab, screens</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    def shot(name: str, caption: str, width: int = 1100) -> str:
        path = MEDIA / f"{name}.png"
        if not path.is_file():
            return ""
        return f"<figure><img src='{jpeg(path, width)}' alt='{esc(caption)}'><figcaption>{esc(caption)}</figcaption></figure>"

    verdicts = "".join(
        f"<li><b>{esc(label)}</b>: {esc(measured[name]['league']['verdict'])}</li>" for name, label in ROBOTS if name in measured)
    drills = "".join(
        f"<li><b>{esc(label)}</b>: rank-1 row → <code>{esc(measured[name]['drill']['hash'])}</code> ({measured[name]['drill']['rows']} rows) → "
        f"<code>{esc(measured[name]['target']['hash'][:70])}…</code>, run list shown: {measured[name]['target']['run_list']}; "
        f"Coverage ↗ link: {'opens ' + esc(measured[name].get('coverage', {}).get('url', '?')) + ' (“' + esc(measured[name].get('coverage', {}).get('title', '')) + '”)' if measured[name].get('coverage', {}).get('link') else 'missing'}; "
        f"page errors: {len(measured[name]['errors'])}</li>"
        for name, label in ROBOTS if name in measured)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>League table landed</title>
<style>
:root {{ --ink:#22211f; --mut:#6f6e69; --line:#dddcd6; --bg:#f4f4f2; --card:#fcfcfb; --ok:#2a7a3c; --warn:#a4372a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --ink:#ecebe6; --mut:#a3a29c; --line:#3a3936; --bg:#1b1b1a; --card:#232321; --ok:#6cc07f; --warn:#ff8a7a; }} }}
:root[data-theme="dark"] {{ --ink:#ecebe6; --mut:#a3a29c; --line:#3a3936; --bg:#1b1b1a; --card:#232321; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:1200px; margin:0 auto; padding:24px 16px 60px; }}
h1 {{ font-size:22px; margin:0 0 6px; }} h2 {{ font-size:17px; margin:34px 0 8px; }}
.verdict {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 16px; }}
figure {{ margin:12px 0; }} figure img, video {{ width:100%; border:1px solid var(--line); border-radius:8px; display:block; }}
figcaption {{ color:var(--mut); font-size:13px; margin-top:4px; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }} @media (max-width:800px) {{ .pair {{ grid-template-columns:1fr; }} }}
table.h {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; display:block; overflow-x:auto; }}
table.h th, table.h td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:right; white-space:nowrap; }}
table.h th:first-child {{ text-align:left; }} table.h td span {{ color:var(--mut); font-size:11.5px; }}
td.ok {{ color:var(--ok); font-weight:600; }} td.warn {{ color:var(--warn); font-weight:600; }}
code {{ font-size:12.5px; }} .mut {{ color:var(--mut); }} ul {{ padding-left:20px; }} li {{ margin:4px 0; }}
details {{ margin:8px 0; }}
</style></head><body><main>
<h1>League table landed: the outer dataset view is tabs, and opens on a ranking of configs</h1>
<p class="verdict"><b>Every bench site now opens on a one-screen league of pipeline configs</b> (rank, value at full speed, ×best, n targets,
a sparkline per KPI over speed, dataset · split chips), with Speed sweeps, Targets and Runs as tabs. A row drills to that config's worst
targets, then a target, then a run. UR5e landing: <b>206,472 px → {measured.get('ur5e', {}).get('tabs', {}).get('overview', 0):,} px</b>
(229 → {screens(measured.get('ur5e', {}).get('tabs', {}).get('overview', 0))} screens), the whole league above the fold.
<span class="mut">traj_compare <code>3ce7e7c</code> on main (tests red first <code>ddeb47f</code>, <code>c5c0725</code>); arm_motion_bench
<code>9d09a24</code> · <code>e5a0fdc</code> · <code>4257829</code> · <code>a1b0fd5</code> on main; the three bench sites rebuilt with it.</span></p>

<h2>Hero: Overview → a config → its worst target → a run (real UR5e site, served)</h2>
<video autoplay muted loop playsinline controls poster="{jpeg(MEDIA / 'ur5e-overview.png', 960)}"><source src="{raw(MEDIA / 'hero.mp4', 'video/mp4')}" type="video/mp4"></video>
<details><summary class="mut">GIF fallback</summary><img src="{raw(MEDIA / 'hero.gif', 'image/gif')}" alt="hero clip as a GIF" style="width:100%"></details>
<p class="mut">Recorded headless at 1440 × 900 from <code>scripts/dashboard.py serve --robot ur5e</code> (orange rings mark each click):
facet chip workspace-v2 · dev, back to all, click the rank-1 row (ctc_tuned_v2), its worst target, that config's line ↗, the run report.</p>

<h2>Before / after at 1440 × 900 (UR5e)</h2>
<div class="pair">{shot('before-ur5e', 'Before (today): the speed-sweep landing; 18,767 px with the scorecard below it, 223,821 px on the cards view')}
{shot('ur5e-overview', 'After: Overview, the league above the fold')}</div>

<h2>Height of every tab, measured (document scrollHeight, 1440 × 900, file://)</h2>
{table}
<p class="mut">Green = within 3.5 screens (3,150 px), the acceptance bound for “every tab ≤ ~3 screens”. file:// pages carry the
“serve this folder” banner (≈ 60 px); served pages are that much shorter. Before = the same page as built before this change
(UR5e already opened on the speed sweep today; BAM FB and pendulum still opened on all target cards).</p>

<h2>Every robot's Overview</h2>
<ul>{verdicts}</ul>
<div class="pair">{shot('bam_fb-overview', 'BAM five-bar: Overview')}{shot('pendulum-overview', 'Pendulum: Overview (sim and real ranked apart)')}</div>
<div class="pair">{shot('before-bam_fb', 'BAM five-bar before: the scorecard tiles, then every target card on one page (220,946 px)')}{shot('before-pendulum', 'Pendulum before: the scorecard, then every target card (133,721 px)')}</div>

<h2>The other tabs (UR5e)</h2>
<div class="pair">{shot('ur5e-sweeps', 'Speed sweeps: the sweep chart and table; energy / jerk / stop-error charts and the folded scorecard below')}
{shot('ur5e-drill', 'Targets, drilled: ctc_tuned_v2’s worst targets at full speed, each with Target ↗ and run ↗')}</div>
<div class="pair">{shot('ur5e-targets', 'Targets · cards, 12 a page')}{shot('ur5e-runs', 'Runs: today’s runs table, unchanged')}</div>

<h2>Drill path, by clicking (measure.cjs)</h2>
<ul>{drills}</ul>

<h2>What I decided for you (each reversible)</h2>
<ul>
<li><b>KPIs are run tags, generic</b>: <code>Sweep(metrics=(Metric(...),))</code>, <code>{{series}}</code> in a tag splits sim / real, tuple
<code>facet_by</code>. The bench's scorecard (summary.charts) is not parsed. Undo: <code>git revert 3ce7e7c</code>.</li>
<li><b>Energy and tool jerk became bench run tags</b> (they existed only as per-split medians, so nothing behind them could be drilled).
Stop error (max) is the third extra KPI; <b>gates pass-rate is not a column</b> (no per-run tag; see Left). Undo: <code>git -C /home/bam/arm_motion_bench revert e5a0fdc</code>.</li>
<li><b>Chips are dataset · split</b> (12 on UR5e), not dataset alone; holdout stays visible as its own chip.</li>
<li><b>The domain scorecard is folded</b> (<code>details</code>, closed) at the foot of Speed sweeps, drawn on first open; nothing removed.</li>
<li><b>Targets are paged</b>: 12 cards, 54 table rows a page, with Show more. The landing is always the Overview (<code>#/</code>); every tab and
the drill are hash links, so back / forward and bookmarks work.</li>
<li><b>Existing tests edited only where they assumed the one-page landing</b> (cards via the Targets tab, runs via the Runs tab, the sweep via
Speed sweeps, back from a target lands on <code>#/targets</code>, the lazy-cards scene clicks Show more): commits <code>ddeb47f</code>,
<code>c5c0725</code>. The bench's parity fixture was regenerated by its documented procedure (only index.html's digest moved): <code>4257829</code>.</li>
<li><b>Every bench site writes the coverage page</b> (<code>coverage=True</code>, arm_motion_bench <code>a1b0fd5</code>), at the
coverage session's request: its “Coverage ↗” link sits at the end of the tab bar (traj_compare <code>a5de694</code>, which also carries my
log-axis exponent fix for the Speed sweeps metric charts).</li>
<li>The bench test pinning <code>_sweep_for</code> (y = real wins) stays green: <code>_league_for</code> wraps it.</li>
</ul>

<h2>Left</h2>
<ul>
<li><b>Gates pass-rate column</b>: needs a per-run “passed every gate” tag in the bench (the scorecard's gate_pass_rate_all is a per-split aggregate). Next, not blocked.</li>
<li><b>Real lines on BAM FB carry no real_tcp_rms_mm tag</b>, so its league ranks sim only; the pendulum's real and rehearsal series rank.</li>
<li><b>The league ranks only configs with a value at the fastest speed</b>: BAM FB shows 4 (hold_friction_v2, hold_friction, jtc_baseline,
record); its fullarm_jtc variants have no tool-RMS tag at 1.0 and stay in the band below and the Targets tab. Next: an “every config” toggle
ranking each at its own fastest speed.</li>
<li><b>BAM FB's Targets · table is 3,396 px (3.8 screens)</b>, over the 3.5 bound by one target group; a page of 54 rows holds its 5-config
targets. Next: page by targets, not rows.</li>
<li>The Target level (unchanged) is still ~4 screens on a 5-config target; out of this scope.</li>
<li><b>Known flake</b>: <code>tests/test_playback.py::test_play_from_a_fresh_page_never_freezes_and_stays_on_the_cursor</code> fails under
full-suite load and passes alone; it failed before today (on <code>d897365</code>) and only exercises the run view's video playback.</li>
</ul>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT}: {OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
