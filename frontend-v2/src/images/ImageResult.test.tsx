// The single image result (/app/images/:id): the job's states, the reason of a failure
// (never the raw error text), live refetches, a local-only edit, the gone page, and the
// slot Compare (F10) plugs into.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient } from "../api/queries";
import type { ImageJobOut, PredictionOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import { paperLayout } from "../test/paperLayout";
import ImageResult, { type ImageCompareProps } from "./ImageResult";

// The fixed MolNexTR's molfile of a CC BY crop (backend-v2/tests/fixtures): image positions.
const NEXTR = (
  JSON.parse(
    readFileSync(resolve(process.cwd(), "../backend-v2/tests/fixtures/molnextr_7a4e03f.json"), "utf8"),
  ) as Record<string, { molfile: string }>
)["corallomycetellains_p3_3"]!.molfile;

// The page's live stream: record each mount's onEvent and hand back a reconnect spy.
const live = vi.hoisted(() => ({
  mounted: [] as { kind: string; id: string }[],
  onEvent: null as null | (() => void),
  reconnect: vi.fn(),
  unmounted: 0,
  mode: "live" as string,
}));

vi.mock("../api/useLiveEvents", async () => {
  const { useEffect } = await import("react");
  return {
    useLiveEvents: (kind: string, id: string, onEvent: () => void) => {
      live.onEvent = onEvent;
      useEffect(() => {
        live.mounted.push({ kind, id });
        return () => {
          live.unmounted += 1;
        };
      }, [kind, id]);
      return { mode: live.mode, reconnect: live.reconnect };
    },
  };
});

const ID = "3f6c1a52-8d0e-4f43-9a7b-2b1c0d9e8f71";
const XSS = "<img src=x onerror=window.__xss=1>";

const CAFFEINE = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C";

function pred(over: Partial<PredictionOut> = {}): PredictionOut {
  return {
    id: "pr1",
    engine: "decimer",
    engine_version: "2.7.1",
    smiles: CAFFEINE,
    molfile: "CAFFEINE-MOL",
    valid: true,
    ms: 1240,
    cached: false,
    created_at: "2026-11-18T10:00:30Z",
    ...over,
  };
}

/**
 * A job as GET /images/{id} sends it. `prediction` (a test shorthand) is the job engine's
 * one prediction; `predictions` (newest first) overrides it. The default step is the job
 * engine's, as the pipeline writes it (the job itself is never "processing").
 */
function job(
  over: Partial<ImageJobOut> & { error?: string | null; prediction?: PredictionOut | null } = {},
): ImageJobOut {
  const { prediction = pred(), ...rest } = over;
  const status = rest.status ?? "done";
  const stepStatus = status === "processing" ? "running" : status;
  return {
    id: ID,
    status: "done",
    engine: "decimer",
    display_name: "drawing.png",
    created_at: "2026-11-18T10:00:00Z",
    expires_at: "2026-12-18T10:00:00Z",
    predictions: prediction ? [prediction] : [],
    error_class: null,
    steps: [
      { engine: rest.engine ?? "decimer", status: stepStatus, error_class: rest.error_class ?? null },
    ],
    ...rest,
  } as ImageJobOut;
}

function renderPage(at = `/app/images/${ID}`, props: Parameters<typeof ImageResult>[0] = {}) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  const view = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="/app/images/:id" element={<ImageResult {...props} />} />
            <Route path="/app" element={<p>tool home</p>} />
          </Routes>
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

beforeEach(() => {
  live.mounted = [];
  live.onEvent = null;
  live.reconnect = vi.fn();
  live.unmounted = 0;
  live.mode = "live";
  vi.spyOn(api, "depict").mockResolvedValue({ format: "svg", data: "<svg/>" });
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:depiction-${++n}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as { __xss?: unknown }).__xss;
});

