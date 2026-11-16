"""CPU worker handlers: check_pdf, render_page, docling, doi.

Importing this module registers them (the worker-cpu image imports it). Handlers get a
detached read-only Step view and never write to the database; results are plain dicts.
"""

import functools
import json
import logging
import os
import re
import uuid
from pathlib import Path

from marcus.core.enums import StepKind
from marcus.core.storage import page_image_path, paper_dir, pdf_path
from marcus.workers import pdfsafe
from marcus.workers.runtime import register

log = logging.getLogger(__name__)

DOI_CALL_TIMEOUT_S = 5
DOI_TOTAL_S = 15
DOI_MAX_CHARS = 255
_DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)


def check_pdf(step, session) -> dict:
    return {"pages": pdfsafe.page_count(pdf_path(step.paper_id), timeout_s=20)}


def render_page(step, session) -> dict:
    pdfsafe.render_page_png(
        pdf_path(step.paper_id),
        step.page,
        page_image_path(step.paper_id, step.page),
        timeout_s=30,
    )
    return {}


@functools.lru_cache(maxsize=1)
def _converter():
    from docling.document_converter import DocumentConverter

    return DocumentConverter()


def _convert_to_dict(path: Path) -> dict:
    """Same call chain as v1 get_converted_document: convert, then export_to_dict()."""
    return _converter().convert(str(path)).document.export_to_dict()


def docling(step, session) -> dict:
    doc = _convert_to_dict(pdf_path(step.paper_id))
    out_dir = paper_dir(step.paper_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f".text.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        os.replace(tmp, out_dir / "text.json")
    finally:
        tmp.unlink(missing_ok=True)
    return {"text_path": "text.json"}


def normalise_doi(value) -> str | None:
    if not isinstance(value, str):
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).strip()
    if not doi or len(doi) > DOI_MAX_CHARS:
        return None
    return doi


def _lookup_doi(path: str) -> str | None:
    """Runs in a child process: pdf2doi with online methods. pdf2doi has no timeout option, so
    the socket default (5 s) bounds every network call; the parent kills the child at 15 s."""
    import socket

    socket.setdefaulttimeout(DOI_CALL_TIMEOUT_S)
    import pdf2doi

    pdf2doi.config.set("verbose", False)
    pdf2doi.config.set("save_identifier_metadata", False)  # never write into the user's PDF
    result = pdf2doi.pdf2doi(path)
    if isinstance(result, dict):
        return result.get("identifier")
    return None


def doi(step, session) -> dict:
    """Never fails the paper: any error or timeout means no DOI."""
    try:
        raw = pdfsafe.run_isolated(
            _lookup_doi, (str(pdf_path(step.paper_id)),), DOI_TOTAL_S, mem_mb=None
        )
        return {"doi": normalise_doi(raw)}
    except Exception as exc:  # noqa: BLE001
        log.info("doi lookup gave nothing: %s", type(exc).__name__)
        return {"doi": None}


register(StepKind.CHECK_PDF, check_pdf)
register(StepKind.RENDER_PAGE, render_page)
register(StepKind.DOCLING, docling)
register(StepKind.DOI, doi)
