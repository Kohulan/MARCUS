// The state of one paper workspace: the paper, its segments and steps, what failed, the
// live stream, and the view and focused segment (both in the URL, so reload and Back work).
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { refreshPaper, usePaper, useSteps } from "../api/queries";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { useLiveEvents } from "../api/useLiveEvents";
import { checkFailure, pageFailures, type PageFailure } from "./pageFailures";

export type WorkspaceView = "review" | "paper";

const FOCUS_PUSHED = { focusPushed: true } as const;
const isFocusPushed = (state: unknown) =>
  typeof state === "object" && state !== null && (state as { focusPushed?: unknown }).focusPushed === true;

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
  /** Focus mode is open on the selection (`?focus=1`, review view). */
  focus: boolean;
  /** Opens focus mode on a segment with a new history entry (Back closes it). */
  openFocus: (segmentId: string) => void;
  /** Closes focus mode: Back to the grid's entry when focus mode pushed one, else drop the flag. */
  closeFocus: () => void;
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
  const navigate = useNavigate();
  // The entry's state says whether openFocus pushed it; replaced entries keep it.
  const location = useLocation();
  const entryState = useRef<unknown>(location.state);
  entryState.current = location.state;

  const segments = useMemo(
    () => [...(paper?.segments ?? [])].sort((a, b) => a.page - b.page || a.idx - b.idx),
    [paper?.segments],
  );
  const failedPages = useMemo(() => pageFailures(steps), [steps]);
  const failure = useMemo(() => checkFailure(steps), [steps]);

  const view: WorkspaceView = params.get("view") === "paper" ? "paper" : "review";
  const selection = params.get("s");
  const focus = view === "review" && selection !== null && params.get("focus") === "1";

  const setView = useCallback(
    (next: WorkspaceView) => {
      if (next === view) return; // no second history entry for the same view
      setParams((prev) => {
        const q = new URLSearchParams(prev);
        if (next === "paper") q.set("view", "paper");
        else q.delete("view");
        q.delete("focus"); // a view switch leaves focus mode
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
        // A replaced entry keeps its state (focus mode stays "pushed" while moving in it).
        opts.push ? {} : { replace: true, state: entryState.current },
      ),
    [setParams],
  );

  const openFocus = useCallback(
    (segmentId: string) =>
      setParams(
        (prev) => {
          const q = new URLSearchParams(prev);
          q.set("s", segmentId);
          q.set("focus", "1");
          return q;
        },
        { state: FOCUS_PUSHED },
      ),
    [setParams],
  );

  // Set by a Back that has not landed yet: a second Esc or "Grid" click before popstate
  // must not go Back again (it would leave the workspace). Any new entry clears it.
  const goingBack = useRef(false);
  useEffect(() => {
    goingBack.current = false;
  }, [location.key]);

  const closeFocus = useCallback(() => {
    if (goingBack.current) return;
    if (isFocusPushed(entryState.current)) {
      goingBack.current = true;
      void navigate(-1);
      return;
    }
    setParams(
      (prev) => {
        const q = new URLSearchParams(prev);
        q.delete("focus");
        return q;
      },
      { replace: true },
    );
  }, [navigate, setParams]);

  return {
    paper,
    segments,
    steps,
    failedPages,
    checkFailure: failure,
    selection,
    setSelection,
    focus,
    openFocus,
    closeFocus,
    view,
    setView,
    live,
  };
}
