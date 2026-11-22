"""R-group (Markush) placeholders in an engine's or a curator's structure: the labels, or none.

A drawing with R1, X, Ar... stands for several compounds, not one. What the engines emit for one
(MARKUSH-RESEARCH.md section 2.4):

- MolScribe and MolNexTR: a dummy atom (atomic number 0), `*` or `[1*]` in the SMILES, with the
  drawn label kept as the atom's alias in the molfile (`A  1` / `R1`). Ketcher writes `R#` atoms
  with an `M  RGP` line. RDKit reads all of them as atomic number 0.
- DECIMER: bracket tokens `[R]`, `[R1]`, `[R']`, `[X]`, `[Z1]`... that RDKit cannot parse, so
  the prediction is invalid. Such a SMILES counts as an R-group scaffold only when it parses
  with every token replaced by a dummy atom: then the R tokens are the only reason it failed.
  `[Y]` alone is yttrium (a valid element, and real organometallics contain it): it counts as
  an R token only next to another R token in a SMILES that RDKit cannot parse.

Labels: the molfile alias (R1, X, Ar...), else Ketcher's R-group number (R1), else `R` + the
isotope or atom-map number, else the dummy's own label when it is not `*`, else `*`. Only a label
with the form of one counts (marcus.core.rgroup_labels: not OAc, MeO, 555...; R2O is R2); a
molfile whose aliases are all no labels is a placeholder `*` only while its SMILES keeps the
wildcard. Sorted (R, R', R1, R2, R10, X, ...; `*` last), each once.

Cheap first: `rgroup_labels` scans the strings, and only a SMILES with `*` or an R token, or a
molfile with an atom that is no element, is parsed with RDKit. Called where RDKit may run (the
OCSR result in the worker, the curation route through marcus.api.chempool, the export, the
0011 backfill), never on the API's event loop.
"""

import re
from functools import lru_cache

from rdkit import Chem
from rdkit.rdBase import BlockLogs

from marcus.core.rgroup_labels import UNLABELLED, as_label

# SMILES: a dummy atom is `*`, bare or in brackets ([*], [1*], [*:1]); nothing else in SMILES
# uses `*` (a CXSMILES extension starts after whitespace and is cut off first).
_SMILES_DUMMY = re.compile(r"\[(\d*)\*(?::(\d+))?\]|\*")
# DECIMER's R tokens: R, X, Y, Z with an optional index, R also with primes.
_R_TOKEN = re.compile(r"\[(R)(\d*)('*)\]|\[([XYZ])(\d*)\]")
_CANDIDATE_SMILES = re.compile(r"\*|\[[RXYZ]")

# Molfile atom symbols: V2000 atom lines (x y z symbol) and V3000 atom lines (index symbol x y z).
_V2000_ATOM = re.compile(r"^ *-?\d+\.\d+ +-?\d+\.\d+ +-?\d+\.\d+ (\S+)", re.MULTILINE)
_V3000_ATOM = re.compile(r"^M  V30 \d+ (\S+) -?\d", re.MULTILINE)
_PT = Chem.GetPeriodicTable()
_ELEMENTS = frozenset(_PT.GetElementSymbol(z) for z in range(1, 119)) | {"D", "T"}


def _smiles_core(smiles: str | None) -> str:
    parts = (smiles or "").split(maxsplit=1)
    return parts[0] if parts else ""


def _molfile_may_have_dummies(molfile: str | None) -> bool:
    """True when an atom of the molfile is no element (*, R, R#, A, Q, L...), or the atom block
    cannot be read here (RDKit then decides)."""
    if not molfile:
        return False
    symbols = _V2000_ATOM.findall(molfile) or _V3000_ATOM.findall(molfile)
    if not symbols:
        return True
    return any(s not in _ELEMENTS for s in symbols)


def _label_order(label: str) -> tuple:
    m = re.match(r"([^\d']*)(\d*)(.*)", label)
    head, num, rest = m.groups() if m else (label, "", "")
    return (label == "*", head, int(num) if num else -1, rest)


def _ordered(labels) -> list[str]:
    return sorted(set(labels), key=_label_order)


