"""The annotation routes: start, read, curation, reset; ownership and the rate limit."""

import json
import uuid

import pytest
from sqlalchemy import select, update

from marcus.core import annotation as ann
from marcus.core import storage
from marcus.core.models import Annotation, Paper, Step
from tests.api.conftest import finish, make_client, new_owner, paper_row, seed_paper, steps_of

TEXT = {
    "body": {"children": [{"$ref": f"#/texts/{i}"} for i in range(3)]},
    "texts": [
        {"self_ref": "#/texts/0", "label": "title", "text": "Taxanes from Taxus brevifolia",
         "prov": [{"page_no": 1}]},
        {"self_ref": "#/texts/1", "label": "text", "prov": [{"page_no": 1}],
         "text": "Two taxanes were isolated from the bark of Taxus brevifolia in Oregon."},
        {"self_ref": "#/texts/2", "label": "text", "prov": [{"page_no": 2}],
         "text": "The bark was collected in Oregon (USA)."},
    ],
}  # fmt: skip


def model_result(**fields) -> dict:
    output = {f: list(fields.get(f, [])) for f in ann.FIELDS}
    blocks = ann.docling_blocks(TEXT)
    return {
        "model": "qwen3.5-9b-marcus-v1",
        "model_version": "Q8_0 llama.cpp b12554",
        "output": output,
        "positions": ann.positions(ann.Locator(blocks), output),
        "ms": 900,
    }


async def text_ready(db, paper_id) -> None:
    """Finish the seeded paper's docling and doi steps; write its Docling document."""

    def run(s):
        for kind in ("docling", "doi"):
            (step,) = steps_of(s, paper_id, kind)
            finish(s, step, {"text_path": "text.json"} if kind == "docling" else {"doi": None})

    await db.run_sync(run)
    await db.commit()
    (storage.paper_dir(paper_id) / "text.json").write_text(json.dumps(TEXT))


async def run_annotate(db, paper_id, result) -> None:
    def run(s):
        (step,) = steps_of(s, paper_id, "annotate", "pending")
        finish(s, step, result)

    await db.run_sync(run)
    await db.commit()


@pytest.fixture
def enabled(monkeypatch, clear_settings_cache):
    """Annotation offered, and a live q.llm consumer (the /ready consumer check, faked)."""
    from marcus.api.routes import health

    monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "1")
    clear_settings_cache()
    monkeypatch.setattr(health, "inspect_live_queues", lambda: {"q.cpu", "q.llm"})
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())


@pytest.fixture
async def ready(app, async_db_session, enabled):
    """An owner and a done paper with text; (token, paper_id, other owner's token)."""
    db = async_db_session
    alice, token = await new_owner(db)
    _, bob = await new_owner(db)
    seeded = await seed_paper(db, alice)
    await text_ready(db, seeded.paper_id)
    assert (await paper_row(db, seeded.paper_id)).status == "done"
    return token, seeded.paper_id, bob


