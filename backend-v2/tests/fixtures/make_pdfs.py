"""Generate the small PDF fixtures used by the CPU worker and e2e tests (PyMuPDF only).

Run: python tests/fixtures/make_pdfs.py   (outputs go to tests/fixtures/pdfs/)

The two adversarial files mirror judges/security/payloads.py: `garbage_pdf_bytes()` (a %PDF-
header with no structure) and `xss_pdf_bytes()` (real text carrying an HTML/JS payload),
rebuilt here with PyMuPDF instead of reportlab so the test environment needs no extra package.
"""

from pathlib import Path

import pymupdf

OUT = Path(__file__).parent / "pdfs"
XSS = '<img src=x onerror="window.__judge_xss_fired=true">'
# Same bytes as judges/security/payloads.py garbage_pdf_bytes().
GARBAGE = b"%PDF-1.4\n%judge-security-probe, not a real PDF\n"
ZERO_PAGE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    b"trailer<</Root 1 0 R/Size 3>>\n%%EOF\n"
)
# 1x1 white PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea7d6c0e00000000049"
    "454e44ae426082"
)


def _text_pdf(lines: list[str], pages: int = 1) -> pymupdf.Document:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        for j, line in enumerate(lines):
            page.insert_text((72, 100 + 20 * j), f"{line} (page {i + 1})")
    return doc


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = _text_pdf(["Two page fixture.", "Ethanol CCO."], pages=2)
    doc.save(OUT / "two_page.pdf")
    # e2e fairness: the "big" paper (text only, a few KB; fake engines ignore page content)
    _text_pdf(["Twenty page fixture.", "Benzene c1ccccc1."], pages=20).save(
        OUT / "twenty_page.pdf", garbage=4, deflate=True
    )
    doc = _text_pdf(["Secret."])
    doc.save(
        OUT / "encrypted.pdf",
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    (OUT / "zero_page.pdf").write_bytes(ZERO_PAGE)
    (OUT / "png_as.pdf").write_bytes(PNG)
    (OUT / "adversarial_garbage.pdf").write_bytes(GARBAGE)
    _text_pdf(["Judge security probe.", XSS]).save(OUT / "adversarial_xss.pdf")


if __name__ == "__main__":
    main()
