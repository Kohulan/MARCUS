"""Request and response models for the v2 API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from marcus.core import annotation as ann
from marcus.core.drawable import is_drawable
from marcus.core.enums import Engine
from marcus.core.molfile import absolute_stereo

MAX_MOLFILE_BYTES = 200 * 1024
MAX_SMILES_CHARS = 2000  # as the tools routes; RDKit parses run in marcus.api.chempool
MAX_NOTE_CHARS = 2000

CurationStatus = Literal["unchecked", "accepted", "rejected"]


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _RGroups(BaseModel):
    """`rgroups`: the R-group labels of the structure (marcus.core.rgroups), [] for none; in a
    paper, those its page's text names (marcus.core.rgroup_labels.shown_labels; all of them
    when it names none). `placeholder`: the structure has R-group placeholder atoms, whatever
    labels are shown. A structure with placeholders stands for several compounds: it is not
    sent to COCONUT."""

    rgroups: list[str] = []
    placeholder: bool = False

    @field_validator("rgroups", mode="before")
    @classmethod
    def _none_is_empty(cls, value: list[str] | None) -> list[str]:
        return value or []

    @model_validator(mode="after")
    def _placeholder(self):
        self.placeholder = bool(self.rgroups)
        return self


class _EngineMolfile(BaseModel):
    """An engine's molfile with chiral flag 1 when it has wedge bonds, as its SMILES
    (marcus.core.molfile). Also covers rows stored before the fix."""

    molfile: str | None

    @field_validator("molfile")
    @classmethod
    def _absolute(cls, value: str | None) -> str | None:
        return absolute_stereo(value)


class PaperSummary(_Orm):
    id: uuid.UUID
    display_name: str
    status: str
    pages: int | None
    doi: str | None
    title: str | None
    first_author: str | None
    year: int | None
    engine: str
    ocsr_mode: str
    created_at: datetime
    expires_at: datetime
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int
    failed: int
    # The read's coarse progress, for the tool home's row bar (frontend readingProgress.ts reads
    # the same from the steps): pages whose newest page step ended, structures with an OCSR step
    # and those read (or with nothing in flight), the text read (every docling step ended; with
    # none, every page), a check_pdf step started, busy only re-reading read structures.
    pages_read: int
    structures_total: int
    structures_read: int
    text_read: bool
    check_started: bool
    rereading: bool


class PaperList(BaseModel):
    papers: list[PaperSummary]


class Counts(BaseModel):
    steps_by_status: dict[str, int]


class CurationOut(_RGroups, _Orm):
    status: CurationStatus
    smiles: str | None
    molfile: str | None
    note: str | None


class UploadPaperOut(BaseModel):
    """POST /papers: the new paper, or (`reused`) this browser's earlier paper of the same file
    (owner request 2026-11-26)."""

    paper_id: uuid.UUID
    status: str
    reused: bool = False


class PredictionOut(_EngineMolfile, _RGroups, _Orm):
    id: uuid.UUID
    engine: str
    engine_version: str
    smiles: str
    molfile: str | None
    valid: bool
    ms: int
    cached: bool
    created_at: datetime
    # the server can draw it (marcus.core.drawable): valid, or an R-group scaffold
    drawable: bool = False

    @model_validator(mode="after")
    def _drawable(self):
        self.drawable = is_drawable(self.smiles, self.valid, self.rgroups)
        return self


class BuildFailure(BaseModel):
    """A row of a scaffold's R-group table that was not built, and why ("Could not build")."""

    compound: str
    reason: str


