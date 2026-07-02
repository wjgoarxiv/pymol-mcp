"""Clathrate cage perception (TRACE), ported from a validated Rust reference implementation.

Pipeline: H-bond network -> geometrically-validated rings (4/5/6) -> cage assembly by
constraint propagation with the SEC (simple-edge-closed) Euler validation -> face-count
classification. All lengths in nm.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .geometry import Cell
from .hbond import build_hbond_network

_CAGE_TABLE = {
    (0, 12, 0): "5^12",
    (0, 12, 2): "5^12 6^2",
    (0, 12, 3): "5^12 6^3",
    (0, 12, 4): "5^12 6^4",
    (0, 12, 8): "5^12 6^8",
    (3, 6, 3): "4^3 5^6 6^3",
    (2, 8, 4): "4^2 5^8 6^4",
    (1, 10, 2): "4^1 5^10 6^2",
}


def _normalize_ring(ring):
    n = len(ring)
    i = ring.index(min(ring))
    fwd = tuple(ring[(i + k) % n] for k in range(n))
    rev = tuple(ring[(i - k) % n] for k in range(n))
    return fwd if fwd[1] <= rev[1] else rev


def find_rings(adj, size):
    """All simple cycles of exactly `size` in the adjacency graph (TRACE, non-primitive)."""
    n = len(adj)
    adj_sets = [set(a) for a in adj]
    rings = set()

    def dfs(start, path, visited):
        cur = path[-1]
        if len(path) == size:
            if start in adj_sets[cur]:
                rings.add(_normalize_ring(tuple(path)))
            return
        for nb in adj[cur]:
            if nb in visited:
                continue
            if len(path) == 1 and nb <= start:
                continue
            visited.add(nb)
            path.append(nb)
            dfs(start, path, visited)
            path.pop()
            visited.discard(nb)

    for s in range(n):
        dfs(s, [s], {s})
    return [list(r) for r in rings]


def is_valid_ring(ring, o, cell: Cell, rcut: float = 0.36) -> bool:
    n = len(ring)
    pts = [np.asarray(o[v]) for v in ring]
    closure = np.zeros(3)
    for i in range(n):
        closure += cell.mic(pts[(i + 1) % n] - pts[i])
    if np.any(np.abs(closure) > 0.1):
        return False
    if n == 4:
        lrange = 1.2 * rcut - 0.08
        diag = [(0, 2), (1, 3)]
    elif n == 5:
        lrange = 1.6 * rcut - 0.18
        diag = [(i, j) for i in range(n) for j in range(i + 2, n) if not (i == 0 and j == n - 1)]
    elif n == 6:
        lrange = 2.0 * rcut - 0.26
        diag = [(i, i + 3) for i in range(3)]
    else:
        return True
    for i, j in diag:
        if cell.distance(pts[i], pts[j]) < lrange:
            return False
    return True


def _classify(face_indices, rings):
    n4 = sum(1 for ri in face_indices if len(rings[ri]) == 4)
    n5 = sum(1 for ri in face_indices if len(rings[ri]) == 5)
    n6 = sum(1 for ri in face_indices if len(rings[ri]) == 6)
    return _CAGE_TABLE.get((n4, n5, n6), f"({n4},{n5},{n6})"), (n4, n5, n6)


def _grow_cage(seed, rings, ring_edges, edge_rings, max_faces=20):
    faces = [seed]
    edge_count: dict = defaultdict(int)
    vertex_count: dict = defaultdict(int)

    def apply(ri, sign):
        for e in ring_edges[ri]:
            edge_count[e] += sign
        for v in rings[ri]:
            vertex_count[v] += sign

    apply(seed, +1)

    def valid_add(ri):
        if ri in faces:
            return False
        for e in ring_edges[ri]:
            if edge_count[e] >= 2:
                return False
        for v in rings[ri]:
            if vertex_count[v] >= 3:
                return False
        return True

    def validate_sec():
        F = len(faces)
        edges = set()
        verts = set()
        for ri in faces:
            edges.update(ring_edges[ri])
            verts.update(rings[ri])
        E, V = len(edges), len(verts)
        if F - E + V != 2:
            return False
        if any(edge_count[e] != 2 for e in edges):
            return False
        if any(vertex_count[v] != 3 for v in verts):
            return False
        return True

    def dfs():
        open_edges = [e for e, c in edge_count.items() if c == 1]
        if not open_edges:
            return validate_sec()
        if len(faces) >= max_faces:
            return False
        best_cands = None
        for e in open_edges:
            cands = [r for r in edge_rings[e] if valid_add(r)]
            if not cands:
                return False
            if best_cands is None or len(cands) < len(best_cands):
                best_cands = cands
                if len(cands) == 1:
                    break
        for r in best_cands:
            faces.append(r)
            apply(r, +1)
            if dfs():
                return True
            faces.pop()
            apply(r, -1)
        return False

    return list(faces) if dfs() else None


def identify_cages(waters, cell: Cell, rcut: float = 0.36, theta: float = 35.0):
    """Return a dict: cage list (vertices, type, center) + per-type counts."""
    o = [np.asarray(w[0]) for w in waters]
    if len(o) < 20:
        return {"cages": [], "counts": {}, "n_rings": 0}

    adj = build_hbond_network(waters, cell, rcut, theta)

    rings = []
    for size in (4, 5, 6):
        for r in find_rings(adj, size):
            if is_valid_ring(r, o, cell, rcut):
                rings.append(r)

    ring_edges = []
    edge_rings: dict = defaultdict(list)
    for ri, ring in enumerate(rings):
        edges = set()
        n = len(ring)
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            edges.add((a, b) if a < b else (b, a))
        ring_edges.append(edges)
        for e in edges:
            edge_rings[e].append(ri)

    seen = set()
    cages = []
    for seed in range(len(rings)):
        face_indices = _grow_cage(seed, rings, ring_edges, edge_rings)
        if not face_indices:
            continue
        key = frozenset(face_indices)
        if key in seen:
            continue
        seen.add(key)
        vertices = sorted({v for ri in face_indices for v in rings[ri]})
        # Polyhedron edges = deduplicated consecutive vertex pairs across all ring faces.
        edge_set = set()
        for ri in face_indices:
            ring = rings[ri]
            nr = len(ring)
            for k in range(nr):
                a, b = ring[k], ring[(k + 1) % nr]
                edge_set.add((a, b) if a < b else (b, a))
        label, _ = _classify(face_indices, rings)
        center = cell.pbc_average([o[v] for v in vertices])
        cages.append(
            {
                "type": label,
                "vertices": vertices,
                "edges": sorted(edge_set),
                "center": [float(x) for x in center],
            }
        )

    counts: dict = defaultdict(int)
    for c in cages:
        counts[c["type"]] += 1
    return {"cages": cages, "counts": dict(counts), "n_rings": len(rings)}


def classify_structure(counts: dict) -> str:
    """Classify the hydrate structure type (sI/sII/sH/mixed) from cage-type counts."""
    n512 = counts.get("5^12", 0)
    n51262 = counts.get("5^12 6^2", 0)
    n51264 = counts.get("5^12 6^4", 0)
    n435663 = counts.get("4^3 5^6 6^3", 0)
    n51268 = counts.get("5^12 6^8", 0)
    if (n435663 > 0 or n51268 > 0) and n512 > 0:
        return "sH"
    if n51262 > 0 and n51264 == 0:
        return "sI"
    if n51264 > 0 and n51262 == 0:
        return "sII"
    if n51262 > 0 and n51264 > 0:
        return "mixed"
    if n512 > 0:
        return "unknown"
    return "amorphous"


# Guest-to-cage containment radii (nm), by cage type.
_OCC_RADII = {"5^12": 0.395, "5^12 6^2": 0.433, "5^12 6^4": 0.473}


def cage_occupancy(waters, guests, cell: Cell, cage_result=None, rcut: float = 0.36, theta: float = 35.0):
    """Assign guest molecules to cages (one guest per cage, nearest within the type radius)."""
    if cage_result is None:
        cage_result = identify_cages(waters, cell, rcut, theta)
    cages = cage_result["cages"]
    if not cages:
        return {"total_cages": 0, "occupied": 0, "overall_occupancy": 0.0, "by_type": {}}

    # each guest -> its nearest eligible cage
    guest_best = []
    for gi, (_gname, gpos) in enumerate(guests):
        gpos = np.asarray(gpos)
        best, bestd = None, None
        for ci, c in enumerate(cages):
            r = _OCC_RADII.get(c["type"], 0.473)
            d = cell.distance(gpos, np.asarray(c["center"]))
            if d < r and (bestd is None or d < bestd):
                best, bestd = ci, d
        guest_best.append((gi, best, bestd))

    # resolve conflicts: one guest per cage (nearest wins)
    cage_guest: dict = {}
    for gi, ci, d in guest_best:
        if ci is None:
            continue
        if ci not in cage_guest or d < cage_guest[ci][1]:
            cage_guest[ci] = (gi, d)

    total_by_type: dict = defaultdict(int)
    occ_by_type: dict = defaultdict(int)
    for ci, c in enumerate(cages):
        total_by_type[c["type"]] += 1
        if ci in cage_guest:
            occ_by_type[c["type"]] += 1

    return {
        "total_cages": len(cages),
        "occupied": len(cage_guest),
        "overall_occupancy": round(len(cage_guest) / len(cages), 4),
        "by_type": {
            t: {
                "total": total_by_type[t],
                "occupied": occ_by_type[t],
                "occupancy": round(occ_by_type[t] / total_by_type[t], 4) if total_by_type[t] else 0.0,
            }
            for t in total_by_type
        },
    }
