// The paper's annotation (the local model's suggestion, or the curator's corrections) as the
// Paper view shows it: which spans of the text to mark, which occurrence a click goes to, and
// the editing of a field as lines. Model text is data: it is only ever a React text node.
import type {
  AnnotationHit,
  AnnotationField,
  AnnotationLimits,
  AnnotationOut,
  AnnotationPositions,
  AnnotationValues,
} from "../api/types";

/** The positions of the values shown: the curator's once saved, else the model's. */
export function shownPositions(a: AnnotationOut): AnnotationPositions {
  return (a.curated !== null ? a.curated_positions : a.positions) ?? {};
}

/**
 * A value's occurrences ([] when none). Positions are keyed by model or curator text, which
 * can be "__proto__" or "constructor": only own keys count, never an inherited property.
 */
export function hitsOf(
  positions: AnnotationPositions,
  field: string,
  value: string,
): AnnotationHit[] {
  if (!Object.hasOwn(positions, field)) return [];
  const byValue = positions[field]!;
  if (!Object.hasOwn(byValue, value)) return [];
  const hits = byValue[value];
  return Array.isArray(hits) ? hits : [];
}

/** A field's shown values ([] when none; only own keys count). */
export function valuesIn(values: AnnotationValues | null, field: string): string[] {
  if (!values || !Object.hasOwn(values, field)) return [];
  const list = values[field];
  return Array.isArray(list) ? list : [];
}

export type Span = [start: number, end: number];

/** An occurrence in a block's text and the field whose value it is. */
export type FieldSpan = [start: number, end: number, field: string];

/** Every occurrence of every shown value, per block (blocks and spans in first-seen order). */
export function blockRanges(
  values: AnnotationValues,
  positions: AnnotationPositions,
): Map<number, FieldSpan[]> {
  const out = new Map<number, FieldSpan[]>();
  for (const [field, list] of Object.entries(values)) {
    for (const value of list) {
      for (const [block, start, end] of hitsOf(positions, field, value)) {
        const spans = out.get(block);
        if (spans) spans.push([start, end, field]);
        else out.set(block, [[start, end, field]]);
      }
    }
  }
  return out;
}

/**
 * A run of a block's text. `fields`: the fields whose values cover it ([] for plain text), the
 * one whose colour it takes first. `current`: it is in the occurrence a click went to.
 */
export type Piece = { text: string; fields: string[]; current: boolean };

/** A run of a block's text (no current occurrence): the fields over it, in span order, and its lead. */
export type MarkRun = { start: number; end: number; over: string[]; lead: string | undefined };

const clipTo = (len: number, [s, e, field]: FieldSpan): FieldSpan | null => {
  const a = Math.max(0, Math.min(s, len));
  const b = Math.max(0, Math.min(e, len));
  return a < b ? [a, b, field] : null;
};

/**
 * A block's text (`len` long) cut where marks begin and end: one sweep over the sorted
 * boundaries with the spans that cover each run. Where two fields cover the same text, the
 * most specific (the shortest span; on a tie, the first) leads. Neighbouring runs under the same
 * fields are one. Spans outside the text are clipped (or dropped when empty).
 */
export function markRuns(len: number, spans: FieldSpan[]): MarkRun[] {
  const marks = spans.map((s) => clipTo(len, s)).filter((s): s is FieldSpan => s !== null);
  const points = [...new Set([0, len, ...marks.flatMap(([s, e]) => [s, e])])].sort((a, b) => a - b);
  const byStart = marks.map((_, i) => i).sort((i, j) => marks[i]![0] - marks[j]![0]);
  let next = 0;
  let active: number[] = []; // indices into marks, in span order
  const runs: MarkRun[] = [];
  for (let k = 0; k + 1 < points.length; k++) {
    const a = points[k]!;
    const b = points[k + 1]!;
    active = active.filter((i) => marks[i]![1] > a);
    let added = false;
    while (next < byStart.length && marks[byStart[next]!]![0] <= a) {
      active.push(byStart[next]!);
      next += 1;
      added = true;
    }
    if (added) active.sort((i, j) => i - j);
    const over: string[] = [];
    let lead: FieldSpan | undefined;
    for (const i of active) {
      const m = marks[i]!;
      if (!over.includes(m[2])) over.push(m[2]);
      if (!lead || m[1] - m[0] < lead[1] - lead[0]) lead = m;
    }
    const last = runs[runs.length - 1];
    if (last && last.lead === lead?.[2] && sameList(last.over, over)) last.end = b;
    else runs.push({ start: a, end: b, over, lead: lead?.[2] });
  }
  return runs;
}

/**
 * A block's runs (markRuns) as flat pieces (marks never nest), with the clicked occurrence
 * (`current`) laid over them as one piece: led by its field, naming every field found inside it.
 */
