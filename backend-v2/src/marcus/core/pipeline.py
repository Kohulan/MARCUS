"""Pipeline state transitions (the planner).

Every function takes a sync SQLAlchemy Session and never commits: the caller owns the
transaction. Steps are created only when their inputs exist: completing a step creates its
successors. Functions that change a paper lock its row first (SELECT ... FOR UPDATE), so two
workers finishing the last two steps of one paper cannot both miss the `done` transition.

Annotation (owner decisions 2026-11-20, 2026-11-22): request_annotation adds one `annotate`
step (q.llm) to a paper whose docling step is done, asked for by the dispatcher once the text
is read (marcus.core.auto) or by the user (a re-run); its result (the MARCUS model's values and
their positions in the text, marcus.core.annotation) is stored in the paper's one `annotations`
row. A re-run replaces the model's values and keeps the curator's. An annotate step is outside
the paper's progress, like an rgroups step: it never reopens a paper, never keeps one busy and
never decides whether it is done or failed.

R-group rows (Markush Phase 2): per prediction with R-group labels, asked for by the dispatcher
(marcus.core.auto) or by the user.
request_rgroups adds one `rgroups` step (q.rgroup, the step's segment set, no page) and writes the
prediction's `rgroup_extractions` row (status `queued`); the step's end sets it `done` with the
rows or `failed` with the error class. An rgroups step is outside the paper's progress: it never
reopens a paper, never keeps one busy (_finish_check, the read counts in marcus.api.read) and
never decides whether it is done or failed.

Segmentation cache (spec §7): when the last page of a paper is segmented and every page was
segmented successfully by one segmenter version, the planner stores the paper's segments under
(owner, pdf_sha256, seg_cache_key(version)). A later paper of the same owner with the same PDF
bytes, while the configured `seg_version` matches, gets each page's segments from that row
when the page is rendered (no segment_page step): new Segment, Curation and ocsr rows under the
new paper, and crop files copied by content hash from the owner's live papers that have them.
Of that other paper only its id is used, to find the file; its rows (ids, curation,
predictions, names) are never copied. A page whose crops cannot all be found falls back to a
normal segment_page step. The cache is per owner (security F6): another owner's paper never
skips a step because of it. Deleting the paper that made a row drops the row (cancel_paper).
"""

import hashlib
import logging
import os
import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from marcus.core import annotation, rgroup_extraction, rgroup_labels, storage
from marcus.core.enums import (
    FINISHED_STEPS,
    Engine,
    ErrorClass,
    ImageJobStatus,
    PaperStatus,
    StepKind,
    StepStatus,
)
from marcus.core.models import (
    Annotation,
    Curation,
    DrawingFlag,
    ImageJob,
    Owner,
    Paper,
    Prediction,
    RgroupExtraction,
    SegCache,
    Segment,
    Step,
)
from marcus.core.queues import queue_for
from marcus.core.settings import fake_enabled, get_settings

log = logging.getLogger(__name__)

DOCLING_SEQ = 100_000
DOI_SEQ = 100_001
ANNOTATE_SEQ = 100_002
RGROUPS_SEQ = 100_003
MAX_ATTEMPTS = 2  # a step is retried once; the second failure is final

ACTIVE = (StepStatus.PENDING.value, StepStatus.QUEUED.value, StepStatus.RUNNING.value)

MAX_SEGMENTS_PER_PAGE = 1000  # ocsr seq = page * 1000 + idx, so idx must stay below 1000
_INT32_MAX = 2**31 - 1
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
# One page's render_page and segment_page steps are read newest first in this order (segment_page
# follows render_page when created_at ties). retry_page and the failed_pages count share it, so
# "the newest step across both kinds" means the same thing in both.
PAGE_KINDS = (StepKind.RENDER_PAGE.value, StepKind.SEGMENT_PAGE.value)
MANUAL_PAGE_RETRIES = 2  # extra render_page steps one page may get through retry_page
MAX_VERSION_CHARS = 200
RENDER_DPI = 300  # fixed page render (marcus.workers.pdfsafe_child); part of the cache key
CROP_SOURCES_TRIED = 20  # live papers tried per crop on a cache hit


CROP_FORMAT = "rgb"  # stored crops are true-colour RGB PNGs (D4 fix round 2); part of the key


