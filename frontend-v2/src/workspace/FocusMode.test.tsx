// Focus mode (/app/papers/:id?s=<segment>&focus=1): one structure large with its crop, its
// page and its box, SMILES, the engines' predictions and a note; the review keys (A accept,
// R reject, ← →, Esc, ?); accept and reject keep an edited structure and save the note;
// Esc returns to the grid with the same card focused.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { createQueryClient, keys, useSaveCuration } from "../api/queries";
import type { CurationOut, PaperDetail, PredictionOut, SegmentOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import { useReviewKeys } from "./useReviewKeys";
import { useWorkspace } from "./useWorkspace";
import Workspace from "./Workspace";

vi.mock("../api/useLiveEvents", () => ({
  useLiveEvents: () => ({ mode: "live", reconnect: () => undefined }),
}));

vi.mock("../api/depictions", () => ({
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

function curation(over: Partial<CurationOut> = {}): CurationOut {
  return { status: "unchecked", smiles: null, molfile: null, note: null, ...over };
}

function segment(id: string, over: Partial<SegmentOut> = {}): SegmentOut {
  const n = Number(id.replace(/\D/g, "")) || 0;
  return {
    id,
    page: 0,
    idx: n,
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
    counts: { steps_by_status: {} },
    segments,
  };
}

let client: QueryClient;

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{`${loc.pathname}${loc.search}`}</output>;
}

function renderAt(p: PaperDetail, search = "") {
  vi.spyOn(api, "getPaper").mockResolvedValue(p);
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps: [] });
  vi.spyOn(api, "getQueue").mockResolvedValue({ papers: [], estimate_s: 0 });
  client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
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
}

/** Opens focus mode on the structure tagged `tag` the way a curator does: Enter on its card. */
async function openWithEnter(tag: string) {
  const card = await waitFor(() => {
    const found = screen
      .getAllByRole("article")
      .find((c) => c.getAttribute("aria-label")?.startsWith(tag));
    if (!found) throw new Error(`no card ${tag}`);
    return found;
  });
  card.focus();
  fireEvent.keyDown(card, { key: "Enter" });
  return focusRegion();
}

const focusRegion = () => screen.findByRole("region", { name: /^Focus/ });
const press = (key: string, init: KeyboardEventInit = {}) =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...init });

function putSpy() {
  return vi
    .spyOn(api, "putCuration")
    .mockImplementation((_id, body) => Promise.resolve({ ...body }));
}

