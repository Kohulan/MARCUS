"""Drawings in the paper's orientation (marcus.workers.orient): the common part keeps the
template's positions, the y axis as the OCSR libraries write it, and every fallback."""

import json
import math
import random
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Geometry import Point3D

from marcus.workers.orient import image_layout, oriented_coords, width_factor

FERULIC = "COc1cc(/C=C/C(=O)O)ccc1O"  # no symmetry: every atom maps one way


def _layout(smiles: str, degrees: float) -> tuple[Chem.Mol, list[tuple[float, float]]]:
    """RDKit's layout of `smiles`, turned by `degrees` (y up)."""
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    a = math.radians(degrees)
    conf = mol.GetConformer()
    pos = []
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        pos.append((p.x * math.cos(a) - p.y * math.sin(a), p.x * math.sin(a) + p.y * math.cos(a)))
    return mol, pos


def _ocsr_molfile(
    mol: Chem.Mol, pos: list[tuple[float, float]], width: float, height: float, jitter: float = 0.04
):
    """The molfile an OCSR library writes for a crop of `width` x `height` in which the
    structure is drawn as `pos` (y up): image coordinates (y down) as fractions of the width
    and height, then each atom at (x, 1 - y), as MolScribe/MolNexTR `_verify_chirality` do.
    Each atom is read `jitter` bond lengths off (a fixed seed), as a model reads a printed
    drawing: no two bonds come out exactly one length."""
    rng = random.Random(7)
    pos = [(x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter)) for x, y in pos]
    xs = [x for x, _ in pos]
    ys = [y for _, y in pos]
    left, top = min(xs) - 1.0, max(ys) + 1.0  # a margin around the drawing
    out = Chem.Mol(mol)
    conf = out.GetConformer()
    image = []
    for i, (x, y) in enumerate(pos):
        u, v = (x - left) / width, (top - y) / height  # image: y grows downwards
        image.append((u, v))
        conf.SetAtomPosition(i, Point3D(u, 1 - v, 0))
    return Chem.MolToMolBlock(out), image


def _turn(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> tuple[float, float]:
    """(degrees b is turned from a, scale) by a least-squares fit over the paired points."""
    ax = sum(x for x, _ in a) / len(a)
    ay = sum(y for _, y in a) / len(a)
    bx = sum(x for x, _ in b) / len(b)
    by = sum(y for _, y in b) / len(b)
    dot = cross = norm = 0.0
    for (x1, y1), (x2, y2) in zip(a, b, strict=True):
        x1, y1, x2, y2 = x1 - ax, y1 - ay, x2 - bx, y2 - by
        dot += x1 * x2 + y1 * y2
        cross += x1 * y2 - y1 * x2
        norm += x1 * x1 + y1 * y1
    return math.degrees(math.atan2(cross, dot)), math.hypot(dot, cross) / norm


def _area(p: list[tuple[float, float]], i: int, j: int, k: int) -> float:
    """Signed area of the triangle i, j, k: its sign is the drawing's handedness."""
    (x1, y1), (x2, y2), (x3, y3) = p[i], p[j], p[k]
    return (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)


def _paired(smiles: str, template: Chem.Mol, coords, mapped_from: Chem.Mol | None = None):
    """The template atoms' positions and the result's for the atoms they share."""
    params = Chem.SmilesParserParams()
    params.removeHs = False
    drawn = Chem.MolFromSmiles(smiles, params)
    common = mapped_from if mapped_from is not None else template
    on_drawn = drawn.GetSubstructMatch(common)
    on_tpl = template.GetSubstructMatch(common)
    assert on_drawn and on_tpl
    return on_tpl, on_drawn


@pytest.mark.parametrize("degrees", [0, 70, 180, 250])
def test_the_structure_keeps_the_template_orientation(degrees):
    """A wide crop (3:1) of the structure turned by `degrees`; the SMILES (another atom order)
    comes out turned the same way, the same way round, and not squeezed."""
    mol, pos = _layout(FERULIC, degrees)
    molfile, _ = _ocsr_molfile(mol, pos, width=30.0, height=10.0)
    smiles = "OC(=O)/C=C/c1ccc(O)c(OC)c1"  # the same structure in another atom order
    coords = oriented_coords(smiles, molfile)
    assert coords is not None
    on_tpl, on_drawn = _paired(smiles, mol, coords)
    turn, _ = _turn([pos[i] for i in on_tpl], [coords[j] for j in on_drawn])
    assert abs(turn) < 3
    # same handedness: the drawing is not mirrored
    a, b, c = 0, 4, 9
    assert (
        _area(pos, on_tpl[a], on_tpl[b], on_tpl[c])
        * _area(coords, on_drawn[a], on_drawn[b], on_drawn[c])
        > 0
    )
    # not squeezed: the bonds are one length again
    lengths = [
        math.dist(coords[b.GetBeginAtomIdx()], coords[b.GetEndAtomIdx()])
        for b in Chem.MolFromSmiles(smiles).GetBonds()
    ]
    assert max(lengths) / min(lengths) < 1.15


def test_the_top_of_the_image_is_the_top_of_the_drawing():
    """The libraries write (x, 1 - y): the atom highest in the image (smallest image y) has
    the largest y here, which CDK draws at the top. A second flip would put it at the bottom."""
    mol, pos = _layout(FERULIC, 35)
    molfile, image = _ocsr_molfile(mol, pos, width=12.0, height=12.0)
    smiles = Chem.MolToSmiles(mol)
    coords = oriented_coords(smiles, molfile)
    assert coords is not None
    on_tpl, on_drawn = _paired(smiles, mol, coords)
    top_in_image = min(range(len(image)), key=lambda i: image[i][1])
    drawn_top = max(range(len(coords)), key=lambda j: coords[j][1])
    assert on_drawn[on_tpl.index(top_in_image)] == drawn_top


def test_another_engine_reading_differs_a_little_and_is_still_turned():
    """DECIMER read a methoxy where the template has a hydroxy: the common part (all but one
    atom) keeps the template's place, the rest is laid out around it."""
    mol, pos = _layout(FERULIC, 120)
    molfile, _ = _ocsr_molfile(mol, pos, width=15.0, height=10.0)
    other = "COc1cc(/C=C/C(=O)O)ccc1OC"
    coords = oriented_coords(other, molfile)
    assert coords is not None
    core = Chem.MolFromSmiles("COc1cc(/C=C/C(=O)O)ccc1O")
    on_tpl, on_drawn = _paired(other, mol, coords, mapped_from=core)
    turn, _ = _turn([pos[i] for i in on_tpl], [coords[j] for j in on_drawn])
    assert abs(turn) < 3
    assert len(coords) == Chem.MolFromSmiles(other).GetNumAtoms()


def test_written_hydrogens_keep_their_place_in_the_atom_order():
    """CDK keeps every atom the SMILES writes, [H] included: the positions follow that order."""
    mol, pos = _layout("OC(=O)c1ccccc1", 10)
    molfile, _ = _ocsr_molfile(mol, pos, width=10.0, height=10.0)
    coords = oriented_coords("[H]OC(=O)c1ccccc1", molfile)
    assert coords is not None and len(coords) == 10


def test_width_factor_finds_the_squeeze():
    mol, pos = _layout(FERULIC, 20)
    vectors = []
    for b in mol.GetBonds():
        (x1, y1), (x2, y2) = pos[b.GetBeginAtomIdx()], pos[b.GetEndAtomIdx()]
        vectors.append(((x2 - x1) / 2.5, y2 - y1))
    assert width_factor(vectors) == pytest.approx(2.5, rel=0.05)


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [(1.0, 0.0)],  # one bond
        [(0.87, 0.5), (0.87, -0.5), (0.87, 0.5)],  # a zig-zag chain: any squeeze keeps it even
    ],
)
def test_width_factor_without_information_is_one(vectors):
    assert width_factor(vectors) == 1.0


