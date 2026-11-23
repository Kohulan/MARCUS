// imageLayout: the same verdicts as the tools worker (backend workers/orient.py image_layout,
// tests/workers/test_orient.py) on the same real engine output.
import { backendFixture } from "../test/backendFixture";
import { describe, expect, it } from "vitest";
import { imageLayout } from "./engines";

type Out = { smiles: string; molfile: string | null };
const fixture = (name: string) => backendFixture<Record<string, Record<string, Out> | Out | string>>(name);

const real = fixture("orient_engines.json") as Record<string, Record<string, Out>>;
const fixed = fixture("molnextr_7a4e03f.json");

describe("imageLayout", () => {
  it.each(Object.keys(real).flatMap((crop) => ["molnextr", "molscribe"].map((engine) => [crop, engine])))(
    "%s %s: only positions from the image count",
    (crop, engine) => {
      const fromImage = engine === "molscribe" && (crop === "p2_6" || crop === "p2_10");
      expect(imageLayout(real[crop]![engine]!.molfile!)).toBe(fromImage);
    },
  );

  it("takes the fixed MolNexTR's molfiles (7a4e03f)", () => {
    for (const crop of ["corallomycetellains_p3_3", "stylissa-bromopyrroles_p6_2"]) {
      expect(imageLayout((fixed[crop] as Out).molfile!)).toBe(true);
    }
  });

  it("a molfile it cannot read is not one", () => {
    expect(imageLayout("")).toBe(false);
    expect(imageLayout("<nextr>")).toBe(false);
    expect(imageLayout("\n\n\n  1  0  0  0  0  0  0  0  0  0999 V3000\n")).toBe(false);
  });
});