def seg_cache_key(seg_version: str) -> str:
    """seg_cache.seg_version: the segmenter version plus the fixed render settings and the crop
    format, so cached segmentations from an older crop format are never reused (and retention
    purges them)."""
    return f"{seg_version}|dpi{RENDER_DPI}|{CROP_FORMAT}"


class BadResult(ValueError):
    """A worker result does not have the shape its step kind requires.

    Raised by complete_step before any state changes. The caller must roll back and may then
    record the failure with fail_step in a fresh transaction.
    """


class RetryNotAllowed(Exception):
    """retry_page refused: the page has not failed, is still running, or has no retries left."""

    def __init__(self, reason: Literal["not_failed", "busy", "limit"]):
        super().__init__(reason)
        self.reason = reason


class RgroupsNotAllowed(Exception):
    """request_rgroups refused: the prediction has no R-group labels."""

    def __init__(self, reason: Literal["no_rgroups"]):
        super().__init__(reason)
        self.reason = reason


class AnnotateNotAllowed(Exception):
    """request_annotation refused: the paper has no text (its docling step is not done)."""

    def __init__(self, reason: Literal["no_text"]):
        super().__init__(reason)
        self.reason = reason


def page_step_order() -> tuple:
    """ORDER BY terms (newest first) over one page's render_page/segment_page steps."""
    return Step.created_at.desc(), Step.kind.desc(), Step.seq.desc()


def start_paper(
    session: Session,
    owner: Owner,
    data: bytes,
    display_name: str,
    engine: Engine,
    ocsr_mode: str,
    started_ip: str | None = None,
) -> Paper:
    """Create the paper plus its check_pdf step, then store the PDF. Caller commits.

    The API runs the two halves itself (new_paper, then store_pdf in a thread) so the hash and
    the file write do not block its event loop."""
    paper = new_paper(
        session, owner, hashlib.sha256(data).hexdigest(), len(data), display_name, engine,
        ocsr_mode, started_ip,
    )  # fmt: skip
    store_pdf(paper.id, data)
    return paper


def new_paper(
    session: Session,
    owner: Owner,
    pdf_sha256: str,
    size: int,
    display_name: str,
    engine: Engine,
    ocsr_mode: str,
    started_ip: str | None = None,
) -> Paper:
    """The paper row and its check_pdf step (flushed: the paper has its id). Its PDF must be
    stored (store_pdf) before the commit. `started_ip`: the address bucket that started it
    (Paper.started_ip)."""
    paper = Paper(
        owner_id=owner.id,
        display_name=display_name,
        pdf_sha256=pdf_sha256,
        bytes=size,
        engine=Engine(engine).value,
        ocsr_mode=ocsr_mode,
        status=PaperStatus.CHECKING.value,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
    )
    keep_address(paper, started_ip)
    session.add(paper)
    session.flush()  # assigns paper.id
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


