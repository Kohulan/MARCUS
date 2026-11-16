"""Read helpers shared by the route modules (routes never import each other)."""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import CurationOut, PredictionOut, SegmentOut
from marcus.core.models import Curation, Prediction, Segment, Step

IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600"}


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
