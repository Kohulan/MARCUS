"""Main figure repeats: which structures on other pages are compounds of the main figure.

The user marks one page of a paper as its main figure, the figure that lists the compounds
(papers.main_figure_page). A structure on another page is a repeat of a main-figure structure
when both show the same compound: the same InChIKey of the structure shown (api.read
shown_source), or the same compound ID. A repeat links to the first such main-figure structure
in (page, idx) order; the workspace shows it once, and exports and COCONUT count it once.
Structures on the main page itself are never repeats, even of each other.

The compound ID is the number or name printed under a drawing (phase B item 4). It is not read
yet, so every Entry has compound_id None and only InChIKeys link today. When it is read, fill
Entry.compound_id (api.read.repeat_links builds the entries) and the match below uses it.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    segment_id: uuid.UUID
    page: int
    # InChIKey of the structure shown; None without one (no structure, an R-group scaffold, or a
    # structure RDKit cannot read).
    inchikey: str | None
    # The compound ID printed by the drawing (phase B item 4); None until that is read.
    compound_id: str | None = None


def link_repeats(entries: list[Entry], main_page: int | None) -> dict[uuid.UUID, uuid.UUID]:
    """repeat segment id -> the main-figure segment id it repeats. `entries` in (page, idx)
    order. Empty without a main page."""
    if main_page is None:
        return {}
    by_key: dict[str, uuid.UUID] = {}
    by_id: dict[str, uuid.UUID] = {}
    for e in entries:
        if e.page != main_page:
            continue
        if e.inchikey:
            by_key.setdefault(e.inchikey, e.segment_id)
        if e.compound_id:
            by_id.setdefault(e.compound_id, e.segment_id)
    out: dict[uuid.UUID, uuid.UUID] = {}
    for e in entries:
        if e.page == main_page:
            continue
        main = (by_key.get(e.inchikey) if e.inchikey else None) or (
            by_id.get(e.compound_id) if e.compound_id else None
        )
        if main is not None:
            out[e.segment_id] = main
    return out
