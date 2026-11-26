import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";
import {
  createDepictionLoader,
  createDrawingCache,
  depictQuery,
  forgetDrawings,
  useDepiction,
} from "./depictions";

// The tab's loader waits for the owner gate; here a gated request has already succeeded.
vi.mock("./client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./client")>()),
  ownerReady: () => Promise.resolve(),
}));

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
  forgetDrawings();
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

  it("busy replies do not count as attempts: ten 503s, then a 200, and it loads (B-I2)", async () => {
    vi.useFakeTimers();
    const loader = createDepictionLoader();
    const load = loader.load("a");
    for (let i = 0; i < 10; i++) {
      pending[i]!.resolve(busy("5"));
      await flush();
      await act(() => vi.advanceTimersByTimeAsync(5000));
    }
    pending[10]!.resolve(svg());
    expect((await load).size).toBe(6);
  });

  it("gives up on a busy server only after 5 minutes of waiting, with the ApiError", async () => {
    vi.useFakeTimers();
    const loader = createDepictionLoader();
    const outcome = loader.load("a").catch((e: unknown) => e);
    let settled = false;
    void outcome.then(() => (settled = true));
    // 30 s pauses: the 10th busy reply comes at 4.5 min, and another 30 s would pass 5.
    for (let i = 0; i < 10; i++) {
      pending[i]!.resolve(busy("30"));
      await flush();
      expect(settled).toBe(false);
      await act(() => vi.advanceTimersByTimeAsync(30_000));
    }
    pending[10]!.resolve(busy("30"));
    await flush();
    const err = await outcome;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(503);
    expect(pending).toHaveLength(11);
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

describe("owner gate", () => {
  it("a gated loader fetches nothing until the gate opens", async () => {
    let open!: () => void;
    const gate = new Promise<void>((r) => (open = r));
    const loader = createDepictionLoader({ gate: () => gate });
    const blob = loader.load("a");
    await flush();
    expect(pending).toHaveLength(0);
    open();
    await flush();
    expect(pending.map((p) => p.url)).toEqual(["a"]);
    pending[0]!.resolve(svg());
    await expect(blob).resolves.toHaveProperty("size", 6);
  });
});

describe("createDrawingCache", () => {
  it("keeps drawings in use, keeps up to maxIdle unused ones, revokes the oldest beyond", () => {
    const revoked: string[] = [];
    let n = 0;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: () => `blob:${++n}`,
      revokeObjectURL: (u: string) => revoked.push(u),
    });
    const cache = createDrawingCache(2);
    const blob = new Blob(["<svg/>"]);
    const a = cache.take("/a", blob)!;
    const b = cache.take("/b", blob)!;
    const c = cache.take("/c", blob)!;
    const d = cache.take("/d", blob)!;
    cache.release("/a", a);
    cache.release("/b", b);
    cache.release("/c", c); // three idle: the oldest (a) goes
    expect(revoked).toEqual(["blob:1"]);
    expect(cache.get("/a")).toBeUndefined();
    expect(cache.take("/b")).toBe(b); // b in use again: c is now the oldest idle
    cache.release("/d", d); // idle: c, d
    expect(revoked).toEqual(["blob:1"]);
    cache.release("/b", b); // idle: c, d, b: c goes, b (in use until now) stays
    expect(revoked).toEqual(["blob:1", "blob:3"]);
    expect(cache.get("/b")?.src).toBe("blob:2");
    expect(cache.get("/d")?.src).toBe("blob:4");
  });
});

describe("useDepiction", () => {
  it("gives a blob URL once loaded, and the same one at once to the next view of it", async () => {
    const revoked: string[] = [];
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: () => "blob:svg-1",
      revokeObjectURL: (u: string) => revoked.push(u),
    });
    const url = "/api/v2/segments/s1/depiction?v=k";
    const hook = renderHook(() => useDepiction(url));
    expect(hook.result.current).toMatchObject({ src: null, failed: false });
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]!.resolve(svg());
    await waitFor(() => expect(hook.result.current.src).toBe("blob:svg-1"));
    hook.unmount();
    expect(revoked).toEqual([]); // kept for the tab
    const again = renderHook(() => useDepiction(url));
    expect(again.result.current.src).toBe("blob:svg-1");
    expect(pending).toHaveLength(1);
    again.unmount();
    forgetDrawings();
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

  it("a drawing not loaded (busy too long, network) offers retry, which loads it again", async () => {
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:svg-2", revokeObjectURL: () => {} });
    const hook = renderHook(() => useDepiction("/z"));
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]!.resolve(new Response('{"detail":"bad gateway"}', { status: 500 }));
    await waitFor(() => expect(hook.result.current.failed).toBe(true));
    expect(hook.result.current.retry).toBeTypeOf("function");
    act(() => hook.result.current.retry!());
    expect(hook.result.current).toMatchObject({ src: null, failed: false });
    await waitFor(() => expect(pending).toHaveLength(2));
    pending[1]!.resolve(svg());
    await waitFor(() => expect(hook.result.current.src).toBe("blob:svg-2"));
  });

  it("nothing to draw (404, 422) offers no retry", async () => {
    const hook = renderHook(() => useDepiction("/n"));
    await waitFor(() => expect(pending).toHaveLength(1));
    pending[0]!.resolve(new Response(null, { status: 422 }));
    await waitFor(() => expect(hook.result.current.failed).toBe(true));
    expect(hook.result.current.retry).toBeNull();
  });

  it("null url loads nothing", () => {
    const hook = renderHook(() => useDepiction(null));
    expect(hook.result.current).toMatchObject({ src: null, failed: false });
    expect(pending).toHaveLength(0);
  });
});

describe("depictQuery marks", () => {
  it("sends the marks with the layout template and keys the drawing by both; none: the plain key", async () => {
    const depict = vi.spyOn(api, "depict").mockResolvedValue({ format: "svg", data: "<svg/>" });
    const marked = depictQuery("CCO", null, undefined, null, { marks: [2, 0] });
    await marked.queryFn();
    expect(depict).toHaveBeenCalledWith("CCO", { marks: [2, 0] });
    expect(marked.queryKey).toEqual(["depict", "CCO", null, "glow", "2,0", ""]);
    expect(depictQuery("CCO", null, undefined, null, { marks: [] }).queryKey).toEqual(["depict", "CCO", null]);
    const both = depictQuery("CCO", null, undefined, { id: "p:layout", molfile: "L" }, { marks: [1] });
    await both.queryFn();
    expect(depict).toHaveBeenLastCalledWith("CCO", { marks: [1], template: "L" });
    expect(both.queryKey).toEqual(["depict", "CCO", null, "p:layout", "glow", "1", ""]);
    depict.mockRestore();
  });
});
