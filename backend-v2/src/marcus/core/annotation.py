"""Paper annotation with the local MARCUS model: the 11 fields, the decoding grammar, the output
parser, the paper's text blocks and the value locator.

Shared by the annotate worker (marcus.workers.annotate: builds the input, calls the model,
parses and locates) and the API (locates curated values, exports). Standard library only.

The model (models/qwen3.5-9b-marcus-v1/README.md) returns one JSON object with the 11 string
keys of FIELDS, in that order; each value is a comma-separated list of spans copied from the
input text, or `nan`. A field whose values contain `, ` (and `compound_group` always) is in the
quoted form `'a', 'b'` (GUIDELINE v2.1, F7). Decoding is greedy under `grammar()`: the keys in
order, each string at most MAX_LENGTH characters, no whitespace outside the strings. The model
text is data: it is parsed into plain lists of strings, never rendered as markup anywhere.

Positions: every value is located in the paper's text as the Paper view shows it, i.e. the
blocks of `docling_blocks` (a port of frontend-v2/src/workspace/doclingText.ts, which must stay
in step with it). A position is `[block, start, end]`: the block's index in that list and the
value's start and end offsets in the block's text in UTF-16 code units (JavaScript string
indices), end exclusive.
"""

import bisect
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FIELDS = (
    "compound_group",
    "compound_class",
    "organism_part",
    "organism_or_species",
    "geo_location",
    "Kingdom",
    "trivial_name",
    "location",
    "iupac_name",
    "abbreviation",
    "iupac_like_name",
)

# maxLength per field from the training schema (1.5 x the longest train value, at least 60)
MAX_LENGTH = {
    "compound_group": 435,
    "compound_class": 576,
    "organism_part": 183,
    "organism_or_species": 676,
    "geo_location": 348,
    "Kingdom": 60,
    "trivial_name": 397,
    "location": 234,
    "iupac_name": 7179,
    "abbreviation": 586,
    "iupac_like_name": 990,
}

LABELS = {
    "compound_group": "Compound series",
    "compound_class": "Compound class",
    "organism_part": "Organism part",
    "organism_or_species": "Organism",
    "geo_location": "Place",
    "Kingdom": "Kingdom",
    "trivial_name": "Compound names",
    "location": "Habitat or host",
    "iupac_name": "IUPAC names",
    "abbreviation": "Abbreviations",
    "iupac_like_name": "Semi-systematic names",
}

SYSTEM_PROMPT = "Extract the compound information from the Paragraph."
MAX_OUTPUT_TOKENS = 4096
EMPTY = {"", "nan", "none", "null", "n/a", "na", "[]"}
MAX_VALUES_PER_FIELD = 200  # values kept per field (model or curator)
MAX_CURATED_VALUES = 300  # values in one curation save, all fields together
MAX_OCCURRENCES = 200  # positions kept per value
# A paper's Docling document (text.json) larger than this is not read (API and worker-llm, whose
# mem_limit is 1g: parsing a 64 MB document peaks at about 365 MB).
MAX_TEXT_BYTES = 64 * 2**20

_QUOTED_SEP = re.compile(r"['\u2018\u2019]\s*,\s*['\u2018\u2019]")
_PLAIN_SEP = re.compile(r",\s+")
_QUOTES = "'\u2018\u2019"
_HIDDEN = {"Cc", "Cf", "Cs", "Co", "Cn"}  # controls (NUL too), format (bidi, zero-width), ...
_SPACES = re.compile(r"\s+")


class BadOutput(ValueError):
    """The model text is not the 11-key object the schema allows."""


class TextTooLarge(ValueError):
    """The paper's text file is larger than MAX_TEXT_BYTES (it is not read)."""


def read_document(path: Path) -> object:
    """The parsed JSON of a paper's text file (its Docling document; blocking read). A file over
    MAX_TEXT_BYTES is refused before it is read (TextTooLarge); otherwise OSError or ValueError
    as reading and parsing raise them."""
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise TextTooLarge(path.parent.name)
    return json.loads(path.read_text(encoding="utf-8"))


