"""R-group definitions of a scaffold, read by the local vision model (Markush Phase 2).

A structure with R-group placeholders (marcus.core.rgroups) stands for several compounds. On
request, worker-rgroup asks the R-group model (nuextract3-rgroup-v1, vision variant, behind its own
llama-server `llama-rgroup`) which compounds the scaffold stands for and what each R-group is:

    {"rows": [{"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}}, ...]}

The request is the one the model was trained and tested on (MARCUS-training
models/nuextract3-rgroup-v1/README.md; markush-eval/markush_eval.py `user_prompt`, `schema_for`,
`ask`; markush-eval/bakeoff/code/rg_common.py `SYSTEM_VISION` and predict_rg.py `body_for`):
the system turn SYSTEM_VISION, one user turn whose first part is the page image and whose second
is user_prompt(labels, context), temperature 0, at most 2,048 output tokens, the JSON schema of
schema_for(labels) as `response_format`, thinking off. Keep every string here byte for byte as
in those files: a change changes what the model sees.

This module holds what both sides need: the request (worker) and the checks of the stored rows
(planner, API). The page text and the page image are built in marcus.workers.rgroups.
"""

from __future__ import annotations

import json
import unicodedata

from marcus.core.rgroup_labels import UNLABELLED, shown_labels, text_labels

MAX_VALUE = 80  # markush_eval.MAX_VALUE: a substituent's maxLength in the schema
MAX_COMPOUND = 40  # the compound label's maxLength in the schema
MAX_OUTPUT_TOKENS = 2048
MAX_ROWS = 500  # rows kept (2,048 tokens hold far fewer); a longer answer is cut here
MAX_LABELS = 30  # labels one request may name (a scaffold has at most a handful)
MAX_LABEL_CHARS = 40

# rg_common.SYSTEM_VISION, verbatim
SYSTEM_VISION = (
    "You read chemistry papers. A structure drawing in this paper has R-group placeholders. "
    "From the page image and the text, captions and tables below, list every compound that this "
    "scaffold stands for, with the substituent the paper gives for each R-group. Copy compound "
    "labels and substituents exactly as written in the paper (for example 3a, OMe, H, β-D-Glc, OAc). "
    "Use only what the paper states; never guess. If the paper does not define the R-groups, "
    "return an empty list."
)

_HIDDEN = {"Cc", "Cf", "Cs", "Co", "Cn"}  # controls (NUL too), format (bidi, zero-width), ...


class BadRows(ValueError):
    """The model text is not the object the schema allows."""


def schema_for(labels: list[str]) -> dict:
    """markush_eval.schema_for, verbatim: every row names its compound and every label."""
    groups = {lab: {"type": "string", "maxLength": MAX_VALUE} for lab in labels}
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "compound": {"type": "string", "maxLength": MAX_COMPOUND},
                        "groups": {"type": "object", "properties": groups,
                                   "required": labels, "additionalProperties": False},
                    },
                    "required": ["compound", "groups"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    }  # fmt: skip


# --- the labels to ask for --------------------------------------------------------------------

def named_labels(labels: list[str], context: str) -> list[str]:
    """The labels to ask the model for: those the page text (the model's `context`) names, in
    their order; all of them when it names none (no text, or the definitions are only drawn).

    The same rule as the labels shown for a structure (marcus.core.rgroup_labels.shown_labels).
    OCSR sometimes adds a label the drawing does not have (DECIMER read stylissa-bromopyrroles
    page 6 as R1, R2 and Z); asked for it, the model fills that column too. Measured on the
    Phase 2 test set, DECIMER run as MARCUS runs it on all 42 gold scaffold pages (MARCUS-training
    markush-eval/followups/): 33 crops match a gold scaffold, 7 of them with a label the gold
    labels do not have; this drops 7 of those 8 labels and none of the 60 real ones. On the gold
    labels themselves it keeps 164 of 164 (test set) and 1,770 of 1,778 (training set). A rule
    on the answer instead (a column whose value differs between rows) would lose 19 of the 164
    gold labels (stylissa's R2 is Br in both rows).
    """
    return shown_labels(labels, text_labels(context))




def labels_to_ask(labels: list[str], context: str) -> list[str]:
    """The labels of a request: `*` left out, then those the page text names (named_labels).

    The model was trained and tested on the labels printed in the paper (the markush-train and
    markush-testset gold labels: R, R1, R′, X, n, Ar...), never on `*`, and the trained requests
    named only those. An unlabelled point is no column the paper fills; and the text's
    asterisks (author marks, footnotes) would otherwise count as naming it. [] for a structure
    with no label but `*`: there is no trained request for it (request_rgroups refuses it).
    """
    labelled = [lab for lab in labels if lab != UNLABELLED]
    return named_labels(labelled, context) if labelled else []


