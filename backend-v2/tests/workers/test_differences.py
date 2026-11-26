"""Where the engines' answers differ, and their common part, stereo-aware
(marcus.workers.differences; owner decision 2026-11-26)."""

import pytest
from rdkit import Chem

from marcus.workers.differences import DifferencesError, differences


def marks(*smiles):
    return differences(list(smiles))["marks"]


def common(*smiles):
    return differences(list(smiles))["common"]


def test_the_same_structure_written_two_ways_has_no_difference():
    a, b = "OCC", "CCO"
    assert marks(a, b) == [[], []]
    assert common(a, b) == [[0, 1, 2], [0, 1, 2]]


def test_a_missing_piece_marks_the_piece_and_the_atom_it_attaches_to():
    # CCO lacks the methyl of CCOC: the methyl in one, the O it should sit on in the other
    assert marks("CCO", "CCOC") == [[2], [3]]
    # the O is still common: only the methyl is not
    assert common("CCO", "CCOC") == [[0, 1, 2], [0, 1, 2]]


def test_another_atom_in_the_same_place_marks_only_the_two_atoms():
    assert marks("CCCl", "CCBr") == [[2], [2]]


def test_another_bond_order_marks_both_ends():
    assert marks("CC=O", "CCO") == [[1, 2], [1, 2]]


def test_another_charge_marks_the_atom():
    assert marks("CC[O-]", "CCO") == [[2], [2]]


def test_an_inverted_stereocentre_is_a_difference():
    a, b = "C[C@H](N)C(=O)O", "C[C@@H](N)C(=O)O"
    assert marks(a, b) == [[1], [1]]
    assert common(a, b) == [[0, 2, 3, 4, 5], [0, 2, 3, 4, 5]]


def test_a_stereocentre_one_answer_leaves_open_is_a_difference():
    assert marks("CC(N)C(=O)O", "C[C@@H](N)C(=O)O") == [[1], [1]]


def test_the_same_centre_written_in_another_order_is_none():
    a = "C[C@H](N)C(=O)O"
    b = "N[C@@H](C)C(=O)O"
    assert Chem.CanonSmiles(a) == Chem.CanonSmiles(b)
    assert marks(a, b) == [[], []]


def test_double_bond_geometry_counts():
    assert marks("C/C=C/C", "C/C=C\\C") == [[1, 2], [1, 2]]
    assert marks("CC=CC", "C/C=C\\C") == [[1, 2], [1, 2]]
    assert marks("C/C=C/C", "C\\C=C\\C") == [[], []]
    # the same geometry given by the other substituent
    a, b = "C/C(F)=C/Cl", "F\\C(C)=C/Cl"
    assert Chem.CanonSmiles(a) == Chem.CanonSmiles(b)
    assert marks(a, b) == [[], []]


def test_indices_are_the_written_atoms_and_a_plain_h_is_never_marked():
    """Atom indices count every written atom ([H] too: CDK's reading, tools.depict); an explicit
    H is no difference, and never a mark itself."""
    a = "[H][C@](C)(N)C(=O)O"
    b = Chem.CanonSmiles(a)
    assert "[H]" not in b
    assert marks(a, b) == [[], []]
    assert common(a, b)[0] == [1, 2, 3, 4, 5, 6]
    other = "C[C@H](N)C(=O)O" if Chem.CanonSmiles("C[C@H](N)C(=O)O") != b else "C[C@@H](N)C(=O)O"
    assert marks(a, other)[0] == [1]


def test_a_symmetric_structure_is_not_marked_through_its_mirror_mapping():
    """meso-butane-2,3-diol against its methyl ether: the diol fits the ether in two ways, one
    through its mirror (every centre inverted). The way that keeps the stereo is taken: only
    the methyl and the O it sits on are marked."""
    diol = "C[C@H](O)[C@@H](C)O"
    assert Chem.CanonSmiles(diol) == Chem.CanonSmiles("C[C@@H](O)[C@H](C)O")  # meso
    ether = Chem.MolFromSmiles("C[C@H](O)[C@@H](C)OC")
    for seed in range(6):
        written = Chem.MolToRandomSmilesVect(ether, 1, randomSeed=seed)[0]
        out = marks(diol, written)
        assert [len(m) for m in out] == [1, 1], written
        assert Chem.MolFromSmiles(diol).GetAtomWithIdx(out[0][0]).GetSymbol() == "O"


