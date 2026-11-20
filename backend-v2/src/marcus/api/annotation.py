"""Read side of a paper's annotation: the response shape, the values exports use, and the
positions of curated values (located in the paper's text like the model's)."""

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import AnnotationField, AnnotationOut, StepOut
from marcus.core import annotation as ann
from marcus.core import storage
from marcus.core.enums import StepKind
from marcus.core.models import Annotation, Step
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

FIELD_LIST = [AnnotationField(key=f, label=ann.LABELS[f]) for f in ann.FIELDS]
MAX_TEXT_BYTES = 64 * 2**20  # a Docling document larger than this is not read by the API


def shown(row: Annotation | None) -> dict[str, list[str]] | None:
    """The values shown and exported: the curator's, else the model's (FIELDS order)."""
    if row is None:
        return None
    values = row.curated if row.curated is not None else row.output
    return {f: list(values.get(f, [])) for f in ann.FIELDS}


async def load(db: AsyncSession, paper_id: uuid.UUID) -> Annotation | None:
    return (
        await db.execute(
            select(Annotation)
            .where(Annotation.paper_id == paper_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def load_for_update(db: AsyncSession, paper_id: uuid.UUID) -> Annotation | None:
    """The row locked until the commit (a model run finishing meanwhile waits for it)."""
    return (
        await db.execute(
            select(Annotation)
            .where(Annotation.paper_id == paper_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def annotation_out(db: AsyncSession, paper_id: uuid.UUID) -> AnnotationOut:
    row = await load(db, paper_id)
    step = (
        await db.execute(
            select(Step)
            .where(Step.paper_id == paper_id, Step.kind == StepKind.ANNOTATE.value)
            .order_by(Step.created_at.desc(), Step.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    values = shown(row)
    return AnnotationOut(
        available=get_settings().annotate_enabled,
        status=step.status if step is not None else "none",
        step=StepOut.model_validate(step) if step is not None else None,
        fields=FIELD_LIST,
        model=row.model if row else None,
        model_version=row.model_version if row else None,
        output=row.output if row else None,
        positions=row.positions if row else None,
        curated=row.curated if row else None,
        curated_positions=row.curated_positions if row else None,
        values=values,
        coconut=ann.coconut_prefill(values) if values is not None else None,
        created_at=row.created_at if row else None,
        updated_at=row.updated_at if row else None,
        curated_at=row.curated_at if row else None,
    )


def text_blocks(paper_id: uuid.UUID) -> list[str]:
    """The paper's text blocks (blocking file read: run it in a thread). [] when the text is
    missing, too large or unreadable."""
    path: Path = storage.paper_dir(paper_id) / "text.json"
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            log.warning("paper %s: text too large to locate curated values", paper_id)
            return []
        return ann.docling_blocks(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def locate(paper_id: uuid.UUID, values: dict[str, list[str]]) -> dict:
    """Positions of `values` in the paper's text (blocking: run it in a thread)."""
    return ann.positions(ann.Locator(text_blocks(paper_id)), values)
