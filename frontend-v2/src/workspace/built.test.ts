// Built structures (Markush Phase 3): the words and the order cards take.
import { describe, expect, it } from "vitest";
import type { SegmentOut } from "../api/types";
import { builtFromText, isBuilt, placeBuilt } from "./built";

const seg = (id: string, over: Partial<SegmentOut> = {}): SegmentOut => ({
  id,
  page: 0,
  idx: 0,
  bbox: [0, 0, 1, 1],
  curation: null,
  predictions: [],
  ...over,
});

describe("built", () => {
  it("builtFromText", () => {
    expect(builtFromText(3)).toBe("Built from [03]");
  });

  it("isBuilt", () => {
    expect(isBuilt(seg("a", { built_from: "s" }))).toBe(true);
    expect(isBuilt(seg("a"))).toBe(false);
  });

  it("placeBuilt puts each built card right after its scaffold, in idx order", () => {
    const list = [
      seg("s1", { idx: 0 }),
      seg("p", { idx: 1 }),
      seg("b2", { idx: 10002, built_from: "s1" }),
      seg("b1", { idx: 10001, built_from: "s1" }),
    ];
    expect(placeBuilt(list).map((s) => s.id)).toEqual(["s1", "b1", "b2", "p"]);
  });

  it("an orphan built card stays where it was, the rest unchanged", () => {
    const list = [seg("x"), seg("o", { idx: 10001, built_from: "gone" }), seg("y")];
    expect(placeBuilt(list).map((s) => s.id)).toEqual(["x", "o", "y"]);
  });
});
