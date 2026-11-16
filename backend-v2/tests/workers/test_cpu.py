"""CPU worker: isolated PDF handling, docling export, bounded DOI lookup.

Handlers are called directly with a fake Step view; no Celery or database needed.
"""

import json
import shutil
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from marcus.core.storage import page_image_path, paper_dir, pdf_path
from marcus.workers import cpu, pdfsafe
from marcus.workers.runtime import HANDLERS, BadInput

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pdfs"


def make_paper_with(name: str):
    paper_id = uuid.uuid4()
    pdf = pdf_path(paper_id)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / name, pdf)
    return paper_id


def view(paper_id, page=None):
    return SimpleNamespace(paper_id=paper_id, page=page)


def test_handlers_are_registered():
    from marcus.core.enums import StepKind

    for kind in (StepKind.CHECK_PDF, StepKind.RENDER_PAGE, StepKind.DOCLING, StepKind.DOI):
        assert kind in HANDLERS


def test_check_pdf_counts_pages():
    pid = make_paper_with("two_page.pdf")
    assert cpu.check_pdf(view(pid), None) == {"pages": 2}


@pytest.mark.parametrize("name", ["encrypted.pdf", "zero_page.pdf", "png_as.pdf"])
def test_encrypted_zero_page_and_png_pdf_fail_bad_input_fast(name):
    pid = make_paper_with(name)
    start = time.monotonic()
    with pytest.raises(BadInput):
        cpu.check_pdf(view(pid), None)
    assert time.monotonic() - start < 30


def test_too_many_pages_is_bad_input(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCUS_MAX_PAGES", "1")
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    pid = make_paper_with("two_page.pdf")
    with pytest.raises(BadInput, match="more than"):
        cpu.check_pdf(view(pid), None)


@pytest.mark.parametrize("name", ["adversarial_garbage.pdf", "adversarial_xss.pdf"])
def test_adversarial_pdf_times_out_without_hanging_worker(name):
    pid = make_paper_with(name)
    start = time.monotonic()
    try:
        assert pdfsafe.page_count(pdf_path(pid), timeout_s=5) >= 1
    except BadInput:
        pass
    assert time.monotonic() - start < 10


def test_render_page_is_300_dpi():
    pid = make_paper_with("two_page.pdf")
    assert cpu.render_page(view(pid, 1), None) == {}
    png = page_image_path(pid, 1)
    pix = pymupdf.Pixmap(str(png))
    with pymupdf.open(str(pdf_path(pid))) as doc:
        rect = doc[1].rect
    assert pix.width == round(rect.width * 300 / 72)
    assert pix.height == round(rect.height * 300 / 72)
    assert not pix.alpha
    assert [p.name for p in png.parent.iterdir()] == ["0001.png"]


def test_render_failure_leaves_no_partial_file():
    pid = make_paper_with("two_page.pdf")
    with pytest.raises(BadInput):
        cpu.render_page(view(pid, 5), None)
    pages = page_image_path(pid, 0).parent
    assert not pages.exists() or list(pages.iterdir()) == []


def test_docling_goes_through_isolated_child(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    calls = []

    def fake_run_docling(path, out_dir, timeout_s, mem_mb=32768):
        calls.append((path, out_dir, timeout_s, mem_mb))

    monkeypatch.setattr(cpu.pdfsafe, "run_docling", fake_run_docling)
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    assert calls == [(pdf_path(pid), paper_dir(pid), 280, 32768)]


@pytest.mark.ml
def test_docling_real_conversion():
    pid = make_paper_with("two_page.pdf")
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    data = json.loads((paper_dir(pid) / "text.json").read_text())
    assert "texts" in data


def test_doi_timeout_returns_none(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "DOI_OP", "_sleep")
    monkeypatch.setattr(cpu, "DOI_TOTAL_S", 2)
    start = time.monotonic()
    assert cpu.doi(view(pid), None) == {"doi": None}
    assert time.monotonic() - start < 8


def test_doi_error_returns_none(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "DOI_OP", "_fail")
    assert cpu.doi(view(pid), None) == {"doi": None}


def test_doi_is_normalised(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu.pdfsafe, "run_op", lambda *a, **k: " https://doi.org/10.1000/ABC.123 ")
    assert cpu.doi(view(pid), None) == {"doi": "10.1000/ABC.123"}


def test_child_timeouts_are_below_celery_soft_limits():
    from marcus.core.queues import TIME_LIMITS

    assert cpu.CHECK_TIMEOUT_S < TIME_LIMITS["check_pdf"][0]
    assert cpu.RENDER_TIMEOUT_S < TIME_LIMITS["render_page"][0]
    assert cpu.DOCLING_TIMEOUT_S < TIME_LIMITS["docling"][0]
    assert cpu.DOI_TOTAL_S < TIME_LIMITS["doi"][0]


def test_normalise_doi_limits():
    assert cpu.normalise_doi(None) is None
    assert cpu.normalise_doi("  ") is None
    assert cpu.normalise_doi("10." + "1" * 300) is None
    assert cpu.normalise_doi("http://dx.doi.org/10.1/x") == "10.1/x"


GOLD = Path(__file__).resolve().parents[3] / "judges/goldset/data/pdf/PMC6017977.pdf"


@pytest.mark.ml
@pytest.mark.skipif(not GOLD.exists(), reason="goldset PDF not present")
def test_docling_real_multipage_paper_within_cpu_limit():
    pid = uuid.uuid4()
    pdf_path(pid).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(GOLD, pdf_path(pid))
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    assert "texts" in json.loads((paper_dir(pid) / "text.json").read_text())
