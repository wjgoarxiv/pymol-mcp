"""M3 end-to-end: load a hydrate .gro into PyMOL and run domain tools through the MCP layer.

Exercises the full path: PyMOL load -> get_symmetry box -> Angstrom->nm extraction -> analysis.
"""

import asyncio
import os

import pytest
from fastmcp import Client
from pymol.cgo import COLOR, CYLINDER, SPHERE

from pymol_mcp.server import SESSION, mcp

_FIX = os.path.dirname(__file__)
GRO_SI = os.path.join(_FIX, "fixtures", "hydrate_sI.gro")
GRO_SII = os.path.join(_FIX, "fixtures", "hydrate_sII.gro")
GRO_SH = os.path.join(_FIX, "fixtures", "hydrate_sH.gro")


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=180))


def _cgo_radii(data):
    spheres = []
    cylinders = []
    index = 0
    while index < len(data):
        opcode = data[index]
        if opcode == COLOR:
            index += 4
        elif opcode == SPHERE:
            spheres.append(data[index + 4])
            index += 5
        elif opcode == CYLINDER:
            cylinders.append(data[index + 7])
            index += 14
        else:
            raise AssertionError(f"unexpected CGO opcode at {index}: {opcode}")
    return spheres, cylinders


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
def test_mark_cages_uses_default_and_explicit_geometry():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "hyd"})
            captured = []

            def install_capture(cmd):
                original = cmd.load_cgo

                def load_cgo(data, name, *args, **kwargs):
                    captured.append(list(data))
                    return original(data, name, *args, **kwargs)

                cmd.load_cgo = load_cgo
                return original

            original = SESSION.call(install_capture)
            try:
                await client.call_tool("mark_cages", {"selection": "hyd"})
                await client.call_tool(
                    "mark_cages",
                    {"selection": "hyd", "edge_radius": 0.12, "vertex_radius": 0.32},
                )
            finally:
                SESSION.call(lambda cmd: setattr(cmd, "load_cgo", original))

            default_spheres, default_cylinders = _cgo_radii(captured[0])
            override_spheres, override_cylinders = _cgo_radii(captured[1])
            assert set(default_spheres) == {0.38}
            assert set(default_cylinders) == {0.18}
            assert set(override_spheres) == {0.32}
            assert set(override_cylinders) == {0.12}
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

            marked = (
                await client.call_tool(
                    "mark_cages",
                    {"selection": "hyd", "edge_radius": 0.12, "vertex_radius": 0.32},
                )
            ).data
            assert marked["object"] == "cages", marked
            assert marked["n_cages"] == 192, marked
            assert marked["drawn"].get("5^12") == 128 and marked["drawn"].get("5^12 6^4") == 64, marked
            objs = (await client.call_tool("list_objects", {})).data
            assert "cages" in objs, objs
            info = (await client.call_tool("get_object_info", {"name": "cages"})).data
            assert info["object"] == "cages", info
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_chill_plus_and_visualization_via_mcp():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "hyd"})
            result = (await client.call_tool("chill_plus", {"selection": "hyd"})).data
            assert result["algorithm"] == "CHILL+", result
            assert result["class_counts"] == [0, 0, 0, 0, 1088, 0], result
            assert result["n_water"] == 1088, result
            assert result["state"] == 1, result
            assert len(result["edges"]) == 2176, result

            marked = (await client.call_tool("mark_chill_plus", {"selection": "hyd"})).data
            assert marked["object"] == "chill_plus", marked
            assert marked["n_edges"] == 2176, marked
            assert marked["state"] == 1, marked
            assert marked["drawn_by_class"] == {"4": 2176}, marked
            rendered = await client.call_tool("render_image", {"selection": "hyd", "width": 256, "height": 256})
            assert rendered.content and rendered.content[0].type == "image", rendered
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_mark_chill_plus_preserves_a_molecule_name_collision():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "chill_plus"})
            result = await client.call_tool(
                "mark_chill_plus",
                {"selection": "chill_plus"},
                raise_on_error=False,
            )
            assert result.is_error
            info = (await client.call_tool("get_object_info", {"name": "chill_plus"})).data
            assert info["n_atoms"] == 3264, info
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SII), reason="sII reference .gro not present")
def test_chill_plus_rejects_an_invalid_periodic_box():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": GRO_SII, "object_name": "hyd"})
            result = await client.call_tool(
                "chill_plus",
                {"selection": "hyd", "box": [1.0, 2.0]},
                raise_on_error=False,
            )
            assert result.is_error
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SI), reason="sI reference .gro not present")
def test_identify_cages_and_render_sI():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("reset_session", {})
            load = (await client.call_tool("load_structure", {"path": GRO_SI, "object_name": "sI"})).data
            assert load["n_atoms"] == 1472, load
            res = (await client.call_tool("identify_cages", {"selection": "sI"})).data
            assert res["structure_type"] == "sI", res
            assert res["counts"].get("5^12") == 16, res
            assert res["counts"].get("5^12 6^2") == 48, res
            marked = (await client.call_tool("mark_cages", {"selection": "sI"})).data
            assert marked["object"] == "cages", marked
            assert marked["n_cages"] == 64, marked
            rendered = await client.call_tool("render_image", {"selection": "all", "width": 256, "height": 256})
            assert rendered.content and rendered.content[0].type == "image", rendered
            return True

    assert _run(scenario())


@pytest.mark.skipif(not os.path.exists(GRO_SH), reason="sH reference .gro not present")
def test_identify_cages_and_render_sH():
    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("reset_session", {})
            load = (await client.call_tool("load_structure", {"path": GRO_SH, "object_name": "sH"})).data
            assert load["n_atoms"] == 1632, load
            res = (await client.call_tool("identify_cages", {"selection": "sH"})).data
            assert res["structure_type"] == "sH", res
            assert res["counts"].get("5^12") == 48, res
            assert res["counts"].get("4^3 5^6 6^3") == 32, res
            assert res["counts"].get("5^12 6^8") == 16, res
            marked = (await client.call_tool("mark_cages", {"selection": "sH"})).data
            assert marked["n_cages"] == 96, marked
            filtered = (
                await client.call_tool(
                    "mark_cages",
                    {"selection": "sH", "cage_types": ["5^12 6^8"]},
                )
            ).data
            assert filtered["n_cages"] == 16, filtered
            rendered = await client.call_tool("render_image", {"selection": "all", "width": 256, "height": 256})
            assert rendered.content and rendered.content[0].type == "image", rendered
            return True

    assert _run(scenario())
