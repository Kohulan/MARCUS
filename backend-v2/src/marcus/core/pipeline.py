"""Pipeline state transitions (the planner).

Every function takes a sync SQLAlchemy Session and never commits: the caller owns the
transaction. Steps are created only when their inputs exist: completing a step creates its
successors. Functions that change a paper lock its row first (SELECT ... FOR UPDATE), so two
workers finishing the last two steps of one paper cannot both miss the `done` transition.

Segmentation cache (spec §7): when the last page of a paper is segmented and every page was
segmented successfully by one segmenter version, the planner stores the paper's segments under
(pdf_sha256, seg_cache_key(version)). A later paper with the same PDF bytes, while the
configured `seg_version` matches, gets each page's segments from that row when the page is
rendered (no segment_page step): new Segment, Curation and ocsr rows under the new paper, and
crop files copied by content hash from any live paper that has them. Of that other paper
only its id is used, to find the file; its rows (ids, curation, predictions, names) are never
copied. A page whose crops cannot all be found falls back to a normal segment_page step.
"""

import hashlib
import logging
import os
import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from marcus.core import storage
from marcus.core.enums import Engine, ErrorClass, PaperStatus, StepKind, StepStatus
from marcus.core.models import (
    Curation,
    ImageJob,
    Owner,
    Paper,
    Prediction,
    SegCache,
    Segment,
    Step,
)
from marcus.core.queues import queue_for
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

DOCLING_SEQ = 100_000
DOI_SEQ = 100_001
MAX_ATTEMPTS = 2  # a step is retried once; the second failure is final

ACTIVE = (StepStatus.PENDING.value, StepStatus.QUEUED.value, StepStatus.RUNNING.value)
_FINISHED = (StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.CANCELLED.value)

MAX_SEGMENTS_PER_PAGE = 1000  # ocsr seq = page * 1000 + idx, so idx must stay below 1000
_INT32_MAX = 2**31 - 1
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
MAX_VERSION_CHARS = 200
RENDER_DPI = 300  # fixed page render (marcus.workers.pdfsafe_child); part of the cache key
CROP_SOURCES_TRIED = 20  # live papers tried per crop on a cache hit


def seg_cache_key(seg_version: str) -> str:
    """seg_cache.seg_version: the segmenter version plus the fixed render settings."""
    return f"{seg_version}|dpi{RENDER_DPI}"


class BadResult(ValueError):
    """A worker result does not have the shape its step kind requires.

    Raised by complete_step before any state changes. The caller must roll back and may then
    record the failure with fail_step in a fresh transaction.
    """


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


def start_image_job(
    session: Session, owner: Owner, png: bytes, display_name: str, engine: Engine
) -> ImageJob:
    """Store the normalised PNG and create the image job plus its ocsr step. Caller commits."""
    engine = Engine(engine)
    job = ImageJob(
        owner_id=owner.id,
        display_name=display_name,
        image_sha256=hashlib.sha256(png).hexdigest(),
        engine=engine.value,
        status="queued",
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
    )
    session.add(job)
    session.flush()  # assigns job.id

    path = storage.image_job_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(png)
    os.replace(tmp, path)

    session.add(
        Step(
            image_job_id=job.id,
            kind=StepKind.OCSR.value,
            queue=queue_for(StepKind.OCSR, engine),
            engine=engine.value,
            seq=0,
            status=StepStatus.PENDING.value,
        )
    )
    session.flush()
    return job


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
    """If no step of the paper is still active, close the paper as done or failed.

    Failed (spec §8): check_pdf failed, or every page failed, a page being failed when its
    render_page or its segment_page step failed for good. Otherwise done, failed steps and all.
    """
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
        select(Step.kind, Step.status, Step.error, Step.page).where(
            Step.paper_id == paper.id,
            Step.kind.in_(
                [
                    StepKind.CHECK_PDF.value,
                    StepKind.RENDER_PAGE.value,
                    StepKind.SEGMENT_PAGE.value,
                ]
            ),
        )
    ).all()
    failed = StepStatus.FAILED.value
    check = [r for r in rows if r.kind == StepKind.CHECK_PDF.value]
    renders = [r for r in rows if r.kind == StepKind.RENDER_PAGE.value]
    # A page fails when its render failed or its segmentation failed (a page served from the
    # segmentation cache has no segment_page step and counts as segmented).
    segmented = {
        r.page for r in rows if r.kind == StepKind.SEGMENT_PAGE.value and r.status != failed
    }
    seg_failed = {
        r.page for r in rows if r.kind == StepKind.SEGMENT_PAGE.value and r.status == failed
    }
    page_failed = [
        r.status == failed or (r.page in seg_failed and r.page not in segmented) for r in renders
    ]
    if any(r.status == failed for r in check):
        paper.status = PaperStatus.FAILED.value
        paper.error = next(r.error for r in check if r.status == failed)
    elif renders and all(r.status == failed for r in renders):
        paper.status = PaperStatus.FAILED.value
        paper.error = "all pages failed to render"
    elif renders and all(page_failed):
        paper.status = PaperStatus.FAILED.value
        paper.error = "all pages failed (render or segmentation)"
    else:
        paper.status = PaperStatus.DONE.value


