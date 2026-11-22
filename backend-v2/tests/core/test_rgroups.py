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


# --- only labels that look like R-group labels (owner decision 2026-11-22) -----------------------
# MolScribe writes a group it did not expand (OAc, BnO, MeO, CO2H...) as an atom alias, and also
# numbers and element counts it misread (555, S7, N3).


@pytest.mark.parametrize(
    "label",
    ["R", "R1", "R10", "R'", "R′", "R″", "R1′", "R′1", "R6″", "Ra", "Rf", "R1a",
     "X", "X1", "Y", "Z", "Z2", "Ar", "Ar1", "n", "m", "Q", "*"],
)  # fmt: skip
def test_rgroup_like_labels_stay(label):
    assert rgroups.as_label(label) == label


@pytest.mark.parametrize(
    ("alias", "label"),
    [("OR", "R"), ("OR3", "R3"), ("R2O", "R2"), ("RaO", "Ra"), ("RO", "R"), ("OR′", "R′")],
)
def test_an_o_linked_label_is_its_r_group(alias, label):
    """MolScribe keeps the linking O in the alias (R2O, OR3): the drawn label is R2, R3."""
    assert rgroups.as_label(alias) == label


@pytest.mark.parametrize(
    ("alias", "label"),
    [("CO2R", "R"), ("COOR", "R"), ("NHR", "R"), ("SR", "R"), ("CH2R", "R"), ("CH2OR1", "R1"),
     ("NR2", "R2"), ("CO2R′", "R′"), ("N(R)2", "R"), ("OCOR3", "R3")],
)  # fmt: skip
def test_an_alias_carrying_one_r_group_is_that_label(alias, label):
    """Review finding 4: MolScribe writes the group around an R as one alias (CO2R, NHR): the
    placeholder is the R in it."""
    assert rgroups.as_label(alias) == label


@pytest.mark.parametrize("alias", ["Br", "Bz", "TMSO", "OTBS", "NR1R2", "CF3", "Ph", "PrO"])
def test_an_alias_without_exactly_one_r_group_is_no_label(alias):
    assert rgroups.as_label(alias) is None


def test_a_co2r_only_structure_keeps_its_label():
    molfile = _molfile("*c1ccccc1", {0: "CO2R"})
    assert rgroup_labels("*c1ccccc1", molfile) == ["R"]


@pytest.mark.parametrize(
    "alias",
    ["OAc", "AcO", "BnO", "MeO", "OMe", "OCH3", "H3CO", "CO2H", "COOH", "Me", "Ac", "Bz",
     "BzO", "Boc", "OTMS", "TMSO", "CF3", "CN", "C2H5", "NMe", "N3", "S7", "O3", "F2", "Br",
     "555", "12", "0", "1*", "Ring A", "aa1", "X-Y", ""],
)  # fmt: skip
def test_abbreviations_numbers_and_atoms_are_no_labels(alias):
    assert rgroups.as_label(alias) is None


def test_an_expanded_abbreviation_leaves_no_placeholder():
    """MolScribe wrote OMe as an aliased dummy atom in the molfile but expanded it in the
    SMILES: the SMILES is a whole compound, no scaffold."""
    molfile = _molfile("*c1ccccc1", {0: "OMe"})
    assert rgroup_labels("COc1ccccc1", molfile) == []


def test_an_abbreviation_on_a_wildcard_atom_stays_a_placeholder():
    """The SMILES still has the wildcard: never a finished compound (COCONUT stays blocked)."""
    molfile = _molfile("*c1ccccc1", {0: "OTMS"})
    assert rgroup_labels("*c1ccccc1", molfile) == ["*"]
    assert rgroup_labels(None, molfile) == ["*"]  # no SMILES to tell: kept as a placeholder


def test_real_labels_beside_abbreviations_stay():
    smiles = "[1*]c1ccc(OC)cc1[2*]"
    molfile = _molfile("[1*]c1ccc(*)cc1[2*]", {0: "R1", 5: "MeO", 8: "R2O"})
    assert rgroup_labels(smiles, molfile) == ["R1", "R2"]


def test_a_smiles_wildcard_is_always_a_placeholder():
    assert rgroup_labels("[555*]CC") == ["*"]