def test_the_mirror_mapping_would_mark_the_centres(monkeypatch):
    """The test above is not empty: with one mapping only, some writing is marked wrongly."""
    from marcus.workers import differences as module

    monkeypatch.setattr(module, "MAX_MAPPINGS", 1)
    ether = Chem.MolFromSmiles("C[C@H](O)[C@@H](C)OC")
    sizes = set()
    for seed in range(6):
        written = Chem.MolToRandomSmilesVect(ether, 1, randomSeed=seed)[0]
        sizes.add(len(marks("C[C@H](O)[C@@H](C)O", written)[0]))
    assert max(sizes) > 1


TAXOL = (
    "CC1=C2[C@@H](C(=O)[C@@]3([C@H](C[C@@H]4[C@]([C@H]3[C@@H]([C@@](C2(C)C)(C[C@@H]1OC(=O)"
    "[C@@H]([C@H](C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)OC(=O)C7=CC=CC=C7)(CO4)OC(=O)C)O)C)OC(=O)C"
)
CEMBRENE = "C/C1=C\\CC/C(C)=C/C[C@H](C(C)=C)CC/C(C)=C/CC1"  # a macrocycle with E double bonds


@pytest.mark.parametrize("smiles", [TAXOL, CEMBRENE])
def test_random_writings_of_one_structure_never_differ(smiles):
    mol = Chem.MolFromSmiles(smiles)
    for seed in range(5):
        other = Chem.MolToRandomSmilesVect(mol, 1, randomSeed=seed)[0]
        assert marks(smiles, other) == [[], []], other


def test_one_inverted_centre_of_a_large_structure_is_the_only_mark():
    mol = Chem.MolFromSmiles(TAXOL)
    flipped = Chem.Mol(mol)
    centre = next(
        a for a in flipped.GetAtoms() if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED
    )
    centre.InvertChirality()
    a = Chem.MolToSmiles(mol)
    b = Chem.MolToRandomSmilesVect(flipped, 1, randomSeed=3)[0]
    out = marks(a, b)
    assert len(out[0]) == 1 and len(out[1]) == 1
    assert (
        Chem.MolFromSmiles(a).GetAtomWithIdx(out[0][0]).GetChiralTag()
        != Chem.ChiralType.CHI_UNSPECIFIED
    )


def test_three_answers_mark_what_differs_from_any_other():
    out = differences(["CCO", "OCC", "CCOC"])
    assert out["marks"] == [[2], [0], [3]]
    assert out["common"] == [[0, 1, 2], [0, 1, 2], [0, 1, 2]]


def test_decimers_r_tokens_are_compared_as_placeholder_atoms():
    """DECIMER's R-group answer ([R1]; RDKit refuses it) counts (owner, 2026-11-26): an R token
    is a placeholder atom, the same as another engine's `*` whatever its number."""
    assert marks("[R1]c1ccccc1", "*c1ccccc1") == [[], []]
    assert marks("[R1]c1ccccc1", "*c1ccccc1C") == [[6], [7]]


def test_an_isotope_h_is_an_atom_and_is_marked():
    """[3H] (an engine's misreading) changes the InChIKey: the atom is marked, and where it sits."""
    out = differences(["CC[3H]", "CC"])
    assert out["marks"] == [[2], [1]]


def test_a_search_out_of_time_gives_the_part_found_and_says_rough(monkeypatch):
    """RDKit's MCS often cannot prove the largest part in time: the part found so far is used
    (marks right or too wide), flagged; an exact answer is not flagged."""
    from rdkit.Chem import rdFMCS

    from marcus.workers import differences as module

    assert differences(["CCO", "CCOC"])["rough"] is False
    real = rdFMCS.FindMCS

    class Canceled:
        def __init__(self, found):
            self.smartsString, self.numAtoms, self.canceled = "[#6]-,:[#6]", 2, True

    monkeypatch.setattr(module.rdFMCS, "FindMCS", lambda *a, **k: Canceled(real(*a, **k)))
    out = differences(["CCO", "CCOC"])
    assert out["rough"] is True
    assert out["marks"] == [[2], [2, 3]] and out["common"] == [[0, 1], [0, 1]]


def test_the_time_budget_is_for_all_pairs(monkeypatch):
    from marcus.workers import differences as module

    monkeypatch.setattr(module, "BUDGET_S", -1.0)
    with pytest.raises(DifferencesError, match="timed out"):
        differences(["CCO", "CCOC"])


@pytest.mark.parametrize("smiles", [["CCO"], ["CCO", "not a smiles"], ["CCO", ""], ["C"] * 7])
def test_bad_input_is_refused(smiles):
    with pytest.raises(DifferencesError):
        differences(smiles)
