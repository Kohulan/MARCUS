// scripts/check-dist.mjs on a small fake dist/ (CHECK_DIST_DIR): the CSP rules it adds for
// inline event handlers and for the Ketcher page. Never reads the real dist/.
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const SCRIPT = join(process.cwd(), "scripts", "check-dist.mjs");
const MATOMO = '<script src="/matomo.js" defer></script>';

function page(title: string, body = "<p>ok</p>"): string {
  return `<!doctype html><html><head><title>${title}</title>${MATOMO}</head><body><!-- 6b4eb402 FORM: Survey Sheet -->${body}</body></html>`;
}

let dist: string;

function write(file: string, text: string) {
  const path = join(dist, file);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
}

function check(): { status: number | null; out: string } {
  const run = spawnSync(process.execPath, [SCRIPT], {
    env: { ...process.env, CHECK_DIST_DIR: dist },
    encoding: "utf8",
  });
  return { status: run.status, out: `${run.stdout}${run.stderr}` };
}

beforeEach(() => {
  dist = mkdtempSync(join(tmpdir(), "check-dist-"));
  write("index.html", page("Home", "<h1>Every molecule has a source.</h1>"));
  write("app/index.html", page("App", '<div id="root"></div>'));
  write("about/index.html", page("About"));
  write("privacy/index.html", page("Privacy"));
  write("disclaimer/index.html", page("Disclaimer"));
  write("404.html", page("Not found"));
  write("matomo.js", "");
  write(
    "ketcher/index.html",
    '<!doctype html><html><head><script type="module" src="/ketcher/assets/k.js"></script></head>' +
      '<body><div id="root" style="height:100%"></div></body></html>',
  );
});

afterEach(() => {
  rmSync(dist, { recursive: true, force: true });
});

describe("check-dist", () => {
  it("passes a clean dist (the Ketcher page may carry inline styles)", () => {
    const { status, out } = check();
    expect(out).toContain("check-dist: ok");
    expect(status).toBe(0);
  });

  it("fails on an inline event handler attribute in a page", () => {
    write("about/index.html", page("About", '<img src="/x.png" alt="" onerror="go()">'));
    const { status, out } = check();
    expect(status).toBe(1);
    expect(out).toMatch(/dist\/about\/index\.html: inline event handler onerror=/);
  });

  it("fails on an inline script or handler in the Ketcher page", () => {
    write(
      "ketcher/index.html",
      '<!doctype html><html><head><script>window.x = 1</script></head>' +
        '<body onload="start()"><div id="root"></div></body></html>',
    );
    const { status, out } = check();
    expect(status).toBe(1);
    expect(out).toMatch(/dist\/ketcher\/index\.html: inline <script>/);
    expect(out).toMatch(/dist\/ketcher\/index\.html: inline event handler onload=/);
  });

  it("does not take text that mentions onerror= for a handler", () => {
    write("about/index.html", page("About", "<p>An &lt;img onerror=…&gt; payload</p>"));
    const { status } = check();
    expect(status).toBe(0);
  });
});
