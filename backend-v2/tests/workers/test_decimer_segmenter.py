"""DECIMER segmentation on the S1 fixture (synth_015.pdf: 5 pages, 3 structures each).

Runs only in the TF image (needs TensorFlow, decimer_segmentation and the baked weights):

  docker compose -p marcus-v2 run --rm worker-segment pytest -m ml \
      tests/workers/test_decimer_segmenter.py -q

The v1 per-page counts were computed once with v1's offline counting script inside the v1 image
(command and output in tests/fixtures/v1_segment_counts_synth015.json); v1 is never called here.
"""

import json
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from marcus.core.storage import page_image_path, segment_crop_path

pytestmark = pytest.mark.ml

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PDF = FIXTURES / "pdfs" / "synth_015.pdf"
V1 = json.loads((FIXTURES / "v1_segment_counts_synth015.json").read_text())
PINNED_COMMIT = "d0045d9ef4b29a2a8d865eae55399ba1b14481bf"


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    """The fixture rendered by the CPU worker's own render function (300 DPI, alpha=False)."""
    from marcus.workers import pdfsafe

    out_dir = tmp_path_factory.mktemp("pages")
    paths = []
    for p in range(len(V1["per_page"])):
        out = out_dir / f"{p}.png"
        pdfsafe.render_page_png(PDF, p, out, timeout_s=60)
        paths.append(out)
    return paths


@pytest.fixture(scope="module")
def segmenter():
    from marcus.workers.segment import DecimerSegmenter

    seg = DecimerSegmenter()
    seg.load()
    return seg


@pytest.fixture(scope="module")
def results(segmenter, pages):
    return [segmenter.segment(p) for p in pages]


def test_version_is_pinned_commit(segmenter):
    assert segmenter.version == PINNED_COMMIT


def test_segment_count_matches_v1_on_s1_fixture(results):
    per_page = [len(crops) for crops in results]
    assert per_page == V1["per_page"]
    assert sum(per_page) == V1["n_structures"] == 15


def test_crops_are_rgb_uint8_and_bboxes_inside_page(results, pages):
    for crops, page in zip(results, pages, strict=True):
        with Image.open(page) as im:
            width, height = im.size
        for array, (x0, y0, x1, y1) in crops:
            assert array.dtype == np.uint8
            assert array.ndim == 3 and array.shape[2] == 3
            assert 0 <= x0 < x1 <= width
            assert 0 <= y0 < y1 <= height
            # the crop is exactly the bbox region of the page (bbox is x0, y0, x1, y1)
            assert array.shape[:2] == (y1 - y0, x1 - x0)


def test_crop_pixels_come_from_the_rgb_page(results, pages):
    """Channel order: unmasked crop pixels equal the page's RGB pixels (not BGR as in v1's
    cv2.imwrite files). Pixels outside the structure mask are white in both."""
    crops, page = results[0], pages[0]
    rgb = np.asarray(Image.open(page).convert("RGB"))
    array, (x0, y0, x1, y1) = crops[0]
    region = rgb[y0:y1, x0:x1]
    not_white = np.any(array != 255, axis=2)
    assert not_white.any()
    assert np.array_equal(array[not_white], region[not_white])


def test_segment_page_handler_with_default_segmenter(monkeypatch, segmenter, pages):
    """The real handler path: MARCUS_SEGMENTER unset selects "decimer"; bboxes are ints."""
    from marcus.workers import segment
    from tests.workers.helpers import view

    monkeypatch.delenv("MARCUS_SEGMENTER", raising=False)
    monkeypatch.setattr(segment, "_segmenter", None)
    pid = uuid.uuid4()
    dest = page_image_path(pid, 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pages[1].read_bytes())

    out = segment.segment_page(view(pid, page=1), None)

    assert isinstance(segment._segmenter, segment.DecimerSegmenter)
    assert len(out["segments"]) == V1["per_page"][1]
    for s in out["segments"]:
        assert len(s["bbox"]) == 4
        assert all(type(v) is int for v in s["bbox"])
        with Image.open(segment_crop_path(pid, s["image_sha256"])) as crop:
            assert crop.mode == "RGB"
            x0, y0, x1, y1 = s["bbox"]
            assert crop.size == (x1 - x0, y1 - y0)
