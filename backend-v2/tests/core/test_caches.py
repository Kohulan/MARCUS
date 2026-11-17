"""Segmentation cache (planner) and OCSR cache (ocsr handler).

Spec §7: cached results are copied into the new owner's paper (new ids, new paths, only crop
bytes identical by hash), so the cache never shows one owner's data to another.
"""

import hashlib
import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import func, select

from marcus.core import storage
from marcus.core.db import get_sync_sessionmaker
from marcus.core.enums import Engine, ErrorClass
from marcus.core.models import Curation, OcsrCache, Paper, Prediction, SegCache, Segment, Step
from marcus.core.pipeline import BadResult, cancel_paper, complete_step, fail_step
from marcus.core.settings import get_settings
from tests.factories import make_owner, make_paper

SEG_V = "segv-1"
OCSR = {"smiles": "CCO", "molfile": None, "valid": True, "ms": 12, "engine_version": "2.7"}


@pytest.fixture(autouse=True)
def _seg_version(monkeypatch):
    monkeypatch.setenv("MARCUS_SEG_VERSION", SEG_V)
    get_settings.cache_clear()
    yield


def _png(page: int, idx: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8 + idx, 8 + page), (page * 40 % 256, idx * 70 % 256, 9)).save(buf, "PNG")
    return buf.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def steps(s, paper, kind=None, status=None) -> list[Step]:
    q = select(Step).where(Step.paper_id == paper.id)
    if kind:
        q = q.where(Step.kind == kind)
    if status:
        q = q.where(Step.status == status)
    return list(s.execute(q.order_by(Step.seq)).scalars())


def segments_of(s, paper) -> list[Segment]:
    q = select(Segment).where(Segment.paper_id == paper.id).order_by(Segment.page, Segment.idx)
    return list(s.execute(q).scalars())


def finish(s, step, result) -> list[Step]:
    step.status = "running"
    step.attempts += 1
    s.flush()
    return complete_step(s, step.id, result)


def segment_result(paper, page: int, per_page: int = 2, version: str = SEG_V) -> dict:
    """What the segment worker returns, with the crops written like the worker does."""
    items = []
    for idx in range(per_page):
        data = _png(page, idx)
        crop = storage.segment_crop_path(paper.id, _sha(data))
        crop.parent.mkdir(parents=True, exist_ok=True)
        crop.write_bytes(data)
        items.append(
            {"idx": idx, "bbox": [idx, page, idx + 10, page + 10], "image_sha256": _sha(data)}
        )
    return {"segments": items, "seg_version": version}


def drive(s, paper, pages=2, seg=segment_result, fail_segment_pages=()) -> list[str]:
    """Run every pending step of the paper to the end; return the kinds that ran, in order."""
    ran = []
    while True:
        pending = steps(s, paper, status="pending")
        if not pending:
            return ran
        for st in pending:
            ran.append(st.kind)
            if st.kind == "check_pdf":
                finish(s, st, {"pages": pages})
            elif st.kind == "render_page":
                finish(s, st, {})
            elif st.kind == "segment_page":
                if st.page in fail_segment_pages:
                    st.status = "running"
                    st.attempts = 2
                    s.flush()
                    fail_step(s, st.id, ErrorClass.ENGINE_ERROR, "boom", retryable=True)
                else:
                    finish(s, st, seg(paper, st.page))
            elif st.kind == "ocsr":
                finish(s, st, OCSR)
            elif st.kind == "doi":
                finish(s, st, {"doi": None})
            else:
                finish(s, st, {})


def cache_rows(s) -> list[SegCache]:
    return list(s.execute(select(SegCache)).scalars())


def done_first_paper(s, owner=None, pages=2) -> Paper:
    paper = make_paper(s, owner)
    ran = drive(s, paper, pages=pages)
    assert ran.count("segment_page") == pages
    s.refresh(paper)
    assert paper.status == "done"
    return paper


# --- segmentation cache ----------------------------------------------------------------------


