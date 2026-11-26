// COCONUT side form (owner decision 2026-11-25), tagged @mocked: Accept in the Paper view opens
// the form beside the columns, filled; without a COCONUT login the login sits at its end;
// Download JSON saves MARCUS JSON. axe: 0 serious or critical violations.
import { expect, test } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations } from "./helpers";
import { FIRST, PID, paper, routeApi } from "./mockedApi";

test.describe("COCONUT side form", { tag: "@mocked" }, () => {
  let csp: () => Promise<string[]>;

  test.beforeEach(async ({ page }) => {
    csp = collectCspViolations(page);
    await routeApi(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
    // as the server does: once Accept is saved, the paper says so
    const accepted = structuredClone(paper) as unknown as {
      segments: { id: string; curation: unknown }[];
    };
    accepted.segments.find((x) => x.id === FIRST)!.curation = {
      status: "accepted",
      smiles: null,
      molfile: null,
      note: null,
    };
    let current: unknown = paper;
    await page.route(`**/api/v2/papers/${PID}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(current),
      }),
    );
    // the path only: a decision adds ?decision=true&shown_prediction_id=...
    await page.route(
      (url) => url.pathname === `/api/v2/segments/${FIRST}/curation`,
      (route) => {
        current = accepted;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "accepted",
            smiles: null,
            molfile: null,
            note: null,
          }),
        });
      },
    );
  });

  test.afterEach(async () => {
    expect(await csp()).toEqual([]);
  });

  test("Accept opens the filled form; login at the end; Download JSON", async ({
    page,
  }) => {
    await page.goto(`/app/papers/${PID}?view=paper`);
    await page.getByRole("button", { name: "Accept [01]" }).click();
    const form = page.getByRole("complementary", { name: "COCONUT [01]" });
    await expect(form).toBeVisible();
    await expect(page.getByRole("article", { name: "[01] · Page 1, Accepted" })).toBeVisible();
    // opens at its top: the heading has focus, not the login's Email at its end (live 2026-11-26)
    await expect(form.getByRole("heading", { name: "COCONUT [01]" })).toBeFocused();
    expect(await form.evaluate((el) => el.scrollTop)).toBe(0);
    await expect(
      form.getByRole("heading", { name: "Log in to COCONUT" }),
    ).toBeVisible();
    await expect(
      form.getByRole("button", { name: "Send to COCONUT" }),
    ).toHaveCount(0);
    const download = page.waitForEvent("download");
    await form.getByRole("button", { name: "Download JSON" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/^marcus-coconut-.+\.json$/);
    const doc = JSON.parse(
      await (
        await file.createReadStream()
      )
        .toArray()
        .then((c) => Buffer.concat(c).toString()),
    );
    expect(doc.format).toBe("marcus-coconut-1");
    expect(doc.structure.tag).toBe("[01]");
    await expectNoA11yViolations(page);
    await form.getByRole("button", { name: "Close" }).click();
    await expect(form).toHaveCount(0);
  });
});
