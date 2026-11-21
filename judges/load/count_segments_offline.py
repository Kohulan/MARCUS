"""Count the structures v1's segmenter finds in a PDF WITHOUT the HTTP API, one page per worker process.

For fixtures too big for the CPU copy's one-page-at-a-time path (the 2,020-structure paper has 169 pages, ~28 s per
page on CPU = 80 min). It uses the same library call as the backend (decimer_segmentation.segment_chemical_structures
on a 300 DPI render, expand=True), but separate PROCESSES, so it avoids the thread race that crashes the backend.
Run it inside the production image (no code is changed, nothing is installed):

  docker run --rm -e CUDA_VISIBLE_DEVICES= -e TF_NUM_INTRAOP_THREADS=2 -e TF_NUM_INTEROP_THREADS=2 \
     -v $PWD/judges/load:/work:ro -v $PWD/judges/stack/data/cache:/root/.data \
     marcus-backend:latest python /work/count_segments_offline.py /work/data/fixtures/synth_2020.pdf 12

Prints one JSON object: segments per page (0-based page index), total, pages with none.
"""
import json
import multiprocessing as mp
import sys
import time


def _init():
    global _seg, _fitz, _np
    import fitz
    import numpy as np
    from decimer_segmentation import segment_chemical_structures

    _seg, _fitz, _np = segment_chemical_structures, fitz, np


def _page(args):
    path, p = args
    t = time.time()
    doc = _fitz.open(path)
    pix = doc[p].get_pixmap(matrix=_fitz.Matrix(300 / 72, 300 / 72), alpha=False)
    img = _np.frombuffer(pix.samples, dtype=_np.uint8).reshape(pix.h, pix.w, pix.n)
    try:
        segs, _ = _seg(img, expand=True, return_bboxes=True)
        n = sum(1 for s in segs if s.shape[0] and s.shape[1])
        return p, n, None, round(time.time() - t, 1)
    except Exception as e:
        return p, 0, f"{type(e).__name__}: {str(e)[:120]}", round(time.time() - t, 1)


if __name__ == "__main__":
    import fitz

    path, workers = sys.argv[1], int(sys.argv[2])
    n_pages = fitz.open(path).page_count
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers, initializer=_init) as pool:
        res = sorted(pool.imap_unordered(_page, [(path, p) for p in range(n_pages)]))
    per = {p: n for p, n, _, _ in res}
    errs = {p: e for p, _, e, _ in res if e}
    print(json.dumps({"pdf": path, "pages": n_pages, "segments_total": sum(per.values()), "pages_without_segments": [p for p, n in per.items() if n == 0],
                      "errors": errs, "per_page": [per[p] for p in range(n_pages)], "seconds": round(time.time() - t0, 1)}))
