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

Name: the paper text's "<name> (<id>)", the name most often written before that ID
("salsubstolin A (1)"). A port of the measurement scripts (phase-b/scripts/compound_id_full.py,
docling_boxes.py, id_name_link.py), unchanged. Standard library only.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

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


def read_id(bbox: list[int] | tuple[int, ...], boxes: list[Box]) -> str | None:
    """Rule B: the compound ID of the crop `bbox` (page pixels) from its page's ID boxes."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0

    def nearest(inside: float) -> str | None:
        found = []
        for value, (bx0, by0, bx1, by1) in boxes:
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if not (x0 - X_PAD_SHARE * w <= cx <= x1 + X_PAD_SHARE * w):
                continue
            if cy < y1 - inside * h or by0 > y1 + BELOW_PX:
                continue
            found.append((max(0, by0 - y1) + abs(cx - (x0 + x1) / 2) * 0.2, value))
        return min(found)[1] if found else None

    return nearest(0.0) or nearest(INSIDE_SHARE)


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
