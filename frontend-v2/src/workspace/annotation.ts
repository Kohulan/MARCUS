// The paper's annotation (the local model's suggestion, or the curator's corrections) as the
// Paper view shows it: which spans of the text to mark, which occurrence a click goes to, and
// the editing of a field as lines. Model text is data: it is only ever a React text node.
import { ApiError, errorText } from "../api/client";
import { isPaperBusy, isStepActive } from "../api/status";
import type {
  AnnotationHit,
  AnnotationField,
  AnnotationOut,
  AnnotationPositions,
  AnnotationValues,
  StepOut,
} from "../api/types";
import { newestFirst } from "./pageFailures";

/**
 * The longest value the server takes per field (backend-v2 core/annotation.py MAX_LENGTH: the
 * model's own maxLength); longer values get a 422. The API sends each field's limit
 * (`fields[].max_length`, which fieldMax prefers); this copy is only the fallback.
 */
export const FIELD_MAX: Readonly<Record<string, number>> = {
  compound_group: 435,
  compound_class: 576,
  organism_part: 183,
  organism_or_species: 676,
  geo_location: 348,
  Kingdom: 60,
  trivial_name: 397,
  location: 234,
  iupac_name: 7179,
  abbreviation: 586,
  iupac_like_name: 990,
};

/** The most values a field keeps (MAX_VALUES_PER_FIELD). */
export const FIELD_MAX_VALUES = 200;

/** The most values a correction holds in all fields together (more: 422). */
export const TOTAL_MAX_VALUES = 300;

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

/**
 * A block's text cut where marks begin and end, into flat pieces (marks never nest). Where
 * two fields cover the same text, the clicked occurrence's field leads, else the most
 * specific (the shortest span; on a tie, the first): its colour, both names. Spans outside
 * the text are clipped (or dropped when empty).
 */
export function splitMarks(text: string, spans: FieldSpan[], current: FieldSpan | null): Piece[] {
  const len = text.length;
  const clip = ([s, e, field]: FieldSpan): FieldSpan | null => {
    const a = Math.max(0, Math.min(s, len));
    const b = Math.max(0, Math.min(e, len));
    return a < b ? [a, b, field] : null;
  };
  const marks = spans.map(clip).filter((s): s is FieldSpan => s !== null);
  const cur = current ? clip(current) : null;
  const cuts = new Set<number>([0, len]);
  for (const [s, e] of cur ? [...marks, cur] : marks) {
    cuts.add(s);
    cuts.add(e);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const pieces: Piece[] = [];
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    const isCurrent = cur !== null && cur[0] <= a && b <= cur[1];
    const over = marks.filter(([s, e]) => s <= a && b <= e);
    let lead: string | undefined = isCurrent ? cur[2] : undefined;
    if (lead === undefined && over.length > 0) {
      lead = over.reduce((best, m) => (m[1] - m[0] < best[1] - best[0] ? m : best))[2];
    }
    const fields = lead === undefined ? [] : [lead];
    for (const [, , f] of over) if (!fields.includes(f)) fields.push(f);
    const last = pieces[pieces.length - 1];
    if (last && last.current === isCurrent && sameList(last.fields, fields)) last.text += text.slice(a, b);
    else pieces.push({ text: text.slice(a, b), fields, current: isCurrent });
  }
  return pieces;
}

const sameList = (x: string[], y: string[]) => x.length === y.length && x.every((v, i) => v === y[i]);

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

/** The paper's newest annotate step. */
export function newestAnnotate(steps: StepOut[]): StepOut | undefined {
  return newestFirst(steps.filter((s) => s.kind === "annotate"))[0];
}

/** The paper is busy only because it is being annotated (its other steps are finished). */
export function onlyAnnotating(steps: StepOut[]): boolean {
  const ann = newestAnnotate(steps);
  if (!ann || !isStepActive(ann.status)) return false;
  return steps.every((s) => s.kind === "annotate" || !isStepActive(s.status));
}

/**
 * The paper is being read: busy with more than its annotation (an annotate run makes a done
 * paper processing again; the server's `annotating` or the steps say when that is all).
 */
export function isPaperReading(
  paper: { status: string; annotating?: boolean | undefined },
  steps: StepOut[],
): boolean {
  return isPaperBusy(paper.status) && !paper.annotating && !onlyAnnotating(steps);
}

const REASONS: Record<string, string> = {
  timeout: "it took too long",
  worker_lost: "the worker stopped",
  bad_input: "no title, abstract or introduction was found",
  engine_error: "the model failed",
};

/** Why an annotate step failed, from its coarse error_class. */
export function annotateReason(errorClass: string | null): string {
  if (errorClass !== null && Object.hasOwn(REASONS, errorClass)) return REASONS[errorClass]!;
  return "an unknown error";
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

/** The longest value a field takes: the API's `max_length`, else the client's FIELD_MAX. */
export function fieldMax(fields: readonly AnnotationField[], key: string): number | undefined {
  const served = fields.find((f) => f.key === key)?.max_length;
  if (typeof served === "number" && Number.isInteger(served) && served > 0) return served;
  return Object.hasOwn(FIELD_MAX, key) ? FIELD_MAX[key] : undefined;
}

/** Why the server would refuse these values (422), in words; null when it takes them. */
export function valuesProblem(
  values: AnnotationValues,
  label: (field: string) => string,
  fields: readonly AnnotationField[] = [],
): string | null {
  const total = Object.values(values).reduce((n, list) => n + list.length, 0);
  if (total > TOTAL_MAX_VALUES) return `At most ${TOTAL_MAX_VALUES} values in all (${total} now).`;
  for (const [field, list] of Object.entries(values)) {
    if (list.length > FIELD_MAX_VALUES) {
      return `${label(field)} has more than ${FIELD_MAX_VALUES} values.`;
    }
    const max = fieldMax(fields, field);
    if (max !== undefined && list.some((v) => v.length > max)) {
      return `A value in ${label(field)} is longer than ${max.toLocaleString("en")} characters.`;
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

/**
 * A refused start, save or reset in a few words: the API's own detail (503 "The annotation
 * model is not running" or "Annotation is not available", 503 busy, 422), except a 429: the
 * per-owner limit on starts (5 a minute) or on corrections.
 */
export function annotationError(err: unknown, action: "start" | "change" = "change"): string {
  if (err instanceof ApiError && err.status === 429) {
    return action === "start"
      ? "Too many starts, try again in a minute"
      : "Too many changes, try again in a minute";
  }
  return errorText(err);
}
