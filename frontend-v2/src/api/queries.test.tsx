import { QueryClient, QueryClientProvider, QueryObserver } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";
import { depictionKey } from "./depictionKey";
import {
  createQueryClient,
  keys,
  LIST_POLL_MS,
  refreshPaper,
  SEGMENT_GONE,
  snapshotIsCached,
  useImages,
  usePapers,
  useSaveCuration,
} from "./queries";
import type { CurationIn, CurationOut, PaperDetail, StepList } from "./types";

function paper(curation: CurationOut | null): PaperDetail {
  return {
    id: "p1",
    display_name: "a.pdf",
    status: "done",
    pages: 1,
    doi: null,
    title: null,
    first_author: null,
    year: null,
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T00:00:00Z",
    expires_at: "2026-12-18T00:00:00Z",
    structures: 2,
    accepted: 0,
    rejected: 0,
    to_review: 2,
    failed_pages: 0,
    failed: 0,
    annotating: false,
    pages_read: 0,
    structures_total: 0,
    structures_read: 0,
    text_read: false,
    check_started: false,
    rereading: false,
    counts: { steps_by_status: {} },
    segments: [
      { id: "s1", page: 0, idx: 0, bbox: [0, 0, 1, 1], curation, predictions: [] },
      { id: "s2", page: 0, idx: 1, bbox: [0, 0, 1, 1], curation: null, predictions: [] },
    ],
  };
}

let client: QueryClient;
let sent: { id: string; body: CurationIn }[];

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  client = createQueryClient();
  sent = [];
  vi.spyOn(api, "putCuration").mockImplementation(async (id, body) => {
    sent.push({ id, body });
    return { ...body };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  client.clear();
});

describe("useSaveCuration", () => {
  it("builds on the cached curation and writes the reply back into the cache", async () => {
    client.setQueryData(
      keys.paper("p1"),
      paper({ status: "unchecked", smiles: "CCN", molfile: null, note: "edited" }),
    );
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(() => result.current.save("s1", { status: "accepted" }));
    expect(sent[0]).toEqual({
      id: "s1",
      body: { status: "accepted", smiles: "CCN", molfile: null, note: "edited" },
    });
    const cached = client.getQueryData<PaperDetail>(keys.paper("p1"));
    expect(cached?.segments[0]?.curation?.status).toBe("accepted");
    expect(cached?.segments[1]?.curation).toBeNull();
  });

  it("chains saves for one segment: the second builds on the first's reply", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(async () => {
      const a = result.current.save("s1", { structure: { smiles: "CCO", molfile: null } });
      const b = result.current.save("s1", { status: "accepted" });
      await Promise.all([a, b]);
    });
    expect(sent.map((s) => s.body)).toEqual([
      { status: "unchecked", smiles: "CCO", molfile: null, note: null },
      { status: "accepted", smiles: "CCO", molfile: null, note: null },
    ]);
  });

  it("chains across two hook instances of the same client", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const one = renderHook(() => useSaveCuration("p1"), { wrapper });
    const two = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(async () => {
      await Promise.all([
        one.result.current.save("s1", { note: "kept" }),
        two.result.current.save("s1", { status: "rejected" }),
      ]);
    });
    expect(sent[1]?.body).toEqual({
      status: "rejected",
      smiles: null,
      molfile: null,
      note: "kept",
    });
  });

  it("a failed save rejects, leaves the cache alone, and does not block the next one", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    vi.mocked(api.putCuration).mockRejectedValueOnce(new ApiError(422, "bad SMILES"));
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(async () => {
      const a = result.current.save("s1", { structure: { smiles: "C1", molfile: null } });
      const b = result.current.save("s1", { status: "accepted" });
      await expect(a).rejects.toThrow("bad SMILES");
      await b;
    });
    expect(sent).toEqual([
      { id: "s1", body: { status: "accepted", smiles: null, molfile: null, note: null } },
    ]);
  });
});

