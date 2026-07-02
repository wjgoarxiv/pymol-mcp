"""F3 and F4 water order parameters (all-nm), ported from a validated Rust reference implementation.

F4 uses the signed atan2 dihedral and selects, on each molecule, the hydrogen furthest from
the opposing oxygen -- the sign is what distinguishes hydrate (phi~0, cos3phi~+1) from ice.
"""

from __future__ import annotations

import math

import numpy as np

from .geometry import Cell, neighbor_pairs


def _split(waters):
    o = np.array([w[0] for w in waters], dtype=float)
    h1 = np.array([w[1] for w in waters], dtype=float)
    h2 = np.array([w[2] for w in waters], dtype=float)
    return o, h1, h2


def calculate_f4(waters, cell: Cell, cutoff: float = 0.35):
    """Return (f4_overall, n_pairs). Neighbors by O-O distance < cutoff (nm, KDTree)."""
    o, h1, h2 = _split(waters)
    total = 0.0
    pairs = 0
    for i, j in neighbor_pairs(o, cell, cutoff):
        hi = h1[i] if cell.distance(o[j], h1[i]) > cell.distance(o[j], h2[i]) else h2[i]
        hj = h1[j] if cell.distance(o[i], h1[j]) > cell.distance(o[i], h2[j]) else h2[j]
        phi = cell.dihedral(hi, o[i], o[j], hj)
        total += math.cos(3.0 * phi)
        pairs += 1
    return (total / pairs if pairs else 0.0), pairs


def calculate_f3(waters, cell: Cell, cutoff: float = 0.35):
    """Global F3 (three-body angular order), cos reference 109.47 deg (= -1/3)."""
    o, _, _ = _split(waters)
    n = len(o)
    adj: list[list[int]] = [[] for _ in range(n)]
    for i, j in neighbor_pairs(o, cell, cutoff):
        adj[i].append(j)
        adj[j].append(i)
    f3 = np.zeros(n)
    counts = np.zeros(n, dtype=int)
    for i in range(n):
        neigh = adj[i]
        s = 0.0
        c = 0
        for a in range(len(neigh)):
            for b in range(a + 1, len(neigh)):
                v1 = cell.mic(o[neigh[a]] - o[i])
                v2 = cell.mic(o[neigh[b]] - o[i])
                nv = np.linalg.norm(v1) * np.linalg.norm(v2)
                if nv < 1e-12:
                    continue
                cos = float(np.clip(np.dot(v1, v2) / nv, -1.0, 1.0))
                term = (cos * cos + 1.0 / 9.0) if cos >= 0 else (-cos * cos + 1.0 / 9.0)
                s += term * term
                c += 1
        if c:
            f3[i] = s / c
            counts[i] = c
    valid = counts > 0
    return float(f3[valid].mean()) if valid.any() else 0.0
