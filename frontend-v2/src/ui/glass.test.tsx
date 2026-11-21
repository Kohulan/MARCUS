// Glass buttons (spec §7 decision 4, Global Constraints "Glass buttons"): the markup, the
// one refraction filter in every pre-rendered page, the CSS fallbacks, and WCAG AA text on
// every tint, computed from the gradient stops in glass.css blended over paper and surface.
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { render as renderPage } from "../entry-server";
import { GlassButton, GlassLink } from "./GlassButton";

const glassCss = readFileSync(resolve(process.cwd(), "src/ui/glass.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);
/** Whitespace removed and "0.9" written ".9", so stops compare as the board writes them. */
const flat = glassCss.replace(/\s+/g, "").replace(/([(,])0\./g, "$1.");

describe("GlassButton and GlassLink", () => {
  it("a button with the glass classes and type=button by default", () => {
    expect(renderToStaticMarkup(<GlassButton tint="orange">Upload a PDF</GlassButton>)).toBe(
      '<button type="button" class="glass glass--orange">Upload a PDF</button>',
    );
  });

  it("small size and submit type", () => {
    render(
      <GlassButton tint="green" size="sm" type="submit">
        Save
      </GlassButton>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "submit");
    expect(button).toHaveAttribute("class", "glass glass--green glass--sm");
  });

  it("disabled sets disabled", () => {
    render(
      <GlassButton tint="clear" disabled>
        Export
      </GlassButton>,
    );
    expect(screen.getByRole("button", { name: "Export" })).toBeDisabled();
  });

  it("GlassLink is an <a href> with the same classes", () => {
    render(
      <MemoryRouter>
        <GlassLink tint="clear" to="/app">
          Try a sample paper
        </GlassLink>
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Try a sample paper" });
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", "/app");
    expect(link).toHaveAttribute("class", "glass glass--clear");
  });
});

describe("the refraction filter", () => {
  it("is in the pre-rendered landing exactly once, with no style attribute", () => {
    const html = renderPage("/");
    expect(html.split('id="marcus-glass"').length - 1).toBe(1);
    expect(html).not.toContain(" style=");
    expect(html).toContain('class="glass-defs"');
  });

  it("carries the board's values", () => {
    const html = renderPage("/");
    for (const attr of [
      'baseFrequency="0.012 0.03"',
      'numOctaves="2"',
      'seed="7"',
      'stdDeviation="2"',
      'scale="18"',
      'xChannelSelector="R"',
      'yChannelSelector="G"',
    ]) {
      expect(html).toContain(attr);
    }
  });
});

describe("glass.css", () => {
  it("refracts where supported and falls back everywhere else", () => {
    expect(glassCss).toContain("url(#marcus-glass)");
    expect(glassCss).toContain("prefers-reduced-transparency");
    expect(glassCss).toContain("@supports not");
    expect(glassCss).toContain("forced-colors");
    expect(glassCss).toContain("-webkit-backdrop-filter");
  });

  it("declares the refraction after the plain blur (a browser that rejects it keeps blur)", () => {
    const plain = flat.indexOf("backdrop-filter:blur(3px)saturate(1.8)");
    const refract = flat.indexOf("backdrop-filter:url(#marcus-glass)blur(3px)saturate(1.8)");
    expect(plain).toBeGreaterThanOrEqual(0);
    expect(refract).toBeGreaterThan(plain);
  });

  it.each([
    "rgba(255,118,72,.95)",
    "rgba(250,54,0,.9)",
    "rgba(46,110,74,.95)",
    "rgba(30,77,51,.92)",
    "rgba(255,255,255,.7)",
    "rgba(255,255,255,.25)",
  ])("has the board stop %s", (stop) => {
    expect(flat).toContain(stop);
  });
});

// WCAG 2.x contrast.
type RGB = [number, number, number];
const hexRgb = (hex: string): RGB => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const channel = (c: number) => {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]: RGB) =>
  0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
const contrast = (a: RGB, b: RGB) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
};
const blend = ([r, g, b, a]: [number, number, number, number], [br, bg, bb]: RGB): RGB => [
  r * a + br * (1 - a),
  g * a + bg * (1 - a),
  b * a + bb * (1 - a),
];

/** The rgba() stops of the first rule for `selector` in glass.css. */
function stops(selector: string): [number, number, number, number][] {
  const rule = new RegExp(`${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`).exec(glassCss);
  if (!rule) throw new Error(`${selector} not found in glass.css`);
  const found = [...(rule[1] as string).matchAll(/rgba\(([^)]+)\)/g)].map(
    (m) => (m[1] as string).split(",").map(Number) as [number, number, number, number],
  );
  if (found.length !== 2) throw new Error(`${selector}: expected 2 gradient stops`);
  return found;
}

const PAPER = hexRgb("#F4F3EA");
const SURFACE = hexRgb("#FFFFFF");

describe("text on every tint is WCAG AA (4.5:1) over paper and surface", () => {
  const tints: [string, string, string][] = [
    // [selector, text colour, solid fallback]
    [".glass--orange", "#141414", "#FA3600"],
    [".glass--green", "#FFFFFF", "#1E4D33"],
    [".glass--clear", "#1C211D", "#FFFFFF"],
  ];

  it.each(tints)("%s glass", (selector, text) => {
    for (const stop of stops(selector)) {
      for (const ground of [PAPER, SURFACE]) {
        expect(contrast(hexRgb(text), blend(stop, ground))).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(tints)("%s solid fallback", (_selector, text, solid) => {
    expect(contrast(hexRgb(text), hexRgb(solid))).toBeGreaterThanOrEqual(4.5);
  });

  it("the solid fallbacks in glass.css are the solid tokens", () => {
    expect(flat).toContain("background:var(--orange)");
    expect(flat).toContain("background:var(--green)");
    expect(flat).toContain("background:var(--surface)");
  });
});
