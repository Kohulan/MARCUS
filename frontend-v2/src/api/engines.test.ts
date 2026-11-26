// imageLayout: the same verdicts as the tools worker (backend workers/orient.py image_layout,
// tests/workers/test_orient.py) on the same real engine output.
import { backendFixture } from "../test/backendFixture";
import { describe, expect, it } from "vitest";
import { paperLayout } from "../test/paperLayout";
import {
  asEngine,
  engineName,
  ENGINES,
  imageLayout,
  isLegacyEngine,
  layoutInfo,
  layoutPrediction,
  orientationTemplate,
  TEMPLATE_ENGINES,
} from "./engines";
import type { PredictionOut } from "./types";

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

describe("offered and legacy engines", () => {
  it("the menu offers MolParser, never the legacy MolNexTR", () => {
    expect(ENGINES.map((e) => e.value)).toEqual(["decimer", "decimer-hand", "molparser", "molscribe"]);
    expect(ENGINES.map((e) => e.value)).not.toContain("molnextr");
  });

  it("old papers' MolNexTR keeps its name but is not an offered engine", () => {
    expect(engineName("molnextr")).toBe("MolNexTR");
    expect(engineName("molparser")).toBe("MolParser");
    expect(engineName("fake")).toBe("fake");
    expect(asEngine("molnextr")).toBeNull();
    expect(asEngine("molparser")).toBe("molparser");
    expect(isLegacyEngine("molnextr")).toBe(true);
    expect(isLegacyEngine("molparser")).toBe(false);
  });

  it("MolParser is no template engine (its molfile is a computed layout)", () => {
    expect(TEMPLATE_ENGINES).not.toContain("molparser");
  });
});

describe("the paper layout", () => {
  const pred = (over: Partial<PredictionOut>): PredictionOut => ({
    id: "p",
    engine: "molscribe",
    engine_version: "1",
    smiles: "CC",
    molfile: null,
    valid: true,
    ms: 1,
    cached: false,
    created_at: "2026-11-26T00:00:00Z",
    ...over,
  });

  it("reads the title line; the overlay needs a fit within 4 % of a bond", () => {
    expect(layoutInfo(paperLayout(0.5, 40))).toEqual({ fit: 0.5, bond: 40, width: 400, height: 300, overlay: true });
    expect(layoutInfo(paperLayout(1.6, 40))?.overlay).toBe(true);
    expect(layoutInfo(paperLayout(1.7, 40))?.overlay).toBe(false);
    for (const other of [null, undefined, "", "\n  RDKit\n", "MARCUS layout fit=x bond=1 size=1x1"]) {
      expect(layoutInfo(other)).toBeNull();
    }
  });

  it("is never taken for a computed layout (a printed ring has bonds of one length)", () => {
    const layout = paperLayout();
    expect(imageLayout(layout)).toBe(true);
    expect(imageLayout("\n" + layout.slice(layout.indexOf("\n") + 1))).toBe(false);
  });

  it("is the first template, also of an invalid MolScribe; its key differs from the molfile's", () => {
    const layout = paperLayout();
    const invalid = pred({ id: "bad", valid: false, molfile: "computed", layout });
    expect(layoutPrediction([pred({ id: "new" }), invalid])).toBe(invalid);
    expect(layoutPrediction([pred({ engine: "molparser", layout })])).toBeNull();
    expect(orientationTemplate([invalid])).toEqual({ id: "bad:layout", molfile: layout });
    // Use coordinates off for MolScribe: no layout either
    expect(orientationTemplate([invalid], { molscribe: false })).toBeNull();
    expect(orientationTemplate([pred({ engine: "decimer" })])).toBeNull();
  });
});
