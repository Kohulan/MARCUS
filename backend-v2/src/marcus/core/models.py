"""ORM models. Status/kind/engine columns are text with CHECK constraints."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CHAR, INET, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from marcus.core.db import Base
from marcus.core.enums import (
    BUILT_ENGINE,
    OCSR_MODES,
    Engine,
    ErrorClass,
    ImageJobStatus,
    OwnerKind,
    PaperStatus,
    StepKind,
    StepStatus,
)

TZ = TIMESTAMP(timezone=True)
NOW = func.now()


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


ENGINES = [e.value for e in Engine]
# predictions and steps: the engines, and the built structures (marcus.core.enumeration)
PREDICTION_ENGINES = [*ENGINES, BUILT_ENGINE]
IMAGE_JOB_STATUSES = [s.value for s in ImageJobStatus]


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _fk(target: str, nullable: bool = False):
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete="CASCADE"), nullable=nullable
    )


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        CheckConstraint(_in("kind", [k.value for k in OwnerKind]), name="ck_owners_kind"),
        Index("ix_owners_created_ip_created_at", "created_ip", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    priority_class: Mapped[int] = mapped_column(Integer)
    created_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    last_seen_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    revoked_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)
    daily_page_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint(_in("ocsr_mode", OCSR_MODES), name="ck_papers_ocsr_mode"),
        CheckConstraint(_in("status", [s.value for s in PaperStatus]), name="ck_papers_status"),
        CheckConstraint(_in("engine", ENGINES), name="ck_papers_engine"),
        Index("ix_papers_owner_id_status", "owner_id", "status"),
        Index("ix_papers_expires_at", "expires_at"),
        Index("ix_papers_started_ip", "started_ip"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _fk("owners.id")
    display_name: Mapped[str] = mapped_column(Text)
    pdf_sha256: Mapped[str] = mapped_column(CHAR(64))
    bytes: Mapped[int] = mapped_column(Integer)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_author: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine: Mapped[str] = mapped_column(Text)
    ocsr_mode: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    # The address bucket (marcus.api.deps.rate_key_for_ip) that started the work, kept only
    # while it is active: the per-address active-work cap counts it. Cleared when the work
    # finishes, fails or is deleted (and by the retention purge as a backstop).
    started_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When started_ip was last set (creation or reopen): the retention backstop ages it by this.
    started_ip_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)
    # Per page (0-based, key a string), the R-group labels its text names (docling result,
    # marcus.core.rgroup_labels.page_label_index): a structure shows only those of its labels.
    # NULL: no index (text not read, unreadable, or a paper from before 0015): all shown.
    # Deferred: only the routes that show labels load it (undefer; see api.deps, with_labels).
    rgroup_text_labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)


class ImageJob(Base):
    __tablename__ = "image_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", IMAGE_JOB_STATUSES), name="ck_image_jobs_status"),
        CheckConstraint(_in("engine", ENGINES), name="ck_image_jobs_engine"),
        Index("ix_image_jobs_owner_id", "owner_id"),
        Index("ix_image_jobs_expires_at", "expires_at"),
        Index("ix_image_jobs_started_ip", "started_ip"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = _fk("owners.id")
    display_name: Mapped[str] = mapped_column(Text)
    image_sha256: Mapped[str] = mapped_column(CHAR(64))
    engine: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    # The address bucket (marcus.api.deps.rate_key_for_ip) that started the work, kept only
    # while it is active: the per-address active-work cap counts it. Cleared when the work
    # finishes, fails or is deleted (and by the retention purge as a backstop).
    started_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When started_ip was last set (creation or reopen): the retention backstop ages it by this.
    started_ip_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("paper_id", "page", "idx", name="uq_segments_paper_page_idx"),
        CheckConstraint("cardinality(bbox) = 4", name="ck_segments_bbox_len"),
        Index("ix_segments_image_sha256", "image_sha256"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    paper_id: Mapped[uuid.UUID] = _fk("papers.id")
    page: Mapped[int] = mapped_column(Integer)
    idx: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    image_sha256: Mapped[str] = mapped_column(CHAR(64))


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (
        CheckConstraint(
            "(paper_id IS NOT NULL)::int + (image_job_id IS NOT NULL)::int = 1",
            name="ck_steps_one_parent",
        ),
        CheckConstraint(_in("kind", [k.value for k in StepKind]), name="ck_steps_kind"),
        CheckConstraint(_in("status", [s.value for s in StepStatus]), name="ck_steps_status"),
        CheckConstraint(
            "engine IS NULL OR " + _in("engine", PREDICTION_ENGINES), name="ck_steps_engine"
        ),
        CheckConstraint(
            "error_class IS NULL OR " + _in("error_class", [e.value for e in ErrorClass]),
            name="ck_steps_error_class",
        ),
        Index("ix_steps_queue_status", "queue", "status"),
        Index("ix_steps_paper_id_status", "paper_id", "status"),
        Index("ix_steps_segment_id", "segment_id"),
        Index("ix_steps_image_job_id", "image_job_id"),
        Index("ix_steps_queue_finished_at", "queue", "finished_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    paper_id: Mapped[uuid.UUID | None] = _fk("papers.id", nullable=True)
    image_job_id: Mapped[uuid.UUID | None] = _fk("image_jobs.id", nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    queue: Mapped[str] = mapped_column(Text)
    engine: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment_id: Mapped[uuid.UUID | None] = _fk("segments.id", nullable=True)
    seq: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    queued_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)
    worker_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The model version the result came from (segment_page: the segmenter version).
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint(_in("engine", PREDICTION_ENGINES), name="ck_predictions_engine"),
        Index("ix_predictions_segment_id", "segment_id"),
        Index("ix_predictions_image_job_id", "image_job_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    segment_id: Mapped[uuid.UUID | None] = _fk("segments.id", nullable=True)
    image_job_id: Mapped[uuid.UUID | None] = _fk("image_jobs.id", nullable=True)
    engine: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(Text)
    smiles: Mapped[str] = mapped_column(Text)
    molfile: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid: Mapped[bool] = mapped_column()
    ms: Mapped[int] = mapped_column(Integer)
    # True when the result came from ocsr_cache (ms is then 0), not from the engine
    cached: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # R-group labels of the structure (marcus.core.rgroups; [] none, NULL not computed)
    rgroups: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    # InChIKey of a valid structure (marcus.core.agreement: the engines agree on the full
    # key); NULL when invalid, an R-group scaffold, or made before 0019.
    inchikey: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The paper layout (marcus.core.paper_layout): MolScribe's atom positions in the image's
    # pixels as a molfile, kept also when its answer is invalid. NULL without one.
    layout: Mapped[str | None] = mapped_column(Text, nullable=True)


class Curation(Base):
    __tablename__ = "curation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('unchecked', 'accepted', 'rejected')", name="ck_curation_status"
        ),
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text)
    smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    molfile: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # R-group labels of the curated structure (marcus.core.rgroups); NULL without one
    rgroups: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    # The prediction shown when an accept or reject without a structure of its own was saved
    # (marcus.api.decisions): shown from then on (agreement.pick_prediction). NULL: none.
    shown_prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )


def _owner_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), primary_key=True
    )


class SegCache(Base):
    """Per owner (security F6): one owner's row is never another owner's hit. `paper_id`: the
    paper whose segmentation the row holds; deleting that paper drops the row."""

    __tablename__ = "seg_cache"
    __table_args__ = (
        Index("ix_seg_cache_created_at", "created_at"),
        Index("ix_seg_cache_paper_id", "paper_id"),
    )

    owner_id: Mapped[uuid.UUID] = _owner_pk()
    pdf_sha256: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    seg_version: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[uuid.UUID] = _fk("papers.id")
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class OcsrCache(Base):
    """Per owner (security F3): a hit, `cached: true` and `ms` 0, only ever follows the same
    owner's own earlier prediction of the same bytes."""

    __tablename__ = "ocsr_cache"
    __table_args__ = (Index("ix_ocsr_cache_created_at", "created_at"),)

    owner_id: Mapped[uuid.UUID] = _owner_pk()
    image_sha256: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    engine: Mapped[str] = mapped_column(Text, primary_key=True)
    engine_version: Mapped[str] = mapped_column(Text, primary_key=True)
    smiles: Mapped[str] = mapped_column(Text)
    molfile: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The paper layout of a layout engine's row: NULL never tried (a row from before 0024),
    # '' tried and none, else the molfile (marcus.workers.ocsr.handler).
    layout: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Annotation(Base):
    """The MARCUS model's annotation of one paper (marcus.core.annotation). `output`:
    {field: [values]} of the model run; `positions`: {field: {value: [[block, start, end]]}} of
    those values in the paper's text. `curated` / `curated_positions`: the curator's values
    (every field) and theirs; NULL until corrected, and again after "reset to model"."""

    __tablename__ = "annotations"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    output: Mapped[dict] = mapped_column(JSONB)
    positions: Mapped[dict] = mapped_column(JSONB)
    curated: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    curated_positions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    curated_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)


