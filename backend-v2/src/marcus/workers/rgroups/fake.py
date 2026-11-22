"""Fake R-group reader for the fake stack and tests (no GPU): deterministic, from the page text.

It answers in the model's own format ({"rows": [...]}, every label in every row), so parsing,
checks and storage run as with the real model. Rows come from definitions written in the text
as `<compound>: <label> = <value>, <label> = <value>` up to a `;` or a line end (e.g.
"3a: R1 = OMe, R2 = H; 3b: R1 = H, R2 = OMe"); a label a definition does not name is "". No
definition: no rows (the model's answer for a paper that does not define its R-groups). The
image is not looked at.

Refused unless fake engines are enabled. MARCUS_FAKE_RGROUP_DELAY_S (default 0) waits that long
per request, so the e2e runs can see the step running.
"""

import json
import os
import re
import time

_ENTRY = re.compile(r"(?<![\w'-])(\d+[a-z]?'?)\s*:\s*([^;\n]*)")
_PAIR = re.compile(r"([^\s=,:]+)\s*=\s*([^,]+)")


def fake_rows(labels: list[str], context: str) -> list[dict]:
    rows: list[dict] = []
    for compound, pairs in _ENTRY.findall(context):
        found = {k: v.strip() for k, v in _PAIR.findall(pairs)}
        if not any(lab in found for lab in labels):
            continue
        rows.append({"compound": compound, "groups": {lab: found.get(lab, "") for lab in labels}})
    return rows


class FakeRgroupReader:
    model = "fake-rgroup"
    version = "fake-1"

    def __init__(self, delay_s: float | None = None):
        if delay_s is None:
            delay_s = float(os.environ.get("MARCUS_FAKE_RGROUP_DELAY_S", "0"))
        self.delay_s = delay_s

    def read(self, labels: list[str], context: str, image_uri: str) -> tuple[str, bool]:
        if self.delay_s:
            time.sleep(self.delay_s)
        rows = fake_rows(labels, context)
        return json.dumps({"rows": rows}, ensure_ascii=False, separators=(",", ":")), False
