"""Chiral flag of the engines' molfiles.

MolNexTR and MolScribe write their molfiles with RDKit's MolToMolBlock, which always writes
chiral flag 0 (relative stereo). Ketcher (Indigo) then reads every stereocentre as "AND
Enantiomer", while the same structure's SMILES reads as absolute. The SMILES is what MARCUS
keeps and exports, and the CDK molfile of a SMILES (marcus.workers.tools.smiles_to_molfile)
has flag 1 when it has stereo, so an engine molfile with wedge bonds gets flag 1 too.

Text only: the rest of the molfile (atom positions, aliases) stays byte for byte.
"""


def absolute_stereo(molfile: str | None) -> str | None:
    """The V2000 molfile with chiral flag 1 when a bond is a wedge (1) or hash (6); any other
    input (V3000, no wedges, flag already set, unreadable) comes back unchanged."""
    if not molfile:
        return molfile
    lines = molfile.splitlines(keepends=True)
    if len(lines) < 4:
        return molfile
    counts = lines[3]
    if "V2000" not in counts or len(counts) < 15 or counts[12:15] != "  0":
        return molfile
    try:
        atoms, bonds = int(counts[0:3]), int(counts[3:6])
    except ValueError:
        return molfile
    bond_lines = lines[4 + atoms : 4 + atoms + bonds]
    if len(bond_lines) != bonds:
        return molfile
    if not any(line[9:12].strip() in ("1", "6") for line in bond_lines):
        return molfile
    lines[3] = counts[:12] + "  1" + counts[15:]
    return "".join(lines)
