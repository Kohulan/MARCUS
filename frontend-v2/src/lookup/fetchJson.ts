// Shared by the two lookups: a fetch with a timeout and the caller's abort, whose body is
// parsed as JSON and handed back as `unknown` (third-party data: every caller validates).
export const TIMEOUT_MS = 10_000;

/** Resolves to the parsed body, `undefined` for a non-OK status; rejects on network, timeout, abort. */
export async function fetchJson(
  url: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  // One controller for both the timeout and the caller's abort (AbortSignal.any/timeout are
  // not in older browsers).
  const ctl = new AbortController();
  const onAbort = () => ctl.abort();
  if (signal?.aborted) ctl.abort();
  else signal?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(onAbort, TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      ...init,
      credentials: "omit",
      signal: ctl.signal,
    });
    if (!res.ok) return undefined;
    return (await res.json()) as unknown;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
