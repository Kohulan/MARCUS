"""R-group rows of a scaffold, read by the local R-group model (Markush Phase 2).

    GET  /papers/{id}/rgroups              the paper's readings and whether the feature is on
    GET  /predictions/{id}/rgroups         one prediction's reading (status "none": never asked)
    POST /predictions/{id}/rgroups         start by hand; {"rerun": true} runs it again

Every route is owner-scoped (another owner's paper or prediction is the same 404 as a missing
one; a prediction of an image job has no paper and is a 404 too). POST is rate-limited per
owner (`rate_limit_rgroup_per_min`, failing closed) and idempotent: a step still waiting or
running is returned again, and a prediction that has rows gets 200 with no step unless `rerun`
is asked for. A prediction without R-group labels is refused (409). The paper's status does not
change, so there is no event stream for it: a client reads GET again while a reading is queued
or running, or `auto_pending` names a scaffold whose reading starts by itself (the dispatcher,
marcus.core.auto; no rate limit is charged for that).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api import rgroups as reads
from marcus.api.deps import current_owner, get_owned_paper, not_found, visible
from marcus.api.read import named_on
from marcus.api.schemas import RgroupExtractionOut, RgroupList, RgroupStart, RgroupStarted
from marcus.api.security import rgroup_limit
from marcus.core import auto
from marcus.core.db import get_db
from marcus.core.enums import StepKind
from marcus.core.models import Owner, Paper, Prediction, Segment
from marcus.core.pipeline import RgroupsNotAllowed, request_rgroups
from marcus.core.queues import queue_for

router = APIRouter()

NOT_AVAILABLE = "R-group reading is not available"
NOT_RUNNING = "The R-group model is not running"
NO_RGROUPS = "This structure has no R-groups"
MAX_LISTED = 1000  # = the most structures a paper's pages can hold here, in practice


async def get_owned_prediction(
    db: AsyncSession, owner: Owner, prediction_id: uuid.UUID
) -> tuple[Prediction, list[str] | None]:
    """A prediction of one of the owner's visible papers, with the R-group labels its page names
    (read.named_on), else the one 404."""
    found = (
        await db.execute(
            select(Prediction, Segment.page, Paper.rgroup_text_labels)
            .join(Segment, Segment.id == Prediction.segment_id)
            .join(Paper, Paper.id == Segment.paper_id)
            .where(Prediction.id == prediction_id, Paper.owner_id == owner.id, *visible(Paper))
        )
    ).one_or_none()
    if found is None:
        raise not_found()
    prediction, page, index = found
    return prediction, named_on(index, page)


@router.get("/papers/{paper_id}/rgroups", response_model=RgroupList)
async def get_paper_rgroups(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> RgroupList:
    paper = await get_owned_paper(db, owner, paper_id, with_labels=True)
    return RgroupList(
        available=reads.available(),
        extractions=await reads.for_paper(db, paper.id, paper.rgroup_text_labels),
        auto_pending=await _auto_pending(db, paper.id),
    )


async def _auto_pending(db: AsyncSession, paper_id: uuid.UUID) -> list[uuid.UUID]:
    """The paper's scaffolds whose reading is about to start by itself: candidates within the
    last few dispatcher passes (marcus.core.auto START_S). After that a reading that did not
    start leaves the card's action. One narrow query; never the broker."""
    query = auto.candidates_query(
        StepKind.RGROUPS, paper_id, within_s=auto.START_S, limit=MAX_LISTED
    )
    return [] if query is None else list((await db.execute(query)).scalars())


@router.get("/predictions/{prediction_id}/rgroups", response_model=RgroupExtractionOut)
async def get_prediction_rgroups(
    prediction_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> RgroupExtractionOut:
    prediction, named = await get_owned_prediction(db, owner, prediction_id)
    return await reads.for_prediction(db, prediction, named)


@router.post(
    "/predictions/{prediction_id}/rgroups",
    status_code=202,
    response_model=RgroupStarted,
    dependencies=[Depends(rgroup_limit)],
)
async def start_rgroups(
    request: Request,
    response: Response,
    prediction_id: uuid.UUID,
    body: RgroupStart | None = None,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> RgroupStarted:
    # Both before the owner check (no existence oracle). Offered, but no worker consumes q.rgroup:
    # refuse instead of queueing a step nobody runs.
    if not reads.available():
        raise HTTPException(status_code=503, detail=NOT_AVAILABLE)
    if queue_for(StepKind.RGROUPS, None) not in await request.app.state.live_queues():
        raise HTTPException(status_code=503, detail=NOT_RUNNING)
    prediction, _ = await get_owned_prediction(db, owner, prediction_id)
    rerun = body.rerun if body is not None else False
    try:
        step = await db.run_sync(lambda s: request_rgroups(s, prediction.id, rerun=rerun))
    except RgroupsNotAllowed:
        await db.rollback()
        raise HTTPException(status_code=409, detail=NO_RGROUPS) from None
    except ValueError:
        await db.rollback()
        raise not_found() from None  # deleted meanwhile
    await db.commit()
    if step is None:
        response.status_code = 200
        return RgroupStarted(step_id=None)
    return RgroupStarted(step_id=step.id)
