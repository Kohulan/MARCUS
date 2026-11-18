// What the status bar reads from a paper's steps. Pages are 0-based here, as in the API.
import { reasonText } from "../api/reasons";
import type { StepOut } from "../api/types";

export type PageFailure = { page0: number; errorClass: string | null; retrying: boolean };

const PAGE_KINDS = new Set(["render_page", "segment_page"]);
const ACTIVE = new Set(["pending", "queued", "running"]);

const ms = (iso: string) => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
};

/**
 * Newest first, as the server's page_step_order: created_at, then kind (segment_page before
 * render_page), then the later one in the list (steps come oldest first, by created_at and
 * seq). Same-millisecond times fall back to the ISO strings, which carry microseconds.
 */
function newestFirst(steps: StepOut[]): StepOut[] {
  return steps
    .map((s, i) => ({ s, i }))
    .sort(
      (a, b) =>
        ms(b.s.created_at) - ms(a.s.created_at) ||
        b.s.created_at.localeCompare(a.s.created_at) ||
        b.s.kind.localeCompare(a.s.kind) ||
        b.i - a.i,
    )
    .map(({ s }) => s);
}

/** Each page's render_page and segment_page steps, newest first. */
function pageSteps(steps: StepOut[]): Map<number, StepOut[]> {
  const byPage = new Map<number, StepOut[]>();
  for (const s of newestFirst(steps)) {
    if (!PAGE_KINDS.has(s.kind) || s.page === null) continue;
    const list = byPage.get(s.page) ?? [];
    list.push(s);
    byPage.set(s.page, list);
  }
  return byPage;
}

/**
 * The failed pages, by the server's failed_pages rule (F0-1, R-F10): per page, the newest
 * render_page or segment_page step decides. Failed → listed. Active after an older failure →
 * listed as retrying (with the old failure's class). Done, or never failed → not listed.
 */
export function pageFailures(steps: StepOut[]): PageFailure[] {
  const out: PageFailure[] = [];
  for (const [page0, list] of pageSteps(steps)) {
    const newest = list[0]!;
    if (newest.status === "failed") {
      out.push({ page0, errorClass: newest.error_class, retrying: false });
    } else if (ACTIVE.has(newest.status)) {
      const failed = list.find((s) => s.status === "failed");
      if (failed) out.push({ page0, errorClass: failed.error_class, retrying: true });
    }
  }
  return out.sort((a, b) => a.page0 - b.page0);
}

const BAD_PDF = "it is encrypted, damaged or has more than 100 pages";

/** Why the PDF check failed (its newest check_pdf step), or null when it did not fail. */
export function checkFailure(steps: StepOut[]): string | null {
  const check = newestFirst(steps).find((s) => s.kind === "check_pdf");
  if (!check || check.status !== "failed") return null;
  return check.error_class === "bad_input" ? BAD_PDF : reasonText(check.error_class);
}

export type Progress = {
  pagesRead: number;
  /** Null until the PDF check has counted the pages. */
  pages: number | null;
  structuresRead: number;
  /** Segments with an ocsr step (0 for a paper uploaded with ocsr=off). */
  structures: number;
};

/**
 * Pages read: pages whose newest page step is done. A done render_page is the newest only
 * when the segmentation cache gave the page its segments: otherwise its segment_page step is
 * created in the same transaction that finishes the render (backend pipeline.py), so it is
 * already newer. Structures read:
 * segments with a finished ocsr step, of the segments that have one (a second engine run
 * on a read structure does not make it unread).
 */
export function progress(steps: StepOut[], pages: number | null): Progress {
  let pagesRead = 0;
  for (const list of pageSteps(steps).values()) {
    const newest = list[0]!;
    if (newest.status === "done") pagesRead += 1;
  }
  const read = new Set<string>();
  const all = new Set<string>();
  for (const s of steps) {
    if (s.kind !== "ocsr" || s.segment_id === null) continue;
    all.add(s.segment_id);
    if (s.status === "done") read.add(s.segment_id);
  }
  return { pagesRead, pages, structuresRead: read.size, structures: all.size };
}
