// The state of one paper workspace: the paper, its segments and steps, the live stream, and the view and focused segment (both in the URL, so reload and Back work).
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { refreshPaper, snapshotIsCached, usePaper, useSteps } from "../api/queries";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { useLiveEvents } from "../api/useLiveEvents";
import { readSteps } from "./cardState";
import { mainFirst } from "./mainFigure";

export type WorkspaceView = "review" | "paper";

/**
 * The paper waits for the user ("ask": the choice; "pick": boxes to pick): an empty structure
 * list is no "No structures found".
 */
export const waitsForPicks = (mode: string) => mode === "ask" || mode === "pick";

const FOCUS_PUSHED = { focusPushed: true } as const;
const isFocusPushed = (state: unknown) =>
  typeof state === "object" && state !== null && (state as { focusPushed?: unknown }).focusPushed === true;

const NO_STEPS: StepOut[] = [];

/** Compare engines or the structure editor, open on one segment (rendered once, by the frame). */
export type WorkspaceDialog = { kind: "compare" | "edit"; segmentId: string };

export type Workspace = {
  /** Undefined only before the first answer (Workspace mounts this once the paper is in). */
  paper: PaperDetail | undefined;
  /**
   * In (page, idx) order, the main figure's page first (mainFirst). Repeats of main-figure
   * structures are in it too; the listed structures (structure n is the n-th) leave them out
   * (listedSegments).
   */
  segments: SegmentOut[];
  /**
   * Pick mode: the boxes the user has not picked (candidate). Drawn on their page in the pick
   * panel only: never in `segments`, so no card, marker, count or COCONUT send has them.
   */
  candidates: SegmentOut[];
  /** The paper's read steps: background OCSR steps left out (readSteps). */
  steps: StepOut[];
  /** Every step, background OCSR steps too (Compare shows those engines reading). */
  allSteps: StepOut[];
  /** The focused segment id (`?s=`; a repeat's main-figure structure for a repeat). */
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
  /** The open dialog; null once its segment is gone (deleted live in another tab). */
  dialog: WorkspaceDialog | null;
  openCompare: (segmentId: string) => void;
  openEditor: (segmentId: string) => void;
  closeDialog: () => void;
};

/** Mount only for a paper that exists: a 404 must unmount it, and its live stream with it. */
export function useWorkspace(id: string): Workspace {
  const client = useQueryClient();
  const paper = usePaper(id).data;
  const allSteps = useSteps(id).data?.steps ?? NO_STEPS;
  const steps = useMemo(() => readSteps(allSteps), [allSteps]);
  // The stream's first snapshot comes right after the paper and its steps were read: when
  // it says what they say, the refetch is skipped (a later one, a reconnect, never is).
  const firstSnapshot = useRef(true);
  const live = useLiveEvents("paper", id, (snapshot) => {
    const first = snapshot !== undefined && firstSnapshot.current;
    if (snapshot !== undefined) firstSnapshot.current = false;
    if (first && snapshotIsCached(client, id, snapshot)) return;
    refreshPaper(client, id);
  });
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  // The entry's state says whether openFocus pushed it; replaced entries keep it.
  const location = useLocation();
  const entryState = useRef<unknown>(location.state);
  entryState.current = location.state;

  const segments = useMemo(
    () =>
      mainFirst(
        (paper?.segments ?? []).filter((s) => s.candidate !== true),
        paper?.main_figure_page,
      ),
    [paper?.segments, paper?.main_figure_page],
  );
  const candidates = useMemo(
    () => (paper?.segments ?? []).filter((s) => s.candidate === true),
    [paper?.segments],
  );

  const [open, setOpen] = useState<WorkspaceDialog | null>(null);
  const dialog = open && segments.some((s) => s.id === open.segmentId) ? open : null;
  const openCompare = useCallback(
    (segmentId: string) => setOpen({ kind: "compare", segmentId }),
    [],
  );
  const openEditor = useCallback((segmentId: string) => setOpen({ kind: "edit", segmentId }), []);
  const closeDialog = useCallback(() => setOpen(null), []);

  const view: WorkspaceView = params.get("view") === "paper" ? "paper" : "review";
  // A repeat of a main-figure structure has no card: `?s=` naming one selects its main one.
  const asked = params.get("s");
  const selection = segments.find((s) => s.id === asked)?.repeat_of ?? asked;
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
    candidates,
    steps,
    allSteps,
    selection,
    setSelection,
    focus,
    openFocus,
    closeFocus,
    view,
    setView,
    live,
    dialog,
    openCompare,
    openEditor,
    closeDialog,
  };
}
