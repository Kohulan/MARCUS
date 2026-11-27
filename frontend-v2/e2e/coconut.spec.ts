// COCONUT through the MARCUS relay (owner decision 2026-11-20): COCONUT sends no CORS headers,
// so the browser calls the same-origin relay /api/v2/coconut/..., and the stack's nginx passes
// the call on. In the fake stack a fake COCONUT holds COCONUT's name (backend-v2
// tests/fake_coconut/server.py): login → form → send runs the real relay config end to end and
// nothing reaches the real COCONUT. Needs the built UI and the fake stack; never production.
import { expect, test, type Page } from "@playwright/test";
import { collectCspViolations, routeMatomo, uploadPaperViaApi } from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf";
// The fake COCONUT's fixed login and the DOI it has rows for (tests/fake_coconut/server.py).
const EMAIL = "curator@example.org";
const PASSWORD = "fake-coconut-password";
const FAKE_DOI = "10.5555/marcus.fake.coconut";

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

test("log in, fill the form and send one structure to COCONUT through the relay", async ({
  page,
}) => {
  test.setTimeout(360_000);
  const csp = collectCspViolations(page);
  await routeMatomo(page);
  // Every request the page makes: none may leave for COCONUT's own host.
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/app");
  await page.getByText("No papers yet.").or(page.getByRole("list", { name: "Papers" })).waitFor();
  const id = await uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });
  const paper = await waitDone(page, id);
  const put = await page.request.put(`/api/v2/segments/${paper.segments[0]!.id}/curation`, {
    data: { status: "accepted", smiles: null, molfile: null, note: null },
  });
  expect(put.status(), await put.text()).toBe(200);

  await page.goto(`/app/papers/${id}`);
  await page.getByRole("button", { name: "Send 1 to COCONUT" }).click();
  const dialog = page.getByRole("dialog", { name: "Send to COCONUT" });

  // A wrong password: COCONUT's 401 comes back through the relay as it was.
  await dialog.getByLabel("Email").fill(EMAIL);
  await dialog.getByLabel("Password").fill("not-the-password");
  await dialog.getByRole("button", { name: "Log in" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Wrong email or password");

  await dialog.getByLabel("Password").fill(PASSWORD);
  await dialog.getByRole("button", { name: "Log in" }).click();
  await expect(dialog.getByLabel("Title")).toBeVisible();
  // the token lives in this tab only
  expect(await page.evaluate(() => sessionStorage.getItem("marcus-coconut-token"))).toBe(
    "fake-coconut-token",
  );

  await dialog.getByLabel("Title").fill("Relay e2e");
  await dialog.getByLabel("DOI").fill(FAKE_DOI);
  await dialog.getByLabel("Evidence").fill("Isolated from the bark");
  await dialog.getByLabel("Organism", { exact: true }).fill("Taxus brevifolia");
  await dialog.getByLabel("Name for structure 1").fill("Benzene");
  await dialog.getByRole("button", { name: "Send 1 to COCONUT" }).click();
  // the fake COCONUT's created id, read from its answer through the relay
  await expect(dialog.getByText(/^Report 1\d{3}$/)).toBeVisible({ timeout: 30_000 });

  const coconutCalls = urls.filter((u) => new URL(u).pathname.startsWith("/api/v2/coconut/"));
  expect(coconutCalls.map((u) => new URL(u).pathname)).toEqual(
    expect.arrayContaining(["/api/v2/coconut/auth/login", "/api/v2/coconut/reports/mutate"]),
  );
  expect(urls.filter((u) => new URL(u).hostname.includes("naturalproducts"))).toEqual([]);
  expect(await csp()).toEqual([]);
});

test("the DOI search goes through the relay too", async ({ page }) => {
  // The UI's body (lookup/coconutDoi.ts): no `sort`, which COCONUT refuses as "desc".
  const search = (query: string, extra: Record<string, unknown> = {}) =>
    page.request.post("/api/v2/coconut/search", {
      data: { type: "tags", tagType: "citations", query, limit: 20, page: 1, offset: 0, ...extra },
    });
  const hit = await search(FAKE_DOI);
  expect(hit.status()).toBe(200);
  expect(hit.headers()["content-type"]).toBe("application/json");
  expect(((await hit.json()) as { data: { data: unknown[] } }).data.data).toHaveLength(3);
  const none = await search("10.1/nothing");
  expect(((await none.json()) as { data: { data: unknown[] } }).data.data).toHaveLength(0);
  expect((await search(FAKE_DOI, { sort: "desc" })).status()).toBe(400);
});
