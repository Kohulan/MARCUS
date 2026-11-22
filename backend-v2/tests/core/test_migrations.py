from sqlalchemy import inspect

from alembic import command
from tests.conftest import _assert_test_database, alembic_config

EXPECTED = {
    "owners", "papers", "steps", "segments", "predictions", "curation",
    "image_jobs", "seg_cache", "ocsr_cache", "annotations", "rgroup_extractions", "main_figures",
    "inherited_statuses", "drawing_flags",
}  # fmt: skip

# 0002: column + index
INDEXES_0002 = {("segments", "ix_segments_image_sha256")}
# 0003: purge and foreign-key indexes, (table, name) -> columns
INDEXES_0003 = {
    ("steps", "ix_steps_segment_id"): ["segment_id"],
    ("steps", "ix_steps_image_job_id"): ["image_job_id"],
    ("predictions", "ix_predictions_segment_id"): ["segment_id"],
    ("predictions", "ix_predictions_image_job_id"): ["image_job_id"],
    ("image_jobs", "ix_image_jobs_owner_id"): ["owner_id"],
    ("papers", "ix_papers_expires_at"): ["expires_at"],
    ("image_jobs", "ix_image_jobs_expires_at"): ["expires_at"],
    ("owners", "ix_owners_created_ip_created_at"): ["created_ip", "created_at"],
    ("steps", "ix_steps_queue_finished_at"): ["queue", "finished_at"],
    ("seg_cache", "ix_seg_cache_created_at"): ["created_at"],
    ("ocsr_cache", "ix_ocsr_cache_created_at"): ["created_at"],
}


