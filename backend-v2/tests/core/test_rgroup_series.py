"""A scaffold drawing's own series (owner 2026-11-26, "Fix the reader"): the R-group reader reads
the whole page, so several scaffolds on one page got the same rows (JNP PMC13200251: four
drawings on page 4 all got 20a-f; the 22 and 24 drawings on page 5 got 21c/21e). The series
label printed with the drawing ("20a-f", "21a (R = OH)") says which rows are its own."""

from marcus.core.rgroup_series import drawing_compounds, keep_series, series_boxes, series_of

H = 792.0  # page height in PDF points


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
