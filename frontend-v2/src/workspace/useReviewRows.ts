import { useMemo } from "react";
import { firstRunNote } from "../api/engines";
import { reasonText } from "../api/reasons";
import { isStepActive } from "../api/status";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { shownStructure, stateOf, type CardState } from "./cardState";
import { alsoOnText, listedSegments, repeatPages } from "./mainFigure";
import { newestFirst } from "./pageFailures";

/** One structure of the paper as the review views show it. */
export type ReviewRow = {
  segmentId: string;
  /** 1-based, in (page, idx) order: the `[nn]` tag. */
  n: number;
  state: CardState;
  /** For a failed structure: the reason (reasonText) and the engine that failed. */
  reason: string | null;
  failedEngine: string | null;
  /** For a structure being read: firstRunNote of the engine reading it. */
  readingNote: string | null;
  /** R-group labels of the structure shown ([] for none): the R-groups filter, the tags. */
  rgroups: string[];
  /** A main-figure structure with repeats on other pages: "Also on page N"; else null. */
  alsoOn: string | null;
};

const NO_STEPS: StepOut[] = [];

/**
 * The rows of the review grid and focus mode: one pass over the steps for the whole paper,
 * not one per card. `segments` in the workspace's order (useWorkspace sorts them). A repeat of
 * a main-figure structure has no row of its own: its main card says "Also on page N".
 */
export function useReviewRows(
  paper: PaperDetail,
  segments: SegmentOut[],
  steps: StepOut[],
): ReviewRow[] {
  // Each segment's ocsr steps, newest first: grouped and sorted once per steps change.
  const stepsBySegment = useMemo(() => {
    const map = new Map<string, StepOut[]>();
    for (const s of steps) {
      if (s.kind !== "ocsr" || s.segment_id === null) continue;
      const list = map.get(s.segment_id);
      if (list) list.push(s);
      else map.set(s.segment_id, [s]);
    }
    for (const [id, list] of map) map.set(id, newestFirst(list));
    return map;
  }, [steps]);

  return useMemo<ReviewRow[]>(() => {
    const repeats = repeatPages(segments);
    return listedSegments(segments).map((segment, i) => {
      const own = stepsBySegment.get(segment.id) ?? NO_STEPS;
      const state = stateOf(segment, own, paper);
      const newest = state === "failed" ? own[0] : undefined;
      return {
        segmentId: segment.id,
        n: i + 1,
        state,
        reason: newest ? reasonText(newest.error_class) : null,
        failedEngine: newest?.engine ?? null,
        readingNote:
          state === "reading" ? firstRunNote(own.find((s) => isStepActive(s.status))?.engine) : null,
        rgroups: shownStructure(segment, paper.engine).rgroups,
        alsoOn: alsoOnText(repeats.get(segment.id)),
      };
    });
  }, [segments, stepsBySegment, paper]);
}
