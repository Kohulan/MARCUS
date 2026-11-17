"""Request and response models for the v2 API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    engine: str
    ocsr_mode: str
    created_at: datetime
    expires_at: datetime
    structures: int
    accepted: int
    rejected: int
    to_review: int
    failed_pages: int


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


class QueuePaper(BaseModel):
    id: uuid.UUID
    steps_ahead_by_queue: dict[str, int]
    estimate_s: float


class QueueOut(BaseModel):
    papers: list[QueuePaper]
    estimate_s: float
