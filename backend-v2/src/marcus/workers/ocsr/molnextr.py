"""MolNexTR OCSR engine `molnextr` (torch, q.molnextr worker).

Same model call and output as v1 (`backend/app/modules/ocsr_wrapper.py` get_molnextr_prediction
with data_type "both", which v1's generate_both route uses). v1 calls the library's
`get_predictions(path, atoms_bonds=False, smiles=True, predicted_molfile=True)`, which is
`MolNexTRSingleton.get_instance().predict_final_results(path, return_atoms_bonds=False)` with the
result filtered to `predicted_smiles` / `predicted_molfile`. v2 makes that inner call directly and
reads the same two keys, so the output is byte-identical. It does not go through
`get_predictions` because that wraps the prediction in `except Exception`, which resets the
singleton and loads the model again (`_detect_hardware` again, so CUDA again when visible), then
predicts again. That swallows Celery's SoftTimeLimitExceeded (an Exception): a step at its soft
limit would reload (~16 s on CPU) and predict into the hard kill; on a GPU the reload holds two
models (OOM under MARCUS_TORCH_MEM_FRACTION) or meets a sticky CUDA error, after which
`_initialize_model` silently falls back to CPU for good. Here an error reaches the step, whose
retry-once handles it.

Device as in v1: the singleton picks CUDA when torch sees a GPU, else CPU. If its model setup
fails on the GPU, the library falls back to CPU ("CPU (fallback)"); with CUDA visible that load
is refused (the worker stops; compose restarts it) instead of serving silently from the CPU.

The checkpoint is baked into the image where the singleton looks first
(`pystow.join("molnextr")/molnextr_best.pth`, PYSTOW_HOME=/opt/pystow); a missing file stops the
load before the library could try to download it. Graph-to-SMILES conversion runs in-process
(torch_common.serial_graph_conversion). MolNexTR's own `num_workers <= 1` branch cannot be used:
it calls `itertools`, which MolNexTR.chemical never imports (NameError at the pinned commit).

Before the import: torch thread caps and the GPU memory share (marcus.workers.gpu.prepare_torch).
The model loads and warms up when the pool process starts (base.preload_engines). This module
does not import torch or MolNexTR at import time.
"""

import logging
import threading
import time
from pathlib import Path

from marcus.core.enums import Engine
from marcus.workers.ocsr.base import OcsrResult, register_engine
from marcus.workers.ocsr.torch_common import package_commit, serial_graph_conversion, warm_up

log = logging.getLogger(__name__)

DIST_NAME = "MolNexTR"
CHECKPOINT = "molnextr_best.pth"  # MolNexTRSingleton._initialize_model

_lock = threading.Lock()
_model = None  # MolNexTR.model.molnextr instance held by MolNexTRSingleton

FALLBACK_DEVICE = "CPU (fallback)"  # MolNexTRSingleton's name after a failed GPU setup


def checkpoint_path() -> Path:
    """Where MolNexTRSingleton looks for the checkpoint before it would download it."""
    import pystow

    return Path(pystow.join("molnextr", name=CHECKPOINT, ensure_exists=False))


def _predict(path: str) -> dict:
    return _model.predict_final_results(path, return_atoms_bonds=False)


def _load() -> None:
    global _model
    with _lock:
        if _model is not None:
            return
        from marcus.workers import gpu

        gpu.prepare_torch()
        weights = checkpoint_path()
        if not weights.is_file():
            raise RuntimeError(f"MolNexTR checkpoint missing at {weights} (baked into the image)")

        start = time.monotonic()
        import MolNexTR.chemical as chemical
        import MolNexTR.model as model_module
        import MolNexTR.molnextr as module
        import torch

        model_module.convert_graph_to_smiles = serial_graph_conversion(
            chemical._convert_graph_to_smiles
        )
        instance = module.MolNexTRSingleton.get_instance()
        device, device_name = module.MolNexTRSingleton.get_device()
        if device_name.startswith(FALLBACK_DEVICE) and torch.cuda.is_available():
            raise RuntimeError(
                "MolNexTR fell back to CPU although CUDA is visible (GPU model setup failed)"
            )
        _model = instance
        log.info(
            "MolNexTR loaded on %s (%s) in %.1f s", device_name, device, time.monotonic() - start
        )
        warm_up("MolNexTR", lambda p: _predict(p).get("predicted_smiles", ""))


class MolnextrEngine:
    name = Engine.MOLNEXTR

    def __init__(self) -> None:
        self.version = package_commit(DIST_NAME)

    def load(self) -> None:
        _load()

    def predict(self, image: Path) -> OcsrResult:
        if _model is None:
            raise RuntimeError("MolnextrEngine.predict() called before load()")
        prediction = _predict(str(image))
        smiles = prediction.get("predicted_smiles", "")
        # v1 returns "" when the graph could not be turned into a molfile: no molfile.
        return OcsrResult(smiles, prediction.get("predicted_molfile", "") or None)


def register(name: Engine) -> None:
    """Called by marcus.workers.ocsr when `molnextr` is configured."""
    if Engine(name) is not Engine.MOLNEXTR:
        raise ValueError(f"not the MolNexTR engine: {name!r}")
    register_engine(Engine.MOLNEXTR, MolnextrEngine)
