"""MolNexTR and MolScribe OCSR engines in the torch image.

Runs only in the torch image (needs torch, MolNexTR, MolScribe and the baked weights), with no
network:

  docker compose -p marcus-v2 run --rm worker-torch-test
  (= pytest -m ml tests/workers/test_torch_ocsr.py -q -s)

The expected SMILES and molfiles were recorded once from the local v1 copy on the three crops
B2 stored (v2's segmenter output for synth_015.pdf); commands and provenance in
tests/fixtures/v1_molnextr.json and v1_molscribe.json. v1 is never called here.

The tests share one process and its loaded models, in file order: each engine is preloaded the
way a worker pool process does it at start, then asked for the three crops. Timings are printed
(and recorded in the task report), never asserted.
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import pytest

from marcus.core.enums import Engine
from marcus.core.storage import image_job_path
from marcus.workers import runtime

pytestmark = pytest.mark.ml

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
V1 = {
    Engine.MOLNEXTR: json.loads((FIXTURES / "v1_molnextr.json").read_text()),
    Engine.MOLSCRIBE: json.loads((FIXTURES / "v1_molscribe.json").read_text()),
}
# docker/MODEL_PINS.md: the commits v1 installed; engine version = short hash.
VERSIONS = {Engine.MOLNEXTR: "fb7505b", Engine.MOLSCRIBE: "250f683"}
WEIGHTS = {
    Engine.MOLNEXTR: (
        "/opt/pystow/molnextr/molnextr_best.pth",
        "5990bc19aaafa5cf44e9d04e06fb8e2b5aea50c66e1e925f662bdff7d2a6422c",
    ),
    Engine.MOLSCRIBE: (
        "/opt/pystow/molscribe/swin_base_char_aux_1m.pth",
        "6f0df56fa32b5ffc21f8c7f311ef333da522f590bf5622e966c6bcb1f2d9ea1d",
    ),
}


def canonical(smiles: str) -> str:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"invalid SMILES {smiles!r}"
    return Chem.MolToSmiles(mol)


def crop_path(crop: dict) -> Path:
    path = FIXTURES / crop["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == crop["sha256"]
    return path


@pytest.fixture(scope="module")
def ocsr_modules():
    from marcus.workers import ocsr
    from marcus.workers.ocsr import base

    return ocsr, base


def preload(monkeypatch, ocsr, base, engine: Engine):
    """What a q.molnextr / q.molscribe pool process does at start."""
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", engine.value)
    ocsr.register_configured_engines()
    assert engine.value in base.PRELOAD
    monkeypatch.setattr(runtime, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(runtime, "abort_worker", lambda: aborted.append(True))
    start = time.monotonic()
    base.preload_engines(sender=None)
    print(f"\npreload {engine.value} (load + warm-up): {time.monotonic() - start:.1f} s")
    assert not aborted
    assert engine.value in base._ENGINES


def same_as_v1(base, engine: Engine):
    model = base.get_engine(engine)
    crops = V1[engine]["crops"]
    assert len(crops) == 3
    for crop in crops:
        start = time.monotonic()
        result = model.predict(crop_path(crop))
        print(f"\n{engine.value} {crop['file']}: {time.monotonic() - start:.1f} s  {result.smiles}")
        assert result.smiles == crop["v1_smiles"], crop["file"]  # same string as v1
        assert canonical(result.smiles) == canonical(crop["v1_smiles"]), crop["file"]
        assert result.molfile == crop["v1_molfile"], crop["file"]


def test_torch_threads_are_capped_before_any_model_loads():
    from marcus.core.settings import get_settings
    from marcus.workers import gpu

    threads = get_settings().torch_threads
    assert threads is not None, "the test service sets MARCUS_TORCH_THREADS"
    gpu.limit_torch_threads(threads)
    import torch

    assert torch.get_num_threads() == threads
    assert torch.get_num_interop_threads() == 1
    assert os.environ["OMP_NUM_THREADS"] == str(threads)
    # No GPU here: the memory budget is a no-op.
    assert gpu.limit_torch_memory(0.5) is False


@pytest.mark.parametrize("engine", [Engine.MOLNEXTR, Engine.MOLSCRIBE])
def test_weights_are_baked_with_the_pinned_checksum(engine):
    path, sha256 = WEIGHTS[engine]
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            digest.update(block)
    assert digest.hexdigest() == sha256


def test_molnextr_preload(monkeypatch, ocsr_modules):
    ocsr, base = ocsr_modules
    preload(monkeypatch, ocsr, base, Engine.MOLNEXTR)


def test_molnextr_same_smiles_as_v1_on_three_segments(ocsr_modules):
    _, base = ocsr_modules
    same_as_v1(base, Engine.MOLNEXTR)


def test_molscribe_preload(monkeypatch, ocsr_modules):
    ocsr, base = ocsr_modules
    preload(monkeypatch, ocsr, base, Engine.MOLSCRIBE)


def test_molscribe_same_smiles_as_v1_on_three_segments(ocsr_modules):
    _, base = ocsr_modules
    same_as_v1(base, Engine.MOLSCRIBE)


def test_molscribe_runs_on_the_configured_device(ocsr_modules):
    _, base = ocsr_modules
    model = base.get_engine(Engine.MOLSCRIBE)
    assert str(model.device) == "cpu"  # MARCUS_MOLSCRIBE_DEVICE default, as v1


@pytest.mark.parametrize("engine", [Engine.MOLNEXTR, Engine.MOLSCRIBE])
def test_version_is_the_pinned_commit(ocsr_modules, engine):
    _, base = ocsr_modules
    model = base.get_engine(engine)
    assert model.name == engine
    assert model.version == VERSIONS[engine]


@pytest.mark.parametrize("engine", [Engine.MOLNEXTR, Engine.MOLSCRIBE])
def test_ocsr_handler(ocsr_modules, engine):
    """The real handler path (image job input)."""
    from marcus.workers.ocsr.handler import ocsr
    from tests.workers.helpers import view

    crop = V1[engine]["crops"][2]
    job = uuid.uuid4()
    dest = image_job_path(job)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(crop_path(crop).read_bytes())

    out = ocsr(view(image_job_id=job, engine=engine.value), None)

    assert out["valid"] is True
    assert out["engine_version"] == VERSIONS[engine]
    assert out["smiles"] == crop["v1_smiles"]
    assert canonical(out["smiles"]) == canonical(crop["v1_smiles"])
    assert out["molfile"] == crop["v1_molfile"]
    print(f"\nhandler {engine.value}: {out['ms']} ms")