# --- result validation (runs before any state change) -------------------------------------


def _is_int(value: object, lo: int = 0, hi: int = _INT32_MAX) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi


def _is_text(value: object) -> bool:
    return isinstance(value, str) and "\x00" not in value


def _check_pdf_result(result: dict) -> None:
    pages = result.get("pages")
    if not _is_int(pages, 1, get_settings().max_pages):
        raise BadResult(f"check_pdf: 'pages' must be an int in 1..{get_settings().max_pages}")


def _check_segments(segments: object) -> None:
    """A list of {idx, bbox, image_sha256} with unique idx (one page's segments)."""
    if not isinstance(segments, list):
        raise BadResult("segment_page: 'segments' must be a list")
    seen: set[int] = set()
    for item in segments:
        if not isinstance(item, dict):
            raise BadResult("segment_page: each segment must be an object")
        idx, bbox, sha = item.get("idx"), item.get("bbox"), item.get("image_sha256")
        if not _is_int(idx, 0, MAX_SEGMENTS_PER_PAGE - 1):
            raise BadResult(f"segment_page: 'idx' must be an int in 0..{MAX_SEGMENTS_PER_PAGE - 1}")
        if idx in seen:
            raise BadResult(f"segment_page: duplicate idx {idx}")
        seen.add(idx)
        if not isinstance(bbox, list | tuple) or len(bbox) != 4 or not all(map(_is_int, bbox)):
            raise BadResult("segment_page: 'bbox' must be 4 non-negative ints")
        if not isinstance(sha, str) or not _SHA256_HEX.fullmatch(sha):
            raise BadResult("segment_page: 'image_sha256' must be 64 lowercase hex characters")


def _check_segment_page_result(result: dict) -> None:
    _check_segments(result.get("segments"))
    version = result.get("seg_version")
    if not _is_text(version) or not version or len(version) > MAX_VERSION_CHARS:
        raise BadResult(
            f"segment_page: 'seg_version' must be a non-empty string of at most "
            f"{MAX_VERSION_CHARS} characters"
        )


def _check_ocsr_result(result: dict) -> None:
    if not _is_text(result.get("smiles")):
        raise BadResult("ocsr: 'smiles' must be a string")
    molfile = result.get("molfile")
    if molfile is not None and not _is_text(molfile):
        raise BadResult("ocsr: 'molfile' must be a string or null")
    if not isinstance(result.get("valid"), bool):
        raise BadResult("ocsr: 'valid' must be a bool")
    if not _is_int(result.get("ms")):
        raise BadResult("ocsr: 'ms' must be a non-negative int")
    version = result.get("engine_version")
    if not _is_text(version) or not version:
        raise BadResult("ocsr: 'engine_version' must be a non-empty string")
    if "cached" in result and not isinstance(result["cached"], bool):
        raise BadResult("ocsr: 'cached' must be a bool")


