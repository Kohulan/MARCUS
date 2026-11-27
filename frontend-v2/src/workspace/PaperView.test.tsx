// Paper view (/app/papers/:id?view=paper): the pages with a marker per structure, the
// paper's text (fetched only while this view is open), and the structure list. Markers and
// cards are linked: clicking a marker selects its card, hovering either outlines the other.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { paperLayout } from "../test/paperLayout";
import { createQueryClient } from "../api/queries";
import type {
  AnnotationOut,
  DoclingDoc,
  PaperDetail,
  PredictionOut,
  SegmentOut,
  StepOut,
} from "../api/types";
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
    pages_read: 0,
    structures_total: 0,
    structures_read: 0,
    text_read: false,
    check_started: false,
    rereading: false,
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

/** The served fields: key, label and max_length (backend core/annotation.py MAX_LENGTH). */
const FIELDS: [string, string, number][] = [
  ["compound_group", "Compound series", 435],
  ["compound_class", "Compound class", 576],
  ["organism_part", "Organism part", 183],
  ["organism_or_species", "Organism", 676],
  ["geo_location", "Place", 348],
  ["Kingdom", "Kingdom", 60],
  ["trivial_name", "Compound names", 397],
  ["location", "Habitat or host", 234],
  ["iupac_name", "IUPAC names", 7179],
  ["abbreviation", "Abbreviations", 586],
  ["iupac_like_name", "Semi-systematic names", 990],
];
const noValues = () => Object.fromEntries(FIELDS.map(([k]) => [k, [] as string[]]));

