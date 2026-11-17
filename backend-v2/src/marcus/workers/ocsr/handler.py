"""The `ocsr` step handler (GPU worker images import `marcus.workers.ocsr`).

OCSR cache (spec §7): before predicting, the handler looks up (sha256 of the input image's
bytes, engine, engine version) in `ocsr_cache`. A hit returns the cached SMILES and molfile
(`ms` 0, `valid` recomputed with RDKit) without calling the engine; a miss predicts and then
stores a non-empty SMILES in its own short transaction (ON CONFLICT DO NOTHING). The cache
row holds no owner data: only the hash, the engine and its output. A cache read or write that
fails is logged and ignored (the prediction does not depend on it).
"""

import hashlib
import logging
import time

from celery.exceptions import SoftTimeLimitExceeded
from rdkit import Chem, RDLogger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from marcus.core.enums import Engine, StepKind
from marcus.core.models import OcsrCache, Segment
from marcus.core.storage import image_job_path, segment_crop_path
from marcus.workers.ocsr.base import get_engine
from marcus.workers.runtime import BadInput, register

RDLogger.DisableLog("rdApp.*")

log = logging.getLogger(__name__)


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


def _cache_get(session, sha: str, engine: str, version: str):
    """(smiles, molfile) from ocsr_cache, or None. Ends its read transaction."""
    if session is None:
        return None
    try:
        return session.execute(
            select(OcsrCache.smiles, OcsrCache.molfile).where(
                OcsrCache.image_sha256 == sha,
                OcsrCache.engine == engine,
                OcsrCache.engine_version == version,
            )
        ).one_or_none()
    except SoftTimeLimitExceeded:
        raise
    except Exception:  # noqa: BLE001 - the cache is an optimisation; predict instead
        log.warning("ocsr_cache read failed; predicting", exc_info=True)
        return None
    finally:
        session.rollback()  # end the read transaction before the long work


def _cache_put(session, sha: str, engine: str, version: str, smiles: str, molfile) -> None:
    """Store one prediction in its own short transaction; an existing row is kept."""
    if session is None or not smiles:
        return
    try:
        session.execute(
            pg_insert(OcsrCache)
            .values(
                image_sha256=sha,
                engine=engine,
                engine_version=version,
                smiles=smiles,
                molfile=molfile,
            )
            .on_conflict_do_nothing(index_elements=["image_sha256", "engine", "engine_version"])
        )
        session.commit()
    except Exception:  # noqa: BLE001 - the prediction is done; a lost cache row costs nothing
        session.rollback()
        log.warning("ocsr_cache write failed", exc_info=True)


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
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    engine = get_engine(name)
    hit = _cache_get(session, sha, name.value, engine.version)
    if hit is not None:
        return {
            "smiles": hit.smiles,
            "molfile": hit.molfile,
            "valid": is_valid_smiles(hit.smiles),
            "ms": 0,
            "engine_version": engine.version,
        }
    start = time.monotonic()
    result = engine.predict(image)
    ms = int((time.monotonic() - start) * 1000)
    _cache_put(session, sha, name.value, engine.version, result.smiles, result.molfile)
    return {
        "smiles": result.smiles,
        "molfile": result.molfile,
        "valid": is_valid_smiles(result.smiles),
        "ms": ms,
        "engine_version": engine.version,
    }


register(StepKind.OCSR, ocsr)