def test_same_pdf_twice_same_owner_two_papers_second_from_cache(db_session):
    s = db_session
    owner = make_owner(s)
    a = done_first_paper(s, owner)
    (row,) = cache_rows(s)
    assert (row.pdf_sha256, row.seg_version) == (a.pdf_sha256, f"{SEG_V}|dpi300|rgb")
    assert row.payload["pages"] == 2 and len(row.payload["segments"]) == 4

    b = make_paper(s, owner)
    ran = drive(s, b)
    s.refresh(b)
    assert a.id != b.id and b.status == "done"
    assert "segment_page" not in ran and steps(s, b, "segment_page") == []
    assert ran.count("render_page") == 2 and ran.count("ocsr") == 4
    seg_a, seg_b = segments_of(s, a), segments_of(s, b)
    assert len(seg_b) == len(seg_a) == 4
    key = lambda g: (g.page, g.idx, g.bbox, g.image_sha256)  # noqa: E731
    assert [key(g) for g in seg_b] == [key(g) for g in seg_a]
    for g in seg_b:
        crop = storage.segment_crop_path(b.id, g.image_sha256)
        assert _sha(crop.read_bytes()) == g.image_sha256
    assert {c.status for c in s.execute(select(Curation)).scalars()} == {"unchecked"}
    # each of b's ocsr steps points at b's own segment
    b_ocsr = steps(s, b, "ocsr")
    assert {st.segment_id for st in b_ocsr} == {g.id for g in seg_b}
    assert len(cache_rows(s)) == 1


def test_cache_never_exposes_other_owner_ids(db_session):
    s = db_session
    a = done_first_paper(s, make_owner(s))
    seg_a = segments_of(s, a)
    cur = s.get(Curation, seg_a[0].id)
    cur.status, cur.smiles, cur.note = "accepted", "CCN", "owner A's private note"
    a.display_name = "owner-a-secret.pdf"
    s.flush()

    owner_b = make_owner(s)
    b = make_paper(s, owner_b)
    ran = drive(s, b)
    assert "segment_page" not in ran
    seg_b = segments_of(s, b)
    a_ids = {g.id for g in seg_a}
    assert seg_b and all(g.paper_id == b.id for g in seg_b)
    assert not a_ids & {g.id for g in seg_b}
    for g in seg_b:
        crop = storage.segment_crop_path(b.id, g.image_sha256)
        assert crop.is_file() and storage.paper_dir(b.id) in crop.parents
        c = s.get(Curation, g.id)
        assert (c.status, c.smiles, c.note) == ("unchecked", None, None)
    preds_b = list(
        s.execute(
            select(Prediction).where(Prediction.segment_id.in_([g.id for g in seg_b]))
        ).scalars()
    )
    assert len(preds_b) == 4  # b's own ocsr steps, none copied
    for st in steps(s, b):
        assert st.paper_id == b.id
        assert st.segment_id is None or st.segment_id not in a_ids
    s.refresh(b)
    assert b.display_name == "paper.pdf" and b.owner_id == owner_b.id
    payload = cache_rows(s)[0].payload
    flat = repr(payload)
    for leaked in (str(a.id), str(a.owner_id), "owner-a-secret", "private note", "CCN"):
        assert leaked not in flat
    assert all(str(i) not in flat for i in a_ids)


def test_partial_result_not_cached(db_session):
    s = db_session
    paper = make_paper(s)
    drive(s, paper, fail_segment_pages=(1,))
    s.refresh(paper)
    assert paper.status == "done"
    assert cache_rows(s) == []


