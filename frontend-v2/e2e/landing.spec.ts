// Landing and info pages in a real browser (F4). Needs `npm run build` and
// `npm run serve:local` only: no API call is made (@mocked). Matomo is answered locally with
// an empty 204, so no test ever reaches the real tracker. Never production.
import { expect, test } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations, routeMatomo } from "./helpers";

const INFO_PAGES = ["/", "/about", "/privacy", "/disclaimer"];
const HEADLINE = "Molecular Annotation and Recognition for Curating Unravelled Structures";

test.describe("landing and info pages @mocked", () => {
  test.beforeEach(async ({ page }) => {
    await routeMatomo(page);
  });

  test("the pre-rendered / has the headline before any script runs", async ({ page }) => {
    await page.route("**/*.js", (route) => route.abort());
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveAccessibleName(HEADLINE);
    await expect(page.getByRole("button", { name: /^Drop a PDF here or browse/ })).toBeVisible();
    await expect(page.getByText("Every molecule has a source")).toHaveCount(0);
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

  test("one glass filter, and Try a sample paper refracts in Chromium", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.locator("#marcus-glass")).toHaveCount(1);
    const sample = page.getByRole("link", { name: /^Try a sample paper/ });
    const filter = await sample.evaluate((el) => getComputedStyle(el).backdropFilter);
    expect(filter).toContain("url(");
  });

  // The first screen: the name, the drop zone and the sample pill in the first viewport.
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [1280, 800],
    [1280, 720],
    [1024, 768],
  ] as const) {
    test(`${width} × ${height}: the name, the drop zone and the sample pill are in the first viewport`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await page.goto("/", { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { level: 1 })).toBeInViewport({ ratio: 1 });
      await expect(page.getByRole("button", { name: /^Drop a PDF here/ })).toBeInViewport({
        ratio: 1,
      });
      await expect(page.getByRole("link", { name: /^Try a sample paper/ })).toBeInViewport({
        ratio: 1,
      });
    });
  }

  // The name: each initial is copied out of the header's MARCUS and falls to its line
  // (src/pages/flight.ts). The copies start on the header's letters; at the end they are gone
  // and the name is its layout, as it is under reduced motion (no flight at all).
  for (const [width, height] of [
    [1440, 900],
    [390, 844],
  ] as const) {
    test(`${width} × ${height}: the initials fall from the header's MARCUS and end on the layout`, async ({
      browser,
    }) => {
      // the flight's animations (the copies, the initials, the rests): hold at a time, or
      // run to the end (null); returns how many there are
      const flight = (at: number | null) => {
        const all = document.getAnimations().filter((a) => {
          const el = (a.effect as KeyframeEffect | null)?.target;
          return el instanceof Element && el.closest(".acro-flight, .acro") !== null;
        });
        for (const a of all) {
          if (at === null) a.finish();
          else {
            a.pause();
            a.currentTime = at;
          }
        }
        return all.length;
      };
      // the glyphs' own boxes (text ranges), whatever box the element draws
      const glyphs = () =>
        [...document.querySelectorAll(".acro b, .acro .acro__rest")].map((el) => {
          const range = document.createRange();
          range.selectNodeContents(el);
          const r = range.getBoundingClientRect();
          return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width) };
        });
      const open = async (reducedMotion: "reduce" | "no-preference") => {
        const page = await browser.newPage({ viewport: { width, height }, reducedMotion });
        await routeMatomo(page);
        await page.goto("/", { waitUntil: "commit" });
        return page;
      };

      const still = await open("reduce");
      await still.waitForLoadState("load");
      await still.evaluate(() => document.fonts.ready);
      await still.waitForTimeout(1000);
      expect(await still.locator(".acro-fly").count()).toBe(0);
      const layout = await still.evaluate(glyphs);
      await still.close();

      const page = await open("no-preference");
      await expect(page.locator(".acro-fly")).toHaveCount(6);
      expect(await page.evaluate(flight, 0)).toBeGreaterThan(0);
      // at lift-off each copy's wordmark letter sits on its letter in the header's MARCUS
      const starts = await page.evaluate(() => {
        const word = document.querySelector(".site-header__word")!;
        const text = word.firstChild as Text;
        const spacing = parseFloat(getComputedStyle(word).letterSpacing) || 0;
        const range = document.createRange();
        return [...document.querySelectorAll(".acro-fly__mark")].map((mark, i) => {
          range.setStart(text, i);
          range.setEnd(text, i + 1);
          const [h, c] = [range.getBoundingClientRect(), mark.getBoundingClientRect()];
          return { dx: c.left + c.width / 2 - (h.left + (h.width - spacing) / 2) };
        });
      });
      for (const s of starts) expect(Math.abs(s.dx)).toBeLessThanOrEqual(1);
      // the initials wait hidden until their copies land
      const hidden = await page.$$eval(".acro b", (els) =>
        els.map((el) => getComputedStyle(el).opacity),
      );
      expect(hidden.every((o) => o === "0")).toBe(true);

      await page.evaluate(flight, null);
      await expect(page.locator(".acro-flight")).toHaveCount(0);
      expect(await page.evaluate(glyphs)).toEqual(layout);
      await page.close();
    });
  }

  test("the first Tab reaches Skip to content, which leads past the header", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/about", { waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport({ ratio: 1 });
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    const inHeader = await page.evaluate(
      () => !!document.activeElement?.closest(".site-header"),
    );
    expect(inHeader).toBe(false);
    expect(
      await page.evaluate(() => !!document.activeElement?.closest("main")),
    ).toBe(true);
  });

  test("at 390 px the sample pill comes before the ring, in the first screen", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "networkidle" });
    const pill = page.getByRole("link", { name: /^Try a sample paper/ });
    await expect(pill).toBeInViewport({ ratio: 1 });
    const [pillTop, ringTop] = await Promise.all([
      pill.evaluate((el) => el.getBoundingClientRect().top),
      page.locator(".dz__ring").evaluate((el) => el.getBoundingClientRect().top),
    ]);
    expect(pillTop).toBeLessThan(ringTop);
  });

  test("the beams draw on the canvas, and one still frame under reduced motion", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/", { waitUntil: "networkidle" });
    const drawn = await page.locator("canvas.beams").evaluate((el) => {
      const cv = el as HTMLCanvasElement;
      const data = cv.getContext("2d")!.getImageData(0, 0, cv.width, cv.height).data;
      let ink = 0;
      for (let i = 3; i < data.length; i += 4) if (data[i]! > 0) ink++;
      return { ink, width: cv.width, cssWidth: cv.clientWidth };
    });
    expect(drawn.ink).toBeGreaterThan(0);
    expect(drawn.width).toBeLessThan(drawn.cssWidth / 2); // drawn small, blurred in CSS
  });

  test("a file that is not a PDF is refused on the landing, with no request", async ({ page }) => {
    const api: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/")) api.push(r.url());
    });
    await page.goto("/", { waitUntil: "networkidle" });
    await page.locator('.act input[type="file"]').setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a pdf"),
    });
    await expect(page.locator(".act").getByRole("alert")).toHaveText("That file is not a PDF");
    await expect(page.locator(".dz")).toHaveClass(/is-error/);
    await expect(page).toHaveURL(/\/$/);
    expect(api).toEqual([]);
  });

  test("the header floats free; the nav marks the current page with the drop", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/about", { waitUntil: "networkidle" });
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: "About" })).toHaveAttribute("aria-current", "page");
    await expect(nav).toHaveClass(/has-drop/);
    await expect(page.locator(".site-header")).toHaveCSS("border-bottom-width", "0px");
    await expect(page.locator(".sheet__page")).toHaveCSS("border-top-width", "1px");
    // arrow keys walk the items
    await nav.getByRole("link", { name: "About" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(nav.getByRole("link", { name: /^GitHub/ })).toBeFocused();
    await page.keyboard.press("End");
    await expect(nav.getByRole("link", { name: "Open the tool" })).toBeFocused();
  });

  test("from 1200 px the footer bubbles stick to the bottom and rest under the page at its end", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/about", { waitUntil: "networkidle" });
    const footer = page.getByRole("contentinfo");
    await expect(footer).toBeInViewport();
    const bottom = await footer.evaluate((el) => el.getBoundingClientRect().bottom);
    expect(bottom).toBeLessThanOrEqual(900 - 11);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const [pageEnd, footerTop] = await page.evaluate(() => [
      document.querySelector(".sheet__page")!.getBoundingClientRect().bottom,
      document.querySelector(".site-footer")!.getBoundingClientRect().top,
    ]);
    expect(footerTop).toBeGreaterThanOrEqual(pageEnd);
  });

  // WCAG 2.4.11: Tab never puts focus under the sticky footer bubbles.
  for (const url of ["/about", "/disclaimer"]) {
    test(`${url}: tabbing through the page, focus is never under the footer`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(url, { waitUntil: "networkidle" });
      const hidden: string[] = [];
      let seen = 0;
      for (let i = 0; i < 80; i++) {
        await page.keyboard.press("Tab");
        const r = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          const footer = document.querySelector(".site-footer")!;
          if (!el || el === document.body) return null;
          if (footer.contains(el)) return { inFooter: true, label: "", covered: false };
          const box = el.getBoundingClientRect();
          const bubbles = [...footer.children].map((b) => b.getBoundingClientRect());
          const covered = bubbles.some(
            (b) => box.bottom > b.top && box.top < b.bottom && box.right > b.left && box.left < b.right,
          );
          return { inFooter: false, label: el.textContent?.trim().slice(0, 40) ?? "", covered };
        });
        if (!r) continue;
        if (r.inFooter) break; // reached the footer: the page's own links are done
        seen++;
        if (r.covered) hidden.push(r.label);
      }
      expect(seen).toBeGreaterThan(3);
      expect(hidden).toEqual([]);
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
    await expect(page).toHaveURL(/\/about#cite$/);
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

// Needs the fake stack behind the UI (the upload goes to the API).
test.describe("landing upload", () => {
  test.beforeEach(async ({ page }) => {
    await routeMatomo(page);
  });

  test("a PDF chosen on the landing is uploaded by the tool and opens its paper", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "networkidle" });
    await page.locator('.act input[type="file"]').setInputFiles("public/sample/synth_015.pdf");
    await expect(page).toHaveURL(/\/app\/papers\/[^/?]+$/, { timeout: 20_000 });
    // the hand-over left the history entry: Back to /app uploads nothing again
    const uploads: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().includes("/papers")) uploads.push(r.url());
    });
    await page.goBack();
    await expect(page).toHaveURL(/\/app$/);
    await page.waitForLoadState("networkidle");
    expect(uploads).toEqual([]);
    await page.reload({ waitUntil: "networkidle" }); // a reload of that entry: nothing to send
    await expect(page.getByRole("heading", { level: 1, name: "Drop a PDF here" })).toBeVisible();
    expect(uploads).toEqual([]);
  });
});
