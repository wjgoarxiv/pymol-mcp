"""CHILL+ contract and input-boundary tests."""

import os

import numpy as np
import pytest

from pymol_mcp.analysis import chill_plus as chill_module
from pymol_mcp.analysis.chill_plus import _classify_bond, _classify_bonds, _neighbor_indices, calculate_chill_plus
from pymol_mcp.analysis.geometry import Cell
from pymol_mcp.analysis.gro import parse_gro

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
GRO_SII = os.path.join(_FIX, "hydrate_sII.gro")


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_chill_plus_matches_frozen_sii_contract():
    waters, _, box = parse_gro(GRO_SII)

    result = calculate_chill_plus(waters, Cell.from_box(box))

    assert result["algorithm"] == "CHILL+"
    assert result["cutoff_nm"] == 0.35
    assert result["n_water"] == 1088
    assert result["class_counts"] == [0, 0, 0, 0, 1088, 0]
    assert result["fractions"] == [0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert len(result["per_atom_class"]) == 1088
    assert set(result["per_atom_class"]) == {4}
    assert len(result["edges"]) == 2176
    assert [tuple(edge) for edge in result["edges"]] == sorted({tuple(edge) for edge in result["edges"]})


def test_chill_plus_keeps_overcoordinated_triclinic_neighbors():
    cell = Cell.from_box([2.0, 2.0, 2.0, 0.5, 0.0, 0.0])
    oxygen = np.array(
        [
            [0.10, 0.10, 0.10],
            [0.55, 1.90, 0.10],
            [0.30, 0.10, 0.10],
            [0.10, 0.30, 0.10],
            [0.10, 0.10, 0.30],
            [1.90, 0.10, 0.10],
        ]
    )
    waters = [(p, p, p) for p in oxygen]

    result = calculate_chill_plus(waters, cell)

    assert [0, 1] in result["edges"]
    assert result["neighbor_counts"][0] == 5
    assert result["per_atom_class"][0] == 0


def test_chill_plus_uses_the_reference_cell_distance_for_triclinic_cutoffs():
    cell = Cell.from_box(
        [
            1.3035766346504567,
            0.6366072397234004,
            0.674061130438492,
            0.013123139123049323,
            0.03546231556583548,
            -0.18421181618092583,
        ]
    )
    waters = [
        (np.array([0.9963948052563278, 0.1776607376991751, 0.17445036849305864]),) * 3,
        (np.array([-0.23595633447411635, 0.47720959341803637, 0.28893055168286635]),) * 3,
    ]

    result = calculate_chill_plus(waters, cell)

    assert cell.distance(waters[0][0], waters[1][0]) > 0.35
    assert result["neighbor_counts"] == [0, 0]
    assert result["edges"] == []


def test_chill_plus_uses_the_cell_list_for_an_exact_orthorhombic_cell(monkeypatch):
    called = []

    def fake_cell_list(*args):
        called.append(args)
        return [[], []]

    monkeypatch.setattr(chill_module, "_neighbor_indices_cell_list", fake_cell_list, raising=False)
    water = (np.zeros(3), np.zeros(3), np.zeros(3))
    far_water = (np.array([0.8, 0.8, 0.8]),) * 3

    calculate_chill_plus([water, far_water], Cell.from_box([1.0, 1.0, 1.0]))

    assert called, "an exact orthorhombic cell must use the bounded-memory cell-list path"


def test_chill_plus_treats_angle_derived_roundoff_as_orthorhombic(monkeypatch):
    called = []

    def fake_cell_list(*args):
        called.append(args)
        return [[], []]

    monkeypatch.setattr(chill_module, "_neighbor_indices_cell_list", fake_cell_list)
    water = (np.zeros(3), np.zeros(3), np.zeros(3))
    far_water = (np.array([0.8, 0.8, 0.8]),) * 3

    calculate_chill_plus([water, far_water], Cell.from_lengths_angles(1.0, 1.0, 1.0, 90.0, 90.0, 90.0))

    assert called, "90-degree angle conversion roundoff must not disable the fast path"


def test_chill_plus_keeps_triclinic_cells_on_the_bruteforce_fallback(monkeypatch):
    called = []

    def fail_cell_list(*args):
        called.append(args)
        raise AssertionError("triclinic cells must not use the orthorhombic cell-list path")

    monkeypatch.setattr(chill_module, "_neighbor_indices_cell_list", fail_cell_list)
    waters = [(np.zeros(3),) * 3, (np.array([0.2, 0.0, 0.0]),) * 3]

    calculate_chill_plus(waters, Cell.from_box([2.0, 2.0, 2.0, 0.01, 0.0, 0.0]))

    assert called == []


@pytest.mark.parametrize("tilt", [1e-12, 1e-14])
def test_chill_plus_keeps_a_small_real_tilt_on_the_fallback(monkeypatch, tilt):
    called = []

    def fail_cell_list(*args):
        called.append(args)
        raise AssertionError("a real tilt must use the canonical fallback")

    monkeypatch.setattr(chill_module, "_neighbor_indices_cell_list", fail_cell_list)
    waters = [(np.zeros(3),) * 3, (np.array([0.2, 0.0, 0.0]),) * 3]

    calculate_chill_plus(waters, Cell.from_box([2.0, 2.0, 2.0, tilt, 0.0, 0.0]))

    assert called == []


def _bruteforce_neighbor_oracle(oxygen, cell, cutoff):
    expected = []
    for i, center in enumerate(oxygen):
        candidates = []
        for j, other in enumerate(oxygen):
            if i == j:
                continue
            distance_sq = cell.distance(center, other) ** 2
            if distance_sq <= cutoff**2:
                candidates.append((distance_sq, j))
        expected.append([j for _, j in sorted(candidates, key=lambda pair: (pair[0], pair[1]))])
    return expected


@pytest.mark.parametrize("side", [0.6, 0.7, 1.4])
def test_chill_plus_cell_list_matches_independent_oracle_across_bin_sizes(side):
    rng = np.random.default_rng(20260815 + int(side * 100))
    oxygen = rng.uniform(-0.15, side + 0.15, size=(72, 3))
    waters = [(position, position, position) for position in oxygen]
    cell = Cell.from_box([side, side, side])
    expected = _bruteforce_neighbor_oracle(oxygen, cell, 0.35)

    result = calculate_chill_plus(waters, cell)

    assert result["neighbor_counts"] == [len(indices) for indices in expected]
    assert result["edges"] == sorted([[i, j] for i, indices in enumerate(expected) for j in indices if i < j])


def test_chill_plus_keeps_an_exact_cutoff_pair():
    oxygen = [np.array([0.0, 0.0, 0.0]), np.array([0.35, 0.0, 0.0])]
    waters = [(position, position, position) for position in oxygen]

    result = calculate_chill_plus(waters, Cell.from_box([2.0, 2.0, 2.0]))

    assert result["neighbor_counts"] == [1, 1]
    assert result["edges"] == [[0, 1]]


def test_chill_plus_handles_a_tiny_positive_cutoff_without_overflow():
    waters = [(np.zeros(3),) * 3, (np.array([0.1, 0.0, 0.0]),) * 3]

    result = calculate_chill_plus(waters, Cell.from_box([1.0, 1.0, 1.0]), 1e-320)

    assert result["neighbor_counts"] == [0, 0]
    assert result["edges"] == []


def test_chill_plus_orders_equal_distance_neighbors_by_input_index():
    oxygen = [
        np.array([0.0, 0.0, 0.0]),
        np.array([0.2, 0.0, 0.0]),
        np.array([-0.2, 0.0, 0.0]),
    ]

    neighbours = _neighbor_indices(oxygen, Cell.from_box([2.0, 2.0, 2.0]), 0.35)

    assert neighbours[0][:2] == [1, 2]


@pytest.mark.parametrize(
    ("correlation", "expected"),
    [(-0.800001, "staggered"), (-0.8, None), (-0.35, "eclipsed"), (0.25, "eclipsed"), (0.250001, None)],
)
def test_chill_plus_bond_thresholds(correlation, expected):
    assert _classify_bond(correlation) == expected


@pytest.mark.parametrize(
    ("n_staggered", "n_eclipsed", "expected"),
    [(4, 0, 2), (3, 1, 1), (0, 4, 4), (0, 3, 5), (2, 0, 3), (3, 0, 3), (0, 0, 0)],
)
def test_chill_plus_class_mapping(n_staggered, n_eclipsed, expected):
    assert _classify_bonds(n_staggered, n_eclipsed) == expected


@pytest.mark.parametrize(
    ("waters", "cell", "cutoff"),
    [
        ([("bad", (0, 0, 0), (0, 0, 0))], Cell.from_box([1.0, 1.0, 1.0]), 0.35),
        ([(np.array([np.nan, 0.0, 0.0]),) * 3], Cell.from_box([1.0, 1.0, 1.0]), 0.35),
        ([(np.zeros(2),) * 3], Cell.from_box([1.0, 1.0, 1.0]), 0.35),
        ([(np.zeros(3),) * 3], None, 0.35),
    ],
)
def test_chill_plus_rejects_invalid_inputs(waters, cell, cutoff):
    with pytest.raises(ValueError):
        calculate_chill_plus(waters, cell, cutoff)


def test_chill_plus_allows_empty_input_with_zero_counts():
    result = calculate_chill_plus([], Cell.from_box([1.0, 1.0, 1.0]))

    assert result["n_water"] == 0
    assert result["class_counts"] == [0, 0, 0, 0, 0, 0]
    assert result["fractions"] == [0.0] * 6
    assert result["edges"] == []


def test_chill_plus_rejects_nonpositive_cutoff():
    water = (np.zeros(3), np.zeros(3), np.zeros(3))

    with pytest.raises(ValueError, match="cutoff"):
        calculate_chill_plus([water], Cell.from_box([1.0, 1.0, 1.0]), 0.0)


def test_chill_plus_rejects_a_noniterable_water_collection():
    with pytest.raises(ValueError, match="waters"):
        calculate_chill_plus(1, Cell.from_box([1.0, 1.0, 1.0]))
