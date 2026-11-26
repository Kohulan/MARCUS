"""Built structures in the database (Markush Phase 3, owner decision 2026-11-25).

A scaffold's R-group rows, built by marcus.core.enumeration, become cards: per built row a
Segment (the scaffold's paper, page, bbox and crop; idx BUILT_IDX + n, never a segmenter idx,
which stays below pipeline.MAX_SEGMENTS_PER_PAGE), a Prediction of engine `enumerated` and an
unchecked Curation, linked to the scaffold by a BuiltSegment row. The rows that could not be
built are kept on the scaffold (ScaffoldBuild.failures), shown as "Could not build".

Rebuild (the button again, e.g. after the rows were read again), per compound ID:
- a card a curator decided, edited, noted, or whose status is inherited: never touched;
- an untouched card: same input (hash of the scaffold structure and the row's groups) kept,
  changed input refreshed (a new prediction), a row that no longer builds or is gone removed;
- a new row that builds: a new card.

`built_clause` (SQL) and `is_built_idx` keep built segments out of OCSR, pick candidates, the
segmentation cache and compound-ID reading (the guards: marcus.core.picks, pipeline, api.read).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from marcus.core.enums import BUILT_ENGINE, PaperStatus
from marcus.core.locks import lock_row
from marcus.core.models import (
    BuiltSegment,
    Curation,
    InheritedStatus,
    Paper,
    Prediction,
    ScaffoldBuild,
    Segment,
)
from marcus.core.substituents import RESOLVER_VERSION

BUILT_IDX = 10_000


class IsBuilt(Exception):
    """The segment is itself a built structure: no OCSR, no R-group reading, no build on it."""


def is_built_idx(idx: int) -> bool:
    """True for a built segment's idx (a segmenter idx stays below 1000)."""
    return idx >= BUILT_IDX


def built_clause():
    """SQL condition, true for a Segment row that is a built structure (correlated)."""
    return select(BuiltSegment.segment_id).where(BuiltSegment.segment_id == Segment.id).exists()


def input_hash(scaffold: tuple[str, str], groups: dict) -> str:
    # the rule set too: a fixed resolver refreshes an untouched card on the next build
    text = json.dumps(
        {"scaffold": list(scaffold), "groups": groups, "resolver": RESOLVER_VERSION},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def touched(curation: Curation | None, inherited: bool) -> bool:
    """A curator's work on the card: a decision, an own structure, a note, or an inherited
    status."""
    if inherited:
        return True
    if curation is None:
        return False
    return bool(
        curation.status != "unchecked"
        or curation.smiles
        or curation.molfile
        or (curation.note or "").strip()
    )


@dataclass
class BuildSummary:
    built: list[uuid.UUID] = field(default_factory=list)  # new cards
    refreshed: int = 0
    kept: int = 0
    removed: int = 0
    failures: list[dict] = field(default_factory=list)


def _prediction(segment_id: uuid.UUID, outcome: dict) -> Prediction:
    return Prediction(
        segment_id=segment_id,
        engine=BUILT_ENGINE,
        engine_version=RESOLVER_VERSION,
        smiles=outcome["smiles"],
        molfile=None,
        valid=True,
        ms=0,
        rgroups=[],
        inchikey=outcome["inchikey"],
    )


def _forget(session: Session, gone: set[uuid.UUID]) -> None:
    """Drop the session's objects of deleted segments (the database cascaded their rows)."""
    for key in list(session.identity_map.keys()):
        obj = session.identity_map.get(key)
        if obj is None:
            continue
        sid = obj.__dict__.get("segment_id") if not isinstance(obj, Segment) else key[1][0]
        if sid in gone:
            session.expunge(obj)


def apply_build(
    session: Session,
    scaffold_segment_id: uuid.UUID,
    scaffold: tuple[str, str],
    outcomes: list[dict],
    names: dict[str, str] | None = None,
) -> BuildSummary:
    """Write a build of the scaffold's rows (enumeration.build_rows outcomes) and apply the
    rebuild rule. Locks the paper first. Caller commits. Raises ValueError for a missing segment
    or a deleted paper, IsBuilt when the scaffold is itself built."""
    names = names or {}
    seg = session.get(Segment, scaffold_segment_id)
    if seg is None:
        raise ValueError("segment not found")
    paper = lock_row(session, Paper, seg.paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper is deleted")
    if session.get(BuiltSegment, seg.id) is not None:
        raise IsBuilt()
    existing = {
        b.row_key: b
        for b in session.execute(
            select(BuiltSegment).where(BuiltSegment.scaffold_segment_id == seg.id)
        ).scalars()
    }
    ids = [b.segment_id for b in existing.values()]
    curations = {
        c.segment_id: c
        for c in session.execute(select(Curation).where(Curation.segment_id.in_(ids))).scalars()
    }
    inherited = set(
        session.execute(
            select(InheritedStatus.segment_id).where(InheritedStatus.segment_id.in_(ids))
        ).scalars()
    )
    top = session.execute(
        select(func.max(Segment.idx)).where(
            Segment.paper_id == seg.paper_id, Segment.page == seg.page, Segment.idx >= BUILT_IDX
        )
    ).scalar_one()
    next_idx = (top if top is not None else BUILT_IDX) + 1
    summary = BuildSummary()
    gone: list[uuid.UUID] = []
    seen: set[str] = set()
    for o in outcomes:
        key = o["compound"]
        seen.add(key)
        ok = "inchikey" in o
        if not ok:
            summary.failures.append({"compound": key, "reason": o["reason"]})
        link = existing.get(key)
        if link is not None:
            if touched(curations.get(link.segment_id), link.segment_id in inherited):
                summary.kept += 1
            elif not ok:
                gone.append(link.segment_id)
            else:
                digest = input_hash(scaffold, o["groups"])
                if link.input_hash == digest:
                    summary.kept += 1
                else:
                    session.execute(
                        delete(Prediction).where(
                            Prediction.segment_id == link.segment_id,
                            Prediction.engine == BUILT_ENGINE,
                        )
                    )
                    session.add(_prediction(link.segment_id, o))
                    link.input_hash = digest
                    link.name = names.get(key)
                    summary.refreshed += 1
            continue
        if not ok:
            continue
        child = Segment(
            paper_id=seg.paper_id,
            page=seg.page,
            idx=next_idx,
            bbox=list(seg.bbox),
            image_sha256=seg.image_sha256,
        )
        next_idx += 1
        session.add(child)
        session.flush()
        session.add(_prediction(child.id, o))
        session.add(Curation(segment_id=child.id, status="unchecked"))
        session.add(
            BuiltSegment(
                segment_id=child.id,
                scaffold_segment_id=seg.id,
                row_key=key,
                name=names.get(key),
                input_hash=input_hash(scaffold, o["groups"]),
            )
        )
        summary.built.append(child.id)
    for key, link in existing.items():
        if key in seen:
            continue
        if touched(curations.get(link.segment_id), link.segment_id in inherited):
            summary.kept += 1
        else:
            gone.append(link.segment_id)
    if gone:
        session.execute(
            delete(Segment).where(Segment.id.in_(gone)).execution_options(synchronize_session=False)
        )
        _forget(session, set(gone))
        summary.removed = len(gone)
    build = session.get(ScaffoldBuild, seg.id)
    if build is None:
        session.add(ScaffoldBuild(scaffold_segment_id=seg.id, failures=summary.failures))
    else:
        build.failures = summary.failures
        build.built_at = func.now()
    session.flush()
    return summary