/** GET /papers/{id}/annotation: never asked for by default. */
function annotation(over: Partial<AnnotationOut> = {}): AnnotationOut {
  return {
    available: true,
    status: "none",
    step: null,
    fields: FIELDS.map(([key, label, max_length]) => ({ key, label, max_length })),
    limits: { max_values_per_field: 200, max_total_values: 300 },
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

function renderAt(
  p: PaperDetail,
  { search = "?view=paper", steps = [step({})], doc = DOC, ann = annotation() }: {
    search?: string;
    steps?: StepOut[];
    doc?: DoclingDoc;
    ann?: AnnotationOut;
  } = {},
) {
  vi.spyOn(api, "getAnnotation").mockResolvedValue(ann);
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

  it("a structure with R-groups carries the tag on its marker and its list card", async () => {
    renderAt(
      paper([
        segment("s1", {
          predictions: [prediction({ smiles: "[1*]c1ccccc1", rgroups: ["R1"] })],
        }),
        segment("s2"),
      ]),
    );
    await loadPage(2);
    const one = screen.getByRole("button", { name: "Structure [01] on page 2, R-groups: R1" });
    expect(one).toHaveTextContent("R-groups: R1");
    expect(screen.getByRole("button", { name: "Structure [02] on page 2" })).not.toHaveTextContent(
      "R-groups",
    );
    const list = screen.getByRole("region", { name: "Structures" });
    expect(within(list).getByText("R-groups: R1")).toBeInTheDocument();
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

  it("shows the paper's text as headings and paragraphs, with Annotate above it", async () => {
    renderAt(paper([segment("s1")]));
    const text = await screen.findByRole("region", { name: "Text" });
    expect(await within(text).findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(within(text).getByText("Compound 1 was isolated.")).toBeInTheDocument();
    const panel = await within(text).findByRole("region", { name: "Annotation" });
    expect(within(panel).getByRole("button", { name: "Annotate" })).toHaveAccessibleDescription(
      "A model on this server suggests organism, place and compound names.",
    );
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

// The annotation: on demand (Annotate), its progress, the fields with their values, each
// found value a button that walks its occurrences in the text, corrections and the reset.
const TEXT = "Two diterpenoids from the bark of Taxus brevifolia. Taxus brevifolia grows in Oregon.";
const ANN_DOC: DoclingDoc = {
  body: { children: [{ $ref: "#/texts/0" }, { $ref: "#/texts/1" }] },
  texts: [
    { self_ref: "#/texts/0", label: "section_header", text: "Abstract" },
    { self_ref: "#/texts/1", label: "text", text: TEXT },
  ],
};
const at = (s: string, n = 0) => {
  let i = -1;
  for (let k = 0; k <= n; k++) i = TEXT.indexOf(s, i + 1);
  return [1, i, i + s.length] as [number, number, number];
};

function annotated(over: Partial<AnnotationOut> = {}): AnnotationOut {
  const values = {
    ...noValues(),
    organism_or_species: ["Taxus brevifolia"],
    organism_part: ["bark"],
    Kingdom: ["Plantae"],
  };
  return annotation({
    status: "done",
    model: "fake-annotator",
    model_version: "fake-1",
    output: values,
    values,
    positions: {
      organism_or_species: { "Taxus brevifolia": [at("Taxus brevifolia"), at("Taxus brevifolia", 1)] },
      organism_part: { bark: [at("bark")] },
      Kingdom: { Plantae: [] },
    },
    ...over,
  });
}

const annStep = (over: Partial<StepOut> = {}) =>
  step({ id: "st-ann", kind: "annotate", status: "running", created_at: "2026-11-18T11:00:00Z", ...over });

async function panel() {
  const text = await screen.findByRole("region", { name: "Text" });
  return within(text).findByRole("region", { name: "Annotation" });
}

/** POST starts a run: from then on GET says its step is pending (the panel reads GET again). */
function startable() {
  return vi.spyOn(api, "startAnnotation").mockImplementation(() => {
    vi.mocked(api.getAnnotation).mockResolvedValue(
      annotation({ status: "pending", step: annStep({ status: "pending" }) }),
    );
    return Promise.resolve({ step_id: "st-ann" });
  });
}

/** GET now answers `ann` (the run ended), read at once instead of at the next poll. */
async function settle(ann: AnnotationOut) {
  vi.mocked(api.getAnnotation).mockResolvedValue(ann);
  await client.invalidateQueries({ queryKey: ["annotation", ID] });
}

describe("Paper view: annotation", () => {
  it("Annotate (where none started by itself) starts it and the panel says Annotating…", async () => {
    const start = startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    fireEvent.click(within(await panel()).getByRole("button", { name: "Annotate" }));
    expect(await within(await panel()).findByText("Annotating…", { selector: "span" })).toBeInTheDocument();
    expect(start).toHaveBeenCalledWith(ID, false);
  });

  it("says Annotating… where the button was while a run is queued, running or about to start by itself; the status bar says nothing", async () => {
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotation({ auto_pending: true }),
    });
    const p = await panel();
    expect(await within(p).findByText("Annotating…", { selector: "span" })).toBeInTheDocument();
    expect(within(p).queryByRole("button", { name: "Annotate" })).toBeNull();
    const status = screen.getByRole("region", { name: "Status" });
    expect(within(status).queryByText("Annotating…")).toBeNull();
    await settle(annotation({ status: "running", step: annStep() }));
    expect(within(p).getByText("Annotating…", { selector: "span" })).toBeInTheDocument();
  });

  it("starts by itself: the values show without a click", async () => {
    const start = vi.spyOn(api, "startAnnotation");
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotation({ auto_pending: true }) });
    const p = await panel();
    await within(p).findByText("Annotating…", { selector: "span" });
    await settle(annotated({ step: annStep({ status: "done" }) }));
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it("a run that started by itself takes no focus when it ends; its end is said", async () => {
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotation({ auto_pending: true }) });
    const p = await panel();
    await within(p).findByText("Annotating…", { selector: "span" });
    (document.activeElement as HTMLElement | null)?.blur();
    await settle(annotated({ step: annStep({ status: "done" }) }));
    await within(p).findByText("Model suggestion");
    await waitFor(() => expect(p.querySelector('[aria-live="polite"]')).toHaveTextContent("Annotation ready"));
    expect(document.activeElement).toBe(document.body);
  });

  it("reads GET again every 2 s while a run is on its way, and stops after", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotation({ auto_pending: true }) });
      await within(await panel()).findByText("Annotating…", { selector: "span" });
      const get = vi.mocked(api.getAnnotation);
      const before = get.mock.calls.length;
      get.mockResolvedValue(annotated({ step: annStep({ status: "done" }) }));
      await vi.advanceTimersByTimeAsync(2100);
      await within(await panel()).findByText("Model suggestion");
      const after = get.mock.calls.length;
      expect(after).toBeGreaterThan(before);
      await vi.advanceTimersByTimeAsync(6000);
      expect(get.mock.calls.length).toBe(after);
    } finally {
      vi.useRealTimers();
    }
  });

  it("Run again runs the model again over the values", async () => {
    const start = startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated({ step: annStep({ status: "done" }) }) });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Run again" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith(ID, true));
    expect(await within(p).findByText("Annotating…", { selector: "span" })).toBeInTheDocument();
  });

  it("while it runs the panel's bar shows the estimate, about n%; a run that ends shows 100% before the values", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    fireEvent.click(within(p).getByRole("button", { name: "Annotate" }));
    const bar = await within(p).findByRole("progressbar", { name: "Annotation progress" });
    expect(bar).toHaveAttribute("aria-valuetext", expect.stringMatching(/^Annotating, about \d+%$/));
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeLessThan(100);
    await settle(annotated({ step: annStep({ status: "done" }) }));
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuenow", "100"));
    expect(within(p).queryByText("Model suggestion")).toBeNull();
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
    expect(within(p).queryByRole("progressbar")).toBeNull();
  });

  it("a run that fails never shows a full bar", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    fireEvent.click(within(p).getByRole("button", { name: "Annotate" }));
    await within(p).findByRole("progressbar", { name: "Annotation progress" });
    const failed = annStep({ status: "failed", error_class: "timeout" });
    await settle(annotation({ status: "failed", step: failed }));
    await within(p).findByRole("button", { name: "Try again" });
    expect(within(p).queryByRole("progressbar")).toBeNull();
  });

  it("a start the server refuses says so in a short line (503: not available)", async () => {
    vi.spyOn(api, "startAnnotation").mockRejectedValue(
      new ApiError(503, "Annotation is not available"),
    );
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    fireEvent.click(within(await panel()).getByRole("button", { name: "Annotate" }));
    expect(await within(await panel()).findByRole("alert")).toHaveTextContent(
      "Not started: Annotation is not available",
    );
    expect(within(await panel()).getByRole("button", { name: "Annotate" })).toBeEnabled();
  });

  it("a start refused by its rate limit (429) says too many starts, not changes", async () => {
    vi.spyOn(api, "startAnnotation").mockRejectedValue(new ApiError(429, "rate limited", 30));
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    fireEvent.click(within(await panel()).getByRole("button", { name: "Annotate" }));
    expect(await within(await panel()).findByRole("alert")).toHaveTextContent(
      "Not started: Too many starts, try again in 30 s",
    );
  });

  it("a start refused because the model is not running says so", async () => {
    vi.spyOn(api, "startAnnotation").mockRejectedValue(
      new ApiError(503, "The annotation model is not running"),
    );
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    fireEvent.click(within(await panel()).getByRole("button", { name: "Annotate" }));
    expect(await within(await panel()).findByRole("alert")).toHaveTextContent(
      "Not started: The annotation model is not running",
    );
    expect(within(await panel()).queryByText("Annotating…", { selector: "span" })).toBeNull();
  });

  it("a run that ended failed says why and offers Try again", async () => {
    const start = vi.spyOn(api, "startAnnotation").mockResolvedValue({ step_id: "st-2" });
    const failed = annStep({ status: "failed", error_class: "bad_input" });
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      steps: [step({}), failed],
      ann: annotation({ status: "failed", step: failed }),
    });
    const p = await panel();
    expect(
      await within(p).findByText("Annotation failed: no title, abstract or introduction was found"),
    ).toBeInTheDocument();
    fireEvent.click(within(p).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith(ID, true));
  });

  it("is not offered where the server cannot annotate", async () => {
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotation({ available: false }) });
    const text = await screen.findByRole("region", { name: "Text" });
    await within(text).findByText(TEXT);
    expect(within(text).queryByRole("region", { name: "Annotation" })).toBeNull();
  });

  it("lists the fields that have values, labelled as a model suggestion, with their counts", async () => {
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
    expect(within(p).getByText("fake-annotator")).toBeInTheDocument();
    expect(within(p).getAllByRole("term").map((t) => t.textContent)).toEqual([
      "Organism part",
      "Organism",
      "Kingdom",
    ]);
    expect(within(p).getByRole("button", { name: "Taxus brevifolia (2 in the text)" })).toBeInTheDocument();
    expect(within(p).getByRole("button", { name: "bark (1 in the text)" })).toBeInTheDocument();
    // inferred, not in the text: no button
    expect(within(p).queryByRole("button", { name: /Plantae/ })).toBeNull();
    expect(within(p).getByText(/not in the text/)).toBeInTheDocument();
  });

  it("marks every occurrence in the text; a click shows the first, the next click the next", async () => {
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    const text = screen.getByRole("group", { name: "Paper text" });
    await waitFor(() => expect(text.querySelectorAll("mark")).toHaveLength(3));
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual([
      "bark",
      "Taxus brevifolia",
      "Taxus brevifolia",
    ]);
    const taxus = within(p).getByRole("button", { name: /^Taxus brevifolia/ });
    fireEvent.click(taxus);
    const current = () => [...text.querySelectorAll("mark[data-current]")];
    expect(current()).toHaveLength(1);
    expect(current()[0]).toBe(text.querySelectorAll("mark")[1]);
    expect(taxus).toHaveAttribute("aria-current", "true");
    expect(within(p).getByRole("status")).toHaveTextContent("Taxus brevifolia: 1 of 2, Organism");
    fireEvent.click(taxus);
    expect(current()[0]).toBe(text.querySelectorAll("mark")[2]);
    expect(within(p).getByRole("status")).toHaveTextContent("Taxus brevifolia: 2 of 2");
    fireEvent.click(taxus); // around to the first
    expect(current()[0]).toBe(text.querySelectorAll("mark")[1]);
    fireEvent.click(within(p).getByRole("button", { name: /^bark/ }));
    expect(current()[0]?.textContent).toBe("bark");
    expect(taxus).not.toHaveAttribute("aria-current");
  });

  it("colours each field by its family: legend swatch, value chips and marks, each mark named", async () => {
    const values = { ...annotated().values!, geo_location: ["Oregon"] };
    const positions = { ...annotated().positions!, geo_location: { Oregon: [at("Oregon")] } };
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated({ output: values, values, positions }) });
    const p = await panel();
    const term = (name: string) => within(p).getAllByRole("term").find((t) => t.textContent === name)!;
    // the legend: a decorative swatch of the family before each field's name
    for (const [label, family] of [
      ["Organism", "organism"],
      ["Kingdom", "organism"],
      ["Organism part", "part"],
      ["Place", "place"],
    ] as const) {
      const swatch = term(label).querySelector(".pv-swatch");
      expect(swatch).toHaveClass(`pv-fam--${family}`);
      expect(swatch).toHaveAttribute("aria-hidden", "true");
    }
    expect(within(p).getByRole("button", { name: /^Taxus brevifolia/ })).toHaveClass("pv-fam--organism");
    expect(within(p).getByRole("button", { name: /^bark/ })).toHaveClass("pv-fam--part");
    expect(within(p).getByRole("button", { name: /^Oregon/ })).toHaveClass("pv-fam--place");
    expect(within(p).getByText("Plantae").closest(".pv-ann__value")).toHaveClass("pv-fam--organism");
    const text = screen.getByRole("group", { name: "Paper text" });
    const marks = [...text.querySelectorAll("mark")];
    // the field is named for pointer users (title) and for screen readers (aria-description)
    for (const m of marks) expect(m.getAttribute("aria-description")).toBe(m.title);
    expect(marks.map((m) => [m.textContent, m.className, m.title])).toEqual([
      ["bark", "pv-mark pv-fam--part", "Organism part"],
      ["Taxus brevifolia", "pv-mark pv-fam--organism", "Organism"],
      ["Taxus brevifolia", "pv-mark pv-fam--organism", "Organism"],
      ["Oregon", "pv-mark pv-fam--place", "Place"],
    ]);
    // no style attribute anywhere in the text or the panel (strict CSP)
    expect(text.querySelector("[style]")).toBeNull();
    expect(p.querySelector("[style]")).toBeNull();
    // the occurrence a click went to keeps its family and says its field
    fireEvent.click(within(p).getByRole("button", { name: /^Oregon/ }));
    const current = text.querySelector("mark[data-current]")!;
    expect(current).toHaveClass("pv-mark", "pv-fam--place", "pv-mark--current");
    expect(within(p).getByRole("status")).toHaveTextContent("Oregon: 1 of 1, Place");
  });

  it("a span found in two fields is one mark in the first field's colour, named by both", async () => {
    const values = { ...noValues(), trivial_name: ["bark"], organism_part: ["bark"] };
    const positions = { trivial_name: { bark: [at("bark")] }, organism_part: { bark: [at("bark")] } };
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotated({ output: values, values, positions }),
    });
    await panel();
    const text = screen.getByRole("group", { name: "Paper text" });
    await waitFor(() => expect(text.querySelectorAll("mark")).toHaveLength(1));
    const mark = text.querySelector("mark")!;
    expect(mark.textContent).toBe("bark");
    expect(mark.querySelector("mark")).toBeNull();
    expect(mark).toHaveClass("pv-fam--part");
    expect(mark.title).toBe("Organism part, Compound names");
    expect(mark).toHaveAttribute("aria-description", "Organism part, Compound names");
  });

  it("shows hostile model text as text, and values named __proto__ or constructor like any other", async () => {
    const hostile = "<img src=x onerror=window.__xss=1>";
    const doc: DoclingDoc = {
      texts: [{ self_ref: "#/texts/0", label: "text", text: `__proto__ and constructor ${hostile}` }],
    };
    const values = { ...noValues(), trivial_name: ["__proto__", "constructor", hostile] };
    const positions = JSON.parse(
      JSON.stringify({
        trivial_name: { __proto__: [[0, 0, 9]], constructor: [[0, 14, 25]], [hostile]: [[0, 26, 26 + hostile.length]] },
      }),
    ) as AnnotationOut["positions"];
    // JSON.stringify drops a literal __proto__ key: build it as the API sends it
    positions!.trivial_name = JSON.parse(
      `{"__proto__": [[0, 0, 9]], "constructor": [[0, 14, 25]], ${JSON.stringify(hostile)}: [[0, 26, ${26 + hostile.length}]]}`,
    ) as Record<string, [number, number, number][]>;
    renderAt(paper([segment("s1")]), {
      doc,
      ann: annotated({ output: values, values, positions }),
    });
    const p = await panel();
    expect(await within(p).findByRole("button", { name: "__proto__ (1 in the text)" })).toBeInTheDocument();
    expect(within(p).getByRole("button", { name: "constructor (1 in the text)" })).toBeInTheDocument();
    expect(within(p).getByRole("button", { name: `${hostile} (1 in the text)` })).toBeInTheDocument();
    const text = screen.getByRole("group", { name: "Paper text" });
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual([
      "__proto__",
      "constructor",
      hostile,
    ]);
    expect(document.querySelector('img[src="x"]')).toBeNull();
    expect((window as { __xss?: unknown }).__xss).toBeUndefined();
  });

  it("Edit: one box per field, one value a line; Save sends all 11 fields and shows Curated", async () => {
    const values = { ...annotated().values!, geo_location: ["Oregon"], organism_part: [] };
    const saved = annotated({
      curated: values,
      values,
      curated_positions: { organism_or_species: annotated().positions!.organism_or_species!, geo_location: { Oregon: [at("Oregon")] } },
    });
    const save = vi.spyOn(api, "saveAnnotation").mockResolvedValue(saved);
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    const boxes = within(p).getAllByRole("textbox");
    expect(boxes).toHaveLength(11);
    expect(within(p).getByLabelText("Compound series")).toHaveFocus();
    expect(within(p).getByLabelText("Organism")).toHaveValue("Taxus brevifolia");
    fireEvent.change(within(p).getByLabelText("Organism part"), { target: { value: "" } });
    fireEvent.change(within(p).getByLabelText("Place"), { target: { value: " Oregon \n\nOregon" } });
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    const sent = save.mock.calls[0]![1];
    expect(Object.keys(sent)).toEqual(FIELDS.map(([k]) => k));
    expect(sent.geo_location).toEqual(["Oregon"]);
    expect(sent.organism_part).toEqual([]);
    expect(await within(p).findByText("Curated")).toBeInTheDocument();
    expect(within(p).getByRole("button", { name: "Oregon (1 in the text)" })).toBeInTheDocument();
    expect(within(p).getByRole("button", { name: "Edit" })).toHaveFocus();
  });

  it("Save refuses a value longer than the field takes, and sends nothing", async () => {
    const save = vi.spyOn(api, "saveAnnotation");
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    fireEvent.change(within(p).getByLabelText("Kingdom"), { target: { value: "x".repeat(61) } });
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    expect(await within(p).findByRole("alert")).toHaveTextContent(
      "A value in Kingdom is longer than 60 characters.",
    );
    expect(save).not.toHaveBeenCalled();
  });

  it("Save checks each field against the limit the API sends with it", async () => {
    const save = vi.spyOn(api, "saveAnnotation");
    const fields = FIELDS.map(([key, label]) => ({ key, label, max_length: key === "Kingdom" ? 12 : 500 }));
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated({ fields }) });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    fireEvent.change(within(p).getByLabelText("Kingdom"), { target: { value: "x".repeat(13) } });
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    expect(await within(p).findByRole("alert")).toHaveTextContent(
      "A value in Kingdom is longer than 12 characters.",
    );
    expect(save).not.toHaveBeenCalled();
  });

  it.each([
    [new ApiError(429, "rate limited", 30), "Not saved: Too many changes, try again in 30 s"],
    [new ApiError(503, "The server is busy, try again in a moment."), "Not saved: The server is busy, try again in a moment."],
    [new ApiError(422, "Value error, at most 300 values in all"), "Not saved: Value error, at most 300 values in all"],
  ])("a refused save (%s) says why and keeps what was typed", async (err, said) => {
    vi.spyOn(api, "saveAnnotation").mockRejectedValue(err);
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    fireEvent.change(within(p).getByLabelText("Place"), { target: { value: "Oregon" } });
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    expect(await within(p).findByRole("alert")).toHaveTextContent(said);
    expect(within(p).getByLabelText("Place")).toHaveValue("Oregon");
    expect(within(p).getByRole("button", { name: "Save" })).toBeEnabled();
    fireEvent.click(within(p).getByRole("button", { name: "Cancel" }));
    expect(within(p).queryByRole("alert")).toBeNull();
  });

  it("Save refuses more than 300 values in all before asking the server", async () => {
    const save = vi.spyOn(api, "saveAnnotation");
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    const lines = (n: number, tag: string) => Array.from({ length: n }, (_, i) => `${tag}${i}`).join("\n");
    fireEvent.change(within(p).getByLabelText("IUPAC names"), { target: { value: lines(150, "a") } });
    fireEvent.change(within(p).getByLabelText("Compound names"), { target: { value: lines(150, "b") } });
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    expect(await within(p).findByRole("alert")).toHaveTextContent("At most 300 values in all (303 now).");
    expect(save).not.toHaveBeenCalled();
  });

  it("a refused reset (429) says so where it can be seen", async () => {
    const curated = { ...annotated().values!, organism_part: [] };
    vi.spyOn(api, "resetAnnotation").mockRejectedValue(new ApiError(429, "rate limited", 30));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotated({ curated, values: curated, curated_positions: {} }),
    });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Reset to model" }));
    expect(await within(p).findByRole("alert")).toHaveTextContent(
      "Not reset: Too many changes, try again in 30 s",
    );
    expect(within(p).getByText("Curated")).toBeInTheDocument();
  });

  it("Cancel and Escape leave the values as they were; unchanged values are not saved", async () => {
    const save = vi.spyOn(api, "saveAnnotation");
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, ann: annotated() });
    const p = await panel();
    fireEvent.click(await within(p).findByRole("button", { name: "Edit" }));
    fireEvent.change(within(p).getByLabelText("Place"), { target: { value: "Mars" } });
    fireEvent.click(within(p).getByRole("button", { name: "Cancel" }));
    expect(within(p).queryByText("Mars")).toBeNull();
    fireEvent.click(within(p).getByRole("button", { name: "Edit" }));
    fireEvent.keyDown(within(p).getByLabelText("Place"), { key: "Escape" });
    expect(within(p).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(p).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(p).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(within(p).queryByRole("textbox")).toBeNull());
    expect(save).not.toHaveBeenCalled();
  });

  it("Reset to model asks first, then shows the model's values", async () => {
    const curated = { ...annotated().values!, organism_part: [] };
    const reset = vi.spyOn(api, "resetAnnotation").mockResolvedValue(annotated());
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotated({ curated, values: curated, curated_positions: {} }),
    });
    const p = await panel();
    expect(await within(p).findByText("Curated")).toBeInTheDocument();
    fireEvent.click(within(p).getByRole("button", { name: "Reset to model" }));
    expect(reset).not.toHaveBeenCalled();
    fireEvent.click(within(p).getByRole("button", { name: "Reset to model" }));
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
    expect(reset).toHaveBeenCalledWith(ID);
    // the Reset button is gone: the focus is on Edit, not dropped to the page
    await waitFor(() => expect(document.activeElement).toBe(within(p).getByRole("button", { name: "Edit" })));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(within(p).queryByRole("button", { name: "Reset to model" })).toBeNull();
  });

  it("after Annotate the focus stays in the panel; the end of the run is said and Edit takes the focus", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    const button = within(p).getByRole("button", { name: "Annotate" });
    button.focus();
    fireEvent.click(button);
    await within(p).findByText("Annotating…", { selector: "span" });
    expect(document.activeElement).toBe(p);
    const live = p.querySelector('[aria-live="polite"]')!;
    expect(live).toHaveTextContent("Annotating…");
    await settle(annotated({ step: annStep({ status: "done" }) }));
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
    await waitFor(() => expect(live).toHaveTextContent("Annotation ready"));
    expect(document.activeElement).toBe(within(p).getByRole("button", { name: "Edit" }));
  });

  it("a run that ends failed is said, and Try again takes the focus", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    fireEvent.click(within(p).getByRole("button", { name: "Annotate" }));
    await within(p).findByText("Annotating…", { selector: "span" });
    const failed = annStep({ status: "failed", error_class: "timeout" });
    await settle(annotation({ status: "failed", step: failed }));
    const again = await within(p).findByRole("button", { name: "Try again" });
    const live = p.querySelector('[aria-live="polite"]')!;
    await waitFor(() => expect(live).toHaveTextContent("Annotation failed: it took too long"));
    expect(document.activeElement).toBe(again);
  });

  it("a run that fails while earlier values are shown is said as failed (B-rr1)", async () => {
    // a re-run (e.g. asked from another tab) over values the panel already shows
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotated({ status: "running", step: annStep() }),
    });
    const p = await panel();
    await within(p).findByText("Annotating…", { selector: "span" });
    const failed = annStep({ status: "failed", error_class: "timeout" });
    await settle(annotated({ status: "failed", step: failed }));
    expect(await within(p).findByText("The last run failed: it took too long")).toBeInTheDocument();
    const live = p.querySelector('[aria-live="polite"]')!;
    await waitFor(() => expect(live).toHaveTextContent("Annotation failed: it took too long"));
    expect(live).not.toHaveTextContent("Annotation ready");
  });

  it("a start the server refuses gives the focus back to Annotate (B-rr2)", async () => {
    vi.spyOn(api, "startAnnotation").mockRejectedValue(new ApiError(503, "The annotation model is not running"));
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    const button = within(p).getByRole("button", { name: "Annotate" });
    button.focus();
    fireEvent.click(button);
    await within(p).findByRole("alert");
    await waitFor(() =>
      expect(document.activeElement).toBe(within(p).getByRole("button", { name: "Annotate" })),
    );
  });

  it("a focus the panel moves after a mouse click shows no keyboard ring; a key brings it back (B-rr4)", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    const button = within(p).getByRole("button", { name: "Annotate" });
    fireEvent.pointerDown(button);
    button.focus();
    fireEvent.click(button);
    await within(p).findByText("Annotating…", { selector: "span" });
    expect(document.activeElement).toBe(p);
    expect(p).toHaveAttribute("data-quiet-focus");
    fireEvent.keyDown(p, { key: "Tab" });
    expect(p).not.toHaveAttribute("data-quiet-focus");
  });

  it("a focus the panel moves after a key keeps the keyboard ring (B-rr4)", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    const button = within(p).getByRole("button", { name: "Annotate" });
    button.focus();
    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.click(button);
    await within(p).findByText("Annotating…", { selector: "span" });
    expect(document.activeElement).toBe(p);
    expect(p).not.toHaveAttribute("data-quiet-focus");
  });

  it("a focus elsewhere on the page is left where it is when the run ends", async () => {
    startable();
    renderAt(paper([segment("s1")]), { doc: ANN_DOC });
    const p = await panel();
    fireEvent.click(within(p).getByRole("button", { name: "Annotate" }));
    await within(p).findByText("Annotating…", { selector: "span" });
    const download = screen.getByRole("button", { name: "Download text" });
    download.focus();
    await settle(annotated({ step: annStep({ status: "done" }) }));
    await within(p).findByText("Model suggestion");
    await waitFor(() => expect(p.querySelector('[aria-live="polite"]')).toHaveTextContent("Annotation ready"));
    expect(document.activeElement).toBe(download);
  });

  it("a re-read that fails keeps the last answer; the next good read shows the run's end", async () => {
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotation({ status: "running", step: annStep() }),
    });
    const p = await panel();
    await within(p).findByText("Annotating…", { selector: "span" });
    vi.mocked(api.getAnnotation).mockRejectedValueOnce(new ApiError(429, "rate limited"));
    await client.invalidateQueries({ queryKey: ["annotation", ID] });
    expect(within(p).getByText("Annotating…", { selector: "span" })).toBeInTheDocument();
    await settle(annotated({ step: annStep({ status: "done" }) }));
    expect(await within(p).findByText("Model suggestion")).toBeInTheDocument();
  });

  it("the same place said twice is said again (the live text changes)", async () => {
    const values = { ...noValues(), organism_part: ["bark"] };
    renderAt(paper([segment("s1")]), {
      doc: ANN_DOC,
      ann: annotated({ output: values, values }),
    });
    const p = await panel();
    const bark = await within(p).findByRole("button", { name: /^bark/ });
    const live = p.querySelector('[aria-live="polite"]')!;
    fireEvent.click(bark);
    const first = live.textContent;
    fireEvent.click(bark);
    expect(live.textContent).not.toBe(first);
    expect(live).toHaveTextContent("bark: 1 of 1");
  });

  it("a done paper whose annotation runs says No pages / No structures found", async () => {
    renderAt(paper([], { pages: 0 }), {
      doc: ANN_DOC,
      ann: annotation({ status: "running", step: annStep() }),
    });
    expect(await screen.findByText("No structures found.")).toBeInTheDocument();
    expect(screen.getByText("No pages.")).toBeInTheDocument();
    expect(screen.queryByText(/appear here as/)).toBeNull();
  });

  it("reads the annotation again when the text is read later: an auto run that starts then shows", async () => {
    renderAt(paper([segment("s1")], { status: "processing" }), {
      doc: ANN_DOC,
      steps: [step({ status: "running", finished_at: null })],
    });
    expect(await screen.findByText("The text of this paper is not ready")).toBeInTheDocument();
    await waitFor(() => expect(api.getAnnotation).toHaveBeenCalled());
    const before = vi.mocked(api.getAnnotation).mock.calls.length;
    vi.mocked(api.getAnnotation).mockResolvedValue(annotation({ auto_pending: true }));
    vi.mocked(api.getSteps).mockResolvedValue({ steps: [step({})] });
    await client.invalidateQueries({ queryKey: ["steps", ID] });
    const p = await panel();
    expect(await within(p).findByText("Annotating…", { selector: "span" })).toBeInTheDocument();
    expect(vi.mocked(api.getAnnotation).mock.calls.length).toBeGreaterThan(before);
  });

  it("reads the R-group list again when the text or a structure is read later", async () => {
    const get = vi
      .spyOn(api, "getPaperRgroups")
      .mockResolvedValue({ available: true, extractions: [], auto_pending: [] });
    const scaffold = segment("s1", { predictions: [prediction({ rgroups: ["R1"] })] });
    renderAt(paper([scaffold], { status: "processing" }), {
      doc: ANN_DOC,
      steps: [step({ status: "running", finished_at: null })],
    });
    await waitFor(() => expect(get).toHaveBeenCalled());
    const before = get.mock.calls.length;
    vi.mocked(api.getSteps).mockResolvedValue({ steps: [step({})] });
    await client.invalidateQueries({ queryKey: ["steps", ID] });
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before));
  });

  it("never reads the paper's steps for the annotation: an annotate step there changes nothing", async () => {
    renderAt(paper([segment("s1")]), { doc: ANN_DOC, steps: [step({}), annStep()] });
    const p = await panel();
    expect(await within(p).findByRole("button", { name: "Annotate" })).toBeInTheDocument();
    expect(within(p).queryByText("Annotating…", { selector: "span" })).toBeNull();
  });
});

