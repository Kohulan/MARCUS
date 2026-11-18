// The structure editor (F11): the sample paper read by the fake engine, a structure opened in
// focus mode, E opens Ketcher in its own frame (its own CSP), "Save drawing" stores the
// structure (note kept, unchecked → accepted) and the card's drawing URL changes. Needs
// `npm run build`, the fake stack and `npm run serve:local` (Group F header); never production.
import { expect, test } from "@playwright/test";
import { collectCspViolations, routeMatomo, uploadPaperViaApi } from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf";
const STRUCTURES = 10; // the fake segmenter: 2 per page, 5 pages
const NOTE = "e2e note, kept by the editor";
// Exact, from Global Constraints (the same constant as csp.spec.ts).
const KETCHER_CSP =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; " +
  "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; " +
  "object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'";
// Set by the caller only, for the hand-off screenshot of the open editor.
const SHOT = process.env.MARCUS_EDITOR_SHOT;

type Curation = { status: string; smiles: string | null; molfile: string | null; note: string | null };
type Segment = { id: string; page: number; idx: number; curation: Curation | null };

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
});

test("edit a structure in Ketcher: saved, note kept, drawing changed, no CSP violation", async ({
  page,
}) => {
  test.setTimeout(420_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  // The papers list's answer sets the owner cookie before the upload (see csp.spec.ts).
  await page.goto("/app");
  await page
    .getByText("No papers yet.")
    .or(page.getByRole("list", { name: "Papers" }))
    .waitFor();
  const id = await uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });
  await page.goto(`/app/papers/${id}`);
  await expect(page.getByRole("region", { name: "Status" })).toContainText("Done", {
    timeout: 360_000,
  });
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(STRUCTURES);

  // Structure [01] gets a note first, so the save can prove it keeps it.
  const segments = async (): Promise<Segment[]> => {
    const res = await page.request.get(`/api/v2/papers/${id}`);
    expect(res.ok()).toBe(true);
    const body = (await res.json()) as { segments: Segment[] };
    return body.segments.sort((a, b) => a.page - b.page || a.idx - b.idx);
  };
  const first = (await segments())[0]!;
  const put = await page.request.put(`/api/v2/segments/${first.id}/curation`, {
    data: { status: "unchecked", smiles: null, molfile: null, note: NOTE },
  });
  expect(put.status(), await put.text()).toBe(200);
  // The cards load their drawings as blobs: watch the depiction URLs [01] asks for.
  const asked: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (url.pathname === `/api/v2/segments/${first.id}/depiction`) asked.push(url.search);
  });
  await page.reload();
  const card = cards.first();
  await expect(card.getByRole("img", { name: "Structure [01]" })).toHaveAttribute("src", /^blob:/);
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  const before = asked.at(-1)!;
  expect(before).toMatch(/^\?v=/);

  // Focus mode on [01], then E.
  await card.focus();
  await page.keyboard.press("Enter");
  const focus = page.getByRole("region", { name: "Focus [01]" });
  await expect(focus).toBeVisible();
  const ketcherPage = page.waitForResponse((r) => new URL(r.url()).pathname === "/ketcher/");
  await page.keyboard.press("e");
  const dialog = page.getByRole("dialog", { name: "Edit structure" });
  await expect(dialog).toBeVisible();
  const response = await ketcherPage;
  expect(response.headers()["content-security-policy"]).toBe(KETCHER_CSP);
  // marcus:ready arrived: the dialog drops its loading line, and Ketcher is up in the frame.
  await expect(dialog.getByText("Loading editor…")).toHaveCount(0, { timeout: 60_000 });
  const frame = page.frameLocator('iframe[title="Structure editor"]');
  const save = frame.getByRole("button", { name: "Save drawing" });
  await expect(save).toBeEnabled({ timeout: 60_000 });
  await expect(dialog.getByLabel("SMILES")).not.toHaveValue("");
  // Read while the Ketcher frame is still open: its own `securitypolicyviolation` records
  // live in the frame's window and are gone once the dialog closes.
  expect(
    page.frames().some((f) => new URL(f.url()).pathname === "/ketcher/"),
    "the /ketcher/ frame is open",
  ).toBe(true);
  expect(await csp()).toEqual([]);
  if (SHOT) await page.screenshot({ path: SHOT });

  // A review key typed in the dialog does nothing to focus mode.
  await dialog.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("a");
  await page.keyboard.press("ArrowRight");
  await expect(focus).toBeVisible();
  expect((await segments())[0]!.curation?.status ?? "unchecked").toBe("unchecked");

  // Save the drawing as it is.
  await save.click();
  await expect(dialog).toHaveCount(0);
  await expect(focus).toBeVisible(); // still focus mode, still [01]
  await expect
    .poll(async () => (await segments())[0]!.curation, { timeout: 15_000 })
    .toMatchObject({ status: "accepted", note: NOTE });
  const saved = (await segments())[0]!.curation!;
  expect(saved.smiles).toBeTruthy();
  expect(saved.molfile).toContain("M  END");

  // A SMILES that cannot be parsed: the dialog stays open with the API's reason.
  await page.keyboard.press("e");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("SMILES").fill("C1CC(");
  await dialog.getByRole("button", { name: "Save SMILES" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Save failed:");
  await expect(dialog).toBeVisible();
  // Esc in the dialog closes only the editor.
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(focus).toBeVisible();
  expect((await segments())[0]!.curation).toMatchObject({
    smiles: saved.smiles,
    molfile: saved.molfile,
    note: NOTE,
  });

  // Back on the grid: the card's drawing has a new URL (a new `?v=`). The card menu's Edit opens the same
  // editor.
  await page.keyboard.press("Escape");
  await expect(focus).toHaveCount(0);
  await expect.poll(() => asked.filter((q) => q !== before).length).toBeGreaterThan(0);
  await card.getByRole("button", { name: "More for [01]" }).click();
  await card.getByRole("button", { name: "Edit" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(card.getByRole("button", { name: "More for [01]" })).toBeFocused();

  expect(await csp()).toEqual([]);
});
