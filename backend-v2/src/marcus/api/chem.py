"""Small RDKit helpers for the API (validation and export). RDKit's log spam is blocked."""

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.rdBase import BlockLogs


def parse_smiles(smiles: str) -> Chem.Mol | None:
    """A sanitized molecule, or None when the SMILES does not parse."""
    if not smiles:
        return None
    _block = BlockLogs()  # noqa: F841 - logs stay blocked while this object lives
    return Chem.MolFromSmiles(smiles)


def parse_molfile(molfile: str) -> Chem.Mol | None:
    """A sanitized molecule, or None when the molfile does not read or sanitize."""
    if not molfile:
        return None
    _block = BlockLogs()  # noqa: F841
    return Chem.MolFromMolBlock(molfile, sanitize=True)


def mol_for_sdf(smiles: str | None, molfile: str | None) -> Chem.Mol | None:
    """The molfile if RDKit can read it, else the SMILES with fresh 2D coordinates."""
    _block = BlockLogs()  # noqa: F841
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
    _block = BlockLogs()  # noqa: F841
    mol = Chem.MolFromMolBlock(molfile)
    return Chem.MolToSmiles(mol) if mol is not None else None
