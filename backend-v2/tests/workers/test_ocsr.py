import hashlib
import io
import uuid
from types import SimpleNamespace

import pytest
from PIL import Image

from marcus.core.enums import Engine, StepKind
from marcus.core.settings import get_settings
from marcus.core.storage import image_job_path, segment_crop_path
from marcus.workers.ocsr import base
from marcus.workers.ocsr.base import OcsrResult
from marcus.workers.runtime import HANDLERS
from tests.workers.helpers import view

OWNER = uuid.UUID(int=5)  # the owner the fake session's lookups answer with


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
    """Answers the segment lookup (or an image job's owner lookup) with `seg`; the ocsr_cache
    lookup misses and its write is recorded (the cache itself is tested against the database in
    tests/core/test_caches.py)."""

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


def use_engine(monkeypatch, smiles, name="decimer"):
    eng = StubEngine(smiles)
    monkeypatch.setitem(base.FACTORIES, name, lambda: eng)
    return eng


def test_handler_registered():
    from marcus.workers.ocsr.handler import ocsr  # importing it registers the handler

    assert HANDLERS[StepKind.OCSR] is ocsr


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
    session = FakeSession(SimpleNamespace(paper_id=pid, image_sha256=sha, owner_id=OWNER))
    step = view(pid, segment_id=uuid.uuid4(), engine="decimer")
    assert ocsr(step, session)["valid"] is True
    assert session.rolled_back >= 1
    # the cache key is the hash of the ENGINE's input (the v1-swapped crop), written in its own
    # committed transaction
    from marcus.workers.ocsr.handler import v1_engine_input

    (written,) = session.writes
    assert written["image_sha256"] == hashlib.sha256(v1_engine_input(crop)).hexdigest()
    assert (written["engine"], written["engine_version"], written["smiles"]) == (
        "decimer",
        "stub-9",
        "CCO",
    )
    assert written["owner_id"] == OWNER
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


def test_ocsr_marks_cache_hits_and_misses(monkeypatch):
    """The step result says whether it came from ocsr_cache (judges need it for honest timings)."""
    from marcus.workers.ocsr import handler

    use_engine(monkeypatch, "CCO")
    sha = "cd" * 32
    pid = uuid.uuid4()
    crop = segment_crop_path(pid, sha)
    crop.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(crop)
    session = FakeSession(SimpleNamespace(paper_id=pid, image_sha256=sha, owner_id=uuid.uuid4()))
    miss = handler.ocsr(view(pid, segment_id=uuid.uuid4(), engine="decimer"), session)
    assert miss["cached"] is False
    monkeypatch.setattr(
        handler, "_cache_get", lambda *a: SimpleNamespace(smiles="CCO", molfile=None)
    )
    hit = handler.ocsr(view(pid, segment_id=uuid.uuid4(), engine="decimer"), session)
    assert hit["cached"] is True and hit["ms"] == 0


# --- engine input: true-colour stored crop, v1's swapped pixels for the engine (D4 fix round 2) ---

RED, BLUE, BLACK, WHITE = (255, 0, 0), (0, 0, 255), (0, 0, 0), (255, 255, 255)


