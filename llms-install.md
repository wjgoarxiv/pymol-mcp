# Installing pymol-mcp (guide for AI agents / one-shot setup)

`pymol-mcp` is a **headless PyMOL MCP server**. It MUST run in a Python that can `import pymol2`,
and PyMOL open-source is a **conda** package (it is *not* cleanly pip-installable). Follow these
steps exactly; do not try `pip install pymol-mcp` on its own — it will install and then fail at
`import pymol2`.

## 1. Create a conda env with PyMOL

```bash
conda create -y -n pymol-mcp -c conda-forge "python>=3.11" pymol-open-source numpy scipy
```

(If `conda` is unavailable, install Miniforge first: https://github.com/conda-forge/miniforge)

## 2. Install pymol-mcp into that env

```bash
conda run -n pymol-mcp pip install "git+https://github.com/wjgoarxiv/pymol-mcp.git"
```

Optional trajectory bridge (GROMACS `.xtc` / LAMMPS dumps via MDAnalysis):

```bash
conda run -n pymol-mcp pip install "pymol-mcp[md] @ git+https://github.com/wjgoarxiv/pymol-mcp.git"
```

## 3. Register the server in the MCP client config

```json
{
  "mcpServers": {
    "pymol": {
      "command": "conda",
      "args": ["run", "-n", "pymol-mcp", "python", "-m", "pymol_mcp"]
    }
  }
}
```

If the client can't find `conda` on its PATH (common for GUI desktop apps), use the absolute
interpreter path instead:

```json
{
  "mcpServers": {
    "pymol": {
      "command": "/ABSOLUTE/PATH/TO/miniforge3/envs/pymol-mcp/bin/python",
      "args": ["-m", "pymol_mcp"]
    }
  }
}
```

Find that path with: `conda run -n pymol-mcp python -c "import sys; print(sys.executable)"`

## 4. Verify

```bash
conda run -n pymol-mcp python -c "import pymol2, pymol_mcp; print('pymol-mcp OK')"
```

Expected output: `pymol-mcp OK`. The server then communicates over stdio (MCP).

## Notes

- The optional scripting passthrough (`run_pml` / `run_python`) is **off by default**. To enable it,
  add `"env": {"PYMOL_MCP_ALLOW_CODE_EXEC": "1"}` to the server entry (runs arbitrary local code).
- Structure/trajectory file paths passed to tools must be **absolute**.
