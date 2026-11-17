"""MolNexTR OCSR engine `molnextr` (torch, q.molnextr worker).

Called exactly as v1 (`backend/app/modules/ocsr_wrapper.py` get_molnextr_prediction with
data_type "both", which v1's generate_both route uses):
`MolNexTR.get_predictions(str(path), atoms_bonds=False, smiles=True, predicted_molfile=True)`,
returning the predicted SMILES and molfile. The library's `MolNexTRSingleton` picks the device
as in v1 (CUDA when torch sees a GPU, else CPU) and falls back to CPU on a failed prediction.

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
from collections.abc import Callable
from pathlib import Path

from marcus.core.enums import Engine
from marcus.workers.ocsr.base import OcsrResult, register_engine
from marcus.workers.ocsr.torch_common import package_commit, serial_graph_conversion, warm_up

log = logging.getLogger(__name__)

DIST_NAME = "MolNexTR"
CHECKPOINT = "molnextr_best.pth"  # MolNexTRSingleton._initialize_model

_lock = threading.Lock()
_get_predictions: Callable | None = None  # MolNexTR.molnextr.get_predictions


def checkpoint_path() -> Path:
    """Where MolNexTRSingleton looks for the checkpoint before it would download it."""
    import pystow

    return Path(pystow.join("molnextr", name=CHECKPOINT, ensure_exists=False))


def _predict(path: str) -> dict:
    return _get_predictions(path, atoms_bonds=False, smiles=True, predicted_molfile=True)


def _load() -> None:
    global _get_predictions
    with _lock:
        if _get_predictions is not None:
            return
        from marcus.workers import gpu

        gpu.prepare_torch()
        weights = checkpoint_path()
        if not weights.is_file():
            raise RuntimeError(f"MolNexTR checkpoint missing at {weights} (baked into the image)")

        start = time.monotonic()
        import MolNexTR.chemical as chemical
        import MolNexTR.model as model
        import MolNexTR.molnextr as module

        model.convert_graph_to_smiles = serial_graph_conversion(chemical._convert_graph_to_smiles)
        module.MolNexTRSingleton.get_instance()
        _, device_name = module.MolNexTRSingleton.get_device()
        _get_predictions = module.get_predictions
        log.info("MolNexTR loaded on %s in %.1f s", device_name, time.monotonic() - start)
        warm_up("MolNexTR", lambda p: _predict(p).get("predicted_smiles", ""))


class MolnextrEngine:
    name = Engine.MOLNEXTR

    def __init__(self) -> None:
        self.version = package_commit(DIST_NAME)

    def load(self) -> None:
        _load()

    def predict(self, image: Path) -> OcsrResult:
        if _get_predictions is None:
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
