// Pins the Survey Sheet foundation (spec §7, owner decisions 2026-11-17): the exact
// light tokens, their WCAG contrast, the self-hosted Geist faces, and that nothing of the
// old Field Sheet world (dark tokens, theme switch, dropped fonts) comes back.
// Vitest runs with `css: false`, so the files are read as text from the project root.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const read = (file: string) => readFileSync(resolve(process.cwd(), "src/styles", file), "utf8");
const stripComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

const tokensCss = stripComments(read("tokens.css"));
const fontsCss = stripComments(read("fonts.css"));
const baseCss = stripComments(read("base.css"));

const EXPECTED_TOKENS: Record<string, string> = {
  "--paper": "#F4F3EA",
  "--surface": "#FFFFFF",
  "--sunken": "#ECEBE1",
  "--ink": "#1C211D",
  "--text-2": "#3F443D",
  "--muted": "#5E625B",
  "--line": "#B9BCB2",
  "--hair": "#D9DACF",
  "--tick": "#9FA398",
  "--green": "#1E4D33",
  "--accepted": "#2D7A46",
  "--orange": "#FA3600",
  "--orange-ink": "#B82800",
  "--on-orange": "#141414",
  "--charcoal": "#1C211D",
  "--control-border": "#7E8279",
  "--hatch": "#E6E5DC",
  "--on-green": "#FFFFFF",
  "--on-charcoal": "#F4F3EA",
  "--selection": "#DCEBDF",
  "--focus": "var(--green)",
  "--font-head": '"Geist", ui-sans-serif, system-ui, sans-serif',
  "--font-text": '"Geist", ui-sans-serif, system-ui, sans-serif',
  "--font-mono": '"Geist Mono", ui-monospace, "SFMono-Regular", Menlo, monospace',
  "--font-mark": '"Gmarket Sans", var(--font-text)',
};

/** Custom properties declared in tokens.css, name → value (whitespace collapsed). */
function declaredTokens(css: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out.set(m[1] as string, (m[2] as string).replace(/\s+/g, " ").trim());
  }
  return out;
}

