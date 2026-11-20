// Tool home (/app): upload checks in the browser, where an upload goes, the sample paper,
// the papers list (expiry, delete with a confirm), 429 text, and hostile names as text.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient } from "../api/queries";
import type { ImageJobSummary, PaperSummary, StepOut } from "../api/types";
import { ToastHost, ToastProvider } from "../ui/Toasts";
import { handOff } from "./files";
import ToolHome from "./ToolHome";

const DAY = 86_400_000;
const MB = 1024 * 1024;
const SAMPLE_NAME = "Sample paper (synthetic).pdf";
const XSS = "<img src=x onerror=alert(1)>";

function paper(over: Partial<PaperSummary> = {}): PaperSummary {
  return {
    id: "p1",
    display_name: "alkaloids.pdf",
    status: "done",
    pages: 8,
    doi: null,
    title: "Alkaloids from Coffea leaves",
    first_author: null,
    year: null,
    engine: "decimer",
    ocsr_mode: "auto",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 20 * DAY).toISOString(),
    structures: 15,
    accepted: 9,
    rejected: 2,
    to_review: 3,
    failed_pages: 1,
    failed: 1,
    ...over,
  };
}

function imageJob(over: Partial<ImageJobSummary> = {}): ImageJobSummary {
  return {
    id: "i1",
    display_name: "drawing.png",
    status: "done",
    engine: "decimer",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 10 * DAY).toISOString(),
    ...over,
  };
}

function PaperPage() {
  return <p>paper page {useParams().id}</p>;
}

function ImagePage() {
  return <p>image page {useParams().id}</p>;
}

type Entry = string | { pathname: string; search?: string; state?: unknown };

function renderHome(
  opts: {
    at?: Entry;
    papers?: PaperSummary[];
    images?: ImageJobSummary[];
    papersReply?: Promise<{ papers: PaperSummary[] }>;
  } = {},
) {
  if (opts.papersReply) vi.spyOn(api, "listPapers").mockReturnValue(opts.papersReply);
  else vi.spyOn(api, "listPapers").mockResolvedValue({ papers: opts.papers ?? [] });
  vi.spyOn(api, "listImages").mockResolvedValue({ jobs: opts.images ?? [] });
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[opts.at ?? "/app"]}>
          <Routes>
            <Route path="/app" element={<ToolHome />} />
            <Route path="/app/papers/:id" element={<PaperPage />} />
            <Route path="/app/images/:id" element={<ImagePage />} />
          </Routes>
        </MemoryRouter>
        <ToastHost />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function fileOf(name: string, type: string, size = 1024): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function pick(container: HTMLElement, file: File) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  vi.spyOn(api, "getSteps").mockResolvedValue({ steps: [] });
  vi.spyOn(api, "uploadPaper").mockResolvedValue({ paper_id: "new-paper", status: "checking" });
  vi.spyOn(api, "uploadImage").mockResolvedValue({ image_job_id: "new-image", status: "queued" });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Upload checks in the browser", () => {
  it("refuses a file over 20 MB without a request", async () => {
    const { container } = renderHome();
    pick(container, fileOf("big.pdf", "application/pdf", 21 * MB));
    expect(await screen.findByText("This file is larger than 20 MB.")).toBeInTheDocument();
    expect(api.uploadPaper).not.toHaveBeenCalled();
    expect(api.uploadImage).not.toHaveBeenCalled();
  });

  it("refuses a GIF without a request", async () => {
    const { container } = renderHome();
    pick(container, fileOf("anim.gif", "image/gif"));
    expect(
      await screen.findByText("Use a PDF or a PNG, JPEG, TIFF or WebP image."),
    ).toBeInTheDocument();
    expect(api.uploadPaper).not.toHaveBeenCalled();
    expect(api.uploadImage).not.toHaveBeenCalled();
  });

  it("accepts a file dropped on the drop area", async () => {
    renderHome();
    const area = screen.getByTestId("drop-area");
    fireEvent.drop(area, {
      dataTransfer: { files: [fileOf("paper.pdf", "application/pdf")], types: ["Files"] },
    });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
  });
});

