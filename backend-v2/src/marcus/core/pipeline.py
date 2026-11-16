"""Pipeline state transitions. Every function takes a sync SQLAlchemy Session."""

import hashlib
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from marcus.core import storage
from marcus.core.enums import Engine, PaperStatus, StepKind, StepStatus
from marcus.core.models import Owner, Paper, Step
from marcus.core.queues import queue_for
from marcus.core.settings import get_settings


def start_paper(
    session: Session,
    owner: Owner,
    data: bytes,
    display_name: str,
    engine: Engine,
    ocsr_mode: str,
) -> Paper:
    """Store the PDF and create the paper plus its check_pdf step. Caller commits."""
    paper = Paper(
        owner_id=owner.id,
        display_name=display_name,
        pdf_sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        engine=Engine(engine).value,
        ocsr_mode=ocsr_mode,
        status=PaperStatus.CHECKING.value,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().retention_days),
    )
    session.add(paper)
    session.flush()  # assigns paper.id

    path = storage.pdf_path(paper.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)

    session.add(
        Step(
            paper_id=paper.id,
            kind=StepKind.CHECK_PDF.value,
            queue=queue_for(StepKind.CHECK_PDF, None),
            seq=0,
            status=StepStatus.PENDING.value,
        )
    )
    session.flush()
    return paper