def user_prompt(labels: list[str], context: str) -> str:
    """markush_eval.user_prompt, verbatim (the record's labels and context as arguments)."""
    return (f"The structure has these R-groups: {', '.join(labels)}.\n\n"
            f"Paper text near the structure:\n{context}")  # fmt: skip


def request_body(model: str, labels: list[str], context: str, image_uri: str) -> dict:
    """predict_rg.body_for with a page image: the same keys in the same order (so json.dumps
    gives the same bytes as the bake-off client for the same inputs)."""
    content = [
        {"type": "image_url", "image_url": {"url": image_uri}},
        {"type": "text", "text": user_prompt(labels, context)},
    ]
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_VISION},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "rgroups", "schema": schema_for(labels)},
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }


# --- the model text -> rows --------------------------------------------------------------------


def clean(value: str) -> str:
    """Hidden characters out (controls, NUL, bidi and zero-width marks), whitespace collapsed,
    trimmed. Nothing else changes: values are kept as the paper writes them."""
    text = "".join(c for c in value if c.isspace() or unicodedata.category(c) not in _HIDDEN)
    return " ".join(text.split())


def _row(item: object, labels: list[str]) -> dict:
    if not isinstance(item, dict) or set(item) != {"compound", "groups"}:
        raise BadRows("a row must have exactly 'compound' and 'groups'")
    compound, groups = item["compound"], item["groups"]
    if not isinstance(compound, str) or len(compound) > MAX_COMPOUND:
        raise BadRows(f"'compound' must be a string of at most {MAX_COMPOUND} characters")
    if not isinstance(groups, dict) or set(groups) != set(labels):
        raise BadRows("'groups' must have exactly the scaffold's labels")
    for value in groups.values():
        if not isinstance(value, str) or len(value) > MAX_VALUE:
            raise BadRows(f"a group must be a string of at most {MAX_VALUE} characters")
    return {"compound": clean(compound), "groups": {lab: clean(groups[lab]) for lab in labels}}


def _keep(rows: list[dict]) -> list[dict]:
    """Rows with something in them, each (compound, groups) once, at most MAX_ROWS."""
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not row["compound"] and not any(row["groups"].values()):
            continue
        key = json.dumps(row, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) == MAX_ROWS:
            break
    return out


def parse_rows(raw: str, labels: list[str]) -> list[dict]:
    """The model text -> rows (labels in `labels` order, values cleaned, empty and repeated rows
    dropped). BadRows unless it is the schema's object."""
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise BadRows("model output is not JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"rows"} or not isinstance(obj["rows"], list):
        raise BadRows("model output must be an object with only 'rows', a list")
    return _keep([_row(item, labels) for item in obj["rows"]])


def salvage_rows(raw: str, labels: list[str]) -> list[dict]:
    """The complete rows before the cut of an answer the token limit ended (finish_reason
    `length`): each row object that parses whole and fits the schema, in order, up to the first
    that does not. [] when none does."""
    start = raw.find("[")
    if start < 0 or "".join(raw[:start].split()) != '{"rows":':
        return []
    decoder = json.JSONDecoder()
    rows: list[dict] = []
    i = start + 1
    while True:
        while i < len(raw) and raw[i] in " \t\r\n,":
            i += 1
        try:
            item, i = decoder.raw_decode(raw, i)
            rows.append(_row(item, labels))
        except (ValueError, RecursionError):  # BadRows is a ValueError
            break
    return _keep(rows)


# --- checks of stored shapes (worker results are data: checked before they are stored) -------


def labels_error(labels: object) -> str | None:
    """Why `labels` is not a list of distinct non-empty labels, or None."""
    if not isinstance(labels, list) or not 0 < len(labels) <= MAX_LABELS:
        return f"labels must be a list of 1 to {MAX_LABELS} labels"
    for lab in labels:
        if not isinstance(lab, str) or not lab or len(lab) > MAX_LABEL_CHARS or "\x00" in lab:
            return f"every label must be a string of 1 to {MAX_LABEL_CHARS} characters"
    if len(set(labels)) != len(labels):
        return "labels must be distinct"
    return None


def rows_error(rows: object, labels: list[str]) -> str | None:
    """Why `rows` is not a list of {compound, groups} rows over exactly `labels`, or None."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        return f"rows must be a list of at most {MAX_ROWS} rows"
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"compound", "groups"}:
            return "a row must have exactly 'compound' and 'groups'"
        compound, groups = row["compound"], row["groups"]
        if not isinstance(compound, str) or len(compound) > MAX_COMPOUND or "\x00" in compound:
            return f"'compound' must be a string of at most {MAX_COMPOUND} characters"
        if not isinstance(groups, dict) or list(groups) != labels:
            return "'groups' must have exactly the labels, in order"
        for value in groups.values():
            if not isinstance(value, str) or len(value) > MAX_VALUE or "\x00" in value:
                return f"a group must be a string of at most {MAX_VALUE} characters"
    return None
