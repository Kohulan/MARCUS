"""DECIMER OCSR engines `decimer` and `decimer-hand` (TensorFlow, q.decimer worker).

Called exactly as v1 (`backend/app/modules/ocsr_wrapper.py` get_decimer_prediction):
`predict_SMILES(str(path), confidence=False, hand_drawn=hand_drawn)`; no molfile.

The hand-drawn model loads on its first request only. decimer itself loads BOTH SavedModels
when `DECIMER.decimer` is imported (module level `get_models`), so the import runs with
`tf.saved_model.load` wrapped: the hand-drawn model directory gets a `LazySavedModel` that
loads the real model when first asked (`DecimerEngine(hand_drawn=True).load()`, or a call).
`predict_SMILES` uses it unchanged (`DECIMER_Hand_drawn(tf.constant(...))`).

Measured on CPU (4 TF threads): import + normal model load 73 s, hand-drawn model load 76 s; the
first call of each model costs ~10 s more than later ones (3-12 s per structure). The normal
engine therefore warms up with one prediction at load (worker start, base.preload_engines);
decimer-hand's first request pays load and warm-up, under its own longer time limit
(queues.ENGINE_TIME_LIMITS).

Before the import: TensorFlow thread caps and the GPU memory budget (marcus.workers.gpu), as in
the segment worker. decimer's import also turns on memory growth for every GPU, which
TensorFlow refuses for a GPU with a memory limit; with a budget that call is skipped.

Weights come from PYSTOW_HOME/DECIMER-V2 (baked into the image, docker/Dockerfile.tf). This
module does not import TensorFlow or decimer at import time.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from importlib.metadata import version as package_version
from pathlib import Path

from marcus.core.enums import Engine
from marcus.core.settings import get_settings
from marcus.workers.ocsr.base import OcsrResult, register_engine

log = logging.getLogger(__name__)

HAND_MODEL_DIR = "DECIMER_HandDrawn_model"  # decimer's `<name>_model` for DECIMER_HandDrawn


class LazySavedModel:
    """Stands in for a SavedModel; loads it with `load_fn(path)` on first use."""

    def __init__(self, load_fn: Callable[[str], object], path: str) -> None:
        self._load_fn = load_fn
        self.path = path
        self._model: object | None = None
        self._lock = threading.Lock()
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def ensure_loaded(self) -> object:
        with self._lock:
            if self._model is None:
                start = time.monotonic()
                self._model = self._load_fn(self.path)
                self.load_seconds = time.monotonic() - start
                log.info("loaded %s in %.1f s", self.path, self.load_seconds)
            return self._model

    def __call__(self, *args, **kwargs):
        return self.ensure_loaded()(*args, **kwargs)


_lock = threading.Lock()
_predict: Callable | None = None  # DECIMER.decimer.predict_SMILES
_hand: LazySavedModel | None = None  # DECIMER.decimer.DECIMER_Hand_drawn


def _import_decimer() -> None:
    """Import DECIMER once per process: tokenizer and normal model load now, hand-drawn later."""
    global _predict, _hand
    with _lock:
        if _predict is not None:
            return
        from marcus.workers import gpu

        settings = get_settings()
        gpu.limit_tf_threads(settings.tf_intra_threads, settings.tf_inter_threads)
        budget = gpu.limit_tf_memory(gpu.gpu_mem_mb_from_env())

        import tensorflow as tf

        real_load = tf.saved_model.load
        real_growth = tf.config.experimental.set_memory_growth

        def load(export_dir, *args, **kwargs):
            if os.path.basename(os.path.normpath(str(export_dir))) == HAND_MODEL_DIR:
                return LazySavedModel(lambda p: real_load(p, *args, **kwargs), str(export_dir))
            return real_load(export_dir, *args, **kwargs)

        def no_growth(device, enable):
            log.info("GPU memory budget set: skipping decimer's set_memory_growth(%s)", enable)

        start = time.monotonic()
        tf.saved_model.load = load
        if budget:
            tf.config.experimental.set_memory_growth = no_growth
        try:
            import DECIMER.decimer as module
        finally:
            tf.saved_model.load = real_load
            tf.config.experimental.set_memory_growth = real_growth
        if not isinstance(module.DECIMER_Hand_drawn, LazySavedModel):
            raise RuntimeError("decimer loaded the hand-drawn model eagerly (library changed?)")
        _predict = module.predict_SMILES
        _hand = module.DECIMER_Hand_drawn
        log.info("decimer %s imported in %.1f s", decimer_version(), time.monotonic() - start)


def hand_model_loaded() -> bool:
    return _hand is not None and _hand.loaded


def decimer_version() -> str:
    return package_version("decimer")


_warmed_up = False


def _warm_up() -> None:
    """One prediction on a small drawn structure: the model's first call costs ~10 s more
    than later ones (measured on CPU), which the first ocsr step would otherwise pay."""
    global _warmed_up
    if _warmed_up:
        return
    import tempfile

    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D

    drawer = rdMolDraw2D.MolDraw2DCairo(300, 300)
    drawer.DrawMolecule(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    drawer.FinishDrawing()
    start = time.monotonic()
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(drawer.GetDrawingText())
        f.flush()
        smiles = _predict(f.name, confidence=False, hand_drawn=False)
    _warmed_up = True
    log.info("decimer warm-up in %.1f s (%s)", time.monotonic() - start, smiles)


class DecimerEngine:
    def __init__(self, hand_drawn: bool) -> None:
        self.hand_drawn = hand_drawn
        self.name = Engine.DECIMER_HAND if hand_drawn else Engine.DECIMER
        self.version = decimer_version() + ("-hand" if hand_drawn else "")

    def load(self) -> None:
        _import_decimer()
        if self.hand_drawn:
            _hand.ensure_loaded()  # no warm-up: the first request pays it, within its limit
        else:
            _warm_up()

    def predict(self, image: Path) -> OcsrResult:
        if _predict is None:
            raise RuntimeError("DecimerEngine.predict() called before load()")
        smiles = _predict(str(image), confidence=False, hand_drawn=self.hand_drawn)
        return OcsrResult(smiles, None)


def register(name: Engine) -> None:
    """Called by marcus.workers.ocsr for each configured engine of this module."""
    if Engine(name) is Engine.DECIMER:
        register_engine(Engine.DECIMER, lambda: DecimerEngine(hand_drawn=False))
    elif Engine(name) is Engine.DECIMER_HAND:
        register_engine(Engine.DECIMER_HAND, lambda: DecimerEngine(hand_drawn=True), preload=False)
    else:
        raise ValueError(f"not a DECIMER engine: {name!r}")
