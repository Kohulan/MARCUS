// Survey Sheet parts (spec §7 state table, Global Constraints): exact state words and
// shapes, the stamp, numbered tags, the drawing, SMILES copy, the desktop note, and that
// every part a pre-rendered page uses renders on the server without touching window and
// without a style attribute (CSP style-src 'self').
import { faCircleInfo } from "@fortawesome/free-solid-svg-icons";
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
import Icon from "./Icon";
import Kbd from "./Kbd";
import Smiles from "./Smiles";
import SpecimenLabel from "./SpecimenLabel";
import Stamp from "./Stamp";
import StateBadge from "./StateBadge";
import Structure from "./Structure";
import { structureTag } from "./tag";
import { ToastHost, ToastProvider, useToast } from "./Toasts";
import { reduceMotion } from "../test/reduceMotion";

const realMatchMedia = window.matchMedia;
const realInnerWidth = window.innerWidth;

/** The real matchMedia comes back after each test (afterEach), as after the stubs below. */
function mockReducedMotion(reduce: boolean) {
  reduceMotion(reduce);
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
  it("To check is an amber badge (not the brand orange: owner, 2026-11-26)", () => {
    const { container } = render(<StateBadge state="to-check" />);
    expect(container.textContent).toBe("To check");
    expect(container.querySelector(".badge--amber")).not.toBeNull();
    expect(container.querySelector(".badge--orange")).toBeNull();
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

  it("200 stamps share one media query and one change listener, and follow a change", () => {
    const listeners = new Set<() => void>();
    let reduce = false;
    const add = vi.fn((_: string, fn: () => void) => listeners.add(fn));
    window.matchMedia = vi.fn((query: string) => ({
      get matches() {
        return reduce;
      },
      media: query,
      onchange: null,
      addEventListener: add,
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })) as unknown as typeof window.matchMedia;
    const { unmount } = render(
      <>
        {Array.from({ length: 200 }, (_, i) => (
          <Stamp key={i} state="accepted" animate />
        ))}
      </>,
    );
    expect(window.matchMedia).toHaveBeenCalledTimes(1);
    expect(add).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("img", { name: "Accepted" })[0]).toHaveClass("stamp--landing");
    act(() => {
      reduce = true;
      for (const fn of listeners) fn();
    });
    for (const stamp of screen.getAllByRole("img", { name: "Accepted" })) {
      expect(stamp).not.toHaveClass("stamp--landing");
    }
    unmount();
    expect(listeners.size).toBe(0);
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

  it("a drawing that was not loaded (not 'nothing to draw') says so and offers Try again", () => {
    const onRetry = vi.fn();
    render(<Structure src={null} alt="x" failed onRetry={onRetry} />);
    expect(screen.getByText("Drawing not loaded")).toBeInTheDocument();
    expect(screen.queryByText("No drawing")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
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

  it("below 1024 px the note is the page's h1, with a way back to the start page", () => {
    setWidth(390);
    render(
      <DesktopOnly>
        <p>tool</p>
      </DesktopOnly>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "MARCUS is made for a desktop screen" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to start" })).toHaveAttribute("href", "/");
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

  it("a mounted tool stays mounted when the window narrows: hidden behind the note (B-I1)", () => {
    setWidth(1400);
    const unmounted = vi.fn();
    function Tool() {
      useEffect(() => unmounted, []);
      return <input aria-label="note draft" defaultValue="half typed" />;
    }
    render(
      <DesktopOnly>
        <Tool />
      </DesktopOnly>,
    );
    const draft = screen.getByRole("textbox", { name: "note draft" });
    act(() => {
      setWidth(900);
      window.dispatchEvent(new Event("resize"));
    });
    expect(screen.getByText("MARCUS is made for a desktop screen")).toBeInTheDocument();
    expect(unmounted).not.toHaveBeenCalled();
    expect(draft.isConnected).toBe(true);
    expect(draft.closest("[hidden]")).not.toBeNull(); // not shown, not torn down
    act(() => {
      setWidth(1400);
      window.dispatchEvent(new Event("resize"));
    });
    expect(screen.queryByText("MARCUS is made for a desktop screen")).toBeNull();
    expect(screen.getByRole("textbox", { name: "note draft" })).toBe(draft);
    expect(draft).toHaveValue("half typed");
    expect(unmounted).not.toHaveBeenCalled();
  });
});

describe("Kbd", () => {
  it("is a <kbd>", () => {
    const { container } = render(<Kbd>A</Kbd>);
    expect(container.querySelector("kbd.kbd")?.textContent).toBe("A");
  });
});

describe("Header and Footer", () => {
  const headerAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <Header />
      </MemoryRouter>,
    );

  it("header has the wordmark and the Waterline nav: About, GitHub, Open the tool", () => {
    const { container } = headerAt("/");
    expect(screen.getByRole("link", { name: "MARCUS" })).toHaveAttribute("href", "/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveClass("wl");
    const links = [...nav.querySelectorAll("a")];
    expect(links.map((a) => a.textContent)).toEqual([
      "About",
      "GitHub (opens in a new tab)",
      "Open the tool",
    ]);
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    const github = screen.getByRole("link", { name: "GitHub (opens in a new tab)" });
    expect(github).toHaveAttribute("href", "https://github.com/Kohulan/MARCUS");
    expect(github).toHaveAttribute("target", "_blank");
    expect(github).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "Open the tool" })).toHaveAttribute("href", "/app");
    // one decorative icon per item, the tool's arrow after its label
    for (const a of links) expect(a.querySelectorAll("svg.fa[aria-hidden='true']")).toHaveLength(1);
    expect(links[2]?.lastElementChild).toHaveClass("fa", "fa--after");
    // no anchors on the landing any more
    expect(container.querySelector('a[href^="/#"]')).toBeNull();
  });

  it.each([
    ["/about", "About"],
    ["/about/", "About"],
    ["/app", "Open the tool"],
  ])("on %s, %s is the current page and holds the drop", (path, name) => {
    headerAt(path);
    const nav = screen.getByRole("navigation", { name: "Main" });
    const current = nav.querySelectorAll('[aria-current="page"]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(name);
    expect(nav).toHaveClass("has-drop");
  });

  it.each(["/", "/privacy", "/app/papers/abc"])("on %s no item is current and no drop shows", (path) => {
    headerAt(path);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav.querySelector("[aria-current]")).toBeNull();
    expect(nav).not.toHaveClass("has-drop");
  });

  it("the drop follows focus and goes back to rest when focus leaves", () => {
    headerAt("/about");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const tool = screen.getByRole("link", { name: "Open the tool" });
    fireEvent.focus(tool);
    expect(nav).toHaveClass("has-drop");
    // the drop moves by transform only (skill B7): an offset and a width, never left/right
    expect(nav.style.getPropertyValue("--wl-x")).toMatch(/^-?\d+(\.\d+)?px$/);
    expect(nav.style.getPropertyValue("--wl-w")).toMatch(/^\d+(\.\d+)?px$/);
    expect(nav.style.getPropertyValue("--wl-l")).toBe("");
    fireEvent.blur(tool, { relatedTarget: null });
    expect(nav).toHaveClass("has-drop"); // resting on About again
  });

  it("arrow keys, Home and End move focus along the items", () => {
    headerAt("/");
    const [about, github, tool] = [
      screen.getByRole("link", { name: "About" }),
      screen.getByRole("link", { name: "GitHub (opens in a new tab)" }),
      screen.getByRole("link", { name: "Open the tool" }),
    ];
    about.focus();
    fireEvent.keyDown(about, { key: "ArrowRight" });
    expect(document.activeElement).toBe(github);
    fireEvent.keyDown(github, { key: "End" });
    expect(document.activeElement).toBe(tool);
    fireEvent.keyDown(tool, { key: "ArrowRight" }); // stays at the end
    expect(document.activeElement).toBe(tool);
    fireEvent.keyDown(tool, { key: "Home" });
    expect(document.activeElement).toBe(about);
    fireEvent.keyDown(about, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(about);
    // with a modifier the key is the browser's (Alt+← goes Back): not taken, not prevented
    for (const mod of [{ altKey: true }, { ctrlKey: true }, { metaKey: true }]) {
      const allowed = fireEvent.keyDown(about, { key: "ArrowRight", ...mod });
      expect(allowed).toBe(true);
      expect(document.activeElement).toBe(about);
    }
  });

  const footerAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <Footer />
      </MemoryRouter>,
    );
  const href = (name: string) => screen.getByRole("link", { name }).getAttribute("href");
  const text = (el: Element | null | undefined) =>
    (el?.textContent ?? "").replace(/\s+/g, " ").trim();

  it("the bubbles: copyright left, credit centre, Disclaimer and Privacy right", () => {
    const { container } = footerAt("/");
    const footer = container.querySelector("footer.site-footer--bubbles");
    expect(footer).not.toBeNull();
    const [copy, credit, nav] = [...(footer?.children ?? [])];
    expect(copy).toHaveClass("site-footer__copy");
    expect(text(copy)).toBe("Copyright 2026 MARCUS");
    expect(copy?.querySelector(".visually-hidden")?.textContent).toBe("Copyright ");
    expect(credit).toHaveClass("site-footer__credit");
    expect(text(credit)).toBe(
      "Built with coffee by Kohulan.R (opens in a new tab) at the Steinbeck Lab (opens in a new tab), " +
        "Friedrich Schiller University Jena (opens in a new tab)",
    );
    expect(credit?.querySelector("svg.fa-mug")).not.toBeNull();
    expect(nav).toHaveClass("site-footer__nav");
    expect(screen.getByRole("navigation", { name: "Footer" })).toBe(nav);
    expect(href("Kohulan.R (opens in a new tab)")).toBe("https://kohulanr.com");
    expect(href("Steinbeck Lab (opens in a new tab)")).toBe("https://github.com/Steinbeck-Lab");
    expect(href("Friedrich Schiller University Jena (opens in a new tab)")).toBe(
      "https://www.uni-jena.de",
    );
    for (const a of credit?.querySelectorAll("a") ?? []) {
      expect(a).toHaveAttribute("target", "_blank");
      expect(a).toHaveAttribute("rel", "noopener noreferrer");
      expect(a.querySelector("svg")).toBeNull(); // no icons on the credit's links
    }
    expect(href("Disclaimer")).toBe("/disclaimer");
    expect(href("Privacy")).toBe("/privacy");
    for (const a of nav?.querySelectorAll("a") ?? []) {
      expect(a.hasAttribute("target")).toBe(false);
      expect(a.querySelectorAll("svg.fa")).toHaveLength(1);
    }
    // About, GitHub and the licence are not in the footer; the citation lives on About
    for (const gone of ["About", "GitHub", "MIT", "10.1039", "rights reserved"]) {
      expect(container.textContent).not.toContain(gone);
    }
  });

  it.each(["/", "/about", "/privacy", "/disclaimer", "/app", "/app/images/7", "/no-such-page"])(
    "%s gets the bubbles",
    (path) => {
      const { container } = footerAt(path);
      expect(container.querySelector(".site-footer--bubbles")).not.toBeNull();
      expect(container.querySelector(".site-footer--thin")).toBeNull();
    },
  );

  it.each(["/app/papers/abc", "/app/papers/abc?s=3&focus=1", "/app/papers/abc?view=paper"])(
    "%s keeps the thin line, so the review grid keeps its space",
    (path) => {
      const { container } = footerAt(path);
      expect(container.querySelector(".site-footer--thin")).not.toBeNull();
      expect(container.querySelector(".site-footer--bubbles")).toBeNull();
      expect(container.textContent).toContain(
        "MARCUS · Friedrich Schiller University Jena · NFDI4Chem",
      );
      expect(href("About")).toBe("/about");
      expect(href("Privacy")).toBe("/privacy");
      expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    },
  );
});

describe("Icon", () => {
  it("is an inline, decorative svg with the icon's own viewBox and path", async () => {
    const { faMugHot } = await import("@fortawesome/free-solid-svg-icons");
    const { default: Icon } = await import("./Icon");
    const html = renderToString(<Icon icon={faMugHot} className="fa-mug" />);
    expect(html).toBe(
      `<svg class="fa fa-mug" viewBox="0 0 ${faMugHot.icon[0]} ${faMugHot.icon[1]}" aria-hidden="true" focusable="false">` +
        `<path d="${faMugHot.icon[4] as string}"></path></svg>`,
    );
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
    ["Icon", <Icon key="i" icon={faCircleInfo} />],
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
