// Paper annotation with the fake annotator (worker-fake-annotate: values picked from the
// title, abstract and introduction by fixed rules, 2 s a run). On demand from the Paper view:
// Annotate, Annotating…, the fields, each value walking its occurrences in the text, the
// curator's corrections (kept, exported) and the reset; then the COCONUT form starting from
// the annotation's organism. Needs the built UI and the fake stack (compose.e2e.yml); never
// production.
import { expect, test, type Page } from "@playwright/test";
import { collectCspViolations, routeMatomo, uploadPaperViaApi } from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf";

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
  // No request goes to the COCONUT relay (its DOI count, a submit): the form is only looked at.
  await page.route("**/api/v2/coconut/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"data":[]}' }),
  );
});

/** Sets the owner cookie (the papers list answers first), then uploads. */
async function upload(page: Page, file: string): Promise<string> {
  await page.goto("/app");
  await page.getByText("No papers yet.").or(page.getByRole("list", { name: "Papers" })).waitFor();
  return uploadPaperViaApi(page, file, { engine: "fake" });
}

/** RFC 4180 rows (quoted fields may hold commas, quotes and line breaks). */
function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i]!;
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field !== "" || row.length) rows.push([...row, field]);
  return rows;
}

async function waitDone(page: Page, id: string): Promise<{ segments: { id: string }[] }> {
  let paper: { status: string; segments: { id: string }[] } | undefined;
  await expect
    .poll(
      async () => {
        paper = await (await page.request.get(`/api/v2/papers/${id}`)).json();
        return paper!.status;
      },
      { timeout: 240_000, intervals: [2000] },
    )
    .toBe("done");
  return paper!;
}

