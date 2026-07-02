"""FastMCP server for headless PyMOL (M0 skeleton).

All PyMOL access goes through the single-worker-thread ``SESSION`` (see session.py).
Logging goes to STDERR only -- never stdout (stdout is the JSON-RPC channel).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from pydantic import Field

from .session import PyMOLSession

logging.basicConfig(level=logging.INFO, stream=sys.stderr)  # stderr, NEVER stdout
log = logging.getLogger("pymol-mcp")

SESSION = PyMOLSession()

# The raw code-execution passthrough is an opt-in capability (arbitrary local code
# execution, prompt-injectable via file headers/names). Off by default.
ALLOW_CODE_EXEC = os.environ.get("PYMOL_MCP_ALLOW_CODE_EXEC", "").lower() in ("1", "true", "yes", "on")


@asynccontextmanager
async def lifespan(app):
    SESSION.start()
    log.info("PyMOL session started (headless, worker thread)")
    try:
        yield {}
    finally:
        SESSION.stop()
        log.info("PyMOL session stopped")


mcp = FastMCP(
    "pymol-mcp",
    instructions=(
        "Headless PyMOL for molecular visualization, GROMACS/LAMMPS MD workflows, and "
        "clathrate-hydrate cage analysis. Load structures, render images (returned inline), "
        "and inspect the session with typed tools."
    ),
    lifespan=lifespan,
)


# ----------------------------------------------------------------------------
# Session / IO
# ----------------------------------------------------------------------------
@mcp.tool
def load_structure(
    path: Annotated[str, Field(description="Absolute path to a structure/coordinate file (.pdb, .cif, .gro, .mol2, .sdf, .xyz).")],
    object_name: Annotated[str | None, Field(description="Optional name for the loaded object.")] = None,
) -> dict:
    """Load a molecular structure or single-frame coordinate file into PyMOL.

    Returns the created object name and its atom/state counts.
    """
    def _load(cmd):
        if not os.path.exists(path):
            raise ToolError(f"File not found: {path}")
        before = set(cmd.get_object_list())
        if object_name:
            cmd.load(path, object_name)
        else:
            cmd.load(path)
        after = cmd.get_object_list()
        new = [o for o in after if o not in before] or list(after[-1:])
        obj = new[-1] if new else ""
        if not obj:
            raise ToolError(f"PyMOL loaded no object from {path}")
        return {
            "object": obj,
            "n_atoms": cmd.count_atoms(obj),
            "n_states": cmd.count_states(obj),
            "objects": list(after),
        }

    return SESSION.call(_load)


@mcp.tool
def fetch_pdb(
    code: Annotated[str, Field(description="4-character PDB accession code, e.g. '1UBQ'.", min_length=4, max_length=4)],
    object_name: Annotated[str | None, Field(description="Optional object name.")] = None,
) -> dict:
    """Fetch a structure from the RCSB PDB (requires network) and load it."""
    def _fetch(cmd):
        fetch_dir = tempfile.mkdtemp(prefix="pymol_mcp_fetch_")
        cmd.set("fetch_path", fetch_dir)
        name = object_name or code.lower()
        cmd.fetch(code.lower(), name, type="pdb")
        if cmd.count_atoms(name) == 0:
            raise ToolError(f"Fetched nothing for PDB code '{code}' (network or invalid code?)")
        return {"object": name, "n_atoms": cmd.count_atoms(name), "n_states": cmd.count_states(name)}

    return SESSION.call(_fetch, timeout=120)


@mcp.tool
def list_objects() -> list[str]:
    """List all loaded object names in the current PyMOL session."""
    return SESSION.call(lambda cmd: list(cmd.get_object_list()))


@mcp.tool
def get_object_info(
    name: Annotated[str, Field(description="Object name to inspect.")],
) -> dict:
    """Return atom count, state count, and chains for a loaded object."""
    def _info(cmd):
        if name not in cmd.get_object_list():
            raise ToolError(f"No object named '{name}'. Loaded: {cmd.get_object_list()}")
        return {
            "object": name,
            "n_atoms": cmd.count_atoms(name),
            "n_states": cmd.count_states(name),
            "chains": list(cmd.get_chains(name)),
        }

    return SESSION.call(_info)


@mcp.tool
def reset_session() -> str:
    """Reinitialize PyMOL, clearing all objects, selections, and settings."""
    SESSION.reinitialize()
    return "PyMOL session reinitialized."


# ----------------------------------------------------------------------------
# Rendering (vision loop)
# ----------------------------------------------------------------------------
@mcp.tool
def render_image(
    selection: Annotated[str, Field(description="Selection to zoom before rendering ('all' = whole scene).")] = "all",
    width: Annotated[int, Field(description="Image width in pixels.", ge=16, le=2000)] = 800,
    height: Annotated[int, Field(description="Image height in pixels.", ge=16, le=2000)] = 600,
    zoom: Annotated[bool, Field(description="Zoom/orient onto the selection before rendering.")] = True,
) -> Image:
    """Ray-trace the current scene (headless CPU raytracer) to a PNG and return it inline."""
    def _render(cmd):
        if selection != "all" and cmd.count_atoms(selection) == 0:
            raise ToolError(f"Selection '{selection}' matched 0 atoms")
        if zoom:
            cmd.zoom(selection)
        cmd.ray(width, height)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            cmd.png(tmp, dpi=150)
            with open(tmp, "rb") as fh:
                data = fh.read()
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if len(data) < 100:
            raise ToolError("Render produced an empty image")
        return data

    data = SESSION.call(_render, timeout=300)
    return Image(data=data, format="png")


# ----------------------------------------------------------------------------
# Scripting swiss-army-knife (opt-in; arbitrary local code execution)
# ----------------------------------------------------------------------------
def _require_code_exec():
    if not ALLOW_CODE_EXEC:
        raise ToolError(
            "Code-execution tools are disabled. Set environment variable "
            "PYMOL_MCP_ALLOW_CODE_EXEC=1 to enable run_pml / run_python. "
            "These run arbitrary local code and can be prompt-injected via file contents."
        )


@mcp.tool
def run_pml(
    command: Annotated[str, Field(description="PyMOL command-language (.pml) statement(s), newline-separated.")],
) -> str:
    """[opt-in] Execute raw PyMOL command-language statements. Requires PYMOL_MCP_ALLOW_CODE_EXEC=1."""
    _require_code_exec()

    def _do(cmd):
        for line in command.splitlines():
            line = line.strip()
            if line:
                cmd.do(line)
        return "ok"

    return SESSION.call(_do)


@mcp.tool
def run_python(
    code: Annotated[str, Field(description="Python snippet; PyMOL `cmd` is in scope. Set a `result` variable to return a value.")],
) -> str:
    """[opt-in] Execute a Python snippet with PyMOL `cmd` in scope. Requires PYMOL_MCP_ALLOW_CODE_EXEC=1."""
    _require_code_exec()

    def _exec(cmd):
        import contextlib
        import io

        ns = {"cmd": cmd, "__name__": "pymol_mcp_exec"}
        buf = io.StringIO()
        # Capture Python-level stdout so a stray print() cannot reach the JSON-RPC pipe.
        with contextlib.redirect_stdout(buf):
            exec(code, ns)  # noqa: S102 - opt-in, documented capability
        out = buf.getvalue().strip()
        res = ns.get("result")
        parts = [p for p in (out, (f"result={res!r}" if res is not None else "")) if p]
        return "\n".join(parts) or "(ok, no output)"

    return SESSION.call(_exec)


# ----------------------------------------------------------------------------
# Selection
# ----------------------------------------------------------------------------
@mcp.tool
def select(
    name: Annotated[str, Field(description="Name for the new named selection.")],
    selection: Annotated[str, Field(description="PyMOL selection-algebra expression, e.g. 'chain A and resn ALA'.")],
) -> dict:
    """Create a named selection and return how many atoms it matched."""
    def _sel(cmd):
        n = cmd.select(name, selection)
        return {"selection": name, "n_atoms": int(n)}

    return SESSION.call(_sel)


@mcp.tool
def get_selection_info(
    selection: Annotated[str, Field(description="Selection expression to summarize.")] = "all",
) -> dict:
    """Summarize a selection: atom count, chains, and residue names present."""
    def _info(cmd):
        n = cmd.count_atoms(selection)
        if n == 0:
            return {"selection": selection, "n_atoms": 0, "chains": [], "resn": []}
        resn: set[str] = set()
        cmd.iterate(selection, "resn_set.add(resn)", space={"resn_set": resn})
        return {
            "selection": selection,
            "n_atoms": int(n),
            "chains": list(cmd.get_chains(selection)),
            "resn": sorted(resn)[:50],
        }

    return SESSION.call(_info)


# ----------------------------------------------------------------------------
# Representation / color
# ----------------------------------------------------------------------------
_REPRS = ("lines", "sticks", "spheres", "surface", "mesh", "dots", "ribbon", "cartoon", "nb_spheres", "nonbonded", "putty")


@mcp.tool
def show(
    representation: Annotated[str, Field(description=f"Representation to show. One of: {', '.join(_REPRS)}.")],
    selection: Annotated[str, Field(description="Selection to apply it to.")] = "all",
    only: Annotated[bool, Field(description="If true, show ONLY this representation (hide others) via `as`.")] = False,
) -> str:
    """Show (or exclusively set with `only=True`) a molecular representation for a selection."""
    if representation not in _REPRS:
        raise ToolError(f"Unknown representation '{representation}'. Options: {_REPRS}")

    def _show(cmd):
        if selection != "all" and cmd.count_atoms(selection) == 0:
            raise ToolError(f"Selection '{selection}' matched 0 atoms")
        (cmd.show_as if only else cmd.show)(representation, selection)
        return f"{'as ' if only else ''}{representation} on {selection}"

    return SESSION.call(_show)


@mcp.tool
def hide(
    representation: Annotated[str, Field(description="Representation to hide (or 'everything').")] = "everything",
    selection: Annotated[str, Field(description="Selection to hide it for.")] = "all",
) -> str:
    """Hide a representation for a selection."""
    return SESSION.call(lambda cmd: (cmd.hide(representation, selection), f"hid {representation} on {selection}")[1])


@mcp.tool
def color(
    color: Annotated[str, Field(description="PyMOL color name or hex like 0xRRGGBB.")],
    selection: Annotated[str, Field(description="Selection to color.")] = "all",
) -> str:
    """Color a selection."""
    def _color(cmd):
        if selection != "all" and cmd.count_atoms(selection) == 0:
            raise ToolError(f"Selection '{selection}' matched 0 atoms")
        cmd.color(color, selection)
        return f"colored {selection} {color}"

    return SESSION.call(_color)


@mcp.tool
def spectrum(
    expression: Annotated[str, Field(description="Per-atom expression to color by, e.g. 'b', 'count', 'resi'.")] = "count",
    palette: Annotated[str, Field(description="Color palette, e.g. 'rainbow', 'blue_white_red'.")] = "rainbow",
    selection: Annotated[str, Field(description="Selection to color.")] = "all",
) -> str:
    """Color a selection along a spectrum of a per-atom expression (e.g. B-factor)."""
    return SESSION.call(lambda cmd: (cmd.spectrum(expression, palette, selection), f"spectrum {expression}/{palette} on {selection}")[1])


@mcp.tool
def set_background(
    color: Annotated[str, Field(description="Background color name, e.g. 'white', 'black'.")] = "white",
) -> str:
    """Set the render background color."""
    return SESSION.call(lambda cmd: (cmd.bg_color(color), f"background {color}")[1])


# ----------------------------------------------------------------------------
# View
# ----------------------------------------------------------------------------
@mcp.tool
def orient(selection: Annotated[str, Field(description="Selection to orient the camera on.")] = "all") -> str:
    """Orient the camera along the principal axes of a selection."""
    return SESSION.call(lambda cmd: (cmd.orient(selection), f"oriented on {selection}")[1])


@mcp.tool
def zoom(
    selection: Annotated[str, Field(description="Selection to zoom on.")] = "all",
    buffer: Annotated[float, Field(description="Extra padding in Angstroms.")] = 5.0,
) -> str:
    """Zoom the camera onto a selection."""
    return SESSION.call(lambda cmd: (cmd.zoom(selection, buffer), f"zoomed on {selection}")[1])


@mcp.tool
def turn(
    axis: Annotated[str, Field(description="Rotation axis: 'x', 'y', or 'z'.")],
    angle: Annotated[float, Field(description="Rotation angle in degrees.")] = 90.0,
) -> str:
    """Rotate the camera about an axis."""
    if axis not in ("x", "y", "z"):
        raise ToolError("axis must be 'x', 'y', or 'z'")
    return SESSION.call(lambda cmd: (cmd.turn(axis, angle), f"turned {axis} {angle}")[1])


# ----------------------------------------------------------------------------
# Measurement
# ----------------------------------------------------------------------------
def _one_atom(cmd, sel):
    n = cmd.count_atoms(sel)
    if n != 1:
        raise ToolError(f"Selection '{sel}' must match exactly 1 atom (matched {n}).")


@mcp.tool
def measure_distance(
    atom1: Annotated[str, Field(description="Single-atom selection.")],
    atom2: Annotated[str, Field(description="Single-atom selection.")],
) -> dict:
    """Measure the distance (Angstroms) between two single-atom selections."""
    def _d(cmd):
        _one_atom(cmd, atom1)
        _one_atom(cmd, atom2)
        return {"distance_A": float(cmd.get_distance(atom1, atom2))}

    return SESSION.call(_d)


@mcp.tool
def measure_angle(
    atom1: Annotated[str, Field(description="Single-atom selection.")],
    atom2: Annotated[str, Field(description="Vertex single-atom selection.")],
    atom3: Annotated[str, Field(description="Single-atom selection.")],
) -> dict:
    """Measure the angle (degrees) defined by three single-atom selections."""
    def _a(cmd):
        for s in (atom1, atom2, atom3):
            _one_atom(cmd, s)
        return {"angle_deg": float(cmd.get_angle(atom1, atom2, atom3))}

    return SESSION.call(_a)


@mcp.tool
def measure_dihedral(
    atom1: Annotated[str, Field(description="Single-atom selection.")],
    atom2: Annotated[str, Field(description="Single-atom selection.")],
    atom3: Annotated[str, Field(description="Single-atom selection.")],
    atom4: Annotated[str, Field(description="Single-atom selection.")],
) -> dict:
    """Measure the dihedral (degrees) defined by four single-atom selections."""
    def _dih(cmd):
        for s in (atom1, atom2, atom3, atom4):
            _one_atom(cmd, s)
        return {"dihedral_deg": float(cmd.get_dihedral(atom1, atom2, atom3, atom4))}

    return SESSION.call(_dih)


@mcp.tool
def align(
    mobile: Annotated[str, Field(description="Object/selection to move.")],
    target: Annotated[str, Field(description="Reference object/selection.")],
) -> dict:
    """Sequence-align and superpose `mobile` onto `target` (use for different structures)."""
    def _al(cmd):
        r = cmd.align(mobile, target)
        return {"rmsd_A": float(r[0]), "n_atoms_aligned": int(r[1]), "n_cycles": int(r[2])}

    return SESSION.call(_al)


@mcp.tool
def save_file(
    path: Annotated[str, Field(description="Output path; extension sets format (.pdb, .pse, .png, .mol2, ...).")],
    selection: Annotated[str, Field(description="Selection to save.")] = "all",
    state: Annotated[int, Field(description="State to save (-1 = current, 0 = all).")] = -1,
) -> dict:
    """Save a selection/session to a file (format from extension)."""
    def _save(cmd):
        cmd.save(path, selection, state)
        ok = os.path.exists(path)
        return {"path": path, "saved": ok, "bytes": os.path.getsize(path) if ok else 0}

    return SESSION.call(_save)


# ----------------------------------------------------------------------------
# Trajectory / MD
# ----------------------------------------------------------------------------
@mcp.tool
def load_trajectory(
    structure_path: Annotated[str, Field(description="Topology/first-frame file (.gro/.pdb) matching the trajectory atoms.")],
    trajectory_path: Annotated[str, Field(description="Trajectory file (.xtc/.trr/.dcd) with the SAME atom set/order.")],
    object_name: Annotated[str, Field(description="Object name to create.")] = "traj",
    start: Annotated[int, Field(description="First frame (1-based) to load.")] = 1,
    stop: Annotated[int, Field(description="Last frame to load (-1 = all).")] = -1,
    interval: Annotated[int, Field(description="Load every Nth frame (subsample to bound RAM).")] = 1,
) -> dict:
    """Load a GROMACS/DCD trajectory: load the structure, then append frames as states.

    Requires matching atom count/order (trjconv strip/reorder is the common pitfall).
    """
    def _load(cmd):
        for p in (structure_path, trajectory_path):
            if not os.path.exists(p):
                raise ToolError(f"File not found: {p}")
        cmd.set("defer_builds_mode", 3)  # bound RAM for large trajectories
        cmd.load(structure_path, object_name)
        n_topo = cmd.count_atoms(object_name)
        # state=1 overwrites from the first state, so the object holds exactly the
        # trajectory frames (the topology's single state is replaced by frame 1).
        cmd.load_traj(
            trajectory_path, object_name, state=1,
            start=start, stop=stop, interval=interval,
        )
        return {
            "object": object_name,
            "n_atoms": int(n_topo),
            "n_states": int(cmd.count_states(object_name)),
        }

    return SESSION.call(_load, timeout=600)


@mcp.tool
def load_trajectory_mda(
    trajectory_path: Annotated[str, Field(description="Trajectory PyMOL can't read natively (LAMMPS dump, NetCDF, ...).")],
    topology_path: Annotated[str | None, Field(description="Topology (LAMMPS data, PSF, PDB, GRO). If omitted, the trajectory is used as its own topology (e.g. LAMMPS dump).")] = None,
    object_name: Annotated[str, Field(description="Object name to create.")] = "mda",
    topology_format: Annotated[str | None, Field(description="MDAnalysis topology_format, e.g. 'LAMMPSDATA', 'DATA'.")] = None,
    trajectory_format: Annotated[str | None, Field(description="MDAnalysis format, e.g. 'LAMMPSDUMP', 'NCDF'.")] = None,
    length_unit: Annotated[str, Field(description="MDAnalysis length unit ('Angstrom' or 'nm'); LAMMPS non-real units matter.")] = "Angstrom",
    max_frames: Annotated[int, Field(description="Max frames to inject (subsample across the trajectory).")] = 200,
) -> dict:
    """Load any MDAnalysis-readable trajectory (LAMMPS dump, AMBER NetCDF, ...) by injecting
    coordinates into PyMOL states. Requires the optional `md` extra (MDAnalysis).
    """
    try:
        import MDAnalysis as mda  # lazy: optional GPL dependency
    except Exception as exc:  # pragma: no cover
        raise ToolError("MDAnalysis is not installed. Install the optional extra: pip install 'pymol-mcp[md]'") from exc

    for p in (trajectory_path, topology_path):
        if p is not None and not os.path.exists(p):
            raise ToolError(f"File not found: {p}")

    kwargs = {}
    if topology_format:
        kwargs["topology_format"] = topology_format
    if trajectory_format:
        kwargs["format"] = trajectory_format
    if length_unit:
        kwargs["lengthunit"] = length_unit
    try:
        if topology_path:
            u = mda.Universe(topology_path, trajectory_path, **kwargs)
        else:
            u = mda.Universe(trajectory_path, **kwargs)
    except Exception as exc:
        raise ToolError(f"MDAnalysis failed to build Universe: {exc}") from exc

    n_frames_total = len(u.trajectory)
    stride = max(1, n_frames_total // max_frames)
    # Convert to a PDB-topology PyMOL can hold, then inject coordinate sets per frame.
    frames = list(range(0, n_frames_total, stride))

    def _inject(cmd):
        # Write frame 0 as a PDB so PyMOL has a topology, then append coordinate sets.
        import tempfile
        fd, pdb = tempfile.mkstemp(suffix=".pdb")
        os.close(fd)
        try:
            u.trajectory[frames[0]]
            u.atoms.write(pdb)
            cmd.load(pdb, object_name)
        finally:
            try:
                os.remove(pdb)
            except OSError:
                pass
        n_atoms = cmd.count_atoms(object_name)
        if n_atoms != u.atoms.n_atoms:
            raise ToolError(f"Atom-count mismatch: PyMOL {n_atoms} vs MDAnalysis {u.atoms.n_atoms}")
        for i, fr in enumerate(frames):
            u.trajectory[fr]
            coords = u.atoms.positions  # (N,3) float32, Angstrom
            cmd.load_coordset(coords, object_name, state=i + 1)
        return {"object": object_name, "n_atoms": int(n_atoms), "n_states": int(cmd.count_states(object_name)), "frames_loaded": len(frames)}

    return SESSION.call(_inject, timeout=600)


# ----------------------------------------------------------------------------
# Domain: clathrate-hydrate analysis (all-nm)
# ----------------------------------------------------------------------------
def _resolve_cell(cmd, obj: str, box):
    """Build a Cell (nm). Prefer a user-supplied per-frame box; fall back to get_symmetry."""
    from .analysis.geometry import Cell

    if box:
        return Cell.from_box(box)
    sym = cmd.get_symmetry(obj) if obj else None
    if sym and len(sym) >= 6 and sym[0] and sym[1] and sym[2]:
        a, b, c = sym[0] / 10.0, sym[1] / 10.0, sym[2] / 10.0  # Angstrom -> nm
        return Cell.from_lengths_angles(a, b, c, sym[3], sym[4], sym[5])
    raise ToolError(
        "No periodic box available. Pass `box` (3/6/9 values in nm) explicitly; "
        "get_symmetry returned no usable cell (expected for NPT/LAMMPS/xtc inputs)."
    )


def _extract_waters(cmd, selection: str):
    """Extract water (O, H1, H2) triplets in nm from PyMOL (coords are Angstrom -> x0.1)."""
    from .analysis.gro import WATER_RESNAMES, is_hydrogen, is_oxygen

    rows: list = []
    cmd.iterate_state(
        1, selection,
        "rows.append((segi, chain, resi, name, resn, x, y, z))",
        space={"rows": rows},
    )
    groups: dict = {}
    for segi, chain, resi, name, resn, x, y, z in rows:
        if resn.strip().upper() not in WATER_RESNAMES:
            continue
        g = groups.setdefault((segi, chain, resi), {"o": None, "h": []})
        if is_oxygen(name):
            g["o"] = (x * 0.1, y * 0.1, z * 0.1)
        elif is_hydrogen(name) and len(g["h"]) < 2:
            g["h"].append((x * 0.1, y * 0.1, z * 0.1))
    waters = []
    for g in groups.values():
        if g["o"] is not None and len(g["h"]) >= 2:
            waters.append((g["o"], g["h"][0], g["h"][1]))
    return waters


def _pick_object(cmd, selection: str, object_name):
    if object_name:
        return object_name
    objs = cmd.get_object_list(selection) if selection != "all" else cmd.get_object_list()
    if not objs:
        objs = cmd.get_object_list()
    return objs[0] if objs else ""


@mcp.tool
def order_parameter(
    selection: Annotated[str, Field(description="Selection of the water system.")] = "all",
    kind: Annotated[str, Field(description="'f4' (torsional) or 'f3' (three-body angular).")] = "f4",
    box: Annotated[list[float] | None, Field(description="Periodic box in nm: 3 (orthorhombic), 6 (lx,ly,lz,xy,xz,yz), or 9 (GROMACS). If omitted, read from get_symmetry.")] = None,
    object_name: Annotated[str | None, Field(description="Object whose box to use (defaults to the selection's object).")] = None,
) -> dict:
    """Compute the F3 or F4 water order parameter for a clathrate-hydrate system.

    F4 ~ 0.7-0.95 = hydrate, ~0 = liquid, ~ -0.4 = ice Ih. F3 <= 0.04 = hydrate-like.
    """
    from .analysis.order_params import calculate_f3, calculate_f4

    def _op(cmd):
        obj = _pick_object(cmd, selection, object_name)
        cell = _resolve_cell(cmd, obj, box)
        waters = _extract_waters(cmd, selection)
        if len(waters) < 2:
            raise ToolError(f"Need >=2 water molecules; found {len(waters)}. Check the selection/resnames.")
        if kind.lower() == "f4":
            value, n_pairs = calculate_f4(waters, cell)
            return {"parameter": "F4", "value": value, "n_pairs": n_pairs, "n_waters": len(waters)}
        if kind.lower() == "f3":
            value = calculate_f3(waters, cell)
            return {"parameter": "F3", "value": value, "n_waters": len(waters), "hydrate_like": value <= 0.04}
        raise ToolError("kind must be 'f4' or 'f3'")

    return SESSION.call(_op, timeout=300)


@mcp.tool
def hbond_network(
    selection: Annotated[str, Field(description="Selection of the water system.")] = "all",
    box: Annotated[list[float] | None, Field(description="Periodic box in nm (3/6/9 values). If omitted, read from get_symmetry.")] = None,
    object_name: Annotated[str | None, Field(description="Object whose box to use.")] = None,
    rcut_nm: Annotated[float, Field(description="O-O distance cutoff in nm.", gt=0)] = 0.36,
    angle_deg: Annotated[float, Field(description="Donor H-O...O angle cutoff in degrees.", gt=0)] = 35.0,
) -> dict:
    """Build the water hydrogen-bond network and report coordination statistics.

    A well-formed clathrate framework has ~4 H-bonds per water (tetrahedral).
    """
    from .analysis.hbond import build_hbond_network

    def _hb(cmd):
        obj = _pick_object(cmd, selection, object_name)
        cell = _resolve_cell(cmd, obj, box)
        waters = _extract_waters(cmd, selection)
        if not waters:
            raise ToolError("No water molecules found in the selection.")
        adj = build_hbond_network(waters, cell, rcut_nm, angle_deg)
        degrees = [len(a) for a in adj]
        return {
            "n_waters": len(waters),
            "n_hbonds": sum(degrees) // 2,
            "mean_coordination": round(sum(degrees) / len(degrees), 3) if degrees else 0.0,
            "max_coordination": max(degrees) if degrees else 0,
        }

    return SESSION.call(_hb, timeout=300)


def _extract_guests(cmd, selection: str):
    """Extract guest centers (C atom of CO2/CH4 residues) in nm from PyMOL."""
    rows: list = []
    cmd.iterate_state(1, selection, "rows.append((resn, name, x, y, z))", space={"rows": rows})
    guests = []
    for resn, name, x, y, z in rows:
        up = resn.strip().upper()
        first = name.strip().upper()[:1]
        if ("CO2" in up and first == "C") or (("CH4" in up or "METH" in up) and first == "C"):
            guests.append((resn, (x * 0.1, y * 0.1, z * 0.1)))
    return guests


@mcp.tool
def identify_cages(
    selection: Annotated[str, Field(description="Selection of the water system.")] = "all",
    box: Annotated[list[float] | None, Field(description="Periodic box in nm (3/6/9 values); else from get_symmetry.")] = None,
    object_name: Annotated[str | None, Field(description="Object whose box to use.")] = None,
    rcut_nm: Annotated[float, Field(description="H-bond O-O cutoff in nm.", gt=0)] = 0.36,
    angle_deg: Annotated[float, Field(description="H-bond donor angle cutoff in degrees.", gt=0)] = 35.0,
) -> dict:
    """Identify clathrate cages (TRACE): ring perception -> cage assembly -> face-count typing.

    Returns per-type cage counts (5^12, 5^12 6^2, 5^12 6^4, ...) and the overall structure
    (sI / sII / sH). Validated: sII -> 128x 5^12 + 64x 5^12 6^4; sI -> 16x 5^12 + 48x 5^12 6^2.
    """
    from .analysis.cage import classify_structure
    from .analysis.cage import identify_cages as _identify

    def _f(cmd):
        obj = _pick_object(cmd, selection, object_name)
        cell = _resolve_cell(cmd, obj, box)
        waters = _extract_waters(cmd, selection)
        if len(waters) < 20:
            raise ToolError(f"Need >=20 water molecules for cage detection; found {len(waters)}.")
        res = _identify(waters, cell, rcut_nm, angle_deg)
        return {
            "structure_type": classify_structure(res["counts"]),
            "counts": res["counts"],
            "total_cages": len(res["cages"]),
            "n_valid_rings": res["n_rings"],
        }

    return SESSION.call(_f, timeout=600)


@mcp.tool
def cage_occupancy(
    selection: Annotated[str, Field(description="Selection of the water system.")] = "all",
    guest_selection: Annotated[str | None, Field(description="Selection containing guests (CO2/CH4). Defaults to `selection`.")] = None,
    box: Annotated[list[float] | None, Field(description="Periodic box in nm (3/6/9 values); else from get_symmetry.")] = None,
    object_name: Annotated[str | None, Field(description="Object whose box to use.")] = None,
) -> dict:
    """Compute clathrate cage occupancy: assign guest molecules to detected cages (one per cage)."""
    from .analysis.cage import cage_occupancy as _occ
    from .analysis.cage import classify_structure
    from .analysis.cage import identify_cages as _identify

    def _f(cmd):
        obj = _pick_object(cmd, selection, object_name)
        cell = _resolve_cell(cmd, obj, box)
        waters = _extract_waters(cmd, selection)
        guests = _extract_guests(cmd, guest_selection or selection)
        if len(waters) < 20:
            raise ToolError(f"Need >=20 water molecules; found {len(waters)}.")
        res = _identify(waters, cell)
        occ = _occ(waters, guests, cell, cage_result=res)
        occ["structure_type"] = classify_structure(res["counts"])
        occ["n_guests"] = len(guests)
        return occ

    return SESSION.call(_f, timeout=600)


# Cage-type colors (hex) for wireframe rendering.
_CAGE_HEX = {
    "5^12": "#06b6d4",        # cyan
    "5^12 6^2": "#8b5cf6",    # violet
    "5^12 6^3": "#f59e0b",    # amber
    "5^12 6^4": "#ef4444",    # red
    "5^12 6^5": "#22c55e",    # green
    "5^12 6^6": "#ec4899",    # pink
    "5^12 6^8": "#3b82f6",    # blue
    "4^3 5^6 6^3": "#84cc16",  # lime
}
_CAGE_HEX_DEFAULT = "#9ca3af"  # gray


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]


@mcp.tool
def mark_cages(
    selection: Annotated[str, Field(description="Selection of the water system.")] = "all",
    box: Annotated[list[float] | None, Field(description="Periodic box in nm (3/6/9 values); else from get_symmetry.")] = None,
    object_name: Annotated[str | None, Field(description="Object whose box to use.")] = None,
    edge_radius: Annotated[float, Field(description="Cage edge (cylinder) radius in Angstrom.", gt=0)] = 0.12,
    vertex_radius: Annotated[float, Field(description="Cage vertex (sphere) radius in Angstrom.", gt=0)] = 0.32,
    cage_types: Annotated[list[str] | None, Field(description="Only draw these cage types (e.g. ['5^12','5^12 6^4']); default all.")] = None,
) -> dict:
    """Draw each detected cage as a **wireframe polyhedron** — cylinders along the O-O ring edges
    plus spheres at the water-oxygen vertices, colored by cage type (5^12=cyan, 5^12 6^2=violet,
    5^12 6^4=red, ...). Builds a single CGO object named `cages` for `render_image`.
    """
    import numpy as np

    from .analysis.cage import identify_cages as _identify

    def _f(cmd):
        from pymol.cgo import COLOR, CYLINDER, SPHERE  # float constants; safe on the worker thread

        obj = _pick_object(cmd, selection, object_name)
        cell = _resolve_cell(cmd, obj, box)
        waters = _extract_waters(cmd, selection)
        if len(waters) < 20:
            raise ToolError(f"Need >=20 water molecules; found {len(waters)}.")
        res = _identify(waters, cell)
        opos = [np.asarray(w[0], dtype=float) for w in waters]  # nm
        want = set(cage_types) if cage_types else None

        cgo: list = []
        counts: dict = {}
        for c in res["cages"]:
            if want is not None and c["type"] not in want:
                continue
            rgb = _hex_rgb(_CAGE_HEX.get(c["type"], _CAGE_HEX_DEFAULT))
            counts[c["type"]] = counts.get(c["type"], 0) + 1
            for v in c["vertices"]:
                p = opos[v] * 10.0  # nm -> Angstrom
                cgo += [COLOR, *rgb, SPHERE, float(p[0]), float(p[1]), float(p[2]), vertex_radius]
            for i, j in c["edges"]:
                a = opos[i] * 10.0
                b = (opos[i] + cell.mic(opos[j] - opos[i])) * 10.0  # MIC keeps cages compact across PBC
                cgo += [
                    CYLINDER, float(a[0]), float(a[1]), float(a[2]),
                    float(b[0]), float(b[1]), float(b[2]), edge_radius, *rgb, *rgb,
                ]
        if not cgo:
            raise ToolError("No cages matched the requested types.")
        cmd.delete("cages")
        cmd.load_cgo(cgo, "cages")
        return {"object": "cages", "drawn": counts, "n_cages": sum(counts.values())}

    return SESSION.call(_f, timeout=600)
