"""A scaffold drawing's own series (owner 2026-11-26, "Fix the reader"): the R-group reader reads
the whole page, so several scaffolds on one page got the same rows (JNP PMC13200251: four
drawings on page 4 all got 20a-f; the 22 and 24 drawings on page 5 got 21c/21e). The series
label printed with the drawing ("20a-f", "21a (R = OH)") says which rows are its own.

Second round (2026-11-26, BJOC 22/57 page 3): the label can be a legend list printed to the right
of the drawing ("17: R = CH3", one line per compound), and each label belongs to the nearest
drawing of the page only."""

import json
from pathlib import Path

import pytest

from marcus.core.rgroup_series import drawing_compounds, keep_series, series_boxes, series_of

H = 792.0  # page height in PDF points
PAPERS = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "rgroup_series" / "papers.json").read_text()
)


def text(t: str, left: float, top: float, r: float, bottom: float, page: int = 4) -> dict:
    """A Docling text item, its box given top-down in points (stored bottom-left, as Docling)."""
    return {
        "text": t,
        "prov": [
            {
                "page_no": page,
                "bbox": {
                    "l": left,
                    "t": H - top,
                    "r": r,
                    "b": H - bottom,
                    "coord_origin": "BOTTOMLEFT",
                },
            }
        ],
    }


def doc(*items) -> dict:
    return {"pages": {"4": {"size": {"width": 612.0, "height": H}}}, "texts": list(items)}


def test_series_labels_and_others():
    assert series_of("20a-f") == {"20a", "20b", "20c", "20d", "20e", "20f"}
    assert series_of("20a–20d") == {"20a", "20b", "20c", "20d"}
    assert series_of("(3a-c)") == {"3a", "3b", "3c"}
    assert series_of("21a (R = OH)") == {"21a"}
    assert series_of("22b (R1 = R² = H)") == {"22b"}
    for other in [
        "R1",
        "OCH3",
        "Pd(dba)2 (4.0 mol-%)",
        "20 (yield, %)",
        "12",
        "HCl (aq, 4M)",
        "20f-a",
    ]:
        assert series_of(other) is None, other


def test_the_label_under_a_drawing_names_its_compounds():
    # two drawings side by side (pixels = points * 300/72); labels under each
    d = doc(
        text("3a-f", 270, 120, 300, 130),
        text("20a-f", 380, 160, 410, 170),
        text("R1", 280, 80, 290, 88),  # inside the first drawing: no label
    )
    boxes = series_boxes(d)[3]
    first = (1111, 312, 1333, 486)  # about 267-320 pt wide, 75-117 pt tall
    second = (1338, 367, 1710, 653)  # about 321-410 pt wide, 88-157 pt tall
    assert drawing_compounds(first, boxes) == {f"3{c}" for c in "abcdef"}
    assert drawing_compounds(second, boxes) == {f"20{c}" for c in "abcdef"}
    assert drawing_compounds((100, 100, 200, 200), boxes) == set()


def test_a_label_inside_the_drawings_box_counts():
    """The segmenter's crop often holds the label printed under the structure (JNP page 4:
    "3a-f" sits in the bottom quarter of its drawing's box); a label in the upper half does not
    count (it is another drawing's, above)."""
    boxes = series_boxes(doc(text("3a-f", 275, 107, 290, 116), text("9a-b", 275, 78, 290, 84)))[3]
    assert drawing_compounds((1111, 312, 1333, 486), boxes) == {f"3{c}" for c in "abcdef"}


def test_rows_of_another_series_are_dropped_none_found_keeps_all():
    rows = [{"compound": c, "groups": {"R1": "H"}} for c in ["20a", "20b", "21c"]]
    assert keep_series(rows, {"20a", "20b", "20c"}) == rows[:2]
    assert keep_series(rows, {"3a", "3b"}) == []
    assert keep_series(rows, set()) == rows  # no label found: as before


