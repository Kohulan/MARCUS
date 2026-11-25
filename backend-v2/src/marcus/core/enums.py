from enum import IntEnum, StrEnum


class StepKind(StrEnum):
    CHECK_PDF = "check_pdf"
    RENDER_PAGE = "render_page"
    SEGMENT_PAGE = "segment_page"
    OCSR = "ocsr"
    DOCLING = "docling"
    DOI = "doi"
    ANNOTATE = "annotate"
    RGROUPS = "rgroups"  # one scaffold's R-group rows (marcus.core.rgroup_extraction)


class StepStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorClass(StrEnum):
    TIMEOUT = "timeout"
    WORKER_LOST = "worker_lost"
    BAD_INPUT = "bad_input"
    ENGINE_ERROR = "engine_error"


class Engine(StrEnum):
    DECIMER = "decimer"
    DECIMER_HAND = "decimer-hand"
    MOLNEXTR = "molnextr"  # legacy: old rows only, never run (replaced by molparser)
    MOLPARSER = "molparser"
    MOLSCRIBE = "molscribe"
    FAKE = "fake"


class OwnerKind(StrEnum):
    BROWSER = "browser"
    API_KEY = "api_key"


class PaperStatus(StrEnum):
    CHECKING = "checking"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    DELETED = "deleted"


class ImageJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    DELETED = "deleted"


# Status sets used by more than one module (plain values, for SQL IN lists)
ACTIVE_PAPER_STATUSES = (PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value)
ACTIVE_IMAGE_STATUSES = (ImageJobStatus.QUEUED.value, ImageJobStatus.PROCESSING.value)
WAITING_STEPS = (StepStatus.PENDING.value, StepStatus.QUEUED.value)  # not yet started
FINISHED_STEPS = (StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.CANCELLED.value)


class PriorityClass(IntEnum):
    BROWSER = 0
    API = 1
