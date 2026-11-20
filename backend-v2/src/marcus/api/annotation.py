"""Read side of a paper's annotation: the response shape, the values exports use, and the
positions of curated values (located in the paper's text like the model's)."""

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import AnnotationField, AnnotationOut, StepOut
from marcus.core import annotation as ann
from marcus.core.enums import StepKind
from marcus.core.models import Annotation, Step
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

FIELD_LIST = [
    AnnotationField(key=f, label=ann.LABELS[f], max_length=ann.MAX_LENGTH[f]) for f in ann.FIELDS
]


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


def for_export(row: Annotation | None) -> dict | None:
    """The paper-level annotation object of an export (plain data: it travels pickled to the
    chem process). `values`: what is shown (the curator's, else the model's)."""
    if row is None:
        return None
    return {
        "source": "curated" if row.curated is not None else "model",
        "model": row.model,
        "model_version": row.model_version,
        "values": shown(row),
        "model_values": {f: list(row.output.get(f, [])) for f in ann.FIELDS},
        "annotated_at": row.updated_at.isoformat(),
        "curated_at": row.curated_at.isoformat() if row.curated_at else None,
    }


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


def text_blocks(path: Path) -> list[str]:
    """The text blocks of a paper's Docling document at `path` (blocking file read). [] when
    the text is missing, too large or unreadable."""
    try:
        return ann.docling_blocks(ann.read_document(path))
    except ann.TextTooLarge:
        log.warning("%s: text too large to locate curated values", path.parent.name)
        return []
    except (OSError, ValueError):
        return []


def known_positions(row: Annotation) -> dict[str, list]:
    """value -> positions, for every value already located on this paper (the model's and the
    stored curation's). A value's positions do not depend on its field."""
    known: dict[str, list] = {}
    for found in (row.positions, row.curated_positions or {}):
        for per_value in found.values():
            known.update(per_value)
    return known


def locate(path: Path, values: dict[str, list[str]], known: dict[str, list]) -> dict:
    """Positions of `values` in the paper's text (its Docling document at `path`, from
    storage.text_path: the path is resolved in the API process, whose settings are current),
    {field: {value: positions}}. Values in `known` keep theirs; only new ones are searched,
    and the text is read only for them. Blocking and CPU-bound: the route runs it in the chem
    process (marcus.api.chempool)."""
    new = {v for items in values.values() for v in items if v not in known}
    found = dict(known)
    if new:
        locator = ann.Locator(text_blocks(path))
        found.update((v, locator.find(v)) for v in new)
    return {field: {v: found[v] for v in values.get(field, [])} for field in ann.FIELDS}
