import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

// Vitest runs from the project root (frontend-v2/).
const source = readFileSync(resolve(process.cwd(), "public/theme.js"), "utf8");

function runThemeScript() {
  // Same as the browser: a classic script evaluated in the page's global scope.
  new Function(source)();
}

afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

describe("public/theme.js", () => {
  it("does not throw when localStorage itself throws on access", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(runThemeScript).not.toThrow();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("does not throw when getItem throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(runThemeScript).not.toThrow();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it('sets data-theme="dark" when "dark" is stored', () => {
    localStorage.setItem("marcus-theme", "dark");
    runThemeScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it('sets data-theme="light" when "light" is stored', () => {
    localStorage.setItem("marcus-theme", "light");
    runThemeScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("ignores any other stored value", () => {
    localStorage.setItem("marcus-theme", "\"><img src=x>");
    runThemeScript();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
