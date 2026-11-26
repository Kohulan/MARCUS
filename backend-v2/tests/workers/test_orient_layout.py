"""The paper layout as an orientation template (marcus.workers.orient): used valid or not, never
taken for a computed layout, and its pixel scale comes back for the overlay.

The case of the design (fixtures/layout): DECIMER reads an extra methyl, MolParser misses one,
MolScribe's own answer is invalid; with its layout both answers are drawn as the paper draws.
"""

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem

from marcus.core import paper_layout
from marcus.workers import orient
from marcus.workers.ocsr import layout
from marcus.workers.orient import first_template, image_layout, oriented, oriented_coords

FIXTURES = Path(__file__).parent.parent / "fixtures" / "layout"
RAW = json.loads((FIXTURES / "raw.json").read_text())
CASE = layout.layout_molfile(FIXTURES / "crop.png", RAW["atoms"], RAW["bonds"])
DECIMER = "CC[C@@H](C)C(=O)O[C@@H]1C2=C(C)C(=O)O[C@]32C=C(C)[C@@](C)(CC[C@H](C)C1=O)O3"
MOLPARSER = "CC[C@@H](C)C(=O)O[C@H]1C(=O)[C@@H](C)CC[C@H]2C=C[C@@]3(OC(=O)C(C)=C13)O2"


def _layout_of(symbols, pixels, edges, fit=0.5):
    lengths = sorted(math.dist(pixels[a], pixels[b]) for a, b, _ in edges)
    title = paper_layout.header(fit, lengths[len(lengths) // 2], 400, 400)
    return layout._molfile(symbols, pixels, edges, title)


def _hexagon(cx=200.0, cy=200.0, r=40.0):
    return [
        (cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30)))
        for i in range(6)
    ]


RING = [(i, (i + 1) % 6, "aromatic") for i in range(6)]


@pytest.mark.parametrize(("smiles", "atoms", "placed"), [(DECIMER, 27, 26), (MOLPARSER, 25, 25)])
def test_both_answers_of_the_case_follow_the_paper(smiles, atoms, placed):
    found = oriented(smiles, CASE)
    assert found is not None and len(found.coords) == atoms
    assert len(found.placed) >= placed - 1
    # the placed atoms sit at the layout's pixels: coords / scale = px (y up)
    info = paper_layout.info(CASE)
    assert found.scale == pytest.approx(orient.BOND_LENGTH / info.bond, rel=0.02)
    for i in found.placed:
        x, y = found.coords[i]
        assert 0 <= x / found.scale <= info.width and -info.height <= y / found.scale <= 0
    assert oriented_coords(smiles, CASE) == found.coords


def test_a_drawing_with_every_bond_one_length_is_still_a_layout():
    """A printed benzene has bonds of one length: for any other molfile that is the mark of a
    computed layout; a paper layout says itself where its positions come from."""
    ring = _layout_of(["C"] * 6, _hexagon(), RING)
    assert image_layout(ring)
    plain = "\n" + ring.split("\n", 1)[1]  # the same molfile without the layout's title
    assert not image_layout(plain)
    found = oriented("Cc1ccccc1", ring)
    assert found is not None and len(found.placed) == 6


def test_a_layout_that_does_not_sanitize_is_used():
    """MolScribe's reading with a carbon of five bonds: no molecule, still the drawing's
    positions. Any other molfile that does not sanitize is no template (as before)."""
    pixels = [(200.0, 200.0), (240.0, 200.0), (160.0, 200.0), (200.0, 240.0), (200.0, 160.0),
              (228.0, 228.0), (268.0, 228.0)]  # fmt: skip
    edges = [(0, i, "single") for i in range(1, 6)] + [(5, 6, "single")]
    bad = _layout_of(["C"] * 7, pixels, edges)
    assert Chem.MolFromMolBlock(bad) is None
    found = oriented("CC(C)(C)CC", bad)
    assert found is not None and len(found.placed) >= 5
    assert oriented("CC(C)(C)CC", "\n" + bad.split("\n", 1)[1]) is None


def test_a_valid_layout_maps_whole_without_an_mcs(monkeypatch):
    """MolScribe's own valid reading: the layout sanitizes, the same graph maps atom by atom."""

    def no_mcs(*args, **kwargs):
        raise AssertionError("no MCS for the same graph")

    monkeypatch.setattr(orient.rdFMCS, "FindMCS", no_mcs)
    pixels = _hexagon() + [
        (200.0 + 80 * math.cos(math.radians(30)), 200.0 + 80 * math.sin(math.radians(30)))
    ]
    ring = _layout_of(["C"] * 6 + ["O"], pixels, RING + [(0, 6, "single")])
    found = oriented("Oc1ccccc1", ring)
    assert found is not None and found.placed == frozenset(range(7))
    # the oxygen (atom 0 of the SMILES) sits where the layout has it, y up
    x, y = found.coords[0]
    assert (x / found.scale, -y / found.scale) == pytest.approx(pixels[6], abs=0.01)


def test_a_label_in_the_layout_matches_no_atom():
    """An unknown label ("[OMe]", a dummy atom) is not a wildcard: the rest still places."""
    pixels = _hexagon() + [(280.0, 240.0)]
    ring = _layout_of(["C"] * 6 + ["[OMe]"], pixels, RING + [(0, 6, "single")])
    found = oriented("COc1ccccc1", ring)
    assert found is not None and len(found.placed) == 6
    ring_atoms = {
        i for i, a in enumerate(Chem.MolFromSmiles("COc1ccccc1").GetAtoms()) if a.IsInRing()
    }
    assert found.placed == ring_atoms


def test_the_layout_is_preferred_when_it_comes_first():
    ring = _layout_of(["C"] * 6, _hexagon(), RING)
    assert first_template([ring, "not a molfile"]) == ring
    assert first_template(["not a molfile", ring]) == ring


def test_the_mcs_time_can_be_bounded(monkeypatch):
    seen = []
    real = orient.rdFMCS.FindMCS

    def spy(mols, **kwargs):
        seen.append(kwargs["timeout"])
        return real(mols, **kwargs)

    monkeypatch.setattr(orient.rdFMCS, "FindMCS", spy)
    assert oriented(DECIMER, CASE, timeout=1) is not None
    assert oriented(DECIMER, CASE) is not None
    assert seen == [1, orient.MCS_TIMEOUT_S]
