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
