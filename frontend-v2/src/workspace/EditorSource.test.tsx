// The editor's left panel: the crop the engines read, and "Find on paper" to see the
// structure's place on its page (one marker, the paper view's box placement), "Back" to return.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
    expect(screen.getByRole("img", { name: "Crop the engines read" })).toBeInTheDocument();
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
