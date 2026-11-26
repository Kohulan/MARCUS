"""The tools task `paper_view`: an image's answers on its paper layout (marcus.core.paper_layout).

For each answer (a SMILES, atoms in SMILES order as CDK and marcus.workers.orient read it):

- `atoms` / `bonds`: every atom at the layout's pixels (x right, y DOWN, the image's own), the
  common part with the layout placed there and the rest laid out by RDKit around it
  (orient.oriented), each atom with whether it was placed; null when the answer cannot follow
  the layout (too little in common, or a double bond the layout would draw against the answer's
  own E/Z). Never a made-up place.
- `marks`: the atoms where the answer differs from the OTHER answers (`differences`).

With them the layout's `fit`, `bond`, `width` and `height`, and `overlay`: the fit is good enough
to draw over the image (paper_layout.OVERLAY_MAX_FIT_SHARE); the API refuses the overlay
otherwise.

`differences` is the SIMPLE rule (no stereo): per pair of different answers, the largest common
part by element and connection (any bond order, rings match rings); of its embeddings the one
with the fewest bonds of different order. Marked in an answer are then
  - its atoms outside the common part,
  - the common atom where an atom outside it attaches, in BOTH answers (an answer that LACKS a
    group has no atom of its own to mark: the place it is missing from is marked),
  - both ends of a bond that the other answer has with another order or not at all,
  - an atom whose charge differs.
An answer's marks are the union over the other answers. Two stereoisomers have no marks here.
The trust-agreement branch (docs/superpowers/specs/2026-11-26-trust-agreement-design.md) owns
the stereo-aware differences and the Compare switch: it can replace `differences` (same
signature: SMILES in, per answer a sorted list of atom indices or None, and whether every pair
was compared) without touching the rest.

Time: every MCS search of one call (up to MAX_ANSWERS layout searches and their pairs) draws on
ONE budget of VIEW_BUDGET_S seconds, under the tools tasks' 5 s soft limit. RDKit's timeout is in
whole seconds, so a search starts only with a whole second left and gets what is left (at most
orient.MCS_TIMEOUT_S); a search skipped or stopped by its timeout gives no marks or geometry,
and `complete` is false. Identical SMILES are one answer.
"""

import time
from itertools import combinations

from rdkit import Chem
from rdkit.Chem import rdFMCS
from rdkit.rdBase import BlockLogs

from marcus.core import paper_layout
from marcus.workers import orient
from marcus.workers.tool_errors import ToolInputError

MAX_ANSWERS = 6  # the engines of one image (Compare shows up to four)
VIEW_BUDGET_S = 3
MAX_EMBEDDINGS = 64  # of the common part in the second answer, to pick the closest one
MAX_SMILES = 2000  # = marcus.api.tooling.MAX_SMILES


class _Budget:
    """Whole seconds left for the next MCS search; 0 when none can start."""

    def __init__(self, seconds: float = VIEW_BUDGET_S):
        self.deadline = time.monotonic() + seconds
        self.complete = True

    def take(self) -> int:
        left = int(self.deadline - time.monotonic())
        if left < 1:
            self.complete = False
            return 0
        return min(left, orient.MCS_TIMEOUT_S)


def _pair(a, b, timeout: int) -> tuple[set[int], set[int]] | None:
    """The atoms of `a` and of `b` where the two differ; None when the search ran out of time."""
    with BlockLogs():
        result = rdFMCS.FindMCS(
            [a, b],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            bondCompare=rdFMCS.BondCompare.CompareAny,
            ringMatchesRingOnly=True,
            completeRingsOnly=False,
            timeout=timeout,
        )
    if result.canceled:
        return None
    heavy_a = {x.GetIdx() for x in a.GetAtoms() if x.GetAtomicNum() != 1}
    heavy_b = {x.GetIdx() for x in b.GetAtoms() if x.GetAtomicNum() != 1}
    query = Chem.MolFromSmarts(result.smartsString) if result.numAtoms else None
    on_a = a.GetSubstructMatch(query) if query is not None else ()
    if not on_a:
        return heavy_a, heavy_b  # nothing in common
    best: tuple[int, tuple[int, ...]] | None = None
    for on_b in b.GetSubstructMatches(query, uniquify=False, maxMatches=MAX_EMBEDDINGS):
        wrong = len(_other_bonds(a, b, on_a, on_b))
        if best is None or wrong < best[0]:
            best = (wrong, on_b)
        if wrong == 0:
            break
    if best is None:
        return heavy_a, heavy_b
    on_b = best[1]
    outside_a, outside_b = heavy_a - set(on_a), heavy_b - set(on_b)
    spots = set(_other_bonds(a, b, on_a, on_b))
    for k, (i, j) in enumerate(zip(on_a, on_b, strict=True)):
        atom_a, atom_b = a.GetAtomWithIdx(i), b.GetAtomWithIdx(j)
        if (
            any(n.GetIdx() in outside_a for n in atom_a.GetNeighbors())
            or any(n.GetIdx() in outside_b for n in atom_b.GetNeighbors())
            or atom_a.GetFormalCharge() != atom_b.GetFormalCharge()
        ):
            spots.add(k)
    return outside_a | {on_a[k] for k in spots}, outside_b | {on_b[k] for k in spots}


