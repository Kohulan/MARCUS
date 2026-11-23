"""The compound ID by each drawing and the compound's name (marcus.core.compound_ids).

tests/fixtures/compound_ids/pestalotiopsis-benzophenones.json is the Docling document MARCUS
stores for an open-access CC BY 4.0 paper (Marine Drugs, 10.3390/md15030069), cut down to the
text items that hold an ID or "name (id)": its page 2 figure lists compounds 1-8b. The crop
boxes are DECIMER Segmentation's at 300 DPI, as MARCUS made them (MEASURE.md).
"""

import json
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from marcus.core import compound_ids

FIXTURE = Path(__file__).parent.parent / "fixtures" / "compound_ids"
DOC = json.loads((FIXTURE / "pestalotiopsis-benzophenones.json").read_text())

# page 2 (0-based 1): the compound list
CROPS = [
    ([440, 1152, 715, 1395], "1"),
    ([723, 1196, 1080, 1395], "2"),
    ([1101, 1192, 1414, 1394], "3"),
    ([1471, 1168, 1742, 1419], "4"),
    ([1728, 1199, 2054, 1404], "5"),
    ([426, 1502, 792, 1788], "6"),
    ([828, 1501, 1194, 1787], "7"),
    ([1228, 1504, 1593, 1802], "8a"),
    ([1632, 1503, 1996, 1801], "8b"),
]


@pytest.mark.parametrize(("text", "expected"), [
    ("12", "12"), ("8a", "8a"), ("6′", "6′"), ("6'", "6'"), ("(3)", "3"), (" ( 3 ) ", "3"),
    ("Taveuniamide L (1)", "1"), ("a", "a"), ("0", None), ("00", None), ("OH", None),
    ("1234", None), ("H3CO", None), ("ab", None), ("A", None),
])  # fmt: skip
def test_id_of(text, expected):
    assert compound_ids.id_of(text) == expected


def test_the_main_figure_ids_as_printed():
    boxes, _ = compound_ids.figure_labels(DOC)
    assert compound_ids.read_ids([bbox for bbox, _ in CROPS], boxes[1]) == [c for _, c in CROPS]


def test_names_from_the_text():
    _, names = compound_ids.figure_labels(DOC)
    assert names["1"] == "pestaloisocoumarin A"
    assert names["4"] == "isopolisin B"
    assert "8a" not in names  # the text never writes "<name> (8a)"


def box(text, left, top, right, bottom, page=1, origin="BOTTOMLEFT"):
    coords = {"l": left, "t": top, "r": right, "b": bottom, "coord_origin": origin}
    return {"text": text, "prov": [{"page_no": page, "bbox": coords}]}


# One A4 page (842 pt high); a crop at x 300-600 px, y 300-600 px of the 300 DPI render.
PAGE = {"1": {"size": {"width": 595.0, "height": 842.0}, "page_no": 1}}
CROP = [300, 300, 600, 600]
PT = 72 / 300  # one pixel in points


def ids(*texts):
    boxes, _ = compound_ids.figure_labels({"pages": PAGE, "texts": list(texts)})
    return compound_ids.read_ids([CROP], boxes.get(0, []))[0]


def below(text, gap_px, x_px=450, page=1):
    """A box `gap_px` below the crop's bottom edge, 20 px high, centred at `x_px`."""
    top = 600 + gap_px
    return box(
        text, (x_px - 10) * PT, 842 - top * PT, (x_px + 10) * PT, 842 - (top + 20) * PT, page
    )


def test_rule_b():
    assert ids(below("3", 50)) == "3"
    assert ids(below("3", 99)) == "3"
    assert ids(below("3", 120)) is None  # too far below
    assert ids(below("3", 50, x_px=620)) == "3"  # within the crop width + 15 %
    assert ids(below("3", 50, x_px=700)) is None  # beside the next crop
    assert ids(below("4", 80), below("3", 10)) == "3"  # the nearest
    assert ids(below("3", -30)) == "3"  # in the crop's bottom 15 %, nothing below
    assert ids(below("3", -100)) is None  # higher in the crop: an atom number, not an ID
    assert ids(below("7", -30), below("3", 60)) == "3"  # below the crop wins
    assert ids(below("0", 20)) is None  # a ring O read as zero
    assert ids(below("3", 50, page=2)) is None  # a page the document does not describe


def test_top_left_boxes_and_odd_documents():
    top = box("5", 440 * PT, 640 * PT, 460 * PT, 660 * PT, origin="TOPLEFT")
    assert ids(top) == "5"
    assert compound_ids.figure_labels({"texts": ["hi"]}) == ({}, {})  # a string item is skipped
    assert compound_ids.figure_labels({}) == ({}, {})


def test_labels_from_a_file(tmp_path):
    path = tmp_path / "text.json"
    assert compound_ids.labels_from_file(path) == ({}, {})  # no text yet
    path.write_text("not json")
    assert compound_ids.labels_from_file(path) == ({}, {})
    path.write_text(json.dumps(DOC))
    boxes, names = compound_ids.labels_from_file(path)
    assert (
        compound_ids.read_ids([CROPS[7][0]], boxes[1]) == ["8a"]
        and names["2"] == "pestaloisocoumarin B"
    )


# Page-level rules (read_ids): an atom number must not become a crop's ID. Layouts as the
# tester paper's (np6c00666 pages 3 and 4, where OCR missed the label "1"), with made-up boxes:
# (value, (x0, y0, x1, y1)) in page pixels, as compound_ids.id_boxes gives them.


