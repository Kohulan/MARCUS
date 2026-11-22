"""What counts as an R-group label: the grammar of the placeholders papers draw. Pure (no RDKit).

A dummy atom's alias is the label the engine read beside it. MolScribe also writes a group it did
not expand there (OAc, BnO, MeO, CO2H, Boc...), and numbers or element counts it misread (555,
S7, N3, O3): none of those is a placeholder. A label counts only when it has the form papers use
for one (owner decision 2026-11-22; the list chosen from the Phase 2 test set's OCSR output and
the gold labels of the test and training sets, MARCUS-training markush-eval/followups/):

- R, with optional primes, an index of 1 or 2 digits and one lower-case letter: R, R1, R10, R′,
  R1′, R′1, R6″, Ra, Rf, R1a;
- X, Y, Z with an optional index and primes (X1, Z2); Ar with an optional index;
- n, m (repeat counts) and Q;
- `*`: an unlabelled point.

MolScribe writes the group around an R-group as one alias (OR3, R2O, RaO, CO2R, COOR, NHR, SR,
CH2OR1, N(R)2): the label is the one R-group in it.
"""

import re

_R = r"R[′″']*(?:\d{1,2})?[a-z]?[′″']*"
_OTHER = r"[XYZ](?:\d{1,2})?[′″']*|Ar(?:\d{1,2})?|[nmQ]|\*"
_LABEL = re.compile(rf"(?:{_R}|{_OTHER})")
# An alias that carries one R-group in a small group written around it (OR3, R2O, CO2R, COOR,
# NHR, SR, CH2OR1, N(R)2): only H, C, N, O, S, digits and brackets beside the R.
_FRAGMENT = r"(?:[CHONS()][CHONS0-9()=]*)?"  # starts with an atom or a bracket, never a digit
_CARRIED = re.compile(rf"({_FRAGMENT})({_R})({_FRAGMENT})")


def as_label(text: str) -> str | None:
    """`text` as an R-group label (an alias carrying one R-group as that R-group), or None when
    it has not the form of one."""
    text = text.strip()
    if _LABEL.fullmatch(text):
        return text
    m = _CARRIED.fullmatch(text)
    if m and (m.group(1) or m.group(3)):
        return m.group(2)
    return None


# --- the labels a page's text names ---------------------------------------------------------

_SCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
_PRIMES = (("″", "′′"), ('"', "′′"), ("’", "′"), ("'", "′"))
# The label grammar as text writes it: Docling may space a subscript or a prime ("R 1", "R 1 ′").
_TEXT_LABEL = re.compile(
    r"(?<!\w)(?:R(?:\s?′)*(?:\s?\d{1,2})?[a-z]?(?:\s?′)*"
    r"|[XYZ](?:\s?\d{1,2})?(?:\s?′)*|Ar(?:\s?\d{1,2})?|[nmQ])(?![\w′])"
)
MAX_PAGE_LABELS = 200  # labels one page's text may name in the stored index


def _plain(text: str) -> str:
    """Super- and subscript digits as digits, every prime as ′ (R², R₂ -> R2; R', R’ -> R′;
    R", R″ -> R′′), as Docling and the drawings write them in different ways."""
    text = text.translate(_SCRIPT_DIGITS)
    for old, new in _PRIMES:
        text = text.replace(old, new)
    return text


def canonical(label: str) -> str:
    """One spelling of a label for comparing: R' and R′ alike, no spaces."""
    return "".join(_plain(label).split())


