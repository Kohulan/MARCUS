"""The `ocsr` step handler (GPU worker images import `marcus.workers.ocsr`)."""

import time

from rdkit import Chem, RDLogger
from sqlalchemy import select

from marcus.core.enums import Engine, StepKind
from marcus.core.models import Segment
from marcus.core.storage import image_job_path, segment_crop_path
from marcus.workers.ocsr.base import get_engine
from marcus.workers.runtime import BadInput, register

RDLogger.DisableLog("rdApp.*")


def is_valid_smiles(smiles: str) -> bool:
    if not smiles:
        return False
    return Chem.MolFromSmiles(smiles) is not None


def _input_image(step, session):
    if step.image_job_id is not None:
        return image_job_path(step.image_job_id)
    if step.segment_id is None or session is None:
        raise BadInput("ocsr step has no input image")
    try:
        row = session.execute(
            select(Segment.paper_id, Segment.image_sha256).where(Segment.id == step.segment_id)
        ).one_or_none()
    finally:
        session.rollback()  # end the read transaction before the long work
    if row is None:
        raise BadInput("segment not found")
    return segment_crop_path(row.paper_id, row.image_sha256)


def ocsr(step, session) -> dict:
    if not step.engine:
        raise BadInput("ocsr step has no engine")
    try:
        name = Engine(step.engine)
    except ValueError as exc:
        raise BadInput("unknown engine") from exc
    image = _input_image(step, session)
    if not image.is_file():
        raise BadInput("input image is missing")
    engine = get_engine(name)
    start = time.monotonic()
    result = engine.predict(image)
    ms = int((time.monotonic() - start) * 1000)
    return {
        "smiles": result.smiles,
        "molfile": result.molfile,
        "valid": is_valid_smiles(result.smiles),
        "ms": ms,
        "engine_version": engine.version,
    }


register(StepKind.OCSR, ocsr)
