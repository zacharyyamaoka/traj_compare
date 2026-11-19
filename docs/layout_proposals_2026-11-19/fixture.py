"""The one shared fixture for the 2026-11-19 layout rounds: three targets, many real repeats, a full torque breakdown.

SIMULATED DATA, physically grounded — every layout proposal (standalone summary, standalone run, Rerun run) shows
this same scenario, so no variant wins on easier data. It mirrors what Zach saw on the pendulum rig that day: a
feedforward model that underestimates gravity, so the feedback torque slopes with the arm's angle on the full-circle
probe and the error depends on gravity.

The arm: a vertical planar 2R arm (the L1/L2 chain of examples/tracking_errors_demo.py, gravity along -y), moteus-style
joint control at 1 kHz: commanded = clip(feedforward + kp·e + kd·ė + ki∫e), a current loop that delivers the
command through a 1.5 ms lag with a torque-constant error, and a reply torque with sensor noise. Recorded at 100 Hz.

    target  τ: inverse dynamics of the target with the planning model (= the v1 nominal model)
    tau_ff    : inverse dynamics of the target with the run's feedforward model (v1 nominal or v2 calibrated)
    tau_fb    : kp·e + kd·ė + ki∫e
    tau_cmd   : clip(tau_ff + tau_fb, ±max) — what goes to the FOC current loop (moteus control_torque)
    tau       : applied, measured (moteus reply torque)

Targets (runs are grouped by target — the target is the one thing identical across its runs):

    full-circle-slow  shoulder one full turn from hanging, 6 s;    sim + 14 real (8 × ff v1 on 11-18/19, 6 × ff v2 on 11-19)
    full-circle-fast  the same turn in 2 s;                        sim + 8 real  (4 × v1, 4 × v2)
    pick-swing        out to a pick pose and back, 3 s;            sim + 5 real  (5 × v1)

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19
    ../../.venv/bin/python fixture.py   # writes fixture/fixture.json
    from fixture import comparisons          # traj_compare Comparisons, one per target (torque fields when supported)
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixture" / "fixture.json"

JOINTS = ("shoulder", "elbow")
L1_M, L2_M = 0.30, 0.25  # examples/tracking_errors_demo.py's chain
GRAVITY = 9.81
CONTROL_HZ = 1000.0
RECORD_HZ = 100.0
MAX_TORQUE_NM = np.array([7.0, 3.0])
KT_NM_PER_A = np.array([0.083, 0.083]) * 8.0  # torque constant × gear ratio, so current = tau / this


@dataclass(frozen=True)
class ArmModel:
    """Link masses (kg), rotor inertia reflected to the joint (kg·m²), viscous (N·m·s/rad) and Coulomb (N·m) friction."""

    upper_mass: float
    fore_mass: float
    rotor_inertia: float
    viscous: tuple[float, float]
    coulomb: tuple[float, float]


TRUE_ARM = ArmModel(upper_mass=1.10, fore_mass=0.62, rotor_inertia=0.0045, viscous=(0.045, 0.02), coulomb=(0.11, 0.05))
FF_MODELS = {
    # v1: CAD masses, no friction — underestimates gravity by ~20 %, the slope Zach saw on the full-circle probe
    "v1 nominal": ArmModel(upper_mass=0.88, fore_mass=0.50, rotor_inertia=0.004, viscous=(0.0, 0.0), coulomb=(0.0, 0.0)),
    # v2: weighed links and a fitted friction model — what a feedforward calibration would give
    "v2 calibrated": ArmModel(upper_mass=1.07, fore_mass=0.60, rotor_inertia=0.0044, viscous=(0.04, 0.018), coulomb=(0.09, 0.04)),
}
PLANNING_MODEL = "v1 nominal"
GAINS = {"kp": np.array([38.0, 14.0]), "kd": np.array([1.1, 0.35]), "ki": np.array([12.0, 4.0]), "ilimit": np.array([0.4, 0.15])}


def _quintic(phase: np.ndarray) -> np.ndarray:
    phase = np.clip(phase, 0.0, 1.0)
    return phase**3 * (10.0 - 15.0 * phase + 6.0 * phase**2)


@dataclass(frozen=True)
class Target:
    name: str
    title: str
    duration_s: float
    description: str

    def joints(self, t: np.ndarray) -> np.ndarray:
        """Joint angles (rad) at t: rest, the motion, rest (0.4 s each end)."""

        lead, move = 0.4, self.duration_s - 0.8
        phase = (t - lead) / move
        if self.name.startswith("full-circle"):
            shoulder = -math.pi / 2 + 2.0 * math.pi * _quintic(phase)
            elbow = 0.4 + 0.0 * t
        else:  # pick-swing: out and back
            swing = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.clip(phase, 0.0, 1.0))
            shoulder = -1.2 + 1.5 * swing
            elbow = 0.4 + 1.0 * swing
        return np.column_stack([shoulder, elbow])


TARGETS = (
    Target("full-circle-slow", "Full-circle probe · slow (6 s)", 6.0, "Shoulder one full turn from hanging; elbow held at 23°."),
    Target("full-circle-fast", "Full-circle probe · fast (2 s)", 2.0, "The same turn in 2 s: inertia on top of gravity."),
    Target("pick-swing", "Pick swing (3 s)", 3.0, "Out to a pick pose and back, both joints moving."),
)


def _derivatives(q: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    qd = np.gradient(q, dt, axis=0)
    return qd, np.gradient(qd, dt, axis=0)


def inverse_dynamics(model: ArmModel, q: np.ndarray, qd: np.ndarray, qdd: np.ndarray) -> np.ndarray:
    """τ = M(q)·qdd + C(q, qd)·qd + G(q) + friction, for the vertical 2R arm (thin rods, gravity along -y)."""

    m1, m2 = model.upper_mass, model.fore_mass
    lc1, lc2 = L1_M / 2, L2_M / 2
    inertia1, inertia2 = m1 * L1_M**2 / 12, m2 * L2_M**2 / 12
    q1, q2 = q[..., 0], q[..., 1]
    c2, s2 = np.cos(q2), np.sin(q2)
    m11 = inertia1 + inertia2 + m1 * lc1**2 + m2 * (L1_M**2 + lc2**2 + 2 * L1_M * lc2 * c2) + model.rotor_inertia
    m12 = inertia2 + m2 * (lc2**2 + L1_M * lc2 * c2)
    m22 = inertia2 + m2 * lc2**2 + model.rotor_inertia
    h = m2 * L1_M * lc2 * s2
    coriolis1 = -h * (2 * qd[..., 0] * qd[..., 1] + qd[..., 1] ** 2)
    coriolis2 = h * qd[..., 0] ** 2
    gravity1 = (m1 * lc1 + m2 * L1_M) * GRAVITY * np.cos(q1) + m2 * lc2 * GRAVITY * np.cos(q1 + q2)
    gravity2 = m2 * lc2 * GRAVITY * np.cos(q1 + q2)
    viscous, coulomb = np.array(model.viscous), np.array(model.coulomb)
    friction = viscous * qd + coulomb * np.tanh(qd / 0.02)
    tau = np.stack([m11 * qdd[..., 0] + m12 * qdd[..., 1] + coriolis1 + gravity1,
                    m12 * qdd[..., 0] + m22 * qdd[..., 1] + coriolis2 + gravity2], axis=-1)  # fmt: skip
    return tau + friction


def _forward_dynamics(model: ArmModel, q: np.ndarray, qd: np.ndarray, tau: np.ndarray) -> np.ndarray:
    """qdd from τ: solve M·qdd = τ − (C·qd + G + friction), a 2 × 2 solve."""

    bias = inverse_dynamics(model, q, qd, np.zeros(2))
    m1, m2 = model.upper_mass, model.fore_mass
    lc2 = L2_M / 2
    inertia1, inertia2 = m1 * L1_M**2 / 12, m2 * L2_M**2 / 12
    c2 = math.cos(q[1])
    m11 = inertia1 + inertia2 + m1 * (L1_M / 2) ** 2 + m2 * (L1_M**2 + lc2**2 + 2 * L1_M * lc2 * c2) + model.rotor_inertia
    m12 = inertia2 + m2 * (lc2**2 + L1_M * lc2 * c2)
    m22 = inertia2 + m2 * lc2**2 + model.rotor_inertia
    return np.linalg.solve(np.array([[m11, m12], [m12, m22]]), tau - bias)


@dataclass(frozen=True)
class RunSpec:
    name: str
    title: str
    target: Target
    kind: str  # "sim" | "real"
    ff_model: str
    date: str
    seed: int
    plant: ArmModel
    kt_error: float = 0.0  # applied = (1 + kt_error) × command (a torque-constant error)
    start_offset_s: float = 0.0  # the run's clock vs the target's (latency / trigger jitter)
    noise_nm: float = 0.0


def simulate(spec: RunSpec) -> dict[str, np.ndarray]:
    """Run the moteus-style loop at 1 kHz on ``spec.plant``; return 100 Hz records (SI)."""

    rng = np.random.default_rng(spec.seed)
    dt = 1.0 / CONTROL_HZ
    t = np.arange(0.0, spec.target.duration_s + 1e-9, dt)
    q_target = spec.target.joints(t)
    qd_target, qdd_target = _derivatives(q_target, dt)
    ff_model = FF_MODELS[spec.ff_model]
    tau_ff_all = inverse_dynamics(ff_model, q_target, qd_target, qdd_target)

    q = q_target[0].copy() + rng.normal(0.0, 0.002, 2) * (spec.kind == "real")
    qd = np.zeros(2)
    integral = np.zeros(2)
    applied = tau_ff_all[0].copy()
    lag = dt / 0.0015  # current-loop first-order lag, 1.5 ms
    rows = {key: np.zeros((t.size, 2)) for key in ("q", "qd", "qdd", "tau_cmd", "tau_ff", "tau_fb", "tau")}
    for index in range(t.size):
        error, rate_error = q_target[index] - q, qd_target[index] - qd
        integral = np.clip(integral + GAINS["ki"] * error * dt, -GAINS["ilimit"], GAINS["ilimit"])
        tau_fb = GAINS["kp"] * error + GAINS["kd"] * rate_error + integral
        tau_ff = tau_ff_all[index]
        tau_cmd = np.clip(tau_ff + tau_fb, -MAX_TORQUE_NM, MAX_TORQUE_NM)
        applied = applied + lag * ((1.0 + spec.kt_error) * tau_cmd - applied)
        cogging = 0.03 * np.sin(24.0 * q) * (spec.kind == "real")
        qdd = _forward_dynamics(spec.plant, q, qd, applied + cogging)
        for key, value in (("q", q), ("qd", qd), ("qdd", qdd), ("tau_cmd", tau_cmd), ("tau_ff", tau_ff), ("tau_fb", tau_fb)):
            rows[key][index] = value
        rows["tau"][index] = applied + rng.normal(0.0, spec.noise_nm, 2)
        qd = qd + qdd * dt
        q = q + qd * dt
    step = int(round(CONTROL_HZ / RECORD_HZ))
    out = {key: value[::step] for key, value in rows.items()}
    out["t"] = t[::step] + spec.start_offset_s
    out["current"] = out["tau"] / KT_NM_PER_A
    return out


def target_record(target: Target) -> dict[str, np.ndarray]:
    dt = 1.0 / CONTROL_HZ
    t = np.arange(0.0, target.duration_s + 1e-9, dt)
    q = target.joints(t)
    qd, qdd = _derivatives(q, dt)
    tau = inverse_dynamics(FF_MODELS[PLANNING_MODEL], q, qd, qdd)
    step = int(round(CONTROL_HZ / RECORD_HZ))
    return {"t": t[::step], "q": q[::step], "qd": qd[::step], "qdd": qdd[::step], "tau": tau[::step]}


def run_specs() -> list[RunSpec]:
    """Every run, in a fixed order; seeds make the fixture byte-for-byte reproducible."""

    plan = {"full-circle-slow": [("v1 nominal", "2026-11-18", 4), ("v1 nominal", "2026-11-19", 4), ("v2 calibrated", "2026-11-19", 6)],
            "full-circle-fast": [("v1 nominal", "2026-11-19", 4), ("v2 calibrated", "2026-11-19", 4)],
            "pick-swing": [("v1 nominal", "2026-11-19", 5)]}  # fmt: skip
    specs: list[RunSpec] = []
    seed = 1119
    for target in TARGETS:
        specs.append(RunSpec(name=f"{target.name}/sim", title="Sim (ideal plant)", target=target, kind="sim",
                             ff_model=PLANNING_MODEL, date="2026-11-19", seed=seed, plant=FF_MODELS[PLANNING_MODEL]))  # fmt: skip
        repeat = 0
        for ff_model, date, count in plan[target.name]:
            for _ in range(count):
                seed += 1
                rng = np.random.default_rng(seed)
                scale = rng.normal(1.0, 0.08)
                plant = replace(TRUE_ARM, viscous=tuple(np.array(TRUE_ARM.viscous) * scale),
                                coulomb=tuple(np.array(TRUE_ARM.coulomb) * rng.normal(1.0, 0.1)),
                                fore_mass=TRUE_ARM.fore_mass * rng.normal(1.0, 0.01))  # fmt: skip
                repeat += 1
                specs.append(RunSpec(
                    name=f"{target.name}/real-{repeat:02d}", title=f"Real #{repeat:02d} · ff {ff_model.split()[0]}", target=target,
                    kind="real", ff_model=ff_model, date=date, seed=seed, plant=plant, kt_error=float(rng.normal(-0.03, 0.015)),
                    start_offset_s=float(rng.normal(0.0, 0.004)), noise_nm=0.02,
                ))  # fmt: skip
    return specs


def _round(values: np.ndarray, decimals: int) -> list:
    return np.round(np.asarray(values, dtype=float), decimals).T.tolist()  # one list per joint


def build() -> dict:
    """The fixture as one JSON-ready dict: targets, runs (with tags), and the units."""

    targets = []
    for target in TARGETS:
        record = target_record(target)
        targets.append({"name": target.name, "title": target.title, "description": target.description,
                        "t": np.round(record["t"], 4).tolist(),
                        **{key: _round(record[key], 5 if key.startswith("q") else 4) for key in ("q", "qd", "qdd", "tau")}})  # fmt: skip
    runs = []
    for spec in run_specs():
        record = simulate(spec)
        runs.append({
            "name": spec.name, "title": spec.title, "target": spec.target.name, "kind": spec.kind,
            "tags": {"ff_model": spec.ff_model, "date": spec.date, "kind": spec.kind, "kt_error": round(spec.kt_error, 4),
                     "start_offset_ms": round(spec.start_offset_s * 1000.0, 2)},
            "t": np.round(record["t"], 4).tolist(),
            **{key: _round(record[key], 5 if key.startswith("q") else 4)
               for key in ("q", "qd", "qdd", "tau_cmd", "tau_ff", "tau_fb", "tau", "current")},
        })  # fmt: skip
    return {
        "schema": "traj-compare-layout-fixture/1",
        "simulated": True,
        "robot": "vertical planar 2R arm (L1 0.30 m, L2 0.25 m), moteus-style joint control",
        "joints": list(JOINTS),
        "units": {"t": "s", "q": "rad", "qd": "rad/s", "qdd": "rad/s^2", "tau*": "N·m", "current": "A"},
        "torque_names": {"tau": "applied (measured)", "tau_cmd": "commanded (to the FOC current loop)",
                         "tau_ff": "feedforward", "tau_fb": "feedback", "target.tau": "target"},  # fmt: skip
        "max_torque_nm": MAX_TORQUE_NM.tolist(),
        "targets": targets,
        "runs": runs,
    }


def _examples():
    sys.path.insert(0, str(HERE.parents[1] / "examples"))
    from dataset_demo import planar_robot  # noqa: E402
    from tracking_errors_demo import l2_tip_fk  # noqa: E402

    return planar_robot, l2_tip_fk


def comparisons(data: dict | None = None, *, runs_per_target: int | None = None) -> list:
    """One traj_compare ``Comparison`` per target: the target, its sim, its real repeats (torque breakdown when the
    installed ``Situation`` has the fields), the planar robot model and the L2-tip fk. Repeats form one repeat group."""

    from traj_compare import Comparison, Situation

    planar_robot, l2_tip_fk = _examples()
    data = data or json.loads(OUT.read_text())
    breakdown = "tau_cmd" in Situation.__dataclass_fields__
    robot = planar_robot()
    out = []
    for target in data["targets"]:
        array = lambda record, key: np.asarray(record[key], dtype=float).T  # noqa: E731
        target_situation = Situation(name="target", title="Target", t=np.asarray(target["t"]), q=array(target, "q"),
                                     qd=array(target, "qd"), qdd=array(target, "qdd"), tau=array(target, "tau"))  # fmt: skip
        members = [run for run in data["runs"] if run["target"] == target["name"]]
        if runs_per_target is not None:
            members = members[: runs_per_target + 1]
        situations = []
        for run in members:
            extra = {key: array(run, key) for key in ("tau_cmd", "tau_ff", "tau_fb")} if breakdown else {}
            situations.append(Situation(
                name=run["name"].split("/")[1], title=run["title"], t=np.asarray(run["t"]), q=array(run, "q"),
                qd=array(run, "qd"), qdd=array(run, "qdd"), tau=array(run, "tau"), current=array(run, "current"),
                meta=dict(run["tags"]), group=run["kind"], group_title="Sim" if run["kind"] == "sim" else "Real", **extra,
            ))  # fmt: skip
        reals = [situation.name for situation in situations if situation.group == "real"]
        out.append(Comparison(
            title=target["title"], name=target["name"], joint_names=data["joints"], target=target_situation,
            situations=situations, fk=l2_tip_fk, tcp_frame="L2 tip", robot=robot, description=target["description"],
            repeat_groups={f"Real ×{len(reals)}": reals} if len(reals) >= 2 else {},
            default_sections=None,
        ))  # fmt: skip
    return out


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fixture = build()
    OUT.write_text(json.dumps(fixture, separators=(",", ":")))
    print(f"{OUT}  {OUT.stat().st_size / 1e6:.2f} MB  {len(fixture['targets'])} targets  {len(fixture['runs'])} runs")
