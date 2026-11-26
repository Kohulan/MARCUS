// R-group scaffolds: the words on the card, in focus mode and in the filter strip, the text
// signal, and the COCONUT guard's reasons (owner decision: never sent, never dropped silently).
import { describe, expect, it } from "vitest";
import type { CurationOut, DoclingDoc, PredictionOut, SegmentOut } from "../api/types";
import { guardSend, hasDummyAtom, heldOnlyReason, heldReason } from "../coconut/held";
import {
  filterCounts,
  hasDrawing,
  inFilter,
  metaText,
  shownFilter,
  shownStructure,
  type GridFilter,
} from "./cardState";
import { definitionPages, resultWord, rgroupNotice, rgroupTag, rgroupsOf } from "./rgroups";

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

function segment(curation: Partial<CurationOut> | null, predictions = [prediction()]): SegmentOut {
  return {
    id: "s",
    page: 0,
    idx: 0,
    bbox: [0, 0, 1, 1],
    curation: curation && { status: "unchecked", smiles: null, molfile: null, note: null, ...curation },
    predictions,
  } as SegmentOut;
}

describe("a DECIMER scaffold has a drawing (owner, 2026-11-26)", () => {
  it("[R1] tokens: RDKit refuses them, CDK draws them; other invalid SMILES have none", () => {
    const scaffold = segment(null, [
      prediction({ smiles: "[R1]c1ccccc1[R2]", valid: false, rgroups: ["R1", "R2"], drawable: true }),
    ]);
    const garbage = segment(null, [prediction({ smiles: "C1CC", valid: false, rgroups: [], drawable: false })]);
    expect(hasDrawing(scaffold)).toBe(true);
    expect(hasDrawing(garbage)).toBe(false);
  });
});

describe("the meta line", () => {
  it("names a DECIMER scaffold instead of a bare Invalid", () => {
    const s = segment(null, [
      prediction({ smiles: "[R1]c1ccccc1[R2]", valid: false, rgroups: ["R1", "R2"] }),
    ]);
    expect(metaText(shownStructure(s, "decimer"))).toBe("DECIMER · R-group scaffold (R1, R2)");
  });

  it("names a MolScribe scaffold instead of Valid", () => {
    const s = segment(null, [prediction({ engine: "molscribe", smiles: "*c1ccccc1", rgroups: ["Ar"] })]);
    expect(metaText(shownStructure(s, "molscribe"))).toBe("MolScribe · R-group scaffold (Ar)");
  });

  it("keeps Valid, Invalid and Edited for everything else", () => {
    expect(metaText(shownStructure(segment(null), "decimer"))).toBe("DECIMER · Valid");
    const bad = segment(null, [prediction({ smiles: "C(", valid: false })]);
    expect(metaText(shownStructure(bad, "decimer"))).toBe("DECIMER · Invalid");
    const edited = segment({ smiles: "CCN", rgroups: [] }, [prediction({ rgroups: ["R1"] })]);
    expect(metaText(shownStructure(edited, "decimer"))).toBe("Edited");
    // an older server without the field: no labels, no crash
    expect(rgroupsOf(prediction())).toEqual([]);
  });

  it("says an edited structure still has R-groups", () => {
    const s = segment({ molfile: "M  END", rgroups: ["R1"] });
    expect(metaText(shownStructure(s, "decimer"))).toBe("Edited · R-group scaffold (R1)");
  });

  it("uses the same word in the engines list and Compare", () => {
    expect(resultWord(prediction({ valid: false, rgroups: ["X"] }))).toBe("R-group scaffold (X)");
    expect(resultWord(prediction())).toBe("Valid");
    expect(resultWord(prediction({ valid: false }))).toBe("Invalid");
  });
});

describe("the tag and the focus line", () => {
  it("reads as words", () => {
    expect(rgroupTag(["R1", "R2"])).toBe("R-groups: R1, R2");
  });

  it("says the drawing stands for several compounds, and when the page defines them", () => {
    expect(rgroupNotice(["R1", "R2"], false)).toBe(
      "This drawing has R-groups (R1, R2): it stands for several compounds.",
    );
    expect(rgroupNotice(["X"], true)).toBe(
      "This drawing has R-groups (X): it stands for several compounds. Definitions found on this page.",
    );
  });
});

