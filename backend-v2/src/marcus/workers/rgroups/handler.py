"""The `rgroups` step handler (worker-llm, worker-fake-annotate): one scaffold's R-group rows.

The step points at its request row (rgroup_extractions.step_id), and through it at the
prediction (its R-group labels) and the segment (the page). Of the labels, only the drawn ones
(not `*`) that the page text names are asked for (marcus.core.rgroup_extraction.labels_to_ask). The
handler builds the model's two inputs (marcus.workers.rgroups.inputs: the text of pages P-1..P+1
of the paper's Docling document, and the page image at the size the model was trained on), asks
the reader, and parses the answer (marcus.core.rgroup_extraction.parse_rows). The planner checks
the result again before storing it (pipeline._check_rgroups_result).

Input problems are final (BadInput): no request row (the structure is gone), no page image or
one that cannot be read. A paper whose text is missing or unreadable is read from the image
alone (the context is then empty, as for a page without text). An answer outside the schema is
final (BadResult): decoding is greedy, so a retry gives the same answer. An answer the token
limit cut keeps the rows that were complete (`truncated`).
"""

import logging
import time
import uuid

from sqlalchemy import select

from marcus.core import annotation as ann
from marcus.core.enums import StepKind
from marcus.core.models import Prediction, RgroupExtraction, Segment
from marcus.core.pipeline import BadResult
from marcus.core.rgroup_extraction import BadRows, labels_to_ask, parse_rows, salvage_rows
from marcus.core.settings import fake_enabled, get_settings
from marcus.core.storage import page_image_path, text_path
from marcus.workers.rgroups.fake import FakeRgroupReader
from marcus.workers.rgroups.inputs import page_context, page_image_uri
from marcus.workers.rgroups.llama import LlamaRgroupReader
from marcus.workers.runtime import BadInput, register

log = logging.getLogger(__name__)


def get_reader():
    """The configured reader (settings `rgroup_reader`); the fake one only where fake engines are
    enabled."""
    settings = get_settings()
    if settings.rgroup_reader == "fake":
        if not fake_enabled():
            raise RuntimeError("the fake R-group reader is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
        return FakeRgroupReader()
    return LlamaRgroupReader(
        settings.rgroup_url,
        settings.rgroup_timeout_s,
        settings.rgroup_model,
        settings.rgroup_model_version,
    )


def _context(paper_id: uuid.UUID, page: int) -> str:
    """The page text for a scaffold on `page` (0-based, as the API counts; Docling counts from
    1). "" when the paper's text is missing, too large or not a Docling document."""
    try:
        doc = ann.read_document(text_path(paper_id))
        if not isinstance(doc, dict):
            raise ValueError("not a Docling document")
        return page_context(doc, page + 1)
    except FileNotFoundError:
        log.info("paper %s: no text; R-groups read from the page image only", paper_id)
    except (ann.TextTooLarge, OSError, ValueError, KeyError, TypeError, AttributeError,
            RecursionError) as exc:  # fmt: skip
        log.warning("paper %s: text not usable (%s); R-groups read from the page image only",
                    paper_id, type(exc).__name__)  # fmt: skip
    return ""


def _image(paper_id: uuid.UUID, page: int) -> str:
    try:
        return page_image_uri(page_image_path(paper_id, page))
    except FileNotFoundError:
        raise BadInput("the page image is missing") from None
    except (OSError, ValueError, SyntaxError):  # Pillow: unreadable or not an image
        raise BadInput("the page image could not be read") from None


def read_scaffold(reader, paper_id: uuid.UUID, page: int, labels: list[str]) -> dict:
    """Ask `reader` for the rows of a scaffold with `labels` on `page` (0-based). Only the drawn
    labels the page text names are asked for (rgroup_extraction.labels_to_ask: no `*`, no OCSR
    extra label); the result's `labels` are those."""
    context = _context(paper_id, page)
    labels = labels_to_ask(labels, context)
    image = _image(paper_id, page)
    start = time.monotonic()
    raw, cut = reader.read(labels, context, image)
    ms = int((time.monotonic() - start) * 1000)
    try:
        rows = parse_rows(raw, labels)
    except BadRows as exc:
        if not cut:
            raise BadResult(str(exc)) from None
        rows = salvage_rows(raw, labels)
    return {
        "model": reader.model,
        "model_version": reader.version,
        "labels": labels,
        "rows": rows,
        "truncated": cut,
        "ms": ms,
    }


def extract_rgroups(step, session) -> dict:
    if step.paper_id is None or step.segment_id is None:
        raise BadInput("rgroups step has no structure")
    found = session.execute(
        select(Prediction.rgroups, Segment.page)
        .select_from(RgroupExtraction)
        .join(Prediction, Prediction.id == RgroupExtraction.prediction_id)
        .join(Segment, Segment.id == step.segment_id)
        .where(RgroupExtraction.step_id == step.id)
    ).one_or_none()
    session.rollback()  # end the read before the long work
    if found is None:
        raise BadInput("the structure is gone")
    reader = get_reader()
    return read_scaffold(reader, step.paper_id, found.page, list(found.rgroups))


register(StepKind.RGROUPS, extract_rgroups)
