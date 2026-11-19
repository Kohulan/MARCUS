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