def _other_bonds(a, b, on_a, on_b) -> list[int]:
    """The positions in the common part of both ends of every bond between common atoms that
    the other molecule has with another order or not at all (an end once per such bond)."""
    found = []
    spot_a = {atom: k for k, atom in enumerate(on_a)}
    spot_b = {atom: k for k, atom in enumerate(on_b)}
    for mol, other, spot, on_other in ((a, b, spot_a, on_b), (b, a, spot_b, on_a)):
        for bond in mol.GetBonds():
            p, q = spot.get(bond.GetBeginAtomIdx()), spot.get(bond.GetEndAtomIdx())
            if p is None or q is None:
                continue
            twin = other.GetBondBetweenAtoms(on_other[p], on_other[q])
            if twin is None or twin.GetBondType() != bond.GetBondType():
                found += [p, q]
    return found


def _differences(smiles: list[str], budget: _Budget) -> list[list[int] | None]:
    mols = {s: orient._structure(s) for s in dict.fromkeys(smiles)}
    marks: dict[str, set[int]] = {s: set() for s, m in mols.items() if m is not None}
    for s, t in combinations(marks, 2):  # identical SMILES are one key: never compared
        timeout = budget.take()
        if not timeout:
            continue
        found = _pair(mols[s], mols[t], timeout)
        if found is None:
            budget.complete = False
            continue
        marks[s] |= found[0]
        marks[t] |= found[1]
    return [sorted(marks[s]) if s in marks else None for s in smiles]


def differences(smiles: list[str]) -> tuple[list[list[int] | None], bool]:
    """(per answer the atoms where it differs from the other answers, in SMILES order; None for
    an answer RDKit cannot read), and whether every pair was compared within the time."""
    budget = _Budget()
    return _differences(smiles, budget), budget.complete


def _geometry(smiles: str, layout: str, budget: _Budget) -> dict:
    """{"atoms": [[x, y, symbol, placed]], "bonds": [[atom, atom, order]]} of one answer at the
    layout's pixels (y down), both None when it cannot follow the layout."""
    none = {"atoms": None, "bonds": None}
    timeout = budget.take()
    if not timeout:
        return none
    found = orient.oriented(smiles, layout, timeout)
    mol = orient._structure(smiles)
    if found is None or mol is None or len(found.coords) != mol.GetNumAtoms():
        return none
    atoms = [
        [
            round(x / found.scale, 1),
            round(-y / found.scale, 1),
            mol.GetAtomWithIdx(i).GetSymbol(),
            i in found.placed,
        ]
        for i, (x, y) in enumerate(found.coords)
    ]
    bonds = [
        [b.GetBeginAtomIdx(), b.GetEndAtomIdx(), _order(b.GetBondTypeAsDouble())]
        for b in mol.GetBonds()
    ]
    return {"atoms": atoms, "bonds": bonds}


def _order(value: float) -> float | int:
    return int(value) if value == int(value) else value


def paper_view(smiles: list[str], layout: str) -> dict:
    """See the module docstring. ToolInputError for anything but 1..MAX_ANSWERS SMILES and a
    paper layout."""
    info = paper_layout.info(layout) if isinstance(layout, str) else None
    if info is None:
        raise ToolInputError("not a paper layout")
    if (
        not isinstance(smiles, list)
        or not 1 <= len(smiles) <= MAX_ANSWERS
        or not all(isinstance(s, str) and 0 < len(s) <= MAX_SMILES for s in smiles)
    ):
        raise ToolInputError(f"1 to {MAX_ANSWERS} SMILES are required")
    budget = _Budget()
    readable = {s: orient._structure(s) is not None for s in dict.fromkeys(smiles)}
    geometry = {s: _geometry(s, layout, budget) for s, ok in readable.items() if ok}
    marks = _differences(smiles, budget)
    return {
        "fit": info.fit,
        "bond": info.bond,
        "width": info.width,
        "height": info.height,
        "overlay": info.overlay_ok,
        "complete": budget.complete,
        "answers": [
            {"marks": marks[i], **geometry[s]} if readable[s] else None
            for i, s in enumerate(smiles)
        ],
    }
