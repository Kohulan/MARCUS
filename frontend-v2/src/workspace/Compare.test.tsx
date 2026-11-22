// Compare engines: opening starts every engine not read and not running (one prediction
// each, then onStarted once, no stream of its own), a failed engine's Retry, live states per engine, Tanimoto with two
// decimals once per pair of distinct SMILES (cached), the common part (molfile → mcs →
// depict with highlight), 429 text, "Use this one" (accept keeping the note, molfile
// replaced), and the dialog in focus mode (review keys held, Esc closes Compare first).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { orientationTemplate } from "../api/engines";
import { createQueryClient } from "../api/queries";
import type { CurationOut, PaperDetail, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import Compare, { type CompareProps } from "./Compare";
import Workspace from "./Workspace";

const live = vi.hoisted(() => ({ reconnect: (() => undefined) as () => void }));

vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: () => ({ mode: "live", reconnect: live.reconnect }),
}));

vi.mock("../api/depictions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/depictions")>()),
  useDepiction: (url: string | null) => ({ src: url, failed: false }),
}));

const ID = "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f";

// Real molfiles (backend-v2/tests/fixtures): MolScribe's and the fixed MolNexTR's hold the
// image's positions; the old MolNexTR (fb7505b) wrote a computed layout.
type Out = { molfile: string };
const fixture = (name: string) =>
  JSON.parse(readFileSync(resolve(process.cwd(), "../backend-v2/tests/fixtures", name), "utf8")) as Record<string, never>;
const REAL = fixture("orient_engines.json") as Record<string, Record<string, Out>>;
const SCRIBE = REAL.p2_6!.molscribe!.molfile;
const OLD_NEXTR = REAL.p2_6!.molnextr!.molfile;
const NEXTR = (fixture("molnextr_7a4e03f.json") as Record<string, Out>)["corallomycetellains_p3_3"]!.molfile;

/** The highlighted /tools/depict calls (the common part). */
const litCalls = () => vi.mocked(api.depict).mock.calls.filter((c) => c[1]?.highlight);
/** The template each /tools/depict call of `smiles` sent (undefined: the normal layout). */
const templatesOf = (smiles: string) =>
  vi.mocked(api.depict).mock.calls.filter((c) => c[0] === smiles).map((c) => c[1]?.template);

