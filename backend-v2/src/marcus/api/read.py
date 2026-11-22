"""Read helpers shared by the route modules (routes never import each other)."""

import hashlib
import logging
import uuid
from collections import OrderedDict, defaultdict
from typing import NamedTuple, TypeVar

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.chem import inchikeys
from marcus.api.chempool import CHEM
from marcus.api.schemas import CurationOut, PaperSummary, PredictionOut, SegmentOut, StepOut
from marcus.core.enums import (
    FINISHED_STEPS,
    Engine,
    StepKind,
    StepStatus,
)
from marcus.core.main_figure import Entry, link_repeats
from marcus.core.models import Curation, MainFigure, Paper, Prediction, Segment, Step
from marcus.core.pipeline import ACTIVE, PAGE_KINDS, in_paper_progress, page_step_order
from marcus.core.rgroup_labels import shown_labels

log = logging.getLogger(__name__)

IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600"}


class PaperCounts(NamedTuple):
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int
    failed: int
    # the read's coarse progress, as the workspace reads it from the steps (readingProgress.ts)
    pages_read: int = 0  # pages whose newest render_page/segment_page step has ended
    structures_total: int = 0  # structures with an OCSR step
    structures_read: int = 0  # of those, read once, or with nothing in flight
    text_read: bool | None = None  # every docling step ended; None: it has none (paper_summary)
    check_started: bool = False  # a check_pdf step runs or ended
    rereading: bool = False  # busy only with OCSR runs on structures already read


async def waiting_ocsr_step(db: AsyncSession, where, engine: Engine) -> uuid.UUID | None:
    """The OCSR step of `engine` still waiting or running for `where` (a segment's or an image
    job's steps): a repeat click gets it back instead of queueing another one."""
    return await db.scalar(
        select(Step.id)
        .where(
            where,
            Step.kind == StepKind.OCSR.value,
            Step.engine == engine.value,
            Step.status.in_(ACTIVE),
        )
        .limit(1)
    )


