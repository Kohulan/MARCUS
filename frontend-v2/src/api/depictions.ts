// Loading stored depictions (GET /segments/{id}/depiction) for a grid of up to hundreds of
// cards. The API draws a missing depiction on the tools worker, with at most 4 draws per API
// process (marcus/api/tooling.py MAX_DEPICTION_WAITS); above that it answers 503 with
// Retry-After: 5. A plain <img src> cannot see that header or limit how many load at once,
// so depictions are fetched here and shown from a blob: URL (CSP img-src allows blob:):
//
// - at most 4 loads in flight per tab, first asked first served (the grid's top first);
// - a 503 or 429 (or a gateway 502/504) pauses the whole queue for Retry-After seconds
//   (default 5, at most 30) and puts the load back at the front. A busy reply is not a
//   failure: it never counts as an attempt (a second tab makes 503s routine). A load gives
//   up only when its busy waiting would pass 5 minutes in all;
// - any other error fails at once (404 or 422: nothing to draw; anything else can be
//   retried by hand: useDepiction's `retry`);
// - an aborted load leaves the queue (unmounted card);
// - the tab's loader waits for the owner gate (client.ts ownerReady) before its first fetch:
//   a raw fetch bypasses the gate, and a cookie-less one would make a second owner.
//
// A loaded drawing is kept in memory for the tab (`drawings` below), so a card that comes
// back (a filter change, Review ↔ Paper, focus mode on the same structure) shows it at once
// and asks nothing. Behind that, the browser HTTP cache still applies (Cache-Control:
// private, max-age=86400 and the `v=<depictionKey>` in the URL).
import { useCallback, useEffect, useState } from "react";
import { api, isGone, ownerReady, svgBlobUrl, toApiError } from "./client";
import type { DepictReply } from "./types";

const RETRY_STATUSES = new Set([429, 502, 503, 504]);
const DEFAULT_WAIT_S = 5;
const MAX_WAIT_S = 30;
const MAX_BUSY_MS = 5 * 60_000;

type Job = {
  url: string;
  signal: AbortSignal | undefined;
  /** Date.now() of the first busy reply, null before one. */
  busySince: number | null;
  resolve: (blob: Blob) => void;
  reject: (err: unknown) => void;
};

export type DepictionLoader = { load: (url: string, signal?: AbortSignal) => Promise<Blob> };

function abortError(): DOMException {
  return new DOMException("The load was aborted.", "AbortError");
}

export function createDepictionLoader(
  opts: { maxActive?: number; maxBusyMs?: number; gate?: () => Promise<void> } = {},
): DepictionLoader {
  const maxActive = opts.maxActive ?? 4;
  const maxBusyMs = opts.maxBusyMs ?? MAX_BUSY_MS;
  const queue: Job[] = [];
  let active = 0;
  let pause: ReturnType<typeof setTimeout> | null = null;

  const pump = () => {
    while (pause === null && active < maxActive && queue.length > 0) {
      const job = queue.shift()!;
      if (job.signal?.aborted) continue; // already rejected by its abort listener
      void run(job);
    }
  };

  const pauseFor = (seconds: number) => {
    if (pause !== null) clearTimeout(pause);
    pause = setTimeout(() => {
      pause = null;
      pump();
    }, seconds * 1000);
  };

  const run = async (job: Job) => {
    active += 1;
    try {
      if (opts.gate) await opts.gate();
      const init: RequestInit = { credentials: "same-origin" };
      if (job.signal) init.signal = job.signal;
      const res = await fetch(job.url, init);
      if (res.ok) {
        job.resolve(await res.blob());
        return;
      }
      const err = await toApiError(res);
      if (RETRY_STATUSES.has(res.status) && !job.signal?.aborted) {
        const wait = Math.min(Math.max(err.retryAfter ?? DEFAULT_WAIT_S, 1), MAX_WAIT_S);
        const now = Date.now();
        job.busySince ??= now;
        if (now - job.busySince + wait * 1000 <= maxBusyMs) {
          pauseFor(wait);
          queue.unshift(job);
          return;
        }
      }
      job.reject(err);
    } catch (err) {
      job.reject(err);
    } finally {
      active -= 1;
      pump();
    }
  };

  const load = (url: string, signal?: AbortSignal): Promise<Blob> =>
    new Promise<Blob>((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError());
        return;
      }
      const job: Job = { url, signal, busySince: null, resolve, reject };
      signal?.addEventListener(
        "abort",
        () => {
          const i = queue.indexOf(job);
          if (i >= 0) queue.splice(i, 1);
          reject(abortError()); // an in-flight fetch also rejects; the first settle wins
        },
        { once: true },
      );
      queue.push(job);
      pump();
    });

  return { load };
}

/** The one loader of the tab. */
export const depictionLoader = createDepictionLoader({ gate: ownerReady });

