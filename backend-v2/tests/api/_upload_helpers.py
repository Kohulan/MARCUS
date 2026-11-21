"""Upload helpers shared by the paper and image API tests."""

import io

from PIL import Image


def pdf_bytes(size: int = 2048) -> bytes:
    head = b"%PDF-1.4\n"
    return head + b"0" * (size - len(head))


async def upload(c, data=None, name="paper.pdf", **form):
    data = pdf_bytes() if data is None else data
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
