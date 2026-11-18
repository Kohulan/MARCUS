import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../api/client";
import { refreshPaper, useQueue } from "../api/queries";
import { reasonText } from "../api/reasons";
import type { PaperDetail, StepOut } from "../api/types";
import type { useLiveEvents } from "../api/useLiveEvents";
import { ItemState } from "../tool/PapersList";
import { GlassButton } from "../ui/GlassButton";
import { useToast } from "../ui/Toasts";
import { progress, type PageFailure } from "./pageFailures";
import "./workspace.css";

/** "About 3 min in the queue" (whole minutes, rounded up); under 60 s "Less than a minute …". */
export function queueText(seconds: number): string {
  if (seconds < 60) return "Less than a minute in the queue";
  return `About ${Math.ceil(seconds / 60)} min in the queue`;
}

function progressText(steps: StepOut[], pages: number | null): string | null {
  const p = progress(steps, pages);
  const parts: string[] = [];
  if (p.pages !== null) parts.push(`Pages read ${p.pagesRead}/${p.pages}`);
  if (p.structures > 0) parts.push(`Structures read ${p.structuresRead}/${p.structures}`);
  return parts.length ? parts.join(" · ") : null;
}

const WAITING = new Set(["checking", "processing"]);

type Props = {
  paper: PaperDetail;
  steps: StepOut[];
  failedPages: PageFailure[];
  checkFailure: string | null;
  live: ReturnType<typeof useLiveEvents>;
};

/**
 * The status bar both views share: the paper's state word, its place in the queue while it
 * waits, per-step progress (or the one line of a PDF that could not be read), the live note,
 * then one hatched line per failed page with its reason and a retry.
 */
export default function StatusBar({ paper, steps, failedPages, checkFailure, live }: Props) {
  const client = useQueryClient();
  const toast = useToast();
  const waiting = WAITING.has(paper.status);
  const queue = useQueue(waiting);
  const mine = waiting ? queue.data?.papers.find((p) => p.id === paper.id) : undefined;
  const [retrying, setRetrying] = useState<ReadonlySet<number>>(new Set());
  const readout = checkFailure === null ? progressText(steps, paper.pages) : null;

  async function retry(page0: number) {
    setRetrying((s) => new Set(s).add(page0));
    try {
      await api.retryPage(paper.id, page0);
      live.reconnect(); // a finished paper's stream has ended; the retry reopens it
      refreshPaper(client, paper.id);
    } catch (error) {
      // the 409 details ("already being read again", "retried too often") are written for people
      toast(error instanceof ApiError ? error.detail : "Something went wrong.", "error");
    } finally {
      setRetrying((s) => {
        const next = new Set(s);
        next.delete(page0);
        return next;
      });
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
      {failedPages.length > 0 && (
        <ul className="ws-status__failures" aria-label="Failed pages">
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
                  disabled={retrying.has(f.page0)}
                  onClick={() => void retry(f.page0)}
                >
                  Retry page
                </GlassButton>
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}
