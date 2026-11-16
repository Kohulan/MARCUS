"""Tool task pure functions against a real JVM (CDK) and RDKit. v1 values: fixtures/v1_tools.json."""

import base64
import json
import os
from pathlib import Path

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