let pseq = 0;
function prediction(over: Partial<PredictionOut> = {}): PredictionOut {
  pseq += 1;
  return {
    id: `pr${pseq}`,
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

const step = (engine: string, status: string, error_class: string | null = null) => ({
  engine,
  status,
  error_class,
});

let client: QueryClient;
let EventSourceSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  live.reconnect = vi.fn();
  EventSourceSpy = vi.fn();
  vi.stubGlobal("EventSource", EventSourceSpy);
  Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:http://localhost/d"),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(api, "depict").mockResolvedValue({ format: "svg", data: "<svg/>" });
  vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
  vi.spyOn(api, "runImagePrediction").mockResolvedValue({ step_id: "st" });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderCompare(over: Partial<CompareProps> = {}) {
  const props: CompareProps = {
    target: { kind: "segment", id: "s1" },
    predictions: [],
    steps: [],
    onPick: vi.fn(),
    onStarted: vi.fn(),
    ...over,
  };
  const view = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Compare {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...view, props };
}

/** The table cell of an engine's column in the row named `row`. */
function cell(row: string, engine: string): HTMLElement {
  const table = screen.getByRole("table", { name: "Engines" }) as HTMLTableElement;
  const heads = [...table.tHead!.rows[0]!.cells].map((c) => c.textContent ?? "");
  const col = heads.findIndex((h) => h.startsWith(engine));
  const tr = [...table.tBodies[0]!.rows].find((r) => r.cells[0]!.textContent === row)!;
  // The source column's one cell spans the body: only the Drawing row has it.
  return tr.cells[row === "Drawing" ? col : col - 1] as HTMLElement;
}

describe("Compare", () => {
  it("three columns: DECIMER, MolNexTR, MolScribe; a hand-drawn reading is not a column", () => {
    renderCompare({
      predictions: [prediction({ engine: "decimer-hand" }), prediction({ engine: "decimer" })],
    });
    const table = screen.getByRole("table", { name: "Engines" }) as HTMLTableElement;
    const heads = [...table.tHead!.rows[0]!.cells].slice(1).map((c) => c.querySelector(".cmp-table__name")?.textContent);
    expect(heads).toEqual(["Paper", "DECIMER", "MolNexTR", "MolScribe"]);
  });

  it("shows the paper's crop the engines read beside the drawings", () => {
    renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    const crop = screen.getByRole("img", { name: "Crop from the paper" });
    expect(crop).toHaveAttribute("src", api.segmentImageUrl("s1"));
    // in the Drawing row, before the engines' drawings
    const row = crop.closest("tr")!;
    expect(row.cells[0]).toHaveTextContent("Drawing");
    expect(row.cells[1]).toContainElement(crop);
  });

  it("an image job shows the uploaded image", () => {
    renderCompare({ target: { kind: "image", id: "img1" }, predictions: [] });
    expect(screen.getByRole("img", { name: "The uploaded image" })).toHaveAttribute(
      "src",
      api.imageUrl("img1"),
    );
    expect(screen.getByRole("columnheader", { name: "Image" })).toBeInTheDocument();
  });

  it("opening starts the main engines not read (never hand-drawn), then onStarted once, and opens no stream", async () => {
    const { props } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    const run = vi.mocked(api.runPrediction);
    expect(run.mock.calls.map((c) => c[1]).sort()).toEqual(["molnextr", "molscribe"]);
    expect(run.mock.calls.every((c) => c[0] === "s1")).toBe(true);
    expect(EventSourceSpy).not.toHaveBeenCalled();
    // Started engines read as Reading… until their steps arrive.
    expect(cell("Result", "MolNexTR")).toHaveTextContent("Reading…");
    expect(screen.queryByRole("button", { name: "Run all engines" })).toBeNull();
  });

  it("starts once: a later render with new rows asks nothing more", async () => {
    const { props, rerender } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    rerender(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Compare {...props} predictions={[prediction({ engine: "decimer" })]} steps={[]} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    await new Promise((r) => setTimeout(r, 20));
    expect(api.runPrediction).toHaveBeenCalledTimes(2);
  });

  it("everything read: nothing is started", async () => {
    const { props } = renderCompare({
      predictions: ["decimer", "molnextr", "molscribe"].map((engine) =>
        prediction({ engine }),
      ),
    });
    await new Promise((r) => setTimeout(r, 20));
    expect(api.runPrediction).not.toHaveBeenCalled();
    expect(props.onStarted).not.toHaveBeenCalled();
  });

  it("the opening start shows its progress: engines read of those started; full for a moment, then gone", async () => {
    const { props, rerender } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    const bar = await screen.findByRole("progressbar", { name: "Engines" });
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("Running engines 0/2")).toBeInTheDocument();
    // an engine reading has the calm indeterminate bar under its word
    expect(within(cell("Result", "MolNexTR")).getByRole("progressbar", { name: "Reading, MolNexTR" })).not.toHaveAttribute(
      "aria-valuenow",
    );
    await waitFor(() => expect(props.onStarted).toHaveBeenCalled());
    const again = (predictions: PredictionOut[], steps: ReturnType<typeof step>[]) =>
      rerender(
        <QueryClientProvider client={client}>
          <ToastProvider>
            <Compare {...props} predictions={predictions} steps={steps} />
          </ToastProvider>
        </QueryClientProvider>,
      );
    const first = [prediction({ engine: "decimer" }), prediction({ engine: "molnextr" })];
    again(first, [step("molnextr", "done"), step("molscribe", "running")]);
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveAttribute("aria-valuetext", "Engines read, 1 of 2, 50%");
    again(first, [step("molnextr", "done"), step("molscribe", "failed", "timeout")]);
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    await waitFor(() => expect(screen.queryByRole("progressbar", { name: "Engines" })).toBeNull());
  });

  it("Hand-drawn (off by default) reads DECIMER hand-drawn in the DECIMER column; its first run says it loads the model", async () => {
    const first = [prediction({ engine: "decimer" }), prediction({ engine: "molnextr" }), prediction({ engine: "molscribe" })];
    const { props, rerender } = renderCompare({ predictions: first });
    const toggle = screen.getByRole("button", { name: "Hand-drawn" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(api.runPrediction).not.toHaveBeenCalled();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(api.runPrediction).toHaveBeenCalledWith("s1", "decimer-hand");
    const note = "The first run can take about 30 s";
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent("Reading…");
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent(note);
    expect(cell("Result", "MolNexTR")).not.toHaveTextContent(note);
    const again = (predictions: PredictionOut[], s: ReturnType<typeof step>[]) =>
      rerender(
        <QueryClientProvider client={client}>
          <ToastProvider>
            <Compare {...props} predictions={predictions} steps={s} />
          </ToastProvider>
        </QueryClientProvider>,
      );
    again(first, [step("decimer-hand", "running")]);
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent(note);
    const hand = prediction({ engine: "decimer-hand", smiles: "CCCl" });
    again([hand, ...first], [step("decimer-hand", "done")]);
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent("Valid");
    expect(cell("Result", "DECIMER hand-drawn")).not.toHaveTextContent(note);
    expect(cell("SMILES", "DECIMER hand-drawn")).toHaveTextContent("CCCl");
    // Use this one takes what the column shows
    fireEvent.click(screen.getByRole("button", { name: "Use this one, DECIMER hand-drawn" }));
    expect(props.onPick).toHaveBeenCalledWith(hand);
    // Off: normal DECIMER again, nothing started
    fireEvent.click(screen.getByRole("button", { name: "Hand-drawn" }));
    expect(cell("SMILES", "DECIMER")).toHaveTextContent("c1ccccc1");
    expect(screen.queryByRole("button", { name: "Use this one, DECIMER hand-drawn" })).toBeNull();
    expect(api.runPrediction).toHaveBeenCalledTimes(1);
  });

  it("Hand-drawn starts on where the upload chose DECIMER hand-drawn (and starts it if not read)", async () => {
    const { props } = renderCompare({
      handDrawn: true,
      predictions: [prediction({ engine: "molnextr" }), prediction({ engine: "molscribe" })],
    });
    expect(screen.getByRole("button", { name: "Hand-drawn" })).toHaveAttribute("aria-pressed", "true");
    expect(cell("Result", "DECIMER hand-drawn")).toBeDefined();
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.runPrediction).mock.calls.map((c) => c[1])).toEqual(["decimer-hand"]);
    // off: normal DECIMER, started then (it is not read)
    fireEvent.click(screen.getByRole("button", { name: "Hand-drawn" }));
    expect(screen.getByRole("button", { name: "Hand-drawn" })).toHaveAttribute("aria-pressed", "false");
    expect(cell("Result", "DECIMER")).toHaveTextContent("Not read yet");
  });

  it("Hand-drawn on an already read hand-drawn model starts nothing; the similarity uses what the columns show", async () => {
    const cmp = vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    renderCompare({
      predictions: [
        prediction({ engine: "decimer-hand", smiles: "CCN" }),
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
        prediction({ engine: "molscribe", smiles: "CCO" }),
      ],
    });
    const label = await screen.findByRole("table", { name: "Similarity" });
    expect(within(label).getByRole("row", { name: /DECIMER · MolScribe/ })).toHaveTextContent("1.00");
    fireEvent.click(screen.getByRole("button", { name: "Hand-drawn" }));
    await waitFor(() =>
      expect(within(label).getByRole("row", { name: /DECIMER hand-drawn · MolNexTR/ })).toHaveTextContent("1.00"),
    );
    expect(within(label).queryByRole("row", { name: /^DECIMER · / })).toBeNull();
    expect(api.runPrediction).not.toHaveBeenCalled();
    expect(cmp).toHaveBeenCalledWith("CCN", "CCO");
  });

  it("does not ask again for an engine with an active step", async () => {
    const { props } = renderCompare({
      predictions: [prediction({ engine: "decimer" })],
      steps: [step("molnextr", "running")],
    });
    expect(cell("Result", "MolNexTR")).toHaveTextContent("Reading…");
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.runPrediction).mock.calls.map((c) => c[1]).sort()).toEqual(["molscribe"]);
  });

  it("an image target starts image predictions", async () => {
    const seg = vi.mocked(api.runPrediction);
    const { props } = renderCompare({
      target: { kind: "image", id: "img1" },
      predictions: [prediction({ engine: "decimer" })],
    });
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    const run = vi.mocked(api.runImagePrediction);
    expect(run).toHaveBeenCalledTimes(2);
    expect(run.mock.calls.every((c) => c[0] === "img1")).toBe(true);
    expect(seg).not.toHaveBeenCalled();
  });

  it("a failed engine is not started again on opening: its own Retry starts it", async () => {
    const { props } = renderCompare({
      predictions: ["decimer", "molnextr"].map((engine) => prediction({ engine })),
      steps: [step("molscribe", "failed", "engine_error")],
    });
    expect(cell("Result", "MolScribe")).toHaveTextContent("Failed: the engine failed");
    await new Promise((r) => setTimeout(r, 20));
    expect(api.runPrediction).not.toHaveBeenCalled();
    fireEvent.click(within(cell("Result", "MolScribe")).getByRole("button", { name: "Retry, MolScribe" }));
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(api.runPrediction).toHaveBeenCalledWith("s1", "molscribe");
    expect(cell("Result", "MolScribe")).toHaveTextContent("Reading…");
    expect(within(cell("Result", "MolNexTR")).queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("a refused start says so and leaves the engines not read", async () => {
    vi.mocked(api.runPrediction).mockRejectedValue(new ApiError(503, "engine not available"));
    const { props } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    expect(await screen.findByText("Not started: engine not available")).toBeInTheDocument();
    expect(props.onStarted).not.toHaveBeenCalled();
    expect(cell("Result", "MolNexTR").textContent).toBe("□ Not read yet");
  });

  it("an image job's drawings come from /tools/depict keyed with a null highlight", async () => {
    renderCompare({
      target: { kind: "image", id: "img1" },
      predictions: [prediction({ engine: "decimer", smiles: "CCO" })],
    });
    expect(await screen.findByRole("img", { name: "Structure, DECIMER" })).toHaveAttribute(
      "src",
      "blob:http://localhost/d",
    );
    expect(api.depict).toHaveBeenCalledWith("CCO");
    expect(client.getQueryData(["depict", "CCO", null])).toEqual({ format: "svg", data: "<svg/>" });
  });

  it("every drawing comes from /tools/depict, a segment's too", async () => {
    renderCompare({ predictions: [prediction({ engine: "molnextr", smiles: "CCO" })] });
    expect(await screen.findByRole("img", { name: "Structure, MolNexTR" })).toHaveAttribute(
      "src",
      "blob:http://localhost/d",
    );
    expect(api.depict).toHaveBeenCalledWith("CCO");
  });

  it("Use coordinates (on): MolScribe and MolNexTR draw on their own positions; DECIMER on MolScribe's", async () => {
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN", molfile: NEXTR }),
        prediction({ engine: "molscribe", smiles: "CCC", molfile: SCRIBE }),
      ],
    });
    for (const engine of ["MolNexTR", "MolScribe"]) {
      expect(screen.getByRole("button", { name: `Use coordinates, ${engine}` })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }
    await waitFor(() => expect(templatesOf("CCO")).toEqual([SCRIBE]));
    expect(templatesOf("CCN")).toEqual([NEXTR]);
    expect(templatesOf("CCC")).toEqual([SCRIBE]);
  });

  it("Use coordinates off: that engine draws in the normal layout and is no template; both off: all normal", async () => {
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN", molfile: NEXTR }),
        prediction({ engine: "molscribe", smiles: "CCC", molfile: SCRIBE }),
      ],
    });
    await waitFor(() => expect(templatesOf("CCO")).toEqual([SCRIBE]));
    fireEvent.click(screen.getByRole("button", { name: "Use coordinates, MolScribe" }));
    expect(screen.getByRole("button", { name: "Use coordinates, MolScribe" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // MolScribe plain; DECIMER now on MolNexTR's positions
    await waitFor(() => expect(templatesOf("CCC")).toEqual([SCRIBE, undefined]));
    await waitFor(() => expect(templatesOf("CCO")).toEqual([SCRIBE, NEXTR]));
    fireEvent.click(screen.getByRole("button", { name: "Use coordinates, MolNexTR" }));
    await waitFor(() => expect(templatesOf("CCN")).toEqual([NEXTR, undefined]));
    await waitFor(() => expect(templatesOf("CCO")).toEqual([SCRIBE, NEXTR, undefined]));
  });

  it("Use coordinates shows only with a molfile, and is disabled for one without the image's positions", async () => {
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN", molfile: OLD_NEXTR, engine_version: "fb7505b" }),
        prediction({ engine: "molscribe", smiles: "CCC", molfile: null }),
      ],
    });
    const old = screen.getByRole("button", { name: "Use coordinates, MolNexTR" });
    expect(old).toBeDisabled();
    expect(old).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("button", { name: "Use coordinates, MolScribe" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Use coordinates, DECIMER/ })).toBeNull();
    // nothing to orient by: every drawing in the normal layout
    await waitFor(() => expect(templatesOf("CCN")).toEqual([undefined]));
    expect(templatesOf("CCO")).toEqual([undefined]);
  });

  it("the paper's orientation: an image job's drawings send MolScribe's molfile (MolNexTR's without one)", async () => {
    const decimer = prediction({ engine: "decimer", smiles: "CCO" });
    const scribe = prediction({ engine: "molscribe", smiles: "CCN", molfile: SCRIBE });
    const nextr = prediction({ engine: "molnextr", smiles: "CCC", molfile: NEXTR });
    const view = renderCompare({ target: { kind: "image", id: "img1" }, predictions: [decimer, nextr] });
    await waitFor(() => expect(api.depict).toHaveBeenCalledWith("CCO", { template: NEXTR }));
    expect(client.getQueryData(["depict", "CCO", null, nextr.id])).toBeDefined();
    view.unmount();
    renderCompare({ target: { kind: "image", id: "img1" }, predictions: [nextr, decimer, scribe] });
    await waitFor(() => expect(api.depict).toHaveBeenCalledWith("CCO", { template: SCRIBE }));
  });

  it("the paper's orientation goes with the common part too", async () => {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    vi.spyOn(api, "mcs").mockResolvedValue({
      mcs_smarts: "[#6]-[#6]",
      atom_count: 2,
      bond_count: 1,
      original_molecules: [],
      highlight_token: "tok-1",
    });
    vi.spyOn(api, "smilesToMolfile").mockImplementation((s) => Promise.resolve(`M:${s}`));
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN", molfile: NEXTR }),
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Show common part" }));
    const on = { highlight: "[#6]-[#6]", highlightToken: "tok-1", template: NEXTR };
    await waitFor(() => expect(api.depict).toHaveBeenCalledWith("CCO", on));
    expect(api.depict).toHaveBeenCalledWith("CCN", on);
  });

  it("orientationTemplate: the newest valid MolScribe prediction with the image's positions, else MolNexTR's", () => {
    const old = prediction({ engine: "molscribe", molfile: SCRIBE });
    const invalid = prediction({ engine: "molscribe", molfile: SCRIBE, valid: false });
    const bare = prediction({ engine: "molscribe", molfile: null });
    const nextr = prediction({ engine: "molnextr", molfile: NEXTR });
    const hand = prediction({ engine: "decimer-hand", molfile: SCRIBE });
    expect(orientationTemplate([invalid, bare, nextr, old])).toBe(old);
    expect(orientationTemplate([invalid, bare, hand, nextr])).toBe(nextr);
    // a computed layout (old MolNexTR) is none; an engine left out is skipped
    expect(orientationTemplate([prediction({ engine: "molnextr", molfile: OLD_NEXTR })])).toBeNull();
    expect(orientationTemplate([old, nextr], { molscribe: false })).toBe(nextr);
    expect(orientationTemplate([hand, prediction()])).toBeNull();
  });

  it("shows Tanimoto with two decimals", async () => {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.8734,
      identical: false,
      same_structure: false,
      agree: false,
    });
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
      ],
    });
    const label = await screen.findByRole("table", { name: "Similarity" });
    await waitFor(() =>
      expect(within(label).getByRole("row", { name: /DECIMER · MolNexTR/ })).toHaveTextContent(
        "0.87",
      ),
    );
    expect(label).not.toHaveTextContent("0.8734");
  });

  it("three distinct SMILES make exactly 3 compare calls, and reopening makes none", async () => {
    const cmp = vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    const predictions = [
      prediction({ engine: "decimer", smiles: "CCO" }),
      prediction({ engine: "molnextr", smiles: "CCN" }),
      prediction({ engine: "molscribe", smiles: "CCC" }),
      prediction({ engine: "fake", smiles: "CCO" }),
    ];
    const first = renderCompare({ predictions });
    await waitFor(() => expect(cmp).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByText("…")).toBeNull());
    for (const [a, b] of cmp.mock.calls) expect(a < b).toBe(true);
    // DECIMER and another engine read the same SMILES: 1.00 without a call.
    expect(screen.getByRole("row", { name: /DECIMER · fake/ })).toHaveTextContent(
      "1.00",
    );
    first.unmount();
    renderCompare({ predictions });
    await screen.findByRole("table", { name: "Similarity" });
    expect(cmp).toHaveBeenCalledTimes(3);
  });

  it("Show common part draws each structure with the MCS highlighted", async () => {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    const molfile = vi.spyOn(api, "smilesToMolfile").mockImplementation((s) => Promise.resolve(`M:${s}`));
    const mcs = vi.spyOn(api, "mcs").mockResolvedValue({
      mcs_smarts: "[#6]-[#6]",
      atom_count: 2,
      bond_count: 1,
      original_molecules: [],
      highlight_token: "tok-1",
    });
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
      ],
    });
    const toggle = screen.getByRole("button", { name: "Show common part" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(litCalls()).toHaveLength(2));
    expect(molfile.mock.calls.map((c) => c[0]).sort()).toEqual(["CCN", "CCO"]);
    expect(mcs).toHaveBeenCalledWith(["M:CCN", "M:CCO"]);
    // the server's token from the MCS reply goes with every highlighted drawing (F5)
    const lit = { highlight: "[#6]-[#6]", highlightToken: "tok-1" };
    expect(api.depict).toHaveBeenCalledWith("CCO", lit);
    expect(api.depict).toHaveBeenCalledWith("CCN", lit);
    expect(await screen.findByRole("img", { name: "Structure, MolNexTR" })).toHaveAttribute(
      "src",
      "blob:http://localhost/d",
    );
  });

  /** Two predictions, Show common part pressed; the MCS replies carry the tokens in turn. */
  function commonPartWithTokens(tokens: string[]) {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    vi.spyOn(api, "smilesToMolfile").mockImplementation((s) => Promise.resolve(`M:${s}`));
    let n = 0;
    const mcs = vi.spyOn(api, "mcs").mockImplementation(() =>
      Promise.resolve({
        mcs_smarts: "[#6]-[#6]",
        atom_count: 2,
        bond_count: 1,
        original_molecules: [],
        highlight_token: tokens[Math.min(n++, tokens.length - 1)]!,
      }),
    );
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Show common part" }));
    return mcs;
  }

  const INVALID = new ApiError(422, "highlight not valid for this structure");

  it("an expired highlight token asks the MCS once more and draws again with the new one", async () => {
    vi.mocked(api.depict).mockImplementation((_smiles, opts) =>
      opts?.highlightToken === "tok-old"
        ? Promise.reject(INVALID)
        : Promise.resolve({ format: "svg", data: "<svg/>" }),
    );
    const mcs = commonPartWithTokens(["tok-old", "tok-new"]);
    for (const name of ["Structure, DECIMER", "Structure, MolNexTR"]) {
      await waitFor(() =>
        expect(screen.getByRole("img", { name })).toHaveAttribute("src", "blob:http://localhost/d"),
      );
    }
    // both drawings failed on the old token, yet the MCS is asked again only once
    expect(mcs).toHaveBeenCalledTimes(2);
    const lit = { highlight: "[#6]-[#6]", highlightToken: "tok-new" };
    expect(api.depict).toHaveBeenCalledWith("CCO", lit);
    expect(api.depict).toHaveBeenCalledWith("CCN", lit);
    expect(litCalls()).toHaveLength(4);
  });

  it("a highlight still refused with the new token is not asked for again (no loop)", async () => {
    vi.mocked(api.depict).mockRejectedValue(INVALID);
    const mcs = commonPartWithTokens(["tok-old", "tok-new", "tok-3", "tok-4"]);
    await waitFor(() => expect(litCalls()).toHaveLength(4));
    await new Promise((r) => setTimeout(r, 50));
    expect(mcs).toHaveBeenCalledTimes(2);
    expect(litCalls()).toHaveLength(4);
    const tokens = litCalls().map((c) => c[1]?.highlightToken).sort();
    expect(tokens).toEqual(["tok-new", "tok-new", "tok-old", "tok-old"]);
  });

  it("another 4xx on a highlighted drawing does not ask the MCS again", async () => {
    vi.mocked(api.depict).mockRejectedValue(new ApiError(429, "slow down"));
    const mcs = commonPartWithTokens(["tok-old", "tok-new"]);
    await waitFor(() => expect(litCalls()).toHaveLength(2));
    await new Promise((r) => setTimeout(r, 50));
    expect(mcs).toHaveBeenCalledTimes(1);
  });

  it("Show common part is not pressed while it is disabled (fewer than 2 valid)", async () => {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    vi.spyOn(api, "smilesToMolfile").mockImplementation((s) => Promise.resolve(`M:${s}`));
    vi.spyOn(api, "mcs").mockResolvedValue({
      mcs_smarts: "[#6]-[#6]",
      atom_count: 2,
      bond_count: 1,
      original_molecules: [],
      highlight_token: "tok-1",
    });
    const two = [
      prediction({ engine: "decimer", smiles: "CCO" }),
      prediction({ engine: "molnextr", smiles: "CCN" }),
    ];
    const { rerender, props } = renderCompare({ predictions: two });
    const toggle = screen.getByRole("button", { name: "Show common part" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    rerender(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Compare {...props} predictions={[two[0]!]} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    const now = screen.getByRole("button", { name: "Show common part" });
    expect(now).toBeDisabled();
    expect(now).toHaveAttribute("aria-pressed", "false");
  });

  it("a common part that fails (not a 429) says so", async () => {
    vi.spyOn(api, "compare").mockResolvedValue({
      tanimoto: 0.5,
      identical: false,
      same_structure: false,
      agree: false,
    });
    vi.spyOn(api, "smilesToMolfile").mockImplementation((s) => Promise.resolve(`M:${s}`));
    vi.spyOn(api, "mcs").mockRejectedValue(new ApiError(500, "boom"));
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
      ],
    });
    expect(screen.queryByText("Common part unavailable")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show common part" }));
    expect(await screen.findByText("Common part unavailable", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText(/boom/)).toBeNull();
  });

  it("an engine not read yet: □ Not read yet, a muted dash for its SMILES, the word in its blank", async () => {
    vi.mocked(api.runPrediction).mockRejectedValue(new ApiError(503, "busy"));
    renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    await screen.findByText("Not started: busy");
    expect(cell("Result", "MolNexTR").textContent).toBe("□ Not read yet");
    const smiles = cell("SMILES", "MolNexTR");
    expect(smiles.textContent).toBe("–None");
    expect(smiles.querySelector(".cmp-table__none [aria-hidden='true']")?.textContent).toBe("–");
    expect(cell("Drawing", "MolNexTR").textContent).toBe("□ Not read yet");
  });

  it("a 429 from the tools bucket says when to try again", async () => {
    vi.spyOn(api, "compare").mockRejectedValue(new ApiError(429, "rate limited", 12));
    renderCompare({
      predictions: [
        prediction({ engine: "decimer", smiles: "CCO" }),
        prediction({ engine: "molnextr", smiles: "CCN" }),
      ],
    });
    await waitFor(() =>
      expect(screen.getByText("Too many requests, try again in 12 s")).toBeInTheDocument(),
    );
  });

  it("as a dialog: native <dialog>, a glass Close, and focus home when the opener is gone", () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <section data-focus-home="" tabIndex={-1} aria-label="Focus [01]">
          {!open && (
            <button type="button" onClick={() => setOpen(true)}>
              Open compare
            </button>
          )}
          {open && (
            <Compare
              target={{ kind: "segment", id: "s1" }}
              predictions={[]}
              steps={[]}
              onPick={vi.fn()}
              onStarted={vi.fn()}
              onClose={() => setOpen(false)}
            />
          )}
        </section>
      );
    }
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <Host />
        </ToastProvider>
      </QueryClientProvider>,
    );
    const opener = screen.getByRole("button", { name: "Open compare" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: /Compare engines/ });
    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAttribute("open");
    const close = within(dialog).getByRole("button", { name: "Close" });
    expect(close).toHaveClass("glass", "glass--clear", "glass--sm");
    expect(close).toHaveFocus();
    fireEvent.click(close);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("region", { name: "Focus [01]" })).toHaveFocus();
  });

  it("Use this one hands the prediction to onPick", () => {
    const p = prediction({ engine: "molnextr", smiles: "CCN" });
    const { props } = renderCompare({ predictions: [prediction(), p] });
    fireEvent.click(screen.getByRole("button", { name: "Use this one, MolNexTR" }));
    expect(props.onPick).toHaveBeenCalledWith(p);
  });
});

