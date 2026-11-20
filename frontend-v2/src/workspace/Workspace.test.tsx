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
import type {
  AnnotationOut,
  CurationOut,
  PaperDetail,
  PredictionOut,
  QueueOut,
  SegmentOut,
  StepOut,
} from "../api/types";
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

// COCONUT's DOI count (src/lookup, tested on its own): no test reaches the real COCONUT.
const coconut = vi.hoisted(() => ({
  count: vi.fn<(doi: string, signal?: AbortSignal) => Promise<unknown>>(),
}));
vi.mock("../lookup/coconutDoi", async (actual) => ({
  ...(await actual<typeof import("../lookup/coconutDoi")>()),
  coconutCountForDoi: coconut.count,
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
    first_author: "Rajan",
    year: 2025,
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: 15,
    accepted: 9,
    rejected: 2,
    to_review: 4,
    failed_pages: 0,
    failed: 0,
    counts: { steps_by_status: {} },
    segments: [],
    ...over,
  };
}

function seg(id: string, curation: Partial<CurationOut> | null, predictions?: PredictionOut[]): SegmentOut {
  return {
    id,
    page: 0,
    idx: Number(id.replace(/\D/g, "")),
    bbox: [0, 0, 10, 10],
    curation: curation && { status: "unchecked", smiles: null, molfile: null, note: null, ...curation },
    predictions: predictions ?? [
      {
        id: `pr-${id}`,
        engine: "decimer",
        engine_version: "2.7",
        smiles: "CCO",
        molfile: null,
        valid: true,
        ms: 1,
        cached: false,
        created_at: "2026-11-18T10:00:00Z",
      },
    ],
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

/** GET /papers/{id}/annotation: none yet, unless a test hands one. */
function annotationOut(over: Partial<AnnotationOut> = {}): AnnotationOut {
  return {
    available: true,
    status: "none",
    step: null,
    fields: [],
    model: null,
    model_version: null,
    output: null,
    positions: null,
    curated: null,
    curated_positions: null,
    values: null,
    coconut: null,
    created_at: null,
    updated_at: null,
    curated_at: null,
    ...over,
  };
}

function renderWorkspace(
  opts: {
    search?: string;
    paper?: PaperDetail;
    steps?: StepOut[];
    queue?: QueueOut;
    annotation?: AnnotationOut;
  } = {},
) {
  vi.spyOn(api, "getAnnotation").mockResolvedValue(opts.annotation ?? annotationOut());
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
  coconut.count.mockReset().mockResolvedValue(null);
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
    renderWorkspace({
      paper: paper({
        segments: [
          seg("s1", { status: "accepted" }),
          seg("s2", { status: "accepted" }),
          seg("s3", { status: "rejected" }),
          seg("s4", null),
        ],
      }),
    });
    expect(await title()).toHaveTextContent("Alkaloids from Coffea leaves");
    const doi = screen.getByRole("link", { name: "10.1039/d5dd00313j" });
    expect(doi).toHaveAttribute("href", "https://doi.org/10.1039/d5dd00313j");
    expect(doi).toHaveAttribute("rel", "noopener noreferrer");
    const counts = screen.getByRole("list", { name: "Counts" });
    expect(counts).toHaveTextContent("4 structures");
    expect(counts).toHaveTextContent("2 accepted");
    expect(counts).toHaveTextContent("1 to check");
    expect(counts).toHaveTextContent("1 rejected");
    expect(counts).not.toHaveTextContent("failed");
    await waitFor(() => expect(document.title).toBe("Alkaloids from Coffea leaves · MARCUS"));
  });

  it("counts as the filters do: a failed structure is Failed, not to check (C-I3)", async () => {
    const failed = (id: string) =>
      step({ kind: "ocsr", segment_id: id, status: "failed", engine: "decimer", error_class: "timeout" });
    renderWorkspace({
      // the server's to_review counts the failed ones too
      paper: paper({
        structures: 5,
        accepted: 0,
        rejected: 0,
        to_review: 5,
        segments: [seg("s1", null), seg("s2", null), seg("s3", null, []), seg("s4", null, []), seg("s5", null, [])],
      }),
      steps: [failed("s3"), failed("s4"), failed("s5")],
    });
    await title();
    const counts = screen.getByRole("list", { name: "Counts" });
    await waitFor(() => expect(counts).toHaveTextContent("2 to check"));
    expect(counts).toHaveTextContent("3 failed");
    const filters = screen.getByRole("group", { name: "Filter" });
    expect(within(filters).getByRole("button", { name: /To check/ })).toHaveTextContent("2");
    expect(within(filters).getByRole("button", { name: /Failed/ })).toHaveTextContent("3");
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

  it("links how many structures COCONUT has for the DOI, a known 0 included", async () => {
    const url = "https://coconut.naturalproducts.net/search?q=10.1039%2Fd5dd00313j&tagType=citations&type=tags&activeTab=citations";
    coconut.count.mockResolvedValue({ count: 3, more: false, url });
    const { unmount } = renderWorkspace();
    const link = await screen.findByRole("link", { name: "3 already in COCONUT" });
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(coconut.count).toHaveBeenCalledWith("10.1039/d5dd00313j", expect.any(AbortSignal));
    unmount();
    coconut.count.mockResolvedValue({ count: 0, more: false, url });
    const second = renderWorkspace();
    expect(await screen.findByRole("link", { name: "0 already in COCONUT" })).toBeInTheDocument();
    second.unmount();
    coconut.count.mockResolvedValue({ count: 20, more: true, url });
    renderWorkspace();
    expect(await screen.findByRole("link", { name: "20+ already in COCONUT" })).toBeInTheDocument();
  });

  it("says nothing about COCONUT when the count is unknown or the paper has no DOI", async () => {
    const { unmount } = renderWorkspace();
    await title();
    await waitFor(() => expect(coconut.count).toHaveBeenCalledTimes(1));
    await act(() => new Promise((r) => setTimeout(r, 10)));
    expect(screen.queryByRole("link", { name: /in COCONUT/ })).toBeNull();
    unmount();
    coconut.count.mockClear();
    renderWorkspace({ paper: paper({ doi: null }) });
    await title();
    expect(coconut.count).not.toHaveBeenCalled();
  });

  it("Send N to COCONUT counts accepted structures that have one; with none it is disabled", async () => {
    const segs = [
      seg("s1", null),
      seg("s2", { status: "accepted" }),
      seg("s3", { status: "accepted", smiles: "CCBr" }),
      seg("s4", { status: "accepted" }, []), // accepted, nothing to send
      seg("s5", { status: "rejected" }),
    ];
    const { unmount } = renderWorkspace({ paper: paper({ segments: segs, accepted: 3 }) });
    expect(await screen.findByRole("button", { name: "Send 2 to COCONUT" })).toBeEnabled();
    unmount();
    renderWorkspace({ paper: paper({ segments: [seg("s1", null)], accepted: 0 }) });
    const send = await screen.findByRole("button", { name: "Send 0 to COCONUT" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription("Accept a structure first");
  });

  it("opens the COCONUT form with those structures, tagged as on their cards", async () => {
    sessionStorage.setItem("marcus-coconut-token", "t"); // logged in: the form, not the login
    try {
      renderWorkspace({
        paper: paper({
          segments: [seg("s1", null), seg("s2", { status: "accepted" }), seg("s3", { status: "accepted", smiles: "CCBr" })],
        }),
      });
      fireEvent.click(await screen.findByRole("button", { name: "Send 2 to COCONUT" }));
      const form = await screen.findByRole("dialog");
      const rows = within(form).getAllByRole("listitem");
      expect(rows.map((r) => within(r).getByText(/^\[\d+\]$/).textContent)).toEqual([
        "[02]",
        "[03]",
      ]);
      expect(within(form).getByText("CCBr")).toBeInTheDocument();
      expect(within(form).getByLabelText("Title")).toHaveValue("MARCUS_Submission Rajan 2025");
      expect(within(form).getByLabelText("DOI")).toHaveValue("10.1039/d5dd00313j");
      fireEvent.click(within(form).getByRole("button", { name: "Close" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    } finally {
      sessionStorage.removeItem("marcus-coconut-token");
    }
  });

  it("starts the organisms from the paper's annotation; the curator can still change them", async () => {
    sessionStorage.setItem("marcus-coconut-token", "t");
    try {
      renderWorkspace({
        paper: paper({ segments: [seg("s1", { status: "accepted" })] }),
        annotation: annotationOut({
          status: "done",
          values: { organism_or_species: ["Taxus brevifolia", "Taxus baccata"] },
          coconut: {
            organisms: [
              { name: "Taxus brevifolia", parts: "bark, leaves", location: "China", ecosystems: "forest" },
              { name: "Taxus baccata", parts: "bark, leaves", location: "China", ecosystems: "forest" },
            ],
            kingdom: ["Plantae"],
          },
        }),
      });
      await waitFor(() => expect(api.getAnnotation).toHaveBeenCalled());
      await act(async () => undefined);
      fireEvent.click(await screen.findByRole("button", { name: "Send 1 to COCONUT" }));
      const form = await screen.findByRole("dialog");
      expect(within(form).getByLabelText("Organism")).toHaveValue("Taxus brevifolia");
      expect(within(form).getAllByLabelText("Parts").map((el) => (el as HTMLInputElement).value)).toEqual([
        "bark, leaves",
        "bark, leaves",
      ]);
      expect(within(form).getAllByLabelText("Location")[0]).toHaveValue("China");
      expect(within(form).getAllByLabelText("Ecosystems")[0]).toHaveValue("forest");
      expect(within(form).getByLabelText("Organism 2")).toHaveValue("Taxus baccata");
      // COCONUT has no kingdom field: it is not put anywhere
      expect(within(form).queryByDisplayValue(/Plantae/)).toBeNull();
      const name = within(form).getByLabelText("Organism");
      fireEvent.change(name, { target: { value: "Taxus wallichiana" } });
      expect(name).toHaveValue("Taxus wallichiana");
    } finally {
      sessionStorage.removeItem("marcus-coconut-token");
    }
  });

  it("starts with one empty organism when the paper has no annotation", async () => {
    sessionStorage.setItem("marcus-coconut-token", "t");
    try {
      renderWorkspace({ paper: paper({ segments: [seg("s1", { status: "accepted" })] }) });
      await waitFor(() => expect(api.getAnnotation).toHaveBeenCalled());
      fireEvent.click(await screen.findByRole("button", { name: "Send 1 to COCONUT" }));
      const form = await screen.findByRole("dialog");
      expect(within(form).getByLabelText("Organism")).toHaveValue("");
      expect(within(form).queryByLabelText("Organism 2")).toBeNull();
    } finally {
      sessionStorage.removeItem("marcus-coconut-token");
    }
  });

  it.each([
    ["Rajan", 2025, "MARCUS_Submission Rajan 2025"],
    ["Rajan", null, "MARCUS_Submission Rajan"],
    [null, 2025, "MARCUS_Submission 2025"],
    [null, null, "MARCUS_Submission"],
  ])("the form's title starts as v1's from the first author %s and year %s", async (first_author, year, want) => {
    sessionStorage.setItem("marcus-coconut-token", "t");
    try {
      renderWorkspace({
        paper: paper({ first_author, year, segments: [seg("s1", { status: "accepted" })] }),
      });
      fireEvent.click(await screen.findByRole("button", { name: "Send 1 to COCONUT" }));
      const field = within(await screen.findByRole("dialog")).getByLabelText("Title");
      expect(field).toHaveValue(want);
      fireEvent.change(field, { target: { value: "My own title" } });
      expect(field).toHaveValue("My own title");
    } finally {
      sessionStorage.removeItem("marcus-coconut-token");
    }
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

  it("says that every file carries the annotation once the paper has one", async () => {
    const { unmount } = renderWorkspace();
    fireEvent.click(await screen.findByRole("button", { name: "Export" }));
    await waitFor(() => expect(api.getAnnotation).toHaveBeenCalled());
    expect(screen.queryByText("With the annotation")).toBeNull();
    unmount();
    renderWorkspace({ annotation: annotationOut({ status: "done", values: { Kingdom: ["Plantae"] } }) });
    const button = await screen.findByRole("button", { name: "Export" });
    await waitFor(() => {
      fireEvent.click(button);
      expect(within(screen.getByRole("group", { name: "Export" })).getByText("With the annotation")).toBeInTheDocument();
    });
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

  it("→ in focus mode does not re-render the hidden grid's cards", async () => {
    const segments = Array.from({ length: 20 }, (_, i) => seg(`s${i + 1}`, null));
    const url = vi.spyOn(api, "depictionUrl");
    renderWorkspace({ paper: paper({ segments }), search: "?s=s1&focus=1" });
    const region = await screen.findByRole("region", { name: /^Focus/ });
    url.mockClear();
    fireEvent.keyDown(region, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("s=s2"));
    // Focus mode draws its own structure and the two cards whose `current` changed render
    // again; the other 18 memoised cards stay as they were (41 calls before).
    expect(url.mock.calls.length).toBeLessThan(10);
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
    // the API's own 409 details: "Page has not failed", "Page is still running",
    // "No retries left for this page" (backend-v2 api/routes/papers.py)
    vi.spyOn(api, "retryPage").mockRejectedValue(new ApiError(409, "No retries left for this page"));
    renderWorkspace({ steps: failedPage4("timeout") });
    fireEvent.click(await screen.findByRole("button", { name: "Retry page 5" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No retries left for this page");
    expect(live.reconnect).not.toHaveBeenCalled();
  });

  it("a retry that gets 404 (the paper was deleted meanwhile) shows the gone page", async () => {
    vi.spyOn(api, "retryPage").mockRejectedValue(new ApiError(404, "Not found"));
    renderWorkspace({ steps: failedPage4("timeout") });
    fireEvent.click(await screen.findByRole("button", { name: "Retry page 5" }));
    vi.mocked(api.getPaper).mockRejectedValue(new ApiError(404, "Not found"));
    expect(await screen.findByText("This paper is not here any more.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeEmptyDOMElement();
  });

  it("Retry stays disabled after a 202 until the refresh after it lands", async () => {
    vi.spyOn(api, "retryPage").mockResolvedValue({ step_id: "new" });
    renderWorkspace({ steps: failedPage4("timeout") });
    const button = await screen.findByRole("button", { name: "Retry page 5" });
    const reads = vi.mocked(api.getSteps).mock.calls.length;
    let answer!: (v: { steps: StepOut[] }) => void;
    vi.mocked(api.getSteps).mockReturnValue(new Promise((r) => (answer = r)));
    fireEvent.click(button);
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getSteps).toHaveBeenCalledTimes(reads + 1)); // the refresh is out
    expect(screen.getByRole("button", { name: "Retry page 5" })).toBeDisabled();
    // the refresh lands (here still failed: the button is offered again)
    await act(async () => answer({ steps: failedPage4("timeout") }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry page 5" })).toBeEnabled());
  });

  it("failed pages are in a polite live region that is there before a page fails", async () => {
    renderWorkspace({ paper: paper({ status: "processing" }) });
    await title();
    const region = screen.getByRole("status", { name: "Failed pages" });
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toBeEmptyDOMElement();
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
    expect(await screen.findByText("Less than a minute")).toBeInTheDocument();
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
