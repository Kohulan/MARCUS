// Survey Sheet parts (spec §7 state table, Global Constraints): exact state words and
// shapes, the stamp, numbered tags, the drawing, SMILES copy, the desktop note, and that
// every part a pre-rendered page uses renders on the server without touching window and
// without a style attribute (CSP style-src 'self').
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type ReactElement } from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DesktopOnly from "./DesktopOnly";
import Footer from "./Footer";
import { GlassButton, GlassLink } from "./GlassButton";
import GlassFilter from "./GlassFilter";
import Header from "./Header";
import Kbd from "./Kbd";
import Smiles from "./Smiles";
import SpecimenLabel from "./SpecimenLabel";
import Stamp from "./Stamp";
import StateBadge from "./StateBadge";
import Structure from "./Structure";
import { structureTag } from "./tag";
import { ToastHost, ToastProvider, useToast } from "./Toasts";

const realMatchMedia = window.matchMedia;
const realInnerWidth = window.innerWidth;

function mockReducedMotion(reduce: boolean) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion: reduce"),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  })) as unknown as typeof window.matchMedia;
}

function setWidth(px: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: px });
}

afterEach(() => {
  window.matchMedia = realMatchMedia;
  setWidth(realInnerWidth);
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("StateBadge: the exact word and its shape", () => {
  it("To check is an orange badge", () => {
    const { container } = render(<StateBadge state="to-check" />);
    expect(container.textContent).toBe("To check");
    expect(container.querySelector(".badge--orange")).not.toBeNull();
  });

  it("Failed is a charcoal tag", () => {
    const { container } = render(<StateBadge state="failed" />);
    expect(container.textContent).toBe("Failed");
    expect(container.querySelector(".tag--charcoal")).not.toBeNull();
  });

  it("Rejected carries the ✕", () => {
    const { container } = render(<StateBadge state="rejected" />);
    expect(container.textContent).toContain("✕");
    expect(container.textContent).toContain("Rejected");
  });

  it("Reading… is a dashed badge", () => {
    const { container } = render(<StateBadge state="reading" />);
    expect(container.textContent).toBe("Reading…");
    expect(container.querySelector(".badge--dashed")).not.toBeNull();
  });

  it("Not read yet carries the hollow square", () => {
    const { container } = render(<StateBadge state="not-read" />);
    expect(container.textContent).toContain("□");
    expect(container.textContent).toContain("Not read yet");
  });

  it("Accepted is the green word", () => {
    const { container } = render(<StateBadge state="accepted" />);
    expect(container.textContent).toBe("Accepted");
    expect(container.querySelector(".state--accepted")).not.toBeNull();
  });
});

describe("Stamp", () => {
  it("is labelled Accepted or Rejected; the rejected stamp is charcoal", () => {
    render(
      <>
        <Stamp state="accepted" />
        <Stamp state="rejected" />
      </>,
    );
    const accepted = screen.getByRole("img", { name: "Accepted" });
    const rejected = screen.getByRole("img", { name: "Rejected" });
    expect(accepted).not.toHaveClass("stamp--charcoal");
    expect(rejected).toHaveClass("stamp--charcoal");
  });

  it("lands (stamp--landing) when animated and reduced motion is off", () => {
    mockReducedMotion(false);
    render(<Stamp state="accepted" animate />);
    expect(screen.getByRole("img", { name: "Accepted" })).toHaveClass("stamp--landing");
  });

  it("does not move when reduced motion is on", () => {
    mockReducedMotion(true);
    render(<Stamp state="accepted" animate />);
    expect(screen.getByRole("img", { name: "Accepted" })).not.toHaveClass("stamp--landing");
  });

  it("does not move without animate", () => {
    mockReducedMotion(false);
    render(<Stamp state="rejected" />);
    expect(screen.getByRole("img", { name: "Rejected" })).not.toHaveClass("stamp--landing");
  });
});

describe("structureTag", () => {
  it.each([
    [1, "[01]"],
    [12, "[12]"],
    [100, "[100]"],
  ])("%i → %s", (n, tag) => {
    expect(structureTag(n)).toBe(tag);
  });
});

describe("Structure", () => {
  it("is a plain <img> with the given src, never an inline svg", () => {
    const { container } = render(<Structure src="blob:http://x/1" alt="Structure [01]" />);
    const img = screen.getByRole("img", { name: "Structure [01]" });
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", "blob:http://x/1");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("decoding", "async");
    expect(container.querySelector("svg")).toBeNull();
  });

  it("crossed adds the strike line", () => {
    const { container } = render(<Structure src="blob:http://x/1" alt="x" crossed />);
    expect(container.querySelector(".strike")).not.toBeNull();
  });

  it("shows a quiet placeholder while src is null", () => {
    const { container } = render(<Structure src={null} alt="x" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(container.textContent).not.toContain("No drawing");
  });

  it('shows "No drawing" when the drawing failed', () => {
    render(<Structure src={null} alt="x" failed />);
    expect(screen.getByText("No drawing")).toBeInTheDocument();
  });

  it('shows "No drawing" when the image does not load', () => {
    const { container } = render(<Structure src="blob:http://x/bad" alt="x" />);
    fireEvent.error(container.querySelector("img")!);
    expect(screen.getByText("No drawing")).toBeInTheDocument();
  });
});

describe("Smiles", () => {
  it("copies the exact value and says so", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const value = "Cn1cnc2c1c(=O)n(C)c(=O)n2C";
    render(
      <ToastProvider>
        <Smiles value={value} />
        <ToastHost />
      </ToastProvider>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy SMILES" }));
    });
    expect(writeText).toHaveBeenCalledWith(value);
    expect(screen.getByText("SMILES copied")).toBeInTheDocument();
  });

  it("struck strikes the value through", () => {
    const { container } = render(<Smiles value="C1=Cc2ccccc2OC1" struck />);
    expect(container.querySelector(".smiles--struck")).not.toBeNull();
  });

  it("shows an error toast when the clipboard refuses", async () => {
    const writeText = vi.fn(() => Promise.reject(new Error("denied")));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(
      <ToastProvider>
        <Smiles value="CCO" />
        <ToastHost />
      </ToastProvider>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy SMILES" }));
    });
    expect(screen.getByText("Could not copy")).toBeInTheDocument();
  });
});