describe("Paper view: the main figure", () => {
  it("marks a page with structures as the main figure from its caption; again clears it", async () => {
    const segs = [segment("s1", { page: 0 }), segment("s2", { page: 1 })];
    const put = vi.spyOn(api, "putMainFigure").mockResolvedValue({ main_figure_page: 1 });
    renderAt(paper(segs));
    const pages = await screen.findByRole("region", { name: "Pages" });
    const mark = await within(pages).findByRole("button", { name: "Main figure: Page 2" });
    expect(mark).toHaveAttribute("aria-pressed", "false");
    // a page without structures has no button
    expect(within(pages).queryByRole("button", { name: "Main figure: Page 3" })).toBeNull();

    vi.mocked(api.getPaper).mockResolvedValue(paper(segs, { main_figure_page: 1 }));
    fireEvent.click(mark);
    await waitFor(() => expect(put).toHaveBeenCalledWith(ID, 1));
    await waitFor(() => expect(mark).toHaveAttribute("aria-pressed", "true"));

    put.mockResolvedValue({ main_figure_page: null });
    vi.mocked(api.getPaper).mockResolvedValue(paper(segs, { main_figure_page: null }));
    fireEvent.click(mark);
    await waitFor(() => expect(put).toHaveBeenLastCalledWith(ID, null));
    await waitFor(() => expect(mark).toHaveAttribute("aria-pressed", "false"));
  });

  it("a mark that is not saved goes back and says why", async () => {
    vi.spyOn(api, "putMainFigure").mockRejectedValue(new ApiError(503, "The server is busy."));
    renderAt(paper([segment("s1", { page: 0 })]));
    const mark = await screen.findByRole("button", { name: "Main figure: Page 1" });
    fireEvent.click(mark);
    expect(await screen.findByText("Not saved: The server is busy.")).toBeInTheDocument();
    expect(mark).toHaveAttribute("aria-pressed", "false");
  });

  it("lists the main figure first and a repeat once, on its main card", async () => {
    renderAt(
      paper(
        [
          segment("s1", { page: 0 }),
          segment("s2", { page: 1 }),
          segment("s3", { page: 2, repeat_of: "s2" }), // s2's compound again
        ],
        { main_figure_page: 1 },
      ),
    );
    const list = await screen.findByRole("region", { name: "Structures" });
    const cards = await within(list).findAllByRole("article");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      "[01] · Page 2, To check",
      "[02] · Page 1, To check",
    ]);
    expect(within(cards[0]!).getByText("Also on page 3")).toBeInTheDocument();
    expect(within(cards[1]!).queryByText(/Also on/)).toBeNull();
    expect(screen.getByRole("list", { name: "Counts" })).toHaveTextContent("2 structures");

    // the repeat's marker carries its main structure's tag and selects that card
    await loadPage(3);
    fireEvent.click(screen.getByRole("button", { name: "Structure [01] on page 3" }));
    expect(screen.getByTestId("where")).toHaveTextContent("s=s2");
  });
});

