// The main figure: the page the user marks as the paper's compound list. Its structures come
// first; a structure on another page that shows the same compound (the server's `repeat_of`:
// same InChIKey) is a repeat, shown once, on its main-figure card ("Also on page N").
import type { SegmentOut } from "../api/types";

/** The main page's segments first, then the rest, each in (page, idx) order. */
export function mainFirst(segments: SegmentOut[], mainPage: number | null | undefined): SegmentOut[] {
  const rank = (s: SegmentOut) => (s.page === mainPage ? 0 : 1);
  return [...segments].sort((a, b) => rank(a) - rank(b) || a.page - b.page || a.idx - b.idx);
}

/** A repeat of a main-figure structure: not listed on its own. */
export const isRepeat = (segment: SegmentOut): boolean => Boolean(segment.repeat_of);

/** The segments listed as structures: all but the repeats, in the order given. */
export const listedSegments = (segments: SegmentOut[]): SegmentOut[] =>
  segments.some(isRepeat) ? segments.filter((s) => !isRepeat(s)) : segments;

/** Per main-figure segment id: the pages (1-based, sorted, once each) of its repeats. */
export function repeatPages(segments: SegmentOut[]): Map<string, number[]> {
  const out = new Map<string, number[]>();
  for (const s of segments) {
    if (!s.repeat_of) continue;
    const pages = out.get(s.repeat_of) ?? [];
    if (!pages.includes(s.page + 1)) pages.push(s.page + 1);
    out.set(s.repeat_of, pages);
  }
  for (const pages of out.values()) pages.sort((a, b) => a - b);
  return out;
}

/** "Also on page 5", "Also on pages 5, 7"; null for none. */
export function alsoOnText(pages: number[] | undefined): string | null {
  if (!pages || pages.length === 0) return null;
  return `Also on ${pages.length === 1 ? "page" : "pages"} ${pages.join(", ")}`;
}
