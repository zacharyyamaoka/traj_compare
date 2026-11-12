"""The review page for the two shipped Rerun layouts ("questions", "evo").

    python3 build_named_report.py --root <report dir>

<root> holds the ur-sim-real example (ur5e-conveyor/), manifest.json + shots/ (shoot.py) and
media/<layout>-hero.mp4 (shoot.py --film). Every picture is the real Rerun 0.40.0 web viewer.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

UVX = "uvx --from rerun-sdk==0.40.0 rerun"
BLURB = {
    "questions": ("Questions", "The 3D robot over the camera overlay stays pinned on the left; the tabs on the right are the questions you ask, in order."),
    "evo": ("evo", "evo's own Rerun layout (Visualization + Raw data) plus one full-screen tab per analysis; the path draws itself, coloured by the worst run's error."),
}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rerun Layouts</title>
<style>
:root{--bg:#fbfbf8;--ink:#1b1b19;--mute:#6b6a64;--line:#e3e2dc;--card:#fff;--accent:#2a78d6;--code:#f2f1ec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--ink:#ecebe6;--mute:#a3a29b;--line:#33322f;--card:#1f1f1d;--accent:#6aa6ee;--code:#262624}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:28px;margin:0 0 6px}h2{font-size:20px;margin:36px 0 10px}h3{margin:0 0 4px;font-size:17px}
.verdict{font-size:16px;margin:0 0 18px}.mute{color:var(--mute)}
.heroes{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;min-width:0}
video,img{width:100%;height:auto;display:block;border-radius:6px;border:1px solid var(--line)}
code,pre{background:var(--code);border-radius:6px;font:12.5px/1.5 ui-monospace,Menlo,monospace}
code{padding:1px 5px}pre{padding:10px 12px;overflow-x:auto;white-space:pre-wrap;word-break:break-all;margin:8px 0}
.tabs{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0}
.tabs button{border:1px solid var(--line);background:transparent;color:var(--mute);border-radius:6px;padding:4px 10px;font:inherit;font-size:13px;cursor:pointer}
.tabs button[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.shot{display:none}.shot.on{display:block}
ul{padding-left:20px}li{margin:4px 0}
</style></head><body><main>
<h1>Rerun layouts: questions and evo</h1>
<p class="verdict"><b>Both layouts ship, named, in traj_compare.</b> <code>questions</code> is the default. Pick per call, or set your preference once. Every <code>.rrd</code> embeds your layout and has the other one beside it. The report's Rerun bar has a <b>Layout</b> menu.</p>
<div class="heroes">__HEROES__</div>
<h2>Every tab, in the real viewer</h2>
<p class="mute">UR5e conveyor: target, sim and 5 stand-in "real" runs, with real #1's camera overlay. Playhead at 2.0 s. Click a tab.</p>
__TABS__
<h2>Choose your layout</h2>
<div class="card">
<p>Per call:</p><pre>write_comparison_report(comparisons, out, rerun=True, rerun_layout="evo")</pre>
<p>Once, for every call that doesn't name one (the env var beats the file):</p><pre>export TRAJ_COMPARE_RERUN_LAYOUT=evo</pre>
<pre># ~/.config/traj_compare/config.toml
rerun_layout = "evo"</pre>
<p>In the report, the Rerun bar's <b>Layout</b> menu switches both the command and what <b>Open in Rerun</b> launches:</p>
<img src="media/report-layout-picker.jpg" alt="The report's Rerun bar with the Layout menu set to evo">
</div>
<h2>What changed</h2>
<ul>
<li><b>Named layouts:</b> <code>rerun_export.LAYOUTS</code> holds <code>questions</code> and <code>evo</code>. <code>default_layout()</code> reads <code>$TRAJ_COMPARE_RERUN_LAYOUT</code>, then <code>~/.config/traj_compare/config.toml</code>, then falls back to <code>questions</code>. <code>layout_blueprint(..., tab=)</code> opens a layout on a named tab. Tabs with nothing to show are dropped.</li>
<li><b>Units:</b> the <code>.rrd</code> shows joints in degrees (°, °/s) and the tool in mm. Milliradians are gone. The report payload, Parquet and MCAP stay SI.</li>
<li><b>New entities both layouts read:</b>
  <ul>
  <li>shaded tolerance bands (Rerun <code>Measurements</code>);</li>
  <li>worst joint error at each instant;</li>
  <li>tool x/y/z;</li>
  <li>the reference path coloured by the worst run's tool error, static and drawn up to the playhead;</li>
  <li>a worst-first scorecard;</li>
  <li>tolerance and settling events;</li>
  <li>RMS bars per run.</li>
  </ul></li>
<li><b>Camera overlay:</b> a <code>CameraOverlay</code> is baked with ffmpeg into one MP4 and played by Rerun's stock video view. <code>key_color</code> keys a render's flat background out first. The UR5e example now has one: real #1's camera with the sim and target layered on top.</li>
<li><b>Server:</b> <code>serve.py</code> accepts <code>&amp;layout=</code>, so <b>Open in Rerun</b> launches the chosen layout.</li>
</ul>
<h2>Open it yourself</h2>
__COMMANDS__
</main>
<script>
document.querySelectorAll('[data-tabs]').forEach(function (box) {
  var buttons = box.querySelectorAll('.tabs button'), shots = box.querySelectorAll('.shot');
  buttons.forEach(function (button, index) {
    button.onclick = function () {
      buttons.forEach(function (b, i) { b.setAttribute('aria-selected', i === index); });
      shots.forEach(function (s, i) { s.classList.toggle('on', i === index); });
    };
  });
});
</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    heroes, tabs, commands = [], [], []
    for name, entry in manifest.items():
        title, blurb = BLURB[name]
        clip = f"media/{name}-hero.mp4"
        if not (root / clip).is_file():
            raise SystemExit(f"missing {clip}: run shoot.py --film {name}:0")
        heroes.append(
            f'<div class="card"><h3>{html.escape(title)} <span class="mute">· <code>{name}</code></span></h3>'
            f'<p class="mute">{html.escape(blurb)}</p>'
            f'<video src="{clip}" poster="media/{name}-hero-poster.png" autoplay muted loop playsinline controls>'
            f'<img src="media/{name}-hero.gif" alt="{html.escape(title)} playing"></video></div>'
        )
        buttons, shots = [], []
        for index, tab in enumerate(entry["tabs"]):
            shot = f"shots/{name}--{index}.png"
            if not (root / shot).is_file():
                raise SystemExit(f"missing {shot}")
            buttons.append(f'<button aria-selected="{str(index == 0).lower()}">{html.escape(tab["tab"])}</button>')
            shots.append(f'<img class="shot{" on" if index == 0 else ""}" src="{shot}" alt="{html.escape(title)}: {html.escape(tab["tab"])} tab" loading="lazy">')
        tabs.append(f'<div class="card" data-tabs><h3>{html.escape(title)}</h3><div class="tabs">{"".join(buttons)}</div>{"".join(shots)}</div><br>')
        rrd = root / entry["rrd"]
        rbl = rrd.with_name(f"{rrd.stem}.{name}.rbl")
        commands.append(f'<p><b>{html.escape(title)}:</b></p><pre>{html.escape(UVX)} {html.escape(str(rrd))} {html.escape(str(rbl))}</pre>')
    page = PAGE.replace("__HEROES__", "".join(heroes)).replace("__TABS__", "".join(tabs)).replace("__COMMANDS__", "".join(commands))
    out = root / "index.html"
    out.write_text(page, "utf-8")
    print(out)


if __name__ == "__main__":
    main()