describe("ImageResult", () => {
  it("shows a done job's SMILES, engine, validity and time, the image and the drawing", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    renderPage();
    expect(await screen.findByText("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toBeInTheDocument();
    const label = screen.getByRole("table");
    expect(within(label).getByText("DECIMER 2.7.1")).toBeInTheDocument();
    expect(within(label).getByText("Yes")).toBeInTheDocument();
    expect(within(label).getByText("1.2 s")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The uploaded image" })).toHaveAttribute(
      "src",
      `/api/v2/images/${ID}/image`,
    );
    const drawing = await screen.findByRole("img", {
      name: "Structure read from the image",
    });
    expect(drawing).toHaveAttribute("src", "blob:depiction-1");
    expect(api.depict).toHaveBeenCalledWith("CN1C=NC2=C1C(=O)N(C(=O)N2C)C");
    expect(live.mounted).toEqual([{ kind: "image", id: ID }]);
    await waitFor(() => expect(document.title).toBe("drawing.png · MARCUS"));
  });

  describe("the main result is the job engine's (A-I1)", () => {
    // an old job's MolNexTR (legacy): its molfile holds the image's positions
    const molnextr = pred({
      id: "pr2",
      engine: "molnextr",
      engine_version: "1.0",
      smiles: "c1ccccc1O",
      created_at: "2026-11-18T10:01:00Z",
    });
    const molscribe = pred({
      id: "pr3",
      engine: "molscribe",
      engine_version: "1.1",
      smiles: "C(",
      valid: false,
      created_at: "2026-11-18T10:02:00Z",
    });

    it("draws the main structure in the image's orientation once MolNexTR gave its positions", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({ predictions: [{ ...molnextr, molfile: NEXTR }, pred()] }),
      );
      renderPage();
      await screen.findByRole("img", { name: "Structure read from the image" });
      await waitFor(() => expect(api.depict).toHaveBeenCalledWith(CAFFEINE, { template: NEXTR }));
    });

    it("stays on the job engine's structure when Compare's engines finish later", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({
          predictions: [molscribe, molnextr, pred()],
          steps: [
            { engine: "molscribe", status: "done", error_class: null },
            { engine: "molnextr", status: "done", error_class: null },
            { engine: "decimer", status: "done", error_class: null },
          ],
        }),
      );
      renderPage();
      expect(await screen.findByText(CAFFEINE)).toBeInTheDocument();
      const label = screen.getByRole("table");
      expect(within(label).getByText("DECIMER 2.7.1")).toBeInTheDocument();
      expect(within(label).getByText("Yes")).toBeInTheDocument();
      expect(screen.queryByText("C(")).toBeNull();
      expect(screen.queryByText("Picked here, not saved")).toBeNull();
    });

    it("takes the engine's newest valid prediction over a newer invalid one", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({
          predictions: [
            pred({ id: "pr9", smiles: "C1CC", valid: false, created_at: "2026-11-18T10:05:00Z" }),
            pred(),
          ],
        }),
      );
      renderPage();
      expect(await screen.findByText(CAFFEINE)).toBeInTheDocument();
      expect(screen.queryByText("C1CC")).toBeNull();
    });

    it("says nothing about the queue while only Compare's engines run", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({
          status: "queued",
          steps: [
            { engine: "molscribe", status: "queued", error_class: null },
            { engine: "molnextr", status: "running", error_class: null },
            { engine: "decimer", status: "done", error_class: null },
          ],
        }),
      );
      renderPage();
      expect(await screen.findByText(CAFFEINE)).toBeInTheDocument();
      const result = screen.getByRole("region", { name: "Structure" });
      expect(within(result).queryByText("Waiting in the queue")).toBeNull();
      expect(within(result).queryByText("Reading…")).toBeNull();
    });

    it("reads 'Reading…' while the job engine's step runs (the job itself stays queued)", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({
          status: "queued",
          prediction: null,
          steps: [{ engine: "decimer", status: "running", error_class: null }],
        }),
      );
      renderPage();
      expect(await screen.findByText("Reading…")).toBeInTheDocument();
      expect(screen.queryByText("Waiting in the queue")).toBeNull();
      expect(screen.queryByText("The first run can take about 30 s")).toBeNull();
    });

    it("a DECIMER hand-drawn job says its first run loads the model while it reads", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({
          status: "processing",
          engine: "decimer-hand",
          prediction: null,
          steps: [{ engine: "decimer-hand", status: "running", error_class: null }],
        }),
      );
      renderPage();
      expect(await screen.findByText("Reading…")).toBeInTheDocument();
      expect(screen.getByText("The first run can take about 30 s")).toBeInTheDocument();
    });
  });

  it("Download image saves the drawing the page holds, with no fetch (C-I1: CSP)", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    const fetchSpy = vi.fn(() => Promise.reject(new TypeError("refused by connect-src")));
    vi.stubGlobal("fetch", fetchSpy);
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    try {
      renderPage();
      await screen.findByRole("img", { name: "Structure read from the image" });
      const before = vi.mocked(URL.createObjectURL).mock.calls.length;
      fireEvent.click(screen.getByRole("button", { name: "Download image" }));
      await waitFor(() => expect(saved).toEqual(["drawing-1.svg"]));
      expect(fetchSpy).not.toHaveBeenCalled();
      const blob = vi.mocked(URL.createObjectURL).mock.calls[before]![0] as Blob;
      expect(blob.type).toBe("image/svg+xml");
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.readAsText(blob);
      });
      expect(text).toBe("<svg/>");
      expect(screen.queryByText("Could not download the image")).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("revokes the drawing's object URL when the page goes away", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    const { unmount } = renderPage();
    await screen.findByRole("img", { name: "Structure read from the image" });
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:depiction-1");
  });

  it("shows a failed job's reason from error_class, never the raw error text", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(
      job({
        status: "failed",
        prediction: null,
        error_class: "engine_error",
        error: "Traceback: CUDA out of memory at /srv/marcus/worker.py",
        steps: [{ engine: "decimer", status: "failed", error_class: "engine_error" }],
      }),
    );
    renderPage();
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/the engine failed/)).toBeInTheDocument();
    expect(screen.queryByText(/CUDA|Traceback/)).toBeNull();
    expect(document.body.textContent).not.toContain("CUDA");
  });

  it("an unknown error class reads 'an unknown error'", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(
      job({ status: "failed", prediction: null, error_class: "kaboom" }),
    );
    renderPage();
    expect(await screen.findByText(/an unknown error/)).toBeInTheDocument();
  });

  it("Retry runs the job's engine again and reopens the stream", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(
      job({
        status: "failed",
        prediction: null,
        engine: "molscribe",
        error_class: "timeout",
      }),
    );
    const run = vi.spyOn(api, "runImagePrediction").mockResolvedValue({ step_id: "s1" });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
    expect(run).toHaveBeenCalledWith(ID, "molscribe");
  });

  it("an old job read with the legacy MolNexTR shows its failure without Retry", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(
      job({ status: "failed", prediction: null, engine: "molnextr", error_class: "timeout" }),
    );
    renderPage();
    expect(await screen.findByText(/Could not read a structure/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("a refused retry shows the API's reason as a toast", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(
      job({ status: "failed", prediction: null, error_class: "timeout" }),
    );
    vi.spyOn(api, "runImagePrediction").mockRejectedValue(
      new ApiError(409, "A prediction with this engine is already running"),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(
      await screen.findByText("A prediction with this engine is already running"),
    ).toBeInTheDocument();
    expect(live.reconnect).not.toHaveBeenCalled();
  });

  it("waits in the queue, then reads, then shows the result as live events arrive", async () => {
    const get = vi
      .spyOn(api, "getImageJob")
      .mockResolvedValueOnce(job({ status: "queued", prediction: null, steps: [] }))
      .mockResolvedValueOnce(
        job({
          status: "processing",
          prediction: null,
          steps: [{ engine: "decimer", status: "running", error_class: null }],
        }),
      )
      .mockResolvedValue(job());
    renderPage();
    expect(await screen.findByText("Waiting in the queue")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Image progress" })).not.toHaveAttribute("aria-valuenow");
    expect(get).toHaveBeenCalledTimes(1);

    act(() => live.onEvent!());
    expect(await screen.findByText("Reading…")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);

    act(() => live.onEvent!());
    expect(await screen.findByText("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("says so while live updates are paused on a running job", async () => {
    live.mode = "polling";
    vi.spyOn(api, "getImageJob").mockResolvedValue(job({ status: "processing", prediction: null }));
    renderPage();
    expect(await screen.findByText("Live updates paused, checking every 2 s")).toBeInTheDocument();
  });

  it("an editor save changes the shown SMILES on this page only, with no API write", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    const writes = [
      vi.spyOn(api, "putCuration"),
      vi.spyOn(api, "putBulkCuration"),
      vi.spyOn(api, "runImagePrediction"),
      vi.spyOn(api, "runPrediction"),
      vi.spyOn(api, "uploadImage"),
    ];
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit structure" });
    fireEvent.change(within(dialog).getByLabelText("SMILES"), {
      target: { value: "CCO" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save SMILES" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("CCO")).toBeInTheDocument();
    expect(screen.queryByText("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toBeNull();
    expect(screen.getByText("Edited here, not saved")).toBeInTheDocument();
    await waitFor(() => expect(api.depict).toHaveBeenLastCalledWith("CCO"));
    for (const write of writes) expect(write).not.toHaveBeenCalled();
  });

  it("the edited SMILES is the one copied", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("SMILES", { selector: "input" }), {
      target: { value: "CCO" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save SMILES" }));
    await screen.findByText("Edited here, not saved");
    // the SMILES's own Copy (the actions leave theirs out: one per place)
    fireEvent.click(screen.getByRole("button", { name: "Copy SMILES" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls).toEqual([["CCO"]]);
  });

  it("Undo edit brings back the engine's structure", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job());
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("SMILES", { selector: "input" }), {
      target: { value: "CCO" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save SMILES" }));
    fireEvent.click(await screen.findByRole("button", { name: "Undo edit" }));
    expect(screen.getByText("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toBeInTheDocument();
    expect(screen.queryByText("Edited here, not saved")).toBeNull();
  });

  it("a 404 shows the gone page and unmounts the live stream", async () => {
    vi.spyOn(api, "getImageJob").mockRejectedValue(new ApiError(404, "Not found"));
    renderPage();
    expect(await screen.findByText("This image is not here any more.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "It was deleted, it expired after 30 days, or it was opened in another browser.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your papers" })).toHaveAttribute("href", "/app");
    expect(live.mounted).toEqual([]);
  });

  it("a 404 on a later refresh drops the result and closes the stream", async () => {
    vi.spyOn(api, "getImageJob")
      .mockResolvedValueOnce(job({ status: "processing", prediction: null }))
      .mockRejectedValue(new ApiError(404, "Not found"));
    renderPage();
    await screen.findByText("Reading…");
    expect(live.mounted).toHaveLength(1);
    act(() => live.onEvent!());
    expect(await screen.findByText("This image is not here any more.")).toBeInTheDocument();
    expect(live.unmounted).toBe(1);
  });

  it("an id that is not a UUID gets the gone page without a request", async () => {
    const get = vi.spyOn(api, "getImageJob");
    renderPage("/app/images/not-an-id");
    expect(await screen.findByText("This image is not here any more.")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
    expect(live.mounted).toEqual([]);
  });

  it("another error offers Try again, not the gone page", async () => {
    const get = vi
      .spyOn(api, "getImageJob")
      .mockRejectedValueOnce(new ApiError(503, "The server is busy, try again in a moment."))
      .mockResolvedValue(job());
    renderPage();
    expect(await screen.findByText("This image could not be opened.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("renders a hostile file name as text", async () => {
    vi.spyOn(api, "getImageJob").mockResolvedValue(job({ display_name: XSS }));
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: XSS })).toBeInTheDocument();
    expect((window as { __xss?: unknown }).__xss).toBeUndefined();
  });

  describe("Compare slot", () => {
    const molparser: PredictionOut = {
      id: "pr2",
      engine: "molparser",
      engine_version: "1.0",
      smiles: "c1ccccc1O",
      molfile: null,
      valid: true,
      ms: 900,
      cached: false,
      created_at: "2026-11-18T10:01:00Z",
    };

    it("plugs in the real Compare: one Compare engines section, its Close, its engines started on this job", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({ predictions: [{ ...molparser, engine: "decimer", engine_version: "2.7.1" }] }),
      );
      const run = vi.spyOn(api, "runImagePrediction").mockResolvedValue({ step_id: "st" });
      renderPage();
      const open = await screen.findByRole("button", { name: "Compare" });
      open.focus();
      fireEvent.click(open);
      const section = await screen.findByRole("region", { name: "Compare engines" });
      expect(within(section).getByRole("button", { name: "Close" })).toHaveFocus();
      expect(screen.getAllByRole("heading", { name: "Compare engines" })).toHaveLength(1);
      await waitFor(() => expect(run).toHaveBeenCalledTimes(2));
      expect(run.mock.calls.map((c) => c[0])).toEqual([ID, ID]);
      await waitFor(() => expect(live.reconnect).toHaveBeenCalledTimes(1));
      fireEvent.click(within(section).getByRole("button", { name: "Close" }));
      expect(screen.queryByRole("region", { name: "Compare engines" })).toBeNull();
      expect(screen.getByRole("button", { name: "Compare" })).toHaveFocus();
    });

    it.each([
      ["decimer-hand", "true"],
      ["decimer", "false"],
    ])("an image read with %s opens Compare with Hand-drawn on=%s", async (engine, pressed) => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({ engine, prediction: pred({ engine }) }),
      );
      vi.spyOn(api, "runImagePrediction").mockResolvedValue({ step_id: "st" });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: "Compare" }));
      const section = await screen.findByRole("region", { name: "Compare engines" });
      expect(within(section).getByRole("switch", { name: "Hand-drawn" })).toHaveAttribute(
        "aria-checked",
        pressed,
      );
    });

    it("has one Copy SMILES (the SMILES's own)", async () => {
      vi.spyOn(api, "getImageJob").mockResolvedValue(job());
      renderPage();
      await screen.findByRole("button", { name: "Edit" });
      expect(screen.getAllByRole("button", { name: "Copy SMILES" })).toHaveLength(1);
    });

    it("Edit opens a DECIMER answer laid out like the paper (owner, 2026-11-27)", async () => {
      const layout = paperLayout();
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({ predictions: [pred(), pred({ id: "s1", engine: "molscribe", smiles: "CCC", valid: false, layout })] }),
      );
      const laidOut = vi.spyOn(api, "smilesToMolfile").mockResolvedValue("LAID OUT MOLFILE");
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
      await screen.findByRole("dialog", { name: "Edit structure" });
      expect(laidOut).toHaveBeenCalledWith(pred().smiles, layout);
    });

    it("hands Compare the image target, predictions, steps and the page's reconnect", async () => {
      const steps = [
        { engine: "molparser", status: "done", error_class: null },
        { engine: "decimer", status: "done", error_class: null },
      ];
      vi.spyOn(api, "getImageJob").mockResolvedValue(
        job({ predictions: [molparser, pred()], steps }),
      );
      const seen: ImageCompareProps[] = [];
      function FakeCompare(props: ImageCompareProps) {
        seen.push(props);
        return (
          <div>
            <button type="button" onClick={props.onStarted}>
              Run all engines
            </button>
            <button type="button" onClick={() => props.onPick(molparser)}>
              Use this one
            </button>
            {props.onEdit && (
              <button type="button" onClick={() => props.onEdit!(molparser)}>
                Edit and use
              </button>
            )}
          </div>
        );
      }
      renderPage(undefined, { compare: FakeCompare });
      fireEvent.click(await screen.findByRole("button", { name: "Compare" }));
      const last = seen.at(-1)!;
      expect(last.target).toEqual({ kind: "image", id: ID });
      expect(last.predictions).toEqual([molparser, pred()]);
      expect(last.steps).toEqual(steps);

      fireEvent.click(screen.getByRole("button", { name: "Run all engines" }));
      expect(live.reconnect).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByRole("button", { name: "Use this one" }));
      expect(await screen.findByText("c1ccccc1O")).toBeInTheDocument();
      expect(screen.getByText("Picked here, not saved")).toBeInTheDocument();
      expect(within(screen.getByRole("table")).getByText("MolParser 1.0")).toBeInTheDocument();

      // Edit and use (owner, 2026-11-27): the editor opens on that answer, Compare closes
      fireEvent.click(screen.getByRole("button", { name: "Compare" }));
      fireEvent.click(await screen.findByRole("button", { name: "Edit and use" }));
      const editor = await screen.findByRole("dialog", { name: "Edit structure" });
      expect(within(editor).getByLabelText("SMILES")).toHaveValue("c1ccccc1O");
      expect(screen.queryByRole("button", { name: "Edit and use" })).toBeNull();
    });
  });
});
