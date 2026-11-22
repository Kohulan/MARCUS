"""What runs by itself (owner decision 2026-11-22): a paper's annotation once its text is read,
and a scaffold's R-group rows once it is read and the paper's text is too.

The dispatcher (marcus.dispatcher.auto) asks for these with the planner's own requests
(request_annotation, request_rgroups), only where the feature is on and a worker serves the
queue (q.llm, q.rgroup); otherwise nothing is asked and the manual action stays. The API reads
the same candidates to tell a client that a run is about to start (`auto_pending`).

A candidate is asked for once: a paper that ever had an annotate step, or a prediction that
has an `rgroup_extractions` row (a failed one too), is never one again; a re-run is the user's.
Only work younger than `auto_window_s` counts (no backfill of old papers). Neither step is part
of the paper's read: neither keeps it busy nor counts in its progress (pipeline.in_paper_progress).

R-group rows: the newest prediction of the paper's engine per segment (the structure the paper
read), when it has a label the model can be asked for (not only unlabelled points, `*`).
"""

import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from marcus.core import rgroup_labels
from marcus.core.enums import PaperStatus, StepKind, StepStatus
from marcus.core.models import Annotation, Paper, Prediction, RgroupExtraction, Segment, Step
from marcus.core.settings import get_settings

BATCH = 20  # candidates asked for per pass
# "About to start": the few dispatcher passes (every 3 s, its consumer answer kept 30 s) after a
# candidate appeared. The API's `auto_pending` covers only this; after it, a run that did not
# start (the dispatcher skipped it) leaves the manual action, never a wait for nothing.
START_S = 20


def _since(within_s: int | None):
    seconds = get_settings().auto_window_s if within_s is None else within_s
    return func.now() - func.make_interval(0, 0, 0, 0, 0, 0, seconds)


def _live_paper():
    return (Paper.status != PaperStatus.DELETED.value, Paper.expires_at >= func.now())


def _text_read(paper_id):
    """The paper's done docling step (correlated on `paper_id`); filter on its end."""
    return select(Step.finished_at).where(
        Step.paper_id == paper_id,
        Step.kind == StepKind.DOCLING.value,
        Step.status == StepStatus.DONE.value,
    )


def annotation_query(
    paper_id: uuid.UUID | None = None, within_s: int | None = None, limit: int = BATCH
):
    """SELECT the ids of papers to annotate by themselves (oldest first), whose text was read
    within `within_s` (default auto_window_s)."""
    q = select(Paper.id).where(
        *_live_paper(),
        exists(_text_read(Paper.id).where(Step.finished_at > _since(within_s)).correlate(Paper)),
        ~exists(
            select(Step.id).where(Step.paper_id == Paper.id, Step.kind == StepKind.ANNOTATE.value)
        ),
        ~exists(select(Annotation.paper_id).where(Annotation.paper_id == Paper.id)),
    )
    if paper_id is not None:
        q = q.where(Paper.id == paper_id)
    return q.order_by(Paper.created_at, Paper.id).limit(limit)


def rgroup_query(
    paper_id: uuid.UUID | None = None, within_s: int | None = None, limit: int = BATCH
):
    """SELECT the ids of scaffold predictions to read by themselves (oldest paper first): the
    newest prediction of the paper's engine per segment, read (or its paper's text read) within
    `within_s` (default auto_window_s). The window comes first: only predictions made in it, or
    of papers whose text was read in it, are looked at for the newest (any newer prediction is
    in the window too, so the newest is the same)."""
    since = _since(within_s)
    recent_text = exists(_text_read(Paper.id).where(Step.finished_at > since).correlate(Paper))
    newest = (
        select(Prediction.id, Prediction.rgroups, Prediction.created_at, Segment.paper_id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .where(
            Prediction.engine == Paper.engine,
            *_live_paper(),
            (Prediction.created_at > since) | recent_text,
        )
        .order_by(Prediction.segment_id, Prediction.created_at.desc(), Prediction.id)
        .ext(distinct_on(Prediction.segment_id))
    )
    if paper_id is not None:
        newest = newest.where(Segment.paper_id == paper_id)
    newest = newest.subquery()
    text = _text_read(newest.c.paper_id).correlate(newest)
    return (
        select(newest.c.id)
        .join(Paper, Paper.id == newest.c.paper_id)
        .where(
            # rgroup_labels.drawn_labels in SQL: a label the model can be asked for (not only
            # `*`), the rule request_rgroups refuses by
            func.cardinality(func.array_remove(newest.c.rgroups, rgroup_labels.UNLABELLED)) > 0,
            exists(text.where((Step.finished_at > since) | (newest.c.created_at > since))),
            ~exists(
                select(RgroupExtraction.prediction_id).where(
                    RgroupExtraction.prediction_id == newest.c.id
                )
            ),
        )
        .order_by(Paper.created_at, newest.c.id)
        .limit(limit)
    )


_FLAGS = {StepKind.ANNOTATE: "annotate_enabled", StepKind.RGROUPS: "rgroup_enabled"}
_QUERIES = {StepKind.ANNOTATE: annotation_query, StepKind.RGROUPS: rgroup_query}


def candidates_query(
    kind: StepKind,
    paper_id: uuid.UUID | None = None,
    within_s: int | None = None,
    limit: int = BATCH,
):
    """The one rule of what runs by itself: None where the feature is off, else the SELECT of
    its candidates (annotate: paper ids; rgroups: prediction ids). The dispatcher asks with the
    default window (and checks that a worker serves the queue); the API's `auto_pending` asks
    with START_S."""
    if not getattr(get_settings(), _FLAGS[kind]):
        return None
    return _QUERIES[kind](paper_id, within_s, limit)


def annotation_candidates(session: Session, paper_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    return list(session.execute(annotation_query(paper_id)).scalars())


def rgroup_candidates(session: Session, paper_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    return list(session.execute(rgroup_query(paper_id)).scalars())