describe("Where an upload goes", () => {
  it("sends a PDF with DECIMER and ocsr auto, then opens the paper", async () => {
    const { container } = renderHome();
    pick(container, fileOf("paper.pdf", "application/pdf"));
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
    const [file, opts] = vi.mocked(api.uploadPaper).mock.calls[0]!;
    expect(file.name).toBe("paper.pdf");
    expect(opts).toEqual({ engine: "decimer", ocsr: "auto" });
  });

  it("sends ocsr off when the switch is off", async () => {
    const { container } = renderHome();
    const toggle = screen.getByRole("switch", { name: "Find structures automatically" });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    pick(container, fileOf("paper.pdf", "application/pdf"));
    await screen.findByText("paper page new-paper");
    expect(vi.mocked(api.uploadPaper).mock.calls[0]![1]).toEqual({
      engine: "decimer",
      ocsr: "off",
    });
  });

  it("offers the four engines, DECIMER first, and sends the chosen one", async () => {
    const { container } = renderHome();
    const select = screen.getByRole("combobox", { name: "Engine" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["DECIMER", "DECIMER hand-drawn", "MolNexTR", "MolScribe"]);
    expect(select).toHaveValue("decimer");
    fireEvent.change(select, { target: { value: "molscribe" } });
    pick(container, fileOf("paper.pdf", "application/pdf"));
    await screen.findByText("paper page new-paper");
    expect(vi.mocked(api.uploadPaper).mock.calls[0]![1]).toEqual({
      engine: "molscribe",
      ocsr: "auto",
    });
  });

  it.each([
    ["mol.png", "image/png"],
    ["mol.tiff", "image/tiff"],
    ["mol.webp", "image/webp"],
    ["mol.jpg", "image/jpeg"],
  ])("sends %s to the image upload and opens the image job", async (name, type) => {
    const { container } = renderHome();
    pick(container, fileOf(name, type));
    expect(await screen.findByText("image page new-image")).toBeInTheDocument();
    expect(api.uploadImage).toHaveBeenCalledWith(expect.any(File), "decimer");
    expect(api.uploadPaper).not.toHaveBeenCalled();
  });

  it("takes the type from the extension when the browser gives none", async () => {
    const { container } = renderHome();
    pick(container, fileOf("scan.TIF", ""));
    expect(await screen.findByText("image page new-image")).toBeInTheDocument();
  });

  it("shows the 429 detail and the wait from Retry-After", async () => {
    vi.mocked(api.uploadPaper).mockRejectedValue(new ApiError(429, "Too many active papers", 7));
    const { container } = renderHome();
    pick(container, fileOf("paper.pdf", "application/pdf"));
    expect(await screen.findByText("Too many active papers")).toBeInTheDocument();
    expect(screen.getByText("Try again in 7 s")).toBeInTheDocument();
  });

  it("the 429 alert is static (announced once); the countdown runs outside it and stops at zero", async () => {
    const clear = vi.spyOn(globalThis, "clearInterval");
    vi.mocked(api.uploadPaper).mockRejectedValue(new ApiError(429, "Too many active papers", 2));
    const { container } = renderHome();
    pick(container, fileOf("paper.pdf", "application/pdf"));
    const alert = (await screen.findByText("Too many active papers")).closest('[role="alert"]')!;
    await screen.findByText("Try again in 2 s");
    const said = alert.textContent;
    expect(said).toContain("Too many active papers");
    expect(said).toContain("Try again in 2 s"); // once, for screen readers
    const countdown = screen.getByText("Try again in 2 s");
    expect(alert).not.toContainElement(countdown);
    expect(countdown).toHaveAttribute("aria-hidden", "true");
    expect(await screen.findByText("Try again in 1 s", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(alert.textContent).toBe(said);
    const before = clear.mock.calls.length;
    await waitFor(() => expect(screen.queryByText(/^Try again in \d+ s$/)).toBeNull(), {
      timeout: 2500,
    });
    expect(clear.mock.calls.length).toBeGreaterThan(before); // the timer stopped at zero
    expect(alert.textContent).toBe(said);
  });

  it("shows a 429 without Retry-After without a wait", async () => {
    vi.mocked(api.uploadPaper).mockRejectedValue(new ApiError(429, "daily quota exceeded"));
    const { container } = renderHome();
    pick(container, fileOf("paper.pdf", "application/pdf"));
    expect(await screen.findByText("daily quota exceeded")).toBeInTheDocument();
    expect(screen.queryByText(/Try again in/)).toBeNull();
  });
});

function deferred() {
  let resolve!: (v: { papers: PaperSummary[] }) => void;
  const promise = new Promise<{ papers: PaperSummary[] }>((r) => (resolve = r));
  return { promise, resolve };
}

describe("One owner cookie on the first visit", () => {
  it("asks for the image jobs only after the papers list answered", async () => {
    const reply = deferred();
    renderHome({ papersReply: reply.promise });
    await new Promise((r) => setTimeout(r, 20));
    expect(api.listImages).not.toHaveBeenCalled();
    reply.resolve({ papers: [] });
    await waitFor(() => expect(api.listImages).toHaveBeenCalledTimes(1));
  });

  it("an upload made before the list answered waits for it", async () => {
    const reply = deferred();
    const { container } = renderHome({ papersReply: reply.promise });
    pick(container, fileOf("paper.pdf", "application/pdf"));
    await new Promise((r) => setTimeout(r, 20));
    expect(api.uploadPaper).not.toHaveBeenCalled();
    expect(api.listPapers).toHaveBeenCalledTimes(1); // it waits on the same request
    reply.resolve({ papers: [] });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
  });
});

describe("A PDF handed over by the landing's drop zone", () => {
  const at = (token: string) => ({ pathname: "/app", state: { handOff: token } });

  it("is taken once, uploaded with the default engine, and opens its paper", async () => {
    const file = fileOf("alkaloids.pdf", "application/pdf");
    renderHome({ at: at(handOff(file)) });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
    expect(api.uploadPaper).toHaveBeenCalledWith(file, { engine: "decimer", ocsr: "auto" });
    expect(api.uploadImage).not.toHaveBeenCalled();
  });

  it("a reload or Back with the same token uploads nothing again", async () => {
    const token = handOff(fileOf("alkaloids.pdf", "application/pdf"));
    const first = renderHome({ at: at(token) });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    first.unmount();
    renderHome({ at: at(token) }); // the same history entry, opened again
    await screen.findByText("No papers yet.");
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
    expect(document.querySelector(".drop__problem")).toBeNull();
  });

  it("a token with nothing behind it (reload, new tab) opens /app as usual", async () => {
    renderHome({ at: at("h-gone") });
    await screen.findByText("No papers yet.");
    expect(api.uploadPaper).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1, name: "Drop a PDF here" })).toBeInTheDocument();
    expect(document.querySelector(".drop__problem")).toBeNull();
  });

  it("waits for the papers list (the owner cookie) before it is sent", async () => {
    const reply = deferred();
    renderHome({ at: at(handOff(fileOf("a.pdf", "application/pdf"))), papersReply: reply.promise });
    expect(await screen.findByText("Uploading a.pdf…")).toBeInTheDocument();
    // fetch reports no upload progress: the indeterminate bar, no number
    expect(screen.getByRole("progressbar", { name: "Upload" })).not.toHaveAttribute("aria-valuenow");
    expect(api.uploadPaper).not.toHaveBeenCalled();
    reply.resolve({ papers: [] });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
  });

  it("shows the server's refusal in the tool's drop area", async () => {
    vi.mocked(api.uploadPaper).mockRejectedValue(new ApiError(400, "Not a readable PDF."));
    renderHome({ at: at(handOff(fileOf("x.pdf", "application/pdf"))) });
    expect(await screen.findByText("Not a readable PDF.")).toBeInTheDocument();
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
  });

  it("a File in the router state itself is not taken (only the in-memory hand-off is)", async () => {
    renderHome({ at: { pathname: "/app", state: { upload: fileOf("a.pdf", "application/pdf") } } });
    await screen.findByText("No papers yet.");
    expect(api.uploadPaper).not.toHaveBeenCalled();
  });
});

