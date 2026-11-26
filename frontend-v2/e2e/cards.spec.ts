// Compact cards (Paper view list, pick page), tagged @mocked: the round Accepted stamp never
// covers the card's text (live layout check 2026-11-26: it covered "3 agree" and the note).
import { expect, test } from "@playwright/test";
import { PID, routeApi } from "./mockedApi";

test.describe("compact cards", { tag: "@mocked" }, () => {
  test("the stamp covers no text", async ({ page }) => {
    await routeApi(page);
    for (const width of [1440, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/app/papers/${PID}?view=paper`);
      const card = page.locator(".card--compact", { has: page.locator(".card__stamp") }).first();
      await card.waitFor();
      const overlaps = await card.evaluate((el) => {
        const stamp = el.querySelector(".card__stamp")!.getBoundingClientRect();
        const hit = (r: DOMRect) =>
          r.width > 0 && r.left < stamp.right && r.right > stamp.left && r.top < stamp.bottom && r.bottom > stamp.top;
        return [...el.querySelectorAll(".card__body p, .card__body code, .card__body span")]
          .filter((t) => !t.closest(".card__stamp"))
          .filter((t) => hit(t.getBoundingClientRect()))
          .map((t) => t.textContent);
      });
      expect(overlaps, `at ${width} px`).toEqual([]);
    }
  });
});
