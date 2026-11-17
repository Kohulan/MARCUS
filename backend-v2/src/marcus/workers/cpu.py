"""CPU worker handlers: check_pdf, render_page, docling, doi; plus the retention purge task.

Importing this module registers them (the worker-cpu image imports it). Handlers get a
detached read-only Step view and never write to the database; results are plain dicts.
The daily purge (`marcus.retention.purge_expired`, a plain Celery task, not a step) lives in
marcus.workers.retention and is registered by the import below.
"""

import logging
import re

from sqlalchemy import select

from marcus.core.enums import StepKind
from marcus.core.models import Paper
from marcus.core.queues import time_limits_for
from marcus.core.storage import page_image_path, paper_dir, pdf_path
from marcus.workers import (
    pdfsafe,
    retention,  # noqa: F401  (registers the purge task in worker-cpu)
)
from marcus.workers.runtime import register

log = logging.getLogger(__name__)

# Child timeouts sit below the Celery soft limits (20/30/scaled/15) so a timeout here is mapped
# to BadInput before the runtime's SoftTimeLimitExceeded can fire.
CHECK_TIMEOUT_S = 15
RENDER_TIMEOUT_S = 25
DOCLING_MARGIN_S = 20  # child timeout = Celery soft limit - margin (soft scales with pages)
DOI_CALL_TIMEOUT_S = 5
DOI_TOTAL_S = 12
DOI_OP = "doi"
DOI_MAX_CHARS = 255
_DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)


def check_pdf(step, session) -> dict:
    return {"pages": pdfsafe.page_count(pdf_path(step.paper_id), timeout_s=CHECK_TIMEOUT_S)}


def render_page(step, session) -> dict:
    pdfsafe.render_page_png(
        pdf_path(step.paper_id),
        step.page,
        page_image_path(step.paper_id, step.page),
        timeout_s=RENDER_TIMEOUT_S,
    )
    return {}


def docling(step, session) -> dict:
    """Docling parses the untrusted PDF in an isolated child (32 GiB address space cap)."""
    pages = None
    if session is not None:
        try:
            pages = session.execute(
                select(Paper.pages).where(Paper.id == step.paper_id)
            ).scalar_one_or_none()
        finally:
            session.rollback()  # end the read transaction before the long work
    soft, _ = time_limits_for(StepKind.DOCLING, pages)
    pdfsafe.run_docling(
        pdf_path(step.paper_id), paper_dir(step.paper_id), timeout_s=soft - DOCLING_MARGIN_S
    )
    return {"text_path": "text.json"}


def normalise_doi(value) -> str | None:
    if not isinstance(value, str):
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).strip()
    if not doi or len(doi) > DOI_MAX_CHARS:
        return None
    return doi


def doi(step, session) -> dict:
    """Never fails the paper: any error or timeout means no DOI."""
    try:
        raw = pdfsafe.run_op(
            DOI_OP, [str(pdf_path(step.paper_id)), DOI_CALL_TIMEOUT_S], DOI_TOTAL_S
        )
        return {"doi": normalise_doi(raw)}
    except Exception as exc:  # noqa: BLE001
        log.info("doi lookup gave nothing: %s", type(exc).__name__)
        return {"doi": None}


register(StepKind.CHECK_PDF, check_pdf)
register(StepKind.RENDER_PAGE, render_page)
register(StepKind.DOCLING, docling)
register(StepKind.DOI, doi)
