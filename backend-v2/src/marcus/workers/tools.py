# ruff: noqa: N806  (CDK class handles are CamelCase on purpose)
"""Synchronous tools: CDK depiction and molfile (JVM via JPype), RDKit MCS and similarity.

Ported from v1 (`modules/cdk_wrapper.py`, `modules/depiction.py`, `routers/similarity_router.py`).
Differences from v1: the JVM is started lazily, once per worker process, with -Xmx1g and jars
from MARCUS_CDK_JAR_DIR (baked into the image, never downloaded); PNG comes from CDK's own
raster output (v1 used cairosvg) and is returned base64-encoded.

The pure functions hold the logic; the Celery wrappers at the bottom only add routing and
time limits. Bad user input raises ToolInputError (the API maps it to 422); anything else is
a 500. Tool tasks keep their results (unlike pipeline steps) because the API waits for them.
"""

import base64
import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init

from marcus.core.celery_app import celery_app
from marcus.workers.tool_errors import ToolInputError  # noqa: F401 (re-exported)

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

CDK = "org.openscience.cdk"
JARS = ("cdk-2.10.jar", "centres.jar")
MCS_TIMEOUT_S = 3  # below the 5 s task soft limit
AGREEMENT_THRESHOLD = 0.99  # v1: similarity above this counts as agreement
# A highlight SMARTS (the MCS the compare view shows; the API takes only one it signed for the
# drawn molecule, marcus.api.highlight) is matched by RDKit, the toolkit that made it, on the
# drawn SMILES: there the signed pattern is a known substructure. CDK perceives aromaticity
# differently (a tellurophene is aromatic to RDKit, not to CDK), so it would miss the match and
# search on unbounded; CDK only draws the matched atoms, by index (both read a SMILES in its
# atom order). At most MAX_HIGHLIGHT_MAPPINGS mappings are walked and at most
# MAX_HIGHLIGHT_MATCHES distinct atom sets highlighted. A pattern over MAX_HIGHLIGHT_ATOMS
# atoms, or with recursive SMARTS ($(...), a search per atom), is refused (the API applies the
# same caps).
MAX_HIGHLIGHT_MAPPINGS = 1000
MAX_HIGHLIGHT_MATCHES = 32
MAX_HIGHLIGHT_ATOMS = 128
# Atoms drawn with a glow by their index in the written SMILES (no search): `marks`, where the
# engines' answers differ (the brand orange, frontend tokens.css --orange), and `common`, what
# they share (the highlight's light blue). marcus.workers.differences gives both lists.
MARK_COLOUR = (250, 54, 0)
COMMON_COLOUR = (173, 216, 230)
MAX_MARKS = 250  # = marcus.workers.orient.MAX_ATOMS


# --- JVM -----------------------------------------------------------------------------------


def _jar_dir() -> Path:
    return Path(os.environ.get("MARCUS_CDK_JAR_DIR", "/opt/cdk"))


def _jvm():
    """Start the JVM once per process; return the jpype module. Jars are never downloaded."""
    import jpype

    if not jpype.isJVMStarted():
        jars = [_jar_dir() / name for name in JARS]
        missing = [str(j) for j in jars if not j.is_file()]
        if missing:
            raise RuntimeError(f"CDK jars missing: {', '.join(missing)}")
        jpype.startJVM("-Xmx1g", "-Djava.awt.headless=true", classpath=[str(j) for j in jars])
    return jpype


def _smiles_to_cdk(smiles: str):
    jpype = _jvm()
    builder = jpype.JClass(f"{CDK}.silent.SilentChemObjectBuilder").getInstance()
    parser = jpype.JClass(f"{CDK}.smiles.SmilesParser")(builder)
    try:
        return parser.parseSmiles(smiles)
    except jpype.JException as exc:  # SoftTimeLimitExceeded is not one: it propagates
        raise ToolInputError(f"cannot parse SMILES: {exc}") from exc


def _sdg(molecule):
    jpype = _jvm()
    gen = jpype.JClass(f"{CDK}.layout.StructureDiagramGenerator")()
    try:
        gen.generateCoordinates(molecule)
    except jpype.JException as exc:
        raise ToolInputError(f"cannot lay out molecule: {exc}") from exc
    return gen.getMolecule()


