// A scaffold's R-group rows: hidden where the feature is off, the action and its progress, the
// table (columns from the labels, model text as text), failures in words, the list polled only
// while a reading is in flight, and the words the helpers pin.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { reasonText } from "../api/reasons";
import { createQueryClient } from "../api/queries";
import type { PredictionOut, RgroupExtractionOut, RgroupList, SegmentOut } from "../api/types";
import { hasScaffold, scaffoldPrediction, shownStructure } from "./cardState";
import RgroupRows from "./RgroupRows";
import {
  anyRgroupActive,
  compoundCount,
  extractionFor,
  isRgroupActive,
  RGROUP_NOTE,
  rgroupFailure,
  rgroupProgress,
} from "./rgroups";
import { RGROUP_POLL_MS, RgroupPaper, useRgroupList } from "./useRgroupRows";

const PAPER = "11111111-1111-4111-8111-111111111111";
const PRED = "22222222-2222-4222-8222-222222222222";

function extraction(over: Partial<RgroupExtractionOut> = {}): RgroupExtractionOut {
  return {
    prediction_id: PRED,
    segment_id: "s",
    status: "done",
    labels: ["R1", "R2"],
    rows: [
      { compound: "3a", groups: { R1: "OMe", R2: "H" } },
      { compound: "3b", groups: { R1: "H", R2: "OMe" } },
    ],
    truncated: false,
    error: null,
    model: "nuextract3-rgroup-v1",
    model_version: "vision Q8_0 llama.cpp b12554",
    created_at: null,
    updated_at: null,
    finished_at: null,
    ...over,
  };
}

const list = (available: boolean, ...extractions: RgroupExtractionOut[]): RgroupList => ({
  available,
  extractions,
});

let client: QueryClient;

function wrap(children: ReactNode) {
  return (
    <QueryClientProvider client={client}>
      <RgroupPaper.Provider value={PAPER}>{children}</RgroupPaper.Provider>
    </QueryClientProvider>
  );
}

function show(compact = false) {
  return render(wrap(<RgroupRows predictionId={PRED} labels={["R1", "R2"]} tag="[03]" compact={compact} />));
}

