"""MolNexTR and MolScribe engine wrappers against stub packages (no torch, no weights).

The stubs mimic what the wrappers rely on in the pinned commits: MolNexTR's `molnextr` module
(MolNexTRSingleton, get_predictions), `model` (binds convert_graph_to_smiles) and `chemical`;
molscribe's `interface` (MolScribe, binds convert_graph_to_smiles) and `chemistry`.
The real-model checks are the ml tests in test_torch_ocsr.py.
"""

import subprocess
import sys
import types

import pytest

from marcus.core.enums import Engine
from marcus.workers import gpu, ocsr, runtime
from marcus.workers.ocsr import base, molnextr, molscribe, torch_common
from marcus.workers.ocsr.base import OcsrResult


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    monkeypatch.setattr(base, "FACTORIES", dict(base.FACTORIES))
    monkeypatch.setattr(base, "PRELOAD", set(base.PRELOAD))
    monkeypatch.setattr(base, "_ENGINES", {})
    monkeypatch.delenv("MARCUS_OCSR_ENGINES", raising=False)


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    """Stub pystow / torch / MolNexTR / molscribe in sys.modules; weights under tmp_path."""
    calls = []
    home = tmp_path / "pystow"

    pystow = types.ModuleType("pystow")
    pystow.join = lambda key, name=None, ensure_exists=True: home / key / name
    torch = types.ModuleType("torch")
    torch.device = lambda name: f"device:{name}"
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    modules = {"pystow": pystow, "torch": torch}

    def convert_one(coords, symbols, edges, image=None):
        calls.append(("convert", coords, image is not None))
        return f"smiles-{coords}", f"molblock-{coords}", coords != "bad"

    # --- MolNexTR
    chemical = types.ModuleType("MolNexTR.chemical")

    def mn_convert(coords, symbols, edges, images=None, num_workers=16):
        raise AssertionError("the multiprocessing.Pool version must not run")

    chemical.convert_graph_to_smiles = mn_convert
    chemical._convert_graph_to_smiles = convert_one
    model = types.ModuleType("MolNexTR.model")
    model.convert_graph_to_smiles = mn_convert

    class MnModel:
        """MolNexTR.model.molnextr: what the singleton holds."""

        error = None

        def predict_final_results(self, path, return_atoms_bonds=False, return_confidence=False):
            calls.append(("mn_predict", path, return_atoms_bonds))
            if MnModel.error is not None:
                raise MnModel.error
            # the library calls model.convert_graph_to_smiles (bound in MolNexTR.model)
            smi, mol, _ = model.convert_graph_to_smiles(["g"], ["s"], ["e"], images=["img"])
            return {
                "predicted_smiles": smi[0],
                "predicted_molfile": mol[0] if "empty" not in path else "",
            }

    class Singleton:
        instance = None
        device_type = "cpu"  # torch.device(...).type of the model's device
        device_name = "CPU"

        @classmethod
        def get_instance(cls):
            calls.append("mn_init")
            cls.instance = MnModel()
            return cls.instance

        @classmethod
        def get_device(cls):
            return types.SimpleNamespace(type=cls.device_type), cls.device_name

    def get_predictions(*args, **kwargs):
        raise AssertionError("get_predictions (reload on error) must not be used")

    mn = types.ModuleType("MolNexTR.molnextr")
    mn.MolNexTRSingleton = Singleton
    mn.get_predictions = get_predictions
    pkg_mn = types.ModuleType("MolNexTR")
    pkg_mn.chemical, pkg_mn.model, pkg_mn.molnextr = chemical, model, mn
    modules.update(
        {
            "MolNexTR": pkg_mn,
            "MolNexTR.chemical": chemical,
            "MolNexTR.model": model,
            "MolNexTR.molnextr": mn,
        }
    )

    # --- molscribe
    chemistry = types.ModuleType("molscribe.chemistry")
    chemistry._convert_graph_to_smiles = convert_one
    interface = types.ModuleType("molscribe.interface")

    def pooled(*args, **kwargs):
        raise AssertionError("the multiprocessing.Pool version must not run")

    interface.convert_graph_to_smiles = pooled

    class MolScribe:
        def __init__(self, path, device=None):
            calls.append(("ms_init", path, device))
            self.device = device

        def predict_image_file(self, path):
            calls.append(("ms_predict", path))
            smi, mol, _ = interface.convert_graph_to_smiles(["g"], ["s"], ["e"], images=["i"])
            return {"smiles": smi[0], "molfile": "" if "empty" in path else mol[0]}

    interface.MolScribe = MolScribe
    pkg_ms = types.ModuleType("molscribe")
    pkg_ms.chemistry, pkg_ms.interface = chemistry, interface
    modules.update(
        {"molscribe": pkg_ms, "molscribe.chemistry": chemistry, "molscribe.interface": interface}
    )

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(molnextr, "_model", None)
    monkeypatch.setattr(gpu, "prepare_torch", lambda: calls.append("prepare_torch"))
    monkeypatch.setattr(torch_common, "warm_up", lambda name, fn: calls.append(("warm", fn("w"))))
    monkeypatch.setattr(molnextr, "warm_up", torch_common.warm_up)
    monkeypatch.setattr(molscribe, "warm_up", torch_common.warm_up)
    commits = {"MolNexTR": "fb7505b", "MolScribe": "250f683"}
    monkeypatch.setattr(molnextr, "package_commit", lambda dist: commits[dist])
    monkeypatch.setattr(molscribe, "package_commit", lambda dist: commits[dist])

    def bake(key, name):
        path = home / key / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"weights")
        return path

    return types.SimpleNamespace(
        calls=calls,
        bake=bake,
        model=model,
        interface=interface,
        chemical=chemical,
        torch=torch,
        singleton=Singleton,
        mn_model=MnModel,
    )


