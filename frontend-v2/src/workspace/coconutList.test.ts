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
  it("sends a main structure and its repeats once, and numbers as the listed rows", () => {
    const list = coconutStructures(
      [
        segment("main", { status: "accepted" }),
        { ...segment("again", { status: "accepted", smiles: "OCC" }), repeat_of: "main" },
        segment("other", { status: "accepted", smiles: "CCN" }),
      ],
      "decimer",
    );
    expect(list.send).toEqual([
      { segmentId: "main", n: 1, smiles: "CCO" }, // the main one first when it is accepted
      { segmentId: "other", n: 2, smiles: "CCN" },
    ]);
    expect(list.held).toEqual([]);
  });

  it("an accepted repeat sends its group, with its structure, whatever the main one's status", () => {
    for (const main of [null, { status: "unchecked" as const }, { status: "rejected" as const }]) {
      const list = coconutStructures(
        [
          segment("main", main),
          { ...segment("again", { status: "accepted", smiles: "OCC" }), repeat_of: "main" },
        ],
        "decimer",
      );
      expect(list.send).toEqual([{ segmentId: "main", n: 1, smiles: "OCC" }]);
    }
  });

  it("a group with no accepted member sends nothing (all rejected, or to check)", () => {
    const rejected = coconutStructures(
      [
        segment("main", { status: "rejected" }),
        { ...segment("again", { status: "rejected" }), repeat_of: "main" },
      ],
      "decimer",
    );
    expect(rejected).toEqual({ send: [], held: [] });
  });

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
    expect(list.send).toEqual([
      { segmentId: "s2", n: 2, smiles: "CCO" },
      { segmentId: "s4", n: 4, smiles: "CCBr" },
    ]);
    expect(list.held).toEqual([]);
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
    expect(list.send).toEqual([{ segmentId: "s1", n: 1, smiles: "CCC" }]);
  });

  it("takes the server's pick: the engines' majority over the paper's engine", () => {
    const own = prediction({ id: "d", engine: "decimer", smiles: "CCC" });
    const majority = prediction({ id: "m", engine: "molparser", smiles: "CCN" });
    const list = coconutStructures(
      [
        {
          ...segment("s1", { status: "accepted" }, [
            prediction({ id: "s", engine: "molscribe", smiles: "NCC" }),
            majority,
            own,
          ]),
          default_prediction_id: "m",
        },
      ],
      "decimer",
    );
    expect(list.send).toEqual([{ segmentId: "s1", n: 1, smiles: "CCN" }]);
  });

  it("never sends a structure with R-groups: it is held, with its labels", () => {
    const list = coconutStructures(
      [
        segment("s1", { status: "accepted" }), // plain: sent
        // MolScribe's scaffold: valid, but a wildcard atom
        segment("s2", { status: "accepted" }, [
          prediction({ smiles: "[1*]c1ccccc1[2*]", rgroups: ["R1", "R2"] }),
        ]),
        // a curated scaffold (Ketcher R#), molfile only
        segment("s3", { status: "accepted", molfile: "M  END", rgroups: ["R1"] }),
        // edited to a full compound: the prediction's R-groups no longer count
        segment("s4", { status: "accepted", smiles: "CCOC", rgroups: [] }, [
          prediction({ smiles: "*CC", rgroups: ["*"] }),
        ]),
        // a dummy atom the server has not labelled yet (optimistic curation): held as "*"
        segment("s5", { status: "accepted", smiles: "[1*]CC" }),
        // to check, with R-groups: not accepted, so neither sent nor held
        segment("s6", null, [prediction({ smiles: "*C", rgroups: ["*"] })]),
      ],
      "decimer",
    );
    expect(list.send).toEqual([
      { segmentId: "s1", n: 1, smiles: "CCO" },
      { segmentId: "s4", n: 4, smiles: "CCOC" },
    ]);
    expect(list.held).toEqual([
      { segmentId: "s2", n: 2, rgroups: ["R1", "R2"] },
      { segmentId: "s3", n: 3, rgroups: ["R1"] },
      { segmentId: "s5", n: 5, rgroups: ["*"] },
    ]);
  });

  it("holds any structure with placeholder atoms, whatever labels its page shows", () => {
    // DECIMER read R1, R2 and Z; the page's text names R1 and R2, so Z is not shown. The
    // SMILES has no "*" (DECIMER's tokens), so only the server's word can hold it.
    const list = coconutStructures(
      [
        segment("s1", { status: "accepted" }, [
          prediction({ smiles: "[R1]c1ccc([Z])cc1[R2]", rgroups: ["R1", "R2"], placeholder: true }),
        ]),
        // even with no label shown at all
        segment("s2", { status: "accepted" }, [
          prediction({ smiles: "[Z]c1ccccc1", rgroups: [], placeholder: true }),
        ]),
        segment("s3", { status: "accepted", smiles: "CC[R1]", rgroups: [], placeholder: true }),
      ],
      "decimer",
    );
    expect(list.send).toEqual([]);
    expect(list.held).toEqual([
      { segmentId: "s1", n: 1, rgroups: ["R1", "R2"] },
      { segmentId: "s2", n: 2, rgroups: ["*"] },
      { segmentId: "s3", n: 3, rgroups: ["*"] },
    ]);
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

describe("built structures (Markush Phase 3)", () => {
  it("an accepted built card is sent with its SMILES; the accepted scaffold stays held", () => {
    const scaffold = {
      ...segment("s1", { status: "accepted" }, [prediction({ smiles: "[1*]c1ccccc1", rgroups: ["R1"] })]),
    };
    const built = {
      ...segment("s2", { status: "accepted" }, [
        prediction({ id: "pb", engine: "enumerated", smiles: "COc1ccccc1" }),
      ]),
      idx: 10001,
      built_from: "s1",
      compound_id: "3a",
    };
    const out = coconutStructures([scaffold, built], "decimer");
    expect(out.send.map((s) => s.smiles)).toEqual(["COc1ccccc1"]);
    expect(out.held).toHaveLength(1);
  });
});
