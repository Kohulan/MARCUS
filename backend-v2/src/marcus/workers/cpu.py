"""CPU worker handlers: check_pdf, render_page, docling, doi; plus the retention purge task.

Importing this module registers them (the worker-cpu image imports it). Handlers get a
detached read-only Step view and never write to the database; results are plain dicts.
The daily purge (`marcus.retention.purge_expired`, a plain Celery task, not a step) lives in
marcus.workers.retention and is registered by the import below.
"""

import html
import importlib
import json
import logging
import re
import time
import unicodedata
from datetime import UTC, datetime
from urllib.parse import quote

import requests
from sqlalchemy import select

from marcus.core.enums import StepKind
from marcus.core.models import Paper
from marcus.core.queues import time_limits_for
from marcus.core.storage import disk_is_full, page_image_path, paper_dir, pdf_path
from marcus.workers import pdfsafe
from marcus.workers.runtime import StorageFull, register

importlib.import_module("marcus.workers.retention")  # registers the purge task in worker-cpu

log = logging.getLogger(__name__)

# Child timeouts sit below the Celery soft limits (20/30/scaled/15) so the child is killed (and
# reported as StepTimeout: error class timeout, retried once) before Celery's soft limit fires.
CHECK_TIMEOUT_S = 15
RENDER_TIMEOUT_S = 25
DOCLING_MARGIN_S = 20  # child timeout = Celery soft limit - margin (soft scales with pages)
DOI_CALL_TIMEOUT_S = 5
DOI_TOTAL_S = 12
DOI_OP = "doi"
DOI_MAX_CHARS = 255
TITLE_MAX_CHARS = 500
AUTHOR_MAX_CHARS = 100
YEAR_MIN = 1800
NO_META = {"title": None, "first_author": None, "year": None}
TITLE_MAX_BYTES = 256 * 1024
TITLE_MIN_LEFT_S = 1
CROSSREF_URL = "https://api.crossref.org/works/{}"
DATACITE_URL = "https://api.datacite.org/dois/{}"
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_YEAR = re.compile(r"[0-9]{4}")
_DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)


def check_pdf(step, session) -> dict:
    return {"pages": pdfsafe.page_count(pdf_path(step.paper_id), timeout_s=CHECK_TIMEOUT_S)}


def render_page(step, session) -> dict:
    """Render one page (pdfsafe child). Below the free-space floor of the data volume nothing is
    written and the step fails retryable (StorageFull): accepted papers must not fill the disk
    once uploads are refused."""
    if disk_is_full():
        raise StorageFull("data volume below its free-space floor")
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
    result: dict = {"text_path": "text.json"}
    index = _page_label_index(step.paper_id, pages)
    if index is not None:
        result["rgroup_text_labels"] = index
    return result


def _page_label_index(paper_id, pages: int | None) -> dict | None:
    """Per page, the R-group labels its text names (marcus.core.rgroup_labels.page_label_index),
    from the text docling just wrote; None when that text cannot be read or the page count is
    unknown (every label is then shown)."""
    from marcus.core.page_text import UNUSABLE_TEXT, read_paper_document
    from marcus.core.rgroup_labels import page_label_index

    if not pages:
        return None
    try:
        return page_label_index(read_paper_document(paper_id), pages)
    except UNUSABLE_TEXT as exc:  # FileNotFoundError too: no text, no index
        log.warning("paper %s: no page label index (%s)", paper_id, type(exc).__name__)
        return None


def normalise_doi(value) -> str | None:
    if not isinstance(value, str):
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).strip()
    if not doi or len(doi) > DOI_MAX_CHARS:
        return None
    return doi


def _first(items) -> dict:
    """The first entry of a list of objects, else an empty one."""
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def _date_year(date) -> object:
    parts = date.get("date-parts") if isinstance(date, dict) else None
    first = parts[0] if isinstance(parts, list) and parts else None
    return first[0] if isinstance(first, list) and first else None


def _crossref_meta(data) -> dict:
    message = data["message"]
    # `published` as in v1; `issued` only when it has no year
    years = (_clean_year(_date_year(message.get(k))) for k in ("published", "issued"))
    return {
        "title": _clean_text(message["title"][0], TITLE_MAX_CHARS),
        "first_author": _clean_text(_first(message.get("author")).get("family"), AUTHOR_MAX_CHARS),
        "year": next((y for y in years if y is not None), None),
    }