def _indexes(engine) -> dict[tuple[str, str], list[str]]:
    insp = inspect(engine)
    return {
        (table, ix["name"]): ix["column_names"]
        for table in insp.get_table_names()
        for ix in insp.get_indexes(table)
    }


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_upgrade_then_downgrade_clean(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert EXPECTED <= set(inspect(engine).get_table_names())
        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        command.upgrade(cfg, "head")


def test_0002_and_0003_objects_up_and_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        indexes = _indexes(engine)
        assert "model_version" in _columns(engine, "steps")
        assert INDEXES_0002 <= set(indexes)
        for key, columns in INDEXES_0003.items():
            assert indexes.get(key) == columns, key

        command.downgrade(cfg, "0002")
        indexes = _indexes(engine)
        assert not set(INDEXES_0003) & set(indexes)
        assert INDEXES_0002 <= set(indexes)
        assert "model_version" in _columns(engine, "steps")

        command.downgrade(cfg, "0001")
        assert not INDEXES_0002 & set(_indexes(engine))
        assert "model_version" not in _columns(engine, "steps")
    finally:
        command.upgrade(cfg, "head")


def test_models_declare_the_0003_indexes():
    """The ORM metadata matches the migrations (the model is what readers look at)."""
    from marcus.core.db import Base

    declared = {
        (table.name, ix.name): [c.name for c in ix.columns]
        for table in Base.metadata.sorted_tables
        for ix in table.indexes
    }
    for key, columns in INDEXES_0003.items():
        assert declared.get(key) == columns, key


def test_0004_adds_predictions_cached(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert "cached" in _columns(engine, "predictions")
        command.downgrade(cfg, "0003")
        assert "cached" not in _columns(engine, "predictions")
    finally:
        command.upgrade(cfg, "head")


def test_migration_0005_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert "title" in _columns(engine, "papers")
        command.downgrade(cfg, "0004")
        assert "title" not in _columns(engine, "papers")
    finally:
        command.upgrade(cfg, "head")


def test_migration_0006_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in inspect(engine).get_columns("papers")}
        assert cols["first_author"]["nullable"] and cols["year"]["nullable"]
        command.downgrade(cfg, "0005")
        cols = _columns(engine, "papers")
        assert "first_author" not in cols and "year" not in cols and "title" in cols
    finally:
        command.upgrade(cfg, "head")


def test_migration_0007_caches_per_owner_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        insp = inspect(engine)
        seg_pk = insp.get_pk_constraint("seg_cache")["constrained_columns"]
        ocsr_pk = insp.get_pk_constraint("ocsr_cache")["constrained_columns"]
        assert seg_pk == ["owner_id", "pdf_sha256", "seg_version"]
        assert ocsr_pk == ["owner_id", "image_sha256", "engine", "engine_version"]
        fks = {
            (t, fk["referred_table"]): fk["options"].get("ondelete")
            for t in ("seg_cache", "ocsr_cache")
            for fk in insp.get_foreign_keys(t)
        }
        assert fks == {
            ("seg_cache", "owners"): "CASCADE",
            ("seg_cache", "papers"): "CASCADE",
            ("ocsr_cache", "owners"): "CASCADE",
        }
        assert ("seg_cache", "ix_seg_cache_paper_id") in _indexes(engine)
        assert ("seg_cache", "ix_seg_cache_created_at") in _indexes(engine)
        assert ("ocsr_cache", "ix_ocsr_cache_created_at") in _indexes(engine)
        command.downgrade(cfg, "0006")
        insp = inspect(engine)
        assert "owner_id" not in _columns(engine, "seg_cache")
        assert "paper_id" not in _columns(engine, "seg_cache")
        assert "owner_id" not in _columns(engine, "ocsr_cache")
        assert insp.get_pk_constraint("seg_cache")["constrained_columns"] == [
            "pdf_sha256", "seg_version",
        ]  # fmt: skip
        assert insp.get_pk_constraint("ocsr_cache")["constrained_columns"] == [
            "image_sha256", "engine", "engine_version",
        ]  # fmt: skip
        assert insp.get_foreign_keys("seg_cache") == insp.get_foreign_keys("ocsr_cache") == []
        assert ("seg_cache", "ix_seg_cache_paper_id") not in _indexes(engine)
        assert ("seg_cache", "ix_seg_cache_created_at") in _indexes(engine)
        assert ("ocsr_cache", "ix_ocsr_cache_created_at") in _indexes(engine)
        assert {c["name"] for c in insp.get_columns("ocsr_cache")} == {
            "image_sha256", "engine", "engine_version", "smiles", "molfile", "created_at",
        }  # fmt: skip
    finally:
        command.upgrade(cfg, "head")


def test_migration_0008_work_started_ip_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        for table in ("papers", "image_jobs"):
            cols = {c["name"]: c for c in inspect(engine).get_columns(table)}
            assert cols["started_ip"]["nullable"]
            assert (table, f"ix_{table}_started_ip") in _indexes(engine)
        command.downgrade(cfg, "0007")
        for table in ("papers", "image_jobs"):
            assert "started_ip" not in _columns(engine, table)
            assert (table, f"ix_{table}_started_ip") not in _indexes(engine)
    finally:
        command.upgrade(cfg, "head")


def test_migration_0009_work_started_ip_at_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        for table in ("papers", "image_jobs"):
            cols = {c["name"]: c for c in inspect(engine).get_columns(table)}
            assert cols["started_ip_at"]["nullable"]
        command.downgrade(cfg, "0008")
        for table in ("papers", "image_jobs"):
            assert "started_ip_at" not in _columns(engine, table)
            assert "started_ip" in _columns(engine, table)
    finally:
        command.upgrade(cfg, "head")


def test_migration_0010_annotations_up_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in inspect(engine).get_columns("annotations")}
        assert set(cols) == {
            "paper_id", "model", "model_version", "output", "positions", "curated",
            "curated_positions", "created_at", "updated_at", "curated_at",
        }  # fmt: skip
        nullable = {name for name, c in cols.items() if c["nullable"]}
        assert nullable == {"curated", "curated_positions", "curated_at"}
        assert inspect(engine).get_pk_constraint("annotations")["constrained_columns"] == [
            "paper_id"
        ]
        (fk,) = inspect(engine).get_foreign_keys("annotations")
        assert fk["referred_table"] == "papers" and fk["options"]["ondelete"] == "CASCADE"
        command.downgrade(cfg, "0009")
        assert "annotations" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(cfg, "head")


KETCHER_R1 = (
    "\n  Ketcher\n\n  2  1  0  0  0  0  0  0  0  0999 V2000\n"
    "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.0000    0.0000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0  0  0  0\nM  RGP  1   2   1\nM  END\n"
)


