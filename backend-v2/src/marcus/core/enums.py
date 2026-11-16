from enum import IntEnum, StrEnum


class StepKind(StrEnum):
    CHECK_PDF = "check_pdf"
    RENDER_PAGE = "render_page"
    SEGMENT_PAGE = "segment_page"
    OCSR = "ocsr"
    DOCLING = "docling"
    DOI = "doi"
    ANNOTATE = "annotate"


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
    MOLNEXTR = "molnextr"
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


class PriorityClass(IntEnum):
    BROWSER = 0
    API = 1
