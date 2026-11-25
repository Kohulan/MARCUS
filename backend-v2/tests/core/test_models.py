import uuid

import psycopg
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from marcus.core.models import ImageJob, Owner, Paper, Segment, Step


def _owner(session):
    o = Owner(kind="browser", token_hash=uuid.uuid4().hex, priority_class=0)
    session.add(o)
    session.flush()
    return o


def _paper(session, owner):
    p = Paper(
        owner_id=owner.id, display_name="a.pdf", pdf_sha256="0" * 64, bytes=10,
        engine="decimer", ocsr_mode="auto", status="checking",
        expires_at="2030-01-01T00:00:00+00:00",
    )  # fmt: skip
    session.add(p)
    session.flush()
    return p


def _image_job(session, owner):
    j = ImageJob(
        owner_id=owner.id, display_name="a.png", image_sha256="1" * 64,
        engine="decimer", status="queued", expires_at="2030-01-01T00:00:00+00:00",
    )  # fmt: skip
    session.add(j)
    session.flush()
    return j


def test_step_needs_exactly_one_parent(db_session):
    owner = _owner(db_session)
    paper = _paper(db_session, owner)
    job = _image_job(db_session, owner)
    db_session.commit()

    db_session.add(
        Step(paper_id=paper.id, image_job_id=job.id, kind="ocsr", queue="q.cpu", seq=0,
             status="pending")
    )  # fmt: skip
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    db_session.add(Step(kind="ocsr", queue="q.cpu", seq=0, status="pending"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    db_session.add(Step(paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=0,
                        status="pending"))  # fmt: skip
    db_session.flush()


def test_segment_unique_and_bbox_length(db_session):
    owner = _owner(db_session)
    paper = _paper(db_session, owner)
    db_session.add(
        Segment(paper_id=paper.id, page=1, idx=0, bbox=[1, 2, 3, 4], image_sha256="2" * 64)
    )
    db_session.flush()
    db_session.add(
        Segment(paper_id=paper.id, page=1, idx=0, bbox=[1, 2, 3, 4], image_sha256="2" * 64)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    paper = db_session.execute(select(Paper)).scalars().first()
    assert paper is None  # rollback discarded uncommitted rows


def test_paper_delete_cascades(db_session):
    owner = _owner(db_session)
    paper = _paper(db_session, owner)
    db_session.add(Step(paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=0,
                        status="pending"))  # fmt: skip
    db_session.commit()
    db_session.delete(owner)
    db_session.commit()
    assert db_session.execute(select(Step)).first() is None


def test_notify_on_step_status_change(db_session, migrated_db):
    from sqlalchemy.engine import make_url

    from marcus.core.settings import get_settings

    url = make_url(get_settings().database_url).set(drivername="postgresql")
    owner = _owner(db_session)
    paper = _paper(db_session, owner)
    step = Step(paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=0, status="pending")
    db_session.add(step)
    db_session.commit()

    with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as listener:
        listener.execute("LISTEN marcus_steps")
        step.status = "queued"
        db_session.commit()
        notes = list(listener.notifies(timeout=5, stop_after=1))
    assert [n.payload for n in notes] == ["q.cpu"]


async def test_async_session_roundtrip(async_db_session):
    o = Owner(kind="api_key", token_hash=uuid.uuid4().hex, priority_class=1)
    async_db_session.add(o)
    await async_db_session.commit()
    assert (await async_db_session.execute(select(Owner))).scalars().one().kind == "api_key"


def test_tables_clean_between_tests(db_session):
    assert db_session.execute(select(Owner)).first() is None


def _listener_url() -> str:
    from sqlalchemy.engine import make_url

    from marcus.core.settings import get_settings

    url = make_url(get_settings().database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def test_bbox_of_length_3_is_refused(db_session):
    paper = _paper(db_session, _owner(db_session))
    db_session.add(Segment(paper_id=paper.id, page=0, idx=0, bbox=[1, 2, 3], image_sha256="2" * 64))
    with pytest.raises(IntegrityError, match="ck_segments_bbox_len"):
        db_session.flush()
    db_session.rollback()


def test_owner_delete_cascades_through_the_whole_tree(db_session):
    from sqlalchemy import func

    from marcus.core.models import Curation, Prediction

    s = db_session
    owner = _owner(s)
    paper = _paper(s, owner)
    job = _image_job(s, owner)
    segments = [
        Segment(paper_id=paper.id, page=0, idx=i, bbox=[0, 0, 1, 1], image_sha256="2" * 64)
        for i in range(2)
    ]
    s.add_all(segments)
    s.flush()
    for seg in segments:
        s.add(Curation(segment_id=seg.id, status="unchecked"))
        s.add(Prediction(segment_id=seg.id, engine="decimer", engine_version="v", smiles="C",
                         valid=True, ms=1))  # fmt: skip
        s.add(Step(paper_id=paper.id, segment_id=seg.id, kind="ocsr", queue="q.decimer",
                   engine="decimer", seq=seg.idx, status="done"))  # fmt: skip
    s.add(Step(paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=0, status="done"))
    s.add(Step(image_job_id=job.id, kind="ocsr", queue="q.decimer", engine="decimer", seq=0,
               status="pending"))  # fmt: skip
    s.add(Prediction(image_job_id=job.id, engine="decimer", engine_version="v", smiles="C",
                     valid=True, ms=1))  # fmt: skip
    s.commit()

    def n(model) -> int:
        return s.execute(select(func.count()).select_from(model)).scalar_one()

    # one segment alone: its ocsr step (via segment_id), prediction and curation go with it
    s.delete(segments[0])
    s.commit()
    assert (n(Segment), n(Curation), n(Step), n(Prediction)) == (1, 1, 3, 2)

    s.delete(owner)
    s.commit()
    for model in (Owner, Paper, ImageJob, Segment, Curation, Prediction, Step):
        assert n(model) == 0, model.__tablename__


def test_notify_on_step_insert(db_session):
    paper = _paper(db_session, _owner(db_session))
    db_session.commit()
    with psycopg.connect(_listener_url(), autocommit=True) as listener:
        listener.execute("LISTEN marcus_steps")
        db_session.add(
            Step(paper_id=paper.id, kind="ocsr", queue="q.molnextr", engine="molnextr", seq=0,
                 status="pending")
        )  # fmt: skip
        db_session.commit()
        notes = list(listener.notifies(timeout=5, stop_after=1))
    assert [n.payload for n in notes] == ["q.molnextr"]


def test_no_notify_when_status_unchanged(db_session):
    paper = _paper(db_session, _owner(db_session))
    step = Step(paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=0, status="pending")
    db_session.add(step)
    db_session.commit()
    with psycopg.connect(_listener_url(), autocommit=True) as listener:
        listener.execute("LISTEN marcus_steps")
        # same status written explicitly (the trigger is AFTER UPDATE OF status), other columns
        db_session.execute(
            Step.__table__.update().where(Step.id == step.id).values(status="pending", attempts=1)
        )
        db_session.commit()
        notes = list(listener.notifies(timeout=1, stop_after=1))
    assert notes == []


def test_deleting_a_paper_deletes_its_built_rows(db_session):
    """A built structure (Markush Phase 3) and its side rows go with its paper."""
    from marcus.core.models import BuiltSegment, ScaffoldBuild

    s = db_session
    paper = _paper(s, _owner(s))
    scaffold = Segment(paper_id=paper.id, page=0, idx=0, bbox=[0, 0, 1, 1], image_sha256="a" * 64)
    built = Segment(paper_id=paper.id, page=0, idx=10000, bbox=[0, 0, 1, 1], image_sha256="a" * 64)
    s.add_all([scaffold, built])
    s.flush()
    s.add(BuiltSegment(segment_id=built.id, scaffold_segment_id=scaffold.id, row_key="3a",
                       name=None, input_hash="0" * 64))  # fmt: skip
    s.add(ScaffoldBuild(scaffold_segment_id=scaffold.id, failures=[]))
    s.commit()
    s.delete(s.get(Paper, paper.id))
    s.commit()
    assert s.execute(select(BuiltSegment)).first() is None
    assert s.execute(select(ScaffoldBuild)).first() is None
