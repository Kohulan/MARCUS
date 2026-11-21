// R-group (Markush) placeholders: a drawing with R1, X, Ar… stands for several compounds, not
// one. The server finds the labels (backend-v2 marcus/core/rgroups.py) and sends them with each
// prediction and curation as `rgroups`. Pure helpers, so the words are pinned by tests.
import type { DoclingDoc } from "../api/types";

const NONE: readonly string[] = Object.freeze([]);

/** The labels of a prediction or curation ([] for none, or from an older server). */
export function rgroupsOf(row: { rgroups?: string[] | undefined } | null | undefined): string[] {
  return (row?.rgroups ?? NONE) as string[];
}

/** "R1, R2" */
export const labelList = (labels: readonly string[]): string => labels.join(", ");

/** The tag beside the state badge (card, Paper view): "R-groups: R1, R2". */
export const rgroupTag = (labels: readonly string[]): string => `R-groups: ${labelList(labels)}`;

/** A prediction's result word: "R-group scaffold (R1, R2)", else "Valid" or "Invalid". */
export function resultWord(p: { valid: boolean; rgroups?: string[] | undefined }): string {
  const labels = rgroupsOf(p);
  if (labels.length > 0) return `R-group scaffold (${labelList(labels)})`;
  return p.valid ? "Valid" : "Invalid";
}

/** Focus mode's line under the structure. */
export function rgroupNotice(labels: readonly string[], definitionsOnPage: boolean): string {
  const line = `This drawing has R-groups (${labelList(labels)}): it stands for several compounds.`;
  return definitionsOnPage ? `${line} Definitions found on this page.` : line;
}

// --- the text signal: definitions on the page ------------------------------------------------

/**
 * "R1 = OMe", "R' = H", "X = Cl", "Ar = Ph": a label, then "=". Not inside a word (PAR = …);
 * Docling may space a subscript ("R 1 =") or keep it as a Unicode subscript (R₁).
 */
const DEFINITION = /(?<![\p{L}\p{N}])(?:R\s?[0-9₀-₉]{0,2}['′]?|X\s?[0-9₀-₉]{0,2}|Ar)\s*=/u;
/**
 * A table cell that is only a numbered or primed label (a column head "R1", "R'" over the
 * substituents). Not a bare "R" (an R/S configuration column) or "X" (a tick).
 */
const LABEL_CELL = /^\s*R(?:\s?[0-9₀-₉]{1,2}['′]?|['′])\s*$/u;

type Prov = { page_no?: unknown };

function pagesOf(prov: unknown): number[] {
  if (!Array.isArray(prov)) return [];
  return (prov as Prov[])
    .map((p) => p?.page_no)
    .filter((n): n is number => typeof n === "number" && Number.isInteger(n) && n >= 1)
    .map((n) => n - 1); // Docling counts pages from 1, the API from 0
}

/**
 * The 0-based pages whose text defines R-groups: any text item (caption, footnote, paragraph,
 * list item) with "R1 = …", or a table cell with that or with only a label. A supporting
 * signal: it says definitions are likely on the page, not which ones.
 */
export function definitionPages(doc: DoclingDoc): Set<number> {
  const pages = new Set<number>();
  const texts = Array.isArray(doc.texts) ? doc.texts : [];
  for (const t of texts) {
    if (typeof t?.text === "string" && DEFINITION.test(t.text)) {
      for (const p of pagesOf(t.prov)) pages.add(p);
    }
  }
  const tables = Array.isArray(doc.tables) ? doc.tables : [];
  for (const table of tables) {
    const cells = table?.data?.table_cells;
    if (!Array.isArray(cells)) continue;
    const hit = cells.some(
      (c) => typeof c?.text === "string" && (DEFINITION.test(c.text) || LABEL_CELL.test(c.text)),
    );
    if (hit) for (const p of pagesOf(table.prov)) pages.add(p);
  }
  return pages;
}
