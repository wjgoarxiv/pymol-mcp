"""Shared test fixtures."""

MINIMAL_PDB = """\
HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O
HETATM    2  H1  HOH A   1       0.757   0.586   0.000  1.00  0.00           H
HETATM    3  H2  HOH A   1      -0.757   0.586   0.000  1.00  0.00           H
END
"""


def write_minimal_pdb(tmp_path):
    p = tmp_path / "tiny.pdb"
    p.write_text(MINIMAL_PDB)
    return str(p)
