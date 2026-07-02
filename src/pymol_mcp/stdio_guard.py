"""Permanent stdout protection for the stdio JSON-RPC transport.

PyMOL's C core writes to file descriptor 1 (STDOUT_FILENO) directly. Over an MCP
stdio transport, fd 1 is the JSON-RPC channel to the client, so any PyMOL byte that
reaches it corrupts the protocol stream (dropped responses / client hangs).

We cannot selectively silence *only* PyMOL's writes to fd 1 -- they share the fd with
the transport. So we move the JSON-RPC channel OFF fd 1 and sink fd 1 to devnull, ONCE,
at process start, BEFORE PyMOL is ever imported/started:

    saved_fd = dup(1)            # a private handle onto the real client pipe
    sys.stdout -> saved_fd       # the MCP transport writes here (-> client)
    dup2(devnull, 1)             # PyMOL C chatter now sinks into devnull, forever

This is deliberately a permanent, one-time redirect -- never toggled per call -- because
toggling fd 1 while the transport writes on another thread is an unwinnable race.
"""

from __future__ import annotations

import os
import sys

_real_stdout = None


def protect_stdout():
    """Redirect fd 1 -> devnull permanently and expose the real client pipe as sys.stdout.

    Idempotent. Must be called before PyMOL is imported/launched. Returns the text
    stream (backed by a private dup of the original stdout) that the MCP stdio transport
    should use to talk to the client.
    """
    global _real_stdout
    if _real_stdout is not None:
        return _real_stdout

    try:
        sys.stdout.flush()
    except Exception:
        pass

    # Private dup of the original stdout (same open file description as the client pipe).
    saved_fd = os.dup(1)
    real = os.fdopen(saved_fd, "w", buffering=1, closefd=True)

    # Sink fd 1 into devnull so PyMOL's C-level printf can never reach the client.
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 1)
    os.close(devnull_fd)

    # The MCP transport and any intentional protocol writes go through sys.stdout -> saved_fd.
    sys.stdout = real
    _real_stdout = real
    return real
