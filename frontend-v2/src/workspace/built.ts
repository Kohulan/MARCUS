// Markush Phase 3: structures MARCUS built from a scaffold and its R-group rows. The words, and
// the small pure helpers the cards use.
import type { BuildFailure, SegmentOut } from "../api/types";
import { structureTag } from "../ui/tag";

export const BUILD = "Build structures";
export const COULD_NOT_BUILD = "Could not build";

/** One row that was not built: "3c: unknown substituent "Tig"". */
export const failureText = (f: BuildFailure): string => `${f.compound}: ${f.reason}`;

/** A structure MARCUS built from a scaffold's row (it has no drawing of its own). */
export const isBuilt = (s: SegmentOut): boolean => Boolean(s.built_from);

/** "Built from [03]": the link to the scaffold, by its tag. */
export const builtFromText = (n: number): string => `Built from ${structureTag(n)}`;

/**
 * Each built card right after its scaffold, in idx order (their order of building); a built
 * card whose scaffold is not in the list stays where it was; every other card keeps its place.
 */
export function placeBuilt(segments: SegmentOut[]): SegmentOut[] {
  const ids = new Set(segments.map((s) => s.id));
  const children = new Map<string, SegmentOut[]>();
  for (const s of segments) {
    if (s.built_from && ids.has(s.built_from)) {
      const list = children.get(s.built_from);
      if (list) list.push(s);
      else children.set(s.built_from, [s]);
    }
  }
  if (children.size === 0) return segments;
  const out: SegmentOut[] = [];
  for (const s of segments) {
    if (s.built_from && ids.has(s.built_from)) continue;
    out.push(s);
    const kids = children.get(s.id);
    if (kids) out.push(...[...kids].sort((a, b) => a.idx - b.idx));
  }
  return out;
}

type Familiar = { segmentId: string; builtFrom: { segmentId: string; n: number } | null };

/** One card on its own, or the built cards of one scaffold together. */
export type Family<T extends Familiar> =
  | { kind: "one"; row: T }
  | { kind: "built"; from: { segmentId: string; n: number }; rows: T[] };

/**
 * The list cut into families (owner, 2026-11-26): the built rows that follow each other from
 * the same scaffold (placeBuilt puts them right after it) form one family, shown in one box
 * under the scaffold; every other row stays on its own. Order is kept.
 */
export function families<T extends Familiar>(rows: T[]): Family<T>[] {
  const out: Family<T>[] = [];
  for (const row of rows) {
    const last = out.at(-1);
    if (!row.builtFrom) out.push({ kind: "one", row });
    else if (last?.kind === "built" && last.from.segmentId === row.builtFrom.segmentId) {
      last.rows.push(row);
    } else out.push({ kind: "built", from: row.builtFrom, rows: [row] });
  }
  return out;
}
