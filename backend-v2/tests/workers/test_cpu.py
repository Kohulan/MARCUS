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


def sleepy_lookup(path):
    time.sleep(30)
    return "10.1000/never"


def sleepy_count(path, max_pages):
    time.sleep(30)


def fixed_lookup(path):
    return " https://doi.org/10.1000/ABC.123 "


def boom_lookup(path):
    raise RuntimeError("network down")


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


def test_hanging_child_is_killed_on_timeout():
    start = time.monotonic()
    with pytest.raises(pdfsafe.ChildTimeout):
        pdfsafe.run_isolated(sleepy_lookup, ("x",), timeout_s=2, mem_mb=None)
    assert time.monotonic() - start < 8


def test_timeout_maps_to_bad_input(monkeypatch):
    monkeypatch.setattr(pdfsafe, "_count", sleepy_count)
    pid = make_paper_with("two_page.pdf")
    with pytest.raises(BadInput, match="timeout"):
        pdfsafe.page_count(pdf_path(pid), timeout_s=2)


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


def test_docling_writes_text_json_atomically(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "_convert_to_dict", lambda path: {"texts": [{"text": "hi"}]})
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    assert json.loads((paper_dir(pid) / "text.json").read_text()) == {"texts": [{"text": "hi"}]}
    assert [p.name for p in paper_dir(pid).iterdir() if p.name.startswith(".")] == []


@pytest.mark.ml
def test_docling_real_conversion():
    pid = make_paper_with("two_page.pdf")
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    data = json.loads((paper_dir(pid) / "text.json").read_text())
    assert "texts" in data


def test_doi_timeout_returns_none(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "_lookup_doi", sleepy_lookup)
    monkeypatch.setattr(cpu, "DOI_TOTAL_S", 2)
    start = time.monotonic()
    assert cpu.doi(view(pid), None) == {"doi": None}
    assert time.monotonic() - start < 10


def test_doi_error_returns_none(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "_lookup_doi", boom_lookup)
    assert cpu.doi(view(pid), None) == {"doi": None}


def test_doi_is_normalised(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "_lookup_doi", fixed_lookup)
    assert cpu.doi(view(pid), None) == {"doi": "10.1000/ABC.123"}


def test_normalise_doi_limits():
    assert cpu.normalise_doi(None) is None
    assert cpu.normalise_doi("  ") is None
    assert cpu.normalise_doi("10." + "1" * 300) is None
    assert cpu.normalise_doi("http://dx.doi.org/10.1/x") == "10.1/x"
