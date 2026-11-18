// Review grid (/app/papers/:id, review view): structure cards with their state word and
// shape, filters with counts, selection and bulk accept / reject (no `note` key, chunks of
// 500, rollback on error), engine actions for failed and not-read cards, live cards, and
// hostile notes and SMILES as text.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient, keys, useBulkCuration } from "../api/queries";
import type {
  BulkCurationItem,
  CurationOut,
  PaperDetail,
  PredictionOut,
  SegmentOut,
  StepOut,
} from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import { cardState } from "./cardState";
import Workspace from "./Workspace";

// The live stream is mocked: the test fires its onEvent (a hint to refetch) by hand.
const live = vi.hoisted(() => ({
  onEvent: (() => undefined) as () => void,
  reconnect: (() => undefined) as () => void,
}));

vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: (_kind: string, _id: string, onEvent: () => void) => {
    live.onEvent = onEvent;
    return { mode: "live", reconnect: live.reconnect };
  },
}));

// Depictions: the src is the depiction URL itself (the real loader is tested on its own).
vi.mock("../api/depictions", () => ({
  useDepiction: (url: string | null) => ({ src: url, failed: false }),
}));

const XSS = "<img src=x onerror=window.__xss=1>";
const ID = "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f";

let pseq = 0;
function prediction(over: Partial<PredictionOut> = {}): PredictionOut {
  pseq += 1;
  return {
    id: `pr${pseq}`,
    engine: "decimer",
    engine_version: "2.7",
    smiles: "CCO",
    molfile: null,
    valid: true,
    ms: 120,
    cached: false,
    created_at: "2026-11-18T10:00:00Z",
    ...over,
  };
}

function curation(over: Partial<CurationOut> = {}): CurationOut {
  return { status: "unchecked", smiles: null, molfile: null, note: null, ...over };
}

function segment(id: string, over: Partial<SegmentOut> = {}): SegmentOut {
  const n = Number(id.replace(/\D/g, "")) || 0;
  return {
    id,
    page: 0,
    idx: n,
    bbox: [0, 0, 10, 10],
    curation: null,
    predictions: [prediction()],
    ...over,
  };
}

function paper(segments: SegmentOut[], over: Partial<PaperDetail> = {}): PaperDetail {
  return {
    id: ID,
    display_name: "alkaloids.pdf",
    status: "done",
    pages: 3,
    doi: null,
    title: "Alkaloids",
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: segments.length,
    accepted: segments.filter((s) => s.curation?.status === "accepted").length,
    rejected: segments.filter((s) => s.curation?.status === "rejected").length,
    to_review: segments.filter((s) => (s.curation?.status ?? "unchecked") === "unchecked").length,
    failed_pages: 0,
    counts: { steps_by_status: {} },
    segments,
    ...over,
  };
}

