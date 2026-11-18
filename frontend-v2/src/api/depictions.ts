// Loading stored depictions (GET /segments/{id}/depiction) for a grid of up to hundreds of
// cards. The API draws a missing depiction on the tools worker, with at most 4 draws per API
// process (marcus/api/tooling.py MAX_DEPICTION_WAITS); above that it answers 503 with
// Retry-After: 5. A plain <img src> cannot see that header or limit how many load at once,
// so depictions are fetched here and shown from a blob: URL (CSP img-src allows blob:):
//
// - at most 4 loads in flight per tab, first asked first served (the grid's top first);
// - a 503 or 429 (or a gateway 502/504) pauses the whole queue for Retry-After seconds
//   (default 5, at most 30) and puts the load back at the front; after 6 attempts it fails;
// - any other error fails at once (404: nothing to draw);
// - an aborted load leaves the queue (unmounted card);
// - the tab's loader waits for the owner gate (client.ts ownerReady) before its first fetch:
//   a raw fetch bypasses the gate, and a cookie-less one would make a second owner.
//
// The browser HTTP cache still applies (Cache-Control: private, max-age=86400 and the
// `v=<depictionKey>` in the URL), so a revisit is served from disk.
import { useEffect, useState } from "react";
import { ownerReady, toApiError } from "./client";

const RETRY_STATUSES = new Set([429, 502, 503, 504]);
const DEFAULT_WAIT_S = 5;
const MAX_WAIT_S = 30;

type Job = {
  url: string;
  signal: AbortSignal | undefined;
  attempts: number;
  resolve: (blob: Blob) => void;
  reject: (err: unknown) => void;
};

export type DepictionLoader = { load: (url: string, signal?: AbortSignal) => Promise<Blob> };

function abortError(): DOMException {
  return new DOMException("The load was aborted.", "AbortError");
}

export function createDepictionLoader(
  opts: { maxActive?: number; maxAttempts?: number; gate?: () => Promise<void> } = {},
): DepictionLoader {
  const maxActive = opts.maxActive ?? 4;
  const maxAttempts = opts.maxAttempts ?? 6;
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
    job.attempts += 1;
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
      if (RETRY_STATUSES.has(res.status) && job.attempts < maxAttempts && !job.signal?.aborted) {
        pauseFor(Math.min(Math.max(err.retryAfter ?? DEFAULT_WAIT_S, 1), MAX_WAIT_S));
        queue.unshift(job);
        return;
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
      const job: Job = { url, signal, attempts: 0, resolve, reject };
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

/**
 * A blob: URL for `<Structure src>` (null while loading or for a null `url`); `failed` when
 * the drawing cannot be had. The URL is revoked and the load aborted on unmount or change.
 */
export function useDepiction(url: string | null): { src: string | null; failed: boolean } {
  // Keyed by URL, so a changed URL never shows the previous (already revoked) blob.
  const [state, setState] = useState<{ url: string; src: string | null; failed: boolean }>();

  useEffect(() => {
    if (url === null) return;
    const ctrl = new AbortController();
    let objectUrl: string | null = null;
    depictionLoader.load(url, ctrl.signal).then(
      (blob) => {
        if (ctrl.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ url, src: objectUrl, failed: false });
      },
      () => {
        if (!ctrl.signal.aborted) setState({ url, src: null, failed: true });
      },
    );
    return () => {
      ctrl.abort();
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (url === null || state?.url !== url) return { src: null, failed: false };
  return { src: state.src, failed: state.failed };
}
