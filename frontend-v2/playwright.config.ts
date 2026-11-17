import { defineConfig, devices } from "@playwright/test";

// e2e runs against a served build (local nginx from F1b on), never production.
export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.MARCUS_UI_URL ?? "http://localhost:18091",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
