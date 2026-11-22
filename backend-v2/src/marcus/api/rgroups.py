"""Read side of the R-group rows: the response shape and the rows exports use."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.read import named_on
from marcus.api.schemas import RgroupExtractionOut, RgroupRow
from marcus.core.enums import StepStatus
from marcus.core.models import Paper, Prediction, RgroupExtraction, Segment, Step
from marcus.core.rgroup_labels import shown_labels
from marcus.core.settings import get_settings


def _rows(row: RgroupExtraction) -> list[dict] | None:
    """Stored rows with each row's groups in label order (JSONB keeps no key order)."""
    if row.rows is None:
        return None
    labels = list(row.labels)
    return [
        {
            "compound": r.get("compound", ""),
            "groups": {lab: (r.get("groups") or {}).get(lab, "") for lab in labels},
        }
        for r in row.rows
        if isinstance(r, dict)
    ]


def _status(row: RgroupExtraction, step_status: str | None) -> str:
    """The row's status, with `queued` told apart from `running` by its step."""
    if row.status == "queued" and step_status == StepStatus.RUNNING.value:
        return "running"
    return row.status


def extraction_out(
    row: RgroupExtraction,
    segment_id: uuid.UUID,
    step_status: str | None,
    named: list[str] | None = None,
) -> RgroupExtractionOut:
    """`named`: the labels the structure's page names (read.named_on). Before any rows the
    labels are the structure's shown ones (as on the card); with rows, those of the rows."""
    rows = _rows(row)
    labels = list(row.labels) if row.rows is not None else shown_labels(list(row.labels), named)
    return RgroupExtractionOut(
        prediction_id=row.prediction_id,
        segment_id=segment_id,
        status=_status(row, step_status),  # type: ignore[arg-type]
        labels=labels,
        rows=[RgroupRow(**r) for r in rows] if rows is not None else None,
        truncated=row.truncated,
        error=row.error if row.status == "failed" else None,
        model=row.model,
        model_version=row.model_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
    )


def none_out(prediction: Prediction, named: list[str] | None = None) -> RgroupExtractionOut:
    """A prediction never asked for (its shown labels, as on the card)."""
    return RgroupExtractionOut(
        prediction_id=prediction.id,
        segment_id=prediction.segment_id,  # type: ignore[arg-type]
        status="none",
        labels=shown_labels(list(prediction.rgroups or []), named),
        rows=None,
        truncated=False,
        error=None,
        model=None,
        model_version=None,
        created_at=None,
        updated_at=None,
        finished_at=None,
    )


def _query(where):
    return (
        select(
            RgroupExtraction,
            Prediction.segment_id,
            Step.status,
            Segment.page,
            Paper.rgroup_text_labels,
        )
        .join(Prediction, Prediction.id == RgroupExtraction.prediction_id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .outerjoin(Step, Step.id == RgroupExtraction.step_id)
        .where(where)
        .execution_options(populate_existing=True)
    )


async def for_paper(db: AsyncSession, paper_id: uuid.UUID) -> list[RgroupExtractionOut]:
    """The paper's readings in paper order (page, idx, then oldest request first)."""
    rows = await db.execute(
        _query(Segment.paper_id == paper_id).order_by(
            Segment.page, Segment.idx, RgroupExtraction.created_at, RgroupExtraction.prediction_id
        )
    )
    return [
        extraction_out(r, seg, status, named_on(index, page))
        for r, seg, status, page, index in rows.all()
    ]


async def for_prediction(db: AsyncSession, prediction: Prediction) -> RgroupExtractionOut:
    found = (
        await db.execute(_query(RgroupExtraction.prediction_id == prediction.id))
    ).one_or_none()
    if found is None:
        where = (
            await db.execute(
                select(Segment.page, Paper.rgroup_text_labels)
                .join(Paper, Paper.id == Segment.paper_id)
                .where(Segment.id == prediction.segment_id)
            )
        ).one_or_none()
        return none_out(
            prediction, named_on(where.rgroup_text_labels, where.page) if where else None
        )
    row, seg, status, page, index = found
    return extraction_out(row, seg, status, named_on(index, page))


async def for_export(db: AsyncSession, paper_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    """prediction id -> the rows an export writes for it (plain data: it travels pickled to the
    chem process). Only predictions with rows (a run that ended well)."""
    out: dict[uuid.UUID, dict] = {}
    for item in await for_paper(db, paper_id):
        if item.rows is None:
            continue
        out[item.prediction_id] = {
            "labels": item.labels,
            "rows": [r.model_dump() for r in item.rows],
            "truncated": item.truncated,
            "model": item.model,
            "model_version": item.model_version,
            "extracted_at": item.finished_at.isoformat() if item.finished_at else None,
        }
    return out


def available() -> bool:
    return get_settings().rgroup_enabled
