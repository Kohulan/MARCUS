"""CPU worker: isolated PDF handling, docling export, bounded DOI lookup.

Handlers are called directly with a fake Step view; no Celery or database needed.
"""

import io
import json
import resource
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
import requests
from requests.adapters import BaseAdapter
from requests.models import Response

from marcus.core.storage import page_image_path, paper_dir, pdf_path
from marcus.workers import cpu, pdfsafe
from marcus.workers.runtime import HANDLERS, BadInput, StepTimeout

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pdfs"
NO_META = {"title": None, "first_author": None, "year": None}


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
    except (BadInput, StepTimeout):
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


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.rolled_back = False

    def execute(self, stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: self.pages)

    def rollback(self):
        self.rolled_back = True


def test_docling_child_timeout_scales_with_pages(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    seen = []
    monkeypatch.setattr(
        cpu.pdfsafe, "run_docling", lambda path, out, timeout_s, mem_mb=0: seen.append(timeout_s)
    )
    session = _FakeSession(100)
    cpu.docling(view(pid), session)
    assert seen == [1260 - 20]  # soft limit for 100 pages minus the margin
    assert session.rolled_back


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
    assert cpu.doi(view(pid), None) == {"doi": None, **NO_META}
    assert time.monotonic() - start < 8


def test_doi_error_returns_none(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu, "DOI_OP", "_fail")
    assert cpu.doi(view(pid), None) == {"doi": None, **NO_META}


def test_doi_is_normalised(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu.pdfsafe, "run_op", lambda *a, **k: " https://doi.org/10.1000/ABC.123 ")
    meta = {"title": "A title", "first_author": "Rajan", "year": 2025}
    monkeypatch.setattr(cpu, "fetch_meta", lambda doi, timeout_s: meta)
    assert cpu.doi(view(pid), None) == {"doi": "10.1000/ABC.123", **meta}


class FakeAdapter(BaseAdapter):
    """Answers by URL prefix: {prefix: (status, body bytes or Exception, headers)}."""

    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.urls = []

    def send(self, request, **kwargs):
        self.urls.append(request.url)
        for prefix, (status, body, headers) in self.routes.items():
            if request.url.startswith(prefix):
                if isinstance(body, Exception):
                    raise body
                resp = Response()
                resp.status_code = status
                resp.headers.update(headers)
                resp.raw = io.BytesIO(body)
                resp.url = request.url
                return resp
        raise AssertionError(request.url)

    def close(self):
        pass


def fake_web(monkeypatch, routes):
    adapter = FakeAdapter(routes)
    real = requests.Session

    def session():
        s = real()
        s.mount("https://", adapter)
        return s

    monkeypatch.setattr(cpu.requests, "Session", session)
    return adapter


def crossref(title, **message):
    return json.dumps({"message": {"title": [title], **message}}).encode()


def datacite(title, **attributes):
    return json.dumps(
        {"data": {"attributes": {"titles": [{"title": title}], **attributes}}}
    ).encode()


def test_fetch_meta_crossref_then_datacite(monkeypatch):
    web = fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (404, b"", {}),
            "https://api.datacite.org/": (200, datacite("From DataCite"), {}),
        },
    )
    assert cpu.fetch_meta("10.1/x", 5)["title"] == "From DataCite"
    assert len(web.urls) == 2


def test_fetch_meta_uses_crossref_first(monkeypatch):
    web = fake_web(monkeypatch, {"https://api.crossref.org/": (200, crossref("Crossref one"), {})})
    assert cpu.fetch_meta("10.1/x", 5)["title"] == "Crossref one"
    assert len(web.urls) == 1


def test_fetch_meta_strips_markup_and_cuts(monkeypatch):
    fake_web(
        monkeypatch,
        {"https://api.crossref.org/": (200, crossref("<i>Coffea</i>  alkaloids &amp; more\n"), {})},
    )
    assert cpu.fetch_meta("10.1/x", 5)["title"] == "Coffea alkaloids & more"
    fake_web(monkeypatch, {"https://api.crossref.org/": (200, crossref("a" * 600), {})})
    assert cpu.fetch_meta("10.1/x", 5)["title"] == "a" * 500
    fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (200, crossref(" <b></b> "), {}),
            "https://api.datacite.org/": (404, b"", {}),
        },
    )
    assert cpu.fetch_meta("10.1/x", 5)["title"] is None


