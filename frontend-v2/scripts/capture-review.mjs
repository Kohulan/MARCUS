// Review screenshots for the finish review (F16), light mode only, into .impeccable/review/.
// Needs the fake stack up (Group F header) and serves from its own nginx by default.
// Seeds its own data through the API: synth_015.pdf (engine fake, 10 structures) and one image.
//
//   node scripts/capture-review.mjs            # MARCUS_UI_URL=http://localhost:18090
//
// Never point it at production.
import { mkdir, readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.MARCUS_UI_URL ?? "http://localhost:18090";
if (!["localhost", "127.0.0.1"].includes(new URL(BASE).hostname)) {
  console.error(`capture-review: refusing ${BASE} (local stack only)`);
  process.exit(2);
}
const OUT = resolve(".impeccable/review");
const PDF = resolve("public/sample/synth_015.pdf");
// A real crop of synth_015 (page 1, structure 1), for a realistic single-image result.
const IMAGE = resolve("../backend-v2/tests/fixtures/ocsr/synth015_p0_i0.png");

/** Keep every third-party request off the network (Matomo, COCONUT, PubChem). */
async function offline(context) {
  await context.route(/^https?:\/\/(?!localhost|127\.0\.0\.1)/, (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
}

async function upload(page, path, kind, mimeType, extra) {
  const res = await page.request.post(`/api/v2/${kind}`, {
    multipart: {
      file: { name: basename(path), mimeType, buffer: await readFile(path) },
      engine: "fake",
      ...extra,
    },
  });
  if (res.status() !== 202) throw new Error(`${kind} upload: ${res.status()} ${await res.text()}`);
  return res.json();
}

async function shot(page, name, opts = {}) {
  await page.waitForTimeout(400); // let motion settle
  await page.screenshot({ path: `${OUT}/${name}.png`, ...opts });
  console.log(`${OUT}/${name}.png`);
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
try {
  // Desktop, 1440 wide.
  const desk = await browser.newContext({
    baseURL: BASE,
    viewport: { width: 1440, height: 900 },
    colorScheme: "light",
  });
  await offline(desk);
  const page = await desk.newPage();

  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await shot(page, "desktop");
  await shot(page, "landing-full", { fullPage: true });

  // The papers list's answer sets the owner cookie before the uploads.
  await page.goto("/app");
  await page.getByText("No papers yet.").or(page.getByRole("list", { name: "Papers" })).waitFor();
  const { paper_id: id } = await upload(page, PDF, "papers", "application/pdf", { ocsr: "auto" });
  const { image_job_id: imageId } = await upload(page, IMAGE, "images", "image/png", {});

  await page.goto(`/app/papers/${id}`);
  await page
    .getByRole("region", { name: "Status" })
    .getByText("Done")
    .waitFor({ timeout: 360_000 });

  // A realistic mix: some accepted, one rejected, the rest to check.
  const detail = await (await page.request.get(`/api/v2/papers/${id}`)).json();
  const segs = detail.segments.sort((a, b) => a.page - b.page || a.idx - b.idx);
  const marks = { 1: "accepted", 2: "accepted", 4: "accepted", 6: "rejected" };
  for (const [i, status] of Object.entries(marks)) {
    const res = await page.request.put(`/api/v2/segments/${segs[i].id}/curation`, {
      data: { status, smiles: null, molfile: null, note: null },
    });
    if (!res.ok()) throw new Error(`curation: ${res.status()} ${await res.text()}`);
  }
  await page.reload();
  const cards = page.getByRole("article");
  await cards.first().getByRole("img").first().waitFor();
  await page.waitForLoadState("networkidle");
  await shot(page, "tool");

  // Focus mode on [01].
  await cards.first().focus();
  await page.keyboard.press("Enter");
  await page.getByRole("region", { name: "Focus [01]" }).waitFor();
  await page.waitForLoadState("networkidle");
  await shot(page, "focus");

  // Compare engines over focus mode.
  await page.keyboard.press("c");
  await page.getByRole("dialog").waitFor();
  await page.waitForLoadState("networkidle");
  await shot(page, "compare");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "detached" });

  // The structure editor (Ketcher in its frame).
  await page.keyboard.press("e");
  const editor = page.getByRole("dialog", { name: "Edit structure" });
  await editor.waitFor();
  await page
    .frameLocator('iframe[title="Structure editor"]')
    .getByRole("button", { name: "Save drawing" })
    .waitFor({ timeout: 60_000 });
  await page.waitForTimeout(1000);
  await shot(page, "editor");
  await editor.getByRole("button", { name: "Close" }).click();
  await editor.waitFor({ state: "detached" });
  await page.keyboard.press("Escape");

  // Paper view.
  await page.getByRole("group", { name: "View" }).getByRole("button", { name: "Paper" }).click();
  await page.getByRole("region", { name: "Paper view" }).waitFor();
  await page.waitForLoadState("networkidle");
  await shot(page, "paper");

  // COCONUT form, as a logged-in user (a dummy token; nothing is sent).
  await page.evaluate(() => sessionStorage.setItem("marcus-coconut-token", "review-shot"));
  await page.getByRole("button", { name: /^Send \d+ to COCONUT$/ }).click();
  await page.locator("dialog[open]").waitFor();
  await shot(page, "coconut");

  // Single image result.
  await page.goto(`/app/images/${imageId}`);
  await page.getByRole("region", { name: "Structure" }).getByRole("img").first().waitFor({
    timeout: 120_000,
  });
  await page.waitForLoadState("networkidle");
  await shot(page, "image");
  await desk.close();

  // Mobile, 390 wide: the landing.
  const phone = await browser.newContext({
    baseURL: BASE,
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    colorScheme: "light",
  });
  await offline(phone);
  const mobile = await phone.newPage();
  await mobile.goto("/");
  await mobile.waitForLoadState("networkidle");
  await shot(mobile, "mobile", { fullPage: true });
  await phone.close();
} finally {
  await browser.close();
}
