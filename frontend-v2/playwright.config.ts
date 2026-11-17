import { defineConfig, devices } from "@playwright/test";

// e2e runs against a served build: the local nginx (`npm run serve:local`, port 18091) in
// front of the fake stack, both started by hand (Group F header). Never production.
export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  retries: 0,
  // One shared stack (one database, one per-IP rate limit): tests run one at a time.
  workers: 1,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: process.env.MARCUS_UI_URL ?? "http://localhost:18091",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
