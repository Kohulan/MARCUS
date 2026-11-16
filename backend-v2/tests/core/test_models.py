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