def _check_doi_result(result: dict) -> None:
    if "doi" not in result:
        raise BadResult("doi: 'doi' is missing")
    doi = result["doi"]
    if doi is not None and not _is_text(doi):
        raise BadResult("doi: 'doi' must be a string or null")


def _check_nothing(result: dict) -> None:
    pass


_CHECK = {
    StepKind.CHECK_PDF.value: _check_pdf_result,
    StepKind.SEGMENT_PAGE.value: _check_segment_page_result,
    StepKind.OCSR.value: _check_ocsr_result,
    StepKind.DOI.value: _check_doi_result,
}


def _validate(kind: str, result: object) -> None:
    if not isinstance(result, dict):
        raise BadResult(f"{kind}: result must be an object")
    _CHECK.get(kind, _check_nothing)(result)


# --- successors per step kind --------------------------------------------------------------


def _after_check_pdf(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    pages = result["pages"]
    paper.pages = pages
    if paper.status == PaperStatus.CHECKING.value:
        paper.status = PaperStatus.PROCESSING.value
    new = [_new_step(paper, StepKind.RENDER_PAGE, p, page=p) for p in range(pages)]  # 0-based
    new.append(_new_step(paper, StepKind.DOCLING, DOCLING_SEQ))
    new.append(_new_step(paper, StepKind.DOI, DOI_SEQ))
    return new


def _after_render_page(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    cached = _cached_page(session, paper, step.page)
    if cached is not None:
        return _add_segments(session, paper, step.page, cached)
    return [_new_step(paper, StepKind.SEGMENT_PAGE, step.page, page=step.page)]


def _add_segments(session: Session, paper: Paper, page: int, items: list[dict]) -> list[Step]:
    """New Segment + Curation rows for one page; returns its ocsr steps (ocsr_mode auto)."""
    segments = [
        Segment(
            paper_id=paper.id,
            page=page,
            idx=item["idx"],
            bbox=list(item["bbox"]),
            image_sha256=item["image_sha256"],
        )
        for item in items
    ]
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


def _after_segment_page(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    step.model_version = result["seg_version"]
    new = _add_segments(session, paper, step.page, result["segments"])
    _store_seg_cache(session, paper, result["seg_version"])
    return new


# --- segmentation cache ----------------------------------------------------------------------


def _store_seg_cache(session: Session, paper: Paper, seg_version: str) -> None:
    """Cache the paper's segmentation once every page has a done segment_page step from this
    one segmenter version. Any page without one (failed render or segmentation, still running,
    or served from the cache) means no row: a partial result is never cached."""
    if not paper.pages:
        return
    session.flush()
    rows = session.execute(
        select(Step.page, Step.model_version).where(
            Step.paper_id == paper.id,
            Step.kind == StepKind.SEGMENT_PAGE.value,
            Step.status == StepStatus.DONE.value,
        )
    ).all()
    versions = {r.page: r.model_version for r in rows}
    if set(versions) != set(range(paper.pages)) or set(versions.values()) != {seg_version}:
        return
    segments = session.execute(
        select(Segment.page, Segment.idx, Segment.bbox, Segment.image_sha256)
        .where(Segment.paper_id == paper.id)
        .order_by(Segment.page, Segment.idx)
    ).all()
    payload = {
        "pages": paper.pages,
        "segments": [
            {"page": g.page, "idx": g.idx, "bbox": list(g.bbox), "image_sha256": g.image_sha256}
            for g in segments
        ],
    }
    session.execute(
        pg_insert(SegCache)
        .values(
            pdf_sha256=paper.pdf_sha256, seg_version=seg_cache_key(seg_version), payload=payload
        )
        .on_conflict_do_nothing(index_elements=["pdf_sha256", "seg_version"])
    )


def _cached_page(session: Session, paper: Paper, page: int) -> list[dict] | None:
    """The page's cached segments with every crop present in this paper's crop dir, or None
    (no usable cache row for the configured segmenter version, or a crop not found)."""
    version = get_settings().seg_version
    if not version:
        return None
    payload = session.execute(
        select(SegCache.payload).where(
            SegCache.pdf_sha256 == paper.pdf_sha256,
            SegCache.seg_version == seg_cache_key(version),
        )
    ).scalar_one_or_none()
    if payload is None:
        return None
    try:
        items = _page_items(payload, paper.pages, page)
    except BadResult as exc:
        log.warning("paper %s: seg_cache row ignored: %s", paper.id, exc)
        return None
    for item in items:
        if not _copy_crop(session, paper.id, item["image_sha256"]):
            log.info("paper %s page %d: cached crop not found; segmenting", paper.id, page)
            return None
    return items


def _page_items(payload: object, pages: int | None, page: int) -> list[dict]:
    """Validate a whole seg_cache payload (it is data: checked like worker results, every page)
    and return one page's segments as {idx, bbox, image_sha256}."""
    if not isinstance(payload, dict) or not _is_int(pages, 1) or payload.get("pages") != pages:
        raise BadResult("page count differs")
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise BadResult("'segments' must be a list")
    by_page: dict[int, list[dict]] = {}
    for item in segments:
        if not isinstance(item, dict) or not _is_int(item.get("page"), 0, pages - 1):
            raise BadResult("each segment needs a valid 'page'")
        by_page.setdefault(item["page"], []).append(
            {
                "idx": item.get("idx"),
                "bbox": item.get("bbox"),
                "image_sha256": item.get("image_sha256"),
            }
        )
    for items in by_page.values():
        _check_segments(items)
    return by_page.get(page, [])


def _copy_crop(session: Session, paper_id: uuid.UUID, sha: str) -> bool:
    """Put the crop with content hash `sha` into this paper's crop dir.

    Sources are other live (not deleted) papers with a segment of that hash; only the file's
    bytes are used, and only if they hash to `sha`. True if the crop is in place.
    """
    dest = storage.segment_crop_path(paper_id, sha)
    if dest.is_file():
        return True
    sources = session.execute(
        select(Segment.paper_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .where(
            Segment.image_sha256 == sha,
            Segment.paper_id != paper_id,
            Paper.status != PaperStatus.DELETED.value,
        )
        .distinct()
        .limit(CROP_SOURCES_TRIED)
    ).scalars()
    for source_paper in sources:
        try:
            data = storage.segment_crop_path(source_paper, sha).read_bytes()
        except OSError:
            continue  # gone (deleted or purged meanwhile)
        if hashlib.sha256(data).hexdigest() != sha:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{dest.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return True
    return False


def _prediction(step: Step, result: dict) -> Prediction:
    return Prediction(
        segment_id=step.segment_id,
        image_job_id=step.image_job_id,
        engine=step.engine,
        engine_version=result["engine_version"],
        smiles=result["smiles"],
        molfile=result.get("molfile"),
        valid=result["valid"],
        ms=result["ms"],
        cached=bool(result.get("cached", False)),
    )


def _after_ocsr(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    session.add(_prediction(step, result))
    return []


def _after_doi(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    paper.doi = result["doi"]
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

    The result is checked in full before anything changes; a malformed result raises
    BadResult. On any exception the caller must roll back the session before reusing it.
    """
    loaded = _load_for_change(session, step_id)
    if loaded is None:
        return []
    step, paper, job = loaded
    if job is not None and step.kind != StepKind.OCSR.value:
        raise BadResult(f"image job step has unexpected kind {step.kind!r}")
    _validate(step.kind, result)

    step.status = StepStatus.DONE.value
    step.finished_at = _now()

    if job is not None:
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

    A running step's late result is dropped by complete_step / fail_step. A file that cannot
    be removed (any OSError) is logged and does not abort the transaction: the paper is
    deleted either way, and the retention purge's orphan sweep removes the leftovers later.
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
    except OSError as exc:
        log.warning(
            "paper %s: files not removed (%s: %s); the retention sweep retries",
            paper_id, type(exc).__name__, exc,
        )


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
