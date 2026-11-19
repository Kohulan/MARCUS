// Paper view (/app/papers/:id?view=paper): the pages with a marker per structure, the
// paper's text (fetched only while this view is open), and the structure list. Markers and
// cards are linked: clicking a marker selects its card, hovering either outlines the other.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { createQueryClient } from "../api/queries";
import type { DoclingDoc, PaperDetail, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import Workspace from "./Workspace";

vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: () => ({ mode: "live", reconnect: () => undefined }),
}));

vi.mock("../api/depictions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/depictions")>()),
  useDepiction: (url: string | null) => ({ src: url, failed: false }),
}));

const ID = "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f";

function prediction(over: Partial<PredictionOut> = {}): PredictionOut {
  return {
    id: "pr1",
    engine: "decimer",
    engine_version: "2.7",
    smiles: "c1ccccc1",
    molfile: null,
    valid: true,
    ms: 120,
    cached: false,
    created_at: "2026-11-18T10:00:00Z",
    ...over,
  };
}

function segment(id: string, over: Partial<SegmentOut> = {}): SegmentOut {
  const n = Number(id.replace(/\D/g, "")) || 0;
  return {
    id,
    page: 1,
    idx: n,
    bbox: [100, 200, 300, 400],
    curation: null,
    predictions: [prediction({ id: `pr-${id}` })],
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
    ocsr_mode: "auto",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: segments.length,
    accepted: 0,
    rejected: 0,
    to_review: segments.length,
    failed_pages: 0,
    failed: 0,
    counts: { steps_by_status: {} },
    segments,
    ...over,
  };
}

