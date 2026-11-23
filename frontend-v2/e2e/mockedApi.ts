// The mocked API for the @mocked specs: every API call is answered from e2e/fixtures/
// (recorded from the fake stack, engines renamed to real ones), so a spec needs only the built
// UI behind nginx (`npm run serve:local`), no stack.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Page, Route } from "@playwright/test";
import { routeMatomo } from "./helpers";

const FIXTURES = join(process.cwd(), "e2e", "fixtures");
const fixture = (name: string) => readFileSync(join(FIXTURES, name));
const json = (name: string) => JSON.parse(fixture(name).toString("utf8")) as Record<string, unknown>;

export const paper = json("paper.json") as { id: string; segments: { id: string }[] };
export const image = json("image.json") as { id: string; display_name: string };
export const PID = paper.id;
export const IID = image.id;
export const FIRST = paper.segments[0]!.id;
const END = 'event: end\ndata: {"status":"done"}\n\n';

/** The mocked API: GETs from fixtures, the tools' POSTs with recorded answers, else a 404. */
export async function routeApi(page: Page): Promise<void> {
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
