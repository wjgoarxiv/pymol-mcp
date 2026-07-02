"""M3 end-to-end: load a hydrate .gro into PyMOL and run domain tools through the MCP layer.

Exercises the full path: PyMOL load -> get_symmetry box -> Angstrom->nm extraction -> analysis.
"""

import asyncio
import os

import pytest
from fastmcp import Client

from pymol_mcp.server import mcp

GRO_SII = os.path.join(os.path.dirname(__file__), "fixtures", "hydrate_sII.gro")


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=180))


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_order_parameter_and_hbond_via_mcp():
    async def scenario():
        async with Client(mcp) as client:
            load = (await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "hyd"})).data
            assert load["n_atoms"] == 1088 * 3, load

            f4 = (await client.call_tool("order_parameter", {"selection": "hyd", "kind": "f4"})).data
            assert f4["parameter"] == "F4"
            assert 0.85 <= f4["value"] <= 0.98, f4        # matches the direct-parse full-system value

            f3 = (await client.call_tool("order_parameter", {"selection": "hyd", "kind": "f3"})).data
            assert f3["hydrate_like"] is True, f3

            hb = (await client.call_tool("hbond_network", {"selection": "hyd"})).data
            assert 3.5 <= hb["mean_coordination"] <= 4.05, hb
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_identify_cages_via_mcp():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "hyd"})
            res = (await client.call_tool("identify_cages", {"selection": "hyd"})).data
            assert res["structure_type"] == "sII", res
            assert res["counts"].get("5^12") == 128, res
            assert res["counts"].get("5^12 6^4") == 64, res

            marked = (await client.call_tool("mark_cages", {"selection": "hyd"})).data
            assert marked["object"] == "cages", marked
            assert marked["n_cages"] == 192, marked
            assert marked["drawn"].get("5^12") == 128 and marked["drawn"].get("5^12 6^4") == 64, marked
            return True

    assert _run(scenario())
