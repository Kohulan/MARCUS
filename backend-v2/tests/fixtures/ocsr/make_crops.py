"""Regenerate the OCSR fixture crops: v2's DecimerSegmenter on synth_015.pdf (TF image only).

Saves every crop exactly as the segment worker stores it (RGB PNG, segment._write_crop) plus a
meta.json with page, index (position in the segmenter output), bbox and sha256:

  docker run --rm --network none -v $PWD/tests/fixtures/ocsr/make_crops.py:/w/make_crops.py:ro \
      -v OUT:/out marcus-v2-tf-test:local \
      python /w/make_crops.py /app/tests/fixtures/pdfs/synth_015.pdf /out

Not a test (never collected); see tests/fixtures/v1_decimer.json for the crops that were kept.
"""

import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image

from marcus.workers import pdfsafe
from marcus.workers.segment import DecimerSegmenter


def main(pdf: Path, out: Path, pages: int = 5) -> None:
    seg = DecimerSegmenter()
    seg.load()
    meta = []
    for page in range(pages):
        png = Path("/tmp") / f"page{page}.png"
        pdfsafe.render_page_png(pdf, page, png, timeout_s=60)
        for index, (array, bbox) in enumerate(seg.segment(png)):
            buf = io.BytesIO()
            Image.fromarray(array).save(buf, format="PNG")
            data = buf.getvalue()
            name = f"synth015_p{page}_i{index}.png"
            (out / name).write_bytes(data)
            meta.append(
                {
                    "page": page,
                    "index": index,
                    "bbox": list(bbox),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "file": name,
                }
            )
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
