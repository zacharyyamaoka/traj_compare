"""Open in Rerun on a run that HAS a target: the round's V2 "Target vs run" is traj_compare's stock (2026-11-25).

Zach, 2026-11-25, on the Rerun pick round (docs/proposals/rerun-pick-variants-2026-11-24/): "when we are look at just a
normal trajectory without comparison than I think it makes sense to just keep with V1. that should basically just be
the stock like robot msg viz viewer for a joint trajectory". So a lone trajectory stays robot_msgs' V1
(test_coverage_workbench_robot.py), and a run with its target is V2: the run drawn as V1's steel arm, its deviation from
the target ×N as a magenta skeleton with an arrow labelled "TCP off X mm", an Error tab first, and the target a pale
line under the run on V1's six tabs.

Every check reads the .rrd back with Rerun's own reader (or the blueprint object), against the made-up arm's closed-form
kinematics (target_run_fixture.py), never against the forward kinematics the recording was made with.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("rerun")

from target_run_fixture import (  # noqa: E402
    JOINTS,
    URDF,
    link_poses,
    nice,
    target_and_run,
    tcp,
    tool_of,
    well_tracked,
)

from traj_compare import Comparison, RobotDisplay, Situation, write_comparison_report  # noqa: E402
from traj_compare.coverage.workbench import write_trajectory_rrd  # noqa: E402
from traj_compare.rerun_export import (  # noqa: E402
    LAYOUTS,
    blueprint_path,
    rerun_view,
    target_vs_run_blueprint,
    viewer_command,
    write_rrd,
    write_target_vs_run_rrd,
)

# ── reading the .rrd back ───────────────────────────────────────────────────────────────────────────────────────────


def rows(path: Path, entity: str, column: str) -> list[tuple[float | None, object]]:
    """(t in seconds or None for static, value) of one component column at one entity, in time order."""
    from rerun.chunk import RrdReader

    found = []
    for chunk in RrdReader(path).stream():
        if chunk.entity_path != entity:
            continue
        batch = chunk.to_record_batch()
        if column not in batch.schema.names:
            continue
        values = batch.column(column).to_pylist()
        times = batch.column("t").cast("int64").to_pylist() if "t" in batch.schema.names else [None] * len(values)
        found += [(None if ns is None else ns / 1e9, value) for ns, value in zip(times, values, strict=True)]
    return sorted(found, key=lambda row: -1e9 if row[0] is None else row[0])


def entities(path: Path) -> set[str]:
    from rerun.chunk import RrdReader

    return {chunk.entity_path for chunk in RrdReader(path).stream()}


def series(path: Path, entity: str) -> tuple[np.ndarray, np.ndarray]:
    """(times, values (N,) or (N, k)) of a scalar series entity."""
    found = [(at, value) for at, value in rows(path, entity, "Scalars:scalars") if at is not None and value]
    values = np.asarray([value for _, value in found], dtype=float)
    return np.asarray([at for at, _ in found]), values[:, 0] if values.shape[1] == 1 else values


def tab_names(path: Path) -> list[str]:
    """The embedded blueprint's tab names in order, read from its one Tabs container (container_kind 1) with Rerun's
    reader: what the viewer shows, whichever writer made the recording."""
    from rerun.chunk import RrdReader

    reader = RrdReader(path)
    names, contents = {}, []
    for chunk in reader.stream(store=reader.blueprints()[0]):
        batch = chunk.to_record_batch()
        fields = batch.schema.names
        key = chunk.entity_path.lstrip("/")
        if "ContainerBlueprint:display_name" in fields:
            names[key] = batch.column("ContainerBlueprint:display_name").to_pylist()[-1][0]
        if ("ContainerBlueprint:container_kind" in fields
                and batch.column("ContainerBlueprint:container_kind").to_pylist()[-1] == [1]):
            contents.append(batch.column("ContainerBlueprint:contents").to_pylist()[-1])
    assert len(contents) == 1, f"{path.name}: {len(contents)} Tabs containers"
    return [names.get(child) for child in contents[0]]


def views(node) -> list:
    if type(node).__name__ in ("Horizontal", "Vertical", "Grid", "Tabs"):
        return [view for child in node.contents for view in views(child)]
    return [node]


def write(tmp_path: Path, name: str = "run.rrd", **options) -> Path:
    target, run = target_and_run(**options.pop("fixture", {}))
    return write_target_vs_run_rrd(tmp_path / name, run, target=target, robot=URDF, tool=tool_of(run),
                                   target_tool=tool_of(target), **options)


# ── the recording ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_run_is_v1s_steel_arm_and_the_target_and_its_error_ride_on_it(tmp_path):
    path = write(tmp_path)
    found = entities(path)
    # the run: robot_msgs' V1 logger, unchanged (its arm, its series, its TCP, its playhead table, its tool path)
    assert {f"/world/run/robot/joint_transforms/{joint}" for joint in JOINTS} <= found
    assert {f"/positions/{joint}/run" for joint in JOINTS} <= found
    assert {"/tcp/position_mm/run", "/notes/run", "/world/run/tool/trail", "/world/run/tool/stick"} <= found
    # no ghosts and no second arm: the target is within a degree of the run, so it is drawn as a path and a skeleton
    assert not any("/ghost_" in entity for entity in found)
    assert not any(entity.startswith("/world/reference") for entity in found)
    # the target: a pale line under every plot, and its dashed tool path
    assert {f"/positions/{joint}/reference" for joint in JOINTS} <= found
    assert {"/tcp/position_mm/reference", "/world/run/target_tool/path"} <= found
    # the error and the magnifier
    assert {"/error/joint/run", "/error/tool/ruler", "/notes/error"} <= found
    assert {f"/world/run/magnifier/{part}" for part in ("now", "skeleton", "joints", "tip", "label", "path")} <= found
    from rerun.chunk import RrdReader

    reader = RrdReader(path)
    assert [store.application_id for store in reader.recordings()] == ["traj_compare"]
    assert reader.blueprints(), "the dashboard is embedded"


def test_the_series_are_the_run_and_the_target_in_degrees_and_the_target_sorts_first(tmp_path):
    target, run = target_and_run()
    path = write(tmp_path)
    for index, joint in enumerate(JOINTS):
        _, shown_run = series(path, f"/positions/{joint}/run")
        _, shown_target = series(path, f"/positions/{joint}/reference")
        np.testing.assert_allclose(shown_run, np.degrees(run.positions[:, index]))
        np.testing.assert_allclose(shown_target, np.degrees(target.positions[:, index]))
    # WHY it matters: Rerun 0.40 draws a plot's series in entity-path order, so the pale target lies under the bold run
    assert "/positions/elbow/reference" < "/positions/elbow/run"


def test_the_joint_error_is_run_minus_target_in_degrees(tmp_path):
    target, run = target_and_run()
    path = write(tmp_path)
    times, error = series(path, "/error/joint/run")
    np.testing.assert_allclose(times, run.t - run.t[0])
    np.testing.assert_allclose(error, np.degrees(run.positions - target.positions), atol=1e-9)


def test_the_magnifier_is_a_1_2_5_scale_in_joint_space_and_its_arrow_ends_on_the_skeletons_tool_point(tmp_path):
    target, run = target_and_run()
    path = write(tmp_path)
    arrows = rows(path, "/world/run/magnifier/now", "Arrows3D:origins")
    vectors = rows(path, "/world/run/magnifier/now", "Arrows3D:vectors")
    skeletons = rows(path, "/world/run/magnifier/skeleton", "LineStrips3D:strips")
    labels = rows(path, "/world/run/magnifier/label", "Points3D:labels")
    title = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run),
                                    target_tool=tool_of(target)).root_container.contents[0].name
    factor = int(re.search(r"run ×(\d+)", title).group(1))
    assert nice(factor) and factor > 1
    seconds = run.t - run.t[0]
    true_off = np.linalg.norm(tcp(run.positions) - tcp(target.positions), axis=1) * 1000.0
    magnified = target.positions + factor * (run.positions - target.positions)
    checked = 0
    for (at, origin), (_, vector), (_, strips), (_, label) in zip(arrows, vectors, skeletons, labels, strict=True):
        if at is None:
            continue
        row = int(np.argmin(np.abs(seconds - at)))
        origin, tip = np.asarray(origin[0]), np.asarray(origin[0]) + np.asarray(vector[0])
        np.testing.assert_allclose(origin, tcp(target.positions)[row], atol=1e-9)  # from the target's tool point
        np.testing.assert_allclose(tip, tcp(magnified)[row], atol=1e-9)  # to the ×N arm's tool point (joint space)
        np.testing.assert_allclose(np.asarray(strips[0])[-1], tip, atol=1e-9)  # where the skeleton ends
        assert label[0] == f"run ×{factor} · TCP off {true_off[row]:.1f} mm"  # the TRUE offset, not ×N
        checked += 1
    assert checked > 50
    # the skeleton runs through the ×N arm's joints: its elbow (l3's origin) is on it at the worst instant
    worst = int(np.argmax(true_off))
    at, strips = min(((at, s) for at, s in skeletons if at is not None), key=lambda row: abs(row[0] - seconds[worst]))
    elbow = link_poses(magnified[worst:worst + 1])[0, 2, :3, 3]
    assert min(np.linalg.norm(np.asarray(strips[0]) - elbow, axis=1)) < 1e-6  # Rerun stores float32


def factor_of(run, target) -> int:
    """The ×N the dashboard's 3D title names."""
    title = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run),
                                    target_tool=tool_of(target)).root_container.contents[0].name
    return int(re.search(r"run ×(\d+)", title).group(1))


