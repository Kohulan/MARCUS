// Landing and info pages in a real browser (F4). Needs `npm run build` and
// `npm run serve:local` only: no API call is made (@mocked). Matomo is answered locally with
// an empty 204, so no test ever reaches the real tracker. Never production.
import { expect, test } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations, routeMatomo } from "./helpers";

const INFO_PAGES = ["/", "/about", "/privacy", "/disclaimer"];

test.describe("landing and info pages @mocked", () => {
  test.beforeEach(async ({ page }) => {
    await routeMatomo(page);
  });

  test("the pre-rendered / has the headline before any script runs", async ({ page }) => {
    await page.route("**/*.js", (route) => route.abort());
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Every molecule has a source.",
    );
    await expect(page.getByText("[01] Structure")).toBeVisible();
  });

  for (const url of INFO_PAGES) {
    test(`${url}: axe finds nothing serious, no CSP violation, no console error`, async ({
      page,
    }) => {
      const violations = collectCspViolations(page);
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
      page.on("console", (msg) => {
        if (msg.type() === "error" || /preload/i.test(msg.text())) {
          errors.push(`console ${msg.type()}: ${msg.text()}`);
        }
      });
      await page.goto(url, { waitUntil: "networkidle" });
      await expectNoA11yViolations(page);
      expect(await violations()).toEqual([]);
      expect(errors).toEqual([]);
    });

    test(`${url}: every preloaded font is used by the page`, async ({ page }) => {
      await page.goto(url, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const unused = await page.evaluate(() => {
        const loaded = performance
          .getEntriesByType("resource")
          .map((e) => e.name)
          .filter((name) => name.endsWith(".woff2"));
        const preloads = [...document.querySelectorAll<HTMLLinkElement>('link[rel="preload"][as="font"]')];
        const faces = [...document.fonts].filter((f) => f.status === "loaded");
        // A preload is used when a loaded face of the same file family and weight exists.
        return preloads
          .map((l) => l.href)
          .filter((href) => {
            const file = href.split("/").pop() ?? "";
            const weight = /-(\d00)-/.exec(file)?.[1] ?? "300";
            const family = file.startsWith("geist-mono")
              ? "Geist Mono"
              : file.startsWith("geist")
                ? "Geist"
                : "Gmarket Sans";
            const used = faces.some(
              (f) => f.family.replace(/"/g, "") === family && f.weight === weight,
            );
            return !(used && loaded.some((name) => name === href));
          });
      });
      expect(unused).toEqual([]);
    });

    test(`${url}: no horizontal scroll at 390 px`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(url, { waitUntil: "networkidle" });
      const [scroll, client] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scroll).toBeLessThanOrEqual(client);
    });
  }

  test("one glass filter, and Upload a PDF refracts in Chromium", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.locator("#marcus-glass")).toHaveCount(1);
    const upload = page.getByRole("link", { name: /^Upload a PDF/ });
    const filter = await upload.evaluate((el) => getComputedStyle(el).backdropFilter);
    expect(filter).toContain("url(");
  });

  // Contract FIRST VIEWPORT: under the hero, the whole headline and both buttons.
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [1280, 800],
    [1024, 768],
  ] as const) {
    test(`${width} × ${height}: the headline and both buttons are in the first viewport`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await page.goto("/", { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { level: 1 })).toBeInViewport({ ratio: 1 });
      await expect(page.getByRole("link", { name: /^Upload a PDF/ })).toBeInViewport({
        ratio: 1,
      });
      await expect(page.getByRole("link", { name: /^Try a sample paper/ })).toBeInViewport({
        ratio: 1,
      });
      await expect(page.getByText("[01] Structure")).toBeInViewport({ ratio: 1 });
    });
  }

  test("a footer link opens the info page at its top", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.getByRole("contentinfo").getByRole("link", { name: "Privacy" }).click();
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });

  test("the Disclaimer's How to cite link lands on the cite section", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/disclaimer", { waitUntil: "networkidle" });
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.getByRole("link", { name: "How to cite" }).click();
    await expect(page).toHaveURL(/\/#cite$/);
    await expect(page.locator("#cite")).toBeInViewport();
  });

  test("each pre-rendered page has its own title", async ({ page }) => {
    const titles: string[] = [];
    for (const url of [...INFO_PAGES, "/nope"]) {
      await page.goto(url);
      titles.push(await page.title());
    }
    expect(new Set(titles).size).toBe(titles.length);
  });

  test("Matomo gets the route template as its page view, never more", async ({ page }) => {
    const hits: string[] = [];
    await page.route("https://matomo.nfdi4chem.de/**", (route) => {
      hits.push(route.request().url());
      return route.fulfill({ status: 204, body: "" });
    });
    await page.goto("/about", { waitUntil: "networkidle" });
    const paq = await page.evaluate(() => JSON.stringify(window._paq ?? null));
    expect(paq).toContain('["setSiteId","7"]');
    expect(paq).toContain('["setCustomUrl","/about"]');
    expect(hits.some((u) => u.endsWith("/matomo.js"))).toBe(true);
  });
});
