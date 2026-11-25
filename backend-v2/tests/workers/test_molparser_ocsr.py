"""The MolParser OCSR engine in its image (docker/Dockerfile.molparser).

Runs only in that image (needs torch, transformers, the MolParser library and the baked model),
with no network:

  docker compose -p marcus-v2 run --rm worker-molparser-test
  (= pytest -m ml tests/workers/test_molparser_ocsr.py -q -s)

The expected SMILES were recorded on CPU with the same pinned stack on the three synth_015 crops
the other engines' tests use (tests/fixtures/molparser_f8f1e21.json; the same molecules as
MolScribe's v1 results there). The tests share one process and its loaded model, in file order.
Timings are printed, never asserted.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

import pytest

from marcus.core.enums import Engine
from marcus.core.storage import image_job_path
from marcus.workers import runtime

pytestmark = pytest.mark.ml

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "molparser_f8f1e21.json").read_text())
MODEL = Path("/opt/models/molparser-mobile-v2")
MODEL_SHA256 = "2204a871f7975780ead6eee8ac354de11f859c4eccc8863c3462e6f9eb110f02"


def crop_path(crop: dict) -> Path:
    path = FIXTURES / crop["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == crop["sha256"]
    return path


@pytest.fixture(scope="module")
def ocsr_modules():
    from marcus.workers import ocsr
    from marcus.workers.ocsr import base

    return ocsr, base


def test_the_model_is_baked_with_the_pinned_checksum():
    digest = hashlib.sha256((MODEL / "model.safetensors").read_bytes()).hexdigest()
    assert digest == MODEL_SHA256


def test_preload(monkeypatch, ocsr_modules):
    """What a q.molparser pool process does at start (offline, read-only root)."""
    ocsr, base = ocsr_modules
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", Engine.MOLPARSER.value)
    ocsr.register_configured_engines()
    assert Engine.MOLPARSER.value in base.PRELOAD
    monkeypatch.setattr(runtime, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(runtime, "abort_worker", lambda: aborted.append(True))
    start = time.monotonic()
    base.preload_engines(sender=None)
    print(f"\npreload molparser (load + warm-up): {time.monotonic() - start:.1f} s")
    assert not aborted
    assert Engine.MOLPARSER.value in base._ENGINES


def test_same_smiles_as_recorded_on_three_segments(ocsr_modules):
    _, base = ocsr_modules
    model = base.get_engine(Engine.MOLPARSER)
    assert model.version == EXPECTED["version"]
    assert str(model.device) == "cpu"
    for crop in EXPECTED["crops"]:
        start = time.monotonic()
        result = model.predict(crop_path(crop))
        print(f"\nmolparser {crop['file']}: {time.monotonic() - start:.2f} s  {result.smiles}")
        assert result.smiles == crop["smiles"], crop["file"]
        assert result.molfile == crop["molfile"], crop["file"]


def test_ocsr_handler(ocsr_modules):
    """The real handler path (image job input)."""
    from marcus.workers.ocsr.handler import ocsr
    from tests.workers.helpers import view

    crop = EXPECTED["crops"][2]
    job = uuid.uuid4()
    dest = image_job_path(job)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(crop_path(crop).read_bytes())

    out = ocsr(view(image_job_id=job, engine=Engine.MOLPARSER.value), None)

    assert out["valid"] is True
    assert out["engine_version"] == EXPECTED["version"]
    assert out["smiles"] == crop["smiles"]
    print(f"\nhandler molparser: {out['ms']} ms")
