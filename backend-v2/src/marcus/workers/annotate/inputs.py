"""The model input: title + abstract + introduction of a paper's Docling document.

A port of the training input builder (MARCUS-training corpus/scripts/build_inputs.py, `build`,
the format the model was trained on), unchanged but for the corpus-only parts:

    {title}\tABSTRACT: {abstract}\tINTRODUCTION: {introduction}

A part that is not found is left out with its marker; with neither an abstract nor an
introduction, the opening body paragraphs follow the title, tab-separated. At most MAX_CHARS
characters, cut at paragraph, then sentence boundaries. Then every e-mail address is removed
(owner ruling 7, applied to every training text: corpus/harmonise/build.py `scrub_emails`).

Standard library only. Keep it in step with the training builder: a change here changes what
the model sees.
"""

from __future__ import annotations

import re
import unicodedata

MAX_CHARS = 6500
ABSTRACT_MAX = 3200
KEEP_LABELS = {"title", "section_header", "text", "paragraph", "list_item"}

HEAD_ABSTRACT = re.compile(r"^\W*(abstract|summary|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)\W*$", re.I)
INLINE_ABSTRACT = re.compile(r"^\W*(abstract|summary)\s*[:.\-\u2014\u2013]\s*", re.I)
HEAD_INTRO = re.compile(r"^\W*((\d+|[IVX]+)[.)]?\s*)?(introduction|background|introducton)\b", re.I)
KEYWORDS = re.compile(r"^\W*(key\s*words?|keywords|index terms)\b", re.I)
NON_TITLE_HEAD = re.compile(
    r"^\W*(abstract|summary|introduction|access|article|letter|note|review|communication|"
    r"keywords?|contents|research article|original article|open access|full paper|"
    r"supporting information|cite this|graphical abstract|highlights)\W*$",
    re.I,
)
FURNITURE = re.compile(
    r"(doi\.org|^doi\s*:|\bdoi:\s*10\.|https?://|www\.|pubs\.acs\.org|^rece[iv]ved[:\s]|"
    r"^accepted[:\s]|^published|^revised|^cite this|^read online|^access\b|metrics\s*&\s*more|"
    r"article recommendations|supporting information|^downloaded (via|from)|licensed under|"
    r"copyright|\u00a9|all rights reserved|^journal of\b|^open access$|^article$|^note$|"
    r"check for updates|@\s?[a-z0-9-]+\.\s?[a-z]|^e-?mail|corresponding author|to whom correspondence|"
    r"^tel[:./]|^fax[:.]|^special issue|^this article is|creative commons|^citation:|"
    r"^academic editor|^publisher'?s note|^received date|^available online|"
    r"\bvol\.\s*\d+|\b(19|20)\d\d,\s*\d+,\s*\d+|^[\u2020\u2021\u00a7\u22a5\u2016|#\u00b6*]\s*\S)",
    re.I,
)
CAPTION = re.compile(r"^\W*(chart|table|figure|fig\.|scheme|graphical abstract)\s*\d*\b", re.I)
MAJOR_SECTION = re.compile(
    r"^\W*((\d+|[IVX]+)[.)]?\s*)?(results?( and discussion)?|discussion|experimental( section| procedures?)?|"
    r"materials? and methods|methods|conclusions?|references|acknowledge?ments?|"
    r"general experimental procedures|plant material|associated content|author information)\W*$",
    re.I,
)
AFFIL = re.compile(
    r"\b(university|universit[a\u00e4]t|universit[a\u00e0]|institute|department|college|laboratory|"
    r"laboratories|academy|school of|faculty|hospital|centre|center for|key lab|ministry|gmbh|inc\.)",
    re.I,
)
VERBISH = re.compile(
    r"\b(we|was|were|is|are|has|have|been|showed|isolated|exhibited|using)\b", re.I
)
FUNCTION_END = re.compile(r"\b(with|of|from|and|the|in|on|for|by|to|a|an|its|their)$", re.I)
SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


def clean(t: str) -> str:
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("\u00ad", "")  # soft hyphen
    t = re.sub(r"[ \t\r\n\f\v]+", " ", t)
    return t.strip()


def linearize(d: dict) -> list[dict]:
    """Body items in Docling reading order: {label, text, page}."""
    out: list[dict] = []
    seen: set[str] = set()

    def resolve(ref: str):
        _, kind, idx = ref.split("/")
        return kind, d[kind][int(idx)]

    def walk(node):
        for child in node.get("children", []):
            ref = child["$ref"]
            if ref in seen:
                continue
            seen.add(ref)
            kind, item = resolve(ref)
            if kind == "texts":
                page = item["prov"][0]["page_no"] if item.get("prov") else None
                out.append(
                    {"label": item.get("label"), "text": clean(item.get("text", "")), "page": page}
                )
                walk(item)  # list items / inline groups may nest
            elif kind == "groups":
                walk(item)
            # pictures / tables: skipped; their child texts are figure-internal

    walk(d.get("body", {}))
    return out


