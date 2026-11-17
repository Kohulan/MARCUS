"""Server-made filesystem paths. Only uuid.UUID identifiers are accepted."""

import os
import re
import shutil
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


_SHA256 = re.compile(r"[0-9a-f]{64}")


def segment_crop_path(paper_id: uuid.UUID, sha256: str) -> Path:
    """Content-addressed crop: the segment worker does not know Segment ids yet."""
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ValueError("sha256 must be 64 lowercase hex characters")
    return paper_dir(paper_id) / "segments" / "by-sha" / f"{sha256}.png"


def disk_is_full() -> bool:
    """Free bytes on the data volume below Settings.min_free_disk_bytes (an unreadable volume
    counts as full: nothing could be stored either). Uploads answer 503 and render_page writes
    nothing while it holds."""
    settings = get_settings()
    try:
        return shutil.disk_usage(settings.data_root).free < settings.min_free_disk_bytes
    except OSError:
        return True


def write_atomic(path: Path, data: bytes, mode: int | None = None, *, unique: bool = True) -> None:
    """Write `data` to `path` via a temp file and os.replace: a reader sees the old file or the
    whole new one, never a part. `mode`: the new file's permission bits (default: the umask's).

    The temp file sits next to `path` and ends in `.tmp`; it is removed on any failure, and a
    crash's leftover is removed by retention (with its paper dir, or as `<image job>.png.tmp`).
    Its name is unique per call (`<name>.<pid>.<random>.tmp`), so concurrent writers of one
    path (a content-addressed crop) never share it. `unique=False` names it `<name>.tmp`: only
    for a path a single writer owns (a new image job's file, whose leftover retention sweeps).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    name = f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp" if unique else f"{path.name}.tmp"
    tmp = path.with_name(name)
    try:
        if mode is None:
            tmp.write_bytes(data)
        else:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