test("annotate the sample: the values, their occurrences, corrections kept and exported, reset", async ({
  page,
}) => {
  test.setTimeout(360_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const id = await upload(page, SAMPLE_PDF);
  await waitDone(page, id);

  await page.goto(`/app/papers/${id}?view=paper`);
  const ann = page.getByRole("region", { name: "Annotation" });
  await ann.getByRole("button", { name: "Annotate" }).focus();
  await page.keyboard.press("Enter");
  await expect(ann.locator(".state", { hasText: "Annotating…" })).toBeVisible();
  // the button is gone: the focus stays in the panel, the start is said
  await expect(ann).toBeFocused();
  await expect(ann.getByRole("status")).toHaveText("Annotating…");
  // the paper is busy only with its annotation: the status bar says so
  await expect(page.getByRole("region", { name: "Status" }).getByText("Annotating…")).toBeVisible();
  // the model reports no progress: both bars show the time-based estimate, said as one
  await expect(ann.getByRole("progressbar", { name: "Annotation progress" })).toHaveAttribute(
    "aria-valuetext",
    /^Annotating, (about \d+|100)%$/,
  );
  await expect(page.getByRole("region", { name: "Status" }).getByRole("progressbar")).toHaveAttribute(
    "aria-valuetext",
    /^Annotating, (about \d+|100)%$/,
  );

  await expect(ann.getByText("Model suggestion")).toBeVisible({ timeout: 60_000 });
  await expect(ann.getByText("fake-annotator")).toBeVisible();
  // the end is said, and Edit takes the focus
  await expect(ann.getByRole("status")).toHaveText("Annotation ready");
  await expect(ann.getByRole("button", { name: "Edit" })).toBeFocused();
  await expect(page.getByRole("region", { name: "Status" }).getByText("Done")).toBeVisible({
    timeout: 30_000,
  });
  await expect(ann.getByRole("term")).toHaveText(["Abbreviations"]);
  const nmr = ann.getByRole("button", { name: "NMR (5 in the text)" });
  await expect(nmr).toBeVisible();
  await expect(ann.getByRole("button", { name: "HPLC (5 in the text)" })).toBeVisible();

  // every occurrence is marked: 3 values × 5 pages
  const text = page.getByRole("group", { name: "Paper text" });
  await expect(text.locator("mark")).toHaveCount(15);
  await nmr.click();
  const current = text.locator(".pv-mark--current");
  await expect(current).toHaveText("NMR");
  await expect(current).toBeInViewport();
  await expect(ann.getByRole("status")).toHaveText("NMR: 1 of 5, Abbreviations");
  // the next click (Enter on the focused button) goes to the next occurrence, further down
  await page.keyboard.press("Enter");
  await expect(ann.getByRole("status")).toHaveText("NMR: 2 of 5, Abbreviations");
  await expect(current).toBeInViewport();
  const nmrs = text.locator("mark", { hasText: /^NMR$/ });
  await expect(nmrs.nth(1)).toHaveClass(/pv-mark--current/);

  // Corrections: one value a line per field; Place gets a value not in the text
  await ann.getByRole("button", { name: "Edit" }).click();
  const abbrevs = ann.getByLabel("Abbreviations");
  await expect(abbrevs).toHaveValue("HPLC\nNMR\nHRMS");
  await abbrevs.fill("HPLC\nNMR");
  await ann.getByLabel("Place").fill("Jena");
  await ann.getByRole("button", { name: "Save" }).click();
  await expect(ann.getByText("Curated")).toBeVisible();
  await expect(ann.getByText(/Jena/)).toContainText("Jena");
  await expect(ann.getByRole("button", { name: /^HRMS/ })).toHaveCount(0);
  await expect(text.locator("mark")).toHaveCount(10);

  // kept: a reload shows the curated values
  await page.reload();
  await expect(ann.getByText("Curated")).toBeVisible();

  // Export: the menu says so, and the files carry the curated values
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("group", { name: "Export" }).getByText(/^JSON: the whole annotation\./)).toBeVisible();
  const href = await page.getByRole("link", { name: "JSON, all" }).getAttribute("href");
  const doc = await (await page.request.get(href!)).json();
  expect(doc.annotation.source).toBe("curated");
  expect(doc.annotation.values.geo_location).toEqual(["Jena"]);
  expect(doc.annotation.values.abbreviation).toEqual(["HPLC", "NMR"]);
  const csvHref = await page.getByRole("link", { name: "CSV, all" }).getAttribute("href");
  const csv = await (await page.request.get(csvHref!)).text();
  const [cols, row] = csvRows(csv);
  for (const col of ["organism", "organism_part", "geo_location", "kingdom"]) expect(cols).toContain(col);
  expect(row![cols!.indexOf("geo_location")]).toBe("Jena");
  await page.keyboard.press("Escape");

  // Reset to model (asks first)
  page.once("dialog", (d) => void d.accept());
  await ann.getByRole("button", { name: "Reset to model" }).click();
  await expect(ann.getByText("Model suggestion")).toBeVisible();
  await expect(ann.getByRole("button", { name: "HRMS (5 in the text)" })).toBeVisible();
  await expect(text.locator("mark")).toHaveCount(15);

  expect(await csp()).toEqual([]);
});

