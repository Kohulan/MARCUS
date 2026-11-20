// Landing and the info pages: the acrostic h1, the ring drop zone and its hand-over to the
// tool, the sample pill; About with what moved there (honest example labels, an illustration
// with nothing focusable, the citation with its copy button); v2 privacy facts, and the
// route-template page views (never a real id).
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { routeTemplate, trackPage } from "../analytics";
import { takeHandOff } from "../tool/files";
import Landing from "./Landing";
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

const HEADLINE = "Molecular Annotation and Recognition for Curating Unravelled Structures";
const MB = 1024 * 1024;

function pdf(name: string, size = 1024, type = "application/pdf"): File {
  const file = new File(["%PDF"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

/** Where /app was opened, and what the hand-off held (taken here, as the tool does). */
function AppProbe() {
  const location = useLocation();
  const [file] = useState(() => takeHandOff((location.state as { handOff?: unknown } | null)?.handOff));
  return <p>tool opened with {file ? file.name : "nothing"}</p>;
}

function renderLanding() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<AppProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Landing", () => {
  it("has one h1: the name spelled out, read as the plain name", () => {
    renderAt("/");
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    const h1 = h1s[0]!;
    expect(h1).toHaveAccessibleName(HEADLINE);
    expect(h1.querySelector(".visually-hidden")?.textContent).toBe(HEADLINE);
    // the drawn acrostic: bold initials, and/for set apart, one word a line
    const drawn = h1.querySelector('[aria-hidden="true"]')!;
    expect([...drawn.querySelectorAll("b")].map((b) => b.textContent).join("")).toBe("MARCUS");
    expect([...drawn.querySelectorAll(".acro__line")].map((l) => text(l))).toEqual([
      "Molecular",
      "Annotation and",
      "Recognition for",
      "Curating",
      "Unravelled",
      "Structures",
    ]);
    expect([...drawn.querySelectorAll(".acro__link")].map((s) => s.textContent)).toEqual([
      "and",
      "for",
    ]);
  });

  it("says one sentence under the name, then the mono facts line", () => {
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

  it("everything else moved to About: no steps, review grid or citation here", () => {
    const { container } = renderAt("/");
    const main = screen.getByRole("main");
    expect(main.querySelector("#how, #cite, .preview, .hero")).toBeNull();
    expect(main.querySelectorAll("h2")).toHaveLength(0);
    expect(container.textContent).not.toContain("Every molecule has a source");
    expect(container.querySelector('a[href^="/#"]')).toBeNull();
  });

  it("Try a sample paper is the orange glass pill to /app?sample=1", () => {
    renderAt("/");
    const sample = screen.getByRole("link", { name: /^Try a sample paper/ });
    expect(sample).toHaveClass("glass", "glass--orange");
    expect(sample).toHaveAttribute("href", "/app?sample=1");
    expect(screen.queryByRole("link", { name: /Upload a PDF/ })).toBeNull();
  });

  it("the drop zone is one button: the ring, the words, the limit; the beams are decoration", () => {
    const { container } = renderAt("/");
    const zone = screen.getByRole("button", { name: /Drop a PDF here or browse/ });
    expect(zone).toHaveClass("dz");
    expect(text(zone)).toBe(
      "Drop a PDF here or browse Desktop screen needed PDF up to 20 MB",
    );
    expect(zone.querySelector("svg.dz__ring")).toHaveAttribute("aria-hidden", "true");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).toHaveAttribute("accept", "application/pdf,.pdf");
    expect(input).toHaveAttribute("tabindex", "-1");
    expect(container.querySelector("canvas.beams")).toHaveAttribute("aria-hidden", "true");
  });

  it("Enter, Space or a click on the zone opens the file picker", () => {
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    renderAt("/");
    fireEvent.click(screen.getByRole("button", { name: /Drop a PDF here/ }));
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("a PDF picked there goes to the tool, which uploads it", async () => {
    const { container } = renderLanding();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [pdf("alkaloids.pdf")] } });
    const zone = container.querySelector(".dz");
    expect(zone).toHaveClass("is-done");
    expect(zone).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Uploading alkaloids.pdf…");
    expect(await screen.findByText("tool opened with alkaloids.pdf")).toBeInTheDocument();
  });

  it("a PDF dropped on the ring goes to the tool; drag-over turns it orange first", async () => {
    const { container } = renderLanding();
    const zone = container.querySelector(".dz")!;
    fireEvent.dragEnter(zone, { dataTransfer: { types: ["Files"], files: [] } });
    expect(zone).toHaveClass("is-drag");
    fireEvent.dragLeave(zone, { relatedTarget: document.body });
    expect(zone).not.toHaveClass("is-drag");
    fireEvent.dragOver(zone, { dataTransfer: { types: ["Files"], files: [] } });
    fireEvent.drop(zone, { dataTransfer: { types: ["Files"], files: [pdf("paper.pdf")] } });
    expect(await screen.findByText("tool opened with paper.pdf")).toBeInTheDocument();
  });

  it.each([
    ["a picture", pdf("figure.png", 1024, "image/png"), "That file is not a PDF"],
    ["a PDF over 20 MB", pdf("big.pdf", 21 * MB), "That PDF is larger than 20 MB"],
  ])("refuses %s in the browser and strikes the ring through", async (_what, file, said) => {
    const { container } = renderLanding();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [file] } });
    const zone = container.querySelector(".dz");
    expect(zone).toHaveClass("is-error");
    expect(screen.getByRole("alert")).toHaveTextContent(said);
    expect(zone?.querySelector(".dz__title--said")).toHaveTextContent(said);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/tool opened/)).toBeNull();
  });

  it("the same refusal twice is announced twice (new text in the alert)", () => {
    const { container } = renderLanding();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [pdf("a.png", 1024, "image/png")] } });
    const first = screen.getByRole("alert").firstElementChild;
    fireEvent.change(input, { target: { files: [pdf("b.png", 1024, "image/png")] } });
    const second = screen.getByRole("alert").firstElementChild;
    expect(second).toHaveTextContent("That file is not a PDF");
    expect(second).not.toBe(first);
  });

  it("of several dropped files, the first PDF goes to the tool", async () => {
    const { container } = renderLanding();
    const zone = container.querySelector(".dz")!;
    const files = [pdf("fig.png", 1024, "image/png"), pdf("paper.pdf"), pdf("other.pdf")];
    fireEvent.drop(zone, { dataTransfer: { types: ["Files"], files } });
    expect(await screen.findByText("tool opened with paper.pdf")).toBeInTheDocument();
  });

  it("dragging text or a link over the ring does not light it", () => {
    const { container } = renderLanding();
    const zone = container.querySelector(".dz")!;
    fireEvent.dragEnter(zone, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(zone).not.toHaveClass("is-drag");
  });
});

