import uuid

from rdkit import Chem

from marcus.api.chem import inchikey, inchikeys
from marcus.core.main_figure import Entry, link_repeats


def _ids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_no_main_page_no_links():
    (s,) = _ids(1)
    assert link_repeats([Entry(s, 0, "K")], None) == {}


def test_a_repeat_links_to_the_first_main_structure_of_its_key():
    m1, m2, m3, r1, r2, r3 = _ids(6)
    entries = [
        Entry(r1, 0, "A"),  # before the main page: still a repeat
        Entry(m1, 1, "A"),
        Entry(m2, 1, "A"),  # the same key twice on the main page: both stay
        Entry(m3, 1, None),
        Entry(r2, 2, "A"),
        Entry(r3, 2, "B"),  # not on the main page
    ]
    assert link_repeats(entries, 1) == {r1: m1, r2: m1}


def test_structures_without_a_key_never_link():
    m, r = _ids(2)
    assert link_repeats([Entry(m, 0, None), Entry(r, 1, None)], 0) == {}


def test_a_compound_id_links_as_a_key_does():
    """The hook for phase B item 4 (the compound ID read under the drawing)."""
    m, r, other = _ids(3)
    entries = [
        Entry(m, 0, "A", compound_id="12"),
        Entry(r, 1, "B", compound_id="12"),
        Entry(other, 1, "C", compound_id=None),
    ]
    assert link_repeats(entries, 0) == {r: m}


def test_inchikey_of_smiles_and_molfile():
    key = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"  # ethanol
    assert inchikey("smiles", "CCO") == key
    assert inchikey("smiles", "OCC") == key
    assert inchikey("molfile", Chem.MolToMolBlock(Chem.MolFromSmiles("CCO"))) == key
    assert inchikey("smiles", "*CC") is None  # a scaffold is not one compound
    assert inchikey("smiles", "not a smiles") is None
    assert inchikeys([("smiles", "CCO"), ("smiles", "C1")]) == [key, None]


def test_group_status_rule():
    from marcus.core.main_figure import group_status

    assert group_status(["unchecked", "accepted"]) == "accepted"
    assert group_status(["rejected", "accepted"]) == "accepted"
    assert group_status(["rejected", "rejected"]) == "rejected"
    assert group_status(["rejected", None]) == "unchecked"
    assert group_status([None, None]) == "unchecked"


def test_chosen_member_and_count_fix():
    from marcus.core.main_figure import CountFix, chosen_member, count_fix

    m, r1, r2, m2, r3, m3, r4 = _ids(7)
    status = {m: "unchecked", r1: "rejected", r2: "accepted", m2: "accepted", r3: "accepted",
              m3: "rejected", r4: None}  # fmt: skip
    assert chosen_member(m, [r1, r2], status) == r2  # the first accepted repeat
    assert chosen_member(m2, [r3], status) == m2  # the main one first
    assert chosen_member(m3, [r4], status) == m3  # not accepted: the main one
    fix = count_fix({r1: m, r2: m, r3: m2, r4: m3}, status)
    assert fix == CountFix(
        hidden=frozenset({r1, r2, r3, r4}), promote=frozenset({m}), unreject=frozenset({m3})
    )
    assert (CountFix() | fix) == fix
