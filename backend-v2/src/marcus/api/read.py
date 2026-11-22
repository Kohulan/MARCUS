"""Read helpers shared by the route modules (routes never import each other)."""

import uuid
from collections import defaultdict
from typing import NamedTuple, TypeVar

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import CurationOut, PaperSummary, PredictionOut, SegmentOut, StepOut
from marcus.core.enums import (
    FINISHED_STEPS,
    Engine,
    StepKind,
    StepStatus,
)
from marcus.core.models import Curation, Paper, Prediction, Segment, Step
from marcus.core.pipeline import ACTIVE, PAGE_KINDS, in_paper_progress, page_step_order
from marcus.core.rgroup_labels import shown_labels

IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600"}


class PaperCounts(NamedTuple):
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int
    failed: int
    # always false: an annotation runs beside the read, never keeping the paper busy (kept in the
    # API for older clients)
    annotating: bool = False
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
    db: AsyncSession, paper_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PaperCounts]:
    """Structure, failure and progress counts per paper: two queries, whatever the number of
    papers (one over the segments, one over the steps).

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
        .where(Segment.paper_id.in_(paper_ids))
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
    segments = list(
        (
            await db.execute(
                select(Segment)
                .where(Segment.paper_id == paper_id)
                .order_by(Segment.page, Segment.idx)
            )
        ).scalars()
    )
    curations = {
        c.segment_id: c
        for c in (
            await db.execute(
                select(Curation)
                .join(Segment, Segment.id == Curation.segment_id)
                .where(Segment.paper_id == paper_id)
            )
        ).scalars()
    }
    predictions: dict[uuid.UUID, list[Prediction]] = defaultdict(list)
    for p in (
        await db.execute(
            select(Prediction)
            .join(Segment, Segment.id == Prediction.segment_id)
            .where(Segment.paper_id == paper_id)
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


async def segments_out(db: AsyncSession, paper: Paper) -> list[SegmentOut]:
    """The paper's segments; each structure shows the R-group labels its page's text names."""
    segments, curations, predictions = await load_segments(db, paper.id)
    index = paper.rgroup_text_labels
    return [
        SegmentOut(
            id=seg.id,
            page=seg.page,
            idx=seg.idx,
            bbox=list(seg.bbox),
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
