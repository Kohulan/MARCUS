// Lighthouse performance gate (F15): the landing page served by the stack's own nginx
// (http://localhost:18090/, the shipped image and headers), desktop preset. Prints the score
// and exits 1 below 90. Needs the stack up (Group F header); never production.
//   node scripts/lighthouse-gate.mjs [url]
import { execFileSync } from "node:child_process";
import { chromium } from "@playwright/test";

const MIN = 90;
const url = process.argv[2] ?? "http://localhost:18090/";
const host = new URL(url).hostname;
if (!["localhost", "127.0.0.1"].includes(host)) {
  console.error(`lighthouse-gate: refusing ${url} (local stack only)`);
  process.exit(2);
}

// Lighthouse needs a Chrome: Playwright's Chromium unless CHROME_PATH names another.
const env = { ...process.env, CHROME_PATH: process.env.CHROME_PATH || chromium.executablePath() };

let report;
try {
  const out = execFileSync(
    "npx",
    [
      "--yes",
      "lighthouse@13.6.0",
      url,
      "--preset=desktop",
      "--only-categories=performance",
      "--output=json",
      "--quiet",
      // --no-sandbox as Playwright launches it: Ubuntu 23.10+ blocks Chromium's user
      // namespace sandbox; the page is the local stack only.
      "--chrome-flags=--headless --no-sandbox",
    ],
    { encoding: "utf8", env, maxBuffer: 64 * 1024 * 1024 },
  );
  report = JSON.parse(out);
} catch (err) {
  console.error(`lighthouse-gate: lighthouse failed: ${err.message}`);
  process.exit(1);
}

const score = Math.round((report.categories?.performance?.score ?? 0) * 100);
const audits = report.audits ?? {};
const metric = (id) => audits[id]?.displayValue ?? "?";
console.log(
  `lighthouse-gate: performance ${score} (min ${MIN}) · FCP ${metric("first-contentful-paint")} · ` +
    `LCP ${metric("largest-contentful-paint")} · TBT ${metric("total-blocking-time")} · ` +
    `CLS ${metric("cumulative-layout-shift")}`,
);
process.exit(score >= MIN ? 0 : 1);
