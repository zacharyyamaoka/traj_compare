"""The generated report must be self-contained and structurally sound."""

import json
import re

import numpy as np
import pytest

from traj_compare import (
    BarChart,
    BarSeries,
    Comparison,
    Insight,
    MetricCard,
    ReportPage,
    ReportTable,
    Situation,
    TableRow,
    write_comparison_report,
)


def translation_fk(q: np.ndarray) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, :2, 3] = q
    return poses


def small_comparison(title: str = "demo") -> Comparison:
    t = np.linspace(0.0, 1.0, 60)
    q = np.column_stack([0.3 * t, 0.1 * np.sin(2 * np.pi * t)])
    return Comparison(
        title=title,
        joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[
            Situation(name="sim_a", title="Sim A", t=t, q=q + 0.002, tau=np.ones_like(q)),
            Situation(name="real", title="Real", note="hardware skipped"),
        ],
        fk=translation_fk,
        vec_dirs=[("Conveyor", np.array([1.0, 0.0, 0.0]))],
        meta={
            "summary": {
                "title": "Metrics",
                "facts": [{"label": "Gain", "value": "8 rad/s"}],
                "columns": [
                    {"key": "name", "label": "Situation"},
                    {"key": "rms", "label": "RMS", "unit": "deg"},
                ],
                "rows": [{"name": "Sim A", "rms": "0.12"}],
            }
        },
    )


def extract_payload(document: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="traj-compare-data">(.*?)</script>',
        document,
        re.DOTALL,
    )
    assert match, "embedded data block missing"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_report_builds_and_embeds_everything(tmp_path):
    path = write_comparison_report(
        small_comparison(), tmp_path, subtitle="unit test", provenance={"agent": "pytest"}
    )
    assert path == tmp_path / "report.html"
    document = path.read_text("utf-8")

    # Self-contained: no external URLs in script/style/link tags.
    assert "src=" not in document.split("<body>")[1].split("<script")[0]
    assert "https://" not in re.sub(r"<script.*?</script>", "", document, flags=re.DOTALL)
    for marker in ("uPlot", "REVISION", "TrajCompare.boot()", "Viewer3D"):
        assert marker in document

    payload = extract_payload(document)
    assert payload["comparisons"][0]["situations"][0]["role"] == "target"
    assert payload["comparisons"][0]["situations"][0]["color"] == "#52514e"
    assert payload["comparisons"][0]["situations"][1]["color"] == "#2a78d6"
    assert payload["comparisons"][0]["has_tau"] is True

    empty = payload["comparisons"][0]["situations"][2]
    assert empty["has_data"] is False
    assert empty["note"] == "hardware skipped"
    assert "unit test" in document
    assert "agent: pytest" in document
    assert "tc-summary-table" in document
    assert payload["comparisons"][0]["meta"]["summary"]["rows"][0]["rms"] == "0.12"


def test_report_ships_the_error_overlay_controls(tmp_path):
    """The Δ-vs-target overlay is part of the viewer contract, not a build extra.

    Only the user-visible label and the per-run pref key are asserted — the
    curve itself is computed in the browser and is covered there.
    """

    document = write_comparison_report(small_comparison(), tmp_path).read_text("utf-8")
    assert "'Error vs target'" in document
    assert "err:" in document
    assert "chart.setError" in document
    # err_q is what the q overlay reuses, so it must still reach the payload
    payload = extract_payload(document)
    assert payload["comparisons"][0]["situations"][1]["plot"]["err_q"]


def test_multi_comparison_tabs_and_html_path(tmp_path):
    report_file = tmp_path / "custom.html"
    path = write_comparison_report(
        [small_comparison("one"), small_comparison("two")], report_file, title="Both"
    )
    assert path == report_file
    payload = extract_payload(path.read_text("utf-8"))
    assert [page["name"] for page in payload["comparisons"]] == ["one", "two"]
    assert payload["title"] == "Both"


def test_error_statistics_are_automatic_on_each_comparison(tmp_path):
    path = write_comparison_report(small_comparison(), tmp_path)
    table = extract_payload(path.read_text("utf-8"))["comparisons"][0]["statistics"]

    assert table["title"] == "Error statistics vs target"
    assert table["columns"][:5] == [
        "Situation",
        "Mean joint RMS",
        "Worst joint",
        "TCP pos RMS",
        "TCP rot RMS",
    ]
    assert table["rows"][0]["cells"][0] == "Sim A"
    assert table["rows"][0]["cells"][1] == "0.115°"
    assert table["rows"][0]["cells"][3] == "2.828 mm"
    assert table["rows"][1]["tone"] == "muted"


