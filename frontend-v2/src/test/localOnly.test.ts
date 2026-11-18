// The e2e runs and the review-screenshot script upload papers to whatever they are pointed
// at: both refuse any host but localhost and 127.0.0.1 (never production), as the
// Lighthouse gate already does.
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();

function run(args: string[], url: string) {
  const done = spawnSync(process.execPath, args, {
    cwd: ROOT,
    env: { ...process.env, MARCUS_UI_URL: url },
    encoding: "utf8",
    timeout: 60_000,
  });
  return { status: done.status, out: `${done.stdout}${done.stderr}` };
}

describe("local stack only", () => {
  it("scripts/capture-review.mjs refuses a non-local host", () => {
    const { status, out } = run([join(ROOT, "scripts", "capture-review.mjs")], "https://marcus.example.org");
    expect(status).toBe(2);
    expect(out).toContain("refusing https://marcus.example.org");
  });

  it("the e2e config refuses a non-local MARCUS_UI_URL", () => {
    const cli = join(ROOT, "node_modules", "@playwright", "test", "cli.js");
    const { status, out } = run([cli, "test", "--list"], "https://marcus.example.org:8080");
    expect(status).not.toBe(0);
    expect(out).toContain("refusing https://marcus.example.org:8080");
  }, 60_000);
});
