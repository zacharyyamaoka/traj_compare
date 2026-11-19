"""The torque breakdown is first class: target, commanded, feedforward, feedback, applied (written before the code, 2026-11-19).

Zach, daily note 2026-11-19: "target torque, the commanded torque (what you send to the FOC controller) and the
actual torque (what was applied at that instant) ... of the command torque some portion of that is coming from
Feedforward, and some portion of that is coming from feedback. That right now is not being made clear to me."

Contract: docs/layout_proposals_2026-11-19/CONTRACT.md. ``tau`` keeps its meaning (applied on a run, target on the
target); ``tau_cmd`` / ``tau_ff`` / ``tau_fb`` are new, and two of the three derive the third.

These tests are the acceptance ruler for the implementing lane: it must not edit this file.
"""

from __future__ import annotations

import numpy as np
import pytest

from traj_compare import Comparison, Situation, write_comparison_report
from traj_compare.analysis import analyze_comparison

T = np.linspace(0.0, 2.0, 401)
JOINTS = ["shoulder", "elbow"]


def _target(t: np.ndarray = T) -> Situation:
    q = np.column_stack([0.5 * np.sin(np.pi * t), 0.2 * t])
    tau = np.column_stack([2.0 * np.sin(np.pi * t) + 0.2, 0.3 * np.ones_like(t)])
    return Situation(name="target", title="Target", t=t, q=q, tau=tau)


def _parts(t: np.ndarray = T):
    ff = np.column_stack([2.0 * np.sin(np.pi * t), 0.25 * np.ones_like(t)])
    fb = np.column_stack([0.5 * np.cos(3.0 * t), 0.05 * np.sin(5.0 * t)])
    return ff, fb


def _comparison(*runs: Situation, target: Situation | None = None) -> Comparison:
    return Comparison(title="Full circle probe", joint_names=JOINTS, target=target or _target(), situations=list(runs))


def _run(name: str = "real_1", t: np.ndarray = T, **torques) -> Situation:
    q = np.column_stack([0.5 * np.sin(np.pi * t) - 0.01, 0.2 * t + 0.002])
    return Situation(name=name, title=name.replace("_", " ").title(), t=t, q=q, **torques)


def _entry(payload: dict, name: str) -> dict:
    return next(entry for entry in payload["situations"] if entry["name"] == name)


def _column(entry: dict, key: str, joint: int) -> np.ndarray:
    return np.array([np.nan if value is None else value for value in entry["plot"][key][joint]], dtype=float)


# ── model ──────────────────────────────────────────────────────────────────


def test_situation_carries_the_three_command_torques_on_its_own_grid():
    ff, fb = _parts()
    run = _run(tau_cmd=ff + fb, tau_ff=ff, tau_fb=fb)
    assert run.tau_cmd.shape == run.tau_ff.shape == run.tau_fb.shape == run.q.shape
    one_joint = Situation(name="pendulum", t=T, q=np.sin(T), tau_ff=np.cos(T))
    assert one_joint.tau_ff.shape == (T.size, 1)  # 1-D promotes to one column, like tau


def test_situation_rejects_a_torque_of_the_wrong_shape_or_without_a_time_base():
    ff, _ = _parts()
    with pytest.raises(ValueError):
        _run(tau_ff=ff[:-1])
    with pytest.raises(ValueError):
        Situation(name="orphan", tau_cmd=ff)


def test_the_new_section_id_is_known():
    ff, fb = _parts()
    comparison = Comparison(title="x", joint_names=JOINTS, target=_target(), situations=[_run(tau_ff=ff, tau_fb=fb)],
                            default_sections=["joint-q", "joint-torque"])  # fmt: skip
    assert "joint-torque" in comparison.default_sections


# ── payload ────────────────────────────────────────────────────────────────


def test_feedforward_plus_feedback_derives_the_command_and_says_so():
    ff, fb = _parts()
    payload = analyze_comparison(_comparison(_run(tau_ff=ff, tau_fb=fb, tau=0.9 * (ff + fb))))
    entry = _entry(payload, "real_1")
    assert payload["has_torque_breakdown"] is True
    assert "tau_cmd" in entry["derived"]
    np.testing.assert_allclose(_column(entry, "tau_cmd", 0), ff[:, 0] + fb[:, 0], atol=1e-4)
    np.testing.assert_allclose(_column(entry, "tau_ff", 1), ff[:, 1], atol=1e-4)