describe("toasts", () => {
  function Push({ msg, tone }: { msg: string; tone?: "info" | "error" }) {
    const toast = useToast();
    return (
      <button type="button" onClick={() => toast(msg, tone)}>
        push
      </button>
    );
  }

  it("show a message and go away after a few seconds", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Push msg="Paper deleted" />
        <ToastHost />
      </ToastProvider>,
    );
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    fireEvent.click(screen.getByRole("button", { name: "push" }));
    expect(screen.getByRole("status")).toHaveTextContent("Paper deleted");
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("an error toast is marked as an error", () => {
    render(
      <ToastProvider>
        <Push msg="Upload failed" tone="error" />
        <ToastHost />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "push" }));
    expect(screen.getByText("Upload failed").closest(".toast")).toHaveClass("toast--error");
  });

  it("an error toast is announced assertively, an info toast politely", () => {
    render(
      <ToastProvider>
        <Push msg="Upload failed" tone="error" />
        <Push msg="Paper deleted" />
        <ToastHost />
      </ToastProvider>,
    );
    const [error, info] = screen.getAllByRole("button", { name: "push" });
    fireEvent.click(error!);
    fireEvent.click(info!);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("aria-live", "assertive");
    expect(alert).toHaveTextContent("Upload failed");
    expect(alert).not.toHaveTextContent("Paper deleted");
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Paper deleted");
    expect(status).not.toHaveTextContent("Upload failed");
  });

  it("useToast outside a provider does nothing and does not throw", () => {
    render(<Push msg="x" />);
    expect(() => fireEvent.click(screen.getByRole("button", { name: "push" }))).not.toThrow();
  });
});

