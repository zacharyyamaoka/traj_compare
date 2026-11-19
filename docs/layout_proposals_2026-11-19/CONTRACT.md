# Torque breakdown contract (frozen 2026-11-19)

Zach, daily note 2026-11-19: *"target torque, the commanded torque (what you send to the FOC controller) and the
actual torque (what was applied at that instant) ... of the command torque some portion of that is coming from
Feedforward, and some portion of that is coming from feedback. That right now is not being made clear to me."*

Every lane (the production change and the three layout rounds) builds against this file. Do not change it
inside a lane; a change is a barrier the dispatcher lands first.

## The five torques (SI, N·m, one column per joint, on the situation's own time grid)

| Name | `Situation` field | What it is | moteus / sim source |
| --- | --- | --- | --- |
| target | `target.tau` | the torque the reference needs (inverse dynamics of the target with the planning model) | planner / `tau_pred` |
| commanded | `tau_cmd` | what the controller asks the motor driver's current (FOC) loop for at that instant | reply `control_torque`; sim: controller output |
| feedforward | `tau_ff` | the model-based part of the command, sent by the host | cmd `feedforward_torque` |
| feedback | `tau_fb` | the error-correcting part of the command (PID: kp·e + kd·ė + ki∫e) | `control_torque − feedforward_torque` |
| applied | `tau` | the torque actually delivered at that instant | reply `torque` (q-axis current × kt); sim: plant input after the drive |

- `tau` keeps its old meaning, so every existing report is unchanged: applied on a run, target on the target.
- **Two of three derive the third:** `tau_cmd = tau_ff + tau_fb`. The derived one is listed in the payload's
  `entry["derived"]` (as `qd` already is), so the page can say "derived". All three given: kept as given (a drive
  clamp can make the sum differ; the page must not hide it).
- Only one of the three, or none: nothing is derived, nothing is invented; the breakdown shows what exists.

## Payload (`analysis.analyze_comparison`)

- `entry["plot"]["tau_cmd" | "tau_ff" | "tau_fb"]`: one list per joint on `plot_t` (nulls outside the run), or `None`.
- `payload["has_torque_breakdown"]`: true when any situation has `tau_cmd`, `tau_ff` or `tau_fb`.
- `entry["torque_budget"]`: `None`, or `{joint_name: {...}}` for a measured run with a breakdown:
  - `cmd_rms`, `ff_rms`, `fb_rms`, `applied_rms`, `cmd_peak` — `robot_msgs.compare.error_stats` of the series
    (rms / max_abs), on the run's own samples; `None` when that series is absent.
  - `fb_share` — Σ|fb| / (Σ|ff| + Σ|fb|) over the run's samples: the fraction of the command the feedback had to
    supply (0 = the feedforward did all of it). `None` without both ff and fb.
  - `target_minus_cmd_rms` — RMS of target τ − commanded, the target interpolated onto the run's samples exactly as
    `robot_msgs.compare` lines it up (time offset honoured, never extrapolated). `None` without both.
  - `cmd_minus_applied_rms` — RMS of commanded − applied (the drive gap: saturation, current-loop lag, kt error).
- The automatic statistics table is unchanged; the breakdown section carries its own "Torque budget" table.
- Exports: `tau_cmd`, `tau_ff`, `tau_fb` are joint channels in Parquet/MCAP like `tau`.

## HTML run view (`assets/plots.js`)

- New section id `joint-torque`, label **Torque breakdown**, on by default when `has_torque_breakdown`
  (`Comparison.default_sections` may still override).
- Opens with the **Torque budget** table: one row per measured run × joint — FB share, commanded RMS, FF RMS,
  FB RMS, target − commanded RMS, commanded − applied RMS, peak |commanded|.
- Then one plot card per joint × data-bearing run that has a breakdown, titled `<joint> — <run title>`, with five
  traces: target (dashed), commanded (run colour, thickest), feedforward, feedback (filled to zero, lightly),
  applied (thin). Component colours are fixed across the page and keyed by one component legend whose chips
  toggle that component on every card. Situation chips still hide a run's cards.
- `_SECTION_IDS` gains `joint-torque`.

## Rerun (`rerun_export`)

Entities (N·m):

```text
/torque/<joint>/target
/torque/<joint>/<run>/commanded
/torque/<joint>/<run>/feedforward
/torque/<joint>/<run>/feedback
/torque/<joint>/<run>/applied
/stats/fb_share/<joint>            bar chart, one bar per run, percent
```

- `<joint>` and `<run>` go through `_part()` like every other path.
- Component colours: commanded = run colour; feedforward `#3b82f6`; feedback `#f97316`; applied = run colour, thin;
  target grey `#8a8983`.
- Both named layouts get a torque tab when the payload has a breakdown: `questions` → **Feedforward or feedback?**,
  `evo` → **Torque**. Each shows, per joint, one run's full breakdown (the worst run on the scorecard), every run's
  feedback, and the FB-share bars. No breakdown → no tab (tabs with nothing to show are dropped, as today).
