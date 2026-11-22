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

MolScribe keeps the linking O in an alias (OR, OR3, R2O, RaO): the label is the R-group in it.
"""

import re

_R = r"R[′″']*(?:\d{1,2})?[a-z]?[′″']*"
_OTHER = r"[XYZ](?:\d{1,2})?[′″']*|Ar(?:\d{1,2})?|[nmQ]|\*"
_LABEL = re.compile(rf"(?:{_R}|{_OTHER})")
_O_LINKED = re.compile(rf"O({_R})|({_R})O")


def as_label(text: str) -> str | None:
    """`text` as an R-group label (an O-linked R-group as its R-group), or None when it has not
    the form of one."""
    text = text.strip()
    if _LABEL.fullmatch(text):
        return text
    m = _O_LINKED.fullmatch(text)
    if m:
        return m.group(1) or m.group(2)
    return None
