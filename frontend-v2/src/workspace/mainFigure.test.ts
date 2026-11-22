// The main figure's order and its repeats (the server links them: SegmentOut.repeat_of).
import { describe, expect, it } from "vitest";
import type { SegmentOut } from "../api/types";
import { alsoOnText, listedSegments, mainFirst, repeatPages } from "./mainFigure";

const seg = (id: string, page: number, idx: number, repeat_of: string | null = null) =>
  ({ id, page, idx, bbox: [0, 0, 1, 1], curation: null, predictions: [], repeat_of }) as SegmentOut;

describe("mainFigure", () => {
  it("puts the main page first, each part in (page, idx) order", () => {
    const list = [seg("a", 0, 1), seg("b", 2, 0), seg("c", 1, 1), seg("d", 1, 0), seg("e", 0, 0)];
    expect(mainFirst(list, 1).map((s) => s.id)).toEqual(["d", "c", "e", "a", "b"]);
    expect(mainFirst(list, null).map((s) => s.id)).toEqual(["e", "a", "d", "c", "b"]);
    expect(mainFirst(list, undefined).map((s) => s.id)).toEqual(["e", "a", "d", "c", "b"]);
  });

  it("lists every structure but the repeats", () => {
    const list = [seg("m", 1, 0), seg("r", 3, 0, "m"), seg("o", 2, 0)];
    expect(listedSegments(list).map((s) => s.id)).toEqual(["m", "o"]);
    const none = [seg("m", 1, 0)];
    expect(listedSegments(none)).toBe(none);
  });

  it("names the pages of a main structure's repeats once each, 1-based and sorted", () => {
    const list = [seg("m", 1, 0), seg("r1", 5, 0, "m"), seg("r2", 3, 0, "m"), seg("r3", 5, 1, "m")];
    const pages = repeatPages(list);
    expect(pages.get("m")).toEqual([4, 6]);
    expect(alsoOnText(pages.get("m"))).toBe("Also on pages 4, 6");
    expect(alsoOnText([2])).toBe("Also on page 2");
    expect(alsoOnText(undefined)).toBeNull();
    expect(alsoOnText([])).toBeNull();
  });
});
