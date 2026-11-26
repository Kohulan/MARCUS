"""The three engines' agreement on a structure, and the prediction a segment shows (phase B item 3,
owner decisions 2026-11-22 and 2026-11-26).

Every segment of a new paper is read by DECIMER, MolParser and MolScribe (the paper's engine in
its read, the other two in the background: pipeline.background_engines). Two predictions agree
when both are valid and have the same full InChIKey: the same structure, stereo included (owner
decision 2026-11-26; an explicit H is no difference, InChI normalises it; a stereocentre one
engine left open and another gave is a difference). An invalid or empty one, or one RDKit gives
no InChIKey, never agrees. Of each engine its newest prediction counts.

The badge (`badge`): "agree3" (three share the full key), "agree2" (two do), "stereo" (two or
more share the first block, the connectivity, but no two the full key), "differ". How often each
was right on hand-checked drawings: MARCUS-training review-feedback/trust-measure/MEASURE.md.

MolParser replaced MolNexTR (owner decision 2026-11-25). Old papers (kept up to the retention
limit) have MolNexTR predictions: the three counted slots are DECIMER, MolParser and MolScribe,
and a segment with no MolParser prediction counts its MolNexTR one in MolParser's slot (SLOTS),
so an old card keeps its shown structure.

pick_prediction is the one rule for the structure shown when nothing is curated: the card, the
stored depiction, the exports and COCONUT, and the main figure's InChIKey links all use it.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol

from marcus.core.enums import Engine

# The engines that read every new segment, in badge order.
ENGINES = (Engine.DECIMER.value, Engine.MOLPARSER.value, Engine.MOLSCRIBE.value)
# engine -> its slot of ENGINES; MolNexTR (legacy, old papers only) fills MolParser's slot when the
# segment has no MolParser prediction.
SLOTS = {
    Engine.DECIMER.value: Engine.DECIMER.value,
    Engine.MOLPARSER.value: Engine.MOLPARSER.value,
    Engine.MOLNEXTR.value: Engine.MOLPARSER.value,
    Engine.MOLSCRIBE.value: Engine.MOLSCRIBE.value,
}
# Every engine whose predictions or steps count (SLOTS' keys).
COUNTED = tuple(SLOTS)


class _Prediction(Protocol):
    engine: str
    valid: bool
    inchikey: str | None


def _key(p: _Prediction) -> str | None:
    """Full InChIKey of a valid prediction; None: it agrees with nothing."""
    return p.inchikey if p.valid and p.inchikey else None


def _block(p: _Prediction) -> str | None:
    """InChIKey first block (connectivity) of a valid prediction; None without a key."""
    key = _key(p)
    return key[:14] if key else None


def newest_by_engine(predictions: Iterable[_Prediction]) -> dict[str, _Prediction]:
    """Each slot's newest prediction, keyed by slot (ENGINES; `predictions` newest first): the
    slot's own engine's newest, else (MolParser's slot) the newest MolNexTR one."""
    own: dict[str, _Prediction] = {}
    legacy: dict[str, _Prediction] = {}
    for p in predictions:
        slot = SLOTS.get(p.engine)
        if slot is None:
            continue
        found = own if p.engine == slot else legacy
        found.setdefault(slot, p)
    return {e: own.get(e) or legacy[e] for e in ENGINES if e in own or e in legacy}


def _largest(predictions: Iterable[_Prediction], key) -> list[_Prediction]:
    """The largest group of slots' newest predictions with the same `key` (two or three, in
    ENGINES order); [] when no two share one."""
    newest = newest_by_engine(predictions)
    groups: dict[str, list[_Prediction]] = {}
    for engine in ENGINES:
        p = newest.get(engine)
        k = key(p) if p is not None else None
        if k is not None:
            groups.setdefault(k, []).append(p)
    best = max(groups.values(), key=len, default=[])
    return best if len(best) >= 2 else []


def majority(predictions: Iterable[_Prediction]) -> list[_Prediction]:
    """The newest predictions of the slots that agree, stereo included (two or three, in ENGINES
    order); [] when fewer than two agree. `predictions` newest first."""
    return _largest(predictions, _key)


def same_connectivity(predictions: Iterable[_Prediction]) -> list[_Prediction]:
    """As majority, by connectivity only (the InChIKey first block): stereo may differ."""
    return _largest(predictions, _block)


def badge(predictions: Iterable[_Prediction]) -> str | None:
    """The badge state: "agree3", "agree2", "stereo" or "differ" (module docstring); None with
    fewer than two newest predictions that have a key (nothing to compare)."""
    predictions = list(predictions)
    if sum(_key(p) is not None for p in newest_by_engine(predictions).values()) < 2:
        return None
    n = len(majority(predictions))
    if n >= 2:
        return f"agree{n}"
    return "stereo" if same_connectivity(predictions) else "differ"


def agree_count(predictions: Iterable[_Prediction]) -> int:
    """The badge's number: 3 or 2 engines agree, 0 when they differ."""
    return len(majority(predictions))


def pick_prediction(
    predictions: Sequence[_Prediction], paper_engine: str, frozen: object | None = None
):
    """The prediction shown and exported when nothing is curated (`predictions`: the segment's,
    newest first): the one a decision was made on (`frozen`: Curation.shown_prediction_id,
    while the segment has it), else the majority's (the paper's engine's when it is in it, else
    the first engine of it), else in the same way of the engines that share the connectivity
    (stereo differs), else the newest valid one of the paper's engine, else the newest valid
    one; None without a valid one. A decided card never changes its structure when other
    engines land later."""
    if frozen is not None:
        held = next((p for p in predictions if getattr(p, "id", None) == frozen), None)
        if held is not None:
            return held
    group = majority(predictions) or same_connectivity(predictions)
    if group:
        return next((p for p in group if p.engine == paper_engine), group[0])
    valid = [p for p in predictions if p.valid]
    return next((p for p in valid if p.engine == paper_engine), None) or next(iter(valid), None)


def shown_prediction(
    predictions: Sequence[_Prediction], paper_engine: str, frozen: object | None = None
):
    """The prediction a card shows (frontend cardState.shownPrediction): the pick
    (pick_prediction), else the newest one (none valid); None without a prediction."""
    pick = pick_prediction(predictions, paper_engine, frozen)
    if pick is not None:
        return pick
    return predictions[0] if predictions else None


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