def test_failed_render_not_cached(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    finish(s, check, {"pages": 2})
    r1 = steps(s, paper, "render_page")[1]
    r1.status, r1.attempts = "running", 2
    s.flush()
    fail_step(s, r1.id, ErrorClass.ENGINE_ERROR, "boom", retryable=True)
    drive(s, paper)
    s.refresh(paper)
    assert paper.status == "done" and cache_rows(s) == []


def test_mixed_seg_versions_not_cached(db_session):
    s = db_session
    paper = make_paper(s)

    def seg(p, page):
        return segment_result(p, page, version=SEG_V if page == 0 else "other")

    drive(s, paper, seg=seg)
    assert cache_rows(s) == []


def test_crop_missing_falls_back_to_segment_page_for_that_page(db_session):
    s = db_session
    a = done_first_paper(s)
    gone = [g for g in segments_of(s, a) if g.page == 1][0]
    storage.segment_crop_path(a.id, gone.image_sha256).unlink()

    b = make_paper(s)
    ran = drive(s, b)
    s.refresh(b)
    assert b.status == "done"
    assert [st.page for st in steps(s, b, "segment_page")] == [1]
    assert ran.count("segment_page") == 1
    assert len(segments_of(s, b)) == 4
    for g in segments_of(s, b):
        assert storage.segment_crop_path(b.id, g.image_sha256).is_file()


def test_deleted_source_paper_is_not_a_crop_source(db_session):
    s = db_session
    a = done_first_paper(s)
    # the files stay, but a deleted paper must never serve as a source
    cancel_paper(s, a.id)
    for g in segments_of(s, a):
        crop = storage.segment_crop_path(a.id, g.image_sha256)
        crop.parent.mkdir(parents=True, exist_ok=True)
        crop.write_bytes(_png(g.page, g.idx))
    b = make_paper(s)
    drive(s, b)
    assert [st.page for st in steps(s, b, "segment_page")] == [0, 1]


@pytest.mark.parametrize("version", ["segv-2", ""])
def test_seg_version_mismatch_or_unset_no_cache_use(db_session, monkeypatch, version):
    s = db_session
    done_first_paper(s)
    assert len(cache_rows(s)) == 1
    monkeypatch.setenv("MARCUS_SEG_VERSION", version)
    get_settings.cache_clear()
    b = make_paper(s)
    ran = drive(s, b)
    assert ran.count("segment_page") == 2
    s.refresh(b)
    assert b.status == "done"


def test_cache_pages_mismatch_is_ignored(db_session):
    s = db_session
    done_first_paper(s)
    b = make_paper(s)
    ran = drive(s, b, pages=3)  # cache says 2 pages: never trusted for a 3-page result
    assert ran.count("segment_page") == 3


def test_zero_segment_page_from_cache(db_session):
    s = db_session

    def seg(p, page):
        return segment_result(p, page, per_page=0 if page == 0 else 1)

    a = make_paper(s)
    drive(s, a, seg=seg)
    assert len(cache_rows(s)) == 1
    b = make_paper(s)
    ran = drive(s, b, seg=seg)
    assert "segment_page" not in ran
    assert [(g.page, g.idx) for g in segments_of(s, b)] == [(1, 0)]


@pytest.mark.parametrize("bad", [None, "", "x" * 201, 7])
def test_segment_page_result_needs_seg_version(db_session, bad):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    finish(s, check, {"pages": 1})
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    result = segment_result(paper, 0)
    if bad is None:
        del result["seg_version"]
    else:
        result["seg_version"] = bad
    with pytest.raises(BadResult):
        finish(s, seg_step, result)


def test_seg_cache_survives_concurrent_writer(db_session):
    """The insert is ON CONFLICT DO NOTHING: an existing row (another paper) is kept."""
    s = db_session
    paper = make_paper(s)
    s.add(SegCache(pdf_sha256=paper.pdf_sha256, seg_version=f"{SEG_V}|dpi300|rgb", payload={"x": 1}))
    s.flush()
    drive(s, paper)
    s.refresh(paper)
    assert paper.status == "done"
    (row,) = cache_rows(s)
    assert row.payload == {"x": 1}


def test_malformed_cache_payload_is_a_miss(db_session):
    s = db_session
    paper = make_paper(s)
    s.add(
        SegCache(
            pdf_sha256=paper.pdf_sha256,
            seg_version=f"{SEG_V}|dpi300|rgb",
            payload={"pages": 2, "segments": [{"page": 0, "idx": "x"}]},
        )
    )
    s.flush()
    ran = drive(s, paper)
    assert ran.count("segment_page") == 2


# --- OCSR cache ------------------------------------------------------------------------------


class CountingEngine:
    name = Engine.DECIMER

    def __init__(self, smiles, version="stub-9"):
        self.smiles = smiles
        self.version = version
        self.calls = 0

    def load(self):
        pass

    def predict(self, image):
        from marcus.workers.ocsr.base import OcsrResult

        self.calls += 1
        return OcsrResult(self.smiles, "MOLFILE" if self.smiles else None)


@pytest.fixture
def engine_slot(monkeypatch):
    from marcus.workers.ocsr import base

    monkeypatch.setattr(base, "_ENGINES", {})

    def use(engine):
        base._ENGINES.clear()
        monkeypatch.setitem(base.FACTORIES, "decimer", lambda: engine)
        return engine

    return use


def _job_image(color=(255, 255, 255)) -> uuid.UUID:
    job = uuid.uuid4()
    p = storage.image_job_path(job)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), color).save(p)
    return job


def _run_ocsr(job, engine="decimer"):
    from marcus.workers.ocsr.handler import ocsr
    from tests.workers.helpers import view

    with get_sync_sessionmaker()() as reads:
        try:
            return ocsr(view(image_job_id=job, engine=engine), reads)
        finally:
            reads.rollback()


def test_ocsr_cache_hit_skips_engine(db_session, engine_slot):
    eng = engine_slot(CountingEngine("c1ccccc1"))
    job = _job_image()
    first = _run_ocsr(job)
    assert eng.calls == 1
    sha = _sha(storage.image_job_path(job).read_bytes())
    (row,) = db_session.execute(select(OcsrCache)).scalars()
    assert (row.image_sha256, row.engine, row.engine_version) == (sha, "decimer", "stub-9")
    assert (row.smiles, row.molfile) == ("c1ccccc1", "MOLFILE")

    # same bytes in another job (another owner): served from the cache, engine not called
    eng2 = engine_slot(CountingEngine("SHOULD-NOT-RUN"))
    second = _run_ocsr(_job_image())
    assert eng2.calls == 0
    assert second == {
        "smiles": "c1ccccc1",
        "molfile": "MOLFILE",
        "valid": True,
        "ms": 0,
        "cached": True,
        "engine_version": "stub-9",
    }
    assert first["smiles"] == second["smiles"]


