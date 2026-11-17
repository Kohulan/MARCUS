"""`GET /queue`: where my active papers stand, and a rough wait estimate.

This is an estimate, not a promise (the dispatcher is fair, not first-in-first-out):

- For each of my active papers and each queue it has waiting (pending/queued) steps in,
  `steps_ahead_by_queue[q]` = waiting steps in `q`, of any owner, created before this
  paper's oldest waiting step in `q`.
- `median_s[q]` = median of (finished_at - started_at) over `q`'s steps finished in the last
  hour; `DEFAULT_STEP_S` when there are none.
- A paper's `estimate_s` = sum over q of steps_ahead[q] x median_s[q].
- The top-level `estimate_s` = sum over q of (max steps_ahead[q] over my papers) x
  median_s[q]: the work in front of all my papers, without counting a shared step twice.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from marcus.api.deps import current_owner
from marcus.api.schemas import QueueOut, QueuePaper
from marcus.core.db import get_db
from marcus.core.enums import PaperStatus, StepStatus
from marcus.core.models import Owner, Paper, Step

router = APIRouter()

DEFAULT_STEP_S = 5.0
MEDIAN_WINDOW = timedelta(hours=1)
WAITING = (StepStatus.PENDING.value, StepStatus.QUEUED.value)
ACTIVE_PAPER = (PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value)


async def _medians(db: AsyncSession, queues: set[str]) -> dict[str, float]:
    if not queues:
        return {}
    secs = func.extract("epoch", Step.finished_at - Step.started_at)
    rows = await db.execute(
        select(Step.queue, func.percentile_cont(0.5).within_group(secs))
        .where(
            Step.queue.in_(queues),
            Step.status == StepStatus.DONE.value,
            Step.started_at.is_not(None),
            Step.finished_at >= datetime.now(UTC) - MEDIAN_WINDOW,
        )
        .group_by(Step.queue)
    )
    return {q: float(m) for q, m in rows.all() if m is not None}


@router.get("/queue", response_model=QueueOut)
async def queue_position(
    owner: Owner = Depends(current_owner), db: AsyncSession = Depends(get_db)
) -> QueueOut:
    papers = list(
        (
            await db.execute(
                select(Paper.id)
                .where(
                    Paper.owner_id == owner.id,
                    Paper.status.in_(ACTIVE_PAPER),
                    Paper.expires_at >= func.now(),  # expired = gone for the client (404)
                )
                .order_by(Paper.created_at, Paper.id)
            )
        ).scalars()
    )
    if not papers:
        return QueueOut(papers=[], estimate_s=0.0)

    mine = (
        select(Step.paper_id, Step.queue, func.min(Step.created_at).label("oldest"))
        .where(Step.paper_id.in_(papers), Step.status.in_(WAITING))
        .group_by(Step.paper_id, Step.queue)
        .subquery()
    )
    other = aliased(Step)
    rows = await db.execute(
        select(mine.c.paper_id, mine.c.queue, func.count(other.id))
        .select_from(mine)
        .outerjoin(
            other,
            and_(
                other.queue == mine.c.queue,
                other.status.in_(WAITING),
                other.created_at < mine.c.oldest,
            ),
        )
        .group_by(mine.c.paper_id, mine.c.queue)
    )
    ahead: dict = {pid: {} for pid in papers}
    for pid, queue, n in rows.all():
        ahead[pid][queue] = int(n)

    queues = {q for per in ahead.values() for q in per}
    medians = await _medians(db, queues)

    def cost(q: str, n: int) -> float:
        return n * medians.get(q, DEFAULT_STEP_S)

    out = [
        QueuePaper(
            id=pid,
            steps_ahead_by_queue=per,
            estimate_s=round(sum(cost(q, n) for q, n in per.items()), 1),
        )
        for pid, per in ahead.items()
    ]
    worst = {q: max(per.get(q, 0) for per in ahead.values()) for q in queues}
    total = round(sum(cost(q, n) for q, n in worst.items()), 1)
    return QueueOut(papers=out, estimate_s=total)
