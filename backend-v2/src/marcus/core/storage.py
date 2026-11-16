"""Server-made filesystem paths. Only uuid.UUID identifiers are accepted."""

import uuid
from pathlib import Path

from marcus.core.settings import get_settings


def _uuid(value: object) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise TypeError(f"expected uuid.UUID, got {type(value).__name__}")
    return value


def paper_dir(paper_id: uuid.UUID) -> Path:
    return get_settings().data_root / "papers" / str(_uuid(paper_id))


def pdf_path(paper_id: uuid.UUID) -> Path:
    return paper_dir(paper_id) / "source.pdf"


def page_image_path(paper_id: uuid.UUID, page: int) -> Path:
    if isinstance(page, bool) or not isinstance(page, int):
        raise TypeError("page must be int")
    if page < 0:
        raise ValueError("page must be >= 0")
    return paper_dir(paper_id) / "pages" / f"{page:04d}.png"


def segment_image_path(paper_id: uuid.UUID, segment_id: uuid.UUID) -> Path:
    return paper_dir(paper_id) / "segments" / f"{_uuid(segment_id)}.png"


def image_job_path(job_id: uuid.UUID) -> Path:
    return get_settings().data_root / "images" / f"{_uuid(job_id)}.png"