describe("useSaveCuration optimistic write", () => {
  const cached = (id = "s1") =>
    client.getQueryData<PaperDetail>(keys.paper("p1"))!.segments.find((s) => s.id === id)!;

  function holdPuts() {
    const held: { id: string; resolve: () => void; reject: (e: unknown) => void }[] = [];
    vi.mocked(api.putCuration).mockImplementation(
      (id, body) =>
        new Promise((resolve, reject) =>
          held.push({ id, resolve: () => resolve({ ...body }), reject }),
        ),
    );
    return held;
  }

  it("a status shows at once and a failed PUT takes it back; another segment keeps its own", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    let one!: Promise<unknown>;
    let two!: Promise<unknown>;
    await act(async () => {
      one = result.current.save("s1", { status: "accepted" }).catch((e: unknown) => e);
      two = result.current.save("s2", { status: "rejected" });
      await vi.waitFor(() => expect(held).toHaveLength(2));
    });
    expect(cached("s1").curation?.status).toBe("accepted");
    expect(cached("s2").curation?.status).toBe("rejected");
    await act(async () => {
      held.find((h) => h.id === "s1")!.reject(new ApiError(500, "boom"));
      held.find((h) => h.id === "s2")!.resolve();
      await Promise.all([one, two]);
    });
    expect(cached("s1").curation).toBeNull();
    expect(cached("s2").curation?.status).toBe("rejected");
  });

  it("a new structure is cached only with the reply; a failed one leaves the drawing key", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const key = depictionKey(cached());
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    const structure = { smiles: "CCN", molfile: null };
    let first!: Promise<unknown>;
    await act(async () => {
      first = result.current.save("s1", { status: "accepted", structure });
      await vi.waitFor(() => expect(held).toHaveLength(1));
    });
    expect(cached().curation).toBeNull(); // nothing written before the PUT saved
    await act(async () => {
      held[0]!.resolve();
      await first;
    });
    expect(cached().curation).toMatchObject({ status: "accepted", smiles: "CCN" });

    const saved = depictionKey(cached());
    let second!: Promise<unknown>;
    await act(async () => {
      second = result.current
        .save("s1", { structure: { smiles: "CCO", molfile: null } })
        .catch((e: unknown) => e);
      await vi.waitFor(() => expect(held).toHaveLength(2));
    });
    expect(depictionKey(cached())).toBe(saved);
    await act(async () => {
      held[1]!.reject(new ApiError(422, "bad SMILES"));
      await second;
    });
    expect(depictionKey(cached())).toBe(saved);
    expect(saved).not.toBe(key);
  });

  it("a save that times out rolls back, then the held refresh runs", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const getPaper = vi.spyOn(api, "getPaper").mockResolvedValue(paper(null));
    const stop = new QueryObserver(client, {
      queryKey: keys.paper("p1"),
      queryFn: () => api.getPaper("p1"),
      staleTime: Infinity,
    }).subscribe(() => undefined);
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    let saving!: Promise<unknown>;
    await act(async () => {
      saving = result.current.save("s1", { status: "accepted" }).catch((e: unknown) => e);
      await vi.waitFor(() => expect(held).toHaveLength(1));
    });
    getPaper.mockClear();
    refreshPaper(client, "p1");
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(getPaper).not.toHaveBeenCalled(); // held while the PUT is on the wire
    await act(async () => {
      held[0]!.reject(new ApiError(504, "The server is busy, try again in a moment."));
      await saving;
    });
    expect(cached().curation).toBeNull(); // rolled back
    await vi.waitFor(() => expect(getPaper).toHaveBeenCalledTimes(1), { timeout: 3000 });
    stop();
  });

  it("a timed-out save fetches the paper again on its own: the PUT may have been saved", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const getPaper = vi.spyOn(api, "getPaper").mockResolvedValue(
      paper({ status: "accepted", smiles: null, molfile: null, note: null } as CurationOut),
    );
    const stop = new QueryObserver(client, {
      queryKey: keys.paper("p1"),
      queryFn: () => api.getPaper("p1"),
      staleTime: Infinity,
    }).subscribe(() => undefined);
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    let saving!: Promise<unknown>;
    await act(async () => {
      saving = result.current.save("s1", { status: "accepted" }).catch((e: unknown) => e);
      await vi.waitFor(() => expect(held).toHaveLength(1));
    });
    getPaper.mockClear();
    await act(async () => {
      held[0]!.reject(new ApiError(504, "The server is busy, try again in a moment."));
      await saving;
    });
    await vi.waitFor(() => expect(getPaper).toHaveBeenCalledTimes(1), { timeout: 3000 });
    await vi.waitFor(() => expect(cached().curation?.status).toBe("accepted")); // the server's
    stop();
  });

  it("a save the server refused (4xx) is not fetched again", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const getPaper = vi.spyOn(api, "getPaper").mockResolvedValue(paper(null));
    const stop = new QueryObserver(client, {
      queryKey: keys.paper("p1"),
      queryFn: () => api.getPaper("p1"),
      staleTime: Infinity,
    }).subscribe(() => undefined);
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    let saving!: Promise<unknown>;
    await act(async () => {
      saving = result.current.save("s1", { status: "accepted" }).catch((e: unknown) => e);
      await vi.waitFor(() => expect(held).toHaveLength(1));
    });
    getPaper.mockClear();
    await act(async () => {
      held[0]!.reject(new ApiError(422, "bad"));
      await saving;
    });
    await act(() => new Promise((r) => setTimeout(r, 1500)));
    expect(getPaper).not.toHaveBeenCalled();
    stop();
  });

  it("a refresh asked for while a save is on the wire waits for it", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const getPaper = vi.spyOn(api, "getPaper").mockResolvedValue(paper(null));
    const stop = new QueryObserver(client, {
      queryKey: keys.paper("p1"),
      queryFn: () => api.getPaper("p1"),
      staleTime: Infinity,
    }).subscribe(() => undefined);
    const held = holdPuts();
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    let saving!: Promise<unknown>;
    await act(async () => {
      saving = result.current.save("s1", { status: "accepted" });
      await vi.waitFor(() => expect(held).toHaveLength(1));
    });
    getPaper.mockClear();
    refreshPaper(client, "p1");
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(getPaper).not.toHaveBeenCalled();
    expect(cached().curation?.status).toBe("accepted");
    await act(async () => {
      held[0]!.resolve();
      await saving;
    });
    await vi.waitFor(() => expect(getPaper).toHaveBeenCalled(), { timeout: 3000 });
    stop();
  });
});

