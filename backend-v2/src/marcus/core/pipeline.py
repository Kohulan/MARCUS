"""Pipeline state transitions (the planner).

Every function takes a sync SQLAlchemy Session and never commits: the caller owns the
transaction. Steps are created only when their inputs exist: completing a step creates its
successors. Functions that change a paper lock its row first (SELECT ... FOR UPDATE), so two
workers finishing the last two steps of one paper cannot both miss the `done` transition.
"""

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from marcus.core import storage
from marcus.core.enums import Engine, ErrorClass, PaperStatus, StepKind, StepStatus
from marcus.core.models import (
    Curation,
    ImageJob,
    Owner,
    Paper,
    Prediction,
    Segment,
    Step,
)
from marcus.core.queues import queue_for
from marcus.core.settings import get_settings

DOCLING_SEQ = 100_000
DOI_SEQ = 100_001
MAX_ATTEMPTS = 2  # a step is retried once; the second failure is final

ACTIVE = (StepStatus.PENDING.value, StepStatus.QUEUED.value, StepStatus.RUNNING.value)
_FINISHED = (StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.CANCELLED.value)


def start_paper(
    session: Session,
    owner: Owner,
    data: bytes,
    display_name: str,
    engine: Engine,
    ocsr_mode: str,
) -> Paper:
    """Store the PDF and create the paper plus its check_pdf step. Caller commits."""
    paper = Paper(
        owner_id=owner.id,
        display_name=display_name,
        pdf_sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        engine=Engine(engine).value,
        ocsr_mode=ocsr_mode,
        status=PaperStatus.CHECKING.value,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
    )
    session.add(paper)
    session.flush()  # assigns paper.id

    path = storage.pdf_path(paper.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)

    session.add(
        Step(
            paper_id=paper.id,
            kind=StepKind.CHECK_PDF.value,
            queue=queue_for(StepKind.CHECK_PDF, None),
            seq=0,
            status=StepStatus.PENDING.value,
        )
    )
    session.flush()
    return paper


# --- helpers -------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _new_step(paper: Paper, kind: StepKind, seq: int, **kw) -> Step:
    engine = kw.get("engine")
    return Step(
        paper_id=paper.id,
        kind=kind.value,
        queue=queue_for(kind, Engine(engine) if engine else None),
        seq=seq,
        status=StepStatus.PENDING.value,
        **kw,
    )


def _ocsr_seq(page: int, idx: int) -> int:
    return page * 1000 + idx


