"""Daily page quota of an API-key owner (one definition for the upload routes and the CLI).

Pages used today (UTC) = pages of the owner's papers created today whose page count is known,
plus 1 for each such paper still being checked (count unknown yet), plus 1 per image job.
After `check_pdf` nothing else is enforced: one upload may overshoot by its own page count.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select

from marcus.core.enums import PaperStatus
from marcus.core.models import ImageJob, Paper


def utc_day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def pages_used_stmt(owner_id: uuid.UUID, since: datetime | None = None) -> Select:
    """A SELECT returning the owner's pages used since `since` (default: today, UTC)."""
    since = since or utc_day_start()
    known = (
        select(func.coalesce(func.sum(Paper.pages), 0))
        .where(Paper.owner_id == owner_id, Paper.created_at >= since, Paper.pages.is_not(None))
        .scalar_subquery()
    )
    unknown = (
        select(func.count())
        .select_from(Paper)
        .where(
            Paper.owner_id == owner_id,
            Paper.created_at >= since,
            Paper.pages.is_(None),
            Paper.status == PaperStatus.CHECKING.value,
        )
        .scalar_subquery()
    )
    images = (
        select(func.count())
        .select_from(ImageJob)
        .where(ImageJob.owner_id == owner_id, ImageJob.created_at >= since)
        .scalar_subquery()
    )
    return select(known + unknown + images)
