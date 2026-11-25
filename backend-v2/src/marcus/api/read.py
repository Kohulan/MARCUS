"""Read helpers shared by the route modules (routes never import each other)."""

import hashlib
import logging
import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Collection
from typing import NamedTuple, TypeVar

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.chem import inchikeys
from marcus.api.chempool import CHEM
from marcus.api.schemas import CurationOut, PaperSummary, PredictionOut, SegmentOut, StepOut
from marcus.core import compound_ids, storage
from marcus.core.agreement import COUNTED as AGREE_ENGINES
from marcus.core.agreement import SLOTS as AGREE_SLOTS
from marcus.core.agreement import majority, newest_by_engine, pick_prediction
from marcus.core.enums import (
    FINISHED_STEPS,
    Engine,
    StepKind,
    StepStatus,
)
from marcus.core.main_figure import (
    CountFix,
    Entry,
    count_fix,
    id_conflicts,
    link_repeats,
    stale_members,
)
from marcus.core.models import (
    Curation,
    DrawingFlag,
    InheritedStatus,
    MainFigure,
    Paper,
    Prediction,
    Segment,
    Step,
)
from marcus.core.picks import candidate_clause
from marcus.core.pipeline import (
    ACTIVE,
    PAGE_KINDS,
    in_paper_progress,
    in_paper_steps,
    is_background,
    page_step_order,
)
from marcus.core.rgroup_labels import shown_labels

log = logging.getLogger(__name__)

IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600"}


class PaperCounts(NamedTuple):
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int
    failed: int
    # the read's coarse progress, as the workspace reads it from the steps (readingProgress.ts)
    pages_read: int = 0  # pages whose newest render_page/segment_page step has ended
    structures_total: int = 0  # structures with an OCSR step
    structures_read: int = 0  # of those, read once, or with nothing in flight
    text_read: bool | None = None  # every docling step ended; None: it has none (paper_summary)
    check_started: bool = False  # a check_pdf step runs or ended
    rereading: bool = False  # busy only with OCSR runs on structures already read


async def waiting_ocsr_step(db: AsyncSession, where, engine: Engine) -> uuid.UUID | None:
    """The OCSR step of `engine` still waiting or running for `where` (a segment's or an image
    job's steps): a repeat click gets it back instead of queueing another one. A background
    step is left to pipeline.request_ocsr, which makes it the paper's own."""
    return await db.scalar(
        select(Step.id)
        .where(
            where,
            Step.kind == StepKind.OCSR.value,
            Step.engine == engine.value,
            Step.status.in_(ACTIVE),
            ~is_background(),
        )
        .limit(1)
    )


