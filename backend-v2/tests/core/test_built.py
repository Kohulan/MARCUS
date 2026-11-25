"""Built structures in the database (marcus.core.built, Markush Phase 3): one card per built row,
and the rebuild rule (never touch what a curator decided, edited or noted)."""

import pytest
from sqlalchemy import select

from marcus.core.agreement import inchikey_of
from marcus.core.built import (
    BUILT_IDX,
    IsBuilt,
    apply_build,
    input_hash,
)
from marcus.core.models import (
    BuiltSegment,
    Curation,
    InheritedStatus,
    Prediction,
    ScaffoldBuild,
    Segment,
)
from marcus.core.substituents import RESOLVER_VERSION
from tests.core.test_rgroups_pipeline import done_paper

SCAFFOLD = ("smiles", "[1*]c1ccccc1")


def outcome(compound: str, smiles: str | None = None, reason: str | None = None, groups=None):
    groups = groups if groups is not None else {"R1": compound}
    if smiles is None:
        return {"compound": compound, "groups": groups, "reason": reason or "no"}
    return {
        "compound": compound,
        "groups": groups,
        "smiles": smiles,
        "inchikey": inchikey_of(smiles, True),
    }


def make_built(s, scaffold_segment_id, rows: dict[str, str], names=None) -> list[Segment]:
    """Build `rows` (compound -> full SMILES) on the scaffold; the built segments, idx order.
    Used by the guard tests of later tasks."""
    apply_build(s, scaffold_segment_id, SCAFFOLD, [outcome(c, smi) for c, smi in rows.items()],
                names)  # fmt: skip
    s.flush()
    return built_segments(s, scaffold_segment_id)


def built_segments(s, scaffold_segment_id) -> list[Segment]:
    return list(
        s.execute(
            select(Segment)
            .join(BuiltSegment, BuiltSegment.segment_id == Segment.id)
            .where(BuiltSegment.scaffold_segment_id == scaffold_segment_id)
            .order_by(Segment.idx)
        ).scalars()
    )


def preds_of(s, segment_id) -> list[Prediction]:
    return list(s.execute(select(Prediction).where(Prediction.segment_id == segment_id)).scalars())


@pytest.fixture
def scaffold(db_session):
    paper, pred, _ = done_paper(db_session)
    return db_session.get(Segment, pred.segment_id)


def test_build_makes_one_card_per_row(db_session, scaffold):
    s = db_session
    outs = [outcome("3a", "COc1ccccc1"), outcome("3b", "c1ccccc1"), outcome("3c", reason="bad")]
    summary = apply_build(s, scaffold.id, SCAFFOLD, outs, {"3a": "Name A"})
    built = built_segments(s, scaffold.id)
    assert [b.idx for b in built] == [BUILT_IDX + 1, BUILT_IDX + 2]
    assert summary.built == [b.id for b in built] and summary.removed == 0
    for b, o in zip(built, outs[:2], strict=True):
        assert (b.page, b.bbox, b.image_sha256) == (
            scaffold.page,
            scaffold.bbox,
            scaffold.image_sha256,
        )
        (p,) = preds_of(s, b.id)
        assert (p.engine, p.valid, p.ms, p.rgroups, p.engine_version, p.inchikey) == (
            "enumerated", True, 0, [], RESOLVER_VERSION, o["inchikey"],
        )  # fmt: skip
        assert s.get(Curation, b.id).status == "unchecked"
    link = s.get(BuiltSegment, built[0].id)
    assert (link.row_key, link.name, link.input_hash) == (
        "3a", "Name A", input_hash(SCAFFOLD, outs[0]["groups"]),
    )  # fmt: skip
    assert s.get(BuiltSegment, built[1].id).name is None
    assert s.get(ScaffoldBuild, scaffold.id).failures == [{"compound": "3c", "reason": "bad"}]


