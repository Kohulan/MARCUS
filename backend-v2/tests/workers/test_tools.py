"""Tool task pure functions against a real JVM (CDK) and RDKit. v1 values: fixtures/v1_tools.json."""

import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

CDK_DIR = Path(
    os.environ.get("MARCUS_CDK_JAR_DIR", "/home/kohulan/MARCUS/judges/stack/data/cache/CDK_Jar")
)
FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "v1_tools.json").read_text())

needs_cdk = pytest.mark.skipif(
    not (CDK_DIR / "cdk-2.10.jar").exists() or not (CDK_DIR / "centres.jar").exists(),
    reason=f"CDK jars (cdk-2.10.jar, centres.jar) not found in {CDK_DIR}",
)


@pytest.fixture(autouse=True)
def _jar_dir(monkeypatch):
    monkeypatch.setenv("MARCUS_CDK_JAR_DIR", str(CDK_DIR))


def test_tasks_registered_on_tools_queue():
    from marcus.core.celery_app import celery_app
    from marcus.workers import tools  # noqa: F401  (registers the tasks)

    for name in ("depict", "smiles_to_molfile", "mcs", "compare"):
        task = celery_app.tasks[f"marcus.tools.{name}"]
        assert task.soft_time_limit == 5 and task.time_limit == 10
        assert not task.ignore_result

    assert celery_app.amqp.router.route({}, "marcus.tools.mcs")["queue"].name == "q.tools"


@needs_cdk
def test_depict_svg_for_benzene():
    from marcus.workers.tools import depict

    svg = depict("c1ccccc1", "svg", 300, 300)
    assert svg.lstrip().startswith("<svg") and "</svg>" in svg


@needs_cdk
def test_depict_png_is_base64_png():
    from marcus.workers.tools import depict

    out = depict("CC(=O)O", "png", 200, 150)
    raw = base64.b64decode(out)
    assert raw.startswith(b"\x89PNG")


@needs_cdk
def test_depict_bad_smiles_is_input_error():
    from marcus.workers.tools import ToolInputError, depict

    with pytest.raises(ToolInputError):
        depict("C1CC(", "svg", 200, 200)


@needs_cdk
def test_smiles_to_molfile_has_coordinates():
    from rdkit import Chem

    from marcus.workers.tools import smiles_to_molfile

    mf = smiles_to_molfile(FIXTURE["smiles_to_molfile"]["request"]["smiles"])
    assert "V2000" in mf
    mol = Chem.MolFromMolBlock(mf)
    conf = mol.GetConformer()
    assert conf.Is3D() is False
    assert any(abs(conf.GetAtomPosition(i).x) > 0 for i in range(mol.GetNumAtoms()))
    assert mol.GetNumAtoms() == 7


def test_mcs_of_two_known_molecules():
    from marcus.workers.tools import mcs

    req, expected = FIXTURE["find_mcs"]["request"], FIXTURE["find_mcs"]["response"]
    out = mcs(req["molfiles"])
    assert out["mcs_smarts"] == expected["mcs_smarts"]
    assert out["atom_count"] == expected["atom_count"]
    assert out["bond_count"] == expected["bond_count"]
    assert [(m["atom_count"], m["bond_count"]) for m in out["original_molecules"]] == [
        (m["atom_count"], m["bond_count"]) for m in expected["original_molecules"]
    ]


def test_mcs_needs_two_valid_molfiles():
    from marcus.workers.tools import ToolInputError, mcs

    mf = FIXTURE["find_mcs"]["request"]["molfiles"][0]
    with pytest.raises(ToolInputError):
        mcs([mf, "garbage"])


def test_compare_matches_v1_tanimoto():
    from marcus.workers.tools import compare

    exp = FIXTURE["compare_smiles"]["response"]["matrix"][0][1]
    out = compare("CCO", "CCN")
    assert out["tanimoto"] == pytest.approx(exp)
    assert out["identical"] is False
    assert compare("CCO", "OCC")["tanimoto"] == 1.0


def test_compare_bad_smiles_is_input_error():
    from marcus.workers.tools import ToolInputError, compare

    with pytest.raises(ToolInputError):
        compare("CCO", "not a smiles(")


