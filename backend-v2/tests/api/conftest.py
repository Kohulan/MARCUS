"""Shared API test helpers: an app bound to the test session and seeded, owned papers.

Seeding runs the real planner (`complete_step`) through `AsyncSession.run_sync`, so the rows
look exactly like the ones workers produce.
"""

import json
import uuid
from dataclasses import dataclass, field

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from marcus.api.deps import COOKIE_NAME
from marcus.api.main import create_app
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine, OwnerKind, PriorityClass
from marcus.core.models import Owner, Paper, Segment, Step
from marcus.core.pipeline import complete_step
from marcus.core.tokens import hash_token, new_token
from tests.factories import make_paper

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SEGS = [
    {"idx": 0, "bbox": [0, 0, 10, 10], "image_sha256": "0" * 64},
    {"idx": 1, "bbox": [5, 5, 50, 60], "image_sha256": "1" * 64},
]


def ocsr_result(smiles: str = "CCO", valid: bool = True, molfile: str | None = None) -> dict:
    return {"smiles": smiles, "molfile": molfile, "valid": valid, "ms": 5, "engine_version": "t1"}


@pytest.fixture
def app(async_db_session):
    app = create_app()

    async def _db():
        yield async_db_session

    app.dependency_overrides[get_db] = _db
    return app


def make_client(app, token: str | None = None) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")
    if token is not None:
        c.cookies.set(COOKIE_NAME, token)  # no domain: the cookie jar sends it to any host
    return c


async def new_owner(db) -> tuple[Owner, str]:
    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
    )
    db.add(owner)
    await db.commit()
    return owner, token


def steps_of(s: Session, paper_id, kind=None, status=None) -> list[Step]:
    q = select(Step).where(Step.paper_id == paper_id)
    if kind:
        q = q.where(Step.kind == kind)
    if status:
        q = q.where(Step.status == status)
    return list(s.execute(q.order_by(Step.seq, Step.created_at)).scalars())


def finish(s: Session, step: Step, result: dict) -> list[Step]:
    step.status = "running"
    step.attempts += 1
    s.flush()
    return complete_step(s, step.id, result)


@dataclass
class Seeded:
    paper_id: uuid.UUID
    segment_ids: list[uuid.UUID] = field(default_factory=list)


def _seed(s: Session, owner_id, engine: Engine, ocsr: bool, write_files: bool) -> Seeded:
    owner = s.get(Owner, owner_id)
    paper = make_paper(s, owner, engine=engine)
    (check,) = steps_of(s, paper.id, "check_pdf")
    finish(s, check, {"pages": 1})
    (render,) = steps_of(s, paper.id, "render_page")
    (seg_step,) = finish(s, render, {})
    ocsr_steps = finish(s, seg_step, {"segments": SEGS})
    if ocsr:
        for st in ocsr_steps:
            finish(s, st, ocsr_result())
    segs = s.execute(
        select(Segment).where(Segment.paper_id == paper.id).order_by(Segment.idx)
    ).scalars()
    seeded = Seeded(paper.id, [seg.id for seg in segs])
    if write_files:
        page = storage.page_image_path(paper.id, 0)
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_bytes(PNG)
        for item in SEGS:
            crop = storage.segment_crop_path(paper.id, item["image_sha256"])
            crop.parent.mkdir(parents=True, exist_ok=True)
            crop.write_bytes(PNG + item["image_sha256"][:1].encode())
        (storage.paper_dir(paper.id) / "text.json").write_text(json.dumps({"texts": ["hi"]}))
    s.flush()
    return seeded


async def seed_paper(
    db,
    owner: Owner,
    engine: Engine = Engine.DECIMER,
    ocsr: bool = True,
    write_files: bool = True,
) -> Seeded:
    """A 1-page paper with 2 segments (and one decimer prediction each when `ocsr`)."""
    seeded = await db.run_sync(lambda s: _seed(s, owner.id, engine, ocsr, write_files))
    await db.commit()
    return seeded


async def paper_row(db, paper_id) -> Paper:
    return (
        await db.execute(
            select(Paper).where(Paper.id == paper_id).execution_options(populate_existing=True)
        )
    ).scalar_one()
