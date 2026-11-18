// Paper workspace frame (/app/papers/:id): header row, export links, view in the URL, the
// status bar (state, queue, progress, failed pages with retry, a failed PDF check, live
// note), the gone page on a 404 (and no live stream behind it), hostile titles as text.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient, keys } from "../api/queries";
import type { PaperDetail, QueueOut, StepOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import { useWorkspace } from "./useWorkspace";
import Workspace from "./Workspace";

// The live stream is mocked: what matters here is its mode, reconnect(), and whether the
// hook is mounted at all (F2 M5: a gone paper must not keep a stream or a poll running).
const live = vi.hoisted(() => ({
  mode: "live" as "connecting" | "live" | "polling" | "ended",
  reconnect: (() => undefined) as () => void,
  mounted: 0,
  everMounted: 0,
}));

vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: () => {
    useEffect(() => {
      live.mounted += 1;
      live.everMounted += 1;
      return () => {
        live.mounted -= 1;
      };
    }, []);
    return { mode: live.mode, reconnect: live.reconnect };
  },
}));

const XSS = "<img src=x onerror=window.__xss=1>";
const ID = "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f"; // paper ids are UUIDs

function paper(over: Partial<PaperDetail> = {}): PaperDetail {
  return {
    id: ID,
    display_name: "alkaloids.pdf",
    status: "done",
    pages: 8,
    doi: "10.1039/d5dd00313j",
    title: "Alkaloids from Coffea leaves",
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: 15,
    accepted: 9,
    rejected: 2,
    to_review: 4,
    failed_pages: 0,
    counts: { steps_by_status: {} },
    segments: [],
    ...over,
  };
}

let seq = 0;
function step(over: Partial<StepOut>): StepOut {
  seq += 1;
  return {
    id: `st${seq}`,
    kind: "segment_page",
    page: 0,
    segment_id: null,
    status: "done",
    attempts: 1,
    error_class: null,
    engine: null,
    created_at: `2026-11-18T10:${String(Math.floor(seq / 60) % 60).padStart(2, "0")}:${String(seq % 60).padStart(2, "0")}.000000Z`,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname + loc.search}</output>;
}

let client: QueryClient;

