import type { CurationIn, CurationOut, CurationStatus } from "./types";

export type CurationChange = {
  status?: CurationStatus;
  note?: string | null;
  /** Sets smiles and molfile together (an edit replaces the whole structure). */
  structure?: { smiles: string | null; molfile: string | null };
};

/**
 * The full body for PUT /segments/{id}/curation, which replaces the whole record ("omitted
 * fields are cleared"). Every key not in `change` is copied from `current`, so an accept
 * keeps an edited structure and an edit keeps the note. No caller builds a body by hand.
 */
export function curationBody(current: CurationOut | null, change: CurationChange): CurationIn {
  const base: CurationIn = {
    status: current?.status ?? "unchecked",
    smiles: current?.smiles ?? null,
    molfile: current?.molfile ?? null,
    note: current?.note ?? null,
  };
  return {
    status: change.status ?? base.status,
    smiles: change.structure ? change.structure.smiles : base.smiles,
    molfile: change.structure ? change.structure.molfile : base.molfile,
    note: change.note !== undefined ? change.note : base.note,
  };
}
