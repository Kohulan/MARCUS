import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api import annotation as annotations
from marcus.api import export
from marcus.api import rgroups as rgroup_reads
from marcus.api.chempool import CHEM
from marcus.api.deps import (
    client_ip,
    current_owner,
    get_owned_paper,
    not_found,
    require_engine_enabled,
    visible,
    work_ip,
)
from marcus.api.limits import enforce_active_limits
from marcus.api.read import (
    IMAGE_HEADERS,
    load_segments,
    paper_counts,
    paper_summary,
    segments_out,
    steps_by_status,
    steps_out,
)
from marcus.api.schemas import (
    BulkCurationIn,
    BulkCurationOut,
    Counts,
    PaperDetail,
    PaperList,
    SegmentList,
    StepAccepted,
    StepList,
)
from marcus.api.security import upload_limit
from marcus.api.uploads import read_limited, sanitize_display_name, sniff_pdf
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine, PaperStatus
from marcus.core.models import Curation, Owner, Paper, Segment
from marcus.core.pipeline import (
    RetryNotAllowed,
    cancel_paper,
    new_paper,
    remove_paper_files,
    retry_page,
    store_pdf,
)
from marcus.core.settings import get_settings

router = APIRouter()


@router.post("/papers", status_code=202, dependencies=[Depends(upload_limit)])
async def upload_paper(
    request: Request,
    file: UploadFile = File(...),
    engine: Engine = Form(Engine.DECIMER),
    ocsr: Literal["auto", "off"] = Form("auto"),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    require_engine_enabled(engine)
    await enforce_active_limits(db, owner, client_ip(request))

    data = await read_limited(file, settings.max_upload_bytes)
    sniff_pdf(data)
    name = sanitize_display_name(file.filename)

    # hash and file write in a thread: up to max_upload_bytes must not block the event loop
    sha = await run_in_threadpool(lambda: hashlib.sha256(data).hexdigest())
    ip = work_ip(request)
    paper = await db.run_sync(
        lambda s: new_paper(s, owner, sha, len(data), name, engine, ocsr, started_ip=ip)
    )
    await run_in_threadpool(store_pdf, paper.id, data)  # before the commit, as start_paper
    await db.commit()
    return {"paper_id": str(paper.id), "status": PaperStatus.CHECKING.value}


@router.get("/papers", response_model=PaperList)
async def list_papers(
    owner: Owner = Depends(current_owner), db: AsyncSession = Depends(get_db)
) -> PaperList:
    papers = list(
        (
            await db.execute(
                select(Paper)
                .where(Paper.owner_id == owner.id, *visible(Paper))
                .order_by(Paper.created_at.desc(), Paper.id)
            )
        ).scalars()
    )
    counts = await paper_counts(db, [p.id for p in papers])
    return PaperList(papers=[paper_summary(p, counts[p.id]) for p in papers])


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> PaperDetail:
    paper = await get_owned_paper(db, owner, paper_id)
    counts = await steps_by_status(db, paper.id)
    return PaperDetail(
        **paper_summary(paper, (await paper_counts(db, [paper.id]))[paper.id]).model_dump(),
        counts=Counts(steps_by_status=counts),
        segments=await segments_out(db, paper.id),
    )


@router.get("/papers/{paper_id}/segments", response_model=SegmentList)
async def get_segments(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> SegmentList:
    paper = await get_owned_paper(db, owner, paper_id)
    return SegmentList(segments=await segments_out(db, paper.id))


@router.put("/papers/{paper_id}/curation", response_model=BulkCurationOut)
async def put_bulk_curation(
    paper_id: uuid.UUID,
    body: BulkCurationIn,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> BulkCurationOut:
    """Status (and note, when the key is present) for many segments of one paper, atomically."""
    paper = await get_owned_paper(db, owner, paper_id)
    ids = [item.segment_id for item in body.items]
    locked = set(
        (
            await db.execute(
                select(Segment.id)
                .where(Segment.paper_id == paper.id, Segment.id.in_(ids))
                .order_by(Segment.id)  # one lock order: overlapping bulk calls cannot deadlock
                .with_for_update()
            )
        ).scalars()
    )
    if len(locked) != len(ids):
        await db.rollback()
        raise not_found()
    rows = {
        c.segment_id: c
        for c in (await db.execute(select(Curation).where(Curation.segment_id.in_(ids)))).scalars()
    }
    now = datetime.now(UTC)
    for item in body.items:
        cur = rows.get(item.segment_id)
        if cur is None:
            cur = Curation(segment_id=item.segment_id)
            db.add(cur)
        cur.status = item.status
        if "note" in item.model_fields_set:
            cur.note = item.note
        cur.updated_at = now
    await db.commit()
    return BulkCurationOut(updated=len(ids))


@router.get("/papers/{paper_id}/steps", response_model=StepList)
async def get_steps(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StepList:
    paper = await get_owned_paper(db, owner, paper_id)
    return StepList(steps=await steps_out(db, paper.id))


@router.delete("/papers/{paper_id}", status_code=204)
async def delete_paper(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    paper = await get_owned_paper(db, owner, paper_id)
    try:
        await db.run_sync(lambda s: cancel_paper(s, paper.id, remove_files=False))
    except ValueError:
        await db.rollback()
        raise not_found() from None  # removed meanwhile
    await db.commit()
    await run_in_threadpool(remove_paper_files, paper.id)  # page PNGs and crops: off the loop


@router.get("/papers/{paper_id}/pages/{n}/image")
async def page_image(
    paper_id: uuid.UUID,
    n: int,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    paper = await get_owned_paper(db, owner, paper_id)
    if paper.pages is None or not 0 <= n < paper.pages:
        raise not_found()
    path = storage.page_image_path(paper.id, n)
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="image/png", headers=IMAGE_HEADERS)


RETRY_DETAIL = {
    "not_failed": "Page has not failed",
    "busy": "Page is still running",
    "limit": "No retries left for this page",
}


@router.post("/papers/{paper_id}/pages/{n}/retry", status_code=202, response_model=StepAccepted)
async def retry_page_route(
    request: Request,
    paper_id: uuid.UUID,
    n: int,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StepAccepted:
    paper = await get_owned_paper(db, owner, paper_id)
    if paper.pages is None or not 0 <= n < paper.pages:
        raise not_found()
    try:
        ip = work_ip(request)
        step = await db.run_sync(lambda s: retry_page(s, paper.id, n, started_ip=ip))
    except RetryNotAllowed as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=RETRY_DETAIL[exc.reason]) from None
    except ValueError:
        await db.rollback()
        raise not_found() from None  # deleted meanwhile
    await db.commit()
    return StepAccepted(step_id=step.id)


@router.get("/papers/{paper_id}/text")
async def paper_text(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    paper = await get_owned_paper(db, owner, paper_id)
    path = storage.text_path(paper.id)
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="application/json")


@router.get("/papers/{paper_id}/export")
async def export_paper(
    paper_id: uuid.UUID,
    format: export.ExportFormat = Query("json"),
    status: export.ExportStatus | None = Query(None),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> Response:
    paper = await get_owned_paper(db, owner, paper_id)
    segments, curations, predictions = await load_segments(db, paper.id)
    annotation = annotations.for_export(await annotations.load(db, paper.id))
    rows = await rgroup_reads.for_export(db, paper.id)
    # RDKit (molfile -> SMILES, SDF) holds the GIL: the whole build runs in the chem process
    content = await CHEM.run(
        export.build, format, paper, segments, curations, predictions, status, annotation, rows
    )
    return Response(
        content=content,
        media_type=export.MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="marcus-{paper.id}.{format}"'},
    )
