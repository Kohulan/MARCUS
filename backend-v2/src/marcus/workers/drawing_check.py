"""The "check this drawing" flag of a crop (phase B item 1, owner decision 2026-11-22).

A crop is flagged when it is not a clean drawing the engines can read: a drawing covered with
NMR marks (HMBC/COSY/NOESY arrows, bold bonds, coloured labels) or an X-ray / 3D picture. The
rule, from MARCUS-training review-feedback/phase-b/MEASURE.md (140 hand-labelled crops: 32/36
annotated drawings and 10/13 X-ray crops flagged, 0/87 clean drawings):

    long curved strokes >= 4  OR  coloured-ink share >= 0.25

Both features come from the crop image only and take milliseconds:
- long curved strokes: skeletonize the ink, remove the straight Hough segments, count the
  leftover parts longer than 10 % of the crop diagonal (arrows and arcs; bonds are straight);
- coloured-ink share: saturated pixels over ink pixels.

A port of the measurement scripts (phase-b/scripts/feat_curves.py, feat_image.py), unchanged.
opencv and scikit-image are in worker-segment's image (the segmenter needs them); where they are
missing (the fake stack's api image) there is no flag.
"""

import logging

import numpy as np

log = logging.getLogger(__name__)

LONG_CURVES_MIN = 4
COLOUR_SHARE_MIN = 0.25


def features(rgb: np.ndarray) -> tuple[int, float]:
    """(long curved strokes, coloured-ink share) of an RGB uint8 crop."""
    import cv2
    from skimage.morphology import skeletonize

    im = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
    hsv = cv2.cvtColor(im, cv2.COLOR_RGB2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]

    # long curved strokes (feat_curves.py)
    gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    ink = (gray < 170) | ((sat > 100) & (val > 60))
    sk = skeletonize(ink).astype(np.uint8)
    diag = float(np.hypot(*ink.shape))
    lines = cv2.HoughLinesP(
        sk * 255, 1, np.pi / 180, threshold=12, minLineLength=max(10, int(0.035 * diag)),
        maxLineGap=2,
    )  # fmt: skip
    straight = np.zeros_like(sk)
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            cv2.line(straight, (int(x1), int(y1)), (int(x2), int(y2)), 1, 5)
    left = (sk & (1 - straight)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(left, connectivity=8)
    long_curves = 0
    for i in range(1, n):
        _, _, w, h, area = stats[i]
        if area >= max(0.10 * diag, 45) and max(w, h) >= max(0.08 * diag, 30):
            long_curves += 1

    # coloured-ink share (feat_image.py)
    ink2 = (im.min(axis=2) < 200) | (sat > 80)
    colour = (sat > 100) & (val > 60)
    share = float(colour.sum() / max(int(ink2.sum()), 1))
    return long_curves, share


def check_drawing(rgb: np.ndarray) -> bool | None:
    """True: flag the crop ("check this drawing"); None when it cannot be told (the image
    libraries are missing, or the crop is not an image they can read)."""
    try:
        curves, share = features(rgb)
    except ImportError:
        return None
    except Exception:  # noqa: BLE001 - a flag is never worth failing a page for
        log.warning("drawing check failed", exc_info=True)
        return None
    return curves >= LONG_CURVES_MIN or share >= COLOUR_SHARE_MIN
