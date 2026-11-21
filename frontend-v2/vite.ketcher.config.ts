// The Ketcher editor build: dist/ketcher/, served at /ketcher/ under the Ketcher CSP.
// Separate from the app build because a dedicated worker runs under the CSP of its own
// script response: the Indigo worker and its .wasm must be served from /ketcher/, not from
// the app's /assets/. Runs after the client build (which empties dist/); owns dist/ketcher/.
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL("./ketcher", import.meta.url)),
  base: "/ketcher/",
  publicDir: false,
  plugins: [react()],
  // Ketcher reads process.env, and some of its dependencies the Node `global`, at run time.
  define: { "process.env": {}, global: "globalThis" },
  build: {
    outDir: "../dist/ketcher",
    emptyOutDir: true,
    // Ketcher is large by nature; the size is recorded in the F1b report, not warned on.
    chunkSizeWarningLimit: 10000,
    // ketcher-core's ES build loads Raphael with a bare `require("raphael")`
    // (render/raphael-ext.modern.js); without this it stays a `require` call that throws in
    // the browser.
    commonjsOptions: { transformMixedEsModules: true },
  },
  // The Indigo worker is an ES module worker (new Worker(url, {type: "module"})).
  worker: { format: "es" },
});
