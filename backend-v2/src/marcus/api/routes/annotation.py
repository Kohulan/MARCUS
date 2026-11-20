"""A paper's annotation by the local MARCUS model (owner decision 2026-11-20).

    GET    /papers/{id}/annotation           state, model values, curated values, positions
    POST   /papers/{id}/annotation           start (on demand); {"rerun": true} runs it again
    PUT    /papers/{id}/annotation/curation  save the curator's values (all 11 fields)
    DELETE /papers/{id}/annotation/curation  reset to the model's values

Every route is owner-scoped (another owner's paper is the same 404 as a missing one). POST is
rate-limited per owner (`rate_limit_annotate_per_min`, failing closed) and idempotent: a step
still waiting or running is returned again, and a paper that has an annotation gets 200 with
no step unless `rerun` is asked for. PUT/DELETE curation are rate-limited per owner
(`rate_limit_curation_per_min`); a save holds at most 300 values, and only values not located
before are searched, in the chem process. Progress arrives on the paper's event stream
(GET /papers/{id}/events) as step events of kind `annotate`: starting the step puts a done
paper back to `processing`, so a client reopens the stream after POST.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api import annotation as reads
from marcus.api.chempool import CHEM
from marcus.api.deps import current_owner, get_owned_paper, not_found, work_ip
from marcus.api.schemas import (
    AnnotationCurationIn,
    AnnotationOut,
    AnnotationStart,
    AnnotationStarted,
)
from marcus.api.security import annotate_limit, curation_limit
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import StepKind
from marcus.core.models import Owner
from marcus.core.pipeline import AnnotateNotAllowed, request_annotation
from marcus.core.queues import queue_for
from marcus.core.settings import get_settings

router = APIRouter()

NOT_AVAILABLE = "Annotation is not available"
NOT_RUNNING = "The annotation model is not running"
NO_TEXT = "The text of this paper is not ready"
NOTHING_TO_CORRECT = "This paper has no annotation yet"


@router.get("/papers/{paper_id}/annotation", response_model=AnnotationOut)
async def get_annotation(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> AnnotationOut:
    paper = await get_owned_paper(db, owner, paper_id)
    return await reads.annotation_out(db, paper.id)


@router.post(
    "/papers/{paper_id}/annotation",
    status_code=202,
    response_model=AnnotationStarted,
    dependencies=[Depends(annotate_limit)],
)
async def start_annotation(
    request: Request,
    response: Response,
    paper_id: uuid.UUID,
    body: AnnotationStart | None = None,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> AnnotationStarted:
    # Both before the owner check (no existence oracle). Offered, but no worker consumes q.llm
    # (llama-server down, worker-llm not started): refuse instead of reopening the paper for a
    # step nobody runs.
    if not get_settings().annotate_enabled:
        raise HTTPException(status_code=503, detail=NOT_AVAILABLE)
    # the /ready consumer check and its cache (routes.health.live_queues, via create_app)
    if queue_for(StepKind.ANNOTATE, None) not in await request.app.state.live_queues():
        raise HTTPException(status_code=503, detail=NOT_RUNNING)
    paper = await get_owned_paper(db, owner, paper_id)
    rerun = body.rerun if body is not None else False
    ip = work_ip(request)
    try:
        step = await db.run_sync(
            lambda s: request_annotation(s, paper.id, rerun=rerun, started_ip=ip)
        )
    except AnnotateNotAllowed:
        await db.rollback()
        raise HTTPException(status_code=409, detail=NO_TEXT) from None
    except ValueError:
        await db.rollback()
        raise not_found() from None  # deleted meanwhile
    await db.commit()
    if step is None:
        response.status_code = 200
        return AnnotationStarted(step_id=None)
    return AnnotationStarted(step_id=step.id)


@router.put(
    "/papers/{paper_id}/annotation/curation",
    response_model=AnnotationOut,
    dependencies=[Depends(curation_limit)],
)
async def put_annotation_curation(
    paper_id: uuid.UUID,
    body: AnnotationCurationIn,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> AnnotationOut:
    paper = await get_owned_paper(db, owner, paper_id)
    row = await reads.load(db, paper.id)
    if row is None:
        raise HTTPException(status_code=409, detail=NOTHING_TO_CORRECT)
    known = reads.known_positions(row)
    await db.commit()  # end the read transaction: locating reads the text file
    # CPU-bound (text normalisation, search): in the chem process, not on the event loop's GIL
    found = await CHEM.run(reads.locate, storage.text_path(paper.id), body.values, known)
    row = await reads.load_for_update(db, paper.id)
    if row is None:  # deleted meanwhile
        await db.rollback()
        raise not_found()
    row.curated = body.values
    row.curated_positions = found
    row.curated_at = datetime.now(UTC)
    await db.commit()
    return await reads.annotation_out(db, paper.id)


@router.delete(
    "/papers/{paper_id}/annotation/curation",
    response_model=AnnotationOut,
    dependencies=[Depends(curation_limit)],
)
async def reset_annotation_curation(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> AnnotationOut:
    """Reset to the model's values (the curator's are dropped). Idempotent."""
    paper = await get_owned_paper(db, owner, paper_id)
    row = await reads.load_for_update(db, paper.id)
    if row is not None:
        row.curated = None
        row.curated_positions = None
        row.curated_at = None
    await db.commit()
    return await reads.annotation_out(db, paper.id)
