// Pick mode, a page open (owner, 2026-11-26): the structures picked on that page stand next to
// it, not below the page where nobody sees them; a scaffold's built structures sit under it in
// one tinted box ("Built from [nn]").
import { useCallback, useMemo } from "react";
import type { CurationStatus } from "../api/types";
import BuiltFamily from "./BuiltFamily";
import { rowCardProps } from "./cardProps";
import StructureCard from "./StructureCard";
import { useCardActions } from "./useCardActions";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";

export default function PickedColumn({
  ws,
  rows,
  page0,
  onAccept,
}: {
  ws: Workspace;
  rows: ReviewRow[];
  page0: number;
  /** Accept on a card here (the Paper view's rule): the COCONUT form opens for it. */
  onAccept?: (segmentId: string) => void;
}) {
  const paper = ws.paper!;
  const { decide, run } = useCardActions(paper.id, ws.live.reconnect);
  const onDecide = useCallback(
    (segmentId: string, status: CurationStatus) => {
      decide(segmentId, status);
      if (status === "accepted") onAccept?.(segmentId);
    },
    [decide, onAccept],
  );
  const byId = useMemo(() => new Map(ws.segments.map((s) => [s.id, s])), [ws.segments]);
  const mains = rows.filter((r) => !r.builtFrom && byId.get(r.segmentId)?.page === page0);
  // the built rows of each scaffold, found once (not once per card)
  const builtOf = useMemo(() => {
    const m = new Map<string, ReviewRow[]>();
    for (const r of rows) {
      if (!r.builtFrom) continue;
      const list = m.get(r.builtFrom.segmentId);
      if (list) list.push(r);
      else m.set(r.builtFrom.segmentId, [r]);
    }
    return m;
  }, [rows]);

  const card = (r: ReviewRow) => (
    <StructureCard
      {...rowCardProps(r, byId.get(r.segmentId)!, paper)}
      key={r.segmentId}
      compact
      current={ws.selection === r.segmentId}
      onOpen={ws.setSelection}
      onDecide={onDecide}
      onRun={run}
      onCompare={ws.openCompare}
      onEdit={ws.openEditor}
    />
  );

  return (
    <section className="pick-side" aria-label={`Picked on page ${page0 + 1}`}>
      {mains.length === 0 ? (
        <p className="pick-side__hint">Click a box to read its structure.</p>
      ) : (
        mains.map((r) => {
          const built = builtOf.get(r.segmentId) ?? [];
          return (
            <div key={r.segmentId} className="pick-side__item">
              {card(r)}
              {built.length > 0 && (
                <BuiltFamily n={r.n} count={built.length}>
                  {built.map(card)}
                </BuiltFamily>
              )}
            </div>
          );
        })
      )}
    </section>
  );
}
