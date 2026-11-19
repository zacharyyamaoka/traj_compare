"""Run-view layout round (Round B, 2026-11-19): build five runnable layouts + the babble gallery from the shared fixture.

    .venv/bin/python run/build.py            # data, pages, gallery  -> OUT
    .venv/bin/python run/build.py --shots    # also hero + state screenshots (shoot.sh + Playwright, one browser at a time)

SIMULATED fixture (../fixture/fixture.json, see ../fixture.py). Everything shown on the pages comes from it; the
builder only re-grids each run onto its target's time grid and computes the per-run torque budget the CONTRACT names
(FB share = Σ|fb| / (Σ|ff| + Σ|fb|), drive gap = RMS(commanded − applied), target − commanded with the target
interpolated onto the run's own samples). Repeat-band statistics are computed in the page, over the runs you select.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent  # TCD/run
TCD = HERE.parent
TRAJ_COMPARE = TCD.parents[1]
ASSETS = TRAJ_COMPARE / "src" / "traj_compare" / "assets"
# WHY: a production lane edits traj_compare's assets while this round runs; copy the frozen HEAD snapshot when present
HEAD_ASSETS = Path("/tmp/claude-1000/traj_compare_head_273ad59/core/mdp/agent/actor/trajectory_generation/traj_compare/src/traj_compare/assets")
FIXTURE = TCD / "fixture" / "fixture.json"
OUT = Path("/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19/run")
GALLERY = Path("/home/bam/.claude-personal/skills/babble/scripts/gallery.py")
VARIANTS = ("v1", "v2", "v3", "v4", "v5")
L1_M, L2_M = 0.30, 0.25
RAD2DEG = 180.0 / math.pi


def _group(run: dict) -> str:
    return "sim" if run["kind"] == "sim" else "ff " + run["tags"]["ff_model"].split()[0]


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def _tip(q: np.ndarray) -> np.ndarray:
    """(2, N) joint angles (rad) -> (2, N) L2-tip xy (m); links rotate about z by q1 and q1 + q2."""

    return np.array([L1_M * np.cos(q[0]) + L2_M * np.cos(q[0] + q[1]), L1_M * np.sin(q[0]) + L2_M * np.sin(q[0] + q[1])])


def _r(values, decimals: int) -> list:
    return np.round(np.asarray(values, dtype=float), decimals).tolist()


def prepare(data: dict) -> dict:
    """The page payload: per target its grid, target q (deg) / τ, and its runs re-gridded with metrics."""

    max_torque = np.array(data["max_torque_nm"])
    targets = []
    for target in data["targets"]:
        grid = np.asarray(target["t"])
        target_q = np.asarray(target["q"])  # (2, N) rad
        target_tau = np.asarray(target["tau"])
        runs = []
        for run in (r for r in data["runs"] if r["target"] == target["name"]):
            t = np.asarray(run["t"])
            q = np.asarray(run["q"])
            series = {key: np.asarray(run[key]) for key in ("tau_cmd", "tau_ff", "tau_fb", "tau")}
            # error = target − run, the target interpolated onto the run's own samples (never extrapolated: the run
            # starts within a few ms of the target, np.interp holds the end value there)
            target_on_run = np.array([np.interp(t, grid, target_q[j]) for j in range(2)])
            error = target_on_run - q
            tip_error_mm = np.linalg.norm(_tip(target_on_run) - _tip(q), axis=0) * 1000.0
            tau_target_on_run = np.array([np.interp(t, grid, target_tau[j]) for j in range(2)])
            regrid = lambda values: np.array([np.interp(grid, t, values[j]) for j in range(len(values))])  # noqa: E731
            metrics = []
            for j in range(2):
                ff, fb, cmd, applied = (series[k][j] for k in ("tau_ff", "tau_fb", "tau_cmd", "tau"))
                abs_error = np.abs(error[j])
                worst = int(np.argmax(abs_error))
                metrics.append({
                    "errRms": round(_rms(error[j]) * RAD2DEG, 4), "errMax": round(float(abs_error[worst]) * RAD2DEG, 4),
                    "errMaxT": round(float(t[worst]), 3),
                    "fbShare": round(float(np.abs(fb).sum() / (np.abs(ff).sum() + np.abs(fb).sum())), 4),
                    "cmdRms": round(_rms(cmd), 4), "ffRms": round(_rms(ff), 4), "fbRms": round(_rms(fb), 4),
                    "appliedRms": round(_rms(applied), 4), "cmdPeak": round(float(np.abs(cmd).max()), 4),
                    "tgtMinusCmdRms": round(_rms(tau_target_on_run[j] - cmd), 4),
                    "driveGapRms": round(_rms(cmd - applied), 4),
                    "satFrac": round(float(np.mean(np.abs(cmd) >= 0.999 * max_torque[j])), 4),
                })  # fmt: skip
            worst_tip = int(np.argmax(tip_error_mm))
            runs.append({
                "name": run["name"], "id": run["name"].split("/")[1], "title": run["title"], "kind": run["kind"],
                "group": _group(run), "tags": run["tags"],
                "err": _r(regrid(error) * RAD2DEG, 4),
                "cmd": _r(regrid(series["tau_cmd"]), 4), "ff": _r(regrid(series["tau_ff"]), 4),
                "fb": _r(regrid(series["tau_fb"]), 4), "applied": _r(regrid(series["tau"]), 4),
                "tipErr": _r(np.interp(grid, t, tip_error_mm), 3),
                "m": metrics,
                "tip": {"rms": round(_rms(tip_error_mm), 3), "max": round(float(tip_error_mm[worst_tip]), 3),
                        "maxT": round(float(t[worst_tip]), 3)},
            })  # fmt: skip
        targets.append({
            "name": target["name"], "title": target["title"], "description": target["description"],
            "t": _r(grid, 4), "q": _r(target_q * RAD2DEG, 4), "tau": _r(target_tau, 4), "runs": runs,
        })  # fmt: skip
    return {
        "simulated": True, "robot": data["robot"], "joints": data["joints"], "maxTorque": data["max_torque_nm"],
        "links": [L1_M, L2_M], "targets": targets,
    }  # fmt: skip


def write_pages(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fixture.js").write_text(
        "/* SIMULATED fixture (traj_compare layout round 2026-11-19), re-gridded by run/build.py */\n"
        "window.FIXTURE = " + json.dumps(payload, separators=(",", ":")) + ";\n"
    )
    vendor = OUT / "vendor"
    vendor.mkdir(exist_ok=True)
    assets = HEAD_ASSETS if HEAD_ASSETS.is_dir() else ASSETS
    for name in ("uplot.iife.min.js", "uplot.min.css", "three.min.js"):
        shutil.copy2(assets / name, vendor / name)
    shutil.copy2(assets / "style.css", vendor / "tc-style.css")  # traj_compare's own visual language, read-only
    shutil.copytree(HERE / "common", OUT / "common", dirs_exist_ok=True)
    for variant in VARIANTS:
        if (HERE / variant).is_dir():
            shutil.copytree(HERE / variant, OUT / variant, dirs_exist_ok=True)


def build_gallery() -> None:
    """gallery.py build, which refuses an unscored spec. This round leaves scores/defaultId/hinge to the dispatcher
    (scored after all five exist), so on that refusal the deck shell is rendered through gallery.py's own
    render_gallery — same shell, same embedded spec — and `check --strict` reports what is still unscored."""

    sys.path.insert(0, str(HERE))
    import spec_source  # the spec's prose + shot table (writes run/gallery-spec.json, proof from run/proof.json)

    spec_source.main()
    spec = HERE / "gallery-spec.json"
    shutil.copy2(spec, OUT / "gallery-spec.json")
    index = OUT / "index.html"
    index.unlink(missing_ok=True)  # gallery.py refuses to overwrite
    result = subprocess.run([sys.executable, str(GALLERY), "build", "--spec", str(OUT / "gallery-spec.json"),
                             "--output", str(index)], capture_output=True, text=True)  # fmt: skip
    if result.returncode != 0:
        refusals = [line for line in result.stderr.splitlines() if line.startswith("ERROR")]
        unscored = [line for line in refusals if "score" in line or "default" in line.lower() or "decisionHinge" in line
                    or "hard-gate result" in line]  # fmt: skip
        if len(unscored) != len(refusals):
            print("\n".join(sorted(set(refusals) - set(unscored))))
            raise SystemExit("gallery spec has errors besides the unscored fields")
        import importlib.util

        module_spec = importlib.util.spec_from_file_location("babble_gallery", GALLERY)
        gallery = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(gallery)
        index.write_text(gallery.render_gallery(json.loads(spec.read_text()), "deck"), encoding="utf-8")
        print(f"Built gallery (unscored, {len(unscored)} fields left to the dispatcher): {index}")
    else:
        print(result.stdout.strip())
    check = subprocess.run([sys.executable, str(GALLERY), "check", "--input", str(index), "--strict"], capture_output=True, text=True)
    lines = (check.stdout + check.stderr).strip().splitlines()
    other = [line for line in lines if not any(k in line for k in ("score", "defaultId", "defaultWhy", "decisionHinge", "hard-gate result"))]
    print(f"check --strict: {len(lines)} lines, {len(lines) - len(other)} about scoring/default/hinge/gates; other:")
    print("\n".join(other) or "  (none)")


def shoot() -> None:
    """Hero (shoot.sh) + interaction states (Playwright), each behind the shared one-browser lock."""

    shots = OUT / "shots"
    shots.mkdir(exist_ok=True)
    for variant in VARIANTS:
        if (OUT / variant / "index.html").exists():
            subprocess.run([str(TCD / "shoot.sh"), str(OUT / variant / "index.html"), str(shots / f"{variant}-hero.png"),
                            "1440", "900"], check=True)  # fmt: skip
    command = ["flock", "/tmp/claude-1000/traj-layout-browser.lock", "taskset", "-c", "2-5,16,17", "nice", "-n", "19",
               "uv", "run", "--no-project", "--with", "playwright==1.64.1", "python", str(HERE / "shots.py"), str(OUT)]  # fmt: skip
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", action="store_true", help="also take the hero and state screenshots")
    arguments = parser.parse_args()
    payload = prepare(json.loads(FIXTURE.read_text()))
    write_pages(payload)
    print(f"{OUT / 'fixture.js'}  {(OUT / 'fixture.js').stat().st_size / 1e6:.2f} MB")
    if arguments.shots:
        shoot()
    build_gallery()


if __name__ == "__main__":
    main()
