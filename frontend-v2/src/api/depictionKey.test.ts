import { describe, expect, it } from "vitest";
import { depictionKey } from "./depictionKey";
import type { PredictionOut, SegmentOut } from "./types";

function pred(id: string, valid: boolean, smiles = "CCO"): PredictionOut {
  return {
    id,
    engine: "decimer",
    engine_version: "1",
    smiles,
    molfile: null,
    valid,
    ms: 10,
    cached: false,
    created_at: "2026-11-18T00:00:00Z",
  };
}

function seg(over: Partial<SegmentOut> = {}): SegmentOut {
  return {
    id: "s1",
    page: 0,
    idx: 0,
    bbox: [1, 2, 3, 4],
    curation: { status: "unchecked", smiles: "CCO", molfile: null, note: null },
    predictions: [pred("a", true), pred("b", false)],
    ...over,
  };
}

describe("depictionKey", () => {
  it("is an 8-digit hex string and the same for the same inputs", () => {
    expect(depictionKey(seg())).toMatch(/^[0-9a-f]{8}$/);
    expect(depictionKey(seg())).toBe(depictionKey(seg()));
  });

  it("ignores status, note and bbox", () => {
    const other = seg({
      bbox: [9, 9, 9, 9],
      curation: { status: "accepted", smiles: "CCO", molfile: null, note: "n" },
    });
    expect(depictionKey(other)).toBe(depictionKey(seg()));
  });

  it("changes with the curated SMILES or molfile", () => {
    const base = depictionKey(seg());
    expect(
      depictionKey(
        seg({ curation: { status: "unchecked", smiles: "CCN", molfile: null, note: null } }),
      ),
    ).not.toBe(base);
    expect(
      depictionKey(
        seg({ curation: { status: "unchecked", smiles: "CCO", molfile: "M  END", note: null } }),
      ),
    ).not.toBe(base);
    expect(depictionKey(seg({ curation: null }))).not.toBe(base);
  });

  it("changes with a new valid prediction, not with a new invalid one", () => {
    const base = depictionKey(seg());
    const preds = seg().predictions;
    expect(depictionKey(seg({ predictions: [pred("c", true), ...preds] }))).not.toBe(base);
    expect(depictionKey(seg({ predictions: [pred("c", false), ...preds] }))).toBe(base);
  });

  it("changes when a prediction becomes invalid", () => {
    const base = depictionKey(seg());
    expect(depictionKey(seg({ predictions: [pred("a", false), pred("b", false)] }))).not.toBe(
      base,
    );
  });

  it("matches FNV-1a 32-bit of the JSON input", () => {
    // FNV-1a("") = 811c9dc5; FNV-1a("a") = e40c292c (published test vectors)
    const noInputs = seg({ curation: null, predictions: [] });
    // JSON.stringify([null, null, []]) = "[null,null,[]]"
    expect(depictionKey(noInputs)).toBe(fnv("[null,null,[]]"));
    expect(fnv("")).toBe("811c9dc5");
    expect(fnv("a")).toBe("e40c292c");
  });
});

// independent reference implementation for the vector check
function fnv(s: string): string {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(s)) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}
