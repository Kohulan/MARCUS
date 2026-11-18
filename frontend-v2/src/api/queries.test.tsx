import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";
import { createQueryClient, keys, useSaveCuration } from "./queries";
import type { CurationIn, CurationOut, PaperDetail } from "./types";

function paper(curation: CurationOut | null): PaperDetail {
  return {
    id: "p1",
    display_name: "a.pdf",
    status: "done",
    pages: 1,
    doi: null,
    title: null,
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T00:00:00Z",
    expires_at: "2026-12-18T00:00:00Z",
    structures: 2,
    accepted: 0,
    rejected: 0,
    to_review: 2,
    failed_pages: 0,
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
