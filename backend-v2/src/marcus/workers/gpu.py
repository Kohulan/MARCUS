"""TensorFlow and PyTorch runtime limits for model workers. Must run in the worker process BEFORE
any model loads (TensorFlow refuses both changes once its runtime is initialised; torch refuses a
second inter-op thread setting).

`limit_tf_memory` gives TensorFlow one logical GPU device capped at `mb` MiB (env
`MARCUS_GPU_MEM_MB`), so the TF worker cannot take the whole card from the torch workers that
share it. Without a visible GPU, or without a budget, it does nothing.

`limit_tf_threads` caps TensorFlow's CPU thread pools (settings `tf_intra_threads` /
`tf_inter_threads`, env `MARCUS_TF_INTRA_THREADS` / `MARCUS_TF_INTER_THREADS`), so one worker on
CPU does not take every core next to docling.

`limit_torch_threads` does the same for torch (setting `torch_threads`, env
`MARCUS_TORCH_THREADS`): intra-op threads = n, inter-op threads = 1, and OMP / MKL / OpenBLAS
thread variables (only where not already set; compose sets them, because OpenBLAS reads its
variable when numpy is first imported). `limit_torch_memory` caps a torch process to a share of
each GPU's memory (env `MARCUS_TORCH_MEM_FRACTION`); without CUDA it does nothing.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

log = logging.getLogger(__name__)

GPU_MEM_ENV = "MARCUS_GPU_MEM_MB"

_tf_limited = False


def gpu_mem_mb_from_env() -> int | None:
    raw = os.environ.get(GPU_MEM_ENV, "").strip()
    if not raw:
        return None
    mb = int(raw)
    if mb <= 0:
        raise ValueError(f"{GPU_MEM_ENV} must be a positive number of MiB, got {raw!r}")
    return mb


def limit_tf_memory(mb: int | None) -> bool:
    """Cap TensorFlow to one logical GPU device with `memory_limit=mb` MiB.

    Returns True when a limit was applied (now or by an earlier call in this process), False
    when there is no GPU or no budget. TensorFlow refuses the change once its runtime is
    initialised; that RuntimeError is raised, not hidden: a worker must not run unbudgeted.
    """
    global _tf_limited
    if _tf_limited:
        return True
    if mb is None:
        return False
    if mb <= 0:
        raise ValueError(f"GPU memory limit must be positive, got {mb}")
    import tensorflow as tf

    gpus = tf.config.list_physical_devices("GPU")
    if not gpus:
        return False
    tf.config.set_visible_devices(gpus[0], "GPU")
    tf.config.set_logical_device_configuration(
        gpus[0], [tf.config.LogicalDeviceConfiguration(memory_limit=mb)]
    )
    _tf_limited = True
    log.info("TensorFlow limited to %s MiB on %s", mb, gpus[0].name)
    return True


def limit_tf_threads(intra: int | None, inter: int | None) -> None:
    """Set TensorFlow's intra-op / inter-op thread pool sizes; None keeps TF's default."""
    for name, value in (("intra", intra), ("inter", inter)):
        if value is not None and value <= 0:
            raise ValueError(f"TF {name}-op threads must be positive, got {value}")
    if intra is None and inter is None:
        return
    import tensorflow as tf

    if intra is not None:
        tf.config.threading.set_intra_op_parallelism_threads(intra)
    if inter is not None:
        tf.config.threading.set_inter_op_parallelism_threads(inter)
    log.info("TensorFlow threads: intra-op %s, inter-op %s", intra, inter)


def prepare_tf() -> bool:
    """Thread caps and GPU memory budget for a TensorFlow model worker; call before the model
    loads. True when a GPU memory budget is in force (then see skip_memory_growth)."""
    from marcus.core.settings import get_settings

    settings = get_settings()
    limit_tf_threads(settings.tf_intra_threads, settings.tf_inter_threads)
    return limit_tf_memory(gpu_mem_mb_from_env())


@contextmanager
def skip_memory_growth(active: bool, library: str) -> Iterator[None]:
    """While `active` (a GPU budget is in force), `tf.config.experimental.set_memory_growth` does
    nothing (logged); the real one is restored afterwards, also when the body raises.

    decimer and decimer_segmentation turn memory growth on for every GPU when imported, which
    TensorFlow refuses once the budget's logical device exists ("Cannot set memory growth on
    device when virtual devices configured"): the import, and so the model load, would fail.
    Without a budget nothing is patched (v1 behaviour: memory growth on)."""
    if not active:
        yield
        return
    import tensorflow as tf

    real_growth = tf.config.experimental.set_memory_growth

    def no_growth(device, enable):
        log.info("GPU memory budget set: skipping %s's set_memory_growth(%s)", library, enable)

    tf.config.experimental.set_memory_growth = no_growth
    try:
        yield
    finally:
        tf.config.experimental.set_memory_growth = real_growth


TORCH_MEM_FRACTION_ENV = "MARCUS_TORCH_MEM_FRACTION"
THREAD_ENV_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")

_torch_threads: int | None = None
_torch_limited = False


def torch_mem_fraction_from_env() -> float | None:
    raw = os.environ.get(TORCH_MEM_FRACTION_ENV, "").strip()
    if not raw:
        return None
    fraction = float(raw)
    if not 0 < fraction <= 1:
        raise ValueError(f"{TORCH_MEM_FRACTION_ENV} must be in (0, 1], got {raw!r}")
    return fraction


def limit_torch_threads(n: int | None) -> None:
    """torch intra-op threads = n, inter-op threads = 1; None keeps torch's default (every core).

    Once per process: torch refuses a second inter-op setting, so a different `n` later is an
    error (a worker must not silently run with other caps than configured).
    """
    global _torch_threads
    if n is None:
        return
    if n <= 0:
        raise ValueError(f"torch threads must be positive, got {n}")
    if _torch_threads is not None:
        if _torch_threads != n:
            raise RuntimeError(f"torch threads already set to {_torch_threads}, not {n}")
        return
    for var in THREAD_ENV_VARS:
        if os.environ.setdefault(var, str(n)) != str(n):
            log.warning("%s=%s differs from torch threads %s", var, os.environ[var], n)
    import torch

    torch.set_num_threads(n)
    torch.set_num_interop_threads(1)
    _torch_threads = n
    log.info("torch threads: intra-op %s, inter-op 1", n)


def limit_torch_memory(fraction: float | None) -> bool:
    """Cap this process to `fraction` of each visible GPU's memory (torch caching allocator).

    Returns True when a limit was applied (now or by an earlier call in this process), False
    without a budget or without CUDA.
    """
    global _torch_limited
    if _torch_limited:
        return True
    if fraction is None:
        return False
    if not 0 < fraction <= 1:
        raise ValueError(f"GPU memory fraction must be in (0, 1], got {fraction}")
    import torch

    if not torch.cuda.is_available():
        return False
    for device in range(torch.cuda.device_count()):
        torch.cuda.set_per_process_memory_fraction(fraction, device)
    _torch_limited = True
    log.info("torch limited to %.0f%% of GPU memory", fraction * 100)
    return True


def prepare_torch() -> None:
    """Thread caps and GPU memory budget for a torch model worker; call before the model loads."""
    from marcus.core.settings import get_settings

    limit_torch_threads(get_settings().torch_threads)
    limit_torch_memory(torch_mem_fraction_from_env())