def _failed_structure():
    """True for a segment the workspace shows as Failed (frontend cardState): no decision, no
    valid prediction, no OCSR step in flight, and its newest OCSR step failed."""
    ocsr = and_(Step.segment_id == Segment.id, Step.kind == StepKind.OCSR.value, ~is_background())
    newest = (
        select(Step.status)
        .where(ocsr)
        .order_by(Step.created_at.desc(), Step.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    return and_(
        or_(Curation.status.is_(None), Curation.status.not_in(("accepted", "rejected"))),
        ~exists().where(Prediction.segment_id == Segment.id, Prediction.valid.is_(True)),
        ~exists().where(ocsr, Step.status.in_(ACTIVE)),
        newest == StepStatus.FAILED.value,
    )


async def paper_counts(
    db: AsyncSession, paper_ids: list[uuid.UUID], fix: CountFix | None = None
) -> dict[uuid.UUID, PaperCounts]:
    """Structure, failure and progress counts per paper: two queries, whatever the number of
    papers (one over the segments, one over the steps).

    `fix`: the linked groups of main-figure structures and their repeats (list_count_fix,
    segments_out) count once, under the group's status (core.main_figure.group_status), as the
    workspace shows them: repeats are not counted, a main with an accepted repeat counts as
    accepted, a rejected main with a repeat not rejected as to review; an inherited status that
    no longer holds (stale) as to review.
    structures = segments; accepted / rejected = curations with that status; failed = the
    undecided ones whose read failed (_failed_structure); to_review = the rest (every segment
    has a curation row). failed_pages = distinct pages whose newest
    render_page or segment_page step, across both kinds (the order retry_page uses), is failed.
    A retry in flight (pending, queued, running) is the newest step, so the page is not counted
    while it runs; retry_page itself still sees the old failure standing and answers "busy".
    The progress fields are PaperCounts'."""
    if not paper_ids:
        return {}
    fix = fix or CountFix()
    accepted = Curation.status == "accepted"
    rejected = Curation.status == "rejected"
    failed = _failed_structure()
    if fix.stale:  # an inherited status that no longer holds: to review
        accepted = and_(accepted, Segment.id.not_in(fix.stale))
        rejected = and_(rejected, Segment.id.not_in(fix.stale))
    if fix.promote:
        accepted = or_(accepted, Segment.id.in_(fix.promote))
        rejected = and_(rejected, Segment.id.not_in(fix.promote))
        failed = and_(failed, Segment.id.not_in(fix.promote))
    if fix.unreject:
        rejected = and_(rejected, Segment.id.not_in(fix.unreject))
    seg_rows = await db.execute(
        select(
            Segment.paper_id,
            func.count(),
            func.count().filter(accepted),
            func.count().filter(rejected),
            func.count().filter(failed),
        )
        .select_from(Segment)
        .outerjoin(Curation, Curation.segment_id == Segment.id)
        .where(
            Segment.paper_id.in_(paper_ids),
            ~candidate_clause(),  # pick mode: a box not picked is no structure
            *([Segment.id.not_in(fix.hidden)] if fix.hidden else []),
        )
        .group_by(Segment.paper_id)
    )
    progress = {row.paper_id: row for row in (await db.execute(_step_counts(paper_ids))).all()}
    out = {}
    for pid in paper_ids:
        row = progress.get(pid)
        if row is None:
            out[pid] = PaperCounts(0, 0, 0, 0, 0, 0)
            continue
        active = row.active
        out[pid] = PaperCounts(
            0, 0, 0, 0, row.failed_pages or 0, 0,
            pages_read=row.pages_read or 0,
            structures_total=row.structures_total or 0,
            structures_read=row.structures_read or 0,
            text_read=row.docling_ended == row.docling if row.docling else None,
            check_started=bool(row.check_started),
            rereading=active > 0 and (row.rereads or 0) == active,
        )  # fmt: skip
    for pid, total, accepted, rejected, broken in seg_rows.all():
        rest = total - accepted - rejected - broken
        out[pid] = out[pid]._replace(
            structures=total, accepted=accepted, rejected=rejected, to_review=rest, failed=broken
        )
    return out


def _step_counts(paper_ids: list[uuid.UUID]):
    """One row per paper with steps: the step counts paper_counts needs, from three grouped
    subqueries over its steps (all of them, each page's newest page step, each structure's
    OCSR steps) joined on the paper."""
    active = Step.status.in_(ACTIVE)
    ended = Step.status.in_(FINISHED_STEPS)
    kind = Step.kind
    steps = (
        select(
            Step.paper_id,
            func.count().filter(active).label("active"),
            func.count().filter(kind == StepKind.DOCLING.value).label("docling"),
            func.count().filter(ended, kind == StepKind.DOCLING.value).label("docling_ended"),
            func.count()
            .filter(ended | (Step.status == StepStatus.RUNNING.value))
            .filter(kind == StepKind.CHECK_PDF.value)
            .label("check_started"),
        )
        .where(Step.paper_id.in_(paper_ids), in_paper_progress())
        .group_by(Step.paper_id)
        .subquery()
    )
    newest = (
        select(Step.paper_id, Step.page, Step.status)
        .ext(distinct_on(Step.paper_id, Step.page))
        .where(
            Step.paper_id.in_(paper_ids),
            Step.page.is_not(None),
            Step.kind.in_(PAGE_KINDS),
        )
        .order_by(Step.paper_id, Step.page, *page_step_order(), Step.id)
        .subquery()
    )
    pages = (
        select(
            newest.c.paper_id,
            func.count().filter(newest.c.status == StepStatus.FAILED.value).label("failed_pages"),
            func.count().filter(newest.c.status.in_(FINISHED_STEPS)).label("pages_read"),
        )
        .group_by(newest.c.paper_id)
        .subquery()
    )
    per_structure = (
        select(
            Step.paper_id,
            func.bool_or(Step.status == StepStatus.DONE.value).label("read"),
            func.count().filter(active).label("busy"),
        )
        .where(
            Step.paper_id.in_(paper_ids),
            Step.kind == StepKind.OCSR.value,
            Step.segment_id.is_not(None),
            ~is_background(),
        )
        .group_by(Step.paper_id, Step.segment_id)
        .subquery()
    )
    read, busy = per_structure.c.read, per_structure.c.busy
    structures = (
        select(
            per_structure.c.paper_id,
            func.count().label("structures_total"),
            func.count().filter(read | (busy == 0)).label("structures_read"),
            func.sum(busy).filter(read).label("rereads"),
        )
        .group_by(per_structure.c.paper_id)
        .subquery()
    )
    return select(
        steps.c.paper_id,
        steps.c.active,
        steps.c.docling,
        steps.c.docling_ended,
        steps.c.check_started,
        pages.c.failed_pages,
        pages.c.pages_read,
        structures.c.structures_total,
        structures.c.structures_read,
        structures.c.rereads,
    ).select_from(
        steps.outerjoin(pages, pages.c.paper_id == steps.c.paper_id).outerjoin(
            structures, structures.c.paper_id == steps.c.paper_id
        )
    )


def paper_summary(paper: Paper, counts: PaperCounts) -> PaperSummary:
    fields = PaperSummary.model_fields.keys() - PaperCounts._fields
    values = counts._asdict()
    if counts.text_read is None:  # no docling step (a paper read before it existed): its pages
        values["text_read"] = paper.pages is not None and counts.pages_read >= paper.pages
    return PaperSummary(**{f: getattr(paper, f) for f in fields}, **values)


async def steps_by_status(db: AsyncSession, paper_id: uuid.UUID) -> dict[str, int]:
    """The paper's steps per status, as steps_out lists them (annotate and rgroups steps aside:
    they are not part of its read; background OCSR steps in)."""
    rows = await db.execute(
        select(Step.status, func.count())
        .where(Step.paper_id == paper_id, in_paper_steps())
        .group_by(Step.status)
    )
    return {status: n for status, n in rows.all()}


async def load_segments(db: AsyncSession, paper_id: uuid.UUID, *, candidates: bool = False):
    """Segments in (page, idx) order, curation per segment, predictions per segment (newest
    first). Three queries, whatever the number of segments. Pick-mode candidates
    (marcus.core.picks) only with `candidates` (the page drawing them): every structure reader
    (export, decisions, links) leaves them out."""
    counted = [] if candidates else [~candidate_clause()]
    segments = list(
        (
            await db.execute(
                select(Segment)
                .where(Segment.paper_id == paper_id, *counted)
                .order_by(Segment.page, Segment.idx)
            )
        ).scalars()
    )
    curations = {
        c.segment_id: c
        for c in (
            await db.execute(
                select(Curation)
                .join(Segment, Segment.id == Curation.segment_id)
                .where(Segment.paper_id == paper_id)
            )
        ).scalars()
    }
    predictions: dict[uuid.UUID, list[Prediction]] = defaultdict(list)
    for p in (
        await db.execute(
            select(Prediction)
            .join(Segment, Segment.id == Prediction.segment_id)
            .where(Segment.paper_id == paper_id)
            .order_by(Prediction.created_at.desc(), Prediction.id)
        )
    ).scalars():
        predictions[p.segment_id].append(p)
    return segments, curations, predictions


_Structure = TypeVar("_Structure", CurationOut, PredictionOut)


def named_on(index: dict | None, page: int) -> list[str] | None:
    """The R-group labels a paper's page names (papers.rgroup_text_labels), None without an
    index."""
    return None if index is None else index.get(str(page), [])


def structure_out(model: type[_Structure], row: object, named: list[str] | None) -> _Structure:
    """A prediction or curation for the API, with the R-group labels shown for it: those its
    page names (marcus.core.rgroup_labels.shown_labels), `placeholder` from all of them. Every
    endpoint that returns a paper's structure goes through here."""
    out = model.model_validate(row)
    out.rgroups = shown_labels(out.rgroups, named)
    return out


def shown_source(
    paper_engine: str,
    curation: Curation | None,
    predictions: list[Prediction],
    use_frozen: bool = True,
) -> tuple[str, str] | None:
    """("smiles" | "molfile", value) of the structure a segment shows, as the export picks it
    (curated, else pick_prediction), whatever its status; None without one, and for an R-group
    scaffold (it stands for several compounds). `predictions`: the segment's, newest first.
    Rows with only the columns read here do as well (_load_light). The one pick the linking
    uses: a new default pick plugs in here. `use_frozen` False: the decided structure
    (Curation.shown_prediction_id) is not taken (an inherited decision's: see link_entries)."""
    if curation is not None and (curation.smiles or curation.molfile):
        if curation.rgroups:
            return None
        return ("smiles", curation.smiles) if curation.smiles else ("molfile", curation.molfile)
    frozen = curation.shown_prediction_id if curation is not None and use_frozen else None
    pick = pick_prediction(predictions, paper_engine, frozen)
    if pick is None or not pick.smiles or pick.rgroups:
        return None
    return "smiles", pick.smiles


# InChIKeys already computed, per (kind, sha256 of the value): a paper's live refreshes ask the
# chem process only for structures it has not seen. Bounded, oldest out first.
_KEYS: OrderedDict[tuple[str, str], str | None] = OrderedDict()
KEY_CACHE_MAX = 20_000
# Structures per chem-process trip: each trip stays well inside chempool.TIMEOUT_S, and its keys
# are cached at once, so a cold cache fills over a few reads even when one trip fails.
CHEM_CHUNK = 200


def _remember(name: tuple[str, str], key: str | None) -> None:
    _KEYS[name] = key
    _KEYS.move_to_end(name)
    while len(_KEYS) > KEY_CACHE_MAX:
        _KEYS.popitem(last=False)


async def _known_keys(items: list[tuple[str, str]]) -> dict[tuple[str, str], str | None]:
    """InChIKey per (kind, value) of `items` that is known: cached, or computed now in trips of
    CHEM_CHUNK structures. Stops at the first trip the chem process cannot take (busy, timeout):
    the items not computed by then are missing from the answer (what was computed is cached)."""
    known: dict[tuple[str, str], str | None] = {}
    todo: dict[tuple[str, str], tuple[str, str]] = {}
    for item in items:
        name = (item[0], hashlib.sha256(item[1].encode()).hexdigest())
        if name in _KEYS:
            known[item] = _KEYS[name]
            _KEYS.move_to_end(name)
        else:
            todo.setdefault(name, item)
    pending = list(todo.items())
    for start in range(0, len(pending), CHEM_CHUNK):
        chunk = pending[start : start + CHEM_CHUNK]
        try:
            keys = await CHEM.run(inchikeys, [item for _, item in chunk])
        except HTTPException:
            log.warning("inchikeys: chem process busy, %d left", len(pending) - start)
            break
        for (name, item), key in zip(chunk, keys, strict=True):
            _remember(name, key)
            known[item] = key
    return known


async def main_figure_page(db: AsyncSession, paper_id: uuid.UUID) -> int | None:
    """The page (0-based) marked as the paper's main figure; None: none."""
    return await db.scalar(select(MainFigure.page).where(MainFigure.paper_id == paper_id))


# The compound IDs and names of a paper's text (marcus.core.compound_ids.figure_labels), per
# (paper id, the text file's mtime and size): each paper's text is read once per API process.
_LABELS: OrderedDict[tuple, tuple] = OrderedDict()
LABELS_CACHE_MAX = 256
NO_LABELS: tuple[dict, dict] = ({}, {})


async def figure_labels(paper_id: uuid.UUID, strict: bool = False) -> tuple[dict, dict] | None:
    """(ID boxes per page, compound ID -> name) from the paper's Docling text, read in the chem
    process (JSON parsing holds the GIL). Empty without a text file. When the chem process is
    busy: 503 if `strict` (an export), else None (a read: not known yet; not cached)."""
    path = storage.text_path(paper_id)
    try:
        stat = path.stat()
    except OSError:
        return NO_LABELS
    key = (paper_id, stat.st_mtime_ns, stat.st_size)
    if key in _LABELS:
        _LABELS.move_to_end(key)
        return _LABELS[key]
    try:
        labels = await CHEM.run(compound_ids.labels_from_file, str(path))
    except HTTPException:
        if strict:
            raise
        log.warning("compound IDs skipped: chem process busy")
        return None
    _LABELS[key] = labels
    while len(_LABELS) > LABELS_CACHE_MAX:
        _LABELS.popitem(last=False)
    return labels


def segment_ids(segments: list[Segment], boxes: dict) -> dict[uuid.UUID, str]:
    """segment id -> the compound ID printed by its drawing (compound_ids.read_ids, each page's
    crops together); segments without one are left out."""
    by_page: dict[int, list[Segment]] = {}
    for seg in segments:
        by_page.setdefault(seg.page, []).append(seg)
    out = {}
    for page, segs in by_page.items():
        found = compound_ids.read_ids([s.bbox for s in segs], boxes.get(page, []))
        out.update({s.id: cid for s, cid in zip(segs, found, strict=True) if cid is not None})
    return out


async def repeat_links(
    paper: Paper,
    main_page: int | None,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    strict: bool = False,
    known: dict[tuple[str, str], str | None] | None = None,
    compound_id_of: dict[uuid.UUID, str] | None = None,
    inherited: Collection[uuid.UUID] = (),
) -> dict[uuid.UUID, uuid.UUID] | None:
    """repeat segment id -> its main-figure segment id (marcus.core.main_figure); empty
    without a main figure (`main_page` None). `segments` in (page, idx) order; `known`: keys
    already asked for (_known_keys), else asked for here. A key missing (the chem process
    busy): 503 if `strict` (an export must not count a compound twice), else None (a read: the
    links are not ready). A repeat also links by the compound ID printed by its drawing
    (`compound_id_of`: segment_ids; read here from the paper's text when not given), where one
    of the two has no InChIKey."""
    if main_page is None:
        return {}
    entries = await link_entries(
        paper, segments, curations, predictions, strict, known, compound_id_of, inherited
    )
    return None if entries is None else link_repeats(entries, main_page)


async def link_entries(
    paper: Paper,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    strict: bool = False,
    known: dict[tuple[str, str], str | None] | None = None,
    compound_id_of: dict[uuid.UUID, str] | None = None,
    inherited: Collection[uuid.UUID] = (),
) -> list[Entry] | None:
    """The marcus.core.main_figure entries of the segments (InChIKey of the structure shown,
    compound ID), as repeat_links takes them; None when not ready (repeat_links). `inherited`:
    structures with an inherited status (inherited_of). Their decided structure (frozen with
    the inherited decision) never counts here: the links decide whether that decision still
    holds, so they must not depend on it."""
    if compound_id_of is None:
        labels = await figure_labels(paper.id, strict)
        if labels is None:
            return None  # the IDs are not known yet: as for a missing key
        compound_id_of = segment_ids(segments, labels[0])
    ids = compound_id_of
    sources = [
        shown_source(
            paper.engine, curations.get(s.id), predictions.get(s.id, []), s.id not in inherited
        )
        for s in segments
    ]
    needed = [src for src in sources if src is not None]
    if known is None:
        known = await _known_keys(needed)
    if any(src not in known for src in needed):
        if strict:
            raise HTTPException(status_code=503, detail="busy, try again")
        return None
    return [
        Entry(s.id, s.page, known[src] if src is not None else None, ids.get(s.id))
        for s, src in zip(segments, sources, strict=True)
    ]


def _statuses(curations: dict) -> dict[uuid.UUID, str | None]:
    return {sid: c.status for sid, c in curations.items()}


async def _load_light(db: AsyncSession, paper_ids: list[uuid.UUID]):
    """load_segments for several papers, with only the columns the linking reads (shown_source,
    repeat_links, the statuses; the bbox for the compound IDs): no prediction molfile, a curated
    molfile only where the curation has no SMILES. Segments in (paper, page, idx) order."""
    of_papers = and_(Segment.paper_id.in_(paper_ids), ~candidate_clause())
    segments = (
        await db.execute(
            select(Segment.id, Segment.paper_id, Segment.page, Segment.idx, Segment.bbox)
            .where(of_papers)
            .order_by(Segment.paper_id, Segment.page, Segment.idx)
        )
    ).all()
    curations = {
        c.segment_id: c
        for c in (
            await db.execute(
                select(
                    Curation.segment_id,
                    Curation.status,
                    Curation.smiles,
                    case((Curation.smiles.is_(None), Curation.molfile)).label("molfile"),
                    Curation.rgroups,
                    Curation.shown_prediction_id,
                )
                .join(Segment, Segment.id == Curation.segment_id)
                .where(of_papers)
            )
        ).all()
    }
    predictions: dict[uuid.UUID, list] = defaultdict(list)
    for p in (
        await db.execute(
            select(
                Prediction.id,
                Prediction.segment_id,
                Prediction.engine,
                Prediction.smiles,
                Prediction.valid,
                Prediction.rgroups,
                Prediction.inchikey,  # agreement.pick_prediction
            )
            .join(Segment, Segment.id == Prediction.segment_id)
            .where(of_papers)
            .order_by(Prediction.created_at.desc(), Prediction.id)
        )
    ).all():
        predictions[p.segment_id].append(p)
    return segments, curations, predictions


async def inherited_of(
    db: AsyncSession, paper_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]]:
    """Per paper: its structures with an inherited status -> the main structure it came from
    (InheritedStatus). One query; papers without any are left out."""
    rows = await db.execute(
        select(Segment.paper_id, InheritedStatus.segment_id, InheritedStatus.main_id)
        .join(Segment, Segment.id == InheritedStatus.segment_id)
        .where(Segment.paper_id.in_(paper_ids))
    )
    out: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]] = defaultdict(dict)
    for paper_id, segment_id, main_id in rows.all():
        out[paper_id][segment_id] = main_id
    return out


