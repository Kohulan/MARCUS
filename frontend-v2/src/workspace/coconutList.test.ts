// What "Send N to COCONUT" sends: accepted structures that have a structure, numbered as
// their [nn] tags (before filtering), and the form's default title.
import { describe, expect, it } from "vitest";
import type { CurationOut, PredictionOut, SegmentOut } from "../api/types";
import { coconutStructures, submissionTitle } from "./coconutList";

function prediction(over: Partial<PredictionOut> = {}): PredictionOut {
  return {
    id: "p",
    engine: "decimer",
    engine_version: "2.7",
    smiles: "CCO",
    molfile: null,
    valid: true,
    ms: 1,
    cached: false,
    created_at: "2026-11-18T10:00:00Z",
    ...over,
  };
}

function segment(id: string, curation: Partial<CurationOut> | null, predictions = [prediction()]) {
  return {
    id,
    page: 0,
    idx: 0,
    bbox: [0, 0, 1, 1],
    curation: curation && { status: "unchecked", smiles: null, molfile: null, note: null, ...curation },
    predictions,
  } as SegmentOut;
}

describe("coconutStructures", () => {
  it("keeps accepted structures with a structure, numbered as their tags", () => {
    const list = coconutStructures(
      [
        segment("s1", null), // to check
        segment("s2", { status: "accepted" }), // the prediction's SMILES
        segment("s3", { status: "rejected" }),
        segment("s4", { status: "accepted", smiles: "CCBr" }), // edited
        segment("s5", { status: "accepted" }, [prediction({ valid: false, smiles: "C(" })]),
        segment("s6", { status: "accepted" }, []),
      ],
      "decimer",
    );
    expect(list).toEqual([
      { segmentId: "s2", n: 2, smiles: "CCO" },
      { segmentId: "s4", n: 4, smiles: "CCBr" },
    ]);
  });

  it("takes the paper engine's prediction, and never a prediction for a molfile-only edit", () => {
    const list = coconutStructures(
      [
        segment("s1", { status: "accepted" }, [
          prediction({ engine: "molscribe", smiles: "CCN" }),
          prediction({ engine: "decimer", smiles: "CCC" }),
        ]),
        segment("s2", { status: "accepted", molfile: "M  END" }),
      ],
      "decimer",
    );
    expect(list).toEqual([{ segmentId: "s1", n: 1, smiles: "CCC" }]);
  });
});

describe("submissionTitle", () => {
  it("is v1's title when the first author and the year are known", () => {
    expect(submissionTitle({ firstAuthor: "Rajan", year: 2025 })).toBe(
      "MARCUS_Submission Rajan 2025",
    );
  });

  it("keeps only the parts that are known, never 'undefined'", () => {
    expect(submissionTitle({ year: 2025 })).toBe("MARCUS_Submission 2025");
    expect(submissionTitle({ firstAuthor: "  Rajan " })).toBe("MARCUS_Submission Rajan");
    expect(submissionTitle({ firstAuthor: null, year: null })).toBe("MARCUS_Submission");
    expect(submissionTitle({})).toBe("MARCUS_Submission");
  });
});
