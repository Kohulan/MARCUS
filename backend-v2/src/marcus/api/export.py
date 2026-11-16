"""Paper export: pick one structure per segment, then write JSON, CSV or SDF.

Choice per segment, in order: a curated SMILES/molfile (a SMILES is derived from a
curated molfile when none was given); else the newest valid prediction
of the paper's engine; else the newest valid prediction of any engine. Rejected segments
and segments without any structure are left out.
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass
from typing import Literal

from rdkit import Chem

from marcus.api.chem import mol_for_sdf, smiles_from_molfile
from marcus.core.models import Curation, Paper, Prediction, Segment

ExportFormat = Literal["json", "csv", "sdf"]

MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "sdf": "chemical/x-mdl-sdfile",
}


@dataclass(frozen=True)
class Chosen:
    segment_id: uuid.UUID
    page: int
    idx: int
    smiles: str | None
    molfile: str | None
    source: Literal["curated", "predicted"]


def choose(
    paper: Paper,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
) -> list[Chosen]:
    """`segments` in (page, idx) order; `predictions` per segment, newest first."""
    out: list[Chosen] = []
    for seg in segments:
        cur = curations.get(seg.id)
        if cur is not None and cur.status == "rejected":
            continue
        if cur is not None and (cur.smiles or cur.molfile):
            smiles = cur.smiles or smiles_from_molfile(cur.molfile)
            out.append(Chosen(seg.id, seg.page, seg.idx, smiles, cur.molfile, "curated"))
            continue
        valid = [p for p in predictions.get(seg.id, []) if p.valid]
        pick = next((p for p in valid if p.engine == paper.engine), None) or next(iter(valid), None)
        if pick is not None:
            out.append(Chosen(seg.id, seg.page, seg.idx, pick.smiles, pick.molfile, "predicted"))
    return out


def to_json(paper: Paper, chosen: list[Chosen]) -> bytes:
    doc = {
        "paper": {
            "id": str(paper.id),
            "display_name": paper.display_name,
            "doi": paper.doi,
            "pages": paper.pages,
            "engine": paper.engine,
            "created_at": paper.created_at.isoformat(),
        },
        "segments": [
            {
                "segment_id": str(c.segment_id),
                "page": c.page,
                "idx": c.idx,
                "smiles": c.smiles,
                "molfile": c.molfile,
                "source": c.source,
            }
            for c in chosen
        ],
    }
    return json.dumps(doc, indent=2).encode("utf-8")


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value: object) -> str:
    """A spreadsheet must not run a cell as a formula: prefix risky starts with a quote."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def to_csv(chosen: list[Chosen]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["segment_id", "page", "idx", "smiles", "source"])
    for c in chosen:
        row = [c.segment_id, c.page, c.idx, c.smiles, c.source]
        writer.writerow([csv_cell(v) for v in row])
    return buf.getvalue().encode("utf-8")


def to_sdf(chosen: list[Chosen]) -> bytes:
    """One record per segment RDKit can build a molecule for; RDKit writes every record."""
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    for c in chosen:
        mol = mol_for_sdf(c.smiles, c.molfile)
        if mol is None:
            continue
        mol.SetProp("_Name", str(c.segment_id))
        mol.SetProp("segment_id", str(c.segment_id))
        mol.SetIntProp("page", c.page)
        mol.SetIntProp("idx", c.idx)
        writer.write(mol)
    writer.close()
    return buf.getvalue().encode("utf-8")


def render(fmt: ExportFormat, paper: Paper, chosen: list[Chosen]) -> bytes:
    if fmt == "json":
        return to_json(paper, chosen)
    if fmt == "csv":
        return to_csv(chosen)
    return to_sdf(chosen)
