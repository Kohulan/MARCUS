import sys
import types

import pytest

from marcus.workers import gpu


class FakeTfConfig:
    def __init__(self, gpus):
        self.gpus = gpus
        self.visible = None
        self.logical = None

    def list_physical_devices(self, kind):
        assert kind == "GPU"
        return list(self.gpus)

    def set_visible_devices(self, device, kind):
        self.visible = (device, kind)

    def set_logical_device_configuration(self, device, configs):
        self.logical = (device, configs)

    class threading:  # noqa: N801 - mirrors tf.config.threading
        intra = None
        inter = None

        @classmethod
        def set_intra_op_parallelism_threads(cls, n):
            cls.intra = n

        @classmethod
        def set_inter_op_parallelism_threads(cls, n):
            cls.inter = n

    class LogicalDeviceConfiguration:
        def __init__(self, memory_limit):
            self.memory_limit = memory_limit


@pytest.fixture
def fake_tf(monkeypatch):
    def install(gpus):
        tf = types.ModuleType("tensorflow")
        tf.config = FakeTfConfig(gpus)
        tf.config.threading.intra = tf.config.threading.inter = None
        monkeypatch.setitem(sys.modules, "tensorflow", tf)
        return tf

    monkeypatch.setattr(gpu, "_tf_limited", False)
    return install


def test_no_budget_is_a_noop_and_does_not_import_tensorflow(monkeypatch):
    monkeypatch.setattr(gpu, "_tf_limited", False)
    monkeypatch.delitem(sys.modules, "tensorflow", raising=False)
    assert gpu.limit_tf_memory(None) is False
    assert "tensorflow" not in sys.modules


def test_no_gpu_is_a_noop(fake_tf):
    tf = fake_tf([])
    assert gpu.limit_tf_memory(2048) is False
    assert tf.config.logical is None and tf.config.visible is None


def test_one_logical_device_with_memory_limit(fake_tf):
    gpu0 = types.SimpleNamespace(name="/physical_device:GPU:0")
    gpu1 = types.SimpleNamespace(name="/physical_device:GPU:1")
    tf = fake_tf([gpu0, gpu1])
    assert gpu.limit_tf_memory(2048) is True
    assert tf.config.visible == (gpu0, "GPU")
    device, configs = tf.config.logical
    assert device is gpu0
    assert [c.memory_limit for c in configs] == [2048]
    tf.config.logical = None
    assert gpu.limit_tf_memory(2048) is True  # once per process
    assert tf.config.logical is None


def test_non_positive_limit_rejected(fake_tf):
    fake_tf([])
    with pytest.raises(ValueError):
        gpu.limit_tf_memory(0)


def test_budget_from_env(monkeypatch):
    monkeypatch.delenv("MARCUS_GPU_MEM_MB", raising=False)
    assert gpu.gpu_mem_mb_from_env() is None
    monkeypatch.setenv("MARCUS_GPU_MEM_MB", " ")
    assert gpu.gpu_mem_mb_from_env() is None
    monkeypatch.setenv("MARCUS_GPU_MEM_MB", "4096")
    assert gpu.gpu_mem_mb_from_env() == 4096
    monkeypatch.setenv("MARCUS_GPU_MEM_MB", "-1")
    with pytest.raises(ValueError):
        gpu.gpu_mem_mb_from_env()


def test_thread_caps_applied(fake_tf):
    tf = fake_tf([])
    gpu.limit_tf_threads(4, 2)
    assert (tf.config.threading.intra, tf.config.threading.inter) == (4, 2)


def test_thread_caps_none_is_a_noop_and_does_not_import_tensorflow(monkeypatch):
    monkeypatch.delitem(sys.modules, "tensorflow", raising=False)
    gpu.limit_tf_threads(None, None)
    assert "tensorflow" not in sys.modules


def test_thread_caps_must_be_positive(fake_tf):
    fake_tf([])
    with pytest.raises(ValueError):
        gpu.limit_tf_threads(0, 2)
    with pytest.raises(ValueError):
        gpu.limit_tf_threads(4, -1)
