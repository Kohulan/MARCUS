// Server state of the tool (TanStack Query): query keys, the client defaults, the read
// hooks, and the one way the UI writes a single curation.
import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "./client";
import { curationBody, type CurationChange } from "./curation";
import type { BulkCurationItem, CurationOut, CurationStatus, PaperDetail } from "./types";

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

// The papers and image lists (tool home) have no stream of their own: while one of their
// items is still being worked on, they are fetched again every LIST_POLL_MS.
export const LIST_POLL_MS = 5000;
const ACTIVE = new Set(["checking", "processing", "queued"]);
const anyActive = (items: { status: string }[] | undefined) =>
  (items ?? []).some((item) => ACTIVE.has(item.status));

export function usePapers() {
  return useQuery({
    queryKey: keys.papers(),
    queryFn: ({ signal }) => api.listPapers({ signal }),
    refetchInterval: (query) => (anyActive(query.state.data?.papers) ? LIST_POLL_MS : false),
  });
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

/** `enabled` false holds the request (the tool home asks after its papers list answered). */
export function useImages(enabled = true) {
  return useQuery({
    queryKey: keys.images(),
    queryFn: ({ signal }) => api.listImages({ signal }),
    enabled,
    refetchInterval: (query) => (anyActive(query.state.data?.jobs) ? LIST_POLL_MS : false),
  });
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

type Counts = Pick<PaperDetail, "accepted" | "rejected" | "to_review">;

/** Moves one structure from status `from` to `to` in the paper's counts. */
function moveCount(counts: Counts, from: CurationStatus, to: CurationStatus): Counts {
  if (from === to) return counts;
  const next = { ...counts };
  const field = (s: CurationStatus) =>
    s === "accepted" ? "accepted" : s === "rejected" ? "rejected" : "to_review";
  next[field(from)] -= 1;
  next[field(to)] += 1;
  return next;
}

/** The paper with one segment's curation replaced and its counts moved to match (no refetch). */
function withCuration(paper: PaperDetail, segmentId: string, out: CurationOut): PaperDetail {
  const segment = paper.segments.find((s) => s.id === segmentId);
  if (!segment) return paper;
  const counts = moveCount(paper, segment.curation?.status ?? "unchecked", out.status);
  return {
    ...paper,
    accepted: counts.accepted,
    rejected: counts.rejected,
    to_review: counts.to_review,
    segments: paper.segments.map((s) => (s.id === segmentId ? { ...s, curation: out } : s)),
  };
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
            old ? withCuration(old, segmentId, out) : old,
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

/**
 * Thrown by bulk() when a chunk failed after earlier chunks were saved: `saved` of `total`
 * items kept their new status (the rest were rolled back). `cause` is the chunk's error.
 */
export class BulkPartialError extends Error {
  constructor(
    readonly saved: number,
    readonly total: number,
    override readonly cause: unknown,
  ) {
    const why = cause instanceof ApiError ? cause.detail : "Something went wrong.";
    super(`Saved ${saved.toLocaleString("en")} of ${total.toLocaleString("en")}: ${why}`);
    this.name = "BulkPartialError";
  }
}

/** The most items one PUT /papers/{id}/curation takes. */
export const BULK_CHUNK = 500;

type BulkStatus = BulkCurationItem["status"];

/** The paper with `status` set on the given segments, and its counts moved to match. */
function withStatuses(
  paper: PaperDetail,
  statuses: Map<string, BulkStatus | null>,
): PaperDetail {
  const counts = { accepted: paper.accepted, rejected: paper.rejected, to_review: paper.to_review };
  const bump = (status: BulkStatus, by: number) => {
    if (status === "accepted") counts.accepted += by;
    else if (status === "rejected") counts.rejected += by;
    else counts.to_review += by;
  };
  const segments = paper.segments.map((s) => {
    if (!statuses.has(s.id)) return s;
    const next = statuses.get(s.id)!;
    const before = s.curation?.status ?? "unchecked";
    const after = next ?? "unchecked";
    if (before === after && (next !== null || s.curation === null)) return s;
    bump(before, -1);
    bump(after, 1);
    const c = s.curation;
    // null (a rollback): back to no curation, unless a note or structure was stored since
    const curation: CurationOut | null =
      next === null && c !== null && !c.smiles && !c.molfile && !c.note
        ? null
        : c
          ? { ...c, status: after }
          : { status: after, smiles: null, molfile: null, note: null };
    return { ...s, curation };
  });
  return { ...paper, ...counts, segments };
}

/**
 * `bulk(items)`: set the status of many segments with PUT /papers/{id}/curation, in chunks
 * of BULK_CHUNK, one after another. Items carry no `note` key, so the server keeps every
 * note (and structure). The cache changes at once (optimistic); a chunk that fails, and
 * every chunk after it, is rolled back (status only) and bulk() rejects. A bulk change waits
 * for pending single saves of the same segments and later single saves wait for it (the
 * per-segment chain of useSaveCuration), so a save's reply never lands over it out of order.
 * A failure after a saved chunk rejects with BulkPartialError (how many were saved).
 */
export function useBulkCuration(paperId: string): {
  bulk: (items: BulkCurationItem[]) => Promise<void>;
} {
  const client = useQueryClient();
  const bulk = useCallback(
    (items: BulkCurationItem[]): Promise<void> => {
      const key = keys.paper(paperId);
      const map = chainFor(client);
      const ids = items.map((i) => i.segment_id);
      const wanted = new Set(ids);
      const cached = client.getQueryData<PaperDetail>(key);
      const before = new Map<string, BulkStatus | null>(
        (cached?.segments ?? [])
          .filter((s) => wanted.has(s.id))
          .map((s) => [s.id, s.curation?.status ?? null]),
      );
      const apply = (list: BulkCurationItem[], undo: boolean) => {
        const statuses = new Map(
          list.map((i) => [i.segment_id, undo ? (before.get(i.segment_id) ?? null) : i.status]),
        );
        client.setQueryData<PaperDetail>(key, (old) => (old ? withStatuses(old, statuses) : old));
      };

      // Taken now, so the chain order is the call order.
      const prior = ids.map((id) => map.get(id)).filter((p): p is Promise<unknown> => !!p);
      const run = (async () => {
        // A fetch already on the wire would bring the old statuses back over the optimistic
        // ones (and a cancelled one reverts its state): cancel first, then write.
        await client.cancelQueries({ queryKey: key });
        apply(items, false);
        await Promise.allSettled(prior);
        // A single save that finished meanwhile wrote its reply (with the old status).
        apply(items, false);
        for (let i = 0; i < items.length; i += BULK_CHUNK) {
          try {
            await api.putBulkCuration(paperId, items.slice(i, i + BULK_CHUNK));
          } catch (err) {
            apply(items.slice(i), true);
            void client.invalidateQueries({ queryKey: key });
            throw i > 0 ? new BulkPartialError(i, items.length, err) : err;
          }
        }
        await client.cancelQueries({ queryKey: key });
        apply(items, false);
        void client.invalidateQueries({ queryKey: key }); // the server's counts
      })();
      for (const id of ids) map.set(id, run);
      void run.then(
        () => ids.forEach((id) => (map.get(id) === run ? map.delete(id) : undefined)),
        () => ids.forEach((id) => (map.get(id) === run ? map.delete(id) : undefined)),
      );
      return run;
    },
    [client, paperId],
  );
  return { bulk };
}
