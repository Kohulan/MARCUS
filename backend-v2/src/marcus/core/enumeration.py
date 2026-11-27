"""Scaffold + R-group row -> the full molecule (Markush Phase 3, owner decision 2026-11-25).

A scaffold (the structure a card shows, with R-group placeholder atoms) and one row of its
R-group table ({"compound": "20d", "groups": {"R1": "H", "R2": "–OCH2O–", "R3": ""}}) give the
compound: each labelled placeholder is replaced by its group's fragment
(marcus.core.substituents) with RDKit's molzip; "H" removes the placeholder. A two-point group
(–OCH2O–) bridges two labels only when the table printed it once across both (the other label
empty), the labels are neighbours in label order and their atoms are bonded (ortho), and the
group is symmetric. Anything unsure fails the row with a short reason (shown to the user as
"Could not build"): a placeholder without a label, a label that carries more than a label
("OR1"), a placeholder on more than one bond (inside a ring), a missing or extra group, an
unknown substituent. Never a guess: a wrong molecule is worse than none.

A point labelled with a known group as drawn ("OMe") is that group in every row.

Pure: no database. `build_rows` runs in the API's chem process (marcus.api.chempool).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.rdBase import BlockLogs

from marcus.core.rgroup_labels import UNLABELLED, as_label
from marcus.core.rgroups import _R_TOKEN, _label_order, _token_label, dummy_labels
from marcus.core.substituents import Fragment, bond_dashes, resolve

NO_COMPOUND = "no compound ID"
TWICE = 'compound "{}" is in two rows'
NO_VALUE = "no value for {}"
NOT_IN_SCAFFOLD = "the scaffold has no {}"
UNLABELLED_POINT = "unlabelled point in the scaffold"
NOT_A_LABEL = 'scaffold label "{}" is not a bare label'
NOT_ONE_BOND = "scaffold label {} is not on one bond"
BRIDGE = '"{}" joins two groups that are not side by side'
NOT_READ = "the scaffold could not be read"
NOT_VALID = "the result is not a valid structure"
NO_POINTS = "the scaffold has no R-group points"
MISREAD_LABEL = 'the scaffold has "{}": a misread label? Edit the structure first'
# Element symbols an R-group label becomes when an engine misreads it ("R1" -> [Rf] rutherfordium,
# MolScribe on BJOC 18/23; "Y" -> yttrium): never copied into a build. Metals and counter-ions a
# real structure has (Na, Mg, Fe, Co...) are not in it.
MISREAD_ELEMENTS = frozenset({"Ra", "Rb", "Re", "Rf", "Rg", "Rh", "Rn", "Ru", "Y"})

_TOKEN_MAP = 900  # atom map numbers of DECIMER's R tokens while the scaffold is read


@dataclass(frozen=True)
class Scaffold:
    """The scaffold with each dummy atom's map number set (1..k, isotopes cleared) and its raw
    label by atom index."""

    mol: Chem.Mol
    labels: dict[int, str]


def _bare_r(atom: Chem.Atom) -> bool:
    """A molfile dummy whose only label is its atom symbol: RDKit writes an unlabelled `*` as
    "R", so "R" with no alias, no R# number, no isotope and no map number is no drawn label."""
    return not (
        atom.HasProp("molFileAlias")
        or atom.HasProp("_MolFileRLabel")
        or atom.GetIsotope()
        or atom.GetAtomMapNum()
    )


def _read(smiles: str | None, molfile: str | None) -> tuple[Chem.Mol | None, dict[int, str]]:
    """The scaffold molecule and the labels it carries outside the atoms' own (atom index ->
    label): DECIMER's R tokens, and a molfile's unlabelled points."""
    with BlockLogs():
        if molfile:
            mol = Chem.MolFromMolBlock(molfile)
            if mol is not None:
                return mol, {a.GetIdx(): UNLABELLED for a in mol.GetAtoms()
                             if a.GetAtomicNum() == 0 and _bare_r(a)}  # fmt: skip
        if not smiles:
            return None, {}
        core = smiles.split(maxsplit=1)[0]
        mol = Chem.MolFromSmiles(core)
        if mol is not None:
            return mol, {}
        tokens = list(_R_TOKEN.finditer(core))
        if not tokens:
            return None, {}
        it = iter(range(len(tokens)))
        replaced = _R_TOKEN.sub(lambda m: f"[*:{_TOKEN_MAP + next(it)}]", core)
        mol = Chem.MolFromSmiles(replaced)
        if mol is None:
            return None, {}
        by_map = {_TOKEN_MAP + i: _token_label(t) for i, t in enumerate(tokens)}
        return mol, {a.GetIdx(): by_map[a.GetAtomMapNum()] for a in mol.GetAtoms()
                     if a.GetAtomMapNum() in by_map}  # fmt: skip


