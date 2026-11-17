import hashlib
import uuid
from types import SimpleNamespace

import pytest
from PIL import Image

from marcus.core.enums import Engine, StepKind
from marcus.core.settings import get_settings
from marcus.core.storage import image_job_path, segment_crop_path
from marcus.workers import ocsr as ocsr_pkg  # noqa: F401
from marcus.workers.ocsr import base
from marcus.workers.ocsr.base import OcsrResult
from marcus.workers.runtime import HANDLERS
from tests.workers.helpers import view


class StubEngine:
    name = Engine.DECIMER
    version = "stub-9"

    def __init__(self, smiles):
        self.smiles = smiles

    def load(self):
        pass

    def predict(self, image):
        return OcsrResult(self.smiles, None)


class FakeSession:
    """Answers the segment lookup with `seg`; the ocsr_cache lookup misses and its write is
    recorded (the cache itself is tested against the database in tests/core/test_caches.py)."""

    def __init__(self, seg):
        self.seg = seg
        self.rolled_back = 0
        self.writes = []
        self.commits = 0

    def execute(self, stmt, *a, **k):
        if "ocsr_cache" in str(stmt):
            if stmt.is_insert:
                self.writes.append(stmt.compile().params)
            return SimpleNamespace(one_or_none=lambda: None)
        return SimpleNamespace(one_or_none=lambda: self.seg, scalar_one_or_none=lambda: self.seg)

    def commit(self):
        self.commits += 1

    def get(self, *a, **k):
        return self.seg

    def rollback(self):
        self.rolled_back += 1


def job_image():
    job = uuid.uuid4()
    p = image_job_path(job)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), "white").save(p)
    return job


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(base, "_ENGINES", {})
    yield


def use_engine(monkeypatch, smiles):
    eng = StubEngine(smiles)
    monkeypatch.setitem(base.FACTORIES, "decimer", lambda: eng)
    return eng


def test_handler_registered():
    import marcus.workers.ocsr.handler  # noqa: F401
    from marcus.workers import ocsr as _  # noqa: F401

    assert StepKind.OCSR in HANDLERS


def test_ocsr_handler_marks_invalid_smiles(monkeypatch):
    from marcus.workers.ocsr.handler import ocsr

    use_engine(monkeypatch, "C1CC")
    out = ocsr(view(image_job_id=job_image(), engine="decimer"), None)
    assert out["valid"] is False and out["smiles"] == "C1CC"
    assert out["engine_version"] == "stub-9"
    assert isinstance(out["ms"], int) and out["molfile"] is None


def test_ocsr_handler_valid_and_empty(monkeypatch):
    from marcus.workers.ocsr.handler import ocsr

    use_engine(monkeypatch, "c1ccccc1")
    assert ocsr(view(image_job_id=job_image(), engine="decimer"), None)["valid"] is True
    base._ENGINES.clear()
    use_engine(monkeypatch, "")
    assert ocsr(view(image_job_id=job_image(), engine="decimer"), None)["valid"] is False


def test_ocsr_paper_step_reads_crop_by_sha(monkeypatch):
    from marcus.workers.ocsr.handler import ocsr

    use_engine(monkeypatch, "CCO")
    pid, sha = uuid.uuid4(), "ab" * 32
    crop = segment_crop_path(pid, sha)
    crop.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(crop)
    session = FakeSession(SimpleNamespace(paper_id=pid, image_sha256=sha))
    step = view(pid, segment_id=uuid.uuid4(), engine="decimer")
    assert ocsr(step, session)["valid"] is True
    assert session.rolled_back >= 1
    # the cache key is the hash of the crop's bytes, written in its own committed transaction
    (written,) = session.writes
    assert written["image_sha256"] == hashlib.sha256(crop.read_bytes()).hexdigest()
    assert (written["engine"], written["engine_version"], written["smiles"]) == (
        "decimer",
        "stub-9",
        "CCO",
    )
    assert session.commits == 1


def test_ocsr_missing_segment_is_bad_input(monkeypatch):
    from marcus.workers.ocsr.handler import ocsr
    from marcus.workers.runtime import BadInput

    use_engine(monkeypatch, "CCO")
    with pytest.raises(BadInput):
        ocsr(view(uuid.uuid4(), segment_id=uuid.uuid4(), engine="decimer"), FakeSession(None))


def test_fake_engine_refused_in_production_settings():
    with pytest.raises(RuntimeError):
        base.get_engine(Engine.FAKE)


def test_fake_engine_allowed_and_cached(monkeypatch):
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    get_settings.cache_clear()
    a = base.get_engine(Engine.FAKE)
    assert a is base.get_engine(Engine.FAKE)
    img = job_image()
    assert a.predict(image_job_path(img)).smiles == "c1ccccc1"


def test_unregistered_engine_raises():
    with pytest.raises(RuntimeError):
        base.get_engine(Engine.MOLSCRIBE)


def test_engine_loaded_once(monkeypatch):
    calls = []

    class E(StubEngine):
        def load(self):
            calls.append(1)

    monkeypatch.setitem(base.FACTORIES, "decimer", lambda: E("C"))
    base.get_engine(Engine.DECIMER)
    base.get_engine(Engine.DECIMER)
    assert calls == [1]
