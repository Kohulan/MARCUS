// The paper's text as the Paper view shows it: Docling's document (GET /papers/{id}/text)
// flattened to headings and paragraphs, in reading order. Plain strings only: the view
// renders them as React text nodes, never as HTML.
import type { DoclingDoc } from "../api/types";

export type TextBlock = { kind: "heading" | "paragraph"; text: string };

type Ref = { $ref: string };

const HEADINGS = new Set(["title", "section_header"]);
const REF = /^#\/(texts|groups)\/(\d+)$/;

function block(item: { text: string; label: string } | undefined): TextBlock | null {
  if (!item || typeof item.text !== "string" || item.text.trim() === "") return null;
  return { kind: HEADINGS.has(item.label) ? "heading" : "paragraph", text: item.text };
}

/**
 * Walks `body.children` in order: `#/texts/<i>` is `texts[i]` followed by its own `children`
 * (nested list items under a list_item), `#/groups/<i>` is walked in turn (lists, inline
 * groups); tables, pictures and refs that point nowhere are skipped.
 * `title` and `section_header` are headings, every other text label is a paragraph.
 * Without a `body`, the texts in array order.
 */
export function doclingBlocks(doc: DoclingDoc): TextBlock[] {
  const texts = Array.isArray(doc.texts) ? doc.texts : [];
  if (!doc.body || !Array.isArray(doc.body.children)) {
    return texts.map(block).filter((b): b is TextBlock => b !== null);
  }
  const groups = Array.isArray(doc.groups) ? doc.groups : [];
  const out: TextBlock[] = [];
  const walking = new Set<string>(); // a malformed item that contains itself ends here

  const walk = (children: Ref[]) => {
    for (const child of children) {
      const m = REF.exec(child?.$ref ?? "");
      if (!m || walking.has(m[0])) continue;
      const i = Number(m[2]);
      const item = m[1] === "texts" ? texts[i] : groups[i];
      if (m[1] === "texts") {
        const b = block(texts[i]);
        if (b) out.push(b);
      }
      if (Array.isArray(item?.children)) {
        walking.add(m[0]);
        walk(item.children);
        walking.delete(m[0]);
      }
    }
  };
  walk(doc.body.children);
  return out;
}
