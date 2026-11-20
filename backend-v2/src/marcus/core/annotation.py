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

import json
import re
import unicodedata

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
MAX_VALUE_CHARS = 1000  # one curated value
MAX_OCCURRENCES = 200  # positions kept per value

_QUOTED_SEP = re.compile(r"['\u2018\u2019]\s*,\s*['\u2018\u2019]")
_PLAIN_SEP = re.compile(r",\s+")
_QUOTES = "'\u2018\u2019"
_HIDDEN = {"Cc", "Cf", "Cs", "Co", "Cn"}  # controls (NUL too), format (bidi, zero-width), ...
_SPACES = re.compile(r"\s+")


class BadOutput(ValueError):
    """The model text is not the 11-key object the schema allows."""


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


def split_field(text: str) -> list[str]:
    """One field's string -> its distinct values in order (exact duplicates dropped: the case
    of a form is part of it, GUIDELINE F4). `nan` and other empty markers -> []."""
    t = text.strip()
    if t.lower() in EMPTY:
        return []
    quoted = bool(_QUOTED_SEP.search(t)) or (len(t) >= 2 and t[0] in _QUOTES and t[-1] in _QUOTES)
    if quoted:
        t = t[1:-1] if t[0] in _QUOTES and t[-1] in _QUOTES else t
        parts = _QUOTED_SEP.split(t)
    else:
        parts = _PLAIN_SEP.split(t)
    out: list[str] = []
    for part in parts:
        value = clean_value(part)
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
    return {field: split_field(obj[field]) for field in FIELDS}


def empty_values() -> dict[str, list[str]]:
    return {field: [] for field in FIELDS}


# --- the paper's text blocks (frontend-v2 doclingText.ts) -----------------------------------------

_REF = re.compile(r"^#/(texts|groups)/(\d+)$")
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


def docling_blocks(doc: object) -> list[str]:
    """The texts of the Paper view's headings and paragraphs, in its order: `body.children`
    walked depth first (`#/texts/i` is texts[i] followed by its own children, `#/groups/i` is
    walked; anything else is skipped, and so is a ref back to an item being walked); without a
    body, the texts in array order. Blank texts are left out."""
    if not isinstance(doc, dict):
        return []
    texts = doc.get("texts") if isinstance(doc.get("texts"), list) else []
    body = doc.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("children"), list):
        return [t for t in map(_block, texts) if t is not None]
    groups = doc.get("groups") if isinstance(doc.get("groups"), list) else []
    out: list[str] = []
    walking: set[str] = set()

    def walk(children: list) -> None:
        for child in children:
            ref = child.get("$ref") if isinstance(child, dict) else None
            m = _REF.match(ref) if isinstance(ref, str) else None
            if m is None or m.group(0) in walking:
                continue
            i = int(m.group(2))
            pool = texts if m.group(1) == "texts" else groups
            item = pool[i] if i < len(pool) else None
            if m.group(1) == "texts":
                text = _block(item)
                if text is not None:
                    out.append(text)
            kids = item.get("children") if isinstance(item, dict) else None
            if isinstance(kids, list):
                walking.add(m.group(0))
                walk(kids)
                walking.discard(m.group(0))

    walk(body["children"])
    return out


# --- locating values ---------------------------------------------------------------------------

_DASHES = set("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d")


def _piece(ch: str) -> str:
    """What one character of the text counts as when matching: compatibility form without
    accents, every dash a hyphen, any whitespace one space, a soft hyphen nothing."""
    if ch == "\u00ad":
        return ""
    if ch.isspace():
        return " "
    if ch in _DASHES:
        return "-"
    decomposed = unicodedata.normalize("NFKD", ch)
    kept = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join("-" if c in _DASHES else c for c in kept)


def _normalise(text: str, fold: bool) -> tuple[str, list[int]]:
    """(matching form of `text`, for each of its characters the index in `text` it came from).
    Runs of spaces become one."""
    chars: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        piece = _piece(ch)
        if fold:
            piece = piece.lower()
        for c in piece:
            if c == " " and chars and chars[-1] == " ":
                continue
            chars.append(c)
            origin.append(i)
    return "".join(chars), origin


def _utf16(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


class Locator:
    """Finds values in the paper's text blocks (built once per paper)."""

    def __init__(self, blocks: list[str]):
        self.blocks = blocks
        self._forms = {fold: [_normalise(b, fold) for b in blocks] for fold in (False, True)}

    def _scan(self, needle: str, fold: bool) -> list[list[int]]:
        hits: list[list[int]] = []
        edge_start, edge_end = needle[0].isalnum(), needle[-1].isalnum()
        for b, (form, origin) in enumerate(self._forms[fold]):
            at = form.find(needle)
            while at >= 0:
                end = at + len(needle)
                clear_before = not edge_start or at == 0 or not form[at - 1].isalnum()
                clear_after = not edge_end or end == len(form) or not form[end].isalnum()
                if clear_before and clear_after:
                    text = self.blocks[b]
                    start_cp, end_cp = origin[at], origin[end - 1] + 1
                    # take along what counts as nothing (a combining accent, a soft hyphen)
                    while end_cp < len(text) and _piece(text[end_cp]) == "":
                        end_cp += 1
                    hits.append([b, _utf16(text, start_cp), _utf16(text, end_cp)])
                    if len(hits) == MAX_OCCURRENCES:
                        return hits
                at = form.find(needle, end if clear_before and clear_after else at + 1)
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


def coconut_prefill(shown: dict[str, list[str]]) -> dict:
    """Starting values for the COCONUT submit form's organisms (frontend-v2 OrganismDraft): one
    per organism value, each with the paper's parts (comma-separated), its first place and its
    habitats as ecosystems. COCONUT has no kingdom field; `kingdom` is passed on as is."""
    parts = ", ".join(shown.get("organism_part", []))
    places = shown.get("geo_location", [])
    ecosystems = ", ".join(shown.get("location", []))
    organisms = [
        {
            "name": name,
            "parts": parts,
            "location": places[0] if places else "",
            "ecosystems": ecosystems,
        }
        for name in shown.get("organism_or_species", [])
    ]
    return {"organisms": organisms, "kingdom": list(shown.get("Kingdom", []))}
