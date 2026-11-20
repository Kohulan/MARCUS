import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import type { AnnotationOut, StepOut } from "../api/types";
import {
  annotateReason,
  annotationError,
  blockRanges,
  FAMILIES,
  familyOf,
  FIELD_MAX,
  fieldMax,
  hitsOf,
  linesOf,
  markLabel,
  newestAnnotate,
  nextHit,
  onlyAnnotating,
  sameValues,
  shownPositions,
  splitMarks,
  valuesOf,
  valuesIn,
  valuesProblem,
} from "./annotation";

const FIELDS = [
  "compound_group",
  "compound_class",
  "organism_part",
  "organism_or_species",
  "geo_location",
  "Kingdom",
  "trivial_name",
  "location",
  "iupac_name",
  "abbreviation",
  "iupac_like_name",
];

function step(over: Partial<StepOut>): StepOut {
  return {
    id: "st",
    kind: "annotate",
    page: null,
    segment_id: null,
    status: "done",
    attempts: 1,
    error_class: null,
    engine: null,
    created_at: "2026-11-20T10:00:00Z",
    started_at: null,
    finished_at: null,
    ...over,
  };
}

function ann(over: Partial<AnnotationOut> = {}): AnnotationOut {
  return {
    available: true,
    status: "done",
    step: null,
    fields: [],
    model: "fake-annotator",
    model_version: "fake-1",
    output: { organism_or_species: ["Taxus brevifolia"] },
    positions: { organism_or_species: { "Taxus brevifolia": [[0, 4, 20]] } },
    curated: null,
    curated_positions: null,
    values: { organism_or_species: ["Taxus brevifolia"] },
    coconut: null,
    created_at: null,
    updated_at: null,
    curated_at: null,
    ...over,
  };
}

