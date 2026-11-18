// The state of one paper workspace: the paper, its segments and steps, what failed, the
// live stream, and the view and focused segment (both in the URL, so reload and Back work).
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { refreshPaper, usePaper, useSteps } from "../api/queries";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { useLiveEvents } from "../api/useLiveEvents";
import { checkFailure, pageFailures, type PageFailure } from "./pageFailures";

export type WorkspaceView = "review" | "paper";

const NO_STEPS: StepOut[] = [];

export type Workspace = {
  /** Undefined only before the first answer (Workspace mounts this once the paper is in). */
  paper: PaperDetail | undefined;
  /** In (page, idx) order: structure n is segments[n - 1]. */
  segments: SegmentOut[];
  steps: StepOut[];
  failedPages: PageFailure[];
  /** Why the PDF check failed, as UI text; null when it did not. */
  checkFailure: string | null;
  /** The focused segment id (`?s=`). */
  selection: string | null;
  /** Replaces the URL entry by default (moving between cards makes no history); `push` adds one. */
  setSelection: (segmentId: string | null, opts?: { push?: boolean }) => void;
  view: WorkspaceView;
  /** Adds a history entry, so Back returns to the other view. */
  setView: (view: WorkspaceView) => void;
  live: ReturnType<typeof useLiveEvents>;
};

/** Mount only for a paper that exists: a 404 must unmount it, and its live stream with it. */
export function useWorkspace(id: string): Workspace {
  const client = useQueryClient();
  const paper = usePaper(id).data;
  const steps = useSteps(id).data?.steps ?? NO_STEPS;
  const live = useLiveEvents("paper", id, () => refreshPaper(client, id));
  const [params, setParams] = useSearchParams();

  const segments = useMemo(
    () => [...(paper?.segments ?? [])].sort((a, b) => a.page - b.page || a.idx - b.idx),
    [paper?.segments],
  );
  const failedPages = useMemo(() => pageFailures(steps), [steps]);
  const failure = useMemo(() => checkFailure(steps), [steps]);

  const view: WorkspaceView = params.get("view") === "paper" ? "paper" : "review";
  const selection = params.get("s");

  const setView = useCallback(
    (next: WorkspaceView) => {
      if (next === view) return; // no second history entry for the same view
      setParams((prev) => {
        const q = new URLSearchParams(prev);
        if (next === "paper") q.set("view", "paper");
        else q.delete("view");
        return q;
      });
    },
    [setParams, view],
  );

  const setSelection = useCallback(
    (segmentId: string | null, opts: { push?: boolean } = {}) =>
      setParams(
        (prev) => {
          const q = new URLSearchParams(prev);
          if (segmentId) q.set("s", segmentId);
          else q.delete("s");
          return q;
        },
        { replace: !opts.push },
      ),
    [setParams],
  );

  return {
    paper,
    segments,
    steps,
    failedPages,
    checkFailure: failure,
    selection,
    setSelection,
    view,
    setView,
    live,
  };
}