def _drop_plain_h(molecule) -> tuple[list[int], dict[int, int]]:
    """Takes the plain explicit H atoms out of `molecule` (display only, owner decision
    2026-11-26: MolScribe writes H atoms the other engines leave implicit; the stored SMILES
    stays as it is). Each becomes an implicit H of its atom, drawn in that atom's label. An H
    that carries stereo stays an atom: one on a stereocentre (its wedge says the configuration)
    or on a double bond with E/Z; so does an isotope, a charged or bridging H, and H2.

    Returns (the written indices of the atoms left, in their order now; dropped H's written
    index -> its atom's written index)."""
    jpype = _jvm()
    IAtom = jpype.JClass(f"{CDK}.interfaces.IAtom")
    IBond = jpype.JClass(f"{CDK}.interfaces.IBond")
    count = molecule.getAtomCount()
    stereo: set[int] = set()
    for element in molecule.stereoElements():
        for obj in [element.getFocus(), *element.getCarriers()]:
            if isinstance(obj, IBond):
                stereo.update((molecule.indexOf(obj.getBegin()), molecule.indexOf(obj.getEnd())))
            elif isinstance(obj, IAtom):
                stereo.add(molecule.indexOf(obj))
    moved: dict[int, int] = {}
    for i in range(count):
        atom = molecule.getAtom(i)
        if atom.getAtomicNumber() != 1 or atom.getMassNumber() is not None or i in stereo:
            continue
        if (atom.getFormalCharge() or 0) != 0 or molecule.getConnectedBondsCount(atom) != 1:
            continue
        bond = molecule.getConnectedBondsList(atom).get(0)
        base = molecule.indexOf(bond.getOther(atom))
        if molecule.getAtom(base).getAtomicNumber() == 1 or base in stereo:
            continue
        moved[i] = base
    for i in sorted(moved, reverse=True):
        base = molecule.getAtom(moved[i])
        hydrogens = int(base.getImplicitHydrogenCount() or 0) + 1
        base.setImplicitHydrogenCount(jpype.JClass("java.lang.Integer").valueOf(hydrogens))
        molecule.removeAtom(molecule.getAtom(i))
    return [i for i in range(count) if i not in moved], moved


def _layout(molecule, smiles: str, template: str | list[str], kept: list[int] | None = None):
    """2D positions for `molecule` (CDK's reading of `smiles`): the paper's orientation from an
    OCSR template molfile (marcus.workers.orient, RDKit, same atom order as CDK) when it can
    be had, else CDK's own layout. `template`: one molfile, or candidates in the order they are
    preferred (the first with the image's positions is used, orient.first_template). Wedges are
    set from the stereo on the given positions. `kept`: the written indices of the molecule's
    atoms when some written atoms were taken out (_drop_plain_h); None: all are there."""
    from marcus.workers import orient  # RDKit, as the highlight match: only where it runs

    candidates = [template] if isinstance(template, str) else list(template or [])
    chosen = orient.first_template(candidates)
    coords = orient.oriented_coords(smiles, chosen) if chosen else None
    if kept is None:
        kept = list(range(molecule.getAtomCount()))
        written = len(kept)
    else:
        written = len(coords) if coords is not None and max(kept, default=-1) < len(coords) else -1
    if coords is None or len(coords) != written or len(kept) != molecule.getAtomCount():
        return _sdg(molecule)
    jpype = _jvm()
    point = jpype.JClass("javax.vecmath.Point2d")
    for i, source in enumerate(kept):
        x, y = coords[source]
        molecule.getAtom(i).setPoint2d(point(float(x), float(y)))
    # the ring flags CDK's layout sets on its way: the CIP step's ring test reads them
    jpype.JClass(f"{CDK}.graph.Cycles").markRingAtomsAndBonds(molecule)
    try:
        jpype.JClass(f"{CDK}.layout.NonplanarBonds").assign(molecule)
    except jpype.JException:
        return _sdg(molecule)  # stereo CDK cannot place on these positions: its own layout
    return molecule


