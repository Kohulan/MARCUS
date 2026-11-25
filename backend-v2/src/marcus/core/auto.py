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

R-group rows: the scaffold prediction the card shows (agreement.shown_prediction: the frozen
one, the majority's, the paper engine's valid one, else the newest), whichever engine made it,
when it has a label the model can be asked for (not only unlabelled points, `*`). Until
2026-11-25 only the paper engine's prediction was read: a scaffold DECIMER could not read but
MolScribe could got no rows (live test, JNP 10.1021/acs.jnatprod.6c00411). SQL narrows (one
prediction per segment, ordered as the pick would be without a majority); Python decides
(shown_only). Built structures (Markush Phase 3) are never candidates.
"""

import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from marcus.core import rgroup_labels
from marcus.core.agreement import shown_prediction
from marcus.core.built import built_clause
from marcus.core.enums import PaperStatus, StepKind, StepStatus
from marcus.core.models import (
    Annotation,
    Curation,
    Paper,
    Prediction,
    RgroupExtraction,
    Segment,
    Step,
)
from marcus.core.settings import get_settings

BATCH = 20  # candidates asked for per pass
SCAN_FACTOR = 5  # SQL rows looked at per candidate wanted (Python keeps the shown ones)
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
    """SELECT the ids of scaffold predictions to read by themselves (oldest paper first): per
    segment the prediction its card likely shows (the frozen one, a valid one of the paper's
    engine, a valid one, the newest; shown_only checks it), read (or its paper's text read)
    within `within_s` (default auto_window_s). The window comes first: only predictions made in
    it, or of papers whose text was read in it, are looked at."""
    since = _since(within_s)
    recent_text = exists(_text_read(Paper.id).where(Step.finished_at > since).correlate(Paper))
    newest = (
        select(Prediction.id, Prediction.rgroups, Prediction.created_at, Segment.paper_id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .outerjoin(Curation, Curation.segment_id == Segment.id)
        .where(
            *_live_paper(),
            ~built_clause(),
            (Prediction.created_at > since) | recent_text,
        )
        .order_by(
            Prediction.segment_id,
            (Prediction.id == Curation.shown_prediction_id).desc().nulls_last(),
            Prediction.valid.desc(),
            (Prediction.valid & (Prediction.engine == Paper.engine)).desc(),
            Prediction.created_at.desc(),
            Prediction.id,
        )
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


def shown_only(session: Session, prediction_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Of `prediction_ids`, in order, those their segment's card shows (shown_prediction)."""
    if not prediction_ids:
        return []
    segs = select(Prediction.segment_id).where(Prediction.id.in_(prediction_ids))
    rows = session.execute(
        select(Prediction, Paper.engine, Curation.shown_prediction_id)
        .join(Segment, Segment.id == Prediction.segment_id)
        .join(Paper, Paper.id == Segment.paper_id)
        .outerjoin(Curation, Curation.segment_id == Segment.id)
        .where(Prediction.segment_id.in_(segs))
        .order_by(Prediction.created_at.desc(), Prediction.id)
    ).all()
    by_segment: dict[uuid.UUID, list] = {}
    context: dict[uuid.UUID, tuple] = {}
    for pred, engine, frozen in rows:
        by_segment.setdefault(pred.segment_id, []).append(pred)
        context[pred.segment_id] = (engine, frozen)
    shown = set()
    for seg_id, preds in by_segment.items():
        engine, frozen = context[seg_id]
        pick = shown_prediction(preds, engine, frozen)
        if pick is not None:
            shown.add(pick.id)
    return [pid for pid in prediction_ids if pid in shown]


def candidates(
    session: Session,
    kind: StepKind,
    paper_id: uuid.UUID | None = None,
    within_s: int | None = None,
    limit: int = BATCH,
) -> list[uuid.UUID] | None:
    """The candidates themselves: None where the feature is off; R-group ones only those their
    card shows (shown_only)."""
    if kind == StepKind.RGROUPS:
        query = candidates_query(kind, paper_id, within_s, limit * SCAN_FACTOR)
        if query is None:
            return None
        return shown_only(session, list(session.execute(query).scalars()))[:limit]
    query = candidates_query(kind, paper_id, within_s, limit)
    return None if query is None else list(session.execute(query).scalars())


def annotation_candidates(session: Session, paper_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    return list(session.execute(annotation_query(paper_id)).scalars())


def rgroup_candidates(session: Session, paper_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    return shown_only(
        session, list(session.execute(rgroup_query(paper_id, None, BATCH * SCAN_FACTOR)).scalars())
    )[:BATCH]
