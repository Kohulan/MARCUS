import hashlib
import os
import signal
import subprocess
import sys
import types
import uuid
import weakref
from pathlib import Path

import numpy as np
import pytest
from celery.signals import worker_process_init
from PIL import Image

from marcus.core.enums import StepKind
from marcus.core.settings import get_settings
from marcus.core.storage import page_image_path, segment_crop_path
from marcus.workers import gpu, segment
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


# --- DecimerSegmenter with a stub decimer_segmentation module (the real one is ml-marked) ---


def _stub_decimer(monkeypatch, segments, bboxes, calls):
    def segment_chemical_structures(image, expand=False, return_bboxes=False):
        calls.append({"image": image, "expand": expand, "return_bboxes": return_bboxes})
        return segments, bboxes

    mod = types.ModuleType("decimer_segmentation")
    mod.segment_chemical_structures = segment_chemical_structures
    monkeypatch.setitem(sys.modules, "decimer_segmentation", mod)


def test_decimer_registered_without_importing_tensorflow():
    assert segment.SEGMENTERS["decimer"] is segment.DecimerSegmenter
    assert segment.DecimerSegmenter.version == "d0045d9ef4b29a2a8d865eae55399ba1b14481bf"
    # a fresh interpreter: importing the handler module must not load the model stack
    code = (
        "import sys, marcus.workers.segment; "
        "assert 'tensorflow' not in sys.modules and 'decimer_segmentation' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_decimer_load_limits_threads_and_gpu_before_model_import(monkeypatch):
    """Importing decimer_segmentation builds the model, so TF's thread caps and GPU budget
    must be set first."""
    calls = []

    def fake_threads(intra, inter):
        assert "decimer_segmentation" not in sys.modules  # model not imported yet
        calls.append(("threads", intra, inter))

    def fake_limit(mb):
        assert "decimer_segmentation" not in sys.modules
        calls.append(("gpu", mb))
        _stub_decimer(monkeypatch, [], [], [])  # the "import" can only succeed after this

    monkeypatch.setenv("MARCUS_GPU_MEM_MB", "3072")
    monkeypatch.setenv("MARCUS_TF_INTRA_THREADS", "4")
    monkeypatch.setenv("MARCUS_TF_INTER_THREADS", "2")
    get_settings.cache_clear()
    monkeypatch.delitem(sys.modules, "decimer_segmentation", raising=False)
    monkeypatch.setattr(gpu, "limit_tf_threads", fake_threads)
    monkeypatch.setattr(gpu, "limit_tf_memory", fake_limit)
    seg = segment.DecimerSegmenter()
    seg.load()
    assert calls == [("threads", 4, 2), ("gpu", 3072)]


def test_decimer_segment_converts_bbox_and_channels(monkeypatch):
    pid = uuid.uuid4()
    page = make_page(pid, 0, size=(40, 30))
    Image.new("RGB", (40, 30), (10, 20, 30)).save(page)
    rgba = np.zeros((5, 7, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3] = 10, 20, 30, 255
    calls = []
    # the library returns (y0, x0, y1, x1) with numpy ints
    _stub_decimer(
        monkeypatch, [rgba], [(np.int64(3), np.int64(2), np.int64(8), np.int64(9))], calls
    )
    # thread caps default to 4/2 (settings): no TensorFlow here to apply them to
    monkeypatch.setattr(gpu, "limit_tf_threads", lambda intra, inter: None)
    seg = segment.DecimerSegmenter()
    seg.load()
    crops = seg.segment(page)

    (call,) = calls
    assert call["expand"] is True and call["return_bboxes"] is True
    img = call["image"]
    assert img.dtype == np.uint8 and img.shape == (30, 40, 3)
    assert tuple(img[0, 0]) == (10, 20, 30)  # RGB, as v1's pix.samples
    ((array, bbox),) = crops
    assert bbox == (2, 3, 9, 8)  # x0, y0, x1, y1
    assert array.dtype == np.uint8 and array.shape == (5, 7, 3)
    assert tuple(array[0, 0]) == (10, 20, 30)


def test_decimer_segment_before_load_fails():
    with pytest.raises(RuntimeError, match="load"):
        segment.DecimerSegmenter().segment(Path("/nonexistent.png"))


# --- model preload at pool process start ----------------------------------------------------


def _connected(signal, func) -> bool:
    for _, ref in signal.receivers:
        target = ref() if isinstance(ref, weakref.ReferenceType) else ref
        if target is func:
            return True
    return False


def test_preload_hook_connected_to_worker_process_init():
    assert _connected(worker_process_init, segment.preload_segmenter)


def test_preload_loads_the_segmenter(monkeypatch):
    monkeypatch.setattr(segment, "_in_pool_process", lambda: True)
    stub = StubSegmenter([])
    aborted = []
    monkeypatch.setattr(segment, "_segmenter", None)
    monkeypatch.setattr(segment, "SEGMENTERS", {"decimer": lambda: stub})
    monkeypatch.delenv("MARCUS_SEGMENTER", raising=False)
    monkeypatch.setattr(segment, "_abort_worker", lambda: aborted.append(True))
    segment.preload_segmenter(sender=None)
    assert stub.loaded == 1 and segment._segmenter is stub and not aborted
    segment.get_segmenter()  # later tasks reuse it: no second load
    assert stub.loaded == 1
    monkeypatch.setattr(segment, "_segmenter", None)


def test_preload_failure_stops_the_worker(monkeypatch):
    monkeypatch.setattr(segment, "_in_pool_process", lambda: True)
    aborted = []

    def broken():
        raise OSError("weights missing")

    monkeypatch.setattr(segment, "get_segmenter", broken)
    monkeypatch.setattr(segment, "_abort_worker", lambda: aborted.append(True))
    segment.preload_segmenter(sender=None)
    assert aborted == [True]


def test_preload_does_nothing_outside_a_pool_process(monkeypatch):
    """Sending worker_process_init in a plain process (as other tests do) must neither load a
    model nor signal the parent."""
    called = []
    monkeypatch.setattr(segment, "get_segmenter", lambda: called.append("load"))
    monkeypatch.setattr(segment, "_abort_worker", lambda: called.append("abort"))
    assert segment._in_pool_process() is False  # pytest runs in billiard's MainProcess
    segment.preload_segmenter(sender=None)
    assert called == []


def test_abort_worker_cold_stops_parent_and_exits_nonzero(monkeypatch):
    killed, exits = [], []

    def fake_exit(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(segment.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(segment.os, "_exit", fake_exit)
    with pytest.raises(SystemExit):
        segment._abort_worker()
    assert killed == [(os.getppid(), signal.SIGQUIT)]
    assert exits == [1]
