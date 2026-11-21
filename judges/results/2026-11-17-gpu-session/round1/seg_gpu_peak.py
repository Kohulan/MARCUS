"""D4 fix round 1: GPU memory the segmenter really needs (TensorFlow allocator peak per page), and segmentation
through the shipping code path. Run in marcus-v2-tf:cuda with --gpus and the pages mounted at /pages.

MODE=growth  memory growth, no budget (the library's own setting, as v1): peak = allocator bytes in use at the
             worst moment of each page.
MODE=budget  the worker loader (marcus.workers.segment.DecimerSegmenter) with MARCUS_GPU_MEM_MB set, as the
             worker-segment container does.
"""
import glob
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

mode = os.environ.get("MODE", "growth")
pages = sorted(glob.glob("/pages/*.png"))
if mode == "growth":
    import tensorflow as tf
    from decimer_segmentation import segment_chemical_structures

    def run(p):
        return segment_chemical_structures(np.array(Image.open(p).convert("RGB"), dtype=np.uint8),
                                           expand=True, return_bboxes=True)[0]
else:
    from marcus.workers.segment import DecimerSegmenter

    s = DecimerSegmenter()
    s.load()
    import tensorflow as tf

    def run(p):
        return s.segment(Path(p))

dev = "GPU:0"
rows = []
t_all = time.time()
for p in pages:
    try:
        tf.config.experimental.reset_memory_stats(dev)
    except Exception:
        pass  # the memory-stats reset is optional: not every TF build has it
    t = time.time()
    err = None
    try:
        n = len(run(p))
    except Exception as e:
        n, err = None, f"{type(e).__name__}: {str(e)[:200]}"
    mi = tf.config.experimental.get_memory_info(dev)
    rows.append({"page": os.path.basename(p), "segments": n, "s": round(time.time() - t, 2),
                 "peak_mib": round(mi["peak"] / 2**20), "current_mib": round(mi["current"] / 2**20), "error": err})
    print(json.dumps(rows[-1]), flush=True)
print("SUMMARY " + json.dumps({"mode": mode, "budget_mb": os.environ.get("MARCUS_GPU_MEM_MB"), "pages": len(rows),
                              "max_peak_mib": max(r["peak_mib"] for r in rows),
                              "errors": sum(1 for r in rows if r["error"]),
                              "segments": sum(r["segments"] or 0 for r in rows),
                              "total_s": round(time.time() - t_all, 1)}))
