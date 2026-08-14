"""CHILL+ water-structure classification and O-O network construction."""

from __future__ import annotations

import math

import numpy as np

from .geometry import Cell

DEFAULT_CUTOFF_NM = 0.35
STAGGERED_MAX = -0.8
ECLIPSED_MIN = -0.35
ECLIPSED_MAX = 0.25

CHILL_CLASS_LABELS = (
    "Other/liquid",
    "Hexagonal ice",
    "Cubic ice",
    "Interfacial ice",
    "Gas hydrate",
    "Interfacial hydrate",
)

CHILL_CLASS_COLORS = (
    "#94a3b8",
    "#60a5fa",
    "#22d3ee",
    "#2dd4bf",
    "#f59e0b",
    "#fbbf24",
)


def _validate_inputs(waters, cell: Cell, cutoff_nm: float) -> list[np.ndarray]:
    if not isinstance(cell, Cell) or not np.isfinite(cell.H).all():
        raise ValueError("cell must be a finite Cell")

    try:
        cutoff = float(cutoff_nm)
    except (TypeError, ValueError) as exc:
        raise ValueError("cutoff must be a finite positive number in nm") from exc
    if not math.isfinite(cutoff) or cutoff <= 0.0:
        raise ValueError("cutoff must be a finite positive number in nm")

    if waters is None:
        raise ValueError("waters must be a sequence of water triplets")

    try:
        water_iter = iter(waters)
    except TypeError as exc:
        raise ValueError("waters must be a sequence of water triplets") from exc

    oxygens: list[np.ndarray] = []
    for index, water in enumerate(water_iter):
        try:
            if len(water) != 3:
                raise ValueError
            positions = [np.asarray(position, dtype=float) for position in water]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"water {index} must contain three 3D coordinate triplets") from exc
        if any(position.shape != (3,) or not np.isfinite(position).all() for position in positions):
            raise ValueError(f"water {index} must contain finite 3D coordinates")
        oxygens.append(positions[0])
    return oxygens


def _mic(delta, cell: Cell):
    fractional = np.asarray(delta, dtype=float) @ cell.Hinv
    rounded = np.where(
        fractional >= 0.0,
        np.floor(fractional + 0.5),
        np.ceil(fractional - 0.5),
    )
    return (fractional - rounded) @ cell.H


def _neighbor_indices(oxygens: list[np.ndarray], cell: Cell, cutoff_nm: float) -> list[list[int]]:
    if not oxygens:
        return []
    coordinates = np.asarray(oxygens, dtype=float)
    cutoff_sq = cutoff_nm * cutoff_nm
    adjacency: list[list[int]] = []
    for i, center in enumerate(coordinates):
        distances = _mic(coordinates - center, cell)
        distance_sq = np.einsum("ij,ij->i", distances, distances)
        distance_sq[i] = np.inf
        candidates = np.flatnonzero(distance_sq <= cutoff_sq)
        adjacency.append(sorted(candidates.tolist(), key=lambda j: (float(distance_sq[j]), j)))
    return adjacency


def _y3(direction: np.ndarray) -> tuple[complex, complex, complex, complex]:
    x, y, z = (float(value) for value in direction)
    pi = math.pi
    c0 = 0.25 * math.sqrt(7.0 / pi)
    c1 = -0.125 * math.sqrt(21.0 / pi)
    c2 = 0.25 * math.sqrt(105.0 / (2.0 * pi))
    c3 = -0.125 * math.sqrt(35.0 / pi)
    xy = complex(x, y)
    return (
        complex(c0 * (5.0 * z**3 - 3.0 * z)),
        c1 * (5.0 * z**2 - 1.0) * xy,
        c2 * z * xy**2,
        c3 * xy**3,
    )


def _local_q3(center: np.ndarray, neighbours: list[int], oxygens: list[np.ndarray], cell: Cell):
    q = [0j, 0j, 0j, 0j]
    for index in neighbours:
        delta = _mic(oxygens[index] - center, cell)
        norm = float(np.linalg.norm(delta))
        if norm <= 0.0:
            continue
        for m, value in enumerate(_y3(delta / norm)):
            q[m] += value
    if neighbours:
        q = [value / len(neighbours) for value in q]
    return q


def _q3_norm_sq(q: list[complex]) -> float:
    return abs(q[0]) ** 2 + 2.0 * sum(abs(value) ** 2 for value in q[1:])


def _correlation(qi: list[complex], ni: float, qj: list[complex], nj: float) -> float:
    if ni <= 0.0 or nj <= 0.0:
        return 0.0
    numerator = (qi[0].real * qj[0].real) + 2.0 * sum(
        (left * right.conjugate()).real for left, right in zip(qi[1:], qj[1:])
    )
    return numerator / math.sqrt(ni * nj)


def _classify_bond(correlation: float) -> str | None:
    if correlation < STAGGERED_MAX:
        return "staggered"
    if ECLIPSED_MIN <= correlation <= ECLIPSED_MAX:
        return "eclipsed"
    return None


def _classify_bonds(n_staggered: int, n_eclipsed: int) -> int:
    if n_staggered == 4:
        return 2
    if n_staggered == 3 and n_eclipsed == 1:
        return 1
    if n_eclipsed == 4:
        return 4
    if n_eclipsed == 3:
        return 5
    if n_staggered in (2, 3):
        return 3
    return 0


def calculate_chill_plus(
    waters,
    cell: Cell,
    cutoff_nm: float = DEFAULT_CUTOFF_NM,
) -> dict:
    """Classify water molecules with the CHILL+ q3 bond-orientational method.

    Coordinates and the periodic cell use nanometres. The result preserves water input order.
    """
    oxygens = _validate_inputs(waters, cell, cutoff_nm)
    cutoff = float(cutoff_nm)
    neighbours = _neighbor_indices(oxygens, cell, cutoff)
    q_vectors = [_local_q3(oxygens[i], neighbours[i], oxygens, cell) for i in range(len(oxygens))]
    q_norms = [_q3_norm_sq(q) for q in q_vectors]

    per_atom_class: list[int] = []
    class_counts = [0] * len(CHILL_CLASS_LABELS)
    for i, neighbour_indices in enumerate(neighbours):
        if len(neighbour_indices) != 4:
            class_code = 0
        else:
            n_staggered = 0
            n_eclipsed = 0
            for j in neighbour_indices:
                kind = _classify_bond(_correlation(q_vectors[i], q_norms[i], q_vectors[j], q_norms[j]))
                if kind == "staggered":
                    n_staggered += 1
                elif kind == "eclipsed":
                    n_eclipsed += 1
            class_code = _classify_bonds(n_staggered, n_eclipsed)
        per_atom_class.append(class_code)
        class_counts[class_code] += 1

    n_water = len(oxygens)
    fractions = [count / n_water if n_water else 0.0 for count in class_counts]
    edges = sorted([[i, j] for i, indices in enumerate(neighbours) for j in indices if i < j])
    return {
        "algorithm": "CHILL+",
        "units": "nm",
        "cutoff_nm": cutoff,
        "class_labels": list(CHILL_CLASS_LABELS),
        "class_colors": list(CHILL_CLASS_COLORS),
        "per_atom_class": per_atom_class,
        "class_counts": class_counts,
        "fractions": fractions,
        "n_water": n_water,
        "neighbor_counts": [len(indices) for indices in neighbours],
        "edges": edges,
    }
