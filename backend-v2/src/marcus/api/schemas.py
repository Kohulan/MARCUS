"""Request and response models for the v2 API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from marcus.core import annotation as ann
from marcus.core.enums import Engine

MAX_MOLFILE_BYTES = 200 * 1024
MAX_SMILES_CHARS = 2000  # as the tools routes; RDKit parses run in marcus.api.chempool
MAX_NOTE_CHARS = 2000

CurationStatus = Literal["unchecked", "accepted", "rejected"]


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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
    annotating: bool  # busy only with its annotation (its only step in flight is annotate)
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


class CurationOut(_Orm):
    status: CurationStatus
    smiles: str | None
    molfile: str | None
    note: str | None


class PredictionOut(_Orm):
    id: uuid.UUID
    engine: str
    engine_version: str
    smiles: str
    molfile: str | None
    valid: bool
    ms: int
    cached: bool
    created_at: datetime


class SegmentOut(BaseModel):
    id: uuid.UUID
    page: int
    idx: int
    bbox: list[int]
    curation: CurationOut | None
    predictions: list[PredictionOut]


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
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StepList(BaseModel):
    steps: list[StepOut]


class PaperDetail(PaperSummary):
    counts: Counts
    segments: list[SegmentOut]


class PredictionRequest(BaseModel):
    engine: Engine


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


MAX_BULK_ITEMS = 500


class BulkCurationItem(BaseModel):
    """Status for one segment. A `note` key that is absent keeps the stored note; a present
    one (a string or null) replaces it. smiles and molfile are never touched."""

    model_config = ConfigDict(extra="forbid")

    segment_id: uuid.UUID
    status: CurationStatus
    note: str | None = Field(None, max_length=MAX_NOTE_CHARS)

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


class ImagePrediction(_Orm):
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


class AnnotationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rerun: bool = False  # run the model again although the paper has an annotation


class AnnotationStarted(BaseModel):
    """`step_id`: the annotate step started (or still running); null when the paper already
    has an annotation and no re-run was asked for (HTTP 200 instead of 202)."""

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
