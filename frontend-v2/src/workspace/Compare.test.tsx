// Compare engines: "Run all engines" (one prediction per engine not read and not running,
// then onStarted once, no stream of its own), live states per engine, Tanimoto with two
// decimals once per pair of distinct SMILES (cached), the common part (molfile → mcs →
// depict with highlight), 429 text, "Use this one" (accept keeping the note, molfile
// replaced), and the dialog in focus mode (review keys held, Esc closes Compare first).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
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
  return tr.cells[col] as HTMLElement;
}

describe("Compare", () => {
  it("Run all engines starts the three others, then onStarted once, and opens no stream", async () => {
    const run = vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const { props } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(run.mock.calls.map((c) => c[1]).sort()).toEqual(["decimer-hand", "molnextr", "molscribe"]);
    expect(run.mock.calls.every((c) => c[0] === "s1")).toBe(true);
    expect(EventSourceSpy).not.toHaveBeenCalled();
    // Started engines read as Reading… until their steps arrive.
    expect(cell("Result", "MolNexTR")).toHaveTextContent("Reading…");
    expect(screen.getByRole("button", { name: "Run all engines" })).toBeDisabled();
  });

  it("Run all engines shows its progress: engines read of those started, with the percentage; full for a moment, then gone", async () => {
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const { props, rerender } = renderCompare({ predictions: [prediction({ engine: "decimer" })] });
    fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
    const bar = await screen.findByRole("progressbar", { name: "Run all engines" });
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("Running engines 0/3")).toBeInTheDocument();
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
    again(first, [step("molnextr", "done"), step("molscribe", "running"), step("decimer-hand", "running")]);
    expect(bar).toHaveAttribute("aria-valuenow", "33");
    expect(bar).toHaveAttribute("aria-valuetext", "Engines read, 1 of 3, 33%");
    again(
      [...first, prediction({ engine: "molscribe" })],
      [step("molnextr", "done"), step("molscribe", "done"), step("decimer-hand", "failed", "timeout")],
    );
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    await waitFor(() => expect(screen.queryByRole("progressbar", { name: "Run all engines" })).toBeNull());
  });

  it("DECIMER hand-drawn reading says its first run loads the model; the others do not", async () => {
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const first = [prediction({ engine: "decimer" })];
    const { props, rerender } = renderCompare({ predictions: first });
    fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    const note = "The first run can take about 30 s";
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent("Reading…");
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent(note);
    expect(cell("Result", "MolNexTR")).not.toHaveTextContent(note);
    // MolNexTR and MolScribe are back; the hand-drawn model is still loading.
    const steps = [step("decimer-hand", "running"), step("molnextr", "done"), step("molscribe", "done")];
    const two = [...first, prediction({ engine: "molnextr" }), prediction({ engine: "molscribe" })];
    const again = (predictions: PredictionOut[], s: typeof steps) =>
      rerender(
        <QueryClientProvider client={client}>
          <ToastProvider>
            <Compare {...props} predictions={predictions} steps={s} />
          </ToastProvider>
        </QueryClientProvider>,
      );
    again(two, steps);
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent(note);
    again([prediction({ engine: "decimer-hand" }), ...two], [step("decimer-hand", "done"), ...steps.slice(1)]);
    expect(cell("Result", "DECIMER hand-drawn")).toHaveTextContent("Valid");
    expect(cell("Result", "DECIMER hand-drawn")).not.toHaveTextContent(note);
  });

  it("does not ask again for an engine with an active step", async () => {
    const run = vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    const { props } = renderCompare({
      predictions: [prediction({ engine: "decimer" })],
      steps: [step("molnextr", "running")],
    });
    expect(cell("Result", "MolNexTR")).toHaveTextContent("Reading…");
    fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(run.mock.calls.map((c) => c[1]).sort()).toEqual(["decimer-hand", "molscribe"]);
  });

  it("an image target starts image predictions", async () => {
    const run = vi.spyOn(api, "runImagePrediction").mockResolvedValue({ step_id: "st" });
    const seg = vi.spyOn(api, "runPrediction");
    const { props } = renderCompare({
      target: { kind: "image", id: "img1" },
      predictions: [prediction({ engine: "decimer" })],
    });
    fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
    await waitFor(() => expect(props.onStarted).toHaveBeenCalledTimes(1));
    expect(run).toHaveBeenCalledTimes(3);
    expect(run.mock.calls.every((c) => c[0] === "img1")).toBe(true);
    expect(seg).not.toHaveBeenCalled();
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

  it("a segment's drawings are its stored depictions per engine (no tools call)", () => {
    const p = prediction({ engine: "molnextr", smiles: "CCO" });
    renderCompare({ predictions: [p] });
    expect(screen.getByRole("img", { name: "Structure, MolNexTR" })).toHaveAttribute(
      "src",
      api.depictionUrl("s1", p.id, "molnextr"),
    );
    expect(api.depict).not.toHaveBeenCalled();
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
      prediction({ engine: "decimer-hand", smiles: "CCO" }),
      prediction({ engine: "molnextr", smiles: "CCN" }),
      prediction({ engine: "molscribe", smiles: "CCC" }),
    ];
    const first = renderCompare({ predictions });
    await waitFor(() => expect(cmp).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByText("…")).toBeNull());
    for (const [a, b] of cmp.mock.calls) expect(a < b).toBe(true);
    // DECIMER and DECIMER hand-drawn read the same SMILES: 1.00 without a call.
    expect(screen.getByRole("row", { name: /DECIMER · DECIMER hand-drawn/ })).toHaveTextContent(
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
    await waitFor(() => expect(api.depict).toHaveBeenCalledTimes(2));
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
    expect(api.depict).toHaveBeenCalledTimes(4);
  });

  it("a highlight still refused with the new token is not asked for again (no loop)", async () => {
    vi.mocked(api.depict).mockRejectedValue(INVALID);
    const mcs = commonPartWithTokens(["tok-old", "tok-new", "tok-3", "tok-4"]);
    await waitFor(() => expect(api.depict).toHaveBeenCalledTimes(4));
    await new Promise((r) => setTimeout(r, 50));
    expect(mcs).toHaveBeenCalledTimes(2);
    expect(api.depict).toHaveBeenCalledTimes(4);
    const tokens = vi.mocked(api.depict).mock.calls.map((c) => c[1]?.highlightToken).sort();
    expect(tokens).toEqual(["tok-new", "tok-new", "tok-old", "tok-old"]);
  });

  it("another 4xx on a highlighted drawing does not ask the MCS again", async () => {
    vi.mocked(api.depict).mockRejectedValue(new ApiError(429, "slow down"));
    const mcs = commonPartWithTokens(["tok-old", "tok-new"]);
    await waitFor(() => expect(api.depict).toHaveBeenCalledTimes(2));
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

  it("a failed engine shows its reason", () => {
    renderCompare({
      predictions: [prediction({ engine: "decimer" })],
      steps: [step("molscribe", "failed", "engine_error")],
    });
    expect(cell("Result", "MolScribe")).toHaveTextContent("Failed: the engine failed");
    expect(cell("Result", "MolNexTR")).toHaveTextContent("Not read yet");
  });

  it("an engine not read yet: □ Not read yet, a muted dash for its SMILES, the word in its blank", () => {
    renderCompare({ predictions: [prediction({ engine: "decimer" })] });
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
    annotating: false,
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

  it("Run all engines from focus mode reopens the page's stream once", async () => {
    vi.spyOn(api, "runPrediction").mockResolvedValue({ step_id: "st" });
    renderWorkspace(paper([segment("s1")]), "?s=s1&focus=1");
    await screen.findByRole("region", { name: /^Focus/ });
    press("c");
    const dialog = await screen.findByRole("dialog", { name: /Compare engines/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Run all engines" }));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    expect(api.runPrediction).toHaveBeenCalledTimes(3);
    expect(EventSourceSpy).not.toHaveBeenCalled();
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
