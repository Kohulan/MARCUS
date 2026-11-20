// The paper's annotation (the local model's suggestion, or the curator's corrections) as the
// Paper view shows it: which spans of the text to mark, which occurrence a click goes to, and
// the editing of a field as lines. Model text is data: it is only ever a React text node.
import { ApiError, errorText } from "../api/client";
import { isStepActive } from "../api/status";
import type {
  AnnotationHit,
  AnnotationOut,
  AnnotationPositions,
  AnnotationValues,
  StepOut,
} from "../api/types";
import { newestFirst } from "./pageFailures";

/**
 * The longest value the server takes per field (backend-v2 core/annotation.py MAX_LENGTH: the
 * model's own maxLength); longer values get a 422.
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

/** Every occurrence of every shown value, per block (blocks and spans in first-seen order). */
export function blockRanges(
  values: AnnotationValues,
  positions: AnnotationPositions,
): Map<number, Span[]> {
  const out = new Map<number, Span[]>();
  for (const [field, list] of Object.entries(values)) {
    for (const value of list) {
      for (const [block, start, end] of hitsOf(positions, field, value)) {
        const spans = out.get(block);
        if (spans) spans.push([start, end]);
        else out.set(block, [[start, end]]);
      }
    }
  }
  return out;
}

export type Piece = { text: string; mark: boolean; current: boolean };

/**
 * A block's text cut where marks begin and end: overlapping marks merge, the current
 * occurrence's pieces say so. Spans outside the text are clipped (or dropped when empty).
 */
export function splitMarks(text: string, spans: Span[], current: Span | null): Piece[] {
  const len = text.length;
  const clip = ([s, e]: Span): Span | null => {
    const a = Math.max(0, Math.min(s, len));
    const b = Math.max(0, Math.min(e, len));
    return a < b ? [a, b] : null;
  };
  const marks = spans.map(clip).filter((s): s is Span => s !== null);
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
    const mark = isCurrent || marks.some(([s, e]) => s <= a && b <= e);
    const last = pieces[pieces.length - 1];
    if (last && last.mark === mark && last.current === isCurrent) last.text += text.slice(a, b);
    else pieces.push({ text: text.slice(a, b), mark, current: isCurrent });
  }
  return pieces;
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

/** Why the server would refuse these values (422), in words; null when it takes them. */
export function valuesProblem(
  values: AnnotationValues,
  label: (field: string) => string,
): string | null {
  const total = Object.values(values).reduce((n, list) => n + list.length, 0);
  if (total > TOTAL_MAX_VALUES) return `At most ${TOTAL_MAX_VALUES} values in all (${total} now).`;
  for (const [field, list] of Object.entries(values)) {
    if (list.length > FIELD_MAX_VALUES) {
      return `${label(field)} has more than ${FIELD_MAX_VALUES} values.`;
    }
    const max = Object.hasOwn(FIELD_MAX, field) ? FIELD_MAX[field] : undefined;
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
 * model is not running" or "Annotation is not available", 503 busy, 422), except the 429 of
 * the per-owner limit on corrections.
 */
export function annotationError(err: unknown): string {
  if (err instanceof ApiError && err.status === 429) return "Too many changes, try again in a minute";
  return errorText(err);
}