def scaffold_of(smiles: str | None, molfile: str | None) -> Scaffold | str:
    """The scaffold from the molfile (its labelled dummies win), else from the SMILES (DECIMER's
    [R1] tokens read as labelled dummies); NOT_READ when RDKit reads neither, MISREAD_LABEL when
    it holds an element a misread R label makes."""
    found = _scaffold(smiles, molfile)
    if isinstance(found, str):
        return found
    if odd := next((a.GetSymbol() for a in found.mol.GetAtoms()
                    if a.GetSymbol() in MISREAD_ELEMENTS), None):  # fmt: skip
        return MISREAD_LABEL.format(odd)
    return found


def scaffold_core(smiles: str | None, molfile: str | None) -> str | None:
    """What a reading of a scaffold says outside its R-group points, as one canonical SMILES
    (no stereo): every R point (and an element a misread label makes, [Rf]) a plain `*`, every
    point labelled with a known group as drawn ("OMe", "GlcO") that group. Two readings with one
    core differ only in their R points, so Build may take one for the other (owner, 2026-11-27:
    DECIMER read the drawn GlcO of BJOC 18/23 as OMe; its core differs). None when unreadable."""
    found = _scaffold(smiles, molfile)
    if isinstance(found, str):
        return None
    mol = Chem.RWMol(found.mol)
    pieces = Chem.Mol()
    for idx, lab in found.labels.items():
        atom = mol.GetAtomWithIdx(idx)
        if lab != UNLABELLED and as_label(lab) != lab:
            frag = resolve(lab)
            if isinstance(frag, str) or frag.attachments != 1:
                return None
            piece = Chem.RWMol(Chem.MolFromSmiles(frag.smiles))
            star = next(a for a in piece.GetAtoms() if a.GetAtomicNum() == 0)
            star.SetAtomMapNum(atom.GetAtomMapNum())
            pieces = Chem.CombineMols(pieces, piece)
        else:
            atom.SetAtomMapNum(0)
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in MISREAD_ELEMENTS:
            atom.SetAtomicNum(0)
            atom.SetNoImplicit(True)
    try:
        with BlockLogs():
            out = Chem.molzip(mol, pieces) if pieces.GetNumAtoms() else mol.GetMol()
            for atom in out.GetAtoms():
                if atom.GetAtomicNum() == 0:
                    atom.SetIsotope(0)
                    atom.SetAtomMapNum(0)
                    for prop in ("molFileAlias", "_MolFileRLabel", "dummyLabel"):
                        if atom.HasProp(prop):
                            atom.ClearProp(prop)
            out = Chem.RemoveHs(out, sanitize=False)
            return Chem.MolToSmiles(out, isomericSmiles=False)
    except Exception:  # noqa: BLE001 - RDKit refused it: no core to compare
        return None


def _scaffold(smiles: str | None, molfile: str | None) -> Scaffold | str:
    """scaffold_of without the misread-element guard."""
    mol, tokens = _read(smiles, molfile)
    if mol is None:
        return NOT_READ
    mol = Chem.RWMol(mol)
    for a in mol.GetAtoms():
        if a.GetAtomicNum() != 0:
            a.SetAtomMapNum(0)
    labels: dict[int, str] = {}
    for n, (idx, raw) in enumerate(dummy_labels(mol), start=1):
        labels[idx] = tokens.get(idx, raw)
        atom = mol.GetAtomWithIdx(idx)
        atom.SetIsotope(0)
        atom.SetAtomMapNum(n)
    return Scaffold(mol.GetMol(), labels)


def _symmetric(frag: Chem.Mol) -> bool:
    ranks = list(Chem.CanonicalRankAtoms(frag, breakTies=False))
    stars = [ranks[a.GetIdx()] for a in frag.GetAtoms() if a.GetAtomicNum() == 0]
    return len(stars) == 2 and stars[0] == stars[1]