describe("The sample paper", () => {
  function stubSample() {
    const fetchMock = vi.fn(
      async () => new Response(new Blob(["%PDF-1.4"], { type: "application/pdf" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("?sample=1 fetches the sample and uploads it under its display name", async () => {
    const fetchMock = stubSample();
    renderHome({ at: "/app?sample=1" });
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/sample/synth_015.pdf", expect.anything());
    expect(api.uploadPaper).toHaveBeenCalledTimes(1);
    const [file, opts] = vi.mocked(api.uploadPaper).mock.calls[0]!;
    expect(file.name).toBe(SAMPLE_NAME);
    expect(file.type).toBe("application/pdf");
    expect(opts).toEqual({ engine: "decimer", ocsr: "auto" });
  });

  it("the button uploads the sample when it is not listed", async () => {
    stubSample();
    renderHome();
    fireEvent.click(await screen.findByRole("button", { name: "Try a sample paper" }));
    expect(await screen.findByText("paper page new-paper")).toBeInTheDocument();
    expect(vi.mocked(api.uploadPaper).mock.calls[0]![0].name).toBe(SAMPLE_NAME);
  });

  it("opens the listed sample instead of uploading it again", async () => {
    const fetchMock = stubSample();
    renderHome({
      papers: [paper({ id: "old-sample", display_name: SAMPLE_NAME, title: null })],
    });
    fireEvent.click(await screen.findByRole("button", { name: "Open the sample paper" }));
    expect(await screen.findByText("paper page old-sample")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(api.uploadPaper).not.toHaveBeenCalled();
  });

  it("?sample=1 opens the listed sample without an upload", async () => {
    const fetchMock = stubSample();
    renderHome({
      at: "/app?sample=1",
      papers: [paper({ id: "old-sample", display_name: SAMPLE_NAME, title: null })],
    });
    expect(await screen.findByText("paper page old-sample")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(api.uploadPaper).not.toHaveBeenCalled();
  });
});

describe("Papers list", () => {
  it("shows title, state, counts, expiry and Open", async () => {
    renderHome({ papers: [paper()] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    const r = within(row);
    expect(r.getByText("alkaloids.pdf")).toBeInTheDocument();
    expect(
      r.getByText("15 structures · 9 accepted · 3 to check · 2 rejected · 1 failed · 1 failed page"),
    ).toBeInTheDocument();
    expect(r.getByText("Done")).toBeInTheDocument();
    expect(r.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/app/papers/p1");
  });

  it("falls back to the display name and leaves out zero counts", async () => {
    renderHome({
      papers: [
        paper({
          title: null,
          status: "processing",
          structures: 1,
          accepted: 0,
          rejected: 0,
          to_review: 1,
          failed_pages: 0,
          failed: 0,
        }),
      ],
    });
    const row = (await screen.findByText("alkaloids.pdf")).closest("li")!;
    expect(within(row).getByText("1 structure · 1 to check")).toBeInTheDocument();
    expect(within(row).getByText("Reading…")).toBeInTheDocument();
  });

  it("says Annotating… for a paper busy only with its annotation", async () => {
    renderHome({ papers: [paper({ status: "processing", annotating: true })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    expect(within(row).getByText("Annotating…")).toBeInTheDocument();
    expect(within(row).queryByText("Reading…")).toBeNull();
  });

  it("a busy paper's row has a thin progress bar and its stage in a few words", async () => {
    const step = (over: Partial<StepOut>): StepOut => ({
      id: Math.random().toString(36),
      kind: "segment_page",
      page: 0,
      segment_id: null,
      status: "done",
      attempts: 1,
      error_class: null,
      engine: null,
      created_at: "2026-11-18T10:00:00.000000Z",
      started_at: null,
      finished_at: null,
      ...over,
    });
    vi.mocked(api.getSteps).mockResolvedValue({
      steps: [
        step({ kind: "check_pdf", page: null }),
        step({ page: 0 }),
        step({ page: 1 }),
        step({ page: 2, status: "running" }),
      ],
    });
    renderHome({ papers: [paper({ status: "processing", pages: 4 })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    const bar = await within(row).findByRole("progressbar", {
      name: "Progress of Alkaloids from Coffea leaves",
    });
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuetext", "Reading pages, 2 of 4, 22%"));
    expect(bar).toHaveAttribute("aria-valuenow", "22");
    expect(within(row).getByText("Reading pages 2/4")).toBeInTheDocument();
    expect(within(row).getByText("22%")).toBeInTheDocument();
    expect(api.getSteps).toHaveBeenCalledWith("p1", expect.anything());
    // no announcements from the list: a row's figure changes with every poll
    expect(within(row).queryByRole("status")).toBeNull();
  });

  it("a busy paper's row waits for its steps before it shows a bar (no 0/5 guess)", async () => {
    let answer!: (v: { steps: StepOut[] }) => void;
    vi.mocked(api.getSteps).mockReturnValue(new Promise((r) => (answer = r)));
    renderHome({ papers: [paper({ status: "processing", pages: 5 })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    await waitFor(() => expect(api.getSteps).toHaveBeenCalled());
    expect(within(row).queryByRole("progressbar")).toBeNull();
    answer({ steps: [] });
    expect(await within(row).findByRole("progressbar")).toBeInTheDocument();
  });

  it("a finished paper's row has no bar and asks for no steps", async () => {
    renderHome({ papers: [paper()] });
    await screen.findByText("Alkaloids from Coffea leaves");
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(api.getSteps).not.toHaveBeenCalled();
  });

  it("an annotating paper's row has an indeterminate bar and no second word", async () => {
    renderHome({ papers: [paper({ status: "processing", annotating: true })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    const bar = await within(row).findByRole("progressbar");
    expect(bar).not.toHaveAttribute("value");
    expect(within(row).getAllByText(/Annotating/)).toHaveLength(1);
  });

  it("says Not read yet for a finished paper uploaded with ocsr off", async () => {
    renderHome({ papers: [paper({ ocsr_mode: "off" })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    expect(within(row).getByText("Not read yet")).toBeInTheDocument();
  });

  it("says Failed for a failed paper", async () => {
    renderHome({ papers: [paper({ status: "failed" })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    expect(within(row).getByText("Failed")).toBeInTheDocument();
  });

  it("rounds the days to deletion up", async () => {
    renderHome({
      papers: [
        paper({ id: "a", title: "A", expires_at: new Date(Date.now() + 2.2 * DAY).toISOString() }),
        paper({ id: "b", title: "B", expires_at: new Date(Date.now() + 0.4 * DAY).toISOString() }),
        paper({ id: "c", title: "C", expires_at: new Date(Date.now() + 1.5 * DAY).toISOString() }),
      ],
    });
    const row = (title: string) => within(screen.getByText(title).closest("li")!);
    await screen.findByText("A");
    expect(row("A").getByText("Deleted in 3 days")).toBeInTheDocument();
    expect(row("B").getByText("Deleted today")).toBeInTheDocument();
    expect(row("C").getByText("Deleted in 2 days")).toBeInTheDocument();
  });

  it("asks before it deletes, and deletes only after the confirm", async () => {
    const del = vi.spyOn(api, "deletePaper").mockResolvedValue(undefined);
    renderHome({ papers: [paper()] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText("Delete this paper and its results? This cannot be undone."),
    ).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(del).not.toHaveBeenCalled();

    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("p1"));
  });

  it("a deleted paper leaves the list at once, even when the list refresh then fails", async () => {
    vi.spyOn(api, "deletePaper").mockResolvedValue(undefined);
    renderHome({ papers: [paper(), paper({ id: "p2", title: "Second paper" })] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    vi.mocked(api.listPapers).mockRejectedValue(new ApiError(503, "busy"));
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Alkaloids from Coffea leaves")).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Second paper")).toBeInTheDocument();
  });

  it("closes the confirm with Escape", async () => {
    const del = vi.spyOn(api, "deletePaper").mockResolvedValue(undefined);
    renderHome({ papers: [paper()] });
    const row = (await screen.findByText("Alkaloids from Coffea leaves")).closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(del).not.toHaveBeenCalled();
  });

  it("lists image jobs in their own list", async () => {
    renderHome({ papers: [paper()], images: [imageJob()] });
    const images = await screen.findByRole("list", { name: "Images" });
    expect(within(images).getByText("drawing.png")).toBeInTheDocument();
    expect(within(images).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/app/images/i1",
    );
  });

  it("empty: one line and the sample button", async () => {
    renderHome();
    expect(await screen.findByText("No papers yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try a sample paper" })).toHaveLength(1);
  });

  it("renders a hostile display name and title as text", async () => {
    const { container } = renderHome({
      papers: [
        paper({ id: "x1", title: XSS, display_name: "a.pdf" }),
        paper({ id: "x2", title: null, display_name: XSS }),
      ],
      images: [imageJob({ display_name: XSS })],
    });
    await screen.findByRole("list", { name: "Images" });
    expect(screen.getAllByText(XSS)).toHaveLength(3);
    expect(container.querySelector("img")).toBeNull();
  });
});