@needs_cdk
@pytest.mark.parametrize(
    "name,good,bad",
    [
        (
            "depict",
            {"smiles": "CCO", "fmt": "svg", "width": 100, "height": 100},
            {"smiles": "C1CC(", "fmt": "svg", "width": 100, "height": 100},
        ),
        ("smiles_to_molfile", {"smiles": "CCO"}, {"smiles": "C1CC("}),
        ("mcs", {"molfiles": FIXTURE["find_mcs"]["request"]["molfiles"]}, {"molfiles": ["x", "y"]}),
        (
            "compare",
            {"smiles_a": "CCO", "smiles_b": "CCN"},
            {"smiles_a": "CCO", "smiles_b": "C1CC("},
        ),
    ],
)
def test_task_envelope_is_json_and_flags_bad_input(name, good, bad):
    from marcus.core.celery_app import celery_app
    from marcus.workers import tools  # noqa: F401  (registers the tasks)

    task = celery_app.tasks[f"marcus.tools.{name}"]
    ok = task.apply(kwargs=good).get()
    assert json.loads(json.dumps(ok)) == ok and ok["ok"] is True and "result" in ok
    err = task.apply(kwargs=bad).get()
    assert json.loads(json.dumps(err)) == err
    assert err["ok"] is False and isinstance(err["error"], str) and err["error"]


def test_mcs_timeout_is_not_a_partial_result(monkeypatch):
    from rdkit.Chem import rdFMCS

    from marcus.workers import tools

    seen = {}

    res = SimpleNamespace(canceled=True, smartsString="[#6]", numAtoms=1, numBonds=1)

    def fake(mols, **kw):
        seen.update(kw)
        return res

    monkeypatch.setattr(rdFMCS, "FindMCS", fake)
    out = tools.mcs_task.apply(
        kwargs={"molfiles": FIXTURE["find_mcs"]["request"]["molfiles"]}
    ).get()
    assert seen["timeout"] == 3
    assert out == {"ok": False, "error": "mcs timed out"}


@needs_cdk
@pytest.mark.parametrize("target", ["_cip_annotate", "_sdg"])
def test_soft_time_limit_is_not_turned_into_bad_input(monkeypatch, target):
    from celery.exceptions import SoftTimeLimitExceeded

    from marcus.workers import tools

    def boom(*a, **k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tools, target, boom)
    with pytest.raises(SoftTimeLimitExceeded):
        tools.depict("CCO", "svg", 100, 100)
    with pytest.raises(SoftTimeLimitExceeded):  # through the task wrapper too: no envelope
        tools.depict_task.apply(
            kwargs={"smiles": "CCO", "fmt": "svg", "width": 100, "height": 100},
            throw=True,
        )


def test_jvm_starts_when_the_worker_process_starts(monkeypatch):
    """JVM start + CDK class loading (~3.5 s molfile, ~3 s depiction, measured in the tools
    image) is most of the 5 s soft limit: it happens at worker process init, not in a task."""
    from celery.signals import worker_process_init

    from marcus.workers import tools

    calls = []
    monkeypatch.setattr(tools, "smiles_to_molfile", lambda s: calls.append(("molfile", s)))
    monkeypatch.setattr(tools, "depict", lambda s, fmt, *args: calls.append((fmt, s)))
    assert tools.warm_up_jvm in [r() for _, r in worker_process_init.receivers]
    worker_process_init.send(sender=None)
    assert calls == [("molfile", "C"), ("svg", "C"), ("png", "C")]


def test_jvm_warm_up_failure_does_not_kill_the_worker_process(monkeypatch, caplog):
    from marcus.workers import tools

    def boom(smiles):
        raise RuntimeError("CDK jars missing")

    monkeypatch.setattr(tools, "smiles_to_molfile", boom)
    tools.warm_up_jvm()  # logged; the first task then reports the real error
    assert "JVM warm-up failed" in caplog.text


def test_worker_waits_long_enough_for_a_process_warm_up():
    from marcus.core.celery_app import celery_app

    assert celery_app.conf.worker_proc_alive_timeout >= 30


