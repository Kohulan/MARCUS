"""Segment worker: Segmenter protocol, DecimerSegmenter, FakeSegmenter, `segment_page` handler.

Importing this module registers the handler (GPU worker images import it). Crops are stored
content-addressed (`storage.segment_crop_path`): the planner creates Segment ids only after
this handler returns, so the crop cannot be named by segment id. Crop arrays and files are RGB
(true colour, what users see); the OCSR handler gives the engines v1's red/blue-swapped pixels
(`marcus.workers.ocsr.handler.v1_engine_input`).
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
from celery.signals import worker_process_init
from PIL import Image, ImageDraw

from marcus.core.enums import StepKind
from marcus.core.settings import fake_enabled
from marcus.core.storage import page_image_path, segment_crop_path, write_atomic
from marcus.workers.runtime import BadInput, preload_on_worker_init, register

log = logging.getLogger(__name__)

Crop = tuple[np.ndarray, tuple[int, int, int, int]]  # image, bbox x0,y0,x1,y1


class Segmenter(Protocol):
    version: str

    def load(self) -> None:
        """Load the model."""

    def segment(self, page_png: Path) -> list[Crop]:
        """The crops of one rendered page."""


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


DECIMER_SEGMENTATION_COMMIT = "d0045d9ef4b29a2a8d865eae55399ba1b14481bf"  # docker/MODEL_PINS.md


class DecimerSegmenter:
    """DECIMER Segmentation (Mask R-CNN, TensorFlow), called exactly as v1's
    `process_single_page`: the 300 DPI page as an RGB uint8 array (v1 passes `pix.samples`;
    the CPU worker saved the same pixels as PNG), `expand=True, return_bboxes=True`.

    The library returns crops as 4-channel arrays in the input's channel order plus alpha
    (every pixel opaque; pixels outside the structure mask are white) and bboxes as
    (y0, x0, y1, x1). Crops are returned here as RGB (alpha dropped, true colour) with
    (x0, y0, x1, y1). Like v1, crops and bboxes are paired by position.

    v1 writes the same RGB crop with `cv2.imwrite`, which takes the array as BGR, so v1's crop
    files have red and blue exchanged and its engines read them that way. v2 stores the true
    colours (owner decision, D4 fix round 2) and swaps only the engine input
    (`marcus.workers.ocsr.handler.v1_engine_input`).
    """

    version = DECIMER_SEGMENTATION_COMMIT

    def __init__(self) -> None:
        self._segment: Callable | None = None

    def load(self) -> None:
        from marcus.workers import gpu

        # Importing decimer_segmentation builds, loads and warms up the model (module level),
        # so the thread caps and the GPU budget must be set first. Weights come from
        # PYSTOW_HOME (baked into the image). The import also runs mrcnn/model.py's
        # configure_gpu(memory_growth=True): skipped while a budget is set (as worker-decimer).
        with gpu.skip_memory_growth(gpu.prepare_tf(), "decimer_segmentation"):
            from decimer_segmentation import segment_chemical_structures

        self._segment = segment_chemical_structures

    def segment(self, page_png: Path) -> list[Crop]:
        if self._segment is None:
            raise RuntimeError("DecimerSegmenter.segment() called before load()")
        with Image.open(page_png) as im:
            page = np.array(im.convert("RGB"), dtype=np.uint8)
        segments, bboxes = self._segment(page, expand=True, return_bboxes=True)
        crops: list[Crop] = []
        for array, (y0, x0, y1, x1) in zip(segments, bboxes):  # paired by position, as v1
            array = np.asarray(array, dtype=np.uint8)
            if array.ndim == 2:
                array = np.stack([array] * 3, axis=-1)
            crops.append(
                (
                    np.ascontiguousarray(array[:, :, :3]),  # true colour; alpha dropped
                    (int(x0), int(y0), int(x1), int(y1)),
                )
            )
        return crops


SEGMENTERS: dict[str, Callable[[], Segmenter]] = {"decimer": DecimerSegmenter}


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
            if name == "fake" and not fake_enabled():
                raise RuntimeError("fake segmenter is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
            factory = SEGMENTERS.get(name)
            if factory is None:
                raise RuntimeError(f"segmenter {name!r} is not available (not registered yet)")
            seg = factory()
            seg.load()
            _segmenter = seg
        return _segmenter


@worker_process_init.connect
def preload_segmenter(**_) -> None:
    """Load the model when a pool process starts (after the fork), not in the first task: the
    load (~32 s on CPU) would otherwise count against segment_page's 60 s soft limit.

    A failed load stops the whole worker with a non-zero exit (SIGQUIT to the parent = Celery
    cold shutdown, exit code 1), so compose restarts it and /ready reports q.segment as
    unserved. A half-ready worker that keeps taking steps it cannot run must not exist.

    Only in a Celery pool process: the signal can also be sent elsewhere (tests send it to
    exercise other workers' hooks), and there the parent is not a Celery worker.
    """
    preload_on_worker_init(_load_segmenter, "segmenter")


def _load_segmenter() -> None:
    log.info("segmenter %s loaded", get_segmenter().version)


def _write_crop(paper_id, array: np.ndarray) -> str:
    import io

    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    data = buf.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    write_atomic(segment_crop_path(paper_id, sha), data)
    return sha


def segment_page(step, session) -> dict:
    page_png = page_image_path(step.paper_id, step.page)
    if not page_png.is_file():
        raise BadInput("page image is missing")
    segmenter = get_segmenter()
    crops = segmenter.segment(page_png)
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
    # seg_version: the planner caches a paper's segmentation only when every page reports the
    # same one (marcus.core.pipeline, seg_cache).
    return {"segments": segments, "seg_version": segmenter.version}


register(StepKind.SEGMENT_PAGE, segment_page)