async def list_count_fix(db: AsyncSession, papers: list[Paper]) -> CountFix:
    """How the paper list counts the linked groups of `papers` (core.main_figure.count_fix),
    and their stale inherited statuses. Only papers with a main figure cost much: one query for
    the main pages, one for the inherited statuses, three light ones for the marked papers'
    segments (_load_light), chem trips only for structures not cached. A paper whose keys are
    not all known (the chem process busy) counts as if it had no links, every inherited status
    to review."""
    if not papers:
        return CountFix()
    ids = [p.id for p in papers]
    mains = dict(
        (
            await db.execute(
                select(MainFigure.paper_id, MainFigure.page).where(MainFigure.paper_id.in_(ids))
            )
        ).all()
    )
    inherited = await inherited_of(db, ids)
    fix = CountFix()
    for pid, members in inherited.items():
        if pid not in mains:  # no main figure: no group holds
            fix |= CountFix(stale=stale_members(members, {}))
    if not mains:
        return fix
    segments, curations, predictions = await _load_light(db, list(mains))
    by_paper: dict[uuid.UUID, list] = defaultdict(list)
    for seg in segments:
        by_paper[seg.paper_id].append(seg)
    marked = [p for p in papers if p.id in mains]
    # One pass over every paper's structures (chunked trips); each paper then links from it.
    known = await _known_keys(
        [
            src
            for p in marked
            for s in by_paper[p.id]
            if (
                src := shown_source(
                    p.engine, curations.get(s.id), predictions.get(s.id, []),
                    s.id not in inherited.get(p.id, {}),
                )
            )  # fmt: skip
        ]
    )
    status_of = _statuses(curations)
    for p in marked:
        links = await repeat_links(
            p, mains[p.id], by_paper[p.id], curations, predictions, known=known,
            inherited=inherited.get(p.id, {}),
        )  # fmt: skip
        stale = stale_members(inherited.get(p.id, {}), links)
        fix |= CountFix(stale=stale) if links is None else count_fix(links, status_of, stale)
    return fix


