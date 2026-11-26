"""The paper layout: an image's atom positions as a V2000 molfile in the image's pixels.

MolScribe reads atoms and bonds with positions off the image, also when its answer is invalid.
Its worker fits them to the image's ink and writes them as a molfile (marcus.workers.ocsr.layout):
x in pixels, y = -pixel y (y up, as every molfile), symbols and bond orders as read, no wedges,
never sanitized. It is stored beside the prediction (`predictions.layout`) and used only to draw:
as the first orientation template of every answer of that image (marcus.workers.orient) and for
the overlay on the paper (marcus.workers.tools.paper_view). Never the editor's start, the
R-group labels or the export: it is a reading aid, not a structure.

The molfile's title line says what it is and how well it fits:

    MARCUS layout fit=<mean px from the ink> bond=<median bond length, px> size=<width>x<height>

`fit` is the mean distance from points along each bond to the nearest dark pixel. The overlay
is offered only when it is at most OVERLAY_MAX_FIT_SHARE of the median bond length
(`overlay_ok`); a layout that fits worse still gives the drawings their shape. Measured
2026-11-26 on 17 real crops against the same graphs mirrored: see the tests
(tests/workers/test_paper_layout.py) and the branch report.

Nothing here imports RDKit: the API, the tools worker and the OCSR worker all read the header.
"""

import math
import re
from dataclasses import dataclass

PREFIX = "MARCUS layout"
OVERLAY_MAX_FIT_SHARE = 0.04
_HEADER = re.compile(
    r"MARCUS layout fit=(\d+(?:\.\d+)?) bond=(\d+(?:\.\d+)?) size=(\d{1,6})x(\d{1,6})\s*$"
)


@dataclass(frozen=True)
class LayoutInfo:
    fit: float  # mean px from the ink
    bond: float  # median bond length, px
    width: int  # the image the positions are in
    height: int

    @property
    def overlay_ok(self) -> bool:
        """The fit is good enough to draw the answers over the image."""
        return self.fit <= OVERLAY_MAX_FIT_SHARE * self.bond


def header(fit: float, bond: float, width: int, height: int) -> str:
    return f"{PREFIX} fit={fit:.2f} bond={bond:.1f} size={width}x{height}"


def info(molfile: str | None) -> LayoutInfo | None:
    """The header of a paper layout molfile; None for any other molfile."""
    if not molfile or not molfile.startswith(PREFIX):
        return None
    match = _HEADER.match(molfile.split("\n", 1)[0])
    if match is None:
        return None
    fit, bond = float(match[1]), float(match[2])
    width, height = int(match[3]), int(match[4])
    if not (math.isfinite(fit) and math.isfinite(bond)) or bond <= 0 or min(width, height) < 1:
        return None
    return LayoutInfo(fit, bond, width, height)


def is_layout(molfile: str | None) -> bool:
    return info(molfile) is not None