export function piecesOf(text: string, runs: MarkRun[], current: FieldSpan | null): Piece[] {
  const cur = current ? clipTo(text.length, current) : null;
  const pieces: Piece[] = [];
  const plain = (r: MarkRun, a: number, b: number) => {
    if (a >= b) return;
    const fields = r.lead === undefined ? [] : [r.lead, ...r.over.filter((f) => f !== r.lead)];
    pieces.push({ text: text.slice(a, b), fields, current: false });
  };
  let mark: Piece | null = null;
  for (const r of runs) {
    if (!cur || r.end <= cur[0] || r.start >= cur[1]) {
      plain(r, r.start, r.end);
      continue;
    }
    plain(r, r.start, cur[0]);
    if (!mark) {
      mark = { text: text.slice(cur[0], cur[1]), fields: [cur[2]], current: true };
      pieces.push(mark);
    }
    for (const f of r.over) if (!mark.fields.includes(f)) mark.fields.push(f);
    plain(r, cur[1], r.end);
  }
  return pieces;
}

/**
 * A block's text cut where marks begin and end, into flat pieces (markRuns, then piecesOf).
 * Where two fields cover the same text, the clicked occurrence's field leads, else the most
 * specific (the shortest span; on a tie, the first): its colour, both names. The clicked
 * occurrence is one piece, whatever other fields cover parts of it. Spans outside the text
 * are clipped (or dropped when empty).
 */
export function splitMarks(text: string, spans: FieldSpan[], current: FieldSpan | null): Piece[] {
  return piecesOf(text, markRuns(text.length, spans), current);
}

const sameList = (x: string[], y: string[]) => x.length === y.length && x.every((v, i) => v === y[i]);

/** A field's label, else its key. */
export function fieldLabel(fields: readonly AnnotationField[] | undefined, key: string): string {
  return fields?.find((f) => f.key === key)?.label ?? key;
}

/**
 * The colour families of the highlights (DESIGN.md Annotation): the 11 fields in 6 groups a
 * curator reads together. Each family is a tint, a deep colour and an underline style
 * (tokens.css --ann-*, paper.css .pv-fam--*).
 */
export const FAMILIES = {
  organism: ["organism_or_species", "Kingdom"],
  part: ["organism_part"],
  place: ["geo_location", "location"],
  name: ["trivial_name", "abbreviation"],
  class: ["compound_class", "compound_group"],
  systematic: ["iupac_name", "iupac_like_name"],
} as const satisfies Record<string, readonly string[]>;

/** A family, or `other` for a field the client does not know (a plain tint). */
export type Family = keyof typeof FAMILIES | "other";

const FAMILY_OF = new Map<string, Family>(
  Object.entries(FAMILIES).flatMap(([family, fields]) =>
    fields.map((f) => [f, family as Family] as const),
  ),
);

/** The colour family of a field. */
export function familyOf(field: string): Family {
  return FAMILY_OF.get(field) ?? "other";
}

/** The class that gives an element its field's colours. */
export const familyClass = (field: string): string => `pv-fam--${familyOf(field)}`;

/** A mark's name: its fields' labels, the leading one first ("Compound names, Abbreviations"). */
export function markLabel(fields: readonly string[], label: (field: string) => string): string {
  return fields.map(label).join(", ");
}

/** The occurrence a click shows: where the value's walk stands. */
export type HitAt = { field: string; value: string; index: number };

/** A click on a value: its first occurrence, or (clicked again) the next, around to the first. */
export function nextHit(at: HitAt | null, field: string, value: string, count: number): number {
  if (!at || at.field !== field || at.value !== value || count === 0) return 0;
  return (at.index + 1) % count;
}

/** A field's values as the editor's lines. */
export const linesOf = (values: string[]): string => values.join("\n");

/** The editor's lines as values: trimmed, blanks and exact repeats out (as the server does). */
export function valuesOf(lines: string): string[] {
  const out: string[] = [];
  for (const line of lines.split(/\r?\n/)) {
    const value = line.trim();
    if (value && !out.includes(value)) out.push(value);
  }
  return out;
}

/**
 * Why the server would refuse these values (422), in words, from the limits it serves (each
 * field's `max_length`, the save's `limits`); null when it takes them. A pre-check only: the
 * server's 422 detail is shown too.
 */
export function valuesProblem(
  values: AnnotationValues,
  fields: readonly AnnotationField[],
  limits: AnnotationLimits,
): string | null {
  const { max_total_values: total, max_values_per_field: perField } = limits;
  const count = Object.values(values).reduce((n, list) => n + list.length, 0);
  if (count > total) return `At most ${total} values in all (${count} now).`;
  for (const [field, list] of Object.entries(values)) {
    const label = fieldLabel(fields, field);
    if (list.length > perField) return `${label} has more than ${perField} values.`;
    const max = fields.find((f) => f.key === field)?.max_length;
    if (max !== undefined && list.some((v) => v.length > max)) {
      return `A value in ${label} is longer than ${max.toLocaleString("en")} characters.`;
    }
  }
  return null;
}

/** Same values in the same order per field; a field that is missing has none. */
export function sameValues(a: AnnotationValues, b: AnnotationValues): boolean {
  const fields = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const f of fields) {
    const x = a[f] ?? [];
    const y = b[f] ?? [];
    if (x.length !== y.length || x.some((v, i) => v !== y[i])) return false;
  }
  return true;
}
