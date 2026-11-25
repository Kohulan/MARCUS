// Markush Phase 3, tagged @mocked: the recorded paper's first structure as a scaffold (R1, R2)
// with rows; "Build structures" makes a built card right after it, "Built from [01]", and the
// scaffold lists what could not be built. axe: 0 serious or critical violations.
import { expect, test } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations } from "./helpers";
import { FIRST, PID, paper, routeApi } from "./mockedApi";

type Pred = { id: string; engine: string; smiles: string; rgroups?: string[]; valid: boolean };
type Seg = {
  id: string;
  idx: number;
  predictions: Pred[];
  built_from?: string | null;
  compound_id?: string | null;
  build_failures?: { compound: string; reason: string }[] | null;
  curation: unknown;
};
const json = (body: unknown) => ({
  status: 200,
  contentType: "application/json",
  body: JSON.stringify(body),
});

test.describe("build structures", { tag: "@mocked" }, () => {
  let csp: () => Promise<string[]>;

  test.beforeEach(async ({ page }) => {
    csp = collectCspViolations(page);
    await routeApi(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
  });

  test.afterEach(async () => {
    expect(await csp()).toEqual([]);
  });

  test("Build structures adds a built card after its scaffold", async ({ page }) => {
    const before = structuredClone(paper) as unknown as { segments: Seg[] };
    const scaffold = before.segments[0]!;
    const shown = scaffold.predictions.find((p) => p.engine === "decimer")!;
    shown.rgroups = ["R1", "R2"];
    const rows = {
      available: true,
      extractions: [
        {
          prediction_id: shown.id,
          segment_id: scaffold.id,
          status: "done",
          labels: ["R1", "R2"],
          rows: [
            { compound: "3a", groups: { R1: "OMe", R2: "H" } },
            { compound: "3b", groups: { R1: "Tig", R2: "H" } },
          ],
          truncated: false,
          error: null,
          model: "nuextract3-rgroup-v1",
          model_version: "vision Q8_0 llama.cpp b12554",
          created_at: null,
          updated_at: null,
          finished_at: null,
        },
      ],
    };
    const after = structuredClone(before);
    after.segments[0]!.build_failures = [{ compound: "3b", reason: 'unknown substituent "Tig"' }];
    after.segments.push({
      id: "99999999-9999-4999-8999-999999999999",
      idx: 10001,
      built_from: scaffold.id,
      compound_id: "3a",
      curation: { status: "unchecked", smiles: null, molfile: null, note: null },
      predictions: [
        {
          ...shown,
          id: "99999999-9999-4999-8999-999999999998",
          engine: "enumerated",
          smiles: "COc1ccccc1",
          rgroups: [],
          valid: true,
        },
      ],
    });
    let current: unknown = before;
    await page.route(`**/api/v2/papers/${PID}`, (route) => route.fulfill(json(current)));
    await page.route(`**/api/v2/papers/${PID}/rgroups`, (route) => route.fulfill(json(rows)));
    await page.route(`**/api/v2/segments/${FIRST}/build`, (route) => {
      current = after;
      return route.fulfill(
        json({ built: 1, kept: 0, removed: 0, failures: after.segments[0]!.build_failures }),
      );
    });

    await page.goto(`/app/papers/${PID}`);
    const card = page.locator(`article[data-segment-id="${FIRST}"]`);
    await card.getByRole("button", { name: "Build structures" }).click();
    const built = page.getByRole("article").nth(1);
    await expect(built.getByRole("button", { name: "Built from [01]" })).toBeVisible();
    await expect(built.getByText("Compound 3a")).toBeVisible();
    await expect(card.getByText("Could not build")).toBeVisible();
    await expectNoA11yViolations(page);
  });
});