const tokens = declaredTokens(tokensCss);
const hex = (name: string): string => {
  const value = tokens.get(name);
  if (!value || !/^#[0-9a-f]{6}$/i.test(value)) throw new Error(`${name} is not a hex colour`);
  return value;
};

// WCAG 2.x relative luminance (sRGB) and contrast ratio.
function luminance(colour: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(colour.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("tokens.css", () => {
  it("has one :root block with color-scheme: light", () => {
    expect(tokensCss.match(/:root\b/g)).toHaveLength(1);
    expect(tokensCss).toMatch(/:root\s*\{[^}]*color-scheme:\s*light;/);
  });

  it("declares exactly the Survey Sheet tokens", () => {
    expect([...tokens.keys()].sort()).toEqual(Object.keys(EXPECTED_TOKENS).sort());
  });

  it.each(Object.entries(EXPECTED_TOKENS))("%s is %s", (name, value) => {
    expect(tokens.get(name)).toBe(value);
  });

  it("keeps nothing of the old Field Sheet world", () => {
    for (const css of [tokensCss, baseCss, fontsCss]) {
      for (const gone of [
        "--to-check",
        "--rejected",
        "--failed-bg",
        "--failed-ink",
        "--on-ink",
        "prefers-color-scheme",
        "data-theme",
      ]) {
        expect(css).not.toContain(gone);
      }
    }
  });

  const grounds = ["--paper", "--surface", "--sunken"];

  // accepted is 4.40:1 on sunken (#2D7A46 on #ECEBE1); both values are owner decisions,
  // so accepted is text only on paper and surface (pinned below).
  it.each(
    ["--ink", "--text-2", "--muted", "--green", "--accepted", "--orange-ink"].flatMap((fg) =>
      grounds
        .filter((bg) => !(fg === "--accepted" && bg === "--sunken"))
        .map((bg) => [fg, bg] as const),
    ),
  )("text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it("pins the one exception: accepted on sunken is below 4.5:1 (never text there)", () => {
    expect(contrast(hex("--accepted"), hex("--sunken"))).toBeLessThan(4.5);
  });

  it.each([
    ["--on-orange", "--orange"],
    ["--on-green", "--green"],
    ["--on-charcoal", "--charcoal"],
  ] as const)("text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ...grounds.map((bg) => ["--control-border", bg] as const),
    ["--orange", "--paper"] as const,
    ["--orange", "--surface"] as const,
  ])("shape %s on %s is at least 3:1", (fg, bg) => {
    expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(3);
  });
});

describe("fonts.css", () => {
  const faces = [...fontsCss.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((m) => m[1] as string);
  const prop = (face: string, name: string) =>
    face.match(new RegExp(`${name}\\s*:\\s*([^;]+);`))?.[1]?.trim().replace(/^"|"$/g, "");

  it("has five faces, each with font-display: swap", () => {
    expect(faces).toHaveLength(5);
    for (const face of faces) expect(prop(face, "font-display")).toBe("swap");
  });

  it("names only Geist, Geist Mono and Gmarket Sans, at most two weights each", () => {
    const weights = new Map<string, Set<string>>();
    for (const face of faces) {
      const family = prop(face, "font-family") ?? "";
      const set = weights.get(family) ?? new Set<string>();
      set.add(prop(face, "font-weight") ?? "");
      weights.set(family, set);
    }
    expect([...weights.keys()].sort()).toEqual(["Geist", "Geist Mono", "Gmarket Sans"]);
    for (const set of weights.values()) expect(set.size).toBeLessThanOrEqual(2);
    expect([...(weights.get("Geist") ?? [])].sort()).toEqual(["400", "700"]);
    expect([...(weights.get("Geist Mono") ?? [])].sort()).toEqual(["400", "500"]);
  });

  it("loads the latin files of @fontsource/geist and @fontsource/geist-mono", () => {
    for (const file of [
      "@fontsource/geist/files/geist-latin-400-normal.woff2",
      "@fontsource/geist/files/geist-latin-700-normal.woff2",
      "@fontsource/geist-mono/files/geist-mono-latin-400-normal.woff2",
      "@fontsource/geist-mono/files/geist-mono-latin-500-normal.woff2",
      "/fonts/gmarket-mark.woff2",
    ]) {
      expect(fontsCss).toContain(`url("${file}")`);
    }
    expect(fontsCss).toMatch(/unicode-range:\s*U\+0041, U\+0043, U\+004D, U\+0052, U\+0053, U\+0055;/);
  });

  it("uses no file of the dropped font packages", () => {
    expect(fontsCss).not.toMatch(/bricolage|hanken|jetbrains/i);
  });
});

describe("base.css", () => {
  it("defines the sheet primitives", () => {
    for (const cls of [".sheet", ".ticks", ".vticks", ".corner", ".mono-label", ".hatch", ".strike"]) {
      expect(baseCss).toMatch(new RegExp(`\\${cls}\\s*[{,]`));
    }
  });

  it("draws ruler ticks with --tick, 1 px every 8 px", () => {
    expect(baseCss).toContain(
      "repeating-linear-gradient(90deg, var(--tick) 0 1px, transparent 1px 8px)",
    );
    expect(baseCss).toContain(
      "repeating-linear-gradient(180deg, var(--tick) 0 1px, transparent 1px 8px)",
    );
  });

  it("hatches at 135° with --hatch 0–6 px and --paper 6–12 px", () => {
    expect(baseCss).toContain(
      "repeating-linear-gradient(135deg, var(--hatch) 0 6px, var(--paper) 6px 12px)",
    );
  });

  it("keeps the reduced-motion block", () => {
    expect(baseCss).toContain("@media (prefers-reduced-motion: reduce)");
  });
});
