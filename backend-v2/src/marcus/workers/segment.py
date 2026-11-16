"""Segment worker: Segmenter protocol, FakeSegmenter and the `segment_page` handler.

Importing this module registers the handler (GPU worker images import it). Crops are stored
content-addressed (`storage.segment_crop_path`): the planner creates Segment ids only after
this handler returns, so the crop cannot be named by segment id. Crop arrays are RGB.
"""

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageDraw

from marcus.core.enums import StepKind
from marcus.core.settings import get_settings
from marcus.core.storage import page_image_path, segment_crop_path
from marcus.workers.runtime import BadInput, register

log = logging.getLogger(__name__)

Crop = tuple[np.ndarray, tuple[int, int, int, int]]  # image, bbox x0,y0,x1,y1


class Segmenter(Protocol):
    version: str

    def load(self) -> None: ...

    def segment(self, page_png: Path) -> list[Crop]: ...


class FakeSegmenter:
    version = "fake-1"

    def __init__(self, per_page: int = 2, delay_s: float = 0.0):
        self.per_page = per_page
        self.delay_s = delay_s

    def load(self) -> None:
        pass

    def segment(self, page_png: Path) -> list[Crop]:
        if self.delay_s:
            time.sleep(self.delay_s)
        with Image.open(page_png) as im:
            width, height = im.size
        n = max(self.per_page, 0)
        crops: list[Crop] = []
        if n == 0:
            return crops
        cell_h = height // n
        w = max(width // 2, 1)
        h = max(min(cell_h, height) // 2, 1)
        for i in range(n):
            x0, y0 = width // 8, i * cell_h + cell_h // 4
            x1, y1 = min(x0 + w, width), min(y0 + h, height)
            if x1 <= x0 or y1 <= y0:
                continue
            img = Image.new("RGB", (x1 - x0, y1 - y0), (255, 255, 255))
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(0, 0, 0))
            d.text((4, 4), f"#{i}", fill=(0, 0, 0))
            for k in range(i + 1):  # i+1 bars make each crop differ from the others
                x = 4 + 6 * k
                d.line([x, 16, x, max(img.height - 4, 17)], fill=(0, 0, 0))
            crops.append((np.asarray(img), (x0, y0, x1, y1)))
        return crops


SEGMENTERS: dict[str, Callable[[], Segmenter]] = {}  # B1 registers "decimer"


def _fake() -> Segmenter:
    return FakeSegmenter(
        per_page=int(os.environ.get("MARCUS_FAKE_SEGMENTS_PER_PAGE", "2")),
        delay_s=float(os.environ.get("MARCUS_FAKE_SEGMENT_DELAY_S", "0")),
    )


SEGMENTERS["fake"] = _fake

_segmenter: Segmenter | None = None
_lock = threading.Lock()


def get_segmenter() -> Segmenter:
    """One segmenter per worker process, created and `load()`ed on first use."""
    global _segmenter
    with _lock:
        if _segmenter is None:
            name = os.environ.get("MARCUS_SEGMENTER", "decimer")
            if name == "fake" and not get_settings().enable_fake_engines:
                raise RuntimeError("fake segmenter is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
            factory = SEGMENTERS.get(name)
            if factory is None:
                raise RuntimeError(f"segmenter {name!r} is not available (not registered yet)")
            seg = factory()
            seg.load()
            _segmenter = seg
        return _segmenter


def _write_crop(paper_id, array: np.ndarray) -> str:
    import io

    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    data = buf.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    dest = segment_crop_path(paper_id, sha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return sha


def segment_page(step, session) -> dict:
    page_png = page_image_path(step.paper_id, step.page)
    if not page_png.is_file():
        raise BadInput("page image is missing")
    crops = get_segmenter().segment(page_png)
    segments = []
    for idx, (array, bbox) in enumerate(crops):
        if array.ndim < 2 or array.shape[0] == 0 or array.shape[1] == 0:
            continue
        segments.append(
            {
                "idx": idx,
                "bbox": [int(v) for v in bbox],
                "image_sha256": _write_crop(step.paper_id, array),
            }
        )
    return {"segments": segments}


register(StepKind.SEGMENT_PAGE, segment_page)