RGROUP_STATUSES = ("queued", "done", "failed")


class RgroupExtraction(Base):
    """The R-group model's reading of one scaffold (marcus.core.rgroup_extraction), per
    prediction. `labels`: the prediction's R-group labels when it was asked for; `step_id`: the
    newest rgroups step (its request). `status`: queued (asked, not ended: the step tells
    queued from running), done, failed; `error`: the failed step's error class (public words
    only, never the step's error text). `rows` ([{compound, groups: {label: value}}]), `model`,
    `model_version`, `truncated`: of the newest run that ended well; a re-run replaces them when
    it ends well and keeps them otherwise. Deleting the prediction (its segment, its paper)
    deletes the row; deleting a paper deletes it at once (pipeline.cancel_paper)."""

    __tablename__ = "rgroup_extractions"
    __table_args__ = (
        CheckConstraint(_in("status", RGROUP_STATUSES), name="ck_rgroup_extractions_status"),
        Index("ix_rgroup_extractions_step_id", "step_id", unique=True),
    )

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), primary_key=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("steps.id", ondelete="SET NULL"), nullable=True
    )
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    truncated: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    finished_at: Mapped[datetime | None] = mapped_column(TZ, nullable=True)


class MainFigure(Base):
    """The page the user marked as a paper's main figure, its compound list: its structures come
    first, and a structure on another page showing the same compound is a repeat of one of them
    (marcus.core.main_figure). At most one per paper; no row: none. A table of its own, not a
    papers column: the papers rows stay as the migration tests of older revisions write them."""

    __tablename__ = "main_figures"
    __table_args__ = (CheckConstraint("page >= 0", name="ck_main_figures_page"),)

    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    page: Mapped[int] = mapped_column(Integer)  # 0-based, as Segment.page
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class InheritedStatus(Base):
    """A curation status a structure got from a decision on its main-figure structure
    (marcus.api.decisions); `main_id`: that structure (no foreign key: the row outlives it). Read
    as "unchecked" while the structure is not a repeat of it (core.main_figure.stale_members).
    A decision on the structure itself deletes the row."""

    __tablename__ = "inherited_statuses"

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )
    main_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DrawingFlag(Base):
    """A segment whose crop is not a clean drawing: NMR marks or an X-ray / 3D picture ("check
    this drawing"; segment_page, marcus.workers.drawing_check). No row: a clean drawing, or a
    segment from before the check. A table of its own, not a segments column: the migration
    tests of older revisions insert segments through the ORM."""

    __tablename__ = "drawing_flags"

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )


