"""The R-group model's two inputs: the page text near the scaffold and the page image.

Text: a port of MARCUS-training markush-eval/markush_eval.py `page_context` (and `_page`,
`_table_rows`), unchanged. The Docling items of pages P-1..P+1 (P is the scaffold's page,
Docling's 1-based page_no), captions and footnotes first, then tables written as rows, then the
other text, each part whole, cut at MAX_CHARS. The test and training documents were the
Docling documents exactly as MARCUS stores them (`GET /papers/{id}/text`), so nothing had to be
adapted. Standard library only.

Image: the model saw each page rendered at 150 dpi (PyMuPDF), then scaled down to at most
1,300,000 pixels (rg_common.load_image: Lanczos, sides at least 28) and sent as a PNG data URI.
MARCUS keeps its page PNGs at 300 dpi (pipeline.RENDER_DPI, PyMuPDF too), so page_image_uri
computes the size the 150 dpi render would have (half the 300 dpi size, rounded up), applies
the same 1.3 MP cap to that size, and resizes the 300 dpi image to the result in one Lanczos
step. The model gets the pixel size it was trained on (the same as the bake-off's to within one
pixel per side); the pixels come from a sharper source, a difference the resize averages out.

Keep it in step with the training code: a change here changes what the model sees.
"""

from __future__ import annotations

import base64
import io
import math
from pathlib import Path

MAX_CHARS = 16000  # markush_eval.MAX_CHARS
MAX_PIXELS = 1_300_000  # rg_common.MAX_PIXELS
MIN_SIDE = 28  # rg_common.load_image: max(28, ...)
STORED_DPI = 300  # marcus.core.pipeline.RENDER_DPI
MODEL_DPI = 150  # the bake-off's render (bakeoff/code/render_pages.py)


# --- text: markush_eval.page_context -------------------------------------------------------


def _page(item) -> int | None:
    prov = item.get("prov") or []
    return prov[0].get("page_no") if prov else None


def _table_rows(table) -> list[str]:
    cells = (table.get("data") or {}).get("table_cells") or []
    grid: dict[int, dict[int, str]] = {}
    for c in cells:
        r = c.get("start_row_offset_idx", 0)
        col = c.get("start_col_offset_idx", 0)
        grid.setdefault(r, {})[col] = " ".join(str(c.get("text", "")).split())
    return [" | ".join(row[k] for k in sorted(row)) for _, row in sorted(grid.items())]


def page_context(doc: dict, page: int) -> str:
    """The text the model reads for a scaffold on Docling page `page` (1-based)."""
    pages = {page - 1, page, page + 1}
    captions, tables, body = [], [], []
    for t in doc.get("texts", []):
        p = _page(t)
        if p not in pages or t.get("content_layer") == "furniture":
            continue
        text = " ".join(str(t.get("text", "")).split())
        if not text:
            continue
        (captions if t.get("label") in ("caption", "footnote") else body).append((p, text))
    for tb in doc.get("tables", []):
        p = _page(tb)
        if p in pages:
            rows = _table_rows(tb)
            if rows:
                tables.append((p, "TABLE (page %d):\n%s" % (p, "\n".join(rows))))
    parts = [f"CAPTION (page {p}): {s}" for p, s in captions]
    parts += [s for _, s in tables]
    parts += [f"(page {p}) {s}" for p, s in body]
    out, size = [], 0
    for s in parts:
        if size + len(s) + 1 > MAX_CHARS:
            break
        out.append(s)
        size += len(s) + 1
    return "\n".join(out)


# --- image: rg_common.load_image on the 150 dpi size --------------------------------------


def model_size(width: int, height: int) -> tuple[int, int]:
    """The pixel size the model gets for a page stored at STORED_DPI as width x height: the
    150 dpi render's size, capped at MAX_PIXELS as rg_common.load_image does."""
    w = math.ceil(width * MODEL_DPI / STORED_DPI)
    h = math.ceil(height * MODEL_DPI / STORED_DPI)
    if w * h > MAX_PIXELS:
        s = (MAX_PIXELS / (w * h)) ** 0.5
        w, h = max(MIN_SIDE, int(w * s)), max(MIN_SIDE, int(h * s))
    return w, h


def page_image_uri(path: Path) -> str:
    """The page PNG at `path` (300 dpi) as the model's image: RGB, model_size, PNG data URI."""
    from PIL import Image  # the api image has Pillow; imported where the step runs

    with Image.open(path) as src:
        im = src.convert("RGB")
    size = model_size(*im.size)
    if size != im.size:
        im = im.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
