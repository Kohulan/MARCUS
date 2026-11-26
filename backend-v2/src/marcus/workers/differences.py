"""Where the engines' answers for one drawing differ, and what they share (Compare's
"Differences" and "Common part"; owner decision 2026-11-26). RDKit only.

Per answer (a SMILES), two lists of atom indices in the order the SMILES is written (every
written atom counts, an explicit [H] too: CDK's atom order, marcus.workers.tools.depict):

- `marks`: the atoms where the answer differs from at least one other answer, and the common
  atom where a piece another answer has would attach. Drawn orange.
- `common`: the atoms the answer shares with every other answer (the attaching atoms are
  common). `marks` minus the attaching atoms and `common` are the heavy atoms, split in two.

Two answers are compared through their largest common part (MCS: same elements, any bond
order, ring atoms on ring atoms), then atom by atom. Outside the common part an atom differs.
Inside it an atom differs when its charge or isotope differs, when a bond to another common atom
has another order or is missing in the other answer, or by stereo (an R-group placeholder is
the same atom whatever its number, DECIMER's [R1] included): a stereocentre with another
configuration, or with a configuration only one answer gives; the two atoms of a double bond
with another E/Z, or with an E/Z only one answer gives. An explicit H is no difference (it is
left out before comparing), and never an atom of either list.

A symmetric structure matches itself in several ways (a meso compound through its mirror): of
up to MAX_MAPPINGS ways the one with the fewest differences is used.

The MCS search gets PAIR_TIMEOUT_S a pair (RDKit often finds the largest common part of two
40-atom answers at once and then cannot prove it within seconds: measured on the phase-B
crops). When it runs out, the largest part found so far is used and the result says `rough`:
the marks are then right or too wide, never too narrow.
"""

import time

from rdkit import Chem
from rdkit.Chem import rdFMCS
from rdkit.rdBase import BlockLogs

from marcus.core.rgroups import rtoken_dummies, rtoken_scaffold

