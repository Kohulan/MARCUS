"""Fake annotator for the fake stack and e2e (no GPU): deterministic, from the input text.

It answers in the model's own format (one JSON object, the 11 keys, comma-separated values or
`nan`), so the parser and the locator run as with the real model. Values are picked from the
text by fixed rules, so they occur in the paper and get highlights:

    trivial_name         the first three distinct "Compound <n>"
    abbreviation         the first three distinct all-caps words of 2-5 letters (not the
                         ABSTRACT / INTRODUCTION markers)
    compound_class       the first two distinct words ending in -oids, -enes or -ones
    organism_or_species  the first "<Genus> <species>" after "from" or "of"
    organism_part        known part words (leaves, roots, bark, ...) in the text
    geo_location         known country names in the text
    Kingdom              "Plant" when an organism part was found
    every other field    nan

Refused unless fake engines are enabled. MARCUS_FAKE_ANNOTATE_DELAY_S (default 0) waits that
long per request, so the e2e runs can see the step running.
"""

import json
import os
import re
import time

from marcus.core.annotation import FIELDS

_COMPOUND = re.compile(r"\bCompound \d+\b")
_ABBREV = re.compile(r"\b[A-Z]{2,5}\b")
_CLASS = re.compile(r"\b[a-z]+(?:oids|enes|ones)\b")
_SPECIES = re.compile(r"\b(?:from|of) ([A-Z][a-z]+ [a-z]{4,})\b")
_PARTS = ("leaves", "roots", "bark", "stems", "seeds", "flowers", "fruits", "twigs")
_PLACES = ("China", "Japan", "Brazil", "India", "Germany", "Mexico", "Thailand", "Vietnam")
_MARKERS = {"ABSTRACT", "INTRODUCTION"}


def _distinct(items, limit: int) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
        if len(out) == limit:
            break
    return out


def _words(text: str, vocabulary) -> list[str]:
    return [w for w in vocabulary if re.search(rf"\b{w}\b", text)]


def fake_values(text: str) -> dict[str, list[str]]:
    values = {field: [] for field in FIELDS}
    values["trivial_name"] = _distinct(_COMPOUND.findall(text), 3)
    abbrevs = (a for a in _ABBREV.findall(text) if a not in _MARKERS)
    values["abbreviation"] = _distinct(abbrevs, 3)
    values["compound_class"] = _distinct(_CLASS.findall(text), 2)
    values["organism_or_species"] = _distinct(_SPECIES.findall(text), 1)
    values["organism_part"] = _words(text, _PARTS)
    values["geo_location"] = _words(text, _PLACES)
    values["Kingdom"] = ["Plant"] if values["organism_part"] else []
    return values


class FakeAnnotator:
    model = "fake-annotator"
    version = "fake-1"

    def __init__(self, delay_s: float | None = None):
        if delay_s is None:
            delay_s = float(os.environ.get("MARCUS_FAKE_ANNOTATE_DELAY_S", "0"))
        self.delay_s = delay_s

    def complete(self, text: str) -> str:
        if self.delay_s:
            time.sleep(self.delay_s)
        values = fake_values(text)
        obj = {field: ", ".join(values[field]) or "nan" for field in FIELDS}
        return json.dumps(obj, separators=(",", ":"))
