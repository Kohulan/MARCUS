// What "Send N to COCONUT" hands the submit form. Pure, so the rules are pinned by tests.
import type { SegmentOut } from "../api/types";
import type { SubmitStructure } from "../coconut/types";
import { hasDrawing, shownPrediction } from "./cardState";

/**
 * The accepted structures that have a structure (the rule of bulk Accept: `hasDrawing`), in
 * (page, idx) order. `segments` is the whole paper in that order, so `n` is numbered before
 * any filter and matches the `[nn]` tag. The SMILES is the curated one, else the shown
 * prediction's; a curation with a molfile and no SMILES has no SMILES to send and is left
 * out (the prediction would be another structure).
 */
export function coconutStructures(segments: SegmentOut[], paperEngine: string): SubmitStructure[] {
  return segments.flatMap((s, i): SubmitStructure[] => {
    if (s.curation?.status !== "accepted" || !hasDrawing(s)) return [];
    const c = s.curation;
    const smiles = c.smiles || (c.molfile ? null : shownPrediction(s, paperEngine)?.smiles);
    return smiles ? [{ segmentId: s.id, n: i + 1, smiles }] : [];
  });
}

/**
 * The form's starting title. v1: `MARCUS_Submission <first author> <year>` from the DOI's
 * metadata. Only the known parts are kept.
 */
export function submissionTitle(meta: {
  firstAuthor?: string | null;
  year?: number | null;
}): string {
  const author = meta.firstAuthor?.trim();
  return ["MARCUS_Submission", author, meta.year ?? undefined]
    .filter((part) => part !== undefined && part !== "")
    .join(" ");
}