async def engines_run(db: AsyncSession, paper_id: uuid.UUID) -> dict[uuid.UUID, dict[str, bool]]:
    """Per segment, the agreement slots (marcus.core.agreement.SLOTS: a MolNexTR step counts in
    MolParser's slot) that have an OCSR step: slot -> True while one of its steps is pending,
    queued or running, else False (it ran: done or failed). Cancelled steps are left out: an
    engine whose step never ran (an expired background step) did not read."""
    rows = await db.execute(
        select(Step.segment_id, Step.engine, func.bool_or(Step.status.in_(ACTIVE)))
        .where(
            Step.paper_id == paper_id,
            Step.kind == StepKind.OCSR.value,
            Step.segment_id.is_not(None),
            Step.engine.in_(AGREE_ENGINES),
            Step.status != StepStatus.CANCELLED.value,
        )
        .group_by(Step.segment_id, Step.engine)
    )
    out: dict[uuid.UUID, dict[str, bool]] = defaultdict(dict)
    for segment_id, engine, active in rows.all():
        slot = AGREE_SLOTS[engine]
        out[segment_id][slot] = out[segment_id].get(slot, False) or active
    return out


def agreement_out(
    paper_engine: str,
    predictions: list[Prediction],
    ran: dict[str, bool],
    frozen: uuid.UUID | None = None,
) -> dict:
    """SegmentOut's agreement fields (marcus.core.agreement). `predictions` newest first; `ran`:
    engines_run of the segment. The badge waits until no agreement engine is still reading. It
    counts the engines that read (a failed one too, not one that never ran): "3 agree", "2
    agree" or differ of three; "2 of 2 agree" or "2 differ" of two (owner decision
    2026-11-22). No badge with fewer than two engines read, with fewer than two newest
    predictions that have an InChIKey (older predictions have none: no backfill), or for an
    R-group scaffold shown. `frozen`: Curation.shown_prediction_id (pick_prediction)."""
    group = majority(predictions)
    pick = pick_prediction(predictions, paper_engine, frozen)
    newest = newest_by_engine(predictions)
    engines = set(ran) | set(newest)
    keyed = [p for p in newest.values() if p.valid and p.inchikey]
    scaffold = pick is not None and bool(pick.rgroups)
    shown = not any(ran.values()) and len(engines) >= 2 and len(keyed) >= 2 and not scaffold
    return {
        "agree": len(group) if shown else None,
        "agree_of": len(engines) if shown else None,
        "agree_engines": [p.engine for p in group],
        "default_prediction_id": pick.id if pick is not None else None,
    }


