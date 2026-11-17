"""DECIMER OCSR engines (normal and hand-drawn) in the TF image.

Runs only in the TF image (needs TensorFlow, decimer and the baked weights), with no network:

  docker compose -p marcus-v2 run --rm worker-decimer-test
  (= pytest -m ml tests/workers/test_decimer_ocsr.py -q)

The expected SMILES were recorded once from the local v1 copy on the same three crops (v2's
segmenter output for synth_015.pdf); command and provenance in tests/fixtures/v1_decimer.json.
v1 is never called here.

The tests share one process and its loaded models, in file order: the preload test runs first
(it is what a worker pool process does at start), the hand-drawn model is asked for last.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

import pytest

from marcus.core.enums import Engine, StepKind
from marcus.core.queues import TIME_LIMITS, time_limits_for
from marcus.core.storage import image_job_path

pytestmark = pytest.mark.ml

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
V1 = json.loads((FIXTURES / "v1_decimer.json").read_text())
DECIMER_VERSION = "2.8.0"  # docker/MODEL_PINS.md


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
    from marcus.workers.ocsr import base, decimer

    return ocsr, base, decimer


def test_preload_hook_loads_only_the_normal_model(monkeypatch, ocsr_modules):
    """What a q.decimer pool process does at start: both engines registered, only the normal
    model loaded (the hand-drawn one waits for its first request)."""
    ocsr, base, decimer = ocsr_modules
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer,decimer-hand")
    ocsr.register_configured_engines()
    assert {"decimer", "decimer-hand"} <= set(base.FACTORIES)
    monkeypatch.setattr(base, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(base, "abort_worker", lambda: aborted.append(True))

    start = time.monotonic()
    base.preload_engines(sender=None)
    print(f"\npreload (normal model): {time.monotonic() - start:.1f} s")

    assert not aborted
    assert "decimer" in base._ENGINES
    assert "decimer-hand" not in base._ENGINES
    assert decimer.hand_model_loaded() is False


def test_same_smiles_as_v1_on_three_fixture_segments(ocsr_modules):
    _, base, decimer = ocsr_modules
    engine = base.get_engine(Engine.DECIMER)
    assert len(V1["crops"]) == 3
    for crop in V1["crops"]:
        start = time.monotonic()
        result = engine.predict(crop_path(crop))
        print(f"\n{crop['file']}: {time.monotonic() - start:.1f} s  {result.smiles}")
        assert result.molfile is None
        assert result.smiles == crop["v1_smiles"], crop["file"]  # same string as v1
        assert canonical(result.smiles) == canonical(crop["v1_smiles"]), crop["file"]
    assert decimer.hand_model_loaded() is False


def test_versions_are_the_installed_decimer_package(ocsr_modules):
    _, base, decimer = ocsr_modules
    assert base.get_engine(Engine.DECIMER).version == DECIMER_VERSION
    hand = decimer.DecimerEngine(hand_drawn=True)  # constructing does not load anything
    assert hand.name == Engine.DECIMER_HAND
    assert hand.version == DECIMER_VERSION + "-hand"
    assert decimer.hand_model_loaded() is False


def test_ocsr_handler_with_decimer(ocsr_modules):
    """The real handler path (image job input), normal model."""
    from marcus.workers.ocsr.handler import ocsr
    from tests.workers.helpers import view

    crop = V1["crops"][2]
    job = uuid.uuid4()
    dest = image_job_path(job)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(crop_path(crop).read_bytes())

    out = ocsr(view(image_job_id=job, engine="decimer"), None)

    assert out["valid"] is True
    assert out["molfile"] is None
    assert out["engine_version"] == DECIMER_VERSION
    assert out["smiles"] == crop["v1_smiles"]
    assert canonical(out["smiles"]) == canonical(crop["v1_smiles"])


def test_hand_model_not_loaded_until_asked(ocsr_modules):
    """The hand-drawn model loads on the first decimer-hand request. Its timing (load +
    prediction, ~80-100 s on CPU; decimer-hand's own limit is 180 s soft) is printed and
    recorded in the report, not asserted (host load makes it vary)."""
    _, base, decimer = ocsr_modules
    assert decimer.hand_model_loaded() is False
    assert "decimer-hand" not in base._ENGINES

    path = crop_path(V1["crops"][1])
    start = time.monotonic()
    engine = base.get_engine(Engine.DECIMER_HAND)
    loaded_s = time.monotonic() - start
    assert decimer.hand_model_loaded() is True
    result = engine.predict(path)
    first_s = time.monotonic() - start
    print(f"\nhand-drawn: load {loaded_s:.1f} s, first request {first_s:.1f} s  {result.smiles}")

    assert engine.version == DECIMER_VERSION + "-hand"
    assert isinstance(result.smiles, str) and result.smiles
    assert result.molfile is None
    soft, _ = time_limits_for(StepKind.OCSR, None, Engine.DECIMER_HAND)
    assert soft > TIME_LIMITS[StepKind.OCSR][0]
    print(f"decimer-hand soft limit {soft} s; first request used {first_s / soft:.0%} of it")

    # Later requests reuse the loaded model.
    assert base.get_engine(Engine.DECIMER_HAND) is engine
