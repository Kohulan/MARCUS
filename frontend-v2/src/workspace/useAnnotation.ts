// The paper's annotation: read once with the paper, read again when an annotate step ends
// (the live stream refreshes the steps), and the curator's three writes.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import { isStepActive } from "../api/status";
import type { AnnotationOut, AnnotationValues, StepOut } from "../api/types";
import { newestAnnotate } from "./annotation";

/**
 * GET /papers/{id}/annotation. Read again (never cancelling a read on the wire) when the
 * paper's newest annotate step has ended and the annotation was read before that: a run that
 * finished or failed while the paper is open. Asked once per difference, so an answer that
 * still differs does not loop.
 */
export function useAnnotation(paperId: string, steps: StepOut[]) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.annotation(paperId),
    queryFn: ({ signal }) => api.getAnnotation(paperId, { signal }),
  });
  const step = newestAnnotate(steps);
  const ended = step && !isStepActive(step.status) ? `${step.id}:${step.status}` : null;
  const read = query.data?.step ? `${query.data.step.id}:${query.data.step.status}` : null;
  const stale = ended !== null && query.data !== undefined && read !== ended;
  useEffect(() => {
    if (!stale) return;
    void client.invalidateQueries({ queryKey: keys.annotation(paperId) }, { cancelRefetch: false });
  }, [stale, ended, read, client, paperId]);
  return query;
}

/**
 * start: POST (a 202 reopens the paper's live stream through `onStarted`, the paper is
 * busy again until the step ends); save / reset: PUT / DELETE the curation, whose reply is
 * the annotation. Each rejects with the ApiError.
 */
export function useAnnotationActions(paperId: string, onStarted: () => void) {
  const client = useQueryClient();
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

  return { start, save, reset };
}
