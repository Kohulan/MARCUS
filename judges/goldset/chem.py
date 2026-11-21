"""Shared structure standardisation for the gold-set builder and scorer.

Both sides (COCONUT expected structures and MARCUS predictions) go through
exactly the same function, so a match means "same molecule after the same
clean-up", not "same string".

Steps (recorded in the manifest as STANDARDISATION):
  1. Chem.MolFromSmiles (full sanitisation). Failure -> invalid.
  2. rdMolStandardize.Normalizer  (functional-group normal forms, e.g. nitro).
  3. rdMolStandardize.LargestFragmentChooser(preferOrganic=True)  (drop salts,
     counter-ions, solvent).  Metals are NOT disconnected first.
  4. rdMolStandardize.Uncharger  (neutralise where a neutral form exists).
  5. Canonical isomeric SMILES + standard InChIKey of the result.
No tautomer canonicalisation: RDKit's canonical tautomer can drop or move
stereo and is slow; the standard InChI already merges mobile-H tautomers.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rdkit import Chem, RDLogger, rdBase
from rdkit.Chem import DataStructs, rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize

RDLogger.DisableLog("rdApp.*")

STANDARDISATION = (
    f"RDKit {rdBase.rdkitVersion}: MolFromSmiles(sanitize) -> Normalizer -> "
    "LargestFragmentChooser(preferOrganic=True) -> Uncharger; no metal "
    "disconnection; no tautomer canonicalisation; standard InChIKey"
)

_normalizer = rdMolStandardize.Normalizer()
_largest = rdMolStandardize.LargestFragmentChooser(preferOrganic=True)
_uncharger = rdMolStandardize.Uncharger()
_mfpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


@dataclass(frozen=True)
class Std:
    ok: bool
    smiles: str | None = None
    inchikey: str | None = None  # full 27-char key, None if InChI failed (e.g. '*' atoms)
    error: str | None = None

    @property
    def first_block(self) -> str | None:
        return self.inchikey.split("-")[0] if self.inchikey else None


def _std_mol(smiles: str):
    if not isinstance(smiles, str) or not smiles.strip():
        return None, "empty SMILES"
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return None, "RDKit could not parse SMILES"
    try:
        mol = _normalizer.normalize(mol)
        mol = _largest.choose(mol)
        mol = _uncharger.uncharge(mol)
        Chem.SanitizeMol(mol)
    except Exception as exc:  # noqa: BLE001 - RDKit raises many types
        return None, f"standardisation failed: {type(exc).__name__}: {exc}"
    return mol, None


@lru_cache(maxsize=200_000)
def standardise(smiles: str) -> Std:
    mol, err = _std_mol(smiles)
    if mol is None:
        return Std(ok=False, error=err)
    std_smiles = Chem.MolToSmiles(mol)
    try:
        key = Chem.MolToInchiKey(mol) or None
    except Exception:  # noqa: BLE001
        key = None
    return Std(ok=True, smiles=std_smiles, inchikey=key)


@lru_cache(maxsize=200_000)
def fingerprint(std_smiles: str):
    """Morgan r=2, 2048 bits, on the standardised SMILES."""
    mol = Chem.MolFromSmiles(std_smiles)
    if mol is None:
        return None
    return _mfpgen.GetFingerprint(mol)


def tanimoto(fp_a, fps_b) -> float:
    """Max Tanimoto of fp_a against a list of fingerprints (0.0 if empty)."""
    if fp_a is None or not fps_b:
        return 0.0
    return max(DataStructs.BulkTanimotoSimilarity(fp_a, fps_b))
