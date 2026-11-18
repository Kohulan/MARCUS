// Server state of the tool (TanStack Query): query keys, the client defaults, the read
// hooks, and the one way the UI writes a single curation.
import { QueryClient, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "./client";
import { curationBody, type CurationChange } from "./curation";
import type { CurationOut, PaperDetail } from "./types";

export const keys = {
  papers: () => ["papers"] as const,
  paper: (id: string) => ["paper", id] as const,
  steps: (id: string) => ["steps", id] as const,
  queue: () => ["queue"] as const,
  text: (id: string) => ["text", id] as const,
  images: () => ["images"] as const,
  image: (id: string) => ["image", id] as const,
};

const QUEUE_REFRESH_MS = 10000;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A 4xx (404 gone, 429 limited, 422) does not get better by asking again; a 5xx or
        // a network error gets one more try.
        retry: (failures, error) =>
          failures < 1 && !(error instanceof ApiError && error.status < 500),
        // Live events (useLiveEvents) say when to refetch; no refetch on focus as well.
        refetchOnWindowFocus: false,
        staleTime: 5000,
      },
    },
  });
}

/** Mark a paper and its steps stale: what a live event or a poll tick does. */
export function refreshPaper(client: QueryClient, id: string): void {
  void client.invalidateQueries({ queryKey: keys.paper(id) });
  void client.invalidateQueries({ queryKey: keys.steps(id) });
}

export function usePapers() {
  return useQuery({ queryKey: keys.papers(), queryFn: api.listPapers });
}

export function usePaper(id: string) {
  return useQuery({ queryKey: keys.paper(id), queryFn: () => api.getPaper(id) });
}

export function useSteps(id: string) {
  return useQuery({ queryKey: keys.steps(id), queryFn: () => api.getSteps(id) });
}

/** The queue position; refetched every 10 s while `active` (a paper checking or processing). */
export function useQueue(active: boolean) {
  return useQuery({
    queryKey: keys.queue(),
    queryFn: api.getQueue,
    enabled: active,
    refetchInterval: active ? QUEUE_REFRESH_MS : false,
  });
}

export function useText(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.text(id),
    queryFn: () => api.getText(id),
    enabled,
    staleTime: Infinity,
  });
}

export function useImages() {
  return useQuery({ queryKey: keys.images(), queryFn: api.listImages });
}

export function useImageJob(id: string) {
  return useQuery({ queryKey: keys.image(id), queryFn: () => api.getImageJob(id) });
}

// Saves of one segment run one after another, across every hook instance of one client.
const chains = new WeakMap<QueryClient, Map<string, Promise<unknown>>>();

function chainFor(client: QueryClient): Map<string, Promise<unknown>> {
  let map = chains.get(client);
  if (!map) {
    map = new Map();
    chains.set(client, map);
  }
  return map;
}

function cachedCuration(client: QueryClient, key: QueryKey, segmentId: string) {
  const paper = client.getQueryData<PaperDetail>(key);
  return paper?.segments.find((s) => s.id === segmentId)?.curation ?? null;
}

/**
 * `save(segmentId, change)`: PUT the full curation built by curationBody from the cached one,
 * then write the reply into the ["paper", paperId] cache so the next change builds on it.
 * The only way the UI writes a single curation (PUT replaces the whole record).
 */
export function useSaveCuration(paperId: string): {
  save: (segmentId: string, change: CurationChange) => Promise<CurationOut>;
} {
  const client = useQueryClient();
  const save = useCallback(
    (segmentId: string, change: CurationChange): Promise<CurationOut> => {
      const key = keys.paper(paperId);
      const map = chainFor(client);
      const previous = map.get(segmentId) ?? Promise.resolve();
      const run = previous
        .catch(() => undefined) // a failed save does not block the next one
        .then(async () => {
          const body = curationBody(cachedCuration(client, key, segmentId), change);
          const out = await api.putCuration(segmentId, body);
          // A paper fetch that started before this PUT would bring back the old curation
          // and the next change would build on it: cancel it, write, then fetch again.
          const stale = client.isFetching({ queryKey: key }) > 0;
          if (stale) await client.cancelQueries({ queryKey: key });
          client.setQueryData<PaperDetail>(key, (old) =>
            old
              ? {
                  ...old,
                  segments: old.segments.map((s) =>
                    s.id === segmentId ? { ...s, curation: out } : s,
                  ),
                }
              : old,
          );
          if (stale) void client.invalidateQueries({ queryKey: key });
          return out;
        });
      map.set(segmentId, run);
      void run.then(
        () => (map.get(segmentId) === run ? map.delete(segmentId) : undefined),
        () => (map.get(segmentId) === run ? map.delete(segmentId) : undefined),
      );
      return run;
    },
    [client, paperId],
  );
  return { save };
}
