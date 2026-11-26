// Pick mode, a page open (owner, 2026-11-26): the structures picked on that page stand next to
// it, not below the page where nobody sees them; a scaffold's built structures sit under it in
// one tinted box ("Built from [nn]").
import { useMemo } from "react";
import BuiltFamily from "./BuiltFamily";
import StructureCard from "./StructureCard";
import { useCardActions } from "./useCardActions";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";

export default function PickedColumn({
  ws,
  rows,
  page0,
}: {
  ws: Workspace;
  rows: ReviewRow[];
  page0: number;
}) {
  const paper = ws.paper!;
  const { decide, run } = useCardActions(paper.id, ws.live.reconnect);
  const byId = useMemo(() => new Map(ws.segments.map((s) => [s.id, s])), [ws.segments]);
  const mains = rows.filter((r) => !r.builtFrom && byId.get(r.segmentId)?.page === page0);

  const card = (r: ReviewRow) => (
    <StructureCard
      key={r.segmentId}
      compact
      segment={byId.get(r.segmentId)!}
      n={r.n}
      state={r.state}
      paperEngine={paper.engine}
      reason={r.reason}
      failedEngine={r.failedEngine}
      readingNote={r.readingNote}
      alsoOn={r.alsoOn}
      builtFrom={r.builtFrom}
      current={ws.selection === r.segmentId}
      onOpen={ws.setSelection}
      onDecide={decide}
      onRun={run}
      onCompare={ws.openCompare}
      onEdit={ws.openEditor}
      paperName={paper.display_name}
    />
  );

  return (
    <section className="pick-side" aria-label={`Picked on page ${page0 + 1}`}>
      {mains.length === 0 ? (
        <p className="pick-side__hint">Click a box to read its structure.</p>
      ) : (
        mains.map((r) => {
          const built = rows.filter((b) => b.builtFrom?.segmentId === r.segmentId);
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