async def segments_out(
    db: AsyncSession, paper: Paper, main_page: int | None
) -> tuple[list[SegmentOut], CountFix, bool]:
    """The paper's segments; each structure shows the R-group labels its page's text names,
    and a repeat of a main-figure structure (`main_page`: main_figure_page) names it
    (repeat_links); an inherited status that no longer holds shows as unchecked. With them,
    how paper_counts counts the linked groups, and whether the links could be computed (not:
    the chem process busy; no repeat_of at all, every inherited status unchecked)."""
    shown, curations, predictions = await load_segments(db, paper.id, candidates=True)
    candidates = set(
        await db.scalars(
            select(Segment.id).where(Segment.paper_id == paper.id, candidate_clause())
        )
    )
    # the structures; candidates (pick mode) are only drawn on their page
    segments = [seg for seg in shown if seg.id not in candidates]
    index = paper.rgroup_text_labels
    labels = await figure_labels(paper.id)
    boxes, names = labels if labels is not None else NO_LABELS
    ids = segment_ids(segments, boxes)
    inherited = (await inherited_of(db, [paper.id])).get(paper.id, {})
    entries: list[Entry] | None = []
    if main_page is not None:
        entries = (
            None  # the compound IDs are not known yet: the links are not ready
            if labels is None
            else await link_entries(
                paper, segments, curations, predictions, compound_id_of=ids, inherited=inherited
            )
        )
    links = None if entries is None else link_repeats(entries, main_page)
    conflicts = id_conflicts(entries, main_page, links) if entries and links is not None else {}
    page_of = {seg.id: seg.page for seg in segments}
    stale = stale_members(inherited, links)
    fix = CountFix(stale=stale) if links is None else count_fix(links, _statuses(curations), stale)
    repeats = links or {}

    def curation_out(seg: Segment) -> CurationOut:
        out = structure_out(CurationOut, curations[seg.id], named_on(index, seg.page))
        if seg.id in stale:
            out.status = "unchecked"
        return out

    flagged = set(
        await db.scalars(
            select(DrawingFlag.segment_id)
            .join(Segment, Segment.id == DrawingFlag.segment_id)
            .where(Segment.paper_id == paper.id)
        )
    )
    ran = await engines_run(db, paper.id)
    out = [
        SegmentOut(
            id=seg.id,
            page=seg.page,
            idx=seg.idx,
            bbox=list(seg.bbox),
            repeat_of=repeats.get(seg.id),
            check_drawing=seg.id in flagged,
            compound_id=ids.get(seg.id),
            compound_name=names.get(ids[seg.id]) if seg.id in ids else None,
            same_id_pages=sorted({page_of[o] for o in conflicts.get(seg.id, [])}),
            **agreement_out(
                paper.engine,
                predictions[seg.id],
                ran.get(seg.id, {}),
                # an inherited status that no longer holds: its decided structure neither
                curations[seg.id].shown_prediction_id
                if seg.id in curations and seg.id not in stale
                else None,
            ),
            curation=curation_out(seg) if seg.id in curations else None,
            predictions=[
                structure_out(PredictionOut, p, named_on(index, seg.page))
                for p in predictions[seg.id]
            ],
            candidate=seg.id in candidates,
        )
        for seg in shown
    ]
    return out, fix, links is not None


async def steps_out(db: AsyncSession, paper_id: uuid.UUID) -> list[StepOut]:
    """The paper's steps, oldest first (created_at, seq). Annotate and rgroups steps are left
    out: they are not part of the paper's read (their state is served by their own routes).
    Background OCSR steps are in, marked `background`."""
    rows = await db.execute(
        select(Step, is_background().label("background"))
        .where(Step.paper_id == paper_id, in_paper_steps())
        .order_by(Step.created_at, Step.seq, Step.id)
    )
    out = []
    for step, background in rows.all():
        item = StepOut.model_validate(step)
        item.background = background
        out.append(item)
    return out
