"""marcus.core.rgroups: R-group placeholders per engine output (MARKUSH-RESEARCH.md 2.4)."""

import pytest
from rdkit import Chem

from marcus.core import rgroups
from marcus.core.rgroups import rgroup_labels


def _molfile(smiles: str, aliases: dict[int, str]) -> str:
    """A molfile as MolScribe / MolNexTR write one: the drawn labels as atom aliases."""
    mol = Chem.MolFromSmiles(smiles)
    for idx, alias in aliases.items():
        mol.GetAtomWithIdx(idx).SetProp("molFileAlias", alias)
    return Chem.MolToMolBlock(mol)


KETCHER_RGP = """
  Ketcher

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0
    2.0000    0.0000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  RGP  2   2   2   3   1
M  END
"""


@pytest.mark.parametrize(
    ("smiles", "labels"),
    [
        ("[R1]c1ccc([R2])cc1", ["R1", "R2"]),
        ("[R]OC(=O)c1ccccc1", ["R"]),
        ("[R']c1ccccc1[R]", ["R", "R'"]),
        ("[X]c1ccccc1", ["X"]),
        ("[X1]c1ccc([Z])cc1", ["X1", "Z"]),
        ("[R10]C[R2]", ["R2", "R10"]),
        # [Y] beside another R token is an R-group label, not yttrium
        ("[R1]c1ccc([Y])cc1", ["R1", "Y"]),
    ],
)
def test_decimer_r_tokens(smiles, labels):
    assert Chem.MolFromSmiles(smiles) is None  # invalid today: the reason is the R tokens
    assert rgroup_labels(smiles) == labels


def test_decimer_tokens_with_another_error_are_not_a_scaffold():
    # the ring never closes: invalid for its own sake, so it stays plain "Invalid"
    assert rgroup_labels("[R1]c1ccccc") == []


def test_lone_y_is_yttrium():
    assert rgroup_labels("[Y]") == []
    assert rgroup_labels("Cl[Y](Cl)Cl") == []
    # a lone [Y] in a SMILES that fails anyway is still not called an R-group
    assert rgroup_labels("[Y]c1ccccc") == []


def test_yttrium_complex_is_not_flagged():
    # tris(acetylacetonato)yttrium as a disconnected salt SMILES
    acac = "CC(=O)/C=C(/C)[O-]"
    smiles = f"[Y+3].{acac}.{acac}.{acac}"
    assert Chem.MolFromSmiles(smiles) is not None
    assert rgroup_labels(smiles) == []
    assert rgroup_labels(smiles, Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))) == []


@pytest.mark.parametrize(
    ("smiles", "labels"),
    [
        ("*c1ccccc1", ["*"]),
        ("[1*]c1ccccc1[2*]", ["R1", "R2"]),
        ("[*:3]CC", ["R3"]),
        ("[*]OC", ["*"]),
    ],
)
def test_molscribe_dummy_atoms_without_molfile(smiles, labels):
    assert rgroup_labels(smiles) == labels


def test_molscribe_molfile_aliases_give_the_drawn_labels():
    smiles = "[1*]c1ccc(*)cc1O*"
    molfile = _molfile(smiles, {0: "R1", 5: "Ar", 9: "X"})
    assert rgroup_labels(smiles, molfile) == ["Ar", "R1", "X"]


def test_molfile_without_aliases_falls_back_to_isotope_or_star():
    smiles = "[2*]c1ccccc1*"
    assert rgroup_labels(smiles, Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))) == ["R", "R2"]


def test_ketcher_r_group_atoms():
    assert rgroup_labels(None, KETCHER_RGP) == ["R1", "R2"]
    assert rgroup_labels("", KETCHER_RGP) == ["R1", "R2"]


@pytest.mark.parametrize(
    "smiles",
    [
        "CCO",
        "c1ccccc1O",
        "CC(=O)Oc1ccccc1C(=O)O",
        "[Xe]",
        "[Zn+2]",
        "[Rb+].[Cl-]",
        "[2H]C([2H])([2H])O",
        "C[C@H](N)C(=O)O |&1:1|",  # a CXSMILES extension is not part of the structure
    ],
)
def test_normal_molecules_are_not_flagged(smiles):
    mol = Chem.MolFromSmiles(smiles.split()[0])
    assert rgroup_labels(smiles) == []
    assert rgroup_labels(smiles, Chem.MolToMolBlock(mol)) == []


def test_empty_and_garbage():
    assert rgroup_labels("") == []
    assert rgroup_labels(None) == []
    assert rgroup_labels("not a smiles") == []
    assert rgroup_labels("C", "garbage") == []


def test_v3000_molfile():
    mol = Chem.MolFromSmiles("[1*]CC")
    mol.GetAtomWithIdx(0).SetProp("molFileAlias", "R1")
    molfile = Chem.MolToV3KMolBlock(mol)
    assert "V3000" in molfile
    assert rgroup_labels("CC", molfile) == ["R1"]
    assert rgroup_labels("CCO", Chem.MolToV3KMolBlock(Chem.MolFromSmiles("CCO"))) == []


def test_plain_molecules_never_reach_rdkit(monkeypatch):
    """The cheap check keeps RDKit off plain structures (the 0011 backfill and every OCSR
    result go through here)."""

    def boom(*_args):
        raise AssertionError("RDKit was asked")

    monkeypatch.setattr(rgroups, "_parsed_labels", boom)
    molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    assert rgroup_labels("CC(=O)Oc1ccccc1C(=O)O", molfile) == []
