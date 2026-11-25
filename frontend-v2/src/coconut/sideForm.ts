// The COCONUT side form of the Paper view (owner decision 2026-11-25): one accepted structure,
// its form filled as far as MARCUS knows, and the same content as MARCUS JSON. Pure.
import type { PaperDetail, RgroupRow, SegmentOut } from "../api/types";
import { structureTag } from "../ui/tag";
import { hasDummyAtom, heldReason } from "./held";
import type { PaperFields, StructureFields, SubmitStructure } from "./types";
import { shownStructure } from "../workspace/cardState";
import { type CoconutStart, submissionTitle } from "../workspace/coconutList";
import { UNLABELLED } from "../workspace/rgroups";

/** A built structure's scaffold (Markush Phase 3): its id and tag number. */
export type BuiltFrom = { segmentId: string; n: number };

export type SideStart = {
  /** What can be sent; null for a structure with R-group placeholders (`heldReason` says why). */
  structure: SubmitStructure | null;
  heldReason: string | null;
  paper: PaperFields;
  fields: StructureFields;
};

/** "Built from [01]: R1 = OMe, R2 = H (row 20a)"; "" without a scaffold row. */
export function structuralComment(built: BuiltFrom | null, row: RgroupRow | null): string {
  if (!built || !row) return built ? `Built from ${structureTag(built.n)}` : "";
  const groups = Object.entries(row.groups)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k} = ${v}`)
    .join(", ");
  return `Built from ${structureTag(built.n)}: ${groups} (row ${row.compound})`;
}

export function sideStart(
  segment: SegmentOut,
  n: number,
  paper: PaperDetail,
  start: CoconutStart,
  built: BuiltFrom | null,
  row: RgroupRow | null,
): SideStart {
  const { smiles, rgroups, placeholder } = shownStructure(segment, paper.engine);
  const held = placeholder || (smiles !== null && hasDummyAtom(smiles));
  const name =
    segment.compound_name?.trim() || (segment.compound_id ? `Compound ${segment.compound_id}` : "");
  return {
    structure: held || !smiles ? null : { segmentId: segment.id, n, smiles },
    heldReason: held
      ? heldReason({ segmentId: segment.id, n, rgroups: rgroups.length ? rgroups : [UNLABELLED] })
      : null,
    paper: {
      title: submissionTitle({ firstAuthor: paper.first_author, year: paper.year }),
      doi: paper.doi ?? "",
      evidence: paper.title ?? "",
      comment: "",
      organisms: start.organisms,
    },
    fields: { name, structuralComments: structuralComment(built, row) },
  };
}

/** The form as MARCUS JSON ("marcus-coconut-1"): exactly what it shows, for this structure. */
export function marcusJson(
  paper: PaperDetail,
  segment: SegmentOut,
  n: number,
  structure: SubmitStructure,
  paperFields: PaperFields,
  fields: StructureFields,
  built: BuiltFrom | null,
  row: RgroupRow | null,
) {
  return {
    format: "marcus-coconut-1",
    paper: { id: paper.id, doi: paper.doi, title: paper.title, display_name: paper.display_name },
    structure: {
      segment_id: segment.id,
      tag: structureTag(n),
      page: segment.page + 1,
      compound_id: segment.compound_id ?? null,
      name: fields.name,
      smiles: structure.smiles,
      built_from: built
        ? { tag: structureTag(built.n), row: row?.compound ?? null, groups: row?.groups ?? null }
        : null,
    },
    coconut: {
      title: paperFields.title,
      evidence: paperFields.evidence,
      comment: fields.comment?.trim() ? fields.comment : paperFields.comment,
      organisms: fields.organism ? [fields.organism] : paperFields.organisms,
      structural_comments: fields.structuralComments,
      reference_id: paperFields.doi.trim(),
    },
  };
}

/** marcus-coconut-<paper id start>-<compound ID or nn>.json */
export function jsonFileName(paperId: string, compoundId: string | null | undefined, n: number): string {
  const what = (compoundId ?? "").replace(/[^A-Za-z0-9._-]/g, "") || structureTag(n).slice(1, -1);
  return `marcus-coconut-${paperId.split("-")[0]}-${what}.json`;
}
