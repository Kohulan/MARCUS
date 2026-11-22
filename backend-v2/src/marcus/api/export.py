"""Paper export: pick one structure per segment, then write JSON, CSV or SDF.

Choice per segment, in order: a curated SMILES/molfile (a SMILES is derived from a
curated molfile when none was given); else the newest valid prediction
of the paper's engine; else the newest valid prediction of any engine. Segments without any
structure are left out; rejected ones too, unless `include_rejected`.

A structure with R-group placeholders (marcus.core.rgroups) stands for several compounds. It is
exported as what it is, a scaffold, never as a finished compound: every format names its labels
(JSON `rgroups`, CSV column `rgroups`, SDF property MARCUS_RGROUPS), [] / empty for none: those
its page's text names (the paper's page label index; all of them when it names none). It is
kept rather than left out, so an export still holds every structure the curator accepted.

A scaffold's R-group rows read by the local R-group model (Markush Phase 2), when it has them, go
with its segment: JSON `rgroup_rows` ({labels, rows: [{compound, groups}], truncated, model,
model_version, extracted_at}, null without), SDF property MARCUS_RGROUP_ROWS (that object as
one line of compact JSON). CSV keeps one row per structure and its columns as they are. The rows
are those of the prediction the export picks; a curated structure with R-group labels takes
those of the prediction that would be shown without the curation. They are model output, not
checked by MARCUS.

The paper's annotation (owner decision 6), when it has one, goes with every format: the JSON
file has a paper-level `annotation` object (the values shown: the curator's, else the model's;
plus the model's own), CSV rows get the organism/source fields as columns and SDF records as
properties (values joined with "; "). `annotation` is a plain dict (api.annotation.for_export).

A paper with a main figure (the main_figures row) exports each compound once: a repeat of a
main-figure structure on another page (marcus.core.main_figure) is left out, and JSON names its
pages on the main-figure record (`also_on_pages`, 0-based as `page`; [] for none) and the main
page on the paper (`main_figure_page`, null without one).
"""

import csv
import io
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from rdkit import Chem

from marcus.api.chem import mol_for_sdf, smiles_from_molfile
from marcus.api.read import named_on, pick_prediction
from marcus.core.models import Curation, Paper, Prediction, Segment
from marcus.core.rgroup_labels import shown_labels
from marcus.core.rgroups import rgroup_labels

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
    rgroups: tuple[str, ...] = ()  # R-group labels: a scaffold, not a finished compound
    rgroup_rows: dict | None = None  # the R-group model's rows (api.rgroups.for_export)
    also_on_pages: tuple[int, ...] = ()  # pages of its repeats (a main-figure structure)


def _labels(row: Curation | Prediction, named: list[str] | None) -> tuple[str, ...]:
    """The row's labels shown on its page (`named`: the labels the page names, shown_labels):
    of its stored labels, or of those computed for a row without (export runs in the chem
    process)."""
    labels = row.rgroups if row.rgroups is not None else rgroup_labels(row.smiles, row.molfile)
    return tuple(shown_labels(list(labels), named))


def choose(
    paper: Paper,
    segments: list[Segment],
    curations: dict[uuid.UUID, Curation],
    predictions: dict[uuid.UUID, list[Prediction]],
    include_rejected: bool = False,
    rgroup_rows: dict[uuid.UUID, dict] | None = None,
    repeat_of: dict[uuid.UUID, uuid.UUID] | None = None,
) -> list[Chosen]:
    """`segments` in (page, idx) order; `predictions` per segment, newest first; `rgroup_rows`
    per prediction id (api.rgroups.for_export); `repeat_of`: repeat segment id -> its
    main-figure segment id (api.read.repeat_links): repeats are left out."""
    rows_of = rgroup_rows or {}
    repeats = repeat_of or {}
    also_on: dict[uuid.UUID, list[int]] = defaultdict(list)
    for seg in segments:
        if seg.id in repeats:
            also_on[repeats[seg.id]].append(seg.page)
    out: list[Chosen] = []
    for seg in segments:
        if seg.id in repeats:
            continue
        named = named_on(paper.rgroup_text_labels, seg.page)
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
            "also_on_pages": tuple(sorted(set(also_on.get(seg.id, ())))),
        }
        valid = [p for p in predictions.get(seg.id, []) if p.valid]
        pick = pick_prediction(valid, paper.engine)
        if cur is not None and (cur.smiles or cur.molfile):
            smiles = cur.smiles or smiles_from_molfile(cur.molfile)
            labels = _labels(cur, named)
            out.append(
                Chosen(
                    **row,
                    smiles=smiles,
                    molfile=cur.molfile,
                    source="curated",
                    edited=True,
                    rgroups=labels,
                    rgroup_rows=rows_of.get(pick.id) if labels and pick is not None else None,
                )
            )
            continue
        if pick is not None:
            labels = _labels(pick, named)
            out.append(
                Chosen(
                    **row,
                    smiles=pick.smiles,
                    molfile=pick.molfile,
                    source="predicted",
                    engine=pick.engine,
                    rgroups=labels,
                    rgroup_rows=rows_of.get(pick.id) if labels else None,
                )
            )
    return out


