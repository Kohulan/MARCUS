// Pins the Survey Sheet foundation (spec §7, owner decisions 2026-11-17): the exact
// light tokens, their WCAG contrast, the self-hosted Geist faces, and that nothing of the
// old Field Sheet world (dark tokens, theme switch, dropped fonts) comes back.
// Vitest runs with `css: false`, so the files are read as text from the project root.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
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
  "--lift-glass": "0 10px 24px -8px rgba(15, 30, 22, 0.35)",
  "--lift-menu": "0 12px 28px -10px rgba(15, 30, 22, 0.35)",
  "--lift-dialog": "0 24px 64px -24px rgba(15, 30, 22, 0.45)",
  "--lift-pill-solid": "0 6px 16px -8px rgba(15, 30, 22, 0.35)",
  "--glass-shine":
    "inset 0 1.5px 0 rgba(255, 255, 255, 0.9), inset 0 -2px 3px rgba(255, 255, 255, 0.3), " +
    "inset 0 0 0 1px rgba(255, 255, 255, 0.45), inset 0 -12px 18px -12px rgba(0, 0, 0, 0.22)",
  "--scrim": "rgba(28, 33, 29, 0.42)",
  "--porcelain":
    "inset 0 1px 0 #FFFFFF, inset 0 -1.5px 2px rgba(28, 33, 29, 0.1), " +
    "inset 0 0 0 1px rgba(28, 33, 29, 0.07), 0 1px 1px rgba(15, 30, 22, 0.1), " +
    "0 8px 16px -10px rgba(15, 30, 22, 0.45)",
  "--water-drop":
    "inset 0 1.5px 0 rgba(255, 255, 255, 0.9), inset 0 0 0 1px rgba(255, 255, 255, 0.35), " +
    "inset 0 -8px 10px -8px rgba(30, 77, 51, 0.55), 0 5px 10px -7px rgba(15, 30, 22, 0.45)",
  // The spacing table of the landing-page-design skill (B2), and its one motion curve (B7)
  "--s-25": "2px",
  "--s-50": "4px",
  "--s-75": "8px",
  "--s-100": "12px",
  "--s-200": "16px",
  "--s-300": "24px",
  "--s-400": "32px",
  "--s-500": "40px",
  "--s-600": "48px",
  "--s-700": "64px",
  "--s-800": "80px",
  "--s-900": "96px",
  "--ease": "cubic-bezier(0.22, 1, 0.36, 1)",
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

/** Every stylesheet under src/ but tokens.css, path → text without comments. */
function sheets(): [string, string][] {
  const root = resolve(process.cwd(), "src");
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".css") && entry.name !== "tokens.css") {
        out.push([relative(root, path), stripComments(readFileSync(path, "utf8"))]);
      }
    }
  };
  walk(root);
  return out;
}

// DESIGN.md Elevation: one lift per kind of floating object and one scrim, all tokens.
describe("elevation", () => {
  const all = sheets();

  it("finds the stylesheets", () => {
    expect(all.length).toBeGreaterThan(10);
  });

  it("no box-shadow outside tokens.css carries a colour literal", () => {
    const bad = all.flatMap(([file, css]) =>
      [...css.matchAll(/box-shadow\s*:\s*([^;]+);/g)]
        .filter((m) => /rgba?\(|#[0-9a-f]{3,8}\b/i.test(m[1] as string))
        .map((m) => `${file}: ${(m[1] as string).replace(/\s+/g, " ").trim()}`),
    );
    expect(bad).toEqual([]);
  });

  it("every dialog backdrop is the one scrim", () => {
    const backdrops = all.flatMap(([file, css]) =>
      [...css.matchAll(/::backdrop\s*\{([^}]*)\}/g)]
        .map((m) => [file, m[1] as string] as const)
        .filter(([, body]) => /background/.test(body)),
    );
    expect(backdrops.length).toBeGreaterThanOrEqual(4); // editor, COCONUT, Compare, Keys
    for (const [file, body] of backdrops) {
      expect(body, file).toMatch(/background-color:\s*var\(--scrim\);/);
    }
  });
});

// The landing, its header and footer move by transform and opacity only (skill B7).
describe("motion on the landing, the header and the footer", () => {
  const src = (file: string) =>
    stripComments(readFileSync(resolve(process.cwd(), "src", file), "utf8"));
  const transitions = (css: string) =>
    [...css.matchAll(/transition\s*:\s*([^;]+);/g)].map((m) => (m[1] as string).trim());

  it.each(["ui/ui.css", "pages/landing.css"])("%s never transitions a layout property", (file) => {
    for (const t of transitions(src(file))) {
      expect(t).not.toMatch(/\b(left|right|top|bottom|width|height|all)\b/);
    }
  });
});
