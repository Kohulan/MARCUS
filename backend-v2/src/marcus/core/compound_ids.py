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
docling_boxes.py, id_name_link.py); the two page rules came after them (measured with the same
gold, 2026-11-23). Standard library only.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import TypeVar

SCALE = 300 / 72  # PDF points to pixels of the 300 DPI page render (pipeline.RENDER_DPI)
BELOW_PX = 100  # how far below the crop an ID may sit
INSIDE_SHARE = 0.15  # the crop's bottom share an ID may sit in (second pass)
X_PAD_SHARE = 0.15  # an ID's centre x may lie this share of the crop width outside it

_NUMBER = re.compile(r"^\(?\s*(\d{1,3}[a-z]?['′]?)\s*\)?$")
_NAMED = re.compile(r"\((\d{1,3}[a-z]?)\)\s*$")  # "Taveuniamide L (1)"
_LETTER = re.compile(r"^([a-z])$")

# "<name> (<id>)": up to three words and a suffix ("salsubstolin A") before " (1)". Read in
# linear time (security scan 2026-11-23 F1: one pattern over the whole text backtracked over
# every long word, O(n^2), from text an uploaded PDF controls): find each " (<id>)", then walk
# back over at most four tokens before it (_name_start).
_ID_MENTION = re.compile(r"\s\((\d{1,3}[a-z]?)\)")
_WORD_RUN = re.compile(r"[\w\-′']*")  # a word's characters; on the reversed text, a run going left
_ASCII_LETTER = re.compile(r"[A-Za-z]")
_SUFFIX = re.compile(r"[A-Z]{1,2}\d?")
_SPACE = re.compile(r"\s")
MAX_ID_MENTIONS = 20_000  # " (<id>)" mentions read per paper; a paper has a few hundred
_STOP = {
    "compound", "compounds", "of", "and", "the", "for", "to", "in", "with", "by", "as", "that",
    "from", "was", "were", "is", "Figure", "Table",
}  # fmt: skip

T = TypeVar("T")
Box = tuple[str, tuple[int, int, int, int]]  # (compound ID, (x0, y0, x1, y1) page pixels)


def id_of(text: str) -> str | None:
    """The compound ID a text box holds, or None."""
    t = text.strip()
    m = _NUMBER.match(t) or _NAMED.search(t) or _LETTER.match(t)
    value = m.group(1) if m else None
    return None if value in ("0", "00") else value


def text_boxes(
    doc: dict, classify: Callable[[str], T | None]
) -> dict[int, list[tuple[T, tuple[int, int, int, int]]]]:
    """Per page (0-based, as Segment.page), the text boxes of a Docling document that `classify`
    gives a value for, with that value, in page pixels. The one place Docling's boxes (points,
    origin bottom left) become page pixels: compound IDs here, series labels in
    marcus.core.rgroup_series."""
    heights = {int(k): v["size"]["height"] for k, v in (doc.get("pages") or {}).items()}
    out: dict[int, list[tuple[T, tuple[int, int, int, int]]]] = defaultdict(list)
    for item in doc.get("texts") or []:
        if not isinstance(item, dict):
            continue
        value = classify(str(item.get("text") or ""))
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


def id_boxes(doc: dict) -> dict[int, list[Box]]:
    """Per page (0-based, as Segment.page), the ID-like text boxes of a Docling document in page
    pixels."""
    return text_boxes(doc, id_of)


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
    for how, inside in ((1, 0.0), (2, INSIDE_SHARE)):
        if (value := _nearest(bbox, boxes, inside)) is not None:
            return value, how
    return None, 0


def read_ids(bboxes: Sequence[Sequence[int]], boxes: list[Box]) -> list[str | None]:
    """Rule B for all crops of one page (page pixels), in their order, with two page rules
    against atom numbers (tester paper 2026-11-23: OCR missed the label, an atom number took
    its place, and a structure linked to the wrong compound):

    - a crop does not take an ID box whose centre lies in a drawing below it (that drawing's
      atom number): a crop that starts at or below the top of this crop's bottom band (crops
      may overlap a little);
    - an ID found in a crop's bottom band (pass 2) is dropped when another crop of the page
      has the same ID below it (pass 1): the printed label is that crop's.

    The same ID below two crops (two pictures of one compound) stays on both. One crop alone:
    rule B."""
    centres = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for _, b in boxes]
    found = []
    for i, (x0, y0, x1, y1) in enumerate(bboxes):
        pad, band_top = X_PAD_SHARE * (x1 - x0), y1 - INSIDE_SHARE * (y1 - y0)
        # the boxes rule B could take (both passes), then those not in a drawing below
        near = [
            (box, cx, cy)
            for box, (cx, cy) in zip(boxes, centres, strict=True)
            if x0 - pad <= cx <= x1 + pad and cy >= band_top and box[1][1] <= y1 + BELOW_PX
        ]
        below = [o for j, o in enumerate(bboxes) if j != i and o[1] >= band_top] if near else []
        own = [
            box
            for box, cx, cy in near
            if not any(o[0] <= cx <= o[2] and o[1] <= cy <= o[3] for o in below)
        ]
        found.append(_read((x0, y0, x1, y1), own))
    first = {value for value, how in found if how == 1}
    return [None if how == 2 and value in first else value for value, how in found]


def _name_start(text: str, rev: str, lo: int, p: int) -> int | None:
    """Where the name before the ID mention at `p` (text[p] is its space) starts, or None: the
    leftmost s >= lo with text[s:p] = (W\\s){0,2}W(\\sS)?, W = [A-Za-z][\\w\\-′']*, S = _SUFFIX.
    A word runs up to a space, so the leftmost start is the one with the most tokens (at most
    4, the 4th a suffix), at the first ASCII letter of its first token. `rev` is text reversed:
    a token is matched on it from its end, in time linear in its length."""
    n = len(text)
    tokens: list[tuple[int, int]] = []  # (start, end) in text, nearest the mention first
    end = p
    while len(tokens) < 4 and end > lo:
        start = n - _WORD_RUN.match(rev, n - end, n - lo).end()
        if start == end:
            break
        tokens.append((start, end))
        if start - 1 <= lo or not _SPACE.match(text, start - 1):
            break
        end = start - 1  # one space, then the token before
    for k in range(len(tokens), 0, -1):
        if k == 4 and not _SUFFIX.fullmatch(text, *tokens[0]):
            continue
        if not all(_ASCII_LETTER.match(text, s) for s, _ in tokens[: k - 1]):
            continue  # a word after the first starts with a letter
        if first := _ASCII_LETTER.search(text, *tokens[k - 1]):
            return first.start()
    return None


def names(doc: dict) -> dict[str, str]:
    """Compound ID -> the name the text writes most often before "(<id>)"."""
    text = " ".join(str(t.get("text", "")) for t in doc.get("texts") or [] if isinstance(t, dict))
    rev = text[::-1]
    found: dict[str, Counter] = defaultdict(Counter)
    lo = 0  # a name never reaches back over the mention before it
    for i, m in enumerate(_ID_MENTION.finditer(text)):
        if i == MAX_ID_MENTIONS:
            break
        p, lo_here, lo = m.start(), lo, m.end()
        start = _name_start(text, rev, lo_here, p)
        if start is None:
            continue
        words = [w for w in text[start:p].split() if w not in _STOP]
        if not words:
            continue
        name = " ".join(words[-2:]) if re.fullmatch(r"[A-Z]{1,2}\d?", words[-1]) else words[-1]
        if len(name) < 4 or name.lower() in _STOP:
            continue
        found[m.group(1)][name] += 1
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