# Ranges name every label in them: "R1–R4", "R1-R4", "R1-4", "R1 to R4", "R1~R4" (at most 20).
_RANGE = re.compile(r"(?<!\w)R\s?(\d{1,2})\s*(?:[-–—~]|to)\s*(?:R\s?)?(\d{1,2})(?![\d′\w])")
_MAX_RANGE = 20
# Joined forms: a label right after another (R1R2), after a lone O, N or S (OR1, NR1R2, SR4),
# or before O, N, S or Ph (R3O, R1R2N, R2Ph). Only numbered or primed R labels: a bare R or a
# one-letter label joined to letters is a word.
_R_INDEXED = r"R(?:′+\d{0,2}|\d{1,2}′*)"
_JOIN_BEFORE = re.compile(rf"(?<![A-Za-z])([ONS])(?={_R_INDEXED})")
_JOIN_CHAIN = re.compile(rf"({_R_INDEXED})(?={_R_INDEXED})")
_JOIN_AFTER = re.compile(rf"({_R_INDEXED})(O|N|S|Ph)(?![a-z])")
# A one-letter token that is the start of a word ("X-ray", "n-butyl", "m-CPBA", "Q-TOF",
# "R-configured") or half of "E/Z".
_ONE_LETTER = frozenset({"R", "X", "Y", "Z", "n", "m", "Q"})
WEAK = frozenset({"X", "Y", "Z", "n", "m", "Q"})  # named alone, they decide nothing


def _expand_range(m: re.Match) -> str:
    first, last = int(m.group(1)), int(m.group(2))
    if not first < last <= first + _MAX_RANGE:
        return m.group()
    return " ".join(f"R{i}" for i in range(first, last + 1))


def text_labels(text: str) -> set[str]:
    """The labels `text` names, each as a token of its own (canonical spelling): not inside a
    word or another label (R1 in R10 or R1′, R in R1), not a stereo descriptor in brackets
    ("(Z)", "(R)"), not the first letter of a word ("X-ray", "n-butyl") or of "E/Z". A range
    (R1–R4) names every label in it; joined forms (OR1, R1R2N, R2Ph) name their labels."""
    plain = _RANGE.sub(_expand_range, _plain(text))
    plain = _JOIN_BEFORE.sub(r"\1 ", plain)
    plain = _JOIN_CHAIN.sub(r"\1 ", plain)
    plain = _JOIN_AFTER.sub(r"\1 \2", plain)
    found: set[str] = set()
    for m in _TEXT_LABEL.finditer(plain):
        start, end = m.span()
        before, after = plain[start - 1 : start], plain[end : end + 2]
        if before == "(" and after[:1] == ")":
            continue
        token = "".join(m.group().split())
        if token in _ONE_LETTER and (
            (after[:1] == "-" and after[1:2].isalpha()) or "/" in (before, after[:1])
        ):
            continue
        found.add(token)
    return found


def shown_labels(labels: list[str], named: set[str] | list[str] | None) -> list[str]:
    """Of a structure's labels, those its page's text names (`named`: canonical spellings), in
    their order. All of them when the text names none of them, or only one-letter ones (WEAK:
    X, Y, Z, n, m, Q are also words and symbols), or there is no text (None). OCSR sometimes
    adds a label the drawing does not have (DECIMER's Z beside R1, R2)."""
    if not named:
        return list(labels)
    names = set(named)
    hits = [lab for lab in labels if canonical(lab) in names]
    if not any(canonical(lab) not in WEAK for lab in hits):
        return list(labels)
    return hits


def page_label_index(doc: dict, pages: int) -> dict[str, list[str]]:
    """Per page (0-based, as the API counts; key a string, for JSON), the labels the R-group
    model's context for a scaffold on it names (marcus.core.page_text.page_context: Docling
    pages P..P+2). Pages that name none are left out."""
    from marcus.core.page_text import page_context

    index: dict[str, list[str]] = {}
    for page in range(pages):
        found = text_labels(page_context(doc, page + 1))
        if found:
            index[str(page)] = sorted(found)[:MAX_PAGE_LABELS]
    return index


def index_error(index: object, pages: int) -> str | None:
    """Why `index` is not a page label index of a paper with `pages` pages, or None."""
    if not isinstance(index, dict):
        return "the page label index must be an object"
    for key, found in index.items():
        if not (isinstance(key, str) and key.isdigit() and int(key) < pages):
            return f"page label index: {key!r} is not a page of the paper"
        if not isinstance(found, list) or len(found) > MAX_PAGE_LABELS:
            return f"page label index: page {key} must have a list of labels"
        if len(set(found)) != len(found) or not all(
            isinstance(lab, str) and as_label(lab) == lab for lab in found
        ):
            return f"page label index: page {key} must have distinct labels"
    return None
