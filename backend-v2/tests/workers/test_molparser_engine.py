"""The MolParser engine wrapper (marcus.workers.ocsr.molparser) without torch or the model: the
library's recognizer and post-processing are stubs; RDKit is real (labelled molfiles). The
real-model check is the ml test in test_molparser_ocsr.py (MolParser image)."""

import sys
import types

import pytest
from PIL import Image

from marcus.core.enums import Engine
from marcus.core.rgroups import rgroup_labels
from marcus.workers import gpu
from marcus.workers.ocsr import base, molparser
from marcus.workers.orient import image_layout

LABELLED = "*CC1=C[C@@H](C)C(*)C1 |$R[5];;;;;;;R[2];;$|"


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    monkeypatch.setattr(base, "FACTORIES", dict(base.FACTORIES))
    monkeypatch.setattr(base, "PRELOAD", set(base.PRELOAD))
    monkeypatch.setattr(base, "_ENGINES", {})


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    """Stub torch and the molparser library in sys.modules; the model folder under tmp_path."""
    calls = []
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)

    class Recognizer:
        device_type = None  # None: the device asked for

        def __init__(self, path, device="auto", max_length=256):
            calls.append(("init", path, device, max_length))
            self.device = types.SimpleNamespace(type=Recognizer.device_type or device)

        def recognize(self, images):
            calls.append(("recognize", [img.mode for img in images]))
            return ["*C(C)=O<sep><a>0:R[1]</a>"]

    def postprocess_caption(caption):
        calls.append(("post", caption))
        return {"smi": "*C(C)=O", "cxsmiles": "*C(C)=O |$R[1];;;$|", "markush": True}

    runtime = types.ModuleType("molparser.models.runtime")
    runtime.MolParserRecognizer = Recognizer
    models = types.ModuleType("molparser.models")
    models.runtime = runtime
    utils = types.ModuleType("molparser.utils")
    utils.postprocess_caption = postprocess_caption
    pkg = types.ModuleType("molparser")
    pkg.models, pkg.utils = models, utils
    for name, module in {
        "torch": torch,
        "molparser": pkg,
        "molparser.models": models,
        "molparser.models.runtime": runtime,
        "molparser.utils": utils,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(gpu, "prepare_torch", lambda: calls.append("prepare_torch"))
    monkeypatch.setattr(molparser, "warm_up", lambda name, fn: calls.append(("warm", name)))
    monkeypatch.setattr(molparser, "package_commit", lambda dist: "f8f1e21")
    folder = tmp_path / "model"
    monkeypatch.setenv(molparser.MODEL_DIR_ENV, str(folder))
    # load() sets these with setdefault: set here so the test process gets them back
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    def bake():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.safetensors").write_bytes(b"weights")

    return types.SimpleNamespace(calls=calls, bake=bake, torch=torch, recognizer=Recognizer)


# --- E-SMILES labels ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, alias", [("R[1]", "R1"), ("R[12]", "R12"), ("R[1']", "R1'"), ("OAc", "OAc")]
)
def test_alias_of_an_esmiles_label(label, alias):
    assert molparser.alias_of(label) == alias


def test_labelled_molfile_keeps_the_r_group_labels():
    molfile = molparser.labelled_molfile(LABELLED)
    assert molfile is not None
    assert rgroup_labels("*CC1=C[C@@H](C)C(*)C1", molfile) == ["R2", "R5"]


def test_without_labels_the_r_groups_stay_unlabelled():
    assert rgroup_labels("*CC1=C[C@@H](C)C(*)C1", None) == ["*"]


def test_labelled_molfile_has_a_computed_layout_never_a_template():
    assert not image_layout(molparser.labelled_molfile(LABELLED))


@pytest.mark.parametrize(
    "cxsmiles",
    ["", "CCO", "*CCO", "*CC |$;;$|", "C1CC |$R[1];;$|"],  # none, no labels, empty, unreadable
)
def test_no_labelled_molfile(cxsmiles):
    assert molparser.labelled_molfile(cxsmiles) is None


def test_result_of_a_caption(stubs):
    result = molparser.result_of("raw")
    assert result.smiles == "*C(C)=O"
    assert "R1" in result.molfile
    assert ("post", "raw") in stubs.calls


# --- engine --------------------------------------------------------------------------------


def test_load_and_predict(stubs, tmp_path):
    stubs.bake()
    engine = molparser.MolparserEngine()
    assert engine.name == Engine.MOLPARSER
    assert engine.version == "f8f1e21+6ee7c0f"
    engine.load()
    path = tmp_path / "crop.png"
    Image.new("L", (20, 10), 255).save(path)
    result = engine.predict(path)
    assert result.smiles == "*C(C)=O" and "R1" in result.molfile
    assert stubs.calls[:3] == [
        "prepare_torch",
        ("init", str(tmp_path / "model"), "cpu", molparser.MAX_LENGTH),
        ("warm", "MolParser"),
    ]
    assert ("recognize", ["RGB"]) in stubs.calls  # a grey crop goes in as RGB, as the library's


def test_load_once(stubs):
    stubs.bake()
    engine = molparser.MolparserEngine()
    engine.load()
    engine.load()
    assert len([c for c in stubs.calls if c[0] == "init"]) == 1


def test_missing_model_fails_before_the_library_loads(stubs):
    with pytest.raises(RuntimeError, match="missing"):
        molparser.MolparserEngine().load()
    assert not [c for c in stubs.calls if c[0] == "init"]


def test_cuda_when_torch_sees_it(stubs):
    stubs.bake()
    stubs.torch.cuda.is_available = lambda: True
    engine = molparser.MolparserEngine()
    engine.load()
    assert engine.device.type == "cuda"


def test_cpu_with_cuda_visible_is_refused(stubs):
    stubs.bake()
    stubs.torch.cuda.is_available = lambda: True
    stubs.recognizer.device_type = "cpu"
    with pytest.raises(RuntimeError, match="GPU"):
        molparser.MolparserEngine().load()


def test_predict_before_load_fails(stubs):
    with pytest.raises(RuntimeError, match="load"):
        molparser.MolparserEngine().predict("/x.png")


def test_register_rejects_other_engines():
    with pytest.raises(ValueError):
        molparser.register(Engine.MOLSCRIBE)
    molparser.register(Engine.MOLPARSER)
    assert "molparser" in base.FACTORIES and "molparser" in base.PRELOAD