# --- decoding grammar --------------------------------------------------------------------------

# One JSON string character, as llama.cpp's own JSON grammar: no raw control character, any
# escape counts as one character (so the bound equals the schema's maxLength).
_CHAR = r'char ::= [^"\\\x7F\x00-\x1F] | [\\] (["\\/bfnrt] | "u" [0-9a-fA-F]{4})'


def grammar() -> str:
    """GBNF for llama-server: `{"compound_group":"...",...,"iupac_like_name":"..."}`, the keys
    in order, each string at most MAX_LENGTH characters, no whitespace between tokens."""
    keys = ' "," '.join(f'"\\"{f}\\":" s{i}' for i, f in enumerate(FIELDS))
    lines = [f'root ::= "{{" {keys} "}}"']
    for i, f in enumerate(FIELDS):
        lines.append(f'''s{i} ::= "\\"" char{{0,{MAX_LENGTH[f]}}} "\\""''')
    lines.append(_CHAR)
    return "\n".join(lines) + "\n"


# --- parsing the model text --------------------------------------------------------------------


def clean_value(value: str) -> str:
    """Hidden characters out (controls, NUL, bidi and zero-width marks), whitespace collapsed,
    trimmed, trailing `,`/`;` dropped."""
    text = "".join(c for c in value if c.isspace() or unicodedata.category(c) not in _HIDDEN)
    text = _SPACES.sub(" ", text).strip()
    return text.rstrip(",;").strip()


_CLOSE_TAIL = re.compile(r"['\u2018\u2019][.,;]*$")  # a closing quote, maybe with junk after it


def _unquote(part: str, last: bool, cut: bool) -> str | None:
    """One value of the quoted form without its wrapping quotes. A last value with no closing
    quote in a field cut by the length limit is a fragment: None."""
    p = part.strip()
    if p[:1] in _QUOTES:
        p = p[1:]
    tail = _CLOSE_TAIL.search(p)
    if tail:
        p = p[: tail.start()]
    elif last and cut:
        return None
    return p


def split_field(text: str, max_length: int | None = None) -> list[str]:
    """One field's string -> its distinct values in order (exact duplicates dropped: the case
    of a form is part of it, GUIDELINE F4). `nan` and other empty markers -> [].

    Quoted form (`'a', 'b'`, F7; any field that starts with a quote): every value loses its
    wrapping quotes, also when they are unbalanced. Plain form: a leading quote goes, a
    trailing one stays (a prime, `luteolin 3'`). A field as long as `max_length` was cut by the
    decoding limit (the greedy repeat loop the model README describes): its last value is a
    fragment and is dropped."""
    t = text.strip()
    if t.lower() in EMPTY:
        return []
    cut = max_length is not None and len(text) >= max_length
    quoted = bool(_QUOTED_SEP.search(t)) or t[0] in _QUOTES
    parts = _QUOTED_SEP.split(t) if quoted else _PLAIN_SEP.split(t)
    out: list[str] = []
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if quoted:
            raw = _unquote(part, last, cut)
        else:
            raw = None if last and cut and len(parts) > 1 else part.strip().lstrip(_QUOTES)
        if raw is None:
            continue
        value = clean_value(raw)
        if not value or value.lower() in EMPTY or value in out:
            continue
        out.append(value)
        if len(out) == MAX_VALUES_PER_FIELD:
            break
    return out


def parse_output(raw: str) -> dict[str, list[str]]:
    """The model text -> {field: [values]} in FIELDS order. BadOutput unless it is a JSON
    object with exactly the 11 keys, each a string within its maxLength."""
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise BadOutput("model output is not JSON") from exc
    if not isinstance(obj, dict) or set(obj) != set(FIELDS):
        raise BadOutput("model output does not have the 11 keys")
    for field in FIELDS:
        value = obj[field]
        if not isinstance(value, str) or len(value) > MAX_LENGTH[field]:
            raise BadOutput(f"model output: {field} is not a string within its length")
    return {field: split_field(obj[field], MAX_LENGTH[field]) for field in FIELDS}


