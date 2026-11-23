"""Daily page quota of an API-key owner (one definition for the upload routes and the CLI).

Pages of today (UTC), in two parts:

- used: pages of the owner's papers created today whose page count is known, plus 1 per image
  job;
- reserved: `max_pages` for each such paper still being checked (count unknown yet).

An upload is refused when used + reserved reaches the quota. A paper being checked holds the
most pages it can have (check_pdf accepts 1..max_pages) until check_pdf counts them, so
uploads made while earlier papers wait for their check never pass on an undercount (security
scan 2026-11-23 F3: at 1 page per checking paper, a key with quota 2000 got ~15,000 pages
accepted). One upload may still overshoot by its own page count.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select

from marcus.core.enums import PaperStatus
from marcus.core.models import ImageJob, Paper
from marcus.core.settings import get_settings


def utc_day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def pages_used_stmt(owner_id: uuid.UUID, since: datetime | None = None) -> Select:
    """A SELECT returning one row (used, reserved): the owner's pages since `since` (default:
    today, UTC); see the module docstring."""
    since = since or utc_day_start()
    known = (
        select(func.coalesce(func.sum(Paper.pages), 0))
        .where(Paper.owner_id == owner_id, Paper.created_at >= since, Paper.pages.is_not(None))
        .scalar_subquery()
    )
    checking = (
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
    reserved = checking * get_settings().max_pages
    return select((known + images).label("used"), reserved.label("reserved"))