def _datacite_meta(data) -> dict:
    attributes = data["data"]["attributes"]
    creator = _first(attributes.get("creators"))
    author = _clean_text(creator.get("familyName"), AUTHOR_MAX_CHARS)
    return {
        "title": _clean_text(attributes["titles"][0]["title"], TITLE_MAX_CHARS),
        "first_author": author or _clean_text(creator.get("name"), AUTHOR_MAX_CHARS),
        "year": _clean_year(attributes.get("publicationYear")),
    }


_HIDDEN = {"Cc", "Cf", "Cs"}  # controls (NUL too), format (bidi, zero-width), lone surrogates


def _clean_text(raw, max_chars: int) -> str | None:
    """Tags out, entities unescaped, control/format/surrogate chars out, spaces collapsed, cut
    to `max_chars`. One such char would otherwise make the pipeline reject the whole result."""
    if not isinstance(raw, str):
        return None
    text = html.unescape(_TAGS.sub("", raw))
    text = "".join(c for c in text if c.isspace() or unicodedata.category(c) not in _HIDDEN)
    text = _SPACES.sub(" ", text).strip()[:max_chars].strip()
    return text or None


def _clean_year(raw) -> int | None:
    """An int or a four-digit string, from YEAR_MIN to next year, else None."""
    if isinstance(raw, str) and _YEAR.fullmatch(raw):
        raw = int(raw)
    if type(raw) is not int:  # not bool, not float
        return None
    return raw if YEAR_MIN <= raw <= datetime.now(UTC).year + 1 else None


def _get_json(http, url: str, timeout_s: float):
    """One GET: no redirects, at most TITLE_MAX_BYTES read, JSON object or None."""
    resp = http.get(url, timeout=timeout_s, allow_redirects=False, stream=True)
    try:
        if resp.status_code != 200:
            return None
        body = bytearray()  # appended in place, not copied per chunk
        for chunk in resp.iter_content(16 * 1024):
            body += chunk
            if len(body) > TITLE_MAX_BYTES:
                return None
        return json.loads(body)
    finally:
        resp.close()


def fetch_meta(doi: str, timeout_s: float) -> dict:
    """Paper title, first author's family name and year from Crossref, then DataCite: the
    first reply with a title gives all three. `timeout_s` is the whole budget; each call gets
    min(DOI_CALL_TIMEOUT_S, time left). The DOI comes from an untrusted PDF, so it is quoted into
    the path. Any error, redirect or non-200 means nothing from that source."""
    deadline = time.monotonic() + timeout_s
    quoted = quote(doi, safe="")
    with requests.Session() as http:
        for url, pick in (
            (CROSSREF_URL.format(quoted), _crossref_meta),
            (DATACITE_URL.format(quoted), _datacite_meta),
        ):
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                data = _get_json(http, url, min(DOI_CALL_TIMEOUT_S, left))
                meta = pick(data) if data is not None else None
            except Exception as exc:  # noqa: BLE001
                log.info("title lookup gave nothing: %s", type(exc).__name__)
                continue
            if meta and meta["title"]:
                return meta
    return dict(NO_META)


def doi(step, session) -> dict:
    """Never fails the paper: any error or timeout means no DOI (and no title, first author or
    year). The metadata call runs only for a found DOI and shares the DOI_TOTAL_S budget."""
    start = time.monotonic()
    try:
        raw = pdfsafe.run_op(
            DOI_OP, [str(pdf_path(step.paper_id)), DOI_CALL_TIMEOUT_S], DOI_TOTAL_S
        )
        found = normalise_doi(raw)
    except Exception as exc:  # noqa: BLE001
        log.info("doi lookup gave nothing: %s", type(exc).__name__)
        return {"doi": None, **NO_META}
    meta = NO_META
    left = DOI_TOTAL_S - (time.monotonic() - start)
    if found and left >= TITLE_MIN_LEFT_S:
        try:
            meta = fetch_meta(found, left)
        except Exception as exc:  # noqa: BLE001
            log.info("title lookup gave nothing: %s", type(exc).__name__)
    return {"doi": found, **meta}


register(StepKind.CHECK_PDF, check_pdf)
register(StepKind.RENDER_PAGE, render_page)
register(StepKind.DOCLING, docling)
register(StepKind.DOI, doi)
