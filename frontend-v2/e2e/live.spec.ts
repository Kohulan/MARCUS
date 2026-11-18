// Live updates (F15): a paper read by the fake engine, opened at once. Its first structure
// card appears while the paper is still being read, without a reload, and while the event
// stream is open the page never polls (polling starts only when the stream fails). Needs
// `npm run build`, the stack and nginx (Group F header); never production.
import { expect, test } from "@playwright/test";
import { collectCspViolations, routeMatomo, uploadPaperViaApi } from "./helpers";

const SAMPLE_PDF = "public/sample/synth_015.pdf";
const STRUCTURES = 10; // the fake segmenter: 2 per page, 5 pages

type SseLog = { t: number; type: string; readyState: number }[];
declare global {
  interface Window {
    __sse?: SseLog;
  }
}

test.beforeEach(async ({ page }) => {
  await routeMatomo(page);
});

test("the first card appears while the paper is read, and the open stream is never polled", async ({
  page,
}) => {
  test.setTimeout(300_000);
  const csp = collectCspViolations(page);
  // Every EventSource of the page logs its frames, errors and its end (performance.now()).
  await page.addInitScript(() => {
    const log: SseLog = [];
    window.__sse = log;
    const Native = window.EventSource;
    class Logged extends Native {
      constructor(url: string | URL, init?: EventSourceInit) {
        super(url, init);
        const note = (type: string) =>
          log.push({ t: performance.now(), type, readyState: this.readyState });
        note("new");
        for (const type of ["open", "message", "snapshot", "end", "error"]) {
          this.addEventListener(type, () => note(type));
        }
        const close = this.close.bind(this);
        this.close = () => {
          note("close");
          close();
        };
      }
    }
    window.EventSource = Logged as typeof EventSource;
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  // The papers list's answer sets the owner cookie before the upload (see csp.spec.ts).
  await page.goto("/app");
  await page
    .getByText("No papers yet.")
    .or(page.getByRole("list", { name: "Papers" }))
    .waitFor();
  const id = await uploadPaperViaApi(page, SAMPLE_PDF, { engine: "fake" });

  // Paper reads (GET /papers/<id>), timed on the page's clock.
  const reads: number[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (r.method() === "GET" && url.pathname === `/api/v2/papers/${id}`) reads.push(Date.now());
  });
  let navigations = 0;
  page.on("framenavigated", (f) => {
    if (f === page.mainFrame()) navigations += 1;
  });
  await page.goto(`/app/papers/${id}`);
  const offset = await page.evaluate(() => Date.now() - performance.now());
  const navigationsAtOpen = navigations;

  // The first look at the opened paper: still being read, no card on screen yet, so the
  // card the next look finds arrived live.
  const first = await page.waitForFunction(
    () => {
      const status = document.querySelector('section[aria-label="Status"]');
      if (!/Reading…/.test(status?.textContent ?? "")) return false;
      return { articles: document.querySelectorAll("article").length };
    },
    undefined,
    { timeout: 60_000, polling: 50 },
  );
  expect(await first.jsonValue()).toEqual({ articles: 0 });

  // In one look: a structure card is shown and the status still says the paper is being
  // read ("Reading…" is the UI word for the API's `processing`).
  await page.waitForFunction(
    () => {
      const status = document.querySelector('section[aria-label="Status"]');
      return document.querySelector("article") !== null && /Reading…/.test(status?.textContent ?? "");
    },
    undefined,
    { timeout: 120_000, polling: 50 },
  );
  const api = await page.request.get(`/api/v2/papers/${id}`);
  // The paper may finish between the look and this read, but never before the first card.
  expect(["processing", "done"]).toContain(((await api.json()) as { status: string }).status);

  // The rest arrives live too, and the stream ends with the paper.
  const status = page.getByRole("region", { name: "Status" });
  await expect(status).toContainText("Done", { timeout: 240_000 });
  await expect(page.getByRole("article")).toHaveCount(STRUCTURES);
  expect(navigations).toBe(navigationsAtOpen); // no reload
  await expect(page.getByText("Live updates paused")).toHaveCount(0);

  const sse = (await page.evaluate(() => window.__sse ?? [])).map((e) => ({
    ...e,
    t: e.t + offset,
  }));
  const opened = sse.find((e) => e.type === "open");
  const ended = sse.find((e) => e.type === "end");
  expect(opened, JSON.stringify(sse)).toBeTruthy();
  expect(ended, JSON.stringify(sse)).toBeTruthy();
  // Polling starts only on an error; there was none while the stream was open.
  expect(sse.filter((e) => e.type === "error" && e.t < ended!.t)).toEqual([]);
  // Every read while the stream was open answers a frame: at most one read per frame
  // (refreshes are coalesced, never added), so a 2 s poll would show as surplus reads.
  const frames = sse.filter(
    (e) => (e.type === "message" || e.type === "snapshot") && e.t >= opened!.t && e.t <= ended!.t,
  );
  const openReads = reads.filter((t) => t > opened!.t + 50 && t <= ended!.t);
  expect(openReads.length).toBeLessThanOrEqual(frames.length);
  // And no read ever came two seconds or more after the last frame before it.
  for (const t of openReads) {
    const last = frames.filter((f) => f.t <= t).at(-1);
    expect(last, `read at ${t} with no frame before it`).toBeTruthy();
    expect(t - last!.t).toBeLessThan(2_000);
  }

  expect(await csp()).toEqual([]);
});
