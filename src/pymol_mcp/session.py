"""PyMOLSession -- a headless pymol2 instance owned by ONE dedicated worker thread.

PyMOL's ``cmd`` (and especially its ray/GL state) is thread-affine: it must be created
and driven from the same thread. FastMCP runs sync tools in a threadpool, so we cannot
just guard the global ``cmd`` with a lock -- we would still touch PyMOL from arbitrary
threads. Instead every operation is marshalled as a callable onto a single worker thread
that both creates and drives the instance, via a request queue.

Tools never import the global ``from pymol import cmd``; they receive *this instance's*
own ``cmd`` inside the callable they pass to :meth:`call`.
"""

from __future__ import annotations

import queue
import threading


class PyMOLSession:
    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._pymol = None
        self._cmd = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None

    # -- lifecycle -----------------------------------------------------------
    def start(self, timeout: float = 60.0) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="pymol-worker", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("PyMOL worker thread did not become ready in time")
        if self._start_error is not None:
            raise RuntimeError(f"PyMOL worker failed to start: {self._start_error!r}")

    def _loop(self) -> None:
        try:
            import pymol2

            self._pymol = pymol2.PyMOL()
            self._pymol.start()
            self._cmd = self._pymol.cmd
            self._suppress()
        except BaseException as e:  # pragma: no cover - startup failure path
            self._start_error = e
            self._ready.set()
            return

        self._ready.set()
        while True:
            item = self._q.get()
            if item is None:
                break
            fn, box = item
            try:
                box["result"] = fn(self._cmd)
            except BaseException as e:
                box["error"] = e
            finally:
                box["done"].set()

        try:
            self._pymol.stop()
        except Exception:
            pass

    def _suppress(self) -> None:
        """Silence PyMOL's own feedback channels (belt-and-suspenders with the fd redirect)."""
        try:
            self._cmd.feedback("disable", "all", "everything")
        except Exception:
            pass

    # -- dispatch ------------------------------------------------------------
    def call(self, fn, timeout: float = 120.0):
        """Run ``fn(cmd)`` on the worker thread and return its result (re-raising errors)."""
        if self._cmd is None:
            raise RuntimeError("PyMOL session is not started")
        box: dict = {"done": threading.Event()}
        self._q.put((fn, box))
        if not box["done"].wait(timeout):
            raise TimeoutError(f"PyMOL operation exceeded {timeout:.0f}s")
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def reinitialize(self) -> None:
        """Reset PyMOL and RE-APPLY the suppression bundle (reinitialize re-enables chatter)."""
        self.call(lambda cmd: cmd.reinitialize())
        self.call(lambda cmd: cmd.feedback("disable", "all", "everything"))

    def stop(self) -> None:
        if self._thread is None:
            return
        self._q.put(None)
        self._thread.join(timeout=10)
        self._thread = None
        self._cmd = None
