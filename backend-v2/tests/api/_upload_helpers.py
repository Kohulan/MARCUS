"""Upload helpers shared by the paper and image API tests."""

import io
from itertools import count

from PIL import Image

_files = count(1)


def pdf_bytes(size: int = 2048, tag: int = 0) -> bytes:
    """A minimal PDF of `size` bytes; a `tag` makes it another file (another SHA-256)."""
    head = b"%PDF-1.4\n"
    tail = f"%{tag}".encode() if tag else b""
    return head + b"0" * (size - len(head) - len(tail)) + tail


def fresh_pdf(size: int = 2048) -> bytes:
    """Another file each call: the same file again from the same browser opens its earlier
    paper (owner request 2026-11-26), which is not what a test that counts uploads means."""
    return pdf_bytes(size, tag=next(_files))


async def upload(c, data=None, name="paper.pdf", **form):
    """A new file each call unless `data` is given (fresh_pdf)."""
    data = fresh_pdf() if data is None else data
    return await c.post(
        "/api/v2/papers", files={"file": (name, data, "application/pdf")}, data=form
    )


def image_bytes(fmt: str = "PNG", size=(20, 20), mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, "white").save(buf, fmt)
    return buf.getvalue()


async def upload_image(c, data=None, name="mol.png", **form):
    data = image_bytes() if data is None else data
    return await c.post("/api/v2/images", files={"file": (name, data, "image/png")}, data=form)