def empty_values() -> dict[str, list[str]]:
    return {field: [] for field in FIELDS}


# --- checks of stored shapes (worker results are data: checked before they are stored) -------


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**31


def values_error(values: object, max_chars: dict[str, int] | int = MAX_LENGTH) -> str | None:
    """Why `values` is not {field: [distinct non-empty strings]} over exactly FIELDS, or None."""
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        return "values must have exactly the 11 fields"
    for field in FIELDS:
        items = values[field]
        limit = max_chars if isinstance(max_chars, int) else max_chars[field]
        if not isinstance(items, list) or len(items) > MAX_VALUES_PER_FIELD:
            return f"{field}: must be a list of at most {MAX_VALUES_PER_FIELD} values"
        for item in items:
            if not isinstance(item, str) or not item.strip() or "\x00" in item:
                return f"{field}: every value must be a non-empty string"
            if len(item) > limit:
                return f"{field}: a value is longer than {limit} characters"
        if len(set(items)) != len(items):
            return f"{field}: values must be distinct"
    return None


def positions_error(found: object, values: dict[str, list[str]]) -> str | None:
    """Why `found` is not {field: {value: [[block, start, end], ...]}} for exactly `values`."""
    if not isinstance(found, dict) or set(found) != set(FIELDS):
        return "positions must have exactly the 11 fields"
    for field in FIELDS:
        per_value = found[field]
        if not isinstance(per_value, dict) or set(per_value) != set(values[field]):
            return f"{field}: positions must cover exactly its values"
        for hits in per_value.values():
            if not isinstance(hits, list) or len(hits) > MAX_OCCURRENCES:
                return f"{field}: at most {MAX_OCCURRENCES} positions per value"
            for hit in hits:
                if not (isinstance(hit, list) and len(hit) == 3 and all(map(_is_int, hit))):
                    return f"{field}: a position is [block, start, end]"
                if hit[1] >= hit[2]:
                    return f"{field}: a position must end after it starts"
    return None


# --- the paper's text blocks (frontend-v2 doclingText.ts) -----------------------------------------

_REF = re.compile(r"#/(texts|groups)/([0-9]+)")  # fullmatch: JavaScript's ^...$ and \d
_END = object()
# JavaScript String.prototype.trim(): WhiteSpace and LineTerminator code points
_JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008" \
    "\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"  # fmt: skip


def _block(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str) or text.strip(_JS_SPACE) == "":
        return None
    return text


def resolve_ref(ref: object, texts: list, groups: list) -> tuple[str, object] | None:
    """("texts" or "groups", the item) a child's `$ref` points at; None for anything else (not
    `#/texts/i` or `#/groups/i`, or an index past the end)."""
    m = _REF.fullmatch(ref) if isinstance(ref, str) else None
    if m is None:
        return None
    pool = texts if m.group(1) == "texts" else groups
    digits = m.group(2)
    i = int(digits) if len(digits) < 10 else len(pool)  # 10 digits: past any real list
    return (m.group(1), pool[i]) if i < len(pool) else None


def doc_pools(doc: dict) -> tuple[list, list]:
    """(texts, groups) of a Docling document, [] for one that is missing or not a list."""
    texts, groups = doc.get("texts"), doc.get("groups")
    return (
        texts if isinstance(texts, list) else [],
        groups if isinstance(groups, list) else [],
    )


