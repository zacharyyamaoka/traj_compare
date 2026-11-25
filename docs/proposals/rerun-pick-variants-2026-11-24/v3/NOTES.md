# V3 · Limit-lit

**Thesis.** Every link of the arm is lit by its joint's worst % of limit at the playhead: the largest of |q| (to its
position limit), |qd| / vmax and |qdd| / amax. Green is below 80 %, amber is 80-95 % and red is 95 % or more. The right
half opens on a "% of limit" tab, and the recording opens AT the moment closest to a limit, not at 0 s.

```bash
/home/bam/traj_compare/.venv/bin/rerun /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v3/run-dev-029.rrd
```

Built by `v3/make.py`: `save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None)` returns
`{"path", "closest_s", "closest", "opening", "legend_hits"}`, and `main()` writes both scenarios. The application id is
`rerun_pick_v3`. The blueprint is embedded at `save(..., default_blueprint=...)` and the recording opens paused. The
pieces come from robot_msgs.viz.rerun by import (`_RobotPlan`, `_series`, `_percent`, `_forward_kinematics`,
`_geometry_kinds`, `band`, the stock strips, cards, table and TCP); robot_msgs is not edited (built on its
main 3023fce, the strip-range fix). `v3/opens_at.cjs` is V3's own check of where a file opens. It uses film.cjs's
loader but never moves the playhead.

## What is on screen (run-dev-029, p6s)

- **Left, the 3D view:**
  - The collision-mesh UR5e. Each link's colour is its joint's state at the playhead (the base stays steel).
  - A fixed legend under the arm, "worst % of limit" over one row per joint (e.g. `wrist_2 145 % qdd`), each in its
    link's colour, base at the bottom as on the arm. It sits where neither the arm nor the tool path ever goes.
  - The tool path is neutral slate: travelled solid, still to go pale. `start` and `end` sit beside their ends, off
    the arm, each with a thin leader to its dot.
  - No ghosts. Colour means limits and nothing else, so the stock's orange trail and blue/orange ghosts are gone.