beforeEach(() => {
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("RgroupRows", () => {
  it("shows nothing where the deployment cannot read R-groups", async () => {
    const get = vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(false));
    const { container } = show();
    await waitFor(() => expect(get).toHaveBeenCalledWith(PAPER, expect.anything()));
    expect(container).toBeEmptyDOMElement();
  });

  it("still shows rows read before the feature was turned off, without actions", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(false, extraction()));
    show();
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("starts a reading, then shows it queued", async () => {
    const get = vi
      .spyOn(api, "getPaperRgroups")
      .mockResolvedValueOnce(list(true))
      .mockResolvedValue(list(true, extraction({ status: "queued", rows: null })));
    const start = vi.spyOn(api, "startRgroups").mockResolvedValue({ step_id: "st" });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Extract R-groups" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith(PRED, false));
    expect(await screen.findByText("Queued", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(get).toHaveBeenCalledTimes(2); // read again after the start
    expect(screen.getByRole("status")).toHaveTextContent("Queued");
  });

  it("a reading about to start by itself shows Queued where the button was, then the rows without a click", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue({ ...list(true), auto_pending: [PRED] });
    const start = vi.spyOn(api, "startRgroups");
    show();
    expect(await screen.findByText("Queued", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    vi.mocked(api.getPaperRgroups).mockResolvedValue(list(true, extraction()));
    await client.invalidateQueries({ queryKey: ["rgroups", PAPER] });
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run again" })).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it("another scaffold about to be read leaves this one's button", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue({ ...list(true), auto_pending: ["other"] });
    show();
    expect(await screen.findByRole("button", { name: "Extract R-groups" })).toBeInTheDocument();
  });

  it("says why a start was refused", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true));
    vi.spyOn(api, "startRgroups").mockRejectedValue(
      new ApiError(503, "The R-group model is not running"),
    );
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Extract R-groups" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not started: The R-group model is not running",
    );
    expect(screen.getByRole("button", { name: "Extract R-groups" })).toBeEnabled();
  });

  it("shows a running reading in words", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(
      list(true, extraction({ status: "running", rows: null })),
    );
    show();
    expect(await screen.findByText("Reading R-groups…", { selector: ".badge" })).toBeInTheDocument();
  });

  it("shows the rows as a table: one row per compound, one column per label", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true, extraction()));
    show();
    const table = await screen.findByRole("table");
    expect(within(table).getByText(RGROUP_NOTE).tagName).toBe("CAPTION");
    const heads = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Compound", "R1", "R2"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => [...r.children].map((c) => c.textContent))).toEqual([
      ["3a", "OMe", "H"],
      ["3b", "H", "OMe"],
    ]);
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["3a", "3b"]);
    expect(screen.getByRole("region", { name: "R-group table of [03]" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("button", { name: "Run again" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("R-groups read: 2 compounds");
  });

  it("asks for a re-run once it has rows", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true, extraction()));
    const start = vi.spyOn(api, "startRgroups").mockResolvedValue({ step_id: "st" });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Run again" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith(PRED, true));
  });

  it("keeps model text as text, and an own-key lookup only", async () => {
    const hostile = "<img src=x onerror=alert(1)>";
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(
      list(
        true,
        extraction({
          labels: ["__proto__", "R1"],
          rows: [{ compound: hostile, groups: { R1: "<b>Cl</b>" } }],
        }),
      ),
    );
    const { container } = show();
    const table = await screen.findByRole("table");
    expect(within(table).getByText(hostile)).toBeInTheDocument();
    expect(within(table).getByText("<b>Cl</b>")).toBeInTheDocument();
    expect(container.querySelector("img, b")).toBeNull();
    const cells = within(table).getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toEqual(["", "<b>Cl</b>"]); // __proto__ is not an own key: empty
  });

  it("says when no definitions were found, and when the answer was cut short", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true, extraction({ rows: [] })));
    show();
    expect(await screen.findByText("No R-group definitions found on the page.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    client.setQueryData(["rgroups", PAPER], list(true, extraction({ truncated: true })));
    expect(await screen.findByText("Cut short: later rows are missing.")).toBeInTheDocument();
  });

  it("says why a reading failed and offers to try again", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(
      list(true, extraction({ status: "failed", rows: null, error: "bad_input" })),
    );
    show();
    expect(
      await screen.findByText("R-groups not read: the page image could not be read.", {
        selector: ".rg__problem",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("offers no reading for a structure whose only label is *, but shows rows read before", async () => {
    const get = vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true));
    const only = render(wrap(<RgroupRows predictionId={PRED} labels={["*"]} tag="[03]" />));
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(only.container).toBeEmptyDOMElement();
    only.unmount();
    get.mockResolvedValue(list(true, extraction({ labels: ["*"], rows: [{ compound: "3a", groups: { "*": "H" } }] })));
    client = createQueryClient();
    render(wrap(<RgroupRows predictionId={PRED} labels={["*"]} tag="[03]" />));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps earlier rows over a failed re-run", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(
      list(true, extraction({ status: "failed", error: "timeout" })),
    );
    show();
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(
      screen.getByText("R-groups not read: it took too long.", { selector: ".rg__problem" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run again" })).toBeInTheDocument();
  });

  it("scrolls inside the card", async () => {
    vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true, extraction()));
    const { container } = show(true);
    await screen.findByRole("table");
    expect(container.querySelector(".rg")).toHaveClass("rg--compact");
  });
});

