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


# --- torch ---------------------------------------------------------------------------------


class FakeCuda:
    def __init__(self, devices):
        self.devices = devices
        self.fractions = []

    def is_available(self):
        return self.devices > 0

    def device_count(self):
        return self.devices

    def set_per_process_memory_fraction(self, fraction, device):
        self.fractions.append((fraction, device))


@pytest.fixture
def fake_torch(monkeypatch):
    def install(devices=0):
        torch = types.ModuleType("torch")
        torch.cuda = FakeCuda(devices)
        torch.threads = []

        def set_num_threads(n):
            torch.threads.append(("intra", n))

        def set_num_interop_threads(n):
            if any(kind == "inter" for kind, _ in torch.threads):
                raise RuntimeError("cannot set number of interop threads twice")
            torch.threads.append(("inter", n))

        torch.set_num_threads = set_num_threads
        torch.set_num_interop_threads = set_num_interop_threads
        monkeypatch.setitem(sys.modules, "torch", torch)
        return torch

    monkeypatch.setattr(gpu, "_torch_threads", None)
    monkeypatch.setattr(gpu, "_torch_limited", False)
    for var in gpu.THREAD_ENV_VARS:
        # setenv first: monkeypatch then restores the original state after the test, also the
        # values limit_torch_threads writes with os.environ.setdefault.
        monkeypatch.setenv(var, "unset")
        monkeypatch.delenv(var)
    return install


def test_torch_threads_capped_with_one_interop_thread(fake_torch):
    import os

    torch = fake_torch()
    gpu.limit_torch_threads(4)
    assert torch.threads == [("intra", 4), ("inter", 1)]
    assert [os.environ[var] for var in gpu.THREAD_ENV_VARS] == ["4", "4", "4"]
    gpu.limit_torch_threads(4)  # once per process: the same value again is fine
    assert torch.threads == [("intra", 4), ("inter", 1)]
    with pytest.raises(RuntimeError, match="already set"):
        gpu.limit_torch_threads(8)


def test_torch_thread_env_already_set_is_kept(fake_torch, monkeypatch):
    import os

    fake_torch()
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    gpu.limit_torch_threads(4)
    assert os.environ["OMP_NUM_THREADS"] == "2"
    assert os.environ["MKL_NUM_THREADS"] == "4"


def test_torch_threads_none_is_a_noop_and_does_not_import_torch(monkeypatch):
    monkeypatch.setattr(gpu, "_torch_threads", None)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    gpu.limit_torch_threads(None)
    assert "torch" not in sys.modules


def test_torch_threads_must_be_positive(fake_torch):
    fake_torch()
    with pytest.raises(ValueError):
        gpu.limit_torch_threads(0)


def test_torch_memory_none_is_a_noop_and_does_not_import_torch(monkeypatch):
    monkeypatch.setattr(gpu, "_torch_limited", False)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    assert gpu.limit_torch_memory(None) is False
    assert "torch" not in sys.modules


def test_torch_memory_without_cuda_is_a_noop(fake_torch):
    torch = fake_torch(devices=0)
    assert gpu.limit_torch_memory(0.4) is False
    assert torch.cuda.fractions == []


def test_torch_memory_fraction_on_every_gpu_once(fake_torch):
    torch = fake_torch(devices=2)
    assert gpu.limit_torch_memory(0.4) is True
    assert torch.cuda.fractions == [(0.4, 0), (0.4, 1)]
    assert gpu.limit_torch_memory(0.4) is True  # once per process
    assert len(torch.cuda.fractions) == 2


@pytest.mark.parametrize("fraction", [0, -0.1, 1.5])
def test_torch_memory_fraction_out_of_range(fake_torch, fraction):
    fake_torch(devices=1)
    with pytest.raises(ValueError):
        gpu.limit_torch_memory(fraction)


def test_torch_memory_fraction_from_env(monkeypatch):
    monkeypatch.delenv("MARCUS_TORCH_MEM_FRACTION", raising=False)
    assert gpu.torch_mem_fraction_from_env() is None
    monkeypatch.setenv("MARCUS_TORCH_MEM_FRACTION", " ")
    assert gpu.torch_mem_fraction_from_env() is None
    monkeypatch.setenv("MARCUS_TORCH_MEM_FRACTION", "0.25")
    assert gpu.torch_mem_fraction_from_env() == 0.25
    monkeypatch.setenv("MARCUS_TORCH_MEM_FRACTION", "2")
    with pytest.raises(ValueError):
        gpu.torch_mem_fraction_from_env()


def test_prepare_torch_uses_settings_and_env(fake_torch, monkeypatch):
    torch = fake_torch(devices=1)
    monkeypatch.setenv("MARCUS_TORCH_THREADS", "3")
    monkeypatch.setenv("MARCUS_TORCH_MEM_FRACTION", "0.5")
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    gpu.prepare_torch()
    assert torch.threads == [("intra", 3), ("inter", 1)]
    assert torch.cuda.fractions == [(0.5, 0)]
