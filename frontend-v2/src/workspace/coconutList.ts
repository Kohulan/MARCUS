// What "Send N to COCONUT" hands the submit form. Pure, so the rules are pinned by tests.
import type { AnnotationOut, SegmentOut } from "../api/types";
import { hasDummyAtom, type HeldStructure } from "../coconut/held";
import type { OrganismDraft, SubmitStructure } from "../coconut/types";
import { hasDrawing, shownStructure } from "./cardState";
import { chosenMember, listedSegments, repeatsOf } from "./mainFigure";
import { UNLABELLED } from "./rgroups";

/** The structures to send, and the accepted ones left out because they have R-groups. */
export type CoconutList = { send: SubmitStructure[]; held: HeldStructure[] };

/**
 * The accepted structures that have a structure (the rule of bulk Accept: `hasDrawing`), in
 * the workspace's order. `segments` is the whole paper in that order, so `n` is numbered before
 * any filter and matches the `[nn]` tag; repeats of main-figure structures are left out and
 * not numbered (listedSegments), as in the review rows. The SMILES is the curated one, else
 * the shown prediction's; a curation with a molfile and no SMILES has no SMILES to send and is
 * left out (the prediction would be another structure).
 *
 * A structure that still has R-group placeholders stands for several compounds: it is never
 * sent (owner decision), but listed in `held` so the form says which and why. The curator may
 * still accept it in MARCUS.
 */
/**
 * The shown structure of `s`, and the R-group labels that hold it back (empty: it can be sent).
 * Held for any placeholder atom: the server's word (whatever labels the page shows), or a
 * dummy atom without labels (a curation not yet answered by the server).
 */
export function heldLabels(
  s: SegmentOut,
  paperEngine: string,
): { smiles: string | null; labels: string[] } {
  const { smiles, rgroups, placeholder } = shownStructure(s, paperEngine);
  const isHeld = placeholder || (smiles !== null && hasDummyAtom(smiles));
  return { smiles, labels: rgroups.length > 0 || !isHeld ? rgroups : [UNLABELLED] };
}

export function coconutStructures(segments: SegmentOut[], paperEngine: string): CoconutList {
  const send: SubmitStructure[] = [];
  const held: HeldStructure[] = [];
  // A main structure and its repeats are one compound: sent once, when any member is accepted,
  // with an accepted member's structure (chosenMember), under the main card's tag.
  const groups = repeatsOf(segments);
  listedSegments(segments).forEach((main, i) => {
    const s = chosenMember(main, groups.get(main.id) ?? []);
    if (s.curation?.status !== "accepted" || !hasDrawing(s)) return;
    const { smiles, labels } = heldLabels(s, paperEngine);
    if (labels.length > 0) held.push({ segmentId: main.id, n: i + 1, rgroups: labels });
    else if (smiles) send.push({ segmentId: main.id, n: i + 1, smiles });
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

/** The COCONUT form's starting organisms, and the note they carry when they are the model's. */
export type CoconutStart = { organisms: OrganismDraft[]; note: string | undefined };

/**
 * The annotation's organisms start the COCONUT form (the curator can change them), labelled as
 * the model's suggestion unless they come from the curator's corrections; COCONUT has no
 * kingdom field, so the kingdom is not carried over.
 */
export function coconutStart(annotation: AnnotationOut | undefined): CoconutStart {
  const organisms = (annotation?.coconut?.organisms ?? []).map((o) => ({
    name: o.name,
    parts: o.parts,
    location: o.location,
    ecosystems: o.ecosystems,
  }));
  const suggested = organisms.length > 0 && annotation?.curated === null;
  return { organisms, note: suggested ? "Organisms: model suggestion" : undefined };
}
