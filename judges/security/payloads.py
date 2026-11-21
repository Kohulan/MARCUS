"""Payload / fixture-file generators for the security judge.

Nothing here talks to the network; it only builds bytes (PDFs, images) that
the tests then send to the target.
"""
from __future__ import annotations

import io
import struct
import zlib

from reportlab.pdfgen import canvas


def minimal_pdf(lines: list[str], *, pagesize=(612, 792)) -> bytes:
    """A real, parseable one-page PDF whose page draws `lines` as text.

    Using reportlab (not a hand-rolled PDF) means the text is drawn as real
    glyphs, so any downstream text extractor (docling, pypdf, pdftotext)
    will recover the literal characters, `<`/`>` included, exactly as any
    other text in a real paper would come through.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=pagesize)
    y = pagesize[1] - 92
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def garbage_pdf_bytes() -> bytes:
    """Bytes with a %PDF- magic header but not a real PDF structure.

    Used for upload endpoints that only check the filename/extension, to
    prove a write-outside-the-upload-folder happens before (or regardless
    of) any real PDF parsing.
    """
    return b"%PDF-1.4\n%judge-security-probe, not a real PDF\n"


def minimal_png(size: int = 1) -> bytes:
    """A tiny valid PNG (size x size, white), real enough to pass content-type
    sniffing / magic-number checks."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * size for _ in range(size))
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# A short HTML payload with a globally observable side effect (sets a flag
# on `window`), used to prove a v-html sink actually *executes* script in
# the page, rather than merely containing the literal string unescaped.
XSS_MARKER = "__judge_xss_fired"
XSS_PAYLOAD_HTML = f'<img src=x onerror="window.{XSS_MARKER}=true">'


def xss_pdf_bytes() -> bytes:
    """A PDF whose extracted text contains an unescaped HTML/JS payload.

    Kept to a handful of words so the backend's own "too little text, fall
    back to raw page text" path (see extract_pdf_text in
    docling_conversion.py) is also exercised, not just the docling layout
    path -- either way the payload characters must survive unescaped.
    """
    return minimal_pdf(
        [
            "Judge security probe.",
            XSS_PAYLOAD_HTML,
        ]
    )
