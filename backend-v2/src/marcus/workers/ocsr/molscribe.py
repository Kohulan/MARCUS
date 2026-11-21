"""MolScribe OCSR engine `molscribe` (torch, q.molscribe worker).

Called exactly as v1 (`backend/app/modules/ocsr_wrapper.py` init_molscribe and
get_molscribe_prediction with data_type "both", which v1's generate_both route uses):
`MolScribe(checkpoint, device=...)` once, then `model.predict_image_file(str(path))`, returning
its "smiles" and "molfile".

Device: setting `molscribe_device` (env MARCUS_MOLSCRIBE_DEVICE), "cpu" by default because v1
forces `torch.device("cpu")`; "cuda" is for the GPU stage once it shows no loss against v1.

The checkpoint v1 fetched with `hf_hub_download("yujieq/MolScribe",
"swin_base_char_aux_1m.pth")` is baked into the image at
`pystow.join("molscribe")/swin_base_char_aux_1m.pth` (PYSTOW_HOME=/opt/pystow, pinned Hugging
Face revision and sha256: docker/MODEL_PINS.md); nothing is downloaded at runtime.
Graph-to-SMILES conversion runs in-process (torch_common.serial_graph_conversion).

Before the import: torch thread caps and the GPU memory share (marcus.workers.gpu.prepare_torch).
The model loads and warms up when the pool process starts (base.preload_engines). This module
does not import torch or molscribe at import time.
"""

import logging
import time
from pathlib import Path

from marcus.core.enums import Engine
from marcus.core.settings import get_settings
from marcus.workers.ocsr.base import OcsrResult, register_engine
from marcus.workers.ocsr.torch_common import package_commit, serial_graph_conversion, warm_up

log = logging.getLogger(__name__)

DIST_NAME = "MolScribe"
CHECKPOINT = "swin_base_char_aux_1m.pth"


def checkpoint_path() -> Path:
    import pystow

    return Path(pystow.join("molscribe", name=CHECKPOINT, ensure_exists=False))


class MolscribeEngine:
    name = Engine.MOLSCRIBE

    def __init__(self) -> None:
        self.version = package_commit(DIST_NAME)
        self.device = None
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from marcus.workers import gpu

        gpu.prepare_torch()
        weights = checkpoint_path()
        if not weights.is_file():
            raise RuntimeError(f"MolScribe checkpoint missing at {weights} (baked into the image)")

        start = time.monotonic()
        import molscribe.chemistry as chemistry
        import molscribe.interface as interface
        import torch

        interface.convert_graph_to_smiles = serial_graph_conversion(
            chemistry._convert_graph_to_smiles
        )
        device = torch.device(get_settings().molscribe_device)
        self._model = interface.MolScribe(str(weights), device=device)
        self.device = device
        log.info("MolScribe loaded on %s in %.1f s", device, time.monotonic() - start)
        warm_up("MolScribe", lambda p: self._model.predict_image_file(p).get("smiles", ""))

    def predict(self, image: Path) -> OcsrResult:
        if self._model is None:
            raise RuntimeError("MolscribeEngine.predict() called before load()")
        prediction = self._model.predict_image_file(str(image))
        # v1 returns "" when the graph could not be turned into a molfile: no molfile.
        return OcsrResult(prediction.get("smiles", ""), prediction.get("molfile", "") or None)


def register(name: Engine) -> None:
    """Called by marcus.workers.ocsr when `molscribe` is configured."""
    if Engine(name) is not Engine.MOLSCRIBE:
        raise ValueError(f"not the MolScribe engine: {name!r}")
    register_engine(Engine.MOLSCRIBE, MolscribeEngine)
