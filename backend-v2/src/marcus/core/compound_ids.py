"""The compound ID printed by each drawing, and the compound's name (phase B item 4, owner
decision 2026-11-22).

ID: Docling reads the text in the paper's figures (OCR) into its document: `texts[]` items with a
`prov` box in PDF points (origin bottom left). Scaled by 300/72 they are in the pixels of the
300 DPI page the segments are cut from. Rule B of MARCUS-training review-feedback/phase-b/
MEASURE.md (119 labelled crops: 101 right, 2 wrong, 16 missed):

- the nearest ID-like box at most 100 px below the crop whose centre x is within the crop's
  width +- 15 %;
- else an ID-like box in the bottom 15 % of the crop (same x rule);
- ID-like: `12`, `8a`, `6′`, `(3)`, `name (3)` (the number), a single letter `a`; never `0`
  (OCR reads ring O atoms as zeros).
- per page (read_ids): not an ID box inside a drawing below the crop, and a bottom-band ID
  gives way to the same ID below another crop (atom numbers; 101 right, 0 wrong, 18 missed of
  the 119).

Name: the paper text's "<name> (<id>)", the name most often written before that ID
("salsubstolin A (1)"). A port of the measurement scripts (phase-b/scripts/compound_id_full.py,
docling_boxes.py, id_name_link.py), unchanged. Standard library only.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence

SCALE = 300 / 72  # PDF points to pixels of the 300 DPI page render (pipeline.RENDER_DPI)
BELOW_PX = 100  # how far below the crop an ID may sit
INSIDE_SHARE = 0.15  # the crop's bottom share an ID may sit in (second pass)
X_PAD_SHARE = 0.15  # an ID's centre x may lie this share of the crop width outside it

_NUMBER = re.compile(r"^\(?\s*(\d{1,3}[a-z]?['′]?)\s*\)?$")
_NAMED = re.compile(r"\((\d{1,3}[a-z]?)\)\s*$")  # "Taveuniamide L (1)"
_LETTER = re.compile(r"^([a-z])$")

_NAME_BEFORE_ID = re.compile(
    r"((?:[A-Za-z][\w\-′']*\s){0,2}[A-Za-z][\w\-′']*(?:\s[A-Z]{1,2}\d?)?)\s\((\d{1,3}[a-z]?)\)"
)
_STOP = {
    "compound", "compounds", "of", "and", "the", "for", "to", "in", "with", "by", "as", "that",
    "from", "was", "were", "is", "Figure", "Table",
}  # fmt: skip

Box = tuple[str, tuple[int, int, int, int]]  # (compound ID, (x0, y0, x1, y1) page pixels)


def id_of(text: str) -> str | None:
    """The compound ID a text box holds, or None."""
    t = text.strip()
    m = _NUMBER.match(t) or _NAMED.search(t) or _LETTER.match(t)
    value = m.group(1) if m else None
    return None if value in ("0", "00") else value


def id_boxes(doc: dict) -> dict[int, list[Box]]:
    """Per page (0-based, as Segment.page), the ID-like text boxes of a Docling document in page
    pixels."""
    heights = {int(k): v["size"]["height"] for k, v in (doc.get("pages") or {}).items()}
    out: dict[int, list[Box]] = defaultdict(list)
    for item in doc.get("texts") or []:
        if not isinstance(item, dict):
            continue
        value = id_of(str(item.get("text") or ""))
        if value is None:
            continue
        for prov in item.get("prov") or []:
            b, page = prov["bbox"], prov["page_no"]
            if b.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
                if page not in heights:
                    continue  # a page the document does not describe
                h = heights[page]
                x0, y0, x1, y1 = b["l"], h - b["t"], b["r"], h - b["b"]
            else:
                x0, y0, x1, y1 = b["l"], b["t"], b["r"], b["b"]
            box = tuple(round(v * SCALE) for v in (x0, y0, x1, y1))
            out[page - 1].append((value, box))
    return dict(out)


def _nearest(bbox: Sequence[int], boxes: list[Box], inside: float) -> str | None:
    """The nearest ID box at most BELOW_PX below the crop `bbox` (`inside` 0), or reaching up
    into its bottom `inside` share; centre x within the crop's width +- X_PAD_SHARE."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    found = []
    for value, (bx0, by0, bx1, by1) in boxes:
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if not (x0 - X_PAD_SHARE * w <= cx <= x1 + X_PAD_SHARE * w):
            continue
        if cy < y1 - inside * h or by0 > y1 + BELOW_PX:
            continue
        found.append((max(0, by0 - y1) + abs(cx - (x0 + x1) / 2) * 0.2, value))
    return min(found)[1] if found else None


