"""The MolScribe engine wrapper against stub packages (no torch, no weights).

The stubs mimic what the wrapper relies on in the pinned commit: molscribe's `interface`
(MolScribe, binds convert_graph_to_smiles) and `chemistry`. (MolNexTR's wrapper went with the
engine, 2026-11-25; MolParser's is tested in test_molparser_engine.py.)
The real-model checks are the ml tests in test_torch_ocsr.py.
"""

import subprocess
import sys
import types

import pytest

from marcus.core.enums import Engine
from marcus.workers import gpu, ocsr
from marcus.workers.ocsr import base, molscribe, torch_common
from marcus.workers.ocsr.base import OcsrResult

ATOMS = [{"atom_symbol": "C", "x": 0.0, "y": 0.0}, {"atom_symbol": "O", "x": 1.0, "y": 1.0}]
BONDS = [{"bond_type": "single", "endpoint_atoms": [0, 1]}]


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    monkeypatch.setattr(base, "FACTORIES", dict(base.FACTORIES))
    monkeypatch.setattr(base, "PRELOAD", set(base.PRELOAD))
    monkeypatch.setattr(base, "_ENGINES", {})
    monkeypatch.delenv("MARCUS_OCSR_ENGINES", raising=False)


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    """Stub pystow / torch / molscribe in sys.modules; weights under tmp_path."""
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

        def predict_image_file(self, path, return_atoms_bonds=False):
            calls.append(("ms_predict", path))
            smi, mol, _ = interface.convert_graph_to_smiles(["g"], ["s"], ["e"], images=["i"])
            out = {"smiles": smi[0], "molfile": "" if "empty" in path else mol[0]}
            if return_atoms_bonds:
                out["atoms"] = [] if "empty" in path else ATOMS
                out["bonds"] = [] if "empty" in path else BONDS
            return out

    interface.MolScribe = MolScribe
    pkg_ms = types.ModuleType("molscribe")
    pkg_ms.chemistry, pkg_ms.interface = chemistry, interface
    modules.update(
        {"molscribe": pkg_ms, "molscribe.chemistry": chemistry, "molscribe.interface": interface}
    )

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(gpu, "prepare_torch", lambda: calls.append("prepare_torch"))
    monkeypatch.setattr(torch_common, "warm_up", lambda name, fn: calls.append(("warm", fn("w"))))
    monkeypatch.setattr(molscribe, "warm_up", torch_common.warm_up)
    commits = {"MolScribe": "250f683"}
    monkeypatch.setattr(molscribe, "package_commit", lambda dist: commits[dist])

    def bake(key, name):
        path = home / key / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"weights")
        return path

    return types.SimpleNamespace(
        calls=calls,
        bake=bake,
        interface=interface,
        torch=torch,
    )


# --- configuration -----------------------------------------------------------------------


@pytest.mark.parametrize("engine", [Engine.MOLPARSER, Engine.MOLSCRIBE])
def test_torch_worker_registers_and_preloads_its_engine(monkeypatch, engine):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", engine.value)
    assert ocsr.register_configured_engines() == [engine]
    assert engine.value in base.FACTORIES
    assert engine.value in base.PRELOAD
    assert not {"decimer", "decimer-hand"} & set(base.FACTORIES)


def test_register_rejects_other_engines():
    with pytest.raises(ValueError):
        molscribe.register(Engine.DECIMER)


def test_torch_engine_modules_do_not_import_torch():
    code = (
        "import sys, marcus.workers.ocsr.molparser, marcus.workers.ocsr.molscribe; "
        "bad = {'torch', 'molparser', 'molscribe', 'pystow', 'transformers'} & set(sys.modules); "
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
    # with the raw atoms and bonds (return_atoms_bonds=True), for the paper layout
    assert result == OcsrResult("smiles-g", "molblock-g", {"atoms": ATOMS, "bonds": BONDS})
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
    assert engine.predict("/data/empty.png") == OcsrResult("smiles-g", None, None)


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
        lambda name: Dist(url % "7a4e03f22c13f4c1c236effa9dab4a365a8e08d5"),
    )
    assert torch_common.package_commit("MolScribe") == "7a4e03f"
    monkeypatch.setattr(torch_common, "distribution", lambda name: Dist(None))
    with pytest.raises(RuntimeError, match="pinned git commit"):
        torch_common.package_commit("MolScribe")
