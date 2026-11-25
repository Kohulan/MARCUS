import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from rdkit import Chem

from marcus.api import export
from marcus.core.enums import Engine
from marcus.core.models import Prediction
from tests.api.conftest import make_client, new_owner, seed_paper

HEADER = [
    "segment_id", "page", "idx", "smiles", "status", "engine", "note", "edited", "source",
    "organism", "organism_part", "geo_location", "kingdom", "rgroups",
]  # fmt: skip


async def _curate(app, token, seg, body):
    async with make_client(app, token) as c:
        return await c.put(f"/api/v2/segments/{seg}/curation", json=body)


# --- export -------------------------------------------------------------------------------


async def _export(app, token, paper_id, fmt, status=None):
    params = {"format": fmt} | ({"status": status} if status else {})
    async with make_client(app, token) as c:
        return await c.get(f"/api/v2/papers/{paper_id}/export", params=params)


async def test_export_sdf_uses_curated_smiles(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)  # both segments predicted "CCO"
    s0, s1 = seeded.segment_ids
    assert (await _curate(app, token, s0, {"status": "accepted", "smiles": "c1ccccc1"})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("chemical/x-mdl-sdfile")
    assert r.headers["content-disposition"] == (
        f'attachment; filename="marcus-{seeded.paper_id}.sdf"'
    )
    mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))
    assert len(mols) == 2 and all(m is not None for m in mols)
    by_seg = {m.GetProp("segment_id"): m for m in mols}
    assert Chem.MolToSmiles(by_seg[str(s0)]) == "c1ccccc1"
    assert Chem.MolToSmiles(by_seg[str(s1)]) == "CCO"
    assert by_seg[str(s0)].GetProp("page") == "0" and by_seg[str(s1)].GetProp("idx") == "1"
    assert by_seg[str(s0)].GetNumConformers() == 1  # 2D coordinates were computed


async def test_export_prefers_paper_engine_and_accepted_filter_skips_rejected(
    app, async_db_session
):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    s0, s1 = seeded.segment_ids
    later = datetime.now(UTC) + timedelta(seconds=10)

    def add(s):
        # newer predictions: another engine (valid) and the paper's engine (invalid)
        s.add(
            Prediction(
                segment_id=s0,
                engine="molparser",
                engine_version="m",
                smiles="CCN",
                valid=True,
                ms=1,
                created_at=later,
            )
        )
        s.add(
            Prediction(
                segment_id=s0,
                engine="decimer",
                engine_version="d",
                smiles="C(",
                valid=False,
                ms=1,
                created_at=later,
            )
        )

    await db.run_sync(add)
    await db.commit()
    assert (await _curate(app, token, s0, {"status": "accepted"})).is_success
    assert (await _curate(app, token, s1, {"status": "rejected", "smiles": "CC"})).is_success

    r = await _export(app, token, seeded.paper_id, "json", "accepted")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        f'attachment; filename="marcus-{seeded.paper_id}.json"'
    )
    body = json.loads(r.content)
    assert body["paper"]["id"] == str(seeded.paper_id)
    assert body["paper"]["display_name"] == "paper.pdf"
    assert [(s["segment_id"], s["smiles"], s["source"]) for s in body["segments"]] == [
        (str(s0), "CCO", "predicted"),
    ]

    r = await _export(app, token, seeded.paper_id, "csv", "accepted")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows == [
        HEADER,
        [str(s0), "0", "0", "CCO", "accepted", "decimer", "", "false", "predicted",
         "", "", "", "", ""],
    ]  # fmt: skip