def build_row(scaffold: Scaffold, groups: dict[str, str]) -> tuple[str, str] | str:
    """(canonical SMILES, InChIKey) of the compound, or the reason it is not built."""
    mol = scaffold.mol
    raw = scaffold.labels
    if not raw:
        return NO_POINTS
    if any(lab == UNLABELLED for lab in raw.values()):
        return UNLABELLED_POINT
    # a point labelled with a known group as drawn ("OMe": MolScribe keeps a drawn abbreviation
    # as a labelled point) is that group in every row; any other text is no bare label ("OR1")
    fixed: dict[str, Fragment] = {}
    for lab in set(raw.values()):
        if as_label(lab) != lab:
            frag = resolve(lab)
            if isinstance(frag, str) or frag.attachments != 1:
                return NOT_A_LABEL.format(lab)
            fixed[lab] = frag
    for idx, lab in raw.items():
        atom = mol.GetAtomWithIdx(idx)
        if atom.GetDegree() != 1 or atom.GetBonds()[0].GetBondType() != Chem.BondType.SINGLE:
            return NOT_ONE_BOND.format(lab)
    order = sorted({lab for lab in raw.values() if lab not in fixed}, key=_label_order)
    if not order:
        return NO_POINTS
    values = {str(k).strip(): str(v or "").strip() for k, v in groups.items()}
    # a label the row leaves out counts as empty: only a bridge may take it (else NO_VALUE below)
    for lab in order:
        values.setdefault(lab, "")
    for k, v in values.items():
        if v and k not in order:
            return NOT_IN_SCAFFOLD.format(k)
    frags: dict[str, Fragment] = {}
    for lab in order:
        if values[lab]:
            frag = resolve(values[lab])
            if isinstance(frag, str):
                return frag
            frags[lab] = frag
    atoms_of = {lab: [i for i, x in raw.items() if x == lab] for lab in order}
    empty = [lab for lab in order if not values[lab]]
    partner: dict[str, str] = {}
    for lab, frag in frags.items():
        if frag.attachments != 2:
            continue
        free = [b for b in empty if b not in partner.values()]
        # only a group printed as a bridge (−OCH2O−) spans two labels: "CH2" is no bridge
        ok = bond_dashes(values[lab]) and len(free) == 1
        ok = ok and abs(order.index(free[0]) - order.index(lab)) == 1
        if ok:
            b = free[0]
            ok = len(atoms_of[lab]) == 1 and len(atoms_of[b]) == 1
        if ok:
            na = mol.GetAtomWithIdx(atoms_of[lab][0]).GetNeighbors()[0].GetIdx()
            nb = mol.GetAtomWithIdx(atoms_of[b][0]).GetNeighbors()[0].GetIdx()
            ok = mol.GetBondBetweenAtoms(na, nb) is not None
        if ok:
            ok = _symmetric(Chem.MolFromSmiles(frag.smiles))
        if not ok:
            return BRIDGE.format(values[lab])
        partner[lab] = b
    for lab in empty:
        if lab not in partner.values():
            return NO_VALUE.format(lab)
    pieces = Chem.Mol()
    quiet = BlockLogs()  # "[H]*" warns that its H has a dummy neighbour: expected here
    for lab, frag in fixed.items():
        frags[lab] = frag
        atoms_of[lab] = [i for i, x in raw.items() if x == lab]
    for lab, frag in frags.items():
        targets = (
            [[atoms_of[lab][0], atoms_of[partner[lab]][0]]]
            if lab in partner
            else [[i] for i in atoms_of[lab]]
        )
        for points in targets:
            piece = Chem.RWMol(Chem.MolFromSmiles(frag.smiles))
            stars = [a for a in piece.GetAtoms() if a.GetAtomicNum() == 0]
            for star, idx in zip(stars, points, strict=True):
                star.SetAtomMapNum(mol.GetAtomWithIdx(idx).GetAtomMapNum())
            pieces = Chem.CombineMols(pieces, piece)
    del quiet
    try:
        with BlockLogs():
            out = Chem.molzip(mol, pieces)
            out = Chem.RemoveHs(out)
            Chem.SanitizeMol(out)
            # a stereo tag on an atom that lost its centre (R = H) goes
            Chem.AssignStereochemistry(out, cleanIt=True, force=True)
            if any(a.GetAtomicNum() == 0 for a in out.GetAtoms()):
                return NOT_VALID
            for a in out.GetAtoms():
                a.SetAtomMapNum(0)
            smiles = Chem.MolToSmiles(out)
            inchikey = Chem.MolToInchiKey(out)
    except Exception:  # noqa: BLE001 - RDKit refused the result: not built
        return NOT_VALID
    return (smiles, inchikey) if inchikey else NOT_VALID


def build_rows(smiles: str | None, molfile: str | None, rows: list[dict]) -> list[dict]:
    """Every row of the scaffold's table, in order: {"compound", "groups", "smiles",
    "inchikey"} when built, {"compound", "groups", "reason"} when not."""
    compounds = [str(r.get("compound") or "").strip() for r in rows]
    seen: dict[str, int] = {}
    for c in compounds:
        seen[c] = seen.get(c, 0) + 1
    scaffold = scaffold_of(smiles, molfile)
    out = []
    for row, compound in zip(rows, compounds, strict=True):
        groups = row.get("groups") or {}
        base = {"compound": compound, "groups": groups}
        if not compound:
            out.append({**base, "reason": NO_COMPOUND})
        elif seen[compound] > 1:
            out.append({**base, "reason": TWICE.format(compound)})
        elif isinstance(scaffold, str):
            out.append({**base, "reason": scaffold})
        else:
            result = build_row(scaffold, groups)
            if isinstance(result, str):
                out.append({**base, "reason": result})
            else:
                out.append({**base, "smiles": result[0], "inchikey": result[1]})
    return out


__all__ = [
    "BRIDGE", "NOT_A_LABEL", "NOT_IN_SCAFFOLD", "NOT_ONE_BOND", "NOT_READ", "NOT_VALID",
    "NO_COMPOUND", "NO_VALUE", "TWICE", "UNLABELLED_POINT", "Scaffold", "build_row",
    "build_rows", "scaffold_of",
]  # fmt: skip