def letters_ratio(t: str) -> float:
    return sum(c.isalpha() for c in t) / max(1, len(t))


def words(t: str) -> int:
    return len(t.split())


def is_furniture(t: str) -> bool:
    if len(t) < 3 or letters_ratio(t) < 0.5:
        return True
    if FURNITURE.search(t) and len(t) < 400:
        return True
    return False


def is_author_or_affil(t: str) -> bool:
    if len(t) > 2500:
        return False
    n_aff = len(AFFIL.findall(t))
    if n_aff and not VERBISH.search(t) and (len(t) < 500 or n_aff >= 2):
        return True
    w = t.split()
    if 2 <= len(w) <= 120 and not VERBISH.search(t) and not re.search(r"\b(the|of the)\b", t):
        caps = sum(x[:1].isupper() for x in w)
        if caps / len(w) > 0.6 and ("," in t or " and " in t or "*" in t):
            return True
    return False


def is_boundary(it: dict) -> bool:
    """A real section boundary: a heading that is not page furniture, a caption or an author line,
    or a short text item that names a major section (old PDFs label those as text)."""
    t = it["text"]
    if it["label"] in ("section_header", "title"):
        return not (is_furniture(t) or CAPTION.match(t) or is_author_or_affil(t))
    return words(t) <= 8 and bool(
        MAJOR_SECTION.match(t) or HEAD_ABSTRACT.match(t) or HEAD_INTRO.match(t)
    )


def pick_title(items: list[dict]) -> tuple[str, int | None, str]:
    p1 = [(i, it) for i, it in enumerate(items[:80]) if (it["page"] or 1) <= 1]
    for i, it in p1:
        if it["label"] == "title" and words(it["text"]) >= 3 and not is_furniture(it["text"]):
            return it["text"], i, "title_label"
    for i, it in p1:
        t = it["text"]
        if it["label"] not in ("section_header", "text", "paragraph"):
            continue
        if not 3 <= words(t) <= 60 or is_furniture(t) or is_author_or_affil(t) or CAPTION.match(t):
            continue
        if words(t) <= 5 and re.search(r"\b(journal|letters|chemistry|products)\b", t, re.I):
            continue  # journal masthead
        if (
            NON_TITLE_HEAD.match(t)
            or HEAD_ABSTRACT.match(t)
            or HEAD_INTRO.match(t)
            or MAJOR_SECTION.match(t)
        ):
            continue
        if it["label"] != "section_header" and (t.endswith(".") or words(t) > 40):
            continue  # a sentence, not a title
        end = i
        # a title split over two items ("... Leaves with" + "Anti-inflammatory Activity")
        if FUNCTION_END.search(t) and i + 1 < len(items):
            nxt = items[i + 1]["text"]
            if words(nxt) <= 20 and not is_furniture(nxt) and not is_author_or_affil(nxt):
                t, end = f"{t} {nxt}", i + 1
        return (
            t,
            end,
            "first_title_like_item" if it["label"] != "section_header" else "first_section_header",
        )
    return "", None, "no_title"


def sentence_cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    out = ""
    for s in SENT_END.split(text):
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out or text[:limit].rsplit(" ", 1)[0]