MAX_ANSWERS = 6
MAX_ATOMS = 250  # heavy atoms of one answer (as marcus.workers.orient)
MAX_MAPPINGS = 64
PAIR_TIMEOUT_S = 1  # RDKit's MCS timeout (whole seconds)
BUDGET_S = 3.5  # all pairs together: below the tools task's 5 s soft limit
_INDEX = "_marcus_i"  # an atom's index in the written SMILES
_SPECIFIED = (Chem.ChiralType.CHI_TETRAHEDRAL_CW, Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
_EZ = (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ)


class DifferencesError(ValueError):
    """The input cannot be compared (the tools task maps it to bad input, HTTP 422)."""


class _Answer:
    """One answer without its plain H atoms (`mol`), the same with every H as an atom (`hs`,
    heavy atoms at the same indices: a stereocentre has all its neighbours), and each atom's
    index in the written SMILES (`index`)."""

    def __init__(self, smiles: str):
        params = Chem.SmilesParserParams()
        params.removeHs = False
        with BlockLogs():
            written = Chem.MolFromSmiles(smiles, params) if smiles else None
            if written is None and smiles and rtoken_scaffold(smiles):
                # DECIMER's R tokens ([R1]): placeholder atoms, one per token, in place
                written = Chem.MolFromSmiles(rtoken_dummies(smiles), params)
        if written is None:
            raise DifferencesError("cannot read a SMILES")
        for atom in written.GetAtoms():
            atom.SetIntProp(_INDEX, atom.GetIdx())
        with BlockLogs():
            self.mol = Chem.RemoveHs(written)
            Chem.AssignStereochemistry(self.mol, cleanIt=True, force=True)
            self.hs = Chem.AddHs(self.mol)
        if self.mol.GetNumAtoms() > MAX_ATOMS:
            raise DifferencesError(f"a structure has more than {MAX_ATOMS} atoms")
        self.index = [a.GetIntProp(_INDEX) for a in self.mol.GetAtoms()]
        # every atom left: an H RDKit keeps (an isotope, [3H]) is an atom like any other
        self.heavy = list(range(self.mol.GetNumAtoms()))
        self.canonical = Chem.MolToSmiles(self.mol)


def _neighbours(mol, i: int) -> list[int]:
    """The atom's neighbours in its bond order (the order its chiral tag refers to)."""
    return [b.GetOtherAtomIdx(i) for b in mol.GetAtomWithIdx(i).GetBonds()]


def _same_centre(a: _Answer, i: int, b: _Answer, j: int, to_b: dict[int, int]) -> bool:
    """Two specified stereocentres, one mapped on the other, have the same configuration: each
    neighbour of one is put on its partner of the other (the mapped atom; else, when one is left
    on each side or one H and one other atom, those) and the parities are compared. False when
    the neighbours cannot be paired."""
    mine, theirs = _neighbours(a.hs, i), _neighbours(b.hs, j)
    if len(mine) != len(theirs):
        return False
    heavy_b = b.mol.GetNumAtoms()
    images: list[int | None] = [to_b[n] if n in to_b and to_b[n] in theirs else None for n in mine]
    left_a = [k for k, image in enumerate(images) if image is None]
    left_b = [n for n in theirs if n not in images]
    for is_h in (True, False):  # an H goes on an H, another atom on another atom
        from_a = [k for k in left_a if (a.hs.GetAtomWithIdx(mine[k]).GetAtomicNum() == 1) == is_h]
        from_b = [n for n in left_b if (b.hs.GetAtomWithIdx(n).GetAtomicNum() == 1) == is_h]
        if len(from_a) != len(from_b):
            # one H against one other atom: the two that are left
            if len(left_a) == 1 and len(left_b) == 1:
                from_a, from_b = left_a, left_b
            else:
                return False
        if len(from_a) > 1:
            # two H: no stereocentre; two other atoms nothing maps: not comparable
            if not is_h or any(n < heavy_b for n in from_b):
                return False
        for k, n in zip(from_a, from_b, strict=True):
            images[k] = n
    if any(image is None for image in images) or len(set(images)) != len(images):
        return False
    order = [theirs.index(image) for image in images]
    odd = sum(x > y for k, x in enumerate(order) for y in order[k + 1 :]) % 2 == 1
    same_tag = a.hs.GetAtomWithIdx(i).GetChiralTag() == b.hs.GetAtomWithIdx(j).GetChiralTag()
    return same_tag != odd


def _geometry(mol, bond) -> tuple[int, int, bool] | None:
    """A double bond's E/Z as (a neighbour of its begin atom, one of its end atom, the two are
    on the same side); None without one."""
    if bond.GetStereo() not in _EZ:
        return None
    refs = list(bond.GetStereoAtoms())
    if len(refs) != 2:
        return None
    return refs[0], refs[1], bond.GetStereo() == Chem.BondStereo.STEREOZ


def _same_geometry(a: _Answer, bond_a, b: _Answer, bond_b, to_b: dict[int, int]) -> bool:
    """Two double bonds with E/Z, one mapped on the other, have the same geometry. Each end's
    reference neighbour is followed through the mapping (or the end's other neighbour, which is
    on the opposite side); False when neither can be followed."""
    ga, gb = _geometry(a.mol, bond_a), _geometry(b.mol, bond_b)
    if ga is None or gb is None:
        return False
    a1, a2 = bond_a.GetBeginAtomIdx(), bond_a.GetEndAtomIdx()
    b1, b2 = to_b[a1], to_b[a2]
    ref_b1, ref_b2 = (gb[0], gb[1]) if bond_b.GetBeginAtomIdx() == b1 else (gb[1], gb[0])
    flipped = False
    for end_a, other_a, ref_a, end_b, other_b, ref_b in (
        (a1, a2, ga[0], b1, b2, ref_b1),
        (a2, a1, ga[1], b2, b1, ref_b2),
    ):
        subs_a = [n for n in _neighbours(a.mol, end_a) if n != other_a]
        subs_b = [n for n in _neighbours(b.mol, end_b) if n != other_b]
        image = to_b.get(ref_a)
        if image is not None and image in subs_b:
            flipped ^= image != ref_b
            continue
        across = next((to_b.get(n) for n in subs_a if n != ref_a), None)
        if across is not None and across in subs_b:
            flipped ^= across == ref_b
        elif len(subs_a) != 1 or len(subs_b) != 1:
            return False
    return (ga[2] != flipped) == gb[2]


def _pair(a: _Answer, b: _Answer, to_b: dict[int, int]):
    """(differing atoms of a, of b, attaching atoms of a, of b) under one mapping."""
    to_a = {j: i for i, j in to_b.items()}
    diff_a = {i for i in a.heavy if i not in to_b}
    diff_b = {j for j in b.heavy if j not in to_a}
    outside_a, outside_b = set(diff_a), set(diff_b)
    for i, j in to_b.items():
        x, y = a.mol.GetAtomWithIdx(i), b.mol.GetAtomWithIdx(j)
        specified = x.GetChiralTag() in _SPECIFIED, y.GetChiralTag() in _SPECIFIED
        if (
            x.GetFormalCharge() != y.GetFormalCharge()
            or (x.GetIsotope() != y.GetIsotope() and x.GetAtomicNum() != 0)  # not R numbers
            or specified[0] != specified[1]
            or (all(specified) and not _same_centre(a, i, b, j, to_b))
        ):
            diff_a.add(i)
            diff_b.add(j)
    for mine, theirs, mapping, diff_mine, diff_theirs, first in (
        (a, b, to_b, diff_a, diff_b, True),
        (b, a, to_a, diff_b, diff_a, False),
    ):
        for bond in mine.mol.GetBonds():
            i1, i2 = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            if i1 not in mapping or i2 not in mapping:
                continue
            other = theirs.mol.GetBondBetweenAtoms(mapping[i1], mapping[i2])
            if other is None or other.GetBondType() != bond.GetBondType():
                diff_mine.update((i1, i2))
                continue
            if not first:
                continue  # the stereo of a bond both have: once
            has = bond.GetStereo() in _EZ, other.GetStereo() in _EZ
            if has[0] != has[1] or (all(has) and not _same_geometry(a, bond, b, other, to_b)):
                diff_mine.update((i1, i2))
                diff_theirs.update((mapping[i1], mapping[i2]))
    attach_a = _attaching(a, b, to_a, outside_a, outside_b)
    attach_b = _attaching(b, a, to_b, outside_b, outside_a)
    return diff_a, diff_b, attach_a - diff_a, attach_b - diff_b


def _attaching(
    mine: _Answer, theirs: _Answer, to_mine: dict[int, int], outside_mine, outside_theirs
):
    """The common atoms of `mine` where a piece only `theirs` has would attach: not one that has
    a piece of its own there (another atom in the same place: the two atoms say it)."""
    out = set()
    for j in outside_theirs:
        for n in _neighbours(theirs.mol, j):
            i = to_mine.get(n)
            if i is not None and not any(k in outside_mine for k in _neighbours(mine.mol, i)):
                out.add(i)
    return out


def _mappings(a: _Answer, b: _Answer, deadline: float) -> tuple[list[dict[int, int]], bool]:
    """(ways to put a's common part with b on b's (atom of a -> atom of b), at most MAX_MAPPINGS,
    [{}] when they share nothing; the search ran out of time: the part may not be the largest)."""
    if time.monotonic() >= deadline:
        raise DifferencesError("differences timed out")
    with BlockLogs():
        found = rdFMCS.FindMCS(
            [a.mol, b.mol],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            bondCompare=rdFMCS.BondCompare.CompareAny,
            ringMatchesRingOnly=True,
            completeRingsOnly=False,
            matchValences=False,
            timeout=PAIR_TIMEOUT_S,
        )
    query = Chem.MolFromSmarts(found.smartsString) if found.numAtoms else None
    if query is None:
        return [{}], found.canceled
    one = a.mol.GetSubstructMatch(query, useChirality=False)
    many = b.mol.GetSubstructMatches(
        query, uniquify=False, maxMatches=MAX_MAPPINGS, useChirality=False
    )
    return [dict(zip(one, match, strict=True)) for match in many] or [{}], found.canceled


def differences(smiles: list[str]) -> dict:
    """{"marks": [[int]], "common": [[int]], "rough": bool} (module docstring), one list per
    answer. DifferencesError: fewer than 2 or more than MAX_ANSWERS answers, one RDKit cannot
    read or over MAX_ATOMS atoms, or the comparison took over BUDGET_S."""
    if not 2 <= len(smiles) <= MAX_ANSWERS:
        raise DifferencesError(f"2 to {MAX_ANSWERS} structures are compared")
    answers = [_Answer(s) for s in smiles]
    deadline = time.monotonic() + BUDGET_S
    diff = [set() for _ in answers]
    attach = [set() for _ in answers]
    rough = False
    for x, a in enumerate(answers):
        for y in range(x + 1, len(answers)):
            b = answers[y]
            if a.canonical == b.canonical:
                continue  # the same structure, stereo included
            best = None
            mappings, partial = _mappings(a, b, deadline)
            rough = rough or partial
            for to_b in mappings:
                found = _pair(a, b, to_b)
                if best is None or sum(map(len, found)) < sum(map(len, best)):
                    best = found
            diff[x] |= best[0]
            diff[y] |= best[1]
            attach[x] |= best[2]
            attach[y] |= best[3]
    marks, common = [], []
    for answer, d, at in zip(answers, diff, attach, strict=True):
        marks.append(sorted(answer.index[i] for i in d | at))
        common.append(sorted(answer.index[i] for i in answer.heavy if i not in d))
    return {"marks": marks, "common": common, "rough": rough}
