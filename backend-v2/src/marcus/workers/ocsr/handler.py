"""The `ocsr` step handler (GPU worker images import `marcus.workers.ocsr`).

Engine input (owner decision, D4 fix round 2): segment crops are stored in true colour (what
users see), but v1 fed its engines crop files with red and blue swapped (its `cv2.imwrite` of an
RGB array). For v1-identical accuracy every engine gets that swapped image for a segment crop
(`v1_engine_input`, written to a temporary PNG on /tmp). Image jobs (a user's own image) reach
the engine unchanged, as in v1's image path. This module is the ONLY place that builds engine
input from a crop: a new consumer that feeds crops to a model must use `v1_engine_input` too.

OCSR cache (spec §7): before predicting, the handler looks up (sha256 of the bytes the ENGINE
gets, engine, engine version) in `ocsr_cache`: for a crop the swapped PNG, for an image job its
file. So a crop and an image job with identical stored bytes never share a row. The version is read without loading the model
(base.engine_version), so a hit never loads one. A hit returns the cached SMILES and molfile
(`ms` 0, `valid` recomputed with RDKit) without calling the engine; a miss loads the engine if
needed, predicts and stores a non-empty SMILES in its own short transaction (ON CONFLICT DO
NOTHING). The cache row holds no owner data: only the hash, the engine and its output. A cache
read or write that fails is logged and ignored (the prediction does not depend on it).

The fake engine never reads or writes the cache: its output is not a real result, and the
fake stack's tests must measure the engine, not cache hits.
"""

import hashlib
import io
import logging
import os
import tempfile
import time
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from PIL import Image
from rdkit import Chem, RDLogger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from marcus.core.enums import Engine, StepKind
from marcus.core.models import OcsrCache, Segment
from marcus.core.storage import image_job_path, segment_crop_path
from marcus.workers.ocsr.base import engine_version, get_engine
from marcus.workers.runtime import BadInput, register

RDLogger.DisableLog("rdApp.*")

log = logging.getLogger(__name__)


def is_valid_smiles(smiles: str) -> bool:
    if not smiles:
        return False
    return Chem.MolFromSmiles(smiles) is not None


def v1_engine_input(crop_path: Path) -> bytes:
    """The PNG bytes an OCSR engine gets for a stored (true-colour) segment crop: red and blue
    swapped, i.e. the pixels of v1's `cv2.imwrite(path, rgb_crop)` file (v1 parity of every engine;
    D4: all four convert to grey with unequal channel weights). PNG is lossless, so the engine
    decodes exactly these pixels. Image jobs never go through this."""
    with Image.open(crop_path) as im:
        r, g, b = im.convert("RGB").split()
        buf = io.BytesIO()
        Image.merge("RGB", (b, g, r)).save(buf, format="PNG")
    return buf.getvalue()


def _input_image(step, session) -> tuple[Path, bool]:
    """(stored input file, is_segment_crop)."""
    if step.image_job_id is not None:
        return image_job_path(step.image_job_id), False
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
    return segment_crop_path(row.paper_id, row.image_sha256), True


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
    image, is_crop = _input_image(step, session)
    if not image.is_file():
        raise BadInput("input image is missing")
    data = v1_engine_input(image) if is_crop else image.read_bytes()
    use_cache = name is not Engine.FAKE
    if use_cache:
        sha = hashlib.sha256(data).hexdigest()  # the engine's input, not the stored file
        version = engine_version(name)
        hit = _cache_get(session, sha, name.value, version)
        if hit is not None:
            return {
                "smiles": hit.smiles,
                "molfile": hit.molfile,
                "valid": is_valid_smiles(hit.smiles),
                "ms": 0,
                "cached": True,
                "engine_version": version,
            }
    engine = get_engine(name)
    if is_crop:
        # /tmp is a tmpfs in every worker container; the engine reads the file with its own reader
        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="ocsr-input-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            start = time.monotonic()
            result = engine.predict(Path(tmp))
            ms = int((time.monotonic() - start) * 1000)
        finally:
            os.unlink(tmp)
    else:
        start = time.monotonic()
        result = engine.predict(image)
        ms = int((time.monotonic() - start) * 1000)
    if use_cache:
        _cache_put(session, sha, name.value, engine.version, result.smiles, result.molfile)
    return {
        "smiles": result.smiles,
        "molfile": result.molfile,
        "valid": is_valid_smiles(result.smiles),
        "ms": ms,
        "cached": False,
        "engine_version": engine.version,
    }


register(StepKind.OCSR, ocsr)
