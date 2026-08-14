"""CHILL+ contract and input-boundary tests."""

import os

import numpy as np
import pytest

from pymol_mcp.analysis.chill_plus import _classify_bond, _classify_bonds, calculate_chill_plus
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