- **Right, the tabs:**
  - **% of limit** (open on load):
    - Its title is the moment: `◆ closest to limit: wrist_2 145 % qdd at 0.40 s · measured (encoder q differenced;
      smoothed 132-141 %)`.
    - A lane per joint, `/joint (shoulder_pan)` … `/joint (wrist_3)` in joint order (Rerun's state timeline), shows
      the colour its link had at every instant, labelled with the quantity that set it (`q` / `qd` / `qdd`).
    - A two-line key: what the lanes are, the strips' colours (q blue, qd teal, qdd grey), the shading, and which
      target line shows (`pale line = qdd target (q, qd: under the run)`).
    - One strip per joint shows q, qd and qdd as % of its own limits over a slate ±100 % band, the amber 80-95 % zone
      and the red ≥ 95 % zone (out to the strip's edge, so past the limit too), with 80 %, 95 % and 100 % lines.
      The target's three lines are drawn pale underneath; only its qdd shows.
    - A ◆ marks the moment on its joint's strip. Each strip's title gives `peak 145 % qdd · 48 % red`, where the last
      number is the share of the run that joint spends at 95 % or more.
  - **q · qd · qdd · qddd:** the stock strips per joint in degrees, with the same amber 80-95 % and red ≥ 95 % zones of
    each joint's limit shaded on both sides. A strip whose target sits under the run says so and by how much
    (`target under the run (≤ 0.62°)`); where it shows (qdd, qddd) the title says `pale = target`.
  - **q / qd / qdd:** the stock playhead table and cards, with the target pale under each card (`pale = qdd target`).
  - **TCP:** position, orientation, speed and angular speed, titles shortened so they fit; each says the target is
    under the run and by how much, and the legend lists it as `x target (under)`. Cartesian limits are not in the
    message, so there are no zones here.

## Decisions

1. **The tint is the albedo of each link's mesh, logged on `t` only where it changes.** Latest-at holds each colour in
   between. V3 writes its own copy of `_urdf_copy` (`_lit_copy`) without the stock's static tint, because Rerun lets
   static data win over temporal data of the same component. Each link takes the colour of the joint that moves it
   (child link of the joint). The thresholds are 80 % and 95 % because a time-optimal plan rides its acceleration
   limit at about 99 %, so "red" means "at the limit", not "near it".
2. **The file opens at the moment closest to a limit.** The moment is the instant whose worst joint is worst; on a tie,
   the first. On the run it is 0.40 s, wrist_2 at 145 % of its qdd limit. That is the solution's **measured**
   acceleration: qdd is the difference of differences of the encoder q (`make.py` checks this against
   `np.gradient`). Smoothing q with a Savitzky-Golay filter (order 2 or 3) before differencing still gives 141 %
   (70 ms window), 137 % (90 ms) and 132 % (110 ms), against 145 % raw. So it is a real overshoot of the gen-0
   controller, not only quantisation noise. The data is kept as given; the title says what it is. On the plan the
   moment is 0.90 s (wrist_2 at 99 % qd, the planner's own qd).
   - Rerun 0.40 has no time-cursor field in the blueprint, so `_write_opening_at` writes the file in an order that
     makes the viewer start there:
     1. the on-screen rows (the 3D view, the "% of limit" tab) at or after the moment, earliest first;
     2. the static data (meshes);
     3. the on-screen rows before the moment, the arm's joints first;
     4. the other tabs' rows, after the moment, then before it.
   - The data is identical; only the order in the file changed.
   - Measured with `opens_at.cjs` in the real 0.40 web viewer on this order: the run opened at 0.400 s on 7 of 7
     loads (2 on the final build) and the plan at 0.900 s on 3 of 3 (the checked build: 9 of 9).
   - The moment is also stored as a recording property (`limit_lit.closest_s`), for any host that can move the cursor
     itself.
3. **The numbers sit in a fixed legend, not on the links and not on leaders.** UR joint origins coincide or sit
   centimetres apart, so labels on the links overprinted or vanished (the first cut). A callout column with leaders
   (the second cut) was fixed beside the motion, and when the arm swung to the far side its leaders crossed the whole
   view and the tool path. Now `_Layout` projects the opening camera (55° vertical field of view, the 800 × 908 px 3D
   view of a 1600 × 1000 page) over 900 surface points per link mesh at 120 instants, plus the tool path. It puts the
   legend in the box nearest the bottom and the middle that stays 14 px clear of all of it (0 cells covered, on both
   scenarios). `start` / `end` go beside their ends, clear of the arm where it stands at that end, with a leader.
4. **Zones are shaded, and red runs to the strip's edge.** Red means "≥ 95 %" on the arm, past the limit too, so the
   red zone is 95 % to the edge of the strip, not a 95-100 % sliver (1-2 px in a qd strip). Rerun fills a Measurements
   band at 0.2 × its colour's alpha (measured), so each zone is drawn twice over itself (36 %). The ±100 % band of the
   "% of limit" strips is one slate layer (20 %) so the lines on it stay crisp.
5. **The lanes are one entity, one string component per joint.** Rerun labels a state lane with its entity path and
   sorts lanes by it. A visualizer mapping (`StateChange:state` ← the joint's component) labels the lane
   `/joint (shoulder_pan)` and keeps the blueprint's order, so the lanes read as joint names in joint order.
6. **A target line is promised only where it can be seen.** Where the target is within 2 % of a strip's height of the
   run (about 2 px, under the run's own line), the title says `target under the run (≤ gap)` with the measured gap.
   On this run that is q (≤ 0.62°), qd (≤ 6.0°/s), every TCP strip (≤ 3.0 mm per axis, ≤ 3.5°, ≤ 25 mm/s, ≤ 3.7°/s)
   and the q / qd lines of every "% of limit" strip and card. qdd (5-14 % of its strip) and qddd show.
7. **Draw order is controlled by path names.** Rerun 0.40 draws a plot's series in entity-path order, with the last on
   top, regardless of blueprint or log order (measured). So the zones are `_band` and the target `_target`, both drawn
   under the run.
8. **Fewer entities.** Each zone set and each set of lines is one entity per strip with one instance per band or line.
   Every entity is about three chunks once the file is split at the moment, and at 772 chunks the headless 0.40 viewer
   had not ingested the file 14 s after opening (an unopened tab's zones were missing, the hero's t = 0 frame drew the
   base alone). Now 487 chunks on the run, 367 on the plan.
9. **Filmed with `--wait 30000`.** The machine ran at a load average of 50-95 during this round, and V3 opens at the
   moment by writing the rows before it late. In one of the default 12 s waits film.cjs read the timeline as
   0.4 → 3.2 s and filmed 29 frames from 0.4 s, so every still here waited 30 s. To re-film V3, pass `--wait 30000`
   (same frame names).

## Best when / loses when

- **Best when** the question is "is anything saturating, where on the arm, and when?" That covers a candidate plan
  before it goes to hardware, a speed sweep, or a retime. The arm answers *where*, the lanes answer *when*, and the file
  opens on the worst moment.
- **Loses when** the trajectory is time-optimal. The plan is red most of the time (wrist_3 66 % of the run, wrist_2
  64 %), so the colour stops discriminating; that is true, but it is not news.
- **Noisy on measured runs.** qd and qdd there come from differences of encoder positions, so qdd noise flickers links
  between amber and red. The worst moment (145 %) holds up when smoothed (132-141 %), so it is a real overshoot, but
  the smaller flickers are not all real.
- **Not for tracking error.** The target is a pale line, mostly hidden under the run here, and how far the run is off
  it is V2's question.

## Worth keeping in a splice

- **The live link tint** (`_lit_copy` + `_tint`): any variant can light its arm by a per-joint scalar (limit, error,
  temperature).
- **Open at a moment** (`_write_opening_at(scratch, path, blueprint, at_s, properties)`): V4 could open at its
  worst-error event, V2 at its worst tool error.
- **Named lanes** (`_lanes_view` + one AnyValues component per joint): any state lane labelled by joint, in joint
  order.
- **`_Layout`**: the opening camera as a pinhole plus the arm's footprint over the run, to put 3D labels where the arm
  never goes.
- **Visible zones** (`_bands`, `_zones`) and **"target under the run (≤ gap)"** (`_Notes`): useful in any variant
  with limit bands or a target overlay.

## The signature it would add to robot_msgs (additive)

```python
viz.rerun.save(path, traj, *, robot, tool=None, ghosts=True,
               tint: Literal["none", "limits"] = "none",            # "limits": V3's live link colour + "% of limit" tab first
               open_at: float | Literal["start", "closest_to_limit"] = "start",
               target: JointTrajectory | None = None)              # pale under every plot, or "under the run (≤ gap)"
viz.rerun.limit_usage(traj, robot=urdf) -> LimitUsage              # pct (q/qd/qdd, N×J), worst, which, closest_s
```

`robot_blueprint(...)` would take the same `tint=`. Defaults keep today's behaviour.

## What Rerun 0.40 could not do

- **Open a file at a chosen time on its own.**
  - There is no blueprint field for the time cursor.
  - A `#when=t@…` URL fragment is ignored on a plain .rrd URL. Five tries: `t@0.4s` on the data URL and on the page
    URL, then `t@+0.400s`, `t@400000000` and `t@0.4` on the data URL. All opened at 0 s. The fragment is documented
    for server (`rerun+http`) dataset URLs.
  - One row at the moment sent first, followed at once by rows from 0 s, still opened at 0 s.
  - What works is the file order above. It relies on observed, undocumented viewer behaviour. A viewer that took in the
    whole file in one frame would open at 0 s; the ◆ and the titles still name the moment then.
  - **Not tried in the native viewer**: this lane may not open a native window. The host-side route exists:
    `rerun.experimental.ViewerClient.set_time(...)`, or the web viewer's `set_time_for_timeline`.
- **Name a state lane freely.** A lane's label is its entity path, or `<entity path> (<component>)` for a mapped
  component, and plain lanes sort by path. `/joint (shoulder_pan)` is as close to a bare joint name as it gets.
- **Pin a legend to the screen in 3D.** There is no 2D overlay on a 3D view; the legend is 3D labels placed for the
  opening camera. Orbit the camera and it moves with the scene (still off the arm at the opening view).
- **Shade a band at its colour.** A Measurements band fills at 0.2 × its colour's alpha, so zones are drawn twice over
  themselves.
- **Ingest fast in a headless browser.** The software-rendered web viewer takes in a few chunks per frame; chunk count,
  not bytes, set how long the file took to load (decision 8).
- **Tint a link through the stock copy.** A static albedo shadows any temporal one, so V3 carries its own copy of
  `_urdf_copy` without the static tint.
- **Dashed lines.** The target is pale and thin, not dashed.
- **Load the .dae visuals.** The arm uses the collision meshes.

## Sizes

- `v3/plan-dev-029.rrd`: 2 051 128 B (2003 KB)
- `v3/run-dev-029.rrd`: 2 635 131 B (2573 KB)

(The checked build: 2537 KB and 3116 KB; the merged zone and line entities, decision 8, took the difference.)

## Stills (shots/v3/)

- `opens-run.png`: **the run as it opens, untouched** (opens_at.cjs). The playhead is at 0.400 s. wrist_2's link is
  red (`wrist_2 145 % qdd` in the legend), the shoulder is amber (82 % q), the ◆ is on wrist_2's strip at 145 %, and the
  title says the number is measured (encoder q differenced; smoothed 132-141 %).
- `opens-plan.png`: the plan as it opens: 0.900 s, wrist_2 99 % qd, ◆ on wrist_2's strip.
- `hero/f-0-t0.png … f-32-t3.2.png`: the hero, the run from 0 → 3.2 s every 0.1 s on the "% of limit" tab. The links
  change colour as the arm moves and the playhead walks the lanes; the legend stays put under the arm. Good single
  frames:
  - `f-0-t0.png`: the arm at the start, `start` beside its end, off the arm;
  - `f-4-t0.4.png`: the moment (wrist_2 145 % qdd);
  - `f-12-t1.2.png`: the wrists red, the rest green and amber;
  - `f-24-t2.4.png`: the arm swung to the left edge: shoulder_pan 110 % and shoulder_lift 97 % qdd, so the shoulder and
    upper arm are red while the forearm (elbow 31 %) is green; the legend and `end` stay clear of it;
  - `f-32-t3.2.png`: the end, all green; `end` sits below-left of the wrist with its leader.
- `tab-limit-0-t1.8.png`: "% of limit" at 1.8 s: the named lanes, the key, six strips with the slate ±100 % band and
  the amber / red zones, ◆ at 0.40 s.
- `tab-q-0-t1.8.png`: q in degrees. shoulder_pan and wrist_3 come near their ±360° limits, so their strips show the
  amber zone and the red zone out to the edge; every title says `target under the run (≤ …°)`.
- `tab-qd-0-t1.8.png`: qd in °/s, the zones at ±vmax in every strip that reaches them; wrist_1, 2 and 3 ride the red
  zone; the target is under the run (≤ 0.96-6.0°/s).
- `tab-qdd-0-t1.8.png`: qdd in °/s², the zones at ±amax; the run's noisy qdd crosses them; `pale = target`, and it
  shows.
- `tab-qddd-0-t1.8.png`: qddd (slope of qdd), with the target pale. There is no jerk limit in the message, so there are
  no zones.
- `tab-q-qd-qdd-0-t1.8.png`: the stock playhead table plus cards, `pale = qdd target` on each card.
- `tab-tcp-0-t1.8.png`: TCP position, orientation, speed and angular speed, each title whole and saying the target is
  under the run (≤ 3.0 mm, ≤ 3.5°, ≤ 25 mm/s, ≤ 3.7°/s); the legend reads `x target (under)`.
- `plan-0-t1.8.png`: the dataset plan at 1.8 s. It is mostly red (a time-optimal plan rides its limits), the ◆ sits
  at 0.90 s, and the title and key have no target or measured note (the plan has neither).

## Fixed after the check (2026-11-24)

1. **The .rrd files were older than make.py.** Both rebuilt from the final make.py on robot_msgs main 3023fce, and
   every still above re-filmed from them. → any still, e.g. `tab-qd-0-t1.8.png`.
2. **The 95-100 % zone read as a line; the ±100 % band was a barely visible grey.** Red now runs from 95 % to the
   strip's edge, amber is 80-95 %, both drawn twice over themselves (36 %); the "% of limit" strips have a slate ±100 %
   band (20 %) with the zones and 80 / 95 / 100 % lines on it. → `tab-qd-0-t1.8.png`, `tab-q-0-t1.8.png`,
   `tab-limit-0-t1.8.png`.
3. **The lanes read `/tint/1_shoulder_pan`.** One entity, a string component per joint, a lane each by visualizer
   mapping: `/joint (shoulder_pan)` … `/joint (wrist_3)`, in joint order. → `tab-limit-0-t1.8.png`.
4. **The TCP orientation title was cut.** The TCP titles drop the tool's source (the 3D view shows it), and every
   title was cut to fit and checked in the frames: the opening title is 102 characters, Rerun cut at ~108.
   → `tab-tcp-0-t1.8.png`, `tab-limit-0-t1.8.png`.
5. **The callout leaders crossed the view and the tool path late in the run; `end` sat on the arm.** The callouts are
   now a fixed legend under the arm, placed where the arm's meshes and the tool path never go over the whole run (no
   leaders), and `start` / `end` sit beside their ends off the arm with a short leader. → `hero/f-24-t2.4.png`,
   `hero/f-32-t3.2.png`, `hero/f-0-t0.png`.
6. **"target" was promised where it is hidden.** Each title says `target under the run (≤ gap)` where the target is
   within 2 % of the strip's height, the TCP legend says `x target (under)`, the cards and the key name only the qdd
   target. → `tab-q-0-t1.8.png`, `tab-qd-0-t1.8.png`, `tab-tcp-0-t1.8.png`, `tab-q-qd-qdd-0-t1.8.png`.
7. **wrist_2's 145 % qdd at 0.40 s was not called measured.** The opening title says `measured (encoder q
   differenced; smoothed 132-141 %)` and decision 2 gives the Savitzky-Golay numbers (141 / 137 / 132 % at 70 / 90 /
   110 ms; the check quoted 133-141 %, and 110 ms gives 132.4 % here). The data is not smoothed. → `opens-run.png`,
   `tab-limit-0-t1.8.png`.

Note: make.py imports robot_msgs' private helpers. robot_msgs main moved during the round (now 3023fce, the contract
names 248f9f1) and still builds, but a refactor of those helpers would break this file.
