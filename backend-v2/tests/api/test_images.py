import asyncio
import io
import threading
import uuid

from PIL import Image
from sqlalchemy import func, select

from marcus.api.routes import images as images_route
from marcus.api.security import ASSET_GET
from marcus.core import storage
from marcus.core.models import ImageJob, Prediction, Step
from marcus.core.pipeline import complete_step
from marcus.core.settings import get_settings
from tests.api._upload_helpers import image_bytes, pdf_bytes, upload_image
from tests.api._upload_helpers import upload as upload_paper
from tests.api.conftest import make_client, new_owner, ocsr_result

MB = 1024 * 1024


async def test_upload_creates_job_and_step(app, async_db_session):
    async with make_client(app) as c:
        r = await upload_image(c)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert "marcus_owner=" in r.headers["set-cookie"]
    job = (await async_db_session.execute(select(ImageJob))).scalar_one()
    assert str(job.id) == body["image_job_id"]
    assert job.engine == "decimer" and job.status == "queued" and job.display_name == "mol.png"
    step = (await async_db_session.execute(select(Step))).scalar_one()
    assert (step.kind, step.image_job_id, step.paper_id, step.seq, step.status) == (
        "ocsr",
        job.id,
        None,
        0,
        "pending",
    )
    assert step.engine == "decimer" and step.queue == "q.decimer"
    path = storage.image_job_path(job.id)
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(job.image_sha256) == 64


async def test_jpeg_is_stored_as_png(app, async_db_session):
    async with make_client(app) as c:
        r = await upload_image(c, image_bytes("JPEG"), name="x.jpg")
    assert r.status_code == 202
    job = (await async_db_session.execute(select(ImageJob))).scalar_one()
    saved = storage.image_job_path(job.id).read_bytes()
    assert saved[:8] == b"\x89PNG\r\n\x1a\n"
    import hashlib

    assert job.image_sha256 == hashlib.sha256(saved).hexdigest()


async def test_image_20mb_plus_one_is_413(app, async_db_session):
    data = image_bytes() + b"0" * (20 * MB + 1)
    async with make_client(app) as c:
        r = await upload_image(c, data)
    assert r.status_code == 413
    assert (await async_db_session.execute(select(ImageJob))).first() is None


async def test_pdf_sent_as_image_is_415(app):
    async with make_client(app) as c:
        r = await upload_image(c, pdf_bytes(), name="x.png")
    assert r.status_code == 415


async def test_corrupt_png_is_415(app):
    async with make_client(app) as c:
        r = await upload_image(c, b"\x89PNG\r\n\x1a\n" + b"junk" * 20)
    assert r.status_code == 415


async def test_decompression_bomb_is_413(app, async_db_session):
    # 8000 x 8000 = 64 MP: under the 10 000 side limit, over 50 MP
    data = image_bytes("PNG", (8000, 8000), mode="1")
    async with make_client(app) as c:
        r = await upload_image(c, data)
    assert r.status_code == 413
    assert (await async_db_session.execute(select(ImageJob))).first() is None


async def test_side_over_10000_is_413(app):
    data = image_bytes("PNG", (10001, 2), mode="1")
    async with make_client(app) as c:
        r = await upload_image(c, data)
    assert r.status_code == 413


async def test_fake_engine_refused_unless_enabled(app, monkeypatch):
    monkeypatch.delenv("MARCUS_ENABLE_FAKE_ENGINES", raising=False)
    get_settings.cache_clear()
    async with make_client(app) as c:
        r = await upload_image(c, engine="fake")
    assert r.status_code == 422