class SegmentOut(BaseModel):
    id: uuid.UUID
    page: int
    idx: int
    bbox: list[int]
    curation: CurationOut | None
    predictions: list[PredictionOut]
    # The main-figure structure this one repeats (same compound on another page:
    # marcus.core.main_figure); None for every other structure, and without a main figure.
    repeat_of: uuid.UUID | None = None
    # The crop is not a clean drawing (NMR marks, an X-ray / 3D picture): "check this drawing"
    # (a drawing_flags row; false for a clean one, and for segments from before the check).
    check_drawing: bool = False
    # The compound ID printed by the drawing ("12", "8a"; marcus.core.compound_ids, from the
    # paper's Docling text), and the name the text gives it ("salsubstolin A (12)"); None
    # without one.
    compound_id: str | None = None
    compound_name: str | None = None
    # Pages (0-based) of structures with the same compound ID but another InChIKey, not linked
    # (marcus.core.main_figure.id_conflicts: the main-figure one, or its look-alikes): "check".
    same_id_pages: list[int] = []
    # The engines' agreement (marcus.core.agreement): 3 or 2 agree, 0 they differ, of `agree_of`
    # engines that read (3, or 2 for a structure only two engines read); None while an engine is
    # still reading, with fewer than two read or two with an InChIKey, and for a scaffold.
    agree: int | None = None
    agree_of: int | None = None
    # The badge state (agreement.badge): "agree3", "agree2", "stereo" (the same connectivity,
    # no two the same stereo) or "differ"; None with `agree` None. Agree = the full InChIKey.
    agree_state: str | None = None
    # Pick mode (marcus.core.picks): a box the user has not picked; drawn on its page only, no
    # card, in no count, export or bulk action.
    candidate: bool = False
    # Markush Phase 3: a built structure's scaffold segment (None for every other segment), and
    # on a scaffold that was built, the rows that could not be (None when never built).
    built_from: uuid.UUID | None = None
    build_failures: list[BuildFailure] | None = None
    # The engines that agree ([] none), in DECIMER, MolParser (MolNexTR on old papers), MolScribe
    # order.
    agree_engines: list[str] = []
    # The prediction shown when nothing is curated (agreement.pick_prediction); None without a
    # valid one.
    default_prediction_id: uuid.UUID | None = None


class SegmentList(BaseModel):
    segments: list[SegmentOut]


class StepOut(_Orm):
    """One pipeline step. No `error` text: only the coarse `error_class` is public."""

    id: uuid.UUID
    kind: str
    page: int | None
    segment_id: uuid.UUID | None
    status: str
    attempts: int
    error_class: str | None
    engine: str | None  # set for ocsr steps
    # A background OCSR step (another engine, beside the paper's read): it never counts in the
    # paper's progress, and its failure is no failure of the structure.
    background: bool = False
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StepList(BaseModel):
    steps: list[StepOut]


class PaperDetail(PaperSummary):
    # The page (0-based) marked as the main figure, the paper's compound list; None: none.
    main_figure_page: int | None
    # False when the repeats of the main figure could not be linked (the chem process busy):
    # no segment has repeat_of, so the client must not send structures to COCONUT yet.
    links_ready: bool = True
    counts: Counts
    segments: list[SegmentOut]


class PredictionRequest(BaseModel):
    engine: Engine


class ModeIn(BaseModel):
    """The user's answer on the paper page: read all pages, or pick a structure."""

    mode: Literal["auto", "pick"]


class ModeOut(BaseModel):
    ocsr_mode: str


class SegmentAccepted(BaseModel):
    """A page opened in pick mode: its segment_page step, or None when its boxes are there."""

    step_id: uuid.UUID | None


class ReadAccepted(BaseModel):
    """A box picked in pick mode: its OCSR steps (the three engines)."""

    step_ids: list[uuid.UUID]


class BuildOut(BaseModel):
    """A build of a scaffold's rows (Markush Phase 3): new or refreshed cards, cards kept
    (a curator's, or unchanged), cards removed, and the rows not built."""

    built: int
    kept: int
    removed: int
    failures: list[BuildFailure]


class StepAccepted(BaseModel):
    step_id: uuid.UUID