async def test_a_paper_without_annotation(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{seeded.paper_id}/annotation")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False and body["status"] == "none" and body["step"] is None
    assert [f["key"] for f in body["fields"]] == list(ann.FIELDS)
    assert body["fields"][3] == {
        "key": "organism_or_species", "label": "Organism", "max_length": 676
    }  # fmt: skip
    # the editor's per-value limit comes from here (B-M7): the model's maxLength per field
    assert {f["key"]: f["max_length"] for f in body["fields"]} == ann.MAX_LENGTH
    # and the save's count limits (the PUT's 422 lines)
    assert body["limits"] == {"max_values_per_field": 200, "max_total_values": 300}
    for key in ("output", "positions", "curated", "curated_positions", "values", "coconut"):
        assert body[key] is None


async def test_start_is_503_where_annotation_is_not_available(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    async with make_client(app, token) as c:
        own = await c.post(f"/api/v2/papers/{seeded.paper_id}/annotation")
        missing = await c.post(f"/api/v2/papers/{uuid.uuid4()}/annotation")
    assert own.status_code == missing.status_code == 503
    assert own.json() == missing.json() == {"detail": "Annotation is not available"}


async def test_start_needs_the_text(app, async_db_session, enabled):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)  # docling still pending
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/papers/{seeded.paper_id}/annotation")
    assert r.status_code == 409 and r.json() == {"detail": "The text of this paper is not ready"}


async def test_start_progress_and_result(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        r = await c.post(f"/api/v2/papers/{paper_id}/annotation")
        assert r.status_code == 202
        step_id = r.json()["step_id"]
        again = await c.post(f"/api/v2/papers/{paper_id}/annotation", json={"rerun": True})
        assert again.status_code == 202 and again.json()["step_id"] == step_id  # repeat click
        # beside the read: the paper stays done; the client reads GET until the step ends
        assert (await paper_row(db, paper_id)).status == "done"
        pending = (await c.get(f"/api/v2/papers/{paper_id}/annotation")).json()
        assert pending["status"] == "pending" and pending["step"]["id"] == step_id
        assert pending["step"]["kind"] == "annotate" and pending["values"] is None

        await run_annotate(
            db,
            paper_id,
            model_result(organism_or_species=["Taxus brevifolia"], geo_location=["Oregon"],
                         organism_part=["bark"], Kingdom=["Plant"]),
        )  # fmt: skip
        done = (await c.get(f"/api/v2/papers/{paper_id}/annotation")).json()
    assert (await paper_row(db, paper_id)).status == "done"
    assert done["status"] == "done" and done["available"] is True
    assert done["model"] == "qwen3.5-9b-marcus-v1"
    assert done["values"] == done["output"]
    assert done["values"]["organism_or_species"] == ["Taxus brevifolia"]
    assert done["positions"]["geo_location"]["Oregon"] == [[1, 63, 69], [2, 26, 32]]
    assert done["curated"] is None and done["curated_positions"] is None
    assert done["coconut"] == {
        "organisms": [{"name": "Taxus brevifolia", "parts": "bark", "location": "Oregon",
                       "ecosystems": ""}],
        "kingdom": ["Plant"],
    }  # fmt: skip


async def test_an_annotation_run_is_outside_the_papers_read(app, async_db_session, ready):
    """Annotation runs beside the read (it starts by itself): it never makes the paper busy,
    is not in its steps or step counts (the progress bar), and no paper field says it."""
    db = async_db_session
    token, paper_id, _ = ready
    async with make_client(app, token) as c:

        async def seen() -> tuple:
            listed = (await c.get("/api/v2/papers")).json()["papers"]
            detail = (await c.get(f"/api/v2/papers/{paper_id}")).json()
            kinds = [
                s["kind"] for s in (await c.get(f"/api/v2/papers/{paper_id}/steps")).json()["steps"]
            ]
            assert "annotating" not in listed[0] and "annotating" not in detail
            return (
                listed[0]["status"], detail["status"],
                "annotate" in kinds, sum(detail["counts"]["steps_by_status"].values()),
            )  # fmt: skip

        before = await seen()
        assert before[:3] == ("done", "done", False)
        assert (await c.post(f"/api/v2/papers/{paper_id}/annotation")).status_code == 202
        assert await seen() == before
        await run_annotate(db, paper_id, model_result())
        assert await seen() == before


async def test_get_says_when_the_annotation_will_start_by_itself(app, async_db_session, ready):
    """`auto_pending`: the text is read, nothing was asked yet, and a worker serves q.llm, so
    the dispatcher starts it within seconds (the client keeps reading GET)."""
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        first = (await c.get(f"/api/v2/papers/{paper_id}/annotation")).json()
        assert first["auto_pending"] is True and first["status"] == "none"
        assert (await c.post(f"/api/v2/papers/{paper_id}/annotation")).status_code == 202
        after = (await c.get(f"/api/v2/papers/{paper_id}/annotation")).json()
    assert after["auto_pending"] is False and after["status"] == "pending"


async def _age_docling(db, paper_id, seconds: float) -> None:
    from datetime import UTC, datetime, timedelta

    await db.execute(
        update(Step)
        .where(Step.paper_id == paper_id, Step.kind == "docling")
        .values(finished_at=datetime.now(UTC) - timedelta(seconds=seconds))
    )
    await db.commit()


async def test_auto_pending_is_only_the_moment_before_it_starts(
    app, async_db_session, ready, monkeypatch, clear_settings_cache
):
    """`auto_pending` covers the few dispatcher passes after the text was read. If nothing
    started by then (the dispatcher skipped it: no worker, the feature off there), the manual
    action shows again, never a "Annotating…" that waits for nothing."""
    db = async_db_session
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        url = f"/api/v2/papers/{paper_id}/annotation"
        assert (await c.get(url)).json()["auto_pending"] is True
        await _age_docling(db, paper_id, 120)
        assert (await c.get(url)).json()["auto_pending"] is False
        await _age_docling(db, paper_id, 0)
        monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "0")
        clear_settings_cache()
        assert (await c.get(url)).json()["auto_pending"] is False


async def test_a_polled_get_never_asks_the_broker(app, async_db_session, ready, monkeypatch):
    async def boom():
        raise AssertionError("GET must not wait on the consumer broadcast")

    token, paper_id, _ = ready
    monkeypatch.setattr(app.state, "live_queues", boom)
    async with make_client(app, token) as c:
        r = await c.get(f"/api/v2/papers/{paper_id}/annotation")
    assert r.status_code == 200 and r.json()["auto_pending"] is True


async def test_annotated_paper_is_kept_unless_a_rerun_is_asked(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result(Kingdom=["Plant"]))
        kept = await c.post(f"/api/v2/papers/{paper_id}/annotation", json={})
        assert kept.status_code == 200 and kept.json() == {"step_id": None}
        assert (await paper_row(db, paper_id)).status == "done"
        rerun = await c.post(f"/api/v2/papers/{paper_id}/annotation", json={"rerun": True})
        assert rerun.status_code == 202 and rerun.json()["step_id"]
        bad = await c.post(f"/api/v2/papers/{paper_id}/annotation", json={"rerun": "x", "y": 1})
        assert bad.status_code == 422


async def test_curation_save_and_reset(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    url = f"/api/v2/papers/{paper_id}/annotation/curation"
    values = {f: [] for f in ann.FIELDS}
    values["organism_or_species"] = ["  Taxus   brevifolia ", "Taxus brevifolia", "", "T. x"]
    values["geo_location"] = ["Oregon", "USA"]
    async with make_client(app, token) as c:
        early = await c.put(url, json={"values": values})
        assert early.status_code == 409
        assert early.json() == {"detail": "This paper has no annotation yet"}
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result(Kingdom=["Plant"], geo_location=["Oregon"]))
        r = await c.put(url, json={"values": values})
        assert r.status_code == 200
        body = r.json()
        assert body["curated"]["organism_or_species"] == ["Taxus brevifolia", "T. x"]
        assert body["values"] == body["curated"]
        assert body["output"]["Kingdom"] == ["Plant"]  # the model output is kept
        assert body["curated_positions"]["geo_location"]["USA"] == [[2, 34, 37]]
        assert body["curated_positions"]["organism_or_species"]["T. x"] == []
        assert body["curated_at"] is not None
        assert body["coconut"]["organisms"][1]["name"] == "T. x"
        again = (await c.get(f"/api/v2/papers/{paper_id}/annotation")).json()
        assert again["curated"] == body["curated"]

        reset = await c.delete(url)
        assert reset.status_code == 200
        body = reset.json()
        assert body["curated"] is None and body["curated_positions"] is None
        assert body["values"] == body["output"] and body["curated_at"] is None
        again = await c.delete(url)
        assert again.status_code == 200  # idempotent


@pytest.mark.parametrize(
    "payload",
    [
        {"values": {f: [] for f in ann.FIELDS[:-1]}},
        {"values": {**{f: [] for f in ann.FIELDS}, "extra": []}},
        {"values": {f: [] for f in ann.FIELDS}, "more": 1},
        {"values": {**{f: [] for f in ann.FIELDS}, "Kingdom": ["x" * 61]}},
        {"values": {**{f: [] for f in ann.FIELDS}, "Kingdom": ["a"] * 201}},
        {"values": {**{f: [] for f in ann.FIELDS}, "Kingdom": "Plant"}},
        {"values": {**{f: [] for f in ann.FIELDS}, "Kingdom": [3]}},
    ],
)
async def test_curation_payloads_outside_the_shape_are_422(app, async_db_session, ready, payload):
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        r = await c.put(f"/api/v2/papers/{paper_id}/annotation/curation", json=payload)
    assert r.status_code == 422
    assert all("input" not in err for err in r.json()["detail"])  # never echoes the payload


async def test_hidden_characters_are_stripped_from_curated_values(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    values = {f: [] for f in ann.FIELDS}
    values["Kingdom"] = ["Pl\u202eant\u0000", "\u200b"]
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result())
        r = await c.put(f"/api/v2/papers/{paper_id}/annotation/curation", json={"values": values})
    assert r.status_code == 200 and r.json()["curated"]["Kingdom"] == ["Plant"]


async def test_other_owners_get_the_same_404_as_a_missing_paper(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, bob = ready
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
    await run_annotate(db, paper_id, model_result(Kingdom=["Plant"]))
    body = {"values": {f: [] for f in ann.FIELDS}}
    calls = [
        ("GET", "/annotation", None),
        ("POST", "/annotation", None),
        ("POST", "/annotation", {"rerun": True}),
        ("PUT", "/annotation/curation", body),
        ("DELETE", "/annotation/curation", None),
    ]
    async with make_client(app, bob) as c:
        for method, suffix, payload in calls:
            theirs = await c.request(method, f"/api/v2/papers/{paper_id}{suffix}", json=payload)
            missing = await c.request(
                method, f"/api/v2/papers/{uuid.uuid4()}{suffix}", json=payload
            )
            assert theirs.status_code == missing.status_code == 404, (method, suffix)
            assert theirs.content == missing.content
    row = (await db.execute(select(Annotation).where(Annotation.paper_id == paper_id))).scalar_one()
    assert row.curated is None  # untouched
    runs = (
        await db.execute(select(Step).where(Step.paper_id == paper_id, Step.kind == "annotate"))
    ).scalars()
    assert len(list(runs)) == 1


async def test_deleted_paper_is_404_and_its_annotation_is_gone(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result(Kingdom=["Plant"]))
        gone = await c.delete(f"/api/v2/papers/{paper_id}")
        assert gone.status_code == 204
        for method in ("GET", "POST"):
            r = await c.request(method, f"/api/v2/papers/{paper_id}/annotation")
            assert r.status_code == 404
    gone = (await db.execute(select(Annotation).where(Annotation.paper_id == paper_id))).first()
    assert gone is None


async def test_start_is_rate_limited_per_owner(app, async_db_session, ready, monkeypatch):
    db = async_db_session
    token, paper_id, bob = ready
    async with make_client(app, token) as c:
        codes = [
            (await c.post(f"/api/v2/papers/{paper_id}/annotation")).status_code for _ in range(5)
        ]
        assert codes == [202] * 5
        r = await c.post(f"/api/v2/papers/{paper_id}/annotation")
        assert r.status_code == 429 and r.json() == {"detail": "rate limited"}
        assert int(r.headers["retry-after"]) >= 1
    async with make_client(app, bob) as c:  # another owner has its own bucket
        assert (await c.post(f"/api/v2/papers/{uuid.uuid4()}/annotation")).status_code == 404
    runs = await db.execute(select(Step).where(Step.paper_id == paper_id, Step.kind == "annotate"))
    assert len(list(runs.scalars())) == 1  # idempotent: one step for the whole burst


async def test_expired_paper_is_404(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    await db.execute(update(Paper).where(Paper.id == paper_id).values(expires_at=Paper.created_at))
    await db.commit()
    async with make_client(app, token) as c:
        assert (await c.get(f"/api/v2/papers/{paper_id}/annotation")).status_code == 404


# --- the cost of a curation save is bounded (review I2) -----------------------------------------


async def test_a_curation_with_too_many_values_is_422(app, async_db_session, ready):
    db = async_db_session
    token, paper_id, _ = ready
    values = {f: [f"v{f}{i}" for i in range(28)] for f in ann.FIELDS}  # 308 in all, 28 per field
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result())
        r = await c.put(f"/api/v2/papers/{paper_id}/annotation/curation", json={"values": values})
    assert r.status_code == 422
    assert "at most 300 values" in r.text


async def test_curation_saves_are_rate_limited_per_owner(
    app, async_db_session, ready, monkeypatch, clear_settings_cache
):
    db = async_db_session
    token, paper_id, bob = ready
    monkeypatch.setenv("MARCUS_RATE_LIMIT_CURATION_PER_MIN", "3")
    clear_settings_cache()
    url = f"/api/v2/papers/{paper_id}/annotation/curation"
    body = {"values": {f: [] for f in ann.FIELDS}}
    async with make_client(app, token) as c:
        await c.post(f"/api/v2/papers/{paper_id}/annotation")
        await run_annotate(db, paper_id, model_result())
        codes = [(await c.put(url, json=body)).status_code for _ in range(2)]
        codes.append((await c.delete(url)).status_code)  # resets count too
        assert codes == [200, 200, 200]
        r = await c.put(url, json=body)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    async with make_client(app, bob) as c:  # another owner: own bucket (and not my paper)
        assert (await c.put(url, json=body)).status_code == 404


def test_locate_reuses_known_positions_and_reads_no_text_when_all_are_known(monkeypatch):
    from marcus.api import annotation as reads

    paper_id = uuid.uuid4()
    storage.paper_dir(paper_id).mkdir(parents=True)
    (storage.paper_dir(paper_id) / "text.json").write_text(json.dumps(TEXT))
    searched = []
    real_find = ann.Locator.find
    monkeypatch.setattr(
        ann.Locator, "find", lambda self, v: searched.append(v) or real_find(self, v)
    )
    values = {f: [] for f in ann.FIELDS} | {"geo_location": ["Oregon", "USA"]}
    known = {"Oregon": [[9, 9, 9]]}
    found = reads.locate(storage.text_path(paper_id), values, known)
    assert searched == ["USA"]  # only the new value is searched
    assert found["geo_location"] == {"Oregon": [[9, 9, 9]], "USA": [[2, 34, 37]]}
    monkeypatch.setattr(reads, "text_blocks", lambda pid: pytest.fail("text read"))
    assert reads.locate(
        storage.text_path(paper_id), {f: [] for f in ann.FIELDS} | {"Kingdom": ["Oregon"]}, known
    )["Kingdom"] == {"Oregon": [[9, 9, 9]]}


async def test_start_is_503_while_no_annotation_worker_is_running(
    app, async_db_session, ready, monkeypatch
):
    from marcus.api.routes import health

    token, paper_id, bob = ready
    monkeypatch.setattr(health, "inspect_live_queues", lambda: {"q.cpu", "q.tools"})
    monkeypatch.setattr(health, "_live_queues", health.LiveQueues())
    async with make_client(app, token) as c:
        own = await c.post(f"/api/v2/papers/{paper_id}/annotation")
        state = await c.get(f"/api/v2/papers/{paper_id}/annotation")
    async with make_client(app, bob) as c:
        theirs = await c.post(f"/api/v2/papers/{paper_id}/annotation")
    assert own.status_code == theirs.status_code == 503
    assert own.json() == theirs.json() == {"detail": "The annotation model is not running"}
    assert state.json()["status"] == "none"
    assert (await paper_row(async_db_session, paper_id)).status == "done"  # not reopened
