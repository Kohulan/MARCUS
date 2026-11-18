import { useEffect } from "react";

/** What a pre-rendered page puts in its <head>: title, description, the fonts to preload. */
export type PageMeta = {
  title: string;
  description: string;
  /** File-name stems of the font preloads in index.html this page keeps (above the fold). */
  preload: readonly string[];
};

const DESCRIPTION =
  "MARCUS finds the chemical structures in a scientific PDF, reads them with DECIMER, " +
  "MolNexTR or MolScribe, and helps you check them before they go into COCONUT.";

// Every page shows the Gmarket wordmark and a Geist 700 h1 in its first screen; the
// landing also opens on the Geist Mono readouts of the hero sheet.
const BASE = ["gmarket-mark", "geist-latin-700-normal"] as const;

const META: Record<string, PageMeta> = {
  "/": {
    title: "MARCUS · Every molecule has a source",
    description: DESCRIPTION,
    preload: [...BASE, "geist-mono-latin-400-normal"],
  },
  "/about": {
    title: "About · MARCUS",
    description: "Who makes MARCUS, the publications behind it, and how to take part.",
    preload: BASE,
  },
  "/privacy": {
    title: "Privacy · MARCUS",
    description: "What MARCUS stores, for how long, and the one tracker it uses (Matomo).",
    preload: BASE,
  },
  "/disclaimer": {
    title: "Disclaimer · MARCUS",
    description: "MARCUS is a research tool: check every structure before you use it.",
    preload: BASE,
  },
};

const NOT_FOUND: PageMeta = {
  title: "Page not found · MARCUS",
  description: DESCRIPTION,
  preload: BASE,
};

/** The head of the /app shell (rendered on the client; the tool sets its own titles). */
export const APP_SHELL_META: PageMeta = { title: "MARCUS", description: DESCRIPTION, preload: BASE };

/** The head of the pre-rendered page at `url`; any other path is the not-found page. */
export function pageMeta(url: string): PageMeta {
  const path = url.length > 1 ? url.replace(/\/+$/, "") : url;
  return META[path] ?? NOT_FOUND;
}

/** Keeps document.title right after a client-side navigation (the pre-render sets it first). */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
