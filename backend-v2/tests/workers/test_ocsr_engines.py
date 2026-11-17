"""OCSR engine configuration, preload hook and the DECIMER engine wrapper (no TensorFlow).

The DECIMER tests run the real `marcus.workers.ocsr.decimer` against a stub `tensorflow` and a
stub `DECIMER` package that, like decimer 2.8.0, loads both SavedModels and turns on GPU memory
growth when `DECIMER.decimer` is imported.
"""

import sys
import textwrap
import types
import weakref

import pytest
from celery.signals import worker_process_init

from marcus.core.enums import Engine
from marcus.workers import ocsr
from marcus.workers.ocsr import base, decimer
from marcus.workers.ocsr.base import OcsrResult


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    monkeypatch.setattr(base, "FACTORIES", dict(base.FACTORIES))
    monkeypatch.setattr(base, "PRELOAD", set(base.PRELOAD))
    monkeypatch.setattr(base, "_ENGINES", {})
    monkeypatch.delenv("MARCUS_OCSR_ENGINES", raising=False)


# --- configuration -----------------------------------------------------------------------


def test_no_engines_configured_by_default():
    assert base.configured_engines() == []
    assert ocsr.register_configured_engines() == []


def test_configured_engines_parse_and_dedupe(monkeypatch):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", " decimer, decimer-hand ,decimer,")
    assert base.configured_engines() == [Engine.DECIMER, Engine.DECIMER_HAND]


def test_unknown_engine_is_a_config_error(monkeypatch):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer,bogus")
    with pytest.raises(RuntimeError, match="MARCUS_OCSR_ENGINES"):
        base.configured_engines()


def test_unbuilt_engine_is_refused_at_start(monkeypatch):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "molnextr")
    with pytest.raises(RuntimeError, match="not available in this build"):
        ocsr.register_configured_engines()


def test_decimer_worker_registers_both_but_preloads_only_normal(monkeypatch):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer,decimer-hand")
    assert ocsr.register_configured_engines() == [Engine.DECIMER, Engine.DECIMER_HAND]
    assert {"decimer", "decimer-hand"} <= set(base.FACTORIES)
    assert "decimer" in base.PRELOAD
    assert "decimer-hand" not in base.PRELOAD


def test_only_configured_engines_are_registered(monkeypatch):
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer")
    ocsr.register_configured_engines()
    assert "decimer" in base.FACTORIES
    assert "decimer-hand" not in base.FACTORIES
    with pytest.raises(RuntimeError, match="not available"):
        base.get_engine(Engine.DECIMER_HAND)


def test_decimer_register_rejects_other_engines():
    with pytest.raises(ValueError):
        decimer.register(Engine.MOLNEXTR)


# --- preload at pool process start ---------------------------------------------------------


class StubEngine:
    def __init__(self, name):
        self.name = name
        self.version = "stub"
        self.loaded = 0

    def load(self):
        self.loaded += 1

    def predict(self, image):
        return OcsrResult("C", None)


def _connected(signal, func) -> bool:
    for _, ref in signal.receivers:
        target = ref() if isinstance(ref, weakref.ReferenceType) else ref
        if target is func:
            return True
    return False


def test_preload_hook_connected_to_worker_process_init():
    assert _connected(worker_process_init, base.preload_engines)