def _template_of(smiles: str, degrees: float = 0) -> str:
    mol, pos = _layout(smiles, degrees)
    return _ocsr_molfile(mol, pos, width=10.0, height=10.0)[0]


@pytest.mark.parametrize(
    ("smiles", "template"),
    [
        ("CCCCCCCCCCCCO", _template_of("c1ccc2ccccc2c1")),  # nothing in common
        ("c1ccccc1CCCCCCCCCCCCCCCCCC", _template_of("Cc1ccccc1")),  # common part under half
        ("not a smiles", _template_of(FERULIC)),
        (FERULIC, "not a molfile"),
        (FERULIC, ""),
        ("", _template_of(FERULIC)),
    ],
)
def test_falls_back_to_the_normal_layout(smiles, template):
    assert oriented_coords(smiles, template) is None


def test_a_template_without_positions_falls_back():
    mol = Chem.MolFromSmiles(FERULIC)
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))  # every atom at 0, 0
    flat = Chem.MolToMolBlock(mol)
    assert oriented_coords(FERULIC, flat) is None


def test_too_many_atoms_fall_back():
    big = "C" * 300
    assert oriented_coords(big, _template_of("CCCCCC")) is None


def test_the_template_engines_own_reading_needs_no_mcs(monkeypatch):
    """The same graph (stereo aside) as the template maps whole, without an MCS search."""
    from marcus.workers import orient

    def no_mcs(*args, **kwargs):
        raise AssertionError("no MCS for the same graph")

    monkeypatch.setattr(orient.rdFMCS, "FindMCS", no_mcs)
    mol, pos = _layout(FERULIC, 70)
    molfile, _ = _ocsr_molfile(mol, pos, width=30.0, height=10.0)
    smiles = "OC(=O)C=Cc1ccc(O)c(OC)c1"  # no stereo: still the same graph
    coords = oriented_coords(smiles, molfile)
    assert coords is not None
    on_tpl, on_drawn = _paired(smiles, mol, coords)
    turn, _ = _turn([pos[i] for i in on_tpl], [coords[j] for j in on_drawn])
    assert abs(turn) < 3


