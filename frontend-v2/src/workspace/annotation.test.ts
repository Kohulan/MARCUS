import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import type { AnnotationOut, StepOut } from "../api/types";
import {
  annotateReason,
  annotationError,
  blockRanges,
  FIELD_MAX,
  hitsOf,
  linesOf,
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

  it("collects the ranges of every shown value per block, in first-seen order", () => {
    const positions = {
      organism_or_species: { "Taxus brevifolia": [[2, 10, 26], [0, 4, 20]] as [number, number, number][] },
      organism_part: { bark: [[0, 30, 34]] as [number, number, number][], gone: [] },
      geo_location: { China: [[0, 40, 45]] as [number, number, number][] },
    };
    const values = { organism_or_species: ["Taxus brevifolia"], organism_part: ["bark", "gone"] };
    const ranges = blockRanges(values, positions);
    // China is in the positions but not a shown value: not highlighted
    expect([...ranges.entries()]).toEqual([
      [2, [[10, 26]]],
      [0, [[4, 20], [30, 34]]],
    ]);
  });

  it("splits a block's text into plain and marked pieces, overlaps merged", () => {
    const text = "The bark of Taxus brevifolia was used.";
    expect(splitMarks(text, [[12, 28], [12, 17], [4, 8]], null)).toEqual([
      { text: "The ", mark: false, current: false },
      { text: "bark", mark: true, current: false },
      { text: " of ", mark: false, current: false },
      { text: "Taxus brevifolia", mark: true, current: false },
      { text: " was used.", mark: false, current: false },
    ]);
  });

  it("marks the current occurrence apart from the others", () => {
    const text = "Taxus brevifolia bark";
    expect(splitMarks(text, [[0, 16], [17, 21]], [0, 5])).toEqual([
      { text: "Taxus", mark: true, current: true },
      { text: " brevifolia", mark: true, current: false },
      { text: " ", mark: false, current: false },
      { text: "bark", mark: true, current: false },
    ]);
  });

  it("ignores ranges outside the text (a stale position never throws)", () => {
    expect(splitMarks("abc", [[1, 99], [7, 9], [2, 1]], null)).toEqual([
      { text: "a", mark: false, current: false },
      { text: "bc", mark: true, current: false },
    ]);
    expect(splitMarks("", [], null)).toEqual([]);
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
      [0, [[0, 9]]],
      [1, [[2, 13]]],
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
    expect(annotationError(new ApiError(503, "The server is busy, try again in a moment."))).toBe(
      "The server is busy, try again in a moment.",
    );
    expect(annotationError(new ApiError(422, "Value error, too many values"))).toBe(
      "Value error, too many values",
    );
    expect(annotationError(new Error("x"))).toBe("Something went wrong.");
  });
});
