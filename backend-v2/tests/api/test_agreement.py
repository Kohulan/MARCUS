"""GET /papers/{id} and its steps with three engines per structure (phase B item 3): the badge
(`agree`), the structure shown (`default_prediction_id`, the export's pick too), background
steps marked and outside the paper's read."""

import json
import uuid

from sqlalchemy import select

from marcus.core.agreement import inchikey_of
from marcus.core.models import BackgroundStep, Curation, Prediction, Step
from tests.api.conftest import (
    finish,
    make_client,
    new_owner,
    ocsr_result,
    seed_paper,
    steps_of,
)


async def _read(db, paper_id, smiles: dict[tuple[int, str], str | None], fail=()):
    """Run the pending OCSR steps: segment n's `engine` reads smiles[(n, engine)] (None: invalid);
    an (n, engine) in `fail` fails; one missing from both stays pending."""

    def run(s):
        for st in steps_of(s, paper_id, status="pending"):
            if st.kind in ("doi", "docling"):
                finish(s, st, {"doi": None} if st.kind == "doi" else {})
        segs = sorted({st.segment_id for st in steps_of(s, paper_id, "ocsr")}, key=str)
        order = {sid: n for n, sid in enumerate(segs)}
        for st in steps_of(s, paper_id, "ocsr", status="pending"):
            key = (order[st.segment_id], st.engine)
            if key in fail:
                st.status, st.attempts = "failed", 2
            elif key in smiles:
                value = smiles[key]
                finish(s, st, ocsr_result(value or "C(", valid=value is not None))
        s.flush()
        return segs

    segs = await db.run_sync(run)
    await db.commit()
    return segs


async def _get(app, token, path):
    async with make_client(app, token) as client:
        r = await client.get(path)
    assert r.status_code == 200
    return r.json()


async def test_badge_waits_for_the_engines_then_says_how_many_agree(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    segs = await _read(db, pid, {(0, "decimer"): "CCO", (1, "decimer"): "CCO"})
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert paper["status"] == "done"  # the paper's engine read everything
    assert {s["agree"] for s in paper["segments"]} == {None}  # the others still read
    await _read(
        db, pid,
        {(0, "molparser"): "OCC", (0, "molscribe"): "C(C)O", (1, "molparser"): "CCN"},
        fail={(1, "molscribe")},
    )  # fmt: skip
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    by_id = {s["id"]: s for s in paper["segments"]}
    first, second = by_id[str(segs[0])], by_id[str(segs[1])]
    assert (first["agree"], first["agree_of"]) == (3, 3)
    assert first["agree_engines"] == ["decimer", "molparser", "molscribe"]
    # MolScribe failed: it read, so this is "Differ" of three, never "2 of 2"
    assert (second["agree"], second["agree_of"], second["agree_engines"]) == (0, 3, [])
    shown = {p["id"]: p["engine"] for p in second["predictions"]}
    assert shown[second["default_prediction_id"]] == "decimer"
    # a failed background engine is no failed structure
    assert paper["failed"] == 0 and paper["to_review"] == 2


async def test_two_agree_against_the_papers_engine(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (0, "molparser"): "CCO", (0, "molscribe"): "OCC",
                          (1, "decimer"): "CCO"})  # fmt: skip
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    seg = next(s for s in paper["segments"] if s["agree"] is not None)
    assert seg["agree"] == 2 and seg["agree_engines"] == ["molparser", "molscribe"]
    shown = next(p for p in seg["predictions"] if p["id"] == seg["default_prediction_id"])
    assert shown["engine"] == "molparser" and shown["smiles"] == "CCO"
    # the export takes the same structure
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{pid}/export", params={"format": "json"})
    exported = {s["segment_id"]: s for s in json.loads(r.content)["segments"]}
    assert exported[seg["id"]]["smiles"] == "CCO"
    assert exported[seg["id"]]["engine"] == "molparser"


