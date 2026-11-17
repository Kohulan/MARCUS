// Shared e2e helpers. e2e runs against the local nginx (`npm run serve:local`) in front of
// the fake stack, never production.
import { readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

declare global {
  interface Window {
    __cspViolations?: string[];
  }
}

/**
 * Starts collecting CSP violations in the page and in every frame it opens.
 * Call before the first `page.goto`. The returned function reads what was collected so far:
 * `securitypolicyviolation` events from every frame's document, plus the browser's own
 * "Refused to …" console reports from the page, its frames and its workers (a dedicated
 * worker runs under its own CSP and reports there, not to a document).
 */
export function collectCspViolations(page: Page): () => Promise<string[]> {
  const fromConsole: string[] = [];
  const isCsp = (text: string) => /Content Security Policy|Refused to/i.test(text);
  page.on("console", (msg) => {
    if (isCsp(msg.text())) fromConsole.push(`console: ${msg.text()}`);
  });
  page.on("worker", (worker) => {
    worker.on("console", (msg) => {
      if (isCsp(msg.text())) fromConsole.push(`worker ${worker.url()}: ${msg.text()}`);
    });
  });

  // addInitScript runs in every frame of the page, iframes included, before their scripts.
  const ready = page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      window.__cspViolations?.push(
        `${e.violatedDirective} blocked=${e.blockedURI || "(inline)"} ` +
          `at ${e.sourceFile}:${e.lineNumber} in ${document.location.pathname}`,
      );
    });
  });

  return async () => {
    await ready;
    const out: string[] = [];
    for (const frame of page.frames()) {
      try {
        out.push(...(await frame.evaluate(() => window.__cspViolations ?? [])));
      } catch {
        // A frame that navigated away or closed has nothing left to read.
      }
    }
    return [...out, ...fromConsole];
  };
}

/**
 * Uploads a PDF through the API with the page's own cookies (`page.request` shares the
 * browser context's cookie jar, so the paper belongs to the page's owner).
 * Returns the paper id. `engine` defaults to "fake" (the only engine the fake stack reads).
 */
export async function uploadPaperViaApi(
  page: Page,
  file: string,
  opts: { engine?: "fake"; ocsr?: "auto" | "off" } = {},
): Promise<string> {
  const path = resolve(file);
  const response = await page.request.post("/api/v2/papers", {
    multipart: {
      file: { name: basename(path), mimeType: "application/pdf", buffer: await readFile(path) },
      engine: opts.engine ?? "fake",
      ocsr: opts.ocsr ?? "auto",
    },
  });
  expect(response.status(), await response.text()).toBe(202);
  const body = (await response.json()) as { paper_id: string };
  return body.paper_id;
}

/** Runs axe on the current page (light mode only); fails on any serious or critical violation. */
export async function expectNoA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const bad = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
  expect(bad, bad.join("\n")).toEqual([]);
}