async def test_image_job_owned(app, async_db_session):
    async with make_client(app) as c:
        job_id = (await upload_image(c)).json()["image_job_id"]
        r = await c.get(f"/api/v2/images/{job_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == job_id and body["status"] == "queued"
        assert body["engine"] == "decimer" and body["display_name"] == "mol.png"
        assert body["prediction"] is None and body["error"] is None
        assert body["created_at"] and body["expires_at"]
        missing = await c.get("/api/v2/images/00000000-0000-0000-0000-000000000000")
    _, token = await new_owner(async_db_session)
    async with make_client(app, token) as other:
        theirs = await other.get(f"/api/v2/images/{job_id}")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_deleted_job_is_404(app, async_db_session):
    async with make_client(app) as c:
        job_id = (await upload_image(c)).json()["image_job_id"]
        job = (await async_db_session.execute(select(ImageJob))).scalar_one()
        job.status = "deleted"
        await async_db_session.commit()
        assert (await c.get(f"/api/v2/images/{job_id}")).status_code == 404


async def test_expired_job_is_same_404_as_missing(app, async_db_session):
    """Expired but not yet purged: not served, even to its owner."""
    from datetime import UTC, datetime, timedelta

    async with make_client(app) as c:
        job_id = (await upload_image(c)).json()["image_job_id"]
        job = (await async_db_session.execute(select(ImageJob))).scalar_one()
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await async_db_session.commit()
        expired = await c.get(f"/api/v2/images/{job_id}")
        missing = await c.get("/api/v2/images/00000000-0000-0000-0000-000000000000")
    assert expired.status_code == missing.status_code == 404
    assert expired.content == missing.content


async def test_get_returns_prediction_after_complete_step(app, async_db_session):
    async with make_client(app) as c:
        job_id = (await upload_image(c)).json()["image_job_id"]
        step = (await async_db_session.execute(select(Step))).scalar_one()
        step.status = "running"
        step.attempts += 1
        await async_db_session.commit()
        await async_db_session.run_sync(lambda s: complete_step(s, step.id, ocsr_result("CCO")))
        await async_db_session.commit()
        body = (await c.get(f"/api/v2/images/{job_id}")).json()
    assert body["status"] == "done"
    p = body["prediction"]
    assert p["smiles"] == "CCO" and p["valid"] is True and p["engine"] == "decimer"
    assert p["engine_version"] == "t1" and p["ms"] == 5 and "molfile" in p
    assert (await async_db_session.execute(select(Prediction))).scalar_one()


async def test_image_jobs_count_toward_active_limit(app):
    async with make_client(app) as c:
        assert (await upload_paper(c)).status_code == 202
        assert (await upload_paper(c)).status_code == 202
        assert (await upload_image(c)).status_code == 202
        assert (await upload_image(c)).status_code == 429
        assert (await upload_paper(c)).status_code == 429


async def test_image_jobs_count_toward_ip_limit(app, async_db_session, monkeypatch):
    monkeypatch.setenv("MARCUS_IP_MAX_ACTIVE_PAPERS", "2")
    monkeypatch.setenv("MARCUS_BROWSER_MAX_ACTIVE_PAPERS", "5")
    get_settings.cache_clear()
    async with make_client(app) as c1:
        assert (await upload_image(c1)).status_code == 202
    async with make_client(app) as c2:
        assert (await upload_image(c2)).status_code == 202
    async with make_client(app) as c3:
        assert (await upload_image(c3)).status_code == 429


def test_16bit_grayscale_is_scaled_not_clipped():
    import numpy as np

    from marcus.api.uploads import normalize_to_png

    arr = np.full((8, 8), 20000, dtype=np.uint16)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    out = Image.open(io.BytesIO(normalize_to_png(buf.getvalue())))
    assert out.mode == "RGB"
    assert set(out.getdata()) == {(78, 78, 78)}  # 20000 // 256


def test_32bit_int_grayscale_uses_data_range():
    import numpy as np

    from marcus.api.uploads import normalize_to_png

    arr = np.array([[0, 100000], [50000, 100000]], dtype=np.int32)
    buf = io.BytesIO()
    Image.fromarray(arr, "I").save(buf, "TIFF")
    out = Image.open(io.BytesIO(normalize_to_png(buf.getvalue())))
    px = list(out.convert("L").getdata())
    assert px[0] == 0 and px[3] == 255 and 100 < px[2] < 150


async def test_at_most_two_image_decodes_at_once(app, monkeypatch):
    """A third concurrent decode waits for a slot (the semaphore is per app / API process)."""
    assert get_settings().image_decode_concurrency == 2
    release = threading.Event()
    running = 0
    peak = 0
    lock = threading.Lock()

    def slow_png(data: bytes) -> bytes:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        release.wait(5)
        with lock:
            running -= 1
        return b"png"

    monkeypatch.setattr(images_route, "sniff_image", lambda data: None)
    monkeypatch.setattr(images_route, "normalize_to_png", slow_png)
    tasks = [
        asyncio.create_task(images_route.decode_image(app.state.decode_slots, b"x"))
        for _ in range(3)
    ]
    for _ in range(100):  # wait until two decodes are inside the threadpool
        if running == 2:
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)
    assert running == 2 and not any(t.done() for t in tasks)  # the third is waiting
    release.set()
    assert await asyncio.gather(*tasks) == [b"png"] * 3
    assert peak == 2


