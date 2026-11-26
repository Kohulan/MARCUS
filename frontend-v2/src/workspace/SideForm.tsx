// The COCONUT side form of one structure (owner decisions 2026-11-25 and 2026-11-26): opened by
// Accept in the Paper view and on the pick page; its scaffold row when it was built (Markush
// Phase 3), the paper's organisms from the annotation.
import CoconutSidePanel from "../coconut/CoconutSidePanel";
import { shownPrediction } from "./cardState";
import { coconutStart } from "./coconutList";
import { useAnnotation } from "./useAnnotation";
import type { ReviewRow } from "./useReviewRows";
import { useRgroupReading } from "./useRgroupRows";
import type { Workspace } from "./useWorkspace";

/** The side form of one structure; its scaffold row when it was built (Markush Phase 3). */
export default function SideForm({
  ws,
  rows,
  segmentId,
  onClose,
}: {
  ws: Workspace;
  rows: ReviewRow[];
  segmentId: string;
  onClose: () => void;
}) {
  const paper = ws.paper!;
  const annotation = useAnnotation(paper.id).data;
  const segment = ws.segments.find((s) => s.id === segmentId);
  const row = rows.find((r) => r.segmentId === segmentId);
  const built = row?.builtFrom ?? null;
  const scaffold = built ? ws.segments.find((s) => s.id === built.segmentId) : undefined;
  const reading = useRgroupReading(scaffold ? shownPrediction(scaffold, paper.engine)?.id : undefined);
  if (!segment || !row) return null;
  const rgroupRow =
    reading.extraction?.rows?.find((r) => r.compound === segment.compound_id) ?? null;
  return (
    <CoconutSidePanel
      paper={paper}
      segment={segment}
      n={row.n}
      start={coconutStart(annotation)}
      built={built}
      row={rgroupRow}
      onClose={onClose}
    />
  );
}
