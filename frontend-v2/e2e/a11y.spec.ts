// Accessibility sweep (F15), tagged @mocked: every API call is answered from e2e/fixtures/
// (recorded from the fake stack, engines renamed to real ones), so it needs only the built UI
// behind nginx (`npm run serve:local`), no stack: CI runs it. axe: 0 serious or critical
// violations, light mode only, on each screen of the tool (1440 px) and on the static pages at
// phone width (390 px: the pages that must work on a phone, footer target sizes included). The
// Ketcher frame is a third-party page and is left out of the editor dialog's run.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations, routeMatomo } from "./helpers";

const FIXTURES = join(process.cwd(), "e2e", "fixtures");
const fixture = (name: string) => readFileSync(join(FIXTURES, name));
const json = (name: string) => JSON.parse(fixture(name).toString("utf8")) as Record<string, unknown>;

const paper = json("paper.json") as { id: string; segments: { id: string }[] };
const image = json("image.json") as { id: string; display_name: string };
const PID = paper.id;
const IID = image.id;
const FIRST = paper.segments[0]!.id;
const END = 'event: end\ndata: {"status":"done"}\n\n';

/** The mocked API: GETs from fixtures, the tools' POSTs with recorded answers, else a 404. */
async function routeApi(page: Page): Promise<void> {
  const reply = (route: Route, body: Buffer | string, contentType = "application/json") =>
    route.fulfill({ status: 200, contentType, body });
  await page.route("**/api/v2/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api\/v2/, "");
    const get = req.method() === "GET";
    if (get && /\/events$/.test(path)) return reply(route, END, "text/event-stream");
    if (get && path === "/papers") return reply(route, fixture("papers.json"));
    if (get && path === "/images") return reply(route, fixture("images.json"));
    if (get && path === "/queue") return reply(route, fixture("queue.json"));
    if (get && path === `/papers/${PID}`) return reply(route, fixture("paper.json"));
    if (get && path === `/papers/${PID}/steps`) return reply(route, fixture("steps.json"));
    if (get && path === `/papers/${PID}/text`) return reply(route, fixture("text.json"));
    if (get && path === `/papers/${PID}/annotation`) return reply(route, fixture("annotation.json"));
    if (get && /^\/papers\/[^/]+\/pages\/\d+\/image$/.test(path)) {
      return reply(route, fixture("page.png"), "image/png");
    }
    if (get && /^\/segments\/[^/]+\/image$/.test(path)) {
      return reply(route, fixture("crop.png"), "image/png");
    }
    if (get && /^\/segments\/[^/]+\/depiction$/.test(path)) {
      return reply(route, fixture("depiction.svg"), "image/svg+xml");
    }
    if (get && path === `/images/${IID}`) return reply(route, fixture("image.json"));
    if (get && path === `/images/${IID}/image`) return reply(route, fixture("crop.png"), "image/png");
    if (req.method() === "POST") {
      if (path === "/tools/depict") return reply(route, fixture("depict.json"));
      if (path === "/tools/compare") return reply(route, fixture("compare.json"));
      if (path === "/tools/mcs") return reply(route, fixture("mcs.json"));
      if (path === "/tools/smiles-to-molfile") return reply(route, fixture("molfile.json"));
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"not found"}' });
  });
  // Third parties: Matomo (empty 204), COCONUT's DOI search through the MARCUS relay (nothing
  // found), PubChem (none).
  await routeMatomo(page);
  await page.route("**/api/v2/coconut/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"data":[]}' }),
  );
  await page.route("https://pubchem.ncbi.nlm.nih.gov/**", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: "{}" }),
  );
}

