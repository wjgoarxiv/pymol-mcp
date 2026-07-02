"""PBC-correct geometry primitives (all lengths in nm), ported from a validated Rust reference implementation.

Supports orthorhombic and triclinic cells via fractional-coordinate minimum-image
convention. The signed dihedral uses the atan2 form required for F4.
"""

from __future__ import annotations

import math

import numpy as np

_EPS = 1e-10


class Cell:
    """A periodic cell. ``H`` holds the lattice vectors a, b, c as ROWS (nm)."""

    def __init__(self, H):
        self.H = np.asarray(H, dtype=float)
        if abs(np.linalg.det(self.H)) < 1e-9:
            raise ValueError("degenerate (zero-volume) periodic box")
        self.Hinv = np.linalg.inv(self.H)

    # -- constructors --------------------------------------------------------
    @classmethod
    def from_box(cls, box) -> "Cell":
        """Build from 3 (orthorhombic lengths), 6 (lx,ly,lz,xy,xz,yz), or 9 (GROMACS) values, in nm."""
        b = [float(x) for x in box]
        if len(b) == 3:
            H = np.diag(b)
        elif len(b) == 6:
            lx, ly, lz, xy, xz, yz = b
            H = np.array([[lx, 0.0, 0.0], [xy, ly, 0.0], [xz, yz, lz]])
        elif len(b) == 9:
            v1x, v2y, v3z, v1y, v1z, v2x, v2z, v3x, v3y = b
            H = np.array([[v1x, v1y, v1z], [v2x, v2y, v2z], [v3x, v3y, v3z]])
        else:
            raise ValueError(f"box must have 3, 6, or 9 values, got {len(b)}")
        return cls(H)

    @classmethod
    def from_lengths_angles(cls, a, b, c, alpha, beta, gamma) -> "Cell":
        """Build from crystallographic parameters (lengths nm, angles degrees).

        Matches PyMOL's ``get_symmetry`` ordering (after Angstrom->nm conversion).
        """
        al, be, ga = (math.radians(x) for x in (alpha, beta, gamma))
        va = np.array([a, 0.0, 0.0])
        vb = np.array([b * math.cos(ga), b * math.sin(ga), 0.0])
        cx = c * math.cos(be)
        cy = c * (math.cos(al) - math.cos(be) * math.cos(ga)) / (math.sin(ga) or _EPS)
        cz = math.sqrt(max(c * c - cx * cx - cy * cy, 0.0))
        vc = np.array([cx, cy, cz])
        return cls(np.array([va, vb, vc]))

    # -- operations ----------------------------------------------------------
    def mic(self, delta):
        """Minimum-image image of a displacement vector (nm)."""
        frac = np.asarray(delta, dtype=float) @ self.Hinv
        frac -= np.round(frac)
        return frac @ self.H

    def distance(self, a, b) -> float:
        return float(np.linalg.norm(self.mic(np.asarray(b) - np.asarray(a))))

    def angle(self, center, a, b) -> float:
        """Angle a-center-b in degrees (MIC-corrected)."""
        v1 = self.mic(np.asarray(a) - np.asarray(center))
        v2 = self.mic(np.asarray(b) - np.asarray(center))
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < _EPS or n2 < _EPS:
            return 180.0
        cos = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
        return math.degrees(math.acos(cos))

    def dihedral(self, p1, p2, p3, p4) -> float:
        """Signed dihedral p1-p2-p3-p4 in radians (atan2 form; collinear -> pi/2)."""
        b1 = self.mic(np.asarray(p2) - np.asarray(p1))
        b2 = self.mic(np.asarray(p3) - np.asarray(p2))
        b3 = self.mic(np.asarray(p4) - np.asarray(p3))
        n1 = np.cross(b1, b2)
        n2 = np.cross(b2, b3)
        nb2 = np.linalg.norm(b2)
        if np.linalg.norm(n1) < _EPS or np.linalg.norm(n2) < _EPS or nb2 < _EPS:
            return math.pi / 2
        x = np.dot(b2, np.cross(n1, n2))
        y = nb2 * np.dot(n1, n2)
        return math.atan2(x, y)

    def pbc_average(self, points):
        """PBC-aware centroid of points (nm), via reference-point unwrapping."""
        pts = np.asarray(points, dtype=float)
        ref = pts[0]
        acc = np.zeros(3)
        for p in pts:
            acc += self.mic(p - ref)
        return ref + acc / len(pts)


def neighbor_pairs(coords, cell: Cell, cutoff: float):
    """All index pairs (i<j) whose MIC distance < cutoff (nm).

    Uses an explicit periodic-image KDTree so it is correct for triclinic cells and
    negative coordinates (unlike scipy's cKDTree ``boxsize=``, which is orthorhombic-only).
    """
    from scipy.spatial import cKDTree

    coords = np.asarray(coords, dtype=float)
    n = len(coords)
    # Wrap into the primary cell, then tile the 27 (or fewer) image shells within cutoff.
    frac = coords @ cell.Hinv
    frac -= np.floor(frac)
    wrapped = frac @ cell.H

    shifts = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                shifts.append(np.array([i, j, k], dtype=float) @ cell.H)
    images = []
    image_of = []
    for s in shifts:
        images.append(wrapped + s)
        image_of.append(np.arange(n))
    images = np.vstack(images)
    image_of = np.concatenate(image_of)

    tree_img = cKDTree(images)
    pairs = set()
    for i in range(n):
        for jimg in tree_img.query_ball_point(wrapped[i], cutoff):
            j = int(image_of[jimg])
            if j == i:
                continue
            key = (i, j) if i < j else (j, i)
            pairs.add(key)
    return sorted(pairs)
