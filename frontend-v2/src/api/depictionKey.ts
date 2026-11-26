import type { PredictionOut, SegmentOut } from "./types";

/**
 * A prediction the server can draw: its own word (PredictionOut.drawable, backend
 * marcus.core.drawable: valid, or an R-group scaffold such as DECIMER's [R1]); a reply from
 * before the field, valid.
 */
export const drawable = (p: PredictionOut): boolean => p.drawable ?? p.valid;

/**
 * Cache key of a segment's depiction URL (`?v=`): FNV-1a 32-bit (hex) of the inputs of the
 * server's choice of structure (F0-4): the curated SMILES and molfile and the ids of the
 * drawable predictions in API order. Status, note and bbox do not change the drawing.
 */
export function depictionKey(segment: SegmentOut): string {
  const validPredictionIds = segment.predictions.filter(drawable).map((p) => p.id);
  const input = JSON.stringify([
    segment.curation?.smiles ?? null,
    segment.curation?.molfile ?? null,
    validPredictionIds,
  ]);
  return fnv1a32(input);
}

const encoder = new TextEncoder();

function fnv1a32(text: string): string {
  let hash = 0x811c9dc5;
  for (const byte of encoder.encode(text)) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}
