"""Minimal GROMACS .gro reader for water/guest extraction (coords in nm), per a validated Rust reference implementation.

Water residues are recognized by an exact residue-name whitelist; oxygen/hydrogen by atom-name
predicates. Waters are assembled as (O, H1, H2) triplets grouped by residue number.
"""

from __future__ import annotations

WATER_RESNAMES = {
    "SOL", "WAT", "HOH", "H2O", "TIP", "TIP3", "TIP3P", "TIP4", "TIP4P", "TIP5", "TIP5P",
    "SPC", "SPCE", "SPC/E", "HSL", "ICE", "HYD", "HYW", "CAGE", "WCL", "WATC",
}


def is_water_resn(resn: str) -> bool:
    return resn.strip().upper() in WATER_RESNAMES


def is_oxygen(name: str) -> bool:
    n = name.strip().upper()
    return n.startswith("O") or "OW" in n


def is_hydrogen(name: str) -> bool:
    n = name.strip().upper()
    return n.startswith("H") and "HE" not in n


def parse_gro(path: str):
    """Return (waters, guests, box).

    waters: list of ((ox,oy,oz),(h1x,..),(h2x,..)) in nm
    guests: list of (resn, (x,y,z)) in nm  (C atom of CO2/CH4 residues)
    box:    list of 3 or 9 floats (nm)
    """
    with open(path) as fh:
        lines = fh.read().splitlines()
    natoms = int(lines[1])

    waters = []
    guests = []
    cur_o = None
    cur_h: list = []
    cur_resid = None

    for i in range(2, 2 + natoms):
        ln = lines[i]
        if len(ln) < 44:
            continue
        resnum = ln[0:5].strip()
        resn = ln[5:10].strip()
        name = ln[10:15].strip()
        coord = (float(ln[20:28]), float(ln[28:36]), float(ln[36:44]))

        if is_water_resn(resn):
            if is_oxygen(name):
                if cur_o is not None and len(cur_h) >= 2:
                    waters.append((cur_o, cur_h[0], cur_h[1]))
                cur_o, cur_h, cur_resid = coord, [], resnum
            elif is_hydrogen(name) and cur_resid == resnum and len(cur_h) < 2:
                cur_h.append(coord)
        else:
            up = resn.upper()
            first = name.strip().upper()[:1]
            if "CO2" in up and first == "C":
                guests.append((resn, coord))
            elif ("CH4" in up or "METH" in up) and first == "C":
                guests.append((resn, coord))

    if cur_o is not None and len(cur_h) >= 2:
        waters.append((cur_o, cur_h[0], cur_h[1]))

    box = [float(v) for v in lines[2 + natoms].split()]
    return waters, guests, box
