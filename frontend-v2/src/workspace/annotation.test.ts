import { describe, expect, it } from "vitest";
import type { AnnotationOut } from "../api/types";
import {
  blockRanges,
  FAMILIES,
  familyOf,
  fieldLabel,
  hitsOf,
  linesOf,
  markLabel,
  nextHit,
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

function ann(over: Partial<AnnotationOut> = {}): AnnotationOut {
  return {
    available: true,
    status: "done",
    step: null,
    fields: [],
    limits: { max_values_per_field: 200, max_total_values: 300 },
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

const LIMITS = { max_values_per_field: 200, max_total_values: 300 };

describe("annotation helpers", () => {
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

  it("the occurrence a click went to is one mark, led by the clicked field, naming every field in it", () => {
    const spans: [number, number, string][] = [[0, 16, "organism_or_species"], [0, 5, "trivial_name"]];
    expect(splitMarks("Taxus brevifolia", spans, [0, 16, "organism_or_species"])).toEqual([
      { text: "Taxus brevifolia", fields: ["organism_or_species", "trivial_name"], current: true },
    ]);
    // the clicked field leads even over a shorter span of another field
    expect(splitMarks("Taxus brevifolia", spans, [0, 5, "trivial_name"])).toEqual([
      { text: "Taxus", fields: ["trivial_name", "organism_or_species"], current: true },
      { text: " brevifolia", fields: ["organism_or_species"], current: false },
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

  it("edits a field as lines: one value a line, blanks and repeats out", () => {
    expect(linesOf(["Taxus brevifolia", "Taxus baccata"])).toBe("Taxus brevifolia\nTaxus baccata");
    expect(valuesOf("  Taxus brevifolia \n\n Taxus baccata\r\nTaxus brevifolia\n  ")).toEqual([
      "Taxus brevifolia",
      "Taxus baccata",
    ]);
    // commas belong to the value (IUPAC names have them)
    expect(valuesOf("2,3-dihydroxy-1,4-dione")).toEqual(["2,3-dihydroxy-1,4-dione"]);
  });

  it("tells a value set the server would refuse, from the limits it serves, by the field's label", () => {
    const fields = [
      { key: "Kingdom", label: "Kingdom", max_length: 10 },
      { key: "geo_location", label: "Place", max_length: 348 },
    ];
    expect(valuesProblem({ Kingdom: ["Plantae"] }, fields, LIMITS)).toBeNull();
    expect(valuesProblem({ Kingdom: ["x".repeat(11)] }, fields, LIMITS)).toBe(
      "A value in Kingdom is longer than 10 characters.",
    );
    expect(valuesProblem({ Kingdom: ["x".repeat(10)] }, fields, LIMITS)).toBeNull();
    expect(valuesProblem({ geo_location: Array.from({ length: 201 }, (_, i) => `v${i}`) }, fields, LIMITS)).toBe(
      "Place has more than 200 values.",
    );
    expect(valuesProblem({ geo_location: ["a", "b"] }, fields, { ...LIMITS, max_values_per_field: 1 })).toBe(
      "Place has more than 1 values.",
    );
    // a field the server did not send has no length limit here (its 422 still says so)
    expect(valuesProblem({ trivial_name: ["x".repeat(9999)] }, fields, LIMITS)).toBeNull();
    expect(fieldLabel(fields, "geo_location")).toBe("Place");
    expect(fieldLabel(fields, "constructor")).toBe("constructor");
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
    expect(valuesProblem({ constructor: ["x"] } as unknown as Record<string, string[]>, [], LIMITS)).toBeNull();
  });

  it("caps the values in all at the server's 300", () => {
    const many = (n: number) => Array.from({ length: n }, (_, i) => `v${i}`);
    expect(valuesProblem({ a: many(150), b: many(150) }, [], LIMITS)).toBeNull();
    expect(valuesProblem({ a: many(150), b: many(151) }, [], LIMITS)).toBe(
      "At most 300 values in all (301 now).",
    );
  });
});
