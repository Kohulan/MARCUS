// Server state of the tool (TanStack Query): query keys, the client defaults, the read
// hooks, and the one way the UI writes a single curation.
import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError, errorText } from "./client";
import { curationBody, type CurationChange } from "./curation";
import { isImageActive, isPaperBusy } from "./status";
import type { BulkCurationItem, CurationOut, PaperDetail, StepList } from "./types";

export const keys = {
  papers: () => ["papers"] as const,
  paper: (id: string) => ["paper", id] as const,
  steps: (id: string) => ["steps", id] as const,
  queue: () => ["queue"] as const,
  text: (id: string) => ["text", id] as const,
  annotation: (id: string) => ["annotation", id] as const,
  rgroups: (id: string) => ["rgroups", id] as const,
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
const REFRESH_MS = 1000;

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

// Curation saves still on the wire, per paper. A refresh read before such a PUT has committed
// would bring the old curation back over the optimistic one (a stamp that vanishes and lands
// again), so a refresh waits for them as it waits for a fetch.
const saving = new WeakMap<QueryClient, Map<string, number>>();

function savingCount(client: QueryClient): Map<string, number> {
  let map = saving.get(client);
  if (!map) {
    map = new Map();
    saving.set(client, map);
  }
  return map;
}

/** Counts `work` as a save of paper `id` until it settles. */
function whileSaving<T>(client: QueryClient, id: string, work: Promise<T>): Promise<T> {
  const map = savingCount(client);
  map.set(id, (map.get(id) ?? 0) + 1);
  const done = () => {
    const n = (map.get(id) ?? 1) - 1;
    if (n > 0) map.set(id, n);
    else map.delete(id);
  };
  void work.then(done, done);
  return work;
}

const busyPaper = (client: QueryClient, id: string) =>
  fetchingPaper(client, id) || (saving.get(client)?.has(id) ?? false);

/**
 * True when a stream's snapshot ({status, counts: {steps_by_status}}) says what the cached
 * paper and steps already say, so a refetch would bring nothing new.
 */
export function snapshotIsCached(client: QueryClient, id: string, snapshot: unknown): boolean {
  const paper = client.getQueryData<PaperDetail>(keys.paper(id));
  const steps = client.getQueryData<StepList>(keys.steps(id))?.steps;
  if (!paper || !steps || typeof snapshot !== "object" || snapshot === null) return false;
  const snap = snapshot as { status?: unknown; counts?: { steps_by_status?: unknown } };
  const byStatus = snap.counts?.steps_by_status;
  if (snap.status !== paper.status || typeof byStatus !== "object" || byStatus === null) {
    return false;
  }
  const mine: Record<string, number> = {};
  for (const s of steps) mine[s.status] = (mine[s.status] ?? 0) + 1;
  const theirs = Object.entries(byStatus as Record<string, unknown>).filter(([, n]) => n !== 0);
  return (
    theirs.length === Object.keys(mine).length && theirs.every(([k, n]) => mine[k] === n)
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
      if (busyPaper(client, id)) schedule(REFRESH_MS);
      else run();
    }, delay);
  };

  const since = Date.now() - state.last;
  if (since >= REFRESH_MS && !busyPaper(client, id)) run();
  else schedule(Math.max(REFRESH_MS - since, 0) || REFRESH_MS);
}

// The papers and image lists (tool home) have no stream of their own: while one of their
// items is still being worked on, they are fetched again every LIST_POLL_MS.
export const LIST_POLL_MS = 5000;
const anyBusy = (items: { status: string }[] | undefined, busy: (status: string) => boolean) =>
  (items ?? []).some((item) => busy(item.status));

export function usePapers() {
  return useQuery({
    queryKey: keys.papers(),
    queryFn: ({ signal }) => api.listPapers({ signal }),
    refetchInterval: (query) =>
      anyBusy(query.state.data?.papers, isPaperBusy) ? LIST_POLL_MS : false,
  });
}

/** While the server could not link a paper's repeats (links_ready false), it is read again. */
export const LINKS_POLL_MS = 5000;

