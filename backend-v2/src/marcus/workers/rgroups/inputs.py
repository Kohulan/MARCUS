"""The R-group model's two inputs: the page text near the scaffold and the page image.

Text: marcus.core.page_text.page_context (a port of markush_eval's, unchanged).

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

MAX_PIXELS = 1_300_000  # rg_common.MAX_PIXELS
MIN_SIDE = 28  # rg_common.load_image: max(28, ...)
STORED_DPI = 300  # marcus.core.pipeline.RENDER_DPI
MODEL_DPI = 150  # the bake-off's render (bakeoff/code/render_pages.py)


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