async def test_export_falls_back_to_any_engine_and_uses_curated_molfile(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, engine=Engine.MOLPARSER, ocsr=False)
    s0, s1 = seeded.segment_ids

    def add(s):
        s.add(
            Prediction(
                segment_id=s0, engine="decimer", engine_version="d", smiles="CCCl", valid=True, ms=1
            )
        )

    await db.run_sync(add)
    await db.commit()
    molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("CN"))
    assert (await _curate(app, token, s1, {"status": "accepted", "molfile": molfile})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    mols = {m.GetProp("segment_id"): m for m in Chem.ForwardSDMolSupplier(io.BytesIO(r.content))}
    assert Chem.MolToSmiles(mols[str(s0)]) == "CCCl"
    assert Chem.MolToSmiles(mols[str(s1)]) == "CN"
    r = await _export(app, token, seeded.paper_id, "csv")
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    assert [(row[0], row[8]) for row in rows] == [(str(s0), "predicted"), (str(s1), "curated")]


async def test_export_leaves_out_segments_without_a_valid_structure(app, async_db_session):
    """s0 has no predictions at all; s1 has only invalid ones: neither is exported."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    s0, s1 = seeded.segment_ids

    def add(s):
        for engine in ("decimer", "molparser"):
            s.add(Prediction(segment_id=s1, engine=engine, engine_version="v", smiles="C(",
                             valid=False, ms=1))  # fmt: skip

    await db.run_sync(add)
    await db.commit()
    r = await _export(app, token, seeded.paper_id, "json")
    assert r.status_code == 200 and json.loads(r.content)["segments"] == []
    r = await _export(app, token, seeded.paper_id, "csv")
    assert list(csv.reader(io.StringIO(r.text))) == [HEADER]
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    assert r.status_code == 200
    assert list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content))) == []
    for seg in (s0, s1):
        assert str(seg) not in r.text


def test_csv_cells_escape_formulas():
    seg = uuid.uuid4()
    risky = ["=HYPERLINK(1)", "+1", "-1", "@SUM(A1)", "\tC", "\rC", "CCO"]
    chosen = [export.Chosen(seg, 0, i, s, None, "predicted") for i, s in enumerate(risky)]
    rows = list(csv.reader(io.StringIO(export.to_csv(chosen).decode())))[1:]
    assert [r[3] for r in rows] == [
        "'=HYPERLINK(1)", "'+1", "'-1", "'@SUM(A1)", "'\tC", "'\rC", "CCO",
    ]  # fmt: skip


async def test_export_csv_escapes_predicted_formula(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, ocsr=False)
    s0 = seeded.segment_ids[0]

    def add(s):
        s.add(
            Prediction(segment_id=s0, engine="decimer", engine_version="d",
                       smiles="=cmd|' /C calc'!A0", valid=True, ms=1)
        )  # fmt: skip

    await db.run_sync(add)
    await db.commit()
    r = await _export(app, token, seeded.paper_id, "csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[1][3] == "'=cmd|' /C calc'!A0"


async def test_export_bad_format_is_422(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    assert (await _export(app, token, seeded.paper_id, "../../etc/passwd")).status_code == 422


# --- curation in the export -----------------------------------------------------------------


async def _three(app, db):
    """s0 accepted (own SMILES + note), s1 rejected (predicted CCO), nothing else: also a
    third segment is not seeded, so unchecked is s1 reset via `unchecked` where needed."""
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    return token, seeded, *seeded.segment_ids


async def test_csv_header_exact(app, async_db_session):
    token, seeded, *_ = await _three(app, async_db_session)
    r = await _export(app, token, seeded.paper_id, "csv")
    assert r.text.split("\n")[0] == ",".join(HEADER)


async def test_sdf_default_only_accepted(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    assert (await _curate(app, token, s0, {"status": "accepted"})).is_success
    assert (await _curate(app, token, s1, {"status": "rejected"})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf")
    mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))
    assert [m.GetProp("segment_id") for m in mols] == [str(s0)]
    assert mols[0].GetProp("MARCUS_STATUS") == "accepted"
    assert mols[0].GetProp("MARCUS_ENGINE") == "decimer"
    assert mols[0].GetProp("MARCUS_EDITED") == "false"
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    assert len(list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))) == 2


async def test_json_default_all_includes_rejected(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    assert (await _curate(app, token, s1, {"status": "rejected", "note": "bad"})).is_success
    r = await _export(app, token, seeded.paper_id, "json")
    segs = json.loads(r.content)["segments"]
    assert [(x["segment_id"], x["status"]) for x in segs] == [
        (str(s0), "unchecked"),
        (str(s1), "rejected"),
    ]
    assert segs[1]["note"] == "bad" and segs[1]["engine"] == "decimer"
    assert set(segs[0]) >= {"status", "engine", "note", "edited"}


async def test_status_accepted_filter_json(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    assert (await _curate(app, token, s0, {"status": "accepted"})).is_success
    r = await _export(app, token, seeded.paper_id, "json", "accepted")
    assert [x["segment_id"] for x in json.loads(r.content)["segments"]] == [str(s0)]


async def test_status_value_is_unchecked_not_to_review(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    assert (await _curate(app, token, s1, {"status": "unchecked"})).is_success
    r = await _export(app, token, seeded.paper_id, "csv")
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    assert [row[4] for row in rows] == ["unchecked", "unchecked"]  # missing and explicit
    assert "to_review" not in r.text and "to review" not in r.text.lower()


async def test_note_formula_guarded_in_csv(app, async_db_session):
    token, seeded, s0, _ = await _three(app, async_db_session)
    note = '=HYPERLINK("http://x","y")'
    assert (await _curate(app, token, s0, {"status": "accepted", "note": note})).is_success
    r = await _export(app, token, seeded.paper_id, "csv")
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    assert rows[0][6] == "'" + note


async def test_sdf_note_newlines_folded(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    note = "a\n\n$$$$\nb"
    assert (await _curate(app, token, s0, {"status": "accepted", "note": note})).is_success
    assert (await _curate(app, token, s1, {"status": "accepted", "note": "x\r\ny\rz"})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf")
    assert r.text.count("$$$$") == 3  # two record ends + the folded one inside the note
    mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))
    assert len(mols) == 2 and all(m is not None for m in mols)
    props = {m.GetProp("segment_id"): m.GetProp("MARCUS_NOTE") for m in mols}
    assert props[str(s0)] == "a  $$$$ b"
    assert props[str(s1)] == "x y z"
    # a note that is only $$$$ must not end the record either
    assert (await _curate(app, token, s0, {"status": "accepted", "note": "$$$$"})).is_success
    r = await _export(app, token, seeded.paper_id, "sdf")
    assert len(list(Chem.ForwardSDMolSupplier(io.BytesIO(r.content)))) == 2


async def test_edited_flag(app, async_db_session):
    token, seeded, s0, s1 = await _three(app, async_db_session)
    assert (await _curate(app, token, s0, {"status": "accepted", "smiles": "CN"})).is_success
    assert (await _curate(app, token, s1, {"status": "accepted", "note": "ok"})).is_success
    r = await _export(app, token, seeded.paper_id, "json")
    segs = {x["segment_id"]: x for x in json.loads(r.content)["segments"]}
    assert segs[str(s0)]["edited"] is True and segs[str(s0)]["engine"] is None
    assert segs[str(s0)]["source"] == "curated"
    assert segs[str(s1)]["edited"] is False and segs[str(s1)]["engine"] == "decimer"
    r = await _export(app, token, seeded.paper_id, "sdf")
    mols = {m.GetProp("segment_id"): m for m in Chem.ForwardSDMolSupplier(io.BytesIO(r.content))}
    assert mols[str(s0)].GetProp("MARCUS_EDITED") == "true"
    assert not mols[str(s0)].HasProp("MARCUS_ENGINE")


# --- the paper's annotation in every format ------------------------------------------------------


async def _annotated(db, curated: bool):
    from marcus.core import annotation as ann
    from marcus.core.models import Annotation

    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    output = {f: [] for f in ann.FIELDS}
    output |= {"organism_or_species": ["Taxus brevifolia", "T. baccata"],
               "organism_part": ["bark"], "Kingdom": ["Plant"], "trivial_name": ["taxol"]}  # fmt: skip
    row = Annotation(
        paper_id=seeded.paper_id,
        model="qwen3.5-9b-marcus-v1",
        model_version="Q8_0 llama.cpp b12554",
        output=output,
        positions={f: {v: [] for v in output[f]} for f in ann.FIELDS},
    )
    if curated:
        row.curated = output | {"geo_location": ["=Oregon"], "organism_part": []}
        row.curated_positions = {f: {v: [] for v in row.curated[f]} for f in ann.FIELDS}
        row.curated_at = datetime.now(UTC)
    db.add(row)
    await db.commit()
    return token, seeded


async def test_json_export_has_the_paper_level_annotation(app, async_db_session):
    token, seeded = await _annotated(async_db_session, curated=True)
    doc = (await _export(app, token, seeded.paper_id, "json")).json()
    a = doc["annotation"]
    assert a["source"] == "curated" and a["model"] == "qwen3.5-9b-marcus-v1"
    assert a["values"]["geo_location"] == ["=Oregon"] and a["values"]["organism_part"] == []
    assert a["model_values"]["organism_part"] == ["bark"]
    assert a["values"]["trivial_name"] == ["taxol"] and a["curated_at"]
    assert list(a["values"]) == list(a["model_values"])  # all 11 fields, in order


async def test_json_export_without_annotation_has_null(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    assert (await _export(app, token, seeded.paper_id, "json")).json()["annotation"] is None


async def test_csv_export_has_the_source_columns_guarded(app, async_db_session):
    token, seeded = await _annotated(async_db_session, curated=True)
    rows = list(csv.reader(io.StringIO((await _export(app, token, seeded.paper_id, "csv")).text)))
    assert rows[0] == HEADER and len(rows) == 3
    for row in rows[1:]:
        assert row[9:13] == ["Taxus brevifolia; T. baccata", "", "'=Oregon", "Plant"]


async def test_csv_export_without_annotation_has_empty_source_columns(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    rows = list(csv.reader(io.StringIO((await _export(app, token, seeded.paper_id, "csv")).text)))
    assert all(row[9:13] == ["", "", "", ""] for row in rows[1:])


async def test_sdf_export_has_the_source_properties(app, async_db_session):
    token, seeded = await _annotated(async_db_session, curated=False)
    for seg in seeded.segment_ids:
        await _curate(app, token, seg, {"status": "accepted"})
    r = await _export(app, token, seeded.paper_id, "sdf")
    supplier = Chem.SDMolSupplier()
    supplier.SetData(r.text)
    mols = [m for m in supplier if m is not None]
    assert len(mols) == 2
    for mol in mols:
        assert mol.GetProp("MARCUS_ORGANISM") == "Taxus brevifolia; T. baccata"
        assert mol.GetProp("MARCUS_ORGANISM_PART") == "bark"
        assert mol.GetProp("MARCUS_KINGDOM") == "Plant"
        assert not mol.HasProp("MARCUS_GEO_LOCATION")  # empty: left out


async def test_scaffold_is_exported_flagged_not_as_a_finished_compound(app, async_db_session):
    """A structure with R-group placeholders is kept (the curator accepted it) and every format
    names its labels; a plain structure has none. A row stored without labels (NULL) is
    labelled at export time."""
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, others=False)  # its engine only: no majority
    s0, s1 = seeded.segment_ids
    later = datetime.now(UTC) + timedelta(seconds=10)

    def add(s):
        s.add(
            Prediction(
                segment_id=s0, engine="decimer", engine_version="d", smiles="[1*]c1ccc(*)cc1",
                valid=True, ms=1, created_at=later,  # rgroups NULL: computed by the export
            )
        )  # fmt: skip

    await db.run_sync(add)
    await db.commit()
    body = json.loads((await _export(app, token, seeded.paper_id, "json")).content)
    flags = {s["segment_id"]: s["rgroups"] for s in body["segments"]}
    assert flags == {str(s0): ["R1", "*"], str(s1): []}

    rows = list(csv.reader(io.StringIO((await _export(app, token, seeded.paper_id, "csv")).text)))
    assert rows[0][-1] == "rgroups"
    assert {r[0]: r[-1] for r in rows[1:]} == {str(s0): "R1; *", str(s1): ""}

    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    by_seg = {m.GetProp("segment_id"): m for m in Chem.ForwardSDMolSupplier(io.BytesIO(r.content))}
    assert by_seg[str(s0)].GetProp("MARCUS_RGROUPS") == "R1; *"
    assert not by_seg[str(s1)].HasProp("MARCUS_RGROUPS")


async def test_curated_scaffold_labels_come_from_the_curation(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice)
    s0, _ = seeded.segment_ids
    r = await _curate(app, token, s0, {"status": "accepted", "smiles": "[2*]CCO"})
    assert r.status_code == 200
    body = json.loads((await _export(app, token, seeded.paper_id, "json", "accepted")).content)
    assert [(s["source"], s["rgroups"]) for s in body["segments"]] == [("curated", ["R2"])]


async def test_exports_name_the_labels_the_page_text_names(app, async_db_session):
    """JSON, CSV and SDF carry the labels shown (owner decision 2026-11-22): DECIMER's extra Z
    is left out where the page's text names R1 and R2."""
    from sqlalchemy import update

    from marcus.core.models import Paper

    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, others=False)  # its engine only: no majority
    s0, _ = seeded.segment_ids
    later = datetime.now(UTC) + timedelta(seconds=10)

    def add(s):
        s.add(
            Prediction(
                segment_id=s0, engine="decimer", engine_version="d",
                smiles="[1*]c1ccc(*)cc1[2*]", valid=True, ms=1, created_at=later,
                rgroups=["R1", "R2", "Z"],  # as stored for DECIMER's [R1], [R2], [Z]
            )
        )  # fmt: skip

    await db.run_sync(add)
    await db.execute(update(Paper).where(Paper.id == seeded.paper_id)
                     .values(rgroup_text_labels={"0": ["R1", "R2"]}))  # fmt: skip
    await db.commit()
    body = json.loads((await _export(app, token, seeded.paper_id, "json")).content)
    assert {s["segment_id"]: s["rgroups"] for s in body["segments"]}[str(s0)] == ["R1", "R2"]
    rows = list(csv.reader(io.StringIO((await _export(app, token, seeded.paper_id, "csv")).text)))
    assert {r[0]: r[-1] for r in rows[1:]}[str(s0)] == "R1; R2"
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    by_seg = {m.GetProp("segment_id"): m for m in Chem.ForwardSDMolSupplier(io.BytesIO(r.content))}
    assert by_seg[str(s0)].GetProp("MARCUS_RGROUPS") == "R1; R2"