// The drawings loaded in this tab, by URL: one blob and one blob: URL each, shared by every
// view that shows it. One in use is never revoked; up to `maxIdle` unused ones are kept
// (most recently used last), the oldest beyond that are revoked and dropped.
type Drawing = { blob: Blob; src: string; users: number };

export function createDrawingCache(maxIdle: number) {
  const drawings = new Map<string, Drawing>();
  return {
    get: (url: string) => drawings.get(url),
    /** One more user of `url`'s drawing (kept from `blob` when new); undefined without one. */
    take(url: string, blob?: Blob): Drawing | undefined {
      let d = drawings.get(url);
      if (!d && blob) {
        d = { blob, src: URL.createObjectURL(blob), users: 0 };
        drawings.set(url, d);
      }
      if (d) d.users += 1;
      return d;
    },
    release(url: string, d: Drawing) {
      d.users -= 1;
      if (d.users > 0 || drawings.get(url) !== d) return;
      drawings.delete(url); // re-inserted: the most recently used
      drawings.set(url, d);
      let idle = [...drawings.values()].filter((x) => x.users === 0).length;
      for (const [key, x] of drawings) {
        if (idle <= maxIdle) break;
        if (x.users > 0) continue;
        URL.revokeObjectURL(x.src);
        drawings.delete(key);
        idle -= 1;
      }
    },
    clear() {
      for (const d of drawings.values()) URL.revokeObjectURL(d.src);
      drawings.clear();
    },
  };
}

const drawings = createDrawingCache(300);

/** A drawing this tab has loaded (Download saves it without asking again). */
export function loadedDrawing(url: string): Blob | undefined {
  return drawings.get(url)?.blob;
}

/** Tests only: forget every loaded drawing. */
export function forgetDrawings(): void {
  drawings.clear();
}

/**
 * A blob: URL for `<Structure src>` (null while it loads or for a null `url`); `failed` when
 * the drawing cannot be had. `retry` (null otherwise) loads it again when the failure was
 * not "nothing to draw": a server busy for minutes, a network error. A drawing already
 * loaded in the tab is shown at once; the load is aborted on unmount or change.
 */
export function useDepiction(url: string | null): {
  src: string | null;
  failed: boolean;
  retry: (() => void) | null;
} {
  // Keyed by URL and try, so a changed URL (or a retry) never shows the previous blob.
  const [tries, setTries] = useState(0);
  const [state, setState] = useState<{
    url: string;
    tries: number;
    src: string | null;
    failed: boolean;
    again: boolean;
  }>();

  useEffect(() => {
    if (url === null) return;
    let held = drawings.take(url);
    if (held) {
      const d = held;
      setState({ url, tries, src: d.src, failed: false, again: false });
      return () => drawings.release(url, d);
    }
    const ctrl = new AbortController();
    depictionLoader.load(url, ctrl.signal).then(
      (blob) => {
        if (ctrl.signal.aborted) return;
        held = drawings.take(url, blob)!;
        setState({ url, tries, src: held.src, failed: false, again: false });
      },
      (err: unknown) => {
        if (ctrl.signal.aborted) return;
        // Gone (404, 422): nothing to draw, so a retry would get the same.
        setState({ url, tries, src: null, failed: true, again: !isGone(err) });
      },
    );
    return () => {
      ctrl.abort();
      if (held) drawings.release(url, held);
    };
  }, [url, tries]);

  const retry = useCallback(() => setTries((n) => n + 1), []);
  if (url === null) return { src: null, failed: false, retry: null };
  if (state?.url !== url || state.tries !== tries) {
    // Loaded before (another card, an earlier visit): shown from the first render.
    return { src: drawings.get(url)?.src ?? null, failed: false, retry: null };
  }
  return { src: state.src, failed: state.failed, retry: state.again ? retry : null };
}

/** A /tools/depict drawing: key ["depict", smiles, highlight] (null: a plain drawing). */
export function depictQuery(smiles: string, highlight: string | null) {
  return {
    queryKey: ["depict", smiles, highlight] as const,
    queryFn: (): Promise<DepictReply> =>
      highlight === null ? api.depict(smiles) : api.depict(smiles, { highlight }),
    staleTime: Infinity,
  };
}

/** A blob: URL for a depict reply (null without one), revoked when it changes or unmounts. */
export function useReplyUrl(reply: DepictReply | undefined): string | null {
  const [shown, setShown] = useState<{ reply: DepictReply; url: string } | null>(null);
  useEffect(() => {
    if (!reply) return;
    const url = svgBlobUrl(reply);
    setShown({ reply, url });
    return () => URL.revokeObjectURL(url);
  }, [reply]);
  return reply !== undefined && shown?.reply === reply ? shown.url : null;
}
