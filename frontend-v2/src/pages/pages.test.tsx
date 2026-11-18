// Landing (Persuade mode, the Survey Sheet board) and the info pages: exact copy, honest
// example labels, the CTA links, an illustration with nothing focusable, the citation with
// its copy button, v2 privacy facts, and the route-template page views (never a real id).
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { routeTemplate, trackPage } from "../analytics";
import { pageMeta } from "./meta";

const CITATION =
  "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular " +
  "annotation and recognition for curating unravelled structures. Digital Discovery 2025, " +
  "4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const text = (el: Element | null) => (el?.textContent ?? "").replace(/\s+/g, " ").trim();

afterEach(() => {
  vi.restoreAllMocks();
  delete window._paq;
});

describe("Landing", () => {
  it("has one h1 with the exact headline, in sentence case in the DOM", () => {
    renderAt("/");
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]?.textContent).toBe("Every molecule has a source.");
  });

  it("says one sentence under the headline, then the mono facts line", () => {
    renderAt("/");
    expect(
      screen.getByText(
        "MARCUS finds every chemical structure in a PDF, reads it, and helps you check it " +
          "before it goes into COCONUT.",
        { selector: "p" },
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Open source (MIT) · No login · Files deleted after 30 days"),
    ).toBeInTheDocument();
  });

  it("Upload a PDF is orange glass to /app; Try a sample paper is clear glass to /app?sample=1", () => {
    renderAt("/");
    const upload = screen.getByRole("link", { name: /^Upload a PDF/ });
    expect(upload.tagName).toBe("A");
    expect(upload).toHaveClass("glass", "glass--orange");
    expect(upload).toHaveAttribute("href", "/app");
    const sample = screen.getByRole("link", { name: /^Try a sample paper/ });
    expect(sample).toHaveClass("glass", "glass--clear");
    expect(sample).toHaveAttribute("href", "/app?sample=1");
  });

  it("the hero is labelled as an example page, with both tags and a bbox line for each", () => {
    renderAt("/");
    const hero = screen.getByRole("region", { name: "Example: a page read by MARCUS" });
    expect(hero.textContent).toContain("Sheet 01 · Example page · 300 DPI");
    expect(within(hero).getByText("[01] Structure")).toBeInTheDocument();
    expect(within(hero).getByText("[02] Reading…")).toBeInTheDocument();
    expect(
      within(hero).getByText((_, el) => text(el) === "BBox [01] X0 967 · Y0 671 · X1 1513 · Y1 1120 px" && el?.children.length === 0),
    ).toBeInTheDocument();
    expect(
      within(hero).getByText((_, el) => text(el) === "BBox [02] X0 1410 · Y0 2010 · X1 2190 · Y1 2400 px" && el?.children.length === 0),
    ).toBeInTheDocument();
  });

  it("the hero shows the steps of the sample paper with a word for each state", () => {
    renderAt("/");
    const hero = screen.getByRole("region", { name: "Example: a page read by MARCUS" });
    const steps = within(hero).getAllByRole("listitem").map((li) => text(li));
    expect(steps).toEqual([
      "Done: 001 Check PDF",
      "Done: 002 Render 5 pages",
      "Done: 003 Find structures · 15",
      "Running: 004 Reading with DECIMER · 9 / 15",
      "Not started: 005 Look up DOI",
    ]);
  });

  it("the three cards carry [01], [02], [03] and live under #how", () => {
    const { container } = renderAt("/");
    const how = container.querySelector("section#how");
    expect(how).toHaveAttribute("aria-label", "What MARCUS does");
    const h2s = within(how as HTMLElement).getAllByRole("heading", { level: 2 });
    expect(h2s.map((h) => h.textContent)).toEqual([
      "Every structure on every page",
      "Three engines, side by side",
      "Checked, then into COCONUT",
    ]);
    for (const tag of ["[01]", "[02]", "[03]"]) {
      expect(within(how as HTMLElement).getByText(tag)).toBeInTheDocument();
    }
  });

  it("the review preview is an example with nothing focusable in it", () => {
    renderAt("/");
    const preview = screen.getByRole("region", { name: "Example: the review grid" });
    expect(preview.textContent).toContain("Example paper");
    expect(preview.textContent).toContain("Send 9 to COCONUT");
    expect(preview.querySelectorAll("button, a, [tabindex], input, select, textarea")).toHaveLength(0);
  });

  it("the cite section shows the exact citation and copies it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const { container } = renderAt("/");
    const cite = container.querySelector("section#cite") as HTMLElement;
    expect(cite).not.toBeNull();
    expect(within(cite).getByText((_, el) => el?.tagName === "P" && text(el) === CITATION)).toBeInTheDocument();
    const copy = within(cite).getByRole("button", { name: /Copy/ });
    expect(copy).toHaveClass("glass", "glass--clear", "glass--sm");
    await act(async () => {
      fireEvent.click(copy);
    });
    expect(writeText).toHaveBeenCalledWith(CITATION);
    expect(screen.getByText("Citation copied")).toBeInTheDocument();
  });
});