def test_a_prediction_without_labels_exports_no_rgroup_rows():
    """Review finding 5: rows read while a prediction had labels (before 0014 left MolScribe's
    OMe out, say) do not go with it once it has none, as for a curated structure."""
    from types import SimpleNamespace

    seg = SimpleNamespace(id=uuid.uuid4(), page=0, idx=0)
    paper = SimpleNamespace(engine="molscribe", rgroup_text_labels=None)
    pred = SimpleNamespace(id=uuid.uuid4(), engine="molscribe", valid=True, smiles="COc1ccccc1",
                           molfile=None, rgroups=[], inchikey=None)  # fmt: skip
    rows = {pred.id: {"labels": ["OMe"], "rows": []}}
    (chosen,) = export.choose(paper, [seg], {}, {seg.id: [pred]}, rgroup_rows=rows)
    assert chosen.rgroups == () and chosen.rgroup_rows is None
    pred.rgroups = ["R1"]
    (chosen,) = export.choose(paper, [seg], {}, {seg.id: [pred]}, rgroup_rows=rows)
    assert chosen.rgroup_rows == rows[pred.id]


# --- chiral flag (absolute stereo, as the SMILES) -------------------------------------------


def _sdf_flags(content: bytes) -> list[str]:
    records = [r for r in content.decode().split("$$$$") if "V2000" in r]
    return [next(ln for ln in r.splitlines() if "V2000" in ln)[12:15] for r in records]