def test_command_minus_feedforward_derives_the_feedback():
    ff, fb = _parts()
    entry = _entry(analyze_comparison(_comparison(_run(tau_cmd=ff + fb, tau_ff=ff))), "real_1")
    assert "tau_fb" in entry["derived"] and "tau_cmd" not in entry["derived"]
    np.testing.assert_allclose(_column(entry, "tau_fb", 0), fb[:, 0], atol=1e-4)


def test_command_minus_feedback_derives_the_feedforward():
    ff, fb = _parts()
    entry = _entry(analyze_comparison(_comparison(_run(tau_cmd=ff + fb, tau_fb=fb))), "real_1")
    assert "tau_ff" in entry["derived"]
    np.testing.assert_allclose(_column(entry, "tau_ff", 1), ff[:, 1], atol=1e-4)


def test_all_three_given_are_kept_as_given_even_when_a_clamp_breaks_the_sum():
    ff, fb = _parts()
    clamped = np.clip(ff + fb, -1.5, 1.5)  # a drive clamp: commanded != ff + fb
    entry = _entry(analyze_comparison(_comparison(_run(tau_cmd=clamped, tau_ff=ff, tau_fb=fb))), "real_1")
    assert not {"tau_cmd", "tau_ff", "tau_fb"} & set(entry["derived"])
    np.testing.assert_allclose(_column(entry, "tau_cmd", 0), clamped[:, 0], atol=1e-4)


def test_one_of_three_derives_nothing_and_invents_nothing():
    ff, _ = _parts()
    entry = _entry(analyze_comparison(_comparison(_run(tau_ff=ff))), "real_1")
    assert entry["plot"]["tau_cmd"] is None and entry["plot"]["tau_fb"] is None
    assert entry["plot"]["tau_ff"] is not None


def test_no_breakdown_anywhere_keeps_the_old_payload():
    payload = analyze_comparison(_comparison(_run(tau=np.ones((T.size, 2)))))
    assert payload["has_torque_breakdown"] is False
    entry = _entry(payload, "real_1")
    assert entry["plot"]["tau_cmd"] is None and entry["torque_budget"] is None


def test_torque_budget_numbers():
    ff, fb = _parts()
    cmd = ff + fb
    applied = 0.9 * cmd
    target = _target()
    entry = _entry(analyze_comparison(_comparison(_run(tau_ff=ff, tau_fb=fb, tau=applied), target=target)), "real_1")
    budget = entry["torque_budget"]
    assert set(budget) == set(JOINTS)
    for joint, name in enumerate(JOINTS):
        row = budget[name]
        rms = lambda values: float(np.sqrt(np.mean(values**2)))  # noqa: E731
        assert row["cmd_rms"] == pytest.approx(rms(cmd[:, joint]), rel=1e-3)
        assert row["ff_rms"] == pytest.approx(rms(ff[:, joint]), rel=1e-3)
        assert row["fb_rms"] == pytest.approx(rms(fb[:, joint]), rel=1e-3)
        assert row["applied_rms"] == pytest.approx(rms(applied[:, joint]), rel=1e-3)
        assert row["cmd_peak"] == pytest.approx(float(np.max(np.abs(cmd[:, joint]))), rel=1e-3)
        share = np.sum(np.abs(fb[:, joint])) / (np.sum(np.abs(ff[:, joint])) + np.sum(np.abs(fb[:, joint])))
        assert row["fb_share"] == pytest.approx(float(share), rel=1e-3)
        assert row["target_minus_cmd_rms"] == pytest.approx(rms(target.tau[:, joint] - cmd[:, joint]), rel=1e-3)
        assert row["cmd_minus_applied_rms"] == pytest.approx(rms(cmd[:, joint] - applied[:, joint]), rel=1e-3)
    assert _entry(analyze_comparison(_comparison(_run(tau_ff=ff, tau_fb=fb))), "target")["torque_budget"] is None


