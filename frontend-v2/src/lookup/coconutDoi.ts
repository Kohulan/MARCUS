// How many molecules COCONUT already holds for a DOI (v1 PdfViewerObject.checkInCoconut):
// a tag search on citations, no login. Any failure is null.
import { fetchJson, isRecord } from "./fetchJson";

const SEARCH = "https://coconut.naturalproducts.net/api/search";
export const COCONUT_PAGE_SIZE = 20;

export type CoconutDoiCount = { count: number; more: boolean; url: string };

function rows(body: unknown): unknown[] {
  if (Array.isArray(body)) return body;
  if (!isRecord(body)) return [];
  const data = body.data;
  if (isRecord(data) && Array.isArray(data.data)) return data.data;
  if (Array.isArray(data)) return data;
  if (Array.isArray(body.results)) return body.results;
  return [];
}

function identifier(row: unknown): string | null {
  if (!isRecord(row)) return null;
  for (const key of ["id", "coconut_id", "identifier"]) {
    const v = row[key];
    if (
      (typeof v === "string" && v) ||
      (typeof v === "number" && Number.isFinite(v))
    ) {
      return String(v);
    }
  }
  return null;
}

export async function coconutCountForDoi(
  doi: string,
  signal?: AbortSignal,
): Promise<CoconutDoiCount | null> {
  const clean = doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
  if (!clean) return null;
  try {
    const body = await fetchJson(
      SEARCH,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          type: "tags",
          tagType: "citations",
          query: clean,
          limit: COCONUT_PAGE_SIZE,
          sort: "desc",
          page: 1,
          offset: 0,
        }),
      },
      signal,
    );
    if (body === undefined) return null;
    const list = rows(body);
    const ids = new Set<string>();
    for (const row of list) {
      const id = identifier(row);
      if (id !== null) ids.add(id);
    }
    return {
      count: ids.size,
      more: list.length >= COCONUT_PAGE_SIZE,
      url: `https://coconut.naturalproducts.net/search?q=${encodeURIComponent(clean)}&tagType=citations&type=tags&activeTab=citations`,
    };
  } catch {
    return null;
  }
}
