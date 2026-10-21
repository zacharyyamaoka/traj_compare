"""Camera overlays and the motor-current channel: model, payload, report wiring."""

import json
import re

import numpy as np
import pytest

from traj_compare import CameraOverlay, Comparison, Situation, write_comparison_report
from traj_compare.analysis import analyze_comparison


def toy_comparison(**kwargs) -> Comparison:
    t = np.linspace(0.0, 2.0, 41)
    q = np.column_stack([0.5 * np.sin(t), 0.2 * t])
    target = Situation(name="target", title="Target", t=t, q=q)
    # real runs on a finer, shorter grid so resampling onto the target's is exercised
    t_real = np.linspace(0.0, 1.5, 151)
    q_real = np.column_stack([0.5 * np.sin(t_real), 0.2 * t_real])
    current = np.column_stack([2.0 * t_real, -1.0 * np.ones_like(t_real)])
    real = Situation(name="real", title="Real", t=t_real, q=q_real, current=current)
    sim = Situation(name="sim", title="Twin", t=t, q=q)
    return Comparison(
        title="rack", joint_names=["j1", "j2"], target=target, situations=[real, sim], **kwargs
    )


def test_camera_overlay_is_carried_into_the_payload():
    overlay = CameraOverlay(
        name="D405",
        real_video="real.mp4",
        sims=[("MuJoCo", "sim_a.mp4"), ("Kinematic", "sim_b.mp4")],
        t0_s=0.35,
        note="tag 21",
    )
    payload = analyze_comparison(toy_comparison(overlays=[overlay]))
    assert payload["has_overlay"] is True
    assert payload["overlays"] == [
        {
            "name": "D405",
            "real_video": "real.mp4",
            "sims": [
                {"label": "MuJoCo", "video": "sim_a.mp4"},
                {"label": "Kinematic", "video": "sim_b.mp4"},
            ],
            "t0_s": 0.35,
            "note": "tag 21",
        }
    ]
    json.dumps(payload)


def test_no_overlays_leaves_the_payload_as_before():
    payload = analyze_comparison(toy_comparison())
    assert payload["has_overlay"] is False
    assert payload["overlays"] == []
    assert payload["has_current"] is True  # the toy real run carries current


def test_overlay_validation():
    with pytest.raises(ValueError):
        CameraOverlay(name="cam", real_video="r.mp4", sims=[])
    with pytest.raises(ValueError):
        CameraOverlay(name="cam", real_video="r.mp4", sims=[("a", "1.mp4"), ("a", "2.mp4")])
    with pytest.raises(ValueError):
        CameraOverlay(name="cam", real_video="r.mp4", sims=[("a", "1.mp4")], t0_s=float("nan"))
    overlay = CameraOverlay(name="cam", real_video="r.mp4", sims=[("a", "1.mp4")])
    with pytest.raises(ValueError):
        toy_comparison(overlays=[overlay, overlay])


def test_current_is_resampled_onto_the_target_grid_with_null_padding():
    comparison = toy_comparison()
    payload = analyze_comparison(comparison)
    plot_t = np.array(payload["plot_t"], dtype=float)
    real = next(sit for sit in payload["situations"] if sit["name"] == "real")
    channel = real["plot"]["current"]
    assert len(channel) == 2 and all(len(column) == len(plot_t) for column in channel)

    column = np.array([np.nan if v is None else v for v in channel[0]])
    inside = plot_t <= 1.5
    np.testing.assert_allclose(column[inside], 2.0 * plot_t[inside], atol=1e-5)
    # beyond the run's own span there is a gap, not a fabricated plateau
    assert inside.sum() < len(plot_t)
    assert all(v is None for v, flag in zip(channel[0], inside, strict=True) if not flag)
    assert payload["has_current"] is True


def test_missing_current_is_fine_and_target_gets_no_invented_current():
    payload = analyze_comparison(toy_comparison())
    by_name = {sit["name"]: sit for sit in payload["situations"]}
    assert by_name["target"]["plot"]["current"] is None
    assert by_name["sim"]["plot"]["current"] is None
    # no tau anywhere in this comparison, and none is invented either
    assert payload["has_tau"] is False

    t = np.linspace(0.0, 1.0, 11)
    quiet = Comparison(
        title="quiet",
        joint_names=["j"],
        situations=[Situation(name="sim", t=t, q=t)],
    )
    quiet_payload = analyze_comparison(quiet)
    assert quiet_payload["has_current"] is False
    assert quiet_payload["situations"][0]["plot"]["current"] is None


def test_current_shape_is_validated():
    t = np.linspace(0.0, 1.0, 11)
    with pytest.raises(ValueError):
        Situation(name="bad", t=t, q=np.zeros((11, 2)), current=np.zeros((11, 3)))
    with pytest.raises(ValueError):
        Situation(name="bad", current=np.zeros((11, 2)))
    one_dof = Situation(name="ok", t=t, q=t, current=t)  # 1-D promotes to (N, 1)
    assert one_dof.current.shape == (11, 1)


def test_report_ships_the_camera_section_and_current_channel(tmp_path):
    overlay = CameraOverlay(name="D405", real_video="r.mp4", sims=[("MuJoCo", "s.mp4")])
    document = write_comparison_report(toy_comparison(overlays=[overlay]), tmp_path).read_text(
        "utf-8"
    )
    match = re.search(
        r'<script type="application/json" id="traj-compare-data">(.*?)</script>',
        document,
        re.DOTALL,
    )
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    page = payload["comparisons"][0]
    assert page["overlays"][0]["real_video"] == "r.mp4"
    assert page["has_current"] is True
    # viewer contract: section ids, the A unit, and the report-level pref keys
    markers = ("'joint-current'", "'camera'", "A: { label: 'A' }", "'overlay:'", "tc-ovl-opacity")
    for marker in markers:
        assert marker in document
    assert "Real ◀ ▶ Sim" in document


def test_unknown_default_section_still_rejected():
    with pytest.raises(ValueError):
        toy_comparison(default_sections=["camera", "nope"])
    comparison = toy_comparison(default_sections=["camera", "joint-current"])
    assert comparison.default_sections == ["camera", "joint-current"]
