"""Scaffold + R-group row -> the full molecule (marcus.core.enumeration, Markush Phase 3). The
expected structures are written by hand from the paper (JNP 10.1021/acs.jnatprod.6c00411,
Table 1) and compared as InChIKeys computed by RDKit at test time."""

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from marcus.core.enumeration import (
    BRIDGE,
    NO_COMPOUND,
    NOT_A_LABEL,
    NOT_ONE_BOND,
    TWICE,
    UNLABELLED_POINT,
    build_row,
    build_rows,
    scaffold_of,
)


def key(smiles: str) -> str:
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


SCAFFOLD_20 = "O=c1c(-c2cc([2*])c([3*])cc2[1*])coc2ccccc12"  # B ring R1/R2/R3
ROWS_20 = [  # PMC13200251 gold rows, as stored (R3 "" where −OCH2O− spans R2+R3)
    {"compound": "20a", "groups": {"R1": "H", "R2": "OH", "R3": "H"}},
    {"compound": "20b", "groups": {"R1": "H", "R2": "OCH3", "R3": "H"}},
    {"compound": "20c", "groups": {"R1": "H", "R2": "OCH3", "R3": "OCH3"}},
    {"compound": "20d", "groups": {"R1": "H", "R2": "−OCH2O−", "R3": ""}},
    {"compound": "20e", "groups": {"R1": "OCH3", "R2": "OCH3", "R3": "OCH3"}},
    {"compound": "20f", "groups": {"R1": "OCH3", "R2": "−OCH2O−", "R3": ""}},
]
FULL_20 = {
    "20a": "O=c1c(-c2cc(O)ccc2)coc2ccccc12",
    "20b": "O=c1c(-c2cc(OC)ccc2)coc2ccccc12",
    "20c": "O=c1c(-c2cc(OC)c(OC)cc2)coc2ccccc12",
    "20d": "O=c1c(-c2cc3OCOc3cc2)coc2ccccc12",
    "20e": "O=c1c(-c2cc(OC)c(OC)cc2OC)coc2ccccc12",
    "20f": "O=c1c(-c2cc3OCOc3cc2OC)coc2ccccc12",
}


def aliased_molfile(smiles: str, alias: dict[int, str] | None = None) -> str:
    """A molfile of a [n*] SMILES whose dummies carry the alias Rn (or `alias[n]`), as MolScribe
    and MolParser write them."""
    mol = Chem.MolFromSmiles(smiles)
    for a in mol.GetAtoms():
        if a.GetAtomicNum() == 0:
            n = a.GetIsotope()
            a.SetProp("molFileAlias", (alias or {}).get(n, f"R{n}"))
            a.SetIsotope(0)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_jnp_table_1_rows_build_the_right_molecules():
    out = build_rows(SCAFFOLD_20, None, ROWS_20)
    assert {o["compound"]: o.get("inchikey") for o in out} == {
        c: key(s) for c, s in FULL_20.items()
    }
    assert all("reason" not in o for o in out)


def test_the_molfile_scaffold_builds_the_same():
    out = build_rows(None, aliased_molfile(SCAFFOLD_20), ROWS_20)
    assert {o["compound"]: o["inchikey"] for o in out} == {c: key(s) for c, s in FULL_20.items()}


def test_a_decimer_scaffold_with_r_tokens_builds():
    out = build_rows("O=c1c(-c2cc([R2])c([R3])cc2[R1])coc2ccccc12", None, ROWS_20[:3])
    assert [o["inchikey"] for o in out] == [key(FULL_20[c]) for c in ("20a", "20b", "20c")]


def test_a_label_drawn_twice_gets_the_group_twice():
    (out,) = build_rows("[1*]c1ccc([1*])cc1", None, [{"compound": "x", "groups": {"R1": "OMe"}}])
    assert out["inchikey"] == key("COc1ccc(OC)cc1")


def test_h_on_an_aromatic_nitrogen_keeps_the_ring():
    rows = [{"compound": "h", "groups": {"R1": "H"}}, {"compound": "m", "groups": {"R1": "Me"}}]
    h, m = build_rows("[1*]n1ccc2ccccc21", None, rows)
    assert h["inchikey"] == key("c1ccc2[nH]ccc2c1")
    assert m["inchikey"] == key("Cn1ccc2ccccc21")


def test_stereo_of_the_scaffold_is_kept():
    (out,) = build_rows("O[C@@H](C)[1*]", None, [{"compound": "s", "groups": {"R1": "Et"}}])
    assert out["inchikey"] == key("O[C@@H](C)CC")
    assert out["inchikey"] != key("O[C@H](C)CC")


@pytest.mark.parametrize(
    "groups,reason",
    [
        ({"R1": "Tig", "R2": "H", "R3": "H"}, 'unknown substituent "Tig"'),
        ({"R1": "H", "R2": "OH"}, "no value for R3"),
        ({"R1": "H", "R2": "OH", "R3": ""}, "no value for R3"),
        ({"R1": "H", "R2": "OH", "R3": "H", "R4": "H"}, "the scaffold has no R4"),
        ({"R1": "−OCH2O−", "R2": "", "R3": "H"}, BRIDGE.format("−OCH2O−")),
        ({"R1": "H", "R2": "−OCH2O−", "R3": "−OCH2O−"}, BRIDGE.format("−OCH2O−")),
    ],
)
def test_the_row_fails_with_the_reason(groups, reason):
    assert build_row(scaffold_of(SCAFFOLD_20, None), groups) == reason


def test_a_carried_alias_fails_the_row():
    molfile = aliased_molfile("[1*]c1ccccc1", {1: "OR1"})
    (out,) = build_rows(None, molfile, [{"compound": "c", "groups": {"R1": "Me"}}])
    assert out["reason"] == NOT_A_LABEL.format("OR1")


def test_a_label_inside_a_ring_fails():
    (out,) = build_rows("C1CC[1*]C1", None, [{"compound": "r", "groups": {"R1": "O"}}])
    assert out["reason"] == NOT_ONE_BOND.format("R1")


def test_an_unlabelled_point_fails_every_row():
    rows = [{"compound": "u", "groups": {"R1": "H"}}, {"compound": "v", "groups": {"R1": "Me"}}]
    assert [o["reason"] for o in build_rows("*c1ccccc1[1*]", None, rows)] == [UNLABELLED_POINT] * 2


def test_duplicate_compound_ids_fail_both_rows():
    rows = [
        {"compound": "20a", "groups": {"R1": "H"}},
        {"compound": " 20a ", "groups": {"R1": "Me"}},
    ]
    out = build_rows("[1*]c1ccccc1", None, rows)
    assert [o["reason"] for o in out] == [TWICE.format("20a")] * 2
    assert [o["compound"] for o in out] == ["20a", "20a"]


def test_a_row_without_compound_id_fails():
    (out,) = build_rows("[1*]c1ccccc1", None, [{"compound": "  ", "groups": {"R1": "H"}}])
    assert out["reason"] == NO_COMPOUND


def test_an_unreadable_scaffold_fails_every_row():
    (out,) = build_rows("C1CC(", None, [{"compound": "z", "groups": {"R1": "H"}}])
    assert out["reason"] == "the scaffold could not be read"