# --- configuration -----------------------------------------------------------------------


@pytest.mark.parametrize("engine", [Engine.MOLNEXTR, Engine.MOLSCRIBE])
def test_torch_worker_registers_and_preloads_its_engine(monkeypatch, engine):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", engine.value)
    assert ocsr.register_configured_engines() == [engine]
    assert engine.value in base.FACTORIES
    assert engine.value in base.PRELOAD
    assert not {"decimer", "decimer-hand"} & set(base.FACTORIES)


def test_register_rejects_other_engines():
    with pytest.raises(ValueError):
        molnextr.register(Engine.MOLSCRIBE)
    with pytest.raises(ValueError):
        molscribe.register(Engine.DECIMER)


def test_torch_engine_modules_do_not_import_torch():
    code = (
        "import sys, marcus.workers.ocsr.molnextr, marcus.workers.ocsr.molscribe; "
        "bad = {'torch', 'MolNexTR', 'molscribe', 'pystow'} & set(sys.modules); "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_thread_settings_default_to_the_compose_caps(monkeypatch):
    """An image run outside compose is capped too (torch 4; TF intra 4 / inter 2)."""
    from marcus.core.settings import Settings

    for var in ("MARCUS_TORCH_THREADS", "MARCUS_TF_INTRA_THREADS", "MARCUS_TF_INTER_THREADS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert (s.torch_threads, s.tf_intra_threads, s.tf_inter_threads) == (4, 4, 2)


def test_molscribe_device_setting(monkeypatch):
    from pydantic import ValidationError

    from marcus.core.settings import Settings

    monkeypatch.delenv("MARCUS_MOLSCRIBE_DEVICE", raising=False)
    assert Settings().molscribe_device == "cpu"  # v1 forces CPU
    monkeypatch.setenv("MARCUS_MOLSCRIBE_DEVICE", "cuda")
    assert Settings().molscribe_device == "cuda"
    monkeypatch.setenv("MARCUS_MOLSCRIBE_DEVICE", "tpu")
    with pytest.raises(ValidationError):
        Settings()


# --- MolNexTR ------------------------------------------------------------------------------


def test_molnextr_load_and_predict_like_v1(stubs):
    stubs.bake("molnextr", "molnextr_best.pth")
    engine = molnextr.MolnextrEngine()
    assert engine.name == Engine.MOLNEXTR and engine.version == "fb7505b"
    engine.load()

    assert stubs.calls[0] == "prepare_torch"  # thread caps and GPU share before the model
    assert "mn_init" in stubs.calls
    # graph conversion runs in-process with MolNexTR's per-structure function, not a pool
    assert stubs.model.convert_graph_to_smiles is not stubs.chemical.convert_graph_to_smiles
    assert stubs.calls[-1] == ("warm", "smiles-g")  # warm-up prediction at load

    stubs.calls.clear()
    result = engine.predict("/data/crop.png")
    assert result == OcsrResult("smiles-g", "molblock-g")
    # the call inside v1's get_predictions, without its reload-on-error wrapper
    assert stubs.calls == [("mn_predict", "/data/crop.png", False), ("convert", "g", True)]
    engine.load()  # once per process
    assert stubs.calls.count("mn_init") == 0


def test_molnextr_empty_molfile_is_none(stubs):
    stubs.bake("molnextr", "molnextr_best.pth")
    engine = molnextr.MolnextrEngine()
    engine.load()
    assert engine.predict("/data/empty.png").molfile is None


def test_molnextr_missing_checkpoint_fails_before_the_library_loads(stubs):
    engine = molnextr.MolnextrEngine()
    with pytest.raises(RuntimeError, match="checkpoint missing"):
        engine.load()
    assert "mn_init" not in stubs.calls
    assert molnextr._model is None


@pytest.mark.parametrize("error", [ValueError("bad graph"), "soft"])
def test_molnextr_prediction_errors_reach_the_step_without_a_reload(stubs, error):
    from celery.exceptions import SoftTimeLimitExceeded

    stubs.bake("molnextr", "molnextr_best.pth")
    engine = molnextr.MolnextrEngine()
    engine.load()
    exc = SoftTimeLimitExceeded() if error == "soft" else error
    stubs.mn_model.error = exc
    stubs.calls.clear()
    with pytest.raises(type(exc)):
        engine.predict("/data/crop.png")
    assert stubs.calls == [("mn_predict", "/data/crop.png", False)]  # no reload, no second try
    assert "mn_init" not in stubs.calls


def test_molnextr_cpu_fallback_with_cuda_visible_is_refused(stubs, monkeypatch):
    stubs.bake("molnextr", "molnextr_best.pth")
    monkeypatch.setattr(stubs.singleton, "device_name", "CPU (fallback)")
    stubs.torch.cuda.is_available = lambda: True
    with pytest.raises(RuntimeError, match="not on the GPU although CUDA is visible"):
        molnextr.MolnextrEngine().load()
    assert molnextr._model is None


def test_molnextr_cpu_fallback_aborts_the_worker_at_preload(stubs, monkeypatch):
    stubs.bake("molnextr", "molnextr_best.pth")
    monkeypatch.setattr(stubs.singleton, "device_name", "CPU (fallback)")
    stubs.torch.cuda.is_available = lambda: True
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "molnextr")
    ocsr.register_configured_engines()
    monkeypatch.setattr(runtime, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(runtime, "abort_worker", lambda: aborted.append(True))
    base.preload_engines(sender=None)
    assert aborted == [True]


def test_molnextr_cpu_after_a_failed_cuda_smoke_test_is_refused(stubs, monkeypatch):
    """After a failed CUDA smoke test MolNexTR's device name is plain "CPU", not "CPU
    (fallback)": the guard reads the device type, not the name."""
    stubs.bake("molnextr", "molnextr_best.pth")
    monkeypatch.setattr(stubs.singleton, "device_type", "cpu")
    monkeypatch.setattr(stubs.singleton, "device_name", "CPU")
    stubs.torch.cuda.is_available = lambda: True
    with pytest.raises(RuntimeError, match="not on the GPU although CUDA is visible"):
        molnextr.MolnextrEngine().load()
    assert molnextr._model is None


def test_molnextr_on_cuda_with_cuda_visible_is_fine(stubs, monkeypatch):
    stubs.bake("molnextr", "molnextr_best.pth")
    monkeypatch.setattr(stubs.singleton, "device_type", "cuda")
    monkeypatch.setattr(stubs.singleton, "device_name", "NVIDIA GPU (Tesla V100)")
    stubs.torch.cuda.is_available = lambda: True
    molnextr.MolnextrEngine().load()
    assert molnextr._model is not None


def test_molnextr_cpu_without_cuda_is_fine(stubs):
    stubs.bake("molnextr", "molnextr_best.pth")
    engine = molnextr.MolnextrEngine()
    engine.load()  # device "CPU", no CUDA: v1's normal CPU case
    assert molnextr._model is not None


def test_molnextr_predict_before_load_fails(stubs):
    with pytest.raises(RuntimeError, match="load"):
        molnextr.MolnextrEngine().predict("/x.png")


# --- MolScribe -----------------------------------------------------------------------------


def test_molscribe_load_and_predict_like_v1(stubs, monkeypatch):
    path = stubs.bake("molscribe", "swin_base_char_aux_1m.pth")
    monkeypatch.delenv("MARCUS_MOLSCRIBE_DEVICE", raising=False)
    engine = molscribe.MolscribeEngine()
    assert engine.name == Engine.MOLSCRIBE and engine.version == "250f683"
    engine.load()

    assert stubs.calls[0] == "prepare_torch"
    assert stubs.calls[1] == ("ms_init", str(path), "device:cpu")  # v1: CPU
    assert engine.device == "device:cpu"
    assert stubs.calls[-1] == ("warm", "smiles-g")

    stubs.calls.clear()
    result = engine.predict("/data/crop.png")
    assert result == OcsrResult("smiles-g", "molblock-g")
    # in-process conversion with the library's per-structure function, image passed through
    assert stubs.calls == [("ms_predict", "/data/crop.png"), ("convert", "g", True)]


def test_molscribe_device_from_settings(stubs, monkeypatch):
    stubs.bake("molscribe", "swin_base_char_aux_1m.pth")
    monkeypatch.setenv("MARCUS_MOLSCRIBE_DEVICE", "cuda")
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    engine = molscribe.MolscribeEngine()
    engine.load()
    assert engine.device == "device:cuda"


def test_molscribe_empty_molfile_is_none(stubs):
    stubs.bake("molscribe", "swin_base_char_aux_1m.pth")
    engine = molscribe.MolscribeEngine()
    engine.load()
    assert engine.predict("/data/empty.png") == OcsrResult("smiles-g", None)


def test_molscribe_missing_checkpoint_fails_before_the_library_loads(stubs):
    engine = molscribe.MolscribeEngine()
    with pytest.raises(RuntimeError, match="checkpoint missing"):
        engine.load()
    assert not [c for c in stubs.calls if c[0] == "ms_init"]


def test_molscribe_predict_before_load_fails(stubs):
    with pytest.raises(RuntimeError, match="load"):
        molscribe.MolscribeEngine().predict("/x.png")


# --- shared helpers --------------------------------------------------------------------------


def test_serial_conversion_matches_the_pool_version_contract():
    seen = []

    def convert_one(coords, symbols, edges, image=None):
        seen.append((coords, symbols, edges, image))
        return f"S{coords}", f"M{coords}", coords != 2

    convert = torch_common.serial_graph_conversion(convert_one)
    smiles, molblocks, rate = convert([1, 2], ["a", "b"], ["x", "y"], images=["i1", "i2"])
    assert smiles == ("S1", "S2") and molblocks == ("M1", "M2") and rate == 0.5
    assert seen == [(1, "a", "x", "i1"), (2, "b", "y", "i2")]  # input order kept

    seen.clear()
    convert([3], ["c"], ["z"])
    assert seen == [(3, "c", "z", None)]


def test_package_commit_reads_direct_url(monkeypatch):
    class Dist:
        def __init__(self, text):
            self.text = text

        def read_text(self, name):
            assert name == "direct_url.json"
            return self.text

    url = '{"url": "https://github.com/x/y.git", "vcs_info": {"commit_id": "%s", "vcs": "git"}}'
    monkeypatch.setattr(
        torch_common,
        "distribution",
        lambda name: Dist(url % "fb7505bed4774d13e8feae2aafbb57da22114512"),
    )
    assert torch_common.package_commit("MolNexTR") == "fb7505b"
    monkeypatch.setattr(torch_common, "distribution", lambda name: Dist(None))
    with pytest.raises(RuntimeError, match="pinned git commit"):
        torch_common.package_commit("MolNexTR")
