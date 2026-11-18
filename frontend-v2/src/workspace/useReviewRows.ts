import { useMemo } from "react";
import { reasonText } from "../api/reasons";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { cardState, ocsrSteps, type CardState } from "./cardState";

/** One structure of the paper as the review views show it. */
export type ReviewRow = {
  segmentId: string;
  /** 1-based, in (page, idx) order: the `[nn]` tag. */
  n: number;
  state: CardState;
  /** For a failed structure: the reason (reasonText) and the engine that failed. */
  reason: string | null;
  failedEngine: string | null;
};

const NO_STEPS: StepOut[] = [];

/**
 * The rows of the review grid and focus mode: one pass over the steps for the whole paper,
 * not one per card. `segments` in (page, idx) order (useWorkspace sorts them).
 */
export function useReviewRows(
  paper: PaperDetail,
  segments: SegmentOut[],
  steps: StepOut[],
): ReviewRow[] {
  const stepsBySegment = useMemo(() => {
    const map = new Map<string, StepOut[]>();
    for (const s of steps) {
      if (s.kind !== "ocsr" || s.segment_id === null) continue;
      const list = map.get(s.segment_id);
      if (list) list.push(s);
      else map.set(s.segment_id, [s]);
    }
    return map;
  }, [steps]);

  return useMemo<ReviewRow[]>(
    () =>
      segments.map((segment, i) => {
        const own = stepsBySegment.get(segment.id) ?? NO_STEPS;
        const state = cardState(segment, own, paper);
        const newest = state === "failed" ? ocsrSteps(segment, own)[0] : undefined;
        return {
          segmentId: segment.id,
          n: i + 1,
          state,
          reason: newest ? reasonText(newest.error_class) : null,
          failedEngine: newest?.engine ?? null,
        };
      }),
    [segments, stepsBySegment, paper],
  );
}