def next_nice(factor: int) -> int:
    """The 1-2-5 step after ``factor`` (20 -> 50 -> 100)."""
    lead = int(str(factor)[0])
    return factor * (5 if lead == 2 else 2) // (2 if lead == 2 else 1)


# WHY 35° (2026-11-25, the UR workbench check): the largest magnified joint deviation, N × max |run − target| over every
# joint and instant. The pick round's UR5e tour reads as a deformation at ×50 with its worst joint (wrist 2, 0.62°) at
# 31°, and must keep ×50; the UR5e sim run ctc_tuned_v2 r0 at ×2000 put its elbow 77° off and stopped reading as the arm
MAX_MAGNIFIED_DEG = 35.0


def test_a_well_tracked_runs_magnifier_keeps_every_joint_within_35_degrees(tmp_path):
    """Joint errors of a few hundredths of a degree that cancel at the tool: the tool share alone asked for ×5000 and
    swung the skeleton 179° (red on 15e9f4b); the joint cap holds it to the largest 1-2-5 step within 35°."""
    target, run = well_tracked()
    peak = float(np.abs(np.degrees(run.positions - target.positions)).max())
    assert peak < 0.05  # the fixture is what it says: well tracked
    factor = factor_of(run, target)
    assert nice(factor) and factor > 1
    assert factor * peak <= MAX_MAGNIFIED_DEG, f"×{factor} swings a joint {factor * peak:.1f}° off"
    assert next_nice(factor) * peak > MAX_MAGNIFIED_DEG, f"×{factor} is not the largest step within the cap"
    # what is drawn is what is said: the arrow ends on the ×N arm's tool point, the label names that ×N and the TRUE offset
    path = write_target_vs_run_rrd(tmp_path / "well.rrd", run, target=target, robot=URDF, tool=tool_of(run),
                                   target_tool=tool_of(target))
    seconds = run.t - run.t[0]
    magnified = target.positions + factor * (run.positions - target.positions)
    true_off = np.linalg.norm(tcp(run.positions) - tcp(target.positions), axis=1) * 1000.0
    origins = rows(path, "/world/run/magnifier/now", "Arrows3D:origins")
    vectors = rows(path, "/world/run/magnifier/now", "Arrows3D:vectors")
    labels = rows(path, "/world/run/magnifier/label", "Points3D:labels")
    checked = 0
    for (at, origin), (_, vector), (_, label) in zip(origins, vectors, labels, strict=True):
        if at is None:
            continue
        row = int(np.argmin(np.abs(seconds - at)))
        np.testing.assert_allclose(np.asarray(origin[0]) + np.asarray(vector[0]), tcp(magnified)[row], atol=1e-6)
        assert label[0] == f"run ×{factor} · TCP off {true_off[row]:.1f} mm"
        checked += 1
    assert checked > 50