def test_migration_0011_rgroups_up_down_and_backfill(migrated_db):
    """0011 adds the columns and fills the rows already there: [] for a plain structure, the
    labels for a scaffold; a curation without its own structure stays NULL."""
    from sqlalchemy import text

    from marcus.core.db import get_sync_engine, get_sync_sessionmaker
    from marcus.core.models import Segment
    from tests.factories import make_paper

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.downgrade(cfg, "0010")
        assert "rgroups" not in _columns(engine, "predictions")
        with get_sync_sessionmaker()() as s:
            paper = make_paper(s)
            segs = [
                Segment(paper_id=paper.id, page=0, idx=i, bbox=[0, 0, 1, 1], image_sha256="b" * 64)
                for i in range(3)
            ]
            s.add_all(segs)
            s.flush()
            ids = [seg.id for seg in segs]
            # raw SQL: the models already have the column this revision does not
            for seg, smiles, valid in [
                (ids[0], "CCO", True),
                (ids[1], "[1*]c1ccccc1*", True),
                (ids[2], "[R1]c1ccccc1[X]", False),
            ]:
                s.execute(
                    text(
                        "INSERT INTO predictions (id, segment_id, engine, engine_version, smiles,"
                        " valid, ms) VALUES (gen_random_uuid(), :s, 'decimer', 'v', :smi, :v, 1)"
                    ),
                    {"s": seg, "smi": smiles, "v": valid},
                )
            s.execute(
                text(
                    "INSERT INTO curation (segment_id, status, molfile) VALUES"
                    " (:a, 'accepted', :m), (:b, 'accepted', NULL)"
                ),
                {"a": ids[0], "b": ids[1], "m": KETCHER_R1},
            )
            s.commit()
        command.upgrade(cfg, "0011")
        with engine.connect() as conn:
            preds = dict(conn.execute(text("SELECT segment_id, rgroups FROM predictions")).all())
            curs = dict(conn.execute(text("SELECT segment_id, rgroups FROM curation")).all())
        assert preds == {ids[0]: [], ids[1]: ["R1", "*"], ids[2]: ["R1", "X"]}
        assert curs == {ids[0]: ["R1"], ids[1]: None}
        command.downgrade(cfg, "0010")
        assert "rgroups" not in _columns(engine, "predictions")
        assert "rgroups" not in _columns(engine, "curation")
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM owners"))  # papers, segments and the rest cascade
        command.upgrade(cfg, "head")


def test_migration_0012_rgroup_extractions_up_down(migrated_db):
    """0012 adds the table (one row per prediction, cascading) and the `rgroups` step kind; the
    downgrade drops both, rgroups steps first."""
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from marcus.core.db import get_sync_engine, get_sync_sessionmaker
    from tests.factories import make_paper

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in inspect(engine).get_columns("rgroup_extractions")}
        assert set(cols) == {
            "prediction_id", "step_id", "labels", "status", "error", "rows", "truncated",
            "model", "model_version", "created_at", "updated_at", "finished_at",
        }  # fmt: skip
        nullable = {name for name, c in cols.items() if c["nullable"]}
        assert nullable == {"step_id", "error", "rows", "model", "model_version", "finished_at"}
        assert inspect(engine).get_pk_constraint("rgroup_extractions")["constrained_columns"] == [
            "prediction_id"
        ]
        fks = {fk["referred_table"]: fk for fk in inspect(engine).get_foreign_keys(
            "rgroup_extractions")}  # fmt: skip
        assert fks["predictions"]["options"]["ondelete"] == "CASCADE"
        assert fks["steps"]["options"]["ondelete"] == "SET NULL"
        assert _indexes(engine)[("rgroup_extractions", "ix_rgroup_extractions_step_id")] == [
            "step_id"
        ]
        with get_sync_sessionmaker()() as s:
            paper = make_paper(s)
            s.execute(
                text("INSERT INTO steps (paper_id, kind, queue, seq, status, id) VALUES "
                     "(:p, 'rgroups', 'q.llm', 100003, 'pending', gen_random_uuid())"),
                {"p": paper.id},
            )  # fmt: skip
            s.commit()
            with pytest.raises(IntegrityError):
                s.execute(
                    text("INSERT INTO steps (paper_id, kind, queue, seq, status, id) VALUES "
                         "(:p, 'nope', 'q.llm', 1, 'pending', gen_random_uuid())"),
                    {"p": paper.id},
                )  # fmt: skip
            s.rollback()
        command.downgrade(cfg, "0011")
        assert "rgroup_extractions" not in inspect(engine).get_table_names()
        with engine.connect() as conn:
            kinds = conn.execute(text("SELECT count(*) FROM steps WHERE kind = 'rgroups'"))
            assert kinds.scalar_one() == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM owners"))
        command.upgrade(cfg, "head")


