"""Drawings in the paper's orientation: atom positions for a SMILES, laid out like a template.

MolScribe reads atom positions off the image and writes them into its molfile (v1 drew MolNexTR
and MolScribe with their own coordinates, `shouldUseCoordinates`). Here such a molfile is the
template for every engine's structure of that image: the common part (an MCS
of the structure and the template) keeps the template's positions, RDKit lays out the rest
around it, and CDK draws the result instead of its own layout (marcus.workers.tools.depict).

The y axis: both libraries write each atom at (x, 1 - y) of the image's normalised (x, y), y
pointing down in the image, so the molfile's y already points up, like every molfile and like
CDK's model coordinates. No flip is needed here; flipping again would mirror the drawing.

The x axis: both libraries resize the image to a square before reading it, so x and y are
fractions of the image's width and height: a wide crop comes out squeezed. The width:height
factor is estimated from the template itself, as the one that makes its bonds most nearly one
length (printed structures draw every bond about the same length); a template whose bonds
cannot tell (all along two mirrored directions, or a single bond) keeps the factor 1.

Only a molfile that holds the image's positions is a template (image_layout). The pinned
MolNexTR rewrites its molfile from its own SMILES (MolNexTR/chemical.py: MolFromSmiles, then
MolToMolBlock), and MolScribe lays its molecule out itself when its structure does not sanitize
(its _verify_chirality gives up before the positions are set): both are RDKit's computed layout,
nearly every bond one length. Positions read off a printed drawing never are.

Everything here is a fallback to the normal layout: any input it cannot use, a common part
under MIN_COMMON_ATOMS atoms or under MIN_COMMON_SHARE of the structure's heavy atoms, a
structure or template over MAX_ATOMS atoms, or a double bond the template would draw against
the structure's own E/Z (the template carries no stereo), gives None.
"""

import math

from rdkit import Chem
from rdkit.Chem import rdDepictor, rdFMCS
from rdkit.Geometry import Point2D
from rdkit.rdBase import BlockLogs

MIN_COMMON_ATOMS = 3
MIN_COMMON_SHARE = 0.5
MAX_ATOMS = 250
MCS_TIMEOUT_S = 2  # below the depict task's 5 s soft limit, with the drawing still to come
BOND_LENGTH = 1.5  # RDKit's depiction bond length: the laid-out rest matches the template
_ASPECTS = [math.exp(math.log(0.2) + i * (math.log(5.0) - math.log(0.2)) / 200) for i in range(201)]
_FLAT = 0.01  # a spread gain below this: the bonds cannot tell the factor
# A computed layout: at least this share of the bonds within ONE_LENGTH of the median length
# (measured on real output: computed layouts 0.86 to 1.00, positions from the image 0.09 and
# 0.59). Fewer than FEW_BONDS bonds cannot tell.
COMPUTED_SHARE = 0.8
ONE_LENGTH = 0.01
FEW_BONDS = 4


def _spread(vectors: list[tuple[float, float]], factor: float) -> float:
    """The standard deviation of the log bond lengths with x scaled by `factor`."""
    logs = [0.5 * math.log((factor * dx) ** 2 + dy**2) for dx, dy in vectors]
    mean = sum(logs) / len(logs)
    return math.sqrt(sum((v - mean) ** 2 for v in logs) / len(logs))


def width_factor(vectors: list[tuple[float, float]]) -> float:
    """The factor x must be scaled by so the bonds (dx, dy) are most nearly one length; 1.0
    when the bonds cannot tell."""
    vectors = [(dx, dy) for dx, dy in vectors if dx * dx + dy * dy > 1e-12]
    if len(vectors) < 2:
        return 1.0
    best = min(_ASPECTS, key=lambda f: _spread(vectors, f))
    return best if _spread(vectors, 1.0) - _spread(vectors, best) > _FLAT else 1.0