def test_the_cap_leaves_a_run_it_does_not_bind_at_its_tool_share_factor():
    """The closely tracked run (elbow 0.38° worst) keeps the tool share's ×50: 19°, inside the cap."""
    target, run = target_and_run()
    assert factor_of(run, target) == 50


def test_the_tool_error_is_the_runs_own_ruler_when_given_else_the_tcp_offset(tmp_path):
    target, run = target_and_run()
    true_off = np.linalg.norm(tcp(run.positions) - tcp(target.positions), axis=1) * 1000.0
    plain = write(tmp_path, "plain.rrd")
    np.testing.assert_allclose(series(plain, "/error/tool/ruler")[1], true_off, atol=1e-9)
    assert "/error/tool/fk_tcp_off" not in entities(plain)
    ruler = 0.6 * true_off + 0.1
    given = write(tmp_path, "ruler.rrd", tool_error_mm=ruler, tool_error_rms_mm=0.42)
    np.testing.assert_allclose(series(given, "/error/tool/ruler")[1], ruler)
    np.testing.assert_allclose(series(given, "/error/tool/fk_tcp_off")[1], true_off, atol=1e-9)
    tool_view = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run), target_tool=tool_of(target),
                                        tool_error_mm=ruler, tool_error_rms_mm=0.42)
    error_tab = tool_view.root_container.contents[1].contents[0]
    assert "RMS 0.42" in views(error_tab)[0].name
    with pytest.raises(ValueError, match="one value per run sample"):
        write(tmp_path, "short.rrd", tool_error_mm=ruler[:-3])