async def test_image_decode_concurrency_setting(monkeypatch):
    from marcus.api.main import create_app

    monkeypatch.setenv("MARCUS_IMAGE_DECODE_CONCURRENCY", "5")
    get_settings.cache_clear()
    app = create_app()
    assert app.state.decode_slots._value == 5


# --- F0-6: list, bytes, extra predictions, job out ---------------------------------------------


async def run_and_finish(db, step, result=None, fail=None):
    from marcus.core.enums import ErrorClass
    from marcus.core.pipeline import fail_step

    step.status = "running"
    step.attempts += 1
    await db.commit()
    if fail:
        await db.run_sync(lambda s: fail_step(s, step.id, ErrorClass(fail), "secret boom", False))
    else:
        await db.run_sync(lambda s: complete_step(s, step.id, result or ocsr_result("CCO")))
    await db.commit()


async def test_list_images_only_mine(app, async_db_session):
    async with make_client(app) as c:
        a = (await upload_image(c, name="a.png")).json()["image_job_id"]
        b = (await upload_image(c, name="b.png")).json()["image_job_id"]
        gone = (await upload_image(c, name="c.png")).json()["image_job_id"]
        job = await async_db_session.get(ImageJob, uuid.UUID(gone))
        job.status = "deleted"
        await async_db_session.commit()
        body = (await c.get("/api/v2/images")).json()
    _, token = await new_owner(async_db_session)
    async with make_client(app, token) as other:
        theirs = (await other.get("/api/v2/images")).json()
    assert theirs == {"jobs": []}
    assert [j["id"] for j in body["jobs"]] == [b, a]
    assert set(body["jobs"][0]) == {
        "id",
        "display_name",
        "status",
        "engine",
        "created_at",
        "expires_at",
    }
    assert body["jobs"][0]["display_name"] == "b.png"