function renderWorkspace(
  opts: { search?: string; paper?: PaperDetail; steps?: StepOut[]; queue?: QueueOut } = {},
) {
  if (opts.paper !== undefined || !vi.isMockFunction(api.getPaper)) {
    vi.spyOn(api, "getPaper").mockResolvedValue(opts.paper ?? paper());
  }
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps: opts.steps ?? [] });
  vi.spyOn(api, "getQueue").mockResolvedValue(opts.queue ?? { papers: [], estimate_s: 0 });
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/app/papers/${ID}${opts.search ?? ""}`]}>
          <Routes>
            <Route path="/app/papers/:id" element={<Workspace />} />
            <Route path="/app" element={<p>tool home</p>} />
          </Routes>
          <Where />
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const title = () => screen.findByRole("heading", { level: 1 });

beforeEach(() => {
  live.mode = "live";
  live.reconnect = vi.fn();
  live.mounted = 0;
  live.everMounted = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as { __xss?: unknown }).__xss;
});

describe("header", () => {
  it("shows the title, the DOI as a text link, the counts and the page title", async () => {
    renderWorkspace();
    expect(await title()).toHaveTextContent("Alkaloids from Coffea leaves");
    const doi = screen.getByRole("link", { name: "10.1039/d5dd00313j" });
    expect(doi).toHaveAttribute("href", "https://doi.org/10.1039/d5dd00313j");
    expect(doi).toHaveAttribute("rel", "noopener noreferrer");
    const counts = screen.getByRole("list", { name: "Counts" });
    expect(counts).toHaveTextContent("15 structures");
    expect(counts).toHaveTextContent("9 accepted");
    expect(counts).toHaveTextContent("4 to check");
    expect(counts).toHaveTextContent("2 rejected");
    await waitFor(() => expect(document.title).toBe("Alkaloids from Coffea leaves · MARCUS"));
  });

  it("falls back to the display name without a title, and leaves the DOI out without one", async () => {
    renderWorkspace({ paper: paper({ title: null, doi: null }) });
    expect(await title()).toHaveTextContent("alkaloids.pdf");
    expect(screen.queryByRole("link", { name: /10\./ })).toBeNull();
    await waitFor(() => expect(document.title).toBe("alkaloids.pdf · MARCUS"));
  });

  it("a hostile title renders as text and runs nothing", async () => {
    renderWorkspace({ paper: paper({ title: XSS, display_name: XSS }) });
    expect(await title()).toHaveTextContent(XSS);
    expect(document.querySelector("main img")).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect((window as { __xss?: unknown }).__xss).toBeUndefined();
  });

  it("Send N to COCONUT names the accepted count; with none it is disabled with a reason", async () => {
    const { unmount } = renderWorkspace();
    expect(await screen.findByRole("button", { name: "Send 9 to COCONUT" })).toBeEnabled();
    unmount();
    renderWorkspace({ paper: paper({ accepted: 0, to_review: 13 }) });
    const send = await screen.findByRole("button", { name: "Send 0 to COCONUT" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription("Accept a structure first");
  });
});

describe("export menu", () => {
  it("offers JSON, CSV and SDF, accepted only or all, as plain links", async () => {
    renderWorkspace();
    const button = await screen.findByRole("button", { name: "Export" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("group", { name: "Export" });
    const sdf = within(menu).getByRole("link", { name: "SDF, accepted only" });
    expect(sdf).toHaveAttribute("href", `/api/v2/papers/${ID}/export?format=sdf&status=accepted`);
    expect(within(menu).getByRole("link", { name: "JSON, all" })).toHaveAttribute(
      "href",
      `/api/v2/papers/${ID}/export?format=json&status=all`,
    );
    expect(within(menu).getAllByRole("link")).toHaveLength(6);
  });

  it("Escape closes the menu and gives the focus back", async () => {
    renderWorkspace();
    const button = await screen.findByRole("button", { name: "Export" });
    fireEvent.click(button);
    fireEvent.keyDown(screen.getByRole("link", { name: "CSV, all" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Export" })).toBeNull();
    expect(button).toHaveFocus();
  });
});

describe("view in the URL", () => {
  it("opens the review view by default", async () => {
    renderWorkspace();
    await title();
    expect(screen.getByRole("button", { name: "Review" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Review view" })).toBeInTheDocument();
  });

  it("?view=paper opens the paper view, and the toggle writes the URL", async () => {
    renderWorkspace({ search: "?view=paper&s=g7" });
    await title();
    expect(screen.getByRole("button", { name: "Paper" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Paper view" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(screen.getByRole("region", { name: "Review view" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`/app/papers/${ID}?s=g7`);
  });
});

describe("status bar", () => {
  const failedPage4 = (errorClass: string) => [
    step({ kind: "render_page", page: 4 }),
    step({ kind: "segment_page", page: 4, status: "failed", error_class: errorClass }),
  ];

  it("a failed segment_page on API page 4 reads as page 5 with its reason, and retries page 4", async () => {
    let resolve!: (v: { step_id: string }) => void;
    const retry = vi
      .spyOn(api, "retryPage")
      .mockReturnValue(new Promise((r) => (resolve = r)));
    renderWorkspace({ steps: failedPage4("timeout") });
    expect(await screen.findByText("Page 5 could not be read: it took too long")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry page 5" }));
    expect(retry).toHaveBeenCalledWith(ID, 4);
    expect(live.reconnect).not.toHaveBeenCalled(); // only once the retry is accepted
    await act(async () => resolve({ step_id: "new" }));
    expect(live.reconnect).toHaveBeenCalledTimes(1);
  });

  it("worker_lost and an unknown class get their phrases", async () => {
    const { unmount } = renderWorkspace({ steps: failedPage4("worker_lost") });
    expect(
      await screen.findByText("Page 5 could not be read: the worker stopped while reading it"),
    ).toBeInTheDocument();
    unmount();
    renderWorkspace({ steps: failedPage4("gremlins") });
    expect(await screen.findByText("Page 5 could not be read: an unknown error")).toBeInTheDocument();
  });

  it("a page failed, then retried and done, is not shown", async () => {
    renderWorkspace({
      steps: [...failedPage4("timeout"), step({ kind: "render_page", page: 4, status: "done" })],
    });
    await title();
    await screen.findByText(/Pages read/);
    expect(screen.queryByText(/could not be read/)).toBeNull();
  });

  it("a page with a newer step running reads retrying, without a button", async () => {
    renderWorkspace({
      paper: paper({ status: "processing" }),
      steps: [...failedPage4("timeout"), step({ kind: "render_page", page: 4, status: "running" })],
    });
    expect(await screen.findByText("Page 5: retrying…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry page/ })).toBeNull();
  });

  it("a 409 from the retry shows its detail as an error toast", async () => {
    vi.spyOn(api, "retryPage").mockRejectedValue(
      new ApiError(409, "This page is already being read again."),
    );
    renderWorkspace({ steps: failedPage4("timeout") });
    fireEvent.click(await screen.findByRole("button", { name: "Retry page 5" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This page is already being read again.",
    );
    expect(live.reconnect).not.toHaveBeenCalled();
  });

  it("a failed check_pdf with bad_input shows one line instead of the progress", async () => {
    renderWorkspace({
      paper: paper({ status: "failed", pages: null }),
      steps: [step({ kind: "check_pdf", page: null, status: "failed", error_class: "bad_input" })],
    });
    expect(
      await screen.findByText(
        "This PDF could not be read: it is encrypted, damaged or has more than 100 pages",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Pages read/)).toBeNull();
  });

  it("shows the per-step progress", async () => {
    renderWorkspace({
      paper: paper({ status: "processing", pages: 2 }),
      steps: [
        step({ kind: "segment_page", page: 0 }),
        step({ kind: "segment_page", page: 1, status: "running" }),
        step({ kind: "ocsr", segment_id: "g1", status: "done" }),
        step({ kind: "ocsr", segment_id: "g2", status: "queued" }),
      ],
    });
    expect(
      await screen.findByText("Pages read 1/2 · Structures read 1/2"),
    ).toBeInTheDocument();
  });

  it("while waiting, shows this paper's queue estimate in whole minutes", async () => {
    renderWorkspace({
      paper: paper({ status: "processing" }),
      queue: {
        papers: [
          { id: "other", steps_ahead_by_queue: {}, estimate_s: 900 },
          { id: ID, steps_ahead_by_queue: { ocsr: 4 }, estimate_s: 130 },
        ],
        estimate_s: 900,
      },
    });
    expect(await screen.findByText("About 3 min in the queue")).toBeInTheDocument();
  });

  it("under a minute reads less than a minute", async () => {
    renderWorkspace({
      paper: paper({ status: "checking" }),
      queue: { papers: [{ id: ID, steps_ahead_by_queue: {}, estimate_s: 40 }], estimate_s: 40 },
    });
    expect(await screen.findByText("Less than a minute in the queue")).toBeInTheDocument();
  });

  it("a finished paper does not ask for the queue", async () => {
    renderWorkspace();
    await title();
    expect(api.getQueue).not.toHaveBeenCalled();
  });

  it("live mode polling shows the paused note", async () => {
    live.mode = "polling";
    renderWorkspace();
    expect(await screen.findByText("Live updates paused, checking every 2 s")).toBeInTheDocument();
  });

  it("shows the paper state word", async () => {
    renderWorkspace({ paper: paper({ status: "processing" }) });
    const bar = await screen.findByRole("region", { name: "Status" });
    expect(within(bar).getByText("Reading…")).toBeInTheDocument();
  });
});

describe("gone paper", () => {
  it("a 404 renders the one gone page and never opens a live stream", async () => {
    vi.spyOn(api, "getPaper").mockRejectedValue(new ApiError(404, "Not found"));
    renderWorkspace();
    expect(
      await screen.findByRole("heading", { level: 1, name: "This paper is not here any more." }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "It was deleted, it expired after 30 days, or it was opened in another browser.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your papers" })).toHaveAttribute("href", "/app");
    expect(live.everMounted).toBe(0);
  });

  it("a paper that goes away while open unmounts the live stream", async () => {
    renderWorkspace();
    await title();
    expect(live.mounted).toBe(1);
    vi.spyOn(api, "getPaper").mockRejectedValue(new ApiError(404, "Not found"));
    await act(() => client.invalidateQueries({ queryKey: keys.paper(ID) }));
    expect(
      await screen.findByRole("heading", { name: "This paper is not here any more." }),
    ).toBeInTheDocument();
    expect(live.mounted).toBe(0);
  });

  it("a link whose id is not a paper id shows the gone page without asking the API", async () => {
    const get = vi.spyOn(api, "getPaper");
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/app/papers/x"]}>
          <Routes>
            <Route path="/app/papers/:id" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "This paper is not here any more." }),
    ).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
    expect(live.everMounted).toBe(0);
  });

  it("a 422 for the id counts as gone too", async () => {
    vi.spyOn(api, "getPaper").mockRejectedValue(new ApiError(422, "invalid id"));
    renderWorkspace();
    expect(
      await screen.findByRole("heading", { level: 1, name: "This paper is not here any more." }),
    ).toBeInTheDocument();
  });

  it("another error shows its text and a way to try again", async () => {
    const get = vi
      .spyOn(api, "getPaper")
      .mockRejectedValueOnce(new ApiError(503, "The server is busy, try again in a moment."));
    renderWorkspace();
    expect(
      await screen.findByText("The server is busy, try again in a moment."),
    ).toBeInTheDocument();
    get.mockResolvedValue(paper());
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "This paper could not be opened.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Alkaloids from Coffea leaves" }),
    ).toBeInTheDocument();
  });
});

describe("useWorkspace", () => {
  it("keeps the focused segment in ?s= (replace by default, push on request) and sorts segments", async () => {
    const seg = (id: string, page: number, idx: number) => ({
      id,
      page,
      idx,
      bbox: [0, 0, 1, 1] as [number, number, number, number],
      curation: null,
      predictions: [],
    });
    vi.spyOn(api, "getPaper").mockResolvedValue(
      paper({ segments: [seg("c", 1, 0), seg("b", 0, 1), seg("a", 0, 0)] }),
    );
    vi.spyOn(api, "getSteps").mockResolvedValue({ steps: [] });
    const qc = createQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/app", `/app/papers/${ID}?view=paper`]} initialIndex={1}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
    const { result } = renderHook(
      () => ({ ws: useWorkspace(ID), loc: useLocation(), navigate: useNavigate() }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.ws.segments.map((s) => s.id)).toEqual(["a", "b", "c"]));
    act(() => result.current.ws.setSelection("b"));
    expect(result.current.ws.selection).toBe("b");
    expect(result.current.loc.search).toBe("?view=paper&s=b");
    act(() => result.current.ws.setSelection("c", { push: true }));
    expect(result.current.ws.selection).toBe("c");
    act(() => result.current.navigate(-1)); // Back: the replaced entry, not the first page
    expect(result.current.ws.selection).toBe("b");
    expect(result.current.ws.view).toBe("paper");
    act(() => result.current.ws.setSelection(null));
    expect(result.current.loc.search).toBe("?view=paper");
  });
});
