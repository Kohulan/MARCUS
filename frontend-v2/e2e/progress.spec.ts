// The reading progress bar on the fake stack: a paper read by the fake engines climbs through
// its stages (never back, the printed percentage never down) and ends on a full bar that says
// Done, 100%; its tool home row shows a thin bar with its percentage while it is busy. Then, on
// a read paper whose status and steps are pinned in the browser (the rest real), the waiting
// and reading-structures states, the motion (eased fill, sheen, indeterminate slide), reduced
// motion (none of it, the percentage still printed) and axe.
// MARCUS_SHOTS=<dir> also saves screenshots of each state at 1440 and 390 px. Needs
// `npm run build`, the stack and nginx (Group F header); never production.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { collectCspViolations, expectNoA11yViolations, routeMatomo, uploadPaperViaApi } from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf"; // 5 pages, 2 structures a page (fake)
const SHOTS = process.env.MARCUS_SHOTS;
const END = 'event: end\ndata: {"status":"done"}\n\n';

type Step = { kind: string; status: string; page: number | null; segment_id: string | null };
type Sample = { value: string | null; text: string | null; shown: string | null };
declare global {
  interface Window {
    __rp?: Sample[];
  }
}

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
  await page.route("**/api/v2/coconut/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"data":[]}' }),
  );
});

async function upload(page: Page): Promise<string> {
  await page.goto("/app");
  await page.getByText("No papers yet.").or(page.getByRole("list", { name: "Papers" })).waitFor();
  return uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });
}

/** Saves the shot at 1440 px (`target`, or the page above the views) and the page at 390 px. */
async function shoot(page: Page, name: string, target?: () => Promise<Buffer>) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  if (target) await target().then((png) => writeShot(join(SHOTS, `${name}-1440.png`), png));
  else {
    const status = await page.getByRole("region", { name: "Status" }).boundingBox();
    await page.screenshot({
      path: join(SHOTS, `${name}-1440.png`),
      clip: { x: 0, y: 0, width: 1440, height: Math.ceil(status!.y + status!.height + 24) },
    });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: join(SHOTS, `${name}-390.png`) });
  await page.setViewportSize({ width: 1440, height: 1000 });
}

async function writeShot(path: string, png: Buffer) {
  const { writeFile } = await import("node:fs/promises");
  await writeFile(path, png);
}

test("a read climbs through its stages, never back, and ends on Done; the list row shows it", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  // Two papers: the second waits behind the first for the one fake segmenter, so it is still
  // being read when the paper view opens after the list.
  await upload(page);
  const id = await uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });

  // The tool home: a busy paper's row has a thin bar and its stage.
  await page.goto("/app");
  const row = page.getByRole("listitem").filter({ has: page.locator(`a[href="/app/papers/${id}"]`) });
  const rowBar = row.getByRole("progressbar");
  await expect(rowBar).toBeVisible({ timeout: 30_000 });
  await expect(rowBar).toHaveAttribute("aria-valuetext", /^Reading pages, \d of 5, \d+%$/, { timeout: 60_000 });
  await expect(row.getByText(/^Reading pages \d\/5$/)).toBeVisible();
  await expect(row.locator(".pb__pct")).toHaveText(/^\d+%$/);
  await shoot(page, "list-row", () => row.screenshot());

  // The paper: every look at the bar is recorded until it says Done.
  await page.addInitScript(() => {
    window.__rp = [];
    setInterval(() => {
      const bar = document.querySelector('[role="progressbar"][aria-label="Reading progress"]');
      if (bar) {
        window.__rp!.push({
          value: bar.getAttribute("aria-valuenow"),
          text: bar.getAttribute("aria-valuetext"),
          shown: bar.parentElement?.querySelector(".pb__pct")?.textContent ?? null,
        });
      }
    }, 50);
  });
  await page.goto(`/app/papers/${id}`);
  const bar = page.getByRole("progressbar", { name: "Reading progress" });
  const status = page.getByRole("region", { name: "Status" });
  await expect(bar).toBeVisible();
  await expectNoA11yViolations(page);
  await expect(bar).toHaveAttribute("aria-valuetext", "Done, 100%", { timeout: 180_000 });
  await expect(bar).toHaveAttribute("aria-valuenow", "100");
  await expect(status.locator(".pb__pct")).toHaveText("100%");
  // done: no sheen
  await expect(status.locator(".pb")).not.toHaveClass(/pb--active/);
  await expect(status.getByRole("list", { name: "Stages" }).getByRole("listitem")).toHaveText([
    "Checking PDF",
    "Reading pages",
    "Reading structures",
    "Reading the text",
    "Done",
  ]);
  await expect(status.getByRole("status").filter({ hasText: "Done" })).toHaveCount(1);

  const seen = await page.evaluate(() => window.__rp ?? []);
  const values = seen.filter((s) => s.value !== null).map((s) => Number(s.value));
  expect(values.length).toBeGreaterThan(0);
  for (let i = 1; i < values.length; i += 1) expect(values[i]).toBeGreaterThanOrEqual(values[i - 1]!);
  // the printed figure counts up, never down
  const shown = seen.filter((s) => s.shown).map((s) => parseInt(s.shown!, 10));
  expect(shown.length).toBeGreaterThan(0);
  for (let i = 1; i < shown.length; i += 1) expect(shown[i]).toBeGreaterThanOrEqual(shown[i - 1]!);
  expect(seen.some((s) => /^Reading pages, \d of 5, \d+%$/.test(s.text ?? ""))).toBe(true);
  expect(await csp()).toEqual([]);
});