def test_a_run_that_starts_late_is_drawn_late_against_its_target(tmp_path):
    target, run = target_and_run(start_late_s=0.2)
    path = write(tmp_path, fixture={"start_late_s": 0.2})
    run_times, _ = series(path, "/positions/elbow/run")
    target_times, _ = series(path, "/positions/elbow/reference")
    # t = 0 is the run's first sample (V1's own clock for the run); the target, 0.2 s earlier, starts at -0.2 s
    assert run_times[0] == pytest.approx(0.0) and target_times[0] == pytest.approx(-0.2)
    # the error at each run sample is against the target at the SAME instant (held at its end pose after it ends)
    absolute = run.header.stamp + run.t
    expected = np.stack([np.interp(absolute, target.header.stamp + target.t, target.positions[:, k])
                         for k in range(len(JOINTS))], 1)
    np.testing.assert_allclose(series(path, "/error/joint/run")[1], np.degrees(run.positions - expected), atol=1e-9)


# ── the dashboard ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_dashboard_is_v1s_with_the_error_tab_first_and_the_target_keyed_in_every_title():
    target, run = target_and_run()
    blueprint = target_vs_run_blueprint(run, target=target, robot=URDF, tool=tool_of(run), target_tool=tool_of(target))
    world, tabs = blueprint.root_container.contents
    assert type(world).__name__ == "Spatial3DView" and "/world/run/**" in world.contents
    assert world.name.startswith("steel = run · magenta skeleton = run ×")
    assert [tab.name for tab in tabs.contents] == ["Error", "q", "qd", "qdd", "qddd", "q / qd / qdd", "TCP"]
    assert tabs.active_tab in (0, "Error")
    error = views(tabs.contents[0])
    assert [type(view).__name__ for view in error] == ["TimeSeriesView", "TimeSeriesView", "TextDocumentView"]
    assert error[0].name.startswith("Tool error [mm]") and error[1].name.startswith("Joint error, run − target [°]")
    assert error[2].origin == "/notes/error"
    q = views(tabs.contents[1])
    assert all(" · run − target ≤ " in view.name for view in q)
    assert "bold = run, pale = target, grey = limit" in q[0].name
    assert all(any(entry.endswith("/reference") for entry in view.contents) for view in q)
    assert "grey = limit" not in views(tabs.contents[4])[0].name  # qddd: no jerk limit, no grey line, not claimed
    panel = blueprint.time_panel
    assert (panel.play_state, panel.timeline) == ("paused", "t")


# ── who gets V2, who keeps V1 ──────────────────────────────────────────────────────────────────────────────────────


def test_a_lone_trajectory_stays_v1(tmp_path):
    """The coverage workbench's record (a lone trajectory, no target) keeps robot_msgs' V1, ghosts and all."""
    target, _ = target_and_run()
    lone = write_trajectory_rrd(tmp_path / "lone.rrd", "lone", target, robot=URDF, tool=tool_of(target))
    found = entities(lone)
    assert "/world/lone/ghost_start/joint_transforms/pan" in found  # V1, as before
    assert not any(entity.startswith(("/error", "/world/run")) for entity in found)


def test_the_recording_id_and_application_id_name_the_run(tmp_path):
    from rerun.chunk import RrdReader

    path = write(tmp_path, recording_id="task-7", application_id="traj_compare_runs")
    assert [(store.application_id, store.recording_id) for store in RrdReader(path).recordings()] == [
        ("traj_compare_runs", "task-7")]
    with pytest.raises(ValueError, match="together"):
        target, run = target_and_run()
        write_target_vs_run_rrd(tmp_path / "x.rrd", run, target=target, robot=URDF, tool=tool_of(run))


