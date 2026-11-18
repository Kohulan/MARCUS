"""Seed one big finished paper for the frontend's big-paper e2e (frontend-v2/e2e/big-paper.spec.ts).

Runs INSIDE the api container of the local stack (the image has the app and Pillow, not
tests/; Postgres is not published), read from stdin:

    docker compose -p marcus-v2 exec -T api python - < tests/e2e/seed_big_paper.py

Creates a browser owner, a `done` paper with 10 pages (white 1240 x 1754 PNGs), 200 segments
(20 per page on a 4 x 5 grid) with their crop PNGs, an `unchecked` curation each and one valid
`decimer` prediction each with 200 distinct SMILES. Their stored depictions (from an earlier
run) are removed, so the tools worker has 200 depictions to draw on every run. Prints one JSON line: {"paper_id": ..., "token": ...}. The token is the owner cookie
value (`marcus_owner`). Only for the local `marcus-v2` project, never production.
"""

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from PIL import Image, ImageDraw

from marcus.core import storage
from marcus.core.db import sync_session
from marcus.core.enums import Engine, OwnerKind, PaperStatus, PriorityClass
from marcus.core.models import Curation, Owner, Paper, Prediction, Segment
from marcus.core.tokens import hash_token, new_token

PAGES = 10
PER_PAGE = 20
COLS, ROWS = 4, 5
PAGE_W, PAGE_H = 1240, 1754


def smiles_for(k: int) -> str:
    """200 distinct SMILES: C, CC, ... (k <= 100), then CO, CCO, ... (k > 100)."""
    return "C" * k if k <= 100 else "C" * (k - 100) + "O"


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def crop_png(k: int) -> bytes:
    """A distinct crop per structure (crops are content-addressed by their sha256)."""
    image = Image.new("RGB", (270, 310), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20 + k % 50, 20, 200 + k % 50, 120 + k // 2], outline="black", width=3)
    draw.text((20, 280), f"{k:03d}", fill="black")
    return png(image)


def forget_depiction(smiles: str) -> None:
    """A stored drawing of this SMILES (or its no-draw marker) from an earlier run: gone."""
    sha = hashlib.sha256(smiles.encode()).hexdigest()
    storage.depiction_path(sha).unlink(missing_ok=True)
    storage.depiction_marker_path(sha).unlink(missing_ok=True)


def bbox(slot: int) -> list[int]:
    """[x0, y0, x1, y1] in page pixels: slot 0..19 on a 4 x 5 grid."""
    col, row = slot % COLS, slot // COLS
    w, h = PAGE_W // COLS, PAGE_H // ROWS
    return [col * w + 20, row * h + 20, col * w + w - 20, row * h + h - 20]


def main() -> None:
    token = new_token()
    now = datetime.now(UTC)
    with sync_session() as s:
        owner = Owner(
            kind=OwnerKind.BROWSER.value,
            token_hash=hash_token(token),
            priority_class=int(PriorityClass.BROWSER),
        )
        s.add(owner)
        s.flush()
        paper = Paper(
            owner_id=owner.id,
            display_name="Big paper (200 structures).pdf",
            pdf_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            bytes=1,
            pages=PAGES,
            engine=Engine.DECIMER.value,
            ocsr_mode="auto",
            status=PaperStatus.DONE.value,
            expires_at=now + timedelta(days=30),
        )
        s.add(paper)
        s.flush()

        blank = png(Image.new("RGB", (PAGE_W, PAGE_H), "white"))
        k = 0
        for page in range(PAGES):
            storage.write_atomic(storage.page_image_path(paper.id, page), blank)
            for idx in range(PER_PAGE):
                k += 1
                forget_depiction(smiles_for(k))
                data = crop_png(k)
                sha = hashlib.sha256(data).hexdigest()
                storage.write_atomic(storage.segment_crop_path(paper.id, sha), data)
                seg = Segment(
                    paper_id=paper.id, page=page, idx=idx, bbox=bbox(idx), image_sha256=sha
                )
                s.add(seg)
                s.flush()
                s.add(Curation(segment_id=seg.id, status="unchecked"))
                s.add(
                    Prediction(
                        segment_id=seg.id,
                        engine=Engine.DECIMER.value,
                        engine_version="seed",
                        smiles=smiles_for(k),
                        valid=True,
                        ms=0,
                    )
                )
        s.commit()
        print(json.dumps({"paper_id": str(paper.id), "token": token}))


main()
