"""The three engines' agreement on a structure, and the prediction a segment shows (phase B item 3,
owner decision 2026-11-22).

Every segment of a new paper is read by DECIMER, MolNexTR and MolScribe (the paper's engine in
its read, the other two in the background: pipeline.BACKGROUND). Two predictions agree when both
are valid and have the same InChIKey first block (connectivity; stereo may differ); an invalid
or empty one, or one RDKit gives no InChIKey, never agrees. Of each engine its newest
prediction counts. MARCUS-training review-feedback/phase-b/MEASURE.md: where 2 engines agreed
their structure was right in 60/60 crops; 3 never agreed on a wrong one (0/42).

pick_prediction is the one rule for the structure shown when nothing is curated: the card, the
stored depiction, the exports and COCONUT, and the main figure's InChIKey links all use it.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol

from marcus.core.enums import Engine

ENGINES = (Engine.DECIMER.value, Engine.MOLNEXTR.value, Engine.MOLSCRIBE.value)


class _Prediction(Protocol):
    engine: str
    valid: bool
    inchikey: str | None


def _block(p: _Prediction) -> str | None:
    """InChIKey first block of a valid prediction; None: it agrees with nothing."""
    return p.inchikey[:14] if p.valid and p.inchikey else None


def newest_by_engine(predictions: Iterable[_Prediction]) -> dict[str, _Prediction]:
    """Each of the three engines' newest prediction (`predictions` newest first)."""
    out: dict[str, _Prediction] = {}
    for p in predictions:
        if p.engine in ENGINES and p.engine not in out:
            out[p.engine] = p
    return out


def majority(predictions: Iterable[_Prediction]) -> list[_Prediction]:
    """The newest predictions of the engines that agree (two or three, in ENGINES order); [] when
    fewer than two agree. `predictions` newest first."""
    newest = newest_by_engine(predictions)
    groups: dict[str, list[_Prediction]] = {}
    for engine in ENGINES:
        p = newest.get(engine)
        key = _block(p) if p is not None else None
        if key is not None:
            groups.setdefault(key, []).append(p)
    best = max(groups.values(), key=len, default=[])
    return best if len(best) >= 2 else []


def agree_count(predictions: Iterable[_Prediction]) -> int:
    """The badge's number: 3 or 2 engines agree, 0 when they differ."""
    return len(majority(predictions))


def pick_prediction(predictions: Sequence[_Prediction], paper_engine: str):
    """The prediction shown and exported when nothing is curated (`predictions`: the segment's,
    newest first): the majority's (the paper's engine's when it is in it, else the first engine
    of it), else the newest valid one of the paper's engine, else the newest valid one; None
    without a valid one."""
    group = majority(predictions)
    if group:
        return next((p for p in group if p.engine == paper_engine), group[0])
    valid = [p for p in predictions if p.valid]
    return next((p for p in valid if p.engine == paper_engine), None) or next(iter(valid), None)


def inchikey_of(smiles: str, valid: bool) -> str | None:
    """Prediction.inchikey: the InChIKey of a valid SMILES; None when invalid, unreadable, or a
    scaffold with placeholder atoms (as marcus.api.chem.inchikey). RDKit: call it where RDKit
    may run (the planner, as an OCSR result lands)."""
    if not valid or not smiles:
        return None
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    with BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or mol.GetNumAtoms() == 0:
            return None
        if any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
            return None
        return Chem.MolToInchiKey(mol) or None
