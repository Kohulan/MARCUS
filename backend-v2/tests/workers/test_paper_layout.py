"""The paper layout: MolScribe's raw atoms and bonds, fitted to the ink of the image it read,
as a molfile in the image's pixels (marcus.workers.ocsr.layout, marcus.core.paper_layout).

Fixture `layout/raw.json` + `layout/crop.png`: the case of the design (paper 0e1b8692, page 1,
a bridged sesquiterpene lactone): MolScribe's answer is invalid (a carbon with five bonds), its
28 atoms and 31 bonds still hold the drawing's positions, with two atoms read twice.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from rdkit import Chem

from marcus.core import paper_layout
from marcus.workers.ocsr import layout

FIXTURES = Path(__file__).parent.parent / "fixtures" / "layout"
RAW = json.loads((FIXTURES / "raw.json").read_text())
CROP = FIXTURES / "crop.png"


def _mirrored(atoms: list[dict]) -> list[dict]:
    return [{**a, "x": 1.0 - a["x"]} for a in atoms]


# --- the graph ------------------------------------------------------------------------------


def test_atoms_read_twice_at_one_position_are_merged():
    """Atoms 24/26 and 25/27 of the case sit at one position each: one atom each, their bonds
    joined (a bond read twice is kept once, the first order wins)."""
    symbols, points, bonds = layout.graph(RAW["atoms"], RAW["bonds"])
    assert len(symbols) == len(points) == 26
    assert len(set(points)) == 26
    assert len(bonds) == 28
    pairs = [frozenset(b[:2]) for b in bonds]
    assert len(set(pairs)) == 28 and all(len(p) == 2 for p in pairs)
    assert (23, 24, "single") in bonds and (24, 25, "double") in bonds


def test_wedges_are_single_bonds_and_other_words_too():
    _, _, bonds = layout.graph(
        [{"atom_symbol": "C", "x": 0.0, "y": 0.0}, {"atom_symbol": "O", "x": 1.0, "y": 0.0}]
        + [{"atom_symbol": "C", "x": 0.5, "y": float(i)} for i in range(1, 5)],
        [
            {"bond_type": "solid wedge", "endpoint_atoms": [0, 1]},
            {"bond_type": "dashed wedge", "endpoint_atoms": [1, 2]},
            {"bond_type": "aromatic", "endpoint_atoms": [2, 3]},
            {"bond_type": "triple", "endpoint_atoms": [3, 4]},
            {"bond_type": "something new", "endpoint_atoms": [4, 5]},
            {"bond_type": "single", "endpoint_atoms": [5, 5]},  # a loop: dropped
            {"bond_type": "single", "endpoint_atoms": [5, 9]},  # no such atom: dropped
        ],
    )
    assert [b[2] for b in bonds] == ["single", "single", "aromatic", "triple", "single"]


@pytest.mark.parametrize(
    ("symbol", "number", "charge"),
    [
        ("C", 6, 0),
        ("[C@@H]", 6, 0),
        ("Cl", 17, 0),
        ("[N+]", 7, 1),
        ("[O-]", 8, -1),
        ("[Si]", 14, 0),
        ("[R1]", 0, 0),  # a label: a dummy atom
        ("[OMe]", 0, 0),
        ("", 0, 0),
        ("[", 0, 0),
    ],
)
def test_symbols_are_read_as_smiles_atoms_else_a_dummy(symbol, number, charge):
    atom = layout.atom_of(symbol)
    assert (atom.GetAtomicNum(), atom.GetFormalCharge()) == (number, charge)
    assert atom.GetChiralTag() == Chem.ChiralType.CHI_UNSPECIFIED


# --- the fit --------------------------------------------------------------------------------


def test_the_case_is_fitted_to_the_ink_and_written_in_crop_pixels():
    molfile = layout.layout_molfile(CROP, RAW["atoms"], RAW["bonds"])
    info = paper_layout.info(molfile)
    assert (info.width, info.height) == Image.open(CROP).size == (585, 689)
    assert info.fit < 1.0  # mean px from the ink (the prototype: 0.53)
    assert 30 < info.bond < 90
    assert info.overlay_ok
    mol = Chem.MolFromMolBlock(molfile, sanitize=False)
    assert mol.GetNumAtoms() == 26 and mol.GetNumBonds() == 28
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(26)]
    ys = [conf.GetAtomPosition(i).y for i in range(26)]
    # crop pixels, y up as every molfile (molfile y = -pixel y)
    assert 0 <= min(xs) < max(xs) <= 585 and -689 <= min(ys) < max(ys) <= 0
    # the top of the drawing (atom 15, y 0 of MolScribe's box) is the top of the molfile
    assert ys[15] == max(ys)
    # every bond lies on ink: the mean distance of its points is the stated fit
    grey = np.asarray(Image.open(CROP).convert("L"))
    off = []
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        for t in (0.3, 0.5, 0.7):
            x = xs[a] + (xs[b] - xs[a]) * t
            y = -(ys[a] + (ys[b] - ys[a]) * t)
            box = grey[int(y) - 4 : int(y) + 5, int(x) - 4 : int(x) + 5]
            off.append(box.min() < layout.DARK)
    assert sum(off) >= 0.95 * len(off)


def test_a_mirrored_graph_does_not_fit_no_overlay():
    """The negative control of the overlay threshold: the same graph mirrored finds no place
    on the ink within OVERLAY_MAX_FIT_SHARE of a bond length."""
    molfile = layout.layout_molfile(CROP, _mirrored(RAW["atoms"]), RAW["bonds"])
    info = paper_layout.info(molfile)
    assert info.fit > 2 * paper_layout.OVERLAY_MAX_FIT_SHARE * info.bond
    assert not info.overlay_ok


def test_the_fitted_box_never_collapses():
    """A box shrunk onto one stroke would score ~0: width and height stay at or above half the
    ink's."""
    grey = np.asarray(Image.open(CROP).convert("L"))
    _, points, bonds = layout.graph(_mirrored(RAW["atoms"]), RAW["bonds"])
    fit = layout.fit_to_ink(grey, points, [b[:2] for b in bonds])
    ys, xs = np.nonzero(grey < layout.DARK)
    assert fit.w >= 0.5 * (xs.max() - xs.min()) and fit.h >= 0.5 * (ys.max() - ys.min())


