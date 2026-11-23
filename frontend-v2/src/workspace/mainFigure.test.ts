// The main figure's order and its repeats (the server links them: SegmentOut.repeat_of).
import { describe, expect, it } from "vitest";
import type { SegmentOut } from "../api/types";
import {
  alsoOnText,
  chosenMember,
  groupState,
  listedSegments,
  mainFirst,
  repeatPages,
  repeatsOf,
} from "./mainFigure";

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

  it("gives a main structure and its repeats one state", () => {
    const decided = (id: string, status: "accepted" | "rejected" | "unchecked", of?: string) => ({
      ...seg(id, of ? 2 : 1, 0, of ?? null),
      curation: { status, smiles: null, molfile: null, note: null },
    });
    const main = seg("m", 1, 0);
    // an accepted repeat, the main one not decided: accepted
    expect(groupState("to-check", main, [decided("r", "accepted", "m")])).toBe("accepted");
    // the main one rejected, a repeat accepted: accepted
    const rejected = decided("m", "rejected");
    expect(groupState("rejected", rejected, [decided("r", "accepted", "m")])).toBe("accepted");
    // rejected only when every member is
    expect(groupState("rejected", rejected, [decided("r", "rejected", "m")])).toBe("rejected");
    expect(groupState("rejected", rejected, [seg("r", 2, 0, "m")])).toBe("to-check");
    // nothing decided: the main card's own state; no repeats: its own state
    expect(groupState("failed", main, [seg("r", 2, 0, "m")])).toBe("failed");
    expect(groupState("rejected", rejected, [])).toBe("rejected");

    const r1 = decided("r1", "rejected", "m");
    const r2 = decided("r2", "accepted", "m");
    expect(chosenMember(main, [r1, r2]).id).toBe("r2");
    expect(chosenMember(decided("m", "accepted"), [r2]).id).toBe("m");
    expect(chosenMember(main, [r1]).id).toBe("m");
    expect(repeatsOf([main, r1, r2]).get("m")?.map((s) => s.id)).toEqual(["r1", "r2"]);
  });
});
