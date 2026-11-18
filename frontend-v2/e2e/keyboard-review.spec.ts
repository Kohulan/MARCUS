// Keyboard review (F8): the sample paper read by the fake engine (10 structures), opened in
// focus mode with Enter and reviewed to the end with A, R and the arrows only. Needs
// `npm run build`, the fake stack and `npm run serve:local` (Group F header); never production.
import { expect, test } from "@playwright/test";
import {
  collectCspViolations,
  expectNoA11yViolations,
  routeMatomo,
  uploadPaperViaApi,
} from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf";
const STRUCTURES = 10; // the fake segmenter: 2 per page, 5 pages

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
});

test("a whole paper reviewed with the keyboard only", async ({ page }) => {
  test.setTimeout(420_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  // Wait for the tool home's own papers list: its answer sets the owner cookie, and an
  // upload sent before it would get a second owner (see csp.spec.ts openApp).
  await page.goto("/app");
  await page
    .getByText("No papers yet.")
    .or(page.getByRole("list", { name: "Papers" }))
    .waitFor();
  const id = await uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });
  await page.goto(`/app/papers/${id}`);

  const status = page.getByRole("region", { name: "Status" });
  await expect(status).toContainText("Done", { timeout: 360_000 });
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(STRUCTURES);

  // Open the first with Enter.
  await cards.first().focus();
  await page.keyboard.press("Enter");
  const focus = page.getByRole("region", { name: /^Focus / });
  await expect(focus).toBeVisible();
  await expect(focus).toHaveAccessibleName("Focus [01]");
  await expect(focus.getByRole("img", { name: "Page 1" })).toBeVisible();
  await expect(focus.getByTestId(/^marker-/).first()).toBeVisible();
  await expectNoA11yViolations(page);
  await page.screenshot({ path: test.info().outputPath("focus-1440.png") });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.screenshot({ path: test.info().outputPath("focus-1024.png") });
  await page.setViewportSize({ width: 1440, height: 1000 });

  // ← on the first stays; → then ← comes back.
  await page.keyboard.press("ArrowRight");
  await expect(focus).toHaveAccessibleName("Focus [02]");
  await page.keyboard.press("ArrowLeft");
  await expect(focus).toHaveAccessibleName("Focus [01]");

  // ? shows the key list; Esc closes it and keeps focus mode.
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Keys" })).toBeVisible();
  await expectNoA11yViolations(page);
  await page.screenshot({ path: test.info().outputPath("keys.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Keys" })).toHaveCount(0);
  await expect(focus).toBeVisible();

  // Every structure: odd ones accepted, even ones rejected. Each decision moves on to the
  // next structure still to check.
  for (let n = 1; n <= STRUCTURES; n++) {
    const tag = `[${String(n).padStart(2, "0")}]`;
    await expect(focus).toHaveAccessibleName(`Focus ${tag}`);
    await page.keyboard.press(n % 2 === 1 ? "a" : "r");
    const word = n % 2 === 1 ? "Accepted" : "Rejected";
    if (n < STRUCTURES) {
      await expect(focus).not.toHaveAccessibleName(`Focus ${tag}`);
    } else {
      await expect(focus.getByRole("img", { name: word })).toBeVisible();
    }
  }
  await expect(focus.getByRole("status").filter({ hasText: "None left to check" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("focus-done.png") });

  // The saves reached the server: a fresh read of the paper agrees.
  await expect
    .poll(async () => {
      const res = await page.request.get(`/api/v2/papers/${id}`);
      const body = (await res.json()) as { accepted: number; rejected: number; to_review: number };
      return [body.accepted, body.rejected, body.to_review];
    })
    .toEqual([5, 5, 0]);

  // Esc: back to the grid, the last card focused; the To check filter is empty.
  await page.keyboard.press("Escape");
  await expect(focus).toHaveCount(0);
  await expect(cards.nth(STRUCTURES - 1)).toBeFocused();
  const toCheck = page
    .getByRole("group", { name: "Filter" })
    .getByRole("button", { name: /^To check/ });
  await expect(toCheck).toContainText("0");
  await toCheck.click();
  await expect(cards).toHaveCount(0);

  expect(await csp()).toEqual([]);
});
