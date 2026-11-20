"""The `annotate` step handler (worker-llm, worker-fake-annotate).

Reads the paper's Docling document (`text.json`, written by the docling step), builds the
model input from its title, abstract and introduction (inputs.model_input, as trained), asks
the annotator, parses the answer (marcus.core.annotation.parse_output: the 11 fields, values
split and deduplicated) and locates every value in the paper's whole text as the Paper view
shows it (docling_blocks + Locator). The result goes to the planner, which checks it again
before storing it (pipeline._check_annotate_result).

Input problems are final (BadInput): no text file, a file that is not a Docling document, no
title/abstract/introduction text. An answer outside the schema is final too (BadResult): the
decoding is greedy, so a retry gives the same answer.
"""

import json
import time

from marcus.core.annotation import BadOutput, Locator, docling_blocks, parse_output, positions
from marcus.core.enums import StepKind
from marcus.core.pipeline import BadResult
from marcus.core.settings import fake_enabled, get_settings
from marcus.core.storage import paper_dir
from marcus.workers.annotate.fake import FakeAnnotator
from marcus.workers.annotate.inputs import model_input
from marcus.workers.annotate.llama import LlamaAnnotator
from marcus.workers.runtime import BadInput, register


def get_annotator():
    """The configured annotator (settings `annotator`); the fake one only where fake engines
    are enabled."""
    settings = get_settings()
    if settings.annotator == "fake":
        if not fake_enabled():
            raise RuntimeError("the fake annotator is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
        return FakeAnnotator()
    return LlamaAnnotator(
        settings.annotator_url,
        settings.annotator_timeout_s,
        settings.annotate_model,
        settings.annotate_model_version,
    )


def _document(step) -> dict:
    path = paper_dir(step.paper_id) / "text.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BadInput("the paper has no text") from None
    except (ValueError, OSError):
        raise BadInput("the paper's text could not be read") from None
    if not isinstance(doc, dict):
        raise BadInput("the paper's text is not a Docling document")
    return doc


def annotate(step, session) -> dict:
    if session is not None:
        session.rollback()  # nothing to read: end any transaction before the long work
    if step.paper_id is None:
        raise BadInput("annotate step has no paper")
    annotator = get_annotator()
    doc = _document(step)
    try:
        text = model_input(doc)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise BadInput("the paper's text is not a Docling document") from None
    if not text.strip():
        raise BadInput("no title, abstract or introduction found")
    start = time.monotonic()
    raw = annotator.complete(text)
    ms = int((time.monotonic() - start) * 1000)
    try:
        output = parse_output(raw)
    except BadOutput as exc:
        raise BadResult(str(exc)) from None
    found = positions(Locator(docling_blocks(doc)), output)
    return {
        "model": annotator.model,
        "model_version": annotator.version,
        "output": output,
        "positions": found,
        "ms": ms,
    }


register(StepKind.ANNOTATE, annotate)
