// The figures behind every progress bar: the shown percentage (100 only when the work is
// done), the one motion curve, the count-up frame (never down) and the annotate estimate.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ANNOTATE_CAP,
  ANNOTATE_TYPICAL_MS,
  ANNOTATE_TYPICAL_SHARE,
  annotateEstimate,
  climb,
  type Climb,
  countFrame,
  ease,
  EASE,
  FILL_MS,
  percentOf,
  spokenValue,
} from "./progressMotion";

describe("percentOf", () => {
  it("rounds down, so 100% is shown only when the work is done", () => {
    expect(percentOf(0)).toBe(0);
    expect(percentOf(0.625)).toBe(62);
    expect(percentOf(0.999)).toBe(99);
    expect(percentOf(1)).toBe(100);
  });

  it("keeps a float that is a whole percent on its percent", () => {
    expect(percentOf(0.29)).toBe(29); // 0.29 * 100 is 28.999999999999996
    expect(percentOf(0.57)).toBe(57);
  });

  it("stays within 0 to 100", () => {
    expect(percentOf(-0.2)).toBe(0);
    expect(percentOf(1.4)).toBe(100);
    expect(percentOf(Number.NaN)).toBe(0);
  });
});

describe("spokenValue", () => {
  it("adds the percentage to the bar's words", () => {
    expect(spokenValue("Reading structures, 10 of 15", 0.62)).toBe("Reading structures, 10 of 15, 62%");
    expect(spokenValue("", 0.5)).toBe("50%");
  });

  it("says an estimate is one, until the work has ended", () => {
    expect(spokenValue("Annotating", 0.6, true)).toBe("Annotating, about 60%");
    expect(spokenValue("Annotating", 1, true)).toBe("Annotating, 100%");
  });

  it("says only the words while nothing is measured", () => {
    expect(spokenValue("Waiting", null)).toBe("Waiting");
  });
});

describe("ease (the --ease curve, cubic-bezier(0.22, 1, 0.36, 1))", () => {
  it("is the --ease token's curve", () => {
    const tokens = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");
    expect(tokens).toContain(`--ease: cubic-bezier(${EASE.join(", ")});`);
  });

  it("starts at 0, ends at 1 and never goes back", () => {
    expect(ease(0)).toBe(0);
    expect(ease(1)).toBe(1);
    let last = 0;
    for (let t = 0.05; t <= 1; t += 0.05) {
      const y = ease(t);
      expect(y).toBeGreaterThanOrEqual(last);
      last = y;
    }
  });

  it("is an ease-out: most of the way there by half time", () => {
    expect(ease(0.5)).toBeGreaterThan(0.85);
    expect(ease(0.1)).toBeGreaterThan(0.25);
  });
});

describe("countFrame", () => {
  it("eases from the shown value to the new one over FILL_MS", () => {
    expect(countFrame(0.2, 0.6, 0, FILL_MS)).toBe(0.2);
    const mid = countFrame(0.2, 0.6, FILL_MS / 2, FILL_MS);
    expect(mid).toBeGreaterThan(0.4);
    expect(mid).toBeLessThan(0.6);
    expect(countFrame(0.2, 0.6, FILL_MS, FILL_MS)).toBe(0.6);
    expect(countFrame(0.2, 0.6, FILL_MS * 3, FILL_MS)).toBe(0.6);
  });

  it("never counts down", () => {
    expect(countFrame(0.6, 0.2, 100, FILL_MS)).toBe(0.6);
    for (let t = 0; t <= FILL_MS; t += 25) {
      expect(countFrame(0.3, 0.9, t + 25, FILL_MS)).toBeGreaterThanOrEqual(countFrame(0.3, 0.9, t, FILL_MS));
    }
  });
});

describe("annotateEstimate (the model reports no progress: a time-based estimate)", () => {
  it("is a named estimate of a typical run: about 6 s to 90%", () => {
    expect(ANNOTATE_TYPICAL_MS).toBe(6000);
    expect(ANNOTATE_TYPICAL_SHARE).toBe(0.9);
    expect(ANNOTATE_CAP).toBe(0.95);
  });

  it("starts at 0 and eases toward 90% over the typical run time", () => {
    expect(annotateEstimate(0)).toBe(0);
    expect(annotateEstimate(1500)).toBeGreaterThan(0.3);
    expect(annotateEstimate(3000)).toBeGreaterThan(0.6);
    expect(annotateEstimate(3000)).toBeLessThan(0.9);
    expect(annotateEstimate(ANNOTATE_TYPICAL_MS)).toBeCloseTo(0.9, 5);
  });

  it("then creeps slowly toward 95%, never reaching it, never 100%", () => {
    const at = (s: number) => annotateEstimate(s * 1000);
    expect(at(12)).toBeGreaterThan(0.9);
    expect(at(12)).toBeLessThan(0.94);
    expect(at(60)).toBeLessThan(ANNOTATE_CAP);
    expect(at(3600)).toBeLessThanOrEqual(ANNOTATE_CAP);
    expect(percentOf(at(3600))).toBeLessThanOrEqual(95);
  });

  it("never goes back as time passes", () => {
    let last = 0;
    for (let ms = 0; ms <= 60_000; ms += 250) {
      const v = annotateEstimate(ms);
      expect(v).toBeGreaterThanOrEqual(last);
      last = v;
    }
  });

  it("treats a negative elapsed time as the start", () => {
    expect(annotateEstimate(-500)).toBe(0);
  });
});

describe("climb", () => {
  const start: Climb = { max: 0, busy: true };

  it("only ever rises during a run", () => {
    let s = climb(start, 0.2, true);
    expect(s.max).toBe(0.2);
    s = climb(s, 0.15, true);
    expect(s.max).toBe(0.2);
    s = climb(s, 0.4, true);
    expect(s.max).toBe(0.4);
  });

  it("keeps the figure through a moment with none", () => {
    const s = climb({ max: 0.4, busy: true }, null, true);
    expect(s.max).toBe(0.4);
  });

  it("returns the same state when nothing changes (no extra render)", () => {
    const s = { max: 0.4, busy: true };
    expect(climb(s, 0.3, true)).toBe(s);
  });

  it("starts again when a finished paper is busy again (a page retried)", () => {
    let s = climb({ max: 0, busy: true }, 1, false);
    expect(s).toEqual({ max: 1, busy: false });
    s = climb(s, 0.8, true);
    expect(s).toEqual({ max: 0.8, busy: true });
  });
});