describe("About", () => {
  it("What it does says it once, and the PI line names the university only once", () => {
    const { container } = renderAt("/about");
    expect(
      screen.getByText(
        "MARCUS turns a journal article into checked chemical structures for COCONUT, the " +
          "open natural products database.",
      ),
    ).toBeInTheDocument();
    const pi = screen.getByText(/^Principal investigator/);
    expect(text(pi)).toBe(
      "Principal investigator. Professor of Analytical Chemistry, Cheminformatics and Chemometrics",
    );
    expect(container.querySelector(".info__body")?.textContent?.match(/Friedrich Schiller/g)).toHaveLength(1);
  });

  it("the sections run in order, each with its anchor where other pages link", () => {
    const { container } = renderAt("/about");
    const h2s = [...container.querySelectorAll(".info__body h2")].map((h) => text(h));
    expect(h2s).toEqual([
      "What it does",
      "How it works",
      "Example: the review grid",
      "Team",
      "Open source",
      "Cite",
      "Publications",
    ]);
    for (const id of ["how", "review", "cite"]) expect(container.querySelector(`section#${id}`)).not.toBeNull();
    expect(container.textContent).not.toContain("Mockup note");
  });

  it("How it works: the three steps with [nn] tags, the real crop, the sample paper's run", () => {
    const { container } = renderAt("/about");
    const how = container.querySelector("section#how") as HTMLElement;
    const h3s = within(how).getAllByRole("heading", { level: 3 });
    expect(h3s.map((h) => text(h))).toEqual([
      "Every structure on every page",
      "Four engines, side by side",
      "Checked, then into COCONUT",
    ]);
    expect([...how.querySelectorAll(".steps3__tag")].map((t) => t.textContent)).toEqual([
      "[01]",
      "[02]",
      "[03]",
    ]);
    expect(how.textContent).toContain("MolNexTR, MolScribe and DECIMER hand-drawn");
    const crop = within(how).getByRole("img", {
      name: "Example: a structure drawing that DECIMER Segmentation cut from page 1 of the sample paper",
    });
    expect(crop.getAttribute("src")).toMatch(/example-crop/);
    const steps = [...how.querySelectorAll(".runlog li")].map((li) => text(li));
    expect(steps).toEqual([
      "Done: 001 Check PDF",
      "Done: 002 Render 5 pages",
      "Done: 003 Find structures · 15",
      "Running: 004 Reading with DECIMER · 9 / 15",
      "Not started: 005 Look up DOI",
    ]);
  });

  it("the review grid is an example with nothing focusable in it, as the tool shows it", () => {
    const { container } = renderAt("/about");
    const preview = container.querySelector("section#review .preview") as HTMLElement;
    expect(preview.textContent).toContain("Example paper");
    expect(preview.textContent).toContain("Send 9 to COCONUT");
    expect(within(preview).getByText("Engines differ")).toBeInTheDocument();
    expect(preview.querySelectorAll(".pcard kbd")).toHaveLength(0);
    expect(preview.querySelector(".preview__foot")?.textContent).toContain("Keys in focus mode");
    expect(preview.querySelectorAll("button, a, [tabindex], input, select, textarea")).toHaveLength(0);
  });

  it("Cite shows the exact citation and copies it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const { container } = renderAt("/about");
    const cite = container.querySelector("section#cite") as HTMLElement;
    expect(within(cite).getByText((_, el) => el?.tagName === "P" && text(el) === CITATION)).toBeInTheDocument();
    const copy = within(cite).getByRole("button", { name: "Copy citation" });
    expect(copy).toHaveClass("glass", "glass--clear", "glass--sm");
    await act(async () => {
      fireEvent.click(copy);
    });
    expect(writeText).toHaveBeenCalledWith(CITATION);
    expect(screen.getByText("Citation copied")).toBeInTheDocument();
  });

  it("Publications leave out the MARCUS paper: it is under Cite", () => {
    const { container } = renderAt("/about");
    const pubs = [...container.querySelectorAll(".refs li")].map((li) => text(li));
    expect(pubs).toHaveLength(7);
    expect(pubs.some((p) => p.includes("10.1039/d5dd00313j"))).toBe(false);
  });

  it("the Disclaimer's How to cite goes to About's Cite, and it credits the icons", () => {
    const { container } = renderAt("/disclaimer");
    expect(screen.getByRole("link", { name: "How to cite" })).toHaveAttribute("href", "/about#cite");
    expect(container.textContent).toContain("Font Awesome Free 6.7.2");
    expect(screen.getByRole("link", { name: "CC BY 4.0" })).toHaveAttribute(
      "href",
      "https://fontawesome.com/license/free",
    );
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
    // the IP recorded with a new key is not kept for good
    expect(container.textContent).toContain("This IP address is deleted after 30 days.");
    expect(container.textContent).toContain(
      "The address is also kept with a paper while it is being processed",
    );
    // the annotation is stored like the rest of the paper
    expect(container.textContent).toContain("the annotation and your corrections to it");
    // the annotation model runs on MARCUS's own server: no paper text leaves it
    expect(container.textContent).toContain(
      "Annotate runs a model on MARCUS's own server; no paper text leaves it.",
    );
    // R-F22: the one request the browser makes to COCONUT without a click
    expect(container.textContent).toContain(
      "Opening a paper with a DOI asks COCONUT how many structures it already has for that DOI.",
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
    expect(pageMeta("/").title).toBe(`MARCUS · ${HEADLINE}`);
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
