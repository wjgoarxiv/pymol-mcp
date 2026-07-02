"""Entry point: `python -m pymol_mcp` (registered as the `pymol-mcp` console script).

Order matters: stdout MUST be protected before PyMOL is ever launched.
"""

from __future__ import annotations


def main() -> None:
    # 1) Redirect fd 1 -> devnull and move the JSON-RPC channel onto a private fd,
    #    BEFORE the PyMOL worker thread (and thus pymol2) starts.
    from .stdio_guard import protect_stdout

    protect_stdout()

    # 2) Import + run the server on the default stdio transport.
    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