class BackgroundStep(Base):
    """An OCSR step the planner added beside the paper's own read: the engines of
    marcus.core.agreement other than the paper's (phase B item 3). It never keeps the paper busy,
    counts in its progress or fails it (pipeline.in_paper_progress). A table of its own, not a
    steps column: the migration tests of older revisions write steps through the ORM."""

    __tablename__ = "background_steps"

    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("steps.id", ondelete="CASCADE"), primary_key=True
    )


class BuiltSegment(Base):
    """A structure MARCUS built from a scaffold and one of its R-group rows (Markush Phase 3,
    marcus.core.built): a segment with the scaffold's crop and position (idx 10000 and up), an
    `enumerated` prediction and a curation, linked here to its scaffold. `row_key`: the row's
    compound ID; `input_hash`: of the scaffold structure and the row's groups (the rebuild rule).
    A table of its own, not a segments column: the migration tests of older revisions insert
    segments through the ORM."""

    __tablename__ = "built_segments"
    __table_args__ = (
        UniqueConstraint("scaffold_segment_id", "row_key", name="uq_built_segments_scaffold_row"),
        Index("ix_built_segments_scaffold_segment_id", "scaffold_segment_id"),
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )
    scaffold_segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE")
    )
    row_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_hash: Mapped[str] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class ScaffoldBuild(Base):
    """A scaffold's last build (Markush Phase 3): the rows that could not be built, with the
    reason ([{compound, reason}]); the built ones are BuiltSegment rows."""

    __tablename__ = "scaffold_builds"

    scaffold_segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )
    failures: Mapped[list] = mapped_column(JSONB)
    built_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