def store_pdf(paper_id: uuid.UUID, data: bytes) -> None:
    """Write a new paper's PDF (owner-only mode; refuses to overwrite an existing file)."""
    path = storage.pdf_path(paper_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def start_image_job(
    session: Session, owner: Owner, png: bytes, display_name: str, engine: Engine
) -> ImageJob:
    """Create the image job plus its ocsr step, then store the normalised PNG. Caller commits.

    The API runs the two halves itself (new_image_job, then store_image in a thread)."""
    job = new_image_job(session, owner, hashlib.sha256(png).hexdigest(), display_name, engine)
    store_image(job.id, png)
    return job


def store_image(job_id: uuid.UUID, png: bytes) -> None:
    """Write a new image job's PNG (owner-only mode). The temp name `<id>.png.tmp` is the one
    retention sweeps after a crash (one writer per new job)."""
    storage.write_atomic(storage.image_job_path(job_id), png, 0o600, unique=False)


def new_image_job(
    session: Session,
    owner: Owner,
    image_sha256: str,
    display_name: str,
    engine: Engine,
    started_ip: str | None = None,
) -> ImageJob:
    """The image job row and its ocsr step (flushed: the job has its id). Its PNG must be
    stored (store_image) before the commit. `started_ip`: as new_paper's."""
    engine = Engine(engine)
    job = ImageJob(
        owner_id=owner.id,
        display_name=display_name,
        image_sha256=image_sha256,
        engine=engine.value,
        status=ImageJobStatus.QUEUED.value,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
    )
    keep_address(job, started_ip)
    session.add(job)
    session.flush()  # assigns job.id
    session.add(_new_image_step(job, engine, seq=0))
    session.flush()
    return job


# --- helpers -------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def keep_address(work: Paper | ImageJob, started_ip: str | None) -> None:
    """Set (or clear, with None) the address bucket kept on active work, and when it was set:
    the retention backstop ages the address by that time, not by the work's creation."""
    work.started_ip = started_ip
    work.started_ip_at = _now() if started_ip is not None else None


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


def _new_image_step(job: ImageJob, engine: Engine, seq: int) -> Step:
    """A pending `ocsr` step of an image job (the only kind an image job has)."""
    return Step(
        image_job_id=job.id,
        kind=StepKind.OCSR.value,
        queue=queue_for(StepKind.OCSR, engine),
        engine=engine.value,
        seq=seq,
        status=StepStatus.PENDING.value,
    )


def _ocsr_engine(engine: Engine) -> Engine:
    """`engine` as an Engine; ValueError for the fake engine where it is disabled."""
    engine = Engine(engine)
    if engine == Engine.FAKE and not fake_enabled():
        raise ValueError("engine 'fake' is disabled")
    return engine


def _ocsr_seq(page: int, idx: int) -> int:
    return page * 1000 + idx


def _lock(session: Session, model, row_id: uuid.UUID):
    """SELECT ... FOR UPDATE of one row (fresh attributes), or None."""
    return session.execute(
        select(model)
        .where(model.id == row_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def lock_parent(
    session: Session, paper_id: uuid.UUID | None, image_job_id: uuid.UUID | None
) -> Paper | ImageJob | None:
    """Lock a step's parent row: its paper, else its image job. None when the row is gone.

    The first half of the lock order every writer of step state keeps: parent row, then step
    row (the planner here, the runtime's attempt fence, the watchdog)."""
    if paper_id is not None:
        return _lock(session, Paper, paper_id)
    return _lock(session, ImageJob, image_job_id)


def parent_gone(parent: Paper | ImageJob | None) -> bool:
    """The parent row is missing or deleted: its steps must not change."""
    return parent is None or parent.status in (
        PaperStatus.DELETED.value,
        ImageJobStatus.DELETED.value,
    )


def _load_for_change(session: Session, step_id: uuid.UUID):
    """Lock the step's parent (paper or image job), then the step.

    Returns (step, paper, job), or None when the step must not change: it is unknown,
    already finished (done/failed/cancelled), or its parent is deleted.
    Lock order is always parent row, then step row.
    """
    ids = session.execute(
        select(Step.paper_id, Step.image_job_id).where(Step.id == step_id)
    ).one_or_none()
    if ids is None:
        return None
    parent = lock_parent(session, ids.paper_id, ids.image_job_id)
    if parent_gone(parent):
        return None
    paper, job = (parent, None) if ids.paper_id is not None else (None, parent)
    step = _lock(session, Step, step_id)
    if step is None or step.status in FINISHED_STEPS:
        return None
    return step, paper, job


# Step kinds outside the paper's read: they never keep it busy or count in its progress.
OUTSIDE_PROGRESS = (StepKind.ANNOTATE.value, StepKind.RGROUPS.value)


def in_paper_progress():
    """SQL condition: the step counts in its paper's progress (every kind but `annotate` and
    `rgroups`, which run beside the read)."""
    return Step.kind.not_in(OUTSIDE_PROGRESS)


def _finish_check(session: Session, paper: Paper) -> None:
    """If no step of the paper is still active (annotate and rgroups steps aside), close the
    paper as done or failed.

    Failed (spec §8): check_pdf failed, or every page failed, a page being failed when its
    render_page or its segment_page step failed for good. Otherwise done, failed steps and all.
    """
    if paper.status not in (PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value):
        return
    session.flush()
    active = session.execute(
        select(func.count())
        .select_from(Step)
        .where(Step.paper_id == paper.id, Step.status.in_(ACTIVE), in_paper_progress())
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
    keep_address(paper, None)  # no longer active work: its address is not kept


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
    """A list of {idx, bbox, image_sha256, check_drawing?} with unique idx (one page's segments;
    check_drawing: a bool or None, absent from older results and cache rows)."""
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
        flag = item.get("check_drawing")
        if flag is not None and not isinstance(flag, bool):
            raise BadResult("segment_page: 'check_drawing' must be a bool or null")


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
    title = result.get("title")
    if title is not None and not _is_text(title):
        raise BadResult("doi: 'title' must be a string or null")
    first_author = result.get("first_author")
    if first_author is not None and not _is_text(first_author):
        raise BadResult("doi: 'first_author' must be a string or null")
    year = result.get("year")
    if year is not None and type(year) is not int:
        raise BadResult("doi: 'year' must be an int or null")


def _check_annotate_result(result: dict) -> None:
    for key in ("model", "model_version"):
        value = result.get(key)
        if not _is_text(value) or not value or len(value) > MAX_VERSION_CHARS:
            raise BadResult(f"annotate: {key!r} must be a non-empty string of at most "
                            f"{MAX_VERSION_CHARS} characters")  # fmt: skip
    output = result.get("output")
    error = annotation.values_error(output) or annotation.positions_error(
        result.get("positions"), output
    )
    if error:
        raise BadResult(f"annotate: {error}")
    if not _is_int(result.get("ms")):
        raise BadResult("annotate: 'ms' must be a non-negative int")


def _check_rgroups_result(result: dict) -> None:
    for key in ("model", "model_version"):
        value = result.get(key)
        if not _is_text(value) or not value or len(value) > MAX_VERSION_CHARS:
            raise BadResult(f"rgroups: {key!r} must be a non-empty string of at most "
                            f"{MAX_VERSION_CHARS} characters")  # fmt: skip
    labels = result.get("labels")
    error = rgroup_extraction.labels_error(labels) or rgroup_extraction.rows_error(
        result.get("rows"), labels
    )
    if error:
        raise BadResult(f"rgroups: {error}")
    if not isinstance(result.get("truncated"), bool):
        raise BadResult("rgroups: 'truncated' must be a bool")
    if not _is_int(result.get("ms")):
        raise BadResult("rgroups: 'ms' must be a non-negative int")


def _check_nothing(result: dict) -> None:
    pass


_CHECK = {
    StepKind.CHECK_PDF.value: _check_pdf_result,
    StepKind.SEGMENT_PAGE.value: _check_segment_page_result,
    StepKind.OCSR.value: _check_ocsr_result,
    StepKind.DOI.value: _check_doi_result,
    StepKind.ANNOTATE.value: _check_annotate_result,
    StepKind.RGROUPS.value: _check_rgroups_result,
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
    session.add_all(
        DrawingFlag(segment_id=seg.id)
        for seg, item in zip(segments, items, strict=True)
        if item.get("check_drawing")
    )
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
    done = (
        Step.paper_id == paper.id,
        Step.kind == StepKind.SEGMENT_PAGE.value,
        Step.status == StepStatus.DONE.value,
    )
    # Cheap first: pages segmented so far. Only the paper's last page reads the rows.
    pages_done = session.execute(select(func.count(Step.page.distinct())).where(*done))
    if pages_done.scalar_one() != paper.pages:
        return
    rows = session.execute(select(Step.page, Step.model_version).where(*done)).all()
    versions = {r.page: r.model_version for r in rows}
    if set(versions) != set(range(paper.pages)) or set(versions.values()) != {seg_version}:
        return
    segments = session.execute(
        select(
            Segment.page,
            Segment.idx,
            Segment.bbox,
            Segment.image_sha256,
            DrawingFlag.segment_id.is_not(None).label("check_drawing"),
        )
        .outerjoin(DrawingFlag, DrawingFlag.segment_id == Segment.id)
        .where(Segment.paper_id == paper.id)
        .order_by(Segment.page, Segment.idx)
    ).all()
    payload = {
        "pages": paper.pages,
        "segments": [
            {
                "page": g.page,
                "idx": g.idx,
                "bbox": list(g.bbox),
                "image_sha256": g.image_sha256,
                "check_drawing": g.check_drawing,
            }
            for g in segments
        ],
    }
    session.execute(
        pg_insert(SegCache)
        .values(
            owner_id=paper.owner_id,
            pdf_sha256=paper.pdf_sha256,
            seg_version=seg_cache_key(seg_version),
            paper_id=paper.id,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["owner_id", "pdf_sha256", "seg_version"])
    )


def _cached_page(session: Session, paper: Paper, page: int) -> list[dict] | None:
    """The page's cached segments with every crop present in this paper's crop dir, or None
    (no usable cache row for the configured segmenter version, or a crop not found)."""
    version = get_settings().seg_version
    if not version:
        return None
    payload = session.execute(
        select(SegCache.payload).where(
            SegCache.owner_id == paper.owner_id,
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
        if not _copy_crop(session, paper, item["image_sha256"]):
            log.info("paper %s page %d: cached crop not found; segmenting", paper.id, page)
            return None
    return items


def _page_items(payload: object, pages: int | None, page: int) -> list[dict]:
    """Validate a whole seg_cache payload (it is data: checked like worker results, every page)
    and return one page's segments as {idx, bbox, image_sha256, check_drawing} (None in a row
    from before the drawing check)."""
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
                "check_drawing": item.get("check_drawing"),
            }
        )
    for items in by_page.values():
        _check_segments(items)
    return by_page.get(page, [])


def _copy_crop(session: Session, paper: Paper, sha: str) -> bool:
    """Put the crop with content hash `sha` into this paper's crop dir.

    Sources are the same owner's other live (not deleted) papers with a segment of that hash;
    only the file's bytes are used, and only if they hash to `sha`. True if the crop is in
    place.
    """
    paper_id = paper.id
    dest = storage.segment_crop_path(paper_id, sha)
    if dest.is_file():
        return True
    sources = session.execute(
        select(Segment.paper_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .where(
            Segment.image_sha256 == sha,
            Segment.paper_id != paper_id,
            Paper.owner_id == paper.owner_id,
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
        storage.write_atomic(dest, data)
        return True
    return False


def _prediction(step: Step, result: dict) -> Prediction:
    # The R-group labels are computed once here, with the row (a string check; RDKit only for a
    # scaffold), so no read of the paper has to. Imported here: RDKit only where results land.
    from marcus.core.rgroups import rgroup_labels

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
        rgroups=rgroup_labels(result["smiles"], result.get("molfile")),
    )


def _after_ocsr(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    session.add(_prediction(step, result))
    return []


def _after_doi(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    paper.doi = result["doi"]
    paper.title = result.get("title")
    paper.first_author = result.get("first_author")
    paper.year = result.get("year")
    return []


def _after_annotate(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    """Store the model's values (a re-run replaces them; the curator's stay)."""
    step.model_version = result["model_version"]
    model = {
        "model": result["model"],
        "model_version": result["model_version"],
        "output": result["output"],
        "positions": result["positions"],
    }
    session.execute(
        pg_insert(Annotation)
        .values(paper_id=paper.id, **model)
        .on_conflict_do_update(index_elements=["paper_id"], set_={**model, "updated_at": _now()})
    )
    return []


def _ordered_subset(part: list[str], whole: list[str]) -> bool:
    """Every label of `part` is in `whole`, in the same order."""
    rest = iter(whole)
    return all(label in rest for label in part)


def _after_rgroups(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    """Store the rows and their labels on the step's request row (a re-run replaces them). The
    worker asks for the prediction's labels that the page text names: a result for labels the
    prediction does not have, or in another order, is refused."""
    step.model_version = result["model_version"]
    found = session.execute(
        select(RgroupExtraction, Prediction.rgroups)
        .join(Prediction, Prediction.id == RgroupExtraction.prediction_id)
        .where(RgroupExtraction.step_id == step.id)
        .with_for_update(of=RgroupExtraction)
    ).one_or_none()
    if found is None:
        return []  # the prediction is gone: nothing to store
    row, asked = found
    if not _ordered_subset(result["labels"], list(asked or [])):
        raise BadResult("rgroups: the result is for other labels than were asked for")
    now = _now()
    row.labels = result["labels"]
    row.status = "done"
    row.error = None
    row.rows = result["rows"]
    row.truncated = result["truncated"]
    row.model = result["model"]
    row.model_version = result["model_version"]
    row.updated_at = now
    row.finished_at = now
    return []


def _rgroups_failed(session: Session, step: Step) -> None:
    """The step failed for good: its request row says so (with the error class only). Earlier
    rows stay."""
    now = _now()
    session.execute(
        update(RgroupExtraction)
        .where(RgroupExtraction.step_id == step.id)
        .values(status="failed", error=step.error_class, updated_at=now, finished_at=now)
        .execution_options(synchronize_session=False)
    )


def _after_docling(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    """The text file already sits in the paper dir; the page label index goes on the paper
    (checked here, where the paper's page count is known: only pages the paper has)."""
    index = result.get("rgroup_text_labels")
    if "rgroup_text_labels" in result:
        error = rgroup_labels.index_error(index, paper.pages or 0)
        if error:
            raise BadResult(f"docling: {error}")
    paper.rgroup_text_labels = index
    return []


def _no_successors(session: Session, paper: Paper, step: Step, result: dict) -> list[Step]:
    # Fallback for a step kind with no entry in _AFTER: nothing to store, no successors.
    return []


_AFTER = {
    StepKind.CHECK_PDF.value: _after_check_pdf,
    StepKind.RENDER_PAGE.value: _after_render_page,
    StepKind.SEGMENT_PAGE.value: _after_segment_page,
    StepKind.OCSR.value: _after_ocsr,
    StepKind.DOCLING.value: _after_docling,
    StepKind.DOI.value: _after_doi,
    StepKind.ANNOTATE.value: _after_annotate,
    StepKind.RGROUPS.value: _after_rgroups,
}


# --- public API ----------------------------------------------------------------------------


def _settle_image_job(session: Session, job: ImageJob, error: str | None = None) -> None:
    """Image job status after one of its ocsr steps finished (flushes).

    While any ocsr step of the job is active it is `queued`; when the last one finishes it is
    `done` if the job has a prediction, else `failed` (with `error`). A failed extra engine
    therefore never turns a job with a good result into `failed`."""
    session.flush()
    active = session.execute(
        select(func.count())
        .select_from(Step)
        .where(Step.image_job_id == job.id, Step.status.in_(ACTIVE))
    ).scalar_one()
    if active:
        job.status = ImageJobStatus.QUEUED.value
        return
    predicted = session.execute(
        select(func.count()).select_from(Prediction).where(Prediction.image_job_id == job.id)
    ).scalar_one()
    if predicted:
        job.status = ImageJobStatus.DONE.value
        job.error = None
    else:
        job.status = ImageJobStatus.FAILED.value
        job.error = error
    keep_address(job, None)  # no longer active work: its address is not kept
    session.flush()


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
        _settle_image_job(session, job)
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
            _settle_image_job(session, job, error)
        if step.kind == StepKind.RGROUPS.value:
            _rgroups_failed(session, step)
    if paper is not None:
        _finish_check(session, paper)
    session.flush()


def cancel_paper(session: Session, paper_id: uuid.UUID, remove_files: bool = True) -> None:
    """Cancel all active steps, mark the paper deleted, drop the seg_cache row it made and its
    annotation, and remove its files. Caller commits.

    A running step's late result is dropped by complete_step / fail_step. A file that cannot
    be removed (any OSError) is logged and does not abort the transaction: the paper is
    deleted either way, and the retention purge's orphan sweep removes the leftovers later.
    `remove_files=False`: the caller runs remove_paper_files itself (the API: after its commit,
    in a thread).
    """
    paper = _lock(session, Paper, paper_id)
    if paper is None:
        raise ValueError("paper not found")
    session.execute(
        update(Step)
        .where(Step.paper_id == paper_id, Step.status.in_(ACTIVE))
        .values(status=StepStatus.CANCELLED.value, finished_at=_now())
        .execution_options(synchronize_session="fetch")
    )
    paper.status = PaperStatus.DELETED.value
    keep_address(paper, None)
    for model in (SegCache, Annotation):  # the annotation holds text from the paper: gone now
        session.execute(
            delete(model)
            .where(model.paper_id == paper_id)
            .execution_options(synchronize_session=False)
        )
    # R-group rows hold text from the paper too
    predictions = (
        select(Prediction.id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .where(Segment.paper_id == paper_id)
    )
    session.execute(
        delete(RgroupExtraction)
        .where(RgroupExtraction.prediction_id.in_(predictions))
        .execution_options(synchronize_session=False)
    )
    session.flush()
    if remove_files:
        remove_paper_files(paper_id)


def remove_paper_files(paper_id: uuid.UUID) -> None:
    """Remove a deleted paper's directory; an OSError is logged, not raised (retention retries)."""
    try:
        shutil.rmtree(storage.paper_dir(paper_id))
    except FileNotFoundError:
        pass  # already gone: nothing to remove
    except OSError as exc:
        log.warning(
            "paper %s: files not removed (%s: %s); the retention sweep retries",
            paper_id,
            type(exc).__name__,
            exc,
        )


def _waiting_ocsr(session: Session, where, engine: Engine) -> Step | None:
    """The `engine` OCSR step of a segment or image job (`where`) still pending, queued or
    running. Read under the parent's lock, so two requests at once cannot both miss it."""
    session.flush()
    return session.execute(
        select(Step)
        .where(where, Step.kind == StepKind.OCSR.value, Step.engine == engine.value,
               Step.status.in_(ACTIVE))
        .order_by(Step.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()  # fmt: skip


def request_ocsr(
    session: Session, segment_id: uuid.UUID, engine: Engine, started_ip: str | None = None
) -> Step:
    """Create a pending `ocsr` step for one segment with the given engine. Caller commits.
    A `done` paper becomes active again, with `started_ip` (the requesting address bucket).
    A step of that engine still waiting or running for the segment is returned instead (repeat
    requests never queue a second one).

    Raises ValueError for an unknown segment, a deleted paper, or a disabled engine.
    """
    engine = _ocsr_engine(engine)
    segment = session.get(Segment, segment_id)
    if segment is None:
        raise ValueError("segment not found")
    paper = _lock(session, Paper, segment.paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper is deleted")
    waiting = _waiting_ocsr(session, Step.segment_id == segment.id, engine)
    if waiting is not None:
        return waiting
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
        keep_address(paper, started_ip)
    session.flush()
    return step


def retry_page(
    session: Session, paper_id: uuid.UUID, page: int, started_ip: str | None = None
) -> Step:
    """Retry one failed page (0-based): a new pending `render_page` step, whose normal
    successors (segment_page, ocsr) follow. A `done`/`failed` paper goes back to `processing`.
    Caller commits.

    Locks the paper first. Raises ValueError for a missing or deleted paper, or a page outside
    the paper; RetryNotAllowed("not_failed") unless the page's newest finished render_page/
    segment_page step failed, ("busy") while any step of that page is pending, queued or running, and
    ("limit") after MANUAL_PAGE_RETRIES earlier manual retries.
    """
    paper = _lock(session, Paper, paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper not found")
    if paper.pages is None or not 0 <= page < paper.pages:
        raise ValueError("page not found")
    session.flush()
    rows = session.execute(
        select(Step.kind, Step.status, Step.created_at)
        .where(
            Step.paper_id == paper.id,
            Step.page == page,
            Step.kind.in_(PAGE_KINDS),
        )
        .order_by(*page_step_order())
    ).all()
    # the newest step that has finished decides; a pending retry leaves the old failure standing
    settled = [r for r in rows if r.status not in ACTIVE]
    if not settled or settled[0].status != StepStatus.FAILED.value:
        raise RetryNotAllowed("not_failed")
    busy = session.execute(
        select(func.count())
        .select_from(Step)
        .where(Step.paper_id == paper.id, Step.page == page, Step.status.in_(ACTIVE))
    ).scalar_one()
    if busy:
        raise RetryNotAllowed("busy")
    renders = sum(1 for r in rows if r.kind == StepKind.RENDER_PAGE.value)
    if renders - 1 >= MANUAL_PAGE_RETRIES:
        raise RetryNotAllowed("limit")
    step = _new_step(paper, StepKind.RENDER_PAGE, page, page=page, created_at=_now())
    session.add(step)
    if paper.status in (PaperStatus.DONE.value, PaperStatus.FAILED.value):
        paper.status = PaperStatus.PROCESSING.value
        paper.error = None
        keep_address(paper, started_ip)
    session.flush()
    return step


def request_image_ocsr(
    session: Session, job_id: uuid.UUID, engine: Engine, started_ip: str | None = None
) -> Step:
    """Create a pending `ocsr` step for an image job with the given engine and reopen the job
    (status `queued`; a finished job gets `started_ip`, the requesting address bucket). Caller
    commits. A step of that engine still waiting or running for the job is returned instead.

    Raises ValueError for an unknown or deleted image job, or a disabled engine.
    """
    engine = _ocsr_engine(engine)
    job = _lock(session, ImageJob, job_id)
    if job is None or job.status == ImageJobStatus.DELETED.value:
        raise ValueError("image job not found")
    waiting = _waiting_ocsr(session, Step.image_job_id == job.id, engine)
    if waiting is not None:
        return waiting
    seq = session.execute(
        select(func.count()).select_from(Step).where(Step.image_job_id == job.id)
    ).scalar_one()
    step = _new_image_step(job, engine, seq)
    session.add(step)
    if job.status not in (ImageJobStatus.QUEUED.value, ImageJobStatus.PROCESSING.value):
        keep_address(job, started_ip)  # active again, from this address
    job.status = ImageJobStatus.QUEUED.value
    session.flush()
    return step


def request_annotation(session: Session, paper_id: uuid.UUID, rerun: bool = False) -> Step | None:
    """Ask for the paper's annotation: a new pending `annotate` step, or None when the paper
    already has one and `rerun` is false. An annotate step still pending, queued or running is
    returned instead of a new one (repeat clicks). The paper's status does not change. Caller
    commits.

    Locks the paper first. Raises ValueError for a missing or deleted paper and
    AnnotateNotAllowed("no_text") unless the paper's docling step is done.
    """
    paper = _lock(session, Paper, paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper not found")
    session.flush()
    kind = Step.paper_id == paper.id
    running = session.execute(
        select(Step)
        .where(kind, Step.kind == StepKind.ANNOTATE.value, Step.status.in_(ACTIVE))
        .order_by(Step.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if running is not None:
        return running
    text = session.execute(
        select(func.count())
        .select_from(Step)
        .where(kind, Step.kind == StepKind.DOCLING.value, Step.status == StepStatus.DONE.value)
    ).scalar_one()
    if not text:
        raise AnnotateNotAllowed("no_text")
    if not rerun and session.get(Annotation, paper.id) is not None:
        return None
    step = _new_step(paper, StepKind.ANNOTATE, ANNOTATE_SEQ, created_at=_now())
    session.add(step)
    session.flush()
    return step


def request_rgroups(session: Session, prediction_id: uuid.UUID, rerun: bool = False) -> Step | None:
    """Ask for a scaffold's R-group rows: a new pending `rgroups` step for the prediction and its
    `rgroup_extractions` row set `queued` (a new row's labels: the prediction's), or None when it
    already has rows and `rerun` is false. An rgroups step of the prediction still pending,
    queued or running is returned instead of a new one (repeat clicks). The paper's status does
    not change. Caller commits.

    Locks the paper, then the row. Raises ValueError for a missing prediction, one not from a
    paper, or a deleted paper, and RgroupsNotAllowed("no_rgroups") for a prediction without
    R-group labels or with only unlabelled points (`*`: the model has no request for them).
    """
    found = session.execute(
        select(Prediction.rgroups, Segment.id, Segment.paper_id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .where(Prediction.id == prediction_id)
    ).one_or_none()
    if found is None:
        raise ValueError("prediction not found")
    paper = _lock(session, Paper, found.paper_id)
    if paper is None or paper.status == PaperStatus.DELETED.value:
        raise ValueError("paper not found")
    labels = list(found.rgroups or [])
    if not rgroup_labels.drawn_labels(labels):
        raise RgroupsNotAllowed("no_rgroups")  # none, or only unlabelled points (`*`)
    row = session.execute(
        select(RgroupExtraction)
        .where(RgroupExtraction.prediction_id == prediction_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is not None and row.step_id is not None:
        running = session.execute(
            select(Step).where(Step.id == row.step_id, Step.status.in_(ACTIVE))
        ).scalar_one_or_none()
        if running is not None:
            return running
    if row is not None and row.status == "done" and not rerun:
        return None
    step = _new_step(paper, StepKind.RGROUPS, RGROUPS_SEQ, segment_id=found.id, created_at=_now())
    session.add(step)
    session.flush()  # assigns the step id
    if row is None:
        row = RgroupExtraction(prediction_id=prediction_id, labels=labels, status="queued")
        session.add(row)
    # An existing row keeps its labels: they are those of the rows it shows (the worker asks
    # for the prediction's labels again, and the result sets them).
    row.step_id = step.id
    row.status = "queued"
    row.error = None
    row.updated_at = _now()
    row.finished_at = None
    session.flush()
    return step