def _read(bbox: Sequence[int], boxes: list[Box]) -> tuple[str | None, int]:
    """Rule B of one crop: (ID, the pass that found it: 1 below the crop, 2 in its bottom
    band, 0 none)."""
    first = _nearest(bbox, boxes, 0.0)
    if first is not None:
        return first, 1
    second = _nearest(bbox, boxes, INSIDE_SHARE)
    return (second, 2) if second is not None else (None, 0)


def read_id(bbox: Sequence[int], boxes: list[Box]) -> str | None:
    """Rule B: the compound ID of the crop `bbox` (page pixels) from its page's ID boxes, the
    crop taken alone (read_ids: with the page's other crops)."""
    return _read(bbox, boxes)[0]


def _in_drawing_below(box: tuple[int, int, int, int], bbox: Sequence[int], other) -> bool:
    """Whether the ID box's centre lies in the crop `other`, a drawing below the crop `bbox`:
    `other` starts at or below the top of `bbox`'s bottom band (crops may overlap a little)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    ox0, oy0, ox1, oy1 = other
    band_top = bbox[3] - INSIDE_SHARE * (bbox[3] - bbox[1])
    return oy0 >= band_top and ox0 <= cx <= ox1 and oy0 <= cy <= oy1


def read_ids(bboxes: Sequence[Sequence[int]], boxes: list[Box]) -> list[str | None]:
    """Rule B for all crops of one page (page pixels), in their order, with two page rules
    against atom numbers (tester paper 2026-11-23: OCR missed the label, an atom number took
    its place, and a structure linked to the wrong compound):

    - a crop does not take an ID box that lies in a drawing below it (that drawing's atom
      number);
    - an ID found in a crop's bottom band (pass 2) is dropped when another crop of the page
      has the same ID below it (pass 1): the printed label is that crop's.

    The same ID below two crops (two pictures of one compound) stays on both."""
    found = []
    for i, bbox in enumerate(bboxes):
        own = [
            b
            for b in boxes
            if not any(j != i and _in_drawing_below(b[1], bbox, o) for j, o in enumerate(bboxes))
        ]
        found.append(_read(bbox, own))
    below = {value for value, how in found if how == 1}
    return [None if how == 2 and value in below else value for value, how in found]


def names(doc: dict) -> dict[str, str]:
    """Compound ID -> the name the text writes most often before "(<id>)"."""
    text = " ".join(str(t.get("text", "")) for t in doc.get("texts") or [] if isinstance(t, dict))
    found: dict[str, Counter] = defaultdict(Counter)
    for m in _NAME_BEFORE_ID.finditer(text):
        words = [w for w in m.group(1).split() if w not in _STOP]
        if not words:
            continue
        name = " ".join(words[-2:]) if re.fullmatch(r"[A-Z]{1,2}\d?", words[-1]) else words[-1]
        if len(name) < 4 or name.lower() in _STOP:
            continue
        found[m.group(2)][name] += 1
    return {cid: counts.most_common(1)[0][0] for cid, counts in found.items()}


def figure_labels(doc: dict) -> tuple[dict[int, list[Box]], dict[str, str]]:
    """(id_boxes, names) of a Docling document: all a paper's cards need from its text."""
    return id_boxes(doc), names(doc)


def labels_from_file(path) -> tuple[dict[int, list[Box]], dict[str, str]]:
    """figure_labels of a paper's text file (a blocking read, under marcus.core.annotation's size
    cap); empty without a file, or for one that cannot be used. Run in marcus.api.chempool."""
    from pathlib import Path

    from marcus.core import annotation
    from marcus.core.page_text import UNUSABLE_TEXT

    try:
        doc = annotation.read_document(Path(path))
        return figure_labels(doc) if isinstance(doc, dict) else ({}, {})
    except UNUSABLE_TEXT:
        return {}, {}
