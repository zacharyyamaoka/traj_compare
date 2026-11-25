# Lane brief (shared by R2–R5; the dispatcher wrote it, lanes read it)

You build ONE variant of the playback viewer in /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/rN/.

## Read first (in this order)
1. `CONTRACT.md` (the round: Zach's words, invariants, fixtures, axes table, proof) and `criteria.json` (how it is judged).
2. `common/runview.js` (loader, shared header, `window.__runView` readback) and `check.cjs` (the proof you must pass).
3. `r1/` — the baseline every variant starts from: `diff -u /home/bam/traj_compare/src/traj_compare/assets/plots.js r1/plots.js`
   (keep=, boot(payload), the per-chart playhead + drag-to-scrub gesture, the hover fix) and `r1/viewer3d.js` (`debug()`).
4. `/home/bam/traj_compare/docs/NAVIGATION.md` Part B (the frozen stage + question tabs) and the production viewer
   `/home/bam/traj_compare/src/traj_compare/assets/{plots.js,viewer3d.js,style.css}`.
5. Zach's screenshots of today's view: `/home/bam/zach_brain/Sources/Images/Pasted image 20261124221841.png` and `... 20261124221946.png`.

## Start
`cp -r r1 rN` (then edit rN/index.html: title "Playback viewer · RN <name>", `data-rv-variant="rN"`, its comment). Your
variant OWNS its copies (plots.js, style.css, viewer3d.js, any new rN/*.js|css); unchanged production files keep loading
from `/assets/`. Mark every change `RV:` with a short WHY. Keep the readback hooks in CONTRACT.md working.

## Server and checks
- The round server is ALREADY RUNNING on http://127.0.0.1:8853 (the dispatcher owns it; do not stop or restart it). Only if
  `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8853/r1/index.html` is not 200, start it yourself with Bash
  `run_in_background`: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/serve.py --port 8853`
  and say so in your report.
- Pages: `http://127.0.0.1:8853/rN/index.html?fixture=tta&keep=p5s-pass3,p6s` and
  `http://127.0.0.1:8853/rN/index.html?fixture=bam_fb&keep=3460,3461,3463,3465,3466,3467,3471,3474,3476` (add `&dry=1` so
  Open in Rerun writes the recording without launching a viewer window — ALWAYS use dry in automation).
- Proof: `cd /home/bam/traj_compare/docs/proposals/run-view-2026-11-24 && node check.cjs rN --only tta` while iterating,
  then `node check.cjs rN --video` (both fixtures + the drag films) must print `"ok": true`. Tell the check your gestures in
  `rN/gestures.json` (see r1's; `scrub.modifiers` or `scrub.selector` (+`yFrac`) to scrub on your own element at the
  chart's x pixels; `zoom.kind` = `wheel` (`at`, `ticks`) | `drag` (`modifiers`, optional `selector`, `from`/`to` as
  fractions of the chart's or the selector's box) | `click` (`selector`); `reset` = `{"dblclick":"chart"}` or
  `{"click": selector}`; `toggle` = the run toggle selector with `{name}` (the situation name, e.g. `p6s`, `L3471`);
  `tab` = the tab selector with `{id}`; `"snaps": true` if your drag snaps; `heroSetup`/`filmSetup` = a JS expression
  run in the page before the hero still / film). You may NOT edit check.cjs, common/, serve.py, fixtures.py, criteria.json,
  CONTRACT.md or another lane's folder: if the check cannot express your gesture, implement a second gesture it can, and say so.
- LOOK at every still it writes in `shots/rN/` (Read the PNGs): hero-tta.png, hero-bam_fb.png, sync-*-after-drag.png,
  sync-*-other-tab.png, zoom-*.png, toggle-*.png. Fix what looks wrong. Visual credibility is judged: same visual
  language as traj_compare's style.css, no overlapping text, no clipped controls, nothing broken at 1440 × 900.
- Headless only (check.cjs and any script of yours use playwright from /home/bam/aruco-studio/web/node_modules/playwright,
  launched headless). Never open a visible browser or front a window. Stop every process you start. Memory is shared:
  run one headless browser at a time. (A hook blocks shell commands that name the browser binary; drive it from node.)

## Zach's rules for this surface
Every boundary drags and is remembered (localStorage in try/catch); panels fold; plain-word labels (no jargon, define any
term you coin); angles in degrees; every chart title names signal, joint, sign convention and unit; joints one per row;
never truncate a name silently (ellipsis + the whole name in `title`); never truncate/normalize authored values. Keep a
short `WHY:` comment wherever code preserves one of his stated preferences. Real data only (the two fixtures).

## Deliverables in rN/
- the working variant (index.html + its copies) and `gestures.json`;
- `NOTES.md`: name · one-sentence thesis · 2–4 consequential decisions · best when · loses when · 2–3 keep-parts (for a
  splice) · what is simulated / not built · the change size (`diff -u /home/bam/traj_compare/src/traj_compare/assets/plots.js rN/plots.js | grep -c '^[-+]'`, same for the other copies);
- `media.json`: 1–3 EXTRA stills that show your thesis (beyond what check.cjs captures), each
  `{"file": "shots/rN/extra-<name>.png", "label": "...", "caption": "what to notice"}`, captured headless at 1440 × 900
  by a small script of yours in rN/ (e.g. rN/extra.cjs), from the real page.

## Never
git add/commit/stash/reset/checkout (the dispatcher commits your folder); edit anything outside rN/ and shots/rN/;
touch /home/bam/traj_compare/src; use a Haiku model; run audits / Codex; publish Claude Artifacts.

## Report back (short)
`check.cjs rN --video` result (ok + the sync numbers: committed t, max chart diff, slider, 3D time, on both fixtures),
what you built (one line per decision), the gaps you know of, the files you wrote.
