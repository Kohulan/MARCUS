"""Main figure repeats: which structures on other pages are compounds of the main figure.

The user marks one page of a paper as its main figure, the figure that lists the compounds
(papers.main_figure_page). A structure on another page is a repeat of a main-figure structure
when both show the same compound: the same InChIKey of the structure shown (api.read
shown_source), or the same compound ID. A repeat links to the first such main-figure structure
in (page, idx) order; the workspace shows it once, and exports and COCONUT count it once.
Structures on the main page itself are never repeats, even of each other.

A main structure and its repeats are one group with one status (group_status): accepted if any
member is, rejected only if all are, else to review. An accepted group exports and sends the
structure of an accepted member (chosen_member), so a decision on a repeat is never lost.

A decision on a main structure goes to its repeats (api.decisions), marked inherited. An
inherited status holds only while the structure is still a repeat of that main one; else it
reads as unchecked (stale_members), so it is never exported unreviewed.

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


ACCEPTED, REJECTED, UNCHECKED = "accepted", "rejected", "unchecked"


def group_status(statuses: list[str | None]) -> str:
    """One status for a linked group (a main-figure structure and its repeats): accepted if any
    member is accepted; rejected only if every member is rejected; else unchecked (to review).
    None (no curation row) counts as unchecked."""
    if ACCEPTED in statuses:
        return ACCEPTED
    if statuses and all(s == REJECTED for s in statuses):
        return REJECTED
    return UNCHECKED


def groups_of(links: dict[uuid.UUID, uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """main segment id -> its repeats, in the order of `links` (link_repeats keeps (page, idx))."""
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for repeat, main in links.items():
        out.setdefault(main, []).append(repeat)
    return out


def chosen_member(
    main: uuid.UUID, repeats: list[uuid.UUID], status_of: dict[uuid.UUID, str | None]
) -> uuid.UUID:
    """The member whose structure an accepted group exports and sends: the main one when it is
    accepted, else the first accepted repeat; the main one for a group not accepted."""
    if status_of.get(main) == ACCEPTED:
        return main
    return next((r for r in repeats if status_of.get(r) == ACCEPTED), main)


def stale_members(
    inherited: dict[uuid.UUID, uuid.UUID], links: dict[uuid.UUID, uuid.UUID] | None
) -> frozenset[uuid.UUID]:
    """The structures whose inherited status (`inherited`: structure -> the main structure it
    came from) no longer holds: not a repeat of that main one now. `links` None (not known):
    all of them. Their status reads as unchecked (effective_statuses)."""
    if links is None:
        return frozenset(inherited)
    return frozenset(m for m, main in inherited.items() if links.get(m) != main)


def effective_statuses(
    status_of: dict[uuid.UUID, str | None], stale: frozenset[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """The statuses as reads, counts and exports use them: a stale inherited one is unchecked."""
    return {sid: (UNCHECKED if sid in stale else st) for sid, st in status_of.items()}


@dataclass(frozen=True)
class CountFix:
    """How the structure counts treat linked groups (api.read.paper_counts): `hidden` repeats
    are not counted; a main in `promote` counts as accepted (an accepted repeat); a rejected main
    in `unreject` counts as to review (a repeat not rejected); a `stale` inherited status counts
    as to review."""

    hidden: frozenset[uuid.UUID] = frozenset()
    promote: frozenset[uuid.UUID] = frozenset()
    unreject: frozenset[uuid.UUID] = frozenset()
    stale: frozenset[uuid.UUID] = frozenset()

    def __or__(self, other: "CountFix") -> "CountFix":
        return CountFix(
            self.hidden | other.hidden,
            self.promote | other.promote,
            self.unreject | other.unreject,
            self.stale | other.stale,
        )


def count_fix(
    links: dict[uuid.UUID, uuid.UUID],
    status_of: dict[uuid.UUID, str | None],
    stale: frozenset[uuid.UUID] = frozenset(),
) -> CountFix:
    """The CountFix of one paper's links: each group counts once, under group_status (of the
    effective statuses: `stale` inherited ones are unchecked)."""
    status_of = effective_statuses(status_of, stale)
    promote, unreject = set(), set()
    for main, repeats in groups_of(links).items():
        status = group_status([status_of.get(m) for m in [main, *repeats]])
        if status == ACCEPTED and status_of.get(main) != ACCEPTED:
            promote.add(main)
        elif status == UNCHECKED and status_of.get(main) == REJECTED:
            unreject.add(main)
    return CountFix(frozenset(links), frozenset(promote), frozenset(unreject), stale)
