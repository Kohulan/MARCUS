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
  "MolParser or MolScribe, and helps you check them before they go into COCONUT.";

// Every page shows the Gmarket wordmark and Geist 700 (an h1, or the landing's initials) in
// its first screen; the landing also opens on Geist Mono 400 (the facts line, the drop hint).
const BASE = ["gmarket-mark", "geist-latin-700-normal"] as const;

const META: Record<string, PageMeta> = {
  "/": {
    title: "MARCUS · Molecular Annotation and Recognition for Curating Unravelled Structures",
    description: DESCRIPTION,
    preload: [...BASE, "geist-mono-latin-400-normal"],
  },
  "/about": {
    title: "About · MARCUS",
    description: "How MARCUS works, who makes it, how to cite it, and the publications behind it.",
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
