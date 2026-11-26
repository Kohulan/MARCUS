"""Builds the paper layout (marcus.core.paper_layout) from MolScribe's raw atoms and bonds.

`MolScribe.predict_image_file(path, return_atoms_bonds=True)` returns every atom
({"atom_symbol", "x", "y"}) and bond ({"bond_type", "endpoint_atoms"}) it read, also when the
structure does not sanitize and its molfile is therefore a computed layout. The positions are
normalised to the atoms' own box (0..1 on each axis), not to the image, so the box is found
again on the image:

- `graph`: atoms read twice at one position become one atom (the case of the design had two
  such pairs), bonds follow, a bond read twice is kept once; wedges are single bonds.
- `fit_to_ink`: four numbers (x0, y0, w, h) place the box on the image. The cost is the mean
  distance from points along each bond to the nearest dark pixel (grey below DARK, OpenCV's
  distance transform); Nelder-Mead from seven starts (70 to 100 % of the ink's box: with
  the design's three, 3 of 17 real crops stopped in a worse local minimum). The box
  is kept at or above MIN_BOX_SHARE of the ink's box on each axis: a box collapsed onto one
  stroke would score ~0.
- `layout_molfile`: the molfile, each atom at its fitted pixel (y = -pixel y), with the fit in
  its title line. None when there is nothing to fit.

A mirrored or otherwise wrong graph still gets its best box; how well it fits is in the header,
and the overlay is offered only under paper_layout.OVERLAY_MAX_FIT_SHARE.

cv2, scipy and numpy come with MolScribe's own stack (docker/Dockerfile.torch) and are imported
with the first fit; RDKit with the first molfile.
"""

from pathlib import Path
from typing import NamedTuple

from marcus.core import paper_layout

DARK = 160  # grey below this is ink
MIN_BOX_SHARE = 0.5
STARTS = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)  # the box's share of the ink's box at each start
ALONG = 8  # points per bond, between 15 % and 85 % of its length (off the atom labels)
MAX_ATOMS = 250  # = marcus.workers.orient.MAX_ATOMS: a larger template is never used
SAME_POSITION = 1e-6  # of the 0..1 box
BOND_WORDS = ("single", "double", "triple", "aromatic")


class Fit(NamedTuple):
    x0: float
    y0: float
    w: float
    h: float
    error: float  # mean px from the ink


def atom_of(symbol):
    """The RDKit atom of a symbol as MolScribe writes it ("C", "[C@@H]", "[N+]"); a label it
    cannot be ("[R1]", "[OMe]") is a dummy atom. Element, charge and isotope only: the layout
    holds no stereo and no hydrogen counts."""
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    parsed = None
    if isinstance(symbol, str) and symbol:
        with BlockLogs():
            try:
                parsed = Chem.AtomFromSmiles(symbol)
            except Exception:  # noqa: BLE001 - any unreadable label is a dummy atom
                parsed = None
    atom = Chem.Atom(parsed.GetAtomicNum() if parsed is not None else 0)
    if parsed is not None:
        atom.SetFormalCharge(parsed.GetFormalCharge())
        atom.SetIsotope(parsed.GetIsotope())
    return atom


def graph(atoms, bonds) -> tuple[list[str], list[tuple[float, float]], list[tuple[int, int, str]]]:
    """(symbols, positions in the 0..1 box, bonds as (atom, atom, word)) of MolScribe's raw
    output, atoms at one position merged. Empty lists for anything unusable."""
    symbols: list[str] = []
    points: list[tuple[float, float]] = []
    index: list[int] = []  # raw atom -> merged atom
    try:
        for atom in atoms:
            point = (float(atom["x"]), float(atom["y"]))
            found = next(
                (
                    i
                    for i, p in enumerate(points)
                    if abs(p[0] - point[0]) <= SAME_POSITION
                    and abs(p[1] - point[1]) <= SAME_POSITION
                ),
                None,
            )
            if found is None:
                found = len(points)
                points.append(point)
                symbols.append(str(atom.get("atom_symbol", "")))
            index.append(found)
        edges: list[tuple[int, int, str]] = []
        seen: set[frozenset[int]] = set()
        for bond in bonds:
            a, b = (int(i) for i in bond["endpoint_atoms"])
            if not (0 <= a < len(index) and 0 <= b < len(index)):
                continue
            a, b = index[a], index[b]
            pair = frozenset((a, b))
            if a == b or pair in seen:
                continue
            seen.add(pair)
            word = bond.get("bond_type")
            edges.append((a, b, word if word in BOND_WORDS else "single"))
    except (TypeError, ValueError, KeyError, AttributeError):
        return [], [], []
    if not all(_finite(x) and _finite(y) for x, y in points):
        return [], [], []
    return symbols, points, edges


