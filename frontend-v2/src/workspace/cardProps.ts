// The props every structure card takes from its review row (grid, Paper view list, pick page
// column): one place, so a new row field reaches all three views.
import type { PaperDetail, SegmentOut } from "../api/types";
import type { ReviewRow } from "./useReviewRows";

export function rowCardProps(r: ReviewRow, segment: SegmentOut, paper: PaperDetail) {
  return {
    segment,
    n: r.n,
    state: r.state,
    paperEngine: paper.engine,
    reason: r.reason,
    failedEngine: r.failedEngine,
    readingNote: r.readingNote,
    alsoOn: r.alsoOn,
    builtFrom: r.builtFrom,
    paperName: paper.display_name,
  };
}
