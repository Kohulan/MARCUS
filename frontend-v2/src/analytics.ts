// Matomo page views (tracker https://matomo.nfdi4chem.de/, site id 7, loaded by
// /matomo.js). A page view carries the route template, never a real paper, segment or
// image id: the URL and the title Matomo records are both the template.

declare global {
  interface Window {
    _paq?: unknown[];
  }
}

const TEMPLATES: [RegExp, string][] = [
  [/^\/$/, "/"],
  [/^\/about$/, "/about"],
  [/^\/privacy$/, "/privacy"],
  [/^\/disclaimer$/, "/disclaimer"],
  [/^\/app$/, "/app"],
  [/^\/app\/papers\/[^/]+$/, "/app/papers/:id"],
  [/^\/app\/images\/[^/]+$/, "/app/images/:id"],
];

/** The route template of a path: `/app/papers/3f2a` → `/app/papers/:id`; unknown → `/not-found`. */
export function routeTemplate(path: string): string {
  const clean = path.split(/[?#]/)[0] ?? "/";
  const trimmed = clean.length > 1 ? clean.replace(/\/+$/, "") : clean;
  for (const [pattern, template] of TEMPLATES) {
    if (pattern.test(trimmed)) return template;
  }
  return "/not-found";
}

/** Sends one page view for `path` (a path or its template). A no-op without the tracker. */
export function trackPage(path: string): void {
  const paq = typeof window === "undefined" ? undefined : window._paq;
  if (!paq) return;
  const template = routeTemplate(path);
  paq.push(["setCustomUrl", template]);
  paq.push(["setDocumentTitle", template]);
  paq.push(["trackPageView"]);
}
