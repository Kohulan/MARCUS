"""A scaffold drawing's own series (owner 2026-11-26, "Fix the reader").

The R-group reader reads the whole page (image and text), so several scaffolds on one page with
the same labels got the same rows: JNP PMC13200251, page 4, four drawings all got 20a-f; on page
5 the 22 and 24 drawings got the 21 drawing's 21c and 21e. A scheme prints the series with each
drawing, as a range ("20a-f", "3a–c") or one label per compound ("21a (R = OH)",
"17: R = CH3"). Docling reads that text with its box; the labels of a drawing say which
compounds it stands for, and the reader's rows of other series are dropped. No label with a
drawing: its rows stay as read.

Where a label may sit: under the drawing (or in its lower half: the crop often holds it), or to
its right, beside it (BJOC 22/57 page 3: a legend "17: R = CH3" ... "22: R = CN", one line per
compound). The lines of one legend (a column of labels) go together, and a legend belongs to
the nearest drawing of the page only, so two drawings never share one.

Measured on three papers (live data 2026-11-26, tests/fixtures/rgroup_series/papers.json; truth
written down from the pages): JNP PMC13200251 stays as it was, BJOC 22/57 page 3 loses the rows
17-22 on the 4-11 and 23-28 drawings, BJOC 18/23 (tables, no series label) is unchanged.
Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from marcus.core.compound_ids import text_boxes

BELOW_PX = 160  # how far below the drawing its series label may start (page pixels)
RIGHT_PX = 160  # how far to the right of the drawing its legend may start (page pixels)
X_PAD_SHARE = 0.15  # a label's centre x may lie this share of the drawing's width outside it
INSIDE_SHARE = 0.5  # or start in the drawing's lower half: the crop often holds its label

_RANGE = re.compile(r"^\(?\s*(\d{1,3})([a-z])\s*[-–—]\s*(?:\1)?([a-z])\s*\)?$")
_ITEM = re.compile(r"^(\d{1,3}[a-z])\s*\(\s*[A-Z]")  # "21a (R = OH)", "22b (R1 = R² = H)"
# "17: R = CH3", "12: R1 = R² = H", "5b: X = Cl": the ID, a colon, a label and "="; one text
# box may hold several ("3a: R1 = OMe; 3b: R1 = H"), the first at its start
_COLON = re.compile(r"(?<![\w.:])(\d{1,3}[a-z]?)\s*:\s*[A-Z][a-z]?[\d¹²³⁴-⁹'′]{0,2}\s*=")

Box = tuple[int, int, int, int]
Series = tuple[frozenset[str], Box]  # (compounds, page pixels)


def series_of(text: str) -> set[str] | None:
    """The compounds a series label names ("20a-f" -> 20a..20f; "21a (R = OH)" -> 21a;
    "17: R = CH3" -> 17, every such item of the text), or None for any other text."""
    t = text.strip()
    if m := _RANGE.match(t):
        number, first, last = m.groups()
        if first > last:
            return None
        return {f"{number}{chr(c)}" for c in range(ord(first), ord(last) + 1)}
    if m := _ITEM.match(t):
        return {m.group(1)}
    if _COLON.match(t):
        return set(_COLON.findall(t))
    return None


def series_boxes(doc: dict) -> dict[int, list[Series]]:
    """Per page (0-based, as Segment.page), the series labels of a Docling document with their
    boxes in page pixels (marcus.core.compound_ids.text_boxes)."""
    return text_boxes(doc, lambda t: frozenset(names) if (names := series_of(t)) else None)


def _legends(boxes: list[Series]) -> list[tuple[set[str], Box, Box]]:
    """The labels of a page as legends: (compounds, first line's box, whole box). A label
    joins the legend whose last line is just above it and starts at the same x (both within one
    line height); any other label is a legend of its own."""
    out: list[list[Series]] = []
    for item in sorted(boxes, key=lambda s: (s[1][1], s[1][0])):
        x0, y0 = item[1][0], item[1][1]
        for lines in out:
            lx0, ly0, _lx1, ly1 = lines[-1][1]
            height = ly1 - ly0
            if abs(x0 - lx0) <= height and ly0 < y0 <= ly1 + height:
                lines.append(item)
                break
        else:
            out.append([item])
    legends = []
    for lines in out:
        names = set().union(*(n for n, _ in lines))
        whole = (
            min(b[0] for _, b in lines),
            lines[0][1][1],
            max(b[2] for _, b in lines),
            max(b[3] for _, b in lines),
        )
        legends.append((names, lines[0][1], whole))
    return legends


def _distance(drawing: Sequence[int], first: Box, whole: Box) -> tuple[float, float] | None:
    """How far a legend is from a drawing it may belong to, as (gap, centre x offset) in page
    pixels, or None when it sits neither under the drawing nor to its right. Under: the first
    line's centre x is over the drawing (+- X_PAD_SHARE of its width) and its top is in the
    drawing's lower half or at most BELOW_PX below it. Right: the legend starts in the
    drawing's right half or at most RIGHT_PX right of it, and its centre y is beside it."""
    x0, y0, x1, y1 = drawing
    w, h = x1 - x0, y1 - y0
    fx0, fy0, fx1, _fy1 = first
    wx0, wy0, _wx1, wy1 = whole
    offset = abs((fx0 + fx1) / 2 - (x0 + x1) / 2)
    cx = (fx0 + fx1) / 2
    if (
        x0 - X_PAD_SHARE * w <= cx <= x1 + X_PAD_SHARE * w
        and y1 - INSIDE_SHARE * h <= fy0 <= y1 + BELOW_PX
    ):
        return (max(0, fy0 - y1), offset)
    if x0 + w / 2 <= wx0 <= x1 + RIGHT_PX and y0 <= (wy0 + wy1) / 2 <= y1:
        return (max(0, wx0 - x1), offset)
    return None


def drawing_compounds(
    bbox: Sequence[int], boxes: list[Series], drawings: Sequence[Sequence[int]] | None = None
) -> set[str]:
    """The compounds the series labels of a drawing (`bbox`, page pixels) name: the legends
    under it or to its right (_distance) that are not nearer to another of the page's
    `drawings` (all drawings of the page, with or without R-groups; `bbox` may be among them).
    Empty when there is none."""
    own = tuple(bbox)
    others = [tuple(d) for d in drawings or [] if tuple(d) != own]
    found: set[str] = set()
    for names, first, whole in _legends(boxes):
        mine = _distance(own, first, whole)
        if mine is None:
            continue
        rivals = (_distance(d, first, whole) for d in others)
        if all(r is None or mine <= r for r in rivals):
            found |= names
    return found


def keep_series(rows: list[dict], compounds: set[str]) -> list[dict]:
    """The rows of the drawing's own series; all rows when no series label was found."""
    if not compounds:
        return rows
    return [r for r in rows if r.get("compound") in compounds]
