import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, errorText } from "../api/client";
import { keys, refreshPaper, useQueue, useSteps } from "../api/queries";
import { reasonText } from "../api/reasons";
import { isPaperBusy } from "../api/status";
import type { PaperDetail, StepOut } from "../api/types";
import type { useLiveEvents } from "../api/useLiveEvents";
import { ItemState } from "../tool/PapersList";
import { GlassButton } from "../ui/GlassButton";
import { useToast } from "../ui/Toasts";
import { checkFailure as checkFailureOf, pageFailures, progress } from "./pageFailures";
import "./workspace.css";

/** "About 3 min in the queue" (whole minutes, rounded up); under 60 s "Less than a minute". */
export function queueText(seconds: number): string {
  if (seconds < 60) return "Less than a minute";
  return `About ${Math.ceil(seconds / 60)} min in the queue`;
}

function progressText(steps: StepOut[], pages: number | null): string | null {
  const p = progress(steps, pages);
  const parts: string[] = [];
  if (p.pages !== null) parts.push(`Pages read ${p.pagesRead}/${p.pages}`);
  if (p.structures > 0) parts.push(`Structures read ${p.structuresRead}/${p.structures}`);
  return parts.length ? parts.join(" · ") : null;
}

type Props = {
  paper: PaperDetail;
  steps: StepOut[];
  live: ReturnType<typeof useLiveEvents>;
};

/**
 * The status bar both views share: the paper's state word, its place in the queue while it
 * waits, per-step progress (or the one line of a PDF that could not be read), the live note,
 * then one hatched line per failed page with its reason and a retry.
 */
export default function StatusBar({ paper, steps, live }: Props) {
  const client = useQueryClient();
  const toast = useToast();
  const waiting = isPaperBusy(paper.status);
  const queue = useQueue(waiting);
  const mine = waiting ? queue.data?.papers.find((p) => p.id === paper.id) : undefined;
  // Pages whose Retry is held: 0 while the request runs; after a 202, the time it was
  // accepted, until a steps refresh newer than that lands (the line then says "retrying…",
  // or offers Retry again). So a second press cannot meet "Page is still running".
  const [held, setHeld] = useState<ReadonlyMap<number, number>>(new Map());
  const stepsAt = useSteps(paper.id).dataUpdatedAt;
  // Once per steps change, not on every workspace render (each ← / → in focus mode is one).
  const failedPages = useMemo(() => pageFailures(steps), [steps]);
  const checkFailure = useMemo(() => checkFailureOf(steps), [steps]);
  const readout = useMemo(
    () => (checkFailure === null ? progressText(steps, paper.pages) : null),
    [checkFailure, steps, paper.pages],
  );

  useEffect(() => {
    setHeld((m) => {
      const keep = [...m].filter(([, at]) => at === 0 || at >= stepsAt);
      return keep.length === m.size ? m : new Map(keep);
    });
  }, [stepsAt]);

  const release = (page0: number) =>
    setHeld((m) => {
      const next = new Map(m);
      next.delete(page0);
      return next;
    });

  async function retry(page0: number) {
    setHeld((m) => new Map(m).set(page0, 0));
    try {
      await api.retryPage(paper.id, page0);
      setHeld((m) => new Map(m).set(page0, Date.now()));
      live.reconnect(); // a finished paper's stream has ended; the retry reopens it
      refreshPaper(client, paper.id);
    } catch (error) {
      release(page0);
      if (error instanceof ApiError && error.status === 404) {
        // the paper was deleted (or expired) meanwhile: reading it again shows the gone page
        void client.invalidateQueries({ queryKey: keys.paper(paper.id) });
        return;
      }
      // the 409 details ("Page has not failed", "Page is still running", "No retries left
      // for this page") are written for people
      toast(errorText(error), "error");
    }
  }

  return (
    <section className="ws-status" aria-label="Status">
      <div className="ws-status__line">
        <span className="ws-status__cell">
          <ItemState status={paper.status} notRead={paper.ocsr_mode === "off"} />
        </span>
        {mine && <span className="ws-status__cell ws-status__readout">{queueText(mine.estimate_s)}</span>}
        {checkFailure !== null && (
          <p className="ws-status__cell ws-status__problem hatch">
            {`This PDF could not be read: ${checkFailure}`}
          </p>
        )}
        {readout !== null && <span className="ws-status__cell ws-status__readout">{readout}</span>}
        {live.mode === "polling" && (
          <span className="ws-status__cell ws-status__live">
            Live updates paused, checking every 2 s
          </span>
        )}
      </div>
      {/* Always in the page, so a page that fails while the paper is open is announced. */}
      <div role="status" aria-live="polite" aria-atomic="false" aria-label="Failed pages">
        {failedPages.length > 0 && (
          <ul className="ws-status__failures">
            {failedPages.map((f) =>
              f.retrying ? (
                <li key={f.page0} className="ws-fail ws-fail--retrying">
                  <span className="state badge badge--dashed">Reading…</span>
                  <p className="ws-fail__text">{`Page ${f.page0 + 1}: retrying…`}</p>
                </li>
              ) : (
                <li key={f.page0} className="ws-fail hatch">
                  <span className="state tag tag--charcoal">Failed</span>
                  <p className="ws-fail__text">
                    {`Page ${f.page0 + 1} could not be read: ${reasonText(f.errorClass)}`}
                  </p>
                  <GlassButton
                    tint="clear"
                    size="sm"
                    label={`Retry page ${f.page0 + 1}`}
                    disabled={held.has(f.page0)}
                    onClick={() => void retry(f.page0)}
                  >
                    Retry page
                  </GlassButton>
                </li>
              ),
            )}
          </ul>
          )}
      </div>
    </section>
  );
}