# organism/source fields of the annotation as CSV columns and SDF properties
SOURCE_FIELDS = (
    ("organism", "organism_or_species", "MARCUS_ORGANISM"),
    ("organism_part", "organism_part", "MARCUS_ORGANISM_PART"),
    ("geo_location", "geo_location", "MARCUS_GEO_LOCATION"),
    ("kingdom", "Kingdom", "MARCUS_KINGDOM"),
)
VALUE_SEPARATOR = "; "


def _source_values(annotation: dict | None) -> list[str]:
    """The organism/source fields' shown values, joined, in SOURCE_FIELDS order ("" if none)."""
    values = (annotation or {}).get("values") or {}
    return [VALUE_SEPARATOR.join(values.get(field, [])) for _, field, _ in SOURCE_FIELDS]


def to_json(
    paper: Paper,
    chosen: list[Chosen],
    annotation: dict | None = None,
    main_figure_page: int | None = None,
) -> bytes:
    doc = {
        "paper": {
            "id": str(paper.id),
            "display_name": paper.display_name,
            "doi": paper.doi,
            "pages": paper.pages,
            "engine": paper.engine,
            "created_at": paper.created_at.isoformat(),
            "main_figure_page": main_figure_page,
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
                "rgroups": list(c.rgroups),
                "rgroup_rows": c.rgroup_rows,
                "also_on_pages": list(c.also_on_pages),
            }
            for c in chosen
        ],
        "annotation": annotation,
    }
    return json.dumps(doc, indent=2).encode("utf-8")


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value: object) -> str:
    """A spreadsheet must not run a cell as a formula: prefix risky starts with a quote."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


CSV_HEADER = [
    "segment_id", "page", "idx", "smiles", "status", "engine", "note", "edited", "source",
    *(column for column, _, _ in SOURCE_FIELDS), "rgroups",
]  # fmt: skip


def to_csv(chosen: list[Chosen], annotation: dict | None = None) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    source = _source_values(annotation)
    for c in chosen:
        row = [
            c.segment_id, c.page, c.idx, c.smiles, c.status, c.engine, c.note,
            "true" if c.edited else "false", c.source, *source, VALUE_SEPARATOR.join(c.rgroups),
        ]  # fmt: skip
        writer.writerow([csv_cell(v) for v in row])
    return buf.getvalue().encode("utf-8")


def sdf_text(value: str) -> str:
    """One line of an SDF data field: every line break becomes one space, and the text never
    starts with `$$$$` (a record end). A blank line would end the field, `$$$$` the record."""
    text = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return " " + text if text.startswith("$$$$") else text


def rgroup_rows_json(rows: dict) -> str:
    """The rows object as one line of compact JSON (no raw line break: JSON escapes them)."""
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def to_sdf(chosen: list[Chosen], annotation: dict | None = None) -> bytes:
    """One record per segment RDKit can build a molecule for; RDKit writes every record."""
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    source = [
        (prop, value)
        for (_, _, prop), value in zip(SOURCE_FIELDS, _source_values(annotation), strict=True)
        if value
    ]
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
        if c.rgroups:
            mol.SetProp("MARCUS_RGROUPS", sdf_text(VALUE_SEPARATOR.join(c.rgroups)))
        if c.rgroup_rows is not None:
            mol.SetProp("MARCUS_RGROUP_ROWS", sdf_text(rgroup_rows_json(c.rgroup_rows)))
        for prop, value in source:
            mol.SetProp(prop, sdf_text(value))
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
    annotation: dict | None = None,
    rgroup_rows: dict[uuid.UUID, dict] | None = None,
    repeat_of: dict[uuid.UUID, uuid.UUID] | None = None,
    main_figure_page: int | None = None,
) -> bytes:
    """choose + render: all the RDKit work of an export (molfile to SMILES, SDF records), for
    marcus.api.chempool (RDKit holds the GIL; the rows travel pickled, detached)."""
    status = status or ("accepted" if fmt == "sdf" else "all")
    chosen = choose(
        paper, segments, curations, predictions, include_rejected=status == "all",
        rgroup_rows=rgroup_rows, repeat_of=repeat_of,
    )  # fmt: skip
    if status == "accepted":
        chosen = [c for c in chosen if c.status == "accepted"]
    if fmt == "json":
        return to_json(paper, chosen, annotation, main_figure_page)
    if fmt == "csv":
        return to_csv(chosen, annotation)
    return to_sdf(chosen, annotation)