describe("pre-rendered pages", () => {
  it("no page source uses dangerouslySetInnerHTML", () => {
    const dir = resolve(process.cwd(), "src/pages");
    for (const name of readdirSync(dir).filter((n) => n.endsWith(".tsx") && !n.endsWith(".test.tsx"))) {
      expect(readFileSync(resolve(dir, name), "utf8"), name).not.toContain("dangerouslySetInnerHTML");
    }
  });

  it("Privacy says 30 days and Matomo, and nothing about OpenAI", () => {
    const { container } = renderAt("/privacy");
    expect(screen.getByRole("heading", { level: 1, name: "Privacy" })).toBeInTheDocument();
    expect(container.textContent).toContain("30 days");
    expect(container.textContent).toContain("Matomo");
    expect(container.textContent).not.toMatch(/OpenAI/i);
    // the one outside lookup: the paper's DOI, and nothing else, at Crossref or DataCite
    expect(container.textContent).toContain(
      "To show the paper's title, the server looks up its DOI at Crossref or DataCite; only the DOI is sent.",
    );
  });

  it("About and Disclaimer carry v2 facts and nothing about OpenAI", () => {
    for (const path of ["/about", "/disclaimer"]) {
      const { container, unmount } = renderAt(path);
      expect(container.textContent, path).not.toMatch(/OpenAI/i);
      unmount();
    }
    const { container } = renderAt("/disclaimer");
    expect(container.textContent).toContain("30 days");
  });

  it("NotFound says the page does not exist and links home", () => {
    renderAt("/no-such-page");
    expect(screen.getByText("This page does not exist.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the start page" })).toHaveAttribute("href", "/");
  });

  it("each pre-rendered page has its own title", () => {
    const titles = ["/", "/about", "/privacy", "/disclaimer", "/__marcus_not_found__"].map(
      (url) => pageMeta(url).title,
    );
    expect(new Set(titles).size).toBe(titles.length);
    expect(pageMeta("/").title).toBe("MARCUS · Every molecule has a source");
    expect(pageMeta("/privacy").title).toBe("Privacy · MARCUS");
  });

  it("client navigation sets the page title", () => {
    renderAt("/about");
    expect(document.title).toBe("About · MARCUS");
  });
});

describe("analytics", () => {
  it("trackPage on /app/papers/123 pushes the route template, never the id", () => {
    window._paq = [];
    trackPage("/app/papers/123");
    expect(window._paq).toEqual([
      ["setCustomUrl", "/app/papers/:id"],
      ["setDocumentTitle", "/app/papers/:id"],
      ["trackPageView"],
    ]);
    expect(JSON.stringify(window._paq)).not.toContain("123");
  });

  it.each([
    ["/", "/"],
    ["/about", "/about"],
    ["/about/", "/about"],
    ["/privacy", "/privacy"],
    ["/disclaimer", "/disclaimer"],
    ["/app", "/app"],
    ["/app/papers/3f2a", "/app/papers/:id"],
    ["/app/images/9c1b", "/app/images/:id"],
    ["/app/papers/3f2a/extra", "/not-found"],
    ["/anything-else", "/not-found"],
  ])("routeTemplate(%s) = %s", (path, template) => {
    expect(routeTemplate(path)).toBe(template);
  });

  it("is a no-op when the tracker is absent", () => {
    expect(() => trackPage("/app")).not.toThrow();
    expect(window._paq).toBeUndefined();
  });

  it("App sends one page view per route, with the template", () => {
    window._paq = [];
    renderAt("/app/images/abc-123");
    expect(window._paq).toContainEqual(["setCustomUrl", "/app/images/:id"]);
    expect((window._paq as unknown[][]).filter((c) => c[0] === "trackPageView")).toHaveLength(1);
    expect(JSON.stringify(window._paq)).not.toContain("abc-123");
  });
});
