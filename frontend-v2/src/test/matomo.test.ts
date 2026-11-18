// public/matomo.js: the referrer Matomo records never carries a MARCUS path (a paper or image
// id). A same-origin referrer is cut to the origin; another site's referrer is left as it is.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const CODE = readFileSync(join(process.cwd(), "public", "matomo.js"), "utf8");

function run(referrer: string): unknown[][] {
  Object.defineProperty(document, "referrer", { configurable: true, get: () => referrer });
  delete window._paq;
  new Function(CODE)();
  return (window._paq ?? []) as unknown[][];
}

afterEach(() => {
  delete window._paq;
  Object.defineProperty(document, "referrer", { configurable: true, get: () => "" });
  for (const s of document.head.querySelectorAll("script")) s.remove();
});

describe("matomo.js", () => {
  it("cuts a same-origin referrer (a paper page) to the origin", () => {
    const origin = window.location.origin;
    const paq = run(`${origin}/app/papers/3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f?view=paper`);
    expect(paq).toContainEqual(["setReferrerUrl", `${origin}/`]);
    expect(JSON.stringify(paq)).not.toContain("3f2a9c1e");
  });

  it("leaves another site's referrer and an empty one alone", () => {
    expect(run("https://www.example.org/search?q=marcus").map((c) => c[0])).not.toContain(
      "setReferrerUrl",
    );
    expect(run("").map((c) => c[0])).not.toContain("setReferrerUrl");
  });

  it("still sets the tracker and site 7", () => {
    const paq = run("");
    expect(paq).toContainEqual(["setTrackerUrl", "https://matomo.nfdi4chem.de/matomo.php"]);
    expect(paq).toContainEqual(["setSiteId", "7"]);
  });
});
