// Accepted structures that are never sent to COCONUT, and why (owner decision: a structure that
// still has R-group placeholders stands for several compounds, not one). Pure, pinned by tests.
import { structureTag } from "../ui/tag";
import { UNLABELLED } from "../workspace/rgroups";
import type { SubmitStructure } from "./types";

/** An accepted structure left out of the send, with its R-group labels. */
export type HeldStructure = { segmentId: string; n: number; rgroups: string[] };

/** "[03] has R-groups (R1, R2): build the compounds or edit the structure first" */
export function heldReason(h: HeldStructure): string {
  return `${structureTag(h.n)} has R-groups (${h.rgroups.join(", ")}): build the compounds or edit the structure first`;
}

/** Why nothing can be sent when every accepted structure is held (beside the disabled button). */
export function heldOnlyReason(held: HeldStructure[]): string {
  if (held.length === 1) return heldReason(held[0]!);
  return `${held.length} accepted structures have R-groups: build the compounds or edit the structures first`;
}

/** The SMILES has a dummy atom (`*`, `[1*]`), an R-group placeholder (CXSMILES tail ignored). */
export const hasDummyAtom = (smiles: string): boolean =>
  (smiles.trim().split(/\s/, 1)[0] ?? "").includes("*");

/**
 * The form's last guard: of the structures handed to it, those whose SMILES has a dummy atom
 * join `held` (labelled "*" when the caller had not held them), the rest may be sent.
 */
export function guardSend(
  structures: SubmitStructure[],
  held: HeldStructure[],
): { send: SubmitStructure[]; held: HeldStructure[] } {
  const send: SubmitStructure[] = [];
  const out = [...held];
  for (const s of structures) {
    if (hasDummyAtom(s.smiles)) out.push({ segmentId: s.segmentId, n: s.n, rgroups: [UNLABELLED] });
    else send.push(s);
  }
  out.sort((a, b) => a.n - b.n);
  return { send, held: out };
}
