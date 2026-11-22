"""The page text the R-group model reads for a scaffold: a port of MARCUS-training
markush-eval/markush_eval.py `page_context` (and `_page`, `_table_rows`), unchanged.

The Docling items of pages P-1..P+1 (P is the scaffold's page, Docling's 1-based page_no),
captions and footnotes first, then tables written as rows, then the other text, each part whole,
cut at MAX_CHARS. The test and training documents were the Docling documents exactly as MARCUS
stores them (`GET /papers/{id}/text`), so nothing had to be adapted. Standard library only.
Used by the worker (marcus.workers.rgroups) and by the page label index
(marcus.core.rgroup_labels). Keep it in step with the training code.
"""

from __future__ import annotations

MAX_CHARS = 16000  # markush_eval.MAX_CHARS

# What reading a paper's Docling document, or working through a malformed one, may raise when
# the text cannot be used (too large, not JSON, not a Docling document). FileNotFoundError (no
# text) is an OSError too: catch it first where it means something else.
UNUSABLE_TEXT = (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError)


def read_paper_document(paper_id) -> dict:
    """The paper's Docling document (its text.json, under marcus.core.annotation's size cap).
    FileNotFoundError without one; one of UNUSABLE_TEXT when it cannot be used."""
    from marcus.core import annotation
    from marcus.core.storage import text_path

    doc = annotation.read_document(text_path(paper_id))  # TextTooLarge is a ValueError
    if not isinstance(doc, dict):
        raise ValueError("not a Docling document")
    return doc


def _page(item) -> int | None:
    prov = item.get("prov") or []
    return prov[0].get("page_no") if prov else None


page_of = _page  # the Docling page (1-based) an item is on, None without one


def _table_rows(table) -> list[str]:
    cells = (table.get("data") or {}).get("table_cells") or []
    grid: dict[int, dict[int, str]] = {}
    for c in cells:
        r = c.get("start_row_offset_idx", 0)
        col = c.get("start_col_offset_idx", 0)
        grid.setdefault(r, {})[col] = " ".join(str(c.get("text", "")).split())
    return [" | ".join(row[k] for k in sorted(row)) for _, row in sorted(grid.items())]


def page_context(doc: dict, page: int) -> str:
    """The text the model reads for a scaffold on Docling page `page` (1-based)."""
    pages = {page - 1, page, page + 1}
    captions, tables, body = [], [], []
    for t in doc.get("texts", []):
        p = _page(t)
        if p not in pages or t.get("content_layer") == "furniture":
            continue
        text = " ".join(str(t.get("text", "")).split())
        if not text:
            continue
        (captions if t.get("label") in ("caption", "footnote") else body).append((p, text))
    for tb in doc.get("tables", []):
        p = _page(tb)
        if p in pages:
            rows = _table_rows(tb)
            if rows:
                tables.append((p, "TABLE (page %d):\n%s" % (p, "\n".join(rows))))
    parts = [f"CAPTION (page {p}): {s}" for p, s in captions]
    parts += [s for _, s in tables]
    parts += [f"(page {p}) {s}" for p, s in body]
    out, size = [], 0
    for s in parts:
        if size + len(s) + 1 > MAX_CHARS:
            break
        out.append(s)
        size += len(s) + 1
    return "\n".join(out)