describe("DesktopOnly", () => {
  it("shows the exact note below 1024 px", () => {
    setWidth(800);
    render(
      <DesktopOnly>
        <p>tool</p>
      </DesktopOnly>,
    );
    expect(screen.getByText("MARCUS is made for a desktop screen")).toBeInTheDocument();
    expect(screen.queryByText("tool")).toBeNull();
  });

  it("never mounts the tool below 1024 px, not even for one frame", () => {
    setWidth(800);
    const mounted = vi.fn();
    function Tool() {
      useEffect(() => mounted(), []);
      return <p>tool</p>;
    }
    render(
      <DesktopOnly>
        <Tool />
      </DesktopOnly>,
    );
    expect(mounted).not.toHaveBeenCalled();
  });

  it("follows the (min-width: 1024px) media query when the browser has one", () => {
    const listeners = new Set<() => void>();
    let wide = false;
    window.matchMedia = vi.fn((query: string) => ({
      get matches() {
        return query === "(min-width: 1024px)" ? wide : false;
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })) as unknown as typeof window.matchMedia;
    setWidth(1400); // the query wins over innerWidth
    render(
      <DesktopOnly>
        <p>tool</p>
      </DesktopOnly>,
    );
    expect(screen.queryByText("tool")).toBeNull();
    act(() => {
      wide = true;
      for (const fn of listeners) fn();
    });
    expect(screen.getByText("tool")).toBeInTheDocument();
  });

  it("shows the tool at 1024 px and follows a resize", () => {
    setWidth(1024);
    render(
      <DesktopOnly>
        <p>tool</p>
      </DesktopOnly>,
    );
    expect(screen.getByText("tool")).toBeInTheDocument();
    act(() => {
      setWidth(900);
      window.dispatchEvent(new Event("resize"));
    });
    expect(screen.getByText("MARCUS is made for a desktop screen")).toBeInTheDocument();
  });
});

describe("Kbd", () => {
  it("is a <kbd>", () => {
    const { container } = render(<Kbd>A</Kbd>);
    expect(container.querySelector("kbd.kbd")?.textContent).toBe("A");
  });
});

describe("Header and Footer", () => {
  it("header has the wordmark, the nav and the way into the tool", () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "MARCUS" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/#how");
    expect(screen.getByRole("link", { name: "Cite" })).toHaveAttribute("href", "/#cite");
    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/Kohulan/MARCUS",
    );
    expect(screen.getByRole("link", { name: "Open the tool" })).toHaveAttribute("href", "/app");
  });

  it("footer has the line, the citation and the links", () => {
    const { container } = render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>,
    );
    expect(container.textContent).toContain(
      "MARCUS · Friedrich Schiller University Jena · NFDI4Chem",
    );
    expect(container.textContent).toContain("Digital Discovery 2025 · DOI 10.1039/d5dd00313j");
    const href = (name: string) => screen.getByRole("link", { name }).getAttribute("href");
    expect(href("About")).toBe("/about");
    expect(href("Privacy")).toBe("/privacy");
    expect(href("Disclaimer")).toBe("/disclaimer");
    expect(href("DECIMER")).toBe("https://decimer.ai");
    expect(href("COCONUT")).toBe("https://coconut.naturalproducts.net");
    expect(href("GitHub")).toBe("https://github.com/Kohulan/MARCUS");
  });
});

describe("server rendering of the pre-rendered parts", () => {
  const spies: { mock: { calls: unknown[] } }[] = [];

  beforeEach(() => {
    mockReducedMotion(false);
    spies.length = 0;
    spies.push(vi.spyOn(window, "matchMedia"));
    for (const prop of ["innerWidth", "innerHeight", "localStorage", "sessionStorage"] as const) {
      spies.push(vi.spyOn(window, prop, "get"));
    }
    spies.push(vi.spyOn(window, "addEventListener"));
  });

  const parts: [string, ReactElement][] = [
    ["Header", <Header key="h" />],
    ["Footer", <Footer key="f" />],
    ["Stamp", <Stamp key="s" state="accepted" />],
    ["Stamp animate", <Stamp key="sa" state="rejected" size="lg" animate />],
    [
      "SpecimenLabel",
      <SpecimenLabel
        key="l"
        title="Structure [03]"
        rows={[
          ["Source", "Sample paper, page 2"],
          ["Engine", "DECIMER"],
        ]}
      />,
    ],
    ["SpecimenLabel failed", <SpecimenLabel key="lf" title="Page 5" tone="failed" />],
    ["StateBadge", <StateBadge key="b" state="to-check" />],
    [
      "GlassButton",
      <GlassButton key="g" tint="orange">
        Upload a PDF
      </GlassButton>,
    ],
    [
      "GlassLink",
      <GlassLink key="gl" tint="clear" size="sm" to="/app">
        Try a sample paper
      </GlassLink>,
    ],
    ["GlassFilter", <GlassFilter key="gf" />],
    ["Structure", <Structure key="st" src="/sample/x.png" alt="x" crossed />],
    ["Smiles", <Smiles key="sm" value="CCO" struck />],
    ["DesktopOnly", <DesktopOnly key="d">tool</DesktopOnly>],
  ];

  it.each(parts)("%s: no window access, no style attribute", (_name, element) => {
    const html = renderToString(<MemoryRouter>{element}</MemoryRouter>);
    expect(html.length).toBeGreaterThan(0);
    expect(html).not.toContain(" style=");
    for (const spy of spies) expect(spy.mock.calls).toEqual([]);
  });

  it("DesktopOnly renders its children on the server", () => {
    expect(renderToString(<DesktopOnly>tool</DesktopOnly>)).toContain("tool");
  });
});