beforeEach(() => {
  pseq = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("focus mode", () => {
  it("Enter on a card opens focus mode on that structure, with its page, box and engines", async () => {
    renderAt(
      paper([
        segment("s1"),
        segment("s2", {
          page: 1,
          predictions: [
            prediction({ engine: "molnextr", smiles: "CCN", valid: false }),
            prediction({ engine: "decimer", smiles: "CCO" }),
          ],
        }),
      ]),
    );
    const region = await openWithEnter("[02]");
    expect(within(region).getByText("[02] · Page 2")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`?s=s2&focus=1`);
    // The grid is out of the way (hidden, still mounted so its filter and selection stay).
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    // The page image with its marker, and the crop.
    const page = within(region).getByRole("img", { name: "Page 2" });
    expect(page).toHaveAttribute("src", `/api/v2/papers/${ID}/pages/1/image`);
    expect(within(region).getByRole("img", { name: "Crop [02]" })).toHaveAttribute(
      "src",
      "/api/v2/segments/s2/image",
    );
    // Engines listed, newest per engine, with validity.
    const engines = within(region).getByRole("table", { name: "Engines" });
    expect(within(engines).getByRole("rowheader", { name: /MolNexTR/ })).toBeInTheDocument();
    expect(within(engines).getByText("CCN")).toBeInTheDocument();
    expect(within(engines).getByText(/Invalid/)).toBeInTheDocument();
    // The shown SMILES: the paper engine's valid prediction.
    expect(within(region).getAllByText("CCO").length).toBeGreaterThan(0);
  });

  it("draws the box from bbox [x0, y0, x1, y1] scaled to the page image", async () => {
    renderAt(paper([segment("s1", { bbox: [248, 702, 1240, 1404] })]), "?s=s1&focus=1");
    const region = await focusRegion();
    const page = within(region).getByRole("img", { name: "Page 1" });
    Object.defineProperty(page, "naturalWidth", { value: 2480 });
    Object.defineProperty(page, "naturalHeight", { value: 3510 });
    fireEvent.load(page);
    const marker = await within(region).findByTestId("marker-s1");
    // x0/W = 10 %, y0/H = 20 %, (x1-x0)/W = 40 %, (y1-y0)/H = 20 % (not width/height = x1/y1)
    expect(marker.style.getPropertyValue("--l")).toBe("10%");
    expect(marker.style.getPropertyValue("--t")).toBe("20%");
    expect(marker.style.getPropertyValue("--w")).toBe("40%");
    expect(marker.style.getPropertyValue("--h")).toBe("20%");
    expect(marker).toHaveTextContent("[01]");
    expect(within(region).getByText(/X0 248 · Y0 702 · X1 1240 · Y1 1404 PX/)).toBeInTheDocument();
  });

  it("A accepts an unedited structure (smiles and molfile null) and lands the Accepted stamp", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await focusRegion();
    press("a");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "accepted",
      smiles: null,
      molfile: null,
      note: null,
    });
    expect(within(region).getByRole("img", { name: "Accepted" })).toBeInTheDocument();
  });

  it("accept after an edit keeps the edited SMILES and molfile (and the note)", async () => {
    const put = putSpy();
    renderAt(
      paper([
        segment("s1", {
          curation: curation({ status: "unchecked", smiles: "CCO", molfile: "<m>", note: "n" }),
        }),
      ]),
      "?s=s1&focus=1",
    );
    await focusRegion();
    press("A");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "accepted",
      smiles: "CCO",
      molfile: "<m>",
      note: "n",
    });
  });

  it("R rejects with the same rule and lands the charcoal Rejected stamp", async () => {
    const put = putSpy();
    renderAt(
      paper([
        segment("s1", {
          curation: curation({ status: "unchecked", smiles: "CCO", molfile: "<m>", note: "n" }),
        }),
      ]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    press("r");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "rejected",
      smiles: "CCO",
      molfile: "<m>",
      note: "n",
    });
    expect(within(region).getByRole("img", { name: "Rejected" })).toBeInTheDocument();
  });

  it("after a decision it moves on to the next To check structure (skipping decided ones)", async () => {
    putSpy();
    renderAt(
      paper([
        segment("s1"),
        segment("s2", { curation: curation({ status: "accepted" }) }),
        segment("s3"),
      ]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    press("a");
    await waitFor(() => expect(within(region).getByText("[03] · Page 1")).toBeInTheDocument());
    expect(screen.getByTestId("where")).toHaveTextContent("?s=s3&focus=1");
  });

  it("under reduced motion it moves on at once (no wait for the stamp)", async () => {
    putSpy();
    const real = window.matchMedia;
    window.matchMedia = vi.fn((query: string) => ({
      matches: query.includes("reduce"),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
      await focusRegion();
      vi.useFakeTimers();
      act(() => {
        press("a");
      });
      // No timer needed: the next structure is there before any time passes.
      expect(screen.getByTestId("where")).toHaveTextContent("?s=s2&focus=1");
    } finally {
      vi.useRealTimers();
      window.matchMedia = real;
    }
  });

  it("the note is saved with the next accept, and on blur (keeping status and structure)", async () => {
    const put = putSpy();
    renderAt(
      paper([
        segment("s1", {
          curation: curation({ status: "accepted", smiles: "CCO", molfile: "<m>", note: null }),
        }),
        segment("s2"),
      ]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    const note = within(region).getByRole("textbox", { name: "Note" });
    note.focus();
    fireEvent.change(note, { target: { value: "ring closure unclear" } });
    fireEvent.blur(note);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "accepted",
      smiles: "CCO",
      molfile: "<m>",
      note: "ring closure unclear",
    });
    // An unchanged note is not saved again on the next blur.
    note.focus();
    fireEvent.blur(note);
    // The next decision carries the note.
    region.focus(); // back in the region (what Esc in the note does): the keys act there
    press("r");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1]![1]).toEqual({
      status: "rejected",
      smiles: "CCO",
      molfile: "<m>",
      note: "ring closure unclear",
    });
  });

  it("typing a in the note field does not accept", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1")]), "?s=s1&focus=1");
    const region = await focusRegion();
    const note = within(region).getByRole("textbox", { name: "Note" });
    note.focus();
    fireEvent.keyDown(note, { key: "a" });
    fireEvent.keyDown(note, { key: "ArrowRight" });
    expect(put).not.toHaveBeenCalled();
    expect(within(region).queryByRole("img", { name: "Accepted" })).toBeNull();
  });

  it("Ctrl, Meta or Alt with a key does nothing (browser shortcuts stay)", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    await focusRegion();
    press("a", { ctrlKey: true });
    press("r", { metaKey: true });
    press("ArrowRight", { altKey: true });
    expect(put).not.toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("?s=s1&focus=1");
  });

  it("ArrowRight and ArrowLeft move between structures (replacing the URL entry)", async () => {
    renderAt(paper([segment("s1"), segment("s2"), segment("s3")]), "?s=s1&focus=1");
    const region = await focusRegion();
    press("ArrowRight");
    await waitFor(() => expect(within(region).getByText("[02] · Page 1")).toBeInTheDocument());
    press("ArrowRight");
    await waitFor(() => expect(within(region).getByText("[03] · Page 1")).toBeInTheDocument());
    press("ArrowRight"); // the last one: stays
    expect(within(region).getByText("[03] · Page 1")).toBeInTheDocument();
    press("ArrowLeft");
    await waitFor(() => expect(within(region).getByText("[02] · Page 1")).toBeInTheDocument());
  });

  it("Escape returns to the grid with the same card focused", async () => {
    renderAt(paper([segment("s1"), segment("s2"), segment("s3")]));
    await openWithEnter("[01]");
    press("ArrowRight");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?s=s2&focus=1"));
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("region", { name: /^Focus/ })).toBeNull());
    const card = screen
      .getAllByRole("article")
      .find((c) => c.getAttribute("aria-label")?.startsWith("[02]"));
    await waitFor(() => expect(card).toHaveFocus());
    expect(card).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("where")).toHaveTextContent(`/app/papers/${ID}?s=s2`);
    expect(screen.getByTestId("where")).not.toHaveTextContent("focus");
  });

  it("Escape on a focus link opened directly also returns to the grid", async () => {
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s2&focus=1");
    await focusRegion();
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("region", { name: /^Focus/ })).toBeNull());
    const card = screen
      .getAllByRole("article")
      .find((c) => c.getAttribute("aria-label")?.startsWith("[02]"));
    await waitFor(() => expect(card).toHaveFocus());
  });

  it("? opens a dialog named Keys with the key list; Escape closes it, not focus mode", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1")]), "?s=s1&focus=1");
    const region = await focusRegion();
    press("?");
    const dialog = await screen.findByRole("dialog", { name: "Keys" });
    expect(dialog.tagName).toBe("DIALOG"); // native: the page behind is inert
    expect(within(dialog).getByText("Accept")).toBeInTheDocument();
    expect(within(dialog).getByText("Compare engines")).toBeInTheDocument();
    expect(dialog.contains(document.activeElement)).toBe(true);
    // A key while the list is open does not decide.
    press("a");
    expect(put).not.toHaveBeenCalled();
    // Focus stays inside (trap): Tab from the last focusable goes back to the first.
    const close = within(dialog).getByRole("button", { name: "Close" });
    close.focus();
    fireEvent.keyDown(close, { key: "Tab" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keys" })).toBeNull());
    expect(region).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^Focus/ })).toBeInTheDocument();
  });

  it("A does nothing on a structure with nothing to accept (only an invalid prediction)", async () => {
    const put = putSpy();
    renderAt(
      paper([segment("s1", { predictions: [prediction({ valid: false, smiles: "C(" })] })]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    expect(within(region).getByRole("button", { name: /^Accept/ })).toBeDisabled();
    press("a");
    expect(put).not.toHaveBeenCalled();
    press("r");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]![1].status).toBe("rejected");
  });

  it("E opens the editor on the shown structure; the review keys hold; Esc closes only it", async () => {
    const put = putSpy();
    renderAt(
      paper([segment("s1", { predictions: [prediction({ smiles: "CCN", molfile: "M1" })] }), segment("s2")]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    press("e");
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(within(dialog).getByLabelText("SMILES")).toHaveValue("CCN");
    // Keys typed while the editor is open (focus on its Close button, not a text field).
    within(dialog).getByRole("button", { name: "Close" }).focus();
    for (const key of ["a", "r", "ArrowRight", "c", "?"]) press(key);
    await act(() => new Promise((r) => setTimeout(r, 20)));
    expect(put).not.toHaveBeenCalled();
    expect(within(region).queryByRole("img", { name: /Accepted|Rejected/ })).toBeNull();
    expect(region).toHaveAccessibleName("Focus [01]");
    expect(screen.queryByRole("dialog", { name: /Compare engines|Keys/ })).toBeNull();
    // A key from the page behind (focus left the dialog) is held too.
    fireEvent.keyDown(document.body, { key: "a" });
    await act(() => new Promise((r) => setTimeout(r, 20)));
    expect(put).not.toHaveBeenCalled();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Edit structure" })).toBeInTheDocument();
    // Esc in the dialog closes the editor and leaves focus mode open.
    fireEvent.keyDown(within(dialog).getByRole("button", { name: "Close" }), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit structure" })).toBeNull());
    expect(await focusRegion()).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("focus=1");
  });

  it("a save in the editor keeps the note and accepts a structure still to check", async () => {
    const put = putSpy();
    renderAt(
      paper([segment("s1", { curation: curation({ note: "n" }) })]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    fireEvent.click(within(region).getByRole("button", { name: /^Edit/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    fireEvent.change(within(dialog).getByLabelText("SMILES"), { target: { value: "CCO" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save SMILES" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0]).toEqual([
      "s1",
      { status: "accepted", smiles: "CCO", molfile: null, note: "n" },
    ]);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit structure" })).toBeNull());
    expect(within(region).getByRole("img", { name: "Accepted" })).toBeInTheDocument();
  });

  it("E right after R edits the structure it opened on: the move is cancelled, the save goes there", async () => {
    const put = putSpy();
    renderAt(
      paper([
        segment("s1", { predictions: [prediction({ smiles: "CCN" })] }),
        segment("s2", { predictions: [prediction({ smiles: "CCC" })] }),
      ]),
      "?s=s1&focus=1",
    );
    const region = await focusRegion();
    press("r");
    press("e");
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(within(dialog).getByLabelText("SMILES")).toHaveValue("CCN");
    // Past the advance wait: focus mode stays on [01] while its editor is open.
    await act(() => new Promise((r) => setTimeout(r, 400)));
    expect(region).toHaveAccessibleName("Focus [01]");
    fireEvent.change(within(dialog).getByLabelText("SMILES"), { target: { value: "CCBr" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save SMILES" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[0]![0]).toBe("s1");
    expect(put.mock.calls[1]![0]).toBe("s1");
    expect(put.mock.calls[1]![1]).toMatchObject({ smiles: "CCBr" });
    expect(put.mock.calls.some(([id]) => id === "s2")).toBe(false);
  });

  it("C right after A compares the structure it opened on (the move is cancelled)", async () => {
    putSpy();
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await focusRegion();
    press("a");
    press("c");
    await screen.findByRole("dialog", { name: /Compare engines/ });
    await act(() => new Promise((r) => setTimeout(r, 400)));
    expect(region).toHaveAccessibleName("Focus [01]");
    expect(screen.getByTestId("where")).toHaveTextContent("?s=s1&focus=1");
  });

  it.each([
    ["e", "Edit structure"],
    ["c", /Compare engines/],
  ] as const)(
    "a pinned dialog (%s) whose structure is deleted live closes and the review keys work again",
    async (key, dialogName) => {
      const put = putSpy();
      renderAt(paper([segment("s1"), segment("s2"), segment("s3")]), "?s=s1&focus=1");
      const region = await focusRegion();
      // The dialog opens on [01]; a marker behind it moves focus mode to [02] (the dialog stays
      // pinned to [01]); then [01] is deleted in another tab.
      const page = within(region).getByRole("img", { name: "Page 1" });
      Object.defineProperty(page, "naturalWidth", { value: 2480 });
      Object.defineProperty(page, "naturalHeight", { value: 3510 });
      fireEvent.load(page);
      press(key);
      await screen.findByRole("dialog", { name: dialogName });
      fireEvent.click(await within(region).findByRole("button", { name: "Open [02]" }));
      await waitFor(() => expect(region).toHaveAccessibleName("Focus [02]"));
      act(() => {
        client.setQueryData(keys.paper(ID), paper([segment("s2"), segment("s3")]));
      });
      await waitFor(() => expect(screen.queryByRole("dialog", { name: dialogName })).toBeNull());
      (await focusRegion()).focus();
      press("a");
      await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
      expect(put.mock.calls[0]![0]).toBe("s2");
    },
  );

  it("an edited structure opens with its curated SMILES and molfile; C still opens Compare", async () => {
    putSpy();
    renderAt(
      paper([
        segment("s1", {
          curation: curation({ status: "rejected", smiles: "CCCl", molfile: "M2" }),
        }),
      ]),
      "?s=s1&focus=1",
    );
    await focusRegion();
    press("e");
    const dialog = await screen.findByRole("dialog", { name: "Edit structure" });
    expect(within(dialog).getByLabelText("SMILES")).toHaveValue("CCCl");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit structure" })).toBeNull());
    press("c");
    expect(await screen.findByRole("dialog", { name: /Compare engines/ })).toBeInTheDocument();
  });

  it("shows the structure actions, with Edit and Compare once (in the decision row)", async () => {
    renderAt(paper([segment("s1")]), "?s=s1&focus=1");
    const region = await focusRegion();
    for (const name of ["Copy SMILES", "Copy molfile", "Download image", "Look up in PubChem"]) {
      expect(within(region).getByRole("button", { name })).toBeInTheDocument(); // one each
    }
    expect(within(region).getAllByRole("button", { name: /^Edit/ })).toHaveLength(1);
    expect(within(region).getAllByRole("button", { name: /^Compare/ })).toHaveLength(1);
  });

  it("a save that fails says so and takes the stamp back", async () => {
    vi.spyOn(api, "putCuration").mockRejectedValue(new Error("down"));
    renderAt(paper([segment("s1")]), "?s=s1&focus=1");
    const region = await focusRegion();
    press("a");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Not saved/);
    await waitFor(() => expect(within(region).queryByRole("img", { name: "Accepted" })).toBeNull());
  });
});

describe("useReviewKeys", () => {
  // The keys act only while focus is inside the focus-mode region (WCAG 2.1.4, "active only
  // on focus"): each test gets a focusable region and sends its keys from there.
  let region: HTMLElement;
  beforeEach(() => {
    region = document.createElement("section");
    region.tabIndex = -1;
    document.body.append(region);
    region.focus();
  });
  afterEach(() => region.remove());
  const keysIn = (h: ReturnType<typeof handlers>) =>
    renderHook(() => useReviewKeys({ current: region }, h));

  function handlers() {
    return {
      accept: vi.fn(),
      reject: vi.fn(),
      edit: vi.fn(),
      compare: vi.fn(),
      prev: vi.fn(),
      next: vi.fn(),
      close: vi.fn(),
      help: vi.fn(),
    };
  }

  it("maps the keys exactly (A R E C ← → Esc ?)", () => {
    const h = handlers();
    keysIn(h);
    for (const key of ["a", "r", "e", "c", "ArrowLeft", "ArrowRight", "Escape", "?"]) {
      fireEvent.keyDown(region, { key });
    }
    for (const fn of Object.values(h)) expect(fn).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(region, { key: "x" });
    for (const fn of Object.values(h)) expect(fn).toHaveBeenCalledTimes(1);
  });

  it("does nothing while focus is outside the region (keys active only on focus, 2.1.4)", () => {
    const h = handlers();
    keysIn(h);
    const outside = document.createElement("button");
    document.body.append(outside);
    try {
      outside.focus();
      for (const key of ["a", "r", "e", "c", "ArrowLeft", "ArrowRight", "Escape", "?"]) {
        fireEvent.keyDown(outside, { key });
        fireEvent.keyDown(document.body, { key });
      }
      for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled();
      // Back inside (a child of the region counts): the keys work again.
      const inside = document.createElement("button");
      region.append(inside);
      inside.focus();
      fireEvent.keyDown(inside, { key: "a" });
      expect(h.accept).toHaveBeenCalledTimes(1);
    } finally {
      outside.remove();
    }
  });

  it("ignores keys in inputs, textareas, selects and the Ketcher iframe", () => {
    const h = handlers();
    keysIn(h);
    const host = document.createElement("div");
    const select = document.createElement("select");
    select.append(document.createElement("option"));
    region.append(host);
    host.append(
      document.createElement("input"),
      document.createElement("textarea"),
      select,
      document.createElement("iframe"),
    );
    for (const el of [...host.children] as HTMLElement[]) {
      el.focus();
      fireEvent.keyDown(el, { key: "a" });
    }
    expect(h.accept).not.toHaveBeenCalled();
    host.remove();
  });

  it("does nothing, and leaves Esc its default, while a native dialog is open", () => {
    const h = handlers();
    keysIn(h);
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.append(dialog);
    try {
      // Focus in the region: still the dialog's keys.
      for (const key of ["a", "r", "e", "c", "ArrowLeft", "ArrowRight", "?"]) {
        fireEvent.keyDown(region, { key });
      }
      const esc = fireEvent.keyDown(region, { key: "Escape" });
      expect(esc).toBe(true); // not default-prevented: the dialog's cancel can fire
      for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled();
    } finally {
      dialog.remove();
    }
    fireEvent.keyDown(region, { key: "a" });
    expect(h.accept).toHaveBeenCalledTimes(1);
  });

  it("does nothing while a non-native modal (Compare, Keys) is open or the tool is hidden", () => {
    const h = handlers();
    keysIn(h);
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    const hidden = document.createElement("div");
    hidden.setAttribute("data-keys-off", "");
    for (const el of [modal, hidden]) {
      document.body.append(el);
      try {
        for (const key of ["a", "r", "e", "c", "ArrowLeft", "ArrowRight", "Escape", "?"]) {
          fireEvent.keyDown(region, { key });
        }
        for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled();
      } finally {
        el.remove();
      }
    }
    fireEvent.keyDown(region, { key: "a" });
    expect(h.accept).toHaveBeenCalledTimes(1);
  });

  it("ignores a held key for decisions (no repeat accept)", () => {
    const h = handlers();
    keysIn(h);
    fireEvent.keyDown(region, { key: "a", repeat: true });
    fireEvent.keyDown(region, { key: "ArrowRight", repeat: true });
    expect(h.accept).not.toHaveBeenCalled();
    expect(h.next).toHaveBeenCalledTimes(1);
  });

  it("is removed on unmount", () => {
    const h = handlers();
    const { unmount } = keysIn(h);
    unmount();
    act(() => {
      fireEvent.keyDown(region, { key: "a" });
    });
    expect(h.accept).not.toHaveBeenCalled();
  });
});

describe("useSaveCuration counts", () => {
  it("moves the paper's counts with the saved status (the header stays right)", async () => {
    vi.spyOn(api, "putCuration").mockImplementation((_id, body) => Promise.resolve({ ...body }));
    const qc = createQueryClient();
    qc.setQueryData(keys.paper(ID), paper([segment("s1"), segment("s2")]));
    const { result } = renderHook(() => useSaveCuration(ID), {
      wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
    });
    await act(() => result.current.save("s1", { status: "accepted" }));
    let p = qc.getQueryData<PaperDetail>(keys.paper(ID))!;
    expect([p.accepted, p.rejected, p.to_review]).toEqual([1, 0, 1]);
    await act(() => result.current.save("s1", { status: "rejected" }));
    p = qc.getQueryData<PaperDetail>(keys.paper(ID))!;
    expect([p.accepted, p.rejected, p.to_review]).toEqual([0, 1, 1]);
    await act(() => result.current.save("s1", { note: "x" }));
    p = qc.getQueryData<PaperDetail>(keys.paper(ID))!;
    expect([p.accepted, p.rejected, p.to_review]).toEqual([0, 1, 1]);
  });
});

describe("focus mode keys act only inside focus mode (WCAG 2.1.4)", () => {
  it("a key pressed with focus outside focus mode does nothing", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await focusRegion();
    expect(region).toHaveFocus(); // open: the region takes focus, the keys work at once
    const outside = document.createElement("button");
    document.body.append(outside);
    try {
      outside.focus();
      for (const key of ["a", "r", "e", "c", "ArrowRight", "?", "Escape"]) press(key);
      (document.activeElement as HTMLElement).blur(); // focus on the page body
      for (const key of ["a", "r", "ArrowRight"]) press(key);
      await act(() => new Promise((r) => setTimeout(r, 20)));
      expect(put).not.toHaveBeenCalled();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.getByTestId("where")).toHaveTextContent("?s=s1&focus=1");
      // Focus back in the region: A accepts.
      region.focus();
      press("a");
      await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    } finally {
      outside.remove();
    }
  });

  it("a decision or step made with focus outside brings focus back into the region", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1"), segment("s2"), segment("s3")]), "?s=s1&focus=1");
    const region = await focusRegion();
    // A click that leaves focus on the page body (Safari does not focus a clicked button).
    (document.activeElement as HTMLElement).blur();
    fireEvent.click(within(region).getByRole("button", { name: /^Next structure/ }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?s=s2&focus=1"));
    expect(region.contains(document.activeElement)).toBe(true);
    (document.activeElement as HTMLElement).blur();
    fireEvent.click(within(region).getByRole("button", { name: /^Reject/ }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(region.contains(document.activeElement)).toBe(true);
    // The next key works with no extra click.
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?s=s3&focus=1"));
    press("a");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
  });

  it("Esc closes Keys after a click on plain text inside it (the box takes focus)", async () => {
    renderAt(paper([segment("s1")]), "?s=s1&focus=1");
    await focusRegion();
    press("?");
    const dialog = await screen.findByRole("dialog", { name: "Keys" });
    expect(dialog).toHaveAttribute("tabindex", "-1");
    dialog.focus(); // what a click on the key list does to focus
    expect(dialog).toHaveFocus();
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keys" })).toBeNull());
    expect(screen.getByRole("region", { name: /^Focus/ })).toBeInTheDocument();
  });
});

describe("focus mode follow-ups (F8 review)", () => {
  it("announces each step: [nn] · Page n · state in the polite status", async () => {
    renderAt(
      paper([segment("s1"), segment("s2", { curation: curation({ status: "accepted" }) })]),
      "?s=s1&focus=1",
    );
    await focusRegion();
    press("ArrowRight");
    await waitFor(() =>
      expect(
        screen.getAllByRole("status").some((s) => s.textContent === "[02] · Page 1 · Accepted"),
      ).toBe(true),
    );
  });

  it("keeps the keyboard in focus mode after a marker click", async () => {
    renderAt(paper([segment("s1"), segment("s2", { bbox: [500, 600, 900, 1000] })]), "?s=s1&focus=1");
    const region = await focusRegion();
    const page = within(region).getByRole("img", { name: "Page 1" });
    Object.defineProperty(page, "naturalWidth", { value: 2480 });
    Object.defineProperty(page, "naturalHeight", { value: 3510 });
    fireEvent.load(page);
    const other = await within(region).findByRole("button", { name: "Open [02]" });
    other.focus();
    fireEvent.click(other);
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("?s=s2&focus=1"));
    await waitFor(() => expect(region).toHaveFocus());
  });

  it("keeps the keyboard in focus mode when the focused button turns disabled", async () => {
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await focusRegion();
    const next = within(region).getByRole("button", { name: "Next structure" });
    next.focus();
    fireEvent.click(next);
    await waitFor(() => expect(next).toBeDisabled());
    await waitFor(() => expect(region).toHaveFocus());
  });

  it("a saved note draft is dropped, so a newer stored note is not overwritten", async () => {
    const put = putSpy();
    renderAt(paper([segment("s1"), segment("s2")]), "?s=s1&focus=1");
    const region = await focusRegion();
    const note = within(region).getByRole("textbox", { name: "Note" });
    note.focus();
    fireEvent.change(note, { target: { value: "old" } });
    fireEvent.blur(note);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    // The stored note changes elsewhere (another tab, a later editor).
    await act(async () => {
      client.setQueryData<PaperDetail>(keys.paper(ID), (old) =>
        old && {
          ...old,
          segments: old.segments.map((s) =>
            s.id === "s1" ? { ...s, curation: curation({ note: "newer" }) } : s,
          ),
        },
      );
    });
    await waitFor(() => expect(note).toHaveValue("newer"));
    region.focus(); // back in the region (what Esc in the note does): the keys act there
    press("a");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1]![1]).toMatchObject({ status: "accepted", note: "newer" });
  });
});

describe("useWorkspace closeFocus", () => {
  it("goes Back once, however often it is called before the focus flag drops", async () => {
    vi.spyOn(api, "getPaper").mockResolvedValue(paper([segment("s1")]));
    vi.spyOn(api, "getSteps").mockResolvedValue({ steps: [] });
    const qc = createQueryClient();
    let where = "";
    function Probe() {
      where = useLocation().pathname + useLocation().search;
      return null;
    }
    const { result } = renderHook(() => useWorkspace(ID), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={["/app", `/app/papers/${ID}`]} initialIndex={1}>
            {children}
            <Probe />
          </MemoryRouter>
        </QueryClientProvider>
      ),
    });
    act(() => result.current.openFocus("s1"));
    expect(where).toBe(`/app/papers/${ID}?s=s1&focus=1`);
    act(() => {
      result.current.closeFocus();
      result.current.closeFocus();
    });
    await waitFor(() => expect(where).toBe(`/app/papers/${ID}`));
    expect(result.current.focus).toBe(false);
  });
});