def _cip_annotate(mol):
    """v1 get_cip_annotation(add_coordinates=False): CIP labels as StandardGenerator annotations."""
    jpype = _jvm()
    J = jpype.JClass
    Cycles = J(f"{CDK}.graph.Cycles")
    IBond = J(f"{CDK}.interfaces.IBond")
    IStereoElement = J(f"{CDK}.interfaces.IStereoElement")
    Stereocenters = J(f"{CDK}.stereo.Stereocenters")
    Std = J(f"{CDK}.renderer.generators.standard.StandardGenerator")
    BaseMol = J("com.simolecule.centres.BaseMol")
    CdkLabeller = J("com.simolecule.centres.CdkLabeller")
    Descriptor = J("com.simolecule.centres.Descriptor")

    centers = Stereocenters.of(mol)
    for atom in mol.atoms():
        idx = atom.getIndex()
        if (
            centers.isStereocenter(idx)
            and centers.elementType(idx) == Stereocenters.Type.Tetracoordinate
        ):
            atom.setProperty(Std.ANNOTATION_LABEL, "(?)")
    for bond in mol.bonds():
        if bond.getOrder() != IBond.Order.DOUBLE:
            continue
        beg, end = bond.getBegin().getIndex(), bond.getEnd().getIndex()
        if (
            centers.elementType(beg) == Stereocenters.Type.Tricoordinate
            and centers.elementType(end) == Stereocenters.Type.Tricoordinate
            and centers.isStereocenter(beg)
            and centers.isStereocenter(end)
            and Cycles.smallRingSize(bond, 7) == 0
        ):
            bond.setProperty(Std.ANNOTATION_LABEL, "(?)")

    if not mol.stereoElements().iterator().hasNext():
        return mol

    CdkLabeller.label(mol)

    for se in mol.stereoElements():
        if se.getConfigClass() == IStereoElement.TH and se.getGroupInfo() != 0:
            focus = se.getFocus()
            label = focus.getProperty(BaseMol.CIP_LABEL_KEY)
            if (
                isinstance(label, Descriptor)
                and label != Descriptor.ns
                and label != Descriptor.Unknown
            ):
                if (se.getGroupInfo() & IStereoElement.GRP_RAC) != 0:
                    inv = {Descriptor.R: Descriptor.S, Descriptor.S: Descriptor.R}.get(label)
                    if inv is not None:
                        focus.setProperty(BaseMol.CIP_LABEL_KEY, label.toString() + inv.name())
                elif (se.getGroupInfo() & IStereoElement.GRP_REL) != 0:
                    if label == Descriptor.R or label == Descriptor.S:
                        focus.setProperty(BaseMol.CIP_LABEL_KEY, label.toString() + "*")

    italic = Std.ITALIC_DISPLAY_PREFIX
    for atom in mol.atoms():
        conf = atom.getProperty(BaseMol.CONF_INDEX)
        cip = atom.getProperty(BaseMol.CIP_LABEL_KEY)
        if conf is not None:
            atom.setProperty(Std.ANNOTATION_LABEL, italic + conf.toString())
        elif cip is not None:
            atom.setProperty(Std.ANNOTATION_LABEL, italic + cip.toString())
    for bond in mol.bonds():
        cip = bond.getProperty(BaseMol.CIP_LABEL_KEY)
        if cip is not None:
            bond.setProperty(Std.ANNOTATION_LABEL, italic + cip.toString())
    return mol


# --- pure functions ------------------------------------------------------------------------


