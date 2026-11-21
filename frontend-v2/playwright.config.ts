import { defineConfig, devices } from "@playwright/test";

// e2e runs against a served build: the local nginx (`npm run serve:local`, port 18091) in
// front of the fake stack, both started by hand (Group F header). Never production.
// The specs upload papers: any host but this machine is refused (never production).
const BASE = process.env.MARCUS_UI_URL ?? "http://localhost:18091";
if (!["localhost", "127.0.0.1"].includes(new URL(BASE).hostname)) {
  throw new Error(`e2e: refusing ${BASE} (local stack only)`);
}

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  retries: 0,
  // One shared stack (one database, one per-IP rate limit): tests run one at a time.
  workers: 1,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: BASE,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