def _atom_label(atom: Chem.Atom) -> str:
    if atom.HasProp("molFileAlias"):
        alias = atom.GetProp("molFileAlias").strip()
        if alias:
            return alias
    if atom.HasProp("_MolFileRLabel"):
        return f"R{atom.GetIntProp('_MolFileRLabel')}"
    if atom.GetIsotope():
        return f"R{atom.GetIsotope()}"
    if atom.GetAtomMapNum():
        return f"R{atom.GetAtomMapNum()}"
    if atom.HasProp("dummyLabel"):
        own = atom.GetProp("dummyLabel").strip()
        if own and own != "*":
            return own
    return "*"


def _mol_labels(mol: Chem.Mol | None) -> list[str]:
    if mol is None:
        return []
    return [_atom_label(a) for a in mol.GetAtoms() if a.GetAtomicNum() == 0]


def _token_label(m: re.Match) -> str:
    if m.group(1):
        return f"R{m.group(2)}{m.group(3)}"
    return f"{m.group(4)}{m.group(5)}"


def _dummy_label(m: re.Match) -> str:
    number = m.group(1) or m.group(2)
    return f"R{number}" if number else "*"


def _as_dummy(m: re.Match) -> str:
    return f"[{m.group(2) or m.group(5) or ''}*]"


def _unparsed_smiles_labels(smiles: str) -> list[str]:
    """Labels of a SMILES RDKit refused, when its R tokens are the only reason; else []."""
    tokens = list(_R_TOKEN.finditer(smiles))
    others = [t for t in tokens if _token_label(t) != "Y"]
    if not others:
        return []  # no R token, or a lone [Y]: not an R-group scaffold
    # each R token (and [Y] beside them) becomes a dummy atom; R1 keeps its number as isotope
    replaced = _R_TOKEN.sub(_as_dummy, smiles)
    with BlockLogs():
        if Chem.MolFromSmiles(replaced) is None:
            return []
    dummies = [_dummy_label(m) for m in _SMILES_DUMMY.finditer(smiles)]
    return [_token_label(t) for t in tokens] + dummies


def _placeholders(raw: list[str]) -> list[str]:
    """The R-group labels among a SMILES's dummy-atom labels: a wildcard is always a
    placeholder, so one whose label has not the form of a label counts as `*`."""
    return [as_label(lab) or UNLABELLED for lab in raw]


@lru_cache(maxsize=2048)
def _parsed_labels(smiles: str, molfile: str, has_smiles: bool = False) -> tuple[str, ...]:
    """The RDKit part, for strings that passed the cheap check (cached: a scaffold's molfile is
    read once per process, not again on each cache hit or backfill of the same output).
    `smiles` is "" when it passed the cheap check as plain; `has_smiles` says whether there is
    one at all."""
    labels: list[str] = []
    if molfile:
        with BlockLogs():
            raw = _mol_labels(Chem.MolFromMolBlock(molfile, sanitize=False))
        labels = [lab for lab in map(as_label, raw) if lab is not None]
        if raw and not labels:
            # Only aliases that are no labels (OMe, OAc, 555...): a placeholder only if the
            # SMILES still has the wildcard (or there is none to tell); MolScribe expands a
            # group it knows in the SMILES, which is then a whole compound.
            return (UNLABELLED,) if not has_smiles or _SMILES_DUMMY.search(smiles) else ()
    if not labels and smiles:
        with BlockLogs():
            mol = Chem.MolFromSmiles(smiles)
        raw = _mol_labels(mol) if mol is not None else _unparsed_smiles_labels(smiles)
        labels = _placeholders(raw)
    return tuple(_ordered(labels))


def rgroup_labels(smiles: str | None, molfile: str | None = None) -> list[str]:
    """The R-group labels of a structure (its SMILES and optional molfile), [] when it has none.
    The molfile's dummy atoms win (they carry the drawn labels); else the SMILES decides."""
    core = _smiles_core(smiles)
    check_smiles = bool(core) and _CANDIDATE_SMILES.search(core) is not None
    check_molfile = _molfile_may_have_dummies(molfile)
    if not check_smiles and not check_molfile:
        return []
    return list(
        _parsed_labels(core if check_smiles else "", molfile if check_molfile else "", bool(core))
    )