test.describe("accessibility", { tag: "@mocked" }, () => {
  let csp: () => Promise<string[]>;

  test.beforeEach(async ({ page }) => {
    csp = collectCspViolations(page);
    await routeApi(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
  });

  test.afterEach(async () => {
    expect(await csp()).toEqual([]);
  });

  test("tool home", async ({ page }) => {
    await page.goto("/app");
    await expect(page.getByRole("list", { name: "Papers" })).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("review grid", async ({ page }) => {
    await page.goto(`/app/papers/${PID}`);
    await expect(page.getByRole("article")).toHaveCount(paper.segments.length);
    await expect(page.getByRole("img", { name: "Structure [01]" })).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("focus mode", async ({ page }) => {
    await page.goto(`/app/papers/${PID}?s=${FIRST}&focus=1`);
    const focus = page.getByRole("region", { name: "Focus [01]" });
    await expect(focus).toBeVisible();
    await expect(focus.getByRole("img", { name: "Page 1" })).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("paper view", async ({ page }) => {
    await page.goto(`/app/papers/${PID}?view=paper`);
    const view = page.getByRole("region", { name: "Paper view" });
    await expect(view).toBeVisible();
    await expect(view.getByRole("button", { name: "Structure [01] on page 1" })).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("paper view: the annotation, a value shown in the text, and its corrections", async ({ page }) => {
    await page.goto(`/app/papers/${PID}?view=paper`);
    const ann = page.getByRole("region", { name: "Annotation" });
    await ann.getByRole("button", { name: "NMR (5 in the text)" }).click();
    await expect(page.locator(".pv-mark--current")).toHaveText("NMR");
    await expectNoA11yViolations(page);
    await ann.getByRole("button", { name: "Edit" }).click();
    await expect(ann.getByLabel("Abbreviations")).toHaveValue("HPLC\nNMR\nHRMS");
    await expectNoA11yViolations(page);
  });

  test("a scaffold's R-group rows: card and focus mode", async ({ page }) => {
    // The first structure as a scaffold (R1, R2) with rows read by the R-group model.
    const scaffold = structuredClone(paper) as unknown as {
      segments: { id: string; predictions: { id: string; engine: string; rgroups?: string[] }[] }[];
    };
    const segment = scaffold.segments[0]!;
    const shown = segment.predictions.find((p) => p.engine === "decimer")!;
    shown.rgroups = ["R1", "R2"];
    const rows = {
      available: true,
      extractions: [
        {
          prediction_id: shown.id,
          segment_id: segment.id,
          status: "done",
          labels: ["R1", "R2"],
          rows: [
            { compound: "3a", groups: { R1: "OMe", R2: "H" } },
            { compound: "3b", groups: { R1: "H", R2: "β-D-Glc" } },
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
    const body = (data: unknown) => ({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
    await page.route(`**/api/v2/papers/${PID}`, (route) => route.fulfill(body(scaffold)));
    await page.route(`**/api/v2/papers/${PID}/rgroups`, (route) => route.fulfill(body(rows)));

    await page.goto(`/app/papers/${PID}`);
    const card = page.locator(`article[data-segment-id="${FIRST}"]`);
    await expect(card.getByRole("table")).toBeVisible();
    await expect(card.getByRole("cell", { name: "β-D-Glc" })).toBeVisible();
    await expectNoA11yViolations(page);

    await page.goto(`/app/papers/${PID}?s=${FIRST}&focus=1`);
    const focus = page.getByRole("region", { name: "Focus [01]" });
    await expect(focus.getByRole("table", { name: /^Model output/ })).toBeVisible();
    await expect(focus.getByRole("button", { name: "Run again" })).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("the main figure: its page marked, its structures first, a repeat shown once", async ({
    page,
  }) => {
    // Page 3 is the main figure; the first structure of page 4 repeats its first structure.
    const marked = structuredClone(paper) as unknown as {
      main_figure_page: number | null;
      segments: { id: string; repeat_of?: string | null }[];
    };
    const main = marked.segments[4]!;
    marked.main_figure_page = 2;
    marked.segments[6]!.repeat_of = main.id;
    const puts: unknown[] = [];
    await page.route(`**/api/v2/papers/${PID}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(marked) }),
    );
    await page.route(`**/api/v2/papers/${PID}/main-figure`, (route) => {
      puts.push(route.request().postDataJSON());
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: '{"main_figure_page":null}',
      });
    });

    await page.goto(`/app/papers/${PID}?view=paper`);
    const mark = page.getByRole("button", { name: "Main figure: Page 3" });
    await expect(mark).toHaveAttribute("aria-pressed", "true");
    const list = page.getByRole("region", { name: "Structures" });
    await expect(list.getByRole("article")).toHaveCount(paper.segments.length - 1);
    const first = list.getByRole("article").first();
    await expect(first).toHaveAttribute("data-segment-id", main.id);
    await expect(first.getByText("Also on page 4")).toBeVisible();
    await expectNoA11yViolations(page);

    await mark.click();
    await expect.poll(() => puts).toEqual([{ page: null }]);

    await page.goto(`/app/papers/${PID}`);
    await expect(page.getByRole("article")).toHaveCount(paper.segments.length - 1);
    await expectNoA11yViolations(page);
  });

  test("phase B cards: Check this drawing, the engines' badge, the compound ID", async ({
    page,
  }) => {
    const shown = structuredClone(paper) as unknown as {
      segments: {
        check_drawing?: boolean;
        agree?: number | null;
        agree_engines?: string[];
        compound_id?: string | null;
        compound_name?: string | null;
      }[];
    };
    Object.assign(shown.segments[0]!, {
      check_drawing: true,
      agree: 0,
      agree_engines: [],
      compound_id: "12",
      compound_name: "salsubstolin A",
    });
    Object.assign(shown.segments[1]!, { agree: 3, agree_engines: ["decimer", "molnextr", "molscribe"] });
    Object.assign(shown.segments[2]!, { agree: 2, agree_engines: ["molnextr", "molscribe"] });
    await page.route(`**/api/v2/papers/${PID}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(shown) }),
    );
    await page.goto(`/app/papers/${PID}`);
    const first = page.getByRole("article").first();
    await expect(first.getByText("Check this drawing")).toBeVisible();
    await expect(first.getByText("Compound 12 · salsubstolin A")).toBeVisible();
    await expect(first.getByText("Differ")).toBeVisible();
    await expect(page.getByText("3 agree")).toBeVisible();
    await expect(page.getByText("2 agree")).toBeVisible();
    await expectNoA11yViolations(page);
    await first.getByRole("button", { name: "Edit [01]" }).click();
    await expect(page.getByRole("dialog", { name: "Edit structure" })).toBeVisible();
  });

  test("compare", async ({ page }) => {
    await page.goto(`/app/papers/${PID}?s=${FIRST}&focus=1`);
    await expect(page.getByRole("region", { name: "Focus [01]" })).toBeVisible();
    await page.keyboard.press("c");
    const dialog = page.getByRole("dialog", { name: /Compare engines/ });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("MolNexTR").first()).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("editor dialog (the Ketcher frame excluded)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto(`/app/papers/${PID}?s=${FIRST}&focus=1`);
    await expect(page.getByRole("region", { name: "Focus [01]" })).toBeVisible();
    await page.keyboard.press("e");
    const dialog = page.getByRole("dialog", { name: "Edit structure" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Loading editor…")).toHaveCount(0, { timeout: 60_000 });
    await expectNoA11yViolations(page, { exclude: ["iframe"] });
  });

  test("COCONUT login and form", async ({ page }) => {
    await page.goto(`/app/papers/${PID}`);
    const send = page.getByRole("button", { name: /^Send 1 to COCONUT/ });
    await send.click();
    const dialog = page.getByRole("dialog", { name: /COCONUT/ });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Email")).toBeVisible();
    await expectNoA11yViolations(page);

    // Logged in (the token only lives in this tab): the form itself.
    await page.evaluate(() => sessionStorage.setItem("marcus-coconut-token", "e2e-token"));
    await page.reload();
    await page.getByRole("button", { name: /^Send 1 to COCONUT/ }).click();
    await expect(dialog.getByLabel("Title")).toBeVisible();
    await expectNoA11yViolations(page);
  });

  test("image result", async ({ page }) => {
    await page.goto(`/app/images/${IID}`);
    await expect(page.getByText(image.display_name).first()).toBeVisible();
    await expect(page.getByRole("img", { name: /structure/i }).first()).toBeVisible();
    await expectNoA11yViolations(page);

    // Download image under the real CSP: the drawing the page holds, never a fetch of blob:.
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download image" }).click();
    expect((await download).suggestedFilename()).toBe("Figure_2b-1.svg");
    await expect(page.getByText("Could not download the image")).toHaveCount(0);
  });
});

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

// The pages a phone visitor reaches (the landing, the info pages, and /app's desktop-only
// note), at 390 px: the footer links wrap there, so target size (2.5.8) is checked where it bites.
test.describe("accessibility at phone width", { tag: "@mocked" }, () => {
  let csp: () => Promise<string[]>;

  test.beforeEach(async ({ page }) => {
    csp = collectCspViolations(page);
    await routeApi(page);
    await page.setViewportSize({ width: 390, height: 844 });
  });

  test.afterEach(async () => {
    expect(await csp()).toEqual([]);
  });

  for (const url of ["/", "/about/", "/privacy/", "/disclaimer/", "/app"]) {
    test(`${url} at 390 px`, async ({ page }) => {
      await page.goto(url);
      await expect(page.getByRole("navigation", { name: "Footer" })).toBeVisible();
      // the footer band stacks: every link in it is at least a 24 by 24 px target
      for (const link of await page.getByRole("contentinfo").getByRole("link").all()) {
        const box = await link.boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(24);
        expect(box?.height).toBeGreaterThanOrEqual(24);
      }
      // WCAG 2.2 AA on: axe leaves target-size (2.5.8) off unless its tag is asked for.
      await expectNoA11yViolations(page, { tags: WCAG_TAGS });
    });
  }
});
