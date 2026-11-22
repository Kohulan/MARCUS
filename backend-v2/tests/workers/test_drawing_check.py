"""The "check this drawing" flag (marcus.workers.drawing_check) on real crops.

The crops in tests/fixtures/drawing_check are DECIMER Segmentation crops (300 DPI, as MARCUS
makes them) from open-access CC BY 4.0 papers in Marine Drugs (MDPI):
- mollisia-chlorinated: 10.3390/md21010032
- sarcophyton-cembranoids: 10.3390/md23120450
- cyanobacterium-taveuniamides: 10.3390/md22010028
- briarane-dichotella: 10.3390/md12126178
The expected features are those MARCUS-training review-feedback/phase-b/MEASURE.md measured.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from marcus.workers import drawing_check

CROPS = Path(__file__).parent.parent / "fixtures" / "drawing_check"

# crop: (hand label, long curved strokes, coloured-ink share, flagged)
CASES = {
    "mollisia-chlorinated__p3_0": ("HMBC/COSY arrows", 8, 0.0, True),
    "cyanobacterium-taveuniamides__p4_0": ("HMBC arrows", 9, 0.028, True),
    "sarcophyton-cembranoids__p4_2": ("coloured NMR marks", 7, 0.267, True),
    "mollisia-chlorinated__p3_1": ("X-ray picture", 5, 0.085, True),
    "briarane-dichotella__p2_1": ("clean, 3 curves from letters", 3, 0.0, False),
    "cyanobacterium-taveuniamides__p2_1": ("clean, blue Cl atoms", 0, 0.172, False),
    "mollisia-chlorinated__p2_8": ("clean", 0, 0.0, False),
    # a known miss (MEASURE.md, accepted by the owner): black delta-delta values, no arrows
    "cyanobacterium-taveuniamides__p6_2": ("black Mosher values", 0, 0.0, False),
}


def crop(name: str) -> np.ndarray:
    return np.asarray(Image.open(CROPS / f"{name}.png").convert("RGB"))


@pytest.mark.parametrize("name", sorted(CASES))
def test_features_and_flag_as_measured(name):
    _, curves, share, flagged = CASES[name]
    got_curves, got_share = drawing_check.features(crop(name))
    assert got_curves == curves
    assert got_share == pytest.approx(share, abs=0.0005)
    assert drawing_check.check_drawing(crop(name)) is flagged


def test_either_feature_alone_flags(monkeypatch):
    for curves, share, flagged in [(4, 0.0, True), (3, 0.249, False), (0, 0.25, True)]:
        monkeypatch.setattr(drawing_check, "features", lambda _rgb, c=curves, s=share: (c, s))
        assert drawing_check.check_drawing(np.zeros((4, 4, 3), np.uint8)) is flagged


def test_blank_crop_is_clean():
    assert drawing_check.check_drawing(np.full((40, 60, 3), 255, np.uint8)) is False


def test_no_flag_without_the_image_libraries(monkeypatch):
    def missing(_rgb):
        raise ImportError("cv2")

    monkeypatch.setattr(drawing_check, "features", missing)
    assert drawing_check.check_drawing(crop("mollisia-chlorinated__p2_8")) is None


def test_a_failure_gives_no_flag(monkeypatch):
    def broken(_rgb):
        raise ValueError("odd image")

    monkeypatch.setattr(drawing_check, "features", broken)
    assert drawing_check.check_drawing(np.zeros((4, 4, 3), np.uint8)) is None