describe("useSaveCuration without a cached paper", () => {
  it("fetches the paper first and builds on its stored curation", async () => {
    const stored = { status: "accepted", smiles: "CCN", molfile: "M  END", note: "kept" } as const;
    const getPaper = vi.spyOn(api, "getPaper").mockResolvedValue(paper({ ...stored }));
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(() => result.current.save("s1", { status: "rejected" }));
    expect(getPaper).toHaveBeenCalledTimes(1);
    expect(sent).toEqual([{ id: "s1", body: { ...stored, status: "rejected" } }]);
  });

  it("refuses, sending nothing, when the segment is not in the paper", async () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(async () => {
      await expect(result.current.save("gone", { status: "accepted" })).rejects.toThrow(
        SEGMENT_GONE,
      );
    });
    expect(sent).toEqual([]);
  });

  it("refuses when the paper cannot be fetched", async () => {
    vi.spyOn(api, "getPaper").mockRejectedValue(new ApiError(404, "Not found"));
    const { result } = renderHook(() => useSaveCuration("p1"), { wrapper });
    await act(async () => {
      await expect(result.current.save("s1", { status: "accepted" })).rejects.toThrow(
        "Not found",
      );
    });
    expect(sent).toEqual([]);
  });
});

describe("snapshotIsCached", () => {
  const step = (status: string) => ({ status }) as StepList["steps"][number];

  it("is true only when the stream's status and step counts are what the cache holds", () => {
    client.setQueryData(keys.paper("p1"), paper(null));
    client.setQueryData<StepList>(keys.steps("p1"), {
      steps: [step("done"), step("done"), step("running")],
    });
    const snap = (status: string, counts: Record<string, number>) => ({
      status,
      counts: { steps_by_status: counts },
    });
    expect(snapshotIsCached(client, "p1", snap("done", { done: 2, running: 1, failed: 0 }))).toBe(
      true,
    );
    expect(snapshotIsCached(client, "p1", snap("done", { done: 3 }))).toBe(false);
    expect(snapshotIsCached(client, "p1", snap("processing", { done: 2, running: 1 }))).toBe(
      false,
    );
    expect(snapshotIsCached(client, "p1", null)).toBe(false);
    expect(snapshotIsCached(client, "p2", snap("done", {}))).toBe(false); // nothing cached
  });
});

