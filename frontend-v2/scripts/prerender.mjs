// Pre-renders the static pages into dist/ after the client and SSR builds.
// The built dist/index.html is the template: it keeps the hashed asset links.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const PLACEHOLDER = '<div id="root"><!--app--></div>';

const template = await readFile(join(dist, "index.html"), "utf8");
if (!template.includes(PLACEHOLDER)) {
  throw new Error(`dist/index.html has no ${PLACEHOLDER} placeholder`);
}

const { render } = await import(pathToFileURL(join(root, "dist-ssr", "entry-server.js")).href);

const fill = (html) => template.replace(PLACEHOLDER, () => `<div id="root">${html}</div>`);

// url -> output file. Any path no route claims renders NotFound (route "*").
const pages = [
  ["/", "index.html"],
  ["/about", "about/index.html"],
  ["/privacy", "privacy/index.html"],
  ["/disclaimer", "disclaimer/index.html"],
  ["/__marcus_not_found__", "404.html"],
];

async function write(file, html) {
  const target = join(dist, file);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  console.log(`prerender: ${file}`);
}

// The shell nginx falls back to for every /app/... path: empty root,
// rendered on the client. Written first, from the untouched template.
await write("app/index.html", fill(""));

for (const [url, file] of pages) {
  await write(file, fill(render(url)));
}
