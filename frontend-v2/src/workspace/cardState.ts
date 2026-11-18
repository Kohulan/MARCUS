// What a structure card shows: its state (spec §7 state table), the structure the server
// draws for it, and the grid's filters. Pure functions: the grid computes them once per
// paper or steps change, for up to hundreds of segments.
import { isPaperBusy, isStepActive } from "../api/status";
import type { PaperDetail, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { engineName } from "../api/engines";
import { STATE_WORD, type CardState } from "../ui/StateBadge";
import { newestFirst } from "./pageFailures";

export { STATE_WORD, type CardState };

/** The segment's `ocsr` steps, newest first. `steps` may hold the whole paper's steps. */
export function ocsrSteps(segment: SegmentOut, steps: StepOut[]): StepOut[] {
  return newestFirst(steps.filter((s) => s.kind === "ocsr" && s.segment_id === segment.id));
}

/**
 * The card state. A curation `accepted`/`rejected` wins. Else, with a valid prediction it is
 * `to-check`. With none: `reading` while an `ocsr` step of the segment is pending, queued or
 * running; `failed` when its newest `ocsr` step failed; `not-read` when it has no `ocsr`
 * step (a paper uploaded with `ocsr=off`; on an `auto` paper still being worked on, the step
 * is about to come, so that is `reading`); else `to-check`.
 */
export function cardState(segment: SegmentOut, steps: StepOut[], paper: PaperDetail): CardState {
  return stateOf(segment, ocsrSteps(segment, steps), paper);
}

/** cardState with the segment's `ocsr` steps already picked, newest first (ocsrSteps). */
export function stateOf(segment: SegmentOut, ocsr: StepOut[], paper: PaperDetail): CardState {
  const status = segment.curation?.status;
  if (status === "accepted" || status === "rejected") return status;
  if (segment.predictions.some((p) => p.valid)) return "to-check";
  if (ocsr.some((s) => isStepActive(s.status))) return "reading";
  const newest = ocsr[0];
  if (newest === undefined) {
    return paper.ocsr_mode !== "off" && isPaperBusy(paper.status) ? "reading" : "not-read";
  }
  return newest.status === "failed" ? "failed" : "to-check";
}

/**
 * The prediction the card shows, as the server picks the drawing (api/depiction.py
 * shown_structure; predictions come newest first): the newest valid one of the paper's
 * engine, else of any engine; with no valid one, the newest (shown as invalid).
 */
export function shownPrediction(segment: SegmentOut, paperEngine: string): PredictionOut | null {
  const valid = segment.predictions.filter((p) => p.valid);
  return (
    valid.find((p) => p.engine === paperEngine) ?? valid[0] ?? segment.predictions[0] ?? null
  );
}

/** The structure a segment shows (card, focus mode, editor start, COCONUT list). */
export type ShownStructure = {
  /** shownPrediction: what the server draws when nothing is curated. */
  prediction: PredictionOut | null;
  /** A curated SMILES or molfile: the curated structure is shown, never the prediction. */
  edited: boolean;
  /** Null without one, and for a curated molfile without SMILES (never the prediction's). */
  smiles: string | null;
  /** The curated molfile when edited, else the prediction's. */
  molfile: string | null;
};

export function shownStructure(segment: SegmentOut, paperEngine: string): ShownStructure {
  const c = segment.curation;
  const prediction = shownPrediction(segment, paperEngine);
  if (c?.smiles || c?.molfile) {
    return { prediction, edited: true, smiles: c.smiles || null, molfile: c.molfile ?? null };
  }
  return {
    prediction,
    edited: false,
    smiles: prediction?.smiles || null,
    molfile: prediction?.molfile ?? null,
  };
}

/** "Edited", or the shown prediction's "<engine> · Valid|Invalid"; null with neither. */
export function metaText({ edited, prediction }: ShownStructure): string | null {
  if (edited) return "Edited";
  if (!prediction) return null;
  return `${engineName(prediction.engine)} · ${prediction.valid ? "Valid" : "Invalid"}`;
}

/** A reason as a sentence: "it took too long" → "It took too long." */
export function sentence(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

/** True when the server has something to draw (a curated structure or a valid prediction). */
export function hasDrawing(segment: SegmentOut): boolean {
  return Boolean(
    segment.curation?.smiles || segment.curation?.molfile || segment.predictions.some((p) => p.valid),
  );
}

/** Two engines that differ: the newest valid predictions of two engines give different SMILES. */
export function enginesDiffer(segment: SegmentOut): boolean {
  const byEngine = new Map<string, string>();
  for (const p of segment.predictions) {
    if (p.valid && !byEngine.has(p.engine)) byEngine.set(p.engine, p.smiles);
  }
  return new Set(byEngine.values()).size > 1;
}

export type GridFilter = "all" | "to-check" | "accepted" | "rejected" | "failed";

export const FILTERS: { filter: GridFilter; label: string }[] = [
  { filter: "all", label: "All" },
  ...(["to-check", "accepted", "rejected", "failed"] as const).map((filter) => ({
    filter,
    label: STATE_WORD[filter],
  })),
];

/** The filter a state counts under ("Reading…" and "Not read yet" count as To check). */
export function filterOf(state: CardState): Exclude<GridFilter, "all"> {
  if (state === "reading" || state === "not-read") return "to-check";
  return state;
}

/**
 * How many structures each filter holds: the grid's filter strip and the workspace header
 * both count with this, so "N to check" means the same in both (a Failed one is not To check).
 */
export function filterCounts(rows: readonly { state: CardState }[]): Record<GridFilter, number> {
  const c: Record<GridFilter, number> = {
    all: rows.length,
    "to-check": 0,
    accepted: 0,
    rejected: 0,
    failed: 0,
  };
  for (const r of rows) c[filterOf(r.state)] += 1;
  return c;
}

/** Id of the one hidden "Enter: open" that every structure card points at (Workspace). */
export const CARD_OPEN_HINT = "card-open-hint";
