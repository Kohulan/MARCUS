// "All pages or pick a structure" on the paper page (owner decision 2026-11-25): mode `ask`
// shows the two choices; mode `pick` shows the pages to pick from, then one page with its
// boxes. A box not picked yet (a candidate) is no card and counts nowhere.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { createQueryClient } from "../api/queries";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import Workspace from "./Workspace";

const live = vi.hoisted(() => ({ reconnect: vi.fn() }));
vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: () => ({ mode: "live", reconnect: live.reconnect }),
}));

vi.mock("../api/depictions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/depictions")>()),
  useDepiction: (url: string | null) => ({ src: url, failed: false }),
}));

const ID = "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f";

function segment(id: string, over: Partial<SegmentOut> = {}): SegmentOut {
  const n = Number(id.replace(/\D/g, "")) || 0;
  return {
    id,
    page: 0,
    idx: n,
    bbox: [100, 200, 300, 400],
    curation: null,
    predictions: [],
    candidate: true,
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
    first_author: null,
    year: null,
    engine: "decimer",
    ocsr_mode: "pick",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: segments.filter((s) => !s.candidate).length,
    accepted: 0,
    rejected: 0,
    to_review: segments.filter((s) => !s.candidate).length,
    failed_pages: 0,
    failed: 0,
    pages_read: 3,
    structures_total: 0,
    structures_read: 0,
    text_read: true,
    check_started: true,
    rereading: false,
    counts: { steps_by_status: {} },
    segments,
    ...over,
  };
}

function step(over: Partial<StepOut>): StepOut {
  return {
    id: `st-${over.kind}-${over.page}`,
    kind: "render_page",
    page: 0,
    segment_id: null,
    status: "done",
    attempts: 1,
    error_class: null,
    engine: null,
    created_at: "2026-11-18T10:00:00Z",
    started_at: "2026-11-18T10:00:01Z",
    finished_at: "2026-11-18T10:00:09Z",
    ...over,
  };
}

const RENDERED = [0, 1, 2].map((page) => step({ kind: "render_page", page }));

function renderAt(p: PaperDetail, steps: StepOut[] = RENDERED) {
  vi.spyOn(api, "getPaper").mockResolvedValue(p);
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps });
  vi.spyOn(api, "getQueue").mockResolvedValue({ papers: [], estimate_s: 0 });
  vi.spyOn(api, "getAnnotation").mockRejectedValue(new Error("not asked here"));
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
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

async function loadPage(page: number) {
  const img = await screen.findByRole("img", { name: `Page ${page}` });
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: 2480 });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: 3507 });
  Object.defineProperty(img, "clientWidth", { configurable: true, value: 620 });
  fireEvent.load(img);
  return img;
}

afterEach(() => {
  vi.restoreAllMocks();
  live.reconnect.mockClear();
});