describe("the R-groups filter", () => {
  const rows = [
    { state: "to-check" as const, rgroups: ["R1"] },
    { state: "accepted" as const, rgroups: ["X"] },
    { state: "accepted" as const, rgroups: [] },
    { state: "failed" as const }, // no labels at all
  ];

  it("counts structures with R-groups, besides their state", () => {
    expect(filterCounts(rows)).toEqual({
      all: 4,
      "to-check": 1,
      accepted: 2,
      rejected: 0,
      failed: 1,
      rgroups: 2,
    });
  });

  it("shows only those", () => {
    expect(rows.filter((r) => inFilter(r, "rgroups"))).toEqual(rows.slice(0, 2));
    expect(rows.filter((r) => inFilter(r, "accepted"))).toHaveLength(2);
  });

  it("is in the strip only when the paper has such structures, or while pressed", () => {
    const none = filterCounts([{ state: "to-check" }]);
    expect(shownFilter("rgroups", "all", none)).toBe(false);
    expect(shownFilter("rgroups", "rgroups", none)).toBe(true);
    expect(shownFilter("rgroups", "all", filterCounts(rows))).toBe(true);
    const states: GridFilter[] = ["all", "to-check", "accepted", "rejected", "failed"];
    expect(states.every((f) => shownFilter(f, "all", none))).toBe(true);
  });
});

describe("the COCONUT guard", () => {
  it("says which structure is left out and why", () => {
    const h = { segmentId: "s3", n: 3, rgroups: ["R1", "R2"] };
    expect(heldReason(h)).toBe(
      "[03] has R-groups (R1, R2): build the compounds or edit the structure first",
    );
    expect(heldOnlyReason([h])).toBe(heldReason(h));
    expect(heldOnlyReason([h, { ...h, segmentId: "s4", n: 4 }])).toBe(
      "2 accepted structures have R-groups: build the compounds or edit the structures first",
    );
  });

  it("holds back any SMILES with a dummy atom, in tag order", () => {
    expect(hasDummyAtom("[1*]CC")).toBe(true);
    expect(hasDummyAtom("*C")).toBe(true);
    expect(hasDummyAtom("CCO")).toBe(false);
    expect(hasDummyAtom("CC |$;R1$|")).toBe(false); // a CXSMILES tail is not the structure
    const out = guardSend(
      [
        { segmentId: "a", n: 1, smiles: "CCO" },
        { segmentId: "b", n: 4, smiles: "*CC" },
      ],
      [{ segmentId: "c", n: 2, rgroups: ["R1"] }],
    );
    expect(out.send.map((s) => s.segmentId)).toEqual(["a"]);
    expect(out.held).toEqual([
      { segmentId: "c", n: 2, rgroups: ["R1"] },
      { segmentId: "b", n: 4, rgroups: ["*"] },
    ]);
  });
});

describe("definitionPages", () => {
  const prov = (page: number) => [{ page_no: page, bbox: {}, charspan: [0, 1] }];
  const text = (t: string, page: number, label = "caption") => ({
    self_ref: "#/texts/0",
    text: t,
    label,
    prov: prov(page),
  });

  it("finds 'R1 = OMe' in a caption, footnote or paragraph, on its 0-based page", () => {
    const doc: DoclingDoc = {
      texts: [
        text("Figure 2. Compounds 1a-1d (1a: R1 = OMe, R2 = H)", 2),
        text("a X = Cl; Ar = Ph", 4, "footnote"),
        text("R' =H for 5", 5, "text"),
        text("R 1 = Me (subscript spaced)", 6, "text"),
        text("R₂ = OH", 7, "text"),
      ],
    };
    expect([...definitionPages(doc)].sort()).toEqual([1, 3, 4, 5, 6]);
  });

  it("finds a table with R columns or definitions in its cells", () => {
    const doc: DoclingDoc = {
      texts: [],
      tables: [
        { prov: prov(3), data: { table_cells: [{ text: "Compound" }, { text: "R1" }, { text: "R2" }] } },
        { prov: prov(8), data: { table_cells: [{ text: "2" }, { text: "R = Me" }] } },
        // R/S configuration and a tick column are no definitions
        { prov: prov(9), data: { table_cells: [{ text: "C-3" }, { text: "R" }, { text: "X" }] } },
      ],
    };
    expect([...definitionPages(doc)].sort()).toEqual([2, 7]);
  });

  it("ignores words that only end in R or X, and text without a page", () => {
    const doc: DoclingDoc = {
      texts: [
        text("the PAR = 3 and MAX = 9 were used", 1, "text"),
        text("(R)-configuration, [α]D = +12", 1, "text"),
        { self_ref: "#/texts/9", text: "R1 = H", label: "text" }, // no prov
        { self_ref: "#/texts/10", text: "R1 = H", label: "text", prov: [{ page_no: "2" }] },
      ],
    };
    expect(definitionPages(doc).size).toBe(0);
  });
});
