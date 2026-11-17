import uuid
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

from marcus.api import export
from marcus.api.deps import client_ip, current_owner, get_owned_paper, not_found, paper_visible
from marcus.api.limits import enforce_active_limits
from marcus.api.read import IMAGE_HEADERS, load_segments, segments_out, steps_by_status, steps_out
from marcus.api.schemas import Counts, PaperDetail, PaperList, PaperSummary, SegmentList, StepList
from marcus.api.security import upload_limit
from marcus.api.uploads import read_limited, sanitize_display_name, sniff_pdf
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine, PaperStatus
from marcus.core.models import Owner, Paper
from marcus.core.pipeline import cancel_paper, start_paper
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
    if engine == Engine.FAKE and not settings.enable_fake_engines:
        raise HTTPException(status_code=422, detail="Engine not available")
    await enforce_active_limits(db, owner, client_ip(request))

    data = await read_limited(file, settings.max_upload_bytes)
    sniff_pdf(data)
    name = sanitize_display_name(file.filename)

    paper = await db.run_sync(lambda s: start_paper(s, owner, data, name, engine, ocsr))
    await db.commit()
    return {"paper_id": str(paper.id), "status": PaperStatus.CHECKING.value}


@router.get("/papers", response_model=PaperList)
async def list_papers(
    owner: Owner = Depends(current_owner), db: AsyncSession = Depends(get_db)
) -> PaperList:
    papers = (
        await db.execute(
            select(Paper)
            .where(Paper.owner_id == owner.id, *paper_visible())
            .order_by(Paper.created_at.desc(), Paper.id)
        )
    ).scalars()
    return PaperList(papers=[PaperSummary.model_validate(p) for p in papers])


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> PaperDetail:
    paper = await get_owned_paper(db, owner, paper_id)
    counts = await steps_by_status(db, paper.id)
    return PaperDetail(
        **PaperSummary.model_validate(paper).model_dump(),
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
        await db.run_sync(lambda s: cancel_paper(s, paper.id))
    except ValueError:
        await db.rollback()
        raise not_found() from None  # removed meanwhile
    await db.commit()


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


@router.get("/papers/{paper_id}/text")
async def paper_text(
    paper_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    paper = await get_owned_paper(db, owner, paper_id)
    path = storage.paper_dir(paper.id) / "text.json"
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="application/json")


@router.get("/papers/{paper_id}/export")
async def export_paper(
    paper_id: uuid.UUID,
    format: export.ExportFormat = Query("json"),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> Response:
    paper = await get_owned_paper(db, owner, paper_id)
    segments, curations, predictions = await load_segments(db, paper.id)
    chosen = export.choose(paper, segments, curations, predictions)
    content = await run_in_threadpool(export.render, format, paper, chosen)  # RDKit is sync
    return Response(
        content=content,
        media_type=export.MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="marcus-{paper.id}.{format}"'},
    )
