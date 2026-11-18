import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { createDepictionLoader, useDepiction } from "./depictions";

type Pending = { url: string; resolve: (r: Response) => void; signal: AbortSignal | undefined };
let pending: Pending[];

function svg() {
  return new Response("<svg/>", { status: 200, headers: { "Content-Type": "image/svg+xml" } });
}

function busy(retryAfter?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (retryAfter !== undefined) headers["Retry-After"] = retryAfter;
  return new Response('{"detail":"tools busy, try again"}', { status: 503, headers });
}

async function flush() {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

beforeEach(() => {
  pending = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (url: string, init: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          pending.push({ url, resolve, signal: init.signal ?? undefined });
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    ),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("createDepictionLoader", () => {
  it("has at most 4 loads in flight, in order", async () => {
    const loader = createDepictionLoader();
    const loads = ["a", "b", "c", "d", "e", "f"].map((u) => loader.load(u));
    expect(pending.map((p) => p.url)).toEqual(["a", "b", "c", "d"]);
    pending[0]!.resolve(svg());
    expect((await loads[0])?.size).toBe(6);
    await flush();
    expect(pending.map((p) => p.url)).toEqual(["a", "b", "c", "d", "e"]);
  });

  it("a 503 pauses every load for Retry-After, then retries the same URL", async () => {
    vi.useFakeTimers();
    const loader = createDepictionLoader();
    const loads = ["a", "b", "c", "d", "e"].map((u) => loader.load(u));
    pending[0]!.resolve(busy("5"));
    await flush();
    // the freed slot is not used while the server is busy
    expect(pending).toHaveLength(4);
    await act(() => vi.advanceTimersByTimeAsync(4999));
    expect(pending).toHaveLength(4);
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(pending[4]?.url).toBe("a"); // retried first, ahead of "e"
    pending[4]!.resolve(svg());
    expect((await loads[0])?.size).toBe(6);
  });

  it("caps the wait at 30 s and defaults to 5 s without Retry-After", async () => {
    vi.useFakeTimers();
    const loader = createDepictionLoader();
    void loader.load("a");
    pending[0]!.resolve(busy("600"));
    await flush();
    await act(() => vi.advanceTimersByTimeAsync(29999));
    expect(pending).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(pending).toHaveLength(2);
    pending[1]!.resolve(busy());
    await flush();
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(pending).toHaveLength(3);
  });

  it("gives up after 6 attempts with the ApiError", async () => {
    vi.useFakeTimers();
    const loader = createDepictionLoader();
    const load = loader.load("a");
    const outcome = load.catch((e: unknown) => e);
    for (let i = 0; i < 6; i++) {
      pending[i]!.resolve(busy("1"));
      await flush();
      await act(() => vi.advanceTimersByTimeAsync(1000));
    }
    const err = await outcome;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(503);
    expect(pending).toHaveLength(6);
  });

  it("a 404 fails at once", async () => {
    const loader = createDepictionLoader();
    const load = loader.load("a");
    pending[0]!.resolve(new Response('{"detail":"Not found"}', { status: 404 }));
    await expect(load).rejects.toMatchObject({ status: 404 });
  });

  it("an aborted queued load never fetches and frees its place", async () => {
    const loader = createDepictionLoader({ maxActive: 1 });
    void loader.load("a");
    const ctrl = new AbortController();
    const b = loader.load("b", ctrl.signal);
    ctrl.abort();
    await expect(b).rejects.toMatchObject({ name: "AbortError" });
    void loader.load("c");
    pending[0]!.resolve(svg());
    await flush();
    expect(pending.map((p) => p.url)).toEqual(["a", "c"]);
  });
});

describe("useDepiction", () => {
  it("gives a blob URL once loaded and revokes it on unmount", async () => {
    const revoked: string[] = [];
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: () => "blob:svg-1",
      revokeObjectURL: (u: string) => revoked.push(u),
    });
    const hook = renderHook(() => useDepiction("/api/v2/segments/s1/depiction?v=k"));
    expect(hook.result.current).toEqual({ src: null, failed: false });
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]!.resolve(svg());
    await waitFor(() => expect(hook.result.current.src).toBe("blob:svg-1"));
    hook.unmount();
    expect(revoked).toEqual(["blob:svg-1"]);
  });

  it("reports failure and aborts on unmount", async () => {
    const hook = renderHook(() => useDepiction("/x"));
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]!.resolve(new Response(null, { status: 404 }));
    await waitFor(() => expect(hook.result.current.failed).toBe(true));
    const other = renderHook(() => useDepiction("/y"));
    await waitFor(() => expect(pending).toHaveLength(2));
    other.unmount();
    expect(pending[1]?.signal?.aborted).toBe(true);
  });

  it("null url loads nothing", () => {
    const hook = renderHook(() => useDepiction(null));
    expect(hook.result.current).toEqual({ src: null, failed: false });
    expect(pending).toHaveLength(0);
  });
});
