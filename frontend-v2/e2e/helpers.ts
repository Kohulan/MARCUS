// Shared e2e helpers. e2e runs against the local nginx (`npm run serve:local`) in front of
// the fake stack, never production.
import { readFile } from "node:fs/promises";
import { basename, extname, resolve } from "node:path";
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
 * Answers every request to the Matomo host with an empty 204, so a test never reaches the
 * real tracker (and never counts as a visit). Call before the first `page.goto`.
 */
export async function routeMatomo(page: Page): Promise<void> {
  await page.route("https://matomo.nfdi4chem.de/**", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
}

const MIME: Record<string, string> = {
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".webp": "image/webp",
};

/** The upload's media type from its extension (the types the API accepts). */
export function mimeTypeOf(file: string): string {
  const type = MIME[extname(file).toLowerCase()];
  if (!type) throw new Error(`no upload type for ${file}`);
  return type;
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
      file: { name: basename(path), mimeType: mimeTypeOf(path), buffer: await readFile(path) },
      engine: opts.engine ?? "fake",
      ocsr: opts.ocsr ?? "auto",
    },
  });
  expect(response.status(), await response.text()).toBe(202);
  const body = (await response.json()) as { paper_id: string };
  return body.paper_id;
}

/**
 * Runs axe on the current page (light mode only); fails on any serious or critical violation.
 * `exclude`: CSS selectors axe leaves out (the Ketcher frame: a third-party editor page).
 * `tags`: run only the rules with these tags (axe's default set leaves target-size off).
 */
export async function expectNoA11yViolations(
  page: Page,
  opts: { exclude?: string[]; tags?: string[] } = {},
): Promise<void> {
  // Contrast is judged at rest: wait for the running finite animations (a dialog's fade-in)
  // to end, so axe never measures text halfway through an opacity fade. Endless loops (a
  // spinner, the ring's arrow) are left alone.
  await page.evaluate(() =>
    Promise.race([
      Promise.allSettled(
        document
          .getAnimations()
          .filter((a) => a.playState === "running" && a.effect?.getTiming().iterations !== Infinity)
          .map((a) => a.finished),
      ),
      new Promise((done) => setTimeout(done, 3000)),
    ]),
  );
  let axe = new AxeBuilder({ page });
  if (opts.tags) axe = axe.withTags(opts.tags);
  for (const selector of opts.exclude ?? []) axe = axe.exclude(selector);
  const results = await axe.analyze();
  const bad = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
  expect(bad, bad.join("\n")).toEqual([]);
}