async def test_steps_list_background_steps_marked(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    listed = (await _get(app, token, f"/api/v2/papers/{pid}/steps"))["steps"]
    ocsr = [st for st in listed if st["kind"] == "ocsr"]
    assert sorted((st["engine"], st["background"]) for st in ocsr) == [
        ("decimer", False), ("decimer", False),
        ("molparser", True), ("molparser", True), ("molscribe", True), ("molscribe", True),
    ]  # fmt: skip
    background = set(await db.scalars(select(BackgroundStep.step_id)))
    assert {st["id"] for st in ocsr if st["background"]} == {str(b) for b in background}
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    # the counts match the listed steps (a client compares them before refetching)
    assert sum(paper["counts"]["steps_by_status"].values()) == len(listed)
    assert paper["structures_total"] == 2  # background steps are no structures of the read


async def test_a_background_step_asked_for_becomes_the_papers_own(app, async_db_session):
    """Compare (or "Run MolScribe") asks for an engine still waiting in the background: it gets
    that step, promoted to the paper's own (no background row: it counts in the read and is
    sent with the paper's own steps), and the done paper is busy again until it ends."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCO", (1, "decimer"): "CCO"})
    seg = seeded.segment_ids[0]
    async with make_client(app, token) as client:
        r = await client.post(f"/api/v2/segments/{seg}/predictions", json={"engine": "molscribe"})
    assert r.status_code == 202
    step_id = uuid.UUID(r.json()["step_id"])
    step = await db.get(Step, step_id)
    assert step is not None and step.engine == "molscribe" and step.status == "pending"
    rows = await db.scalars(select(BackgroundStep.step_id).where(BackgroundStep.step_id == step_id))
    assert list(rows) == []
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert paper["status"] == "processing"
    listed = (await _get(app, token, f"/api/v2/papers/{pid}/steps"))["steps"]
    assert [st["background"] for st in listed if st["id"] == str(step_id)] == [False]


ETHANOL = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
PROPANOL = "BDERNNFJNOPAEC-UHFFFAOYSA-N"


def _p(engine, key, valid=True, rgroups=()):
    from types import SimpleNamespace

    return SimpleNamespace(id=uuid.uuid4(), engine=engine, inchikey=key, valid=valid,
                           rgroups=list(rgroups), smiles="CCO")  # fmt: skip


def _badge(predictions, ran):
    from marcus.api.read import agreement_out

    out = agreement_out("decimer", predictions, ran)
    return out["agree"], out["agree_of"]


def test_badge_counts_the_engines_that_read():
    """Owner decision 2026-11-22: "3 agree" / "2 agree" / differ of three; "2 of 2 agree" /
    "2 differ" when only two engines read; nothing while one still reads."""
    done3 = {"decimer": False, "molparser": False, "molscribe": False}
    three = [_p("molscribe", ETHANOL), _p("molparser", ETHANOL), _p("decimer", PROPANOL)]
    assert _badge(three, done3) == (2, 3)
    assert _badge(three, {**done3, "molscribe": True}) == (None, None)
    # one engine failed (a step, no prediction): still of three
    assert _badge(three[1:], done3) == (0, 3)
    assert _badge([_p("molparser", ETHANOL), _p("decimer", ETHANOL)], done3) == (2, 3)
    # only two engines ever ran (an older paper, a second engine run in Compare)
    two = {"decimer": False, "molscribe": False}
    assert _badge([_p("molscribe", ETHANOL), _p("decimer", ETHANOL)], two) == (2, 2)
    assert _badge([_p("molscribe", PROPANOL), _p("decimer", ETHANOL)], two) == (0, 2)
    assert _badge([_p("decimer", ETHANOL)], {"decimer": False}) == (None, None)


ETHANOL_D = "LFQSCWFLJHTTHZ-ZZZZZZZZSA-N"  # ethanol's connectivity, other stereo


def test_badge_state_is_stereo_aware():
    """Owner decision 2026-11-26: engines agree on the full InChIKey; the same connectivity with
    other stereo is its own state, "stereo" (the card says "Stereo differs")."""
    from marcus.api.read import agreement_out

    done3 = {"decimer": False, "molparser": False, "molscribe": False}

    def out(*keys):
        ps = [_p(e, k) for e, k in zip(("molscribe", "molparser", "decimer"), keys, strict=False)]
        o = agreement_out("decimer", ps, done3)
        return o["agree_state"], o["agree"], o["agree_engines"]

    assert out(ETHANOL, ETHANOL, ETHANOL) == ("agree3", 3, ["decimer", "molparser", "molscribe"])
    assert out(ETHANOL, ETHANOL, ETHANOL_D) == ("agree2", 2, ["molparser", "molscribe"])
    assert out(ETHANOL, ETHANOL_D, PROPANOL) == ("stereo", 0, [])
    assert out(ETHANOL, PROPANOL) == ("differ", 0, [])
    # no badge: no state
    waiting = agreement_out("decimer", [_p("decimer", ETHANOL)], {**done3, "molscribe": True})
    assert waiting["agree_state"] is None and waiting["agree"] is None
    # stereo differs: the card shows the paper's engine's structure of those that share the
    # connectivity
    ps = [_p("molscribe", ETHANOL), _p("molparser", ETHANOL_D), _p("decimer", PROPANOL)]
    picked = agreement_out("molscribe", ps, done3)["default_prediction_id"]
    assert picked == ps[0].id


def test_no_badge_without_two_inchikeys_or_for_a_scaffold():
    done3 = {"decimer": False, "molparser": False, "molscribe": False}
    # predictions from before 0019 have no InChIKey: they can never agree, so no false "Differ"
    old = [_p("molscribe", None), _p("molparser", ETHANOL), _p("decimer", None)]
    assert _badge(old, done3) == (None, None)
    invalid = [_p("molscribe", None, valid=False), _p("molparser", None), _p("decimer", ETHANOL)]
    assert _badge(invalid, done3) == (None, None)
    scaffold = [
        _p("molscribe", ETHANOL), _p("molparser", ETHANOL), _p("decimer", None, rgroups=["R1"])
    ]  # fmt: skip
    from marcus.api.read import agreement_out

    shown = agreement_out("decimer", scaffold, done3)
    assert shown["agree"] == 2  # the majority is a plain structure, shown
    scaffold_shown = [_p("decimer", ETHANOL, rgroups=["R1"]), _p("molparser", PROPANOL)]
    assert _badge(scaffold_shown, done3) == (None, None)


async def test_an_engine_whose_step_never_ran_does_not_count(app, async_db_session):
    """A background step cancelled before it ran (expired: no worker) is no engine that read."""
    from sqlalchemy import update

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(n, e): "CCO" for n in (0, 1) for e in ("decimer", "molparser")})
    await db.execute(
        update(Step)
        .where(Step.paper_id == pid, Step.engine == "molscribe")
        .values(status="cancelled")
    )
    await db.commit()
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert {(s["agree"], s["agree_of"]) for s in paper["segments"]} == {(2, 2)}


async def _decide(app, token, seg, status):
    body = {"status": status, "smiles": None, "molfile": None, "note": None}
    async with make_client(app, token) as client:
        r = await client.put(f"/api/v2/segments/{seg}/curation?decision=true", json=body)
    assert r.status_code == 200, r.text


async def test_a_decision_freezes_the_structure_it_was_made_on(app, async_db_session):
    """Review finding: accepted while only DECIMER had read (CCN); the other two engines then
    agree on CCO. The card, its depiction pick and its export keep CCN; back to unchecked, the
    majority shows; a new accept keeps that one."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (1, "decimer"): "CCN"})
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    seg = paper["segments"][0]
    own = seg["default_prediction_id"]
    await _decide(app, token, seg["id"], "accepted")
    await _read(db, pid, {(n, e): "CCO" for n in (0, 1) for e in ("molparser", "molscribe")})

    def shown(paper, sid):
        s = next(x for x in paper["segments"] if x["id"] == sid)
        return next(p for p in s["predictions"] if p["id"] == s["default_prediction_id"])

    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert shown(paper, seg["id"])["id"] == own and shown(paper, seg["id"])["smiles"] == "CCN"
    other = next(x for x in paper["segments"] if x["id"] != seg["id"])
    assert shown(paper, other["id"])["smiles"] == "CCO"  # undecided: the majority
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{pid}/export", params={"format": "json"})
    exported = {s["segment_id"]: s["smiles"] for s in json.loads(r.content)["segments"]}
    assert exported[seg["id"]] == "CCN"

    await _decide(app, token, seg["id"], "unchecked")
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert shown(paper, seg["id"])["smiles"] == "CCO"
    await _decide(app, token, seg["id"], "rejected")
    row = await db.get(Curation, uuid.UUID(seg["id"]))
    await db.refresh(row)
    assert row.shown_prediction_id == uuid.UUID(shown(paper, seg["id"])["id"])


async def test_bulk_and_group_decisions_freeze_each_structure(app, async_db_session):
    """A bulk accept freezes each card's own shown prediction; a repeat that inherits a main
    card's decision freezes its own."""
    from marcus.core.models import Paper, Prediction, Segment

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (1, "decimer"): "CCO"})

    def add_repeat(s):
        s.get(Paper, pid).pages = 2
        seg = Segment(id=uuid.uuid4(), paper_id=pid, page=1, idx=0, bbox=[0, 0, 10, 10],
                      image_sha256="7" * 64)  # fmt: skip
        s.add(seg)
        s.flush()
        s.add(Curation(segment_id=seg.id, status="unchecked"))
        s.add(Prediction(segment_id=seg.id, engine="decimer", engine_version="t", smiles="OCC",
                         valid=True, ms=1, rgroups=[], inchikey=ETHANOL))  # fmt: skip
        return seg.id

    repeat = await db.run_sync(add_repeat)
    await db.commit()
    async with make_client(app, token) as client:
        assert (await client.put(f"/api/v2/papers/{pid}/main-figure", json={"page": 0})).is_success
        items = [{"segment_id": str(s), "status": "accepted"} for s in seeded.segment_ids]
        r = await client.put(f"/api/v2/papers/{pid}/curation", json={"items": items})
    assert r.status_code == 200, r.text
    rows = {
        c.segment_id: c
        for c in (await db.scalars(select(Curation).execution_options(populate_existing=True)))
    }
    preds = {
        p.id: p for p in await db.scalars(select(Prediction).where(Prediction.segment_id.in_(rows)))
    }
    for sid in [*seeded.segment_ids, repeat]:
        assert rows[sid].status == "accepted"
        frozen = preds[rows[sid].shown_prediction_id]
        assert frozen.segment_id == sid  # its own structure
    assert preds[rows[repeat].shown_prediction_id].smiles == "OCC"


