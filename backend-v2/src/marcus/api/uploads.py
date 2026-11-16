"""Upload helpers: bounded reads, type sniffing, display-name sanitising."""

import io
import unicodedata

import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

CHUNK = 1024 * 1024
DEFAULT_NAME = "upload.pdf"
MAX_NAME = 200
MAX_IMAGE_SIDE = 10_000
MAX_IMAGE_PIXELS = 50_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS  # Pillow warns above this, raises above twice this

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"II*\x00", "TIFF"),
    (b"MM\x00*", "TIFF"),
)


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


def _magic_ok(data: bytes) -> bool:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return any(data.startswith(m) for m, _ in _MAGIC)


def sniff_image(data: bytes) -> str:
    """Return the detected format (PNG, JPEG, TIFF, WEBP) of a safe-to-decode image.

    415 for anything that is not one of those or does not decode, 413 above 10 000 px per
    side or 50 megapixels (including decompression bombs).
    """
    if not _magic_ok(data):
        raise HTTPException(status_code=415, detail="Not a supported image file")
    too_big = HTTPException(status_code=413, detail="Image too large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            fmt = img.format or ""
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise too_big from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError):
        raise HTTPException(status_code=415, detail="Not a supported image file") from None
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        raise too_big
    if fmt not in {"PNG", "JPEG", "TIFF", "WEBP"}:
        raise HTTPException(status_code=415, detail="Not a supported image file")
    return fmt


def _to_8bit(img: Image.Image) -> Image.Image:
    """Scale 16/32-bit grayscale to 8-bit by its real range (convert("RGB") would clip)."""
    arr = np.asarray(img).astype(np.int64)
    if arr.size and (arr.min() < 0 or arr.max() > 65535):
        lo, hi = int(arr.min()), int(arr.max())
        scaled = (arr - lo) * 255 // max(hi - lo, 1)
    else:
        scaled = arr // 256
    return Image.fromarray(scaled.clip(0, 255).astype(np.uint8), "L")


def normalize_to_png(data: bytes) -> bytes:
    """Decode, apply EXIF orientation, flatten to RGB on white, and re-encode as plain PNG.

    Drops all metadata. Call only after sniff_image accepted `data`.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode == "I" or img.mode.startswith("I;16"):
                img = _to_8bit(img)
            if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
                rgba = img.convert("RGBA")
                flat = Image.new("RGB", rgba.size, "white")
                flat.paste(rgba, mask=rgba.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, "PNG")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=413, detail="Image too large") from None
    except (OSError, SyntaxError, ValueError, EOFError):
        raise HTTPException(status_code=415, detail="Not a supported image file") from None
    return out.getvalue()


def sanitize_display_name(name: str | None) -> str:
    """Label for the UI only. Never use the result in a filesystem path."""
    text = unicodedata.normalize("NFKC", name or "")
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("C"))
    text = text.replace("\\", "/").rsplit("/", 1)[-1].strip()[:MAX_NAME].strip()
    return text or DEFAULT_NAME
