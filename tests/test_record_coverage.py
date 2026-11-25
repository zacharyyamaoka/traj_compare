"""Record coverage: any list of dataclass records in, one payload out (acceptance, written before the code, 2026-11-24).

Contract: docs/RECORD_COVERAGE.md. Every expected number here is recomputed from the records with numpy / the standard
library (or robot_msgs.coverage.binned for the pair planes), never read back from the module under test.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pytest
from dataclass_values import Value
from robot_msgs.coverage import binned
from robot_msgs.geometry import Point, Pose

from traj_compare.record_coverage import SCHEMA, analyze

NUMBER_KEYS = {
    "records", "fields", "number_fields", "category_fields", "missing_pct", "complete_records_pct",
    "range_visited_mean_pct", "fields_without_range", "class_imbalance_max", "missing_classes",
    "pair_visited_mean_pct", "coverage_visited_pct", "last_tenth_new_pct", "ceiling_pct", "droppable_records_pct",
}


class Bin(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    FAR = "far"


@dataclass(frozen=True)
class Grip:
    width_mm: float = Value(40.0, "mm", low=0.0, high=80.0)
    force_n: float = Value(10.0, "N", low=0.0, high=50.0)


@dataclass(frozen=True)
class Pick:
    name: str
    item: str = Value("vial", choices=("vial", "pill", "cap", "box"))  # "box" never appears: a missing class
    split: str = "dev"
    bin: Bin = Bin.LEFT
    ok: bool = True
    angle_rad: float = Value(0.0, "rad", low=-1.0, high=1.0)
    grip: Grip = field(default_factory=Grip)
    tcp: tuple = (0.0, 0.0, 0.0)
    speed: float | None = None  # no range anywhere: the data's span, "no range stated"
    draws: int = 0
    path: tuple = ()  # longer than 4: its length

    @property
    def n_path(self) -> int:
        return len(self.path)

    @property
    def broken(self) -> float:
        raise RuntimeError("a property that raises is skipped")


def made_up(n: int = 240, seed: int = 0) -> list[Pick]:
    rng = random.Random(seed)
    picks = []
    for i in range(n):
        item = rng.choices(["vial", "pill", "cap", "lid"], weights=[60, 25, 10, 5])[0]  # "lid" is undeclared
        picks.append(Pick(
            name=f"pick-{i:03d}", item=item, split="holdout" if i % 5 == 4 else "dev",
            bin=rng.choice([Bin.LEFT, Bin.LEFT, Bin.RIGHT]), ok=rng.random() < 0.8,
            angle_rad=rng.uniform(-0.6, 0.9) if i % 17 else 1.3,  # every 17th is beyond the declared range
            grip=Grip(width_mm=rng.uniform(5.0, 60.0), force_n=rng.uniform(2.0, 45.0)),
            tcp=(rng.uniform(-0.3, 0.3), rng.uniform(0.2, 0.5), rng.uniform(-0.1, 0.1)),
            speed=None if i % 7 == 0 else (float("nan") if i % 11 == 0 else rng.uniform(0.1, 0.4)),
            draws=rng.randint(0, 9), path=tuple(range(rng.randint(5, 9))),
        ))
    return picks


@pytest.fixture(scope="module")
def picks() -> list[Pick]:
    return made_up()


@pytest.fixture(scope="module")
def coverage(picks):
    return analyze(picks, ranges={"draws": (0, 9), "tcp[0]": (-0.4, 0.4), "tcp[1]": (0.0, 0.6), "tcp[2]": (-0.2, 0.2)},
                   pairs=[("angle_rad", "grip.width_mm"), ("tcp[0]", "tcp[1]")], group_by="item", split="split",
                   title="Made-up picks")


def column(picks, getter) -> list:
    return [getter(p) for p in picks]


def present(values) -> np.ndarray:
    return np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))], float)


def histogram(values: np.ndarray, block) -> np.ndarray:
    low, high, bins = block
    counts, _ = np.histogram(values, bins=np.linspace(low, high, bins + 1))  # numpy closes the last bin, as the contract
    return counts


# ── fields ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_payload_is_json_safe_and_names_its_schema(coverage):
    payload = coverage.payload
    assert payload["schema"] == SCHEMA == "traj_compare.record_coverage/1"
    json.dumps(payload, allow_nan=False)
    assert payload["title"] == "Made-up picks"
    assert payload["source"]["records"] == 240


def test_a_record_is_flattened_into_columns_in_declaration_order(coverage):
    fields = {f["name"]: f for f in coverage.payload["fields"]}
    names = list(fields)
    expected = ["name", "item", "split", "bin", "ok", "angle_rad", "grip.width_mm", "grip.force_n", "tcp[0]", "tcp[1]",
                "tcp[2]", "speed", "draws", "len(path)", "n_path"]
    assert names == expected
    assert fields["tcp[1]"]["origin"] == "component"
    assert fields["len(path)"]["origin"] == "length" and fields["len(path)"]["kind"] == "number"
    assert fields["n_path"]["origin"] == "property"
    assert "broken" not in fields
    assert [fields[n]["kind"] for n in ("name", "item", "bin", "ok", "angle_rad", "draws")] == \
           ["text", "category", "category", "category", "number", "number"]


def test_an_identifier_field_is_text_and_names_the_records(coverage):
    payload = coverage.payload
    assert payload["source"]["id_field"] == "name"
    assert payload["texts"]["name"]["distinct"] == 240 and payload["texts"]["name"]["duplicates"] == 0
    assert [r["id"] for r in payload["records"][:2]] == ["pick-000", "pick-001"]


def test_units_come_from_the_value_or_the_name_and_radians_show_in_degrees(coverage):
    fields = {f["name"]: f for f in coverage.payload["fields"]}
    assert fields["angle_rad"]["unit"] == "rad"
    assert fields["angle_rad"]["display"]["unit"] == "°"
    assert fields["angle_rad"]["display"]["scale"] == pytest.approx(180.0 / math.pi)
    assert fields["grip.width_mm"]["unit"] == "mm" and fields["grip.width_mm"]["display"] == {"scale": 1.0, "unit": "mm"}
    assert fields["grip.force_n"]["unit"] == "N"


# ── number fields against their declared range ──────────────────────────────────────────────────────────────────────


def test_the_class_default_value_declares_the_range(coverage):
    hist = coverage.payload["hist"]["angle_rad"]
    assert (hist["low"], hist["high"], hist["source"]) == (-1.0, 1.0, "declared")
    # 40 bins inside the range plus 4 of margin each side: the limits fall exactly on bin edges
    assert hist["edges"] == [pytest.approx(-1.2), pytest.approx(1.2), 48]


def test_a_given_range_wins_and_a_field_without_one_takes_the_data_span(coverage, picks):
    hist = coverage.payload["hist"]
    assert (hist["tcp[0]"]["low"], hist["tcp[0]"]["high"], hist["tcp[0]"]["source"]) == (-0.4, 0.4, "given")
    speed = present(column(picks, lambda p: p.speed))
    p001, p999 = np.percentile(speed, [0.1, 99.9])
    middle, half = (p001 + p999) / 2, (p999 - p001) / 2 * 1.15
    assert hist["speed"]["source"] == "data"
    assert hist["speed"]["low"] == pytest.approx(middle - half) and hist["speed"]["high"] == pytest.approx(middle + half)
    assert hist["speed"]["outside"] == 0  # a data span is never a limit


def test_the_histogram_counts_match_numpy_and_count_what_is_beyond_the_range(coverage, picks):
    hist = coverage.payload["hist"]["angle_rad"]
    values = present(column(picks, lambda p: p.angle_rad))
    assert hist["counts"] == histogram(values, hist["edges"]).tolist()
    assert hist["outside"] == int(((values < -1.0) | (values > 1.0)).sum()) > 0
    inside = histogram(values, (-1.0, 1.0, 40))
    assert hist["visited_pct"] == pytest.approx(100.0 * np.count_nonzero(inside) / 40)
    p001, p999 = np.percentile(values, [0.1, 99.9])
    assert hist["p001"] == pytest.approx(p001) and hist["p999"] == pytest.approx(p999)
    assert hist["span_pct"] == pytest.approx((p999 - p001) / 2.0 * 100)
    assert hist["min"] == pytest.approx(values.min()) and hist["max"] == pytest.approx(values.max())


def test_a_whole_number_field_gets_one_bin_per_integer(coverage, picks):
    hist = coverage.payload["hist"]["draws"]
    assert hist["integer"] is True
    assert hist["edges"] == [pytest.approx(-1.5), pytest.approx(10.5), 12]  # 10 integers + 1 margin bin each side
    values = np.asarray(column(picks, lambda p: p.draws), float)
    assert hist["counts"] == histogram(values, hist["edges"]).tolist()


def test_histograms_stack_by_the_group_and_add_back_up(coverage, picks):
    hist = coverage.payload["hist"]["grip.width_mm"]
    assert set(hist["groups"]) == {"vial", "pill", "cap", "lid"}
    assert np.sum([hist["groups"][g] for g in hist["groups"]], axis=0).tolist() == hist["counts"]
    vials = present([p.grip.width_mm for p in picks if p.item == "vial"])
    assert hist["groups"]["vial"] == histogram(vials, hist["edges"]).tolist()


# ── categories: class balance ────────────────────────────────────────────────────────────────────────────────────────


def test_class_balance_lists_declared_levels_first_and_names_the_missing_class(coverage, picks):
    item = coverage.payload["classes"]["item"]
    counts = Counter(p.item for p in picks)
    assert item["levels"] == ["vial", "pill", "cap", "box", "lid"]
    assert item["declared"] == [True, True, True, True, False]
    assert item["source"] == "declared"
    assert item["counts"] == [counts[level] for level in item["levels"]]
    assert item["unseen"] == ["box"] and item["undeclared"] == ["lid"]
    seen = [c for c in item["counts"] if c]
    total = sum(seen)
    assert item["majority_pct"] == pytest.approx(100 * max(seen) / total)
    assert item["minority_pct"] == pytest.approx(100 * min(seen) / total)
    assert item["imbalance_ratio"] == pytest.approx(max(seen) / min(seen))
    shares = np.asarray(seen) / total
    effective = math.exp(-float(np.sum(shares * np.log(shares))))
    assert item["effective_classes"] == pytest.approx(effective)
    assert item["evenness_pct"] == pytest.approx(100 * effective / 5)


def test_an_enum_lists_its_members_and_a_bool_both_values(coverage, picks):
    classes = coverage.payload["classes"]
    assert classes["bin"]["levels"] == ["left", "right", "far"] and classes["bin"]["source"] == "enum"
    assert classes["bin"]["unseen"] == ["far"]
    assert classes["ok"]["levels"] == ["False", "True"] and classes["ok"]["source"] == "bool"
    assert classes["ok"]["counts"] == [sum(not p.ok for p in picks), sum(p.ok for p in picks)]


def test_an_undeclared_text_category_lists_its_levels_commonest_first(coverage, picks):
    split = coverage.payload["classes"]["split"]
    assert split["source"] == "data" and split["levels"] == ["dev", "holdout"]
    assert split["counts"] == [sum(p.split == "dev" for p in picks), sum(p.split == "holdout" for p in picks)]


def test_class_groups_add_back_up(coverage):
    split = coverage.payload["classes"]["split"]
    assert np.sum([split["groups"][g] for g in split["groups"]], axis=0).tolist() == split["counts"]


# ── missing values ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_none_and_nan_are_missing_never_a_value(coverage, picks):
    fields = {f["name"]: f for f in coverage.payload["fields"]}
    missing = sum(1 for p in picks if p.speed is None or (isinstance(p.speed, float) and math.isnan(p.speed)))
    assert missing > 0
    assert fields["speed"]["missing"] == missing and fields["speed"]["present"] == 240 - missing
    assert fields["speed"]["missing_pct"] == pytest.approx(100 * missing / 240)
    assert fields["angle_rad"]["missing"] == 0
    numbers = coverage.numbers
    assert numbers["complete_records_pct"] == pytest.approx(100 * (240 - missing) / 240)
    assert numbers["missing_pct"] == pytest.approx(100 * missing / (240 * len(fields)))


def test_a_mapping_with_a_missing_key_counts_it_missing():
    rows = [{"a": 1.0, "b": "x"}, {"a": 2.0}, {"b": "y", "c": {"d": 3}}]
    payload = analyze(rows).payload
    fields = {f["name"]: f for f in payload["fields"]}
    assert list(fields) == ["a", "b", "c.d"]
    assert (fields["a"]["missing"], fields["b"]["missing"], fields["c.d"]["missing"]) == (1, 1, 2)


# ── pairs: 2-D coverage ──────────────────────────────────────────────────────────────────────────────────────────────


def test_a_pair_plane_spans_exactly_both_ranges_and_matches_robot_msgs_binned(coverage, picks):
    pair = coverage.payload["pairs"][0]
    assert (pair["x"], pair["y"]) == ("angle_rad", "grip.width_mm")
    assert pair["x_edges"] == [-1.0, 1.0, 24] and pair["y_edges"] == [0.0, 80.0, 24] and pair["shape"] == [24, 24]
    points = [(p.angle_rad, p.grip.width_mm) for p in picks]
    axes = [list(np.linspace(-1.0, 1.0, 25)), list(np.linspace(0.0, 80.0, 25))]
    oracle = binned(points, axes)
    assert pair["visited_pct"] == pytest.approx(oracle.pct, abs=0.01)
    assert pair["outside"] == oracle.outside
    dense = np.zeros(24 * 24, int)
    for (i, j), count in oracle.cells.items():
        dense[i * 24 + j] = count
    assert pair["samples"] == dense.tolist()
    assert pair["sufficient_pct"] == pytest.approx(100 * np.count_nonzero(dense >= 10) / 576)


def test_default_pairs_are_every_pair_of_the_first_four_ranged_numbers():
    payload = analyze(made_up(60)).payload
    ranged = ["angle_rad", "grip.width_mm", "grip.force_n"]  # tcp, draws and speed have no declared range here
    assert [(p["x"], p["y"]) for p in payload["pairs"]] == [(ranged[0], ranged[1]), (ranged[0], ranged[2]),
                                                             (ranged[1], ranged[2])]


# ── is more data still adding coverage? ─────────────────────────────────────────────────────────────────────────────


def test_growth_rises_to_the_whole_set_and_matches_a_recount_of_each_prefix(coverage, picks):
    growth = coverage.payload["coverage"]["growth"]
    cells = coverage.payload["coverage"]["cells"]
    assert growth["records"][-1] == 240 and len(growth["records"]) <= 200
    assert all(b >= a for a, b in zip(growth["visited_pct"], growth["visited_pct"][1:]))
    assert growth["visited_pct"][-1] == pytest.approx(coverage.payload["coverage"]["visited_pct"])
    # the oracle: a prefix's own analysis, on the whole set's ranges and levels, visits that many cells
    ranges = {name: (h["low"], h["high"]) for name, h in coverage.payload["hist"].items()}
    choices = {name: c["levels"] for name, c in coverage.payload["classes"].items()}
    # WHY from 30 records: a shorter prefix has fields with no value yet (fewer cells) and few enough names that "name"
    # reads as a category, not an identifier; from 30 on the prefix's space is the whole set's, cell for cell
    checked = 0
    for k, pct in list(zip(growth["records"], growth["visited_pct"]))[::20]:
        if k < 30:
            continue
        prefix = analyze(picks[:k], ranges=ranges, choices=choices,
                         pairs=[("angle_rad", "grip.width_mm"), ("tcp[0]", "tcp[1]")])
        assert prefix.payload["coverage"]["cells"] == cells
        assert round(pct * cells / 100) == prefix.payload["coverage"]["visited"]
        checked += 1
    assert checked >= 5


def test_the_shuffled_band_brackets_its_median(coverage):
    # WHY the median, not the mean: 32 shuffles are discrete, and a mean can fall outside p10..p90 (29 equal and 3 low)
    shuffled = coverage.payload["coverage"]["growth"]["shuffled"]
    assert all(lo <= mid <= hi for lo, mid, hi in zip(shuffled["p10"], shuffled["median"], shuffled["p90"]))
    assert shuffled["median"][-1] == pytest.approx(coverage.payload["coverage"]["visited_pct"])
    assert shuffled["p10"][0] <= shuffled["p90"][0] < shuffled["median"][-1]


def test_new_cells_add_up_to_the_visited_cells_and_a_copy_adds_nothing():
    picks = made_up(80)
    picks = picks + [picks[3]]  # an exact copy of record 3, at the end
    payload = analyze(picks).payload
    records = payload["records"]
    assert sum(r["new_cells"] for r in records) == payload["coverage"]["visited"]
    assert records[-1]["new_cells"] == 0
    assert records[-1]["unique_cells"] == 0 and records[3]["unique_cells"] == 0  # two of them: neither is unique


def test_a_dataset_that_repeats_itself_has_stopped_adding():
    base = made_up(30)
    payload = analyze(base * 10, ranges={"draws": (0, 9)}).payload
    assert payload["coverage"]["last_tenth_new_pct"] == 0
    # every visited cell has at least two records, so Chao1 expects nothing new
    assert payload["coverage"]["ceiling_pct"] == pytest.approx(payload["coverage"]["visited_pct"])


def test_chao1_from_the_singletons_and_doubletons():
    payload = analyze(made_up(40)).payload
    cov = payload["coverage"]
    assert cov["ceiling_pct"] >= cov["visited_pct"]
    assert cov["ceiling_pct"] <= 100.0
    assert cov["chao1_cells"] >= cov["visited"]


# ── held-out support ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_held_out_records_outside_the_reference_cells_are_unsupported():
    dev = [Pick(name=f"d{i}", split="dev", angle_rad=-0.5 + 0.01 * (i % 10)) for i in range(50)]
    near = [Pick(name=f"n{i}", split="holdout", angle_rad=-0.5) for i in range(5)]  # inside dev's bins
    far = [Pick(name=f"f{i}", split="holdout", angle_rad=0.8) for i in range(5)]  # where dev never went
    payload = analyze(dev + near + far, split="split", pairs=[]).payload
    support = payload["support"]
    assert support["split"] == "split" and support["reference"] == "dev"
    holdout = support["levels"]["holdout"]
    assert (holdout["records"], holdout["unsupported"]) == (10, 5)
    assert holdout["unsupported_pct"] == pytest.approx(50.0)
    assert holdout["fields"]["angle_rad"] == pytest.approx(50.0)
    assert payload_numbers(payload)["unsupported_pct.holdout"] == pytest.approx(50.0)


def payload_numbers(payload) -> dict:
    return {n["key"]: n["value"] for n in payload["numbers"]}


# ── 3-D points ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_first_three_vector_is_the_3d_view_coloured_by_the_group(coverage, picks):
    points = coverage.payload["points3d"]
    assert points["fields"] == ["tcp[0]", "tcp[1]", "tcp[2]"]
    assert points["low"] == [-0.4, 0.0, -0.2] and points["high"] == [0.4, 0.6, 0.2]
    assert len(points["points"]) == 240
    assert points["points"][5] == pytest.approx(list(picks[5].tcp))
    assert points["color_by"] == "item"
    assert [points["levels"][c] for c in points["codes"][:5]] == [p.item for p in picks[:5]]


def test_without_a_vector_or_xyz_there_are_no_3d_points():
    rows = [{"a": float(i), "b": "x"} for i in range(10)]
    assert analyze(rows).payload["points3d"] is None
    assert analyze(rows, xyz=("a", "a", "a")).payload["points3d"]["fields"] == ["a", "a", "a"]


# ── robot_msgs messages are records too ─────────────────────────────────────────────────────────────────────────────


def test_robot_msgs_poses_flatten_into_their_fields():
    poses = [Pose(position=Point(x=0.1 * i, y=0.0, z=0.3)) for i in range(12)]
    payload = analyze(poses).payload
    names = [f["name"] for f in payload["fields"]]
    assert names[:3] == ["position.x", "position.y", "position.z"]
    assert "orientation.w" in names
    assert payload["hist"]["position.x"]["max"] == pytest.approx(1.1)


# ── the headline numbers ─────────────────────────────────────────────────────────────────────────────────────────────


def test_the_headline_numbers_are_the_contracts_and_all_finite(coverage):
    numbers = coverage.numbers
    assert NUMBER_KEYS <= set(numbers)
    assert set(numbers) - NUMBER_KEYS == {"unsupported_pct.holdout"}
    assert all(math.isfinite(v) for v in numbers.values())
    assert numbers["records"] == 240
    assert numbers["missing_classes"] == 2  # item's "box", bin's "far"
    assert numbers["class_imbalance_max"] == pytest.approx(
        max(c["imbalance_ratio"] for c in coverage.payload["classes"].values()))
    for entry in coverage.payload["numbers"]:
        assert set(entry) == {"key", "label", "value", "unit"} and entry["label"]


def test_fields_picks_and_orders_the_columns(picks):
    payload = analyze(picks, fields=["grip.width_mm", "item"]).payload
    assert [f["name"] for f in payload["fields"]] == ["grip.width_mm", "item"]


# ── refusals ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_refusals_name_what_is_wrong(picks):
    with pytest.raises(ValueError, match="no records"):
        analyze([])
    with pytest.raises(ValueError, match="'item' is a category"):
        analyze(picks, pairs=[("item", "angle_rad")])
    with pytest.raises(ValueError, match="no field 'nope'"):
        analyze(picks, group_by="nope")
    with pytest.raises(ValueError, match="'angle_rad' is a number"):
        analyze(picks, group_by="angle_rad")
    with pytest.raises(ValueError, match="'holdout2' is not a level of 'split'"):
        analyze(picks, split="split", reference="holdout2")
