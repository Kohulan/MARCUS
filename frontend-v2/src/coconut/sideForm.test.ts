// The COCONUT side form's starting values and its MARCUS JSON (owner decision 2026-11-25).
import { describe, expect, it } from "vitest";
import type { PaperDetail, PredictionOut, SegmentOut } from "../api/types";
import { jsonFileName, marcusJson, sideStart, sideStructure, structuralComment } from "./sideForm";

const pred = (over: Partial<PredictionOut> = {}): PredictionOut => ({
  id: "p1",
  engine: "molparser",
  engine_version: "1",
  smiles: "COc1ccccc1",
  molfile: null,
  valid: true,
  ms: 1,
  cached: false,
  created_at: "2026-11-25T10:00:00Z",
  ...over,
});

const seg = (over: Partial<SegmentOut> = {}): SegmentOut => ({
  id: "s2",
  page: 3,
  idx: 10001,
  bbox: [0, 0, 1, 1],
  curation: { status: "accepted", smiles: null, molfile: null, note: null },
  predictions: [pred()],
  ...over,
});

const PAPER = {
  id: "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f",
  doi: "10.1021/acs.jnatprod.6c00411",
  title: "Prenylated Isoflavones",
  display_name: "jnp.pdf",
  engine: "decimer",
  first_author: "Fang",
  year: 2026,
} as unknown as PaperDetail;

const START = {
  organisms: [{ name: "Millettia dura", parts: "roots", location: "", ecosystems: "" }],
  note: "Organisms: model suggestion",
};
const BUILT = { segmentId: "s1", n: 1 };
const ROW = { compound: "20a", groups: { R1: "OMe", R2: "H" } };

describe("sideStart", () => {
  it("names the structure from the text, else by its compound ID, else nothing", () => {
    expect(sideStart(seg({ compound_id: "1i", compound_name: "maximaisoflavone J" }), PAPER, START, null, null).fields.name).toBe("maximaisoflavone J");
    expect(sideStart(seg({ compound_id: "20a" }), PAPER, START, null, null).fields.name).toBe("Compound 20a");
    expect(sideStart(seg(), PAPER, START, null, null).fields.name).toBe("");
  });

  it("starts the paper fields as the batch form does", () => {
    const { paper } = sideStart(seg(), PAPER, START, null, null);
    expect(paper).toEqual({
      title: "MARCUS_Submission Fang 2026",
      doi: "10.1021/acs.jnatprod.6c00411",
      evidence: "Prenylated Isoflavones",
      comment: "",
      organisms: START.organisms,
    });
  });

  it("a built structure says where it comes from", () => {
    const s = seg({ compound_id: "20a", built_from: "s1" });
    expect(sideStart(s, PAPER, START, BUILT, ROW).fields.structuralComments).toBe("Built from [01]: R1 = OMe, R2 = H (row 20a)");
    expect(sideStructure(s, 2, PAPER.engine).structure).toEqual({ segmentId: "s2", n: 2, smiles: "COc1ccccc1" });
  });

  it("a scaffold gets no structure to send, and the reason", () => {
    const scaffold = seg({ predictions: [pred({ smiles: "*c1ccccc1", rgroups: ["R1"] })] });
    const out = sideStructure(scaffold, 1, PAPER.engine);
    expect(out.structure).toBeNull();
    expect(out.heldReason).toBe("[01] has R-groups (R1): build the compounds or edit the structure first");
  });
});

describe("structuralComment", () => {
  it("without a scaffold row it is empty", () => {
    expect(structuralComment(null, null)).toBe("");
  });
});

describe("marcusJson", () => {
  it("holds exactly what the form shows", () => {
    const s = seg({ compound_id: "20a", built_from: "s1" });
    const start = sideStart(s, PAPER, START, BUILT, ROW);
    const { structure } = sideStructure(s, 2, PAPER.engine);
    expect(marcusJson(PAPER, s, structure!, start.paper, start.fields, BUILT, ROW)).toEqual({
      format: "marcus-coconut-1",
      paper: { id: PAPER.id, doi: PAPER.doi, title: PAPER.title, display_name: "jnp.pdf" },
      structure: {
        segment_id: "s2",
        tag: "[02]",
        page: 4,
        compound_id: "20a",
        name: "Compound 20a",
        smiles: "COc1ccccc1",
        molfile: null,
        rgroups: [],
        built_from: { tag: "[01]", row: "20a", groups: { R1: "OMe", R2: "H" } },
      },
      coconut: {
        title: "MARCUS_Submission Fang 2026",
        evidence: "Prenylated Isoflavones",
        comment: "",
        organisms: START.organisms,
        structural_comments: "Built from [01]: R1 = OMe, R2 = H (row 20a)",
        reference_id: "10.1021/acs.jnatprod.6c00411",
        link: "",
      },
    });
  });

  it("names the file by paper and compound", () => {
    expect(jsonFileName(PAPER.id, "20a", 2)).toBe("marcus-coconut-3f2a9c1e-20a.json");
    expect(jsonFileName(PAPER.id, null, 2)).toBe("marcus-coconut-3f2a9c1e-02.json");
  });
});
