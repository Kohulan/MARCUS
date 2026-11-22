// The paper's annotation: read with the paper, and again every ANNOTATION_POLL_MS while a run is
// on its way (its step is active, or the server says one starts by itself: `auto_pending`). The
// run is beside the paper's read, so the paper's steps and stream never show it. And the
// curator's writes.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import { isStepActive } from "../api/status";
import type { AnnotationOut, AnnotationValues } from "../api/types";

export const ANNOTATION_POLL_MS = 2000;

/** A run is queued, running, or about to start by itself. */
export function annotationBusy(a: AnnotationOut | undefined): boolean {
  return a !== undefined && ((a.step !== null && isStepActive(a.step.status)) || a.auto_pending === true);
}

/** GET /papers/{id}/annotation, read again while a run is on its way. */
export function useAnnotation(paperId: string) {
  return useQuery({
    queryKey: keys.annotation(paperId),
    queryFn: ({ signal }) => api.getAnnotation(paperId, { signal }),
    refetchInterval: (query) => (annotationBusy(query.state.data) ? ANNOTATION_POLL_MS : false),
  });
}

/**
 * start: POST (by hand: a first run where none started by itself, or `rerun`), then GET again
 * (it polls from there); save / reset: PUT / DELETE the curation, whose reply is the
 * annotation. Each rejects with the ApiError.
 */
export function useAnnotationActions(paperId: string) {
  const client = useQueryClient();
  const put = useCallback(
    (a: AnnotationOut) => client.setQueryData<AnnotationOut>(keys.annotation(paperId), a),
    [client, paperId],
  );

  const start = useCallback(
    async (rerun = false) => {
      const out = await api.startAnnotation(paperId, rerun);
      await client.invalidateQueries({ queryKey: keys.annotation(paperId) });
      return out;
    },
    [client, paperId],
  );

  const save = useCallback(
    async (values: AnnotationValues) => put(await api.saveAnnotation(paperId, values)),
    [paperId, put],
  );
  const reset = useCallback(async () => put(await api.resetAnnotation(paperId)), [paperId, put]);

  return { start, save, reset };
}
