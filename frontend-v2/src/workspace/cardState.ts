// What a structure card shows: its state (spec §7 state table), the structure the server
// draws for it, and the grid's filters. Pure functions: the grid computes them once per
// paper or steps change, for up to hundreds of segments.
import { isPaperBusy, isStepActive } from "../api/status";
import type { PaperDetail, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { engineName } from "../api/engines";
import { STATE_WORD, type CardState } from "../ui/StateBadge";
import { newestFirst } from "./pageFailures";
import { isPlaceholder, labelList, resultWord, rgroupsOf } from "./rgroups";

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
 * is about to come, so that is `reading`, unless the paper is busy only with its annotation);
 * else `to-check`.
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
 * The prediction the card shows: the one the server picks (`default_prediction_id`, backend
 * core/agreement.py pick_prediction: the engines' majority, else the newest valid one of the
 * paper's engine, else of any engine). Without it (an older server, an optimistic update): the
 * newest valid one of the paper's engine, else of any engine; with no valid one, the newest
 * (shown as invalid). Predictions come newest first.
 */
export function shownPrediction(segment: SegmentOut, paperEngine: string): PredictionOut | null {
  const picked = segment.predictions.find((p) => p.id === segment.default_prediction_id);
  if (picked) return picked;
  const valid = segment.predictions.filter((p) => p.valid);
  return (
    valid.find((p) => p.engine === paperEngine) ?? valid[0] ?? segment.predictions[0] ?? null
  );
}

/** The paper's read steps: background OCSR steps (other engines filling in) left out. */
export function readSteps(steps: StepOut[]): StepOut[] {
  return steps.some((s) => s.background) ? steps.filter((s) => !s.background) : steps;
}

/** The agreement badge: "3 agree", "2 agree", "Differ"; null while engines read, or without. */
export function agreeText(segment: SegmentOut): string | null {
  const n = segment.agree;
  if (n === undefined || n === null) return null;
  return n >= 2 ? `${n} agree` : "Differ";
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
  /**
   * R-group labels of the structure shown ([] for none): the curation's when edited, else
   * the prediction's. With labels it is a scaffold, not one compound.
   */
  rgroups: string[];
  /** It has R-group placeholder atoms, whatever labels are shown (never sent to COCONUT). */
  placeholder: boolean;
  /**
   * The two engines whose shared structure is shown (the prediction is theirs, "2 agree");
   * [] otherwise. The card names them.
   */
  agreeing: string[];
};

export function shownStructure(segment: SegmentOut, paperEngine: string): ShownStructure {
  const c = segment.curation;
  const prediction = shownPrediction(segment, paperEngine);
  if (c?.smiles || c?.molfile) {
    return {
      prediction,
      edited: true,
      smiles: c.smiles || null,
      molfile: c.molfile ?? null,
      rgroups: rgroupsOf(c),
      placeholder: isPlaceholder(c),
      agreeing: [],
    };
  }
  const engines = segment.agree_engines ?? [];
  const agreeing =
    prediction !== null && engines.length === 2 && engines.includes(prediction.engine)
      ? engines
      : [];
  return {
    prediction,
    edited: false,
    smiles: prediction?.smiles || null,
    molfile: prediction?.molfile ?? null,
    rgroups: rgroupsOf(prediction),
    placeholder: isPlaceholder(prediction),
    agreeing,
  };
}

/**
 * The prediction whose R-group rows a segment shows: the shown prediction (cardState
 * shownPrediction) when it is a scaffold, else none. An edited structure keeps the rows of the
 * prediction under it while it still has R-groups itself (as the export does).
 */
export function scaffoldPrediction(
  shown: { prediction: PredictionOut | null; rgroups: readonly string[] },
): PredictionOut | null {
  const p = shown.prediction;
  return p !== null && shown.rgroups.length > 0 && rgroupsOf(p).length > 0 ? p : null;
}

/** The segment shows a scaffold that can have R-group rows. */
export const hasScaffold = (segment: SegmentOut, paperEngine: string): boolean =>
  scaffoldPrediction(shownStructure(segment, paperEngine)) !== null;

/**
 * "Edited", or the shown prediction's "<engine> · Valid|Invalid"; null with neither. The
 * structure two engines agree on names both ("MolNexTR + MolScribe · Valid"). A scaffold says
 * so instead, with its labels ("DECIMER · R-group scaffold (R1, R2)"), never a bare "Invalid"
 * (DECIMER's R tokens) or "Valid" (a dummy atom).
 */
export function metaText({ edited, prediction, rgroups, agreeing }: ShownStructure): string | null {
  if (edited) {
    return rgroups.length > 0 ? `Edited · R-group scaffold (${labelList(rgroups)})` : "Edited";
  }
  if (!prediction) return null;
  const engines = agreeing.length > 0 ? agreeing : [prediction.engine];
  return `${engines.map(engineName).join(" + ")} · ${resultWord(prediction)}`;
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

/** The state filters, and "rgroups": structures with R-groups, whatever their state. */
export type GridFilter = "all" | "to-check" | "accepted" | "rejected" | "failed" | "rgroups";

export const FILTERS: { filter: GridFilter; label: string }[] = [
  { filter: "all", label: "All" },
  ...(["to-check", "accepted", "rejected", "failed"] as const).map((filter) => ({
    filter,
    label: STATE_WORD[filter],
  })),
  { filter: "rgroups", label: "R-groups" },
];

/** The state filter a state counts under ("Reading…" and "Not read yet" count as To check). */
export function filterOf(state: CardState): Exclude<GridFilter, "all" | "rgroups"> {
  if (state === "reading" || state === "not-read") return "to-check";
  return state;
}

/**
 * The filter strip shows `f`: the state filters always; "R-groups" only on a paper that has
 * such structures, or while it is pressed (a pressed filter never vanishes under the pointer).
 */
export function shownFilter(
  f: GridFilter,
  pressed: GridFilter,
  counts: Record<GridFilter, number>,
): boolean {
  return f !== "rgroups" || counts.rgroups > 0 || pressed === "rgroups";
}

type FilterRow = { state: CardState; rgroups?: readonly string[] };

/** The row is shown under `filter`. */
export function inFilter(row: FilterRow, filter: GridFilter): boolean {
  if (filter === "all") return true;
  if (filter === "rgroups") return (row.rgroups?.length ?? 0) > 0;
  return filterOf(row.state) === filter;
}

/**
 * How many structures each filter holds: the grid's filter strip and the workspace header
 * both count with this, so "N to check" means the same in both (a Failed one is not To check).
 * A structure with R-groups also counts under its state.
 */
export function filterCounts(rows: readonly FilterRow[]): Record<GridFilter, number> {
  const c: Record<GridFilter, number> = {
    all: rows.length,
    "to-check": 0,
    accepted: 0,
    rejected: 0,
    failed: 0,
    rgroups: 0,
  };
  for (const r of rows) {
    c[filterOf(r.state)] += 1;
    if (inFilter(r, "rgroups")) c.rgroups += 1;
  }
  return c;
}

/** Id of the one hidden "Enter: open" that every structure card points at (Workspace). */
export const CARD_OPEN_HINT = "card-open-hint";

/** The structure card of `segmentId` under `root` (compared as data, never as a selector). */
export function segmentCard(
  root: ParentNode | null | undefined,
  segmentId: string,
): HTMLElement | undefined {
  return [...(root?.querySelectorAll<HTMLElement>("[data-segment-id]") ?? [])].find(
    (el) => el.dataset.segmentId === segmentId,
  );
}
