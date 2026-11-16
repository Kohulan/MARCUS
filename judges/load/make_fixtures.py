"""Synthetic PDFs with a KNOWN number of RDKit-drawn structures (load and fairness fixtures).

    uv run python load/make_fixtures.py                 # builds synth_015, synth_190, synth_2020
    uv run python load/make_fixtures.py --sizes 15      # only some
    uv run python load/make_fixtures.py --check 15      # build if missing, then run v1 segmentation on the
                                                        # LOCAL copy and print segments found vs expected

Output (git-ignored, ``load/data/fixtures/``): ``synth_<N>.pdf`` and ``synth_<N>.json`` (sidecar with the
expected structure for every slot: page (0-based), slot, standardised SMILES, InChIKey, drawn SMILES).

Each page has a title line, two short paragraphs of text and a grid of structures drawn with RDKit as VECTOR
graphics (black and white, as in most journal PDFs) with a caption "Compound n" under each one, so
DECIMER segmentation sees a text page with figures. Structures come from the gold-set manifest
(``goldset/manifest.jsonl`` expected structures, heavy atoms 8..45); lists longer than the pool repeat
the structures, redrawn from a randomised atom order so the layouts differ.

Density: 15 -> 3 per page (5 pages), 190 -> 8 per page (24 pages), 2020 -> 12 per page (169 pages). The
2020 file has far more structures per page than "a few" so that its page count stays that of a long
supplementary document; production's largest paper had 2,020 segments.

Why 15 / 190 / 2020: the production medians and extremes from the load plan (median ~15 segments, p95
190, maximum 2,020).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402
from rdkit import Chem, RDLogger  # noqa: E402
from rdkit.Chem import rdDepictor  # noqa: E402
from rdkit.Chem.Draw import rdMolDraw2D  # noqa: E402

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "data" / "fixtures"
PER_PAGE = {15: 3, 190: 8, 2020: 12}
# grid (cols, rows) and box size (pt) per structures-per-page
GRID = {3: (1, 3, 300, 190), 8: (2, 4, 230, 140), 12: (3, 4, 160, 138)}
PAGE_W, PAGE_H = 595, 842
SEED = 20261116

TEXT = [
    "Isolation and structural elucidation. The crude extract was fractionated by silica gel column",
    "chromatography and purified by semi-preparative HPLC to give the compounds shown below.",
    "Structures were assigned by 1D and 2D NMR and HRMS; the numbering follows the text.",
]


def pool() -> list[dict]:
    rows = [json.loads(l) for l in open(ROOT / "goldset" / "manifest.jsonl")]
    seen, out = set(), []
    for r in rows:
        for e in r["expected"]:
            smi = e.get("std_smiles")
            if not e.get("rdkit_ok") or not smi or smi in seen:
                continue
            m = Chem.MolFromSmiles(smi)
            if m is None or not (8 <= m.GetNumHeavyAtoms() <= 45) or "." in smi:
                continue
            seen.add(smi)
            out.append({"std_smiles": smi, "inchikey": e.get("inchikey"), "source_paper": r["paper_id"]})
    random.Random(SEED).shuffle(out)
    return out


def draw_svg(smiles: str, w: int, h: int, randomise: bool, rng: random.Random) -> tuple[bytes, str]:
    m = Chem.MolFromSmiles(smiles)
    drawn = smiles
    if randomise:
        drawn = Chem.MolToSmiles(m, doRandom=True, canonical=False)
        m = Chem.MolFromSmiles(drawn) or m
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(m)
    d = rdMolDraw2D.MolDraw2DSVG(w * 4, h * 4)  # drawn big, scaled into the box by show_pdf_page
    o = d.drawOptions()
    o.useBWAtomPalette()
    o.bondLineWidth = 3
    o.padding = 0.08
    o.fixedBondLength = 12 * 4  # uniform bond length (12 pt on the page) like real papers; RDKit shrinks if it would not fit
    d.DrawMolecule(m)
    d.FinishDrawing()
    return d.GetDrawingText().encode(), drawn


def build(n: int, pool_rows: list[dict]) -> dict:
    per = PER_PAGE[n]
    cols, rows, bw, bh = GRID[per]
    rng = random.Random(SEED + n)
    chosen = []
    for i in range(n):
        base = pool_rows[i % len(pool_rows)]
        chosen.append({**base, "repeat": i // len(pool_rows)})
    doc = pymupdf.open()
    n_pages = -(-n // per)
    expected = []
    idx = 0
    for p in range(n_pages):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_text((50, 48), f"Synthetic paper {n:04d} structures - page {p + 1} of {n_pages}", fontsize=11)
        y = 68
        for line in TEXT:
            page.insert_text((50, y), line, fontsize=9)
            y += 12
        top = y + 16
        gap_x = (PAGE_W - 100 - cols * bw) / max(cols - 1, 1) if cols > 1 else 0
        for slot in range(per):
            if idx >= n:
                break
            r, c = divmod(slot, cols)
            x0 = 50 + c * (bw + gap_x) if cols > 1 else (PAGE_W - bw) / 2
            y0 = top + r * (bh + 34)
            item = chosen[idx]
            svg, drawn = draw_svg(item["std_smiles"], bw, bh, item["repeat"] > 0, rng)
            sdoc = pymupdf.open(stream=svg, filetype="svg")
            pdfdoc = pymupdf.open("pdf", sdoc.convert_to_pdf())
            page.show_pdf_page(pymupdf.Rect(x0, y0, x0 + bw, y0 + bh), pdfdoc, 0)
            page.insert_text((x0 + bw / 2 - 28, y0 + bh + 14), f"Compound {idx + 1}", fontsize=9)
            expected.append({"index": idx, "page": p, "slot": slot, "std_smiles": item["std_smiles"],
                             "inchikey": item["inchikey"], "drawn_smiles": drawn, "source_paper": item["source_paper"]})
            idx += 1
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = OUT / f"synth_{n:03d}.pdf" if n < 1000 else OUT / f"synth_{n}.pdf"
    doc.save(pdf, deflate=True, garbage=3)
    per_page = [sum(1 for e in expected if e["page"] == p) for p in range(n_pages)]
    meta = {"name": pdf.stem, "n_structures": n, "pages": n_pages, "per_page": per_page, "bytes": pdf.stat().st_size,
            "expected": expected}
    pdf.with_suffix(".json").write_text(json.dumps(meta))
    return meta


def fixture_path(n: int) -> Path:
    return OUT / (f"synth_{n:03d}.pdf" if n < 1000 else f"synth_{n}.pdf")


def ensure(n: int) -> Path:
    p = fixture_path(n)
    if not p.exists():
        build(n, pool())
    return p


def load_meta(n: int) -> dict:
    return json.loads(fixture_path(n).with_suffix(".json").read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sizes", type=int, nargs="*", default=[15, 190, 2020])
    ap.add_argument("--check", type=int, nargs="*", default=None,
                    help="after building, run v1 segmentation (no OCSR) on the LOCAL copy for these sizes")
    ap.add_argument("--base-url", default="http://localhost:19000")
    a = ap.parse_args()
    pl = pool()
    print(f"pool: {len(pl)} distinct structures from the gold-set manifest")
    for n in a.sizes:
        if n not in PER_PAGE:
            raise SystemExit(f"size {n} not supported; use one of {sorted(PER_PAGE)}")
        meta = build(n, pl)
        print(f"built {meta['name']}: {meta['n_structures']} structures, {meta['pages']} pages, {meta['bytes'] / 1e6:.2f} MB")
    for n in a.check or []:
        from common.client_v1 import run_paper

        path = ensure(n)
        meta = load_meta(n)
        rec = run_paper(path, "decimer", base_url=a.base_url, paper_id=path.stem, max_segments=0, segment_timeout_s=3600)
        found = rec["segments_listed"]
        pages_found = {}
        for e in meta["expected"]:
            pages_found.setdefault(e["page"], 0)
        print(json.dumps({"fixture": path.stem, "expected": n, "segments_reported": rec["segments_reported"],
                          "segments_listed": found, "segment_ms": rec["segment_ms"], "pages_total": rec["pages_total"],
                          "page_errors": rec["page_errors"], "fatal_error": rec["fatal_error"]}, indent=1))


if __name__ == "__main__":
    main()