def test_fetch_meta_quotes_doi_in_path(monkeypatch):
    web = fake_web(monkeypatch, {"https://api.crossref.org/": (200, crossref("T"), {})})
    cpu.fetch_meta("10.1/../x?y", 5)
    assert web.urls[0] == "https://api.crossref.org/works/10.1%2F..%2Fx%3Fy"


def test_fetch_meta_redirect_is_none(monkeypatch):
    web = fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (302, b"", {"Location": "https://evil.example/"}),
            "https://api.datacite.org/": (301, b"", {"Location": "https://evil.example/"}),
        },
    )
    assert cpu.fetch_meta("10.1/x", 5) == NO_META
    assert len(web.urls) == 2


def test_fetch_meta_error_is_none(monkeypatch):
    fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (200, requests.ConnectionError("down"), {}),
            "https://api.datacite.org/": (200, b"not json", {}),
        },
    )
    assert cpu.fetch_meta("10.1/x", 5) == NO_META


def test_fetch_meta_oversized_body_is_none(monkeypatch):
    big = crossref("t") + b" " * cpu.TITLE_MAX_BYTES
    fake_web(
        monkeypatch,
        {"https://api.crossref.org/": (200, big, {}), "https://api.datacite.org/": (404, b"", {})},
    )
    assert cpu.fetch_meta("10.1/x", 5) == NO_META


def crossref_meta(monkeypatch, **message):
    fake_web(monkeypatch, {"https://api.crossref.org/": (200, crossref("T", **message), {})})
    return cpu.fetch_meta("10.1/x", 5)


def datacite_meta(monkeypatch, **attributes):
    fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (404, b"", {}),
            "https://api.datacite.org/": (200, datacite("T", **attributes), {}),
        },
    )
    return cpu.fetch_meta("10.1/x", 5)


def test_fetch_meta_crossref_author_and_year(monkeypatch):
    web = fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (
                200,
                crossref(
                    "Coffea",
                    author=[{"given": "Kohulan", "family": "Rajan"}, {"family": "Steinbeck"}],
                    issued={"date-parts": [[2025, 3, 1]]},
                    published={"date-parts": [[2024]]},
                ),
                {},
            )
        },
    )
    assert cpu.fetch_meta("10.1/x", 5) == {"title": "Coffea", "first_author": "Rajan", "year": 2025}
    assert len(web.urls) == 1  # no extra call for the author or year


def test_fetch_meta_crossref_year_falls_back_to_published(monkeypatch):
    assert crossref_meta(monkeypatch, published={"date-parts": [[2019, 5]]})["year"] == 2019
    assert crossref_meta(monkeypatch, issued={"date-parts": [["2017"]]})["year"] == 2017
    assert crossref_meta(monkeypatch, issued={"date-parts": [[None]]},
                         published={"date-parts": [[2018]]})["year"] == 2018  # fmt: skip


def test_fetch_meta_datacite_author_and_year(monkeypatch):
    meta = datacite_meta(
        monkeypatch,
        creators=[{"name": "Rajan, Kohulan", "familyName": "Rajan"}],
        publicationYear=2023,
    )
    assert meta == {"title": "T", "first_author": "Rajan", "year": 2023}
    meta = datacite_meta(monkeypatch, creators=[{"name": "COCONUT team"}], publicationYear="2021")
    assert meta == {"title": "T", "first_author": "COCONUT team", "year": 2021}


def test_fetch_meta_author_is_cleaned_and_cut(monkeypatch):
    odd = crossref_meta(monkeypatch, author=[{"family": " <i>M&uuml;ller</i>\n  Smith "}])
    assert odd["first_author"] == "Müller Smith"
    long = crossref_meta(monkeypatch, author=[{"family": "a" * 300}])["first_author"]
    assert long == "a" * cpu.AUTHOR_MAX_CHARS == "a" * 100


