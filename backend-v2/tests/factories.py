"""Small sync-session factories for tests. Each flushes; the caller commits if it needs to."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from marcus.core.enums import Engine, OwnerKind, PriorityClass, StepKind, StepStatus
from marcus.core.models import ImageJob, Owner, Paper, Step
from marcus.core.pipeline import start_paper
from marcus.core.queues import queue_for

PDF = b"%PDF-1.4\n" + b"0" * 64


def make_owner(session: Session, kind: OwnerKind = OwnerKind.BROWSER) -> Owner:
    priority = PriorityClass.BROWSER if kind == OwnerKind.BROWSER else PriorityClass.API
    owner = Owner(kind=kind.value, token_hash=uuid.uuid4().hex, priority_class=int(priority))
    session.add(owner)
    session.flush()
    return owner


def make_paper(
    session: Session,
    owner: Owner | None = None,
    engine: Engine = Engine.DECIMER,
    ocsr_mode: str = "auto",
) -> Paper:
    owner = owner or make_owner(session)
    return start_paper(session, owner, PDF, "paper.pdf", engine, ocsr_mode)


def make_image_job(
    session: Session, owner: Owner | None = None, engine: Engine = Engine.DECIMER
) -> tuple[ImageJob, Step]:
    owner = owner or make_owner(session)
    job = ImageJob(
        owner_id=owner.id,
        display_name="img.png",
        image_sha256="a" * 64,
        engine=engine.value,
        status="queued",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(job)
    session.flush()
    step = Step(
        image_job_id=job.id,
        kind=StepKind.OCSR.value,
        queue=queue_for(StepKind.OCSR, engine),
        engine=engine.value,
        seq=0,
        status=StepStatus.PENDING.value,
    )
    session.add(step)
    session.flush()
    return job, step
