// Shared by the two lookups: a fetch with a timeout and the caller's abort, whose body is
// parsed as JSON and handed back as `unknown` (third-party data: every caller validates).
const TIMEOUT_MS = 10_000;

/** Resolves to the parsed body, `undefined` for a non-OK status; rejects on network, timeout, abort. */
export async function fetchJson(
  url: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const res = await fetch(url, {
    ...init,
    credentials: "omit",
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  if (!res.ok) return undefined;
  return (await res.json()) as unknown;
}

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
