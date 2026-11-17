"""D4 fix round 1: pixel comparison of v2's stored crops (one v2 paper of synth_190) with v1's crop files of the
same fixture, matched by (page, index). Usage (judges env on jarvis):

    python crop_parity.py <v1 all_segments dir> <dir with v2 by-sha PNGs> <map.csv: page,idx,sha256> <out.json>
"""
import json
import sys

import numpy as np
from PIL import Image

v1_dir, v2_dir, map_csv, out = sys.argv[1:5]
rows, same = [], 0
for line in open(map_csv):
    p, i, sha = line.strip().split(",")
    a = np.asarray(Image.open(f"{v1_dir}/page_{p}_{i}_segmented.png").convert("RGB")).astype(int)
    b = np.asarray(Image.open(f"{v2_dir}/{sha}.png").convert("RGB")).astype(int)
    if a.shape == b.shape and (a == b).all():
        same += 1
        continue
    row = {"page": int(p), "idx": int(i), "same_shape": a.shape == b.shape}
    if a.shape == b.shape:
        d = (a != b).any(axis=2)
        row.update(pixels=int(d.sum()), equal_after_rb_swap=bool((a == b[..., ::-1]).all()))
    rows.append(row)
res = {"crops": same + len(rows), "pixel_identical": same, "differ": rows}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res))