def test_colon_items_and_others():
    """A legend line "17: R = CH3" (BJOC 22/57): the ID, a colon, then a label and "="."""
    assert series_of("17: R = CH3") == {"17"}
    assert series_of("4: R = H") == {"4"}
    assert series_of("12: R1 = R² = H") == {"12"}
    assert series_of("13: R1 = F, R² = H") == {"13"}
    assert series_of("23: R  = CH3") == {"23"}
    assert series_of("3a: R¹ = OMe") == {"3a"}
    assert series_of("5b : X = Cl") == {"5b"}
    assert series_of("7: Ar = Ph") == {"7"}
    # several compounds in one text box: all of them
    assert series_of("3a: R1 = OMe, R2 = H; 3b: R1 = H, R2 = OMe") == {"3a", "3b"}
    assert series_of("1: R = H, 2: R = Me, 3: R = OH") == {"1", "2", "3"}
    assert series_of("4: R = H (dr 20:1, X = 2)") == {"4"}
    for other in [
        "Pd(dba)2 (4.0 mol-%)",
        "755",
        "2: 1 mixture",
        "12:30",
        "1:1 v/v",
        "3:1",
        "dr 20:1",
        "20: 1 dr",
        "17:",
        "17: 85%",
        "2: Structures of compounds",
        "Figure 2: R = H",
        "2026: R = H",
        "10: yield = 85%",
        "t-BuOH/H2O (1:1 v/v), rt, 36 h",
    ]:
        assert series_of(other) is None, other


def test_a_text_without_a_box_is_no_label():
    """A text item without a box (tests, the fake stack) cannot be placed."""
    d = doc({"text": "3a: R1 = OMe, R2 = H", "prov": [{"page_no": 4}]})
    assert series_boxes(d) == {}


def px(left: float, top: float, r: float, bottom: float) -> tuple[int, ...]:
    return tuple(round(v * 300 / 72) for v in (left, top, r, bottom))


def test_a_legend_to_the_right_of_a_drawing_names_its_compounds():
    """BJOC 22/57 page 3: the drawing, then "17: R = CH3" ... "22: R = CN" in a column to its
    right, one line each, beside it."""
    lines = ["17: R = CH3", "18: R = OCH3", "19: R = Cl", "20: R = Br"]
    d = doc(*[text(t, 465, 250 + 10 * i, 510, 259 + 10 * i) for i, t in enumerate(lines)])
    boxes = series_boxes(d)[3]
    drawing = px(310, 232, 458, 312)
    assert drawing_compounds(drawing, boxes) == {"17", "18", "19", "20"}
    assert drawing_compounds(px(310, 400, 458, 480), boxes) == set()  # not beside the legend
    assert drawing_compounds(px(100, 232, 250, 312), boxes) == set()  # too far to its left


def test_a_long_legend_under_a_drawing_is_one_list():
    """BJOC 22/57 page 3, compounds 4-11: eight lines; the list starts in the drawing's box and
    its last lines are far below it. The lines of one list go together."""
    lines = [f"{n}: R = H" for n in range(4, 12)]
    d = doc(*[text(t, 147, 155 + 10 * i, 190, 164 + 10 * i) for i, t in enumerate(lines)])
    boxes = series_boxes(d)[3]
    assert drawing_compounds(px(66, 111, 215, 188), boxes) == {str(n) for n in range(4, 12)}


def test_a_label_belongs_to_the_nearest_drawing_of_the_page():
    """JNP page 4: "3a-f" sits in its own drawing's box and beside the drawing to its left; with
    the page's drawings, only its own drawing gets it. A drawing without rows counts too."""
    boxes = series_boxes(doc(text("3a-f", 275, 107, 290, 116)))[3]
    own, left = (1111, 312, 1333, 486), (828, 368, 1090, 600)
    assert drawing_compounds(left, boxes) == {f"3{c}" for c in "abcdef"}  # alone on the page
    assert drawing_compounds(left, boxes, [own, left]) == set()
    assert drawing_compounds(own, boxes, [own, left]) == {f"3{c}" for c in "abcdef"}


CASES = [
    (name, seg["page"], seg["idx"])
    for name, paper in PAPERS.items()
    for seg in paper["segments"]
    if "rows" in seg
]


@pytest.mark.parametrize(("name", "page", "idx"), CASES, ids=str)
def test_three_papers_each_drawing_keeps_its_own_rows(name, page, idx):
    """Real data (live site, 2026-11-26; tests/fixtures/rgroup_series/papers.json): the Docling
    text of the pages, every drawing's box, the rows the reader gave (`rows`) and the compounds
    the drawing stands for, written down by looking at the page (`truth`). The kept rows are the
    true ones of those the reader gave; a drawing marked `open` has no series label and keeps
    its rows as read."""
    paper = PAPERS[name]
    segments = [s for s in paper["segments"] if s["page"] == page]
    seg = next(s for s in segments if s["idx"] == idx)
    boxes = series_boxes(paper["doc"]).get(page, [])
    own = drawing_compounds(seg["bbox"], boxes, [s["bbox"] for s in segments])
    kept = [r["compound"] for r in keep_series([{"compound": c} for c in seg["rows"]], own)]
    if "open" in seg:
        assert kept == seg["rows"]
    else:
        assert kept == [c for c in seg["rows"] if c in seg["truth"]]
