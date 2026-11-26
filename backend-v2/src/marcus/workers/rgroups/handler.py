"""The `rgroups` step handler (worker-rgroup, worker-fake-rgroup): one scaffold's R-group rows.

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
from collections.abc import Sequence

from sqlalchemy import select

from marcus.core.enums import StepKind
from marcus.core.models import Prediction, RgroupExtraction, Segment
from marcus.core.page_text import UNUSABLE_TEXT, page_context, read_paper_document
from marcus.core.pipeline import BadResult
from marcus.core.rgroup_extraction import BadRows, labels_to_ask, parse_rows, salvage_rows
from marcus.core.rgroup_series import drawing_compounds, keep_series, series_boxes
from marcus.core.rgroups import _label_order
from marcus.core.settings import fake_enabled, get_settings
from marcus.core.storage import page_image_path
from marcus.workers.rgroups.fake import FakeRgroupReader
from marcus.workers.rgroups.inputs import page_image_uri
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
        settings.llm_url, settings.llm_timeout_s, settings.llm_model, settings.llm_model_version
    )


def _document(paper_id: uuid.UUID) -> dict | None:
    """The paper's Docling document; None when its text is missing, too large or not a Docling
    document (the R-groups are then read from the page image only)."""
    try:
        return read_paper_document(paper_id)
    except FileNotFoundError:
        log.info("paper %s: no text; R-groups read from the page image only", paper_id)
    except UNUSABLE_TEXT as exc:
        log.warning("paper %s: text not usable (%s); R-groups read from the page image only",
                    paper_id, type(exc).__name__)  # fmt: skip
    return None


def _image(paper_id: uuid.UUID, page: int) -> str:
    try:
        return page_image_uri(page_image_path(paper_id, page))
    except FileNotFoundError:
        raise BadInput("the page image is missing") from None
    except (OSError, ValueError, SyntaxError):  # Pillow: unreadable or not an image
        raise BadInput("the page image could not be read") from None


def read_scaffold(
    reader,
    paper_id: uuid.UUID,
    page: int,
    labels: list[str],
    bbox: Sequence[int] | None = None,
    drawings: Sequence[Sequence[int]] | None = None,
) -> dict:
    """Ask `reader` for the rows of a scaffold with `labels` on `page` (0-based). Only the drawn
    labels the page text names are asked for (rgroup_extraction.labels_to_ask: no `*`, no OCSR
    extra label); the result's `labels` are those. The reader reads the whole page: with the
    drawing's box (`bbox`, page pixels), the rows of another series are dropped when a series
    label is printed under the drawing or to its right; a label belongs to the nearest of the
    page's `drawings` (the boxes of all its segments) only (marcus.core.rgroup_series; owner,
    2026-11-26)."""
    doc = _document(paper_id)
    context = page_context(doc, page + 1) if doc is not None else ""
    labels = labels_to_ask(labels, context)
    if not labels:
        raise BadInput("the structure has no labelled R-groups")
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
    if doc is not None and bbox is not None:
        own = drawing_compounds(bbox, series_boxes(doc).get(page, []), drawings)
        kept = keep_series(rows, own)
        if len(kept) != len(rows):
            log.info("paper %s page %d: %d of %d rows are another series's (own: %s)",
                     paper_id, page, len(rows) - len(kept), len(rows), sorted(own))  # fmt: skip
        rows = kept
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
        select(Prediction.rgroups, Segment.page, Segment.bbox)
        .select_from(RgroupExtraction)
        .join(Prediction, Prediction.id == RgroupExtraction.prediction_id)
        .join(Segment, Segment.id == step.segment_id)
        .where(RgroupExtraction.step_id == step.id)
    ).one_or_none()
    drawings = []
    labels: list[str] = []
    if found is not None:
        # every engine's labels of this drawing: one engine may misread one (MolScribe read R5
        # as "Rs", BJOC 18/23); the page text still decides which are asked (labels_to_ask)
        readings = session.scalars(
            select(Prediction.rgroups).where(Prediction.segment_id == step.segment_id)
        ).all()
        labels = sorted(
            {lab for found_labels in [found.rgroups, *readings] for lab in (found_labels or [])},
            key=_label_order,
        )
    if found is not None:  # the page's drawings: a series label belongs to the nearest one
        drawings = session.scalars(
            select(Segment.bbox).where(
                Segment.paper_id == step.paper_id, Segment.page == found.page
            )
        ).all()
    session.rollback()  # end the read before the long work
    if found is None:
        raise BadInput("the structure is gone")
    reader = get_reader()
    return read_scaffold(reader, step.paper_id, found.page, labels, found.bbox, drawings)


register(StepKind.RGROUPS, extract_rgroups)