def test_target_minus_command_never_extrapolates_the_target():
    """A run that outlasts the target is scored only where the target exists (robot_msgs.compare's rule)."""

    long_t = np.linspace(0.0, 2.5, 501)
    ff = np.column_stack([np.ones_like(long_t), np.ones_like(long_t)])
    fb = np.zeros_like(ff)
    target = _target()
    budget = _entry(analyze_comparison(_comparison(_run(t=long_t, tau_ff=ff, tau_fb=fb), target=target)),
                    "real_1")["torque_budget"]  # fmt: skip
    inside = long_t <= T[-1] + 1e-12
    expected = np.sqrt(np.mean((np.interp(long_t[inside], T, target.tau[:, 0]) - 1.0) ** 2))
    assert budget["shoulder"]["target_minus_cmd_rms"] == pytest.approx(float(expected), rel=2e-3)


def test_a_target_without_torque_leaves_target_minus_command_empty():
    ff, fb = _parts()
    bare = Situation(name="target", title="Target", t=T, q=_target().q)
    budget = _entry(analyze_comparison(_comparison(_run(tau_ff=ff, tau_fb=fb), target=bare)), "real_1")["torque_budget"]
    assert budget["shoulder"]["target_minus_cmd_rms"] is None
    assert budget["shoulder"]["fb_share"] is not None


# ── the page ───────────────────────────────────────────────────────────────


def test_report_ships_the_torque_breakdown_section(tmp_path):
    ff, fb = _parts()
    html = write_comparison_report([_comparison(_run(tau_ff=ff, tau_fb=fb, tau=0.9 * (ff + fb)))], tmp_path).read_text()
    for needle in ("joint-torque", "Torque breakdown", "Torque budget", "Feedforward", "Feedback", "Commanded", "Applied"):
        assert needle in html, needle


def test_parquet_carries_the_breakdown_channels(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    from traj_compare.export import write_parquet

    ff, fb = _parts()
    path = write_parquet(_comparison(_run(tau_ff=ff, tau_fb=fb)), tmp_path / "probe.parquet")
    channels = set(pq.read_table(path).column("channel").to_pylist())
    assert {"tau_cmd", "tau_ff", "tau_fb"} <= channels


# ── Rerun ──────────────────────────────────────────────────────────────────


def test_rerun_logs_every_torque_and_a_torque_tab_in_both_layouts(tmp_path):
    pytest.importorskip("rerun")
    from test_rerun_export import rrd_print
    from test_rerun_layouts import _find_tabs, _names, _scalars

    from traj_compare.report import _colorize
    from traj_compare.rerun_export import layout_blueprint, write_rrd

    ff, fb = _parts()
    comparison = _comparison(_run(tau_ff=ff, tau_fb=fb, tau=0.9 * (ff + fb)), _run("sim", tau_ff=ff, tau_fb=0.5 * fb))
    rrd = write_rrd(comparison, tmp_path / "probe.rrd")
    printed = rrd_print(rrd)
    for entity in (
        "/torque/shoulder/target",
        "/torque/shoulder/real_1/commanded",
        "/torque/shoulder/real_1/feedforward",
        "/torque/elbow/real_1/feedback",
        "/torque/elbow/real_1/applied",
        "/torque/elbow/sim/feedback",
        "/stats/fb_share/shoulder",
    ):
        assert entity in printed, entity
    feedforward = _scalars(rrd, "/torque/shoulder/real_1/feedforward")
    assert feedforward.size and np.nanmax(np.abs(feedforward - 2.0 * np.sin(np.pi * np.linspace(0, 2, feedforward.size)))) < 0.05

    payload = analyze_comparison(comparison)
    _colorize(payload)
    questions = _names(_find_tabs(layout_blueprint("questions", payload, {}).root_container)[0])
    evo = _names(_find_tabs(layout_blueprint("evo", payload, {}).root_container)[0])
    assert "Feedforward or feedback?" in questions
    assert "Torque" in evo

    bare = analyze_comparison(_comparison(_run(tau=np.ones((T.size, 2)))))
    _colorize(bare)
    assert "Feedforward or feedback?" not in _names(_find_tabs(layout_blueprint("questions", bare, {}).root_container)[0])
    assert "Torque" not in _names(_find_tabs(layout_blueprint("evo", bare, {}).root_container)[0])