def docling_blocks(doc: object) -> list[str]:
    """The texts of the Paper view's headings and paragraphs, in its order: `body.children`
    walked depth first (`#/texts/i` is texts[i] followed by its own children, `#/groups/i` is
    walked; anything else is skipped, and so is a ref back to an item being walked); without a
    body, the texts in array order. Blank texts are left out."""
    if not isinstance(doc, dict):
        return []
    texts, groups = doc_pools(doc)
    body = doc.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("children"), list):
        return [t for t in map(_block, texts) if t is not None]
    out: list[str] = []
    walking: set[str] = set()  # the refs on the current path (a ref back to one is skipped)
    stack: list[tuple] = [(iter(body["children"]), None)]  # iterative: no recursion limit
    while stack:
        children, ref_of_frame = stack[-1]
        child = next(children, _END)
        if child is _END:
            stack.pop()
            walking.discard(ref_of_frame)
            continue
        ref = child.get("$ref") if isinstance(child, dict) else None
        found = resolve_ref(ref, texts, groups)
        if found is None or ref in walking:
            continue
        kind, item = found
        if kind == "texts":
            text = _block(item)
            if text is not None:
                out.append(text)
        kids = item.get("children") if isinstance(item, dict) else None
        if isinstance(kids, list):
            walking.add(ref)
            stack.append((iter(kids), ref))
    return out


# --- locating values ---------------------------------------------------------------------------

_DASHES = set("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d")


@lru_cache(maxsize=8192)
def _piece(ch: str, fold: bool = False) -> str:
    """What one character of the text counts as when matching: compatibility form without
    accents, every dash a hyphen, any whitespace one space, a soft hyphen nothing; lower-cased
    when `fold`. Cached: a paper has few distinct characters."""
    if ch == "\u00ad":
        return ""
    if ch.isspace():
        return " "
    if ch in _DASHES:
        return "-"
    decomposed = unicodedata.normalize("NFKD", ch)
    kept = "".join(c for c in decomposed if not unicodedata.combining(c))
    piece = "".join("-" if c in _DASHES else c for c in kept)
    return piece.lower() if fold else piece


_TOKENS = re.compile(r"[!-~]+|\s+|.", re.DOTALL)  # printable ASCII runs, space runs, any other


def _normalise(text: str, fold: bool) -> tuple[str, list[int] | range]:
    """(matching form of `text`, for each of its characters the index in `text` it came from).
    Every character counts as its `_piece`; runs of spaces become one. Printable ASCII runs are
    their own pieces (lower-cased when folding) and are copied whole, not per character."""
    # Fast path (most blocks): every character's piece is one character and no two spaces end
    # up side by side, so the form is a per-character translation and the map the identity.
    table = {ord(c): _piece(c, fold) for c in set(text)}
    if all(len(p) == 1 for p in table.values()):
        form = text.translate(table)
        if "  " not in form:
            return form, range(len(form))
    chars: list[str] = []
    origin: list[int] = []
    last = ""
    for m in _TOKENS.finditer(text):
        token, i = m.group(), m.start()
        if token[0] > " " and token[0] <= "~":
            chars.append(token.lower() if fold else token)
            origin.extend(range(i, i + len(token)))
            last = token[-1]
            continue
        if token.isspace():  # a run of spaces: one space (if the last character is not one)
            if last != " ":
                chars.append(" ")
                origin.append(i)
                last = " "
            continue
        for k, ch in enumerate(token):
            for c in _piece(ch, fold):
                if c == " " and last == " ":
                    continue
                chars.append(c)
                origin.append(i + k)
                last = c
    return "".join(chars), origin


def _utf16_offsets(text: str) -> list[int] | None:
    """For each index 0..len(text), its offset in UTF-16 code units; None when every character
    is one code unit (no astral character: the index is the offset). A lone surrogate counts
    as one code unit, as in JavaScript."""
    if not text or max(text) <= "\uffff":
        return None
    out, at = [0], 0
    for c in text:
        at += 2 if c > "\uffff" else 1
        out.append(at)
    return out


