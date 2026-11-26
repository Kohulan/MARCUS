"""The engines' agreement and the structure a segment shows (marcus.core.agreement)."""

from dataclasses import dataclass

import pytest

from marcus.core import agreement

ETHANOL = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
ETHANOL_D = "LFQSCWFLJHTTHZ-ZZZZZZZZSA-N"  # same first block, other stereo / protons
PROPANE = "ATUOYWHBWRKTHZ-UHFFFAOYSA-N"


@dataclass
class P:
    engine: str
    inchikey: str | None
    valid: bool = True
    name: str = ""


def test_three_agree_on_the_full_key():
    ps = [P("molscribe", ETHANOL), P("molnextr", ETHANOL), P("decimer", ETHANOL)]
    assert agreement.agree_count(ps) == 3
    assert agreement.badge(ps) == "agree3"
    assert [p.engine for p in agreement.majority(ps)] == ["decimer", "molnextr", "molscribe"]
    assert agreement.pick_prediction(ps, "decimer").engine == "decimer"


def test_other_stereo_is_no_agreement():
    """Owner decision 2026-11-26: agree = the same full InChIKey. Two with the same key and a
    third with other stereo: "2 agree", the pick one of the two."""
    ps = [P("molscribe", ETHANOL), P("molnextr", ETHANOL), P("decimer", ETHANOL_D)]
    assert agreement.agree_count(ps) == 2 and agreement.badge(ps) == "agree2"
    assert [p.engine for p in agreement.majority(ps)] == ["molnextr", "molscribe"]
    assert agreement.pick_prediction(ps, "decimer").engine == "molnextr"


def test_stereo_differs_when_only_the_connectivity_is_shared():
    """No two share the full key but two share the first block: "Stereo differs"; nothing
    agrees, and the pick falls back to the connectivity group as before."""
    ps = [P("molscribe", ETHANOL_D), P("molnextr", ETHANOL), P("decimer", PROPANE)]
    assert agreement.badge(ps) == "stereo"
    assert agreement.agree_count(ps) == 0 and agreement.majority(ps) == []
    assert agreement.pick_prediction(ps, "decimer").engine == "molnextr"
    assert agreement.pick_prediction(ps, "molscribe").engine == "molscribe"


def test_differ_and_no_badge():
    ps = [P("molscribe", PROPANE), P("decimer", ETHANOL)]
    assert agreement.badge(ps) == "differ"
    # fewer than two with a key: nothing to compare
    assert agreement.badge([P("decimer", ETHANOL)]) is None
    assert agreement.badge([P("decimer", ETHANOL), P("molscribe", None, valid=False)]) is None


def test_two_agree_and_their_structure_is_shown():
    ps = [P("molscribe", ETHANOL), P("molnextr", ETHANOL), P("decimer", PROPANE)]
    assert agreement.agree_count(ps) == 2
    # the paper's engine is not in the majority: the majority's first engine
    assert agreement.pick_prediction(ps, "decimer").engine == "molnextr"
    # the paper's engine is in it: its own
    assert agreement.pick_prediction(ps, "molscribe").engine == "molscribe"


@pytest.mark.parametrize(
    "ps",
    [
        [P("decimer", ETHANOL), P("molnextr", PROPANE), P("molscribe", None)],
        [P("decimer", ETHANOL), P("molnextr", ETHANOL, valid=False), P("molscribe", PROPANE)],
        [P("decimer", ETHANOL)],
        [],
    ],
)
def test_invalid_or_empty_never_agrees(ps):
    assert agreement.agree_count(ps) == 0 and agreement.majority(ps) == []


def test_without_a_majority_the_old_rule():
    ps = [P("molscribe", PROPANE, name="new"), P("decimer", ETHANOL, name="own")]
    assert agreement.pick_prediction(ps, "decimer").name == "own"  # the paper's engine
    assert agreement.pick_prediction(ps, "molnextr").name == "new"  # else the newest valid
    assert agreement.pick_prediction([P("decimer", None, valid=False)], "decimer") is None


def test_each_engines_newest_counts_and_others_not_at_all():
    ps = [
        P("molnextr", PROPANE),  # newest MolNexTR: no longer agrees
        P("molnextr", ETHANOL),
        P("decimer-hand", ETHANOL),  # not one of the three
        P("decimer", ETHANOL),
    ]
    assert agreement.agree_count(ps) == 0


def test_inchikey_of():
    assert agreement.inchikey_of("CCO", True) == ETHANOL
    assert agreement.inchikey_of("CCO", False) is None
    assert agreement.inchikey_of("", True) is None
    assert agreement.inchikey_of("C1CC", True) is None  # does not parse
    assert agreement.inchikey_of("*CC", True) is None  # a scaffold: not one compound


# --- MolParser replaced MolNexTR (2026-11-25) --------------------------------------------------


def test_the_three_engines_that_read_are_decimer_molparser_molscribe():
    assert agreement.ENGINES == ("decimer", "molparser", "molscribe")
    assert agreement.SLOTS["molnextr"] == "molparser"


def test_an_old_molnextr_prediction_fills_molparsers_slot():
    """An old paper: MolNexTR's prediction counts where MolParser's would (the badge and the
    shown structure of old cards do not change)."""
    ps = [P("molscribe", PROPANE), P("molnextr", ETHANOL), P("decimer", ETHANOL)]
    assert [p.engine for p in agreement.majority(ps)] == ["decimer", "molnextr"]
    assert agreement.pick_prediction(ps, "molnextr").engine == "molnextr"


def test_molparser_wins_its_slot_over_an_older_molnextr_one():
    """A MolParser prediction (e.g. Compare on an old paper) takes the slot, even when a
    MolNexTR one is newer: never four engines, never two votes for one slot."""
    ps = [P("molnextr", ETHANOL), P("molparser", PROPANE), P("decimer", ETHANOL)]
    newest = agreement.newest_by_engine(ps)
    assert sorted(newest) == ["decimer", "molparser"]
    assert newest["molparser"].engine == "molparser"
    assert agreement.agree_count(ps) == 0


def test_shown_prediction_falls_back_to_the_newest():
    """The prediction a card shows: the pick, else (no valid one) the newest (cardState)."""
    ps = [P("molscribe", None, valid=False), P("decimer", None, valid=False)]
    assert agreement.shown_prediction(ps, "decimer") is ps[0]
    assert agreement.shown_prediction([], "decimer") is None
    ok = [P("molscribe", None, valid=False), P("decimer", ETHANOL)]
    assert agreement.shown_prediction(ok, "decimer").engine == "decimer"
