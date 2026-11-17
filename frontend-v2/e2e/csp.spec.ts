// Serving, both CSPs and the Ketcher frame (F1b). Needs `npm run build`, the fake stack and
// `npm run serve:local` (see the Group F header); never production.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { collectCspViolations, uploadPaperViaApi } from "./helpers";

// Exact, from Global Constraints (the Ketcher CSP as F1b narrowed it).
const APP_CSP =
  "default-src 'self'; script-src 'self' https://matomo.nfdi4chem.de; " +
  "connect-src 'self' https://coconut.naturalproducts.net https://pubchem.ncbi.nlm.nih.gov https://matomo.nfdi4chem.de; " +
  "img-src 'self' data: blob: https://matomo.nfdi4chem.de; style-src 'self'; font-src 'self'; " +
  "frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
const KETCHER_CSP =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; " +
  "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; " +
  "object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'";
const IMMUTABLE = "public, max-age=31536000, immutable";
const SAMPLE_PDF = "public/sample/synth_015.pdf";

const dist = join(process.cwd(), "dist");
const distFile = (file: string) => readFileSync(join(dist, file), "utf8");
const largestFile = (dir: string, ext: string) =>
  readdirSync(join(dist, dir))
    .filter((name) => name.endsWith(ext))
    .sort((a, b) => statSync(join(dist, dir, b)).size - statSync(join(dist, dir, a)).size)[0];

function expectCommonHeaders(response: APIResponse) {
  const h = response.headers();
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(h["cross-origin-resource-policy"]).toBe("same-origin");
  expect(h["permissions-policy"]).toBe("camera=(), microphone=(), geolocation=()");
}

function expectAppHeaders(response: APIResponse) {
  expect(response.headers()["content-security-policy"]).toBe(APP_CSP);
  expect(response.headers()["x-frame-options"]).toBe("DENY");
  expectCommonHeaders(response);
}

function expectKetcherHeaders(response: APIResponse) {
  expect(response.headers()["content-security-policy"]).toBe(KETCHER_CSP);
  expect(response.headers()["x-frame-options"]).toBe("SAMEORIGIN");
  expectCommonHeaders(response);
}

// Every URL of the pre-rendered set (with and without the trailing slash) and of the tool,
// with the file nginx must answer with. A wrong file means React hydration errors.
const PAGES: [url: string, file: string][] = [
  ["/", "index.html"],
  ["/about", "about/index.html"],
  ["/about/", "about/index.html"],
  ["/privacy", "privacy/index.html"],
  ["/privacy/", "privacy/index.html"],
  ["/disclaimer", "disclaimer/index.html"],
  ["/disclaimer/", "disclaimer/index.html"],
  ["/app", "app/index.html"],
  ["/app/", "app/index.html"],
  ["/app/papers/x", "app/index.html"],
  ["/app/images/x", "app/index.html"],
];

test.describe("app pages", () => {
  for (const [url, file] of PAGES) {
    test(`${url} answers 200 with dist/${file} and the app headers`, async ({ request }) => {
      const response = await request.get(url);
      expect(response.status()).toBe(200);
      expectAppHeaders(response);
      expect(response.headers()["cache-control"]).toBe("no-cache");
      expect(await response.text()).toBe(distFile(file));
    });
  }

  test("an unknown path answers 404 with the NotFound page and the app headers", async ({
    request,
  }) => {
    for (const url of ["/nope", "/apple", "/about/x"]) {
      const response = await request.get(url);
      expect(response.status(), url).toBe(404);
      expectAppHeaders(response);
      expect(await response.text(), url).toBe(distFile("404.html"));
    }
    expect(distFile("404.html")).toContain("Page not found");
  });

  // Hydration errors (#418/#423) and CSP violations show up only in a real browser.
  for (const url of ["/", "/about", "/privacy", "/disclaimer", "/app", "/app/papers/x", "/nope"]) {
    test(`${url} loads with no console error and no CSP violation`, async ({ page }) => {
      const violations = collectCspViolations(page);
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
      page.on("console", (msg) => {
        if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
      });
      const response = await page.goto(url, { waitUntil: "networkidle" });
      expect(response?.status()).toBe(url === "/nope" ? 404 : 200);
      // The 404 document's own status line is reported as a console error; nothing else may be.
      const real = errors.filter((e) => !(url === "/nope" && /status of 404/.test(e)));
      expect(real).toEqual([]);
      expect(await violations()).toEqual([]);
    });
  }
});

test.describe("static assets", () => {
  test("a hashed /assets/ script is JavaScript, immutable and gzipped when asked", async ({
    request,
  }) => {
    const js = largestFile("assets", ".js");
    expect(js).toBeTruthy();
    const response = await request.get(`/assets/${js}`, {
      headers: { "Accept-Encoding": "gzip" },
    });
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toMatch(/^(application|text)\/javascript/);
    expect(response.headers()["cache-control"]).toBe(IMMUTABLE);
    expect(response.headers()["content-encoding"]).toBe("gzip");
    expectAppHeaders(response);
  });

  test("a missing hashed asset is a 404, not an HTML page", async ({ request }) => {
    const response = await request.get("/assets/missing-0000.js");
    expect(response.status()).toBe(404);
    expect(response.headers()["content-type"] ?? "").not.toMatch(/javascript/);
  });
});

