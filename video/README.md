# Demo video (Remotion)

The demo (`../assets/pymol-mcp-demo.gif` / `.mp4`) is composed with [Remotion](https://remotion.dev)
from **real pymol-mcp renders** — a chat panel drives the tool calls while the viewport shows the
headless PyMOL output (a rotating sII cage cluster drawn by `mark_cages`).

## Regenerate

1. **Frames** — run in the conda env that has `pymol2` (e.g. `viz`):
   ```bash
   /path/to/conda/envs/viz/bin/python gen_frames.py   # -> public/frames/*.png
   ```
2. **Render** — with Node:
   ```bash
   npm install
   npm run render        # -> out/pymol-mcp-demo.mp4
   npm run studio        # interactive preview
   ```

`node_modules/`, `out/`, and `public/frames/` are gitignored (regenerate as above).
