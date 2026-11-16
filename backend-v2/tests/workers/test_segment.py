import hashlib
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from marcus.core.enums import StepKind
from marcus.core.storage import page_image_path, segment_crop_path
from marcus.workers import segment
from marcus.workers.runtime import HANDLERS
from tests.workers.helpers import view


class StubSegmenter:
    version = "stub-1"

    def __init__(self, crops):
        self.crops = crops
        self.loaded = 0

    def load(self):
        self.loaded += 1

    def segment(self, page_png: Path):
        return self.crops


def make_page(paper_id, page=0, size=(200, 300)):
    path = page_image_path(paper_id, page)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def test_handler_registered():
    assert HANDLERS[StepKind.SEGMENT_PAGE] is segment.segment_page


def test_segment_page_saves_crops_and_returns_bboxes(monkeypatch):
    pid = uuid.uuid4()
    make_page(pid, 2)
    crops = [
        (np.full((20, 30, 3), 10, np.uint8), (5, 6, 35, 26)),
        (np.full((10, 10, 3), 200, np.uint8), (50, 60, 60, 70)),
    ]
    monkeypatch.setattr(segment, "get_segmenter", lambda: StubSegmenter(crops))
    out = segment.segment_page(view(pid, page=2), None)
    assert [s["idx"] for s in out["segments"]] == [0, 1]
    assert out["segments"][0]["bbox"] == [5, 6, 35, 26]
    for s in out["segments"]:
        p = segment_crop_path(pid, s["image_sha256"])
        assert hashlib.sha256(p.read_bytes()).hexdigest() == s["image_sha256"]
        assert not list(p.parent.glob("*.tmp"))


def test_zero_width_crop_is_skipped(monkeypatch):
    pid = uuid.uuid4()
    make_page(pid)
    crops = [
        (np.zeros((10, 0, 3), np.uint8), (1, 1, 1, 11)),
        (np.full((10, 10, 3), 90, np.uint8), (1, 1, 11, 11)),
    ]
    monkeypatch.setattr(segment, "get_segmenter", lambda: StubSegmenter(crops))
    out = segment.segment_page(view(pid, page=0), None)
    assert len(out["segments"]) == 1
    assert out["segments"][0]["bbox"] == [1, 1, 11, 11]


def test_fake_segmenter_distinct_crops_inside_page(monkeypatch):
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    monkeypatch.setenv("MARCUS_SEGMENTER", "fake")
    monkeypatch.setenv("MARCUS_FAKE_SEGMENTS_PER_PAGE", "4")
    monkeypatch.setattr(segment, "_segmenter", None)
    pid = uuid.uuid4()
    make_page(pid, 0, size=(400, 500))
    out = segment.segment_page(view(pid, page=0), None)
    assert len(out["segments"]) == 4
    assert len({s["image_sha256"] for s in out["segments"]}) == 4
    for s in out["segments"]:
        x0, y0, x1, y1 = s["bbox"]
        assert 0 <= x0 < x1 <= 400 and 0 <= y0 < y1 <= 500
    monkeypatch.setattr(segment, "_segmenter", None)


def test_fake_segmenter_refused_without_fake_engines(monkeypatch):
    monkeypatch.setenv("MARCUS_SEGMENTER", "fake")
    monkeypatch.setattr(segment, "_segmenter", None)
    with pytest.raises(RuntimeError):
        segment.get_segmenter()


def test_decimer_segmenter_not_yet_registered(monkeypatch):
    monkeypatch.delenv("MARCUS_SEGMENTER", raising=False)
    monkeypatch.setattr(segment, "_segmenter", None)
    monkeypatch.setattr(segment, "SEGMENTERS", {"fake": segment.SEGMENTERS["fake"]})
    with pytest.raises(RuntimeError, match="decimer"):
        segment.get_segmenter()


def test_segmenter_loaded_once(monkeypatch):
    stub = StubSegmenter([])
    monkeypatch.setattr(segment, "_segmenter", None)
    monkeypatch.setattr(segment, "SEGMENTERS", {"decimer": lambda: stub})
    monkeypatch.delenv("MARCUS_SEGMENTER", raising=False)
    assert segment.get_segmenter() is segment.get_segmenter()
    assert stub.loaded == 1
    monkeypatch.setattr(segment, "_segmenter", None)


def test_crop_path_validates_sha():
    with pytest.raises(ValueError):
        segment_crop_path(uuid.uuid4(), "../etc/passwd")
    with pytest.raises(ValueError):
        segment_crop_path(uuid.uuid4(), "A" * 64)