def comparison(*, urdf: bool = True, runs: int = 1, poses: bool = True) -> Comparison:
    target, run = target_and_run()
    display = RobotDisplay(link_names=["l1", "l2", "l3", "tool"], link_meshes=[np.zeros((1, 3, 3))] * 4,
                           link_fk=link_poses, urdf=str(URDF) if urdf else None)
    situations = [Situation(name=f"real{k}" if k else "real", title=f"Real {k}", t=run.t, q=run.positions,
                            poses=link_poses(run.positions)[:, 3] if poses else None) for k in range(runs)]
    return Comparison(title="Tour 7", name="tour-7", joint_names=list(JOINTS),
                      target=Situation(name="target", title="Target", t=target.t, q=target.positions,
                                       qd=target.velocities, qdd=target.accelerations,
                                       poses=link_poses(target.positions)[:, 3] if poses else None),
                      situations=situations, robot=display, tcp_frame="tool")


def test_write_rrd_draws_a_one_run_comparison_on_its_urdf_as_target_vs_run(tmp_path):
    one = comparison()
    assert rerun_view(one) == "target_vs_run"
    path = write_rrd(one, tmp_path / "rerun" / "tour-7.rrd")
    found = entities(path)
    assert {"/world/run/magnifier/skeleton", "/error/joint/run", "/positions/pan/reference"} <= found
    # no named-layout files beside it: they lay out the questions recording, not this one
    assert not any(blueprint_path(path, name).exists() for name in LAYOUTS)
    target, run = target_and_run()
    np.testing.assert_allclose(series(path, "/error/joint/run")[1], np.degrees(run.positions - target.positions),
                               atol=1e-9)
    # the tool is the situations' own poses (in the URDF's root frame): TCP off is the closed form's
    true_off = np.linalg.norm(tcp(run.positions) - tcp(target.positions), axis=1) * 1000.0
    np.testing.assert_allclose(series(path, "/error/tool/ruler")[1], true_off, atol=1e-6)


def test_without_a_urdf_or_with_several_runs_write_rrd_is_the_questions_recording_as_before(tmp_path):
    for case in (comparison(urdf=False), comparison(runs=2)):
        assert rerun_view(case) == "layouts"
        path = write_rrd(case, tmp_path / f"{len(case.situations)}-{case.robot.urdf is None}.rrd")
        assert "/world/run/magnifier/skeleton" not in entities(path)
        assert all(blueprint_path(path, name).exists() for name in LAYOUTS)
    forced = write_rrd(comparison(), tmp_path / "forced.rrd", view="layouts")
    assert "/world/run/magnifier/skeleton" not in entities(forced)
    with pytest.raises(ValueError, match="one target and one run"):
        write_rrd(comparison(runs=2), tmp_path / "no.rrd", view="target_vs_run")


def test_the_comparison_reports_open_in_rerun_opens_the_target_vs_run_recording_bare(tmp_path):
    page = write_comparison_report(comparison(), tmp_path / "report.html", rerun=True)
    data = json.loads(re.search(r'id="traj-compare-data">(.*?)</script>', page.read_text(), re.S).group(1)
                      .replace("<\\/", "</"))
    rerun = data["comparisons"][0]["rerun"]
    assert rerun["layout"] == "target_vs_run" and rerun["layouts"] == []  # no picker, no .rbl to open beside it
    assert rerun["command"] == viewer_command(tmp_path / "rerun" / "tour-7.rrd")
    assert "/world/run/magnifier/skeleton" in entities(tmp_path / "rerun" / "tour-7.rrd")


# ── the runs workbench's Open in Rerun (selection.build_selection_rrd) and the dataset page's drill-down ────────────


@pytest.fixture
def site(tmp_path) -> Path:
    from traj_compare import Run, write_dataset_report

    target, run = target_and_run()
    second = run.replace(positions=target.positions + 0.5 * (run.positions - target.positions)).with_derivatives(
        overwrite=True)
    runs = [Run(name=f"tour-{k}", title=f"Tour {k}", reference=target, measured={"real": series_},
                tags={"target": "tour"}) for k, series_ in enumerate((run, second))]
    out = tmp_path / "site"
    write_dataset_report(runs, out, title="Made-up arm", robot="target_run_fixture:robot",
                         poses="target_run_fixture:poses", rows=())
    return out


