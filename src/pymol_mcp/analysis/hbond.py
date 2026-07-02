"""Hydrogen-bond network over water oxygens (all-nm), ported from a validated Rust reference implementation.

Edge i-j iff O-O distance <= rcut AND at least one donor angle H-O...O < theta.
"""

from __future__ import annotations

import numpy as np

from .geometry import Cell, neighbor_pairs


def build_hbond_network(waters, cell: Cell, rcut: float = 0.36, theta: float = 35.0):
    """Return an adjacency list (sorted) over water indices."""
    o = np.array([w[0] for w in waters], dtype=float)
    h1 = np.array([w[1] for w in waters], dtype=float)
    h2 = np.array([w[2] for w in waters], dtype=float)
    n = len(waters)
    adj: list[list[int]] = [[] for _ in range(n)]

    for i, j in neighbor_pairs(o, cell, rcut):
        # Four candidate donor angles H-O...O; bond if the smallest is below theta.
        angles = (
            cell.angle(o[i], h1[i], o[j]),
            cell.angle(o[i], h2[i], o[j]),
            cell.angle(o[j], h1[j], o[i]),
            cell.angle(o[j], h2[j], o[i]),
        )
        if min(angles) < theta:
            adj[i].append(j)
            adj[j].append(i)

    for a in adj:
        a.sort()
    return adj
