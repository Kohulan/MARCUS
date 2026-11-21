// Paper view layout: nothing a click opens or brings into view is cut off. The card menus
// (More, Other engine) open in the top layer next to their button, inside the window, at the
// list's top and bottom edges, after the window or the column scrolled; a structure a marker
// selects, and the marker a card brings in, land clear of the sticky column captions; the
// Export menu stays inside. At 1024 × 768 and 1440 × 900. Needs the built UI and the fake
// stack (compose.e2e.yml); never production.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { routeMatomo, uploadPaperViaApi } from "./helpers";

// 20 pages, 2 structures a page; uploaded with OCSR off, so every card is "Not read yet"
// and has both menus (Other engine, More).
const PDF = "../backend-v2/tests/fixtures/pdfs/twenty_page.pdf";
const VIEWPORTS = [
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

let paperId = "";
let owner: { name: string; value: string; domain: string; path: string }[] = [];

test.beforeAll(async ({ browser }) => {
  test.setTimeout(240_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  await routeMatomo(page);
  await page.goto("/app");
  await page.getByText("No papers yet.").or(page.getByRole("list", { name: "Papers" })).waitFor();
  paperId = await uploadPaperViaApi(page, PDF, { ocsr: "off" });
  await expect
    .poll(async () => (await (await page.request.get(`/api/v2/papers/${paperId}`)).json()).status, {
      timeout: 200_000,
      intervals: [2000],
    })
    .toBe("done");
  owner = (await context.cookies()).map(({ name, value, domain, path }) => ({ name, value, domain, path }));
  await context.close();
});

test.beforeEach(async ({ page, context }) => {
  await routeMatomo(page);
  await context.addCookies(owner);
});

/**
 * The element lies wholly inside the window and nothing covers or clips it: the point just
 * inside each corner and each edge's middle hits the element itself (or something in it).
 */
async function expectUncut(el: Locator, what: string): Promise<void> {
  const r = await el.evaluate((node) => {
    const b = node.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    const x = [b.left + 2, (b.left + b.right) / 2, b.right - 3];
    const y = [b.top + 2, (b.top + b.bottom) / 2, b.bottom - 3];
    const covered: string[] = [];
    for (const px of x) {
      for (const py of y) {
        const hit = document.elementFromPoint(px, py);
        if (!hit || !(hit === node || node.contains(hit))) {
          covered.push(`${Math.round(px)},${Math.round(py)}: ${hit?.className || hit?.tagName || "none"}`);
        }
      }
    }
    return {
      box: [b.left, b.top, b.right, b.bottom].map(Math.round),
      inside: b.left >= 0 && b.top >= 0 && b.right <= vw && b.bottom <= vh && b.height > 0,
      covered,
    };
  });
  expect(r.inside, `${what}: ${JSON.stringify(r.box)} leaves the window`).toBe(true);
  expect(r.covered, `${what}: covered or clipped at`).toEqual([]);
}

async function openPaper(page: Page) {
  await page.goto(`/app/papers/${paperId}?view=paper`);
  await expect(page.locator(".pv-list .card")).toHaveCount(40);
  await page.locator(".pv-marker").first().waitFor();
}

/** Scrolls the list column so the card sits at its top or bottom edge. */
async function cardAtEdge(page: Page, index: number, edge: "top" | "bottom"): Promise<Locator> {
  const card = page.locator(".pv-list .card").nth(index);
  await card.evaluate((el, at) => {
    const col = el.closest<HTMLElement>(".pv-col--list")!;
    const cap = col.querySelector<HTMLElement>(".pv-cap")!.offsetHeight;
    const c = col.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    col.scrollTop += at === "top" ? r.top - c.top - cap : r.bottom - c.bottom;
  }, edge);
  return card;
}

async function checkMenus(card: Locator, page: Page, what: string) {
  await card.getByRole("button", { name: /^More for/ }).click();
  const more = page.locator(".card-menu__panel");
  await expect(more).toBeVisible();
  await expectUncut(more, `${what}: More`);
  await expect(more.getByRole("button", { name: /^Edit/ })).toBeInViewport({ ratio: 1 });
  await page.keyboard.press("Escape");
  await expect(more).toHaveCount(0);
  await expect(card.getByRole("button", { name: /^More for/ })).toBeFocused();

  await card.getByRole("button", { name: "Other engine" }).click();
  const engines = page.locator(".engine-menu__panel");
  await expect(engines).toBeVisible();
  await expectUncut(engines, `${what}: Other engine`);
  await page.keyboard.press("Escape");
  await expect(engines).toHaveCount(0);
}

for (const vp of VIEWPORTS) {
  test.describe(`${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("card menus open uncut at the list's top and bottom, first and last card", async ({ page }) => {
      await openPaper(page);
      const first = page.locator(".pv-list .card").first();
      await checkMenus(first, page, "first card");
      await checkMenus(await cardAtEdge(page, 17, "top"), page, "card 18 at the column's top");
      await checkMenus(await cardAtEdge(page, 17, "bottom"), page, "card 18 at the column's bottom");
      await checkMenus(await cardAtEdge(page, 39, "bottom"), page, "last card");

      // The window scrolled down too (the view's top under the window's top edge).
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await checkMenus(await cardAtEdge(page, 20, "top"), page, "window scrolled, card 21 at top");
      await checkMenus(await cardAtEdge(page, 20, "bottom"), page, "window scrolled, card 21 at bottom");
    });

    test("an open menu follows its card; scrolled out of the column, it closes", async ({ page }) => {
      await openPaper(page);
      const card = await cardAtEdge(page, 10, "top");
      const button = card.getByRole("button", { name: /^More for/ });
      await button.click();
      const more = page.locator(".card-menu__panel");
      await expect(more).toBeVisible();
      const list = page.locator(".pv-col--list");
      await list.evaluate((col) => (col.scrollTop += 60));
      await expect
        .poll(async () => {
          const [b, p] = await Promise.all([button.boundingBox(), more.boundingBox()]);
          // still 6 px above its button (sub-pixel layout: within a pixel)
          return Math.abs(p!.y + p!.height - b!.y + 6) <= 1.5;
        })
        .toBe(true);
      await expectUncut(more, "after the column scrolled");
      await list.evaluate((col) => (col.scrollTop += 3000));
      await expect(more).toHaveCount(0);
    });

    test("a marker's card and a card's marker land clear of the sticky captions", async ({ page }) => {
      await openPaper(page);
      const markers = page.locator(".pv-marker");
      for (const which of ["first", "last"] as const) {
        const marker = which === "first" ? markers.first() : markers.last();
        await marker.scrollIntoViewIfNeeded();
        await marker.click();
        const card = page.locator('.pv-list .card[aria-current="true"]');
        await expect(card).toBeFocused();
        await expect.poll(() => card.evaluate((el) => el.closest(".pv-col")!.scrollTop)).not.toBeNaN();
        await page.waitForTimeout(800); // the smooth scroll settles
        await expectUncut(card.locator(".card__tagrow"), `${which} marker's card`);
      }

      // Hovering a card brings its marker in, the tag above the box clear of the caption.
      await page.mouse.move(0, 0);
      const card = await cardAtEdge(page, 25, "top");
      const id = await card.getAttribute("data-segment-id");
      await card.locator(".card__tagrow").hover();
      const marker = page.locator(`.pv-marker[data-marker="${id}"]`);
      await expect(marker).toHaveClass(/pv-marker--lit/);
      await page.waitForTimeout(800);
      await expectUncut(marker, "hovered card's marker");
      const [tag, cap] = await Promise.all([
        marker.locator(".pv-marker__tag").boundingBox(),
        page.locator(".pv-col--pages > .pv-cap").boundingBox(),
      ]);
      expect(tag!.y).toBeGreaterThanOrEqual(cap!.y + cap!.height);
    });

    test("the Export menu stays inside the window", async ({ page }) => {
      await openPaper(page);
      await page.getByRole("button", { name: "Export" }).click();
      const panel = page.locator(".ws-export__panel");
      await expect(panel).toBeVisible();
      await page.waitForTimeout(250); // its entry animation
      await expectUncut(panel, "Export");
      await page.keyboard.press("Escape");
      await expect(panel).toHaveCount(0);
    });
  });
}