@pytest.mark.parametrize(
    "message",
    [
        {},
        {"author": []},
        {"author": "Rajan"},
        {"author": ["Rajan"]},
        {"author": [{"given": "Kohulan"}]},
        {"author": [{"family": 5}]},
        {"author": [{"family": " <b></b> "}]},
        {"author": [{"name": "A consortium"}]},  # Crossref: the family name only
    ],
)
def test_fetch_meta_odd_crossref_author_is_none(monkeypatch, message):
    meta = crossref_meta(monkeypatch, **message)
    assert meta["title"] == "T" and meta["first_author"] is None


@pytest.mark.parametrize(
    "dates",
    [
        {},
        {"issued": {"date-parts": [[None]]}},
        {"issued": {"date-parts": []}},
        {"issued": {"date-parts": [[]]}},
        {"issued": {"date-parts": "2020"}},
        {"issued": "2020"},
        {"issued": {"date-parts": [["20"]]}},
        {"issued": {"date-parts": [[True]]}},
        {"issued": {"date-parts": [[2020.5]]}},
        {"issued": {"date-parts": [[1799]]}},
        {"issued": {"date-parts": [[datetime.now(UTC).year + 2]]}},
        {"issued": {"date-parts": [[10**30]]}},
    ],
)
def test_fetch_meta_odd_crossref_year_is_none(monkeypatch, dates):
    meta = crossref_meta(monkeypatch, **dates)
    assert meta["title"] == "T" and meta["year"] is None


def test_fetch_meta_year_bounds(monkeypatch):
    assert crossref_meta(monkeypatch, issued={"date-parts": [[1800]]})["year"] == 1800
    next_year = datetime.now(UTC).year + 1
    assert crossref_meta(monkeypatch, issued={"date-parts": [[next_year]]})["year"] == next_year


@pytest.mark.parametrize(
    "attributes",
    [
        {},
        {"creators": []},
        {"creators": {"name": "Rajan"}},
        {"creators": [None]},
        {"creators": [{"givenName": "Kohulan"}], "publicationYear": "20x1"},
        {"creators": [{"familyName": None, "name": 7}], "publicationYear": " 2021 "},
        {"publicationYear": None},
        {"publicationYear": "1600"},
        {"publicationYear": ["2020"]},
        {"publicationYear": "٢٠٢٠"},  # Arabic-Indic digits: not a year here
    ],
)
def test_fetch_meta_odd_datacite_data_is_none(monkeypatch, attributes):
    assert datacite_meta(monkeypatch, **attributes) == {**NO_META, "title": "T"}


def test_fetch_meta_author_and_year_come_with_the_title(monkeypatch):
    """No title in the Crossref reply: its author and year are not kept; DataCite's are."""
    web = fake_web(
        monkeypatch,
        {
            "https://api.crossref.org/": (
                200,
                json.dumps(
                    {
                        "message": {
                            "author": [{"family": "Wrong"}],
                            "issued": {"date-parts": [[2001]]},
                        }
                    }
                ).encode(),
                {},
            ),  # fmt: skip
            "https://api.datacite.org/": (
                200,
                datacite("D", creators=[{"familyName": "Right"}]),
                {},
            ),
        },
    )
    assert cpu.fetch_meta("10.1/x", 5) == {"title": "D", "first_author": "Right", "year": None}
    assert len(web.urls) == 2


def test_doi_step_skips_title_when_budget_spent(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu.pdfsafe, "run_op", lambda *a, **k: "10.1/x")
    monkeypatch.setattr(cpu, "DOI_TOTAL_S", 0.5)
    called = []
    monkeypatch.setattr(cpu, "fetch_meta", lambda *a: called.append(a) or {"title": "T"})
    assert cpu.doi(view(pid), None) == {"doi": "10.1/x", **NO_META}
    assert not called


def test_doi_step_no_title_call_without_doi(monkeypatch):
    pid = make_paper_with("two_page.pdf")
    monkeypatch.setattr(cpu.pdfsafe, "run_op", lambda *a, **k: None)
    monkeypatch.setattr(cpu, "fetch_meta", lambda *a: pytest.fail("called"))
    assert cpu.doi(view(pid), None) == {"doi": None, **NO_META}