/** A small paper whose abstract names an organism, its part and a place (PDF made by Chromium). */
async function organismPaper(page: Page, path: string): Promise<void> {
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>t</title></head>
    <body style="font: 12pt serif; margin: 2cm">
    <h1>Taxanes from the Bark of Taxus brevifolia</h1>
    <h2>Abstract</h2>
    <p>Two new taxane diterpenoids were isolated from the bark of Taxus brevifolia collected in
    China. Their structures were determined by spectroscopic methods and compared with known
    taxanes from related yew species.</p>
    <h2>Introduction</h2>
    <p>Taxus brevifolia is a source of paclitaxel, an important anticancer drug. In this study we
    report new taxanes from this species and describe their isolation in detail.</p>
    <h2>Results</h2>
    <p>The bark of Taxus brevifolia was extracted with methanol and the extract was separated.</p>
    </body></html>`;
  const maker = await page.context().newPage();
  await maker.setContent(html);
  await maker.pdf({ path, format: "A4" });
  await maker.close();
}

test("the COCONUT form starts from the annotation's organism, part and place", async ({
  page,
}, testInfo) => {
  test.setTimeout(360_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  // logged in to COCONUT: the form, not the login (nothing is sent)
  await page.addInitScript(() => sessionStorage.setItem("marcus-coconut-token", "e2e"));
  const pdf = testInfo.outputPath("taxus.pdf");
  await organismPaper(page, pdf);
  const id = await upload(page, pdf);
  const paper = await waitDone(page, id);
  // one accepted structure, so the paper has something to send
  const seg = paper.segments[0]!.id;
  const put = await page.request.put(`/api/v2/segments/${seg}/curation`, {
    data: { status: "accepted", smiles: null, molfile: null, note: null },
  });
  expect(put.status(), await put.text()).toBe(200);

  await page.goto(`/app/papers/${id}?view=paper`);
  const ann = page.getByRole("region", { name: "Annotation" });
  await ann.getByRole("button", { name: "Annotate" }).click();
  await expect(ann.getByText("Model suggestion")).toBeVisible({ timeout: 60_000 });
  await expect(ann.getByRole("button", { name: /^Taxus brevifolia/ })).toBeVisible();
  await expect(ann.getByRole("button", { name: /^bark/ })).toBeVisible();
  await expect(ann.getByRole("button", { name: /^China/ })).toBeVisible();

  // Each field family has its own colour: the chip, the legend swatch and the marks, each
  // mark named by its field (colour is never alone)
  const text = page.getByRole("group", { name: "Paper text" });
  const families = [
    ["Taxus brevifolia", "organism", "Organism"],
    ["bark", "part", "Organism part"],
    ["China", "place", "Place"],
  ] as const;
  const tints = new Map<string, string>();
  for (const [value, family, label] of families) {
    await expect(ann.getByRole("button", { name: new RegExp(`^${value}`) })).toHaveClass(
      new RegExp(`pv-fam--${family}`),
    );
    const mark = text.locator(`mark.pv-fam--${family}`, { hasText: value }).first();
    await expect(mark).toHaveAttribute("title", label);
    tints.set(family, await mark.evaluate((m) => getComputedStyle(m).backgroundColor));
    const swatch = ann.getByRole("term").filter({ hasText: new RegExp(`^${label}$`) }).locator(".pv-swatch");
    await expect(swatch).toHaveClass(new RegExp(`pv-fam--${family}`));
  }
  expect(new Set(tints.values()).size).toBe(3);
  expect([...tints.values()]).not.toContain("rgba(0, 0, 0, 0)");
  // the occurrence a click went to: filled with its family's deep colour, apart from its tint
  await ann.getByRole("button", { name: /^bark/ }).click();
  const current = text.locator("mark.pv-mark--current");
  await expect(current).toHaveClass(/pv-fam--part/);
  await expect(ann.getByRole("status")).toHaveText(/^bark: 1 of \d+, Organism part$/);
  const fill = await current.evaluate((m) => getComputedStyle(m).backgroundColor);
  expect(fill).not.toBe(tints.get("part"));
  await expect(page.getByRole("region", { name: "Status" }).getByText("Done")).toBeVisible({
    timeout: 30_000,
  });

  await page.getByRole("button", { name: "Send 1 to COCONUT" }).click();
  const form = page.getByRole("dialog", { name: "Send to COCONUT" });
  await expect(form.getByLabel("Organism", { exact: true })).toHaveValue("Taxus brevifolia");
  await expect(form.getByLabel("Parts").first()).toHaveValue("bark");
  await expect(form.getByLabel("Location").first()).toHaveValue("China");
  // labelled as the model's suggestion (decision 7)
  await expect(form.getByText("Organisms: model suggestion")).toBeVisible();
  // the curator can still change it
  await form.getByLabel("Organism", { exact: true }).fill("Taxus baccata");
  await expect(form.getByLabel("Organism", { exact: true })).toHaveValue("Taxus baccata");
  page.once("dialog", (d) => void d.accept());
  await form.getByRole("button", { name: "Close" }).click();
  await expect(form).toBeHidden();

  expect(await csp()).toEqual([]);
});