class CurationIn(BaseModel):
    """PUT replaces the whole curation: omitted fields are cleared. Empty strings mean None."""

    model_config = ConfigDict(extra="forbid")

    status: CurationStatus
    smiles: str | None = Field(None, max_length=MAX_SMILES_CHARS)
    molfile: str | None = None
    note: str | None = Field(None, max_length=MAX_NOTE_CHARS)

    @field_validator("smiles", "molfile", "note")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\x00" in value:
            raise ValueError("must not contain NUL characters")
        return value if value.strip() else None

    @field_validator("molfile")
    @classmethod
    def _molfile_size(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > MAX_MOLFILE_BYTES:
            raise ValueError(f"molfile must be at most {MAX_MOLFILE_BYTES} bytes")
        return value

    @field_validator("smiles")
    @classmethod
    def _smiles_strip(cls, value: str | None) -> str | None:
        # Whether RDKit can read the SMILES / molfile is checked by the route, after the owner
        # check and outside the event loop (marcus.api.chem.curation_error).
        return value.strip() if value is not None else None


class MainFigureIn(BaseModel):
    """The page (0-based) to mark as the paper's main figure; null clears the mark."""

    model_config = ConfigDict(extra="forbid")

    page: int | None = Field(..., ge=0)


class MainFigureOut(BaseModel):
    main_figure_page: int | None


MAX_BULK_ITEMS = 500


class BulkCurationItem(BaseModel):
    """Status for one segment. A `note` key that is absent keeps the stored note; a present
    one (a string or null) replaces it. smiles and molfile are never touched."""

    model_config = ConfigDict(extra="forbid")

    segment_id: uuid.UUID
    status: CurationStatus
    note: str | None = Field(None, max_length=MAX_NOTE_CHARS)
    # The prediction the card showed: frozen with the decision (marcus.api.decisions); it must be
    # the segment's own. Absent: the server's pick.
    shown_prediction_id: uuid.UUID | None = None

    @field_validator("note")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\x00" in value:
            raise ValueError("must not contain NUL characters")
        return value if value.strip() else None


class BulkCurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BulkCurationItem] = Field(min_length=1, max_length=MAX_BULK_ITEMS)

    @field_validator("items")
    @classmethod
    def _unique(cls, items: list[BulkCurationItem]) -> list[BulkCurationItem]:
        if len({i.segment_id for i in items}) != len(items):
            raise ValueError("segment_id appears more than once")
        return items


class BulkCurationOut(BaseModel):
    updated: int


class QueuePaper(BaseModel):
    id: uuid.UUID
    steps_ahead_by_queue: dict[str, int]
    estimate_s: float


class QueueOut(BaseModel):
    papers: list[QueuePaper]
    estimate_s: float


class ImagePrediction(_EngineMolfile, _RGroups, _Orm):
    smiles: str
    molfile: str | None
    valid: bool
    engine: str
    engine_version: str
    ms: int


class ImageStepOut(BaseModel):
    """One ocsr step of an image job. No error text: only the coarse `error_class`."""

    engine: str
    status: str
    error_class: str | None


class ImageJobSummary(_Orm):
    id: uuid.UUID
    display_name: str
    status: str
    engine: str
    created_at: datetime
    expires_at: datetime


class ImageJobList(BaseModel):
    jobs: list[ImageJobSummary]


class ImageJobOut(BaseModel):
    id: uuid.UUID
    status: str
    engine: str
    display_name: str
    created_at: datetime
    expires_at: datetime
    prediction: ImagePrediction | None  # the newest one
    predictions: list[PredictionOut]  # all, newest first
    error_class: str | None  # of the newest failed step
    steps: list[ImageStepOut]  # newest first
    error: str | None  # kept for API compatibility; the UI never shows it


# --- annotation (marcus.core.annotation; routes in marcus.api.routes.annotation) ---------------

Values = dict[str, list[str]]  # {field: [values]} over the 11 fields, in ann.FIELDS order
# {field: {value: [[block, start, end], ...]}}: block = index in the Paper view's text blocks
# (frontend-v2 doclingBlocks), start/end = UTF-16 offsets in that block's text, end exclusive
Positions = dict[str, dict[str, list[list[int]]]]
StepState = Literal["none", "pending", "queued", "running", "done", "failed", "cancelled"]


class AnnotationField(BaseModel):
    key: str
    label: str
    max_length: int  # the longest value a curation may hold in this field (the model's maxLength)


class AnnotationLimits(BaseModel):
    """What one curation save may hold (PUT answers 422 beyond it)."""

    max_values_per_field: int
    max_total_values: int


class CoconutOrganism(BaseModel):
    """frontend-v2 coconut OrganismDraft: parts and ecosystems are comma-separated (an item
    with a comma in double quotes). The prefill leaves ecosystems empty."""

    name: str
    parts: str
    location: str
    ecosystems: str


class CoconutPrefill(BaseModel):
    organisms: list[CoconutOrganism]
    kingdom: list[str]  # COCONUT has no kingdom field: for the curator to place