C60 = (
    "c12c3c4c5c1c1c6c7c2c2c8c3c3c9c4c4c%10c5c5c1c1c6c6c%11c7c2c2c7c8c3c3c8c9c4c4c9c%10c5c5c1"
    "c1c6c6c%11c2c2c7c3c3c8c4c4c9c5c1c1c6c2c3c41"
)


@needs_cdk
def test_depict_highlight_walks_a_bounded_number_of_matches():
    """A 30-atom any-atom chain has an astronomic number of matches in C60: only the first
    MAX_HIGHLIGHT_MATCHES (unique atom sets) are walked, well inside the 5 s soft limit."""
    import time

    from marcus.workers.tools import depict

    start = time.perf_counter()
    svg = depict(C60, "svg", 300, 300, highlight="~".join(["*"] * 30))
    assert svg.startswith("<svg") and time.perf_counter() - start < 3


@needs_cdk
@pytest.mark.parametrize(
    "highlight",
    ["~".join(["*"] * 129), "[$(*~*~*)]~*", "[$([#6]~[#7])]"],
    ids=["too-many-atoms", "recursive", "recursive-bracket"],
)
def test_depict_refuses_an_over_cap_highlight(highlight):
    from marcus.workers.tools import ToolInputError, depict

    with pytest.raises(ToolInputError):
        depict("CCO", "svg", 200, 200, highlight=highlight)


@needs_cdk
def test_depict_highlight_at_the_atom_cap_is_drawn():
    from marcus.workers.tools import MAX_HIGHLIGHT_ATOMS, depict

    assert MAX_HIGHLIGHT_ATOMS == 128
    assert depict("CCO", "svg", 200, 200, highlight="~".join(["*"] * 128)).startswith("<svg")
    assert depict("CCO", "svg", 200, 200, highlight="[#6]-[#8]").startswith("<svg")


BINDING_CASES = [
    "CCO",
    "c1ccccc1O",
    "C[C@H](N)C(=O)O",  # stereo: dropped from the key on both sides
    "F/C=C/F",
    "C[N+](=O)[O-]",
    "CN(=O)=O",  # nitro written pentavalent
    "[Na+].[Cl-]",
    "c1ccc2[nH]ccc2c1",
    "O=C1c2ccccc2C(=O)c2ccccc21",
    "CC(C)(C)[Si](C)(C)OC",
]


@needs_cdk
@pytest.mark.parametrize("smiles", BINDING_CASES)
def test_highlight_binding_agrees_for_a_smiles_and_its_molfiles(smiles):
    """F5: Compare's MCS takes each prediction's molfile (the engine's, made by RDKit, or CDK's
    /tools/smiles-to-molfile) and draws the prediction's SMILES; the server's binding key of
    both must be the same, or the highlight would be refused."""
    from rdkit import Chem

    from marcus.api.highlight import binding_key_of_smiles, binding_keys_of_molfiles
    from marcus.workers.tools import smiles_to_molfile

    drawn = binding_key_of_smiles(smiles)
    assert drawn is not None
    cdk = smiles_to_molfile(smiles)
    rdkit = Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))
    assert binding_keys_of_molfiles([cdk]) == [drawn]
    assert binding_keys_of_molfiles([rdkit]) == [drawn]


@needs_cdk
def test_mcs_smarts_highlights_each_of_its_molecules():
    """The happy path of a signed highlight: the MCS SMARTS of two molecules, drawn on each,
    gives a highlighted drawing (CDK's outer glow), unlike the plain one."""
    from rdkit import Chem

    from marcus.workers.tools import depict, mcs

    molfiles = [Chem.MolToMolBlock(Chem.MolFromSmiles(s)) for s in ("c1ccccc1CO", "c1ccccc1CN")]
    smarts = mcs(molfiles)["mcs_smarts"]
    assert smarts
    for smiles in ("c1ccccc1CO", "c1ccccc1CN"):
        plain = depict(smiles, "svg", 300, 300)
        lit = depict(smiles, "svg", 300, 300, highlight=smarts)
        assert lit != plain and "#add8e6" in lit.lower()


