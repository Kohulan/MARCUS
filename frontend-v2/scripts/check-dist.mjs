// Fails the build when dist/ breaks the design contract or the CSP rules.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const failures = [];
const fail = (message) => failures.push(message);
const read = (file) => readFileSync(join(dist, file), "utf8");

function htmlFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const rel = relative(dist, path);
    if (rel === "ketcher" || rel.startsWith(`ketcher${sep}`)) continue; // own CSP (F1b)
    if (statSync(path).isDirectory()) out.push(...htmlFiles(path));
    else if (name.endsWith(".html")) out.push(rel);
  }
  return out;
}

const required = [
  "index.html",
  "app/index.html",
  "about/index.html",
  "privacy/index.html",
  "disclaimer/index.html",
  "404.html",
];
for (const file of required) {
  if (!existsSync(join(dist, file))) fail(`missing dist/${file}`);
}

// Each content check runs on whatever exists, so one missing file does not
// hide other problems.
const has = (file) => existsSync(join(dist, file));
for (const file of ["index.html", "app/index.html"]) {
  if (has(file) && !read(file).includes("6b4eb402")) {
    fail(`dist/${file}: design contract (6b4eb402) missing`);
  }
}
if (has("index.html") && !read("index.html").includes("Every molecule has a source.")) {
  fail("dist/index.html: landing headline not pre-rendered");
}
if (has("app/index.html") && !read("app/index.html").includes('<div id="root"></div>')) {
  fail("dist/app/index.html: #root is not empty");
}

for (const file of existsSync(dist) ? htmlFiles(dist) : []) {
  const html = read(file);
  if (html.includes(" style=")) fail(`dist/${file}: inline style attribute (CSP style-src 'self')`);
  for (const tag of html.match(/<script\b[^>]*>/gi) ?? []) {
    if (!/\ssrc=/i.test(tag)) fail(`dist/${file}: inline <script> (CSP script-src 'self'): ${tag}`);
  }
  if (/<style\b/i.test(html)) fail(`dist/${file}: inline <style> block (CSP style-src 'self')`);
}

if (failures.length > 0) {
  console.error(`check-dist: ${failures.length} problem(s)`);
  for (const message of failures) console.error(`  - ${message}`);
  process.exit(1);
}
console.log("check-dist: ok");
