"""Render the PyMOL viewport frames used by the Remotion demo (run in the conda `viz` env).

    /path/to/conda/envs/viz/bin/python video/gen_frames.py

Writes video/public/frames/{load.png, spin_000.png ... spin_047.png} — a water framework
plus a 48-frame 360-deg rotation of a clean sII cage cluster (all drawn by pymol-mcp itself).
"""

import os

import numpy as np
import pymol2
from pymol.cgo import COLOR, CYLINDER, SPHERE

from pymol_mcp.analysis.cage import identify_cages
from pymol_mcp.analysis.geometry import Cell
from pymol_mcp.analysis.gro import parse_gro
from pymol_mcp.server import _CAGE_HEX, _hex_rgb

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "public", "frames")
GRO = os.path.join(_HERE, "..", "tests", "fixtures", "hydrate_sII.gro")
os.makedirs(OUT, exist_ok=True)

w, _guests, box = parse_gro(GRO)
cell = Cell.from_box(box)
res = identify_cages(w, cell)
opos = [np.asarray(x[0]) for x in w]
cages = res["cages"]
centers = np.array([c["center"] for c in cages])
mid = centers.mean(0)

big = [i for i, c in enumerate(cages) if c["type"] == "5^12 6^4"]
bi = min(big, key=lambda i: cell.distance(centers[i], mid))
smalls = sorted(
    (i for i, c in enumerate(cages) if c["type"] == "5^12"),
    key=lambda i: cell.distance(centers[i], centers[bi]),
)
pick = [bi] + smalls[:4]
ref = centers[bi]
edge_r, vert_r = 0.22, 0.48

cluster = []
for idx in pick:
    c = cages[idx]
    rgb = _hex_rgb(_CAGE_HEX[c["type"]])
    v0 = c["vertices"][0]
    shift = cell.mic(opos[v0] - ref) - (opos[v0] - ref)
    pv = {v: opos[v0] + shift + cell.mic(opos[v] - opos[v0]) for v in c["vertices"]}
    for v in c["vertices"]:
        p = pv[v] * 10
        cluster += [COLOR, *rgb, SPHERE, float(p[0]), float(p[1]), float(p[2]), vert_r]
    for i, j in c["edges"]:
        a, b = pv[i] * 10, pv[j] * 10
        cluster += [CYLINDER, *[float(x) for x in a], *[float(x) for x in b], edge_r, *rgb, *rgb]

W, H = 1000, 750
with pymol2.PyMOL() as p:
    cmd = p.cmd
    cmd.feedback("disable", "all", "everything")
    cmd.bg_color("white")

    cmd.load(GRO, "hyd")
    cmd.hide("everything")
    cmd.show("lines", "hyd")
    cmd.color("gray70", "hyd")
    cmd.set("line_width", 0.6)
    cmd.orient("hyd")
    cmd.zoom("hyd", 1)
    cmd.ray(W, H)
    cmd.png(os.path.join(OUT, "load.png"), dpi=120)

    cmd.delete("all")
    cmd.load_cgo(cluster, "cages")
    cmd.reset()
    cmd.orient("cages")
    cmd.zoom("cages", 1.4)
    n = 48
    for f in range(n):
        cmd.ray(W, H)
        cmd.png(os.path.join(OUT, f"spin_{f:03d}.png"), dpi=120)
        cmd.turn("y", 360.0 / n)

print("wrote", len(os.listdir(OUT)), "frames to", OUT)
