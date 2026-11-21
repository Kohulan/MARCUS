"""v1 claim 8 on v2: attacker-controlled text from an upload never runs as script.

v1: HighlightedText.vue rendered extracted PDF text with `v-html`; the real UI flow ran
`window.__judge_xss_fired = true` from an `<img onerror>` in the PDF.

v2 has two halves:
  * the browser half drives the React UI served by the stack's own nginx (the shipped image,
    with its CSP): upload through the tool's own file input, open the Paper view, wait until
    the payload is on screen as text (the extracted text in the Text column, the file name in
    the header), then check that it never ran. Run with MARCUS_FRONTEND_URL=http://localhost:18090;
  * the API half: the attacker-controlled strings (the upload's filename, kept as
    `display_name`, and the PDF's extracted text) come back only inside JSON served as
    `application/json` (or as a JSON download), with nosniff and `default-src 'none'`, never as
    a document a browser would render.
"""
from __future__ import annotations

import json
import re

from payloads import XSS_MARKER, minimal_png, xss_pdf_bytes

from v2.helpers import API, expect_ok, upload_image, upload_paper, wait_image, wait_paper

# No quotes: httpx (like browsers, per the HTML spec) sends `"` in a multipart filename as %22.
XSS_FILENAME_HTML = f"<img src=x onerror=window.{XSS_MARKER}=true>"
XSS_NAME = f"{XSS_FILENAME_HTML}.pdf"
# The payload as text: in the PDF it is `onerror="window.…"`, in the file name `onerror=window.…`.
PAYLOAD_TEXT = re.compile(rf'onerror="?window\.{XSS_MARKER}')


def test_extracted_text_html_does_not_execute_in_browser(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    from common import target

    pdf = tmp_path / XSS_NAME.replace("/", "_")
    pdf.write_bytes(xss_pdf_bytes())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            # Never count a judge run as a visit.
            page.route("https://matomo.nfdi4chem.de/**", lambda r: r.fulfill(status=204, body=""))
            page.goto(target.frontend_url() + "/app", wait_until="load", timeout=30_000)
            # No OCSR engine is needed for the text: the paper finishes without one.
            auto = page.get_by_role("switch", name="Find structures automatically")
            auto.uncheck()
            expect(auto).not_to_be_checked()
            page.locator("input[type=file]").set_input_files(str(pdf))
            # The tool opens the new paper: this also proves the owner cookie worked.
            page.wait_for_url(re.compile(r"/app/papers/[0-9a-f-]{36}$"), timeout=60_000)
            page.goto(page.url + "?view=paper", wait_until="load", timeout=30_000)
            text = page.get_by_role("region", name="Text")
            expect(text.get_by_text(PAYLOAD_TEXT).first).to_be_visible(timeout=240_000)
            expect(page.get_by_role("heading", level=1, name=XSS_NAME)).to_be_visible()
            fired = page.evaluate(f"() => window.{XSS_MARKER} === true")
        finally:
            browser.close()
    assert not fired, "text from an uploaded PDF executed script in the v2 UI"


def _json_only(name: str, resp, problems: list[str]) -> None:
    ctype = resp.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        problems.append(f"{name}: content-type {ctype!r}")
        return
    try:
        json.loads(resp.content)
    except ValueError:
        problems.append(f"{name}: body is not JSON")
    if resp.headers.get("x-content-type-options", "").lower() != "nosniff":
        problems.append(f"{name}: no nosniff")
    if "default-src 'none'" not in resp.headers.get("content-security-policy", ""):
        problems.append(f"{name}: CSP is not default-src 'none'")


def test_display_name_is_returned_only_as_json(new_owner):
    owner = new_owner()
    pid = upload_paper(owner, filename=XSS_NAME, data=xss_pdf_bytes())
    job = upload_image(owner, filename=f"{XSS_FILENAME_HTML}.png", data=minimal_png(32))
    wait_paper(owner, pid)
    wait_image(owner, job)

    problems: list[str] = []
    carriers = 0
    for name, path in (
        ("GET /papers", f"{API}/papers"),
        ("GET /papers/{id}", f"{API}/papers/{pid}"),
        ("GET /papers/{id}/text", f"{API}/papers/{pid}/text"),
        ("GET /papers/{id}/export (json)", f"{API}/papers/{pid}/export?format=json"),
        ("GET /images/{id}", f"{API}/images/{job}"),
    ):
        resp = expect_ok(owner.get(path), name)
        if XSS_MARKER in resp.text or "onerror" in resp.text:
            carriers += 1
            _json_only(name, resp, problems)
            if "export" in name and "attachment" not in resp.headers.get(
                    "content-disposition", ""):
                problems.append(f"{name}: not served as an attachment")

    detail = owner.get(f"{API}/papers/{pid}").json()
    assert detail["display_name"] == XSS_NAME, detail["display_name"]  # kept as data, as JSON
    assert carriers >= 3, f"the payload should come back in several responses, got {carriers}"
    assert not problems, f"attacker-controlled text served outside JSON: {problems}"
