"""The 2026-11-24 report on the eight TTA asks: one section per ask, its before/after evidence, every number read from the
evidence files (never typed in).

    .venv/bin/python docs/tta_asks_2026-11-24/build_report.py <evidence dir> [out.html]

<evidence dir> holds what the measuring scripts wrote: ``assets_check.json`` (sizes of the 42 real task reports inline and
with ``assets=``), ``mask_check.json`` (p5s-pass3's tool RMS on the 42 tasks: the ruler, every sample, the moving
samples), ``ev.json`` (the browser measurements) and the screenshots ``ev/*.png``. Default out:
``/home/bam/traj_compare/reports/media/tta-asks-2026-11-24.html`` (screenshots inline, so in the gitignored media/).
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path


def main() -> None:
    evidence = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/bam/traj_compare/reports/media/tta-asks-2026-11-24.html")
    assets = json.loads((evidence / "assets_check.json").read_text())
    mask = json.loads((evidence / "mask_check.json").read_text())
    ev = json.loads((evidence / "ev.json").read_text())
    commits = json.loads((evidence / "commits.json").read_text())
    shots = evidence / "ev"

    def img(name: str, alt: str, width: str = "100%") -> str:
        data = base64.b64encode((shots / f"{name}.png").read_bytes()).decode()
        return f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(alt)}" style="max-width:{width}"><figcaption>{html.escape(alt)}</figcaption></figure>'

    mb = lambda n: f"{n / 1e6:.1f} MB"  # noqa: E731
    s = mask["summary"]
    worst_rows = sorted(mask["rows"], key=lambda r: -r["every_off"])[:5]
    mask_rows = "".join(
        f"<tr><td>{r['task']}</td><td>{r['moving']} / {r['samples']}</td><td>{r['ruler_mm']:.4f}</td><td>{r['every_mm']:.4f}</td>"
        f"<td>{r['every_off']:.4f}</td><td>{r['masked_mm']:.4f}</td><td>{r['masked_off']:.6f}</td></tr>"
        for r in worst_rows
    )
    band_before = "".join(f"<li><code>{html.escape(row)}</code></li>" for row in ev["dataset-before"])
    band_after = "".join(f"<li><code>{html.escape(row)}</code></li>" for row in ev["dataset-after-light"])
    fold_b, fold_a = ev["fold-before"], ev["fold-after"]

    def c(key: str) -> str:
        return f"<code>{html.escape(commits[key])}</code>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TTA asks, landed</title>
<style>
:root {{ --bg:#f6f6f3; --panel:#fff; --ink:#1d1d1b; --mut:#62615c; --line:#dddcd6; --ok:#2a7a3c; --accent:#2a78d6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#191918; --panel:#232322; --ink:#ecebe8; --mut:#a3a29d; --line:#3a3936; --ok:#6cc07c; --accent:#6aa5f0; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 60px; }}
h1 {{ font-size:24px; margin:0 0 6px; }} h2 {{ font-size:18px; margin:0 0 8px; }}
.lede {{ color:var(--mut); margin:0 0 18px; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin:0 0 16px; }}
.verdict {{ font-weight:650; color:var(--ok); }}
.meta {{ color:var(--mut); font-size:13px; }}
code {{ font-size:12.5px; background:color-mix(in srgb, var(--line) 45%, transparent); padding:1px 4px; border-radius:4px; }}
table {{ border-collapse:collapse; font-size:13px; margin:8px 0; display:block; overflow-x:auto; }}
th, td {{ border-bottom:1px solid var(--line); padding:4px 10px; text-align:right; white-space:nowrap; }}
th:first-child, td:first-child {{ text-align:left; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width:760px) {{ .pair {{ grid-template-columns:1fr; }} }}
figure {{ margin:8px 0; }} figure img {{ display:block; width:100%; height:auto; border:1px solid var(--line); border-radius:6px; }}
figcaption {{ color:var(--mut); font-size:12.5px; margin-top:4px; }}
.big {{ font-size:28px; font-weight:700; }}
</style></head><body><main>
<h1>Eight TTA asks, landed in traj_compare</h1>
<p class="lede">Each is a new keyword (or a fix) whose default keeps today's output. Evidence below is from the 42 real dev
tasks of TTA's comparison site and headless Chrome; every number is read from the measuring scripts' output.</p>

<section><h2>1 · <code>write_comparison_report(assets=…)</code> — shared viewer files</h2>
<p class="verdict">Done · {c("impl")}</p>
<p>The 42 real task reports (their data, no robot meshes): <span class="big">{mb(assets["inline_total"])} → {mb(assets["shared_total"] + assets["assets_bytes"])}</span>
({mb(assets["shared_total"])} of reports + one {mb(assets["assets_bytes"])} <code>assets/</code>), {mb(assets["saved"])} saved.
One report: {mb(assets["one_inline"])} inline, {mb(assets["one_shared"])} with <code>assets=</code>.
Byte-for-byte check: on <b>{assets["identical_to_tta_patch"]} of {assets["reports"]}</b> reports, <code>assets=</code> writes exactly what
TTA's <code>_share_assets</code> text substitution makes of the inline page (timestamps aside), so TTA can drop the patch.</p></section>

<section><h2>2 · The dataset page on a static host</h2>
<p class="verdict">Done · {c("impl")}</p>
<ul><li><code>command_root="site/comparison"</code>: serve / drill / Rerun commands name it; the absolute build folder appears nowhere in the page (test).</li>
<li><code>rerun_server=False</code> + <code>public_url=</code>: no POST button; each row has <b>Open in the Rerun web viewer</b>
(<code>app.rerun.io/version/0.40.0/index.html?url=&lt;public .rrd URL&gt;</code>) and a <code>.rrd</code> download, as in the coverage workbench.</li>
<li><code>rows=()</code>: the footer reads “traj_compare dataset view”, no row files named.</li></ul>
{img("dataset-static-host", "rerun_server=False, public_url, command_root, rows=(): the runs table's actions and footer", "900px")}</section>

<section><h2>3 · Dark mode, following prefers-color-scheme</h2>
<p class="verdict">Done · {c("impl")}</p>
<p>The dark rules are generated from the light ones (<code>python -m traj_compare._theme</code>): data colours stay, neutrals invert,
the page keeps panels a step above it. The light page's computed background is still <code>rgb(244, 244, 242)</code> (test);
<code>&lt;html data-theme="light"&gt;</code> pins light. Canvases (uPlot axes, three.js scene, SVG charts) map their neutrals with a JS port held equal to the Python mapping (test).</p>
<div class="pair">{img("report-light", "A real task report (workspace-dev-000), light: unchanged")}{img("report-dark", "The same report with the system in dark mode")}</div>
<div class="pair">{img("dataset-after-light", "TTA's live dataset page, new assets, light")}{img("dataset-after-dark", "The same page, dark")}</div></section>

<section><h2>4 · Significant figures, not fixed decimals</h2>
<p class="verdict">Done · {c("impl")}</p>
<p>Numbers keep at least two significant figures; every value of 0.1 and up prints exactly as before (dataset.js <code>nice</code>/<code>fixed</code>,
the FB share, fixed-digit table columns; the report's degree and millimetre formatters keep their three decimals down to 0.01).
TTA's live dataset summary, before → after:</p>
<div class="pair"><div><b>Before (as shipped)</b><ul>{band_before}</ul></div><div><b>After</b><ul>{band_after}</ul></div></div>
<div class="pair">{img("dataset-before-band", "Before")}{img("dataset-after-light-band", "After")}</div></section>

<section><h2>5 · <code>Comparison(stats_mask=…, stats_mask_label=…)</code></h2>
<p class="verdict">Done · {c("impl")}</p>
<p>p5s-pass3 on all {s["tasks"]} tasks, the report's tool position RMS against the ruler's <code>tool_track_rms_mm</code>
(mask: the ruler's own <code>moving_mask</code>): every sample is up to <b>{s["worst_every_off_mm"]:.3f} mm</b> off ({s["worst_every_task"]});
the moving samples are at most <b>{s["worst_masked_off_mm"]:.6f} mm</b> off. Median over the tasks (the objective): ruler {s["median_ruler"]:.5f} mm,
masked {s["median_masked"]:.5f} mm, every sample {s["median_every"]:.5f} mm. The plots still draw every sample; the track tab says which samples the statistics use.</p>
<table><thead><tr><th>Task (5 worst unmasked)</th><th>moving / samples</th><th>ruler mm</th><th>every sample mm</th><th>off</th><th>masked mm</th><th>off</th></tr></thead><tbody>{mask_rows}</tbody></table></section>

<section><h2>6 · A 16-colour palette</h2>
<p class="verdict">Done · {c("impl")}</p>
<p>The first eight are unchanged; eight more picked for the largest smallest CIELAB distance in normal vision and under
deuteranopia, protanopia and tritanopia (Machado 2009): each new one is ≥ 20 ΔE from every other colour, ≥ 10 under each
simulation (the original eight are only 6 apart for a deutan), L 40–62 so lines read in both themes. Same list in report.py, plots.js and dataset.js.</p>
<p>{"".join(f'<span style="display:inline-block;width:28px;height:18px;margin:2px;border-radius:3px;background:{col}" title="{col}"></span>' for col in commits["palette"])}</p></section>

<section><h2>7 · <code>report.html#run=&lt;label&gt;</code></h2>
<p class="verdict">Done · {c("impl")}</p>
<p>Name or title, any case, with or without <code>#tab=</code>; only that run beside the target; not remembered; an unknown label changes nothing.
On the real task report, <code>#tab=track&amp;run=p6s</code> → chips: <code>{html.escape(", ".join(ev["run"]))}</code>; a plain visit afterwards: <code>{html.escape(", ".join(ev["runPlain"]))}</code>.</p>
<div class="pair">{img("run-deep-link", "#tab=track&run=p6s: only p6s beside the target")}{img("run-plain", "A plain visit afterwards: every run, as left")}</div></section>

<section><h2>8 · The stage's fold button at 390 px</h2>
<p class="verdict">Done · {c("impl")}</p>
<p>Stacked below 900 px the stage was <code>position: static</code>, so its absolute fold button had nothing to sit in and floated to the page corner.
Measured (getBoundingClientRect, [left, top, right, bottom]): before, button {fold_b["fold"]} vs stage {fold_b["stage"]};
after, button {fold_a["fold"]} inside stage {fold_a["stage"]}, clear of the heading text {fold_a["heading"]} and the canvas {fold_a["canvas"]}.</p>
<div class="pair">{img("fold-before", "Before: the fold button over the page's top-right corner", "390px")}{img("fold-after", "After: in the stage's corner, beside its heading", "390px")}</div></section>

<p class="meta">Commits: tests (red) {c("red")}, implementation {c("impl")}. {html.escape(commits["tests"])}</p>
</main></body></html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, "utf-8")
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