def test_a_pass_two_id_loses_to_the_same_id_below_another_crop():
    left, right = [556, 245, 848, 604], [1684, 268, 1977, 586]
    boxes = [
        ("4", (756, 585, 767, 600)),  # atom number in the left crop's bottom band
        ("4", (1815, 643, 1843, 675)),  # the right crop's printed label, below it
    ]
    assert compound_ids.read_ids([left], boxes) == ["4"]  # one crop alone: rule B
    assert compound_ids.read_ids([left, right], boxes) == [None, "4"]


def test_an_atom_number_of_the_drawing_below_is_not_an_id():
    upper, lower = [462, 245, 764, 591], [447, 626, 833, 932]
    boxes = [
        ("14", (540, 656, 572, 679)),  # atom 14 at the top of the lower drawing
        ("5", (617, 929, 640, 960)),  # the lower crop's label
    ]
    assert compound_ids.read_ids([upper], boxes) == ["14"]
    assert compound_ids.read_ids([upper, lower], boxes) == [None, "5"]
    # crops a little taller than drawn (overlapping by less than 15 % of the upper's height)
    grown_upper, grown_lower = [462, 245, 764, 611], [447, 606, 833, 952]
    assert compound_ids.read_ids([grown_upper, grown_lower], boxes) == [None, "5"]


def test_a_label_below_a_crop_inside_its_overlapping_neighbour_stays():
    # side by side, the neighbour reaching down past the label: not a drawing below
    left, right = [300, 300, 600, 600], [560, 280, 900, 700]
    boxes = [("3", (440, 640, 460, 660))]
    assert compound_ids.read_ids([left, right], boxes) == ["3", None]


def test_the_same_id_printed_twice_on_a_page_stays_on_both():
    # two pictures of compound 3 (NMR and X-ray), each labelled below
    a, b = [300, 300, 600, 600], [300, 900, 600, 1200]
    boxes = [("3", (440, 640, 460, 660)), ("3", (440, 1240, 460, 1260))]
    assert compound_ids.read_ids([a, b], boxes) == ["3", "3"]


def test_a_page_without_crops():
    boxes, _ = compound_ids.figure_labels(DOC)
    assert compound_ids.read_ids([], boxes[1]) == []


# --- names in linear time (security scan 2026-11-23 F1) -------------------------------------
# The one pattern names() used before: over text an uploaded PDF controls it backtracked over
# every long word, O(n^2) (a 16,000-letter word: 10.8 s in the API's chem process).
_ONE_PATTERN = re.compile(
    r"((?:[A-Za-z][\w\-′']*\s){0,2}[A-Za-z][\w\-′']*(?:\s[A-Z]{1,2}\d?)?)\s\((\d{1,3}[a-z]?)\)"
)


def _one_pattern_names(doc: dict) -> dict[str, str]:
    text = " ".join(str(t.get("text", "")) for t in doc.get("texts") or [])
    found: dict[str, Counter] = defaultdict(Counter)
    for m in _ONE_PATTERN.finditer(text):
        words = [w for w in m.group(1).split() if w not in compound_ids._STOP]
        if not words:
            continue
        name = " ".join(words[-2:]) if re.fullmatch(r"[A-Z]{1,2}\d?", words[-1]) else words[-1]
        if len(name) < 4 or name.lower() in compound_ids._STOP:
            continue
        found[m.group(2)][name] += 1
    return {cid: counts.most_common(1)[0][0] for cid, counts in found.items()}


_PIECES = [
    "a", "Z", "AB", "X1", "q", "1", "8a", "-", "′", "'", "_", "é", "α", " ", " ", "  ", "\t",
    " ", "(", ")", "(1)", " (1)", " (12a)", " (3)", "(0)", ",", ".", "of", "the",
    "compound", "Figure", "salsubstolin", " A", "N2", "8-O-methyl",
]  # fmt: skip


def test_names_are_those_the_one_pattern_found():
    rng = random.Random(7)
    assert compound_ids.names(DOC) == _one_pattern_names(DOC)
    for _ in range(5000):
        texts = [
            "".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 30)))
            for _ in range(rng.randint(0, 3))
        ]
        doc = {"texts": [{"text": t} for t in texts]}
        assert compound_ids.names(doc) == _one_pattern_names(doc), texts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the new salsubstolin A (1)", {"1": "salsubstolin A"}),
        ("8-O-methylsterigmatocystin (3)", {"3": "O-methylsterigmatocystin"}),
        ("isopolisin B (4) and isopolisin B (4)", {"4": "isopolisin B"}),
        ("compound (2)", {}),
        ("alpha  (2)", {}),  # two spaces: no name
        ("(5) (2)", {}),
    ],
)
def test_names_of_short_texts(text, expected):
    assert compound_ids.names({"texts": [{"text": text}]}) == expected


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000,  # one word with no ID after it
        "a" * 200_000 + " x",
        "1a" * 100_000,  # a letter after every digit: a start at each
        "a" * 200_000 + " (1)",
        "R′" * 100_000,
    ],
)
def test_names_take_linear_time_on_long_words(text):
    started = time.perf_counter()
    compound_ids.names({"texts": [{"text": text}]})
    assert time.perf_counter() - started < 1.0


def test_names_read_at_most_max_id_mentions():
    text = "salsubstolin A (1) " * compound_ids.MAX_ID_MENTIONS + "isopolisin B (2)"
    assert compound_ids.names({"texts": [{"text": text}]}) == {"1": "salsubstolin A"}