@needs_cdk
def test_depict_highlight_bounds_the_raw_mappings_walked():
    """Many mappings, few distinct atom sets (13 disconnected atoms on a 13-atom ring: 13!
    mappings, one set): at most MAX_HIGHLIGHT_MAPPINGS mappings are walked, not every one."""
    import time

    from marcus.workers.tools import MAX_HIGHLIGHT_MAPPINGS, depict

    assert MAX_HIGHLIGHT_MAPPINGS == 1000
    start = time.perf_counter()
    svg = depict("C1CCCCCCCCCCCC1", "svg", 200, 200, highlight=".".join(["*"] * 13))
    assert svg.startswith("<svg") and time.perf_counter() - start < 3


# --- the highlight is matched in RDKit, never searched by CDK (re-review I-1) ------------------

TELLUROPHENES = ("c1cc[te]c1", "Cc1cc[te]c1")  # RDKit: aromatic; CDK's Daylight model: not

ORDER_CASES = [
    "[H]C([H])([H])O",  # explicit hydrogens are atoms on both sides
    "[2H]C([2H])O",
    "C[N+](=O)[O-]",
    "[NH4+].[Cl-]",
    "c1cc[te]c1",
    "OC(=O)c1ccc[nH]1",
    "C1CC2CCC1C2",  # ring closures: bonds written out of atom order
    "C[C@H](N)C(=O)O",
    "[H]c1ccc2ccccc2c1",
]


@needs_cdk
@pytest.mark.parametrize("smiles", ORDER_CASES)
def test_rdkit_and_cdk_read_a_smiles_in_the_same_atom_order(smiles):
    """The RDKit match is drawn by CDK by atom index: both must keep the SMILES's atom order
    and see the same bonds between the same indices (on the laid-out molecule depict draws)."""
    from marcus.workers.tools import _highlight_mol, _sdg, _smiles_to_cdk

    rd = _highlight_mol(smiles)
    cdk = _sdg(_smiles_to_cdk(smiles))
    assert cdk.getAtomCount() == rd.GetNumAtoms()
    for i, atom in enumerate(rd.GetAtoms()):
        other = cdk.getAtom(i)
        assert int(other.getAtomicNumber()) == atom.GetAtomicNum(), (smiles, i)
        assert int(other.getFormalCharge() or 0) == atom.GetFormalCharge(), (smiles, i)
    rd_bonds = {frozenset((b.GetBeginAtomIdx(), b.GetEndAtomIdx())) for b in rd.GetBonds()}
    cdk_bonds = {
        frozenset((int(b.getBegin().getIndex()), int(b.getEnd().getIndex()))) for b in cdk.bonds()
    }
    assert cdk_bonds == rd_bonds


class _NoCdkSearch:
    """jpype, refusing CDK's SMARTS and substructure classes: depict must not search in CDK."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def JClass(self, name):  # noqa: N802
        assert ".smarts." not in name and ".isomorphism." not in name, name
        return self._real.JClass(name)


@needs_cdk
def test_tellurophene_mcs_highlight_is_drawn_without_a_cdk_search(monkeypatch):
    """A signed MCS SMARTS of tellurophenes uses aromatic bonds, which CDK does not perceive
    there: CDK would find no match (and search unbounded). The match is RDKit's, under the
    model that made the SMARTS, so it is found and drawn, and CDK runs no search."""
    from rdkit import Chem

    from marcus.workers import tools

    molfiles = [Chem.MolToMolBlock(Chem.MolFromSmiles(s)) for s in TELLUROPHENES]
    smarts = tools.mcs(molfiles)["mcs_smarts"]
    assert ":" in smarts  # aromatic bonds in the pattern
    real = tools._jvm()
    monkeypatch.setattr(tools, "_jvm", lambda: _NoCdkSearch(real))
    for smiles in TELLUROPHENES:
        lit = tools.depict(smiles, "svg", 300, 300, highlight=smarts)
        assert "#add8e6" in lit.lower(), smiles


@needs_cdk
def test_highlight_with_explicit_hydrogens_lands_on_the_right_atoms(monkeypatch):
    """[H] atoms shift every later index if one side drops them: the highlighted atoms must
    be the pattern's (the O and its C), not their neighbours."""
    from marcus.workers import tools

    seen = []
    real = tools._highlight_objects

    def spy(mol, matches):
        objs = real(mol, matches)
        seen.append(sorted(str(o.getSymbol()) for o in objs if hasattr(o, "getSymbol")))
        return objs

    monkeypatch.setattr(tools, "_highlight_objects", spy)
    tools.depict("[H]C([H])([H])O", "svg", 200, 200, highlight="[#6]-[#8]")
    assert seen == [["C", "O"]]


