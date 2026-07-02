# Contributing to pymol-mcp

Thanks for your interest! A few notes to make contributions smooth.

## Development setup

The server must run in a Python that can `import pymol2` (conda `pymol-open-source`):

```bash
conda env create -f env.yml
conda activate pymol-mcp
pip install -e ".[md,dev]"
pytest -q
```

## Ground rules

- **Never write to stdout.** It is the JSON-RPC channel. Use `logging` (configured to stderr) or `ctx` logging.
- **Never `from pymol import cmd`.** Always use the session's own `cmd` inside a `SESSION.call(lambda cmd: ...)`
  callable — PyMOL is thread-affine and only the worker thread may touch it.
- **Keep analysis in nanometres.** PyMOL coordinates are Ångström (×0.1 → nm); box vectors likewise.
- **Add a test.** New tools get a functional test (in-memory `Client`); anything touching the transport gets a
  subprocess/stdio test; numeric analysis gets a parity/regression anchor.

## Pull requests

1. Branch from `main`.
2. `pytest -q` must pass.
3. Describe the change and the milestone it belongs to (see the README roadmap).