def _finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")


def fit_to_ink(grey, points, edges) -> Fit | None:
    """The box (x0, y0, w, h) in pixels that puts `points` (0..1 box) with their `edges` best on
    the ink of `grey` (2D uint8 array). None without ink or edges."""
    import cv2
    import numpy as np
    from scipy.optimize import minimize

    if not edges or len(points) < 2:
        return None
    height, width = grey.shape
    dark = (grey < DARK).astype(np.uint8)
    ys, xs = np.nonzero(dark)
    if xs.size == 0:
        return None
    left, top = float(xs.min()), float(ys.min())
    ink_w, ink_h = max(float(xs.max()) - left, 1.0), max(float(ys.max()) - top, 1.0)
    distance = cv2.distanceTransform(1 - dark, cv2.DIST_L2, 5)
    unit = np.asarray(points, dtype=float)
    first = unit[[e[0] for e in edges]]
    second = unit[[e[1] for e in edges]]
    steps = np.linspace(0.15, 0.85, ALONG)[:, None, None]
    along = (first + (second - first) * steps).reshape(-1, 2)  # in the 0..1 box
    min_w, min_h = MIN_BOX_SHARE * ink_w, MIN_BOX_SHARE * ink_h

    def cost(p) -> float:
        x0, y0, w, h = p
        if w < min_w or h < min_h:  # never collapse onto one stroke
            return 1e6 + (max(min_w - w, 0.0) + max(min_h - h, 0.0))
        xi = np.clip(np.rint(x0 + along[:, 0] * w).astype(int), 0, width - 1)
        yi = np.clip(np.rint(y0 + along[:, 1] * h).astype(int), 0, height - 1)
        return float(distance[yi, xi].mean())

    best = None
    for share in STARTS:
        start = [
            left + (1 - share) / 2 * ink_w,
            top + (1 - share) / 2 * ink_h,
            share * ink_w,
            share * ink_h,
        ]
        found = minimize(
            cost,
            start,
            method="Nelder-Mead",
            options={"xatol": 0.5, "fatol": 0.01, "maxiter": 2000},
        )
        if best is None or found.fun < best.fun:
            best = found
    x0, y0, w, h = (float(v) for v in best.x)
    return Fit(x0, y0, w, h, float(best.fun))


def layout_molfile(image: Path, atoms, bonds) -> str | None:
    """The paper layout of MolScribe's raw `atoms` and `bonds` on `image` (the file the engine
    read), or None: no usable graph, no bond, over MAX_ATOMS atoms, no ink."""
    symbols, points, edges = graph(atoms, bonds)
    if not edges or not 2 <= len(points) <= MAX_ATOMS:
        return None
    import numpy as np
    from PIL import Image

    with Image.open(image) as im:
        grey = np.asarray(im.convert("L"))
    fit = fit_to_ink(grey, points, [e[:2] for e in edges])
    if fit is None:
        return None
    pixels = [(fit.x0 + x * fit.w, fit.y0 + y * fit.h) for x, y in points]
    lengths = sorted(
        ((pixels[a][0] - pixels[b][0]) ** 2 + (pixels[a][1] - pixels[b][1]) ** 2) ** 0.5
        for a, b, _ in edges
    )
    bond = lengths[len(lengths) // 2]
    if bond <= 0:
        return None
    height, width = grey.shape
    return _molfile(
        symbols, pixels, edges, paper_layout.header(fit.error, bond, int(width), int(height))
    )


def _molfile(symbols, pixels, edges, title: str) -> str:
    from rdkit import Chem
    from rdkit.Geometry import Point3D

    orders = {
        "single": Chem.BondType.SINGLE,
        "double": Chem.BondType.DOUBLE,
        "triple": Chem.BondType.TRIPLE,
        "aromatic": Chem.BondType.AROMATIC,
    }
    mol = Chem.RWMol()
    for symbol in symbols:
        mol.AddAtom(atom_of(symbol))
    for a, b, word in edges:
        mol.AddBond(a, b, orders[word])
    conf = Chem.Conformer(len(symbols))
    for i, (x, y) in enumerate(pixels):
        conf.SetAtomPosition(i, Point3D(float(x), -float(y), 0.0))  # y up, as every molfile
    conf.Set3D(False)
    mol.AddConformer(conf)
    mol.UpdatePropertyCache(strict=False)  # never sanitized: the reading as it is
    mol.SetProp("_Name", title)
    return Chem.MolToMolBlock(mol, kekulize=False)
