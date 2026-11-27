// Markush Phase 3: structures MARCUS built from a scaffold and its R-group rows. The words, and
// the small pure helpers the cards use.
import type { BuildFailure, SegmentOut } from "../api/types";
import { structureTag } from "../ui/tag";

export const BUILD = "Build structures";
export const COULD_NOT_BUILD = "Could not build";
/** Build left another engine's reading out: it differs outside the R-group points. */
export const READINGS_DIFFER = "The engines read the scaffold differently outside the R-groups: check it";

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

/** One card on its own, or a scaffold (`head`) with the built cards right after it. */
export type Family<T extends Familiar> =
  | { kind: "one"; row: T }
  | { kind: "built"; head: T; rows: T[] };

/**
 * The list cut into families (owner, 2026-11-26): a scaffold and the built rows that follow it
 * (placeBuilt puts them there) form one family, the built ones shown in one box under it. A
 * built row whose scaffold is not just before it (a filter hides the scaffold) stays single:
 * no box under an unrelated card. Order is kept.
 */
export function families<T extends Familiar>(rows: T[]): Family<T>[] {
  const out: Family<T>[] = [];
  for (const row of rows) {
    const last = out.at(-1);
    const from = row.builtFrom?.segmentId;
    if (from && last?.kind === "built" && last.head.segmentId === from) last.rows.push(row);
    else if (from && last?.kind === "one" && last.row.segmentId === from) {
      out[out.length - 1] = { kind: "built", head: last.row, rows: [row] };
    } else out.push({ kind: "one", row });
  }
  return out;
}
