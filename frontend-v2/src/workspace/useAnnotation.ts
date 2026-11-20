// The paper's annotation: read once with the paper, read again when an annotate step ends
// (the live stream refreshes the steps), and the curator's three writes.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import { isStepActive } from "../api/status";
import type { AnnotationOut, AnnotationValues, StepOut } from "../api/types";
import { newestAnnotate } from "./annotation";

/**
 * GET /papers/{id}/annotation. Read again (once per hook, never cancelling a read on the
 * wire) each time the paper's newest annotate step reaches an end it had not reached at the
 * last render: a run that finished or failed while the paper is open.
 */
export function useAnnotation(paperId: string, steps: StepOut[]) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.annotation(paperId),
    queryFn: ({ signal }) => api.getAnnotation(paperId, { signal }),
  });
  const step = newestAnnotate(steps);
  const ended = step && !isStepActive(step.status) ? `${step.id}:${step.status}` : null;
  const seen = useRef(ended);
  useEffect(() => {
    if (ended === seen.current) return;
    seen.current = ended;
    if (ended !== null) {
      void client.invalidateQueries({ queryKey: keys.annotation(paperId) }, { cancelRefetch: false });
    }
  }, [ended, client, paperId]);
  return query;
}

/**
 * start: POST (a 202 reopens the paper's live stream through `onStarted`, the paper is
 * busy again until the step ends); save / reset: PUT / DELETE the curation, whose reply is
 * the annotation. Each rejects with the ApiError.
 */
export function useAnnotationActions(paperId: string, onStarted: () => void) {
  const client = useQueryClient();
  const key = keys.annotation(paperId);
  const put = useCallback(
    (a: AnnotationOut) => client.setQueryData<AnnotationOut>(keys.annotation(paperId), a),
    [client, paperId],
  );

  const start = useCallback(async () => {
    const out = await api.startAnnotation(paperId);
    if (out.step_id !== null) onStarted();
    void client.invalidateQueries({ queryKey: keys.annotation(paperId) });
    return out;
  }, [client, paperId, onStarted]);

  const save = useCallback(
    async (values: AnnotationValues) => put(await api.saveAnnotation(paperId, values)),
    [paperId, put],
  );
  const reset = useCallback(async () => put(await api.resetAnnotation(paperId)), [paperId, put]);

  return { start, save, reset, key };
}