describe("refreshPaper", () => {
  const steps: StepList = { steps: [] };
  let paperCalls: number[];
  let stepCalls: number;
  let hold: { resolve: () => void } | null;

  beforeEach(() => {
    vi.useFakeTimers();
    paperCalls = [];
    stepCalls = 0;
    hold = null;
    vi.spyOn(api, "getPaper").mockImplementation(async () => {
      paperCalls.push(Date.now());
      if (hold === null) return paper(null);
      return new Promise<PaperDetail>((resolve) => {
        hold = { resolve: () => resolve(paper(null)) };
      });
    });
    vi.spyOn(api, "getSteps").mockImplementation(async () => {
      stepCalls += 1;
      return steps;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function watchPaper() {
    // two mounted observers, as the workspace has
    const stops = [
      new QueryObserver(client, {
        queryKey: keys.paper("p1"),
        queryFn: () => api.getPaper("p1"),
      }).subscribe(() => undefined),
      new QueryObserver(client, {
        queryKey: keys.steps("p1"),
        queryFn: () => api.getSteps("p1"),
      }).subscribe(() => undefined),
    ];
    await vi.advanceTimersByTimeAsync(0);
    paperCalls = [];
    stepCalls = 0;
    return () => stops.forEach((stop) => stop());
  }

  it("a burst of 20 events within 1 s makes at most 2 paper fetches, one after the last event", async () => {
    const stop = await watchPaper();
    let lastEvent = 0;
    for (let i = 0; i < 20; i++) {
      lastEvent = Date.now();
      refreshPaper(client, "p1");
      await vi.advanceTimersByTimeAsync(50);
    }
    await vi.advanceTimersByTimeAsync(3000);
    expect(paperCalls.length).toBeGreaterThanOrEqual(1);
    expect(paperCalls.length).toBeLessThanOrEqual(2);
    expect(stepCalls).toBeLessThanOrEqual(2);
    expect(paperCalls.at(-1)!).toBeGreaterThanOrEqual(lastEvent);
    stop();
  });

  it("never starts a second fetch while one is on the wire, and refetches after it", async () => {
    const stop = await watchPaper();
    hold = { resolve: () => undefined }; // the next getPaper hangs
    refreshPaper(client, "p1");
    await vi.advanceTimersByTimeAsync(0);
    expect(paperCalls).toHaveLength(1);
    for (let i = 0; i < 5; i++) {
      refreshPaper(client, "p1");
      await vi.advanceTimersByTimeAsync(700);
    }
    expect(paperCalls).toHaveLength(1);
    const release = hold;
    hold = null;
    release.resolve();
    await vi.advanceTimersByTimeAsync(2000);
    expect(paperCalls).toHaveLength(2);
    stop();
  });

  it("a single event refreshes at once", async () => {
    const stop = await watchPaper();
    refreshPaper(client, "p1");
    await vi.advanceTimersByTimeAsync(0);
    expect(paperCalls).toHaveLength(1);
    expect(stepCalls).toBe(1);
    stop();
  });
});

describe("createQueryClient", () => {
  it("does not retry 4xx ApiErrors but retries 5xx once", () => {
    const retry = createQueryClient().getDefaultOptions().queries?.retry as (
      n: number,
      e: unknown,
    ) => boolean;
    expect(retry(0, new ApiError(404, "x"))).toBe(false);
    expect(retry(0, new ApiError(503, "x"))).toBe(true);
    expect(retry(1, new ApiError(503, "x"))).toBe(false);
  });
});

describe("usePapers and useImages poll only while an item is being worked on", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  async function ticks(n: number) {
    for (let i = 0; i < n; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(LIST_POLL_MS);
      });
    }
  }

  it("refetches the papers every 5 s while one is processing, then stops", async () => {
    vi.useFakeTimers();
    const list = vi
      .spyOn(api, "listPapers")
      .mockResolvedValueOnce({ papers: [{ ...paper(null), status: "processing" }] })
      .mockResolvedValue({ papers: [paper(null)] });
    renderHook(() => usePapers(), { wrapper });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(list).toHaveBeenCalledTimes(1);
    await ticks(1);
    expect(list).toHaveBeenCalledTimes(2); // processing: polled
    await ticks(3);
    expect(list).toHaveBeenCalledTimes(2); // all done: no more polls
  });

  it("refetches the image jobs while one is queued", async () => {
    vi.useFakeTimers();
    const job = {
      id: "i1",
      display_name: "a.png",
      status: "queued",
      engine: "decimer",
      created_at: "2026-11-18T00:00:00Z",
      expires_at: "2026-12-18T00:00:00Z",
    };
    const list = vi
      .spyOn(api, "listImages")
      .mockResolvedValueOnce({ jobs: [job] })
      .mockResolvedValue({ jobs: [{ ...job, status: "done" }] });
    renderHook(() => useImages(), { wrapper });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await ticks(3);
    expect(list).toHaveBeenCalledTimes(2);
  });
});