def depict(
    smiles: str,
    fmt: Literal["svg", "png"],
    width: int,
    height: int,
    highlight: str = "",
    template: str | list[str] = "",
    marks: list[int] | None = None,
    common: list[int] | None = None,
) -> str:
    """CDK StandardGenerator depiction (v1 defaults: kekulize, CIP, CDK2D colours, white
    background, fill-to-fit). SVG as text; PNG as base64. `highlight` is an optional SMARTS.
    `template`: an OCSR molfile with the image's atom positions, or candidates in order; the
    drawing then follows the paper's orientation where it can (_layout). `marks` / `common`:
    atoms by their index in the written SMILES, drawn with an orange / a light blue outer glow
    (MARK_COLOUR, COMMON_COLOUR). A plain explicit H is not drawn as an atom (_drop_plain_h)."""
    jpype = _jvm()
    J = jpype.JClass
    mol = _smiles_to_cdk(smiles)
    written = mol.getAtomCount()
    glows = [(_checked_indices(common, written), COMMON_COLOUR)]
    glows.append((_checked_indices(marks, written), MARK_COLOUR))
    try:
        kept, moved = _drop_plain_h(mol)
        place = {source: i for i, source in enumerate(kept)}
        place.update({h: place[base] for h, base in moved.items()})
        mol = _cip_annotate(_layout(mol, smiles, template, kept if moved else None))
        try:
            J(f"{CDK}.aromaticity.Kekulization").kekulize(mol)
        except jpype.JException:  # v1 logged and carried on; soft limits still propagate
            pass

        Std = J(f"{CDK}.renderer.generators.standard.StandardGenerator")
        gen = (
            J(f"{CDK}.depict.DepictionGenerator")()
            .withAtomColors(J(f"{CDK}.renderer.color.CDK2DAtomColors")())
            .withSize(width, height)
            .withParam(Std.StrokeRatio.class_, 1.0)
            .withFillToFit()
            .withBackgroundColor(J("java.awt.Color").WHITE)
        )
        if highlight.strip():
            matches = [
                ([place[i] for i in atoms], [(place[i], place[j]) for i, j in bonds])
                for atoms, bonds in _highlight_matches(smiles, highlight)
            ]
            gen = gen.withHighlight(
                _highlight_objects(mol, matches), J("java.awt.Color")(*COMMON_COLOUR)
            ).withOuterGlowHighlight()
        for indices, colour in glows:
            if indices:
                objects = _index_objects(mol, sorted({place[i] for i in indices}))
                gen = gen.withHighlight(objects, J("java.awt.Color")(*colour))
                gen = gen.withOuterGlowHighlight()

        depiction = gen.depict(mol)
        if fmt == "svg":
            # v1 round-trips through ElementTree, which drops the XML declaration and DOCTYPE
            return ET.tostring(ET.fromstring(str(depiction.toSvgStr("px"))), encoding="unicode")
        out = J("java.io.ByteArrayOutputStream")()
        J("javax.imageio.ImageIO").write(depiction.toImg(), "png", out)
        return base64.b64encode(bytes(out.toByteArray())).decode("ascii")
    except (ToolInputError, SoftTimeLimitExceeded):
        raise
    except jpype.JException as exc:
        raise ToolInputError(f"cannot depict molecule: {exc}") from exc


def _highlight_mol(smiles: str):
    """RDKit's reading of the drawn SMILES with every written atom kept ([H] included), so its
    atom indices are CDK's; ToolInputError when RDKit cannot read it."""
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    params = Chem.SmilesParserParams()
    params.removeHs = False
    with BlockLogs():
        mol = Chem.MolFromSmiles(smiles, params)
    if mol is None:
        raise ToolInputError("cannot read the SMILES for the highlight")
    return mol


def _highlight_matches(
    smiles: str, highlight: str
) -> list[tuple[list[int], list[tuple[int, int]]]]:
    """The highlight's matches in the drawn SMILES, matched by RDKit: per distinct atom set, its
    atom indices and the index pairs of the pattern's bonds. ToolInputError for a pattern that
    is unreadable, recursive or over MAX_HIGHLIGHT_ATOMS."""
    from rdkit import Chem

    if "$" in highlight:
        raise ToolInputError("recursive SMARTS are not allowed in a highlight")
    query = Chem.MolFromSmarts(highlight)
    if query is None:
        raise ToolInputError("invalid highlight SMARTS")
    if query.GetNumAtoms() > MAX_HIGHLIGHT_ATOMS:
        raise ToolInputError(f"highlight has more than {MAX_HIGHLIGHT_ATOMS} atoms")
    mol = _highlight_mol(smiles)
    found: list[tuple[list[int], list[tuple[int, int]]]] = []
    seen: set[frozenset[int]] = set()
    mappings = mol.GetSubstructMatches(
        query, uniquify=False, maxMatches=MAX_HIGHLIGHT_MAPPINGS, useChirality=False
    )
    for mapping in mappings:
        atoms = frozenset(mapping)
        if atoms in seen:
            continue
        seen.add(atoms)
        bonds = [
            (mapping[b.GetBeginAtomIdx()], mapping[b.GetEndAtomIdx()]) for b in query.GetBonds()
        ]
        found.append((list(mapping), bonds))
        if len(found) == MAX_HIGHLIGHT_MATCHES:
            break
    return found