describe("useRgroupList", () => {
  it("reads the list again only while a reading is in flight", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const get = vi
      .spyOn(api, "getPaperRgroups")
      .mockResolvedValueOnce(list(true, extraction({ status: "queued", rows: null })))
      .mockResolvedValueOnce(list(true, extraction({ status: "running", rows: null })))
      .mockResolvedValue(list(true, extraction()));
    const { result } = renderHook(() => useRgroupList(PAPER, true), {
      wrapper: ({ children }) => wrap(children),
    });
    await waitFor(() => expect(result.current.data?.extractions[0]?.status).toBe("queued"));
    await act(() => vi.advanceTimersByTimeAsync(RGROUP_POLL_MS));
    await waitFor(() => expect(result.current.data?.extractions[0]?.status).toBe("running"));
    await act(() => vi.advanceTimersByTimeAsync(RGROUP_POLL_MS));
    await waitFor(() => expect(result.current.data?.extractions[0]?.status).toBe("done"));
    const calls = get.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(RGROUP_POLL_MS * 3));
    expect(get.mock.calls.length).toBe(calls); // done: no more reads
  });

  it("reads the list again while a reading is about to start by itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const get = vi
      .spyOn(api, "getPaperRgroups")
      .mockResolvedValueOnce({ ...list(true), auto_pending: [PRED] })
      .mockResolvedValue(list(true, extraction()));
    const { result } = renderHook(() => useRgroupList(PAPER, true), {
      wrapper: ({ children }) => wrap(children),
    });
    await waitFor(() => expect(result.current.data?.auto_pending).toEqual([PRED]));
    await act(() => vi.advanceTimersByTimeAsync(RGROUP_POLL_MS));
    await waitFor(() => expect(result.current.data?.extractions[0]?.status).toBe("done"));
    const calls = get.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(RGROUP_POLL_MS * 3));
    expect(get.mock.calls.length).toBe(calls);
  });

  it("never asks for a paper without a scaffold", async () => {
    const get = vi.spyOn(api, "getPaperRgroups").mockResolvedValue(list(true));
    renderHook(() => useRgroupList(PAPER, false), { wrapper: ({ children }) => wrap(children) });
    await act(() => Promise.resolve());
    expect(get).not.toHaveBeenCalled();
  });
});

describe("the words and choices", () => {
  it("tells readings in flight", () => {
    expect(isRgroupActive("queued") && isRgroupActive("running")).toBe(true);
    expect(isRgroupActive("done") || isRgroupActive("failed") || isRgroupActive("none")).toBe(false);
    expect(anyRgroupActive(list(true, extraction()))).toBe(false);
    expect(anyRgroupActive(list(true, extraction({ status: "running" })))).toBe(true);
    expect(anyRgroupActive(undefined)).toBe(false);
  });

  it("finds one prediction's reading", () => {
    const l = list(true, extraction({ prediction_id: "a" }), extraction({ prediction_id: "b" }));
    expect(extractionFor(l, "b")?.prediction_id).toBe("b");
    expect(extractionFor(l, "c")).toBeUndefined();
    expect(extractionFor(undefined, "b")).toBeUndefined();
    expect(extractionFor(l, undefined)).toBeUndefined();
  });

  it("pins the words", () => {
    expect(rgroupProgress("queued")).toBe("Queued");
    expect(rgroupProgress("running")).toBe("Reading R-groups…");
    expect(rgroupFailure("engine_error")).toBe("R-groups not read: the model failed.");
    expect(rgroupFailure(null)).toBe("R-groups not read: an unknown error.");
    expect(reasonText("worker_lost", "rgroups")).toBe("the worker stopped");
    expect(compoundCount(1)).toBe("1 compound");
    expect(compoundCount(3)).toBe("3 compounds");
  });

  it("offers rows only for a shown scaffold prediction", () => {
    const pred = (over: Partial<PredictionOut>): PredictionOut => ({
      id: "p", engine: "decimer", engine_version: "2.7", smiles: "CCO", molfile: null,
      valid: true, ms: 1, cached: false, created_at: "2026-11-18T10:00:00Z", ...over,
    });
    const seg = (curation: SegmentOut["curation"], predictions: PredictionOut[]): SegmentOut =>
      ({ id: "s", page: 0, idx: 0, bbox: [0, 0, 1, 1], curation, predictions }) as SegmentOut;
    const scaffold = pred({ smiles: "[R1]c1ccccc1", valid: false, rgroups: ["R1"] });
    expect(scaffoldPrediction(shownStructure(seg(null, [scaffold]), "decimer"))?.id).toBe("p");
    expect(hasScaffold(seg(null, [pred({})]), "decimer")).toBe(false);
    const cur = (over: object) =>
      ({ status: "unchecked", smiles: null, molfile: null, note: null, ...over }) as SegmentOut["curation"];
    // an edited structure keeps the rows while it still has R-groups
    expect(hasScaffold(seg(cur({ smiles: "Cc1ccccc1*", rgroups: ["R1"] }), [scaffold]), "decimer")).toBe(true);
    expect(hasScaffold(seg(cur({ smiles: "Cc1ccccc1", rgroups: [] }), [scaffold]), "decimer")).toBe(false);
  });
});
