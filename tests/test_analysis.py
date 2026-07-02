"""M3 domain analysis: numeric parity + physical sanity for the ported analysis algorithms."""

import math
import os

import numpy as np
import pytest

from pymol_mcp.analysis.cage import classify_structure, identify_cages
from pymol_mcp.analysis.geometry import Cell
from pymol_mcp.analysis.gro import parse_gro
from pymol_mcp.analysis.hbond import build_hbond_network
from pymol_mcp.analysis.order_params import calculate_f3, calculate_f4

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
GRO_SII = os.path.join(_FIX, "hydrate_sII.gro")
GRO_SI = os.path.join(_FIX, "hydrate_sI.gro")
GRO_SH = os.path.join(_FIX, "hydrate_sH.gro")


def test_mic_triclinic():
    """Fractional-coordinate MIC on a restricted-triclinic cell (reference geometry test)."""
    cell = Cell.from_box([2.0, 2.0, 2.0, 0.5, 0.25, 0.4])  # lx,ly,lz,xy,xz,yz
    out = cell.mic(np.array([1.30, 0.0, 0.0]))
    assert np.allclose(out, [-0.70, 0.0, 0.0], atol=1e-6), out


def test_dihedral_sign_uses_atan2():
    """A signed dihedral must distinguish +phi from -phi (atan2, not acos)."""
    cell = Cell.from_box([10.0, 10.0, 10.0])
    p1 = np.array([0.0, 1.0, 0.0])
    p2 = np.array([0.0, 0.0, 0.0])
    p3 = np.array([1.0, 0.0, 0.0])
    p4a = np.array([1.0, 0.0, 1.0])
    p4b = np.array([1.0, 0.0, -1.0])
    da = cell.dihedral(p1, p2, p3, p4a)
    db = cell.dihedral(p1, p2, p3, p4b)
    assert math.isclose(da, -db, abs_tol=1e-9) and abs(da) > 1e-6, (da, db)


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_f4_parity_sII_ground_truth():
    """F4 over the first 10 waters of the sII fixture == 0.926698 (cross-validated vs the reference impl / F4SPC)."""
    waters, _, box = parse_gro(GRO_SII)
    cell = Cell.from_box(box)
    f4, npairs = calculate_f4(waters[:10], cell, 0.35)
    assert npairs == 12
    assert math.isclose(f4, 0.926698, abs_tol=1e-5), f4


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_f4_physical_and_f3_hydrate_like_sII():
    waters, _, box = parse_gro(GRO_SII)
    cell = Cell.from_box(box)
    f4_all, _ = calculate_f4(waters, cell, 0.35)
    assert 0.85 <= f4_all <= 0.98, f4_all          # static sII crystal, near-perfect
    f3_all = calculate_f3(waters, cell, 0.35)
    assert f3_all <= 0.04, f3_all                  # hydrate-like


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_hbond_tetrahedral_sII():
    waters, _, box = parse_gro(GRO_SII)
    cell = Cell.from_box(box)
    adj = build_hbond_network(waters, cell)
    degrees = [len(a) for a in adj]
    assert 3.5 <= (sum(degrees) / len(degrees)) <= 4.05  # ~4-coordinate framework
    # symmetric adjacency
    assert all(i in adj[j] for i in range(len(adj)) for j in adj[i])


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_cage_perception_sII():
    """TRACE cage perception on structure II: 128x 5^12 + 64x 5^12 6^4 (exact 2:1)."""
    waters, _, box = parse_gro(GRO_SII)
    res = identify_cages(waters, Cell.from_box(box))
    assert res["counts"].get("5^12") == 128, res["counts"]
    assert res["counts"].get("5^12 6^4") == 64, res["counts"]
    assert classify_structure(res["counts"]) == "sII"


@pytest.mark.skipif(not os.path.exists(GRO_SI), reason="sI reference .gro not present")
def test_cage_perception_sI():
    """TRACE cage perception on structure I: 16x 5^12 + 48x 5^12 6^2 (46-H2O unit cell)."""
    waters, _, box = parse_gro(GRO_SI)
    res = identify_cages(waters, Cell.from_box(box))
    assert res["counts"].get("5^12") == 16, res["counts"]
    assert res["counts"].get("5^12 6^2") == 48, res["counts"]
    assert classify_structure(res["counts"]) == "sI"


@pytest.mark.skipif(not os.path.exists(GRO_SH), reason="sH reference .gro not present")
def test_f4_regression_sH():
    """Second anchor (implementation-pinned regression guard on the sH framework)."""
    waters, _, box = parse_gro(GRO_SH)
    cell = Cell.from_box(box)
    f4, npairs = calculate_f4(waters[:10], cell, 0.35)
    assert npairs == 7
    assert math.isclose(f4, 0.847510, abs_tol=1e-5), f4
