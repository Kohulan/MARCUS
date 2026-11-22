"""Real-model smoke test of R-group reading: one scaffold page through the rgroups step's own code
(marcus.workers.rgroups.handler.read_scaffold) against a running llama-server with the MARCUS
model and its vision projector (the GPU stack's `llama-server`, which annotation shares).

    python ops/rgroup_smoke.py --url http://127.0.0.1:8080 --pdf paper.pdf --page 3 \\
        --labels R1,R2 [--text docling.json] [--timeout 600]

Inside the GPU stack: run it in the api image on the `llm` network, --url http://llama-server:8080.

`--page` counts from 1, as Docling and the paper do. The page is rendered at 300 dpi with
PyMuPDF as the render_page step does (marcus.workers.pdfsafe_child.op_render), into a temporary
data root; `--text` is the paper's Docling document as MARCUS stores it (GET
/api/v2/papers/{id}/text); without it the model reads the page image alone. Prints the request
size, the time and the rows. Needs the api extra (PyMuPDF, Pillow). Nothing is stored; the
server must be one you run (it gets the page image and text).
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--page", required=True, type=int)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--text", type=Path)
    ap.add_argument("--timeout", type=float, default=600.0)
    a = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="rgroup-smoke-"))
    try:
        import os

        os.environ["MARCUS_DATA_ROOT"] = str(root)
        import pymupdf

        from marcus.core.settings import get_settings
        from marcus.core.storage import page_image_path, text_path
        from marcus.workers.rgroups.handler import read_scaffold
        from marcus.workers.rgroups.llama import LlamaRgroupReader

        settings = get_settings()
        pid = uuid.uuid4()
        page0 = a.page - 1
        out = page_image_path(pid, page0)
        out.parent.mkdir(parents=True)
        with pymupdf.open(a.pdf) as doc:
            zoom = 300 / 72
            pix = doc[page0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            out.write_bytes(pix.tobytes("png"))
        if a.text is not None:
            shutil.copyfile(a.text, text_path(pid))
        labels = [lab.strip() for lab in a.labels.split(",") if lab.strip()]
        reader = LlamaRgroupReader(
            a.url, a.timeout, settings.rgroup_model, settings.rgroup_model_version
        )
        start = time.monotonic()
        result = read_scaffold(reader, pid, page0, labels)
        took = time.monotonic() - start
        print(f"{len(result['rows'])} rows in {took:.1f} s (truncated: {result['truncated']})")
        print(json.dumps(result["rows"], ensure_ascii=False, indent=1))
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