describe("mode ask: the paper page asks", () => {
  it("offers Read all pages and Pick a structure", async () => {
    renderAt(paper([], { ocsr_mode: "ask" }));
    const setMode = vi.spyOn(api, "setMode").mockResolvedValue({ ocsr_mode: "pick" });
    fireEvent.click(await screen.findByRole("button", { name: "Pick a structure" }));
    await waitFor(() => expect(setMode).toHaveBeenCalledWith(ID, "pick"));
    fireEvent.click(screen.getByRole("button", { name: "Read all pages" }));
    await waitFor(() => expect(setMode).toHaveBeenCalledWith(ID, "auto"));
  });

  it("asks in a dialog right after the upload (owner, 2026-11-26)", async () => {
    renderAt(paper([], { ocsr_mode: "ask" }));
    const dialog = await screen.findByRole("dialog", { name: "How should MARCUS read it?" });
    expect(within(dialog).getByRole("button", { name: "Read all pages" })).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "Pick a structure" })).toBeInTheDocument();
  });

  it("Esc closes the dialog; the two choices stay on the page", async () => {
    renderAt(paper([], { ocsr_mode: "ask" }));
    const dialog = await screen.findByRole("dialog", { name: "How should MARCUS read it?" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    const bar = screen.getByRole("region", { name: "What to read" });
    expect(within(bar).getByRole("button", { name: "Pick a structure" })).toBeInTheDocument();
  });

  it("is not shown on a paper that reads all pages", async () => {
    renderAt(paper([], { ocsr_mode: "auto" }));
    await screen.findByRole("heading", { name: "Alkaloids" });
    expect(screen.queryByRole("button", { name: "Pick a structure" })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("mode pick", () => {
  it("shows one tile per page; a page not rendered yet cannot be picked", async () => {
    renderAt(paper([]), [RENDERED[0]!, RENDERED[1]!, step({ kind: "render_page", page: 2, status: "pending" })]);
    const pick = await screen.findByRole("group", { name: "Pick a page" });
    const tiles = within(pick).getAllByRole("button");
    expect(tiles.map((t) => t.getAttribute("aria-label"))).toEqual(["Page 1", "Page 2", "Page 3"]);
    expect(tiles[2]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Read all pages" })).toBeInTheDocument();
  });

  it("opens a page: finds its boxes, then Pick another goes back", async () => {
    renderAt(paper([]));
    const seg = vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: "st-seg" });
    fireEvent.click(await screen.findByRole("button", { name: "Page 2" }));
    await waitFor(() => expect(seg).toHaveBeenCalledWith(ID, 1));
    fireEvent.click(await screen.findByRole("button", { name: "Pick another" }));
    expect(await screen.findByRole("group", { name: "Pick a page" })).toBeInTheDocument();
  });

  it("a candidate box is read when clicked", async () => {
    renderAt(paper([segment("s1"), segment("s2")]));
    vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: null });
    const read = vi.spyOn(api, "readSegment").mockResolvedValue({ step_ids: ["a", "b", "c"] });
    fireEvent.click(await screen.findByRole("button", { name: "Page 1" }));
    await loadPage(1);
    fireEvent.click(await screen.findByRole("button", { name: "Read structure [02] on page 1" }));
    await waitFor(() => expect(read).toHaveBeenCalledWith("s2"));
  });

  it("says when a page has no structure", async () => {
    renderAt(paper([]), [...RENDERED, step({ kind: "segment_page", page: 0 })]);
    vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: "st-segment_page-0" });
    fireEvent.click(await screen.findByRole("button", { name: "Page 1" }));
    expect(await screen.findByText("No structures found on this page")).toBeInTheDocument();
  });

  it("candidates are no cards and count nowhere", async () => {
    renderAt(paper([segment("s1"), segment("s2"), segment("s3", { candidate: false })]));
    expect(await screen.findByText("1 structure")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("a finished paper's live stream is reopened by every pick action", async () => {
    renderAt(paper([segment("s1")], { ocsr_mode: "pick" }));
    vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: null });
    vi.spyOn(api, "readSegment").mockResolvedValue({ step_ids: ["a"] });
    fireEvent.click(await screen.findByRole("button", { name: "Page 1" }));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    await loadPage(1);
    fireEvent.click(await screen.findByRole("button", { name: "Read structure [01] on page 1" }));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(2));
  });

  it("says no structures for a page whose boxes came from the cache empty", async () => {
    renderAt(paper([]));
    vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: null });
    fireEvent.click(await screen.findByRole("button", { name: "Page 3" }));
    expect(await screen.findByText("No structures found on this page")).toBeInTheDocument();
  });

  it("a page whose segmentation failed says so and tries again", async () => {
    renderAt(paper([]), [...RENDERED, step({ kind: "segment_page", page: 0, status: "failed", error_class: "engine_error" })]);
    const seg = vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: "st-new" });
    fireEvent.click(await screen.findByRole("button", { name: "Page 1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(seg).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/Structures could not be found/)).toBeInTheDocument();
  });

  it("Retry page in pick mode finds the page's structures again", async () => {
    renderAt(paper([], { failed_pages: 1 }), [...RENDERED, step({ kind: "segment_page", page: 0, status: "failed", error_class: "engine_error" })]);
    const seg = vi.spyOn(api, "segmentPage").mockResolvedValue({ step_id: "st-new" });
    const render = vi.spyOn(api, "retryPage");
    fireEvent.click(await screen.findByRole("button", { name: "Retry page 1" }));
    await waitFor(() => expect(seg).toHaveBeenCalledWith(ID, 0));
    expect(render).not.toHaveBeenCalled();
  });

  it("before any pick the empty grid says nothing (the boxes are not 'no structures')", async () => {
    renderAt(paper([segment("s1")]));
    await screen.findByRole("group", { name: "Pick a page" });
    expect(screen.queryByText("No structures found.")).toBeNull();
  });
});

describe("mode ask: the empty grid", () => {
  it("says nothing before the choice", async () => {
    renderAt(paper([], { ocsr_mode: "ask" }));
    await screen.findByRole("button", { name: "Pick a structure" });
    expect(screen.queryByText("No structures found.")).toBeNull();
  });
});
