// "All pages or pick a structure" (owner decision 2026-11-25), tagged @mocked: the recorded
// paper (e2e/fixtures) turned into a paper waiting for the choice, then one in pick mode whose
// first page's boxes are candidates. axe: 0 serious or critical violations on both screens.
import { expect, test } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations } from "./helpers";
import { PID, paper, routeApi } from "./mockedApi";

type Seg = { id: string; page: number; candidate?: boolean };
const json = (body: unknown) => ({
  status: 200,
  contentType: "application/json",
  body: JSON.stringify(body),
});

test.describe("pick a structure", { tag: "@mocked" }, () => {
  let csp: () => Promise<string[]>;

  test.beforeEach(async ({ page }) => {
    csp = collectCspViolations(page);
    await routeApi(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
  });

  test.afterEach(async () => {
    expect(await csp()).toEqual([]);
  });

  test("ask, then pick a page and a box", async ({ page }) => {
    const asked = { ...structuredClone(paper), ocsr_mode: "ask", segments: [] };
    const picked = structuredClone(paper) as unknown as { ocsr_mode: string; segments: Seg[] };
    picked.ocsr_mode = "pick";
    const first = picked.segments.filter((s) => s.page === picked.segments[0]!.page);
    for (const s of picked.segments) s.candidate = true;
    picked.segments = first;
    let current: unknown = asked;
    const calls: string[] = [];
    await page.route(`**/api/v2/papers/${PID}`, (route) => route.fulfill(json(current)));
    await page.route(`**/api/v2/papers/${PID}/mode`, (route) => {
      calls.push(`mode ${JSON.stringify(route.request().postDataJSON())}`);
      current = picked;
      return route.fulfill(json({ ocsr_mode: "pick" }));
    });
    await page.route(`**/api/v2/papers/${PID}/pages/*/segment`, (route) => {
      calls.push(`segment ${new URL(route.request().url()).pathname.split("/").at(-2)}`);
      return route.fulfill({ ...json({ step_id: null }), status: 202 });
    });
    await page.route("**/api/v2/segments/*/read", (route) => {
      calls.push("read");
      return route.fulfill({ ...json({ step_ids: ["a", "b", "c"] }), status: 202 });
    });

    await page.goto(`/app/papers/${PID}`);
    await expect(page.getByRole("button", { name: "Read all pages" })).toBeVisible();
    await expectNoA11yViolations(page);
    await page.getByRole("button", { name: "Pick a structure" }).click();

    const pages = page.getByRole("group", { name: "Pick a page" });
    await expect(pages).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0); // candidates are no cards
    await expectNoA11yViolations(page);
    const n = picked.segments[0]!.page + 1;
    await pages.getByRole("button", { name: `Page ${n}` }).click();
    await page.getByRole("button", { name: `Read structure [01] on page ${n}` }).click();
    await expect.poll(() => calls).toEqual([
      'mode {"mode":"pick"}',
      `segment ${n - 1}`,
      "read",
    ]);
    await page.getByRole("button", { name: "Pick another" }).click();
    await expect(pages).toBeVisible();
  });
});
