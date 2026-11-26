// The COCONUT side form of the Paper view (owner decision 2026-11-25): one accepted structure,
// its form filled as far as MARCUS knows, and the same content as MARCUS JSON. Pure.
import type { PaperDetail, RgroupRow, SegmentOut } from "../api/types";
import { structureTag } from "../ui/tag";
import { heldReason } from "./held";
import type { PaperFields, StructureFields, SubmitStructure } from "./types";
import { builtFromText } from "../workspace/built";
import { shownStructure } from "../workspace/cardState";
import { type CoconutStart, heldLabels, submissionTitle } from "../workspace/coconutList";
import type { ReviewRow } from "../workspace/useReviewRows";

/** A built structure's scaffold (Markush Phase 3): its id and tag number. */
export type BuiltFrom = NonNullable<ReviewRow["builtFrom"]>;

/** What can be sent now; null with the reason when it cannot (not accepted, R-groups, none). */
export type SideStructure =
  | { structure: SubmitStructure; heldReason: null }
  | { structure: null; heldReason: string };

/** The form's starting values. */
export type SideStart = { paper: PaperFields; fields: StructureFields };

/** "Built from [01]: R1 = OMe, R2 = H (row 20a)"; "" without a scaffold. */
export function structuralComment(built: BuiltFrom | null, row: RgroupRow | null): string {
  if (!built) return "";
  const head = builtFromText(built.n);
  if (!row) return head;
  const groups = Object.entries(row.groups)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k} = ${v}`)
    .join(", ");
  return `${head}: ${groups} (row ${row.compound})`;
}

/** The structure the card shows now (an edit or a new read counts), by the batch form's rule. */
export function sideStructure(segment: SegmentOut, n: number, paperEngine: string): SideStructure {
  if (segment.curation?.status !== "accepted") {
    return { structure: null, heldReason: `Accept ${structureTag(n)} to send it` };
  }
  const { smiles, labels } = heldLabels(segment, paperEngine);
  if (labels.length > 0) {
    return { structure: null, heldReason: heldReason({ segmentId: segment.id, n, rgroups: labels }) };
  }
  if (!smiles) return { structure: null, heldReason: "No structure to send" };
  return { structure: { segmentId: segment.id, n, smiles }, heldReason: null };
}

export function sideStart(
  segment: SegmentOut,
  paper: PaperDetail,
  start: CoconutStart,
  built: BuiltFrom | null,
  row: RgroupRow | null,
): SideStart {
  const name =
    segment.compound_name?.trim() || (segment.compound_id ? `Compound ${segment.compound_id}` : "");
  return {
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
  structure: SubmitStructure,
  paperFields: PaperFields,
  fields: StructureFields,
  built: BuiltFrom | null,
  row: RgroupRow | null,
) {
  const { molfile, rgroups } = shownStructure(segment, paper.engine);
  return {
    format: "marcus-coconut-1",
    paper: { id: paper.id, doi: paper.doi, title: paper.title, display_name: paper.display_name },
    structure: {
      segment_id: segment.id,
      tag: structureTag(structure.n),
      page: segment.page + 1,
      compound_id: segment.compound_id ?? null,
      name: fields.name.trim(),
      smiles: structure.smiles,
      molfile,
      rgroups,
      built_from: built
        ? { tag: structureTag(built.n), row: row?.compound ?? null, groups: row?.groups ?? null }
        : null,
    },
    coconut: {
      title: paperFields.title,
      evidence: paperFields.evidence,
      comment: paperFields.comment,
      organisms: paperFields.organisms,
      structural_comments: fields.structuralComments,
      // as the report COCONUT gets (buildReport): the DOI; the compound ID is structure.compound_id
      reference_id: paperFields.doi.trim(),
      link: "",
    },
  };
}

/** marcus-coconut-<paper id start>-<compound ID or nn>.json */
export function jsonFileName(paperId: string, compoundId: string | null | undefined, n: number): string {
  const what = (compoundId ?? "").replace(/[^A-Za-z0-9._-]/g, "") || structureTag(n).slice(1, -1);
  return `marcus-coconut-${paperId.split("-")[0]}-${what}.json`;
}
