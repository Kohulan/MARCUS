// What a structure card's buttons do, shared by the review grid and the Paper view's list:
// Accept / Reject (one curation save) and a run with another engine.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, errorText } from "../api/client";
import { refreshPaper, useSaveCuration } from "../api/queries";
import type { CurationStatus, Engine } from "../api/types";
import { useToast } from "../ui/Toasts";

/**
 * `decide` saves a card's status (a failure says so in a toast); `run` starts a prediction
 * with an engine; `started` is what follows an accepted run: the live stream opens again
 * if it had ended (a finished or ocsr=off paper) and the steps are read once, so the card
 * says "Reading…" at once. All three are stable for a paper.
 */
export function useCardActions(paperId: string, reconnect: () => void) {
  const client = useQueryClient();
  const toast = useToast();
  const { save } = useSaveCuration(paperId);

  const started = useCallback(() => {
    reconnect();
    refreshPaper(client, paperId);
  }, [reconnect, client, paperId]);

  const decide = useCallback(
    (segmentId: string, status: CurationStatus) => {
      save(segmentId, { status }).catch((err: unknown) =>
        toast(`Not saved: ${errorText(err)}`, "error"),
      );
    },
    [save, toast],
  );

  const run = useCallback(
    (segmentId: string, engine: Engine) => {
      api.runPrediction(segmentId, engine).then(started, (err: unknown) =>
        toast(`Not started: ${errorText(err)}`, "error"),
      );
    },
    [started, toast],
  );

  return { decide, run, started };
}