def _highlight_objects(mol, matches):
    """The CDK atoms and bonds of `matches` (RDKit indices, the same in CDK's reading)."""
    jpype = _jvm()
    chosen = jpype.JClass("java.util.LinkedHashSet")()
    count = mol.getAtomCount()
    for atoms, bonds in matches:
        if any(i >= count for i in atoms):
            raise ToolInputError("highlight does not fit the drawn molecule")
        for i in atoms:
            chosen.add(mol.getAtom(i))
        for i, j in bonds:
            bond = mol.getBond(mol.getAtom(i), mol.getAtom(j))
            if bond is not None:
                chosen.add(bond)
    return chosen


def _checked_indices(indices: list[int] | None, count: int) -> list[int]:
    """`marks` / `common` as given, or ToolInputError: at most MAX_MARKS whole numbers, each an
    atom of the written SMILES (`count` atoms)."""
    indices = list(indices or [])
    if len(indices) > MAX_MARKS:
        raise ToolInputError(f"more than {MAX_MARKS} marked atoms")
    if any(type(i) is not int or not 0 <= i < count for i in indices):
        raise ToolInputError("a marked atom is not in the drawn molecule")
    if len(set(indices)) != len(indices):
        raise ToolInputError("marked atoms must be distinct")
    return indices


def _index_objects(mol, indices: list[int]):
    """The CDK atoms at `indices` (of `mol` as it is drawn) and the bonds between two of them."""
    jpype = _jvm()
    chosen = jpype.JClass("java.util.LinkedHashSet")()
    wanted = set(indices)
    for i in indices:
        chosen.add(mol.getAtom(i))
    for bond in mol.bonds():
        if mol.indexOf(bond.getBegin()) in wanted and mol.indexOf(bond.getEnd()) in wanted:
            chosen.add(bond)
    return chosen


def differences(smiles: list[str]) -> dict[str, Any]:
    """Where the answers differ and what they share, per answer as atom indices in the written
    SMILES' order (marcus.workers.differences; the lists `depict` takes as marks / common)."""
    from marcus.workers import differences as module

    try:
        return module.differences(smiles)
    except module.DifferencesError as exc:
        raise ToolInputError(str(exc)) from exc


def smiles_to_molfile(smiles: str, template: str | list[str] = "") -> str:
    """CDK structure diagram layout as a V2000 molfile (v1 get_CDK_SDG_mol); with `template`
    (the paper's layout, as depict takes it) the atoms sit as in the drawing (_layout), so the
    editor opens an engine's answer laid out like the paper (owner, 2026-11-27)."""
    jpype = _jvm()
    J = jpype.JClass
    mol = _smiles_to_cdk(smiles)
    mol = _layout(mol, smiles, template) if template else _sdg(mol)
    writer_out = J("java.io.StringWriter")()
    sdf = J(f"{CDK}.io.SDFWriter")(writer_out)
    try:
        sdf.setAlwaysV3000(False)
        sdf.write(mol)
        sdf.flush()
    finally:
        sdf.close()
    return str(writer_out.toString())


def _mol_from_molfile(molfile: str):
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(molfile, sanitize=True)
    if mol is None:  # v1: retry unsanitized, then sanitize explicitly
        try:
            mol = Chem.MolFromMolBlock(molfile, sanitize=False)
            if mol is not None:
                Chem.SanitizeMol(mol)
        except (ValueError, RuntimeError):  # RDKit sanitize errors subclass ValueError
            mol = None
    return mol