def _same_side(coords, a, b, c, d) -> bool:
    """c (on a) and d (on b) lie on the same side of the a=b axis: a Z (cis) drawing."""
    (ax, ay), (bx, by) = coords[a], coords[b]

    def side(p):
        return (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)

    return side(coords[c]) * side(coords[d]) > 0


Z_CINNAMIC = "OC(=O)/C=C\\c1ccccc1"
E_CINNAMIC = "OC(=O)/C=C/c1ccccc1"  # atoms: 1 C(acid), 3 C=, 4 =C, 5 ring C


def test_a_double_bond_keeps_the_structures_own_e_z():
    """The template engine drew the double bond Z, the structure says E: the drawing shows E
    (its label says E), never the template's Z (it falls back to the normal layout)."""
    z_mol, z_pos = _layout(Z_CINNAMIC, 40)
    molfile, _ = _ocsr_molfile(z_mol, z_pos, width=12.0, height=12.0)
    coords = oriented_coords(E_CINNAMIC, molfile)
    assert coords is None or not _same_side(coords, 3, 4, 1, 5)
    # the Z reading itself keeps the template's place, Z and all
    same = oriented_coords(Z_CINNAMIC, molfile)
    assert same is not None and _same_side(same, 3, 4, 1, 5)


def test_a_double_bond_without_e_z_follows_the_template():
    z_mol, z_pos = _layout(Z_CINNAMIC, 40)
    molfile, _ = _ocsr_molfile(z_mol, z_pos, width=12.0, height=12.0)
    coords = oriented_coords("OC(=O)C=Cc1ccccc1", molfile)
    assert coords is not None and _same_side(coords, 3, 4, 1, 5)


def test_an_unsanitizable_template_falls_back():
    pentavalent = Chem.MolFromSmiles("C(C)(C)(C)(C)C", sanitize=False)
    rdDepictor.Compute2DCoords(pentavalent)
    assert oriented_coords("CC(C)(C)C", Chem.MolToMolBlock(pentavalent, kekulize=False)) is None


# --- real engine output: which molfile holds the image's positions ----------------------------
# tests/fixtures/orient_engines.json: what DECIMER, MolNexTR (fb7505b) and MolScribe read from
# five crops of one paper page (structures only). MolNexTR rewrites its molfile from its SMILES
# (MolNexTR/chemical.py: MolFromSmiles, MolToMolBlock): a computed layout, every bond 1.5.
# MolScribe keeps the image's positions when its structure sanitizes (p2_6, p2_10); when it
# does not (p2_0, p2_2, p2_5), its _verify_chirality gives up before the positions are set and
# MolToMolBlock lays the molecule out itself.

REAL = json.loads((Path(__file__).parent.parent / "fixtures" / "orient_engines.json").read_text())
FROM_IMAGE = {("p2_6", "molscribe"), ("p2_10", "molscribe")}


@pytest.mark.parametrize("crop", sorted(REAL))
@pytest.mark.parametrize("engine", ["molnextr", "molscribe"])
def test_only_a_molfile_with_the_images_positions_is_a_template(crop, engine):
    assert image_layout(REAL[crop][engine]["molfile"]) is ((crop, engine) in FROM_IMAGE)


def test_a_computed_layout_is_no_template():
    """RDKit's own layout (bonds all one length) says nothing about the image; read with a
    model's small errors, the same drawing is a template."""
    mol, pos = _layout(FERULIC, 70)
    exact, _ = _ocsr_molfile(mol, pos, width=12.0, height=12.0, jitter=0.0)
    read, _ = _ocsr_molfile(mol, pos, width=12.0, height=12.0)
    assert not image_layout(exact) and oriented_coords(FERULIC, exact) is None
    assert image_layout(read) and oriented_coords(FERULIC, read) is not None


def _side(coords, a, b, c) -> float:
    (ax, ay), (bx, by), (cx, cy) = coords[a], coords[b], coords[c]
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


@pytest.mark.parametrize("crop", ["p2_6", "p2_10"])
def test_decimers_reading_follows_molscribes_positions(crop):
    """DECIMER's structure, drawn on MolScribe's positions: turned and handed as the crop."""
    template = REAL[crop]["molscribe"]["molfile"]
    smiles = REAL[crop]["decimer"]["smiles"]
    coords = oriented_coords(smiles, template)
    assert coords is not None
    tpl = Chem.MolFromMolBlock(template)
    params = Chem.SmilesParserParams()
    params.removeHs = False
    drawn = Chem.MolFromSmiles(smiles, params)
    on_drawn = drawn.GetSubstructMatch(tpl)
    assert len(on_drawn) == tpl.GetNumAtoms()  # the same structure
    conf = tpl.GetConformer()
    pos = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(tpl.GetNumAtoms())]
    turn, _ = _turn(pos, [coords[j] for j in on_drawn])
    assert abs(turn) < 5
    a, b, c = 0, tpl.GetNumAtoms() // 2, tpl.GetNumAtoms() - 1
    assert _side(pos, a, b, c) * _side(coords, on_drawn[a], on_drawn[b], on_drawn[c]) > 0