def test_ocsr_cache_keyed_by_engine_version(db_session, engine_slot):
    engine_slot(CountingEngine("CCO", version="v1"))
    _run_ocsr(_job_image())
    eng = engine_slot(CountingEngine("CCN", version="v2"))
    out = _run_ocsr(_job_image())
    assert eng.calls == 1 and out["smiles"] == "CCN" and out["engine_version"] == "v2"
    n = db_session.execute(select(func.count()).select_from(OcsrCache)).scalar_one()
    assert n == 2


def test_ocsr_empty_prediction_not_cached(db_session, engine_slot):
    engine_slot(CountingEngine(""))
    out = _run_ocsr(_job_image())
    assert out["smiles"] == "" and out["valid"] is False
    assert db_session.execute(select(func.count()).select_from(OcsrCache)).scalar_one() == 0
    eng = engine_slot(CountingEngine(""))
    _run_ocsr(_job_image())
    assert eng.calls == 1


def test_ocsr_cache_hit_recomputes_valid(db_session, engine_slot):
    eng = engine_slot(CountingEngine("C1CC"))  # not a valid SMILES (open ring)
    job = _job_image()
    sha = _sha(storage.image_job_path(job).read_bytes())
    db_session.add(
        OcsrCache(
            image_sha256=sha,
            engine="decimer",
            engine_version="stub-9",
            smiles="c1ccccc1",
            molfile=None,
        )
    )
    db_session.commit()
    out = _run_ocsr(job)
    assert eng.calls == 0
    assert out["smiles"] == "c1ccccc1" and out["valid"] is True and out["ms"] == 0


def test_ocsr_cache_rows_hold_no_owner_data(db_session, engine_slot):
    engine_slot(CountingEngine("CCO"))
    _run_ocsr(_job_image())
    cols = {c.name for c in OcsrCache.__table__.columns}
    assert cols == {"image_sha256", "engine", "engine_version", "smiles", "molfile", "created_at"}


class LazyStub(CountingEngine):
    """A lazily loaded engine (like decimer-hand) that counts its loads."""

    name = Engine.DECIMER_HAND

    def __init__(self, smiles, version="2.8.0-hand"):
        super().__init__(smiles, version)
        self.loads = 0

    def load(self):
        self.loads += 1


def test_ocsr_cache_hit_on_lazy_engine_does_not_load_the_model(db_session, monkeypatch):
    from marcus.workers.ocsr import base

    monkeypatch.setattr(base, "_ENGINES", {})
    built = []

    def factory():
        built.append(LazyStub("SHOULD-NOT-RUN"))
        return built[-1]

    monkeypatch.setitem(base.FACTORIES, "decimer-hand", factory)
    job = _job_image()
    sha = _sha(storage.image_job_path(job).read_bytes())
    db_session.add(OcsrCache(image_sha256=sha, engine="decimer-hand", engine_version="2.8.0-hand",
                             smiles="CCO", molfile=None))  # fmt: skip
    db_session.commit()
    out = _run_ocsr(job, engine="decimer-hand")
    assert out["smiles"] == "CCO" and out["ms"] == 0 and out["engine_version"] == "2.8.0-hand"
    assert sum(e.loads for e in built) == 0 and sum(e.calls for e in built) == 0
    assert "decimer-hand" not in base._ENGINES  # nothing loaded for the hit

    # a miss loads once and predicts
    out = _run_ocsr(_job_image((0, 0, 0)), engine="decimer-hand")
    assert out["smiles"] == "SHOULD-NOT-RUN"
    assert sum(e.loads for e in built) == 1 and sum(e.calls for e in built) == 1


def test_fake_engine_bypasses_the_ocsr_cache(db_session, monkeypatch):
    from marcus.workers.ocsr import base

    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(base, "_ENGINES", {})
    job = _job_image()
    sha = _sha(storage.image_job_path(job).read_bytes())
    db_session.add(OcsrCache(image_sha256=sha, engine="fake", engine_version="fake-1",
                             smiles="CCO", molfile=None))  # fmt: skip
    db_session.commit()
    out = _run_ocsr(job, engine="fake")
    assert out["smiles"] == "c1ccccc1"  # the engine ran; the planted row was not read
    _run_ocsr(_job_image((0, 0, 0)), engine="fake")
    rows = db_session.execute(select(OcsrCache.smiles)).scalars().all()
    assert rows == ["CCO"]  # nothing written for the fake engine
