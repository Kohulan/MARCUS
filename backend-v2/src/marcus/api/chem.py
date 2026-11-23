"""Small RDKit helpers for the API (validation and export). RDKit's log spam is blocked.

RDKit holds the GIL while it parses, so the API never calls these on its event loop or in a
thread: request-time calls go through marcus.api.chempool (a separate process).
"""

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.rdBase import BlockLogs

from marcus.core.rgroups import rgroup_labels


def parse_smiles(smiles: str) -> Chem.Mol | None:
    """A sanitized molecule, or None when the SMILES does not parse."""
    if not smiles:
        return None
    with BlockLogs():
        return Chem.MolFromSmiles(smiles)


def parse_molfile(molfile: str) -> Chem.Mol | None:
    """A sanitized molecule, or None when the molfile does not read or sanitize."""
    if not molfile:
        return None
    with BlockLogs():
        return Chem.MolFromMolBlock(molfile, sanitize=True)


MAX_CURATION_ATOMS = 1000  # bounds the parse time of one curated molfile (~0.1 s)


def curation_error(smiles: str | None, molfile: str | None) -> tuple[str, str] | None:
    """(field, message) for the first curated value RDKit refuses, else None. CPU-bound: run
    it in marcus.api.chempool."""
    if smiles is not None and parse_smiles(smiles) is None:
        return "smiles", "SMILES could not be parsed"
    if molfile is not None:
        with BlockLogs():
            raw = Chem.MolFromMolBlock(molfile, sanitize=False)  # cheap; counts atoms first
            if raw is not None and raw.GetNumAtoms() > MAX_CURATION_ATOMS:
                return "molfile", f"molfile must have at most {MAX_CURATION_ATOMS} atoms"
            if raw is None or parse_molfile(molfile) is None:
                return "molfile", "molfile could not be parsed"
    return None


def check_curation(
    smiles: str | None, molfile: str | None
) -> tuple[tuple[str, str] | None, list[str]]:
    """(curation_error, the R-group labels of the curated structure): one trip to
    marcus.api.chempool for the curation route. No labels for a structure RDKit refuses."""
    error = curation_error(smiles, molfile)
    return error, ([] if error is not None else rgroup_labels(smiles, molfile))


def mol_for_sdf(smiles: str | None, molfile: str | None) -> Chem.Mol | None:
    """The molfile if RDKit can read it, else the SMILES with fresh 2D coordinates."""
    with BlockLogs():
        if molfile:
            mol = Chem.MolFromMolBlock(molfile)
            if mol is not None:
                return mol
        mol = parse_smiles(smiles) if smiles else None
        if mol is not None:
            AllChem.Compute2DCoords(mol)
        return mol


def smiles_from_molfile(molfile: str | None) -> str | None:
    if not molfile:
        return None
    with BlockLogs():
        mol = Chem.MolFromMolBlock(molfile)
        return Chem.MolToSmiles(mol) if mol is not None else None


def inchikey(kind: str, value: str) -> str | None:
    """The InChIKey of a SMILES (`kind` "smiles") or molfile ("molfile"); None when RDKit cannot
    read it or it has placeholder atoms (an R-group scaffold is not one compound)."""
    mol = parse_smiles(value) if kind == "smiles" else parse_molfile(value)
    if mol is None or any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        return None
    with BlockLogs():
        return Chem.MolToInchiKey(mol) or None


def inchikeys(items: list[tuple[str, str]]) -> list[str | None]:
    """inchikey of each (kind, value): one trip to marcus.api.chempool for a whole paper."""
    return [inchikey(kind, value) for kind, value in items]
