"""M2: GROMACS/LAMMPS trajectory ingestion (native load_traj + MDAnalysis injection)."""

import asyncio
import os

import pytest
from fastmcp import Client

from pymol_mcp.server import mcp

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
GRO = os.path.join(_FIX, "hydrate_sI.gro")
LAMMPS = os.path.join(_FIX, "lammps_water.lammpstrj")


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=180))


@pytest.fixture
def xtc(tmp_path):
    mda = pytest.importorskip("MDAnalysis")
    import numpy as np

    if not os.path.exists(GRO):
        pytest.skip("reference .gro not present")
    u = mda.Universe(GRO)
    out = str(tmp_path / "traj.xtc")
    with mda.Writer(out, n_atoms=u.atoms.n_atoms) as w:
        base = u.atoms.positions.copy()
        for i in range(4):
            u.atoms.positions = base + np.array([i * 0.5, 0, 0], dtype=np.float32)
            w.write(u.atoms)
    return out


def test_native_load_trajectory(xtc):
    async def scenario():
        async with Client(mcp) as client:
            r = (await client.call_tool(
                "load_trajectory",
                {"structure_path": GRO, "trajectory_path": xtc, "object_name": "t"},
            )).data
            assert r["n_states"] == 4, r
            assert r["n_atoms"] == 1472, r
            return True

    assert _run(scenario())


def test_mda_coordinate_injection(xtc):
    async def scenario():
        async with Client(mcp) as client:
            r = (await client.call_tool(
                "load_trajectory_mda",
                {"trajectory_path": xtc, "topology_path": GRO, "object_name": "m"},
            )).data
            assert r["frames_loaded"] == 4, r
            assert r["n_states"] == 4, r
            return True

    assert _run(scenario())


def test_lammps_dump_reads(tmp_path):
    """LAMMPS dump ingest via MDAnalysis (single-file topology)."""
    if not os.path.exists(LAMMPS):
        pytest.skip("reference LAMMPS dump not present")
    pytest.importorskip("MDAnalysis")

    async def scenario():
        async with Client(mcp) as client:
            r = (await client.call_tool(
                "load_trajectory_mda",
                {"trajectory_path": LAMMPS, "trajectory_format": "LAMMPSDUMP", "object_name": "lmp"},
            )).data
            assert r["n_atoms"] == 13800, r
            assert r["n_states"] >= 1, r
            return True

    assert _run(scenario())
