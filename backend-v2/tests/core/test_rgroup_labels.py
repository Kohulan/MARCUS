"""marcus.core.rgroup_labels: the labels a page's text names, and the labels shown for a
structure (owner decision 2026-11-22: tag, exports and UI list show the labels the page text
names; all of them when it names none)."""

import pytest

from marcus.core import rgroup_labels as rl


def test_the_text_labels_of_a_context_in_their_one_spelling():
    text = "R 1 = OMe; R² = H; R₃ = Me; X = Cl; R' = H; R1′ = Glc; the (Z)-isomer; PAR1; R10"
    assert rl.text_labels(text) == {"R1", "R2", "R3", "X", "R′", "R1′", "R10"}


def test_a_stereo_descriptor_or_a_word_is_no_label():
    assert rl.text_labels("(Z)-configured, (R)-C-7, Rat, Xylose, nm") == set()


def test_shown_labels_are_those_the_page_names_in_order():
    assert rl.shown_labels(["R1", "R2", "Z"], {"R2", "R1"}) == ["R1", "R2"]
    assert rl.shown_labels(["R'", "X"], {"R′"}) == ["R'"]  # spelled either way


def test_a_page_that_names_none_or_no_text_shows_them_all():
    assert rl.shown_labels(["R1", "Z"], set()) == ["R1", "Z"]
    assert rl.shown_labels(["R1", "Z"], None) == ["R1", "Z"]
    assert rl.shown_labels([], {"R1"}) == []


def test_the_unlabelled_point_is_never_named():
    assert rl.shown_labels(["R1", "*"], {"R1"}) == ["R1"]
    assert rl.shown_labels(["*"], {"R1"}) == ["*"]


def _text(text, page):
    return {"label": "text", "text": text, "prov": [{"page_no": page}]}


def test_the_page_index_holds_each_pages_labels_from_the_models_context():
    """Page P (0-based, as the API counts) gets the labels of Docling pages P..P+2, the text
    the model reads for a scaffold on it."""
    doc = {"texts": [_text("3a: R1 = OMe", 1), _text("X = Cl", 3), _text("none here", 5)]}
    assert rl.page_label_index(doc, 5) == {"0": ["R1"], "1": ["R1", "X"], "2": ["X"], "3": ["X"]}


@pytest.mark.parametrize("doc", [{}, {"texts": []}])
def test_a_document_without_text_has_an_empty_index(doc):
    assert rl.page_label_index(doc, 3) == {}


# --- review findings 1 and 2 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["single-crystal X-ray data", "n-butyl", "n-BuLi", "m-CPBA", "E/Z isomers", "Z/E", "Q-TOF MS",
     "X-Ray", "R-configured"],
)  # fmt: skip
def test_chemistry_words_name_no_label(text):
    assert rl.text_labels(text) == set()


def test_a_word_hit_does_not_hide_the_real_labels():
    """R1, R2 drawn only in the figure, "X-ray" in the text: nothing tells, so all stay."""
    assert rl.shown_labels(["R1", "R2", "X"], rl.text_labels("from X-ray data")) == [
        "R1", "R2", "X",
    ]  # fmt: skip


def test_only_a_named_label_beyond_one_letter_decides():
    """A one-letter hit (X, Y, Z, n, m, Q) alone is weak evidence: it decides nothing; once
    another label is named, the one-letter ones named are shown too."""
    assert rl.shown_labels(["R1", "Z"], {"Z"}) == ["R1", "Z"]
    assert rl.shown_labels(["R1", "X", "Z"], {"R1", "X"}) == ["R1", "X"]
    assert rl.shown_labels(["X", "Y", "Z"], {"X", "Y"}) == ["X", "Y", "Z"]


@pytest.mark.parametrize(
    ("text", "labels"),
    [
        ("R1–R4 = H", {"R1", "R2", "R3", "R4"}),
        ("R1-R3 are OMe", {"R1", "R2", "R3"}),
        ("R1-3 = H", {"R1", "R2", "R3"}),
        ("R 1 to R 4", {"R1", "R2", "R3", "R4"}),
        ("R2~R5", {"R2", "R3", "R4", "R5"}),
    ],
)
def test_a_range_names_every_label_in_it(text, labels):
    assert rl.text_labels(text) == labels


@pytest.mark.parametrize(
    ("text", "labels"),
    [("OR1", {"R1"}), ("NR1R2", {"R1", "R2"}), ("R1R2N", {"R1", "R2"}), ("R2Ph", {"R2"}),
     ("R3O", {"R3"}), ("SR4", {"R4"})],
)  # fmt: skip
def test_joined_labels_are_named(text, labels):
    assert rl.text_labels(text) == labels


@pytest.mark.parametrize("text", ["PAR1", "MAJOR", "NMR", "SRB assay", "BR1A"])
def test_joining_stays_safe(text):
    assert not rl.text_labels(text) & {"R1", "R2", "R"}


def test_index_error():
    assert rl.index_error({"0": ["R1", "X"], "4": ["R′"]}, pages=5) is None
    for bad in ([], {"x": ["R1"]}, {"5": ["R1"]}, {"-1": ["R1"]}, {"0": "R1"}, {"0": ["OAc"]},
                {"0": ["R1", "R1"]}, {"0": [1]}, {"0": ["R1"] * 300}):  # fmt: skip
        assert rl.index_error(bad, pages=5) is not None, bad