export function usePaper(id: string) {
  return useQuery({
    queryKey: keys.paper(id),
    queryFn: paperFn(id),
    refetchInterval: (query) => (query.state.data?.links_ready === false ? LINKS_POLL_MS : false),
  });
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
    refetchInterval: (query) =>
      anyBusy(query.state.data?.jobs, isImageActive) ? LIST_POLL_MS : false,
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

// The workspace counts from its rows and the tool home reads GET /papers, so the cached
// paper's own counts are never patched here: only segments change.

/** The paper with one segment's curation replaced (no refetch). */
function withCuration(
  paper: PaperDetail,
  segmentId: string,
  curation: CurationOut | null,
): PaperDetail {
  return {
    ...paper,
    segments: paper.segments.map((s) => (s.id === segmentId ? { ...s, curation } : s)),
  };
}

/**
 * `save(segmentId, change)`: PUT the full curation built by curationBody from the cached one
 * (the paper is fetched first when it is not cached; a segment not in it rejects unsaved).
 * Optimistic for status and note, as bulk() is: the body goes into the ["paper", paperId]
 * cache at once, the reply replaces it, and a failed PUT rolls it back and rejects. A change
 * of structure is written only with the reply. Refreshes wait while a save is on the wire (a
 * PUT not answered in SAVE_TIMEOUT_MS fails, and the paper is then fetched again, as after a
 * 5xx). The only way the UI writes a single curation (PUT replaces the whole record).
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
          const before = await currentCuration(client, paperId, segmentId);
          const body = curationBody(before, change);
          // A paper fetch on the wire would bring back the old curation (over the optimistic
          // one now, over the reply later) and the next change would build on it: cancel it,
          // write, and fetch again once the PUT has answered.
          const write = async (curation: CurationOut | null) => {
            const stale = client.isFetching({ queryKey: key }) > 0;
            if (stale) await client.cancelQueries({ queryKey: key });
            client.setQueryData<PaperDetail>(key, (old) =>
              old ? withCuration(old, segmentId, curation) : old,
            );
            return stale;
          };
          // Optimistic only for status and note. A new structure waits for the reply: its
          // drawing key would change at once, and the drawing asked for under it would be the
          // one still stored (the server draws what it has committed).
          const optimistic = change.structure === undefined;
          const cancelled = optimistic ? await write(body) : false;
          let out: CurationOut;
          try {
            out = await api.putCuration(segmentId, body);
          } catch (err) {
            if ((optimistic && (await write(before))) || cancelled) {
              void client.invalidateQueries({ queryKey: key });
            }
            // No answer, a network error or a 5xx (a timed-out PUT is a 504): the server may
            // have saved it. Fetch the paper once more (after the saves on the wire), so the
            // screen shows what is stored rather than the rollback.
            if (!(err instanceof ApiError) || err.status >= 500) refreshPaper(client, paperId);
            throw err;
          }
          // A new structure can make or end a repeat of the main figure (the server links
          // them): fetch the paper again when it has one.
          const relink =
            change.structure !== undefined &&
            client.getQueryData<PaperDetail>(key)?.main_figure_page != null;
          if ((await write(out)) || cancelled || relink) {
            void client.invalidateQueries({ queryKey: key });
          }
          return out;
        });
      map.set(segmentId, run);
      void run.then(
        () => (map.get(segmentId) === run ? map.delete(segmentId) : undefined),
        () => (map.get(segmentId) === run ? map.delete(segmentId) : undefined),
      );
      return whileSaving(client, paperId, run);
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
    super(
      `Saved ${saved.toLocaleString("en")} of ${total.toLocaleString("en")}: ${errorText(cause)}`,
    );
    this.name = "BulkPartialError";
  }
}

/** The most items one PUT /papers/{id}/curation takes. */
const BULK_CHUNK = 500;

type BulkStatus = BulkCurationItem["status"];

/** The paper with `status` set on the given segments. */
function withStatuses(
  paper: PaperDetail,
  statuses: Map<string, BulkStatus | null>,
): PaperDetail {
  const segments = paper.segments.map((s) => {
    if (!statuses.has(s.id)) return s;
    const next = statuses.get(s.id)!;
    const before = s.curation?.status ?? "unchecked";
    const after = next ?? "unchecked";
    if (before === after && (next !== null || s.curation === null)) return s;
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
  return { ...paper, segments };
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
        void client.invalidateQueries({ queryKey: key });
      })();
      void whileSaving(client, paperId, run);
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

/**
 * `mark(page0)`: marks a page as the paper's main figure (null clears it). The page changes in
 * the cache at once (the order follows); the repeat links stay as they were until the fetch
 * that follows brings the server's (dropping them early could let a compound be sent twice). A
 * failure puts the old page back and rejects.
 */
export function useMainFigure(paperId: string): { mark: (page0: number | null) => Promise<void> } {
  const client = useQueryClient();
  const mark = useCallback(
    async (page0: number | null): Promise<void> => {
      const key = keys.paper(paperId);
      await client.cancelQueries({ queryKey: key });
      const old = client.getQueryData<PaperDetail>(key);
      client.setQueryData<PaperDetail>(key, (p) => (p ? { ...p, main_figure_page: page0 } : p));
      try {
        await api.putMainFigure(paperId, page0);
      } catch (err) {
        if (old) client.setQueryData<PaperDetail>(key, old);
        throw err;
      } finally {
        void client.invalidateQueries({ queryKey: key });
      }
    },
    [client, paperId],
  );
  return { mark };
}
