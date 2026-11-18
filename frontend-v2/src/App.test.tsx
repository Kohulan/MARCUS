import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api/client";

const realInnerWidth = window.innerWidth;

function setWidth(px: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: px });
}

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
    expect(document.title).toBe("Papers · MARCUS");
  });

  it.each([
    ["/app/papers/p1", "Paper · MARCUS"],
    ["/app/images/i1", "Image · MARCUS"],
  ])("%s sets its own title", async (path, title) => {
    renderAt(path);
    await screen.findByRole("heading", { level: 1 });
    expect(document.title).toBe(title);
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