async def _put(app, token, seg, status, shown=None):
    body = {"status": status, "smiles": None, "molfile": None, "note": None}
    query = "?decision=true" + (f"&shown_prediction_id={shown}" if shown else "")
    async with make_client(app, token) as client:
        return await client.put(f"/api/v2/segments/{seg}/curation{query}", json=body)


async def _frozen(db, seg):
    row = (
        await db.execute(
            select(Curation)
            .where(Curation.segment_id == seg)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return row.shown_prediction_id


async def test_a_decision_freezes_the_prediction_the_card_showed(app, async_db_session):
    """The race: the card showed DECIMER's CCN (A); MolParser and MolScribe land CCO (B) before
    the click reaches the server, so the server's own pick would be B. The browser names A:
    A is frozen."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (1, "decimer"): "CCN"})
    paper = await _get(app, token, f"/api/v2/papers/{pid}")  # what the client read
    seg = paper["segments"][0]
    seen = seg["default_prediction_id"]
    await _read(db, pid, {(n, e): "CCO" for n in (0, 1) for e in ("molparser", "molscribe")})
    r = await _put(app, token, seg["id"], "accepted", seen)
    assert r.status_code == 200, r.text
    assert await _frozen(db, uuid.UUID(seg["id"])) == uuid.UUID(seen)
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    assert (
        next(s for s in paper["segments"] if s["id"] == seg["id"])["default_prediction_id"] == seen
    )
    # without it (an older client), the server's pick when the decision lands: the majority
    other = next(s for s in paper["segments"] if s["id"] != seg["id"])
    assert (await _put(app, token, other["id"], "accepted")).status_code == 200
    frozen = await db.get(Prediction, await _frozen(db, uuid.UUID(other["id"])))
    assert frozen.smiles == "CCO"


async def test_the_shown_prediction_must_be_the_segments_own(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    paper = await _get(app, token, f"/api/v2/papers/{seeded.paper_id}")
    first, second = paper["segments"]
    foreign = second["predictions"][0]["id"]
    r = await _put(app, token, first["id"], "accepted", foreign)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["query", "shown_prediction_id"]
    assert (await _put(app, token, first["id"], "accepted", str(uuid.uuid4()))).status_code == 422
    assert await _frozen(db, uuid.UUID(first["id"])) is None  # nothing saved
    items = [{"segment_id": first["id"], "status": "accepted", "shown_prediction_id": foreign}]
    async with make_client(app, token) as client:
        bad = await client.put(f"/api/v2/papers/{seeded.paper_id}/curation", json={"items": items})
        items[0]["shown_prediction_id"] = first["predictions"][-1]["id"]
        good = await client.put(f"/api/v2/papers/{seeded.paper_id}/curation", json={"items": items})
    assert bad.status_code == 422 and good.status_code == 200
    assert await _frozen(db, uuid.UUID(first["id"])) == uuid.UUID(first["predictions"][-1]["id"])


async def test_a_structure_edit_drops_the_frozen_prediction(app, async_db_session):
    """Review finding: an edit with a structure of its own, even one that keeps the status (no
    decision), clears the frozen prediction; clearing the structure later shows the default
    pick, not the old frozen one."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (1, "decimer"): "CCN"})
    seg = seeded.segment_ids[0]
    assert (await _put(app, token, seg, "accepted")).status_code == 200
    assert await _frozen(db, seg) is not None
    edit = {"status": "accepted", "smiles": "CCCl", "molfile": None, "note": None}
    async with make_client(app, token) as client:
        assert (await client.put(f"/api/v2/segments/{seg}/curation", json=edit)).is_success
    assert await _frozen(db, seg) is None
    await _read(db, pid, {(n, e): "CCO" for n in (0, 1) for e in ("molparser", "molscribe")})
    back = {**edit, "smiles": None}
    async with make_client(app, token) as client:
        assert (await client.put(f"/api/v2/segments/{seg}/curation", json=back)).is_success
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    s0 = next(s for s in paper["segments"] if s["id"] == str(seg))
    shown = next(p for p in s0["predictions"] if p["id"] == s0["default_prediction_id"])
    assert shown["smiles"] == "CCO"  # the majority now, not the old CCN


async def test_a_stale_inherited_decision_drops_its_frozen_structure(app, async_db_session):
    """Review finding: a repeat inherits the main card's accept and freezes its own OCC; later
    MolParser and MolScribe agree on CCN for it, and the main figure is unmarked, so the
    inherited status no longer holds ("to review"). Its card, export and links take the
    default pick (CCN), not the frozen OCC; a decision on the card itself freezes what it
    shows."""
    from marcus.core.models import Paper, Segment

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await _read(db, pid, {(0, "decimer"): "CCN", (1, "decimer"): "CCO"})

    def add_repeat(s):
        s.get(Paper, pid).pages = 2
        seg = Segment(id=uuid.uuid4(), paper_id=pid, page=1, idx=0, bbox=[0, 0, 10, 10],
                      image_sha256="7" * 64)  # fmt: skip
        s.add(seg)
        s.flush()
        s.add(Curation(segment_id=seg.id, status="unchecked"))
        s.add(Prediction(segment_id=seg.id, engine="decimer", engine_version="t", smiles="OCC",
                         valid=True, ms=1, rgroups=[], inchikey=ETHANOL))  # fmt: skip
        return seg.id

    repeat = await db.run_sync(add_repeat)
    await db.commit()
    async with make_client(app, token) as client:
        assert (await client.put(f"/api/v2/papers/{pid}/main-figure", json={"page": 0})).is_success
    # the main-figure structure the repeat links to: the one read as CCO (same InChIKey)
    main = await db.scalar(
        select(Prediction.segment_id).where(
            Prediction.segment_id.in_(seeded.segment_ids), Prediction.smiles == "CCO"
        )
    )
    assert (await _put(app, token, main, "accepted")).status_code == 200
    occ = await _frozen(db, repeat)
    assert (await db.get(Prediction, occ)).smiles == "OCC"

    def later(s):
        for engine in ("molparser", "molscribe"):
            s.add(Prediction(segment_id=repeat, engine=engine, engine_version="t",
                             smiles="CCN", valid=True, ms=1, rgroups=[],
                             inchikey=inchikey_of("CCN", True)))  # fmt: skip

    await db.run_sync(later)
    await db.commit()
    async with make_client(app, token) as client:
        assert (
            await client.put(f"/api/v2/papers/{pid}/main-figure", json={"page": None})
        ).is_success
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    card = next(s for s in paper["segments"] if s["id"] == str(repeat))
    assert card["curation"]["status"] == "unchecked"  # stale
    shown = next(p for p in card["predictions"] if p["id"] == card["default_prediction_id"])
    assert shown["smiles"] == "CCN"
    async with make_client(app, token) as client:
        r = await client.get(f"/api/v2/papers/{pid}/export", params={"format": "json"})
    exported = {s["segment_id"]: s["smiles"] for s in json.loads(r.content)["segments"]}
    assert exported[str(repeat)] == "CCN"
    assert (await _put(app, token, repeat, "accepted", shown["id"])).status_code == 200
    assert await _frozen(db, repeat) == uuid.UUID(shown["id"])


async def test_an_old_paper_keeps_its_molnextr_badge(app, async_db_session):
    """A paper read before MolParser replaced MolNexTR (2026-11-25): its MolNexTR steps and
    predictions count in MolParser's slot, so the badge stays "3 agree" of three. A MolParser
    read asked for later (Compare) takes the slot: still three engines, never four."""
    from sqlalchemy import update

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    pid = seeded.paper_id
    await db.execute(
        update(Step)
        .where(Step.paper_id == pid, Step.engine == "molparser")
        .values(engine="molnextr", queue="q.molnextr")
    )
    await db.commit()
    segs = await _read(
        db, pid,
        {(n, e): "CCO" for n in (0, 1) for e in ("decimer", "molnextr", "molscribe")},
    )  # fmt: skip
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    first = {s["id"]: s for s in paper["segments"]}[str(segs[0])]
    assert (first["agree"], first["agree_of"]) == (3, 3)
    assert first["agree_engines"] == ["decimer", "molnextr", "molscribe"]

    async with make_client(app, token) as client:
        r = await client.post(
            f"/api/v2/segments/{segs[0]}/predictions", json={"engine": "molparser"}
        )
    assert r.status_code == 202
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    first = {s["id"]: s for s in paper["segments"]}[str(segs[0])]
    assert first["agree"] is None  # MolParser's slot is reading again: the badge waits
    await _read(db, pid, {(0, "molparser"): "CCN"})
    paper = await _get(app, token, f"/api/v2/papers/{pid}")
    first = {s["id"]: s for s in paper["segments"]}[str(segs[0])]
    assert (first["agree"], first["agree_of"]) == (2, 3)
    assert first["agree_engines"] == ["decimer", "molscribe"]