async def test_image_bytes_owner_only(app, async_db_session):
    data = image_bytes()
    async with make_client(app) as c:
        job_id = (await upload_image(c, data)).json()["image_job_id"]
        r = await c.get(f"/api/v2/images/{job_id}/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert r.content.startswith(b"\x89PNG")
    assert ASSET_GET.match(f"/api/v2/images/{job_id}/image")
    _, token = await new_owner(async_db_session)
    async with make_client(app, token) as other:
        theirs = await other.get(f"/api/v2/images/{job_id}/image")
        missing = await other.get(f"/api/v2/images/{uuid.uuid4()}/image")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.content == missing.content


async def _job_and_step(c, db):
    job_id = (await upload_image(c)).json()["image_job_id"]
    step = (await db.execute(select(Step))).scalar_one()
    return job_id, step


async def test_image_predictions_second_engine(app, async_db_session):
    db = async_db_session
    async with make_client(app) as c:
        job_id, first = await _job_and_step(c, db)
        await run_and_finish(db, first)
        assert (await c.get(f"/api/v2/images/{job_id}")).json()["status"] == "done"
        r = await c.post(f"/api/v2/images/{job_id}/predictions", json={"engine": "molparser"})
        assert r.status_code == 202
        step_id = r.json()["step_id"]
        body = (await c.get(f"/api/v2/images/{job_id}")).json()
    assert body["status"] == "queued"
    new = await db.get(Step, uuid.UUID(step_id))
    assert (new.kind, new.engine, new.status, new.image_job_id) == (
        "ocsr",
        "molparser",
        "pending",
        uuid.UUID(job_id),
    )
    assert new.queue == "q.molparser"


async def test_image_predictions_repeat_click_same_step(app, async_db_session):
    db = async_db_session
    async with make_client(app) as c:
        job_id, _ = await _job_and_step(c, db)
        url = f"/api/v2/images/{job_id}/predictions"
        one = await c.post(url, json={"engine": "molscribe"})
        two = await c.post(url, json={"engine": "molscribe"})
        same_engine_as_upload = await c.post(url, json={"engine": "decimer"})
    assert one.status_code == two.status_code == 202
    assert one.json() == two.json()
    assert same_engine_as_upload.json()["step_id"] == str(
        (await db.execute(select(Step.id).where(Step.engine == "decimer"))).scalar_one()
    )
    assert (await db.execute(select(func.count()).select_from(Step))).scalar_one() == 2


async def test_image_predictions_fake_engine_refused(app, monkeypatch):
    monkeypatch.delenv("MARCUS_ENABLE_FAKE_ENGINES", raising=False)
    get_settings.cache_clear()
    async with make_client(app) as c:
        job_id = (await upload_image(c)).json()["image_job_id"]
        r = await c.post(f"/api/v2/images/{job_id}/predictions", json={"engine": "fake"})
    assert r.status_code == 422 and r.json() == {"detail": "Engine not available"}


async def test_image_job_out_lists_all_predictions_and_steps(app, async_db_session):
    db = async_db_session
    async with make_client(app) as c:
        job_id, first = await _job_and_step(c, db)
        await run_and_finish(db, first, ocsr_result("CCO"))
        step_id = (
            await c.post(f"/api/v2/images/{job_id}/predictions", json={"engine": "molparser"})
        ).json()["step_id"]
        second = await db.get(Step, uuid.UUID(step_id))
        await run_and_finish(db, second, ocsr_result("CCC"))
        body = (await c.get(f"/api/v2/images/{job_id}")).json()
    assert body["status"] == "done"
    assert [p["smiles"] for p in body["predictions"]] == ["CCC", "CCO"]
    assert body["prediction"]["smiles"] == "CCC"
    assert [(s["engine"], s["status"], s["error_class"]) for s in body["steps"]] == [
        ("molparser", "done", None),
        ("decimer", "done", None),
    ]
    assert body["error_class"] is None


async def test_image_job_second_engine_fails_job_stays_done(app, async_db_session):
    db = async_db_session
    async with make_client(app) as c:
        job_id, first = await _job_and_step(c, db)
        await run_and_finish(db, first)
        step_id = (
            await c.post(f"/api/v2/images/{job_id}/predictions", json={"engine": "molparser"})
        ).json()["step_id"]
        await run_and_finish(db, await db.get(Step, uuid.UUID(step_id)), fail="timeout")
        body = (await c.get(f"/api/v2/images/{job_id}")).json()
    assert body["status"] == "done" and body["error"] is None
    assert body["error_class"] == "timeout"
    assert body["steps"][0] == {"engine": "molparser", "status": "failed", "error_class": "timeout"}
    assert len(body["predictions"]) == 1


async def test_image_job_only_engine_fails_job_failed_with_error_class(app, async_db_session):
    db = async_db_session
    async with make_client(app) as c:
        job_id, first = await _job_and_step(c, db)
        await run_and_finish(db, first, fail="engine_error")
        r = await c.get(f"/api/v2/images/{job_id}")
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_class"] == "engine_error"
    assert body["predictions"] == [] and body["prediction"] is None
    assert body["error"] == "secret boom"  # kept for compatibility, never shown by the UI