@pytest.mark.parametrize(
    ("atoms", "bonds"),
    [
        ([], []),
        (RAW["atoms"][:1], []),
        (RAW["atoms"], []),  # no bond: nothing to fit
        ([{"atom_symbol": "C"}], [{"bond_type": "single", "endpoint_atoms": [0, 0]}]),
        ("atoms", "bonds"),
        (None, None),
    ],
)
def test_no_layout_without_a_usable_graph(atoms, bonds):
    assert layout.layout_molfile(CROP, atoms, bonds) is None


def test_no_layout_on_a_blank_image(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), "white").save(blank)
    assert layout.layout_molfile(blank, RAW["atoms"], RAW["bonds"]) is None


def test_too_many_atoms_give_no_layout():
    atoms = [
        {"atom_symbol": "C", "x": i / 300, "y": (i % 7) / 7} for i in range(layout.MAX_ATOMS + 1)
    ]
    bonds = [{"bond_type": "single", "endpoint_atoms": [i, i + 1]} for i in range(len(atoms) - 1)]
    assert layout.layout_molfile(CROP, atoms, bonds) is None


# --- the header -----------------------------------------------------------------------------


def test_header_round_trip_and_the_overlay_rule():
    text = paper_layout.header(0.526, 40.52, 585, 689)
    assert text == "MARCUS layout fit=0.53 bond=40.5 size=585x689"
    info = paper_layout.info(text + "\n  RDKit          2D\n\n  0  0  0 ...")
    assert (info.fit, info.bond, info.width, info.height) == (0.53, 40.5, 585, 689)
    assert info.overlay_ok
    assert not paper_layout.info(paper_layout.header(1.7, 40.0, 10, 10)).overlay_ok  # 4.25 %
    assert paper_layout.info(paper_layout.header(1.6, 40.0, 10, 10)).overlay_ok  # 4 %


@pytest.mark.parametrize(
    "molfile",
    [None, "", "\n  RDKit\n", "MARCUS layout", "MARCUS layout fit=x bond=1 size=1x1",
     "MARCUS layout fit=1 bond=0 size=1x1", "MARCUS layout fit=-1 bond=1 size=1x1",
     "MARCUS layout fit=nan bond=1 size=1x1", "x MARCUS layout fit=1 bond=1 size=1x1"],
)  # fmt: skip
def test_only_a_well_formed_header_is_a_layout(molfile):
    assert paper_layout.info(molfile) is None
    assert not paper_layout.is_layout(molfile)


def test_the_layout_module_imports_no_image_library():
    """cv2 and scipy load with the first fit, in the MolScribe worker only."""
    code = (
        "import sys; import marcus.workers.ocsr.layout, marcus.core.paper_layout; "
        "print([m for m in ('cv2', 'scipy') if m in sys.modules])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