def _failed_structure():
    """True for a segment the workspace shows as Failed (frontend cardState): no decision, no
    valid prediction, no OCSR step in flight, and its newest OCSR step failed."""
    ocsr = and_(Step.segment_id == Segment.id, Step.kind == StepKind.OCSR.value)
    newest = (
        select(Step.status)
        .where(ocsr)
        .order_by(Step.created_at.desc(), Step.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    return and_(
        or_(Curation.status.is_(None), Curation.status.not_in(("accepted", "rejected"))),
        ~exists().where(Prediction.segment_id == Segment.id, Prediction.valid.is_(True)),
        ~exists().where(ocsr, Step.status.in_(ACTIVE)),
        newest == StepStatus.FAILED.value,
    )


async def paper_counts(
    db: AsyncSession, paper_ids: list[uuid.UUID], hidden: set[uuid.UUID] | None = None
) -> dict[uuid.UUID, PaperCounts]:
    """Structure, failure and progress counts per paper: two queries, whatever the number of
    papers (one over the segments, one over the steps).

    `hidden`: segments left out of the structure counts, the repeats of main-figure structures
    (repeat_ids): the paper list counts each compound once, as the workspace does.
    structures = segments; accepted / rejected = curations with that status; failed = the
    undecided ones whose read failed (_failed_structure); to_review = the rest (every segment
    has a curation row). failed_pages = distinct pages whose newest
    render_page or segment_page step, across both kinds (the order retry_page uses), is failed.
    A retry in flight (pending, queued, running) is the newest step, so the page is not counted
    while it runs; retry_page itself still sees the old failure standing and answers "busy".
    The progress fields are PaperCounts'."""
    if not paper_ids:
        return {}
    seg_rows = await db.execute(
        select(
            Segment.paper_id,
            func.count(),
            func.count().filter(Curation.status == "accepted"),
            func.count().filter(Curation.status == "rejected"),
            func.count().filter(_failed_structure()),
        )
        .select_from(Segment)
        .outerjoin(Curation, Curation.segment_id == Segment.id)
        .where(Segment.paper_id.in_(paper_ids), *([Segment.id.not_in(hidden)] if hidden else []))
        .group_by(Segment.paper_id)
    )
    progress = {row.paper_id: row for row in (await db.execute(_step_counts(paper_ids))).all()}
    out = {}
    for pid in paper_ids:
        row = progress.get(pid)
        if row is None:
            out[pid] = PaperCounts(0, 0, 0, 0, 0, 0)
            continue
        active = row.active
        out[pid] = PaperCounts(
            0, 0, 0, 0, row.failed_pages or 0, 0,
            pages_read=row.pages_read or 0,
            structures_total=row.structures_total or 0,
            structures_read=row.structures_read or 0,
            text_read=row.docling_ended == row.docling if row.docling else None,
            check_started=bool(row.check_started),
            rereading=active > 0 and (row.rereads or 0) == active,
        )  # fmt: skip
    for pid, total, accepted, rejected, broken in seg_rows.all():
        rest = total - accepted - rejected - broken
        out[pid] = out[pid]._replace(
            structures=total, accepted=accepted, rejected=rejected, to_review=rest, failed=broken
        )
    return out


def _step_counts(paper_ids: list[uuid.UUID]):
    """One row per paper with steps: the step counts paper_counts needs, from three grouped
    subqueries over its steps (all of them, each page's newest page step, each structure's
    OCSR steps) joined on the paper."""
    active = Step.status.in_(ACTIVE)
    ended = Step.status.in_(FINISHED_STEPS)
    kind = Step.kind
    steps = (
        select(
            Step.paper_id,
            func.count().filter(active).label("active"),
            func.count().filter(kind == StepKind.DOCLING.value).label("docling"),
            func.count().filter(ended, kind == StepKind.DOCLING.value).label("docling_ended"),
            func.count()
            .filter(ended | (Step.status == StepStatus.RUNNING.value))
            .filter(kind == StepKind.CHECK_PDF.value)
            .label("check_started"),
        )
        .where(Step.paper_id.in_(paper_ids), in_paper_progress())
        .group_by(Step.paper_id)
        .subquery()
    )
    newest = (
        select(Step.paper_id, Step.page, Step.status)
        .ext(distinct_on(Step.paper_id, Step.page))
        .where(
            Step.paper_id.in_(paper_ids),
            Step.page.is_not(None),
            Step.kind.in_(PAGE_KINDS),
        )
        .order_by(Step.paper_id, Step.page, *page_step_order(), Step.id)
        .subquery()
    )
    pages = (
        select(
            newest.c.paper_id,
            func.count().filter(newest.c.status == StepStatus.FAILED.value).label("failed_pages"),
            func.count().filter(newest.c.status.in_(FINISHED_STEPS)).label("pages_read"),
        )
        .group_by(newest.c.paper_id)
        .subquery()
    )
    per_structure = (
        select(
            Step.paper_id,
            func.bool_or(Step.status == StepStatus.DONE.value).label("read"),
            func.count().filter(active).label("busy"),
        )
        .where(
            Step.paper_id.in_(paper_ids),
            Step.kind == StepKind.OCSR.value,
            Step.segment_id.is_not(None),
        )
        .group_by(Step.paper_id, Step.segment_id)
        .subquery()
    )
    read, busy = per_structure.c.read, per_structure.c.busy
    structures = (
        select(
            per_structure.c.paper_id,
            func.count().label("structures_total"),
            func.count().filter(read | (busy == 0)).label("structures_read"),
            func.sum(busy).filter(read).label("rereads"),
        )
        .group_by(per_structure.c.paper_id)
        .subquery()
    )
    return select(
        steps.c.paper_id,
        steps.c.active,
        steps.c.docling,
        steps.c.docling_ended,
        steps.c.check_started,
        pages.c.failed_pages,
        pages.c.pages_read,
        structures.c.structures_total,
        structures.c.structures_read,
        structures.c.rereads,
    ).select_from(
        steps.outerjoin(pages, pages.c.paper_id == steps.c.paper_id).outerjoin(
            structures, structures.c.paper_id == steps.c.paper_id
        )
    )


def paper_summary(paper: Paper, counts: PaperCounts) -> PaperSummary:
    fields = PaperSummary.model_fields.keys() - PaperCounts._fields
    values = counts._asdict()
    if counts.text_read is None:  # no docling step (a paper read before it existed): its pages
        values["text_read"] = paper.pages is not None and counts.pages_read >= paper.pages
    return PaperSummary(**{f: getattr(paper, f) for f in fields}, **values)


async def steps_by_status(db: AsyncSession, paper_id: uuid.UUID) -> dict[str, int]:
    """The paper's steps per status (rgroups steps aside: they are not part of its read)."""
    rows = await db.execute(
        select(Step.status, func.count())
        .where(Step.paper_id == paper_id, in_paper_progress())
        .group_by(Step.status)
    )
    return {status: n for status, n in rows.all()}


async def load_segments(db: AsyncSession, paper_id: uuid.UUID):
    """Segments in (page, idx) order, curation per segment, predictions per segment (newest
    first). Three queries, whatever the number of segments."""
    return await _load_segments(db, [paper_id])


async def _load_segments(db: AsyncSession, paper_ids: list[uuid.UUID]):
    """load_segments for several papers at once: segments in (paper, page, idx) order."""
    of_papers = Segment.paper_id.in_(paper_ids)
    segments = list(
        (
            await db.execute(
                select(Segment)
                .where(of_papers)
                .order_by(Segment.paper_id, Segment.page, Segment.idx)
            )
        ).scalars()
    )
    curations = {
        c.segment_id: c
        for c in (
            await db.execute(
                select(Curation).join(Segment, Segment.id == Curation.segment_id).where(of_papers)
            )
        ).scalars()
    }
    predictions: dict[uuid.UUID, list[Prediction]] = defaultdict(list)
    for p in (
        await db.execute(
            select(Prediction)
            .join(Segment, Segment.id == Prediction.segment_id)
            .where(of_papers)
            .order_by(Prediction.created_at.desc(), Prediction.id)
        )
    ).scalars():
        predictions[p.segment_id].append(p)
    return segments, curations, predictions


_Structure = TypeVar("_Structure", CurationOut, PredictionOut)


def named_on(index: dict | None, page: int) -> list[str] | None:
    """The R-group labels a paper's page names (papers.rgroup_text_labels), None without an
    index."""
    return None if index is None else index.get(str(page), [])


def structure_out(model: type[_Structure], row: object, named: list[str] | None) -> _Structure:
    """A prediction or curation for the API, with the R-group labels shown for it: those its
    page names (marcus.core.rgroup_labels.shown_labels), `placeholder` from all of them. Every
    endpoint that returns a paper's structure goes through here."""
    out = model.model_validate(row)
    out.rgroups = shown_labels(out.rgroups, named)
    return out


def pick_prediction(valid: list[Prediction], paper_engine: str) -> Prediction | None:
    """The prediction shown and exported when nothing is curated: of `valid` (newest first),
    the newest of the paper's engine, else the newest of any engine. The one rule; the stored
    depiction (api.depiction.shown_structure) and the UI (cardState shownPrediction) agree."""
    return next((p for p in valid if p.engine == paper_engine), None) or next(iter(valid), None)


def shown_source(
    paper_engine: str, curation: Curation | None, predictions: list[Prediction]
) -> tuple[str, str] | None:
    """("smiles" | "molfile", value) of the structure a segment shows, as the export picks it
    (curated, else pick_prediction), whatever its status; None without one, and for an R-group
    scaffold (it stands for several compounds). `predictions`: the segment's, newest first."""
    if curation is not None and (curation.smiles or curation.molfile):
        if curation.rgroups:
            return None
        return ("smiles", curation.smiles) if curation.smiles else ("molfile", curation.molfile)
    pick = pick_prediction([p for p in predictions if p.valid], paper_engine)
    if pick is None or not pick.smiles or pick.rgroups:
        return None
    return "smiles", pick.smiles


# InChIKeys already computed, per (kind, sha256 of the value): a paper's live refreshes ask the
# chem process only for structures it has not seen. Bounded, oldest out first.
_KEYS: OrderedDict[tuple[str, str], str | None] = OrderedDict()
KEY_CACHE_MAX = 20_000


async def _inchikeys(items: list[tuple[str, str]]) -> list[str | None]:
    """inchikey of each (kind, value), from the cache or one chem-process trip (HTTPException
    503 when it is busy)."""
    names = [(kind, hashlib.sha256(value.encode()).hexdigest()) for kind, value in items]
    found = {n: _KEYS[n] for n in names if n in _KEYS}
    todo = {n: item for n, item in zip(names, items, strict=True) if n not in found}
    if todo:
        keys = await CHEM.run(inchikeys, list(todo.values()))
        found.update(zip(todo, keys, strict=True))
    for n in names:
        _KEYS[n] = found[n]
        _KEYS.move_to_end(n)
    while len(_KEYS) > KEY_CACHE_MAX:
        _KEYS.popitem(last=False)
    return [found[n] for n in names]


async def main_figure_page(db: AsyncSession, paper_id: uuid.UUID) -> int | None:
    """The page (0-based) marked as the paper's main figure; None: none."""
    return await db.scalar(select(MainFigure.page).where(MainFigure.paper_id == paper_id))


async def repeat_links(
    paper: Paper,
    main_page: int | None,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    strict: bool = False,
) -> dict[uuid.UUID, uuid.UUID]:
    """repeat segment id -> its main-figure segment id (marcus.core.main_figure); empty
    without a main figure (`main_page` None). `segments` in (page, idx) order. When the chem
    process is busy: 503 if `strict` (an export must not count a compound twice), else no links
    (a read)."""
    if main_page is None:
        return {}
    sources = [
        shown_source(paper.engine, curations.get(s.id), predictions.get(s.id, [])) for s in segments
    ]
    try:
        keys = iter(await _inchikeys([src for src in sources if src is not None]))
    except HTTPException:
        if strict:
            raise
        log.warning("repeat links skipped: chem process busy")
        return {}
    entries = [
        # compound_id: phase B item 4 (the ID printed by the drawing) fills it; not read yet.
        Entry(s.id, s.page, next(keys) if src is not None else None)
        for s, src in zip(segments, sources, strict=True)
    ]
    return link_repeats(entries, main_page)


async def repeat_ids(db: AsyncSession, papers: list[Paper]) -> set[uuid.UUID]:
    """The segments of `papers` that repeat a main-figure structure (repeat_links), for the
    paper list's counts. Only papers with a main figure cost anything: one query for the main
    pages, three for all their segments, one chem-process trip for the InChIKeys not cached.
    The chem process busy: none (the counts then include the repeats)."""
    if not papers:
        return set()
    mains = dict(
        (
            await db.execute(
                select(MainFigure.paper_id, MainFigure.page).where(
                    MainFigure.paper_id.in_([p.id for p in papers])
                )
            )
        ).all()
    )
    if not mains:
        return set()
    segments, curations, predictions = await _load_segments(db, list(mains))
    by_paper: dict[uuid.UUID, list[Segment]] = defaultdict(list)
    for seg in segments:
        by_paper[seg.paper_id].append(seg)
    marked = [p for p in papers if p.id in mains]
    # One trip for every paper's structures; repeat_links below then reads them from the cache.
    sources = [
        src
        for p in marked
        for s in by_paper[p.id]
        if (src := shown_source(p.engine, curations.get(s.id), predictions.get(s.id, [])))
    ]
    try:
        await _inchikeys(sources)
    except HTTPException:
        log.warning("repeat counts skipped: chem process busy")
        return set()
    out: set[uuid.UUID] = set()
    for p in marked:
        links = await repeat_links(p, mains[p.id], by_paper[p.id], curations, predictions)
        out.update(links)
    return out


async def segments_out(db: AsyncSession, paper: Paper, main_page: int | None) -> list[SegmentOut]:
    """The paper's segments; each structure shows the R-group labels its page's text names,
    and a repeat of a main-figure structure (`main_page`: main_figure_page) names it
    (repeat_links)."""
    segments, curations, predictions = await load_segments(db, paper.id)
    index = paper.rgroup_text_labels
    repeats = await repeat_links(paper, main_page, segments, curations, predictions)
    return [
        SegmentOut(
            id=seg.id,
            page=seg.page,
            idx=seg.idx,
            bbox=list(seg.bbox),
            repeat_of=repeats.get(seg.id),
            curation=(
                structure_out(CurationOut, curations[seg.id], named_on(index, seg.page))
                if seg.id in curations
                else None
            ),
            predictions=[
                structure_out(PredictionOut, p, named_on(index, seg.page))
                for p in predictions[seg.id]
            ],
        )
        for seg in segments
    ]


async def steps_out(db: AsyncSession, paper_id: uuid.UUID) -> list[StepOut]:
    """The paper's steps, oldest first (created_at, seq). Rgroups steps are left out: they are
    not part of the paper's read (their state is served by marcus.api.routes.rgroups)."""
    rows = (
        await db.execute(
            select(Step)
            .where(Step.paper_id == paper_id, in_paper_progress())
            .order_by(Step.created_at, Step.seq, Step.id)
        )
    ).scalars()
    return [StepOut.model_validate(s) for s in rows]
