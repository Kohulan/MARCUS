"""absolute_stereo: a V2000 molfile with wedge bonds gets chiral flag 1 (absolute stereo)."""

from rdkit import Chem

from marcus.core.molfile import absolute_stereo


def _rdkit_molfile(smiles: str) -> str:
    return Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))  # RDKit always writes flag 0


def _flag(molfile: str) -> str:
    return molfile.splitlines()[3][12:15]


def test_wedged_molfile_gets_flag_1_and_nothing_else_changes():
    before = _rdkit_molfile("C[C@H](N)C(=O)O")
    assert _flag(before) == "  0"
    after = absolute_stereo(before)
    assert _flag(after) == "  1"
    changed = [i for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines())) if a != b]
    assert changed == [3]
    assert len(after) == len(before)


def test_hashed_wedge_counts_too():
    before = _rdkit_molfile("C[C@@H](N)C(=O)O")
    assert _flag(absolute_stereo(before)) == "  1"


def test_no_wedges_keeps_flag_0():
    before = _rdkit_molfile("CC(N)C(=O)O")
    assert absolute_stereo(before) == before


def test_double_bond_stereo_alone_keeps_flag_0():
    before = _rdkit_molfile("C/C=C/C")
    assert absolute_stereo(before) == before


def test_crlf_line_ends_are_kept():
    before = _rdkit_molfile("C[C@H](N)C(=O)O").replace("\n", "\r\n")
    after = absolute_stereo(before)
    assert _flag(after) == "  1"
    assert after.count("\r\n") == before.count("\r\n")


def test_flag_already_1_is_unchanged():
    once = absolute_stereo(_rdkit_molfile("C[C@H](N)C(=O)O"))
    assert absolute_stereo(once) == once


def test_v3000_none_empty_and_broken_are_unchanged():
    mol = Chem.MolFromSmiles("C[C@H](N)C(=O)O")
    v3000 = Chem.MolToMolBlock(mol, forceV3000=True)
    assert absolute_stereo(v3000) == v3000
    assert absolute_stereo(None) is None
    assert absolute_stereo("") == ""
    for broken in ("not a molfile", "\n\n\n  x  y  0  0  0  0  0  0  0  0999 V2000\n"):
        assert absolute_stereo(broken) == broken
    truncated = "\n".join(_rdkit_molfile("C[C@H](N)C(=O)O").splitlines()[:6])
    assert absolute_stereo(truncated) == truncated