def test_child_timeouts_are_below_celery_soft_limits():
    from marcus.core.queues import TIME_LIMITS

    assert cpu.CHECK_TIMEOUT_S < TIME_LIMITS["check_pdf"][0]
    assert cpu.RENDER_TIMEOUT_S < TIME_LIMITS["render_page"][0]
    assert 300 - cpu.DOCLING_MARGIN_S < TIME_LIMITS["docling"][0]
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
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    assert cpu.docling(view(pid), None) == {"text_path": "text.json"}
    wall = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_used = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    limit = (pdfsafe.DOCLING_THREADS + pdfsafe.CPU_HEADROOM_THREADS) * (280 + 5)
    print(f"docling wall {wall:.1f} s, child cpu {cpu_used:.1f} s, cpu limit {limit} s")
    assert cpu_used < 0.8 * limit
    assert "texts" in json.loads((paper_dir(pid) / "text.json").read_text())


def _big_page_paper(width_pt: float, height_pt: float):
    paper_id = uuid.uuid4()
    pdf = pdf_path(paper_id)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.new_page(width=width_pt, height=height_pt)
    doc.save(str(pdf))
    doc.close()
    return paper_id


def test_render_refuses_a_page_above_the_pixel_cap():
    """Review I6: a page is rendered only up to MARCUS_MAX_PAGE_PIXELS (50 MP at 300 DPI); a
    larger one is refused before any pixel is drawn, as final bad_input, and leaves no file."""
    pid = _big_page_paper(3000, 3000)  # 12500 x 12500 px at 300 DPI = 156 MP
    start = time.monotonic()
    with pytest.raises(BadInput, match="page too large to render"):
        cpu.render_page(view(pid, 0), None)
    assert time.monotonic() - start < 15
    pages = page_image_path(pid, 0).parent
    assert not pages.exists() or list(pages.iterdir()) == []


def test_render_pixel_cap_is_a_setting(monkeypatch):
    from marcus.core.settings import get_settings

    pid = _big_page_paper(595, 842)  # A4: 2480 x 3508 px = 8.7 MP
    monkeypatch.setenv("MARCUS_MAX_PAGE_PIXELS", "8000000")
    get_settings.cache_clear()
    with pytest.raises(BadInput, match="page too large to render"):
        cpu.render_page(view(pid, 0), None)
    monkeypatch.setenv("MARCUS_MAX_PAGE_PIXELS", "9000000")
    get_settings.cache_clear()
    assert cpu.render_page(view(pid, 0), None) == {}


def test_render_refuses_a_png_above_the_byte_cap(monkeypatch):
    """Re-review I6: an incompressible page under the pixel cap can still be ~150 MB of PNG.
    Above MARCUS_MAX_PAGE_PNG_BYTES the page fails as final bad_input and nothing is written."""
    from marcus.core.settings import get_settings

    assert get_settings().max_page_png_bytes == 32 * 2**20
    monkeypatch.setenv("MARCUS_MAX_PAGE_PNG_BYTES", "1000")
    get_settings.cache_clear()
    pid = make_paper_with("two_page.pdf")
    with pytest.raises(BadInput, match="page image too large"):
        cpu.render_page(view(pid, 0), None)
    pages = page_image_path(pid, 0).parent
    assert not pages.exists() or list(pages.iterdir()) == []


def test_render_waits_for_disk_space_below_the_floor(monkeypatch):
    """Re-review I6: below the free-space floor (the one uploads use) a render writes nothing
    and fails retryable (engine_error, retried), not final bad_input."""
    from collections import namedtuple

    from marcus.core import storage
    from marcus.core.enums import ErrorClass
    from marcus.core.settings import get_settings
    from marcus.workers.runtime import StorageFull, _classify

    usage = namedtuple("usage", "total used free")
    floor = get_settings().min_free_disk_bytes
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda p: usage(10 * floor, 0, floor - 1))
    pid = make_paper_with("two_page.pdf")
    with pytest.raises(StorageFull) as info:
        cpu.render_page(view(pid, 0), None)
    assert _classify(info.value) == (ErrorClass.ENGINE_ERROR, True)
    assert not page_image_path(pid, 0).exists()
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda p: usage(10 * floor, 0, floor))
    assert cpu.render_page(view(pid, 0), None) == {}
