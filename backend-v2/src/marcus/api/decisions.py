"""A decision on a main-figure structure goes to its whole linked group.

A main-figure structure and its repeats on other pages are one compound (marcus.core.main_figure).
A decision (accepted, rejected, back to unchecked) on the main card, alone or in a bulk action,
is written on every repeat too, in the same transaction, and each repeat is marked as having
inherited it (InheritedStatus: the main segment it came from). While a repeat is no longer a
repeat of that main structure, its inherited status reads as unchecked (api.read). A decision on
a structure's own card is its own: its inherited mark goes. A repeat decided in the same call
keeps its own decision. There is no undo or event log in MARCUS to record the group change in.

A decision freezes the structure it was made on (review finding, phase B): an accept or reject
without a structure of its own keeps the prediction the card showed
(Curation.shown_prediction_id; marcus.core.agreement.pick_prediction), so engines landing later
never change a decided card, its export or its links. The browser names the prediction it
showed (`shown`, checked by the routes to be the segment's own): a prediction that landed after
the card was drawn is never the one decided on. Without it (an older client, an API-key user)
it is the server's pick when the decision lands. A card already frozen keeps its prediction. A
repeat that inherits a decision freezes its own shown prediction (the server's pick); that one
holds only with the inherited status: while it is stale (api.read) the card shows the default
pick, the links never use it, and a decision on the card itself drops it. Back to unchecked,
or a curated structure, clears it.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.read import inherited_of, load_segments, main_figure_page, repeat_links
from marcus.core.agreement import pick_prediction
from marcus.core.main_figure import ACCEPTED, REJECTED, groups_of
from marcus.core.models import Curation, InheritedStatus, Paper, Prediction


async def record_decisions(
    db: AsyncSession,
    paper: Paper,
    decided: dict[uuid.UUID, str],
    shown: dict[uuid.UUID, uuid.UUID] | None = None,
) -> None:
    """After the decided segments' own curations were set in `db` (segment id -> status): their
    shown prediction is frozen (`shown`: segment id -> the prediction its card showed, each the
    segment's own), their inherited marks go, and a main-figure structure's status goes to its
    repeats, marked inherited. The links are those after the write (an edit with the decision counts). 503
    (HTTPException) when the chem process cannot link them: the caller rolls back."""
    if not decided:
        return
    await db.flush()
    # A structure decided on its own card loses its inherited mark, and the structure frozen
    # with that inherited decision (it was not the one this card showed, see api.read).
    was_inherited = set(
        await db.scalars(
            delete(InheritedStatus)
            .where(InheritedStatus.segment_id.in_(decided))
            .returning(InheritedStatus.segment_id)
        )
    )
    segments, curations, predictions = await load_segments(db, paper.id)
    for sid, status in decided.items():
        if sid in curations:
            if sid in was_inherited:
                curations[sid].shown_prediction_id = None
            seen = (shown or {}).get(sid)
            freeze(curations[sid], status, paper.engine, predictions.get(sid, []), seen)
    main_page = await main_figure_page(db, paper.id)
    if main_page is None:
        return
    inherited = (await inherited_of(db, [paper.id])).get(paper.id, {})
    links = await repeat_links(
        paper, main_page, segments, curations, predictions, strict=True, inherited=inherited
    )
    groups = groups_of(links or {})
    now = datetime.now(UTC)
    for main, status in decided.items():
        for repeat in groups.get(main, []):
            if repeat in decided:
                continue
            cur = curations.get(repeat)
            if cur is None:
                cur = Curation(segment_id=repeat)
                db.add(cur)
            cur.status = status
            cur.updated_at = now
            freeze(cur, status, paper.engine, predictions.get(repeat, []))
            await db.execute(
                pg_insert(InheritedStatus)
                .values(segment_id=repeat, main_id=main)
                .on_conflict_do_update(
                    index_elements=[InheritedStatus.segment_id], set_={"main_id": main}
                )
            )


def freeze(
    cur: Curation,
    status: str,
    paper_engine: str,
    predictions: list[Prediction],
    seen: uuid.UUID | None = None,
) -> None:
    """Keep (accepted, rejected) or clear (unchecked, a curated structure) the prediction the
    card shows: one already frozen (it is the one shown), else `seen` (the one the browser
    showed), else the server's pick now."""
    if status not in (ACCEPTED, REJECTED) or cur.smiles or cur.molfile:
        cur.shown_prediction_id = None
        return
    ids = {p.id for p in predictions}
    if cur.shown_prediction_id in ids:
        return
    if seen in ids:
        cur.shown_prediction_id = seen
        return
    pick = pick_prediction(predictions, paper_engine)
    cur.shown_prediction_id = pick.id if pick is not None else None