let sseq = 0;
function step(over: Partial<StepOut>): StepOut {
  sseq += 1;
  return {
    id: `st${sseq}`,
    kind: "ocsr",
    page: 0,
    segment_id: null,
    status: "done",
    attempts: 1,
    error_class: null,
    engine: "decimer",
    created_at: `2026-11-18T10:00:${String(sseq % 60).padStart(2, "0")}.000000Z`,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

let client: QueryClient;

function renderGrid(p: PaperDetail, steps: StepOut[] = []) {
  vi.spyOn(api, "getPaper").mockResolvedValue(p);
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps });
  vi.spyOn(api, "getQueue").mockResolvedValue({ papers: [], estimate_s: 0 });
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/app/papers/${ID}`]}>
          <Routes>
            <Route path="/app/papers/:id" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const cards = () => screen.queryAllByRole("article");
const card = (tag: string) => {
  const found = cards().find((c) => c.getAttribute("aria-label")?.startsWith(tag));
  if (!found) throw new Error(`no card ${tag}`);
  return found;
};
const filter = (label: string) =>
  within(screen.getByRole("group", { name: "Filter" })).getByRole("button", {
    name: new RegExp(`^${label}`),
  });

beforeEach(() => {
  live.reconnect = vi.fn();
  live.onEvent = () => undefined;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  delete (window as { __xss?: unknown }).__xss;
});

describe("cards and their states", () => {
  it("an accepted, a rejected and an unchecked segment show two stamps and one To check", async () => {
    renderGrid(
      paper([
        segment("s1", { curation: curation({ status: "accepted" }) }),
        segment("s2", { curation: curation({ status: "rejected" }) }),
        segment("s3"),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(screen.getAllByRole("img", { name: "Accepted" })).toHaveLength(1);
    expect(screen.getAllByRole("img", { name: "Rejected" })).toHaveLength(1);
    expect(within(card("[03]")).getByText("To check")).toBeInTheDocument();
    expect(card("[03]")).toHaveTextContent("[03] · Page 1");
    // the rejected SMILES is struck through
    expect(within(card("[02]")).getByText("CCO").closest(".smiles")).toHaveClass("smiles--struck");
    // a To check card offers Accept and Reject with their keys
    expect(within(card("[03]")).getByRole("button", { name: /Accept/ })).toHaveTextContent("A");
    expect(within(card("[03]")).getByRole("button", { name: /Reject/ })).toHaveTextContent("R");
  });

  it("tags follow (page, idx) order, and two engines that differ say so", async () => {
    renderGrid(
      paper([
        segment("s9", { page: 1, idx: 0 }),
        segment("s1", {
          page: 0,
          idx: 0,
          predictions: [prediction({ smiles: "CCO" }), prediction({ engine: "molnextr", smiles: "CCN" })],
        }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(cards()[0]).toHaveTextContent("[01] · Page 1");
    expect(cards()[1]).toHaveTextContent("[02] · Page 2");
    expect(within(cards()[0]!).getByText("Engines differ")).toBeInTheDocument();
    expect(within(cards()[1]!).queryByText("Engines differ")).toBeNull();
  });

  it("filter Accepted shows 1 card; each filter shows its count", async () => {
    renderGrid(
      paper([
        segment("s1", { curation: curation({ status: "accepted" }) }),
        segment("s2", { curation: curation({ status: "rejected" }) }),
        segment("s3"),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(filter("All")).toHaveTextContent("3");
    expect(filter("To check")).toHaveTextContent("1");
    expect(filter("Failed")).toHaveTextContent("0");
    fireEvent.click(filter("Accepted"));
    expect(filter("Accepted")).toHaveAttribute("aria-pressed", "true");
    expect(cards()).toHaveLength(1);
    expect(cards()[0]).toHaveAccessibleName(/^\[01\]/);
  });

  it("a segment without a prediction and a running OCSR step shows Reading…", async () => {
    renderGrid(paper([segment("s1", { predictions: [] })], { status: "processing" }), [
      step({ segment_id: "s1", status: "running" }),
    ]);
    await waitFor(() => expect(cards()).toHaveLength(1));
    await waitFor(() => expect(within(card("[01]")).getByText("Reading…")).toBeInTheDocument());
    expect(filter("To check")).toHaveTextContent("1");
  });

  it("a failed OCSR step shows Failed, its reason and Try another engine", async () => {
    const run = vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "x" });
    renderGrid(paper([segment("s1", { predictions: [] })]), [
      step({ segment_id: "s1", status: "failed", error_class: "timeout" }),
    ]);
    await waitFor(() => expect(within(card("[01]")).getByText("Failed")).toBeInTheDocument());
    expect(card("[01]")).toHaveTextContent("It took too long");
    expect(filter("Failed")).toHaveTextContent("1");
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "Try another engine" }));
    const menu = within(card("[01]")).getByRole("group", { name: "Engines" });
    // the other three engines, not the one that failed
    expect(within(menu).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "DECIMER hand-drawn",
      "MolNexTR",
      "MolScribe",
    ]);
    fireEvent.click(within(menu).getByRole("button", { name: "MolNexTR" }));
    await waitFor(() => expect(run).toHaveBeenCalledWith("s1", "molnextr"));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
  });

  it("a paper read with ocsr off shows Not read yet and Read with DECIMER", async () => {
    const run = vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "x" });
    renderGrid(paper([segment("s1", { predictions: [] })], { ocsr_mode: "off" }));
    await waitFor(() => expect(within(card("[01]")).getByText("Not read yet")).toBeInTheDocument());
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "Read with DECIMER" }));
    await waitFor(() => expect(run).toHaveBeenCalledWith("s1", "decimer"));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
  });

  it("a note and an invalid predicted SMILES that look like markup render as text", async () => {
    renderGrid(
      paper([
        segment("s1", {
          curation: curation({ note: `${XSS}\nsecond line` }),
          predictions: [prediction({ smiles: XSS, valid: false })],
        }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(card("[01]")).toHaveTextContent(XSS);
    expect(card("[01]")).not.toHaveTextContent("second line"); // first line only
    expect(card("[01]").querySelector('img[src="x"]')).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect((window as { __xss?: unknown }).__xss).toBeUndefined();
  });

  it("a card's depiction src changes after its curated SMILES changes in the cache", async () => {
    renderGrid(paper([segment("s1")]));
    await waitFor(() => expect(cards()).toHaveLength(1));
    const img = () => within(card("[01]")).getByRole("img", { name: /^Structure/ });
    const before = img().getAttribute("src");
    expect(before).toMatch(/\/segments\/s1\/depiction\?v=/);
    act(() =>
      client.setQueryData<PaperDetail>(keys.paper(ID), (old) => ({
        ...old!,
        segments: old!.segments.map((s) => ({ ...s, curation: curation({ smiles: "CCN" }) })),
      })),
    );
    await waitFor(() => expect(img().getAttribute("src")).not.toBe(before));
  });

  it("a live event that adds a segment makes a new card appear", async () => {
    renderGrid(paper([segment("s1")], { status: "processing" }));
    await waitFor(() => expect(cards()).toHaveLength(1));
    vi.mocked(api.getPaper).mockResolvedValue(
      paper([segment("s1"), segment("s2")], { status: "processing" }),
    );
    act(() => live.onEvent());
    await waitFor(() => expect(cards()).toHaveLength(2));
  });

  it("Enter on a card opens it in focus mode (the focused segment goes into the URL)", async () => {
    renderGrid(paper([segment("s1"), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(card("[02]")).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(card("[02]"), { key: "Enter" });
    expect(await screen.findByRole("region", { name: "Focus [02]" })).toBeInTheDocument();
  });
});

describe("selection and bulk review", () => {
  it("select 2 + Accept 2 sends one bulk call with both ids and no note key", async () => {
    let answer: () => void = () => undefined;
    const bulk = vi.spyOn(api, "putBulkCuration").mockImplementation(
      () => new Promise((resolve) => (answer = () => resolve({ updated: 2 }))),
    );
    renderGrid(
      paper([
        segment("s1", { curation: curation({ note: "keep me" }) }),
        segment("s2"),
        segment("s3"),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [01]" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [02]" }));
    fireEvent.click(screen.getByRole("button", { name: "Accept 2" }));
    await waitFor(() => expect(bulk).toHaveBeenCalledTimes(1));
    const items = bulk.mock.calls[0]![1];
    expect(bulk.mock.calls[0]![0]).toBe(ID);
    expect(items).toEqual([
      { segment_id: "s1", status: "accepted" },
      { segment_id: "s2", status: "accepted" },
    ]);
    for (const item of items) expect(Object.hasOwn(item, "note")).toBe(false);
    // optimistic: two stamps before the server answers, and the note stays in the cache
    expect(screen.getAllByRole("img", { name: "Accepted" })).toHaveLength(2);
    const cached = client.getQueryData<PaperDetail>(keys.paper(ID))!;
    expect(cached.segments.find((s) => s.id === "s1")!.curation?.note).toBe("keep me");
    expect(cached.accepted).toBe(2);
    await act(async () => answer());
    await waitFor(() => expect(screen.queryByRole("button", { name: "Accept 2" })).toBeNull());
  });

  it("Shift-click selects a range; Select all shown selects every shown card; Clear empties it", async () => {
    renderGrid(paper([segment("s1"), segment("s2"), segment("s3"), segment("s4")]));
    await waitFor(() => expect(cards()).toHaveLength(4));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [01]" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [03]" }), { shiftKey: true });
    expect(screen.getByRole("button", { name: "Accept 3" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("button", { name: /^Accept \d/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Select all shown" }));
    expect(screen.getByRole("button", { name: "Reject 4" })).toBeInTheDocument();
  });

  it("an API error rolls back and toasts", async () => {
    vi.spyOn(api, "putBulkCuration").mockRejectedValue(new ApiError(500, "Server error."));
    renderGrid(paper([segment("s1"), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [01]" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject 1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not saved/i);
    await waitFor(() => expect(screen.queryAllByRole("img", { name: "Rejected" })).toHaveLength(0));
    expect(within(card("[01]")).getByText("To check")).toBeInTheDocument();
    const cached = client.getQueryData<PaperDetail>(keys.paper(ID))!;
    expect(cached.rejected).toBe(0);
  });

  it("Read 6 with DECIMER makes 6 calls, never more than 4 in flight, then reconnects once", async () => {
    let inFlight = 0;
    let most = 0;
    const resolvers: (() => void)[] = [];
    const run = vi.spyOn(api, "runPrediction").mockImplementation(
      () =>
        new Promise((resolve) => {
          inFlight += 1;
          most = Math.max(most, inFlight);
          resolvers.push(() => {
            inFlight -= 1;
            resolve({ step_id: "x" });
          });
        }),
    );
    const segs = Array.from({ length: 6 }, (_, i) => segment(`s${i + 1}`, { predictions: [] }));
    renderGrid(paper(segs, { ocsr_mode: "off" }));
    await waitFor(() => expect(cards()).toHaveLength(6));
    fireEvent.click(screen.getByRole("button", { name: "Select all shown" }));
    fireEvent.click(screen.getByRole("button", { name: "Read 6 with DECIMER" }));
    await waitFor(() => expect(run).toHaveBeenCalledTimes(4));
    expect(live.reconnect).not.toHaveBeenCalled();
    while (resolvers.length) {
      await act(async () => {
        resolvers.shift()!();
        await Promise.resolve();
      });
    }
    await waitFor(() => expect(run).toHaveBeenCalledTimes(6));
    while (resolvers.length || inFlight) {
      await act(async () => {
        resolvers.shift()?.();
        await Promise.resolve();
      });
    }
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    expect(most).toBeLessThanOrEqual(4);
  });
});

describe("useBulkCuration", () => {
  function bigPaper(n: number): PaperDetail {
    return paper(Array.from({ length: n }, (_, i) => segment(`s${i}`)));
  }

  it("1,200 items go out as 3 calls of at most 500", async () => {
    const qc = createQueryClient();
    qc.setQueryData(keys.paper(ID), bigPaper(1200));
    const bulk = vi.spyOn(api, "putBulkCuration").mockResolvedValue({ updated: 0 });
    vi.spyOn(api, "getPaper").mockResolvedValue(bigPaper(1200));
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useBulkCuration(ID), { wrapper });
    const items: BulkCurationItem[] = Array.from({ length: 1200 }, (_, i) => ({
      segment_id: `s${i}`,
      status: "accepted",
    }));
    await act(() => result.current.bulk(items));
    expect(bulk).toHaveBeenCalledTimes(3);
    expect(bulk.mock.calls.map((c) => c[1].length)).toEqual([500, 500, 200]);
  });

  it("waits for a pending single save of the same segment before it sends", async () => {
    const qc = createQueryClient();
    qc.setQueryData(keys.paper(ID), bigPaper(2));
    vi.spyOn(api, "getPaper").mockResolvedValue(bigPaper(2));
    const order: string[] = [];
    let finishPut: () => void = () => undefined;
    vi.spyOn(api, "putCuration").mockImplementation(
      (_id, body) =>
        new Promise((resolve) => {
          finishPut = () => {
            order.push("put");
            resolve({ ...body });
          };
        }),
    );
    vi.spyOn(api, "putBulkCuration").mockImplementation(async () => {
      order.push("bulk");
      return { updated: 1 };
    });
    const { useSaveCuration } = await import("../api/queries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () => ({ save: useSaveCuration(ID).save, bulk: useBulkCuration(ID).bulk }),
      { wrapper },
    );
    let saved!: Promise<unknown>;
    let bulked!: Promise<void>;
    act(() => {
      saved = result.current.save("s0", { note: "n" });
      bulked = result.current.bulk([{ segment_id: "s0", status: "accepted" }]);
    });
    await new Promise((r) => setTimeout(r, 10));
    expect(order).toEqual([]);
    await act(async () => {
      finishPut();
      await saved;
      await bulked;
    });
    expect(order).toEqual(["put", "bulk"]);
    // the bulk status wins in the cache, and the note of the single save stays
    const s0 = qc.getQueryData<PaperDetail>(keys.paper(ID))!.segments[0]!;
    expect(s0.curation).toMatchObject({ status: "accepted", note: "n" });
  });
});

describe("cardState", () => {
  const p = paper([]);
  it("curation wins; else reading, failed, not-read, to-check", () => {
    const none = segment("s1", { predictions: [] });
    expect(cardState(segment("s1", { curation: curation({ status: "accepted" }) }), [], p)).toBe(
      "accepted",
    );
    expect(cardState(segment("s1", { curation: curation({ status: "rejected" }) }), [], p)).toBe(
      "rejected",
    );
    expect(cardState(segment("s1"), [], p)).toBe("to-check");
    for (const status of ["pending", "queued", "running"]) {
      expect(cardState(none, [step({ segment_id: "s1", status })], p)).toBe("reading");
    }
    expect(cardState(none, [step({ segment_id: "s1", status: "failed" })], p)).toBe("failed");
    expect(
      cardState(
        none,
        [
          step({ segment_id: "s1", status: "failed" }),
          step({ segment_id: "s1", status: "done" }), // newer, but gave no valid structure
        ],
        p,
      ),
    ).toBe("to-check");
    expect(cardState(none, [], paper([], { ocsr_mode: "off" }))).toBe("not-read");
    expect(cardState(none, [step({ segment_id: "other", status: "running" })], p)).toBe(
      "not-read",
    );
  });
});