describe("Paper view: a main structure and its repeats", () => {
  const accepted = { status: "accepted" as const, smiles: null, molfile: null, note: null };

  it("an accepted repeat makes its main card accepted, and COCONUT gets the compound once", async () => {
    renderAt(
      paper(
        [
          segment("s1", { page: 0 }),
          segment("s2", { page: 2, repeat_of: "s1", curation: accepted }),
        ],
        { main_figure_page: 0 },
      ),
    );
    const list = await screen.findByRole("region", { name: "Structures" });
    expect(await within(list).findAllByRole("article")).toHaveLength(1);
    expect(card("[01]")).toHaveAttribute("aria-label", "[01] · Page 1, Accepted");
    expect(screen.getByRole("button", { name: "Send 1 to COCONUT" })).toBeEnabled();
  });

  it("Reject on a main card is a decision for its group: the card shows Rejected at once", async () => {
    const put = vi
      .spyOn(api, "putCuration")
      .mockImplementation(() => new Promise<never>(() => undefined)); // still on the wire
    renderAt(
      paper([segment("s1", { page: 0 }), segment("s2", { page: 2, repeat_of: "s1" })], {
        main_figure_page: 0,
      }),
      { search: "" },
    );
    await screen.findByRole("button", { name: "Reject [01]" });
    fireEvent.click(screen.getByRole("button", { name: "Reject [01]" }));
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(put.mock.calls[0]![0]).toBe("s1");
    expect(put.mock.calls[0]![2]).toBe(true);
    // without the repeat shown rejected too, the group would still be to check
    await waitFor(() =>
      expect(card("[01]")).toHaveAttribute("aria-label", "[01] · Page 1, Rejected"),
    );
  });

  it("while the server could not link the repeats, nothing goes to COCONUT", async () => {
    renderAt(
      paper([segment("s1", { page: 0, curation: accepted })], {
        main_figure_page: 0,
        links_ready: false,
      }),
    );
    const send = await screen.findByRole("button", { name: "Send 0 to COCONUT" });
    expect(send).toBeDisabled();
    expect(screen.getByText("Checking repeats, try again soon")).toBeInTheDocument();
  });

  it("clicking a repeat's marker selects its main card and leaves the pages column where it was", async () => {
    renderAt(
      paper([segment("s1", { page: 0 }), segment("s2", { page: 2, repeat_of: "s1" })], {
        main_figure_page: 0,
      }),
    );
    await loadPage(3);
    const pages = screen.getByRole("region", { name: "Pages" });
    const scrolled = vi.fn();
    pages.scrollTo = scrolled as unknown as typeof pages.scrollTo;
    fireEvent.click(screen.getByRole("button", { name: "Structure [01] on page 3" }));
    expect(screen.getByTestId("where")).toHaveTextContent("s=s1");
    await waitFor(() => expect(card("[01]")).toHaveAttribute("aria-current", "true"));
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("a marked page without structures keeps its button, so the mark can be cleared", async () => {
    const put = vi.spyOn(api, "putMainFigure").mockResolvedValue({ main_figure_page: null });
    renderAt(paper([segment("s1", { page: 0 })], { main_figure_page: 2 }));
    const mark = await screen.findByRole("button", { name: "Main figure: Page 3" });
    expect(mark).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Main figure: Page 2" })).toBeNull();
    fireEvent.click(mark);
    await waitFor(() => expect(put).toHaveBeenCalledWith(ID, null));
  });

  it("?s= naming a repeat selects its main card in the Paper view", async () => {
    const segs = [segment("s1", { page: 0 }), segment("s2", { page: 2, repeat_of: "s1" })];
    renderAt(paper(segs, { main_figure_page: 0 }), { search: "?view=paper&s=s2" });
    await waitFor(() => expect(card("[01]")).toHaveAttribute("aria-current", "true"));
  });

  it("?s= naming a repeat selects its main card in the grid", async () => {
    const segs = [segment("s1", { page: 0 }), segment("s2", { page: 2, repeat_of: "s1" })];
    renderAt(paper(segs, { main_figure_page: 0 }), { search: "?s=s2" });
    await waitFor(() => expect(card("[01]")).toHaveAttribute("aria-current", "true"));
  });
});

describe("built structures (Markush Phase 3)", () => {
  it("a built card has no box of its own on the page (its scaffold's box is there)", async () => {
    const scaffold = segment("s1", { page: 0 });
    const built = segment("s2", {
      page: 0,
      idx: 10001,
      built_from: "s1",
      compound_id: "3a",
      predictions: [prediction({ id: "pb", engine: "enumerated", smiles: "COc1ccccc1" })],
    });
    renderAt(paper([scaffold, built], { pages: 1 }), { steps: [step({}), step({ id: "r0", kind: "render_page", page: 0 })] });
    const img = await loadPage(1);
    const sheet = img.parentElement!;
    await waitFor(() => expect(sheet.querySelectorAll("[data-marker]")).toHaveLength(1));
    expect(sheet.querySelector('[data-marker="s1"]')).not.toBeNull();
    expect(sheet.querySelector('[data-marker="s2"]')).toBeNull();
  });

  it("in the list, the built cards sit in one box under their scaffold (owner, 2026-11-26)", async () => {
    const scaffold = segment("s1", { page: 0 });
    const built = segment("s2", {
      page: 0,
      idx: 10001,
      built_from: "s1",
      compound_id: "3a",
      predictions: [prediction({ id: "pb", engine: "enumerated", smiles: "COc1ccccc1" })],
    });
    renderAt(paper([scaffold, built], { pages: 1 }));
    const family = await screen.findByRole("group", { name: "Built from [01]" });
    expect(within(family).getAllByRole("article").map((a) => a.getAttribute("data-segment-id"))).toEqual(["s2"]);
  });
});

describe("COCONUT side form (owner decision 2026-11-25)", () => {
  it("Accept in the Paper view opens the form for that structure; Close hides it", async () => {
    vi.spyOn(api, "putCuration").mockImplementation(() => new Promise<never>(() => undefined));
    renderAt(paper([segment("s1", { page: 0, compound_id: "12" })]));
    fireEvent.click(await screen.findByRole("button", { name: "Accept [01]" }));
    const form = await screen.findByRole("complementary", { name: "COCONUT [01]" });
    expect(await within(form).findByLabelText("Name")).toHaveValue("Compound 12"); // once the status lands
    fireEvent.click(within(form).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("complementary", { name: "COCONUT [01]" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(card("[01]")));
  });

  it("Use this one in Compare (an accept) opens the form too (owner, 2026-11-26)", async () => {
    vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }) as never);
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const preds = ["decimer", "molparser", "molscribe"].map((engine) => prediction({ id: `p-${engine}`, engine }));
    renderAt(paper([segment("s1", { page: 0, compound_id: "12", predictions: preds })]));
    fireEvent.click(await screen.findByRole("button", { name: "Compare [01]" }));
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this one, DECIMER" }));
    const form = await screen.findByRole("complementary", { name: "COCONUT [01]" });
    expect(await within(form).findByLabelText("Name")).toHaveValue("Compound 12");
  });

  it("Edit and use opens the editor on that engine's answer; saving accepts the edit and opens the form (owner, 2026-11-27)", async () => {
    const put = vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }) as never);
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const preds = ["decimer", "molparser", "molscribe"].map((engine, i) =>
      prediction({ id: `p-${engine}`, engine, smiles: ["CCO", "CCN", "CCC"][i]! }),
    );
    renderAt(paper([segment("s1", { page: 0, compound_id: "12", predictions: preds })]));
    fireEvent.click(await screen.findByRole("button", { name: "Compare [01]" }));
    const compare = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(compare).getByRole("button", { name: "Edit and use, MolParser" }));
    const editor = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(within(editor).getByLabelText("SMILES")).toHaveValue("CCN");
    expect(screen.queryByRole("dialog", { name: /Compare engines/ })).toBeNull();
    fireEvent.change(within(editor).getByLabelText("SMILES"), { target: { value: "CCNC" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Save SMILES" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]![1]).toMatchObject({ status: "accepted", smiles: "CCNC" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit structure" })).toBeNull());
    expect(await screen.findByRole("complementary", { name: "COCONUT [01]" })).toBeInTheDocument();
  });

  it("Edit and use keeps the paper's coordinates: the editor opens the answer laid out like the paper (owner, 2026-11-27)", async () => {
    vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }) as never);
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const laidOut = vi.spyOn(api, "smilesToMolfile").mockResolvedValue("LAID OUT MOLFILE");
    const layout = paperLayout();
    const preds = [
      prediction({ id: "p-decimer", engine: "decimer", smiles: "CCO" }),
      prediction({ id: "p-molparser", engine: "molparser", smiles: "CCN" }),
      prediction({ id: "p-molscribe", engine: "molscribe", smiles: "CCC", valid: false, layout }),
    ];
    renderAt(paper([segment("s1", { page: 0, predictions: preds })]));
    fireEvent.click(await screen.findByRole("button", { name: "Compare [01]" }));
    const compare = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(compare).getByRole("button", { name: "Edit and use, MolParser" }));
    await screen.findByRole("dialog", { name: "Edit structure" });
    expect(laidOut).toHaveBeenCalledWith("CCN", layout);
  });

  it("a closed form stays closed after Review and back (simplify review, 2026-11-26)", async () => {
    vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }) as never);
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const preds = ["decimer", "molparser", "molscribe"].map((engine) => prediction({ id: `p-${engine}`, engine }));
    renderAt(paper([segment("s1", { page: 0, compound_id: "12", predictions: preds })]));
    fireEvent.click(await screen.findByRole("button", { name: "Compare [01]" }));
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this one, DECIMER" }));
    const form = await screen.findByRole("complementary", { name: "COCONUT [01]" });
    fireEvent.click(within(form).getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Paper" }));
    await screen.findByRole("region", { name: "Paper view" });
    expect(screen.queryByRole("complementary", { name: /^COCONUT/ })).toBeNull();
  });

  it("Reject opens nothing", async () => {
    vi.spyOn(api, "putCuration").mockImplementation(() => new Promise<never>(() => undefined));
    renderAt(paper([segment("s1", { page: 0 })]));
    fireEvent.click(await screen.findByRole("button", { name: "Reject [01]" }));
    expect(screen.queryByRole("complementary", { name: /^COCONUT/ })).toBeNull();
  });
});