def folders(site: Path) -> list[Path]:
    return sorted(path.parent for path in (site / "runs").glob("*/manifest.json"))


def test_one_ticked_run_on_a_urdf_opens_as_target_vs_run_and_several_stay_one_line_each(site, tmp_path):
    from traj_compare.selection import Pick, build_selection_rrd

    first, second = folders(site)
    one, names = build_selection_rrd([Pick(first, "real")], tmp_path / "one.rrd")
    assert names == ["target", "Tour 0 · real"]
    assert {"/world/run/magnifier/skeleton", "/error/joint/run", "/positions/elbow/reference"} <= entities(one)
    target, run = target_and_run()
    np.testing.assert_allclose(series(one, "/error/joint/run")[1], np.degrees(run.positions - target.positions),
                               atol=1e-6)  # the npz round trip
    both, _ = build_selection_rrd([Pick(first, "real"), Pick(second, "real")], tmp_path / "both.rrd")
    assert "/world/run/magnifier/skeleton" not in entities(both)
    assert {"/positions/elbow/run1", "/positions/elbow/run2", "/positions/elbow/target"} <= entities(both)


def test_the_dataset_pages_drill_down_rrd_is_target_vs_run_when_the_site_knows_its_urdf(site):
    from traj_compare.dataset import build_run_folder

    folder = folders(site)[0]
    build_run_folder(folder)
    recordings = sorted((folder / "rerun").glob("*.rrd"))
    assert recordings, "the drill-down writes one .rrd per pair"
    assert all("/world/run/magnifier/skeleton" in entities(path) for path in recordings)


V2_TABS = ["Error", "q", "qd", "qdd", "qddd", "q / qd / qdd", "TCP"]


@pytest.mark.parametrize("stored", ["q and qd", "q only"])
def test_both_open_in_rerun_paths_show_the_same_tabs_for_a_run_stored_without_accelerations(tmp_path, stored):
    """A sim run stores no accelerations: the drill-down differentiated it (all seven tabs) and the runs workbench did not
    (no qdd, no qddd; found 2026-11-25 on the UR workbench). Both now fill what is missing the same way: np.gradient of
    what the run stores, the drill-down's (rerun_target_run._joint), never a second differentiator."""
    from robot_msgs._core import load_npz

    from traj_compare import Run, write_dataset_report
    from traj_compare.dataset import build_run_folder
    from traj_compare.selection import Pick, build_selection_rrd

    target, run = target_and_run()
    run = run.replace(accelerations=None) if stored == "q and qd" else run.replace(velocities=None, accelerations=None)
    out = tmp_path / "site"
    write_dataset_report([Run(name="sim-0", title="Sim 0", reference=target, measured={"sim": run},
                              tags={"target": "tour"})], out, title="Made-up arm", robot="target_run_fixture:robot",
                         poses="target_run_fixture:poses", rows=())
    (folder,) = folders(out)
    manifest = json.loads((folder / "manifest.json").read_text())
    stored_run = load_npz(folder / manifest["files"]["sim"])
    assert stored_run.accelerations is None  # else this proves nothing
    workbench, _ = build_selection_rrd([Pick(folder, "sim")], tmp_path / "workbench.rrd")
    build_run_folder(folder)
    (drill,) = sorted((folder / "rerun").glob("*.rrd"))
    assert tab_names(workbench) == V2_TABS, "the runs workbench's Open in Rerun"
    assert tab_names(drill) == V2_TABS, "the dataset drill-down's"
    # the same numbers on both, and they are np.gradient (edge order 1) of what the run stores, in degrees
    t = stored_run.t
    qd = np.gradient(stored_run.positions, t, axis=0) if stored_run.velocities is None else stored_run.velocities
    qdd = np.gradient(qd, t, axis=0)
    for index, joint in enumerate(JOINTS):
        for field, expected in (("velocities", qd), ("accelerations", qdd)):
            entity = f"/{field}/{joint}/run"
            np.testing.assert_allclose(series(workbench, entity)[1], np.degrees(expected[:, index]), atol=1e-6)
            np.testing.assert_allclose(series(drill, entity)[1], series(workbench, entity)[1], atol=1e-6)
        np.testing.assert_allclose(series(drill, f"/jerks/{joint}/run")[1], series(workbench, f"/jerks/{joint}/run")[1],
                                   atol=1e-6)