class AnnotationOut(BaseModel):
    """A paper's annotation. `status`: its newest annotate step's status ("none": never asked
    for). `output`/`positions`: the model's values (kept as they were); `curated`/
    `curated_positions`: the curator's (null until saved, and again after a reset); `values`:
    what is shown and exported (curated, else output). The model text never reaches HTML: every
    value is a plain string."""

    available: bool  # this deployment can annotate (POST answers 503 otherwise)
    status: StepState
    step: StepOut | None
    fields: list[AnnotationField]
    limits: AnnotationLimits
    model: str | None
    model_version: str | None
    output: Values | None
    positions: Positions | None
    curated: Values | None
    curated_positions: Positions | None
    values: Values | None
    coconut: CoconutPrefill | None
    created_at: datetime | None
    updated_at: datetime | None
    curated_at: datetime | None
    # GET only: the annotation starts by itself within seconds (the text is read, nothing was
    # asked yet, a worker serves q.llm; marcus.core.auto): read GET again.
    auto_pending: bool = False


class AnnotationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rerun: bool = False  # run the model again although the paper has an annotation


class AnnotationStarted(BaseModel):
    """`step_id`: the annotate step started (or still running); null when the paper already
    has an annotation and no re-run was asked for (HTTP 200 instead of 202)."""

    step_id: uuid.UUID | None


class RgroupRow(BaseModel):
    """One compound the scaffold stands for: its label as the paper writes it, and the
    substituent for every R-group label ("" where the paper gives none)."""

    compound: str
    groups: dict[str, str]


RgroupState = Literal["none", "queued", "running", "done", "failed"]


class RgroupExtractionOut(BaseModel):
    """The R-group model's reading of one scaffold (a prediction with R-group labels).

    `status`: none (never asked for), queued, running, done, failed (the newest run; `error`:
    its error class: timeout, engine_error, bad_input or worker_lost). `labels`: the labels it
    was asked for (the table's columns, in order). `rows`, `model`, `model_version`,
    `truncated` (the token limit cut the answer: rows after the cut are missing): of the newest
    run that ended well, kept while a re-run runs or after one fails; null before any. Model
    output to check: every value is a plain string, never markup."""

    prediction_id: uuid.UUID
    segment_id: uuid.UUID
    status: RgroupState
    labels: list[str]
    rows: list[RgroupRow] | None
    truncated: bool
    error: str | None
    model: str | None
    model_version: str | None
    created_at: datetime | None
    updated_at: datetime | None
    finished_at: datetime | None


class RgroupList(BaseModel):
    """A paper's R-group readings, one per prediction that was asked for (paper order)."""

    available: bool  # this deployment can read R-groups (POST answers 503 otherwise)
    extractions: list[RgroupExtractionOut]
    # predictions whose reading starts by itself within seconds (a worker serves q.rgroup;
    # marcus.core.auto): read the list again
    auto_pending: list[uuid.UUID] = []


class RgroupStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rerun: bool = False  # run the model again although the scaffold has rows


class RgroupStarted(BaseModel):
    """`step_id`: the rgroups step started (or still running); null when the scaffold already
    has rows and no re-run was asked for (HTTP 200 instead of 202)."""

    step_id: uuid.UUID | None


class AnnotationCurationIn(BaseModel):
    """Every field's values as the curator wants them (all 11 keys; [] = none). Each value is
    trimmed (hidden characters out, spaces collapsed); empty ones and exact repeats are
    dropped."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, list[str]]

    @field_validator("values")
    @classmethod
    def _fields(cls, values: dict[str, list[str]]) -> dict[str, list[str]]:
        if set(values) != set(ann.FIELDS):
            raise ValueError("values must have exactly the 11 fields")
        if sum(len(items) for items in values.values()) > ann.MAX_CURATED_VALUES:
            raise ValueError(f"at most {ann.MAX_CURATED_VALUES} values in all")
        out: dict[str, list[str]] = {}
        for field in ann.FIELDS:
            items = values[field]
            if len(items) > ann.MAX_VALUES_PER_FIELD:
                raise ValueError(f"{field}: at most {ann.MAX_VALUES_PER_FIELD} values")
            kept: list[str] = []
            for item in items:
                if len(item) > ann.MAX_LENGTH[field]:
                    raise ValueError(f"{field}: a value is longer than {ann.MAX_LENGTH[field]}")
                value = ann.clean_value(item)
                if value and value not in kept:
                    kept.append(value)
            out[field] = kept
        return out
