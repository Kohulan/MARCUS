"""Drawings in the paper's orientation: atom positions for a SMILES, laid out like a template.

MolScribe and MolNexTR (from 7a4e03f) read atom positions off the image and write them into
their molfile (v1 drew both with their own coordinates, `shouldUseCoordinates`). Here such a molfile is the
template for every engine's structure of that image: the common part (an MCS
of the structure and the template) keeps the template's positions, RDKit lays out the rest
around it, and CDK draws the result instead of its own layout (marcus.workers.tools.depict).

The y axis: both libraries write each atom at (x, 1 - y) of the image's normalised (x, y), y
pointing down in the image, so the molfile's y already points up, like every molfile and like
CDK's model coordinates. No flip is needed here; flipping again would mirror the drawing.

The x axis: both libraries read the image resized to a square, then undo it before writing the
molfile (_convert_graph_to_smiles in MolScribe 250f683 and MolNexTR: x * width / height, given
the image), so the positions keep the drawing's proportions. They are used as they are, only
scaled to BOND_LENGTH.

Only a molfile that holds the image's positions is a template (image_layout). MolNexTR before
7a4e03f (fb7505b) rewrote its molfile from its own SMILES (MolFromSmiles, then MolToMolBlock), and
MolScribe lays its molecule out itself when its structure does not sanitize (its
_verify_chirality gives up before the positions are set): both are RDKit's computed layout,
nearly every bond one length. Positions read off a printed drawing never are.

The paper layout (marcus.core.paper_layout; owner decision 2026-11-26) is the one template
that is used valid or not: MolScribe's raw atoms and bonds at their pixels in the image, written
by its worker with a title line that says so. It is read sanitized first (MolScribe's own valid
reading then maps whole, _same_graph) and, when it does not sanitize, as it is, with rings
perceived: only its graph and positions matter. It is never put to the computed-layout test (a
printed benzene has bonds of one length too). `oriented` returns, with the positions, which
atoms were placed from the template and the scale back to the template's own units (a paper
layout: pixels), for the overlay on the paper.

Everything here is a fallback to the normal layout: any input it cannot use, a common part
under MIN_COMMON_ATOMS atoms or under MIN_COMMON_SHARE of the structure's heavy atoms, a
structure or template over MAX_ATOMS atoms, or a double bond the template would draw against
the structure's own E/Z (the template carries no stereo), gives None.
"""

import math
from typing import NamedTuple

from rdkit import Chem
from rdkit.Chem import rdDepictor, rdFMCS
from rdkit.Geometry import Point2D
from rdkit.rdBase import BlockLogs

from marcus.core import paper_layout

MIN_COMMON_ATOMS = 3
MIN_COMMON_SHARE = 0.5
MAX_ATOMS = 250
MCS_TIMEOUT_S = 2  # below the depict task's 5 s soft limit, with the drawing still to come
BOND_LENGTH = 1.5  # RDKit's depiction bond length: the laid-out rest matches the template
# A computed layout: at least this share of the bonds within ONE_LENGTH of the median length
# (measured on real output: computed layouts 0.86 to 1.00, positions from the image 0.09 and
# 0.59). Fewer than FEW_BONDS bonds cannot tell.
COMPUTED_SHARE = 0.8
ONE_LENGTH = 0.01
FEW_BONDS = 4


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


def first_template(molfiles) -> str | None:
    """Of candidate templates in the order they are preferred (MolScribe's, then MolNexTR's),
    the first whose positions were read off the image; None without one. The one rule the
    stored depictions (cards, focus mode) go by; Compare's client applies the same rule."""
    return next((m for m in molfiles if m and image_layout(m)), None)


class Template(NamedTuple):
    mol: Chem.Mol
    pos: list[tuple[float, float]]  # scaled to BOND_LENGTH
    scale: float  # pos = the molfile's own positions * scale


class Oriented(NamedTuple):
    coords: list[tuple[float, float]]  # every atom of the SMILES, in its order, y up
    placed: frozenset[int]  # the atoms that sit at the template's positions
    scale: float  # coords / scale = the template's own units (a paper layout: pixels)


def _read(molfile: str, layout: bool):
    """The molfile's molecule: sanitized; a paper layout that does not sanitize, as it is."""
    with BlockLogs():
        mol = Chem.MolFromMolBlock(molfile, sanitize=True)
        if mol is None and layout:
            mol = Chem.MolFromMolBlock(molfile, sanitize=False)
            if mol is not None:
                try:
                    mol.UpdatePropertyCache(strict=False)
                    Chem.FastFindRings(mol)  # the MCS matches rings with rings
                except (ValueError, RuntimeError):
                    return None
    return mol


def _template(molfile: str) -> Template | None:
    """The molecule of a molfile with 2D positions and its positions scaled to BOND_LENGTH, or
    None."""
    layout = paper_layout.is_layout(molfile)
    mol = _read(molfile, layout)
    if mol is None or mol.GetNumConformers() == 0 or not 0 < mol.GetNumAtoms() <= MAX_ATOMS:
        return None
    conf = mol.GetConformer()
    pos = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())]
    vectors = _bond_vectors(mol)
    # A paper layout says itself that its positions are the image's (a printed ring has bonds
    # of one length too); any other molfile with bonds of one length is a computed layout.
    if not layout and _computed([math.hypot(dx, dy) for dx, dy in vectors]):
        return None  # a computed layout says nothing about the image
    lengths = sorted(math.hypot(dx, dy) for dx, dy in vectors)
    if not lengths or lengths[len(lengths) // 2] <= 1e-9:
        return None  # no bond, or no positions (a molfile with every atom at 0,0)
    scale = BOND_LENGTH / lengths[len(lengths) // 2]
    return Template(mol, [(x * scale, y * scale) for x, y in pos], scale)


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


def _common_part(mol, tpl, timeout: int = MCS_TIMEOUT_S) -> tuple[tuple, tuple]:
    """(atoms of mol, atoms of tpl) of their MCS; empty when it is too small to place by."""
    heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() != 1)
    with BlockLogs():
        result = rdFMCS.FindMCS(
            [mol, tpl],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            bondCompare=rdFMCS.BondCompare.CompareAny,  # a misread bond order keeps its place
            ringMatchesRingOnly=True,
            completeRingsOnly=True,
            timeout=timeout,
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
    found = oriented(smiles, template_molfile)
    return found.coords if found is not None else None


def oriented(smiles: str, template_molfile: str, timeout: int = MCS_TIMEOUT_S) -> Oriented | None:
    """`oriented_coords` with the atoms placed from the template and the scale back to the
    template's own units. `timeout`: seconds for the MCS search (whole seconds, RDKit's)."""
    if not smiles or not template_molfile:
        return None
    mol = _structure(smiles)
    found = _template(template_molfile)
    if mol is None or found is None:
        return None
    tpl, pos, scale = found
    on_mol, on_tpl = _same_graph(mol, tpl) or _common_part(mol, tpl, timeout)
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
    if not _double_bonds_as_written(mol, coords):
        return None
    return Oriented(coords, frozenset(on_mol), scale)


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
