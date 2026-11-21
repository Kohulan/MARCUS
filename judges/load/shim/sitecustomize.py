"""Local-copy workaround, NOT part of v1.

v1's segmentation renders PDF pages in a ThreadPoolExecutor whose size comes from the machine's RAM:
    batch_size = min(4, max(1, SC_PHYS_PAGES * SC_PAGE_SIZE // 1 GiB))
so on any real machine it uses 4 threads that share one fitz document and one Keras Mask R-CNN model.
On the CPU-only local copy that crashes the whole backend process (heap corruption: glibc "corrupted size vs.
prev_size", TensorFlow protobuf SIGSEGV) on EVERY multi-page PDF we tried (5 of 5 attempts).
Reporting 1 GiB of RAM to the app makes v1 take its own low-memory path (batch size 1, one worker thread),
which is the code the authors wrote for small machines. No app code is changed.

Mounted into the private local copy by load/docker-compose.local-private.yml (PYTHONPATH=/shim:/app).
The jarvis (GPU) copy does NOT use this shim and runs v1 as is.
"""
import os

_orig = os.sysconf


def _sysconf(name):
    v = _orig(name)
    if name == "SC_PHYS_PAGES":
        gib = float(os.environ.get("JUDGE_FAKE_RAM_GIB", "1"))
        return min(v, int(gib * (1 << 30) // _orig("SC_PAGE_SIZE")))
    return v


os.sysconf = _sysconf