def test_identical_robot_meshes_are_embedded_once_across_comparisons(tmp_path):
    """One rig posed on many pages ships its triangle soups once.

    Each page keeps its own model (name, per-link color/opacity, poses); only
    the encoded soups move into ``mesh_library`` and links point into it, so
    a 12-page factorial study does not embed its CAD meshes 12 times.
    """

    import base64

    from traj_compare import RobotDisplay

    plate = np.array([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], dtype=np.float32)
    frame = np.array([[[0, 0, 0], [0, 0, 0.2], [0.2, 0, 0]]], dtype=np.float32)
    other = np.array([[[0, 0, 0], [0.3, 0, 0], [0, 0, 0.3]]], dtype=np.float32)

    def still(q_matrix):
        return np.tile(np.eye(4), (len(q_matrix), 2, 1, 1))

    def paged(title: str, robot: RobotDisplay) -> Comparison:
        comparison = small_comparison(title)
        comparison.robot = robot
        return comparison

    first = RobotDisplay(["frame", "plate"], [frame, plate], still, link_colors=["#888888", None])
    second = RobotDisplay(["frame", "plate"], [frame, plate], still, link_colors=[None, "#888888"])
    third = RobotDisplay(["frame", "other"], [frame, other], still)
    document = write_comparison_report(
        [paged("one", first), paged("two", second), paged("three", third)], tmp_path
    ).read_text("utf-8")
    payload = extract_payload(document)

    library = payload["mesh_library"]
    assert len(library) == 3, "frame, plate and other: each distinct soup once"
    decoded = [
        np.frombuffer(base64.b64decode(item), dtype="<f4").reshape(-1, 3, 3) for item in library
    ]
    expected = ([frame, plate], [frame, plate], [frame, other])
    for page, meshes in zip(payload["comparisons"], expected, strict=True):
        (model,) = page["robots"]
        assert [type(link["tris"]) for link in model["links"]] == [int, int]
        for link, mesh in zip(model["links"], meshes, strict=True):
            np.testing.assert_array_equal(decoded[link["tris"]], mesh)
    # per-page styling survives the sharing
    colors = [
        [link["color"] for link in page["robots"][0]["links"]] for page in payload["comparisons"]
    ]
    assert colors[:2] == [["#888888", None], [None, "#888888"]]
    # the viewer resolves the indices before any page is built
    assert "payload.mesh_library" in document


def test_grouped_navigation_and_summary_insight_pages_are_embedded(tmp_path):
    first = small_comparison("Scenario one")
    first.group = "trajectory-a"
    first.group_title = "Trajectory A"
    first.tab_title = "Gravity"
    first.situations[0].group = "simulation"
    first.situations[0].group_title = "Simulation"
    second = small_comparison("Scenario two")
    second.group = "trajectory-a"
    second.group_title = "Trajectory A"
    second.tab_title = "Zero-g"
    second.statistics = ReportTable(
        title="Custom",
        columns=["Run", "Error"],
        rows=[TableRow(["Sim A", "1.0 mm"], tone="highlight")],
    )
    summary = ReportPage(
        name="summary",
        title="Summary",
        metrics=[MetricCard("Runs", "2 / 2", tone="positive")],
        charts=[
            BarChart(
                title="Errors",
                categories=["A"],
                series=[BarSeries("Gravity", [1.0])],
                unit="mm",
            )
        ],
        tables=[
            ReportTable(
                title="Overview",
                columns=["Scenario", "Error"],
                rows=[TableRow(["A", "1.0 mm"])],
            )
        ],
    )
    insights = ReportPage(
        name="insights",
        title="Insights",
        insights=[
            Insight(
                title="Do this",
                finding="Evidence points one way.",
                recommendation="Run the next test.",
                tone="action",
            )
        ],
    )

    path = write_comparison_report(
        [first, second],
        tmp_path,
        summary=summary,
        insights=insights,
    )
    document = path.read_text("utf-8")
    payload = extract_payload(document)

    assert [page["group"] for page in payload["comparisons"]] == [
        "trajectory-a",
        "trajectory-a",
    ]
    assert [page["tab_title"] for page in payload["comparisons"]] == [
        "Gravity",
        "Zero-g",
    ]
    assert payload["comparisons"][0]["situations"][1]["group"] == "simulation"
    assert payload["comparisons"][1]["statistics"]["title"] == "Custom"
    assert [page["name"] for page in payload["report_pages"]] == ["summary", "insights"]
    assert payload["report_pages"][0]["charts"][0]["series"][0]["values"] == [1.0]
    assert "id='tc-subtabs'" in document
    assert "function buildInsightCards" in document


def test_comparison_can_surface_torque_by_default(tmp_path):
    comparison = small_comparison()
    comparison.default_sections = ["joint-q", "joint-tau", "tcp-err"]
    path = write_comparison_report(comparison, tmp_path)
    payload = extract_payload(path.read_text("utf-8"))

    assert payload["comparisons"][0]["default_sections"] == [
        "joint-q",
        "joint-tau",
        "tcp-err",
    ]
    document = path.read_text("utf-8")
    assert "sectionStartsOn(data, 'joint-tau', false)" in document
    assert "Motor / joint τ" in document


def test_script_terminator_inside_data_is_escaped(tmp_path):
    comparison = small_comparison()
    comparison.description = "beware </script> injection"
    path = write_comparison_report(comparison, tmp_path)
    document = path.read_text("utf-8")
    payload = extract_payload(document)
    assert payload["comparisons"][0]["description"] == "beware </script> injection"


def test_empty_comparison_list_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_comparison_report([], tmp_path)
