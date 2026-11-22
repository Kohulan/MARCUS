// R-group rows of the paper's scaffolds (GET /papers/{id}/rgroups): one list per paper, read by
// one poller (the workspace) every 2 s while a reading is in flight; each scaffold reads its
// own entry from that list. A reading never reopens the paper, so there is no live stream for it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { RgroupExtractionOut, RgroupList } from "../api/types";
import { anyRgroupActive, extractionFor } from "./rgroups";

export const RGROUP_POLL_MS = 2000;

/** The open paper's id, for the scaffolds below the workspace (null outside one). */
export const RgroupPaper = createContext<string | null>(null);

/**
 * The paper's list, read again every RGROUP_POLL_MS while a reading is queued or running.
 * `enabled`: the paper has a scaffold (a paper without one never asks).
 */
export function useRgroupList(paperId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.rgroups(paperId),
    queryFn: ({ signal }) => api.getPaperRgroups(paperId, { signal }),
    enabled,
    refetchInterval: (query) => (anyRgroupActive(query.state.data) ? RGROUP_POLL_MS : false),
  });
}

export type RgroupReading = {
  /** The deployment reads R-groups (false also before the list is in). */
  available: boolean;
  /** The prediction's reading; undefined: never asked for. */
  extraction: RgroupExtractionOut | undefined;
  /** POST, then the list is read again (it polls from there). Rejects with the ApiError. */
  start: (rerun: boolean) => Promise<void>;
};

/**
 * One prediction's reading (card, focus mode). It never polls itself: the workspace's
 * useRgroupList does, and this reads the same cached list.
 */
export function useRgroupReading(predictionId: string | undefined): RgroupReading {
  const paperId = useContext(RgroupPaper);
  const client = useQueryClient();
  const select = useCallback(
    (list: RgroupList) => ({
      available: list.available,
      extraction: extractionFor(list, predictionId),
    }),
    [predictionId],
  );
  const query = useQuery({
    queryKey: keys.rgroups(paperId ?? ""),
    queryFn: ({ signal }) => api.getPaperRgroups(paperId ?? "", { signal }),
    enabled: paperId !== null && predictionId !== undefined,
    staleTime: Infinity,
    select,
  });
  const start = useCallback(
    async (rerun: boolean) => {
      if (paperId === null || predictionId === undefined) return;
      await api.startRgroups(predictionId, rerun);
      await client.invalidateQueries({ queryKey: keys.rgroups(paperId) });
    },
    [client, paperId, predictionId],
  );
  return {
    available: query.data?.available ?? false,
    extraction: query.data?.extraction,
    start,
  };
}