def mcs(molfiles: list[str]) -> dict[str, Any]:
    """Maximum common substructure of >= 2 parseable molfiles (v1 /similarity/find_mcs)."""
    from rdkit.Chem import rdFMCS

    mols = [m for m in (_mol_from_molfile(f) for f in molfiles) if m is not None]
    if len(mols) < 2:
        raise ToolInputError("at least 2 valid molecules are required to find MCS")
    result = rdFMCS.FindMCS(
        mols,
        atomCompare=rdFMCS.AtomCompare.CompareElements,
        bondCompare=rdFMCS.BondCompare.CompareOrder,
        completeRingsOnly=True,
        timeout=MCS_TIMEOUT_S,
        matchValences=False,
    )
    if result.canceled:
        raise ToolInputError("mcs timed out")
    return {
        "mcs_smarts": result.smartsString,
        "atom_count": result.numAtoms,
        "bond_count": result.numBonds,
        "original_molecules": [
            {"atom_count": m.GetNumAtoms(), "bond_count": m.GetNumBonds()} for m in mols
        ],
    }


def compare(smiles_a: str, smiles_b: str) -> dict[str, Any]:
    """ECFP4 (Morgan r=2, 2048 bits) Tanimoto of two SMILES, as v1 /similarity/compare_smiles."""
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem

    mols = []
    for label, smi in (("a", smiles_a), ("b", smiles_b)):
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            raise ToolInputError(f"cannot parse SMILES {label}")
        mols.append(mol)
    fps = [AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048) for m in mols]
    sim = DataStructs.TanimotoSimilarity(fps[0], fps[1])
    return {
        "tanimoto": sim,
        "identical": smiles_a == smiles_b,
        "same_structure": Chem.MolToSmiles(mols[0]) == Chem.MolToSmiles(mols[1]),
        "agree": sim > AGREEMENT_THRESHOLD,
    }


# --- worker process start ------------------------------------------------------------------


@worker_process_init.connect
def warm_up_jvm(**_) -> None:
    """Start the JVM and load the CDK layout and depiction classes when a pool process starts
    (after the fork), not in the first tool task: measured in the tools image, JVM start +
    first molfile ~3.5 s and first depiction ~3 s, against a 5 s soft limit. A failure is
    only logged; the first task then raises the real error."""
    try:
        smiles_to_molfile("C")
        depict("C", "svg", 64, 64, "")
        depict("C", "png", 64, 64, "")  # the raster path loads its own classes (~1.3 s)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("JVM warm-up failed")


# --- Celery wrappers -----------------------------------------------------------------------
# Each task returns a JSON envelope: {"ok": true, "result": ...} or, for bad input,
# {"ok": false, "error": "..."}. The API never needs to import ToolInputError (it cannot
# rebuild exceptions from the result backend without the tools extra). Other errors raise.

_LIMITS = {"soft_time_limit": 5, "time_limit": 10}  # routed to q.tools by task_routes


def _envelope(fn, *args) -> dict:
    try:
        return {"ok": True, "result": fn(*args)}
    except ToolInputError as exc:
        return {"ok": False, "error": str(exc)[:300]}


@celery_app.task(name="marcus.tools.depict", **_LIMITS)
def depict_task(
    smiles: str,
    fmt: str = "svg",
    width: int = 512,
    height: int = 512,
    highlight: str = "",
    template: str | list[str] = "",
    marks: list[int] | None = None,
    common: list[int] | None = None,
) -> dict:
    return _envelope(depict, smiles, fmt, width, height, highlight, template, marks, common)


@celery_app.task(name="marcus.tools.smiles_to_molfile", **_LIMITS)
def smiles_to_molfile_task(smiles: str, template: str | list[str] = "") -> dict:
    return _envelope(smiles_to_molfile, smiles, template)


@celery_app.task(name="marcus.tools.mcs", **_LIMITS)
def mcs_task(molfiles: list[str]) -> dict:
    return _envelope(mcs, molfiles)


@celery_app.task(name="marcus.tools.differences", **_LIMITS)
def differences_task(smiles: list[str]) -> dict:
    return _envelope(differences, smiles)


@celery_app.task(name="marcus.tools.compare", **_LIMITS)
def compare_task(smiles_a: str, smiles_b: str) -> dict:
    return _envelope(compare, smiles_a, smiles_b)


@celery_app.task(name="marcus.tools.paper_view", **_LIMITS)
def paper_view_task(smiles: list[str], layout: str) -> dict:
    """An image's answers on its paper layout: overlay geometry and marks
    (marcus.workers.paper_view; RDKit only, its searches share one budget under the limit)."""
    from marcus.workers.paper_view import paper_view  # RDKit: only where it runs

    return _envelope(paper_view, smiles, layout)