def _computed(lengths: list[float]) -> bool:
    """Bond lengths of a computed layout (nearly all one length), not of a drawing's reading."""
    if len(lengths) < FEW_BONDS:
        return False
    median = sorted(lengths)[len(lengths) // 2]
    if median <= 1e-9:
        return True
    same = sum(abs(x - median) <= ONE_LENGTH * median for x in lengths)
    return same >= COMPUTED_SHARE * len(lengths)


def _bond_vectors(mol) -> list[tuple[float, float]]:
    conf = mol.GetConformer()
    out = []
    for bond in mol.GetBonds():
        p, q = (
            conf.GetAtomPosition(bond.GetBeginAtomIdx()),
            conf.GetAtomPosition(bond.GetEndAtomIdx()),
        )
        out.append((q.x - p.x, q.y - p.y))
    return out


def image_layout(molfile: str) -> bool:
    """The molfile's positions were read off the image (not a layout an engine computed)."""
    return _template(molfile) is not None


def _template(molfile: str):
    """(molecule, its positions corrected and scaled to BOND_LENGTH) of a molfile with 2D
    positions, or None."""
    with BlockLogs():
        mol = Chem.MolFromMolBlock(molfile, sanitize=True)
    if mol is None or mol.GetNumConformers() == 0 or not 0 < mol.GetNumAtoms() <= MAX_ATOMS:
        return None
    conf = mol.GetConformer()
    pos = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())]
    vectors = _bond_vectors(mol)
    if _computed([math.hypot(dx, dy) for dx, dy in vectors]):
        return None  # a computed layout says nothing about the image
    factor = width_factor(vectors)
    lengths = sorted(math.hypot(factor * dx, dy) for dx, dy in vectors)
    if not lengths or lengths[len(lengths) // 2] <= 1e-9:
        return None  # no bond, or no positions (a molfile with every atom at 0,0)
    scale = BOND_LENGTH / lengths[len(lengths) // 2]
    return mol, [(factor * x * scale, y * scale) for x, y in pos]


def _structure(smiles: str):
    """The SMILES as CDK reads it: every written atom kept ([H] too), in SMILES order."""
    params = Chem.SmilesParserParams()
    params.removeHs = False
    with BlockLogs():
        mol = Chem.MolFromSmiles(smiles, params)
    return mol if mol is not None and 0 < mol.GetNumAtoms() <= MAX_ATOMS else None


def _graph_key(mol) -> str | None:
    try:
        return Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=False)
    except (ValueError, RuntimeError):
        return None


def _same_graph(mol, tpl) -> tuple[tuple, tuple] | None:
    """(atoms of mol, atoms of tpl) when both are one graph (the template engine's own reading,
    or another that agrees): the whole template maps, no MCS needed."""
    key = _graph_key(mol)
    if key is None or key != _graph_key(tpl):
        return None
    on_mol = mol.GetSubstructMatch(tpl)
    return (on_mol, tuple(range(tpl.GetNumAtoms()))) if on_mol else None


def _common_part(mol, tpl) -> tuple[tuple, tuple]:
    """(atoms of mol, atoms of tpl) of their MCS; empty when it is too small to place by."""
    heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() != 1)
    with BlockLogs():
        result = rdFMCS.FindMCS(
            [mol, tpl],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            bondCompare=rdFMCS.BondCompare.CompareAny,  # a misread bond order keeps its place
            ringMatchesRingOnly=True,
            completeRingsOnly=True,
            timeout=MCS_TIMEOUT_S,
        )
    if result.numAtoms < max(MIN_COMMON_ATOMS, MIN_COMMON_SHARE * heavy):
        return (), ()
    query = Chem.MolFromSmarts(result.smartsString)
    if query is None:
        return (), ()
    return mol.GetSubstructMatch(query), tpl.GetSubstructMatch(query)


def oriented_coords(smiles: str, template_molfile: str) -> list[tuple[float, float]] | None:
    """2D positions (y up) for every atom of `smiles`, in its atom order, with the common part
    placed as in the template; None to fall back to the normal layout."""
    if not smiles or not template_molfile:
        return None
    mol = _structure(smiles)
    found = _template(template_molfile)
    if mol is None or found is None:
        return None
    tpl, pos = found
    on_mol, on_tpl = _same_graph(mol, tpl) or _common_part(mol, tpl)
    if not on_mol or len(on_mol) != len(on_tpl):
        return None
    coord_map = {m: Point2D(*pos[t]) for m, t in zip(on_mol, on_tpl, strict=True)}
    rdDepictor.SetPreferCoordGen(False)  # RDKit's own depictor keeps coordMap positions fixed
    try:
        rdDepictor.Compute2DCoords(mol, coordMap=coord_map, canonOrient=False)
    except (ValueError, RuntimeError):
        return None
    conf = mol.GetConformer()
    coords = [
        (conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())
    ]
    # The template carries no stereo (the MCS ignores it): a double bond it drew the other way
    # round would show Z where the structure says E. Its own E/Z wins: the normal layout then.
    return coords if _double_bonds_as_written(mol, coords) else None


_CIS = (Chem.BondStereo.STEREOZ, Chem.BondStereo.STEREOCIS)
_TRANS = (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOTRANS)


def _double_bonds_as_written(mol, coords) -> bool:
    """Every double bond with E/Z in the structure is drawn that way round at `coords`."""
    for bond in mol.GetBonds():
        stereo = bond.GetStereo()
        if stereo not in _CIS + _TRANS or len(bond.GetStereoAtoms()) != 2:
            continue
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        c, d = bond.GetStereoAtoms()
        (ax, ay), (bx, by) = coords[a], coords[b]

        def side(i: int) -> float:
            x, y = coords[i]
            return (bx - ax) * (y - ay) - (by - ay) * (x - ax)

        cis = side(c) * side(d) > 0
        if cis != (stereo in _CIS):
            return False
    return True
