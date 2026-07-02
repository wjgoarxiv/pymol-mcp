"""Functional tests via FastMCP's in-memory Client (fast; bypasses stdio transport).

These verify tool behavior. They CANNOT detect stdout corruption -- that is what the
subprocess test in test_stdio_purity.py exists for.
"""

import asyncio

from conftest import write_minimal_pdb
from fastmcp import Client

from pymol_mcp.server import mcp


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def test_load_list_and_info(tmp_path):
    pdb = write_minimal_pdb(tmp_path)

    async def scenario():
        async with Client(mcp) as client:
            res = await client.call_tool("load_structure", {"path": pdb})
            data = res.data
            assert data["n_atoms"] == 3, data
            obj = data["object"]

            objs = (await client.call_tool("list_objects", {})).data
            assert obj in objs

            info = (await client.call_tool("get_object_info", {"name": obj})).data
            assert info["n_atoms"] == 3
            return True

    assert _run(scenario())


def test_render_returns_image(tmp_path):
    pdb = write_minimal_pdb(tmp_path)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": pdb})
            res = await client.call_tool("render_image", {"width": 200, "height": 150})
            # An Image return arrives as image content on the result.
            assert res.content, "no content returned"
            blob = res.content[0]
            mime = getattr(blob, "mimeType", "") or ""
            assert "image" in mime or hasattr(blob, "data"), f"not an image block: {blob!r}"
            return True

    assert _run(scenario())


def test_code_exec_disabled_by_default(tmp_path):
    async def scenario():
        async with Client(mcp) as client:
            res = await client.call_tool("run_python", {"code": "result = 1+1"}, raise_on_error=False)
            assert res.is_error, "run_python should be disabled without the env flag"
            return True

    assert _run(scenario())