describe("annotation helpers", () => {
  it("knows the server's per-value limit of all 11 fields", () => {
    expect(Object.keys(FIELD_MAX).sort()).toEqual([...FIELDS].sort());
    expect(FIELD_MAX.Kingdom).toBe(60);
    expect(FIELD_MAX.iupac_name).toBe(7179);
  });

  it("highlights the curated positions once there is a curation, else the model's", () => {
    expect(shownPositions(ann())).toEqual(ann().positions);
    const curatedPositions = { geo_location: { Jena: [[1, 0, 4]] as [number, number, number][] } };
    expect(
      shownPositions(ann({ curated: { geo_location: ["Jena"] }, curated_positions: curatedPositions })),
    ).toBe(curatedPositions);
    expect(shownPositions(ann({ positions: null }))).toEqual({});
  });

  it("collects the ranges of every shown value per block, with its field, in first-seen order", () => {
    const positions = {
      organism_or_species: { "Taxus brevifolia": [[2, 10, 26], [0, 4, 20]] as [number, number, number][] },
      organism_part: { bark: [[0, 30, 34]] as [number, number, number][], gone: [] },
      geo_location: { China: [[0, 40, 45]] as [number, number, number][] },
    };
    const values = { organism_or_species: ["Taxus brevifolia"], organism_part: ["bark", "gone"] };
    const ranges = blockRanges(values, positions);
    // China is in the positions but not a shown value: not highlighted
    expect([...ranges.entries()]).toEqual([
      [2, [[10, 26, "organism_or_species"]]],
      [0, [[4, 20, "organism_or_species"], [30, 34, "organism_part"]]],
    ]);
  });

  it("splits a block's text into plain and marked pieces, each mark with its field", () => {
    const text = "The bark of Taxus brevifolia was used.";
    const org = "organism_or_species";
    expect(splitMarks(text, [[12, 28, org], [12, 28, org], [4, 8, "organism_part"]], null)).toEqual([
      { text: "The ", fields: [], current: false },
      { text: "bark", fields: ["organism_part"], current: false },
      { text: " of ", fields: [], current: false },
      { text: "Taxus brevifolia", fields: [org], current: false },
      { text: " was used.", fields: [], current: false },
    ]);
  });

  it("marks the current occurrence apart from the others", () => {
    const text = "Taxus brevifolia bark";
    const org = "organism_or_species";
    expect(splitMarks(text, [[0, 16, org], [17, 21, "organism_part"]], [0, 16, org])).toEqual([
      { text: "Taxus brevifolia", fields: [org], current: true },
      { text: " ", fields: [], current: false },
      { text: "bark", fields: ["organism_part"], current: false },
    ]);
  });

  it("a span two fields share is one mark: the first field leads, both are named", () => {
    // NMR found as a compound name and as an abbreviation: one flat mark, no nesting
    expect(splitMarks("By NMR.", [[3, 6, "trivial_name"], [3, 6, "abbreviation"]], null)).toEqual([
      { text: "By ", fields: [], current: false },
      { text: "NMR", fields: ["trivial_name", "abbreviation"], current: false },
      { text: ".", fields: [], current: false },
    ]);
  });

  it("overlapping spans of two fields: the most specific (shortest) field leads where they meet", () => {
    const text = "Taxus brevifolia";
    const pieces = splitMarks(text, [[0, 16, "organism_or_species"], [0, 5, "trivial_name"]], null);
    expect(pieces).toEqual([
      { text: "Taxus", fields: ["trivial_name", "organism_or_species"], current: false },
      { text: " brevifolia", fields: ["organism_or_species"], current: false },
    ]);
    // the pieces only touch: every character is in exactly one mark
    expect(pieces.map((p) => p.text).join("")).toBe(text);
  });

  it("the occurrence a click went to leads with the clicked field where fields overlap", () => {
    const spans: [number, number, string][] = [[0, 16, "organism_or_species"], [0, 5, "trivial_name"]];
    expect(splitMarks("Taxus brevifolia", spans, [0, 16, "organism_or_species"])).toEqual([
      { text: "Taxus", fields: ["organism_or_species", "trivial_name"], current: true },
      { text: " brevifolia", fields: ["organism_or_species"], current: true },
    ]);
  });

  it("ignores ranges outside the text (a stale position never throws)", () => {
    expect(splitMarks("abc", [[1, 99, "Kingdom"], [7, 9, "Kingdom"], [2, 1, "Kingdom"]], null)).toEqual([
      { text: "a", fields: [], current: false },
      { text: "bc", fields: ["Kingdom"], current: false },
    ]);
    expect(splitMarks("", [], null)).toEqual([]);
  });

  it("groups the 11 fields into 6 colour families a curator reads together", () => {
    expect(Object.keys(FAMILIES)).toEqual(["organism", "part", "place", "name", "class", "systematic"]);
    expect(Object.values(FAMILIES).flat().sort()).toEqual([...FIELDS].sort());
    expect(familyOf("organism_or_species")).toBe("organism");
    expect(familyOf("Kingdom")).toBe("organism");
    expect(familyOf("organism_part")).toBe("part");
    expect(familyOf("geo_location")).toBe("place");
    expect(familyOf("location")).toBe("place");
    expect(familyOf("trivial_name")).toBe("name");
    expect(familyOf("abbreviation")).toBe("name");
    expect(familyOf("compound_class")).toBe("class");
    expect(familyOf("compound_group")).toBe("class");
    expect(familyOf("iupac_name")).toBe("systematic");
    expect(familyOf("iupac_like_name")).toBe("systematic");
  });

  it("gives a field it does not know (or a prototype name) the plain family", () => {
    expect(familyOf("new_field")).toBe("other");
    expect(familyOf("__proto__")).toBe("other");
    expect(familyOf("constructor")).toBe("other");
    expect(familyOf("toString")).toBe("other");
  });

  it("names a mark by its fields' labels, the leading field first", () => {
    const label = (key: string) =>
      ({ trivial_name: "Compound names", abbreviation: "Abbreviations" })[key] ?? key;
    expect(markLabel(["abbreviation"], label)).toBe("Abbreviations");
    expect(markLabel(["trivial_name", "abbreviation"], label)).toBe("Compound names, Abbreviations");
    expect(markLabel([], label)).toBe("");
  });

  it("walks a value's occurrences: the first, then the next, around to the first", () => {
    expect(nextHit(null, "organism_part", "bark", 3)).toBe(0);
    const at = { field: "organism_part", value: "bark", index: 0 };
    expect(nextHit(at, "organism_part", "bark", 3)).toBe(1);
    expect(nextHit({ ...at, index: 2 }, "organism_part", "bark", 3)).toBe(0);
    // another value starts at its first occurrence
    expect(nextHit({ ...at, index: 2 }, "organism_part", "roots", 3)).toBe(0);
    expect(nextHit({ ...at, index: 2 }, "location", "bark", 3)).toBe(0);
  });

  it("finds the newest annotate step and whether it is all the paper is doing", () => {
    const older = step({ id: "a1", created_at: "2026-11-20T09:00:00Z", status: "failed" });
    const newer = step({ id: "a2", created_at: "2026-11-20T10:00:00Z", status: "running" });
    const docling = step({ id: "d", kind: "docling", status: "done" });
    expect(newestAnnotate([older, docling, newer])?.id).toBe("a2");
    expect(newestAnnotate([docling])).toBeUndefined();
    expect(onlyAnnotating([older, docling, newer])).toBe(true);
    expect(onlyAnnotating([newer, step({ id: "o", kind: "ocsr", status: "queued" })])).toBe(false);
    expect(onlyAnnotating([older, docling])).toBe(false);
  });

  it("says why an annotation failed in words for this step", () => {
    expect(annotateReason("bad_input")).toBe("no title, abstract or introduction was found");
    expect(annotateReason("timeout")).toBe("it took too long");
    expect(annotateReason("engine_error")).toBe("the model failed");
    expect(annotateReason("worker_lost")).toBe("the worker stopped");
    expect(annotateReason(null)).toBe("an unknown error");
    expect(annotateReason("toString")).toBe("an unknown error");
  });

  it("edits a field as lines: one value a line, blanks and repeats out", () => {
    expect(linesOf(["Taxus brevifolia", "Taxus baccata"])).toBe("Taxus brevifolia\nTaxus baccata");
    expect(valuesOf("  Taxus brevifolia \n\n Taxus baccata\r\nTaxus brevifolia\n  ")).toEqual([
      "Taxus brevifolia",
      "Taxus baccata",
    ]);
    // commas belong to the value (IUPAC names have them)
    expect(valuesOf("2,3-dihydroxy-1,4-dione")).toEqual(["2,3-dihydroxy-1,4-dione"]);
  });

  it("tells a value set the server would refuse, by the field's label", () => {
    const label = (key: string) => (key === "Kingdom" ? "Kingdom" : key);
    expect(valuesProblem({ Kingdom: ["Plantae"] }, label)).toBeNull();
    expect(valuesProblem({ Kingdom: ["x".repeat(61)] }, label)).toBe(
      "A value in Kingdom is longer than 60 characters.",
    );
    expect(valuesProblem({ iupac_name: Array.from({ length: 201 }, (_, i) => `v${i}`) }, label)).toBe(
      "iupac_name has more than 200 values.",
    );
  });

  it("takes each field's limit from the API's fields, the client table only as a fallback", () => {
    const label = (key: string) => key;
    const fields = [
      { key: "Kingdom", label: "Kingdom", max_length: 10 },
      { key: "geo_location", label: "Place" },
    ];
    expect(fieldMax(fields, "Kingdom")).toBe(10);
    expect(fieldMax(fields, "geo_location")).toBe(348); // no max_length: the client table
    expect(fieldMax([{ key: "Kingdom", label: "K", max_length: 0 }], "Kingdom")).toBe(60);
    expect(fieldMax([], "constructor")).toBeUndefined();
    expect(valuesProblem({ Kingdom: ["x".repeat(11)] }, label, fields)).toBe(
      "A value in Kingdom is longer than 10 characters.",
    );
    expect(valuesProblem({ Kingdom: ["x".repeat(10)] }, label, fields)).toBeNull();
    expect(valuesProblem({ geo_location: ["x".repeat(349)] }, label, fields)).toBe(
      "A value in geo_location is longer than 348 characters.",
    );
  });

  it("compares value sets field by field (a missing field is none)", () => {
    expect(sameValues({ a: ["x"], b: [] }, { a: ["x"] })).toBe(true);
    expect(sameValues({ a: ["x", "y"] }, { a: ["y", "x"] })).toBe(false);
    expect(sameValues({ a: ["x"] }, { a: ["x"], b: ["z"] })).toBe(false);
  });

  it("looks values up as own keys only: __proto__ and constructor are values like any other", () => {
    // as the API sends them: JSON keys are own properties, never the prototype
    const positions = JSON.parse(
      '{"trivial_name": {"__proto__": [[0, 0, 9]], "constructor": [[1, 2, 13]]}, "abbreviation": {}}',
    ) as Record<string, Record<string, [number, number, number][]>>;
    expect(hitsOf(positions, "trivial_name", "__proto__")).toEqual([[0, 0, 9]]);
    expect(hitsOf(positions, "trivial_name", "constructor")).toEqual([[1, 2, 13]]);
    expect(hitsOf(positions, "abbreviation", "constructor")).toEqual([]);
    expect(hitsOf(positions, "abbreviation", "toString")).toEqual([]);
    expect(hitsOf(positions, "__proto__", "x")).toEqual([]);
    expect(hitsOf(positions, "constructor", "name")).toEqual([]);
    const values = { trivial_name: ["__proto__", "constructor", "hasOwnProperty"] };
    expect([...blockRanges(values, positions).entries()]).toEqual([
      [0, [[0, 9, "trivial_name"]]],
      [1, [[2, 13, "trivial_name"]]],
    ]);
    expect(valuesIn(values, "trivial_name")).toEqual(values.trivial_name);
    expect(valuesIn(values, "constructor")).toEqual([]);
    expect(valuesIn(null, "trivial_name")).toEqual([]);
    expect(valuesProblem({ constructor: ["x"] } as unknown as Record<string, string[]>, String)).toBeNull();
  });

  it("caps the values in all at the server's 300", () => {
    const many = (n: number) => Array.from({ length: n }, (_, i) => `v${i}`);
    expect(valuesProblem({ a: many(150), b: many(150) }, String)).toBeNull();
    expect(valuesProblem({ a: many(150), b: many(151) }, String)).toBe(
      "At most 300 values in all (301 now).",
    );
  });

  it("words the server's refusals of a start or a save shortly", () => {
    expect(annotationError(new ApiError(503, "The annotation model is not running"))).toBe(
      "The annotation model is not running",
    );
    expect(annotationError(new ApiError(503, "Annotation is not available"))).toBe(
      "Annotation is not available",
    );
    expect(annotationError(new ApiError(429, "rate limited", 20))).toBe(
      "Too many changes, try again in a minute",
    );
    // a start is not a change: its own limit (5 a minute) has its own words (F3)
    expect(annotationError(new ApiError(429, "rate limited", 20), "start")).toBe(
      "Too many starts, try again in a minute",
    );
    expect(annotationError(new ApiError(503, "The server is busy, try again in a moment."))).toBe(
      "The server is busy, try again in a moment.",
    );
    expect(annotationError(new ApiError(422, "Value error, too many values"))).toBe(
      "Value error, too many values",
    );
    expect(annotationError(new Error("x"))).toBe("Something went wrong.");
  });
});
