"""A scaffold drawing's own series (owner 2026-11-26, "Fix the reader").

The R-group reader reads the whole page (image and text), so several scaffolds on one page with
the same labels got the same rows: JNP PMC13200251, page 4, four drawings all got 20a-f; on page
5 the 22 and 24 drawings got the 21 drawing's 21c and 21e. A scheme prints the series under each
drawing, as a range ("20a-f", "3a–c") or one label per compound ("21a (R = OH)"). Docling reads
that text with its box; the labels under a drawing say which compounds it stands for, and the
reader's rows of other series are dropped. No label under a drawing: its rows stay as read.

Measured on that paper (live, 2026-11-26): every drawing the reader gave another series' rows has
its own label within BELOW_PX under it. Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from marcus.core.compound_ids import text_boxes

BELOW_PX = 160  # how far below the drawing its series label may start (page pixels)
X_PAD_SHARE = 0.15  # a label's centre x may lie this share of the drawing's width outside it
INSIDE_SHARE = 0.5  # or start in the drawing's lower half: the crop often holds its label

_RANGE = re.compile(r"^\(?\s*(\d{1,3})([a-z])\s*[-–—]\s*(?:\1)?([a-z])\s*\)?$")
_ITEM = re.compile(r"^(\d{1,3}[a-z])\s*\(\s*[A-Z]")  # "21a (R = OH)", "22b (R1 = R² = H)"

Series = tuple[frozenset[str], tuple[int, int, int, int]]  # (compounds, page pixels)


def series_of(text: str) -> set[str] | None:
    """The compounds a series label names ("20a-f" -> 20a..20f; "21a (R = OH)" -> 21a), or
    None for any other text."""
    t = text.strip()
    if m := _RANGE.match(t):
        number, first, last = m.groups()
        if first > last:
            return None
        return {f"{number}{chr(c)}" for c in range(ord(first), ord(last) + 1)}
    if m := _ITEM.match(t):
        return {m.group(1)}
    return None


def series_boxes(doc: dict) -> dict[int, list[Series]]:
    """Per page (0-based, as Segment.page), the series labels of a Docling document with their
    boxes in page pixels (marcus.core.compound_ids.text_boxes)."""
    return text_boxes(doc, lambda t: frozenset(names) if (names := series_of(t)) else None)


def drawing_compounds(bbox: Sequence[int], boxes: list[Series]) -> set[str]:
    """The compounds the series labels under a drawing (`bbox`, page pixels) name: labels whose
    centre x is over the drawing (+- X_PAD_SHARE of its width) and whose top is in its lower
    half (the segmenter's crop often holds the label: JNP page 4) or at most BELOW_PX below it. Empty when there is none."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    found: set[str] = set()
    for names, (bx0, by0, bx1, _by1) in boxes:
        cx = (bx0 + bx1) / 2
        if (
            x0 - X_PAD_SHARE * w <= cx <= x1 + X_PAD_SHARE * w
            and y1 - INSIDE_SHARE * h <= by0 <= y1 + BELOW_PX
        ):
            found |= names
    return found


def keep_series(rows: list[dict], compounds: set[str]) -> list[dict]:
    """The rows of the drawing's own series; all rows when no series label was found."""
    if not compounds:
        return rows
    return [r for r in rows if r.get("compound") in compounds]
