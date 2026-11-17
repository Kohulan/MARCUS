"""D4: pixel comparison of v2 crops (one v2 paper of synth_190) with v1's crop files of the same fixture,
matched by (page, index). Usage (judges env on jarvis):

    python crop_parity.py <v1 all_segments dir> <dir with v2 by-sha PNGs> <map.csv: page,idx,sha256> <out.json>
        [--stored-is-engine-input]

Since D4 fix round 2 v2 stores TRUE-colour crops and gives the engines red and blue swapped
(marcus.workers.ocsr.handler.v1_engine_input), which is what v1's cv2.imwrite files hold. So the default compares
v1's file with the ENGINE INPUT (the stored crop with channels 0 and 2 swapped) and must give 190/190 on synth_190.
--stored-is-engine-input compares the stored file as is (round 1, when the stored crop itself was swapped).
"""
import json
import sys

import numpy as np
from PIL import Image

v1_dir, v2_dir, map_csv, out = sys.argv[1:5]
stored_is_input = "--stored-is-engine-input" in sys.argv[5:]
rows, same = [], 0
for line in open(map_csv):
    p, i, sha = line.strip().split(",")
    a = np.asarray(Image.open(f"{v1_dir}/page_{p}_{i}_segmented.png").convert("RGB")).astype(int)
    stored = np.asarray(Image.open(f"{v2_dir}/{sha}.png").convert("RGB")).astype(int)
    b = stored if stored_is_input else stored[..., ::-1]  # the engine input (v1_engine_input)
    if a.shape == b.shape and (a == b).all():
        same += 1
        continue
    row = {"page": int(p), "idx": int(i), "same_shape": a.shape == b.shape}
    if a.shape == b.shape:
        row.update(pixels=int((a != b).any(axis=2).sum()), equal_stored_as_is=bool((a == stored).all()))
    rows.append(row)
res = {"compared": "stored crop" if stored_is_input else "engine input (stored crop, red/blue swapped)",
       "crops": same + len(rows), "pixel_identical": same, "differ": rows}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res))
