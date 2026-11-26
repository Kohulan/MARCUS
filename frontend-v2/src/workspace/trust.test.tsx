// Trustworthy agreement (owner decisions 2026-11-26): the stereo-aware badge, "To review"
// against "To check", and the measured line beside the badge.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PaperDetail, PredictionOut, SegmentOut } from "../api/types";
import StateBadge, { STATE_WORD } from "../ui/StateBadge";
import {
  agreeState,
  agreeText,
  filterCounts,
  filterOf,
  FILTERS,
  isOpen,
  stateOf,
} from "./cardState";
import { MEASURED, measuredText } from "./trust";

const paper = { status: "done", ocsr_mode: "auto" } as PaperDetail;

function segment(over: Partial<SegmentOut> = {}): SegmentOut {
  const prediction = { id: "p", engine: "decimer", smiles: "CCO", valid: true } as PredictionOut;
  return {
    id: "s",
    page: 0,
    idx: 0,
    bbox: [0, 0, 1, 1],
    curation: null,
    predictions: [prediction],
    ...over,
  } as SegmentOut;
}

describe("the badge is stereo-aware", () => {
  it.each([
    ["agree3", 3, 3, "3 agree"],
    ["agree2", 2, 3, "2 agree"],
    ["agree2", 2, 2, "2 of 2 agree"],
    ["stereo", 0, 3, "Stereo differs"],
    ["stereo", 0, 2, "Stereo differs"],
    ["differ", 0, 3, "Differ"],
    ["differ", 0, 2, "2 differ"],
  ] as const)("%s (%i of %i) reads %s", (agree_state, agree, agree_of, text) => {
    expect(agreeText(segment({ agree_state, agree, agree_of }))).toBe(text);
  });

  it("has no badge while engines read", () => {
    expect(agreeText(segment({ agree: null, agree_state: null }))).toBeNull();
    expect(agreeState(segment({}))).toBeNull();
  });

  it("an older server (no agree_state): the count decides", () => {
    expect(agreeState(segment({ agree: 3, agree_of: 3 }))).toBe("agree3");
    expect(agreeState(segment({ agree: 2, agree_of: 3 }))).toBe("agree2");
    expect(agreeState(segment({ agree: 0, agree_of: 3 }))).toBe("differ");
  });
});

describe("To review against To check", () => {
  const state = (over: Partial<SegmentOut>) => stateOf(segment(over), [], paper);

  it("engines agree: To review", () => {
    expect(state({ agree_state: "agree3", agree: 3 })).toBe("to-review");
    expect(state({ agree_state: "agree2", agree: 2 })).toBe("to-review");
  });

  it("engines differ, stereo differs, or no badge: To check", () => {
    expect(state({ agree_state: "differ", agree: 0 })).toBe("to-check");
    expect(state({ agree_state: "stereo", agree: 0 })).toBe("to-check");
    expect(state({ agree_state: null, agree: null })).toBe("to-check");
    expect(state({})).toBe("to-check");
  });

  it("a decision wins", () => {
    const curation = { status: "accepted" } as SegmentOut["curation"];
    expect(state({ agree_state: "differ", curation })).toBe("accepted");
  });

  it("both are open: still to decide", () => {
    expect(isOpen("to-review") && isOpen("to-check")).toBe(true);
    expect(isOpen("accepted") || isOpen("failed") || isOpen("reading")).toBe(false);
  });

  it("each has its own filter and count", () => {
    expect(FILTERS.map((f) => f.label)).toEqual([
      "All",
      "To check",
      "To review",
      "Accepted",
      "Rejected",
      "Failed",
      "R-groups",
    ]);
    expect(filterOf("to-review")).toBe("to-review");
    const counts = filterCounts([
      { state: "to-review" },
      { state: "to-review" },
      { state: "to-check" },
      { state: "reading" },
      { state: "accepted" },
    ]);
    expect(counts["to-review"]).toBe(2);
    expect(counts["to-check"]).toBe(2);
  });

  it("To review is a calm outline, To check an amber fill", () => {
    expect(STATE_WORD["to-review"]).toBe("To review");
    const review = render(<StateBadge state="to-review" />).container.firstElementChild!;
    expect(review.textContent).toBe("To review");
    expect(review.className).toContain("badge--outline");
    const check = render(<StateBadge state="to-check" />).container.firstElementChild!;
    expect(check.textContent).toBe("To check");
    expect(check.className).toContain("badge--amber");
    expect(check.className).not.toContain("orange");
  });
});

describe("the measured line", () => {
  it("says how often each badge was right, and where the number comes from", () => {
    for (const s of ["agree3", "agree2", "stereo", "differ"] as const) {
      const m = MEASURED[s];
      expect(m.right).toBeLessThanOrEqual(m.n);
      expect(measuredText(s)).toContain(`${m.right} of ${m.n}`);
      expect(measuredText(s)).toContain("hand-checked");
      expect(measuredText(s)).toContain("MARCUS test set 2026-11-26");
    }
  });
});