class Locator:
    """Finds values in the paper's text blocks (built once per paper). Each matching form (own
    case, any case) is built on first use: the blocks normalised and joined by newlines (a
    normalised text has none, so no match crosses a block)."""

    def __init__(self, blocks: list[str]):
        self.blocks = blocks
        self._forms: dict[bool, tuple[str, list[int], list[list[int]]]] = {}
        self._units: dict[int, list[int] | None] = {}  # block -> _utf16_offsets, on first hit

    def _form(self, fold: bool) -> tuple[str, list[int], list[list[int]]]:
        """(joined text, start of each block in it, each block's origin map)."""
        if fold not in self._forms:
            parts, starts, origins, at = [], [], [], 0
            for block in self.blocks:
                form, origin = _normalise(block, fold)
                parts.append(form)
                starts.append(at)
                origins.append(origin)
                at += len(form) + 1
            self._forms[fold] = ("\n".join(parts), starts, origins)
        return self._forms[fold]

    def _scan(self, needle: str, fold: bool) -> list[list[int]]:
        joined, starts, origins = self._form(fold)
        literal = re.escape(needle)
        pattern = literal
        # whole spans only: no letter or digit right before or after a value that starts or
        # ends with one. The check before is a lookbehind AFTER the literal, so the regex
        # engine can still search for the literal first.
        if needle[0].isalnum():
            pattern += rf"(?<![^\W_]{literal})"
        if needle[-1].isalnum():
            pattern += r"(?![^\W_])"
        hits: list[list[int]] = []
        for m in re.finditer(pattern, joined):
            at, end = m.span()
            b = bisect.bisect_right(starts, at) - 1
            text, origin = self.blocks[b], origins[b]
            start_cp, end_cp = origin[at - starts[b]], origin[end - 1 - starts[b]] + 1
            # take along what counts as nothing (a combining accent, a soft hyphen)
            while end_cp < len(text) and _piece(text[end_cp]) == "":
                end_cp += 1
            if b not in self._units:
                self._units[b] = _utf16_offsets(text)
            units = self._units[b]
            hits.append([b, units[start_cp], units[end_cp]] if units else [b, start_cp, end_cp])
            if len(hits) == MAX_OCCURRENCES:
                break
        return hits

    def find(self, value: str) -> list[list[int]]:
        """Every occurrence of `value` as a whole span (not inside a longer word): in its own
        case if it occurs so anywhere, else in any case. At most MAX_OCCURRENCES."""
        for fold in (False, True):
            needle = _normalise(value, fold)[0].strip()
            if not needle:
                return []
            hits = self._scan(needle, fold)
            if hits:
                return hits
        return []


def positions(locator: Locator, values: dict[str, list[str]]) -> dict[str, dict[str, list]]:
    """{field: {value: [[block, start, end], ...]}} for every value (an empty list when the
    value is not in the text, e.g. an inferred Kingdom)."""
    return {
        field: {value: locator.find(value) for value in values.get(field, [])} for field in FIELDS
    }


# --- COCONUT -----------------------------------------------------------------------------------


def _form_item(value: str) -> str:
    """One item of the COCONUT form's comma-separated lists: a value holding a comma or a double
    quote goes in double quotes, a quote inside doubled (frontend-v2 coconutApi `list`)."""
    if "," not in value and '"' not in value:
        return value
    return '"' + value.replace('"', '""') + '"'


def coconut_prefill(shown: dict[str, list[str]]) -> dict:
    """Starting values for the COCONUT submit form's organisms (frontend-v2 OrganismDraft): one
    per organism value, each with the paper's parts (the form's comma-separated list) and its
    first place. Ecosystems stay empty: "Habitat or host" holds a host organism as often as a
    habitat, and the model cannot tell them apart. COCONUT has no kingdom field; `kingdom` is
    passed on as is."""
    parts = ", ".join(map(_form_item, shown.get("organism_part", [])))
    places = shown.get("geo_location", [])
    organisms = [
        {
            "name": name,
            "parts": parts,
            "location": places[0] if places else "",
            "ecosystems": "",
        }
        for name in shown.get("organism_or_species", [])
    ]
    return {"organisms": organisms, "kingdom": list(shown.get("Kingdom", []))}