def build(d: dict) -> dict:
    items = [it for it in linearize(d) if it["label"] in KEEP_LABELS and it["text"]]
    notes: list[str] = []
    title, ti, how = pick_title(items)
    notes.append(f"title:{how}")
    body = items[(ti + 1) if ti is not None else 0 :]
    bound = [is_boundary(it) for it in body]

    def next_boundary(j: int) -> int:
        for k in range(j, len(body)):
            if bound[k]:
                return k
        return len(body)

    def prose(t: str) -> bool:
        return not (
            is_furniture(t) or KEYWORDS.match(t) or CAPTION.match(t) or is_author_or_affil(t)
        )

    def texts(a: int, b: int) -> list[str]:
        return [
            it["text"]
            for k, it in enumerate(body[a:b], a)
            if not bound[k] and it["label"] not in ("section_header", "title") and prose(it["text"])
        ]

    # ---- abstract
    abstract, a_end = "", None
    for j, it in enumerate(body):
        t = it["text"]
        if bound[j] and HEAD_ABSTRACT.match(t):
            end = next_boundary(j + 1)
            parts = texts(j + 1, end)
            if not parts:  # heading, then furniture/headers, then the text
                for k in range(j + 1, min(len(body), j + 40)):
                    if words(body[k]["text"]) >= 40 and prose(body[k]["text"]):
                        end = next_boundary(k + 1)
                        parts = texts(k, end)
                        break
            if parts:
                abstract, a_end = " ".join(parts), end
                notes.append("abstract:header")
            break
        if INLINE_ABSTRACT.match(t) and words(t) > 15:
            parts = [INLINE_ABSTRACT.sub("", t, count=1)]
            k = j + 1
            # a graphical abstract can split the abstract; take lower-case continuations
            while (
                k < len(body)
                and body[k]["label"] in ("text", "paragraph")
                and body[k]["text"][:1].islower()
                and words(body[k]["text"]) > 5
            ):
                parts.append(body[k]["text"])
                k += 1
            abstract, a_end = " ".join(parts), k
            notes.append("abstract:inline_label")
            break
    if not abstract:
        # unlabelled: first long prose paragraph on pages 1-2 before the first real section
        stop = next_boundary(0)
        for j, it in enumerate(body[:stop]):
            t = it["text"]
            if (it["page"] or 1) <= 2 and words(t) >= 60 and prose(t):
                abstract, a_end = t, j + 1
                notes.append("abstract:unlabelled_first_long_paragraph")
                break
    if not abstract:
        notes.append("abstract:none")
    abstract = sentence_cut(abstract, ABSTRACT_MAX)

    # ---- introduction
    intro_parts: list[str] = []
    for j, it in enumerate(body):
        if bound[j] and HEAD_INTRO.match(it["text"]):
            intro_parts = texts(j + 1, next_boundary(j + 1))
            if intro_parts:
                notes.append("intro:header")
            break
    if not intro_parts and a_end is not None and a_end < len(body) and not bound[a_end]:
        # JNP style: the introduction has no heading and runs to the next section heading
        intro_parts = texts(a_end, next_boundary(a_end))
        if intro_parts:
            notes.append("intro:implicit_after_abstract")
    fallback: list[str] = []
    if not intro_parts:
        notes.append("intro:none")
        if not abstract:
            fallback = texts(0, len(body))
            if fallback:
                notes.append("fallback:opening_body_text")

    # ---- compose within MAX_CHARS
    segs = [title]
    if abstract:
        segs.append(f"ABSTRACT: {abstract}")
    intro = ""
    if intro_parts:
        used = len("\t".join(segs)) + len("\tINTRODUCTION: ")
        for p in intro_parts:
            room = MAX_CHARS - used - len(intro) - 1
            if room <= 50:
                notes.append("truncated")
                break
            if len(p) > room:
                intro = f"{intro} {sentence_cut(p, room)}".strip()
                notes.append("truncated")
                break
            intro = f"{intro} {p}".strip()
        if intro:
            segs.append(f"INTRODUCTION: {intro}")
    n_fallback = 0
    for p in fallback:
        room = MAX_CHARS - len("\t".join(segs)) - 1
        if room <= 50:
            notes.append("truncated")
            break
        if len(p) > room:
            segs.append(sentence_cut(p, room))
            n_fallback += 1
            notes.append("truncated")
            break
        segs.append(p)
        n_fallback += 1
    body_chars = sum(
        len(it["text"]) for it in items if it["label"] in ("text", "paragraph", "list_item")
    )
    return {
        "title": title,
        "input_text": "\t".join(segs),
        "parts": {
            "title": title,
            "abstract": abstract,
            "introduction": intro,
            "fallback_paragraphs": n_fallback,
        },
        "notes": notes,
        "body_chars": body_chars,
        "full_text": " ".join(it["text"] for it in items),
    }


EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
EMAIL_RE = re.compile(EMAIL)
# an address, optionally with its "e-mail:" label and further addresses after ; or ,
EMAIL_BLOCK = re.compile(
    r"(?:\b[Ee]-?[Mm]ail(?:s| addresses| address)?\s*:?\s*)?"
    + EMAIL
    + r"(?:\s*[;,]\s*"
    + EMAIL
    + r")*"
)


def scrub_emails(text: str) -> str:
    """Every e-mail address out, with its label (harmonise/build.py scrub_emails)."""
    if not EMAIL_RE.search(text):
        return text
    out = EMAIL_BLOCK.sub("", text)
    return re.sub(r"[ ]{2,}", " ", out)


def model_input(doc: dict) -> str:
    """The text the model gets for one Docling document (may be empty)."""
    return scrub_emails(build(doc)["input_text"])