def test_rebuild_never_touches_decided_edited_or_noted_cards(db_session, scaffold):
    s = db_session
    rows = {"a": "Cc1ccccc1", "b": "CCc1ccccc1", "c": "CCCc1ccccc1", "d": "CCCCc1ccccc1"}
    built = make_built(s, scaffold.id, rows)
    cur = {b.id: s.get(Curation, b.id) for b in built}
    cur[built[0].id].status = "accepted"
    cur[built[1].id].smiles = "OCc1ccccc1"
    cur[built[2].id].note = "check"
    s.add(InheritedStatus(segment_id=built[3].id, main_id=scaffold.id))
    s.flush()
    before = {b.id: [p.id for p in preds_of(s, b.id)] for b in built}
    summary = apply_build(s, scaffold.id, SCAFFOLD, [outcome("x", "Oc1ccccc1")])
    s.flush()
    for b in built:
        assert s.get(Segment, b.id) is not None
        assert [p.id for p in preds_of(s, b.id)] == before[b.id]
    assert summary.kept == 4 and summary.removed == 0


def test_rebuild_refreshes_untouched_cards(db_session, scaffold):
    s = db_session
    (b,) = make_built(s, scaffold.id, {"a": "Cc1ccccc1"})
    (old,) = preds_of(s, b.id)
    same = apply_build(s, scaffold.id, SCAFFOLD, [outcome("a", "Cc1ccccc1")])
    assert [p.id for p in preds_of(s, b.id)] == [old.id] and same.kept == 1
    changed = apply_build(
        s, scaffold.id, SCAFFOLD, [outcome("a", "CCc1ccccc1", groups={"R1": "Et"})]
    )
    s.flush()
    (new,) = preds_of(s, b.id)
    assert new.id != old.id and new.inchikey == inchikey_of("CCc1ccccc1", True)
    assert s.get(BuiltSegment, b.id).input_hash == input_hash(SCAFFOLD, {"R1": "Et"})
    assert changed.built == [] and changed.refreshed == 1


def test_rebuild_adds_new_rows_and_removes_untouched_cards_whose_row_is_gone(db_session, scaffold):
    s = db_session
    a, b = make_built(s, scaffold.id, {"a": "Cc1ccccc1", "b": "CCc1ccccc1"})
    summary = apply_build(
        s, scaffold.id, SCAFFOLD, [outcome("a", "Cc1ccccc1"), outcome("c", "Oc1ccccc1")]
    )
    s.flush()
    s.expire_all()
    assert s.get(Segment, b.id) is None and summary.removed == 1
    assert [x.id for x in built_segments(s, scaffold.id)][0] == a.id
    assert len(summary.built) == 1


def test_rebuild_removes_an_untouched_card_whose_row_now_fails(db_session, scaffold):
    s = db_session
    (b,) = make_built(s, scaffold.id, {"a": "Cc1ccccc1"})
    summary = apply_build(s, scaffold.id, SCAFFOLD, [outcome("a", reason="unknown")])
    s.flush()
    s.expire_all()
    assert s.get(Segment, b.id) is None and summary.removed == 1
    assert s.get(ScaffoldBuild, scaffold.id).failures == [{"compound": "a", "reason": "unknown"}]


def test_build_twice_makes_no_duplicates(db_session, scaffold):
    s = db_session
    rows = {"a": "Cc1ccccc1", "b": "CCc1ccccc1"}
    first = [x.id for x in make_built(s, scaffold.id, rows)]
    second = [x.id for x in make_built(s, scaffold.id, rows)]
    assert first == second


def test_idx_never_collides_after_a_removal(db_session, scaffold):
    s = db_session
    make_built(s, scaffold.id, {"a": "Cc1ccccc1", "b": "CCc1ccccc1"})
    apply_build(s, scaffold.id, SCAFFOLD, [outcome("b", "CCc1ccccc1"), outcome("c", "Oc1ccccc1")])
    s.flush()
    idx = [x.idx for x in built_segments(s, scaffold.id)]
    assert idx == sorted(set(idx)) and max(idx) == BUILT_IDX + 3


def test_build_on_a_built_segment_raises_is_built(db_session, scaffold):
    s = db_session
    (b,) = make_built(s, scaffold.id, {"a": "Cc1ccccc1"})
    with pytest.raises(IsBuilt):
        apply_build(s, b.id, SCAFFOLD, [outcome("z", "Cc1ccccc1")])
