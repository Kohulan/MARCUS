import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api/client";

const realInnerWidth = window.innerWidth;

function setWidth(px: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: px });
}

// The routes' lazy chunks, loaded once before any test: under a full-suite run the first
// dynamic import (transform included) could take longer than a findBy's 1 s, so the first
// lazy route timed out about one run in five. With the modules cached, React.lazy resolves
// at once and each test measures its own page, not the transform.
beforeAll(async () => {
  await Promise.all([
    import("./tool/ToolHome"),
    import("./workspace/Workspace"),
    import("./images/ImageResult"),
    import("./api/QueryProvider"),
  ]);
}, 60_000);

beforeEach(() => {
  vi.spyOn(api, "listPapers").mockResolvedValue({ papers: [] });
  vi.spyOn(api, "listImages").mockResolvedValue({ jobs: [] });
});

afterEach(() => {
  setWidth(realInnerWidth);
  delete window._paq;
  vi.restoreAllMocks();
});

function renderAt(path: string | { pathname: string; search?: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routes", () => {
  it("renders the landing headline at /", () => {
    renderAt("/");
    expect(
      screen.getByRole("heading", { level: 1, name: "Every molecule has a source." }),
    ).toBeInTheDocument();
  });

  it("loads the lazy tool home at /app and gives it its own title", async () => {
    document.title = "MARCUS · Every molecule has a source";
    renderAt("/app");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Drop a PDF here" }),
    ).toBeInTheDocument();
    // the title is set in an effect, which may run just after the heading is found
    await waitFor(() => expect(document.title).toBe("Papers · MARCUS"));
  });

  it("/app/images/i1 sets its own title", async () => {
    renderAt("/app/images/i1");
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(document.title).toBe("Image · MARCUS"));
  });

  it("/app/papers/:id is titled with the paper's title (or its file name)", async () => {
    vi.spyOn(api, "getPaper").mockResolvedValue({
      id: "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f",
      display_name: "alkaloids.pdf",
      status: "done",
      pages: 1,
      doi: null,
      title: null,
      engine: "decimer",
      ocsr_mode: "auto",
      created_at: "2026-11-18T10:00:00Z",
      expires_at: "2026-12-18T10:00:00Z",
      structures: 0,
      accepted: 0,
      rejected: 0,
      to_review: 0,
      failed_pages: 0,
      counts: { steps_by_status: {} },
      segments: [],
    });
    vi.spyOn(api, "getSteps").mockResolvedValue({ steps: [] });
    renderAt("/app/papers/3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f");
    await screen.findByRole("heading", { level: 1, name: "alkaloids.pdf" });
    await waitFor(() => expect(document.title).toBe("alkaloids.pdf · MARCUS"));
  });

  it("below 1024 px /app shows the desktop note and never asks the API", async () => {
    setWidth(800);
    renderAt("/app");
    expect(screen.getByText("MARCUS is made for a desktop screen")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("heading", { name: "Drop a PDF here" })).toBeNull();
    expect(api.listPapers).not.toHaveBeenCalled();
  });

  it("the landing's Upload a PDF opens the picker once and counts one page view", async () => {
    window._paq = [];
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    renderAt({ pathname: "/app", state: { openPicker: true } });
    await screen.findByRole("heading", { level: 1, name: "Drop a PDF here" });
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    const views = (window._paq as unknown[][]).filter((c) => c[0] === "trackPageView");
    expect(views).toHaveLength(1);
  });

  it("frames every page with the header, the footer and the one glass filter", () => {
    const { container } = renderAt("/about");
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(container.querySelectorAll("#marcus-glass")).toHaveLength(1);
    expect(container.querySelector(".frame > .sheet")).not.toBeNull();
  });

  it("renders the not-found page for an unknown path", () => {
    renderAt("/no-such-page");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});

describe("scroll on navigation", () => {
  it("a forward navigation opens the next page at its top", () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    renderAt("/");
    expect(scrollTo).not.toHaveBeenCalled(); // the first load is the browser's
    fireEvent.click(within(screen.getByRole("contentinfo")).getByRole("link", { name: "Privacy" }));
    expect(screen.getByRole("heading", { level: 1, name: "Privacy" })).toBeInTheDocument();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    vi.unstubAllGlobals();
  });

  it("a link with a hash scrolls to its target", () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    const into = vi.fn();
    Element.prototype.scrollIntoView = into;
    renderAt("/disclaimer");
    fireEvent.click(screen.getByRole("link", { name: "How to cite" }));
    expect(into).toHaveBeenCalledTimes(1);
    expect((into.mock.contexts[0] as Element).id).toBe("cite");
    expect(scrollTo).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("a malformed hash does not crash: the page opens at its top", () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    function Go() {
      const navigate = useNavigate();
      return (
        <button type="button" onClick={() => navigate("/about#%E0%A4%A")}>
          go
        </button>
      );
    }
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
        <Go />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    expect(screen.queryByRole("heading", { level: 1, name: "Every molecule has a source." })).toBeNull();
    vi.unstubAllGlobals();
  });
});
