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
import { BulkPartialError, createQueryClient, keys, useBulkCuration } from "../api/queries";
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
import { measuredText } from "./trust";
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
vi.mock("../api/depictions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/depictions")>()),
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
    first_author: null,
    year: null,
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    structures: segments.length,
    accepted: segments.filter((s) => s.curation?.status === "accepted").length,
    rejected: segments.filter((s) => s.curation?.status === "rejected").length,
    to_review: segments.filter((s) => (s.curation?.status ?? "unchecked") === "unchecked").length,
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
    // a To check card offers Accept and Reject: the visible word starts the name (WCAG 2.5.3),
    // and no key hints (A and R act in focus mode only)
    const accept = within(card("[03]")).getByRole("button", { name: "Accept [03]" });
    const reject = within(card("[03]")).getByRole("button", { name: "Reject [03]" });
    expect(accept).toHaveTextContent(/^Accept$/);
    expect(reject).toHaveTextContent(/^Reject$/);
    expect(card("[03]").querySelector("kbd")).toBeNull();
  });

  it("tags follow (page, idx) order", async () => {
    renderGrid(paper([segment("s9", { page: 1, idx: 0 }), segment("s1", { page: 0, idx: 0 })]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(cards()[0]).toHaveTextContent("[01] · Page 1");
    expect(cards()[1]).toHaveTextContent("[02] · Page 2");
  });

  it("the engines' badge: 3 agree, 2 agree naming both, Differ; nothing while they read", async () => {
    const decimer = prediction({ smiles: "OCC" });
    const molparser = prediction({ engine: "molparser", smiles: "CCO" });
    const molscribe = prediction({ engine: "molscribe", smiles: "CCO" });
    const three = [prediction({ engine: "molscribe" }), prediction({ engine: "molparser" }), prediction()];
    renderGrid(
      paper([
        segment("s1", {
          predictions: three,
          agree: 3,
          agree_of: 3,
          agree_engines: ["decimer", "molparser", "molscribe"],
        }),
        segment("s2", {
          predictions: [molscribe, molparser, decimer],
          agree: 2,
          agree_of: 3,
          agree_engines: ["molparser", "molscribe"],
          default_prediction_id: molparser.id,
        }),
        segment("s3", { predictions: three, agree: 0, agree_of: 3, agree_engines: [] }),
        segment("s4", { predictions: three, agree: null, agree_engines: ["molparser", "molscribe"] }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(4));
    expect(within(card("[01]")).getByText("3 agree")).toBeInTheDocument();
    expect(within(card("[01]")).getByText("DECIMER · Valid")).toBeInTheDocument();
    // The majority's structure is shown (the server's pick), naming its two engines.
    expect(within(card("[02]")).getByText("2 agree")).toHaveAttribute(
      "title",
      `MolParser and MolScribe agree. ${measuredText("agree2")}`,
    );
    expect(within(card("[02]")).getByText("MolParser + MolScribe · Valid")).toBeInTheDocument();
    expect(within(card("[02]")).getByText("CCO")).toBeInTheDocument();
    expect(within(card("[03]")).getByText("Differ")).toBeInTheDocument();
    for (const word of ["agree", "Differ"]) {
      expect(within(card("[04]")).queryByText(new RegExp(word))).toBeNull();
    }
  });

  it("two engines only: 2 of 2 agree, 2 differ", async () => {
    const two = [prediction({ engine: "molscribe" }), prediction()];
    renderGrid(
      paper([
        segment("s1", { predictions: two, agree: 2, agree_of: 2, agree_engines: ["decimer", "molscribe"] }),
        segment("s2", { predictions: two, agree: 0, agree_of: 2, agree_engines: [] }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(within(card("[01]")).getByText("2 of 2 agree")).toBeInTheDocument();
    expect(within(card("[02]")).getByText("2 differ")).toBeInTheDocument();
  });

  it("a background engine that failed is no failure of the card", async () => {
    renderGrid(paper([segment("s1", { predictions: [prediction({ valid: false, smiles: "C(" })] })]), [
      step({ segment_id: "s1", status: "done", created_at: "2026-11-18T10:00:01Z" }),
      step({
        segment_id: "s1",
        engine: "molscribe",
        status: "failed",
        background: true,
        created_at: "2026-11-18T10:00:05Z",
      }),
    ]);
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(card("[01]")).toHaveAccessibleName(/To check/);
    expect(filter("Failed")).toHaveTextContent("0");
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

  it("engines agree: To review; stereo differs: To check, each with its filter", async () => {
    const three = [prediction({ engine: "molscribe" }), prediction({ engine: "molparser" }), prediction()];
    renderGrid(
      paper([
        segment("s1", { predictions: three, agree: 3, agree_of: 3, agree_state: "agree3" }),
        segment("s2", { predictions: three, agree: 0, agree_of: 3, agree_state: "stereo" }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(within(card("[01]")).getByText("To review")).toBeInTheDocument();
    expect(within(card("[01]")).getByRole("button", { name: /^Accept/ })).toBeEnabled();
    expect(within(card("[02]")).getByText("To check")).toBeInTheDocument();
    const badge = within(card("[02]")).getByText("Stereo differs");
    expect(badge).toHaveClass("card__differ");
    expect(badge.title).toContain("different stereo");
    expect(badge.title).toContain(measuredText("stereo"));
    fireEvent.click(screen.getByRole("button", { name: /^To review/ }));
    expect(cards()).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /^To check/ }));
    expect(within(cards()[0]!).getByText("Stereo differs")).toBeInTheDocument();
  });

  it("an old paper's badge still names MolNexTR", async () => {
    const molnextr = prediction({ engine: "molnextr", smiles: "CCO" });
    renderGrid(
      paper([
        segment("s1", {
          predictions: [prediction({ engine: "molscribe", smiles: "CCO" }), molnextr, prediction({ smiles: "CCO" })],
          agree: 3,
          agree_of: 3,
          agree_engines: ["decimer", "molnextr", "molscribe"],
        }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(within(card("[01]")).getByText("3 agree")).toHaveAttribute(
      "title",
      `DECIMER, MolNexTR and MolScribe agree. ${measuredText("agree3")}`,
    );
  });

  it("a card read again with DECIMER hand-drawn says its first run loads the model", async () => {
    const note = "The first run can take about 30 s";
    renderGrid(paper([segment("s1", { predictions: [] }), segment("s2", { predictions: [] })], { status: "processing" }), [
      step({ segment_id: "s1", status: "failed", error_class: "timeout" }),
      step({ segment_id: "s1", status: "queued", engine: "decimer-hand" }),
      step({ segment_id: "s2", status: "running", engine: "molparser" }),
    ]);
    await waitFor(() => expect(cards()).toHaveLength(2));
    await waitFor(() => expect(within(card("[01]")).getByText("Reading…")).toBeInTheDocument());
    expect(card("[01]")).toHaveTextContent(note);
    expect(within(card("[02]")).getByText("Reading…")).toBeInTheDocument();
    expect(card("[02]")).not.toHaveTextContent(note);
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
    // the other three engines, not the one that failed, then Compare
    expect(within(menu).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "DECIMER hand-drawn",
      "MolParser",
      "MolScribe",
      "Compare",
    ]);
    fireEvent.click(within(menu).getByRole("button", { name: "MolParser" }));
    await waitFor(() => expect(run).toHaveBeenCalledWith("s1", "molparser"));
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

describe("the way into focus mode", () => {
  it("Review one by one opens focus mode on the first structure still to check", async () => {
    renderGrid(
      paper([
        segment("s1", { curation: curation({ status: "accepted" }) }),
        segment("s2"),
        segment("s3"),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    fireEvent.click(screen.getByRole("button", { name: "Review one by one" }));
    expect(await screen.findByRole("region", { name: "Focus [02]" })).toBeInTheDocument();
  });

  it("with nothing to check it opens on the first structure", async () => {
    renderGrid(paper([segment("s1", { curation: curation({ status: "accepted" }) })]));
    await waitFor(() => expect(cards()).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Review one by one" }));
    expect(await screen.findByRole("region", { name: "Focus [01]" })).toBeInTheDocument();
  });

  it("is off when the paper has no structures", async () => {
    renderGrid(paper([]));
    expect(await screen.findByRole("button", { name: "Review one by one" })).toBeDisabled();
  });

  it("each card says that Enter opens it", async () => {
    renderGrid(paper([segment("s1"), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    for (const c of cards()) expect(c).toHaveAccessibleDescription("Enter: open");
  });
});

describe("the compound ID", () => {
  it("shows the ID printed by the drawing, with its name when the text gives one", async () => {
    renderGrid(
      paper([
        segment("s1", { compound_id: "12", compound_name: "salsubstolin A" }),
        segment("s2", { compound_id: "8a", compound_name: null }),
        segment("s3"),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(within(card("[01]")).getByText("Compound 12 · salsubstolin A")).toBeInTheDocument();
    expect(within(card("[02]")).getByText("Compound 8a")).toBeInTheDocument();
    expect(within(card("[03]")).queryByText(/^Compound/)).toBeNull();
  });

  it("asks to check a structure that shares its ID with another structure", async () => {
    renderGrid(
      paper([
        segment("s1", { compound_id: "12", same_id_pages: [3] }),
        segment("s2", { page: 3, idx: 0, compound_id: "12", same_id_pages: [0] }),
        segment("s3", { compound_id: "13", same_id_pages: [1, 4] }),
        segment("s4", { compound_id: "14", same_id_pages: [] }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(4));
    expect(within(card("[01]")).getByText("Same ID as compound 12, page 4. Check.")).toBeInTheDocument();
    expect(within(card("[04]")).getByText("Same ID as compound 12, page 1. Check.")).toBeInTheDocument();
    expect(
      within(card("[02]")).getByText("Same ID as compound 13, pages 2, 5. Check."),
    ).toBeInTheDocument();
    expect(within(card("[03]")).queryByText(/Same ID/)).toBeNull();
  });
});

describe("Check this drawing", () => {
  it("a flagged card says so and its Edit opens the editor on it; others say nothing", async () => {
    renderGrid(
      paper([segment("s1", { check_drawing: true }), segment("s2"), segment("s3", { check_drawing: false })]),
    );
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(within(card("[01]")).getByText("Check this drawing")).toBeInTheDocument();
    expect(card("[01]")).toHaveAccessibleName(/Check this drawing$/);
    expect(within(card("[02]")).queryByText("Check this drawing")).toBeNull();
    expect(within(card("[03]")).queryByText("Check this drawing")).toBeNull();
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "Edit [01]" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(dialog).toBeInTheDocument();
  });
});

describe("the card menu (More)", () => {
  it("Edit opens the editor on that structure; a save keeps the note; focus returns to More", async () => {
    const put = vi
      .spyOn(api, "putCuration")
      .mockImplementation((_id, body) => Promise.resolve({ ...body }));
    renderGrid(
      paper([
        segment("s1"),
        segment("s2", { curation: curation({ status: "rejected", note: "keep", smiles: "CCCl" }) }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    const more = within(card("[02]")).getByRole("button", { name: "More for [02]" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    expect(more).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(within(card("[02]")).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(within(dialog).getByLabelText("SMILES")).toHaveValue("CCCl");
    fireEvent.change(within(dialog).getByLabelText("SMILES"), { target: { value: "CCBr" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save SMILES" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]).toEqual([
      "s2",
      { status: "rejected", smiles: "CCBr", molfile: null, note: "keep" },
      false, // the editor's save keeps the status: no decision
    ]);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit structure" })).toBeNull());
    expect(within(card("[02]")).getByRole("button", { name: "More for [02]" })).toHaveFocus();
  });

  it("holds the structure's actions; a SMILES-only edit never takes the prediction's molfile", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const convert = vi.spyOn(api, "smilesToMolfile").mockResolvedValue("CONVERTED");
    renderGrid(
      paper([
        segment("s1", { predictions: [prediction({ molfile: "PREDICTED" })] }),
        segment("s2", {
          curation: curation({ smiles: "CCBr" }),
          predictions: [prediction({ molfile: "PREDICTED" })],
        }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    fireEvent.click(within(card("[02]")).getByRole("button", { name: "More for [02]" }));
    const menu = within(card("[02]")).getByRole("group", { name: "[02] actions" });
    expect(within(card("[02]")).getAllByRole("button", { name: "Copy SMILES" })).toHaveLength(1);
    for (const name of ["Download molfile", "Download image", "Look up in PubChem", "Edit", "Compare"]) {
      expect(within(menu).getByRole("button", { name })).toBeInTheDocument();
    }
    fireEvent.click(within(menu).getByRole("button", { name: "Copy molfile" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("CONVERTED"));
    expect(convert).toHaveBeenCalledWith("CCBr");
    // The unedited [01] copies its prediction's molfile.
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "More for [01]" }));
    fireEvent.click(
      within(within(card("[01]")).getByRole("group", { name: "[01] actions" })).getByRole("button", {
        name: "Copy molfile",
      }),
    );
    await waitFor(() => expect(writeText).toHaveBeenLastCalledWith("PREDICTED"));
  });

  it("Compare in the menu opens Compare engines for that structure", async () => {
    renderGrid(paper([segment("s1", { curation: curation({ status: "accepted" }) })]));
    await waitFor(() => expect(cards()).toHaveLength(1));
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "More for [01]" }));
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "Compare" }));
    expect(await screen.findByRole("dialog", { name: /Compare engines/ })).toBeInTheDocument();
  });

  it("Escape closes the menu without leaving the page; every card has one", async () => {
    renderGrid(
      paper([
        segment("s1", { curation: curation({ status: "accepted" }) }),
        segment("s2", { predictions: [] }),
      ]),
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(within(card("[01]")).getByRole("button", { name: "More for [01]" })).toBeInTheDocument();
    const more = within(card("[02]")).getByRole("button", { name: "More for [02]" });
    fireEvent.click(more);
    const edit = within(card("[02]")).getByRole("button", { name: "Edit" });
    fireEvent.keyDown(edit, { key: "Escape" });
    expect(within(card("[02]")).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(more).toHaveFocus();
  });
});

describe("Compare from a card (F10 review)", () => {
  it("after Use this one from a To check card, focus goes to that card, not the page", async () => {
    vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }));
    renderGrid(paper([segment("s1"), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    const compare = within(card("[02]")).getByRole("button", { name: "Compare [02]" });
    compare.focus();
    fireEvent.click(compare);
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this one, DECIMER" }));
    await waitFor(() => expect(card("[02]")).toHaveAttribute("aria-label", "[02] · Page 1, Accepted"));
    await waitFor(() => expect(card("[02]")).toHaveFocus());
  });
});

describe("Compare and the background engines", () => {
  it("shows a background engine still reading and starts only the idle one", async () => {
    const run = vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "x" });
    renderGrid(paper([segment("s1")]), [
      step({ segment_id: "s1", status: "done" }),
      step({ segment_id: "s1", engine: "molparser", status: "running", background: true }),
    ]);
    await waitFor(() => expect(cards()).toHaveLength(1));
    fireEvent.click(within(card("[01]")).getByRole("button", { name: "Compare [01]" }));
    await screen.findByRole("dialog", { name: /Compare engines/ });
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    expect(run).toHaveBeenCalledWith("s1", "molscribe");
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

describe("selection follows the visible cards (F7 fix round 1)", () => {
  function putOk() {
    return vi
      .spyOn(api, "putCuration")
      .mockImplementation((_id, body) => Promise.resolve({ ...body }));
  }

  it("under To check, select 3 and accept one from its card: the bar acts on the 2 left", async () => {
    putOk();
    const bulk = vi.spyOn(api, "putBulkCuration").mockResolvedValue({ updated: 2 });
    renderGrid(paper([segment("s1"), segment("s2"), segment("s3"), segment("s4")]));
    await waitFor(() => expect(cards()).toHaveLength(4));
    fireEvent.click(filter("To check"));
    for (const t of ["[01]", "[02]", "[03]"]) {
      fireEvent.click(screen.getByRole("checkbox", { name: `Select ${t}` }));
    }
    expect(screen.getByRole("button", { name: "Reject 3" })).toBeInTheDocument();
    fireEvent.click(within(card("[02]")).getByRole("button", { name: /^Accept/ }));
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(screen.getByRole("group", { name: "2 selected" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reject 2" }));
    await waitFor(() => expect(bulk).toHaveBeenCalledTimes(1));
    expect(bulk.mock.calls[0]![1].map((i) => i.segment_id)).toEqual(["s1", "s3"]);
  });

  it("a card that leaves the filter and comes back is not selected again", async () => {
    putOk();
    renderGrid(paper([segment("s1"), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    fireEvent.click(filter("To check"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [01]" }));
    fireEvent.click(within(card("[01]")).getByRole("button", { name: /^Accept/ }));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(screen.queryByRole("group", { name: /selected$/ })).toBeNull();
    fireEvent.click(filter("All"));
    expect(screen.getByRole("checkbox", { name: "Select [01]" })).not.toBeChecked();
  });

  it("the Shift-click anchor is the card, not its old position", async () => {
    putOk();
    renderGrid(paper([segment("s1"), segment("s2"), segment("s3"), segment("s4")]));
    await waitFor(() => expect(cards()).toHaveLength(4));
    fireEvent.click(filter("To check"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [03]" }));
    fireEvent.click(within(card("[01]")).getByRole("button", { name: /^Accept/ }));
    await waitFor(() => expect(cards()).toHaveLength(3));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [02]" }), { shiftKey: true });
    // [02]..[03], not the cards at the old index range
    expect(screen.getByRole("button", { name: "Reject 2" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select [04]" })).not.toBeChecked();
  });

  it("Accept is off for a card with no structure, and bulk Accept counts only cards with one", async () => {
    const bulk = vi.spyOn(api, "putBulkCuration").mockResolvedValue({ updated: 1 });
    renderGrid(
      paper([segment("s1"), segment("s2", { predictions: [prediction({ valid: false })] })]),
      [step({ segment_id: "s2", status: "done" })], // read, but nothing valid: To check
    );
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(await within(card("[02]")).findByRole("button", { name: /^Accept/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Select all shown" }));
    expect(screen.getByRole("button", { name: "Reject 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Accept 1" }));
    await waitFor(() => expect(bulk).toHaveBeenCalledTimes(1));
    expect(bulk.mock.calls[0]![1].map((i) => i.segment_id)).toEqual(["s1"]);
  });

  it("after a decision on a card, focus goes to the next card", async () => {
    putOk();
    renderGrid(paper([segment("s1"), segment("s2"), segment("s3")]));
    await waitFor(() => expect(cards()).toHaveLength(3));
    const accept = within(card("[01]")).getByRole("button", { name: /^Accept/ });
    accept.focus();
    fireEvent.click(accept);
    await waitFor(() => expect(card("[02]")).toHaveFocus());
  });

  it("the last card under To check: after its decision, focus goes to the filter strip", async () => {
    putOk();
    renderGrid(paper([segment("s1", { curation: curation({ status: "accepted" }) }), segment("s2")]));
    await waitFor(() => expect(cards()).toHaveLength(2));
    fireEvent.click(filter("To check"));
    await waitFor(() => expect(cards()).toHaveLength(1));
    const accept = within(card("[02]")).getByRole("button", { name: /^Accept/ });
    accept.focus();
    fireEvent.click(accept);
    await waitFor(() => expect(cards()).toHaveLength(0));
    await waitFor(() => expect(filter("To check")).toHaveFocus());
  });

  it("after a bulk decision, focus stays in the grid (not on the page body)", async () => {
    vi.spyOn(api, "putBulkCuration").mockResolvedValue({ updated: 2 });
    renderGrid(paper([segment("s1"), segment("s2"), segment("s3")]));
    await waitFor(() => expect(cards()).toHaveLength(3));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select [01]" }));
    const accept = screen.getByRole("button", { name: "Accept 1" });
    accept.focus();
    fireEvent.click(accept);
    await waitFor(() => expect(screen.queryByRole("group", { name: /selected$/ })).toBeNull());
    await waitFor(() => expect(document.activeElement?.tagName).toBe("ARTICLE"));
  });

  it("a rejected card that shows its crop has the crop crossed too", async () => {
    renderGrid(
      paper([segment("s1", { predictions: [], curation: curation({ status: "rejected" }) })]),
    );
    await waitFor(() => expect(cards()).toHaveLength(1));
    const crop = within(card("[01]")).getByRole("img", { name: "Crop [01]" });
    expect(crop.closest(".structure")).toHaveClass("structure--crossed");
  });

  it("the failed-pages live region is not atomic (only the new line is read)", async () => {
    renderGrid(paper([segment("s1")]));
    await waitFor(() => expect(cards()).toHaveLength(1));
    expect(screen.getByRole("status", { name: "Failed pages" })).toHaveAttribute(
      "aria-atomic",
      "false",
    );
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

  it("a run that fails after a saved chunk rejects with how many were saved", async () => {
    const qc = createQueryClient();
    qc.setQueryData(keys.paper(ID), bigPaper(600));
    vi.spyOn(api, "getPaper").mockResolvedValue(bigPaper(600));
    vi.spyOn(api, "putBulkCuration")
      .mockResolvedValueOnce({ updated: 500 })
      .mockRejectedValueOnce(new ApiError(500, "Server error."));
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useBulkCuration(ID), { wrapper });
    const items: BulkCurationItem[] = Array.from({ length: 600 }, (_, i) => ({
      segment_id: `s${i}`,
      status: "accepted",
    }));
    let caught: unknown;
    await act(() => result.current.bulk(items).catch((e: unknown) => void (caught = e)));
    expect(caught).toBeInstanceOf(BulkPartialError);
    expect((caught as BulkPartialError).saved).toBe(500);
    expect((caught as BulkPartialError).total).toBe(600);
    expect((caught as BulkPartialError).message).toBe("Saved 500 of 600: Server error.");
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

describe("Review view while only the annotation runs (beside the read)", () => {
  it("says No structures found, not that they appear as pages are read", async () => {
    renderGrid(paper([], { status: "done" }), [
      step({ kind: "docling", page: null, engine: null, status: "done" }),
      step({ kind: "annotate", page: null, engine: null, status: "running" }),
    ]);
    expect(await screen.findByText("No structures found.")).toBeInTheDocument();
    expect(screen.queryByText("Structures appear here as pages are read.")).toBeNull();
  });
});

describe("built structures (Markush Phase 3)", () => {
  it("a built card names its compound and its scaffold, and has no Compare", async () => {
    const scaffold = segment("s1", { idx: 0 });
    const built = segment("s2", {
      idx: 10001,
      built_from: "s1",
      compound_id: "3a",
      predictions: [prediction({ id: "pb", engine: "enumerated", smiles: "COc1ccccc1" })],
    });
    renderGrid(paper([scaffold, built]));
    const c = await waitFor(() => card("[02]"));
    expect(within(c).getByText("Compound 3a")).toBeInTheDocument();
    expect(within(c).getByRole("button", { name: "Built from [01]" })).toBeInTheDocument();
    expect(within(c).queryByRole("button", { name: /^Compare/ })).toBeNull();
    expect(within(c).getByRole("button", { name: /^Accept/ })).toBeInTheDocument();
  });

  it("built cards follow their scaffold in the grid's flow, each on a mint cell (owner, 2026-11-26)", async () => {
    const scaffold = segment("s1", { idx: 0 });
    const built = (id: string, idx: number) =>
      segment(id, {
        idx,
        built_from: "s1",
        predictions: [prediction({ id: `p${id}`, engine: "enumerated", smiles: "COc1ccccc1" })],
      });
    renderGrid(paper([scaffold, built("s2", 10001), built("s3", 10002), segment("s4", { idx: 1 })]));
    await screen.findByText("Compound 3a", undefined).catch(() => undefined);
    const cards = await screen.findAllByRole("article");
    expect(cards.map((a) => a.getAttribute("data-segment-id"))).toEqual(["s1", "s2", "s3", "s4"]);
    const cell = (a: HTMLElement) => a.closest(".built-cell");
    expect(cards.map((a) => cell(a) !== null)).toEqual([false, true, true, false]);
    // no full-width block: every card is one cell of the grid
    expect(document.querySelector(".built-block, .built-family--wide")).toBeNull();
    expect(cell(cards[1]!)).toHaveTextContent("Built from [01]");
  });

  it("under a filter that hides the scaffold, its built cards show without the box (owner review)", async () => {
    const scaffold = segment("s1", { idx: 0 });
    const built = segment("s2", {
      idx: 10001,
      built_from: "s1",
      curation: { status: "accepted", smiles: null, molfile: null, note: null },
      predictions: [prediction({ id: "pb", engine: "enumerated", smiles: "COc1ccccc1" })],
    });
    renderGrid(paper([scaffold, built]));
    fireEvent.click(await screen.findByRole("button", { name: /^Accepted/ }));
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(1));
    expect(screen.queryByRole("group", { name: "Built from [01]" })).toBeNull();
  });
});
