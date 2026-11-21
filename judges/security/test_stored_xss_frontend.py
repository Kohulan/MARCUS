"""Claim 8: frontend/src/components/text-extraction/HighlightedText.vue
renders extracted PDF text with `v-html` and no escaping:

    <div v-html="highlightedText"></div>

`highlightedText` is built from the `text` prop (the PDF's extracted text,
verbatim) with `formatPlainText`, which only wraps paragraphs/`<br>`s -- it
never escapes `<`, `>` or `"`. (frontend/src/components/text-extraction/
HighlightedText.vue, template + `formatPlainText`.)

This test drives the REAL UI at the frontend origin (:18080), end to end:
upload a PDF -> click "Extract Text" -> the extracted text (containing an
HTML/JS payload) is rendered via that v-html sink -> the payload's
`onerror` handler runs and sets `window.__judge_xss_fired`, proving script
executed in the app's own origin, not just that the raw string is present
in the DOM.

The full UI flow *is* reachable on this copy (confirmed live), so no
fallback is needed.

The PDF is kept to a handful of words on purpose: extract_pdf_text
(backend/app/routers/docling_conversion.py:137-173) always runs the PDF
through docling first, but docling's own document-to-text path happens to
HTML-escape `<`/`>` -- if that first pass yields ten words or fewer, the
handler re-extracts with pypdf's raw `page.extract_text()` instead, which
does not escape anything. Either escaping behavior is an implementation
detail of extraction, not a sanitizer the component can rely on, and the
component must not trust it either way.

Safe behaviour under test: after the real extract-and-render flow, no
script from the extracted text has run in the page.
"""
from __future__ import annotations

import pytest

from payloads import XSS_MARKER, xss_pdf_bytes

# Deliberately a plain import, not pytest.importorskip: per the judges'
# design rule a test must never pass by skipping, so a missing playwright
# install must ERROR this test (collection failure), not skip it. Install
# with `uv add playwright && uv run playwright install chromium` (already
# done for this judge -- see README.md).
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture
def pdf_on_disk(tmp_path):
    p = tmp_path / "judge_xss_probe.pdf"
    p.write_bytes(xss_pdf_bytes())
    return p


def test_extracted_text_html_does_not_execute_in_browser(frontend, pdf_on_disk, fs_probe):
    """FAILS on v1: uploading a PDF whose text contains
    `<img src=x onerror="window.__judge_xss_fired=true">` and clicking
    "Extract Text" causes that handler to run in the page, because
    HighlightedText.vue injects the extracted text with `v-html`."""
    fired = None
    rendered_html = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(frontend, wait_until="load", timeout=30_000)

            file_input = page.locator("input[type=file]")
            file_input.wait_for(state="attached", timeout=15_000)
            file_input.set_input_files(str(pdf_on_disk))

            page.get_by_role("button", name="Upload Document").click()

            extract_button = page.get_by_role(
                "button", name="Extract Text", exact=False
            )
            extract_button.wait_for(timeout=30_000)
            extract_button.click()

            # The local CPU backend is slow on first use (docling layout
            # models, no GPU) -- give it room rather than flake.
            try:
                page.wait_for_function(
                    f"() => window.{XSS_MARKER} === true", timeout=180_000
                )
            except Exception:
                pass  # handled by the assertion below either way

            fired = page.evaluate(f"() => window.{XSS_MARKER} === true")
            text_display = page.locator(".text-display")
            if text_display.count():
                rendered_html = text_display.inner_html()
        finally:
            browser.close()

    # Clean up the PDF the real upload flow wrote to PDF_DIR under its
    # original filename (extract_text does not rename uploads).
    fs_probe.remove("/app/uploads/pdfs/judge_xss_probe.pdf")

    assert not fired, (
        "Extracted PDF text executed script in the page via v-html: "
        f"window.{XSS_MARKER} was set to True after the real "
        f"upload -> Extract Text flow. Rendered markup: {rendered_html!r}"
    )