def test_sdf_from_a_stereo_smiles_has_chiral_flag_1():
    seg = uuid.uuid4()
    chosen = [
        export.Chosen(seg, 0, 0, "C[C@H](N)C(=O)O", None, "predicted"),
        export.Chosen(seg, 0, 1, "CC(N)C(=O)O", None, "predicted"),
    ]
    assert _sdf_flags(export.to_sdf(chosen)) == ["  1", "  0"]


async def test_export_gives_an_engine_molfile_chiral_flag_1(app, async_db_session):
    db = async_db_session
    alice, token = await new_owner(db)
    seeded = await seed_paper(db, alice, engine=Engine.MOLPARSER, ocsr=False)
    s0 = seeded.segment_ids[0]
    molfile = Chem.MolToMolBlock(Chem.MolFromSmiles("C[C@H](N)C(=O)O"))  # RDKit: flag 0

    def add(s):
        s.add(
            Prediction(
                segment_id=s0,
                engine="molparser",
                engine_version="m",
                smiles="C[C@H](N)C(=O)O",
                molfile=molfile,
                valid=True,
                ms=1,
            )
        )

    await db.run_sync(add)
    await db.commit()
    doc = (await _export(app, token, seeded.paper_id, "json", "all")).json()
    out = next(s["molfile"] for s in doc["segments"] if s["segment_id"] == str(s0))
    assert out.splitlines()[3][12:15] == "  1"
    r = await _export(app, token, seeded.paper_id, "sdf", "all")
    assert _sdf_flags(r.content) == ["  1"]
