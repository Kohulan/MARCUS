"""Paper export: pick one structure per segment, then write JSON, CSV or SDF.

Choice per segment, in order: a curated SMILES/molfile (a SMILES is derived from a
curated molfile when none was given); else the newest valid prediction
of the paper's engine; else the newest valid prediction of any engine. Segments without any
structure are left out; rejected ones too, unless `include_rejected`.
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
ExportStatus = Literal["accepted", "all"]
Status = Literal["accepted", "rejected", "unchecked"]

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
    status: Status = "unchecked"
    engine: str | None = None  # engine of the chosen prediction; None for a curated structure
    note: str | None = None
    edited: bool = False  # the curation has its own SMILES or molfile


def pick_prediction(valid: list[Prediction], paper_engine: str) -> Prediction | None:
    """The prediction shown and exported when nothing is curated: of `valid` (newest first),
    the newest of the paper's engine, else the newest of any engine. The one rule; the stored
    depiction (api.depiction.shown_structure) and the UI (cardState shownPrediction) agree."""
    return next((p for p in valid if p.engine == paper_engine), None) or next(iter(valid), None)


def choose(
    paper: Paper,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    include_rejected: bool = False,
) -> list[Chosen]:
    """`segments` in (page, idx) order; `predictions` per segment, newest first."""
    out: list[Chosen] = []
    for seg in segments:
        cur = curations.get(seg.id)
        status: Status = "unchecked" if cur is None else cur.status  # type: ignore[assignment]
        if status == "rejected" and not include_rejected:
            continue
        row = {
            "segment_id": seg.id,
            "page": seg.page,
            "idx": seg.idx,
            "status": status,
            "note": cur.note if cur is not None else None,
        }
        if cur is not None and (cur.smiles or cur.molfile):
            smiles = cur.smiles or smiles_from_molfile(cur.molfile)
            out.append(
                Chosen(**row, smiles=smiles, molfile=cur.molfile, source="curated", edited=True)
            )
            continue
        valid = [p for p in predictions.get(seg.id, []) if p.valid]
        pick = pick_prediction(valid, paper.engine)
        if pick is not None:
            out.append(
                Chosen(
                    **row,
                    smiles=pick.smiles,
                    molfile=pick.molfile,
                    source="predicted",
                    engine=pick.engine,
                )
            )
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
                "status": c.status,
                "engine": c.engine,
                "note": c.note,
                "edited": c.edited,
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


CSV_HEADER = ["segment_id", "page", "idx", "smiles", "status", "engine", "note", "edited", "source"]


def to_csv(chosen: list[Chosen]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for c in chosen:
        row = [
            c.segment_id, c.page, c.idx, c.smiles, c.status, c.engine, c.note,
            "true" if c.edited else "false", c.source,
        ]  # fmt: skip
        writer.writerow([csv_cell(v) for v in row])
    return buf.getvalue().encode("utf-8")


def sdf_text(value: str) -> str:
    """One line of an SDF data field: every line break becomes one space, and the text never
    starts with `$$$$` (a record end). A blank line would end the field, `$$$$` the record."""
    text = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return " " + text if text.startswith("$$$$") else text


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
        mol.SetProp("MARCUS_STATUS", c.status)
        if c.engine is not None:
            mol.SetProp("MARCUS_ENGINE", sdf_text(c.engine))
        if c.note is not None:
            mol.SetProp("MARCUS_NOTE", sdf_text(c.note))
        mol.SetProp("MARCUS_EDITED", "true" if c.edited else "false")
        writer.write(mol)
    writer.close()
    return buf.getvalue().encode("utf-8")


def build(
    fmt: ExportFormat,
    paper: Paper,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    status: ExportStatus | None = None,
) -> bytes:
    """choose + render: all the RDKit work of an export (molfile to SMILES, SDF records), for
    marcus.api.chempool (RDKit holds the GIL; the rows travel pickled, detached)."""
    status = status or ("accepted" if fmt == "sdf" else "all")
    chosen = choose(paper, segments, curations, predictions, include_rejected=status == "all")
    if status == "accepted":
        chosen = [c for c in chosen if c.status == "accepted"]
    if fmt == "json":
        return to_json(paper, chosen)
    if fmt == "csv":
        return to_csv(chosen)
    return to_sdf(chosen)
