"""Real-model smoke test of paper annotation: the annotate step's own handler against a running
llama-server, on one paper's Docling document. Run by ops/annotate_smoke.sh inside the api image
(it needs no database, Redis or Celery broker).

    python annotate_smoke.py <paper id>
    env: MARCUS_DATA_ROOT (holds papers/<id>/text.json), MARCUS_LLM_URL,
         MARCUS_LLM_TIMEOUT_S

Checks: the handler's result passes the planner's own result check; every position points at
its value in the text the Paper view shows (UTF-16 offsets, same matching rules); the grammar
held (the reply parsed). Prints a JSON report (values, occurrences, seconds) and exits 1 when a
check fails.
"""

import json
import sys
import time
import uuid
from types import SimpleNamespace

from marcus.core import annotation as ann
from marcus.core.pipeline import BadResult, _check_annotate_result
from marcus.core.storage import paper_dir
from marcus.workers.annotate.handler import annotate
from marcus.workers.annotate.inputs import model_input


def _same(found: str, value: str) -> bool:
    """The text at a position matches its value under the locator's own rules."""
    for fold in (False, True):
        a = ann._normalise(found, fold)[0].strip()
        b = ann._normalise(value, fold)[0].strip()
        if a == b:
            return True
    return False


def main(argv: list[str]) -> int:
    paper_id = uuid.UUID(argv[1])
    doc = json.loads((paper_dir(paper_id) / "text.json").read_text(encoding="utf-8"))
    blocks = ann.docling_blocks(doc)
    view = SimpleNamespace(paper_id=paper_id, page=None, segment_id=None, image_job_id=None,
                           engine=None)  # fmt: skip
    start = time.monotonic()
    result = annotate(view, None)
    seconds = round(time.monotonic() - start, 1)
    problems: list[str] = []
    try:
        _check_annotate_result(result)
    except BadResult as exc:
        problems.append(f"result check: {exc}")
    for field, per_value in result["positions"].items():
        for value, hits in per_value.items():
            for block, s, e in hits:
                text = blocks[block].encode("utf-16-le")[2 * s : 2 * e].decode("utf-16-le")
                if not _same(text, value):
                    problems.append(f"{field}: {value!r} points at {text!r}")
    report = {
        "model": result["model"],
        "model_version": result["model_version"],
        "seconds": seconds,
        "model_ms": result["ms"],
        "input_chars": len(model_input(doc)),
        "text_blocks": len(blocks),
        "values": {f: v for f, v in result["output"].items() if v},
        "occurrences": {
            f: {v: len(h) for v, h in per.items()} for f, per in result["positions"].items() if per
        },
        "problems": problems,
    }
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
