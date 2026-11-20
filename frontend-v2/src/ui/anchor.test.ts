import { describe, expect, it } from "vitest";
import { placePanel, visibleArea, type Box, type PlaceOptions } from "./anchor";

const VIEW: Box = { top: 0, left: 0, right: 1024, bottom: 768 };
const box = (left: number, top: number, w: number, h: number): Box => ({
  top,
  left,
  right: left + w,
  bottom: top + h,
});
const opts = (o: Partial<PlaceOptions> = {}): PlaceOptions => ({
  prefer: "above",
  align: "end",
  gap: 6,
  margin: 8,
  ...o,
});
const MENU = { width: 200, height: 260 };

/** The placed panel's box. */
function placed(anchor: Box, size = MENU, o: Partial<PlaceOptions> = {}, bounds = VIEW) {
  const p = placePanel(anchor, size, bounds, opts(o));
  const height = Math.min(size.height, p.maxHeight);
  return { ...p, box: box(p.left, p.top, size.width, height) };
}

const inside = (b: Box, bounds = VIEW, margin = 8) =>
  b.left >= bounds.left + margin &&
  b.top >= bounds.top + margin &&
  b.right <= bounds.right - margin &&
  b.bottom <= bounds.bottom - margin;

describe("placePanel", () => {
  it("opens on the preferred side when it fits there, its right edge on the button's", () => {
    const p = placed(box(900, 600, 80, 32));
    expect(p.side).toBe("above");
    expect(p.box.bottom).toBe(600 - 6);
    expect(p.box.right).toBe(980);
    expect(inside(p.box)).toBe(true);
  });

  it("flips below a button near the top of the window (the first card's More)", () => {
    const p = placed(box(900, 220, 80, 32));
    expect(p.side).toBe("below");
    expect(p.box.top).toBe(252 + 6);
    expect(inside(p.box)).toBe(true);
  });

  it("flips above a button near the bottom when below is preferred (Export, a last card)", () => {
    const p = placed(box(600, 700, 80, 32), MENU, { prefer: "below" });
    expect(p.side).toBe("above");
    expect(inside(p.box)).toBe(true);
  });

  it("caps the height on the roomier side when neither side has room; it scrolls inside", () => {
    const short: Box = { top: 0, left: 0, right: 1024, bottom: 400 };
    const p = placed(box(600, 150, 80, 32), { width: 200, height: 500 }, {}, short);
    expect(p.side).toBe("below");
    expect(p.maxHeight).toBe(400 - 8 - (182 + 6));
    expect(inside(p.box, short)).toBe(true);
  });

  it("shifts sideways to stay inside: start-aligned at the right edge, end-aligned at the left", () => {
    const right = placed(box(950, 600, 60, 32), MENU, { align: "start" });
    expect(right.box.right).toBe(1024 - 8);
    const left = placed(box(10, 600, 60, 32), MENU, { align: "end" });
    expect(left.box.left).toBe(8);
  });

  it("keeps the panel inside even when the anchor is partly past the window's edge", () => {
    for (const top of [-20, 760]) {
      const p = placed(box(600, top, 80, 32));
      expect(inside(p.box)).toBe(true);
    }
  });

  it("never gives a negative height", () => {
    const tiny: Box = { top: 0, left: 0, right: 300, bottom: 40 };
    const p = placePanel(box(10, 4, 60, 32), MENU, tiny, opts());
    expect(p.maxHeight).toBeGreaterThanOrEqual(0);
  });
});

describe("visibleArea", () => {
  it("is the viewport cut by every clipping ancestor", () => {
    const root = document.documentElement;
    Object.defineProperty(root, "clientWidth", { configurable: true, value: 1024 });
    Object.defineProperty(root, "clientHeight", { configurable: true, value: 700 });
    const col = document.createElement("section");
    col.style.overflowY = "auto";
    const card = document.createElement("div");
    const button = document.createElement("button");
    card.append(button);
    col.append(card);
    document.body.append(col);
    col.getBoundingClientRect = () => DOMRect.fromRect({ x: 600, y: 260, width: 400, height: 500 });
    card.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 0, width: 5000, height: 5000 });
    const seen = visibleArea(button);
    expect(seen).toEqual({ top: 260, left: 600, right: 1000, bottom: 700 });
    col.remove();
    delete (root as { clientWidth?: number }).clientWidth;
    delete (root as { clientHeight?: number }).clientHeight;
  });
});