def test_migration_0013_moves_rgroups_steps_to_their_own_queue(migrated_db):
    """0013 moves rgroups steps from q.llm to q.rgroup (annotate steps stay); a step already
    sent or started goes back to pending with one more attempt, so the dispatcher sends it again
    on q.rgroup with a new attempt token and the old q.llm message is dropped as stale, even
    once the step is queued again. The downgrade moves them back the same way."""
    from sqlalchemy import text, update

    from marcus.core.db import get_sync_engine, get_sync_sessionmaker
    from marcus.core.models import Step
    from marcus.workers import runtime
    from tests.factories import make_paper

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()

    def rows(conn):
        return sorted(
            conn.execute(
                text(
                    "SELECT kind, status, queue, attempts, queued_at IS NULL FROM steps "
                    "WHERE kind IN ('rgroups', 'annotate')"
                )
            ).all()
        )

    def state(step_id):
        with engine.connect() as conn:
            return tuple(
                conn.execute(
                    text("SELECT status, attempts FROM steps WHERE id = :i"), {"i": step_id}
                ).one()
            )

    try:
        command.downgrade(cfg, "0012")
        ids = {}
        with get_sync_sessionmaker()() as s:
            paper = make_paper(s)
            for kind, seq, status, attempts in (
                ("rgroups", 1, "pending", 0), ("rgroups", 2, "queued", 0),
                ("rgroups", 3, "running", 1), ("rgroups", 4, "done", 1),
                ("annotate", 5, "queued", 0),
            ):  # fmt: skip
                ids[seq] = s.execute(
                    text("INSERT INTO steps (paper_id, kind, queue, seq, status, attempts, "
                         "queued_at, id) VALUES (:p, :k, 'q.llm', :seq, :st, :a, "
                         "CASE WHEN :st IN ('queued', 'running') THEN now() END, "
                         "gen_random_uuid()) RETURNING id"),
                    {"p": paper.id, "k": kind, "seq": seq, "st": status, "a": attempts},
                ).scalar_one()  # fmt: skip
            s.commit()
        command.upgrade(cfg, "0013")
        with engine.connect() as conn:
            assert rows(conn) == sorted([
                ("rgroups", "pending", "q.rgroup", 0, True),
                ("rgroups", "pending", "q.rgroup", 1, True),
                ("rgroups", "pending", "q.rgroup", 2, True),
                ("rgroups", "done", "q.rgroup", 1, True),
                ("annotate", "queued", "q.llm", 0, False),
            ])  # fmt: skip
        # The dispatcher sends both again (new tokens 1 and 2); the old q.llm messages
        # (tokens 0: sent once, and redelivered after the lost worker) are stale.
        with get_sync_sessionmaker()() as s:
            s.execute(update(Step).where(Step.id.in_([ids[2], ids[3]])).values(status="queued"))
            s.commit()
        assert runtime.claim(ids[2], 0, "w") is None
        assert runtime.claim(ids[3], 0, "w") is None
        assert [state(ids[2]), state(ids[3])] == [("queued", 1), ("queued", 2)]
        assert runtime.claim(ids[3], 2, "w") is not None  # the new message runs it
        assert state(ids[3]) == ("running", 3)
        with engine.begin() as conn:
            conn.execute(text("UPDATE steps SET status = 'pending', attempts = 2, "
                              "started_at = NULL, worker_name = NULL WHERE id = :i"),
                         {"i": ids[3]})  # fmt: skip
            conn.execute(text("UPDATE steps SET status = 'pending' WHERE id = :i"), {"i": ids[2]})
        command.downgrade(cfg, "0012")
        with engine.connect() as conn:
            assert rows(conn) == sorted([
                ("rgroups", "pending", "q.llm", 0, True),
                ("rgroups", "pending", "q.llm", 1, True),
                ("rgroups", "pending", "q.llm", 2, True),
                ("rgroups", "done", "q.llm", 1, True),
                ("annotate", "queued", "q.llm", 0, False),
            ])  # fmt: skip
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM owners"))
        command.upgrade(cfg, "head")


