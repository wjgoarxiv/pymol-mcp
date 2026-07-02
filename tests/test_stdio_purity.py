"""GATE B: prove PyMOL's stdout chatter never corrupts the stdio JSON-RPC stream.

This spawns the server as a REAL child process over stdin/stdout and drives it with the
official MCP stdio client. Loading a structure and ray-tracing make PyMOL emit copious
fd-1 output; if the permanent redirect in stdio_guard.py failed, the JSON-RPC stream would
desync and these calls would raise or hang. A clean multi-call round-trip (including
concurrent calls) is the purity proof.

The in-memory Client CANNOT catch this class of bug -- it bypasses the stdio transport.
"""

import asyncio
import os
import sys

from conftest import write_minimal_pdb
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=180))


def test_stdio_stream_stays_clean_under_load(tmp_path):
    pdb = write_minimal_pdb(tmp_path)
    params = StdioServerParameters(
        command=sys.executable,          # the conda `viz` python running pytest
        args=["-m", "pymol_mcp"],
        env={**os.environ},
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = {t.name for t in (await session.list_tools()).tools}
                assert {"load_structure", "render_image", "list_objects"} <= tools, tools

                # Load: triggers PyMOL's ObjectMolecule / loader chatter on fd 1.
                load = await session.call_tool("load_structure", {"path": pdb})
                assert not load.isError, load

                # Fire several calls CONCURRENTLY, incl. a ray-trace (heavy fd-1 output).
                results = await asyncio.gather(
                    session.call_tool("render_image", {"width": 160, "height": 120}),
                    session.call_tool("list_objects", {}),
                    session.call_tool("render_image", {"width": 120, "height": 90}),
                )
                for r in results:
                    assert not r.isError, r

                # Confirm the render actually returned image content over the wire.
                img = results[0]
                assert any(getattr(c, "type", "") == "image" or hasattr(c, "data") for c in img.content), img.content
                return True

    assert _run(scenario())
