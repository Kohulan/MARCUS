"""Read helpers shared by the route modules (routes never import each other)."""

import uuid
from collections import defaultdict
from typing import NamedTuple

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import CurationOut, PaperSummary, PredictionOut, SegmentOut, StepOut
from marcus.core.enums import Engine, StepKind, StepStatus
from marcus.core.models import Curation, Paper, Prediction, Segment, Step
from marcus.core.pipeline import ACTIVE, PAGE_KINDS, page_step_order

IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600"}


class PaperCounts(NamedTuple):
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int
    failed: int


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
    """Structure and failure counts per paper: two grouped queries, whatever the number of papers.

    structures = segments; accepted / rejected = curations with that status; failed = the
    undecided ones whose read failed (_failed_structure); to_review = the rest (every segment
    has a curation row). failed_pages = distinct pages whose newest
    render_page or segment_page step, across both kinds (the order retry_page uses), is failed.
    A retry in flight (pending, queued, running) is the newest step, so the page is not counted
    while it runs; retry_page itself still sees the old failure standing and answers "busy"."""
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
    failed_rows = await db.execute(
        select(newest.c.paper_id, func.count(func.distinct(newest.c.page)))
        .where(newest.c.status == StepStatus.FAILED.value)
        .group_by(newest.c.paper_id)
    )
    failed = dict(failed_rows.all())
    out = {pid: PaperCounts(0, 0, 0, 0, failed.get(pid, 0), 0) for pid in paper_ids}
    for pid, total, accepted, rejected, broken in seg_rows.all():
        rest = total - accepted - rejected - broken
        out[pid] = PaperCounts(total, accepted, rejected, rest, failed.get(pid, 0), broken)
    return out


def paper_summary(paper: Paper, counts: PaperCounts) -> PaperSummary:
    fields = PaperSummary.model_fields.keys() - PaperCounts._fields
    return PaperSummary(**{f: getattr(paper, f) for f in fields}, **counts._asdict())


async def steps_by_status(db: AsyncSession, paper_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(Step.status, func.count()).where(Step.paper_id == paper_id).group_by(Step.status)
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


async def segments_out(db: AsyncSession, paper_id: uuid.UUID) -> list[SegmentOut]:
    segments, curations, predictions = await load_segments(db, paper_id)
    return [
        SegmentOut(
            id=seg.id,
            page=seg.page,
            idx=seg.idx,
            bbox=list(seg.bbox),
            curation=(
                CurationOut.model_validate(curations[seg.id]) if seg.id in curations else None
            ),
            predictions=[PredictionOut.model_validate(p) for p in predictions[seg.id]],
        )
        for seg in segments
    ]


async def steps_out(db: AsyncSession, paper_id: uuid.UUID) -> list[StepOut]:
    """The paper's steps, oldest first (created_at, seq)."""
    rows = (
        await db.execute(
            select(Step)
            .where(Step.paper_id == paper_id)
            .order_by(Step.created_at, Step.seq, Step.id)
        )
    ).scalars()
    return [StepOut.model_validate(s) for s in rows]