def test_migration_0014_computes_the_labels_again(migrated_db):
    """0014: rows with labels get them again from marcus.core.rgroups (MolScribe's OMe alias is
    no label, R2O is R2, CO2R is R); rows without labels are not touched."""
    from rdkit import Chem
    from sqlalchemy import text

    from marcus.core.db import get_sync_engine, get_sync_sessionmaker
    from marcus.core.models import Segment
    from tests.factories import make_paper

    def molfile(smiles, aliases):
        mol = Chem.MolFromSmiles(smiles)
        for idx, alias in aliases.items():
            mol.GetAtomWithIdx(idx).SetProp("molFileAlias", alias)
        return Chem.MolToMolBlock(mol)

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.downgrade(cfg, "0013")
        with get_sync_sessionmaker()() as s:
            paper = make_paper(s)
            segs = [
                Segment(paper_id=paper.id, page=0, idx=i, bbox=[0, 0, 1, 1], image_sha256="c" * 64)
                for i in range(4)
            ]
            s.add_all(segs)
            s.flush()
            ids = [seg.id for seg in segs]
            for seg, smiles, mol, old in [
                (ids[0], "COc1ccccc1", molfile("*c1ccccc1", {0: "OMe"}), ["OMe"]),
                (ids[1], "[2*]Oc1ccccc1", molfile("[2*]c1ccccc1", {0: "R2O"}), ["R2O"]),
                (ids[2], "CCO", None, []),
                (ids[3], "*c1ccccc1", molfile("*c1ccccc1", {0: "CO2R"}), ["CO2R"]),
            ]:
                s.execute(
                    text(
                        "INSERT INTO predictions (id, segment_id, engine, engine_version, smiles,"
                        " molfile, valid, ms, rgroups) VALUES (gen_random_uuid(), :s,"
                        " 'molscribe', 'v', :smi, :mf, true, 1, :old)"
                    ),
                    {"s": seg, "smi": smiles, "mf": mol, "old": old},
                )
            s.commit()
        command.upgrade(cfg, "0014")
        with engine.connect() as conn:
            preds = dict(conn.execute(text("SELECT segment_id, rgroups FROM predictions")).all())
        assert preds == {ids[0]: [], ids[1]: ["R2"], ids[2]: [], ids[3]: ["R"]}
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM owners"))
        command.upgrade(cfg, "head")


def test_migration_0015_page_label_index_up_down(migrated_db):
    """0015 adds papers.rgroup_text_labels (NULL: no index, every label shown)."""
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in inspect(engine).get_columns("papers")}
        assert cols["rgroup_text_labels"]["nullable"] is True
        command.downgrade(cfg, "0014")
        assert "rgroup_text_labels" not in _columns(engine, "papers")
    finally:
        command.upgrade(cfg, "head")


def test_migration_0016_main_figures_up_down(migrated_db):
    """0016 adds the main_figures table (one row per paper at most, never a negative page)."""
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert "main_figures" in inspect(engine).get_table_names()
        assert inspect(engine).get_pk_constraint("main_figures")["constrained_columns"] == [
            "paper_id"
        ]
        checks = {c["name"] for c in inspect(engine).get_check_constraints("main_figures")}
        assert "ck_main_figures_page" in checks
        command.downgrade(cfg, "0015")
        assert "main_figures" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(cfg, "head")


def test_migration_0017_inherited_statuses_up_down(migrated_db):
    """0017 adds inherited_statuses (one row per structure; main_id without a foreign key)."""
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        insp = inspect(engine)
        assert insp.get_pk_constraint("inherited_statuses")["constrained_columns"] == ["segment_id"]
        fks = insp.get_foreign_keys("inherited_statuses")
        assert [fk["constrained_columns"] for fk in fks] == [["segment_id"]]
        command.downgrade(cfg, "0016")
        assert "inherited_statuses" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(cfg, "head")


def test_migration_0018_drawing_flags_up_down(migrated_db):
    """0018 adds the drawing_flags table (one row per flagged segment, keyed by it)."""
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert inspect(engine).get_pk_constraint("drawing_flags")["constrained_columns"] == [
            "segment_id"
        ]
        command.downgrade(cfg, "0017")
        assert "drawing_flags" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(cfg, "head")
