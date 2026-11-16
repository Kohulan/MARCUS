"""TensorFlow runtime limits for model workers. Must run in the worker process BEFORE any model
loads (TensorFlow refuses both changes once its runtime is initialised).

`limit_tf_memory` gives TensorFlow one logical GPU device capped at `mb` MiB (env
`MARCUS_GPU_MEM_MB`), so the TF worker cannot take the whole card from the torch workers that
share it. Without a visible GPU, or without a budget, it does nothing.

`limit_tf_threads` caps TensorFlow's CPU thread pools (settings `tf_intra_threads` /
`tf_inter_threads`, env `MARCUS_TF_INTRA_THREADS` / `MARCUS_TF_INTER_THREADS`), so one worker on
CPU does not take every core next to docling.
"""

import logging
import os

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
