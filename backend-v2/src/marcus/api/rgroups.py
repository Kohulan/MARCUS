"""Read side of the R-group rows: the response shape and the rows exports use."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.schemas import RgroupExtractionOut, RgroupRow
from marcus.core.enums import StepStatus
from marcus.core.models import Prediction, RgroupExtraction, Segment, Step
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
    row: RgroupExtraction, segment_id: uuid.UUID, step_status: str | None
) -> RgroupExtractionOut:
    rows = _rows(row)
    return RgroupExtractionOut(
        prediction_id=row.prediction_id,
        segment_id=segment_id,
        status=_status(row, step_status),  # type: ignore[arg-type]
        labels=list(row.labels),
        rows=[RgroupRow(**r) for r in rows] if rows is not None else None,
        truncated=row.truncated,
        error=row.error if row.status == "failed" else None,
        model=row.model,
        model_version=row.model_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
    )


def none_out(prediction: Prediction) -> RgroupExtractionOut:
    """A prediction never asked for."""
    return RgroupExtractionOut(
        prediction_id=prediction.id,
        segment_id=prediction.segment_id,  # type: ignore[arg-type]
        status="none",
        labels=list(prediction.rgroups or []),
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
        select(RgroupExtraction, Prediction.segment_id, Step.status)
        .join(Prediction, Prediction.id == RgroupExtraction.prediction_id)
        .join(Segment, Segment.id == Prediction.segment_id)
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
    return [extraction_out(r, seg, status) for r, seg, status in rows.all()]


async def for_prediction(db: AsyncSession, prediction: Prediction) -> RgroupExtractionOut:
    found = (
        await db.execute(_query(RgroupExtraction.prediction_id == prediction.id))
    ).one_or_none()
    if found is None:
        return none_out(prediction)
    row, seg, status = found
    return extraction_out(row, seg, status)


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