# --- the paper's orientation (marcus.workers.orient) ---------------------------------------


def _ocsr_template(smiles: str, degrees: float) -> str:
    """A molfile as MolNexTR/MolScribe write it for a square crop of `smiles` turned by
    `degrees` (tests/workers/test_orient.py has the construction)."""
    from tests.workers.test_orient import _layout, _ocsr_molfile

    mol, pos = _layout(smiles, degrees)
    return _ocsr_molfile(mol, pos, width=12.0, height=12.0)[0]


@needs_cdk
def test_depict_with_a_template_draws_the_oriented_positions():
    from marcus.workers import tools
    from marcus.workers.orient import oriented_coords

    smiles = "OC(=O)/C=C/c1ccc(O)c(OC)c1"
    template = _ocsr_template("COc1cc(/C=C/C(=O)O)ccc1O", 70)
    mol = tools._layout(tools._smiles_to_cdk(smiles), smiles, template)
    want = oriented_coords(smiles, template)
    assert want is not None
    for i, (x, y) in enumerate(want):
        point = mol.getAtom(i).getPoint2d()
        assert (point.x, point.y) == pytest.approx((x, y))
    svg = tools.depict(smiles, "svg", 300, 300, "", template)
    assert svg.lstrip().startswith("<svg")
    assert svg != tools.depict(smiles, "svg", 300, 300)


@needs_cdk
def test_depict_keeps_its_stereo_wedges_on_template_positions():
    from marcus.workers import tools

    smiles = "C[C@H](N)c1ccc(O)cc1"
    template = _ocsr_template("CC(N)c1ccc(O)cc1", 200)
    mol = tools._layout(tools._smiles_to_cdk(smiles), smiles, template)
    displays = {str(b.getDisplay()) for b in mol.bonds()}
    assert displays - {"Solid"}, displays  # a wedge or hash for the stereocentre


@needs_cdk
def test_depict_on_template_positions_labels_like_its_own_layout():
    """The CIP step's labels (a "(?)" on an undefined centre, never on a ring's double bonds)
    are the same whichever positions the atoms have: ring flags are set as CDK's layout sets
    them."""
    from marcus.workers import tools

    jp = tools._jvm()
    std = jp.JClass(f"{tools.CDK}.renderer.generators.standard.StandardGenerator")

    def labels(mol):
        mol = tools._cip_annotate(mol)
        atoms = [i for i, a in enumerate(mol.atoms()) if a.getProperty(std.ANNOTATION_LABEL)]
        bonds = [i for i, b in enumerate(mol.bonds()) if b.getProperty(std.ANNOTATION_LABEL)]
        return atoms, bonds

    smiles = "O=C1CC(c2ccc(O)cc2)Oc2cc(O)cc(O)c21"
    template = _ocsr_template(smiles, 150)
    oriented = tools._layout(tools._smiles_to_cdk(smiles), smiles, template)
    assert oriented.getAtom(0).getPoint2d() is not None
    assert labels(oriented) == labels(tools._sdg(tools._smiles_to_cdk(smiles))) == ([3], [])


@needs_cdk
@pytest.mark.parametrize("template", ["", "not a molfile"])
def test_depict_without_a_usable_template_lays_out_as_before(template):
    from marcus.workers import tools

    smiles = "c1ccccc1CCN"
    oriented = tools._layout(tools._smiles_to_cdk(smiles), smiles, template)
    plain = tools._sdg(tools._smiles_to_cdk(smiles))
    for i in range(plain.getAtomCount()):
        a, b = oriented.getAtom(i).getPoint2d(), plain.getAtom(i).getPoint2d()
        assert (a.x, a.y) == pytest.approx((b.x, b.y))


@needs_cdk
def test_depict_task_takes_a_template():
    from marcus.workers import tools

    out = tools.depict_task.apply(
        kwargs={"smiles": "CCO", "template": _ocsr_template("CCO", 30)}, throw=True
    ).get()
    assert out["ok"] and out["result"].lstrip().startswith("<svg")
