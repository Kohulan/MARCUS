// A 200-structure paper (F15): seeded straight into the local stack (no OCSR run), opened in
// the grid and scrolled to the end. Every card's drawing and crop must load within 120 s (the
// tools worker draws 200 depictions it has never drawn) and nothing may be answered 429 at
// the production per-IP limit (300/min, e2e/compose.e2e.yml). Needs the stack (Group F
// header); the seed runs inside its api container. Never production.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { routeMatomo } from "./helpers";

const STRUCTURES = 200;
// The local stack's api container (project marcus-v2). The seed refuses (exit 2, nothing
// written) any api without the fake engines (MARCUS_ENABLE_FAKE_ENGINES).
const API_CONTAINER = "marcus-v2-api-1";
const SEED = resolve("../backend-v2/tests/e2e/seed_big_paper.py");

function seed(): { paper_id: string; token: string } {
  // = docker compose -p marcus-v2 exec -T api python - < tests/e2e/seed_big_paper.py
  const out = execFileSync("docker", ["exec", "-i", API_CONTAINER, "python", "-"], {
    input: readFileSync(SEED),
    encoding: "utf8",
    timeout: 120_000,
  });
  const line = out.trim().split("\n").at(-1) ?? "";
  return JSON.parse(line) as { paper_id: string; token: string };
}

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
});

test("a 200-structure paper: every drawing and crop loads, no 429", async ({ page, context }) => {
  test.setTimeout(300_000);
  const { paper_id: id, token } = seed();
  await context.addCookies([
    { name: "marcus_owner", value: token, domain: "localhost", path: "/api/v2" },
  ]);
  const limited: string[] = [];
  page.on("response", (r) => {
    if (r.status() === 429) limited.push(`${r.request().method()} ${r.url()}`);
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/app/papers/${id}`);
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(STRUCTURES, { timeout: 30_000 });

  // Scroll the grid to its end a screen at a time, so every card comes near the viewport.
  for (let i = 0; i < 200; i++) {
    const atEnd = await page.evaluate(() => {
      window.scrollBy(0, window.innerHeight * 0.8);
      return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
    });
    await page.waitForTimeout(150);
    if (atEnd) break;
  }
  await expect(cards.last()).toBeInViewport();

  // Every card's drawing ("Structure [nn]"), then, with each card's Crop toggle on, its crop
  // ("Crop [nn]"): a decoded image. The <img>s load lazily, so a card still missing one is
  // brought into view again (a curator scrolling back), until all are in or 120 s pass.
  await expectEveryCardImage(page, "Structure ");
  await page.evaluate(() => {
    for (const b of document.querySelectorAll<HTMLButtonElement>('article button[aria-label^="Crop "]')) {
      if (b.getAttribute("aria-pressed") !== "true") b.click();
    }
  });
  await expectEveryCardImage(page, "Crop ");

  expect(limited).toEqual([]);
});

/** Polls (120 s) until every card shows an <img> whose alt starts with `alt`, decoded. */
async function expectEveryCardImage(page: Page, alt: string): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(async (prefix) => {
          const missing: HTMLElement[] = [];
          for (const card of document.querySelectorAll<HTMLElement>("article")) {
            const img = [...card.querySelectorAll("img")].find((i) => i.alt.startsWith(prefix));
            if (!img || img.naturalWidth === 0) missing.push(card);
          }
          for (const card of missing) {
            card.scrollIntoView({ block: "center" });
            await new Promise((r) => setTimeout(r, 30));
          }
          return missing.map((c) => c.getAttribute("aria-label") ?? "?");
        }, alt),
      { timeout: 120_000, intervals: [1_000] },
    )
    .toEqual([]);
}
