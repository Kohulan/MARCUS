// The editor's left panel: the crop the engines read, and "Find on paper" to see the
// structure's place on its page (one marker, the paper view's box placement), "Back" to return.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EditorSource, type EditorSourceInfo } from "./EditorSource";
import { boxStyle } from "./pageBox";

const BBOX: [number, number, number, number] = [400, 900, 1200, 1500];
const SOURCE: EditorSourceInfo = {
  image: "/api/segments/s1/image",
  page: { url: "/api/papers/p1/pages/2/image", bbox: BBOX, page0: 2 },
};

function natural(img: HTMLElement, w: number, h: number) {
  Object.defineProperty(img, "naturalWidth", { value: w, configurable: true });
  Object.defineProperty(img, "naturalHeight", { value: h, configurable: true });
}

describe("EditorSource", () => {
  it("shows the crop and Find on paper", () => {
    render(<EditorSource source={SOURCE} />);
    expect(screen.getByRole("img", { name: "Crop the engines read" })).toHaveAttribute(
      "src",
      SOURCE.image,
    );
    expect(screen.getByRole("button", { name: "Find on paper" })).toBeInTheDocument();
  });

  it("without a page: no Find on paper", () => {
    render(<EditorSource source={{ image: "/api/images/j1", page: null }} />);
    expect(screen.getByRole("img", { name: "Uploaded image" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Find on paper" })).toBeNull();
  });

  it("Find on paper shows the page with this structure's box; Back returns to the crop", () => {
    const { container } = render(<EditorSource source={SOURCE} />);
    fireEvent.click(screen.getByRole("button", { name: "Find on paper" }));
    expect(screen.queryByRole("img", { name: "Crop the engines read" })).toBeNull();
    const page = screen.getByRole("img", { name: "Page 3" });
    expect(page).toHaveAttribute("src", SOURCE.page!.url);
    expect(screen.getByRole("button", { name: "Back" })).toHaveFocus();
    // the marker waits for the natural size of the 300 DPI page
    expect(container.querySelector(".editor-src__mark")).toBeNull();
    natural(page, 2480, 3508);
    fireEvent.load(page);
    const mark = container.querySelector<HTMLElement>(".editor-src__mark")!;
    expect(mark).not.toBeNull();
    const want = boxStyle(BBOX, 2480, 3508) as Record<string, string>;
    for (const v of ["--l", "--t", "--w", "--h"]) {
      expect(mark.style.getPropertyValue(v)).toBe(want[v]);
    }

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("img", { name: "Crop the engines read" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Page 3" })).toBeNull();
    expect(screen.getByRole("button", { name: "Find on paper" })).toHaveFocus();
  });

  it("a crop that fails to load keeps its alt text, and Find on paper still works", () => {
    render(<EditorSource source={SOURCE} />);
    const crop = screen.getByRole("img", { name: "Crop the engines read" });
    fireEvent.error(crop);
    expect(screen.getByRole("img", { name: "Crop the engines read" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Find on paper" }));
    expect(screen.getByRole("img", { name: "Page 3" })).toBeInTheDocument();
  });
});

describe("EditorSource zoom", () => {
  /** The view's size, as the browser would lay it out (jsdom has none). */
  function sized(view: HTMLElement, w: number, h: number) {
    Object.defineProperty(view, "clientWidth", { value: w, configurable: true });
    Object.defineProperty(view, "clientHeight", { value: h, configurable: true });
  }

  function openPage() {
    const utils = render(<EditorSource source={SOURCE} />);
    const view = utils.container.querySelector<HTMLElement>(".editor-src__view")!;
    sized(view, 500, 700);
    fireEvent.click(screen.getByRole("button", { name: "Find on paper" }));
    const page = screen.getByRole("img", { name: "Page 3" });
    natural(page, 2480, 3508);
    fireEvent.load(page);
    const sheet = utils.container.querySelector<HTMLElement>(".editor-src__sheet")!;
    return { view, sheet };
  }

  it("opens zoomed so the box fills at most 3/4 of the view, centred on it", () => {
    const { view, sheet } = openPage();
    // fit: the whole page in 500 x 700 less 16 px padding each side (468 px wide). The box,
    // 800 of 2480 px wide, is 151 px at zoom 1: 2x is the largest step within 375 px.
    expect(sheet.dataset.zoom).toBe("2");
    const fit = Math.min(500 - 32, (700 - 32) * (2480 / 3508));
    const width = fit * 2;
    expect(parseFloat(sheet.style.width)).toBeCloseTo(width, 0);
    // box centre (800, 1200) of 2480 x 3508, in the middle of the view
    const cx = (800 / 2480) * width;
    const cy = (1200 / 3508) * width * (3508 / 2480);
    expect(view.scrollLeft).toBeCloseTo(cx + Math.max(16, (500 - width) / 2) - 250, 0);
    expect(view.scrollTop).toBeCloseTo(cy + 16 - 350, 0);
  });

  it("zooms out to the whole page and in to 6x, the buttons off at the ends", () => {
    const { sheet } = openPage();
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    for (let i = 0; i < 5; i++) fireEvent.click(zoomOut);
    expect(sheet.dataset.zoom).toBe("1");
    expect(zoomOut).toBeDisabled();
    for (let i = 0; i < 6; i++) fireEvent.click(zoomIn);
    expect(sheet.dataset.zoom).toBe("6");
    expect(zoomIn).toBeDisabled();
  });

  it("a small box opens at 4x, no more", () => {
    const small: EditorSourceInfo = { ...SOURCE, page: { ...SOURCE.page!, bbox: [400, 900, 500, 1000] } };
    const { container } = render(<EditorSource source={small} />);
    sized(container.querySelector<HTMLElement>(".editor-src__view")!, 500, 700);
    fireEvent.click(screen.getByRole("button", { name: "Find on paper" }));
    const page = screen.getByRole("img", { name: "Page 3" });
    natural(page, 2480, 3508);
    fireEvent.load(page);
    expect(container.querySelector<HTMLElement>(".editor-src__sheet")!.dataset.zoom).toBe("4");
  });

  it("drag moves the page", () => {
    // jsdom has no PointerEvent: a MouseEvent with a pointerId and pointerType stands in
    class FakePointer extends MouseEvent {
      pointerId: number;
      pointerType: string;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 1;
        this.pointerType = init.pointerType ?? "mouse";
      }
    }
    vi.stubGlobal("PointerEvent", FakePointer);
    const { view } = openPage();
    const left = view.scrollLeft;
    const top = view.scrollTop;
    fireEvent.pointerDown(view, { clientX: 300, clientY: 300, button: 0, pointerId: 1 });
    fireEvent.pointerMove(view, { clientX: 260, clientY: 250, pointerId: 1 });
    fireEvent.pointerUp(view, { pointerId: 1 });
    expect(view.scrollLeft).toBe(left + 40);
    expect(view.scrollTop).toBe(top + 50);
    vi.unstubAllGlobals();
  });

  it("no zoom buttons on the crop", () => {
    render(<EditorSource source={SOURCE} />);
    expect(screen.queryByRole("button", { name: "Zoom in" })).toBeNull();
  });
});
