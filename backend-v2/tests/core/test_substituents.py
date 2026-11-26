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


@pytest.mark.parametrize("text", ["Tig", "Ang", "Glc-Ara", "[drawn]"])
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
    assert RESOLVER_VERSION.startswith("marcus-substituents 3;")


# --- sugars (owner decision 2026-11-26: D-pyranoses, L-rhamnose, anomer open unless printed) ----
# Reference keys: PubChem (CID 5793 D-glucose, 64689 beta-D-glucose, 79025 alpha-D-glucose,
# 439353 beta-D-galactopyranose, 439680 beta-D-mannopyranose, 125409 beta-D-xylopyranose,
# 439710 alpha-L-rhamnose, 441478 beta-D-glucopyranuronic acid).
D_GLUCOSE, BETA_GLC, ALPHA_GLC = (
    "WQZGKKKJIJFFOK-GASJEMHNSA-N", "WQZGKKKJIJFFOK-VFUOTHLCSA-N", "WQZGKKKJIJFFOK-DVKNGEFBSA-N")  # fmt: skip
REFERENCE = {"Gal": "WQZGKKKJIJFFOK-FPRJBGLDSA-N", "Man": "WQZGKKKJIJFFOK-RWOPYEJCSA-N",
             "Xyl": "SRBFZHDQGSBBOR-KKQCNMDGSA-N", "GlcA": "AEMOLEFTQBMNLQ-QIUUJYRFSA-N"}  # fmt: skip


def sugar_key(frag, cap: str) -> str:
    """The InChIKey of a sugar fragment with its `*` replaced by `cap` (the free sugar)."""
    assert isinstance(frag, Fragment) and frag.attachments == 1, frag
    mol = Chem.MolFromSmiles(frag.smiles.replace("*", cap))
    return Chem.MolToInchiKey(mol)


def open_centres(frag, cap: str = "[H]") -> int:
    mol = Chem.MolFromSmiles(frag.smiles.replace("*", cap))
    return sum(1 for _, tag in Chem.FindMolChiralCenters(mol, includeUnassigned=True) if tag == "?")


@pytest.mark.parametrize("text", ["OGlc", "GlcO", "O-Glc", "OGlcp", "O-D-Glc", "Glc-O"])
def test_a_glucoside_oxygen_is_d_glucose_with_its_anomer_open(text):
    frag = resolve(text)
    assert sugar_key(frag, "[H]") == D_GLUCOSE  # * on the anomeric O: the free sugar
    assert open_centres(frag) == 1


def test_glc_alone_attaches_at_the_anomeric_carbon():
    frag = resolve("Glc")
    assert sugar_key(frag, "O") == D_GLUCOSE  # * on C1: an OH there gives the free sugar
    assert open_centres(frag, "O") == 1


@pytest.mark.parametrize("text,want", [("O-β-D-Glc", BETA_GLC), ("β-OGlc", BETA_GLC),
                                       ("OβGlc", BETA_GLC), ("O-α-D-Glc", ALPHA_GLC), ("α-Glc-O", ALPHA_GLC)])  # fmt: skip
def test_an_anomer_printed_in_the_cell_is_set(text, want):
    assert sugar_key(resolve(text), "[H]") == want


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_the_other_d_sugars_with_beta_printed_match_pubchem(name):
    assert sugar_key(resolve(f"O-β-D-{name}"), "[H]") == REFERENCE[name]
    assert open_centres(resolve(f"O{name}")) == 1


def test_rhamnose_is_l():
    assert sugar_key(resolve("O-α-L-Rha"), "[H]") == "SHZGCJCMOBCMKK-HGVZOGFYSA-N"
    assert open_centres(resolve("ORha")) == 1


@pytest.mark.parametrize(
    "text", ["O-L-Glc", "O-D-Rha", "OAra", "Ara", "OGlc2", "OGlcGlc", "Glcp-Glc"]
)
def test_a_sugar_against_its_natural_series_or_unclear_is_not_built(text):
    assert isinstance(resolve(text), str)
