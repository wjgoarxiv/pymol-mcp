"""Functional tests via FastMCP's in-memory Client (fast; bypasses stdio transport).

These verify tool behavior. They CANNOT detect stdout corruption -- that is what the
subprocess test in test_stdio_purity.py exists for.
"""

import asyncio

from conftest import write_minimal_pdb
from fastmcp import Client

from pymol_mcp.server import SESSION, mcp

_RAY_SETTING_NAMES = (
    "ray_trace_mode",
    "ray_trace_color",
    "antialias",
    "ray_opaque_background",
    "ray_default_renderer",
    "ray_trace_fog",
)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def _ray_settings():
    return SESSION.call(lambda cmd: {name: cmd.get(name) for name in _RAY_SETTING_NAMES})


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


def test_render_supports_pymolwiki_color_style_and_restores_settings(tmp_path):
    pdb = write_minimal_pdb(tmp_path)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": pdb})
            before = _ray_settings()
            res = await client.call_tool(
                "render_image",
                {"ray_style": "pymolwiki_color", "width": 200, "height": 150},
            )
            assert res.content, "styled render returned no content"
            after = _ray_settings()
            assert after == before
            return True

    assert _run(scenario())


def test_render_defaults_to_pymolwiki_outline_style(tmp_path):
    pdb = write_minimal_pdb(tmp_path)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": pdb})
            tools = await client.list_tools()
            render = next(tool for tool in tools if tool.name == "render_image")
            assert render.inputSchema["properties"]["ray_style"]["default"] == "pymolwiki_outline"
            result = await client.call_tool("render_image", {"width": 200, "height": 150})
            assert result.content, "default styled render returned no content"
            explicit_default = await client.call_tool(
                "render_image",
                {"ray_style": "default", "width": 200, "height": 150},
            )
            assert explicit_default.content, "explicit default render returned no content"
            return True

    assert _run(scenario())


def test_render_rejects_unknown_ray_style(tmp_path):
    pdb = write_minimal_pdb(tmp_path)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": pdb})
            tools = await client.list_tools()
            render = next(tool for tool in tools if tool.name == "render_image")
            assert render.inputSchema["properties"]["ray_style"]["enum"] == [
                "default",
                "pymolwiki_outline",
                "pymolwiki_bw",
                "pymolwiki_color",
            ]
            result = await client.call_tool(
                "render_image",
                {"ray_style": "not_a_style", "width": 200, "height": 150},
                raise_on_error=False,
            )
            assert result.is_error
            return True

    assert _run(scenario())


def test_render_restores_ray_style_after_render_error(tmp_path, monkeypatch):
    import pymol_mcp.server as server

    pdb = write_minimal_pdb(tmp_path)

    def fail_mkstemp(*args, **kwargs):
        raise OSError("forced temporary-file failure")

    monkeypatch.setattr(server.tempfile, "mkstemp", fail_mkstemp)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool("load_structure", {"path": pdb})
            before = _ray_settings()
            result = await client.call_tool(
                "render_image",
                {"ray_style": "pymolwiki_color", "width": 200, "height": 150},
                raise_on_error=False,
            )
            assert result.is_error
            after = _ray_settings()
            assert after == before
            return True

    assert _run(scenario())


def test_mark_cages_defaults_use_bold_geometry():
    async def scenario():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            mark = next(tool for tool in tools if tool.name == "mark_cages")
            properties = mark.inputSchema["properties"]
            assert properties["edge_radius"]["default"] == 0.18
            assert properties["vertex_radius"]["default"] == 0.38
            return True

    assert _run(scenario())


def test_code_exec_disabled_by_default(tmp_path):
    async def scenario():
        async with Client(mcp) as client:
            res = await client.call_tool("run_python", {"code": "result = 1+1"}, raise_on_error=False)
            assert res.is_error, "run_python should be disabled without the env flag"
            return True

    assert _run(scenario())