test.describe("ketcher", () => {
  test("/ketcher without the slash redirects to /ketcher/", async ({ request }) => {
    const response = await request.get("/ketcher", { maxRedirects: 0 });
    expect(response.status()).toBe(301);
    expect(response.headers()["location"]).toBe("/ketcher/");
    expectAppHeaders(response);
  });

  test("/ketcher/ answers with the Ketcher headers", async ({ request }) => {
    const response = await request.get("/ketcher/");
    expect(response.status()).toBe(200);
    expectKetcherHeaders(response);
    expect(await response.text()).toBe(distFile("ketcher/index.html"));
  });

  test("the Indigo .wasm under /ketcher/ is application/wasm with the Ketcher headers", async ({
    request,
  }) => {
    const wasm = largestFile("ketcher/assets", ".wasm");
    expect(wasm).toBeTruthy();
    const response = await request.head(`/ketcher/assets/${wasm}`);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBe("application/wasm");
    expect(response.headers()["cache-control"]).toBe(IMMUTABLE);
    expectKetcherHeaders(response);
  });

  test("Ketcher runs in a frame of /app under both CSPs", async ({ page }) => {
    test.setTimeout(90_000);
    const violations = collectCspViolations(page);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    await page.goto("/app");

    // Insert the frame and wait for its ready message (from that frame, same origin).
    await page.evaluate(
      () =>
        new Promise<void>((resolve, reject) => {
          const frame = document.createElement("iframe");
          frame.src = "/ketcher/";
          frame.title = "Structure editor";
          frame.width = "1024";
          frame.height = "768";
          const timer = setTimeout(() => reject(new Error("no marcus:ready in 60 s")), 60_000);
          window.addEventListener("message", (e: MessageEvent<{ type?: string }>) => {
            if (
              e.origin === window.location.origin &&
              e.source === frame.contentWindow &&
              e.data?.type === "marcus:ready"
            ) {
              clearTimeout(timer);
              resolve();
            }
          });
          document.body.append(frame);
        }),
    );

    const frame = page.frames().find((f) => new URL(f.url()).pathname === "/ketcher/");
    expect(frame, "the /ketcher/ frame").toBeTruthy();
    // setMolecule and getSmiles go through the Indigo worker and its WebAssembly. A worker
    // blocked by the CSP never answers, so the call is bounded and the violations are
    // checked first: they say why.
    const smiles = await frame!
      .evaluate(async () => {
        type KetcherApi = { setMolecule(s: string): Promise<void>; getSmiles(): Promise<string> };
        const ketcher = (window as unknown as { ketcher: KetcherApi }).ketcher;
        const work = (async () => {
          await ketcher.setMolecule("c1ccccc1O");
          return ketcher.getSmiles();
        })();
        const timeout = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("Indigo gave no answer in 20 s")), 20_000),
        );
        return Promise.race([work, timeout]);
      })
      .catch((e: unknown) => `error: ${String(e)}`);
    expect(await violations()).toEqual([]);
    expect(errors).toEqual([]);
    expect(smiles).toMatch(/^[^ ]*O[^ ]*$/);
  });
});

async function listPaperIds(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v2/papers");
    const body = (await response.json()) as { papers: { id: string }[] };
    return body.papers.map((p) => p.id);
  });
}

test.describe("owner cookie on http://localhost", () => {
  test("a paper uploaded through page.request is listed by the page's own fetch", async ({
    browser,
    page,
    context,
  }) => {
    await page.goto("/app");
    const id = await uploadPaperViaApi(page, SAMPLE_PDF, { ocsr: "off" });
    expect(await listPaperIds(page)).toContain(id);

    // Negative check: a fresh browser context (no owner cookie) is a different owner and
    // must not see the paper.
    const other = await browser.newContext();
    try {
      const stranger = await other.newPage();
      await stranger.goto("/app");
      expect(await listPaperIds(stranger)).not.toContain(id);
    } finally {
      await other.close();
    }

    // For the record (F1b): whether the owner cookie kept its Secure flag on http://localhost.
    const cookie = (await context.cookies()).find((c) => c.name === "marcus_owner");
    test.info().annotations.push({
      type: "owner cookie",
      description: `secure=${cookie?.secure} httpOnly=${cookie?.httpOnly} sameSite=${cookie?.sameSite} path=${cookie?.path}`,
    });
  });

  test("a paper uploaded by the browser's own fetch is listed by the next fetch", async ({
    page,
  }) => {
    await page.goto("/app");
    const id = await page.evaluate(async () => {
      const pdf = await (await fetch("/sample/synth_015.pdf")).blob();
      const form = new FormData();
      form.append("file", new File([pdf], "Sample paper (synthetic).pdf", { type: "application/pdf" }));
      form.append("ocsr", "off");
      const response = await fetch("/api/v2/papers", { method: "POST", body: form });
      if (response.status !== 202) throw new Error(`upload: ${response.status}`);
      return ((await response.json()) as { paper_id: string }).paper_id;
    });
    expect(await listPaperIds(page)).toContain(id);
  });
});
