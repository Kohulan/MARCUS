// Server state of the tool (TanStack Query): query keys, the client defaults, the read
// hooks, and the one way the UI writes a single curation.
import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
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

// Live events and poll ticks ask for a paper refresh. A running 200-structure paper sends
// hundreds of events (one per step state change), and every refresh is 2 GETs in the plain
// 300/min IP bucket, so refreshes are coalesced per paper: at most one per REFRESH_MS, the
// last request of a burst is never dropped (a trailing refresh), and a refresh never starts
// while the paper or its steps are still being fetched (it waits for that fetch, then
// refetches, so data newer than that fetch is read).
export const REFRESH_MS = 1000;

type RefreshState = {
  timer: ReturnType<typeof setTimeout> | null;
  pending: boolean;
  last: number;
};

const refreshes = new WeakMap<QueryClient, Map<string, RefreshState>>();

function refreshState(client: QueryClient, id: string): RefreshState {
  let map = refreshes.get(client);
  if (!map) {
    map = new Map();
    refreshes.set(client, map);
  }
  let state = map.get(id);
  if (!state) {
    state = { timer: null, pending: false, last: -Infinity };
    map.set(id, state);
  }
  return state;
}

function fetchingPaper(client: QueryClient, id: string): boolean {
  return (
    client.isFetching({ queryKey: keys.paper(id) }) > 0 ||
    client.isFetching({ queryKey: keys.steps(id) }) > 0
  );
}

/** Refetch a paper and its steps (only these two): what a live event or a poll tick does. */
export function refreshPaper(client: QueryClient, id: string): void {
  const state = refreshState(client, id);
  state.pending = true;
  if (state.timer !== null) return; // the scheduled refresh will cover this request

  const run = () => {
    state.pending = false;
    state.last = Date.now();
    // cancelRefetch false: never cancel (and so never repeat) a fetch already on the wire
    void client.invalidateQueries({ queryKey: keys.paper(id) }, { cancelRefetch: false });
    void client.invalidateQueries({ queryKey: keys.steps(id) }, { cancelRefetch: false });
  };
  const schedule = (delay: number) => {
    state.timer = setTimeout(() => {
      state.timer = null;
      if (!state.pending) return;
      if (fetchingPaper(client, id)) schedule(REFRESH_MS);
      else run();
    }, delay);
  };

  const since = Date.now() - state.last;
  if (since >= REFRESH_MS && !fetchingPaper(client, id)) run();
  else schedule(Math.max(REFRESH_MS - since, 0) || REFRESH_MS);
}

export function usePapers() {
  return useQuery({ queryKey: keys.papers(), queryFn: ({ signal }) => api.listPapers({ signal }) });
}

export function usePaper(id: string) {
  return useQuery({ queryKey: keys.paper(id), queryFn: paperFn(id) });
}

function paperFn(id: string) {
  return ({ signal }: { signal: AbortSignal }) => api.getPaper(id, { signal });
}

export function useSteps(id: string) {
  return useQuery({
    queryKey: keys.steps(id),
    queryFn: ({ signal }) => api.getSteps(id, { signal }),
  });
}

/** The queue position; refetched every 10 s while `active` (a paper checking or processing). */
export function useQueue(active: boolean) {
  return useQuery({
    queryKey: keys.queue(),
    queryFn: ({ signal }) => api.getQueue({ signal }),
    enabled: active,
    refetchInterval: active ? QUEUE_REFRESH_MS : false,
  });
}

export function useText(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.text(id),
    queryFn: ({ signal }) => api.getText(id, { signal }),
    enabled,
    staleTime: Infinity,
  });
}

export function useImages() {
  return useQuery({ queryKey: keys.images(), queryFn: ({ signal }) => api.listImages({ signal }) });
}

export function useImageJob(id: string) {
  return useQuery({
    queryKey: keys.image(id),
    queryFn: ({ signal }) => api.getImageJob(id, { signal }),
  });
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

/** Thrown by save() when the segment is not in the paper: nothing is written. */
export const SEGMENT_GONE = "This structure is not here any more.";

/**
 * The segment's stored curation (null: it has none yet). A paper missing from the cache is
 * fetched first; a segment missing from the paper rejects. Never a guessed null: a body
 * built from null would clear the stored smiles, molfile and note.
 */
async function currentCuration(
  client: QueryClient,
  paperId: string,
  segmentId: string,
): Promise<CurationOut | null> {
  const key = keys.paper(paperId);
  const paper: PaperDetail =
    client.getQueryData<PaperDetail>(key) ??
    (await client.fetchQuery<PaperDetail>({ queryKey: key, queryFn: paperFn(paperId) }));
  const segment = paper.segments.find((s) => s.id === segmentId);
  if (!segment) throw new ApiError(404, SEGMENT_GONE);
  return segment.curation;
}

/**
 * `save(segmentId, change)`: PUT the full curation built by curationBody from the cached one
 * (the paper is fetched first when it is not cached; a segment not in it rejects unsaved),
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
          const body = curationBody(await currentCuration(client, paperId, segmentId), change);
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