def test_preload_loads_preload_engines_only(monkeypatch):
    normal, hand = StubEngine("decimer"), StubEngine("decimer-hand")
    base.register_engine(Engine.DECIMER, lambda: normal)
    base.register_engine(Engine.DECIMER_HAND, lambda: hand, preload=False)
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer,decimer-hand")
    monkeypatch.setattr(base, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(base, "abort_worker", lambda: aborted.append(True))

    base.preload_engines(sender=None)

    assert normal.loaded == 1 and hand.loaded == 0 and not aborted
    assert set(base._ENGINES) == {"decimer"}
    assert base.get_engine(Engine.DECIMER) is normal and normal.loaded == 1  # reused
    assert base.get_engine(Engine.DECIMER_HAND) is hand and hand.loaded == 1  # first request


def test_preload_skips_registered_but_unconfigured_engines(monkeypatch):
    normal = StubEngine("decimer")
    base.register_engine(Engine.DECIMER, lambda: normal)
    monkeypatch.setattr(base, "in_pool_process", lambda: True)
    base.preload_engines(sender=None)  # MARCUS_OCSR_ENGINES unset
    assert normal.loaded == 0


def test_preload_failure_stops_the_worker(monkeypatch):
    def broken():
        raise OSError("weights missing")

    base.register_engine(Engine.DECIMER, broken)
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer")
    monkeypatch.setattr(base, "in_pool_process", lambda: True)
    aborted = []
    monkeypatch.setattr(base, "abort_worker", lambda: aborted.append(True))
    base.preload_engines(sender=None)
    assert aborted == [True]


def test_preload_does_nothing_outside_a_pool_process(monkeypatch):
    called = []
    base.register_engine(Engine.DECIMER, lambda: called.append("load"))
    monkeypatch.setenv("MARCUS_OCSR_ENGINES", "decimer")
    monkeypatch.setattr(base, "abort_worker", lambda: called.append("abort"))
    assert base.in_pool_process() is False  # pytest runs in billiard's MainProcess
    base.preload_engines(sender=None)
    assert called == []


# --- DecimerEngine against stub tensorflow / DECIMER ---------------------------------------

FAKE_DECIMER = textwrap.dedent(
    """
    import tensorflow as tf

    for gpu in tf.config.experimental.list_physical_devices("GPU"):
        tf.config.experimental.set_memory_growth(gpu, True)

    DECIMER_V2 = tf.saved_model.load("{root}/DECIMER_model")
    DECIMER_Hand_drawn = tf.saved_model.load("{hand}")


    def predict_SMILES(image_input, confidence=False, hand_drawn=False):
        model = DECIMER_Hand_drawn if hand_drawn else DECIMER_V2
        return model(image_input) + "|" + str(confidence)
    """
)


class StubTF(types.ModuleType):
    def __init__(self):
        super().__init__("tensorflow")
        self.loads, self.growth = [], []
        self.saved_model = types.SimpleNamespace(load=self._load)
        self.config = types.SimpleNamespace(
            experimental=types.SimpleNamespace(
                list_physical_devices=lambda kind: ["GPU:0"],
                set_memory_growth=lambda dev, on: self.growth.append((dev, on)),
            )
        )
        self.real_load = self.saved_model.load
        self.real_growth = self.config.experimental.set_memory_growth

    def _load(self, path):
        name = path.rstrip("/").rsplit("/", 1)[-1]
        self.loads.append(name)
        return lambda image: f"{name}:{image}"


@pytest.fixture
def fake_decimer(monkeypatch, tmp_path):
    """Stub tensorflow + DECIMER package; returns a function that writes DECIMER and the stub."""
    tf = StubTF()
    monkeypatch.setitem(sys.modules, "tensorflow", tf)
    for name in ("DECIMER", "DECIMER.decimer"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(decimer, "_predict", None)
    monkeypatch.setattr(decimer, "_hand", None)
    monkeypatch.setattr(decimer, "_warmed_up", False)
    monkeypatch.setattr(decimer, "decimer_version", lambda: "2.8.0")
    limits = []
    from marcus.workers import gpu

    monkeypatch.setattr(gpu, "limit_tf_threads", lambda a, b: limits.append(("threads", a, b)))
    monkeypatch.setattr(gpu, "gpu_mem_mb_from_env", lambda: None)
    monkeypatch.setattr(gpu, "limit_tf_memory", lambda mb: limits.append(("mem", mb)) or False)
    tf.limits = limits

    def write(hand_dir=None):
        pkg = tmp_path / "DECIMER"
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").write_text("")
        root = "/opt/pystow/DECIMER-V2"
        hand = hand_dir or f"{root}/DECIMER_HandDrawn_model"
        (pkg / "decimer.py").write_text(FAKE_DECIMER.format(root=root, hand=hand))
        return tf

    yield write
    for name in ("DECIMER", "DECIMER.decimer"):
        sys.modules.pop(name, None)


def test_normal_engine_loads_only_the_normal_model(fake_decimer):
    tf = fake_decimer()
    engine = decimer.DecimerEngine(hand_drawn=False)
    assert engine.name == Engine.DECIMER and engine.version == "2.8.0"
    engine.load()

    assert tf.loads == ["DECIMER_model"]
    assert decimer.hand_model_loaded() is False
    assert decimer._warmed_up is True  # one prediction at load: the first step pays no warm-up
    assert tf.limits[0][0] == "threads"  # caps before the import
    # the import-time patches are undone
    assert tf.saved_model.load == tf.real_load
    assert tf.config.experimental.set_memory_growth == tf.real_growth

    result = engine.predict("/data/crop.png")
    assert result == OcsrResult("DECIMER_model:/data/crop.png|False", None)
    assert tf.loads == ["DECIMER_model"]


def test_hand_engine_loads_the_hand_model_on_first_request(fake_decimer, tmp_path):
    tf = fake_decimer()
    decimer.DecimerEngine(hand_drawn=False).load()
    hand = decimer.DecimerEngine(hand_drawn=True)
    assert hand.name == Engine.DECIMER_HAND and hand.version == "2.8.0-hand"
    assert decimer.hand_model_loaded() is False  # constructing loads nothing

    hand.load()

    assert tf.loads == ["DECIMER_model", "DECIMER_HandDrawn_model"]
    assert decimer.hand_model_loaded() is True
    out = hand.predict(tmp_path / "x.png")  # Path in, str to predict_SMILES
    assert out.smiles == f"DECIMER_HandDrawn_model:{tmp_path / 'x.png'}|False"
    hand.load()
    assert tf.loads.count("DECIMER_HandDrawn_model") == 1


def test_hand_model_also_loads_when_called_directly(fake_decimer):
    tf = fake_decimer()
    engine = decimer.DecimerEngine(hand_drawn=False)
    engine.load()
    decimer._hand("img")  # predict_SMILES(hand_drawn=True) calls the model object
    assert tf.loads == ["DECIMER_model", "DECIMER_HandDrawn_model"]


def test_memory_growth_skipped_only_with_a_gpu_budget(fake_decimer, monkeypatch):
    from marcus.workers import gpu

    tf = fake_decimer()
    decimer.DecimerEngine(hand_drawn=False).load()
    assert tf.growth == [("GPU:0", True)]  # no budget: decimer's own setting stays

    monkeypatch.setattr(decimer, "_predict", None)
    monkeypatch.setattr(decimer, "_hand", None)
    sys.modules.pop("DECIMER.decimer", None)
    sys.modules.pop("DECIMER", None)
    tf.growth.clear()
    monkeypatch.setattr(gpu, "gpu_mem_mb_from_env", lambda: 3072)
    monkeypatch.setattr(gpu, "limit_tf_memory", lambda mb: True)
    decimer.DecimerEngine(hand_drawn=False).load()
    assert tf.growth == []
    assert tf.config.experimental.set_memory_growth == tf.real_growth


def test_eager_hand_model_is_refused(fake_decimer):
    """If decimer ever loads the hand-drawn model from another directory, fail loudly rather
    than silently keep two models in memory."""
    fake_decimer(hand_dir="/elsewhere/hand_model")
    with pytest.raises(RuntimeError, match="eagerly"):
        decimer.DecimerEngine(hand_drawn=False).load()


def test_predict_before_load_fails(monkeypatch):
    monkeypatch.setattr(decimer, "_predict", None)
    monkeypatch.setattr(decimer, "decimer_version", lambda: "2.8.0")
    with pytest.raises(RuntimeError, match="load"):
        decimer.DecimerEngine(hand_drawn=False).predict("/x.png")


def test_decimer_module_does_not_import_tensorflow():
    import subprocess

    code = (
        "import sys, marcus.workers.ocsr.decimer; "
        "assert 'tensorflow' not in sys.modules and 'DECIMER' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_hand_engine_alone_does_not_warm_up_the_normal_model(fake_decimer):
    fake_decimer()
    decimer.DecimerEngine(hand_drawn=True).load()
    assert decimer.hand_model_loaded() is True
    assert decimer._warmed_up is False


# --- recycle the pool process after an interrupted model load ------------------------------


@pytest.fixture
def no_recycle(monkeypatch):
    from marcus.workers import runtime

    monkeypatch.setattr(runtime, "_recycle_reason", None)
    return runtime


def test_interrupted_hand_load_marks_the_process_for_recycling(no_recycle):
    from celery.exceptions import SoftTimeLimitExceeded

    calls = []

    def slow_load(path):
        calls.append(path)
        raise SoftTimeLimitExceeded()

    lazy = decimer.LazySavedModel(slow_load, "/m/DECIMER_HandDrawn_model")
    with pytest.raises(SoftTimeLimitExceeded):
        lazy.ensure_loaded()
    assert lazy.loaded is False
    assert no_recycle.recycle_requested() is True


def test_successful_hand_load_does_not_recycle(no_recycle):
    lazy = decimer.LazySavedModel(lambda path: object(), "/m/DECIMER_HandDrawn_model")
    lazy.ensure_loaded()
    assert lazy.loaded is True
    assert no_recycle.recycle_requested() is False


def test_recycle_handler_connected_to_task_postrun():
    from celery.signals import task_postrun

    from marcus.workers import runtime

    assert _connected(task_postrun, runtime.recycle_if_requested)


def test_recycle_handler_exits_the_pool_process_only_when_marked(no_recycle, monkeypatch):
    exits = []

    def fake_exit(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(no_recycle.os, "_exit", fake_exit)
    monkeypatch.setattr(no_recycle, "in_pool_process", lambda: True)

    no_recycle.recycle_if_requested(sender=None)  # not marked: nothing
    assert exits == []

    no_recycle.request_recycle("interrupted model load")
    with pytest.raises(SystemExit):
        no_recycle.recycle_if_requested(sender=None)
    assert exits == [0]


def test_recycle_handler_never_exits_outside_a_pool_process(no_recycle, monkeypatch):
    exits = []
    monkeypatch.setattr(no_recycle.os, "_exit", lambda code: exits.append(code))
    no_recycle.request_recycle("x")
    assert no_recycle.in_pool_process() is False
    no_recycle.recycle_if_requested(sender=None)
    assert exits == []
