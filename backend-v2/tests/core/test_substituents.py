"""Substituent text -> fragment (marcus.core.substituents, Markush Phase 3): the built-in table,
condensed formulas, then the vendored BChemLookup (CC0); anything else is a reason, never a
guess."""

from hashlib import sha256
from pathlib import Path

import pytest
from rdkit import Chem

from marcus.core import substituents
from marcus.core.substituents import (
    BCHEMLOOKUP_COMMIT,
    RESOLVER_VERSION,
    Fragment,
    parse_condensed,
    resolve,
)


def canon(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def same(frag, smiles: str, attachments: int = 1) -> bool:
    assert isinstance(frag, Fragment), frag
    return canon(frag.smiles) == canon(smiles) and frag.attachments == attachments


def test_vendored_bchemlookup_is_the_pinned_file():
    d = Path(substituents.__file__).parent / "data" / "bchemlookup"
    assert (
        sha256((d / "abbreviations.smi").read_bytes()).hexdigest()
        == "70f0e4076f7c38230a7a861722fda26d6cab3053817d31dacc93c0eaa75a1e76"
    )
    assert (
        sha256((d / "LICENSE").read_bytes()).hexdigest()
        == "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
    )
    assert BCHEMLOOKUP_COMMIT in RESOLVER_VERSION
    assert BCHEMLOOKUP_COMMIT in (d / "SOURCE").read_text()


@pytest.mark.parametrize(
    "text,smiles",
    [
        ("H", "[H]*"), ("OH", "*O"), ("F", "*F"), ("Cl", "*Cl"), ("Br", "*Br"), ("I", "*I"),
        ("CH3", "*C"), ("Me", "*C"), ("OCH3", "*OC"), ("OMe", "*OC"), ("NH2", "*N"),
        ("CHO", "*C=O"), ("COOH", "*C(=O)O"), ("CH2OH", "*CO"), ("NO2", "*[N+](=O)[O-]"),
        ("CN", "*C#N"), ("SH", "*S"), ("Et", "*CC"), ("OAc", "*OC(C)=O"), ("Ac", "*C(C)=O"),
    ],
)  # fmt: skip
def test_the_builtin_table(text, smiles):
    assert same(resolve(text), smiles)


@pytest.mark.parametrize(
    "text,smiles",
    [("−OCH3", "*OC"), ("HO−", "*O"), ("AcO", "*OC(C)=O"), ("MeO", "*OC"), ("CH₃", "*C"),
     (" O Me ", "*OC"), ("- CH2OH", "*CO")],
)  # fmt: skip
def test_normalisation_and_the_leftward_mirror(text, smiles):
    assert same(resolve(text), smiles)


@pytest.mark.parametrize(
    "text,smiles",
    [("CH2CH3", "*CC"), ("CH(CH3)CH3", "*C(C)C"), ("CH2CH=CH2", "*CC=C"), ("CH2CN", "*CC#N"),
     ("OCH2OMe", "*OCOC"), ("C(CH3)3", "*C(C)(C)C"), ("CH2CH2CH3", "*CCC")],
)  # fmt: skip
def test_condensed_formulas(text, smiles):
    assert same(resolve(text), smiles)
    assert parse_condensed(text) is not None


@pytest.mark.parametrize(
    "text,smiles",
    [("i-Pr", "*C(C)C"), ("BnO", "*OCc1ccccc1"), ("n-Bu", "*CCCC"), ("Ph", "*c1ccccc1")],
)
def test_bchemlookup_groups(text, smiles):
    assert same(resolve(text), smiles)


def test_bchemlookup_ch2_is_a_two_point_bridge():
    """CH2 alone is no one-point group (a condensed parse fails its valence); BChemLookup lists
    it as the methylene bridge *C*, which substitution accepts only between two neighbouring
    labels."""
    assert parse_condensed("CH2") is None
    assert same(resolve("CH2"), "*C*", 2)


def test_a_bridge_has_two_attachments():
    assert same(resolve("−OCH2O−"), "*OCO*", 2)
    assert resolve("–OCH2O–") == resolve("−OCH2O−")


@pytest.mark.parametrize("text", ["NO", "CO", "ome", "CH3CH2", "2", ""])
def test_text_that_could_mean_two_things_is_not_guessed(text):
    assert resolve(text) == f'unknown substituent "{text}"'


@pytest.mark.parametrize("text", ["S", "N", "NH2·HCl", "NH3Cl"])
def test_bchemlookup_entries_without_one_or_two_attachments_are_dropped(text):
    assert isinstance(resolve(text), str)


def test_nh2_itself_still_resolves():
    assert same(resolve("NH2"), "*N")


@pytest.mark.parametrize("text", ["Tig", "Ang", "β-D-Glc", "Glc-Ara", "[drawn]"])
def test_non_goals_are_unknown(text):
    assert resolve(text) == f'unknown substituent "{text}"'


def test_the_condensed_parser_stays_fast_on_long_branchy_text():
    import time

    start = time.monotonic()
    assert parse_condensed("C" + "(OH)" * 16 + "OH") is None
    parse_condensed("C" + "(CH3)" * 14)
    assert time.monotonic() - start < 1.0


def test_oco_is_not_mirrored_into_a_carboxylate():
    assert resolve("OCO") == 'unknown substituent "OCO"'


def test_the_version_names_the_rule_set():
    assert RESOLVER_VERSION.startswith("marcus-substituents 2;")
