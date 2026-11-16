"""Upload helpers: bounded reads, type sniffing, display-name sanitising."""

import unicodedata

from fastapi import HTTPException, UploadFile

CHUNK = 1024 * 1024
DEFAULT_NAME = "upload.pdf"
MAX_NAME = 200


async def read_limited(upload: UploadFile, limit: int) -> bytes:
    """Read the whole upload, raising 413 once more than `limit` bytes have been seen.

    Never trusts Content-Length; holds at most limit + 1 bytes in memory.
    """
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(CHUNK, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="File too large")
        parts.append(chunk)
    return b"".join(parts)


def sniff_pdf(data: bytes) -> None:
    if b"%PDF-" not in data[:1024]:
        raise HTTPException(status_code=415, detail="Not a PDF file")


def sanitize_display_name(name: str | None) -> str:
    """Label for the UI only. Never use the result in a filesystem path."""
    text = unicodedata.normalize("NFKC", name or "")
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("C"))
    text = text.replace("\\", "/").rsplit("/", 1)[-1].strip()[:MAX_NAME].strip()
    return text or DEFAULT_NAME
