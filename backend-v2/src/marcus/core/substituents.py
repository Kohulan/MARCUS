"""Substituent text -> fragment with attachment points (Markush Phase 3, owner decision
2026-11-25).

An R-group row gives each label a text as the paper prints it ("OMe", "H", "CH2CH3",
"–OCH2O–"). Building the compound needs that text as a fragment: SMILES whose `*` atoms are its
attachment points (one, or two for a group that bridges two labels). The order, the first that
answers wins:

1. normalise: NFKC (subscript digits too), the dashes (− – — ‐ ‒) as "-", no spaces, no bond
   dash at either end ("- CH3", "HO-");
2. the built-in table (the values measured most often in the Phase 2 test set);
3. a condensed formula of C, H, O, N, digits, "=" and "()" ("CH2CH3", "CH(CH3)CH3"), each atom
   with exactly its full valence; a text with no parse, or two different ones, is not guessed;
4. BChemLookup (Beilstein-Institut/BChemLookup, CC0, vendored in data/bchemlookup at
   BCHEMLOOKUP_COMMIT): only entries with one or two `*` and no second component;
5. a sugar (owner decision 2026-11-26): Glc, Gal, Man, Xyl, GlcA as D-pyranoses and Rha as
   L-rhamnopyranose, every ring centre set; alpha/beta at the anomeric carbon only when the
   cell prints it ("O-β-D-Glc"), else left open for the curator. "OGlc" / "GlcO" attach at the
   anomeric oxygen, "Glc" at the anomeric carbon. A series against the sugar's own (L-Glc,
   D-Rha), a sugar whose ring size is unclear (Ara) or a chain (GlcGlc) is not built;
6. else a reason, `unknown substituent "<text>"`: never a guess ("Tig", "[drawn]"...).

A text written leftward ("AcO", "HO", "MeO") is tried as its rightward form ("OAc") too, but
never "CO" (carbonyl vs methoxy is not a mirror). Measured on the 1,479 values of the Phase 2 test
set: about 72% resolvable (MARCUS-training markush-eval). Pure: no database, RDKit only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdkit import Chem
from rdkit.rdBase import BlockLogs

BCHEMLOOKUP_COMMIT = "800d41508798df556ec26401c5db4b6a64dbba8a"
RESOLVER_VERSION = f"marcus-substituents 3; BChemLookup {BCHEMLOOKUP_COMMIT}"
DATA = Path(__file__).parent / "data" / "bchemlookup" / "abbreviations.smi"

_DASHES = dict.fromkeys(map(ord, "−–—‐‒‑"), "-")

# 2. built-in table: text -> fragment SMILES (`*` = attachment)
BUILTIN = {
    "H": "[H]*", "OH": "*O", "F": "*F", "Cl": "*Cl", "Br": "*Br", "I": "*I",
    "CH3": "*C", "Me": "*C", "OCH3": "*OC", "OMe": "*OC", "NH2": "*N", "CHO": "*C=O",
    "COOH": "*C(=O)O", "CH2OH": "*CO", "NO2": "*[N+](=O)[O-]", "CN": "*C#N", "SH": "*S",
    "Et": "*CC", "OAc": "*OC(C)=O", "Ac": "*C(C)=O",
}  # fmt: skip

_VALENCE = {"C": 4, "N": 3, "O": 2}

# Texts that name two different groups (final review, 2026-11-25): NC nitrile or isocyanide,
# OCN cyanate or isocyanate (written leftward), SCN / NCS likewise. Never built.
AMBIGUOUS = frozenset({"NC", "CNO", "ONC", "OCN", "NCO", "SCN", "NCS"})
# A bare alkyl formula (C4H9, C8H17): which isomer is not said. C1/C2 have only one.
_ALKYL_FORMULA = re.compile(r"C(\d+)H(\d+)")
# The condensed parser backtracks: a longer or branchier text is not parsed (it is never a
# simple group anyway, and it runs in the shared chem process).
MAX_CONDENSED = 30
MAX_BRANCHES = 4


@dataclass(frozen=True)
class Fragment:
    """A substituent: canonical SMILES whose `*` atoms are its attachment points."""

    smiles: str
    attachments: int


def bond_dashes(text: str) -> bool:
    """The paper printed the group with a bond dash at both ends (−OCH2O−): a bridge."""
    raw = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).translate(_DASHES))
    return len(raw) > 2 and raw.startswith("-") and raw.endswith("-")


def _ambiguous(text: str) -> bool:
    m = _ALKYL_FORMULA.fullmatch(text)
    return text in AMBIGUOUS or (m is not None and int(m.group(1)) >= 3)


def normalise(text: str) -> str:
    """NFKC, one kind of dash, no spaces, no bond dash at either end."""
    text = unicodedata.normalize("NFKC", text).translate(_DASHES)
    text = re.sub(r"\s+", "", text)
    return text.strip("-")


def _fragment(smiles: str) -> Fragment | None:
    """The canonical fragment of a SMILES with one or two `*` and one component, or None."""
    with BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1:
        return None
    stars = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 0)
    if stars not in (1, 2):
        return None
    return Fragment(Chem.MolToSmiles(mol), stars)


# --- 3. condensed formulas --------------------------------------------------------------------

_ATOM = re.compile(r"([CNO])(?:H(\d*))?")


def _parses(text: str, pos: int, first: bool):
    """Every parse of the chain at `pos` to the end of `text` (or to a closing parenthesis):
    yields (units, end) where units are [(kind, value, branches, double)]: kind "atom" with
    value (symbol, hydrogens), or "tail" with a built-in key (only last in its chain)."""
    # a built-in key that ends the chain (never the whole formula: the table answered that)
    if not first:
        rest = text[pos:]
        stop = rest.find(")")
        piece = rest if stop < 0 else rest[:stop]
        if piece in BUILTIN and piece != "H":
            yield [("tail", piece, [], False)], pos + len(piece)
    m = _ATOM.match(text, pos)
    if not m:
        return
    hydrogens = 0 if m.group(2) is None and "H" not in m.group(0) else int(m.group(2) or 1)
    atom = (m.group(1), hydrogens)
    for branches, after in _branches(text, m.end()):
        if after == len(text) or text[after] == ")":
            yield [("atom", atom, branches, False)], after
            continue
        double = text[after] == "="
        nxt = after + 1 if double else after
        for units, end in _parses(text, nxt, False):
            head, *tail = units
            yield [("atom", atom, branches, False), (head[0], head[1], head[2], double), *tail], end


def _branches(text: str, pos: int):
    """Every way to read the branches written at `pos`: yields (branches, end)."""
    yield [], pos
    if pos >= len(text) or text[pos] != "(":
        return
    for units, end in _parses(text, pos + 1, False):
        if end >= len(text) or text[end] != ")":
            continue
        m = re.match(r"\d*", text[end + 1 :])
        times = int(m.group(0)) if m.group(0) else 1
        after = end + 1 + len(m.group(0))
        for more, last in _branches(text, after):
            if more or after == last:
                yield [units] * times + more, last


def _build(units) -> str | None:
    """SMILES of the parsed chain with `*` on its first atom, or None when a valence is not
    exactly full."""
    mol = Chem.RWMol()
    star = mol.AddAtom(Chem.Atom(0))
    bonds_of: dict[int, int] = {}
    want: dict[int, int] = {}

    def add_chain(chain, parent: int) -> bool:
        prev = parent
        for kind, value, branches, double in chain:
            order = Chem.BondType.DOUBLE if double else Chem.BondType.SINGLE
            if kind == "tail":
                frag = Chem.MolFromSmiles(BUILTIN[value])
                if frag is None:
                    return False
                offset = mol.GetNumAtoms()
                for a in frag.GetAtoms():
                    mol.AddAtom(Chem.Atom(a.GetAtomicNum()) if a.GetAtomicNum() else Chem.Atom(0))
                    new = mol.GetAtomWithIdx(offset + a.GetIdx())
                    new.SetFormalCharge(a.GetFormalCharge())
                for b in frag.GetBonds():
                    mol.AddBond(
                        offset + b.GetBeginAtomIdx(), offset + b.GetEndAtomIdx(), b.GetBondType()
                    )
                (dummy,) = [offset + a.GetIdx() for a in frag.GetAtoms() if a.GetAtomicNum() == 0]
                (joint,) = [n.GetIdx() for n in mol.GetAtomWithIdx(dummy).GetNeighbors()]
                mol.RemoveBond(dummy, joint)
                mol.AddBond(prev, joint, order)
                bonds_of[prev] = bonds_of.get(prev, 0) + (2 if double else 1)
                mol.GetAtomWithIdx(dummy).SetAtomicNum(0)
                mol.GetAtomWithIdx(dummy).SetProp("_drop", "1")
                return True
            symbol, hydrogens = value
            idx = mol.AddAtom(Chem.Atom(symbol))
            atom = mol.GetAtomWithIdx(idx)
            atom.SetNumExplicitHs(hydrogens)
            atom.SetNoImplicit(True)
            want[idx] = _VALENCE[symbol] - hydrogens
            mol.AddBond(prev, idx, order)
            step = 2 if double else 1
            bonds_of[idx] = bonds_of.get(idx, 0) + step
            if prev != star:
                bonds_of[prev] = bonds_of.get(prev, 0) + step
            for branch in branches:
                if not add_chain(branch, idx):
                    return False
            prev = idx
        return True

    if not add_chain(units, star):
        return None
    if any(bonds_of.get(i, 0) != n for i, n in want.items()):
        return None
    for a in sorted((a.GetIdx() for a in mol.GetAtoms() if a.HasProp("_drop")), reverse=True):
        mol.RemoveAtom(a)
    try:
        with BlockLogs():
            Chem.SanitizeMol(mol)
    except Exception:  # noqa: BLE001 - not a structure: no parse
        return None
    return Chem.MolToSmiles(mol)


def parse_condensed(text: str) -> str | None:
    """The fragment SMILES (`*` first) of a condensed formula with exactly one reading, else
    None (no reading, or two different ones: never guessed)."""
    if not text or not re.fullmatch(r"[CHNO0-9=()a-zA-Z]+", text):
        return None
    if len(text) > MAX_CONDENSED or text.count("(") > MAX_BRANCHES:
        return None
    results = set()
    for units, end in _parses(text, 0, True):
        if end != len(text):
            continue
        smiles = _build(units)
        if smiles is not None:
            results.add(smiles)
    return results.pop() if len(results) == 1 else None


# --- 4. BChemLookup ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def bchemlookup() -> dict[str, str]:
    """Normalised abbreviation -> fragment SMILES, from the vendored CC0 file. Kept: entries that
    are one component with one or two `*`. A key with two different structures is dropped."""
    found: dict[str, set[str]] = {}
    for line in DATA.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        key, smiles = (part.strip() for part in line.split("\t")[:2])
        frag = _fragment(smiles) if key and smiles else None
        if frag is not None:
            found.setdefault(normalise(key), set()).add(frag.smiles)
    return {k: v.pop() for k, v in found.items() if len(v) == 1}


# --- 5. sugars ---------------------------------------------------------------------------------

# name -> (free pyranose SMILES from PubChem, its series, its anomer as written there). PubChem
# CIDs: 64689 beta-D-glucose, 439353 beta-D-galactopyranose, 439680 beta-D-mannopyranose,
# 125409 beta-D-xylopyranose, 439710 alpha-L-rhamnose, 441478 beta-D-glucopyranuronic acid.
SUGARS = {
    "Glc": ("C([C@@H]1[C@H]([C@@H]([C@H]([C@@H](O1)O)O)O)O)O", "D", "β"),
    "Gal": ("C([C@@H]1[C@@H]([C@@H]([C@H]([C@@H](O1)O)O)O)O)O", "D", "β"),
    "Man": ("C([C@@H]1[C@H]([C@@H]([C@@H]([C@@H](O1)O)O)O)O)O", "D", "β"),
    "Xyl": ("C1[C@H]([C@@H]([C@H]([C@@H](O1)O)O)O)O", "D", "β"),
    "Rha": ("C[C@H]1[C@@H]([C@H]([C@H]([C@@H](O1)O)O)O)O", "L", "α"),
    "GlcA": ("[C@@H]1([C@@H]([C@H](O[C@H]([C@@H]1O)O)C(=O)O)O)O", "D", "β"),
}
# [O-][α|β-][D|L-]Name[p][-O]: the cell's text after normalise (no spaces, one kind of dash).
_SUGAR = re.compile(
    r"(?:(?P<pre>[αβ])-?)?(?P<o1>O-?)?(?:(?P<anomer>[αβ])-?)?(?:(?P<series>[DL])-?)?"
    r"(?P<name>GlcA|Glc|Gal|Man|Xyl|Rha)p?(?P<o2>-?O)?"
)


def _anomeric(mol: Chem.Mol) -> tuple[int, int]:
    """(anomeric carbon, its exocyclic oxygen) of a free pyranose: the ring carbon next to the
    ring oxygen that carries an OH."""
    ring_o = next(a for a in mol.GetAtoms() if a.GetSymbol() == "O" and a.IsInRing())
    for c in ring_o.GetNeighbors():
        for o in c.GetNeighbors():
            if o.GetSymbol() == "O" and not o.IsInRing() and o.GetTotalNumHs() == 1:
                return c.GetIdx(), o.GetIdx()
    raise ValueError("no anomeric OH")


def _sugar(text: str) -> Fragment | None:
    """The fragment of a sugar text (section 5 of the module doc), or None."""
    m = _SUGAR.fullmatch(text)
    if m is None or (m["o1"] and m["o2"]) or (m["pre"] and m["anomer"]):
        return None
    anomer = m["pre"] or m["anomer"]
    smiles, series, written = SUGARS[m["name"]]
    if m["series"] and m["series"] != series:
        return None  # L-glucose, D-rhamnose: not the sugar the table holds
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    c, o = _anomeric(mol)
    carbon = mol.GetAtomWithIdx(c)
    if anomer is None:
        carbon.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
    elif anomer != written:
        carbon.InvertChirality()
    if m["o1"] or m["o2"]:  # attached at the anomeric oxygen (a glycoside)
        star = mol.AddAtom(Chem.Atom(0))
        mol.AddBond(o, star, Chem.BondType.SINGLE)
        mol.GetAtomWithIdx(o).SetNoImplicit(False)
    else:  # the glycosyl itself: the anomeric oxygen's place is the attachment
        mol.ReplaceAtom(o, Chem.Atom(0))
    out = mol.GetMol()
    Chem.SanitizeMol(out)
    return _fragment(Chem.MolToSmiles(out))


# --- resolve ----------------------------------------------------------------------------------


def _mirrored(text: str) -> str | None:
    """ "AcO" -> "OAc", "HO" -> "OH": a leftward group written with its O last; never "CO"."""
    if len(text) < 2 or not text.endswith("O") or text[:-1] == "C" or "O" in text[:-1]:
        return None  # never "CO" (carbonyl), never "OCO" -> "OOC" (a carboxylate)
    mirror = "O" + text[:-1]
    return mirror if mirror in BUILTIN or mirror in bchemlookup() else None


def _one(text: str) -> Fragment | None:
    if _ambiguous(text):
        return None
    if text in BUILTIN:
        return _fragment(BUILTIN[text])
    condensed = parse_condensed(text)
    if condensed is not None:
        return _fragment(condensed)
    if text in bchemlookup():
        return _fragment(bchemlookup()[text])
    return _sugar(text)


def resolve(text: str) -> Fragment | str:
    """The fragment of a substituent text, or the reason it has none."""
    norm = normalise(text)
    for candidate in (norm, _mirrored(norm)):
        if candidate:
            frag = _one(candidate)
            if frag is not None:
                return frag
    return f'unknown substituent "{text}"'