function step(over: Partial<StepOut>): StepOut {
  return {
    id: "st-docling",
    kind: "docling",
    page: null,
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

const DOC: DoclingDoc = {
  body: { children: [{ $ref: "#/texts/0" }, { $ref: "#/texts/1" }] },
  texts: [
    { self_ref: "#/texts/0", label: "section_header", text: "Results" },
    { self_ref: "#/texts/1", label: "text", text: "Compound 1 was isolated." },
  ],
};

let client: QueryClient;

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{`${loc.pathname}${loc.search}`}</output>;
}

function renderAt(
  p: PaperDetail,
  { search = "?view=paper", steps = [step({})], doc = DOC }: {
    search?: string;
    steps?: StepOut[];
    doc?: DoclingDoc;
  } = {},
) {
  vi.spyOn(api, "getPaper").mockResolvedValue(p);
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps });
  vi.spyOn(api, "getQueue").mockResolvedValue({ papers: [], estimate_s: 0 });
  const getText = vi.spyOn(api, "getText").mockResolvedValue(doc);
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/app/papers/${ID}${search}`]}>
          <Routes>
            <Route
              path="/app/papers/:id"
              element={
                <>
                  <Workspace />
                  <Where />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { getText };
}

/** Loads a page image as the browser would: its natural size, then the width it is shown at. */
async function loadPage(page: number, natural = 2480, shown = 620) {
  const img = await screen.findByRole("img", { name: `Page ${page}` });
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: natural });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: Math.round(natural * 1.414) });
  Object.defineProperty(img, "clientWidth", { configurable: true, value: shown });
  fireEvent.load(img);
  return img;
}

const card = (tag: string) =>
  screen.getAllByRole("article").find((el) => el.getAttribute("aria-label")?.startsWith(tag))!;

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as { __xss?: unknown }).__xss;
});

describe("Paper view", () => {
  it("draws one marker button per segment of the page, named by structure and page", async () => {
    renderAt(paper([segment("s1"), segment("s2", { bbox: [500, 600, 900, 1000] })]));
    await loadPage(2);
    const pages = screen.getByRole("region", { name: "Pages" });
    expect(within(pages).getByRole("button", { name: "Structure [01] on page 2" })).toBeInTheDocument();
    expect(within(pages).getByRole("button", { name: "Structure [02] on page 2" })).toBeInTheDocument();
    expect(within(pages).getAllByRole("button", { name: /^Structure / })).toHaveLength(2);
  });

  it("places the bbox in percent of the image's natural size (it follows the shown size)", async () => {
    renderAt(paper([segment("s1", { bbox: [100, 200, 300, 400] })]));
    await loadPage(2, 2480, 620); // natural 2480 × 3507
    const box = screen.getByRole("button", { name: "Structure [01] on page 2" });
    expect(box.style.getPropertyValue("--l")).toBe("4.032%");
    expect(box.style.getPropertyValue("--t")).toBe("5.703%");
    expect(box.style.getPropertyValue("--w")).toBe("8.065%");
    expect(box.style.getPropertyValue("--h")).toBe("5.703%");
  });

  it("gives each marker its state shape and its numbered tag", async () => {
    renderAt(
      paper([
        segment("s1", { curation: { status: "accepted", smiles: null, molfile: null, note: null } }),
        segment("s2"),
      ]),
    );
    await loadPage(2);
    const one = screen.getByRole("button", { name: "Structure [01] on page 2" });
    const two = screen.getByRole("button", { name: "Structure [02] on page 2" });
    expect(one).toHaveClass("pv-marker--accepted");
    expect(two).toHaveClass("pv-marker--to-check");
    expect(two).toHaveTextContent("[02]");
  });

  it("selects a structure's card when its marker is clicked", async () => {
    renderAt(paper([segment("s1"), segment("s2")]));
    await loadPage(2);
    fireEvent.click(screen.getByRole("button", { name: "Structure [02] on page 2" }));
    await waitFor(() => expect(card("[02]")).toHaveAttribute("aria-current", "true"));
    expect(card("[01]")).not.toHaveAttribute("aria-current");
    expect(screen.getByTestId("where")).toHaveTextContent("s=s2");
    expect(card("[02]")).toHaveFocus();
  });

  it("outlines the marker of a hovered or selected card, and the card of a hovered marker", async () => {
    renderAt(paper([segment("s1"), segment("s2")]));
    await loadPage(2);
    const two = screen.getByRole("button", { name: "Structure [02] on page 2" });
    fireEvent.mouseEnter(card("[02]"));
    expect(two).toHaveClass("pv-marker--lit");
    fireEvent.mouseLeave(card("[02]"));
    expect(two).not.toHaveClass("pv-marker--lit");

    fireEvent.mouseEnter(screen.getByRole("button", { name: "Structure [01] on page 2" }));
    expect(card("[01]")).toHaveClass("card--linked");

    fireEvent.click(card("[02]"));
    await waitFor(() => expect(card("[02]")).toHaveAttribute("aria-current", "true"));
    expect(two).toHaveClass("pv-marker--lit");
  });

  it("lists the structures as compact cards with their actions", async () => {
    renderAt(paper([segment("s1")]));
    const list = await screen.findByRole("region", { name: "Structures" });
    const c = within(list).getByRole("article");
    expect(c).toHaveClass("card--compact");
    expect(within(c).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(c).getByRole("button", { name: "Accept [01]" })).toHaveTextContent(/^Accept$/);
    expect(within(c).getByRole("button", { name: "Reject [01]" })).toHaveTextContent(/^Reject$/);
  });

  it("does not ask for the text in the Review view", async () => {
    const { getText } = renderAt(paper([segment("s1")]), { search: "" });
    await screen.findByRole("region", { name: "Review view" });
    await screen.findAllByRole("article");
    expect(getText).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Paper" }));
    await screen.findByRole("heading", { name: "Results" });
    expect(getText).toHaveBeenCalledTimes(1);
  });

  it("shows the paper's text as headings and paragraphs, and reserves the annotation area", async () => {
    renderAt(paper([segment("s1")]));
    const text = await screen.findByRole("region", { name: "Text" });
    expect(await within(text).findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(within(text).getByText("Compound 1 was isolated.")).toBeInTheDocument();
    expect(
      within(text).getByText("Annotations (compounds, organisms, methods) come in a later version."),
    ).toBeInTheDocument();
  });

  it("renders hostile text from the PDF as text", async () => {
    const hostile = "<img src=x onerror=window.__xss=1>";
    renderAt(paper([segment("s1")]), {
      doc: { texts: [{ self_ref: "#/texts/0", label: "text", text: hostile }] },
    });
    const shown = await screen.findByText(hostile);
    expect(shown.tagName).toBe("P");
    expect(document.querySelector('img[src="x"]')).toBeNull();
    expect((window as { __xss?: unknown }).__xss).toBeUndefined();
  });

  it("downloads the text as <display name without .pdf>.txt through a blob link", async () => {
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:http://localhost/7c1d");
    const revokeObjectURL = vi.fn();
    // jsdom has no object URLs. Left in place for this file: the revoke runs on a timer.
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    renderAt(paper([segment("s1")], { display_name: "alkaloids.PDF" }));
    await screen.findByRole("heading", { name: "Results" });
    fireEvent.click(screen.getByRole("button", { name: "Download text" }));

    expect(clicked).toHaveLength(1);
    expect(clicked[0]!.href).toMatch(/^blob:/);
    expect(clicked[0]!.download).toBe("alkaloids.txt");
    const blob = createObjectURL.mock.calls[0]![0];
    const read = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsText(blob);
    });
    expect(read).toBe("Results\n\nCompound 1 was isolated.");
  });

  it("shows the failure line when the docling step failed, without asking for the text", async () => {
    const { getText } = renderAt(paper([segment("s1")]), {
      steps: [step({ status: "failed", error_class: "timeout" })],
    });
    expect(
      await screen.findByText("The text could not be read: it took too long"),
    ).toBeInTheDocument();
    expect(getText).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Download text" })).not.toBeInTheDocument();
  });

  it("says the text is not ready while the docling step runs", async () => {
    const { getText } = renderAt(paper([segment("s1")], { status: "processing" }), {
      steps: [step({ status: "running" })],
    });
    expect(await screen.findByText("The text of this paper is not ready")).toBeInTheDocument();
    expect(getText).not.toHaveBeenCalled();
  });

  it("says the text is not ready when the server has none yet", async () => {
    const { getText } = renderAt(paper([segment("s1")]), { steps: [] });
    getText.mockRejectedValue(new ApiError(404, "Not found"));
    expect(await screen.findByText("The text of this paper is not ready")).toBeInTheDocument();
  });

  it("shows a page that failed to render with its reason, not an empty sheet", async () => {
    renderAt(paper([segment("s1", { page: 0 })]), {
      steps: [
        step({}),
        step({ id: "r2", kind: "render_page", page: 2, status: "failed", error_class: "timeout" }),
        step({ id: "r0", kind: "render_page", page: 0 }),
        step({ id: "r1", kind: "render_page", page: 1 }),
      ],
    });
    const pages = await screen.findByRole("region", { name: "Pages" });
    expect(await within(pages).findByText("Could not be read: it took too long")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Page 1" })).toHaveAttribute("loading", "lazy");
    expect(screen.queryByRole("img", { name: "Page 3" })).not.toBeInTheDocument();
  });
});

describe("Paper view fixes (F9 review)", () => {
  it("a page image that failed to load offers Try again, which loads it afresh", async () => {
    renderAt(paper([segment("s1")]));
    const pages = await screen.findByRole("region", { name: "Pages" });
    const img = await within(pages).findByRole("img", { name: "Page 2" });
    const first = img.getAttribute("src");
    fireEvent.error(img);
    expect(within(pages).getByText("The page image could not be loaded")).toBeInTheDocument();
    fireEvent.click(within(pages).getByRole("button", { name: "Try again" }));
    const again = await within(pages).findByRole("img", { name: "Page 2" });
    expect(again.getAttribute("src")).not.toBe(first);
    expect(again.getAttribute("src")).toContain(`/papers/${ID}/pages/1/image`);
  });
});