def _lock_paper(session: Session, paper_id: uuid.UUID) -> Paper | None:
    return session.execute(
        select(Paper)
        .where(Paper.id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _lock_image_job(session: Session, job_id: uuid.UUID) -> ImageJob | None:
    return session.execute(
        select(ImageJob)
        .where(ImageJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _lock_step(session: Session, step_id: uuid.UUID) -> Step | None:
    return session.execute(
        select(Step)
        .where(Step.id == step_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _load_for_change(session: Session, step_id: uuid.UUID):
    """Lock the step's parent (paper or image job), then the step.

    Returns (step, paper, job), or None when the step must not change: it is unknown,
    already finished (done/failed/cancelled), or its parent is deleted.
    Lock order is always parent row, then step row.
    """
    parent = session.execute(
        select(Step.paper_id, Step.image_job_id).where(Step.id == step_id)
    ).one_or_none()
    if parent is None:
        return None
    paper = job = None
    if parent.paper_id is not None:
        paper = _lock_paper(session, parent.paper_id)
        if paper is None or paper.status == PaperStatus.DELETED.value:
            return None
    else:
        job = _lock_image_job(session, parent.image_job_id)
        if job is None or job.status == "deleted":
            return None
    step = _lock_step(session, step_id)
    if step is None or step.status in _FINISHED:
        return None
    return step, paper, job


def _finish_check(session: Session, paper: Paper) -> None:
    """If no step of the paper is still active, close the paper as done or failed."""
    if paper.status not in (PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value):
        return
    session.flush()
    active = session.execute(
        select(func.count())
        .select_from(Step)
        .where(Step.paper_id == paper.id, Step.status.in_(ACTIVE))
    ).scalar_one()
    if active:
        return
    rows = session.execute(
        select(Step.kind, Step.status, Step.error).where(
            Step.paper_id == paper.id,
            Step.kind.in_([StepKind.CHECK_PDF.value, StepKind.RENDER_PAGE.value]),
        )
    ).all()
    check = [r for r in rows if r.kind == StepKind.CHECK_PDF.value]
    renders = [r for r in rows if r.kind == StepKind.RENDER_PAGE.value]
    if any(r.status == StepStatus.FAILED.value for r in check):
        paper.status = PaperStatus.FAILED.value
        paper.error = next(r.error for r in check if r.status == StepStatus.FAILED.value)
    elif renders and all(r.status == StepStatus.FAILED.value for r in renders):
        paper.status = PaperStatus.FAILED.value
        paper.error = "all pages failed to render"
    else:
        paper.status = PaperStatus.DONE.value


# --- successors per step kind --------------------------------------------------------------


def _after_check_pdf(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    pages = result["pages"]
    if isinstance(pages, bool) or not isinstance(pages, int):
        raise ValueError("check_pdf result 'pages' must be an int")
    if not 1 <= pages <= get_settings().max_pages:
        raise ValueError(f"check_pdf result 'pages' out of range: {pages}")
    paper.pages = pages
    if paper.status == PaperStatus.CHECKING.value:
        paper.status = PaperStatus.PROCESSING.value
    new = [_new_step(paper, StepKind.RENDER_PAGE, p, page=p) for p in range(1, pages + 1)]
    new.append(_new_step(paper, StepKind.DOCLING, DOCLING_SEQ))
    new.append(_new_step(paper, StepKind.DOI, DOI_SEQ))
    return new


def _after_render_page(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    return [_new_step(paper, StepKind.SEGMENT_PAGE, step.page, page=step.page)]


def _after_segment_page(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    segments = []
    for item in result["segments"]:
        bbox = [int(v) for v in item["bbox"]]
        if len(bbox) != 4:
            raise ValueError("segment bbox must have 4 values")
        segments.append(
            Segment(
                paper_id=paper.id,
                page=step.page,
                idx=int(item["idx"]),
                bbox=bbox,
                image_sha256=item["image_sha256"],
            )
        )
    session.add_all(segments)
    session.flush()  # assigns segment ids
    session.add_all(Curation(segment_id=seg.id, status="unchecked") for seg in segments)
    if paper.ocsr_mode != "auto":
        return []
    return [
        _new_step(
            paper,
            StepKind.OCSR,
            _ocsr_seq(seg.page, seg.idx),
            engine=paper.engine,
            page=seg.page,
            segment_id=seg.id,
        )
        for seg in segments
    ]


def _prediction(step: Step, result: dict) -> Prediction:
    return Prediction(
        segment_id=step.segment_id,
        image_job_id=step.image_job_id,
        engine=step.engine,
        engine_version=result["engine_version"],
        smiles=result["smiles"],
        molfile=result.get("molfile"),
        valid=bool(result["valid"]),
        ms=int(result["ms"]),
    )


def _after_ocsr(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    session.add(_prediction(step, result))
    return []


def _after_doi(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    paper.doi = result.get("doi")
    return []


def _no_successors(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    # docling: the text file already sits in the paper dir; nothing to store.
    return []


_AFTER = {
    StepKind.CHECK_PDF.value: _after_check_pdf,
    StepKind.RENDER_PAGE.value: _after_render_page,
    StepKind.SEGMENT_PAGE.value: _after_segment_page,
    StepKind.OCSR.value: _after_ocsr,
    StepKind.DOCLING.value: _no_successors,
    StepKind.DOI.value: _after_doi,
}


# --- public API ----------------------------------------------------------------------------


def complete_step(session: Session, step_id: uuid.UUID, result: dict) -> list[Step]:
    """Mark a step done, store its result rows and return the new successor steps.

    A step that is already finished or cancelled, or whose paper/image job is deleted, is a
    no-op returning [] (a redelivered or late Celery result). Caller commits.
    """
    loaded = _load_for_change(session, step_id)
    if loaded is None:
        return []
    step, paper, job = loaded
    step.status = StepStatus.DONE.value
    step.finished_at = _now()

    if job is not None:
        if step.kind != StepKind.OCSR.value:
            raise ValueError(f"image job step has unexpected kind {step.kind!r}")
        session.add(_prediction(step, result))
        job.status = "done"
        job.error = None
        session.flush()
        return []

    new = _AFTER.get(step.kind, _no_successors)(session, paper, step, result)
    session.add_all(new)
    _finish_check(session, paper)
    session.flush()
    return new


def fail_step(
    session: Session,
    step_id: uuid.UUID,
    error_class: ErrorClass,
    error: str,
    retryable: bool,
) -> None:
    """Record a step failure: back to `pending` for one retry, else `failed`. Caller commits.

    `attempts` is incremented by the runtime when it starts a step, not here.
    """
    loaded = _load_for_change(session, step_id)
    if loaded is None:
        return
    step, paper, job = loaded
    step.error_class = ErrorClass(error_class).value
    step.error = error
    if retryable and step.attempts < MAX_ATTEMPTS:
        step.status = StepStatus.PENDING.value
        step.queued_at = None
        step.started_at = None
        step.finished_at = None
    else:
        step.status = StepStatus.FAILED.value
        step.finished_at = _now()
        if job is not None:
            job.status = "failed"
            job.error = error
    if paper is not None:
        _finish_check(session, paper)
    session.flush()


def cancel_paper(session: Session, paper_id: uuid.UUID) -> None:
    """Cancel all active steps, mark the paper deleted and remove its files. Caller commits.

    A running step's late result is dropped by complete_step / fail_step.
    """
    paper = _lock_paper(session, paper_id)
    if paper is None:
        raise ValueError("paper not found")
    session.execute(
        update(Step)
        .where(Step.paper_id == paper_id, Step.status.in_(ACTIVE))
        .values(status=StepStatus.CANCELLED.value, finished_at=_now())
        .execution_options(synchronize_session="fetch")
    )
    paper.status = PaperStatus.DELETED.value
    session.flush()
    try:
        shutil.rmtree(storage.paper_dir(paper_id))
    except FileNotFoundError:
        pass


def request_ocsr(session: Session, segment_id: uuid.UUID, engine: Engine) -> Step:
    """Create a pending `ocsr` step for one segment with the given engine. Caller commits.

    Raises ValueError for an unknown segment, a deleted paper, or a disabled engine.
    """
    engine = Engine(engine)
    if engine == Engine.FAKE and not get_settings().enable_fake_engines:
        raise ValueError("engine 'fake' is disabled")
    segment = session.get(Segment, segment_id)
    if segment is None:
        raise ValueError("segment not found")
    paper = _lock_paper(session, segment.paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper is deleted")
    step = _new_step(
        paper,
        StepKind.OCSR,
        _ocsr_seq(segment.page, segment.idx),
        engine=engine.value,
        page=segment.page,
        segment_id=segment.id,
    )
    session.add(step)
    if paper.status == PaperStatus.DONE.value:
        paper.status = PaperStatus.PROCESSING.value
    session.flush()
    return step