test("waiting and reading structures, pinned on a read paper; calm under reduced motion", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const csp = collectCspViolations(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const id = await upload(page);
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v2/papers/${id}`)).json()) as { status: string }).status, {
      timeout: 180_000,
    })
    .toBe("done");
  const real = (await (await page.request.get(`/api/v2/papers/${id}`)).json()) as Record<string, unknown>;
  const steps = ((await (await page.request.get(`/api/v2/papers/${id}/steps`)).json()) as { steps: Step[] }).steps;

  // The paper's own reads answer the pinned state; everything else is the stack's.
  let pinned: { paper: Record<string, unknown>; steps: Step[] } = { paper: real, steps };
  await page.route(`**/api/v2/papers/${id}`, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(pinned.paper) })
      : route.continue(),
  );
  await page.route(`**/api/v2/papers/${id}/steps`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ steps: pinned.steps }) }),
  );
  await page.route(`**/api/v2/papers/${id}/events`, (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: END }),
  );
  await page.route("**/api/v2/queue", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ papers: [{ id, steps_ahead_by_queue: { "q.cpu": 1 }, estimate_s: 130 }], estimate_s: 130 }),
    }),
  );
  const bar = page.getByRole("progressbar", { name: "Reading progress" });
  const status = page.getByRole("region", { name: "Status" });

  // Waiting: the PDF is not checked yet, no pages known: no figure, the queue estimate.
  pinned = {
    paper: { ...real, status: "checking", pages: null },
    steps: steps.filter((s) => s.kind === "check_pdf").map((s) => ({ ...s, status: "queued" })),
  };
  await page.goto(`/app/papers/${id}`);
  await expect(status.getByText("About 3 min in the queue")).toBeVisible();
  await expect(bar).not.toHaveAttribute("aria-valuenow");
  await expect(bar).toHaveAttribute("aria-valuetext", "Waiting");
  // unmeasured: a calm slide and no number
  const slide = bar.locator(".pb__slide");
  await expect(slide).toHaveCSS("animation-name", "pb-slide");
  await expect(status.locator(".pb__pct")).toBeHidden();
  await expectNoA11yViolations(page);
  await shoot(page, "paper-waiting");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(slide).toBeHidden();
  await page.emulateMedia({ reducedMotion: "no-preference" });

  // Reading pages: three of five pages read, their structures read.
  const late = (s: Step) => s.page !== null && s.page >= 3;
  pinned = {
    paper: { ...real, status: "processing" },
    steps: steps
      .filter((s) => !(s.kind === "ocsr" && late(s)) && !(s.kind === "docling" || s.kind === "doi"))
      .map((s) => (s.kind !== "ocsr" && late(s) ? { ...s, status: s.page === 3 ? "running" : "queued" } : s)),
  };
  await page.reload();
  await expect(bar).toHaveAttribute("aria-valuetext", /^Reading pages, 3 of 5, \d+%$/);
  await shoot(page, "paper-pages");

  // Reading structures: every page read, four of ten structures still to read.
  const ocsr = steps.filter((s) => s.kind === "ocsr");
  const open = new Set(ocsr.slice(-4).map((s) => s.segment_id));
  pinned = {
    paper: { ...real, status: "processing" },
    steps: steps.map((s) => (s.kind === "ocsr" && open.has(s.segment_id) ? { ...s, status: "queued" } : s)),
  };
  await page.reload();
  await expect(bar).toHaveAttribute("aria-valuetext", /^Reading structures, 6 of 10, \d+%$/);
  const figure = await bar.getAttribute("aria-valuenow");
  await expect(status.locator(".pb__pct")).toHaveText(`${figure}%`);
  // measured: the fill eases on the one curve, the sheen crosses it while the read goes on
  const fill = bar.locator(".pb__fill");
  await expect(fill).toHaveCSS("transition-duration", "0.5s");
  await expect(fill).toHaveCSS("transform", /^matrix\(0\.\d+, 0, 0, 1, 0, 0\)$/);
  const sheen = () =>
    bar.locator(".pb__sheen").evaluate((el) => {
      const s = getComputedStyle(el);
      return `${s.display} ${getComputedStyle(el, "::before").animationName}`;
    });
  expect(await sheen()).toBe("block pb-sheen");
  // reduced motion: no sheen, no easing; the percentage is still printed
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await sheen()).toMatch(/^none /);
  await expect(fill).toHaveCSS("transition-duration", /^(0s|1e-05s)$/);
  await expect(status.locator(".pb__pct")).toHaveText(`${figure}%`);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(status.getByRole("listitem").filter({ hasText: "Reading structures" })).toHaveAttribute(
    "aria-current",
    "step",
  );
  await expectNoA11yViolations(page);
  await shoot(page, "paper-structures");

  expect(await csp()).toEqual([]);
});