def coloured_image(path):
    """A 4x4 RGB PNG: red (an O label), blue (an N label), black (a bond), white elsewhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (4, 4), WHITE)
    im.putpixel((0, 0), RED)
    im.putpixel((1, 1), BLUE)
    im.putpixel((2, 2), BLACK)
    im.save(path)
    return path


class PixelEngine:
    """Records the pixels of the file it is given, as each real engine reads its file itself."""

    version = "pix-1"

    def __init__(self, name):
        self.name = Engine(name)
        self.seen, self.paths = [], []

    def load(self):
        pass

    def predict(self, image):
        self.paths.append(image)
        with Image.open(image) as im:
            rgb = im.convert("RGB")
            self.seen.append([rgb.getpixel(xy) for xy in ((0, 0), (1, 1), (2, 2), (3, 3))])
        return OcsrResult("CCO", None)


def crop_step(monkeypatch, engine_name):
    pid, sha = uuid.uuid4(), "cd" * 32
    crop = coloured_image(segment_crop_path(pid, sha))
    eng = PixelEngine(engine_name)
    monkeypatch.setitem(base.FACTORIES, engine_name, lambda: eng)
    session = FakeSession(SimpleNamespace(paper_id=pid, image_sha256=sha, owner_id=OWNER))
    return crop, eng, session, view(pid, segment_id=uuid.uuid4(), engine=engine_name)


@pytest.mark.parametrize("engine_name", ["decimer", "decimer-hand", "molnextr", "molscribe"])
def test_every_engine_gets_v1_swapped_pixels_for_a_crop(monkeypatch, engine_name):
    """All four engines convert to grey with unequal channel weights, so each must get v1's input:
    red and blue swapped (v1's cv2.imwrite of the RGB crop). The stored crop stays true colour."""
    from marcus.workers.ocsr.handler import ocsr

    crop, eng, session, step = crop_step(monkeypatch, engine_name)
    before = crop.read_bytes()
    out = ocsr(step, session)

    assert out["smiles"] == "CCO" and out["cached"] is False
    assert eng.seen == [[BLUE, RED, BLACK, WHITE]]  # red label arrives blue, blue arrives red
    assert crop.read_bytes() == before  # the file users see is untouched
    assert eng.paths[0] != crop and not eng.paths[0].exists()  # a temporary file, removed after


def test_image_job_reaches_the_engine_unswapped(monkeypatch):
    """A user's own image is never swapped (v1's image path has no swap), and its cache key is the
    file's own hash."""
    from marcus.workers.ocsr.handler import ocsr

    job = uuid.uuid4()
    path = coloured_image(image_job_path(job))
    eng = PixelEngine("molscribe")
    monkeypatch.setitem(base.FACTORIES, "molscribe", lambda: eng)
    session = FakeSession(OWNER)  # the image job's owner id
    ocsr(view(image_job_id=job, engine="molscribe"), session)
    assert eng.seen == [[RED, BLUE, BLACK, WHITE]]
    assert eng.paths == [path]
    (written,) = session.writes
    assert written["image_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert written["owner_id"] == OWNER  # F3: the cache row is the owner's own


def test_crop_and_image_job_with_the_same_bytes_get_different_cache_keys(monkeypatch):
    """A user who downloads a coloured crop and uploads it as an image job must not get the crop's
    cached answer: the engine inputs differ, so the keys differ."""
    from marcus.workers.ocsr.handler import ocsr

    crop, _, crop_session, step = crop_step(monkeypatch, "molnextr")
    ocsr(step, crop_session)
    job = uuid.uuid4()
    p = image_job_path(job)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(crop.read_bytes())  # identical stored bytes
    job_session = FakeSession(OWNER)
    ocsr(view(image_job_id=job, engine="molnextr"), job_session)
    (crop_key,), (job_key,) = crop_session.writes, job_session.writes
    assert crop_key["image_sha256"] != job_key["image_sha256"]
    assert job_key["image_sha256"] == hashlib.sha256(crop.read_bytes()).hexdigest()


def test_black_and_white_crop_input_is_the_crop_itself(tmp_path):
    """Grey pixels have R == B, so the swap changes nothing (186 of 190 synth_190 crops)."""
    from marcus.workers.ocsr.handler import v1_engine_input

    p = tmp_path / "bw.png"
    im = Image.new("RGB", (5, 5), WHITE)
    im.putpixel((2, 2), (90, 90, 90))
    im.save(p)
    with Image.open(io.BytesIO(v1_engine_input(p))) as out:
        assert list(out.convert("RGB").get_flattened_data()) == list(im.get_flattened_data())


def test_engine_input_equals_v1_cv2_imwrite_of_the_library_crop(tmp_path):
    """Ties the helper to v1's real call: decimer_segmentation returns the crop as R, G, B, A (alpha
    255); v1 saves it with cv2.imwrite (backend/app/modules/decimer_segmentation_wrapper.py:147),
    which takes it as B, G, R, A. The helper's output, from v2's true-colour file, must decode to
    the same RGB pixels as that v1 file."""
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from marcus.workers.ocsr.handler import v1_engine_input

    rng = np.random.default_rng(7)
    rgba = np.full((6, 9, 4), 255, np.uint8)
    rgba[..., :3] = rng.integers(0, 256, size=(6, 9, 3), dtype=np.uint8)
    rgba[0, 0, :3], rgba[1, 1, :3] = RED, BLUE
    v1_file = tmp_path / "v1_page_0_0_segmented.png"
    assert cv2.imwrite(str(v1_file), rgba)  # exactly v1's call on the library's array
    v2_file = tmp_path / "v2_crop.png"
    Image.fromarray(np.ascontiguousarray(rgba[:, :, :3])).save(v2_file)  # v2: true colour

    with Image.open(v1_file) as a, Image.open(io.BytesIO(v1_engine_input(v2_file))) as b:
        v1_px, v2_px = np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB"))
    assert np.array_equal(v1_px, v2_px)
    assert tuple(v1_px[0, 0]) == BLUE  # v1's file really is swapped


def test_molparser_reads_a_segment_crop_in_true_colour(monkeypatch):
    """MolParser is no v1 engine: it gets the stored crop as it is (the cache key is its hash);
    the v1 engines get v1's red/blue-swapped crop (test above)."""
    from marcus.workers.ocsr.handler import ocsr

    use_engine(monkeypatch, "CCO", name="molparser")
    pid, sha = uuid.uuid4(), "cd" * 32
    crop = segment_crop_path(pid, sha)
    crop.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (200, 10, 10)).save(crop)
    session = FakeSession(SimpleNamespace(paper_id=pid, image_sha256=sha, owner_id=OWNER))
    assert ocsr(view(pid, segment_id=uuid.uuid4(), engine="molparser"), session)["valid"] is True
    (written,) = session.writes
    assert written["image_sha256"] == hashlib.sha256(crop.read_bytes()).hexdigest()
    assert written["engine"] == "molparser"
