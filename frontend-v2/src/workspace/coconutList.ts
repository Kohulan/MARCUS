// What "Send N to COCONUT" hands the submit form. Pure, so the rules are pinned by tests.
import type { SegmentOut } from "../api/types";
import { hasDummyAtom, type HeldStructure } from "../coconut/held";
import type { SubmitStructure } from "../coconut/types";
import { hasDrawing, shownStructure } from "./cardState";
import { UNLABELLED } from "./rgroups";

/** The structures to send, and the accepted ones left out because they have R-groups. */
export type CoconutList = { send: SubmitStructure[]; held: HeldStructure[] };

/**
 * The accepted structures that have a structure (the rule of bulk Accept: `hasDrawing`), in
 * (page, idx) order. `segments` is the whole paper in that order, so `n` is numbered before
 * any filter and matches the `[nn]` tag. The SMILES is the curated one, else the shown
 * prediction's; a curation with a molfile and no SMILES has no SMILES to send and is left
 * out (the prediction would be another structure).
 *
 * A structure that still has R-group placeholders stands for several compounds: it is never
 * sent (owner decision), but listed in `held` so the form says which and why. The curator may
 * still accept it in MARCUS.
 */
export function coconutStructures(segments: SegmentOut[], paperEngine: string): CoconutList {
  const send: SubmitStructure[] = [];
  const held: HeldStructure[] = [];
  segments.forEach((s, i) => {
    if (s.curation?.status !== "accepted" || !hasDrawing(s)) return;
    const { smiles, rgroups, placeholder } = shownStructure(s, paperEngine);
    // Held for any placeholder atom: the server's word (whatever labels the page shows), or a
    // dummy atom without labels (a curation not yet answered by the server).
    const isHeld = placeholder || (smiles !== null && hasDummyAtom(smiles));
    const labels = rgroups.length > 0 || !isHeld ? rgroups : [UNLABELLED];
    if (labels.length > 0) held.push({ segmentId: s.id, n: i + 1, rgroups: labels });
    else if (smiles) send.push({ segmentId: s.id, n: i + 1, smiles });
  });
  return { send, held };
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