// ---- In the paper workspace ------------------------------------------------------------

function segment(id: string, over: Partial<SegmentOut> = {}): SegmentOut {
  return {
    id,
    page: 0,
    idx: Number(id.replace(/\D/g, "")) || 0,
    bbox: [100, 200, 400, 500],
    curation: null,
    predictions: [prediction()],
    ...over,
  };
}

function paper(segments: SegmentOut[]): PaperDetail {
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
  };
}

function renderWorkspace(p: PaperDetail, search = "", steps: StepOut[] = []) {
  vi.spyOn(api, "getPaper").mockResolvedValue(p);
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps });
  vi.spyOn(api, "getQueue").mockResolvedValue({ papers: [], estimate_s: 0 });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/app/papers/${ID}${search}`]}>
          <Routes>
            <Route path="/app/papers/:id" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const press = (key: string) =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key });

describe("Compare in the workspace", () => {
  it("Use this one accepts MolNexTR's structure, keeps the note and replaces the molfile", async () => {
    const molnextr = prediction({ engine: "molnextr", smiles: "CCN", molfile: "<molnextr>" });
    const cur: CurationOut = { status: "unchecked", note: "keep me", smiles: "CCO", molfile: "<m>" };
    const put = vi
      .spyOn(api, "putCuration")
      .mockImplementation((_id, body) => Promise.resolve({ ...body }));
    renderWorkspace(
      paper([segment("s1", { curation: cur, predictions: [prediction(), molnextr] })]),
      "?s=s1&focus=1",
    );
    await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this one, MolNexTR" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]).toEqual([
      "s1",
      { status: "accepted", smiles: "CCN", molfile: "<molnextr>", note: "keep me" },
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a prediction without a molfile clears the old curated molfile", async () => {
    const molscribe = prediction({ engine: "molscribe", smiles: "CCC", molfile: null });
    const cur: CurationOut = { status: "unchecked", note: null, smiles: "CCO", molfile: "<m>" };
    const put = vi
      .spyOn(api, "putCuration")
      .mockImplementation((_id, body) => Promise.resolve({ ...body }));
    renderWorkspace(
      paper([segment("s1", { curation: cur, predictions: [molscribe] })]),
      "?s=s1&focus=1",
    );
    await screen.findByRole("region", { name: /^Focus/ });
    fireEvent.click(screen.getByRole("button", { name: /^Compare/ }));
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this one, MolScribe" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]![1]).toEqual({
      status: "accepted",
      smiles: "CCC",
      molfile: null,
      note: null,
    });
  });

  it("while Compare is open the review keys do nothing; Esc closes Compare first", async () => {
    const put = vi
      .spyOn(api, "putCuration")
      .mockImplementation((_id, body) => Promise.resolve({ ...body }));
    renderWorkspace(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    for (const key of ["a", "r", "ArrowRight", "e", "c", "?"]) press(key);
    // Focus outside the dialog (a click on the page underneath) holds the keys as well.
    (document.activeElement as HTMLElement).blur();
    for (const key of ["a", "r", "ArrowRight"]) press(key);
    expect(put).not.toHaveBeenCalled();
    expect(region).toHaveAccessibleName(/\[01\]/);
    expect(screen.queryByRole("dialog", { name: "Keys" })).toBeNull();

    // A click on plain text in the box (the table) keeps focus in it: Esc still closes.
    expect(dialog).toHaveAttribute("tabindex", "-1");
    dialog.focus();
    expect(dialog).toHaveFocus();
    press("Escape");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("region", { name: /^Focus/ })).toBeInTheDocument();
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("region", { name: /^Focus/ })).toBeNull());
  });

  it("Compare from focus mode starts the engines and reopens the page's stream once", async () => {
    renderWorkspace(paper([segment("s1")]), "?s=s1&focus=1");
    await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    await screen.findByRole("dialog", { name: /Compare engines/ });
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    expect(api.runPrediction).toHaveBeenCalledTimes(2);
    expect(EventSourceSpy).not.toHaveBeenCalled();
  });

  it("a paper uploaded with DECIMER hand-drawn opens Compare with Hand-drawn on; another engine with it off", async () => {
    const hand = { ...paper([segment("s1", { predictions: [prediction({ engine: "decimer-hand" })] })]), engine: "decimer-hand" };
    const first = renderWorkspace(hand, "?s=s1&focus=1");
    await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    let dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    expect(within(dialog).getByRole("button", { name: "Hand-drawn" })).toHaveAttribute("aria-pressed", "true");
    first.unmount();
    renderWorkspace(paper([segment("s1")]), "?s=s1&focus=1");
    await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    expect(within(dialog).getByRole("button", { name: "Hand-drawn" })).toHaveAttribute("aria-pressed", "false");
  });

  it("a card's engine menu and a To check card open Compare in the grid", async () => {
    const steps: StepOut[] = [
      {
        id: "st1",
        kind: "ocsr",
        page: 0,
        segment_id: "s2",
        status: "failed",
        attempts: 1,
        error_class: "timeout",
        engine: "decimer",
        created_at: "2026-11-18T10:00:00Z",
        started_at: null,
        finished_at: null,
      },
    ];
    renderWorkspace(paper([segment("s1"), segment("s2", { predictions: [] })]), "", steps);
    fireEvent.click(await screen.findByRole("button", { name: "Compare [01]" }));
    let dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    expect(dialog).toHaveTextContent("[01]");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Try another engine" }));
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    expect(within(dialog).getByText("Failed: it took too long")).toBeInTheDocument();
  });
});
